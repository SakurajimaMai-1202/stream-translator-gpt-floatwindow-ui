from backend.core.hardware_detector import (
    GpuDevice,
    classify_vendor,
    _merge_gpu_detections,
    is_integrated_gpu_name,
    is_integrated_gpu_adapter,
    select_accelerator,
    vram_tier,
)


def test_gpu_name_classification():
    assert classify_vendor("NVIDIA GeForce RTX 4070 Laptop GPU") == "nvidia"
    assert classify_vendor("AMD Radeon RX 7900 XTX") == "amd"
    assert classify_vendor("Intel Iris Xe Graphics") == "intel"


def test_simple_mode_vram_tiers_use_exact_boundaries():
    assert vram_tier(4095)[0] == "under_4gb"
    assert vram_tier(4096)[0] == "4_to_8gb"
    assert vram_tier(8191)[0] == "4_to_8gb"
    assert vram_tier(8192)[0] == "8gb_plus"
    assert vram_tier(None)[0] == "unknown"


def test_gpu_fallback_merge_prefers_reliable_nvidia_smi_vram():
    windows = GpuDevice(0, "NVIDIA GeForce RTX 3060", "nvidia", "cuda", None, False, source="win32_video_controller")
    smi = GpuDevice(0, "NVIDIA GeForce RTX 3060", "nvidia", "cuda", 12288, False, source="nvidia_smi")
    merged = _merge_gpu_detections([windows], [smi])
    assert len(merged) == 1
    assert merged[0].memory_mb == 12288
    assert merged[0].source == "nvidia_smi"


def test_intel_arc_is_discrete_and_uses_sycl_backend():
    from backend.core.hardware_detector import backend_for_vendor, is_integrated_gpu_name

    assert is_integrated_gpu_name("Intel Arc A770") is False
    assert is_integrated_gpu_name("Intel(R) Arc(TM) A750 Graphics") is False
    assert is_integrated_gpu_name("Intel® Arc™ A750 Graphics") is False
    assert backend_for_vendor("intel") == "sycl"


def test_windows_arc_name_reaches_simple_onboarding():
    from backend.core.translation_model_recommender import build_translation_model_recommendations

    name = "Intel(R) Arc(TM) A750 Graphics"
    device = GpuDevice(0, name, classify_vendor(name), "sycl", 8192,
                       is_integrated_gpu_name(name))
    result = build_translation_model_recommendations([device])
    assert result["selected_gpu"]["name"] == name
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-q6-k"


def test_integrated_gpu_heuristic_prefers_discrete_markers():
    assert is_integrated_gpu_name("Intel Iris Xe Graphics")
    assert is_integrated_gpu_name("AMD Radeon(TM) Graphics")
    assert not is_integrated_gpu_name("AMD Radeon RX 7800 XT")
    assert not is_integrated_gpu_name("NVIDIA GeForce RTX 4070 Laptop GPU")


def test_cuda_selection_skips_integrated_and_chooses_largest_nvidia_gpu():
    devices = [
        GpuDevice(0, "Intel Iris Xe Graphics", "intel", "unknown", 1024, True),
        GpuDevice(1, "NVIDIA GeForce RTX 3060", "nvidia", "cuda", 12288, False),
        GpuDevice(2, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False),
    ]

    selected = select_accelerator("cuda", devices)

    assert selected.kind == "gpu"
    assert selected.device is not None
    assert selected.device.index == 1
    assert [device.index for device in selected.ignored_devices] == [0]


def test_arc_and_radeon_integrated_names():
    for name in ("Intel Arc Graphics", "Intel(R) Arc(TM) 140V GPU", "Intel Arc 130V",
                 "AMD Radeon 780M Graphics", "AMD Radeon 680M"):
        assert is_integrated_gpu_name(name), name
    for name in ("Intel Arc A770", "Intel Arc B580 Graphics", "Intel Arc Pro A60",
                 "Intel Arc Pro B60"):
        assert not is_integrated_gpu_name(name), name


def test_dxgi_shared_memory_detects_unnamed_integrated_adapter():
    assert is_integrated_gpu_adapter("AMD Graphics", 0, 8 * 1024**3)
    assert is_integrated_gpu_adapter("Intel Arc 140V GPU", 128 * 1024**2, 8 * 1024**3)
    assert not is_integrated_gpu_adapter("Intel Arc B580", 12 * 1024**3, 8 * 1024**3)


def test_rocm_selection_skips_amd_integrated_by_default():
    devices = [
        GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "rocm", 2048, True, is_supported_by_torch=True),
        GpuDevice(1, "AMD Radeon RX 7900 XTX", "amd", "rocm", 24576, False, is_supported_by_torch=True),
    ]

    selected = select_accelerator("rocm", devices)

    assert selected.kind == "gpu"
    assert selected.device is not None
    assert selected.device.index == 1
    assert [device.index for device in selected.ignored_devices] == [0]


def test_rocm_selection_can_allow_integrated_for_experiments():
    devices = [
        GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "rocm", 2048, True, is_supported_by_torch=True),
    ]

    selected = select_accelerator("rocm", devices, allow_integrated_gpu=True)

    assert selected.kind == "gpu"
    assert selected.device is not None
    assert selected.device.index == 0


def test_rocm_selection_ignores_unsupported_gfx_arch():
    devices = [
        GpuDevice(
            0,
            "AMD Radeon RX 9070 XT",
            "amd",
            "rocm",
            16384,
            False,
            arch_name="gfx1201",
            is_supported_by_torch=False,
        ),
    ]

    selected = select_accelerator("rocm", devices)

    assert selected.kind == "none"
    assert [device.index for device in selected.ignored_devices] == [0]


def test_rocm_selection_accepts_supported_gfx_arch():
    devices = [
        GpuDevice(
            0,
            "AMD Radeon RX 7900 XTX",
            "amd",
            "rocm",
            24576,
            False,
            arch_name="gfx1100",
            is_supported_by_torch=True,
        ),
    ]

    selected = select_accelerator("rocm", devices)

    assert selected.kind == "gpu"
    assert selected.device is not None
    assert selected.device.index == 0


def test_manual_selection_respects_integrated_gpu_guard():
    devices = [
        GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "rocm", 2048, True),
    ]

    blocked = select_accelerator("rocm", devices, policy="manual", device_index=0)
    allowed = select_accelerator("rocm", devices, policy="manual", device_index=0, allow_integrated_gpu=True)

    assert blocked.kind == "none"
    assert allowed.kind == "gpu"


def test_cpu_profile_forces_cpu():
    selected = select_accelerator(
        "cpu",
        [GpuDevice(0, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False)],
    )

    assert selected.kind == "cpu"
    assert selected.device is None
