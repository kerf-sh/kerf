"""
Tests for kerf_systems.extended_components

Covers all 16 new components:
  Mechanical: Mass, Spring, Damper, Lever, Gear, Bearing
  Hydraulic:  Orifice, Valve, Accumulator, Pump_constant_flow
  Pneumatic:  Pneumatic_cylinder
  Thermal-fluid: Heat_exchanger_eNTU
  Control:    Lead_lag, Deadband, Saturation, Rate_limiter

Also includes a coupled simulation validation (mass-spring-damper step response).
"""

from __future__ import annotations

import math
import pytest


# ===========================================================================
# Mechanical
# ===========================================================================

class TestMass:
    def test_residuals_at_equilibrium(self):
        from kerf_systems.extended_components import Mass
        m = Mass(m=2.0, F_in=10.0, x0=0.0, v0=0.0)
        # At t=0: pos=0, vel=0; dpos=0=vel ✓; dvel=F/m=5 → residual[1]=2*5-10=0
        res = m.residuals(0.0, [0.0, 0.0], [0.0, 5.0])
        assert abs(res[0]) < 1e-12   # dpos - vel
        assert abs(res[1]) < 1e-12   # m*dvel - F

    def test_bad_m(self):
        from kerf_systems.extended_components import Mass
        with pytest.raises(ValueError):
            Mass(m=0.0)

    def test_n_vars(self):
        from kerf_systems.extended_components import Mass
        m = Mass(m=1.0)
        assert m.n_vars == 2
        assert "pos" in m.var_names
        assert "vel" in m.var_names

    def test_callable_force(self):
        from kerf_systems.extended_components import Mass
        m = Mass(m=1.0, F_in=lambda t: 5.0 * t)
        # At t=2, F=10, m*dvel=10 → dvel=10
        res = m.residuals(2.0, [0.0, 0.0], [0.0, 10.0])
        assert abs(res[1]) < 1e-10


