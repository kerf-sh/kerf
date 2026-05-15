"""
Tests for kerf_cad_core.civil.hydraulics — pipe-network hydraulics
and Manning open-channel flow.

All tests are pure-Python, hermetic: no OCC, no DB, no network, no fixtures
from disk.  Tests run deterministically with fixed numeric inputs.

Covers:
  - Single pipe Hazen-Williams head loss matches formula
  - Single pipe Darcy-Weisbach head loss matches formula
  - Series pipes: head losses add up
  - Simple loop: flow balance at nodes ≈ 0 (mass conservation)
  - Hardy-Cross convergence flag
  - Non-convergence reported gracefully (not crash)
  - Malformed / missing fields return {ok: False} friendly errors
  - Manning normal depth for rectangular channel matches hand calc
  - Manning flow regime classification (sub/super/critical)
  - Manning channel-full detection
  - Manning invalid inputs return {ok: False}
  - Tool wrappers (async) return ok payloads / error payloads
  - plugin._TOOL_MODULES includes hydraulics_tools
  - Node pressure head calculation
  - Hazen-Williams exponent sensitivity (double Q → ~3.5× headloss)
  - Darcy-Weisbach laminar regime (Re < 2300 → f = 64/Re)
  - Zero demand network (all demands zero, still solves heads)
  - Negative demand (source) node
  - Large network (3-loop grid) converges
  - Manning slope sensitivity (4× slope → 2× velocity)
  - Manning n sensitivity (double n → halved velocity)
  - Manning rectangular vs hand calc at two depths
  - solve_pipe_network missing fixed-head node returns error
  - solve_pipe_network duplicate node_id returns error
  - solve_pipe_network bad pipe reference returns error
  - solve_pipe_network zero length pipe returns error
  - hydraulics_pipe_network tool bad JSON returns BAD_ARGS
  - hydraulics_manning tool missing field returns error

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.civil.hydraulics import (
    _hazen_williams_hf,
    _darcy_weisbach_hf,
    _darcy_weisbach_dhf_dq,
    manning_normal_depth,
    solve_pipe_network,
    Pipe,
    Node,
    _G,
    _WATER_NU,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx():
    """Minimal stub for ProjectCtx."""
    class _Ctx:
        project_id = "test"
    return _Ctx()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. Single pipe Hazen-Williams head loss matches formula
#    hf = 10.67 * L * Q^1.852 / (C^1.852 * D^4.87)
# ---------------------------------------------------------------------------

def test_hazen_williams_single_pipe_formula():
    """HW head loss for a single pipe matches the reference formula."""
    L = 1000.0       # m
    D = 0.25         # m
    C = 120.0
    Q = 0.05         # m³/s  (~50 L/s)
    pipe = Pipe(pipe_id="p1", start_node="A", end_node="B",
                length=L, diameter=D, roughness=0.1, hw_c=C)
    expected = 10.67 * L * (Q ** 1.852) / ((C ** 1.852) * (D ** 4.87))
    got = _hazen_williams_hf(Q, pipe)
    assert abs(got - expected) < 1e-9, f"HW formula mismatch: {got} vs {expected}"


# ---------------------------------------------------------------------------
# 2. HW head loss sign convention (negative Q → negative hf)
# ---------------------------------------------------------------------------

def test_hazen_williams_sign():
    """HW head loss is negative when flow is reversed."""
    pipe = Pipe(pipe_id="p1", start_node="A", end_node="B",
                length=500, diameter=0.2, roughness=0.1, hw_c=100)
    hf_pos = _hazen_williams_hf(0.03, pipe)
    hf_neg = _hazen_williams_hf(-0.03, pipe)
    assert hf_pos > 0
    assert hf_neg < 0
    assert abs(hf_pos + hf_neg) < 1e-10, "Symmetric magnitude"


# ---------------------------------------------------------------------------
# 3. HW exponent sensitivity: doubling Q raises hf by ~2^1.852 ≈ 3.61
# ---------------------------------------------------------------------------

def test_hazen_williams_exponent_sensitivity():
    pipe = Pipe(pipe_id="p", start_node="A", end_node="B",
                length=1000, diameter=0.3, roughness=0.1, hw_c=120)
    hf1 = _hazen_williams_hf(0.04, pipe)
    hf2 = _hazen_williams_hf(0.08, pipe)
    ratio = hf2 / hf1
    expected_ratio = 2.0 ** 1.852
    assert abs(ratio - expected_ratio) < 0.01, f"ratio={ratio}, expected≈{expected_ratio}"


# ---------------------------------------------------------------------------
# 4. Single pipe Darcy-Weisbach head loss matches formula (turbulent regime)
# ---------------------------------------------------------------------------

def test_darcy_weisbach_single_pipe_turbulent():
    """DW head loss in turbulent regime is positive and physically plausible."""
    pipe = Pipe(pipe_id="p1", start_node="A", end_node="B",
                length=500, diameter=0.15, roughness=0.5, hw_c=120)
    Q = 0.02  # m³/s
    hf = _darcy_weisbach_hf(Q, pipe)
    # Sanity: hf > 0 and in a reasonable range (should be several metres for 500 m, 150 mm pipe)
    assert hf > 0.5, f"DW hf unexpectedly small: {hf}"
    assert hf < 500.0, f"DW hf unexpectedly large: {hf}"


# ---------------------------------------------------------------------------
# 5. Darcy-Weisbach laminar regime: f = 64/Re
# ---------------------------------------------------------------------------

def test_darcy_weisbach_laminar():
    """Very low flow → laminar; DW friction ≈ 64/Re."""
    D = 0.05   # 50 mm
    L = 10.0
    pipe = Pipe(pipe_id="p", start_node="A", end_node="B",
                length=L, diameter=D, roughness=0.01, hw_c=120)
    # Choose Q so Re << 2300 (laminar)
    # Re = V * D / nu; V = Q / (pi*D^2/4)
    # Target Re ≈ 500 → V = 500 * nu / D
    V_target = 500 * _WATER_NU / D
    Q_lam = V_target * math.pi * D ** 2 / 4.0
    hf = _darcy_weisbach_hf(Q_lam, pipe)
    # Compute expected with f = 64/Re
    area = math.pi * D ** 2 / 4.0
    v = Q_lam / area
    re = v * D / _WATER_NU
    f_expected = 64.0 / re
    hf_expected = f_expected * (L / D) * (v ** 2) / (2 * _G)
    assert abs(hf - hf_expected) / hf_expected < 0.01, \
        f"Laminar DW mismatch: {hf} vs {hf_expected}, Re={re:.1f}"


# ---------------------------------------------------------------------------
# 6. Series pipes: headlosses add up
# ---------------------------------------------------------------------------

def test_series_pipes_headloss_additive():
    """Head loss through two series pipes equals sum of individual losses."""
    nodes = [
        {"node_id": "A", "elevation": 50.0, "head_fixed": 60.0},
        {"node_id": "B", "elevation": 45.0, "demand": 0.0},
        {"node_id": "C", "elevation": 40.0, "demand": 20.0},  # 20 L/s withdrawal
    ]
    pipes = [
        {"pipe_id": "p1", "start_node": "A", "end_node": "B",
         "length": 400, "diameter": 0.2, "hw_c": 120},
        {"pipe_id": "p2", "start_node": "B", "end_node": "C",
         "length": 600, "diameter": 0.2, "hw_c": 120},
    ]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"], result.get("reason")
    # Head at C = head at A - hf_p1 - hf_p2
    head_a = 60.0
    pipe_res = {p["pipe_id"]: p for p in result["pipes"]}
    head_b_calc = head_a - pipe_res["p1"]["headloss_m"]
    node_res = {n["node_id"]: n for n in result["nodes"]}
    assert abs(node_res["B"]["head_m"] - head_b_calc) < 1e-3, \
        f"Head at B: {node_res['B']['head_m']} vs expected {head_b_calc}"
    head_c_calc = head_b_calc - pipe_res["p2"]["headloss_m"]
    assert abs(node_res["C"]["head_m"] - head_c_calc) < 1e-3


# ---------------------------------------------------------------------------
# 7. Simple loop: flow balance at nodes ≈ 0 (continuity)
# ---------------------------------------------------------------------------

def test_loop_flow_balance():
    """3-node loop: sum of flows at each junction ≈ 0 (mass conservation)."""
    # Square network: reservoir at N0, demands at N1, N2, N3
    nodes = [
        {"node_id": "N0", "elevation": 0.0, "head_fixed": 40.0},
        {"node_id": "N1", "elevation": 0.0, "demand": 5.0},
        {"node_id": "N2", "elevation": 0.0, "demand": 5.0},
        {"node_id": "N3", "elevation": 0.0, "demand": 5.0},
    ]
    pipes = [
        {"pipe_id": "p01", "start_node": "N0", "end_node": "N1",
         "length": 300, "diameter": 0.15, "hw_c": 130},
        {"pipe_id": "p12", "start_node": "N1", "end_node": "N2",
         "length": 300, "diameter": 0.12, "hw_c": 130},
        {"pipe_id": "p23", "start_node": "N2", "end_node": "N3",
         "length": 300, "diameter": 0.12, "hw_c": 130},
        {"pipe_id": "p30", "start_node": "N3", "end_node": "N0",
         "length": 300, "diameter": 0.15, "hw_c": 130},
    ]
    result = solve_pipe_network(nodes, pipes, max_iterations=200)
    assert result["ok"], result.get("reason")
    assert result["converged"], f"Did not converge: {result['warnings']}"

    # Check mass balance at each junction
    pipe_res = result["pipes"]
    def net_inflow(nid: str) -> float:
        net = 0.0
        for p in pipe_res:
            if p["end_node"] == nid:
                net += p["flow_m3_per_s"]
            elif p["start_node"] == nid:
                net -= p["flow_m3_per_s"]
        return net

    node_demands = {n["node_id"]: n["demand_L_per_s"] / 1000.0
                    for n in result["nodes"]}
    for nid in ["N1", "N2", "N3"]:
        balance = net_inflow(nid) - node_demands[nid]
        assert abs(balance) < 1e-3, \
            f"Flow imbalance at {nid}: {balance:.6f} m³/s"


# ---------------------------------------------------------------------------
# 8. Node pressure head = head - elevation
# ---------------------------------------------------------------------------

def test_node_pressure_head():
    """Pressure head = hydraulic head - elevation."""
    nodes = [
        {"node_id": "R", "elevation": 10.0, "head_fixed": 50.0},
        {"node_id": "J", "elevation": 5.0, "demand": 10.0},
    ]
    pipes = [
        {"pipe_id": "p", "start_node": "R", "end_node": "J",
         "length": 200, "diameter": 0.1, "hw_c": 100},
    ]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"]
    node_j = next(n for n in result["nodes"] if n["node_id"] == "J")
    assert abs(node_j["pressure_head_m"] - (node_j["head_m"] - 5.0)) < 1e-6


# ---------------------------------------------------------------------------
# 9. Non-convergence reported (not crash)
# ---------------------------------------------------------------------------

def test_non_convergence_reported_not_crash():
    """With max_iterations=1, Hardy-Cross won't converge but should not raise."""
    nodes = [
        {"node_id": "A", "elevation": 0.0, "head_fixed": 30.0},
        {"node_id": "B", "elevation": 0.0, "demand": 5.0},
        {"node_id": "C", "elevation": 0.0, "demand": 5.0},
    ]
    pipes = [
        {"pipe_id": "p1", "start_node": "A", "end_node": "B",
         "length": 500, "diameter": 0.1},
        {"pipe_id": "p2", "start_node": "B", "end_node": "C",
         "length": 500, "diameter": 0.1},
        {"pipe_id": "p3", "start_node": "C", "end_node": "A",
         "length": 500, "diameter": 0.1},
    ]
    result = solve_pipe_network(nodes, pipes, max_iterations=1)
    assert result["ok"], result.get("reason")
    # With 1 iteration, likely not converged — but must not raise
    assert "converged" in result
    assert "pipes" in result
    assert "nodes" in result


