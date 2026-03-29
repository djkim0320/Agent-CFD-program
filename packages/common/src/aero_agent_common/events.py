from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from aero_agent_contracts import EventType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class EventRecord:
    type: EventType
    payload: dict
    job_id: UUID | None = None
    subagent_id: UUID | None = None
    occurred_at: datetime = field(default_factory=utc_now)
    id: UUID = field(default_factory=uuid4)


class EventBus:
    def publish(self, event: EventRecord) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def subscribe(
        self,
        event_type: EventType | None = None,
        callback: Callable[[EventRecord], None] | None = None,
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._subscribers: dict[EventType | None, list[Callable[[EventRecord], None]]] = defaultdict(list)
        self.history: list[EventRecord] = []

    def publish(self, event: EventRecord) -> None:
        self.history.append(event)
        for callback in self._subscribers.get(None, []):
            callback(event)
        for callback in self._subscribers.get(event.type, []):
            callback(event)

    def subscribe(
        self,
        event_type: EventType | None = None,
        callback: Callable[[EventRecord], None] | None = None,
    ) -> None:
        if callback is None:
            raise ValueError("callback is required")
        self._subscribers[event_type].append(callback)
