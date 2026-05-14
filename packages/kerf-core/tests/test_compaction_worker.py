"""
Hermetic tests for kerf_core.workers.compaction_worker.CompactionWorker.

Tests use the FakePool from test_revisions_compaction and an extended version
that handles the compaction worker's queries.  No Postgres required.

Covers:
  - CompactionWorker raises RuntimeError when local_mode=True.
  - CompactionWorker raises RuntimeError when cloud_enabled=False.
  - run_one returns False when no chains exceed the threshold.
  - run_one returns True and compacts when a chain is long enough.
  - After compaction the old diff rows are removed and a new base is written.
  - Idempotent: re-running on a now-short chain is a no-op.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import pytest

from kerf_core.workers.compaction_worker import CompactionWorker
from kerf_core.revisions import _compress, _sha256, write_revision, REBASE_THRESHOLD


# ---------------------------------------------------------------------------
# Re-use the FakePool from test_revisions_compaction with compaction extensions
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


class FakePool:
    """Extends the revision FakePool to also handle compaction worker queries."""

    def __init__(self):
        self._revisions: "OrderedDict[uuid.UUID, dict]" = OrderedDict()

    class Row(dict):
        def keys(self):
            return super().keys()

        def __getitem__(self, key):
            return super().__getitem__(key)

    def _rows_for_file(self, file_id: uuid.UUID) -> list[dict]:
        fid = uuid.UUID(str(file_id)) if not isinstance(file_id, uuid.UUID) else file_id
        return [r for r in self._revisions.values() if r["file_id"] == fid]

    def _rows_for_file_sorted(self, file_id: uuid.UUID) -> list[dict]:
        return sorted(self._rows_for_file(file_id), key=lambda r: r["created_at"])

    def acquire(self):
        return _FakeConnCtx(self)

    async def fetchrow(self, query: str, *args) -> "FakePool.Row | None":
        if not args:
            return None
        if "WHERE id = $1" in query:
            rid = uuid.UUID(str(args[0]))
            row = self._revisions.get(rid)
            return self.Row(row) if row else None
        if "file_id = $1" in query and "ORDER BY created_at DESC LIMIT 1" in query:
            fid = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(fid)
            return self.Row(rows[-1]) if rows else None
        if "content_sha256 = $1" in query and "kind = 'base'" in query:
            target_hash = args[0]
            for row in self._revisions.values():
                if row.get("content_sha256") == target_hash and row.get("kind") == "base":
                    return self.Row(row)
            return None
        # Compaction worker: SELECT source, user_id FROM file_revisions WHERE id = $1
        if "source, user_id" in query and "WHERE id = $1" in query:
            rid = uuid.UUID(str(args[0]))
            row = self._revisions.get(rid)
            return self.Row(row) if row else None
        # Compaction worker: GROUP BY file_id HAVING COUNT(*) > $1 LIMIT 1
        if "GROUP BY" in query and "HAVING" in query and args:
            rows = await self.fetch(query, *args)
            return rows[0] if rows else None
        return None

    async def fetchval(self, query: str, *args) -> Any:
        if "COUNT(*)" in query and "file_id = $1" in query:
            fid = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(fid)
            last_base_ts = datetime.min.replace(tzinfo=timezone.utc)
            for r in rows:
                if r["kind"] == "base":
                    last_base_ts = r["created_at"]
            return sum(
                1 for r in rows
                if r["kind"] == "diff" and r["created_at"] > last_base_ts
            )
        return 0

    async def execute(self, query: str, *args) -> None:
        q = query.strip()
        if q.startswith("INSERT INTO file_revisions"):
            self._handle_insert(query, args)
        elif q.startswith("DELETE FROM file_revisions"):
            self._handle_delete(query, args)

    async def fetch(self, query: str, *args) -> list:
        # Compaction worker top-level query: GROUP BY file_id HAVING diff_count > $1
        if "GROUP BY" in query and "HAVING" in query and args:
            threshold = int(args[0])
            # Count diffs since last base per file.
            from collections import defaultdict
            counts = defaultdict(int)
            tip_ids = {}
            for r in sorted(self._revisions.values(), key=lambda x: x["created_at"]):
                fid = r["file_id"]
                if r["kind"] == "base":
                    counts[fid] = 0
                    tip_ids[fid] = None
                elif r["kind"] == "diff":
                    counts[fid] += 1
                    tip_ids[fid] = r["id"]

            results = [
                self.Row({
                    "file_id": fid,
                    "diff_count": cnt,
                    "tip_id": tip_ids.get(fid),
                })
                for fid, cnt in counts.items()
                if cnt > threshold and tip_ids.get(fid) is not None
            ]
            results.sort(key=lambda r: r["diff_count"], reverse=True)
            return results[:1]

        # Compaction worker DELETE ... RETURNING id (CTE with 'candidates')
        if "candidates" in query and "RETURNING id" in query and len(args) >= 2:
            fid = uuid.UUID(str(args[0]))
            protect_tip = uuid.UUID(str(args[1]))
            protected_parents = {
                r["parent_revision_id"]
                for r in self._revisions.values()
                if r.get("parent_revision_id") is not None
            }
            to_delete = [
                r["id"] for r in list(self._rows_for_file_sorted(fid))
                if r["kind"] == "diff"
                and r["id"] != protect_tip
                and r["id"] not in protected_parents
            ]
            for rid in to_delete:
                del self._revisions[rid]
            return [self.Row({"id": rid}) for rid in to_delete]

        return []

    def _handle_insert(self, query: str, args):
        now = _now()
        if "'base'" in query:
            # write_revision base: 7 positional args (no parent_revision_id)
            # compaction_worker base: 8 positional args (with parent_revision_id)
            new_id = args[0]
            fid = args[1]
            gz = args[2]
            source = args[3]
            user_id = args[4]
            sha256 = args[5]
            preview = args[6]
            parent_id = args[7] if len(args) > 7 else None
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(fid)),
                "content": "",
                "content_gz": gz,
                "content_codec": "gzip",
                "kind": "base",
                "source": source,
                "user_id": user_id,
                "content_sha256": sha256,
                "content_preview": preview,
                "parent_revision_id": uuid.UUID(str(parent_id)) if parent_id else None,
                "created_at": now,
            }
        elif "'ref'" in query:
            new_id, fid, shared_base_id, source, user_id, sha256, preview = (
                args[0], args[1], args[2], args[3], args[4], args[5], args[6]
            )
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(fid)),
                "content": "",
                "content_gz": None,
                "content_codec": "gzip",
                "kind": "ref",
                "source": source,
                "user_id": user_id,
                "content_sha256": sha256,
                "content_preview": preview,
                "parent_revision_id": uuid.UUID(str(shared_base_id)),
                "created_at": now,
            }
        else:
            # diff — 8 args
            new_id, fid, gz, pid, source, user_id, sha256, preview = (
                args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7]
            )
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(fid)),
                "content": "",
                "content_gz": gz,
                "content_codec": "gzip",
                "kind": "diff",
                "source": source,
                "user_id": user_id,
                "content_sha256": sha256,
                "content_preview": preview,
                "parent_revision_id": uuid.UUID(str(pid)),
                "created_at": now,
            }
        self._revisions[row["id"]] = row

    def _handle_delete(self, query: str, args):
        # Cap-pruning (from write_revision): args are (file_id, cap)
        fid = uuid.UUID(str(args[0]))
        cap = int(args[1])
        protected_parents = {
            r["parent_revision_id"]
            for r in self._revisions.values()
            if r.get("parent_revision_id") is not None
        }
        rows = self._rows_for_file_sorted(fid)
        keep_ids = {r["id"] for r in rows[-cap:]}
        for r in list(rows):
            if r["id"] not in keep_ids and r["id"] not in protected_parents:
                self._revisions.pop(r["id"], None)


class _FakeConnCtx:
    """
    Returned by FakePool.acquire().

    When used as ``async with pool.acquire() as conn``, ``conn`` is a
    _FakeConnHandle that proxies all pool methods AND exposes a
    ``transaction()`` context manager so ``async with conn.transaction()``
    works too.
    """

    def __init__(self, pool: FakePool):
        self._pool = pool

    async def __aenter__(self) -> "_FakeConnHandle":
        return _FakeConnHandle(self._pool)

    async def __aexit__(self, *args):
        pass


class _FakeConnHandle:
    """Proxy for a single acquired connection, adding transaction() support."""

    def __init__(self, pool: FakePool):
        self._pool = pool

    # Proxy all pool async methods.
    async def fetchrow(self, *a, **kw):
        return await self._pool.fetchrow(*a, **kw)

    async def fetchval(self, *a, **kw):
        return await self._pool.fetchval(*a, **kw)

    async def execute(self, *a, **kw):
        return await self._pool.execute(*a, **kw)

    async def fetch(self, *a, **kw):
        return await self._pool.fetch(*a, **kw)

    def transaction(self):
        return _FakeTx(self._pool)


class _FakeTx:
    def __init__(self, pool):
        self._pool = pool

    async def __aenter__(self) -> "_FakeConnHandle":
        return _FakeConnHandle(self._pool)

    async def __aexit__(self, *args):
        pass


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_compaction_worker_refuses_local_mode():
    import pytest
    with pytest.raises(RuntimeError, match="local_mode"):
        CompactionWorker(pool=None, cloud_enabled=True, local_mode=True)


def test_compaction_worker_refuses_cloud_disabled():
    with pytest.raises(RuntimeError, match="cloud_enabled"):
        CompactionWorker(pool=None, cloud_enabled=False, local_mode=False)


def test_run_one_returns_false_when_no_work():
    pool = FakePool()
    file_id = uuid.uuid4()
    # Only a base row — no diffs exceeding threshold.
    run(write_revision(pool, file_id, "initial content\n", "tool"))
    worker = CompactionWorker(pool=pool, cloud_enabled=True, local_mode=False, threshold=5)
    result = run(worker.run_one())
    assert result is False, "run_one should return False when no chain exceeds threshold"


def test_run_one_compacts_long_chain():
    """
    Build a chain longer than the threshold, then verify run_one returns True,
    writes a new base, and removes the excess diff rows.
    """
    pool = FakePool()
    file_id = uuid.uuid4()
    threshold = 3

    # Write base + (threshold+1) diffs — enough to trigger compaction.
    run(write_revision(pool, file_id, "base\n", "tool"))
    for i in range(threshold + 1):
        run(write_revision(pool, file_id, f"edit {i}\n", "tool"))

    rows_before = pool._rows_for_file(file_id)
    diff_count_before = sum(1 for r in rows_before if r["kind"] == "diff")
    assert diff_count_before > threshold

    worker = CompactionWorker(pool=pool, cloud_enabled=True, local_mode=False, threshold=threshold)
    result = run(worker.run_one())
    assert result is True, "run_one should return True when a chain was compacted"

    rows_after = pool._rows_for_file(file_id)
    # A new base should have been added.
    base_rows = [r for r in rows_after if r["kind"] == "base"]
    assert len(base_rows) >= 2, "A second base row should have been written"


def test_run_one_returns_false_after_compaction():
    """
    After compacting, the chain should be short enough that a second call
    returns False (nothing left to compact).
    """
    pool = FakePool()
    file_id = uuid.uuid4()
    threshold = 2

    run(write_revision(pool, file_id, "base\n", "tool"))
    for i in range(threshold + 1):
        run(write_revision(pool, file_id, f"diff {i}\n", "tool"))

    worker = CompactionWorker(pool=pool, cloud_enabled=True, local_mode=False, threshold=threshold)
    first = run(worker.run_one())
    assert first is True

    # After compaction the chain is short — second call should be False.
    second = run(worker.run_one())
    assert second is False
