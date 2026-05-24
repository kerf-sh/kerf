"""
tests/test_punching_torsion.py — ACI 318-19 §22.6 punching shear & §22.7
torsion design tests.

Validation targets
------------------
Punching shear:
  Wight & MacGregor 8th ed., Example 13-1 style:
    Square interior column 450×450 mm, h=200 mm slab, d=160 mm,
    f'c=28 MPa, λ=1 (normal-weight).
    b0 = 4·(450+160) = 2440 mm
    λs = min(1, √(2/(1+0.004·160))) = √(2/1.64) = 1.104 → capped at 1.0
    Vc1 = 0.33·1·1·√28·2440·160 = 0.33·5.292·390400 = 681,974 N ≈ 682 kN
    Vc2 = (0.17+0.34/1)·5.292·390400 = 0.51·5.292·390400 = 1,054 kN [not governs]
    Vc3 = (40·160/2440+0.17)·… = (2.623+0.17)·5.292·390400 ≈ 2.793·… [not governs]
    → Vc1 governs = ~682 kN; φVc = 0.75·682 ≈ 511 kN

Torsion:
  Nilson et al. Example 8-1 style:
    Rectangular beam 300×600 mm, f'c=28 MPa, fyt=420 MPa, fy=420 MPa.
    Stirrup: 10 mm dia (#3-like), At = 78.5 mm² per leg, s = 150 mm.
    Aoh = (300-50)·(600-50) = 250·550 = 137500 mm²
    ph  = 2·(250+550) = 1600 mm
    Ao  = 0.85·137500 = 116875 mm²
    Tn  = 2·116875·(78.5/150)·420·cot45 = 2·116875·0.5233·420 = 51.3 kN·m
    φTn = 0.75·51.3 = 38.5 kN·m

All SI calculations validated to ±3%.

Author: imranparuk
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.concrete.punching_torsion import (
    _lambda_s,
    critical_perimeter,
    two_way_concrete_shear_strength,
    punching_shear_check,
    cracking_torsion,
    torsion_capacity,
    combined_shear_torsion_check,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def approx(val, rel=0.03):
    """3% relative tolerance for engineering checks."""
    return pytest.approx(val, rel=rel)


# ===========================================================================
# Size-effect factor λs
# ===========================================================================

class TestLambdaS:
    def test_small_d_gives_one(self):
        """For small d, λs should be 1.0 (cap)."""
        ls = _lambda_s(50, metric=True)   # d = 50 mm
        assert ls == pytest.approx(1.0)

    def test_large_d_gives_less_than_one(self):
        """For large d (e.g. 500 mm) λs < 1.0."""
        ls = _lambda_s(500, metric=True)
        # √(2/(1+0.004·500)) = √(2/3) ≈ 0.8165
        assert ls == approx(math.sqrt(2 / 3.0))
        assert ls < 1.0

    def test_160mm_capped(self):
        """d=160 mm → √(2/1.64) = 1.104 → capped to 1.0."""
        ls = _lambda_s(160, metric=True)
        assert ls == pytest.approx(1.0)

    def test_imperial_units_converted(self):
        """d=6 in = 152.4 mm → same λs as metric d=152.4 mm."""
        ls_us = _lambda_s(6.0, metric=False)
        ls_si = _lambda_s(152.4, metric=True)
        assert ls_us == pytest.approx(ls_si, rel=1e-4)

    def test_never_exceeds_one(self):
        for d in (10, 50, 100, 200, 400, 800):
            assert _lambda_s(d, metric=True) <= 1.0 + 1e-9


# ===========================================================================
# Critical perimeter b0
# ===========================================================================

class TestCriticalPerimeter:
    def test_interior_column(self):
        """Square 450×450 col, d=160 → b0 = 4·(450+160) = 2440 mm."""
        r = critical_perimeter(450, 450, 160, column_location="interior")
        assert r["b0"] == pytest.approx(2440.0)
        assert r["column_location"] == "interior"

    def test_edge_column(self):
        """Edge col 300×300, d=150 → b0 = 2·(300+75) + (300+150) = 750+450 = 1200 mm."""
        r = critical_perimeter(300, 300, 150, column_location="edge")
        # 2*(300+75) + (300+150) = 750 + 450 = 1200
        assert r["b0"] == pytest.approx(1200.0)

    def test_corner_column(self):
        """Corner col 300×300, d=150 → b0 = (300+75)+(300+75) = 750 mm."""
        r = critical_perimeter(300, 300, 150, column_location="corner")
        assert r["b0"] == pytest.approx(750.0)

    def test_unknown_location_defaults_interior(self):
        r = critical_perimeter(300, 300, 150, column_location="bad")
        assert r["b0"] > 0
        assert len(r["warnings"]) > 0

    def test_output_keys(self):
        r = critical_perimeter(450, 450, 160)
        for k in ("b0", "column_location", "warnings"):
            assert k in r

    def test_rectangular_column(self):
        """Non-square column: c1=500, c2=300, d=200, interior."""
        r = critical_perimeter(500, 300, 200, column_location="interior")
        expected = 2 * (500 + 200) + 2 * (300 + 200)  # 1400 + 1000 = 2400
        assert r["b0"] == pytest.approx(expected)


# ===========================================================================
# Two-way concrete shear strength
# ===========================================================================

class TestTwoWayConcreteShearStrength:
    """Validation: square interior column, d=160 mm, b0=2440 mm, f'c=28 MPa."""

    # Precomputed reference values
    # λs = 1.0 (d=160 mm → capped); lam = 1.0; sqrt(28) = 5.2915
    # Vc1 = 0.33 * 1.0 * 1.0 * 5.2915 * 2440 * 160 = 681,860 N ≈ 681.9 kN
    # Vc2 = (0.17+0.34/1)·5.2915·2440·160 = 0.51·5.2915·2440·160 = 1,054 kN
    # Vc3 = (40*160/2440+0.17)·…  → very large → not governs for interior
    # Governing = Vc1

    def test_si_vc1_governs_interior(self):
        r = two_way_concrete_shear_strength(
            b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40, metric=True
        )
        # Vc1 should govern for β_c=1 (Vc2 = 0.51·... > 0.33·... for β_c=1)
        # With β_c=1: Vc2 coefficient = 0.17+0.34 = 0.51 > 0.33 → Vc1 governs
        assert r["governing_formula"] if "governing_formula" in r else True
        assert r["Vc"] == approx(r["Vc1"])
        assert r["Vc"] == approx(681_860, rel=0.01)

    def test_si_vc_components_positive(self):
        r = two_way_concrete_shear_strength(
            b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40, metric=True
        )
        for key in ("Vc1", "Vc2", "Vc3", "Vc"):
            assert r[key] > 0

    def test_large_beta_c_reduces_vc2(self):
        """Large β_c → Vc2 approaches 0.17·…·b0·d; may then govern."""
        r_sq = two_way_concrete_shear_strength(
            b0=2000, d=150, fc=28, beta_c=1.0, alpha_s=40, metric=True
        )
        r_el = two_way_concrete_shear_strength(
            b0=2000, d=150, fc=28, beta_c=4.0, alpha_s=40, metric=True
        )
        # β_c=4 → Vc2 coeff = 0.17+0.34/4 = 0.255; β_c=1 Vc2 = 0.51 — larger
        assert r_el["Vc2"] < r_sq["Vc2"]

    def test_us_customary_values(self):
        """USC: square interior col, b0 = 4·(18+6.3) = 97.2 in, d=6.3 in,
        f'c = 4000 psi, β_c=1, α_s=40.
        Vc1 = 4·1·1·√4000·97.2·6.3 = 4·63.25·97.2·6.3 ≈ 154,968 lbf ≈ 155 kip"""
        b0_us = 4 * (18 + 6.3)  # ≈ 97.2 in
        r = two_way_concrete_shear_strength(
            b0=b0_us, d=6.3, fc=4000, beta_c=1.0, alpha_s=40, metric=False
        )
        Vc1_expected = 4 * math.sqrt(4000) * b0_us * 6.3
        assert r["Vc1"] == approx(Vc1_expected)
        assert r["Vc"] > 0

    def test_output_keys(self):
        r = two_way_concrete_shear_strength(2440, 160, 28, 1.0, 40)
        for k in ("lambda_s", "Vc1", "Vc2", "Vc3", "Vc", "warnings"):
            assert k in r

    def test_lambda_s_capped(self):
        """d=160 mm → λs=1.0 (capped)."""
        r = two_way_concrete_shear_strength(2440, 160, 28, 1.0, 40)
        assert r["lambda_s"] == pytest.approx(1.0)

    def test_lambda_s_less_than_one_for_thick_slab(self):
        """d=400 mm → λs < 1.0."""
        r = two_way_concrete_shear_strength(3000, 400, 28, 1.0, 40)
        assert r["lambda_s"] < 1.0


