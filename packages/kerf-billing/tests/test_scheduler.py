"""Scheduler helpers — pure SQL emission tests."""
from __future__ import annotations

import pytest

from kerf_billing.scheduler import (
    BillingResetWorker,
    reset_api_token_daily,
    reset_free_quotas,
)


class _Conn:
    def __init__(self, response: str = "UPDATE 0") -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.response = response

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql, args))
        return self.response


class _Pool:
    def __init__(self, response: str = "UPDATE 0") -> None:
        self.conn = _Conn(response)

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Acq()


class TestResetApiTokens:
    async def test_emits_correct_sql(self):
        pool = _Pool("UPDATE 3")
        n = await reset_api_token_daily(pool)
        assert n == 3
        sql, _ = pool.conn.executed[0]
        assert "UPDATE api_tokens" in sql
        assert "spend_today_usd  = 0" in sql
        assert "spend_today_date < current_date" in sql

    async def test_zero_rows_parsed(self):
        pool = _Pool("UPDATE 0")
        n = await reset_api_token_daily(pool)
        assert n == 0

    async def test_malformed_response_returns_zero(self):
        pool = _Pool("oops")
        n = await reset_api_token_daily(pool)
        assert n == 0


class TestResetFreeQuotas:
    async def test_emits_correct_sql_with_defaults(self):
        pool = _Pool("UPDATE 5")
        n = await reset_free_quotas(pool)
        assert n == 5
        sql, args = pool.conn.executed[0]
        assert "UPDATE cloud_user_balances" in sql
        assert "free_tokens_in_remaining" in sql
        assert "free_tokens_out_remaining" in sql
        # defaults
        assert args[0] == 100_000
        assert args[1] == 20_000


class TestBillingResetWorker:
    def test_constructible_and_stoppable(self):
        pool = _Pool()
        w = BillingResetWorker(pool=pool, interval_seconds=60.0)
        assert w.name == "billing_reset"
        assert not w._shutdown
        w.stop()
        assert w._shutdown