class TestSpring:
    def test_hookes_law(self):
        from kerf_systems.extended_components import Spring
        s = Spring(k=100.0)
        # x_a=0.05, x_b=0 → F=5 N
        res = s.residuals(0.0, [0.05, 0.0, 5.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_compression_force(self):
        from kerf_systems.extended_components import Spring
        s = Spring(k=200.0)
        # x_a=0, x_b=0.01 → F=-2
        res = s.residuals(0.0, [0.0, 0.01, -2.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_bad_k(self):
        from kerf_systems.extended_components import Spring
        with pytest.raises(ValueError):
            Spring(k=0.0)

    def test_n_vars(self):
        from kerf_systems.extended_components import Spring
        s = Spring(k=10.0)
        assert s.n_vars == 3


class TestDamper:
    def test_damping_force(self):
        from kerf_systems.extended_components import Damper
        d = Damper(b=50.0)
        # v_a=2, v_b=0.5 → F=75
        res = d.residuals(0.0, [2.0, 0.5, 75.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_zero_velocity_diff(self):
        from kerf_systems.extended_components import Damper
        d = Damper(b=50.0)
        res = d.residuals(0.0, [1.0, 1.0, 0.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_bad_b(self):
        from kerf_systems.extended_components import Damper
        with pytest.raises(ValueError):
            Damper(b=0.0)


class TestLever:
    def test_force_and_displacement(self):
        from kerf_systems.extended_components import Lever
        lv = Lever(l1=0.5, l2=1.0)
        # F_out = F_in * (l1/l2) = 100 * 0.5 = 50
        # x_out = x_in * (l2/l1) = 0.01 * 2 = 0.02
        res = lv.residuals(0.0, [100.0, 50.0, 0.01, 0.02], [0.0] * 4)
        assert abs(res[0]) < 1e-10
        assert abs(res[1]) < 1e-10

    def test_bad_arms(self):
        from kerf_systems.extended_components import Lever
        with pytest.raises(ValueError):
            Lever(l1=0.0, l2=1.0)
        with pytest.raises(ValueError):
            Lever(l1=1.0, l2=0.0)

    def test_n_vars(self):
        from kerf_systems.extended_components import Lever
        lv = Lever(l1=1.0, l2=2.0)
        assert lv.n_vars == 4


class TestGear:
    def test_speed_reduction(self):
        from kerf_systems.extended_components import Gear
        g = Gear(ratio=4.0)
        # omega_out = omega_in / 4 = 100/4 = 25
        # T_out = T_in * 4 = 10*4 = 40
        res = g.residuals(0.0, [100.0, 25.0, 10.0, 40.0], [0.0] * 4)
        assert abs(res[0]) < 1e-10
        assert abs(res[1]) < 1e-10

    def test_bad_ratio(self):
        from kerf_systems.extended_components import Gear
        with pytest.raises(ValueError):
            Gear(ratio=0.0)


class TestBearing:
    def test_viscous_only(self):
        from kerf_systems.extended_components import Bearing
        b = Bearing(mu_c=0.0, T_normal=0.0, b_v=2.0)
        # T_friction = 0 + 2 * omega = 2*5 = 10
        res = b.residuals(0.0, [5.0, 10.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-10

    def test_zero_omega(self):
        from kerf_systems.extended_components import Bearing
        b = Bearing(mu_c=0.1, T_normal=100.0, b_v=0.5)
        # At omega=0: tanh(0)=0 → T_friction = 0
        res = b.residuals(0.0, [0.0, 0.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_bad_omega_eps(self):
        from kerf_systems.extended_components import Bearing
        with pytest.raises(ValueError):
            Bearing(omega_eps=0.0)


# ===========================================================================
# Hydraulic (extended)
# ===========================================================================

class TestOrifice:
    def test_flow_positive(self):
        from kerf_systems.extended_components import Orifice
        o = Orifice(Cd=1.0, A=1e-4, rho=1000.0)
        # ΔP = 1e4 Pa → Q = A * sqrt(2*ΔP/rho) = 1e-4 * sqrt(20) ≈ 4.47e-4
        dp = 1e4
        q_exp = 1e-4 * math.sqrt(2 * dp / 1000.0)
        res = o.residuals(0.0, [dp, 0.0, q_exp], [0.0, 0.0, 0.0])
        assert abs(res[0]) < q_exp * 0.02  # within 2% (regularisation)

    def test_flow_zero_dp(self):
        from kerf_systems.extended_components import Orifice
        o = Orifice(Cd=0.611, A=1e-5)
        res = o.residuals(0.0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-6

    def test_bad_params(self):
        from kerf_systems.extended_components import Orifice
        with pytest.raises(ValueError):
            Orifice(Cd=0.0, A=1e-4)
        with pytest.raises(ValueError):
            Orifice(Cd=0.611, A=0.0)


class TestValve:
    def test_fully_open(self):
        from kerf_systems.extended_components import Valve
        v = Valve(Cd=1.0, A_max=1e-4, rho=1000.0)
        dp = 1e4
        q_exp = 1.0 * 1e-4 * math.sqrt(2 * dp / 1000.0)
        # opening=1, full open
        res = v.residuals(0.0, [dp, 0.0, 1.0, q_exp], [0.0, 0.0, 0.0, 0.0])
        assert abs(res[0]) < q_exp * 0.02

    def test_fully_closed(self):
        from kerf_systems.extended_components import Valve
        v = Valve(Cd=0.7, A_max=1e-4)
        # opening=0 → Q=0
        res = v.residuals(0.0, [1e5, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-6

    def test_bad_params(self):
        from kerf_systems.extended_components import Valve
        with pytest.raises(ValueError):
            Valve(Cd=0.0)
        with pytest.raises(ValueError):
            Valve(A_max=0.0)


class TestAccumulator:
    def test_zero_liquid_at_precharge(self):
        from kerf_systems.extended_components import Accumulator
        acc = Accumulator(V0=0.001, P0=1e6, n=1.4)
        # V_liq=0 → V_gas=V0 → P=P0
        # dV_liq/dt = Q_in = 0
        res = acc.residuals(0.0, [1e6, 0.0, 0.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12  # continuity: 0 - 0
        assert abs(res[1]) < 1e-6   # pressure: P0 - P0

    def test_pressure_rises_with_volume(self):
        from kerf_systems.extended_components import Accumulator
        acc = Accumulator(V0=0.001, P0=1e6, n=1.4)
        # V_liq=0.0001 → V_gas=0.0009 → P = 1e6*(0.001/0.0009)^1.4
        V_liq = 0.0001
        V_gas = 0.001 - V_liq
        P_exp = 1e6 * (0.001 / V_gas) ** 1.4
        res = acc.residuals(0.0, [P_exp, V_liq, 0.0], [0.0, 0.0, 0.0])
        assert abs(res[1]) < 1e-3 * P_exp  # pressure match within 0.1%

    def test_bad_params(self):
        from kerf_systems.extended_components import Accumulator
        with pytest.raises(ValueError):
            Accumulator(V0=0.0)
        with pytest.raises(ValueError):
            Accumulator(V0=0.001, P0=0.0)


class TestPump_constant_flow:
    def test_flow_prescribed(self):
        from kerf_systems.extended_components import Pump_constant_flow
        p = Pump_constant_flow(Q_set=1e-3)
        res = p.residuals(0.0, [0.0, 1e5, 1e-3], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_callable_flow(self):
        from kerf_systems.extended_components import Pump_constant_flow
        p = Pump_constant_flow(Q_set=lambda t: 2e-3 * t)
        # At t=1: Q_set=2e-3
        res = p.residuals(1.0, [0.0, 1e5, 2e-3], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12


# ===========================================================================
# Pneumatic
# ===========================================================================

class TestPneumatic_cylinder:
    def test_extension_force(self):
        from kerf_systems.extended_components import Pneumatic_cylinder
        cyl = Pneumatic_cylinder(bore=0.1, stroke=0.3, rod=0.04)
        A_bore = math.pi / 4 * 0.1 ** 2
        A_ann = math.pi / 4 * (0.1 ** 2 - 0.04 ** 2)
        P_e, P_r = 6e5, 1e5
        F_ext_exp = P_e * A_bore - P_r * A_ann
        F_ret_exp = P_r * A_ann - P_e * A_bore
        res = cyl.residuals(0.0, [P_e, P_r, F_ext_exp, F_ret_exp], [0.0] * 4)
        assert abs(res[0]) < 1e-6
        assert abs(res[1]) < 1e-6

    def test_bad_params(self):
        from kerf_systems.extended_components import Pneumatic_cylinder
        with pytest.raises(ValueError):
            Pneumatic_cylinder(bore=0.0, stroke=0.3, rod=0.04)
        with pytest.raises(ValueError):
            # rod >= bore
            Pneumatic_cylinder(bore=0.1, stroke=0.3, rod=0.1)
        with pytest.raises(ValueError):
            Pneumatic_cylinder(bore=0.1, stroke=0.0, rod=0.04)

    def test_n_vars(self):
        from kerf_systems.extended_components import Pneumatic_cylinder
        cyl = Pneumatic_cylinder(bore=0.05, stroke=0.2, rod=0.02)
        assert cyl.n_vars == 4


# ===========================================================================
# Thermal-fluid
# ===========================================================================

class TestHeat_exchanger_eNTU:
    def test_outlet_temps_balanced(self):
        """Equal capacity rates: ε = NTU / (1 + NTU)."""
        from kerf_systems.extended_components import Heat_exchanger_eNTU
        # Equal flow rates and Cp
        hx = Heat_exchanger_eNTU(UA=1000.0, m_dot_h=0.5, m_dot_c=0.5, Cp_h=4186.0, Cp_c=4186.0)
        T_h_in, T_c_in = 400.0, 300.0
        Q_max = hx._C_min * (T_h_in - T_c_in)
        Q_exp = hx._eps * Q_max
        C = hx.m_dot_h * hx.Cp_h
        T_h_out_exp = T_h_in - Q_exp / C
        T_c_out_exp = T_c_in + Q_exp / C
        res = hx.residuals(
            0.0,
            [T_h_in, T_c_in, T_h_out_exp, T_c_out_exp, Q_exp],
            [0.0] * 5,
        )
        for r in res:
            assert abs(r) < 1e-6

    def test_effectiveness_range(self):
        from kerf_systems.extended_components import Heat_exchanger_eNTU
        hx = Heat_exchanger_eNTU(UA=500.0, m_dot_h=0.3, m_dot_c=0.4, Cp_h=4186.0, Cp_c=4186.0)
        assert 0.0 < hx._eps < 1.0

    def test_bad_params(self):
        from kerf_systems.extended_components import Heat_exchanger_eNTU
        with pytest.raises(ValueError):
            Heat_exchanger_eNTU(UA=0.0, m_dot_h=0.5, m_dot_c=0.5)
        with pytest.raises(ValueError):
            Heat_exchanger_eNTU(UA=1000.0, m_dot_h=0.0, m_dot_c=0.5)


# ===========================================================================
# Control (extended)
# ===========================================================================

class TestLead_lag:
    def test_steady_state_gain_one(self):
        """At DC (s=0), G = 1 for all T_lead, T_lag."""
        from kerf_systems.extended_components import Lead_lag
        ll = Lead_lag(T_lead=0.5, T_lag=2.0)
        # Steady state: dx_f/dt=0, T_lag*0 + x_f = u → x_f=u
        # y = x_f + ratio*(u-x_f) = u + ratio*0 = u
        # residuals at [u=1, x_f=1, y=1], dx=[0,0,0]:
        res = ll.residuals(0.0, [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12  # T_lag*0 + 1 - 1 = 0
        assert abs(res[1]) < 1e-12  # y - x_f - ratio*(u-x_f) = 1-1-0 = 0

    def test_bad_T_lag(self):
        from kerf_systems.extended_components import Lead_lag
        with pytest.raises(ValueError):
            Lead_lag(T_lead=0.5, T_lag=0.0)

    def test_n_vars(self):
        from kerf_systems.extended_components import Lead_lag
        ll = Lead_lag(T_lead=0.1, T_lag=1.0)
        assert ll.n_vars == 3


class TestDeadband:
    def test_within_band_output_zero(self):
        from kerf_systems.extended_components import Deadband
        db = Deadband(band=0.2)
        # u=0 → y≈0
        res = db.residuals(0.0, [0.0, 0.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-9

    def test_outside_band_passthrough(self):
        from kerf_systems.extended_components import Deadband
        db = Deadband(band=0.2)
        # u=10 (>> band) → y ≈ u - d (very close to u for large u)
        # tanh(10/0.1) ≈ 1 → y ≈ 10 - 0.1
        u = 10.0
        d = 0.1
        y_exp = u - d * math.tanh(u / (d + 1e-9))
        res = db.residuals(0.0, [u, y_exp], [0.0, 0.0])
        assert abs(res[0]) < 1e-8

    def test_zero_band(self):
        from kerf_systems.extended_components import Deadband
        db = Deadband(band=0.0)
        res = db.residuals(0.0, [5.0, 5.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-9

    def test_bad_band(self):
        from kerf_systems.extended_components import Deadband
        with pytest.raises(ValueError):
            Deadband(band=-1.0)


class TestSaturation:
    def test_center_passthrough(self):
        from kerf_systems.extended_components import Saturation
        sat = Saturation(lower=-1.0, upper=1.0)
        # u=0 → y ≈ 0 (mid of [-1,1])
        res = sat.residuals(0.0, [0.0, 0.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-9

    def test_upper_clamp(self):
        from kerf_systems.extended_components import Saturation
        sat = Saturation(lower=-5.0, upper=5.0)
        # u=100 >> upper → y ≈ 5
        span = 10.0
        mid = 0.0
        y_exp = mid + 0.5 * span * math.tanh((100.0 - mid) / (0.5 * span))
        res = sat.residuals(0.0, [100.0, y_exp], [0.0, 0.0])
        assert abs(res[0]) < 1e-9
        assert y_exp < 5.0 + 0.01  # near upper

    def test_bad_limits(self):
        from kerf_systems.extended_components import Saturation
        with pytest.raises(ValueError):
            Saturation(lower=1.0, upper=1.0)
        with pytest.raises(ValueError):
            Saturation(lower=2.0, upper=1.0)


class TestRate_limiter:
    def test_slow_input_passes_through(self):
        from kerf_systems.extended_components import Rate_limiter
        rl = Rate_limiter(slew_max=10.0)
        # du/dt=1 (well within slew_max=10) → dy/dt ≈ 1
        # tanh(1/10) ≈ 0.0997; 10*tanh(0.1)=0.997 → residual = 1 - 0.997 ≈ 0.003
        # For near-linear regime: if du/dt << slew_max, clamped_rate ≈ du/dt
        du = 0.01  # << slew_max
        clamped = 10.0 * math.tanh(du / 10.0)
        res = rl.residuals(0.0, [0.0, 0.0], [du, clamped])
        assert abs(res[0]) < 1e-12

    def test_fast_input_clamped(self):
        from kerf_systems.extended_components import Rate_limiter
        rl = Rate_limiter(slew_max=1.0)
        # du/dt=1000 >> slew_max=1 → clamped_rate ≈ slew_max = 1
        du = 1000.0
        clamped = 1.0 * math.tanh(du / 1.0)
        res = rl.residuals(0.0, [0.0, 0.0], [du, clamped])
        assert abs(res[0]) < 1e-12
        assert abs(clamped - 1.0) < 0.001  # very close to slew_max

    def test_bad_slew_max(self):
        from kerf_systems.extended_components import Rate_limiter
        with pytest.raises(ValueError):
            Rate_limiter(slew_max=0.0)


# ===========================================================================
# Registry
# ===========================================================================

class TestRegistry:
    def test_list_components(self):
        from kerf_systems.extended_components import list_extended_components
        names = list_extended_components()
        assert len(names) == 16
        assert "Mass" in names
        assert "Heat_exchanger_eNTU" in names

    def test_instantiate(self):
        from kerf_systems.extended_components import instantiate_component
        spring = instantiate_component("Spring", k=100.0)
        assert spring.n_vars == 3

    def test_unknown_component(self):
        from kerf_systems.extended_components import instantiate_component
        with pytest.raises(KeyError):
            instantiate_component("NonExistent")


# ===========================================================================
# Coupled simulation validation
# ===========================================================================

class TestCoupledSimulation:
    """
    Validate a mass-spring-damper system under a step force using the
    real DAE solver, then check the analytic steady-state.

    System: m*x'' + b*x' + k*x = F_step
    Analytic steady-state: x_ss = F_step / k
    """

    def test_mass_spring_damper_step_response(self):
        from kerf_systems.solver.dae import solve_system

        m_val = 1.0
        k_val = 4.0
        b_val = 2.0   # critically overdamped for fast settling
        F_val = 8.0

        # States: [x (position), v (velocity)]
        # Equations:
        #   dx/dt - v = 0          (kinematic)
        #   m*dv/dt + b*v + k*x - F = 0  (Newton II)
        def F_msd_forced(t, x, dx):
            pos, vel = x[0], x[1]
            dpos, dvel = dx[0], dx[1]
            return [
                dpos - vel,
                m_val * dvel + b_val * vel + k_val * pos - F_val,
            ]

        x0 = [0.0, 0.0]
        dx0 = [0.0, F_val / m_val]
        result = solve_system(F_msd_forced, (0.0, 20.0), x0, dx0)

        assert result.converged, f"Solver did not converge: {result.warnings}"

        # Steady-state position
        x_ss_analytic = F_val / k_val   # = 2.0
        x_final = result.x[-1][0]
        assert abs(x_final - x_ss_analytic) < 0.01, (
            f"Steady-state mismatch: got {x_final:.4f}, expected {x_ss_analytic:.4f}"
        )

    def test_pump_orifice_pressure_transient(self):
        """
        Pump (constant Q) → Accumulator (hydraulic capacitance) → Orifice → tank (P=0).

        At steady-state: Q_pump = Q_orifice
          Q_set = Cd * A * sqrt(2 * P_ss / rho)
          P_ss = rho / 2 * (Q_set / (Cd * A))^2

        Use hydraulic capacitance: C_h * dP/dt = Q_pump - Q_orifice
        """
        from kerf_systems.solver.dae import solve_system

        Q_set = 1e-4       # m³/s
        Cd = 0.611
        A = 5e-5           # m²
        rho = 870.0
        C_h = 1e-9         # hydraulic capacitance [m³/Pa]

        P_ss_analytic = rho / 2.0 * (Q_set / (Cd * A)) ** 2

        # States: [P]
        # ODE: C_h * dP/dt = Q_pump - Q_orifice(P)
        def F_sys(t, x, dx):
            P = x[0]
            dP = dx[0]
            eps = 1.0  # Pa
            Q_out = Cd * A * math.sqrt(2.0 * math.sqrt(P * P + eps * eps) / rho)
            if P < 0:
                Q_out = -Q_out
            return [C_h * dP - (Q_set - Q_out)]

        # Need enough time for the RC-like pressure transient to settle.
        # Time constant ≈ C_h * (dQ_out/dP)^{-1} at P_ss.
        # dQ_out/dP = Cd * A / sqrt(2*P_ss/rho) at steady state.
        # For P_ss≈4661, dQ/dP ≈ Cd*A*sqrt(rho/(2*P_ss)) ≈ 1.6e-8
        # tau ≈ C_h / (dQ/dP) ≈ 1e-9 / 1.6e-8 ≈ 0.063 s → simulate 5 tau = 0.4 s
        result = solve_system(F_sys, (0.0, 1.0), [0.0], [Q_set / C_h])
        assert result.converged

        P_final = result.x[-1][0]
        rel_err = abs(P_final - P_ss_analytic) / P_ss_analytic
        assert rel_err < 0.05, (
            f"Pump-orifice pressure: got {P_final:.1f} Pa, expected {P_ss_analytic:.1f} Pa"
        )

    def test_heat_exchanger_energy_balance(self):
        """
        Verify that Q_transferred = ε * C_min * ΔT_max  and energy balance holds.
        """
        from kerf_systems.extended_components import Heat_exchanger_eNTU

        hx = Heat_exchanger_eNTU(
            UA=2000.0,
            m_dot_h=0.4,
            m_dot_c=0.6,
            Cp_h=4186.0,
            Cp_c=4186.0,
        )
        T_h_in = 380.0
        T_c_in = 290.0
        C_h = hx.m_dot_h * hx.Cp_h
        C_c = hx.m_dot_c * hx.Cp_c
        Q_exp = hx._eps * hx._C_min * (T_h_in - T_c_in)
        T_h_out = T_h_in - Q_exp / C_h
        T_c_out = T_c_in + Q_exp / C_c
        res = hx.residuals(0.0, [T_h_in, T_c_in, T_h_out, T_c_out, Q_exp], [0.0] * 5)
        assert all(abs(r) < 1e-4 for r in res)
        # Energy balance: heat lost by hot = heat gained by cold
        Q_hot  = C_h * (T_h_in - T_h_out)
        Q_cold = C_c * (T_c_out - T_c_in)
        assert abs(Q_hot - Q_cold) / Q_hot < 1e-6
