"""
T-62 — Feature tests: file_revisions (OSS fine-grained undo)

Scope:
  - source ∈ {user, llm, tool, restore} recorded correctly
  - Compaction (mig 048): content_codec='gzip', REBASE_THRESHOLD new base
  - SHA-256 chain (mig 018): content_sha256 set; same-content dedup; chain integrity
  - Content-ref dedup (mig 049): cross-file ref rows; reconstruct follows pointer
  - Restore semantics: reconstructed content written back as source='restore'
  - 25 distinct edit-sequence test cases spread across all categories above

All tests are hermetic — no Postgres required. They use an in-memory FakePool
(same pattern as kerf-core tests) and call the public kerf_core.revisions API.
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
# In-memory fake pool (mirrors kerf-core/tests/test_revisions_compaction.py)
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


class FakePool:
    """
    Minimal asyncpg-compatible fake pool backed by an in-memory ordered dict.
    Supports fetchrow / fetchval / execute / fetch — enough for write_revision
    and reconstruct_revision.
    """

    def __init__(self):
        self._revisions: "OrderedDict[uuid.UUID, dict]" = OrderedDict()

    class Row(dict):
        def keys(self):
            return super().keys()

        def __getitem__(self, key):
            return super().__getitem__(key)

    # --- helpers ---

    def _rows_for_file(self, file_id: uuid.UUID) -> list[dict]:
        fid = uuid.UUID(str(file_id)) if not isinstance(file_id, uuid.UUID) else file_id
        return [r for r in self._revisions.values() if r["file_id"] == fid]

    def _rows_for_file_sorted(self, file_id: uuid.UUID) -> list[dict]:
        return sorted(self._rows_for_file(file_id), key=lambda r: r["created_at"])

    # --- asyncpg interface ---

    async def fetchrow(self, query: str, *args) -> "FakePool.Row | None":
        if not args:
            return None
        if "WHERE id = $1" in query:
            rid = uuid.UUID(str(args[0]))
            row = self._revisions.get(rid)
            return self.Row(row) if row else None
        if "file_id = $1" in query and "ORDER BY created_at DESC LIMIT 1" in query:
            file_id = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(file_id)
            return self.Row(rows[-1]) if rows else None
        if "content_sha256 = $1" in query and "kind = 'base'" in query:
            target_hash = args[0]
            for row in self._revisions.values():
                if row.get("content_sha256") == target_hash and row.get("kind") == "base":
                    return self.Row(row)
            return None
        return None

    async def fetchval(self, query: str, *args) -> Any:
        if "COUNT(*)" in query and "file_id = $1" in query:
            file_id = uuid.UUID(str(args[0]))
            rows = self._rows_for_file_sorted(file_id)
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
        if query.strip().startswith("INSERT INTO file_revisions"):
            self._handle_insert(query, args)
        elif query.strip().startswith("DELETE FROM file_revisions"):
            self._handle_delete(query, args)

    async def fetch(self, query: str, *args) -> list:
        return []

    def _handle_insert(self, query: str, args):
        now = _now()
        if "'base'" in query:
            new_id, file_id, content_gz, source, user_id, content_sha256, preview = args
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
        elif "'ref'" in query:
            new_id, file_id, shared_base_id, source, user_id, content_sha256, preview = args
            row = {
                "id": uuid.UUID(str(new_id)),
                "file_id": uuid.UUID(str(file_id)),
                "content": "",
                "content_gz": None,
                "content_codec": "gzip",
                "kind": "ref",
                "source": source,
                "user_id": user_id,
                "content_sha256": content_sha256,
                "content_preview": preview,
                "parent_revision_id": uuid.UUID(str(shared_base_id)),
                "created_at": now,
            }
        else:  # diff
            new_id, file_id, content_gz, parent_revision_id, source, user_id, content_sha256, preview = args
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
        protected_parents = {
            r["parent_revision_id"]
            for r in self._revisions.values()
            if r.get("parent_revision_id") is not None
        }
        rows = self._rows_for_file_sorted(file_id)
        keep_ids = {r["id"] for r in rows[-cap:]}
        to_delete = [
            r["id"] for r in rows
            if r["id"] not in keep_ids and r["id"] not in protected_parents
        ]
        for rid in to_delete:
            del self._revisions[rid]


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def pool():
    return FakePool()


@pytest.fixture
def fid():
    return uuid.uuid4()


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1-5: source values
# ---------------------------------------------------------------------------

class TestSources:
    """T-62 sequences 1-5: source ∈ {user, llm, tool, restore, chained}."""

    def test_01_source_user_recorded(self, pool, fid):
        """Source='user' is stored on the row."""
        uid = uuid.uuid4()
        rid = run(write_revision(pool, fid, "user edit\n", "user", user_id=uid))
        row = pool._revisions[rid]
        assert row["source"] == "user"
        assert row["user_id"] == uid

    def test_02_source_llm_recorded(self, pool, fid):
        """Source='llm' is stored on the row."""
        rid = run(write_revision(pool, fid, "llm generated content\n", "llm"))
        row = pool._revisions[rid]
        assert row["source"] == "llm"

    def test_03_source_tool_recorded(self, pool, fid):
        """Source='tool' is stored on the row."""
        rid = run(write_revision(pool, fid, "tool wrote this\n", "tool"))
        row = pool._revisions[rid]
        assert row["source"] == "tool"

    def test_04_source_restore_recorded(self, pool, fid):
        """Source='restore' is stored on the row."""
        run(write_revision(pool, fid, "original\n", "user"))
        rid2 = run(write_revision(pool, fid, "edited\n", "llm"))
        # Simulate restore: reconstruct v1 and write it back as restore
        orig_content = run(reconstruct_revision(pool, pool._rows_for_file_sorted(fid)[0]["id"]))
        rid_r = run(write_revision(pool, fid, orig_content, "restore"))
        row = pool._revisions[rid_r]
        assert row["source"] == "restore"

    def test_05_multi_source_sequence(self, pool, fid):
        """A sequence mixing user → llm → tool sources stores each correctly."""
        for src, content in [
            ("user", "draft v1\n"),
            ("llm", "ai improved draft\n"),
            ("tool", "auto-formatted\n"),
        ]:
            run(write_revision(pool, fid, content, src))
        rows = pool._rows_for_file_sorted(fid)
        sources = [r["source"] for r in rows]
        assert "user" in sources
        assert "llm" in sources
        assert "tool" in sources


# ---------------------------------------------------------------------------
# 6-10: SHA-256 chain integrity (mig 018)
# ---------------------------------------------------------------------------

class TestSha256Chain:
    """T-62 sequences 6-10: SHA-256 set; dedup; chain integrity across diff chain."""

    def test_06_sha256_set_on_base_row(self, pool, fid):
        """content_sha256 is set (non-None) on a base row."""
        rid = run(write_revision(pool, fid, "content to hash\n", "tool"))
        row = pool._revisions[rid]
        assert row["content_sha256"] is not None
        expected = _sha256("content to hash\n")
        assert row["content_sha256"] == expected

    def test_07_sha256_set_on_diff_row(self, pool, fid):
        """content_sha256 is set on diff rows as well as base rows."""
        run(write_revision(pool, fid, "base content\n", "tool"))
        rid2 = run(write_revision(pool, fid, "modified content\n", "tool"))
        row2 = pool._revisions[rid2]
        assert row2["kind"] == "diff"
        assert row2["content_sha256"] is not None
        assert row2["content_sha256"] == _sha256("modified content\n")

    def test_08_same_content_dedup_returns_same_id(self, pool, fid):
        """Identical consecutive saves return the same revision ID (no new row)."""
        content = "no change\n"
        rid1 = run(write_revision(pool, fid, content, "tool"))
        rid2 = run(write_revision(pool, fid, content, "tool"))
        assert rid1 == rid2
        assert len(pool._rows_for_file(fid)) == 1

    def test_09_sha256_chain_integrity_diff_chain(self, pool, fid):
        """Every diff row's sha256 matches the content it represents."""
        versions = [
            "version 0\n",
            "version 1 with extra line\n",
            "version 2\n",
            "version 3 final\n",
        ]
        rids = []
        for v in versions:
            rids.append(run(write_revision(pool, fid, v, "llm")))

        for rid, expected_content in zip(rids, versions):
            row = pool._revisions[rid]
            assert row["content_sha256"] == _sha256(expected_content), (
                f"SHA-256 mismatch for version {expected_content!r}"
            )

    def test_10_sha256_different_sources_same_content_deduped(self, pool, fid):
        """Different source values still dedup when content is identical."""
        content = "shared exact content\n"
        rid1 = run(write_revision(pool, fid, content, "user"))
        rid2 = run(write_revision(pool, fid, content, "llm"))
        assert rid1 == rid2


