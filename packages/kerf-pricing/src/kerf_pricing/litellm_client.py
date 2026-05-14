"""Fetch + parse the LiteLLM ``model_prices_and_context_window.json`` corpus.

The upstream JSON is a flat map of ``"<provider>/<model_id>" | "<model_id>" ->
{mode, litellm_provider, input_cost_per_token, output_cost_per_token,
cache_read_input_token_cost?, max_input_tokens?, ...}``.

We only care about chat models, and we surface costs in **per-Mtok** USD
(easier to display, fewer leading zeros).  Output entries:

    ParsedModel(provider, model_id, input_per_mtok, output_per_mtok,
                cache_read_per_mtok | None, max_input_tokens | None, raw)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpx


logger = logging.getLogger(__name__)


LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# The very first row in the upstream JSON is a `sample_spec` documenting the
# schema, NOT a real model.  Skip it.
_SKIP_KEYS = {"sample_spec"}


@dataclass(frozen=True)
class ParsedModel:
    provider: str
    model_id: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: Optional[float]
    max_input_tokens: Optional[int]
    raw: dict[str, Any]


async def fetch_raw(url: str = LITELLM_URL, *, timeout: float = 30.0) -> dict[str, Any]:
    """GET the upstream JSON.  Raises on transport failure or non-200."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _to_per_mtok(per_token_cost: Any) -> Optional[float]:
    """Convert a per-token cost (float) to per-Mtok.

    Returns None for missing / non-numeric / negative values so the caller
    can drop the row from the upsert.
    """
    if per_token_cost is None:
        return None
    try:
        v = float(per_token_cost)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    return v * 1_000_000.0


def _split_provider_model(key: str, entry: dict[str, Any]) -> tuple[str, str]:
    """Resolve the (provider, model_id) for a top-level JSON key.

    Strategy:
    - prefer the explicit ``litellm_provider`` field if present
    - else, if the key contains "/", split on the first one — left side is the
      provider, right side is the model id (LiteLLM canonical form)
    - else, fall back to provider="" and key as-is
    """
    provider = (entry.get("litellm_provider") or "").strip()
    if "/" in key:
        prefix, _, suffix = key.partition("/")
        if not provider:
            provider = prefix
        return provider, suffix
    return provider, key


def parse_models(raw: dict[str, Any]) -> list[ParsedModel]:
    """Filter to chat-mode entries and convert per-token → per-Mtok."""
    out: list[ParsedModel] = []
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        if key in _SKIP_KEYS:
            continue
        mode = entry.get("mode")
        if mode != "chat":
            continue
        in_per_mtok = _to_per_mtok(entry.get("input_cost_per_token"))
        out_per_mtok = _to_per_mtok(entry.get("output_cost_per_token"))
        if in_per_mtok is None or out_per_mtok is None:
            continue

        provider, model_id = _split_provider_model(key, entry)
        if not provider or not model_id:
            continue

        cache_read = _to_per_mtok(entry.get("cache_read_input_token_cost"))

        max_in = entry.get("max_input_tokens") or entry.get("max_tokens")
        try:
            max_in_int = int(max_in) if max_in is not None else None
        except (TypeError, ValueError):
            max_in_int = None

        out.append(
            ParsedModel(
                provider=provider,
                model_id=model_id,
                input_per_mtok=in_per_mtok,
                output_per_mtok=out_per_mtok,
                cache_read_per_mtok=cache_read,
                max_input_tokens=max_in_int,
                raw=entry,
            )
        )
    return out


async def fetch_and_parse(url: str = LITELLM_URL) -> list[ParsedModel]:
    """Convenience: fetch + parse in one call."""
    raw = await fetch_raw(url)
    return parse_models(raw)
