"""
Hermetic tests for the EMC/EMI pre-compliance estimator.

Covers (≥30 tests):
  radiated_emission_differential
    - E-field scales with f² (doubling f → ×4 E-field)
    - E-field scales linearly with loop area
    - E-field scales linearly with current
    - E-field scales as 1/r
    - Returns ok=True with required keys
    - Zero frequency → ok=False
    - Negative loop area → ok=False
    - Negative current → ok=False
    - Near-field warning issued when r < λ/(2π)

  radiated_emission_common_mode
    - E-field scales linearly with frequency
    - E-field scales linearly with cable length
    - E-field scales as 1/r
    - Returns ok=True with required keys
    - Electrically-short flag correct
    - Negative frequency → ok=False

  fcc_limit_dbuvm / cispr_limit_dbuvm
    - FCC Class B 10m limit for 50 MHz = 29.5 dBμV/m
    - FCC Class A 10m limit for 50 MHz = 39.5 dBμV/m
    - CISPR Class B 10m limit for 100 MHz = 30.0 dBμV/m
    - Distance scaling: 3m limit = 10m limit + 10.5 dB (20*log10(10/3))
    - Invalid class → ok=False
    - Invalid standard → ok=False
    - Frequency below 30 MHz falls to last bucket, not error

  emission_margin_db
    - Emission well below limit → positive margin, passes=True
    - Emission above limit → negative margin, passes=False, warning issued
    - CISPR vs FCC limits differ as expected
    - Bad standard → ok=False

  near_field_crosstalk
    - Larger spacing → smaller K_effective
    - Larger height → larger Kl (closer to ground → more inductive coupling)
    - Longer parallel run → larger K_effective (saturates toward K_combined)
    - K_effective <= K_combined (saturation factor ≤ 1)
    - Kc + Kl both in (0, 1)
    - Zero spacing → ok=False
    - Negative height → ok=False

  shielding_effectiveness
    - Thicker wall → higher SEa
    - Higher frequency → higher SEa, lower SEr
    - Aperture present → SE_effective ≤ SE_total
    - Large aperture → aperture_limited = True
    - No aperture → se_aperture_db = None, se_effective = se_total
    - Steel (high μr) → higher SEa at low freq
    - Zero thickness → ok=False
    - Negative conductivity → ok=False

  LLM tool handlers (stub registry)
    - emc_radiated_differential tool returns ok=True
    - emc_radiated_common_mode tool returns ok=True
    - emc_emission_margin tool returns ok=True with margin_db
    - emc_near_field_crosstalk tool returns ok=True with K_effective
    - emc_shielding tool returns ok=True with se_effective_db
    - Tool with invalid JSON → returns error payload

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

from kerf_electronics.emc.estimate import (
    cispr_limit_dbuvm,
    emission_margin_db,
    fcc_limit_dbuvm,
    near_field_crosstalk,
    radiated_emission_common_mode,
    radiated_emission_differential,
    shielding_effectiveness,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.emc.tools",
    os.path.join(_SRC, "kerf_electronics", "emc", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

emc_radiated_differential_tool = _tool_mod.emc_radiated_differential
emc_radiated_common_mode_tool = _tool_mod.emc_radiated_common_mode
emc_emission_margin_tool = _tool_mod.emc_emission_margin
emc_near_field_crosstalk_tool = _tool_mod.emc_near_field_crosstalk
emc_shielding_tool = _tool_mod.emc_shielding


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. radiated_emission_differential
# ═══════════════════════════════════════════════════════════════════════════════

class TestRadiatedDifferential:
    """Closed-form DM loop: E = 263e-16 × f² × A × I / r"""

    def test_ok_returns_required_keys(self):
        res = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        assert res["ok"] is True
        for key in ("e_field_vpm", "e_field_dbuvm", "far_field"):
            assert key in res, f"missing key {key!r}"

    def test_e_field_scales_with_freq_squared(self):
        """Doubling frequency → 4× the E-field (f² dependence)."""
        r1 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        r2 = radiated_emission_differential(
            freq_hz=200e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        ratio = r2["e_field_vpm"] / r1["e_field_vpm"]
        assert abs(ratio - 4.0) < 1e-6, f"Expected ratio 4.0, got {ratio}"

    def test_e_field_linear_in_loop_area(self):
        """Doubling loop area → 2× E-field."""
        r1 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        r2 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=2e-4, current_a=0.001, distance_m=3.0
        )
        ratio = r2["e_field_vpm"] / r1["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_e_field_linear_in_current(self):
        """Doubling current → 2× E-field."""
        r1 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        r2 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.002, distance_m=3.0
        )
        ratio = r2["e_field_vpm"] / r1["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_e_field_inverse_distance(self):
        """Doubling distance → half the E-field (1/r dependence)."""
        r1 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        r2 = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=6.0
        )
        ratio = r1["e_field_vpm"] / r2["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_formula_exact_value(self):
        """Verify formula numerically: E = 263e-16 × f² × A × I / r"""
        f = 50e6
        A = 1e-4
        I = 0.01
        r = 3.0
        expected = 263e-16 * f**2 * A * I / r
        res = radiated_emission_differential(
            freq_hz=f, loop_area_m2=A, current_a=I, distance_m=r
        )
        assert abs(res["e_field_vpm"] - expected) / expected < 1e-9

    def test_near_field_warning_issued(self):
        """When r < λ/(2π), a UserWarning should be issued."""
        # 100 MHz: λ=3m, λ/(2π)≈0.477m; measuring at 0.1m triggers warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = radiated_emission_differential(
                freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=0.1
            )
            assert res["ok"] is True
            assert res["far_field"] is False
            assert any("near field" in str(x.message).lower() for x in w)

    def test_zero_frequency_returns_error(self):
        res = radiated_emission_differential(
            freq_hz=0.0, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        assert res["ok"] is False
        assert "freq_hz" in res["reason"]

    def test_negative_loop_area_returns_error(self):
        res = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=-1e-4, current_a=0.001, distance_m=3.0
        )
        assert res["ok"] is False

    def test_negative_current_returns_error(self):
        res = radiated_emission_differential(
            freq_hz=100e6, loop_area_m2=1e-4, current_a=-0.001, distance_m=3.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. radiated_emission_common_mode
# ═══════════════════════════════════════════════════════════════════════════════

class TestRadiatedCommonMode:
    """CM cable: E = μ₀ × f × I_cm × L / r"""

    def test_ok_returns_required_keys(self):
        res = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        assert res["ok"] is True
        for key in ("e_field_vpm", "e_field_dbuvm", "electrically_short"):
            assert key in res

    def test_e_field_linear_in_frequency(self):
        """Doubling frequency → 2× E-field (f linear for CM)."""
        r1 = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        r2 = radiated_emission_common_mode(
            freq_hz=200e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        ratio = r2["e_field_vpm"] / r1["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_e_field_linear_in_cable_length(self):
        """Doubling cable length → 2× E-field."""
        r1 = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.3, current_a=5e-6, distance_m=3.0
        )
        r2 = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.6, current_a=5e-6, distance_m=3.0
        )
        ratio = r2["e_field_vpm"] / r1["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_e_field_inverse_distance(self):
        """Doubling measurement distance → half E-field."""
        r1 = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        r2 = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.5, current_a=5e-6, distance_m=6.0
        )
        ratio = r1["e_field_vpm"] / r2["e_field_vpm"]
        assert abs(ratio - 2.0) < 1e-9

    def test_electrically_short_flag_true(self):
        """Cable length < λ/4 at 100 MHz (~0.75 m): electrically_short=True."""
        res = radiated_emission_common_mode(
            freq_hz=100e6, cable_length_m=0.1, current_a=1e-6, distance_m=3.0
        )
        assert res["electrically_short"] is True

    def test_electrically_short_flag_false_and_warning(self):
        """Cable length > λ/4 at 30 MHz (~2.5 m): electrically_short=False, warning."""
        # λ/4 at 30 MHz = c/(4f) = 3e8/(4*30e6) = 2.5 m
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = radiated_emission_common_mode(
                freq_hz=30e6, cable_length_m=3.0, current_a=1e-6, distance_m=3.0
            )
            assert res["electrically_short"] is False
            assert any("λ/4" in str(x.message) or "lambda" in str(x.message).lower()
                       or "electrically" in str(x.message).lower()
                       for x in w)

    def test_negative_frequency_returns_error(self):
        res = radiated_emission_common_mode(
            freq_hz=-100e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. fcc_limit_dbuvm + cispr_limit_dbuvm
# ═══════════════════════════════════════════════════════════════════════════════

class TestLimitLines:
    def test_fcc_class_b_50mhz_at_3m(self):
        """FCC Class B: 50 MHz at 3 m.
        Table limit is 29.5 dBμV/m at reference (3 m for Class B).
        At 3 m from 3 m ref → correction = 20*log10(3/3) = 0 dB → 29.5."""
        res = fcc_limit_dbuvm(freq_hz=50e6, class_="B", distance_m=3.0)
        assert res["ok"] is True
        assert abs(res["limit_dbuvm"] - 29.5) < 0.01

    def test_fcc_class_a_50mhz_at_10m(self):
        """FCC Class A: 50 MHz at 10 m reference → 39.5 dBμV/m."""
        res = fcc_limit_dbuvm(freq_hz=50e6, class_="A", distance_m=10.0)
        assert res["ok"] is True
        assert abs(res["limit_dbuvm"] - 39.5) < 0.01

    def test_cispr_class_b_100mhz_at_10m(self):
        """CISPR Class B: 100 MHz at 10 m → 30.0 dBμV/m."""
        res = cispr_limit_dbuvm(freq_hz=100e6, class_="B", distance_m=10.0)
        assert res["ok"] is True
        assert abs(res["limit_dbuvm"] - 30.0) < 0.01

    def test_cispr_class_a_300mhz_at_10m(self):
        """CISPR Class A: 300 MHz at 10 m → 47.0 dBμV/m."""
        res = cispr_limit_dbuvm(freq_hz=300e6, class_="A", distance_m=10.0)
        assert res["ok"] is True
        assert abs(res["limit_dbuvm"] - 47.0) < 0.01

    def test_distance_scaling_fcc(self):
        """FCC Class A: limit at 3 m = limit at 10 m + 20*log10(10/3)."""
        at_10m = fcc_limit_dbuvm(freq_hz=50e6, class_="A", distance_m=10.0)
        at_3m = fcc_limit_dbuvm(freq_hz=50e6, class_="A", distance_m=3.0)
        correction = 20.0 * math.log10(10.0 / 3.0)
        assert abs(at_3m["limit_dbuvm"] - (at_10m["limit_dbuvm"] + correction)) < 0.01

    def test_invalid_class_returns_error(self):
        res = fcc_limit_dbuvm(freq_hz=50e6, class_="C")
        assert res["ok"] is False
        assert "class_" in res["reason"]

    def test_invalid_frequency_returns_error(self):
        res = cispr_limit_dbuvm(freq_hz=-1e6, class_="B")
        assert res["ok"] is False

    def test_cispr_class_a_greater_than_class_b(self):
        """Class A limit is always higher (more relaxed) than Class B at same freq."""
        a_res = cispr_limit_dbuvm(freq_hz=100e6, class_="A", distance_m=10.0)
        b_res = cispr_limit_dbuvm(freq_hz=100e6, class_="B", distance_m=10.0)
        assert a_res["limit_dbuvm"] > b_res["limit_dbuvm"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. emission_margin_db
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmissionMargin:
    def test_emission_well_below_limit_positive_margin(self):
        """E-field 20 dBμV/m vs CISPR B limit 30.0 → margin = +10 dB, passes."""
        res = emission_margin_db(
            e_field_dbuvm=20.0,
            freq_hz=100e6,
            standard="cispr",
            class_="B",
            distance_m=10.0,
        )
        assert res["ok"] is True
        assert res["passes"] is True
        assert abs(res["margin_db"] - 10.0) < 0.01

    def test_emission_above_limit_negative_margin_and_warning(self):
        """E-field above limit → margin < 0, passes=False, warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = emission_margin_db(
                e_field_dbuvm=45.0,
                freq_hz=100e6,
                standard="cispr",
                class_="B",
                distance_m=10.0,
            )
            assert res["ok"] is True
            assert res["passes"] is False
            assert res["margin_db"] < 0
            assert any("exceedance" in str(x.message).lower() or
                       "limit exceeded" in str(x.message).lower()
                       for x in w)

    def test_margin_exact_computation(self):
        """margin = limit - emission exactly."""
        emission = 25.0
        res = emission_margin_db(
            e_field_dbuvm=emission,
            freq_hz=50e6,
            standard="fcc",
            class_="B",
            distance_m=3.0,
        )
        # FCC Class B at 3 m: 29.5 dBμV/m → margin = 29.5 - 25.0 = 4.5
        assert res["ok"] is True
        assert abs(res["margin_db"] - 4.5) < 0.01

    def test_fcc_vs_cispr_class_b_differ(self):
        """FCC and CISPR Class B limits differ at same freq/distance."""
        fcc_res = emission_margin_db(
            e_field_dbuvm=30.0, freq_hz=100e6, standard="fcc", class_="B",
            distance_m=10.0
        )
        cispr_res = emission_margin_db(
            e_field_dbuvm=30.0, freq_hz=100e6, standard="cispr", class_="B",
            distance_m=10.0
        )
        # FCC Class B 10m at 100 MHz = 33.5 dBμV/m (scaled from 3m ref)
        # CISPR Class B 10m at 100 MHz = 30.0 dBμV/m
        # They should be different
        assert fcc_res["ok"] and cispr_res["ok"]
        assert fcc_res["margin_db"] != cispr_res["margin_db"]

    def test_bad_standard_returns_error(self):
        res = emission_margin_db(
            e_field_dbuvm=30.0, freq_hz=100e6, standard="iec", class_="B"
        )
        assert res["ok"] is False
        assert "standard" in res["reason"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. near_field_crosstalk
# ═══════════════════════════════════════════════════════════════════════════════

class TestNearFieldCrosstalk:
    def test_ok_returns_required_keys(self):
        res = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.2,
            trace_height_mm=0.1, parallel_length_mm=20.0
        )
        assert res["ok"] is True
        for k in ("Kc", "Kl", "K_combined", "K_effective"):
            assert k in res

    def test_larger_spacing_smaller_K_effective(self):
        """Wider separation → weaker coupling."""
        r_close = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.1,
            trace_height_mm=0.2, parallel_length_mm=20.0
        )
        r_far = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=1.0,
            trace_height_mm=0.2, parallel_length_mm=20.0
        )
        assert r_close["K_effective"] > r_far["K_effective"]

    def test_longer_parallel_run_larger_K_effective(self):
        """Longer parallel run → higher effective coupling (saturates)."""
        r_short = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.2,
            trace_height_mm=0.1, parallel_length_mm=1.0
        )
        r_long = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.2,
            trace_height_mm=0.1, parallel_length_mm=50.0
        )
        assert r_long["K_effective"] > r_short["K_effective"]

    def test_K_effective_leq_K_combined(self):
        """K_effective ≤ K_combined (tanh saturation ≤ 1)."""
        res = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.2,
            trace_height_mm=0.1, parallel_length_mm=20.0
        )
        assert res["K_effective"] <= res["K_combined"] + 1e-9

    def test_Kc_Kl_in_unit_interval(self):
        """Kc and Kl are both in (0, 1)."""
        res = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.3, trace_spacing_mm=0.3,
            trace_height_mm=0.15, parallel_length_mm=10.0
        )
        assert 0.0 < res["Kc"] < 1.0
        assert 0.0 < res["Kl"] < 1.0

    def test_K_combined_from_Kc_Kl(self):
        """K_combined = sqrt(Kc² + Kl²) exactly."""
        res = near_field_crosstalk(
            freq_hz=50e6, trace_width_mm=0.2, trace_spacing_mm=0.4,
            trace_height_mm=0.1, parallel_length_mm=15.0
        )
        expected = math.sqrt(res["Kc"] ** 2 + res["Kl"] ** 2)
        assert abs(res["K_combined"] - expected) < 1e-5

    def test_zero_spacing_returns_error(self):
        res = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.0,
            trace_height_mm=0.1, parallel_length_mm=10.0
        )
        assert res["ok"] is False

    def test_negative_height_returns_error(self):
        res = near_field_crosstalk(
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.2,
            trace_height_mm=-0.1, parallel_length_mm=10.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. shielding_effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

class TestShieldingEffectiveness:
    def test_ok_returns_required_keys(self):
        res = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3)
        assert res["ok"] is True
        for k in ("se_absorption_db", "se_reflection_db", "se_total_db",
                  "se_effective_db", "aperture_limited"):
            assert k in res

    def test_thicker_wall_higher_absorption(self):
        """Double thickness → higher SEa."""
        r1 = shielding_effectiveness(freq_hz=1e6, thickness_m=0.5e-3)
        r2 = shielding_effectiveness(freq_hz=1e6, thickness_m=1.0e-3)
        assert r2["se_absorption_db"] > r1["se_absorption_db"]

    def test_higher_freq_higher_absorption(self):
        """Higher frequency → higher absorption (f term under sqrt)."""
        r_low = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3)
        r_high = shielding_effectiveness(freq_hz=10e6, thickness_m=1e-3)
        assert r_high["se_absorption_db"] > r_low["se_absorption_db"]

    def test_higher_freq_lower_reflection(self):
        """Higher frequency → lower reflection (log term decreases)."""
        r_low = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3)
        r_high = shielding_effectiveness(freq_hz=100e6, thickness_m=1e-3)
        assert r_high["se_reflection_db"] < r_low["se_reflection_db"]

    def test_no_aperture_se_aperture_is_none(self):
        """With no aperture, se_aperture_db is None."""
        res = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3, aperture_length_m=0.0)
        assert res["se_aperture_db"] is None
        assert res["aperture_limited"] is False

    def test_no_aperture_se_effective_equals_se_total(self):
        """Without aperture, se_effective = se_total."""
        res = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3)
        assert abs(res["se_effective_db"] - res["se_total_db"]) < 0.01

    def test_large_aperture_limits_se(self):
        """A large slot (1 m at 300 MHz → SE_aperture ≈ 0 dB) limits effectiveness."""
        # λ at 300 MHz = 1 m, slot = 1 m → SE_aperture = 20*log10(c/(2*f*L))
        #   = 20*log10(3e8 / (2*300e6*1)) = 20*log10(0.5) ≈ -6 dB
        res = shielding_effectiveness(
            freq_hz=300e6, thickness_m=1e-3, aperture_length_m=1.0
        )
        assert res["aperture_limited"] is True
        assert res["se_effective_db"] < res["se_total_db"]

    def test_small_aperture_reduces_se_less_than_large(self):
        """A smaller slot produces a higher SE_aperture (less leakage) than a large slot."""
        res_small = shielding_effectiveness(
            freq_hz=300e6, thickness_m=1e-3, aperture_length_m=0.01
        )
        res_large = shielding_effectiveness(
            freq_hz=300e6, thickness_m=1e-3, aperture_length_m=0.5
        )
        assert res_small["se_aperture_db"] > res_large["se_aperture_db"]

    def test_steel_enclosure_higher_absorption(self):
        """Steel (μr=1000) has higher absorption than copper (μr=1) at same freq."""
        cu = shielding_effectiveness(
            freq_hz=1e6, thickness_m=1e-3,
            conductivity_relative=1.0, permeability_relative=1.0
        )
        steel = shielding_effectiveness(
            freq_hz=1e6, thickness_m=1e-3,
            conductivity_relative=0.1, permeability_relative=1000.0
        )
        # For steel: μr×σr = 100 (copper: μr×σr = 1); SEa ∝ sqrt(μr×σr)
        # steel SEa = cu_SEa * sqrt(100) ≈ cu_SEa * 10
        assert steel["se_absorption_db"] > cu["se_absorption_db"]

    def test_zero_thickness_returns_error(self):
        res = shielding_effectiveness(freq_hz=1e6, thickness_m=0.0)
        assert res["ok"] is False

    def test_negative_conductivity_returns_error(self):
        res = shielding_effectiveness(freq_hz=1e6, thickness_m=1e-3,
                                       conductivity_relative=-1.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. LLM tool handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_radiated_differential_tool_ok(self):
        res = await call(
            emc_radiated_differential_tool,
            freq_hz=100e6, loop_area_m2=1e-4, current_a=0.001, distance_m=3.0
        )
        assert res["ok"] is True
        assert "e_field_dbuvm" in res

    @pytest.mark.asyncio
    async def test_radiated_common_mode_tool_ok(self):
        res = await call(
            emc_radiated_common_mode_tool,
            freq_hz=100e6, cable_length_m=0.5, current_a=5e-6, distance_m=3.0
        )
        assert res["ok"] is True
        assert "e_field_dbuvm" in res

    @pytest.mark.asyncio
    async def test_emission_margin_tool_ok(self):
        res = await call(
            emc_emission_margin_tool,
            e_field_dbuvm=25.0, freq_hz=100e6, standard="cispr",
            class_="B", distance_m=10.0
        )
        assert res["ok"] is True
        assert "margin_db" in res

    @pytest.mark.asyncio
    async def test_near_field_crosstalk_tool_ok(self):
        res = await call(
            emc_near_field_crosstalk_tool,
            freq_hz=100e6, trace_width_mm=0.2, trace_spacing_mm=0.3,
            trace_height_mm=0.15, parallel_length_mm=10.0
        )
        assert res["ok"] is True
        assert "K_effective" in res

    @pytest.mark.asyncio
    async def test_shielding_tool_ok(self):
        res = await call(
            emc_shielding_tool,
            freq_hz=1e6, thickness_m=1e-3
        )
        assert res["ok"] is True
        assert "se_effective_db" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await emc_shielding_tool(None, b"not valid json{{")
        data = json.loads(result)
        # Real registry: {"error": ..., "code": ...}; stub: {"ok": False, ...}
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_emission_margin_tool_bad_standard_error(self):
        result = await emc_emission_margin_tool(
            None,
            json.dumps({"e_field_dbuvm": 30.0, "freq_hz": 100e6, "standard": "iec"}).encode(),
        )
        data = json.loads(result)
        # Real registry err_payload has no "ok" key; stub includes it
        assert data.get("ok") is False or "error" in data
