"""In-process pub/sub used to stream investigation progress over SSE.

Swap ``EventBus`` for a Redis/NATS-backed implementation to run multiple API
workers; the orchestrator only depends on the ``publish`` coroutine.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: Any


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._max_queue = max_queue

    async def publish(self, channel: str, event_type: str, data: Any) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            try:
                queue.put_nowait(Event(event_type, data))
            except asyncio.QueueFull:
                logger.warning("dropping slow SSE subscriber on %s", channel)
                self._subscribers[channel].discard(queue)

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[Event]]:
        """``async with bus.subscribe(id) as queue`` — unsubscribes on exit."""
        queue: asyncio.Queue[Event] = asyncio.Queue(self._max_queue)
        self._subscribers[channel].add(queue)
        try:
            yield queue
        finally:
            subs = self._subscribers.get(channel)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(channel, None)

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))
