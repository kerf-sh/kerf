"""
Tests for kerf_structural.masonry (TMS 402-16 ASD).

Covers
------
* masonry_flexure  — §8.3.4 WSD beam flexure (Fb, Fs, n, k, j)
* masonry_shear    — §8.3.5 allowable shear (Fvm, Fvs)
* masonry_axial    — §8.3.4.2 axial wall capacity with slenderness reduction
* LLM tool handlers — structural_masonry_flexure, structural_masonry_shear,
                       structural_masonry_axial

All oracle values are verified analytically; key cross-references:
  1. TMS 402-16 §8.3.4 / NCMA TEK 17-2A masonry beam design.
  2. TMS 402-16 Commentary Example C8.3.4.2 — axial wall slenderness.

Validation references
---------------------
Flexure:
  b=7.63", d=15.0", As=0.60 in², f'm=1500 psi, Grade 60.
  Em = 900×1500 = 1,350,000 psi; n = 29×10⁶/1,350,000 = 21.48.
  ρn = 0.00524 × 21.48 = 0.1126; k = 0.3751; j = 0.8750.
  Masonry governs: M_allow = 0.5×500×0.375×0.875×7.63×225 / 12 = 11.74 kip-ft.

Shear:
  f'm=1500 psi: Fvm = 1.5×√1500 = 58.09 psi.

Axial (TMS 402 Commentary Example C8.3.4.2):
  t=7.63", f'm=2000 psi, h=12 ft=144 in.
  r = 7.63/√12 = 2.2026 in; h/r = 65.38 ≤ 99.
  Fa = (2000/4)×(1−(65.38/140)²) = 500×0.7819 = 390.96 psi.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx():
    try:
        from kerf_structural._compat import ProjectCtx
    except ImportError:
        from types import SimpleNamespace
        return SimpleNamespace(pool=None, project_id=None)
    return ProjectCtx()


def _call(handler, payload: dict) -> dict:
    raw = asyncio.run(handler(_ctx(), json.dumps(payload).encode()))
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Masonry material helpers
# ---------------------------------------------------------------------------

class TestMasonryMaterialHelpers:
    def test_Em(self):
        """Em = 900 × f'm (TMS 402 §1.8.2.2)."""
        from kerf_structural.masonry import Em_masonry
        assert Em_masonry(2000) == pytest.approx(1_800_000.0)

    def test_modular_ratio_fm1500(self):
        """n = Es / Em = 29e6 / (900×1500) = 21.48."""
        from kerf_structural.masonry import modular_ratio
        n = modular_ratio(1500)
        assert n == pytest.approx(29_000_000 / 1_350_000, rel=1e-9)

    def test_Fb_allowable(self):
        """Fb = f'm / 3 (§8.3.4)."""
        from kerf_structural.masonry import Fb_allowable
        assert Fb_allowable(1500) == pytest.approx(500.0)
        assert Fb_allowable(2000) == pytest.approx(666.67, rel=1e-4)

    def test_Fs_grade60(self):
        """Fs = 24,000 psi for Grade 60 (§8.3.3.1)."""
        from kerf_structural.masonry import Fs_allowable
        assert Fs_allowable(60) == pytest.approx(24_000.0)

    def test_Fs_grade40(self):
        """Fs = 20,000 psi for Grade 40."""
        from kerf_structural.masonry import Fs_allowable
        assert Fs_allowable(40) == pytest.approx(20_000.0)

    def test_Fv_masonry(self):
        """Fvm = 1.5√f'm ≤ 120 psi (§8.3.5.1)."""
        from kerf_structural.masonry import Fv_masonry
        # f'm = 1500: 1.5×√1500 = 58.09 psi
        assert Fv_masonry(1500) == pytest.approx(58.09, rel=0.001)
        # f'm = 6400: 1.5×√6400 = 120 psi (at the cap)
        assert Fv_masonry(6400) == pytest.approx(120.0, abs=0.01)
        # f'm = 10000: capped at 120
        assert Fv_masonry(10_000) == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# masonry_flexure
# ---------------------------------------------------------------------------

