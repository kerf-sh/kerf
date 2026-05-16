"""
Hermetic tests for kerf_cad_core.composites — Classical Lamination Theory (CLT).

Coverage:
  laminate.reduced_stiffness      — Q matrix from engineering constants
  laminate.transform_Q            — Q̄(θ) transformation
  laminate.abd_matrix             — ABD assembly for unidirectional, cross-ply, QI
  laminate.laminate_response      — solve ABD system
  laminate.ply_stresses_strains   — per-ply stress/strain in global & material axes
  laminate.failure_indices        — max-stress, max-strain, Tsai-Hill, Tsai-Wu
  laminate.laminate_engineering_moduli — effective Ex, Ey, Gxy, nu_xy
  laminate.first_ply_failure_load — FPF scaling factor
  tools.*                         — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Results verified against Jones/Gibson CLT hand-calculations.

References
----------
Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999) — Chapters 2, 4
Gibson, R.F. "Principles of Composite Material Mechanics", 4th ed. (2016) — Chapters 4, 6

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.composites.laminate import (
    reduced_stiffness,
    transform_Q,
    abd_matrix,
    laminate_response,
    ply_stresses_strains,
    failure_indices,
    laminate_engineering_moduli,
    first_ply_failure_load,
)
from kerf_cad_core.composites.tools import (
    run_composite_reduced_stiffness,
    run_composite_transform_Q,
    run_composite_abd_matrix,
    run_composite_laminate_response,
    run_composite_failure_indices,
    run_composite_engineering_moduli,
    run_composite_first_ply_failure,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

REL = 1e-6   # relative tolerance for floating-point checks
ABS = 1e-8   # absolute tolerance for near-zero values


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


# ---------------------------------------------------------------------------
# Shared material: T300/5208 unidirectional carbon/epoxy (Jones §2.1 Table 2.1)
# E1=181 GPa, E2=10.3 GPa, nu12=0.28, G12=7.17 GPa
# Strengths: F1t=1500 MPa, F1c=1500 MPa, F2t=40 MPa, F2c=246 MPa, F12=68 MPa
# ---------------------------------------------------------------------------

E1_cf = 181e9
E2_cf = 10.3e9
nu12_cf = 0.28
G12_cf = 7.17e9

S_cf = {
    "F1t": 1500e6,
    "F1c": 1500e6,
    "F2t": 40e6,
    "F2c": 246e6,
    "F12": 68e6,
}


def _cf_ply(angle_deg: float, thickness: float = 0.125e-3) -> dict:
    return {
        "E1": E1_cf, "E2": E2_cf, "nu12": nu12_cf,
        "G12": G12_cf, "thickness": thickness, "angle_deg": angle_deg,
    }


# ===========================================================================
# 1. reduced_stiffness
# ===========================================================================

class TestReducedStiffness:

    def test_Q11_formula(self):
        """Q11 = E1/(1-nu12*nu21)."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        assert res["ok"] is True
        nu21 = nu12_cf * E2_cf / E1_cf
        denom = 1.0 - nu12_cf * nu21
        Q11_expected = E1_cf / denom
        assert abs(res["Q11"] - Q11_expected) / Q11_expected < REL

    def test_Q22_formula(self):
        """Q22 = E2/(1-nu12*nu21)."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        nu21 = nu12_cf * E2_cf / E1_cf
        denom = 1.0 - nu12_cf * nu21
        Q22_expected = E2_cf / denom
        assert abs(res["Q22"] - Q22_expected) / Q22_expected < REL

    def test_Q12_formula(self):
        """Q12 = nu12*E2/(1-nu12*nu21)."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        nu21 = nu12_cf * E2_cf / E1_cf
        denom = 1.0 - nu12_cf * nu21
        Q12_expected = nu12_cf * E2_cf / denom
        assert abs(res["Q12"] - Q12_expected) / Q12_expected < REL

    def test_Q66_equals_G12(self):
        """Q66 = G12 (plane-stress assumption)."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        assert abs(res["Q66"] - G12_cf) / G12_cf < REL

    def test_Q_matrix_flat_shape(self):
        """Q returned as 9-element flat list."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        assert isinstance(res["Q"], list)
        assert len(res["Q"]) == 9

    def test_Q_symmetry(self):
        """Q[1] (row0 col1) == Q[3] (row1 col0) = Q12."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        Q = res["Q"]
        assert abs(Q[1] - Q[3]) < ABS  # Q[0,1] == Q[1,0]

    def test_Q_off_diagonal_zeros(self):
        """Q[0,2]=Q[1,2]=Q[2,0]=Q[2,1]=0 in principal axes."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        Q = res["Q"]
        assert abs(Q[2]) < ABS   # Q[0,2]
        assert abs(Q[5]) < ABS   # Q[1,2]
        assert abs(Q[6]) < ABS   # Q[2,0]
        assert abs(Q[7]) < ABS   # Q[2,1]

    def test_nu21_reciprocal(self):
        """nu21 = nu12 * E2/E1."""
        res = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        nu21_expected = nu12_cf * E2_cf / E1_cf
        assert abs(res["nu21"] - nu21_expected) / nu21_expected < REL

    def test_isotropic_material_Q11_eq_Q22(self):
        """For E1=E2, nu12=nu21, Q11==Q22."""
        E = 70e9
        nu = 0.3
        G = E / (2.0 * (1.0 + nu))
        res = reduced_stiffness(E, E, nu, G)
        assert res["ok"] is True
        assert abs(res["Q11"] - res["Q22"]) / res["Q11"] < REL

    def test_negative_E1_returns_error(self):
        res = reduced_stiffness(-181e9, 10.3e9, 0.28, 7.17e9)
        assert res["ok"] is False

    def test_negative_nu12_returns_error(self):
        res = reduced_stiffness(181e9, 10.3e9, -0.1, 7.17e9)
        assert res["ok"] is False

    def test_stability_violation_returns_error(self):
        """nu12 > sqrt(E1/E2) violates positive-definiteness."""
        # sqrt(181/10.3) ≈ 4.19; nu12=5 should fail
        res = reduced_stiffness(181e9, 10.3e9, 5.0, 7.17e9)
        assert res["ok"] is False


