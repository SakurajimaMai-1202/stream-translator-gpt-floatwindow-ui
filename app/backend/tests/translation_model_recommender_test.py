from backend.core.hardware_detector import GpuDevice
from backend.core.translation_model_recommender import build_translation_model_recommendations


def gpu(name: str, memory_mb: int, integrated: bool = False, vendor: str = "nvidia") -> GpuDevice:
    backend = "cuda" if vendor == "nvidia" else "rocm" if vendor == "amd" else "unknown"
    return GpuDevice(index=0, name=name, vendor=vendor, backend=backend, memory_mb=memory_mb, is_integrated=integrated)


def test_recommendations_use_largest_discrete_gpu_and_rank_fits_first():
    result = build_translation_model_recommendations([
        gpu("Integrated Graphics", 2048, True),
        gpu("NVIDIA GeForce RTX", 8192),
    ])
    assert result["selected_gpu"]["name"] == "NVIDIA GeForce RTX"
    assert result["vram_gb"] == 8.0
    assert result["models"][0]["fit"] == "recommended"
    assert next(model for model in result["models"] if model["id"] == "hy-mt2-7b")["fit"] == "recommended"


def test_unknown_vram_does_not_claim_a_model_is_recommended():
    result = build_translation_model_recommendations([gpu("NVIDIA GPU", 0)])
    assert result["selected_gpu"]["memory_mb"] == 0
    assert {model["fit"] for model in result["models"]} == {"unknown"}
    assert result["simple_setup"]["model_id"] == "hy-mt2-iq3-xxs"


def test_unknown_amd_vram_keeps_simple_mode_available_without_virtual_monitor():
    result = build_translation_model_recommendations([
        GpuDevice(0, "Meta Virtual Monitor", "unknown", "unknown", None, False),
        GpuDevice(2, "AMD Radeon RX 9070 XT", "amd", "unknown", None, False),
    ])
    assert result["selected_gpu"]["name"] == "AMD Radeon RX 9070 XT"
    assert result["vram_tier"] == "unknown"
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-iq3-xxs"


def test_cpu_package_uses_dxgi_vram_for_rx_9070_xt(monkeypatch):
    from backend.core import hardware_detector as detector

    dxgi = GpuDevice(0, "AMD Radeon RX 9070 XT", "amd", "unknown", 16384, False, source="dxgi")
    windows = GpuDevice(2, "AMD Radeon RX 9070 XT", "amd", "unknown", None, False,
                        source="win32_video_controller", raw={"AdapterRAM": 4293918720})
    virtual = GpuDevice(0, "Meta Virtual Monitor", "unknown", "unknown", None, False)
    monkeypatch.setattr(detector, "detect_runtime_python_gpus", lambda: [])
    monkeypatch.setattr(detector, "detect_torch_gpus", lambda: [])
    monkeypatch.setattr(detector, "detect_windows_dxgi_adapters", lambda: [dxgi])
    monkeypatch.setattr(detector, "detect_nvidia_smi_gpus", lambda: [])
    monkeypatch.setattr(detector, "detect_windows_video_controllers", lambda: [virtual, windows])

    result = build_translation_model_recommendations(detector.detect_gpus(force_refresh=True))
    assert result["selected_gpu"]["name"] == "AMD Radeon RX 9070 XT"
    assert result["vram_gb"] == 16.0
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-q6-k"


def test_gemma_e4b_recommendation_uses_qat_repository():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 12288)])
    model = next(model for model in result["models"] if model["id"] == "gemma-4-e4b-qat")
    assert model["repo"] == "unsloth/gemma-4-E4B-it-qat-GGUF"
    assert model["url"].endswith("/gemma-4-E4B-it-qat-GGUF/tree/main")