class TestMasonryFlexure:
    """
    Reference section: b=7.63", d=15.0", As=0.60 in², f'm=1500 psi, Grade 60.
    Oracle: n=21.48, k=0.3751, j=0.8750, M_allow=11.74 kip-ft (masonry governs).
    """

    def test_ok(self):
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0, grade=60)
        assert res.ok

    def test_modular_ratio(self):
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        assert res.n == pytest.approx(21.48, rel=0.001)

    def test_k_value(self):
        """Neutral axis ratio k ≈ 0.3751."""
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        assert res.k == pytest.approx(0.3751, rel=0.002)

    def test_j_value(self):
        """j = 1 - k/3 ≈ 0.8750."""
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        assert res.j == pytest.approx(1.0 - res.k/3.0, rel=1e-9)

    def test_M_allow_kip_ft(self):
        """M_allow ≈ 11.74 kip-ft (masonry governs for As=0.60, d=15")."""
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        assert res.M_allow_kip_ft == pytest.approx(11.74, rel=0.005)

    def test_masonry_governs(self):
        """Masonry should govern (As > balanced → masonry stress controls)."""
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        assert res.governing == "masonry"

    def test_steel_governs_low_As(self):
        """Small As → steel governs."""
        from kerf_structural.masonry import masonry_flexure
        res = masonry_flexure(b=12.0, d=20.0, As=0.20, fm=2000.0, grade=60)
        assert res.governing == "steel"

    def test_actual_stresses_at_M_allow(self):
        """At M_allow, the governing material reaches its allowable."""
        from kerf_structural.masonry import masonry_flexure, Fb_allowable, Fs_allowable
        res = masonry_flexure(b=7.63, d=15.0, As=0.60, fm=1500.0)
        Fb = Fb_allowable(1500.0)
        Fs = Fs_allowable(60)
        if res.governing == "masonry":
            assert res.fb_actual == pytest.approx(Fb, rel=0.001)
        else:
            assert res.fs_actual == pytest.approx(Fs, rel=0.001)

    def test_larger_As_higher_M_allow(self):
        """More steel (while steel governs) → higher M_allow."""
        from kerf_structural.masonry import masonry_flexure
        res1 = masonry_flexure(b=12.0, d=20.0, As=0.60, fm=2000.0)
        res2 = masonry_flexure(b=12.0, d=20.0, As=1.20, fm=2000.0)
        assert res2.M_allow > res1.M_allow

    def test_first_principles_verification(self):
        """Directly verify b=12, d=18, As=1.0, fm=2000 against manual calculation."""
        from kerf_structural.masonry import masonry_flexure
        # n = 29e6/(900*2000) = 16.11
        # pn = (1.0/(12*18)) * 16.11 = 0.07460
        # k = -0.07460 + sqrt(0.07460^2 + 2*0.07460) = 0.3188
        # j = 1 - 0.3188/3 = 0.8937
        # Mm = 0.5 * (2000/3) * 0.3188 * 0.8937 * 12 * 18^2 / 12000 = 30.77 kip-ft
        res = masonry_flexure(b=12.0, d=18.0, As=1.0, fm=2000.0)
        assert res.n  == pytest.approx(16.11, rel=0.001)
        assert res.k  == pytest.approx(0.3188, rel=0.002)
        assert res.j  == pytest.approx(0.8937, rel=0.002)
        # M_allow dominated by min(Mm, Ms)
        assert 29.0 < res.M_allow_kip_ft < 34.0  # reasonable range


# ---------------------------------------------------------------------------
# masonry_shear
# ---------------------------------------------------------------------------

