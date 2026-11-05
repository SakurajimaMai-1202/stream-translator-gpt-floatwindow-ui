from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List
from backend.core.config_manager import ConfigManager, ConfigValidationError
from fastapi.responses import Response
from pydantic import BaseModel
import asyncio
import yaml
import io
import logging
import time
import httpx
from backend.core.app_sync import publish_app_event
from backend.core.logging_setup import apply_configured_log_level
from backend.core.config_secrets import mask_secrets, omit_secrets, restore_masked_secrets

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)

# Singleton instance
_config_manager_instance = None

def get_config_manager():
    """獲取配置管理器單例"""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager()
    return _config_manager_instance


def _write_config(method, data=None):
    """Resolve the manager on the worker; mutations restore secrets under their lock."""
    manager = get_config_manager()
    if data is None:
        result = getattr(manager, method)()
    else:
        result = getattr(manager, method)(data)
    try:
        # A level refresh must never turn a successful save into an error.
        apply_configured_log_level(getattr(manager, "config_path", None))
    except Exception:
        logger.warning("Unable to apply the saved log level", exc_info=True)
    return result


def _read_config(method="get_config"):
    """Keep singleton initialization and the complete read off the event loop."""
    return getattr(get_config_manager(), method)()


@router.get("/hy-mt2-glossary-presets")
async def get_hy_mt2_glossary_presets():
    """Expose built-in profiles so the editor previews the runtime source of truth."""
    from backend.core.hy_mt2_glossary_presets import PRESETS, CATEGORY_LABELS, PRESET_ASR_VARIANTS
    return {"categories": [
        {"id": name, "label": CATEGORY_LABELS[name], "terms": dict(terms),
         "asr_variants": {source: list(aliases) for source, aliases in PRESET_ASR_VARIANTS[name].items()}}
        for name, terms in PRESETS.items()
    ]}


