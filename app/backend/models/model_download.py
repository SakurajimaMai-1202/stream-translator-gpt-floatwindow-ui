from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ModelEngine = Literal["qwen3-asr", "faster-whisper", "sensevoice", "parakeet-ctc-ja"]


class StartModelDownloadRequest(BaseModel):
    """Request to start a model download task."""

    engine: ModelEngine = Field(..., description="Model engine")
    model_id: str = Field(..., description="Model id")


class ModelDownloadTask(BaseModel):
    """Model download task state."""

    task_id: str
    engine: ModelEngine
    model_id: str
    status: Literal["pending", "downloading", "completed", "failed"]
    progress: float = Field(0.0, ge=0.0, le=1.0)
    message: str = ""
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StartModelDownloadResponse(BaseModel):
    """Response for a started model download task."""

    success: bool = True
    task_id: str
    message: str


class ModelDownloadTaskListResponse(BaseModel):
    """List of model download tasks."""

    success: bool = True
    tasks: List[ModelDownloadTask]


class DownloadedModelInfo(BaseModel):
    """Downloaded model metadata."""

    engine: ModelEngine
    model_id: str
    repo_id: str
    size_bytes: int = 0
    cache_path: str = ""


class DownloadedModelListResponse(BaseModel):
    """Downloaded model list response."""

    success: bool = True
    models: List[DownloadedModelInfo]


class ModelStorageInfo(BaseModel):
    storage_path: str
    hub_cache_path: str
    modelscope_cache_path: str = ""
    is_default: bool


class ModelStorageInfoResponse(BaseModel):
    success: bool = True
    storage: ModelStorageInfo


class ModelActionResponse(BaseModel):
    success: bool = True
    message: str
