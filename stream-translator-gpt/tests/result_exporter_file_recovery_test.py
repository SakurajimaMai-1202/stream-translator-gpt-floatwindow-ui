import builtins
import queue
import threading

from stream_translator_gpt import result_exporter as module
from stream_translator_gpt.result_exporter import ResultExporter


def make_exporter():
    exporter = ResultExporter(None, None, None, None, None, None, None, False, True)
    exporter.file_queue = queue.SimpleQueue()
    exporter._file_counter = 0
    return exporter


def test_srt_continues_past_1077_and_recovers_from_locked_file(tmp_path, monkeypatch):
    exporter = make_exporter()
    path = tmp_path / 'subtitles.srt'
    real_open = builtins.open
    attempts = 0

    def intermittent_open(file, mode, *args, **kwargs):
        nonlocal attempts
        if mode == 'r+b':
            attempts += 1
            if attempts in (1078, 1079):
                raise PermissionError('temporary file lock')
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(module, 'open', intermittent_open, raising=False)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    for index in range(1, 1501):
        exporter.file_queue.put(f'00:00:01,000 --> 00:00:02,000\n字幕 {index}')
    exporter.file_queue.put(None)
    exporter._write_message_to_file(str(path))
    blocks = path.read_text(encoding='utf-8').strip().split('\n\n')
    assert len(blocks) == 1500
    assert [int(block.splitlines()[0]) for block in blocks] == list(range(1, 1501))
    assert '字幕 1078' in blocks[1077]
    assert '字幕 1500' in blocks[-1]


def test_partial_write_is_rolled_back_before_retry(tmp_path, monkeypatch):
    exporter = make_exporter()
    path = tmp_path / 'subtitles.srt'
    real_open = builtins.open
    failed = False

    class PartialWriter:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def __getattr__(self, name):
            return getattr(self.file, name)

        def write(self, payload):
            nonlocal failed
            if not failed:
                failed = True
                self.file.write(payload[:8])
                raise OSError('temporary disk error')
            return self.file.write(payload)

    def partial_open(file, mode, *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        return PartialWriter(handle) if mode == 'r+b' else handle

    monkeypatch.setattr(module, 'open', partial_open, raising=False)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    exporter.file_queue.put('00:00:01,000 --> 00:00:02,000\n你好')
    exporter.file_queue.put(None)
    exporter._write_message_to_file(str(path))
    assert path.read_text(encoding='utf-8') == '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'


def test_exporter_waits_for_file_queue_to_finish_on_source_end(tmp_path):
    exporter = make_exporter()
    path = tmp_path / 'subtitles.srt'
    exporter.file_queue.put('00:00:01,000 --> 00:00:02,000\n最後一筆')
    exporter._file_thread = threading.Thread(target=exporter._write_message_to_file, args=(str(path),))
    exporter._file_thread.start()
    inputs = queue.SimpleQueue()
    inputs.put(None)
    exporter.loop(inputs)
    assert not exporter._file_thread.is_alive()
    assert '最後一筆' in path.read_text(encoding='utf-8')


def test_deleted_file_is_recreated_with_continuous_numbering(tmp_path, monkeypatch):
    exporter = make_exporter()
    path = tmp_path / 'subtitles.srt'
    real_open = builtins.open
    attempts = 0

    def deleting_open(file, mode, *args, **kwargs):
        nonlocal attempts
        if mode == 'r+b':
            attempts += 1
            if attempts == 2:
                path.unlink()
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(module, 'open', deleting_open, raising=False)
    for text in ('first', 'second', 'third'):
        exporter.file_queue.put(text)
    exporter.file_queue.put(None)
    exporter._write_message_to_file(str(path))
    assert path.read_text(encoding='utf-8') == '2\nsecond\n\n3\nthird\n\n'
    assert exporter._file_counter == 3


def test_missing_parent_is_created(tmp_path):
    exporter = make_exporter()
    path = tmp_path / 'missing' / 'nested' / 'subtitles.srt'
    exporter.file_queue.put('subtitle')
    exporter.file_queue.put(None)
    exporter._write_message_to_file(str(path))
    assert path.read_text(encoding='utf-8') == '1\nsubtitle\n\n'


def test_shutdown_bounds_initial_and_cue_write_retries(tmp_path, monkeypatch, capsys):
    real_open = builtins.open
    for blocked_mode in ('wb', 'r+b'):
        exporter = make_exporter()
        blocked = threading.Event()
        release = threading.Event()
        sleeps = []

        def locked_open(file, mode, *args, **kwargs):
            if mode == blocked_mode:
                blocked.set()
                assert release.wait(2)
                raise PermissionError('permanent lock')
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(module, 'open', locked_open, raising=False)
        monkeypatch.setattr(module.time, 'sleep', lambda seconds: sleeps.append(seconds))
        exporter.file_queue.put('retained cue')
        exporter._file_thread = threading.Thread(
            target=exporter._write_message_to_file,
            args=(str(tmp_path / 'subtitles.srt'),), daemon=True)
        exporter._file_thread.start()
        assert blocked.wait(2)
        inputs = queue.SimpleQueue()
        inputs.put(None)
        shutdown = threading.Thread(target=exporter.loop, args=(inputs,), daemon=True)
        shutdown.start()
        assert exporter._file_stop_event.wait(2)
        release.set()
        shutdown.join(timeout=2)
        assert not shutdown.is_alive()
        assert not exporter._file_thread.is_alive()
        assert sum(sleeps) == 10
    assert '停止重試' in capsys.readouterr().out


def test_recreation_resets_offset_after_partial_write(tmp_path, monkeypatch):
    exporter = make_exporter()
    path = tmp_path / 'subtitles.srt'
    real_open = builtins.open
    attempts = 0

    class FailedWrite:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def write(self, payload):
            self.handle.write(payload[:3])
            raise OSError('partial write')

    def interrupted_open(file, mode, *args, **kwargs):
        nonlocal attempts
        if mode == 'r+b':
            attempts += 1
            if attempts == 3:
                path.unlink()
        handle = real_open(file, mode, *args, **kwargs)
        return FailedWrite(handle) if mode == 'r+b' and attempts == 2 else handle

    monkeypatch.setattr(module, 'open', interrupted_open, raising=False)
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    exporter.file_queue.put('first cue')
    exporter.file_queue.put('second cue')
    exporter.file_queue.put(None)
    exporter._write_message_to_file(str(path))
    assert path.read_bytes() == b'2\nsecond cue\n\n'
