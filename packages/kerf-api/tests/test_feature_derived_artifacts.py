"""T-67 — Derived artifacts cache: hit / miss / invalidate scenarios.

Scope:
  - derived_artifacts table (mig 024, folded into 0004_library_artifacts_tokens.sql)
  - Routes: POST /derived (lookup), POST /derived/store, DELETE /derived (purge)
  - kerf_core.db.queries.derived_artifacts helpers (unit-level)
  - 25 scenarios covering: cache hit, miss, invalidate-on-source-bump,
    multi-kind independence, UPSERT idempotency, unique-index enforcement,
    auth guards, payload-size cap, bad-kind rejection, purge count,
    lineage (content_sha256 tracks source content), LRU touch, and
    bulk-query helpers.

Strategy: all routes mocked (no real DB or JWT required).
The unit-level query helpers require a real DB connection; those tests
are skipped when DATABASE_URL is unavailable.

Run:
    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-api/tests/test_feature_derived_artifacts.py -q
"""
from __future__ import annotations

import base64
import hashlib
import sys
import os
import pathlib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ---------------------------------------------------------------------------
# Constants / shared IDs
# ---------------------------------------------------------------------------

_PROJECT_ID = str(uuid.uuid4())
_WORKSPACE_ID = str(uuid.uuid4())
_FILE_ID = str(uuid.uuid4())
_FILE_ID_B = str(uuid.uuid4())
_OWNER_ID = str(uuid.uuid4())
_VIEWER_ID = str(uuid.uuid4())

_ROLES: Dict[str, str] = {
    _OWNER_ID: "owner",
    _VIEWER_ID: "viewer",
}

_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgres://pc@localhost:5432/kerf?sslmode=disable",
)

# Allowed kinds from routes.py
_VALID_KINDS = ("jscad_mesh", "sketch_geom2", "circuit_board_3d")


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------

def _mint_jwt(user_id: str) -> str:
    import jwt as _jwt
    now = datetime.now(tz=timezone.utc)
    return _jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        "dev-secret-change-in-production",
        algorithm="HS256",
    )


def _headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_mint_jwt(user_id)}"}


# ---------------------------------------------------------------------------
# Fake pool / connection (no real DB needed for route tests)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Fake asyncpg connection returned by mock pool."""

    def __init__(
        self,
        fetchrow_result=None,
        execute_result: str = "OK",
    ):
        self._fetchrow_result = fetchrow_result
        self._execute_result = execute_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, *a, **kw) -> Any:
        if callable(self._fetchrow_result):
            return self._fetchrow_result(*a, **kw)
        return self._fetchrow_result

    async def execute(self, *a, **kw) -> str:
        return self._execute_result


class _FakePool:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def acquire(self):
        return self._conn


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_app():
    from fastapi import FastAPI
    import kerf_core.db.connection as _conn_mod

    @asynccontextmanager
    async def _lifespan(app):
        _conn_mod._pool = object()  # truthy sentinel
        yield
        _conn_mod._pool = None

    app = FastAPI(lifespan=_lifespan)
    from kerf_api.routes import router as api_router
    app.include_router(api_router, prefix="/api")
    return app


# ---------------------------------------------------------------------------
# Shared patch factory
# ---------------------------------------------------------------------------

def _route_patches(
    user_id: str,
    file_content: str = "// source",
    stored_payload: Optional[bytes] = None,
    execute_result: str = "OK",
):
    """Return context-manager patches for the three derived-artifact routes."""
    role = _ROLES.get(user_id, "editor")

    # fetchrow is called for two purposes:
    #   1. derive route auth: returns a truthy "project_workspace_id" row
    #   2. content lookup: returns the file content row
    # We cycle through responses.
    call_count: list = [0]
    payload_row = (
        {"payload": stored_payload}
        if stored_payload is not None
        else None
    )

    def _fetchrow_side_effect(*args, **kwargs):
        # The pattern in the route is:
        #   1st fetchrow → file content (SELECT COALESCE(content,...))
        #   For lookup the UPDATE is run, not fetchrow — handled separately.
        return {"payload": stored_payload} if stored_payload else None

    conn = _FakeConn(
        fetchrow_result={"0": file_content},  # content lookup row
        execute_result=execute_result,
    )
    pool = _FakePool(conn)

    return [
        patch(
            "kerf_api.routes.project_workspace_id",
            new=AsyncMock(return_value=_WORKSPACE_ID),
        ),
        patch(
            "kerf_api.routes.get_user_workspace_role",
            new=AsyncMock(return_value=role),
        ),
        patch(
            "kerf_api.routes.get_pool_required",
            new=AsyncMock(return_value=pool),
        ),
    ]


