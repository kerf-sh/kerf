"""Hermetic API smoke suite — T-120.

One test per key endpoint group; each call:
  - Uses a minimal valid request against a real DB fixture.
  - Asserts the response is NOT 5xx.
  - Asserts the response body has a sane shape.

DB SAFETY:
  - Only inserts rows with a uuid-suffixed unique prefix.
  - Cleans up its own rows in the finally block.
  - Does NOT DROP / CREATE / TRUNCATE / reset migrations.
  - Passes regardless of other rows present.

The test app is a thin FastAPI instance with the kerf-api and kerf-auth
routers mounted inside a lifespan that initialises the asyncpg pool.  The
pool is registered in the ``kerf_core.db.connection`` singleton so all
route helpers (get_pool_required, project_workspace_id, etc.) work
transparently.  ``require_auth`` is overridden to inject the test user id
from a signed JWT — no real password flow needed.

Fixture rows are created synchronously (via a plain ``asyncio.run``) before
the TestClient is started, so they exist for the full session.  Cleanup runs
after the TestClient exits.

Run:
    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-api/tests/test_api_smoke.py -q
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

import asyncpg
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap (mirrors conftest.py)
# ---------------------------------------------------------------------------
import pathlib

_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgres://pc@localhost:5432/kerf?sslmode=disable",
)
_JWT_SECRET: str = "dev-secret-change-in-production"
_RUN_PREFIX: str = f"smoke-{secrets.token_hex(4)}"   # unique per pytest run


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _mint_jwt(user_id: str) -> str:
    """Mint a short-lived JWT for the test user."""
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        _JWT_SECRET,
        algorithm="HS256",
    )


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_mint_jwt(user_id)}"}


# ---------------------------------------------------------------------------
# Fixture creation / teardown helpers (run in a fresh event loop)
# ---------------------------------------------------------------------------

async def _create_fixtures(db_url: str) -> dict:
    """Insert test rows; return their ids."""
    suffix = _RUN_PREFIX
    user_email = f"{suffix}@smoke.test"
    user_name = f"Smoke {suffix}"
    ws_slug = f"ws-{suffix}"
    ws_name = f"WS {suffix}"
    proj_name = f"Proj {suffix}"

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                """
                INSERT INTO users (email, name, account_role, is_system)
                VALUES ($1, $2, 'user', false)
                RETURNING id, email, name, account_role, is_system,
                          created_at, email_verified
                """,
                user_email, user_name,
            )
            user_id = str(user_row["id"])

            ws_row = await conn.fetchrow(
                """
                INSERT INTO workspaces (slug, name, created_by)
                VALUES ($1, $2, $3)
                RETURNING id, slug, name, created_at
                """,
                ws_slug, ws_name, user_row["id"],
            )
            ws_id = str(ws_row["id"])

            await conn.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1, $2, 'owner')
                """,
                ws_row["id"], user_row["id"],
            )

            proj_row = await conn.fetchrow(
                """
                INSERT INTO projects
                    (workspace_id, name, description, visibility, tags)
                VALUES ($1, $2, '', 'private', '{}')
                RETURNING id, name, workspace_id, visibility,
                          created_at, updated_at
                """,
                ws_row["id"], proj_name,
            )
            proj_id = str(proj_row["id"])

            file_row = await conn.fetchrow(
                """
                INSERT INTO files (project_id, name, kind, content)
                VALUES ($1, $2, 'script', $3)
                RETURNING id, name, kind, content,
                          project_id, created_at, updated_at
                """,
                proj_row["id"],
                f"main-{suffix}.jscad",
                "// smoke test file",
            )
            file_id = str(file_row["id"])

            thread_row = await conn.fetchrow(
                """
                INSERT INTO chat_threads (project_id, title)
                VALUES ($1, $2)
                RETURNING id, project_id, title, created_at
                """,
                proj_row["id"],
                f"Thread {suffix}",
            )
            thread_id = str(thread_row["id"])
    finally:
        await pool.close()

    return {
        "user_id": user_id,
        "ws_id": ws_id,
        "ws_slug": ws_slug,
        "proj_id": proj_id,
        "file_id": file_id,
        "thread_id": thread_id,
    }


