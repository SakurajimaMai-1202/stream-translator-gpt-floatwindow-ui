"""Unit and integration tests for WS-2A AudioPreprocessor and AudioSlicer hook."""
import queue
import time

import numpy as np
import pytest

from stream_translator_gpt import audio_slicer, pipeline_runner
from stream_translator_gpt.audio_preprocessor import (
    AudioPreprocessor,
    build_audio_preprocessor,
)
from stream_translator_gpt.common import AUDIO_STREAM_GAP, SAMPLES_PER_FRAME

SAMPLE_RATE = 16000


def _sine(freq_hz: float, duration_s: float, dbfs: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(round(duration_s * sample_rate))
    t = np.arange(n, dtype=np.float64) / sample_rate
    rms = 10.0 ** (dbfs / 20.0)
    amp = rms * np.sqrt(2.0)
    return (amp * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def _rms_dbfs(x: np.ndarray) -> float:
    return float(10.0 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-12))


def _process_frames(proc: AudioPreprocessor, signal: np.ndarray, frame_len: int = SAMPLES_PER_FRAME) -> np.ndarray:
    chunks = [
        proc.process(signal[i:i + frame_len])
        for i in range(0, len(signal), frame_len)
    ]
    return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)


def test_quiet_speech_boosted_toward_target_and_capped_by_max_gain():
    # -58 dBFS 1 kHz sine with 1.0 s -100 dBFS gaps (>10% of the 10 s window)
    # so the 10th-percentile noise floor stays at -100 dBFS.
    gap = _sine(1000.0, 1.0, -100.0)
    speech = _sine(1000.0, 4.0, -58.0)
    signal = np.concatenate([gap, speech, gap, speech, gap, speech])

    # With 40 dB max gain, -58 dBFS converges close to -20 dBFS.
    proc_40 = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=40.0)
    out_40 = _process_frames(proc_40, signal)
    tail_40_db = _rms_dbfs(out_40[-SAMPLE_RATE:])
    assert -22.5 <= tail_40_db <= -18.5
    assert tail_40_db - (-58.0) <= 40.0 + 0.5

    # With default 30 dB max gain, boost is capped at <= 30 dB.
    proc_30 = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0)
    out_30 = _process_frames(proc_30, signal)
    tail_30_db = _rms_dbfs(out_30[-SAMPLE_RATE:])
    assert tail_30_db - (-58.0) <= 30.0 + 0.5
    assert tail_30_db > -30.0


def test_quiet_speech_with_exact_zero_gaps_reaches_full_gain():
    gap = np.zeros(SAMPLE_RATE, dtype=np.float32)
    speech = _sine(1000.0, 4.0, -58.0)
    signal = np.concatenate([gap, speech, gap, speech, gap, speech])

    proc = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0)
    out = _process_frames(proc, signal)

    last_block_tail_db = _rms_dbfs(out[-SAMPLE_RATE:])
    gain_db = last_block_tail_db - (-58.0)
    assert gain_db >= 27.0
    assert gain_db <= 30.5


@pytest.mark.parametrize('dbfs', [-20.0, -15.0, -6.0])
def test_normal_or_loud_signal_is_not_attenuated(dbfs):
    signal = _sine(1000.0, 2.0, dbfs)
    proc = AudioPreprocessor(agc_enabled=True, highpass_enabled=False)
    out = _process_frames(proc, signal)
    assert np.allclose(out, signal, atol=1e-6)


def test_disabled_stages_return_input_unchanged():
    frame = _sine(440.0, 0.032, -35.0)
    proc = AudioPreprocessor(agc_enabled=False, highpass_enabled=False)
    out = proc.process(frame)
    assert out is frame


def test_steady_noise_respects_noise_ceiling():
    rng = np.random.default_rng(42)
    raw = rng.standard_normal(60 * SAMPLE_RATE).astype(np.float64)
    target_rms = 10.0 ** (-60.0 / 20.0)
    noise = (raw * (target_rms / np.sqrt(np.mean(raw ** 2)))).astype(np.float32)

    proc = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0, agc_noise_ceiling_dbfs=-50.0)
    out = _process_frames(proc, noise)

    assert _rms_dbfs(out) <= -48.5
    assert _rms_dbfs(out[-30 * SAMPLE_RATE:]) <= -48.5


def test_single_zero_frame_does_not_open_noise_gate():
    rng = np.random.default_rng(123)
    zero_frame = np.zeros(SAMPLES_PER_FRAME, dtype=np.float32)
    raw = rng.standard_normal(30 * SAMPLE_RATE).astype(np.float64)
    target_rms = 10.0 ** (-60.0 / 20.0)
    noise = (raw * (target_rms / np.sqrt(np.mean(raw ** 2)))).astype(np.float32)
    signal = np.concatenate([zero_frame, noise])

    proc = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0, agc_noise_ceiling_dbfs=-50.0)
    out = _process_frames(proc, signal)

    assert _rms_dbfs(out[:10 * SAMPLE_RATE]) <= -48.0
    assert _rms_dbfs(out[-10 * SAMPLE_RATE:]) <= -48.0