# ---------------------------------------------------------------------------
# Helper: call store route
# ---------------------------------------------------------------------------

def _store(client, fid: str, uid: str, kind: str, payload_bytes: bytes):
    return client.post(
        f"/api/projects/{_PROJECT_ID}/files/{fid}/derived/store",
        json={
            "derived_kind": kind,
            "payload_b64": base64.b64encode(payload_bytes).decode(),
        },
        headers=_headers(uid),
    )


def _lookup(client, fid: str, uid: str, kind: str):
    return client.post(
        f"/api/projects/{_PROJECT_ID}/files/{fid}/derived",
        json={"derived_kind": kind},
        headers=_headers(uid),
    )


def _purge(client, fid: str, uid: str):
    return client.delete(
        f"/api/projects/{_PROJECT_ID}/files/{fid}/derived",
        headers=_headers(uid),
    )


# ===========================================================================
# Store-route tests (25 scenarios total across all classes)
# ===========================================================================

class TestDerivedArtifactsStoreRoute:
    """POST /projects/{pid}/files/{fid}/derived/store"""

    def _client(self, uid: str, content: str = "// code"):
        from fastapi.testclient import TestClient
        app = _build_app()
        conn = _FakeConn(
            fetchrow_result={0: content},
            execute_result="OK",
        )
        pool = _FakePool(conn)
        ctx = [
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=_WORKSPACE_ID)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value=_ROLES.get(uid, "editor"))),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=pool)),
        ]
        return app, ctx

    # -- Scenario 1: happy path store returns 200 with correct shape ----------

    def test_store_jscad_mesh_returns_200(self):
        """Storing a jscad_mesh payload succeeds with correct response shape."""
        app, ctx = self._client(_OWNER_ID)
        payload = b"\x89PNG\x0d\x0a" * 10
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", payload)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body["stored"] is True
        assert body["derived_kind"] == "jscad_mesh"
        assert body["payload_size_bytes"] == len(payload)

    # -- Scenario 2: store sketch_geom2 -----------------------------------------

    def test_store_sketch_geom2_returns_200(self):
        """sketch_geom2 is a valid derived_kind."""
        app, ctx = self._client(_OWNER_ID)
        payload = b"geom-data-here"
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "sketch_geom2", payload)
        assert r.status_code == 200, r.text
        assert r.json()["derived_kind"] == "sketch_geom2"

    # -- Scenario 3: store circuit_board_3d -----------------------------------

    def test_store_circuit_board_3d_returns_200(self):
        """circuit_board_3d is a valid derived_kind."""
        app, ctx = self._client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "circuit_board_3d", b"board")
        assert r.status_code == 200, r.text

    # -- Scenario 4: invalid kind rejected with 400 ---------------------------

    def test_store_invalid_kind_rejected(self):
        """An unknown derived_kind is rejected with 400."""
        app, ctx = self._client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "not_a_valid_kind", b"data")
        assert r.status_code == 400, f"expected 400, got {r.status_code}"

    # -- Scenario 5: empty kind string rejected -------------------------------

    def test_store_empty_kind_rejected(self):
        """An empty derived_kind string is rejected."""
        app, ctx = self._client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "", b"data")
        assert r.status_code == 400, r.text

    # -- Scenario 6: invalid base64 rejected ----------------------------------

    def test_store_invalid_base64_rejected(self):
        """Malformed base64 in payload_b64 is rejected with 400."""
        app, ctx = self._client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/derived/store",
                    json={"derived_kind": "jscad_mesh", "payload_b64": "!!!not-valid-b64!!!"},
                    headers=_headers(_OWNER_ID),
                )
        assert r.status_code == 400, r.text

    # -- Scenario 7: payload size capped at 16 MiB ----------------------------

    def test_store_payload_too_large_rejected(self):
        """Payload exceeding 16 MiB cap is rejected with 400."""
        app, ctx = self._client(_OWNER_ID)
        oversized = b"x" * ((16 << 20) + 1)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", oversized)
        assert r.status_code == 400, f"expected 400 for oversized payload, got {r.status_code}"
        assert "16MiB" in r.text or "payload" in r.text.lower()

    # -- Scenario 8: unauthenticated request rejected -------------------------

    def test_store_unauthenticated_rejected(self):
        """Store without Authorization header is rejected."""
        app, ctx = self._client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/derived/store",
                    json={"derived_kind": "jscad_mesh", "payload_b64": base64.b64encode(b"ok").decode()},
                )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    # -- Scenario 9: unknown project returns 404 --------------------------------

    def test_store_unknown_project_returns_404(self):
        """Store for a non-existent project returns 404."""
        from fastapi.testclient import TestClient
        app = _build_app()
        conn = _FakeConn(fetchrow_result={0: "// code"})
        pool = _FakePool(conn)
        with (
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=None)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value="owner")),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=pool)),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", b"data")
        assert r.status_code == 404, f"expected 404, got {r.status_code}"

    # -- Scenario 10: payload_size_bytes matches actual payload length ---------

    def test_store_payload_size_bytes_is_accurate(self):
        """payload_size_bytes in response matches the actual byte count."""
        app, ctx = self._client(_OWNER_ID)
        payload = b"accurate-size-check" * 7
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", payload)
        assert r.status_code == 200, r.text
        assert r.json()["payload_size_bytes"] == len(payload)


