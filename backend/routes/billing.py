import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import get_settings
from db.connection import get_pool_required
from dependencies import require_auth

from cloud.billing.paystack import PaystackClient
from cloud.billing.handlers import Handlers as BillingHandlers
from cloud.fx import Fetcher


settings = get_settings()
router = APIRouter()

_pool = None
_paystack = None
_fx = None
_billing_handlers = None


def _get_pool():
    global _pool
    if _pool is None:
        import asyncio
        from db.connection import get_pool
        loop = asyncio.get_event_loop()
        _pool = loop.run_until_complete(get_pool())
    return _pool


def _get_paystack() -> Optional[PaystackClient]:
    global _paystack
    if _paystack is None and settings.cloud_paystack_secret_key:
        _paystack = PaystackClient(
            secret_key=settings.cloud_paystack_secret_key,
            public_key=settings.cloud_paystack_public_key,
            webhook_secret=settings.cloud_paystack_webhook_secret,
        )
    return _paystack


def _get_fx() -> Optional[Fetcher]:
    global _fx, _pool
    if _fx is None:
        pool = _get_pool()
        _fx = Fetcher(settings, pool)
    return _fx


def _get_billing_handlers() -> Optional[BillingHandlers]:
    global _billing_handlers
    if _billing_handlers is None:
        _billing_handlers = BillingHandlers(
            pool=_get_pool(),
            cfg=settings,
            fx_fetcher=_get_fx(),
            paystack_client=_get_paystack(),
            mailer=None,
        )
    return _billing_handlers


class TopupRequest(BaseModel):
    amount_usd: float
    callback_url: Optional[str] = None


