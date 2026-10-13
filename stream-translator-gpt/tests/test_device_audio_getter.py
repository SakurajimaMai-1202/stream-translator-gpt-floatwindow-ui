import queue
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AUDIO_STREAM_GAP, SAMPLE_RATE


class FakeEvent:
    def __init__(self, on_wait=None):
        self.delays = []
        self.stopped = False
        self.on_wait = on_wait

    def set(self):
        self.stopped = True

    def wait(self, delay):
        self.delays.append(delay)
        if self.on_wait:
            self.on_wait()
        return self.stopped


@pytest.fixture
def getter(monkeypatch):
    sd = SimpleNamespace(default=SimpleNamespace(device=[1, 2]),
                         query_devices=lambda index: {'name': 'fake input'})
    monkeypatch.setitem(sys.modules, 'sounddevice', sd)
    return audio_getter.DeviceAudioGetter(1, 10)


@pytest.mark.parametrize('backend', ['sounddevice', 'pyaudiowpatch'])
@pytest.mark.parametrize('failure', ['open', 'read'])
def test_device_failures_are_bounded(getter, monkeypatch, capsys, backend, failure):
    getter.backend = backend
    getter._stop_event = FakeEvent()
    attempts, closed, terminated = [], [], []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        @property
        def active(self):
            return False

        def get_read_available(self):
            return 1

        def read(self, *args, **kwargs):
            raise OSError('device disappeared')

        def stop_stream(self):
            pass

        def close(self):
            closed.append(True)

    def open_stream(*args, **kwargs):
        attempts.append(True)
        if failure == 'open':
            raise OSError('device disappeared')
        return Stream()

    if backend == 'sounddevice':
        monkeypatch.setattr(sys.modules['sounddevice'], 'InputStream', open_stream, raising=False)
    else:
        monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(paFloat32=1))
        getter.p = SimpleNamespace(
            get_device_info_by_index=lambda index: {'defaultSampleRate': SAMPLE_RATE, 'maxInputChannels': 1},
            open=open_stream, terminate=lambda: terminated.append(True))
    output = queue.SimpleQueue()
    with pytest.raises(RuntimeError, match='Audio device unavailable'):
        getter.loop(output)
    assert len(attempts) == getter.MAX_DEVICE_FAILURES
    assert len(closed) == (getter.MAX_DEVICE_FAILURES if failure == 'read' else 0)
    assert not getter.running
    retry_delays = [d for d in getter._stop_event.delays if d != getter.DEVICE_POLL_SECONDS]
    assert retry_delays == [0.25, 0.5, 1.0, 2.0]
    assert 'Audio device unavailable' in capsys.readouterr().out
    if backend == 'pyaudiowpatch':
        assert terminated == [True]
    while not output.empty():
        assert output.get_nowait() is AUDIO_STREAM_GAP  # Failure must propagate, not signal success.


def test_stop_interrupts_retry_backoff(getter, monkeypatch):
    attempts = []
    def fail(**kwargs):
        attempts.append(True)
        raise OSError('missing device')
    monkeypatch.setattr(sys.modules['sounddevice'], 'InputStream', fail, raising=False)
    getter._stop_event = FakeEvent(getter.stop)
    output = queue.SimpleQueue()
    getter.loop(output)
    assert len(attempts) == 1
    assert output.get_nowait() is AUDIO_STREAM_GAP
    assert output.get_nowait() is None


@pytest.mark.parametrize('backend', ['sounddevice', 'pyaudiowpatch'])
def test_stop_wakes_capture_without_waiting_recording_interval(getter, monkeypatch, backend):
    entered = threading.Event()
    closed = []
    errors = []
    getter.backend = backend
    getter.DEVICE_POLL_SECONDS = 10  # stop must wake the event, not wait for polling.

    class Stream:
        active = True
        def __enter__(self):
            entered.set()
            return self

        def __exit__(self, *args):
            closed.append(True)

        def get_read_available(self):
            entered.set()
            return 0

        def is_active(self):
            return True

        def read(self, *args, **kwargs):
            pytest.fail('Must not block reading unavailable audio')

        def stop_stream(self):
            pass

        def close(self):
            closed.append(True)

    if backend == 'sounddevice':
        monkeypatch.setattr(sys.modules['sounddevice'], 'InputStream', lambda **kw: Stream(), raising=False)
    else:
        monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(paFloat32=1))
        getter.p = SimpleNamespace(
            get_device_info_by_index=lambda index: {'defaultSampleRate': SAMPLE_RATE, 'maxInputChannels': 1},
            open=lambda **kw: Stream(), terminate=lambda: None)
    output = queue.SimpleQueue()
    def run():
        try:
            getter.loop(output)
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert entered.wait(2)
    finally:
        getter.stop()
        thread.join(2)
    assert not thread.is_alive()
    assert not errors
    assert closed == [True]
    assert output.get_nowait() is None
    assert output.empty()