# ===========================================================================
# 2. transform_Q
# ===========================================================================

class TestTransformQ:

    def test_zero_angle_Q_bar_equals_Q(self):
        """At θ=0, Q̄ = Q (no transformation)."""
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_Qb = transform_Q(res_Q, 0.0)
        assert res_Qb["ok"] is True
        Q = res_Q["Q"]
        Qb = res_Qb["Q_bar"]
        # At 0°: Qb11=Q11, Qb22=Q22, Qb12=Q12, Qb66=Q66, Qb16=Qb26=0
        assert abs(Qb[0] - Q[0]) / Q[0] < REL   # Q_bar_11
        assert abs(Qb[4] - Q[4]) / Q[4] < REL   # Q_bar_22
        assert abs(Qb[1] - Q[1]) / Q[1] < REL   # Q_bar_12
        assert abs(Qb[8] - Q[8]) / Q[8] < REL   # Q_bar_66
        assert abs(Qb[2]) < ABS                  # Q_bar_16
        assert abs(Qb[5]) < ABS                  # Q_bar_26

    def test_90deg_Q11_becomes_Q22(self):
        """At θ=90°, Q̄11 = Q22 and Q̄22 = Q11."""
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_Qb = transform_Q(res_Q, 90.0)
        assert res_Qb["ok"] is True
        assert abs(res_Qb["Q_bar_11"] - res_Q["Q22"]) / res_Q["Q22"] < REL
        assert abs(res_Qb["Q_bar_22"] - res_Q["Q11"]) / res_Q["Q11"] < REL

    def test_90deg_Q16_Q26_near_zero(self):
        """At θ=90°, Q̄16 and Q̄26 should be ~0 (sin90=1, cos90=0 → c*s=0).
        Uses a loose tolerance because cos(pi/2) is ~6e-17, not exactly 0,
        so Q̄16 accumulates O(Q11 * cos90 * sin90) ≈ O(1e-7) floating point noise.
        """
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_Qb = transform_Q(res_Q, 90.0)
        # Loose relative tolerance: noise is ~1e-15 * Q11 ≈ a few hundred Pa
        ref = res_Qb["Q_bar_11"]
        assert abs(res_Qb["Q_bar_16"]) < 1e-6 * ref
        assert abs(res_Qb["Q_bar_26"]) < 1e-6 * ref

    def test_Q_bar_symmetry(self):
        """Q̄ must be symmetric: Q̄[0,1]==Q̄[1,0], Q̄[0,2]==Q̄[2,0], Q̄[1,2]==Q̄[2,1]."""
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_Qb = transform_Q(res_Q, 30.0)
        Qb = res_Qb["Q_bar"]
        assert abs(Qb[1] - Qb[3]) < ABS   # Q_bar[0,1] == Q_bar[1,0]
        assert abs(Qb[2] - Qb[6]) < ABS   # Q_bar[0,2] == Q_bar[2,0]
        assert abs(Qb[5] - Qb[7]) < ABS   # Q_bar[1,2] == Q_bar[2,1]

    def test_45deg_Q11_equals_Q22_by_symmetry(self):
        """At θ=45°, Q̄11 == Q̄22 for a typical anisotropic ply."""
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_Qb = transform_Q(res_Q, 45.0)
        # Verify: Q̄11 = Q̄22 at 45° because sin45=cos45
        assert abs(res_Qb["Q_bar_11"] - res_Qb["Q_bar_22"]) / res_Qb["Q_bar_11"] < REL

    def test_accepts_flat_list_directly(self):
        """transform_Q should accept a raw 9-element list as well as a dict."""
        res_Q = reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf)
        res_via_dict = transform_Q(res_Q, 30.0)
        res_via_list = transform_Q(res_Q["Q"], 30.0)
        assert abs(res_via_dict["Q_bar_11"] - res_via_list["Q_bar_11"]) < ABS


