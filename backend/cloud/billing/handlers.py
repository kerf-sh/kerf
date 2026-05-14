import json
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class Handlers:
    def __init__(self, pool, cfg, fx_fetcher, paystack_client, mailer=None):
        self.pool = pool
        self.cfg = cfg
        self.fx = fx_fetcher
        self.paystack = paystack_client
        self.mailer = mailer

    def mount(self, authed, public):
        if authed:
            authed.add_api_route("/topup", self.topup, methods=["POST"])
            authed.add_api_route("/me", self.me, methods=["GET"])
            authed.add_api_route("/usage", self.usage, methods=["GET"])
        if public:
            public.add_api_route("/webhook", self.webhook, methods=["POST"])

    async def topup(self, request: Request) -> JSONResponse:
        uid = request.state.user_id if hasattr(request.state, "user_id") else None
        if not uid:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid body"})

        amount_usd = body.get("amount_usd", 0)
        if amount_usd <= 0:
            return JSONResponse(status_code=400, content={"error": "amount_usd must be > 0"})

        if not self.paystack:
            return JSONResponse(status_code=503, content={"error": "paystack not configured"})

        rate, _, ok = await self.fx.rate_with_spread(
            self.cfg.cloud_fx_base_currency,
            self.cfg.cloud_fx_settlement_currency,
            self.cfg.cloud_fx_spread_pct,
        )
        if not ok or rate <= 0:
            return JSONResponse(status_code=503, content={"error": "fx rate unavailable"})

        amount_zar = amount_usd * rate
        amount_zar_cents = int(amount_zar * 100)

        user_email_row = await self.pool.fetchrow(
            "SELECT email FROM users WHERE id = $1",
            uid,
        )
        if not user_email_row:
            return JSONResponse(status_code=500, content={"error": "user lookup failed"})
        email = user_email_row["email"]

        reference = str(uuid.uuid4())

        await self.pool.execute(
            """
            INSERT INTO cloud_invoices (user_id, reference, status, amount_usd, amount_zar, fx_rate)
            VALUES ($1, $2, 'pending', $3, $4, $5)
            """,
            uid, reference, amount_usd, amount_zar, rate,
        )

        callback_url = body.get("callback_url", "")
        try:
            auth_url, _ = self.paystack.initialize_transaction(
                email, amount_zar_cents, reference, callback_url,
            )
        except Exception as e:
            await self.pool.execute(
                "UPDATE cloud_invoices SET status = 'abandoned' WHERE reference = $1",
                reference,
            )
            return JSONResponse(status_code=502, content={"error": f"paystack: {e}"})

        return JSONResponse(content={
            "authorization_url": auth_url,
            "reference": reference,
            "amount_usd": amount_usd,
            "amount_zar": amount_zar,
            "fx_rate": rate,
        })

    async def me(self, request: Request) -> JSONResponse:
        uid = request.state.user_id if hasattr(request.state, "user_id") else None
        if not uid:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

        balance_row = await self.pool.fetchrow(
            "SELECT credits_usd FROM cloud_user_balances WHERE user_id = $1",
            uid,
        )
        credits_usd = balance_row["credits_usd"] if balance_row else 0.0

        invoices = await self._load_recent_invoices(uid, 20)
        usage = await self._load_recent_usage(uid, 20)

        return JSONResponse(content={
            "credits_usd": credits_usd,
            "recent_invoices": invoices,
            "recent_usage": usage,
        })

    async def usage(self, request: Request) -> JSONResponse:
        uid = request.state.user_id if hasattr(request.state, "user_id") else None
        if not uid:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

        now = datetime.utcnow()
        default_from = datetime(now.year, now.month, 1)
        default_to = datetime(now.year, now.month + 1, 1) if now.month < 12 else datetime(now.year + 1, 1, 1)

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")

        from_time = self._parse_time_or_default(from_str, default_from)
        to_time = self._parse_time_or_default(to_str, default_to)

        limit = 200
        limit_str = request.query_params.get("limit")
        if limit_str:
            try:
                n = int(limit_str)
                if 0 < n <= 1000:
                    limit = n
            except ValueError:
                pass

        rows = await self.pool.fetch(
            """
            SELECT id, kind, model, input_tokens, output_tokens, bytes_delta,
                   usd_cost, project_id, created_at
            FROM usage_events
            WHERE user_id = $1 AND created_at >= $2 AND created_at < $3
            ORDER BY created_at DESC
            LIMIT $4
            """,
            uid, from_time, to_time, limit,
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

        return JSONResponse(content={"events": events, "from": from_time.isoformat(), "to": to_time.isoformat()})

    async def webhook(self, request: Request) -> JSONResponse:
        body = await request.body()
        sig = request.headers.get("x-paystack-signature", "")

        if not self.paystack or not self.paystack.verify_webhook_signature(body, sig):
            return JSONResponse(status_code=401, content={"error": "invalid signature"})

        try:
            envelope = json.loads(body)
        except Exception:
            return JSONResponse(status_code=400, content={"error": "decode envelope"})

        event = envelope.get("event")
        data = envelope.get("data", {})

        if event == "charge.success":
            try:
                await self._handle_charge_success(data, body)
            except Exception as e:
                logger.error(f"billing/webhook: charge.success: {e}")
                return JSONResponse(status_code=500, content={"error": "processing failed"})
        else:
            logger.info(f"billing/webhook: ignoring event={event}")

        return JSONResponse(content={"status": "ok"})

    async def _handle_charge_success(self, data: dict, raw_body: bytes) -> None:
        from .webhooks import WebhookHandler
        handler = WebhookHandler(self.pool, self.paystack, self.mailer, self.cfg)
        await handler._handle_charge_success(data, raw_body)

    async def _load_recent_invoices(self, user_id: str, limit: int) -> list:
        rows = await self.pool.fetch(
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

    async def _load_recent_usage(self, user_id: str, limit: int) -> list:
        rows = await self.pool.fetch(
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

    def _parse_time_or_default(self, s: Optional[str], default: datetime) -> datetime:
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
