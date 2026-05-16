"""
Hermetic tests for the PCB trace current-capacity and copper-thermal module.

Covers ≥30 tests:

  ipc2152_trace_current
    - Returns ok=True with required keys
    - External layer gives higher capacity than internal
    - Capacity scales with delta_t (higher ΔT → more current)
    - Heavier copper → more capacity (wider cross-section)
    - Wider trace → more capacity
    - Adjacent plane (h_plane_mm) increases capacity (cf_pl > 1)
    - Higher k_pcb increases capacity (better heat spreading)
    - Negative width → ok=False
    - Invalid layer → ok=False

  required_trace_width
    - Returns ok=True with required keys
    - Width increases for larger current
    - Width decreases when ΔT allowance increases
    - Internal layer → wider trace required than external
    - Round-trip: width gives back approximately the target current

  trace_resistance
    - R = ρ × L / A (hand-calc for 1 oz, 1 mm wide, 100 mm long)
    - R increases with temperature (positive TCR)
    - Halving width doubles resistance
    - Power = I² × R
    - Voltage drop = I × R
    - Zero width → ok=False
    - Zero length → ok=False

  via_current_capacity
    - Returns ok=True with required keys
    - Larger drill → more capacity (larger circumference)
    - Thicker plating → more capacity
    - Capacity is positive for valid inputs
    - Zero drill → ok=False

  required_via_count
    - 1 via sufficient for small current
    - Multiple vias for large current
    - n_vias × per_via ≥ total_current_a
    - Zero total current → ok=False

  thermal_via_array
    - Returns ok=True with required keys
    - More vias → lower rth_array
    - Larger array side → lower rth_spread
    - delta_t = power × rth_total
    - n_vias=0 → ok=False
    - Negative drill → ok=False

  plane_sheet_resistance
    - Rs = rho_Cu / t_Cu (hand-calc at 25°C, 1 oz)
    - Rs increases with temperature
    - Heavier copper → lower Rs
    - With current_a and plane_width_mm: returns current_density_a_mm2
    - Onderdonk fuse time present when current given
    - Large current → short fusing time
    - current_a given without plane_width_mm → ok=False

  polygon_pour_heatsink_area
    - Larger target Rθ → smaller required area
    - Higher k_pcb → smaller area
    - Returns area_cm2 and side_mm
    - Zero rth_target → ok=False

  busbar_sizing
    - Returns ok=True with required keys
    - W = I / (J × T) (hand-calc)
    - Larger J_max → narrower busbar
    - Thicker busbar → narrower width required
    - Resistance consistent with hand-calc

  LLM tool handlers (stub registry)
    - tracecurrent_ipc2152 tool returns ok=True
    - tracecurrent_required_width tool returns ok=True
    - tracecurrent_resistance tool returns ok=True
    - tracecurrent_via_capacity tool returns ok=True
    - tracecurrent_via_count tool returns ok=True
    - tracecurrent_thermal_via tool returns ok=True
    - tracecurrent_plane_rs tool returns ok=True
    - tracecurrent_pour_area tool returns ok=True
    - tracecurrent_busbar tool returns ok=True
    - Tool with invalid JSON → returns error payload (ok=False)
    - TOOLS list has 9 entries

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
import warnings

# ── Prefer the real kerf_chat if installed; stub otherwise ───────────────────
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps(
    {"ok": False, "error": msg, "code": code}
)
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.tracecurrent.ampacity import (
    ipc2152_trace_current,
    required_trace_width,
    trace_resistance,
    via_current_capacity,
    required_via_count,
    thermal_via_array,
    plane_sheet_resistance,
    polygon_pour_heatsink_area,
    busbar_sizing,
    _OZ_TO_MM,
    _RHO_CU_20C,
    _ALPHA_CU,
    _K_CU,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.tracecurrent.tools",
    os.path.join(_SRC, "kerf_electronics", "tracecurrent", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

tracecurrent_ipc2152_tool = _tool_mod.tracecurrent_ipc2152
tracecurrent_required_width_tool = _tool_mod.tracecurrent_required_width
tracecurrent_resistance_tool = _tool_mod.tracecurrent_resistance
tracecurrent_via_capacity_tool = _tool_mod.tracecurrent_via_capacity
tracecurrent_via_count_tool = _tool_mod.tracecurrent_via_count
tracecurrent_thermal_via_tool = _tool_mod.tracecurrent_thermal_via
tracecurrent_plane_rs_tool = _tool_mod.tracecurrent_plane_rs
tracecurrent_pour_area_tool = _tool_mod.tracecurrent_pour_area
tracecurrent_busbar_tool = _tool_mod.tracecurrent_busbar
TOOLS = _tool_mod.TOOLS


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ipc2152_trace_current
# ═══════════════════════════════════════════════════════════════════════════════

class TestIpc2152TraceCurrent:
    """IPC-2152 steady-state trace current capacity."""

    def test_returns_ok_with_required_keys(self):
        res = ipc2152_trace_current(width_mm=1.0)
        assert res["ok"] is True
        for k in ("current_a", "cross_section_mil2", "cf_copper_weight",
                  "cf_board", "cf_plane", "layer", "warnings"):
            assert k in res, f"missing key {k!r}"

    def test_external_higher_than_internal(self):
        """External layer convects better → higher current capacity."""
        ext = ipc2152_trace_current(width_mm=1.0, layer="external")
        int_ = ipc2152_trace_current(width_mm=1.0, layer="internal")
        assert ext["current_a"] > int_["current_a"]

    def test_higher_delta_t_more_current(self):
        """Larger allowed temperature rise → more current."""
        lo = ipc2152_trace_current(width_mm=1.0, delta_t_c=5.0)
        hi = ipc2152_trace_current(width_mm=1.0, delta_t_c=20.0)
        assert hi["current_a"] > lo["current_a"]

    def test_heavier_copper_more_current(self):
        """2 oz copper has more cross-section → more current."""
        oz1 = ipc2152_trace_current(width_mm=1.0, copper_oz=1.0)
        oz2 = ipc2152_trace_current(width_mm=1.0, copper_oz=2.0)
        assert oz2["current_a"] > oz1["current_a"]

    def test_wider_trace_more_current(self):
        """Wider trace → bigger area → more current."""
        n = ipc2152_trace_current(width_mm=0.5)
        w = ipc2152_trace_current(width_mm=2.0)
        assert w["current_a"] > n["current_a"]

    def test_adjacent_plane_increases_capacity(self):
        """Copper plane close by increases heat spreading (cf_pl > 1)."""
        no_plane = ipc2152_trace_current(width_mm=1.0)
        with_plane = ipc2152_trace_current(width_mm=1.0, h_plane_mm=0.1)
        assert with_plane["current_a"] > no_plane["current_a"]
        assert with_plane["cf_plane"] > 1.0

    def test_higher_k_pcb_increases_capacity(self):
        """Higher board k → more heat conducted away → higher current."""
        low_k = ipc2152_trace_current(width_mm=1.0, k_pcb=0.25)
        high_k = ipc2152_trace_current(width_mm=1.0, k_pcb=1.0)
        assert high_k["current_a"] > low_k["current_a"]

    def test_negative_width_returns_error(self):
        res = ipc2152_trace_current(width_mm=-1.0)
        assert res["ok"] is False
        assert "reason" in res

    def test_invalid_layer_returns_error(self):
        res = ipc2152_trace_current(width_mm=1.0, layer="buried")
        assert res["ok"] is False

    def test_cross_section_mil2_formula(self):
        """Cross-section = width_mil × thickness_mil; verify against reference."""
        # 1 mm wide, 1 oz = 34.8 µm = 0.0348 mm
        # width_mil = 1.0 × 39.3701 = 39.3701 mil
        # thickness_mil = 0.0348 × 39.3701 ≈ 1.3701 mil
        # area_mil² ≈ 39.3701 × 1.3701 ≈ 53.95 mil²
        res = ipc2152_trace_current(width_mm=1.0, copper_oz=1.0)
        expected = 1.0 * 39.3701 * 0.0348 * 39.3701
        assert abs(res["cross_section_mil2"] - expected) < 0.5, (
            f"cross_section_mil2 {res['cross_section_mil2']} vs expected {expected:.2f}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. required_trace_width
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequiredTraceWidth:
    """Bisection solver for trace width."""

    def test_returns_ok_with_required_keys(self):
        res = required_trace_width(current_a=1.0)
        assert res["ok"] is True
        for k in ("width_mm", "current_a", "delta_t_c", "cross_section_mil2"):
            assert k in res

    def test_larger_current_needs_wider_trace(self):
        lo = required_trace_width(current_a=1.0)
        hi = required_trace_width(current_a=5.0)
        assert hi["width_mm"] > lo["width_mm"]

    def test_higher_delta_t_allows_narrower_trace(self):
        tight = required_trace_width(current_a=2.0, delta_t_c=5.0)
        relaxed = required_trace_width(current_a=2.0, delta_t_c=20.0)
        assert relaxed["width_mm"] < tight["width_mm"]

    def test_internal_requires_wider_trace(self):
        ext = required_trace_width(current_a=2.0, layer="external")
        int_ = required_trace_width(current_a=2.0, layer="internal")
        assert int_["width_mm"] > ext["width_mm"]

    def test_round_trip_capacity(self):
        """Width from solver → capacity ≥ target current."""
        target = 3.0
        res = required_trace_width(current_a=target)
        cap = ipc2152_trace_current(
            width_mm=res["width_mm"],
            delta_t_c=res["delta_t_c"],
        )
        assert cap["current_a"] >= target * 0.999  # within 0.1%

    def test_zero_current_returns_error(self):
        res = required_trace_width(current_a=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. trace_resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestTraceResistance:
    """DC resistance, I²R, voltage drop."""

    def test_hand_calc_resistance(self):
        """1 mm wide, 1 oz (34.8 µm = 0.0348 mm), 100 mm long, 20°C.
           R = ρ₂₀ × L / A = 1.724e-8 × 0.1 / (1e-3 × 34.8e-6)
             = 1.724e-8 × 0.1 / (34.8e-9)
             ≈ 49.5 mΩ
        """
        res = trace_resistance(width_mm=1.0, length_mm=100.0, copper_oz=1.0,
                                current_a=0.0, temp_c=20.0)
        assert res["ok"] is True
        expected = _RHO_CU_20C * 0.1 / (1e-3 * _OZ_TO_MM * 1e-3)
        assert abs(res["resistance_ohm"] - expected) / expected < 1e-4, (
            f"R={res['resistance_ohm']:.6f} vs expected {expected:.6f}"
        )

    def test_resistance_increases_with_temperature(self):
        """Copper has positive TCR: R(100°C) > R(25°C)."""
        lo = trace_resistance(width_mm=1.0, length_mm=100.0, temp_c=25.0)
        hi = trace_resistance(width_mm=1.0, length_mm=100.0, temp_c=100.0)
        assert hi["resistance_ohm"] > lo["resistance_ohm"]

    def test_halving_width_doubles_resistance(self):
        r1 = trace_resistance(width_mm=1.0, length_mm=100.0)
        r2 = trace_resistance(width_mm=0.5, length_mm=100.0)
        assert abs(r2["resistance_ohm"] / r1["resistance_ohm"] - 2.0) < 1e-6

    def test_power_equals_i_squared_r(self):
        res = trace_resistance(width_mm=1.0, length_mm=100.0, current_a=2.5)
        # resistance_ohm is rounded to 8 dp; allow tolerance from rounding
        expected_p = 2.5 ** 2 * res["resistance_ohm"]
        assert abs(res["power_w"] - expected_p) < 1e-5

    def test_voltage_drop_equals_i_times_r(self):
        res = trace_resistance(width_mm=1.0, length_mm=100.0, current_a=3.0)
        # resistance_ohm is rounded to 8 dp; allow tolerance from rounding
        expected_v = 3.0 * res["resistance_ohm"]
        assert abs(res["voltage_drop_v"] - expected_v) < 1e-5

    def test_zero_width_returns_error(self):
        res = trace_resistance(width_mm=0.0, length_mm=100.0)
        assert res["ok"] is False

    def test_zero_length_returns_error(self):
        res = trace_resistance(width_mm=1.0, length_mm=0.0)
        assert res["ok"] is False

    def test_sheet_resistance_formula(self):
        """Rs = ρ / t_Cu at 20°C."""
        res = trace_resistance(width_mm=1.0, length_mm=1.0, copper_oz=1.0,
                                temp_c=20.0)
        expected_rs = _RHO_CU_20C / (_OZ_TO_MM * 1e-3)
        assert abs(res["sheet_resistance_ohm_sq"] - expected_rs) / expected_rs < 1e-4


# ═══════════════════════════════════════════════════════════════════════════════
# 4. via_current_capacity
# ═══════════════════════════════════════════════════════════════════════════════

class TestViaCurrentCapacity:
    """Via barrel current capacity."""

    def test_returns_ok_with_required_keys(self):
        res = via_current_capacity(drill_mm=0.3)
        assert res["ok"] is True
        for k in ("current_a", "barrel_area_mil2", "drill_mm", "plating_mm"):
            assert k in res

    def test_larger_drill_more_capacity(self):
        """Larger drill → larger circumference → more barrel area."""
        small = via_current_capacity(drill_mm=0.2)
        large = via_current_capacity(drill_mm=0.5)
        assert large["current_a"] > small["current_a"]

    def test_thicker_plating_more_capacity(self):
        """Thicker plating → more cross-section area."""
        thin = via_current_capacity(drill_mm=0.3, plating_mm=0.018)
        thick = via_current_capacity(drill_mm=0.3, plating_mm=0.035)
        assert thick["current_a"] > thin["current_a"]

    def test_capacity_positive(self):
        res = via_current_capacity(drill_mm=0.3, plating_mm=0.025)
        assert res["current_a"] > 0

    def test_zero_drill_returns_error(self):
        res = via_current_capacity(drill_mm=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. required_via_count
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequiredViaCount:
    """Minimum number of vias for a current."""

    def test_small_current_one_via(self):
        """A tiny current should need exactly 1 via."""
        res = required_via_count(total_current_a=0.01, drill_mm=0.3)
        assert res["ok"] is True
        assert res["n_vias"] == 1

    def test_large_current_multiple_vias(self):
        """10 A should require multiple vias for a 0.3 mm drill."""
        res = required_via_count(total_current_a=10.0, drill_mm=0.3)
        assert res["ok"] is True
        assert res["n_vias"] > 1

    def test_n_vias_times_per_via_covers_total(self):
        """n × per_via_capacity ≥ total_current_a."""
        total = 5.0
        res = required_via_count(total_current_a=total, drill_mm=0.3)
        assert res["ok"] is True
        assert res["n_vias"] * res["current_per_via_a"] >= total * 0.999

    def test_zero_current_returns_error(self):
        res = required_via_count(total_current_a=0.0, drill_mm=0.3)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. thermal_via_array
# ═══════════════════════════════════════════════════════════════════════════════

class TestThermalViaArray:
    """Thermal resistance of a via array."""

    def test_returns_ok_with_required_keys(self):
        res = thermal_via_array(n_vias=4, drill_mm=0.3)
        assert res["ok"] is True
        for k in ("rth_via_each_k_per_w", "rth_array_k_per_w",
                  "rth_spread_k_per_w", "rth_total_k_per_w", "delta_t_k"):
            assert k in res

    def test_more_vias_lower_rth_array(self):
        """Parallel vias: Rθ_array = Rθ_each / n → more vias → lower Rθ."""
        few = thermal_via_array(n_vias=4, drill_mm=0.3)
        many = thermal_via_array(n_vias=16, drill_mm=0.3)
        assert many["rth_array_k_per_w"] < few["rth_array_k_per_w"]

    def test_double_vias_halves_rth_array(self):
        """Rθ_array ∝ 1/n."""
        r4 = thermal_via_array(n_vias=4, drill_mm=0.3)
        r8 = thermal_via_array(n_vias=8, drill_mm=0.3)
        ratio = r4["rth_array_k_per_w"] / r8["rth_array_k_per_w"]
        assert abs(ratio - 2.0) < 1e-6

    def test_larger_array_side_lower_rth_spread(self):
        """Larger footprint → more spreading → lower Rθ_spread."""
        small = thermal_via_array(n_vias=4, drill_mm=0.3, array_side_mm=2.0)
        large = thermal_via_array(n_vias=4, drill_mm=0.3, array_side_mm=5.0)
        assert large["rth_spread_k_per_w"] < small["rth_spread_k_per_w"]

    def test_delta_t_equals_power_times_rth(self):
        """ΔT = P × Rθ_total."""
        res = thermal_via_array(n_vias=4, drill_mm=0.3, power_w=2.0)
        expected_dt = 2.0 * res["rth_total_k_per_w"]
        assert abs(res["delta_t_k"] - expected_dt) < 1e-6

    def test_zero_vias_returns_error(self):
        res = thermal_via_array(n_vias=0, drill_mm=0.3)
        assert res["ok"] is False

    def test_negative_drill_returns_error(self):
        res = thermal_via_array(n_vias=4, drill_mm=-0.3)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. plane_sheet_resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlaneSheetResistance:
    """Copper-plane sheet resistance and Onderdonk cross-check."""

    def test_hand_calc_rs_at_25c_1oz(self):
        """Rs = ρ_Cu(25°C) / t_Cu  (1 oz = 0.0348 mm)."""
        res = plane_sheet_resistance(copper_oz=1.0, temp_c=25.0)
        assert res["ok"] is True
        rho_25 = _RHO_CU_20C * (1 + _ALPHA_CU * 5.0)
        expected_rs = rho_25 / (_OZ_TO_MM * 1e-3)
        assert abs(res["sheet_resistance_ohm_sq"] - expected_rs) / expected_rs < 1e-4

    def test_rs_increases_with_temperature(self):
        lo = plane_sheet_resistance(copper_oz=1.0, temp_c=25.0)
        hi = plane_sheet_resistance(copper_oz=1.0, temp_c=100.0)
        assert hi["sheet_resistance_ohm_sq"] > lo["sheet_resistance_ohm_sq"]

    def test_heavier_copper_lower_rs(self):
        oz1 = plane_sheet_resistance(copper_oz=1.0)
        oz2 = plane_sheet_resistance(copper_oz=2.0)
        assert oz2["sheet_resistance_ohm_sq"] < oz1["sheet_resistance_ohm_sq"]

    def test_current_density_returned_when_current_given(self):
        res = plane_sheet_resistance(copper_oz=1.0, current_a=5.0, plane_width_mm=10.0)
        assert res["ok"] is True
        assert "current_density_a_mm2" in res
        # J = I / (W × T) = 5 / (10 × 0.0348) = 14.37 A/mm²
        t_mm = _OZ_TO_MM
        expected_j = 5.0 / (10.0 * t_mm)
        assert abs(res["current_density_a_mm2"] - expected_j) / expected_j < 1e-3

    def test_onderdonk_fuse_time_present_when_current_given(self):
        res = plane_sheet_resistance(copper_oz=1.0, current_a=5.0, plane_width_mm=10.0)
        assert "onderdonk_fuse_time_s" in res

    def test_large_current_short_fuse_time(self):
        """High current density → short Onderdonk fusing time."""
        normal = plane_sheet_resistance(copper_oz=1.0, current_a=1.0, plane_width_mm=1.0)
        heavy = plane_sheet_resistance(copper_oz=1.0, current_a=100.0, plane_width_mm=1.0)
        if normal["onderdonk_fuse_time_s"] and heavy["onderdonk_fuse_time_s"]:
            assert heavy["onderdonk_fuse_time_s"] < normal["onderdonk_fuse_time_s"]

    def test_current_without_width_returns_error(self):
        res = plane_sheet_resistance(copper_oz=1.0, current_a=5.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. polygon_pour_heatsink_area
# ═══════════════════════════════════════════════════════════════════════════════

class TestPolygonPourHeatsinkArea:
    """Required copper-pour area for target Rθ."""

    def test_returns_ok_with_required_keys(self):
        res = polygon_pour_heatsink_area(rth_target_k_per_w=10.0)
        assert res["ok"] is True
        for k in ("area_mm2", "area_cm2", "side_mm"):
            assert k in res

    def test_larger_target_rth_smaller_area(self):
        """Higher Rθ_target (less demanding) → smaller required pour area."""
        tight = polygon_pour_heatsink_area(rth_target_k_per_w=5.0)
        relaxed = polygon_pour_heatsink_area(rth_target_k_per_w=50.0)
        assert relaxed["area_mm2"] < tight["area_mm2"]

    def test_higher_k_pcb_smaller_area(self):
        """Higher k → less area needed."""
        low_k = polygon_pour_heatsink_area(rth_target_k_per_w=10.0, k_pcb=0.25)
        high_k = polygon_pour_heatsink_area(rth_target_k_per_w=10.0, k_pcb=1.0)
        assert high_k["area_mm2"] < low_k["area_mm2"]

    def test_formula_verification(self):
        """A_pour = t_pcb / (Rθ × k_pcb)."""
        rth = 10.0
        t_mm = 1.6
        k = 0.25
        res = polygon_pour_heatsink_area(rth_target_k_per_w=rth, t_pcb_mm=t_mm, k_pcb=k)
        expected_m2 = (t_mm * 1e-3) / (rth * k)
        expected_mm2 = expected_m2 * 1e6
        assert abs(res["area_mm2"] - expected_mm2) / expected_mm2 < 1e-6

    def test_zero_rth_returns_error(self):
        res = polygon_pour_heatsink_area(rth_target_k_per_w=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. busbar_sizing
# ═══════════════════════════════════════════════════════════════════════════════

class TestBusbarSizing:
    """Copper busbar width and resistance."""

    def test_returns_ok_with_required_keys(self):
        res = busbar_sizing(current_a=100.0)
        assert res["ok"] is True
        for k in ("width_mm", "cross_section_mm2", "resistance_ohm",
                  "power_w", "voltage_drop_v"):
            assert k in res

    def test_width_formula(self):
        """W = I / (J × T).  width_mm is rounded to 3 dp; allow 1e-3 tolerance."""
        i = 100.0
        t = 2.0
        j = 3.0
        res = busbar_sizing(current_a=i, thickness_mm=t, j_max_a_mm2=j)
        expected_w = i / (j * t)
        assert abs(res["width_mm"] - expected_w) < 1e-3

    def test_larger_j_max_narrower_busbar(self):
        lo = busbar_sizing(current_a=100.0, j_max_a_mm2=2.0)
        hi = busbar_sizing(current_a=100.0, j_max_a_mm2=5.0)
        assert hi["width_mm"] < lo["width_mm"]

    def test_thicker_busbar_narrower_width(self):
        thin = busbar_sizing(current_a=100.0, thickness_mm=1.0)
        thick = busbar_sizing(current_a=100.0, thickness_mm=3.0)
        assert thick["width_mm"] < thin["width_mm"]

    def test_resistance_hand_calc(self):
        """R = ρ_Cu(25°C) × L / A."""
        i = 100.0
        t_mm = 2.0
        j = 3.0
        l_mm = 100.0
        res = busbar_sizing(current_a=i, thickness_mm=t_mm, j_max_a_mm2=j,
                             length_mm=l_mm, temp_c=25.0)
        w_mm = i / (j * t_mm)
        a_m2 = (w_mm * t_mm) * 1e-6
        rho = _RHO_CU_20C * (1 + _ALPHA_CU * 5.0)
        expected_r = rho * (l_mm * 1e-3) / a_m2
        assert abs(res["resistance_ohm"] - expected_r) / expected_r < 1e-4

    def test_zero_current_returns_error(self):
        res = busbar_sizing(current_a=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. LLM tool handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestLlmToolHandlers:
    """LLM tool handlers — stub registry active."""

    @pytest.mark.asyncio
    async def test_tracecurrent_ipc2152_tool_ok(self):
        res = await call(tracecurrent_ipc2152_tool, width_mm=1.0, delta_t_c=10.0)
        assert res["ok"] is True
        assert "current_a" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_required_width_tool_ok(self):
        res = await call(tracecurrent_required_width_tool, current_a=2.0)
        assert res["ok"] is True
        assert "width_mm" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_resistance_tool_ok(self):
        res = await call(tracecurrent_resistance_tool, width_mm=1.0, length_mm=100.0)
        assert res["ok"] is True
        assert "resistance_ohm" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_via_capacity_tool_ok(self):
        res = await call(tracecurrent_via_capacity_tool, drill_mm=0.3)
        assert res["ok"] is True
        assert "current_a" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_via_count_tool_ok(self):
        res = await call(tracecurrent_via_count_tool, total_current_a=5.0, drill_mm=0.3)
        assert res["ok"] is True
        assert "n_vias" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_thermal_via_tool_ok(self):
        res = await call(tracecurrent_thermal_via_tool, n_vias=4, drill_mm=0.3)
        assert res["ok"] is True
        assert "rth_total_k_per_w" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_plane_rs_tool_ok(self):
        res = await call(tracecurrent_plane_rs_tool, copper_oz=1.0)
        assert res["ok"] is True
        assert "sheet_resistance_ohm_sq" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_pour_area_tool_ok(self):
        res = await call(tracecurrent_pour_area_tool, rth_target_k_per_w=10.0)
        assert res["ok"] is True
        assert "area_mm2" in res

    @pytest.mark.asyncio
    async def test_tracecurrent_busbar_tool_ok(self):
        res = await call(tracecurrent_busbar_tool, current_a=100.0)
        assert res["ok"] is True
        assert "width_mm" in res

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        raw = await tracecurrent_ipc2152_tool(None, b"not-valid-json{")
        data = json.loads(raw)
        # Real registry err_payload: {"error": ..., "code": ...}; stub: {"ok": False, ...}
        assert data.get("ok") is False or "error" in data

    def test_tools_list_length(self):
        assert len(TOOLS) == 9

    def test_tools_list_names_unique(self):
        names = [t[0] for t in TOOLS]
        assert len(names) == len(set(names))

    def test_ipc2152_tool_bad_args_returns_error(self):
        import asyncio
        raw = asyncio.get_event_loop().run_until_complete(
            tracecurrent_ipc2152_tool(None, json.dumps({"width_mm": -5.0}).encode())
        )
        data = json.loads(raw)
        # Real registry err_payload: {"error": ..., "code": ...}; stub: {"ok": False, ...}
        assert data.get("ok") is False or "error" in data