# ===========================================================================
# 3. abd_matrix
# ===========================================================================

class TestAbdMatrix:

    def test_single_ply_A_equals_Q_bar_times_t(self):
        """Single ply at 0°: A[0,0] = Q̄11 × t."""
        t = 0.125e-3
        plies = [_cf_ply(0.0, t)]
        res_abd = abd_matrix(plies)
        res_Qb = transform_Q(reduced_stiffness(E1_cf, E2_cf, nu12_cf, G12_cf), 0.0)
        assert res_abd["ok"] is True
        A = res_abd["A"]
        assert abs(A[0] - res_Qb["Q_bar_11"] * t) / (res_Qb["Q_bar_11"] * t) < REL

    def test_symmetric_laminate_B_near_zero(self):
        """[0/90]_s has B≈0 (symmetric)."""
        t = 0.125e-3
        plies = [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]
        res = abd_matrix(plies)
        assert res["ok"] is True
        B = res["B"]
        A_max = max(abs(v) for v in res["A"])
        for v in B:
            assert abs(v) < 1e-4 * A_max * t, f"B component {v} not near zero for symmetric laminate"
        assert res["is_symmetric"] is True

    def test_cross_ply_symmetric_balanced(self):
        """[0/90]_s is both symmetric and balanced (A16=A26=0)."""
        t = 0.125e-3
        plies = [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]
        res = abd_matrix(plies)
        assert res["ok"] is True
        assert res["is_symmetric"] is True
        assert res["is_balanced"] is True

    def test_quasi_isotropic_A11_approx_A22(self):
        """[0/±45/90]_s quasi-isotropic: A11 ≈ A22."""
        t = 0.125e-3
        angles = [0, 45, -45, 90, 90, -45, 45, 0]
        plies = [_cf_ply(a, t) for a in angles]
        res = abd_matrix(plies)
        assert res["ok"] is True
        A = res["A"]
        assert abs(A[0] - A[4]) / A[0] < 5e-3   # 0.5% tolerance for QI

    def test_total_thickness_correct(self):
        """Total thickness is sum of ply thicknesses."""
        plies = [_cf_ply(0, 0.125e-3), _cf_ply(90, 0.250e-3), _cf_ply(0, 0.125e-3)]
        res = abd_matrix(plies)
        assert abs(res["total_thickness"] - 0.5e-3) / 0.5e-3 < REL

    def test_n_plies_correct(self):
        plies = [_cf_ply(a) for a in [0, 45, -45, 90]]
        res = abd_matrix(plies)
        assert res["n_plies"] == 4

    def test_z_coords_midplane_at_zero(self):
        """z_coords span symmetrically around 0 for uniform plies."""
        t = 0.125e-3
        plies = [_cf_ply(a, t) for a in [0, 90, 0]]
        res = abd_matrix(plies)
        z = res["z_coords"]
        assert abs(z[0] + z[-1]) < ABS   # symmetric about z=0

    def test_empty_plies_returns_error(self):
        res = abd_matrix([])
        assert res["ok"] is False

    def test_missing_key_returns_error(self):
        res = abd_matrix([{"E1": 181e9, "E2": 10.3e9}])
        assert res["ok"] is False

    def test_negative_thickness_returns_error(self):
        ply = _cf_ply(0)
        ply["thickness"] = -0.001
        res = abd_matrix([ply])
        assert res["ok"] is False


# ===========================================================================
# 4. laminate_response
# ===========================================================================

