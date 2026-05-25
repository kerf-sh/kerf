"""GPU-render billing meter — kerf_paid credit draw.

Every render job that reaches the cycles_worker flows through this module.
The two public entry-points are:

``quote_render``
    Called BEFORE the job is dispatched.  Returns the expected credit cost,
    whether the result would come from cache (zero cost), and the ``would_charge``
    flag the caller uses to show a confirmation dialog.

``charge_render``
    Called AFTER the worker reports job completion (or immediately on a cache
    hit, though cache hits are free).  Atomically decrements the user's
    ``kerf_paid`` balance via a guarded ``UPDATE … WHERE amount >= cost``
    so concurrent calls cannot drive the balance negative.

Free quota
----------
Studio tier users receive 3 Hero renders per calendar month at no cost.
The quota is stored in ``render_free_quota`` (one row per user per month).
``charge_render`` decrements the monthly allowance first; only after the
allowance reaches zero does it draw from ``kerf_paid`` credits.

Cache semantics
---------------
The ``cache_key`` argument to ``quote_render`` is an opaque string that the
render pipeline derives from (scene_blob_hash, preset, denoising_config, …).
If a completed result is found in ``render_cache`` the job is returned
immediately — zero GPU time, zero credit cost.

Database tables (created by kerf-cloud migrations, not this module):

    cloud_user_balances (user_id, credits_usd, …)
    render_free_quota   (user_id, month TEXT, hero_renders_remaining INT)
    render_cache        (cache_key TEXT PRIMARY KEY, created_at, …)
    render_usage_events (job_id, user_id, preset, gpu_seconds, credits_charged, …)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from kerf_pricing.render_presets import RENDER_CREDIT_COST, VALID_PRESETS
from kerf_billing.buckets import (
    KerfFree,
    KerfPaid,
    Byo,
    InsufficientCredits,
    UserBilling,
    ModelInfo,
    pick_bucket,
)


logger = logging.getLogger(__name__)

# ── Billing kill-switch (mirrors kerf_render.pricing_meter) ─────────────────
_BILLING_DISABLED_VAR = "KERF_RENDER_BILLING_DISABLED"


def _billing_disabled() -> bool:
    """Return True when the self-host billing kill-switch is active."""
    return os.environ.get(_BILLING_DISABLED_VAR, "").strip() == "1"


# ── Synthetic ModelInfo for GPU renders ─────────────────────────────────────
# GPU renders are never on the free cheap-tier — only kerf_paid or byo.
_GPU_MODEL_INFO = ModelInfo(
    provider="gpu",
    model_id="gpu-render",
    cheap_tier_eligible=False,
)

# Re-export the canonical cost table so callers only need to import this module.
RENDER_CREDIT_COST = RENDER_CREDIT_COST  # noqa: F811  (re-export)

# Studio tier entitlement: free Hero renders per calendar month.
_STUDIO_FREE_HERO_PER_MONTH = 3
_STUDIO_TIER_NAME = "studio"

# The preset whose free quota applies (Hero only for now).
_FREE_QUOTA_PRESET = "hero"


# ── Preset validation ────────────────────────────────────────────────────────
class UnknownPresetError(ValueError):
    """Raised when an unrecognised preset name is passed to any public API."""

    def __init__(self, preset: str):
        super().__init__(
            f"Unknown render preset {preset!r}. "
            f"Valid presets: {sorted(VALID_PRESETS)}"
        )
        self.preset = preset


def _require_preset(preset: str) -> float:
    preset = preset.lower()
    if preset not in RENDER_CREDIT_COST:
        raise UnknownPresetError(preset)
    return RENDER_CREDIT_COST[preset]


# ── GPU gate ─────────────────────────────────────────────────────────────────

class RenderGateDenied(Exception):
    """Raised by :func:`gate_render_job` when a render must be blocked.

    Attributes
    ----------
    reason : str
        Human-readable explanation (``"gpu_paid_only"`` | ``"insufficient_credits"``).
    need_credits : float | None
        How many more USD credits the user needs, when reason is
        ``"insufficient_credits"``.
    """

    def __init__(self, reason: str, need_credits: Optional[float] = None):
        super().__init__(reason)
        self.reason = reason
        self.need_credits = need_credits


async def gate_render_job(
    pool,
    user_id: str,
    est_gpu_seconds: float,
    *,
    usage_enabled: bool = True,
) -> None:
    """Billing gate that MUST be called before a render job is dispatched.

    Behaviour
    ---------
    * **Self-host / billing disabled** (``KERF_RENDER_BILLING_DISABLED=1``
      *or* ``usage_enabled=False``): skips the gate entirely — no block,
      no bill.  Self-host users own their own GPU.
    * **kerf_free** bucket: GPU is paid-only.  Raises
      :class:`RenderGateDenied` with ``reason="gpu_paid_only"``.
    * **kerf_paid** with insufficient credits: raises
      :class:`RenderGateDenied` with ``reason="insufficient_credits"``.
    * **kerf_paid** with sufficient credits: returns normally (permit).
    * **byo**: returns normally (user pays their own cloud bill).
    * Any unexpected error inside the gate → re-raises as
      :class:`RenderGateDenied` with ``reason="gate_error"`` (fail-closed,
      since GPU is a direct cost we cannot absorb unknowns).

    Parameters
    ----------
    pool:
        asyncpg connection pool.
    user_id:
        Cloud user UUID.
    est_gpu_seconds:
        Estimated GPU wall-clock seconds for the job.  Used to compute the
        estimated USD cost for the :func:`pick_bucket` call.
    usage_enabled:
        Mirror of ``settings.usage_enabled``.  When ``False`` (local /
        OSS deploy), the gate is skipped entirely.
    """
    # ── Self-host / local-mode kill-switch ────────────────────────────────────
    if _billing_disabled() or not usage_enabled:
        logger.debug("gate_render_job: billing disabled — skipping gate")
        return

    try:
        # Load current billing snapshot for this user.
        from kerf_billing.buckets import load_user_billing  # local import to avoid cycle
        user_billing = await load_user_billing(pool, user_id)

        # Estimate cost using the L4 rate (RunPod entry-level, conservative
        # lower-bound; actual GPU type is resolved by the worker after dispatch).
        from kerf_render.pricing_meter import GPU_RATES_USD_PER_SECOND, GPU_MARKUP_PCT
        base_rate = GPU_RATES_USD_PER_SECOND.get("l4", 0.000194)
        est_cost_usd = est_gpu_seconds * base_rate * (1.0 + GPU_MARKUP_PCT / 100.0)

        bucket = pick_bucket(user_billing, _GPU_MODEL_INFO, est_cost_usd)

    except RenderGateDenied:
        raise  # already formatted
    except Exception as exc:
        # Fail-closed: any gate error blocks the dispatch.
        logger.error("gate_render_job: unexpected error for user=%s — blocking: %s", user_id, exc)
        raise RenderGateDenied("gate_error") from exc

    if isinstance(bucket, KerfFree):
        # Free tier (cheap-tier model only path hit): GPU is paid-only.
        # This path is unlikely given GPU renders are cheap_tier_eligible=False,
        # but guard defensively.
        logger.info("gate_render_job: blocked free-tier user=%s (gpu_paid_only)", user_id)
        raise RenderGateDenied("gpu_paid_only")

    if isinstance(bucket, InsufficientCredits):
        # Distinguish zero-credit (free-tier) users from partial-credit users.
        if user_billing.credits_usd <= 0:
            logger.info("gate_render_job: blocked zero-credit user=%s (gpu_paid_only)", user_id)
            raise RenderGateDenied("gpu_paid_only")
        need = round(est_cost_usd - user_billing.credits_usd, 6)
        logger.info(
            "gate_render_job: blocked user=%s insufficient_credits "
            "est_cost=%.4f balance=%.4f need=%.4f",
            user_id, est_cost_usd, user_billing.credits_usd, need,
        )
        raise RenderGateDenied("insufficient_credits", need_credits=max(0.0, need))

    # KerfPaid or Byo — permit.
    logger.debug("gate_render_job: permitted user=%s bucket=%r", user_id, bucket)


# ── Quote ────────────────────────────────────────────────────────────────────
async def quote_render(
    pool,
    preset: str,
    scene_blob_hash: str,
    cache_key: Optional[str] = None,
) -> dict:
    """Return a pricing quote for a prospective render job.

    Parameters
    ----------
    pool:
        asyncpg connection pool.
    preset:
        One of ``draft``, ``standard``, ``hero``, ``cinema`` (case-insensitive).
    scene_blob_hash:
        Content-addressed hash of the scene data.  Stored with the quote for
        audit purposes but not used in cache lookup (``cache_key`` is the
        richer composite key).
    cache_key:
        Optional composite cache key (preset + scene + settings hash).  When
        provided and a matching entry is found in ``render_cache``, the quote
        returns ``cache_hit=True`` and ``credits=0``.

    Returns
    -------
    dict with keys:
        ``credits``      float — expected credit cost (0 if cache hit)
        ``cache_hit``    bool  — True iff an identical render is already cached
        ``would_charge`` bool  — False if cache hit or cost is zero
    """
    preset = preset.lower()
    cost = _require_preset(preset)

    cache_hit = False
    if cache_key and pool is not None:
        cache_hit = await _check_cache(pool, cache_key)

    credits = 0.0 if cache_hit else cost
    return {
        "credits": credits,
        "cache_hit": cache_hit,
        "would_charge": credits > 0,
    }


async def _check_cache(pool, cache_key: str) -> bool:
    """Return True iff ``cache_key`` exists in ``render_cache``."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM render_cache WHERE cache_key = $1",
            cache_key,
        )
    return row is not None


