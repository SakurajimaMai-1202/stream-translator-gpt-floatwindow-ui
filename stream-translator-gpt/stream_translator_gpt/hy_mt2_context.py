"""Thread-safe source context for HY-MT2 live translation."""

from __future__ import annotations

import threading
from collections import deque


class SourceContext:
    def __init__(self, max_sentences: int):
        self._sources = deque(maxlen=max(0, max_sentences))
        self._lock = threading.Lock()

    def snapshot(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._sources)

    def append(self, source: str) -> None:
        if source:
            with self._lock:
                self._sources.append(source)
