from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    """Diffusion d'événements serveur vers tous les clients SSE connectés."""

    def __init__(self, max_queue: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._max_queue = max_queue

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, kind: str, data: dict[str, Any] | None = None) -> None:
        event = {"type": kind, "data": data or {}}
        for queue in list(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def subscribe(self, heartbeat: float = 15.0) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._max_queue)
        self._subscribers.add(queue)
        try:
            yield ": connecte\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                payload = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event['type']}\ndata: {payload}\n\n"
        finally:
            self._subscribers.discard(queue)
