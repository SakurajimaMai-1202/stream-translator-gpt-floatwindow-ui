from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import mimetypes
import threading

from backend.api import routes
from backend.config import settings
from backend.core.logging_setup import configure_logging

# 設定日誌
LOG_FILE = configure_logging("backend")
logger = logging.getLogger(__name__)
logger.info(f"Backend log 檔案: {LOG_FILE}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # ── 啟動 ──────────────────────────────────────────────
    # 1) 探測是否有現有的 llama 伺服器
    from backend.api.llama import probe_existing_llama_server
    await probe_existing_llama_server()

    # 2) 啟動公開字幕子伺服器（在背景執行緒）
    _start_public_server()

    yield  # 應用程式執行中

    # ── 關閉（可放清理邏輯）──────────────────────────────


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=f"{settings.API_PREFIX}/docs",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    lifespan=lifespan,
)

@app.get(f"{settings.API_PREFIX}/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok"}

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開發階段允許所有來源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
routes.register_routes(app)


def _start_public_server():
    from backend.public_app import public_app, mount_static
    import uvicorn
    import yaml
    
    # 掛載靜態前端檔案
    static_root = Path(__file__).parent / "static"
    if not static_root.exists():
        static_root = Path(__file__).parent.parent / "frontend" / "dist"
    mount_static(static_root)
    
    # 讀取 public_port
    try:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"
        if not config_path.exists():
            config_path = Path(__file__).parent.parent / "config.yaml"
        public_port = 8765
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            public_port = int(cfg.get("server", {}).get("public_port", 8765))
    except Exception as e:
        logger.warning(f"讀取公開端口設定失敗: {e}")
        public_port = 8765
        
    def run_public():
        logger.info(f"🌐 公開字幕端口啟動中: http://0.0.0.0:{public_port}")
        uvicorn.run(
            public_app,
            host="0.0.0.0",
            port=public_port,
            log_level="warning",
            access_log=False
        )
    
    threading.Thread(target=run_public, daemon=True, name="PublicSubtitleServer").start()

# 靜態檔案 (前端構建輸出)
static_root = Path(__file__).parent / "static"
if not static_root.exists():
    static_root = Path(__file__).parent.parent / "frontend" / "dist"

# 修正 Windows MIME 解析
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

index_file = static_root / "index.html"
assets_dir = static_root / "assets"

if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

if index_file.exists():
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # 嘗試返回靜態檔案
        candidate = static_root / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        # 否則返回 index.html (SPA fallback)
        return FileResponse(index_file)
else:
    logger.warning(f"前端構建目錄不存在: {static_root}，將無法在生產模式下提供網頁服務。")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True, access_log=False)
