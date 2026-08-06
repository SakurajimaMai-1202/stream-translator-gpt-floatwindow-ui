from __future__ import annotations

from collections import defaultdict, deque
import math


TRACKED_LATENCY_METRICS = (
    "capture_wait_ms",
    "speech_to_slice_ms",
    "audio_duration_ms",
    "asr_queue_ms",
    "asr_inference_ms",
    "asr_realtime_factor",
    "assembler_wait_ms",
    "translation_queue_ms",
    "translation_inference_ms",
    "delivery_ms",
    "end_to_end_ms",
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class LatencyWindow:
    """Small in-process diagnostic window; it never stores audio or subtitle text."""

    def __init__(self, maxlen: int = 50):
        self.maxlen = max(1, int(maxlen))
        self.sample_count = 0
        self._values: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self.maxlen))

    def add(self, metrics: dict) -> None:
        self.sample_count += 1
        for name in TRACKED_LATENCY_METRICS:
            value = metrics.get(name)
            if isinstance(value, (int, float)) and math.isfinite(value):
                self._values[name].append(float(value))

    def snapshot(self) -> dict:
        result = {
            "sample_count": self.sample_count,
            "window_size": min(self.sample_count, self.maxlen),
            "max_window_size": self.maxlen,
            "metrics": {},
        }
        for name in TRACKED_LATENCY_METRICS:
            values = list(self._values.get(name, ()))
            if not values:
                continue
            result["metrics"][name] = {
                "latest": round(values[-1], 3),
                "p50": round(_percentile(values, 0.50), 3),
                "p95": round(_percentile(values, 0.95), 3),
            }
        return result
