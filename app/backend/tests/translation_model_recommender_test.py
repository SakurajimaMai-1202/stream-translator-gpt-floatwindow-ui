from backend.core.hardware_detector import GpuDevice
from backend.core.translation_model_recommender import build_translation_model_recommendations


def gpu(name: str, memory_mb: int, integrated: bool = False) -> GpuDevice:
    return GpuDevice(index=0, name=name, vendor="nvidia", backend="cuda", memory_mb=memory_mb, is_integrated=integrated)


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
    assert result["selected_gpu"] is None
    assert {model["fit"] for model in result["models"]} == {"unknown"}


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
    assert four_gb["models"][0]["fit"] == "possible"


def test_sakura_parameters_distinguish_model_card_facts_from_app_defaults():
    result = build_translation_model_recommendations([gpu("NVIDIA GeForce RTX", 24576)])
    galtransl = next(model for model in result["models"] if model["id"] == "sakura-galtransl-v4-4b")
    sakura14b = next(model for model in result["models"] if model["id"] == "sakura-14b-qwen3-v15")
    assert galtransl["deployment_config"]["n_ctx"] == 2048
    assert "模型卡要求" in galtransl["parameter_source"]
    assert "未公布" in sakura14b["parameter_source"]
