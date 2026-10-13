import importlib.util
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import ffmpeg
import numpy as np

from .common import AudioSourceQueue, AUDIO_STREAM_GAP, SAMPLE_RATE, SAMPLES_PER_FRAME, FRAME_DURATION, LoopWorkerBase, INFO, WARNING, ERROR, QueueBacklogMonitor


# Definite configuration failures; ambiguous extractor/decoder failures need repetition.
_STREAM_CONFIG_ERRORS = (
    (r'unsupported url|invalid url|not a valid url', '網址無效或不受支援', True),
    (r'no module named [\'"]?yt_dlp|ffmpeg.*(?:not found|not installed)', '缺少 yt-dlp 或 ffmpeg', True),
    (r'requested format.*not available', '要求的音訊格式無法使用', True),
    (r'(?:http(?: error)?|server returned)\s*(?:403|404)\b', '來源拒絕存取或不存在（403／404）', True),
    (r'this video is private|private video|members.only|sign in to confirm', '來源需要登入或會員權限', True),
    (r'cookies?.*(?:no such file|not found)', 'Cookies 檔案不存在', True),
    (r'unable to extract|invalid data found when processing input', '無法解析來源音訊', False),
)


def _capture_stream_stderr(process):
    process._stderr_tail = b''

    def drain():
        try:
            while True:
                chunk = process.stderr.read(1024)
                if not chunk:
                    break
                process._stderr_tail = (process._stderr_tail + chunk)[-8192:]
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=drain, daemon=True, name='stream-stderr')
    process._stderr_thread = thread
    thread.start()


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


