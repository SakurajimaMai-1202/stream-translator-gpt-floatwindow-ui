from __future__ import annotations

import logging
import json
import math
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from backend.core.ytdlp_addon import ytdlp_command
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from backend.core.cookie_manager import _resolve_runtime_python
from backend.core.external_process import run_external


logger = logging.getLogger(__name__)


SourceKind = Literal["url", "file", "microphone", "system_audio", "process_audio"]


@dataclass
class SourceCheckResult:
    source: SourceKind
    status: Literal["ready", "error", "unknown"]
    stage: str
    message: str
    recovery: str
    trace_id: str
    elapsed_ms: float
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(source: SourceKind, started: float, status: str, stage: str, message: str,
            recovery: str = "", **details: Any) -> SourceCheckResult:
    return SourceCheckResult(
        source=source,
        status=status,  # type: ignore[arg-type]
        stage=stage,
        message=message,
        recovery=recovery,
        trace_id=uuid.uuid4().hex,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        details=details,
    )


def check_file(path_text: str) -> SourceCheckResult:
    started = time.perf_counter()
    path = Path(path_text).expanduser()
    if not path.is_file():
        return _result("file", started, "error", "file_open", "找不到或無法讀取檔案",
                       "重新選擇存在且可讀的影音檔。", path=str(path))
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return _result("file", started, "unknown", "decoder", "尚未能檢查音軌：找不到 ffprobe",
                       "在進階設定檢查 FFmpeg，或直接啟動後查看解碼錯誤。", path=str(path))
    command = [ffprobe, "-v", "error", "-show_entries", "stream=index,codec_type,codec_name",
               "-of", "json", str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return _result("file", started, "error", "decode", "檔案檢查逾時",
                       "確認檔案未損壞，或轉換成常見影音格式後重試。", path=str(path))
    if completed.returncode:
        return _result("file", started, "error", "decode", "影音格式無法解析",
                       "確認檔案完整，或用 FFmpeg 轉換後重試。", path=str(path),
                       technical_detail=completed.stderr.strip()[-1000:])
    payload = json.loads(completed.stdout or "{}")
    audio = [item for item in payload.get("streams", []) if item.get("codec_type") == "audio"]
    if not audio:
        return _result("file", started, "error", "audio_track", "檔案沒有可用音軌",
                       "改選含音訊的影音檔。", path=str(path))
    return _result("file", started, "ready", "decode", "檔案可讀且音軌可解碼", path=str(path),
                   audio_streams=audio)


def _resolve_url_command() -> list[str] | None:
    try:
        runtime_python = _resolve_runtime_python()
    except RuntimeError:
        runtime_python = None
    if runtime_python and not (
        getattr(sys, "frozen", False)
        and runtime_python.resolve() == Path(sys.executable).resolve()
    ):
        command = ytdlp_command(runtime_python)
        for root in (runtime_python.parent, runtime_python.parent.parent):
            node = root / "_js_runtime" / "node.exe"
            if node.is_file():
                command.extend(["--js-runtimes", f"node:{node}"])
                break
        return command
    executable = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    return [executable] if executable else None


def check_url(url: str) -> SourceCheckResult:
    started = time.perf_counter()
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _result("url", started, "error", "url_format", "直播網址格式無效",
                       "請貼上以 http:// 或 https:// 開頭的完整網址。")
    command = _resolve_url_command()
    if not command:
        return _result("url", started, "unknown", "resolver", "尚未能解析網址：找不到 yt-dlp",
                       "在進階設定檢查執行環境，或直接啟動後查看取得串流的錯誤。", host=parsed.netloc)
    command.extend(["--no-playlist", "--skip-download", "--dump-single-json", url.strip()])
    try:
        completed = run_external(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=20, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return _result("url", started, "error", "resolve", "網址解析逾時",
                       "檢查網路、直播狀態或稍後重試。", host=parsed.netloc)
    if completed.returncode:
        detail = completed.stderr.strip()[-1200:]
        for pattern, message, recovery in (
            ('twitter space not found', '找不到這個 X Space（網址錯誤、已刪除、尚未開始，或需要登入 Cookie）',
             '確認網址完整；若 Space 尚未開始請等開播後再試，需要登入時請設定 X 的 Cookie。'),
            ('space ended and replay is disabled', 'X Space 已結束，且主持人沒有開放重播',
             '這場 Space 已無法收聽；請改用正在進行或有開放重播的 Space。'),
        ):
            if pattern in completed.stderr.lower():
                return _result("url", started, "error", "resolve", message, recovery,
                               host=parsed.netloc, technical_detail=detail)
        return _result("url", started, "error", "resolve", "無法解析或存取直播網址",
                       "確認網址、直播是否已開始、Cookie 與網路狀態後重試。", host=parsed.netloc,
                       technical_detail=detail)
    payload = json.loads(completed.stdout or "{}")
    formats = payload.get("formats") or []
    audio_formats = [item for item in formats if item.get("acodec") not in {None, "none"}]
    if not audio_formats:
        return _result("url", started, "error", "audio_stream", "解析成功但找不到音訊串流",
                       "確認直播包含聲音，或改用其他可存取的來源。", title=payload.get("title"))
    return _result("url", started, "ready", "stream", "網址已解析並找到音訊串流",
                   title=payload.get("title"), live_status=payload.get("live_status"),
                   audio_format_count=len(audio_formats))


def _process_audio_probe_command(process_id: int, process_start_time: str, duration_seconds: float) -> list[str]:
    # Resolve the same profile/CPU sidecar and workspace source as a real task.
    from backend.api.config import get_config_manager
    from backend.core.translator import TranslationContext
    manager = get_config_manager()
    config = manager.get_config()
    import copy
    config = copy.deepcopy(config)
    config['input'].update(audio_source='process_audio', process_id=process_id,
                           process_start_time=process_start_time)
    command = TranslationContext(manager.to_main_args(config), 'source-probe')._build_command()
    if '-c' in command:
        index = command.index('-c')
        prefix = command[:index + 1] + [command[index + 1].replace(
            "run_module('stream_translator_gpt',", "run_module('stream_translator_gpt.process_audio_capture',")]
    else:
        index = command.index('-m')
        prefix = command[:index + 1] + ['stream_translator_gpt.process_audio_capture']
    return prefix + ['--probe', '--process-id', str(process_id), '--process-start-time', process_start_time,
                     '--duration', str(duration_seconds)]


def check_process_audio(process_id: int | None, process_start_time: str,
                        duration_seconds: float = 1.0, window_handle: str = '') -> SourceCheckResult:
    started = time.perf_counter()
    source = 'process_audio'
    recovery = '重新選擇正在播放聲音的程式，再測試一次。'
    def failure(stage: str, message: str, detail: str, recovery_message: str = recovery):
        logger.warning('指定程式收音測試失敗 stage=%s technical_detail=%s', stage, detail)
        return _result(source, started, 'error', stage, message, recovery_message,
                       technical_detail=detail)

    from backend.core.process_audio import validate_process_target
    try:
        validate_process_target(process_id, process_start_time, window_handle or None)
    except (ValueError, RuntimeError, OSError) as exc:
        return failure('target', str(exc), str(exc))
    completed = None
    try:
        duration = min(max(float(duration_seconds), 0.2), 3.0)
        try:
            command = _process_audio_probe_command(process_id, process_start_time, duration)
        except RuntimeError as exc:
            return failure('runtime', str(exc), str(exc),
                           '到「ASR 模型管理」檢查 CPU ASR Runtime，或改用其他音訊來源。')
        completed = run_external(command, capture_output=True, text=True, timeout=duration + 15,
                                 check=False, encoding='utf-8', errors='replace',
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        if not isinstance(payload, dict):
            raise ValueError('指定程式收音測試回傳的 JSON 格式不正確')
        if completed.returncode or payload.get('error'):
            message = str(payload.get('error') or payload.get('message') or '指定程式收音失敗')
            return failure('capture', message, (completed.stderr or message).strip()[-800:])
        received = bool(payload.get('received_audio'))
        return _result(source, started, 'ready' if received else 'unknown', 'capture',
                       '已收到指定程式的音訊' if received else '程式已開啟，但測試期間未收到明顯聲音',
                       '' if received else recovery, received_audio=received, detected_speech=None,
                       peak=payload.get('peak', 0), peak_dbfs=payload.get('peak_dbfs'))
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, IndexError) as exc:
        stderr = completed.stderr if completed is not None else getattr(exc, 'stderr', '')
        if isinstance(stderr, bytes):
            stderr = stderr.decode('utf-8', errors='replace')
        message = '無法完成指定程式收音測試'
        if 'No module named stream_translator_gpt.process_audio_capture' in (stderr or ''):
            message = '目前的執行環境缺少指定應用程式音訊元件，請重新安裝 CPU ASR Runtime 或更新主程式。'
        return failure('capture', message, (stderr or str(exc)).strip()[-800:])


def check_device(source: SourceKind, device_index: int | None, duration_seconds: float = 1.0) -> SourceCheckResult:
    started = time.perf_counter()
    duration_seconds = min(max(float(duration_seconds), 0.2), 3.0)
    try:
        if source == "microphone":
            import sounddevice as sd
            recording = sd.rec(int(16000 * duration_seconds), samplerate=16000, channels=1,
                               dtype="float32", device=device_index)
            sd.wait()
            peak = max((abs(float(value)) for row in recording for value in row), default=0.0)
        elif source == "system_audio":
            import pyaudiowpatch as pyaudio
            audio = pyaudio.PyAudio()
            info = (audio.get_device_info_by_index(device_index) if device_index is not None
                    else audio.get_default_wasapi_loopback())
            stream = audio.open(format=pyaudio.paFloat32, channels=max(1, int(info.get("maxInputChannels", 2))),
                                rate=int(info.get("defaultSampleRate", 48000)), input=True,
                                input_device_index=int(info["index"]), frames_per_buffer=1024)
            peak = 0.0
            import struct
            for _ in range(max(1, int(duration_seconds * int(info.get("defaultSampleRate", 48000)) / 1024))):
                raw = stream.read(1024, exception_on_overflow=False)
                values = struct.unpack(f"<{len(raw) // 4}f", raw)
                peak = max(peak, max((abs(value) for value in values), default=0.0))
            stream.stop_stream(); stream.close(); audio.terminate()
        else:
            raise ValueError(f"不支援的裝置來源: {source}")
    except Exception as exc:
        logger.debug("測試音訊裝置失敗", exc_info=True)
        return _result(source, started, "error", "device_open", "無法開啟音訊裝置",
                       "重新選擇裝置、確認未被停用或占用，再重試。", technical_detail=str(exc))
    dbfs = round(20 * math.log10(max(peak, 1e-9)), 1)
    if peak < 0.0005:
        return _result(source, started, "unknown", "capture", "裝置已開啟，但測試期間未收到明顯聲音",
                       "播放影片或對麥克風說話後重試；收到聲音不代表模型已能辨識。",
                       received_audio=False, detected_speech=False, peak=peak, peak_dbfs=dbfs)
    return _result(source, started, "ready", "capture", "裝置已開啟並收到音訊",
                   "", received_audio=True, detected_speech=None, peak=peak, peak_dbfs=dbfs)
