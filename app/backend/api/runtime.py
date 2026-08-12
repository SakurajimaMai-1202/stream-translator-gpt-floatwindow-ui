from fastapi import APIRouter, HTTPException
import asyncio

from backend.api.config import get_config_manager
from backend.core.runtime_status import build_runtime_status
from backend.core.cpu_asr_sidecar_manager import cpu_asr_sidecar_manager
from backend.core.app_update_manager import app_update_manager


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/status")
async def get_runtime_status():
    try:
        config = get_config_manager().get_config()
        return {"success": True, "data": build_runtime_status(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cpu-asr-sidecar")
async def get_cpu_asr_sidecar_status():
    return {"success": True, "data": cpu_asr_sidecar_manager.status()}


@router.post("/cpu-asr-sidecar/install")
async def install_cpu_asr_sidecar():
    try:
        return {
            "success": True,
            "data": cpu_asr_sidecar_manager.start(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cpu-asr-sidecar/cancel")
async def cancel_cpu_asr_sidecar_install():
    return {"success": True, "data": cpu_asr_sidecar_manager.cancel()}


@router.get("/app-update")
async def get_app_update_status():
    return {"success": True, "data": app_update_manager.status()}


@router.post("/app-update/check")
async def check_app_update():
    # Keep the backend responsive while GitHub handles the one-time startup check.
    data = await asyncio.to_thread(app_update_manager.check)
    return {"success": True, "data": data}


@router.post("/app-update/download")
async def download_app_update():
    try:
        return {"success": True, "data": app_update_manager.start_download()}
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/app-update/cancel")
async def cancel_app_update():
    return {"success": True, "data": app_update_manager.cancel()}


@router.post("/app-update/apply")
async def prepare_app_update_apply():
    try:
        return {"success": True, "data": app_update_manager.create_apply_plan()}
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
