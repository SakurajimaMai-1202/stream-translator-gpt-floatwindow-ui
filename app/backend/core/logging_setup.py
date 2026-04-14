"""
共用日誌設定
統一 UI 啟動器與 FastAPI 後端的 log 輸出、輪替與等級控制
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import yaml

from backend.config import settings


DEFAULT_LOG_LEVEL_NAME = "INFO"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def resolve_log_dir() -> Path:
    """取得 log 目錄。打包模式放在執行檔旁，開發模式放在 app/logs。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "logs"
    return settings.BASE_DIR / "logs"


def resolve_log_file(log_name: str) -> Path:
    """取得指定 log 檔完整路徑。"""
    return resolve_log_dir() / f"{log_name}.log"


def _read_log_level_name(config_path: Optional[Path] = None) -> str:
    """從 config.yaml 讀取 general.log_level。"""
    path = config_path or settings.CONFIG_FILE
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            value = str(config.get("general", {}).get("log_level", DEFAULT_LOG_LEVEL_NAME)).strip().upper()
            if value in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                return value
    except Exception:
        pass
    return DEFAULT_LOG_LEVEL_NAME


def get_configured_log_level(config_path: Optional[Path] = None) -> int:
    """轉換設定檔中的 log level 為 logging 常數。"""
    return getattr(logging, _read_log_level_name(config_path), logging.INFO)


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s [%(levelname)s] %(processName)s/%(threadName)s %(name)s: %(message)s"
    )


def _close_handlers(logger: logging.Logger):
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _configure_named_logger(name: str, *, level: int, propagate: bool = True):
    logger = logging.getLogger(name)
    _close_handlers(logger)
    logger.setLevel(level)
    logger.propagate = propagate


def _install_exception_hook():
    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("uncaught").exception(
            "未捕獲例外",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = _handle_exception


def configure_logging(log_name: str, config_path: Optional[Path] = None, *, console: bool = True) -> Path:
    """設定 root logger，回傳實際 log 檔路徑。"""
    log_dir = resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = get_configured_log_level(config_path)
    formatter = _build_formatter()
    log_file = resolve_log_file(log_name)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    root_logger = logging.getLogger()
    _close_handlers(root_logger)
    root_logger.setLevel(log_level)
    for handler in handlers:
        root_logger.addHandler(handler)

    logging.captureWarnings(True)
    _install_exception_hook()

    # 讓 uvicorn / fastapi / warnings 統一走 root handlers
    for logger_name in ("uvicorn", "uvicorn.error", "fastapi", "starlette", "py.warnings"):
        _configure_named_logger(logger_name, level=log_level, propagate=True)

    # access log 通常偏噪，除非整體已開 DEBUG，否則壓到 WARNING
    access_level = logging.DEBUG if log_level <= logging.DEBUG else logging.WARNING
    _configure_named_logger("uvicorn.access", level=access_level, propagate=True)

    # 第三方高噪音 logger 預設收斂一點
    for logger_name in ("watchfiles", "asyncio", "httpx", "urllib3"):
        logging.getLogger(logger_name).setLevel(max(log_level, logging.WARNING))

    return log_file