"""Download and verify the small set of GGUF models offered by simple setup."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.core.http_downloader import HttpDownloader
from backend.core.portable_paths import get_app_root

REPOSITORY = "mradermacher/Hy-MT2-7B-i1-GGUF"
MODELS = {
    "hy-mt2-iq3-xxs": "Hy-MT2-7B.i1-IQ3_XXS.gguf",
    "hy-mt2-iq4-nl": "Hy-MT2-7B.i1-IQ4_NL.gguf",
    "hy-mt2-q6-k": "Hy-MT2-7B.i1-Q6_K.gguf",
}
BUSY = {"resolving", "downloading", "verifying"}


@dataclass
class ModelInstallStatus:
    state: str = "idle"
    message: str = ""
    progress: float = 0.0
    job_id: str = ""
    model_id: str = ""
    filename: str = ""
    path: str = ""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    sha256: str = ""
    error: str = ""


def simple_model_directory() -> Path:
    return (get_app_root() / "models" / "translation").resolve()


class LlamaModelInstaller:
    def __init__(self) -> None:
        self._status = ModelInstallStatus()
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def _set(self, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self._status, key, value)

    def begin(self, model_id: str) -> str:
        if model_id not in MODELS:
            raise RuntimeError("不支援的簡單模式翻譯模型")
        with self._lock:
            if self._status.state in BUSY:
                raise RuntimeError("翻譯模型正在下載")
            job_id = uuid.uuid4().hex
            self._status = ModelInstallStatus(
                state="resolving", message="正在讀取模型檔案資訊", job_id=job_id,
                model_id=model_id, filename=MODELS[model_id],
            )
        return job_id

    @staticmethod
    def _metadata(filename: str) -> tuple[str, int, str]:
        # Hugging Face omits LFS hashes from the default model response.  The
        # blobs view includes the authoritative size and SHA-256 needed before
        # we download multi-gigabyte GGUF files.
        api_url = f"https://huggingface.co/api/models/{REPOSITORY}?blobs=true"
        request = urllib.request.Request(api_url, headers={"User-Agent": "Stream-Translator"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        sibling = next((item for item in payload.get("siblings", []) if item.get("rfilename") == filename), None)
        if not sibling:
            raise RuntimeError(f"模型發布頁缺少 {filename}")
        lfs = sibling.get("lfs") or {}
        digest = str(lfs.get("sha256") or "").lower()
        size = int(lfs.get("size") or sibling.get("size") or 0)
        if len(digest) != 64 or size <= 0:
            raise RuntimeError("模型發布頁未提供可驗證的 SHA-256 或檔案大小")
        encoded = urllib.parse.quote(filename)
        return f"https://huggingface.co/{REPOSITORY}/resolve/main/{encoded}", size, digest

    def install(self, job_id: str, model_id: str) -> None:
        try:
            filename = MODELS[model_id]
            target_dir = simple_model_directory()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            url, size, expected = self._metadata(filename)
            if self.status().get("job_id") != job_id:
                return
            if target.is_file() and target.stat().st_size == size:
                actual = self._sha256(target)
                if actual == expected:
                    self._set(state="completed", message="翻譯模型已就緒", progress=1.0,
                              path=str(target), bytes_downloaded=size, bytes_total=size, sha256=actual)
                    return
            partial = target.with_suffix(target.suffix + ".part")
            self._set(state="downloading", message="正在下載本機翻譯模型",
                      bytes_total=size, sha256=expected)

            def progress(downloaded: int, total: int) -> None:
                total = total or size
                self._set(bytes_downloaded=downloaded, bytes_total=total,
                          progress=min(0.92, downloaded / total * 0.92) if total else 0.1)

            HttpDownloader(progress=progress).download(url, partial)
            if partial.stat().st_size != size:
                raise RuntimeError(f"模型大小不符：預期 {size}，實際 {partial.stat().st_size}")
            self._set(state="verifying", message="正在驗證模型 SHA-256", progress=0.94)
            actual = self._sha256(partial)
            if actual != expected:
                partial.unlink(missing_ok=True)
                raise RuntimeError("翻譯模型 SHA-256 驗證失敗，請重新下載")
            os.replace(partial, target)
            self._set(state="completed", message="翻譯模型已就緒", progress=1.0,
                      path=str(target), bytes_downloaded=size, bytes_total=size, sha256=actual)
        except Exception as exc:
            self._set(state="error", message="翻譯模型下載失敗", error=str(exc))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


model_installer = LlamaModelInstaller()
