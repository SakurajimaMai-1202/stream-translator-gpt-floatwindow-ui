from fastapi import APIRouter, HTTPException
import asyncio
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from fastapi.responses import Response
from pydantic import BaseModel

from backend.api.config import get_config_manager
from backend.core.runtime_status import build_runtime_status
from backend.core.hardware_detector import detect_gpus
from backend.core.cpu_asr_sidecar_manager import cpu_asr_sidecar_manager
from backend.core.app_update_manager import app_update_manager

from backend.core.admin_auth import get_admin_token
from backend.core.config_secrets import SECRET_KEYS
from backend.core.logging_setup import resolve_log_dir

LOG_EXPORT_MAX_BYTES = 50 * 1024 * 1024


def _log_redactor(config):
    secrets = set()
    sensitive_name = r"[\w.-]*(?:token|key|secret|auth|password|signature|sig)[\w.-]*"

    def add_secret(value):
        if isinstance(value, str) and len(value) >= 4:
            secrets.add(value)
            secrets.add(json.dumps(value, ensure_ascii=False)[1:-1])

    def collect(value, sensitive=False, cookie=False):
        if isinstance(value, dict):
            for key, item in value.items():
                name = str(key).lower()
                collect(item, sensitive or name in SECRET_KEYS or bool(
                    re.search(r"token|cookie|password|secret|key|auth|signature|sig", name)),
                    cookie or "cookie" in name)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, sensitive, cookie)
        elif sensitive and isinstance(value, str):
            add_secret(value)
            # ApiKeyPool splits on commas and strips each key (common.py).
            for piece in value.split(","):
                add_secret(piece.strip())
            if cookie:
                for match in re.finditer(r"(?:^|;)\s*[^=;]+\s*=\s*([^;]*)", value):
                    add_secret(match.group(1).strip().strip("\"'"))

    collect(config)
    add_secret(get_admin_token())
    pattern = re.compile("|".join(re.escape(value) for value in sorted(secrets, key=len, reverse=True))) if secrets else None
    # Logs may contain Python bytes/raw reprs or JSON escaped inside a string.
    # Capture the quote spelling so redaction preserves its serialization layer.
    name_quote = r"(?P<name_quote>\\*[\"'])?"
    name_end = r"(?(name_quote)(?P=name_quote))"
    quoted_value = (r"(?P<value_prefix>[br]{1,2})?(?P<value_quote>\\*[\"'])"
                    r"[^\r\n]*?(?P=value_quote)")
    name_prefix = r"(?<![\w.-])(?P<field_prefix>(?:[br]{1,2})?" + name_quote
    header_pattern = re.compile(
        name_prefix + r"(?:authorization|proxy-authorization|cookie|set-cookie)" + name_end + r"\s*[:=]\s*)"
        r"(?P<field_value>" + quoted_value + r"|[^\r\n\"'<>]+)", re.I)
    list_item = r"[^\s,;&\"'{}\[\]<>]+"
    field_pattern = re.compile(
        name_prefix + sensitive_name + name_end + r"\s*[:=]\s*)"
        r"(?P<field_value>" + quoted_value + r"|" + list_item + r"(?:\s*,\s*" + list_item + r")*)", re.I)

    def mask_field(match):
        quote = match.group("value_quote") or ""
        prefix = match.group("value_prefix") or ""
        return match.group("field_prefix") + prefix + quote + "<redacted>" + quote

    def redact(text):
        if pattern:
            text = pattern.sub("<redacted>", text)
        text = re.sub(r"([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1<redacted>@", text, flags=re.I)
        text = re.sub(r"([?&]" + sensitive_name + r"=)[^&#\s\"'<>]+",
                      r"\1<redacted>", text, flags=re.I)
        text = header_pattern.sub(mask_field, text)
        text = field_pattern.sub(mask_field, text)
        return text

    return redact


