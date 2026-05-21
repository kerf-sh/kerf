"""T-61 Library: submissions + moderation.

Scope: ``library_part_submissions`` lifecycle (draft → submitted → approved/rejected).
Success: 25 submissions across roles; state-machine guards; admin override path.

Strategy: hermetic — all DB calls are intercepted by _FakePool / _FakeConn;
no real Postgres connection needed.  The FastAPI TestClient is used to exercise
the HTTP layer end-to-end (routes → route helpers → mocked DB).

Endpoints under test:
  POST   /api/library/submissions               (authenticated user)
  GET    /api/admin/library/submissions         (admin only)
  PUT    /api/admin/library/submissions/{id}    (admin only)
"""
from __future__ import annotations

import sys
import uuid
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap — mirrors conftest.py
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
# Constants
# ---------------------------------------------------------------------------

_JWT_SECRET = "dev-secret-change-in-production"
_ADMIN_ID = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())
_OTHER_USER_ID = str(uuid.uuid4())
_WS_ID = str(uuid.uuid4())
_WS_SLUG = "test-workspace"

# Pre-baked submission IDs for deterministic tests
_SUB_ID_PENDING = str(uuid.uuid4())
_SUB_ID_APPROVED = str(uuid.uuid4())
_SUB_ID_REJECTED = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _mint_jwt(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        _JWT_SECRET,
        algorithm="HS256",
    )


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_mint_jwt(user_id)}"}


