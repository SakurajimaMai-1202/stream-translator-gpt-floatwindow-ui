from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt import asr_preload
from stream_translator_gpt.sherpa_onnx_models import SHERPA_CPU_MODELS, resolve_sherpa_model_dir
from stream_translator_gpt.sherpa_onnx_transcriber import SherpaOnnxTranscriber


class _FakeStream:
    def __init__(self):
        self.result = SimpleNamespace(text=" CPU transcript ", tokens=[1, 2])
        self.waveform = None

    def accept_waveform(self, sample_rate, samples):
        self.waveform = (sample_rate, samples)


class _FakeRecognizer:
    calls = []

    def __init__(self, config=None, **kwargs):
        self.calls.append(("constructor", config, kwargs))

    @classmethod
    def _factory(cls, name, **kwargs):
        cls.calls.append((name, kwargs))
        return cls()

    from_transducer = classmethod(lambda cls, **kwargs: cls._factory("transducer", **kwargs))
    from_sense_voice = classmethod(lambda cls, **kwargs: cls._factory("sense_voice", **kwargs))
    from_funasr_nano = classmethod(lambda cls, **kwargs: cls._factory("funasr_nano", **kwargs))
    from_qwen3_asr = classmethod(lambda cls, **kwargs: cls._factory("qwen3_asr", **kwargs))

    def create_stream(self):
        self.stream = _FakeStream()
        return self.stream

    def decode_stream(self, stream):
        assert stream is self.stream


class _Config:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


FAKE_SHERPA = SimpleNamespace(
    OfflineRecognizer=_FakeRecognizer,
    OfflineModelConfig=_Config,
    OfflineRecognizerConfig=_Config,
    OfflineNemoEncDecCtcModelConfig=_Config,
)


def _materialize(root: Path, model_id: str) -> None:
    spec = SHERPA_CPU_MODELS[model_id]
    for relative in spec.required_paths:
        path = root / spec.bundle / relative
        if Path(relative).suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        else:
            path.mkdir(parents=True, exist_ok=True)


@pytest.mark.parametrize("model_id", SHERPA_CPU_MODELS)
def test_all_cpu_models_build_and_transcribe_with_one_adapter(tmp_path, model_id):
    _materialize(tmp_path, model_id)
    transcriber = SherpaOnnxTranscriber(
        model=model_id, language="ja", model_root=tmp_path, num_threads=2,
        sherpa_module=FAKE_SHERPA, transcription_filters="",
    )
    text, tokens = transcriber.transcribe(np.zeros(1600, dtype=np.float32))
    assert text == "CPU transcript"
    assert tokens == [1, 2]
    assert transcriber.recognizer.stream.waveform[0] == 16000


def test_missing_bundle_has_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="CPU sherpa-onnx model is not installed"):
        resolve_sherpa_model_dir("Qwen/Qwen3-ASR-0.6B", tmp_path)


def test_cpu_preload_routes_to_sherpa_without_torch(monkeypatch):
    captured = {}

    def fake_transcriber(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(asr_preload, "SherpaOnnxTranscriber", fake_transcriber)
    config = asr_preload.build_asr_config({
        "use_qwen3_asr": True,
        "qwen3_asr_model": "Qwen/Qwen3-ASR-0.6B",
        "runtime_profile": "cpu",
    })
    assert asr_preload.resolve_preload_config(config) is config
    asr_preload.create_transcriber(config)
    assert captured["model"] == "Qwen/Qwen3-ASR-0.6B"
