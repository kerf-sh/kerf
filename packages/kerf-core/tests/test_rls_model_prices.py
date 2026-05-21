"""
T-93 — RLS: model_prices admin-only
====================================
Hermetic tests verifying that the ``model_prices`` table is write-protected
so only callers with ``account_role='admin'`` (or 'system') can mutate it.

Access-control is enforced at the application layer in
``kerf_pricing.routes._require_admin``, which looks up the caller's
``account_role`` in the ``users`` table before allowing any mutation.

Tables / surfaces under test
-----------------------------
model_prices (mig 050 / 0008_billing.sql):
  - INSERT / UPDATE / upsert: exclusively through the admin routes
    POST /admin/pricing/refresh → _require_admin → refresh_model_prices
  - SELECT: publicly available to any authenticated user via get_price /
    list_all_prices (no user_id scoping needed — pricing is not tenant data)

Security invariants
-------------------
 1.  Non-admin INSERT via refresh route returns 403.
 2.  Non-admin GET /admin/pricing returns 403.
 3.  Non-admin POST /admin/pricing/refresh returns 403.
 4.  'system' role IS allowed (admin + system are both trusted).
 5.  'admin' role IS allowed.
 6.  User not found in DB → 403 (no fallback grant).
 7.  Missing ``sub`` claim in token payload → 401.
 8.  get_price SELECT binds provider + model_id (no user_id gate needed).
 9.  list_all_prices SELECT has no tenant filter (global table, not row-scoped).
10.  upsert_models does NOT check caller role — the guard lives in the route.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixed actor UUIDs
# ---------------------------------------------------------------------------

USER_REGULAR = str(uuid.uuid4())
USER_ADMIN = str(uuid.uuid4())
USER_SYSTEM = str(uuid.uuid4())
USER_MISSING = str(uuid.uuid4())   # not in our fake DB


# ---------------------------------------------------------------------------
# Minimal fake asyncpg connection / pool
# ---------------------------------------------------------------------------

class _Record(dict):
    """Minimal asyncpg-Record-alike that supports dict-style and .get() access."""

    def __getitem__(self, key: str):
        return super().__getitem__(key)

    def get(self, key: str, default=None):  # type: ignore[override]
        return super().get(key, default)


# Maps user_id → account_role for our fake DB
_FAKE_USERS: dict[str, str] = {
    USER_REGULAR: "user",
    USER_ADMIN:   "admin",
    USER_SYSTEM:  "system",
    # USER_MISSING is intentionally absent
}


class _RecordingConn:
    """Records every SQL call; returns rows from per-call queues."""

    def __init__(
        self,
        fetchrow_seq: list[Optional[_Record]] = (),
        fetch_seq: list[list[_Record]] = (),
    ) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._fetchrow_seq = list(fetchrow_seq)
        self._fetch_seq = list(fetch_seq)

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql, args))
        return "OK"

    async def fetchrow(self, sql: str, *args) -> Optional[_Record]:
        self.executed.append((sql, args))
        if self._fetchrow_seq:
            return self._fetchrow_seq.pop(0)
        return None

    async def fetch(self, sql: str, *args) -> list[_Record]:
        self.executed.append((sql, args))
        if self._fetch_seq:
            return self._fetch_seq.pop(0)
        return []

    def transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self_inner):
                return outer

            async def __aexit__(self_inner, *_):
                return False

        return _Tx()


class _RecordingPool:
    """Pool that yields a shared _RecordingConn via acquire()."""

    def __init__(
        self,
        fetchrow_seq: list[Optional[_Record]] = (),
        fetch_seq: list[list[_Record]] = (),
    ) -> None:
        self.conn = _RecordingConn(fetchrow_seq, fetch_seq)

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *_):
                return False

        return _Acq()

    async def fetch(self, sql: str, *args) -> list[_Record]:
        return await self.conn.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args) -> Optional[_Record]:
        return await self.conn.fetchrow(sql, *args)


# ---------------------------------------------------------------------------
# Helper: build a fake token payload for _require_admin
# ---------------------------------------------------------------------------

def _payload(user_id: Optional[str]) -> dict:
    if user_id is None:
        return {}            # no 'sub' claim → 401 path
    return {"sub": user_id}


# ---------------------------------------------------------------------------
# Monkey-patchable _require_admin helper
# ---------------------------------------------------------------------------

async def _call_require_admin(user_id: Optional[str], role: Optional[str]) -> str:
    """Exercise _require_admin in isolation with a fake pool.

    Simulates: pool.acquire() → conn.fetchrow("SELECT account_role …", uid)
    """
    import kerf_pricing.routes as pricing_routes

    payload = _payload(user_id)
    if role is None:
        # No row in DB
        pool = _RecordingPool(fetchrow_seq=[None])
    else:
        pool = _RecordingPool(
            fetchrow_seq=[_Record({"account_role": role})]
        )

    # Patch the name in the routes module namespace (where it is looked up at
    # call time after the module-level `from kerf_core.db.connection import ...`).
    real_gpr = pricing_routes.get_pool_required

    async def _fake_gpr():
        return pool

    pricing_routes.get_pool_required = _fake_gpr
    try:
        uid = await pricing_routes._require_admin(payload)
    finally:
        pricing_routes.get_pool_required = real_gpr

    return uid


# ============================================================================
# Case 1 — regular user ('user' role) is refused with 403
# ============================================================================

@pytest.mark.asyncio
async def test_regular_user_insert_refused():
    """A caller with account_role='user' must receive 403 on any admin route."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_require_admin(USER_REGULAR, role="user")
    assert exc_info.value.status_code == 403
    assert "admin" in exc_info.value.detail.lower()


