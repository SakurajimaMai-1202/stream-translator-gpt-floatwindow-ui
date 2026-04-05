import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import ffmpeg
import numpy as np

from .common import SAMPLE_RATE, SAMPLES_PER_FRAME, FRAME_DURATION, LoopWorkerBase, INFO, WARNING, ERROR


def _is_twitter_url(url: str) -> bool:
    """判斷是否為 X/Twitter 相關網址。"""
    try:
        hostname = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False

    if not hostname:
        return False

    return hostname in {
        'x.com',
        'www.x.com',
        'twitter.com',
        'www.twitter.com',
        'mobile.x.com',
        'mobile.twitter.com',
    } or hostname.endswith('.x.com') or hostname.endswith('.twitter.com')


def _resolve_cookie_file(url: str, cookies: str | None) -> str | None:
    """解析 cookies 檔案，缺失或明顯不相干時自動忽略。"""
    if not cookies:
        return None

    cookie_path = os.path.expandvars(os.path.expanduser(str(cookies).strip()))
    if not cookie_path:
        return None

    if not os.path.isfile(cookie_path):
        print(f'{WARNING}Cookies 檔案不存在，已忽略：{cookie_path}')
        return None

    if _is_twitter_url(url):
        file_name = os.path.basename(cookie_path).lower()
        if any(marker in file_name for marker in ('youtube', 'youtu')):
            print(
                f'{WARNING}偵測到 X/Twitter URL 搭配 YouTube cookies，'
                '已自動忽略 cookies 以降低 guest token / API 錯誤。'
            )
            return None

    return cookie_path


def _append_site_specific_ytdlp_args(cmd: list[str], url: str) -> None:
    """依站點補上較穩定的 yt-dlp 參數。"""
    if _is_twitter_url(url):
        # X/Twitter 的 GraphQL / guest token 經常波動；
        # 官方 issue 建議改走 syndication endpoint 作為 workaround。
        cmd.extend(['--extractor-args', 'twitter:api=syndication'])


def _build_ytdlp_command(url: str,
                         format: str,
                         cookies: str,
                         proxy: str,
                         *,
                         ffmpeg_dir: str | None = None,
                         js_runtime_arg: str | None = None) -> list[str]:
    """建構 yt-dlp 命令列，方便重用與測試。"""
    cmd = _resolve_ytdlp_command() + [url, '-f', format, '-o', '-', '-q']
    _append_site_specific_ytdlp_args(cmd, url)

    if ffmpeg_dir:
        cmd.extend(['--ffmpeg-location', ffmpeg_dir])
    if js_runtime_arg:
        cmd.extend(['--js-runtimes', js_runtime_arg])
        # 啟用 EJS 挑戰解算元件，降低 YouTube 簽章失敗造成的中斷
        cmd.extend(['--remote-components', 'ejs:github'])

    resolved_cookies = _resolve_cookie_file(url, cookies)
    if resolved_cookies:
        cmd.extend(['--cookies', resolved_cookies])
    if proxy:
        cmd.extend(['--proxy', proxy])

    return cmd


def _resolve_ytdlp_command() -> list[str]:
    """解析可用的 yt-dlp 呼叫方式。

    優先順序：
    1) PATH 中的 yt-dlp / yt-dlp.exe
    2) 與目前 Python 同目錄下的 yt-dlp.exe（常見於 venv\\Scripts）
    3) 退回 `python -m yt_dlp`
    """
    ytdlp_exe = shutil.which('yt-dlp') or shutil.which('yt-dlp.exe')
    if ytdlp_exe:
        return [ytdlp_exe]

    py_dir = os.path.dirname(sys.executable)
    local_ytdlp_exe = os.path.join(py_dir, 'yt-dlp.exe')
    if os.path.exists(local_ytdlp_exe):
        return [local_ytdlp_exe]

    # fallback：即使 PATH 沒有 yt-dlp.exe，也可透過已安裝的 yt_dlp 模組執行
    return [sys.executable, '-m', 'yt_dlp']


