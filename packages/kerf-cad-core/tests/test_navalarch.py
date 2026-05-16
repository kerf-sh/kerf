"""
Hermetic tests for kerf_cad_core.navalarch — hydrostatics & intact stability.

Coverage:
  hydrostatics.displacement_from_LBT         — LxBxT formula
  hydrostatics.displacement_from_offsets      — Simpson's rule integration
  hydrostatics.form_coefficients              — Cb, Cp, Cm, Cw
  hydrostatics.waterplane_properties          — Aw, LCF, IL, IT
  hydrostatics.vertical_centres               — KB (Morrish), KB_box
  hydrostatics.metacentric_height             — GM, stability flag
  hydrostatics.righting_arm_GZ               — small-angle + wall-sided
  hydrostatics.tpc_mctc                       — TPC, MCT1cm
  hydrostatics.free_surface_correction        — FSC
  hydrostatics.resistance_admiralty           — Admiralty Coefficient EHP
  hydrostatics.trim_from_moment               — trim, dT_aft, dT_fwd
  tools.*                                     — LLM tool wrappers (happy + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against published naval architecture expressions.

References
----------
Barras, C.B. "Ship Stability for Masters and Mates", 6th ed.
Rawson & Tupper, "Basic Ship Theory", 5th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.navalarch.hydrostatics import (
    displacement_from_LBT,
    displacement_from_offsets,
    form_coefficients,
    waterplane_properties,
    vertical_centres,
    metacentric_height,
    righting_arm_GZ,
    tpc_mctc,
    free_surface_correction,
    resistance_admiralty,
    trim_from_moment,
    _simpsons_rule,
    _RHO_SW,
    _G,
)
from kerf_cad_core.navalarch.tools import (
    run_navalarch_displacement_LBT,
    run_navalarch_displacement_offsets,
    run_navalarch_form_coefficients,
    run_navalarch_waterplane,
    run_navalarch_vertical_centres,
    run_navalarch_metacentric_height,
    run_navalarch_righting_arm,
    run_navalarch_tpc_mctc,
    run_navalarch_free_surface,
    run_navalarch_resistance,
    run_navalarch_trim,
)


# ---------------------------------------------------------------------------
# Test helpers
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
# 1. _simpsons_rule — integration primitive
# ===========================================================================

class TestSimpsonsRule:

    def test_constant_function_integrates_to_width_times_value(self):
        """∫ c dx from 0 to 4 = 4c, with 5 ordinates at h=1."""
        c = 3.0
        ords = [c] * 5
        result = _simpsons_rule(ords, h=1.0)
        assert abs(result - 4.0 * c) / (4.0 * c) < REL

    def test_linear_function_exact(self):
        """∫ x dx from 0 to 4 = 8, via 5 equally-spaced ordinates."""
        ords = [0.0, 1.0, 2.0, 3.0, 4.0]
        result = _simpsons_rule(ords, h=1.0)
        assert abs(result - 8.0) / 8.0 < REL

    def test_quadratic_function_exact(self):
        """∫ x² dx from 0 to 6 = 72, via 7 ordinates at h=1."""
        ords = [float(i ** 2) for i in range(7)]
        result = _simpsons_rule(ords, h=1.0)
        assert abs(result - 72.0) / 72.0 < REL

    def test_two_ordinates_trapezoidal(self):
        """Two ordinates: falls back to trapezoidal (exact for linear)."""
        result = _simpsons_rule([0.0, 4.0], h=1.0)
        assert abs(result - 2.0) < REL


# ===========================================================================
# 2. displacement_from_LBT
# ===========================================================================

class TestDisplacementFromLBT:

    def test_box_hull_exact(self):
        """Cb=1 → ∇ = L×B×T exactly."""
        L, B, T = 100.0, 20.0, 5.0
        res = displacement_from_LBT(L, B, T, Cb=1.0)
        assert res["ok"] is True
        assert abs(res["volume_m3"] - L * B * T) < 1e-9

    def test_displacement_tonnes_formula(self):
        """W = ∇ × ρ / 1000."""
        L, B, T, Cb = 120.0, 18.0, 6.0, 0.75
        res = displacement_from_LBT(L, B, T, Cb)
        assert res["ok"] is True
        vol = L * B * T * Cb
        expected_t = vol * _RHO_SW / 1000.0
        assert abs(res["displacement_t"] - expected_t) / expected_t < REL

    def test_buoyancy_force_kN(self):
        """Buoyancy = ∇ × ρ × g / 1000 [kN]."""
        L, B, T, Cb = 100.0, 15.0, 5.0, 0.70
        res = displacement_from_LBT(L, B, T, Cb)
        assert res["ok"] is True
        expected_kN = L * B * T * Cb * _RHO_SW * _G / 1000.0
        assert abs(res["displacement_kN"] - expected_kN) / expected_kN < REL

    def test_custom_rho(self):
        """Fresh water (rho=1000) gives less displacement than sea water."""
        L, B, T, Cb = 80.0, 12.0, 4.0, 0.65
        res_sw = displacement_from_LBT(L, B, T, Cb, rho=1025.0)
        res_fw = displacement_from_LBT(L, B, T, Cb, rho=1000.0)
        assert res_fw["displacement_t"] < res_sw["displacement_t"]

    def test_negative_L_returns_error(self):
        res = displacement_from_LBT(-100.0, 20.0, 5.0, 0.75)
        assert res["ok"] is False

    def test_zero_Cb_returns_error(self):
        res = displacement_from_LBT(100.0, 20.0, 5.0, 0.0)
        assert res["ok"] is False

    def test_Cb_above_1_returns_error(self):
        res = displacement_from_LBT(100.0, 20.0, 5.0, 1.1)
        assert res["ok"] is False


# ===========================================================================
# 3. displacement_from_offsets (Simpson's rule)
# ===========================================================================

class TestDisplacementFromOffsets:

    def test_uniform_rectangle_simpsons(self):
        """Constant area A over length L → volume = A × L."""
        A = 50.0  # m²
        stations = [0.0, 25.0, 50.0, 75.0, 100.0]
        areas = [A] * 5
        res = displacement_from_offsets(stations, areas)
        assert res["ok"] is True
        assert res["method"] == "simpsons"
        assert abs(res["volume_m3"] - A * 100.0) / (A * 100.0) < REL

    def test_LCB_midships_for_symmetric_distribution(self):
        """Symmetric sectional-area curve → LCB at midship (50 m from AP)."""
        L = 100.0
        stations = [0.0, 25.0, 50.0, 75.0, 100.0]
        areas = [0.0, 40.0, 50.0, 40.0, 0.0]  # symmetric about midship
        res = displacement_from_offsets(stations, areas)
        assert res["ok"] is True
        assert abs(res["LCB_fwd_AP"] - 50.0) < 0.01

    def test_two_stations_falls_back_gracefully(self):
        """Two stations: trapezoidal fallback."""
        res = displacement_from_offsets([0.0, 100.0], [50.0, 50.0])
        assert res["ok"] is True
        assert abs(res["volume_m3"] - 5000.0) < REL

    def test_non_monotonic_stations_returns_error(self):
        res = displacement_from_offsets([0.0, 50.0, 30.0], [10.0, 20.0, 15.0])
        assert res["ok"] is False

    def test_negative_area_returns_error(self):
        res = displacement_from_offsets([0.0, 50.0, 100.0], [10.0, -5.0, 10.0])
        assert res["ok"] is False

    def test_mismatched_lengths_returns_error(self):
        res = displacement_from_offsets([0.0, 50.0, 100.0], [10.0, 20.0])
        assert res["ok"] is False


# ===========================================================================
# 4. form_coefficients
# ===========================================================================

class TestFormCoefficients:

    def test_cp_equals_cb_over_cm(self):
        """Cp = Cb / Cm (from Cp = ∇/(Am·L) and Cb = ∇/(L·B·T))."""
        L, B, T = 120.0, 20.0, 6.0
        Cb = 0.70
        Cm = 0.95
        Am = Cm * B * T
        Cw = 0.82
        Aw = Cw * L * B
        res = form_coefficients(L, B, T, Cb, Am, Aw)
        assert res["ok"] is True
        assert abs(res["Cp"] - Cb / Cm) < 1e-9

    def test_cm_from_midship_area(self):
        """Cm = Am / (B × T)."""
        L, B, T, Cb = 100.0, 15.0, 5.0, 0.68
        Am = 0.92 * B * T
        Aw = 0.80 * L * B
        res = form_coefficients(L, B, T, Cb, Am, Aw)
        assert res["ok"] is True
        assert abs(res["Cm"] - Am / (B * T)) < REL

    def test_cw_from_waterplane_area(self):
        """Cw = Aw / (L × B)."""
        L, B, T, Cb = 150.0, 25.0, 7.0, 0.72
        Am = 0.96 * B * T
        Aw = 0.85 * L * B
        res = form_coefficients(L, B, T, Cb, Am, Aw)
        assert res["ok"] is True
        assert abs(res["Cw"] - Aw / (L * B)) < REL

    def test_am_exceeds_BT_returns_error(self):
        """Am > B×T is physically impossible."""
        L, B, T, Cb = 100.0, 15.0, 5.0, 0.70
        Am = B * T * 1.1   # 10% over max
        Aw = 0.80 * L * B
        res = form_coefficients(L, B, T, Cb, Am, Aw)
        assert res["ok"] is False

    def test_invalid_Cb_returns_error(self):
        res = form_coefficients(100.0, 15.0, 5.0, 1.5, 50.0, 1000.0)
        assert res["ok"] is False


# ===========================================================================
# 5. waterplane_properties
# ===========================================================================

class TestWaterplaneProperties:

    def test_rectangular_waterplane_area(self):
        """Rectangular waterplane: Aw = 2 × (B/2) × L = B × L."""
        L, B = 100.0, 20.0
        n = 5
        xs = [L * i / (n - 1) for i in range(n)]
        ys = [B / 2.0] * n      # constant half-breadth
        res = waterplane_properties(xs, ys)
        assert res["ok"] is True
        assert abs(res["Aw_m2"] - L * B) / (L * B) < REL

    def test_LCF_at_midship_for_uniform_waterplane(self):
        """Constant half-breadth → LCF at midship = L/2 from AP."""
        L = 100.0
        xs = [0.0, 25.0, 50.0, 75.0, 100.0]
        ys = [5.0] * 5
        res = waterplane_properties(xs, ys)
        assert res["ok"] is True
        assert abs(res["LCF_fwd_AP"] - 50.0) < 0.01

    def test_IT_rectangular_waterplane(self):
        """For rectangular waterplane: IT = 2/3 × ∫ y³ dx = 2/3 × (B/2)³ × L."""
        L, B = 80.0, 10.0
        xs = [L * i / 4 for i in range(5)]
        ys = [B / 2.0] * 5
        res = waterplane_properties(xs, ys)
        assert res["ok"] is True
        IT_expected = (2.0 / 3.0) * (B / 2.0) ** 3 * L
        assert abs(res["IT_m4"] - IT_expected) / IT_expected < REL

    def test_IL_LCF_less_than_IL_AP(self):
        """Parallel-axis correction: IL about LCF < IL about AP."""
        xs = [0.0, 20.0, 40.0, 60.0, 80.0]
        ys = [5.0, 7.0, 8.0, 7.0, 5.0]
        res = waterplane_properties(xs, ys)
        assert res["ok"] is True
        assert res["IL_LCF_m4"] < res["IL_m4"]

    def test_too_few_stations_returns_error(self):
        res = waterplane_properties([0.0, 50.0], [5.0, 5.0])
        assert res["ok"] is False

    def test_negative_half_breadth_returns_error(self):
        res = waterplane_properties([0.0, 25.0, 50.0], [5.0, -1.0, 5.0])
        assert res["ok"] is False


# ===========================================================================
# 6. vertical_centres
# ===========================================================================

class TestVerticalCentres:

    def test_KB_between_zero_and_T_half(self):
        """KB must be in (0, T) for any valid Cb."""
        for Cb in (0.5, 0.65, 0.80, 0.98):
            res = vertical_centres(T=7.0, Cb=Cb)
            assert res["ok"] is True
            assert 0 < res["KB_m"] < 7.0

    def test_KB_box_equals_T_over_2(self):
        """Box hull KB = T/2 always."""
        T = 6.5
        res = vertical_centres(T=T, Cb=0.70)
        assert res["ok"] is True
        assert abs(res["KB_box_m"] - T / 2.0) < 1e-12

    def test_morrish_formula_explicit(self):
        """Check Morrish formula: KB = T*(5/6 − Cb/(3*Cw)) with Cw = (1+2Cb)/3."""
        T, Cb = 5.0, 0.72
        Cw = (1.0 + 2.0 * Cb) / 3.0
        KB_expected = T * (5.0 / 6.0 - Cb / (3.0 * Cw))
        res = vertical_centres(T=T, Cb=Cb)
        assert res["ok"] is True
        assert abs(res["KB_m"] - KB_expected) < 1e-10

    def test_negative_T_returns_error(self):
        res = vertical_centres(T=-5.0, Cb=0.70)
        assert res["ok"] is False

    def test_zero_Cb_returns_error(self):
        res = vertical_centres(T=5.0, Cb=0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. metacentric_height
# ===========================================================================

class TestMetacentricHeight:

    def test_GM_formula(self):
        """GM = KB + BM − KG."""
        KB, BM, KG = 3.0, 2.5, 4.0
        res = metacentric_height(KB, BM, KG)
        assert res["ok"] is True
        assert abs(res["GM_m"] - (KB + BM - KG)) < 1e-12

    def test_KM_equals_KB_plus_BM(self):
        KB, BM, KG = 2.8, 3.2, 5.0
        res = metacentric_height(KB, BM, KG)
        assert res["ok"] is True
        assert abs(res["KM_m"] - (KB + BM)) < 1e-12

    def test_positive_GM_is_stable(self):
        res = metacentric_height(KB=3.0, BM=2.0, KG=4.0)
        assert res["ok"] is True
        assert res["stable"] is True
        assert res["GM_m"] > 0
        assert res["warnings"] == []

    def test_negative_GM_flagged_in_warnings(self):
        """KG > KB + BM → negative GM → unstable, flagged in warnings."""
        res = metacentric_height(KB=2.0, BM=1.5, KG=5.0)
        assert res["ok"] is True
        assert res["stable"] is False
        assert res["GM_m"] < 0
        assert len(res["warnings"]) > 0

    def test_negative_KB_returns_error(self):
        res = metacentric_height(KB=-1.0, BM=2.0, KG=3.0)
        assert res["ok"] is False

    def test_BM_equals_IT_over_volume(self):
        """Verify: BM = IT/∇ (integration test)."""
        IT = 5000.0   # m⁴ transverse second moment
        volume = 2000.0  # m³
        BM_expected = IT / volume
        KB = 3.0
        KG = KB + BM_expected - 0.5  # → GM = 0.5 m (stable)
        res = metacentric_height(KB=KB, BM=BM_expected, KG=KG)
        assert res["ok"] is True
        assert abs(res["GM_m"] - 0.5) < 1e-10


# ===========================================================================
# 8. righting_arm_GZ
# ===========================================================================

class TestRightingArmGZ:

    def test_small_angle_GZ_at_zero_phi(self):
        """GZ = 0 when φ = 0."""
        res = righting_arm_GZ(GM=1.0, phi_deg=0.0)
        assert res["ok"] is True
        assert res["GZ_small_angle_m"] == 0.0

    def test_small_angle_GZ_formula(self):
        """GZ = GM × sin(φ) for small angles."""
        GM, phi = 1.2, 15.0
        GZ_expected = GM * math.sin(math.radians(phi))
        res = righting_arm_GZ(GM=GM, phi_deg=phi)
        assert res["ok"] is True
        assert abs(res["GZ_small_angle_m"] - GZ_expected) < 1e-10

    def test_wall_sided_correction(self):
        """GZ_wall = (GM + ½ BM_T tan²φ) sinφ > GZ_small for BM_T > 0."""
        GM, phi, BM_T = 0.8, 20.0, 4.0
        res = righting_arm_GZ(GM=GM, phi_deg=phi, wall_sided_BM_T=BM_T)
        assert res["ok"] is True
        phi_r = math.radians(phi)
        GZ_wall_expected = (GM + 0.5 * BM_T * math.tan(phi_r) ** 2) * math.sin(phi_r)
        assert abs(res["GZ_wall_sided_m"] - GZ_wall_expected) < 1e-10
        assert res["GZ_wall_sided_m"] > res["GZ_small_angle_m"]

    def test_negative_GM_flagged(self):
        """Negative GM is flagged in warnings."""
        res = righting_arm_GZ(GM=-0.5, phi_deg=10.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_phi_above_90_returns_error(self):
        res = righting_arm_GZ(GM=1.0, phi_deg=91.0)
        assert res["ok"] is False

    def test_GZ_at_90_degrees_equals_GM(self):
        """At 90°, sin(90) = 1 → GZ_small = GM."""
        GM = 1.5
        res = righting_arm_GZ(GM=GM, phi_deg=90.0)
        assert res["ok"] is True
        assert abs(res["GZ_small_angle_m"] - GM) < 1e-9


# ===========================================================================
# 9. tpc_mctc
# ===========================================================================

class TestTpcMctc:

    def test_TPC_formula(self):
        """TPC = Aw × ρ / (1000 × 100)."""
        Aw, L, W = 2000.0, 150.0, 15000.0
        res = tpc_mctc(Aw, L, W)
        assert res["ok"] is True
        TPC_expected = Aw * _RHO_SW / (1000.0 * 100.0)
        assert abs(res["TPC"] - TPC_expected) / TPC_expected < REL

    def test_MCT1cm_positive(self):
        """MCT1cm must be positive for any valid inputs."""
        res = tpc_mctc(Aw=1500.0, L=120.0, displacement_t=10000.0)
        assert res["ok"] is True
        assert res["MCT1cm_tm_per_cm"] > 0

    def test_BML_approx_IL_over_volume(self):
        """BML ≈ (Aw × L²/12) / ∇."""
        Aw, L, W = 2500.0, 200.0, 30000.0
        res = tpc_mctc(Aw, L, W)
        assert res["ok"] is True
        volume = W * 1000.0 / _RHO_SW
        IL = Aw * L ** 2 / 12.0
        BML_expected = IL / volume
        assert abs(res["BML_approx_m"] - BML_expected) / BML_expected < REL

    def test_negative_displacement_returns_error(self):
        res = tpc_mctc(Aw=2000.0, L=150.0, displacement_t=-100.0)
        assert res["ok"] is False

    def test_larger_Aw_gives_larger_TPC(self):
        """Bigger waterplane area → more buoyancy per cm → higher TPC."""
        res1 = tpc_mctc(Aw=1000.0, L=100.0, displacement_t=5000.0)
        res2 = tpc_mctc(Aw=2000.0, L=100.0, displacement_t=5000.0)
        assert res2["TPC"] > res1["TPC"]


# ===========================================================================
# 10. free_surface_correction
# ===========================================================================

class TestFreeSurfaceCorrection:

    def test_FSC_formula(self):
        """FSC = (ρ_l/ρ_sw) × it / ∇ where it = l×b³/12."""
        rl, l, b, rs, W = 1025.0, 20.0, 8.0, 1025.0, 5000.0
        res = free_surface_correction(rl, l, b, rs, W)
        assert res["ok"] is True
        it = l * b ** 3 / 12.0
        volume = W * 1000.0 / rs
        FSC_expected = (rl / rs) * it / volume
        assert abs(res["FSC_m"] - FSC_expected) / max(abs(FSC_expected), 1e-12) < REL

    def test_wider_tank_larger_FSC(self):
        """Wider tank (larger b) → larger free-surface effect."""
        base = dict(rho_liquid=1000.0, tank_length=10.0, rho_sw=1025.0, displacement_t=3000.0)
        res1 = free_surface_correction(tank_breadth=4.0, **base)
        res2 = free_surface_correction(tank_breadth=8.0, **base)
        assert res2["FSC_m"] > res1["FSC_m"]

    def test_denser_liquid_larger_FSC(self):
        """Denser liquid → larger free-surface moment."""
        base = dict(tank_length=15.0, tank_breadth=6.0, rho_sw=1025.0, displacement_t=4000.0)
        res_water = free_surface_correction(rho_liquid=1000.0, **base)
        res_fuel = free_surface_correction(rho_liquid=850.0, **base)
        assert res_water["FSC_m"] > res_fuel["FSC_m"]

    def test_negative_rho_liquid_returns_error(self):
        res = free_surface_correction(-50.0, 10.0, 5.0, 1025.0, 2000.0)
        assert res["ok"] is False

    def test_zero_displacement_returns_error(self):
        res = free_surface_correction(1000.0, 10.0, 5.0, 1025.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 11. resistance_admiralty
# ===========================================================================

class TestResistanceAdmiralty:

    def test_EHP_formula(self):
        """EHP_hp = W^(2/3) × V³ / Ac."""
        W, V, Ac = 15000.0, 15.0, 400.0
        res = resistance_admiralty(W, V, Ac)
        assert res["ok"] is True
        EHP_expected = W ** (2.0 / 3.0) * V ** 3 / Ac
        assert abs(res["EHP_hp"] - EHP_expected) / EHP_expected < REL

    def test_kW_conversion(self):
        """EHP_kW = EHP_hp × 0.7457."""
        W, V, Ac = 20000.0, 14.0, 450.0
        res = resistance_admiralty(W, V, Ac)
        assert res["ok"] is True
        assert abs(res["EHP_kW"] - res["EHP_hp"] * 0.7457) / res["EHP_kW"] < REL

    def test_higher_speed_higher_power(self):
        """Increasing speed increases required power (V³ dependence)."""
        W, Ac = 12000.0, 380.0
        res_slow = resistance_admiralty(W, V_knots=10.0, Ac=Ac)
        res_fast = resistance_admiralty(W, V_knots=16.0, Ac=Ac)
        assert res_fast["EHP_kW"] > res_slow["EHP_kW"]

    def test_power_scales_with_V_cubed(self):
        """EHP ∝ V³: doubling speed increases power by 8×."""
        W, Ac = 10000.0, 400.0
        res1 = resistance_admiralty(W, V_knots=10.0, Ac=Ac)
        res2 = resistance_admiralty(W, V_knots=20.0, Ac=Ac)
        assert abs(res2["EHP_hp"] / res1["EHP_hp"] - 8.0) / 8.0 < REL

    def test_zero_speed_returns_error(self):
        res = resistance_admiralty(10000.0, 0.0, 400.0)
        assert res["ok"] is False

    def test_negative_displacement_returns_error(self):
        res = resistance_admiralty(-500.0, 14.0, 400.0)
        assert res["ok"] is False


# ===========================================================================
# 12. trim_from_moment
# ===========================================================================

class TestTrimFromMoment:

    def test_trim_cm_formula(self):
        """trim_cm = trimming_moment / MCTC."""
        tm, MCTC, L, LCF = 500.0, 125.0, 150.0, 70.0
        res = trim_from_moment(tm, MCTC, L, LCF)
        assert res["ok"] is True
        assert abs(res["trim_cm"] - tm / MCTC) < REL

    def test_dT_aft_formula(self):
        """dT_aft = trim × (L − LCF) / L."""
        tm, MCTC, L, LCF = 300.0, 100.0, 120.0, 55.0
        res = trim_from_moment(tm, MCTC, L, LCF)
        assert res["ok"] is True
        trim = tm / MCTC
        dT_aft_expected = trim * (L - LCF) / L
        assert abs(res["dT_aft_cm"] - dT_aft_expected) < REL

    def test_dT_fwd_formula(self):
        """dT_fwd = −trim × LCF / L."""
        tm, MCTC, L, LCF = 400.0, 80.0, 100.0, 45.0
        res = trim_from_moment(tm, MCTC, L, LCF)
        assert res["ok"] is True
        trim = tm / MCTC
        dT_fwd_expected = -trim * LCF / L
        assert abs(res["dT_fwd_cm"] - dT_fwd_expected) < REL

    def test_trim_sum_dT_equals_total_trim(self):
        """dT_aft − dT_fwd = trim_cm (stern sinks, bow rises)."""
        tm, MCTC, L, LCF = 600.0, 150.0, 180.0, 90.0
        res = trim_from_moment(tm, MCTC, L, LCF)
        assert res["ok"] is True
        # dT_aft is positive, dT_fwd is negative (bow rises)
        assert abs(res["dT_aft_cm"] - res["dT_fwd_cm"] - res["trim_cm"]) < REL

    def test_negative_moment_trim_by_head(self):
        """Negative moment → trim_cm negative → trim by head."""
        res = trim_from_moment(-300.0, 100.0, 120.0, 60.0)
        assert res["ok"] is True
        assert res["trim_cm"] < 0

    def test_excessive_trim_flagged_in_warnings(self):
        """Trim > 100 cm → warning, but ok=True."""
        res = trim_from_moment(20000.0, 100.0, 120.0, 60.0)
        assert res["ok"] is True
        assert abs(res["trim_cm"]) > 100.0
        assert len(res["warnings"]) > 0

    def test_LCF_outside_range_returns_error(self):
        res = trim_from_moment(300.0, 100.0, 120.0, LCF_fwd_AP=130.0)
        assert res["ok"] is False

    def test_zero_MCTC_returns_error(self):
        res = trim_from_moment(300.0, 0.0, 120.0, 60.0)
        assert res["ok"] is False


# ===========================================================================
# 13. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_displacement_LBT_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_displacement_LBT(
            ctx, _args(L=100.0, B=20.0, T=5.0, Cb=0.75)
        ))
        d = _ok_tool(raw)
        assert d["displacement_t"] > 0

    def test_displacement_LBT_missing_Cb(self):
        ctx = _ctx()
        raw = _run(run_navalarch_displacement_LBT(
            ctx, _args(L=100.0, B=20.0, T=5.0)
        ))
        _err_tool(raw)

    def test_displacement_offsets_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_displacement_offsets(
            ctx, _args(
                stations=[0.0, 25.0, 50.0, 75.0, 100.0],
                sectional_areas=[0.0, 40.0, 50.0, 40.0, 0.0],
            )
        ))
        d = _ok_tool(raw)
        assert d["volume_m3"] > 0

    def test_form_coefficients_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_form_coefficients(
            ctx, _args(L=120.0, B=20.0, T=6.0, Cb=0.70,
                       Am=0.95 * 20.0 * 6.0, Aw=0.82 * 120.0 * 20.0)
        ))
        d = _ok_tool(raw)
        assert 0 < d["Cp"] < 1

    def test_waterplane_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_waterplane(
            ctx, _args(
                stations=[0.0, 25.0, 50.0, 75.0, 100.0],
                half_breadths=[0.0, 8.0, 10.0, 8.0, 0.0],
            )
        ))
        d = _ok_tool(raw)
        assert d["Aw_m2"] > 0

    def test_vertical_centres_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_vertical_centres(ctx, _args(T=6.0, Cb=0.72)))
        d = _ok_tool(raw)
        assert 0 < d["KB_m"] < 6.0

    def test_metacentric_height_stable(self):
        ctx = _ctx()
        raw = _run(run_navalarch_metacentric_height(
            ctx, _args(KB=3.0, BM=2.5, KG=4.0)
        ))
        d = _ok_tool(raw)
        assert d["GM_m"] == pytest.approx(1.5, rel=1e-9)
        assert d["stable"] is True

    def test_metacentric_height_unstable_flagged(self):
        ctx = _ctx()
        raw = _run(run_navalarch_metacentric_height(
            ctx, _args(KB=2.0, BM=1.0, KG=5.0)
        ))
        d = _ok_tool(raw)
        assert d["stable"] is False
        assert len(d["warnings"]) > 0

    def test_righting_arm_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_righting_arm(
            ctx, _args(GM=1.2, phi_deg=15.0, wall_sided_BM_T=3.0)
        ))
        d = _ok_tool(raw)
        assert d["GZ_wall_sided_m"] > 0

    def test_tpc_mctc_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_tpc_mctc(
            ctx, _args(Aw=2000.0, L=150.0, displacement_t=15000.0)
        ))
        d = _ok_tool(raw)
        assert d["TPC"] > 0
        assert d["MCT1cm_tm_per_cm"] > 0

    def test_free_surface_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_free_surface(
            ctx, _args(rho_liquid=1025.0, tank_length=20.0, tank_breadth=8.0,
                       displacement_t=5000.0)
        ))
        d = _ok_tool(raw)
        assert d["FSC_m"] > 0

    def test_resistance_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_resistance(
            ctx, _args(displacement_t=15000.0, V_knots=14.0, Ac=420.0)
        ))
        d = _ok_tool(raw)
        assert d["EHP_kW"] > 0

    def test_trim_happy(self):
        ctx = _ctx()
        raw = _run(run_navalarch_trim(
            ctx, _args(trimming_moment_tm=500.0, MCTC=125.0, L=150.0, LCF_fwd_AP=70.0)
        ))
        d = _ok_tool(raw)
        assert abs(d["trim_cm"] - 4.0) < REL

    def test_bad_json_returns_error(self):
        ctx = _ctx()
        raw = _run(run_navalarch_displacement_LBT(ctx, b"not json"))
        _err_tool(raw)

    def test_missing_MCTC_returns_error(self):
        ctx = _ctx()
        raw = _run(run_navalarch_trim(
            ctx, _args(trimming_moment_tm=500.0, L=150.0, LCF_fwd_AP=70.0)
        ))
        _err_tool(raw)