async def _delete_fixtures(db_url: str, ids: dict) -> None:
    """Delete smoke test rows (best-effort; FK order)."""
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM chat_messages WHERE thread_id = $1",
                uuid.UUID(ids["thread_id"]),
            )
            await conn.execute(
                "DELETE FROM chat_threads WHERE id = $1",
                uuid.UUID(ids["thread_id"]),
            )
            await conn.execute(
                "DELETE FROM files WHERE project_id = $1",
                uuid.UUID(ids["proj_id"]),
            )
            await conn.execute(
                "DELETE FROM projects WHERE id = $1",
                uuid.UUID(ids["proj_id"]),
            )
            await conn.execute(
                "DELETE FROM workspace_members WHERE workspace_id = $1",
                uuid.UUID(ids["ws_id"]),
            )
            await conn.execute(
                "DELETE FROM workspaces WHERE id = $1",
                uuid.UUID(ids["ws_id"]),
            )
            await conn.execute(
                "DELETE FROM refresh_tokens WHERE user_id = $1",
                uuid.UUID(ids["user_id"]),
            )
            await conn.execute(
                "DELETE FROM email_tokens WHERE user_id = $1",
                uuid.UUID(ids["user_id"]),
            )
            await conn.execute(
                "DELETE FROM users WHERE id = $1",
                uuid.UUID(ids["user_id"]),
            )
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Session-scoped fixture data (created/deleted outside the TestClient loop)
# ---------------------------------------------------------------------------

_FIXTURE_IDS: dict | None = None


def _get_fixture_ids() -> dict:
    global _FIXTURE_IDS
    if _FIXTURE_IDS is None:
        _FIXTURE_IDS = asyncio.run(_create_fixtures(_DB_URL))
    return _FIXTURE_IDS


@pytest.fixture(scope="session", autouse=True)
def session_fixtures() -> Generator[dict, None, None]:
    """Create DB rows before the session; tear down after."""
    ids = _get_fixture_ids()
    yield ids
    asyncio.run(_delete_fixtures(_DB_URL, ids))


# ---------------------------------------------------------------------------
# Test app + TestClient
#
# The lifespan opens the asyncpg pool INSIDE the TestClient's event loop,
# wires the kerf_core.db.connection singleton, and tears down on exit.
# This ensures get_pool_required() works inside every route handler.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialise DB pool in the TestClient's event loop."""
    import kerf_core.db.connection as _conn

    pool = await asyncpg.create_pool(_DB_URL, min_size=2, max_size=5)
    _conn._pool = pool

    # Initialise storage singleton (local filesystem backend — prevents
    # get_storage_required() from raising on the cover/thumbnail routes).
    try:
        from kerf_core.storage.factory import create_storage as _cs
        from kerf_core.storage import set_storage as _ss
        _ss(_cs(backend="local", local_storage_path="./.kerf-storage-smoke"))
    except Exception:
        pass

    yield

    _conn._pool = None
    await pool.close()


def _build_test_app() -> FastAPI:
    from kerf_api.routes import router as api_router
    from kerf_auth.routes import router as auth_router

    app = FastAPI(lifespan=_lifespan)
    app.include_router(api_router, prefix="/api")
    app.include_router(auth_router, prefix="/auth")
    return app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    app = _build_test_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def _ids() -> dict:
    return _get_fixture_ids()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------


# ── 1. GET /api/config — public config (no auth) ──────────────────────────

def test_smoke_config(client: TestClient):
    r = client.get("/api/config")
    assert r.status_code < 500, f"/api/config {r.status_code}: {r.text}"
    assert r.status_code == 200
    body = r.json()
    assert "local_mode" in body or "cloud_enabled" in body, (
        f"config missing expected keys: {body}"
    )


# ── 2. GET /api/models — chat/models group ────────────────────────────────