# ── Charge ───────────────────────────────────────────────────────────────────
async def charge_render(
    pool,
    user_id: str,
    job_id: str,
    preset: str,
    gpu_seconds_actual: float,
    *,
    user_tier: str = "",
    cache_key: Optional[str] = None,
) -> dict:
    """Atomically charge the user's kerf_paid balance for a completed render.

    Free-quota path (Studio tier)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    If the user is on the Studio tier AND the preset is ``hero`` AND monthly
    allowance remains, we decrement the allowance table first.  The credits
    cost is still reported (so the caller can display it) but no money balance
    is touched.

    Atomic paid path
    ~~~~~~~~~~~~~~~~
    Uses a single guarded ``UPDATE … WHERE credits_usd >= cost RETURNING …``.
    If the row is not updated (balance < cost) we return ``ok=False`` without
    touching the balance.  This prevents races between concurrent charge calls.

    Cache-hit path
    ~~~~~~~~~~~~~~
    Pass ``cache_key`` and the function skips all deductions, returning
    ``credits_deducted=0``.

    Parameters
    ----------
    pool:
        asyncpg connection pool.
    user_id:
        Cloud user UUID.
    job_id:
        Render job UUID (for ``render_usage_events``).
    preset:
        One of ``draft``, ``standard``, ``hero``, ``cinema``.
    gpu_seconds_actual:
        Measured GPU wall-clock seconds from the worker report.  Stored in
        ``render_usage_events`` for COGS reconciliation; does NOT affect cost.
    user_tier:
        The user's current subscription tier name (e.g. ``"studio"``).
        Used to determine free-quota eligibility.
    cache_key:
        When provided and present in ``render_cache``, the call is a no-op
        (zero deduction).

    Returns
    -------
    dict with keys:
        ``ok``               bool
        ``credits_deducted`` float
        ``new_balance``      float  (None when ok=False)
        ``reason``           str | None  (set when ok=False)
        ``need_credits``     float | None  (set when reason='insufficient_credits')
        ``free_quota_used``  bool  — True when Studio free allowance was consumed
    """
    preset = preset.lower()
    cost = _require_preset(preset)

    # ── Cache hit — zero cost ────────────────────────────────────────────────
    if cache_key:
        is_hit = await _check_cache(pool, cache_key)
        if is_hit:
            await _record_usage(pool, user_id, job_id, preset, gpu_seconds_actual, 0.0)
            return {
                "ok": True,
                "credits_deducted": 0.0,
                "new_balance": None,
                "reason": None,
                "need_credits": None,
                "free_quota_used": False,
            }

    # ── Studio free-quota path ───────────────────────────────────────────────
    # R11 fix: always resolve the tier from the DB so callers cannot grant
    # themselves Studio entitlements by passing user_tier="studio".
    # The passed-in `user_tier` is kept for backward-compat signatures but
    # the DB value ALWAYS overrides it for the free-quota gate.
    # If the DB lookup fails (e.g. column absent on older OSS DB), the
    # exception is caught by _fetch_subscription_tier which returns "".
    # An empty string is NOT "studio", so free quota is denied — fail-closed.
    if preset == _FREE_QUOTA_PRESET:
        effective_tier = await _fetch_subscription_tier(pool, user_id)
    else:
        effective_tier = ""

    if (
        effective_tier == _STUDIO_TIER_NAME
        and preset == _FREE_QUOTA_PRESET
    ):
        used_quota = await _try_consume_free_quota(pool, user_id)
        if used_quota:
            await _record_usage(pool, user_id, job_id, preset, gpu_seconds_actual, 0.0)
            return {
                "ok": True,
                "credits_deducted": 0.0,
                "new_balance": None,
                "reason": None,
                "need_credits": None,
                "free_quota_used": True,
            }

    # ── kerf_paid atomic deduction ────────────────────────────────────────────
    new_balance = await _atomic_deduct(pool, user_id, cost)

    if new_balance is None:
        # balance was < cost; fetch current balance to compute shortfall
        current = await _fetch_balance(pool, user_id)
        need = round(cost - current, 6)
        logger.info(
            "charge_render: insufficient credits user=%s preset=%s cost=%.2f balance=%.4f",
            user_id, preset, cost, current,
        )
        return {
            "ok": False,
            "credits_deducted": 0.0,
            "new_balance": current,
            "reason": "insufficient_credits",
            "need_credits": need,
            "free_quota_used": False,
        }

    await _record_usage(pool, user_id, job_id, preset, gpu_seconds_actual, cost)
    logger.info(
        "charge_render: charged user=%s preset=%s credits=%.2f balance=%.4f",
        user_id, preset, cost, new_balance,
    )
    return {
        "ok": True,
        "credits_deducted": cost,
        "new_balance": new_balance,
        "reason": None,
        "need_credits": None,
        "free_quota_used": False,
    }


