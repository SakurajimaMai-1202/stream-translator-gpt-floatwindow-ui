from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from .hardware_detector import GpuDevice

VRAM_TIERS_GB = (4, 6, 8, 10, 12, 16, 24, 32, 48)


def _next_vram_tier(required_gb: float) -> int:
    return next((tier for tier in VRAM_TIERS_GB if tier >= required_gb), int(required_gb + 0.999))


MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "gemma-4-e2b-qat",
        "name": "Gemma 4 E2B IT QAT",
        "repo": "unsloth/gemma-4-E2B-it-qat-GGUF",
        "url": "https://huggingface.co/unsloth/gemma-4-E2B-it-qat-GGUF/tree/main",
        "recommended_quant": "UD-Q4_K_XL",
        "model_size_gb": 2.62,
        "minimum_quant": "UD-Q2_K_XL",
        "minimum_size_gb": 2.19,
        "category": "general",
        "summary": "低 VRAM 首選；適合日常多語翻譯與希望保留 ASR 顯存的裝置。",
        "languages": ["多語"],
        "deployment_config": {"temp": 1.0, "top_p": 0.95, "top_k": 64, "repeat_penalty": 1.0, "n_ctx": 4096, "n_predict": 1024},
        "parameter_source": "Gemma 4 官方採樣建議與 1024-token 範例；上下文採即時翻譯平衡值",
    },
    {
        "id": "gemma-4-e4b-qat",
        "name": "Gemma 4 E4B IT QAT",
        "repo": "unsloth/gemma-4-E4B-it-qat-GGUF",
        "url": "https://huggingface.co/unsloth/gemma-4-E4B-it-qat-GGUF/tree/main",
        "recommended_quant": "UD-Q4_K_XL",
        "model_size_gb": 4.22,
        "minimum_quant": "UD-Q2_K_XL",
        "minimum_size_gb": 3.22,
        "category": "general",
        "summary": "QAT 版本兼顧品質與低記憶體載入；適合多語翻譯，8 GB 以上顯卡較從容。",
        "languages": ["多語"],
        "deployment_config": {"temp": 1.0, "top_p": 0.95, "top_k": 64, "repeat_penalty": 1.0, "n_ctx": 4096, "n_predict": 1024},
        "parameter_source": "Gemma 4 官方採樣建議與 1024-token 範例；上下文採即時翻譯平衡值",
    },
    {
        "id": "hy-mt2-7b",
        "name": "Hy-MT2 7B",
        "repo": "mradermacher/Hy-MT2-7B-i1-GGUF",
        "url": "https://huggingface.co/mradermacher/Hy-MT2-7B-i1-GGUF/tree/main",
        "recommended_quant": "i1-Q4_K_M",
        "model_size_gb": 4.7,
        "minimum_quant": "i1-IQ3_S",
        "minimum_size_gb": 3.46,
        "category": "translation",
        "app_preferred": True,
        "app_preference_reason": "本程式具備 Hy-MT2 專用提示詞、術語與上下文策略，建議優先使用。",
        "summary": "新一代 33 語專用翻譯模型；支援繁體中文與複雜翻譯指令，並需為 KV cache 與 ASR 保留額外顯存。",
        "languages": ["33 語", "繁體中文"],
        "deployment_config": {"temp": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05, "n_ctx": 4096, "n_predict": 4096},
        "parameter_source": "Tencent Hy-MT2 1.8B／7B 官方推論建議",
        "runtime_note": "請使用支援 Hy-MT2／hunyuan-dense 架構的近期 llama.cpp；若載入失敗請先更新 Runtime。",
    },
    {
        "id": "sakura-galtransl-v4-4b",
        "name": "Sakura GalTransl v4 4B",
        "repo": "SakuraLLM/GalTransl-v4-4B-2601",
        "url": "https://huggingface.co/SakuraLLM/GalTransl-v4-4B-2601/tree/main",
        "recommended_quant": "Q5_K_S",
        "model_size_gb": 2.82,
        "minimum_quant": "Q5_K_S（此 repo 最低）",
        "minimum_size_gb": 2.82,
        "category": "novel_game",
        "use_case": "日文小說／Galgame 遊戲文本專用",
        "summary": "針對日文小說、Galgame 與 ACGN 遊戲文本調校；適合即時遊戲翻譯，不定位為通用多語模型。",
        "languages": ["日文", "簡中"],
        "deployment_config": {"temp": 0.2, "top_p": 0.9, "top_k": 20, "repeat_penalty": 1.05, "n_ctx": 2048, "n_predict": 512},
        "parameter_source": "模型卡要求 context ≥ 2048；採樣值為本程式低發散即時翻譯建議",
    },
    {
        "id": "sakura-14b-qwen3-v15",
        "name": "Sakura 14B Qwen3 v1.5",
        "repo": "SakuraLLM/Sakura-14B-Qwen3-v1.5-GGUF",
        "url": "https://huggingface.co/SakuraLLM/Sakura-14B-Qwen3-v1.5-GGUF/tree/main",
        "recommended_quant": "IQ4_XS",
        "model_size_gb": 8.18,
        "minimum_quant": "IQ4_XS（此 repo 最低）",
        "minimum_size_gb": 8.18,
        "category": "novel_game",
        "use_case": "日文小說／Galgame 遊戲文本專用",
        "summary": "針對日文小說、Galgame 與 ACGN 遊戲文本品質的較新 14B 版本；不定位為通用多語模型。",
        "languages": ["日文", "簡中"],
        "deployment_config": {"temp": 0.2, "top_p": 0.9, "top_k": 20, "repeat_penalty": 1.05, "n_ctx": 4096, "n_predict": 1024},
        "parameter_source": "模型卡未公布採樣值；使用本程式小說／遊戲文本低發散建議",
    },
)


