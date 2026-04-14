from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List
from backend.core.config_manager import ConfigManager
from fastapi.responses import Response
from pydantic import BaseModel
import yaml
import io
from backend.core.app_sync import publish_app_event

router = APIRouter(prefix="/config", tags=["config"])

# Singleton instance
_config_manager_instance = None

def get_config_manager():
    """獲取配置管理器單例"""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager()
    return _config_manager_instance


@router.get("")
async def get_config():
    """獲取完整配置"""
    try:
        return {"success": True, "data": get_config_manager().get_config()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("")
async def update_full_config(data: Dict[str, Any], request: Request):
    """更新完整配置"""
    try:
        # 更新所有區段
        for section, section_data in data.items():
            if isinstance(section_data, dict):
                get_config_manager().update_section(section, section_data)
            elif section == 'custom_models':
                # 特殊處理自訂模型列表
                get_config_manager().config['translation']['custom_models'] = section_data
                get_config_manager().save()
        updated_config = get_config_manager().get_config()
        await publish_app_event("config.updated", {
            "section": "*",
            "config": updated_config,
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": updated_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=List[Dict[str, Any]])
async def get_config_status():
    """獲取配置狀態警告"""
    return get_config_manager().get_config_status()

@router.patch("/{section}")
async def update_section(section: str, data: Dict[str, Any], request: Request):
    """更新配置區段"""
    try:
        # 特殊處理 llama 區段，避免覆蓋 custom_presets
        if section == 'llama':
            current_config = get_config_manager().get_config().get('llama', {})
            current_presets = current_config.get('custom_presets', {})
            incoming_presets = data.get('custom_presets')
            
            # Debug logging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Updating llama section. Current presets: {list(current_presets.keys())}, Incoming presets: {list(incoming_presets.keys()) if incoming_presets else 'None'}")
            
            # 如果更新資料中沒有 custom_presets，但現有配置中有，則保留現有的
            if current_presets and not incoming_presets:
                data['custom_presets'] = current_presets
                logger.info(f"Preserved custom_presets: {list(current_presets.keys())}")
        
        get_config_manager().update_section(section, data)
        full_config = get_config_manager().get_config()
        await publish_app_event("config.updated", {
            "section": section,
            "config": full_config,
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": full_config.get(section)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_config(request: Request):
    """重置配置"""
    try:
        get_config_manager().reset_to_defaults()
        reset_config_data = get_config_manager().get_config()
        await publish_app_event("config.reset", {
            "config": reset_config_data,
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "data": reset_config_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_config():
    """匯出配置為 YAML 檔案"""
    try:
        # 獲取當前配置
        config = get_config_manager().get_config()
        
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
        # 如果接收到的是字典（已經由 FastAPI 透過 JSON 解析）
        # 我們假設前端會傳送整個配置結構
        if not file_content:
            raise HTTPException(status_code=400, detail="配置內容為空")

        # 這裡我們做一個特殊的處理：
        # 如果因為某些原因前端傳來的是 {"content": "yaml string"}，我們解析它
        # 但通常我們期望前端解析好 YAML 後傳送 JSON 對象，或者我們允許上傳檔案
        # 為了簡化前端實作（前端讀取 YAML -> 轉 OBJ -> 傳送），我們這裡直接接收 Dict
        # 並驗證基本的 key 是否存在
        
        required_keys = ['general', 'input', 'transcription']
        for key in required_keys:
            if key not in file_content:
                # 寬容模式：如果是 partial config，可能不報錯，但在這裡我們做全量替換
                pass 
        
        # 更新配置
        # 我們使用 update_full_config 的邏輯，但這裡我們可以直接呼叫 save
        # 更安全的做法是逐個 section 更新
        
        for section, section_data in file_content.items():
            if isinstance(section_data, dict):
                get_config_manager().update_section(section, section_data)
        
        # 強制保存
        get_config_manager().save()
            
        imported_config = get_config_manager().get_config()
        await publish_app_event("config.imported", {
            "config": imported_config,
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "message": "配置已成功匯入"}
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
             
        # 更新配置
        for section, section_data in config_data.items():
            if isinstance(section_data, dict):
                get_config_manager().update_section(section, section_data)
        
        get_config_manager().save()
        
        imported_config = get_config_manager().get_config()
        await publish_app_event("config.imported", {
            "config": imported_config,
            "source_client_id": request.headers.get("X-Client-Id", ""),
        })
        return {"success": True, "message": "配置檔案已成功匯入"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"匯入檔案失敗: {str(e)}")