# ── Internal helpers ─────────────────────────────────────────────────────────
async def _atomic_deduct(pool, user_id: str, cost: float) -> Optional[float]:
    """Attempt to deduct ``cost`` from ``credits_usd`` in one SQL statement.

    Returns the NEW balance on success, or ``None`` if the balance was
    insufficient (the UPDATE matched zero rows).

    The ``WHERE credits_usd >= $2`` guard is the serialisation point; Postgres
    row-level locking ensures two concurrent calls cannot both see a balance
    that covers the cost when only one can actually succeed after the other has
    already decremented.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE cloud_user_balances
                   SET credits_usd = credits_usd - $2
                 WHERE user_id = $1
                   AND credits_usd >= $2
                RETURNING credits_usd
                """,
                user_id, cost,
            )
    if row is None:
        return None
    return float(row["credits_usd"])


async def _fetch_balance(pool, user_id: str) -> float:
    """Read current credit balance; returns 0.0 if no row exists."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits_usd FROM cloud_user_balances WHERE user_id = $1",
            user_id,
        )
    return float(row["credits_usd"]) if row else 0.0


async def _fetch_subscription_tier(pool, user_id: str) -> str:
    """Return the verified subscription tier for *user_id* from the DB.

    Reads ``cloud_user_balances.subscription_tier``.  Returns an empty string
    when no row exists (e.g. in tests that use a minimal pool stub).
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT subscription_tier FROM cloud_user_balances WHERE user_id = $1",
                user_id,
            )
        if row is None:
            return ""
        return str(row["subscription_tier"]).lower()
    except Exception as exc:
        # If the column doesn't exist (older DB) or any other DB error, fall back
        # to empty so the caller degrades gracefully (no free quota granted).
        logger.warning(
            "_fetch_subscription_tier: DB error for user=%s — treating as non-studio: %s",
            user_id, exc,
        )
        return ""


