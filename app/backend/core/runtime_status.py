from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .hardware_detector import (
    AcceleratorSelection,
    GpuDevice,
    detect_gpus,
    select_accelerator,
)
from .runtime_profiles import (
    RuntimeCapabilities,
    effective_asr_compute_backend,
    get_asr_capabilities,
    get_runtime_capabilities,
    normalize_asr_compute_backend,
)
from .asr_model_capabilities import list_asr_model_capabilities
from .portable_paths import get_cpu_asr_runtime_status, get_packaged_runtime_profile


def build_runtime_status(config: dict[str, Any], devices: list[GpuDevice] | None = None) -> dict[str, Any]:
    runtime_config = config.get("runtime", {}) if isinstance(config, dict) else {}
    packaged_profile = get_packaged_runtime_profile()
    capabilities = get_runtime_capabilities(packaged_profile or runtime_config.get("profile"))
    transcription_config = config.get("transcription", {}) if isinstance(config, dict) else {}
    asr_compute_backend = normalize_asr_compute_backend(
        transcription_config.get("asr_compute_backend"), capabilities.profile
    )
    effective_compute_backend = effective_asr_compute_backend(asr_compute_backend, capabilities.profile)
    asr_capabilities = get_asr_capabilities(capabilities.profile, asr_compute_backend)
    policy = _effective_device_policy(capabilities, runtime_config)
    allow_integrated_gpu = bool(runtime_config.get("allow_integrated_gpu", capabilities.allow_integrated_gpu))
    available_devices = devices if devices is not None else detect_gpus()
    selection = select_accelerator(
        profile=capabilities.profile,
        devices=available_devices,
        policy=policy,
        device_index=runtime_config.get("device_index"),
        device_name=runtime_config.get("device_name"),
        allow_integrated_gpu=allow_integrated_gpu,
    )

    return {
        "profile": capabilities.profile,
        "status": capabilities.status,
        "package_suffix": capabilities.package_suffix,
        "device_policy": policy,
        "allow_integrated_gpu": allow_integrated_gpu,
        "profile_locked": packaged_profile is not None,
        "packaged_profile": packaged_profile,
        "asr_compute_backend": asr_compute_backend,
        "effective_asr_compute_backend": effective_compute_backend,
        "capabilities": _capabilities_to_dict(capabilities),
        "asr_capabilities": _capabilities_to_dict(asr_capabilities),
        "cpu_asr_runtime": get_cpu_asr_runtime_status(),
        "devices": [_gpu_to_dict(device) for device in available_devices],
        "selection": _selection_to_dict(selection),
    }


def _effective_device_policy(capabilities: RuntimeCapabilities, runtime_config: dict[str, Any]) -> str:
    if capabilities.profile == "cpu":
        return "cpu"
    return str(runtime_config.get("device_policy") or capabilities.default_device_policy)


def _capabilities_to_dict(capabilities: RuntimeCapabilities) -> dict[str, Any]:
    data = asdict(capabilities)
    data["qwen3_offline_models"] = list(capabilities.qwen3_offline_models)
    data["qwen3_asr_model_ids"] = list(capabilities.qwen3_asr_model_ids)
    data["sensevoice_models"] = list(capabilities.sensevoice_models)
    data["sensevoice_model_ids"] = list(capabilities.sensevoice_model_ids)
    data["fun_asr_models"] = list(capabilities.fun_asr_models)
    data["fun_asr_model_ids"] = list(capabilities.fun_asr_model_ids)
    data["parakeet_models"] = list(capabilities.parakeet_models)
    data["parakeet_model_ids"] = list(capabilities.parakeet_model_ids)
    data["faster_whisper_models"] = list(capabilities.faster_whisper_models)
    data["faster_whisper_model_ids"] = list(capabilities.faster_whisper_model_ids)
    data["local_asr_engines"] = list(capabilities.local_asr_engines)
    data["remote_asr_engines"] = list(capabilities.remote_asr_engines)
    data["asr_model_capabilities"] = list_asr_model_capabilities()
    return data


def _gpu_to_dict(device: GpuDevice | None) -> dict[str, Any] | None:
    if device is None:
        return None
    return {
        "index": device.index,
        "name": device.name,
        "vendor": device.vendor,
        "backend": device.backend,
        "memory_mb": device.memory_mb,
        "is_integrated": device.is_integrated,
        "arch_name": device.arch_name,
        "is_supported_by_torch": device.is_supported_by_torch,
        "source": device.source,
    }


def _selection_to_dict(selection: AcceleratorSelection) -> dict[str, Any]:
    return {
        "kind": selection.kind,
        "profile": selection.profile,
        "policy": selection.policy,
        "device": _gpu_to_dict(selection.device),
        "reason": selection.reason,
        "ignored_devices": [_gpu_to_dict(device) for device in selection.ignored_devices],
    }
