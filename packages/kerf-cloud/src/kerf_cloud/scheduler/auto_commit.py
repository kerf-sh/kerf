"""Auto-commit scheduler — T-185.

A 60-second poller that iterates over every active workspace and calls
``auto_commit_if_idle`` to squash unsaved L2 edits into an autosave commit.

Usage (standalone, for testing):

    python3 -m kerf_cloud.scheduler.auto_commit

Or integrated into the server startup as an asyncio background task:

    from kerf_cloud.scheduler.auto_commit import start_auto_commit_loop
    asyncio.create_task(start_auto_commit_loop(pool, storage))
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def _tick(pool, storage) -> None:
    """One poll cycle: iterate active workspaces and auto-commit idle ones."""
    try:
        async with pool.acquire() as conn:
            workspace_ids: list[uuid.UUID] = await conn.fetch(
                "SELECT id FROM workspaces ORDER BY id"
            )
    except Exception:
        logger.exception("auto_commit: failed to fetch workspaces")
        return

    from kerf_core.storage.materialize import auto_commit_if_idle

    for row in workspace_ids:
        ws_id: uuid.UUID = row["id"]
        try:
            async with pool.acquire() as conn:
                result = await auto_commit_if_idle(
                    ws_id,
                    db_conn=conn,
                    storage=storage,
                )
            if result is not None:
                logger.info(
                    "auto_commit: workspace=%s committed sha=%s",
                    ws_id,
                    result.commit_sha,
                )
        except Exception:
            logger.exception("auto_commit: error for workspace=%s", ws_id)


async def start_auto_commit_loop(pool, storage, *, interval: int = POLL_INTERVAL_SECONDS) -> None:
    """Run the auto-commit poller forever.

    Designed to be run as an asyncio background task.  Catches all exceptions
    internally so a transient DB hiccup never crashes the server.

    Args:
        pool:     An ``asyncpg`` connection pool.
        storage:  The active ``Storage`` backend.
        interval: Poll interval in seconds (default 60).
    """
    logger.info("auto_commit: poller started (interval=%ds)", interval)
    while True:
        await _tick(pool, storage)
        await asyncio.sleep(interval)