# ---------------------------------------------------------------------------
# 11-15: Compaction / gzip codec (mig 048)
# ---------------------------------------------------------------------------

class TestCompaction:
    """T-62 sequences 11-15: codec='gzip'; REBASE_THRESHOLD rebases; chain after rebase."""

    def test_11_base_row_uses_gzip_codec(self, pool, fid):
        """Base rows are stored with content_codec='gzip'."""
        rid = run(write_revision(pool, fid, "initial base content\n", "tool"))
        row = pool._revisions[rid]
        assert row["content_codec"] == "gzip"
        assert row["content_gz"] is not None

    def test_12_diff_row_uses_gzip_codec(self, pool, fid):
        """Diff rows also use content_codec='gzip'."""
        run(write_revision(pool, fid, "first version\n", "tool"))
        rid2 = run(write_revision(pool, fid, "second version\n", "tool"))
        row = pool._revisions[rid2]
        assert row["kind"] == "diff"
        assert row["content_codec"] == "gzip"

    def test_13_rebase_triggers_at_threshold(self, pool, fid):
        """After REBASE_THRESHOLD diffs, the next write creates a second base row."""
        run(write_revision(pool, fid, "initial base\n", "tool"))
        for i in range(REBASE_THRESHOLD):
            run(write_revision(pool, fid, f"edit {i}\n", "tool"))
        run(write_revision(pool, fid, "post-threshold\n", "tool"))

        rows = pool._rows_for_file_sorted(fid)
        base_rows = [r for r in rows if r["kind"] == "base"]
        assert len(base_rows) >= 2, f"Expected ≥2 bases, got {len(base_rows)}"
        assert rows[-1]["kind"] == "base"

    def test_14_rebase_row_reconstructs_correctly(self, pool, fid):
        """The new base row after a rebase can be reconstructed correctly."""
        run(write_revision(pool, fid, "initial base\n", "tool"))
        for i in range(REBASE_THRESHOLD):
            run(write_revision(pool, fid, f"edit {i}\n", "tool"))
        final_content = "after rebase\n"
        rid = run(write_revision(pool, fid, final_content, "tool"))
        rows = pool._rows_for_file_sorted(fid)
        assert rows[-1]["kind"] == "base"
        result = run(reconstruct_revision(pool, rid))
        assert result == final_content

    def test_15_multiple_rebase_cycles(self, pool, fid):
        """Two full rebase cycles produce ≥3 base rows, chain always intact."""
        run(write_revision(pool, fid, "cycle 0 base\n", "tool"))
        for cycle in range(2):
            for i in range(REBASE_THRESHOLD):
                run(write_revision(pool, fid, f"cycle {cycle} edit {i}\n", "tool"))
            run(write_revision(pool, fid, f"cycle {cycle} rebase\n", "tool"))

        rows = pool._rows_for_file_sorted(fid)
        base_count = sum(1 for r in rows if r["kind"] == "base")
        assert base_count >= 3

        all_ids = {r["id"] for r in rows}
        for r in rows:
            if r["kind"] == "diff" and r["parent_revision_id"] is not None:
                assert r["parent_revision_id"] in all_ids


