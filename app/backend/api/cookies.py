import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.api.config import get_config_manager
from backend.core.app_sync import publish_app_event
from backend.core.cookie_manager import (
    BrowserCookieDatabaseLockedError,
    BrowserCookieDecryptionUnsupportedError,
    COOKIE_PLATFORMS,
    SUPPORTED_BROWSERS,
    export_platform_cookies,
    import_platform_cookie_file,
)


router = APIRouter(prefix="/cookies", tags=["cookies"])


class BrowserCookieImportRequest(BaseModel):
    platform: str
    browser: str
    profile: str = ""


MAX_COOKIE_FILE_SIZE = 10 * 1024 * 1024


async def _persist_cookie_result(result: dict, request: Request) -> None:
    manager = get_config_manager()
    current = manager.get_config()
    input_config = dict(current.get("input") or {})
    cookies_by_site = dict(input_config.get("cookies_by_site") or {})
    cookies_by_site[result["platform"]] = result["path"]
    input_config["cookies_by_site"] = cookies_by_site
    updated_config = manager.update_config({"input": input_config})
    await publish_app_event("config.updated", {
        "section": "input",
        "config": updated_config,
        "source_client_id": request.headers.get("X-Client-Id", ""),
    })


@router.get("/options")
async def get_cookie_options():
    return {
        "success": True,
        "platforms": [
            {"value": key, "label": definition.label}
            for key, definition in COOKIE_PLATFORMS.items()
        ],
        "browsers": sorted(SUPPORTED_BROWSERS),
    }


@router.post("/import-browser")
async def import_browser_cookies(payload: BrowserCookieImportRequest, request: Request):
    try:
        result = export_platform_cookies(payload.platform, payload.browser, payload.profile)
        await _persist_cookie_result(result, request)
        return {"success": True, "data": result}
    except BrowserCookieDatabaseLockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except BrowserCookieDecryptionUnsupportedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="讀取瀏覽器 Cookies 逾時")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/import-file")
async def import_cookie_file(
    request: Request,
    platform: str = Form(...),
    cookie_file: UploadFile = File(...),
):
    try:
        content = await cookie_file.read(MAX_COOKIE_FILE_SIZE + 1)
        if len(content) > MAX_COOKIE_FILE_SIZE:
            raise ValueError("cookies.txt 不可超過 10 MB")
        if b"\t" not in content:
            raise ValueError("檔案不是有效的 Netscape cookies.txt")

        with tempfile.TemporaryDirectory(prefix="stream-translator-cookie-upload-") as temp_dir:
            source = Path(temp_dir) / "cookies.txt"
            source.write_bytes(content)
            result = import_platform_cookie_file(platform, source)

        await _persist_cookie_result(result, request)
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cookie_file.close()
