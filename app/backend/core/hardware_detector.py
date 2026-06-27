from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
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
class GpuDevice:
    index: int
    name: str
    vendor: str
    backend: str
    memory_mb: int | None = None
    is_integrated: bool = False
    arch_name: str | None = None
    is_supported_by_torch: bool | None = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceleratorSelection:
    kind: Literal["gpu", "cpu", "none"]
    profile: RuntimeProfile
    policy: DevicePolicy
    device: GpuDevice | None = None
    reason: str = ""
    ignored_devices: tuple[GpuDevice, ...] = ()


def normalize_gpu_name(name: str | None) -> str:
    return " ".join(str(name or "").strip().lower().split())


def classify_vendor(name: str | None) -> str:
    normalized = normalize_gpu_name(name)
    if "nvidia" in normalized or "geforce" in normalized or "quadro" in normalized:
        return "nvidia"
    if "amd" in normalized or "radeon" in normalized or "instinct" in normalized:
        return "amd"
    if "intel" in normalized or "iris" in normalized or "uhd" in normalized:
        return "intel"
    return "unknown"


def is_integrated_gpu_name(name: str | None) -> bool:
    normalized = normalize_gpu_name(name)
    if not normalized:
        return False
    if any(marker in normalized for marker in DISCRETE_NAME_MARKERS):
        return False
    return any(marker in normalized for marker in INTEGRATED_NAME_MARKERS)


def backend_for_vendor(vendor: str, torch_hip_version: str | None = None) -> str:
    if vendor == "nvidia":
        return "cuda"
    if vendor == "amd":
        return "rocm" if torch_hip_version else "unknown"
    return "unknown"


def detect_torch_gpus(torch_module: Any | None = None) -> list[GpuDevice]:
    try:
        torch = torch_module
        if torch is None:
            import torch  # type: ignore
    except Exception:
        return []

    cuda = getattr(torch, "cuda", None)
    if cuda is None:
        return []

    try:
        count = int(cuda.device_count())
    except Exception:
        return []

    torch_version = getattr(torch, "version", None)
    hip_version = getattr(torch_version, "hip", None) if torch_version else None
    devices: list[GpuDevice] = []
    supported_arches = _torch_supported_arches(cuda)
    for index in range(count):
        try:
            name = str(cuda.get_device_name(index))
        except Exception:
            name = f"GPU {index}"
        vendor = classify_vendor(name)
        backend = backend_for_vendor(vendor, hip_version) if hip_version else ("cuda" if vendor == "nvidia" else "unknown")
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
            GpuDevice(
                index=index,
                name=name,
                vendor=vendor,
                backend=backend,
                memory_mb=memory_mb,
                is_integrated=is_integrated_gpu_name(name),
                arch_name=arch_name,
                is_supported_by_torch=is_supported,
                source="torch",
                raw={"torch_version_hip": hip_version, "torch_supported_arches": sorted(supported_arches)},
            )
        )
    return devices


def detect_windows_video_controllers() -> list[GpuDevice]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return []

    command = [
        powershell,
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM,PNPDeviceID | ConvertTo-Json -Compress"
        ),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        parsed_items = [parsed]
    elif isinstance(parsed, list):
        parsed_items = parsed
    else:
        return []

    devices: list[GpuDevice] = []
    for index, item in enumerate(parsed_items):
        name = str(item.get("Name") or f"GPU {index}")
        vendor = classify_vendor(name)
        adapter_ram = item.get("AdapterRAM")
        memory_mb = _memory_mb_from_windows_adapter_ram(adapter_ram)
        devices.append(
            GpuDevice(
                index=index,
                name=name,
                vendor=vendor,
                backend=backend_for_vendor(vendor),
                memory_mb=memory_mb,
                is_integrated=is_integrated_gpu_name(name),
                arch_name=None,
                is_supported_by_torch=None,
                source="win32_video_controller",
                raw=item,
            )
        )
    return devices


def detect_gpus(include_windows_fallback: bool = True) -> list[GpuDevice]:
    runtime_devices = detect_runtime_python_gpus()
    if runtime_devices:
        return runtime_devices
    torch_devices = detect_torch_gpus()
    if torch_devices or not include_windows_fallback:
        return torch_devices
    return detect_windows_video_controllers()


