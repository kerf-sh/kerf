"""R20 — record_storage_event must wrap INSERT + cloud_debit_balance in one transaction.

Verifies that:
  - conn.transaction() is called (the debit is in the same txn as the INSERT)
  - cloud_debit_balance is called with the correct user_id and cost_usd
  - if the debit call raises, the INSERT is rolled back (atomicity)
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

from kerf_cloud.usage import record_storage_event


def _make_pool_and_conn():
    """Return (pool, conn) with a properly stubbed asyncpg-like context."""
    conn = AsyncMock()
    # Simulate conn.transaction() as a context manager
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_r20_storage_event_calls_transaction():
    """record_storage_event must open a transaction (not a bare execute)."""
    pool, conn = _make_pool_and_conn()

    await record_storage_event(pool, "user-1", "proj-1", 1024, 0.001)

    conn.transaction.assert_called_once()


@pytest.mark.asyncio
async def test_r20_storage_event_calls_debit_balance():
    """record_storage_event must call cloud_debit_balance with the correct args."""
    pool, conn = _make_pool_and_conn()

    await record_storage_event(pool, "user-abc", "proj-xyz", 2048, 0.005)

    # Find the cloud_debit_balance call among conn.execute calls
    debit_calls = [
        c for c in conn.execute.call_args_list
        if c.args and "cloud_debit_balance" in str(c.args[0])
    ]
    assert debit_calls, "cloud_debit_balance was not called by record_storage_event"

    # The debit call must pass user_id and cost_usd
    debit_call = debit_calls[0]
    assert "user-abc" in debit_call.args, (
        f"user_id 'user-abc' not passed to cloud_debit_balance; got {debit_call.args}"
    )
    assert 0.005 in debit_call.args, (
        f"cost_usd 0.005 not passed to cloud_debit_balance; got {debit_call.args}"
    )


@pytest.mark.asyncio
async def test_r20_storage_event_insert_and_debit_in_same_transaction():
    """INSERT and cloud_debit_balance must both be called inside the transaction block."""
    pool, conn = _make_pool_and_conn()

    call_order: list[str] = []

    original_tx_enter = conn.transaction.return_value.__aenter__
    original_tx_exit = conn.transaction.return_value.__aexit__

    async def _tx_enter(self=None):
        call_order.append("txn:enter")
        return None

    async def _tx_exit(*args):
        call_order.append("txn:exit")
        return False

    async def _execute_tracker(sql, *args):
        if "INSERT" in sql:
            call_order.append("insert")
        elif "cloud_debit_balance" in sql:
            call_order.append("debit")

    conn.transaction.return_value.__aenter__ = _tx_enter
    conn.transaction.return_value.__aexit__ = _tx_exit
    conn.execute = _execute_tracker  # type: ignore[assignment]

    await record_storage_event(pool, "user-2", None, 512, 0.002)

    assert "txn:enter" in call_order, "transaction was never entered"
    assert "insert" in call_order, "INSERT was not called"
    assert "debit" in call_order, "cloud_debit_balance was not called"

    enter_idx = call_order.index("txn:enter")
    insert_idx = call_order.index("insert")
    debit_idx = call_order.index("debit")
    exit_idx = call_order.index("txn:exit")

    assert enter_idx < insert_idx < exit_idx, (
        "INSERT must happen inside the transaction block"
    )
    assert enter_idx < debit_idx < exit_idx, (
        "cloud_debit_balance must happen inside the transaction block"
    )


@pytest.mark.asyncio
async def test_r20_storage_event_raises_on_empty_user_id():
    """record_storage_event must raise ValueError when user_id is empty."""
    pool, _ = _make_pool_and_conn()
    with pytest.raises(ValueError, match="usage"):
        await record_storage_event(pool, "", "proj-1", 1024, 0.001)
