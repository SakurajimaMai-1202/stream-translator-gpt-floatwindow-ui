import collections
import math

import numpy as np


class AudioPreprocessor:
    """Causal, per-frame audio preprocessor with optional 80 Hz high-pass and boost-only AGC."""

    def __init__(
        self,
        sample_rate: int = 16000,
        agc_enabled: bool = True,
        agc_target_dbfs: float = -20.0,
        agc_max_gain_db: float = 30.0,
        agc_floor_dbfs: float = -75.0,
        agc_rise_s: float = 0.3,
        agc_fall_s: float = 3.0,
        agc_peak_limit: float = 0.95,
        agc_noise_ceiling_dbfs: float = -50.0,
        agc_noise_window_s: float = 10.0,
        agc_noise_percentile: float = 10.0,
        highpass_enabled: bool = False,
        highpass_cutoff_hz: float = 80.0,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.agc_enabled = bool(agc_enabled)
        self.agc_target_dbfs = float(agc_target_dbfs)
        self.agc_max_gain_db = max(0.0, float(agc_max_gain_db))
        self.agc_floor_dbfs = float(agc_floor_dbfs)
        self.agc_rise_s = float(agc_rise_s)
        self.agc_fall_s = float(agc_fall_s)
        self.agc_peak_limit = float(agc_peak_limit)
        self.agc_noise_ceiling_dbfs = float(agc_noise_ceiling_dbfs)
        self.agc_noise_window_s = max(0.0, float(agc_noise_window_s))
        self.agc_noise_percentile = min(max(float(agc_noise_percentile), 0.0), 100.0)
        self.highpass_enabled = bool(highpass_enabled)
        self.highpass_cutoff_hz = float(highpass_cutoff_hz)

        self._hp_alpha = 1.0 / (
            1.0 + 2.0 * math.pi * self.highpass_cutoff_hz / self.sample_rate
        )
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
        self._level_db = self.agc_target_dbfs
        self._prev_lin = 1.0
        self._noise_window: collections.deque[tuple[float, float]] = collections.deque()
        self._noise_window_duration_s = 0.0

    def reset(self) -> None:
        """Reset filter state, speech level estimate, noise floor window, and previous gain."""
        self._hp_prev_x = 0.0
        self._hp_prev_y = 0.0
        self._level_db = self.agc_target_dbfs
        self._prev_lin = 1.0
        self._noise_window.clear()
        self._noise_window_duration_s = 0.0

    def _apply_highpass(self, x: np.ndarray) -> np.ndarray:
        a = self._hp_alpha
        prev_x = self._hp_prev_x
        prev_y = self._hp_prev_y
        out: list[float] = []
        append = out.append
        for sample in x.tolist():
            y_val = a * (prev_y + sample - prev_x)
            prev_x = sample
            prev_y = y_val
            append(y_val)
        self._hp_prev_x = prev_x
        self._hp_prev_y = prev_y
        return np.asarray(out, dtype=np.float32)

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Process one 1D float32 frame in [-1, 1]; returns same length & float32 with no NaN/Inf."""
        if not self.agc_enabled and not self.highpass_enabled:
            return frame

        x = np.asarray(frame, dtype=np.float32)
        if x.size == 0:
            return x

        x = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=-1.0).astype(np.float32, copy=False)

        if self.highpass_enabled:
            x = self._apply_highpass(x)

        if not self.agc_enabled:
            return np.clip(x, -1.0, 1.0).astype(np.float32, copy=False)

        n = len(x)
        frame_dur_s = n / self.sample_rate
        fps = self.sample_rate / n

        mean_sq = float(np.mean(x.astype(np.float64) ** 2))
        db = 10.0 * math.log10(mean_sq + 1e-12)

        if db > self.agc_floor_dbfs:
            a_up = 1.0 - math.exp(-1.0 / (self.agc_rise_s * fps)) if self.agc_rise_s > 0 else 1.0
            a_down = 1.0 - math.exp(-1.0 / (self.agc_fall_s * fps)) if self.agc_fall_s > 0 else 1.0
            alpha = a_up if db > self._level_db else a_down
            self._level_db += alpha * (db - self._level_db)

        self._noise_window.append((frame_dur_s, max(db, -100.0)))
        self._noise_window_duration_s += frame_dur_s
        while (
            len(self._noise_window) > 1
            and self._noise_window_duration_s - self._noise_window[0][0] >= self.agc_noise_window_s
        ):
            dropped_dur, _ = self._noise_window.popleft()
            self._noise_window_duration_s -= dropped_dur

        noise_db = float(
            np.percentile([d for _, d in self._noise_window], self.agc_noise_percentile)
        )

        want = min(max(self.agc_target_dbfs - self._level_db, 0.0), self.agc_max_gain_db)
        want = min(want, self.agc_noise_ceiling_dbfs - noise_db)

        peak = float(np.max(np.abs(x))) + 1e-9
        cap_lin = self.agc_peak_limit / peak
        want = min(want, 20.0 * math.log10(cap_lin))
        want = max(want, 0.0)

        lin = 10.0 ** (want / 20.0)
        start = min(self._prev_lin, max(cap_lin, 1.0))

        if start == 1.0 and lin == 1.0:
            y = x
        else:
            ramp = np.linspace(start, lin, n, endpoint=False, dtype=np.float32)
            y = x * ramp

        self._prev_lin = lin
        return np.clip(y, -1.0, 1.0).astype(np.float32, copy=False)


def build_audio_preprocessor(
    enabled: bool,
    agc_enabled: bool = True,
    agc_max_gain_db: float = 30.0,
    highpass_enabled: bool = False,
) -> AudioPreprocessor | None:
    """Build an AudioPreprocessor when enabled and at least one stage is active, else None."""
    if not enabled or (not agc_enabled and not highpass_enabled):
        return None
    max_gain = 30.0 if agc_max_gain_db is None else float(agc_max_gain_db)
    return AudioPreprocessor(
        agc_enabled=bool(agc_enabled),
        agc_max_gain_db=max_gain,
        highpass_enabled=bool(highpass_enabled),
    )
