import asyncio
import json
import time
from typing import Any, AsyncGenerator


class AppSyncBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
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
                **payload,
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
