from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.core.app_sync import broker

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/events")
async def stream_app_events():
    return StreamingResponse(
        broker.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
