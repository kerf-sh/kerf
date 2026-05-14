"""
Hermetic tests for kerf_core.revisions (Phase 4: revision DB efficiency).

Tests use an in-memory fake asyncpg-like pool — no Postgres required.

Covers:
  - compute_unified_diff + apply_unified_diff round-trips
  - _compress / _decompress_row codec='gzip' (raw bytea)
  - _decompress_row codec='plain' legacy base64-encoded path
  - SHA-256 dedup: identical content skips insert
  - Rebase trigger: after REBASE_THRESHOLD diffs a new base is written
  - Cap pruning: old rows beyond cap are removed; chain-parents are protected
  - write_revision → reconstruct_revision full round-trip (multi-diff chain)
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import pytest

from kerf_core.revisions import (
    REBASE_THRESHOLD,
    _compress,
    _decompress_row,
    _sha256,
    apply_unified_diff,
    compute_unified_diff,
    reconstruct_revision,
    write_revision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


class FakePool:
    """
    Minimal asyncpg-compatible fake pool backed by an in-memory ordered dict.

    Supports:
      fetchrow(query, *args)   — returns the last inserted/matching Row or None
      fetchval(query, *args)   — returns a scalar
      execute(query, *args)    — mutates state
      fetch(query, *args)      — returns a list of rows

    The implementation is intentionally query-key-based rather than a real
    SQL engine; each test below sets up the expected query outcomes directly.
    """

    def __init__(self):
        # Ordered by insertion; each entry is a dict representing a row.
        self._revisions: "OrderedDict[uuid.UUID, dict]" = OrderedDict()

    # --- asyncpg-style Record proxy ---

    class Row(dict):
        """Dict subclass that supports both dict[key] and record[key] access."""

        def keys(self):
            return super().keys()

        def __getitem__(self, key):
            return super().__getitem__(key)

    # --- Helpers ---

    def _rows_for_file(self, file_id: uuid.UUID) -> list[dict]:
        fid = uuid.UUID(str(file_id)) if not isinstance(file_id, uuid.UUID) else file_id
        return [r for r in self._revisions.values() if r["file_id"] == fid]

    def _rows_for_file_sorted(self, file_id: uuid.UUID) -> list[dict]:
        return sorted(self._rows_for_file(file_id), key=lambda r: r["created_at"])

    # --- asyncpg interface ---

    async def fetchrow(self, query: str, *args) -> "FakePool.Row | None":
        if not args:
            return None
        # SELECT ... FROM file_revisions WHERE id = $1
        if "WHERE id = $1" in query:
            rid = uuid.UUID(str(args[0]))
            row = self._revisions.get(rid)
            return self.Row(row) if row else None

        # SELECT ... file_id = $1 ORDER BY created_at DESC LIMIT 1
        if "file_id = $1" in query and "ORDER BY created_at DESC LIMIT 1" in query:
            file_id = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(file_id)
            return self.Row(rows[-1]) if rows else None

        return None

    async def fetchval(self, query: str, *args) -> Any:
        # COUNT(*) diffs since last base
        if "COUNT(*)" in query and "file_id = $1" in query:
            file_id = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(file_id)
            # Find last base
            last_base_ts = datetime.min.replace(tzinfo=timezone.utc)
            for r in rows:
                if r["kind"] == "base":
                    last_base_ts = r["created_at"]
            count = sum(
                1 for r in rows
                if r["kind"] == "diff" and r["created_at"] > last_base_ts
            )
            return count
        return 0

    async def execute(self, query: str, *args) -> None:
        if query.strip().startswith("INSERT INTO file_revisions"):
            self._handle_insert(query, args)
        elif query.strip().startswith("DELETE FROM file_revisions"):
            self._handle_delete(query, args)

    async def fetch(self, query: str, *args) -> list:
        return []

    # --- Mutation helpers ---

    def _handle_insert(self, query: str, args):
        """
        Parse positional args from the INSERT queries emitted by write_revision.

        Base SQL (7 params):
          VALUES ($1, $2, '', $3, 'gzip', 'base', $4, $5, $6, $7)
          args: id, file_id, content_gz, source, user_id, content_sha256, preview

        Diff SQL (8 params):
          VALUES ($1, $2, '', $3, 'gzip', 'diff', $4, $5, $6, $7, $8)
          args: id, file_id, content_gz, parent_revision_id, source, user_id,
                content_sha256, preview
        """
        now = _now()
        if "'base'" in query:
            # 7 positional args
            new_id = args[0]
            file_id = args[1]
            content_gz = args[2]
            source = args[3]
            user_id = args[4]
            content_sha256 = args[5]
            preview = args[6]
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(file_id)),
                "content": "",
                "content_gz": content_gz,
                "content_codec": "gzip",
                "kind": "base",
                "source": source,
                "user_id": user_id,
                "content_sha256": content_sha256,
                "content_preview": preview,
                "parent_revision_id": None,
                "created_at": now,
            }
        else:  # diff — 8 positional args
            new_id = args[0]
            file_id = args[1]
            content_gz = args[2]
            parent_revision_id = args[3]
            source = args[4]
            user_id = args[5]
            content_sha256 = args[6]
            preview = args[7]
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(file_id)),
                "content": "",
                "content_gz": content_gz,
                "content_codec": "gzip",
                "kind": "diff",
                "source": source,
                "user_id": user_id,
                "content_sha256": content_sha256,
                "content_preview": preview,
                "parent_revision_id": uuid.UUID(str(parent_revision_id)),
                "created_at": now,
            }
        self._revisions[row["id"]] = row

    def _handle_delete(self, query: str, args):
        file_id = uuid.UUID(str(args[0]))
        cap = int(args[1])

        # Collect parent ids that are referenced (must not be deleted)
        protected_parents = {
            r["parent_revision_id"]
            for r in self._revisions.values()
            if r.get("parent_revision_id") is not None
        }

        rows = self._rows_for_file_sorted(file_id)
        # Keep the most recent `cap` rows
        keep_ids = {r["id"] for r in rows[-cap:]}

        to_delete = [
            r["id"] for r in rows
            if r["id"] not in keep_ids
            and r["id"] not in protected_parents
        ]
        for rid in to_delete:
            del self._revisions[rid]


# ---------------------------------------------------------------------------
# Pure function tests (no pool needed)
# ---------------------------------------------------------------------------

def test_sha256_is_bytes():
    h = _sha256("hello")
    assert isinstance(h, bytes)
    assert len(h) == 32


def test_compress_round_trip():
    original = "hello world\nthis is a test\n" * 100
    compressed = _compress(original)
    assert isinstance(compressed, bytes)
    assert len(compressed) < len(original.encode())
    assert gzip.decompress(compressed).decode() == original


def test_decompress_row_gzip_codec():
    content = "some content\nmore lines\n"
    gz = _compress(content)
    row = {"content_gz": gz, "content": "", "content_codec": "gzip"}
    assert _decompress_row(row) == content


def test_decompress_row_plain_codec_base64():
    """Legacy path: content_codec='plain', content_gz is a base64 string."""
    import base64
    content = "legacy content\n"
    gz_raw = gzip.compress(content.encode())
    b64_str = base64.b64encode(gz_raw).decode()
    row = {"content_gz": b64_str, "content": "", "content_codec": "plain"}
    assert _decompress_row(row) == content


def test_decompress_row_fallback_to_plain():
    row = {"content_gz": None, "content": "fallback", "content_codec": "plain"}
    assert _decompress_row(row) == "fallback"


def test_unified_diff_empty_to_content():
    patch = compute_unified_diff("", "hello\nworld\n")
    result = apply_unified_diff("", patch)
    assert result == "hello\nworld\n"


def test_unified_diff_content_to_empty():
    original = "hello\nworld\n"
    patch = compute_unified_diff(original, "")
    result = apply_unified_diff(original, patch)
    assert result == ""


def test_unified_diff_single_line_change():
    old = "line1\nline2\nline3\n"
    new = "line1\nLINE2\nline3\n"
    patch = compute_unified_diff(old, new)
    result = apply_unified_diff(old, patch)
    assert result == new


def test_unified_diff_multiline_add():
    old = "a\nb\n"
    new = "a\nb\nc\nd\n"
    patch = compute_unified_diff(old, new)
    result = apply_unified_diff(old, patch)
    assert result == new


def test_unified_diff_multiline_remove():
    old = "a\nb\nc\nd\n"
    new = "a\nd\n"
    patch = compute_unified_diff(old, new)
    result = apply_unified_diff(old, patch)
    assert result == new


def test_unified_diff_identity():
    content = "unchanged\ncontent\n"
    patch = compute_unified_diff(content, content)
    # Identity patch → no changes → output same as input
    result = apply_unified_diff(content, patch)
    assert result == content


def test_unified_diff_large_json():
    """Round-trip on a plausible 1 MB CAD JSON blob."""
    import json
    data = {"version": 1, "objects": [{"id": f"obj-{i}", "x": i * 1.1} for i in range(10_000)]}
    original = json.dumps(data, indent=2)
    # Simulate a small edit: change one value
    modified_data = dict(data)
    modified_data["objects"] = list(data["objects"])
    modified_data["objects"][500] = {"id": "obj-500", "x": 9999.0}
    modified = json.dumps(modified_data, indent=2)

    patch = compute_unified_diff(original, modified)
    result = apply_unified_diff(original, patch)
    assert result == modified

    # Diff should be much smaller than full content
    assert len(patch.encode()) < len(modified.encode()) * 0.1


# ---------------------------------------------------------------------------
# Pool-based tests
# ---------------------------------------------------------------------------

@pytest.fixture
def pool():
    return FakePool()


@pytest.fixture
def file_id():
    return uuid.uuid4()


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_first_write_creates_base(pool, file_id):
    rid = run(write_revision(pool, file_id, "initial content", "tool"))
    assert isinstance(rid, uuid.UUID)
    rows = pool._rows_for_file(file_id)
    assert len(rows) == 1
    assert rows[0]["kind"] == "base"
    assert rows[0]["content_codec"] == "gzip"


def test_second_write_creates_diff(pool, file_id):
    run(write_revision(pool, file_id, "version 1\n", "tool"))
    run(write_revision(pool, file_id, "version 2\n", "tool"))
    rows = pool._rows_for_file_sorted(file_id)
    assert rows[0]["kind"] == "base"
    assert rows[1]["kind"] == "diff"


def test_sha256_dedup_skips_insert(pool, file_id):
    content = "same content\n"
    rid1 = run(write_revision(pool, file_id, content, "tool"))
    rid2 = run(write_revision(pool, file_id, content, "tool"))
    # Same id returned, no new row inserted
    assert rid1 == rid2
    assert len(pool._rows_for_file(file_id)) == 1


def test_rebase_triggers_after_threshold(pool, file_id):
    run(write_revision(pool, file_id, "base content\n", "tool"))
    for i in range(REBASE_THRESHOLD):
        run(write_revision(pool, file_id, f"edit {i}\n", "tool"))
    # The (REBASE_THRESHOLD+1)-th write should be a new base
    run(write_revision(pool, file_id, "after threshold\n", "tool"))
    rows = pool._rows_for_file_sorted(file_id)
    base_rows = [r for r in rows if r["kind"] == "base"]
    assert len(base_rows) >= 2, "Expected a second base row after threshold"
    assert rows[-1]["kind"] == "base"


def test_cap_pruning_removes_old_rows(pool, file_id):
    cap = 5
    for i in range(10):
        run(write_revision(pool, file_id, f"revision {i}\n", "tool", cap=cap))
    rows = pool._rows_for_file(file_id)
    assert len(rows) <= cap + 1  # +1 tolerance for chain-parent protection


def test_cap_pruning_does_not_break_chain(pool, file_id):
    """
    After pruning, any remaining 'diff' rows must still have their
    parent_revision_id present in the pool.
    """
    cap = 5
    for i in range(15):
        run(write_revision(pool, file_id, f"line {i}\n", "tool", cap=cap))

    rows = pool._rows_for_file(file_id)
    all_ids = {r["id"] for r in rows}
    for r in rows:
        if r["kind"] == "diff" and r["parent_revision_id"] is not None:
            assert r["parent_revision_id"] in all_ids, (
                f"Diff row {r['id']} references missing parent {r['parent_revision_id']}"
            )


def test_reconstruct_single_base(pool, file_id):
    content = "hello world\n"
    rid = run(write_revision(pool, file_id, content, "tool"))
    result = run(reconstruct_revision(pool, rid))
    assert result == content


def test_reconstruct_diff_chain(pool, file_id):
    """Write N revisions, reconstruct the last one."""
    versions = [
        "version 0\nsome content here\n",
        "version 1\nsome content here\nedited\n",
        "version 2\nsome other content here\nedited\n",
        "version 3\nfinal state\n",
    ]
    last_id = None
    for v in versions:
        last_id = run(write_revision(pool, file_id, v, "tool"))

    result = run(reconstruct_revision(pool, last_id))
    assert result == versions[-1]


def test_reconstruct_intermediate_revision(pool, file_id):
    """Reconstruct an intermediate diff revision."""
    v0 = "initial\n"
    v1 = "initial\nplus one\n"
    v2 = "initial\nplus one\nplus two\n"

    run(write_revision(pool, file_id, v0, "tool"))
    rid1 = run(write_revision(pool, file_id, v1, "tool"))
    run(write_revision(pool, file_id, v2, "tool"))

    result = run(reconstruct_revision(pool, rid1))
    assert result == v1


def test_reconstruct_missing_returns_empty(pool):
    result = run(reconstruct_revision(pool, uuid.uuid4()))
    assert result == ""


def test_compress_gives_significant_shrink_on_large_content():
    """Verify gzip actually helps on realistic JSON content."""
    import json
    data = {"version": 1, "nodes": [{"id": i, "val": "x" * 50} for i in range(1000)]}
    content = json.dumps(data)
    compressed = _compress(content)
    ratio = len(compressed) / len(content.encode())
    assert ratio < 0.25, f"Expected <25% size ratio, got {ratio:.2%}"
