from fastapi import APIRouter, HTTPException

from backend.core.model_download_manager import get_model_download_manager
from backend.models.model_download import (
    DownloadedModelListResponse,
    ModelDownloadTask,
    ModelDownloadTaskListResponse,
    StartModelDownloadRequest,
    StartModelDownloadResponse,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.post("/download", response_model=StartModelDownloadResponse)
async def start_model_download(request: StartModelDownloadRequest):
    """啟動模型下載任務"""
    try:
        manager = get_model_download_manager()
        task_id = await manager.start_download(request.engine, request.model_id)
        return StartModelDownloadResponse(
            success=True,
            task_id=task_id,
            message="模型下載任務已啟動",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", response_model=ModelDownloadTaskListResponse)
async def list_model_download_tasks():
    """取得模型下載任務列表"""
    manager = get_model_download_manager()
    return ModelDownloadTaskListResponse(success=True, tasks=manager.list_tasks())


@router.get("/tasks/{task_id}", response_model=ModelDownloadTask)
async def get_model_download_task(task_id: str):
    """取得單一模型下載任務"""
    manager = get_model_download_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/list", response_model=DownloadedModelListResponse)
async def list_downloaded_models():
    """列出已下載模型"""
    manager = get_model_download_manager()
    models = manager.list_downloaded_models()
    return DownloadedModelListResponse(success=True, models=models)
