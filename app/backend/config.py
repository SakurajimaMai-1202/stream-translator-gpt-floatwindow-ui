from pydantic_settings import BaseSettings
from pathlib import Path
from typing import ClassVar
import sys

class Settings(BaseSettings):
    """應用程式設定"""
    APP_NAME: str = "YouTube 直播翻譯器 API"
    APP_VERSION: str = "2.0.0"
    API_PREFIX: str = "/api"
    
    # 路徑設定
    if getattr(sys, 'frozen', False):
        # 打包模式：設定檔存放在執行檔旁邊的 data 目錄
        BASE_DIR: Path = Path(sys._MEIPASS)
        # 執行檔同級目錄
        EXE_DIR: ClassVar[Path] = Path(sys.executable).parent
        CONFIG_FILE: Path = EXE_DIR / "data" / "config.yaml"
    else:
        # 開發模式
        BASE_DIR: Path = Path(__file__).parent.parent
        # 使用專案根目錄下的 config.yaml
        CONFIG_FILE: Path = BASE_DIR / "config.yaml"
    
    # 開發模式
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()
