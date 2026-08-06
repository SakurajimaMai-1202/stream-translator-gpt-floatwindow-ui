from fastapi import APIRouter, HTTPException
from backend.api.config import get_config_manager
from backend.core.runtime_status import build_runtime_status
from backend.core.cpu_asr_sidecar_manager import cpu_asr_sidecar_manager


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
