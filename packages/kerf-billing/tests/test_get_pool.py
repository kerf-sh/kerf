"""Regression: kerf-billing _get_pool must use the live kerf_core pool.

It used to do `from db.connection import get_pool` (pre-monorepo module
that no longer exists) inside loop.run_until_complete() — so every
/api/billing/* (the whole billing page) 500'd with
ModuleNotFoundError: No module named 'db'.

The guard is AST-based, not a substring scan: routes.py legitimately
*documents* the old bug in a comment, and a naive `"... " in src`
check trips on its own explanatory text.
"""
import ast
import pathlib

import kerf_core.db.connection as conn_mod
import kerf_billing.routes as billing_routes


def _tree():
    return ast.parse(pathlib.Path(billing_routes.__file__).read_text())


def test_no_dead_db_import_statement():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "db.connection", (
                "dead pre-monorepo `from db.connection import ...` is back"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "db.connection"


def test_no_run_until_complete_call():
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            assert name != "run_until_complete", (
                "loop.run_until_complete() inside the request loop is back"
            )


def test_get_pool_returns_the_live_singleton():
    # connection.py has no set_pool(); the canonical pool is the module
    # global, assigned by create_pool()/create_pool_from_config() at
    # startup. Simulate that here.
    sentinel = object()
    prev = conn_mod._pool
    conn_mod._pool = sentinel
    billing_routes._pool = None  # force re-resolve
    try:
        assert billing_routes._get_pool() is sentinel
    finally:
        conn_mod._pool = prev
        billing_routes._pool = None
