from datetime import datetime, timezone
import queue

import pytest

from stream_translator_gpt.common import (
    QUEUE_BACKLOG_RECOVERY_THRESHOLD,
    QUEUE_BACKLOG_WARNING_THRESHOLD,
    QueueBacklogMonitor,
    sec2str,
)


@pytest.mark.parametrize('seconds, expected', [
    (0, '00:00:00,000'),
    (1.125, '00:00:01,125'),
    (3661.875, '01:01:01,875'),
    (86399.999, '23:59:59,999'),
    (86400, '24:00:00,000'),
    (90001, '25:00:01,000'),
    (90001.125, '25:00:01,125'),
    (360001.875, '100:00:01,875'),
])
def test_srt_timestamp_total_hours(seconds, expected):
    assert sec2str(seconds) == expected


@pytest.mark.parametrize('seconds', [0.001, 0.999, 59.999, 60, 3599.999,
                                     3600, 43210.123456, 86399.999])
def test_timestamp_below_one_day_matches_legacy(seconds):
    legacy = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime('%H:%M:%S')
    legacy += ',' + f'{int(seconds * 1000 % 1000):03d}'
    assert sec2str(seconds) == legacy


class FakeQueue:
    depth = 0

    def qsize(self):
        return self.depth


def test_backlog_warning_crossings_have_hysteresis(capsys):
    pending = FakeQueue()
    monitor = QueueBacklogMonitor(pending, 'slicer -> ASR')
    high = QUEUE_BACKLOG_WARNING_THRESHOLD
    low = QUEUE_BACKLOG_RECOVERY_THRESHOLD
    assert low < high
    for depth in (0, high, high + 1, high + 20, high, low + 1, high + 1):
        pending.depth = depth
        monitor.check()
    output = capsys.readouterr().out
    assert output.count('Queue backlog') == 1
    assert 'slicer -> ASR' in output
    assert str(high + 1) in output

    pending.depth = low
    monitor.check()
    pending.depth = high + 1
    monitor.check()
    monitor.check()
    assert capsys.readouterr().out.count('Queue backlog') == 1


def test_backlog_stage_state_is_independent(capsys):
    pending = FakeQueue()
    pending.depth = QUEUE_BACKLOG_WARNING_THRESHOLD + 1
    asr = QueueBacklogMonitor(pending, 'slicer -> ASR')
    translation = QueueBacklogMonitor(pending, 'segmenter -> translation')
    asr.check()
    translation.check()
    asr.check()
    output = capsys.readouterr().out
    assert output.count('Queue backlog') == 2
    assert 'slicer -> ASR' in output
    assert 'segmenter -> translation' in output


@pytest.mark.parametrize('pending', [object(), type('UnsupportedQueue', (), {
    'qsize': lambda self: (_ for _ in ()).throw(NotImplementedError()),
})()])
def test_backlog_without_qsize_is_optional(pending, capsys):
    QueueBacklogMonitor(pending, 'ASR').check()
    assert capsys.readouterr().out == ''


def test_monitor_does_not_remove_audio_or_end_marker(capsys):
    pending = queue.SimpleQueue()
    items = [object() for _ in range(QUEUE_BACKLOG_WARNING_THRESHOLD + 1)] + [None]
    for item in items:
        pending.put(item)
    monitor = QueueBacklogMonitor(pending, 'stream reader -> audio getter')
    monitor.check()
    assert capsys.readouterr().out.count('Queue backlog') == 1
    assert [pending.get_nowait() for _ in items] == items
    assert pending.empty()
    monitor.check()


