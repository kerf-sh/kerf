"""Background scheduler for billing-bucket housekeeping.

Two trivial cron-ish jobs, both idempotent:

1. ``reset_api_token_daily`` — zero out ``api_tokens.spend_today_usd`` and
   bump ``spend_today_date`` to today wherever the date has rolled over.
   Runs every hour (cheap, idempotent — fine if it fires more than once
   per day).

2. ``reset_free_quotas`` — on the 1st of each month, bump
   ``free_tokens_{in,out}_remaining`` back to the default and advance
   ``free_quota_resets_at`` to next month for any user whose reset window
   has passed.

That's the whole scheduler.  No rate-limit tables.  No reconciler.  The
credit balance IS the spend cap.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional


logger = logging.getLogger(__name__)


_DEFAULT_FREE_TOKENS_IN = 100_000
_DEFAULT_FREE_TOKENS_OUT = 20_000


async def reset_api_token_daily(pool) -> int:
    """Reset stale spend_today_* on api_tokens.  Returns rows updated."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE api_tokens
            SET spend_today_usd  = 0,
                spend_today_date = current_date
            WHERE spend_today_date < current_date
            """,
        )
    # asyncpg's execute returns "UPDATE N"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def reset_free_quotas(pool) -> int:
    """Reset free-tier counters where the reset window has passed.

    Returns rows updated.  Advances ``free_quota_resets_at`` to the first
    day of NEXT month so subsequent ticks idempotently no-op until the
    next rollover.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE cloud_user_balances
            SET free_tokens_in_remaining  = $1,
                free_tokens_out_remaining = $2,
                free_quota_resets_at      = date_trunc('month', now()) + interval '1 month'
            WHERE free_quota_resets_at <= now()
            """,
            _DEFAULT_FREE_TOKENS_IN, _DEFAULT_FREE_TOKENS_OUT,
        )
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


class BillingResetWorker:
    """Combined hourly resetter.  Same shape as PricingRefreshWorker."""

    name = "billing_reset"

    def __init__(self, pool, *, interval_seconds: float = 3600.0) -> None:
        self.pool = pool
        self.interval = interval_seconds
        self._shutdown = False

    async def run(self, ctx: Optional[asyncio.TaskGroup] = None) -> None:
        # Tick once at boot too — handles the case where a process restarts
        # right after midnight UTC and the prior tick was missed.
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
        try:
            n_tokens = await reset_api_token_daily(self.pool)
            n_quotas = await reset_free_quotas(self.pool)
            if n_tokens or n_quotas:
                logger.info(
                    "billing_reset tick api_tokens=%d free_quotas=%d",
                    n_tokens, n_quotas,
                )
        except Exception:
            logger.exception("billing_reset tick failed")
