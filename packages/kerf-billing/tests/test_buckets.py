"""Pure selector tests — no DB, no provider, no HTTP."""
from __future__ import annotations

import pytest

from kerf_billing.buckets import (
    Bucket,
    Byo,
    InsufficientCredits,
    KerfFree,
    KerfPaid,
    ModelInfo,
    UserBilling,
    pick_bucket,
)


def _user(
    credits=10.0, free_in=100_000, free_out=20_000,
    prefer_byo=False, byo=(),
):
    return UserBilling(
        user_id="u1",
        prefer_byo=prefer_byo,
        credits_usd=credits,
        free_tokens_in_remaining=free_in,
        free_tokens_out_remaining=free_out,
        byo_providers=frozenset(byo),
    )


def _model(provider="anthropic", model_id="claude-sonnet-4-7", cheap=True):
    return ModelInfo(provider=provider, model_id=model_id, cheap_tier_eligible=cheap)


# ── Order #1: BYO wins when toggle is on AND key is present ─────────────────
class TestByoPreference:
    def test_byo_chosen_when_toggle_on(self):
        u = _user(prefer_byo=True, byo=["anthropic"])
        m = _model()
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, Byo)
        assert b.provider == "anthropic"

    def test_byo_not_chosen_without_key(self):
        u = _user(prefer_byo=True, byo=["openai"])  # Anthropic key missing
        m = _model(provider="anthropic")
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        # No anthropic key → falls through to free tier (model is cheap)
        assert isinstance(b, KerfFree)

    def test_byo_not_chosen_when_toggle_off(self):
        u = _user(prefer_byo=False, byo=["anthropic"])
        m = _model()
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        # Key present but toggle off — paid path preferred over BYO.
        # Cheap-tier-eligible model + has free quota → free tier wins.
        assert isinstance(b, KerfFree)


# ── Order #2: Free tier ─────────────────────────────────────────────────────
class TestFreeTier:
    def test_cheap_model_with_quota_picks_free(self):
        u = _user()
        m = _model(cheap=True)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, KerfFree)

    def test_non_cheap_model_skips_free(self):
        u = _user()
        m = _model(cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        # Falls through to paid (credits = $10)
        assert isinstance(b, KerfPaid)

    def test_no_input_quota_skips_free(self):
        u = _user(free_in=0)
        m = _model(cheap=True)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, KerfPaid)

    def test_no_output_quota_skips_free(self):
        u = _user(free_out=0)
        m = _model(cheap=True)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, KerfPaid)

    def test_free_blocked_by_estimate_under_quota(self):
        # If estimate fits, free is fine — confirms the gating
        u = _user(free_in=2_000, free_out=2_000)
        m = _model(cheap=True)
        b = pick_bucket(
            u, m, estimated_cost_usd=0.0,
            estimated_input_tokens=1_000, estimated_output_tokens=1_000,
        )
        assert isinstance(b, KerfFree)

    def test_free_blocked_by_oversize_estimate(self):
        u = _user(free_in=500, free_out=500)
        m = _model(cheap=True)
        b = pick_bucket(
            u, m, estimated_cost_usd=0.0,
            estimated_input_tokens=10_000, estimated_output_tokens=10_000,
        )
        # Estimate exceeds remaining quota → falls through to paid
        assert isinstance(b, KerfPaid)


# ── Order #3: Paid ──────────────────────────────────────────────────────────
class TestPaidTier:
    def test_paid_picks_when_credits_cover(self):
        u = _user(credits=5.0, free_in=0)  # no free, has credits
        m = _model(cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.5)
        assert isinstance(b, KerfPaid)

    def test_paid_exact_equal_credits_covers(self):
        u = _user(credits=0.5, free_in=0)
        m = _model(cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.5)
        assert isinstance(b, KerfPaid)


# ── Order #4: InsufficientCredits ───────────────────────────────────────────
class TestInsufficient:
    def test_no_credits_no_byo_returns_no_byo_variant(self):
        u = _user(credits=0.0, free_in=0)
        m = _model(cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, InsufficientCredits)
        assert b.byo_available is False

    def test_no_credits_with_byo_returns_byo_variant(self):
        u = _user(credits=0.0, free_in=0, byo=["anthropic"])
        m = _model(provider="anthropic", cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, InsufficientCredits)
        assert b.byo_available is True

    def test_no_credits_byo_wrong_provider(self):
        u = _user(credits=0.0, free_in=0, byo=["openai"])
        m = _model(provider="anthropic", cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.01)
        assert isinstance(b, InsufficientCredits)
        # User has BYO for openai but the request is anthropic → no BYO
        # fallback available for THIS provider
        assert b.byo_available is False

    def test_credits_below_estimate_with_byo_offers_byo(self):
        u = _user(credits=0.001, free_in=0, byo=["anthropic"])
        m = _model(provider="anthropic", cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=1.0)
        assert isinstance(b, InsufficientCredits)
        assert b.byo_available is True


# ── End-to-end ordering ─────────────────────────────────────────────────────
class TestOrdering:
    def test_byo_beats_free(self):
        # User has BYO toggle on + key + free quota + credits.  BYO wins.
        u = _user(prefer_byo=True, byo=["anthropic"], credits=10.0)
        m = _model(provider="anthropic", cheap=True)
        b = pick_bucket(u, m, estimated_cost_usd=0.001)
        assert isinstance(b, Byo)

    def test_free_beats_paid(self):
        # Cheap model + free quota + credits.  Free wins.
        u = _user(credits=10.0, free_in=100_000, free_out=20_000)
        m = _model(cheap=True)
        b = pick_bucket(u, m, estimated_cost_usd=0.001)
        assert isinstance(b, KerfFree)

    def test_paid_beats_402(self):
        u = _user(credits=10.0, free_in=0)
        m = _model(cheap=False)
        b = pick_bucket(u, m, estimated_cost_usd=0.001)
        assert isinstance(b, KerfPaid)
