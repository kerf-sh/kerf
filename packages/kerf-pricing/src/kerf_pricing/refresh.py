"""Daily refresh job: pull LiteLLM JSON → upsert ``model_prices``.

Idempotent, race-tolerant (uses ON CONFLICT).  The worker harness calls
``refresh_model_prices`` on a 24h cadence + once at boot.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from kerf_pricing.cheap_tier import is_cheap_tier
from kerf_pricing.litellm_client import (
    LITELLM_URL,
    ParsedModel,
    fetch_and_parse,
)


logger = logging.getLogger(__name__)


async def upsert_models(pool, models: list[ParsedModel]) -> int:
    """Upsert a batch of parsed models.  Returns the number of rows written.

    ``cheap_tier_eligible`` is computed from the cheap_tier allow-list at
    upsert time (NOT from the upstream JSON — LiteLLM has no notion of
    "our free tier"; that's a Kerf product decision).
    """
    if not models:
        return 0
    written = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for m in models:
                cheap = is_cheap_tier(m.provider, m.model_id)
                await conn.execute(
                    """
                    INSERT INTO model_prices
                        (provider, model_id, input_per_mtok, output_per_mtok,
                         cache_read_per_mtok, max_input_tokens,
                         cheap_tier_eligible, raw_json, fetched_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, now())
                    ON CONFLICT (provider, model_id) DO UPDATE SET
                        input_per_mtok      = excluded.input_per_mtok,
                        output_per_mtok     = excluded.output_per_mtok,
                        cache_read_per_mtok = excluded.cache_read_per_mtok,
                        max_input_tokens    = excluded.max_input_tokens,
                        cheap_tier_eligible = excluded.cheap_tier_eligible,
                        raw_json            = excluded.raw_json,
                        fetched_at          = excluded.fetched_at
                    """,
                    m.provider,
                    m.model_id,
                    m.input_per_mtok,
                    m.output_per_mtok,
                    m.cache_read_per_mtok,
                    m.max_input_tokens,
                    cheap,
                    json.dumps(m.raw),
                )
                written += 1
    return written


async def refresh_model_prices(
    pool,
    *,
    url: str = LITELLM_URL,
    parsed: Optional[list[ParsedModel]] = None,
) -> int:
    """Fetch the LiteLLM JSON, parse, upsert.

    Returns the number of rows upserted.  ``parsed`` is an injection point
    for tests so they can skip the HTTP call.
    """
    if parsed is None:
        try:
            parsed = await fetch_and_parse(url)
        except Exception as exc:
            logger.warning("pricing.refresh fetch_failed url=%s err=%s", url, exc)
            return 0

    n = await upsert_models(pool, parsed)
    logger.info("pricing.refresh ok models=%d", n)
    return n
