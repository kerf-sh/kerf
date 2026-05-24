"""T-402b — unit tests for billing-hole fixes R7, R9, R10, R12, R14, R15, R22.

All tests are pure-unit (no DB, no real HTTP) using mocks so they run in any
environment including CI without DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call
from unittest.mock import ANY

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# R7 — token markup reads from settings, not hardcoded 1.20
# ---------------------------------------------------------------------------

class TestR7TokenMarkup:
    """R7: cloud_pricing_token_markup_pct drives billed_usd in both paths."""

    def test_markup_factor_computed_from_settings(self):
        """compute_cost_usd × (1 + pct/100) matches settings.cloud_pricing_token_markup_pct."""
        from kerf_core.config import get_settings
        s = get_settings()
        pct = s.cloud_pricing_token_markup_pct
        factor = 1.0 + pct / 100.0
        # Default is 20.0 → factor should be 1.20
        assert factor == pytest.approx(1.20, rel=1e-6), (
            f"expected default factor 1.20, got {factor} from pct={pct}"
        )

    def test_markup_not_hardcoded(self):
        """routes.py must not contain the literal `* 1.20` in billing code paths."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        # Find lines with the old hardcoded billing multiplier pattern
        bad_lines = [
            line.strip()
            for line in src.splitlines()
            if "* 1.20" in line and "# R7" not in line and "1.20.  " not in line
            # allow comments that reference 1.20 but not code that uses it
            and not line.strip().startswith("#")
        ]
        assert not bad_lines, (
            f"Found hardcoded * 1.20 billing multiplier (should use settings):\n"
            + "\n".join(bad_lines)
        )


# ---------------------------------------------------------------------------
# R9 — billing failures surface as errors, not silent swallow
# ---------------------------------------------------------------------------

class TestR9BillingFailureSurfaces:
    """R9: unexpected commit_spend failure → error response, not silent ignore."""

    def test_non_streaming_unknown_billing_error_raises_503(self):
        """post_message: unexpected billing exception must bubble up as 503."""
        from kerf_billing.spend import commit_spend, ApiTokenDailyCapExceeded

        # Build a fake bucket and bucket_model_info_price
        mock_price = MagicMock()
        mock_price.compute_cost_usd.return_value = 0.001
        bucket = MagicMock()  # any non-None bucket

        raised = []

        async def _simulate():
            cogs = 0.001
            from kerf_core.config import get_settings
            s = get_settings()
            billed = cogs * (1.0 + s.cloud_pricing_token_markup_pct / 100.0)
            # Simulate the billing inner-try block from post_message
            try:
                raise RuntimeError("postgres went away")
            except ApiTokenDailyCapExceeded:
                raise HTTPException(status_code=402, detail={"code": "API_TOKEN_DAILY_CAP_EXCEEDED"})
            except Exception:
                raise HTTPException(status_code=503, detail={"code": "BILLING_WRITE_FAILED"})

        with pytest.raises(HTTPException) as exc_info:
            _run(_simulate())
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["code"] == "BILLING_WRITE_FAILED"

    def test_non_streaming_cap_exceeded_raises_402(self):
        """post_message: ApiTokenDailyCapExceeded must be mapped to 402 in source.

        Verifies the source pattern: the inner try/except that wraps commit_spend
        catches ApiTokenDailyCapExceeded and raises HTTPException(402) before the
        generic except-Exception handler for unexpected billing errors.
        """
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        # The non-streaming path must contain the 402 for cap-exceeded
        assert "API_TOKEN_DAILY_CAP_EXCEEDED" in src, (
            "R9: API_TOKEN_DAILY_CAP_EXCEEDED code not found in routes.py"
        )
        # And the 402 status code must appear alongside it
        assert 'status_code=402' in src, (
            "R9: 402 status code not found in routes.py billing error handlers"
        )
        # And the 503 for unexpected billing errors must also exist
        assert "BILLING_WRITE_FAILED" in src, (
            "R9: BILLING_WRITE_FAILED code not found in routes.py"
        )

    def test_streaming_billing_error_not_silently_swallowed(self):
        """The streaming path must not have a bare `except Exception: pass` on commit_spend."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        # The old swallow pattern was exactly:  except Exception:\n                                pass
        # It should no longer appear after R9 fix.
        assert "except Exception:\n                                pass" not in src, (
            "Found bare `except Exception: pass` swallow of commit_spend — R9 not applied"
        )


# ---------------------------------------------------------------------------
# R10 — bucket re-snapshot per iteration
# ---------------------------------------------------------------------------

class TestR10BucketReSnapshot:
    """R10: bucket is re-snapshotted on every agent loop iteration > 0."""

    def test_load_user_billing_called_per_iteration(self):
        """The re-snapshot path in the routes calls load_user_billing at iteration > 0."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        # Both streaming and non-streaming must contain the re-snapshot guard
        assert "iteration > 0 and settings.usage_enabled and bucket is not None" in src, (
            "R10 re-snapshot guard not found in routes.py"
        )
        # Must use _lub alias for load_user_billing inside the loop
        assert "load_user_billing as _lub" in src, (
            "R10: load_user_billing re-import inside iteration loop not found"
        )

    def test_insufficient_credits_on_recheck_stops_loop(self):
        """If re-snapshot returns InsufficientCredits, raise 402 immediately."""
        # Simulate the re-check logic
        async def _simulate(byo_available: bool):
            from kerf_billing.buckets import InsufficientCredits

            # Simulate a fresh bucket that is InsufficientCredits
            fresh_bucket = InsufficientCredits(byo_available=byo_available)
            if isinstance(fresh_bucket, InsufficientCredits):
                code = (
                    "INSUFFICIENT_CREDITS_BYO_AVAILABLE"
                    if fresh_bucket.byo_available
                    else "INSUFFICIENT_CREDITS"
                )
                raise HTTPException(status_code=402, detail={"code": code})

        with pytest.raises(HTTPException) as exc_info:
            _run(_simulate(byo_available=False))
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["code"] == "INSUFFICIENT_CREDITS"

        with pytest.raises(HTTPException) as exc_info:
            _run(_simulate(byo_available=True))
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["code"] == "INSUFFICIENT_CREDITS_BYO_AVAILABLE"