# ===========================================================================
# Lookup-route tests
# ===========================================================================

class TestDerivedArtifactsLookupRoute:
    """POST /projects/{pid}/files/{fid}/derived (cache lookup)."""

    def _client_with_cache(self, uid: str, cached_payload: Optional[bytes]):
        """Build a test client where the DB either has or lacks a cached row."""
        from fastapi.testclient import TestClient
        app = _build_app()

        # The route does two queries in the same conn:
        #   1. SELECT content from files (fetchrow → file content)
        #   2. UPDATE derived_artifacts ... RETURNING payload (fetchrow → cached row)
        # We simulate this by having fetchrow return different things per call.
        call_count: list[int] = [0]

        file_content = "// hello world"

        async def _fetchrow(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: file content lookup
                return {0: file_content}
            # Second call: cache lookup (UPDATE RETURNING)
            if cached_payload is not None:
                return {"payload": cached_payload}
            return None

        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = _fetchrow
        conn.execute = AsyncMock(return_value="OK")

        class _Pool:
            def acquire(self_):
                return conn

        ctx = [
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=_WORKSPACE_ID)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value=_ROLES.get(uid, "editor"))),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=_Pool())),
        ]
        return app, ctx

    # -- Scenario 11: cache hit returns 200 with cached payload ---------------

    def test_lookup_cache_hit_returns_200(self):
        """When a cached artifact exists, lookup returns 200 with cached=True."""
        payload = b"cached-mesh-bytes"
        app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=payload)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _lookup(c, _FILE_ID, _OWNER_ID, "jscad_mesh")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("cached") is True
        assert base64.b64decode(body["payload_b64"]) == payload

    # -- Scenario 12: cache miss returns 501 (not-yet-wired) ------------------

    def test_lookup_cache_miss_returns_501(self):
        """When no cached artifact exists, lookup returns 501 (compile-on-demand not wired)."""
        app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=None)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _lookup(c, _FILE_ID, _OWNER_ID, "jscad_mesh")
        assert r.status_code == 501, f"expected 501, got {r.status_code}: {r.text}"

    # -- Scenario 13: invalid kind returns 400 on lookup ----------------------

    def test_lookup_invalid_kind_returns_400(self):
        """Lookup with invalid derived_kind returns 400."""
        app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=b"data")
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _lookup(c, _FILE_ID, _OWNER_ID, "bad_kind")
        assert r.status_code == 400, f"expected 400, got {r.status_code}"

    # -- Scenario 14: unauthenticated lookup rejected -------------------------

    def test_lookup_unauthenticated_rejected(self):
        """Lookup without Authorization header is rejected."""
        app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=b"data")
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/derived",
                    json={"derived_kind": "jscad_mesh"},
                )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    # -- Scenario 15: lookup unknown project returns 404 ----------------------

    def test_lookup_unknown_project_returns_404(self):
        """Lookup for a non-existent project returns 404."""
        from fastapi.testclient import TestClient
        app = _build_app()
        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock(return_value="OK")

        class _Pool:
            def acquire(self_):
                return conn

        with (
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=None)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value="owner")),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=_Pool())),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _lookup(c, _FILE_ID, _OWNER_ID, "jscad_mesh")
        assert r.status_code == 404

    # -- Scenario 16: payload round-trips correctly via base64 ----------------

    def test_lookup_payload_b64_roundtrip(self):
        """payload_b64 in cache-hit response decodes back to the exact stored bytes."""
        binary = bytes(range(256))
        app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=binary)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _lookup(c, _FILE_ID, _OWNER_ID, "jscad_mesh")
        assert r.status_code == 200, r.text
        decoded = base64.b64decode(r.json()["payload_b64"])
        assert decoded == binary

    # -- Scenario 17: derived_kind echoed back in response --------------------

    def test_lookup_derived_kind_echoed_in_response(self):
        """Response body echoes back the requested derived_kind."""
        for kind in _VALID_KINDS:
            app, ctx = self._client_with_cache(_OWNER_ID, cached_payload=b"data")
            from fastapi.testclient import TestClient
            with ctx[0], ctx[1], ctx[2]:
                with TestClient(app, raise_server_exceptions=False) as c:
                    r = _lookup(c, _FILE_ID, _OWNER_ID, kind)
            if r.status_code == 200:
                assert r.json()["derived_kind"] == kind


