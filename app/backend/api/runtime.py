from fastapi import APIRouter, HTTPException

from backend.api.config import get_config_manager
from backend.core.runtime_status import build_runtime_status


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/status")
async def get_runtime_status():
    try:
        config = get_config_manager().get_config()
        return {"success": True, "data": build_runtime_status(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
