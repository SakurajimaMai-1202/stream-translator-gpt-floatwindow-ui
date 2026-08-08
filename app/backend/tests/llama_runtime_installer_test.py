import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from backend.core import llama_runtime_installer as runtime
from backend.core.hardware_detector import GpuDevice


def _asset(name: str, size: int = 10):
    return {"name": name, "size": size, "browser_download_url": f"https://example.invalid/{name}"}


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


def _runtime_zip_bytes(marker: bytes = b"new-runtime") -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        bundle.writestr("runtime/llama-server.exe", marker)
        bundle.writestr("runtime/ggml.dll", b"dll")
    return payload.getvalue()


def test_latest_runtime_variants_pair_cuda_runtime_and_recommend_hardware(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b9999",
        "published_at": "2026-01-01T00:00:00Z",
        "assets": [
            _asset("llama-b9999-bin-win-cpu-x64.zip"),
            _asset("llama-b9999-bin-win-vulkan-x64.zip"),
            _asset("llama-b9999-bin-win-hip-x64.zip"),
            _asset("llama-b9999-bin-win-cuda-12.4-x64.zip", 20),
            _asset("cudart-llama-bin-win-cuda-12.4-x64.zip", 30),
        ],
    })

    release = runtime.list_latest_variants(
        "cpu",
        [GpuDevice(0, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False)],
    )
    cuda = next(item for item in release["variants"] if item["id"] == "cuda12")

    assert release["tag"] == "b9999"
    assert cuda["recommended"] is True
    assert cuda["size"] == 50
    assert len(cuda["assets"]) == 2
    assert next(item for item in release["variants"] if item["id"] == "cpu")["recommended"] is False


def test_rocm_profile_recommends_hip(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b9999",
        "assets": [
            _asset("llama-b9999-bin-win-vulkan-x64.zip"),
            _asset("llama-b9999-bin-win-hip-x64.zip"),
        ],
    })
    variants = runtime.list_latest_variants(
        "cpu",
        [GpuDevice(0, "AMD Radeon RX 7900 XTX", "amd", "unknown", 24576, False)],
    )["variants"]
    assert next(item for item in variants if item["id"] == "hip")["recommended"] is True
    assert next(item for item in variants if item["id"] == "vulkan")["recommended"] is False


def test_cpu_profile_recommends_discrete_nvidia_runtime():
    variant, _ = runtime._recommend_variant_for_hardware(
        "cpu",
        [{"id": item} for item in ("cpu", "cuda12", "hip", "vulkan")],
        [GpuDevice(0, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False)],
    )
    assert variant == "cuda12"


def test_cpu_profile_recommends_discrete_amd_runtime():
    variant, _ = runtime._recommend_variant_for_hardware(
        "cpu",
        [{"id": item} for item in ("cpu", "hip", "vulkan")],
        [GpuDevice(0, "AMD Radeon RX 7900 XTX", "amd", "unknown", 24576, False)],
    )
    assert variant == "hip"


def test_cpu_profile_falls_back_to_cpu_for_integrated_only():
    variant, reason = runtime._recommend_variant_for_hardware(
        "cpu",
        [{"id": item} for item in ("cpu", "cuda12", "hip", "vulkan")],
        [GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "unknown", 2048, True)],
    )
    assert variant == "cpu"
    assert "內顯" in reason


def test_current_cuda_cu_asset_names_are_paired(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b3923",
        "assets": [
            _asset("llama-b3923-bin-win-cuda-cu12.2.0-x64.zip", 20),
            _asset("cudart-llama-bin-win-cu12.2.0-x64.zip", 30),
        ],
    })

    release = runtime.list_latest_variants(
        "cpu",
        [GpuDevice(0, "NVIDIA RTX 4090", "nvidia", "cuda", 24576, False)],
    )
    cuda = release["variants"][0]

    assert cuda["id"] == "cuda12"
    assert cuda["runtime_version"] == "12.2.0"
    assert cuda["installable"] is True
    assert [asset["role"] for asset in cuda["assets"]] == ["runtime", "dependency"]


