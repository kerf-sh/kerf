# Author: imranparuk
"""
Tests for flex_stackup.py — flex / rigid-flex stackup manager.

Loading strategy mirrors test_diffpair.py: load the module directly via
importlib to avoid pulling in the full kerf_chat stack.

IPC-2223 rules verified:
  static single-sided: r_min ≥ 6 × t
  static double-sided: r_min ≥ 12 × t
  dynamic:             r_min ≥ 100 × t

Outer-fibre strain:   ε = t / (2r)
  static limit:  0.3 %
  dynamic limit: 0.1 %
"""

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

# ── Stub kerf_chat.tools.registry ─────────────────────────────────────────────

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})  # real Registry is a list subclass; keep leaked stub import-compatible
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps({"ok": False, "error": msg, "code": code})
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
_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.tools.flex_stackup",
    "packages/kerf-electronics/src/kerf_electronics/tools/flex_stackup.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Public tool functions
flex_stackup_define = _mod.flex_stackup_define
flex_bend_check = _mod.flex_bend_check
flex_neutral_axis = _mod.flex_neutral_axis
flex_fab_summary = _mod.flex_fab_summary

# Internal helpers (white-box tests)
_parse_layers = _mod._parse_layers
_copper_count = _mod._copper_count
_thickness_zone = _mod._thickness_zone
_bend_multiplier = _mod._bend_multiplier
_neutral_axis_offset = _mod._neutral_axis_offset
_STATIC_SINGLE_MULTIPLIER = _mod._STATIC_SINGLE_MULTIPLIER
_STATIC_DOUBLE_MULTIPLIER = _mod._STATIC_DOUBLE_MULTIPLIER
_DYNAMIC_MULTIPLIER = _mod._DYNAMIC_MULTIPLIER
_STRAIN_LIMIT_STATIC = _mod._STRAIN_LIMIT_STATIC
_STRAIN_LIMIT_DYNAMIC = _mod._STRAIN_LIMIT_DYNAMIC


# ── Async helper ──────────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── Fixture layer lists ───────────────────────────────────────────────────────

def _simple_flex_layers():
    """Single-sided flex: PI core + one copper layer + coverlay."""
    return [
        {"type": "coverlay", "thickness_mm": 0.025, "name": "top_coverlay", "zone": "flex"},
        {"type": "copper",   "thickness_mm": 0.035, "name": "top_cu",       "zone": "flex"},
        {"type": "adhesive", "thickness_mm": 0.025, "name": "adhesive",     "zone": "flex"},
        {"type": "PI",       "thickness_mm": 0.050, "name": "PI_core",      "er": 3.4, "zone": "flex"},
        {"type": "adhesive", "thickness_mm": 0.025, "name": "adhesive_bot", "zone": "flex"},
        {"type": "coverlay", "thickness_mm": 0.025, "name": "bot_coverlay", "zone": "flex"},
    ]


def _double_sided_flex_layers():
    """Double-sided flex: PI core + two copper layers + coverlay both sides."""
    return [
        {"type": "coverlay", "thickness_mm": 0.025, "name": "top_coverlay", "zone": "flex"},
        {"type": "copper",   "thickness_mm": 0.035, "name": "top_cu",       "zone": "flex"},
        {"type": "adhesive", "thickness_mm": 0.025, "name": "adhesive",     "zone": "flex"},
        {"type": "PI",       "thickness_mm": 0.050, "name": "PI_core",      "er": 3.4, "zone": "flex"},
        {"type": "adhesive", "thickness_mm": 0.025, "name": "adhesive_bot", "zone": "flex"},
        {"type": "copper",   "thickness_mm": 0.035, "name": "bot_cu",       "zone": "flex"},
        {"type": "coverlay", "thickness_mm": 0.025, "name": "bot_coverlay", "zone": "flex"},
    ]


