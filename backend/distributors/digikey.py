import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from distributors.service import (
    PROVIDER_DIGIKEY,
    Credentials,
    DistributorAuthError,
    DistributorNotFound,
    DistributorPart,
    Service,
)


DIGIKEY_BASE = "https://api.digikey.com"
DIGIKEY_TOKEN_URL = DIGIKEY_BASE + "/v1/oauth2/token"
DIGIKEY_SEARCH = DIGIKEY_BASE + "/Search/v3/Products/Keyword"


class DigiKeyService(Service):
    def __init__(self, creds: Credentials, timeout: float = 10.0):
        self._client_id = creds.client_id
        self._client_secret = creds.client_secret
        self._token = ""
        self._token_exp = datetime.min
        self._token_error: Optional[Exception] = None
        self._lock = asyncio.Lock()
        self._timeout = timeout

    def name(self) -> str:
        return PROVIDER_DIGIKEY

    async def _ensure_token(self, session: aiohttp.ClientSession) -> str:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._token and now < self._token_exp:
                return self._token
            if self._token_error and now < self._token_exp:
                raise self._token_error

        form = aiohttp.FormData()
        form.add_field("client_id", self._client_id)
        form.add_field("client_secret", self._client_secret)
        form.add_field("grant_type", "client_credentials")

        async with session.post(
            DIGIKEY_TOKEN_URL,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                self._token_error = DistributorAuthError(
                    f"digikey token: status {resp.status}: {body[:200]}"
                )
                self._token_exp = datetime.now(timezone.utc).replace(microsecond=0)
                raise self._token_error

            try:
                tr = json.loads(body)
            except json.JSONDecodeError as e:
                self._token_error = e
                self._token_exp = datetime.now(timezone.utc).replace(microsecond=0)
                raise

            access_token = tr.get("access_token", "")
            if not access_token:
                self._token_error = Exception("digikey token: empty access_token")
                self._token_exp = datetime.now(timezone.utc).replace(microsecond=0)
                raise self._token_error

            expires_in = tr.get("expires_in", 3600)
            if expires_in <= 60:
                expires_in = 600

            async with self._lock:
                self._token = access_token
                self._token_exp = datetime.now(timezone.utc).replace(microsecond=0)
                import time as time_module

                self._token_exp = datetime.fromtimestamp(
                    datetime.now(timezone.utc).timestamp() + expires_in - 60,
                    tz=timezone.utc,
                )
                self._token_error = None

            return access_token

    async def lookup(self, ctx, sku: str) -> DistributorPart:
        if not sku:
            raise DistributorNotFound("empty SKU")
        results = await self.search(ctx, sku, 1)
        if not results:
            raise DistributorNotFound(f"no result for SKU: {sku}")
        return results[0]

    async def search(self, ctx, query: str, limit: int) -> list[DistributorPart]:
        if not query:
            return []
        if limit <= 0 or limit > 25:
            limit = 10

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                token = await self._ensure_token(session)
            except Exception:
                raise

            body = json.dumps(
                {
                    "Keywords": query,
                    "RecordCount": limit,
                    "RecordStartPosition": 0,
                }
            )

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Client-Id": self._client_id,
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en",
                "X-DIGIKEY-Locale-Currency": "USD",
            }

            async with session.post(DIGIKEY_SEARCH, data=body, headers=headers) as resp:
                resp_body = await resp.text()

                if resp.status in (401, 403):
                    async with self._lock:
                        self._token = ""
                        self._token_exp = datetime.min
                    raise DistributorAuthError(f"digikey search: {resp.status}")

                if resp.status != 200:
                    raise Exception(f"digikey search: status {resp.status}: {resp_body[:200]}")

                try:
                    sr = json.loads(resp_body)
                except json.JSONDecodeError as e:
                    raise Exception(f"digikey search decode: {e}")

        products = sr.get("Products", [])
        results = []
        for p in products:
            price = None
            if p.get("UnitPrice", 0) > 0:
                price = p["UnitPrice"]

            stock = None
            if p.get("QuantityAvailable", 0) >= 0:
                stock = p["QuantityAvailable"]

            results.append(
                DistributorPart(
                    name=PROVIDER_DIGIKEY,
                    sku=p.get("DigiKeyPartNumber", ""),
                    url=p.get("ProductUrl", ""),
                    price_usd=price,
                    stock=stock,
                    fetched_at=datetime.now(timezone.utc),
                )
            )

        return results
