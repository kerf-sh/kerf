"""Regression: kerf-billing _get_pool must use the live kerf_core pool.

It did `from db.connection import get_pool` (pre-monorepo module that no
longer exists) inside loop.run_until_complete() — so every
/api/billing/* (the whole billing page) 500'd with
ModuleNotFoundError: No module named 'db'.
"""
import pathlib

import kerf_core.db.connection as conn_mod
import kerf_billing.routes as billing_routes


def test_no_dead_db_import():
    src = (
        pathlib.Path(billing_routes.__file__).read_text()
    )
    assert "from db.connection import" not in src
    assert "run_until_complete" not in src  # was a loop-in-loop crash too


def test_get_pool_returns_the_live_singleton():
    sentinel = object()
    conn_mod.set_pool(sentinel)
    billing_routes._pool = None  # force re-resolve
    try:
        assert billing_routes._get_pool() is sentinel
    finally:
        conn_mod.set_pool(None)
        billing_routes._pool = None
