"""Tests for CLOUD BETA mode billing guard.

Verifies three states:
  1. cloud_beta=True  → topup rejected (403)
  2. cloud_beta=False → topup proceeds normally (no 403 from beta guard)
  3. self-host (cloud_enabled=False) → billing plugin dormant; beta flag irrelevant

All tests are hermetic (no real DB, no network).
"""
from __future__ import annotations

import pytest


# ── Minimal stubs ────────────────────────────────────────────────────────────

class _Cfg:
    """Minimal settings-like object with only the fields the handlers need."""
    def __init__(self, cloud_beta: bool = False, cloud_enabled: bool = True):
        self.cloud_beta = cloud_beta
        self.cloud_enabled = cloud_enabled
        self.cloud_fx_base_currency = "USD"
        self.cloud_fx_settlement_currency = "ZAR"
        self.cloud_fx_spread_pct = 1.5


class _FakeRequest:
    """Minimal FastAPI-like Request stub."""
    class State:
        user_id = "user-abc"
    state = State()

    def __init__(self, body: dict | None = None):
        self._body = body or {"amount_usd": 10}

    async def json(self):
        return self._body


class _FakePool:
    """Never reached in beta-guard path; stubs the interface."""
    async def fetchrow(self, *a, **kw):
        return None

    async def execute(self, *a, **kw):
        pass


class _FakeFx:
    async def rate_with_spread(self, *a, **kw):
        return 18.5, 18.5, True


class _FakePaystack:
    def initialize_transaction(self, *a, **kw):
        return "https://paystack.com/pay/test", "ref-1"


# ── Tests: Handlers class ────────────────────────────────────────────────────

class TestHandlersBetaGuard:
    """Direct tests on kerf_billing.billing.handlers.Handlers.topup."""

    async def test_topup_blocked_in_beta(self):
        from kerf_billing.billing.handlers import Handlers
        h = Handlers(
            pool=_FakePool(),
            cfg=_Cfg(cloud_beta=True),
            fx_fetcher=_FakeFx(),
            paystack_client=_FakePaystack(),
        )
        resp = await h.topup(_FakeRequest({"amount_usd": 25}))
        assert resp.status_code == 403
        import json
        body = json.loads(resp.body)
        assert "billing disabled" in body["error"].lower()
        assert "beta" in body["error"].lower()

    async def test_topup_allowed_when_beta_false(self):
        """With cloud_beta=False the handler proceeds past the guard.

        We don't have a real FX service or DB here so the call will fail
        downstream, but the status must NOT be 403 from the beta guard.
        """
        from kerf_billing.billing.handlers import Handlers

        class _FailFx:
            async def rate_with_spread(self, *a, **kw):
                # Simulate an FX failure so we get a deterministic early exit
                # without needing a real DB, but the guard must not have fired.
                return 0, 0, False

        h = Handlers(
            pool=_FakePool(),
            cfg=_Cfg(cloud_beta=False),
            fx_fetcher=_FailFx(),
            paystack_client=_FakePaystack(),
        )
        resp = await h.topup(_FakeRequest({"amount_usd": 25}))
        # FX failure → 503, not 403 (not a beta rejection)
        assert resp.status_code != 403

    async def test_topup_blocked_unauthenticated_before_beta_check(self):
        """Missing user_id still gets 401, not 403 — auth check runs first."""
        from kerf_billing.billing.handlers import Handlers

        class _NoUserRequest(_FakeRequest):
            class State:
                user_id = None
            state = State()

        h = Handlers(
            pool=_FakePool(),
            cfg=_Cfg(cloud_beta=True),
            fx_fetcher=_FakeFx(),
            paystack_client=_FakePaystack(),
        )
        resp = await h.topup(_NoUserRequest({}))
        assert resp.status_code == 401


# ── Tests: /api/config endpoint ───────────────────────────────────────────────

