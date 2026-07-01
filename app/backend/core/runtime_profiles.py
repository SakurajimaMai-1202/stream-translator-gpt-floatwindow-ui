from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .hardware_detector import DevicePolicy, RuntimeProfile


SupportStatus = Literal["official", "compatibility", "experimental", "disabled"]


@dataclass(frozen=True)
class RuntimeCapabilities:
    profile: RuntimeProfile
    status: SupportStatus
    package_suffix: str
    default_device_policy: DevicePolicy
    allow_integrated_gpu: bool
    qwen3_default_dtype: str
    qwen3_offline_models: tuple[str, ...]
    qwen3_asr_model_ids: tuple[str, ...]
    qwen3_streaming_status: SupportStatus
    qwen3_streaming_note: str
    sensevoice_status: SupportStatus
    sensevoice_models: tuple[str, ...]
    sensevoice_model_ids: tuple[str, ...]
    sensevoice_note: str
    parakeet_status: SupportStatus
    parakeet_models: tuple[str, ...]
    parakeet_model_ids: tuple[str, ...]
    parakeet_note: str
    faster_whisper_status: SupportStatus
    faster_whisper_models: tuple[str, ...]
    faster_whisper_model_ids: tuple[str, ...]
    faster_whisper_gpu_enabled: bool
    faster_whisper_cpu_fallback: bool
    local_asr_engines: tuple[str, ...]
    remote_asr_engines: tuple[str, ...]


_CAPABILITIES: dict[RuntimeProfile, RuntimeCapabilities] = {
    "cuda": RuntimeCapabilities(
        profile="cuda",
        status="official",
        package_suffix="CUDA",
        default_device_policy="auto_discrete",
        allow_integrated_gpu=False,
        qwen3_default_dtype="bfloat16",
        qwen3_offline_models=("0.6B", "1.7B", "1.7B-JA"),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B", "neosophie/Qwen3-ASR-1.7B-JA"),
        qwen3_streaming_status="experimental",
        qwen3_streaming_note="0.6B Streaming, English only.",
        sensevoice_status="compatibility",
        sensevoice_models=("SenseVoiceSmall",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="Offline sliced transcription; CPU-capable, GPU acceleration depends on runtime profile.",
        parakeet_status="experimental",
        parakeet_models=("Parakeet CTC 1.1B JA",),
        parakeet_model_ids=("grider-transwithai/parakeet-ctc-1.1b-ja",),
        parakeet_note="CUDA-only experimental Japanese CTC ASR through NVIDIA NeMo.",
        faster_whisper_status="official",
        faster_whisper_models=("all",),
        faster_whisper_model_ids=("tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"),
        faster_whisper_gpu_enabled=True,
        faster_whisper_cpu_fallback=True,
        local_asr_engines=("faster-whisper", "simul-streaming", "faster-whisper-simul", "qwen3-asr", "sensevoice", "parakeet-ctc-ja"),
        remote_asr_engines=("openai-api",),
    ),
    "cpu": RuntimeCapabilities(
        profile="cpu",
        status="compatibility",
        package_suffix="CPU",
        default_device_policy="cpu",
        allow_integrated_gpu=False,
        qwen3_default_dtype="float32",
        qwen3_offline_models=("0.6B",),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B",),
        qwen3_streaming_status="experimental",
        qwen3_streaming_note="0.6B Streaming, English only, performance not guaranteed.",
        sensevoice_status="compatibility",
        sensevoice_models=("SenseVoiceSmall",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="CPU-capable; performance depends on CPU generation and audio segment length.",
        parakeet_status="disabled",
        parakeet_models=(),
        parakeet_model_ids=(),
        parakeet_note="Parakeet CTC JA is CUDA-only in this build.",
        faster_whisper_status="compatibility",
        faster_whisper_models=("small", "medium"),
        faster_whisper_model_ids=("small", "medium"),
        faster_whisper_gpu_enabled=False,
        faster_whisper_cpu_fallback=True,
        local_asr_engines=("faster-whisper", "qwen3-asr", "sensevoice"),
        remote_asr_engines=("openai-api",),
    ),
    "rocm": RuntimeCapabilities(
        profile="rocm",
        status="experimental",
        package_suffix="ROCm-Experimental",
        default_device_policy="auto_discrete",
        allow_integrated_gpu=False,
        qwen3_default_dtype="bfloat16",
        qwen3_offline_models=("0.6B", "1.7B", "1.7B-JA"),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B", "neosophie/Qwen3-ASR-1.7B-JA"),
        qwen3_streaming_status="experimental",
        qwen3_streaming_note="0.6B Streaming, English only, no formal upstream ROCm promise.",
        sensevoice_status="experimental",
        sensevoice_models=("SenseVoiceSmall",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="ROCm support requires AMD machine validation; package-level validation is not enough.",
        parakeet_status="disabled",
        parakeet_models=(),
        parakeet_model_ids=(),
        parakeet_note="Parakeet CTC JA depends on NVIDIA NeMo/CUDA and is not exposed in ROCm packages.",
        faster_whisper_status="disabled",
        faster_whisper_models=(),
        faster_whisper_model_ids=(),
        faster_whisper_gpu_enabled=False,
        faster_whisper_cpu_fallback=True,
        local_asr_engines=("qwen3-asr", "sensevoice"),
        remote_asr_engines=("openai-api",),
    ),
}


def get_runtime_capabilities(profile: str | None) -> RuntimeCapabilities:
    normalized = normalize_runtime_profile(profile)
    return _CAPABILITIES[normalized]


def normalize_runtime_profile(profile: str | None) -> RuntimeProfile:
    normalized = str(profile or "cuda").strip().lower()
    if normalized in _CAPABILITIES:
        return normalized  # type: ignore[return-value]
    return "cuda"


def default_runtime_config(profile: str | None = None) -> dict[str, object]:
    capabilities = get_runtime_capabilities(profile)
    return {
        "profile": capabilities.profile,
        "device_policy": capabilities.default_device_policy,
        "device_index": None,
        "device_name": "",
        "allow_integrated_gpu": capabilities.allow_integrated_gpu,
    }
