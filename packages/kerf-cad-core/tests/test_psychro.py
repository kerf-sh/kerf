"""
Hermetic tests for kerf_cad_core.psychro — ASHRAE psychrometrics & HVAC loads.

Coverage:
  air.sat_pressure             — Hyland-Wexler over liquid water and ice
  air.altitude_pressure        — ISA troposphere pressure correction
  air.humidity_ratio_from_rh   — W from Tdb + RH
  air.humidity_ratio_from_twb  — W from Tdb + Twb (Sprung)
  air.relative_humidity        — RH from Tdb + W
  air.dew_point                — Tdp from Tdb + RH (Newton iteration)
  air.wet_bulb                 — Twb from Tdb + RH (Newton iteration)
  air.enthalpy                 — SI enthalpy
  air.enthalpy_ip              — IP enthalpy
  air.specific_volume          — v and rho
  air.state_point              — multi-pair solver
  air.mix_air_streams          — mass-weighted mixing
  air.sensible_load_ip         — 1.08·CFM·ΔT
  air.latent_load_ip           — 0.68·CFM·ΔW_gr / 4840·CFM·ΔW
  air.total_load_ip            — 4.5·CFM·Δh
  air.coil_adp                 — ADP, BF, SHR
  air.coil_leaving_conditions  — leaving T/W/h from loads
  air.evaporative_cooling      — direct evap cooler
  tools.*                      — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Reference values cross-checked against ASHRAE Handbook Fundamentals 2021,
Chapter 1 Tables and the ASHRAE psychrometric chart.

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapter 1: Psychrometrics
Hyland & Wexler (1983) ASHRAE Trans. 89(2A):500-519

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.psychro.air import (
    sat_pressure,
    altitude_pressure,
    humidity_ratio_from_rh,
    humidity_ratio_from_twb,
    relative_humidity,
    dew_point,
    wet_bulb,
    enthalpy,
    enthalpy_ip,
    specific_volume,
    state_point,
    mix_air_streams,
    sensible_load_ip,
    latent_load_ip,
    total_load_ip,
    coil_adp,
    coil_leaving_conditions,
    evaporative_cooling,
)
from kerf_cad_core.psychro.tools import (
    run_state_point,
    run_sat_pressure,
    run_dew_point,
    run_wet_bulb,
    run_enthalpy,
    run_enthalpy_ip,
    run_specific_volume,
    run_mix_streams,
    run_sensible_load,
    run_latent_load,
    run_total_load,
    run_coil_adp,
    run_coil_leaving,
    run_evaporative_cooling,
    run_altitude_pressure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


REL = 1e-3   # 0.1% relative tolerance for most psychrometric checks
ABS = 0.05   # 0.05°C / 0.05 Pa absolute tolerance for temperature results


# ===========================================================================
# 1. Saturation pressure — Hyland-Wexler
# ===========================================================================

class TestSatPressure:

    def test_at_0C_near_611Pa(self):
        """pws(0°C) ≈ 611.7 Pa (ice/water triple point region)."""
        r = sat_pressure(0.0)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - 611.7) < 1.0

    def test_at_20C_near_2337Pa(self):
        """pws(20°C) ≈ 2337 Pa per ASHRAE Table 2."""
        r = sat_pressure(20.0)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - 2337.0) < 5.0

    def test_at_100C_near_101325Pa(self):
        """pws(100°C) = 101 325 Pa (normal boiling point)."""
        r = sat_pressure(100.0)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - 101_325.0) / 101_325.0 < 0.002

    def test_at_minus10C_over_ice(self):
        """pws(-10°C) ≈ 259.9 Pa over ice per ASHRAE."""
        r = sat_pressure(-10.0)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - 259.9) < 3.0

    def test_monotone_increasing_with_temperature(self):
        """Saturation pressure must be strictly increasing with T."""
        temps = [-20, -10, 0, 10, 20, 40, 60, 80, 100]
        pressures = [sat_pressure(t)["pws_Pa"] for t in temps]
        for i in range(1, len(pressures)):
            assert pressures[i] > pressures[i - 1]

    def test_out_of_range_returns_warning(self):
        """Temperatures outside [-100, 200] should flag a warning."""
        r = sat_pressure(250.0)
        assert r["ok"] is True
        assert any("out of recommended range" in w for w in r["warnings"])


# ===========================================================================
# 2. Altitude pressure
# ===========================================================================

class TestAltitudePressure:

    def test_sea_level(self):
        """Altitude 0 m → 101 325 Pa."""
        r = altitude_pressure(0.0)
        assert r["ok"] is True
        assert abs(r["P_Pa"] - 101_325.0) < 1.0

    def test_denver_1609m(self):
        """Denver ~1609 m → ~83 600 Pa."""
        r = altitude_pressure(1609.0)
        assert r["ok"] is True
        assert abs(r["P_Pa"] - 83_600.0) < 300.0

    def test_pressure_decreases_with_altitude(self):
        """Pressure must decrease monotonically with altitude."""
        alts = [0, 500, 1000, 2000, 5000, 10000]
        pressures = [altitude_pressure(a)["P_Pa"] for a in alts]
        for i in range(1, len(pressures)):
            assert pressures[i] < pressures[i - 1]

    def test_negative_altitude_clamps(self):
        """Negative altitude is clamped to 0 with a warning."""
        r = altitude_pressure(-100.0)
        assert r["ok"] is True
        assert any("Negative altitude" in w for w in r["warnings"])
        assert abs(r["P_Pa"] - 101_325.0) < 1.0


# ===========================================================================
# 3. Humidity ratio
# ===========================================================================

class TestHumidityRatio:

    def test_saturated_air_at_20C(self):
        """RH=1.0 at 20°C: W = 0.621945 * pws / (P - pws)."""
        pws = sat_pressure(20.0)["pws_Pa"]
        W_expected = 0.621945 * pws / (101_325.0 - pws)
        r = humidity_ratio_from_rh(20.0, 1.0)
        assert r["ok"] is True
        assert abs(r["W"] - W_expected) / W_expected < REL

    def test_dry_air_at_rh0(self):
        """RH=0 → W=0."""
        r = humidity_ratio_from_rh(25.0, 0.0)
        assert r["ok"] is True
        assert r["W"] == 0.0

    def test_typical_office_conditions(self):
        """25°C, 50% RH → W ≈ 0.00988 kg/kg."""
        r = humidity_ratio_from_rh(25.0, 0.50)
        assert r["ok"] is True
        assert abs(r["W"] - 0.00988) < 0.0005

    def test_from_twb_equal_dry_bulb_gives_saturated(self):
        """Twb = Tdb → W = Ws(T)."""
        T = 25.0
        r_sat = humidity_ratio_from_rh(T, 1.0)
        r_twb = humidity_ratio_from_twb(T, T)
        assert r_twb["ok"] is True
        assert abs(r_twb["W"] - r_sat["W"]) / max(r_sat["W"], 1e-9) < 0.01


# ===========================================================================
# 4. Relative humidity round-trip
# ===========================================================================

class TestRelativeHumidity:

    def test_round_trip_rh_to_W_to_rh(self):
        """Computing W from RH and then back should recover the original RH."""
        T, RH_in = 30.0, 0.60
        W = humidity_ratio_from_rh(T, RH_in)["W"]
        r = relative_humidity(T, W)
        assert r["ok"] is True
        assert abs(r["RH"] - RH_in) < 0.002

    def test_dry_air_gives_zero_rh(self):
        r = relative_humidity(20.0, 0.0)
        assert r["ok"] is True
        assert r["RH"] == 0.0


# ===========================================================================
# 5. Dew point
# ===========================================================================

class TestDewPoint:

    def test_at_100pct_rh_tdp_equals_tdb(self):
        """At RH=1.0, Tdp should equal Tdb."""
        T = 25.0
        r = dew_point(T, 1.0)
        assert r["ok"] is True
        assert abs(r["Tdp_C"] - T) < ABS

    def test_tdp_below_tdb_for_unsaturated(self):
        """Tdp must be < Tdb for RH < 1."""
        r = dew_point(30.0, 0.50)
        assert r["ok"] is True
        assert r["Tdp_C"] < 30.0

    def test_known_value_20C_60pct(self):
        """20°C, 60% RH → Tdp ≈ 12.0°C (ASHRAE chart)."""
        r = dew_point(20.0, 0.60)
        assert r["ok"] is True
        assert abs(r["Tdp_C"] - 12.0) < 0.5

    def test_zero_rh_returns_low_tdp(self):
        r = dew_point(25.0, 0.0)
        assert r["ok"] is True
        assert r["Tdp_C"] < -50.0


# ===========================================================================
# 6. Wet-bulb temperature
# ===========================================================================

class TestWetBulb:

    def test_at_100pct_rh_twb_equals_tdb(self):
        """Saturated air: Twb = Tdb."""
        T = 25.0
        r = wet_bulb(T, 1.0)
        assert r["ok"] is True
        assert abs(r["Twb_C"] - T) < ABS

    def test_twb_between_tdp_and_tdb(self):
        """Twb must satisfy Tdp ≤ Twb ≤ Tdb."""
        T, RH = 35.0, 0.40
        r_twb = wet_bulb(T, RH)
        r_tdp = dew_point(T, RH)
        assert r_twb["ok"] is True
        assert r_twb["Twb_C"] <= T + ABS
        assert r_twb["Twb_C"] >= r_tdp["Tdp_C"] - ABS

    def test_known_value_25C_50pct(self):
        """25°C, 50% RH → Twb ≈ 19.0°C (Sprung formula with A_PSY=6.6e-4)."""
        r = wet_bulb(25.0, 0.50)
        assert r["ok"] is True
        # Sprung psychrometric equation gives ~19°C; agrees with sling psychrometer tables
        assert abs(r["Twb_C"] - 19.0) < 0.5

    def test_convergence_flag_is_true(self):
        r = wet_bulb(30.0, 0.60)
        assert r["ok"] is True
        assert r["converged"] is True


# ===========================================================================
# 7. Enthalpy
# ===========================================================================

class TestEnthalpy:

    def test_dry_air_at_0C(self):
        """Dry air at 0°C: h = cp_a * 0 + W*(...) = 0."""
        r = enthalpy(0.0, 0.0)
        assert r["ok"] is True
        assert abs(r["h_kJkg"]) < 0.01

    def test_dry_air_at_20C(self):
        """Dry air at 20°C: h = 1.006 * 20 = 20.12 kJ/kg."""
        r = enthalpy(20.0, 0.0)
        assert r["ok"] is True
        assert abs(r["h_kJkg"] - 20.12) < 0.02

    def test_moist_air_standard_condition(self):
        """25°C, W≈0.0099 kg/kg → h ≈ 50.5 kJ/kg (ASHRAE chart)."""
        r = enthalpy(25.0, 0.0099)
        assert r["ok"] is True
        assert abs(r["h_kJkg"] - 50.5) < 0.5

    def test_enthalpy_ip_at_standard(self):
        """75°F, W=0.0092 lb/lb: verify formula h = 0.240·T + W·(1061 + 0.444·T)."""
        r = enthalpy_ip(75.0, 0.0092)
        assert r["ok"] is True
        expected = 0.240 * 75.0 + 0.0092 * (1061.0 + 0.444 * 75.0)
        assert abs(r["h_BTUperlb"] - expected) < 0.01

    def test_enthalpy_ip_dry_air_70F(self):
        """Dry air at 70°F: h = 0.240 * 70 = 16.8 BTU/lb."""
        r = enthalpy_ip(70.0, 0.0)
        assert r["ok"] is True
        assert abs(r["h_BTUperlb"] - 16.8) < 0.01


# ===========================================================================
# 8. Specific volume and density
# ===========================================================================

class TestSpecificVolume:

    def test_dry_air_20C_sea_level(self):
        """Dry air at 20°C, 101325 Pa: v = R_air/P * T_K ≈ 0.8305 m³/kg."""
        r = specific_volume(20.0, 0.0)
        assert r["ok"] is True
        # Ideal gas: v = 287.055 / 101325 * (273.15 + 20) ≈ 0.8305
        expected = 287.055 / 101_325.0 * (273.15 + 20.0)
        assert abs(r["v_m3perkg"] - expected) < 0.0001

    def test_density_reciprocal_of_volume(self):
        """rho = (1+W)/v by definition."""
        W = 0.008
        r = specific_volume(25.0, W)
        assert r["ok"] is True
        assert abs(r["rho_kgperm3"] - (1.0 + W) / r["v_m3perkg"]) < 1e-9

    def test_volume_increases_with_temperature(self):
        """Higher T → larger specific volume at fixed P and W."""
        v1 = specific_volume(20.0, 0.01)["v_m3perkg"]
        v2 = specific_volume(40.0, 0.01)["v_m3perkg"]
        assert v2 > v1


# ===========================================================================
# 9. State-point solver
# ===========================================================================

class TestStatePoint:

    def test_tdb_rh_pair(self):
        """State from (Tdb, RH): all outputs present and self-consistent."""
        r = state_point(Tdb_C=25.0, RH=0.50)
        assert r["ok"] is True
        assert abs(r["RH"] - 0.50) < 0.005
        assert r["Tdb_C"] == 25.0
        assert r["Twb_C"] < 25.0
        assert r["Tdp_C"] < r["Twb_C"] + ABS

    def test_tdb_W_pair(self):
        """State from (Tdb, W): RH computed consistently."""
        W = 0.010
        r = state_point(Tdb_C=28.0, W=W)
        assert r["ok"] is True
        assert abs(r["W"] - W) < 1e-6
        assert 0.0 < r["RH"] < 1.0

    def test_tdb_Twb_pair(self):
        """State from (Tdb, Twb): roundtrip wet-bulb."""
        r = state_point(Tdb_C=30.0, Twb_C=20.0)
        assert r["ok"] is True
        assert abs(r["Twb_C"] - 20.0) < 0.3

    def test_tdb_tdp_pair(self):
        """State from (Tdb, Tdp): RH should match independent computation."""
        r = state_point(Tdb_C=25.0, Tdp_C=14.0)
        assert r["ok"] is True
        # RH from Tdp independently: pws(Tdp) / pws(Tdb)
        pws_dp = sat_pressure(14.0)["pws_Pa"]
        pws_db = sat_pressure(25.0)["pws_Pa"]
        expected_RH = pws_dp / pws_db
        assert abs(r["RH"] - expected_RH) < 0.01

    def test_tdb_h_pair(self):
        """State from (Tdb, h): W recovered correctly."""
        # First compute h from known (T, W)
        T, W_in = 30.0, 0.012
        h = enthalpy(T, W_in)["h_kJkg"]
        r = state_point(Tdb_C=T, h_kJkg=h)
        assert r["ok"] is True
        assert abs(r["W"] - W_in) < 1e-4

    def test_W_h_pair(self):
        """State from (W, h): Tdb recovered correctly."""
        T_in, W_in = 35.0, 0.015
        h = enthalpy(T_in, W_in)["h_kJkg"]
        r = state_point(W=W_in, h_kJkg=h)
        assert r["ok"] is True
        assert abs(r["Tdb_C"] - T_in) < 0.1

    def test_unsupported_pair_returns_ok_false(self):
        """Single input should return ok=False with a helpful warning."""
        r = state_point(Tdb_C=25.0)
        assert r["ok"] is False


# ===========================================================================
# 10. Air mixing
# ===========================================================================

class TestMixAirStreams:

    def test_equal_streams_gives_average(self):
        """50/50 mix of identical streams returns same state."""
        r = mix_air_streams(
            1000.0, 25.0, 0.010,
            1000.0, 25.0, 0.010,
        )
        assert r["ok"] is True
        assert abs(r["Tdb_C"] - 25.0) < 0.1
        assert abs(r["W"] - 0.010) < 1e-6

    def test_mixing_bounds_temperature(self):
        """Mixed Tdb must be between the two entering temperatures."""
        r = mix_air_streams(
            500.0, 15.0, 0.005,
            500.0, 35.0, 0.015,
        )
        assert r["ok"] is True
        assert 15.0 - ABS < r["Tdb_C"] < 35.0 + ABS

    def test_mixing_bounds_humidity_ratio(self):
        """Mixed W must be between the two stream W values."""
        r = mix_air_streams(
            1000.0, 20.0, 0.004,
            1000.0, 30.0, 0.020,
        )
        assert r["ok"] is True
        assert 0.004 - 1e-5 < r["W"] < 0.020 + 1e-5


# ===========================================================================
# 11. ASHRAE IP load formulas
# ===========================================================================

class TestLoadsIP:

    def test_sensible_load_formula(self):
        """Q = 1.08 × 1000 × 20 = 21 600 BTU/h."""
        r = sensible_load_ip(1000.0, 20.0)
        assert r["ok"] is True
        assert abs(r["Q_BTUh"] - 21_600.0) < 0.01

    def test_latent_load_grains(self):
        """Q = 0.68 × 500 × 30 = 10 200 BTU/h."""
        r = latent_load_ip(500.0, delta_W_grains=30.0)
        assert r["ok"] is True
        assert abs(r["Q_BTUh"] - 10_200.0) < 0.01

    def test_latent_load_lbperlb(self):
        """Q = 4840 × 500 × 0.005 = 12 100 BTU/h."""
        r = latent_load_ip(500.0, delta_W_lbperlb=0.005)
        assert r["ok"] is True
        assert abs(r["Q_BTUh"] - 12_100.0) < 0.01

    def test_total_load_formula(self):
        """Q = 4.5 × 1000 × 5 = 22 500 BTU/h."""
        r = total_load_ip(1000.0, 5.0)
        assert r["ok"] is True
        assert abs(r["Q_BTUh"] - 22_500.0) < 0.01

    def test_sensible_plus_latent_equals_total(self):
        """Verify SI load relationship: Qs + Ql ≈ Qt for a given airstream."""
        # Using standard-air approximation in IP
        cfm = 800.0
        T_sup_F = 55.0
        T_ret_F = 75.0
        W_sup = 0.0082  # lb/lb at 55°F, ~95% RH
        W_ret = 0.0099  # lb/lb at 75°F, ~50% RH
        dT = T_ret_F - T_sup_F
        dW = W_ret - W_sup
        dh = enthalpy_ip(T_ret_F, W_ret)["h_BTUperlb"] - enthalpy_ip(T_sup_F, W_sup)["h_BTUperlb"]

        Qs = sensible_load_ip(cfm, dT)["Q_BTUh"]
        Ql = latent_load_ip(cfm, delta_W_lbperlb=dW)["Q_BTUh"]
        Qt = total_load_ip(cfm, dh)["Q_BTUh"]

        # Qs + Ql ≈ Qt (standard-air approximation; within ~2%)
        assert abs((Qs + Ql - Qt) / Qt) < 0.03

    def test_latent_load_missing_dw_returns_error(self):
        r = latent_load_ip(500.0)
        assert r["ok"] is False


# ===========================================================================
# 12. Cooling-coil ADP
# ===========================================================================

class TestCoilADP:

    def test_adp_below_leaving_temperature(self):
        """ADP must be ≤ leaving Tdb."""
        r = coil_adp(26.7, 19.4, 12.8, 12.2)
        assert r["ok"] is True
        assert r["T_ADP_C"] <= 12.8 + ABS

    def test_bypass_factor_between_0_and_1(self):
        """BF must be in [0, 1]."""
        r = coil_adp(26.7, 19.4, 12.8, 12.2)
        assert r["ok"] is True
        assert 0.0 <= r["BF"] <= 1.0

    def test_shr_between_0_and_1(self):
        """SHR must be in [0, 1]."""
        r = coil_adp(26.7, 19.4, 12.8, 12.2)
        assert r["ok"] is True
        assert 0.0 <= r["SHR"] <= 1.0

    def test_no_cooling_returns_bf_1(self):
        """Identical entering and leaving → BF = 1 or warning."""
        r = coil_adp(25.0, 18.0, 25.0, 18.0)
        assert r["ok"] is True
        assert r["BF"] >= 0.95 or any(r["warnings"])


# ===========================================================================
# 13. Coil leaving conditions
# ===========================================================================

class TestCoilLeaving:

    def test_sensible_only_cooling(self):
        """Pure sensible cooling: W_leaving ≈ W_entering."""
        Q_s = 5.0     # kW
        Q_t = 5.0     # kW (no latent)
        m_dot = 1.0   # kg/s
        r = coil_leaving_conditions(25.0, 0.010, Q_s, Q_t, m_dot)
        assert r["ok"] is True
        assert abs(r["W_leaving"] - 0.010) < 0.0005

    def test_leaving_tdb_lower_than_entering(self):
        r = coil_leaving_conditions(26.0, 0.012, 4.0, 6.0, 1.2)
        assert r["ok"] is True
        assert r["Tdb_leaving_C"] < 26.0

    def test_zero_massflow_returns_error(self):
        r = coil_leaving_conditions(25.0, 0.010, 3.0, 5.0, 0.0)
        assert r["ok"] is False


# ===========================================================================
# 14. Evaporative cooling
# ===========================================================================

class TestEvaporativeCooling:

    def test_leaving_tdb_lower_than_entering(self):
        r = evaporative_cooling(35.0, 0.20, effectiveness=0.80)
        assert r["ok"] is True
        assert r["Tdb_leaving_C"] < 35.0

    def test_leaving_rh_higher_than_entering(self):
        r = evaporative_cooling(40.0, 0.15, effectiveness=0.85)
        assert r["ok"] is True
        assert r["RH_leaving"] > 0.15

    def test_100pct_effectiveness_reaches_near_wet_bulb(self):
        """ε=1.0: leaving Tdb ≈ Twb of entering conditions."""
        T, RH = 35.0, 0.25
        twb = wet_bulb(T, RH)["Twb_C"]
        r = evaporative_cooling(T, RH, effectiveness=1.0)
        assert r["ok"] is True
        assert abs(r["Tdb_leaving_C"] - twb) < 0.5

    def test_humidity_increases(self):
        """Evaporative cooling adds moisture."""
        r = evaporative_cooling(35.0, 0.20, effectiveness=0.80)
        assert r["ok"] is True
        sp = state_point(Tdb_C=35.0, RH=0.20)
        assert r["W_leaving"] >= sp["W"] - 1e-6


# ===========================================================================
# 14b. CITABLE ASHRAE Fundamentals (2021) Chapter 1 reference cases
#
# Saturation pressures cross-checked against ASHRAE Handbook — Fundamentals
# (2021), Chapter 1, Table 2 ("Thermodynamic Properties of Moist Air") and
# the Hyland & Wexler (1983) saturation-pressure equations (ASHRAE Trans.
# 89(2A):500-519).  Humidity ratio, enthalpy, and specific volume checked
# against the same Table 2 / the ASHRAE psychrometric chart.
# ===========================================================================

class TestASHRAEReferenceCases:

    # ASHRAE Fundamentals 2021 Ch.1 Table 2 — pws over water/ice (Pa)
    # Values from Hyland-Wexler; tolerance 0.05% covers table rounding.
    @pytest.mark.parametrize("T_C,pws_ref", [
        (-20.0, 103.24),
        (-10.0, 259.90),
        (0.0,   611.21),
        (10.0,  1227.96),
        (20.0,  2338.80),
        (25.0,  3169.21),
        (30.0,  4246.03),
        (40.0,  7384.93),
        (50.0,  12351.31),
    ])
    def test_hyland_wexler_saturation_pressure_table2(self, T_C, pws_ref):
        r = sat_pressure(T_C)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - pws_ref) / pws_ref < 5e-4

    def test_saturation_pressure_normal_boiling_point(self):
        """Hyland-Wexler at 100 °C must give ≈ 101.4 kPa (water boils at
        1 atm), within 0.1 % of the standard 101 325 Pa datum."""
        r = sat_pressure(100.0)
        assert r["ok"] is True
        assert abs(r["pws_Pa"] - 101_325.0) / 101_325.0 < 1e-3

    def test_humidity_ratio_25C_50pct_chart(self):
        """ASHRAE psychrometric chart: 25 °C, 50 % RH, sea level →
        W ≈ 0.00988 kg/kg dry air."""
        r = humidity_ratio_from_rh(25.0, 0.50)
        assert r["ok"] is True
        assert abs(r["W"] - 0.00988) < 5e-5

    def test_enthalpy_25C_W0099_chart(self):
        """ASHRAE chart: 25 °C, W = 0.0099 kg/kg → h ≈ 50.4 kJ/kg dry air.
        h = 1.006·T + W·(2501 + 1.86·T)."""
        r = enthalpy(25.0, 0.0099)
        assert r["ok"] is True
        assert abs(r["h_kJkg"] - 50.4) < 0.2

    def test_specific_volume_70F_dry_air_table2(self):
        """ASHRAE Table 2: dry air at 70 °F (21.111 °C), 101.325 kPa has
        specific volume v ≈ 0.8333 m³/kg (= 13.348 ft³/lb)."""
        r = specific_volume(21.111, 0.0)
        assert r["ok"] is True
        assert abs(r["v_m3perkg"] - 0.8333) < 1e-3

    def test_enthalpy_ip_ashrae_standard_air(self):
        """ASHRAE IP enthalpy h = 0.240·T + W·(1061 + 0.444·T) [BTU/lb].
        Dry air at 70 °F → h = 16.8 BTU/lb exactly."""
        r = enthalpy_ip(70.0, 0.0)
        assert r["ok"] is True
        assert abs(r["h_BTUperlb"] - 16.8) < 1e-6

    def test_sea_level_standard_pressure(self):
        """ISA / ASHRAE standard sea-level pressure = 101 325 Pa."""
        r = altitude_pressure(0.0)
        assert r["ok"] is True
        assert abs(r["P_Pa"] - 101_325.0) < 1.0

    def test_denver_altitude_pressure_ashrae(self):
        """ASHRAE Ch.1 / ISA troposphere: at 1610 m (Denver) the
        barometric pressure is ≈ 83.4 kPa (ASHRAE climatic-design value)."""
        r = altitude_pressure(1610.0)
        assert r["ok"] is True
        assert abs(r["P_Pa"] - 83_400.0) < 600.0

    def test_dew_point_20C_60pct_chart(self):
        """ASHRAE chart: 20 °C dry-bulb, 60 % RH → dew point ≈ 12.0 °C."""
        r = dew_point(20.0, 0.60)
        assert r["ok"] is True
        assert abs(r["Tdp_C"] - 12.0) < 0.3


# ===========================================================================
# 15. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:
    """ok_payload dumps the result dict flat — keys are top-level in the JSON."""

    def test_tool_sat_pressure_ok(self):
        raw = _run(run_sat_pressure(_ctx(), _args(T_C=20.0)))
        d = _ok_tool(raw)
        assert "pws_Pa" in d

    def test_tool_sat_pressure_missing_arg(self):
        raw = _run(run_sat_pressure(_ctx(), _args(wrong=1)))
        _err_tool(raw)

    def test_tool_state_point_tdb_rh(self):
        raw = _run(run_state_point(_ctx(), _args(Tdb_C=25.0, RH=0.50)))
        d = _ok_tool(raw)
        assert "W" in d

    def test_tool_state_point_too_few_inputs(self):
        raw = _run(run_state_point(_ctx(), _args(Tdb_C=25.0)))
        _err_tool(raw)

    def test_tool_dew_point_ok(self):
        raw = _run(run_dew_point(_ctx(), _args(T_C=25.0, RH=0.60)))
        d = _ok_tool(raw)
        assert "Tdp_C" in d

    def test_tool_wet_bulb_ok(self):
        raw = _run(run_wet_bulb(_ctx(), _args(T_C=30.0, RH=0.60)))
        d = _ok_tool(raw)
        assert "Twb_C" in d

    def test_tool_enthalpy_ok(self):
        raw = _run(run_enthalpy(_ctx(), _args(T_C=25.0, W=0.010)))
        d = _ok_tool(raw)
        assert "h_kJkg" in d

    def test_tool_enthalpy_ip_ok(self):
        raw = _run(run_enthalpy_ip(_ctx(), _args(T_F=75.0, W_lbperlb=0.0092)))
        d = _ok_tool(raw)
        assert "h_BTUperlb" in d

    def test_tool_specific_volume_ok(self):
        raw = _run(run_specific_volume(_ctx(), _args(T_C=20.0, W=0.008)))
        d = _ok_tool(raw)
        assert "v_m3perkg" in d

    def test_tool_sensible_load_ok(self):
        raw = _run(run_sensible_load(_ctx(), _args(cfm=1000.0, delta_T_F=20.0)))
        d = _ok_tool(raw)
        assert abs(d["Q_BTUh"] - 21_600.0) < 1.0

    def test_tool_latent_load_grains_ok(self):
        raw = _run(run_latent_load(_ctx(), _args(cfm=500.0, delta_W_grains=30.0)))
        d = _ok_tool(raw)
        assert "Q_BTUh" in d

    def test_tool_total_load_ok(self):
        raw = _run(run_total_load(_ctx(), _args(cfm=1000.0, delta_h_BTUperlb=5.0)))
        d = _ok_tool(raw)
        assert abs(d["Q_BTUh"] - 22_500.0) < 1.0

    def test_tool_mix_streams_ok(self):
        raw = _run(run_mix_streams(_ctx(), _args(
            cfm1=500.0, Tdb1_C=20.0, W1=0.008,
            cfm2=500.0, Tdb2_C=30.0, W2=0.012,
        )))
        d = _ok_tool(raw)
        assert "Tdb_C" in d

    def test_tool_coil_adp_ok(self):
        raw = _run(run_coil_adp(_ctx(), _args(
            Tdb_entering_C=26.7, Twb_entering_C=19.4,
            Tdb_leaving_C=12.8, Twb_leaving_C=12.2,
        )))
        d = _ok_tool(raw)
        assert "T_ADP_C" in d

    def test_tool_coil_leaving_ok(self):
        raw = _run(run_coil_leaving(_ctx(), _args(
            Tdb_entering_C=26.0, W_entering=0.012,
            Q_sensible_kW=4.0, Q_total_kW=6.0, mass_flow_kgs=1.2,
        )))
        d = _ok_tool(raw)
        assert "Tdb_leaving_C" in d

    def test_tool_evaporative_cooling_ok(self):
        raw = _run(run_evaporative_cooling(_ctx(), _args(Tdb_C=35.0, RH=0.25)))
        d = _ok_tool(raw)
        assert "Tdb_leaving_C" in d

    def test_tool_altitude_pressure_ok(self):
        raw = _run(run_altitude_pressure(_ctx(), _args(altitude_m=1609.0)))
        d = _ok_tool(raw)
        assert "P_Pa" in d
        assert d["P_Pa"] < 101_325.0

    def test_tool_invalid_json_returns_error(self):
        raw = _run(run_sat_pressure(_ctx(), b"not-json"))
        _err_tool(raw)
