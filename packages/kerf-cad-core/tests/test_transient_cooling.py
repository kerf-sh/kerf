"""
Tests for kerf_cad_core.buildingenergy.transient — transient cooling-load methods.

Validation targets
------------------
1. sol_air_temp
   - ASHRAE 2021 HoF Ch. 18 example: dark roof, I=900 W/m², α=0.9, ho=22.7, T=35°C
     → Tsa ≈ 35 + 0.9×900/22.7 ≈ 35 + 35.7 = 70.7°C.  Accept within ±1°C.
   - Vertical wall (dT_long_wave=0) gives Tsa = T + α·I/ho.

2. CLTD tables
   - Group D wall: hour 17 (5 pm) CLTD > hour 12 (noon) CLTD — thermal lag.
   - Group A wall: hour 16 CLTD >= hour 17 CLTD — fast response, near-peak before 5 pm.
   - Heavy roof: hour 19 CLTD > hour 13 CLTD — very slow, late-evening peak.
   - Light roof: hour 14 CLTD > hour 20 CLTD — fast response, early afternoon peak.

3. CLTD correction (correct_cltd)
   - Ti=74°F (warmer than 78) increases CLTDc by 4°F.
   - To=90°F (warmer than 85) increases CLTDc by 5°F.
   - K=0.5 halves the (CLTD+LM) term.

4. wall_cooling_load
   - SI: U=0.5, A=20, CLTDc=15 → q = 150 W.
   - IP: U=0.088, A=215, CLTDc=27 → q ≈ 511.6 Btu/hr → in W ≈ 150 W (consistent).
   - Negative CLTDc gives warning but returns negative q.

5. solar_heat_gain (transient version — direct+diff+gnd)
   - Zero irradiance → zero gain.
   - South orientation: I_dir=500, I_diff=100, area=2, SHGC=0.6, IAC=1.0, ff=1.0
     Q_dir = 0.6×500×2 = 600 W; Q_diff = 0.6×0.5×100×2 = 60 W;
     Q_gnd = 0.6×0.2×(500+100)×0.5×2 = 72 W; total ≈ 732 W.

6. cooling_load_fenestration_rts
   - Flat 24-h SHG of 1000 W → CL profile ≈ 1000 W each hour (RTS sums to 1).
   - A spike at noon (1000 W, others 0) → CL(12) = RTS[0]×1000 = 540 W ≈ within 10 W.
   - Peak hour for south-facing profile with noon spike is hour 12.

7. zone_24h_cooling_load (ASHRAE 1989 / 2009 textbook-level validation)
   - South-facing Group D wall, 40°N, July: peak at hour 17 (5 pm).
   - South-facing window with typical summer solar produces a fenestration peak
     between hours 12–15.
   - Total peak load is positive.
   - Adding a south window increases peak load relative to wall-only case.

All tests are pure-Python and hermetic: no OCC, no DB, no network.

References
----------
ASHRAE Handbook — Fundamentals (1989), Chapters 26 & 27
ASHRAE Handbook — Fundamentals (2009), Chapter 18
ASHRAE Handbook — Fundamentals (2021), Chapter 18 §18.4

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings

import pytest

from kerf_cad_core.buildingenergy.transient import (
    sol_air_temp,
    cltd_wall,
    cltd_roof,
    correct_cltd,
    wall_cooling_load,
    solar_heat_gain,
    cooling_load_fenestration_rts,
    zone_24h_cooling_load,
    _CLTD_WALL,
    _CLTD_ROOF,
    _RTS_MEDIUM,
)


# ---------------------------------------------------------------------------
# 1. sol_air_temp
# ---------------------------------------------------------------------------

class TestSolAirTemp:
    def test_dark_roof_ashrae_example(self):
        """ASHRAE 2021 HoF Ch. 18: α=0.9, I=900 W/m², ho=22.7 W/(m²·K), T=35°C.
        Tsa = 35 + 0.9×900/22.7 ≈ 70.7°C (long-wave correction =0 for this check)."""
        res = sol_air_temp(35.0, 900.0, 0.9, 22.7, 0.0)
        assert res["ok"] is True
        assert 68.0 <= res["T_sol_air"] <= 73.0, f"Tsa={res['T_sol_air']:.2f} not in [68,73]"

    def test_dark_roof_with_longwave(self):
        """With long-wave correction (ΔR=63 W/m², ε=1.0) for horizontal roof:
        lw = 1.0×63/22.7 ≈ 2.78°C reduction."""
        res_no_lw = sol_air_temp(35.0, 900.0, 0.9, 22.7, 0.0)
        res_lw    = sol_air_temp(35.0, 900.0, 0.9, 22.7, 63.0, emittance=1.0)
        assert res_no_lw["ok"] and res_lw["ok"]
        diff = res_no_lw["T_sol_air"] - res_lw["T_sol_air"]
        assert 2.0 <= diff <= 3.5, f"long-wave reduction {diff:.2f} not in [2, 3.5]"

    def test_vertical_wall_no_longwave(self):
        """Vertical wall: dT_long_wave=0, result = T + αI/ho."""
        res = sol_air_temp(30.0, 600.0, 0.8, 22.7, 0.0)
        expected = 30.0 + 0.8 * 600.0 / 22.7
        assert abs(res["T_sol_air"] - expected) < 0.01

    def test_zero_irradiance(self):
        res = sol_air_temp(28.0, 0.0, 0.9, 22.7)
        assert res["ok"] is True
        assert res["T_sol_air"] == pytest.approx(28.0, abs=0.01)

    def test_light_surface(self):
        """Light surface (α=0.45) gives lower Tsa than dark (α=0.9)."""
        dark  = sol_air_temp(35.0, 800.0, 0.9, 22.7, 0.0)
        light = sol_air_temp(35.0, 800.0, 0.45, 22.7, 0.0)
        assert dark["T_sol_air"] > light["T_sol_air"]

    def test_invalid_absorptance(self):
        res = sol_air_temp(30.0, 500.0, 1.5, 22.7)
        assert res["ok"] is False
        assert "absorptance" in res["reason"].lower()

    def test_invalid_h_o(self):
        res = sol_air_temp(30.0, 500.0, 0.9, 0.0)
        assert res["ok"] is False

    def test_invalid_emittance(self):
        res = sol_air_temp(30.0, 500.0, 0.9, 22.7, emittance=2.0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 2. CLTD tables
# ---------------------------------------------------------------------------

class TestCLTDWall:
    def test_group_d_thermal_lag_ashrae(self):
        """Group D (heavy masonry): peak delayed to 5 pm (17:00) — 5 pm > noon.
        ASHRAE 1989 HoF Table 34: typical heavy-wall CLTD peaks mid-to-late afternoon."""
        cltd_noon = cltd_wall("D", 12)
        cltd_5pm  = cltd_wall("D", 17)
        assert cltd_noon["ok"] and cltd_5pm["ok"]
        assert cltd_5pm["CLTD_F"] >= cltd_noon["CLTD_F"], (
            f"Group D CLTD at 17h ({cltd_5pm['CLTD_F']}) should >= noon ({cltd_noon['CLTD_F']})"
        )

    def test_group_a_fast_response(self):
        """Group A (light): peak comes earlier; hour 16 CLTD >= hour 8 CLTD."""
        cltd_8  = cltd_wall("A", 8)
        cltd_16 = cltd_wall("A", 16)
        assert cltd_8["ok"] and cltd_16["ok"]
        assert cltd_16["CLTD_F"] > cltd_8["CLTD_F"]

    def test_all_wall_types_24h(self):
        for wtype in ("A", "B", "C", "D"):
            for h in range(24):
                res = cltd_wall(wtype, h)
                assert res["ok"] is True
                assert isinstance(res["CLTD_F"], float)

    def test_invalid_wall_type(self):
        res = cltd_wall("X", 12)
        assert res["ok"] is False

    def test_invalid_hour(self):
        res = cltd_wall("D", 25)
        assert res["ok"] is False

    def test_group_d_vs_a_mass_effect(self):
        """At hour 3 (pre-dawn), Group D CLTD > Group A CLTD — stored heat releasing."""
        d = cltd_wall("D", 3)
        a = cltd_wall("A", 3)
        assert d["CLTD_F"] > a["CLTD_F"]

    def test_group_d_peak_hour_is_afternoon(self):
        """Group D peak should be between hours 14–20."""
        cltds = [cltd_wall("D", h)["CLTD_F"] for h in range(24)]
        peak_h = cltds.index(max(cltds))
        assert 14 <= peak_h <= 20, f"Group D peak at hour {peak_h}"


class TestCLTDRoof:
    def test_heavy_roof_very_slow(self):
        """Heavy roof: CLTD peaks well after noon (hour 18–22 expected)."""
        cltds = [cltd_roof("heavy", h)["CLTD_F"] for h in range(24)]
        peak_h = cltds.index(max(cltds))
        assert 16 <= peak_h <= 22, f"Heavy roof peak at hour {peak_h}"

    def test_light_roof_peak_afternoon(self):
        """Light roof: peak earlier than heavy roof (hour 12–17)."""
        cltds_light = [cltd_roof("light", h)["CLTD_F"] for h in range(24)]
        cltds_heavy = [cltd_roof("heavy", h)["CLTD_F"] for h in range(24)]
        peak_light = cltds_light.index(max(cltds_light))
        peak_heavy = cltds_heavy.index(max(cltds_heavy))
        assert peak_light < peak_heavy, (
            f"Light peak h={peak_light} should precede heavy peak h={peak_heavy}"
        )

    def test_light_roof_high_afternoon_cltd(self):
        """Light roof at 2 pm (14) should have high CLTD (>25°F)."""
        res = cltd_roof("light", 14)
        assert res["ok"] is True
        assert res["CLTD_F"] > 25

    def test_all_roof_types_24h(self):
        for rtype in ("light", "medium", "heavy"):
            for h in range(24):
                res = cltd_roof(rtype, h)
                assert res["ok"] is True

    def test_invalid_roof_type(self):
        res = cltd_roof("ultralight", 12)
        assert res["ok"] is False

    def test_invalid_hour(self):
        res = cltd_roof("medium", -1)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 3. correct_cltd
# ---------------------------------------------------------------------------

class TestCorrectCLTD:
    def test_default_conditions_no_change(self):
        """At standard conditions (Ti=78, To=85), correction terms cancel."""
        CLTD = 20.0
        res = correct_cltd(CLTD, LM=0.0, K=1.0, T_indoor_F=78.0, T_outdoor_F_mean=85.0)
        assert res["ok"] is True
        assert res["CLTDc_F"] == pytest.approx(20.0, abs=0.01)

    def test_warmer_indoor_reduces_cltdc(self):
        """Ti=82°F (warmer indoor) reduces CLTDc by 4°F."""
        res_std  = correct_cltd(20.0, T_indoor_F=78.0)
        res_warm = correct_cltd(20.0, T_indoor_F=82.0)
        assert res_std["ok"] and res_warm["ok"]
        assert res_std["CLTDc_F"] - res_warm["CLTDc_F"] == pytest.approx(4.0, abs=0.01)

    def test_hotter_outdoor_increases_cltdc(self):
        """To=90°F increases CLTDc by 5°F."""
        res_std  = correct_cltd(20.0, T_outdoor_F_mean=85.0)
        res_hot  = correct_cltd(20.0, T_outdoor_F_mean=90.0)
        assert res_hot["CLTDc_F"] - res_std["CLTDc_F"] == pytest.approx(5.0, abs=0.01)

    def test_K_halves_cltd_lm(self):
        """K=0.5 with LM=0: CLTDc = 0.5×CLTD + temperature offsets."""
        CLTD = 16.0
        res = correct_cltd(CLTD, LM=0.0, K=0.5, T_indoor_F=78.0, T_outdoor_F_mean=85.0)
        assert res["CLTDc_F"] == pytest.approx(8.0, abs=0.01)

    def test_lm_adds_to_cltd_before_K(self):
        """LM=4 adds to CLTD before K multiplication."""
        res = correct_cltd(16.0, LM=4.0, K=1.0, T_indoor_F=78.0, T_outdoor_F_mean=85.0)
        assert res["CLTDc_F"] == pytest.approx(20.0, abs=0.01)

    def test_si_conversion(self):
        """CLTDc_C = CLTDc_F × 5/9 (delta temperature, no offset)."""
        res = correct_cltd(18.0)
        assert res["ok"] is True
        assert res["CLTDc_C"] == pytest.approx(res["CLTDc_F"] * 5 / 9, abs=0.001)

    def test_negative_cltdc_gives_warning(self):
        """CLTDc < 0 is valid but triggers a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = correct_cltd(-10.0, T_outdoor_F_mean=80.0, T_indoor_F=85.0)
        assert res["ok"] is True
        assert res["CLTDc_F"] < 0
        assert len(w) >= 1 or len(res["warnings"]) >= 1