def test_smoke_models(client: TestClient):
    uid = _ids()["user_id"]
    r = client.get("/api/models", headers=_auth_headers(uid))
    assert r.status_code < 500, f"/api/models {r.status_code}: {r.text}"
    body = r.json()
    assert "models" in body, f"missing 'models' key: {body}"
    assert isinstance(body["models"], list)
    assert len(body["models"]) >= 1, "models list must be non-empty"


# ── 3. GET /api/me — identity / me group ─────────────────────────────────

def test_smoke_me(client: TestClient):
    uid = _ids()["user_id"]
    r = client.get("/api/me", headers=_auth_headers(uid))
    assert r.status_code < 500, f"/api/me {r.status_code}: {r.text}"
    assert r.status_code == 200, f"/api/me not 200: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("id") == uid, f"me.id mismatch: {body}"
    assert "email" in body


# ── 4. GET /api/projects — projects list ─────────────────────────────────

def test_smoke_list_projects(client: TestClient):
    uid = _ids()["user_id"]
    r = client.get("/api/projects", headers=_auth_headers(uid))
    assert r.status_code < 500, f"/api/projects {r.status_code}: {r.text}"
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    ids_in_list = [p.get("id") for p in body]
    assert _ids()["proj_id"] in ids_in_list, (
        f"smoke project not in list. ids={ids_in_list[:3]}…"
    )


# ── 5. GET /api/projects/{pid}/files — files group ───────────────────────

def test_smoke_list_files(client: TestClient):
    uid = _ids()["user_id"]
    pid = _ids()["proj_id"]
    r = client.get(f"/api/projects/{pid}/files", headers=_auth_headers(uid))
    assert r.status_code < 500, f"list_files {r.status_code}: {r.text}"
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    fids = [f.get("id") for f in body]
    assert _ids()["file_id"] in fids, (
        f"smoke file not in files list. fids={fids[:3]}…"
    )


# ── 6. GET /api/projects/{pid}/threads — chat threads list ───────────────

def test_smoke_list_threads(client: TestClient):
    uid = _ids()["user_id"]
    pid = _ids()["proj_id"]
    r = client.get(f"/api/projects/{pid}/threads", headers=_auth_headers(uid))
    assert r.status_code < 500, f"list_threads {r.status_code}: {r.text}"
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


# ── 7. POST /api/projects/{pid}/threads/{tid}/messages — chat message ────
#    With no LLM key configured, the route returns a graceful fallback
#    assistant message ("LLM not configured") — not a 500.

def test_smoke_post_message(client: TestClient):
    uid = _ids()["user_id"]
    pid = _ids()["proj_id"]
    tid = _ids()["thread_id"]
    r = client.post(
        f"/api/projects/{pid}/threads/{tid}/messages",
        json={"content": "smoke test: hello"},
        headers=_auth_headers(uid),
    )
    assert r.status_code < 500, f"post_message {r.status_code}: {r.text}"
    assert r.status_code in (200, 201), f"unexpected status {r.status_code}: {r.text}"
    body = r.json()
    assert "user_message" in body, f"missing user_message: {body}"
    assert "assistant_message" in body, f"missing assistant_message: {body}"


# ── 8. GET /api/workshop/ — workshop group ────────────────────────────────

def test_smoke_workshop_list(client: TestClient):
    r = client.get("/api/workshop/")
    assert r.status_code < 500, f"workshop_list {r.status_code}: {r.text}"
    assert r.status_code == 200
    body = r.json()
    assert "listings" in body or "rows" in body, (
        f"workshop list missing listings/rows key: {body}"
    )


# ── 9. GET /api/library/parts — library group ─────────────────────────────

def test_smoke_library_parts(client: TestClient):
    r = client.get("/api/library/parts")
    assert r.status_code < 500, f"library_parts {r.status_code}: {r.text}"
    assert r.status_code == 200, f"library_parts {r.status_code}: {r.text}"


# ── 10. POST /auth/forgot-password — auth forgot group ────────────────────
#     Must always return 200 (never reveals whether email is registered).

