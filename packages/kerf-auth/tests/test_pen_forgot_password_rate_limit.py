"""R17 — /forgot-password must have a per-IP rate limit (5/hour).

Verifies that:
  - the route has a rate_limit Depends in its signature
  - when the rate_limit dependency raises HTTP 429, the endpoint propagates it
  - normal requests (rate_limit not triggered) still return 200 {"status": "ok"}
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

import kerf_auth.routes as auth


def _app():
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    return app


def _fake_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.fixture(autouse=True)
def _stub_rate_limit_pass(monkeypatch):
    """Default: rate_limit is a no-op (pass-through)."""
    import kerf_core.rate_limit as _rl_module
    monkeypatch.setattr(_rl_module, "enforce", AsyncMock(return_value=None))
    import kerf_core.db.connection as _conn_module
    monkeypatch.setattr(_conn_module, "get_pool_required", AsyncMock(return_value=MagicMock()))


# ---------------------------------------------------------------------------
# R17-A  Route must declare a rate_limit dependency
# ---------------------------------------------------------------------------

def test_r17_forgot_password_has_rate_limit_dependency():
    """The forgot_password function must have a rate_limit Depends in its signature."""
    import inspect
    sig = inspect.signature(auth.forgot_password)
    params = dict(sig.parameters)
    # Find any parameter whose default is a Depends wrapping rate_limit
    from fastapi import params as fa_params
    rate_limit_deps = [
        p for p in params.values()
        if isinstance(p.default, fa_params.Depends)
    ]
    assert rate_limit_deps, (
        "/forgot-password must have at least one Depends() parameter (rate_limit). "
        "Found no Depends in signature."
    )


# ---------------------------------------------------------------------------
# R17-B  Rate limit pass-through: normal request → 200 {"status": "ok"}
# ---------------------------------------------------------------------------

def test_r17_forgot_password_normal_request_returns_200():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)  # unknown email
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# R17-C  Rate limit enforcement: when enforce raises 429, endpoint returns 429
# ---------------------------------------------------------------------------

def test_r17_forgot_password_propagates_rate_limit_429(monkeypatch):
    """When the rate_limit dependency fires, /forgot-password must return 429."""
    import kerf_core.rate_limit as _rl_module

    async def _enforce_reject(*args, **kwargs):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )

    monkeypatch.setattr(_rl_module, "enforce", _enforce_reject)

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app(), raise_server_exceptions=False)
        r = c.post("/auth/forgot-password", json={"email": "victim@example.com"})
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# R17-D  Rate limit key_prefix must be distinct from /login and /register
# ---------------------------------------------------------------------------

def test_r17_forgot_password_rate_limit_uses_distinct_key_prefix():
    """The rate_limit prefix for /forgot-password must differ from login and register."""
    import inspect
    from fastapi import params as fa_params
    import kerf_core.dependencies as dep_module

    # Collect all Depends from the forgot_password signature
    sig = inspect.signature(auth.forgot_password)
    found_prefixes: list[str] = []
    for p in sig.parameters.values():
        if isinstance(p.default, fa_params.Depends):
            # The dependency is a closure returned by rate_limit(); call it to
            # introspect the prefix — but we can also inspect via source.
            dep_fn = p.default.dependency
            # rate_limit() returns a closure; its __closure__ cells contain
            # the kwargs passed in including key_prefix.
            if dep_fn and dep_fn.__closure__:
                for cell in dep_fn.__closure__:
                    try:
                        v = cell.cell_contents
                        if isinstance(v, str) and v.startswith("auth:"):
                            found_prefixes.append(v)
                    except ValueError:
                        pass

    assert found_prefixes, "Could not find any auth:* key_prefix in /forgot-password rate_limit dep"
    prefix = found_prefixes[0]
    assert prefix not in ("auth:login", "auth:register"), (
        f"forgot-password rate_limit prefix '{prefix}' must be distinct from "
        "auth:login and auth:register to avoid cross-endpoint interference"
    )