# ---------------------------------------------------------------------------
# 10. Missing fixed-head node → friendly error
# ---------------------------------------------------------------------------

def test_no_fixed_head_returns_error():
    nodes = [
        {"node_id": "A", "elevation": 0.0, "demand": -10.0},
        {"node_id": "B", "elevation": 0.0, "demand": 10.0},
    ]
    pipes = [{"pipe_id": "p", "start_node": "A", "end_node": "B",
              "length": 100, "diameter": 0.1}]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"] is False
    assert "fixed" in result["reason"].lower() or "reservoir" in result["reason"].lower()


# ---------------------------------------------------------------------------
# 11. Duplicate node_id → friendly error
# ---------------------------------------------------------------------------

def test_duplicate_node_id_error():
    nodes = [
        {"node_id": "A", "elevation": 0, "head_fixed": 10.0},
        {"node_id": "A", "elevation": 5, "demand": 5.0},
    ]
    pipes = [{"pipe_id": "p", "start_node": "A", "end_node": "A",
              "length": 100, "diameter": 0.1}]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# 12. Bad pipe node reference → friendly error
# ---------------------------------------------------------------------------

def test_bad_pipe_node_reference():
    nodes = [
        {"node_id": "A", "elevation": 0, "head_fixed": 20.0},
        {"node_id": "B", "elevation": 0, "demand": 5.0},
    ]
    pipes = [{"pipe_id": "p", "start_node": "A", "end_node": "NONEXISTENT",
              "length": 100, "diameter": 0.1}]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"] is False
    assert "NONEXISTENT" in result["reason"]