def test_smoke_auth_forgot_password(client: TestClient):
    r = client.post(
        "/auth/forgot-password",
        json={"email": f"{_RUN_PREFIX}-nonexistent@kerf.test"},
    )
    assert r.status_code < 500, f"forgot-password {r.status_code}: {r.text}"
    assert r.status_code == 200, f"forgot-password {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("status") == "ok", f"unexpected body: {body}"


# ── 11. POST /auth/reset-password with invalid token — auth reset group ───
#     Invalid token must return 400, not 500.

def test_smoke_auth_reset_password_invalid_token(client: TestClient):
    r = client.post(
        "/auth/reset-password",
        json={"token": f"{_RUN_PREFIX}-invalid-token", "password": "newpassword123"},
    )
    assert r.status_code < 500, f"reset-password {r.status_code}: {r.text}"
    assert r.status_code == 400, (
        f"reset-password with invalid token should 400, got {r.status_code}: {r.text}"
    )


# ── 12. GET /auth/verify-email with invalid token — auth verify group ────
#     Invalid token should redirect (302/307), not 500.

def test_smoke_auth_verify_email_invalid(client: TestClient):
    r = client.get(
        f"/auth/verify-email?token={_RUN_PREFIX}-invalid",
        follow_redirects=False,
    )
    assert r.status_code < 500, f"verify-email {r.status_code}: {r.text}"
    assert r.status_code in (302, 307), (
        f"verify-email with invalid token should redirect, got {r.status_code}: {r.text}"
    )


# ── 13. GET /api/projects/{pid}/thumbnail — thumbnail group ───────────────
#     No thumbnail stored → 404, not 500.

def test_smoke_thumbnail_no_cover_404(client: TestClient):
    pid = _ids()["proj_id"]
    uid = _ids()["user_id"]
    r = client.get(
        f"/api/projects/{pid}/thumbnail",
        headers=_auth_headers(uid),
        follow_redirects=False,
    )
    assert r.status_code < 500, f"thumbnail {r.status_code}: {r.text}"
    assert r.status_code == 404, (
        f"thumbnail with no image should 404, got {r.status_code}: {r.text}"
    )


# ── 14. GET /api/projects/{pid}/cover — cover group ───────────────────────
#     No cover stored → 404, not 500.

def test_smoke_cover_no_cover_404(client: TestClient):
    pid = _ids()["proj_id"]
    uid = _ids()["user_id"]
    r = client.get(
        f"/api/projects/{pid}/cover",
        headers=_auth_headers(uid),
        follow_redirects=False,
    )
    assert r.status_code < 500, f"cover {r.status_code}: {r.text}"
    assert r.status_code == 404, (
        f"cover with no image should 404, got {r.status_code}: {r.text}"
    )


# ── 15. GET /api/billing/me — billing group (skipped if cloud disabled) ───

def test_smoke_billing_me(client: TestClient):
    from kerf_core.config import get_settings
    if not get_settings().cloud_enabled:
        pytest.skip("billing routes not mounted: cloud_enabled=False")

    uid = _ids()["user_id"]
    r = client.get("/api/billing/me", headers=_auth_headers(uid))
    assert r.status_code < 500, f"billing/me {r.status_code}: {r.text}"
    assert r.status_code == 200, f"billing/me {r.status_code}: {r.text}"
    body = r.json()
    assert "credits_usd" in body, f"billing/me missing credits_usd: {body}"


# ── 16. GET /api/billing/usage — billing usage group (skipped if cloud off)

def test_smoke_billing_usage(client: TestClient):
    from kerf_core.config import get_settings
    if not get_settings().cloud_enabled:
        pytest.skip("billing routes not mounted: cloud_enabled=False")

    uid = _ids()["user_id"]
    r = client.get("/api/billing/usage", headers=_auth_headers(uid))
    assert r.status_code < 500, f"billing/usage {r.status_code}: {r.text}"
    assert r.status_code == 200, f"billing/usage {r.status_code}: {r.text}"
    body = r.json()
    assert "events" in body, f"billing/usage missing events: {body}"