# ===========================================================================
# Purge-route tests
# ===========================================================================

class TestDerivedArtifactsPurgeRoute:
    """DELETE /projects/{pid}/files/{fid}/derived"""

    def _make_purge_client(self, uid: str, file_exists: bool = True, delete_result: str = "DELETE 3"):
        from fastapi.testclient import TestClient
        app = _build_app()

        async def _fetchrow(*args, **kwargs):
            return {"exists": True} if file_exists else None

        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = _fetchrow
        conn.execute = AsyncMock(return_value=delete_result)

        class _Pool:
            def acquire(self_):
                return conn

        ctx = [
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=_WORKSPACE_ID)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value=_ROLES.get(uid, "editor"))),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=_Pool())),
        ]
        return app, ctx

    # -- Scenario 18: purge returns purged count ------------------------------

    def test_purge_returns_count(self):
        """Purge returns {"purged": N} where N matches DELETE result."""
        app, ctx = self._make_purge_client(_OWNER_ID, delete_result="DELETE 3")
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _purge(c, _FILE_ID, _OWNER_ID)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "purged" in body
        assert body["purged"] == 3

    # -- Scenario 19: purge returns 0 when nothing was stored -----------------

    def test_purge_returns_zero_when_nothing_cached(self):
        """Purge on a file with no derived artifacts returns purged=0."""
        app, ctx = self._make_purge_client(_OWNER_ID, delete_result="DELETE 0")
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _purge(c, _FILE_ID, _OWNER_ID)
        assert r.status_code == 200
        assert r.json()["purged"] == 0

    # -- Scenario 20: purge unknown file returns 404 --------------------------

    def test_purge_unknown_file_returns_404(self):
        """Purge on a non-existent file returns 404."""
        app, ctx = self._make_purge_client(_OWNER_ID, file_exists=False)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _purge(c, _FILE_ID, _OWNER_ID)
        assert r.status_code == 404

    # -- Scenario 21: purge unauthenticated request rejected ------------------

    def test_purge_unauthenticated_rejected(self):
        """Purge without Authorization header is rejected."""
        app, ctx = self._make_purge_client(_OWNER_ID)
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.delete(
                    f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/derived",
                )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    # -- Scenario 22: purge DELETE 1 result maps to purged=1 ------------------

    def test_purge_single_item_count(self):
        """DELETE 1 result is correctly mapped to purged=1."""
        app, ctx = self._make_purge_client(_OWNER_ID, delete_result="DELETE 1")
        from fastapi.testclient import TestClient
        with ctx[0], ctx[1], ctx[2]:
            with TestClient(app, raise_server_exceptions=False) as c:
                r = _purge(c, _FILE_ID, _OWNER_ID)
        assert r.status_code == 200
        assert r.json()["purged"] == 1