@router.post("/billing/topup")
async def topup(
    request: Request,
    payload: dict = Depends(require_auth),
    body: TopupRequest = None,
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    handlers = _get_billing_handlers()
    if not handlers:
        raise HTTPException(status_code=503, detail="paystack not configured")

    rate, _, ok = await handlers.fx.rate_with_spread(
        settings.cloud_fx_base_currency,
        settings.cloud_fx_settlement_currency,
        settings.cloud_fx_spread_pct,
    )
    if not ok or rate <= 0:
        raise HTTPException(status_code=503, detail="fx rate unavailable")

    amount_zar = body.amount_usd * rate
    amount_zar_cents = int(amount_zar * 100)

    pool = _get_pool()
    user_email_row = await pool.fetchrow(
        "SELECT email FROM users WHERE id = $1",
        uid,
    )
    if not user_email_row:
        raise HTTPException(status_code=500, detail="user lookup failed")
    email = user_email_row["email"]

    reference = str(uuid.uuid4())

    await pool.execute(
        """
        INSERT INTO cloud_invoices (user_id, reference, status, amount_usd, amount_zar, fx_rate)
        VALUES ($1, $2, 'pending', $3, $4, $5)
        """,
        uid, reference, body.amount_usd, amount_zar, rate,
    )

    paystack = _get_paystack()
    try:
        auth_url, _ = paystack.initialize_transaction(
            email, amount_zar_cents, reference, body.callback_url or "",
        )
    except Exception as e:
        await pool.execute(
            "UPDATE cloud_invoices SET status = 'abandoned' WHERE reference = $1",
            reference,
        )
        raise HTTPException(status_code=502, detail=f"paystack: {e}")

    return {
        "authorization_url": auth_url,
        "reference": reference,
        "amount_usd": body.amount_usd,
        "amount_zar": amount_zar,
        "fx_rate": rate,
    }


@router.get("/billing/me")
async def me(payload: dict = Depends(require_auth)):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    pool = _get_pool()

    balance_row = await pool.fetchrow(
        "SELECT credits_usd FROM cloud_user_balances WHERE user_id = $1",
        uid,
    )
    credits_usd = balance_row["credits_usd"] if balance_row else 0.0

    invoices = await _load_recent_invoices(pool, uid, 20)
    usage = await _load_recent_usage(pool, uid, 20)

    return {
        "credits_usd": credits_usd,
        "recent_invoices": invoices,
        "recent_usage": usage,
    }


@router.get("/billing/usage")
async def usage(
    payload: dict = Depends(require_auth),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = 200,
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")

    now = datetime.utcnow()
    default_from = datetime(now.year, now.month, 1)
    default_to = datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1)

    from_time = _parse_time_or_default(from_date, default_from)
    to_time = _parse_time_or_default(to_date, default_to)

    pool = _get_pool()
    rows = await pool.fetch(
        """
        SELECT id, kind, model, input_tokens, output_tokens, bytes_delta,
               usd_cost, project_id, created_at
        FROM usage_events
        WHERE user_id = $1 AND created_at >= $2 AND created_at < $3
        ORDER BY created_at DESC
        LIMIT $4
        """,
        uid, from_time, to_time, min(limit or 200, 1000),
    )

    events = []
    for row in rows:
        events.append({
            "id": str(row["id"]),
            "kind": row["kind"],
            "model": row["model"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "bytes_delta": row["bytes_delta"] or 0,
            "usd_cost": row["usd_cost"],
            "project_id": str(row["project_id"]) if row["project_id"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return {"events": events, "from": from_time.isoformat(), "to": to_time.isoformat()}


@router.post("/billing/webhook")
async def webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("x-paystack-signature", "")

    paystack = _get_paystack()
    if not paystack or not paystack.verify_webhook_signature(body, sig):
        raise HTTPException(status_code=401, detail="invalid signature")

    import json
    try:
        envelope = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="decode envelope")

    event = envelope.get("event")
    data = envelope.get("data", {})

    if event == "charge.success":
        try:
            await _handle_charge_success(data, body)
        except Exception as e:
            import logging
            logging.error(f"billing/webhook: charge.success: {e}")
            raise HTTPException(status_code=500, detail="processing failed")

    return {"status": "ok"}


async def _handle_charge_success(data: dict, raw_body: bytes) -> None:
    reference = data.get("reference")
    if not reference:
        raise ValueError("missing reference")

    pool = _get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT user_id, status, amount_usd, amount_zar, fx_rate
                FROM cloud_invoices
                WHERE reference = $1
                FOR UPDATE
                """,
                reference,
            )

            if not row:
                import logging
                logging.info(f"billing/webhook: unknown reference {reference} — acking")
                return

            if row["status"] == "success":
                return

            await conn.execute(
                """
                UPDATE cloud_invoices
                SET status = 'success',
                    paid_at = now(),
                    paystack_response = $2::jsonb
                WHERE reference = $1
                """,
                reference, raw_body.decode(),
            )

            await conn.execute(
                "SELECT cloud_debit_balance($1, $2)",
                row["user_id"], -row["amount_usd"],
            )

            customer = data.get("customer", {})
            customer_code = customer.get("customer_code")
            if customer_code:
                await conn.execute(
                    """
                    INSERT INTO cloud_paystack_customers(user_id, customer_code, customer_id, email)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        customer_code = excluded.customer_code,
                        customer_id = excluded.customer_id,
                        email = excluded.email
                    """,
                    row["user_id"],
                    customer_code,
                    customer.get("id"),
                    customer.get("email"),
                )


async def _load_recent_invoices(pool, user_id: str, limit: int) -> list:
    rows = await pool.fetch(
        """
        SELECT id, reference, status, amount_usd, amount_zar, fx_rate,
               created_at, paid_at
        FROM cloud_invoices
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id, limit,
    )
    result = []
    for row in rows:
        result.append({
            "id": str(row["id"]),
            "reference": row["reference"],
            "status": row["status"],
            "amount_usd": row["amount_usd"],
            "amount_zar": row["amount_zar"],
            "fx_rate": row["fx_rate"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "paid_at": row["paid_at"].isoformat() if row["paid_at"] else None,
        })
    return result


async def _load_recent_usage(pool, user_id: str, limit: int) -> list:
    rows = await pool.fetch(
        """
        SELECT id, kind, model, input_tokens, output_tokens, bytes_delta,
               usd_cost, project_id, created_at
        FROM usage_events
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id, limit,
    )
    result = []
    for row in rows:
        result.append({
            "id": str(row["id"]),
            "kind": row["kind"],
            "model": row["model"],
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "bytes_delta": row["bytes_delta"] or 0,
            "usd_cost": row["usd_cost"],
            "project_id": str(row["project_id"]) if row["project_id"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })
    return result


def _parse_time_or_default(s: Optional[str], default: datetime) -> datetime:
    if not s:
        return default
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return default
