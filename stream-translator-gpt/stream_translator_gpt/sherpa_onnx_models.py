"""CPU-only sherpa-onnx model registry.

The public model ids stay identical to the CUDA UI/API ids while the CPU
runtime resolves them to pre-exported INT8 sherpa-onnx bundles.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SHERPA_RELEASE_ROOT = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"


@dataclass(frozen=True)
class SherpaModelSpec:
    model_id: str
    family: str
    bundle: str
    required_paths: tuple[str, ...]

    @property
    def archive_name(self) -> str:
        return f"{self.bundle}.tar.bz2"

    @property
    def download_url(self) -> str:
        return f"{SHERPA_RELEASE_ROOT}/{self.archive_name}"


SHERPA_CPU_MODELS: dict[str, SherpaModelSpec] = {
    "nvidia/parakeet-tdt-0.6b-v3": SherpaModelSpec(
        model_id="nvidia/parakeet-tdt-0.6b-v3",
        family="transducer",
        bundle="sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8",
        required_paths=("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"),
    ),
    "nvidia/parakeet-tdt_ctc-0.6b-ja": SherpaModelSpec(
        model_id="nvidia/parakeet-tdt_ctc-0.6b-ja",
        family="nemo_ctc",
        bundle="sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8",
        required_paths=("model.int8.onnx", "tokens.txt"),
    ),
    "FunAudioLLM/Fun-ASR-Nano-2512": SherpaModelSpec(
        model_id="FunAudioLLM/Fun-ASR-Nano-2512",
        family="funasr_nano",
        bundle="sherpa-onnx-funasr-nano-int8-2025-12-30",
        required_paths=("encoder_adaptor.int8.onnx", "llm.int8.onnx", "embedding.int8.onnx", "Qwen3-0.6B"),
    ),
    "iic/SenseVoiceSmall": SherpaModelSpec(
        model_id="iic/SenseVoiceSmall",
        family="sense_voice",
        bundle="sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        required_paths=("model.int8.onnx", "tokens.txt"),
    ),
    "Qwen/Qwen3-ASR-0.6B": SherpaModelSpec(
        model_id="Qwen/Qwen3-ASR-0.6B",
        family="qwen3_asr",
        bundle="sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        required_paths=("conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx", "tokenizer"),
    ),
}


def get_sherpa_model_spec(model_id: str) -> SherpaModelSpec:
    try:
        return SHERPA_CPU_MODELS[model_id]
    except KeyError as exc:
        supported = ", ".join(SHERPA_CPU_MODELS)
        raise ValueError(f"Unsupported CPU sherpa-onnx model: {model_id}. Supported: {supported}") from exc


def get_sherpa_model_root() -> Path:
    configured = os.environ.get("SHERPA_ONNX_MODEL_DIR", "").strip()
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured))).resolve()
    return (Path.cwd() / "models" / "sherpa-onnx").resolve()


def resolve_sherpa_model_dir(model_id: str, root: Path | None = None) -> Path:
    spec = get_sherpa_model_spec(model_id)
    model_dir = (root or get_sherpa_model_root()) / spec.bundle
    missing = [name for name in spec.required_paths if not (model_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"CPU sherpa-onnx model is not installed: {model_id}. "
            f"Expected {model_dir}; missing: {', '.join(missing)}"
        )
    return model_dir.resolve()
