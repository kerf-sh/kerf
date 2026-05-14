"""
kerf_core.revisions — canonical write_revision / reconstruct_revision.

Improvements shipped in Phase 4:
  - Real unified diffs for 'diff' rows (not duplicate full content).
  - SHA-256 dedup: skip inserting when hash matches latest base or diff.
  - Safe cap-pruning: never delete a row that is a parent_revision_id for
    a younger row (would break diff-chain reconstruction).
  - gzip stored as raw bytea via content_codec='gzip' (new rows only);
    legacy base64-text rows (content_codec='plain') still decode correctly.

The 'diff' rows store a unified-diff of the *decoded* parent content vs
the new content. Reconstruction walks up to the nearest base, then applies
diffs in order. Chain length is capped at REBASE_THRESHOLD — once that
many diffs accumulate since the last base, the next write is promoted to
a new base row.
"""

from __future__ import annotations

import difflib
import gzip
import hashlib
import re
import uuid
from typing import Any

# Every REBASE_THRESHOLD diffs since the last base triggers a new base row.
REBASE_THRESHOLD = 20

# Only gzip-compress content above this byte threshold.
GZIP_THRESHOLD = 16_384  # 16 KiB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(content: str) -> bytes:
    return hashlib.sha256(content.encode()).digest()


def _compress(content: str) -> bytes:
    """Return raw gzip bytes."""
    return gzip.compress(content.encode(), compresslevel=6)


