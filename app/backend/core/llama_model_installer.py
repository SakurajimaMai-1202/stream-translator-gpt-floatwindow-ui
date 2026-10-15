"""Download and verify GGUF models offered by the translation catalog."""
from __future__ import annotations

import logging
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.http_downloader import HttpDownloader
from backend.core.portable_paths import get_app_root
from backend.core.translation_model_recommender import MODEL_CATALOG

logger = logging.getLogger(__name__)


REPOSITORY = "unsloth/Hy-MT2-7B-GGUF"
MODELS = {
    "hy-mt2-iq3-xxs": "Hy-MT2-7B-UD-IQ3_XXS.gguf",
    "hy-mt2-iq4-nl": "Hy-MT2-7B-IQ4_NL.gguf",
    "hy-mt2-q6-k": "Hy-MT2-7B-Q6_K.gguf",
}
BUSY = {"resolving", "downloading", "verifying"}


@dataclass
class ModelInstallStatus:
    state: str = "idle"
    message: str = ""
    progress: float = 0.0
    job_id: str = ""
    model_id: str = ""
    catalog_id: str = ""
    quant: str = ""
    deployment_config: dict[str, Any] = field(default_factory=dict)
    filename: str = ""
    path: str = ""
    directory: str = ""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    sha256: str = ""
    error: str = ""


def simple_model_directory() -> Path:
    return (get_app_root() / "models" / "translation").resolve()


def model_directory() -> Path:
    try:
        from backend.api.config import _read_config
        raw = str(_read_config().get("llama", {}).get("model_dir") or "").strip()
        if raw:
            path = Path(os.path.expandvars(os.path.expanduser(raw)))
            if not path.is_absolute():
                path = get_app_root() / path
            if path.is_dir():
                return path.resolve()
    except Exception:
        logger.debug("讀取模型目錄設定失敗", exc_info=True)
    return simple_model_directory()


