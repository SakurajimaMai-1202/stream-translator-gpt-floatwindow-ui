"""Select opaque device IDs reported by the installed llama.cpp runtime."""
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from backend.core.external_process import run_external
from backend.core.hardware_detector import (
    detect_windows_dxgi_adapters, is_integrated_gpu_name, normalize_gpu_name,
)


def parse_devices(output: str, adapters=None) -> list[dict]:
    adapters = adapters or []
    devices = []
    # llama.cpp: Vulkan0: AMD Radeon ... (8192 MiB, 7900 MiB free)
    pattern = re.compile(r"^\s*([\w.-]+):\s+(.+?)\s+\((\d+)\s*(?:MiB|MB),\s*(\d+)\s*(?:MiB|MB)\s+free\)", re.I)
    for line in output.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        device_id, name, memory, free = match.groups()
        integrated = is_integrated_gpu_name(name)
        adapter = next((a for a in adapters if normalize_gpu_name(a.name) == normalize_gpu_name(name)), None)
        if adapter is not None:
            integrated = adapter.is_integrated
        devices.append(dict(id=device_id, name=name, memory_mb=int(memory),
                            free_memory_mb=int(free), is_integrated=integrated))
    return devices


def enumerate_devices(server_exe: str, allow_integrated_gpu: bool = False) -> dict:
    try:
        result = run_external([server_exe, "--list-devices"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=15,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise ValueError((result.stderr or result.stdout or "Runtime 無法列出顯卡").strip()[-500:])
        adapters = detect_windows_dxgi_adapters() if os.name == "nt" else []
        devices = parse_devices((result.stdout or "") + "\n" + (result.stderr or ""), adapters)
        for device in devices:
            device["eligible"] = allow_integrated_gpu or not device["is_integrated"]
        return dict(devices=devices, error=None, server_exe=server_exe)
    except Exception as exc:
        return dict(devices=[], error=str(exc), server_exe=server_exe)


def supports_device_selection(server_exe: str) -> bool:
    try:
        stat = Path(server_exe).stat()
    except OSError:
        return False
    return "--device" in _runtime_help(server_exe, stat.st_mtime_ns, stat.st_size)


def gpu_logging_args(server_exe: str) -> list[str]:
    try:
        stat = Path(server_exe).stat()
        help_text = _runtime_help(server_exe, stat.st_mtime_ns, stat.st_size)
        return ["--verbosity", "4"] if "--verbosity" in help_text else []
    except OSError:
        return []


@lru_cache(maxsize=24)
def _runtime_help(server_exe: str, mtime_ns: int, size: int) -> str:
    try:
        result = run_external([server_exe, "--help"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=5,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return (result.stdout or "") + (result.stderr or "")
    except Exception:
        return ""


def select_device(devices: list[dict], requested: str = "auto", expected_name: str = "") -> dict:
    eligible = [d for d in devices if d.get("eligible", not d.get("is_integrated"))]
    if requested != "auto":
        selected = next((d for d in eligible if d["id"] == requested), None)
        if selected is None:
            raise ValueError("所選顯卡不可用或為已排除的內顯，請重新選擇顯卡。")
        if expected_name and normalize_gpu_name(selected["name"]) != normalize_gpu_name(expected_name):
            raise ValueError("所選顯卡的裝置編號已變更，請重新選擇顯卡。")
        return selected
    if not eligible:
        raise ValueError("此 Runtime 沒有可用的獨立顯卡。請選擇其他 Runtime、允許內顯，或將 GPU 層數設為 0 使用 CPU。")
    return max(eligible, key=lambda d: d.get("memory_mb", 0))


def update_gpu_evidence(selection: dict, line: str) -> None:
    if selection.get("mode") != "gpu":
        return
    selected = selection.get("selected_device") or {}
    name = normalize_gpu_name(selected.get("name"))
    device_id = selected.get("id", "")
    # Model placement is stronger evidence than backend initialization or a
    # list of all detected adapters. Require a placement/buffer log explicitly.
    identifies_device = (name and name in normalize_gpu_name(line)) or (
        device_id and re.search(r"(?<![\w])" + re.escape(device_id) + r"(?![\w])", line)
    )
    if identifies_device and re.search(r"using device|model buffer|buffer size", line, re.I):
        selection["evidence"] = line
    offload = re.search(r"offloaded\s+(\d+)(?:/\d+)?\s+layers", line, re.I)
    if offload:
        selection["offloaded_layers"] = int(offload.group(1))
    selection["confirmed"] = bool(selection.get("evidence") and (selection.get("offloaded_layers") or 0) > 0)
