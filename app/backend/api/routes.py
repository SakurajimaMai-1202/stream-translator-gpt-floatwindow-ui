import ipaddress
import socket

from fastapi import FastAPI
from . import config
from . import translation
from . import llama
from . import models
from . import sync
from . import runtime
from . import cookies
from backend.api.config import get_config_manager
from backend.core.system_check import check_ffmpeg

def register_routes(app: FastAPI):
    """註冊所有路由"""
    app.include_router(config.router, prefix="/api")
    app.include_router(translation.router, prefix="/api")
    app.include_router(llama.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(runtime.router, prefix="/api")
    app.include_router(cookies.router, prefix="/api")

    @app.get("/api/server/info")
    async def server_info():
        """回傳伺服器公開端口資訊，供前端組合分享連結"""
        try:
            cfg = get_config_manager().get_config()
            server_cfg = cfg.get("server", {}) if isinstance(cfg, dict) else {}
            public_port = server_cfg.get("public_port", 8765)
            sharing_enabled = server_cfg.get("enable_subtitle_sharing", True)
        except Exception:
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
        return {
            "public_port": public_port,
            "enable_subtitle_sharing": sharing_enabled,
            "lan_addresses": sorted(lan_addresses),
        }

    @app.get("/api/system/check")
    async def system_check():
        """回傳系統相依套件檢查結果（目前包含 ffmpeg）。"""
        ffmpeg = check_ffmpeg()
        return {
            "ffmpeg": ffmpeg,
        }
