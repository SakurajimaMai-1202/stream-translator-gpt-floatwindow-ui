"""Small dependency-free Server-Sent Events parser."""

from __future__ import annotations

import codecs


class SseEventParser:
    """Incrementally parse UTF-8 Server-Sent Events across arbitrary chunks."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""
        self._pending_cr = False

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        text = self._decoder.decode(chunk)
        if self._pending_cr:
            text = "\r" + text
            self._pending_cr = False
        if text.endswith("\r"):
            text = text[:-1]
            self._pending_cr = True
        self._buffer += text.replace("\r\n", "\n").replace("\r", "\n")
        events: list[tuple[str, str]] = []

        while "\n\n" in self._buffer:
            block, self._buffer = self._buffer.split("\n\n", 1)
            event_type = "message"
            data_lines: list[str] = []
            for line in block.split("\n"):
                if not line or line.startswith(":"):
                    continue
                field, separator, value = line.partition(":")
                if separator and value.startswith(" "):
                    value = value[1:]
                if field == "event":
                    event_type = value
                elif field == "data":
                    data_lines.append(value)
            if data_lines:
                events.append((event_type, "\n".join(data_lines)))

        return events
