import json
import re
from typing import Any


class ASRTermCorrector:
    """Apply non-chaining ASR term corrections using longest aliases first."""

    def __init__(self, rules: Any = None, case_sensitive: bool = False):
        self.case_sensitive = bool(case_sensitive)
        self._replacements: dict[str, str] = {}
        aliases: list[str] = []

        for rule in self._normalize_rules(rules):
            canonical = str(rule.get("canonical") or "").strip()
            if not canonical:
                continue
            for alias in rule.get("aliases") or []:
                alias = str(alias or "").strip()
                if not alias or alias == canonical:
                    continue
                key = alias if self.case_sensitive else alias.casefold()
                if key in self._replacements:
                    continue
                self._replacements[key] = canonical
                aliases.append(alias)

        aliases.sort(key=len, reverse=True)
        flags = 0 if self.case_sensitive else re.IGNORECASE
        self._pattern = re.compile(
            "|".join(re.escape(alias) for alias in aliases),
            flags,
        ) if aliases else None

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
        if not text or self._pattern is None:
            return text

        def replace(match: re.Match) -> str:
            value = match.group(0)
            key = value if self.case_sensitive else value.casefold()
            return self._replacements.get(key, value)

        return self._pattern.sub(replace, text)