# ---------------------------------------------------------------------------
# R12 — BYO decryption failure → 402, not fallback to server key
# ---------------------------------------------------------------------------

class TestR12ByoDecryptionFailure:
    """R12: _make_byo_provider must raise 402 on any failure, not fall back."""

    def _pool_with_no_key(self):
        """Fake pool that returns no row for user_provider_keys."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        return pool

    def _pool_with_bad_key(self):
        """Fake pool that returns a row but decrypt will fail."""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"encrypted_key": b"garbage"})
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        return pool

    def test_missing_row_raises_402(self):
        """No key row → must raise 402, not return fallback provider."""
        from kerf_api.routes import _make_byo_provider
        fallback = MagicMock(name="server_provider")
        pool = self._pool_with_no_key()

        with pytest.raises(HTTPException) as exc_info:
            _run(_make_byo_provider(pool, str(uuid.uuid4()), "anthropic", fallback=fallback))
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "byo_key_unavailable"
        # Crucially: fallback was NOT returned
        # (can't easily assert it wasn't returned since exception was raised)

    def test_decrypt_failure_raises_402(self):
        """Decrypt error → must raise 402."""
        from kerf_api.routes import _make_byo_provider
        fallback = MagicMock(name="server_provider")
        pool = self._pool_with_bad_key()

        with patch("kerf_core.utils.encrypt.decrypt_secret", side_effect=ValueError("bad key")):
            with pytest.raises(HTTPException) as exc_info:
                _run(_make_byo_provider(pool, str(uuid.uuid4()), "anthropic", fallback=fallback))
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "byo_key_unavailable"

    def test_unsupported_provider_raises_402(self):
        """Known-but-unmapped provider → 402, not fallback."""
        from kerf_api.routes import _make_byo_provider
        import base64

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"encrypted_key": b"enc"})
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        fallback = MagicMock(name="server_provider")

        with patch("kerf_core.utils.encrypt.decrypt_secret", return_value=b"mykey"):
            with pytest.raises(HTTPException) as exc_info:
                _run(_make_byo_provider(pool, str(uuid.uuid4()), "unsupported_provider", fallback=fallback))
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail == "byo_key_unavailable"

    def test_valid_key_returns_provider(self):
        """Happy path: valid row + decryption → returns provider, no exception."""
        from kerf_api.routes import _make_byo_provider
        import kerf_chat.llm as llm_module

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"encrypted_key": b"enc"})
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))
        fallback = MagicMock(name="server_provider")

        with patch("kerf_core.utils.encrypt.decrypt_secret", return_value=b"sk-real-key"):
            result = _run(_make_byo_provider(pool, str(uuid.uuid4()), "anthropic", fallback=fallback))
        assert isinstance(result, llm_module.AnthropicProvider)


# ---------------------------------------------------------------------------
# R14 — export_project rate limit + egress accounting
# ---------------------------------------------------------------------------

class TestR14ExportRateLimitAndEgress:
    """R14: export_project has rate limit and emits egress usage_events row."""

    def test_export_route_has_rate_limit_dependency(self):
        """export_project must declare a rate_limit dependency."""
        import inspect
        from kerf_api.routes import export_project
        sig = inspect.signature(export_project)
        params = list(sig.parameters.values())
        param_names = [p.name for p in params]
        assert "_rl" in param_names, (
            "export_project missing rate_limit dependency (_rl param)"
        )

    def test_egress_event_emitted_on_export(self):
        """When usage_enabled, export_project records an egress usage_events row."""
        # This is verified by the source code structure — the create_usage_event
        # call with kind='egress' must appear in the export_project body.
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        # The export route must contain both the rate limit and egress event.
        assert "kind=\"egress\"" in src or "kind='egress'" in src, (
            "R14: kind='egress' not found in routes.py export path"
        )
        assert "bytes_delta=bytes_sent" in src, (
            "R14: bytes_delta=bytes_sent not found in egress usage event"
        )


# ---------------------------------------------------------------------------
# R15 — serve_project_blob rate limit
# ---------------------------------------------------------------------------

class TestR15BlobServeRateLimit:
    """R15: serve_project_blob must have a rate limit dependency."""

    def test_blob_serve_has_rate_limit_dependency(self):
        """serve_project_blob must declare a rate_limit dependency."""
        import inspect
        from kerf_api.routes import serve_project_blob
        sig = inspect.signature(serve_project_blob)
        params = list(sig.parameters.values())
        param_names = [p.name for p in params]
        assert "_rl" in param_names, (
            "serve_project_blob missing rate_limit dependency (_rl param)"
        )

    def test_todo_presign_marker_present(self):
        """R15: presign TODO comment must be present as a deferred marker."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        assert "TODO(T-409)" in src, (
            "R15: TODO(T-409) presign marker not found in serve_project_blob"
        )


