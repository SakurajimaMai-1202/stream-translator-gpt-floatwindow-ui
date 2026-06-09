import json
import queue
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4


DEFAULT_PUBLIC_PORT = 8765
DEFAULT_PUBLIC_HOST = "0.0.0.0"
PING_INTERVAL_SECONDS = 15
MAX_HISTORY_EVENTS = 200
LIVE_SUBTITLES_PAGE_PATHS = {"/", "/live_subtitles.html"}
_LIVE_SUBTITLES_HTML: bytes | None = None


def create_task_id() -> str:
    return uuid4().hex


def _load_live_subtitles_html() -> bytes:
    global _LIVE_SUBTITLES_HTML
    if _LIVE_SUBTITLES_HTML is None:
        html_path = resources.files("stream_translator_gpt").joinpath("assets/live_subtitles.html")
        _LIVE_SUBTITLES_HTML = html_path.read_bytes()
    return _LIVE_SUBTITLES_HTML


def format_srt_timestamp(second: float) -> str:
    second = max(0.0, float(second))
    hours = int(second // 3600)
    minutes = int((second % 3600) // 60)
    seconds = int(second % 60)
    milliseconds = int(round((second - int(second)) * 1000))
    if milliseconds == 1000:
        milliseconds = 0
        seconds += 1
        if seconds == 60:
            seconds = 0
            minutes += 1
            if minutes == 60:
                minutes = 0
                hours += 1
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


@dataclass
class SharedTask:
    task_id: str
    pid: int | None
    status: str = "running"
    code: int | None = None
    history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=MAX_HISTORY_EVENTS))
    subscribers: set[queue.Queue] = field(default_factory=set)

    def status_payload(self) -> dict[str, Any]:
        if self.status == "completed":
            return {"status": "completed", "code": self.code}
        payload = {"status": self.status}
        if self.pid is not None:
            payload["pid"] = self.pid
        return payload