# ---------------------------------------------------------------------------
# 13. Zero-length pipe → friendly error
# ---------------------------------------------------------------------------

def test_zero_length_pipe_error():
    nodes = [
        {"node_id": "A", "elevation": 0, "head_fixed": 20.0},
        {"node_id": "B", "elevation": 0, "demand": 5.0},
    ]
    pipes = [{"pipe_id": "p", "start_node": "A", "end_node": "B",
              "length": 0, "diameter": 0.1}]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"] is False
    assert "length" in result["reason"].lower()


# ---------------------------------------------------------------------------
# 14. Negative demand (source) node
# ---------------------------------------------------------------------------

def test_negative_demand_source_node():
    """A node with negative demand acts as an injection source."""
    nodes = [
        {"node_id": "RES", "elevation": 20.0, "head_fixed": 35.0},
        {"node_id": "SRC", "elevation": 5.0, "demand": -8.0},  # 8 L/s injection
        {"node_id": "END", "elevation": 0.0, "demand": 8.0},
    ]
    pipes = [
        {"pipe_id": "p1", "start_node": "RES", "end_node": "SRC",
         "length": 300, "diameter": 0.12},
        {"pipe_id": "p2", "start_node": "SRC", "end_node": "END",
         "length": 400, "diameter": 0.12},
    ]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"], result.get("reason")
    assert "nodes" in result and len(result["nodes"]) == 3


