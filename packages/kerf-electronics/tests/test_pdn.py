"""
Hermetic tests for kerf_electronics PDN analyzer.

Covers:
  - Copper sheet resistance (1 oz, 2 oz, arbitrary weight)
  - Trace resistance (Ohm's law sanity, series / parallel analogy)
  - DC IR-drop solver: two-node, series, parallel, multi-sink
  - IR-drop pass/fail vs tolerance
  - Solver error handling (empty input, missing source, duplicate node IDs,
    unknown segment nodes, negative/zero resistance)
  - Target-impedance formula
  - Decap-count monotonic with ripple spec
  - Decap regime classification (capacitive / inductive)
  - pdn_report combined tool
  - LLM tool handlers (pdn_ir_drop, pdn_target_impedance, pdn_report) via
    async calls through the registry stub

Loading strategy: stub kerf_chat.tools.registry before importing the tool
module so no full kerf_chat install is required.

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
import pytest

# ── Stub kerf_chat.tools.registry ────────────────────────────────────────────

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"ok": False, "error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Import analyzer directly (pure Python, no kerf_chat dependency) ──────────

import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC = _os.path.join(_os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_electronics.pdn.analyzer import (
    PDNNode,
    PDNSegment,
    PDNResult,
    sheet_resistance_ohms_per_sq,
    trace_resistance,
    solve_ir_drop,
    target_impedance,
    decap_count_estimate,
)

# ── Load tool module via importlib so kerf_chat stub is active ────────────────

_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.tools.pdn",
    _os.path.join(_SRC, "kerf_electronics", "tools", "pdn.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

pdn_ir_drop = _tool_mod.pdn_ir_drop
pdn_target_impedance_tool = _tool_mod.pdn_target_impedance_tool
pdn_report = _tool_mod.pdn_report


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def two_node_net(r_ohms: float, i_draw: float = 1.0, v_src: float = 3.3):
    """Source → single sink with explicit resistance r_ohms."""
    nodes = [
        PDNNode("VDD", is_source=True, voltage_v=v_src),
        PDNNode("SINK", i_draw_a=i_draw),
    ]
    segs = [PDNSegment("VDD", "SINK", resistance_ohms=r_ohms)]
    return nodes, segs


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Sheet resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestSheetResistance:
    def test_1oz_approx_0_539_mohm_per_sq(self):
        r = sheet_resistance_ohms_per_sq(1.0)
        # 1 oz copper: ρ/t = 1.724e-5 / 0.035 ≈ 4.926e-4 Ω/sq = 0.4926 mΩ/sq
        # IPC table rounds to ~0.5 mΩ/sq; our constant gives ~0.493 mΩ/sq
        assert 4e-4 < r < 6e-4, f"1 oz sheet R out of range: {r}"

    def test_2oz_half_of_1oz(self):
        r1 = sheet_resistance_ohms_per_sq(1.0)
        r2 = sheet_resistance_ohms_per_sq(2.0)
        assert abs(r2 - r1 / 2) < 1e-8, "2 oz should be half of 1 oz sheet R"

    def test_0_5oz_double_of_1oz(self):
        r1 = sheet_resistance_ohms_per_sq(1.0)
        r_half = sheet_resistance_ohms_per_sq(0.5)
        assert abs(r_half - r1 * 2) < 1e-8, "0.5 oz should be double 1 oz sheet R"

    def test_3oz_lower_than_2oz(self):
        r2 = sheet_resistance_ohms_per_sq(2.0)
        r3 = sheet_resistance_ohms_per_sq(3.0)
        assert r3 < r2, "Thicker copper → lower sheet R"

    def test_invalid_zero_raises(self):
        with pytest.raises(ValueError):
            sheet_resistance_ohms_per_sq(0)

    def test_invalid_negative_raises(self):
        with pytest.raises(ValueError):
            sheet_resistance_ohms_per_sq(-1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Trace resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestTraceResistance:
    def test_ohms_law_sanity(self):
        """10mm × 1mm trace, 1 oz copper → 10 squares → R = 10 × Rsheet."""
        rsheet = sheet_resistance_ohms_per_sq(1.0)
        r = trace_resistance(length_mm=10.0, width_mm=1.0, copper_weight_oz=1.0)
        assert abs(r - rsheet * 10) < 1e-12

    def test_zero_length(self):
        r = trace_resistance(length_mm=0.0, width_mm=1.0, copper_weight_oz=1.0)
        assert r == 0.0

    def test_double_width_half_resistance(self):
        r1 = trace_resistance(10.0, 1.0, copper_weight_oz=1.0)
        r2 = trace_resistance(10.0, 2.0, copper_weight_oz=1.0)
        assert abs(r2 - r1 / 2) < 1e-12

    def test_double_length_double_resistance(self):
        r1 = trace_resistance(10.0, 1.0, copper_weight_oz=1.0)
        r2 = trace_resistance(20.0, 1.0, copper_weight_oz=1.0)
        assert abs(r2 - r1 * 2) < 1e-12

    def test_explicit_sheet_r_override(self):
        r = trace_resistance(5.0, 0.5, sheet_r=1e-3)
        # 5/0.5 = 10 squares × 1 mΩ/sq = 10 mΩ
        assert abs(r - 10e-3) < 1e-15

    def test_invalid_zero_width_raises(self):
        with pytest.raises(ValueError):
            trace_resistance(10.0, 0.0, copper_weight_oz=1.0)

    def test_invalid_negative_length_raises(self):
        with pytest.raises(ValueError):
            trace_resistance(-1.0, 1.0, copper_weight_oz=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DC IR-drop solver — core physics
# ═══════════════════════════════════════════════════════════════════════════════

class TestIRDropTwoNode:
    """Single resistor between source and one sink — pure Ohm's law."""

    def test_ohms_law_1ohm_1amp(self):
        nodes, segs = two_node_net(1.0, i_draw=1.0, v_src=5.0)
        r = solve_ir_drop(nodes, segs)
        assert r.error is None
        assert abs(r.worst_ir_drop_v - 1.0) < 1e-6

    def test_ohms_law_half_amp(self):
        nodes, segs = two_node_net(2.0, i_draw=0.5, v_src=3.3)
        r = solve_ir_drop(nodes, segs)
        # IR drop = 2Ω × 0.5A = 1V
        assert abs(r.worst_ir_drop_v - 1.0) < 1e-6

    def test_sink_voltage_equals_source_minus_drop(self):
        nodes, segs = two_node_net(0.1, i_draw=2.0, v_src=3.3)
        r = solve_ir_drop(nodes, segs)
        expected_v = 3.3 - 0.1 * 2.0
        assert abs(r.sinks[0].voltage_v - expected_v) < 1e-6

    def test_total_current_equals_sink_draw(self):
        nodes, segs = two_node_net(1.0, i_draw=0.75, v_src=1.8)
        r = solve_ir_drop(nodes, segs)
        assert abs(r.total_current_a - 0.75) < 1e-9

    def test_source_node_not_in_sinks(self):
        nodes, segs = two_node_net(1.0)
        r = solve_ir_drop(nodes, segs)
        sink_ids = [s.node_id for s in r.sinks]
        assert "VDD" not in sink_ids
        assert "SINK" in sink_ids


