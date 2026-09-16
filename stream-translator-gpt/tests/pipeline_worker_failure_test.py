import pytest

from stream_translator_gpt.common import PipelineWorkers
from stream_translator_gpt import pipeline_runner


def test_worker_failure_reaches_owner_with_original_cause():
    workers = PipelineWorkers()
    original = RuntimeError('mat1 and mat2 must have the same dtype')

    def fail():
        raise original

    workers.start(fail).join(timeout=2)
    with pytest.raises(RuntimeError, match='Pipeline worker') as caught:
        workers.raise_if_failed()
    assert caught.value.__cause__ is original


@pytest.mark.parametrize('fail', [True, False])
def test_pipeline_does_not_wait_forever_after_asr_failure(monkeypatch, fail):
    class Getter:
        stopped = False

        def loop(self, output_queue):
            output_queue.put('audio')
            output_queue.put(None)

        def stop(self):
            self.stopped = True

    class Forward:
        def loop(self, input_queue, output_queue):
            while True:
                item = input_queue.get()
                output_queue.put(item)
                if item is None:
                    return

    class ASR(Forward):
        def loop(self, input_queue, output_queue):
            if fail:
                input_queue.get()
                raise RuntimeError('ASR failed')
            super().loop(input_queue, output_queue)

    class Exporter:
        def loop(self, input_queue):
            while input_queue.get() is not None:
                pass

    getter = Getter()
    monkeypatch.setattr(pipeline_runner.ClientPool, 'init', lambda **_: None)
    monkeypatch.setattr(pipeline_runner, 'create_audio_getter', lambda *_: getter)
    monkeypatch.setattr(pipeline_runner, 'create_slicer', lambda *_: Forward())
    monkeypatch.setattr(pipeline_runner, 'create_subtitle_segmenter', lambda *_: Forward())
    monkeypatch.setattr(pipeline_runner, 'create_translator', lambda *_: None)
    monkeypatch.setattr(pipeline_runner, 'create_exporter', lambda *_: Exporter())
    if fail:
        with pytest.raises(RuntimeError, match='ASR failed'):
            pipeline_runner.run_inprocess_pipeline('test.wav', {}, ASR())
    else:
        assert pipeline_runner.run_inprocess_pipeline('test.wav', {}, ASR()) == 0
    assert getter.stopped