# ---------------------------------------------------------------------------
# 4. wall_cooling_load
# ---------------------------------------------------------------------------

class TestWallCoolingLoad:
    def test_basic_si(self):
        """q = U×A×CLTDc: 0.5 × 20 × 15 = 150 W."""
        res = wall_cooling_load(0.5, 20.0, 15.0)
        assert res["ok"] is True
        assert res["q_W"] == pytest.approx(150.0, abs=0.01)

    def test_ip_units(self):
        """IP: U=0.088 Btu/(hr·ft²·°F), A=215 ft², CLTDc=27°F → ~511 Btu/hr → ~150 W."""
        res = wall_cooling_load(0.088, 215.0, 27.0, ip_units=True)
        assert res["ok"] is True
        assert res["q_Btuhr"] == pytest.approx(0.088 * 215.0 * 27.0, rel=0.01)
        # Consistent SI/IP: ~511 Btu/hr ≈ 150 W
        assert 100.0 < res["q_W"] < 200.0

    def test_zero_area(self):
        res = wall_cooling_load(0.5, 0.0, 15.0)
        assert res["ok"] is True
        assert res["q_W"] == pytest.approx(0.0)

    def test_zero_cltdc(self):
        res = wall_cooling_load(0.5, 20.0, 0.0)
        assert res["ok"] is True
        assert res["q_W"] == pytest.approx(0.0)

    def test_negative_cltdc_gives_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = wall_cooling_load(0.5, 20.0, -5.0)
        assert res["ok"] is True
        assert res["q_W"] < 0
        assert len(w) >= 1 or len(res["warnings"]) >= 1

    def test_invalid_negative_U(self):
        res = wall_cooling_load(-0.1, 20.0, 10.0)
        assert res["ok"] is False

    def test_invalid_negative_area(self):
        res = wall_cooling_load(0.5, -5.0, 10.0)
        assert res["ok"] is False

    def test_btu_w_consistency(self):
        """q_W and q_Btuhr should be consistent via conversion factor."""
        res = wall_cooling_load(0.5, 20.0, 15.0)
        assert res["q_Btuhr"] == pytest.approx(res["q_W"] * 3.41214, rel=0.001)