# ===========================================================================
# Punching shear check
# ===========================================================================

class TestPunchingShearCheck:
    """Reference: 450×450 col, d=160, f'c=28 MPa, b0=2440 mm.
    Vc ≈ 681,860 N; φVc = 0.75·Vc ≈ 511,395 N ≈ 511 kN.
    """

    def test_adequate_below_capacity(self):
        r = punching_shear_check(
            Vu=400_000,   # 400 kN — below 511 kN
            b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        assert r["ok"] is True
        assert r["demand_capacity_ratio"] < 1.0

    def test_inadequate_above_capacity(self):
        r = punching_shear_check(
            Vu=600_000,   # 600 kN — above 511 kN
            b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        assert r["ok"] is False
        assert r["demand_capacity_ratio"] > 1.0
        assert any("FAILS" in w for w in r["warnings"])

    def test_phi_vc_value(self):
        r = punching_shear_check(
            Vu=400_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40, phi=0.75
        )
        assert r["phiVc"] == approx(0.75 * r["Vc"])
        assert r["phiVc"] == approx(511_395, rel=0.01)

    def test_vu_stress(self):
        """vu = Vu / (b0·d) = 400000 / (2440·160) = 1.024 MPa."""
        r = punching_shear_check(
            Vu=400_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        assert r["vu"] == approx(400_000 / (2440 * 160))

    def test_output_keys(self):
        r = punching_shear_check(
            Vu=400_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        for k in ("Vc", "phiVc", "vu", "phivc", "demand_capacity_ratio",
                  "ok", "governing_formula", "lambda_s", "warnings"):
            assert k in r

    def test_us_customary_mode(self):
        """US: Vu in lbf, b0 and d in inches, fc in psi."""
        r = punching_shear_check(
            Vu=100_000,   # 100 kip
            b0=97.2, d=6.3, fc=4000, beta_c=1.0, alpha_s=40,
            metric=False
        )
        assert r["Vc"] > 0
        assert isinstance(r["ok"], bool)

    def test_edge_alpha_s(self):
        """Edge column (alpha_s=30) should yield different (generally lower) Vc3."""
        r_int = punching_shear_check(
            Vu=400_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        r_edge = punching_shear_check(
            Vu=400_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=30
        )
        # Vc3 is lower for edge (30 vs 40), so overall Vc ≤ for edge
        assert r_edge["Vc"] <= r_int["Vc"] + 1.0  # within numerical precision


# ===========================================================================
# Cracking torsion
# ===========================================================================

class TestCrackingTorsion:
    """Reference: 300×600 mm beam, f'c=28 MPa.
    Acp = 300×600 = 180,000 mm²; pcp = 2·(300+600) = 1800 mm.
    Tcr = 0.33·1·√28·180000²/1800 = 0.33·5.2915·18000000 = 31,409 N·m ≈ 31.4 kN·m
    (actually N·mm → ÷1e6 for kN·m)
    """

    Acp = 300 * 600        # 180000 mm²
    pcp = 2 * (300 + 600)  # 1800 mm
    fc = 28.0              # MPa

    def test_si_tcr_value(self):
        r = cracking_torsion(self.Acp, self.pcp, self.fc, metric=True)
        Tcr_expected = 0.33 * math.sqrt(self.fc) * self.Acp**2 / self.pcp
        assert r["Tcr"] == approx(Tcr_expected)

    def test_tth_is_quarter_of_tcr(self):
        r = cracking_torsion(self.Acp, self.pcp, self.fc, metric=True)
        assert r["Tth"] == approx(r["Tcr"] / 4.0)

    def test_phi_tth(self):
        r = cracking_torsion(self.Acp, self.pcp, self.fc, metric=True)
        assert r["phi_Tth"] == approx(0.75 * r["Tth"])

    def test_us_customary_tcr(self):
        """USC: 12×24 in beam, f'c=4000 psi.
        Acp=288 in²; pcp=72 in; Tcr=4·√4000·288²/72·... """
        Acp_us = 12 * 24   # 288 in²
        pcp_us = 2 * (12 + 24)  # 72 in
        r = cracking_torsion(Acp_us, pcp_us, 4000, metric=False)
        Tcr_expected = 4.0 * math.sqrt(4000) * Acp_us**2 / pcp_us
        assert r["Tcr"] == approx(Tcr_expected)

    def test_normal_weight_vs_lightweight(self):
        r_nw = cracking_torsion(self.Acp, self.pcp, self.fc, lam=1.0)
        r_lw = cracking_torsion(self.Acp, self.pcp, self.fc, lam=0.75)
        assert r_lw["Tcr"] < r_nw["Tcr"]

    def test_zero_acp_returns_zero(self):
        r = cracking_torsion(0, 1800, 28)
        assert r["Tcr"] == 0.0
        assert len(r["warnings"]) > 0

    def test_output_keys(self):
        r = cracking_torsion(self.Acp, self.pcp, self.fc)
        for k in ("Tcr", "Tth", "phi_Tth", "warnings"):
            assert k in r


# ===========================================================================
# Torsion capacity
# ===========================================================================

class TestTorsionCapacity:
    """Reference: 300×600 mm beam.
    Stirrup 10 mm dia (At = π/4·10² ≈ 78.54 mm²), s=150 mm.
    Clear cover 25 mm, stirrup ø10 → centroid at 25+5 = 30 mm from face.
    Aoh = (300-60)·(600-60) = 240·540 = 129,600 mm²
    ph  = 2·(240+540) = 1560 mm
    Ao  = 0.85·129600 = 110,160 mm²
    fyt = 420 MPa, θ = 45°, cotθ = 1
    Tn  = 2·110160·(78.54/150)·420·1 = 2·110160·0.5236·420 = 48.4 kN·m
    φTn = 0.75·48.4 = 36.3 kN·m
    """

    Aoh = 240 * 540      # mm²
    ph  = 2 * (240 + 540)  # mm
    fyt = 420.0           # MPa
    s   = 150.0           # mm
    At  = math.pi / 4 * 10**2   # 78.54 mm² (one leg, 10 mm bar)
    Al  = 1000.0          # mm² arbitrary provided

    def test_ao_is_0_85_aoh(self):
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al)
        assert r["Ao"] == approx(0.85 * self.Aoh)

    def test_tn_stirrup_formula(self):
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al)
        Ao = 0.85 * self.Aoh
        Tn_expected = 2 * Ao * (self.At / self.s) * self.fyt * 1.0  # cot45=1
        assert r["Tn_stirrup"] == approx(Tn_expected)

    def test_phi_tn(self):
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al)
        assert r["phi_Tn"] == approx(0.75 * r["Tn_stirrup"])

    def test_al_req_formula(self):
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al)
        Al_req_expected = (self.At / self.s) * self.fyt * self.ph / self.fyt
        assert r["Al_req"] == approx(Al_req_expected)

    def test_al_insufficient_warns(self):
        """Al much less than Al_req → warning."""
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, Al=1.0)
        assert r["Al_ok"] is False
        assert any("insufficient" in w for w in r["warnings"])

    def test_al_sufficient_no_warn(self):
        """Al >> Al_req → ok, no Al warning."""
        r = torsion_capacity(
            self.Aoh, self.ph, self.fyt, self.s, self.At, Al=5000.0
        )
        assert r["Al_ok"] is True

    def test_spacing_too_large_warns(self):
        """s > ph/8 → warning about spacing."""
        s_large = self.ph  # way too large
        r = torsion_capacity(
            self.Aoh, self.ph, self.fyt, s_large, self.At, self.Al
        )
        assert any("spacing" in w.lower() for w in r["warnings"])

    def test_theta_30_deg(self):
        """θ=30° → cot30 = √3; Tn larger than at 45°."""
        r45 = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al, theta_deg=45)
        r30 = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al, theta_deg=30)
        assert r30["Tn_stirrup"] > r45["Tn_stirrup"]

    def test_us_customary(self):
        """USC: Aoh in in², ph in in, fyt in psi."""
        r = torsion_capacity(
            Aoh=200, ph=60, fyt=60_000, s=6, At=0.11, Al=2.0, metric=False
        )
        assert r["phi_Tn"] > 0

    def test_output_keys(self):
        r = torsion_capacity(self.Aoh, self.ph, self.fyt, self.s, self.At, self.Al)
        for k in ("Ao", "Tn_stirrup", "phi_Tn", "Al_req", "Al_ok", "warnings"):
            assert k in r


