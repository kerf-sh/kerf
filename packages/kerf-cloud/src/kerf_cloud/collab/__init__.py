"""kerf-cloud collab: CRDT-backed real-time collaboration seed.

Modules
-------
crdt      — core Y.Map / Y.Array CRDT with Lamport timestamps
presence  — ephemeral cursor/selection channel (not a CRDT)
y_doc     — Yjs-compatible document envelope

Design notes
------------
This is a pure-Python seed implementation.  All operations carry a
(lamport_clock, client_id) logical timestamp so that merge is both
commutative and idempotent.  The data model targets ``feature_tree``-shaped
documents (nested maps with array children), matching the shape that
Kerf's CAD core already uses for scene-graph encoding.

No network transport is included here; the caller wires an event bus
(e.g. asyncio queues, Redis pub/sub) and invokes ``YDoc.apply_update``
with the serialised ``Op`` objects.
"""

from kerf_cloud.collab.crdt import YArray, YMap
from kerf_cloud.collab.presence import PresenceChannel
from kerf_cloud.collab.y_doc import YDoc

__all__ = ["YDoc", "YMap", "YArray", "PresenceChannel"]
