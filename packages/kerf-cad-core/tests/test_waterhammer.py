"""
Hermetic tests for kerf_cad_core.waterhammer — hydraulic transient analysis.

All tests are pure-Python, deterministic, and independent of OCC / DB / network.
Numeric results verified against Wylie & Streeter (1993), Chaudhry (2014),
and direct algebraic hand-calculations.

Sections covered
----------------
  transient.wave_speed            — celerity formula + restraint + gas correction
  transient.joukowsky_head_rise   — rapid/slow closure, column-sep, overpressure
  transient.moc_single_pipe       — MOC grid, envelopes, BCs, column-sep flag
  transient.safe_closure_time     — rigid-column inversion
  transient.pump_trip_simplified  — rundown time + Joukowsky drop
  transient.air_vessel_sizing     — rigid-column volume estimate
  transient.surge_tank_oscillation— period + amplitude
  transient.relief_valve_flow     — Cv orifice + open/closed logic
  plugin._TOOL_MODULES            — registration

References
----------
Wylie, E.B. & Streeter, V.L. (1993) Fluid Transients in Systems. Prentice Hall.
Chaudhry, M.H. (2014) Applied Hydraulic Transients, 3rd ed. Springer.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.waterhammer.transient import (
    _G,
    wave_speed,
    joukowsky_head_rise,
    moc_single_pipe,
    safe_closure_time,
    pump_trip_simplified,
    air_vessel_sizing,
    surge_tank_oscillation,
    relief_valve_flow,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    class _Ctx:
        project_id = "test"
    return _Ctx()


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


REL = 1e-4    # 0.01% relative tolerance
STRICT = 1e-9  # strict algebraic checks


# ===========================================================================
# 1. wave_speed
# ===========================================================================

class TestWaveSpeed:
    """Wylie & Streeter §2.3 / Chaudhry §2.4."""

    # Steel pipe: D=0.5m, e=0.01m, E=200GPa, K_fluid=2.07GPa, rho=998
    # Expected a ≈ 1200 m/s range (depends on restraint)

    def test_rigid_pipe_limit(self):
        """For very stiff pipe (E→∞) a → sqrt(K/ρ) ≈ 1439 m/s for water."""
        r = wave_speed(K_fluid=2.07e9, rho=998.0, D=0.5, e=10.0, E_pipe=200e12)
        # e very thick → stiff; a approaches sqrt(K/rho)
        a_rigid = math.sqrt(2.07e9 / 998.0)
        assert abs(r["a_m_s"] - a_rigid) / a_rigid < 0.01

    def test_steel_pipe_typical_range(self):
        """Typical steel pipe: 900–1400 m/s."""
        r = wave_speed(K_fluid=2.07e9, rho=998.0, D=0.3, e=0.008, E_pipe=200e9,
                       restraint="anchored-both")
        assert 900 < r["a_m_s"] < 1400

    def test_expansion_joint_c1_is_one(self):
        """Expansion joint: c1=1.0."""
        r = wave_speed(K_fluid=2.07e9, rho=998.0, D=0.3, e=0.008, E_pipe=200e9,
                       restraint="expansion-joint")
        assert abs(r["c1"] - 1.0) < STRICT

    def test_anchored_both_c1(self):
        """anchored-both: c1 = 1 - 0.3² = 0.91."""
        r = wave_speed(K_fluid=2.07e9, rho=998.0, D=0.3, e=0.008, E_pipe=200e9,
                       restraint="anchored-both")
        assert abs(r["c1"] - (1.0 - 0.09)) < 1e-6

    def test_gas_correction_reduces_wavespeed(self):
        """Entrained gas reduces wave speed (Chaudhry §2.4)."""
        r_no_gas = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9)
        r_gas = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9, alpha_gas=1e-3, P_abs=2e5)
        assert r_gas["a_m_s"] < r_no_gas["a_m_s"]

    def test_k_eff_no_gas(self):
        """No gas: K_eff = K_fluid."""
        r = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9)
        assert abs(r["K_eff"] - 2.07e9) < STRICT

    def test_k_eff_with_gas_less_than_k_fluid(self):
        """With gas: K_eff < K_fluid."""
        r = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9, alpha_gas=0.01, P_abs=200000.0)
        assert r["K_eff"] < 2.07e9

    def test_invalid_k_fluid_returns_zero(self):
        r = wave_speed(K_fluid=-1.0, rho=998.0, D=0.3, e=0.008, E_pipe=200e9)
        assert r["a_m_s"] == 0.0
        assert len(r["warnings"]) > 0

    def test_invalid_rho_returns_zero(self):
        r = wave_speed(K_fluid=2.07e9, rho=0.0, D=0.3, e=0.008, E_pipe=200e9)
        assert r["a_m_s"] == 0.0

    def test_invalid_D_returns_zero(self):
        r = wave_speed(K_fluid=2.07e9, rho=998.0, D=0.0, e=0.008, E_pipe=200e9)
        assert r["a_m_s"] == 0.0

    def test_anchored_up_c1(self):
        """anchored-up: c1 = 1 - ν/2 = 1 - 0.15 = 0.85."""
        r = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9, restraint="anchored-up")
        assert abs(r["c1"] - 0.85) < 1e-6

    def test_unknown_restraint_falls_back(self):
        r = wave_speed(2.07e9, 998.0, 0.3, 0.008, 200e9, restraint="free-floating")
        # should fall back to expansion-joint
        assert r["a_m_s"] > 0
        assert any("Unknown" in w for w in r["warnings"])


# ===========================================================================
# 2. joukowsky_head_rise
# ===========================================================================

class TestJoukowskyHeadRise:
    """Wylie & Streeter §3.1 / Chaudhry §3.2."""

    def test_rapid_closure_instantaneous(self):
        """Rapid closure: ΔH = a·V0/g (Joukowsky equation)."""
        V0, a = 2.0, 1200.0
        r = joukowsky_head_rise(V0=V0, a=a, L=1000.0, t_close=0.1)
        expected = a * V0 / _G
        assert abs(r["dH_m"] - expected) / expected < REL

    def test_slow_closure_rigid_column(self):
        """Slow closure (t > 2L/a): ΔH = 2LV0/(g·t_close)."""
        V0, L, t_close = 2.0, 1000.0, 5.0  # T_pipe = 2000/1200 ≈ 1.67 s < 5 s
        a = 1200.0
        r = joukowsky_head_rise(V0=V0, a=a, L=L, t_close=t_close)
        expected = 2.0 * L * V0 / (_G * t_close)
        assert abs(r["dH_m"] - expected) / expected < REL

    def test_rapid_flag_set_correctly(self):
        """rapid_closure=True when t_close <= T_pipe."""
        a, L = 1200.0, 1000.0
        T_pipe = 2.0 * L / a  # ≈ 1.667 s
        r_rapid = joukowsky_head_rise(V0=2.0, a=a, L=L, t_close=T_pipe * 0.5)
        r_slow = joukowsky_head_rise(V0=2.0, a=a, L=L, t_close=T_pipe * 2.0)
        assert r_rapid["rapid_closure"] is True
        assert r_slow["rapid_closure"] is False

    def test_pipe_period_correct(self):
        """T_pipe = 2L/a."""
        a, L = 1200.0, 1000.0
        r = joukowsky_head_rise(V0=2.0, a=a, L=L, t_close=1.0)
        assert abs(r["T_pipe_s"] - 2.0 * L / a) < STRICT

    def test_h_max_equals_h0_plus_dh(self):
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=0.5, H0=50.0)
        assert abs(r["H_max_m"] - (50.0 + r["dH_m"])) < STRICT

    def test_column_sep_flag_low_h0(self):
        """Very low initial head: column separation expected."""
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=0.5,
                                H0=0.0, P_vapor_Pa=2338.0)
        # H_min_estimate = H0 - dH = 0 - 244.9 → well below vapor head
        assert r["column_sep"] is True

    def test_no_column_sep_high_h0(self):
        """High initial head: no column separation."""
        r = joukowsky_head_rise(V0=0.1, a=1200.0, L=500.0, t_close=0.1, H0=200.0)
        assert r["column_sep"] is False

    def test_overpressure_flag(self):
        """Overpressure flagged when H_max > pipe_rating."""
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=0.5,
                                H0=50.0, pipe_rating_m=100.0)
        assert r["overpressure"] is True

    def test_no_overpressure(self):
        r = joukowsky_head_rise(V0=0.1, a=1200.0, L=500.0, t_close=0.1,
                                H0=50.0, pipe_rating_m=500.0)
        assert r["overpressure"] is False

    def test_zero_velocity_zero_head_rise(self):
        r = joukowsky_head_rise(V0=0.0, a=1200.0, L=1000.0, t_close=1.0)
        assert r["dH_m"] == 0.0

    def test_rapid_dh_greater_than_slow(self):
        """Rapid closure always gives larger or equal head rise than slow."""
        V0, a, L = 2.0, 1200.0, 1000.0
        T_pipe = 2.0 * L / a
        r_rapid = joukowsky_head_rise(V0, a, L, t_close=T_pipe * 0.5)
        r_slow = joukowsky_head_rise(V0, a, L, t_close=T_pipe * 3.0)
        assert r_rapid["dH_m"] >= r_slow["dH_m"]


# ===========================================================================
# 3. moc_single_pipe
# ===========================================================================

class TestMOCSinglePipe:
    """Wylie & Streeter §3.2 — MOC explicit grid."""

    def test_courant_number_is_one(self):
        """dt = dx/a → Courant = 1 by construction."""
        r = moc_single_pipe(L=500.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.02, n_reaches=4, t_total=2.0)
        assert r["courant_ok"] is True
        assert abs(r["dt_s"] - r["dx_m"] / 1200.0) < 1e-12

    def test_dx_equals_L_over_n(self):
        r = moc_single_pipe(L=600.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.02, n_reaches=6, t_total=1.0)
        assert abs(r["dx_m"] - 100.0) < STRICT

    def test_n_nodes_correct(self):
        r = moc_single_pipe(L=500.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.02, n_reaches=5, t_total=1.0)
        assert len(r["H_envelope_max"]) == 6  # n_reaches + 1
        assert len(r["x_nodes_m"]) == 6

    def test_x_nodes_positions(self):
        r = moc_single_pipe(L=400.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.0, n_reaches=4, t_total=0.5)
        expected_x = [0.0, 100.0, 200.0, 300.0, 400.0]
        for xi, xe in zip(r["x_nodes_m"], expected_x):
            assert abs(xi - xe) < STRICT

    def test_rapid_valve_closure_head_rise(self):
        """After rapid closure, max head at downstream > initial head."""
        a, L = 1200.0, 500.0
        T_pipe = 2.0 * L / a
        r = moc_single_pipe(L=L, D=0.3, a=a, V0=2.0, H_res=100.0,
                            f=0.01, n_reaches=4, t_total=T_pipe * 3,
                            t_close=T_pipe * 0.5)
        # Max head at downstream node should exceed initial reservoir head
        assert r["H_envelope_max"][-1] > 100.0

    def test_dead_end_bc_zero_velocity(self):
        """Dead-end BC: velocity at last node is always forced to 0 at each step."""
        r = moc_single_pipe(L=400.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.01, n_reaches=4, t_total=2.0,
                            downstream_bc="dead-end")
        # After simulation, the last node velocity envelope min should be <= 0
        # (the dead-end forces V=0 at every step; V_min at last node should be 0
        # since only the initial condition contributes V0 to the max envelope)
        assert abs(r["V_envelope_min"][-1]) < 1e-9

    def test_column_sep_flag_low_reservoir(self):
        """Very low reservoir head + high velocity → column separation."""
        r = moc_single_pipe(L=200.0, D=0.3, a=1200.0, V0=3.0, H_res=0.5,
                            f=0.0, n_reaches=4, t_total=1.0,
                            P_vapor_Pa=2338.0)
        assert r["column_sep"] is True

    def test_overpressure_flag_low_rating(self):
        """Low pipe rating → overpressure flag."""
        r = moc_single_pipe(L=500.0, D=0.3, a=1200.0, V0=3.0, H_res=100.0,
                            f=0.01, n_reaches=4, t_total=2.0,
                            pipe_rating_m=150.0, t_close=0.3)
        assert r["overpressure"] is True

    def test_parabolic_closure_returns_results(self):
        r = moc_single_pipe(L=500.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.01, n_reaches=4, t_total=2.0,
                            closure_law="parabolic")
        assert len(r["H_envelope_max"]) == 5

    def test_invalid_L_returns_empty(self):
        r = moc_single_pipe(L=0.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.01, n_reaches=4, t_total=2.0)
        assert r["H_envelope_max"] == []
        assert len(r["warnings"]) > 0

    def test_pipe_period_correct(self):
        r = moc_single_pipe(L=600.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.0, n_reaches=4, t_total=1.0)
        assert abs(r["T_pipe_s"] - 2.0 * 600.0 / 1200.0) < STRICT

    def test_envelope_max_geq_min(self):
        """H_max >= H_min at every node."""
        r = moc_single_pipe(L=500.0, D=0.3, a=1200.0, V0=2.0, H_res=100.0,
                            f=0.02, n_reaches=5, t_total=2.0)
        for hmax, hmin in zip(r["H_envelope_max"], r["H_envelope_min"]):
            assert hmax >= hmin - 1e-9


# ===========================================================================
# 4. safe_closure_time
# ===========================================================================

class TestSafeClosureTime:
    """Rigid-column inversion: Wylie & Streeter §3.1."""

    def test_basic_formula(self):
        """t_min = 2·L·V0 / (g·dH_allow)."""
        V0, L, dH = 2.0, 1000.0, 50.0
        r = safe_closure_time(V0=V0, a=1200.0, L=L, H0=100.0, dH_allowable=dH)
        expected = 2.0 * L * V0 / (_G * dH)
        assert abs(r["t_close_min_s"] - expected) / expected < REL

    def test_pipe_period_correct(self):
        r = safe_closure_time(V0=2.0, a=1200.0, L=1000.0, H0=100.0, dH_allowable=50.0)
        assert abs(r["T_pipe_s"] - 2.0 * 1000.0 / 1200.0) < STRICT

    def test_joukowsky_rapid_dH(self):
        """dH_rapid = a*V0/g."""
        V0, a = 2.0, 1200.0
        r = safe_closure_time(V0=V0, a=a, L=1000.0, H0=100.0, dH_allowable=50.0)
        assert abs(r["dH_rapid_m"] - a * V0 / _G) < STRICT

    def test_zero_velocity_gives_zero_closure_time(self):
        r = safe_closure_time(V0=0.0, a=1200.0, L=1000.0, H0=100.0, dH_allowable=50.0)
        assert r["t_close_min_s"] == 0.0

    def test_rapid_flag_at_min(self):
        """When t_min <= T_pipe, rapid_at_min=True."""
        # Choose small L / large dH → small t_min; compare with T_pipe
        r = safe_closure_time(V0=2.0, a=1200.0, L=100.0, H0=100.0, dH_allowable=500.0)
        # t_min = 2*100*2/(9.81*500) ≈ 0.0816 s; T_pipe = 2*100/1200 ≈ 0.167 s
        # t_min < T_pipe → rapid
        assert r["rapid_at_min"] is True

    def test_invalid_inputs_return_none(self):
        r = safe_closure_time(V0=2.0, a=-1.0, L=1000.0, H0=100.0, dH_allowable=50.0)
        assert r["t_close_min_s"] is None


# ===========================================================================
# 5. pump_trip_simplified
# ===========================================================================

class TestPumpTripSimplified:

    def test_rundown_time_formula(self):
        """t_run = WR² · ω / T_rated = WR² · ω² / P_rated."""
        n_rpm, P_W, WR2 = 1450.0, 50000.0, 10.0
        omega = 2.0 * math.pi * n_rpm / 60.0
        T_rated = P_W / omega
        expected_t = WR2 * omega / T_rated
        r = pump_trip_simplified(H_ss=50.0, V0=2.0, a=1200.0, L=500.0,
                                 WR2=WR2, n_rated=n_rpm, P_rated_W=P_W)
        assert abs(r["t_rundown_s"] - expected_t) / expected_t < REL

    def test_joukowsky_drop(self):
        """dH_drop = a·V0/g."""
        V0, a = 2.0, 1200.0
        r = pump_trip_simplified(H_ss=100.0, V0=V0, a=a, L=500.0,
                                 WR2=10.0, n_rated=1450.0, P_rated_W=50000.0)
        assert abs(r["dH_drop_m"] - a * V0 / _G) / (a * V0 / _G) < REL

    def test_h_min_formula(self):
        """H_min = H_ss - dH_drop."""
        r = pump_trip_simplified(H_ss=100.0, V0=2.0, a=1200.0, L=500.0,
                                 WR2=10.0, n_rated=1450.0, P_rated_W=50000.0)
        assert abs(r["H_min_m"] - (r["dH_drop_m"] * (-1) + 100.0)) < 1e-6
        # H_min = H_ss - dH_drop
        assert abs(r["H_min_m"] - (100.0 - r["dH_drop_m"])) < STRICT

    def test_column_sep_flagged_low_head(self):
        """Low H_ss → column separation."""
        r = pump_trip_simplified(H_ss=5.0, V0=2.0, a=1200.0, L=500.0,
                                 WR2=10.0, n_rated=1450.0, P_rated_W=50000.0,
                                 P_vapor_Pa=2338.0)
        assert r["column_sep"] is True

    def test_no_column_sep_high_head(self):
        r = pump_trip_simplified(H_ss=500.0, V0=0.5, a=800.0, L=200.0,
                                 WR2=10.0, n_rated=1450.0, P_rated_W=50000.0)
        assert r["column_sep"] is False

    def test_invalid_input_returns_none(self):
        r = pump_trip_simplified(H_ss=0.0, V0=2.0, a=1200.0, L=500.0,
                                 WR2=10.0, n_rated=1450.0, P_rated_W=50000.0)
        assert r["t_rundown_s"] is None


# ===========================================================================
# 6. air_vessel_sizing
# ===========================================================================

class TestAirVesselSizing:
    """Chaudhry §13.3 simplified rigid-column formula."""

    def test_vol_min_formula(self):
        """Vol_min = a·L·V0·A / (2·g·dH)."""
        a, L, V0, A, dH = 1200.0, 500.0, 2.0, 0.07854, 50.0
        r = air_vessel_sizing(V0=V0, A_pipe=A, a=a, L=L, H_res=100.0,
                              dH_allowable=dH)
        expected = a * L * V0 * A / (2.0 * _G * dH)
        assert abs(r["vol_min_m3"] - expected) / expected < REL

    def test_recommended_is_1p5x_min(self):
        r = air_vessel_sizing(V0=2.0, A_pipe=0.07854, a=1200.0, L=500.0,
                              H_res=100.0, dH_allowable=50.0)
        assert abs(r["vol_recommended_m3"] - 1.5 * r["vol_min_m3"]) < STRICT

    def test_initial_pressure_formula(self):
        """P_initial = rho*g*H_res + P_atm."""
        rho, H_res, P_atm = 998.0, 100.0, 101325.0
        r = air_vessel_sizing(V0=2.0, A_pipe=0.07854, a=1200.0, L=500.0,
                              H_res=H_res, dH_allowable=50.0,
                              rho=rho, P_atm_Pa=P_atm)
        expected_P = rho * _G * H_res + P_atm
        assert abs(r["initial_pressure_Pa"] - expected_P) / expected_P < REL

    def test_larger_dH_allowable_smaller_volume(self):
        """Greater allowable surge → smaller vessel needed."""
        r1 = air_vessel_sizing(2.0, 0.07854, 1200.0, 500.0, 100.0, dH_allowable=50.0)
        r2 = air_vessel_sizing(2.0, 0.07854, 1200.0, 500.0, 100.0, dH_allowable=100.0)
        assert r1["vol_min_m3"] > r2["vol_min_m3"]

    def test_invalid_V0_returns_none(self):
        r = air_vessel_sizing(V0=0.0, A_pipe=0.07854, a=1200.0, L=500.0,
                              H_res=100.0, dH_allowable=50.0)
        assert r["vol_min_m3"] is None


# ===========================================================================
# 7. surge_tank_oscillation
# ===========================================================================

class TestSurgeTankOscillation:
    """Wylie & Streeter §8.1 — mass oscillation."""

    def test_period_formula(self):
        """T = 2π·sqrt(L·A_tank / (g·A_pipe))."""
        L, A_p, A_t = 500.0, 0.5, 5.0
        r = surge_tank_oscillation(L=L, A_pipe=A_p, A_tank=A_t, H0=50.0, V0=2.0)
        expected_T = 2.0 * math.pi * math.sqrt(L * A_t / (_G * A_p))
        assert abs(r["T_osc_s"] - expected_T) / expected_T < REL

    def test_amplitude_formula(self):
        """Frictionless mass-oscillation amplitude (Chaudhry, Applied
        Hydraulic Transients §13-2):
            z_max = V0 · sqrt(L · A_pipe / (g · A_tank))
        which equals V0·(A_pipe/A_tank)/omega — NOT V0/omega (the previous
        assertion inverted the area ratio and over-predicted the surge by
        a factor A_tank/A_pipe = 10× for this case)."""
        L, A_p, A_t, V0 = 500.0, 0.5, 5.0, 2.0
        r = surge_tank_oscillation(L=L, A_pipe=A_p, A_tank=A_t, H0=200.0, V0=V0)
        expected_z = V0 * math.sqrt(L * A_p / (_G * A_t))
        assert abs(r["z_max_m"] - expected_z) / expected_z < REL
        # Equivalent (A_pipe/A_tank)/omega form
        omega = math.sqrt(_G * A_p / (L * A_t))
        assert abs(r["z_max_m"] - V0 * (A_p / A_t) / omega) / expected_z < REL

    def test_omega_consistent_with_period(self):
        r = surge_tank_oscillation(L=500.0, A_pipe=0.5, A_tank=5.0, H0=100.0, V0=2.0)
        assert abs(r["omega_rad_s"] - 2.0 * math.pi / r["T_osc_s"]) < 1e-9

    def test_zero_velocity_zero_amplitude(self):
        r = surge_tank_oscillation(L=500.0, A_pipe=0.5, A_tank=5.0, H0=100.0, V0=0.0)
        assert r["z_max_m"] == 0.0

    def test_overflow_warning_when_amplitude_exceeds_h0(self):
        """z_max > H0 → warning issued."""
        r = surge_tank_oscillation(L=5000.0, A_pipe=0.5, A_tank=0.1,
                                   H0=1.0, V0=10.0)
        assert any("overflow" in w.lower() or "drain" in w.lower() or "exceed" in w.lower()
                   for w in r["warnings"])

    def test_invalid_L_returns_none(self):
        r = surge_tank_oscillation(L=0.0, A_pipe=0.5, A_tank=5.0, H0=50.0, V0=2.0)
        assert r["T_osc_s"] is None

    def test_larger_tank_area_longer_period(self):
        """Larger tank → longer oscillation period."""
        r1 = surge_tank_oscillation(500.0, 0.5, 5.0, 100.0, 2.0)
        r2 = surge_tank_oscillation(500.0, 0.5, 20.0, 100.0, 2.0)
        assert r2["T_osc_s"] > r1["T_osc_s"]


# ===========================================================================
# 8. relief_valve_flow
# ===========================================================================

class TestReliefValveFlow:

    def test_valve_closed_below_set(self):
        """No flow when H_operating <= H_set."""
        r = relief_valve_flow(H_set=100.0, H_operating=90.0, Cv=10.0)
        assert r["Q_m3s"] == 0.0
        assert r["valve_open"] is False

    def test_valve_open_above_set(self):
        """Flow when H_operating > H_set."""
        r = relief_valve_flow(H_set=100.0, H_operating=110.0, Cv=10.0)
        assert r["valve_open"] is True
        assert r["Q_m3s"] > 0.0

    def test_dH_formula(self):
        """dH = H_operating - H_set."""
        r = relief_valve_flow(H_set=80.0, H_operating=100.0, Cv=10.0)
        assert abs(r["dH_m"] - 20.0) < STRICT

    def test_higher_pressure_more_flow(self):
        """Higher differential → more flow."""
        r1 = relief_valve_flow(H_set=100.0, H_operating=110.0, Cv=10.0)
        r2 = relief_valve_flow(H_set=100.0, H_operating=130.0, Cv=10.0)
        assert r2["Q_m3s"] > r1["Q_m3s"]

    def test_higher_Cv_more_flow(self):
        r1 = relief_valve_flow(H_set=100.0, H_operating=120.0, Cv=5.0)
        r2 = relief_valve_flow(H_set=100.0, H_operating=120.0, Cv=10.0)
        assert r2["Q_m3s"] > r1["Q_m3s"]

    def test_invalid_H_set_returns_zero(self):
        r = relief_valve_flow(H_set=0.0, H_operating=120.0, Cv=10.0)
        assert r["Q_m3s"] == 0.0
        assert len(r["warnings"]) > 0

    def test_Cv_proportional_to_Q(self):
        """Q ∝ Cv (linear relationship at same dH)."""
        r1 = relief_valve_flow(100.0, 120.0, 5.0)
        r2 = relief_valve_flow(100.0, 120.0, 10.0)
        assert abs(r2["Q_m3s"] / r1["Q_m3s"] - 2.0) < 1e-9


# ===========================================================================
# 9. Authoritative external-reference cases (citable, numeric answers)
# ===========================================================================

class TestAuthoritativeReferences:
    """Cross-checks vs published worked results with known numeric answers.

    Sources:
      Wylie, E.B. & Streeter, V.L. (1993) Fluid Transients in Systems
        — Korteweg wave speed (§2.3), Joukowsky head rise (§3.1),
          MOC reservoir-pipe-valve benchmark (§3.2).
      Chaudhry, M.H. (2014) Applied Hydraulic Transients, 3rd ed.
        — pipe period 2L/a (§3-2), surge-tank mass oscillation (§13-2),
          rigid-column slow closure, column-separation vapor head.
    """

    def test_korteweg_wave_speed_anchored_steel(self):
        # Wylie & Streeter §2.3 Korteweg formula, thin-walled steel pipe
        # anchored both ends: K=2.19 GPa, ρ=999, D=0.5 m, e=5 mm,
        # E=207 GPa, c1=1−ν²=0.91 → a ≈ 1056.8 m/s.
        r = wave_speed(K_fluid=2.19e9, rho=999.0, D=0.5, e=0.005,
                       E_pipe=207e9, restraint="anchored-both")
        assert abs(r["c1"] - 0.91) < 1e-9
        assert abs(r["a_m_s"] - 1056.8) < 0.5

    def test_joukowsky_head_rise_classic(self):
        # Wylie & Streeter §3.1: instantaneous closure ΔH = a·V0/g.
        # a=1200 m/s, V0=2 m/s, g=9.80665 → ΔH = 244.73 m.
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=1e-6)
        assert r["rapid_closure"] is True
        assert abs(r["dH_m"] - 244.732) < 0.01

    def test_pipe_period_two_L_over_a(self):
        # Chaudhry §3-2: pipe period T_p = 2L/a. L=1200 m, a=1200 m/s → 2 s.
        r = joukowsky_head_rise(V0=1.0, a=1200.0, L=1200.0, t_close=5.0)
        assert abs(r["T_pipe_s"] - 2.0) < 1e-9

    def test_rigid_column_slow_closure(self):
        # Rigid-column / Michaud slow closure: ΔH = 2·L·V0/(g·t_close).
        # L=1000 m, V0=2 m/s, t_close=10 s → ΔH = 40.79 m.
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=10.0)
        assert r["rapid_closure"] is False
        assert abs(r["dH_m"] - 40.789) < 0.01

    def test_moc_reservoir_pipe_valve_joukowsky_benchmark(self):
        # Wylie & Streeter §3.2 benchmark: frictionless reservoir-pipe-valve,
        # instantaneous closure → peak head at valve = H_res + a·V0/g and
        # trough = H_res − a·V0/g.  H_res=150 m, a=1000 m/s, V0=2 m/s
        # → peak 353.94 m, trough −53.94 m (analytic Joukowsky).
        r = moc_single_pipe(L=600.0, D=0.5, a=1000.0, V0=2.0, H_res=150.0,
                            f=0.0, n_reaches=20, t_total=16 * 600.0 / 1000.0,
                            t_close=1e-9)
        peak = 150.0 + 1000.0 * 2.0 / _G
        trough = 150.0 - 1000.0 * 2.0 / _G
        assert abs(r["H_envelope_max"][-1] - peak) < 0.5
        assert abs(r["H_envelope_min"][-1] - trough) < 0.5

    def test_moc_slow_closure_below_joukowsky(self):
        # A slow valve closure (t_close ≫ T_pipe) must keep the peak head
        # far below the Joukowsky limit (surge-protection principle,
        # Wylie & Streeter §3.1).
        L, a, V0, H_res = 600.0, 1200.0, 2.0, 150.0
        joukowsky_peak = H_res + a * V0 / _G  # ≈ 394.7 m
        r = moc_single_pipe(L=L, D=0.5, a=a, V0=V0, H_res=H_res,
                            f=0.0, n_reaches=20, t_total=40.0, t_close=20.0)
        assert r["H_envelope_max"][-1] < joukowsky_peak
        assert r["H_envelope_max"][-1] < H_res + 0.30 * (joukowsky_peak - H_res)

    def test_surge_tank_period_chaudhry(self):
        # Chaudhry §13-2 frictionless mass oscillation:
        # T = 2π·sqrt(L·A_tank/(g·A_pipe)); L=1000, A_pipe=2, A_tank=20
        # → T ≈ 200.64 s.
        r = surge_tank_oscillation(L=1000.0, A_pipe=2.0, A_tank=20.0,
                                   H0=50.0, V0=2.0)
        assert abs(r["T_osc_s"] - 200.641) < 0.05

    def test_surge_tank_amplitude_chaudhry(self):
        # Chaudhry §13-2 frictionless surge amplitude:
        # z_max = V0·sqrt(L·A_pipe/(g·A_tank)); V0=2 m/s, L=1000,
        # A_pipe=2, A_tank=20 → z_max ≈ 6.387 m.
        r = surge_tank_oscillation(L=1000.0, A_pipe=2.0, A_tank=20.0,
                                   H0=50.0, V0=2.0)
        assert abs(r["z_max_m"] - 6.3866) < 0.01

    def test_vapor_pressure_head_column_separation(self):
        # Column-separation threshold uses H_vapor = P_v/(ρ·g).
        # P_v=2338 Pa (water 20 °C), ρ=998 → H_vapor ≈ 0.239 m.
        # Low static head + large surge → trough below vapor head → flag.
        r = joukowsky_head_rise(V0=2.0, a=1200.0, L=1000.0, t_close=1e-6,
                                H0=10.0, P_vapor_Pa=2338.0, rho=998.0)
        assert r["column_sep"] is True  # H0 − ΔH ≈ 10 − 244.7 ≪ 0.239 m

    def test_safe_closure_time_rigid_column_inversion(self):
        # t_close_min = 2·L·V0/(g·ΔH_allow); L=1000, V0=2, ΔH_allow=50
        # → t_close_min ≈ 8.158 s (Wylie & Streeter §3.1 inversion).
        r = safe_closure_time(V0=2.0, a=1200.0, L=1000.0, H0=100.0,
                              dH_allowable=50.0)
        assert abs(r["t_close_min_s"] - 8.1577) < 0.01


# ===========================================================================
# 10. plugin registration
# ===========================================================================

class TestPluginRegistration:

    def test_waterhammer_in_tool_modules(self):
        from kerf_cad_core.plugin import _TOOL_MODULES
        assert "kerf_cad_core.waterhammer.tools" in _TOOL_MODULES

    def test_only_one_waterhammer_entry(self):
        from kerf_cad_core.plugin import _TOOL_MODULES
        count = sum(1 for m in _TOOL_MODULES if "waterhammer" in m)
        assert count == 1