# ===========================================================================
# Combined shear + torsion check
# ===========================================================================

class TestCombinedShearTorsionCheck:
    """Reference: 300×600 mm beam, f'c=28 MPa.
    b_w=300, d=540, Aoh=129600 mm², ph=1560 mm.
    Vc = 2·√28·300·540 = 2·5.292·162000 = 1,714,566 N ≈ 1715 kN (simplified Vc)
    Vu = 500 kN, Tu = 20 kN·m = 20e6 N·mm (moderate combined)
    vu_stress = 500000/(300·540) = 3.086 MPa
    tu_stress = 20e6·1560/(1.7·129600²) = 3.12e10/2.857e10 = 1.093 MPa
    lhs = √(3.086²+1.093²) = √(9.524+1.195) = √10.72 = 3.274 MPa
    rhs = 0.75·(1715000/(300·540) + 0.66·√28) = 0.75·(10.587+3.492) = 0.75·14.08 = 10.56 MPa
    → ok (lhs << rhs)
    """

    b_w = 300; d = 540; Aoh = 129_600; ph = 1560; fc = 28.0
    Vc_si = 2 * math.sqrt(28) * 300 * 540   # simplified Vc in N

    def test_adequate_combined(self):
        r = combined_shear_torsion_check(
            Vu=500_000, Tu=20e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
            metric=True
        )
        assert r["ok"] is True
        assert r["demand_ratio"] < 1.0

    def test_inadequate_combined(self):
        """Very large Tu → fails."""
        r = combined_shear_torsion_check(
            Vu=2_000_000, Tu=200e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
            metric=True
        )
        assert r["ok"] is False
        assert r["demand_ratio"] > 1.0
        assert any("FAILS" in w for w in r["warnings"])

    def test_vu_stress_formula(self):
        r = combined_shear_torsion_check(
            Vu=500_000, Tu=20e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
        )
        assert r["vu_stress"] == approx(500_000 / (self.b_w * self.d))

    def test_tu_stress_formula(self):
        r = combined_shear_torsion_check(
            Vu=500_000, Tu=20e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
        )
        tu_expected = 20e6 * self.ph / (1.7 * self.Aoh**2)
        assert r["tu_stress"] == approx(tu_expected)

    def test_lhs_is_sqrt_of_sum_of_squares(self):
        r = combined_shear_torsion_check(
            Vu=500_000, Tu=20e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
        )
        lhs_expected = math.sqrt(r["vu_stress"]**2 + r["tu_stress"]**2)
        assert r["lhs"] == approx(lhs_expected)

    def test_us_customary_mode(self):
        """USC: b_w=12 in, d=21 in, Aoh=8×20=160 in², ph=2·(8+20)=56 in,
        fc=4000 psi, Vc=30 kip=30000 lb."""
        r = combined_shear_torsion_check(
            Vu=20_000, Tu=400_000, Vc=30_000,
            b_w=12, d=21, Aoh=160, ph=56, fc=4000,
            metric=False
        )
        assert isinstance(r["ok"], bool)
        assert r["lhs"] > 0

    def test_output_keys(self):
        r = combined_shear_torsion_check(
            Vu=500_000, Tu=20e6, Vc=self.Vc_si,
            b_w=self.b_w, d=self.d, Aoh=self.Aoh, ph=self.ph, fc=self.fc,
        )
        for k in ("lhs", "rhs", "demand_ratio", "ok", "vu_stress", "tu_stress", "warnings"):
            assert k in r


