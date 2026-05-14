"""refresh_model_prices: parsing + cheap_tier flagging without a DB.

We stub the asyncpg pool to record the upsert calls.  Real DB integration
lives in tests that exercise migrations end-to-end (out of scope for this
package's hermetic suite).
"""
from __future__ import annotations

from typing import Any

import pytest

from kerf_pricing.litellm_client import ParsedModel
from kerf_pricing.refresh import refresh_model_prices, upsert_models


class _RecordingConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args) -> None:
        self.calls.append((sql, args))

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Tx()


class _RecordingPool:
    def __init__(self) -> None:
        self.conn = _RecordingConn()

    def acquire(self):
        pool = self

        class _Acq:
            async def __aenter__(self_inner):
                return pool.conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Acq()


def _mk(provider: str, model_id: str, in_p: float = 3.0, out_p: float = 15.0):
    return ParsedModel(
        provider=provider,
        model_id=model_id,
        input_per_mtok=in_p,
        output_per_mtok=out_p,
        cache_read_per_mtok=None,
        max_input_tokens=200_000,
        raw={"mode": "chat"},
    )


class TestUpsert:
    async def test_writes_each_model(self):
        pool = _RecordingPool()
        n = await upsert_models(pool, [
            _mk("anthropic", "claude-sonnet-4-7"),
            _mk("openai", "gpt-4o", in_p=2.5, out_p=10.0),
        ])
        assert n == 2
        assert len(pool.conn.calls) == 2

    async def test_cheap_tier_flag_anthropic_sonnet(self):
        pool = _RecordingPool()
        await upsert_models(pool, [_mk("anthropic", "claude-sonnet-4-7")])
        sql, args = pool.conn.calls[0]
        # cheap_tier_eligible is the 7th positional arg (provider, model_id,
        # in, out, cache, max_in, cheap, raw_json)
        assert args[6] is True

    async def test_cheap_tier_flag_openai_not_eligible(self):
        pool = _RecordingPool()
        await upsert_models(pool, [_mk("openai", "gpt-4o", 2.5, 10.0)])
        _, args = pool.conn.calls[0]
        assert args[6] is False

    async def test_empty_list_short_circuits(self):
        pool = _RecordingPool()
        n = await upsert_models(pool, [])
        assert n == 0
        assert pool.conn.calls == []


class TestRefresh:
    async def test_refresh_with_injected_parsed(self):
        # When parsed= is supplied, no HTTP call is attempted — that's how
        # we keep the test hermetic.
        pool = _RecordingPool()
        n = await refresh_model_prices(pool, parsed=[
            _mk("anthropic", "claude-sonnet-4-7"),
            _mk("openai", "gpt-4o-mini", 0.15, 0.60),
        ])
        assert n == 2

    async def test_refresh_fetch_failure_returns_zero(self, monkeypatch):
        async def _boom(*_a, **_k):
            raise RuntimeError("network down")
        monkeypatch.setattr(
            "kerf_pricing.refresh.fetch_and_parse", _boom,
        )
        pool = _RecordingPool()
        n = await refresh_model_prices(pool)
        assert n == 0
