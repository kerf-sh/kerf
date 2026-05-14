import json
import logging
from datetime import datetime
from typing import Optional


logger = logging.getLogger(__name__)


class WebhookHandler:
    def __init__(self, pool, paystack_client, mailer=None, cfg=None):
        self.pool = pool
        self.paystack = paystack_client
        self.mailer = mailer
        self.cfg = cfg

    async def handle(self, body: bytes, signature: str) -> dict:
        if not self.paystack.verify_webhook_signature(body, signature):
            raise PermissionError("invalid signature")

        envelope = json.loads(body)
        event = envelope.get("event")
        data = envelope.get("data", {})

        if event == "charge.success":
            await self._handle_charge_success(data, body)
        else:
            logger.info(f"billing/webhook: ignoring event={event}")

        return {"status": "ok"}

    async def _handle_charge_success(self, data: dict, raw_body: bytes) -> None:
        reference = data.get("reference")
        if not reference:
            raise ValueError("missing reference")

        async with self.pool.acquire() as conn:
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
                    logger.info(f"billing/webhook: unknown reference {reference} — acking")
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

        if self.mailer:
            user_email_row = await self.pool.fetchrow(
                "SELECT email FROM users WHERE id = $1",
                row["user_id"],
            )
            recipient = user_email_row["email"] if user_email_row else data.get("customer", {}).get("email", "")
            if recipient:
                try:
                    await self.mailer.send_template(
                        "billing_receipt",
                        recipient,
                        row["user_id"],
                        {
                            "AmountUSD": row["amount_usd"],
                            "AmountZAR": row["amount_zar"],
                            "FXRate": row["fx_rate"],
                            "TxID": reference,
                            "AppURL": self.cfg.cors_origin if self.cfg else "",
                        },
                    )
                except Exception as e:
                    logger.warning(f"billing/webhook: queue receipt: {e}")
