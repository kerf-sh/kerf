"""Tests for the CRDT-backed collaboration seed (T-160).

Test plan
---------
1. YMap commutativity  — two clients independently insert keys; merged state
   matches regardless of apply order.
2. YMap idempotency    — applying the same op twice produces no duplicates/changes.
3. YMap Lamport tie-break — concurrent edits to the same key resolve
   deterministically by Lamport clock (higher wins).
4. YArray commutativity — two clients insert at different positions; both
   merges converge to the same list.
5. YArray idempotency  — applying the same array insert op twice is harmless.
6. Presence broadcast  — client A's cursor is visible to client B after
   broadcast (mock event bus, no network).
7. YDoc round-trip     — ops generated via YDoc.get_map() replicate correctly
   to a peer YDoc via apply_update().
"""

import pytest

from kerf_cloud.collab.crdt import (
    LogicalClock,
    YArray,
    YMap,
)
from kerf_cloud.collab.presence import PresenceChannel, PresenceEvent
from kerf_cloud.collab.y_doc import YDoc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def lc(clock: int, client_id: str = "test") -> LogicalClock:
    return LogicalClock(clock=clock, client_id=client_id)


SHARED_MAP_ID = "test-map-001"
SHARED_ARR_ID = "test-arr-001"


def two_maps() -> tuple[YMap, YMap]:
    """Return two YMap instances sharing the same map_id."""
    return YMap(map_id=SHARED_MAP_ID), YMap(map_id=SHARED_MAP_ID)


def two_arrays() -> tuple[YArray, YArray]:
    """Return two YArray instances sharing the same array_id."""
    return YArray(array_id=SHARED_ARR_ID), YArray(array_id=SHARED_ARR_ID)


# ---------------------------------------------------------------------------
# 1. YMap commutativity
# ---------------------------------------------------------------------------


class TestYMapCommutativity:
    """Two clients independently insert different keys; both merge orderings
    must converge to the same final map."""

    def test_disjoint_keys_converge(self) -> None:
        map_a, map_b = two_maps()

        op_a = map_a.set("key_from_a", "value_a", lc(1, "client-a"))
        op_b = map_b.set("key_from_b", "value_b", lc(1, "client-b"))

        # Apply B's op to A and vice versa
        map_a.apply(op_b)
        map_b.apply(op_a)

        assert map_a.to_dict() == map_b.to_dict()
        assert map_a.get("key_from_a") == "value_a"
        assert map_a.get("key_from_b") == "value_b"

    def test_multiple_keys_all_present_after_merge(self) -> None:
        map_a, map_b = two_maps()

        ops_a = [map_a.set(f"a{i}", i, lc(i + 1, "client-a")) for i in range(3)]
        ops_b = [map_b.set(f"b{i}", i * 10, lc(i + 1, "client-b")) for i in range(3)]

        for op in ops_b:
            map_a.apply(op)
        for op in ops_a:
            map_b.apply(op)

        assert map_a.to_dict() == map_b.to_dict()
        assert len(map_a.to_dict()) == 6


# ---------------------------------------------------------------------------
# 2. YMap idempotency
# ---------------------------------------------------------------------------


class TestYMapIdempotency:
    def test_double_apply_no_duplicate(self) -> None:
        m = YMap(map_id="idem-test")
        op = m.set("x", 99, lc(1, "c1"))
        # Apply again — should be a no-op
        m.apply(op)
        assert m.get("x") == 99
        # Only one entry
        assert list(m) == ["x"]

    def test_double_apply_does_not_change_value(self) -> None:
        m = YMap(map_id="idem-test-2")
        op1 = m.set("y", "first", lc(1, "c1"))
        # A second, separate op writes a different value at a higher clock
        op2 = m.set("y", "second", lc(2, "c1"))
        # Re-applying op1 (lower clock) must NOT overwrite the newer value
        m.apply(op1)
        assert m.get("y") == "second"


# ---------------------------------------------------------------------------
# 3. YMap Lamport tie-break
# ---------------------------------------------------------------------------