async def _try_consume_free_quota(pool, user_id: str) -> bool:
    """Decrement the Studio hero-render monthly allowance by 1.

    Returns True iff an allowance row existed with > 0 remaining and was
    successfully decremented.  If no row exists for the current month, one
    is created with ``_STUDIO_FREE_HERO_PER_MONTH - 1`` remaining.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Upsert: if no row for this month, seed it at max allowance.
            await conn.execute(
                """
                INSERT INTO render_free_quota
                    (user_id, month, hero_renders_remaining)
                VALUES ($1, to_char(current_date, 'YYYY-MM'), $2)
                ON CONFLICT (user_id, month) DO NOTHING
                """,
                user_id, _STUDIO_FREE_HERO_PER_MONTH,
            )
            row = await conn.fetchrow(
                """
                UPDATE render_free_quota
                   SET hero_renders_remaining = hero_renders_remaining - 1
                 WHERE user_id = $1
                   AND month = to_char(current_date, 'YYYY-MM')
                   AND hero_renders_remaining > 0
                RETURNING hero_renders_remaining
                """,
                user_id,
            )
    return row is not None


async def _record_usage(
    pool, user_id: str, job_id: str,
    preset: str, gpu_seconds: float, credits_charged: float,
) -> None:
    """Append a row to ``render_usage_events`` AND ``usage_events`` (best-effort).

    ``render_usage_events`` is the detailed COGS ledger used for GPU
    reconciliation.  ``usage_events`` (kind='gpu') is the user-visible
    dashboard ledger so render spend appears alongside token/storage charges.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO render_usage_events
                    (job_id, user_id, preset, gpu_seconds, credits_charged)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (job_id) DO NOTHING
                """,
                job_id, user_id, preset, gpu_seconds, credits_charged,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_meter: failed to record render_usage_event: %s", exc)

    # Surface GPU spend in the shared usage_events ledger (kind='gpu').
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_events
                    (id, user_id, kind, usd_cost, payer)
                VALUES ($1, $2, 'gpu', $3, 'kerf_paid')
                ON CONFLICT (id) DO NOTHING
                """,
                job_id, user_id, credits_charged,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_meter: failed to record gpu usage_event: %s", exc)
