"""
kerf_core.workers.compaction_worker — background revision-chain compaction.

Polls ``file_revisions`` for chains that have accumulated more than
COMPACTION_THRESHOLD diff rows without a base.  For each such chain the
worker:

1. Reconstructs the full content at the chain tip.
2. Writes a new ``base`` row (gzip-compressed, SHA-256 hash populated).
3. Deletes the now-redundant intermediate diff rows — but only rows that
   are not referenced as ``parent_revision_id`` by any other row and are
   not themselves ``base`` rows (cross-file ``ref`` targets are also
   protected; see Part 2 logic in revisions.py).

This worker is **cloud-tier-only**:
    cloud_enabled=True  AND  local_mode=False

OSS local-install users have small revision sets (revision cap default
200) that never need background compaction.  Gating is the caller's
responsibility; the worker itself will raise ``RuntimeError`` at
``__init__`` if instantiated in local mode.

Schedule / cadence: poll every ``poll_interval`` seconds (default 300 s,
i.e. every 5 minutes).  One chain is compacted per ``run_one`` call;
subsequent iterations drain the backlog naturally.

Idempotent: if a chain is already short (≤ COMPACTION_THRESHOLD diffs)
it is skipped.  Re-running on an already-compacted chain is harmless.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from kerf_core.revisions import (
    REBASE_THRESHOLD,
    _compress,
    _sha256,
    reconstruct_revision,
)

logger = logging.getLogger(__name__)

# Number of diff rows since the last base that triggers compaction.
# Default matches the write-time REBASE_THRESHOLD so newly written chains
# are already compact; the worker is a safety net for very old chains
# written before Phase 4, or chains that somehow accumulated extra diffs.
COMPACTION_THRESHOLD = REBASE_THRESHOLD * 2  # 40 diffs → compact


class CompactionWorker:
    """
    Background worker that lazily re-compacts long revision chains.

    Instantiate via ``CompactionWorker(pool, cloud_enabled, local_mode)``
    and call ``run(ctx)`` from an ``asyncio.TaskGroup``.
    """

    name = "compaction"

    def __init__(
        self,
        pool: Any,
        cloud_enabled: bool = True,
        local_mode: bool = False,
        poll_interval: float = 300.0,
        error_delay: float = 10.0,
        threshold: int = COMPACTION_THRESHOLD,
    ) -> None:
        if not cloud_enabled or local_mode:
            raise RuntimeError(
                "CompactionWorker must not be started in local_mode or "
                "when cloud_enabled=False"
            )
        self.pool = pool
        self.poll_interval = poll_interval
        self.error_delay = error_delay
        self.threshold = threshold
        self._shutdown = False

    # ------------------------------------------------------------------ lifecycle

    def stop(self) -> None:
        self._shutdown = True

    async def run(self, ctx: asyncio.TaskGroup) -> None:
        task = ctx.create_task(self._loop())
        try:
            await task
        except asyncio.CancelledError:
            self._shutdown = True
            logger.info("compaction: worker shutdown")

    # ------------------------------------------------------------------ loop

    async def _loop(self) -> None:
        while not self._shutdown:
            try:
                ran = await self.run_one()
                if not ran:
                    # No work found — sleep until next poll interval.
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("compaction: run_one error, backing off")
                await asyncio.sleep(self.error_delay)

    # ------------------------------------------------------------------ core

    async def run_one(self) -> bool:
        """
        Find one file_id whose chain is too long and compact it.

        Returns True if a chain was processed (caller should loop), False
        if no work is available (caller should sleep).
        """
        async with self.pool.acquire() as conn:
            # Find a file that has more than ``threshold`` diff rows since
            # its most recent base.  We order by diff_count DESC so the
            # worst chains are handled first.
            row = await conn.fetchrow(
                """
                SELECT fr.file_id,
                       COUNT(*) FILTER (WHERE fr.kind = 'diff') AS diff_count,
                       MAX(fr.id) FILTER (WHERE fr.kind = 'diff') AS tip_id
                FROM file_revisions fr
                WHERE fr.kind IN ('base', 'diff')
                  AND fr.created_at > COALESCE(
                      (SELECT MAX(b.created_at)
                       FROM file_revisions b
                       WHERE b.file_id = fr.file_id AND b.kind = 'base'),
                      'epoch'::timestamptz
                  )
                GROUP BY fr.file_id
                HAVING COUNT(*) FILTER (WHERE fr.kind = 'diff') > $1
                ORDER BY diff_count DESC
                LIMIT 1
                """,
                self.threshold,
            )

        if row is None:
            return False

        file_id: uuid.UUID = row["file_id"]
        tip_id: uuid.UUID = row["tip_id"]
        diff_count: int = row["diff_count"]

        logger.info(
            "compaction: compacting file_id=%s diff_count=%d tip_id=%s",
            file_id,
            diff_count,
            tip_id,
        )

        try:
            await self._compact_chain(file_id, tip_id)
        except Exception:
            logger.exception(
                "compaction: failed to compact file_id=%s", file_id
            )
            # Don't re-raise — log and continue so other files are processed.

        return True

    # ------------------------------------------------------------------ helpers

    async def _compact_chain(
        self, file_id: uuid.UUID, tip_id: uuid.UUID
    ) -> None:
        """
        Reconstruct content at ``tip_id``, write a new base, delete the
        now-redundant intermediate diff rows for this file.
        """
        # Step 1: reconstruct full content at the tip.
        content = await reconstruct_revision(self.pool, tip_id)
        if not content:
            logger.warning(
                "compaction: empty content at tip_id=%s, skipping", tip_id
            )
            return

        new_hash = _sha256(content)
        preview = content[:200]
        new_id = uuid.uuid4()
        payload = _compress(content)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Step 2: find the tip row to get source/user_id metadata.
                tip_row = await conn.fetchrow(
                    "SELECT source, user_id FROM file_revisions WHERE id = $1",
                    tip_id,
                )
                source = tip_row["source"] if tip_row else "compaction"
                user_id: Optional[uuid.UUID] = (
                    tip_row["user_id"] if tip_row else None
                )

                # Step 3: insert the new compacted base row.
                await conn.execute(
                    """
                    INSERT INTO file_revisions
                      (id, file_id, content, content_gz, content_codec, kind,
                       source, user_id, content_sha256, content_preview,
                       parent_revision_id)
                    VALUES ($1, $2, '', $3, 'gzip', 'base', $4, $5, $6, $7, $8)
                    """,
                    new_id,
                    file_id,
                    payload,
                    source,
                    user_id,
                    new_hash,
                    preview,
                    tip_id,  # parent_revision_id = old tip, preserves ordering
                )

                # Step 4: delete intermediate diff rows that are no longer
                # needed.  Safety rules:
                #   - Never delete rows referenced as parent_revision_id by
                #     any other row (would break live diff chains).
                #   - Never delete 'base' rows (could break ref rows).
                #   - Never delete 'ref' rows (cross-file dedup pointers).
                #   - Only delete 'diff' rows for this file.
                deleted_rows = await conn.fetch(
                    """
                    WITH protected AS (
                        SELECT parent_revision_id AS id
                        FROM file_revisions
                        WHERE parent_revision_id IS NOT NULL
                    ),
                    candidates AS (
                        SELECT id FROM file_revisions
                        WHERE file_id = $1
                          AND kind = 'diff'
                          AND id != $2
                          AND id NOT IN (SELECT id FROM protected)
                        ORDER BY created_at ASC
                    )
                    DELETE FROM file_revisions
                    WHERE id IN (SELECT id FROM candidates)
                    RETURNING id
                    """,
                    file_id,
                    tip_id,  # protect the old tip (now pointed to by new base)
                )
                deleted_count = len(deleted_rows) if deleted_rows else 0

        logger.info(
            "compaction: file_id=%s new_base=%s deleted_diffs=%d",
            file_id,
            new_id,
            deleted_count,
        )
