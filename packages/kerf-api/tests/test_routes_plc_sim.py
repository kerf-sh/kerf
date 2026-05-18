"""T-224 — PLC HMI simulator route tests.

Tests:
1. /plc/sim/step returns stub data when T-223 simulator is unavailable.
2. /plc/sim/step persists last_state across calls within the same session_id.
3. /plc/sim/load_fixture returns the blinker fixture.
4. /plc/sim/load_fixture returns the conveyor fixture.
5. /plc/sim/load_fixture returns 404 for unknown fixture name.
6. /plc/sim/step returns a new session_id when none is provided.
7. /plc/sim/step accepts explicit session_id and reuses state.
8. /plc/sim/step tick_count is honoured (trace length == tick_count).

All tests are offline — no DB, no network.
"""
from __future__ import annotations

import sys
import os
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure kerf_api is importable even when run from a bare directory.
# The conftest.py in this directory already adds all packages/kerf-*/src to
# sys.path, but we guard here too for direct pytest invocations.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_PACKAGES_ROOT = os.path.dirname(_PLUGIN_ROOT)

for _entry in os.listdir(_PACKAGES_ROOT):
    if not _entry.startswith("kerf-"):
        continue
    _src = os.path.join(_PACKAGES_ROOT, _entry, "src")
    if os.path.isdir(_src) and _src not in sys.path:
        sys.path.insert(0, _src)

# ---------------------------------------------------------------------------
# Build a minimal FastAPI test app — no DB, no auth dependencies needed.
# ---------------------------------------------------------------------------

from kerf_api.routes_plc_sim import router, _sessions  # noqa: E402


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture()
def client():
    # Clear session state between tests so they're independent.
    _sessions.clear()
    app = _make_app()
    with TestClient(app) as c:
        yield c
    _sessions.clear()


MINIMAL_PROGRAM = """\
PROGRAM test_prog
  VAR_OUTPUT
    coil_out : BOOL;
  END_VAR
  coil_out := TRUE;
END_PROGRAM
"""

# ---------------------------------------------------------------------------
# 1. /step returns ok + stub data when simulator unavailable
# ---------------------------------------------------------------------------


def test_step_returns_ok_when_simulator_unavailable(client, monkeypatch):
    """When T-223 is not installed, the stub path must return ok=True."""
    # Force _get_simulator_class to return None (simulator unavailable).
    import kerf_api.routes_plc_sim as mod
    monkeypatch.setattr(mod, "_get_simulator_class", lambda: None)

    res = client.post("/api/plc/sim/step", json={
        "program": MINIMAL_PROGRAM,
        "inputs": {},
        "tick_count": 3,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "session_id" in data
    assert isinstance(data["trace"], list)
    assert isinstance(data["outputs"], dict)
    assert isinstance(data["last_state"], dict)
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# 2. last_state persists across calls in the same session
# ---------------------------------------------------------------------------


def test_step_persists_last_state_across_calls(client, monkeypatch):
    """Session state carries the _tick counter forward across requests."""
    import kerf_api.routes_plc_sim as mod
    monkeypatch.setattr(mod, "_get_simulator_class", lambda: None)

    # First call — no session_id provided
    res1 = client.post("/api/plc/sim/step", json={
        "program": MINIMAL_PROGRAM,
        "inputs": {},
        "tick_count": 5,
    })
    assert res1.status_code == 200
    data1 = res1.json()
    session_id = data1["session_id"]
    tick_after_first = data1["last_state"].get("_tick", 0)
    assert tick_after_first == 5

    # Second call — provide the same session_id
    res2 = client.post("/api/plc/sim/step", json={
        "program": MINIMAL_PROGRAM,
        "inputs": {},
        "tick_count": 3,
        "session_id": session_id,
    })
    assert res2.status_code == 200
    data2 = res2.json()
    tick_after_second = data2["last_state"].get("_tick", 0)
    assert tick_after_second == 8, (
        f"Expected _tick=8 after 5+3 ticks, got {tick_after_second}"
    )


# ---------------------------------------------------------------------------
# 3. load_fixture returns the blinker fixture
# ---------------------------------------------------------------------------


def test_load_fixture_blinker(client):
    res = client.post("/api/plc/sim/load_fixture", json={"name": "blinker"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["name"] == "blinker"
    assert "PROGRAM blinker" in data["program"]
    assert isinstance(data["inputs"], list)
    assert isinstance(data["description"], str)


# ---------------------------------------------------------------------------
# 4. load_fixture returns the conveyor fixture
# ---------------------------------------------------------------------------


def test_load_fixture_conveyor(client):
    res = client.post("/api/plc/sim/load_fixture", json={"name": "conveyor"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["name"] == "conveyor"
    assert "sensor_start" in data["program"] or any(
        i["name"] == "sensor_start" for i in data["inputs"]
    )


# ---------------------------------------------------------------------------
# 5. load_fixture returns 404 for unknown fixture
# ---------------------------------------------------------------------------


def test_load_fixture_unknown_returns_404(client):
    res = client.post("/api/plc/sim/load_fixture", json={"name": "no_such_fixture"})
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data
    assert "no_such_fixture" in data["detail"]


# ---------------------------------------------------------------------------
# 6. /step auto-generates session_id when none provided
# ---------------------------------------------------------------------------


def test_step_generates_session_id(client, monkeypatch):
    import kerf_api.routes_plc_sim as mod
    monkeypatch.setattr(mod, "_get_simulator_class", lambda: None)

    res = client.post("/api/plc/sim/step", json={
        "program": MINIMAL_PROGRAM,
        "inputs": {},
        "tick_count": 1,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"]
    assert len(data["session_id"]) > 10  # looks like a UUID


# ---------------------------------------------------------------------------
# 7. /step reuses state for explicit session_id
# ---------------------------------------------------------------------------


def test_step_uses_provided_session_id(client, monkeypatch):
    import kerf_api.routes_plc_sim as mod
    monkeypatch.setattr(mod, "_get_simulator_class", lambda: None)

    sid = "my-test-session-007"
    for _ in range(2):
        client.post("/api/plc/sim/step", json={
            "program": MINIMAL_PROGRAM,
            "inputs": {},
            "tick_count": 1,
            "session_id": sid,
        })

    assert sid in _sessions
    assert _sessions[sid].get("_tick") == 2


# ---------------------------------------------------------------------------
# 8. tick_count is reflected in trace length
# ---------------------------------------------------------------------------


def test_step_trace_length_matches_tick_count(client, monkeypatch):
    import kerf_api.routes_plc_sim as mod
    monkeypatch.setattr(mod, "_get_simulator_class", lambda: None)

    for count in (1, 5, 10):
        _sessions.clear()
        res = client.post("/api/plc/sim/step", json={
            "program": MINIMAL_PROGRAM,
            "inputs": {},
            "tick_count": count,
        })
        assert res.status_code == 200
        data = res.json()
        assert len(data["trace"]) == count, (
            f"Expected {count} trace entries, got {len(data['trace'])}"
        )
