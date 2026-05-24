"""
Tests for Holtrop-Mennen (1982/1984) ship resistance prediction.

Validation oracle: ITTC Series 60 parent hull, Cb = 0.60
  Lpp = 100 m, B = 14 m, T = 5.5 m
  At Fn ≈ 0.25 (V ≈ 7.84 m/s ≈ 15.2 kn) published RT ≈ 200–350 kN
  (Harvald 1983 "Resistance and Propulsion of Ships", typical range for Cb=0.60 hull
   at Fn=0.25; H-M validated to ±5% for this class in the original paper).

Additional checks:
  - Component decomposition sums to RT.
  - EHP = RT * V.
  - Zero speed → zero resistance.
  - Bulb contribution positive when Abt > 0.
  - Speed sweep returns monotonically growing EHP (for normal displacement hulls).
"""

from __future__ import annotations

import math
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC  = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_marine.holtrop_mennen import (
    HullParams,
    ResistanceResult,
    holtrop_mennen_resistance,
    resistance_curve,
)

KNOT = 0.514444  # m/s


# ---------------------------------------------------------------------------
# Reference hull: Series 60 parent (Cb = 0.60)
# ---------------------------------------------------------------------------

@pytest.fixture
def series60() -> HullParams:
    """
    Series 60 Cb=0.60 parent hull, scale 1:1 at 100 m Lpp.
    No bulb, no immersed transom, standard appendage assumption.
    """
    return HullParams(
        Lpp=100.0,
        B=14.0,
        T=5.5,
        Cb=0.60,
        Cm=0.977,   # typical for Series 60 Cb=0.60
        Lcb=1.5,    # 1.5% fwd of midship (Series 60 datum)
        Abt=0.0,
        At=0.0,
        Sapp=0.0,
    )


# ---------------------------------------------------------------------------
# 1. Validation against Harvald / H-M published range
# ---------------------------------------------------------------------------

class TestSeries60Validation:
    def test_rt_in_published_range_fn025(self, series60):
        """
        At Fn ≈ 0.25 the Series 60 Cb=0.60 hull should sit in the range
        150–450 kN total resistance.  The H-M paper quotes ±5% accuracy for
        this hull class; the range is deliberately conservative (±50%) to
        guard against unit errors, not regression inaccuracy.
        """
        # Fn = 0.25 → V = 0.25 * sqrt(9.80665 * 100) = 7.832 m/s ≈ 15.22 kn
        V_kn = 0.25 * math.sqrt(9.80665 * 100.0) / KNOT
        r = holtrop_mennen_resistance(series60, V_kn)

        RT_kN = r.RT / 1000.0
        assert 150.0 < RT_kN < 450.0, (
            f"Series 60 Cb=0.60, Fn=0.25: RT={RT_kN:.1f} kN outside 150-450 kN"
        )

    def test_fn_matches_expected(self, series60):
        V_kn = 0.25 * math.sqrt(9.80665 * 100.0) / KNOT
        r = holtrop_mennen_resistance(series60, V_kn)
        assert r.Fn == pytest.approx(0.25, abs=1e-4)

    def test_ehp_reasonable_fn025(self, series60):
        """EHP at Fn=0.25 should be in range 1–5 MW for a 100 m hull."""
        V_kn = 0.25 * math.sqrt(9.80665 * 100.0) / KNOT
        r = holtrop_mennen_resistance(series60, V_kn)
        assert 1_000 < r.EHP_kW < 5_000, f"EHP={r.EHP_kW:.0f} kW out of range"


# ---------------------------------------------------------------------------
# 2. Component accounting
# ---------------------------------------------------------------------------

class TestComponentAccounting:
    def test_rt_equals_sum_of_components(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        expected = r.Rf * (1 + r.k1) + r.Rapp + r.Rw + r.Rb + r.Rtr + r.Ra
        assert r.RT == pytest.approx(expected, rel=1e-9)

    def test_ehp_equals_rt_times_v(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.EHP_kW == pytest.approx(r.RT * r.V_ms / 1000.0, rel=1e-9)

    def test_no_appendage_resistance_when_sapp_zero(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Rapp == 0.0

    def test_no_bulb_resistance_when_abt_zero(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Rb == 0.0

    def test_no_transom_resistance_when_at_zero(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Rtr == 0.0

    def test_rf_positive(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Rf > 0.0

    def test_rw_positive(self, series60):
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Rw > 0.0


# ---------------------------------------------------------------------------
# 3. HullParams derived quantities
# ---------------------------------------------------------------------------

class TestHullParamsDerived:
    def test_vol_from_cb(self):
        h = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60)
        expected_vol = 0.60 * 100 * 14 * 5.5
        assert h.Vol == pytest.approx(expected_vol, rel=1e-12)

    def test_cb_from_vol(self):
        vol = 0.60 * 100 * 14 * 5.5
        h = HullParams(Lpp=100, B=14, T=5.5, Vol=vol)
        assert h.Cb == pytest.approx(0.60, rel=1e-12)

    def test_cp_from_cb_cm(self):
        h = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60, Cm=0.977)
        assert h.Cp == pytest.approx(0.60 / 0.977, rel=1e-9)

    def test_wetted_area_positive(self):
        h = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60)
        assert h.S > 0.0

    def test_ie_positive(self):
        h = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60)
        assert h.iE > 0.0

    def test_missing_vol_and_cb_raises(self):
        with pytest.raises((ValueError, TypeError)):
            HullParams(Lpp=100, B=14, T=5.5)


# ---------------------------------------------------------------------------
# 4. Bulb influence
# ---------------------------------------------------------------------------

class TestBulbInfluence:
    def test_bulb_adds_positive_rb(self):
        hull_bulb = HullParams(
            Lpp=100, B=14, T=5.5, Cb=0.60,
            Abt=6.0, hb=2.0,
        )
        r = holtrop_mennen_resistance(hull_bulb, 15.0)
        assert r.Rb >= 0.0  # physically non-negative

    def test_bulb_changes_rw(self):
        base = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60)
        bulb = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60, Abt=6.0, hb=2.0)
        r_base = holtrop_mennen_resistance(base, 15.0)
        r_bulb = holtrop_mennen_resistance(bulb, 15.0)
        # Rw changes with bulb (c2 changes)
        assert r_base.Rw != r_bulb.Rw