class TestLaminateResponse:

    def _symmetric_laminate(self):
        t = 0.125e-3
        plies = [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]
        return abd_matrix(plies)

    def test_uniaxial_Nx_gives_nonzero_eps_x(self):
        """Uniaxial Nx → non-zero ε_x, response is ok."""
        abd = self._symmetric_laminate()
        resp = laminate_response(abd, [1000.0, 0, 0, 0, 0, 0])
        assert resp["ok"] is True
        assert resp["epsilon0"][0] > 0

    def test_symmetric_laminate_no_curvature_under_N(self):
        """For a symmetric laminate (B=0), in-plane N produces κ=0."""
        abd = self._symmetric_laminate()
        resp = laminate_response(abd, [1000.0, 0, 0, 0, 0, 0])
        assert resp["ok"] is True
        kappa = resp["kappa"]
        for k in kappa:
            assert abs(k) < 1e-3   # should be ~0 (numerical noise only)

    def test_solution_satisfies_ABD_equation(self):
        """Verify ABD × x ≈ [N,M] to within numerical tolerance."""
        abd = self._symmetric_laminate()
        N_M = [500.0, 200.0, 0.0, 0.0, 0.0, 0.0]
        resp = laminate_response(abd, N_M)
        assert resp["ok"] is True
        x = resp["response_vector"]
        ABD = abd["ABD"]
        # Compute ABD × x
        for i in range(6):
            row_dot = sum(ABD[i][j] * x[j] for j in range(6))
            assert abs(row_dot - N_M[i]) < 1e-3 * max(abs(N_M[i]), 1.0)

    def test_invalid_N_M_length_returns_error(self):
        abd = self._symmetric_laminate()
        resp = laminate_response(abd, [1.0, 2.0, 3.0])
        assert resp["ok"] is False

    def test_invalid_abd_returns_error(self):
        resp = laminate_response({"ok": False, "reason": "bad"}, [0]*6)
        assert resp["ok"] is False


# ===========================================================================
# 5. ply_stresses_strains
# ===========================================================================

class TestPlyStressesStrains:

    def test_unidirectional_0deg_uniaxial_stress_in_fibre_direction(self):
        """[0] laminate under Nx: fibre-direction stress s1 >> transverse s2."""
        t = 0.125e-3
        plies = [_cf_ply(0, t)]
        abd = abd_matrix(plies)
        resp = laminate_response(abd, [1000.0, 0, 0, 0, 0, 0])
        pss = ply_stresses_strains(abd, resp, plies)
        assert pss["ok"] is True
        s1 = pss["plies"][0]["stress_material"][0]
        s2 = pss["plies"][0]["stress_material"][1]
        assert s1 > 0
        assert abs(s1) > abs(s2)

    def test_strain_continuity_mid_plane(self):
        """For symmetric laminate under pure N, mid-ply strain should equal ε0."""
        t = 0.125e-3
        plies = [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]
        abd = abd_matrix(plies)
        resp = laminate_response(abd, [1000.0, 0, 0, 0, 0, 0])
        pss = ply_stresses_strains(abd, resp, plies)
        assert pss["ok"] is True
        eps0 = resp["epsilon0"]
        # Midplane of the laminate is between plies 1 and 2 (indices 1/2)
        # The top of ply 0 and bottom of ply 1 are near midplane
        # At z=0, strain_global should ≈ eps0
        # Find the ply closest to midplane
        z_coords = abd["z_coords"]
        for k, p_data in enumerate(pss["plies"]):
            z_mid = (z_coords[k] + z_coords[k+1]) / 2.0
            eps_g = p_data["strain_global"]
            # strain_global ≈ eps0 + z_mid * kappa (kappa ≈ 0 for symmetric)
            for i in range(3):
                expected = eps0[i] + z_mid * resp["kappa"][i]
                assert abs(eps_g[i] - expected) < ABS


# ===========================================================================
# 6. failure_indices
# ===========================================================================