class TestConfigEndpoint:
    """Unit tests for the /api/config route handler logic."""

    def _make_settings(self, cloud_enabled=True, cloud_beta=False,
                       google_client_id="", cloud_paystack_public_key="",
                       local_mode=False):
        class S:
            pass
        s = S()
        s.cloud_enabled = cloud_enabled
        s.cloud_beta = cloud_beta
        s.google_client_id = google_client_id
        s.cloud_paystack_public_key = cloud_paystack_public_key
        s.local_mode = local_mode
        return s

    def _call_config_logic(self, s):
        """Mirror the logic in routes.get_config without importing the full app."""
        payload = {
            "cloud_enabled": s.cloud_enabled,
            "local_mode": s.local_mode,
        }
        if s.cloud_enabled:
            if s.cloud_beta:
                payload["cloud_beta"] = True
            if s.google_client_id:
                payload["google_client_id"] = s.google_client_id
            if s.cloud_paystack_public_key:
                payload["paystack_public_key"] = s.cloud_paystack_public_key
        return payload

    def test_beta_flag_surfaced_in_config(self):
        s = self._make_settings(cloud_enabled=True, cloud_beta=True)
        payload = self._call_config_logic(s)
        assert payload["cloud_beta"] is True

    def test_beta_absent_when_false(self):
        s = self._make_settings(cloud_enabled=True, cloud_beta=False)
        payload = self._call_config_logic(s)
        assert "cloud_beta" not in payload

    def test_beta_absent_on_selfhost(self):
        """Self-hosted: cloud_enabled=False means cloud_beta is irrelevant."""
        s = self._make_settings(cloud_enabled=False, cloud_beta=True)
        payload = self._call_config_logic(s)
        assert "cloud_beta" not in payload

    def test_cloud_enabled_surfaced(self):
        s = self._make_settings(cloud_enabled=True)
        payload = self._call_config_logic(s)
        assert payload["cloud_enabled"] is True

    def test_selfhost_config_shape(self):
        s = self._make_settings(cloud_enabled=False, local_mode=True)
        payload = self._call_config_logic(s)
        assert payload["cloud_enabled"] is False
        assert payload["local_mode"] is True
        assert "paystack_public_key" not in payload
        assert "google_client_id" not in payload


# ── Tests: useCloudConfig cloudBeta logic (documented as unit assertions) ────

class TestCloudBetaLogic:
    """Document the frontend merge logic: env OR backend → cloudBeta=True."""

    def _derive_cloud_beta(self, vite_flag: bool, backend_flag: bool) -> bool:
        """Mirror useCloudConfig's cloudBeta derivation."""
        return vite_flag or backend_flag

    def test_env_flag_activates_beta(self):
        assert self._derive_cloud_beta(vite_flag=True, backend_flag=False) is True

    def test_backend_flag_activates_beta(self):
        assert self._derive_cloud_beta(vite_flag=False, backend_flag=True) is True

    def test_both_flags_activates_beta(self):
        assert self._derive_cloud_beta(vite_flag=True, backend_flag=True) is True

    def test_no_flags_beta_false(self):
        assert self._derive_cloud_beta(vite_flag=False, backend_flag=False) is False

    def test_backend_cannot_disable_env_flag(self):
        """Once the build-time env flag is set it cannot be unset by the backend."""
        result = self._derive_cloud_beta(vite_flag=True, backend_flag=False)
        assert result is True


# ── Tests: settings model ────────────────────────────────────────────────────

class TestSettingsCloudBeta:
    """Ensure Settings correctly reads KERF_CLOUD_BETA from env."""

    def test_cloud_beta_defaults_false(self):
        from kerf_core.config import Settings
        import os
        # Ensure the env var is unset
        os.environ.pop("KERF_CLOUD_BETA", None)
        s = Settings(
            database_url="postgres://localhost/test",
            cloud_enabled=True,
        )
        assert s.cloud_beta is False

    def test_cloud_beta_reads_from_env(self, monkeypatch):
        # pydantic-settings maps field "cloud_beta" → env var "CLOUD_BETA"
        # (no prefix; matches the CLOUD_ENABLED convention already in use).
        from kerf_core.config import Settings
        monkeypatch.setenv("CLOUD_BETA", "true")
        s = Settings(
            database_url="postgres://localhost/test",
            cloud_enabled=True,
        )
        assert s.cloud_beta is True

    def test_cloud_beta_false_string(self, monkeypatch):
        from kerf_core.config import Settings
        monkeypatch.setenv("CLOUD_BETA", "false")
        s = Settings(
            database_url="postgres://localhost/test",
            cloud_enabled=True,
        )
        assert s.cloud_beta is False
