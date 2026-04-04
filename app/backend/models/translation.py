from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

class AudioSource(str, Enum):
    """音訊來源類型"""
    URL = "url"
    FILE = "file"
    MICROPHONE = "microphone"
    SYSTEM_AUDIO = "system_audio"

class StartTranslationRequest(BaseModel):
    """啟動翻譯請求模型"""
    # 音訊來源相關
    audio_source: AudioSource = Field(AudioSource.URL, description="音訊來源類型")
    url: Optional[str] = Field(None, description="直播網址或檔案路徑 (當 audio_source 為 url 或 file 時)")
    device_index: Optional[int] = Field(None, description="設備索引 (當 audio_source 為 microphone 或 system_audio 時，null=自動選擇)")
    
    # 轉錄相關
    model: str = Field("base", description="Whisper 模型大小")
    backend: str = Field("faster-whisper", description="語音識別後端")
    transcription_engine: Optional[str] = Field(None, description="轉錄引擎 (faster-whisper/qwen3-asr/openai-api/simul-streaming/faster-whisper-simul)")
    qwen3_asr_model: Optional[str] = Field(None, description="Qwen3-ASR 模型名稱")
    input_language: Optional[str] = Field(None, description="Whisper 輸入語言 (ja/en/ko/zh/auto)")
    
    # 翻譯相關
    target_language: Optional[str] = Field("繁體中文", description="目標語言")
    gpt_model: Optional[str] = Field("gpt-4o-mini", description="LLM 模型")
    translation_backend: Optional[str] = Field(None, description="翻譯後端類型 (gpt/gemini/custom:ModelName)")
    translation_enabled: bool = Field(True, description="是否啟用翻譯功能")
    
    # 其他可選參數可從 config 讀取，這裡只列出最常用的覆蓋參數
    override_config: Optional[Dict[str, Any]] = Field(None, description="覆蓋的配置參數")


class AudioDevice(BaseModel):
    """音訊設備資訊"""
    index: int
    name: str
    sample_rate: int
    is_default: bool = False

class DeviceListResponse(BaseModel):
    """設備列表響應"""
    success: bool
    devices: Dict[str, List[AudioDevice]]

class TranslationTaskResponse(BaseModel):
    """翻譯任務響應"""
    success: bool
    task_id: str
    sse_url: str
    message: Optional[str] = None
