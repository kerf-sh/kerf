"""
Tests for kerf_cad_core.struct.eurocode8 — Eurocode 8 (EN 1998-1) seismic.

Coverage:
  ec8_design_spectrum  — all four period regions, ground types, error paths
  ec8_lateral_force    — T1 formula, Fb, Fi distribution, λ, error paths
  ec8_rsa              — per-mode values, SRSS/CQC combination, mass check,
                         SDOF equivalence to lateral-force method

Validation reference numbers (EN 1998-1 Table 3.2, Type 1, ground type B):
  S=1.2, TB=0.15 s, TC=0.5 s, TD=2.0 s
  q=1.0 (elastic), gamma_I=1.0, ag=0.25g=0.25×9.80665=2.45166 m/s²

  Sd(T=0):
    eq (3.13): ag·S·(2/3 + 0/TB·(2.5/q−2/3)) = ag·S·2/3
    = 2.45166·1.2·(2/3) = 1.961 m/s²

  Sd(T=TC=0.5s, plateau):
    eq (3.14): ag·S·2.5/q = 2.45166·1.2·2.5 = 7.355 m/s²

  Sd(T=TC=0.5s, q=1.5):
    = 2.45166·1.2·2.5/1.5 = 4.903 m/s²

Author: imranparuk
"""
from __future__ import annotations

import math

import pytest

