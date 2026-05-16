"""
Hermetic tests for kerf_cad_core.hydroturbine — hydropower plant engineering.

Coverage:
  plant.plant_power              — P = ρ·g·Q·H·η
  plant.turbine_type_selection   — Pelton/Turgo/Crossflow/Francis/Kaplan/Bulb
  plant.runner_speed             — n ≈ K·√H
  plant.synchronous_speed_poles  — n_s = 120·f / p
  plant.penstock_diameter        — D = √(4Q/πV)
  plant.penstock_friction_loss   — Darcy-Weisbach h_f
  plant.penstock_wall_thickness  — Barlow thin-wall
  plant.water_hammer_joukowsky   — ΔP = ρ·a·V
  plant.water_hammer_allievi     — Michaud / Joukowsky limit
  plant.surge_tank_area          — Thoma criterion
  plant.thoma_cavitation         — σ_plant vs σ_crit
  plant.runaway_speed            — empirical factor
  plant.flow_duration_energy     — annual energy / capacity factor
  plant.pelton_jet_sizing        — jet velocity, diameter, bucket
  plant.micro_hydro_quick        — end-to-end sizing
  tools.*                        — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against hand-calcs.

References
----------
Warnick, C.C., "Hydropower Engineering", Prentice-Hall (1984)
IEC 60193:1999
Gordon, J.L. (1999), Can. J. Civ. Eng. 26

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.hydroturbine.plant import (
    plant_power,
    turbine_type_selection,
    runner_speed,
    synchronous_speed_poles,
    penstock_diameter,
    penstock_friction_loss,
    penstock_wall_thickness,
    water_hammer_joukowsky,
    water_hammer_allievi,
    surge_tank_area,
    thoma_cavitation,
    runaway_speed,
    flow_duration_energy,
    pelton_jet_sizing,
    micro_hydro_quick,
)
from kerf_cad_core.hydroturbine.tools import (
    run_plant_power,
    run_turbine_type,
    run_runner_speed,
    run_sync_speed_poles,
    run_penstock_diameter,
    run_penstock_friction,
    run_penstock_wall,
    run_water_hammer_joukowsky,
    run_water_hammer_allievi,
    run_surge_tank,
    run_thoma_cavitation,
    run_runaway_speed,
    run_flow_duration_energy,
    run_pelton_jet,
    run_micro_quick,
)

_G = 9.81
_RHO = 1000.0
REL = 1e-6


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


# ===========================================================================
# 1. plant_power — P = ρ·g·Q·H·η
# ===========================================================================

class TestPlantPower:

    def test_hydraulic_power_formula(self):
        """P_hydraulic = ρ·g·Q·H (kW hand-calc)."""
        Q, H, rho = 5.0, 100.0, 1000.0
        res = plant_power(Q, H, eta=1.0, rho=rho)
        assert res["ok"] is True
        expected = rho * _G * Q * H
        assert abs(res["P_hydraulic_W"] - expected) / expected < REL

    def test_shaft_power_with_efficiency(self):
        """P_shaft = ρ·g·Q·H·η."""
        Q, H, eta = 10.0, 50.0, 0.88
        res = plant_power(Q, H, eta=eta)
        assert res["ok"] is True
        P_hyd = _RHO * _G * Q * H
        assert abs(res["P_shaft_W"] - P_hyd * eta) / (P_hyd * eta) < REL

    def test_kw_mw_conversions_consistent(self):
        """P_shaft_kW == P_shaft_W / 1000, P_shaft_MW == P_shaft_W / 1e6."""
        res = plant_power(Q=2.0, H_net=80.0)
        assert res["ok"] is True
        assert abs(res["P_shaft_kW"] - res["P_shaft_W"] / 1e3) < 1e-9
        assert abs(res["P_shaft_MW"] - res["P_shaft_W"] / 1e6) < 1e-12

    def test_zero_Q_returns_error(self):
        assert plant_power(0.0, 50.0)["ok"] is False

    def test_negative_H_net_returns_error(self):
        assert plant_power(5.0, -10.0)["ok"] is False

    def test_eta_greater_than_1_returns_error(self):
        assert plant_power(5.0, 50.0, eta=1.1)["ok"] is False

    def test_low_efficiency_warning(self):
        """η < 0.5 triggers a warning."""
        res = plant_power(5.0, 50.0, eta=0.40)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 2. turbine_type_selection
# ===========================================================================

class TestTurbineTypeSelection:

    def test_high_head_selects_pelton(self):
        """H > 300 m → Pelton."""
        res = turbine_type_selection(H_net=500.0, Q=1.0)
        assert res["ok"] is True
        assert res["turbine_type"] == "Pelton"

    def test_low_head_selects_kaplan_or_bulb(self):
        """H < 5 m → Kaplan or Bulb."""
        res = turbine_type_selection(H_net=3.0, Q=50.0)
        assert res["ok"] is True
        assert res["turbine_type"] in ("Kaplan", "Bulb", "Crossflow")

    def test_medium_head_selects_francis(self):
        """H = 100 m → Francis (or Francis in alternatives)."""
        res = turbine_type_selection(H_net=100.0, Q=5.0)
        assert res["ok"] is True
        assert res["turbine_type"] in ("Francis",) or "Francis" in res["alternatives"]

    def test_specific_speed_method_returns_ns(self):
        """With n_rpm given, Ns is computed."""
        res = turbine_type_selection(H_net=200.0, Q=2.0, n_rpm=375.0)
        assert res["ok"] is True
        assert res["Ns"] is not None
        assert res["Ns"] > 0

    def test_ns_pelton_range(self):
        """Ns in Pelton band → type Pelton."""
        # Pelton band: Ns ≈ 0.005–0.07
        # Ns = ω·√Q / H^(3/4); pick n=375 rpm (ω=39.3), Q=0.5, H=500
        # Ns = 39.3·0.707 / 500^0.75 = 27.8 / 105.7 ≈ 0.263 → too high for Pelton
        # Use smaller Q: Q=0.05, H=500
        # Ns = 39.3·0.2236 / 105.7 = 8.8/105.7 ≈ 0.083 → Turgo
        # Use n=100 rpm (ω=10.47), Q=0.05, H=500
        # Ns = 10.47·0.2236 / 105.7 = 2.34/105.7 ≈ 0.022 → Pelton
        n = 100.0
        Q = 0.05
        H = 500.0
        omega = n * 2.0 * math.pi / 60.0
        Ns = omega * math.sqrt(Q) / H ** 0.75
        assert Ns < 0.07  # confirm we're in Pelton band
        res = turbine_type_selection(H_net=H, Q=Q, n_rpm=n)
        assert res["ok"] is True
        assert res["turbine_type"] == "Pelton"

    def test_zero_head_returns_error(self):
        assert turbine_type_selection(0.0, 5.0)["ok"] is False

    def test_negative_flow_returns_error(self):
        assert turbine_type_selection(100.0, -1.0)["ok"] is False


# ===========================================================================
# 3. runner_speed
# ===========================================================================

class TestRunnerSpeed:

    def test_francis_runner_speed_formula(self):
        """n = K·√H with K=50 for Francis."""
        H = 100.0
        res = runner_speed(H, "Francis")
        assert res["ok"] is True
        expected = 50.0 * math.sqrt(H)
        assert abs(res["n_rpm_approx"] - expected) / expected < REL

    def test_pelton_runner_speed(self):
        """K=30 for Pelton."""
        H = 400.0
        res = runner_speed(H, "Pelton")
        assert res["ok"] is True
        assert abs(res["n_rpm_approx"] - 30.0 * math.sqrt(H)) < 1e-9

    def test_kaplan_runner_speed(self):
        """K=150 for Kaplan."""
        H = 25.0
        res = runner_speed(H, "Kaplan")
        assert res["ok"] is True
        assert abs(res["n_rpm_approx"] - 150.0 * math.sqrt(H)) < 1e-9

    def test_unknown_type_returns_error(self):
        res = runner_speed(100.0, "Banki")
        assert res["ok"] is False

    def test_negative_head_returns_error(self):
        assert runner_speed(-1.0)["ok"] is False


# ===========================================================================
# 4. synchronous_speed_poles
# ===========================================================================

class TestSynchronousSpeedPoles:

    def test_exact_sync_speed(self):
        """n_runner = 500 rpm exactly (f=50, p=12 → 500 rpm)."""
        n_sync = 120.0 * 50.0 / 12
        assert n_sync == 500.0
        res = synchronous_speed_poles(n_runner_rpm=500.0, f_hz=50.0)
        assert res["ok"] is True
        # One of the returned speeds should be 500 rpm
        assert (
            abs(res["n_sync_lower_rpm"] - 500.0) < 0.1
            or abs(res["n_sync_higher_rpm"] - 500.0) < 0.1
        )

    def test_poles_are_even(self):
        """Returned pole counts must be even integers."""
        res = synchronous_speed_poles(n_runner_rpm=375.0)
        assert res["ok"] is True
        assert res["poles_lower"] % 2 == 0
        assert res["poles_higher"] % 2 == 0

    def test_lower_speed_leq_runner(self):
        """n_sync_lower_rpm ≤ n_runner."""
        n = 300.0
        res = synchronous_speed_poles(n, f_hz=50.0)
        assert res["ok"] is True
        assert res["n_sync_lower_rpm"] <= n + 0.01  # small float tolerance

    def test_60hz_grid(self):
        """60 Hz grid: n_sync = 120*60/p."""
        res = synchronous_speed_poles(n_runner_rpm=720.0, f_hz=60.0)
        assert res["ok"] is True
        p = res["poles_lower"]
        n_sync = 120.0 * 60.0 / p
        assert abs(res["n_sync_lower_rpm"] - n_sync) < 0.01

    def test_negative_speed_returns_error(self):
        assert synchronous_speed_poles(-100.0)["ok"] is False


# ===========================================================================
# 5. penstock_diameter
# ===========================================================================

class TestPenstockDiameter:

    def test_diameter_formula(self):
        """D = √(4Q / (π·V))."""
        Q, V = 3.0, 3.5
        res = penstock_diameter(Q, V_economic=V)
        assert res["ok"] is True
        A = Q / V
        D_expected = math.sqrt(4.0 * A / math.pi)
        assert abs(res["D_m"] - D_expected) / D_expected < REL

    def test_area_consistent_with_diameter(self):
        """A = π·D²/4."""
        res = penstock_diameter(Q=2.0)
        assert res["ok"] is True
        assert abs(res["A_m2"] - math.pi * res["D_m"] ** 2 / 4.0) < 1e-10

    def test_zero_Q_returns_error(self):
        assert penstock_diameter(0.0)["ok"] is False

    def test_high_velocity_warning(self):
        """V > 6 m/s triggers a warning."""
        res = penstock_diameter(Q=1.0, V_economic=7.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 6. penstock_friction_loss
# ===========================================================================

class TestPenstockFrictionLoss:

    def test_darcy_weisbach_formula(self):
        """h_f = f·(L/D)·V²/(2g)."""
        Q, D, L, f = 2.0, 0.6, 500.0, 0.015
        A = math.pi * D ** 2 / 4.0
        V = Q / A
        h_f_expected = f * (L / D) * V ** 2 / (2.0 * _G)
        res = penstock_friction_loss(Q, D, L, f)
        assert res["ok"] is True
        assert abs(res["h_f_m"] - h_f_expected) / h_f_expected < REL

    def test_velocity_correct(self):
        """V = Q / A."""
        Q, D = 2.0, 0.5
        A = math.pi * D ** 2 / 4.0
        res = penstock_friction_loss(Q, D, 100.0)
        assert res["ok"] is True
        assert abs(res["V_m_s"] - Q / A) / (Q / A) < REL

    def test_negative_D_returns_error(self):
        assert penstock_friction_loss(1.0, -0.5, 100.0)["ok"] is False

    def test_zero_L_returns_error(self):
        assert penstock_friction_loss(1.0, 0.5, 0.0)["ok"] is False


# ===========================================================================
# 7. penstock_wall_thickness
# ===========================================================================

class TestPenstockWallThickness:

    def test_barlow_formula(self):
        """t_calc = P·D / (2·σ·e)."""
        D, P, sigma, e = 0.8, 2e6, 120e6, 0.85
        res = penstock_wall_thickness(D, P, sigma_allow_Pa=sigma, weld_efficiency=e)
        assert res["ok"] is True
        t_calc_expected = P * D / (2.0 * sigma * e) * 1000.0  # mm
        assert abs(res["t_calc_mm"] - t_calc_expected) / t_calc_expected < REL

    def test_corrosion_added_to_total(self):
        """t_total = t_calc + corrosion."""
        res = penstock_wall_thickness(0.5, 1e6, corrosion_mm=3.0)
        assert res["ok"] is True
        assert abs(res["t_total_mm"] - (res["t_calc_mm"] + 3.0)) < 1e-9

    def test_zero_pressure_returns_error(self):
        assert penstock_wall_thickness(0.5, 0.0)["ok"] is False

    def test_negative_D_returns_error(self):
        assert penstock_wall_thickness(-0.5, 1e6)["ok"] is False


# ===========================================================================
# 8. water_hammer_joukowsky
# ===========================================================================

class TestWaterHammerJoukowsky:

    def test_joukowsky_formula(self):
        """ΔP = ρ·a·V."""
        V, a, rho = 3.0, 1200.0, 1000.0
        res = water_hammer_joukowsky(V, a, rho)
        assert res["ok"] is True
        dP_expected = rho * a * V
        assert abs(res["dP_Pa"] - dP_expected) / dP_expected < REL

    def test_head_rise_consistent(self):
        """dH = dP / (ρ·g)."""
        res = water_hammer_joukowsky(V=4.0, a_wave=1200.0)
        assert res["ok"] is True
        assert abs(res["dH_m"] - res["dP_Pa"] / (_RHO * _G)) / res["dH_m"] < REL

    def test_bar_conversion(self):
        """dP_bar = dP_Pa / 1e5."""
        res = water_hammer_joukowsky(V=3.0, a_wave=1000.0)
        assert res["ok"] is True
        assert abs(res["dP_bar"] - res["dP_Pa"] / 1e5) < 1e-10

    def test_large_head_rise_warning(self):
        """dH > 500 m triggers overpressure warning."""
        # V=5 m/s, a=1200 m/s → dH = 1200*5/9.81 ≈ 611 m
        res = water_hammer_joukowsky(V=5.0, a_wave=1200.0)
        assert res["ok"] is True
        assert any("water-hammer" in w.lower() or "large" in w.lower() for w in res["warnings"])

    def test_negative_V_returns_error(self):
        assert water_hammer_joukowsky(-1.0, 1200.0)["ok"] is False

    def test_zero_wave_speed_returns_error(self):
        assert water_hammer_joukowsky(3.0, 0.0)["ok"] is False


# ===========================================================================
# 9. water_hammer_allievi
# ===========================================================================

class TestWaterHammerAllievi:

    def test_rapid_closure_uses_joukowsky(self):
        """T_close ≤ 2L/a → regime 'rapid', dH = a·V/g."""
        H, V, a, L, T = 200.0, 3.0, 1200.0, 500.0, 0.5  # T_crit=0.833, T=0.5<T_crit
        res = water_hammer_allievi(H, V, a, L, T)
        assert res["ok"] is True
        assert res["regime"] == "rapid"
        dH_expected = a * V / _G
        assert abs(res["dH_max_m"] - dH_expected) / dH_expected < REL

    def test_slow_closure_uses_michaud(self):
        """T_close > 2L/a → regime 'slow', dH = 2LV/(gT)."""
        H, V, a, L, T = 200.0, 3.0, 1200.0, 500.0, 60.0  # T_crit=0.833, T=60>>T_crit
        res = water_hammer_allievi(H, V, a, L, T)
        assert res["ok"] is True
        assert res["regime"] == "slow"
        dH_expected = 2.0 * L * V / (_G * T)
        assert abs(res["dH_max_m"] - dH_expected) / dH_expected < REL

    def test_critical_time_formula(self):
        """T_crit = 2L/a."""
        a, L = 1000.0, 800.0
        res = water_hammer_allievi(100.0, 2.0, a, L, 5.0)
        assert res["ok"] is True
        assert abs(res["T_critical_s"] - 2.0 * L / a) < 1e-9

    def test_h_total_max(self):
        """H_total_max = H_static + dH_max."""
        H_s, V, a, L, T = 150.0, 2.0, 1000.0, 300.0, 30.0
        res = water_hammer_allievi(H_s, V, a, L, T)
        assert res["ok"] is True
        assert abs(res["H_total_max_m"] - (H_s + res["dH_max_m"])) < 1e-9

    def test_overpressure_warning(self):
        """dH/H_static > 0.5 triggers overpressure warning."""
        # Rapid closure with V=5, a=1200 → dH = 612; H_s=100 → ratio=6.1 >> 0.5
        res = water_hammer_allievi(100.0, 5.0, 1200.0, 500.0, 0.2)
        assert res["ok"] is True
        assert any("overpressure" in w.lower() or "surge" in w.lower() for w in res["warnings"])

    def test_negative_H_static_returns_error(self):
        assert water_hammer_allievi(-10.0, 2.0, 1000.0, 300.0, 5.0)["ok"] is False

    def test_zero_T_close_returns_error(self):
        assert water_hammer_allievi(100.0, 2.0, 1000.0, 300.0, 0.0)["ok"] is False


# ===========================================================================
# 10. surge_tank_area
# ===========================================================================

class TestSurgeTankArea:

    def test_thoma_area_positive(self):
        """Thoma area must be positive."""
        res = surge_tank_area(Q=5.0, a_wave=1200.0, L=500.0, H_net=100.0, D_penstock=0.8)
        assert res["ok"] is True
        assert res["A_thoma_m2"] > 0

    def test_oscillation_period_formula(self):
        """T_osc = 2π·√(L·A_pipe / (g·A_thoma))."""
        Q, D, L, H_net = 5.0, 0.8, 500.0, 100.0
        res = surge_tank_area(Q=Q, a_wave=1200.0, L=L, H_net=H_net, D_penstock=D)
        assert res["ok"] is True
        A_pipe = math.pi * D ** 2 / 4.0
        T_expected = 2.0 * math.pi * math.sqrt(L * A_pipe / (_G * res["A_thoma_m2"]))
        assert abs(res["oscillation_period_s"] - T_expected) / T_expected < 1e-5

    def test_energy_area_with_max_upsurge(self):
        """A_energy = Q² / (2g·z_max)."""
        Q, z_max = 3.0, 10.0
        res = surge_tank_area(Q=Q, a_wave=1200.0, L=400.0, H_net=80.0,
                              D_penstock=0.6, max_upsurge_m=z_max)
        assert res["ok"] is True
        A_expected = Q ** 2 / (2.0 * _G * z_max)
        assert abs(res["A_energy_m2"] - A_expected) / A_expected < 1e-5

    def test_design_area_is_max_of_thoma_and_energy(self):
        """A_design = max(A_thoma, A_energy)."""
        res = surge_tank_area(Q=5.0, a_wave=1200.0, L=500.0, H_net=100.0,
                              D_penstock=0.8, max_upsurge_m=15.0)
        assert res["ok"] is True
        assert res["A_design_m2"] == pytest.approx(
            max(res["A_thoma_m2"], res["A_energy_m2"]), rel=1e-9
        )

    def test_negative_Q_returns_error(self):
        assert surge_tank_area(Q=-1.0, a_wave=1200.0, L=500.0,
                               H_net=100.0, D_penstock=0.8)["ok"] is False


# ===========================================================================
# 11. thoma_cavitation
# ===========================================================================

class TestThomaCavitation:

    def test_sigma_plant_formula(self):
        """σ_plant = (H_atm - H_vapor - H_s) / H_net."""
        H_net, H_s = 100.0, 2.0
        P_atm, P_vap, rho = 101325.0, 2338.0, 1000.0
        H_atm = P_atm / (rho * _G)
        H_vapor = P_vap / (rho * _G)
        sigma_expected = (H_atm - H_vapor - H_s) / H_net
        res = thoma_cavitation(H_net, H_s, P_atm_Pa=P_atm,
                               P_vapor_Pa=P_vap, rho=rho)
        assert res["ok"] is True
        assert abs(res["sigma_plant"] - sigma_expected) / sigma_expected < REL

    def test_cavitation_risk_flagged(self):
        """Very high draft head triggers cavitation risk."""
        # H_s=12 m, H_net=50 m → H_atm≈10.3 m → sigma_plant = (10.3-0.24-12)/50 < 0 → risk
        res = thoma_cavitation(H_net=50.0, H_s=12.0, turbine_type="Francis")
        assert res["ok"] is True
        assert res["cavitation_risk"] is True
        assert any("CAVITATION" in w.upper() for w in res["warnings"])

    def test_no_cavitation_risk_safe_draft(self):
        """Small draft head (H_s = -2 m submerged) → no cavitation risk."""
        res = thoma_cavitation(H_net=100.0, H_s=-2.0, turbine_type="Francis")
        assert res["ok"] is True
        assert res["cavitation_risk"] is False

    def test_margin_correct(self):
        """margin = sigma_plant - sigma_crit."""
        res = thoma_cavitation(H_net=100.0, H_s=2.0, turbine_type="Francis")
        assert res["ok"] is True
        assert abs(res["margin"] - (res["sigma_plant"] - res["sigma_crit"])) < 1e-9

    def test_ns_based_sigma_with_speed(self):
        """Providing n_rpm and Q gives Ns-based sigma_crit."""
        res = thoma_cavitation(H_net=100.0, H_s=2.0, turbine_type="Francis",
                               n_rpm=375.0, Q=5.0)
        assert res["ok"] is True
        assert "Ns" in res

    def test_zero_head_returns_error(self):
        assert thoma_cavitation(0.0, 2.0)["ok"] is False


# ===========================================================================
# 12. runaway_speed
# ===========================================================================

class TestRunawaySpeed:

    def test_francis_runaway_factor(self):
        """Francis runaway factor = 1.8."""
        n = 375.0
        res = runaway_speed(n, "Francis")
        assert res["ok"] is True
        assert abs(res["n_runaway_rpm"] - n * 1.8) / (n * 1.8) < REL

    def test_kaplan_runaway_higher(self):
        """Kaplan has higher runaway (2.3×) than Francis (1.8×)."""
        n = 200.0
        r_k = runaway_speed(n, "Kaplan")
        r_f = runaway_speed(n, "Francis")
        assert r_k["n_runaway_rpm"] > r_f["n_runaway_rpm"]

    def test_pelton_runaway_factor(self):
        """Pelton factor = 1.8."""
        n = 500.0
        res = runaway_speed(n, "Pelton")
        assert res["ok"] is True
        assert abs(res["runaway_factor"] - 1.8) < 1e-9

    def test_warning_always_present(self):
        """Runaway speed result always includes a warning."""
        res = runaway_speed(375.0, "Francis")
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_unknown_turbine_returns_error(self):
        assert runaway_speed(300.0, "Gorlov")["ok"] is False

    def test_zero_rpm_returns_error(self):
        assert runaway_speed(0.0)["ok"] is False


# ===========================================================================
# 13. flow_duration_energy
# ===========================================================================

class TestFlowDurationEnergy:

    def test_constant_full_flow_equals_installed_energy(self):
        """FDC = [1.0, 1.0, ...] → E = P_installed × 8760."""
        n = 12
        fracs = [1.0] * n
        res = flow_duration_energy(fracs, Q_design=5.0, H_net=100.0, eta=0.88)
        assert res["ok"] is True
        P_inst_Wh = _RHO * _G * 5.0 * 100.0 * 0.88 * 8760.0
        assert abs(res["E_annual_MWh"] * 1e6 - P_inst_Wh) / P_inst_Wh < 1e-6

    def test_capacity_factor_full_flow(self):
        """All flows at design → capacity factor = 1.0."""
        res = flow_duration_energy([1.0] * 8, Q_design=3.0, H_net=50.0)
        assert res["ok"] is True
        assert abs(res["capacity_factor"] - 1.0) < 1e-6

    def test_zero_flows_give_zero_energy(self):
        """All zero flows → E = 0."""
        res = flow_duration_energy([0.0] * 5, Q_design=2.0, H_net=40.0)
        assert res["ok"] is True
        assert abs(res["E_annual_MWh"]) < 1e-12

    def test_spill_fraction_computed(self):
        """Flows > 1 are counted as spill."""
        fracs = [0.5, 1.0, 1.5, 2.0]  # 2 intervals > 1 → spill = 0.5
        res = flow_duration_energy(fracs, Q_design=5.0, H_net=80.0)
        assert res["ok"] is True
        assert abs(res["spill_fraction"] - 0.5) < 1e-9

    def test_partial_flow_reduces_energy(self):
        """Constant flow at 0.5·Q_design → E = 0.5 × full-flow energy."""
        fracs_full = [1.0] * 6
        fracs_half = [0.5] * 6
        res_full = flow_duration_energy(fracs_full, Q_design=5.0, H_net=100.0, eta=0.88)
        res_half = flow_duration_energy(fracs_half, Q_design=5.0, H_net=100.0, eta=0.88)
        assert res_full["ok"] and res_half["ok"]
        assert abs(res_half["E_annual_MWh"] / res_full["E_annual_MWh"] - 0.5) < REL

    def test_negative_Q_design_returns_error(self):
        assert flow_duration_energy([0.5, 1.0], Q_design=-1.0, H_net=50.0)["ok"] is False

    def test_single_interval_returns_error(self):
        assert flow_duration_energy([1.0], Q_design=5.0, H_net=50.0)["ok"] is False


# ===========================================================================
# 14. pelton_jet_sizing
# ===========================================================================

class TestPeltonJetSizing:

    def test_jet_velocity_formula(self):
        """V_jet = Cv·√(2·g·H_net)."""
        H, Cv = 400.0, 0.97
        res = pelton_jet_sizing(H_net=H, Q=0.5, Cv=Cv)
        assert res["ok"] is True
        V_expected = Cv * math.sqrt(2.0 * _G * H)
        assert abs(res["V_jet_m_s"] - V_expected) / V_expected < REL

    def test_jet_diameter_formula(self):
        """A_jet = Q / (n_jets·V_jet),  d_jet = √(4·A_jet/π)."""
        H, Q, n_jets = 300.0, 0.3, 2
        res = pelton_jet_sizing(H_net=H, Q=Q, n_jets=n_jets)
        assert res["ok"] is True
        V_jet = res["V_jet_m_s"]
        A_jet = Q / (n_jets * V_jet)
        d_expected = math.sqrt(4.0 * A_jet / math.pi)
        assert abs(res["d_jet_m"] - d_expected) / d_expected < REL

    def test_bucket_width_is_3p2_times_jet(self):
        """B_bucket = 3.2 × d_jet."""
        res = pelton_jet_sizing(H_net=200.0, Q=0.4, n_jets=1)
        assert res["ok"] is True
        assert abs(res["B_bucket_m"] - 3.2 * res["d_jet_m"]) < 1e-10

    def test_optimal_speed_ratio(self):
        """u_opt = 0.46 × V_jet."""
        res = pelton_jet_sizing(H_net=500.0, Q=0.2)
        assert res["ok"] is True
        assert abs(res["u_opt_m_s"] - 0.46 * res["V_jet_m_s"]) < 1e-9

    def test_n_opt_with_runner_diameter(self):
        """n_opt = 60·u_opt / (π·D_runner)."""
        D_runner = 1.5
        res = pelton_jet_sizing(H_net=500.0, Q=0.5, D_runner_m=D_runner)
        assert res["ok"] is True
        n_expected = 60.0 * res["u_opt_m_s"] / (math.pi * D_runner)
        assert abs(res["n_opt_rpm"] - n_expected) / n_expected < REL

    def test_mm_field_consistent(self):
        """d_jet_mm = d_jet_m × 1000."""
        res = pelton_jet_sizing(H_net=300.0, Q=0.3)
        assert res["ok"] is True
        assert abs(res["d_jet_mm"] - res["d_jet_m"] * 1000.0) < 1e-9

    def test_invalid_n_jets_returns_error(self):
        assert pelton_jet_sizing(H_net=300.0, Q=0.3, n_jets=7)["ok"] is False

    def test_zero_H_returns_error(self):
        assert pelton_jet_sizing(H_net=0.0, Q=0.3)["ok"] is False


# ===========================================================================
# 15. micro_hydro_quick
# ===========================================================================

class TestMicroHydroQuick:

    def test_no_friction_h_net_equals_gross(self):
        """Without penstock, H_net = H_gross."""
        res = micro_hydro_quick(H_gross=20.0, Q=0.1)
        assert res["ok"] is True
        assert abs(res["H_net_m"] - 20.0) < 1e-9

    def test_power_formula_no_friction(self):
        """P = ρ·g·Q·H·η with zero friction."""
        H, Q, eta = 30.0, 0.2, 0.70
        res = micro_hydro_quick(H_gross=H, Q=Q, eta_overall=eta)
        assert res["ok"] is True
        P_expected = _RHO * _G * Q * H * eta / 1e3  # kW
        assert abs(res["P_shaft_kW"] - P_expected) / P_expected < REL

    def test_friction_reduces_net_head(self):
        """With penstock, H_net < H_gross."""
        res = micro_hydro_quick(H_gross=30.0, Q=0.15, penstock_length=200.0)
        assert res["ok"] is True
        assert res["H_net_m"] < 30.0

    def test_turbine_type_field_present(self):
        res = micro_hydro_quick(H_gross=50.0, Q=0.1)
        assert res["ok"] is True
        assert "turbine_type" in res

    def test_large_power_warning(self):
        """P > 100 kW triggers a warning."""
        res = micro_hydro_quick(H_gross=100.0, Q=2.0, eta_overall=0.88)
        assert res["ok"] is True
        assert any("100" in w or "micro" in w.lower() for w in res["warnings"])

    def test_zero_gross_head_returns_error(self):
        assert micro_hydro_quick(H_gross=0.0, Q=0.1)["ok"] is False

    def test_negative_Q_returns_error(self):
        assert micro_hydro_quick(H_gross=20.0, Q=-0.1)["ok"] is False


# ===========================================================================
# 16. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_plant_power_happy_path(self):
        ctx = _ctx()
        raw = _run(run_plant_power(ctx, _args(Q=5.0, H_net=100.0, eta=0.88)))
        d = _ok_tool(raw)
        expected = _RHO * _G * 5.0 * 100.0 * 0.88
        assert abs(d["P_shaft_W"] - expected) / expected < 1e-6

    def test_run_plant_power_missing_Q(self):
        ctx = _ctx()
        raw = _run(run_plant_power(ctx, _args(H_net=100.0)))
        _err_tool(raw)

    def test_run_turbine_type_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turbine_type(ctx, _args(H_net=500.0, Q=1.0)))
        d = _ok_tool(raw)
        assert d["turbine_type"] == "Pelton"

    def test_run_turbine_type_with_speed(self):
        ctx = _ctx()
        raw = _run(run_turbine_type(ctx, _args(H_net=200.0, Q=2.0, n_rpm=375.0)))
        d = _ok_tool(raw)
        assert "Ns" in d and d["Ns"] > 0

    def test_run_runner_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_runner_speed(ctx, _args(H_net=100.0, turbine_type="Francis")))
        d = _ok_tool(raw)
        assert abs(d["n_rpm_approx"] - 50.0 * math.sqrt(100.0)) < 1e-9

    def test_run_runner_speed_missing_field(self):
        ctx = _ctx()
        raw = _run(run_runner_speed(ctx, _args(turbine_type="Francis")))
        _err_tool(raw)

    def test_run_sync_speed_poles_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sync_speed_poles(ctx, _args(n_runner_rpm=375.0, f_hz=50.0)))
        d = _ok_tool(raw)
        assert d["poles_lower"] % 2 == 0
        assert d["poles_higher"] % 2 == 0

    def test_run_penstock_diameter_happy_path(self):
        ctx = _ctx()
        raw = _run(run_penstock_diameter(ctx, _args(Q=3.0, V_economic=3.5)))
        d = _ok_tool(raw)
        assert d["D_m"] > 0

    def test_run_penstock_friction_happy_path(self):
        ctx = _ctx()
        raw = _run(run_penstock_friction(ctx, _args(Q=2.0, D=0.6, L=500.0, f=0.015)))
        d = _ok_tool(raw)
        assert d["h_f_m"] > 0

    def test_run_penstock_wall_happy_path(self):
        ctx = _ctx()
        raw = _run(run_penstock_wall(ctx, _args(D=0.8, P_internal_Pa=2e6)))
        d = _ok_tool(raw)
        assert d["t_total_mm"] > 0

    def test_run_joukowsky_happy_path(self):
        ctx = _ctx()
        raw = _run(run_water_hammer_joukowsky(ctx, _args(V=3.0, a_wave=1200.0)))
        d = _ok_tool(raw)
        assert abs(d["dP_Pa"] - _RHO * 1200.0 * 3.0) / (_RHO * 1200.0 * 3.0) < 1e-9

    def test_run_allievi_happy_path(self):
        ctx = _ctx()
        raw = _run(run_water_hammer_allievi(
            ctx, _args(H_static=200.0, V=3.0, a_wave=1200.0, L=500.0, T_close=60.0)
        ))
        d = _ok_tool(raw)
        assert d["regime"] == "slow"

    def test_run_surge_tank_happy_path(self):
        ctx = _ctx()
        raw = _run(run_surge_tank(
            ctx, _args(Q=5.0, a_wave=1200.0, L=500.0, H_net=100.0, D_penstock=0.8)
        ))
        d = _ok_tool(raw)
        assert d["A_thoma_m2"] > 0

    def test_run_thoma_cavitation_happy_path(self):
        ctx = _ctx()
        raw = _run(run_thoma_cavitation(ctx, _args(H_net=100.0, H_s=2.0, turbine_type="Francis")))
        d = _ok_tool(raw)
        assert "sigma_plant" in d
        assert "cavitation_risk" in d

    def test_run_runaway_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_runaway_speed(ctx, _args(n_rpm=375.0, turbine_type="Kaplan")))
        d = _ok_tool(raw)
        assert abs(d["n_runaway_rpm"] - 375.0 * 2.3) / (375.0 * 2.3) < 1e-9

    def test_run_flow_duration_energy_happy_path(self):
        ctx = _ctx()
        raw = _run(run_flow_duration_energy(
            ctx, _args(flow_fractions=[1.0, 0.8, 0.6, 0.4],
                       Q_design=5.0, H_net=100.0, eta=0.88)
        ))
        d = _ok_tool(raw)
        assert d["E_annual_MWh"] > 0
        assert 0 <= d["capacity_factor"] <= 1.0

    def test_run_pelton_jet_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pelton_jet(ctx, _args(H_net=400.0, Q=0.5, n_jets=2, Cv=0.97)))
        d = _ok_tool(raw)
        assert d["V_jet_m_s"] > 0
        assert d["d_jet_m"] > 0

    def test_run_micro_quick_happy_path(self):
        ctx = _ctx()
        raw = _run(run_micro_quick(
            ctx, _args(H_gross=25.0, Q=0.15, penstock_length=100.0, eta_overall=0.70)
        ))
        d = _ok_tool(raw)
        assert d["H_net_m"] < 25.0
        assert d["P_shaft_kW"] > 0

    def test_run_micro_quick_bad_json(self):
        ctx = _ctx()
        raw = _run(run_micro_quick(ctx, b"not json"))
        _err_tool(raw)