def _resolve_ffmpeg_dir() -> str | None:
    """解析 ffmpeg 所在目錄，優先使用系統可見路徑，否則嘗試專案內建目錄。"""
    ffmpeg_exe = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
    if ffmpeg_exe:
        return os.path.dirname(ffmpeg_exe)

    # 某些 PATH 會錯誤地放入 ...\ffmpeg.exe（檔案）而不是資料夾，這裡容錯處理
    for raw in os.environ.get('PATH', '').split(';'):
        p = raw.strip().strip('"')
        if not p:
            continue
        if p.lower().endswith('ffmpeg.exe') and os.path.exists(p):
            return os.path.dirname(p)

    # 專案內常見位置：<repo>/ffmpeg-8.1-essentials_build/ffmpeg-8.1-essentials_build/bin
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / 'ffmpeg-8.1-essentials_build' / 'ffmpeg-8.1-essentials_build' / 'bin',
        repo_root / 'ffmpeg' / 'bin',
    ]
    for d in candidates:
        if (d / 'ffmpeg.exe').exists() or (d / 'ffmpeg').exists():
            return str(d)

    return None


def _resolve_js_runtime_arg() -> str | None:
    """解析可用的 yt-dlp JavaScript runtime 參數。"""
    node_exe = shutil.which('node') or shutil.which('node.exe')
    if node_exe:
        return f'node:{node_exe}'

    deno_exe = shutil.which('deno') or shutil.which('deno.exe')
    if deno_exe:
        return f'deno:{deno_exe}'

    return None


def _transport(ytdlp_proc, ffmpeg_proc):
    while (ytdlp_proc.poll() is None) and (ffmpeg_proc.poll() is None):
        try:
            chunk = ytdlp_proc.stdout.read(1024)
            if not chunk:
                break
            ffmpeg_proc.stdin.write(chunk)
        except (BrokenPipeError, OSError):
            break

    # 優雅結束：先關閉 ffmpeg stdin 讓其自行 flush/退出，再回收 ytdlp
    try:
        if ffmpeg_proc.stdin and not ffmpeg_proc.stdin.closed:
            ffmpeg_proc.stdin.close()
    except Exception:
        pass

    if ytdlp_proc.poll() is None:
        ytdlp_proc.terminate()
        try:
            ytdlp_proc.wait(timeout=2)
        except Exception:
            ytdlp_proc.kill()

    if ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.wait(timeout=2)
        except Exception:
            ffmpeg_proc.kill()


def _open_stream(url: str, format: str, cookies: str, proxy: str, cwd: str):
    ffmpeg_dir = _resolve_ffmpeg_dir()
    js_runtime_arg = _resolve_js_runtime_arg()

    cmd = _build_ytdlp_command(url,
                               format,
                               cookies,
                               proxy,
                               ffmpeg_dir=ffmpeg_dir,
                               js_runtime_arg=js_runtime_arg)

    env = os.environ.copy()
    if ffmpeg_dir:
        env['PATH'] = ffmpeg_dir + os.pathsep + env.get('PATH', '')

    try:
        ytdlp_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=cwd, env=env)
    except FileNotFoundError as e:
        raise RuntimeError(
            '無法啟動 yt-dlp。請確認已安裝 yt_dlp 套件，或可執行檔可由系統找到。'
        ) from e

    try:
        ffmpeg_cmd = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else 'ffmpeg'
        ffmpeg_process = (ffmpeg.input('pipe:', loglevel='panic').output('pipe:',
                                                                         format='f32le',
                                                                         acodec='pcm_f32le',
                                                                         ac=1,
                                                                         ar=SAMPLE_RATE).run_async(pipe_stdin=True,
                                                                                                  pipe_stdout=True,
                                                                                                  cmd=ffmpeg_cmd))
    except ffmpeg.Error as e:
        raise RuntimeError(f'Failed to load audio: {e.stderr.decode()}') from e

    thread = threading.Thread(target=_transport, args=(ytdlp_process, ffmpeg_process))
    thread.start()
    return ffmpeg_process, ytdlp_process


