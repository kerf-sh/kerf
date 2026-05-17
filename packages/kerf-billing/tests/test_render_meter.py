"""Verification suite for kerf_billing.render_meter (T-106d).

Covers the GPU-render credit meter: preset cost table, quote_render
(cache-hit / would-charge), and charge_render (cache no-op, Studio free
quota, atomic deduction, insufficient-credits race guard).

A minimal in-memory async pool stands in for asyncpg so the SQL-shaped
control flow is exercised without a database.
"""
from __future__ import annotations

import pytest

from kerf_pricing.render_presets import (
    RENDER_CREDIT_COST,
    RENDER_PRESETS,
    VALID_PRESETS,
)
from kerf_billing.render_meter import (
    UnknownPresetError,
    charge_render,
    quote_render,
)


# ---------------------------------------------------------------------------
# In-memory fake asyncpg pool
# ---------------------------------------------------------------------------


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Conn:
    def __init__(self, state):
        self.s = state

    def transaction(self):
        return _Txn()

    async def fetchrow(self, sql, *args):
        q = " ".join(sql.split())
        if "FROM render_cache" in q:
            return {"x": 1} if args[0] in self.s["cache"] else None
        if "UPDATE cloud_user_balances" in q:
            user, cost = args[0], args[1]
            bal = self.s["balances"].get(user, 0.0)
            if bal >= cost:
                bal -= cost
                self.s["balances"][user] = bal
                return {"credits_usd": bal}
            return None
        if "SELECT credits_usd FROM cloud_user_balances" in q:
            user = args[0]
            if user in self.s["balances"]:
                return {"credits_usd": self.s["balances"][user]}
            return None
        if "UPDATE render_free_quota" in q:
            user = args[0]
            rem = self.s["quota"].get(user, 0)
            if rem > 0:
                rem -= 1
                self.s["quota"][user] = rem
                return {"hero_renders_remaining": rem}
            return None
        raise AssertionError(f"unexpected fetchrow: {q}")

    async def execute(self, sql, *args):
        q = " ".join(sql.split())
        if "INSERT INTO render_free_quota" in q:
            user, seed = args[0], args[1]
            self.s["quota"].setdefault(user, seed)
            return
        if "INSERT INTO render_usage_events" in q:
            self.s["events"].append(
                {
                    "job_id": args[0], "user_id": args[1], "preset": args[2],
                    "gpu_seconds": args[3], "credits_charged": args[4],
                }
            )
            return
        raise AssertionError(f"unexpected execute: {q}")


class _Acquire:
    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return _Conn(self.state)

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, *, balances=None, cache=None, quota=None):
        self.state = {
            "balances": dict(balances or {}),
            "cache": set(cache or ()),
            "quota": dict(quota or {}),
            "events": [],
        }

    def acquire(self):
        return _Acquire(self.state)

    @property
    def events(self):
        return self.state["events"]

    def balance(self, user):
        return self.state["balances"].get(user)


# ---------------------------------------------------------------------------
# render_presets contract
# ---------------------------------------------------------------------------


def test_preset_cost_table():
    assert RENDER_CREDIT_COST == {
        "draft": 0.5, "standard": 2.0, "hero": 10.0, "cinema": 60.0,
    }
    assert VALID_PRESETS == frozenset(RENDER_CREDIT_COST)


def test_preset_info_complete():
    for name, cost in RENDER_CREDIT_COST.items():
        info = RENDER_PRESETS[name]
        assert info["credits"] == cost
        assert info["samples"] > 0
        assert info["description"] and info["resolution"]


# ---------------------------------------------------------------------------
# quote_render
# ---------------------------------------------------------------------------


async def test_quote_unknown_preset_raises():
    with pytest.raises(UnknownPresetError):
        await quote_render(None, "ultrabad", "deadbeef")


async def test_quote_no_cache_key_charges_full():
    q = await quote_render(None, "hero", "abc")
    assert q["credits"] == 10.0
    assert q["cache_hit"] is False
    assert q["would_charge"] is True


async def test_quote_case_insensitive():
    q = await quote_render(None, "HERO", "abc")
    assert q["credits"] == 10.0


