import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.core.llama_devices import parse_devices, select_device, update_gpu_evidence


def test_runtime_ids_and_integrated_arc_are_not_os_indices():
    output = "Available devices:\n  Vulkan0: Intel(R) Arc(TM) Graphics (12000 MiB, 9000 MiB free)\n  Vulkan1: NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB, 7000 MiB free)"
    adapters = [SimpleNamespace(name="Intel(R) Arc(TM) Graphics", vendor="intel", memory_mb=128, is_integrated=True)]
    devices = parse_devices(output, adapters)
    assert devices[0]["is_integrated"]
    assert select_device(devices)["id"] == "Vulkan1"
    with pytest.raises(ValueError):
        select_device(devices, "Vulkan0")
    with pytest.raises(ValueError):
        select_device(devices, "1")


def test_manual_and_empty_selection_fail_clearly():
    with pytest.raises(ValueError):
        select_device([])
    devices = [dict(id="Vulkan3", name="AMD", memory_mb=8192, eligible=True)]
    assert select_device(devices, "Vulkan3") == devices[0]
    with pytest.raises(ValueError):
        select_device(devices, "CUDA0")
    with pytest.raises(ValueError):
        select_device(devices, "Vulkan3", "Intel Arc A770")


def test_backend_initialization_does_not_confirm_model_placement():
    selection = dict(mode="gpu", selected_device=dict(name="AMD Radeon RX 7600"), confirmed=False)
    update_gpu_evidence(selection, "ggml_vulkan: 0 = AMD Radeon RX 7600")
    update_gpu_evidence(selection, "load_tensors: offloaded 33/33 layers to GPU")
    assert not selection["confirmed"]
    update_gpu_evidence(selection, "load_tensors: using device AMD Radeon RX 7600")
    assert selection["confirmed"]
    update_gpu_evidence(selection, "load_tensors: offloaded 0/33 layers to GPU")
    assert not selection["confirmed"]
