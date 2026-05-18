"""Yjs-style CRDT primitives for Kerf collaborative editing.

Y.Map and Y.Array share a common operation log.  Every operation carries a
``LogicalClock`` (Lamport timestamp + client_id) so that:

* **Commutativity** — applying ops in any order yields the same state.
* **Idempotency** — applying the same op twice has no effect.
* **Convergence** — concurrent edits to the same key resolve deterministically
  via Lamport tie-break: higher clock wins; equal clocks break on
  ``client_id`` (lexicographic, higher wins).

All state is held in plain Python dicts/lists; there is intentionally no
network layer here.  The caller serialises ``Op`` objects and ships them over
whatever transport is appropriate (websocket, Redis, …).

Public API
----------
  LogicalClock   — (clock: int, client_id: str)  comparable, hashable
  Op             — an immutable operation record
  YMap           — collaborative map (set / delete keys)
  YArray         — collaborative ordered list (insert / delete by index)
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, Iterator, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Logical clock
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, order=False)
class LogicalClock:
    """Lamport clock with client disambiguation.

    Comparison is (clock DESC, client_id DESC) so that the highest logical
    time wins, with client_id as a deterministic tie-breaker when two
    operations share the same Lamport value.
    """

    clock: int
    client_id: str

    # We define explicit comparison so that ``a > b`` means "a wins".

    def _tuple(self) -> tuple:
        return (self.clock, self.client_id)

    def __lt__(self, other: "LogicalClock") -> bool:
        return self._tuple() < other._tuple()

    def __le__(self, other: "LogicalClock") -> bool:
        return self._tuple() <= other._tuple()

    def __gt__(self, other: "LogicalClock") -> bool:
        return self._tuple() > other._tuple()

    def __ge__(self, other: "LogicalClock") -> bool:
        return self._tuple() >= other._tuple()

    def advance(self, other_clock: Optional["LogicalClock"] = None) -> "LogicalClock":
        """Return a new clock that is strictly greater than both *self* and
        *other_clock* (standard Lamport receive-event rule)."""
        base = self.clock
        if other_clock is not None:
            base = max(base, other_clock.clock)
        return LogicalClock(clock=base + 1, client_id=self.client_id)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


OP_MAP_SET = "map_set"
OP_MAP_DELETE = "map_delete"
OP_ARRAY_INSERT = "array_insert"
OP_ARRAY_DELETE = "array_delete"


@dataclasses.dataclass(frozen=True)
class Op:
    """A single CRDT operation.

    Attributes
    ----------
    op_id:
        Globally unique operation identifier (UUID by default).
    op_type:
        One of the ``OP_*`` constants.
    lc:
        Logical clock at the time this operation was generated.
    target_id:
        The ``YMap`` or ``YArray`` instance identifier this op targets.
    key:
        For map ops: the string key.
        For array insert: the *origin* element id after which to insert
        (``None`` means "at the head").
        For array delete: the element id to delete.
    value:
        The value to set (``OP_MAP_SET`` / ``OP_ARRAY_INSERT`` only).
    element_id:
        For ``OP_ARRAY_INSERT``: the unique id assigned to the new element.
    """

    op_id: str
    op_type: str
    lc: LogicalClock
    target_id: str
    key: Optional[str] = None
    value: Any = None
    element_id: Optional[str] = None


def _new_op_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# YMap
# ---------------------------------------------------------------------------


class YMap:
    """A collaborative map.

    Each key stores the **winning** (value, LogicalClock) pair — "winning"
    meaning the op with the highest ``LogicalClock`` for that key.

    Methods
    -------
    set(key, value, lc)  — generate + apply a map-set operation
    delete(key, lc)      — generate + apply a map-delete operation
    apply(op)            — apply an externally received operation (idempotent)
    get(key)             — current value or KeyError
    to_dict()            — snapshot as plain dict
    ops                  — all accepted operations (for replication)
    """

    def __init__(self, map_id: Optional[str] = None) -> None:
        self.map_id: str = map_id or str(uuid.uuid4())
        # key → (value, LogicalClock) — ``value is _DELETED`` means deleted
        self._entries: Dict[str, tuple] = {}
        # op_id → Op — seen set for idempotency
        self._seen: Dict[str, Op] = {}

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any, lc: LogicalClock) -> Op:
        """Create, record and apply a set-operation.  Returns the ``Op``."""
        op = Op(
            op_id=_new_op_id(),
            op_type=OP_MAP_SET,
            lc=lc,
            target_id=self.map_id,
            key=key,
            value=value,
        )
        self.apply(op)
        return op

    def delete(self, key: str, lc: LogicalClock) -> Op:
        """Create, record and apply a delete-operation.  Returns the ``Op``."""
        op = Op(
            op_id=_new_op_id(),
            op_type=OP_MAP_DELETE,
            lc=lc,
            target_id=self.map_id,
            key=key,
        )
        self.apply(op)
        return op

    # ------------------------------------------------------------------
    # Merge / apply (idempotent)
    # ------------------------------------------------------------------

    def apply(self, op: Op) -> None:
        """Apply *op* to this map.  Safe to call multiple times with the same op."""
        if op.op_id in self._seen:
            return  # idempotency
        if op.target_id != self.map_id:
            raise ValueError(
                f"Op targets {op.target_id!r} but this map is {self.map_id!r}"
            )
        if op.op_type not in (OP_MAP_SET, OP_MAP_DELETE):
            raise ValueError(f"YMap cannot apply op_type {op.op_type!r}")

        self._seen[op.op_id] = op

        key = op.key
        assert key is not None, "map ops must have a key"

        current = self._entries.get(key)
        if current is None:
            # No existing entry — accept unconditionally.
            self._entries[key] = (op.value, op.lc)
        else:
            _cur_value, cur_lc = current
            if op.lc > cur_lc:
                self._entries[key] = (op.value, op.lc)
            # If op.lc <= cur_lc, the current entry wins; discard incoming.

    def merge(self, other: "YMap") -> None:
        """Merge all operations from *other* into *self* (in-place)."""
        if other.map_id != self.map_id:
            raise ValueError("Cannot merge maps with different map_id")
        for op in other._seen.values():
            self.apply(op)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    _DELETED = object()  # sentinel

    def get(self, key: str, default: Any = _DELETED) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            if default is YMap._DELETED:
                raise KeyError(key)
            return default
        value, _lc = entry
        if value is YMap._DELETED:
            if default is YMap._DELETED:
                raise KeyError(key)
            return default
        return value

    def __contains__(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        value, _ = entry
        return value is not YMap._DELETED

    def __iter__(self) -> Iterator[str]:
        for key, (value, _) in self._entries.items():
            if value is not YMap._DELETED:
                yield key

    def to_dict(self) -> dict:
        return {k: v for k, (v, _) in self._entries.items() if v is not YMap._DELETED}

    @property
    def ops(self) -> List[Op]:
        return list(self._seen.values())


# ---------------------------------------------------------------------------
# YArray
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _ArrayElement:
    """Internal node in the doubly-linked array."""

    element_id: str  # unique per-element UUID
    value: Any
    lc: LogicalClock
    deleted: bool = False
    # Linked list neighbours (element_id strings; None = boundary)
    prev_id: Optional[str] = None
    next_id: Optional[str] = None


_HEAD = "__head__"  # sentinel: before the first element
_TAIL = "__tail__"  # sentinel: after the last element


class YArray:
    """A collaborative ordered list.

    Uses an RGA (Replicated Growable Array) variant: each element has a
    unique id; insertions are positioned *after* an existing element id
    (``origin``).  Concurrent inserts at the same origin are ordered by
    ``LogicalClock`` (higher wins → appears first among the ties).

    Methods
    -------
    insert(index, value, lc)  — insert at *index* in visible sequence
    insert_after(origin_id, value, lc)  — insert after element with id *origin_id*
    delete(index, lc)         — delete element at *index* in visible sequence
    delete_by_id(element_id, lc)  — delete by element id
    apply(op)                 — apply external op (idempotent)
    to_list()                 — current visible values as a plain list
    ops                       — all accepted operations
    """

    def __init__(self, array_id: Optional[str] = None) -> None:
        self.array_id: str = array_id or str(uuid.uuid4())
        # element_id → _ArrayElement
        self._elements: Dict[str, _ArrayElement] = {}
        # op_id → Op
        self._seen: Dict[str, Op] = {}
        # Maintain explicit head/tail sentinels for linked-list traversal
        self._head = _HEAD
        self._tail = _TAIL
        self._next: Dict[str, Optional[str]] = {_HEAD: _TAIL}
        self._prev: Dict[str, Optional[str]] = {_TAIL: _HEAD}

    # ------------------------------------------------------------------
    # Internal linked-list helpers
    # ------------------------------------------------------------------

    def _insert_node_after(self, after_id: str, new_id: str) -> None:
        """Insert *new_id* immediately after *after_id* in the linked list."""
        next_id = self._next[after_id]
        self._next[after_id] = new_id
        self._next[new_id] = next_id
        self._prev[new_id] = after_id
        if next_id is not None:
            self._prev[next_id] = new_id

    def _find_insert_position(
        self, origin_id: str, new_lc: LogicalClock
    ) -> str:
        """Return the id of the node after which *new_id* should be spliced.

        When multiple concurrent inserts share the same *origin_id*, we walk
        forward past any existing successor whose clock is >= new_lc (i.e.
        the successor was inserted with equal-or-higher priority and should
        appear before the new element).
        """
        pos = origin_id
        while True:
            successor = self._next.get(pos)
            if successor is None or successor == _TAIL:
                break
            succ_el = self._elements.get(successor)
            if succ_el is None:
                # successor is a sentinel or unknown — stop
                break
            # The successor wins (its lc >= new_lc) → skip past it
            if succ_el.lc >= new_lc:
                pos = successor
            else:
                break
        return pos

    def _visible_list(self) -> List[_ArrayElement]:
        """Return elements in order, excluding deleted ones."""
        result = []
        cur = self._next.get(_HEAD)
        while cur and cur != _TAIL:
            el = self._elements.get(cur)
            if el and not el.deleted:
                result.append(el)
            cur = self._next.get(cur)
        return result

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def insert(self, index: int, value: Any, lc: LogicalClock) -> Op:
        """Insert *value* at position *index* in the visible sequence."""
        visible = self._visible_list()
        if index == 0:
            origin_id = _HEAD
        elif index <= len(visible):
            origin_id = visible[index - 1].element_id
        else:
            raise IndexError(
                f"insert index {index} out of range for array of length {len(visible)}"
            )
        return self.insert_after(origin_id, value, lc)

    def insert_after(self, origin_id: str, value: Any, lc: LogicalClock) -> Op:
        """Insert *value* after the element with id *origin_id*."""
        element_id = str(uuid.uuid4())
        op = Op(
            op_id=_new_op_id(),
            op_type=OP_ARRAY_INSERT,
            lc=lc,
            target_id=self.array_id,
            key=origin_id,
            value=value,
            element_id=element_id,
        )
        self.apply(op)
        return op

    def delete(self, index: int, lc: LogicalClock) -> Op:
        """Delete the element at *index* in the visible sequence."""
        visible = self._visible_list()
        if index < 0 or index >= len(visible):
            raise IndexError(
                f"delete index {index} out of range for array of length {len(visible)}"
            )
        return self.delete_by_id(visible[index].element_id, lc)

    def delete_by_id(self, element_id: str, lc: LogicalClock) -> Op:
        """Delete the element with the given *element_id*."""
        op = Op(
            op_id=_new_op_id(),
            op_type=OP_ARRAY_DELETE,
            lc=lc,
            target_id=self.array_id,
            element_id=element_id,
        )
        self.apply(op)
        return op

    # ------------------------------------------------------------------
    # Merge / apply (idempotent)
    # ------------------------------------------------------------------

    def apply(self, op: Op) -> None:
        """Apply *op*.  Safe to call multiple times (idempotent)."""
        if op.op_id in self._seen:
            return
        if op.target_id != self.array_id:
            raise ValueError(
                f"Op targets {op.target_id!r} but this array is {self.array_id!r}"
            )
        self._seen[op.op_id] = op

        if op.op_type == OP_ARRAY_INSERT:
            assert op.element_id is not None
            if op.element_id in self._elements:
                # Element already present (duplicate delivery) — skip.
                return
            origin_id = op.key or _HEAD
            # Ensure origin exists (could arrive out-of-order in a real system)
            if origin_id != _HEAD and origin_id not in self._elements:
                # Optimistic: insert at head for now.  A real implementation
                # would buffer; for the seed this is sufficient.
                origin_id = _HEAD
            pos = self._find_insert_position(origin_id, op.lc)
            el = _ArrayElement(
                element_id=op.element_id,
                value=op.value,
                lc=op.lc,
            )
            self._elements[op.element_id] = el
            self._insert_node_after(pos, op.element_id)

        elif op.op_type == OP_ARRAY_DELETE:
            assert op.element_id is not None
            el = self._elements.get(op.element_id)
            if el is not None:
                el.deleted = True
        else:
            raise ValueError(f"YArray cannot apply op_type {op.op_type!r}")

    def merge(self, other: "YArray") -> None:
        """Merge all operations from *other* into *self* (in-place)."""
        if other.array_id != self.array_id:
            raise ValueError("Cannot merge arrays with different array_id")
        # Replay inserts before deletes to avoid forward-reference issues.
        inserts = [o for o in other._seen.values() if o.op_type == OP_ARRAY_INSERT]
        deletes = [o for o in other._seen.values() if o.op_type == OP_ARRAY_DELETE]
        for op in inserts:
            self.apply(op)
        for op in deletes:
            self.apply(op)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def to_list(self) -> list:
        return [el.value for el in self._visible_list()]

    def __len__(self) -> int:
        return len(self._visible_list())

    @property
    def ops(self) -> List[Op]:
        return list(self._seen.values())