async def test_quote_cache_hit_is_free():
    pool = FakePool(cache={"ck-1"})
    q = await quote_render(pool, "hero", "abc", cache_key="ck-1")
    assert q["cache_hit"] is True
    assert q["credits"] == 0.0
    assert q["would_charge"] is False


async def test_quote_cache_miss_charges():
    pool = FakePool(cache={"other"})
    q = await quote_render(pool, "standard", "abc", cache_key="ck-x")
    assert q["cache_hit"] is False
    assert q["credits"] == 2.0


# ---------------------------------------------------------------------------
# charge_render — cache hit
# ---------------------------------------------------------------------------


async def test_charge_cache_hit_no_deduction():
    pool = FakePool(balances={"u1": 100.0}, cache={"ck"})
    res = await charge_render(
        pool, "u1", "job1", "hero", 12.0, cache_key="ck"
    )
    assert res["ok"] is True
    assert res["credits_deducted"] == 0.0
    assert pool.balance("u1") == 100.0
    assert pool.events[-1]["credits_charged"] == 0.0


# ---------------------------------------------------------------------------
# charge_render — Studio free quota
# ---------------------------------------------------------------------------


async def test_charge_studio_free_quota_consumed_before_credits():
    pool = FakePool(balances={"u1": 100.0})
    res = await charge_render(
        pool, "u1", "j1", "hero", 30.0, user_tier="studio"
    )
    assert res["ok"] is True
    assert res["free_quota_used"] is True
    assert res["credits_deducted"] == 0.0
    assert pool.balance("u1") == 100.0  # paid balance untouched


async def test_studio_free_quota_exhausts_then_charges_credits():
    pool = FakePool(balances={"u1": 100.0})
    # 3 free Hero renders/month, then 4th draws credits
    for _ in range(3):
        r = await charge_render(pool, "u1", "j", "hero", 30.0, user_tier="studio")
        assert r["free_quota_used"] is True
    r4 = await charge_render(pool, "u1", "j4", "hero", 30.0, user_tier="studio")
    assert r4["free_quota_used"] is False
    assert r4["credits_deducted"] == 10.0
    assert pool.balance("u1") == 90.0


async def test_non_studio_tier_gets_no_free_quota():
    pool = FakePool(balances={"u1": 100.0})
    res = await charge_render(pool, "u1", "j", "hero", 30.0, user_tier="pro")
    assert res["free_quota_used"] is False
    assert res["credits_deducted"] == 10.0
    assert pool.balance("u1") == 90.0


async def test_studio_free_quota_only_applies_to_hero():
    pool = FakePool(balances={"u1": 100.0})
    res = await charge_render(pool, "u1", "j", "draft", 5.0, user_tier="studio")
    assert res["free_quota_used"] is False
    assert res["credits_deducted"] == 0.5


# ---------------------------------------------------------------------------
# charge_render — atomic paid deduction
# ---------------------------------------------------------------------------


async def test_charge_deducts_and_records_usage():
    pool = FakePool(balances={"u1": 50.0})
    res = await charge_render(pool, "u1", "job9", "standard", 240.0)
    assert res["ok"] is True
    assert res["credits_deducted"] == 2.0
    assert res["new_balance"] == 48.0
    assert pool.events[-1] == {
        "job_id": "job9", "user_id": "u1", "preset": "standard",
        "gpu_seconds": 240.0, "credits_charged": 2.0,
    }


async def test_charge_insufficient_credits_no_deduction():
    pool = FakePool(balances={"u1": 3.0})
    res = await charge_render(pool, "u1", "job1", "hero", 1200.0)
    assert res["ok"] is False
    assert res["reason"] == "insufficient_credits"
    assert res["credits_deducted"] == 0.0
    assert res["need_credits"] == pytest.approx(7.0)
    assert pool.balance("u1") == 3.0  # untouched


async def test_charge_unknown_preset_raises():
    pool = FakePool(balances={"u1": 100.0})
    with pytest.raises(UnknownPresetError):
        await charge_render(pool, "u1", "j", "nope", 1.0)