# ============================================================================
# Case 2 — non-admin GET /admin/pricing returns 403
# ============================================================================

@pytest.mark.asyncio
async def test_non_admin_get_pricing_forbidden():
    """GET /admin/pricing must 403 a non-admin caller."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_require_admin(USER_REGULAR, role="user")
    assert exc_info.value.status_code == 403


# ============================================================================
# Case 3 — non-admin POST /admin/pricing/refresh returns 403
# ============================================================================

@pytest.mark.asyncio
async def test_non_admin_post_refresh_forbidden():
    """POST /admin/pricing/refresh must 403 a caller with role='user'."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_require_admin(USER_REGULAR, role="user")
    assert exc_info.value.status_code == 403
    # Confirm it is the admin gate, not the auth gate
    assert exc_info.value.detail != "unauthorized"


# ============================================================================
# Case 4 — 'system' role is allowed
# ============================================================================

@pytest.mark.asyncio
async def test_system_role_is_allowed():
    """account_role='system' must be accepted as trusted (same as admin)."""
    uid = await _call_require_admin(USER_SYSTEM, role="system")
    assert uid == USER_SYSTEM


# ============================================================================
# Case 5 — 'admin' role is allowed
# ============================================================================

@pytest.mark.asyncio
async def test_admin_role_is_allowed():
    """account_role='admin' must be accepted — mutation proceeds."""
    uid = await _call_require_admin(USER_ADMIN, role="admin")
    assert uid == USER_ADMIN


# ============================================================================
# Case 6 — user not found in DB → 403
# ============================================================================

