import asyncio
import json
import time
import threading
import copy
from typing import Any, AsyncGenerator

from backend.core.config_secrets import mask_secrets


class AppSyncBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            'type': event_type,
            'payload': {
                **mask_secrets(payload),
                'emitted_at': time.time(),
            },
        }

        async with self._lock:
            subscribers = list(self._subscribers)

        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

    def publish_status(self, event_type: str, payload: dict[str, Any]) -> None:
        """Schedule immutable status snapshots on the subscriber event loop."""
        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            event = {'type': event_type, 'payload': copy.deepcopy(payload)}
            loop.call_soon_threadsafe(self._deliver_status, event)
        except Exception:
            pass  # A disconnected stream must never fail an installation.

    def _deliver_status(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def stream(self) -> AsyncGenerator[str, None]:
        queue = await self.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ': ping\n\n'
        finally:
            await self.unsubscribe(queue)


broker = AppSyncBroker()


async def publish_app_event(event_type: str, payload: dict[str, Any]) -> None:
    await broker.publish(event_type, payload)


class StatusPublisher:
    """Per-job progress limiter; transitions and terminal snapshots bypass it."""
    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        self._lock = threading.Lock()
        self._last: dict[str, tuple[float, str]] = {}

    def publish(self, payload_factory, *, key: str = '', state: str = '', force: bool = False) -> None:
        try:
            with self._lock:
                now = time.monotonic()
                previous = self._last.get(key)
                if not force and state not in {"completed", "error", "failed", "cancelled"} and previous and previous[1] == state and now - previous[0] < 0.25:
                    return
                payload = payload_factory()
                broker.publish_status(self.event_type, payload)
                self._last[key] = (now, state)
        except Exception:
            pass
