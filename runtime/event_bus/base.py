from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: UUID
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]
    correlation_id: UUID


EventHandler = Callable[[EventEnvelope], Coroutine[Any, Any, None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event_type: str, payload: dict[str, Any], correlation_id: UUID) -> None:
        """Publish an event. Fire-and-forget."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an async handler for an event type."""

    @abstractmethod
    async def start(self) -> None:
        """Start the dispatch loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the dispatch loop and drain pending events."""
