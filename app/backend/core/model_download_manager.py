import asyncio
import copy
import fnmatch
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import time
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List, Literal, Optional

from backend.models.model_download import ModelDownloadTask, DownloadedModelInfo, ModelComputeBackend
from backend.core.portable_paths import (
    ensure_model_storage,
    get_app_root,
    get_huggingface_hub_cache,
    get_modelscope_cache,
    get_model_storage_root,
)

logger = logging.getLogger(__name__)

SHERPA_CPU_BUNDLES = {
    "nvidia/parakeet-tdt-0.6b-v3": ("sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8", ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")),
    "nvidia/parakeet-tdt_ctc-0.6b-ja": ("sherpa-onnx-nemo-parakeet-tdt_ctc-0.6b-ja-35000-int8", ("model.int8.onnx", "tokens.txt")),
    "FunAudioLLM/Fun-ASR-Nano-2512": ("sherpa-onnx-funasr-nano-int8-2025-12-30", ("encoder_adaptor.int8.onnx", "llm.int8.onnx", "embedding.int8.onnx", "Qwen3-0.6B")),
    "iic/SenseVoiceSmall": ("sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17", ("model.int8.onnx", "tokens.txt")),
    "Qwen/Qwen3-ASR-0.6B": ("sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25", ("conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx", "tokenizer")),
    "Qwen/Qwen3-ASR-1.7B": ("sherpa-onnx-qwen3-asr-1.7B-int8", ("conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx", "tokenizer")),
}
SHERPA_RELEASE_ROOT = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
SHERPA_HF_REPOS = {
    "Qwen/Qwen3-ASR-1.7B": "thieunv/sherpa-onnx-qwen3-asr-1.7B-int8",
}
SHERPA_CPU_ENGINES = {
    "Qwen/Qwen3-ASR-0.6B": "qwen3-asr",
    "Qwen/Qwen3-ASR-1.7B": "qwen3-asr",
    "iic/SenseVoiceSmall": "sensevoice",
    "FunAudioLLM/Fun-ASR-Nano-2512": "fun-asr-nano",
    "nvidia/parakeet-tdt-0.6b-v3": "parakeet-ctc-ja",
    "nvidia/parakeet-tdt_ctc-0.6b-ja": "parakeet-ctc-ja",
}

SUPPORTED_QWEN3_MODELS = {
    "Qwen/Qwen3-ASR-0.6B",
    "Qwen/Qwen3-ASR-1.7B",
    "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame",
}

SUPPORTED_SENSEVOICE_MODELS = {
    "iic/SenseVoiceSmall",
}

SUPPORTED_FUN_ASR_MODELS = {
    "FunAudioLLM/Fun-ASR-Nano-2512",
    "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
}

SUPPORTED_PARAKEET_MODELS = {
    "nvidia/parakeet-tdt-0.6b-v3",
    "nvidia/parakeet-tdt_ctc-0.6b-ja",
    "nvidia/parakeet-tdt_ctc-1.1b",
    "grider-transwithai/parakeet-ctc-1.1b-ja",
}

SUPPORTED_FASTER_WHISPER_MODELS = {
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
}

FASTER_WHISPER_MODEL_TO_REPO_ID = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}

FASTER_WHISPER_REPO_ID_TO_MODEL = {
    repo_id: model_id for model_id, repo_id in FASTER_WHISPER_MODEL_TO_REPO_ID.items()
}