def test_sakura_models_are_labeled_for_novel_and_game_text():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 12288)])
    sakura_models = [model for model in result["models"] if model["repo"].startswith("SakuraLLM/")]
    assert sakura_models
    assert {model["category"] for model in sakura_models} == {"novel_game"}
    assert all(model["use_case"] == "日文小說／Galgame 遊戲文本專用" for model in sakura_models)


def test_hymt2_uses_official_sampling_recommendation():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 12288)])
    model = next(model for model in result["models"] if model["id"] == "hy-mt2-7b")
    assert model["repo"] == "mradermacher/Hy-MT2-7B-i1-GGUF"
    assert model["recommended_quant"] == "i1-Q4_K_M"
    assert model["deployment_config"] == {
        "temp": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05,
        "n_ctx": 4096, "n_predict": 4096
    }


def test_every_recommended_model_has_deployment_parameters():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 24576)])
    assert all(model.get("deployment_config") for model in result["models"])
    assert all(model.get("parameter_source") for model in result["models"])


def test_vram_recommendations_are_derived_from_reference_quant_file_sizes():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 24576)])
    models = {model["id"]: model for model in result["models"]}
    assert (models["gemma-4-e2b-qat"]["model_size_gb"], models["gemma-4-e2b-qat"]["min_vram_gb"], models["gemma-4-e2b-qat"]["comfortable_vram_gb"]) == (2.62, 4, 6)
    assert (models["gemma-4-e4b-qat"]["model_size_gb"], models["gemma-4-e4b-qat"]["min_vram_gb"], models["gemma-4-e4b-qat"]["comfortable_vram_gb"]) == (4.22, 4, 8)
    assert (models["hy-mt2-7b"]["model_size_gb"], models["hy-mt2-7b"]["min_vram_gb"], models["hy-mt2-7b"]["comfortable_vram_gb"]) == (4.7, 6, 8)
    assert (models["sakura-14b-qwen3-v15"]["model_size_gb"], models["sakura-14b-qwen3-v15"]["min_vram_gb"], models["sakura-14b-qwen3-v15"]["comfortable_vram_gb"]) == (8.18, 10, 12)
    assert (models["gemma-4-e2b-qat"]["minimum_quant"], models["gemma-4-e2b-qat"]["minimum_size_gb"]) == ("UD-Q2_K_XL", 2.19)
    assert (models["gemma-4-e4b-qat"]["minimum_quant"], models["gemma-4-e4b-qat"]["minimum_size_gb"]) == ("UD-Q2_K_XL", 3.22)
    assert (models["hy-mt2-7b"]["minimum_quant"], models["hy-mt2-7b"]["minimum_size_gb"]) == ("i1-IQ3_S", 3.46)


def test_hymt2_is_first_when_it_fits_but_does_not_override_hardware_fit():
    eight_gb = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 8192)])
    assert eight_gb["models"][0]["id"] == "hy-mt2-7b"
    assert eight_gb["models"][0]["app_preferred"] is True

    four_gb = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 4096)])
    assert four_gb["models"][0]["id"] != "hy-mt2-7b"
    assert four_gb["models"][0]["fit"] == "recommended"
    assert four_gb["models"][0]["id"] == "index-translate-2b"


def test_sakura_parameters_distinguish_model_card_facts_from_app_defaults():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 24576)])
    galtransl = next(model for model in result["models"] if model["id"] == "sakura-galtransl-v4-4b")
    sakura14b = next(model for model in result["models"] if model["id"] == "sakura-14b-qwen3-v15")
    assert galtransl["deployment_config"]["n_ctx"] == 2048
    assert "模型卡要求" in galtransl["parameter_source"]
    assert "未公布" in sakura14b["parameter_source"]


def test_simple_setup_uses_small_model_for_four_gb_nvidia():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 4096)])
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-iq4-nl"
    assert result["simple_setup"]["quant"] == "i1-IQ4_NL"
    assert result["vram_tier"] == "4_to_8gb"


