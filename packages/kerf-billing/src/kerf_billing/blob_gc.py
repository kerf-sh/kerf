"""Large-object GC sweep worker (T-136).

Finds blob_objects rows that are:
  1. Zero live refs (no blob_refs row).
  2. Git-unreachable per the registered GitReachabilityOracle.
  3. Past the 72-hour grace window (both created_at and last_unref_at).

Then deletes the backing storage object and the blob_objects row.

Safety invariants
-----------------
* Oracle absent → treat every oid as reachable → skip all deletes.
* dry_run=True (default) → never issue a storage delete or DB row delete.
* MVCC re-check inside a SELECT FOR UPDATE transaction guards against a
  concurrent add_ref between the candidate scan and the delete.

The worker shape (name / __init__ / run / stop / _tick) mirrors
PricingRefreshWorker and BillingResetWorker exactly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable


logger = logging.getLogger(__name__)

_SIX_HOURS = 6 * 60 * 60
_BATCH = 500


# ---------------------------------------------------------------------------
# GitReachabilityOracle — interface only; no implementation shipped here.
# ---------------------------------------------------------------------------

@runtime_checkable
class GitReachabilityOracle(Protocol):
    """Conservative over-approximation of blob reachability across all repos.

    Implementations MUST be safe:
      - False negatives (unreachable → reachable) are FORBIDDEN — they cause data loss.
      - False positives (reachable → unreachable) are safe — they delay GC only.

    Until a concrete implementation is registered via
    ``BlobGCWorker.set_oracle()``, the worker treats every oid as reachable
    and logs ``blob_gc_tick git_oracle_absent skip_all_oids=True``.
    """

    def is_oid_reachable(self, oid: str) -> bool:
        """Return True if any project git repo references this oid.

        An oid is reachable if any commit, in any branch / tag / stash of any
        project repository, has a tree that contains a pointer blob encoding:

            kerf-ptr v1
            sha256: <oid>

        Must be synchronous and conservative (over-approximate).
        """
        ...

    def last_unreachable_at(self, oid: str) -> Optional[datetime]:
        """Return when the oid became git-unreachable, or None.

        None means the oid is currently reachable or the implementation cannot
        determine when it became unreachable.  Returning None is always safe.
        """
        ...


# ---------------------------------------------------------------------------
# BlobGCWorker
# ---------------------------------------------------------------------------

class BlobGCWorker:
    """Idempotent GC sweep — timer worker, same shape as PricingRefreshWorker."""

    name = "blob_gc"

    def __init__(
        self,
        pool,
        storage,
        *,
        interval_seconds: float = _SIX_HOURS,
        dry_run: bool = True,
    ) -> None:
        self.pool = pool
        self.storage = storage
        self.interval = interval_seconds
        self.dry_run = dry_run
        self._shutdown = False
        self._oracle: Optional[GitReachabilityOracle] = None

    def set_oracle(self, oracle: GitReachabilityOracle) -> None:
        """Register the git reachability oracle.  Call before the first tick."""
        self._oracle = oracle

    async def run(self, ctx=None) -> None:
        # One pass at boot so a fresh process GCs immediately.
        await self._tick()
        while not self._shutdown:
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            if self._shutdown:
                break
            await self._tick()

    def stop(self) -> None:
        self._shutdown = True

    async def _tick(self) -> None:
        t0 = time.monotonic()
        metrics = dict(
            blob_gc_candidates=0,
            blob_gc_skipped_live_ref=0,
            blob_gc_skipped_git_reachable=0,
            blob_gc_skipped_oracle_absent=0,
            blob_gc_skipped_dry_run=0,
            blob_gc_deleted_count=0,
            blob_gc_deleted_bytes=0,
            blob_gc_errors=0,
        )

        oracle = self._oracle
        oracle_absent = oracle is None

        if oracle_absent:
            logger.info("blob_gc_tick git_oracle_absent skip_all_oids=True")

        # Track oids already seen this tick so skipped rows (reachable /
        # oracle-absent / dry-run) are excluded from subsequent batches and
        # the loop always terminates.
        seen: set[str] = set()

        try:
            while True:
                candidates = await self._fetch_candidates(exclude=seen)
                if not candidates:
                    break

                metrics["blob_gc_candidates"] += len(candidates)

                for row in candidates:
                    oid = row["oid"]
                    size = row["size_bytes"]
                    seen.add(oid)

                    if oracle_absent:
                        metrics["blob_gc_skipped_oracle_absent"] += 1
                        logger.debug(
                            "blob_gc skip oid=%s reason=oracle_absent", oid
                        )
                        continue

                    if oracle.is_oid_reachable(oid):
                        metrics["blob_gc_skipped_git_reachable"] += 1
                        logger.debug(
                            "blob_gc skip oid=%s reason=git_reachable", oid
                        )
                        continue

                    if self.dry_run:
                        metrics["blob_gc_skipped_dry_run"] += 1
                        logger.debug(
                            "blob_gc skip oid=%s reason=dry_run size=%d",
                            oid, size,
                        )
                        continue

                    skipped, deleted = await self._delete_one(oid, size, metrics)
                    if deleted:
                        metrics["blob_gc_deleted_count"] += 1
                        metrics["blob_gc_deleted_bytes"] += size
                    elif skipped:
                        metrics["blob_gc_skipped_live_ref"] += 1

        except Exception:
            metrics["blob_gc_errors"] += 1
            logger.exception("blob_gc_tick failed unexpectedly")

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        metrics["blob_gc_tick_duration_ms"] = elapsed_ms
        logger.info("blob_gc_tick %s", " ".join(f"{k}={v}" for k, v in metrics.items()))

    async def _fetch_candidates(self, exclude: set[str] | None = None) -> list:
        """Return up to _BATCH zero-ref oids past the 72-hour grace window.

        ``exclude`` is the set of oids already processed this tick (skipped or
        deleted).  Passing them back prevents the query from returning the same
        skipped oids on each iteration and looping forever.
        """
        async with self.pool.acquire() as conn:
            if exclude:
                # asyncpg supports ANY($2::text[]) for exclusion lists.
                return await conn.fetch(
                    """
                    SELECT o.oid, o.size_bytes
                    FROM   blob_objects o
                    WHERE  NOT EXISTS (SELECT 1 FROM blob_refs r WHERE r.oid = o.oid)
                      AND  o.last_unref_at IS NOT NULL
                      AND  o.last_unref_at  < now() - interval '72 hours'
                      AND  o.created_at     < now() - interval '72 hours'
                      AND  o.oid != ALL($2::text[])
                    LIMIT  $1
                    """,
                    _BATCH,
                    list(exclude),
                )
            return await conn.fetch(
                """
                SELECT o.oid, o.size_bytes
                FROM   blob_objects o
                WHERE  NOT EXISTS (SELECT 1 FROM blob_refs r WHERE r.oid = o.oid)
                  AND  o.last_unref_at IS NOT NULL
                  AND  o.last_unref_at  < now() - interval '72 hours'
                  AND  o.created_at     < now() - interval '72 hours'
                LIMIT  $1
                """,
                _BATCH,
            )

    async def _delete_one(
        self, oid: str, size: int, metrics: dict
    ) -> tuple[bool, bool]:
        """Attempt to delete a single oid.

        Returns (skipped_live_ref, deleted).  Any error is logged and counted
        in metrics["blob_gc_errors"] but never re-raised so the sweep continues.
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Re-check inside the transaction with a row lock.
                    row = await conn.fetchrow(
                        """
                        SELECT o.oid, o.size_bytes,
                               o.last_unref_at, o.created_at
                        FROM   blob_objects o
                        WHERE  o.oid = $1
                        FOR UPDATE
                        """,
                        oid,
                    )
                    if row is None:
                        # Already deleted by a concurrent tick — idempotent.
                        return False, False

                    live_ref = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM blob_refs WHERE oid = $1)",
                        oid,
                    )
                    if live_ref:
                        return True, False

                    # Grace-window re-check (clock drift / race).
                    now = datetime.now(tz=timezone.utc)
                    from datetime import timedelta
                    grace = timedelta(hours=72)
                    if row["last_unref_at"] is None or (now - row["last_unref_at"]) < grace:
                        return True, False
                    if (now - row["created_at"]) < grace:
                        return True, False

                    # Delete the storage object first (idempotent: S3 delete
                    # is a no-op if the key is already gone).
                    from kerf_core.storage.materialize import blob_storage_key
                    key = blob_storage_key(oid)
                    try:
                        await self.storage.delete(key)
                    except Exception:
                        metrics["blob_gc_errors"] += 1
                        logger.exception(
                            "blob_gc storage delete failed oid=%s key=%s", oid, key
                        )
                        return False, False

                    # Remove the ledger row (blob_refs cascade-deletes, but
                    # the refcount is already 0 at this point).
                    await conn.execute(
                        "DELETE FROM blob_objects WHERE oid = $1", oid
                    )

            logger.debug(
                "blob_gc deleted oid=%s size=%d key=%s", oid, size, key
            )
            return False, True

        except Exception:
            metrics["blob_gc_errors"] += 1
            logger.exception("blob_gc _delete_one failed oid=%s", oid)
            return False, False


# ---------------------------------------------------------------------------
# BLOB_GC_DRY_RUN environment helper (used by the plugin registration).
# ---------------------------------------------------------------------------

def _dry_run_from_env() -> bool:
    """Parse BLOB_GC_DRY_RUN.  Defaults True (safe).

    PRODUCTION NOTE: without BLOB_GC_DRY_RUN=false blobs are never physically
    deleted from Tigris and storage bytes are never reclaimed — storage billing
    (R3) will accrue but the GC won't clean up.  See 'Required production env
    vars' in deployment/koyeb.md for the mandatory env var.
    """
    val = os.getenv("BLOB_GC_DRY_RUN", "true").strip().lower()
    return val not in ("false", "0", "no")
