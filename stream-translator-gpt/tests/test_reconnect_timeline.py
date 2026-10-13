"""Offline producer-to-slicer timeline regressions (no models or processes)."""
import queue
from types import SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt import audio_getter, audio_slicer
from stream_translator_gpt.common import (
    AUDIO_STREAM_GAP, AudioSourceQueue, FRAME_DURATION, SAMPLES_PER_FRAME,
)


class Clock:
    now = 100.0

    def monotonic(self):
        return self.now


def capture(monkeypatch, source, reconnects, queue_factory=AudioSourceQueue, metadata=True,
            stall_seconds=0.0):
    clock = Clock()
    monkeypatch.setattr(audio_getter.time, 'monotonic', clock.monotonic)
    process = SimpleNamespace(poll=lambda: 0)
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *args: (process, process))
    getter = audio_getter.StreamAudioGetter.__new__(audio_getter.StreamAudioGetter)
    getter.url = 'fake://offline'
    getter.format = getter.cookies = getter.proxy = getter.temp_dir = ''
    getter.running = True
    getter.realtime_throttle = False
    getter._check_stream_error = lambda *args: None
    getter._close_stream = lambda: None
    getter._stop_event = SimpleNamespace(wait=lambda delay: False)
    statuses = iter([source] * (reconnects + 1) + ['ended'])
    getter._source_status = lambda: next(statuses)
    attempts = 0

    def frames():
        nonlocal attempts
        if attempts:
            clock.now += 5.0
        attempts += 1
        clock.now += FRAME_DURATION
        yield np.ones(SAMPLES_PER_FRAME, dtype=np.float32).tobytes()
        if stall_seconds and attempts <= reconnects:
            clock.now += stall_seconds
            raise TimeoutError("fake stalled read")

    getter._read_stream_frames = frames
    output = queue_factory()
    getter.loop(output)
    items = []
    while not output.empty():
        items.append(output.get_with_timeline() if metadata else output.get())
    return items


class NativeVAD:
    def process_native_events(self, audio):
        return [(audio, SimpleNamespace(is_speech_start=True, is_speech=True,
                                       is_speech_end=False))]

    def take_pending_audio(self):
        return np.array([], dtype=np.float32)

    def reset_states(self):
        pass


def slice_items(monkeypatch, mode, items):
    monkeypatch.setattr(audio_slicer, 'create_vad_adapter', lambda *args: NativeVAD())
    slicer = audio_slicer.AudioSlicer(
        min_audio_length=0, max_audio_length=10, target_audio_length=1,
        continuous_no_speech_threshold=1, dynamic_no_speech_threshold=False,
        prefix_retention_length=0, vad_threshold=0.5, dynamic_vad_threshold=False,
        disable_vad=mode == 'legacy', slicing_mode=mode,
    )
    incoming, outgoing = AudioSourceQueue(), queue.SimpleQueue()
    for item in items:
        if isinstance(item, tuple):
            audio, advance = item
            incoming.put(audio, timeline_advance=advance)
        else:
            incoming.put(item)
    slicer.loop(incoming, outgoing)
    tasks = []
    while not outgoing.empty():
        task = outgoing.get()
        if task is not None:
            tasks.append(task)
    return slicer, tasks


@pytest.mark.parametrize('mode', ['legacy', 'omnivad_native'])
def test_live_reconnects_accumulate_missing_time(monkeypatch, mode):
    items = capture(monkeypatch, 'live', reconnects=2)
    advances = [advance for _, advance in items if advance]
    assert advances == pytest.approx([5.0, 5.0])
    slicer, tasks = slice_items(monkeypatch, mode, items)
    assert len(tasks) == 3
    assert slicer.last_slice_second == pytest.approx(10 + 3 * FRAME_DURATION)
    expected = [
        (0, FRAME_DURATION),
        (5 + FRAME_DURATION, 5 + 2 * FRAME_DURATION),
        (10 + 2 * FRAME_DURATION, 10 + 3 * FRAME_DURATION),
    ]
    for task, time_range in zip(tasks, expected):
        assert task.time_range == pytest.approx(time_range)


@pytest.mark.parametrize('mode', ['legacy', 'omnivad_native'])
@pytest.mark.parametrize('source', ['finite', 'live'])
def test_normal_eof_gap_does_not_advance(monkeypatch, mode, source):
    items = capture(monkeypatch, source, reconnects=0)
    assert any(item is AUDIO_STREAM_GAP for item, _ in items)
    assert all(advance == 0 for _, advance in items)
    slicer, tasks = slice_items(monkeypatch, mode, items)
    assert slicer.last_slice_second == pytest.approx(FRAME_DURATION)


@pytest.mark.parametrize('mode', ['legacy', 'omnivad_native'])
@pytest.mark.parametrize('gap', [False, True])
def test_media_time_without_live_reconnect(monkeypatch, mode, gap):
    clock = Clock()
    monkeypatch.setattr(audio_slicer.time, 'monotonic', clock.monotonic)
    frame = np.ones(SAMPLES_PER_FRAME, dtype=np.float32)
    items = [frame] + ([AUDIO_STREAM_GAP] if gap else []) + [frame, None]
    clock.now += 60
    slicer, tasks = slice_items(monkeypatch, mode, items)
    assert slicer.last_slice_second == pytest.approx(2 * FRAME_DURATION)


@pytest.mark.parametrize('queue_factory', [queue.SimpleQueue, AudioSourceQueue])
def test_getter_preserves_public_queue_protocol(monkeypatch, queue_factory):
    items = capture(monkeypatch, 'live', reconnects=2,
                    queue_factory=queue_factory, metadata=False)
    assert len(items) == 7
    for index in (0, 2, 4):
        assert type(items[index]) is np.ndarray
        assert items[index].shape == (SAMPLES_PER_FRAME,)
        assert items[index + 1] is AUDIO_STREAM_GAP
    assert items[-1] is None


def test_queue_metadata_is_per_frame_and_per_pipeline():
    first, second = AudioSourceQueue(), AudioSourceQueue()
    frame = np.ones(SAMPLES_PER_FRAME, dtype=np.float32)
    first.put_nowait(AUDIO_STREAM_GAP)
    first.put(frame, timeline_advance=5)
    first.put(frame, timeline_advance=7)
    first.put_nowait(None)
    second.put(frame)
    assert first.get_nowait() is AUDIO_STREAM_GAP
    audio, advance = first.get_with_timeline()
    assert audio is frame and advance == 5
    audio, advance = second.get_with_timeline()
    assert audio is frame and advance == 0
    audio, advance = first.get_with_timeline()
    assert audio is frame and advance == 7
    assert first.get_nowait() is None
    with pytest.raises(queue.Empty):
        first.get_nowait()


@pytest.mark.parametrize('mode', ['legacy', 'omnivad_native'])
def test_stalled_read_time_is_included_in_reconnect_gap(monkeypatch, mode):
    # Each read waits eight seconds before raising; reopening then takes five.
    # Two reconnects also verify that the receipt anchor resets after recovery.
    items = capture(monkeypatch, 'live', reconnects=2, stall_seconds=8.0)
    advances = [advance for _, advance in items if advance]
    assert advances == pytest.approx([13.0, 13.0])
    slicer, tasks = slice_items(monkeypatch, mode, items)
    assert len(tasks) == 3
    for index, task in enumerate(tasks):
        start = index * (13.0 + FRAME_DURATION)
        assert task.time_range == pytest.approx((start, start + FRAME_DURATION))
    assert slicer.last_slice_second == pytest.approx(26.0 + 3 * FRAME_DURATION)