def test_fluctuating_noise_stays_controlled():
    rng = np.random.default_rng(7)
    block_len = SAMPLE_RATE // 2  # 0.5 s
    blocks = []
    for _ in range(60):  # 30 s total
        level_db = float(rng.uniform(-66.0, -56.0))
        raw = rng.standard_normal(block_len).astype(np.float64)
        target_rms = 10.0 ** (level_db / 20.0)
        blocks.append((raw * (target_rms / np.sqrt(np.mean(raw ** 2)))).astype(np.float32))
    signal = np.concatenate(blocks)

    proc = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0, agc_noise_ceiling_dbfs=-50.0)
    out = _process_frames(proc, signal)

    # With p10 ~= -65 dBFS and ceiling -50 dBFS (+15 dB gain), power-averaged RMS
    # of uniform[-66, -56] dBFS noise (~ -60.1 dBFS) lands near -45 dBFS.
    assert _rms_dbfs(out[-10 * SAMPLE_RATE:]) <= -43.5


def test_sudden_burst_after_quiet_speech_no_clipping_or_nan():
    gap = _sine(1000.0, 1.0, -100.0)
    quiet = _sine(1000.0, 6.0, -55.0)
    proc = AudioPreprocessor(agc_enabled=True, agc_max_gain_db=30.0, agc_peak_limit=0.95)
    _process_frames(proc, np.concatenate([gap, quiet]))

    # Sudden loud burst with peak 0.5: ramp start and end must both respect peak limit.
    burst_half = np.full(SAMPLES_PER_FRAME, 0.5, dtype=np.float32)
    out_half = proc.process(burst_half)
    assert np.all(np.isfinite(out_half))
    assert np.max(np.abs(out_half)) <= 0.95 + 1e-3

    # Re-prime quiet state, then hit with a 0 dBFS (peak 1.0) burst.
    proc.reset()
    _process_frames(proc, np.concatenate([gap, quiet]))
    burst_full = np.ones(SAMPLES_PER_FRAME, dtype=np.float32)
    out_full = proc.process(burst_full)
    assert np.all(np.isfinite(out_full))
    assert np.min(out_full) >= -1.0
    assert np.max(out_full) <= 1.0

    # NaN / Inf inputs are sanitized.
    bad = np.array([np.nan, np.inf, -np.inf, 0.1] * 128, dtype=np.float32)
    out_bad = proc.process(bad)
    assert np.all(np.isfinite(out_bad))
    assert np.min(out_bad) >= -1.0
    assert np.max(out_bad) <= 1.0


@pytest.mark.parametrize('highpass', [False, True])
@pytest.mark.parametrize('length', [0, 1, 160, 333, 512, 1024, 2000])
def test_output_length_and_dtype_for_arbitrary_frame_sizes(highpass, length):
    proc = AudioPreprocessor(agc_enabled=True, highpass_enabled=highpass)
    frame = np.linspace(-0.01, 0.01, length, dtype=np.float32)
    out = proc.process(frame)
    assert len(out) == length
    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))


def test_reset_restores_initial_state():
    warmup = _sine(1000.0, 2.0, -50.0)
    test_seq = np.concatenate([
        _sine(1000.0, 0.5, -100.0),
        _sine(440.0, 1.5, -45.0),
        _sine(1000.0, 0.5, -12.0),
    ])

    p1 = AudioPreprocessor(agc_enabled=True, highpass_enabled=True)
    p2 = AudioPreprocessor(agc_enabled=True, highpass_enabled=True)

    _process_frames(p1, warmup)
    p1.reset()

    out1 = _process_frames(p1, test_seq)
    out2 = _process_frames(p2, test_seq)
    assert np.array_equal(out1, out2)


def test_highpass_attenuation_continuity_and_speed():
    sig_50 = _sine(50.0, 2.0, -20.0)
    sig_1k = _sine(1000.0, 2.0, -20.0)

    p50 = AudioPreprocessor(agc_enabled=False, highpass_enabled=True)
    out_50 = _process_frames(p50, sig_50)
    atten_50_db = _rms_dbfs(sig_50[SAMPLE_RATE:]) - _rms_dbfs(out_50[SAMPLE_RATE:])
    assert atten_50_db > 4.0

    p1k = AudioPreprocessor(agc_enabled=False, highpass_enabled=True)
    out_1k = _process_frames(p1k, sig_1k)
    atten_1k_db = _rms_dbfs(sig_1k[SAMPLE_RATE:]) - _rms_dbfs(out_1k[SAMPLE_RATE:])
    assert atten_1k_db < 0.5

    # Cross-frame continuity: chunked processing matches whole-buffer processing.
    mixed = (_sine(60.0, 0.256, -24.0) + _sine(1200.0, 0.256, -24.0)).astype(np.float32)
    p_whole = AudioPreprocessor(agc_enabled=False, highpass_enabled=True)
    p_chunked = AudioPreprocessor(agc_enabled=False, highpass_enabled=True)
    whole_out = p_whole.process(mixed)
    chunked_out = _process_frames(p_chunked, mixed, frame_len=SAMPLES_PER_FRAME)
    assert np.allclose(whole_out, chunked_out, atol=1e-6)

    # Per-frame processing time for 512 samples (AGC + HPF) stays well under 1 ms on average.
    p_bench = AudioPreprocessor(agc_enabled=True, highpass_enabled=True)
    frame = _sine(1000.0, SAMPLES_PER_FRAME / SAMPLE_RATE, -40.0)
    t0 = time.perf_counter()
    for _ in range(200):
        p_bench.process(frame)
    avg_ms = (time.perf_counter() - t0) * 1000.0 / 200
    assert avg_ms < 2.0


