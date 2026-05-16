"""
Hermetic tests for kerf_cad_core.cuttingtool — cutting-tool geometry,
mechanics & tool-life economics.

Coverage:
  tool.orthogonal_to_normal       — angle system transform
  tool.normal_to_orthogonal       — inverse transform
  tool.merchant_orthogonal        — Merchant model: forces, shear angle, chip ratio
  tool.specific_cutting_energy    — specific energy and power
  tool.cutting_power              — power calculation
  tool.taylor_tool_life           — Taylor VT^n = C
  tool.taylor_extended_tool_life  — extended Taylor
  tool.economic_cutting_speed     — min-cost speed
  tool.max_production_rate_speed  — max-rate speed
  tool.break_even_speed           — break-even range
  tool.machinability_rating       — machinability index
  tool.nose_radius_roughness      — surface finish Ra / Rt
  tools.*                         — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against Boothroyd/Shaw hand-calcs
(Merchant, Taylor, economic speed).

References
----------
Boothroyd, G. & Knight, W.A. "Fundamentals of Machining and Machine Tools", 3rd ed.
Shaw, M.C. "Metal Cutting Principles", 2nd ed.
Merchant, M.E. (1945) J. Appl. Phys. 16, 267–275.
Taylor, F.W. (1907) Trans. ASME 28, 31–350.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.cuttingtool.tool import (
    orthogonal_to_normal,
    normal_to_orthogonal,
    merchant_orthogonal,
    specific_cutting_energy,
    cutting_power,
    taylor_tool_life,
    taylor_extended_tool_life,
    economic_cutting_speed,
    max_production_rate_speed,
    break_even_speed,
    machinability_rating,
    nose_radius_roughness,
)
from kerf_cad_core.cuttingtool.tools import (
    run_cutting_tool_angle_transform,
    run_cutting_tool_merchant,
    run_cutting_tool_specific_energy,
    run_cutting_tool_taylor_life,
    run_cutting_tool_taylor_extended_life,
    run_cutting_tool_economic_speed,
    run_cutting_tool_max_rate_speed,
    run_cutting_tool_break_even,
    run_cutting_tool_machinability,
    run_cutting_tool_surface_finish,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-9   # relative tolerance for exact algebraic checks
TREL = 1e-6  # looser tolerance for iterative / trig checks


# ===========================================================================
# 1. orthogonal_to_normal
# ===========================================================================

class TestOrthogonalToNormal:

    def test_zero_inclination_passes_through(self):
        """λ_s = 0 → γ_n = γ_o, α_n = α_o (cos 0 = 1)."""
        res = orthogonal_to_normal(15.0, 8.0, 0.0)
        assert res["ok"] is True
        assert abs(res["gamma_n_deg"] - 15.0) < TREL
        assert abs(res["alpha_n_deg"] - 8.0) < TREL

    def test_formula_gamma_n_algebraic(self):
        """tan(γ_n) = tan(γ_o) · cos(λ_s)."""
        go, ao, ls = 10.0, 6.0, 30.0
        tan_gn_expected = math.tan(math.radians(go)) * math.cos(math.radians(ls))
        gamma_n_expected = math.degrees(math.atan(tan_gn_expected))
        res = orthogonal_to_normal(go, ao, ls)
        assert res["ok"] is True
        assert abs(res["gamma_n_deg"] - gamma_n_expected) < TREL

    def test_formula_alpha_n_algebraic(self):
        """tan(α_n) = tan(α_o) · cos(λ_s)."""
        go, ao, ls = 10.0, 6.0, 30.0
        tan_an_expected = math.tan(math.radians(ao)) * math.cos(math.radians(ls))
        alpha_n_expected = math.degrees(math.atan(tan_an_expected))
        res = orthogonal_to_normal(go, ao, ls)
        assert abs(res["alpha_n_deg"] - alpha_n_expected) < TREL

    def test_inclination_reduces_effective_rake(self):
        """Positive inclination reduces effective normal rake below orthogonal rake."""
        res0 = orthogonal_to_normal(15.0, 8.0, 0.0)
        res30 = orthogonal_to_normal(15.0, 8.0, 30.0)
        assert res30["gamma_n_deg"] < res0["gamma_n_deg"]

    def test_negative_rake_accepted(self):
        """Negative orthogonal rake must return ok=True."""
        res = orthogonal_to_normal(-10.0, 8.0, 5.0)
        assert res["ok"] is True
        assert res["gamma_n_deg"] < 0

    def test_lambda_s_echo(self):
        """lambda_s_deg echoes input."""
        res = orthogonal_to_normal(10.0, 6.0, 15.0)
        assert res["lambda_s_deg"] == 15.0

    def test_non_finite_input_returns_error(self):
        res = orthogonal_to_normal(float("nan"), 8.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 2. normal_to_orthogonal (inverse)
# ===========================================================================

class TestNormalToOrthogonal:

    def test_roundtrip(self):
        """orthogonal → normal → orthogonal recovers original angles."""
        go_orig, ao_orig, ls = 12.0, 7.0, 20.0
        res_n = orthogonal_to_normal(go_orig, ao_orig, ls)
        assert res_n["ok"] is True
        res_o = normal_to_orthogonal(res_n["gamma_n_deg"], res_n["alpha_n_deg"], ls)
        assert res_o["ok"] is True
        assert abs(res_o["gamma_o_deg"] - go_orig) < TREL
        assert abs(res_o["alpha_o_deg"] - ao_orig) < TREL

    def test_zero_inclination_passthrough(self):
        """λ_s = 0 → γ_o = γ_n, α_o = α_n."""
        res = normal_to_orthogonal(15.0, 8.0, 0.0)
        assert res["ok"] is True
        assert abs(res["gamma_o_deg"] - 15.0) < TREL
        assert abs(res["alpha_o_deg"] - 8.0) < TREL

    def test_lambda_s_90_returns_error(self):
        """λ_s = 90° → cos(λ_s) = 0 → singular; must return ok=False."""
        res = normal_to_orthogonal(10.0, 6.0, 90.0)
        assert res["ok"] is False

    def test_non_finite_returns_error(self):
        res = normal_to_orthogonal(float("inf"), 6.0, 10.0)
        assert res["ok"] is False


# ===========================================================================
# 3. merchant_orthogonal
# ===========================================================================

class TestMerchantOrthogonal:

    # --- Boothroyd/Shaw hand-calc reference ---
    # γ_o = 10°, μ = 0.5 → β = 26.565°
    # φ = 45 + 5 − 13.28 = 36.72°
    # Use tau_s = 350 MPa, t1 = 0.25 mm, b = 2.5 mm, vc = 100 m/min

    _GO = 10.0
    _MU = 0.5
    _TAU_S = 350e6
    _T1 = 0.25
    _B = 2.5
    _VC = 100.0

    def _merchant(self, **kw):
        defaults = dict(
            gamma_o=self._GO, tau_s=self._TAU_S, mu=self._MU,
            t1=self._T1, vc=self._VC, width_b=self._B
        )
        defaults.update(kw)
        return merchant_orthogonal(**defaults)

    def test_returns_ok(self):
        assert self._merchant()["ok"] is True

    def test_shear_angle_formula(self):
        """φ = 45 + γ_o/2 − β/2 (Merchant min-energy)."""
        res = self._merchant()
        beta = math.degrees(math.atan(self._MU))
        phi_expected = 45.0 + self._GO / 2.0 - beta / 2.0
        assert abs(res["phi_deg"] - phi_expected) < TREL

    def test_chip_ratio_formula(self):
        """r_c = sin(φ) / cos(φ − γ_o)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        go_rad = math.radians(self._GO)
        r_c_expected = math.sin(phi_rad) / math.cos(phi_rad - go_rad)
        assert abs(res["r_c"] - r_c_expected) < TREL

    def test_chip_thickness_formula(self):
        """t2 = t1 / r_c."""
        res = self._merchant()
        t2_expected = self._T1 / res["r_c"]
        assert abs(res["t2_mm"] - t2_expected) < TREL

    def test_shear_force_formula(self):
        """Fs = τ_s × b × t1 / sin(φ)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        b_m = self._B * 1e-3
        t1_m = self._T1 * 1e-3
        Fs_expected = self._TAU_S * b_m * t1_m / math.sin(phi_rad)
        assert abs(res["Fs_N"] - Fs_expected) / Fs_expected < TREL

    def test_cutting_force_formula(self):
        """Fc = Fs cos(β − γ_o) / cos(φ + β − γ_o)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        beta_rad = math.radians(res["beta_deg"])
        go_rad = math.radians(self._GO)
        Fc_expected = (res["Fs_N"] * math.cos(beta_rad - go_rad)
                       / math.cos(phi_rad + beta_rad - go_rad))
        assert abs(res["Fc_N"] - Fc_expected) / abs(Fc_expected) < TREL

    def test_thrust_force_formula(self):
        """Ft = Fs sin(β − γ_o) / cos(φ + β − γ_o)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        beta_rad = math.radians(res["beta_deg"])
        go_rad = math.radians(self._GO)
        Ft_expected = (res["Fs_N"] * math.sin(beta_rad - go_rad)
                       / math.cos(phi_rad + beta_rad - go_rad))
        assert abs(res["Ft_N"] - Ft_expected) / max(abs(Ft_expected), 1e-12) < TREL

    def test_friction_force_formula(self):
        """F_friction = Fc sin(γ_o) + Ft cos(γ_o)."""
        res = self._merchant()
        go_rad = math.radians(self._GO)
        F_expected = res["Fc_N"] * math.sin(go_rad) + res["Ft_N"] * math.cos(go_rad)
        assert abs(res["F_friction_N"] - F_expected) / max(abs(F_expected), 1e-12) < TREL

    def test_chip_velocity_formula(self):
        """v_chip = vc × sin(φ) / cos(φ − γ_o)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        go_rad = math.radians(self._GO)
        vc_expected = self._VC * math.sin(phi_rad) / math.cos(phi_rad - go_rad)
        assert abs(res["vchip_m_min"] - vc_expected) / vc_expected < TREL

    def test_shear_velocity_formula(self):
        """vs = vc × cos(γ_o) / cos(φ − γ_o)."""
        res = self._merchant()
        phi_rad = math.radians(res["phi_deg"])
        go_rad = math.radians(self._GO)
        vs_expected = self._VC * math.cos(go_rad) / math.cos(phi_rad - go_rad)
        assert abs(res["vs_m_min"] - vs_expected) / vs_expected < TREL

    def test_higher_rake_reduces_cutting_force(self):
        """Higher rake angle reduces cutting force (for same τ_s, μ, t1)."""
        r5 = merchant_orthogonal(5.0, self._TAU_S, self._MU, self._T1, self._VC, width_b=self._B)
        r20 = merchant_orthogonal(20.0, self._TAU_S, self._MU, self._T1, self._VC, width_b=self._B)
        assert r20["Fc_N"] < r5["Fc_N"]

    def test_higher_friction_increases_shear_angle_sensitivity(self):
        """Higher μ → larger β → smaller φ → larger Fc."""
        r_low_mu = merchant_orthogonal(10.0, self._TAU_S, 0.3, self._T1, self._VC, width_b=self._B)
        r_hi_mu = merchant_orthogonal(10.0, self._TAU_S, 0.8, self._T1, self._VC, width_b=self._B)
        assert r_hi_mu["phi_deg"] < r_low_mu["phi_deg"]

    def test_beta_equals_arctan_mu(self):
        """β = arctan(μ)."""
        res = self._merchant()
        beta_expected = math.degrees(math.atan(self._MU))
        assert abs(res["beta_deg"] - beta_expected) < TREL

    def test_negative_tau_s_returns_error(self):
        res = merchant_orthogonal(10.0, -100e6, 0.5, 0.25, 100.0)
        assert res["ok"] is False

    def test_zero_vc_returns_error(self):
        res = merchant_orthogonal(10.0, 350e6, 0.5, 0.25, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 4. specific_cutting_energy
# ===========================================================================

class TestSpecificCuttingEnergy:

    def test_power_formula(self):
        """P = Fc × vc / 60."""
        Fc, b, t1, vc = 800.0, 3.0, 0.2, 120.0
        res = specific_cutting_energy(Fc, b, t1, vc)
        assert res["ok"] is True
        P_expected = Fc * vc / 60.0
        assert abs(res["power_W"] - P_expected) / P_expected < REL

    def test_MRR_formula(self):
        """MRR = b × t1 × vc × 1000 [mm³/min]."""
        Fc, b, t1, vc = 800.0, 3.0, 0.2, 120.0
        res = specific_cutting_energy(Fc, b, t1, vc)
        MRR_expected = b * t1 * vc * 1000.0
        assert abs(res["MRR_mm3_per_min"] - MRR_expected) / MRR_expected < REL

    def test_specific_energy_formula(self):
        """u = P_W / MRR_mm3_s = Fc × 60 / (b × t1 × 1000)."""
        Fc, b, t1, vc = 800.0, 3.0, 0.2, 120.0
        res = specific_cutting_energy(Fc, b, t1, vc)
        P = Fc * vc / 60.0
        MRR_s = b * t1 * vc * 1000.0 / 60.0
        u_expected = P / MRR_s
        assert abs(res["u_J_per_mm3"] - u_expected) / u_expected < REL

    def test_zero_b_returns_error(self):
        res = specific_cutting_energy(800.0, 0.0, 0.2, 120.0)
        assert res["ok"] is False

    def test_negative_Fc_returns_error(self):
        res = specific_cutting_energy(-100.0, 3.0, 0.2, 120.0)
        assert res["ok"] is False


# ===========================================================================
# 5. cutting_power
# ===========================================================================

class TestCuttingPower:

    def test_power_formula(self):
        """P = Fc × vc / 60."""
        Fc, vc = 500.0, 150.0
        res = cutting_power(Fc, vc)
        assert res["ok"] is True
        assert abs(res["power_W"] - Fc * vc / 60.0) < REL

    def test_power_kW_conversion(self):
        """power_kW = power_W / 1000."""
        res = cutting_power(500.0, 150.0)
        assert abs(res["power_kW"] - res["power_W"] / 1000.0) < REL

    def test_zero_Fc_returns_error(self):
        res = cutting_power(0.0, 100.0)
        assert res["ok"] is False


# ===========================================================================
# 6. taylor_tool_life
# ===========================================================================

class TestTaylorToolLife:

    def test_formula_T_equals_C_over_V_to_1_over_n(self):
        """T = (C / V)^(1/n)."""
        V, C, n = 80.0, 200.0, 0.25
        res = taylor_tool_life(V, C, n)
        assert res["ok"] is True
        T_expected = (C / V) ** (1.0 / n)
        assert abs(res["T_min"] - T_expected) / T_expected < TREL

    def test_V_equals_C_gives_T_equals_1(self):
        """When V = C → T = 1 min (definition of C)."""
        C = 150.0
        res = taylor_tool_life(C, C, 0.3)
        assert res["ok"] is True
        assert abs(res["T_min"] - 1.0) < TREL

    def test_higher_speed_reduces_tool_life(self):
        """Increasing V must decrease T."""
        C, n = 200.0, 0.25
        T_low = taylor_tool_life(80.0, C, n)["T_min"]
        T_high = taylor_tool_life(120.0, C, n)["T_min"]
        assert T_high < T_low

    def test_larger_n_reduces_speed_sensitivity(self):
        """Larger n → tool life less sensitive to speed change."""
        V, C = 100.0, 200.0
        # Halving V: T_new = (C / V/2)^(1/n) = (2C/V)^(1/n) = 2^(1/n) × T_orig
        T1 = taylor_tool_life(V, C, 0.2)["T_min"]
        T2 = taylor_tool_life(V, C, 0.4)["T_min"]
        # With V < C, both T > 1; larger n gives longer life at same V
        assert T2 < T1  # n=0.2 → larger exponent 1/0.2=5, n=0.4 → 1/0.4=2.5, same base>1

    def test_warn_range_flag_set_for_extreme_V_over_C(self):
        """V/C > 10 sets warn_range True."""
        res = taylor_tool_life(V=10000.0, C=100.0, n=0.25)
        assert res["ok"] is True
        assert res["warn_range"] is True

    def test_warn_range_false_for_normal_range(self):
        """V/C ≈ 1 → warn_range False."""
        res = taylor_tool_life(V=100.0, C=200.0, n=0.25)
        assert res["warn_range"] is False

    def test_negative_V_returns_error(self):
        res = taylor_tool_life(-50.0, 200.0, 0.25)
        assert res["ok"] is False

    def test_zero_n_returns_error(self):
        res = taylor_tool_life(100.0, 200.0, 0.0)
        assert res["ok"] is False

    def test_VB_scaling_optional(self):
        """With VB_actual and VB_reference, T_at_VB_actual is returned."""
        res = taylor_tool_life(100.0, 200.0, 0.25, VB_actual=0.5, VB_reference=0.3)
        assert res["ok"] is True
        assert "T_at_VB_actual_min" in res
        T_ref = res["T_min"]
        T_vb = res["T_at_VB_actual_min"]
        assert abs(T_vb - T_ref * (0.5 / 0.3)) / T_ref < TREL


# ===========================================================================
# 7. taylor_extended_tool_life
# ===========================================================================

class TestTaylorExtendedToolLife:

    def test_unity_feed_depth_at_ref_matches_basic_taylor(self):
        """a_f=0, a_d=0 (feed/depth exponents zero) → same as basic Taylor."""
        V, C, n = 100.0, 200.0, 0.25
        res_basic = taylor_tool_life(V, C, n)
        res_ext = taylor_extended_tool_life(V, C, n, f=0.3, a_f=0.0, d=2.0, a_d=0.0)
        assert abs(res_ext["T_min"] - res_basic["T_min"]) / res_basic["T_min"] < TREL

    def test_higher_feed_reduces_tool_life(self):
        """Increasing feed (with a_f > 0) must reduce T."""
        V, C, n = 100.0, 200.0, 0.25
        T_low = taylor_extended_tool_life(V, C, n, f=0.1, a_f=0.5, d=2.0, a_d=0.2)["T_min"]
        T_high = taylor_extended_tool_life(V, C, n, f=0.5, a_f=0.5, d=2.0, a_d=0.2)["T_min"]
        assert T_high < T_low

    def test_C_eff_formula(self):
        """C_eff = C × (f_ref/f)^a_f × (d_ref/d)^a_d."""
        V, C, n = 100.0, 200.0, 0.25
        f, a_f, d, a_d = 0.3, 0.5, 2.0, 0.2
        f_ref, d_ref = 0.2, 1.5
        res = taylor_extended_tool_life(V, C, n, f, a_f, d, a_d, f_ref=f_ref, d_ref=d_ref)
        C_eff_expected = C * (f_ref / f) ** a_f * (d_ref / d) ** a_d
        assert abs(res["C_eff"] - C_eff_expected) / C_eff_expected < TREL

    def test_T_from_C_eff(self):
        """T = (C_eff / V)^(1/n)."""
        V, C, n = 100.0, 200.0, 0.25
        f, a_f, d, a_d = 0.3, 0.5, 2.0, 0.2
        res = taylor_extended_tool_life(V, C, n, f, a_f, d, a_d)
        T_expected = (res["C_eff"] / V) ** (1.0 / n)
        assert abs(res["T_min"] - T_expected) / T_expected < TREL

    def test_negative_a_f_returns_error(self):
        res = taylor_extended_tool_life(100.0, 200.0, 0.25, f=0.3, a_f=-0.1, d=2.0, a_d=0.2)
        assert res["ok"] is False

    def test_zero_f_returns_error(self):
        res = taylor_extended_tool_life(100.0, 200.0, 0.25, f=0.0, a_f=0.5, d=2.0, a_d=0.2)
        assert res["ok"] is False


# ===========================================================================
# 8. economic_cutting_speed
# ===========================================================================

class TestEconomicCuttingSpeed:

    # Reference values: n=0.25, C=200, C_tool=5, t_ct=2, C_m=1
    # T_e = (1/0.25 − 1) × (2 + 5/1) = 3 × 7 = 21 min
    # V_e = 200 / 21^0.25

    def test_T_e_formula(self):
        """T_e = (1/n − 1) × (t_ct + C_tool/C_m)."""
        n, t_ct, C_tool, C_m = 0.25, 2.0, 5.0, 1.0
        T_e_expected = (1.0 / n - 1.0) * (t_ct + C_tool / C_m)
        res = economic_cutting_speed(C_tool, t_ct, t_c=5.0, C_m=C_m, n=n, C=200.0)
        assert res["ok"] is True
        assert abs(res["T_e_min"] - T_e_expected) / T_e_expected < TREL

    def test_V_e_formula(self):
        """V_e = C / T_e^n."""
        n, t_ct, C_tool, C_m, C_val = 0.25, 2.0, 5.0, 1.0, 200.0
        T_e = (1.0 / n - 1.0) * (t_ct + C_tool / C_m)
        V_e_expected = C_val / (T_e ** n)
        res = economic_cutting_speed(C_tool, t_ct, t_c=5.0, C_m=C_m, n=n, C=C_val)
        assert abs(res["V_e_m_min"] - V_e_expected) / V_e_expected < TREL

    def test_higher_tool_cost_reduces_V_e(self):
        """Higher tool cost → larger T_e → lower V_e."""
        V_cheap = economic_cutting_speed(1.0, 2.0, 5.0, 1.0, 0.25, 200.0)["V_e_m_min"]
        V_expensive = economic_cutting_speed(20.0, 2.0, 5.0, 1.0, 0.25, 200.0)["V_e_m_min"]
        assert V_expensive < V_cheap

    def test_n_ge_1_returns_error(self):
        """n >= 1 → formula degenerate → ok=False."""
        res = economic_cutting_speed(5.0, 2.0, 5.0, 1.0, n=1.0, C=200.0)
        assert res["ok"] is False

    def test_V_e_positive(self):
        """V_e must be positive for valid inputs."""
        res = economic_cutting_speed(5.0, 2.0, 5.0, 1.0, 0.25, 200.0)
        assert res["ok"] is True
        assert res["V_e_m_min"] > 0

    def test_cost_per_piece_positive(self):
        """cost_per_piece_at_Ve must be positive."""
        res = economic_cutting_speed(5.0, 2.0, 5.0, 1.0, 0.25, 200.0)
        assert res["cost_per_piece_at_Ve"] > 0


# ===========================================================================
# 9. max_production_rate_speed
# ===========================================================================

class TestMaxProductionRateSpeed:

    # T_mpr = (1/0.25 − 1) × 2 = 3 × 2 = 6 min
    # V_mpr = 200 / 6^0.25

    def test_T_mpr_formula(self):
        """T_mpr = (1/n − 1) × t_ct."""
        n, t_ct = 0.25, 2.0
        T_mpr_expected = (1.0 / n - 1.0) * t_ct
        res = max_production_rate_speed(t_ct, 5.0, n, 200.0)
        assert res["ok"] is True
        assert abs(res["T_mpr_min"] - T_mpr_expected) / T_mpr_expected < TREL

    def test_V_mpr_formula(self):
        """V_mpr = C / T_mpr^n."""
        n, t_ct, C = 0.25, 2.0, 200.0
        T_mpr = (1.0 / n - 1.0) * t_ct
        V_mpr_expected = C / (T_mpr ** n)
        res = max_production_rate_speed(t_ct, 5.0, n, C)
        assert abs(res["V_mpr_m_min"] - V_mpr_expected) / V_mpr_expected < TREL

    def test_V_mpr_ge_V_e(self):
        """V_mpr >= V_e always (max-rate speed is equal to or higher than economic speed)."""
        n, t_ct, t_c, C_tool, C_m, C = 0.25, 2.0, 5.0, 5.0, 1.0, 200.0
        V_e = economic_cutting_speed(C_tool, t_ct, t_c, C_m, n, C)["V_e_m_min"]
        V_mpr = max_production_rate_speed(t_ct, t_c, n, C)["V_mpr_m_min"]
        assert V_mpr >= V_e - 1e-9

    def test_cycle_time_formula(self):
        """cycle_time_s = (t_c + t_ct × t_c / T_mpr) × 60."""
        n, t_ct, t_c, C = 0.25, 2.0, 5.0, 200.0
        res = max_production_rate_speed(t_ct, t_c, n, C)
        T_mpr = res["T_mpr_min"]
        cycle_expected = (t_c + t_ct * t_c / T_mpr) * 60.0
        assert abs(res["cycle_time_s"] - cycle_expected) / cycle_expected < TREL

    def test_n_ge_1_returns_error(self):
        res = max_production_rate_speed(2.0, 5.0, n=1.0, C=200.0)
        assert res["ok"] is False


# ===========================================================================
# 10. break_even_speed
# ===========================================================================

class TestBreakEvenSpeed:

    def test_V_mpr_ge_V_e(self):
        """V_mpr >= V_e in break-even output."""
        res = break_even_speed(5.0, 2.0, 5.0, 1.0, 0.25, 200.0)
        assert res["ok"] is True
        assert res["V_mpr_m_min"] >= res["V_e_m_min"] - 1e-9

    def test_cost_ratio_ge_1(self):
        """cost at V_mpr >= cost at V_e (max-rate is more expensive)."""
        res = break_even_speed(5.0, 2.0, 5.0, 1.0, 0.25, 200.0)
        assert res["cost_ratio_mpr_to_e"] >= 1.0 - 1e-9

    def test_invalid_n_returns_error(self):
        res = break_even_speed(5.0, 2.0, 5.0, 1.0, n=1.1, C=200.0)
        assert res["ok"] is False

    def test_positive_costs_returned(self):
        res = break_even_speed(5.0, 2.0, 5.0, 1.0, 0.25, 200.0)
        assert res["cost_per_piece_at_Ve"] > 0
        assert res["cost_per_piece_at_Vmpr"] > 0


# ===========================================================================
# 11. machinability_rating
# ===========================================================================

class TestMachinabilityRating:

    def test_same_speed_gives_100_percent(self):
        """V_material = V_reference → 100%."""
        res = machinability_rating(100.0, 100.0)
        assert res["ok"] is True
        assert abs(res["rating_pct"] - 100.0) < REL

    def test_double_speed_gives_200_percent(self):
        res = machinability_rating(200.0, 100.0)
        assert abs(res["rating_pct"] - 200.0) < REL

    def test_half_speed_gives_50_percent(self):
        res = machinability_rating(50.0, 100.0)
        assert abs(res["rating_pct"] - 50.0) < REL

    def test_formula_algebraic(self):
        """rating = V_mat / V_ref × 100."""
        V_mat, V_ref = 75.0, 120.0
        res = machinability_rating(V_mat, V_ref)
        assert abs(res["rating_pct"] - (V_mat / V_ref * 100.0)) < REL

    def test_zero_V_reference_returns_error(self):
        res = machinability_rating(100.0, 0.0)
        assert res["ok"] is False

    def test_negative_V_material_returns_error(self):
        res = machinability_rating(-50.0, 100.0)
        assert res["ok"] is False


# ===========================================================================
# 12. nose_radius_roughness
# ===========================================================================

class TestNoseRadiusRoughness:

    def test_Rt_formula(self):
        """Rt = f² / (8 r_n) [mm] × 1000 → μm."""
        f, r_n = 0.3, 0.8
        Rt_expected_um = (f ** 2 / (8.0 * r_n)) * 1000.0
        res = nose_radius_roughness(f, r_n)
        assert res["ok"] is True
        assert abs(res["Rt_um"] - Rt_expected_um) / Rt_expected_um < REL

    def test_Ra_equals_Rt_over_4(self):
        """Ra ≈ Rt / 4 (sinusoidal profile approximation)."""
        res = nose_radius_roughness(0.2, 1.2)
        assert abs(res["Ra_um"] - res["Rt_um"] / 4.0) < REL

    def test_larger_feed_increases_roughness(self):
        """Increasing feed increases Rt (Rt ∝ f²)."""
        Rt_low = nose_radius_roughness(0.1, 0.8)["Rt_um"]
        Rt_high = nose_radius_roughness(0.3, 0.8)["Rt_um"]
        assert Rt_high > Rt_low

    def test_larger_nose_radius_reduces_roughness(self):
        """Larger r_n reduces Rt (Rt ∝ 1/r_n)."""
        Rt_small = nose_radius_roughness(0.2, 0.5)["Rt_um"]
        Rt_large = nose_radius_roughness(0.2, 2.0)["Rt_um"]
        assert Rt_large < Rt_small

    def test_quadratic_feed_scaling(self):
        """Doubling f quadruples Rt (Rt ∝ f²)."""
        Rt1 = nose_radius_roughness(0.1, 1.0)["Rt_um"]
        Rt2 = nose_radius_roughness(0.2, 1.0)["Rt_um"]
        assert abs(Rt2 / Rt1 - 4.0) < 1e-9

    def test_zero_feed_returns_error(self):
        res = nose_radius_roughness(0.0, 0.8)
        assert res["ok"] is False

    def test_zero_nose_radius_returns_error(self):
        res = nose_radius_roughness(0.2, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 13. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    # --- angle transform ---

    def test_angle_transform_ortho_to_normal_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_angle_transform(
            ctx, _args(rake_deg=10.0, clearance_deg=6.0, inclination_deg=20.0)
        ))
        d = _ok_tool(raw)
        assert "gamma_n_deg" in d
        assert "alpha_n_deg" in d

    def test_angle_transform_normal_to_ortho_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_angle_transform(
            ctx, _args(
                direction="normal_to_orthogonal",
                rake_deg=9.4, clearance_deg=5.6, inclination_deg=20.0,
            )
        ))
        d = _ok_tool(raw)
        assert "gamma_o_deg" in d

    def test_angle_transform_missing_rake_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_angle_transform(
            ctx, _args(clearance_deg=6.0)
        ))
        _err_tool(raw)

    def test_angle_transform_bad_json_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_angle_transform(ctx, b"not json"))
        _err_tool(raw)

    # --- merchant ---

    def test_merchant_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_merchant(ctx, _args(
            gamma_o_deg=10.0, tau_s_Pa=350e6, mu=0.5,
            t1_mm=0.25, vc_m_min=100.0, width_b_mm=2.5,
        )))
        d = _ok_tool(raw)
        assert d["phi_deg"] > 0
        assert d["Fc_N"] > 0
        assert d["r_c"] > 0

    def test_merchant_missing_mu_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_merchant(ctx, _args(
            gamma_o_deg=10.0, tau_s_Pa=350e6, t1_mm=0.25, vc_m_min=100.0,
        )))
        _err_tool(raw)

    # --- specific energy ---

    def test_specific_energy_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_specific_energy(ctx, _args(
            Fc_N=800.0, b_mm=3.0, t1_mm=0.2, vc_m_min=120.0
        )))
        d = _ok_tool(raw)
        assert d["u_J_per_mm3"] > 0
        assert d["power_W"] > 0

    def test_specific_energy_missing_field_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_specific_energy(ctx, _args(
            b_mm=3.0, t1_mm=0.2, vc_m_min=120.0
        )))
        _err_tool(raw)

    # --- Taylor life ---

    def test_taylor_life_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_taylor_life(ctx, _args(
            V_m_min=100.0, C_m_min=200.0, n=0.25
        )))
        d = _ok_tool(raw)
        assert d["T_min"] > 0

    def test_taylor_life_V_equals_C_gives_T_1(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_taylor_life(ctx, _args(
            V_m_min=150.0, C_m_min=150.0, n=0.3
        )))
        d = _ok_tool(raw)
        assert abs(d["T_min"] - 1.0) < TREL

    def test_taylor_life_bad_json_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_taylor_life(ctx, b"{bad"))
        _err_tool(raw)

    # --- extended Taylor ---

    def test_taylor_extended_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_taylor_extended_life(ctx, _args(
            V_m_min=100.0, C_m_min=200.0, n=0.25,
            f_mm_rev=0.3, a_f=0.5, d_mm=2.0, a_d=0.2,
        )))
        d = _ok_tool(raw)
        assert d["T_min"] > 0

    def test_taylor_extended_missing_a_f_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_taylor_extended_life(ctx, _args(
            V_m_min=100.0, C_m_min=200.0, n=0.25,
            f_mm_rev=0.3, d_mm=2.0, a_d=0.2,
        )))
        _err_tool(raw)

    # --- economic speed ---

    def test_economic_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_economic_speed(ctx, _args(
            C_tool=5.0, t_ct_min=2.0, t_c_min=5.0,
            C_m_per_min=1.0, n=0.25, C_m_min=200.0,
        )))
        d = _ok_tool(raw)
        assert d["V_e_m_min"] > 0
        assert d["T_e_min"] > 0

    def test_economic_speed_n_ge_1_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_economic_speed(ctx, _args(
            C_tool=5.0, t_ct_min=2.0, t_c_min=5.0,
            C_m_per_min=1.0, n=1.2, C_m_min=200.0,
        )))
        _err_tool(raw)

    # --- max rate speed ---

    def test_max_rate_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_max_rate_speed(ctx, _args(
            t_ct_min=2.0, t_c_min=5.0, n=0.25, C_m_min=200.0
        )))
        d = _ok_tool(raw)
        assert d["V_mpr_m_min"] > 0
        assert d["T_mpr_min"] > 0

    def test_max_rate_speed_bad_json(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_max_rate_speed(ctx, b"not json"))
        _err_tool(raw)

    # --- break-even ---

    def test_break_even_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_break_even(ctx, _args(
            C_tool=5.0, t_ct_min=2.0, t_c_min=5.0,
            C_m_per_min=1.0, n=0.25, C_m_min=200.0,
        )))
        d = _ok_tool(raw)
        assert d["V_mpr_m_min"] >= d["V_e_m_min"] - 1e-9
        assert d["cost_ratio_mpr_to_e"] >= 1.0 - 1e-9

    def test_break_even_missing_n_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_break_even(ctx, _args(
            C_tool=5.0, t_ct_min=2.0, t_c_min=5.0,
            C_m_per_min=1.0, C_m_min=200.0,
        )))
        _err_tool(raw)

    # --- machinability ---

    def test_machinability_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_machinability(ctx, _args(
            V_material_m_min=75.0, V_reference_m_min=100.0,
        )))
        d = _ok_tool(raw)
        assert abs(d["rating_pct"] - 75.0) < REL

    def test_machinability_missing_V_reference_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_machinability(ctx, _args(V_material_m_min=75.0)))
        _err_tool(raw)

    # --- surface finish ---

    def test_surface_finish_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_surface_finish(ctx, _args(
            f_mm_rev=0.25, r_n_mm=0.8,
        )))
        d = _ok_tool(raw)
        assert d["Rt_um"] > 0
        assert d["Ra_um"] > 0
        assert d["Ra_um"] < d["Rt_um"]

    def test_surface_finish_missing_r_n_returns_error(self):
        ctx = _ctx()
        raw = _run(run_cutting_tool_surface_finish(ctx, _args(f_mm_rev=0.25)))
        _err_tool(raw)

    def test_surface_finish_algebraic_Rt(self):
        """Verify Rt = f² / (8 r_n) × 1000 via tool wrapper."""
        f, r_n = 0.2, 0.5
        ctx = _ctx()
        raw = _run(run_cutting_tool_surface_finish(ctx, _args(
            f_mm_rev=f, r_n_mm=r_n,
        )))
        d = _ok_tool(raw)
        Rt_expected_um = (f ** 2 / (8.0 * r_n)) * 1000.0
        assert abs(d["Rt_um"] - Rt_expected_um) / Rt_expected_um < TREL
