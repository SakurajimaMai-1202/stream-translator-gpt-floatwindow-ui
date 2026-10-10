import queue
import threading

import numpy as np
import pytest

from stream_translator_gpt import process_audio_capture as capture
from stream_translator_gpt import process_audio_targets as targets


def test_pcm_packet_boundaries_match_continuous_filtering():
    rng = np.random.default_rng(42)
    stereo = rng.normal(size=48000 * 2).astype(np.float32)
    whole = np.concatenate(capture.PCMAdapter().frames(stereo))
    adapter = capture.PCMAdapter()
    pieces = []
    start = 0
    for frames in [7, 511, 3, 4001, 1600, 17, 997, 4500, 3, 19999, 16362]:
        end = min(len(stereo), start + frames * 2)
        pieces.extend(adapter.frames(stereo[start:end]))
        start = end
    if start < len(stereo):
        pieces.extend(adapter.frames(stereo[start:]))
    combined = np.concatenate(pieces)
    np.testing.assert_allclose(combined, whole, atol=1e-6)
    assert combined.dtype == np.float32
    assert all(len(frame) == 512 for frame in pieces)
    assert len(combined) == 31 * 512
    assert len(adapter.remaining) == 128


def test_pcm_decimator_rejects_high_frequency_alias():
    t = np.arange(48000) / 48000
    def output(freq):
        signal = np.sin(2 * np.pi * freq * t).astype(np.float32)
        stereo = np.repeat(signal[:, None], 2, axis=1).ravel()
        mono = np.concatenate(capture.PCMAdapter().frames(stereo))[512:]
        return np.sqrt(np.mean(mono ** 2))
    assert output(1000) > 0.6
    assert output(12000) < 0.005


def test_capture_error_closes_and_ends_pipeline(monkeypatch):
    from stream_translator_gpt.common import AUDIO_STREAM_GAP
    class FakeNative:
        dropped_frames = 0
        closed = False
        def __init__(self, *_, **__):
            self.calls = 0
        def start(self):
            pass
        def read(self):
            self.calls += 1
            if self.calls == 1:
                self.dropped_frames = 25
                return np.ones(4096, dtype=np.float32)
            raise RuntimeError('target exited')
        def close(self):
            self.closed = True
        def stop(self):
            pass
    monkeypatch.setattr(capture, 'NativeCapture', FakeNative)
    getter = capture.ProcessAudioGetter(12, '1234')
    output = queue.SimpleQueue()
    with pytest.raises(RuntimeError, match='target exited'):
        getter.loop(output)
    assert getter.capture.closed
    entries = []
    while not output.empty():
        entries.append(output.get())
    assert entries[0] is AUDIO_STREAM_GAP
    assert entries[-1] is None
    assert all(len(entry) == 512 for entry in entries[1:-1])


def test_silent_capture_stop_unblocks_and_closes(monkeypatch):
    class FakeNative:
        dropped_frames = 0
        closed = False
        def __init__(self, *_, **__):
            self.wait = threading.Event()
            self.reading = threading.Event()
        def start(self):
            pass
        def read(self):
            self.reading.set()
            self.wait.wait(1)
            return np.empty(0, dtype=np.float32)
        def stop(self):
            self.wait.set()
        def close(self):
            self.closed = True
    monkeypatch.setattr(capture, 'NativeCapture', FakeNative)
    getter = capture.ProcessAudioGetter(12, '1234')
    output = queue.SimpleQueue()
    worker = threading.Thread(target=getter.loop, args=(output,))
    worker.start()
    assert getter.capture.reading.wait(1)
    getter.stop()
    worker.join(1)
    assert not worker.is_alive()
    assert getter.capture.closed
    assert output.get() is None


def test_adapter_init_failure_does_not_open_capture(monkeypatch):
    opened = []
    monkeypatch.setattr(capture, 'NativeCapture', lambda *_, **__: opened.append(True))
    def fail():
        raise ImportError('missing scipy')
    monkeypatch.setattr(capture, 'PCMAdapter', fail)
    with pytest.raises(ImportError):
        capture.ProcessAudioGetter(12, '1234')
    assert not opened


def test_target_reuse_is_rejected(monkeypatch):
    monkeypatch.setattr(targets, 'platform_support', lambda: (True, ''))
    monkeypatch.setattr(targets, '_apis', lambda: (object(), object()))
    monkeypatch.setattr(targets, '_identity', lambda *_: {'process_id': 12, 'process_start_time': '5678'})
    with pytest.raises(ValueError, match='已更換'):
        targets.validate_process_target(12, '1234')


def test_browser_root_does_not_cross_image_or_creation_time(monkeypatch):
    browser = {'process_id': 12, 'process_start_time': '500', 'process_name': 'chrome.exe', 'path': r'C:\browser\chrome.exe'}
    older = browser | {'process_id': 5, 'process_start_time': '300'}
    launcher = older | {'process_id': 2, 'process_name': 'launcher.exe', 'path': r'C:\launcher.exe', 'process_start_time': '200'}
    monkeypatch.setattr(targets, '_identity', lambda pid, _: {5: older, 2: launcher}[pid])
    assert targets._capture_root(browser, {12: 5, 5: 2}, None) == older
    newer = older | {'process_start_time': '600'}
    monkeypatch.setattr(targets, '_identity', lambda *_: newer)
    assert targets._capture_root(browser, {12: 5}, None) == browser


def test_generic_python_host_does_not_capture_parent():
    identity = {'process_id': 12, 'process_name': 'python.exe'}
    assert targets._capture_root(identity, {12: 5}, None) == identity
