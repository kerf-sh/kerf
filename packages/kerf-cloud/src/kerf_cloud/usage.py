import logging
from datetime import datetime
from typing import Optional, Protocol

from kerf_core.config import get_settings

logger = logging.getLogger(__name__)

LOW_BALANCE_THRESHOLD_USD = 1.0


class MailerSink(Protocol):
    async def send_template(self, template: str, recipient: str, user_id: str, data: dict) -> None: ...
    async def eligible_for_low_balance(self, user_id: str) -> bool: ...


_mailer: Optional[MailerSink] = None
_notify_app_url: str = ""


def set_mailer(mailer: MailerSink, app_url: str) -> None:
    global _mailer, _notify_app_url
    _mailer = mailer
    _notify_app_url = app_url


async def record_token_event(
    pool,
    user_id: str,
    project_id: Optional[str],
    model: str,
    in_tokens: int,
    out_tokens: int,
    cost_usd: float,
) -> None:
    if not user_id:
        raise ValueError("usage: userID required")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO usage_events
                    (user_id, project_id, kind, model, input_tokens, output_tokens, usd_cost)
                VALUES ($1, $2, 'token', $3, $4, $5, $6)
                """,
                user_id, project_id, model, in_tokens, out_tokens, cost_usd,
            )

            await conn.execute(
                "SELECT cloud_debit_balance($1, $2)",
                user_id, cost_usd,
            )

    await _maybe_fire_low_balance(pool, user_id)


async def record_storage_event(
    pool,
    user_id: str,
    project_id: Optional[str],
    delta_bytes: int,
    cost_usd: float,
) -> None:
    if not user_id:
        raise ValueError("usage: userID required")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO usage_events
                    (user_id, project_id, kind, bytes_delta, usd_cost)
                VALUES ($1, $2, 'storage', $3, $4)
                """,
                user_id, project_id, delta_bytes, cost_usd,
            )

            await conn.execute(
                "SELECT cloud_debit_balance($1, $2)",
                user_id, cost_usd,
            )


async def balance_for(pool, user_id: str) -> float:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits_usd FROM cloud_user_balances WHERE user_id = $1",
            user_id,
        )
        if not row:
            return 0.0
        return row["credits_usd"]


async def monthly_storage_debit(pool) -> None:
    """Sweep all workspaces and debit storage cost for the current month.

    Attribution rule (per design doc large-object-billing.md):
      billable_bytes(W) = Σ blob_objects.size_bytes WHERE first_workspace_id = W

    Forks (blob_refs rows whose project's workspace != first_workspace_id) pay
    nothing — they are not the first uploader.  NULL first_workspace_id rows
    are skipped (orphan objects, FK set-null after workspace delete).

    Free tier: first cloud_pricing_free_storage_mb MB per workspace is gratis.

    The payer column is always 'kerf_paid' for storage events — storage cost is
    infrastructure COGS that applies regardless of LLM billing bucket.

    Edge cases handled at the SELECT level (no extra reassignment machinery —
    that belongs to T-136 / the ref-deletion path):
      - NULL first_workspace_id → excluded by WHERE clause; not billed
      - Forked blobs → only counted under original first_workspace_id workspace
      - Zero chargeable bytes (under free tier) → no usage_events row, no debit
    """
    settings = get_settings()
    free_bytes = settings.cloud_pricing_free_storage_mb * 1024 * 1024
    rate_per_gb_month = settings.cloud_pricing_storage_usd_per_gb_month

    async with pool.acquire() as conn:
        # Fetch every workspace that owns at least one blob_object, together
        # with the owner's user_id (workspaces.created_by = the billing target).
        rows = await conn.fetch(
            """
            SELECT
                bo.first_workspace_id                    AS workspace_id,
                w.created_by                             AS user_id,
                COALESCE(SUM(bo.size_bytes), 0)::bigint  AS billable_bytes
            FROM   blob_objects bo
            JOIN   workspaces w ON w.id = bo.first_workspace_id
            WHERE  bo.first_workspace_id IS NOT NULL
            GROUP  BY bo.first_workspace_id, w.created_by
            """
        )

    for row in rows:
        workspace_id = row["workspace_id"]
        user_id = row["user_id"]
        billable_bytes = row["billable_bytes"]

        chargeable = max(0, billable_bytes - free_bytes)
        if chargeable == 0:
            continue

        cost_usd = (chargeable / (1024.0 ** 3)) * rate_per_gb_month

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO usage_events
                        (user_id, project_id, kind, bytes_delta, usd_cost, payer)
                    VALUES ($1, NULL, 'storage', $2, $3, 'kerf_paid')
                    """,
                    user_id, billable_bytes, cost_usd,
                )

                await conn.execute(
                    "SELECT cloud_debit_balance($1, $2)",
                    user_id, cost_usd,
                )


async def _maybe_fire_low_balance(pool, user_id: str) -> None:
    global _mailer, _notify_app_url
    if _mailer is None:
        return

    bal = await balance_for(pool, user_id)
    if bal >= LOW_BALANCE_THRESHOLD_USD:
        return

    ok = await _mailer.eligible_for_low_balance(user_id)
    if not ok:
        return

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT email FROM users WHERE id = $1", user_id)
        if not row or not row["email"]:
            return

        try:
            await _mailer.send_template(
                "low_balance",
                row["email"],
                user_id,
                {"BalanceUSD": bal, "AppURL": _notify_app_url},
            )
        except Exception as e:
            logger.warning(f"usage: queue low-balance: {e}")
