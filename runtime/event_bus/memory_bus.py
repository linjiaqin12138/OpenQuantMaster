from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from .base import EventBus, EventEnvelope, EventHandler


@dataclass
class _PendingEvent:
    event_type: str
    payload: dict[str, Any]
    correlation_id: UUID


class MemoryEventBus(EventBus):
    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: asyncio.Queue[_PendingEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._queue.put_nowait(_PendingEvent("__shutdown__", {}, uuid4()))
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any], correlation_id: UUID) -> None:
        envelope = _PendingEvent(event_type=event_type, payload=payload, correlation_id=correlation_id)
        self._queue.put_nowait(envelope)

    async def _dispatch_loop(self) -> None:
        while True:
            pending = await self._queue.get()
            if pending.event_type == "__shutdown__":
                self._queue.task_done()
                break
            envelope = EventEnvelope(
                event_id=uuid4(),
                event_type=pending.event_type,
                timestamp=datetime.now(timezone.utc),
                payload=pending.payload,
                correlation_id=pending.correlation_id,
            )
            handlers = self._subscribers.get(pending.event_type, [])
            await asyncio.gather(*(h(envelope) for h in handlers), return_exceptions=True)
            self._queue.task_done()

    async def _drain(self) -> None:
        """Test helper: wait until queue is empty."""
        await self._queue.join()
