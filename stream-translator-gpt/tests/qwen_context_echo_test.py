from types import SimpleNamespace

import numpy as np

from stream_translator_gpt.audio_transcriber import Qwen3ASRTranscriber


class _StubModel:
    def __init__(self, texts):
        self.texts = iter(texts)
        self.calls = []

    def transcribe(self, audio, context, language):
        self.calls.append((audio, context, language))
        text = next(self.texts)
        # Exercise both model result formats.
        if len(self.calls) == 1:
            return [{'text': text}]
        return [SimpleNamespace(text=text)]


def _make_transcriber(texts, constant_prompt=''):
    transcriber = Qwen3ASRTranscriber.__new__(Qwen3ASRTranscriber)
    transcriber.model = _StubModel(texts)
    transcriber.language = 'Japanese'
    transcriber.rms_threshold = 0.005
    transcriber.constant_prompt = constant_prompt
    return transcriber


def _transcribe(transcriber, prompt, audio=None):
    if audio is None:
        audio = np.ones(160, dtype=np.float32) * 0.1
    return transcriber.transcribe(audio, initial_prompt=prompt)


def test_context_echo_is_replaced_by_context_free_result():
    transcriber = _make_transcriber(['ご飯かな。', 'ねえ、'])

    assert _transcribe(transcriber, 'ご飯かな。') == ('ねえ、', None)
    assert [call[1] for call in transcriber.model.calls] == ['ご飯かな。', '']
    first_audio, _, language = transcriber.model.calls[0]
    retry_audio = transcriber.model.calls[1][0]
    assert retry_audio[0] is first_audio[0]
    assert retry_audio[1] == first_audio[1]
    assert language == transcriber.model.calls[1][2] == 'Japanese'
    assert transcriber.context_echo_retries == 1


def test_genuine_repeat_keeps_first_result():
    transcriber = _make_transcriber(['ご飯かな。', 'ご飯かな。'])

    assert _transcribe(transcriber, 'ご飯かな。') == ('ご飯かな。', None)
    assert len(transcriber.model.calls) == 2
    assert transcriber.context_echo_retries == 1


def test_substring_of_context_is_retried():
    transcriber = _make_transcriber(['いくよ。ご飯かな。', 'はい。'])

    assert _transcribe(transcriber, 'していくよ。 ご飯かな。') == ('はい。', None)
    assert len(transcriber.model.calls) == 2


def test_unrelated_result_is_not_retried():
    transcriber = _make_transcriber(['今日は猫がカリカリしてる。'])

    assert _transcribe(transcriber, 'ご飯かな。') == ('今日は猫がカリカリしてる。', None)
    assert len(transcriber.model.calls) == 1
    assert transcriber.context_echo_retries == 0


def test_empty_prompt_is_not_retried():
    for prompt in (None, ''):
        transcriber = _make_transcriber(['はい。'])

        assert _transcribe(transcriber, prompt) == ('はい。', None)
        assert len(transcriber.model.calls) == 1
        assert transcriber.model.calls[0][1] == ''


def test_empty_first_result_is_not_retried():
    transcriber = _make_transcriber([''])

    assert _transcribe(transcriber, 'ご飯かな。') == ('', None)
    assert len(transcriber.model.calls) == 1


def test_audio_below_rms_gate_skips_model():
    transcriber = _make_transcriber([])

    assert _transcribe(transcriber, 'ご飯かな。', np.zeros(160, dtype=np.float32)) == ('', None)
    assert transcriber.model.calls == []
    assert transcriber.context_echo_retries == 0


def test_retry_preserves_exact_constant_prompt():
    transcriber = _make_transcriber(['ご飯かな。', 'ねえ、'], constant_prompt='用語：猫、ご飯。')
    prompt = '用語：猫、ご飯。 ご飯かな。'

    assert _transcribe(transcriber, prompt) == ('ねえ、', None)
    assert [call[1] for call in transcriber.model.calls] == [prompt, '用語：猫、ご飯。']


def test_constant_only_prompt_is_not_retried():
    transcriber = _make_transcriber(['ご飯かな。'], constant_prompt='ご飯かな。')

    assert _transcribe(transcriber, 'ご飯かな。') == ('ご飯かな。', None)
    assert len(transcriber.model.calls) == 1
    assert transcriber.context_echo_retries == 0


def test_normalization_ignores_punctuation_symbols_and_whitespace():
    transcriber = _make_transcriber(['ご飯、かな。', 'ご飯 かな！'])

    assert _transcribe(transcriber, '★ ご飯_かな。') == ('ご飯、かな。', None)
    assert len(transcriber.model.calls) == 2


def test_punctuation_only_result_is_not_retried():
    transcriber = _make_transcriber(['。'])

    assert _transcribe(transcriber, 'ご飯かな。') == ('。', None)
    assert len(transcriber.model.calls) == 1


def test_empty_retry_result_is_used():
    transcriber = _make_transcriber(['うん。', ''])

    assert _transcribe(transcriber, 'うん。') == ('', None)
    assert len(transcriber.model.calls) == 2


def test_retry_is_not_repeated_when_second_result_is_another_context_substring():
    transcriber = _make_transcriber(['ご飯かな。', 'うん。'])

    assert _transcribe(transcriber, 'うん。 ご飯かな。') == ('うん。', None)
    assert len(transcriber.model.calls) == 2


def test_retry_counter_accumulates_across_calls():
    transcriber = _make_transcriber(['はい次。', 'ねえ、', 'はい次。', 'はい次。'])

    assert _transcribe(transcriber, 'はい次。') == ('ねえ、', None)
    assert _transcribe(transcriber, 'はい次。') == ('はい次。', None)
    assert transcriber.context_echo_retries == 2