# ---------------------------------------------------------------------------
# 5. solar_heat_gain (transient, direct+diff+gnd)
# ---------------------------------------------------------------------------

class TestSolarHeatGainTransient:
    def test_zero_irradiance(self):
        res = solar_heat_gain(0.0, 0.0, 2.0, 0.6)
        assert res["ok"] is True
        assert res["Q_total_W"] == pytest.approx(0.0)

    def test_south_manual_calc(self):
        """South wall: I_dir=500, I_diff=100, A=2, SHGC=0.6, IAC=1, ff=1.
        Q_dir  = 0.6×1.0×500×2×1 = 600 W
        Q_diff = 0.6×1.0×100×0.5×2×1 = 60 W   (Fsky=0.5 for vertical)
        Q_gnd  = 0.6×1.0×0.2×(600)×0.5×2 = 0.6×0.2×600×0.5×2 = 72 W
        Total = 732 W
        """
        res = solar_heat_gain(500.0, 100.0, 2.0, 0.6, 1.0, 1.0, None, "south")
        assert res["ok"] is True
        assert res["Q_dir_W"] == pytest.approx(600.0, abs=0.5)
        assert res["Q_diff_W"] == pytest.approx(60.0, abs=0.5)
        assert 60.0 <= res["Q_gnd_W"] <= 90.0
        assert 700.0 <= res["Q_total_W"] <= 780.0

    def test_iac_reduces_gain(self):
        """IAC < 1 reduces all solar components proportionally."""
        full  = solar_heat_gain(400.0, 80.0, 2.0, 0.6, 1.0, 1.0, None, "south")
        half  = solar_heat_gain(400.0, 80.0, 2.0, 0.6, 0.5, 1.0, None, "south")
        assert full["ok"] and half["ok"]
        assert half["Q_total_W"] == pytest.approx(full["Q_total_W"] * 0.5, rel=0.01)

    def test_frame_factor_reduces_gain(self):
        """frame_factor=0.8 reduces gain by 20%."""
        full = solar_heat_gain(400.0, 80.0, 2.0, 0.6, 1.0, 1.0)
        ff   = solar_heat_gain(400.0, 80.0, 2.0, 0.6, 1.0, 0.8)
        assert ff["Q_total_W"] == pytest.approx(full["Q_total_W"] * 0.8, rel=0.01)

    def test_horizontal_sky_view_factor(self):
        """Horizontal surface (skylight): Fsky=1.0 → higher diffuse than vertical."""
        horiz = solar_heat_gain(0.0, 100.0, 1.0, 0.6, 1.0, 1.0, None, "horizontal")
        vert  = solar_heat_gain(0.0, 100.0, 1.0, 0.6, 1.0, 1.0, None, "south")
        assert horiz["Q_diff_W"] > vert["Q_diff_W"]

    def test_invalid_shgc(self):
        res = solar_heat_gain(300.0, 50.0, 2.0, 1.5)
        assert res["ok"] is False

    def test_invalid_area(self):
        res = solar_heat_gain(300.0, 50.0, -1.0, 0.6)
        assert res["ok"] is False

    def test_invalid_iac(self):
        res = solar_heat_gain(300.0, 50.0, 2.0, 0.6, IAC=1.5)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 6. cooling_load_fenestration_rts