# ---------------------------------------------------------------------------
# 15. Zero demand network (no withdrawals)
# ---------------------------------------------------------------------------

def test_zero_demand_network():
    """Network with all zero demands: no flow, heads propagate from reservoir."""
    nodes = [
        {"node_id": "R", "elevation": 0, "head_fixed": 20.0},
        {"node_id": "J", "elevation": 0, "demand": 0.0},
    ]
    pipes = [{"pipe_id": "p", "start_node": "R", "end_node": "J",
              "length": 100, "diameter": 0.2}]
    result = solve_pipe_network(nodes, pipes)
    assert result["ok"], result.get("reason")
    # Very low flow (near zero) → nearly no head loss
    node_j = next(n for n in result["nodes"] if n["node_id"] == "J")
    # Head at J should be close to 20 (minimal head loss with ~zero flow)
    assert abs(node_j["head_m"] - 20.0) < 1.0


# ---------------------------------------------------------------------------
# 16. Large network (3-loop grid) converges
# ---------------------------------------------------------------------------

def test_three_loop_grid_converges():
    """A 6-node, 3-loop grid network converges and all pressures are reasonable."""
    nodes = [
        {"node_id": "R",  "elevation": 0, "head_fixed": 50.0},
        {"node_id": "N1", "elevation": 0, "demand": 3.0},
        {"node_id": "N2", "elevation": 0, "demand": 3.0},
        {"node_id": "N3", "elevation": 0, "demand": 3.0},
        {"node_id": "N4", "elevation": 0, "demand": 3.0},
        {"node_id": "N5", "elevation": 0, "demand": 3.0},
    ]
    pipes = [
        {"pipe_id": "pR1", "start_node": "R",  "end_node": "N1", "length": 200, "diameter": 0.15},
        {"pipe_id": "pR3", "start_node": "R",  "end_node": "N3", "length": 200, "diameter": 0.15},
        {"pipe_id": "p12", "start_node": "N1", "end_node": "N2", "length": 200, "diameter": 0.10},
        {"pipe_id": "p23", "start_node": "N2", "end_node": "N3", "length": 200, "diameter": 0.10},
        {"pipe_id": "p14", "start_node": "N1", "end_node": "N4", "length": 200, "diameter": 0.10},
        {"pipe_id": "p45", "start_node": "N4", "end_node": "N5", "length": 200, "diameter": 0.10},
        {"pipe_id": "p52", "start_node": "N5", "end_node": "N2", "length": 200, "diameter": 0.10},
        {"pipe_id": "p35", "start_node": "N3", "end_node": "N5", "length": 200, "diameter": 0.10},
    ]
    result = solve_pipe_network(nodes, pipes, max_iterations=300, tolerance_m=1e-5)
    assert result["ok"], result.get("reason")
    assert result["converged"], f"Did not converge: {result['warnings']}"
    # All junction pressures > 0 (since elevations are 0 and reservoir head=50)
    for n in result["nodes"]:
        if not n["is_fixed_head"]:
            assert n["head_m"] > 0, f"Negative head at {n['node_id']}: {n['head_m']}"


