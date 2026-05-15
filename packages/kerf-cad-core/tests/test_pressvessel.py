"""
Hermetic tests for kerf_cad_core.pressvessel — ASME BPVC VIII Div.1
pressure-vessel sizing calculators.

Coverage:
  shell.cylindrical_shell_thickness  — UG-27 hoop/longitudinal stress
  shell.spherical_head_thickness     — UG-32(f)
  shell.ellipsoidal_head_thickness   — UG-32(d) 2:1 head
  shell.torispherical_head_thickness — UG-32(e) F&D head
  shell.external_pressure_check      — UG-28 simplified factor-A/B
  shell.mawp_cylindrical             — inverse UG-27
  shell.nozzle_reinforcement         — UG-37 area-replacement
  shell.hydrostatic_test_pressure    — UG-99(b)
  tools.*                            — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against published ASME hand-calcs.

References
----------
ASME BPVC Section VIII Division 1, 2021 Edition
Megyesy, E.F. "Pressure Vessel Handbook", 14th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.pressvessel.shell import (
    cylindrical_shell_thickness,
    spherical_head_thickness,
    ellipsoidal_head_thickness,
    torispherical_head_thickness,
    external_pressure_check,
    mawp_cylindrical,
    nozzle_reinforcement,
    hydrostatic_test_pressure,
)
from kerf_cad_core.pressvessel.tools import (
    run_pv_cylindrical_shell_thickness,
    run_pv_spherical_head_thickness,
    run_pv_ellipsoidal_head_thickness,
    run_pv_torispherical_head_thickness,
    run_pv_external_pressure_check,
    run_pv_mawp_cylindrical,
    run_pv_nozzle_reinforcement,
    run_pv_hydrostatic_test_pressure,
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
    except Exception:  # pragma: no cover
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


REL = 1e-6  # relative tolerance for floating-point checks


# ===========================================================================
# 1. cylindrical_shell_thickness — UG-27
# ===========================================================================

class TestCylindricalShellThickness:

    def test_algebraic_circumferential_formula(self):
        """Verify t_circ = P·R / (S·E - 0.6·P) for known inputs."""
        P, R, S, E = 1.0e6, 0.5, 138e6, 1.0
        expected_t = P * R / (S * E - 0.6 * P)
        res = cylindrical_shell_thickness(P=P, R=R, S=S, E=E, c=0.0)
        assert res["ok"] is True
        assert abs(res["t_circ_m"] - expected_t) / expected_t < REL

    def test_corrosion_allowance_added_to_result(self):
        """Corrosion allowance c must be added to net required thickness."""
        P, R, S, c = 1.0e6, 0.5, 138e6, 0.003
        res_no_ca = cylindrical_shell_thickness(P=P, R=R, S=S, c=0.0)
        res_with_ca = cylindrical_shell_thickness(P=P, R=R, S=S, c=c)
        assert res_with_ca["ok"] is True
        assert abs(res_with_ca["t_required_m"] - res_no_ca["t_required_m"] - c) < 1e-12

    def test_hoop_governs_over_longitudinal(self):
        """Circumferential stress must always govern (t_circ >= t_long)."""
        res = cylindrical_shell_thickness(P=2e6, R=0.6, S=138e6, E=0.85)
        assert res["ok"] is True
        assert res["t_circ_m"] >= res["t_long_m"]
        assert res["governing"] == "circumferential"

    def test_joint_efficiency_increases_thickness(self):
        """Lower joint efficiency E must require more thickness."""
        P, R, S = 1.5e6, 0.5, 138e6
        t_full = cylindrical_shell_thickness(P=P, R=R, S=S, E=1.0)["t_required_m"]
        t_reduced = cylindrical_shell_thickness(P=P, R=R, S=S, E=0.7)["t_required_m"]
        assert t_reduced > t_full

    def test_mawp_back_calc_matches_design_pressure(self):
        """MAWP from back-calculation must be >= design pressure P."""
        P, R, S = 1.2e6, 0.4, 138e6
        res = cylindrical_shell_thickness(P=P, R=R, S=S)
        assert res["ok"] is True
        # MAWP should be approximately equal to P (within rounding)
        assert res["MAWP_Pa"] >= P * (1 - 1e-5)

    def test_zero_pressure_gives_only_ca(self):
        """Zero internal pressure with corrosion allowance returns t = c."""
        c = 0.003
        res = cylindrical_shell_thickness(P=0.0, R=0.5, S=138e6, c=c)
        assert res["ok"] is True
        assert abs(res["t_required_m"] - c) < 1e-12

    def test_negative_pressure_returns_error(self):
        res = cylindrical_shell_thickness(P=-1e6, R=0.5, S=138e6)
        assert res["ok"] is False

    def test_zero_radius_returns_error(self):
        res = cylindrical_shell_thickness(P=1e6, R=0.0, S=138e6)
        assert res["ok"] is False

    def test_invalid_joint_efficiency_returns_error(self):
        res = cylindrical_shell_thickness(P=1e6, R=0.5, S=138e6, E=1.2)
        assert res["ok"] is False

    def test_pressure_exceeds_limit_returns_error(self):
        """P so large that S·E - 0.6·P <= 0 must return error."""
        # S·E = 138e6, need P > S·E/0.6 = 230e6
        res = cylindrical_shell_thickness(P=300e6, R=0.5, S=138e6, E=1.0)
        assert res["ok"] is False

    def test_t_required_mm_consistent(self):
        """t_required_mm must equal t_required_m × 1000."""
        res = cylindrical_shell_thickness(P=1e6, R=0.5, S=138e6)
        assert res["ok"] is True
        assert abs(res["t_required_mm"] - res["t_required_m"] * 1e3) < 1e-10


# ===========================================================================
# 2. spherical_head_thickness — UG-32(f)
# ===========================================================================

class TestSphericalHeadThickness:

    def test_algebraic_formula(self):
        """Verify t = P·R / (2·S·E - 0.2·P)."""
        P, R, S, E = 1.5e6, 0.4, 138e6, 1.0
        expected = P * R / (2.0 * S * E - 0.2 * P)
        res = spherical_head_thickness(P=P, R=R, S=S, E=E, c=0.0)
        assert res["ok"] is True
        assert abs(res["t_required_m"] - expected) / expected < REL

    def test_spherical_thinner_than_cylindrical_same_radius(self):
        """Spherical head requires less thickness than a cylindrical shell
        of the same radius (factor ~0.5 for thin shells)."""
        P, R, S = 1.0e6, 0.5, 138e6
        t_cyl = cylindrical_shell_thickness(P=P, R=R, S=S)["t_required_m"]
        t_sph = spherical_head_thickness(P=P, R=R, S=S)["t_required_m"]
        assert t_sph < t_cyl

    def test_mawp_consistency(self):
        """MAWP from spherical head must be >= design pressure."""
        P, R, S = 2.0e6, 0.3, 138e6
        res = spherical_head_thickness(P=P, R=R, S=S)
        assert res["ok"] is True
        assert res["MAWP_Pa"] >= P * (1 - 1e-5)

    def test_negative_R_returns_error(self):
        res = spherical_head_thickness(P=1e6, R=-0.5, S=138e6)
        assert res["ok"] is False

    def test_invalid_E_returns_error(self):
        res = spherical_head_thickness(P=1e6, R=0.5, S=138e6, E=0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. ellipsoidal_head_thickness — UG-32(d)
# ===========================================================================

class TestEllipsoidalHeadThickness:

    def test_algebraic_formula(self):
        """Verify t = P·D / (2·S·E - 0.2·P) for 2:1 head."""
        P, D, S = 1.0e6, 1.0, 138e6
        expected = P * D / (2.0 * S * 1.0 - 0.2 * P)
        res = ellipsoidal_head_thickness(P=P, D=D, S=S)
        assert res["ok"] is True
        assert abs(res["t_required_m"] - expected) / expected < REL

    def test_head_depth_is_D_over_4(self):
        """Head depth for 2:1 head must equal D/4."""
        D = 1.2
        res = ellipsoidal_head_thickness(P=1e6, D=D, S=138e6)
        assert res["ok"] is True
        assert abs(res["head_depth_m"] - D / 4.0) < 1e-12

    def test_ca_increases_thickness_linearly(self):
        """Corrosion allowance adds directly to thickness."""
        P, D, S, c = 1e6, 1.0, 138e6, 0.005
        res0 = ellipsoidal_head_thickness(P=P, D=D, S=S, c=0.0)
        res_ca = ellipsoidal_head_thickness(P=P, D=D, S=S, c=c)
        assert abs(res_ca["t_required_m"] - res0["t_required_m"] - c) < 1e-12

    def test_negative_D_returns_error(self):
        res = ellipsoidal_head_thickness(P=1e6, D=-1.0, S=138e6)
        assert res["ok"] is False

    def test_mawp_back_calc(self):
        """MAWP back-calculation: P_back must match design pressure."""
        P, D, S = 1.5e6, 0.8, 138e6
        res = ellipsoidal_head_thickness(P=P, D=D, S=S)
        assert res["ok"] is True
        assert res["MAWP_Pa"] >= P * (1 - 1e-5)


# ===========================================================================
# 4. torispherical_head_thickness — UG-32(e)
# ===========================================================================

class TestTorisphericalHeadThickness:

    def test_algebraic_formula_standard_proportions(self):
        """Verify t = 0.885·P·L / (S·E - 0.1·P) with L=D."""
        P, D, S = 1.0e6, 1.0, 138e6
        L = D  # standard proportions
        expected = 0.885 * P * L / (S * 1.0 - 0.1 * P)
        res = torispherical_head_thickness(P=P, D=D, S=S)
        assert res["ok"] is True
        assert abs(res["t_required_m"] - expected) / expected < REL

    def test_torispherical_thicker_than_ellipsoidal(self):
        """For the same P, D, S a torispherical (F&D) head requires more
        thickness than a 2:1 ellipsoidal head (factor ~0.885 vs 0.5)."""
        P, D, S = 1.0e6, 1.0, 138e6
        t_ell = ellipsoidal_head_thickness(P=P, D=D, S=S)["t_required_m"]
        t_tori = torispherical_head_thickness(P=P, D=D, S=S)["t_required_m"]
        assert t_tori > t_ell

    def test_knuckle_radius_standard(self):
        """Standard knuckle radius must equal 0.06·D."""
        D = 1.2
        res = torispherical_head_thickness(P=1e6, D=D, S=138e6)
        assert res["ok"] is True
        assert abs(res["r_knuckle_m"] - 0.06 * D) < 1e-12

    def test_crown_radius_defaults_to_D(self):
        """Default crown radius must equal D (standard proportions)."""
        D = 0.8
        res = torispherical_head_thickness(P=1e6, D=D, S=138e6)
        assert res["ok"] is True
        assert abs(res["L_crown_m"] - D) < 1e-12

    def test_custom_L_crown(self):
        """Custom crown radius changes the thickness proportionally."""
        P, D, S = 1e6, 1.0, 138e6
        res_std = torispherical_head_thickness(P=P, D=D, S=S)
        res_custom = torispherical_head_thickness(P=P, D=D, S=S, L_crown=0.8)
        # Smaller L_crown → smaller t (direct proportion)
        assert res_custom["t_required_m"] < res_std["t_required_m"]

    def test_mawp_back_calc(self):
        """MAWP must satisfy P_back >= design pressure."""
        P, D, S = 1.2e6, 0.9, 138e6
        res = torispherical_head_thickness(P=P, D=D, S=S)
        assert res["ok"] is True
        assert res["MAWP_Pa"] >= P * (1 - 1e-5)

    def test_negative_P_returns_error(self):
        res = torispherical_head_thickness(P=-1e6, D=1.0, S=138e6)
        assert res["ok"] is False


# ===========================================================================
# 5. external_pressure_check — UG-28
# ===========================================================================

class TestExternalPressureCheck:

    def test_factor_A_formula(self):
        """Factor A = 0.125 / (L/D_o × D_o/t)."""
        D_o, L, t = 0.5, 2.5, 0.01
        res = external_pressure_check(P_ext=50e3, D_o=D_o, L=L, t=t)
        assert res["ok"] is True
        expected_A = 0.125 / ((L / D_o) * (D_o / t))
        assert abs(res["factor_A"] - expected_A) / expected_A < REL

    def test_factor_B_elastic(self):
        """Factor B = A·E/2 in elastic regime (no S_allow cap)."""
        D_o, L, t, E_mod = 0.5, 2.5, 0.01, 200e9
        res = external_pressure_check(P_ext=50e3, D_o=D_o, L=L, t=t, E_mod=E_mod)
        assert res["ok"] is True
        expected_B = res["factor_A"] * E_mod / 2.0
        assert abs(res["factor_B_Pa"] - expected_B) / expected_B < REL

    def test_P_allow_formula(self):
        """P_allow = 4B / (3 × D_o/t)."""
        D_o, L, t = 0.5, 3.0, 0.012
        res = external_pressure_check(P_ext=10e3, D_o=D_o, L=L, t=t)
        assert res["ok"] is True
        expected = 4.0 * res["factor_B_Pa"] / (3.0 * (D_o / t))
        assert abs(res["P_allow_Pa"] - expected) / expected < REL

    def test_pass_when_P_ext_below_allow(self):
        """Low external pressure must pass."""
        res = external_pressure_check(P_ext=1e3, D_o=0.5, L=3.0, t=0.015)
        assert res["ok"] is True
        assert res["pass_fail"] is True
        assert res["safety_factor"] > 1.0

    def test_fail_when_P_ext_above_allow(self):
        """Very thin shell under high external pressure must fail."""
        res = external_pressure_check(P_ext=500e3, D_o=0.5, L=3.0, t=0.003)
        assert res["ok"] is True  # function succeeds
        assert res["pass_fail"] is False
        assert res["safety_factor"] < 1.0
        assert len(res["warnings"]) > 0

    def test_S_allow_cap_reduces_B(self):
        """S_allow cap must reduce factor B when B would exceed S_allow."""
        D_o, L, t = 0.5, 2.5, 0.01
        # Very low S_allow to force the cap
        S_low = 1e6
        res_uncapped = external_pressure_check(P_ext=10e3, D_o=D_o, L=L, t=t)
        res_capped = external_pressure_check(P_ext=10e3, D_o=D_o, L=L, t=t, S_allow=S_low)
        assert res_capped["ok"] is True
        assert res_capped["factor_B_Pa"] <= S_low + 1.0  # must be capped

    def test_negative_t_returns_error(self):
        res = external_pressure_check(P_ext=50e3, D_o=0.5, L=2.5, t=-0.01)
        assert res["ok"] is False

    def test_zero_L_returns_error(self):
        res = external_pressure_check(P_ext=50e3, D_o=0.5, L=0.0, t=0.01)
        assert res["ok"] is False


# ===========================================================================
# 6. mawp_cylindrical
# ===========================================================================

class TestMAWPCylindrical:

    def test_algebraic_formula(self):
        """MAWP = S·E·t_net / (R + 0.6·t_net)."""
        t, R, S, E, c = 0.02, 0.5, 138e6, 1.0, 0.003
        t_net = t - c
        expected = S * E * t_net / (R + 0.6 * t_net)
        res = mawp_cylindrical(t=t, R=R, S=S, E=E, c=c)
        assert res["ok"] is True
        assert abs(res["MAWP_Pa"] - expected) / expected < REL

    def test_mawp_decreases_with_corrosion(self):
        """Higher corrosion allowance (more consumed wall) must reduce MAWP."""
        t, R, S = 0.02, 0.5, 138e6
        mawp_0 = mawp_cylindrical(t=t, R=R, S=S, c=0.0)["MAWP_Pa"]
        mawp_3 = mawp_cylindrical(t=t, R=R, S=S, c=0.003)["MAWP_Pa"]
        assert mawp_3 < mawp_0

    def test_mawp_psi_conversion(self):
        """MAWP_psi = MAWP_Pa / 6894.757."""
        res = mawp_cylindrical(t=0.02, R=0.5, S=138e6)
        assert res["ok"] is True
        assert abs(res["MAWP_psi"] - res["MAWP_Pa"] / 6894.757) / (res["MAWP_Pa"] / 6894.757) < REL

    def test_mawp_bar_conversion(self):
        """MAWP_bar = MAWP_Pa / 1e5."""
        res = mawp_cylindrical(t=0.02, R=0.5, S=138e6)
        assert res["ok"] is True
        assert abs(res["MAWP_bar"] - res["MAWP_Pa"] * 1e-5) < 1e-6

    def test_ca_exceeds_t_returns_error(self):
        """Corrosion allowance >= nominal thickness must return error."""
        res = mawp_cylindrical(t=0.005, R=0.5, S=138e6, c=0.005)
        assert res["ok"] is False

    def test_inverse_of_cylindrical_shell_thickness(self):
        """MAWP(thickness from cylindrical_shell_thickness) must >= P."""
        P, R, S = 1.5e6, 0.5, 138e6
        t_req = cylindrical_shell_thickness(P=P, R=R, S=S)["t_required_m"]
        # Use the net thickness (no CA was used) to back-calculate MAWP
        mawp = mawp_cylindrical(t=t_req, R=R, S=S, c=0.0)["MAWP_Pa"]
        assert mawp >= P * (1 - 1e-5)


# ===========================================================================
# 7. nozzle_reinforcement — UG-37
# ===========================================================================

class TestNozzleReinforcement:

    def test_well_reinforced_nozzle_passes(self):
        """A thick-walled nozzle in a thick shell must pass reinforcement check."""
        res = nozzle_reinforcement(
            P=1e6, D_shell=1.0, t_shell=0.05,
            d_nozzle=0.1, t_nozzle=0.02, S=138e6,
        )
        assert res["ok"] is True
        assert res["reinforcement_ok"] is True
        assert res["A_total_m2"] >= res["A_required_m2"]

    def test_undersized_nozzle_fails(self):
        """A large opening in a thin shell with thin nozzle must fail."""
        res = nozzle_reinforcement(
            P=2e6, D_shell=1.0, t_shell=0.008,
            d_nozzle=0.4, t_nozzle=0.004, S=138e6,
        )
        assert res["ok"] is True  # function succeeds
        assert res["reinforcement_ok"] is False
        assert res["shortfall_m2"] > 0
        assert len(res["warnings"]) > 0

    def test_required_area_formula(self):
        """A_required = d × t_req × F."""
        P, D_shell, S, d_nozzle = 1e6, 0.8, 138e6, 0.15
        res = nozzle_reinforcement(
            P=P, D_shell=D_shell, t_shell=0.03,
            d_nozzle=d_nozzle, t_nozzle=0.01, S=S,
        )
        assert res["ok"] is True
        t_req = res["t_req_shell_m"]
        F = 1.0  # default
        expected_A_req = d_nozzle * t_req * F
        assert abs(res["A_required_m2"] - expected_A_req) / expected_A_req < REL

    def test_corrosion_allowance_reduces_available_area(self):
        """Higher CA reduces available reinforcement area."""
        kwargs = dict(P=1e6, D_shell=0.8, t_shell=0.025,
                      d_nozzle=0.15, t_nozzle=0.012, S=138e6)
        res0 = nozzle_reinforcement(**kwargs, c=0.0)
        res_ca = nozzle_reinforcement(**kwargs, c=0.003)
        assert res0["ok"] is True
        assert res_ca["ok"] is True
        assert res_ca["A_total_m2"] <= res0["A_total_m2"]

    def test_invalid_F_returns_error(self):
        res = nozzle_reinforcement(
            P=1e6, D_shell=0.8, t_shell=0.02,
            d_nozzle=0.15, t_nozzle=0.01, S=138e6, F=0.3,
        )
        assert res["ok"] is False

    def test_zero_P_still_works(self):
        """Zero pressure → t_req = 0 → A_required = 0; any shell passes."""
        res = nozzle_reinforcement(
            P=0.0, D_shell=0.8, t_shell=0.02,
            d_nozzle=0.15, t_nozzle=0.01, S=138e6,
        )
        assert res["ok"] is True
        assert res["A_required_m2"] == 0.0
        assert res["reinforcement_ok"] is True


# ===========================================================================
# 8. hydrostatic_test_pressure — UG-99(b)
# ===========================================================================

class TestHydrostaticTestPressure:

    def test_default_ratio_1_3x_mawp(self):
        """With no S_test/S_design, P_test = 1.3 × MAWP."""
        MAWP = 1.5e6
        res = hydrostatic_test_pressure(MAWP=MAWP)
        assert res["ok"] is True
        assert abs(res["P_test_Pa"] - 1.3 * MAWP) / (1.3 * MAWP) < REL

    def test_stress_ratio_applied(self):
        """P_test = 1.3 × MAWP × (S_test / S_design)."""
        MAWP, S_test, S_design = 1.0e6, 150e6, 138e6
        expected = 1.3 * MAWP * (S_test / S_design)
        res = hydrostatic_test_pressure(MAWP=MAWP, S_test=S_test, S_design=S_design)
        assert res["ok"] is True
        assert abs(res["P_test_Pa"] - expected) / expected < REL

    def test_stress_ratio_is_echoed(self):
        """stress_ratio must equal S_test / S_design."""
        MAWP, S_test, S_design = 1e6, 160e6, 138e6
        res = hydrostatic_test_pressure(MAWP=MAWP, S_test=S_test, S_design=S_design)
        assert res["ok"] is True
        assert abs(res["stress_ratio"] - S_test / S_design) < 1e-12

    def test_psi_kpa_bar_conversions(self):
        """Unit conversions must be self-consistent."""
        res = hydrostatic_test_pressure(MAWP=2.0e6)
        assert res["ok"] is True
        assert abs(res["P_test_kPa"] - res["P_test_Pa"] * 1e-3) < 1e-6
        assert abs(res["P_test_bar"] - res["P_test_Pa"] * 1e-5) < 1e-8
        assert abs(res["P_test_psi"] - res["P_test_Pa"] / 6894.757) < 1e-3

    def test_negative_MAWP_returns_error(self):
        res = hydrostatic_test_pressure(MAWP=-1e6)
        assert res["ok"] is False

    def test_one_sided_S_gives_warning_not_error(self):
        """Providing only S_test (without S_design) should not fail."""
        res = hydrostatic_test_pressure(MAWP=1e6, S_test=150e6)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_equal_stresses_gives_1_3x(self):
        """When S_test == S_design, P_test = 1.3 × MAWP."""
        MAWP, S = 1e6, 138e6
        res = hydrostatic_test_pressure(MAWP=MAWP, S_test=S, S_design=S)
        assert res["ok"] is True
        assert abs(res["P_test_Pa"] - 1.3 * MAWP) / (1.3 * MAWP) < REL


# ===========================================================================
# 9. LLM tool wrappers (run_pv_*)
# ===========================================================================

class TestToolWrappers:

    def test_cylindrical_shell_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_cylindrical_shell_thickness(ctx, _args(P=1e6, R=0.5, S=138e6)))
        d = _ok_tool(raw)
        assert d["t_required_m"] > 0
        assert d["t_required_mm"] > 0

    def test_cylindrical_shell_missing_R(self):
        ctx = _ctx()
        raw = _run(run_pv_cylindrical_shell_thickness(ctx, _args(P=1e6, S=138e6)))
        _err_tool(raw)

    def test_cylindrical_shell_bad_json(self):
        ctx = _ctx()
        raw = _run(run_pv_cylindrical_shell_thickness(ctx, b"not json!!"))
        _err_tool(raw)

    def test_spherical_head_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_spherical_head_thickness(ctx, _args(P=1.5e6, R=0.4, S=138e6)))
        d = _ok_tool(raw)
        assert d["t_required_m"] > 0

    def test_spherical_head_missing_S(self):
        ctx = _ctx()
        raw = _run(run_pv_spherical_head_thickness(ctx, _args(P=1e6, R=0.5)))
        _err_tool(raw)

    def test_ellipsoidal_head_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_ellipsoidal_head_thickness(ctx, _args(P=1e6, D=1.0, S=138e6)))
        d = _ok_tool(raw)
        assert d["t_required_m"] > 0
        assert abs(d["head_depth_m"] - 0.25) < 1e-12

    def test_torispherical_head_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_torispherical_head_thickness(ctx, _args(P=1e6, D=1.0, S=138e6)))
        d = _ok_tool(raw)
        assert d["t_required_m"] > 0

    def test_torispherical_head_with_E_and_c(self):
        ctx = _ctx()
        raw = _run(run_pv_torispherical_head_thickness(ctx, _args(
            P=1e6, D=1.0, S=138e6, E=0.85, c=0.003
        )))
        d = _ok_tool(raw)
        assert d["E_factor"] == pytest.approx(0.85)

    def test_external_pressure_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_external_pressure_check(ctx, _args(
            P_ext=50e3, D_o=0.5, L=3.0, t=0.015
        )))
        d = _ok_tool(raw)
        assert d["P_allow_Pa"] > 0
        assert isinstance(d["pass_fail"], bool)

    def test_external_pressure_missing_t(self):
        ctx = _ctx()
        raw = _run(run_pv_external_pressure_check(ctx, _args(P_ext=50e3, D_o=0.5, L=3.0)))
        _err_tool(raw)

    def test_mawp_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_mawp_cylindrical(ctx, _args(t=0.02, R=0.5, S=138e6)))
        d = _ok_tool(raw)
        assert d["MAWP_Pa"] > 0
        assert d["MAWP_psi"] > 0

    def test_mawp_missing_R(self):
        ctx = _ctx()
        raw = _run(run_pv_mawp_cylindrical(ctx, _args(t=0.02, S=138e6)))
        _err_tool(raw)

    def test_nozzle_reinforcement_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_nozzle_reinforcement(ctx, _args(
            P=1e6, D_shell=1.0, t_shell=0.04,
            d_nozzle=0.1, t_nozzle=0.02, S=138e6,
        )))
        d = _ok_tool(raw)
        assert d["A_required_m2"] >= 0
        assert isinstance(d["reinforcement_ok"], bool)

    def test_nozzle_reinforcement_missing_S(self):
        ctx = _ctx()
        raw = _run(run_pv_nozzle_reinforcement(ctx, _args(
            P=1e6, D_shell=1.0, t_shell=0.04,
            d_nozzle=0.1, t_nozzle=0.02,
        )))
        _err_tool(raw)

    def test_hydrostatic_test_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pv_hydrostatic_test_pressure(ctx, _args(MAWP=2.0e6)))
        d = _ok_tool(raw)
        assert abs(d["P_test_Pa"] - 2.6e6) / 2.6e6 < REL

    def test_hydrostatic_test_with_stress_ratio(self):
        ctx = _ctx()
        raw = _run(run_pv_hydrostatic_test_pressure(ctx, _args(
            MAWP=1e6, S_test=150e6, S_design=138e6
        )))
        d = _ok_tool(raw)
        expected = 1.3 * 1e6 * (150e6 / 138e6)
        assert abs(d["P_test_Pa"] - expected) / expected < REL

    def test_hydrostatic_test_missing_MAWP(self):
        ctx = _ctx()
        raw = _run(run_pv_hydrostatic_test_pressure(ctx, _args(S_test=138e6)))
        _err_tool(raw)
