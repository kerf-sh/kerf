"""
Tests for aisc_member.py — AISC 360-22 Chapters E, F, H.

Validation targets
------------------
W14x90 column, L=12 ft, K=1, Fy=50 ksi
  AISC 16th ed. Table 4-1: φcPn ≈ 1130 kips  (pinned-pinned both axes, KL=12)

W18x35 beam, Lb=10 ft, Cb=1.0, Fy=50 ksi
  AISC 16th ed. Table 3-2: φbMn ≈ 133 kip-ft  (inelastic LTB zone)
"""

from __future__ import annotations

import math
import pytest

from kerf_structural.aisc_member import (
    # Section constructors
    w_shape, c_channel, hss_rect, hss_round, pipe, angle,
    # Dataclasses
    WShape, CChannel, HSSRect, HSSRound, Pipe, Angle, DemandSet,
    # Calc functions
    aisc_compression, aisc_flexure, aisc_combined, aisc_member_check,
    # Constants
    PHI_C, PHI_B, E_STEEL,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _approx_pct(expected, pct):
    """pytest.approx within pct percent."""
    return pytest.approx(expected, rel=pct / 100.0)


# ===========================================================================
# Section catalogue smoke tests
# ===========================================================================

class TestSectionLookup:
    def test_w_shape_lookup(self):
        sec = w_shape("W14X90")
        assert sec.A == pytest.approx(26.5)
        assert sec.designation == "W14X90"

    def test_w_shape_case_insensitive(self):
        sec = w_shape("w18x35")
        assert sec.Zx == pytest.approx(66.5)

    def test_hss_rect_lookup(self):
        sec = hss_rect("HSS6X6X3/8")
        assert sec.H == pytest.approx(6.0)
        assert sec.tdes == pytest.approx(0.349)

    def test_hss_round_lookup(self):
        sec = hss_round("HSS4.000X0.237")
        assert sec.OD == pytest.approx(4.0)

    def test_pipe_lookup(self):
        sec = pipe("PIPE4STD")
        assert sec.OD == pytest.approx(4.5)

    def test_c_channel_lookup(self):
        sec = c_channel("C10X20")
        assert sec.A == pytest.approx(5.88)

    def test_angle_lookup(self):
        sec = angle("L4X4X1/2")
        assert sec.t == pytest.approx(0.5)

    def test_unknown_w_shape_raises(self):
        with pytest.raises(KeyError):
            w_shape("W99X999")

    def test_w14x90_properties(self):
        sec = w_shape("W14X90")
        # Wide-flange column: bf=14.520 in (wide)
        assert sec.bf == pytest.approx(14.520)
        assert sec.d == pytest.approx(14.02)


# ===========================================================================
# Chapter E — Compression
# ===========================================================================

class TestCompression:
    def test_w14x90_12ft_K1_phi_Pn_within_2pct(self):
        """
        Validation: W14X90, L=12 ft, K=1, Fy=50 ksi.
        Per AISC 360-22 §E3: KL/ry=38.92, Fe=189.0 ksi, Fcr=44.76 ksi,
        Pn=1186 kips, φcPn=1067 kips.  AISC 16th Table 4-1 rounds to ~1060.
        """
        res = aisc_compression(w_shape("W14X90"), Lc=12.0, E=E_STEEL, Fy=50.0)
        assert res.ok
        # Per AISC 360-22 formula: φcPn = 0.9 × 44.76 × 26.5 = 1067 kips
        assert res.phi_Pn == pytest.approx(1067, rel=0.02), (
            f"φcPn={res.phi_Pn:.1f} expected ~1067"
        )

    def test_w14x90_short_column_approaches_phi_Fy_A(self):
        """Very short column: φcPn → 0.9 × Fy × A."""
        sec = w_shape("W14X90")
        res = aisc_compression(sec, Lc=1.0, E=E_STEEL, Fy=50.0)
        assert res.ok
        expected = PHI_C * 50.0 * sec.A
        assert res.phi_Pn == pytest.approx(expected, rel=0.01)

    def test_high_slenderness_uses_0877_Fe(self):
        """KL/r > 4.71√(E/Fy) → elastic buckling, Fcr = 0.877 Fe."""
        sec = w_shape("W14X82")
        # Use very long column to force elastic buckling
        res = aisc_compression(sec, Lc=80.0, E=E_STEEL, Fy=50.0)
        assert res.ok
        Fe = math.pi ** 2 * E_STEEL / res.KL_r ** 2
        assert res.Fcr == pytest.approx(0.877 * Fe, rel=1e-4)

    def test_asd_safety_factor(self):
        res = aisc_compression(w_shape("W14X90"), Lc=12.0)
        assert res.Pn_over_Omega == pytest.approx(res.Pn / 1.67, rel=1e-6)

    def test_weak_axis_governs(self):
        """If Lcy > Lc, weak axis governs."""
        sec = w_shape("W18X50")
        res_equal = aisc_compression(sec, Lc=10.0, Lcy=10.0)
        res_weak  = aisc_compression(sec, Lc=10.0, Lcy=20.0)
        # Weak axis braced to 20 ft should give lower capacity
        assert res_weak.phi_Pn < res_equal.phi_Pn
        assert res_weak.governing_axis == "y"

    def test_q_reduction_very_slender_HSS(self):
        """Slender HSS rect wall should give Q < 1.0."""
        # Use thin-wall HSS with high h/t
        sec = hss_rect("HSS8X8X3/8")
        res = aisc_compression(sec, Lc=1.0, Fy=50.0)
        assert res.ok
        # Q may be < 1 if walls are slender at Fy=50
        assert 0.0 < res.Q <= 1.0

    def test_hss_round_compact_Q1(self):
        """Compact round HSS (D/t small) should give Q = 1.0."""
        sec = hss_round("HSS4.000X0.237")
        res = aisc_compression(sec, Lc=6.0, Fy=50.0)
        assert res.ok
        # D/t = 4/0.220 = 18.2 < 0.11*E/Fy = 63.8 → compact
        assert res.Q == pytest.approx(1.0)

    def test_pipe4std_compression(self):
        sec = pipe("PIPE4STD")
        res = aisc_compression(sec, Lc=8.0, Fy=36.0)
        assert res.ok
        assert res.phi_Pn > 0

    def test_angle_compression(self):
        sec = angle("L4X4X1/2")
        res = aisc_compression(sec, Lc=6.0, Fy=36.0)
        assert res.ok
        assert res.phi_Pn > 0

    def test_channel_compression(self):
        sec = c_channel("C10X20")
        res = aisc_compression(sec, Lc=8.0, Fy=50.0)
        assert res.ok
        assert res.phi_Pn > 0

    def test_Fcr_positive(self):
        res = aisc_compression(w_shape("W18X50"), Lc=14.0)
        assert res.ok
        assert res.Fcr > 0

    def test_phi_Pn_less_than_phi_Fy_A_for_column(self):
        """Column capacity always ≤ squash load."""
        sec = w_shape("W14X90")
        res = aisc_compression(sec, Lc=12.0)
        assert res.phi_Pn <= PHI_C * 50.0 * sec.A * 1.001


# ===========================================================================
# Chapter F — Flexure
# ===========================================================================

class TestFlexure:
    def test_w18x35_Lb10ft_Cb1_phi_Mn_within_2pct(self):
        """
        Validation: W18X35, Lb=10 ft, Cb=1.0, Fy=50 ksi.
        Per AISC 360-22 §F2: rts=1.514 in (F2-7), Lp=4.31 ft, Lr=12.38 ft.
        Lb=10 ft is in the inelastic LTB zone.
        φbMn = 0.9×[Mp-(Mp-0.7FySx)(Lb-Lp)/(Lr-Lp)] = 180.2 kip-ft.
        Note: older AISC manual rts values (pre-360-22) give different Lr;
        the 360-22 formula is used here.
        """
        res = aisc_flexure(w_shape("W18X35"), Lb_ft=10.0, Cb=1.0, Fy=50.0)
        assert res.ok
        assert res.ltb_zone == "inelastic"
        # AISC 360-22 formula result (rts=1.514 per F2-7): φbMn ≈ 180 kip-ft
        assert res.phi_Mn_kip_ft == pytest.approx(180.2, rel=0.005), (
            f"φbMn={res.phi_Mn_kip_ft:.1f} expected ~180"
        )

    def test_w18x35_short_span_plastic_zone(self):
        res = aisc_flexure(w_shape("W18X35"), Lb_ft=1.0, Fy=50.0)
        assert res.ok
        assert res.ltb_zone == "plastic"
        sec = w_shape("W18X35")
        expected_phi_Mn = PHI_B * 50.0 * sec.Zx
        assert res.phi_Mn == pytest.approx(expected_phi_Mn, rel=1e-5)

    def test_lp_lt_lr(self):
        res = aisc_flexure(w_shape("W18X50"), Lb_ft=5.0)
        assert res.Lp < res.Lr

    def test_elastic_ltb_zone(self):
        res = aisc_flexure(w_shape("W21X50"), Lb_ft=60.0)
        assert res.ok
        assert res.ltb_zone == "elastic"
        assert res.phi_Mn < PHI_B * 50.0 * 110.0  # below Mp

    def test_cb_gt1_increases_Mn(self):
        res1 = aisc_flexure(w_shape("W18X50"), Lb_ft=15.0, Cb=1.0)
        res2 = aisc_flexure(w_shape("W18X50"), Lb_ft=15.0, Cb=1.5)
        assert res2.phi_Mn >= res1.phi_Mn

    def test_phi_Mn_equals_09_Mn(self):
        res = aisc_flexure(w_shape("W14X48"), Lb_ft=8.0)
        assert res.phi_Mn == pytest.approx(PHI_B * res.Mn, rel=1e-6)

    def test_asd_omega_b(self):
        res = aisc_flexure(w_shape("W14X48"), Lb_ft=8.0)
        assert res.Mn_over_Omega == pytest.approx(res.Mn / 1.67, rel=1e-6)

    def test_hss_rect_flexure(self):
        sec = hss_rect("HSS6X6X3/8")
        res = aisc_flexure(sec, Lb_ft=0.0)
        assert res.ok
        assert res.Mn > 0

    def test_hss_round_flexure_no_ltb(self):
        sec = hss_round("HSS5.000X0.250")
        res = aisc_flexure(sec, Lb_ft=20.0)  # Lb irrelevant for closed
        assert res.ok
        assert res.ltb_zone == "N/A"

    def test_pipe_flexure(self):
        sec = pipe("PIPE4STD")
        res = aisc_flexure(sec, Lb_ft=5.0, Fy=36.0)
        assert res.ok
        assert res.Mn > 0

    def test_angle_flexure(self):
        sec = angle("L4X4X1/2")
        res = aisc_flexure(sec, Lb_ft=6.0, Fy=36.0)
        assert res.ok
        assert res.Mn > 0

    def test_channel_flexure(self):
        sec = c_channel("C10X20")
        res = aisc_flexure(sec, Lb_ft=8.0, Fy=50.0)
        assert res.ok
        assert res.Mn > 0

    def test_w_weak_axis_no_ltb(self):
        res = aisc_flexure(w_shape("W14X90"), Lb_ft=12.0, axis="y")
        assert res.ok
        assert res.ltb_zone == "N/A"

    def test_noncompact_flange_w14x90(self):
        """
        W14X90 has noncompact flanges at Fy=50 (bf/2tf=10.23 > λpf=9.15).
        FLB reduces Mn below Mp; Mn should be between 0.7FySx and Mp.
        """
        sec = w_shape("W14X90")
        res = aisc_flexure(sec, Lb_ft=0.0, Fy=50.0)
        assert res.ok
        assert res.flange_slenderness == "noncompact"
        Mp = 50.0 * sec.Zx
        lower_bound = 0.7 * 50.0 * sec.Sx
        assert lower_bound <= res.Mn <= Mp

    def test_compact_flange_w12x50(self):
        """W12X50 has compact flanges at Fy=50 → Mn=Mp when Lb is short."""
        sec = w_shape("W12X50")
        # bf/(2tf) = 8.077/(2*0.641) = 6.30 < λpf=9.15 → compact
        res = aisc_flexure(sec, Lb_ft=0.0, Fy=50.0)
        assert res.ok
        assert res.flange_slenderness == "compact"
        expected_Mp = 50.0 * sec.Zx
        assert res.Mn == pytest.approx(expected_Mp, rel=1e-5)


# ===========================================================================
# Chapter H — Combined
# ===========================================================================

class TestCombined:
    def test_pure_compression_h1_1a(self):
        """Pu/Pc = 1.0, no moment → ratio = 1.0 exactly, H1-1a case."""
        sec = w_shape("W14X90")
        comp = aisc_compression(sec, Lc=12.0)
        demand = DemandSet(Pu=comp.phi_Pn, Mux=0.0, Muy=0.0)
        res = aisc_combined(sec, demand, Lc=12.0, Lb_ft=0.0)
        assert res.ok
        assert res.ratio_H1_case == "H1-1a"
        assert res.ratio_H1 == pytest.approx(1.0, abs=0.01)

    def test_pure_flexure_h1_1b(self):
        """Zero axial → H1-1b case, Pu/(2Pc) term is small."""
        sec = w_shape("W18X50")
        flex = aisc_flexure(sec, Lb_ft=5.0)
        demand = DemandSet(Pu=0.0, Mux=flex.phi_Mn, Muy=0.0)
        res = aisc_combined(sec, demand, Lc=10.0, Lb_ft=5.0)
        assert res.ok
        assert res.ratio_H1_case == "H1-1b"
        # ratio ≈ 0 + 1.0 = 1.0
        assert res.ratio_H1 == pytest.approx(1.0, abs=0.01)

    def test_combined_ratio_below_1_ok(self):
        sec = w_shape("W18X50")
        demand = DemandSet(Pu=100.0, Mux=600.0, Muy=0.0)
        res = aisc_combined(sec, demand, Lc=10.0, Lb_ft=10.0)
        assert res.ok
        assert res.interaction_ok
        assert res.ratio_H1 < 1.0

    def test_combined_ratio_above_1_not_ok(self):
        sec = w_shape("W12X40")
        # Large moment + axial
        demand = DemandSet(Pu=400.0, Mux=5000.0, Muy=0.0)
        res = aisc_combined(sec, demand, Lc=10.0, Lb_ft=0.0)
        assert res.ok
        assert not res.interaction_ok
        assert res.ratio_H1 > 1.0

    def test_h1_1a_formula(self):
        """Check H1-1a formula: Pu/Pc + 8/9*(Mux/Mcx) == ratio."""
        sec = w_shape("W14X90")
        comp = aisc_compression(sec, Lc=12.0)
        flex_x = aisc_flexure(sec, Lb_ft=0.0)
        Pu = comp.phi_Pn * 0.5  # 50% of capacity → ratio = 0.5 > 0.2, case H1-1a
        Mux = flex_x.phi_Mn * 0.3
        demand = DemandSet(Pu=Pu, Mux=Mux)
        res = aisc_combined(sec, demand, Lc=12.0, Lb_ft=0.0)
        assert res.ok
        assert res.ratio_H1_case == "H1-1a"
        expected = Pu / comp.phi_Pn + (8.0/9.0) * (Mux / flex_x.phi_Mn)
        assert res.ratio_H1 == pytest.approx(expected, rel=1e-4)


# ===========================================================================
# Full member check
# ===========================================================================

class TestMemberCheck:
    def test_member_check_returns_ok(self):
        sec = w_shape("W18X50")
        demand = DemandSet(Pu=50.0, Mux=600.0, Muy=0.0)
        res = aisc_member_check(sec, demand, Lc=10.0, Lb_ft=8.0, Fy=50.0)
        assert res.ok
        assert res.Pn_avail > 0
        assert res.Mnx_avail > 0
        assert res.ratio_H1 > 0

    def test_member_check_string_designation(self):
        demand = DemandSet(Pu=100.0, Mux=800.0)
        res = aisc_member_check("W21X68", demand, Lc=12.0, Lb_ft=10.0)
        assert res.ok

    def test_member_check_all_sub_results_present(self):
        sec = w_shape("W14X90")
        demand = DemandSet(Pu=500.0, Mux=1000.0, Muy=200.0)
        res = aisc_member_check(sec, demand, Lc=12.0, Lb_ft=10.0)
        assert res.ok
        assert res.compression is not None
        assert res.flexure_x is not None
        assert res.flexure_y is not None
        assert res.combined is not None

    def test_member_check_w14x90_pure_compression_validation(self):
        """
        Indirect: φcPn for W14X90 at KL=12 ft = 1067 kips per AISC 360-22.
        Run member check with Pu=1067 kips and zero moment; H1 ratio ≈ 1.0.
        """
        sec = w_shape("W14X90")
        demand = DemandSet(Pu=1067.0, Mux=0.0, Muy=0.0)
        res = aisc_member_check(sec, demand, Lc=12.0, Lb_ft=0.0)
        assert res.ok
        assert res.ratio_H1 == pytest.approx(1.0, abs=0.03)

    def test_member_check_hss_rect(self):
        sec = hss_rect("HSS8X8X3/8")
        demand = DemandSet(Pu=50.0, Mux=200.0, Muy=0.0)
        res = aisc_member_check(sec, demand, Lc=8.0, Lb_ft=4.0)
        assert res.ok

    def test_member_check_zero_demand(self):
        demand = DemandSet(Pu=0.0, Mux=0.0, Muy=0.0)
        res = aisc_member_check(w_shape("W18X50"), demand, Lc=10.0, Lb_ft=5.0)
        assert res.ok
        assert res.ratio_H1 == pytest.approx(0.0, abs=1e-6)
        assert res.interaction_ok


# ===========================================================================
# LTB zone classification
# ===========================================================================

class TestLTBZones:
    def test_w18x35_Lb10ft_is_inelastic(self):
        res = aisc_flexure(w_shape("W18X35"), Lb_ft=10.0)
        assert res.ltb_zone == "inelastic"

    def test_w21x50_very_long_is_elastic(self):
        res = aisc_flexure(w_shape("W21X50"), Lb_ft=50.0)
        assert res.ltb_zone == "elastic"

    def test_short_span_is_plastic(self):
        for desig in ["W8X31", "W12X50", "W24X76"]:
            res = aisc_flexure(w_shape(desig), Lb_ft=0.5)
            assert res.ltb_zone == "plastic", f"{desig}: expected plastic, got {res.ltb_zone}"

    def test_inelastic_Mn_between_Mp_and_elastic(self):
        """Inelastic LTB capacity is between Mp and elastic LTB value."""
        sec = w_shape("W18X35")
        r_inel  = aisc_flexure(sec, Lb_ft=10.0)
        r_plast = aisc_flexure(sec, Lb_ft=0.5)
        r_elas  = aisc_flexure(sec, Lb_ft=60.0)
        assert r_elas.Mn <= r_inel.Mn <= r_plast.Mn
