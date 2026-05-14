import os
import hmac
import hashlib
import hexdump
import json
import httpx
from typing import Optional
from datetime import datetime


class PaystackClient:
    def __init__(self, secret_key: str, public_key: str = "", webhook_secret: str = ""):
        self.secret_key = secret_key
        self.public_key = public_key
        self.webhook_secret = webhook_secret or secret_key
        self.base_url = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
        self.http = httpx.Client(timeout=15.0)

    def secret_key_(self) -> str:
        return self.secret_key

    def initialize_transaction(
        self,
        email: str,
        amount_zarcents: int,
        reference: str,
        callback_url: str = "",
    ) -> tuple[str, str]:
        payload = {
            "email": email,
            "amount": amount_zarcents,
            "currency": "ZAR",
            "reference": reference,
        }
        if callback_url:
            payload["callback_url"] = callback_url

        resp = self.http.post(
            f"{self.base_url}/transaction/initialize",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code // 100 != 2:
            raise Exception(f"paystack initialize: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if not data.get("status"):
            raise Exception(f"paystack initialize: {data.get('message')}")

        return data["data"]["authorization_url"], data["data"]["access_code"]

    def verify_transaction(self, reference: str) -> dict:
        resp = self.http.get(
            f"{self.base_url}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {self.secret_key}"},
        )
        if resp.status_code // 100 != 2:
            raise Exception(f"paystack verify: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if not data.get("status"):
            raise Exception(f"paystack verify: {data.get('message')}")

        result = {
            "reference": data["data"]["reference"],
            "status": data["data"]["status"],
            "amount_minor": data["data"]["amount"],
            "currency": data["data"]["currency"],
            "customer_email": data["data"]["customer"]["email"],
            "customer_code": data["data"]["customer"]["customer_code"],
            "customer_id": data["data"]["customer"]["id"],
        }

        if data["data"].get("paid_at"):
            result["paid_at"] = data["data"]["paid_at"]

        return result

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not self.webhook_secret:
            return False
        mac = hmac.new(
            self.webhook_secret.encode(),
            body,
            hashlib.sha512,
        )
        expected = mac.hexdigest()
        return hmac.compare_digest(expected, signature)

    def create_subscription(self, customer_email: str, plan_code: str) -> dict:
        payload = {
            "customer": customer_email,
            "plan": plan_code,
        }
        resp = self.http.post(
            f"{self.base_url}/subscription",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code // 100 != 2:
            raise Exception(f"paystack create_subscription: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if not data.get("status"):
            raise Exception(f"paystack create_subscription: {data.get('message')}")

        return data["data"]

    def cancel_subscription(self, subscription_code: str) -> dict:
        resp = self.http.post(
            f"{self.base_url}/subscription/disable",
            json={"code": subscription_code},
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code // 100 != 2:
            raise Exception(f"paystack cancel_subscription: HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        return data["data"]
