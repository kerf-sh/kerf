"""Read-side helpers for the ``model_prices`` table.

The chat handler resolves a (provider, model_id) → ModelPrice and asks the
ModelPrice to compute the COGS for a given token count.  Markup is applied
by the caller, NOT here — keeping the COGS calculation a pure function of
provider price + tokens makes the bucket logic easier to test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


class UnknownModelError(Exception):
    """Raised by ``get_price`` when (provider, model_id) is not in the table.

    The chat handler maps this to a 400 with a clear message telling the user
    the model isn't priced yet — we refuse to silently fall back to a median
    rate (which is what the old hardcoded code did, and it was wrong).
    """

    def __init__(self, provider: str, model_id: str):
        super().__init__(
            f"model {provider!r}/{model_id!r} not present in model_prices table"
        )
        self.provider = provider
        self.model_id = model_id


@dataclass(frozen=True)
class ModelPrice:
    """One row of ``model_prices`` exposed as a typed dataclass."""

    provider: str
    model_id: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: Optional[float]
    max_input_tokens: Optional[int]
    cheap_tier_eligible: bool

    def compute_cost_usd(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        """Provider COGS in USD, BEFORE any Kerf markup.

        ``cached_input_tokens`` should be **a subset of** input_tokens; the
        cached half is priced at the cache-read rate if known, else at the
        regular input rate.  The remaining (input - cached) tokens are priced
        at the regular input rate.
        """
        if input_tokens < 0 or output_tokens < 0 or cached_input_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if cached_input_tokens > input_tokens:
            cached_input_tokens = input_tokens
        uncached_in = input_tokens - cached_input_tokens
        cache_rate = (
            self.cache_read_per_mtok
            if self.cache_read_per_mtok is not None
            else self.input_per_mtok
        )
        total = 0.0
        total += (uncached_in / 1_000_000.0) * self.input_per_mtok
        total += (cached_input_tokens / 1_000_000.0) * cache_rate
        total += (output_tokens / 1_000_000.0) * self.output_per_mtok
        return total


async def get_price(pool, provider: str, model_id: str) -> Optional[ModelPrice]:
    """Return the ModelPrice for (provider, model_id), or None if absent.

    NOTE: returns None on miss (does NOT raise).  Callers that want the
    raise-on-miss semantic should use ``require_price`` instead.
    """
    if not provider or not model_id:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT provider, model_id, input_per_mtok, output_per_mtok,
                   cache_read_per_mtok, max_input_tokens, cheap_tier_eligible
            FROM model_prices
            WHERE provider = $1 AND model_id = $2
            """,
            provider, model_id,
        )
        if not row:
            return None
        return ModelPrice(
            provider=row["provider"],
            model_id=row["model_id"],
            input_per_mtok=float(row["input_per_mtok"]),
            output_per_mtok=float(row["output_per_mtok"]),
            cache_read_per_mtok=(
                float(row["cache_read_per_mtok"])
                if row["cache_read_per_mtok"] is not None else None
            ),
            max_input_tokens=row["max_input_tokens"],
            cheap_tier_eligible=bool(row["cheap_tier_eligible"]),
        )


async def require_price(pool, provider: str, model_id: str) -> ModelPrice:
    """Like ``get_price`` but raises ``UnknownModelError`` on miss."""
    price = await get_price(pool, provider, model_id)
    if price is None:
        raise UnknownModelError(provider, model_id)
    return price


async def list_all_prices(pool) -> list[dict[str, Any]]:
    """Return every model_prices row as a JSON-friendly dict — admin surface."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT provider, model_id, input_per_mtok, output_per_mtok,
                   cache_read_per_mtok, max_input_tokens, cheap_tier_eligible,
                   fetched_at
            FROM model_prices
            ORDER BY provider, model_id
            """
        )
    out = []
    for r in rows:
        out.append({
            "provider": r["provider"],
            "model_id": r["model_id"],
            "input_per_mtok": float(r["input_per_mtok"]),
            "output_per_mtok": float(r["output_per_mtok"]),
            "cache_read_per_mtok": (
                float(r["cache_read_per_mtok"])
                if r["cache_read_per_mtok"] is not None else None
            ),
            "max_input_tokens": r["max_input_tokens"],
            "cheap_tier_eligible": bool(r["cheap_tier_eligible"]),
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        })
    return out
