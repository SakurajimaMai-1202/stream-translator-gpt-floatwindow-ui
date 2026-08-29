import pytest
import json
import queue
import numpy as np

from stream_translator_gpt.common import AUDIO_STREAM_GAP, LatencyTrace, TranslationTask
from stream_translator_gpt.audio_slicer import AudioSlicer
from stream_translator_gpt.latency_stats import LatencyWindow
from stream_translator_gpt.result_exporter import ResultExporter, SUBTITLE_EVENT_PREFIX


def test_audio_slicer_creates_latency_trace_when_vad_is_disabled():
    slicer = AudioSlicer(
        min_audio_length=0.01,
        max_audio_length=1.0,
        target_audio_length=0.5,
        continuous_no_speech_threshold=0.1,
        dynamic_no_speech_threshold=False,
        prefix_retention_length=0.0,
        vad_threshold=0.5,
        dynamic_vad_threshold=False,
        disable_vad=True,
    )
    frame = np.zeros(round(16000 * 0.032), dtype=np.float32)
    slicer.put(frame)

    audio, time_range = slicer.slice()

    assert len(audio) == len(frame)
    assert time_range == pytest.approx((0.0, 0.032))
    assert isinstance(slicer.last_latency_trace, LatencyTrace)
    assert slicer.last_latency_trace.audio_duration_ms == pytest.approx(32.0)
    assert slicer.last_latency_trace.slice_emitted_at is not None


def test_audio_slicer_flushes_buffered_speech_at_stream_gap():
    slicer = AudioSlicer(
        min_audio_length=0.05,
        max_audio_length=6.0,
        target_audio_length=4.0,
        continuous_no_speech_threshold=0.5,
        dynamic_no_speech_threshold=False,
        prefix_retention_length=0.0,
        vad_threshold=0.5,
        dynamic_vad_threshold=False,
        disable_vad=True,
    )
    input_queue = queue.SimpleQueue()
    output_queue = queue.SimpleQueue()
    frame = np.ones(512, dtype=np.float32)
    input_queue.put(frame)
    input_queue.put(frame)
    input_queue.put(AUDIO_STREAM_GAP)
    input_queue.put(None)

    slicer.loop(input_queue, output_queue)

    task = output_queue.get()
    assert isinstance(task, TranslationTask)
    assert task.audio.shape == (1024,)
    assert task.time_range == pytest.approx((0.0, 0.064))
    assert output_queue.get() is None