class TestMasonryShear:
    """Reference: b=7.63", d=15", f'm=1500 psi, no shear reinforcement."""

    def test_ok(self):
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=4.0, fm=1500.0)
        assert res.ok

    def test_Fvm_fm1500(self):
        """Fvm = 1.5√1500 = 58.09 psi."""
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=4.0, fm=1500.0)
        assert res.Fvm == pytest.approx(58.09, rel=0.001)

    def test_Fvm_capped_at_120(self):
        """For high f'm, Fvm capped at 120 psi."""
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=0.1, fm=10_000.0)
        assert res.Fvm == pytest.approx(120.0)

    def test_no_shear_rebar_Fvs_zero(self):
        """No shear reinforcement → Fvs = 0."""
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=1.0, fm=1500.0, Av=0.0)
        assert res.Fvs == pytest.approx(0.0)

    def test_shear_rebar_increases_capacity(self):
        """Adding stirrups increases Fv_total and Vallow."""
        from kerf_structural.masonry import masonry_shear
        res_no   = masonry_shear(b=7.63, d=15.0, Vu=1.0, fm=1500.0, Av=0.0)
        res_with = masonry_shear(b=7.63, d=15.0, Vu=1.0, fm=1500.0, Av=0.22, s=8.0)
        assert res_with.Vallow > res_no.Vallow

    def test_Vallow_formula(self):
        """Vallow = Fv_total × b × d / 1000 kips."""
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=2.0, fm=1500.0)
        assert res.Vallow == pytest.approx(res.Fv_total * 7.63 * 15.0 / 1000.0, rel=1e-6)

    def test_shear_ok_when_vu_le_vallow(self):
        """shear_ok = True when Vu ≤ Vallow."""
        from kerf_structural.masonry import masonry_shear
        res_ok  = masonry_shear(b=7.63, d=15.0, Vu=1.0, fm=1500.0)
        res_not = masonry_shear(b=7.63, d=15.0, Vu=100.0, fm=1500.0)
        assert res_ok.shear_ok is True
        assert res_not.shear_ok is False

    def test_demand_ratio(self):
        """demand_ratio = fv_actual / Fv_total."""
        from kerf_structural.masonry import masonry_shear
        res = masonry_shear(b=7.63, d=15.0, Vu=3.0, fm=1500.0)
        fv_actual = 3.0 * 1000 / (7.63 * 15.0)
        assert res.demand_ratio == pytest.approx(fv_actual / res.Fv_total, rel=1e-5)


# ---------------------------------------------------------------------------
# masonry_axial
# ---------------------------------------------------------------------------

