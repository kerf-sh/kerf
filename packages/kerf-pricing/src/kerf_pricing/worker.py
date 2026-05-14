"""PricingRefreshWorker — runs ``refresh_model_prices`` once at boot, then daily.

The cadence is intentionally lax — LiteLLM's price file only moves on
provider price changes (rare).  We refresh once a day at 00:00ish UTC
purely for freshness/monitoring; a missed run isn't an outage.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from kerf_pricing.refresh import refresh_model_prices


logger = logging.getLogger(__name__)


_DAILY_SECONDS = 24 * 60 * 60


class PricingRefreshWorker:
    """Background worker — does NOT inherit BaseWorker because BaseWorker is
    job-table-driven, and this is a pure timer.  Implements the same
    ``run(ctx)`` / ``stop()`` shape the runner expects."""

    name = "pricing_refresh"

    def __init__(self, pool, *, interval_seconds: float = _DAILY_SECONDS) -> None:
        self.pool = pool
        self.interval = interval_seconds
        self._shutdown = False

    async def run(self, ctx: Optional[asyncio.TaskGroup] = None) -> None:
        # One pass at boot so a fresh DB has prices immediately.
        await self._tick(initial=True)
        while not self._shutdown:
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            if self._shutdown:
                break
            await self._tick(initial=False)

    def stop(self) -> None:
        self._shutdown = True

    async def _tick(self, *, initial: bool) -> None:
        try:
            n = await refresh_model_prices(self.pool)
            logger.info(
                "pricing_refresh tick initial=%s upserted=%d", initial, n,
            )
        except Exception:
            logger.exception("pricing_refresh tick failed (initial=%s)", initial)
