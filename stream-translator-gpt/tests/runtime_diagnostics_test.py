import stream_translator_gpt.runtime_diagnostics as diagnostics


class _FakeProps:
    def __init__(self, total_memory, arch=None):
        self.total_memory = total_memory
        self.gcnArchName = arch


class _FakeCuda:
    def __init__(self, devices):
        self.devices = devices

    def is_available(self):
        return bool(self.devices)

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


class _FakeVersion:
    cuda = None
    hip = "6.4.0"


class _FakeTorch:
    __version__ = "2.8.0+rocm"
    version = _FakeVersion()

    def __init__(self, devices):
        self.cuda = _FakeCuda(devices)


def test_rocm_diagnostics_without_discrete_gpu_marks_gpu_validation_false():
    fake_torch = _FakeTorch([
        {"name": "AMD Radeon(TM) Graphics", "memory": 2 * 1024 * 1024 * 1024},
    ])

    def fake_import(name):
        if name == "torch":
            return fake_torch
        if name == "qwen_asr":
            return type("FakeQwen", (), {"__version__": "test"})()
        raise ImportError(name)

    original_import = diagnostics.importlib.import_module
    diagnostics.importlib.import_module = fake_import
    try:
        report = diagnostics.build_runtime_diagnostics("rocm", run_torch_smoke=False)
    finally:
        diagnostics.importlib.import_module = original_import

    assert report["torch"]["backend"] == "rocm"
    assert report["selection"]["device_map"] == "cpu"
    assert report["validation"]["runtime_import_validated"] is True
    assert report["validation"]["gpu_inference_validated"] is False
    assert report["validation"]["asr_inference_validated"] is False


def test_rocm_diagnostics_selects_discrete_amd_gpu():
    fake_torch = _FakeTorch([
        {"name": "AMD Radeon(TM) Graphics", "memory": 2 * 1024 * 1024 * 1024},
        {"name": "AMD Radeon RX 7900 XTX", "memory": 24 * 1024 * 1024 * 1024, "arch": "gfx1100", "supported_arches": ["gfx1100"]},
    ])

    def fake_import(name):
        if name == "torch":
            return fake_torch
        if name == "qwen_asr":
            return type("FakeQwen", (), {"__version__": "test"})()
        raise ImportError(name)

    original_import = diagnostics.importlib.import_module
    diagnostics.importlib.import_module = fake_import
    try:
        report = diagnostics.build_runtime_diagnostics("rocm", run_torch_smoke=False)
    finally:
        diagnostics.importlib.import_module = original_import

    assert report["selection"]["device_map"] == "cuda:1"
    assert report["selection"]["selected_device_index"] == 1
    assert report["devices"][0]["is_integrated"] is True
    assert report["devices"][1]["arch_name"] == "gfx1100"
    assert report["devices"][1]["is_supported_by_torch"] is True


def test_rocm_diagnostics_marks_unsupported_gfx_and_falls_back_to_cpu():
    fake_torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 9070 XT",
            "memory": 16 * 1024 * 1024 * 1024,
            "arch": "gfx1201",
            "supported_arches": ["gfx1100"],
        },
    ])

    def fake_import(name):
        if name == "torch":
            return fake_torch
        if name == "qwen_asr":
            return type("FakeQwen", (), {"__version__": "test"})()
        raise ImportError(name)

    original_import = diagnostics.importlib.import_module
    diagnostics.importlib.import_module = fake_import
    try:
        report = diagnostics.build_runtime_diagnostics("rocm", run_torch_smoke=False)
    finally:
        diagnostics.importlib.import_module = original_import

    assert report["selection"]["device_map"] == "cpu"
    assert report["devices"][0]["arch_name"] == "gfx1201"
    assert report["devices"][0]["is_supported_by_torch"] is False
