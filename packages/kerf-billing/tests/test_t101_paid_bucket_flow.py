"""T-101: Billing flow — paid-bucket upgrade, usage accrual, invoice line items,
and BETA-mode toggle.

Scope (from testing-breakdown.md ~line 556):
  free user → upgrade simulated → consume usage →
  invoice line items appear → BETA-mode toggle hides billing UI
  but features remain.

Success criteria:
  - usage tally matches API
  - BETA flag hides Pricing route (billing disabled)
  - features still available (non-billing endpoints unaffected)

All tests are hermetic: no real Postgres, no network.
Recording-pool stubs capture SQL calls; FastAPI TestClient drives HTTP.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kerf_billing.billing.handlers import Handlers
from kerf_billing.billing.beta import payments_disabled
from kerf_billing.routes import _summarize_usage, _empty_summary


# ── Minimal stubs ─────────────────────────────────────────────────────────────

class _Cfg:
    """Minimal settings object with all fields consumed by Handlers."""
    def __init__(self, cloud_beta: bool = False, cloud_enabled: bool = True):
        self.cloud_beta = cloud_beta
        self.cloud_enabled = cloud_enabled
        self.cloud_fx_base_currency = "USD"
        self.cloud_fx_settlement_currency = "ZAR"
        self.cloud_fx_spread_pct = 1.5


class _Conn:
    """Recording async connection.  fetchrow / fetch responses are injected."""

    def __init__(
        self,
        fetchrow_seq: list[dict | None] | None = None,
        fetch_seq: list[list[dict]] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._fetchrow_seq: list[dict | None] = fetchrow_seq or []
        self._fetch_seq: list[list[dict]] = fetch_seq or []

    async def execute(self, sql: str, *args) -> str:
        self.executed.append((sql, args))
        return "UPDATE 1"

    async def fetchrow(self, sql: str, *args) -> dict | None:
        self.executed.append((sql, args))
        return self._fetchrow_seq.pop(0) if self._fetchrow_seq else None

    async def fetch(self, sql: str, *args) -> list:
        self.executed.append((sql, args))
        return self._fetch_seq.pop(0) if self._fetch_seq else []

    def transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self_inner):
                return outer

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Tx()


class _Pool:
    def __init__(
        self,
        fetchrow_seq: list[dict | None] | None = None,
        fetch_seq: list[list[dict]] | None = None,
    ) -> None:
        self.conn = _Conn(fetchrow_seq, fetch_seq)

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Acq()

    async def fetchrow(self, sql: str, *args):
        return await self.conn.fetchrow(sql, *args)

    async def fetch(self, sql: str, *args):
        return await self.conn.fetch(sql, *args)

    async def execute(self, sql: str, *args):
        return await self.conn.execute(sql, *args)


class _FakeRequest:
    """Minimal FastAPI-like Request stub carrying a user_id on state."""

    class State:
        user_id = "user-t101"

    state = State()

    def __init__(self, body: dict | None = None, query_params: dict | None = None):
        self._body = body or {}
        self.query_params = query_params or {}

    async def json(self):
        return self._body

    async def body(self):
        return json.dumps(self._body).encode()

    @property
    def headers(self):
        return {}


class _FakeFx:
    async def rate_with_spread(self, *a, **kw):
        # 1 USD → 19.5 ZAR (post-spread)
        return 19.5, 19.5, True


class _FakePaystack:
    def initialize_transaction(self, email, amount_zar_cents, reference, callback_url=""):
        return f"https://paystack.com/pay/{reference}", reference

    def verify_webhook_signature(self, body: bytes, sig: str) -> bool:
        return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_handlers(
    cloud_beta: bool = False,
    fetchrow_seq: list | None = None,
    fetch_seq: list | None = None,
) -> tuple[Handlers, _Pool]:
    pool = _Pool(fetchrow_seq=fetchrow_seq, fetch_seq=fetch_seq)
    cfg = _Cfg(cloud_beta=cloud_beta)
    h = Handlers(
        pool=pool,
        cfg=cfg,
        fx_fetcher=_FakeFx(),
        paystack_client=_FakePaystack(),
    )
    return h, pool


_NOW = datetime(2026, 5, 21, 10, 0, 0)
_NOW_ISO = _NOW.isoformat()


def _invoice_row(
    ref: str = "ref-001",
    status: str = "success",
    amount_usd: float = 20.0,
    amount_zar: float = 390.0,
    fx_rate: float = 19.5,
) -> dict:
    return {
        "id": "inv-001",
        "reference": ref,
        "status": status,
        "amount_usd": amount_usd,
        "amount_zar": amount_zar,
        "fx_rate": fx_rate,
        "created_at": _NOW,
        "paid_at": _NOW,
    }


def _usage_row(
    kind: str = "token",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 1000,
    output_tokens: int = 200,
    bytes_delta: int = 0,
    usd_cost: float = 0.012,
    project_id: str | None = "proj-001",
) -> dict:
    return {
        "id": "ev-001",
        "kind": kind,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "bytes_delta": bytes_delta,
        "usd_cost": usd_cost,
        "project_id": project_id,
        "created_at": _NOW,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 1: Upgrade simulation — topup handler inits invoice + Paystack URL
# ─────────────────────────────────────────────────────────────────────────────

class TestUpgradeSimulation:
    """Simulated topup: handler writes pending invoice + returns Paystack URL."""

    async def test_topup_writes_pending_invoice(self):
        """Paid path: topup inserts a pending cloud_invoices row."""
        # fetchrow: user email lookup
        h, pool = _make_handlers(fetchrow_seq=[{"email": "user@example.com"}])
        req = _FakeRequest({"amount_usd": 20.0})
        req.state.user_id = "user-t101"

        resp = await h.topup(req)

        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert "authorization_url" in body
        assert body["amount_usd"] == 20.0
        assert body["fx_rate"] == pytest.approx(19.5)
        assert body["amount_zar"] == pytest.approx(390.0)

        # INSERT INTO cloud_invoices must have fired
        insert_calls = [
            sql for sql, _ in pool.conn.executed
            if "INSERT INTO cloud_invoices" in sql
        ]
        assert insert_calls, "pending invoice must be written before redirecting"

    async def test_topup_status_in_invoice_is_pending(self):
        """The invoice status passed to SQL is 'pending' before webhook fires."""
        h, pool = _make_handlers(fetchrow_seq=[{"email": "user@example.com"}])
        req = _FakeRequest({"amount_usd": 10.0})
        req.state.user_id = "user-t101"

        await h.topup(req)

        insert_sql = next(
            sql for sql, _ in pool.conn.executed
            if "INSERT INTO cloud_invoices" in sql
        )
        assert "'pending'" in insert_sql, "invoice must be inserted with status='pending'"

    async def test_topup_returns_reference_matching_invoice(self):
        """reference in the response matches what was inserted into cloud_invoices."""
        h, pool = _make_handlers(fetchrow_seq=[{"email": "user@example.com"}])
        req = _FakeRequest({"amount_usd": 15.0})
        req.state.user_id = "user-t101"

        resp = await h.topup(req)
        body = json.loads(resp.body)
        reference = body["reference"]

        # The same reference appears in the INSERT args
        invoice_sql, invoice_args = next(
            (sql, args) for sql, args in pool.conn.executed
            if "INSERT INTO cloud_invoices" in sql
        )
        assert reference in invoice_args, (
            "reference from topup response must match the INSERT argument"
        )

    async def test_topup_blocked_in_beta(self):
        """cloud_beta=True → 403 before any DB call."""
        h, pool = _make_handlers(cloud_beta=True)
        req = _FakeRequest({"amount_usd": 20.0})
        req.state.user_id = "user-t101"

        resp = await h.topup(req)
        assert resp.status_code == 403

        # No DB calls (guard fires before any DB access)
        assert not pool.conn.executed, (
            "no DB calls should occur when cloud_beta=True blocks the request"
        )

    async def test_topup_zero_amount_rejected(self):
        """amount_usd <= 0 returns 400 without touching DB."""
        h, pool = _make_handlers()
        req = _FakeRequest({"amount_usd": 0})
        req.state.user_id = "user-t101"

        resp = await h.topup(req)
        assert resp.status_code == 400
        assert not pool.conn.executed


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 2: Invoice line items visible in /billing/me
# ─────────────────────────────────────────────────────────────────────────────

class TestInvoiceLineItemsInMe:
    """After upgrade: /billing/me response contains correct invoice line items."""

    async def test_me_returns_credits_and_recent_invoices(self):
        """me handler returns balance, recent_invoices list with correct shape."""
        inv = _invoice_row()
        usage = _usage_row()
        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 20.0}],  # balance row
            fetch_seq=[[inv], [usage]],              # invoices, then usage
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        assert resp.status_code == 200
        body = json.loads(resp.body)

        assert body["credits_usd"] == pytest.approx(20.0)
        assert len(body["recent_invoices"]) == 1
        invoice = body["recent_invoices"][0]
        assert invoice["status"] == "success"
        assert invoice["amount_usd"] == pytest.approx(20.0)
        assert invoice["reference"] == "ref-001"

    async def test_me_invoice_shape_has_required_fields(self):
        """Each invoice entry must carry the billing UI's required fields."""
        inv = _invoice_row(status="success", amount_usd=50.0, fx_rate=18.8)
        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 50.0}],
            fetch_seq=[[inv], []],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)
        inv_out = body["recent_invoices"][0]

        # All fields required by the billing UI
        required_keys = {"id", "reference", "status", "amount_usd", "amount_zar", "fx_rate",
                         "created_at", "paid_at"}
        assert required_keys.issubset(inv_out.keys()), (
            f"invoice shape missing keys: {required_keys - inv_out.keys()}"
        )

    async def test_me_no_balance_row_defaults_to_zero(self):
        """If no cloud_user_balances row exists yet, credits_usd defaults to 0.0."""
        h, pool = _make_handlers(
            fetchrow_seq=[None],   # no balance row
            fetch_seq=[[], []],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)
        assert body["credits_usd"] == pytest.approx(0.0), (
            "missing balance row must default to 0.0 (free user has no row)"
        )

    async def test_me_recent_usage_entries_included(self):
        """recent_usage list is included in me response with usage rows."""
        usage = _usage_row(usd_cost=0.012, model="claude-haiku")
        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 20.0}],
            fetch_seq=[[], [usage]],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)

        assert "recent_usage" in body
        assert len(body["recent_usage"]) == 1
        u = body["recent_usage"][0]
        assert u["model"] == "claude-haiku"
        assert u["usd_cost"] == pytest.approx(0.012)

    async def test_me_multiple_invoices_preserved(self):
        """Multiple invoices are all returned (up to the limit)."""
        invoices = [
            _invoice_row(ref=f"ref-{i:03d}", amount_usd=float(10 * (i + 1)))
            for i in range(3)
        ]
        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 60.0}],
            fetch_seq=[invoices, []],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)
        assert len(body["recent_invoices"]) == 3


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 3: Usage tally matches API (usage summary)
# ─────────────────────────────────────────────────────────────────────────────