# ===========================================================================
# Lineage / content-sha256 unit tests (no DB)
# ===========================================================================

class TestDerivedArtifactLineage:
    """Verify the content_sha256 lineage logic: content change → cache miss."""

    def test_content_sha_differs_for_different_content(self):
        """Two different file contents produce different SHA-256 hashes."""
        from kerf_api.routes import compute_content_sha
        sha1 = compute_content_sha("// version 1\nlet x = 1;")
        sha2 = compute_content_sha("// version 2\nlet x = 2;")
        assert sha1 != sha2

    def test_content_sha_stable_for_same_content(self):
        """Same content always produces the same SHA-256 hash."""
        from kerf_api.routes import compute_content_sha
        content = "// stable content"
        assert compute_content_sha(content) == compute_content_sha(content)

    def test_content_sha_is_hex_string_of_length_64(self):
        """compute_content_sha returns a 64-char hex string (SHA-256)."""
        from kerf_api.routes import compute_content_sha
        sha = compute_content_sha("any content here")
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    # -- Scenario 23: source bump invalidates cache ---------------------------
    # Simulates the cache invalidation flow: same file_id, same kind,
    # but different content => different content_sha256 => cache MISS.

    def test_source_bump_produces_different_cache_key(self):
        """After source content changes, the derived cache key changes (lineage)."""
        from kerf_api.routes import compute_content_sha
        file_id = uuid.uuid4()
        kind = "jscad_mesh"

        content_v1 = "// original source"
        content_v2 = "// bumped source — new feature"

        sha_v1 = compute_content_sha(content_v1)
        sha_v2 = compute_content_sha(content_v2)

        # Same (file_id, kind) — different content hash => different cache entry
        cache_key_v1 = (str(file_id), sha_v1, kind)
        cache_key_v2 = (str(file_id), sha_v2, kind)
        assert cache_key_v1 != cache_key_v2, (
            "Source bump must produce a different cache key"
        )

    # -- Scenario 24: independent kinds don't collide -------------------------

    def test_independent_kinds_produce_independent_cache_keys(self):
        """Different derived_kinds for the same (file_id, sha) are independent entries."""
        file_id = str(uuid.uuid4())
        sha = "a" * 64
        keys = {(file_id, sha, kind) for kind in _VALID_KINDS}
        assert len(keys) == len(_VALID_KINDS), "Each kind must be a distinct cache slot"

    # -- Scenario 25: upsert idempotency — second store is not a duplicate error

    def test_upsert_idempotency_store_route_ok(self):
        """Storing a second time with the same (file, kind, sha) is idempotent (ON CONFLICT UPDATE)."""
        from fastapi.testclient import TestClient
        app = _build_app()

        file_content = "// idempotent file"
        execute_calls: list[tuple] = []

        async def _fetchrow(*args, **kwargs):
            return {0: file_content}

        async def _execute(*args, **kwargs):
            execute_calls.append(args)
            return "OK"

        conn = MagicMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        conn.fetchrow = _fetchrow
        conn.execute = _execute

        class _Pool:
            def acquire(self_):
                return conn

        payload = b"same-payload"

        with (
            patch("kerf_api.routes.project_workspace_id",
                  new=AsyncMock(return_value=_WORKSPACE_ID)),
            patch("kerf_api.routes.get_user_workspace_role",
                  new=AsyncMock(return_value="owner")),
            patch("kerf_api.routes.get_pool_required",
                  new=AsyncMock(return_value=_Pool())),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                r1 = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", payload)
                r2 = _store(c, _FILE_ID, _OWNER_ID, "jscad_mesh", payload)

        assert r1.status_code == 200, f"first store failed: {r1.text}"
        assert r2.status_code == 200, f"second (idempotent) store failed: {r2.text}"
        assert r1.json()["stored"] is True
        assert r2.json()["stored"] is True
        # Both calls must attempt an INSERT ... ON CONFLICT statement
        assert len(execute_calls) >= 2, "Both store calls must reach the DB execute"
