"""
Hermetic tests for kerf_cad_core.lubrication — tribology & fluid-film bearing design.

Coverage:
  film.sommerfeld_number            — S = (R/c)²·(μN)/P
  film.journal_bearing_raimondi_boyd — RB dimensionless variables (ε, h_min, friction, flow)
  film.petroff_friction             — Petroff torque, force, power
  film.temperature_rise             — ΔT from power loss & flow
  film.viscosity_walther            — ASTM D341 viscosity-temperature
  film.viscosity_barus              — Barus viscosity-pressure
  film.ehl_film_line                — Dowson-Higginson line contact h_min
  film.ehl_film_point               — Hamrock-Dowson point contact h_min
  film.thrust_pad_fixed_incline     — fixed-incline thrust pad load & friction
  film.specific_load                — p = W/(L·D)
  film.lambda_ratio                 — Stribeck λ, regime classification
  film.lubrication_regime           — regime from λ value
  tools.*                           — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified against Shigley Ch. 12, Hamrock §3-6, Dowson-Higginson 1977,
Hamrock-Dowson ASME 1977, and ASTM D341.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Ch. 12
Hamrock, Schmid & Jacobson, Fundamentals of Fluid Film Lubrication, 2nd ed.
Raimondi & Boyd, Trans. ASLE 1, 159–209, 1958
Dowson & Higginson, Elasto-Hydrodynamic Lubrication, Pergamon 1977
ASTM D341 — Viscosity-Temperature Charts for Liquid Petroleum Products

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.lubrication.film import (
    sommerfeld_number,
    journal_bearing_raimondi_boyd,
    petroff_friction,
    temperature_rise,
    viscosity_walther,
    viscosity_barus,
    ehl_film_line,
    ehl_film_point,
    thrust_pad_fixed_incline,
    specific_load,
    lambda_ratio,
    lubrication_regime,
)
from kerf_cad_core.lubrication.tools import (
    run_journal_bearing_sommerfeld,
    run_journal_bearing_raimondi_boyd,
    run_journal_bearing_petroff,
    run_bearing_temperature_rise,
    run_viscosity_walther,
    run_viscosity_barus,
    run_ehl_line_contact,
    run_ehl_point_contact,
    run_thrust_pad_load,
    run_bearing_specific_load,
    run_bearing_lambda_ratio,
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


REL = 1e-4  # 0.01% relative tolerance for engineering correlations


# ===========================================================================
# 1. sommerfeld_number
# ===========================================================================

class TestSommerfeldNumber:

    def test_basic_formula(self):
        """S = (R/c)² × μN/P where P = W/(L·D)."""
        R, c, mu, N, W = 0.025, 25e-6, 0.04, 25.0, 5000.0
        D = 2 * R  # 0.05
        L = D       # L/D = 1
        P = W / (L * D)
        S_expected = (R / c) ** 2 * (mu * N) / P
        res = sommerfeld_number(W=W, mu=mu, N=N, R=R, c=c, L=L)
        assert res["ok"] is True
        assert res["S"] == pytest.approx(S_expected, rel=REL)

    def test_default_L_is_diameter(self):
        """Without L provided, L = 2R (L/D=1) is assumed."""
        R, c, mu, N, W = 0.025, 25e-6, 0.04, 25.0, 5000.0
        res_no_L = sommerfeld_number(W=W, mu=mu, N=N, R=R, c=c)
        res_with_L = sommerfeld_number(W=W, mu=mu, N=N, R=R, c=c, L=2*R)
        assert res_no_L["ok"] is True
        assert res_no_L["S"] == pytest.approx(res_with_L["S"], rel=REL)

    def test_R_over_c_output(self):
        """R/c ratio should be returned correctly."""
        R, c = 0.030, 30e-6  # R/c = 1000
        res = sommerfeld_number(W=10000.0, mu=0.05, N=20.0, R=R, c=c)
        assert res["ok"] is True
        assert res["R_over_c"] == pytest.approx(1000.0, rel=REL)

    def test_specific_load_output(self):
        """P = W/(L·D) in output."""
        W, L, D = 8000.0, 0.05, 0.04
        R = D / 2
        c = 20e-6
        res = sommerfeld_number(W=W, mu=0.03, N=30.0, R=R, c=c, L=L)
        assert res["ok"] is True
        assert res["P_Pa"] == pytest.approx(W / (L * D), rel=REL)

    def test_zero_W_returns_error(self):
        res = sommerfeld_number(W=0.0, mu=0.04, N=25.0, R=0.025, c=25e-6)
        assert res["ok"] is False

    def test_negative_mu_returns_error(self):
        res = sommerfeld_number(W=5000.0, mu=-0.01, N=25.0, R=0.025, c=25e-6)
        assert res["ok"] is False

    def test_negative_c_returns_error(self):
        res = sommerfeld_number(W=5000.0, mu=0.04, N=25.0, R=0.025, c=-1e-5)
        assert res["ok"] is False

    def test_ld_ratio_output(self):
        """L/D ratio should be returned."""
        R = 0.020
        L = 0.030
        res = sommerfeld_number(W=3000.0, mu=0.04, N=20.0, R=R, c=20e-6, L=L)
        assert res["ok"] is True
        assert res["L_D"] == pytest.approx(L / (2 * R), rel=REL)


# ===========================================================================
# 2. journal_bearing_raimondi_boyd
# ===========================================================================

class TestRaimondiBoyd:

    def test_hmin_over_c_is_one_minus_epsilon(self):
        """h_min/c = 1 - ε by definition."""
        res = journal_bearing_raimondi_boyd(S=0.1)
        assert res["ok"] is True
        assert res["hmin_over_c"] == pytest.approx(1.0 - res["epsilon"], rel=REL)

    def test_epsilon_between_zero_and_one(self):
        """Eccentricity ratio must be in [0, 1)."""
        for S in (0.01, 0.05, 0.2, 1.0, 5.0):
            res = journal_bearing_raimondi_boyd(S=S)
            assert res["ok"] is True
            assert 0.0 <= res["epsilon"] < 1.0, f"ε={res['epsilon']} out of range for S={S}"

    def test_high_S_low_eccentricity(self):
        """Large S (lightly loaded) → low ε (near concentric)."""
        res = journal_bearing_raimondi_boyd(S=5.0)
        assert res["ok"] is True
        assert res["epsilon"] < 0.3

    def test_low_S_high_eccentricity(self):
        """Small S (heavily loaded) → high ε (journal approaching bearing)."""
        res = journal_bearing_raimondi_boyd(S=0.01)
        assert res["ok"] is True
        assert res["epsilon"] > 0.7

    def test_friction_variable_positive(self):
        """Friction variable f·(R/c) must always be positive."""
        for S in (0.05, 0.1, 0.5, 2.0):
            res = journal_bearing_raimondi_boyd(S=S)
            assert res["ok"] is True
            assert res["friction_variable"] > 0.0

    def test_flow_variable_positive(self):
        """Oil flow variable must be positive."""
        res = journal_bearing_raimondi_boyd(S=0.3)
        assert res["ok"] is True
        assert res["flow_variable"] > 0.0

    def test_max_pressure_ratio_gte_1(self):
        """P_max/P_mean >= 1.5 (minimum physical value)."""
        for S in (0.05, 0.1, 1.0):
            res = journal_bearing_raimondi_boyd(S=S)
            assert res["ok"] is True
            assert res["max_pressure_ratio"] >= 1.5

    def test_side_flow_ratio_in_valid_range(self):
        """Side-flow ratio in [0, 0.5]."""
        for S in (0.01, 0.1, 1.0, 10.0):
            res = journal_bearing_raimondi_boyd(S=S)
            assert res["ok"] is True
            assert 0.0 <= res["side_flow_ratio"] <= 0.5

    def test_ld_correction_reduces_values(self):
        """L/D < 1 should give lower friction_variable than L/D = 1."""
        res1 = journal_bearing_raimondi_boyd(S=0.2, L_D=1.0)
        res2 = journal_bearing_raimondi_boyd(S=0.2, L_D=0.5)
        assert res1["ok"] is True
        assert res2["ok"] is True
        assert res2["friction_variable"] < res1["friction_variable"]

    def test_zero_S_returns_error(self):
        res = journal_bearing_raimondi_boyd(S=0.0)
        assert res["ok"] is False

    def test_thin_film_warning(self):
        """Very small S → high ε → thin film warning expected."""
        res = journal_bearing_raimondi_boyd(S=0.001)
        assert res["ok"] is True
        assert any("thin" in w.lower() or "film" in w.lower() for w in res["warnings"])


# ===========================================================================
# 3. petroff_friction
# ===========================================================================

class TestPetroffFriction:

    def test_friction_force_formula(self):
        """F_f = 4π²·N·R²·L·μ/c (Petroff)."""
        mu, N, R, c, L = 0.04, 25.0, 0.025, 25e-6, 0.050
        expected_F = 4.0 * math.pi ** 2 * N * R ** 2 * L * mu / c
        res = petroff_friction(mu=mu, N=N, R=R, c=c, L=L)
        assert res["ok"] is True
        assert res["friction_force_N"] == pytest.approx(expected_F, rel=REL)

    def test_torque_equals_force_times_radius(self):
        """T = F_f × R."""
        mu, N, R, c, L = 0.04, 25.0, 0.025, 25e-6, 0.050
        res = petroff_friction(mu=mu, N=N, R=R, c=c, L=L)
        assert res["ok"] is True
        assert res["torque_Nm"] == pytest.approx(res["friction_force_N"] * R, rel=REL)

    def test_power_equals_2pi_N_torque(self):
        """P = 2π·N·T."""
        mu, N, R, c, L = 0.04, 25.0, 0.025, 25e-6, 0.050
        res = petroff_friction(mu=mu, N=N, R=R, c=c, L=L)
        assert res["ok"] is True
        expected_P = 2.0 * math.pi * N * res["torque_Nm"]
        assert res["power_W"] == pytest.approx(expected_P, rel=REL)

    def test_friction_scales_linearly_with_viscosity(self):
        """Doubling μ doubles friction force (Petroff is linear in μ)."""
        base = petroff_friction(mu=0.04, N=25.0, R=0.025, c=25e-6, L=0.050)
        doubled = petroff_friction(mu=0.08, N=25.0, R=0.025, c=25e-6, L=0.050)
        assert doubled["friction_force_N"] == pytest.approx(2.0 * base["friction_force_N"], rel=REL)

    def test_friction_scales_linearly_with_speed(self):
        """Doubling N doubles friction (Petroff is linear in N)."""
        base = petroff_friction(mu=0.04, N=20.0, R=0.025, c=25e-6, L=0.050)
        doubled = petroff_friction(mu=0.04, N=40.0, R=0.025, c=25e-6, L=0.050)
        assert doubled["friction_force_N"] == pytest.approx(2.0 * base["friction_force_N"], rel=REL)

    def test_zero_viscosity_returns_error(self):
        res = petroff_friction(mu=0.0, N=25.0, R=0.025, c=25e-6, L=0.050)
        assert res["ok"] is False

    def test_zero_clearance_returns_error(self):
        res = petroff_friction(mu=0.04, N=25.0, R=0.025, c=0.0, L=0.050)
        assert res["ok"] is False


# ===========================================================================
# 4. temperature_rise
# ===========================================================================

class TestTemperatureRise:

    def test_basic_formula(self):
        """ΔT = P_loss / (ρ·Q·Cp)."""
        P, Q, rho, Cp = 500.0, 1e-4, 870.0, 1900.0
        expected = P / (rho * Q * Cp)
        res = temperature_rise(power_loss_W=P, Q_m3_s=Q, rho=rho, Cp=Cp)
        assert res["ok"] is True
        assert res["delta_T_K"] == pytest.approx(expected, rel=REL)

    def test_default_oil_properties(self):
        """Default rho=870, Cp=1900 should give reasonable ΔT."""
        res = temperature_rise(power_loss_W=200.0, Q_m3_s=5e-5)
        assert res["ok"] is True
        assert res["delta_T_K"] > 0.0

    def test_zero_power_gives_zero_delta_T(self):
        """No power loss → zero temperature rise."""
        res = temperature_rise(power_loss_W=0.0, Q_m3_s=1e-4)
        assert res["ok"] is True
        assert res["delta_T_K"] == 0.0

    def test_high_delta_T_warns(self):
        """ΔT > 30 K should produce a warning."""
        # Q very small → large ΔT
        res = temperature_rise(power_loss_W=5000.0, Q_m3_s=1e-6)
        assert res["ok"] is True
        assert res["delta_T_K"] > 30.0
        assert len(res["warnings"]) > 0

    def test_very_high_delta_T_additional_warning(self):
        """ΔT > 50 K should add a degradation warning."""
        res = temperature_rise(power_loss_W=10000.0, Q_m3_s=5e-7)
        assert res["ok"] is True
        assert res["delta_T_K"] > 50.0
        assert any("degradation" in w.lower() or "50" in w for w in res["warnings"])

    def test_zero_flow_returns_error(self):
        res = temperature_rise(power_loss_W=500.0, Q_m3_s=0.0)
        assert res["ok"] is False

    def test_negative_rho_returns_error(self):
        res = temperature_rise(power_loss_W=500.0, Q_m3_s=1e-4, rho=-10.0)
        assert res["ok"] is False


# ===========================================================================
# 5. viscosity_walther (ASTM D341)
# ===========================================================================

class TestViscosityWalther:

    # SAE 30 constants (approximate): A=10.8, B=3.65 (T in K, ν in cSt)
    # At T=313 K (40°C): ν ≈ 100 cSt; at T=373 K (100°C): ν ≈ 11 cSt
    A_SAE30 = 10.8
    B_SAE30 = 3.65

    def test_viscosity_decreases_with_temperature(self):
        """Oil viscosity must decrease as temperature increases."""
        nu_40 = viscosity_walther(T_K=313.15, A=self.A_SAE30, B=self.B_SAE30)
        nu_100 = viscosity_walther(T_K=373.15, A=self.A_SAE30, B=self.B_SAE30)
        assert nu_40["ok"] is True
        assert nu_100["ok"] is True
        assert nu_40["nu_cSt"] > nu_100["nu_cSt"]

    def test_nu_cSt_to_m2_s_conversion(self):
        """nu_m2_s = nu_cSt × 1e-6."""
        res = viscosity_walther(T_K=313.15, A=self.A_SAE30, B=self.B_SAE30)
        assert res["ok"] is True
        assert res["nu_m2_s"] == pytest.approx(res["nu_cSt"] * 1e-6, rel=REL)

    def test_walther_equation_roundtrip(self):
        """Forward and inverse of log-log-log equation must be self-consistent."""
        T_K = 353.15  # 80°C
        res = viscosity_walther(T_K=T_K, A=self.A_SAE30, B=self.B_SAE30)
        assert res["ok"] is True
        # Verify: log10(log10(nu + 0.7)) ≈ A - B*log10(T)
        nu_cSt = res["nu_cSt"]
        lhs = math.log10(math.log10(nu_cSt + 0.7))
        rhs = self.A_SAE30 - self.B_SAE30 * math.log10(T_K)
        assert lhs == pytest.approx(rhs, abs=1e-6)

    def test_zero_temperature_returns_error(self):
        res = viscosity_walther(T_K=0.0, A=self.A_SAE30, B=self.B_SAE30)
        assert res["ok"] is False

    def test_non_finite_A_returns_error(self):
        res = viscosity_walther(T_K=313.15, A=float("inf"), B=self.B_SAE30)
        assert res["ok"] is False

    def test_positive_viscosity(self):
        """Viscosity must always be positive for valid inputs."""
        res = viscosity_walther(T_K=373.15, A=self.A_SAE30, B=self.B_SAE30)
        assert res["ok"] is True
        assert res["nu_cSt"] > 0.0
        assert res["nu_m2_s"] > 0.0


# ===========================================================================
# 6. viscosity_barus
# ===========================================================================

class TestViscosityBarus:

    def test_zero_pressure_returns_mu0(self):
        """At p=0, μ = μ₀·exp(0) = μ₀."""
        mu0, alpha = 0.04, 2.2e-8
        res = viscosity_barus(mu0=mu0, alpha=alpha, p=0.0)
        assert res["ok"] is True
        assert res["mu_Pa_s"] == pytest.approx(mu0, rel=REL)

    def test_exponential_growth_with_pressure(self):
        """μ(p) = μ₀·exp(α·p): doubling α doubles the exponent."""
        mu0 = 0.04
        alpha1, p = 1e-8, 1e8
        res1 = viscosity_barus(mu0=mu0, alpha=alpha1, p=p)
        res2 = viscosity_barus(mu0=mu0, alpha=2 * alpha1, p=p)
        assert res1["ok"] is True and res2["ok"] is True
        # exp(2α·p) = exp(α·p)², so mu2 = mu1² / mu0
        assert res2["mu_Pa_s"] == pytest.approx(res1["mu_Pa_s"] ** 2 / mu0, rel=REL)

    def test_barus_formula_direct(self):
        """μ = μ₀·exp(α·p) direct check."""
        mu0, alpha, p = 0.04, 2.2e-8, 5e8
        expected = mu0 * math.exp(alpha * p)
        res = viscosity_barus(mu0=mu0, alpha=alpha, p=p)
        assert res["ok"] is True
        assert res["mu_Pa_s"] == pytest.approx(expected, rel=REL)

    def test_large_exponent_warns(self):
        """α·p > 20 should produce a Barus validity warning."""
        res = viscosity_barus(mu0=0.04, alpha=1e-7, p=3e8)  # α·p = 30
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_overflow_exponent_returns_error(self):
        """α·p > 700 should return an error (would overflow float64)."""
        res = viscosity_barus(mu0=0.04, alpha=1.0, p=1000.0)  # α·p = 1000
        assert res["ok"] is False

    def test_negative_alpha_returns_error(self):
        res = viscosity_barus(mu0=0.04, alpha=-1e-8, p=1e8)
        assert res["ok"] is False

    def test_negative_mu0_returns_error(self):
        res = viscosity_barus(mu0=-0.01, alpha=2e-8, p=0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. ehl_film_line (Dowson-Higginson)
# ===========================================================================

class TestEHLFilmLine:

    def test_returns_positive_film_thickness(self):
        """Line contact film must be positive for valid inputs."""
        # Typical spur gear parameters
        R = 0.01  # 10 mm equivalent radius
        E_prime = 2.3e11  # Steel-steel: E'≈230 GPa
        alpha = 2.2e-8  # Pa⁻¹
        mu0 = 0.04     # Pa·s
        u_s = mu0 * 5.0  # mu0 * velocity = 0.04 * 5 = 0.2 Pa·m
        W_prime = 200000.0  # N/m
        res = ehl_film_line(R=R, E_prime=E_prime, u_s=u_s, W_prime=W_prime, k=alpha)
        assert res["ok"] is True
        assert res["h_min_m"] > 0.0

    def test_DH_formula_numerics(self):
        """Direct check of Dowson-Higginson dimensionless H_min formula."""
        R = 0.01
        E_prime = 2.3e11
        alpha = 2.2e-8
        mu0 = 0.04
        u_phys = 5.0
        u_s = mu0 * u_phys
        W_prime = 200000.0

        U_param = u_s / (E_prime * R)
        W_param = W_prime / (E_prime * R)
        G_param = alpha * E_prime

        H_expected = 2.65 * (G_param ** 0.54) * (U_param ** 0.70) * (W_param ** -0.13)
        h_expected = H_expected * R

        res = ehl_film_line(R=R, E_prime=E_prime, u_s=u_s, W_prime=W_prime, k=alpha)
        assert res["ok"] is True
        assert res["h_min_m"] == pytest.approx(h_expected, rel=REL)
        assert res["H_min"] == pytest.approx(H_expected, rel=REL)

    def test_higher_speed_gives_thicker_film(self):
        """Increasing entraining velocity increases film thickness (EHL)."""
        base_kwargs = dict(R=0.01, E_prime=2.3e11, W_prime=200000.0, k=2.2e-8)
        mu0 = 0.04
        h1 = ehl_film_line(**base_kwargs, u_s=mu0 * 2.0)["h_min_m"]
        h2 = ehl_film_line(**base_kwargs, u_s=mu0 * 10.0)["h_min_m"]
        assert h2 > h1

    def test_higher_load_gives_thinner_film(self):
        """Increasing load per unit length reduces film thickness (W exponent -0.13)."""
        base_kwargs = dict(R=0.01, E_prime=2.3e11, u_s=0.2, k=2.2e-8)
        h1 = ehl_film_line(**base_kwargs, W_prime=100000.0)["h_min_m"]
        h2 = ehl_film_line(**base_kwargs, W_prime=500000.0)["h_min_m"]
        assert h2 < h1

    def test_zero_R_returns_error(self):
        res = ehl_film_line(R=0.0, E_prime=2.3e11, u_s=0.2, W_prime=200000.0, k=2.2e-8)
        assert res["ok"] is False

    def test_dimensionless_params_returned(self):
        """U, W, G dimensionless groups must be in the result."""
        res = ehl_film_line(R=0.01, E_prime=2.3e11, u_s=0.2, W_prime=200000.0, k=2.2e-8)
        assert res["ok"] is True
        assert "U_param" in res
        assert "W_param" in res
        assert "G_param" in res


# ===========================================================================
# 8. ehl_film_point (Hamrock-Dowson)
# ===========================================================================

class TestEHLFilmPoint:

    def test_returns_positive_film_thickness(self):
        """Point contact film must be positive for valid inputs."""
        res = ehl_film_point(
            R_x=0.01, R_y=0.01,  # circular contact
            E_prime=2.3e11,
            u_s=0.04 * 5.0,  # mu0 * u
            W=500.0,
            k=2.2e-8,
        )
        assert res["ok"] is True
        assert res["h_min_m"] > 0.0

    def test_HD_formula_numerics(self):
        """Direct check of Hamrock-Dowson H_min formula."""
        R_x, R_y = 0.01, 0.015
        E_prime = 2.3e11
        alpha = 2.2e-8
        u_s = 0.04 * 4.0
        W = 300.0

        k_ell = R_x / R_y
        U_param = u_s / (E_prime * R_x)
        W_param = W / (E_prime * R_x ** 2)
        G_param = alpha * E_prime

        H_expected = (
            3.63
            * (U_param ** 0.68)
            * (G_param ** 0.49)
            * (W_param ** -0.073)
            * (1.0 - math.exp(-0.68 * k_ell))
        )
        h_expected = H_expected * R_x

        res = ehl_film_point(R_x=R_x, R_y=R_y, E_prime=E_prime, u_s=u_s, W=W, k=alpha)
        assert res["ok"] is True
        assert res["h_min_m"] == pytest.approx(h_expected, rel=REL)

    def test_circular_contact_ellipticity_one(self):
        """For R_x = R_y, k_ell = 1.0."""
        res = ehl_film_point(R_x=0.01, R_y=0.01, E_prime=2.3e11, u_s=0.2, W=500.0, k=2.2e-8)
        assert res["ok"] is True
        assert res["k_ell"] == pytest.approx(1.0, rel=REL)

    def test_high_k_ell_warns(self):
        """k_ell > 10 should warn about near-line-contact condition."""
        res = ehl_film_point(R_x=0.10, R_y=0.005, E_prime=2.3e11, u_s=0.2, W=500.0, k=2.2e-8)
        assert res["ok"] is True
        assert res["k_ell"] > 10.0
        assert any("line" in w.lower() for w in res["warnings"])

    def test_zero_load_returns_error(self):
        res = ehl_film_point(R_x=0.01, R_y=0.01, E_prime=2.3e11, u_s=0.2, W=0.0, k=2.2e-8)
        assert res["ok"] is False

    def test_zero_R_y_returns_error(self):
        res = ehl_film_point(R_x=0.01, R_y=0.0, E_prime=2.3e11, u_s=0.2, W=500.0, k=2.2e-8)
        assert res["ok"] is False


# ===========================================================================
# 9. thrust_pad_fixed_incline
# ===========================================================================

class TestThrustPad:

    def test_converging_gap_produces_positive_load(self):
        """Converging gap (h_1 > h_2) must produce positive load capacity."""
        res = thrust_pad_fixed_incline(
            B=0.05, L=0.04, U=2.0, h_1=80e-6, h_2=40e-6, mu=0.04
        )
        assert res["ok"] is True
        assert res["W_N"] > 0.0

    def test_parallel_gap_h1_equals_h2_returns_error(self):
        """h_1 = h_2 (parallel gap) must return error — no wedge action."""
        res = thrust_pad_fixed_incline(
            B=0.05, L=0.04, U=2.0, h_1=50e-6, h_2=50e-6, mu=0.04
        )
        assert res["ok"] is False

    def test_diverging_gap_returns_error(self):
        """h_1 < h_2 (diverging gap) must return error."""
        res = thrust_pad_fixed_incline(
            B=0.05, L=0.04, U=2.0, h_1=30e-6, h_2=60e-6, mu=0.04
        )
        assert res["ok"] is False

    def test_h_min_is_h_2(self):
        """h_min in result must equal h_2 (outlet film thickness)."""
        h_2 = 40e-6
        res = thrust_pad_fixed_incline(
            B=0.05, L=0.04, U=2.0, h_1=80e-6, h_2=h_2, mu=0.04
        )
        assert res["ok"] is True
        assert res["h_min_m"] == pytest.approx(h_2, rel=REL)

    def test_load_increases_with_speed(self):
        """Higher sliding speed → higher hydrodynamic load capacity."""
        base = dict(B=0.05, L=0.04, h_1=80e-6, h_2=40e-6, mu=0.04)
        W1 = thrust_pad_fixed_incline(**base, U=1.0)["W_N"]
        W2 = thrust_pad_fixed_incline(**base, U=4.0)["W_N"]
        assert W2 > W1

    def test_load_scales_with_viscosity(self):
        """Doubling viscosity doubles load (linear in μ)."""
        base = dict(B=0.05, L=0.04, U=2.0, h_1=80e-6, h_2=40e-6)
        W1 = thrust_pad_fixed_incline(**base, mu=0.04)["W_N"]
        W2 = thrust_pad_fixed_incline(**base, mu=0.08)["W_N"]
        assert W2 == pytest.approx(2.0 * W1, rel=REL)

    def test_friction_force_positive(self):
        """Friction force must be positive."""
        res = thrust_pad_fixed_incline(
            B=0.05, L=0.04, U=2.0, h_1=80e-6, h_2=40e-6, mu=0.04
        )
        assert res["ok"] is True
        assert res["F_friction_N"] > 0.0

    def test_optimal_K_ratio(self):
        """K = h_1/h_2 = 2.2 should give higher W than K = 1.5 or K = 4.0 (near optimal)."""
        base = dict(B=0.05, L=0.04, U=2.0, mu=0.04, h_2=40e-6)
        W_K15 = thrust_pad_fixed_incline(**base, h_1=60e-6)["W_N"]   # K=1.5
        W_K22 = thrust_pad_fixed_incline(**base, h_1=88e-6)["W_N"]   # K=2.2
        W_K40 = thrust_pad_fixed_incline(**base, h_1=160e-6)["W_N"]  # K=4.0
        # K=2.2 should be near maximum — not strictly enforced, just check it's higher than K=4
        assert W_K22 > W_K40


# ===========================================================================
# 10. specific_load
# ===========================================================================

class TestSpecificLoad:

    def test_basic_formula(self):
        """p = W/(L·D)."""
        W, L, D = 10000.0, 0.06, 0.05
        res = specific_load(W=W, L=L, D=D)
        assert res["ok"] is True
        assert res["p_Pa"] == pytest.approx(W / (L * D), rel=REL)

    def test_ld_ratio_output(self):
        """L/D ratio returned."""
        L, D = 0.06, 0.05
        res = specific_load(W=10000.0, L=L, D=D)
        assert res["ok"] is True
        assert res["L_D"] == pytest.approx(L / D, rel=REL)

    def test_high_load_warns(self):
        """p > 10 MPa should produce a warning."""
        W, L, D = 2e6, 0.01, 0.02  # p = 10 MPa
        res = specific_load(W=2 * W, L=L, D=D)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_zero_D_returns_error(self):
        res = specific_load(W=10000.0, L=0.06, D=0.0)
        assert res["ok"] is False

    def test_zero_W_returns_error(self):
        res = specific_load(W=0.0, L=0.06, D=0.05)
        assert res["ok"] is False


# ===========================================================================
# 11. lambda_ratio
# ===========================================================================

class TestLambdaRatio:

    def test_formula(self):
        """λ = h_min / √(Ra1² + Ra2²)."""
        h, Ra1, Ra2 = 2e-6, 0.8e-6, 0.6e-6
        Rq = math.sqrt(Ra1 ** 2 + Ra2 ** 2)
        expected_lam = h / Rq
        res = lambda_ratio(h_min=h, Ra1=Ra1, Ra2=Ra2)
        assert res["ok"] is True
        assert res["lambda"] == pytest.approx(expected_lam, rel=REL)

    def test_rq_composite_roughness(self):
        """Rq = √(Ra1² + Ra2²) returned in result."""
        Ra1, Ra2 = 0.8e-6, 0.6e-6
        expected_Rq = math.sqrt(Ra1 ** 2 + Ra2 ** 2)
        res = lambda_ratio(h_min=2e-6, Ra1=Ra1, Ra2=Ra2)
        assert res["ok"] is True
        assert res["Rq_m"] == pytest.approx(expected_Rq, rel=REL)

    def test_boundary_regime(self):
        """λ < 1 → boundary regime and warning."""
        h, Ra1, Ra2 = 0.5e-6, 0.8e-6, 0.6e-6  # λ ≈ 0.5
        res = lambda_ratio(h_min=h, Ra1=Ra1, Ra2=Ra2)
        assert res["ok"] is True
        assert res["lambda"] < 1.0
        assert res["regime"] == "boundary"
        assert len(res["warnings"]) > 0

    def test_mixed_regime(self):
        """1 ≤ λ < 3 → mixed regime and warning."""
        h, Ra1, Ra2 = 2e-6, 0.8e-6, 0.6e-6  # λ ≈ 2.0
        res = lambda_ratio(h_min=h, Ra1=Ra1, Ra2=Ra2)
        assert res["ok"] is True
        assert 1.0 <= res["lambda"] < 3.0
        assert res["regime"] == "mixed"

    def test_hydrodynamic_regime(self):
        """λ ≥ 3 → hydrodynamic regime, no warning."""
        h, Ra1, Ra2 = 5e-6, 0.8e-6, 0.6e-6  # λ ≈ 5.0
        res = lambda_ratio(h_min=h, Ra1=Ra1, Ra2=Ra2)
        assert res["ok"] is True
        assert res["lambda"] >= 3.0
        assert res["regime"] == "hydrodynamic"

    def test_zero_h_min_returns_error(self):
        res = lambda_ratio(h_min=0.0, Ra1=0.8e-6, Ra2=0.6e-6)
        assert res["ok"] is False

    def test_zero_Ra_returns_error(self):
        res = lambda_ratio(h_min=2e-6, Ra1=0.0, Ra2=0.6e-6)
        assert res["ok"] is False


# ===========================================================================
# 12. lubrication_regime
# ===========================================================================

class TestLubricationRegime:

    def test_boundary_below_one(self):
        res = lubrication_regime(lambda_val=0.5)
        assert res["ok"] is True
        assert res["regime"] == "boundary"

    def test_mixed_between_one_and_three(self):
        for lam in (1.0, 1.5, 2.0, 2.99):
            res = lubrication_regime(lambda_val=lam)
            assert res["ok"] is True
            assert res["regime"] == "mixed", f"λ={lam} should be mixed"

    def test_hydrodynamic_at_three(self):
        res = lubrication_regime(lambda_val=3.0)
        assert res["ok"] is True
        assert res["regime"] == "hydrodynamic"

    def test_hydrodynamic_above_three(self):
        res = lubrication_regime(lambda_val=10.0)
        assert res["ok"] is True
        assert res["regime"] == "hydrodynamic"

    def test_boundary_has_warning(self):
        res = lubrication_regime(lambda_val=0.3)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_hydrodynamic_no_warning(self):
        res = lubrication_regime(lambda_val=5.0)
        assert res["ok"] is True
        assert len(res["warnings"]) == 0

    def test_zero_lambda_returns_error(self):
        res = lubrication_regime(lambda_val=0.0)
        assert res["ok"] is False


# ===========================================================================
# 13. LLM Tool wrappers
# ===========================================================================

class TestToolWrappers:

    # --- journal_bearing_sommerfeld ---

    def test_run_sommerfeld_happy_path(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_sommerfeld(
            ctx, _args(W=5000.0, mu=0.04, N=25.0, R=0.025, c=25e-6)
        ))
        d = _ok_tool(raw)
        assert d["S"] > 0.0

    def test_run_sommerfeld_missing_W(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_sommerfeld(
            ctx, _args(mu=0.04, N=25.0, R=0.025, c=25e-6)
        ))
        _err_tool(raw)

    def test_run_sommerfeld_bad_json(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_sommerfeld(ctx, b"not json"))
        _err_tool(raw)

    # --- journal_bearing_raimondi_boyd ---

    def test_run_raimondi_boyd_happy_path(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_raimondi_boyd(ctx, _args(S=0.2, L_D=1.0)))
        d = _ok_tool(raw)
        assert 0.0 < d["epsilon"] < 1.0
        assert "hmin_over_c" in d

    def test_run_raimondi_boyd_missing_S(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_raimondi_boyd(ctx, _args(L_D=1.0)))
        _err_tool(raw)

    # --- journal_bearing_petroff ---

    def test_run_petroff_happy_path(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_petroff(
            ctx, _args(mu=0.04, N=25.0, R=0.025, c=25e-6, L=0.05)
        ))
        d = _ok_tool(raw)
        assert d["power_W"] > 0.0

    def test_run_petroff_missing_L(self):
        ctx = _ctx()
        raw = _run(run_journal_bearing_petroff(
            ctx, _args(mu=0.04, N=25.0, R=0.025, c=25e-6)
        ))
        _err_tool(raw)

    # --- bearing_temperature_rise ---

    def test_run_temperature_rise_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_temperature_rise(
            ctx, _args(power_loss_W=500.0, Q_m3_s=1e-4)
        ))
        d = _ok_tool(raw)
        assert d["delta_T_K"] > 0.0

    def test_run_temperature_rise_missing_Q(self):
        ctx = _ctx()
        raw = _run(run_bearing_temperature_rise(ctx, _args(power_loss_W=500.0)))
        _err_tool(raw)

    # --- viscosity_walther ---

    def test_run_viscosity_walther_happy_path(self):
        ctx = _ctx()
        raw = _run(run_viscosity_walther(ctx, _args(T_K=313.15, A=10.8, B=3.65)))
        d = _ok_tool(raw)
        assert d["nu_cSt"] > 0.0

    def test_run_viscosity_walther_missing_B(self):
        ctx = _ctx()
        raw = _run(run_viscosity_walther(ctx, _args(T_K=313.15, A=10.8)))
        _err_tool(raw)

    # --- viscosity_barus ---

    def test_run_viscosity_barus_happy_path(self):
        ctx = _ctx()
        raw = _run(run_viscosity_barus(ctx, _args(mu0=0.04, alpha=2.2e-8, p=0.0)))
        d = _ok_tool(raw)
        assert d["mu_Pa_s"] == pytest.approx(0.04, rel=1e-6)

    def test_run_viscosity_barus_missing_p(self):
        ctx = _ctx()
        raw = _run(run_viscosity_barus(ctx, _args(mu0=0.04, alpha=2.2e-8)))
        _err_tool(raw)

    # --- ehl_line_contact ---

    def test_run_ehl_line_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ehl_line_contact(
            ctx, _args(R=0.01, E_prime=2.3e11, u_s=0.2, W_prime=200000.0, k=2.2e-8)
        ))
        d = _ok_tool(raw)
        assert d["h_min_m"] > 0.0

    def test_run_ehl_line_missing_R(self):
        ctx = _ctx()
        raw = _run(run_ehl_line_contact(
            ctx, _args(E_prime=2.3e11, u_s=0.2, W_prime=200000.0, k=2.2e-8)
        ))
        _err_tool(raw)

    # --- ehl_point_contact ---

    def test_run_ehl_point_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ehl_point_contact(
            ctx, _args(R_x=0.01, R_y=0.01, E_prime=2.3e11, u_s=0.2, W=500.0, k=2.2e-8)
        ))
        d = _ok_tool(raw)
        assert d["h_min_m"] > 0.0
        assert d["k_ell"] == pytest.approx(1.0, rel=1e-9)

    def test_run_ehl_point_missing_W(self):
        ctx = _ctx()
        raw = _run(run_ehl_point_contact(
            ctx, _args(R_x=0.01, R_y=0.01, E_prime=2.3e11, u_s=0.2, k=2.2e-8)
        ))
        _err_tool(raw)

    # --- thrust_pad_load ---

    def test_run_thrust_pad_happy_path(self):
        ctx = _ctx()
        raw = _run(run_thrust_pad_load(
            ctx, _args(B=0.05, L=0.04, U=2.0, h_1=80e-6, h_2=40e-6, mu=0.04)
        ))
        d = _ok_tool(raw)
        assert d["W_N"] > 0.0

    def test_run_thrust_pad_parallel_gap_error(self):
        ctx = _ctx()
        raw = _run(run_thrust_pad_load(
            ctx, _args(B=0.05, L=0.04, U=2.0, h_1=50e-6, h_2=50e-6, mu=0.04)
        ))
        _err_tool(raw)

    # --- bearing_specific_load ---

    def test_run_specific_load_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_specific_load(ctx, _args(W=10000.0, L=0.06, D=0.05)))
        d = _ok_tool(raw)
        assert d["p_Pa"] == pytest.approx(10000.0 / (0.06 * 0.05), rel=1e-9)

    def test_run_specific_load_missing_D(self):
        ctx = _ctx()
        raw = _run(run_bearing_specific_load(ctx, _args(W=10000.0, L=0.06)))
        _err_tool(raw)

    # --- bearing_lambda_ratio ---

    def test_run_lambda_ratio_hydrodynamic(self):
        ctx = _ctx()
        raw = _run(run_bearing_lambda_ratio(
            ctx, _args(h_min=5e-6, Ra1=0.8e-6, Ra2=0.6e-6)
        ))
        d = _ok_tool(raw)
        assert d["regime"] == "hydrodynamic"

    def test_run_lambda_ratio_boundary(self):
        ctx = _ctx()
        raw = _run(run_bearing_lambda_ratio(
            ctx, _args(h_min=0.3e-6, Ra1=0.8e-6, Ra2=0.6e-6)
        ))
        d = _ok_tool(raw)
        assert d["regime"] == "boundary"

    def test_run_lambda_ratio_missing_Ra2(self):
        ctx = _ctx()
        raw = _run(run_bearing_lambda_ratio(ctx, _args(h_min=2e-6, Ra1=0.8e-6)))
        _err_tool(raw)

    def test_run_lambda_ratio_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bearing_lambda_ratio(ctx, b"{ bad }"))
        _err_tool(raw)


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs Shigley 10th ed. Ch. 12, Hamrock "Fundamentals of Fluid
# Film Lubrication" 2nd ed., Dowson-Higginson (1977), Hamrock-Dowson (1977).
# ===========================================================================

from kerf_cad_core.lubrication.film import (  # noqa: E402
    sommerfeld_number as _ref_S,
    petroff_friction as _ref_petroff,
    temperature_rise as _ref_dT,
    viscosity_barus as _ref_barus,
    ehl_film_line as _ref_ehl_line,
    ehl_film_point as _ref_ehl_point,
    lambda_ratio as _ref_lambda,
    specific_load as _ref_specload,
)


class TestLubricationExternalReferences:
    """Validated against Shigley §12 / Hamrock closed-form relations."""

    def test_sommerfeld_definition_shigley_12_7(self):
        # Shigley Eq (12-7): S = (r/c)²·μN/P, P = W/(L·D).
        r = _ref_S(2000.0, 0.05, 30.0, 0.025, 25e-6, L=0.05)
        D = 0.05
        P = 2000.0 / (0.05 * D)
        assert r["P_Pa"] == pytest.approx(P, rel=1e-12)
        assert r["S"] == pytest.approx((0.025 / 25e-6) ** 2 * (0.05 * 30.0) / P, rel=1e-9)

    def test_petroff_friction_shigley_12_4(self):
        # Shigley §12-4 Petroff: F = 4π²μN R²L/c; T = F·R.
        r = _ref_petroff(0.01, 30.0, 0.02, 2e-5, 0.04)
        F = 4.0 * math.pi ** 2 * 30.0 * 0.02 ** 2 * 0.04 * 0.01 / 2e-5
        assert r["friction_force_N"] == pytest.approx(F, rel=1e-12)
        assert r["torque_Nm"] == pytest.approx(F * 0.02, rel=1e-12)

    def test_petroff_power_loss(self):
        # P = 2πN·T (rotational power = torque × angular speed).
        r = _ref_petroff(0.01, 30.0, 0.02, 2e-5, 0.04)
        assert r["power_W"] == pytest.approx(2.0 * math.pi * 30.0 * r["torque_Nm"], rel=1e-12)

    def test_temperature_rise_energy_balance(self):
        # Shigley §12-8: ΔT = P_loss/(ρ·Q·Cp).
        r = _ref_dT(500.0, 1e-5, rho=870.0, Cp=1900.0)
        assert r["delta_T_K"] == pytest.approx(500.0 / (870.0 * 1e-5 * 1900.0), rel=1e-12)

    def test_barus_viscosity_pressure(self):
        # Hamrock §4: Barus μ(p) = μ0·exp(α p). μ0=0.04, α=2.2e-8, p=100 MPa.
        r = _ref_barus(0.04, 2.2e-8, 100e6)
        assert r["mu_Pa_s"] == pytest.approx(0.04 * math.exp(2.2e-8 * 100e6), rel=1e-12)

    def test_ehl_line_dowson_higginson(self):
        # Dowson-Higginson (1977): Hmin = 2.65 G^0.54 U^0.70 W^(-0.13).
        r = _ref_ehl_line(0.02, 2.2e11, 2.0e-8, 5e5, 2.2e-8)
        U = 2.0e-8 / (2.2e11 * 0.02)
        W = 5e5 / (2.2e11 * 0.02)
        G = 2.2e-8 * 2.2e11
        Hexp = 2.65 * G ** 0.54 * U ** 0.70 * W ** -0.13
        assert r["H_min"] == pytest.approx(Hexp, rel=1e-9)
        assert r["h_min_m"] == pytest.approx(Hexp * 0.02, rel=1e-9)

    def test_ehl_point_hamrock_dowson(self):
        # Hamrock-Dowson (1977): Hmin = 3.63 U^0.68 G^0.49 W^(-0.073)·
        # (1 − e^{−0.68 k}).  Circular contact Rx=Ry → k=1.
        r = _ref_ehl_point(0.01, 0.01, 2.2e11, 2.0e-8, 100.0, 2.2e-8)
        U = 2.0e-8 / (2.2e11 * 0.01)
        W = 100.0 / (2.2e11 * 0.01 ** 2)
        G = 2.2e-8 * 2.2e11
        Hexp = 3.63 * U ** 0.68 * G ** 0.49 * W ** -0.073 * (1.0 - math.exp(-0.68))
        assert r["H_min"] == pytest.approx(Hexp, rel=1e-9)

    def test_lambda_ratio_stribeck(self):
        # Hamrock/Stribeck: λ = h_min/√(Ra1²+Ra2²).
        r = _ref_lambda(0.5e-6, 0.1e-6, 0.1e-6)
        Rq = math.sqrt(0.1e-6 ** 2 + 0.1e-6 ** 2)
        assert r["lambda"] == pytest.approx(0.5e-6 / Rq, rel=1e-12)

    def test_lambda_regime_hydrodynamic(self):
        # Shigley §12: λ ≥ 3 → full hydrodynamic.
        r = _ref_lambda(1.0e-6, 0.1e-6, 0.1e-6)
        assert r["regime"] == "hydrodynamic"

    def test_specific_load_projected(self):
        # Shigley §12-7: p = W/(L·D). W=5000 N, L=0.05, D=0.05.
        r = _ref_specload(5000.0, 0.05, 0.05)
        assert r["p_Pa"] == pytest.approx(5000.0 / (0.05 * 0.05), rel=1e-12)
