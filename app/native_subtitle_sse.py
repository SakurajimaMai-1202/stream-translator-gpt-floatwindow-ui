"""Qt-native SSE subscriber for the floating subtitle window."""

from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from sse_parser import SseEventParser


logger = logging.getLogger(__name__)


class NativeSubtitleSseClient(QObject):
    """Subscribe the native subtitle renderer directly to the backend SSE."""

    subtitleReceived = pyqtSignal(str)
    taskStarted = pyqtSignal(str)
    connectionStateChanged = pyqtSignal(str)

    def __init__(self, base_url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self._manager = QNetworkAccessManager(self)
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(True)
        self._poll_timer.timeout.connect(self._request_active_task)
        self._running = False
        self._request_in_flight = False
        self._active_reply: QNetworkReply | None = None
        self._stream_reply: QNetworkReply | None = None
        self._parser: SseEventParser | None = None
        self._reconnect_attempt = 0
        self._current_task_id: str | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._reconnect_attempt = 0
        self._schedule_poll(0)

    def stop(self) -> None:
        self._running = False
        self._poll_timer.stop()
        self._request_in_flight = False
        for reply in (self._active_reply, self._stream_reply):
            if reply is not None and reply.isRunning():
                reply.abort()
        self._active_reply = None
        self._stream_reply = None
        self._parser = None
        self._current_task_id = None
        self.connectionStateChanged.emit("stopped")

    def _schedule_poll(self, delay_ms: int) -> None:
        if self._running:
            self._poll_timer.start(max(0, delay_ms))

    def _request(self, path: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(f"{self.base_url}{path}"))
        request.setRawHeader(b"Accept", b"application/json, text/event-stream")
        request.setRawHeader(b"Cache-Control", b"no-cache")
        return request

    def _request_active_task(self) -> None:
        if not self._running or self._request_in_flight or self._stream_reply is not None:
            return
        self._request_in_flight = True
        self.connectionStateChanged.emit("discovering")
        reply = self._manager.get(self._request("/api/translation/active-task"))
        self._active_reply = reply
        reply.finished.connect(lambda current=reply: self._active_task_finished(current))

    def _active_task_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._active_reply:
            reply.deleteLater()
            return
        self._active_reply = None
        self._request_in_flight = False
        payload = bytes(reply.readAll())
        error = reply.error()
        reply.deleteLater()
        if not self._running:
            return
        if error != QNetworkReply.NetworkError.NoError:
            logger.warning("原生字幕查詢 active task 失敗: %s", error.name)
            self._schedule_reconnect()
            return

        try:
            data: dict[str, Any] = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            logger.warning("原生字幕收到無效的 active task 回應")
            self._schedule_reconnect()
            return

        task_id = data.get("task_id") if data.get("success") else None
        if not task_id:
            self.connectionStateChanged.emit("waiting")
            self._reconnect_attempt = 0
            self._schedule_poll(3000)
            return
        self._open_stream(str(task_id))

    def _open_stream(self, task_id: str) -> None:
        if not self._running or self._stream_reply is not None:
            return
        self.connectionStateChanged.emit("connecting")
        if self._current_task_id != task_id:
            self._current_task_id = task_id
            self.taskStarted.emit(task_id)
        self._parser = SseEventParser()
        reply = self._manager.get(self._request(f"/api/translation/stream/{task_id}"))
        self._stream_reply = reply
        reply.readyRead.connect(lambda current=reply: self._stream_ready_read(current))
        reply.finished.connect(lambda current=reply: self._stream_finished(current))
        logger.info("原生字幕直接訂閱 SSE task=%s", task_id)

    def _stream_ready_read(self, reply: QNetworkReply) -> None:
        if reply is not self._stream_reply or self._parser is None:
            return
        chunk = bytes(reply.readAll())
        if not chunk:
            return
        self.connectionStateChanged.emit("connected")
        self._reconnect_attempt = 0
        for event_type, payload in self._parser.feed(chunk):
            if event_type == "subtitle":
                try:
                    json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("原生字幕 SSE 收到無效 JSON")
                    continue
                self.subtitleReceived.emit(payload)
            elif event_type in ("error", "completed"):
                reply.abort()

    def _stream_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._stream_reply:
            reply.deleteLater()
            return
        error = reply.error()
        self._stream_reply = None
        self._parser = None
        reply.deleteLater()
        if not self._running:
            return
        if error not in (
            QNetworkReply.NetworkError.NoError,
            QNetworkReply.NetworkError.OperationCanceledError,
        ):
            logger.warning("原生字幕 SSE 中斷: %s", error.name)
        self.connectionStateChanged.emit("reconnecting")
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        delays = (1000, 2000, 5000, 10000)
        delay = delays[min(self._reconnect_attempt, len(delays) - 1)]
        self._reconnect_attempt += 1
        self._schedule_poll(delay)
