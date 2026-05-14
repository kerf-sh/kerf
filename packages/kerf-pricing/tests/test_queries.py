"""Pure tests for ModelPrice.compute_cost_usd + UnknownModelError shape."""
from __future__ import annotations

import pytest

from kerf_pricing.queries import ModelPrice, UnknownModelError


def _mk(input_per_mtok=3.0, output_per_mtok=15.0, cache=None):
    return ModelPrice(
        provider="anthropic",
        model_id="claude-sonnet-4-7",
        input_per_mtok=input_per_mtok,
        output_per_mtok=output_per_mtok,
        cache_read_per_mtok=cache,
        max_input_tokens=200_000,
        cheap_tier_eligible=True,
    )


class TestCompute:
    def test_zero_tokens(self):
        assert _mk().compute_cost_usd(0, 0) == 0.0

    def test_input_only(self):
        # 1Mtok input @ $3 → $3
        assert _mk().compute_cost_usd(1_000_000, 0) == pytest.approx(3.0)

    def test_output_only(self):
        # 1Mtok output @ $15 → $15
        assert _mk().compute_cost_usd(0, 1_000_000) == pytest.approx(15.0)

    def test_mixed(self):
        # 100k in + 50k out: 100/1000 * 3 + 50/1000 * 15 = 0.3 + 0.75 = 1.05
        assert _mk().compute_cost_usd(100_000, 50_000) == pytest.approx(1.05)

    def test_cache_discount_applied(self):
        # 1Mtok input, all cached, cache @ $0.30
        cost = _mk(cache=0.30).compute_cost_usd(1_000_000, 0, cached_input_tokens=1_000_000)
        assert cost == pytest.approx(0.30)

    def test_cache_partial(self):
        # 1Mtok input, half cached.  Half @ $3 + half @ $0.30 = 1.5 + 0.15 = 1.65
        cost = _mk(cache=0.30).compute_cost_usd(1_000_000, 0, cached_input_tokens=500_000)
        assert cost == pytest.approx(1.65)

    def test_cache_none_falls_back_to_input(self):
        # When cache_read_per_mtok is None, cached tokens cost the same as
        # uncached.  This is conservative — we'd rather over-charge a tiny
        # amount than have the math blow up on a None.
        cost = _mk(cache=None).compute_cost_usd(1_000_000, 0, cached_input_tokens=1_000_000)
        assert cost == pytest.approx(3.0)

    def test_cached_above_input_clamped(self):
        # If the caller passes cached_input_tokens > input_tokens, we clamp.
        cost = _mk(cache=0.30).compute_cost_usd(100_000, 0, cached_input_tokens=500_000)
        # All 100k get the cache rate: 100/1000 * 0.30 = 0.03
        assert cost == pytest.approx(0.03)

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            _mk().compute_cost_usd(-1, 0)
        with pytest.raises(ValueError):
            _mk().compute_cost_usd(0, -1)
        with pytest.raises(ValueError):
            _mk().compute_cost_usd(100, 0, cached_input_tokens=-1)


class TestUnknownModelError:
    def test_carries_provider_and_model(self):
        err = UnknownModelError("openai", "gpt-99")
        assert err.provider == "openai"
        assert err.model_id == "gpt-99"
        assert "openai" in str(err)
        assert "gpt-99" in str(err)
