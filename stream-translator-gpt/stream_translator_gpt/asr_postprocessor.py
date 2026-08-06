import json
from difflib import SequenceMatcher
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


ASR_CORRECTION_LOG_MAX_BYTES = 5 * 1024 * 1024
ASR_CORRECTION_LOG_BACKUP_COUNT = 5
_ASR_CORRECTION_LOGGER_NAME = "asr.corrections"
_ASR_CORRECTION_CANDIDATE_LOGGER_NAME = "asr.correction_candidates"
_asr_correction_log_handler: RotatingFileHandler | None = None
_asr_correction_log_path: Path | None = None
_asr_correction_candidate_log_handler: RotatingFileHandler | None = None
_asr_correction_candidate_log_path: Path | None = None
_asr_correction_candidate_summary_path: Path | None = None
_asr_correction_candidate_records: dict[str, dict[str, Any]] = {}
_asr_correction_log_lock = threading.RLock()
ASR_CORRECTION_CANDIDATE_LOG_MAX_BYTES = 5 * 1024 * 1024
ASR_CORRECTION_CANDIDATE_LOG_BACKUP_COUNT = 5
ASR_CORRECTION_CANDIDATE_MAX_RECORDS = 500
ASR_CORRECTION_CANDIDATE_MIN_OBSERVATIONS = 2