# ---------------------------------------------------------------------------
# 16-20: Content-ref dedup (mig 049)
# ---------------------------------------------------------------------------

class TestContentRefDedup:
    """T-62 sequences 16-20: cross-file ref rows; reconstruct follows pointer."""

    def test_16_cross_file_same_content_produces_ref(self, pool):
        """Same content written to two files: second gets a ref row."""
        fa, fb = uuid.uuid4(), uuid.uuid4()
        content = "shared content across two files\n"
        run(write_revision(pool, fa, content, "tool"))
        run(write_revision(pool, fb, content, "tool"))

        rows_b = pool._rows_for_file(fb)
        assert len(rows_b) == 1
        assert rows_b[0]["kind"] == "ref"

    def test_17_ref_row_points_to_base(self, pool):
        """The ref row's parent_revision_id points to the original base row."""
        fa, fb = uuid.uuid4(), uuid.uuid4()
        content = "deduped content\n"
        rid_a = run(write_revision(pool, fa, content, "tool"))
        run(write_revision(pool, fb, content, "tool"))

        ref_row = pool._rows_for_file(fb)[0]
        assert ref_row["parent_revision_id"] == rid_a

    def test_18_ref_row_has_no_content_payload(self, pool):
        """Ref rows store no content_gz payload."""
        fa, fb = uuid.uuid4(), uuid.uuid4()
        content = "content to dedup\n"
        run(write_revision(pool, fa, content, "tool"))
        run(write_revision(pool, fb, content, "tool"))

        ref_row = pool._rows_for_file(fb)[0]
        assert ref_row["content_gz"] is None

    def test_19_reconstruct_ref_returns_correct_content(self, pool):
        """reconstruct_revision on a ref row returns the shared content."""
        fa, fb = uuid.uuid4(), uuid.uuid4()
        content = "exact content to verify on reconstruct\n"
        run(write_revision(pool, fa, content, "tool"))
        ref_id = run(write_revision(pool, fb, content, "llm"))

        result = run(reconstruct_revision(pool, ref_id))
        assert result == content

    def test_20_base_not_pruned_while_ref_exists(self, pool):
        """Cap pruning must not remove a base row pointed to by a live ref."""
        fa, fb = uuid.uuid4(), uuid.uuid4()
        content = "base that must survive pruning\n"
        cap = 2
        run(write_revision(pool, fa, content, "tool", cap=cap))
        base_id = pool._rows_for_file(fa)[0]["id"]

        run(write_revision(pool, fb, content, "tool", cap=cap))
        ref_row = pool._rows_for_file(fb)[0]
        assert ref_row["kind"] == "ref"

        for i in range(cap + 5):
            run(write_revision(pool, fa, f"extra write {i}\n", "tool", cap=cap))

        all_ids = {r["id"] for r in pool._revisions.values()}
        assert base_id in all_ids, "base row must not be pruned while a ref row points to it"

        result = run(reconstruct_revision(pool, ref_row["id"]))
        assert result == content


