"""Yjs-compatible document envelope.

``YDoc`` is the top-level collaborative document.  It owns:

* A collection of named ``YMap`` roots (keyed by name, e.g. ``"feature_tree"``,
  ``"metadata"``, ``"camera"``).
* A collection of named ``YArray`` roots.
* A per-client ``LogicalClock`` that advances on every local operation.
* An ``apply_update`` method that ingests a batch of ``Op`` objects received
  from a remote peer.

The document id is fixed at construction time; two ``YDoc`` instances
representing the same collaborative session must share the same ``doc_id``.

Usage example
~~~~~~~~~~~~~
::

    doc_a = YDoc(doc_id="proj-123", client_id="alice")
    doc_b = YDoc(doc_id="proj-123", client_id="bob")

    tree_a = doc_a.get_map("feature_tree")
    lc = doc_a.tick()
    op = tree_a.set("body1", {"type": "Box", "size": [10, 10, 10]}, lc)

    # Replicate to B
    doc_b.apply_update([op])

    tree_b = doc_b.get_map("feature_tree")
    assert tree_b.get("body1") == {"type": "Box", "size": [10, 10, 10]}
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Sequence

from kerf_cloud.collab.crdt import LogicalClock, Op, YArray, YMap


class YDoc:
    """Top-level collaborative document.

    Parameters
    ----------
    doc_id:
        Stable identifier shared by all peers editing the same document.
        Two ``YDoc`` instances with the same *doc_id* can exchange ``Op``
        objects via ``apply_update`` / ``pending_ops``.
    client_id:
        Unique identifier for this peer.  Should be stable for the lifetime
        of an editing session (e.g. a UUID generated on connect).
    initial_clock:
        Starting Lamport value (default 0).  Useful when re-joining a session
        to avoid clock regression.
    """

    def __init__(
        self,
        doc_id: Optional[str] = None,
        client_id: Optional[str] = None,
        initial_clock: int = 0,
    ) -> None:
        self.doc_id: str = doc_id or str(uuid.uuid4())
        self.client_id: str = client_id or str(uuid.uuid4())
        self._clock = LogicalClock(clock=initial_clock, client_id=self.client_id)
        self._maps: Dict[str, YMap] = {}
        self._arrays: Dict[str, YArray] = {}
        # Ops generated locally since last ``drain_ops`` call
        self._pending: List[Op] = []

    # ------------------------------------------------------------------
    # Clock management
    # ------------------------------------------------------------------

    def tick(self) -> LogicalClock:
        """Advance the local clock by one and return the new value.

        Call this immediately before generating an operation so that the
        operation carries a monotonically increasing timestamp.
        """
        self._clock = self._clock.advance()
        return self._clock

    def _receive_clock(self, remote: LogicalClock) -> None:
        """Merge a remote clock into the local clock (Lamport receive rule)."""
        self._clock = self._clock.advance(remote)

    # ------------------------------------------------------------------
    # Root accessors
    # ------------------------------------------------------------------

    def get_map(self, name: str) -> YMap:
        """Return (creating if necessary) the named ``YMap`` root."""
        if name not in self._maps:
            # Use a deterministic map_id derived from doc + name so that
            # maps with the same logical name on different peers share the
            # same target_id (required for cross-peer apply to work).
            map_id = f"{self.doc_id}:map:{name}"
            self._maps[name] = YMap(map_id=map_id)
        return self._maps[name]

    def get_array(self, name: str) -> YArray:
        """Return (creating if necessary) the named ``YArray`` root."""
        if name not in self._arrays:
            array_id = f"{self.doc_id}:array:{name}"
            self._arrays[name] = YArray(array_id=array_id)
        return self._arrays[name]

    # ------------------------------------------------------------------
    # Replication helpers
    # ------------------------------------------------------------------

    def apply_update(self, ops: Sequence[Op]) -> None:
        """Ingest a sequence of ``Op`` objects from a remote peer.

        Each op is routed to the correct root based on ``target_id``.  Unknown
        target ids are silently skipped (forward-compatibility).

        The local clock is advanced past the highest remote clock seen.
        """
        for op in ops:
            # Advance our clock to stay ahead of remote
            self._receive_clock(op.lc)

            # Route to the right root (may need to create it)
            target = op.target_id
            # Map roots have target_id of the form "<doc_id>:map:<name>"
            map_prefix = f"{self.doc_id}:map:"
            array_prefix = f"{self.doc_id}:array:"

            if target.startswith(map_prefix):
                name = target[len(map_prefix):]
                self.get_map(name).apply(op)
            elif target.startswith(array_prefix):
                name = target[len(array_prefix):]
                self.get_array(name).apply(op)
            # else: unknown root — skip

    def collect_ops(self) -> List[Op]:
        """Return all ops from all roots (for initial sync / state vector)."""
        ops: List[Op] = []
        for m in self._maps.values():
            ops.extend(m.ops)
        for a in self._arrays.values():
            ops.extend(a.ops)
        return ops