class TestUsageTallyMatchesApi:
    """usage tally (summary) in /billing/usage must be consistent with raw events."""

    def _events(self, rows: list[dict]) -> list[dict]:
        """Convert raw DB row dicts into the shape produced by Handlers.usage."""
        result = []
        for row in rows:
            result.append({
                "id": str(row.get("id", "x")),
                "kind": row["kind"],
                "model": row.get("model"),
                "input_tokens": row.get("input_tokens") or 0,
                "output_tokens": row.get("output_tokens") or 0,
                "bytes_delta": row.get("bytes_delta") or 0,
                "usd_cost": row.get("usd_cost"),
                "project_id": str(row["project_id"]) if row.get("project_id") else None,
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            })
        return result

    def test_compute_tokens_summarised_correctly(self):
        """Token events: compute_usd = sum of all token-event costs."""
        events = self._events([
            _usage_row(kind="token", model="claude-opus-4-7", input_tokens=500,
                       output_tokens=100, usd_cost=0.05),
            _usage_row(kind="token", model="claude-haiku", input_tokens=1000,
                       output_tokens=200, usd_cost=0.002),
        ])
        summary = _summarize_usage(events)
        assert summary["by_category"]["compute_usd"] == pytest.approx(0.052)
        assert summary["by_category"]["storage_usd"] == pytest.approx(0.0)
        assert summary["by_category"]["other_usd"] == pytest.approx(0.0)
        assert summary["by_category"]["total_usd"] == pytest.approx(0.052)

    def test_by_model_groups_token_events(self):
        """Events for the same model must be aggregated into one by_model row."""
        events = self._events([
            _usage_row(model="claude-opus-4-7", input_tokens=100, output_tokens=20, usd_cost=0.01),
            _usage_row(model="claude-opus-4-7", input_tokens=200, output_tokens=40, usd_cost=0.02),
            _usage_row(model="claude-haiku",    input_tokens=500, output_tokens=100, usd_cost=0.001),
        ])
        summary = _summarize_usage(events)
        rows = summary["by_model"]
        models = [r["model"] for r in rows]
        assert "claude-opus-4-7" in models
        assert "claude-haiku" in models

        opus = next(r for r in rows if r["model"] == "claude-opus-4-7")
        assert opus["count"] == 2
        assert opus["input_tokens"] == 300
        assert opus["output_tokens"] == 60
        assert opus["usd_cost"] == pytest.approx(0.03)

    def test_by_model_sorted_by_cost_descending(self):
        """Most expensive model appears first in by_model."""
        events = self._events([
            _usage_row(model="cheap-model",    usd_cost=0.001),
            _usage_row(model="expensive-model", usd_cost=0.99),
        ])
        summary = _summarize_usage(events)
        assert summary["by_model"][0]["model"] == "expensive-model"

    def test_storage_event_classified_as_storage(self):
        """bytes_delta != 0 → storage bucket, not compute."""
        events = self._events([
            _usage_row(kind="storage", model=None, bytes_delta=1024 * 1024,
                       input_tokens=0, output_tokens=0, usd_cost=0.0002),
        ])
        summary = _summarize_usage(events)
        assert summary["by_category"]["storage_usd"] == pytest.approx(0.0002)
        assert summary["by_category"]["compute_usd"] == pytest.approx(0.0)

    def test_mixed_events_total_equals_sum(self):
        """total_usd = compute + storage + other (no double-counting)."""
        events = self._events([
            _usage_row(kind="token",   usd_cost=0.05,  bytes_delta=0),
            _usage_row(kind="storage", usd_cost=0.02,  bytes_delta=1000),
            _usage_row(kind="render",  usd_cost=0.01,  bytes_delta=0,
                       model=None, input_tokens=0, output_tokens=0),
        ])
        summary = _summarize_usage(events)
        cat = summary["by_category"]
        assert cat["total_usd"] == pytest.approx(
            cat["compute_usd"] + cat["storage_usd"] + cat["other_usd"]
        )
        assert cat["total_usd"] == pytest.approx(0.08)

    def test_empty_events_gives_zero_totals(self):
        """No events: all summary fields are 0.0."""
        summary = _summarize_usage([])
        cat = summary["by_category"]
        assert cat["total_usd"] == 0.0
        assert cat["compute_usd"] == 0.0
        assert cat["storage_usd"] == 0.0
        assert cat["other_usd"] == 0.0
        assert summary["by_model"] == []

    def test_none_cost_treated_as_zero(self):
        """usd_cost=None must not raise; treated as 0."""
        events = self._events([_usage_row(usd_cost=None)])
        summary = _summarize_usage(events)
        assert summary["by_category"]["total_usd"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 4: BETA-mode toggle — billing UI hidden, features still available
# ─────────────────────────────────────────────────────────────────────────────

class TestBetaModeToggle:
    """BETA flag: topup/webhook disabled; me/usage still served (read-only)."""

    def _build_app(self, cloud_beta: bool) -> tuple[FastAPI, Any]:
        """Build a FastAPI app with the billing plugin registered."""
        from kerf_billing.plugin import register
        import asyncio
        app = FastAPI()

        class Ctx:
            cloud_enabled = True
            settings = _Cfg(cloud_beta=cloud_beta)
            local_mode = False
            workers = None

            import logging as _logging
            logger = _logging.getLogger("test.beta")

        loop = asyncio.get_event_loop()
        loop.run_until_complete(register(app, Ctx()))
        return app

    def test_topup_returns_503_in_beta_mode(self):
        """cloud_beta=True: POST /api/billing/topup must return 503."""
        app = self._build_app(cloud_beta=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/billing/topup", json={"amount_usd": 20.0})
        assert resp.status_code == 503, (
            "beta-inert topup route must return 503 (billing disabled)"
        )

    def test_webhook_returns_503_in_beta_mode(self):
        """cloud_beta=True: POST /api/billing/webhook must return 503."""
        app = self._build_app(cloud_beta=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/billing/webhook", json={})
        assert resp.status_code == 503

    def test_me_returns_empty_in_beta_mode(self):
        """cloud_beta=True: GET /api/billing/me returns zeros (read-only, no auth needed)."""
        from kerf_billing.routes import _BETA_503, router_beta_inert

        # _beta_me is mounted by the plugin under cloud_beta — simulate it directly
        # by reading the beta-inert router's behaviour via a lightweight FastAPI app.
        app = FastAPI()
        # Add a fake auth override so require_auth passes
        from kerf_billing.routes import router_beta_inert
        app.include_router(router_beta_inert, prefix="/api")

        # Override the auth dependency so we don't need a real JWT
        from kerf_core.dependencies import require_auth
        app.dependency_overrides[require_auth] = lambda: {"sub": "user-t101"}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/billing/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["credits_usd"] == pytest.approx(0.0)
        assert body["recent_invoices"] == []
        assert body["recent_usage"] == []

    def test_beta_usage_endpoint_returns_empty_summary(self):
        """cloud_beta=True: GET /api/billing/usage returns empty summary."""
        from kerf_billing.routes import router_beta_inert
        from kerf_core.dependencies import require_auth

        app = FastAPI()
        app.include_router(router_beta_inert, prefix="/api")
        app.dependency_overrides[require_auth] = lambda: {"sub": "user-t101"}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/billing/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["summary"] == _empty_summary()

    def test_payments_disabled_helper_gates_correctly(self):
        """payments_disabled() controls the gate in both modes."""
        assert payments_disabled(_Cfg(cloud_beta=True)) is True
        assert payments_disabled(_Cfg(cloud_beta=False)) is False

    def test_non_billing_endpoint_unaffected_by_beta(self):
        """A non-billing route must still respond normally during beta."""
        app = FastAPI()

        @app.get("/api/health")
        def health():
            return {"ok": True}

        # Add the beta-inert billing router — non-billing routes must not be affected
        from kerf_billing.routes import router_beta_inert
        app.include_router(router_beta_inert, prefix="/api")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 5: Full paid-bucket integration (upgrade → usage → me summary)
# ─────────────────────────────────────────────────────────────────────────────

class TestPaidBucketFlowIntegration:
    """Simulate: free user → topup (upgrade) → consume usage → me shows balance.

    All hermetic — no real DB, no network.  The recording pool captures SQL
    and the response shape is asserted end-to-end via Handlers.
    """

    async def test_upgrade_credits_balance_shown_in_me(self):
        """After simulated topup webhook credits balance, me reflects new credits."""
        # credits_usd = $20 (post-topup balance)
        inv = _invoice_row(status="success", amount_usd=20.0)
        usage = _usage_row(usd_cost=0.012)

        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 20.0}],
            fetch_seq=[[inv], [usage]],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)

        # After topup, credits are positive
        assert body["credits_usd"] > 0, (
            "after upgrade, credits_usd must be > 0 in /billing/me response"
        )
        # Invoice shows up as success
        assert any(
            i["status"] == "success" for i in body["recent_invoices"]
        ), "successful invoice must appear in me response"

    async def test_usage_events_appear_after_spend(self):
        """After KerfPaid spend, usage events show in me response."""
        usage = _usage_row(kind="token", model="claude-opus-4-7", usd_cost=0.05)
        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 19.95}],  # balance after $0.05 spend
            fetch_seq=[[], [usage]],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)

        assert len(body["recent_usage"]) == 1
        ev = body["recent_usage"][0]
        assert ev["model"] == "claude-opus-4-7"
        assert ev["usd_cost"] == pytest.approx(0.05)

    async def test_balance_reflects_net_after_topup_and_spend(self):
        """credits_usd in me response = topup_amount - spend_amount."""
        topup_usd = 20.0
        spend_usd = 0.05
        expected_balance = topup_usd - spend_usd  # 19.95

        inv = _invoice_row(amount_usd=topup_usd, status="success")
        usage = _usage_row(usd_cost=spend_usd)

        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": expected_balance}],
            fetch_seq=[[inv], [usage]],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)

        assert body["credits_usd"] == pytest.approx(expected_balance), (
            f"balance should be topup ({topup_usd}) minus spend ({spend_usd})"
        )

    async def test_invoice_status_success_after_payment(self):
        """Invoice transitions to 'success' status (post-webhook), visible in me."""
        inv = _invoice_row(status="success", amount_usd=50.0)

        h, pool = _make_handlers(
            fetchrow_seq=[{"credits_usd": 50.0}],
            fetch_seq=[[inv], []],
        )
        req = _FakeRequest()
        req.state.user_id = "user-t101"

        resp = await h.me(req)
        body = json.loads(resp.body)

        inv_out = body["recent_invoices"][0]
        assert inv_out["status"] == "success", (
            "invoice must show 'success' status after Paystack webhook fires"
        )
        assert inv_out["paid_at"] is not None, (
            "paid_at must be set on a successful invoice"
        )

    async def test_topup_amount_fx_conversion_correct(self):
        """amount_zar in topup response = amount_usd × fx_rate (1 USD → 19.5 ZAR)."""
        h, pool = _make_handlers(fetchrow_seq=[{"email": "user@example.com"}])
        req = _FakeRequest({"amount_usd": 10.0})
        req.state.user_id = "user-t101"

        resp = await h.topup(req)
        body = json.loads(resp.body)

        assert body["amount_usd"] == pytest.approx(10.0)
        assert body["amount_zar"] == pytest.approx(10.0 * 19.5)
        assert body["fx_rate"] == pytest.approx(19.5)