def test_loopback_reads_only_available_frames(getter, monkeypatch):
    getter.backend = 'pyaudiowpatch'
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(paFloat32=1))
    reads = []
    class Stream:
        def get_read_available(self):
            return 3

        def read(self, frames, **kwargs):
            reads.append(frames)
            getter.stop()
            return np.zeros(frames, dtype=np.float32).tobytes()

        def stop_stream(self):
            pass

        def close(self):
            pass
    getter.p = SimpleNamespace(
        get_device_info_by_index=lambda index: {'defaultSampleRate': SAMPLE_RATE, 'maxInputChannels': 1},
        open=lambda **kw: Stream(), terminate=lambda: None)
    getter.loop(queue.SimpleQueue())
    assert reads == [3]


@pytest.mark.parametrize('use_scipy', [False, True])
def test_odd_native_reads_preserve_sample_count(getter, monkeypatch, use_scipy):
    getter.backend = 'pyaudiowpatch'
    monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(paFloat32=1))
    if not use_scipy:
        monkeypatch.setitem(sys.modules, 'scipy.signal', None)
    else:
        pytest.importorskip('scipy.signal')
    # Compare arbitrary device read boundaries with identical fixed-block input.
    def capture(read_size):
        getter.running = True
        getter._stop_event = threading.Event()
        getter.remaining_audio = np.array([], dtype=np.float32)
        total = 3 * (audio_getter.SAMPLES_PER_FRAME * 101 + 7)
        source = np.sin(np.arange(total, dtype=np.float32) * 0.01)
        class Stream:
            offset = 0
            def get_read_available(self):
                if self.offset == total:
                    getter.stop()
                    return 0
                return min(read_size, total - self.offset)

            def is_active(self):
                return True

            def read(self, frames, **kwargs):
                data = source[self.offset:self.offset + frames]
                self.offset += frames
                return data.tobytes()

            def stop_stream(self):
                pass

            def close(self):
                pass
        getter.p = SimpleNamespace(
            get_device_info_by_index=lambda index: {'defaultSampleRate': 48000, 'maxInputChannels': 1},
            open=lambda **kw: Stream(), terminate=lambda: None)
        output = queue.SimpleQueue()
        getter.loop(output)
        chunks = []
        while not output.empty():
            item = output.get_nowait()
            if item is not None:
                chunks.append(item)
        chunks.append(getter.remaining_audio)
        result = np.concatenate(chunks)
        assert len(result) == total // 3
        return result
    np.testing.assert_allclose(capture(127), capture(3 * audio_getter.SAMPLES_PER_FRAME))


@pytest.mark.parametrize('backend', ['sounddevice', 'pyaudiowpatch'])
def test_successful_capture_resets_failure_streak_and_backoff(getter, monkeypatch, backend):
    getter.backend = backend
    getter._stop_event = FakeEvent()
    attempts = []
    sample_count = round(SAMPLE_RATE * getter.DEVICE_RECOVERY_SECONDS)
    class Stream:
        def __init__(self, callback=None):
            self.callback = callback
            self.reads = 0

        def __enter__(self):
            self.callback(np.zeros((sample_count, 1), dtype=np.float32), sample_count, None, None)
            return self

        def __exit__(self, *args):
            pass

        @property
        def active(self):
            return False

        def get_read_available(self):
            if self.reads:
                raise OSError('interruption after recovery')
            return sample_count

        def read(self, frames, **kw):
            self.reads += 1
            return np.zeros(frames, dtype=np.float32).tobytes()

        def stop_stream(self):
            pass

        def close(self):
            pass

    def open_stream(**kw):
        attempts.append(True)
        if len(attempts) > getter.MAX_DEVICE_FAILURES + 2:
            getter.stop()
            raise OSError('stopped')
        return Stream(kw.get('callback'))
    if backend == 'sounddevice':
        monkeypatch.setattr(sys.modules['sounddevice'], 'InputStream', open_stream, raising=False)
    else:
        monkeypatch.setitem(sys.modules, 'pyaudiowpatch', SimpleNamespace(paFloat32=1))
        getter.p = SimpleNamespace(
            get_device_info_by_index=lambda index: {'defaultSampleRate': SAMPLE_RATE, 'maxInputChannels': 1},
            open=open_stream, terminate=lambda: None)
    getter.loop(queue.SimpleQueue())
    assert len(attempts) == getter.MAX_DEVICE_FAILURES + 3
    delays = [d for d in getter._stop_event.delays if d != getter.DEVICE_POLL_SECONDS]
    assert delays == [getter.DEVICE_RETRY_DELAY_SECONDS] * (len(attempts) - 1)