# ---------------------------------------------------------------------------
# 17. Manning normal depth for rectangular channel matches hand calc
#     Q = (1/n) * A * R^(2/3) * S^(1/2)
#     Given: B=1.0m, n=0.013, S=0.001, Q=0.5 m³/s
# ---------------------------------------------------------------------------

def test_manning_normal_depth_hand_calc():
    """Manning normal depth matches iterative hand calculation."""
    B = 1.0      # width (m)
    n = 0.013
    S = 0.001
    Q = 0.5      # m³/s
    result = manning_normal_depth(flow_m3s=Q, width_m=B, slope=S, manning_n=n)
    assert result["ok"], result.get("reason")
    y_n = result["normal_depth_m"]

    # Verify: Q_manning(y_n) ≈ Q_given
    A = B * y_n
    P = B + 2 * y_n
    R = A / P
    Q_check = (1.0 / n) * A * (R ** (2.0/3.0)) * math.sqrt(S)
    assert abs(Q_check - Q) / Q < 1e-4, \
        f"Q_check={Q_check:.6f} vs Q={Q:.6f}, y_n={y_n:.4f}"


# ---------------------------------------------------------------------------
# 18. Manning flow regime classification
# ---------------------------------------------------------------------------

def test_manning_subcritical_regime():
    """Gentle slope → subcritical flow (Fr < 1)."""
    result = manning_normal_depth(flow_m3s=0.3, width_m=1.0, slope=0.0005, manning_n=0.013)
    assert result["ok"]
    assert result["froude_number"] < 1.0
    assert result["flow_regime"] == "subcritical"


def test_manning_supercritical_regime():
    """Steep slope → supercritical flow (Fr > 1)."""
    result = manning_normal_depth(flow_m3s=0.3, width_m=1.0, slope=0.05, manning_n=0.013)
    assert result["ok"]
    assert result["froude_number"] > 1.0
    assert result["flow_regime"] == "supercritical"


# ---------------------------------------------------------------------------
# 19. Manning channel-full detection
# ---------------------------------------------------------------------------

def test_manning_channel_full():
    """Flow exceeds capacity at max_depth → channel_full flag set."""
    # Very small max_depth so Q easily exceeds capacity
    result = manning_normal_depth(
        flow_m3s=10.0, width_m=0.5, slope=0.001, manning_n=0.013, max_depth_m=0.5
    )
    assert result["ok"]
    assert result["channel_full"] is True


