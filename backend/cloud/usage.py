import logging
from datetime import datetime
from typing import Optional, Protocol


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
        await conn.execute(
            """
            INSERT INTO usage_events
                (user_id, project_id, kind, bytes_delta, usd_cost)
            VALUES ($1, $2, 'storage', $3, $4)
            """,
            user_id, project_id, delta_bytes, cost_usd,
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
    raise NotImplementedError("MonthlyStorageDebit: not implemented")


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
