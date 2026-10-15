"""Ask an OpenAI-compatible server which model it is really serving.

A local llama-server is often started with an alias such as ``localllm``, which
hides the model family from the configured model ID. llama.cpp reports the
loaded GGUF path on ``/props``; LM Studio and others list real IDs on
``/v1/models``. Results are cached briefly so repeated config conversions do
not hit the server every time; the settings page bypasses the cache because a model
switch restarts the server under the same address.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import PurePath
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_PROBE_TIMEOUT_SECONDS = 1.5
_cache: dict[tuple[str, str], tuple[float, list[str]]] = {}
_lock = threading.Lock()


def _server_root(base_url: str) -> str:
    root = str(base_url or "").strip().rstrip("/")
    if root.lower().endswith("/v1"):
        root = root[:-3]
    return root


def served_model_names(base_url: str, api_key: str = "", use_cache: bool = True, configured_model: str = "") -> list[str]:
    """Return model identifiers the server reports, best evidence first."""
    root = _server_root(base_url)
    parts = urlsplit(root)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return []
    cache_key = (root, str(configured_model or "").casefold())
    now = time.monotonic()
    with _lock:
        cached = _cache.get(cache_key)
        if use_cache and cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return list(cached[1])

    names: list[str] = []
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT_SECONDS, headers=headers, trust_env=False) as client:
            try:
                props = client.get(f"{root}/props")
                if props.status_code == 200:
                    data = props.json()
                    model_path = str(data.get("model_path") or "").strip()
                    if model_path:
                        names.append(PurePath(model_path.replace("\\", "/")).name)
                    alias = str(data.get("model_alias") or "").strip()
                    if alias:
                        names.append(alias)
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
            try:
                models = client.get(f"{root}/v1/models")
                if models.status_code == 200:
                    entries = models.json().get("data") or []
                    for item in entries:
                        if isinstance(item, dict):
                            candidates = [str(item.get(key) or "").strip() for key in ("id", "name", "model")]
                            candidates.extend(str(alias).strip() for alias in item.get("aliases") or [])
                            names.extend(name for name in candidates
                                         if len(entries) == 1 or name.casefold() == cache_key[1])
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
    except httpx.HTTPError:
        logger.debug("Model identity probe failed for %s", root, exc_info=True)

    unique = list(dict.fromkeys(name for name in names if name))
    with _lock:
        _cache[cache_key] = (now, unique)
    return unique


def detect_served_family(base_url: str, api_key: str, provider: str, configured_model: str = "") -> tuple[str, str]:
    """Return (family, matched model name) when the served model reveals one."""
    from stream_translator_gpt.translation_policy import resolve_model_family

    for name in served_model_names(base_url, api_key, configured_model=configured_model):
        family = resolve_model_family("auto", name, provider)
        if family in {"hy_mt2", "index_translate"}:
            return family, name
    return "", ""


def family_probe_target(backend: str, config: dict, args: dict) -> tuple[str, str]:
    """Return (server URL to probe, configured model file name to fall back on)."""
    if backend in {"llama", "localllm"}:
        llama_config = config.get("llama", {}) or {}
        host = str(llama_config.get('host') or '127.0.0.1')
        # The app's own server bound to all interfaces is still reached through loopback.
        if host in {"0.0.0.0", "::", "[::]"}:
            host = "127.0.0.1"
        url = f"http://{host}:{llama_config.get('port') or 8081}"
        return url, PurePath(str(llama_config.get("model_path") or "").replace("\\", "/")).name
    return str(args.get("gpt_base_url") or ""), ""


def is_loopback_probe(base_url: str) -> bool:
    """Only local endpoints participate in automatic identity probing."""
    try:
        return urlsplit(base_url).hostname in {"127.0.0.1", "::1", "localhost"}
    except ValueError:
        return False
