from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class StartModelDownloadRequest(BaseModel):
    """啟動模型下載請求"""
    engine: Literal["qwen3-asr", "faster-whisper"] = Field(..., description="模型引擎")
    model_id: str = Field(..., description="模型識別符")


class ModelDownloadTask(BaseModel):
    """模型下載任務"""
    task_id: str
    engine: Literal["qwen3-asr", "faster-whisper"]
    model_id: str
    status: Literal["pending", "downloading", "completed", "failed"]
    progress: float = Field(0.0, ge=0.0, le=1.0)
    message: str = ""
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StartModelDownloadResponse(BaseModel):
    """啟動模型下載回應"""
    success: bool = True
    task_id: str
    message: str


class ModelDownloadTaskListResponse(BaseModel):
    """模型下載任務列表回應"""
    success: bool = True
    tasks: List[ModelDownloadTask]


class DownloadedModelInfo(BaseModel):
    """已下載模型資訊"""
    engine: Literal["qwen3-asr", "faster-whisper"]
    model_id: str
    repo_id: str
    size_bytes: int = 0
    cache_path: str = ""


class DownloadedModelListResponse(BaseModel):
    """已下載模型列表回應"""
    success: bool = True
    models: List[DownloadedModelInfo]
