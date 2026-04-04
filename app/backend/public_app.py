"""
公開字幕端口服務器
僅暴露字幕顯示所需的最小 API，不含管理配置端點。
可安全地分享給外部用戶。
"""
import json
import logging
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.core.translator import active_translations, get_task
from backend.api.config import get_config_manager

logger = logging.getLogger(__name__)


def _is_subtitle_sharing_enabled() -> bool:
    """讀取目前設定中的字幕分享開關。"""
    try:
        cfg = get_config_manager().get_config()
        if not isinstance(cfg, dict):
            return False
        return bool(cfg.get("server", {}).get("enable_subtitle_sharing", True))
    except Exception:
        return False

# 修正 Windows MIME 解析
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

public_app = FastAPI(
    title="字幕顯示服務 (Public)",
    description="僅供字幕顯示使用的公開端口，不含管理功能",
    docs_url=None,     # 禁用 Swagger UI
    redoc_url=None,    # 禁用 ReDoc
    openapi_url=None,  # 禁用 OpenAPI schema
)

# CORS：允許所有來源（因為是公開分享端點）
public_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@public_app.middleware("http")
async def subtitle_sharing_guard(request: Request, call_next):
    """字幕分享關閉時，封鎖公開端口全部路徑。"""
    if not _is_subtitle_sharing_enabled():
        return JSONResponse(
            status_code=404,
            content={"detail": "Subtitle sharing is disabled"},
        )
    return await call_next(request)


# ─── 字幕 API ────────────────────────────────────────────────────────────────

@public_app.get("/api/translation/active-task")
async def public_get_active_task():
    """取得目前正在執行中的翻譯任務（供手機/電腦版字幕頁使用）"""
    for task_id, context in active_translations.items():
        if context.running:
            return {"success": True, "task_id": task_id}
    return {"success": False, "task_id": None}


@public_app.get("/api/translation/status")
async def public_get_translation_status():
    """取得所有翻譯任務狀態（唯讀）"""
    tasks = []
    for task_id, context in active_translations.items():
        tasks.append({
            "task_id": task_id,
            "is_running": context.running,
        })
    return {
        "success": True,
        "active_tasks": len(tasks),
        "tasks": tasks
    }


@public_app.get("/api/translation/stream/{task_id}")
async def public_stream_subtitles(task_id: str):
    """SSE 端點：實時推送字幕"""
    if not _is_subtitle_sharing_enabled():
        raise HTTPException(status_code=404, detail="Subtitle sharing is disabled")

    context = get_task(task_id)
    if not context:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        try:
            async for event in context.stream_output():
                if not _is_subtitle_sharing_enabled():
                    yield "event: error\n"
                    yield f"data: {json.dumps({'message': 'Subtitle sharing is disabled'}, ensure_ascii=False)}\n\n"
                    break
                if event["type"] == "ping":
                    yield ": ping\n\n"
                else:
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Public SSE error for task {task_id}: {e}")
            yield f"event: error\n"
            yield f"data: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@public_app.get("/api/health")
async def public_health():
    return {"status": "ok", "service": "public-subtitle"}


# ─── 靜態前端 ─────────────────────────────────────────────────────────────────

_static_mounted = False

def mount_static(static_root: Path):
    """掛載前端靜態檔案（只執行一次）"""
    global _static_mounted
    if _static_mounted:
        logger.info("[公開端口] 靜態檔案已掛載，跳過重複掛載")
        return
    _static_mounted = True

    assets_dir = static_root / "assets"
    index_file = static_root / "index.html"

    if assets_dir.exists():
        public_app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="public_assets")
        logger.info(f"[公開端口] 已掛載靜態資源: {assets_dir}")

    if index_file.exists():
        from fastapi.responses import RedirectResponse
        @public_app.get("/", include_in_schema=False)
        async def serve_index():
            return RedirectResponse(url="/desktop")

        @public_app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            # 跳過 /api 路徑（避免遮蔽 API 路由）
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = static_root / full_path
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)

        logger.info(f"[公開端口] 已掛載前端 SPA: {index_file}")
    else:
        logger.warning(f"[公開端口] ⚠️ 前端構建目錄不存在: {static_root}")
        logger.warning("[公開端口] ⚠️ 請先執行「構建UI2前端.bat」後再啟動應用")
