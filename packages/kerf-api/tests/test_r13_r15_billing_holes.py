"""T-402b / T-409 — unit tests for R13 (BYO key save+validation) and R15 (blob presign).

All tests are pure-unit (no DB, no real HTTP) using mocks so they run in any
environment including CI without DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(fetchrow_return=None, execute_return="DELETE 1"):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock(return_value=execute_return)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


# ---------------------------------------------------------------------------
# R13 — save_provider_key: POST /api/provider-keys
# ---------------------------------------------------------------------------


class TestR13SaveProviderKey:
    """R13: save_provider_key validates key then upserts encrypted row."""

    def _payload(self, user_id: str | None = None) -> dict:
        return {"sub": user_id or str(uuid.uuid4())}

    # ---- happy path --------------------------------------------------------

    def test_valid_key_stores_encrypted_row(self):
        """Valid key → provider call succeeds → row upserted → 200."""
        from kerf_api.routes import save_provider_key, SaveProviderKeyRequest

        pool, conn = _make_pool()
        user_id = str(uuid.uuid4())
        req = SaveProviderKeyRequest(provider="anthropic", api_key="sk-ant-valid-key")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes._validate_provider_key", new=AsyncMock(return_value=None)), \
             patch("kerf_core.utils.encrypt.encrypt_secret", return_value=b"encrypted-blob"):
            result = _run(save_provider_key(req, payload=self._payload(user_id)))

        assert result == {"provider": "anthropic", "saved": True}
        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args
        assert "user_provider_keys" in call_args[0][0]
        # encrypted bytes passed to execute
        assert b"encrypted-blob" in call_args[0]

    def test_valid_openai_key_stores_row(self):
        """Valid OpenAI key → row upserted."""
        from kerf_api.routes import save_provider_key, SaveProviderKeyRequest

        pool, conn = _make_pool()
        req = SaveProviderKeyRequest(provider="openai", api_key="sk-oai-valid")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes._validate_provider_key", new=AsyncMock(return_value=None)), \
             patch("kerf_core.utils.encrypt.encrypt_secret", return_value=b"enc"):
            result = _run(save_provider_key(req, payload=self._payload()))

        assert result["saved"] is True
        assert result["provider"] == "openai"

    # ---- invalid key (provider returns 401) --------------------------------

    def test_invalid_key_returns_422_no_row_stored(self):
        """Provider call raises 422 → row is NOT stored; exception propagates."""
        from kerf_api.routes import save_provider_key, SaveProviderKeyRequest

        pool, conn = _make_pool()
        req = SaveProviderKeyRequest(provider="anthropic", api_key="sk-ant-bad")

        async def _fake_validate(provider, api_key):
            raise HTTPException(status_code=422, detail="provider_key_invalid")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes._validate_provider_key", side_effect=_fake_validate):
            with pytest.raises(HTTPException) as exc_info:
                _run(save_provider_key(req, payload=self._payload()))

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "provider_key_invalid"
        # DB must NOT have been touched
        conn.execute.assert_not_awaited()

    def test_unsupported_provider_returns_422(self):
        """Unknown provider name → 422 without touching DB."""
        from kerf_api.routes import save_provider_key, SaveProviderKeyRequest

        pool, conn = _make_pool()
        req = SaveProviderKeyRequest(provider="bad_provider", api_key="some-key")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
            with pytest.raises(HTTPException) as exc_info:
                _run(save_provider_key(req, payload=self._payload()))

        assert exc_info.value.status_code == 422
        conn.execute.assert_not_awaited()

    def test_empty_api_key_returns_422(self):
        """Empty api_key → 422 without DB touch."""
        from kerf_api.routes import save_provider_key, SaveProviderKeyRequest

        pool, conn = _make_pool()
        req = SaveProviderKeyRequest(provider="anthropic", api_key="   ")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
            with pytest.raises(HTTPException) as exc_info:
                _run(save_provider_key(req, payload=self._payload()))

        assert exc_info.value.status_code == 422
        conn.execute.assert_not_awaited()

    # ---- unauthenticated (require_auth dependency tested by framework) ------

    def test_require_auth_dependency_present(self):
        """save_provider_key must have require_auth in its dependencies."""
        import inspect
        from kerf_api.routes import save_provider_key
        from kerf_core.dependencies import require_auth
        sig = inspect.signature(save_provider_key)
        deps = [
            p.default
            for p in sig.parameters.values()
            if hasattr(p.default, "dependency")
        ]
        dep_funcs = [d.dependency for d in deps]
        assert require_auth in dep_funcs, (
            "save_provider_key must declare Depends(require_auth)"
        )


# ---------------------------------------------------------------------------
# R13 — delete_provider_key: DELETE /api/provider-keys/{provider}
# ---------------------------------------------------------------------------


class TestR13DeleteProviderKey:
    """R13: delete_provider_key removes the row for the authed user."""

    def _payload(self, user_id: str | None = None) -> dict:
        return {"sub": user_id or str(uuid.uuid4())}

    def test_existing_key_deleted(self):
        """Known provider+user → DELETE executes → 200."""
        from kerf_api.routes import delete_provider_key

        pool, conn = _make_pool(execute_return="DELETE 1")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
            result = _run(delete_provider_key("anthropic", payload=self._payload()))

        assert result == {"provider": "anthropic", "deleted": True}
        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args[0]
        assert "user_provider_keys" in call_args[0]

    def test_missing_key_returns_404(self):
        """No matching row (DELETE 0) → 404."""
        from kerf_api.routes import delete_provider_key

        pool, conn = _make_pool(execute_return="DELETE 0")

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
            with pytest.raises(HTTPException) as exc_info:
                _run(delete_provider_key("openai", payload=self._payload()))

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "provider_key_not_found"

    def test_require_auth_dependency_present(self):
        """delete_provider_key must have require_auth in its dependencies."""
        import inspect
        from kerf_api.routes import delete_provider_key
        from kerf_core.dependencies import require_auth
        sig = inspect.signature(delete_provider_key)
        deps = [
            p.default
            for p in sig.parameters.values()
            if hasattr(p.default, "dependency")
        ]
        dep_funcs = [d.dependency for d in deps]
        assert require_auth in dep_funcs, (
            "delete_provider_key must declare Depends(require_auth)"
        )


# ---------------------------------------------------------------------------
# R13 — _validate_provider_key internal logic
# ---------------------------------------------------------------------------


class TestR13ValidateProviderKey:
    """R13: _validate_provider_key makes a minimal live call per provider."""

    def _mock_response(self, status_code: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_anthropic_200_ok(self):
        """Anthropic 200 → no exception."""
        from kerf_api.routes import _validate_provider_key

        async def _fake_post(*a, **kw):
            return self._mock_response(200)

        client_ctx = AsyncMock()
        client_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=_fake_post))
        client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client_ctx):
            _run(_validate_provider_key("anthropic", "sk-ant-ok"))  # no exception

    def test_anthropic_401_raises_422(self):
        """Anthropic 401 → HTTPException 422 provider_key_invalid."""
        from kerf_api.routes import _validate_provider_key

        async def _fake_post(*a, **kw):
            return self._mock_response(401)

        client_ctx = AsyncMock()
        client_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=_fake_post))
        client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client_ctx):
            with pytest.raises(HTTPException) as exc_info:
                _run(_validate_provider_key("anthropic", "sk-ant-bad"))
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "provider_key_invalid"

    def test_openai_401_raises_422(self):
        """OpenAI 401 → HTTPException 422."""
        from kerf_api.routes import _validate_provider_key

        async def _fake_get(*a, **kw):
            return self._mock_response(401)

        client_ctx = AsyncMock()
        client_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(get=_fake_get))
        client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client_ctx):
            with pytest.raises(HTTPException) as exc_info:
                _run(_validate_provider_key("openai", "sk-bad"))
        assert exc_info.value.status_code == 422

    def test_gemini_400_raises_422(self):
        """Gemini 400 → HTTPException 422."""
        from kerf_api.routes import _validate_provider_key

        async def _fake_get(*a, **kw):
            return self._mock_response(400)

        client_ctx = AsyncMock()
        client_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(get=_fake_get))
        client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client_ctx):
            with pytest.raises(HTTPException) as exc_info:
                _run(_validate_provider_key("gemini", "bad-key"))
        assert exc_info.value.status_code == 422

    def test_unsupported_provider_raises_422(self):
        """Unknown provider name → 422 without HTTP call."""
        from kerf_api.routes import _validate_provider_key

        with pytest.raises(HTTPException) as exc_info:
            _run(_validate_provider_key("unknown_prov", "some-key"))
        assert exc_info.value.status_code == 422

    def test_network_error_raises_422_validation_failed(self):
        """Network exception → 422 provider_key_validation_failed."""
        from kerf_api.routes import _validate_provider_key

        async def _fail(*a, **kw):
            raise OSError("connection refused")

        client_ctx = AsyncMock()
        client_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=_fail))
        client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client_ctx):
            with pytest.raises(HTTPException) as exc_info:
                _run(_validate_provider_key("anthropic", "sk-ant-ok"))
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "provider_key_validation_failed"


# ---------------------------------------------------------------------------
# R15 — serve_project_blob presign redirect
# ---------------------------------------------------------------------------


class TestR15BlobPresign:
    """R15: serve_project_blob redirects to presigned URL when S3 backend."""

    def _make_request(self) -> MagicMock:
        req = MagicMock()
        return req

    def _make_pool_for_blob(self, workspace_id, visibility="public"):
        conn = AsyncMock()

        proj_row = MagicMock()
        proj_row.__getitem__ = lambda self, k: {
            "workspace_id": uuid.UUID(workspace_id),
            "visibility": visibility,
        }[k]

        conn.fetchrow = AsyncMock(return_value=proj_row)
        conn.fetchval = AsyncMock(return_value=1)  # blob_refs row exists

        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        return pool

    def test_s3_backend_returns_302_redirect(self):
        """STORAGE_BACKEND=s3 → 302 redirect to presigned URL."""
        from kerf_api.routes import serve_project_blob
        from kerf_core.storage.s3 import S3Storage
        from fastapi.responses import RedirectResponse

        pid = str(uuid.uuid4())
        oid = "a" * 64  # fake sha256
        ws_id = str(uuid.uuid4())
        fake_presigned = "https://tigris.example.com/key?sig=abc123"

        pool = self._make_pool_for_blob(ws_id, "public")

        storage = MagicMock(spec=S3Storage)
        storage.signed_url = AsyncMock(return_value=fake_presigned)

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes.get_storage_required", return_value=storage), \
             patch("kerf_api.routes.blob_storage_key", return_value=f"blobs/{oid}"):
            result = _run(serve_project_blob(
                request=self._make_request(),
                pid=pid,
                oid=oid,
                auth=None,
                _rl=None,
            ))

        assert isinstance(result, RedirectResponse), (
            f"expected RedirectResponse, got {type(result)}"
        )
        assert result.status_code == 302
        storage.signed_url.assert_awaited_once_with(f"blobs/{oid}", ttl_seconds=900)

    def test_local_backend_streams_bytes(self):
        """Local storage backend → StreamingResponse (not redirect)."""
        from kerf_api.routes import serve_project_blob
        from kerf_core.storage.local import LocalStorage
        from fastapi.responses import StreamingResponse

        pid = str(uuid.uuid4())
        oid = "b" * 64
        ws_id = str(uuid.uuid4())

        pool = self._make_pool_for_blob(ws_id, "public")

        import io
        storage = MagicMock(spec=LocalStorage)
        storage.get = AsyncMock(return_value=(io.BytesIO(b"blob-data"), "application/octet-stream"))

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes.get_storage_required", return_value=storage), \
             patch("kerf_api.routes.blob_storage_key", return_value=f"blobs/{oid}"):
            result = _run(serve_project_blob(
                request=self._make_request(),
                pid=pid,
                oid=oid,
                auth=None,
                _rl=None,
            ))

        assert isinstance(result, StreamingResponse), (
            f"expected StreamingResponse for local backend, got {type(result)}"
        )

    def test_s3_presign_failure_returns_404(self):
        """S3 presign throws → 404, not 500."""
        from kerf_api.routes import serve_project_blob
        from kerf_core.storage.s3 import S3Storage

        pid = str(uuid.uuid4())
        oid = "c" * 64
        ws_id = str(uuid.uuid4())

        pool = self._make_pool_for_blob(ws_id, "public")

        storage = MagicMock(spec=S3Storage)
        storage.signed_url = AsyncMock(side_effect=RuntimeError("S3 error"))

        with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)), \
             patch("kerf_api.routes.get_storage_required", return_value=storage), \
             patch("kerf_api.routes.blob_storage_key", return_value=f"blobs/{oid}"):
            with pytest.raises(HTTPException) as exc_info:
                _run(serve_project_blob(
                    request=self._make_request(),
                    pid=pid,
                    oid=oid,
                    auth=None,
                    _rl=None,
                ))

        assert exc_info.value.status_code == 404

    def test_no_todo_t409_marker_in_source(self):
        """R15 complete: TODO(T-409) marker must be removed from routes.py."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        assert "TODO(T-409)" not in src, (
            "R15: TODO(T-409) marker still present — presign not implemented"
        )

    def test_serve_project_blob_has_rate_limit_dependency(self):
        """serve_project_blob must retain its rate_limit dependency."""
        import inspect
        from kerf_api.routes import serve_project_blob
        sig = inspect.signature(serve_project_blob)
        param_names = list(sig.parameters.keys())
        assert "_rl" in param_names, (
            "serve_project_blob missing rate_limit dependency (_rl param)"
        )