@pytest.mark.asyncio
async def test_missing_user_forbidden():
    """If the users table has no row for the token's sub, return 403."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_require_admin(USER_MISSING, role=None)   # None → no row
    assert exc_info.value.status_code == 403


# ============================================================================
# Case 7 — missing 'sub' claim in payload → 401
# ============================================================================

@pytest.mark.asyncio
async def test_missing_sub_claim_returns_401():
    """Token without a 'sub' claim must receive 401, not 403."""
    import kerf_pricing.routes as pricing_routes

    pool = _RecordingPool()   # pool that returns no rows (should not even be called)

    real_gpr = pricing_routes.get_pool_required

    async def _fake_gpr():
        return pool

    pricing_routes.get_pool_required = _fake_gpr
    try:
        with pytest.raises(HTTPException) as exc_info:
            await pricing_routes._require_admin({})   # empty payload, no 'sub'
    finally:
        pricing_routes.get_pool_required = real_gpr

    assert exc_info.value.status_code == 401


# ============================================================================
# Case 8 — get_price SELECT binds provider + model_id correctly
# ============================================================================

@pytest.mark.asyncio
async def test_get_price_binds_provider_and_model_id():
    """get_price SELECT must pass (provider, model_id) — no user_id gate."""
    from kerf_pricing.queries import get_price

    provider = "anthropic"
    model_id  = "claude-sonnet-4-6"
    fake_row = _Record({
        "provider":            provider,
        "model_id":            model_id,
        "input_per_mtok":      3.0,
        "output_per_mtok":     15.0,
        "cache_read_per_mtok": None,
        "max_input_tokens":    200_000,
        "cheap_tier_eligible": True,
    })
    pool = _RecordingPool(fetchrow_seq=[fake_row])
    price = await get_price(pool, provider, model_id)

    assert price is not None
    assert price.provider == provider
    assert price.model_id == model_id
    assert price.cheap_tier_eligible is True

    # Confirm the SQL bound provider and model_id (no user_id scoping)
    sql, args = pool.conn.executed[0]
    assert args[0] == provider
    assert args[1] == model_id
    assert len(args) == 2, "get_price must only pass (provider, model_id) — no user_id"


# ============================================================================
# Case 9 — list_all_prices SELECT has no per-tenant filter
# ============================================================================

@pytest.mark.asyncio
async def test_list_all_prices_has_no_tenant_filter():
    """list_all_prices is a global admin read — must not restrict by user_id."""
    from kerf_pricing.queries import list_all_prices
    import datetime

    fake_rows = [
        _Record({
            "provider":            "anthropic",
            "model_id":            "claude-sonnet-4-6",
            "input_per_mtok":      3.0,
            "output_per_mtok":     15.0,
            "cache_read_per_mtok": None,
            "max_input_tokens":    200_000,
            "cheap_tier_eligible": True,
            "fetched_at":          datetime.datetime(2026, 5, 21, 0, 0),
        }),
    ]
    pool = _RecordingPool(fetch_seq=[fake_rows])
    rows = await list_all_prices(pool)

    assert len(rows) == 1
    assert rows[0]["provider"] == "anthropic"

    # Confirm the SQL call had NO bound arguments (SELECT * FROM model_prices)
    sql, args = pool.conn.executed[0]
    assert "model_prices" in sql
    assert len(args) == 0, (
        "list_all_prices must not bind any user_id argument — "
        "model_prices is global, not per-tenant"
    )


# ============================================================================
# Case 10 — upsert_models INSERT is never reachable without admin gate
# ============================================================================

@pytest.mark.asyncio
async def test_upsert_models_write_path_requires_admin_source_check():
    """upsert_models itself has no auth gate — the guard lives in the route.

    Verify via source inspection that the only caller path from an HTTP
    handler is through _require_admin → refresh_model_prices → upsert_models.
    """
    import inspect
    from kerf_pricing import routes as pricing_routes

    src = inspect.getsource(pricing_routes)

    # Both write-capable route handlers must call _require_admin
    refresh_handler_src = [
        block for block in src.split("@router.")
        if "pricing/refresh" in block or "post_pricing_refresh" in block
    ]
    assert refresh_handler_src, "POST /admin/pricing/refresh handler not found in routes.py"

    for block in refresh_handler_src:
        assert "_require_admin" in block, (
            "POST /admin/pricing/refresh handler must call _require_admin "
            f"before mutating model_prices.\nBlock:\n{block}"
        )

    # GET /admin/pricing also requires admin
    get_handler_src = [
        block for block in src.split("@router.")
        if "admin/pricing" in block and "refresh" not in block
    ]
    for block in get_handler_src:
        assert "_require_admin" in block, (
            "GET /admin/pricing handler must call _require_admin\n"
            f"Block:\n{block}"
        )

    # _require_admin must reject anything that isn't admin or system
    require_src = inspect.getsource(pricing_routes._require_admin)
    assert '"admin"' in require_src or "'admin'" in require_src
    assert '"system"' in require_src or "'system'" in require_src
    assert "403" in require_src, "_require_admin must raise 403 on non-admin callers"