def test_simple_setup_uses_q6_model_for_eight_gb_nvidia():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 8192)])
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-q6-k"
    assert result["simple_setup"]["quant"] == "i1-Q6_K"
    assert result["vram_tier"] == "8gb_plus"


def test_simple_setup_uses_small_gpu_model_below_four_gb():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 3072)])
    assert result["simple_setup"]["supported"] is True
    assert result["simple_setup"]["model_id"] == "hy-mt2-iq3-xxs"
    assert result["vram_tier"] == "under_4gb"
    assert "GPU Runtime" in result["simple_setup"]["reason"]


def test_simple_setup_supports_amd_in_middle_and_high_tiers():
    middle = build_translation_model_recommendations([gpu("AMD Radeon RX", 6144, vendor="amd")])
    high = build_translation_model_recommendations([gpu("AMD Radeon RX", 12288, vendor="amd")])
    assert middle["simple_setup"]["model_id"] == "hy-mt2-iq4-nl"
    assert middle["vram_tier"] == "4_to_8gb"
    assert high["simple_setup"]["model_id"] == "hy-mt2-q6-k"
    assert high["vram_tier"] == "8gb_plus"


def test_simple_setup_supports_arc_with_known_or_unknown_vram():
    arc = build_translation_model_recommendations([gpu("Intel(R) Arc(TM) A750 Graphics", 8192, vendor="intel")])
    assert arc["simple_setup"]["supported"] is True
    assert arc["simple_setup"]["model_id"] == "hy-mt2-q6-k"
    unknown = build_translation_model_recommendations([gpu("Intel Arc A750", None, vendor="intel")])
    assert unknown["selected_gpu"]["vendor"] == "intel"
    assert unknown["simple_setup"]["model_id"] == "hy-mt2-iq3-xxs"


def test_simple_setup_excludes_intel_integrated_graphics():
    for name in ("Intel UHD Graphics", "Intel Arc Graphics"):
        result = build_translation_model_recommendations([gpu(name, 8192, integrated=True, vendor="intel")])
        assert result["simple_setup"]["supported"] is False


def test_index_models_use_official_gguf_sources_and_separate_memory_fits():
    four_gb = build_translation_model_recommendations([gpu("NVIDIA GPU", 4096)])
    six_gb = build_translation_model_recommendations([gpu("NVIDIA GPU", 6144)])
    eight_gb = build_translation_model_recommendations([gpu("NVIDIA GPU", 8192)])
    by_id = lambda result: {model["id"]: model for model in result["models"]}
    small = by_id(four_gb)["index-translate-2b"]
    large = by_id(four_gb)["index-translate-9b"]
    assert small["repo"] == "IndexTeam/Index-Translate-2B-GGUF"
    assert large["repo"] == "IndexTeam/Index-Translate-9B-GGUF"
    assert small["url"].endswith("/Index-Translate-2B-GGUF/tree/main")
    assert (small["model_size_gb"], small["minimum_size_gb"]) == (1.31, 0.99)
    assert (large["model_size_gb"], large["minimum_size_gb"]) == (5.78, 3.91)
    assert (small["min_vram_gb"], small["comfortable_vram_gb"], small["fit"]) == (4, 4, "recommended")
    assert (large["min_vram_gb"], large["comfortable_vram_gb"], large["fit"]) == (6, 8, "not_recommended")
    assert by_id(six_gb)["index-translate-9b"]["fit"] == "possible"
    assert by_id(eight_gb)["index-translate-9b"]["fit"] == "recommended"
    for model in (small, large):
        assert model["recommended_quant"] == "Q4_K_M"
        assert model["minimum_quant"] == "Q2_K"
        assert model["deployment_config"]["temp"] == 0
        assert model["deployment_config"]["n_predict"] == 1024
        assert "本程式" in model["parameter_source"]
        assert "尚未實測" in model["runtime_note"]
    # Catalog additions do not change the simple-setup download choice.
    assert four_gb["simple_setup"]["model_id"] == "hy-mt2-iq4-nl"
