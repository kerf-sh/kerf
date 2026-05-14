"""Bucket-aware ``commit_spend`` — uses a recording pool to assert the SQL
calls each bucket emits.

We DON'T run against a real Postgres in this suite; the migrations are
exercised by the wider integration tests.  Here we verify the wire
shape (correct payer string, correct decrement column, correct order).
"""
from __future__ import annotations

import pytest

from kerf_billing.buckets import Byo, InsufficientCredits, KerfFree, KerfPaid
from kerf_billing.spend import ApiTokenDailyCapExceeded, commit_spend


# ── Minimal asyncpg-pool fake ───────────────────────────────────────────────
class _Conn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetchrows: list[dict] = []
        self.fetchrow_next: list[dict | None] = []
        self.execute_raise_on: dict[int, Exception] = {}

    async def execute(self, sql: str, *args) -> str:
        idx = len(self.executed)
        if idx in self.execute_raise_on:
            raise self.execute_raise_on[idx]
        self.executed.append((sql, args))
        return "UPDATE 1"

    async def fetchrow(self, sql: str, *args):
        self.executed.append((sql, args))
        if self.fetchrow_next:
            return self.fetchrow_next.pop(0)
        return None

    def transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self_inner):
                return outer

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Tx()


class _Pool:
    def __init__(self) -> None:
        self.conn = _Conn()

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Acq()


# ── kerf_free ───────────────────────────────────────────────────────────────
class TestKerfFreeCommit:
    async def test_inserts_usage_then_decrements_quota(self):
        pool = _Pool()
        await commit_spend(
            pool, bucket=KerfFree(),
            user_id="u1", project_id="p1", model="claude-sonnet-4-7",
            input_tokens=500, output_tokens=200,
            cogs_usd=0.005, billed_usd=0.005,
        )
        # First call: usage_events insert with payer='kerf_free'
        sql0, args0 = pool.conn.executed[0]
        assert "INSERT INTO usage_events" in sql0
        assert "'kerf_free'" in sql0
        assert args0 == ("u1", "p1", "claude-sonnet-4-7", 500, 200, 0.005)

        # Second call: decrement free_tokens_*
        sql1, args1 = pool.conn.executed[1]
        assert "free_tokens_in_remaining" in sql1
        assert "free_tokens_out_remaining" in sql1
        assert args1 == ("u1", 500, 200)


# ── byo_<provider> ──────────────────────────────────────────────────────────
class TestByoCommit:
    async def test_records_zero_cost_with_provider_payer(self):
        pool = _Pool()
        await commit_spend(
            pool, bucket=Byo("anthropic"),
            user_id="u1", project_id="p1", model="claude-sonnet-4-7",
            input_tokens=500, output_tokens=200,
            cogs_usd=0.005, billed_usd=0.0,
        )
        assert len(pool.conn.executed) == 1
        sql, args = pool.conn.executed[0]
        assert "INSERT INTO usage_events" in sql
        # payer is a positional arg ($6) — verify the value
        assert "byo_anthropic" in args

    async def test_byo_different_provider(self):
        pool = _Pool()
        await commit_spend(
            pool, bucket=Byo("openai"),
            user_id="u1", project_id=None, model="gpt-4o",
            input_tokens=100, output_tokens=50,
            cogs_usd=0.001, billed_usd=0.0,
        )
        _, args = pool.conn.executed[0]
        assert "byo_openai" in args
        # project_id=None passed through cleanly
        assert args[1] is None


# ── kerf_paid ───────────────────────────────────────────────────────────────
class TestKerfPaidCommit:
    async def test_inserts_debits_and_optionally_caps(self):
        pool = _Pool()
        # api_tokens UPDATE RETURNING — we want it under cap
        pool.conn.fetchrow_next = [{
            "max_spend_per_day_usd": 50.00,
            "spend_today_usd": 0.01,
        }]
        await commit_spend(
            pool, bucket=KerfPaid(),
            user_id="u1", project_id="p1", model="claude-opus-4-7",
            input_tokens=100, output_tokens=100,
            cogs_usd=0.01, billed_usd=0.012,
            api_token_id="tok1",
        )
        # First call: usage_events INSERT
        assert "INSERT INTO usage_events" in pool.conn.executed[0][0]
        assert "'kerf_paid'" in pool.conn.executed[0][0]
        # Then balance debit (INSERT…ON CONFLICT…UPDATE)
        assert "cloud_user_balances" in pool.conn.executed[1][0]
        assert "credits_usd" in pool.conn.executed[1][0]
        # Then api_tokens UPDATE…RETURNING
        assert "api_tokens" in pool.conn.executed[2][0]

    async def test_no_api_token_skips_cap_update(self):
        pool = _Pool()
        await commit_spend(
            pool, bucket=KerfPaid(),
            user_id="u1", project_id=None, model="claude-opus-4-7",
            input_tokens=10, output_tokens=10,
            cogs_usd=0.001, billed_usd=0.0012,
            api_token_id=None,
        )
        # usage_events + balance debit only — no api_tokens update
        assert len(pool.conn.executed) == 2
        assert all("api_tokens" not in s for s, _ in pool.conn.executed)

    async def test_cap_exceeded_raises_after_commit(self):
        pool = _Pool()
        pool.conn.fetchrow_next = [{
            "max_spend_per_day_usd": 1.00,
            "spend_today_usd": 1.50,  # over cap
        }]
        with pytest.raises(ApiTokenDailyCapExceeded) as exc_info:
            await commit_spend(
                pool, bucket=KerfPaid(),
                user_id="u1", project_id=None, model="claude-opus-4-7",
                input_tokens=10, output_tokens=10,
                cogs_usd=0.5, billed_usd=0.6,
                api_token_id="tok1",
            )
        err = exc_info.value
        assert err.token_id == "tok1"
        assert err.cap_usd == 1.0
        assert err.spent_usd == 1.5
        # The row + balance update DID land before the raise
        assert any("INSERT INTO usage_events" in s for s, _ in pool.conn.executed)


# ── InsufficientCredits is a programming-error path ─────────────────────────
class TestInsufficientCredits:
    async def test_raises_value_error(self):
        pool = _Pool()
        with pytest.raises(ValueError):
            await commit_spend(
                pool, bucket=InsufficientCredits(byo_available=False),
                user_id="u1", project_id=None, model="x",
                input_tokens=0, output_tokens=0,
                cogs_usd=0.0, billed_usd=0.0,
            )