class StreamAudioGetter(LoopWorkerBase):

    def __init__(self, url: str, format: str, cookies: str, proxy: str, realtime_throttle: bool = False) -> None:
        self.url = url
        self.format = format
        self.cookies = cookies
        self.proxy = proxy
        self.realtime_throttle = realtime_throttle
        self.temp_dir = tempfile.mkdtemp()
        self.ffmpeg_process = None
        self.ytdlp_process = None
        self.byte_size = round(SAMPLES_PER_FRAME * 4)  # Factor 4 comes from float32 (4 bytes per sample)

    def __del__(self):
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _exit_handler(self, signum, frame):
        if self.ffmpeg_process:
            self.ffmpeg_process.kill()
        if self.ytdlp_process:
            self.ytdlp_process.kill()
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        sys.exit(0)

    def loop(self, output_queue: queue.SimpleQueue[np.array]):
        print(f'{INFO}Opening stream: {self.url}')
        self.ffmpeg_process, self.ytdlp_process = _open_stream(self.url, self.format, self.cookies, self.proxy,
                                                               self.temp_dir)
        frame_count = 0
        start_time = time.monotonic()
        while self.ffmpeg_process.poll() is None:
            in_bytes = self.ffmpeg_process.stdout.read(self.byte_size)
            if not in_bytes:
                break
            if len(in_bytes) != self.byte_size:
                continue
            audio = np.frombuffer(in_bytes, np.float32).flatten()
            if self.realtime_throttle:
                expected_time = frame_count * FRAME_DURATION
                elapsed = time.monotonic() - start_time
                sleep_time = expected_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
            frame_count += 1
            output_queue.put(audio)

        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.ffmpeg_process.terminate()
            try:
                self.ffmpeg_process.wait(timeout=2)
            except Exception:
                self.ffmpeg_process.kill()
        if self.ytdlp_process:
            if self.ytdlp_process.poll() is None:
                self.ytdlp_process.terminate()
                try:
                    self.ytdlp_process.wait(timeout=2)
                except Exception:
                    self.ytdlp_process.kill()
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        output_queue.put(None)


class LocalFileAudioGetter(LoopWorkerBase):

    def __init__(self, file_path: str, realtime_throttle: bool = False) -> None:
        self.file_path = file_path
        self.realtime_throttle = realtime_throttle
        self.ffmpeg_process = None
        self.byte_size = round(SAMPLES_PER_FRAME * 4)  # Factor 4 comes from float32 (4 bytes per sample)

    def _exit_handler(self, signum, frame):
        if self.ffmpeg_process:
            self.ffmpeg_process.kill()
        sys.exit(0)

    def loop(self, output_queue: queue.SimpleQueue[np.array]):
        print(f'{INFO}Opening local file: {self.file_path}')
        try:
            self.ffmpeg_process = (ffmpeg.input(self.file_path,
                                                loglevel='panic').output('pipe:',
                                                                         format='f32le',
                                                                         acodec='pcm_f32le',
                                                                         ac=1,
                                                                         ar=SAMPLE_RATE).run_async(pipe_stdin=True,
                                                                                                   pipe_stdout=True))
        except ffmpeg.Error as e:
            raise RuntimeError(f'Failed to load audio: {e.stderr.decode()}') from e

        frame_count = 0
        start_time = time.monotonic()
        while self.ffmpeg_process.poll() is None:
            in_bytes = self.ffmpeg_process.stdout.read(self.byte_size)
            if not in_bytes:
                break
            if len(in_bytes) != self.byte_size:
                continue
            audio = np.frombuffer(in_bytes, np.float32).flatten()
            if self.realtime_throttle:
                expected_time = frame_count * FRAME_DURATION
                elapsed = time.monotonic() - start_time
                sleep_time = expected_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
            frame_count += 1
            output_queue.put(audio)

        self.ffmpeg_process.kill()
        output_queue.put(None)