class TestIRDropSeries:
    """Two segments in series: VDD — R1 — MID — R2 — SINK."""

    def test_series_drops_sum(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=5.0),
            PDNNode("MID"),
            PDNNode("SINK", i_draw_a=1.0),
        ]
        segs = [
            PDNSegment("VDD", "MID", resistance_ohms=1.0),
            PDNSegment("MID", "SINK", resistance_ohms=2.0),
        ]
        r = solve_ir_drop(nodes, segs)
        # Total R = 3Ω, I = 1A → total IR drop = 3V
        assert abs(r.worst_ir_drop_v - 3.0) < 1e-6

    def test_mid_node_intermediate_voltage(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=5.0),
            PDNNode("MID"),
            PDNNode("SINK", i_draw_a=1.0),
        ]
        segs = [
            PDNSegment("VDD", "MID", resistance_ohms=1.0),
            PDNSegment("MID", "SINK", resistance_ohms=1.0),
        ]
        r = solve_ir_drop(nodes, segs)
        mid_v = r.all_node_voltages["MID"]
        # I = 1A through 2Ω total, MID is halfway: drop 1V → 4V
        assert abs(mid_v - 4.0) < 1e-6


class TestIRDropParallel:
    """Two parallel paths between VDD and SINK — effective R halves."""

    def test_parallel_paths_halve_resistance(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("SINK", i_draw_a=1.0),
        ]
        segs = [
            PDNSegment("VDD", "SINK", resistance_ohms=2.0),
            PDNSegment("VDD", "SINK", resistance_ohms=2.0),
        ]
        r = solve_ir_drop(nodes, segs)
        # Reff = 1Ω; IR drop = 1V
        assert abs(r.worst_ir_drop_v - 1.0) < 1e-5

    def test_asymmetric_parallel_paths(self):
        """Current divides inversely with resistance."""
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=5.0),
            PDNNode("SINK", i_draw_a=3.0),
        ]
        segs = [
            PDNSegment("VDD", "SINK", resistance_ohms=1.0),
            PDNSegment("VDD", "SINK", resistance_ohms=3.0),
        ]
        r = solve_ir_drop(nodes, segs)
        # Reff = (1×3)/(1+3) = 0.75Ω; IR drop = 3A × 0.75Ω = 2.25V
        assert abs(r.worst_ir_drop_v - 2.25) < 1e-5


