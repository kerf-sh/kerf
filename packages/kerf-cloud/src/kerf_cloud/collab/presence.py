"""Ephemeral presence channel for cursor positions and selections.

Presence is intentionally **not** a CRDT.  Each client owns its own
presence slot; the latest broadcast for a given client_id wins unconditionally.
There is no merge, no history, no conflict resolution.

Design
------
``PresenceChannel`` is an in-process event bus stub.  In production it would
be backed by Redis pub/sub or a WebSocket fan-out layer.  For the seed we
keep everything in-process so the test suite can exercise the full flow
without infrastructure.

Typical usage
~~~~~~~~~~~~~
::

    bus = PresenceChannel()

    # Client A broadcasts its cursor
    bus.broadcast("client-a", {"type": "cursor", "node_id": "body1", "x": 42, "y": 7})

    # Client B subscribes to all presence events
    received = []
    bus.subscribe("client-b", lambda event: received.append(event))

    # … trigger a broadcast …
    bus.broadcast("client-a", {"type": "cursor", "node_id": "body1", "x": 55, "y": 7})
    # received == [{"client_id": "client-a", "data": {"type": "cursor", ...}}]
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable, Dict, List, Optional


@dataclasses.dataclass
class PresenceEvent:
    """A presence broadcast from a single client."""

    client_id: str
    data: Any  # arbitrary JSON-serialisable payload
    timestamp: float = dataclasses.field(default_factory=time.monotonic)


class PresenceChannel:
    """Simple in-process pub/sub presence bus.

    Attributes
    ----------
    _slots:
        Latest presence data per client_id.
    _subscribers:
        client_id → list of callbacks.  Callbacks are invoked synchronously on
        ``broadcast``; async transports should wrap with ``asyncio.create_task``.
    """

    def __init__(self) -> None:
        self._slots: Dict[str, PresenceEvent] = {}
        # subscriber_id → callable
        self._subscribers: Dict[str, List[Callable[[PresenceEvent], None]]] = {}

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def broadcast(self, client_id: str, data: Any) -> PresenceEvent:
        """Publish presence data for *client_id* to all other subscribers.

        The caller's own subscription (if any) is skipped — a client does not
        need to hear its own cursor position.

        Returns the ``PresenceEvent`` that was dispatched.
        """
        event = PresenceEvent(client_id=client_id, data=data)
        self._slots[client_id] = event
        for subscriber_id, callbacks in self._subscribers.items():
            if subscriber_id == client_id:
                continue  # don't echo back to the sender
            for cb in callbacks:
                cb(event)
        return event

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        subscriber_id: str,
        callback: Callable[[PresenceEvent], None],
    ) -> None:
        """Register *callback* to receive presence events on behalf of *subscriber_id*.

        Multiple callbacks can be registered for the same subscriber_id.
        """
        self._subscribers.setdefault(subscriber_id, []).append(callback)

    def unsubscribe(self, subscriber_id: str) -> None:
        """Remove all callbacks registered for *subscriber_id*."""
        self._subscribers.pop(subscriber_id, None)

    # ------------------------------------------------------------------
    # Read current state
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Return the latest presence data for every known client."""
        return {cid: ev.data for cid, ev in self._slots.items()}

    def get(self, client_id: str) -> Optional[PresenceEvent]:
        """Return the latest ``PresenceEvent`` for *client_id*, or ``None``."""
        return self._slots.get(client_id)

    def leave(self, client_id: str) -> None:
        """Remove a client's presence slot and subscriptions."""
        self._slots.pop(client_id, None)
        self._subscribers.pop(client_id, None)
