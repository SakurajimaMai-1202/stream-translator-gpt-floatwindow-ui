import queue
import numpy as np
from stream_translator_gpt.audio_slicer import AudioSlicer
from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.subtitle_segmenter import SubtitleSegmenter


def test_short_endpoint_wait_has_a_hard_sample_budget():
    slicer=AudioSlicer.__new__(AudioSlicer)
    slicer.audio_buffer=[np.zeros(16000,dtype=np.float32)]
    slicer.min_audio_length=.5;slicer.max_audio_length=6
    slicer.slicing_mode='omnivad_native';slicer.speech_count=1
    slicer._native_end_pending=True;slicer._native_end_sample=16000
    slicer._native_total_samples=16000
    slicer.native_short_segment_target=1.5;slicer.native_short_segment_wait=.35
    assert not slicer.should_slice()
    slicer.audio_buffer.append(np.zeros(5600,dtype=np.float32))
    slicer._native_total_samples+=5600
    assert slicer.should_slice()
    slicer._native_end_pending=False
    assert not slicer.should_slice()


def test_long_endpoint_and_maximum_are_not_delayed():
    slicer=AudioSlicer.__new__(AudioSlicer)
    slicer.audio_buffer=[np.zeros(32000,dtype=np.float32)]
    slicer.min_audio_length=.5;slicer.max_audio_length=6
    slicer.slicing_mode='omnivad_native';slicer.speech_count=1
    slicer._native_end_pending=True;slicer._native_end_sample=32000
    slicer._native_total_samples=32000
    slicer.native_short_segment_target=1.5;slicer.native_short_segment_wait=.35
    assert slicer.should_slice()
    slicer._native_end_pending=False
    slicer.audio_buffer=[np.zeros(100000,dtype=np.float32)]
    assert slicer.should_slice()


def test_japanese_dependent_tail_is_joined_despite_asr_period():
    first=TranslationTask(np.zeros(1),(0,1));first.transcript='私と世界が。';first.raw_transcript=first.transcript
    second=TranslationTask(np.zeros(1),(1.1,2));second.transcript='初めて触れ合った。';second.raw_transcript=second.transcript
    incoming=queue.SimpleQueue();outgoing=queue.SimpleQueue()
    for item in (first,second,None):incoming.put(item)
    SubtitleSegmenter(deduplicate_overlap=False).loop(incoming,outgoing)
    assert outgoing.get().transcript=='私と世界が初めて触れ合った。'
    assert outgoing.get() is None


def test_forced_boundary_does_not_look_complete():
    task=TranslationTask(np.zeros(1),(0,6));task.transcript='私は息。';task.audio_boundary='max_length'
    assert not SubtitleSegmenter._is_complete(task)
    task.audio_boundary='speech_end'
    assert SubtitleSegmenter._is_complete(task)


def test_english_and_complete_japanese_keep_fast_path():
    for text in ['今日は晴れです。','This is finished.']:
        task=TranslationTask(np.zeros(1),(0,1));task.transcript=text
        assert SubtitleSegmenter._is_complete(task)


def test_discarded_fragments_do_not_restart_wait_budget(monkeypatch):
    from stream_translator_gpt import subtitle_segmenter as module
    clock=[1.0]
    monkeypatch.setattr(module.time,'perf_counter',lambda:clock[0])
    first=TranslationTask(np.zeros(1),(0,1));first.transcript='私と世界が。'
    punctuation=TranslationTask(np.zeros(1),(1,1.1));punctuation.transcript='。'
    class Input:
        count=0
        def get(self,timeout=None):
            self.count+=1
            if self.count==1:return first
            if timeout is None:return None
            assert timeout<=.2
            if self.count in (2,3):
                clock[0]+=.08
                return punctuation
            clock[0]+=timeout
            raise queue.Empty()
    output=queue.SimpleQueue()
    SubtitleSegmenter(assembler_wait_ms=200).loop(Input(),output)
    assert output.get() is first
    assert output.get() is None
    assert clock[0]<=1.200001


def test_merge_preserves_first_arrival_and_total_wait(monkeypatch):
    from stream_translator_gpt import subtitle_segmenter as module
    clock=[1.0]
    monkeypatch.setattr(module.time,'perf_counter',lambda:clock[0])
    first=TranslationTask(np.zeros(1),(0,1));first.transcript='私と世界が。'
    second=TranslationTask(np.zeros(1),(1,1.1));second.transcript='新しい世界に。'
    class Input:
        count=0
        def get(self,timeout=None):
            self.count+=1
            if self.count==1:return first
            if self.count==2:
                clock[0]+=.15
                return second
            if timeout is not None:
                assert timeout <= .050001
                clock[0]+=timeout
                raise queue.Empty()
            return None
    output=queue.SimpleQueue()
    SubtitleSegmenter(assembler_wait_ms=200,deduplicate_overlap=False).loop(Input(),output)
    merged=output.get()
    assert merged.transcript=='私と世界が新しい世界に。'
    assert abs(merged.latency_trace.metrics()['assembler_wait_ms']-200)<.001
    assert output.get() is None


def test_span_cap_is_emitted_without_useless_wait():
    first=TranslationTask(np.zeros(1),(0,6.01));first.transcript='続いている話'
    first.audio_boundary='max_length'
    class Input:
        count=0
        def get(self,timeout=None):
            assert timeout is None, 'A capped span cannot merge with subsequent audio'
            self.count+=1
            return first if self.count==1 else None
    output=queue.SimpleQueue()
    SubtitleSegmenter(assembler_wait_ms=200,assembler_max_duration=6).loop(Input(),output)
    assert output.get() is first
    assert output.get() is None
    assert first.latency_trace.metrics()['assembler_wait_ms'] < 50