@router.post("/hy-mt2-health")
async def check_hy_mt2_backend():
    """Check the saved HY-MT2 endpoint with one short inference request."""
    manager = await asyncio.to_thread(get_config_manager)
    config = await asyncio.to_thread(manager.get_config)
    if config.get("translation", {}).get("backend") == "none":
        raise HTTPException(status_code=400, detail="請先選擇翻譯模型")
    try:
        args = await asyncio.to_thread(manager.to_main_args, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    provider = args.get("translation_provider")
    if provider not in {"openai", "openai_compatible", "lm_studio", "llama_cpp"}:
        raise HTTPException(status_code=400, detail="此檢查僅支援 OpenAI 相容的 HY-MT2 後端")
    base_url = str(args.get("gpt_base_url") or "").rstrip("/")
    model = str(args.get("gpt_model") or "").strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="請填寫伺服器網址與模型 ID")
    endpoint = f"{base_url if base_url.endswith('/v1') else base_url + '/v1'}/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = str(args.get("openai_api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "將「こんにちは」翻譯為繁體中文，只輸出譯文。"}],
        "max_tokens": 32,
        "temperature": 0.7,
        "top_p": 0.6,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="模型回應逾時（15 秒）") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="無法連線到目前選擇的翻譯後端") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"翻譯後端回傳 HTTP {response.status_code}；請檢查模型 ID 與伺服器設定")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="翻譯後端回應格式不正確") from exc
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=502, detail="翻譯後端回傳空白結果")
    return {
        "success": True,
        "provider": provider,
        "model": model,
        "sample": content.strip()[:120],
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


@router.get("")
async def get_config():
    """獲取完整配置"""
    try:
        return {"success": True, "data": mask_secrets(await asyncio.to_thread(_read_config))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("")
async def update_full_config(data: Dict[str, Any], request: Request):
    """更新完整配置"""
    try:
        updates = dict(data)
        if 'custom_models' in updates:
            translation = dict(updates.get('translation') or {})
            translation['custom_models'] = updates.pop('custom_models')
            updates['translation'] = translation
        updated_config = await asyncio.to_thread(
            _write_config, "update_config",
            updates,
        )
        await publish_app_event("config.updated", {
            "section": "*",
            "config": mask_secrets(updated_config),
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": mask_secrets(updated_config)}
    except ConfigValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid configuration structure") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=List[Dict[str, Any]])
async def get_config_status():
    """獲取配置狀態警告"""
    return await asyncio.to_thread(_read_config, "get_config_status")

@router.patch("/{section}")
async def update_section(section: str, data: Dict[str, Any], request: Request):
    """更新配置區段"""
    try:
        full_config = await asyncio.to_thread(
            _write_config, "update_config",
            {section: data},
        )
        await publish_app_event("config.updated", {
            "section": section,
            "config": mask_secrets(full_config),
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": mask_secrets(full_config.get(section))}
    except ConfigValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid configuration structure") from e
    except Exception as e:
        logger.exception("Failed to save config section %s", section)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_config(request: Request):
    """重置配置"""
    try:
        reset_config_data = await asyncio.to_thread(_write_config, "reset_to_defaults")
        await publish_app_event("config.reset", {
            "config": mask_secrets(reset_config_data),
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": mask_secrets(reset_config_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_config(include_secrets: bool = False):
    """匯出配置為 YAML 檔案"""
    try:
        # 獲取當前配置
        config = await asyncio.to_thread(_read_config)
        
        if not include_secrets:
            config = omit_secrets(config)
        # 轉換為 YAML 字串
        yaml_content = yaml.dump(config, allow_unicode=True, sort_keys=False)
        
        # 返回檔案下載回應
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={"Content-Disposition": "attachment; filename=config.yaml"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯出配置失敗: {str(e)}")

@router.post("/import")
async def import_config(file_content: dict, request: Request):
    """匯入 YAML 配置內容 (接收 JSON 包含 content 欄位或直接 YAML 轉換的 dict)"""
    try:
        if isinstance(file_content.get("content"), str):
            file_content = yaml.safe_load(file_content["content"])
        if not isinstance(file_content, dict):
            raise HTTPException(status_code=400, detail="配置根節點必須是字典")
        # 如果接收到的是字典（已經由 FastAPI 透過 JSON 解析）
        # 我們假設前端會傳送整個配置結構
        if not file_content:
            raise HTTPException(status_code=400, detail="配置內容為空")

        imported_config = await asyncio.to_thread(
            _write_config, "replace_config", file_content)
            
        await publish_app_event("config.imported", {
            "config": mask_secrets(imported_config),
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "message": "配置已成功匯入"}
    except HTTPException:
        raise
    except (yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid configuration structure or YAML") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入配置失敗: {str(e)}")

# 為了支援直接上傳檔案，我們增加一個使用 UploadFile 的端點
from fastapi import UploadFile, File

@router.post("/import/file")
async def import_config_file(request: Request, file: UploadFile = File(...)):
    """透過檔案上傳匯入配置"""
    try:
        content = await file.read()
        try:
            # 解析 YAML
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"YAML 格式錯誤: {str(e)}")
            
        if not isinstance(config_data, dict):
             raise HTTPException(status_code=400, detail="配置檔案格式不正確 (根節點必須是字典)")
             
        imported_config = await asyncio.to_thread(
            _write_config, "replace_config", config_data)
        
        await publish_app_event("config.imported", {
            "config": mask_secrets(imported_config),
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {
            "success": True,
            "message": "配置檔案已成功匯入",
            "data": mask_secrets(imported_config),
        }
    except HTTPException:
        raise
    except (yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid configuration structure or YAML") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入檔案失敗: {str(e)}")

class TestConnectionRequest(BaseModel):
    backend: str
    section: str = "translation"
    api_key: str
    base_url: str | None = None
    proxy: str | None = None

@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest):
    """測試 API 金鑰與連線"""
    backend = request.backend.lower()
    if request.section not in {"translation", "transcription"}:
        raise HTTPException(status_code=400, detail="不支援的配置區段")
    translation = (await asyncio.to_thread(_read_config)).get(request.section, {})
    key_field = "google_api_key" if backend == "gemini" else "openai_api_key"
    api_key = restore_masked_secrets(
        {key_field: request.api_key}, translation)[key_field]
    api_key = api_key.strip() if api_key else ""
    base_url = request.base_url.strip() if request.base_url else None
    proxy = request.proxy.strip() if request.proxy else None
    
    if not api_key:
        return {"success": False, "message": "請輸入 API 金鑰"}
        
    if backend == "gpt":
        try:
            from openai import OpenAI
            import httpx
            
            client_kwargs = {"api_key": api_key, "timeout": 10.0}
            if base_url:
                client_kwargs["base_url"] = base_url
            if proxy:
                client_kwargs["http_client"] = httpx.Client(proxy=proxy)
                
            client = OpenAI(**client_kwargs)
            client.models.list()
            return {"success": True, "message": "連線測試成功！API 金鑰有效。"}
        except Exception as e:
            logger.debug("OpenAI 連線測試失敗", exc_info=True)
            return {"success": False, "message": f"OpenAI 連線測試失敗: {str(e)}"}
            
    elif backend == "gemini":
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=api_key)
            list(genai.list_models())
            return {"success": True, "message": "連線測試成功！API 金鑰有效。"}
        except Exception as e:
            logger.debug("Gemini 連線測試失敗", exc_info=True)
            return {"success": False, "message": f"Gemini 連線測試失敗: {str(e)}"}
            
    else:
        return {"success": False, "message": f"不支援的測試後端: {backend}"}



# Keep terminology administration under the same app registration/auth as config.
_config_router = router
router = APIRouter()
router.include_router(_config_router)
from backend.api.terminology import router as terminology_router
router.include_router(terminology_router)