class TestFailureIndices:

    def test_no_load_no_failure(self):
        """Zero stress/strain → no failure in any criterion."""
        fi = failure_indices(
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            S_cf,
        )
        assert fi["ok"] is True
        assert fi["failed"] is False

    def test_max_stress_fibre_failure(self):
        """σ1 = F1t → F.I.(max-stress) = 1.0 (onset)."""
        fi = failure_indices(
            [S_cf["F1t"], 0.0, 0.0],
            [1e-3, 0.0, 0.0],
            S_cf,
            criteria=["max-stress"],
        )
        assert fi["ok"] is True
        assert abs(fi["max_stress"]["fi"] - 1.0) < REL

    def test_max_stress_no_failure_below_strength(self):
        """σ1 = 0.5*F1t → F.I. < 1."""
        fi = failure_indices(
            [0.5 * S_cf["F1t"], 0.0, 0.0],
            [5e-4, 0.0, 0.0],
            S_cf,
            criteria=["max-stress"],
        )
        assert fi["max_stress"]["fi"] < 1.0
        assert fi["max_stress"]["failed"] is False

    def test_tsai_wu_low_stress_no_failure(self):
        """Low biaxial stress → Tsai-Wu F.I. < 1."""
        fi = failure_indices(
            [100e6, 10e6, 5e6],
            [5.5e-4, 9.7e-4, 7e-4],
            S_cf,
            criteria=["tsai-wu"],
        )
        assert fi["tsai_wu"]["fi"] < 1.0
        assert fi["tsai_wu"]["failed"] is False

    def test_tsai_wu_fibre_tension_fails(self):
        """σ1 >> F1t → Tsai-Wu F.I. > 1."""
        fi = failure_indices(
            [2.0 * S_cf["F1t"], 0.0, 0.0],
            [1.6e-2, 0.0, 0.0],
            S_cf,
            criteria=["tsai-wu"],
        )
        assert fi["tsai_wu"]["fi"] > 1.0
        assert fi["tsai_wu"]["failed"] is True

    def test_tsai_hill_onset(self):
        """σ2 = F2t alone → Tsai-Hill F.I.² ≈ 1 from transverse term."""
        fi = failure_indices(
            [0.0, S_cf["F2t"], 0.0],
            [0.0, 3.9e-3, 0.0],
            S_cf,
            criteria=["tsai-hill"],
        )
        assert abs(fi["tsai_hill"]["fi_squared"] - 1.0) < 1e-6

    def test_max_strain_with_allowables(self):
        """max-strain criterion uses provided allowable strains."""
        strengths = {**S_cf, "e1t": 8.3e-3, "e1c": 8.3e-3,
                     "e2t": 3.9e-3, "e2c": 2.4e-2, "g12_allow": 9.5e-3}
        fi = failure_indices(
            [100e6, 5e6, 3e6],
            [5.5e-4, 4.85e-4, 4.2e-4],
            strengths,
            criteria=["max-strain"],
        )
        assert fi["ok"] is True
        assert fi["max_strain"]["fi"] is not None
        assert fi["max_strain"]["fi"] < 1.0

    def test_max_strain_skipped_without_allowables(self):
        """max-strain returns fi=None when no strain allowables provided."""
        fi = failure_indices(
            [100e6, 5e6, 3e6],
            [5.5e-4, 4.85e-4, 4.2e-4],
            S_cf,     # no e1t, e1c, etc.
            criteria=["max-strain"],
        )
        assert fi["max_strain"]["fi"] is None

    def test_missing_strength_key_returns_error(self):
        bad_s = {"F1t": 1500e6}  # missing F1c, F2t, F2c, F12
        res = failure_indices([100e6, 5e6, 0.0], [1e-3, 0.0, 0.0], bad_s)
        assert res["ok"] is False


# ===========================================================================
# 7. laminate_engineering_moduli
# ===========================================================================

