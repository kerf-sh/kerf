"""
git_gc_runner — weekly per-project packfile GC scheduler (T-188).

Entry point: call ``run_once()`` (an async function) from any scheduler that
already holds a DB pool.  It fetches every project that has a git repo record,
runs ``repack_project`` for each concurrently (capped at 2 workers), and logs
the results.

Design notes
------------
The spec considered adding a ``last_repack_at`` column to
``cloud_git_repos`` but clean-baseline rules forbid new ALTER ADD COLUMN
shims.  Instead the runner runs unconditionally on all known projects every
invocation (the caller should only invoke it weekly) — this is safe because
``repack_project`` is idempotent and inexpensive when no loose objects
exist.  If a project's local working copy has not been materialised yet,
``repack_project`` returns ``{"skipped": True, ...}`` with no side effects.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from kerf_cloud.git_gc import repack_project  # noqa: E402

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2


def _fetch_project_ids_sync(pool_factory: Callable) -> list[str]:
    """Synchronous helper for the executor thread: query cloud_git_repos."""
    # This is intentionally simple and does not use asyncpg so it can run
    # inside a ThreadPoolExecutor without an event-loop.
    import asyncio  # noqa: PLC0415
    import asyncpg  # noqa: PLC0415

    async def _query():
        conn = await pool_factory()
        try:
            rows = await conn.fetch("SELECT project_id::text FROM cloud_git_repos")
            return [r["project_id"] for r in rows]
        finally:
            await conn.close()

    return asyncio.run(_query())


async def run_once(pool=None, *, storage=None) -> dict:
    """Run GC for every project in cloud_git_repos.

    Parameters
    ----------
    pool:
        An asyncpg Pool (or anything with an ``acquire`` async context
        manager).  When None, the function will attempt to use
        ``kerf_core.db.connection.get_pool_required``.
    storage:
        Optional storage to pass to ``repack_project``.  Resolved from
        ``get_storage()`` when None.

    Returns
    -------
    dict with keys:
        projects_processed  int
        projects_skipped    int
        projects_failed     int
        results             list[dict]
    """
    if pool is None:
        try:
            from kerf_core.db.connection import get_pool_required  # noqa: PLC0415
            pool = await get_pool_required()
        except Exception as exc:
            logger.error("git_gc_runner: cannot obtain DB pool: %s", exc)
            return {
                "projects_processed": 0,
                "projects_skipped": 0,
                "projects_failed": 1,
                "results": [],
            }

    # Fetch project ids.
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT project_id::text FROM cloud_git_repos")
        project_ids = [r["project_id"] for r in rows]
    except Exception as exc:
        logger.error("git_gc_runner: failed to query cloud_git_repos: %s", exc)
        return {
            "projects_processed": 0,
            "projects_skipped": 0,
            "projects_failed": 1,
            "results": [],
        }

    if not project_ids:
        logger.info("git_gc_runner: no projects found, nothing to do")
        return {
            "projects_processed": 0,
            "projects_skipped": 0,
            "projects_failed": 0,
            "results": [],
        }

    loop = asyncio.get_running_loop()
    results: list[dict] = []
    processed = 0
    skipped = 0
    failed = 0

    # Run repack_project synchronously in a thread pool, capped at 2 workers.
    # Use a semaphore-like approach: gather all futures and match by index.
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        aws = [
            loop.run_in_executor(
                executor,
                lambda pid=pid: repack_project(pid, storage=storage),
            )
            for pid in project_ids
        ]
        gathered = await asyncio.gather(*aws, return_exceptions=True)

    for pid, outcome in zip(project_ids, gathered):
        if isinstance(outcome, BaseException):
            logger.error(
                "git_gc_runner: repack_project failed for project_id=%s: %s",
                pid, outcome,
            )
            results.append({"project_id": pid, "error": str(outcome)})
            failed += 1
        else:
            result: dict = outcome
            result["project_id"] = pid
            results.append(result)
            if result.get("skipped"):
                skipped += 1
            else:
                processed += 1

    logger.info(
        "git_gc_runner: done processed=%d skipped=%d failed=%d",
        processed, skipped, failed,
    )
    return {
        "projects_processed": processed,
        "projects_skipped": skipped,
        "projects_failed": failed,
        "results": results,
    }
