"""Integration + unit tests for the T-146 git provider settings API.

Covers:
  - GET /git/providers — returns only configured providers; never exposes
    unconfigured ones; response includes the "kerf git retained" note.
  - POST /projects/{pid}/git/provider/connect — round-trip via mock provider;
    editor auth required; 400 on bad kwargs; kerf_git_retained in response.
  - POST /projects/{pid}/git/provider/disconnect — clears mirror; kerf_git_retained.
  - GET /projects/{pid}/git/provider/status — returns per-provider status;
    kerf_git_retained in response.
  - Unauthenticated requests → 401.
  - Cross-tenant (non-member) requests → 404.

Tests call route handler functions directly (same pattern as
test_git_commit_materialize.py) to avoid ASGI thread / event-loop contention
with the shared asyncpg connection.

DB rule: shared Postgres, unique-suffixed rows, no DROP/CREATE/TRUNCATE.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from fastapi import HTTPException

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-t146-"

_LOOP: asyncio.AbstractEventLoop | None = None


def _loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Settings helpers (mirrors test_git_providers.py)
# ---------------------------------------------------------------------------

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


def _configured_settings():
    s = MagicMock()
    s.cloud_github_app_id = "3727956"
    s.cloud_github_app_slug = "kerf-app"
    s.github_private_key_pem = _PRIVATE_KEY_PEM
    return s


def _unconfigured_settings():
    s = MagicMock()
    s.cloud_github_app_id = ""
    s.github_private_key_pem = ""
    s.cloud_github_app_slug = "kerf-app"
    return s


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# DB tenant fixtures (unique-suffixed; self-cleaning)
# ---------------------------------------------------------------------------

async def _make_user(conn: asyncpg.Connection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid, f"{_TAG}{uid.hex}@test.invalid", f"T146 User {uid}",
    )
    return uid


async def _make_workspace(conn: asyncpg.Connection, owner: uuid.UUID) -> uuid.UUID:
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws, f"{_TAG}{ws.hex}", f"T146 WS {ws}", owner,
    )
    return ws


async def _make_project(conn: asyncpg.Connection, ws: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid, ws, f"test-t146-proj-{pid}",
    )
    await conn.execute(
        "INSERT INTO cloud_git_repos (project_id, default_branch) VALUES ($1, 'main')",
        pid,
    )
    return pid


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM projects  WHERE name LIKE $1", "test-t146-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users      WHERE email LIKE $1", f"{_TAG}%@test.invalid")


@pytest.fixture(scope="module")
def db_conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    c = run(asyncpg.connect(DATABASE_URL))
    yield c
    run(_cleanup(c))
    run(c.close())


@pytest.fixture()
def cleanup_after(db_conn):
    """Per-test cleanup runs at the END of each test (not autouse to avoid
    races; each test that uses DB calls this after it's done with db_conn)."""
    yield
    run(_cleanup(db_conn))


# ---------------------------------------------------------------------------
# Route patches helper
# ---------------------------------------------------------------------------

def _patches(conn, *, uid: str, registry=None, role: str = "owner"):
    """Return a list of patch objects that wire auth + pool for route tests."""
    pool = _make_pool(conn)
    ps = [
        patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_cloud.routes.require_editor", AsyncMock(return_value=uid)),
        patch("kerf_cloud.routes.require_role",
              AsyncMock(return_value=(uid, role))),
    ]
    if registry is not None:
        ps.append(patch("kerf_cloud.routes._provider_registry", return_value=registry))
    return ps


def _fake_request():
    return MagicMock()


# ---------------------------------------------------------------------------
# T-146-A  list_git_providers
# ---------------------------------------------------------------------------


class TestListGitProviders:
    """GET /git/providers — only configured providers are returned."""

    def test_returns_github_when_configured(self):
        from kerf_cloud.git_providers.registry import _build_default_registry
        import kerf_cloud.routes as routes

        registry = _build_default_registry(_configured_settings())

        with patch("kerf_cloud.routes._provider_registry", return_value=registry):
            result = run(routes.list_git_providers(payload={"sub": "uid-1"}))

        assert "github" in result["providers"]

    def test_excludes_unconfigured_providers(self):
        from kerf_cloud.git_providers.registry import _build_default_registry
        import kerf_cloud.routes as routes

        registry = _build_default_registry(_unconfigured_settings())

        with patch("kerf_cloud.routes._provider_registry", return_value=registry):
            result = run(routes.list_git_providers(payload={"sub": "uid-1"}))

        assert result["providers"] == []

    def test_response_includes_kerf_git_note(self):
        from kerf_cloud.git_providers.registry import _build_default_registry
        import kerf_cloud.routes as routes

        registry = _build_default_registry(_configured_settings())

        with patch("kerf_cloud.routes._provider_registry", return_value=registry):
            result = run(routes.list_git_providers(payload={"sub": "uid-1"}))

        note = result.get("note", "")
        assert "always retained" in note.lower() or "kerf" in note.lower()

    def test_unauthenticated_request_raises_401(self):
        """require_auth (called by Depends) raises 401 when no credentials."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import kerf_cloud.routes as _routes

        _app = FastAPI()
        _app.include_router(_routes.router)

        with TestClient(_app, raise_server_exceptions=False) as c:
            resp = c.get("/git/providers")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# T-146-B  git_provider_connect
# ---------------------------------------------------------------------------


class TestGitProviderConnect:
    """POST /projects/{pid}/git/provider/connect — connect an external mirror."""

    def test_connect_github_round_trip(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        req = MagicMock()
        req.json = AsyncMock(return_value={
            "provider": "github",
            "github_owner": "acme",
            "github_repo": "my-design",
        })
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            result = run(routes.git_provider_connect(req, payload={"sub": str(uid)}, pid=str(pid)))
        finally:
            for p in reversed(ps):
                p.stop()

        assert result["provider"] == "github"
        assert result["github_owner"] == "acme"
        assert result["github_repo"] == "my-design"
        assert result["kerf_git_retained"] is True
        note = result.get("note", "")
        assert "always retained" in note.lower() or "kerf" in note.lower()

    def test_connect_unknown_provider_raises_404(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        req = MagicMock()
        req.json = AsyncMock(return_value={"provider": "gitlab"})
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_connect(req, payload={"sub": str(uid)}, pid=str(pid)))
        finally:
            for p in reversed(ps):
                p.stop()

        assert exc_info.value.status_code == 404

    def test_connect_unconfigured_provider_raises_404(self, db_conn, cleanup_after):
        """GitHub unconfigured (no app credentials) → 404."""
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_unconfigured_settings())

        req = MagicMock()
        req.json = AsyncMock(return_value={"provider": "github"})
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_connect(req, payload={"sub": str(uid)}, pid=str(pid)))
        finally:
            for p in reversed(ps):
                p.stop()

        assert exc_info.value.status_code == 404

    def test_connect_missing_provider_field_raises_400(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        req = MagicMock()
        req.json = AsyncMock(return_value={"github_owner": "acme"})
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid))
        for p in ps:
            p.start()
        try:
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_connect(req, payload={"sub": str(uid)}, pid=str(pid)))
        finally:
            for p in reversed(ps):
                p.stop()

        assert exc_info.value.status_code == 400

    def test_connect_unauthenticated_raises_401(self):
        """No auth header → require_auth raises 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import kerf_cloud.routes as _routes

        _app = FastAPI()
        _app.include_router(_routes.router)

        with TestClient(_app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/projects/00000000-0000-0000-0000-000000000001/git/provider/connect",
                json={"provider": "github", "github_owner": "x", "github_repo": "y"},
            )
        assert resp.status_code == 401

    def test_connect_cross_tenant_raises_404(self, db_conn, cleanup_after):
        """A user who is not a member of the project gets a 404."""
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        cross_user = str(uuid.uuid4())

        async def _cross_tenant_editor(request, project_id, user_id):
            raise HTTPException(status_code=404, detail="project not found")

        req = MagicMock()
        req.json = AsyncMock(return_value={
            "provider": "github", "github_owner": "acme", "github_repo": "x"
        })
        req.body = AsyncMock(return_value=b"x")

        pool = _make_pool(db_conn)
        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_editor", _cross_tenant_editor):
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_connect(
                    req, payload={"sub": cross_user}, pid=str(pid)
                ))

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# T-146-C  git_provider_disconnect
# ---------------------------------------------------------------------------