def _rigid_flex_layers():
    """4-layer rigid-flex: two rigid zones flanking a flex zone."""
    return [
        {"type": "stiffener", "thickness_mm": 0.200, "name": "top_FR4",      "zone": "rigid"},
        {"type": "copper",    "thickness_mm": 0.035, "name": "L1_cu",        "zone": "rigid"},
        {"type": "adhesive",  "thickness_mm": 0.025, "name": "bond_ply",     "zone": "rigid"},
        {"type": "coverlay",  "thickness_mm": 0.025, "name": "top_coverlay", "zone": "flex"},
        {"type": "copper",    "thickness_mm": 0.035, "name": "L2_cu",        "zone": "flex"},
        {"type": "PI",        "thickness_mm": 0.050, "name": "PI_core",      "er": 3.4, "zone": "flex"},
        {"type": "copper",    "thickness_mm": 0.035, "name": "L3_cu",        "zone": "flex"},
        {"type": "coverlay",  "thickness_mm": 0.025, "name": "bot_coverlay", "zone": "flex"},
        {"type": "adhesive",  "thickness_mm": 0.025, "name": "bond_ply_bot", "zone": "rigid"},
        {"type": "copper",    "thickness_mm": 0.035, "name": "L4_cu",        "zone": "rigid"},
        {"type": "stiffener", "thickness_mm": 0.200, "name": "bot_FR4",      "zone": "rigid"},
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helper unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseLayersInternal:
    def test_valid_simple_flex(self):
        ok, msg, layers = _parse_layers(_simple_flex_layers())
        assert ok is True
        assert len(layers) == 6

    def test_invalid_type_rejected(self):
        bad = [{"type": "fiberglass", "thickness_mm": 0.1}]
        ok, msg, _ = _parse_layers(bad)
        assert ok is False
        assert "fiberglass" in msg

    def test_non_positive_thickness_rejected(self):
        bad = [{"type": "copper", "thickness_mm": 0}]
        ok, msg, _ = _parse_layers(bad)
        assert ok is False
        assert "thickness" in msg.lower()

    def test_invalid_zone_rejected(self):
        bad = [{"type": "copper", "thickness_mm": 0.035, "zone": "semiflex"}]
        ok, msg, _ = _parse_layers(bad)
        assert ok is False

    def test_empty_list_rejected(self):
        ok, msg, _ = _parse_layers([])
        assert ok is False


class TestCopperCount:
    def test_simple_flex_has_one_copper(self):
        _, _, layers = _parse_layers(_simple_flex_layers())
        assert _copper_count(layers) == 1

    def test_double_sided_has_two_copper(self):
        _, _, layers = _parse_layers(_double_sided_flex_layers())
        assert _copper_count(layers) == 2

    def test_rigid_flex_total_copper(self):
        _, _, layers = _parse_layers(_rigid_flex_layers())
        assert _copper_count(layers) == 4


class TestThicknessZone:
    def test_simple_flex_total_thickness(self):
        _, _, layers = _parse_layers(_simple_flex_layers())
        t = _thickness_zone(layers, "flex")
        expected = 0.025 + 0.035 + 0.025 + 0.050 + 0.025 + 0.025
        assert abs(t - expected) < 1e-9

    def test_rigid_flex_flex_thickness(self):
        _, _, layers = _parse_layers(_rigid_flex_layers())
        t = _thickness_zone(layers, "flex")
        expected = 0.025 + 0.035 + 0.050 + 0.035 + 0.025
        assert abs(t - expected) < 1e-9


class TestBendMultiplier:
    def test_static_single_multiplier(self):
        assert _bend_multiplier("single_sided", 1) == _STATIC_SINGLE_MULTIPLIER
        assert _STATIC_SINGLE_MULTIPLIER == 6

    def test_static_double_multiplier(self):
        assert _bend_multiplier("double_sided", 2) == _STATIC_DOUBLE_MULTIPLIER
        assert _STATIC_DOUBLE_MULTIPLIER == 12

    def test_dynamic_multiplier(self):
        assert _bend_multiplier("dynamic", 1) == _DYNAMIC_MULTIPLIER
        assert _DYNAMIC_MULTIPLIER == 100

    def test_double_sided_stricter_than_single(self):
        assert _bend_multiplier("double_sided", 2) > _bend_multiplier("single_sided", 1)

    def test_dynamic_stricter_than_double(self):
        assert _bend_multiplier("dynamic", 2) > _bend_multiplier("double_sided", 2)

    def test_two_flex_copper_layers_promotes_to_double(self):
        # Even if flex_type says single_sided, 2 copper layers → double multiplier
        assert _bend_multiplier("single_sided", 2) == _STATIC_DOUBLE_MULTIPLIER


class TestNeutralAxisOffset:
    def test_symmetric_stack_midpoint(self):
        """For uniform or symmetric stack, NA should be at t/2."""
        layers = [
            {"type": "PI",     "thickness_mm": 0.05, "zone": "flex"},
        ]
        t = 0.05
        na = _neutral_axis_offset(layers, t)
        assert abs(na - t / 2.0) < 1e-9

    def test_none_layers_returns_midpoint(self):
        t = 0.1
        na = _neutral_axis_offset(None, t)
        assert abs(na - t / 2.0) < 1e-9

    def test_two_equal_layers_midpoint(self):
        layers = [
            {"type": "copper", "thickness_mm": 0.035, "zone": "flex"},
            {"type": "PI",     "thickness_mm": 0.035, "zone": "flex"},
        ]
        t = 0.070
        na = _neutral_axis_offset(layers, t)
        assert abs(na - t / 2.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════════
# flex_stackup_define tool tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlexStackupDefine:
    async def test_total_thickness_sum(self):
        r = await call(flex_stackup_define, layers=_simple_flex_layers())
        assert r["ok"] is True
        expected = 0.025 + 0.035 + 0.025 + 0.050 + 0.025 + 0.025
        assert abs(r["total_thickness_mm"] - expected) < 1e-6

    async def test_copper_count_single(self):
        r = await call(flex_stackup_define, layers=_simple_flex_layers())
        assert r["copper_count"] == 1

    async def test_copper_count_double(self):
        r = await call(flex_stackup_define, layers=_double_sided_flex_layers())
        assert r["copper_count"] == 2

    async def test_flex_thickness_rigid_flex(self):
        r = await call(flex_stackup_define, layers=_rigid_flex_layers())
        expected_flex = 0.025 + 0.035 + 0.050 + 0.035 + 0.025
        assert abs(r["flex_thickness_mm"] - expected_flex) < 1e-6

    async def test_is_rigid_flex_flag(self):
        r = await call(flex_stackup_define, layers=_rigid_flex_layers())
        assert r["is_rigid_flex"] is True

    async def test_pure_flex_not_rigid_flex(self):
        r = await call(flex_stackup_define, layers=_simple_flex_layers())
        assert r["is_rigid_flex"] is False

    async def test_no_copper_returns_error(self):
        no_cu = [{"type": "PI", "thickness_mm": 0.05}]
        r = await call(flex_stackup_define, layers=no_cu)
        assert r.get("ok") is not True
        assert "copper" in r.get("error", "").lower()

    async def test_stackup_name_passed_through(self):
        r = await call(
            flex_stackup_define,
            layers=_simple_flex_layers(),
            stackup_name="MY_FLEX",
        )
        assert r["stackup_name"] == "MY_FLEX"

    async def test_layer_count(self):
        r = await call(flex_stackup_define, layers=_rigid_flex_layers())
        assert r["layer_count"] == len(_rigid_flex_layers())

    async def test_invalid_json_returns_error(self):
        result = await flex_stackup_define(None, b"not-json")
        data = json.loads(result)
        assert data.get("ok") is not True


# ═══════════════════════════════════════════════════════════════════════════════
# flex_bend_check tool tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlexBendCheck:
    async def test_static_single_pass_at_10t(self):
        """At r = 10t, single-sided static bend: 10 ≥ 6 → PASS."""
        t = 0.185
        r = 10 * t
        result = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert result["ok"] is True
        assert result["passed"] is True

    async def test_static_single_fail_too_tight(self):
        """At r = 3t, single-sided static bend: 3 < 6 → FAIL."""
        t = 0.185
        r = 3 * t
        result = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert result["passed"] is False

    async def test_static_double_pass_at_15t(self):
        """At r = 15t, double-sided: 15 ≥ 12 → PASS."""
        t = 0.185
        r = 15 * t
        result = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="double_sided",
        )
        assert result["passed"] is True

    async def test_static_double_fail_at_8t(self):
        """At r = 8t, double-sided: 8 < 12 → FAIL."""
        t = 0.185
        r = 8 * t
        result = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="double_sided",
        )
        assert result["passed"] is False

    async def test_dynamic_stricter_than_static(self):
        """Verify dynamic requires larger radius than static for same t."""
        t = 0.185
        r_static = 15 * t   # passes double-sided
        result_dyn = await call(
            flex_bend_check,
            inner_radius_mm=r_static,
            flex_thickness_mm=t,
            flex_type="dynamic",
        )
        assert result_dyn["passed"] is False

    async def test_dynamic_pass_at_110t(self):
        t = 0.1
        r = 110 * t
        result = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="dynamic",
        )
        assert result["passed"] is True

    async def test_recommended_min_radius_formula_single(self):
        t = 0.2
        result = await call(
            flex_bend_check,
            inner_radius_mm=5.0,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert abs(result["recommended_min_radius_mm"] - 6 * t) < 1e-6

    async def test_recommended_min_radius_formula_double(self):
        t = 0.2
        result = await call(
            flex_bend_check,
            inner_radius_mm=5.0,
            flex_thickness_mm=t,
            flex_type="double_sided",
        )
        assert abs(result["recommended_min_radius_mm"] - 12 * t) < 1e-6

    async def test_double_sided_stricter_than_single_same_t(self):
        t = 0.185
        r = 8 * t  # passes single (≥6t) but fails double (needs ≥12t)
        r_single = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        r_double = await call(
            flex_bend_check,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="double_sided",
        )
        assert r_single["passed"] is True
        assert r_double["passed"] is False

    async def test_invalid_radius_returns_error(self):
        result = await call(
            flex_bend_check,
            inner_radius_mm=-1.0,
            flex_thickness_mm=0.2,
            flex_type="single_sided",
        )
        assert result.get("ok") is not True

    async def test_invalid_flex_type_returns_error(self):
        result = await call(
            flex_bend_check,
            inner_radius_mm=1.0,
            flex_thickness_mm=0.2,
            flex_type="extreme_dynamic",
        )
        assert result.get("ok") is not True


# ═══════════════════════════════════════════════════════════════════════════════
# flex_neutral_axis tool tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlexNeutralAxis:
    async def test_outer_fibre_strain_formula(self):
        """ε = t / (2r)  — verify against formula directly."""
        t = 0.2
        r = 5.0
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert result["ok"] is True
        expected_strain = t / (2 * r)
        assert abs(result["outer_fibre_strain"] - expected_strain) < 1e-9

    async def test_strain_percentage_conversion(self):
        t = 0.2
        r = 5.0
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert abs(result["outer_fibre_strain_pct"] - result["outer_fibre_strain"] * 100) < 1e-6

    async def test_static_warn_if_strain_exceeds_limit(self):
        """Strain > 0.3% for static should trigger a warning."""
        t = 0.2
        # ε = t/(2r) > 0.003 → r < t/0.006 = 33.3 mm
        r = 10.0  # ε = 0.2/20 = 0.01 = 1% → exceeds 0.3%
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert result["within_strain_limit"] is False
        assert len(result["warnings"]) > 0

    async def test_static_no_warn_within_limit(self):
        """Strain ≤ 0.3% for static should NOT trigger a warning."""
        t = 0.1
        r = 20.0  # ε = 0.1/40 = 0.0025 = 0.25% ≤ 0.3%
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="single_sided",
        )
        assert result["within_strain_limit"] is True
        assert len(result["warnings"]) == 0

    async def test_dynamic_stricter_strain_limit(self):
        """At the same geometry, dynamic limit (0.1%) is harder to satisfy."""
        t = 0.1
        r = 20.0  # ε = 0.0025 = 0.25% > 0.1% (dynamic limit)
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=r,
            flex_thickness_mm=t,
            flex_type="dynamic",
        )
        assert result["within_strain_limit"] is False

    async def test_neutral_axis_midpoint_symmetric(self):
        """For a symmetric stack the NA should be at t/2."""
        layers = [
            {"type": "copper", "thickness_mm": 0.035, "zone": "flex"},
            {"type": "PI",     "thickness_mm": 0.035, "zone": "flex"},
        ]
        t = 0.070
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=2.0,
            flex_thickness_mm=t,
            flex_type="single_sided",
            layers=layers,
        )
        assert abs(result["neutral_axis_offset_from_inner_mm"] - t / 2.0) < 1e-6

    async def test_invalid_radius_returns_error(self):
        result = await call(
            flex_neutral_axis,
            inner_radius_mm=0,
            flex_thickness_mm=0.2,
            flex_type="single_sided",
        )
        assert result.get("ok") is not True


