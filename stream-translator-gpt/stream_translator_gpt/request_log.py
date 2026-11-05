"""Best-effort durable diagnostics, independent of the application's reset logs."""
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit


_logger = logging.Logger(__name__, level=logging.INFO)
_logger.propagate = False
_lock = threading.Lock()
_path = None
_last_snapshot_at = None
# Only multiline rejections need their text for diagnosis. Every other reason
# is recorded by code alone, because rejected output can repeat the prompt.
_RAW_OUTPUT_REASONS = frozenset({"unexpected_multiline_output"})
_PROMPT_TEXT_MARKS = ("〖", "【", "<think>", "</think>", "请将以下文本翻译", "請將以下文本翻譯")


class _QuietHandler(RotatingFileHandler):
    def handleError(self, record):
        pass


def _write(record):
    global _path
    if os.environ.get("STREAM_TRANSLATOR_REQUEST_LOG") != "1":
        return
    try:
        directory = os.environ.get("STREAM_TRANSLATOR_LOG_DIR", "").strip()
        if not directory:
            return
        path = Path(directory).resolve() / "translation_requests.jsonl"
        with _lock:
            if path != _path:
                for handler in _logger.handlers[:]:
                    _logger.removeHandler(handler)
                    handler.close()
                path.parent.mkdir(parents=True, exist_ok=True)
                handler = _QuietHandler(path, maxBytes=2*1024*1024, backupCount=2,
                                        encoding="utf-8", delay=True)
                handler.setFormatter(logging.Formatter("%(message)s"))
                _logger.addHandler(handler)
                _path = path
            _logger.info(json.dumps(record, ensure_ascii=False))
    except Exception:
        pass


def _timestamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _is_loopback(endpoint):
    try:
        host = urlsplit(str(endpoint or "")).hostname
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except Exception:
        return False


def _gpu_snapshot(executable, segment_id, attempt_ms):
    try:
        result = subprocess.run(
            [executable, "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], timeout=3, capture_output=True,
            text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return
        for line in result.stdout.splitlines():
            util, used, total = (float(value.strip()) for value in line.split(","))
            _write(dict(type="gpu_snapshot", ts=_timestamp(), segment_id=segment_id,
                        attempt_ms=attempt_ms, util_pct=util,
                        mem_used_mb=used, mem_total_mb=total))
    except Exception:
        pass


def _schedule_snapshot(endpoint, segment_id, attempt_ms):
    global _last_snapshot_at
    try:
        if attempt_ms < 2500 or not _is_loopback(endpoint):
            return
        executable = shutil.which("nvidia-smi")
        if not executable:
            return
        with _lock:
            now = time.monotonic()
            if _last_snapshot_at is not None and now - _last_snapshot_at < 5:
                return
            _last_snapshot_at = now
        threading.Thread(target=_gpu_snapshot, args=(executable, segment_id, attempt_ms),
                         daemon=True).start()
    except Exception:
        pass


def _text_lines(text):
    return {line.strip() for line in str(text or "").splitlines() if line.strip()}


def _loggable_raw_output(client, task, validation, raw_output):
    if not set(validation) <= _RAW_OUTPUT_REASONS:
        return None
    if any(mark in raw_output for mark in _PROMPT_TEXT_MARKS):
        return None
    # Substring, not equality: Index joins a numbered prefix onto each constraint.
    prompt_text = f'{getattr(task, "_attempt_prompt_text", "")}\n{getattr(client, "prompt", "") or ""}'
    if any(line in prompt_text for line in _text_lines(raw_output)):
        return None
    return raw_output[:300]


def log_attempt(client, task, attempt_ms):
    try:
        if os.environ.get("STREAM_TRANSLATOR_REQUEST_LOG") != "1":
            return
        if not os.environ.get("STREAM_TRANSLATOR_LOG_DIR", "").strip():
            return
        validation = list(task._attempt_validation)
        record = dict(type="attempt", ts=_timestamp(), segment_id=task.segment_id,
                      attempt=max(1, task._translation_attempts), attempt_ms=attempt_ms,
                      queue_ms=task.translation_queue_latency_ms, provider=client.provider,
                      model=client.model, model_family=client.model_family,
                      prompt_tokens=task.translation_prompt_tokens,
                      completion_tokens=task.translation_completion_tokens,
                      finish_reason=task._attempt_finish_reason, validation=validation,
                      failed=bool(task.translation_failed),
                      error=validation[0] if validation else getattr(task, "_attempt_error", None))
        if validation:
            record["source"] = str(task.transcript or "")[:300]
            raw_output = _loggable_raw_output(client, task, validation, str(task._attempt_raw_output or ""))
            if raw_output is not None:
                record["raw_output"] = raw_output
        _write(record)
        endpoint = (client.gemini_base_url if client.provider == "gemini" else
                    client.base_url or os.environ.get("OPENAI_BASE_URL"))
        _schedule_snapshot(endpoint, task.segment_id, attempt_ms)
    except Exception:
        pass
