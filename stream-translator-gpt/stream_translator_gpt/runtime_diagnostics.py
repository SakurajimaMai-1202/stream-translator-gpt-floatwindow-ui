from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from .runtime_accelerator import detect_torch_runtime_gpus, resolve_qwen3_device_map


def build_runtime_diagnostics(
    profile: str = "cuda",
    device_policy: str = "auto_discrete",
    allow_integrated_gpu: bool = False,
    run_torch_smoke: bool = True,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": 1,
        "generated_at": _iso_timestamp(),
        "profile": profile,
        "device_policy": device_policy,
        "allow_integrated_gpu": allow_integrated_gpu,
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "runtime_manifest": _read_runtime_manifest(),
        "torch": _torch_report(),
        "qwen_asr": _import_report("qwen_asr"),
        "validation": {
            "package_validated": False,
            "runtime_import_validated": False,
            "torch_execution_validated": False,
            "gpu_inference_validated": False,
            "asr_inference_validated": False,
            "reason": "",
        },
    }

    torch_module = report["torch"].get("_module")
    if torch_module is not None:
        devices = detect_torch_runtime_gpus(torch_module)
        device_map = resolve_qwen3_device_map(
            torch_module,
            "auto",
            runtime_profile=profile,
            device_policy=device_policy,
            allow_integrated_gpu=allow_integrated_gpu,
        )
        report["devices"] = [_device_to_dict(device) for device in devices]
        report["selection"] = {
            "device_map": device_map,
            "selected_device_index": _device_index_from_map(device_map),
            "reason": _selection_reason(profile, device_map, devices),
        }
        report["torch_smoke"] = _torch_smoke(torch_module, device_map) if run_torch_smoke else {"status": "skipped"}
    else:
        report["devices"] = []
        report["selection"] = {
            "device_map": "unavailable",
            "selected_device_index": None,
            "reason": "torch import failed",
        }
        report["torch_smoke"] = {"status": "skipped", "reason": "torch import failed"}

    report["validation"] = _validation_summary(report)
    report["torch"].pop("_module", None)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Stream Translator runtime diagnostics.")
    parser.add_argument("--profile", choices=["cuda", "cpu", "rocm"], default="cuda")
    parser.add_argument(
        "--device-policy",
        choices=["auto_discrete", "auto_any", "manual", "cpu"],
        default="auto_discrete",
    )
    parser.add_argument("--allow-integrated-gpu", action="store_true")
    parser.add_argument("--no-torch-smoke", action="store_true")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args(argv)

    report = build_runtime_diagnostics(
        profile=args.profile,
        device_policy=args.device_policy,
        allow_integrated_gpu=args.allow_integrated_gpu,
        run_torch_smoke=not args.no_torch_smoke,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _torch_report() -> dict[str, Any]:
    try:
        torch = importlib.import_module("torch")
    except Exception as exc:
        return {
            "imported": False,
            "error": repr(exc),
            "_module": None,
        }

    cuda = getattr(torch, "cuda", None)
    version = getattr(torch, "version", None)
    hip_version = getattr(version, "hip", None) if version else None
    cuda_version = getattr(version, "cuda", None) if version else None
    cuda_available = False
    device_count = 0
    if cuda is not None:
        try:
            cuda_available = bool(cuda.is_available())
        except Exception:
            cuda_available = False
        try:
            device_count = int(cuda.device_count())
        except Exception:
            device_count = 0
    return {
        "imported": True,
        "version": getattr(torch, "__version__", None),
        "cuda": cuda_version,
        "hip": hip_version,
        "backend": _torch_backend(cuda_version, hip_version),
        "cuda_available": cuda_available,
        "device_count": device_count,
        "_module": torch,
    }


def _import_report(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return {
            "imported": False,
            "error": repr(exc),
        }
    return {
        "imported": True,
        "version": getattr(module, "__version__", None),
    }


def _torch_smoke(torch: Any, device_map: str) -> dict[str, Any]:
    if device_map == "auto":
        return {
            "status": "skipped",
            "reason": "no concrete accelerator device was selected",
        }
    device = "cpu" if device_map == "cpu" else device_map
    try:
        tensor = torch.ones((2, 2), device=device)
        result = (tensor + 1).sum().item()
        if device != "cpu" and hasattr(torch, "cuda"):
            torch.cuda.synchronize(device)
        return {
            "status": "passed",
            "device": device,
            "result": float(result),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "device": device,
            "error": repr(exc),
        }


def _validation_summary(report: dict[str, Any]) -> dict[str, Any]:
    torch_report = report.get("torch", {})
    manifest = report.get("runtime_manifest", {})
    qwen = report.get("qwen_asr", {})
    selection = report.get("selection", {})
    smoke = report.get("torch_smoke", {})
    profile = report.get("profile")
    device_map = selection.get("device_map")

    package_validated = bool(manifest.get("found") and manifest.get("profile") == profile)
    runtime_import_validated = bool(torch_report.get("imported") and qwen.get("imported"))
    torch_execution_validated = smoke.get("status") == "passed"
    gpu_inference_validated = bool(torch_execution_validated and isinstance(device_map, str) and device_map.startswith("cuda:"))

    reason = "ASR inference smoke test was not run by this lightweight diagnostic."
    if profile == "rocm" and not gpu_inference_validated:
        reason = "No ROCm GPU execution was validated on this machine."
    elif profile == "cpu" and torch_execution_validated:
        reason = "CPU torch execution passed; ASR inference smoke test was not run."

    return {
        "package_validated": package_validated,
        "runtime_import_validated": runtime_import_validated,
        "torch_execution_validated": torch_execution_validated,
        "gpu_inference_validated": gpu_inference_validated,
        "asr_inference_validated": False,
        "reason": reason,
    }


def _read_runtime_manifest() -> dict[str, Any]:
    candidates = [
        Path(sys.executable).resolve().parent / "runtime-version.json",
        Path.cwd() / "_runtime" / "runtime-version.json",
        Path.cwd() / "runtime-version.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return {
                "found": True,
                "path": str(candidate),
                "error": repr(exc),
            }
        data["found"] = True
        data["path"] = str(candidate)
        return data
    return {
        "found": False,
        "path": None,
    }


def _device_to_dict(device: Any) -> dict[str, Any]:
    return {
        "index": device.index,
        "name": device.name,
        "vendor": device.vendor,
        "memory_mb": device.memory_mb,
        "is_integrated": device.is_integrated,
        "arch_name": getattr(device, "arch_name", None),
        "is_supported_by_torch": getattr(device, "is_supported_by_torch", None),
    }


def _device_index_from_map(device_map: str) -> int | None:
    if not device_map.startswith("cuda:"):
        return None
    try:
        return int(device_map.split(":", 1)[1])
    except ValueError:
        return None


def _selection_reason(profile: str, device_map: str, devices: Any) -> str:
    if profile == "cpu" or device_map == "cpu":
        return "CPU profile or policy selected."
    if device_map.startswith("cuda:"):
        return "Selected a concrete accelerator device."
    if not devices:
        return "No torch-visible GPU devices were found."
    return "No matching discrete GPU was selected for this profile."


def _torch_backend(cuda_version: str | None, hip_version: str | None) -> str:
    if hip_version:
        return "rocm"
    if cuda_version:
        return "cuda"
    return "cpu"


def _iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


if __name__ == "__main__":
    raise SystemExit(main())
