"""Three-bucket billing model.

Every chat token is paid for by EXACTLY ONE of:

- ``kerf_free``  — free-tier monthly quota.  Cheap-tier models only.  We
  still record COGS in usage_events so we can see the burn.
- ``kerf_paid``  — pre-paid credits.  Any model.  20% markup over COGS.
- ``byo_<provider>``  — user's own API key.  Zero billing.  Tokens still
  recorded so the user can see them on the dashboard.

The selector is a pure function: given the user's state and an estimated
cost, it returns a tagged Bucket value (or an InsufficientCredits sentinel).
Side effects (decrementing balance / quota, inserting usage_events) are
the caller's job and live in :mod:`kerf_billing.spend`.

The caller MUST commit token usage + balance/quota deduction inside a
single SQL transaction so they can't drift.  See ``spend.commit_spend``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Union


logger = logging.getLogger(__name__)


# ── Bucket tag types ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class KerfFree:
    """Free-tier quota — cheap-tier models only, charged to monthly counter."""
    pass


@dataclass(frozen=True)
class KerfPaid:
    """Pre-paid credits — any model, decremented from cloud_user_balances."""
    pass


@dataclass(frozen=True)
class Byo:
    """User's own API key — zero billing, just tokens recorded."""
    provider: str


@dataclass(frozen=True)
class InsufficientCredits:
    """Refuse the request.  ``byo_available`` is True iff the user has a
    saved key for the chosen model's provider — the frontend uses this to
    decide between an INSUFFICIENT_CREDITS_BYO_AVAILABLE and a plain
    INSUFFICIENT_CREDITS error."""
    byo_available: bool


Bucket = Union[KerfFree, KerfPaid, Byo, InsufficientCredits]


# ── Selector input snapshot ──────────────────────────────────────────────────
@dataclass(frozen=True)
class UserBilling:
    """The subset of user-row + balance-row state the selector reads.

    Snapshotted at the start of each chat request so the selector remains
    a pure function (and is trivially unit-testable).
    """
    user_id: str
    prefer_byo: bool
    credits_usd: float
    free_tokens_in_remaining: int
    free_tokens_out_remaining: int
    byo_providers: frozenset[str]


@dataclass(frozen=True)
class ModelInfo:
    """The subset of model_prices row the selector cares about."""
    provider: str
    model_id: str
    cheap_tier_eligible: bool


# ── Pure selector ────────────────────────────────────────────────────────────
def pick_bucket(
    user: UserBilling,
    model: ModelInfo,
    estimated_cost_usd: float,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
) -> Bucket:
    """Resolve the bucket for a chat request.

    Order:
    1. BYO preferred + key present for provider → ``Byo(provider)``.
    2. Cheap-tier model + free quota remains → ``KerfFree``.
    3. Credit balance covers estimated cost → ``KerfPaid``.
    4. Else → ``InsufficientCredits(byo_available=...)``.

    Estimates only need to be order-of-magnitude correct — we re-evaluate
    against actuals when settling.
    """
    # 1. BYO preference: only honoured if a key is on file for the provider.
    if user.prefer_byo and model.provider in user.byo_providers:
        return Byo(provider=model.provider)

    # 2. Free tier: must be a cheap-tier-eligible model AND must have BOTH
    #    in + out quota left to cover this turn's estimate.  We don't try to
    #    split a single request across two buckets — keeps the bookkeeping
    #    sane.
    if (
        model.cheap_tier_eligible
        and user.free_tokens_in_remaining >= max(1, estimated_input_tokens)
        and user.free_tokens_out_remaining >= max(1, estimated_output_tokens)
    ):
        return KerfFree()

    # 3. Paid: do we have credits to cover the estimate?
    if user.credits_usd >= estimated_cost_usd and user.credits_usd > 0:
        return KerfPaid()

    # 4. No path forward.  Tell the frontend which 402 variant to render.
    return InsufficientCredits(
        byo_available=(model.provider in user.byo_providers),
    )


# ── Snapshot loaders (DB side, async) ────────────────────────────────────────
async def load_user_billing(pool, user_id: str) -> UserBilling:
    """Pull the user_billing snapshot from Postgres in one round-trip."""
    async with pool.acquire() as conn:
        # Three small queries, sequential — saves a JOIN that would otherwise
        # span three tables for one nullable row.
        balance_row = await conn.fetchrow(
            """
            SELECT credits_usd,
                   free_tokens_in_remaining,
                   free_tokens_out_remaining
            FROM cloud_user_balances WHERE user_id = $1
            """,
            user_id,
        )
        user_row = await conn.fetchrow(
            "SELECT prefer_byo FROM users WHERE id = $1",
            user_id,
        )
        byo_rows = await conn.fetch(
            "SELECT provider FROM user_provider_keys WHERE user_id = $1",
            user_id,
        )

    credits_usd = float(balance_row["credits_usd"]) if balance_row else 0.0
    free_in = int(balance_row["free_tokens_in_remaining"]) if balance_row else 0
    free_out = int(balance_row["free_tokens_out_remaining"]) if balance_row else 0
    prefer_byo = bool(user_row["prefer_byo"]) if user_row else False
    providers = frozenset(r["provider"] for r in byo_rows)

    return UserBilling(
        user_id=user_id,
        prefer_byo=prefer_byo,
        credits_usd=credits_usd,
        free_tokens_in_remaining=free_in,
        free_tokens_out_remaining=free_out,
        byo_providers=providers,
    )


async def load_model_info(pool, provider: str, model_id: str) -> Optional[ModelInfo]:
    """Minimal model_prices read — just provider + id + cheap flag."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT provider, model_id, cheap_tier_eligible
            FROM model_prices
            WHERE provider = $1 AND model_id = $2
            """,
            provider, model_id,
        )
        if not row:
            return None
        return ModelInfo(
            provider=row["provider"],
            model_id=row["model_id"],
            cheap_tier_eligible=bool(row["cheap_tier_eligible"]),
        )