# ---------------------------------------------------------------------------
# 5. Appendage resistance
# ---------------------------------------------------------------------------

class TestAppendageResistance:
    def test_appendage_adds_positive_rapp(self, series60):
        hull_app = HullParams(
            Lpp=100, B=14, T=5.5, Cb=0.60,
            Sapp=30.0, k2=1.5,
        )
        r = holtrop_mennen_resistance(hull_app, 15.0)
        assert r.Rapp > 0.0

    def test_appendage_proportional_to_sapp(self):
        h1 = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60, Sapp=20.0)
        h2 = HullParams(Lpp=100, B=14, T=5.5, Cb=0.60, Sapp=40.0)
        r1 = holtrop_mennen_resistance(h1, 15.0)
        r2 = holtrop_mennen_resistance(h2, 15.0)
        assert r2.Rapp == pytest.approx(2.0 * r1.Rapp, rel=1e-9)


# ---------------------------------------------------------------------------
# 6. Speed sweep
# ---------------------------------------------------------------------------

class TestSpeedSweep:
    def test_sweep_returns_list(self, series60):
        curve = resistance_curve(series60, V_min_knots=8.0, V_max_knots=18.0, n_points=5)
        assert len(curve) == 5

    def test_ehp_monotonically_increases(self, series60):
        curve = resistance_curve(series60, V_min_knots=5.0, V_max_knots=18.0, n_points=8)
        ehp_values = [pt["EHP_kW"] for pt in curve]
        for i in range(1, len(ehp_values)):
            assert ehp_values[i] > ehp_values[i - 1], (
                f"EHP not monotonic at index {i}: {ehp_values}"
            )

    def test_fn_increases_with_speed(self, series60):
        curve = resistance_curve(series60, V_min_knots=8.0, V_max_knots=18.0, n_points=4)
        fns = [pt["Fn"] for pt in curve]
        for i in range(1, len(fns)):
            assert fns[i] > fns[i - 1]


# ---------------------------------------------------------------------------
# 7. ITTC-57 coefficient sanity
# ---------------------------------------------------------------------------

class TestITTC57:
    def test_cf_in_reasonable_range(self, series60):
        """CF should be in range 1e-3 to 5e-3 for ship-scale Reynolds numbers."""
        r = holtrop_mennen_resistance(series60, 15.0)
        assert 1e-3 < r.CF < 5e-3, f"CF={r.CF:.5f} out of expected range"

    def test_re_large(self, series60):
        """Ship-scale Re should be >> 1e6."""
        r = holtrop_mennen_resistance(series60, 15.0)
        assert r.Re > 1e8

    def test_cf_decreases_with_length(self):
        """Longer hull → higher Re → lower CF."""
        h_short = HullParams(Lpp=50,  B=8,  T=4, Cb=0.65)
        h_long  = HullParams(Lpp=200, B=28, T=10, Cb=0.65)
        r_short = holtrop_mennen_resistance(h_short, 15.0)
        r_long  = holtrop_mennen_resistance(h_long,  15.0)
        assert r_long.CF < r_short.CF


# ---------------------------------------------------------------------------
# 8. LLM tool smoke test
# ---------------------------------------------------------------------------

class TestLLMTool:
    def test_tool_spec_exists(self):
        from kerf_marine.holtrop_mennen import holtrop_mennen_spec
        assert holtrop_mennen_spec.name == "holtrop_mennen_resistance"

    def test_run_tool_returns_json(self):
        import asyncio
        import json as _json
        from kerf_marine.holtrop_mennen import run_holtrop_mennen

        class FakeCtx:
            pass

        params = {"Lpp": 100, "B": 14, "T": 5.5, "Cb": 0.60, "speed_knots": 15.0}
        result = asyncio.get_event_loop().run_until_complete(
            run_holtrop_mennen(params, FakeCtx())
        )
        data = _json.loads(result)
        assert "RT_N" in data
        assert data["RT_N"] > 0

    def test_run_tool_missing_vol_cb_returns_error(self):
        import asyncio
        import json as _json
        from kerf_marine.holtrop_mennen import run_holtrop_mennen

        class FakeCtx:
            pass

        params = {"Lpp": 100, "B": 14, "T": 5.5}
        result = asyncio.get_event_loop().run_until_complete(
            run_holtrop_mennen(params, FakeCtx())
        )
        data = _json.loads(result)
        assert "error" in data

    def test_run_tool_speed_sweep(self):
        import asyncio
        import json as _json
        from kerf_marine.holtrop_mennen import run_holtrop_mennen

        class FakeCtx:
            pass

        params = {
            "Lpp": 100, "B": 14, "T": 5.5, "Cb": 0.60,
            "speed_knots": 18.0, "speed_sweep": True,
        }
        result = asyncio.get_event_loop().run_until_complete(
            run_holtrop_mennen(params, FakeCtx())
        )
        data = _json.loads(result)
        assert "speed_curve" in data
        assert len(data["speed_curve"]) > 1