class TestIRDropMultiSink:
    """Multiple sinks drawing different currents."""

    def test_multi_sink_superposition(self):
        """
        VDD −R1− SINK_A (1 A)
            −R2− SINK_B (2 A)

        Each branch is independent; IR drops add within each branch.
        """
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("SINK_A", i_draw_a=1.0),
            PDNNode("SINK_B", i_draw_a=2.0),
        ]
        segs = [
            PDNSegment("VDD", "SINK_A", resistance_ohms=0.5),
            PDNSegment("VDD", "SINK_B", resistance_ohms=0.5),
        ]
        r = solve_ir_drop(nodes, segs)
        # Each node is connected directly to VDD; KCL at VDD balances total I
        # Node A: V_A = 3.3 − 0.5×I_through_R1; Node B: V_B = 3.3 − 0.5×I_through_R2
        # At VDD (fixed): outflow = I_A + I_B = I through R1 + R2
        # V_A = 3.3 − (V_A branch current) × 0.5
        # Since VDD is fixed:
        #   I_branch_A = (3.3 − V_A) / 0.5 = I_draw_A = 1.0 → V_A = 3.3 − 0.5 = 2.8
        assert abs(r.all_node_voltages["SINK_A"] - 2.8) < 1e-5
        assert abs(r.all_node_voltages["SINK_B"] - 2.3) < 1e-5

    def test_worst_node_is_highest_drop(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("NEAR", i_draw_a=0.1),
            PDNNode("FAR", i_draw_a=0.1),
        ]
        segs = [
            PDNSegment("VDD", "NEAR", resistance_ohms=0.1),
            PDNSegment("VDD", "FAR", resistance_ohms=1.0),
        ]
        r = solve_ir_drop(nodes, segs)
        assert r.worst_node_id == "FAR"

    def test_total_current_sums_all_sinks(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("S1", i_draw_a=0.3),
            PDNNode("S2", i_draw_a=0.5),
            PDNNode("S3", i_draw_a=0.2),
        ]
        segs = [
            PDNSegment("VDD", "S1", resistance_ohms=0.1),
            PDNSegment("VDD", "S2", resistance_ohms=0.1),
            PDNSegment("VDD", "S3", resistance_ohms=0.1),
        ]
        r = solve_ir_drop(nodes, segs)
        assert abs(r.total_current_a - 1.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════════
# 4. IR-drop pass/fail vs tolerance
# ═══════════════════════════════════════════════════════════════════════════════

class TestIRDropPassFail:
    def test_pass_when_drop_within_budget(self):
        nodes, segs = two_node_net(0.01, i_draw=1.0, v_src=3.3)  # 10 mV drop
        r = solve_ir_drop(nodes, segs, ir_drop_budget_v=0.05)     # 50 mV budget
        assert r.all_pass is True
        assert r.sinks[0].pass_fail == "PASS"

    def test_fail_when_drop_exceeds_budget(self):
        nodes, segs = two_node_net(0.1, i_draw=1.0, v_src=3.3)   # 100 mV drop
        r = solve_ir_drop(nodes, segs, ir_drop_budget_v=0.05)     # 50 mV budget
        assert r.all_pass is False
        assert r.sinks[0].pass_fail == "FAIL"

    def test_unspec_when_no_budget(self):
        nodes, segs = two_node_net(0.1, i_draw=1.0, v_src=3.3)
        r = solve_ir_drop(nodes, segs)
        assert r.sinks[0].pass_fail == "UNSPEC"

    def test_mixed_pass_fail(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("OK", i_draw_a=0.1),     # 10 mV drop (within budget)
            PDNNode("BAD", i_draw_a=0.1),    # 100 mV drop (exceeds budget)
        ]
        segs = [
            PDNSegment("VDD", "OK", resistance_ohms=0.1),
            PDNSegment("VDD", "BAD", resistance_ohms=1.0),
        ]
        r = solve_ir_drop(nodes, segs, ir_drop_budget_v=0.05)
        pf_map = {s.node_id: s.pass_fail for s in r.sinks}
        assert pf_map["OK"] == "PASS"
        assert pf_map["BAD"] == "FAIL"
        assert r.all_pass is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Solver geometry inputs (sheet R from copper weight)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIRDropCopperGeometry:
    def test_segment_from_geometry_matches_explicit(self):
        """Segment built from copper geometry should match explicit resistance."""
        rsheet = sheet_resistance_ohms_per_sq(1.0)
        r_explicit = rsheet * (10.0 / 1.0)  # 10 squares

        nodes_a = [PDNNode("VDD", is_source=True, voltage_v=3.3), PDNNode("SINK", i_draw_a=0.1)]
        segs_a = [PDNSegment("VDD", "SINK", resistance_ohms=r_explicit)]

        nodes_b = [PDNNode("VDD", is_source=True, voltage_v=3.3), PDNNode("SINK", i_draw_a=0.1)]
        segs_b = [PDNSegment("VDD", "SINK", length_mm=10.0, width_mm=1.0,
                             sheet_resistance_ohms_per_sq=rsheet)]

        ra = solve_ir_drop(nodes_a, segs_a)
        rb = solve_ir_drop(nodes_b, segs_b)
        assert abs(ra.worst_ir_drop_v - rb.worst_ir_drop_v) < 1e-10


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Solver error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestIRDropErrors:
    def test_empty_nodes(self):
        r = solve_ir_drop([], [PDNSegment("A", "B", resistance_ohms=1.0)])
        assert r.error is not None

    def test_empty_segments(self):
        r = solve_ir_drop([PDNNode("VDD", is_source=True, voltage_v=3.3)], [])
        assert r.error is not None

    def test_no_source_node(self):
        nodes = [PDNNode("A", i_draw_a=1.0), PDNNode("B")]
        segs = [PDNSegment("A", "B", resistance_ohms=1.0)]
        r = solve_ir_drop(nodes, segs)
        assert r.error is not None
        assert "source" in r.error.lower()

    def test_two_source_nodes(self):
        nodes = [
            PDNNode("A", is_source=True, voltage_v=3.3),
            PDNNode("B", is_source=True, voltage_v=3.3),
        ]
        segs = [PDNSegment("A", "B", resistance_ohms=1.0)]
        r = solve_ir_drop(nodes, segs)
        assert r.error is not None

    def test_source_without_voltage(self):
        nodes = [PDNNode("VDD", is_source=True), PDNNode("SINK", i_draw_a=1.0)]
        segs = [PDNSegment("VDD", "SINK", resistance_ohms=1.0)]
        r = solve_ir_drop(nodes, segs)
        assert r.error is not None

    def test_segment_unknown_node(self):
        nodes = [PDNNode("VDD", is_source=True, voltage_v=3.3), PDNNode("SINK", i_draw_a=1.0)]
        segs = [PDNSegment("VDD", "GHOST", resistance_ohms=1.0)]
        r = solve_ir_drop(nodes, segs)
        assert r.error is not None

    def test_duplicate_node_ids(self):
        nodes = [
            PDNNode("VDD", is_source=True, voltage_v=3.3),
            PDNNode("VDD"),
        ]
        segs = [PDNSegment("VDD", "VDD", resistance_ohms=1.0)]
        r = solve_ir_drop(nodes, segs)
        assert r.error is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Target impedance formula
# ═══════════════════════════════════════════════════════════════════════════════

class TestTargetImpedance:
    def test_basic_formula(self):
        # Zt = (3.3 × 0.05) / 2 = 0.0825 Ω
        zt = target_impedance(3.3, 0.05, 2.0)
        assert abs(zt - 0.0825) < 1e-8

    def test_tighter_ripple_lower_zt(self):
        zt_5pct = target_impedance(1.8, 0.05, 5.0)
        zt_2pct = target_impedance(1.8, 0.02, 5.0)
        assert zt_2pct < zt_5pct

    def test_more_current_lower_zt(self):
        zt_low = target_impedance(3.3, 0.05, 10.0)
        zt_high = target_impedance(3.3, 0.05, 20.0)
        assert zt_high < zt_low

    def test_higher_vdd_higher_zt(self):
        zt_low = target_impedance(1.0, 0.05, 5.0)
        zt_high = target_impedance(5.0, 0.05, 5.0)
        assert zt_high > zt_low

    def test_invalid_zero_vdd(self):
        with pytest.raises(ValueError):
            target_impedance(0.0, 0.05, 1.0)

    def test_invalid_zero_ripple(self):
        with pytest.raises(ValueError):
            target_impedance(3.3, 0.0, 1.0)

    def test_invalid_ripple_over_1(self):
        with pytest.raises(ValueError):
            target_impedance(3.3, 1.5, 1.0)

    def test_invalid_zero_current(self):
        with pytest.raises(ValueError):
            target_impedance(3.3, 0.05, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Decap count estimator
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecapCount:
    def test_count_at_least_one(self):
        d = decap_count_estimate(
            target_impedance_ohms=0.1,
            cap_value_f=100e-9,
            cap_esl_h=1e-9,
            frequency_hz=10e6,
        )
        assert d["count"] >= 1

    def test_tighter_target_more_caps(self):
        """Halving the target impedance should require at least as many caps."""
        d1 = decap_count_estimate(0.05, 100e-9, 1e-9, 100e6)
        d2 = decap_count_estimate(0.025, 100e-9, 1e-9, 100e6)
        assert d2["count"] >= d1["count"]

    def test_more_ripple_fewer_caps(self):
        """Relaxing the ripple spec raises Zt → fewer caps needed."""
        zt_tight = target_impedance(3.3, 0.02, 5.0)  # 2% ripple
        zt_loose = target_impedance(3.3, 0.05, 5.0)  # 5% ripple
        d_tight = decap_count_estimate(zt_tight, 100e-9, 1e-9, 100e6)
        d_loose = decap_count_estimate(zt_loose, 100e-9, 1e-9, 100e6)
        assert d_loose["count"] <= d_tight["count"]

    def test_capacitive_regime_below_srf(self):
        cap = 100e-9
        esl = 1e-9
        srf = 1.0 / (2 * math.pi * math.sqrt(esl * cap))
        freq = srf * 0.1   # well below SRF
        d = decap_count_estimate(0.1, cap, esl, freq)
        assert d["regime"] == "capacitive"

    def test_inductive_regime_above_srf(self):
        cap = 100e-9
        esl = 1e-9
        srf = 1.0 / (2 * math.pi * math.sqrt(esl * cap))
        freq = srf * 10    # well above SRF
        d = decap_count_estimate(0.1, cap, esl, freq)
        assert d["regime"] == "inductive"

    def test_srf_computed_correctly(self):
        cap = 100e-9
        esl = 1e-9
        expected_srf = 1.0 / (2 * math.pi * math.sqrt(esl * cap))
        d = decap_count_estimate(0.1, cap, esl, 10e6)
        assert abs(d["srf_hz"] - expected_srf) < 1.0   # within 1 Hz

    def test_invalid_zero_target_z_raises(self):
        with pytest.raises(ValueError):
            decap_count_estimate(0.0, 100e-9, 1e-9, 10e6)

    def test_invalid_zero_cap_raises(self):
        with pytest.raises(ValueError):
            decap_count_estimate(0.1, 0.0, 1e-9, 10e6)

    def test_invalid_zero_esl_raises(self):
        with pytest.raises(ValueError):
            decap_count_estimate(0.1, 100e-9, 0.0, 10e6)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. LLM tool handler tests (async, via registry stub)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolPdnIrDrop:
    @pytest.mark.asyncio
    async def test_basic_two_node(self):
        result = await call(
            pdn_ir_drop,
            nodes=[
                {"node_id": "VDD", "is_source": True, "voltage_v": 3.3},
                {"node_id": "SINK", "i_draw_a": 1.0},
            ],
            segments=[{"node_a": "VDD", "node_b": "SINK", "resistance_ohms": 0.1}],
        )
        assert result["ok"] is True
        assert abs(result["worst_ir_drop_v"] - 0.1) < 1e-5

    @pytest.mark.asyncio
    async def test_copper_weight_auto_conversion(self):
        rsheet = sheet_resistance_ohms_per_sq(1.0)
        result = await call(
            pdn_ir_drop,
            nodes=[
                {"node_id": "PWR", "is_source": True, "voltage_v": 5.0},
                {"node_id": "LOAD", "i_draw_a": 0.5},
            ],
            segments=[{
                "node_a": "PWR", "node_b": "LOAD",
                "length_mm": 10.0, "width_mm": 1.0, "copper_weight_oz": 1.0,
            }],
        )
        assert result["ok"] is True
        expected_drop = rsheet * (10.0 / 1.0) * 0.5
        assert abs(result["worst_ir_drop_v"] - expected_drop) < 1e-8

    @pytest.mark.asyncio
    async def test_missing_nodes_returns_error(self):
        result = await call(
            pdn_ir_drop,
            segments=[{"node_a": "A", "node_b": "B", "resistance_ohms": 1.0}],
        )
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_missing_segments_returns_error(self):
        result = await call(
            pdn_ir_drop,
            nodes=[{"node_id": "VDD", "is_source": True, "voltage_v": 3.3}],
        )
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_pass_fail_in_result(self):
        result = await call(
            pdn_ir_drop,
            nodes=[
                {"node_id": "VDD", "is_source": True, "voltage_v": 3.3},
                {"node_id": "SINK", "i_draw_a": 1.0},
            ],
            segments=[{"node_a": "VDD", "node_b": "SINK", "resistance_ohms": 0.01}],
            ir_drop_budget_v=0.05,
        )
        assert result["ok"] is True
        assert result["all_pass"] is True
        assert result["sinks"][0]["pass_fail"] == "PASS"

    @pytest.mark.asyncio
    async def test_circuit_json_board_fallback(self):
        """Nodes/segments embedded in circuit_json.board are used as fallback."""
        board = {
            "type": "pcb_board",
            "pdn_nodes": [
                {"node_id": "VDD", "is_source": True, "voltage_v": 1.8},
                {"node_id": "CPU", "i_draw_a": 0.2},
            ],
            "pdn_segments": [
                {"node_a": "VDD", "node_b": "CPU", "resistance_ohms": 0.05}
            ],
        }
        result = await call(pdn_ir_drop, circuit_json=board)
        assert result["ok"] is True
        assert abs(result["worst_ir_drop_v"] - 0.01) < 1e-5

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        raw = b"not json"
        res = json.loads(await pdn_ir_drop(None, raw))
        assert res["ok"] is False


class TestToolPdnTargetImpedance:
    @pytest.mark.asyncio
    async def test_basic_calculation(self):
        result = await call(
            pdn_target_impedance_tool,
            vdd_v=3.3,
            ripple_fraction=0.05,
            i_transient_a=2.0,
            cap_value_f=100e-9,
            cap_esl_h=1e-9,
            frequency_hz=100e6,
        )
        assert result["ok"] is True
        zt = result["target_impedance_ohms"]
        assert abs(zt - (3.3 * 0.05 / 2.0)) < 1e-6

    @pytest.mark.asyncio
    async def test_decap_count_present(self):
        result = await call(
            pdn_target_impedance_tool,
            vdd_v=1.8,
            ripple_fraction=0.03,
            i_transient_a=5.0,
            cap_value_f=47e-9,
            cap_esl_h=0.5e-9,
            frequency_hz=200e6,
        )
        assert result["ok"] is True
        assert "decap" in result
        assert result["decap"]["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalid_zero_vdd(self):
        result = await call(
            pdn_target_impedance_tool,
            vdd_v=0.0,
            ripple_fraction=0.05,
            i_transient_a=1.0,
            cap_value_f=100e-9,
            cap_esl_h=1e-9,
            frequency_hz=100e6,
        )
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_missing_param_returns_error(self):
        result = await call(
            pdn_target_impedance_tool,
            vdd_v=3.3,
            ripple_fraction=0.05,
            # i_transient_a missing
            cap_value_f=100e-9,
            cap_esl_h=1e-9,
            frequency_hz=100e6,
        )
        assert result["ok"] is False


class TestToolPdnReport:
    @pytest.mark.asyncio
    async def test_combined_report(self):
        result = await call(
            pdn_report,
            nodes=[
                {"node_id": "VDD", "is_source": True, "voltage_v": 3.3},
                {"node_id": "FPGA", "i_draw_a": 0.5},
            ],
            segments=[{"node_a": "VDD", "node_b": "FPGA", "resistance_ohms": 0.05}],
            vdd_v=3.3,
            ripple_fraction=0.05,
            i_transient_a=0.5,
            cap_value_f=100e-9,
            cap_esl_h=1e-9,
            frequency_hz=100e6,
        )
        assert result["ok"] is True
        assert "ir_drop" in result
        assert "target_impedance" in result

    @pytest.mark.asyncio
    async def test_ir_drop_only_in_report(self):
        result = await call(
            pdn_report,
            nodes=[
                {"node_id": "VDD", "is_source": True, "voltage_v": 5.0},
                {"node_id": "MCU", "i_draw_a": 0.1},
            ],
            segments=[{"node_a": "VDD", "node_b": "MCU", "resistance_ohms": 0.2}],
        )
        assert result["ok"] is True
        assert "ir_drop" in result
        assert "target_impedance" not in result

    @pytest.mark.asyncio
    async def test_target_impedance_only_in_report(self):
        result = await call(
            pdn_report,
            vdd_v=1.0,
            ripple_fraction=0.05,
            i_transient_a=10.0,
            cap_value_f=10e-6,
            cap_esl_h=0.3e-9,
            frequency_hz=50e6,
        )
        assert result["ok"] is True
        assert "target_impedance" in result
        assert "ir_drop" not in result

    @pytest.mark.asyncio
    async def test_no_data_returns_error(self):
        result = await call(pdn_report)
        assert result["ok"] is False