def test_build_audio_preprocessor_factory():
    assert build_audio_preprocessor(enabled=False, agc_enabled=True, highpass_enabled=True) is None
    assert build_audio_preprocessor(enabled=True, agc_enabled=False, highpass_enabled=False) is None

    proc = build_audio_preprocessor(
        enabled=True,
        agc_enabled=True,
        agc_max_gain_db=24.0,
        highpass_enabled=True,
    )
    assert isinstance(proc, AudioPreprocessor)
    assert proc.agc_enabled is True
    assert proc.agc_max_gain_db == pytest.approx(24.0)
    assert proc.highpass_enabled is True


class _RecordingPreprocessor:
    def __init__(self, scale: float = 2.0):
        self.scale = scale
        self.processed = 0
        self.resets = 0

    def process(self, frame: np.ndarray) -> np.ndarray:
        self.processed += 1
        return (frame * self.scale).astype(np.float32)

    def reset(self) -> None:
        self.resets += 1


def _make_legacy_slicer(preprocessor=None):
    return audio_slicer.AudioSlicer(
        min_audio_length=0.0,
        max_audio_length=10.0,
        target_audio_length=1.0,
        continuous_no_speech_threshold=1.0,
        dynamic_no_speech_threshold=False,
        prefix_retention_length=0.0,
        vad_threshold=0.5,
        dynamic_vad_threshold=False,
        disable_vad=True,
        slicing_mode='legacy',
        preprocessor=preprocessor,
    )


def test_audio_slicer_without_preprocessor_preserves_audio():
    slicer = _make_legacy_slicer(preprocessor=None)
    f1 = np.full(SAMPLES_PER_FRAME, 0.25, dtype=np.float32)
    incoming, outgoing = queue.SimpleQueue(), queue.SimpleQueue()
    incoming.put(f1)
    incoming.put(None)
    slicer.loop(incoming, outgoing)

    task = outgoing.get()
    assert outgoing.get() is None
    assert np.array_equal(task.audio, f1)


def test_audio_slicer_calls_preprocessor_process_and_reset_on_gap():
    fake = _RecordingPreprocessor(scale=2.0)
    slicer = _make_legacy_slicer(preprocessor=fake)
    f1 = np.full(SAMPLES_PER_FRAME, 0.1, dtype=np.float32)
    f2 = np.full(SAMPLES_PER_FRAME, 0.2, dtype=np.float32)

    incoming, outgoing = queue.SimpleQueue(), queue.SimpleQueue()
    incoming.put(f1)
    incoming.put(AUDIO_STREAM_GAP)
    incoming.put(f2)
    incoming.put(None)
    slicer.loop(incoming, outgoing)

    t1 = outgoing.get()
    t2 = outgoing.get()
    assert outgoing.get() is None
    assert fake.processed == 2
    assert fake.resets == 1
    assert np.allclose(t1.audio, f1 * 2.0)
    assert np.allclose(t2.audio, f2 * 2.0)


def test_pipeline_runner_create_slicer_wires_preprocessor():
    base_options = {
        'min_audio_length': 0.7,
        'max_audio_length': 6.0,
        'target_audio_length': 3.0,
        'continuous_no_speech_threshold': 0.5,
        'disable_dynamic_no_speech_threshold': False,
        'prefix_retention_length': 0.25,
        'vad_threshold': 0.35,
        'disable_dynamic_vad_threshold': False,
        'disable_vad': True,
        'slicing_mode': 'legacy',
    }
    slicer_off = pipeline_runner.create_slicer(base_options)
    assert slicer_off.preprocessor is None

    slicer_on = pipeline_runner.create_slicer({
        **base_options,
        'audio_preprocess': True,
        'disable_audio_agc': False,
        'audio_agc_max_gain_db': 20.0,
        'audio_highpass': True,
    })
    assert isinstance(slicer_on.preprocessor, AudioPreprocessor)
    assert slicer_on.preprocessor.agc_enabled is True
    assert slicer_on.preprocessor.agc_max_gain_db == pytest.approx(20.0)
    assert slicer_on.preprocessor.highpass_enabled is True