def resolve_asr_correction_log_path() -> Path:
    """Resolve the standalone ASR correction JSONL log path."""
    configured_path = os.environ.get("STREAM_TRANSLATOR_ASR_CORRECTION_LOG", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()

    configured_dir = os.environ.get("STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser() / "asr_corrections.log"

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "logs" / "asr_corrections.log"

    # Development checkout: keep this beside the backend.log family.
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "app" / "logs" / "asr_corrections.log"


def _resolve_asr_auxiliary_log_path(filename: str) -> Path:
    configured_dir = os.environ.get("STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser() / filename

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "logs" / filename

    project_root = Path(__file__).resolve().parents[2]
    return project_root / "app" / "logs" / filename


def configure_asr_correction_logging(enabled: bool, log_path: str | Path | None = None) -> None:
    """Enable or disable the standalone ASR correction JSONL log."""
    global _asr_correction_log_handler, _asr_correction_log_path

    logger = logging.getLogger(_ASR_CORRECTION_LOGGER_NAME)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with _asr_correction_log_lock:
        if not enabled:
            if _asr_correction_log_handler is not None:
                logger.removeHandler(_asr_correction_log_handler)
                _asr_correction_log_handler.close()
                _asr_correction_log_handler = None
                _asr_correction_log_path = None
            return

        resolved_path = Path(log_path).expanduser() if log_path else resolve_asr_correction_log_path()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        if (
            _asr_correction_log_handler is not None
            and _asr_correction_log_path == resolved_path
        ):
            return

        if _asr_correction_log_handler is not None:
            logger.removeHandler(_asr_correction_log_handler)
            _asr_correction_log_handler.close()

        handler = RotatingFileHandler(
            resolved_path,
            maxBytes=ASR_CORRECTION_LOG_MAX_BYTES,
            backupCount=ASR_CORRECTION_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _asr_correction_log_handler = handler
        _asr_correction_log_path = resolved_path


def log_asr_correction(payload: dict[str, Any]) -> None:
    """Write one JSON object to the standalone ASR correction log."""
    logger = logging.getLogger(_ASR_CORRECTION_LOGGER_NAME)
    if _asr_correction_log_handler is None:
        return
    logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _normalize_candidate_text(value: str, case_sensitive: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = "".join(
        chr(ord(character) - 0x60)
        if "\u30a1" <= character <= "\u30f6"
        else character
        for character in normalized
    )
    normalized = re.sub(r"\s+", "", normalized)
    return normalized if case_sensitive else normalized.casefold()


def _candidate_chunks(value: str, case_sensitive: bool = False) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return [
        chunk.strip() for chunk in re.split(
            r"[\s\u3000,\uFF0C.\u3002!?\uFF01\uFF1F\u3001;\uFF1B:\uFF1A\u300C\u300D\u300E\u300F\uFF08\uFF09()\u3010\u3011\[\]\u3008\u3009<>\u2026\u2014\u2013\-_/\\|]+",
            normalized,
        ) if chunk.strip()
    ]


def _contains_meaningful_text(value: str) -> bool:
    return any(character.isalnum() for character in value)


def _name_core(value: str) -> str:
    for suffix in ("ちゃん", "さん", "くん", "さま", "様", "氏"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[:-len(suffix)]
    return value


def configure_asr_correction_learning(
    enabled: bool,
    candidate_log_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> None:
    """Enable or disable unmatched ASR candidate collection."""
    global _asr_correction_candidate_log_handler
    global _asr_correction_candidate_log_path, _asr_correction_candidate_summary_path
    global _asr_correction_candidate_records

    logger = logging.getLogger(_ASR_CORRECTION_CANDIDATE_LOGGER_NAME)
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with _asr_correction_log_lock:
        if not enabled:
            if _asr_correction_candidate_log_handler is not None:
                logger.removeHandler(_asr_correction_candidate_log_handler)
                _asr_correction_candidate_log_handler.close()
            _asr_correction_candidate_log_handler = None
            _asr_correction_candidate_log_path = None
            _asr_correction_candidate_summary_path = None
            _asr_correction_candidate_records = {}
            return

        resolved_log_path = (
            Path(candidate_log_path).expanduser()
            if candidate_log_path
            else _resolve_asr_auxiliary_log_path("asr_correction_candidates.log")
        )
        resolved_summary_path = (
            Path(summary_path).expanduser()
            if summary_path
            else _resolve_asr_auxiliary_log_path("asr_correction_suggestions.json")
        )
        resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_summary_path.parent.mkdir(parents=True, exist_ok=True)

        if (
            _asr_correction_candidate_log_handler is not None
            and _asr_correction_candidate_log_path == resolved_log_path
            and _asr_correction_candidate_summary_path == resolved_summary_path
        ):
            return

        if _asr_correction_candidate_log_handler is not None:
            logger.removeHandler(_asr_correction_candidate_log_handler)
            _asr_correction_candidate_log_handler.close()

        handler = RotatingFileHandler(
            resolved_log_path,
            maxBytes=ASR_CORRECTION_CANDIDATE_LOG_MAX_BYTES,
            backupCount=ASR_CORRECTION_CANDIDATE_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _asr_correction_candidate_log_handler = handler
        _asr_correction_candidate_log_path = resolved_log_path
        _asr_correction_candidate_summary_path = resolved_summary_path

        _asr_correction_candidate_records = {}
        if resolved_summary_path.exists():
            try:
                payload = json.loads(resolved_summary_path.read_text(encoding="utf-8"))
                version = payload.get("version") if isinstance(payload, dict) else None
                records = []
                if version == 2:
                    records.extend(payload.get("records", []))
                    records.extend(payload.get("pending_records", []))
                if isinstance(records, list):
                    for record in records:
                        if not isinstance(record, dict):
                            continue
                        normalized_alias = str(record.get("normalized_alias") or "").strip()
                        canonical = str(record.get("canonical") or "").strip()
                        if normalized_alias and canonical:
                            key = f"{normalized_alias}\0{canonical}"
                            _asr_correction_candidate_records[key] = record
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                _asr_correction_candidate_records = {}


def _write_candidate_summary() -> None:
    if _asr_correction_candidate_summary_path is None:
        return
    all_records = sorted(
        _asr_correction_candidate_records.values(),
        key=lambda record: (
            -int(record.get("count", 0)),
            -float(record.get("best_score", 0)),
            str(record.get("alias", "")),
        ),
    )
    records = [
        record for record in all_records
        if int(record.get("count", 0)) >= ASR_CORRECTION_CANDIDATE_MIN_OBSERVATIONS
    ][:ASR_CORRECTION_CANDIDATE_MAX_RECORDS]
    pending_records = [
        record for record in all_records
        if int(record.get("count", 0)) < ASR_CORRECTION_CANDIDATE_MIN_OBSERVATIONS
    ][:ASR_CORRECTION_CANDIDATE_MAX_RECORDS]
    payload = {
        "version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_observations": ASR_CORRECTION_CANDIDATE_MIN_OBSERVATIONS,
        "records": records,
        "pending_records": pending_records,
    }
    temporary_path = _asr_correction_candidate_summary_path.with_name(
        f"{_asr_correction_candidate_summary_path.name}.tmp"
    )
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, _asr_correction_candidate_summary_path)


def observe_asr_correction_candidate(
    corrector: "ASRTermCorrector",
    text: str,
    *,
    segment_id: int | None = None,
    time_range: tuple[float, float] | None = None,
    asr_engine: str | None = None,
    asr_model: str | None = None,
    language: str | None = None,
) -> None:
    """Record an unmatched transcript and conservative alias suggestions."""
    if _asr_correction_candidate_log_handler is None or not text or not corrector.has_canonicals:
        return

    try:
        suggestions = corrector.suggest_aliases(text)
        normalized_text = _normalize_candidate_text(
            text,
            case_sensitive=corrector.case_sensitive,
        )
        if not normalized_text or not _contains_meaningful_text(normalized_text):
            return
        now = datetime.now(timezone.utc).isoformat()
        engine_label = asr_engine or "unknown"
        suggestion_counts: list[dict[str, Any]] = []

        for suggestion in suggestions:
            alias = str(suggestion.get("alias") or "").strip()
            canonical = str(suggestion.get("canonical") or "").strip()
            normalized_alias = _normalize_candidate_text(
                alias,
                case_sensitive=corrector.case_sensitive,
            )
            if not alias or not canonical or not _contains_meaningful_text(normalized_alias):
                continue

            key = f"{normalized_alias}\0{canonical}"
            record = _asr_correction_candidate_records.get(key)
            if record is None:
                record = {
                    "alias": alias,
                    "normalized_alias": normalized_alias,
                    "canonical": canonical,
                    "count": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "best_score": 0.0,
                    "examples": [],
                    "asr_engines": [],
                }
                _asr_correction_candidate_records[key] = record

            record["count"] = int(record.get("count", 0)) + 1
            record["last_seen"] = now
            score = float(suggestion.get("score", 0))
            record["best_score"] = max(float(record.get("best_score", 0)), score)
            if score >= float(record.get("best_score", 0)):
                record["alias"] = alias
                if suggestion.get("matched_anchor"):
                    record["matched_anchor"] = suggestion["matched_anchor"]

            examples = list(record.get("examples") or [])
            if text not in examples:
                examples.append(text)
            record["examples"] = examples[-5:]

            engines = list(record.get("asr_engines") or [])
            if engine_label not in engines:
                engines.append(engine_label)
            record["asr_engines"] = engines[:20]
            suggestion_counts.append({
                "alias": record["alias"],
                "canonical": canonical,
                "count": record["count"],
                "score": score,
            })

        logger = logging.getLogger(_ASR_CORRECTION_CANDIDATE_LOGGER_NAME)
        logger.info(json.dumps({
            "timestamp": now,
            "event": "unmatched_observation",
            "segment_id": segment_id,
            "time_range": list(time_range) if time_range else None,
            "asr_engine": asr_engine,
            "asr_model": asr_model,
            "language": language,
            "text": text,
            "suggestions": suggestions,
            "suggestion_counts": suggestion_counts,
        }, ensure_ascii=False, separators=(",", ":")))
        _write_candidate_summary()
    except Exception:
        # Learning must never interrupt live ASR.
        logging.getLogger(__name__).debug(
            "Unable to record ASR correction candidate",
            exc_info=True,
        )


class ASRTermCorrector:
    """Apply non-chaining ASR term corrections using longest aliases first."""

    def __init__(self, rules: Any = None, case_sensitive: bool = False):
        self.case_sensitive = bool(case_sensitive)
        self._replacements: dict[str, str] = {}
        self._canonicals: list[str] = []
        self._suggestion_targets: list[dict[str, Any]] = []
        aliases: list[str] = []

        for rule in self._normalize_rules(rules):
            canonical = str(rule.get("canonical") or "").strip()
            if not canonical:
                continue
            if canonical not in self._canonicals:
                self._canonicals.append(canonical)
            suggestion_anchors = [canonical]
            for alias in rule.get("aliases") or []:
                alias = str(alias or "").strip()
                if not alias or alias == canonical:
                    continue
                suggestion_anchors.append(alias)
                key = alias if self.case_sensitive else alias.casefold()
                if key in self._replacements:
                    continue
                self._replacements[key] = canonical
                aliases.append(alias)
            self._suggestion_targets.append({
                "canonical": canonical,
                "anchors": list(dict.fromkeys(suggestion_anchors)),
            })

        aliases.sort(key=len, reverse=True)
        flags = 0 if self.case_sensitive else re.IGNORECASE
        self._pattern = re.compile(
            "|".join(re.escape(alias) for alias in aliases),
            flags,
        ) if aliases else None

    @property
    def has_canonicals(self) -> bool:
        return bool(self._canonicals)

    def suggest_aliases(self, text: str, minimum_score: float = 0.82) -> list[dict[str, Any]]:
        """Suggest short alias spans by comparing canonical names and known aliases."""
        if not text or not self._suggestion_targets:
            return []

        normalized_text = _normalize_candidate_text(
            text,
            case_sensitive=self.case_sensitive,
        )
        suggestions: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for target in self._suggestion_targets:
            canonical = str(target["canonical"])
            anchors = [
                (anchor, _normalize_candidate_text(
                    anchor,
                    case_sensitive=self.case_sensitive,
                ))
                for anchor in target["anchors"]
            ]
            anchors = [item for item in anchors if len(item[1]) >= 3]
            if not anchors:
                continue
            if any(normalized_anchor in normalized_text for _, normalized_anchor in anchors):
                continue
            known_aliases = {normalized for _, normalized in anchors}

            best_candidate: str | None = None
            best_anchor: str | None = None
            best_score = 0.0
            for chunk in _candidate_chunks(text, case_sensitive=self.case_sensitive):
                for anchor, normalized_anchor in anchors:
                    target_length = len(normalized_anchor)
                    anchor_core = _name_core(normalized_anchor)
                    lengths = set(range(
                        max(3, target_length - 3),
                        min(len(chunk), target_length + 2) + 1,
                    ))
                    if len(anchor_core) >= 3:
                        lengths.update(range(
                            max(3, len(anchor_core) - 1),
                            min(len(chunk), len(anchor_core) + 1) + 1,
                        ))

                    for length in sorted(lengths):
                        for start in range(0, len(chunk) - length + 1):
                            candidate = chunk[start:start + length]
                            normalized_candidate = _normalize_candidate_text(
                                candidate,
                                case_sensitive=self.case_sensitive,
                            )
                            if normalized_candidate in known_aliases:
                                continue

                            raw_score = SequenceMatcher(
                                None,
                                normalized_anchor,
                                normalized_candidate,
                            ).ratio()
                            score = raw_score - (
                                0.06 * abs(target_length - len(normalized_candidate))
                            )
                            if target_length == len(normalized_candidate):
                                differing_indexes = [
                                    index
                                    for index, (left, right) in enumerate(zip(
                                        normalized_anchor,
                                        normalized_candidate,
                                    ))
                                    if left != right
                                ]
                                trailing_particle = (
                                    differing_indexes == [target_length - 1]
                                    and normalized_candidate[-1] in "がはをにでとのもへ"
                                )
                                if len(differing_indexes) == 1 and not trailing_particle:
                                    score = max(score, 0.97)
                            if (
                                len(anchor_core) >= 3
                                and normalized_candidate == anchor_core
                            ):
                                score = max(score, 0.90)
                            if (
                                len(normalized_candidate) >= 4
                                and abs(target_length - len(normalized_candidate)) <= 3
                                and (
                                    normalized_anchor.startswith(normalized_candidate)
                                    or normalized_candidate.startswith(normalized_anchor)
                                )
                            ):
                                length_difference = abs(
                                    target_length - len(normalized_candidate)
                                )
                                prefix_score = 0.92 - 0.02 * length_difference
                                if (
                                    normalized_anchor.startswith(normalized_candidate)
                                    and normalized_candidate != anchor_core
                                ):
                                    prefix_score = 0.96 - 0.01 * length_difference
                                score = max(score, prefix_score)

                            if score > best_score:
                                best_candidate = candidate
                                best_anchor = anchor
                                best_score = score

            if best_candidate is None or best_score < minimum_score:
                continue
            normalized_candidate = _normalize_candidate_text(
                best_candidate,
                case_sensitive=self.case_sensitive,
            )
            key = (normalized_candidate, canonical)
            if key in seen:
                continue
            seen.add(key)
            suggestion = {
                "alias": best_candidate,
                "canonical": canonical,
                "score": round(best_score, 3),
            }
            if best_anchor:
                suggestion["matched_anchor"] = best_anchor
            suggestions.append(suggestion)

        return sorted(suggestions, key=lambda item: -float(item["score"]))[:5]

    @staticmethod
    def _normalize_rules(rules: Any) -> list[dict[str, Any]]:
        if not rules:
            return []
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
        return rules if isinstance(rules, list) else []

    def apply(self, text: str) -> str:
        corrected, _ = self.apply_with_details(text)
        return corrected

    def apply_with_details(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """Apply corrections and return the matched alias details."""
        if not text or self._pattern is None:
            return text, []

        matches: list[dict[str, str]] = []

        def replace(match: re.Match) -> str:
            value = match.group(0)
            key = value if self.case_sensitive else value.casefold()
            canonical = self._replacements.get(key, value)
            if canonical != value:
                matches.append({"alias": value, "canonical": canonical})
            return canonical

        return self._pattern.sub(replace, text), matches