class TestYMapTieBreak:
    def test_higher_clock_wins(self) -> None:
        map_a, map_b = two_maps()

        op_a = map_a.set("shared_key", "from_a", lc(3, "client-a"))
        op_b = map_b.set("shared_key", "from_b_wins", lc(5, "client-b"))

        # Apply both to a fresh map
        m = YMap(map_id=SHARED_MAP_ID)
        m.apply(op_a)
        m.apply(op_b)
        assert m.get("shared_key") == "from_b_wins"

    def test_equal_clock_client_id_breaks_tie(self) -> None:
        """When clocks are equal, lexicographically higher client_id wins."""
        m = YMap(map_id="tie-test")
        # "zzz" > "aaa"
        op_low = m.set("k", "from_aaa", lc(1, "aaa"))
        m2 = YMap(map_id="tie-test")
        op_high = m2.set("k", "from_zzz", lc(1, "zzz"))

        fresh = YMap(map_id="tie-test")
        fresh.apply(op_low)
        fresh.apply(op_high)
        assert fresh.get("k") == "from_zzz"

    def test_equal_clock_same_client_idempotent(self) -> None:
        """An op with the same clock + client_id as the winner is idempotent."""
        m = YMap(map_id="tie-same")
        op = m.set("k", "v1", lc(2, "c"))
        # Applying the exact same op again must not change anything
        m.apply(op)
        assert m.get("k") == "v1"

    def test_concurrent_write_order_independent(self) -> None:
        """Order of application must not affect the final winner."""
        map_a, map_b = two_maps()
        op_a = map_a.set("shared", "alice", lc(4, "alice"))
        op_b = map_b.set("shared", "bob", lc(6, "bob"))

        # Order 1: a then b
        m1 = YMap(map_id=SHARED_MAP_ID)
        m1.apply(op_a)
        m1.apply(op_b)

        # Order 2: b then a
        m2 = YMap(map_id=SHARED_MAP_ID)
        m2.apply(op_b)
        m2.apply(op_a)

        assert m1.get("shared") == m2.get("shared") == "bob"


# ---------------------------------------------------------------------------
# 4. YArray commutativity
# ---------------------------------------------------------------------------


class TestYArrayCommutativity:
    def test_two_clients_insert_different_positions(self) -> None:
        arr_a, arr_b = two_arrays()

        # A inserts at position 0; B inserts at position 0 with different clock
        op_a = arr_a.insert(0, "from_a", lc(1, "client-a"))
        op_b = arr_b.insert(0, "from_b", lc(2, "client-b"))

        # Merge: A receives B's op; B receives A's op
        arr_a.apply(op_b)
        arr_b.apply(op_a)

        # Both must contain both elements (convergence)
        assert sorted(arr_a.to_list()) == sorted(arr_b.to_list())
        assert set(arr_a.to_list()) == {"from_a", "from_b"}

    def test_multiple_inserts_converge(self) -> None:
        arr_a, arr_b = two_arrays()

        ops_a = [arr_a.insert(i, f"a{i}", lc(i + 1, "ca")) for i in range(3)]
        ops_b = [arr_b.insert(i, f"b{i}", lc(i + 1, "cb")) for i in range(3)]

        for op in ops_b:
            arr_a.apply(op)
        for op in ops_a:
            arr_b.apply(op)

        assert arr_a.to_list() == arr_b.to_list()
        assert len(arr_a.to_list()) == 6


# ---------------------------------------------------------------------------
# 5. YArray idempotency
# ---------------------------------------------------------------------------


class TestYArrayIdempotency:
    def test_double_insert_no_duplicate(self) -> None:
        arr = YArray(array_id="arr-idem")
        op = arr.insert(0, "hello", lc(1, "c"))
        # Apply the same insert op again
        arr.apply(op)
        assert arr.to_list() == ["hello"]

    def test_double_delete_no_error(self) -> None:
        arr = YArray(array_id="arr-del-idem")
        insert_op = arr.insert(0, "item", lc(1, "c"))
        delete_op = arr.delete(0, lc(2, "c"))
        # Apply delete again — must not raise
        arr.apply(delete_op)
        assert arr.to_list() == []


