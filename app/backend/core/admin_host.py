"""管理 API 的監聽位址設定。"""

import ipaddress
import logging
import os

import yaml


logger = logging.getLogger(__name__)

# 實際監聽的位址；設定頁用它判斷區網開關是否已在本次啟動生效。
bound_host = "127.0.0.1"


def lan_admin_enabled() -> bool:
    """config.yaml 的 server.allow_lan_admin；讀不到時視為關閉。"""
    from backend.config import settings
    try:
        with open(settings.CONFIG_FILE, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return (cfg.get("server") or {}).get("allow_lan_admin") is True
    except Exception:
        logger.debug("讀取區網控制介面設定失敗", exc_info=True)
        return False


def is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def get_admin_host() -> str:
    """預設只允許本機連線；設定頁的區網開關或環境變數可改為對外監聽。"""
    global bound_host
    host = os.environ.get("FLOATWINDOW_ADMIN_HOST", "").strip()
    if not host:
        host = "0.0.0.0" if lan_admin_enabled() else "127.0.0.1"
    if not is_loopback_host(host):
        logger.warning("管理 API 監聽非本機位址 %s，其他裝置可能存取管理功能", host)
    bound_host = host
    return host