def _decompress_row(row: Any) -> str:
    """
    Decode content from a DB row dict / asyncpg Record.
    Handles both new (content_codec='gzip', raw bytea) and legacy
    (content_codec='plain', base64-encoded string in content_gz field) rows.
    """
    codec = row.get("content_codec", "plain") if hasattr(row, "get") else (row["content_codec"] if "content_codec" in row.keys() else "plain")
    gz = row["content_gz"]
    plain = row["content"]

    if codec == "gzip" and gz:
        # New path: raw bytea
        raw = bytes(gz) if not isinstance(gz, bytes) else gz
        return gzip.decompress(raw).decode()

    if codec == "plain" and gz:
        # Legacy path: content_gz is a base64-encoded string
        import base64
        if isinstance(gz, (bytes, memoryview)):
            b64 = bytes(gz)
        else:
            b64 = gz.encode() if isinstance(gz, str) else gz
        try:
            raw = base64.b64decode(b64)
            return gzip.decompress(raw).decode()
        except Exception:
            pass

    # Fallback: plain content column
    return plain or ""


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def compute_unified_diff(old: str, new: str) -> str:
    """Return a unified-diff string between old and new (line-oriented)."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="a", tofile="b")
    return "".join(diff)


def apply_unified_diff(base: str, patch: str) -> str:
    """
    Apply a unified diff produced by compute_unified_diff to base text.
    Returns the patched string.
    """
    if not patch.strip():
        return base

    base_lines = base.splitlines(keepends=True)
    patch_lines = patch.splitlines(keepends=True)
    result: list[str] = []
    base_idx = 0  # 0-based index into base_lines

    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue
        if line.startswith("@@"):
            m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                i += 1
                continue
            old_start = int(m.group(1)) - 1  # convert to 0-based
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            # Copy unchanged base lines before this hunk
            result.extend(base_lines[base_idx:old_start])
            base_idx = old_start
            i += 1
            # Process the hunk
            while i < len(patch_lines):
                hunk_line = patch_lines[i]
                if hunk_line.startswith("@@") or hunk_line.startswith("---") or hunk_line.startswith("+++"):
                    break
                if hunk_line.startswith("-"):
                    # Remove from base
                    base_idx += 1
                elif hunk_line.startswith("+"):
                    # Add new line
                    result.append(hunk_line[1:])
                else:
                    # Context line — copy from base
                    if base_idx < len(base_lines):
                        result.append(base_lines[base_idx])
                    base_idx += 1
                i += 1
            continue
        i += 1

    # Append remaining base lines after last hunk
    result.extend(base_lines[base_idx:])
    return "".join(result)


# ---------------------------------------------------------------------------
# Chain reconstruction
# ---------------------------------------------------------------------------

async def reconstruct_revision(pool: Any, rev_id: uuid.UUID) -> str:
    """
    Walk the parent_revision_id chain up to the nearest 'base' row, then
    apply each 'diff' in order to reconstruct the content at rev_id.
    """
    row = await pool.fetchrow(
        "SELECT id, kind, parent_revision_id, content_gz, content, content_codec "
        "FROM file_revisions WHERE id = $1",
        rev_id,
    )
    if not row:
        return ""

    chain: list[Any] = [row]

    while chain[0]["kind"] == "diff":
        pid = chain[0]["parent_revision_id"]
        if pid is None:
            break
        prow = await pool.fetchrow(
            "SELECT id, kind, parent_revision_id, content_gz, content, content_codec "
            "FROM file_revisions WHERE id = $1",
            pid,
        )
        if not prow:
            break
        chain.insert(0, prow)

    current = _decompress_row(chain[0])

    for node in chain[1:]:
        patch = _decompress_row(node)
        current = apply_unified_diff(current, patch)

    return current


# ---------------------------------------------------------------------------
# Core write path
# ---------------------------------------------------------------------------

async def write_revision(
    pool: Any,
    file_id: str | uuid.UUID,
    content: str,
    source: str,
    user_id: uuid.UUID | None = None,
    cap: int = 200,
) -> uuid.UUID:
    """
    Record a new revision for file_id.

    Algorithm:
      1. SHA-256 dedup: if the latest revision for this file has the same
         hash, skip the insert and return its id.
      2. Count diff rows since the last base. If >= REBASE_THRESHOLD, write
         a new 'base' row; otherwise write a 'diff' row containing a unified
         patch against the latest revision.
      3. Base rows compress their full content. Diff rows compress the patch.
         Both use content_codec='gzip' (raw bytea, no base64 wrapping).
      4. Prune old revisions: delete the oldest rows beyond cap, but never
         delete a row that is referenced as parent_revision_id (would corrupt
         a diff chain).
    """
    fid = uuid.UUID(str(file_id)) if not isinstance(file_id, uuid.UUID) else file_id
    new_hash = _sha256(content)
    preview = content[:200]

    # --- 1. SHA-256 dedup ---
    latest = await pool.fetchrow(
        "SELECT id, kind, content_sha256, parent_revision_id "
        "FROM file_revisions WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
        fid,
    )
    if latest is not None and latest["content_sha256"] == new_hash:
        return latest["id"]

    # --- 2. Decide base vs diff ---
    if latest is None or latest["kind"] == "base":
        diffs_since_base = 0
    else:
        diffs_since_base = await pool.fetchval(
            """
            SELECT COUNT(*) FROM file_revisions
            WHERE file_id = $1
              AND kind = 'diff'
              AND created_at > COALESCE(
                  (SELECT MAX(created_at) FROM file_revisions
                   WHERE file_id = $1 AND kind = 'base'),
                  'epoch'::timestamptz
              )
            """,
            fid,
        )

    make_base = latest is None or diffs_since_base >= REBASE_THRESHOLD

    new_id = uuid.uuid4()

    if make_base:
        payload = _compress(content)
        await pool.execute(
            """
            INSERT INTO file_revisions
              (id, file_id, content, content_gz, content_codec, kind,
               source, user_id, content_sha256, content_preview)
            VALUES ($1, $2, '', $3, 'gzip', 'base', $4, $5, $6, $7)
            """,
            new_id, fid, payload, source, user_id, new_hash, preview,
        )
    else:
        # Reconstruct parent content to compute an actual diff
        parent_content = await reconstruct_revision(pool, latest["id"])
        patch = compute_unified_diff(parent_content, content)
        payload = _compress(patch)
        await pool.execute(
            """
            INSERT INTO file_revisions
              (id, file_id, content, content_gz, content_codec, kind,
               parent_revision_id, source, user_id, content_sha256, content_preview)
            VALUES ($1, $2, '', $3, 'gzip', 'diff', $4, $5, $6, $7, $8)
            """,
            new_id, fid, payload, latest["id"], source, user_id, new_hash, preview,
        )

    # --- 4. Safe cap-pruning ---
    # Find the oldest revision id beyond the cap, then delete it only if
    # nothing younger references it as a parent (i.e. it's not mid-chain).
    await pool.execute(
        """
        DELETE FROM file_revisions
        WHERE file_id = $1
          AND id NOT IN (
              -- protect: rows referenced by younger diffs
              SELECT parent_revision_id FROM file_revisions
              WHERE file_id = $1 AND parent_revision_id IS NOT NULL
          )
          AND id NOT IN (
              -- protect: the N most recent rows
              SELECT id FROM file_revisions
              WHERE file_id = $1
              ORDER BY created_at DESC
              LIMIT $2
          )
        """,
        fid, cap,
    )

    return new_id
