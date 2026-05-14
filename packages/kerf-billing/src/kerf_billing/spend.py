"""Atomic ``usage_events`` insertion + balance/quota deduction per bucket.

Each ``commit_spend`` call wraps both halves in a single SQL transaction
so token usage and balance/quota deduction can't drift.

The four paths:

- ``KerfFree``  → record usd_cost = COGS, payer='kerf_free', decrement
                  free_tokens_{in,out}_remaining.
- ``KerfPaid``  → record usd_cost = COGS * markup, payer='kerf_paid',
                  decrement credits_usd via cloud_debit_balance().  Also
                  increments api_tokens.spend_today_usd; if that exceeds
                  the daily cap, raise ``ApiTokenDailyCapExceeded`` AFTER
                  committing the usage row (so we never under-bill — the
                  request already happened).
- ``Byo``       → record usd_cost = 0, payer='byo_<provider>', no balance
                  change.
- ``InsufficientCredits`` → never reaches commit_spend; the chat handler
                            returns 402 before calling here.

The caller does the bucket selection FIRST (via ``buckets.pick_bucket``),
THEN runs the LLM, THEN calls ``commit_spend`` with the actual token
counts (which it now knows from the provider response).
"""
from __future__ import annotations

import logging
from typing import Optional

from kerf_billing.buckets import Bucket, Byo, KerfFree, KerfPaid


logger = logging.getLogger(__name__)


class ApiTokenDailyCapExceeded(Exception):
    """The API token's daily spend cap was hit by this request.

    Raised AFTER the usage row is recorded so the next request fails
    cleanly (and we never under-bill the already-served request).
    """
    def __init__(self, token_id: str, cap_usd: float, spent_usd: float):
        super().__init__(
            f"api_token {token_id} exceeded daily cap ${cap_usd:.2f} "
            f"(spend_today=${spent_usd:.4f})"
        )
        self.token_id = token_id
        self.cap_usd = cap_usd
        self.spent_usd = spent_usd


async def commit_spend(
    pool,
    *,
    bucket: Bucket,
    user_id: str,
    project_id: Optional[str],
    model: str,
    input_tokens: int,
    output_tokens: int,
    cogs_usd: float,
    billed_usd: float,
    api_token_id: Optional[str] = None,
) -> None:
    """Write the usage_events row + the bucket's side-effect in one txn.

    ``cogs_usd`` is provider-actual COGS (no markup).
    ``billed_usd`` is what we charged the user — equals cogs_usd*1.20 for
    KerfPaid, equals cogs_usd for KerfFree (recorded but not deducted from
    a money balance), equals 0 for Byo.

    Raises ``ApiTokenDailyCapExceeded`` if a kerf-sdk API token used the
    paid path and exceeded its daily cap.  Raised AFTER the row+balance
    update so the already-served request still gets billed.
    """
    if isinstance(bucket, KerfFree):
        await _commit_free(
            pool, user_id, project_id, model,
            input_tokens, output_tokens, cogs_usd,
        )
        return

    if isinstance(bucket, Byo):
        await _commit_byo(
            pool, user_id, project_id, model,
            input_tokens, output_tokens, bucket.provider,
        )
        return

    if isinstance(bucket, KerfPaid):
        await _commit_paid(
            pool, user_id, project_id, model,
            input_tokens, output_tokens, billed_usd,
            api_token_id=api_token_id,
        )
        return

    # InsufficientCredits should never reach here — calling code is wrong.
    raise ValueError(f"commit_spend: unexpected bucket {bucket!r}")


# ── kerf_free path ──────────────────────────────────────────────────────────
async def _commit_free(
    pool, user_id, project_id, model,
    input_tokens, output_tokens, cogs_usd,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO usage_events
                    (user_id, project_id, kind, model,
                     input_tokens, output_tokens, usd_cost, payer)
                VALUES ($1, $2, 'token', $3, $4, $5, $6, 'kerf_free')
                """,
                user_id, project_id, model,
                input_tokens, output_tokens, cogs_usd,
            )
            # GREATEST clamps negative remaining (in case the LLM blew past
            # the estimate) so the column never goes below zero.
            await conn.execute(
                """
                UPDATE cloud_user_balances
                SET free_tokens_in_remaining  = GREATEST(0, free_tokens_in_remaining  - $2),
                    free_tokens_out_remaining = GREATEST(0, free_tokens_out_remaining - $3)
                WHERE user_id = $1
                """,
                user_id, input_tokens, output_tokens,
            )


# ── byo_<provider> path ─────────────────────────────────────────────────────
async def _commit_byo(
    pool, user_id, project_id, model,
    input_tokens, output_tokens, provider,
) -> None:
    payer = f"byo_{provider}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_events
                (user_id, project_id, kind, model,
                 input_tokens, output_tokens, usd_cost, payer)
            VALUES ($1, $2, 'token', $3, $4, $5, 0, $6)
            """,
            user_id, project_id, model,
            input_tokens, output_tokens, payer,
        )


# ── kerf_paid path ──────────────────────────────────────────────────────────
async def _commit_paid(
    pool, user_id, project_id, model,
    input_tokens, output_tokens, billed_usd,
    *, api_token_id: Optional[str] = None,
) -> None:
    """Insert usage_events + debit balance + bump api_tokens daily counter,
    all in one transaction.  If the daily cap is exceeded, the row is still
    committed (so we don't under-bill the served request) but we raise
    ``ApiTokenDailyCapExceeded`` so the NEXT request fails."""
    cap_exceeded: Optional[ApiTokenDailyCapExceeded] = None

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO usage_events
                    (user_id, project_id, kind, model,
                     input_tokens, output_tokens, usd_cost, payer)
                VALUES ($1, $2, 'token', $3, $4, $5, $6, 'kerf_paid')
                """,
                user_id, project_id, model,
                input_tokens, output_tokens, billed_usd,
            )

            # Decrement balance directly — same effect as the stored
            # cloud_debit_balance() function in kerf-billing/handlers.py,
            # and works even on a fresh OSS DB that hasn't run that
            # bootstrap.  ON CONFLICT-style upsert handles the case where
            # no balance row exists yet (registers the user at -billed).
            await conn.execute(
                """
                INSERT INTO cloud_user_balances (user_id, credits_usd)
                VALUES ($1, -$2)
                ON CONFLICT (user_id) DO UPDATE
                SET credits_usd = cloud_user_balances.credits_usd - $2
                """,
                user_id, billed_usd,
            )

            # API-token daily cap: bookkeeping + over-cap detection.
            if api_token_id:
                cap_row = await conn.fetchrow(
                    """
                    UPDATE api_tokens
                    SET spend_today_date = CASE
                            WHEN spend_today_date < current_date THEN current_date
                            ELSE spend_today_date
                        END,
                        spend_today_usd = CASE
                            WHEN spend_today_date < current_date THEN $2
                            ELSE spend_today_usd + $2
                        END
                    WHERE id = $1
                    RETURNING max_spend_per_day_usd, spend_today_usd
                    """,
                    api_token_id, billed_usd,
                )
                if cap_row:
                    cap = float(cap_row["max_spend_per_day_usd"])
                    spent = float(cap_row["spend_today_usd"])
                    if spent > cap:
                        cap_exceeded = ApiTokenDailyCapExceeded(
                            api_token_id, cap, spent,
                        )

    if cap_exceeded is not None:
        raise cap_exceeded
