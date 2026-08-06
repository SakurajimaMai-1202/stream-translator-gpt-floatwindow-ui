import json
import logging
import os
import re
import sys
import threading
import unicodedata
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


GLOSSARY_AUDIT_LOG_MAX_BYTES = 5 * 1024 * 1024
GLOSSARY_AUDIT_LOG_BACKUP_COUNT = 5
GLOSSARY_ISSUE_MIN_OBSERVATIONS = 2
GLOSSARY_ISSUE_MAX_RECORDS = 500
_LOGGER_NAME = "translation.glossary_audit"


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", value)


def _resolve_log_path(filename: str) -> Path:
    configured_dir = os.environ.get("STREAM_TRANSLATOR_LOG_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser() / filename
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "logs" / filename
    return Path(__file__).resolve().parents[2] / "app" / "logs" / filename


class TranslationGlossaryAuditor:
    """Audit provider-independent translation output against the active glossary."""

    def __init__(
        self,
        glossary: dict[str, str] | None,
        enabled: bool = False,
        audit_log_path: str | Path | None = None,
        issues_path: str | Path | None = None,
    ) -> None:
        self.enabled = bool(enabled and glossary)
        self.glossary = {
            str(source).strip(): str(target).strip()
            for source, target in (glossary or {}).items()
            if str(source).strip() and str(target).strip()
        }
        self.audit_log_path = Path(audit_log_path) if audit_log_path else _resolve_log_path("translation_glossary_audit.log")
        self.issues_path = Path(issues_path) if issues_path else _resolve_log_path("translation_glossary_issues.json")
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._handler: RotatingFileHandler | None = None
        if self.enabled:
            self._configure()

    def _configure(self) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.issues_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"{_LOGGER_NAME}.{id(self)}")
        logger.propagate = False
        logger.setLevel(logging.INFO)
        self._handler = RotatingFileHandler(
            self.audit_log_path,
            maxBytes=GLOSSARY_AUDIT_LOG_MAX_BYTES,
            backupCount=GLOSSARY_AUDIT_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(self._handler)
        self._logger = logger
        if self.issues_path.exists():
            try:
                payload = json.loads(self.issues_path.read_text(encoding="utf-8"))
                if payload.get("version") == 1:
                    for record in payload.get("records", []) + payload.get("pending_records", []):
                        if isinstance(record, dict) and record.get("normalized_source") and record.get("normalized_expected"):
                            key = f"{record['normalized_source']}\0{record['normalized_expected']}"
                            self._records[key] = record
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                self._records = {}

    def audit(self, task: Any) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        source_text = str(getattr(task, "transcript", "") or "")
        translation = str(getattr(task, "translation", "") or "")
        normalized_source_text = _normalize(source_text)
        normalized_translation = _normalize(translation)
        results = []
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._lock:
            for source_term, expected in self.glossary.items():
                normalized_source = _normalize(source_term)
                if not normalized_source or normalized_source not in normalized_source_text:
                    continue
                normalized_expected = _normalize(expected)
                compliant = bool(normalized_expected and normalized_expected in normalized_translation)
                payload = {
                    "timestamp": timestamp,
                    "event": "glossary_compliance",
                    "segment_id": getattr(task, "segment_id", None),
                    "time_range": list(getattr(task, "time_range", ()) or ()),
                    "provider": getattr(task, "translation_provider", None),
                    "model": getattr(task, "translation_model", None),
                    "source_term": source_term,
                    "expected_translation": expected,
                    "source_text": source_text,
                    "translation": translation,
                    "compliant": compliant,
                }
                self._logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                results.append(payload)
                if not compliant:
                    self._record_issue(payload, normalized_source, normalized_expected)
            if results:
                self._write_summary()
        return results

    def _record_issue(self, payload: dict[str, Any], normalized_source: str, normalized_expected: str) -> None:
        key = f"{normalized_source}\0{normalized_expected}"
        record = self._records.get(key)
        example = {
            "segment_id": payload["segment_id"],
            "source_text": payload["source_text"],
            "translation": payload["translation"],
        }
        if record is None:
            record = {
                "source_term": payload["source_term"],
                "normalized_source": normalized_source,
                "expected_translation": payload["expected_translation"],
                "normalized_expected": normalized_expected,
                "count": 0,
                "first_seen": payload["timestamp"],
                "last_seen": payload["timestamp"],
                "examples": [],
                "providers": [],
                "models": [],
            }
            self._records[key] = record
        record["count"] = int(record.get("count", 0)) + 1
        record["last_seen"] = payload["timestamp"]
        if example not in record["examples"]:
            record["examples"] = (record["examples"] + [example])[-5:]
        for field, value in (("providers", payload["provider"]), ("models", payload["model"])):
            if value and value not in record[field]:
                record[field].append(value)

    def _write_summary(self) -> None:
        ordered = sorted(self._records.values(), key=lambda item: (-int(item.get("count", 0)), item.get("source_term", "")))
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "minimum_observations": GLOSSARY_ISSUE_MIN_OBSERVATIONS,
            "records": [r for r in ordered if int(r.get("count", 0)) >= GLOSSARY_ISSUE_MIN_OBSERVATIONS][:GLOSSARY_ISSUE_MAX_RECORDS],
            "pending_records": [r for r in ordered if int(r.get("count", 0)) < GLOSSARY_ISSUE_MIN_OBSERVATIONS][:GLOSSARY_ISSUE_MAX_RECORDS],
        }
        temporary = self.issues_path.with_name(f"{self.issues_path.name}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.issues_path)
