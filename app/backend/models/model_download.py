from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ModelEngine = Literal["qwen3-asr", "faster-whisper", "sensevoice", "fun-asr-nano", "parakeet-ctc-ja"]
ModelComputeBackend = Literal["gpu", "cpu"]


class StartModelDownloadRequest(BaseModel):
    """Request to start a model download task."""

    engine: ModelEngine = Field(..., description="Model engine")
    model_id: str = Field(..., description="Model id")
    compute_backend: ModelComputeBackend = Field("gpu", description="Runtime that will consume the model")


class ModelDownloadTask(BaseModel):
    """Model download task state."""

    task_id: str
    engine: ModelEngine
    model_id: str
    compute_backend: ModelComputeBackend = "gpu"
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
    compute_backend: ModelComputeBackend = "gpu"
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
    sherpa_onnx_path: str = ""
    is_default: bool


class ModelStorageInfoResponse(BaseModel):
    success: bool = True
    storage: ModelStorageInfo


class ModelActionResponse(BaseModel):
    success: bool = True
    message: str
