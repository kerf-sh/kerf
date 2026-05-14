import json
from typing import Self

import httpx

from .service import (
    Credentials,
    Message,
    Provider,
    ProviderResend,
    ErrInvalidCredentials,
)


class ResendProvider(Provider):
    def __init__(self, api_key: str, from_addr: str):
        self._api_key = api_key
        self._from = from_addr
        self._client = httpx.Client(timeout=15.0)

    @classmethod
    def from_credentials(cls, creds: Credentials) -> Self:
        if not creds.api_key:
            raise ErrInvalidCredentials("resend: api_key is required")
        if not creds.from_email:
            raise ErrInvalidCredentials("resend: from_email is required")

        from_addr = creds.from_email
        if creds.from_name:
            from_addr = f"{creds.from_name} <{creds.from_email}>"

        return cls(api_key=creds.api_key, from_addr=from_addr)

    def name(self) -> str:
        return ProviderResend

    def send(self, msg: Message) -> bool:
        from_addr = msg.From or self._from

        tags = [{"name": k, "value": v} for k, v in (msg.Tags or {}).items()]

        body = {
            "from": from_addr,
            "to": [msg.To],
            "subject": msg.Subject,
            "html": msg.HTML,
            "text": msg.Text,
            "reply_to": msg.ReplyTo or None,
            "tags": tags or None,
        }

        raw = json.dumps(body).encode()

        req = self._client.build_request(
            "POST",
            "https://api.resend.com/emails",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        resp = self._client.send(req)
        resp.raise_for_status()

        return True
