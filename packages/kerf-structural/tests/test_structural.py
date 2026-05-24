"""
Unit tests for kerf-structural.

Oracle values
-------------
RC beam (12×24 in, Mu=200 kip-ft, f'c=4000 psi, fy=60000 psi):
  d ≈ 21.8125 in, Rn ≈ 467 psi
  As_required ≈ 2.20 in²  (within 2% of analytic R-method)

Lap splice #5 Class B (normal-weight, uncoated, psi_t=1.0, cb_Ktr_db=2.5):
  l_d = 1.3 × development_length  (ACI 318-19 §25.5.5)
  Analytic: l_d ≈ 14.23 in  →  Class B ≈ 18.50 in

ASCE 7 combo 1.2D+1.6L (D=10, L=5): 1.2×10 + 1.6×5 = 20.0
"""

from __future__ import annotations

import math
import pytest

from kerf_structural.rc_beam import design_rc_beam, check_rc_beam
from kerf_cad_core.concrete.design import beam_flexure as _core_beam_flexure, beam_required_As as _core_required_As
from kerf_structural.steel_beam import design_steel_beam, w_section
from kerf_structural.rebar_detailing import (
    bar_info, development_length, lap_splice_length, hook_development_length
)
from kerf_structural.load_combinations import (
    LoadCase, asce7_strength_combinations, governing_combination, combo_by_label
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _analytic_As(b, h, Mu_kip_ft, fc=4000, fy=60000,
                 cover=1.5, stirrup_dia=0.375, bar_dia=0.625, phi=0.9):
    """ACI R-method analytic formula for required As."""
    d = h - cover - stirrup_dia - bar_dia / 2.0
    Mu = Mu_kip_ft * 12.0 * 1000.0   # lb-in
    Rn = Mu / (phi * b * d ** 2)
    rho = (0.85 * fc / fy) * (1.0 - math.sqrt(1.0 - 2.0 * Rn / (0.85 * fc)))
    rho_min = max(3.0 * math.sqrt(fc) / fy, 200.0 / fy)
    rho = max(rho, rho_min)
    return rho * b * d


def _analytic_ld(bar_mark, fc=4000, fy=60000, psi_t=1.0, psi_e=1.0,
                 psi_s=None, lambda_f=1.0, cb_Ktr_db=2.5):
    """ACI 318-19 §25.5.2.1 development length (analytic)."""
    from kerf_structural.rebar_detailing import _BAR_TABLE
    db = _BAR_TABLE[bar_mark][0]
    if psi_s is None:
        psi_s = 0.8 if bar_mark <= 6 else 1.0
    ratio = min(cb_Ktr_db, 2.5)
    ld = (3.0 / 40.0) * (fy / (lambda_f * math.sqrt(fc))) * (
        psi_t * psi_e * psi_s / ratio
    ) * db
    return max(ld, 12.0)


# ─────────────────────────────────────────────────────────────────────────────
# RC beam — primary oracle tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRCBeam:
    def test_design_12x24_200kft_returns_ok(self):
        res = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        assert res.ok, res.reason

    def test_design_12x24_200kft_As_within_2pct(self):
        """As_required matches analytic R-method to within 2%."""
        res = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        assert res.ok

        As_analytic = _analytic_As(12, 24, 200)
        assert abs(res.As_required - As_analytic) / As_analytic < 0.02, (
            f"As_required={res.As_required:.4f} vs analytic={As_analytic:.4f}"
        )

    def test_rho_within_bounds(self):
        res = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        assert res.ok
        assert res.rho_min <= res.rho <= res.rho_max, (
            f"ρ={res.rho:.6f} outside [{res.rho_min:.6f}, {res.rho_max:.6f}]"
        )

    def test_effective_depth_correct(self):
        res = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        expected_d = 24 - 1.5 - 0.375 - 0.625 / 2.0
        assert abs(res.d - expected_d) < 1e-9

    def test_Rn_matches_formula(self):
        res = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        d = res.d
        Mu_lb_in = 200 * 12_000
        Rn_expected = Mu_lb_in / (0.9 * 12 * d ** 2)
        assert abs(res.Rn - Rn_expected) / Rn_expected < 1e-9

    def test_invalid_geometry_returns_error(self):
        res = design_rc_beam(b=0, h=24, Mu_kip_ft=200)
        assert not res.ok

    def test_check_rc_beam_moment_capacity(self):
        """φMn for the designed As should comfortably cover Mu=200 kip-ft."""
        res_d = design_rc_beam(b=12, h=24, Mu_kip_ft=200)
        assert res_d.ok
        cap = check_rc_beam(b=12, h=24, As=res_d.As_required)
        assert cap["ok"]
        assert cap["phi_Mn_kip_ft"] >= 200.0 * 0.99   # at least 99% of Mu (should exceed)


# ─────────────────────────────────────────────────────────────────────────────
# Rebar detailing — lap splice oracle test
# ─────────────────────────────────────────────────────────────────────────────

class TestRebarDetailing:
    def test_bar5_info(self):
        info = bar_info(5)
        assert info.diameter == pytest.approx(0.625)
        assert info.area == pytest.approx(0.31)

    def test_development_length_bar5(self):
        ld = development_length(5)
        expected = _analytic_ld(5)
        assert abs(ld - expected) < 1e-9, f"ld={ld:.4f} vs expected={expected:.4f}"

    def test_lap_splice_classB_bar5_is_1pt3_ld(self):
        """Class B lap = 1.3 × l_d  (ACI 318-19 §25.5.5)."""
        ld = development_length(5)
        lap_b = lap_splice_length(5, "B")
        assert abs(lap_b - 1.3 * ld) / (1.3 * ld) < 1e-9, (
            f"lap_B={lap_b:.4f} vs 1.3×l_d={1.3*ld:.4f}"
        )

    def test_lap_splice_classA_bar5_is_1pt0_ld(self):
        ld = development_length(5)
        lap_a = lap_splice_length(5, "A")
        assert abs(lap_a - 1.0 * ld) < 1e-9

    def test_lap_splice_analytic_oracle_bar5(self):
        """Lap Class B for #5 matches the analytic formula to 0.1%."""
        lap_b = lap_splice_length(5, "B")
        expected = 1.3 * _analytic_ld(5)
        assert abs(lap_b - expected) / expected < 0.001, (
            f"lap_B={lap_b:.4f} vs analytic={expected:.4f}"
        )

    def test_invalid_bar_mark_raises(self):
        with pytest.raises(ValueError):
            bar_info(99)

    def test_invalid_splice_class_raises(self):
        with pytest.raises(ValueError):
            lap_splice_length(5, "C")

    def test_hook_development_length_bar5(self):
        ldh = hook_development_length(5)
        assert ldh > 0
        # Minimum check: 8*db or 6 in
        assert ldh >= max(8 * 0.625, 6.0)

    def test_minimum_ld_12in_enforced(self):
        """For very strong concrete/small bars the 12 in minimum kicks in."""
        # Use very high fc to drive ld below 12 in without minimum
        ld = development_length(3, fc=10_000, fy=60_000)
        assert ld >= 12.0


# ─────────────────────────────────────────────────────────────────────────────
# Load combinations
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadCombinations:
    def test_1pt2D_plus_1pt6L_oracle(self):
        """ASCE 7 §2.3.1 combo 2: 1.2×10 + 1.6×5 = 20.0 (exact)."""
        lc = LoadCase(D=10, L=5)
        value = combo_by_label(lc, "1.2D+1.6L")
        assert value == pytest.approx(20.0)

    def test_1pt4D_only(self):
        lc = LoadCase(D=10)
        value = combo_by_label(lc, "1.4D")
        assert value == pytest.approx(14.0)

    def test_all_zero_loads(self):
        lc = LoadCase()
        results = asce7_strength_combinations(lc)
        for r in results:
            assert r.value == pytest.approx(0.0)

    def test_seven_combinations_returned(self):
        lc = LoadCase(D=10, L=5)
        results = asce7_strength_combinations(lc)
        assert len(results) == 7

    def test_governing_combination(self):
        lc = LoadCase(D=10, L=5)
        gov = governing_combination(lc)
        # With D=10, L=5 and no other loads, combo 1.2D+1.6L = 20.0 should govern
        assert gov.value == pytest.approx(20.0)
        assert "1.2D+1.6L" in gov.label

    def test_wind_governs(self):
        lc = LoadCase(D=10, L=2, W=30)
        gov = governing_combination(lc)
        assert gov.value > 20.0

    def test_dead_only_14D(self):
        lc = LoadCase(D=100)
        value = combo_by_label(lc, "1.4D")
        assert value == pytest.approx(140.0)

    def test_combo_label_not_found_raises(self):
        lc = LoadCase(D=10)
        with pytest.raises(KeyError):
            combo_by_label(lc, "NONEXISTENT")


# ─────────────────────────────────────────────────────────────────────────────
# Steel beam
# ─────────────────────────────────────────────────────────────────────────────

class TestSteelBeam:
    def test_w18x50_plastic_zone(self):
        """Short unbraced length → plastic zone, φMn = 0.9 × Fy × Zx."""
        sec = w_section("W18X50")
        # Lb = 0 ft → unbraced length well below Lp
        res = design_steel_beam("W18X50", Lb_ft=0.5, Fy=50.0)
        assert res.ok
        assert res.ltb_zone == "plastic"
        expected_phi_Mn = 0.9 * 50.0 * sec.Zx  # kip-in
        assert abs(res.phi_Mn - expected_phi_Mn) / expected_phi_Mn < 1e-6

    def test_w18x50_inelastic_zone(self):
        """Mid unbraced length → inelastic LTB zone."""
        res = design_steel_beam("W18X50", Lb_ft=12.0)
        assert res.ok
        assert res.ltb_zone == "inelastic"
        assert res.phi_Mn < 0.9 * 50.0 * 101.0  # below Mp

    def test_w18x50_elastic_zone(self):
        """Long unbraced length → elastic LTB zone."""
        res = design_steel_beam("W18X50", Lb_ft=50.0)
        assert res.ok
        assert res.ltb_zone == "elastic"

    def test_phi_Mn_kip_ft_conversion(self):
        res = design_steel_beam("W18X50", Lb_ft=5.0)
        assert abs(res.phi_Mn_kip_ft - res.phi_Mn / 12.0) < 1e-9

    def test_lp_lr_ordering(self):
        """Lp < Lr always."""
        res = design_steel_beam("W18X50", Lb_ft=10.0)
        assert res.Lp < res.Lr

    def test_unknown_designation_returns_error(self):
        res = design_steel_beam("W99X999", Lb_ft=10.0)
        assert not res.ok

    def test_cb_gt1_increases_capacity(self):
        res1 = design_steel_beam("W18X50", Lb_ft=15.0, Cb=1.0)
        res2 = design_steel_beam("W18X50", Lb_ft=15.0, Cb=1.5)
        assert res2.phi_Mn >= res1.phi_Mn

    def test_w18x50_Lp_reasonable(self):
        """Lp for W18X50 should be in the range 5–10 ft (typical)."""
        res = design_steel_beam("W18X50", Lb_ft=1.0)
        assert 4.0 * 12 <= res.Lp <= 12.0 * 12   # 4 to 12 ft in inches


# ─────────────────────────────────────────────────────────────────────────────
# Parity test: kerf-structural and kerf-cad-core concrete routines must agree
# ─────────────────────────────────────────────────────────────────────────────

class TestRCBeamParityWithCadCore:
    """Verify that kerf-structural's RC beam functions agree with the canonical
    kerf_cad_core.concrete.design implementation after deduplication.

    Reference beam: 12 in wide × 24 in deep, f'c = 4 000 psi, fy = 60 000 psi,
    Mu = 200 kip-ft.  Default cover / stirrup / bar geometry.
    Tolerance: 0.1% relative (engineering parity, not floating-point identity).
    """

    _B = 12.0          # in
    _H = 24.0          # in
    _FC = 4_000.0      # psi
    _FY = 60_000.0     # psi
    _MU_KIPFT = 200.0  # kip-ft
    _COVER = 1.5       # in
    _STIR = 0.375      # in
    _BAR = 0.625       # in

    @classmethod
    def _d(cls) -> float:
        return cls._H - cls._COVER - cls._STIR - cls._BAR / 2.0

    def test_beta1_agrees(self):
        """_beta1 imported from kerf_cad_core returns the same value for
        4 000, 5 000 and 8 000 psi as the historical local formula."""
        from kerf_cad_core.concrete.design import _beta1 as canon_beta1
        for fc in (3_000, 4_000, 5_000, 8_000, 10_000):
            # Historical formula inline for comparison
            if fc <= 4_000:
                expected = 0.85
            else:
                expected = max(0.85 - 0.05 * (fc - 4_000) / 1_000, 0.65)
            assert canon_beta1(fc) == pytest.approx(expected, rel=1e-9), (
                f"_beta1({fc}) mismatch"
            )

    def test_design_rc_beam_As_matches_core_required_As(self):
        """design_rc_beam As_required must agree with core beam_required_As
        to within 0.1% for the reference beam."""
        structural = design_rc_beam(
            b=self._B, h=self._H, Mu_kip_ft=self._MU_KIPFT,
            fc=self._FC, fy=self._FY,
            cover=self._COVER, stirrup_dia=self._STIR, bar_dia=self._BAR,
        )
        assert structural.ok, structural.reason

        Mu_kipin = self._MU_KIPFT * 12.0
        core = _core_required_As(self._B, self._d(), Mu_kipin, self._FC, self._FY)

        assert abs(structural.As_required - core["As_req_in2"]) / core["As_req_in2"] < 0.001, (
            f"As mismatch: structural={structural.As_required:.4f} in² "
            f"vs core={core['As_req_in2']:.4f} in²"
        )

    def test_check_rc_beam_phi_Mn_matches_core_beam_flexure(self):
        """check_rc_beam phi_Mn_kip_ft must agree with core beam_flexure
        phi_Mn_kipin / 12 to within 0.1% for the reference beam's As."""
        structural_design = design_rc_beam(
            b=self._B, h=self._H, Mu_kip_ft=self._MU_KIPFT,
            fc=self._FC, fy=self._FY,
            cover=self._COVER, stirrup_dia=self._STIR, bar_dia=self._BAR,
        )
        assert structural_design.ok

        As = structural_design.As_required
        cap = check_rc_beam(
            b=self._B, h=self._H, As=As,
            fc=self._FC, fy=self._FY,
            cover=self._COVER, stirrup_dia=self._STIR, bar_dia=self._BAR,
        )
        assert cap["ok"]

        core = _core_beam_flexure(self._B, self._d(), As, self._FC, self._FY)
        core_phi_Mn_kip_ft = core["phi_Mn_kipin"] / 12.0

        assert abs(cap["phi_Mn_kip_ft"] - core_phi_Mn_kip_ft) / core_phi_Mn_kip_ft < 0.001, (
            f"phi_Mn mismatch: structural={cap['phi_Mn_kip_ft']:.4f} kip-ft "
            f"vs core={core_phi_Mn_kip_ft:.4f} kip-ft"
        )

    def test_check_rc_beam_geometry_keys_agree(self):
        """Stress-block depth a, neutral-axis c, and epsilon_t from check_rc_beam
        must match core beam_flexure exactly (they delegate to the same call)."""
        As = 2.20  # in² — representative design area
        cap = check_rc_beam(
            b=self._B, h=self._H, As=As,
            fc=self._FC, fy=self._FY,
            cover=self._COVER, stirrup_dia=self._STIR, bar_dia=self._BAR,
        )
        core = _core_beam_flexure(self._B, self._d(), As, self._FC, self._FY)

        assert cap["a"] == pytest.approx(core["a_in"], rel=1e-9)
        assert cap["c"] == pytest.approx(core["c_in"], rel=1e-9)
        assert cap["epsilon_t"] == pytest.approx(core["eps_t"], rel=1e-9)
        assert cap["phi"] == pytest.approx(core["phi"], rel=1e-9)