# ---------------------------------------------------------------------------
# 21-25: Restore semantics + combined sequences
# ---------------------------------------------------------------------------

class TestRestoreAndCombined:
    """T-62 sequences 21-25: restore semantics; combined multi-feature sequences."""

    def test_21_restore_reconstructs_and_rewrites(self, pool, fid):
        """Restore: reconstruct an old revision and write it back as source='restore'."""
        v0 = "original state\n"
        v1 = "changed state\n"
        rid0 = run(write_revision(pool, fid, v0, "user"))
        run(write_revision(pool, fid, v1, "llm"))

        # Restore to v0
        restored_content = run(reconstruct_revision(pool, rid0))
        assert restored_content == v0
        rid_r = run(write_revision(pool, fid, restored_content, "restore"))
        assert pool._revisions[rid_r]["source"] == "restore"

    def test_22_restore_content_matches_original(self, pool, fid):
        """Reconstructed content from a restored revision equals the original."""
        versions = ["v0: initial\n", "v1: modified\n", "v2: more edits\n"]
        rids = [run(write_revision(pool, fid, v, "tool")) for v in versions]

        # Restore to v0
        restored = run(reconstruct_revision(pool, rids[0]))
        assert restored == versions[0]

        rid_r = run(write_revision(pool, fid, restored, "restore"))
        # Reconstruct the restore revision itself
        result = run(reconstruct_revision(pool, rid_r))
        assert result == versions[0]

    def test_23_edit_sequence_25_writes_all_reconstructable(self, pool, fid):
        """25 sequential writes; every revision reconstructs to its written content."""
        uid = uuid.uuid4()
        sources = ["user", "llm", "tool", "restore", "user"]
        contents = [f"revision {i:02d}: {'x' * (i * 3 + 1)}\n" for i in range(25)]
        rids = []
        for i, c in enumerate(contents):
            src = sources[i % len(sources)]
            rids.append(run(write_revision(pool, fid, c, src, user_id=uid if src == "user" else None)))

        # Spot-check every 5th revision
        for idx in range(0, 25, 5):
            result = run(reconstruct_revision(pool, rids[idx]))
            assert result == contents[idx], f"Mismatch at revision {idx}"

    def test_24_sha256_dedup_across_restore_cycle(self, pool, fid):
        """A restore to the current content is deduplicated by SHA-256."""
        content = "stable content\n"
        rid1 = run(write_revision(pool, fid, content, "user"))
        # Simulate a restore that lands on the same content
        rid_r = run(write_revision(pool, fid, content, "restore"))
        # Should be deduplicated — no new row
        assert rid1 == rid_r

    def test_25_full_lifecycle_user_llm_restore_dedup_compaction(self, pool, fid):
        """
        Full lifecycle: user → llm edits → restore → cross-file dedup → compaction.
        Verifies the system stays consistent across all four mechanisms together.

        Cross-file dedup fires when a *base* row in the table matches the incoming
        SHA-256.  We write a dedicated base to fid_base first, then write the same
        content to fb so fb gets a ref row pointing to that base.
        """
        fb = uuid.uuid4()
        fid_base = uuid.uuid4()  # dedicated file whose first write is a base row

        # Phase 1: user writes initial content to fid
        v0 = "initial user draft\n"
        rid0 = run(write_revision(pool, fid, v0, "user"))
        assert pool._revisions[rid0]["kind"] == "base"
        assert pool._revisions[rid0]["source"] == "user"

        # Phase 2: llm makes multiple edits to fid
        for i in range(5):
            run(write_revision(pool, fid, f"llm iteration {i}\ncontent\n", "llm"))

        # Phase 3: tool adds more edits to fid up to trigger compaction
        for i in range(REBASE_THRESHOLD):
            run(write_revision(pool, fid, f"tool step {i}\n", "tool"))
        # This write triggers a new base row for fid
        run(write_revision(pool, fid, "post compaction state fid\n", "tool"))
        rows = pool._rows_for_file_sorted(fid)
        base_count = sum(1 for r in rows if r["kind"] == "base")
        assert base_count >= 2, "Expected a second base row after compaction"

        # Phase 4: cross-file dedup — write shared content to fid_base first
        # (its first write is always a base row), then fb writes the same content
        shared = "cross-file shared content that will be deduped\n"
        rid_base = run(write_revision(pool, fid_base, shared, "tool"))
        assert pool._revisions[rid_base]["kind"] == "base"

        run(write_revision(pool, fb, shared, "tool"))
        rows_b = pool._rows_for_file(fb)
        assert rows_b[0]["kind"] == "ref", "cross-file dedup must produce a ref row"
        ref_row = rows_b[0]

        # Phase 5: restore fid to v0
        restored = run(reconstruct_revision(pool, rid0))
        assert restored == v0
        rid_restore = run(write_revision(pool, fid, restored, "restore"))
        assert pool._revisions[rid_restore]["source"] == "restore"

        # Integrity: all diff rows in fid still have their parents present
        all_ids = {r["id"] for r in pool._revisions.values()}
        for r in pool._rows_for_file(fid):
            if r["kind"] == "diff" and r["parent_revision_id"] is not None:
                assert r["parent_revision_id"] in all_ids

        # Integrity: ref row in fb can still be reconstructed
        ref_result = run(reconstruct_revision(pool, ref_row["id"]))
        assert ref_result == shared
