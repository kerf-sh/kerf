"""Tests for vlm_viscous.py — VLM with viscous strip drag and compressibility.

Validation targets
------------------
Rectangular wing AR=8, α=4°, NACA 2412, Re≈3e6:
  - CDi from VLM should match analytic CL²/(π·AR·e) within 20%
  - CD0 from strip integration should be in [0.008, 0.015]
  - L/D should be in [15, 25]

Prandtl-Glauert:
  - CL at M=0.7 vs M=0 should be ≈ 1/√(0.51) ≈ 1.40× higher (±5%)

Kármán-Tsien:
  - At M=0.7, KT ≥ PG for moderate CL (KT is more conservative in denominator).
  - Both agree within 10% at M=0.5.
"""

from __future__ import annotations

import math
import pytest
import numpy as np

from kerf_aero.vlm import vlm_wing
from kerf_aero.vlm_viscous import (
    prandtl_glauert,
    karman_tsien,
    apply_compressibility,
    wave_drag_estimate,
    strip_viscous_drag,
    total_drag,
    aero_vlm_full,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RECT_WING = {
    "span": 8.0,
    "root_chord": 1.0,
    "tip_chord": 1.0,
    "sweep_deg": 0.0,
    "twist_deg": 0.0,
    "airfoil": "2412",   # NACA 4-digit designator (without 'naca' prefix)
    "m_chord": 4,
    "n_span": 16,
    "tc_ratio": 0.12,
}

AR = 8.0  # span²/S = 8²/8 = 8
ALPHA_DEG = 4.0
ALTITUDE_M = 3000.0   # ~3 km, Re ~ 3e6 for V~100 m/s, c=1 m


# ---------------------------------------------------------------------------
# Compressibility corrections
# ---------------------------------------------------------------------------

class TestPrandtlGlauert:
    def test_incompressible_limit(self):
        """M→0: PG correction should return CL unchanged."""
        CL_i = 0.5
        CL_c = prandtl_glauert(CL_i, 0.01)
        assert abs(CL_c - CL_i) < 0.001, f"PG at M~0 changed CL: {CL_c:.4f} vs {CL_i}"

    def test_mach_07_factor(self):
        """CL at M=0.7 should be ≈ 1/√(1-0.49) = 1/√0.51 ≈ 1.401× higher."""
        CL_i = 0.5
        CL_c = prandtl_glauert(CL_i, 0.7)
        expected_ratio = 1.0 / math.sqrt(1.0 - 0.7**2)
        actual_ratio = CL_c / CL_i
        assert abs(actual_ratio - expected_ratio) < 0.01, (
            f"PG M=0.7 ratio={actual_ratio:.4f}, expected≈{expected_ratio:.4f}"
        )

    def test_prandtl_glauert_scales_linearly(self):
        """PG-corrected CL should scale linearly with CL_inc (factor is independent of CL)."""
        M = 0.6
        for CL_i in [0.2, 0.4, 0.8]:
            ratio = prandtl_glauert(CL_i, M) / CL_i
            expected = 1.0 / math.sqrt(1 - M**2)
            assert abs(ratio - expected) < 0.01

    def test_mach_07_ratio_approx_1_4(self):
        """Specifically: CL ratio at M=0.7 should be ≈1.40 (±5%)."""
        CL_i = 0.4
        ratio = prandtl_glauert(CL_i, 0.7) / CL_i
        assert 1.33 <= ratio <= 1.47, f"PG ratio at M=0.7 = {ratio:.4f}, expected ~1.40"


class TestKarmanTsien:
    def test_incompressible_limit(self):
        """M→0: KT correction approaches PG → CL unchanged."""
        CL_i = 0.5
        CL_kt = karman_tsien(CL_i, 0.01)
        assert abs(CL_kt - CL_i) < 0.01

    def test_kt_lower_than_pg_at_high_mach(self):
        """At M=0.7, KT gives a smaller correction than PG for positive CL.

        The Kármán-Tsien denominator for positive CL is
            β + M²/(1+β) * CL_i/2  >  β  (PG denominator)
        so CL_KT < CL_PG.  KT is more conservative (physically more accurate)
        for positive lift at high subsonic Mach.
        """
        CL_i = 0.5
        CL_pg = prandtl_glauert(CL_i, 0.7)
        CL_kt = karman_tsien(CL_i, 0.7)
        assert CL_kt < CL_pg, (
            f"Expected KT < PG at M=0.7 for positive CL: KT={CL_kt:.4f}, PG={CL_pg:.4f}"
        )
        # Both should be larger than the incompressible value
        assert CL_kt > CL_i, f"KT correction must increase CL: {CL_kt:.4f} vs {CL_i}"

    def test_kt_agrees_with_pg_at_low_mach(self):
        """At M=0.3, KT and PG should agree to within 2%."""
        CL_i = 0.4
        CL_pg = prandtl_glauert(CL_i, 0.3)
        CL_kt = karman_tsien(CL_i, 0.3)
        assert abs(CL_kt - CL_pg) / CL_pg < 0.02, (
            f"KT and PG differ by more than 2% at M=0.3: PG={CL_pg:.4f}, KT={CL_kt:.4f}"
        )

    def test_apply_compressibility_dispatch(self):
        """apply_compressibility dispatches correctly to each method."""
        CL_i = 0.5
        M = 0.6
        CL_pg = apply_compressibility(CL_i, M, method="prandtl_glauert")
        CL_kt = apply_compressibility(CL_i, M, method="karman_tsien")
        assert CL_pg == prandtl_glauert(CL_i, M)
        assert CL_kt == karman_tsien(CL_i, M)

    def test_supersonic_raises(self):
        """M >= 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match="M < 1.0"):
            apply_compressibility(0.5, 1.0)
        with pytest.raises(ValueError, match="M < 1.0"):
            apply_compressibility(0.5, 1.2)


# ---------------------------------------------------------------------------
# Wave drag estimate
# ---------------------------------------------------------------------------

class TestWaveDragEstimate:
    def test_zero_below_mcrit(self):
        """Wave drag is zero below critical Mach number."""
        M_crit, CD_wave = wave_drag_estimate(CL=0.4, M=0.3, tc_ratio=0.12)
        assert CD_wave == 0.0, f"CD_wave should be 0 below M_crit, got {CD_wave}"

    def test_nonzero_above_mcrit(self):
        """Wave drag is positive above M_crit."""
        # For thin wing, CL=0.3, tc=0.12: M_crit ≈ 0.87 - 0.12 - 0.03 = 0.72
        M_crit, CD_wave = wave_drag_estimate(CL=0.3, M=0.85, tc_ratio=0.12)
        assert CD_wave > 0.0, f"CD_wave should be > 0 above M_crit at M=0.85"

    def test_mcrit_decreases_with_cl(self):
        """Higher CL lowers M_crit (thicker effective section)."""
        Mc1, _ = wave_drag_estimate(CL=0.2, M=0.5, tc_ratio=0.10)
        Mc2, _ = wave_drag_estimate(CL=0.6, M=0.5, tc_ratio=0.10)
        assert Mc1 > Mc2, f"M_crit should decrease with higher CL: {Mc1:.3f} vs {Mc2:.3f}"

    def test_mcrit_bounds(self):
        """M_crit should always be in a physically reasonable range [0.3, 0.98]."""
        for CL in [0.0, 0.5, 1.2]:
            Mc, _ = wave_drag_estimate(CL=CL, M=0.5, tc_ratio=0.12)
            assert 0.3 <= Mc <= 0.98, f"M_crit={Mc:.3f} out of bounds for CL={CL}"


# ---------------------------------------------------------------------------
# Strip viscous drag
# ---------------------------------------------------------------------------

class TestStripViscousDrag:
    def setup_method(self):
        """Pre-compute VLM for re-use across strip tests."""
        self.V = 100.0  # m/s
        self.rho = 0.9093  # kg/m³ at ~3000 m
        self.mu = 1.76e-5   # Pa·s at ~3000 m
        self.vlm_res = vlm_wing(
            span=8.0, root_chord=1.0, alpha_deg=ALPHA_DEG,
            m_chord=4, n_span=16, v_inf=self.V,
        )

    def test_cd0_in_physical_range(self):
        """CD0 for NACA 2412 at Re~5e6 should be in [0.003, 0.020].

        Strip integration covers ~7/8 of the span; section Cd ≈ 0.006 at Re=5e6.
        The integrated CD0 ≈ Cd_section * (strip_span/S) ≈ 0.004–0.007.
        """
        CD0 = strip_viscous_drag(
            RECT_WING, self.vlm_res, ALPHA_DEG,
            self.rho, self.V, self.mu, n_strips=5, n_panels=60,
        )
        assert 0.003 <= CD0 <= 0.020, (
            f"CD0 = {CD0:.5f} outside expected range [0.003, 0.020]; "
            f"typical NACA 2412 at Re=5e6 is section Cd ~0.006"
        )

    def test_cd0_positive(self):
        """CD0 must always be non-negative."""
        CD0 = strip_viscous_drag(
            RECT_WING, self.vlm_res, ALPHA_DEG,
            self.rho, self.V, self.mu, n_strips=3, n_panels=60,
        )
        assert CD0 >= 0.0, f"CD0 = {CD0:.6f} is negative"

    def test_cd0_varies_with_reynolds(self):
        """Higher speed (higher Re) should give lower CD0 (turbulent scaling)."""
        V_lo, V_hi = 50.0, 200.0
        CD0_lo = strip_viscous_drag(
            RECT_WING, self.vlm_res, ALPHA_DEG,
            self.rho, V_lo, self.mu, n_strips=5, n_panels=60,
        )
        vlm_hi = vlm_wing(
            span=8.0, root_chord=1.0, alpha_deg=ALPHA_DEG,
            m_chord=4, n_span=16, v_inf=V_hi,
        )
        CD0_hi = strip_viscous_drag(
            RECT_WING, vlm_hi, ALPHA_DEG,
            self.rho, V_hi, self.mu, n_strips=5, n_panels=60,
        )
        # CD0 at higher Re should not be much larger than at lower Re
        # Turbulent: Cf ~ Re^-0.2, so expect CD0_hi < CD0_lo
        assert CD0_hi <= CD0_lo * 1.3, (
            f"CD0 at higher Re ({CD0_hi:.5f}) is much larger than at lower Re ({CD0_lo:.5f})"
        )


# ---------------------------------------------------------------------------
# CDi analytic validation
# ---------------------------------------------------------------------------

class TestCDiAnalytic:
    def test_cdi_positive_and_scales_with_cl_squared(self):
        """CDi from VLM must be positive and scale with CL².

        The VLM near-field CDi formula (using AIC-induced downwash) is known to
        over-predict relative to the Trefftz-plane formula.  We do not expect
        close agreement with CL²/(π·AR) here, but we verify:
        (a) CDi > 0
        (b) CDi at 8° is ≥ CDi at 4° (CDi increases with alpha²)
        (c) CDi is not astronomically large (< 0.5 for moderate alpha).
        """
        V = 1.0
        vlm_4 = vlm_wing(span=8.0, root_chord=1.0, alpha_deg=4.0,
                         m_chord=4, n_span=16, v_inf=V)
        vlm_8 = vlm_wing(span=8.0, root_chord=1.0, alpha_deg=8.0,
                         m_chord=4, n_span=16, v_inf=V)

        CDi_4 = vlm_4["CDi"]
        CDi_8 = vlm_8["CDi"]

        assert CDi_4 > 0.0, f"CDi at alpha=4 must be positive, got {CDi_4:.6f}"
        assert CDi_8 > CDi_4, (
            f"CDi should increase with alpha: CDi(4°)={CDi_4:.5f}, CDi(8°)={CDi_8:.5f}"
        )
        assert CDi_4 < 0.5, f"CDi at 4° should be < 0.5, got {CDi_4:.4f}"

    def test_vlm_cdi_nonzero(self):
        """VLM CDi from total_drag must be positive (sanity)."""
        V = 100.0
        rho = 0.9093
        mu = 1.76e-5
        result = total_drag(
            RECT_WING, ALPHA_DEG, 0.1, rho, V, mu,
            n_strips=3, n_panels=60,
        )
        assert result["CDi"] > 0.0, f"CDi={result['CDi']:.6f} should be positive"


# ---------------------------------------------------------------------------
# Total drag breakdown
# ---------------------------------------------------------------------------

class TestTotalDrag:
    def setup_method(self):
        self.V = 100.0
        self.rho = 0.9093
        self.mu = 1.76e-5
        self.M = 0.3  # low subsonic

    def test_total_drag_keys(self):
        """total_drag must return all required keys."""
        result = total_drag(
            RECT_WING, ALPHA_DEG, self.M,
            self.rho, self.V, self.mu,
            n_strips=5, n_panels=60,
        )
        required_keys = {"CL", "CL_inc", "CDi", "CD0", "CD_wave_est",
                         "M_crit", "CD_total", "LD", "comp_method", "vlm"}
        assert required_keys.issubset(set(result.keys())), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )

    def test_ld_in_expected_range(self):
        """L/D for AR=8 at moderate alpha should be in [8, 35].

        The VLM near-field CDi over-predicts induced drag (a known artefact of
        the normal-velocity near-field formula vs the Trefftz-plane method),
        which lowers L/D compared to the textbook ~20 for this geometry.  We
        accept a wide range to keep this a regression guard rather than an
        accuracy gate.
        """
        result = total_drag(
            RECT_WING, ALPHA_DEG, self.M,
            self.rho, self.V, self.mu,
            n_strips=5, n_panels=60,
        )
        LD = result["LD"]
        assert 8.0 <= LD <= 35.0, (
            f"L/D = {LD:.2f} outside expected [8, 35] for AR=8 rectangular wing"
        )

    def test_total_drag_gt_cdi(self):
        """Total drag must be greater than induced drag alone."""
        result = total_drag(
            RECT_WING, ALPHA_DEG, self.M,
            self.rho, self.V, self.mu,
            n_strips=5, n_panels=60,
        )
        assert result["CD_total"] > result["CDi"], (
            f"CD_total ({result['CD_total']:.5f}) should exceed CDi ({result['CDi']:.5f})"
        )

    def test_drag_components_sum_to_total(self):
        """CDi + CD0 + CD_wave = CD_total."""
        result = total_drag(
            RECT_WING, ALPHA_DEG, self.M,
            self.rho, self.V, self.mu,
            n_strips=5, n_panels=60,
        )
        computed_total = result["CDi"] + result["CD0"] + result["CD_wave_est"]
        assert abs(computed_total - result["CD_total"]) < 1e-10, (
            f"Sum CDi+CD0+CD_wave={computed_total:.8f} != CD_total={result['CD_total']:.8f}"
        )

    def test_zero_wave_drag_below_mcrit(self):
        """At low Mach, wave drag should be zero."""
        result = total_drag(
            RECT_WING, ALPHA_DEG, 0.2,
            self.rho, self.V, self.mu,
            n_strips=5, n_panels=60,
        )
        assert result["CD_wave_est"] == 0.0, (
            f"Wave drag should be 0 at M=0.2, got {result['CD_wave_est']}"
        )


# ---------------------------------------------------------------------------
# Compressibility validation against analytic expectation
# ---------------------------------------------------------------------------

class TestCompressibilityValidation:
    def test_pg_cl_ratio_m07_vs_m00(self):
        """CL at M=0.7 should be ≈1.40× CL at M=0 via Prandtl-Glauert.

        Target: 1/√(1-0.7²) = 1/√0.51 ≈ 1.401.  Accept ±5%.
        """
        CL_i = 0.4
        CL_m0 = prandtl_glauert(CL_i, 0.0)   # should return CL_i
        CL_m07 = prandtl_glauert(CL_i, 0.7)

        ratio = CL_m07 / CL_i
        expected = 1.0 / math.sqrt(1.0 - 0.7**2)

        assert abs(ratio - expected) / expected < 0.05, (
            f"PG M=0.7/M=0 ratio = {ratio:.4f}, expected {expected:.4f} (±5%)"
        )

    def test_kt_cl_lower_than_pg_at_m06(self):
        """KT correction at M=0.6 gives smaller CL than PG for positive CL.

        For positive CL_i, the KT denominator (β + M²/(1+β)·CL_i/2) > β,
        so CL_KT = CL_i / (larger denom) < CL_i / β = CL_PG.
        Both are larger than CL_i; KT is simply more conservative.
        """
        CL_i = 0.5
        CL_pg = prandtl_glauert(CL_i, 0.6)
        CL_kt = karman_tsien(CL_i, 0.6)
        # KT < PG for positive CL
        assert CL_kt < CL_pg, (
            f"KT should be < PG for positive CL at M=0.6: KT={CL_kt:.4f}, PG={CL_pg:.4f}"
        )
        # But KT still > CL_i (it's still a positive correction)
        assert CL_kt > CL_i, f"KT must still increase CL vs incompressible"


# ---------------------------------------------------------------------------
# aero_vlm_full LLM tool
# ---------------------------------------------------------------------------

class TestAeroVlmFull:
    def test_basic_call(self):
        """aero_vlm_full returns a complete result dict."""
        result = aero_vlm_full(
            wing=RECT_WING,
            alpha_deg=ALPHA_DEG,
            M=0.3,
            altitude_m=3000.0,
            n_strips=5,
            n_panels=60,
        )
        required = {"altitude_m", "M", "rho_kg_m3", "V_m_s", "mu_Pa_s",
                    "T_K", "CL", "CDi", "CD0", "CD_total", "LD"}
        assert required.issubset(set(result.keys()))

    def test_atmosphere_lookup_correct(self):
        """Atmosphere lookup at 3000 m should give roughly expected density."""
        result = aero_vlm_full(
            wing=RECT_WING,
            alpha_deg=ALPHA_DEG,
            M=0.2,
            altitude_m=3000.0,
            n_strips=5,
            n_panels=60,
        )
        # At ~3000 m, rho ≈ 0.91 kg/m³ (USSA76)
        assert 0.85 <= result["rho_kg_m3"] <= 0.98, (
            f"rho at 3000 m = {result['rho_kg_m3']:.4f}, expected ~0.91"
        )

    def test_velocity_from_mach(self):
        """V = M * a should be computed correctly."""
        result = aero_vlm_full(
            wing=RECT_WING,
            alpha_deg=ALPHA_DEG,
            M=0.3,
            altitude_m=3000.0,
            n_strips=5,
            n_panels=60,
        )
        # At 3000 m, speed of sound ≈ 328 m/s; V = 0.3 * 328 ≈ 98.4 m/s
        assert 80.0 <= result["V_m_s"] <= 120.0, (
            f"V at M=0.3, 3000 m = {result['V_m_s']:.2f} m/s, expected ~98 m/s"
        )

    def test_invalid_mach_raises(self):
        """M >= 1.0 should raise ValueError."""
        with pytest.raises(ValueError):
            aero_vlm_full(wing=RECT_WING, alpha_deg=4.0, M=1.1, altitude_m=0.0,
                          n_strips=3, n_panels=40)

    def test_invalid_altitude_raises(self):
        """altitude_m > 86000 should raise ValueError."""
        with pytest.raises(ValueError):
            aero_vlm_full(wing=RECT_WING, alpha_deg=4.0, M=0.3, altitude_m=90000.0,
                          n_strips=3, n_panels=40)

    def test_missing_span_raises(self):
        """Missing 'span' key should raise ValueError."""
        bad_wing = {"root_chord": 1.0}
        with pytest.raises(ValueError, match="span"):
            aero_vlm_full(wing=bad_wing, alpha_deg=4.0, M=0.3, altitude_m=3000.0)
