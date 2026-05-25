"""
Dispatch test for topo_advanced LLM tool (coverage sweep wiring).

Verifies:
- topo_advanced ToolSpec is registered in the global registry (via @register).
- run_topo_advanced dispatches correctly for mode="optimize".
- run_topo_advanced dispatches correctly for mode="pareto".
- run_topo_advanced dispatches correctly for mode="lattice".
- Bad mode returns err_payload.
"""

from __future__ import annotations

import json
import asyncio
import pytest


class _FakeCtx:
    project_id = "proj-test"
    pool = None


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# ToolSpec registration
# ---------------------------------------------------------------------------

def test_topo_advanced_spec_registered():
    """topo_advanced ToolSpec must be registered in the global registry."""
    import kerf_topo.advanced  # noqa: F401 — triggers @register

    # Registry lives in kerf_chat.tools.registry when available,
    # otherwise falls back to kerf_topo._compat._registry
    try:
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
    except ImportError:
        from kerf_topo._compat import _registry
        names = {entry["spec"].name for entry in _registry}

    assert "topo_advanced" in names, (
        f"topo_advanced not in registry; found: {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# Dispatch: mode=optimize
# ---------------------------------------------------------------------------

def test_topo_advanced_optimize_dispatch():
    from kerf_topo.advanced import run_topo_advanced
    ctx = _FakeCtx()
    args = json.dumps({
        "mode": "optimize",
        "nelx": 6,
        "nely": 4,
        "volume_fraction": 0.5,
        "max_iterations": 5,
    }).encode()
    raw = _run(run_topo_advanced(ctx, args))
    payload = json.loads(raw)
    assert payload.get("ok") is True, f"optimize failed: {payload}"
    assert "compliance" in payload
    assert "density" in payload


# ---------------------------------------------------------------------------
# Dispatch: mode=pareto
# ---------------------------------------------------------------------------

def test_topo_advanced_pareto_dispatch():
    from kerf_topo.advanced import run_topo_advanced
    ctx = _FakeCtx()
    args = json.dumps({
        "mode": "pareto",
        "nelx": 6,
        "nely": 4,
        "volume_fractions": [0.3, 0.5],
        "max_iterations": 5,
    }).encode()
    raw = _run(run_topo_advanced(ctx, args))
    payload = json.loads(raw)
    assert payload.get("ok") is True, f"pareto failed: {payload}"
    assert "front" in payload
    assert len(payload["front"]) == 2


# ---------------------------------------------------------------------------
# Dispatch: mode=lattice
# ---------------------------------------------------------------------------

def test_topo_advanced_lattice_dispatch():
    from kerf_topo.advanced import run_topo_advanced
    ctx = _FakeCtx()
    args = json.dumps({
        "mode": "lattice",
        "nelx": 6,
        "nely": 4,
        "volume_fraction": 0.5,
        "max_iterations": 5,
        "lattice_period": 2.0,
        "lattice_surface": "gyroid",
    }).encode()
    raw = _run(run_topo_advanced(ctx, args))
    payload = json.loads(raw)
    assert payload.get("ok") is True, f"lattice failed: {payload}"
    assert "cells" in payload
    assert payload["n_cells"] == 6 * 4


# ---------------------------------------------------------------------------
# Bad mode
# ---------------------------------------------------------------------------

def test_topo_advanced_bad_mode():
    from kerf_topo.advanced import run_topo_advanced
    ctx = _FakeCtx()
    args = json.dumps({"mode": "unknown_mode"}).encode()
    raw = _run(run_topo_advanced(ctx, args))
    payload = json.loads(raw)
    # err_payload returns {"error": ..., "code": ...} — no "ok" key
    assert payload.get("code") == "BAD_ARGS", f"expected BAD_ARGS code; got {payload}"
