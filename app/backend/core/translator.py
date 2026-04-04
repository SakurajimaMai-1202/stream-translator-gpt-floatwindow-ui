"""
核心翻譯管理器
負責管理 subprocess 執行與 SSE 事件流
"""

import asyncio
import subprocess
import threading
import sys
import os
import re
import json
import uuid
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from pathlib import Path
from backend.config import settings

logger = logging.getLogger(__name__)
# 設定日誌級別為 DEBUG 以便調試
logger.setLevel(logging.DEBUG)

class TranslationContext:
    """翻譯執行上下文"""
    
    def __init__(self, config: Dict[str, Any], task_id: str):
        self.config = config
        self.task_id = task_id
        self.process = None
        self.running = False
        self.stop_requested = False
        self._subscribers: set = set()  # 每個 SSE 連線各有自己的 Queue
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_timestamp = None
        
    async def start(self):
        """啟動翻譯任務"""
        if self.running:
            return
            
        self.running = True
        self.stop_requested = False
        self._loop = asyncio.get_running_loop()
        
        # 啟動後台處理任務
        asyncio.create_task(self._process_loop())

    def _subscribe(self) -> asyncio.Queue:
        """建立並返回此連線專屬的 Queue"""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        logger.info(f"[Task {self.task_id}] 新訂閱者加入，目前共 {len(self._subscribers)} 個")
        return q

    def _unsubscribe(self, q: asyncio.Queue):
        """移除此連線的 Queue"""
        self._subscribers.discard(q)
        logger.info(f"[Task {self.task_id}] 訂閱者離開，目前共 {len(self._subscribers)} 個")

    def _broadcast(self, event: dict):
        """將事件廣播給所有訂閱者（從任意執行緒呼叫）"""
        if not self._subscribers:
            return
        loop = self._loop
        if loop is None:
            return
        for q in list(self._subscribers):
            try:
                asyncio.run_coroutine_threadsafe(q.put(event), loop)
            except Exception as e:
                logger.warning(f"廣播給訂閱者失敗: {e}")
    
    def _build_command(self) -> List[str]:
        """構建 subprocess 命令行參數"""
        # 檢查是否在打包環境中
        is_frozen = getattr(sys, 'frozen', False)
        
        if is_frozen:
            # 打包環境：直接使用 Python，因為 stream_translator_gpt 已包含在 exe 中
            # 我們需要找到原始的 stream-translator-gpt 安裝
            base_dir = Path(sys.executable).parent
            # 在打包環境中，使用系統 Python 或 venv Python
            python_exe = None
            
            # 嘗試多個可能的 Python 路徑
            possible_pythons = [
                base_dir / '_runtime' / 'python.exe',  # 優先：打包的可攜式 Python 環境
                base_dir.parent.parent / 'venv' / 'Scripts' / 'python.exe',  # ui2/venv
                base_dir.parent.parent / 'stream-translator-gpt' / 'venv' / 'Scripts' / 'python.exe',
                Path(sys.executable).parent / 'python.exe',  # 打包目錄中的 python
            ]
            
            # 添加系統 Python
            import shutil
            system_python = shutil.which('python')
            if system_python:
                possible_pythons.append(Path(system_python))
            
            for py_path in possible_pythons:
                if py_path.exists():
                    python_exe = str(py_path)
                    label = "_runtime (bundled)" if py_path.name == "python.exe" and "_runtime" in str(py_path) else str(py_path)
                    logger.info(f"Found Python at: {python_exe} [{label}]")
                    break
            
            if not python_exe:
                # 最後嘗試：使用系統 python 命令
                python_exe = 'python'
                logger.warning("No Python executable found, using 'python' command")
            
            cmd = [python_exe, '-m', 'stream_translator_gpt']
        else:
            # 開發環境：使用當前 Python 解釋器
            cmd = [sys.executable, '-m', 'stream_translator_gpt']

        allowed_args = {
            'proxy', 'openai_api_key', 'google_api_key', 'format', 'list_format', 'cookies',
            'input_proxy', 'device_index', 'list_devices', 'device_recording_interval',
            'min_audio_length', 'max_audio_length', 'target_audio_length',
            'continuous_no_speech_threshold', 'disable_dynamic_no_speech_threshold',
            'prefix_retention_length', 'vad_threshold', 'disable_dynamic_vad_threshold',
            'vad_every_n_frames', 'realtime_processing',
            'model', 'language', 'use_faster_whisper', 'use_simul_streaming',
            'use_openai_transcription_api', 'use_qwen3_asr', 'openai_transcription_model', 'whisper_filters',
            'transcription_initial_prompt', 'disable_transcription_context', 'qwen3_context',
            'qwen3_load_in_4bit', 'qwen3_dtype',
            'gpt_model', 'gemini_model', 'translation_prompt', 'translation_glossary', 'translation_history_size',
            'translation_timeout', 'gpt_base_url', 'gemini_base_url', 'processing_proxy',
            'use_json_result', 'retry_if_translation_fails', 'output_timestamps',
            'hide_transcribe_result', 'output_proxy', 'output_file_path', 'cqhttp_url',
            'cqhttp_token', 'discord_webhook_url', 'telegram_token', 'telegram_chat_id'
        }
        
        # 複製配置以避免修改原始字典
        config_copy = self.config.copy()
        url = config_copy.pop('url', '')
        
        # 添加所有配置參數
        for key, value in sorted(config_copy.items()):
            if key not in allowed_args:
                logger.warning(f"Skipping unsupported CLI arg: {key}")
                continue
            # 跳過空值
            if value is None or value == '' or value == [] or value == 0:
                continue
            
            # 特殊處理：如果是數字 0 但不是布爾值，則跳過（例如 chat_id=0）
            if isinstance(value, (int, float)) and value == 0 and not isinstance(value, bool):
                continue
            
            # Convert arg name
            arg_name = f'--{key}'
            
            # Boolean handling
            if isinstance(value, bool):
                if value:
                    cmd.append(arg_name)
            # List handling
            elif isinstance(value, list):
                if value:  # 非空列表
                    cmd.extend([arg_name, ','.join(str(v) for v in value)])
            # Normal value
            else:
                str_value = str(value).strip()  # 移除前後空格
                # 跳過空字串
                if str_value:
                    cmd.extend([arg_name, str_value])
        
        # URL as positional arg (last)
        if url:
            cmd.append(url)
            
        return cmd

    async def _process_loop(self):
        """主處理循環：啟動進程並讀取輸出（使用 threading 避免 Windows asyncio 問題）"""
        try:
            cmd = self._build_command()
            
            # 安全的命令日誌輸出 - 避免編碼錯誤
            try:
                logger.info(f"Starting translation process")
                logger.debug(f"Command has {len(cmd)} arguments")
                safe_args = []
                for i, arg in enumerate(cmd):
                    try:
                        if arg.startswith('--'):
                            safe_args.append(arg)
                        elif arg.encode('ascii', errors='ignore').decode('ascii') == arg:
                            safe_args.append(arg)
                        else:
                            safe_args.append('<contains-unicode>')
                    except:
                        safe_args.append('<encoding-error>')
                logger.debug(f"Args: {' '.join(safe_args[:20])}...")
            except Exception as log_err:
                logger.warning(f"Failed to log command: {log_err}")
            
            # 計算工作目錄 (floatwindow root)
            cwd = settings.BASE_DIR.parent
            
            # 設定環境變數
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            env['PYTHONUNBUFFERED'] = '1'

            # 注入打包的 ffmpeg 到 PATH（確保子程序能找到 ffmpeg.exe）
            if getattr(sys, 'frozen', False):
                _base_dir = Path(sys.executable).parent
                _ffmpeg_bin = _base_dir / 'ffmpeg' / 'bin'
                if _ffmpeg_bin.exists():
                    env['PATH'] = str(_ffmpeg_bin) + os.pathsep + env.get('PATH', '')
                    logger.info(f"Injected ffmpeg PATH: {_ffmpeg_bin}")
            
            # 使用同步 subprocess.Popen (避免 Windows asyncio subprocess 問題)
            logger.info(f"Creating subprocess with {len(cmd)} arguments")
            logger.info(f"Working directory: {cwd}")
            
            # 記錄完整命令以便調試
            try:
                import json
                logger.info(f"Full command args: {json.dumps(cmd, ensure_ascii=False)}")
            except:
                logger.info(f"Full command (fallback): {cmd}")
            
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,  # 分開捕獲 stderr
                    cwd=str(cwd),
                    env=env,
                    bufsize=1,  # 行緩衝
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                logger.info(f"Subprocess created successfully, PID: {self.process.pid}")
            except FileNotFoundError as e:
                logger.error(f"Failed to create subprocess - File not found: {e}")
                raise
            except Exception as e:
                import traceback
                logger.error(f"Failed to create subprocess: {type(e).__name__}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            self._broadcast({
                "type": "status", 
                "data": {"status": "running", "pid": self.process.pid}
            })
            logger.info(f"Status event broadcast: running (PID: {self.process.pid})")
            
            # 獲取當前 event loop 已在 start() 中儲存
            loop = self._loop
            
            # 讀取 stderr 的線程
            def read_stderr():
                log_path = Path(settings.BASE_DIR) / "backend" / "translator_stderr.log"
                try:
                    for line in self.process.stderr:
                        line = line.strip()
                        if line:
                            logger.error(f"[STDERR] {line}")
                            try:
                                with open(log_path, "a", encoding="utf-8") as f:
                                    f.write(line + "\n")
                            except Exception as file_err:
                                logger.error(f"Stderr log write error: {file_err}")
                except Exception as e:
                    logger.error(f"Stderr read error: {e}")
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            # 使用線程讀取 stdout(避免阻塞 event loop)
            def read_output():
                import time
                pending_subtitles = {}  # timestamp -> dict
                hide_transcribe_result = self.config.get('output_notification', {}).get('hide_transcribe_result', False)
                try:
                    for line in self.process.stdout:
                        if self.stop_requested:
                            break
                        
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 檢查是否為翻譯行 (result_exporter.py 會加上 \x1b[1m BOLD)
                        is_translation = '\033[1m' in line or '\x1b[1m' in line
                        
                        # 移除 ANSI 顏色碼
                        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                        
                        # 過濾日誌行
                        if any(marker in clean_line for marker in ['[INFO]', '[ERROR]', '[WARNING]', '[DEBUG]']):
                            continue

                        # 將實際輸出寫入後端終端,方便確認有無輸出
                        logger.info(f"[STDOUT] {clean_line}")
                        
                        # 檢查是否包含時間戳
                        timestamp_match = re.search(
                            r'(\d{1,2}:\d{2}:\d{2},\d+)\s*-->\s*(\d{1,2}:\d{2}:\d{2},\d+)', 
                            clean_line
                        )
                        
                        if timestamp_match:
                            timestamp = f"{timestamp_match.group(1)} -> {timestamp_match.group(2)}"
                            remaining_text = clean_line[timestamp_match.end():].strip()
                            
                            # 初始化該時間戳的字典
                            if timestamp not in pending_subtitles:
                                pending_subtitles[timestamp] = {
                                    "original": "",
                                    "translated": "",
                                    "created_at": time.time()
                                }
                            
                            if is_translation or hide_transcribe_result:
                                pending_subtitles[timestamp]["translated"] = remaining_text
                            else:
                                pending_subtitles[timestamp]["original"] = remaining_text
                            
                            # 即時發送給前端 (包含原文與翻譯現況)
                            data = {
                                "timestamp": timestamp,
                                "original": pending_subtitles[timestamp]["original"],
                                "translated": pending_subtitles[timestamp]["translated"]
                            }
                            logger.info(f"[Subtitle] Emit: {data}")
                            self._broadcast({"type": "subtitle", "data": data})
                        else:
                            # 沒有時間戳的行（罕見，fallback 處理）
                            if clean_line:
                                logger.info(f"[Buffer] 純文本(無時間戳): '{clean_line}'")
                                data = {
                                    "timestamp": "",
                                    "original": "" if hide_transcribe_result else clean_line,
                                    "translated": clean_line if hide_transcribe_result else ""
                                }
                                self._broadcast({"type": "subtitle", "data": data})
                        
                        # 清理超過 30 秒的舊緩存，避免記憶體洩漏
                        current_time = time.time()
                        for ts in list(pending_subtitles.keys()):
                            if current_time - pending_subtitles[ts]["created_at"] > 30:
                                del pending_subtitles[ts]
                                
                except Exception as e:
                    logger.error(f"Read thread error: {e}")
            
            # 啟動讀取線程
            read_thread = threading.Thread(target=read_output, daemon=True)
            read_thread.start()
            
            # 等待進程結束（在背景）
            def wait_process():
                return_code = self.process.wait()
                logger.info(f"Process exited with code: {return_code}")
                status = "completed" if return_code == 0 else "error"
                self._broadcast({
                    "type": "status",
                    "data": {"status": status, "code": return_code}
                })
                self.running = False
            
            wait_thread = threading.Thread(target=wait_process, daemon=True)
            wait_thread.start()
            
        except Exception as e:
            import traceback
            logger.error(f"Process error: {type(e).__name__}: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            self._broadcast({
                "type": "error",
                "data": {"message": f"{type(e).__name__}: {e}"}
            })
            self.running = False

    async def _process_subtitle_buffer(self, buffer: List[dict]):
        """處理字幕緩存
        
        buffer 格式:
        [
            {'timestamp': '00:00:01,200 -> 00:00:03,500', 'text': '可選的同行文本'},
            {'text': '原文或翻譯'},
            {'text': '翻譯(如果有兩行)'}
        ]
        """
        if not buffer:
            return
        
        logger.debug(f"[Buffer] Processing: {buffer}")
        
        # 提取時間戳
        timestamp = None
        texts = []
        
        for item in buffer:
            if 'timestamp' in item:
                timestamp = item['timestamp']
                if item.get('text'):  # 時間戳同行可能有文本
                    texts.append(item['text'])
            elif item.get('text'):
                texts.append(item['text'])
        
        if not texts:
            return
        
        # 判斷是原文+翻譯 還是 只有翻譯
        data = {"timestamp": timestamp or ""}
        
        hide_transcribe_result = self.config.get('output_notification', {}).get('hide_transcribe_result', False)
        
        logger.info(f"[Buffer] texts={texts}, timestamp={timestamp}, hide_transcribe={hide_transcribe_result}")
        
        # 簡化邏輯:根據文本行數判斷
        if len(texts) >= 2:
            # 有兩行文本:第一行=原文,第二行=翻譯
            data["original"] = texts[0]
            data["translated"] = texts[1]
            logger.info(f"[Buffer] Case: 2 texts -> first=original, second=translated")
        elif len(texts) == 1:
            # 只有一行文本
            text = texts[0]
            
            if hide_transcribe_result:
                # 如果隱藏轉錄,所有輸出都是翻譯
                data["original"] = ""
                data["translated"] = text
                logger.info(f"[Buffer] Case: hide_transcribe=True -> translated only")
            else:
                # 正常模式:單行文本視為原文(可能還在等待翻譯)
                data["original"] = text
                data["translated"] = ""
                logger.info(f"[Buffer] Case: single text -> original (waiting for translation)")
        
        logger.info(f"[Subtitle] Emit: {data}")
        self._broadcast({"type": "subtitle", "data": data})



    async def stream_output(self) -> AsyncGenerator[Dict, None]:
        """SSE 事件生成器（每個連線訂閱專屬 Queue，避免多客戶端等連互憑事件）"""
        logger.info(f"[Task {self.task_id}] Stream output started")
        event_count = 0
        my_queue = self._subscribe()
        try:
            while True:
                # 檢查是否停止且建件为空
                if (not self.running or self.stop_requested) and my_queue.empty():
                    logger.info(f"[Task {self.task_id}] Stream ending, sent {event_count} events")
                    break
                    
                try:
                    event = await asyncio.wait_for(my_queue.get(), timeout=1.0)
                    event_count += 1
                    logger.debug(f"[Task {self.task_id}] Sending event #{event_count}: {event['type']}")
                    yield event
                except asyncio.TimeoutError:
                    if self.running:
                        yield {"type": "ping", "data": {}}
                    else:
                        logger.info(f"[Task {self.task_id}] Not running, breaking stream")
                        break
                except Exception as e:
                    logger.error(f"[Task {self.task_id}] Stream error: {e}")
                    break
        finally:
            self._unsubscribe(my_queue)
    
    async def stop(self):
        """停止任務"""
        self.stop_requested = True
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        logger.info(f"Task {self.task_id} stopped")

# 全域管理器 (簡單字典實作)
active_translations: Dict[str, TranslationContext] = {}

def get_task(task_id: str) -> Optional[TranslationContext]:
    return active_translations.get(task_id)

def create_task(config: Dict[str, Any]) -> str:
    task_id = str(uuid.uuid4())
    context = TranslationContext(config, task_id)
    active_translations[task_id] = context
    return task_id

def remove_task(task_id: str):
    if task_id in active_translations:
        del active_translations[task_id]