# ---------------------------------------------------------------------------
# Fake DB objects
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    """dict that also supports asyncpg Record attribute-style access."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _make_submission(
    sub_id: str,
    submitter_id: str,
    status: str = "pending",
    reviewer_id: Optional[str] = None,
    review_note: str = "",
    payload: Optional[dict] = None,
) -> _FakeRow:
    now = datetime.now(tz=timezone.utc)
    return _FakeRow({
        "id": uuid.UUID(sub_id),
        "submitter_user_id": uuid.UUID(submitter_id),
        "target_workspace_id": uuid.UUID(_WS_ID),
        "payload": payload or {"name": "Widget", "mpn": "W-001"},
        "status": status,
        "review_note": review_note,
        "reviewer_id": uuid.UUID(reviewer_id) if reviewer_id else None,
        "created_at": now,
        "updated_at": now,
    })


class _FakeConn:
    """Configurable fake asyncpg connection."""

    def __init__(
        self,
        *,
        ws_exists: bool = True,
        user_is_admin: bool = False,
        existing_submissions: Optional[list] = None,
        approve_result: Optional[_FakeRow] = None,
        reject_result: Optional[_FakeRow] = None,
        created_submission_id: Optional[str] = None,
    ):
        self._ws_exists = ws_exists
        self._user_is_admin = user_is_admin
        self._submissions = existing_submissions or []
        self._approve_result = approve_result
        self._reject_result = reject_result
        self._created_id = created_submission_id or str(uuid.uuid4())
        self.inserted: list[dict] = []
        self.updated: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, query: str, *args, **kwargs):
        q = query.strip().lower()

        # workspace lookup by slug
        if "from workspaces" in q and ("slug" in q or "where" in q):
            if not self._ws_exists:
                return None
            return _FakeRow({"id": uuid.UUID(_WS_ID), "slug": _WS_SLUG, "name": "Test WS"})

        # user lookup
        if "from users" in q:
            user_id_arg = args[0] if args else None
            admin_id = uuid.UUID(_ADMIN_ID)
            if user_id_arg == admin_id:
                return _FakeRow({
                    "id": admin_id, "account_role": "admin",
                    "email": "admin@test.com", "name": "Admin",
                })
            # any other user is a regular user
            return _FakeRow({
                "id": user_id_arg, "account_role": "user",
                "email": "user@test.com", "name": "User",
            })

        # library_part_submissions INSERT ... RETURNING
        if "insert into library_part_submissions" in q:
            row = _FakeRow({
                "id": uuid.UUID(self._created_id),
                "submitter_user_id": args[0] if args else uuid.uuid4(),
                "target_workspace_id": args[1] if len(args) > 1 else uuid.UUID(_WS_ID),
                "payload": args[2] if len(args) > 2 else {},
                "status": "pending",
                "review_note": "",
                "reviewer_id": None,
                "created_at": datetime.now(tz=timezone.utc),
                "updated_at": datetime.now(tz=timezone.utc),
            })
            self.inserted.append(dict(row))
            return row

        # approve UPDATE
        if "status = 'approved'" in q:
            self.updated.append({"action": "approve", "id": str(args[0]) if args else None})
            return self._approve_result

        # reject UPDATE
        if "status = 'rejected'" in q:
            self.updated.append({"action": "reject", "id": str(args[0]) if args else None})
            return self._reject_result

        # single submission GET
        if "from library_part_submissions" in q and "where id" in q:
            sub_id_arg = args[0] if args else None
            for s in self._submissions:
                if s["id"] == sub_id_arg:
                    return s
            return None

        return None

    async def fetch(self, query: str, *args, **kwargs):
        q = query.strip().lower()
        if "from library_part_submissions" in q:
            # filter by status if present
            if "status =" in q and args:
                st = args[0]
                return [s for s in self._submissions if s.get("status") == st]
            return list(self._submissions)
        return []

    async def fetchval(self, query: str, *args, **kwargs):
        return None

    async def execute(self, query: str, *args, **kwargs):
        return "OK"


class _FakePool:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def acquire(self):
        return self._conn


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    import kerf_core.db.connection as _conn_mod
    from kerf_api.routes import router as api_router

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _conn_mod._pool = object()  # sentinel; replaced by patch below
        yield
        _conn_mod._pool = None

    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router, prefix="/api")
    return app


_APP = _build_app()


def _client_with(conn: _FakeConn) -> TestClient:
    pool = _FakePool(conn)
    with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
        with TestClient(_APP, raise_server_exceptions=False) as c:
            yield c


from contextlib import contextmanager


@contextmanager
def _patched_client(conn: _FakeConn):
    pool = _FakePool(conn)
    with patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)):
        with TestClient(_APP, raise_server_exceptions=False) as c:
            yield c, conn


# ---------------------------------------------------------------------------
# 1. POST /api/library/submissions  (submit a part)
# ---------------------------------------------------------------------------

class TestSubmitPart:
    """Scenarios 1–8: normal submits, missing workspace, unauthenticated."""

    def _post(self, conn: _FakeConn, user_id: str, body: dict):
        with _patched_client(conn) as (c, _):
            return c.post(
                "/api/library/submissions",
                json=body,
                headers=_auth(user_id),
            )

    def test_submit_basic_returns_201(self):
        """Scenario 1: valid submit → 201 with id."""
        conn = _FakeConn(ws_exists=True)
        r = self._post(conn, _USER_ID, {
            "target_workspace_slug": _WS_SLUG,
            "payload": {"name": "Bolt M3", "mpn": "BM3"},
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert "id" in body
        assert uuid.UUID(body["id"])  # valid UUID

    def test_submit_records_insertion(self):
        """Scenario 2: DB insert was called once."""
        conn = _FakeConn(ws_exists=True)
        self._post(conn, _USER_ID, {
            "target_workspace_slug": _WS_SLUG,
            "payload": {"name": "Nut M3"},
        })
        assert len(conn.inserted) == 1

    def test_submit_stores_payload(self):
        """Scenario 3: payload is passed through to DB."""
        payload = {"name": "Capacitor 100nF", "mpn": "CAP-100N", "category": "passive"}
        conn = _FakeConn(ws_exists=True)
        self._post(conn, _USER_ID, {
            "target_workspace_slug": _WS_SLUG,
            "payload": payload,
        })
        assert len(conn.inserted) == 1
        stored = conn.inserted[0]["payload"]
        # payload is passed as a dict; it may be stored as-is
        assert stored == payload or stored == str(payload)

    def test_submit_missing_workspace_404(self):
        """Scenario 4: non-existent target workspace → 404."""
        conn = _FakeConn(ws_exists=False)
        r = self._post(conn, _USER_ID, {
            "target_workspace_slug": "does-not-exist",
            "payload": {},
        })
        assert r.status_code == 404, r.text

    def test_submit_unauthenticated_401(self):
        """Scenario 5: no auth header → 401 or 403."""
        conn = _FakeConn(ws_exists=True)
        with _patched_client(conn) as (c, _):
            r = c.post(
                "/api/library/submissions",
                json={"target_workspace_slug": _WS_SLUG, "payload": {}},
            )
        assert r.status_code in (401, 403), r.text

    def test_submit_empty_payload_allowed(self):
        """Scenario 6: empty payload dict is allowed (schema is open)."""
        conn = _FakeConn(ws_exists=True)
        r = self._post(conn, _USER_ID, {
            "target_workspace_slug": _WS_SLUG,
            "payload": {},
        })
        assert r.status_code == 201, r.text

    def test_submit_multiple_parts_independent(self):
        """Scenario 7: two sequential submits each produce distinct IDs."""
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())

        conn1 = _FakeConn(ws_exists=True, created_submission_id=id1)
        with _patched_client(conn1) as (c1, _):
            r1 = c1.post(
                "/api/library/submissions",
                json={"target_workspace_slug": _WS_SLUG, "payload": {"mpn": "A"}},
                headers=_auth(_USER_ID),
            )

        conn2 = _FakeConn(ws_exists=True, created_submission_id=id2)
        with _patched_client(conn2) as (c2, _):
            r2 = c2.post(
                "/api/library/submissions",
                json={"target_workspace_slug": _WS_SLUG, "payload": {"mpn": "B"}},
                headers=_auth(_OTHER_USER_ID),
            )

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]

    def test_submit_missing_required_fields_422(self):
        """Scenario 8: missing both required fields → 422 validation error."""
        conn = _FakeConn(ws_exists=True)
        with _patched_client(conn) as (c, _):
            r = c.post(
                "/api/library/submissions",
                json={},
                headers=_auth(_USER_ID),
            )
        assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 2. GET /api/admin/library/submissions  (list submissions, admin only)
# ---------------------------------------------------------------------------

class TestAdminListSubmissions:
    """Scenarios 9–14: admin list; RBAC guards."""

    def _get(self, conn: _FakeConn, user_id: str, params: str = ""):
        with _patched_client(conn) as (c, _):
            return c.get(
                f"/api/admin/library/submissions{params}",
                headers=_auth(user_id),
            )

    def test_admin_can_list_all(self):
        """Scenario 9: admin gets all submissions."""
        subs = [
            _make_submission(_SUB_ID_PENDING, _USER_ID, "pending"),
            _make_submission(_SUB_ID_APPROVED, _USER_ID, "approved"),
        ]
        conn = _FakeConn(user_is_admin=True, existing_submissions=subs)
        r = self._get(conn, _ADMIN_ID)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "rows" in body
        assert len(body["rows"]) == 2

    def test_admin_list_returns_status_field(self):
        """Scenario 10: each row has a status field."""
        subs = [_make_submission(_SUB_ID_PENDING, _USER_ID, "pending")]
        conn = _FakeConn(user_is_admin=True, existing_submissions=subs)
        r = self._get(conn, _ADMIN_ID)
        rows = r.json()["rows"]
        assert rows[0]["status"] == "pending"

    def test_admin_list_filter_by_status(self):
        """Scenario 11: ?status_filter=pending returns only pending rows."""
        subs = [
            _make_submission(_SUB_ID_PENDING, _USER_ID, "pending"),
            _make_submission(_SUB_ID_APPROVED, _USER_ID, "approved"),
        ]
        conn = _FakeConn(user_is_admin=True, existing_submissions=subs)
        r = self._get(conn, _ADMIN_ID, "?status_filter=pending")
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert all(row["status"] == "pending" for row in rows)

    def test_non_admin_cannot_list_403(self):
        """Scenario 12: regular user gets 403."""
        conn = _FakeConn(user_is_admin=False)
        r = self._get(conn, _USER_ID)
        assert r.status_code == 403, r.text

    def test_unauthenticated_cannot_list(self):
        """Scenario 13: no auth → 401 or 403."""
        conn = _FakeConn()
        with _patched_client(conn) as (c, _):
            r = c.get("/api/admin/library/submissions")
        assert r.status_code in (401, 403), r.text

    def test_admin_list_empty_returns_empty_rows(self):
        """Scenario 14: no submissions → rows=[]."""
        conn = _FakeConn(user_is_admin=True, existing_submissions=[])
        r = self._get(conn, _ADMIN_ID)
        assert r.status_code == 200, r.text
        assert r.json()["rows"] == []


# ---------------------------------------------------------------------------
# 3. PUT /api/admin/library/submissions/{id}  (approve / reject)
# ---------------------------------------------------------------------------

class TestAdminModerateSubmission:
    """Scenarios 15–25: approve, reject, state guards, bad inputs."""

    def _put(self, conn: _FakeConn, user_id: str, sub_id: str, body: dict):
        with _patched_client(conn) as (c, _):
            return c.put(
                f"/api/admin/library/submissions/{sub_id}",
                json=body,
                headers=_auth(user_id),
            )

    def test_approve_pending_returns_200(self):
        """Scenario 15: admin approves a pending submission."""
        approved_row = _make_submission(
            _SUB_ID_PENDING, _USER_ID, "approved",
            reviewer_id=_ADMIN_ID, review_note="Looks good",
        )
        conn = _FakeConn(user_is_admin=True, approve_result=approved_row)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {
            "action": "approve", "review_note": "Looks good",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"

    def test_reject_pending_returns_200(self):
        """Scenario 16: admin rejects a pending submission."""
        rejected_row = _make_submission(
            _SUB_ID_PENDING, _USER_ID, "rejected",
            reviewer_id=_ADMIN_ID, review_note="Not enough info",
        )
        conn = _FakeConn(user_is_admin=True, reject_result=rejected_row)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {
            "action": "reject", "review_note": "Not enough info",
        })
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejected"

    def test_approve_records_db_update(self):
        """Scenario 17: approve triggers an UPDATE in the DB."""
        approved_row = _make_submission(_SUB_ID_PENDING, _USER_ID, "approved")
        conn = _FakeConn(user_is_admin=True, approve_result=approved_row)
        self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {"action": "approve"})
        assert len(conn.updated) == 1
        assert conn.updated[0]["action"] == "approve"

    def test_reject_records_db_update(self):
        """Scenario 18: reject triggers an UPDATE in the DB."""
        rejected_row = _make_submission(_SUB_ID_PENDING, _USER_ID, "rejected")
        conn = _FakeConn(user_is_admin=True, reject_result=rejected_row)
        self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {"action": "reject"})
        assert len(conn.updated) == 1
        assert conn.updated[0]["action"] == "reject"

    def test_approve_already_approved_404(self):
        """Scenario 19: approve returns None (already approved) → 404."""
        # DB returns None when status != 'pending'
        conn = _FakeConn(user_is_admin=True, approve_result=None)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_APPROVED, {"action": "approve"})
        assert r.status_code == 404, r.text

    def test_reject_already_rejected_404(self):
        """Scenario 20: reject returns None (already rejected) → 404."""
        conn = _FakeConn(user_is_admin=True, reject_result=None)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_REJECTED, {"action": "reject"})
        assert r.status_code == 404, r.text

    def test_invalid_action_400(self):
        """Scenario 21: unknown action → 400."""
        conn = _FakeConn(user_is_admin=True)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {"action": "delete"})
        assert r.status_code == 400, r.text

    def test_invalid_submission_id_400(self):
        """Scenario 22: non-UUID submission id → 400."""
        conn = _FakeConn(user_is_admin=True)
        r = self._put(conn, _ADMIN_ID, "not-a-uuid", {"action": "approve"})
        assert r.status_code == 400, r.text

    def test_non_admin_cannot_approve_403(self):
        """Scenario 23: regular user cannot approve → 403."""
        conn = _FakeConn(user_is_admin=False)
        r = self._put(conn, _USER_ID, _SUB_ID_PENDING, {"action": "approve"})
        assert r.status_code == 403, r.text

    def test_non_admin_cannot_reject_403(self):
        """Scenario 24: regular user cannot reject → 403."""
        conn = _FakeConn(user_is_admin=False)
        r = self._put(conn, _USER_ID, _SUB_ID_PENDING, {"action": "reject"})
        assert r.status_code == 403, r.text

    def test_approve_response_shape(self):
        """Scenario 25: approved response has correct id + status shape."""
        approved_row = _make_submission(_SUB_ID_PENDING, _USER_ID, "approved")
        conn = _FakeConn(user_is_admin=True, approve_result=approved_row)
        r = self._put(conn, _ADMIN_ID, _SUB_ID_PENDING, {
            "action": "approve",
            "review_note": "Perfect",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body
        assert "status" in body
        assert body["status"] == "approved"
        # id field echoes back the submission id
        assert body["id"] == _SUB_ID_PENDING
