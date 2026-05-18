"""
Tests for kerf-1dsim.

Oracles:
  - RC circuit step response matches analytic V(t) = V0*(1 - exp(-t/RC)) to 1%
  - Mass-spring oscillation period matches 2*pi*sqrt(m/k) to 1%
  - Minimal Modelica parser handles a trivial RC model
"""

from __future__ import annotations

import math
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / abs(expected)


# ---------------------------------------------------------------------------
# Component unit tests
# ---------------------------------------------------------------------------

class TestComponents:
    def test_resistor_ohm(self):
        from kerf_1dsim.components import Resistor
        r = Resistor(R=100.0)
        # v = R*i  →  residual = v - R*i = 0
        res = r.equations(0.0, [100.0, 1.0], [0.0, 0.0])
        assert len(res) == 1
        assert abs(res[0]) < 1e-12

    def test_resistor_bad_R(self):
        from kerf_1dsim.components import Resistor
        with pytest.raises(ValueError):
            Resistor(R=0.0)

    def test_capacitor_residual(self):
        from kerf_1dsim.components import Capacitor
        c = Capacitor(C=1e-6)
        # C*dv/dt - i = 0  →  1e-6 * 1e6 - 1.0 = 0
        res = c.equations(0.0, [5.0, 1.0], [1e6, 0.0])
        assert abs(res[0]) < 1e-10

    def test_inductor_residual(self):
        from kerf_1dsim.components import Inductor
        l = Inductor(L=1e-3)
        # L*di/dt - v = 0  →  1e-3 * 1000 - 1.0 = 0
        res = l.equations(0.0, [1.0, 0.0], [0.0, 1000.0])
        assert abs(res[0]) < 1e-10

    def test_mass_spring_residuals(self):
        from kerf_1dsim.components import MassSpring
        ms = MassSpring(m=1.0, k=4.0)
        # At equilibrium: q=0, v=0, dq=0, dv=0
        res = ms.equations(0.0, [0.0, 0.0], [0.0, 0.0])
        assert len(res) == 2
        for r in res:
            assert abs(r) < 1e-12

    def test_damper_residual(self):
        from kerf_1dsim.components import Damper
        d = Damper(b=5.0)
        # F_d = b * v_rel = 5*2 = 10
        res = d.equations(0.0, [2.0, 10.0], [0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_thermal_conductor(self):
        from kerf_1dsim.components import ThermalConductor
        tc = ThermalConductor(G=2.0)
        # Q = G*(T_a - T_b) = 2*(100-20) = 160
        res = tc.equations(0.0, [100.0, 20.0, 160.0], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12

    def test_fluid_resistor(self):
        from kerf_1dsim.components import FluidResistor
        fr = FluidResistor(Rf=1e6)
        # q = (p_in - p_out)/Rf = (1e5-0)/1e6 = 0.1
        res = fr.equations(0.0, [1e5, 0.0, 0.1], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-12


# ---------------------------------------------------------------------------
# Causality / BLT
# ---------------------------------------------------------------------------

class TestCausality:
    def test_blt_chain(self):
        """Simple chain: eq0 uses var0, eq1 uses var0+var1."""
        from kerf_1dsim.causality import causalise
        incidence = [
            {0},        # eq0 uses var0
            {0, 1},     # eq1 uses var0, var1
        ]
        cs = causalise(n_eq=2, n_var=2, incidence=incidence)
        assert len(cs.blocks) == 2
        assert len(cs.matching) == 2

    def test_single_equation(self):
        from kerf_1dsim.causality import causalise
        cs = causalise(n_eq=1, n_var=1, incidence=[{0}])
        assert len(cs.blocks) == 1
        assert cs.matching[0] == 0

    def test_loop_detection(self):
        """Mutual dependency → algebraic loop."""
        from kerf_1dsim.causality import causalise
        # eq0 uses var0 + var1, eq1 uses var0 + var1
        incidence = [{0, 1}, {0, 1}]
        cs = causalise(n_eq=2, n_var=2, incidence=incidence)
        # Should detect a loop
        loop_blocks = [b for b in cs.blocks if b.is_loop]
        assert len(loop_blocks) >= 1


# ---------------------------------------------------------------------------
# Solver: Newton + BDF-1
# ---------------------------------------------------------------------------

class TestSolverNewton:
    def test_lu_solve(self):
        from kerf_1dsim.solver import _lu_solve
        # 2x + y = 5, x + 3y = 10  →  x=1, y=3
        A = [[2.0, 1.0], [1.0, 3.0]]
        b = [5.0, 10.0]
        x = _lu_solve(A, b)
        assert x is not None
        assert abs(x[0] - 1.0) < 1e-10
        assert abs(x[1] - 3.0) < 1e-10

    def test_singular_returns_none(self):
        from kerf_1dsim.solver import _lu_solve
        A = [[1.0, 1.0], [1.0, 1.0]]
        b = [2.0, 3.0]
        assert _lu_solve(A, b) is None

    def test_newton_quadratic(self):
        from kerf_1dsim.solver import _newton_solve
        # Solve x^2 - 4 = 0, starting from x = [1.5] → x = [2.0]
        def F(x):
            return [x[0] ** 2 - 4.0]
        sol, ok = _newton_solve(F, [1.5])
        assert ok
        assert abs(sol[0] - 2.0) < 1e-8


class TestForwardEuler:
    def test_exponential_decay(self):
        """dx/dt = -x  →  x(t) = exp(-t); check at t=1."""
        from kerf_1dsim.solver import integrate_ode

        def f(t, x):
            return [-x[0]]

        result = integrate_ode(f, t_span=(0.0, 1.0), x0=[1.0], h=1e-4)
        assert result.converged
        x_final = result.x[-1][0]
        x_analytic = math.exp(-1.0)
        assert _relative_error(x_final, x_analytic) < 0.01  # 1% tolerance


# ---------------------------------------------------------------------------
# Oracle 1: RC circuit step response
# ---------------------------------------------------------------------------

class TestRCCircuit:
    """
    Series RC circuit driven by step voltage V0.
    Analytic: V_C(t) = V0 * (1 - exp(-t/RC))
    """

    @pytest.mark.parametrize("R, C, V0", [
        (1e3, 1e-6, 1.0),   # tau = 1 ms
        (10e3, 100e-9, 5.0), # tau = 1 ms
        (1e6, 1e-9, 12.0),  # tau = 1 ms
    ])
    def test_rc_step_response(self, R, C, V0):
        from kerf_1dsim.solver import integrate_dae

        tau = R * C
        t_end = 5 * tau
        h = tau / 500

        def F_rc(t, x, dx):
            v_C, i = x[0], x[1]
            dv_C = dx[0]
            return [
                C * dv_C - i,        # C dv/dt = i
                v_C + R * i - V0,    # KVL
            ]

        x0 = [0.0, V0 / R]
        dx0 = [V0 / (R * C), 0.0]

        result = integrate_dae(F_rc, t_span=(0.0, t_end), x0=x0, dx0=dx0, h=h)
        assert result.converged, f"Solver did not converge: {result.warnings}"

        # Sample at t ≈ tau (63.2%), 2*tau, 3*tau
        for n_tau in [1, 2, 3]:
            t_check = n_tau * tau
            # Find closest step
            idx = min(range(len(result.t)), key=lambda i: abs(result.t[i] - t_check))
            t_actual = result.t[idx]
            v_C_sim = result.x[idx][0]
            v_C_analytic = V0 * (1.0 - math.exp(-t_actual / tau))
            err = _relative_error(v_C_sim, v_C_analytic)
            assert err < 0.01, (
                f"RC(R={R},C={C},V0={V0}) at t={n_tau}*tau: "
                f"sim={v_C_sim:.6f}, analytic={v_C_analytic:.6f}, err={err*100:.2f}%"
            )

    def test_rc_final_voltage(self):
        """At t >> tau, V_C should approach V0."""
        from kerf_1dsim.solver import integrate_dae

        R, C, V0 = 1e3, 1e-6, 1.0
        tau = R * C
        t_end = 10 * tau
        h = tau / 200

        def F_rc(t, x, dx):
            v_C, i = x[0], x[1]
            return [C * dx[0] - i, v_C + R * i - V0]

        result = integrate_dae(F_rc, (0.0, t_end), [0.0, V0 / R], [V0 / (R * C), 0.0], h)
        v_C_final = result.x[-1][0]
        assert _relative_error(v_C_final, V0) < 0.01


# ---------------------------------------------------------------------------
# Oracle 2: Mass-spring oscillation period
# ---------------------------------------------------------------------------

class TestMassSpring:
    """
    Undamped mass-spring: m*x'' + k*x = 0
    Analytic period: T = 2*pi*sqrt(m/k)
    """

    @pytest.mark.parametrize("m, k", [
        (1.0, 1.0),       # T = 2*pi ≈ 6.283 s
        (4.0, 16.0),      # T = 2*pi*sqrt(4/16) = pi s
        (0.1, 10.0),      # T = 2*pi*sqrt(0.01) ≈ 0.628 s
    ])
    def test_oscillation_period(self, m, k):
        from kerf_1dsim.solver import integrate_dae

        T_analytic = 2 * math.pi * math.sqrt(m / k)
        # Run for 2 full periods
        t_end = 2.0 * T_analytic
        h = T_analytic / 1000

        q0 = 1.0  # initial displacement
        v0 = 0.0

        def F_ms(t, x, dx):
            q, v = x[0], x[1]
            dq, dv = dx[0], dx[1]
            return [dq - v, m * dv + k * q]

        result = integrate_dae(
            F_ms, t_span=(0.0, t_end),
            x0=[q0, v0], dx0=[v0, -k * q0 / m], h=h,
        )
        assert result.converged, f"mass-spring solver not converged: {result.warnings}"

        # The oscillator starts at q0=1.0, v0=0 → q(t) = cos(omega*t).
        # The first zero crossing (positive→zero) is at T/4.
        # We measure T by finding the SECOND zero crossing (negative→zero)
        # which occurs at 3*T/4, giving T = (4/3) * t_cross_2.
        # Alternatively: count T as distance between first and second positive
        # zero crossings.  Simpler: find the first time q returns to q0 > 0.95*q0
        # after the minimum.
        #
        # Most robust: find two consecutive positive-going zero crossings.
        t_arr = result.t
        q_arr = [row[0] for row in result.x]

        zero_crossings = []
        for i in range(1, len(t_arr)):
            # positive-going: q goes from negative to positive
            if q_arr[i - 1] < 0 and q_arr[i] >= 0:
                t0_, t1_ = t_arr[i - 1], t_arr[i]
                q0_, q1_ = q_arr[i - 1], q_arr[i]
                t_cross = t0_ - q0_ * (t1_ - t0_) / (q1_ - q0_)
                zero_crossings.append(t_cross)
            if len(zero_crossings) == 2:
                break

        if len(zero_crossings) < 2:
            # Fallback: use first negative-going crossing as T/2
            neg_crossings = []
            for i in range(1, len(t_arr)):
                if q_arr[i - 1] > 0 and q_arr[i] <= 0:
                    t0_, t1_ = t_arr[i - 1], t_arr[i]
                    q0_, q1_ = q_arr[i - 1], q_arr[i]
                    t_cross = t0_ - q0_ * (t1_ - t0_) / (q1_ - q0_)
                    neg_crossings.append(t_cross)
                if len(neg_crossings) == 2:
                    break
            assert len(neg_crossings) >= 2, "No two negative zero crossings found"
            T_sim = neg_crossings[1] - neg_crossings[0]
        else:
            T_sim = zero_crossings[1] - zero_crossings[0]

        err = _relative_error(T_sim, T_analytic)
        assert err < 0.01, (
            f"mass-spring(m={m},k={k}): T_sim={T_sim:.4f}, "
            f"T_analytic={T_analytic:.4f}, err={err*100:.2f}%"
        )

    def test_energy_conservation(self):
        """Total mechanical energy E = 0.5*m*v^2 + 0.5*k*q^2 should be conserved."""
        from kerf_1dsim.solver import integrate_dae

        m, k = 1.0, 4.0
        q0, v0 = 1.0, 0.0
        T = 2 * math.pi * math.sqrt(m / k)
        h = T / 2000

        def F_ms(t, x, dx):
            q, v = x[0], x[1]
            return [dx[0] - v, m * dx[1] + k * q]

        result = integrate_dae(F_ms, (0.0, T), [q0, v0], [0.0, -k * q0 / m], h)
        E0 = 0.5 * k * q0 ** 2
        for i, row in enumerate(result.x):
            q, v = row[0], row[1]
            E = 0.5 * m * v ** 2 + 0.5 * k * q ** 2
            err = abs(E - E0) / E0
            assert err < 0.02, f"Energy drift at step {i}: E={E:.6f}, E0={E0:.6f}"


# ---------------------------------------------------------------------------
# Oracle 3: Modelica parser
# ---------------------------------------------------------------------------

class TestModelicaParser:
    _RC_SOURCE = """
    model RCCircuit
      parameter Real R = 1000.0;
      parameter Real C = 1e-6;
      parameter Real V0 = 1.0;
      Real v_C(start = 0.0);
      Real i(start = 0.001);
    equation
      der(v_C) = i / C;
      v_C + R * i = V0;
    end RCCircuit;
    """

    def test_parse_rc_model_name(self):
        from kerf_1dsim.parser import parse_model
        model = parse_model(self._RC_SOURCE)
        assert model.name == "RCCircuit"

    def test_parse_rc_parameters(self):
        from kerf_1dsim.parser import parse_model
        model = parse_model(self._RC_SOURCE)
        params = {v.name: v for v in model.vars if v.is_parameter}
        assert "R" in params
        assert "C" in params
        assert "V0" in params
        assert abs(params["R"].value - 1000.0) < 1e-9
        assert abs(params["C"].value - 1e-6) < 1e-14
        assert abs(params["V0"].value - 1.0) < 1e-12

    def test_parse_rc_state_vars(self):
        from kerf_1dsim.parser import parse_model
        model = parse_model(self._RC_SOURCE)
        state_vars = [v.name for v in model.vars if not v.is_parameter]
        assert "v_C" in state_vars
        assert "i" in state_vars

    def test_parse_rc_equations(self):
        from kerf_1dsim.parser import parse_model
        model = parse_model(self._RC_SOURCE)
        assert len(model.equations) == 2
        der_eqs = [eq for eq in model.equations if eq.is_der]
        assert len(der_eqs) == 1
        assert der_eqs[0].der_var == "v_C"

    def test_parse_error_no_model(self):
        from kerf_1dsim.parser import parse_model
        with pytest.raises(ValueError, match="No 'model"):
            parse_model("// just a comment\nReal x;")

    def test_build_simulation_runs(self):
        """build_simulation should produce a valid residual callable."""
        from kerf_1dsim.parser import parse_model, build_simulation
        model = parse_model(self._RC_SOURCE)
        F, x0, dx0, var_names, params = build_simulation(model)
        assert "v_C" in var_names
        assert "i" in var_names
        # F should be callable and return 2 residuals
        res = F(0.0, x0, dx0)
        assert len(res) == 2

    def test_modelica_rc_simulation(self):
        """
        End-to-end: parse RC model → integrate → check V_C(tau) ≈ V0*(1-1/e).
        """
        from kerf_1dsim.parser import parse_model, build_simulation
        from kerf_1dsim.solver import integrate_dae

        # Use an RC model written with der() syntax
        source = """
        model RCStep
          parameter Real R = 1000.0;
          parameter Real C = 0.001;
          parameter Real V0 = 5.0;
          Real v_C(start = 0.0);
          Real i(start = 0.005);
        equation
          der(v_C) = i / C;
          v_C + R * i = V0;
        end RCStep;
        """
        model = parse_model(source)
        F, x0, dx0, var_names, params = build_simulation(model)

        R = params["R"]
        C = params["C"]
        V0 = params["V0"]
        tau = R * C
        t_end = 3 * tau
        h = tau / 500

        result = integrate_dae(F, (0.0, t_end), x0, dx0, h)
        assert result.converged

        # At t = tau, V_C ≈ V0*(1 - 1/e) ≈ 0.6321 * V0
        idx = min(range(len(result.t)), key=lambda i: abs(result.t[i] - tau))
        v_C_idx = var_names.index("v_C")
        v_C_sim = result.x[idx][v_C_idx]
        v_C_analytic = V0 * (1.0 - math.exp(-1.0))
        err = _relative_error(v_C_sim, v_C_analytic)
        assert err < 0.01, (
            f"Modelica RC sim: v_C({tau:.3f}s)={v_C_sim:.4f}, "
            f"analytic={v_C_analytic:.4f}, err={err*100:.2f}%"
        )


# ---------------------------------------------------------------------------
# Misc integration tests
# ---------------------------------------------------------------------------

class TestRLCIntegration:
    def test_rlc_resonance(self):
        """
        Under-damped RLC circuit should exhibit oscillation.
        R=10, L=1mH, C=1uF → omega_0 = 1/sqrt(LC) ≈ 31623 rad/s
        """
        from kerf_1dsim.solver import integrate_dae

        R, L, C_val, V0 = 10.0, 1e-3, 1e-6, 1.0
        omega0 = 1.0 / math.sqrt(L * C_val)
        T0 = 2 * math.pi / omega0
        t_end = 3 * T0
        h = T0 / 2000

        def F_rlc(t, x, dx):
            v_C, i_L = x[0], x[1]
            dv_C, di_L = dx[0], dx[1]
            return [
                C_val * dv_C - i_L,
                L * di_L + R * i_L + v_C - V0,
            ]

        result = integrate_dae(F_rlc, (0.0, t_end), [0.0, 0.0], [0.0, V0 / L], h)
        assert result.converged
        # In an under-damped circuit, v_C should exceed V0 at some point
        v_C_max = max(row[0] for row in result.x)
        assert v_C_max > V0 * 1.01, f"Expected overshoot above V0, got max={v_C_max}"


class TestThermalConductorSteadyState:
    def test_steady_state_heat_flow(self):
        """Q_steady = G*(T_a - T_b)."""
        from kerf_1dsim.components import ThermalConductor
        G = 5.0
        T_a, T_b = 100.0, 20.0
        tc = ThermalConductor(G=G)
        Q_expected = G * (T_a - T_b)
        res = tc.equations(0.0, [T_a, T_b, Q_expected], [0.0, 0.0, 0.0])
        assert abs(res[0]) < 1e-10
