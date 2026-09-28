from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.config import get_config_manager
from backend.core.asr_model_capabilities import list_asr_model_capabilities
from backend.core.runtime_status import build_runtime_status
from backend.core.source_checks import check_device, check_file, check_url


router = APIRouter(prefix="/readiness", tags=["readiness"])


class SourceCheckRequest(BaseModel):
    source: Literal["url", "file", "microphone", "system_audio"]
    value: str = ""
    device_index: int | None = None
    duration_seconds: float = Field(default=1.0, ge=0.2, le=3.0)


@router.get("")
async def readiness():
    config = get_config_manager().get_config()
    runtime = await asyncio.to_thread(build_runtime_status, config)
    return {"success": True, "data": {
        "status": "ready" if runtime.get("status") == "ready" else "unknown",
        "runtime": runtime,
        "asr_models": list_asr_model_capabilities(),
        "source_checks": {
            "url": {"status": "unknown", "action": "check_url"},
            "file": {"status": "unknown", "action": "check_file"},
            "microphone": {"status": "unknown", "action": "capture_test"},
            "system_audio": {"status": "unknown", "action": "capture_test"},
        },
    }}


@router.post("/source-check")
async def source_check(request: SourceCheckRequest):
    try:
        if request.source == "url":
            result = await asyncio.to_thread(check_url, request.value)
        elif request.source == "file":
            result = await asyncio.to_thread(check_file, request.value)
        else:
            result = await asyncio.to_thread(
                check_device, request.source, request.device_index, request.duration_seconds
            )
        return {"success": result.status == "ready", "data": result.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