def test_audio_slicer_does_not_discard_valid_weak_speech(monkeypatch):
    class _SequenceVad:
        def __init__(self):
            self.values = iter([0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        def get_speech_prob(self, _audio):
            return next(self.values, 0.0)

        def reset_states(self):
            pass

    monkeypatch.setattr(
        "stream_translator_gpt.audio_slicer.create_vad_adapter",
        lambda *_args, **_kwargs: _SequenceVad(),
    )
    slicer = AudioSlicer(
        min_audio_length=0.05,
        max_audio_length=30.0,
        target_audio_length=4.0,
        continuous_no_speech_threshold=10.0,
        dynamic_no_speech_threshold=False,
        prefix_retention_length=0.0,
        vad_threshold=0.5,
        dynamic_vad_threshold=False,
        disable_vad=False,
    )
    input_queue = queue.SimpleQueue()
    output_queue = queue.SimpleQueue()
    for _ in range(7):
        input_queue.put(np.ones(512, dtype=np.float32))
    input_queue.put(None)

    slicer.loop(input_queue, output_queue)

    task = output_queue.get()
    assert isinstance(task, TranslationTask)
    assert task.audio.shape == (7 * 512,)
    assert output_queue.get() is None


def test_latency_trace_calculates_pipeline_metrics():
    trace = LatencyTrace(
        trace_id="trace-1",
        audio_duration_ms=2000.0,
        capture_started_at=1.0,
        last_speech_at=2.0,
        slice_emitted_at=2.3,
        asr_queued_at=2.3,
        asr_started_at=2.4,
        asr_finished_at=2.9,
        assembler_received_at=2.9,
        assembler_emitted_at=3.1,
        translation_queued_at=3.1,
        translation_started_at=3.2,
        translation_finished_at=3.8,
        subtitle_delivered_at=3.85,
    )
    metrics = trace.metrics()
    assert metrics["trace_id"] == "trace-1"
    assert metrics["speech_to_slice_ms"] == pytest.approx(300.0)
    assert metrics["asr_queue_ms"] == pytest.approx(100.0)
    assert metrics["asr_inference_ms"] == pytest.approx(500.0)
    assert metrics["asr_realtime_factor"] == pytest.approx(0.25)
    assert metrics["assembler_wait_ms"] == pytest.approx(200.0)
    assert metrics["translation_queue_ms"] == pytest.approx(100.0)
    assert metrics["translation_inference_ms"] == pytest.approx(600.0)
    assert metrics["delivery_ms"] == pytest.approx(50.0)
    assert metrics["end_to_end_ms"] == pytest.approx(1850.0)


def test_latency_trace_merge_preserves_full_subtitle_span():
    first = LatencyTrace(trace_id="first", audio_duration_ms=1000.0, capture_started_at=1.0,
                         last_speech_at=1.8, slice_emitted_at=2.0, asr_finished_at=2.4)
    second = LatencyTrace(trace_id="second", merged_trace_ids=["third"], audio_duration_ms=1500.0,
                          capture_started_at=2.0, last_speech_at=3.2, slice_emitted_at=3.4,
                          asr_finished_at=3.8)
    first.merge(second)
    assert first.merged_trace_ids == ["second", "third"]
    assert first.audio_duration_ms == pytest.approx(2500.0)
    assert first.capture_started_at == 1.0
    assert first.last_speech_at == 3.2
    assert first.slice_emitted_at == 3.4
    assert first.asr_finished_at == 3.8


def test_latency_window_reports_recent_p50_and_p95_only():
    window = LatencyWindow(maxlen=3)
    for value in (10.0, 20.0, 30.0, 40.0):
        window.add({"end_to_end_ms": value})
    snapshot = window.snapshot()
    assert snapshot["sample_count"] == 4
    assert snapshot["window_size"] == 3
    assert snapshot["metrics"]["end_to_end_ms"]["latest"] == 40.0
    assert snapshot["metrics"]["end_to_end_ms"]["p50"] == 30.0
    assert snapshot["metrics"]["end_to_end_ms"]["p95"] == pytest.approx(39.0)


def test_result_exporter_emits_trace_and_window(capsys):
    trace = LatencyTrace(
        trace_id="trace-json",
        audio_duration_ms=1000.0,
        last_speech_at=1.0,
        slice_emitted_at=1.2,
        asr_started_at=1.3,
        asr_finished_at=1.6,
        assembler_received_at=1.6,
        assembler_emitted_at=1.7,
        subtitle_delivered_at=None,
    )
    task = TranslationTask(np.zeros(16000, dtype=np.float32), (0.0, 1.0), latency_trace=trace)
    task.transcript = "hello"
    task.asr_latency_ms = 300.0
    input_queue = queue.SimpleQueue()
    input_queue.put(task)
    input_queue.put(None)
    exporter = ResultExporter(
        cqhttp_url=None,
        cqhttp_token=None,
        discord_webhook_url=None,
        telegram_token=None,
        telegram_chat_id=None,
        output_file_path=None,
        proxy=None,
        output_whisper_result=False,
        output_timestamps=False,
        emit_json_events=True,
    )

    exporter.loop(input_queue)

    event_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(SUBTITLE_EVENT_PREFIX))
    payload = json.loads(event_line[len(SUBTITLE_EVENT_PREFIX):])
    assert payload["trace_id"] == "trace-json"
    assert payload["latency_trace"]["asr_inference_ms"] == pytest.approx(300.0)
    assert payload["latency_window"]["sample_count"] == 1
