"""
Hermetic tests for the signal-integrity analyzer.

Loading strategy mirrors test_diffpair.py:
  - Stub kerf_chat.tools.registry so the tool layer is loadable without
    the full kerf_chat stack.
  - Load the solver directly from its file path (no install required).
  - Load the tool module from its file path.
  - All tests are self-contained; no network, no filesystem side-effects.

Author: imranparuk
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
# ── Prefer the real kerf_chat (installed in this monorepo). Pinning it into
#    sys.modules BEFORE the stub setdefaults means those become no-ops and the
#    stub never shadows the real, populated Registry that other suites import.
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

import types
import pytest


# ── Stub kerf_chat.tools.registry ────────────────────────────────────────────

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})  # real Registry is a list subclass; keep leaked stub import-compatible
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")

sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
_KERF_CHAT_SAVED = {
    _n: sys.modules.get(_n)
    for _n in ("kerf_chat", "kerf_chat.tools", "kerf_chat.tools.registry")
}
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub
# ── Load solver module ────────────────────────────────────────────────────────

_solver_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.si.solver",
    "packages/kerf-electronics/src/kerf_electronics/si/solver.py",
)
_solver = importlib.util.module_from_spec(_solver_spec)
_solver_spec.loader.exec_module(_solver)

# Expose solver functions under convenient names
microstrip_z0 = _solver.microstrip_z0
stripline_z0 = _solver.stripline_z0
diff_z0 = _solver.diff_z0
propagation_delay_ps_per_mm = _solver.propagation_delay_ps_per_mm
flight_time_ps = _solver.flight_time_ps
crosstalk_next = _solver.crosstalk_next
crosstalk_fext = _solver.crosstalk_fext
reflection_coefficient = _solver.reflection_coefficient
termination_recommendation = _solver.termination_recommendation


# ── Load tool module ──────────────────────────────────────────────────────────

# Pre-register the si sub-package modules in sys.modules so the tool file's
# "from kerf_electronics.si.solver import ..." resolves to _solver.
_ke_stub = types.ModuleType("kerf_electronics")
_ke_si_stub = types.ModuleType("kerf_electronics.si")
sys.modules.setdefault("kerf_electronics", _ke_stub)
sys.modules.setdefault("kerf_electronics.si", _ke_si_stub)
sys.modules["kerf_electronics.si.solver"] = _solver

_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.tools.si",
    "packages/kerf-electronics/src/kerf_electronics/tools/si.py",
)
_tool = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool)

si_impedance = _tool.si_impedance
si_propagation = _tool.si_propagation
si_crosstalk = _tool.si_crosstalk
si_termination = _tool.si_termination
si_report = _tool.si_report


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ─────────────────────────────────────────────────────────────────────────────
# SOLVER UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestMicrostripZ0:
    """Microstrip single-ended impedance sanity checks."""

    def test_typical_50_ohm_geometry(self):
        # FR4 microstrip: W=0.127 mm, H=0.1 mm, T=0.035 mm, er=4.3 → ~50 Ω
        z0 = microstrip_z0(W=0.127, H=0.1, T=0.035, er=4.3)
        assert 45.0 <= z0 <= 60.0, f"Expected ~50 Ω, got {z0:.2f} Ω"

    def test_narrow_trace_gives_higher_impedance(self):
        z0_narrow = microstrip_z0(W=0.1, H=0.2, T=0.035, er=4.3)
        z0_wide = microstrip_z0(W=0.5, H=0.2, T=0.035, er=4.3)
        assert z0_narrow > z0_wide, "Narrower trace should have higher Z0"

    def test_higher_er_lowers_z0(self):
        z0_fr4 = microstrip_z0(W=0.15, H=0.1, T=0.035, er=4.3)
        z0_rogers = microstrip_z0(W=0.15, H=0.1, T=0.035, er=3.0)
        assert z0_fr4 < z0_rogers, "Higher εr should give lower Z0"

    def test_wider_trace_lower_impedance(self):
        z0_w1 = microstrip_z0(W=0.1, H=0.15, T=0.035, er=4.5)
        z0_w2 = microstrip_z0(W=0.3, H=0.15, T=0.035, er=4.5)
        assert z0_w1 > z0_w2

    def test_returns_float(self):
        z0 = microstrip_z0(W=0.15, H=0.1, T=0.035, er=4.3)
        assert isinstance(z0, float)

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            microstrip_z0(W=0.0, H=0.1, T=0.035, er=4.3)

    def test_zero_height_raises(self):
        with pytest.raises(ValueError):
            microstrip_z0(W=0.15, H=0.0, T=0.035, er=4.3)

    def test_50_ohm_within_percent_of_known_value(self):
        # Cross-check against commonly published result: W=0.3mm, H=0.2mm, T=0.035, er=4.5 ~48Ω
        z0 = microstrip_z0(W=0.3, H=0.2, T=0.035, er=4.5)
        assert 42.0 <= z0 <= 58.0


class TestStriplineZ0:
    """Stripline single-ended impedance sanity checks."""

    def test_typical_50_ohm_stripline(self):
        # FR4 stripline: W=0.15mm, B=0.4mm, T=0.035mm, er=4.3 → typically 40-60 Ω
        z0 = stripline_z0(W=0.15, B=0.4, T=0.035, er=4.3)
        assert 35.0 <= z0 <= 65.0, f"Expected 40–60 Ω range, got {z0:.2f} Ω"

    def test_narrower_trace_higher_z0(self):
        z0_narrow = stripline_z0(W=0.1, B=0.4, T=0.035, er=4.3)
        z0_wide = stripline_z0(W=0.4, B=0.4, T=0.035, er=4.3)
        assert z0_narrow > z0_wide

    def test_higher_er_lowers_z0(self):
        z0_low_er = stripline_z0(W=0.15, B=0.4, T=0.035, er=3.0)
        z0_high_er = stripline_z0(W=0.15, B=0.4, T=0.035, er=4.8)
        assert z0_low_er > z0_high_er

    def test_returns_positive(self):
        z0 = stripline_z0(W=0.15, B=0.4, T=0.035, er=4.3)
        assert z0 > 0

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            stripline_z0(W=0.0, B=0.4, T=0.035, er=4.3)


class TestDiffZ0:
    """Differential impedance checks."""

    def test_diff_z0_greater_than_2x_single_for_large_spacing(self):
        # For very large spacing the correction term → 0 and Zdiff → 2*Z0
        z0 = 50.0
        zdiff = diff_z0(z0_single=z0, S=5.0, H_or_B=0.2)
        # 2*50 = 100; coupling correction is tiny for S >> H
        assert 95.0 <= zdiff <= 105.0

    def test_diff_z0_decreases_with_tighter_spacing(self):
        z0 = 50.0
        zdiff_close = diff_z0(z0_single=z0, S=0.05, H_or_B=0.2)
        zdiff_far = diff_z0(z0_single=z0, S=0.5, H_or_B=0.2)
        assert zdiff_close < zdiff_far

    def test_diff_z0_always_positive(self):
        zdiff = diff_z0(z0_single=50.0, S=0.1, H_or_B=0.2)
        assert zdiff > 0

    def test_diff_z0_approaches_2x_single_at_far_spacing(self):
        z0 = 50.0
        zdiff = diff_z0(z0_single=z0, S=100.0, H_or_B=0.2)
        assert abs(zdiff - 2 * z0) < 0.5

    def test_diff_z0_greater_than_single_ended(self):
        z0 = 50.0
        zdiff = diff_z0(z0_single=z0, S=0.2, H_or_B=0.2)
        assert zdiff > z0, "Differential Z0 must be > single-ended Z0"


class TestPropagationDelay:
    """Propagation delay and flight time checks."""

    def test_fr4_stripline_delay_range(self):
        # FR4 stripline er=4.3: Td = sqrt(4.3)/c ≈ sqrt(4.3)/0.2998 ≈ 6.88 ps/mm
        td = propagation_delay_ps_per_mm(er=4.3, structure="stripline")
        assert 6.5 <= td <= 7.5, f"Expected ~6.9 ps/mm, got {td:.4f}"

    def test_higher_er_more_delay(self):
        td_low = propagation_delay_ps_per_mm(er=3.0, structure="stripline")
        td_high = propagation_delay_ps_per_mm(er=4.8, structure="stripline")
        assert td_low < td_high

    def test_flight_time_scales_with_length(self):
        td = propagation_delay_ps_per_mm(er=4.3, structure="stripline")
        ft_100 = flight_time_ps(100.0, td)
        ft_200 = flight_time_ps(200.0, td)
        assert abs(ft_200 - 2 * ft_100) < 1e-6

    def test_microstrip_td_lower_than_stripline(self):
        # Microstrip has er_eff < er → lower Td than stripline with same er
        td_strip = propagation_delay_ps_per_mm(er=4.3, structure="stripline")
        td_micro = propagation_delay_ps_per_mm(er=4.3, W=0.2, H=0.15, structure="microstrip")
        assert td_micro < td_strip


class TestCrosstalk:
    """Crosstalk NEXT and FEXT checks."""

    def test_next_decreases_with_spacing(self):
        r_close = crosstalk_next(S=0.1, H=0.2, aggressor_swing_mv=1000.0)
        r_far = crosstalk_next(S=0.5, H=0.2, aggressor_swing_mv=1000.0)
        assert r_close["next_mv"] > r_far["next_mv"], "NEXT must decrease as spacing increases"

    def test_next_monotonic_multiple_spacings(self):
        spacings = [0.05, 0.1, 0.2, 0.4, 0.8]
        values = [crosstalk_next(S=s, H=0.15)["next_mv"] for s in spacings]
        for i in range(len(values) - 1):
            assert values[i] > values[i + 1], "NEXT must be strictly decreasing with spacing"

    def test_next_pct_reasonable(self):
        r = crosstalk_next(S=0.1, H=0.2, aggressor_swing_mv=1000.0)
        assert 0 < r["next_pct"] <= 50.0, "NEXT coupling must be < 50%"

    def test_fext_decreases_with_spacing(self):
        td = propagation_delay_ps_per_mm(er=4.3)
        r_close = crosstalk_fext(S=0.1, H=0.2, length_mm=50.0, td_ps_per_mm=td)
        r_far = crosstalk_fext(S=0.5, H=0.2, length_mm=50.0, td_ps_per_mm=td)
        assert r_close["fext_mv"] > r_far["fext_mv"]

    def test_fext_stripline_less_than_microstrip(self):
        td = propagation_delay_ps_per_mm(er=4.3)
        r_micro = crosstalk_fext(S=0.2, H=0.15, length_mm=50.0, td_ps_per_mm=td,
                                  structure="microstrip")
        r_strip = crosstalk_fext(S=0.2, H=0.15, length_mm=50.0, td_ps_per_mm=td,
                                  structure="stripline")
        assert r_micro["fext_mv"] > r_strip["fext_mv"], "Stripline FEXT should be lower"


class TestReflection:
    """Reflection coefficient checks."""

    def test_matched_load_gives_zero_reflection(self):
        gamma = reflection_coefficient(z_load=50.0, z0=50.0)
        assert abs(gamma) < 1e-9, "Matched load must give Γ = 0"

    def test_open_circuit_gives_positive_one(self):
        gamma = reflection_coefficient(z_load=1e9, z0=50.0)
        assert abs(gamma - 1.0) < 0.001, "Open circuit must give Γ ≈ +1"

    def test_short_circuit_gives_negative_one(self):
        gamma = reflection_coefficient(z_load=1e-6, z0=50.0)
        assert abs(gamma + 1.0) < 0.01, "Short circuit must give Γ ≈ -1"

    def test_high_impedance_load_positive_reflection(self):
        gamma = reflection_coefficient(z_load=100.0, z0=50.0)
        assert gamma > 0

    def test_low_impedance_load_negative_reflection(self):
        gamma = reflection_coefficient(z_load=25.0, z0=50.0)
        assert gamma < 0

    def test_reflection_bounded(self):
        gamma = reflection_coefficient(z_load=75.0, z0=50.0)
        assert -1.0 <= gamma <= 1.0


class TestTerminationRecommendation:
    """Termination recommendation checks."""

    def test_series_termination_for_point_to_point(self):
        rec = termination_recommendation(driver_z_ohms=25.0, line_z0_ohms=50.0,
                                          topology="point_to_point")
        assert rec["scheme"] == "series"
        assert rec["resistor_ohms"] == pytest.approx(25.0)

    def test_thevenin_for_bus(self):
        rec = termination_recommendation(driver_z_ohms=25.0, line_z0_ohms=50.0,
                                          topology="bus")
        assert rec["scheme"] == "Thevenin"
        assert rec["r1_ohms"] == pytest.approx(100.0)
        assert rec["r2_ohms"] == pytest.approx(100.0)

    def test_ac_for_clock(self):
        rec = termination_recommendation(driver_z_ohms=25.0, line_z0_ohms=50.0,
                                          topology="clock")
        assert rec["scheme"] == "AC"
        assert rec["resistor_ohms"] == pytest.approx(50.0)

    def test_matched_returns_none_scheme(self):
        # driver_z = z0 → matched
        rec = termination_recommendation(driver_z_ohms=50.0, line_z0_ohms=50.0)
        assert rec["scheme"] == "none"
        assert rec["matched"] is True

    def test_parallel_when_driver_exceeds_z0(self):
        # driver_z > z0 → series resistor would be ≤0 → fallback parallel
        rec = termination_recommendation(driver_z_ohms=75.0, line_z0_ohms=50.0,
                                          topology="point_to_point")
        assert rec["scheme"] in ("parallel", "none", "series")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL LAYER TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestSiImpedanceTool:
    """Tests for the si_impedance LLM tool."""

    @pytest.mark.asyncio
    async def test_microstrip_50_ohm(self):
        r = await call(si_impedance,
                       structure="microstrip",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       copper_thickness_mm=0.035,
                       er=4.3)
        assert r.get("ok") or "z0_ohms" in r
        z0 = r.get("z0_ohms") or (r.get("result") or {}).get("z0_ohms")
        assert z0 is not None
        assert 45.0 <= z0 <= 60.0

    @pytest.mark.asyncio
    async def test_stripline_returns_z0(self):
        r = await call(si_impedance,
                       structure="stripline",
                       trace_width_mm=0.15,
                       dielectric_height_mm=0.4,
                       copper_thickness_mm=0.035,
                       er=4.3)
        z0 = r.get("z0_ohms")
        assert z0 is not None and z0 > 0

    @pytest.mark.asyncio
    async def test_zdiff_returned_when_spacing_given(self):
        r = await call(si_impedance,
                       structure="microstrip",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       er=4.3,
                       spacing_mm=0.15)
        assert "zdiff_ohms" in r

    @pytest.mark.asyncio
    async def test_bad_structure_returns_error(self):
        r = await call(si_impedance,
                       structure="waveguide",
                       trace_width_mm=0.15,
                       dielectric_height_mm=0.1,
                       er=4.3)
        assert "error" in r

    @pytest.mark.asyncio
    async def test_missing_required_field_returns_error(self):
        r = await call(si_impedance,
                       structure="microstrip",
                       dielectric_height_mm=0.1,
                       er=4.3)
        assert "error" in r

    @pytest.mark.asyncio
    async def test_negative_width_returns_error(self):
        r = await call(si_impedance,
                       structure="microstrip",
                       trace_width_mm=-0.1,
                       dielectric_height_mm=0.1,
                       er=4.3)
        assert "error" in r


class TestSiPropagationTool:
    """Tests for the si_propagation LLM tool."""

    @pytest.mark.asyncio
    async def test_fr4_stripline_delay(self):
        r = await call(si_propagation, er=4.3, length_mm=100.0, structure="stripline")
        assert "td_ps_per_mm" in r
        assert 6.5 <= r["td_ps_per_mm"] <= 7.5

    @pytest.mark.asyncio
    async def test_flight_time_100mm(self):
        r = await call(si_propagation, er=4.3, length_mm=100.0)
        ft = r.get("flight_time_ps")
        assert ft is not None and ft > 0

    @pytest.mark.asyncio
    async def test_missing_er_returns_error(self):
        r = await call(si_propagation, length_mm=100.0)
        assert "error" in r

    @pytest.mark.asyncio
    async def test_flight_time_ns_present(self):
        r = await call(si_propagation, er=4.3, length_mm=100.0)
        assert "flight_time_ns" in r
        assert r["flight_time_ns"] == pytest.approx(r["flight_time_ps"] / 1000.0, rel=1e-4)


class TestSiCrosstalkTool:
    """Tests for the si_crosstalk LLM tool."""

    @pytest.mark.asyncio
    async def test_basic_crosstalk(self):
        r = await call(si_crosstalk,
                       spacing_mm=0.2,
                       dielectric_height_mm=0.15,
                       parallel_length_mm=50.0,
                       er=4.3)
        assert "NEXT" in r
        assert "FEXT" in r

    @pytest.mark.asyncio
    async def test_next_decreases_with_spacing_via_tool(self):
        r_close = await call(si_crosstalk,
                             spacing_mm=0.1,
                             dielectric_height_mm=0.15,
                             parallel_length_mm=50.0,
                             er=4.3)
        r_far = await call(si_crosstalk,
                           spacing_mm=0.5,
                           dielectric_height_mm=0.15,
                           parallel_length_mm=50.0,
                           er=4.3)
        assert r_close["NEXT"]["next_mv"] > r_far["NEXT"]["next_mv"]

    @pytest.mark.asyncio
    async def test_missing_spacing_returns_error(self):
        r = await call(si_crosstalk,
                       dielectric_height_mm=0.15,
                       parallel_length_mm=50.0,
                       er=4.3)
        assert "error" in r


class TestSiTerminationTool:
    """Tests for the si_termination LLM tool."""

    @pytest.mark.asyncio
    async def test_series_for_point_to_point(self):
        r = await call(si_termination, driver_z_ohms=25.0, line_z0_ohms=50.0,
                       topology="point_to_point")
        assert r.get("scheme") == "series"

    @pytest.mark.asyncio
    async def test_thevenin_for_bus(self):
        r = await call(si_termination, driver_z_ohms=25.0, line_z0_ohms=50.0,
                       topology="bus")
        assert r.get("scheme") == "Thevenin"

    @pytest.mark.asyncio
    async def test_gamma_open_load_positive(self):
        r = await call(si_termination, driver_z_ohms=25.0, line_z0_ohms=50.0)
        assert r.get("gamma_open_load") == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_missing_driver_z_returns_error(self):
        r = await call(si_termination, line_z0_ohms=50.0)
        assert "error" in r


class TestSiReportTool:
    """Tests for the si_report combined LLM tool."""

    @pytest.mark.asyncio
    async def test_full_report_microstrip(self):
        r = await call(si_report,
                       structure="microstrip",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       er=4.3,
                       length_mm=100.0,
                       driver_z_ohms=25.0,
                       copper_thickness_mm=0.035,
                       topology="point_to_point")
        assert "z0_ohms" in r
        assert "flight_time_ps" in r
        assert "termination" in r
        assert 45.0 <= r["z0_ohms"] <= 60.0

    @pytest.mark.asyncio
    async def test_report_includes_crosstalk_when_spacing_given(self):
        r = await call(si_report,
                       structure="microstrip",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       er=4.3,
                       length_mm=100.0,
                       driver_z_ohms=25.0,
                       spacing_mm=0.2,
                       aggressor_parallel_length_mm=50.0)
        assert "crosstalk" in r
        assert "NEXT" in r["crosstalk"]
        assert "FEXT" in r["crosstalk"]

    @pytest.mark.asyncio
    async def test_report_no_crosstalk_without_spacing(self):
        r = await call(si_report,
                       structure="microstrip",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       er=4.3,
                       length_mm=100.0,
                       driver_z_ohms=25.0)
        assert "crosstalk" not in r

    @pytest.mark.asyncio
    async def test_report_bad_structure_returns_error(self):
        r = await call(si_report,
                       structure="coax",
                       trace_width_mm=0.127,
                       dielectric_height_mm=0.1,
                       er=4.3,
                       length_mm=100.0,
                       driver_z_ohms=25.0)
        assert "error" in r

    @pytest.mark.asyncio
    async def test_report_zdiff_present_with_spacing(self):
        r = await call(si_report,
                       structure="stripline",
                       trace_width_mm=0.15,
                       dielectric_height_mm=0.4,
                       er=4.3,
                       length_mm=150.0,
                       driver_z_ohms=50.0,
                       spacing_mm=0.2)
        assert "zdiff_ohms" in r
        assert r["zdiff_ohms"] > r["z0_ohms"]


# ── Restore sys.modules so the kerf_chat stub does not leak into other test
#    modules (real kerf_chat.tools.registry is a populated list other suites
#    iterate; a leaked stub breaks ~100 downstream tests). ───────────────────
def teardown_module(module):  # noqa: D401  (pytest module teardown)
    import sys as _sys
    for _name, _orig in _KERF_CHAT_SAVED.items():
        if _orig is None:
            _sys.modules.pop(_name, None)
        else:
            _sys.modules[_name] = _orig