def test_cuda_variant_without_matching_cudart_is_not_installable(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b4000",
        "assets": [_asset("llama-b4000-bin-win-cuda-cu13.1.0-x64.zip")],
    })

    cuda = runtime.list_latest_variants("cpu", [])["variants"][0]

    assert cuda["id"] == "cuda13"
    assert cuda["installable"] is False
    assert "CUDA Runtime" in cuda["compatibility_error"]


def test_cuda_variant_does_not_pair_a_different_minor_runtime(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b4000",
        "assets": [
            _asset("llama-b4000-bin-win-cuda-cu12.2.0-x64.zip"),
            _asset("cudart-llama-bin-win-cuda-12.4-x64.zip"),
        ],
    })

    cuda = runtime.list_latest_variants("cpu", [])["variants"][0]

    assert cuda["installable"] is False
    assert len(cuda["assets"]) == 1


def test_unknown_hardware_does_not_silently_recommend_cpu(monkeypatch):
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b4000",
        "assets": [_asset("llama-b4000-bin-win-cpu-x64.zip")],
    })

    release = runtime.list_latest_variants("cpu", [])

    assert release["recommended_variant"] == ""
    assert "無法確認" in release["recommendation_reason"]


def test_safe_extract_rejects_parent_traversal(tmp_path):
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "bad")

    with zipfile.ZipFile(archive) as bundle, pytest.raises(RuntimeError, match="不安全路徑"):
        runtime.LlamaRuntimeInstaller._safe_extract(bundle, tmp_path / "extract")