def _quant_token(value: str) -> str:
    match = re.match(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*", value.strip())
    return match.group().upper() if match else ""


class LlamaModelInstaller:
    def __init__(self) -> None:
        self._status = ModelInstallStatus()
        self._lock = threading.RLock()
        self._worker_lock = threading.Lock()
        self._cancel = threading.Event()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def _set(self, job_id: str, **values: Any) -> None:
        with self._lock:
            if self._status.job_id != job_id or self._status.state == "cancelled":
                return
            for key, value in values.items():
                setattr(self._status, key, value)

    def begin(self, model_id: str, quant: str = "") -> str:
        catalog = next((m for m in MODEL_CATALOG if m["id"] == model_id), None)
        if model_id not in MODELS and catalog is None:
            raise RuntimeError("不支援的翻譯模型")
        if model_id in MODELS:
            catalog = None
            quant = MODELS[model_id].removeprefix("Hy-MT2-7B-").removesuffix(".gguf")
        else:
            quant = _quant_token(quant or catalog["recommended_quant"])
            allowed = {_quant_token(catalog[key]) for key in ("recommended_quant", "minimum_quant")}
            if not quant or quant not in allowed:
                raise RuntimeError("不支援的模型量化格式，請選擇建議或最低量化格式")
        with self._lock:
            if self._status.state in BUSY:
                raise RuntimeError("翻譯模型正在下載")
            job_id = uuid.uuid4().hex
            self._cancel = threading.Event()
            self._status = ModelInstallStatus(
                state="resolving", message="正在讀取模型檔案資訊", job_id=job_id,
                model_id=model_id, filename=MODELS.get(model_id, ""),
                catalog_id=catalog["id"] if catalog else "", quant=quant,
            )
        return job_id

    def cancel(self, job_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if job_id is not None and job_id != self._status.job_id:
                raise RuntimeError("下載工作已變更，請重新整理")
            if self._status.state in BUSY:
                self._cancel.set()
                self._status.state = "cancelled"
                self._status.progress = 0.0
                self._status.bytes_downloaded = 0
                self._status.message = "已取消下載"
            return asdict(self._status)

    @staticmethod
    def _siblings(repo: str) -> list[dict[str, Any]]:
        api_url = f"https://huggingface.co/api/models/{repo}?blobs=true"
        request = urllib.request.Request(api_url, headers={"User-Agent": "Stream-Translator"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response).get("siblings", [])

    @staticmethod
    def _asset(repo: str, sibling: dict[str, Any]) -> tuple[str, int, str]:
        lfs = sibling.get("lfs") or {}
        digest = str(lfs.get("sha256") or "").lower()
        try:
            size = int(lfs.get("size") or sibling.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or size <= 0:
            raise RuntimeError("模型發布頁未提供可驗證的 SHA-256 或檔案大小")
        encoded = urllib.parse.quote(sibling["rfilename"])
        return f"https://huggingface.co/{repo}/resolve/main/{encoded}", size, digest

    @classmethod
    def _resolve(cls, repo: str, quant: str) -> tuple[str, str, int, str]:
        token = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(quant) + r"(?=[.\-]|$)", re.I)
        matches = [item for item in cls._siblings(repo)
                   if item.get("rfilename", "").lower().endswith(".gguf")
                   and "mmproj" not in item["rfilename"].lower()
                   and token.search(Path(item["rfilename"]).name)]
        if any(re.search(r"-\d{5}-of-\d{5}", item["rfilename"], re.I) for item in matches):
            raise RuntimeError("尚不支援分割模型檔案")
        if not matches:
            raise RuntimeError(f"找不到符合 {quant} 的 GGUF 模型檔案")
        if len(matches) != 1:
            raise RuntimeError(f"找到多個符合 {quant} 的 GGUF 模型檔案，無法自動選擇")
        return matches[0]["rfilename"], *cls._asset(repo, matches[0])

    @staticmethod
    def _metadata(filename: str) -> tuple[str, int, str]:
        sibling = next((item for item in LlamaModelInstaller._siblings(REPOSITORY)
                        if item.get("rfilename") == filename), None)
        if not sibling:
            raise RuntimeError(f"模型發布頁缺少 {filename}")
        return LlamaModelInstaller._asset(REPOSITORY, sibling)

    def install(self, job_id: str, model_id: str) -> None:
        # A cancelled worker must release its partial file before another uses it.
        with self._worker_lock:
            with self._lock:
                if self._status.job_id != job_id or self._status.state != "resolving":
                    return
                cancel = self._cancel
                quant = self._status.quant
            self._install(job_id, model_id, quant, cancel)

    def _install(self, job_id: str, model_id: str, quant: str, cancel: threading.Event) -> None:
        def check_cancelled() -> None:
            if cancel.is_set():
                raise InterruptedError("已取消下載")

        try:
            check_cancelled()
            catalog = next((m for m in MODEL_CATALOG if m["id"] == model_id), None)
            deployment = dict(catalog["deployment_config"]) if catalog else {}
            if model_id in MODELS:
                filename = MODELS[model_id]
                url, size, expected = self._metadata(filename)
            else:
                filename, url, size, expected = self._resolve(catalog["repo"], quant)
            check_cancelled()
            if not re.fullmatch(r"[A-Za-z0-9._-]+\.gguf", filename):
                raise RuntimeError("模型檔名不安全，僅接受英數字、點、底線及連字號的 .gguf 檔案")
            self._set(job_id, filename=filename)
            target_dir = simple_model_directory() if model_id in MODELS else model_directory()
            self._set(job_id, directory=str(target_dir))
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / Path(filename).name
            if self.status().get("job_id") != job_id:
                return
            for candidate in (target, target.with_name(f"{target.stem}.{expected[:8]}.gguf")):
                target = candidate
                self._set(job_id, filename=target.name)
                if not target.exists():
                    break
                if target.is_file() and target.stat().st_size == size:
                    actual = self._sha256(target, cancel)
                    check_cancelled()
                    if actual == expected:
                        self._set(job_id, state="completed", message="翻譯模型已就緒", progress=1.0,
                                  path=str(target), bytes_downloaded=size, bytes_total=size, sha256=actual,
                                  deployment_config=deployment)
                        return
            else:
                raise RuntimeError("模型檔案已存在且驗證不符，請先重新命名現有檔案")
            partial = target.with_suffix(target.suffix + ".part")
            self._set(job_id, state="downloading", message="正在下載本機翻譯模型",
                      bytes_total=size, sha256=expected)

            def progress(downloaded: int, total: int) -> None:
                total = total or size
                self._set(job_id, bytes_downloaded=downloaded, bytes_total=total,
                          progress=min(0.92, downloaded / total * 0.92) if total else 0.1)

            HttpDownloader(progress=progress, cancel_event=cancel).download(url, partial)
            check_cancelled()
            if partial.stat().st_size != size:
                raise RuntimeError(f"模型大小不符：預期 {size}，實際 {partial.stat().st_size}")
            self._set(job_id, state="verifying", message="正在驗證模型 SHA-256", progress=0.94)
            actual = self._sha256(partial, cancel)
            if actual != expected:
                partial.unlink(missing_ok=True)
                raise RuntimeError("翻譯模型 SHA-256 驗證失敗，請重新下載")
            with self._lock:
                check_cancelled()
                # A file created during the download must also remain untouched.
                if target.exists():
                    raise RuntimeError("模型檔案已存在，請重新下載以選擇安全檔名")
                os.rename(partial, target)
                self._set(job_id, state="completed", message="翻譯模型已就緒", progress=1.0,
                          path=str(target), bytes_downloaded=size, bytes_total=size, sha256=actual,
                          deployment_config=deployment)
        except InterruptedError:
            # HttpDownloader persists a contiguous prefix and resumes it on retry.
            self._set(job_id, state="cancelled", message="已取消下載",
                      progress=0.0, bytes_downloaded=0)
        except Exception as exc:
            logger.debug("下載翻譯模型失敗", exc_info=True)
            self._set(job_id, state="error", message="翻譯模型下載失敗", error=str(exc))

    @staticmethod
    def _sha256(path: Path, cancel_event: threading.Event | None = None) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("已取消下載")
                digest.update(block)
        return digest.hexdigest()


model_installer = LlamaModelInstaller()
