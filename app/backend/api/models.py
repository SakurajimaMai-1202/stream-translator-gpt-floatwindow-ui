from fastapi import APIRouter, HTTPException

from backend.core.model_download_manager import get_model_download_manager
from backend.core.runtime_profiles import get_asr_capabilities
from backend.api.config import get_config_manager
from backend.models.model_download import (
    DownloadedModelListResponse,
    ModelActionResponse,
    ModelDownloadTask,
    ModelDownloadTaskListResponse,
    ModelStorageInfo,
    ModelStorageInfoResponse,
    StartModelDownloadRequest,
    StartModelDownloadResponse,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.post("/download", response_model=StartModelDownloadResponse)
async def start_model_download(request: StartModelDownloadRequest):
    """啟動模型下載任務"""
    try:
        manager = get_model_download_manager()
        config = get_config_manager().get_config()
        runtime_profile = config.get('runtime', {}).get('profile')
        capabilities = get_asr_capabilities(runtime_profile, request.compute_backend)
        if request.engine not in capabilities.local_asr_engines:
            raise HTTPException(
                status_code=400,
                detail=f'{request.engine} is not supported by {request.compute_backend.upper()} ASR '
                       f'in the {capabilities.profile} runtime.',
            )

        task_id = await manager.start_download(request.engine, request.model_id, request.compute_backend)
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


@router.get("/storage", response_model=ModelStorageInfoResponse)
async def get_model_storage():
    manager = get_model_download_manager()
    return ModelStorageInfoResponse(storage=ModelStorageInfo(**manager.get_storage_info()))


@router.post("/storage/open", response_model=ModelActionResponse)
async def open_model_storage():
    try:
        path = get_model_download_manager().open_storage_folder()
        return ModelActionResponse(message=f"已開啟模型資料夾: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{engine}/{model_id:path}", response_model=ModelActionResponse)
async def delete_model(engine: str, model_id: str, compute_backend: str = "gpu"):
    try:
        if compute_backend not in {"gpu", "cpu"}:
            raise ValueError(f"不支援的 compute backend: {compute_backend}")
        get_model_download_manager().delete_model(engine, model_id, compute_backend)  # type: ignore[arg-type]
        return ModelActionResponse(message=f"已刪除模型: {model_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
