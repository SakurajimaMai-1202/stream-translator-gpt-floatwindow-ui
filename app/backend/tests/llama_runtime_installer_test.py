from backend.core import llama_runtime_installer as runtime


def _asset(name: str, size: int = 10):
    return {"name": name, "size": size, "browser_download_url": f"https://example.invalid/{name}"}


def test_latest_runtime_variants_pair_cuda_runtime_and_recommend_profile(monkeypatch):
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

    release = runtime.list_latest_variants("cuda")
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
    variants = runtime.list_latest_variants("rocm")["variants"]
    assert next(item for item in variants if item["id"] == "hip")["recommended"] is True
    assert next(item for item in variants if item["id"] == "vulkan")["recommended"] is False