def _is_youtube_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'} or hostname.endswith('.youtube.com')


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
    elif _is_youtube_url(url):
        # Live manifests occasionally return a transient missing fragment.  Let
        # yt-dlp keep following the manifest instead of silently ending after
        # the small batch of fragments that was initially available.
        cmd.extend([
            '--fragment-retries', 'infinite',
            '--retry-sleep', 'fragment:1',
        ])


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
    1) 目前 Python 環境中已安裝的 yt_dlp 模組
    2) 目前 Python 環境旁的 yt-dlp.exe
    3) PATH 中的 yt-dlp / yt-dlp.exe

    打包版必須優先使用 runtime 內已驗證的版本，避免被使用者電腦
    PATH 中較舊的全域 yt-dlp.exe 覆蓋。
    """
    if importlib.util.find_spec('yt_dlp') is not None:
        return [sys.executable, '-m', 'yt_dlp']

    py_dir = os.path.dirname(sys.executable)
    local_candidates = (
        os.path.join(py_dir, 'yt-dlp.exe'),
        os.path.join(py_dir, 'Scripts', 'yt-dlp.exe'),
    )
    for local_ytdlp_exe in local_candidates:
        if os.path.exists(local_ytdlp_exe):
            return [local_ytdlp_exe]

    ytdlp_exe = shutil.which('yt-dlp') or shutil.which('yt-dlp.exe')
    if ytdlp_exe:
        return [ytdlp_exe]

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


@lru_cache(maxsize=1)
def _resolve_js_runtime_arg() -> str | None:
    """解析 yt-dlp JavaScript runtime，包含 UI 啟動時可能遺失的 Windows PATH。"""
    executable_dir = Path(sys.executable).resolve().parent
    app_root = Path(__file__).resolve().parents[2]
    program_files = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
    local_app_data = Path(os.environ.get('LOCALAPPDATA', '')) if os.environ.get('LOCALAPPDATA') else None

    node_candidates = [
        # Release-bundled Node is verified with yt-dlp; a user's older PATH
        # installation must not override it.
        executable_dir / '_js_runtime' / 'node.exe',
        executable_dir.parent / '_js_runtime' / 'node.exe',
        executable_dir / 'node.exe',
        executable_dir.parent / 'node.exe',
        app_root / 'node' / 'node.exe',
        app_root / 'runtime' / 'node.exe',
        shutil.which('node'),
        shutil.which('node.exe'),
        program_files / 'nodejs' / 'node.exe',
        local_app_data / 'Programs' / 'nodejs' / 'node.exe' if local_app_data else None,
    ]
    deno_candidates = [
        shutil.which('deno'),
        shutil.which('deno.exe'),
        executable_dir / 'deno.exe',
        executable_dir.parent / 'deno.exe',
        app_root / 'deno' / 'deno.exe',
        local_app_data / 'deno' / 'bin' / 'deno.exe' if local_app_data else None,
    ]

    for runtime, candidates in (('node', node_candidates), ('deno', deno_candidates)):
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.is_file():
                resolved = str(path.resolve())
                print(f'{INFO}yt-dlp JavaScript runtime: {runtime} ({resolved})')
                return f'{runtime}:{resolved}'

    print(f'{WARNING}找不到 yt-dlp 支援的 JavaScript runtime；YouTube 可用格式可能不完整。')
    return None


def _transport(ytdlp_proc, ffmpeg_proc):
    while ffmpeg_proc.poll() is None:
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
    if js_runtime_arg and ':' in js_runtime_arg:
        runtime_path = js_runtime_arg.split(':', 1)[1]
        runtime_dir = str(Path(runtime_path).parent)
        env['PATH'] = runtime_dir + os.pathsep + env.get('PATH', '')

    try:
        ytdlp_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            '無法啟動 yt-dlp。請確認已安裝 yt_dlp 套件，或可執行檔可由系統找到。'
        ) from e

    _capture_stream_stderr(ytdlp_process)

    try:
        ffmpeg_cmd = os.path.join(ffmpeg_dir, 'ffmpeg.exe') if ffmpeg_dir else 'ffmpeg'
        ffmpeg_process = (ffmpeg.input('pipe:', loglevel='error').output('pipe:',
                                                                         format='f32le',
                                                                         acodec='pcm_f32le',
                                                                         ac=1,
                                                                         ar=SAMPLE_RATE).run_async(pipe_stdin=True,
                                                                                                  pipe_stdout=True,
                                                                                                  pipe_stderr=True,
                                                                                                  cmd=ffmpeg_cmd))
    except ffmpeg.Error as exc:
        StreamAudioGetter._stop_process(ytdlp_process)
        raise RuntimeError('ffmpeg 無法啟動') from exc
    except OSError:
        StreamAudioGetter._stop_process(ytdlp_process)
        raise

    _capture_stream_stderr(ffmpeg_process)

    thread = threading.Thread(
        target=_transport,
        args=(ytdlp_process, ffmpeg_process),
        daemon=True,
        name='stream-transport',
    )
    thread.start()
    ffmpeg_process._transport_thread = thread
    return ffmpeg_process, ytdlp_process


class StreamAudioGetter(LoopWorkerBase):

    STREAM_READ_TIMEOUT_SECONDS = 8.0
    YOUTUBE_RECONNECT_DELAY_SECONDS = 1.0
    MAX_UNKNOWN_EOF_CHECKS = 3
    MAX_UNKNOWN_EOF_SECONDS = 10 * 60.0

    def _source_status(self):
        """Return live, finite, ended, or unknown; transport EOF is not proof."""
        self._metadata_answered = False
        try:
            cmd = _build_ytdlp_command(
                self.url, self.format, self.cookies, self.proxy,
                ffmpeg_dir=_resolve_ffmpeg_dir(), js_runtime_arg=_resolve_js_runtime_arg())
            cmd.extend(['--skip-download', '--dump-single-json', '--no-playlist'])
            # Metadata is bounded and must not inherit infinite fragment retries.
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', timeout=15)
            if result.returncode:
                self._check_stream_error(getattr(result, 'stderr', ''))
                return 'unknown'
            info = json.loads(result.stdout)
        except FileNotFoundError as exc:
            self._check_stream_error('', exc)
            raise
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self._check_stream_error('')
            return 'unknown'
        if not isinstance(info, dict):
            return 'unknown'
        self._metadata_answered = True
        status = info.get('live_status')
        if status in ('post_live', 'was_live'):
            return 'ended'
        if info.get('is_live') or status in ('is_live', 'is_upcoming'):
            return 'live'
        if status == 'not_live' or info.get('is_live') is False:
            return 'finite'
        return 'unknown'

    def __init__(self, url: str, format: str, cookies: str, proxy: str, realtime_throttle: bool = False) -> None:
        self.url = url
        self.format = format
        self.cookies = cookies
        self.proxy = proxy
        self.realtime_throttle = realtime_throttle
        self.temp_dir = tempfile.mkdtemp()
        self.ffmpeg_process = None
        self.ytdlp_process = None
        self._reader_thread = None
        self._stop_event = threading.Event()
        self.byte_size = round(SAMPLES_PER_FRAME * 4)  # Factor 4 comes from float32 (4 bytes per sample)
        self.running = True
        self._received_audio = False
        self._metadata_answered = False
        self._startup_error = None
        self._startup_failures = 0

    def _check_stream_error(self, text, exc=None):
        reason = None
        permanent = False
        if isinstance(exc, FileNotFoundError):
            reason, permanent = '缺少 yt-dlp 或 ffmpeg 執行檔', True
        else:
            for pattern, label, definite in _STREAM_CONFIG_ERRORS:
                if re.search(pattern, text, re.IGNORECASE):
                    reason, permanent = label, definite
                    break
        if reason and not permanent and not self._received_audio:
            signature = text.strip()
            self._startup_failures = self._startup_failures + 1 if signature == self._startup_error else 1
            self._startup_error = signature
            permanent = self._startup_failures >= 5
        elif not reason:
            self._startup_error = None
            self._startup_failures = 0
        # A live source that already delivered audio keeps reconnecting until
        # the user stops it; expired fragment URLs (403) are routine there.
        if permanent and not self._received_audio:
            # Never echo raw stderr: URLs, cookies and headers can contain credentials.
            message = f'串流設定錯誤，無法開啟來源：{reason}'
            print(f'{ERROR}{message}', flush=True)
            raise RuntimeError(message) from exc

    @staticmethod
    def _stop_process(process) -> None:
        if not process or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass

    def _close_stream(self) -> None:
        ffmpeg_process = self.ffmpeg_process
        ytdlp_process = self.ytdlp_process
        reader_thread = self._reader_thread
        transport_thread = getattr(ffmpeg_process, '_transport_thread', None) if ffmpeg_process else None
        self._stop_process(ffmpeg_process)
        self._stop_process(ytdlp_process)
        current_thread = threading.current_thread()
        for thread in (reader_thread, transport_thread,
                       getattr(ffmpeg_process, '_stderr_thread', None),
                       getattr(ytdlp_process, '_stderr_thread', None)):
            if thread and thread is not current_thread and thread.is_alive():
                thread.join(timeout=2)
        self.ffmpeg_process = None
        self.ytdlp_process = None
        self._reader_thread = None

    def _read_stream_frames(self):
        """Yield PCM frames without allowing a live pipe read to block forever."""
        process = self.ffmpeg_process
        read_queue = queue.SimpleQueue()
        backlog = QueueBacklogMonitor(read_queue, 'stream reader -> audio getter')
        finished = object()

        def reader():
            try:
                while self.running and process:
                    chunk = process.stdout.read(self.byte_size)
                    if not chunk:
                        break
                    read_queue.put(chunk)
                    backlog.check()
            finally:
                read_queue.put(finished)

        self._reader_thread = threading.Thread(target=reader, daemon=True, name='stream-audio-reader')
        self._reader_thread.start()
        while self.running:
            try:
                chunk = read_queue.get(timeout=self.STREAM_READ_TIMEOUT_SECONDS)
            except queue.Empty as exc:
                raise TimeoutError(
                    f'串流已連續 {self.STREAM_READ_TIMEOUT_SECONDS:g} 秒沒有音訊資料'
                ) from exc
            backlog.check()
            if chunk is finished:
                return
            if len(chunk) == self.byte_size:
                yield chunk

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        self._close_stream()

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
        frame_count = 0
        start_time = time.monotonic()
        source_status = self._source_status()
        confirmed_live = source_status == 'live'
        gap_started_at = None
        last_frame_received_at = None
        while self.running:
            print(f'{INFO}Opening stream: {self.url}')
            stalled = False
            stream_failed = False
            failure = None
            processes = ()
            try:
                self.ffmpeg_process, self.ytdlp_process = _open_stream(
                    self.url, self.format, self.cookies, self.proxy, self.temp_dir
                )
                processes = (self.ffmpeg_process, self.ytdlp_process)
                for in_bytes in self._read_stream_frames():
                    if not self.running:
                        break
                    frame_received_at = time.monotonic()
                    audio = np.frombuffer(in_bytes, np.float32).flatten()
                    if self.realtime_throttle:
                        expected_time = frame_count * FRAME_DURATION
                        elapsed = time.monotonic() - start_time
                        sleep_time = expected_time - elapsed
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                    frame_count += 1
                    self._received_audio = True
                    self._startup_error = None
                    self._startup_failures = 0
                    missing = 0.0
                    if gap_started_at is not None:
                        if confirmed_live:
                            # Include the stalled read, not just reconnect work.
                            # Only the resumed frame adds media since the last receipt.
                            missing = max(0.0, frame_received_at - gap_started_at
                                          - len(audio) / SAMPLE_RATE)
                        gap_started_at = None
                    if isinstance(output_queue, AudioSourceQueue):
                        output_queue.put(audio, timeline_advance=missing)
                    else:
                        output_queue.put(audio)
                    last_frame_received_at = frame_received_at
                if self.running:
                    # Flush the last speech before cleanup or slow metadata queries.
                    if gap_started_at is None:
                        gap_started_at = (last_frame_received_at if last_frame_received_at is not None
                                          else time.monotonic())
                    output_queue.put(AUDIO_STREAM_GAP)
                stream_failed = any(
                    process and process.poll() not in (None, 0)
                    for process in (self.ffmpeg_process, self.ytdlp_process)
                )
            except TimeoutError as exc:
                stalled = True
                print(f'{WARNING}{exc}')
                # Flush speech collected before the transport gap now. Without
                # this marker AudioSlicer can only discover the boundary when
                # the first post-reconnect frame arrives.
                if gap_started_at is None:
                    gap_started_at = (last_frame_received_at if last_frame_received_at is not None
                                      else time.monotonic())
                output_queue.put(AUDIO_STREAM_GAP)
            except (OSError, RuntimeError) as exc:
                failure = exc
                if self.running:
                    if gap_started_at is None:
                        gap_started_at = (last_frame_received_at if last_frame_received_at is not None
                                          else time.monotonic())
                    output_queue.put(AUDIO_STREAM_GAP)
            finally:
                self._close_stream()

            if self.running:
                stderr = '\n'.join(getattr(process, '_stderr_tail', b'').decode('utf-8', errors='replace')
                                   for process in processes)
                self._check_stream_error((str(failure) if failure else '') + '\n' + stderr, failure)
                if failure is not None:
                    if source_status in ('finite', 'ended'):
                        raise failure
                    print(f'{WARNING}串流連線失敗，稍後重試：{failure}')

            if self.running and source_status in ('finite', 'ended') and (stalled or stream_failed):
                raise RuntimeError('有限音訊來源讀取失敗；未確認正常結束，無法安全從頭重播。')
            if not self.running or source_status in ('finite', 'ended'):
                break
            # Remember live confirmation across outages. For a possible VOD,
            # only successful metadata answers without a live flag count as EOF
            # evidence; failed requests must remain retryable.
            unknown_checks = 0
            unknown_started_at = None
            while self.running:
                source_status = self._source_status()
                confirmed_live = confirmed_live or source_status == 'live'
                if source_status != 'unknown' or confirmed_live:
                    break
                # Bound failed metadata requests too, but only for never-live sources.
                now = time.monotonic()
                if unknown_started_at is None:
                    unknown_started_at = now
                if now - unknown_started_at >= self.MAX_UNKNOWN_EOF_SECONDS:
                    print(f'{ERROR}Source status could not be confirmed after EOF/stall; '
                          'stopping after the metadata wait limit (source was never confirmed live).',
                          flush=True)
                    source_status = 'ended'
                    break
                if self._metadata_answered:
                    unknown_checks += 1
                else:
                    unknown_checks = 0
                if unknown_checks >= self.MAX_UNKNOWN_EOF_CHECKS:
                    print(f'{WARNING}Ending source after EOF/stall: '
                          f'{unknown_checks} successful metadata checks returned no live flag; '
                          'source was never confirmed live.', flush=True)
                    source_status = 'ended'
                    break
                print(f'{WARNING}無法確認來源狀態，等待後重新確認…')
                if self._stop_event.wait(self.YOUTUBE_RECONNECT_DELAY_SECONDS):
                    break
            if not self.running:
                break
            if source_status in ('finite', 'ended'):
                break
            print(f'{WARNING}來源尚未確認結束，正在重新連線…')
            if self._stop_event.wait(self.YOUTUBE_RECONNECT_DELAY_SECONDS):
                break

        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        output_queue.put(None)


class LocalFileAudioGetter(LoopWorkerBase):

    def __init__(self, file_path: str, realtime_throttle: bool = False) -> None:
        self.file_path = file_path
        self.realtime_throttle = realtime_throttle
        self.ffmpeg_process = None
        self.byte_size = round(SAMPLES_PER_FRAME * 4)  # Factor 4 comes from float32 (4 bytes per sample)
        self.running = True

    def stop(self) -> None:
        self.running = False
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                self.ffmpeg_process.terminate()
            except Exception:
                pass

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
        while self.running and self.ffmpeg_process.poll() is None:
            in_bytes = self.ffmpeg_process.stdout.read(self.byte_size)
            if not self.running or not in_bytes:
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

    MAX_DEVICE_FAILURES = 5
    DEVICE_RETRY_DELAY_SECONDS = 0.25
    DEVICE_MAX_RETRY_DELAY_SECONDS = 2.0
    DEVICE_POLL_SECONDS = 0.05
    DEVICE_RECOVERY_SECONDS = 1.0

    def __init__(self, device_index: int, recording_interval: float, use_loopback: bool = False) -> None:
        import sys
        from .common import INFO, WARNING
        
        self.use_loopback = use_loopback
        self.recording_interval = recording_interval
        self.remaining_audio = np.array([], dtype=np.float32)
        self.backend = 'sounddevice'  # 預設後端
        self.total_reads = 0
        self.running = True
        self._stop_event = threading.Event()
        
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

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
    
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
        
        failures = 0
        try:
            while self.running:
                self._capture_seconds = 0.0
                try:
                    if self.backend == 'pyaudiowpatch':
                        self._loop_pyaudiowpatch(output_queue)
                    else:
                        self._loop_sounddevice(output_queue)
                    break
                except Exception as exc:
                    if not self.running:
                        break
                    if self._capture_seconds >= self.DEVICE_RECOVERY_SECONDS:
                        failures = 0
                    failures += 1
                    if failures >= self.MAX_DEVICE_FAILURES:
                        message = 'Audio device unavailable after repeated capture failures'
                        print(f'{ERROR}{message}', flush=True)
                        raise RuntimeError(message) from exc
                    print(f'{WARNING}Audio device capture failed; retrying', flush=True)
                    self.remaining_audio = np.array([], dtype=np.float32)
                    output_queue.put(AUDIO_STREAM_GAP)
                    delay = min(self.DEVICE_RETRY_DELAY_SECONDS * 2 ** (failures - 1),
                                self.DEVICE_MAX_RETRY_DELAY_SECONDS)
                    if self._stop_event.wait(delay):
                        break
        finally:
            self.running = False
            self._stop_event.set()
            if self.backend == 'pyaudiowpatch':
                self.p.terminate()
        output_queue.put(None)
    
    def _loop_sounddevice(self, output_queue: queue.SimpleQueue[np.array]):
        """SoundDevice 後端的錄音迴圈"""
        import sounddevice as sd

        def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
            if not self.running:
                return
            if status:
                print(status)

            self._capture_seconds += len(indata) / SAMPLE_RATE
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
                            callback=audio_callback) as stream:
            while self.running:
                if self._stop_event.wait(self.DEVICE_POLL_SECONDS):
                    break
                if not stream.active:
                    raise RuntimeError('Audio input stream became inactive')
    
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

        frames_per_buffer = max(1, round(device_sample_rate * self.recording_interval))
        native_audio = np.array([], dtype=np.float32)
        if needs_resampling:
            # Fixed ratio-aligned blocks decouple filtering from device read sizes.
            resample_block = max(1, round(device_sample_rate * FRAME_DURATION / down)) * down

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

            while self.running:
                try:
                    # Only read frames already available. A blocking read for the
                    # recording interval cannot otherwise be interrupted by stop().
                    available = stream.get_read_available()
                    if available <= 0:
                        if not stream.is_active():
                            raise RuntimeError('Loopback input stream became inactive')
                        if self._stop_event.wait(self.DEVICE_POLL_SECONDS):
                            break
                        continue
                    # exception_on_overflow=False：略過溢出警告，避免 Python 例外開銷
                    data = stream.read(min(frames_per_buffer, available), exception_on_overflow=False)
                    if not self.running:
                        break
                    self.total_reads += 1

                    audio = np.frombuffer(data, dtype=np.float32)

                    # 多聲道 → 單聲道（reshape + mean，比逐樣本迴圈快數倍）
                    if device_channels > 1:
                        audio = audio.reshape(-1, device_channels).mean(axis=1).astype(np.float32)

                    # 重採樣（scipy polyphase 對整數倍率遠比 np.interp 快）
                    self._capture_seconds += len(audio) / device_sample_rate
                    if needs_resampling:
                        native_audio = np.concatenate([native_audio, audio])
                        whole_samples = len(native_audio) // resample_block * resample_block
                        if not whole_samples:
                            continue
                        blocks = native_audio[:whole_samples].reshape(-1, resample_block)
                        native_audio = native_audio[whole_samples:].copy()
                        if _do_resample is not None:
                            audio = np.concatenate([_do_resample(block) for block in blocks])
                        else:
                            target_length = resample_block // down * up
                            positions = np.arange(target_length) * down / up
                            audio = np.concatenate([
                                np.interp(positions, np.arange(resample_block), block)
                                for block in blocks
                            ]).astype(np.float32)

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

                except Exception:
                    if not self.running:
                        break
                    raise

        finally:
            # On stop, retain the final ratio-aligned tail too. During capture it
            # stays buffered so read boundaries never become filter boundaries.
            if needs_resampling and not self.running and len(native_audio):
                count = len(native_audio) // down * down
                if count:
                    tail = native_audio[:count]
                    if _do_resample is not None:
                        tail = _do_resample(tail)
                    else:
                        tail = np.interp(np.arange(count // down * up) * down / up,
                                         np.arange(count), tail).astype(np.float32)
                    audio = np.concatenate([self.remaining_audio, tail])
                    complete = len(audio) // SAMPLES_PER_FRAME * SAMPLES_PER_FRAME
                    for offset in range(0, complete, SAMPLES_PER_FRAME):
                        output_queue.put(audio[offset:offset + SAMPLES_PER_FRAME])
                    self.remaining_audio = audio[complete:].copy()
            if 'stream' in locals():
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