def test_install_tracks_files_and_atomically_activates_runtime(monkeypatch, tmp_path):
    payload = _runtime_zip_bytes()
    sha256 = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(runtime, "llama_root", lambda: tmp_path / "llama")
    monkeypatch.setattr(runtime.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    monkeypatch.setattr(
        runtime.LlamaRuntimeInstaller,
        "_validate_runtime",
        staticmethod(lambda directory: directory / "llama-server.exe"),
    )
    installer = runtime.LlamaRuntimeInstaller()
    installer.begin("cpu")
    installer._set(files=[runtime.asdict(runtime.FileInstallStatus(
        name="llama-b1-bin-win-cpu-x64.zip", total_bytes=len(payload)
    ))])

    installed = installer._download_and_install("b1", {
        "id": "cpu",
        "assets": [{
            "name": "llama-b1-bin-win-cpu-x64.zip",
            "url": "https://example.invalid/runtime.zip",
            "size": len(payload),
            "digest": f"sha256:{sha256}",
            "role": "runtime",
        }],
    })

    assert installed.is_file()
    assert installed.read_bytes() == b"new-runtime"
    assert (tmp_path / "llama" / "active-runtime.txt").read_text(encoding="utf-8") == str(Path("runtimes") / "b1-cpu")
    status = installer.status()
    assert status["files"][0]["state"] == "completed"
    assert status["files"][0]["sha256"] == sha256


def test_digest_failure_never_activates_runtime(monkeypatch, tmp_path):
    payload = _runtime_zip_bytes()
    monkeypatch.setattr(runtime, "llama_root", lambda: tmp_path / "llama")
    monkeypatch.setattr(runtime.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    installer = runtime.LlamaRuntimeInstaller()
    installer.begin("cpu")
    installer._set(files=[runtime.asdict(runtime.FileInstallStatus(name="runtime.zip"))])

    with pytest.raises(RuntimeError, match="SHA-256"):
        installer._download_and_install("b1", {
            "id": "cpu",
            "assets": [{
                "name": "runtime.zip",
                "url": "https://example.invalid/runtime.zip",
                "size": len(payload),
                "digest": f"sha256:{'0' * 64}",
                "role": "runtime",
            }],
        })

    assert not (tmp_path / "llama" / "active-runtime.txt").exists()
    assert installer.status()["files"][0]["state"] == "error"


def test_activation_failure_restores_previous_runtime(monkeypatch, tmp_path):
    payload = _runtime_zip_bytes()
    root = tmp_path / "llama"
    target = root / "runtimes" / "b1-cpu"
    target.mkdir(parents=True)
    (target / "llama-server.exe").write_bytes(b"old-runtime")
    marker = root / "active-runtime.txt"
    marker.write_text(str(Path("runtimes") / "b1-cpu"), encoding="utf-8")
    monkeypatch.setattr(runtime, "llama_root", lambda: root)
    monkeypatch.setattr(runtime.urllib.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(payload))
    monkeypatch.setattr(
        runtime.LlamaRuntimeInstaller,
        "_validate_runtime",
        staticmethod(lambda directory: directory / "llama-server.exe"),
    )
    marker_calls = []

    def fail_new_marker_once(marker_root, relative):
        marker_calls.append(str(relative))
        if len(marker_calls) == 1:
            raise OSError("simulated marker failure")
        (marker_root / "active-runtime.txt").write_text(str(relative), encoding="utf-8")

    monkeypatch.setattr(
        runtime.LlamaRuntimeInstaller,
        "_write_active_marker",
        staticmethod(fail_new_marker_once),
    )
    installer = runtime.LlamaRuntimeInstaller()
    installer.begin("cpu")
    installer._set(files=[runtime.asdict(runtime.FileInstallStatus(name="runtime.zip"))])

    with pytest.raises(OSError, match="marker failure"):
        installer._download_and_install("b1", {
            "id": "cpu",
            "assets": [{
                "name": "runtime.zip",
                "url": "https://example.invalid/runtime.zip",
                "size": len(payload),
                "digest": "",
                "role": "runtime",
            }],
        })

    assert (target / "llama-server.exe").read_bytes() == b"old-runtime"
    assert marker.read_text(encoding="utf-8") == str(Path("runtimes") / "b1-cpu")
    assert not list((root / "runtimes").glob("*.backup-*"))


def test_latest_release_marks_active_runtime_as_current(monkeypatch, tmp_path):
    root = tmp_path / "llama"
    active = root / "runtimes" / "b10312-cuda12"
    active.mkdir(parents=True)
    (active / "llama-server.exe").write_bytes(b"runtime")
    (root / "active-runtime.txt").write_text(
        str(Path("runtimes") / "b10312-cuda12"), encoding="utf-8"
    )
    monkeypatch.setattr(runtime, "llama_root", lambda: root)
    monkeypatch.setattr(runtime, "_release_json", lambda: {
        "tag_name": "b10312", "published_at": "2026-08-08", "assets": []
    })
    monkeypatch.setattr(runtime, "_build_variants", lambda _assets: [{
        "id": "cuda12", "installable": True
    }, {
        "id": "cpu", "installable": True
    }])
    monkeypatch.setattr(runtime, "_recommend_variant_for_hardware", lambda *_args: ("cuda12", "recommended"))

    result = runtime.list_latest_variants(devices=[])

    assert result["is_latest"] is True
    assert result["installed_tag"] == "b10312"
    assert result["installed_variant"] == "cuda12"
    assert result["variants"][0]["installed_latest"] is True
    assert result["variants"][1]["installed_latest"] is False


def test_legacy_runtime_version_can_be_recognized_as_latest(monkeypatch, tmp_path):
    root = tmp_path / "llama"
    root.mkdir()
    (root / "llama-server.exe").write_bytes(b"runtime")
    monkeypatch.setattr(runtime, "llama_root", lambda: root)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {
        "stdout": "version: 10312 (abcdef)", "stderr": ""
    })())

    assert runtime.installed_runtime_build_tag() == "b10312"