def _build_logs_archive(config, report):
    redact = _log_redactor(config)
    metadata = {
        "diagnostics.json": json.dumps(report, ensure_ascii=False, indent=2),
        "README.txt": "包含程式、後端與翻譯引擎的 Log 及 Runtime 診斷報告。\n"
                      "API Key、Token、Cookie 與帳密網址已自動遮蔽。\n"
                      "容量上限為 50 MB；優先保留最新檔案，部分檔案僅保留尾端，詳見 export-notes.txt。\n",
    }
    metadata = {name: redact(text).encode("utf-8") for name, text in metadata.items()}
    directory = resolve_log_dir()
    files = []
    if directory.exists():
        for path in directory.iterdir():
            if re.fullmatch(r".+\.log(?:\.\d+)?", path.name) and path.is_file() and not path.is_symlink():
                try:
                    files.append((path.stat().st_mtime_ns, path))
                except FileNotFoundError:
                    pass  # A rotating logger may rename a file during enumeration.
    files.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    notes = ["容量限制：優先保留最新 Log；截斷檔案僅保留尾端。"]
    # Reserve space for every possible note so the complete ZIP's uncompressed
    # size (including metadata and UTF-8 replacement/redaction expansion) is capped.
    note_reserve = len(redact("\n".join(notes)).encode("utf-8")) + sum(
        len(redact("截斷／略過／無法讀取：" + path.name).encode("utf-8")) + 1 for _, path in files) + 1
    remaining = LOG_EXPORT_MAX_BYTES - sum(map(len, metadata.values())) - note_reserve
    if remaining < 0:
        raise ValueError("診斷資料超過 Log 匯出容量限制")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for _, path in files:
            if remaining == 0:
                notes.append("略過：" + path.name)
                continue
            try:
                with path.open("rb") as source:
                    source.seek(0, io.SEEK_END)
                    size = source.tell()
                    truncated = size > remaining
                    source.seek(max(0, size - remaining) if truncated else 0)
                    chunk = source.read(min(size, remaining))
                if truncated:
                    # The cut may split a credential or UTF-8 character. Discard
                    # the entire first line, even when the cut happens at a newline.
                    chunk = chunk.partition(b"\n")[2]
                content = redact(chunk.decode("utf-8", errors="replace")).encode("utf-8")
            except OSError:
                notes.append("無法讀取：" + path.name)
                continue
            if len(content) > remaining:
                # Replacement characters/redaction can expand the bounded input.
                # Keep complete tail lines so this second cut cannot leak a token.
                content = content[-remaining:].partition(b"\n")[2]
                truncated = True
            if truncated:
                notes.append("截斷：" + path.name)
            archive.writestr("logs/" + path.name, content)
            remaining = 0 if truncated else remaining - len(content)
        for name, content in metadata.items():
            archive.writestr(name, content)
        archive.writestr("export-notes.txt", redact("\n".join(notes) + "\n"))
    return output.getvalue()


router = APIRouter(prefix="/runtime", tags=["runtime"])


class CpuAsrSidecarImportRequest(BaseModel):
    archive_path: str


@router.get("/status")
async def get_runtime_status(refresh: bool = False):
    try:
        config = get_config_manager().get_config()
        # Importing Torch and probing the GPU can take 10-20 seconds on a cold
        # packaged runtime.  Keep that work off the FastAPI event loop so a
        # concurrent /config request remains responsive.
        def build_status():
            if refresh:
                return build_runtime_status(config, detect_gpus(force_refresh=True))
            return build_runtime_status(config)

        data = await asyncio.to_thread(build_status)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cpu-asr-sidecar")
async def get_cpu_asr_sidecar_status():
    return {"success": True, "data": cpu_asr_sidecar_manager.status()}


@router.post("/cpu-asr-sidecar/install")
async def install_cpu_asr_sidecar():
    try:
        return {
            "success": True,
            "data": cpu_asr_sidecar_manager.start(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cpu-asr-sidecar/cancel")
async def cancel_cpu_asr_sidecar_install():
    return {"success": True, "data": cpu_asr_sidecar_manager.cancel()}


@router.post("/cpu-asr-sidecar/import")
async def import_cpu_asr_sidecar(request: CpuAsrSidecarImportRequest):
    try:
        data = await asyncio.to_thread(cpu_asr_sidecar_manager.import_archive, request.archive_path)
        return {"success": True, "data": data}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_diagnostics(config):
    from backend.api.llama import _get_llama_runtime_info
    from backend.config import settings
    return {"success": True, "data": {
        "app_version": settings.APP_VERSION,
        "runtime": build_runtime_status(config),
        "resources": {
            "model_storage_path": str(config.get("models", {}).get("storage_path", "") or ""),
            "llama_server_exe": str(config.get("llama", {}).get("server_exe", "") or ""),
            "llama_model_path": str(config.get("llama", {}).get("model_path", "") or ""),
            "llama_runtime": _get_llama_runtime_info(),
            "cpu_asr_sidecar": cpu_asr_sidecar_manager.status(),
        },
    }}


def _current_diagnostics():
    return _build_diagnostics(get_config_manager().get_config())


@router.get("/diagnostics")
async def export_runtime_diagnostics():
    """Return a support-safe snapshot without secrets or transcript data."""
    try:
        return await asyncio.to_thread(_current_diagnostics)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _export_current_logs():
    config = get_config_manager().get_config()
    return _build_logs_archive(config, _build_diagnostics(config))


@router.get("/logs/export")
async def export_runtime_logs():
    try:
        content = await asyncio.to_thread(_export_current_logs)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return Response(content, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="stream-translator-logs-{timestamp}.zip"',
            "Cache-Control": "no-store",
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail="匯出 Log 失敗") from exc


@router.get("/app-update")
async def get_app_update_status():
    return {"success": True, "data": app_update_manager.status()}


@router.post("/app-update/check")
async def check_app_update():
    # Keep the backend responsive while GitHub handles the one-time startup check.
    data = await asyncio.to_thread(app_update_manager.check)
    return {"success": True, "data": data}


@router.post("/app-update/download")
async def download_app_update():
    try:
        return {"success": True, "data": app_update_manager.start_download()}
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/app-update/cancel")
async def cancel_app_update():
    return {"success": True, "data": app_update_manager.cancel()}


@router.post("/app-update/apply")
async def prepare_app_update_apply():
    try:
        return {"success": True, "data": app_update_manager.create_apply_plan()}
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
