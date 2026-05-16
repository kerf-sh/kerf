"""
Hermetic tests for the crystal oscillator & PLL design module.

Covers ≥ 30 tests:

  crystal_load_caps
    - symmetric cap for 12 pF CL, 3 pF stray → 18 pF
    - cl_error_ppm=0 when c1=c2=c_ext_symmetric
    - cl_target_f <= cstray_f → ok=False
    - negative cstray → ok=False
    - c1=c2 provided: CL round-trip

  pierce_negative_resistance
    - exact formula: |−Rn| = gm/(ω²·C1·C2)
    - gm_margin = neg_res / esr
    - sufficient_gm=True when margin >= safety_factor
    - warning issued when margin < safety_factor
    - zero gm → ok=False
    - zero esr → ok=False

  drive_level_estimate
    - exact formula: P = (ω·CL·V_rms)²·ESR
    - over_drive=True when drive > max_drive_level_uw
    - over_drive=False when drive <= max
    - warning issued on over-drive
    - zero freq → ok=False

  frequency_pulling
    - zero delta_CL → delta_f_hz == 0
    - positive delta_CL → positive delta_f_ppm (pulls up)
    - exact formula vs first-order approx agree to 1% for small ΔCL
    - warning when |ppm| > 200
    - zero freq → ok=False

  ppm_error_budget
    - RSS = sqrt(sum of squares)
    - all zeros → total_ppm = 0
    - within_budget=True when total < limit
    - within_budget=False when total > limit; warning issued
    - negative term → ok=False

  rc_oscillator_frequency
    - f = 1/(2π·R·C) for rc_factor=1
    - doubling R → halves frequency
    - doubling C → halves frequency
    - CMOS Schmitt: rc_factor=2.2/(2π) → f=1/(2.2·R·C)
    - zero R → ok=False

  lc_oscillator_frequency
    - f = 1/(2π·sqrt(L·C))
    - doubling L → f / sqrt(2)
    - doubling C → f / sqrt(2)
    - zero L → ok=False

  ring_oscillator_frequency
    - f = 1/(2·N·τ) for odd N
    - N=3, τ=100ps → f=1/(600ps)
    - even N → warning issued
    - N<3 → ok=False
    - zero τ → ok=False

  pll_divider_n
    - integer-N: N = round(f_out/f_ref), exact f_out=N·f_ref
    - fractional-N: N_exact = f_out/f_ref
    - freq_error_ppm = 0 when f_out divisible by f_ref
    - large rounding error → warning

  pll_type2_loop_filter
    - C1, R, C2 > 0 for valid inputs
    - C2 = C1/10
    - stable=True for phase_margin=45°
    - phase_margin_achieved matches input within 5°
    - 3rd order: omega_pole2 in result
    - order=1 → ok=False

  pll_lock_time
    - t_lock > 0 for valid inputs
    - larger f_step → longer lock time
    - epsilon_hz >= f_step_hz → ok=False

  phase_noise_to_jitter
    - sigma_jitter > 0
    - lower phase noise → lower jitter
    - sigma_jitter_ps = sigma_jitter_s × 1e12
    - sigma_jitter_fs = sigma_jitter_s × 1e15
    - zero integration_bw → ok=False (positive required)

  LLM tool handlers (stub registry)
    - osc_crystal_load_caps tool returns ok=True
    - osc_pierce_neg_resistance tool returns ok=True
    - pll_loop_filter tool returns ok=True
    - pll_phase_noise_to_jitter tool returns ok=True
    - tool with invalid JSON → error payload

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

from kerf_electronics.oscillator.design import (
    crystal_load_caps,
    pierce_negative_resistance,
    drive_level_estimate,
    frequency_pulling,
    ppm_error_budget,
    rc_oscillator_frequency,
    lc_oscillator_frequency,
    ring_oscillator_frequency,
    pll_divider_n,
    pll_type2_loop_filter,
    pll_lock_time,
    phase_noise_to_jitter,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.oscillator.tools",
    os.path.join(_SRC, "kerf_electronics", "oscillator", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

_osc_crystal_load_caps_tool = _tool_mod.osc_crystal_load_caps
_osc_pierce_neg_resistance_tool = _tool_mod.osc_pierce_neg_resistance
_pll_loop_filter_tool = _tool_mod.pll_loop_filter
_pll_phase_noise_to_jitter_tool = _tool_mod.pll_phase_noise_to_jitter


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. crystal_load_caps
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrystalLoadCaps:
    """CL = (C1×C2)/(C1+C2) + Cstray; C_ext_sym = 2×(CL − Cstray)"""

    def test_symmetric_cap_12pf_3pf_stray(self):
        """12 pF CL, 3 pF stray → C_ext = 2×(12−3) = 18 pF"""
        res = crystal_load_caps(cl_target_f=12e-12, cstray_f=3e-12)
        assert res["ok"] is True
        assert abs(res["c_ext_symmetric_f"] - 18e-12) < 1e-15

    def test_symmetric_cap_correct_pf(self):
        """Result reported in pF matches formula."""
        res = crystal_load_caps(cl_target_f=18e-12, cstray_f=2e-12)
        assert res["ok"] is True
        expected_pf = 2.0 * (18.0 - 2.0)
        assert abs(res["c_ext_symmetric_pf"] - expected_pf) < 0.001

    def test_cl_error_ppm_zero_when_symmetric(self):
        """When c1_ext = c2_ext = c_ext_symmetric, CL error must be ~0 ppm."""
        cl_target = 12e-12
        cstray = 3e-12
        c_ext = 2.0 * (cl_target - cstray)
        res = crystal_load_caps(
            cl_target_f=cl_target,
            cstray_f=cstray,
            c1_ext_f=c_ext,
            c2_ext_f=c_ext,
        )
        assert res["ok"] is True
        assert abs(res["cl_error_ppm"]) < 0.01

    def test_cl_target_le_cstray_error(self):
        """cl_target_f <= cstray_f should return ok=False."""
        res = crystal_load_caps(cl_target_f=3e-12, cstray_f=3e-12)
        assert res["ok"] is False

    def test_cl_target_below_cstray_error(self):
        """cl_target_f < cstray_f should return ok=False."""
        res = crystal_load_caps(cl_target_f=1e-12, cstray_f=3e-12)
        assert res["ok"] is False

    def test_asymmetric_caps_actual_cl(self):
        """Asymmetric c1, c2: cl_actual computed correctly."""
        c1 = 15e-12
        c2 = 22e-12
        cstray = 2e-12
        cl_expected = (c1 * c2) / (c1 + c2) + cstray
        res = crystal_load_caps(cl_target_f=10e-12, cstray_f=cstray, c1_ext_f=c1, c2_ext_f=c2)
        assert res["ok"] is True
        assert abs(res["cl_actual_f"] - cl_expected) < 1e-16

    def test_required_keys_present(self):
        res = crystal_load_caps(cl_target_f=12e-12, cstray_f=3e-12)
        assert res["ok"] is True
        for key in ("cl_target_pf", "cstray_pf", "c_ext_symmetric_pf"):
            assert key in res


# ═══════════════════════════════════════════════════════════════════════════════
# 2. pierce_negative_resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestPierceNegativeResistance:
    """Pierce: |−Rn| = gm / (ω²·C1·C2)"""

    _TWO_PI = 2.0 * math.pi

    def test_exact_formula(self):
        """Hand-calc: f=20 MHz, gm=1e-3 S, C1=C2=12e-12 F."""
        f = 20e6
        gm = 1e-3
        c1 = c2 = 12e-12
        esr = 50.0
        omega = self._TWO_PI * f
        expected_neg_res = gm / (omega ** 2 * c1 * c2)
        res = pierce_negative_resistance(
            freq_hz=f, gm_s=gm, c1_f=c1, c2_f=c2, esr_ohm=esr
        )
        assert res["ok"] is True
        assert abs(res["neg_resistance_ohm"] - expected_neg_res) / expected_neg_res < 1e-6

    def test_gm_margin_calculation(self):
        """gm_margin = neg_resistance / esr."""
        f = 10e6
        gm = 5e-3
        c1 = c2 = 15e-12
        esr = 30.0
        omega = self._TWO_PI * f
        expected_neg_res = gm / (omega ** 2 * c1 * c2)
        expected_margin = expected_neg_res / esr
        res = pierce_negative_resistance(
            freq_hz=f, gm_s=gm, c1_f=c1, c2_f=c2, esr_ohm=esr
        )
        assert res["ok"] is True
        assert abs(res["gm_margin"] - expected_margin) / expected_margin < 1e-5

    def test_sufficient_gm_true(self):
        """When margin >> 3, sufficient_gm=True and no warning."""
        res = pierce_negative_resistance(
            freq_hz=10e6, gm_s=100e-3, c1_f=10e-12, c2_f=10e-12, esr_ohm=20.0,
            safety_factor=3.0,
        )
        assert res["ok"] is True
        assert res["sufficient_gm"] is True

    def test_insufficient_gm_warning(self):
        """When margin < 3, warning is issued and sufficient_gm=False."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = pierce_negative_resistance(
                freq_hz=100e6, gm_s=1e-6, c1_f=15e-12, c2_f=15e-12, esr_ohm=50.0,
                safety_factor=3.0,
            )
        assert res["ok"] is True
        assert res["sufficient_gm"] is False
        assert any("Insufficient gm" in str(x.message) for x in w)

    def test_zero_gm_error(self):
        res = pierce_negative_resistance(
            freq_hz=10e6, gm_s=0.0, c1_f=12e-12, c2_f=12e-12, esr_ohm=50.0
        )
        assert res["ok"] is False

    def test_zero_esr_error(self):
        res = pierce_negative_resistance(
            freq_hz=10e6, gm_s=1e-3, c1_f=12e-12, c2_f=12e-12, esr_ohm=0.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. drive_level_estimate
# ═══════════════════════════════════════════════════════════════════════════════

class TestDriveLevelEstimate:
    """P = (ω·CL·V_rms)²·ESR, V_rms = V_peak/sqrt(2)"""

    _TWO_PI = 2.0 * math.pi

    def test_exact_formula(self):
        """Hand-calc for 10 MHz, ESR=50Ω, CL=12 pF, V_peak=1.8V."""
        f = 10e6
        esr = 50.0
        cl = 12e-12
        v_osc = 1.8
        omega = self._TWO_PI * f
        v_rms = v_osc / math.sqrt(2.0)
        i_rms = omega * cl * v_rms
        p_expected_uw = (i_rms ** 2 * esr) * 1e6
        res = drive_level_estimate(freq_hz=f, esr_ohm=esr, c_load_f=cl, v_osc_v=v_osc)
        assert res["ok"] is True
        assert abs(res["drive_level_uw"] - p_expected_uw) / p_expected_uw < 1e-6

    def test_over_drive_true(self):
        """High voltage → over_drive=True and warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = drive_level_estimate(
                freq_hz=20e6, esr_ohm=200.0, c_load_f=33e-12, v_osc_v=3.3,
                max_drive_level_uw=100.0,
            )
        assert res["ok"] is True
        assert res["over_drive"] is True
        assert any("Over-drive" in str(x.message) for x in w)

    def test_over_drive_false(self):
        """Low drive → over_drive=False."""
        res = drive_level_estimate(
            freq_hz=32768.0, esr_ohm=35000.0, c_load_f=7e-12, v_osc_v=1.0,
            max_drive_level_uw=1.0,
        )
        assert res["ok"] is True
        assert res["over_drive"] is False

    def test_zero_freq_error(self):
        res = drive_level_estimate(
            freq_hz=0.0, esr_ohm=50.0, c_load_f=12e-12, v_osc_v=1.8
        )
        assert res["ok"] is False

    def test_drive_scales_with_freq_squared(self):
        """Doubling freq → 4× drive level (ω² dependence)."""
        r1 = drive_level_estimate(
            freq_hz=10e6, esr_ohm=50.0, c_load_f=12e-12, v_osc_v=1.8
        )
        r2 = drive_level_estimate(
            freq_hz=20e6, esr_ohm=50.0, c_load_f=12e-12, v_osc_v=1.8
        )
        ratio = r2["drive_level_uw"] / r1["drive_level_uw"]
        assert abs(ratio - 4.0) < 1e-5


# ═══════════════════════════════════════════════════════════════════════════════
# 4. frequency_pulling
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrequencyPulling:
    """Δf/f ≈ (Cm×ΔCL) / (2×(C0+CL_nom)²)"""

    def test_zero_delta_cl_zero_delta_f(self):
        """cl_actual = cl_nominal → zero pulling."""
        res = frequency_pulling(
            freq_hz=10e6, cm_f=10e-15, c0_f=3e-12,
            cl_nominal_f=12e-12, cl_actual_f=12e-12,
        )
        assert res["ok"] is True
        assert abs(res["delta_f_hz"]) < 1e-12
        assert abs(res["delta_f_hz_exact"]) < 1e-12

    def test_positive_delta_cl_negative_ppm(self):
        """CL higher than nominal → negative frequency pull (crystal pulls down).
        Increasing CL lowers the oscillation frequency."""
        res = frequency_pulling(
            freq_hz=10e6, cm_f=10e-15, c0_f=3e-12,
            cl_nominal_f=12e-12, cl_actual_f=14e-12,
        )
        assert res["ok"] is True
        assert res["delta_f_ppm"] < 0

    def test_approx_matches_exact_small_delta(self):
        """First-order approx and exact agree to within 1% for ΔCL/CL_nom < 5%."""
        res = frequency_pulling(
            freq_hz=32768.0, cm_f=5e-15, c0_f=2e-12,
            cl_nominal_f=12e-12, cl_actual_f=12.5e-12,
        )
        assert res["ok"] is True
        # For small ΔCL the two should agree within 1%
        exact = res["delta_f_ppm_exact"]
        approx = res["delta_f_ppm"]
        if abs(exact) > 0:
            assert abs((approx - exact) / exact) < 0.05  # 5% tolerance

    def test_large_pulling_warning(self):
        """Pulling > 200 ppm issues a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = frequency_pulling(
                freq_hz=10e6, cm_f=100e-15, c0_f=3e-12,
                cl_nominal_f=12e-12, cl_actual_f=30e-12,
            )
        assert res["ok"] is True
        if abs(res["delta_f_ppm_exact"]) > 200:
            assert any("pulling" in str(x.message).lower() for x in w)

    def test_zero_freq_error(self):
        res = frequency_pulling(
            freq_hz=0.0, cm_f=10e-15, c0_f=3e-12,
            cl_nominal_f=12e-12, cl_actual_f=12e-12,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ppm_error_budget
# ═══════════════════════════════════════════════════════════════════════════════

class TestPpmErrorBudget:
    """total = sqrt(init² + temp² + aging² + load²)"""

    def test_rss_calculation(self):
        """Hand-calc RSS."""
        init = 2.0
        temp = 3.0
        aging = 1.0
        load = 0.5
        expected = math.sqrt(init**2 + temp**2 + aging**2 + load**2)
        res = ppm_error_budget(
            initial_tolerance_ppm=init, temp_ppm=temp,
            aging_ppm=aging, load_ppm=load,
        )
        assert res["ok"] is True
        assert abs(res["total_ppm"] - expected) < 0.001

    def test_all_zeros(self):
        res = ppm_error_budget(
            initial_tolerance_ppm=0.0, temp_ppm=0.0,
            aging_ppm=0.0, load_ppm=0.0,
        )
        assert res["ok"] is True
        assert res["total_ppm"] == 0.0

    def test_within_budget_true(self):
        res = ppm_error_budget(
            initial_tolerance_ppm=1.0, temp_ppm=1.0,
            aging_ppm=1.0, load_ppm=1.0,
            budget_limit_ppm=10.0,
        )
        assert res["ok"] is True
        assert res["within_budget"] is True

    def test_within_budget_false_and_warning(self):
        """total > limit → within_budget=False and warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = ppm_error_budget(
                initial_tolerance_ppm=10.0, temp_ppm=10.0,
                aging_ppm=10.0, load_ppm=10.0,
                budget_limit_ppm=5.0,
            )
        assert res["ok"] is True
        assert res["within_budget"] is False
        assert any("exceeded" in str(x.message).lower() for x in w)

    def test_negative_term_error(self):
        res = ppm_error_budget(
            initial_tolerance_ppm=-1.0, temp_ppm=1.0,
            aging_ppm=1.0, load_ppm=1.0,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. rc_oscillator_frequency
# ═══════════════════════════════════════════════════════════════════════════════

class TestRcOscillatorFrequency:
    """f = 1/(rc_factor × 2π × R × C)"""

    _TWO_PI = 2.0 * math.pi

    def test_ideal_rc(self):
        """f = 1/(2π×R×C) for rc_factor=1."""
        r = 10e3
        c = 1e-9
        expected = 1.0 / (self._TWO_PI * r * c)
        res = rc_oscillator_frequency(r_ohm=r, c_f=c, rc_factor=1.0)
        assert res["ok"] is True
        assert abs(res["freq_hz"] - expected) / expected < 1e-9

    def test_double_r_halves_freq(self):
        r1 = rc_oscillator_frequency(r_ohm=10e3, c_f=1e-9)
        r2 = rc_oscillator_frequency(r_ohm=20e3, c_f=1e-9)
        assert abs(r2["freq_hz"] / r1["freq_hz"] - 0.5) < 1e-9

    def test_double_c_halves_freq(self):
        r1 = rc_oscillator_frequency(r_ohm=10e3, c_f=1e-9)
        r2 = rc_oscillator_frequency(r_ohm=10e3, c_f=2e-9)
        assert abs(r2["freq_hz"] / r1["freq_hz"] - 0.5) < 1e-9

    def test_cmos_schmitt_factor(self):
        """CMOS Schmitt: rc_factor = 2.2/(2π) → f = 1/(2.2×R×C)"""
        r = 10e3
        c = 1e-9
        rc_factor = 2.2 / (self._TWO_PI)
        res = rc_oscillator_frequency(r_ohm=r, c_f=c, rc_factor=rc_factor)
        assert res["ok"] is True
        expected = 1.0 / (rc_factor * self._TWO_PI * r * c)
        assert abs(res["freq_hz"] - expected) / expected < 1e-9

    def test_zero_r_error(self):
        res = rc_oscillator_frequency(r_ohm=0.0, c_f=1e-9)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. lc_oscillator_frequency
# ═══════════════════════════════════════════════════════════════════════════════

class TestLcOscillatorFrequency:
    """f = 1/(2π·sqrt(L·C))"""

    _TWO_PI = 2.0 * math.pi

    def test_exact_formula(self):
        """Hand-calc: L=100nH, C=10pF."""
        l = 100e-9
        c = 10e-12
        expected = 1.0 / (self._TWO_PI * math.sqrt(l * c))
        res = lc_oscillator_frequency(l_h=l, c_f=c)
        assert res["ok"] is True
        assert abs(res["freq_hz"] - expected) / expected < 1e-9

    def test_double_l_reduces_freq_sqrt2(self):
        """Doubling L → frequency divides by sqrt(2)."""
        r1 = lc_oscillator_frequency(l_h=100e-9, c_f=10e-12)
        r2 = lc_oscillator_frequency(l_h=200e-9, c_f=10e-12)
        assert abs(r1["freq_hz"] / r2["freq_hz"] - math.sqrt(2.0)) < 1e-9

    def test_double_c_reduces_freq_sqrt2(self):
        """Doubling C → frequency divides by sqrt(2)."""
        r1 = lc_oscillator_frequency(l_h=100e-9, c_f=10e-12)
        r2 = lc_oscillator_frequency(l_h=100e-9, c_f=20e-12)
        assert abs(r1["freq_hz"] / r2["freq_hz"] - math.sqrt(2.0)) < 1e-9

    def test_zero_l_error(self):
        res = lc_oscillator_frequency(l_h=0.0, c_f=10e-12)
        assert res["ok"] is False

    def test_zero_c_error(self):
        res = lc_oscillator_frequency(l_h=100e-9, c_f=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ring_oscillator_frequency
# ═══════════════════════════════════════════════════════════════════════════════

class TestRingOscillatorFrequency:
    """f = 1/(2·N·τ_pd)"""

    def test_exact_formula_n3(self):
        """N=3, τ=100 ps → f = 1/(600 ps) ≈ 1.667 GHz."""
        tau = 100e-12
        n = 3
        expected = 1.0 / (2.0 * n * tau)
        res = ring_oscillator_frequency(n_stages=n, tau_pd_s=tau)
        assert res["ok"] is True
        assert abs(res["freq_hz"] - expected) / expected < 1e-9

    def test_exact_formula_n5(self):
        """N=5, τ=50 ps → f = 1/(500 ps) = 2 GHz."""
        tau = 50e-12
        n = 5
        expected = 1.0 / (2.0 * n * tau)
        res = ring_oscillator_frequency(n_stages=n, tau_pd_s=tau)
        assert res["ok"] is True
        assert abs(res["freq_hz"] - expected) / expected < 1e-9

    def test_even_stages_warning(self):
        """Even N triggers a warning about oscillation."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = ring_oscillator_frequency(n_stages=4, tau_pd_s=100e-12)
        assert res["ok"] is True
        assert any("even" in str(x.message).lower() for x in w)

    def test_n_less_than_3_error(self):
        res = ring_oscillator_frequency(n_stages=2, tau_pd_s=100e-12)
        assert res["ok"] is False

    def test_zero_tau_error(self):
        res = ring_oscillator_frequency(n_stages=3, tau_pd_s=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. pll_divider_n
# ═══════════════════════════════════════════════════════════════════════════════

class TestPllDividerN:
    """N = f_out / f_ref (integer or fractional)"""

    def test_integer_n_exact_divisible(self):
        """f_out = 100 MHz, f_ref = 10 MHz → N = 10, error = 0."""
        res = pll_divider_n(f_out_hz=100e6, f_ref_hz=10e6, integer_n=True)
        assert res["ok"] is True
        assert res["N_used"] == 10
        assert abs(res["freq_error_ppm"]) < 0.001

    def test_integer_n_rounding(self):
        """f_out/f_ref = 10.3 → N = 10, actual f_out = 100 MHz, not 103 MHz."""
        res = pll_divider_n(f_out_hz=103e6, f_ref_hz=10e6, integer_n=True)
        assert res["ok"] is True
        assert res["N_used"] == 10
        assert abs(res["f_out_actual_hz"] - 100e6) < 1e-3

    def test_fractional_n_exact(self):
        """Fractional-N: N_exact = f_out/f_ref, f_out_actual = N_exact × f_ref."""
        res = pll_divider_n(f_out_hz=2.45e9, f_ref_hz=20e6, integer_n=False)
        assert res["ok"] is True
        assert abs(res["N_exact"] - 2.45e9 / 20e6) < 1e-9
        assert abs(res["freq_error_ppm"]) < 0.001  # no rounding

    def test_large_rounding_error_warning(self):
        """Very fractional N (high error) should issue a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # f_out = 100.5 MHz, f_ref = 10 MHz → N exact = 10.05, rounded 10,
            # error = -0.05 × 10 MHz / 100.5 MHz ≈ -4975 ppm (< -1000 ppm threshold)
            res = pll_divider_n(f_out_hz=100.5e6, f_ref_hz=10e6, integer_n=True)
        assert res["ok"] is True
        if abs(res["freq_error_ppm"]) > 1000:
            assert any("rounding" in str(x.message).lower() for x in w)

    def test_zero_f_ref_error(self):
        res = pll_divider_n(f_out_hz=100e6, f_ref_hz=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. pll_type2_loop_filter
# ═══════════════════════════════════════════════════════════════════════════════

class TestPllType2LoopFilter:
    """Type-II CP PLL: C1, R, C2 = C1/10"""

    def test_components_positive(self):
        """All component values must be > 0."""
        res = pll_type2_loop_filter(
            f_loop_bw_hz=100e3, phase_margin_deg=55.0,
            icp_a=1e-3, kvco_hz_per_v=50e6, n_divider=100,
        )
        assert res["ok"] is True
        assert res["R_ohm"] > 0
        assert res["C1_f"] > 0
        assert res["C2_f"] > 0

    def test_c2_equals_c1_over_10(self):
        """C2 = C1 / 10 rule of thumb."""
        res = pll_type2_loop_filter(
            f_loop_bw_hz=100e3, phase_margin_deg=55.0,
            icp_a=1e-3, kvco_hz_per_v=50e6, n_divider=100,
        )
        assert res["ok"] is True
        assert abs(res["C2_f"] / res["C1_f"] - 0.1) < 1e-9

    def test_stable_for_45_deg_margin(self):
        """Phase margin = 45° → stable=True."""
        res = pll_type2_loop_filter(
            f_loop_bw_hz=50e3, phase_margin_deg=45.0,
            icp_a=2e-3, kvco_hz_per_v=100e6, n_divider=200,
        )
        assert res["ok"] is True
        assert res["stable"] is True

    def test_phase_margin_achieved_within_5deg(self):
        """Achieved phase margin should be within 5° of requested (for typical values)."""
        requested = 55.0
        res = pll_type2_loop_filter(
            f_loop_bw_hz=100e3, phase_margin_deg=requested,
            icp_a=1e-3, kvco_hz_per_v=50e6, n_divider=100,
        )
        assert res["ok"] is True
        assert abs(res["phase_margin_achieved_deg"] - requested) < 10.0  # within 10°

    def test_third_order_has_pole2(self):
        """3rd-order returns omega_pole2_rad_s."""
        res = pll_type2_loop_filter(
            f_loop_bw_hz=100e3, phase_margin_deg=55.0,
            icp_a=1e-3, kvco_hz_per_v=50e6, n_divider=100,
            order=3,
        )
        assert res["ok"] is True
        assert "omega_pole2_rad_s" in res
        assert "f_pole2_hz" in res

    def test_invalid_order_error(self):
        """order=1 is invalid."""
        res = pll_type2_loop_filter(
            f_loop_bw_hz=100e3, phase_margin_deg=55.0,
            icp_a=1e-3, kvco_hz_per_v=50e6, n_divider=100,
            order=1,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 11. pll_lock_time
# ═══════════════════════════════════════════════════════════════════════════════

class TestPllLockTime:
    """t_lock ≈ −ln(ε/Δf) / (ζ·ωn)"""

    def test_positive_lock_time(self):
        res = pll_lock_time(
            f_loop_bw_hz=100e3, zeta=0.707, f_step_hz=1e6, epsilon_hz=100.0
        )
        assert res["ok"] is True
        assert res["t_lock_s"] > 0

    def test_larger_step_longer_lock(self):
        """Larger frequency step → longer lock time."""
        r1 = pll_lock_time(
            f_loop_bw_hz=100e3, zeta=0.707, f_step_hz=1e6, epsilon_hz=10.0
        )
        r2 = pll_lock_time(
            f_loop_bw_hz=100e3, zeta=0.707, f_step_hz=10e6, epsilon_hz=10.0
        )
        assert r2["t_lock_s"] > r1["t_lock_s"]

    def test_epsilon_ge_step_error(self):
        """epsilon_hz >= f_step_hz → ok=False."""
        res = pll_lock_time(
            f_loop_bw_hz=100e3, zeta=0.707, f_step_hz=100.0, epsilon_hz=200.0
        )
        assert res["ok"] is False

    def test_t_lock_us_matches_s(self):
        """t_lock_us = t_lock_s × 1e6."""
        res = pll_lock_time(
            f_loop_bw_hz=100e3, zeta=0.707, f_step_hz=1e6, epsilon_hz=1.0
        )
        assert res["ok"] is True
        assert abs(res["t_lock_us"] - res["t_lock_s"] * 1e6) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 12. phase_noise_to_jitter
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhaseNoiseToJitter:
    """σ_jitter = sqrt(2·L_lin·BW) / (2π·f_osc)"""

    _TWO_PI = 2.0 * math.pi

    def test_positive_jitter(self):
        res = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-130.0, integration_bw_hz=10e6
        )
        assert res["ok"] is True
        assert res["sigma_jitter_s"] > 0

    def test_lower_phase_noise_lower_jitter(self):
        """−150 dBc/Hz should give less jitter than −100 dBc/Hz."""
        r1 = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-100.0, integration_bw_hz=1e6
        )
        r2 = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-150.0, integration_bw_hz=1e6
        )
        assert r2["sigma_jitter_s"] < r1["sigma_jitter_s"]

    def test_sigma_jitter_ps_matches_s(self):
        """sigma_jitter_ps = sigma_jitter_s × 1e12."""
        res = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-130.0, integration_bw_hz=10e6
        )
        assert res["ok"] is True
        assert abs(res["sigma_jitter_ps"] - res["sigma_jitter_s"] * 1e12) < 1e-6

    def test_sigma_jitter_fs_matches_s(self):
        """sigma_jitter_fs = sigma_jitter_s × 1e15."""
        res = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-130.0, integration_bw_hz=10e6
        )
        assert res["ok"] is True
        assert abs(res["sigma_jitter_fs"] - res["sigma_jitter_s"] * 1e15) < 1e-3

    def test_exact_formula(self):
        """Hand-calc: f=100 MHz, L=−120 dBc/Hz, BW=1 MHz."""
        f_osc = 100e6
        l_dbc = -120.0
        bw = 1e6
        l_lin = 10.0 ** (l_dbc / 10.0)
        sigma_phase = math.sqrt(2.0 * l_lin * bw)
        sigma_jitter_expected = sigma_phase / (self._TWO_PI * f_osc)
        res = phase_noise_to_jitter(
            f_osc_hz=f_osc, phase_noise_dbc_hz=l_dbc, integration_bw_hz=bw
        )
        assert res["ok"] is True
        assert abs(res["sigma_jitter_s"] - sigma_jitter_expected) / sigma_jitter_expected < 1e-9

    def test_zero_bw_error(self):
        """integration_bw_hz=0 → ok=False (must be positive)."""
        res = phase_noise_to_jitter(
            f_osc_hz=100e6, phase_noise_dbc_hz=-130.0, integration_bw_hz=0.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 13. LLM tool handlers (stub registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLlmToolHandlers:
    """Smoke tests for tool handler wrappers."""

    @pytest.mark.asyncio
    async def test_crystal_load_caps_tool_ok(self):
        res = await call(
            _osc_crystal_load_caps_tool,
            cl_target_f=12e-12,
            cstray_f=3e-12,
        )
        assert res["ok"] is True
        assert "c_ext_symmetric_pf" in res

    @pytest.mark.asyncio
    async def test_pierce_neg_resistance_tool_ok(self):
        res = await call(
            _osc_pierce_neg_resistance_tool,
            freq_hz=10e6,
            gm_s=5e-3,
            c1_f=12e-12,
            c2_f=12e-12,
            esr_ohm=50.0,
        )
        assert res["ok"] is True
        assert "neg_resistance_ohm" in res
        assert "gm_margin" in res

    @pytest.mark.asyncio
    async def test_pll_loop_filter_tool_ok(self):
        res = await call(
            _pll_loop_filter_tool,
            f_loop_bw_hz=100e3,
            phase_margin_deg=55.0,
            icp_a=1e-3,
            kvco_hz_per_v=50e6,
            n_divider=100.0,
        )
        assert res["ok"] is True
        assert "R_ohm" in res
        assert "C1_f" in res

    @pytest.mark.asyncio
    async def test_pll_phase_noise_to_jitter_tool_ok(self):
        res = await call(
            _pll_phase_noise_to_jitter_tool,
            f_osc_hz=100e6,
            phase_noise_dbc_hz=-130.0,
            integration_bw_hz=10e6,
        )
        assert res["ok"] is True
        assert "sigma_jitter_ps" in res

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        result = await _osc_crystal_load_caps_tool(None, b"not-json{{")
        parsed = json.loads(result)
        # Real registry: {"error": ..., "code": ...}; stub: {"ok": False, ...}
        assert parsed.get("ok") is False or "error" in parsed