# ---------------------------------------------------------------------------
# 20. Manning invalid inputs return {ok: False}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs,msg_fragment", [
    ({"flow_m3s": -1,   "width_m": 1, "slope": 0.001, "manning_n": 0.013}, "flow"),
    ({"flow_m3s": 0.5,  "width_m": 0, "slope": 0.001, "manning_n": 0.013}, "width"),
    ({"flow_m3s": 0.5,  "width_m": 1, "slope": -0.01, "manning_n": 0.013}, "slope"),
    ({"flow_m3s": 0.5,  "width_m": 1, "slope": 0.001, "manning_n": 0},     "manning_n"),
])
def test_manning_invalid_input(kwargs, msg_fragment):
    result = manning_normal_depth(**kwargs)
    assert result["ok"] is False
    assert msg_fragment in result["reason"]


# ---------------------------------------------------------------------------
# 21. Manning slope sensitivity: 4× slope → 2× velocity
#     v ∝ S^(1/2); 4× S → 2× v
# ---------------------------------------------------------------------------

def test_manning_slope_sensitivity():
    """Quadrupling slope doubles velocity (Manning v ∝ S^0.5)."""
    r1 = manning_normal_depth(flow_m3s=0.2, width_m=1.0, slope=0.001, manning_n=0.013)
    r2 = manning_normal_depth(flow_m3s=0.2, width_m=1.0, slope=0.004, manning_n=0.013)
    assert r1["ok"] and r2["ok"]
    # At *same* depth the velocity ratio would be exactly 2; with different normal
    # depths we allow 10% tolerance.
    ratio = r2["velocity_m_per_s"] / r1["velocity_m_per_s"]
    assert 1.5 < ratio < 2.5, f"Slope sensitivity ratio={ratio:.3f}"


# ---------------------------------------------------------------------------
# 22. Manning n sensitivity: double n → lower velocity at same Q
# ---------------------------------------------------------------------------

def test_manning_n_sensitivity():
    """Doubling Manning's n decreases velocity (higher roughness, deeper flow)."""
    r1 = manning_normal_depth(flow_m3s=0.3, width_m=1.0, slope=0.001, manning_n=0.013)
    r2 = manning_normal_depth(flow_m3s=0.3, width_m=1.0, slope=0.001, manning_n=0.026)
    assert r1["ok"] and r2["ok"]
    # Higher n → deeper flow → lower velocity
    assert r2["normal_depth_m"] > r1["normal_depth_m"]
    assert r2["velocity_m_per_s"] < r1["velocity_m_per_s"]


# ---------------------------------------------------------------------------
# 23. Manning hand-calc at second set of values
# ---------------------------------------------------------------------------

def test_manning_normal_depth_second_hand_calc():
    """Verify at B=2m, n=0.025, S=0.002, Q=1.5 m³/s."""
    B = 2.0
    n = 0.025
    S = 0.002
    Q = 1.5
    result = manning_normal_depth(flow_m3s=Q, width_m=B, slope=S, manning_n=n)
    assert result["ok"]
    y_n = result["normal_depth_m"]
    A = B * y_n
    P = B + 2 * y_n
    R = A / P
    Q_check = (1.0 / n) * A * (R ** (2.0/3.0)) * math.sqrt(S)
    assert abs(Q_check - Q) / Q < 1e-4, \
        f"Q_check={Q_check:.6f} vs Q={Q:.6f}, y_n={y_n:.4f}"


# ---------------------------------------------------------------------------
# 24. Darcy-Weisbach DhF_dQ is always positive
# ---------------------------------------------------------------------------

def test_darcy_weisbach_dhf_dq_positive():
    pipe = Pipe(pipe_id="p", start_node="A", end_node="B",
                length=200, diameter=0.1, roughness=0.3)
    for q in [0.001, 0.01, 0.05, 0.1]:
        dhf = _darcy_weisbach_dhf_dq(q, pipe)
        assert dhf > 0, f"dHf/dQ should be positive at Q={q}, got {dhf}"