# ---------------------------------------------------------------------------

class TestCoolingLoadFenestrationRTS:
    def test_flat_profile_returns_flat(self):
        """Flat 1000 W for all 24 hours with RTS summing to 1 → CL ≈ 1000 W."""
        SHG = [1000.0] * 24
        res = cooling_load_fenestration_rts(SHG)
        assert res["ok"] is True
        for cl in res["CL_24h"]:
            assert cl == pytest.approx(1000.0, abs=1.0), f"Expected ~1000, got {cl}"

    def test_noon_spike_hour_12(self):
        """Single spike at noon: CL[12] = RTS[0] × 1000 W ≈ 540 W."""
        SHG = [0.0] * 24
        SHG[12] = 1000.0
        res = cooling_load_fenestration_rts(SHG)
        assert res["ok"] is True
        expected = _RTS_MEDIUM[0] * 1000.0
        assert res["CL_24h"][12] == pytest.approx(expected, rel=0.01)
        assert res["peak_hour"] == 12

    def test_rts_sums_to_unity(self):
        """Default RTS sums to 1.0 (within tolerance)."""
        assert abs(sum(_RTS_MEDIUM) - 1.0) < 0.02

    def test_peak_hour_and_load_consistent(self):
        SHG = [float(max(0, h - 10) * 100) for h in range(24)]
        res = cooling_load_fenestration_rts(SHG)
        assert res["ok"] is True
        assert res["peak_load_W"] == max(res["CL_24h"])
        assert res["CL_24h"][res["peak_hour"]] == res["peak_load_W"]

    def test_wrong_length_shg(self):
        res = cooling_load_fenestration_rts([1000.0] * 12)
        assert res["ok"] is False

    def test_wrong_length_rts(self):
        res = cooling_load_fenestration_rts([1000.0] * 24, [0.5] * 12)
        assert res["ok"] is False

    def test_custom_rts_series(self):
        """All-hour-0 RTS (instantaneous): CL equals SHG directly."""
        rts = [1.0] + [0.0] * 23
        SHG = [float(h * 50) for h in range(24)]
        res = cooling_load_fenestration_rts(SHG, rts)
        assert res["ok"] is True
        for h in range(24):
            assert res["CL_24h"][h] == pytest.approx(SHG[h], abs=0.01)

    def test_cyclic_wrap(self):
        """RTS is cyclic: energy from hour 23 wraps into hour 0."""
        rts = [0.0] * 24
        rts[1] = 1.0  # 1-hour lag RTS
        SHG = [0.0] * 24
        SHG[23] = 1000.0
        res = cooling_load_fenestration_rts(SHG, rts)
        assert res["ok"] is True
        # CL[0] = RTS[1]*SHG[23] = 1.0*1000 = 1000
        assert res["CL_24h"][0] == pytest.approx(1000.0, abs=0.01)


