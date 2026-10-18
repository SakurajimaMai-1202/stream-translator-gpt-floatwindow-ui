import ipaddress
import logging
import socket

from fastapi import FastAPI, Request
from . import config
from . import translation
from . import llama
from . import models
from . import sync
from . import runtime
from . import cookies
from . import readiness
from backend.api.config import get_config_manager
from backend.core import admin_host
from backend.core.system_check import check_ffmpeg

logger = logging.getLogger(__name__)

def register_routes(app: FastAPI):
    """註冊所有路由"""
    app.include_router(config.router, prefix="/api")
    app.include_router(translation.router, prefix="/api")
    app.include_router(llama.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(runtime.router, prefix="/api")
    app.include_router(cookies.router, prefix="/api")
    app.include_router(readiness.router, prefix="/api")

    @app.get("/api/server/info")
    async def server_info(request: Request):
        """回傳伺服器公開端口資訊，供前端組合分享連結"""
        allow_lan_admin = False
        lan_admin_password_set = False
        try:
            cfg = get_config_manager().get_config()
            server_cfg = cfg.get("server", {}) if isinstance(cfg, dict) else {}
            public_port = server_cfg.get("public_port", 8765)
            sharing_enabled = server_cfg.get("enable_subtitle_sharing", True)
            allow_lan_admin = server_cfg.get("allow_lan_admin") is True
            lan_admin_password_set = bool(server_cfg.get("lan_admin_password"))
        except Exception:
            logger.debug("讀取伺服器分享設定失敗", exc_info=True)
            public_port = 8765
            sharing_enabled = False
        lan_addresses = set()
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                address = item[4][0]
                parsed = ipaddress.ip_address(address)
                if not (parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified):
                    lan_addresses.add(address)
        except OSError:
            pass
        lan_admin_active = not admin_host.is_loopback_host(admin_host.bound_host)
        lan_admin_urls = []
        if lan_admin_active and request.url.port:
            lan_admin_urls = [f"http://{ip}:{request.url.port}/" for ip in sorted(lan_addresses)]
        return {
            "public_port": public_port,
            "enable_subtitle_sharing": sharing_enabled,
            "lan_addresses": sorted(lan_addresses),
            "allow_lan_admin": allow_lan_admin,
            "lan_admin_active": lan_admin_active,
            "lan_admin_urls": lan_admin_urls,
            "lan_admin_password_set": lan_admin_password_set,
        }

    @app.get("/api/system/check")
    async def system_check():
        """回傳系統相依套件檢查結果（目前包含 ffmpeg）。"""
        ffmpeg = check_ffmpeg()
        return {
            "ffmpeg": ffmpeg,
        }