class ModelDownloadManager:
    """模型下載任務管理器"""

    def __init__(self):
        self._tasks: Dict[str, ModelDownloadTask] = {}
        self._lock = Lock()

    def _now(self) -> datetime:
        return datetime.now()

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.0f} {unit}" if unit in {"B", "KB"} else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @staticmethod
    def _directory_size(path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
        return total

    @staticmethod
    def _has_required_paths(path: Path, required_paths: tuple[str, ...]) -> bool:
        """Return False for incomplete or temporarily inaccessible model folders."""
        try:
            return path.is_dir() and all((path / name).exists() for name in required_paths)
        except OSError:
            logger.warning("Skipping inaccessible model directory: %s", path, exc_info=True)
            return False

    def _update_byte_progress(self, task_id: str, downloaded: int, total: int, label: str) -> None:
        if total <= 0:
            return
        ratio = min(1.0, max(0.0, downloaded / total))
        self._update_task(
            task_id,
            progress=0.15 + ratio * 0.80,
            downloaded_bytes=min(downloaded, total),
            total_bytes=total,
            message=(
                f"{label} {ratio * 100:.1f}% "
                f"({self._format_bytes(downloaded)} / {self._format_bytes(total)})"
            ),
        )

    def _update_task(
        self,
        task_id: str,
        *,
        status: Optional[Literal["pending", "downloading", "completed", "failed"]] = None,
        progress: Optional[float] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            if status is not None:
                task.status = status
            if progress is not None:
                task.progress = max(0.0, min(1.0, progress))
            if downloaded_bytes is not None:
                task.downloaded_bytes = max(0, downloaded_bytes)
            if total_bytes is not None:
                task.total_bytes = max(0, total_bytes)
            if message is not None:
                task.message = message
            if error is not None:
                task.error = error
            task.updated_at = self._now()

    def _normalize_repo_id(self, engine: str, model_id: str) -> str:
        if engine == "qwen3-asr":
            return model_id
        if engine in {"sensevoice", "fun-asr-nano"}:
            return model_id
        if engine == "parakeet-ctc-ja":
            return model_id
        if "/" in model_id:
            return model_id
        return FASTER_WHISPER_MODEL_TO_REPO_ID.get(model_id, f"Systran/faster-whisper-{model_id}")

    def _validate_model_id(self, engine: str, model_id: str, compute_backend: ModelComputeBackend = "gpu") -> str:
        if compute_backend == "cpu":
            if model_id not in SHERPA_CPU_BUNDLES:
                raise ValueError(f"CPU / sherpa-onnx 不支援此模型: {model_id}")
            if engine == "faster-whisper":
                raise ValueError("CPU / sherpa-onnx 模式不使用 Faster-Whisper 模型")
            expected_engine = SHERPA_CPU_ENGINES[model_id]
            if engine != expected_engine:
                raise ValueError(f"CPU 模型 {model_id} 必須使用引擎 {expected_engine}，不是 {engine}")
        if engine == "qwen3-asr":
            if model_id not in SUPPORTED_QWEN3_MODELS:
                raise ValueError(f"不支援的 Qwen3-ASR 模型: {model_id}")
            return model_id

        if engine == "sensevoice":
            if model_id not in SUPPORTED_SENSEVOICE_MODELS:
                raise ValueError(f"不支援的 SenseVoice 模型: {model_id}")
            return model_id

        if engine == "fun-asr-nano":
            if model_id not in SUPPORTED_FUN_ASR_MODELS:
                raise ValueError(f"Unsupported Fun-ASR Nano model: {model_id}")
            return model_id

        if engine == "parakeet-ctc-ja":
            if model_id not in SUPPORTED_PARAKEET_MODELS:
                raise ValueError(f"不支援的 NVIDIA Parakeet 模型: {model_id}")
            return model_id

        if engine == "faster-whisper":
            if "/" in model_id:
                # 允許進階使用者直接輸入完整 repo id
                return model_id
            if model_id not in SUPPORTED_FASTER_WHISPER_MODELS:
                raise ValueError(f"不支援的 Faster-Whisper 模型: {model_id}")
            return model_id

        raise ValueError(f"不支援的引擎: {engine}")

    async def start_download(self, engine: str, model_id: str, compute_backend: ModelComputeBackend = "gpu") -> str:
        """建立下載任務並背景執行"""
        normalized_model_id = self._validate_model_id(engine, model_id, compute_backend)
        task_id = str(uuid.uuid4())
        now = self._now()

        task = ModelDownloadTask(
            task_id=task_id,
            engine=engine,  # type: ignore[arg-type]
            model_id=normalized_model_id,
            compute_backend=compute_backend,
            status="pending",
            progress=0.0,
            message="任務已建立",
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._tasks[task_id] = task

        asyncio.create_task(self._run_download_task(task_id, engine, normalized_model_id, compute_backend))
        return task_id

    async def _run_download_task(self, task_id: str, engine: str, model_id: str, compute_backend: ModelComputeBackend) -> None:
        """執行單一下載任務"""
        try:
            self._update_task(task_id, status="downloading", progress=0.05, message="準備下載")
            if compute_backend == "cpu":
                await self._download_sherpa_archive(task_id, model_id)
            elif engine == "sensevoice":
                await self._download_sensevoice_from_modelscope(task_id, model_id)
            else:
                repo_id = self._normalize_repo_id(engine, model_id)
                await self._download_from_hf(task_id, repo_id)
            self._update_task(task_id, status="completed", progress=1.0, message="下載完成")
        except Exception as e:
            logger.exception("模型下載失敗 task_id=%s", task_id)
            self._update_task(task_id, status="failed", message="下載失敗", error=str(e))

    async def _download_sherpa_archive(self, task_id: str, model_id: str) -> None:
        bundle, required_paths = SHERPA_CPU_BUNDLES[model_id]
        model_root = ensure_model_storage() / "sherpa-onnx"
        target = (model_root / bundle).resolve()
        archive = (model_root / f"{bundle}.tar.bz2").resolve()

        if model_id in SHERPA_HF_REPOS:
            state = {"total": 0}

            def blocking_hf_download() -> None:
                if target.exists() and all((target / name).exists() for name in required_paths):
                    return
                from huggingface_hub import HfApi, snapshot_download

                repo_id = SHERPA_HF_REPOS[model_id]
                allow_patterns = ["*.onnx", "tokenizer/*", "LICENSE*", "README*"]
                info = HfApi().model_info(repo_id, files_metadata=True)
                state["total"] = sum(
                    int(sibling.size or 0)
                    for sibling in info.siblings
                    if any(fnmatch.fnmatch(sibling.rfilename, pattern) for pattern in allow_patterns)
                )

                snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(target),
                    allow_patterns=allow_patterns,
                )
                missing = [name for name in required_paths if not (target / name).exists()]
                if missing:
                    raise RuntimeError(f"Incomplete sherpa model download; missing: {', '.join(missing)}")

            self._update_task(task_id, progress=0.15, message="Downloading sherpa-onnx INT8 model from Hugging Face")
            download = asyncio.create_task(asyncio.to_thread(blocking_hf_download))
            while not download.done():
                total = state["total"]
                if total > 0:
                    downloaded = min(total, await asyncio.to_thread(self._directory_size, target))
                    self._update_byte_progress(task_id, downloaded, total, "下載中")
                await asyncio.sleep(0.5)
            await download
            self._update_task(task_id, progress=0.95, message=f"sherpa-onnx model ready: {target}")
            return

        def blocking_download() -> None:
            if target.exists() and all((target / name).exists() for name in required_paths):
                return
            last_update = {"time": 0.0, "progress": -1.0}

            def reporthook(block_count: int, block_size: int, total_size: int) -> None:
                if total_size <= 0:
                    return
                downloaded = min(total_size, block_count * block_size)
                ratio = downloaded / total_size
                now = time.monotonic()
                if ratio >= 1.0 or ratio - last_update["progress"] >= 0.002 or now - last_update["time"] >= 0.5:
                    last_update.update(time=now, progress=ratio)
                    self._update_byte_progress(task_id, downloaded, total_size, "下載中")

            urllib.request.urlretrieve(
                f"{SHERPA_RELEASE_ROOT}/{archive.name}",
                archive,
                reporthook=reporthook,
            )
            with tarfile.open(archive, "r:bz2") as model_archive:
                for member in model_archive.getmembers():
                    extracted = (model_root / member.name).resolve()
                    try:
                        extracted.relative_to(model_root.resolve())
                    except ValueError as exc:
                        raise RuntimeError(f"Unsafe path in sherpa model archive: {member.name}") from exc
                    if member.issym() or member.islnk():
                        raise RuntimeError(f"Links are not allowed in sherpa model archive: {member.name}")
                model_archive.extractall(model_root)
            archive.unlink(missing_ok=True)
            missing = [name for name in required_paths if not (target / name).exists()]
            if missing:
                raise RuntimeError(f"Incomplete sherpa model archive; missing: {', '.join(missing)}")

        self._update_task(task_id, progress=0.15, message="Downloading sherpa-onnx INT8 model")
        await asyncio.to_thread(blocking_download)
        self._update_task(task_id, progress=0.95, message=f"sherpa-onnx model ready: {target}")

    async def _download_from_hf(self, task_id: str, repo_id: str) -> None:
        """Download a Hugging Face model with byte-based progress."""
        self._update_task(task_id, progress=0.15, message="初始化 HuggingFace 下載")
        state = {"total": 0, "blob_dir": None}

        def blocking_download():
            from huggingface_hub import HfApi, snapshot_download

            cache_dir = get_huggingface_hub_cache()
            cache_dir.mkdir(parents=True, exist_ok=True)
            repo_cache = cache_dir / f"models--{repo_id.replace('/', '--')}"
            state["blob_dir"] = repo_cache / "blobs"
            info = HfApi().model_info(repo_id, files_metadata=True)
            state["total"] = sum(int(sibling.size or 0) for sibling in info.siblings)
            return snapshot_download(
                repo_id=repo_id,
                cache_dir=str(cache_dir),
                resume_download=True,
                local_files_only=False,
            )

        download = asyncio.create_task(asyncio.to_thread(blocking_download))
        while not download.done():
            total = state["total"]
            blob_dir = state["blob_dir"]
            if total > 0 and isinstance(blob_dir, Path):
                downloaded = min(total, await asyncio.to_thread(self._directory_size, blob_dir))
                self._update_byte_progress(task_id, downloaded, total, "下載中")
            await asyncio.sleep(0.5)
        path = await download
        self._update_task(task_id, progress=0.95, message=f"模型已快取至 {path}")

    async def _download_sensevoice_from_modelscope(self, task_id: str, model_id: str) -> None:
        self._update_task(task_id, progress=0.15, message="Preparing ModelScope download")

        def blocking_download():
            cache_dir = self._get_modelscope_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            python_exe = self._resolve_sensevoice_download_python()
            script = (
                "from funasr import AutoModel\n"
                f"AutoModel(model={model_id!r}, trust_remote_code=True, device='cpu', disable_update=True)\n"
            )
            env = dict(os.environ)
            env["MODELSCOPE_CACHE"] = str(cache_dir)
            result = subprocess.run(
                [python_exe, "-c", script],
                cwd=str(get_app_root()),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "SenseVoice ModelScope download failed with "
                    f"{python_exe}: {result.stderr or result.stdout}"
                )
            return self._get_modelscope_model_dir(model_id)

        for step in (0.25, 0.45, 0.65, 0.85):
            self._update_task(task_id, progress=step, message="Downloading from ModelScope")
            await asyncio.sleep(0.05)

        path = await asyncio.to_thread(blocking_download)
        self._update_task(task_id, progress=0.95, message=f"SenseVoice model downloaded: {path}")

    def get_task(self, task_id: str) -> Optional[ModelDownloadTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            return copy.deepcopy(task) if task else None

    def list_tasks(self) -> List[ModelDownloadTask]:
        with self._lock:
            tasks = [copy.deepcopy(t) for t in self._tasks.values()]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def _get_hf_cache_dir(self) -> Path:
        return get_huggingface_hub_cache()

    def _get_modelscope_cache_dir(self) -> Path:
        return get_modelscope_cache()

    def _get_modelscope_model_dir(self, repo_id: str) -> Path:
        namespace, name = repo_id.split("/", 1)
        return (self._get_modelscope_cache_dir() / "models" / namespace / name).resolve()

    def _get_modelscope_model_dirs(self, repo_id: str) -> List[Path]:
        namespace, name = repo_id.split("/", 1)
        cache_dir = self._get_modelscope_cache_dir()
        return [
            (cache_dir / "models" / namespace / name).resolve(),
            (cache_dir / namespace / name).resolve(),
        ]

    def _resolve_sensevoice_download_python(self) -> str:
        app_root = get_app_root()
        candidates = [
            app_root / "_runtime" / "python.exe",
            app_root / "build-runtime-cache" / "cuda-runtime" / "python.exe",
            app_root / "build-runtime-cache" / "cpu-runtime" / "python.exe",
            app_root / "build-runtime-cache" / "rocm-runtime" / "python.exe",
            Path(sys.executable),
        ]
        for candidate in candidates:
            if not candidate.exists():
                continue
            result = subprocess.run(
                [str(candidate), "-c", "import funasr"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode == 0:
                return str(candidate)
        raise RuntimeError("No Python runtime with FunASR is available for SenseVoice download")

    def _directory_size(self, path: Path) -> int:
        size_bytes = 0
        try:
            for root, _, files in os.walk(path):
                for file_name in files:
                    fp = Path(root) / file_name
                    try:
                        size_bytes += fp.stat().st_size
                    except OSError:
                        continue
        except OSError:
            pass
        return size_bytes

    def get_storage_info(self) -> dict:
        root = ensure_model_storage()
        default_root = (get_app_root() / "models" / "huggingface").resolve()
        return {
            "storage_path": str(root),
            "hub_cache_path": str(root / "hub"),
            "modelscope_cache_path": str(root / "modelscope"),
            "sherpa_onnx_path": str(root / "sherpa-onnx"),
            "is_default": root == default_root,
        }

    def open_storage_folder(self) -> Path:
        root = ensure_model_storage()
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise RuntimeError("目前只支援在 Windows 開啟模型資料夾")
        os.startfile(str(root))
        return root

    def delete_model(self, engine: str, model_id: str, compute_backend: ModelComputeBackend = "gpu") -> Path:
        normalized_model_id = self._validate_model_id(engine, model_id, compute_backend)
        if compute_backend == "cpu":
            bundle, _ = SHERPA_CPU_BUNDLES[normalized_model_id]
            cache_root = (get_model_storage_root() / "sherpa-onnx").resolve()
            repo_dir = (cache_root / bundle).resolve()
        elif engine == "sensevoice":
            cache_root = self._get_modelscope_cache_dir().resolve()
            repo_dir = next(
                (candidate for candidate in self._get_modelscope_model_dirs(normalized_model_id) if candidate.exists()),
                self._get_modelscope_model_dir(normalized_model_id),
            )
        else:
            repo_id = self._normalize_repo_id(engine, normalized_model_id)
            cache_root = self._get_hf_cache_dir().resolve()
            repo_dir = (cache_root / f"models--{repo_id.replace('/', '--')}").resolve()

        try:
            repo_dir.relative_to(cache_root)
        except ValueError as exc:
            raise ValueError("模型路徑不在快取目錄內") from exc

        if not repo_dir.exists():
            raise FileNotFoundError(f"模型尚未下載: {model_id}")
        if repo_dir.is_symlink():
            raise ValueError("拒絕刪除符號連結模型目錄")

        shutil.rmtree(repo_dir)
        return repo_dir

    def list_downloaded_models(self) -> List[DownloadedModelInfo]:
        """列出 HuggingFace 快取中的指定模型"""
        models: List[DownloadedModelInfo] = []

        sherpa_root = get_model_storage_root() / "sherpa-onnx"
        for model_id, (bundle, required_paths) in SHERPA_CPU_BUNDLES.items():
            model_dir = sherpa_root / bundle
            if self._has_required_paths(model_dir, required_paths):
                engine = "qwen3-asr" if model_id.startswith("Qwen/") else (
                    "sensevoice" if model_id.startswith("iic/") else
                    "fun-asr-nano" if model_id.startswith("FunAudioLLM/") else "parakeet-ctc-ja"
                )
                models.append(DownloadedModelInfo(
                    engine=engine, model_id=model_id, repo_id=bundle,
                    compute_backend="cpu",
                    size_bytes=self._directory_size(model_dir), cache_path=str(model_dir),
                ))

        for model_id in sorted(SUPPORTED_SENSEVOICE_MODELS):
            for model_dir in self._get_modelscope_model_dirs(model_id):
                if not model_dir.exists() or not model_dir.is_dir():
                    continue
                models.append(
                    DownloadedModelInfo(
                        engine="sensevoice",
                        model_id=model_id,
                        repo_id=model_id,
                        compute_backend="gpu",
                        size_bytes=self._directory_size(model_dir),
                        cache_path=str(model_dir),
                    )
                )
                break

        # 優先使用 huggingface_hub 的 cache 掃描
        try:
            from huggingface_hub import scan_cache_dir

            cache = scan_cache_dir(str(self._get_hf_cache_dir()))
            for repo in cache.repos:
                repo_id = repo.repo_id
                size_bytes = int(getattr(repo, "size_on_disk", 0) or 0)
                cache_path = str(getattr(repo, "repo_path", ""))

                if repo_id in SUPPORTED_QWEN3_MODELS or repo_id.startswith("Qwen/Qwen3-ASR-"):
                    models.append(
                        DownloadedModelInfo(
                            engine="qwen3-asr",
                            model_id=repo_id,
                            repo_id=repo_id,
                            compute_backend="gpu",
                            size_bytes=size_bytes,
                            cache_path=cache_path,
                        )
                    )
                elif repo_id in SUPPORTED_PARAKEET_MODELS:
                    models.append(
                        DownloadedModelInfo(
                            engine="parakeet-ctc-ja",
                            model_id=repo_id,
                            repo_id=repo_id,
                            compute_backend="gpu",
                            size_bytes=size_bytes,
                            cache_path=cache_path,
                        )
                    )
                elif repo_id in SUPPORTED_FUN_ASR_MODELS:
                    models.append(
                        DownloadedModelInfo(
                            engine="fun-asr-nano",
                            model_id=repo_id,
                            repo_id=repo_id,
                            compute_backend="gpu",
                            size_bytes=size_bytes,
                            cache_path=cache_path,
                        )
                    )
                elif repo_id in FASTER_WHISPER_REPO_ID_TO_MODEL or repo_id.startswith("Systran/faster-whisper-"):
                    model_id = FASTER_WHISPER_REPO_ID_TO_MODEL.get(repo_id, repo_id.replace("Systran/faster-whisper-", ""))
                    models.append(
                        DownloadedModelInfo(
                            engine="faster-whisper",
                            model_id=model_id,
                            repo_id=repo_id,
                            compute_backend="gpu",
                            size_bytes=size_bytes,
                            cache_path=cache_path,
                        )
                    )
            models.sort(key=lambda m: (m.engine, m.model_id))
            return models
        except Exception as e:
            logger.warning("scan_cache_dir 失敗，回退檔案系統掃描: %s", e)

        # 回退：直接掃描資料夾名稱
        cache_dir = self._get_hf_cache_dir()
        if not cache_dir.exists():
            return models

        for item in cache_dir.iterdir():
            if not item.is_dir() or not item.name.startswith("models--"):
                continue

            folder_name = item.name.replace("models--", "")
            repo_id = folder_name.replace("--", "/")

            size_bytes = 0
            try:
                for root, _, files in os.walk(item):
                    for file_name in files:
                        fp = Path(root) / file_name
                        try:
                            size_bytes += fp.stat().st_size
                        except OSError:
                            continue
            except OSError:
                pass

            if repo_id in SUPPORTED_QWEN3_MODELS or repo_id.startswith("Qwen/Qwen3-ASR-"):
                models.append(
                    DownloadedModelInfo(
                        engine="qwen3-asr",
                        model_id=repo_id,
                        repo_id=repo_id,
                        compute_backend="gpu",
                        size_bytes=size_bytes,
                        cache_path=str(item),
                    )
                )
            elif repo_id in SUPPORTED_PARAKEET_MODELS:
                models.append(
                    DownloadedModelInfo(
                        engine="parakeet-ctc-ja",
                        model_id=repo_id,
                        repo_id=repo_id,
                        compute_backend="gpu",
                        size_bytes=size_bytes,
                        cache_path=str(item),
                    )
                )
            elif repo_id in SUPPORTED_FUN_ASR_MODELS:
                models.append(
                    DownloadedModelInfo(
                        engine="fun-asr-nano",
                        model_id=repo_id,
                        repo_id=repo_id,
                        compute_backend="gpu",
                        size_bytes=size_bytes,
                        cache_path=str(item),
                    )
                )
            elif repo_id in FASTER_WHISPER_REPO_ID_TO_MODEL or repo_id.startswith("Systran/faster-whisper-"):
                model_id = FASTER_WHISPER_REPO_ID_TO_MODEL.get(repo_id, repo_id.replace("Systran/faster-whisper-", ""))
                models.append(
                    DownloadedModelInfo(
                        engine="faster-whisper",
                        model_id=model_id,
                        repo_id=repo_id,
                        compute_backend="gpu",
                        size_bytes=size_bytes,
                        cache_path=str(item),
                    )
                )
        models.sort(key=lambda m: (m.engine, m.model_id))
        return models


_download_manager_instance: Optional[ModelDownloadManager] = None


def get_model_download_manager() -> ModelDownloadManager:
    global _download_manager_instance
    if _download_manager_instance is None:
        _download_manager_instance = ModelDownloadManager()
    return _download_manager_instance
