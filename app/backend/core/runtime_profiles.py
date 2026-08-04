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
    sensevoice_status: SupportStatus
    sensevoice_models: tuple[str, ...]
    sensevoice_model_ids: tuple[str, ...]
    sensevoice_note: str
    fun_asr_status: SupportStatus
    fun_asr_models: tuple[str, ...]
    fun_asr_model_ids: tuple[str, ...]
    fun_asr_note: str
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
        qwen3_offline_models=("0.6B", "1.7B", "1.7B-JA-Anime"),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B", "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame"),
        sensevoice_status="compatibility",
        sensevoice_models=("SenseVoiceSmall",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="Offline sliced transcription; CPU-capable, GPU acceleration depends on runtime profile.",
        fun_asr_status="compatibility",
        fun_asr_models=("Fun-ASR Nano (ZH/EN/JA)", "Fun-ASR MLT Nano (31 languages)"),
        fun_asr_model_ids=("FunAudioLLM/Fun-ASR-Nano-2512", "FunAudioLLM/Fun-ASR-MLT-Nano-2512"),
        fun_asr_note="Offline sliced transcription through FunASR; timestamps are not available.",
        parakeet_status="experimental",
        parakeet_models=("NVIDIA Parakeet 0.6B JA", "NVIDIA Parakeet 1.1B EN", "Legacy Parakeet CTC 1.1B JA"),
        parakeet_model_ids=("nvidia/parakeet-tdt_ctc-0.6b-ja", "nvidia/parakeet-tdt_ctc-1.1b", "grider-transwithai/parakeet-ctc-1.1b-ja"),
        parakeet_note="CUDA-only offline sliced English/Japanese hybrid TDT/CTC ASR through NVIDIA NeMo.",
        faster_whisper_status="official",
        faster_whisper_models=("all",),
        faster_whisper_model_ids=("tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"),
        faster_whisper_gpu_enabled=True,
        faster_whisper_cpu_fallback=True,
        local_asr_engines=("faster-whisper", "simul-streaming", "faster-whisper-simul", "qwen3-asr", "sensevoice", "fun-asr-nano", "parakeet-ctc-ja"),
        remote_asr_engines=("openai-api",),
    ),
    "cpu": RuntimeCapabilities(
        profile="cpu",
        status="compatibility",
        package_suffix="CPU",
        default_device_policy="cpu",
        allow_integrated_gpu=False,
        qwen3_default_dtype="float32",
        qwen3_offline_models=("0.6B INT8 (sherpa-onnx)",),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B",),
        sensevoice_status="official",
        sensevoice_models=("SenseVoiceSmall INT8 (sherpa-onnx)",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="INT8 CPU inference through sherpa-onnx; no PyTorch runtime is used.",
        fun_asr_status="official",
        fun_asr_models=("Fun-ASR Nano INT8 (ZH/EN/JA, sherpa-onnx)",),
        fun_asr_model_ids=("FunAudioLLM/Fun-ASR-Nano-2512",),
        fun_asr_note="INT8 CPU inference through sherpa-onnx; timestamps are not available.",
        parakeet_status="official",
        parakeet_models=("Parakeet TDT 0.6B v3 INT8 EN", "Parakeet TDT-CTC 0.6B INT8 JA"),
        parakeet_model_ids=("nvidia/parakeet-tdt-0.6b-v3", "nvidia/parakeet-tdt_ctc-0.6b-ja"),
        parakeet_note="INT8 CPU inference through sherpa-onnx; independent from NVIDIA NeMo/CUDA.",
        faster_whisper_status="disabled",
        faster_whisper_models=(),
        faster_whisper_model_ids=(),
        faster_whisper_gpu_enabled=False,
        faster_whisper_cpu_fallback=False,
        local_asr_engines=("qwen3-asr", "sensevoice", "fun-asr-nano", "parakeet-ctc-ja"),
        remote_asr_engines=("openai-api",),
    ),
    "rocm": RuntimeCapabilities(
        profile="rocm",
        status="experimental",
        package_suffix="ROCm-Experimental",
        default_device_policy="auto_discrete",
        allow_integrated_gpu=False,
        qwen3_default_dtype="bfloat16",
        qwen3_offline_models=("0.6B", "1.7B", "1.7B-JA-Anime"),
        qwen3_asr_model_ids=("Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B", "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame"),
        sensevoice_status="experimental",
        sensevoice_models=("SenseVoiceSmall",),
        sensevoice_model_ids=("iic/SenseVoiceSmall",),
        sensevoice_note="ROCm support requires AMD machine validation; package-level validation is not enough.",
        fun_asr_status="experimental",
        fun_asr_models=("Fun-ASR Nano (ZH/EN/JA)", "Fun-ASR MLT Nano (31 languages)"),
        fun_asr_model_ids=("FunAudioLLM/Fun-ASR-Nano-2512", "FunAudioLLM/Fun-ASR-MLT-Nano-2512"),
        fun_asr_note="ROCm support is experimental and requires validation on a discrete AMD GPU.",
        parakeet_status="disabled",
        parakeet_models=(),
        parakeet_model_ids=(),
        parakeet_note="NVIDIA Parakeet depends on NVIDIA NeMo/CUDA and is not exposed in ROCm packages.",
        faster_whisper_status="disabled",
        faster_whisper_models=(),
        faster_whisper_model_ids=(),
        faster_whisper_gpu_enabled=False,
        faster_whisper_cpu_fallback=True,
        local_asr_engines=("qwen3-asr", "sensevoice", "fun-asr-nano"),
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
