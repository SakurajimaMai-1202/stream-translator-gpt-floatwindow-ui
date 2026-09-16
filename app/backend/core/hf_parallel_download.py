"""Prefetch large public LFS blobs while preserving Hugging Face cache semantics."""
import hashlib
import logging
import re
import urllib.error
from pathlib import Path

from .http_downloader import HttpDownloader, DOWNLOAD_CHUNK_SIZE

logger = logging.getLogger(__name__)


def prefetch_large_files(repo_id, info, cache_dir: Path, allow_file=lambda _: True):
    from huggingface_hub import hf_hub_url
    from huggingface_hub.utils import WeakFileLock, validate_repo_id

    # An immutable revision and LFS digest are required before writing a blob.
    validate_repo_id(repo_id)
    if not re.fullmatch('[0-9a-f]{40}', getattr(info, 'sha', '') or ''):
        return
    folder = f"models--{repo_id.replace('/', '--')}"
    for entry in info.siblings:
        if not allow_file(entry.rfilename) or int(entry.size or 0) < 2 * DOWNLOAD_CHUNK_SIZE:
            continue
        lfs = getattr(entry, 'lfs', None)
        digest = lfs.get('sha256') if isinstance(lfs, dict) else getattr(lfs, 'sha256', None)
        if not digest or not re.fullmatch('[0-9a-f]{64}', digest):
            continue
        snapshot_file = cache_dir / folder / 'snapshots' / info.sha / entry.rfilename
        if snapshot_file.is_file() and snapshot_file.stat().st_size == entry.size:
            continue
        blob = cache_dir / folder / 'blobs' / digest
        lock = cache_dir / '.locks' / folder / f'{digest}.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        blob.parent.mkdir(parents=True, exist_ok=True)
        with WeakFileLock(str(lock)):
            if blob.is_file():
                continue
            partial = blob.with_name(blob.name + '.incomplete')
            url = hf_hub_url(repo_id, entry.rfilename, revision=info.sha)
            try:
                # No credentials are forwarded to CDN redirects. Gated/private
                # repositories fall back to the SDK's authenticated downloader.
                HttpDownloader().download(url, partial)
            except (OSError, urllib.error.URLError) as exc:
                logger.warning('Parallel prefetch unavailable for %s; using Hugging Face downloader: %s',
                               entry.rfilename, type(exc).__name__)
                continue
            with partial.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if partial.stat().st_size != entry.size or actual != digest:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f'Model integrity check failed: {entry.rfilename}')
            partial.replace(blob)
