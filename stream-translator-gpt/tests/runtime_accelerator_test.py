from stream_translator_gpt.runtime_accelerator import resolve_qwen3_device_map


class _FakeProps:
    def __init__(self, total_memory, arch=None):
        self.total_memory = total_memory
        self.gcnArchName = arch


class _FakeCuda:
    def __init__(self, devices):
        self.devices = devices

    def device_count(self):
        return len(self.devices)

    def get_device_name(self, index):
        return self.devices[index]["name"]

    def get_device_properties(self, index):
        return _FakeProps(self.devices[index].get("memory", 0), self.devices[index].get("arch"))

    def get_arch_list(self):
        arches = []
        for device in self.devices:
            arches.extend(device.get("supported_arches", []))
        return arches


class _FakeTorch:
    def __init__(self, devices):
        self.cuda = _FakeCuda(devices)


def test_cuda_profile_selects_discrete_nvidia_with_most_memory():
    torch = _FakeTorch([
        {"name": "Intel Iris Xe Graphics", "memory": 1024 * 1024 * 1024},
        {"name": "NVIDIA GeForce RTX 3060", "memory": 12 * 1024 * 1024 * 1024},
        {"name": "NVIDIA GeForce RTX 4070", "memory": 8 * 1024 * 1024 * 1024},
    ])

    assert resolve_qwen3_device_map(torch, "auto", "cuda") == "cuda:1"


def test_rocm_profile_skips_amd_integrated_by_default():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon(TM) Graphics",
            "memory": 2 * 1024 * 1024 * 1024,
            "arch": "gfx1036",
            "supported_arches": ["gfx1036", "gfx1100"],
        },
        {
            "name": "AMD Radeon RX 7900 XTX",
            "memory": 24 * 1024 * 1024 * 1024,
            "arch": "gfx1100",
            "supported_arches": ["gfx1036", "gfx1100"],
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm") == "cuda:1"


def test_rocm_profile_can_allow_integrated_gpu():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon(TM) Graphics",
            "memory": 2 * 1024 * 1024 * 1024,
            "arch": "gfx1036",
            "supported_arches": ["gfx1036"],
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm", allow_integrated_gpu=True) == "cuda:0"


def test_rocm_profile_falls_back_to_cpu_when_only_integrated_gpu_is_visible():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon(TM) Graphics",
            "memory": 2 * 1024 * 1024 * 1024,
            "arch": "gfx1036",
            "supported_arches": ["gfx1036"],
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm") == "cpu"


def test_rocm_profile_falls_back_to_cpu_when_torch_arch_support_is_unknown():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 9070 XT",
            "memory": 16 * 1024 * 1024 * 1024,
            "arch": "gfx1201",
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm") == "cpu"


def test_rocm_profile_falls_back_to_cpu_when_gfx_arch_is_not_in_torch_build():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 9070 XT",
            "memory": 16 * 1024 * 1024 * 1024,
            "arch": "gfx1201",
            "supported_arches": ["gfx1100", "gfx1101"],
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm") == "cpu"


def test_rocm_profile_selects_gpu_when_gfx_arch_is_in_torch_build():
    torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 7900 XTX",
            "memory": 24 * 1024 * 1024 * 1024,
            "arch": "gfx1100",
            "supported_arches": ["gfx1100", "gfx1101"],
        },
    ])

    assert resolve_qwen3_device_map(torch, "auto", "rocm") == "cuda:0"


def test_cpu_profile_forces_cpu():
    torch = _FakeTorch([
        {"name": "NVIDIA GeForce RTX 4070", "memory": 8 * 1024 * 1024 * 1024},
    ])

    assert resolve_qwen3_device_map(torch, "auto", "cpu") == "cpu"


def test_explicit_device_map_is_preserved():
    torch = _FakeTorch([
        {"name": "NVIDIA GeForce RTX 4070", "memory": 8 * 1024 * 1024 * 1024},
    ])

    assert resolve_qwen3_device_map(torch, "cuda:0", "cpu") == "cuda:0"
