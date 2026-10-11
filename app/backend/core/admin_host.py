"""管理 API 的監聽位址設定。"""

import ipaddress
import logging
import os


logger = logging.getLogger(__name__)


def get_admin_host() -> str:
    """預設只允許本機連線，進階使用者可透過環境變數覆寫。"""
    host = os.environ.get("FLOATWINDOW_ADMIN_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback:
        logger.warning("管理 API 監聽非本機位址 %s，其他裝置可能存取管理功能", host)
    return host
