from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal


RuntimeProfile = Literal["cuda", "cpu", "rocm"]
DevicePolicy = Literal["auto_discrete", "auto_any", "manual", "cpu"]

INTEGRATED_NAME_MARKERS = (
    "intel",
    "uhd",
    "iris",
    "integrated",
    "apu",
    "radeon graphics",
    "amd radeon(tm) graphics",
)

DISCRETE_NAME_MARKERS = (
    "nvidia geforce",
    "nvidia rtx",
    "nvidia gtx",
    "nvidia quadro",
    "nvidia rtx a",
    "amd radeon rx",
    "amd radeon pro",
    "amd instinct",
)


@dataclass(frozen=True)
class RuntimeGpu:
    index: int
    name: str
    vendor: str
    memory_mb: int | None
    is_integrated: bool
    arch_name: str | None = None
    is_supported_by_torch: bool | None = None


def resolve_qwen3_device_map(
    torch_module: Any,
    requested_device_map: str | None,
    runtime_profile: str | None = "cuda",
    device_policy: str | None = "auto_discrete",
    allow_integrated_gpu: bool = False,
) -> str:
    requested = str(requested_device_map or "auto").strip() or "auto"
    profile = _normalize_runtime_profile(runtime_profile)
    policy = _normalize_device_policy(device_policy)

    if requested != "auto":
        return requested
    if profile == "cpu" or policy == "cpu":
        return "cpu"

    selected = select_runtime_gpu(
        torch_module=torch_module,
        profile=profile,
        policy=policy,
        allow_integrated_gpu=allow_integrated_gpu,
    )
    if selected is None:
        return "cpu"
    return f"cuda:{selected.index}"


def select_runtime_gpu(
    torch_module: Any,
    profile: RuntimeProfile,
    policy: DevicePolicy = "auto_discrete",
    allow_integrated_gpu: bool = False,
) -> RuntimeGpu | None:
    devices = detect_torch_runtime_gpus(torch_module)
    candidates: list[RuntimeGpu] = []
    for device in devices:
        if not _device_matches_profile(device, profile):
            continue
        if policy == "auto_discrete" and device.is_integrated and not allow_integrated_gpu:
            continue
        if profile == "rocm" and device.is_supported_by_torch is not True:
            continue
        if device.is_supported_by_torch is False:
            continue
        candidates.append(device)
    if not candidates:
        return None
    return sorted(candidates, key=lambda device: device.memory_mb or 0, reverse=True)[0]


def detect_torch_runtime_gpus(torch_module: Any) -> tuple[RuntimeGpu, ...]:
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None:
        return ()
    try:
        count = int(cuda.device_count())
    except Exception:
        return ()

    devices: list[RuntimeGpu] = []
    supported_arches = _torch_supported_arches(cuda)
    for index in range(count):
        try:
            name = str(cuda.get_device_name(index))
        except Exception:
            name = f"GPU {index}"
        memory_mb = None
        arch_name = None
        try:
            props = cuda.get_device_properties(index)
            memory_mb = int(getattr(props, "total_memory", 0) / (1024 * 1024)) or None
            arch_name = _normalize_arch_name(
                getattr(props, "gcnArchName", None)
                or getattr(props, "gcn_arch_name", None)
                or getattr(props, "arch_name", None)
            )
        except Exception:
            pass
        is_supported = _is_arch_supported_by_torch(arch_name, supported_arches)
        devices.append(
            RuntimeGpu(
                index=index,
                name=name,
                vendor=classify_vendor(name),
                memory_mb=memory_mb,
                is_integrated=is_integrated_gpu_name(name),
                arch_name=arch_name,
                is_supported_by_torch=is_supported,
            )
        )
    return tuple(devices)


def classify_vendor(name: str | None) -> str:
    normalized = _normalize_name(name)
    if "nvidia" in normalized or "geforce" in normalized or "quadro" in normalized:
        return "nvidia"
    if "amd" in normalized or "radeon" in normalized or "instinct" in normalized:
        return "amd"
    if "intel" in normalized or "iris" in normalized or "uhd" in normalized:
        return "intel"
    return "unknown"


def is_integrated_gpu_name(name: str | None) -> bool:
    normalized = _normalize_name(name)
    if not normalized:
        return False
    if any(marker in normalized for marker in DISCRETE_NAME_MARKERS):
        return False
    return any(marker in normalized for marker in INTEGRATED_NAME_MARKERS)


def _device_matches_profile(device: RuntimeGpu, profile: RuntimeProfile) -> bool:
    if profile == "cuda":
        return device.vendor == "nvidia"
    if profile == "rocm":
        return device.vendor == "amd"
    return False


def _normalize_name(name: str | None) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _normalize_arch_name(arch_name: object) -> str | None:
    if arch_name is None:
        return None
    normalized = str(arch_name).strip().lower()
    if not normalized:
        return None
    return normalized.split(":", 1)[0]


def _torch_supported_arches(cuda: Any) -> set[str]:
    get_arch_list = getattr(cuda, "get_arch_list", None)
    if get_arch_list is None:
        return set()
    try:
        raw_arches = get_arch_list()
    except Exception:
        return set()
    arches: set[str] = set()
    for arch in raw_arches or []:
        normalized = _normalize_arch_name(arch)
        if normalized:
            arches.add(normalized)
    return arches


def _is_arch_supported_by_torch(arch_name: str | None, supported_arches: set[str]) -> bool | None:
    if not arch_name or not supported_arches:
        return None
    if arch_name in supported_arches:
        return True
    # CUDA builds report sm_* while ROCm builds report gfx*. Only make a hard
    # rejection when both sides are ROCm-style gfx identifiers.
    if arch_name.startswith("gfx") and any(arch.startswith("gfx") for arch in supported_arches):
        return False
    return None


def _normalize_runtime_profile(profile: str | None) -> RuntimeProfile:
    normalized = str(profile or "cuda").strip().lower()
    if normalized in {"cuda", "cpu", "rocm"}:
        return normalized  # type: ignore[return-value]
    return "cuda"


def _normalize_device_policy(policy: str | None) -> DevicePolicy:
    normalized = str(policy or "auto_discrete").strip().lower()
    if normalized in {"auto_discrete", "auto_any", "manual", "cpu"}:
        return normalized  # type: ignore[return-value]
    return "auto_discrete"