def build_translation_model_recommendations(devices: Iterable[GpuDevice]) -> dict[str, Any]:
    detected = list(devices)
    discrete = [device for device in detected if not device.is_integrated]
    usable = [device for device in discrete if device.memory_mb]
    selected = max(usable, key=lambda device: int(device.memory_mb or 0), default=None)
    vram_gb = round((selected.memory_mb or 0) / 1024, 1) if selected else None

    models: list[dict[str, Any]] = []
    for position, source in enumerate(MODEL_CATALOG):
        model = dict(source)
        model_size_gb = float(model["model_size_gb"])
        minimum_size_gb = float(model["minimum_size_gb"])
        model["min_vram_gb"] = _next_vram_tier(minimum_size_gb + 0.75)
        model["comfortable_vram_gb"] = _next_vram_tier(model_size_gb + 2.0)
        model["vram_basis"] = (
            f"最低依 {model['minimum_quant']} {minimum_size_gb:g} GB 加 0.75 GB；"
            f"建議依 {model['recommended_quant']} {model_size_gb:g} GB 加 2 GB，再取常見 VRAM 級距。"
        )
        if vram_gb is None:
            fit = "unknown"
            reason = "無法可靠讀取獨立顯卡 VRAM，請依模型容量手動選擇。"
        elif vram_gb >= model["comfortable_vram_gb"]:
            fit = "recommended"
            reason = f"{vram_gb:g} GB VRAM 可使用建議量化 {model['recommended_quant']}。"
        elif vram_gb >= model["min_vram_gb"]:
            fit = "possible"
            reason = f"{vram_gb:g} GB 可使用最低量化 {model['minimum_quant']}；品質可能下降，並建議 CPU ASR。"
        else:
            fit = "not_recommended"
            reason = f"至少建議 {model['min_vram_gb']} GB VRAM；可改用更小量化或 CPU 混合卸載。"
        model.update({"fit": fit, "fit_reason": reason, "catalog_order": position})
        models.append(model)

    rank = {"recommended": 0, "possible": 1, "unknown": 2, "not_recommended": 3}
    models.sort(key=lambda item: (
        rank[item["fit"]],
        0 if item.get("app_preferred") else 1,
        item["comfortable_vram_gb"],
        item["catalog_order"],
    ))
    return {
        "selected_gpu": asdict(selected) if selected else None,
        "detected_gpus": [asdict(device) for device in detected],
        "vram_gb": vram_gb,
        "models": models,
        "notice": "VRAM 建議以指定量化的實際檔案大小加上 llama.cpp／KV cache 餘量計算；ASR 同時使用 GPU 時需另外預留顯存。",
    }
