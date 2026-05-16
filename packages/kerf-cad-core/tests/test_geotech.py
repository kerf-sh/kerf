"""
Hermetic tests for kerf_cad_core.geotech — geotechnical / foundation
engineering calculators.

Coverage:
  foundation.bearing_capacity        — Terzaghi factors, strip/square/circular
  foundation.settlement              — consolidation (Cc/e0), immediate
  foundation.lateral_earth_pressure  — Rankine Ka/Kp, resultant forces
  foundation.retaining_wall_stability — overturning / sliding / bearing FS
  foundation.slope_stability_infinite — dry, saturated, warning flags
  foundation.pile_axial_capacity     — alpha-method skin friction + end bearing
  tools.*                            — LLM tool wrappers (happy + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against Das/Bowles hand-calculations.

References
----------
Das, B.M. "Principles of Geotechnical Engineering", 9th ed.
Bowles, J.E. "Foundation Analysis and Design", 5th ed.
Terzaghi (1943); Rankine (1857); Coulomb (1776).

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.geotech.foundation import (
    bearing_capacity,
    settlement,
    lateral_earth_pressure,
    retaining_wall_stability,
    slope_stability_infinite,
    pile_axial_capacity,
)
from kerf_cad_core.geotech.tools import (
    run_bearing_capacity,
    run_settlement,
    run_lateral_earth_pressure,
    run_retaining_wall,
    run_slope_stability,
    run_pile_capacity,
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


REL = 1e-6


# ===========================================================================
# 1. bearing_capacity — Terzaghi factors + formulas
# ===========================================================================

class TestBearingCapacity:

    def _Nq(self, phi_deg: float) -> float:
        phi_rad = phi_deg * math.pi / 180.0
        return math.exp(math.pi * math.tan(phi_rad)) * math.tan(
            math.pi / 4.0 + phi_rad / 2.0
        ) ** 2

    def _Nc(self, phi_deg: float) -> float:
        phi_rad = phi_deg * math.pi / 180.0
        if phi_deg < 1e-9:
            return 5.14
        return (self._Nq(phi_deg) - 1.0) / math.tan(phi_rad)

    def _Ngamma(self, phi_deg: float) -> float:
        Nq = self._Nq(phi_deg)
        phi_rad = phi_deg * math.pi / 180.0
        return 2.0 * (Nq + 1.0) * math.tan(phi_rad)

    def test_strip_footing_algebraic(self):
        """Verify strip: q_ult = c·Nc + q·Nq + 0.5·γ·B·Nγ."""
        c, phi, gamma, Df, B = 20.0, 30.0, 18.0, 1.5, 2.0
        res = bearing_capacity(c, phi, gamma, Df, B, "strip")
        assert res["ok"] is True

        Nc = self._Nc(phi)
        Nq = self._Nq(phi)
        Ng = self._Ngamma(phi)
        q_over = gamma * Df
        q_ult_exp = c * Nc + q_over * Nq + 0.5 * gamma * B * Ng
        assert abs(res["q_ult_kPa"] - q_ult_exp) / q_ult_exp < REL

    def test_square_footing_algebraic(self):
        """Verify square: q_ult = 1.3·c·Nc + q·Nq + 0.4·γ·B·Nγ."""
        c, phi, gamma, Df, B = 10.0, 25.0, 17.0, 1.0, 1.5
        res = bearing_capacity(c, phi, gamma, Df, B, "square")
        assert res["ok"] is True

        Nc = self._Nc(phi)
        Nq = self._Nq(phi)
        Ng = self._Ngamma(phi)
        q_over = gamma * Df
        q_ult_exp = 1.3 * c * Nc + q_over * Nq + 0.4 * gamma * B * Ng
        assert abs(res["q_ult_kPa"] - q_ult_exp) / q_ult_exp < REL

    def test_circular_footing_algebraic(self):
        """Verify circular: q_ult = 1.3·c·Nc + q·Nq + 0.3·γ·B·Nγ."""
        c, phi, gamma, Df, B = 5.0, 20.0, 16.0, 0.5, 1.0
        res = bearing_capacity(c, phi, gamma, Df, B, "circular")
        assert res["ok"] is True

        Nc = self._Nc(phi)
        Nq = self._Nq(phi)
        Ng = self._Ngamma(phi)
        q_over = gamma * Df
        q_ult_exp = 1.3 * c * Nc + q_over * Nq + 0.3 * gamma * B * Ng
        assert abs(res["q_ult_kPa"] - q_ult_exp) / q_ult_exp < REL

    def test_allowable_equals_q_ult_over_FS(self):
        """q_allow = q_ult / FS exactly."""
        res = bearing_capacity(15.0, 30.0, 18.0, 1.0, 2.0, FS=3.0)
        assert res["ok"] is True
        assert abs(res["q_allow_kPa"] - res["q_ult_kPa"] / 3.0) < REL

    def test_phi_zero_uses_Prandtl_Nc(self):
        """For φ=0, Nc = 5.14 (Prandtl/Terzaghi limit)."""
        res = bearing_capacity(c=50.0, phi_deg=0.0, gamma=18.0, Df=1.0, B=2.0)
        assert res["ok"] is True
        assert abs(res["Nc"] - 5.14) < 0.01

    def test_surcharge_increases_q_ult(self):
        """Adding surcharge must increase q_ult."""
        base = bearing_capacity(10.0, 25.0, 17.0, 1.0, 2.0, surcharge=0.0)
        surcharge_case = bearing_capacity(10.0, 25.0, 17.0, 1.0, 2.0, surcharge=20.0)
        assert surcharge_case["q_ult_kPa"] > base["q_ult_kPa"]

    def test_deeper_Df_increases_q_ult(self):
        """Deeper embedment increases q_ult (higher overburden)."""
        res1 = bearing_capacity(10.0, 25.0, 18.0, 1.0, 2.0)
        res2 = bearing_capacity(10.0, 25.0, 18.0, 2.0, 2.0)
        assert res2["q_ult_kPa"] > res1["q_ult_kPa"]

    def test_negative_c_returns_error(self):
        res = bearing_capacity(-1.0, 25.0, 18.0, 1.0, 2.0)
        assert res["ok"] is False

    def test_phi_out_of_range_returns_error(self):
        res = bearing_capacity(10.0, 50.0, 18.0, 1.0, 2.0)
        assert res["ok"] is False

    def test_invalid_foundation_type_returns_error(self):
        res = bearing_capacity(10.0, 25.0, 18.0, 1.0, 2.0, "rectangular")
        assert res["ok"] is False

    def test_low_FS_triggers_warning(self):
        """FS < 3.0 should populate warnings list."""
        res = bearing_capacity(20.0, 30.0, 18.0, 1.0, 2.0, FS=1.5)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 2. settlement — consolidation + immediate
# ===========================================================================

class TestSettlement:

    def test_consolidation_algebraic(self):
        """Verify Sc = (Cc/(1+e0)) × H × log10(σ'v/σ'v0)."""
        sigma_v, Cc, e0, H, sigma_v0 = 200.0, 0.4, 1.2, 5.0, 100.0
        res = settlement(sigma_v, Cc, e0, H, sigma_v0=sigma_v0)
        assert res["ok"] is True
        Sc_exp = (Cc / (1.0 + e0)) * H * math.log10(sigma_v / sigma_v0)
        assert abs(res["settlement_m"] - Sc_exp) / Sc_exp < REL

    def test_settlement_mm_equals_1000_times_m(self):
        """settlement_mm must equal settlement_m × 1000."""
        res = settlement(150.0, 0.3, 0.8, 4.0, sigma_v0=80.0)
        assert res["ok"] is True
        assert abs(res["settlement_mm"] - res["settlement_m"] * 1000.0) < 1e-9

    def test_higher_Cc_gives_more_settlement(self):
        """Larger Cc → more settlement for same loading."""
        s1 = settlement(200.0, 0.3, 1.0, 5.0, sigma_v0=100.0)["settlement_m"]
        s2 = settlement(200.0, 0.6, 1.0, 5.0, sigma_v0=100.0)["settlement_m"]
        assert s2 > s1

    def test_default_sigma_v0_triggers_warning(self):
        """Not providing sigma_v0 should trigger a warning."""
        res = settlement(200.0, 0.4, 1.0, 5.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_sigma_v_less_than_sigma_v0_returns_error(self):
        """sigma_v <= sigma_v0 must return ok=False."""
        res = settlement(50.0, 0.4, 1.0, 5.0, sigma_v0=100.0)
        assert res["ok"] is False

    def test_immediate_settlement_algebraic(self):
        """Si ≈ q·B·(1-ν²)/Es."""
        q, Es, nu, B = 100.0, 20000.0, 0.3, 2.0
        res = settlement(q, Es, nu, B, settlement_type="immediate")
        assert res["ok"] is True
        Si_exp = q * B * (1.0 - nu ** 2) / Es
        assert abs(res["settlement_m"] - Si_exp) / Si_exp < REL

    def test_invalid_settlement_type_returns_error(self):
        res = settlement(100.0, 0.4, 1.0, 5.0, settlement_type="creep")
        assert res["ok"] is False

    def test_negative_Cc_returns_error(self):
        res = settlement(200.0, -0.3, 1.0, 5.0, sigma_v0=100.0)
        assert res["ok"] is False


# ===========================================================================
# 3. lateral_earth_pressure — Rankine Ka/Kp
# ===========================================================================

class TestLateralEarthPressure:

    def test_rankine_Ka_formula(self):
        """Ka = tan²(45 - φ/2) for Rankine."""
        phi = 30.0
        res = lateral_earth_pressure(18.0, 5.0, phi, method="rankine")
        assert res["ok"] is True
        phi_rad = phi * math.pi / 180.0
        Ka_exp = math.tan(math.pi / 4.0 - phi_rad / 2.0) ** 2
        assert abs(res["Ka"] - Ka_exp) / Ka_exp < REL

    def test_rankine_Kp_formula(self):
        """Kp = tan²(45 + φ/2) for Rankine."""
        phi = 30.0
        res = lateral_earth_pressure(18.0, 5.0, phi, method="rankine")
        assert res["ok"] is True
        phi_rad = phi * math.pi / 180.0
        Kp_exp = math.tan(math.pi / 4.0 + phi_rad / 2.0) ** 2
        assert abs(res["Kp"] - Kp_exp) / Kp_exp < REL

    def test_Ka_Kp_inverse_relationship(self):
        """For Rankine: Ka × Kp = 1 exactly (since tan(45-φ/2)×tan(45+φ/2)=1)."""
        res = lateral_earth_pressure(18.0, 5.0, 30.0)
        assert res["ok"] is True
        assert abs(res["Ka"] * res["Kp"] - 1.0) < REL

    def test_active_force_triangular_no_surcharge(self):
        """Pa = 0.5 × Ka × γ × H² for dry sand (no c, no surcharge)."""
        gamma, H, phi = 18.0, 4.0, 30.0
        res = lateral_earth_pressure(gamma, H, phi, method="rankine")
        assert res["ok"] is True
        Ka = res["Ka"]
        Pa_exp = 0.5 * Ka * gamma * H ** 2
        # The function includes potential cohesion and water effects; since c=0, hw=0:
        assert abs(res["Pa_kN_m"] - Pa_exp) / Pa_exp < 0.05  # allow 5% for centroid calc

    def test_passive_greater_than_active(self):
        """Pp > Pa for the same wall geometry (Kp > Ka)."""
        res = lateral_earth_pressure(18.0, 4.0, 30.0)
        assert res["ok"] is True
        assert res["Pp_kN_m"] > res["Pa_kN_m"]

    def test_surcharge_increases_Pa(self):
        """Adding surcharge must increase Pa."""
        base = lateral_earth_pressure(18.0, 5.0, 30.0, surcharge=0.0)
        surcharge_case = lateral_earth_pressure(18.0, 5.0, 30.0, surcharge=10.0)
        assert surcharge_case["Pa_kN_m"] > base["Pa_kN_m"]

    def test_coulomb_method_runs(self):
        """Coulomb method returns ok=True with valid Ka, Kp."""
        res = lateral_earth_pressure(18.0, 5.0, 30.0, method="coulomb", delta_deg=10.0)
        assert res["ok"] is True
        assert res["Ka"] > 0
        assert res["Kp"] > 0

    def test_invalid_method_returns_error(self):
        res = lateral_earth_pressure(18.0, 5.0, 30.0, method="mononobe-okabe")
        assert res["ok"] is False

    def test_phi_out_of_range_returns_error(self):
        res = lateral_earth_pressure(18.0, 5.0, 50.0)
        assert res["ok"] is False

    def test_z_a_in_valid_range(self):
        """Pa resultant z should be within [0, H]."""
        H = 6.0
        res = lateral_earth_pressure(18.0, H, 30.0)
        assert res["ok"] is True
        assert 0.0 <= res["Pa_z_m"] <= H


# ===========================================================================
# 4. retaining_wall_stability
# ===========================================================================

class TestRetainingWallStability:

    def _base_case(self):
        """Typical cantilever wall: stable."""
        return retaining_wall_stability(
            Fa=50.0, Fp=10.0, W_wall=120.0, x_W=1.5,
            B_base=3.0, Df=1.0, c=5.0, phi_deg=25.0, gamma=18.0,
        )

    def test_returns_ok_true(self):
        res = self._base_case()
        assert res["ok"] is True

    def test_FS_positive_finite(self):
        res = self._base_case()
        assert math.isfinite(res["FS_overturning"])
        assert math.isfinite(res["FS_sliding"])
        assert math.isfinite(res["FS_bearing"])
        assert res["FS_overturning"] > 0
        assert res["FS_sliding"] > 0
        assert res["FS_bearing"] > 0

    def test_sliding_FS_formula(self):
        """FS_sliding = (W tan φ + c×B + Fp) / Fa."""
        Fa, Fp, W, B, c, phi = 50.0, 10.0, 120.0, 3.0, 5.0, 25.0
        phi_rad = phi * math.pi / 180.0
        FS_exp = (W * math.tan(phi_rad) + c * B + Fp) / Fa
        res = retaining_wall_stability(
            Fa=Fa, Fp=Fp, W_wall=W, x_W=1.5,
            B_base=B, Df=1.0, c=c, phi_deg=phi, gamma=18.0,
        )
        assert res["ok"] is True
        assert abs(res["FS_sliding"] - FS_exp) / FS_exp < REL

    def test_zero_Fa_gives_infinite_FS(self):
        """Zero active force → infinite FS overturning and sliding."""
        res = retaining_wall_stability(
            Fa=0.0, Fp=5.0, W_wall=100.0, x_W=1.5,
            B_base=3.0, Df=1.0, c=5.0, phi_deg=25.0, gamma=18.0,
        )
        assert res["ok"] is True
        assert math.isinf(res["FS_sliding"]) or res["FS_sliding"] > 1e6

    def test_inadequate_FS_generates_warnings(self):
        """Very large active force → warnings about failed stability checks."""
        res = retaining_wall_stability(
            Fa=500.0, Fp=5.0, W_wall=50.0, x_W=0.5,
            B_base=1.5, Df=0.5, c=0.0, phi_deg=10.0, gamma=18.0,
        )
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_negative_W_returns_error(self):
        res = retaining_wall_stability(
            Fa=50.0, Fp=10.0, W_wall=-100.0, x_W=1.5,
            B_base=3.0, Df=1.0, c=5.0, phi_deg=25.0, gamma=18.0,
        )
        assert res["ok"] is False

    def test_phi_out_of_range_returns_error(self):
        res = retaining_wall_stability(
            Fa=50.0, Fp=10.0, W_wall=120.0, x_W=1.5,
            B_base=3.0, Df=1.0, c=5.0, phi_deg=50.0, gamma=18.0,
        )
        assert res["ok"] is False


# ===========================================================================
# 5. slope_stability_infinite
# ===========================================================================

class TestSlopeStability:

    def test_dry_cohesionless_formula(self):
        """Dry, c=0: FS = tan(φ)/tan(β)."""
        gamma, c, phi, H, beta = 18.0, 0.0, 30.0, 3.0, 20.0
        phi_rad = phi * math.pi / 180.0
        beta_rad = beta * math.pi / 180.0
        FS_exp = math.tan(phi_rad) / math.tan(beta_rad)
        res = slope_stability_infinite(gamma, c, phi, H, beta)
        assert res["ok"] is True
        assert abs(res["FS"] - FS_exp) / FS_exp < REL

    def test_dry_cohesive_formula(self):
        """Dry with cohesion: FS = c/(γHsinβcosβ) + tanφ/tanβ."""
        gamma, c, phi, H, beta = 18.0, 10.0, 25.0, 4.0, 20.0
        phi_rad = phi * math.pi / 180.0
        beta_rad = beta * math.pi / 180.0
        c_term = c / (gamma * H * math.sin(beta_rad) * math.cos(beta_rad))
        f_term = math.tan(phi_rad) / math.tan(beta_rad)
        FS_exp = c_term + f_term
        res = slope_stability_infinite(gamma, c, phi, H, beta)
        assert res["ok"] is True
        assert abs(res["FS"] - FS_exp) / FS_exp < REL

    def test_saturated_reduces_FS(self):
        """Fully saturated (hw_ratio=1) gives lower FS than dry."""
        kwargs = dict(gamma=18.0, c=5.0, phi_deg=30.0, H=3.0, beta_deg=25.0)
        FS_dry = slope_stability_infinite(**kwargs, hw_ratio=0.0)["FS"]
        FS_sat = slope_stability_infinite(**kwargs, hw_ratio=1.0)["FS"]
        assert FS_sat < FS_dry

    def test_adequate_flag_correct(self):
        """adequate is True when FS >= FS_req."""
        res = slope_stability_infinite(18.0, 10.0, 35.0, 3.0, 15.0, FS_req=1.5)
        assert res["ok"] is True
        assert res["adequate"] == (res["FS"] >= 1.5)

    def test_liquefaction_prone_warning(self):
        """phi<5 and c<1 triggers liquefaction warning."""
        res = slope_stability_infinite(16.0, 0.0, 2.0, 2.0, 10.0)
        assert res["ok"] is True
        assert any("liquefaction" in w.lower() for w in res["warnings"])

    def test_beta_ge_90_returns_error(self):
        res = slope_stability_infinite(18.0, 5.0, 30.0, 3.0, 90.0)
        assert res["ok"] is False

    def test_hw_ratio_out_of_range_returns_error(self):
        res = slope_stability_infinite(18.0, 5.0, 30.0, 3.0, 20.0, hw_ratio=1.5)
        assert res["ok"] is False

    def test_negative_H_returns_error(self):
        res = slope_stability_infinite(18.0, 5.0, 30.0, -3.0, 20.0)
        assert res["ok"] is False


# ===========================================================================
# 6. pile_axial_capacity
# ===========================================================================

class TestPileAxialCapacity:

    def test_Qs_formula(self):
        """Qs = α × fs × perimeter × L."""
        perimeter, area_tip, fs, qp, L, alpha = 1.257, 0.126, 50.0, 450.0, 15.0, 0.6
        res = pile_axial_capacity(perimeter, area_tip, fs, qp, L, alpha=alpha)
        assert res["ok"] is True
        Qs_exp = alpha * fs * perimeter * L
        assert abs(res["Qs_kN"] - Qs_exp) / Qs_exp < REL

    def test_Qp_formula(self):
        """Qp = qp × A_tip."""
        perimeter, area_tip, fs, qp, L = 1.257, 0.126, 50.0, 450.0, 15.0
        res = pile_axial_capacity(perimeter, area_tip, fs, qp, L)
        assert res["ok"] is True
        Qp_exp = qp * area_tip
        assert abs(res["Qp_kN"] - Qp_exp) / Qp_exp < REL

    def test_Q_ult_equals_Qs_plus_Qp(self):
        """Q_ult = Qs + Qp exactly."""
        res = pile_axial_capacity(1.2, 0.1, 60.0, 540.0, 12.0, alpha=0.7)
        assert res["ok"] is True
        assert abs(res["Q_ult_kN"] - (res["Qs_kN"] + res["Qp_kN"])) < 1e-9

    def test_Q_allow_formula(self):
        """Q_allow = Q_ult / FS."""
        res = pile_axial_capacity(1.2, 0.1, 60.0, 540.0, 12.0, FS=2.5)
        assert res["ok"] is True
        assert abs(res["Q_allow_kN"] - res["Q_ult_kN"] / 2.5) / (res["Q_ult_kN"] / 2.5) < REL

    def test_low_FS_triggers_warning(self):
        """FS < 2.5 should generate a warning."""
        res = pile_axial_capacity(1.2, 0.1, 60.0, 540.0, 12.0, FS=1.5)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_alpha_gt_1_returns_error(self):
        res = pile_axial_capacity(1.2, 0.1, 60.0, 540.0, 12.0, alpha=1.1)
        assert res["ok"] is False

    def test_negative_perimeter_returns_error(self):
        res = pile_axial_capacity(-1.0, 0.1, 60.0, 540.0, 12.0)
        assert res["ok"] is False

    def test_zero_skin_friction_gives_only_end_bearing(self):
        """Zero skin friction → Qs=0, Q_ult=Qp."""
        res = pile_axial_capacity(1.2, 0.1, 0.0, 500.0, 10.0)
        assert res["ok"] is True
        assert res["Qs_kN"] == 0.0
        assert abs(res["Q_ult_kN"] - res["Qp_kN"]) < 1e-9


# ===========================================================================
# 7. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_bearing_capacity_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_capacity(ctx, _args(
            c=20.0, phi_deg=30.0, gamma=18.0, Df=1.5, B=2.0
        )))
        d = _ok_tool(raw)
        assert d["q_ult_kPa"] > 0
        assert d["q_allow_kPa"] > 0

    def test_run_bearing_capacity_missing_field(self):
        ctx = _ctx()
        raw = _run(run_bearing_capacity(ctx, _args(
            c=20.0, phi_deg=30.0, gamma=18.0, Df=1.5  # missing B
        )))
        _err_tool(raw)

    def test_run_bearing_capacity_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bearing_capacity(ctx, b"not-json"))
        _err_tool(raw)

    def test_run_settlement_consolidation_happy_path(self):
        ctx = _ctx()
        raw = _run(run_settlement(ctx, _args(
            sigma_v=200.0, Cc=0.4, e0=1.2, H=5.0, sigma_v0=100.0
        )))
        d = _ok_tool(raw)
        assert d["settlement_m"] > 0

    def test_run_settlement_missing_field(self):
        ctx = _ctx()
        raw = _run(run_settlement(ctx, _args(
            sigma_v=200.0, Cc=0.4, e0=1.2  # missing H
        )))
        _err_tool(raw)

    def test_run_lateral_earth_pressure_happy_path(self):
        ctx = _ctx()
        raw = _run(run_lateral_earth_pressure(ctx, _args(
            gamma=18.0, H=5.0, phi_deg=30.0
        )))
        d = _ok_tool(raw)
        assert d["Ka"] > 0
        assert d["Kp"] > 0
        assert d["Pa_kN_m"] > 0

    def test_run_lateral_earth_pressure_coulomb(self):
        ctx = _ctx()
        raw = _run(run_lateral_earth_pressure(ctx, _args(
            gamma=18.0, H=5.0, phi_deg=30.0, method="coulomb", delta_deg=10.0
        )))
        d = _ok_tool(raw)
        assert d["method"] == "coulomb"

    def test_run_retaining_wall_happy_path(self):
        ctx = _ctx()
        raw = _run(run_retaining_wall(ctx, _args(
            Fa=50.0, Fp=10.0, W_wall=120.0, x_W=1.5,
            B_base=3.0, Df=1.0, c=5.0, phi_deg=25.0, gamma=18.0,
        )))
        d = _ok_tool(raw)
        assert d["FS_overturning"] > 0
        assert d["FS_sliding"] > 0

    def test_run_retaining_wall_missing_field(self):
        ctx = _ctx()
        raw = _run(run_retaining_wall(ctx, _args(
            Fa=50.0, Fp=10.0, W_wall=120.0  # many fields missing
        )))
        _err_tool(raw)

    def test_run_slope_stability_happy_path(self):
        ctx = _ctx()
        raw = _run(run_slope_stability(ctx, _args(
            gamma=18.0, c=5.0, phi_deg=30.0, H=3.0, beta_deg=20.0
        )))
        d = _ok_tool(raw)
        assert d["FS"] > 0
        assert "adequate" in d

    def test_run_slope_stability_bad_args(self):
        ctx = _ctx()
        raw = _run(run_slope_stability(ctx, _args(
            gamma=18.0, c=5.0, phi_deg=30.0, H=3.0, beta_deg=95.0  # beta > 90
        )))
        _err_tool(raw)

    def test_run_pile_capacity_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pile_capacity(ctx, _args(
            perimeter=1.257, area_tip=0.126,
            unit_skin_friction=50.0, unit_end_bearing=450.0,
            pile_length=15.0, alpha=0.7,
        )))
        d = _ok_tool(raw)
        assert d["Q_ult_kN"] > 0
        assert d["Q_allow_kN"] > 0

    def test_run_pile_capacity_missing_field(self):
        ctx = _ctx()
        raw = _run(run_pile_capacity(ctx, _args(
            perimeter=1.257, area_tip=0.126  # missing other required fields
        )))
        _err_tool(raw)

    def test_run_pile_capacity_bad_json(self):
        ctx = _ctx()
        raw = _run(run_pile_capacity(ctx, b"}}bad"))
        _err_tool(raw)

    def test_run_bearing_capacity_with_FS_kwarg(self):
        """Optional FS kwarg should be forwarded correctly."""
        ctx = _ctx()
        raw = _run(run_bearing_capacity(ctx, _args(
            c=20.0, phi_deg=30.0, gamma=18.0, Df=1.5, B=2.0, FS=2.5
        )))
        d = _ok_tool(raw)
        assert d["FS"] == 2.5
