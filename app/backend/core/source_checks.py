from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse


SourceKind = Literal["url", "file", "microphone", "system_audio"]


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


def check_url(url: str) -> SourceCheckResult:
    started = time.perf_counter()
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _result("url", started, "error", "url_format", "直播網址格式無效",
                       "請貼上以 http:// 或 https:// 開頭的完整網址。")
    executable = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if not executable:
        return _result("url", started, "unknown", "resolver", "尚未能解析網址：找不到 yt-dlp",
                       "在進階設定檢查執行環境，或直接啟動後查看取得串流的錯誤。", host=parsed.netloc)
    command = [executable, "--no-playlist", "--skip-download", "--dump-single-json", url.strip()]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return _result("url", started, "error", "resolve", "網址解析逾時",
                       "檢查網路、直播狀態或稍後重試。", host=parsed.netloc)
    if completed.returncode:
        detail = completed.stderr.strip()[-1200:]
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
        return _result(source, started, "error", "device_open", "無法開啟音訊裝置",
                       "重新選擇裝置、確認未被停用或占用，再重試。", technical_detail=str(exc))
    dbfs = round(20 * math.log10(max(peak, 1e-9)), 1)
    if peak < 0.0005:
        return _result(source, started, "unknown", "capture", "裝置已開啟，但測試期間未收到明顯聲音",
                       "播放影片或對麥克風說話後重試；收到聲音不代表模型已能辨識。",
                       received_audio=False, detected_speech=False, peak=peak, peak_dbfs=dbfs)
    return _result(source, started, "ready", "capture", "裝置已開啟並收到音訊",
                   "", received_audio=True, detected_speech=None, peak=peak, peak_dbfs=dbfs)
