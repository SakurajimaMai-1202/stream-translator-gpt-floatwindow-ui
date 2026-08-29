from pydantic_settings import BaseSettings
from pathlib import Path
from typing import ClassVar
import sys

class Settings(BaseSettings):
    """應用程式設定"""
    APP_NAME: str = "YouTube 直播翻譯器 API"
    APP_VERSION: str = "1.4.2"
    API_PREFIX: str = "/api"
    
    # 路徑設定
    if getattr(sys, 'frozen', False):
        # 打包環境：使用 PyInstaller 的臨時目錄作為 base
        BASE_DIR: Path = Path(sys._MEIPASS)
        # 設定檔放在執行檔同目錄
        EXE_DIR: ClassVar[Path] = Path(sys.executable).parent
        CONFIG_FILE: Path = EXE_DIR / "config.yaml"
    else:
        # 開發環境
        BASE_DIR: Path = Path(__file__).parent.parent
        # 使用專案根目錄的 config.yaml
        CONFIG_FILE: Path = BASE_DIR / "config.yaml"
    
    # 開發環境
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()