class TestLaminateEngineeringModuli:

    def test_single_0deg_ply_Ex_approx_E1(self):
        """Single 0° ply: effective Ex ≈ E1."""
        plies = [_cf_ply(0, 0.125e-3)]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        # Within 5% of E1 (some coupling due to nu12)
        assert abs(mod["Ex"] - E1_cf) / E1_cf < 0.05

    def test_quasi_isotropic_Ex_approx_Ey(self):
        """[0/±45/90]_s quasi-isotropic: Ex ≈ Ey."""
        t = 0.125e-3
        angles = [0, 45, -45, 90, 90, -45, 45, 0]
        plies = [_cf_ply(a, t) for a in angles]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        assert abs(mod["Ex"] - mod["Ey"]) / mod["Ex"] < 5e-3  # 0.5% tolerance

    def test_moduli_positive(self):
        """All engineering moduli must be positive."""
        plies = [_cf_ply(a) for a in [0, 45, -45, 90, 90, -45, 45, 0]]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        assert mod["Ex"] > 0
        assert mod["Ey"] > 0
        assert mod["Gxy"] > 0

    def test_nu_yx_reciprocal_relation(self):
        """nu_yx = nu_xy * Ex / Ey (Maxwell reciprocal)."""
        t = 0.125e-3
        plies = [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        nu_yx_expected = mod["nu_xy"] * mod["Ex"] / mod["Ey"]
        assert abs(mod["nu_yx"] - nu_yx_expected) < ABS

    def test_cross_ply_Ex_greater_than_Ey_for_more_0_plies(self):
        """[0/0/90] laminate: Ex > Ey because more 0° plies."""
        plies = [_cf_ply(0), _cf_ply(0), _cf_ply(90)]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        assert mod["Ex"] > mod["Ey"]


# ===========================================================================
# 8. first_ply_failure_load
# ===========================================================================

class TestFirstPlyFailureLoad:

    def _fpf_plies(self):
        t = 0.125e-3
        return [_cf_ply(0, t), _cf_ply(90, t), _cf_ply(90, t), _cf_ply(0, t)]

    def _fpf_strengths(self, n):
        return [S_cf.copy() for _ in range(n)]

    def test_fpf_returns_ok(self):
        plies = self._fpf_plies()
        res = first_ply_failure_load(
            plies,
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            self._fpf_strengths(4),
            criteria=["max-stress"],
        )
        assert res["ok"] is True

    def test_fpf_lambda_positive(self):
        plies = self._fpf_plies()
        res = first_ply_failure_load(
            plies,
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            self._fpf_strengths(4),
            criteria=["max-stress"],
        )
        assert res["lambda_fpf"] > 0

    def test_fpf_load_matches_lambda(self):
        """N_M_fpf = lambda_fpf * N_M_unit."""
        plies = self._fpf_plies()
        N_M_unit = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        res = first_ply_failure_load(
            plies, N_M_unit, self._fpf_strengths(4),
            criteria=["max-stress"],
        )
        lam = res["lambda_fpf"]
        for i in range(6):
            assert abs(res["N_M_fpf"][i] - lam * N_M_unit[i]) < ABS

    def test_fpf_strength_mismatch_returns_error(self):
        """Mismatch in plies vs strengths_list length → error."""
        plies = self._fpf_plies()
        res = first_ply_failure_load(
            plies, [1]*6, [S_cf],  # only 1 strength for 4 plies
            criteria=["max-stress"],
        )
        assert res["ok"] is False

    def test_fpf_empty_plies_returns_error(self):
        res = first_ply_failure_load([], [1]*6, [], criteria=["max-stress"])
        assert res["ok"] is False


# ===========================================================================
# 8b. CITABLE REFERENCE CASES — known numeric answers from textbooks
# ---------------------------------------------------------------------------
# Source: Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999),
#         Table 2-3 (T300/5208 graphite-epoxy) and §2.6/§2.7 worked
#         transformation example.  Gibson, R.F. "Principles of Composite
#         Material Mechanics", 4th ed., E-glass/epoxy properties.
# ===========================================================================

class TestCitableReferenceCases:

    def test_jones_T300_5208_Q_matrix(self):
        """Jones Table 2-3 (T300/5208): E1=181, E2=10.3 GPa, ν12=0.28,
        G12=7.17 GPa →  Q11=181.8 GPa, Q22=10.34 GPa, Q12=2.897 GPa,
        Q66=7.17 GPa  (reduced plane-stress stiffness)."""
        res = reduced_stiffness(181e9, 10.3e9, 0.28, 7.17e9)
        assert res["ok"] is True
        assert abs(res["Q11"] / 1e9 - 181.8) / 181.8 < 1e-3
        assert abs(res["Q22"] / 1e9 - 10.34) / 10.34 < 2e-3
        assert abs(res["Q12"] / 1e9 - 2.897) / 2.897 < 2e-3
        assert abs(res["Q66"] / 1e9 - 7.17) / 7.17 < 1e-6

    def test_jones_T300_5208_transform_45deg(self):
        """Jones §2.7 worked example, T300/5208 at θ=45°:
        Q̄11=Q̄22=56.66 GPa, Q̄12=42.32 GPa, Q̄66=46.59 GPa,
        Q̄16=Q̄26=42.87 GPa."""
        res_Q = reduced_stiffness(181e9, 10.3e9, 0.28, 7.17e9)
        qb = transform_Q(res_Q, 45.0)
        assert qb["ok"] is True
        assert abs(qb["Q_bar_11"] / 1e9 - 56.66) / 56.66 < 1e-3
        assert abs(qb["Q_bar_22"] / 1e9 - 56.66) / 56.66 < 1e-3
        assert abs(qb["Q_bar_12"] / 1e9 - 42.32) / 42.32 < 1e-3
        assert abs(qb["Q_bar_66"] / 1e9 - 46.59) / 46.59 < 1e-3
        assert abs(qb["Q_bar_16"] / 1e9 - 42.87) / 42.87 < 2e-3

    def test_transform_90deg_swaps_Q11_Q22_exact(self):
        """Jones §2.7: at θ=90° the transformed stiffness swaps
        Q̄11↔Q22 and Q̄22↔Q11 exactly (fibre rotated transverse)."""
        res_Q = reduced_stiffness(181e9, 10.3e9, 0.28, 7.17e9)
        qb = transform_Q(res_Q, 90.0)
        assert abs(qb["Q_bar_11"] - res_Q["Q22"]) / res_Q["Q22"] < 1e-9
        assert abs(qb["Q_bar_22"] - res_Q["Q11"]) / res_Q["Q11"] < 1e-9

    def test_gibson_eglass_epoxy_Q(self):
        """Gibson 4th ed. typical E-glass/epoxy: E1=38.6 GPa, E2=8.27 GPa,
        ν12=0.26, G12=4.14 GPa → Q11≈39.17 GPa, Q22≈8.39 GPa,
        Q12≈2.18 GPa (ν 21 = 0.26·8.27/38.6 = 0.0557)."""
        res = reduced_stiffness(38.6e9, 8.27e9, 0.26, 4.14e9)
        assert res["ok"] is True
        assert abs(res["Q11"] / 1e9 - 39.17) / 39.17 < 2e-3
        assert abs(res["Q22"] / 1e9 - 8.39) / 8.39 < 2e-3
        assert abs(res["Q12"] / 1e9 - 2.18) / 2.18 < 5e-3
        assert abs(res["nu21"] - 0.26 * 8.27 / 38.6) < 1e-9

    def test_unidirectional_0deg_Ex_equals_E1(self):
        """A single 0° ply laminate has effective Ex = E1 exactly and
        Ey = E2 exactly (Jones §2.5, lamina = laminate of one ply).
        T300/5208 → Ex = 181 GPa, Ey = 10.3 GPa."""
        plies = [_cf_ply(0.0, 0.125e-3)]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        assert abs(mod["Ex"] - 181e9) / 181e9 < 1e-3
        assert abs(mod["Ey"] - 10.3e9) / 10.3e9 < 1e-3
        assert abs(mod["nu_xy"] - 0.28) / 0.28 < 1e-3

    def test_quasi_isotropic_graphite_epoxy_modulus(self):
        """[0/±45/90]s quasi-isotropic T300/5208: the laminate is
        in-plane isotropic, Ex = Ey.  The QI plane-stress modulus from
        CLT is ≈ 69.7 GPa with ν_xy ≈ 0.30 (Jones §4.6, Daniel & Ishai
        QI laminate result)."""
        t = 0.125e-3
        angles = [0, 45, -45, 90, 90, -45, 45, 0]
        plies = [_cf_ply(a, t) for a in angles]
        abd = abd_matrix(plies)
        mod = laminate_engineering_moduli(abd)
        assert mod["ok"] is True
        assert abs(mod["Ex"] - mod["Ey"]) / mod["Ex"] < 1e-4
        assert abs(mod["Ex"] / 1e9 - 69.7) / 69.7 < 5e-3
        assert abs(mod["nu_xy"] - 0.30) / 0.30 < 0.02

    def test_tsai_wu_uniaxial_fibre_tension_onset(self):
        """Tsai-Wu (Jones §2.9; Tsai & Wu 1971) under pure σ1 reduces to
        F1·σ1 + F11·σ1² = 1 with F1 = 1/F1t − 1/F1c, F11 = 1/(F1t·F1c).
        With F1t=F1c (=1500 MPa) F1=0, so failure at σ1 = F1t exactly.
        F.I. at σ1 = F1t must equal 1.0."""
        fi = failure_indices(
            [S_cf["F1t"], 0.0, 0.0],
            [S_cf["F1t"] / 181e9, 0.0, 0.0],
            S_cf,
            criteria=["tsai-wu"],
        )
        assert fi["ok"] is True
        assert abs(fi["tsai_wu"]["fi"] - 1.0) < 1e-6

    def test_tsai_hill_transverse_tension_onset(self):
        """Tsai-Hill (Jones §2.9): under pure σ2, F.I.² = (σ2/F2t)².
        At σ2 = F2t the failure index squared is exactly 1.0."""
        fi = failure_indices(
            [0.0, S_cf["F2t"], 0.0],
            [0.0, S_cf["F2t"] / 10.3e9, 0.0],
            S_cf,
            criteria=["tsai-hill"],
        )
        assert fi["ok"] is True
        assert abs(fi["tsai_hill"]["fi_squared"] - 1.0) < 1e-9

    def test_max_stress_shear_onset(self):
        """Max-stress criterion (Jones §2.9): pure shear τ12 = F12 gives
        F.I. = |τ12|/F12 = 1.0 exactly (onset of shear failure)."""
        fi = failure_indices(
            [0.0, 0.0, S_cf["F12"]],
            [0.0, 0.0, S_cf["F12"] / 7.17e9],
            S_cf,
            criteria=["max-stress"],
        )
        assert fi["ok"] is True
        assert abs(fi["max_stress"]["fi"] - 1.0) < 1e-9


# ===========================================================================
# 9. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_reduced_stiffness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_composite_reduced_stiffness(ctx, _args(
            E1=181e9, E2=10.3e9, nu12=0.28, G12=7.17e9
        )))
        d = _ok_tool(raw)
        assert "Q11" in d
        assert d["Q11"] > 0

    def test_reduced_stiffness_missing_E1(self):
        ctx = _ctx()
        raw = _run(run_composite_reduced_stiffness(ctx, _args(
            E2=10.3e9, nu12=0.28, G12=7.17e9
        )))
        _err_tool(raw)

    def test_transform_Q_happy_path(self):
        ctx = _ctx()
        res_Q = reduced_stiffness(181e9, 10.3e9, 0.28, 7.17e9)
        raw = _run(run_composite_transform_Q(ctx, _args(
            Q=res_Q["Q"], theta_deg=45.0
        )))
        d = _ok_tool(raw)
        assert "Q_bar_11" in d

    def test_transform_Q_bad_Q_length(self):
        ctx = _ctx()
        raw = _run(run_composite_transform_Q(ctx, _args(Q=[1, 2, 3], theta_deg=30.0)))
        _err_tool(raw)

    def test_abd_matrix_happy_path(self):
        ctx = _ctx()
        plies = [
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 0},
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 90},
        ]
        raw = _run(run_composite_abd_matrix(ctx, _args(plies=plies)))
        d = _ok_tool(raw)
        assert "A" in d
        assert len(d["A"]) == 9

    def test_abd_matrix_missing_plies(self):
        ctx = _ctx()
        raw = _run(run_composite_abd_matrix(ctx, _args()))
        _err_tool(raw)

    def test_laminate_response_happy_path(self):
        ctx = _ctx()
        plies = [
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 0},
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 90},
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 90},
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": 0},
        ]
        abd_raw = _run(run_composite_abd_matrix(ctx, _args(plies=plies)))
        abd_d = _ok_tool(abd_raw)
        raw = _run(run_composite_laminate_response(ctx, _args(
            ABD=abd_d["ABD"], N_M=[1000.0, 0, 0, 0, 0, 0]
        )))
        d = _ok_tool(raw)
        assert "epsilon0" in d
        assert len(d["epsilon0"]) == 3

    def test_failure_indices_happy_path(self):
        ctx = _ctx()
        raw = _run(run_composite_failure_indices(ctx, _args(
            stress_material=[100e6, 10e6, 5e6],
            strain_material=[5.5e-4, 9.7e-4, 7e-4],
            strengths=S_cf,
        )))
        d = _ok_tool(raw)
        assert "failed" in d

    def test_failure_indices_missing_stress(self):
        ctx = _ctx()
        raw = _run(run_composite_failure_indices(ctx, _args(
            strain_material=[1e-3, 0.0, 0.0],
            strengths=S_cf,
        )))
        _err_tool(raw)

    def test_engineering_moduli_happy_path(self):
        ctx = _ctx()
        plies = [
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": a}
            for a in [0, 45, -45, 90, 90, -45, 45, 0]
        ]
        abd = abd_matrix(plies)
        raw = _run(run_composite_engineering_moduli(ctx, _args(
            A=abd["A"], total_thickness=abd["total_thickness"]
        )))
        d = _ok_tool(raw)
        assert d["Ex"] > 0
        assert d["Ey"] > 0
        assert d["Gxy"] > 0

    def test_first_ply_failure_happy_path(self):
        ctx = _ctx()
        plies = [
            {"E1": 181e9, "E2": 10.3e9, "nu12": 0.28, "G12": 7.17e9, "thickness": 0.125e-3, "angle_deg": a}
            for a in [0, 90, 90, 0]
        ]
        strengths = [S_cf.copy() for _ in range(4)]
        raw = _run(run_composite_first_ply_failure(ctx, _args(
            plies=plies,
            N_M_unit=[1.0, 0, 0, 0, 0, 0],
            strengths_list=strengths,
            criteria=["max-stress"],
        )))
        d = _ok_tool(raw)
        assert d["lambda_fpf"] > 0

    def test_first_ply_failure_bad_json(self):
        ctx = _ctx()
        raw = _run(run_composite_first_ply_failure(ctx, b"not-json"))
        _err_tool(raw)
