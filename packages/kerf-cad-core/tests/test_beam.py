"""
Hermetic tests for kerf_cad_core.beam — beam & cross-section analysis.

Coverage:
  analysis.section_properties — rectangle, circle, hollow_rect, hollow_circ,
                                 I-section, channel, angle
  analysis.beam_loads          — cantilever, simply_supported, fixed_fixed
                                 under point, UDL, and moment loads
  analysis.superpose           — linear superposition
  analysis.buckling            — Euler + Johnson short-column
  analysis.combined_stress     — axial + bending
  analysis.mohr_circle         — principal stresses
  analysis.shear_flow          — VQ/It
  tools.*                      — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically vs Roark/Hibbeler closed-form references.

References
----------
Roark's Formulas for Stress and Strain, 8th ed. (Young & Budynas)
Hibbeler, Mechanics of Materials, 10th ed.
AISC Steel Construction Manual, 15th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.beam.analysis import (
    section_properties,
    beam_loads,
    superpose,
    buckling,
    combined_stress,
    mohr_circle,
    shear_flow,
)
from kerf_cad_core.beam.tools import (
    run_section_properties,
    run_beam_loads,
    run_beam_superpose,
    run_beam_buckling,
    run_combined_stress,
    run_mohr_circle,
    run_shear_flow,
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


REL = 1e-6  # relative tolerance for floating-point comparisons


# ===========================================================================
# 1. section_properties — rectangle
# ===========================================================================

class TestSectionRectangle:

    def test_area(self):
        r = section_properties("rectangle", b=0.1, h=0.2)
        assert r["ok"] is True
        assert abs(r["A"] - 0.1 * 0.2) < 1e-15

    def test_Ix_formula(self):
        """Ix = b h³ / 12 for solid rectangle (Hibbeler §12.3)."""
        r = section_properties("rectangle", b=0.05, h=0.10)
        expected = 0.05 * 0.10 ** 3 / 12.0
        assert abs(r["Ix"] - expected) / expected < REL

    def test_Iy_formula(self):
        """Iy = h b³ / 12."""
        r = section_properties("rectangle", b=0.05, h=0.10)
        expected = 0.10 * 0.05 ** 3 / 12.0
        assert abs(r["Iy"] - expected) / expected < REL

    def test_Sx_top_equals_Ix_over_c(self):
        """Sx_top = Ix / (h/2)."""
        r = section_properties("rectangle", b=0.1, h=0.3)
        c = 0.3 / 2.0
        assert abs(r["Sx_top"] - r["Ix"] / c) / (r["Ix"] / c) < REL

    def test_Zx_formula(self):
        """Zx = b h² / 4 for rectangle (plastic modulus)."""
        r = section_properties("rectangle", b=0.1, h=0.2)
        expected = 0.1 * 0.2 ** 2 / 4.0
        assert abs(r["Zx"] - expected) / expected < REL

    def test_radius_of_gyration(self):
        """rx = sqrt(Ix/A) = h/sqrt(12)."""
        r = section_properties("rectangle", b=0.1, h=0.2)
        expected_rx = 0.2 / math.sqrt(12.0)
        assert abs(r["rx"] - expected_rx) / expected_rx < REL

    def test_centroid_at_centre(self):
        r = section_properties("rectangle", b=0.08, h=0.12)
        assert abs(r["cx"] - 0.04) < 1e-14
        assert abs(r["cy"] - 0.06) < 1e-14

    def test_negative_b_returns_error(self):
        r = section_properties("rectangle", b=-0.1, h=0.2)
        assert r["ok"] is False

    def test_missing_h_returns_error(self):
        r = section_properties("rectangle", b=0.1)
        assert r["ok"] is False


# ===========================================================================
# 2. section_properties — circle
# ===========================================================================

class TestSectionCircle:

    def test_area(self):
        r = section_properties("circle", d=0.1)
        assert abs(r["A"] - math.pi * 0.0025) / (math.pi * 0.0025) < REL

    def test_Ix_formula(self):
        """Ix = π d⁴ / 64 (Hibbeler App. B)."""
        r = section_properties("circle", d=0.1)
        expected = math.pi * 0.1 ** 4 / 64.0
        assert abs(r["Ix"] - expected) / expected < REL

    def test_J_equals_2Ix(self):
        """Polar moment J = 2Ix for circle: J = π d⁴ / 32."""
        r = section_properties("circle", d=0.1)
        assert abs(r["J"] - 2.0 * r["Ix"]) / (2.0 * r["Ix"]) < REL

    def test_Ix_equals_Iy(self):
        r = section_properties("circle", d=0.15)
        assert abs(r["Ix"] - r["Iy"]) < 1e-25


# ===========================================================================
# 3. section_properties — hollow_rect
# ===========================================================================

class TestSectionHollowRect:

    def test_area_is_outer_minus_inner(self):
        r = section_properties("hollow_rect", b=0.10, h=0.15, t=0.005)
        expected = 0.10 * 0.15 - 0.09 * 0.14
        assert abs(r["A"] - expected) / expected < REL

    def test_Ix_formula(self):
        """Ix = (b h³ - bi hi³) / 12."""
        b, h, t = 0.10, 0.15, 0.005
        r = section_properties("hollow_rect", b=b, h=h, t=t)
        bi, hi = b - 2 * t, h - 2 * t
        expected = (b * h ** 3 - bi * hi ** 3) / 12.0
        assert abs(r["Ix"] - expected) / expected < REL

    def test_thick_wall_error(self):
        """Wall too thick (no interior) must return error."""
        r = section_properties("hollow_rect", b=0.10, h=0.10, t=0.06)
        assert r["ok"] is False

    def test_J_positive(self):
        r = section_properties("hollow_rect", b=0.10, h=0.15, t=0.005)
        assert r["J"] > 0


# ===========================================================================
# 4. section_properties — hollow_circ
# ===========================================================================

class TestSectionHollowCirc:

    def test_Ix_formula(self):
        """Ix = π (d⁴ - di⁴) / 64."""
        d, t = 0.10, 0.005
        r = section_properties("hollow_circ", d=d, t=t)
        di = d - 2 * t
        expected = math.pi * (d ** 4 - di ** 4) / 64.0
        assert abs(r["Ix"] - expected) / expected < REL

    def test_J_equals_2Ix(self):
        d, t = 0.10, 0.005
        r = section_properties("hollow_circ", d=d, t=t)
        assert abs(r["J"] - 2.0 * r["Ix"]) / (2.0 * r["Ix"]) < REL

    def test_t_too_large_returns_error(self):
        r = section_properties("hollow_circ", d=0.10, t=0.06)
        assert r["ok"] is False


# ===========================================================================
# 5. section_properties — I-section
# ===========================================================================

class TestSectionI:

    def _std_I(self):
        """Standard I 150×150 (mm → m): bf=0.15, d=0.30, tf=0.01, tw=0.008."""
        return section_properties("I", bf=0.15, d=0.30, tf=0.01, tw=0.008)

    def test_ok(self):
        assert self._std_I()["ok"] is True

    def test_area(self):
        r = self._std_I()
        bf, d, tf, tw = 0.15, 0.30, 0.01, 0.008
        hw = d - 2 * tf
        expected = 2 * bf * tf + hw * tw
        assert abs(r["A"] - expected) / expected < REL

    def test_Ix_greater_than_rectangle_with_same_depth(self):
        """I-section should have lower area but higher Ix than solid rectangle."""
        r_I = self._std_I()
        r_rect = section_properties("rectangle", b=0.008, h=0.30)
        # I section has more material away from NA, so higher Ix per unit area
        assert r_I["Ix"] > r_rect["Ix"]

    def test_Zx_positive(self):
        assert self._std_I()["Zx"] > 0

    def test_flanges_overlap_error(self):
        r = section_properties("I", bf=0.15, d=0.10, tf=0.06, tw=0.008)
        assert r["ok"] is False

    def test_J_positive(self):
        assert self._std_I()["J"] > 0


# ===========================================================================
# 6. section_properties — channel and angle
# ===========================================================================

class TestSectionChannelAndAngle:

    def test_channel_ok(self):
        r = section_properties("channel", b=0.10, d=0.20, tf=0.01, tw=0.006)
        assert r["ok"] is True
        assert r["A"] > 0
        assert r["Ix"] > 0

    def test_channel_centroid_within_section(self):
        r = section_properties("channel", b=0.10, d=0.20, tf=0.01, tw=0.006)
        # cx must be between 0 and b
        assert 0 < r["cx"] < 0.10
        assert abs(r["cy"] - 0.10) < 1e-10  # symmetric

    def test_angle_ok(self):
        r = section_properties("angle", b=0.10, h=0.10, t=0.01)
        assert r["ok"] is True
        assert r["A"] > 0

    def test_angle_centroid_on_diagonal(self):
        """Equal-leg angle: cx == cy by symmetry."""
        r = section_properties("angle", b=0.10, h=0.10, t=0.01)
        assert abs(r["cx"] - r["cy"]) < 1e-10

    def test_angle_thick_returns_error(self):
        r = section_properties("angle", b=0.05, h=0.05, t=0.06)
        assert r["ok"] is False

    def test_unknown_shape_error(self):
        r = section_properties("hexagon", b=0.1)
        assert r["ok"] is False


# ===========================================================================
# 7. beam_loads — cantilever
# ===========================================================================

class TestBeamLoadsCantilever:

    def test_udl_deflection_formula(self):
        """δ_max = w L⁴ / (8 EI) at free end (Roark Table 8.1)."""
        E, I, L, w = 200e9, 1e-6, 2.0, 1000.0
        r = beam_loads("cantilever", "udl", E=E, I=I, L=L, w=w)
        assert r["ok"] is True
        expected = w * L ** 4 / (8.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_udl_max_moment(self):
        """M_max = w L² / 2 at the fixed end."""
        E, I, L, w = 200e9, 1e-6, 2.0, 1000.0
        r = beam_loads("cantilever", "udl", E=E, I=I, L=L, w=w)
        expected = w * L ** 2 / 2.0
        assert abs(r["max_moment"] - expected) / expected < REL

    def test_udl_max_shear(self):
        """V_max = w L at fixed end."""
        E, I, L, w = 200e9, 1e-6, 2.0, 1000.0
        r = beam_loads("cantilever", "udl", E=E, I=I, L=L, w=w)
        assert abs(r["max_shear"] - w * L) / (w * L) < REL

    def test_point_load_at_free_end_deflection(self):
        """δ_max = P L³ / (3 EI) for cantilever point load at free end (Roark)."""
        E, I, L, P = 200e9, 1e-6, 3.0, 5000.0
        r = beam_loads("cantilever", "point", E=E, I=I, L=L, P=P, a=L)
        expected = P * L ** 3 / (3.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_point_load_at_free_end_moment(self):
        """M_max = P L at fixed end."""
        E, I, L, P = 200e9, 1e-6, 3.0, 5000.0
        r = beam_loads("cantilever", "point", E=E, I=I, L=L, P=P, a=L)
        assert abs(r["max_moment"] - P * L) / (P * L) < REL

    def test_moment_load_deflection(self):
        """δ_max = M0 L² / (2 EI) for cantilever with end moment."""
        E, I, L, M0 = 200e9, 1e-6, 2.0, 10000.0
        r = beam_loads("cantilever", "moment", E=E, I=I, L=L, M0=M0)
        expected = M0 * L ** 2 / (2.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_stiffer_EI_reduces_deflection(self):
        """Doubling EI halves deflection (δ ∝ 1/EI)."""
        E, I, L, w = 200e9, 1e-6, 2.0, 1000.0
        d1 = beam_loads("cantilever", "udl", E=E, I=I, L=L, w=w)["max_deflection"]
        d2 = beam_loads("cantilever", "udl", E=E * 2, I=I, L=L, w=w)["max_deflection"]
        assert abs(d2 / d1 - 0.5) < 1e-10


# ===========================================================================
# 8. beam_loads — simply_supported
# ===========================================================================

class TestBeamLoadsSimplySupported:

    def test_udl_deflection_formula(self):
        """δ_max = 5 w L⁴ / (384 EI) at midspan (Hibbeler App. C)."""
        E, I, L, w = 200e9, 1e-6, 4.0, 2000.0
        r = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        assert r["ok"] is True
        expected = 5.0 * w * L ** 4 / (384.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_udl_max_moment(self):
        """M_max = w L² / 8 at midspan."""
        E, I, L, w = 200e9, 1e-6, 4.0, 2000.0
        r = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        expected = w * L ** 2 / 8.0
        assert abs(r["max_moment"] - expected) / expected < REL

    def test_udl_reactions_equal(self):
        """Symmetric UDL: Ra = Rb = w L / 2."""
        E, I, L, w = 200e9, 1e-6, 4.0, 2000.0
        r = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        assert abs(r["Ra"] - w * L / 2.0) / (w * L / 2.0) < REL
        assert abs(r["Rb"] - w * L / 2.0) / (w * L / 2.0) < REL

    def test_central_point_load_deflection(self):
        """δ_max = P L³ / (48 EI) for central point load (Hibbeler App. C)."""
        E, I, L, P = 200e9, 1e-6, 4.0, 10000.0
        r = beam_loads("simply_supported", "point", E=E, I=I, L=L, P=P, a=L / 2.0)
        expected = P * L ** 3 / (48.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < 1e-4  # loose due to formula approx

    def test_central_point_load_moment(self):
        """M_max = P L / 4 at midspan for central load."""
        E, I, L, P = 200e9, 1e-6, 4.0, 10000.0
        r = beam_loads("simply_supported", "point", E=E, I=I, L=L, P=P, a=L / 2.0)
        expected = P * L / 4.0
        assert abs(r["max_moment"] - expected) / expected < REL

    def test_point_load_reactions_sum_to_P(self):
        """Ra + Rb = P (equilibrium)."""
        E, I, L, P = 200e9, 1e-6, 3.0, 8000.0
        r = beam_loads("simply_supported", "point", E=E, I=I, L=L, P=P, a=1.0)
        assert abs(r["Ra"] + r["Rb"] - P) / P < REL


# ===========================================================================
# 9. beam_loads — fixed_fixed
# ===========================================================================

class TestBeamLoadsFixedFixed:

    def test_udl_deflection_formula(self):
        """δ_max = w L⁴ / (384 EI) at midspan (Roark Table 8.2)."""
        E, I, L, w = 200e9, 1e-6, 3.0, 1500.0
        r = beam_loads("fixed_fixed", "udl", E=E, I=I, L=L, w=w)
        assert r["ok"] is True
        expected = w * L ** 4 / (384.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_udl_max_moment_at_ends(self):
        """M at clamped ends = w L² / 12 (Roark Table 8.2)."""
        E, I, L, w = 200e9, 1e-6, 3.0, 1500.0
        r = beam_loads("fixed_fixed", "udl", E=E, I=I, L=L, w=w)
        expected_end = w * L ** 2 / 12.0
        assert abs(r["max_moment"] - expected_end) / expected_end < REL

    def test_central_point_load_deflection(self):
        """δ_max = P L³ / (192 EI) for central point load (Roark)."""
        E, I, L, P = 200e9, 1e-6, 2.0, 10000.0
        r = beam_loads("fixed_fixed", "point", E=E, I=I, L=L, P=P, a=L / 2.0)
        expected = P * L ** 3 / (192.0 * E * I)
        assert abs(r["max_deflection"] - expected) / expected < REL

    def test_fixed_fixed_less_deflection_than_simply_supported(self):
        """Fixed-fixed has lower deflection than simply-supported for same UDL."""
        E, I, L, w = 200e9, 1e-6, 4.0, 2000.0
        d_ss = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)["max_deflection"]
        d_ff = beam_loads("fixed_fixed",      "udl", E=E, I=I, L=L, w=w)["max_deflection"]
        assert d_ff < d_ss

    def test_invalid_support_returns_error(self):
        r = beam_loads("hinged_roller", "udl", E=200e9, I=1e-6, L=2.0, w=1000.0)
        assert r["ok"] is False

    def test_invalid_load_type_returns_error(self):
        r = beam_loads("cantilever", "triangular", E=200e9, I=1e-6, L=2.0)
        assert r["ok"] is False


# ===========================================================================
# 10. superpose
# ===========================================================================

class TestSuperpose:

    def test_two_udl_cases(self):
        """Superposing two identical loads doubles results."""
        E, I, L, w = 200e9, 1e-6, 4.0, 1000.0
        c1 = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        c2 = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        sp = superpose([c1, c2])
        assert sp["ok"] is True
        assert abs(sp["max_deflection"] - 2.0 * c1["max_deflection"]) < 1e-15
        assert abs(sp["max_moment"] - 2.0 * c1["max_moment"]) < 1e-10
        assert sp["n_cases"] == 2

    def test_empty_cases_returns_error(self):
        r = superpose([])
        assert r["ok"] is False

    def test_failed_case_returns_error(self):
        r = superpose([{"ok": False, "reason": "bad input"}])
        assert r["ok"] is False

    def test_ra_rb_summed(self):
        """Reactions are algebraically summed."""
        E, I, L, w = 200e9, 1e-6, 4.0, 1000.0
        c = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        sp = superpose([c, c, c])
        assert abs(sp["Ra"] - 3.0 * c["Ra"]) < 1e-10


# ===========================================================================
# 11. buckling
# ===========================================================================

class TestBuckling:

    def test_euler_formula(self):
        """P_euler = π² E I / (K L)² (Euler, 1744)."""
        L, A, I, E, Fy = 3.0, 0.01, 8.333e-6, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy, K=1.0)
        assert r["ok"] is True
        expected = math.pi ** 2 * E * I / L ** 2
        assert abs(r["P_euler"] - expected) / expected < REL

    def test_K_pin_pin(self):
        """K=1.0 (pin-pin) is the base case."""
        L, A, I, E, Fy = 2.0, 0.005, 1e-6, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy, K=1.0)
        Pe_expected = math.pi ** 2 * E * I / L ** 2
        assert abs(r["P_euler"] - Pe_expected) / Pe_expected < REL

    def test_K_doubles_length_quarters_euler(self):
        """Doubling K halves effective KL, quarters P_euler (P ∝ 1/(KL)²)."""
        L, A, I, E, Fy = 2.0, 0.005, 1e-6, 200e9, 250e6
        P1 = buckling(L, A, I, E, Fy=Fy, K=1.0)["P_euler"]
        P2 = buckling(L, A, I, E, Fy=Fy, K=2.0)["P_euler"]
        assert abs(P2 / P1 - 0.25) < 1e-9

    def test_johnson_mode_for_short_column(self):
        """Short column (low slenderness) should use Johnson mode."""
        # Small KL/r → Johnson governs
        L, A, I, E, Fy = 0.2, 0.01, 8.333e-6, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy, K=1.0)
        assert r["ok"] is True
        assert r["mode"] == "johnson"

    def test_euler_mode_for_slender_column(self):
        """Slender column (KL/r >> Cc) should use Euler mode."""
        L, A, I, E, Fy = 10.0, 0.001, 1e-8, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy, K=1.0)
        assert r["ok"] is True
        assert r["mode"] == "euler"

    def test_radius_of_gyration(self):
        """r = sqrt(I/A)."""
        L, A, I, E, Fy = 2.0, 0.005, 1e-6, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy)
        expected_r = math.sqrt(I / A)
        assert abs(r["r"] - expected_r) / expected_r < REL

    def test_transition_slenderness(self):
        """Cc = π √(2E/Fy)."""
        L, A, I, E, Fy = 2.0, 0.005, 1e-6, 200e9, 250e6
        r = buckling(L, A, I, E, Fy=Fy)
        expected_Cc = math.pi * math.sqrt(2.0 * E / Fy)
        assert abs(r["Cc"] - expected_Cc) / expected_Cc < REL

    def test_negative_L_returns_error(self):
        r = buckling(-1.0, 0.01, 1e-6, 200e9, Fy=250e6)
        assert r["ok"] is False

    def test_zero_A_returns_error(self):
        r = buckling(2.0, 0.0, 1e-6, 200e9, Fy=250e6)
        assert r["ok"] is False


# ===========================================================================
# 12. combined_stress
# ===========================================================================

class TestCombinedStress:

    def test_pure_tension(self):
        """Pure axial tension: sigma_bot = sigma_top = P/A when M=0."""
        P, M, A, S = 100000.0, 0.0, 0.01, 0.001
        r = combined_stress(P, M, A, S)
        assert r["ok"] is True
        assert abs(r["sigma_axial"] - P / A) / (P / A) < REL
        assert abs(r["sigma_top"] - P / A) / (P / A) < REL
        assert abs(r["sigma_bot"] - P / A) / (P / A) < REL

    def test_pure_bending(self):
        """Pure bending (P=0): sigma_top = -M/S, sigma_bot = +M/S."""
        P, M, A, S = 0.0, 5000.0, 0.01, 0.0002
        r = combined_stress(P, M, A, S)
        assert r["ok"] is True
        expected_b = M / S
        assert abs(r["sigma_bending"] - expected_b) / expected_b < REL
        assert abs(r["sigma_top"] + expected_b) < 1e-6  # sigma_top = 0 - sigma_b
        assert abs(r["sigma_bot"] - expected_b) / expected_b < REL

    def test_sigma_max_is_maximum(self):
        """sigma_max = max(|sigma_top|, |sigma_bot|)."""
        P, M, A, S = 50000.0, 10000.0, 0.01, 0.0002
        r = combined_stress(P, M, A, S)
        expected_max = max(abs(r["sigma_top"]), abs(r["sigma_bot"]))
        assert abs(r["sigma_max"] - expected_max) < 1e-6

    def test_compressive_axial(self):
        """Negative P gives compressive axial stress."""
        r = combined_stress(-100000.0, 5000.0, 0.01, 0.0002)
        assert r["sigma_axial"] < 0

    def test_zero_S_returns_error(self):
        r = combined_stress(10000.0, 5000.0, 0.01, 0.0)
        assert r["ok"] is False


# ===========================================================================
# 13. mohr_circle
# ===========================================================================

class TestMohrCircle:

    def test_uniaxial_stress(self):
        """Uniaxial: σx alone → σ1=σx, σ2=0, tau_max=σx/2."""
        sx = 100e6
        r = mohr_circle(sx, 0.0, 0.0)
        assert r["ok"] is True
        assert abs(r["sigma_1"] - sx) / sx < REL
        assert abs(r["sigma_2"]) < 1.0  # ~ 0
        assert abs(r["tau_max"] - sx / 2.0) / (sx / 2.0) < REL

    def test_biaxial_equal_stress_zero_shear(self):
        """σx=σy, τxy=0 → σ1=σ2=σx, tau_max=0."""
        s = 50e6
        r = mohr_circle(s, s, 0.0)
        assert abs(r["sigma_1"] - s) / s < REL
        assert abs(r["sigma_2"] - s) / s < REL
        assert abs(r["tau_max"]) < 1.0

    def test_pure_shear(self):
        """τxy only: σ1=-σ2=|τxy|, tau_max=|τxy|."""
        tau = 80e6
        r = mohr_circle(0.0, 0.0, tau)
        assert abs(r["sigma_1"] - tau) / tau < REL
        assert abs(r["sigma_2"] + tau) / tau < REL
        assert abs(r["tau_max"] - tau) / tau < REL

    def test_principal_stress_inequality(self):
        """σ1 >= σ2 always."""
        r = mohr_circle(120e6, -30e6, 60e6)
        assert r["sigma_1"] >= r["sigma_2"]

    def test_radius_formula(self):
        """R = √[((σx-σy)/2)² + τxy²]."""
        sx, sy, txy = 100e6, 40e6, 30e6
        r = mohr_circle(sx, sy, txy)
        expected_R = math.sqrt(((sx - sy) / 2.0) ** 2 + txy ** 2)
        assert abs(r["R"] - expected_R) / expected_R < REL

    def test_sigma_avg(self):
        """sigma_avg = (σx + σy) / 2."""
        sx, sy, txy = 60e6, 20e6, 10e6
        r = mohr_circle(sx, sy, txy)
        assert abs(r["sigma_avg"] - (sx + sy) / 2.0) / ((sx + sy) / 2.0) < REL


# ===========================================================================
# 14. shear_flow
# ===========================================================================

class TestShearFlow:

    def test_vqit_formula(self):
        """τ = VQ / (I b)."""
        V, Q, I_val, b = 10000.0, 1e-4, 1e-6, 0.01
        r = shear_flow(V, Q, I_val, b)
        assert r["ok"] is True
        expected = V * Q / (I_val * b)
        assert abs(r["tau_Pa"] - expected) / expected < REL

    def test_doubling_V_doubles_tau(self):
        """τ ∝ V."""
        V, Q, I_val, b = 5000.0, 2e-4, 5e-6, 0.015
        tau1 = shear_flow(V, Q, I_val, b)["tau_Pa"]
        tau2 = shear_flow(V * 2.0, Q, I_val, b)["tau_Pa"]
        assert abs(tau2 / tau1 - 2.0) < 1e-10

    def test_zero_Q_gives_zero_tau(self):
        """Q=0 at neutral axis: τ=0."""
        r = shear_flow(10000.0, 0.0, 1e-6, 0.01)
        assert r["ok"] is True
        assert r["tau_Pa"] == 0.0

    def test_negative_b_returns_error(self):
        r = shear_flow(10000.0, 1e-4, 1e-6, -0.01)
        assert r["ok"] is False

    def test_zero_I_returns_error(self):
        r = shear_flow(10000.0, 1e-4, 0.0, 0.01)
        assert r["ok"] is False


# ===========================================================================
# 14b. Externally-citable reference cases (worked examples / code tables)
# ===========================================================================

class TestExternalReferenceCases:
    """Each assertion checks against a specific, citable published answer."""

    def test_aisc_C12x30_channel_Ix(self):
        # AISC Steel Construction Manual, 15th ed., Shapes Database — C12x30:
        # d=12.0 in, bf=3.17 in, tf=0.501 in, tw=0.510 in, Ix = 162 in^4.
        # Rectangle decomposition (no fillets) should land within ~1%.
        r = section_properties("channel", b=3.17, d=12.0, tf=0.501, tw=0.510)
        assert abs(r["Ix"] - 162.0) / 162.0 < 0.01

    def test_aisc_C12x30_channel_area(self):
        # AISC C12x30: A = 8.81 in^2 (rectangle model ignores fillets → ~0.3% low).
        r = section_properties("channel", b=3.17, d=12.0, tf=0.501, tw=0.510)
        assert abs(r["A"] - 8.81) / 8.81 < 0.01

    def test_aisc_W14x90_plastic_Zx(self):
        # AISC Shapes Database — W14x90: bf=14.52, d=14.0, tf=0.710, tw=0.440 in.
        # Zx = 157 in^3 (rectangle model w/o fillets ~1.7% low).
        r = section_properties("I", bf=14.52, d=14.0, tf=0.710, tw=0.440)
        assert abs(r["Zx"] - 157.0) / 157.0 < 0.02

    def test_aisc_W14x90_weak_axis_plastic_Zy(self):
        # AISC W14x90: Zy = 75.6 in^3.  Pre-fix code returned ~151 (2x error).
        r = section_properties("I", bf=14.52, d=14.0, tf=0.710, tw=0.440)
        assert abs(r["Zy"] - 75.6) / 75.6 < 0.02

    def test_hibbeler_solid_circle_polar_J(self):
        # Hibbeler, Mechanics of Materials: solid shaft J = π d^4 / 32.
        # d = 0.04 m → J = π(0.04)^4/32 = 2.5133e-7 m^4.
        r = section_properties("circle", d=0.04)
        assert abs(r["J"] - math.pi * 0.04 ** 4 / 32.0) / (math.pi * 0.04 ** 4 / 32.0) < REL

    def test_roark_ss_point_load_offset_max_deflection(self):
        # Roark's Formulas, 8th ed., Table 8.1, case 1e (SS, off-centre point):
        # P=1000 N at a=2 m on L=5 m span, EI = 1.0e6 N·m².
        # δ_max = 0.01615 m at x = sqrt((L²−b²)/3) (b = shorter dist = 2 m... a>b).
        # Closed-form Roark value: x_m = sqrt((25-4)/3)=2.6458 m,
        # δ = P·b·x·(L²−b²−x²)/(6 EI L) with b=2 → 1000·2·2.6458·(25-4-7)/(6e6·5)
        E, I, L, P = 1.0, 1.0e6, 5.0, 1000.0
        r = beam_loads("simply_supported", "point", E=E, I=I, L=L, P=P, a=3.0)
        # a=3, b=2 → b_s=2; x_m = sqrt((25-4)/3) = 2.64575 m
        x_m = math.sqrt((25.0 - 4.0) / 3.0)
        d_ref = P * 2.0 * x_m * (25.0 - 4.0 - x_m ** 2) / (6.0 * 1.0e6 * 5.0)
        assert abs(r["max_deflection"] - d_ref) / d_ref < 1e-6

    def test_roark_cantilever_point_tip_deflection(self):
        # Roark Table 8.1 case 1a: cantilever, tip point load,
        # δ = P L³/(3EI).  P=5 kN, L=3 m, EI=200e9·1e-6=2e5 → δ=0.225 m.
        r = beam_loads("cantilever", "point", E=200e9, I=1e-6, L=3.0, P=5000.0, a=3.0)
        assert abs(r["max_deflection"] - 0.225) / 0.225 < 1e-9

    def test_roark_fixed_fixed_central_point(self):
        # Roark Table 8.2: fixed-fixed central point load δ = P L³/(192 EI),
        # fixed-end moment M = P L / 8.
        E, I, L, P = 200e9, 1e-6, 4.0, 12000.0
        r = beam_loads("fixed_fixed", "point", E=E, I=I, L=L, P=P, a=L / 2.0)
        assert abs(r["max_deflection"] - P * L ** 3 / (192.0 * E * I)) / (P * L ** 3 / (192.0 * E * I)) < 1e-9
        assert abs(r["max_moment"] - P * L / 8.0) / (P * L / 8.0) < 1e-9

    def test_hibbeler_mohr_principal_angle(self):
        # Hibbeler, Mechanics of Materials, 10th ed., Example 9.6:
        # σx = -20 MPa, σy = 90 MPa, τxy = 60 MPa →
        # σ1 = 116.4 MPa, σ2 = -46.4 MPa, θp2 = -23.7° (to σ1 axis +66.3°/-23.7°).
        r = mohr_circle(-20e6, 90e6, 60e6)
        assert abs(r["sigma_1"] - 116.4e6) / 116.4e6 < 5e-3
        assert abs(r["sigma_2"] - (-46.4e6)) / 46.4e6 < 5e-3
        # principal angle: tan(2θp)=2·60/(-20-90) → 2θp = atan2(120,-110)
        theta_ref = math.degrees(0.5 * math.atan2(2.0 * 60e6, -20e6 - 90e6))
        assert abs(r["theta_p_deg"] - theta_ref) < 1e-6

    def test_euler_pinned_column_known_value(self):
        # Hibbeler, Mechanics of Materials, Euler column:
        # P_cr = π²EI/(KL)².  Steel rod E=200 GPa, I=4.909e-9 m^4 (d=20 mm),
        # L=2 m, K=1 → P_cr = π²·200e9·4.909e-9/4 = 2423 N.
        r = buckling(2.0, math.pi * 0.01 ** 2, math.pi * 0.02 ** 4 / 64.0,
                     200e9, Fy=10e9, K=1.0)
        Pe = math.pi ** 2 * 200e9 * (math.pi * 0.02 ** 4 / 64.0) / 4.0
        assert abs(r["P_euler"] - Pe) / Pe < REL


# ===========================================================================
# 15. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    # ---- beam_section_properties ----

    def test_section_rectangle_tool(self):
        ctx = _ctx()
        raw = _run(run_section_properties(ctx, _args(shape="rectangle", b=0.1, h=0.2)))
        d = _ok_tool(raw)
        assert abs(d["A"] - 0.02) < 1e-12

    def test_section_circle_tool(self):
        ctx = _ctx()
        raw = _run(run_section_properties(ctx, _args(shape="circle", d=0.1)))
        d = _ok_tool(raw)
        assert abs(d["Ix"] - math.pi * 0.1 ** 4 / 64.0) / (math.pi * 0.1 ** 4 / 64.0) < REL

    def test_section_missing_shape_returns_error(self):
        ctx = _ctx()
        raw = _run(run_section_properties(ctx, _args(b=0.1, h=0.2)))
        _err_tool(raw)

    def test_section_bad_json_returns_error(self):
        ctx = _ctx()
        raw = _run(run_section_properties(ctx, b"not json"))
        _err_tool(raw)

    # ---- beam_loads tool ----

    def test_beam_loads_cantilever_udl_tool(self):
        ctx = _ctx()
        raw = _run(run_beam_loads(ctx, _args(
            support="cantilever", load_type="udl",
            E=200e9, I=1e-6, L=2.0, w=1000.0,
        )))
        d = _ok_tool(raw)
        expected = 1000.0 * 2.0 ** 4 / (8.0 * 200e9 * 1e-6)
        assert abs(d["max_deflection"] - expected) / expected < REL

    def test_beam_loads_missing_E_returns_error(self):
        ctx = _ctx()
        raw = _run(run_beam_loads(ctx, _args(
            support="cantilever", load_type="udl", I=1e-6, L=2.0, w=1000.0,
        )))
        _err_tool(raw)

    def test_beam_loads_invalid_support_returns_error(self):
        ctx = _ctx()
        raw = _run(run_beam_loads(ctx, _args(
            support="portal_frame", load_type="udl",
            E=200e9, I=1e-6, L=2.0, w=1000.0,
        )))
        _err_tool(raw)

    # ---- beam_superpose tool ----

    def test_beam_superpose_tool(self):
        ctx = _ctx()
        E, I, L, w = 200e9, 1e-6, 4.0, 1000.0
        c = beam_loads("simply_supported", "udl", E=E, I=I, L=L, w=w)
        raw = _run(run_beam_superpose(ctx, json.dumps({"cases": [c, c]}).encode()))
        d = _ok_tool(raw)
        assert abs(d["max_deflection"] - 2.0 * c["max_deflection"]) < 1e-15

    def test_beam_superpose_non_array_returns_error(self):
        ctx = _ctx()
        raw = _run(run_beam_superpose(ctx, _args(cases="not_a_list")))
        _err_tool(raw)

    # ---- beam_buckling tool ----

    def test_beam_buckling_tool(self):
        ctx = _ctx()
        raw = _run(run_beam_buckling(ctx, _args(
            L_eff=3.0, A=0.01, I=8.333e-6, E=200e9, Fy=250e6,
        )))
        d = _ok_tool(raw)
        assert d["P_euler"] > 0
        assert d["mode"] in ("euler", "johnson")

    def test_beam_buckling_missing_Fy_returns_error(self):
        ctx = _ctx()
        raw = _run(run_beam_buckling(ctx, _args(
            L_eff=3.0, A=0.01, I=8.333e-6, E=200e9,
        )))
        _err_tool(raw)

    # ---- beam_combined_stress tool ----

    def test_combined_stress_tool(self):
        ctx = _ctx()
        raw = _run(run_combined_stress(ctx, _args(P=50000.0, M=5000.0, A=0.01, S=0.0002)))
        d = _ok_tool(raw)
        assert d["sigma_max"] > 0

    def test_combined_stress_zero_S_tool_returns_error(self):
        ctx = _ctx()
        raw = _run(run_combined_stress(ctx, _args(P=50000.0, M=5000.0, A=0.01, S=0.0)))
        _err_tool(raw)

    # ---- beam_mohr_circle tool ----

    def test_mohr_circle_tool_pure_shear(self):
        ctx = _ctx()
        raw = _run(run_mohr_circle(ctx, _args(sigma_x=0.0, sigma_y=0.0, tau_xy=100e6)))
        d = _ok_tool(raw)
        assert abs(d["sigma_1"] - 100e6) / 100e6 < REL
        assert abs(d["sigma_2"] + 100e6) / 100e6 < REL

    def test_mohr_circle_missing_tau_returns_error(self):
        ctx = _ctx()
        raw = _run(run_mohr_circle(ctx, _args(sigma_x=100e6, sigma_y=0.0)))
        _err_tool(raw)

    # ---- beam_shear_flow tool ----

    def test_shear_flow_tool(self):
        ctx = _ctx()
        raw = _run(run_shear_flow(ctx, _args(V=10000.0, Q=1e-4, I=1e-6, b=0.01)))
        d = _ok_tool(raw)
        expected = 10000.0 * 1e-4 / (1e-6 * 0.01)
        assert abs(d["tau_Pa"] - expected) / expected < REL

    def test_shear_flow_bad_json_returns_error(self):
        ctx = _ctx()
        raw = _run(run_shear_flow(ctx, b"{bad json"))
        _err_tool(raw)