class TestGitProviderDisconnect:
    """POST /projects/{pid}/git/provider/disconnect — remove mirror link."""

    def test_disconnect_round_trip(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        # First connect via provider directly so there is something to clear.
        from kerf_cloud.git_providers.github import GitHubProvider
        provider = GitHubProvider(_configured_settings(), pool=_make_pool(db_conn))
        run(provider.connect(str(pid), github_owner="acme", github_repo="my-design"))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        req = MagicMock()
        req.json = AsyncMock(return_value={"provider": "github"})
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            result = run(routes.git_provider_disconnect(
                req, payload={"sub": str(uid)}, pid=str(pid)
            ))
        finally:
            for p in reversed(ps):
                p.stop()

        assert result["disconnected"] is True
        assert result["kerf_git_retained"] is True
        note = result.get("note", "")
        assert "always retained" in note.lower() or "kerf" in note.lower()

        # Verify the DB was actually cleared.
        row = run(db_conn.fetchrow(
            "SELECT github_owner, github_repo FROM cloud_git_repos WHERE project_id = $1",
            pid,
        ))
        assert row["github_owner"] is None
        assert row["github_repo"] is None

    def test_disconnect_unknown_provider_raises_404(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        req = MagicMock()
        req.json = AsyncMock(return_value={"provider": "bitbucket"})
        req.body = AsyncMock(return_value=b"x")

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_disconnect(
                    req, payload={"sub": str(uid)}, pid=str(pid)
                ))
        finally:
            for p in reversed(ps):
                p.stop()

        assert exc_info.value.status_code == 404

    def test_disconnect_unauthenticated_raises_401(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import kerf_cloud.routes as _routes

        _app = FastAPI()
        _app.include_router(_routes.router)

        with TestClient(_app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/projects/00000000-0000-0000-0000-000000000001/git/provider/disconnect",
                json={"provider": "github"},
            )
        assert resp.status_code == 401

    def test_disconnect_cross_tenant_raises_404(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        cross_user = str(uuid.uuid4())

        async def _cross_tenant_editor(request, project_id, user_id):
            raise HTTPException(status_code=404, detail="project not found")

        req = MagicMock()
        req.json = AsyncMock(return_value={"provider": "github"})
        req.body = AsyncMock(return_value=b"x")

        pool = _make_pool(db_conn)
        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_editor", _cross_tenant_editor):
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_disconnect(
                    req, payload={"sub": cross_user}, pid=str(pid)
                ))

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# T-146-D  git_provider_status
# ---------------------------------------------------------------------------


class TestGitProviderStatus:
    """GET /projects/{pid}/git/provider/status — connection + last-sync status."""

    def test_status_returns_provider_list_and_note(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            result = run(routes.git_provider_status(
                _fake_request(), payload={"sub": str(uid)}, pid=str(pid)
            ))
        finally:
            for p in reversed(ps):
                p.stop()

        assert result["project_id"] == str(pid)
        assert isinstance(result["providers"], list)
        assert result["kerf_git_retained"] is True
        note = result.get("note", "")
        assert "always retained" in note.lower() or "kerf" in note.lower()

    def test_status_disconnected_when_no_mirror_set(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            result = run(routes.git_provider_status(
                _fake_request(), payload={"sub": str(uid)}, pid=str(pid)
            ))
        finally:
            for p in reversed(ps):
                p.stop()

        gh_status = next(
            (p for p in result["providers"] if p["provider"] == "github"), None
        )
        assert gh_status is not None
        assert gh_status["connected"] is False

    def test_status_connected_after_connect(self, db_conn, cleanup_after):
        """After connecting GitHub + writing token row, status shows connected=True."""
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        # Write owner's github token row so status can resolve installation_id.
        inst_id = 88000 + (uid.int % 1000)
        run(db_conn.execute(
            """
            INSERT INTO cloud_github_tokens
                (user_id, access_token_encrypted, scope, github_installation_id,
                 github_login, updated_at)
            VALUES ($1, $2, '', $3, 'testbot', now())
            ON CONFLICT (user_id) DO UPDATE
                SET github_installation_id = EXCLUDED.github_installation_id,
                    github_login = EXCLUDED.github_login,
                    updated_at = now()
            """,
            uid,
            b"placeholder",
            inst_id,
        ))

        # Connect via provider directly.
        from kerf_cloud.git_providers.github import GitHubProvider
        provider = GitHubProvider(_configured_settings(), pool=_make_pool(db_conn))
        run(provider.connect(str(pid), github_owner="acme", github_repo="my-design"))

        from kerf_cloud.git_providers.registry import _build_default_registry
        registry = _build_default_registry(_configured_settings())

        ps = _patches(db_conn, uid=str(uid), registry=registry)
        for p in ps:
            p.start()
        try:
            result = run(routes.git_provider_status(
                _fake_request(), payload={"sub": str(uid)}, pid=str(pid)
            ))
        finally:
            for p in reversed(ps):
                p.stop()

        gh_status = next(
            (p for p in result["providers"] if p["provider"] == "github"), None
        )
        assert gh_status is not None
        assert gh_status["connected"] is True
        assert gh_status["github_owner"] == "acme"
        assert gh_status["github_repo"] == "my-design"

    def test_status_unauthenticated_raises_401(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import kerf_cloud.routes as _routes

        _app = FastAPI()
        _app.include_router(_routes.router)

        with TestClient(_app, raise_server_exceptions=False) as c:
            resp = c.get(
                "/projects/00000000-0000-0000-0000-000000000001/git/provider/status"
            )
        assert resp.status_code == 401

    def test_status_cross_tenant_raises_404(self, db_conn, cleanup_after):
        import kerf_cloud.routes as routes

        uid = run(_make_user(db_conn))
        ws = run(_make_workspace(db_conn, uid))
        pid = run(_make_project(db_conn, ws))

        cross_user = str(uuid.uuid4())

        async def _cross_tenant_role(request, project_id, user_id):
            raise HTTPException(status_code=404, detail="project not found")

        pool = _make_pool(db_conn)
        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_role", _cross_tenant_role):
            with pytest.raises(HTTPException) as exc_info:
                run(routes.git_provider_status(
                    _fake_request(), payload={"sub": cross_user}, pid=str(pid)
                ))

        assert exc_info.value.status_code == 404