class DeviceAudioGetter(LoopWorkerBase):

    def __init__(self, device_index: int, recording_interval: float, use_loopback: bool = False) -> None:
        import sys
        from .common import INFO, WARNING
        
        self.use_loopback = use_loopback
        self.recording_interval = recording_interval
        self.remaining_audio = np.array([], dtype=np.float32)
        self.backend = 'sounddevice'  # 預設後端
        self.total_reads = 0
        
        # 嘗試使用 PyAudioWPatch loopback (僅 Windows)
        if use_loopback:
            if sys.platform != 'win32':
                print(f'{INFO}WASAPI loopback 僅支援 Windows，目前平台使用標準設備輸入。')
                self._init_sounddevice(device_index)
            else:
                try:
                    import pyaudiowpatch as pyaudio
                    self.backend = 'pyaudiowpatch'
                    self._init_pyaudiowpatch(device_index)
                    print(f'{INFO}✅ 使用 WASAPI Loopback 捕獲系統音頻：{self.device_name}')
                except ImportError:
                    print(f'{WARNING}⚠️ pyaudiowpatch 未安裝，請執行 "pip install pyaudiowpatch" 啟用 WASAPI loopback。回退到標準設備輸入。')
                    self._init_sounddevice(device_index)
                except Exception as e:
                    print(f'{WARNING}⚠️ PyAudioWPatch 初始化失敗：{e}。回退到標準設備輸入。')
                    self._init_sounddevice(device_index)
        else:
            self._init_sounddevice(device_index)
    
    def _init_sounddevice(self, device_index: int) -> None:
        """初始化 SoundDevice 後端"""
        import sounddevice as sd
        
        if not device_index:
            device_index = sd.default.device[0]
        else:
            sd.default.device[0] = device_index
        self.device_index = device_index
        self.device_name = sd.query_devices(device_index)['name']
        self.backend = 'sounddevice'
    
    def _init_pyaudiowpatch(self, device_index: int) -> None:
        """初始化 PyAudioWPatch 後端 (WASAPI Loopback)"""
        import pyaudiowpatch as pyaudio
        
        self.p = pyaudio.PyAudio()
        
        # 如果指定了 device_index，優先使用
        if device_index:
            device_info = self.p.get_device_info_by_index(device_index)
            self.device_index = device_index
            self.device_name = device_info['name']
        else:
            # 自動查找 loopback 設備
            loopback_device = self._find_loopback_device()
            if loopback_device:
                self.device_index = loopback_device['index']
                self.device_name = loopback_device['name']
            else:
                # 無法找到 loopback 設備，拋出錯誤
                raise RuntimeError(
                    f'{ERROR}無法找到 WASAPI loopback 設備！\n'
                    f'  請確認：\n'
                    f'  1. pyaudiowpatch 已正確安裝\n'
                    f'  2. 系統支援 WASAPI loopback\n'
                    f'  3. 至少有一個播放設備可用\n'
                    f'  提示：執行 "python 檢查loopback設備.py" 查看可用設備'
                )
    
    def _find_loopback_device(self):
        """查找 WASAPI loopback 設備（預設揚聲器的鏡像）"""
        import pyaudiowpatch as pyaudio
        
        try:
            # 獲取預設輸出設備（揚聲器）
            default_speakers = self.p.get_default_output_device_info()
            default_name = default_speakers.get('name', '')
            
            # 查找 WASAPI host API
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            
            # 第一輪：嘗試找到與預設揚聲器對應的 loopback
            for i in range(wasapi_info.get('deviceCount')):
                device = self.p.get_device_info_by_host_api_device_index(
                    wasapi_info.get('index'), i
                )
                
                # 必須是 loopback 設備
                if not device.get('isLoopbackDevice', False):
                    continue
                
                device_name = device.get('name', '')
                
                # 比對名稱：loopback 設備名稱可能包含 [Loopback] 後綴
                # 移除後綴後比對
                clean_name = device_name.replace(' [Loopback]', '').strip()
                
                # 檢查是否匹配（支援部分匹配，因為名稱可能被截斷）
                if (clean_name == default_name or 
                    clean_name in default_name or 
                    default_name in clean_name):
                    print(f'{INFO}找到預設播放設備的 loopback: {device_name}')
                    return device
            
            # 第二輪：如果沒找到匹配的，返回第一個 loopback 設備
            for i in range(wasapi_info.get('deviceCount')):
                device = self.p.get_device_info_by_host_api_device_index(
                    wasapi_info.get('index'), i
                )
                
                if device.get('isLoopbackDevice', False):
                    print(f'{WARNING}未找到預設播放設備的 loopback，使用第一個可用的: {device.get("name")}')
                    return device
                    
        except Exception as e:
            print(f'{ERROR}查找 loopback 設備時發生錯誤: {e}')
        
        return None

    def loop(self, output_queue: queue.SimpleQueue[np.array]):
        print(f'{INFO}Recording device: {self.device_name}')
        
        if self.backend == 'pyaudiowpatch':
            self._loop_pyaudiowpatch(output_queue)
        else:
            self._loop_sounddevice(output_queue)
    
    def _loop_sounddevice(self, output_queue: queue.SimpleQueue[np.array]):
        """SoundDevice 後端的錄音迴圈"""
        import sounddevice as sd

        def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
            if status:
                print(status)

            audio = np.concatenate([self.remaining_audio, indata.flatten().astype(np.float32)])
            num_samples = len(audio)
            num_chunks = num_samples // SAMPLES_PER_FRAME
            remaining_samples = num_samples % SAMPLES_PER_FRAME

            for i in range(num_chunks):
                chunk = audio[i * SAMPLES_PER_FRAME:(i + 1) * SAMPLES_PER_FRAME]
                output_queue.put(chunk)

            self.remaining_audio = audio[-remaining_samples:] if remaining_samples > 0 else np.array([],
                                                                                                     dtype=np.float32)

        with sd.InputStream(samplerate=SAMPLE_RATE,
                            blocksize=round(SAMPLE_RATE * self.recording_interval),
                            device=self.device_index,
                            channels=1,
                            dtype=np.float32,
                            callback=audio_callback):
            while True:
                time.sleep(5)
        output_queue.put(None)
    
    def _loop_pyaudiowpatch(self, output_queue: queue.SimpleQueue[np.array]):
        """PyAudioWPatch 後端的錄音迴圈（已優化）"""
        import pyaudiowpatch as pyaudio
        from math import gcd

        # ── 查詢設備規格 ────────────────────────────────────────────
        device_info = self.p.get_device_info_by_index(self.device_index)
        device_sample_rate = int(device_info.get('defaultSampleRate', SAMPLE_RATE))

        # WASAPI loopback 幾乎都是立體聲（2ch）
        # maxInputChannels 為 0 時改查 maxOutputChannels
        device_channels = int(device_info.get('maxInputChannels', 0))
        if device_channels == 0:
            device_channels = int(device_info.get('maxOutputChannels', 2))
        device_channels = max(1, device_channels)

        # ── 預先建立重採樣函式（只計算一次）────────────────────────
        needs_resampling = (device_sample_rate != SAMPLE_RATE)
        _do_resample = None
        if needs_resampling:
            g = gcd(device_sample_rate, SAMPLE_RATE)
            up   = SAMPLE_RATE      // g
            down = device_sample_rate // g
            try:
                from scipy.signal import resample_poly as _rp
                _do_resample = lambda a: _rp(a, up, down).astype(np.float32)
                print(f'{INFO}設備採樣率 {device_sample_rate}Hz ({device_channels}ch)，'
                      f'使用 scipy.signal.resample_poly ({up}/{down}) → {SAMPLE_RATE}Hz')
            except ImportError:
                _do_resample = None
                print(f'{INFO}設備採樣率 {device_sample_rate}Hz ({device_channels}ch)，'
                      f'使用線性插值重採樣（安裝 scipy 可顯著降低 CPU 占用）')
        else:
            print(f'{INFO}設備採樣率 {device_sample_rate}Hz ({device_channels}ch)，無需重採樣')

        frames_per_buffer = round(device_sample_rate * self.recording_interval)

        try:
            # 以設備實際聲道數開啟串流，避免驅動層隱式轉換帶來的額外開銷
            stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=device_channels,
                rate=device_sample_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=frames_per_buffer
            )

            while True:
                try:
                    # exception_on_overflow=False：略過溢出警告，避免 Python 例外開銷
                    data = stream.read(frames_per_buffer, exception_on_overflow=False)
                    self.total_reads += 1

                    audio = np.frombuffer(data, dtype=np.float32)

                    # 多聲道 → 單聲道（reshape + mean，比逐樣本迴圈快數倍）
                    if device_channels > 1:
                        audio = audio.reshape(-1, device_channels).mean(axis=1).astype(np.float32)

                    # 重採樣（scipy polyphase 對整數倍率遠比 np.interp 快）
                    if needs_resampling:
                        if _do_resample is not None:
                            audio = _do_resample(audio)
                        else:
                            target_length = int(len(audio) * SAMPLE_RATE / device_sample_rate)
                            audio = np.interp(
                                np.linspace(0, len(audio) - 1, target_length),
                                np.arange(len(audio)),
                                audio
                            ).astype(np.float32)

                    # 合併剩餘樣本（只在有剩餘時才 concatenate，避免無謂分配）
                    if len(self.remaining_audio) > 0:
                        audio = np.concatenate([self.remaining_audio, audio])

                    num_samples = len(audio)
                    num_chunks = num_samples // SAMPLES_PER_FRAME
                    remaining_samples = num_samples % SAMPLES_PER_FRAME

                    for i in range(num_chunks):
                        output_queue.put(audio[i * SAMPLES_PER_FRAME:(i + 1) * SAMPLES_PER_FRAME])

                    self.remaining_audio = (audio[-remaining_samples:] if remaining_samples > 0
                                            else np.array([], dtype=np.float32))

                except Exception as e:
                    print(f'{WARNING}讀取音頻資料時發生錯誤：{e}')
                    time.sleep(0.1)

        except Exception as e:
            print(f'{ERROR}PyAudioWPatch 串流錯誤：{e}')
        finally:
            if 'stream' in locals():
                stream.stop_stream()
                stream.close()
            self.p.terminate()
            output_queue.put(None)