def detect_runtime_python_gpus(python_exe: str | None = None) -> list[GpuDevice]:
    runtime_python = Path(python_exe) if python_exe else _find_runtime_python()
    if runtime_python is None or not runtime_python.exists():
        return []

    script = (
        "import json\n"
        "try:\n"
        "    import torch\n"
        "    cuda = getattr(torch, 'cuda', None)\n"
        "    version = getattr(torch, 'version', None)\n"
        "    hip = getattr(version, 'hip', None) if version else None\n"
        "    supported_arches = []\n"
        "    if cuda is not None and hasattr(cuda, 'get_arch_list'):\n"
        "        try:\n"
        "            supported_arches = list(cuda.get_arch_list() or [])\n"
        "        except Exception:\n"
        "            supported_arches = []\n"
        "    devices = []\n"
        "    count = int(cuda.device_count()) if cuda is not None else 0\n"
        "    for index in range(count):\n"
        "        try:\n"
        "            name = str(cuda.get_device_name(index))\n"
        "        except Exception:\n"
        "            name = f'GPU {index}'\n"
        "        memory_mb = None\n"
        "        arch_name = None\n"
        "        try:\n"
        "            props = cuda.get_device_properties(index)\n"
        "            memory_mb = int(getattr(props, 'total_memory', 0) / (1024 * 1024)) or None\n"
        "            arch_name = getattr(props, 'gcnArchName', None) or getattr(props, 'gcn_arch_name', None) or getattr(props, 'arch_name', None)\n"
        "        except Exception:\n"
        "            pass\n"
        "        devices.append({'index': index, 'name': name, 'memory_mb': memory_mb, 'arch_name': arch_name})\n"
        "    print(json.dumps({'ok': True, 'hip': hip, 'supported_arches': supported_arches, 'devices': devices}, ensure_ascii=True))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=True))\n"
    )

    try:
        result = subprocess.run(
            [str(runtime_python), "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return []
    if not payload.get("ok"):
        return []

    supported_arches = {
        arch
        for arch in (_normalize_arch_name(raw_arch) for raw_arch in payload.get("supported_arches", []))
        if arch
    }
    hip_version = payload.get("hip")
    devices: list[GpuDevice] = []
    for raw in payload.get("devices", []):
        name = str(raw.get("name") or f"GPU {len(devices)}")
        vendor = classify_vendor(name)
        arch_name = _normalize_arch_name(raw.get("arch_name"))
        is_supported = _is_arch_supported_by_torch(arch_name, supported_arches)
        devices.append(
            GpuDevice(
                index=int(raw.get("index", len(devices))),
                name=name,
                vendor=vendor,
                backend=backend_for_vendor(vendor, hip_version) if hip_version else ("cuda" if vendor == "nvidia" else "unknown"),
                memory_mb=raw.get("memory_mb"),
                is_integrated=is_integrated_gpu_name(name),
                arch_name=arch_name,
                is_supported_by_torch=is_supported,
                source="runtime_python",
                raw={
                    "python": str(runtime_python),
                    "torch_version_hip": hip_version,
                    "torch_supported_arches": sorted(supported_arches),
                },
            )
        )
    return devices


def _find_runtime_python() -> Path | None:
    candidates: list[Path] = []
    executable_dir = Path(sys.executable).resolve().parent
    cwd = Path.cwd().resolve()
    candidates.extend(
        [
            executable_dir / "_runtime" / "python.exe",
            cwd / "_runtime" / "python.exe",
            executable_dir.parent / "_runtime" / "python.exe",
            cwd.parent / "_runtime" / "python.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _memory_mb_from_windows_adapter_ram(adapter_ram: object) -> int | None:
    if not isinstance(adapter_ram, int) or adapter_ram <= 0:
        return None
    memory_mb = int(adapter_ram / (1024 * 1024))
    # Win32_VideoController.AdapterRAM is often truncated to a 32-bit value,
    # which makes modern GPUs with more than 4 GB look like 4 GB cards.
    if adapter_ram >= 0xF0000000 or memory_mb >= 3840:
        return None
    return memory_mb or None


def select_accelerator(
    profile: RuntimeProfile,
    devices: Iterable[GpuDevice],
    policy: DevicePolicy = "auto_discrete",
    device_index: int | None = None,
    device_name: str | None = None,
    allow_integrated_gpu: bool = False,
) -> AcceleratorSelection:
    device_list = tuple(devices)
    if profile == "cpu" or policy == "cpu":
        return AcceleratorSelection(kind="cpu", profile=profile, policy=policy, reason="CPU profile or policy selected.")

    if policy == "manual":
        selected = _match_manual_device(device_list, device_index, device_name)
        if selected is None:
            return AcceleratorSelection(kind="none", profile=profile, policy=policy, reason="Manual GPU was not found.")
        if selected.is_integrated and not allow_integrated_gpu:
            return AcceleratorSelection(
                kind="none",
                profile=profile,
                policy=policy,
                reason="Manual GPU is integrated and allow_integrated_gpu is false.",
                ignored_devices=(selected,),
            )
        if not _device_matches_profile(selected, profile):
            return AcceleratorSelection(
                kind="none",
                profile=profile,
                policy=policy,
                reason=f"Manual GPU does not match the {profile} profile.",
                ignored_devices=(selected,),
            )
        return AcceleratorSelection(kind="gpu", profile=profile, policy=policy, device=selected, reason="Manual GPU selected.")

    candidates: list[GpuDevice] = []
    ignored: list[GpuDevice] = []
    for device in device_list:
        if not _device_matches_profile(device, profile):
            ignored.append(device)
            continue
        if policy == "auto_discrete" and device.is_integrated and not allow_integrated_gpu:
            ignored.append(device)
            continue
        if profile == "rocm" and device.is_supported_by_torch is not True:
            ignored.append(device)
            continue
        if device.is_supported_by_torch is False:
            ignored.append(device)
            continue
        candidates.append(device)

    if not candidates:
        return AcceleratorSelection(
            kind="none",
            profile=profile,
            policy=policy,
            reason=f"No suitable GPU found for the {profile} profile.",
            ignored_devices=tuple(ignored),
        )

    selected = sorted(candidates, key=lambda device: device.memory_mb or 0, reverse=True)[0]
    return AcceleratorSelection(
        kind="gpu",
        profile=profile,
        policy=policy,
        device=selected,
        reason="Selected the matching GPU with the largest known memory.",
        ignored_devices=tuple(ignored),
    )


def _match_manual_device(
    devices: Iterable[GpuDevice],
    device_index: int | None,
    device_name: str | None,
) -> GpuDevice | None:
    normalized_name = normalize_gpu_name(device_name)
    for device in devices:
        if device_index is not None and device.index == device_index:
            return device
        if normalized_name and normalized_name in normalize_gpu_name(device.name):
            return device
    return None


def _device_matches_profile(device: GpuDevice, profile: RuntimeProfile) -> bool:
    if profile == "cuda":
        return device.vendor == "nvidia" or device.backend == "cuda"
    if profile == "rocm":
        return device.vendor == "amd" or device.backend == "rocm"
    return False


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
    if arch_name.startswith("gfx") and any(arch.startswith("gfx") for arch in supported_arches):
        return False
    return None
