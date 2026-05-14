import asyncio
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from distributors.service import (
    PROVIDER_LCSC,
    Credentials,
    DistributorNotFound,
    DistributorPart,
    Service,
)


LCSC_BASE = "https://wmsc.lcsc.com"


class LCSCService(Service):
    def __init__(self, creds: Credentials, timeout: float = 10.0, fx=None):
        self._api_key = creds.api_key
        self._timeout = timeout
        self._fx = fx

    def name(self) -> str:
        return PROVIDER_LCSC

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

        timeout = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self._timeout))
        params = {
            "keyword": query,
            "currentPage": "1",
            "pageSize": str(limit),
        }

        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-LCSC-API-Key"] = self._api_key

        url = f"{LCSC_BASE}/search/global?{urllib.parse.urlencode(params)}"

        async with timeout.get(url, headers=headers) as resp:
            resp_body = await resp.text()

            if resp.status != 200:
                raise Exception(f"lcsc: status {resp.status}: {resp_body[:200]}")

            try:
                sr = json.loads(resp_body)
            except json.JSONDecodeError as e:
                raise Exception(f"lcsc decode: {e}")

        products = sr.get("result", {}).get("productList", [])
        results = []
        for p in products:
            price_cny = 0.0
            price_list = p.get("productPriceList", [])
            for pb in price_list:
                if pb.get("ladderLevel") == 1:
                    price_cny = pb.get("productPrice", 0.0)
                    break
            if price_cny == 0 and price_list:
                price_cny = price_list[0].get("productPrice", 0.0)

            price_usd = None
            if price_cny > 0 and self._fx is not None:
                try:
                    rate_val, _, ok = await self._fx.rate("CNY", "USD")
                    if ok and rate_val > 0:
                        price_usd = price_cny * rate_val
                except Exception:
                    pass

            stock = None
            if p.get("stockNumber", 0) > 0:
                stock = p["stockNumber"]

            raw_data = {"price_cny": price_cny, "product": p.get("productCode", "")}

            results.append(
                DistributorPart(
                    name=PROVIDER_LCSC,
                    sku=p.get("productCode", ""),
                    url=p.get("productUrl", ""),
                    price_usd=price_usd,
                    stock=stock,
                    fetched_at=datetime.now(timezone.utc),
                    raw=raw_data,
                )
            )

        return results