# ═══════════════════════════════════════════════════════════════════════════════
# flex_fab_summary tool tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlexFabSummary:
    async def test_basic_returns_ok(self):
        r = await call(flex_fab_summary, layers=_simple_flex_layers())
        assert r["ok"] is True

    async def test_coverlay_detected(self):
        r = await call(flex_fab_summary, layers=_simple_flex_layers())
        assert r["coverlay_flex"] is True

    async def test_no_coverlay_generates_warning(self):
        no_cov = [
            {"type": "copper", "thickness_mm": 0.035, "zone": "flex"},
            {"type": "PI",     "thickness_mm": 0.050, "zone": "flex"},
        ]
        r = await call(flex_fab_summary, layers=no_cov)
        assert any("coverlay" in w.lower() for w in r["warnings"])

    async def test_stiffener_detected(self):
        r = await call(flex_fab_summary, layers=_rigid_flex_layers())
        assert r["stiffener_present"] is True

    async def test_all_bends_pass_true(self):
        bend_results = [
            {
                "passed": True,
                "inner_radius_mm": 2.0,
                "flex_type": "single_sided",
                "recommended_min_radius_mm": 1.11,
                "message": "PASS",
            }
        ]
        r = await call(
            flex_fab_summary,
            layers=_simple_flex_layers(),
            bend_results=bend_results,
        )
        assert r["all_bends_pass"] is True

    async def test_all_bends_pass_false_with_failing_bend(self):
        bend_results = [
            {
                "passed": False,
                "inner_radius_mm": 0.5,
                "flex_type": "single_sided",
                "recommended_min_radius_mm": 1.11,
                "message": "FAIL",
            }
        ]
        r = await call(
            flex_fab_summary,
            layers=_simple_flex_layers(),
            bend_results=bend_results,
        )
        assert r["all_bends_pass"] is False
        assert any("FAIL" in w.upper() or "fail" in w.lower() for w in r["warnings"])

    async def test_no_copper_returns_error(self):
        no_cu = [{"type": "PI", "thickness_mm": 0.05}]
        r = await call(flex_fab_summary, layers=no_cu)
        assert r.get("ok") is not True

    async def test_controlled_impedance_feasible_when_er_set(self):
        r = await call(flex_fab_summary, layers=_double_sided_flex_layers())
        assert r["controlled_impedance"] == "feasible"

    async def test_rigid_flex_flag(self):
        r = await call(flex_fab_summary, layers=_rigid_flex_layers())
        assert r["is_rigid_flex"] is True

    async def test_total_thickness_reported(self):
        r = await call(flex_fab_summary, layers=_simple_flex_layers())
        expected = sum(la["thickness_mm"] for la in _simple_flex_layers())
        assert abs(r["total_thickness_mm"] - expected) < 1e-6


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