class TestMasonryAxial:
    """
    Reference: TMS 402 Commentary Example C8.3.4.2.
    t=7.63", f'm=2000 psi, h=12 ft=144 in.
    r=2.2026 in, h/r=65.38 ≤ 99.
    Fa = (2000/4)×(1−(65.38/140)²) = 390.96 psi.
    """

    def test_ok(self):
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0)
        assert res.ok

    def test_r_value(self):
        """r = t / √12."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0)
        assert res.r == pytest.approx(7.63 / math.sqrt(12.0), rel=1e-9)

    def test_h_r_ratio(self):
        """h/r = 144 / (7.63/√12) ≈ 65.38."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0)
        assert res.h_r == pytest.approx(65.38, rel=0.001)

    def test_Fa_commentary_value(self):
        """Fa ≈ 390.96 psi (TMS 402 Commentary Example C8.3.4.2)."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0)
        assert res.Fa == pytest.approx(390.96, rel=0.002)

    def test_slenderness_regime_1_eq(self):
        """For h/r ≤ 99: Fa = (f'm/4)(1 − (h/140r)²)."""
        from kerf_structural.masonry import masonry_axial
        h, t, fm = 120.0, 7.63, 2000.0
        res = masonry_axial(h=h, t=t, fm=fm)
        r = t / math.sqrt(12)
        expected_Fa = (fm/4.0) * (1.0 - (h/(140*r))**2)
        assert res.Fa == pytest.approx(expected_Fa, rel=1e-9)

    def test_slenderness_regime_2(self):
        """For h/r > 99: Fa = (f'm/4)(70r/h)² (Eq. 8-22)."""
        from kerf_structural.masonry import masonry_axial
        # Need h/r > 99: use thin wall t=2.0", tall h=300 in
        res = masonry_axial(h=300.0, t=2.0, fm=2000.0)
        r = 2.0 / math.sqrt(12)
        h_r = 300.0 / r
        assert h_r > 99
        expected_Fa = (2000.0/4.0) * (70.0*r/300.0)**2
        assert res.Fa == pytest.approx(expected_Fa, rel=1e-9)

    def test_taller_wall_lower_Fa(self):
        """Taller wall (more slenderness) → lower Fa."""
        from kerf_structural.masonry import masonry_axial
        res_short = masonry_axial(h=96.0,  t=7.63, fm=2000.0)  # 8 ft
        res_tall  = masonry_axial(h=192.0, t=7.63, fm=2000.0)  # 16 ft
        assert res_tall.Fa < res_short.Fa

    def test_Pa_uses_An(self):
        """Pa = Fa × An / 1000 kips."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0)
        assert res.Pa == pytest.approx(res.Fa * res.An / 1000.0, rel=1e-9)

    def test_demand_ratio_zero_when_Pu_zero(self):
        """demand_ratio = 0 when Pu = 0."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0, Pu=0.0)
        assert res.demand_ratio == pytest.approx(0.0)

    def test_demand_ratio_nonzero_with_load(self):
        """demand_ratio = Pu / Pa when Pu > 0."""
        from kerf_structural.masonry import masonry_axial
        res = masonry_axial(h=144.0, t=7.63, fm=2000.0, Pu=10.0)
        assert res.demand_ratio == pytest.approx(10.0 / res.Pa, rel=1e-6)


# ---------------------------------------------------------------------------
# LLM Tool handler tests
# ---------------------------------------------------------------------------

class TestMasonryFlexureTool:
    def test_spec_name(self):
        from kerf_structural.masonry import masonry_flexure_spec
        assert masonry_flexure_spec.name == "structural_masonry_flexure"

    def test_valid_call(self):
        from kerf_structural.masonry import run_masonry_flexure
        result = _call(run_masonry_flexure, {
            "b": 7.63, "d": 15.0, "As": 0.60, "fm": 1500, "grade": 60,
        })
        assert result.get("ok") is True
        assert "M_allow_kip_ft" in result
        assert result["M_allow_kip_ft"] > 0

    def test_bad_json(self):
        from kerf_structural.masonry import run_masonry_flexure
        raw = asyncio.run(run_masonry_flexure(_ctx(), b"not-json"))
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_missing_required_field(self):
        from kerf_structural.masonry import run_masonry_flexure
        result = _call(run_masonry_flexure, {"b": 7.63, "d": 15.0})  # missing As
        assert "error" in result


class TestMasonryShearTool:
    def test_spec_name(self):
        from kerf_structural.masonry import masonry_shear_spec
        assert masonry_shear_spec.name == "structural_masonry_shear"

    def test_valid_call(self):
        from kerf_structural.masonry import run_masonry_shear
        result = _call(run_masonry_shear, {
            "b": 7.63, "d": 15.0, "Vu": 4.0, "fm": 1500,
        })
        assert result.get("ok") is True
        assert result["Fvm_psi"] == pytest.approx(58.09, rel=0.002)
        assert result["shear_ok"] is True

    def test_bad_json(self):
        from kerf_structural.masonry import run_masonry_shear
        raw = asyncio.run(run_masonry_shear(_ctx(), b"bad"))
        assert json.loads(raw).get("code") == "BAD_ARGS"


class TestMasonryAxialTool:
    def test_spec_name(self):
        from kerf_structural.masonry import masonry_axial_spec
        assert masonry_axial_spec.name == "structural_masonry_axial"

    def test_valid_call(self):
        from kerf_structural.masonry import run_masonry_axial
        result = _call(run_masonry_axial, {
            "h": 144.0, "t": 7.63, "fm": 2000,
        })
        assert result.get("ok") is True
        assert result["Fa_psi"] == pytest.approx(390.96, rel=0.002)

    def test_bad_json(self):
        from kerf_structural.masonry import run_masonry_axial
        raw = asyncio.run(run_masonry_axial(_ctx(), b"bad"))
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_missing_required_field(self):
        from kerf_structural.masonry import run_masonry_axial
        result = _call(run_masonry_axial, {"h": 144.0})  # missing t
        assert "error" in result