@pytest.mark.parametrize('translate', [False, True])
def test_pipeline_checks_each_stage_without_duplicate_export_queue(monkeypatch, translate):
    from types import SimpleNamespace
    from stream_translator_gpt import pipeline_runner

    monitors = []

    class Monitor:
        def __init__(self, pending, stage):
            self.pending = pending
            self.stage = stage
            self.checks = 0
            monitors.append(self)

        def check(self):
            self.checks += 1

    class Workers:
        def start(self, *args, **kwargs):
            alive = iter([True, False])
            return SimpleNamespace(is_alive=lambda: next(alive))

        def raise_if_failed(self):
            pass

    worker = SimpleNamespace(loop=lambda **_: None, stop=lambda: None,
                             llm_client=SimpleNamespace(reset_context=lambda: None))
    monkeypatch.setattr(pipeline_runner.ClientPool, 'init', lambda **_: None)
    for factory in ('create_audio_getter', 'create_slicer',
                    'create_subtitle_segmenter', 'create_exporter'):
        monkeypatch.setattr(pipeline_runner, factory, lambda *_: worker)
    monkeypatch.setattr(pipeline_runner, 'create_translator',
                        lambda *_: worker if translate else None)
    monkeypatch.setattr(pipeline_runner, 'PipelineWorkers', Workers)
    from stream_translator_gpt import common
    monkeypatch.setattr(common, 'QueueBacklogMonitor', Monitor)
    monkeypatch.setattr(pipeline_runner.time, 'sleep', lambda _: None)
    options = {'translation_prompt': 'translate'} if translate else {}
    assert pipeline_runner.run_inprocess_pipeline('test.wav', options, worker) == 0
    stages = [monitor.stage for monitor in monitors]
    assert stages == ['audio getter -> slicer', 'slicer -> ASR', 'ASR -> segmenter',
                      'segmenter -> translation' if translate else 'segmenter -> exporter'] + (
                          ['translation -> exporter'] if translate else [])
    assert all(monitor.checks == 1 for monitor in monitors)
    assert len({id(monitor.pending) for monitor in monitors}) == len(monitors)


@pytest.mark.parametrize('translate', [False, True])
def test_normal_main_path_reports_backlogs(monkeypatch, capsys, translate):
    from types import SimpleNamespace
    from stream_translator_gpt import main as engine_main

    class Worker:
        def __init__(self, *args, **kwargs):
            self.stopped = False

        def loop(self, **kwargs):
            pass

        def stop(self):
            self.stopped = True

    class Client(Worker):
        LLM_TYPE = engine_main.LLMClient.LLM_TYPE

    class Workers:
        def start(self, *args, **kwargs):
            # No real capture/model threads: simulate each producer's backlog.
            if 'output_queue' in kwargs:
                for _ in range(QUEUE_BACKLOG_WARNING_THRESHOLD + 1):
                    kwargs['output_queue'].put(object())
            alive = iter([True, True, False])
            return SimpleNamespace(is_alive=lambda: next(alive))

        def raise_if_failed(self):
            pass

    getter = Worker()
    monkeypatch.setattr(engine_main, 'LocalFileAudioGetter', lambda **_: getter)
    for constructor in ('AudioSlicer', 'OpenaiWhisper', 'FasterWhisper',
                        'ResultExporter', 'SubtitleSegmenter', 'ParallelTranslator'):
        monkeypatch.setattr(engine_main, constructor, Worker)
    monkeypatch.setattr(engine_main, 'LLMClient', Client)
    monkeypatch.setattr(engine_main, 'PipelineWorkers', Workers)
    monkeypatch.setattr(engine_main.ApiKeyPool, 'init', lambda **_: None)
    monkeypatch.setattr(engine_main, 'configure_utf8_stdio', lambda: None)
    monkeypatch.setattr(engine_main.time, 'sleep', lambda _: None)
    engine_main.main('test.wav', translation_prompt='translate' if translate else '')
    lines = [line for line in capsys.readouterr().out.splitlines()
             if line.startswith('[WARNING] Queue backlog')]
    stages = ['audio getter -> slicer', 'slicer -> ASR', 'ASR -> segmenter',
              'segmenter -> translation' if translate else 'segmenter -> exporter']
    if translate:
        stages.append('translation -> exporter')
    assert len(lines) == len(stages)
    assert all(any(f'at {stage}:' in line for line in lines) for stage in stages)
    assert getter.stopped