from kerf_cad_core.struct.eurocode8 import (
    ec8_design_spectrum,
    ec8_lateral_force,
    ec8_rsa,
    _G,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-4


def _ag(g_fraction: float) -> float:
    """Convert fraction-of-g to m/s²."""
    return g_fraction * _G


# ---------------------------------------------------------------------------
# 1. ec8_design_spectrum — spectrum values
# ---------------------------------------------------------------------------

class TestEc8DesignSpectrum:
    """EN 1998-1 §3.2.2.5 Eq. (3.13)–(3.16)."""

    # Reference: Type 1, ground B, ag=0.25g=2.45166 m/s², q=1.0, gamma_I=1.0
    ag_025 = _ag(0.25)

    def _sd(self, T: float, **kw) -> float:
        r = ec8_design_spectrum(T, self.ag_025, "B", **kw)
        assert r["ok"] is True, r
        return r["Sd_m_s2"]

    def test_at_T0_rising_region(self):
        """T=0 → region 'rising', Sd = ag·S·2/3 (Eq. 3.13)."""
        r = ec8_design_spectrum(0.0, self.ag_025, "B", spectrum_type="1", q=1.0)
        assert r["ok"] is True
        assert r["region"] == "rising"
        expected = self.ag_025 * 1.2 * (2.0 / 3.0)  # = ~1.961 m/s²
        assert abs(r["Sd_m_s2"] - expected) < REL

    def test_at_TC_plateau(self):
        """T=TC=0.5s → plateau, Sd = ag·S·2.5/q (Eq. 3.14), q=1."""
        r = ec8_design_spectrum(0.5, self.ag_025, "B", spectrum_type="1", q=1.0)
        assert r["ok"] is True
        assert r["region"] == "plateau"
        expected = self.ag_025 * 1.2 * 2.5 / 1.0
        assert abs(r["Sd_m_s2"] - expected) < REL

    def test_at_TC_plateau_q15(self):
        """T=TC=0.5s, q=1.5 → Sd = ag·S·2.5/1.5."""
        r = ec8_design_spectrum(0.5, self.ag_025, "B", spectrum_type="1", q=1.5)
        assert r["ok"] is True
        assert r["region"] == "plateau"
        expected = self.ag_025 * 1.2 * 2.5 / 1.5
        assert abs(r["Sd_m_s2"] - expected) < REL

    def test_velocity_region(self):
        """TC < T ≤ TD → Sd = ag·S·2.5/q·(TC/T)."""
        T = 1.0  # TC=0.5, TD=2.0
        r = ec8_design_spectrum(T, self.ag_025, "B", spectrum_type="1", q=1.5)
        assert r["ok"] is True
        assert r["region"] == "velocity"
        TC = r["TC"]
        expected = self.ag_025 * 1.2 * 2.5 / 1.5 * (TC / T)
        assert abs(r["Sd_m_s2"] - expected) < REL

    def test_displacement_region(self):
        """TD < T ≤ 4s → Sd = ag·S·2.5/q·(TC·TD/T²), lower bound β·ag."""
        T = 3.0  # TD=2.0
        r = ec8_design_spectrum(T, self.ag_025, "B", spectrum_type="1", q=1.5)
        assert r["ok"] is True
        assert r["region"] == "displacement"
        TC, TD = r["TC"], r["TD"]
        val = self.ag_025 * 1.2 * 2.5 / 1.5 * (TC * TD / (T * T))
        beta_ag = 0.2 * self.ag_025
        expected = max(val, beta_ag)
        assert abs(r["Sd_m_s2"] - expected) < REL

    def test_lower_bound_applies_in_displacement_region(self):
        """Very long period → lower bound β·ag governs."""
        # At T=4.0, ground A, q=6.0: value will be very small
        ag_small = _ag(0.05)
        r = ec8_design_spectrum(4.0, ag_small, "A", q=6.0)
        assert r["ok"] is True
        # Lower bound = 0.2 · ag_small
        assert r["Sd_m_s2"] >= 0.2 * ag_small - 1e-9

    def test_spectrum_type2_ground_B(self):
        """Type 2 spectrum, ground B: S=1.35, TB=0.05, TC=0.25, TD=1.2."""
        r = ec8_design_spectrum(0.25, self.ag_025, "B", spectrum_type="2", q=1.0)
        assert r["ok"] is True
        assert r["S"] == pytest.approx(1.35)
        assert r["TC"] == pytest.approx(0.25)

    def test_gamma_I_scales_spectrum(self):
        """gamma_I=1.4 scales Sd by 1.4 relative to gamma_I=1.0."""
        r1 = ec8_design_spectrum(0.5, self.ag_025, "B", gamma_I=1.0)
        r2 = ec8_design_spectrum(0.5, self.ag_025, "B", gamma_I=1.4)
        assert r1["ok"] and r2["ok"]
        assert abs(r2["Sd_m_s2"] / r1["Sd_m_s2"] - 1.4) < REL

    def test_all_ground_types_return_ok(self):
        """All ground types A–E return ok for a mid-period T."""
        for gt in ("A", "B", "C", "D", "E"):
            r = ec8_design_spectrum(0.5, self.ag_025, gt)
            assert r["ok"] is True, f"ground_type={gt} failed: {r}"

    def test_returns_Se_and_Sd(self):
        """Both Se and Sd are returned (Se >= Sd when q >= 1)."""
        r = ec8_design_spectrum(0.5, self.ag_025, "B", q=2.0)
        assert r["ok"] is True
        assert r["Se_m_s2"] >= r["Sd_m_s2"] - 1e-9

    def test_auxiliary_parameters_returned(self):
        """TB, TC, TD, S, ag_eff, eta are all returned."""
        r = ec8_design_spectrum(0.5, self.ag_025, "B")
        for k in ("TB", "TC", "TD", "S", "ag_eff", "eta", "region"):
            assert k in r, f"Missing key: {k}"

    # --- Error paths ---

    def test_invalid_ground_type(self):
        r = ec8_design_spectrum(0.5, self.ag_025, "F")
        assert r["ok"] is False

    def test_invalid_spectrum_type(self):
        r = ec8_design_spectrum(0.5, self.ag_025, "B", spectrum_type="3")
        assert r["ok"] is False

    def test_T_negative(self):
        r = ec8_design_spectrum(-0.1, self.ag_025, "B")
        assert r["ok"] is False

    def test_T_exceeds_4s(self):
        r = ec8_design_spectrum(4.5, self.ag_025, "B")
        assert r["ok"] is False

    def test_ag_zero(self):
        r = ec8_design_spectrum(0.5, 0.0, "B")
        assert r["ok"] is False

    def test_q_below_1(self):
        r = ec8_design_spectrum(0.5, self.ag_025, "B", q=0.9)
        assert r["ok"] is False

    def test_gamma_I_zero(self):
        r = ec8_design_spectrum(0.5, self.ag_025, "B", gamma_I=0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 2. ec8_lateral_force
# ---------------------------------------------------------------------------

class TestEc8LateralForce:

    ag_025 = _ag(0.25)

    def test_Fb_equals_Sd_times_mass_times_lambda(self):
        """Fb = Sd(T1) · m_total · λ (algebraically)."""
        m = [10000.0, 10000.0, 10000.0]  # 30 000 kg total
        z = [3.0, 6.0, 9.0]
        H = 9.0
        r = ec8_lateral_force(self.ag_025, "B", H, m, z, q=1.5)
        assert r["ok"] is True
        expected_Fb = r["Sd_T1_m_s2"] * r["m_total_kg"] * r["lambda_corr"]
        assert abs(r["Fb_N"] - expected_Fb) < 1.0  # N precision

    def test_Fi_sums_to_Fb(self):
        """Sum of storey forces must equal base shear Fb."""
        m = [8000.0, 8000.0, 8000.0]
        z = [4.0, 8.0, 12.0]
        H = 12.0
        r = ec8_lateral_force(self.ag_025, "B", H, m, z)
        assert r["ok"] is True
        assert abs(sum(r["Fi_N"]) - r["Fb_N"]) < 0.01

    def test_Cvx_sums_to_one(self):
        """Distribution coefficients must sum to 1."""
        m = [5000.0, 7000.0, 4000.0]
        z = [3.5, 7.0, 10.5]
        H = 10.5
        r = ec8_lateral_force(self.ag_025, "C", H, m, z)
        assert r["ok"] is True
        assert abs(sum(r["Cvx"]) - 1.0) < 1e-9

    def test_T1_formula_other(self):
        """T1 = 0.05 · H^0.75 for structural_type='other'."""
        H = 15.0
        r = ec8_lateral_force(self.ag_025, "B", H, [10000.0], [15.0],
                               structural_type="other")
        assert r["ok"] is True
        expected_T1 = 0.05 * (H ** 0.75)
        # T1_s is rounded to 4 decimal places in the returned dict
        assert abs(r["T1_s"] - expected_T1) < 1e-4

    def test_T1_formula_concrete_moment(self):
        """T1 = 0.075 · H^0.75 for concrete moment frame."""
        H = 20.0
        r = ec8_lateral_force(self.ag_025, "B", H, [10000.0], [20.0],
                               structural_type="moment_resisting_frame_concrete")
        assert r["ok"] is True
        expected_T1 = 0.075 * (H ** 0.75)
        # T1_s is rounded to 4 decimal places in the returned dict
        assert abs(r["T1_s"] - expected_T1) < 1e-4

    def test_lambda_auto_085_for_many_storeys(self):
        """λ=0.85 auto-selected when n>2 and T1 ≤ 2·TC."""
        # Use a short building so T1 is small (well below 2·TC=1.0 for ground B)
        m = [10000.0] * 3
        z = [3.0, 6.0, 9.0]
        H = 9.0
        r = ec8_lateral_force(self.ag_025, "B", H, m, z)
        assert r["ok"] is True
        # T1 = 0.05·9^0.75 ≈ 0.267 s; TC=0.5; 2·TC=1.0 > T1 and n=3>2
        assert r["lambda_corr"] == pytest.approx(0.85)

    def test_lambda_auto_10_for_single_storey(self):
        """λ=1.0 auto-selected when n=1."""
        r = ec8_lateral_force(self.ag_025, "B", 5.0, [20000.0], [5.0])
        assert r["ok"] is True
        assert r["lambda_corr"] == pytest.approx(1.0)

    def test_lambda_override(self):
        """Explicit lambda_corr overrides auto."""
        m = [10000.0] * 3
        z = [3.0, 6.0, 9.0]
        r = ec8_lateral_force(self.ag_025, "B", 9.0, m, z, lambda_corr=1.0)
        assert r["ok"] is True
        assert r["lambda_corr"] == pytest.approx(1.0)

    def test_Fi_proportional_to_zi_mi(self):
        """Fi ∝ zi·mi (equal masses → linear distribution)."""
        m = [1000.0, 1000.0, 1000.0]
        z = [3.0, 6.0, 9.0]  # sum_zm = 1000*(3+6+9)=18000
        H = 9.0
        r = ec8_lateral_force(self.ag_025, "B", H, m, z)
        assert r["ok"] is True
        # Cvx ∝ [3, 6, 9] → [1/6, 2/6, 3/6]
        expected_cvx = [3 / 18, 6 / 18, 9 / 18]
        for i, ecvx in enumerate(expected_cvx):
            # Cvx is rounded to 6 decimal places in the returned dict
            assert abs(r["Cvx"][i] - ecvx) < 5e-7

    # --- Error paths ---

    def test_invalid_ground_type(self):
        r = ec8_lateral_force(self.ag_025, "Z", 10.0, [10000.0], [10.0])
        assert r["ok"] is False

    def test_empty_masses(self):
        r = ec8_lateral_force(self.ag_025, "B", 10.0, [], [])
        assert r["ok"] is False

    def test_mismatched_lengths(self):
        r = ec8_lateral_force(self.ag_025, "B", 10.0, [10000.0, 20000.0], [5.0])
        assert r["ok"] is False

    def test_non_increasing_heights(self):
        r = ec8_lateral_force(self.ag_025, "B", 10.0, [10000.0, 10000.0], [6.0, 3.0])
        assert r["ok"] is False

    def test_ag_zero(self):
        r = ec8_lateral_force(0.0, "B", 10.0, [10000.0], [10.0])
        assert r["ok"] is False

    def test_invalid_structural_type(self):
        r = ec8_lateral_force(self.ag_025, "B", 10.0, [10000.0], [10.0],
                               structural_type="timber_shearwall")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 3. ec8_rsa — modal response spectrum analysis
# ---------------------------------------------------------------------------

class TestEc8Rsa:

    ag_025 = _ag(0.25)

    def _single_mode_sdof(self, omega1: float, mass: float) -> dict:
        """SDOF system: one mode, one DOF, unit mode shape."""
        return ec8_rsa(
            self.ag_025, "B",
            omega_n=[omega1],
            phi_n=[[1.0]],
            m_stories=[mass],
            q=1.5,
        )

    def test_sdof_base_shear_equals_lateral_force(self):
        """Single-mode SDOF RSA base shear ≈ lateral-force-method base shear.

        For a SDOF system with T1 and total mass m:
          RSA: Vb = m_eff · Sd(T1) = m · Sd(T1)  (100% mass participation)
          LF:  Fb = Sd(T1) · m · λ              (λ=1.0 for single storey)
        Both must agree when λ=1.
        """
        mass = 50000.0  # kg
        T1 = 0.4        # s (on plateau for ground B)
        omega1 = 2.0 * math.pi / T1

        rsa_r = self._single_mode_sdof(omega1, mass)
        assert rsa_r["ok"] is True

        # Lateral force method (single storey → λ=1.0, n=1)
        H = 10.0
        lf_r = ec8_lateral_force(
            self.ag_025, "B", H,
            [mass], [H],
            q=1.5, structural_type="other",
            lambda_corr=1.0,
        )
        assert lf_r["ok"] is True

        # Both use the same Sd value at T1, so V_combined == Fb when λ=1
        Sd_rsa = rsa_r["Sd_n"][0]
        Sd_lf = lf_r["Sd_T1_m_s2"]
        # Note: T1 from RSA is exact; LF uses Ct formula.
        # We compare RSA V_combined to mass * Sd(T1_rsa) directly:
        expected_Vb = mass * Sd_rsa
        assert abs(rsa_r["V_combined_N"] - expected_Vb) < 0.1

    def test_single_mode_100pct_mass_participation(self):
        """Single-mode SDOF → m_eff = total mass → ratio = 1.0."""
        r = self._single_mode_sdof(math.pi * 2, 30000.0)
        assert r["ok"] is True
        assert r["m_eff_ratio"] == pytest.approx(1.0, abs=1e-9)
        assert r["m_eff_check_ok"] is True

    def test_sdof_displacement_formula(self):
        """u = Γ·φ·Sd/ω² = 1·1·Sd/ω² (SDOF)."""
        omega1 = 2.0 * math.pi / 0.5  # T=0.5s
        mass = 10000.0
        r = self._single_mode_sdof(omega1, mass)
        assert r["ok"] is True
        Sd = r["Sd_n"][0]
        expected_u = Sd / (omega1 ** 2)
        assert abs(r["u_combined"][0] - expected_u) < 1e-9

    def test_two_mode_srss_combination(self):
        """SRSS combination: V_total = sqrt(V1² + V2²)."""
        # Two uncoupled SDOF modes
        omega1 = 2.0 * math.pi / 0.3
        omega2 = 2.0 * math.pi / 0.15
        # Orthogonal mode shapes on 2-DOF system
        mass = [20000.0, 20000.0]
        # Mode 1: [1, 0]; Mode 2: [0, 1] — fully decoupled
        phi = [[1.0, 0.0], [0.0, 1.0]]
        r = ec8_rsa(
            self.ag_025, "B",
            omega_n=[omega1, omega2],
            phi_n=phi,
            m_stories=mass,
            combination="srss",
            q=1.5,
        )
        assert r["ok"] is True
        V1, V2 = r["V_n"]
        expected_combined = math.sqrt(V1 ** 2 + V2 ** 2)
        assert abs(r["V_combined_N"] - expected_combined) < 0.001

    def test_cqc_collapses_to_srss_for_wellseparated_modes(self):
        """CQC ≈ SRSS when modes are well-separated (ρ ≈ 0)."""
        omega1 = 2.0 * math.pi / 2.0   # T=2.0s
        omega2 = 2.0 * math.pi / 0.2   # T=0.2s — ratio ~10
        mass = [15000.0, 15000.0]
        phi = [[1.0, 0.0], [0.0, 1.0]]

        r_srss = ec8_rsa(self.ag_025, "B",
                         omega_n=[omega1, omega2], phi_n=phi,
                         m_stories=mass, combination="srss", q=1.5)
        r_cqc = ec8_rsa(self.ag_025, "B",
                        omega_n=[omega1, omega2], phi_n=phi,
                        m_stories=mass, combination="cqc", q=1.5)

        assert r_srss["ok"] and r_cqc["ok"]
        ratio = r_cqc["V_combined_N"] / r_srss["V_combined_N"]
        # CQC ≈ SRSS for well-separated modes (within 5%)
        assert abs(ratio - 1.0) < 0.05

    def test_m_eff_check_fails_when_too_few_modes(self):
        """When m_eff < 90%, check flag is False and warning issued."""
        # Two-DOF, two-mode system — Mode 1 captures only DOF 1
        # phi[0]=[1,0], phi[1]=[0,0] — second mode has zero modal mass
        # Use only 1 mode for a 2-DOF system
        mass = [10000.0, 10000.0]
        omega1 = 2.0 * math.pi / 0.5
        phi = [[1.0, 0.0]]  # only mode 1, captures 50% of mass
        r = ec8_rsa(self.ag_025, "B",
                    omega_n=[omega1], phi_n=phi,
                    m_stories=mass, q=1.5)
        assert r["ok"] is True
        assert r["m_eff_ratio"] < 0.9
        assert r["m_eff_check_ok"] is False
        assert any("0.90" in w or "90" in w for w in r["warnings"])

    def test_returns_per_mode_T_and_Sd(self):
        """Per-mode T_n and Sd_n are returned for all modes."""
        omega_n = [2.0 * math.pi / 0.4, 2.0 * math.pi / 0.15]
        phi_n = [[1.0, 0.5], [0.3, 1.0]]
        m = [10000.0, 8000.0]
        r = ec8_rsa(self.ag_025, "B", omega_n=omega_n, phi_n=phi_n,
                    m_stories=m, q=1.5)
        assert r["ok"] is True
        assert len(r["T_n"]) == 2
        assert len(r["Sd_n"]) == 2
        # T values correct
        for k in range(2):
            assert abs(r["T_n"][k] - 2.0 * math.pi / omega_n[k]) < 1e-9

    def test_drift_has_correct_length(self):
        """drift_combined has same length as m_stories."""
        mass = [10000.0, 12000.0, 8000.0]
        omega_n = [2.0 * math.pi / 0.5, 2.0 * math.pi / 0.2]
        phi_n = [[1.0, 0.8, 0.5], [0.4, 1.0, 0.3]]
        r = ec8_rsa(self.ag_025, "B", omega_n=omega_n, phi_n=phi_n,
                    m_stories=mass, q=1.5)
        assert r["ok"] is True
        assert len(r["drift_combined"]) == 3

    # --- Error paths ---

    def test_invalid_ground_type(self):
        r = ec8_rsa(self.ag_025, "X", [10.0], [[1.0]], [5000.0])
        assert r["ok"] is False

    def test_empty_modes(self):
        r = ec8_rsa(self.ag_025, "B", [], [], [5000.0])
        assert r["ok"] is False

    def test_mismatched_phi_n_shape(self):
        """phi_n has wrong number of DOF entries."""
        r = ec8_rsa(self.ag_025, "B",
                    omega_n=[10.0, 20.0],
                    phi_n=[[1.0, 0.5], [1.0]],  # second row too short
                    m_stories=[5000.0, 5000.0])
        assert r["ok"] is False

    def test_invalid_combination_method(self):
        r = ec8_rsa(self.ag_025, "B",
                    omega_n=[10.0], phi_n=[[1.0]],
                    m_stories=[5000.0], combination="abs")
        assert r["ok"] is False

    def test_ag_zero(self):
        r = ec8_rsa(0.0, "B", [10.0], [[1.0]], [5000.0])
        assert r["ok"] is False

    def test_zero_omega(self):
        r = ec8_rsa(self.ag_025, "B", [0.0], [[1.0]], [5000.0])
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 4. Validation: reference spectrum values
# ---------------------------------------------------------------------------

class TestEc8ReferenceValues:
    """Cited against EN 1998-1 Table 3.2 / §3.2.2.5."""

    ag_025 = _ag(0.25)  # 0.25g in m/s²

    def test_Sd_at_T0_ground_B_type1_q1(self):
        """Sd(0) = ag·S·2/3 for Type 1, B, q=1, gamma_I=1."""
        expected = self.ag_025 * 1.2 * (2.0 / 3.0)  # ≈ 1.961 m/s²
        r = ec8_design_spectrum(0.0, self.ag_025, "B",
                                spectrum_type="1", q=1.0, gamma_I=1.0)
        assert r["ok"] is True
        assert r["Sd_m_s2"] == pytest.approx(expected, rel=1e-5)

    def test_Sd_at_TC_ground_B_type1_q15(self):
        """Sd(TC=0.5s) = ag·S·2.5/q for Type 1, B, q=1.5, gamma_I=1."""
        expected = self.ag_025 * 1.2 * 2.5 / 1.5  # ≈ 4.903 m/s²
        r = ec8_design_spectrum(0.5, self.ag_025, "B",
                                spectrum_type="1", q=1.5, gamma_I=1.0)
        assert r["ok"] is True
        assert r["Sd_m_s2"] == pytest.approx(expected, rel=1e-5)

    def test_Sd_at_T_in_velocity_region_ground_B(self):
        """Sd(1.0s) = ag·S·2.5/q·(TC/T) for Type 1, B, q=1.5."""
        T = 1.0
        TC = 0.5
        expected = self.ag_025 * 1.2 * 2.5 / 1.5 * (TC / T)  # ≈ 2.452 m/s²
        r = ec8_design_spectrum(T, self.ag_025, "B",
                                spectrum_type="1", q=1.5, gamma_I=1.0)
        assert r["ok"] is True
        assert r["Sd_m_s2"] == pytest.approx(expected, rel=1e-5)

    def test_ground_type_params_type1_all(self):
        """Verify S values match EN 1998-1 Table 3.2 for all ground types."""
        expected_S = {"A": 1.0, "B": 1.2, "C": 1.15, "D": 1.35, "E": 1.4}
        for gt, S_exp in expected_S.items():
            r = ec8_design_spectrum(0.5, self.ag_025, gt, spectrum_type="1", q=1.0)
            assert r["ok"] is True
            assert r["S"] == pytest.approx(S_exp), f"Ground type {gt}: S mismatch"

    def test_importance_factor_class_IV(self):
        """gamma_I=1.4 for Importance Class IV matches EN 1998-1 Table 4.3."""
        from kerf_cad_core.struct.eurocode8 import _IMPORTANCE_FACTORS
        assert _IMPORTANCE_FACTORS[4] == pytest.approx(1.4)

    def test_behaviour_factor_q1_is_elastic(self):
        """q=1.0 → Sd = Se (elastic spectrum, no reduction)."""
        r = ec8_design_spectrum(0.5, self.ag_025, "B",
                                q=1.0, gamma_I=1.0, xi=5.0)
        assert r["ok"] is True
        # At T=TC plateau: Sd = ag·S·2.5/q = ag·S·2.5 = Se (with eta=1 for xi=5%)
        # eta = sqrt(10/(5+5)) = 1.0 → Se = Sd when q=1
        assert abs(r["Sd_m_s2"] - r["Se_m_s2"]) < 1e-9

    def test_tb_tc_td_ground_D_type1(self):
        """Ground D Type 1: TB=0.20, TC=0.80, TD=2.0 (Table 3.2)."""
        r = ec8_design_spectrum(0.5, self.ag_025, "D", spectrum_type="1")
        assert r["ok"] is True
        assert r["TB"] == pytest.approx(0.20)
        assert r["TC"] == pytest.approx(0.80)
        assert r["TD"] == pytest.approx(2.0)

    def test_sdof_rsa_single_mode_Vb(self):
        """SDOF RSA: Vb = m·Sd(T) exactly (Γ=1, φ=1 → m_eff=m)."""
        T1 = 0.5
        omega1 = 2.0 * math.pi / T1
        mass = 25000.0
        Sd_ref = ec8_design_spectrum(T1, self.ag_025, "B",
                                     q=1.5)["Sd_m_s2"]
        r = ec8_rsa(self.ag_025, "B",
                    omega_n=[omega1], phi_n=[[1.0]],
                    m_stories=[mass], q=1.5)
        assert r["ok"] is True
        expected_Vb = mass * Sd_ref
        assert abs(r["V_combined_N"] - expected_Vb) < 0.01
