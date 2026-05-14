import asyncio
import json
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from distributors.service import (
    PROVIDER_MOUSER,
    Credentials,
    DistributorNotFound,
    DistributorPart,
    Service,
)


MOUSER_BASE = "https://api.mouser.com"


class MouserService(Service):
    def __init__(self, creds: Credentials, timeout: float = 10.0):
        self._api_key = creds.api_key
        self._timeout = timeout

    def name(self) -> str:
        return PROVIDER_MOUSER

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
        if limit <= 0 or limit > 50:
            limit = 10

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            body = json.dumps(
                {
                    "SearchByKeywordRequest": {
                        "keyword": query,
                        "records": limit,
                        "startingRecord": 0,
                    }
                }
            )

            url = f"{MOUSER_BASE}/api/v1/search/keyword?apiKey={self._api_key}"

            async with session.post(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}) as resp:
                resp_body = await resp.text()

                if resp.status != 200:
                    raise Exception(f"mouser search: status {resp.status}: {resp_body[:200]}")

                try:
                    sr = json.loads(resp_body)
                except json.JSONDecodeError as e:
                    raise Exception(f"mouser decode: {e}")

        errors = sr.get("Errors")
        if errors and len(errors) > 0:
            first = errors[0]
            raise Exception(f"mouser error: {first.get('Code', '')} {first.get('Message', '')}")

        parts = sr.get("SearchResults", {}).get("Parts", [])
        results = []
        for p in parts:
            price = self._parse_price(p.get("PriceBreaks", []))
            price_usd = price if price > 0 else None

            stock = None
            avail = p.get("Availability", "")
            try:
                stock = int(avail) if avail else None
            except ValueError:
                pass

            results.append(
                DistributorPart(
                    name=PROVIDER_MOUSER,
                    sku=p.get("MouserPartNumber", ""),
                    url=p.get("ProductDetailUrl", ""),
                    price_usd=price_usd,
                    stock=stock,
                    fetched_at=datetime.now(timezone.utc),
                )
            )

            if len(results) >= limit:
                break

        return results

    def _parse_price(self, breaks: list) -> float:
        for b in breaks:
            s = b.get("Price", "").strip()
            s = s.lstrip("$")
            s = s.replace(",", "")
            sp = s.split(" ")
            if len(sp) > 0:
                s = sp[0]
            try:
                v = float(s)
                if v > 0:
                    return v
            except ValueError:
                continue
        return 0.0


from distributors.service import Credentials
