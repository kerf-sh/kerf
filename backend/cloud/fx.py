import os
import json
import httpx
import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Optional


class Fetcher:
    def __init__(self, cfg, pool):
        self.pool = pool
        self.cfg = cfg
        self.http = httpx.Client(timeout=10.0)
        self._cache: dict[str, "CachedRate"] = {}
        self._cache_ttl_seconds = 60

    async def refresh(self) -> None:
        url = self.cfg.cloud_fx_refresh_url
        if not url:
            raise ValueError("fx: refresh url not configured")

        resp = self.http.get(url)
        if resp.status_code != 200:
            raise Exception(f"fx: provider returned {resp.status_code}")

        body = resp.json()
        if body.get("success") is False:
            raise Exception("fx: provider reported success=false")

        base = body.get("base") or self.cfg.cloud_fx_base_currency
        target = self.cfg.cloud_fx_settlement_currency
        rates = body.get("rates", {})
        rate = rates.get(target)
        if not rate or rate <= 0:
            raise Exception(f"fx: no {target} rate in response")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cloud_fx_rates(base_currency, target_currency, rate)
                VALUES ($1, $2, $3)
                """,
                base, target, rate,
            )

        self._cache[f"{base}/{target}"] = CachedRate(
            rate=rate,
            as_of=datetime.now(timezone.utc),
            cached_at=datetime.now(timezone.utc),
        )

    async def rate(self, base: str, target: str) -> tuple[float, datetime, bool]:
        key = f"{base}/{target}"
        now = datetime.now(timezone.utc)

        if key in self._cache:
            c = self._cache[key]
            if (now - c.cached_at) < timedelta(seconds=self._cache_ttl_seconds):
                return c.rate, c.as_of, True

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT rate, fetched_at FROM cloud_fx_rates
                WHERE base_currency = $1 AND target_currency = $2
                ORDER BY fetched_at DESC LIMIT 1
                """,
                base, target,
            )
            if not row:
                return 0.0, datetime.now(timezone.utc), False

            self._cache[key] = CachedRate(
                rate=row["rate"],
                as_of=row["fetched_at"].replace(tzinfo=timezone.utc) if row["fetched_at"] else datetime.now(timezone.utc),
                cached_at=datetime.now(timezone.utc),
            )
            return row["rate"], row["fetched_at"], True

    async def rate_with_spread(self, base: str, target: str, spread_pct: float) -> tuple[float, datetime, bool]:
        r, as_of, ok = await self.rate(base, target)
        if not ok:
            return 0.0, as_of, False
        return r * (1.0 + spread_pct / 100.0), as_of, True


class CachedRate:
    def __init__(self, rate: float, as_of: datetime, cached_at: datetime):
        self.rate = rate
        self.as_of = as_of
        self.cached_at = cached_at