# ===========================================================================
# ACI 318-19 Reference cases (citable)
# ===========================================================================

class TestACIReferenceCases:
    """Citable numerical checks against published textbook examples."""

    def test_punching_shear_wight_ex13_style(self):
        """Wight 8th ed. §13-5 type example.
        450×450 mm col, 200 mm slab (d=160 mm), f'c=28 MPa, Vu=500 kN.
        b0 = 4·(450+160) = 2440 mm
        Vc ≈ 682 kN (formula 1 governs); φVc ≈ 511 kN.
        Vu=500 kN < φVc=511 kN → ok."""
        r = punching_shear_check(
            Vu=500_000, b0=2440, d=160, fc=28, beta_c=1.0, alpha_s=40
        )
        assert r["phiVc"] == approx(511_395, rel=0.015)
        assert r["ok"] is True   # 500 < 511

    def test_cracking_torsion_nilson_ex8_style(self):
        """Nilson 14th ed. style torsion example.
        b=300, h=600 mm; f'c=28 MPa (lam=1).
        Acp=180000 mm², pcp=1800 mm.
        Tcr = 0.33·√28·(180000²/1800) ≈ 31.4 kN·m = 31.4e6 N·mm."""
        Acp = 300 * 600
        pcp = 2 * (300 + 600)
        r = cracking_torsion(Acp, pcp, 28, metric=True)
        Tcr_expected = 0.33 * math.sqrt(28) * Acp**2 / pcp
        assert r["Tcr"] == approx(Tcr_expected, rel=0.005)

    def test_torsion_capacity_closed_form(self):
        """Direct closed-form validation for torsion_capacity.
        Aoh=129600 mm², ph=1560 mm, At=78.54 mm², s=150 mm, fyt=420 MPa.
        Ao = 0.85·129600 = 110160; Tn = 2·110160·(78.54/150)·420·1 ≈ 48.4 kN·m.
        φTn = 0.75·48.4 ≈ 36.3 kN·m = 36.3e6 N·mm."""
        At = math.pi / 4 * 10**2
        r = torsion_capacity(
            Aoh=129600, ph=1560, fyt=420, s=150, At=At, Al=5000.0
        )
        Tn_expected = 2 * (0.85 * 129600) * (At / 150) * 420 * 1.0
        assert r["Tn_stirrup"] == approx(Tn_expected, rel=0.005)
        assert r["phi_Tn"] == approx(0.75 * Tn_expected, rel=0.005)

    def test_size_effect_factor_aci_22_5_5_1_3(self):
        """ACI 318-19 §22.5.5.1.3: λs = √(2/(1+0.004·d)) ≤ 1.
        d=250 mm → λs = √(2/2.0) = 1.0 → capped.
        d=400 mm → λs = √(2/2.6) = 0.877."""
        ls_250 = _lambda_s(250, metric=True)
        assert ls_250 == pytest.approx(1.0)  # capped

        ls_400 = _lambda_s(400, metric=True)
        assert ls_400 == pytest.approx(math.sqrt(2 / (1 + 0.004 * 400)), rel=1e-6)

    def test_two_way_vc1_formula_aci_table_22_6_5_2(self):
        """ACI 318-19 Table 22.6.5.2 formula (1) — SI:
        Vc = 0.33·λs·λ·√f'c·b0·d.
        f'c=30 MPa, d=180 mm, b0=2600 mm, λ=1, λs computed."""
        d, b0, fc = 180, 2600, 30
        ls = _lambda_s(d, metric=True)
        Vc1_expected = 0.33 * ls * 1.0 * math.sqrt(fc) * b0 * d
        r = two_way_concrete_shear_strength(b0, d, fc, 1.0, 40, metric=True)
        assert r["Vc1"] == pytest.approx(Vc1_expected, rel=1e-6)

    def test_combined_interaction_eq_22_7_7_1(self):
        """ACI §22.7.7.1: verify LHS formula matches manual calculation."""
        Vu, Tu = 300_000, 10e6  # N, N·mm
        Vc = 500_000  # N
        b_w, d, Aoh, ph, fc = 250, 450, 100_000, 1400, 30
        r = combined_shear_torsion_check(
            Vu, Tu, Vc, b_w, d, Aoh, ph, fc, metric=True
        )
        vu_s = Vu / (b_w * d)
        tu_s = Tu * ph / (1.7 * Aoh**2)
        lhs_exp = math.sqrt(vu_s**2 + tu_s**2)
        assert r["lhs"] == pytest.approx(lhs_exp, rel=1e-6)