# ---------------------------------------------------------------------------
# 6. Presence broadcast (mock event bus)
# ---------------------------------------------------------------------------


class TestPresenceChannel:
    def test_cursor_broadcast_received_by_subscriber(self) -> None:
        bus = PresenceChannel()
        received: list[PresenceEvent] = []
        bus.subscribe("client-b", received.append)

        bus.broadcast("client-a", {"type": "cursor", "node_id": "body1", "x": 42})

        assert len(received) == 1
        ev = received[0]
        assert ev.client_id == "client-a"
        assert ev.data["x"] == 42

    def test_sender_does_not_receive_own_broadcast(self) -> None:
        bus = PresenceChannel()
        received: list[PresenceEvent] = []
        bus.subscribe("client-a", received.append)  # A subscribes

        bus.broadcast("client-a", {"type": "cursor", "x": 0})

        assert received == []  # A must not echo to itself

    def test_latest_broadcast_wins_in_snapshot(self) -> None:
        bus = PresenceChannel()
        bus.broadcast("client-a", {"x": 10})
        bus.broadcast("client-a", {"x": 99})
        snap = bus.snapshot()
        assert snap["client-a"]["x"] == 99

    def test_multiple_subscribers_all_notified(self) -> None:
        bus = PresenceChannel()
        received_b: list[PresenceEvent] = []
        received_c: list[PresenceEvent] = []
        bus.subscribe("client-b", received_b.append)
        bus.subscribe("client-c", received_c.append)

        bus.broadcast("client-a", {"type": "selection", "nodes": ["n1", "n2"]})

        assert len(received_b) == 1
        assert len(received_c) == 1

    def test_leave_removes_slot_and_subscription(self) -> None:
        bus = PresenceChannel()
        received: list[PresenceEvent] = []
        bus.subscribe("client-b", received.append)
        bus.broadcast("client-a", {"x": 1})
        assert len(received) == 1

        bus.leave("client-a")
        assert "client-a" not in bus.snapshot()

        bus.leave("client-b")
        # No subscribers now — broadcast should not raise
        bus.broadcast("client-a", {"x": 2})


# ---------------------------------------------------------------------------
# 7. YDoc round-trip
# ---------------------------------------------------------------------------


class TestYDocRoundTrip:
    def test_map_op_replicates_to_peer(self) -> None:
        doc_a = YDoc(doc_id="doc-1", client_id="alice")
        doc_b = YDoc(doc_id="doc-1", client_id="bob")

        tree_a = doc_a.get_map("feature_tree")
        lc_a = doc_a.tick()
        tree_a.set("body1", {"type": "Box"}, lc_a)

        # Ship all of A's ops to B
        doc_b.apply_update(doc_a.collect_ops())

        tree_b = doc_b.get_map("feature_tree")
        assert tree_b.get("body1") == {"type": "Box"}

    def test_bidirectional_convergence(self) -> None:
        doc_a = YDoc(doc_id="doc-2", client_id="alice")
        doc_b = YDoc(doc_id="doc-2", client_id="bob")

        # Both clients write independently
        doc_a.get_map("meta").set("title", "from-alice", doc_a.tick())
        doc_b.get_map("meta").set("author", "from-bob", doc_b.tick())

        # Cross-replicate
        doc_a.apply_update(doc_b.collect_ops())
        doc_b.apply_update(doc_a.collect_ops())

        snap_a = doc_a.get_map("meta").to_dict()
        snap_b = doc_b.get_map("meta").to_dict()
        assert snap_a == snap_b
        assert snap_a["title"] == "from-alice"
        assert snap_a["author"] == "from-bob"

    def test_array_in_ydoc_replicates(self) -> None:
        doc_a = YDoc(doc_id="doc-3", client_id="alice")
        doc_b = YDoc(doc_id="doc-3", client_id="bob")

        arr_a = doc_a.get_array("history")
        arr_a.insert(0, "step1", doc_a.tick())
        arr_a.insert(1, "step2", doc_a.tick())

        doc_b.apply_update(doc_a.collect_ops())

        arr_b = doc_b.get_array("history")
        assert arr_b.to_list() == ["step1", "step2"]