class SubtitleShareServer:

    def __init__(self,
         host: str = DEFAULT_PUBLIC_HOST,
         port: int = DEFAULT_PUBLIC_PORT,
         enabled: bool = False) -> None:
        self.host = host
        self.port = int(port)
        self.enabled = bool(enabled)
        self.push_token = f"st_{secrets.token_urlsafe(32)}"
        self._lock = threading.RLock()
        self._tasks: dict[str, SharedTask] = {}
        self._active_task_id: str | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def active_task_id(self) -> str | None:
        with self._lock:
            task = self._get_active_task_locked()
            if not task:
                return None
            return task.task_id

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        if self._httpd is not None:
            return

        share_server = self

        class RequestHandler(SubtitleShareRequestHandler):
            pass

        RequestHandler.share_server = share_server
        self._httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="subtitle-share-server")
        self._thread.daemon = True
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
            self._active_task_id = None
        for task in tasks:
            if task.status != "completed":
                self._broadcast(task, {"event": "error", "data": {"message": "Subtitle sharing is disabled"}})
            self._close_subscribers(task)
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        with self._lock:
            was_enabled = self.enabled
            self.enabled = enabled
            tasks = list(self._tasks.values()) if was_enabled and not enabled else []
            self._active_task_id = None if not enabled else self._active_task_id
        if was_enabled and not enabled:
            for task in tasks:
                self._broadcast(task, {"event": "error", "data": {"message": "Subtitle sharing is disabled"}})
                self._close_subscribers(task)

    def begin_task(self, task_id: str, pid: int | None) -> None:
        with self._lock:
            self.enabled = True
            task = SharedTask(task_id=task_id, pid=pid)
            self._tasks[task_id] = task
            self._active_task_id = task_id
        self._broadcast(task, {"event": "status", "data": task.status_payload()})

    def finish_task(self, task_id: str, code: int | None) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if task.status == "completed" and task.code == code:
                return
            task.status = "completed"
            task.code = code
            if self._active_task_id == task_id:
                self._active_task_id = None
        self._broadcast(task, {"event": "status", "data": task.status_payload()})

    def publish_subtitle(self, task_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            event = {"event": "subtitle", "data": data}
            task.history.append(event)
        self._broadcast(task, event)
        return True

    def publish_status(self, task_id: str, data: dict[str, Any]) -> bool:
        status = data.get("status")
        if status == "completed":
            self.finish_task(task_id, data.get("code"))
            return True
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if status:
                task.status = status
            if "pid" in data:
                task.pid = data["pid"]
        self._broadcast(task, {"event": "status", "data": task.status_payload()})
        return True

    def active_task_payload(self) -> dict[str, Any]:
        with self._lock:
            task = self._get_active_task_locked()
            if task is None:
                return {"success": False, "task_id": None}
            return {"success": True, "task_id": task.task_id}

    def server_info_payload(self) -> dict[str, Any]:
        return {
            "public_host": self.host,
            "public_port": self.port,
            "enable_subtitle_sharing": bool(self.enabled and self.is_running),
        }

    def subscribe(self, task_id: str) -> tuple[queue.Queue, list[dict[str, Any]], dict[str, Any]] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            subscriber_queue: queue.Queue = queue.Queue()
            task.subscribers.add(subscriber_queue)
            history = list(task.history)
            status_event = {"event": "status", "data": task.status_payload()}
            return subscriber_queue, history, status_event

    def unsubscribe(self, task_id: str, subscriber_queue: queue.Queue) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.subscribers.discard(subscriber_queue)

    def validate_push_token(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(token, self.push_token)

    def _get_active_task_locked(self) -> SharedTask | None:
        if not self._active_task_id:
            return None
        task = self._tasks.get(self._active_task_id)
        if task is None or task.status == "completed":
            return None
        return task

    def _broadcast(self, task: SharedTask, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(task.subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def _close_subscribers(self, task: SharedTask) -> None:
        with self._lock:
            subscribers = list(task.subscribers)
            task.subscribers.clear()
        for subscriber in subscribers:
            subscriber.put(None)


class SubtitleShareRequestHandler(BaseHTTPRequestHandler):
    share_server: SubtitleShareServer

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in LIVE_SUBTITLES_PAGE_PATHS:
            self._handle_live_subtitles_page()
            return
        if parsed.path == "/api/server/info":
            self._handle_server_info()
            return
        if parsed.path == "/api/translation/active-task":
            self._handle_active_task()
            return
        if parsed.path.startswith("/api/translation/stream/"):
            task_id = unquote(parsed.path.removeprefix("/api/translation/stream/"))
            self._handle_stream(task_id)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"message": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/translation/push/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Not found"})
            return

        task_id = unquote(parsed.path.removeprefix("/api/translation/push/"))
        query_token = parse_qs(parsed.query).get("token", [None])[0]
        token = query_token or self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not self.share_server.validate_push_token(token):
            self._send_json(HTTPStatus.FORBIDDEN, {"success": False, "message": "Forbidden"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"success": False, "message": "Invalid JSON"})
            return

        event = payload.get("event")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"success": False, "message": "Invalid event data"})
            return

        if event == "subtitle":
            success = self.share_server.publish_subtitle(task_id, data)
        elif event == "status":
            success = self.share_server.publish_status(task_id, data)
        else:
            self._send_json(HTTPStatus.BAD_REQUEST, {"success": False, "message": "Unknown event"})
            return

        if not success:
            self._send_json(HTTPStatus.NOT_FOUND, {"success": False, "message": "Task not found"})
            return
        self._send_json(HTTPStatus.OK, {"success": True})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_server_info(self) -> None:
        self._send_json(HTTPStatus.OK, self.share_server.server_info_payload())

    def _handle_live_subtitles_page(self) -> None:
        try:
            body = _load_live_subtitles_html()
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Live subtitle page not found"})
            return
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_active_task(self) -> None:
        if not self.share_server.enabled:
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Subtitle sharing is disabled"})
            return
        self._send_json(HTTPStatus.OK, self.share_server.active_task_payload())

    def _handle_stream(self, task_id: str) -> None:
        if not self.share_server.enabled:
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Subtitle sharing is disabled"})
            return
        subscription = self.share_server.subscribe(task_id)
        if subscription is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"message": "Task not found"})
            return

        subscriber_queue, history, status_event = subscription
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self._write_sse_event(status_event)
            for event in history:
                self._write_sse_event(event)
            while True:
                try:
                    event = subscriber_queue.get(timeout=PING_INTERVAL_SECONDS)
                except queue.Empty:
                    self._write_raw_sse(": ping\n\n")
                    continue
                if event is None:
                    break
                self._write_sse_event(event)
                if event.get("event") == "status" and event.get("data", {}).get("status") == "completed":
                    time.sleep(0.1)
                    break
                if event.get("event") == "error":
                    time.sleep(0.1)
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.share_server.unsubscribe(task_id, subscriber_queue)

    def _write_sse_event(self, event: dict[str, Any]) -> None:
        event_name = event.get("event")
        if event_name:
            self._write_raw_sse(f"event: {event_name}\n")
        data = json.dumps(event.get("data") or {}, ensure_ascii=False, separators=(",", ":"))
        for line in data.splitlines() or [""]:
            self._write_raw_sse(f"data: {line}\n")
        self._write_raw_sse("\n")

    def _write_raw_sse(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
