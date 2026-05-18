"""
Tests for kerf_composites — ply/layup CLT solver, failure criteria, drape.

DoD requirements verified:
  - A-matrix exact vs analytic CLT formula for a [0/90/0] symmetric laminate
  - Tsai-Wu failure index matches hand-calculated value to 1%
  - Drape map produces a flat→surface mapping (flat surface: identity; cylinder: geometry)
  - pytest analytic oracles throughout
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap (belt-and-suspenders alongside conftest)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_composites.layup import (
    Ply, PlyMaterial, LaminateLayup,
    T300_5208, EGLASS_EPOXY,
)
from kerf_composites.clt import (
    ply_Q_matrix,
    ply_Qbar_matrix,
    abd_matrices,
    effective_moduli,
)
from kerf_composites.failure import (
    PlyStress,
    tsai_wu_index,
    tsai_hill_index,
    reserve_factor_tsai_wu,
    reserve_factor_tsai_hill,
    laminate_failure_analysis,
)
from kerf_composites.drape import (
    DrapeResult,
    drape_flat_to_surface,
    flat_surface,
    cylindrical_surface,
)


# ===========================================================================
# Reference material constants for analytic checks
# ===========================================================================

# T300/5208 reference values (Reddy 2004, Example 3.2)
E1   = 181.0   # GPa
E2   = 10.3    # GPa
G12  = 7.17    # GPa
nu12 = 0.28
nu21 = nu12 * E2 / E1   # = 0.01591...
denom = 1.0 - nu12 * nu21

# Ply-level Q values (GPa) — analytic
Q11_ref = E1 / denom
Q22_ref = E2 / denom
Q12_ref = nu12 * E2 / denom
Q66_ref = G12


def make_unidirectional_ply(angle: float = 0.0, t: float = 0.125) -> Ply:
    return Ply(angle=angle, material=T300_5208, thickness=t)


# ===========================================================================
# Section 1: LaminateLayup data model
# ===========================================================================

class TestPlyMaterial:
    def test_nu21_reciprocal(self):
        m = T300_5208
        assert abs(m.nu21 - m.nu12 * m.E2 / m.E1) < 1e-12

    def test_negative_thickness_raises(self):
        with pytest.raises(ValueError, match="positive"):
            Ply(angle=0.0, material=T300_5208, thickness=-0.1)

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError):
            Ply(angle=0.0, material=T300_5208, thickness=0.0)


class TestLaminateLayup:
    def test_from_sequence_creates_plies(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
        assert layup.num_plies == 3
        assert layup.plies[1].angle == 90.0

    def test_total_thickness(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
        assert abs(layup.total_thickness - 0.375) < 1e-10

    def test_is_symmetric_true(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208)
        assert layup.is_symmetric is True

    def test_is_symmetric_false(self):
        layup = LaminateLayup.from_sequence([0, 90, 45], T300_5208)
        assert layup.is_symmetric is False

    def test_z_coords_length(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
        z = layup.z_coords
        assert len(z) == 4  # num_plies + 1

    def test_z_coords_symmetric_about_midplane(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
        z = layup.z_coords
        assert abs(z[0] + z[-1]) < 1e-12  # z[0] = -z[-1]
        assert abs(z[0] - (-0.1875)) < 1e-10

    def test_repr(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208)
        r = repr(layup)
        assert "LaminateLayup" in r
        assert "n=3" in r

    def test_empty_layup_num_plies(self):
        layup = LaminateLayup(plies=[])
        assert layup.num_plies == 0

    def test_single_ply(self):
        layup = LaminateLayup(plies=[Ply(0.0, T300_5208, 0.25)])
        assert layup.num_plies == 1
        assert abs(layup.total_thickness - 0.25) < 1e-12


# ===========================================================================
# Section 2: CLT Q and Q-bar matrices
# ===========================================================================

class TestQMatrix:
    """ply_Q_matrix returns analytic values."""

    def test_Q11(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert abs(Q[0, 0] - Q11_ref) < 1e-6, f"Q11={Q[0,0]:.6f} vs ref={Q11_ref:.6f}"

    def test_Q22(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert abs(Q[1, 1] - Q22_ref) < 1e-6

    def test_Q12(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert abs(Q[0, 1] - Q12_ref) < 1e-6

    def test_Q66(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert abs(Q[2, 2] - Q66_ref) < 1e-6

    def test_Q_shear_coupling_zero_0deg(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert abs(Q[0, 2]) < 1e-12
        assert abs(Q[1, 2]) < 1e-12

    def test_Q_symmetric(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        assert np.allclose(Q, Q.T)


class TestQbarMatrix:
    """ply_Qbar_matrix at 0° == Q; at 90° swaps Q11↔Q22."""

    def test_Qbar_0deg_equals_Q(self):
        ply = make_unidirectional_ply(0.0)
        Q = ply_Q_matrix(ply)
        Qbar = ply_Qbar_matrix(ply)
        assert np.allclose(Q, Qbar, atol=1e-8)

    def test_Qbar_90deg_swaps_11_22(self):
        ply = make_unidirectional_ply(90.0)
        Qbar = ply_Qbar_matrix(ply)
        # At 90°: Q̄11 = Q22, Q̄22 = Q11, Q̄12 = Q12, Q̄66 = Q66
        assert abs(Qbar[0, 0] - Q22_ref) < 1e-4, f"Qbar11 at 90°: {Qbar[0,0]:.4f} vs Q22={Q22_ref:.4f}"
        assert abs(Qbar[1, 1] - Q11_ref) < 1e-4, f"Qbar22 at 90°: {Qbar[1,1]:.4f} vs Q11={Q11_ref:.4f}"

    def test_Qbar_symmetric(self):
        for angle in [0, 15, 30, 45, 60, 90]:
            ply = make_unidirectional_ply(float(angle))
            Qbar = ply_Qbar_matrix(ply)
            assert np.allclose(Qbar, Qbar.T, atol=1e-8), f"Qbar not symmetric at {angle}°"

    def test_Qbar_45deg_has_coupling(self):
        ply = make_unidirectional_ply(45.0)
        Qbar = ply_Qbar_matrix(ply)
        # At 45°, Q̄16 and Q̄26 should be nonzero
        assert abs(Qbar[0, 2]) > 0.1

    def test_Qbar_minus_angle_Q16_negates(self):
        """Q̄16(+θ) = −Q̄16(−θ) for symmetric angles."""
        ply_p = make_unidirectional_ply(30.0)
        ply_m = make_unidirectional_ply(-30.0)
        Qbar_p = ply_Qbar_matrix(ply_p)
        Qbar_m = ply_Qbar_matrix(ply_m)
        assert abs(Qbar_p[0, 2] + Qbar_m[0, 2]) < 1e-6


# ===========================================================================
# Section 3: ABD matrices — analytic oracle (DoD requirement)
# ===========================================================================

class TestABDMatrices:
    """
    Analytic oracle for a [0/90/0] symmetric laminate.

    Reference: Reddy (2004), §4.3, Example 4.3 / Jones (1975), §4.3.

    For a symmetric laminate:
      B = 0  (coupling matrix vanishes for symmetric layup)

    For a 3-ply [0/90/0] with uniform ply thickness t = 0.125 mm and
    T300/5208 material:
      h = 3t = 0.375 mm
      z = [-0.1875, -0.0625, 0.0625, 0.1875] mm

    A11 = Q̄11(0°)·2t + Q̄11(90°)·t
        = Q11·2t + Q22·t
        = (2·Q11 + Q22) · t

    A22 = Q̄22(0°)·2t + Q̄22(90°)·t
        = Q22·2t + Q11·t
        = (2·Q22 + Q11) · t

    A12 = Q̄12(0°)·2t + Q̄12(90°)·t
        = Q12·3t    (Q12 invariant under 0→90° rotation)

    A66 = Q66·3t   (Q66 invariant)

    All multiplied by 1000 (GPa·mm → N/mm).
    """

    def _layup_0_90_0(self, t: float = 0.125) -> LaminateLayup:
        return LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=t)

    def _analytic_A(self, t: float = 0.125) -> np.ndarray:
        """Compute A analytically for [0/90/0] layup."""
        A11 = (2 * Q11_ref + Q22_ref) * t * 1.0e3
        A22 = (2 * Q22_ref + Q11_ref) * t * 1.0e3
        A12 = Q12_ref * 3 * t * 1.0e3
        A66 = Q66_ref * 3 * t * 1.0e3
        return np.array([
            [A11, A12, 0.0],
            [A12, A22, 0.0],
            [0.0, 0.0, A66],
        ])

    def test_A11_matches_analytic(self):
        """A-matrix [0,0] element exact vs CLT formula (DoD)."""
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        A_ref = self._analytic_A()
        rel_err = abs(A[0, 0] - A_ref[0, 0]) / abs(A_ref[0, 0])
        assert rel_err < 1e-8, (
            f"A11={A[0,0]:.4f} vs analytic={A_ref[0,0]:.4f}, rel_err={rel_err:.2e}"
        )

    def test_A22_matches_analytic(self):
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        A_ref = self._analytic_A()
        rel_err = abs(A[1, 1] - A_ref[1, 1]) / abs(A_ref[1, 1])
        assert rel_err < 1e-8, f"A22 rel_err={rel_err:.2e}"

    def test_A12_matches_analytic(self):
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        A_ref = self._analytic_A()
        rel_err = abs(A[0, 1] - A_ref[0, 1]) / abs(A_ref[0, 1])
        assert rel_err < 1e-8, f"A12 rel_err={rel_err:.2e}"

    def test_A66_matches_analytic(self):
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        A_ref = self._analytic_A()
        rel_err = abs(A[2, 2] - A_ref[2, 2]) / abs(A_ref[2, 2])
        assert rel_err < 1e-8, f"A66 rel_err={rel_err:.2e}"

    def test_full_A_matrix_matches_analytic(self):
        """Full A-matrix matches analytic formula element-by-element."""
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        A_ref = self._analytic_A()
        assert np.allclose(A, A_ref, rtol=1e-7, atol=1e-4), (
            f"A matrix mismatch:\n{A}\nvs analytic:\n{A_ref}"
        )

    def test_B_zero_for_symmetric_layup(self):
        """B matrix must vanish for any symmetric laminate."""
        layup = self._layup_0_90_0()
        _, B, _ = abd_matrices(layup)
        assert np.allclose(B, 0.0, atol=1e-8), f"B not zero for symmetric:\n{B}"

    def test_B_nonzero_for_asymmetric(self):
        """B non-zero for [0/90] asymmetric layup."""
        layup = LaminateLayup.from_sequence([0, 90], T300_5208, ply_thickness=0.125)
        _, B, _ = abd_matrices(layup)
        assert not np.allclose(B, 0.0, atol=1e-2), "B should be non-zero for asymmetric layup"

    def test_D_positive_definite(self):
        """D matrix must be positive definite (real physical laminate)."""
        layup = self._layup_0_90_0()
        _, _, D = abd_matrices(layup)
        eigvals = np.linalg.eigvalsh(D)
        assert np.all(eigvals > 0.0), f"D not positive definite; eigvals={eigvals}"

    def test_A_symmetric(self):
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        assert np.allclose(A, A.T, atol=1e-10)

    def test_D_symmetric(self):
        layup = self._layup_0_90_0()
        _, _, D = abd_matrices(layup)
        assert np.allclose(D, D.T, atol=1e-10)

    def test_thicker_plies_larger_A(self):
        """Doubling ply thickness doubles A."""
        layup_thin = self._layup_0_90_0(t=0.125)
        layup_thick = self._layup_0_90_0(t=0.250)
        A_thin, _, _ = abd_matrices(layup_thin)
        A_thick, _, _ = abd_matrices(layup_thick)
        assert np.allclose(A_thick, 2.0 * A_thin, rtol=1e-8)

    def test_empty_layup_raises(self):
        layup = LaminateLayup(plies=[])
        with pytest.raises(ValueError, match="no plies"):
            abd_matrices(layup)

    def test_isotropic_layup_equal_A11_A22(self):
        """Quasi-isotropic [0/45/-45/90]_s → A11 ≈ A22."""
        angles = [0, 45, -45, 90, 90, -45, 45, 0]
        layup = LaminateLayup.from_sequence(angles, T300_5208, ply_thickness=0.125)
        A, _, _ = abd_matrices(layup)
        rel_diff = abs(A[0, 0] - A[1, 1]) / A[0, 0]
        assert rel_diff < 1e-6, f"A11={A[0,0]:.3f} A22={A[1,1]:.3f} for QI layup"

    def test_crossply_A16_A26_zero(self):
        """[0/90/0] has zero shear-extension coupling (A16 = A26 = 0)."""
        layup = self._layup_0_90_0()
        A, _, _ = abd_matrices(layup)
        assert abs(A[0, 2]) < 1e-8, f"A16 = {A[0,2]:.2e}"
        assert abs(A[1, 2]) < 1e-8, f"A26 = {A[1,2]:.2e}"


class TestEffectiveModuli:
    def test_Ex_positive(self):
        layup = LaminateLayup.from_sequence([0, 90, 0], T300_5208, ply_thickness=0.125)
        m = effective_moduli(layup)
        assert m["Ex"] > 0

    def test_unidirectional_Ex_close_to_E1(self):
        """Unidirectional 0° laminate → Ex ≈ E1."""
        layup = LaminateLayup.from_sequence([0, 0, 0, 0], T300_5208, ply_thickness=0.125)
        m = effective_moduli(layup)
        assert abs(m["Ex"] - E1) / E1 < 0.01, f"Ex={m['Ex']:.3f} vs E1={E1}"

    def test_unidirectional_Ey_close_to_E2(self):
        """Unidirectional 0° laminate → Ey ≈ E2."""
        layup = LaminateLayup.from_sequence([0, 0, 0, 0], T300_5208, ply_thickness=0.125)
        m = effective_moduli(layup)
        assert abs(m["Ey"] - E2) / E2 < 0.01, f"Ey={m['Ey']:.3f} vs E2={E2}"

    def test_QI_moduli_isotropic(self):
        """Quasi-isotropic laminate → Ex ≈ Ey."""
        angles = [0, 45, -45, 90, 90, -45, 45, 0]
        layup = LaminateLayup.from_sequence(angles, T300_5208, ply_thickness=0.125)
        m = effective_moduli(layup)
        assert abs(m["Ex"] - m["Ey"]) / m["Ex"] < 1e-5


# ===========================================================================
# Section 4: Tsai-Wu failure index — analytic oracle (DoD requirement)
# ===========================================================================

class TestTsaiWuIndex:
    """
    Hand-calculated Tsai-Wu failure index for T300/5208 ply.

    Material strengths (MPa):
      Xt=1500, Xc=1500, Yt=40, Yc=246, S12=68

    F1  = 1/1500 - 1/1500 = 0
    F2  = 1/40   - 1/246  = 0.025 - 0.004065 = 0.020935
    F11 = 1/(1500·1500)   = 4.444e-7
    F22 = 1/(40·246)      = 1.0163e-4
    F66 = 1/68²           = 2.1626e-4
    F12 = -0.5 · √(F11·F22) = -0.5 · √(4.444e-7 · 1.0163e-4)
        = -0.5 · √(4.516e-11)
        = -0.5 · 6.721e-6
        = -3.360e-6

    Test load: σ1 = 200 MPa, σ2 = 10 MPa, τ12 = 5 MPa

    FI = F1·200 + F2·10 + F11·200² + F22·10² + F66·5² + 2·F12·200·10
       = 0
         + 0.020935·10
         + 4.444e-7·40000
         + 1.0163e-4·100
         + 2.1626e-4·25
         + 2·(-3.360e-6)·2000
       = 0.20935 + 0.017776 + 0.010163 + 0.005407 - 0.013441
       = 0.229255

    Computed below to verify the implementation matches to within 1%.
    """

    M = T300_5208

    def _hand_calc_fi(self) -> float:
        m = self.M
        s1, s2, t12 = 200.0, 10.0, 5.0
        F1  = 1/m.Xt - 1/m.Xc
        F2  = 1/m.Yt - 1/m.Yc
        F11 = 1/(m.Xt * m.Xc)
        F22 = 1/(m.Yt * m.Yc)
        F66 = 1/(m.S12 ** 2)
        F12 = -0.5 * math.sqrt(F11 * F22)
        fi = (
            F1 * s1 + F2 * s2
            + F11 * s1**2 + F22 * s2**2
            + F66 * t12**2
            + 2 * F12 * s1 * s2
        )
        return fi

    def test_tsai_wu_matches_hand_calc_to_1pct(self):
        """Tsai-Wu FI matches hand-calculated value to 1% (DoD)."""
        stress = PlyStress(sigma1=200.0, sigma2=10.0, tau12=5.0)
        fi_code = tsai_wu_index(stress, self.M, F12_star=-0.5)
        fi_ref = self._hand_calc_fi()
        rel_err = abs(fi_code - fi_ref) / abs(fi_ref)
        assert rel_err < 0.01, (
            f"Tsai-Wu FI={fi_code:.6f} vs hand-calc={fi_ref:.6f}, "
            f"rel_err={rel_err:.4%}"
        )

    def test_tsai_wu_below_1_safe_load(self):
        """Low stress → FI < 1 (safe)."""
        stress = PlyStress(sigma1=200.0, sigma2=10.0, tau12=5.0)
        fi = tsai_wu_index(stress, self.M)
        assert fi < 1.0, f"Expected FI < 1 for moderate load, got {fi:.4f}"

    def test_tsai_wu_above_1_at_ultimate(self):
        """Stress at 110% of Xt → FI > 1 (failure)."""
        stress = PlyStress(sigma1=1.1 * self.M.Xt, sigma2=0.0, tau12=0.0)
        fi = tsai_wu_index(stress, self.M)
        assert fi > 1.0, f"Expected FI > 1 at 110% Xt, got {fi:.4f}"

    def test_tsai_wu_pure_shear_failure(self):
        """Pure shear at S12 → FI ≈ 1."""
        stress = PlyStress(sigma1=0.0, sigma2=0.0, tau12=self.M.S12)
        fi = tsai_wu_index(stress, self.M)
        assert abs(fi - 1.0) < 0.01, f"Pure shear at S12: FI={fi:.4f}"

    def test_tsai_wu_zero_stress_near_zero(self):
        """Zero stress → FI ≈ 0 (linear term is also zero for balanced Xt=Xc)."""
        stress = PlyStress(sigma1=0.0, sigma2=0.0, tau12=0.0)
        fi = tsai_wu_index(stress, self.M)
        assert abs(fi) < 1e-10

    def test_reserve_factor_safe(self):
        stress = PlyStress(sigma1=200.0, sigma2=10.0, tau12=5.0)
        rf = reserve_factor_tsai_wu(stress, self.M)
        assert rf > 1.0

    def test_reserve_factor_failed(self):
        stress = PlyStress(sigma1=1.1 * self.M.Xt, sigma2=0.0, tau12=0.0)
        rf = reserve_factor_tsai_wu(stress, self.M)
        assert rf < 1.0


class TestTsaiHillIndex:
    M = T300_5208

    def test_tsai_hill_pure_longitudinal_at_Xt(self):
        """At σ1 = Xt, FI = 1 (by definition of Tsai-Hill)."""
        stress = PlyStress(sigma1=self.M.Xt, sigma2=0.0, tau12=0.0)
        fi = tsai_hill_index(stress, self.M)
        assert abs(fi - 1.0) < 1e-10, f"TH FI at σ1=Xt: {fi:.6f}"

    def test_tsai_hill_pure_transverse_at_Yt(self):
        """At σ2 = Yt, FI = 1."""
        stress = PlyStress(sigma1=0.0, sigma2=self.M.Yt, tau12=0.0)
        fi = tsai_hill_index(stress, self.M)
        assert abs(fi - 1.0) < 1e-10, f"TH FI at σ2=Yt: {fi:.6f}"

    def test_tsai_hill_pure_shear_at_S12(self):
        """At τ12 = S12, FI = 1."""
        stress = PlyStress(sigma1=0.0, sigma2=0.0, tau12=self.M.S12)
        fi = tsai_hill_index(stress, self.M)
        assert abs(fi - 1.0) < 1e-10, f"TH FI at τ12=S12: {fi:.6f}"

    def test_tsai_hill_below_1_safe(self):
        stress = PlyStress(sigma1=100.0, sigma2=5.0, tau12=10.0)
        fi = tsai_hill_index(stress, self.M)
        assert fi < 1.0

    def test_tsai_hill_compressive_uses_Xc(self):
        """Compressive σ1 uses Xc not Xt."""
        # With Xt = Xc = 1500, result should be same sign
        stress_t = PlyStress(sigma1=self.M.Xt, sigma2=0.0, tau12=0.0)
        stress_c = PlyStress(sigma1=-self.M.Xc, sigma2=0.0, tau12=0.0)
        fi_t = tsai_hill_index(stress_t, self.M)
        fi_c = tsai_hill_index(stress_c, self.M)
        # Both should be ≈ 1.0 since Xt == Xc for T300/5208
        assert abs(fi_t - fi_c) < 1e-10

    def test_reserve_factor_tsai_hill_safe(self):
        stress = PlyStress(sigma1=100.0, sigma2=5.0, tau12=10.0)
        rf = reserve_factor_tsai_hill(stress, self.M)
        assert rf > 1.0


class TestLaminateFailureAnalysis:
    M = T300_5208

    def test_returns_list(self):
        stresses = [PlyStress(100.0, 5.0, 5.0)] * 3
        mats = [self.M] * 3
        angles = [0.0, 90.0, 0.0]
        results = laminate_failure_analysis(stresses, mats, angles)
        assert len(results) == 3

    def test_failed_ply_detected(self):
        # 110% Xt loading
        stresses = [PlyStress(1.1 * self.M.Xt, 0.0, 0.0)]
        results = laminate_failure_analysis(stresses, [self.M], [0.0])
        assert results[0].failed_tsai_wu is True
        assert results[0].failed_tsai_hill is True

    def test_safe_ply_not_failed(self):
        stresses = [PlyStress(100.0, 5.0, 5.0)]
        results = laminate_failure_analysis(stresses, [self.M], [0.0])
        assert results[0].failed_tsai_wu is False

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError, match="equal length"):
            laminate_failure_analysis(
                [PlyStress(0, 0, 0)],
                [self.M, self.M],
                [0.0],
            )


# ===========================================================================
# Section 5: Drape simulation (DoD requirement)
# ===========================================================================

class TestDrapeFlat:
    """Flat surface: draped coordinates are identity mapping in x,y with z=0."""

    def test_returns_drape_result(self):
        result = drape_flat_to_surface(flat_surface(0.0), (0, 100), (0, 100), nu=5, nv=5)
        assert isinstance(result, DrapeResult)

    def test_flat_shape(self):
        result = drape_flat_to_surface(flat_surface(0.0), (0, 100), (0, 100), nu=5, nv=5)
        assert result.flat_coords.shape == (5, 5, 2)
        assert result.surf_coords.shape == (5, 5, 3)

    def test_flat_identity_mapping(self):
        """Draped onto flat z=0 surface: surf_coords[:,:,0]=u, [:,:,1]=v, [:,:,2]=0."""
        result = drape_flat_to_surface(flat_surface(0.0), (0.0, 100.0), (0.0, 50.0), nu=6, nv=4)
        # x-coords should match u grid
        us = np.linspace(0.0, 100.0, 6)
        vs = np.linspace(0.0, 50.0, 4)
        for i in range(6):
            for j in range(4):
                assert abs(result.surf_coords[i, j, 0] - us[i]) < 1e-10, "x mismatch"
                assert abs(result.surf_coords[i, j, 1] - vs[j]) < 1e-10, "y mismatch"
                assert abs(result.surf_coords[i, j, 2] - 0.0) < 1e-10, "z mismatch"

    def test_flat_shear_angles_near_zero(self):
        """Flat surface → shear angles ≈ 0° (no distortion)."""
        result = drape_flat_to_surface(flat_surface(0.0), (0, 100), (0, 100), nu=6, nv=6)
        # All shear angles on a flat surface should be ~0°
        interior = result.shear_angles[:-1, :-1]
        assert np.all(interior < 1.0), f"max shear={interior.max():.4f}° on flat"

    def test_flat_coords_correct(self):
        """flat_coords should contain the original u, v grid."""
        result = drape_flat_to_surface(flat_surface(0.0), (0.0, 10.0), (0.0, 5.0), nu=3, nv=3)
        assert abs(result.flat_coords[0, 0, 0] - 0.0) < 1e-10
        assert abs(result.flat_coords[2, 0, 0] - 10.0) < 1e-10
        assert abs(result.flat_coords[0, 2, 1] - 5.0) < 1e-10

    def test_flat_nu_nv_stored(self):
        result = drape_flat_to_surface(flat_surface(0.0), (0, 10), (0, 10), nu=4, nv=7)
        assert result.nu == 4
        assert result.nv == 7

    def test_flat_too_few_points_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            drape_flat_to_surface(flat_surface(0.0), (0, 10), (0, 10), nu=1, nv=5)


class TestDrapeCylinder:
    """Cylindrical surface: verify that surf_coords lie on the cylinder."""

    def test_cylinder_surf_points_on_surface(self):
        """All draped points lie on a cylinder of radius R."""
        R = 500.0  # mm
        surf_fn = cylindrical_surface(radius=R, axis="x")
        result = drape_flat_to_surface(
            surf_fn,
            u_range=(0.0, 30.0),    # degrees of arc
            v_range=(0.0, 100.0),   # mm along axis
            nu=5, nv=5,
        )
        # surf_coords[i,j] = (v, R*cos(u_deg), R*sin(u_deg))
        # → dist from x-axis = sqrt(y²+z²) = R
        for i in range(result.nu):
            for j in range(result.nv):
                x, y, z = result.surf_coords[i, j]
                dist = math.sqrt(y**2 + z**2)
                assert abs(dist - R) < 1e-6, (
                    f"Point ({i},{j}): dist from axis = {dist:.6f}, expected R={R}"
                )

    def test_cylinder_flat_coords_preserved(self):
        """flat_coords are the flat-sheet (u, v) grid regardless of surface."""
        R = 300.0
        surf_fn = cylindrical_surface(radius=R, axis="x")
        result = drape_flat_to_surface(surf_fn, (0.0, 45.0), (0.0, 200.0), nu=4, nv=4)
        us = np.linspace(0.0, 45.0, 4)
        vs = np.linspace(0.0, 200.0, 4)
        for i in range(4):
            for j in range(4):
                assert abs(result.flat_coords[i, j, 0] - us[i]) < 1e-10
                assert abs(result.flat_coords[i, j, 1] - vs[j]) < 1e-10

    def test_drape_different_surface_different_coords(self):
        """Flat and curved surfaces give different surf_coords."""
        u_range = (0.0, 30.0)
        v_range = (0.0, 100.0)
        res_flat = drape_flat_to_surface(flat_surface(0.0), u_range, v_range, nu=5, nv=5)
        res_cyl = drape_flat_to_surface(cylindrical_surface(500.0), u_range, v_range, nu=5, nv=5)
        # The surf_coords must be different for non-trivial u
        assert not np.allclose(res_flat.surf_coords, res_cyl.surf_coords)


# ===========================================================================
# Section 6: Module import / py_compile smoke tests
# ===========================================================================

class TestModuleImports:
    def test_layup_imports(self):
        import kerf_composites.layup  # noqa: F401

    def test_clt_imports(self):
        import kerf_composites.clt  # noqa: F401

    def test_failure_imports(self):
        import kerf_composites.failure  # noqa: F401

    def test_drape_imports(self):
        import kerf_composites.drape  # noqa: F401

    def test_tools_imports(self):
        import kerf_composites.tools  # noqa: F401

    def test_plugin_imports(self):
        import kerf_composites.plugin  # noqa: F401

    def test_pycompile_layup(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_composites", "layup.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_clt(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_composites", "clt.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_failure(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_composites", "failure.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_drape(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_composites", "drape.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_composites", "tools.py")
        py_compile.compile(path, doraise=True)
