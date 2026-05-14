"""
BaseWorker — minimal async worker base class for kerf-tess.

Mirrors backend/workers/base.py so that kerf-tess is self-contained and does
not depend on the backend package at runtime.  The canonical copy lives in
backend/workers/base.py; keep these in sync when changing the interface.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    def __init__(
        self,
        name: str,
        pool,
        poll_interval: float = 5.0,
        error_delay: float = 2.0,
    ):
        self.name = name
        self.pool = pool
        self.poll_interval = poll_interval
        self.error_delay = error_delay
        self._shutdown = False

    async def run(self, ctx: asyncio.TaskGroup):
        task = ctx.create_task(self._loop())
        try:
            await task
        except asyncio.CancelledError:
            self._shutdown = True
            logger.info("%s: worker shutdown", self.name)

    def stop(self):
        self._shutdown = True

    async def _loop(self):
        while not self._shutdown:
            try:
                ran = await self.run_one()
                if not ran:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("%s: runOne error", self.name)
                await asyncio.sleep(self.error_delay)

    @abstractmethod
    async def run_one(self) -> bool:
        pass

    async def mark_error(self, table: str, job_id: str, error: str):
        try:
            await self.pool.execute(
                f"""
                UPDATE {table}
                SET status = 'error', error = $2, finished_at = now()
                WHERE id = $1
                """,
                job_id,
                error[:800] if len(error) > 800 else error,
            )
        except Exception:
            logger.exception("%s: mark error failed (job=%s)", self.name, job_id)

    def truncate_error(self, err: str, max_len: int = 800) -> str:
        if len(err) <= max_len:
            return err
        return err[:max_len] + "..."