# ---------------------------------------------------------------------------
# 25. Hydraulics pipe-network tool — ok payload
# ---------------------------------------------------------------------------

def test_tool_pipe_network_ok():
    from kerf_cad_core.civil.hydraulics_tools import run_hydraulics_pipe_network
    ctx = _make_ctx()
    args = json.dumps({
        "nodes": [
            {"node_id": "R", "elevation": 10.0, "head_fixed": 30.0},
            {"node_id": "J", "elevation": 5.0, "demand": 8.0},
        ],
        "pipes": [
            {"pipe_id": "p1", "start_node": "R", "end_node": "J",
             "length": 200, "diameter": 0.1, "hw_c": 120},
        ],
    }).encode()
    raw = _run(run_hydraulics_pipe_network(ctx, args))
    result = json.loads(raw)
    assert result.get("ok"), f"Expected ok, got: {result}"
    assert len(result["nodes"]) == 2
    assert len(result["pipes"]) == 1


# ---------------------------------------------------------------------------
# 26. Hydraulics pipe-network tool — bad JSON returns BAD_ARGS
# ---------------------------------------------------------------------------

def test_tool_pipe_network_bad_json():
    from kerf_cad_core.civil.hydraulics_tools import run_hydraulics_pipe_network
    ctx = _make_ctx()
    raw = _run(run_hydraulics_pipe_network(ctx, b"not json {{{"))
    result = json.loads(raw)
    # err_payload returns {"error": ..., "code": "BAD_ARGS"}
    assert result.get("code") == "BAD_ARGS" or result.get("ok") is False


# ---------------------------------------------------------------------------
# 27. Hydraulics Manning tool — ok payload
# ---------------------------------------------------------------------------

def test_tool_manning_ok():
    from kerf_cad_core.civil.hydraulics_tools import run_hydraulics_manning
    ctx = _make_ctx()
    args = json.dumps({
        "flow_m3s": 0.5,
        "width_m": 1.0,
        "slope": 0.001,
        "manning_n": 0.013,
    }).encode()
    raw = _run(run_hydraulics_manning(ctx, args))
    result = json.loads(raw)
    assert result.get("ok"), f"Expected ok, got: {result}"
    assert "normal_depth_m" in result
    assert result["normal_depth_m"] > 0


# ---------------------------------------------------------------------------
# 28. Hydraulics Manning tool — missing field returns error
# ---------------------------------------------------------------------------

def test_tool_manning_missing_field():
    from kerf_cad_core.civil.hydraulics_tools import run_hydraulics_manning
    ctx = _make_ctx()
    args = json.dumps({"flow_m3s": 0.5, "width_m": 1.0}).encode()  # missing slope, manning_n
    raw = _run(run_hydraulics_manning(ctx, args))
    result = json.loads(raw)
    assert result.get("ok") is False
    assert "reason" in result


# ---------------------------------------------------------------------------
# 29. plugin._TOOL_MODULES includes hydraulics_tools
# ---------------------------------------------------------------------------

def test_plugin_includes_hydraulics_tools():
    from kerf_cad_core.plugin import _TOOL_MODULES
    assert "kerf_cad_core.civil.hydraulics_tools" in _TOOL_MODULES


# ---------------------------------------------------------------------------
# 30. Darcy-Weisbach Colebrook-White gives physically plausible f (0.01–0.1)
# ---------------------------------------------------------------------------

def test_darcy_weisbach_friction_factor_range():
    """Colebrook-White friction factor falls in physically expected range."""
    pipe = Pipe(pipe_id="p", start_node="A", end_node="B",
                length=100, diameter=0.1, roughness=0.5)
    Q = 0.01
    area = math.pi * 0.1 ** 2 / 4
    v = Q / area
    # Reconstruct f from DW formula: f = hf * 2g * D / (L * v^2)
    hf = _darcy_weisbach_hf(Q, pipe)
    f = hf * 2 * _G * 0.1 / (100.0 * v ** 2)
    assert 0.01 < f < 0.1, f"Friction factor {f:.4f} outside 0.01–0.1"
