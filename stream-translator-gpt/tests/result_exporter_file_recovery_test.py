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
