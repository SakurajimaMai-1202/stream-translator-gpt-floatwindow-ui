"""Unified CPU ASR adapter backed by sherpa-onnx INT8 models."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from .audio_transcriber import AudioTranscriber
from .common import INFO, SAMPLE_RATE
from .qwen3_asr_postprocess import strip_qwen3_asr_markers
from .sherpa_onnx_models import get_sherpa_model_spec, resolve_sherpa_model_dir


def _thread_count() -> int:
    configured = os.environ.get("SHERPA_ONNX_NUM_THREADS", "").strip()
    if configured:
        return max(1, int(configured))
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _language_hint(language: str | None) -> str:
    value = (language or "").strip().lower()
    aliases = {"chinese": "zh", "english": "en", "japanese": "ja", "korean": "ko"}
    return aliases.get(value, value) if value != "auto" else ""


class SherpaOnnxTranscriber(AudioTranscriber):
    """Runs one of the supported CPU model families without importing torch."""

    suppress_consecutive_duplicates = True

    def __init__(self, model: str, language: str | None = None, model_root: Path | None = None,
                 num_threads: int | None = None, sherpa_module: Any | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model_id = model
        self.output_language = language
        self.language = _language_hint(language)
        self.spec = get_sherpa_model_spec(model)
        self.model_dir = resolve_sherpa_model_dir(model, model_root)
        self.num_threads = num_threads or _thread_count()
        if sherpa_module is None:
            try:
                import sherpa_onnx as sherpa_module
            except ImportError as exc:
                raise RuntimeError(
                    "The CPU runtime requires sherpa-onnx. Install the CPU package or run "
                    "pip install sherpa-onnx==1.13.4."
                ) from exc
        print(f"{INFO}Loading CPU sherpa-onnx model: {model} ({self.num_threads} threads)")
        self.recognizer = self._create_recognizer(sherpa_module)

    def _path(self, name: str) -> str:
        return str((self.model_dir / name).resolve())

    def _create_recognizer(self, sherpa: Any):
        common = {"num_threads": self.num_threads, "provider": "cpu", "debug": False}
        if self.spec.family == "transducer":
            return sherpa.OfflineRecognizer.from_transducer(
                encoder=self._path("encoder.int8.onnx"), decoder=self._path("decoder.int8.onnx"),
                joiner=self._path("joiner.int8.onnx"), tokens=self._path("tokens.txt"),
                model_type="nemo_transducer", **common)
        if self.spec.family == "nemo_ctc":
            return sherpa.OfflineRecognizer.from_nemo_ctc(
                model=self._path("model.int8.onnx"), tokens=self._path("tokens.txt"), **common)
        if self.spec.family == "sense_voice":
            return sherpa.OfflineRecognizer.from_sense_voice(
                model=self._path("model.int8.onnx"), tokens=self._path("tokens.txt"),
                language=self.language, use_itn=True, **common)
        if self.spec.family == "funasr_nano":
            return sherpa.OfflineRecognizer.from_funasr_nano(
                encoder_adaptor=self._path("encoder_adaptor.int8.onnx"), llm=self._path("llm.int8.onnx"),
                embedding=self._path("embedding.int8.onnx"), tokenizer=self._path("Qwen3-0.6B"),
                language=self.language, itn=True, **common)
        if self.spec.family == "qwen3_asr":
            return sherpa.OfflineRecognizer.from_qwen3_asr(
                conv_frontend=self._path("conv_frontend.onnx"), encoder=self._path("encoder.int8.onnx"),
                decoder=self._path("decoder.int8.onnx"), tokenizer=self._path("tokenizer"), **common)
        raise AssertionError(f"Unhandled sherpa-onnx model family: {self.spec.family}")

    def transcribe(self, audio: np.ndarray, initial_prompt: str = None) -> tuple[str, list | None]:
        del initial_prompt  # Offline sherpa models do not share a cross-segment prompt API.
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return "", None
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self.recognizer.decode_stream(stream)
        result = stream.result
        text = str(getattr(result, "text", "") or "").strip()
        if self.spec.family == "qwen3_asr":
            text = strip_qwen3_asr_markers(text)
        tokens = list(getattr(result, "tokens", []) or [])
        return text, tokens or None