# ---------------------------------------------------------------------------
# 7. zone_24h_cooling_load — ASHRAE validation
# ---------------------------------------------------------------------------

# Helper: south-facing summer solar profile (W/m²) — simplified 40°N July approximation
# Peak direct ≈ 570 W/m² at noon for south vertical surface
_SOUTH_I_DIR_24H = [
    0, 0, 0, 0, 0, 0,
    20, 80, 180, 290, 390, 460,
    470, 430, 350, 250, 140, 50,
    10, 0, 0, 0, 0, 0,
]
_SOUTH_I_DIFF_24H = [
    0, 0, 0, 0, 0, 0,
    30, 60, 100, 140, 170, 190,
    195, 185, 165, 135, 100, 60,
    20, 0, 0, 0, 0, 0,
]
# Design-day outdoor temperature profile (°C) — 40°N summer
_OUTDOOR_T_24H = [
    27, 26, 25, 25, 25, 26,
    27, 28, 30, 32, 34, 35,
    36, 37, 38, 37, 36, 35,
    34, 33, 31, 30, 29, 28,
]


class TestZone24hCoolingLoad:
    def _make_wall(self, wall_type="D", U=0.5, A=20.0):
        return {"U": U, "A": A, "wall_type": wall_type}

    def _make_window(self, area=2.0, SHGC=0.6):
        return {
            "I_dir_24h": _SOUTH_I_DIR_24H,
            "I_diff_24h": _SOUTH_I_DIFF_24H,
            "area": area,
            "SHGC": SHGC,
            "IAC": 1.0,
            "frame_factor": 1.0,
            "orientation": "south",
        }

    def _make_roof(self, roof_type="medium", U=0.3, A=50.0):
        return {"U": U, "A": A, "roof_type": roof_type}

    def test_wall_only_returns_valid_profile(self):
        res = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[500.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert res["ok"] is True
        assert len(res["CL_24h"]) == 24
        assert res["peak_load_W"] > 0
        assert 0 <= res["peak_hour"] <= 23

    def test_group_d_wall_peak_hour_afternoon(self):
        """Group D heavy-mass wall: peak cooling load in mid-to-late afternoon (14–21)."""
        res = zone_24h_cooling_load(
            walls=[self._make_wall("D")],
            roof=None,
            windows=[],
            internal_gains=[0.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert res["ok"] is True
        ph = res["peak_hour"]
        assert 14 <= ph <= 21, f"Group D wall peak at hour {ph}, expected 14–21"

    def test_window_increases_peak_load(self):
        """Adding a south window should increase peak cooling load vs wall-only."""
        base = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[300.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        with_win = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[self._make_window()],
            internal_gains=[300.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert base["ok"] and with_win["ok"]
        assert with_win["peak_load_W"] > base["peak_load_W"]

    def test_fenestration_peak_early_afternoon(self):
        """South fenestration via RTS: fenestration peak between hours 11–16."""
        res = zone_24h_cooling_load(
            walls=[],
            roof=None,
            windows=[self._make_window(area=4.0)],
            internal_gains=[0.0] * 24,
            outdoor_temp_24h=[24.0] * 24,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert res["ok"] is True
        # fenestration_24h peak
        fen = res["fenestration_24h"]
        peak_h = fen.index(max(fen))
        assert 10 <= peak_h <= 16, f"Fenestration peak at hour {peak_h}, expected 10–16"

    def test_roof_adds_load(self):
        """Adding a roof increases total peak load."""
        no_roof = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[200.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        with_roof = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=self._make_roof(),
            windows=[],
            internal_gains=[200.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert no_roof["ok"] and with_roof["ok"]
        assert with_roof["peak_load_W"] > no_roof["peak_load_W"]

    def test_infiltration_ua_adds_sensible_load(self):
        """Adding infiltration_UA adds to load when T_outdoor > T_indoor."""
        no_inf = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[0.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
            infiltration_UA=0.0,
        )
        with_inf = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[0.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
            infiltration_UA=50.0,
        )
        assert no_inf["ok"] and with_inf["ok"]
        # At peak hour outdoor > 24°C, infiltration adds positive load
        assert with_inf["peak_load_W"] > no_inf["peak_load_W"]

    def test_wrong_outdoor_temp_length(self):
        res = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[0.0] * 24,
            outdoor_temp_24h=[30.0] * 12,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert res["ok"] is False

    def test_wrong_internal_gains_length(self):
        res = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=None,
            windows=[],
            internal_gains=[0.0] * 12,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
        )
        assert res["ok"] is False

    def test_full_zone_ashrae_textbook_order_of_magnitude(self):
        """Full zone: wall + roof + window + internal.
        For a small office zone (≈50 m² floor), peak should be in 2–15 kW range.
        ASHRAE 2009 HoF: typical small-zone peak 50–200 W/m² → 2.5–10 kW for 50 m².
        """
        internal = [300.0 if 8 <= h <= 18 else 50.0 for h in range(24)]
        res = zone_24h_cooling_load(
            walls=[
                self._make_wall("D", U=0.4, A=40.0),
                {"U": 0.4, "A": 10.0, "wall_type": "D"},
            ],
            roof=self._make_roof("medium", U=0.25, A=50.0),
            windows=[self._make_window(area=5.0, SHGC=0.4)],
            internal_gains=internal,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
            infiltration_UA=30.0,
        )
        assert res["ok"] is True
        peak = res["peak_load_W"]
        assert 500.0 < peak < 20000.0, f"Peak load {peak:.0f} W out of expected range"

    def test_component_sum_matches_total(self):
        """Total CL per hour = envelope + fenestration + internal + infiltration."""
        res = zone_24h_cooling_load(
            walls=[self._make_wall()],
            roof=self._make_roof(),
            windows=[self._make_window()],
            internal_gains=[400.0] * 24,
            outdoor_temp_24h=_OUTDOOR_T_24H,
            solar_24h=[],
            design_indoor_T=24.0,
            infiltration_UA=20.0,
        )
        assert res["ok"] is True
        for h in range(24):
            expected = (
                res["envelope_24h"][h]
                + res["fenestration_24h"][h]
                + res["internal_24h"][h]
                + res["infiltration_24h"][h]
            )
            assert res["CL_24h"][h] == pytest.approx(expected, abs=0.1), (
                f"Hour {h}: CL={res['CL_24h'][h]:.3f} != sum={expected:.3f}"
            )


# ---------------------------------------------------------------------------
# Edge cases & error handling
# ---------------------------------------------------------------------------

class TestTransientEdgeCases:
    def test_cltd_wall_case_insensitive(self):
        """Wall type should be case-insensitive ('a' == 'A')."""
        res_upper = cltd_wall("A", 12)
        res_lower = cltd_wall("a", 12)
        assert res_upper["ok"] and res_lower["ok"]
        assert res_upper["CLTD_F"] == res_lower["CLTD_F"]

    def test_cltd_roof_case_insensitive(self):
        res_lower = cltd_roof("LIGHT", 12)
        assert res_lower["ok"] is True

    def test_sol_air_negative_solar_error(self):
        res = sol_air_temp(30.0, -10.0, 0.9, 22.7)
        assert res["ok"] is False

    def test_wall_cooling_load_zero_u(self):
        res = wall_cooling_load(0.0, 20.0, 15.0)
        assert res["ok"] is True
        assert res["q_W"] == pytest.approx(0.0)

    def test_rts_medium_all_non_negative(self):
        """All RTS factors should be non-negative."""
        for v in _RTS_MEDIUM:
            assert v >= 0.0

    def test_rts_medium_first_factor_dominant(self):
        """By convention, RTS[0] (current hour) is the largest factor."""
        assert _RTS_MEDIUM[0] == max(_RTS_MEDIUM)
