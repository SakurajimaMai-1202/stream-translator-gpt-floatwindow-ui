"""Windows process capture adapter and lightweight runtime probe entry point."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading
import time

from .process_audio_targets import platform_support, validate_process_target

_LIBRARY = None  # Keep DLL loaded for worker/callback lifetime, including bounded-stop timeout.
_LIBRARY_LOCK = threading.Lock()


def _error(operation: str, code: int) -> RuntimeError:
    if (code & 0xFFFFFFFF) == 0x8007042B:
        return RuntimeError("目標應用程式已退出，請重新選擇後開始翻譯。")
    return RuntimeError(f"{operation}失敗 (HRESULT 0x{code & 0xFFFFFFFF:08X})；請重新選擇目標或改用音訊設備。")


def _load_library_uncached():
    supported, reason = platform_support()
    if not supported:
        raise RuntimeError(reason)
    path = Path(__file__).resolve().parent / "native" / "process_audio_capture.dll"
    if not path.is_file():
        raise RuntimeError("目前執行環境缺少指定應用程式音訊擷取元件，請更新或重新建置 runtime。")
    try:
        # Only load our absolute package path; never an arbitrary PATH DLL.
        dll = ctypes.CDLL(str(path))
        signatures = {
            "pa_create": ([ctypes.c_uint32, ctypes.c_uint64, ctypes.POINTER(ctypes.c_int32)], ctypes.c_void_p),
            "pa_start": ([ctypes.c_void_p], ctypes.c_int32),
            "pa_read": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int], ctypes.c_int32),
            "pa_status": ([ctypes.c_void_p], ctypes.c_int32),
            "pa_dropped_frames": ([ctypes.c_void_p], ctypes.c_uint64),
            "pa_stop": ([ctypes.c_void_p], None),
            "pa_destroy": ([ctypes.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            function = getattr(dll, name)
            function.argtypes, function.restype = args, result
        return dll
    except (OSError, AttributeError) as exc:
        raise RuntimeError(f"無法載入音訊擷取元件，請確認 runtime 與 DLL 架構一致：{exc}") from exc


def _load_library():
    global _LIBRARY
    with _LIBRARY_LOCK:
        if _LIBRARY is None:
            _LIBRARY = _load_library_uncached()
        return _LIBRARY


def capture_capabilities() -> dict:
    try:
        _load_library()
    except RuntimeError as exc:
        return {"supported": False, "message": str(exc)}
    return {"supported": True, "message": "指定應用程式音訊元件可載入", "sample_rate": 48000,
            "channels": 2, "output_sample_rate": 16000, "scope": "process_tree"}


class NativeCapture:
    """The read owner closes; stop may run concurrently without destroying handles."""

    def __init__(self, process_id: int, process_start_time: str, *, start: bool = True):
        import numpy as np
        self.buffer = np.empty(48000 // 10 * 2, dtype=np.float32)
        validate_process_target(process_id, process_start_time)
        self.dll = _load_library()
        self._lock = threading.Lock()
        error = ctypes.c_int32()
        self.handle = self.dll.pa_create(int(process_id), int(process_start_time), ctypes.byref(error))
        if not self.handle:
            raise _error("建立音訊擷取", error.value)
        if start:
            self.start()

    def start(self):
        result = self.dll.pa_start(self.handle)
        if result < 0:
            self.close()
            raise _error("初始化音訊擷取", result)

    def read(self, timeout_ms: int = 100):
        count = self.dll.pa_read(self.handle, self.buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                 len(self.buffer), timeout_ms)
        if count < 0:
            raise _error("讀取音訊", count)
        return self.buffer[:count].copy()

    @property
    def dropped_frames(self) -> int:
        return int(self.dll.pa_dropped_frames(self.handle))

    def stop(self):
        with self._lock:
            if self.handle:
                self.dll.pa_stop(self.handle)

    def close(self):
        with self._lock:
            if self.handle:
                self.dll.pa_destroy(self.handle)
                self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PCMAdapter:
    """Continuous anti-alias filtering and exact 3:1 decimation, then 512 frames."""

    def __init__(self):
        import numpy as np
        self.np = np
        # Fixed short FIR avoids a heavy scipy import in the portable runtimes.
        position = np.arange(63) - 31
        self.coefficients = np.sinc(2 * 7200 / 48000 * position) * np.hamming(63)
        self.coefficients /= self.coefficients.sum()
        self.reset()

    def reset(self):
        self.state = self.np.zeros(len(self.coefficients) - 1)
        self.offset = 0
        self.remaining = self.np.empty(0, dtype=self.np.float32)

    def frames(self, stereo):
        if not len(stereo):
            return []
        mono = stereo.reshape(-1, 2).mean(axis=1)
        padded = self.np.concatenate((self.state, mono))
        filtered = self.np.convolve(padded, self.coefficients, mode='valid')
        self.state = padded[-(len(self.coefficients) - 1):].copy()
        audio = filtered[self.offset::3].astype(self.np.float32)
        self.offset = (self.offset - len(mono)) % 3
        audio = self.np.concatenate((self.remaining, audio))
        complete = len(audio) // 512 * 512
        self.remaining = audio[complete:].copy()
        return [audio[i:i + 512].copy() for i in range(0, complete, 512)]


class ProcessAudioGetter:
    def __init__(self, process_id: int, process_start_time: str):
        self.adapter = PCMAdapter()
        # Do not record while ASR models are still initializing in other futures.
        self.capture = NativeCapture(process_id, process_start_time, start=False)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()
        self.capture.stop()

    def close(self):
        """Only call before loop starts, or from its owner after loop finishes."""
        self.stop_event.set()
        self.capture.close()

    def _exit_handler(self, *_):
        self.stop()

    def loop(self, output_queue):
        from .common import AUDIO_STREAM_GAP, INFO, WARNING
        print(f"{INFO}指定應用程式音訊擷取已開始（程序及子程序）。")
        dropped = 0
        try:
            if self.stop_event.is_set():
                return
            self.capture.start()
            while not self.stop_event.is_set():
                audio = self.capture.read()
                if self.stop_event.is_set():
                    break
                total = self.capture.dropped_frames
                if total != dropped:
                    print(f"{WARNING}音訊擷取中斷／緩衝溢出：{total - dropped} frames，已重設擷取緩衝。")
                    dropped = total
                    self.adapter.reset()
                    output_queue.put(AUDIO_STREAM_GAP)
                if audio.size:
                    for frame in self.adapter.frames(audio):
                        output_queue.put(frame)
        finally:
            self.capture.close()
            output_queue.put(None)


def probe(process_id: int, process_start_time: str, duration: float) -> dict:
    import numpy as np
    peak, samples = 0.0, 0
    with NativeCapture(process_id, process_start_time) as capture:
        deadline = time.monotonic() + min(max(duration, 0.2), 3.0)
        while time.monotonic() < deadline:
            audio = capture.read()
            samples += audio.size
            if audio.size:
                peak = max(peak, float(np.max(np.abs(audio))))
        dropped = capture.dropped_frames
    received = peak >= 0.0005
    return {"supported": True, "received_audio": received, "peak": peak,
            "peak_dbfs": round(20 * math.log10(max(peak, 1e-9)), 1), "samples": samples,
            "dropped_frames": dropped, "message": "已收到音訊" if received else "擷取已開啟，目前無明顯聲音"}


def cli():
    parser = argparse.ArgumentParser(description="Windows process audio capture probe")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--process-id", type=int)
    parser.add_argument("--process-start-time")
    parser.add_argument("--duration", type=float, default=1.0)
    args = parser.parse_args()
    try:
        if args.capabilities:
            result = capture_capabilities()
        elif args.probe and args.process_id and args.process_start_time:
            result = probe(args.process_id, args.process_start_time, args.duration)
        else:
            raise ValueError("請提供 --probe、--process-id 與 --process-start-time。")
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result.get("supported") else 1
    except Exception as exc:
        print(json.dumps({"supported": False, "received_audio": False, "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