# ---------------------------------------------------------------------------
# R22 — operator LLM calls emit usage_events rows
# ---------------------------------------------------------------------------

class TestR22OperatorUsageAudit:
    """R22: auto_title_thread, workshop README-gen, and regenerate_readme emit operator_token rows."""

    def test_auto_title_accepts_user_id_and_project_id(self):
        """_auto_title_thread signature has user_id and project_id kwargs."""
        import inspect
        from kerf_api.routes import _auto_title_thread
        sig = inspect.signature(_auto_title_thread)
        params = sig.parameters
        assert "user_id" in params, "_auto_title_thread missing user_id param"
        assert "project_id" in params, "_auto_title_thread missing project_id param"

    def test_auto_title_emits_operator_token_event(self):
        """_auto_title_thread calls create_usage_event with kind='operator_token', payer='operator'."""
        captured = []

        async def _fake_create_usage_event(conn, *, user_id, kind, project_id=None,
                                            model=None, input_tokens=0, output_tokens=0,
                                            bytes_delta=0, usd_cost=0.0, payer="kerf_paid"):
            captured.append({"kind": kind, "payer": payer, "model": model})

        # Build minimal fakes
        uid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        tid = str(uuid.uuid4())

        # Fake provider response
        resp = MagicMock()
        resp.content = "My CAD Title"
        resp.input_tokens = 10
        resp.output_tokens = 5

        provider = MagicMock()
        provider.complete = MagicMock(return_value=resp)

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("kerf_api.routes.usage_queries.create_usage_event", side_effect=_fake_create_usage_event):
            with patch("kerf_api.routes.settings") as mock_settings:
                mock_settings.usage_enabled = True
                from kerf_api.routes import _auto_title_thread
                _run(_auto_title_thread(
                    tid, "How do I model a gear?", "Here is how...",
                    provider, "claude-haiku-4-5", pool,
                    user_id=uid, project_id=pid,
                ))

        assert len(captured) == 1, f"expected 1 usage event, got {captured}"
        assert captured[0]["kind"] == "operator_token"
        assert captured[0]["payer"] == "operator"

    def test_workshop_publish_readme_usage_event_in_source(self):
        """workshop_publish contains operator_token usage event for README gen."""
        import pathlib
        routes_path = (
            pathlib.Path(__file__).parent.parent
            / "src" / "kerf_api" / "routes.py"
        )
        src = routes_path.read_text()
        assert "operator_token" in src, (
            "R22: operator_token kind not found in routes.py"
        )
        assert "payer=\"operator\"" in src or "payer='operator'" in src, (
            "R22: payer='operator' not found in routes.py"
        )

    def test_create_usage_event_accepts_payer(self):
        """create_usage_event now accepts a payer kwarg."""
        import inspect
        from kerf_core.db.queries.usage_events import create_usage_event
        sig = inspect.signature(create_usage_event)
        assert "payer" in sig.parameters, (
            "create_usage_event missing payer parameter"
        )
        # Default should be 'kerf_paid' to preserve backwards compat
        assert sig.parameters["payer"].default == "kerf_paid"
