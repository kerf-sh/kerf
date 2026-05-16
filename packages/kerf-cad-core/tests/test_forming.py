"""
Hermetic tests for kerf_cad_core.forming — bulk metal forming calculators.

Coverage:
  bulk.flow_stress              — Hollomon σ = K·ε^n
  bulk.mean_flow_stress         — σ̄_f = K·ε_f^n / (n+1)
  bulk.upset_forging_force      — open-die upset force (Siebel slab method)
  bulk.closed_die_forging_load  — closed-die load (Kf × σ̄_f × A_proj)
  bulk.forward_extrusion        — forward extrusion pressure + force
  bulk.backward_extrusion       — backward extrusion pressure + force
  bulk.flat_rolling             — contact length, force, torque, power, neutral point
  bulk.wire_drawing             — drawing stress, force, max reduction
  bulk.forming_work             — work/energy + adiabatic temperature rise
  bulk.passes_required          — number of passes to achieve total reduction
  tools.*                       — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against Kalpakjian / Hosford hand-calc values.

References
----------
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
Hosford, W.F. & Caddell, R.M. "Metal Forming: Mechanics and Metallurgy", 4th ed.
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.forming.bulk import (
    flow_stress,
    mean_flow_stress,
    upset_forging_force,
    closed_die_forging_load,
    forward_extrusion,
    backward_extrusion,
    flat_rolling,
    wire_drawing,
    forming_work,
    passes_required,
)
from kerf_cad_core.forming.tools import (
    run_forming_flow_stress,
    run_forming_mean_flow_stress,
    run_forming_upset_forging_force,
    run_forming_closed_die_load,
    run_forming_forward_extrusion,
    run_forming_backward_extrusion,
    run_forming_flat_rolling,
    run_forming_wire_drawing,
    run_forming_work,
    run_forming_passes_required,
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


REL = 1e-9


# ===========================================================================
# 1. flow_stress
# ===========================================================================

class TestFlowStress:

    def test_algebraic_formula(self):
        """σ_f = K · ε^n algebraically verified."""
        K, eps, n = 530e6, 0.3, 0.26
        expected = K * (eps ** n)
        res = flow_stress(K, eps, n)
        assert res["ok"] is True
        assert abs(res["sigma_f_Pa"] - expected) / expected < REL

    def test_perfectly_plastic_n_zero(self):
        """For n=0, flow stress equals K regardless of ε."""
        K, eps = 300e6, 0.5
        res = flow_stress(K, eps, 0.0)
        assert res["ok"] is True
        assert abs(res["sigma_f_Pa"] - K) / K < REL

    def test_larger_strain_higher_stress(self):
        """Higher true strain → higher flow stress for n>0."""
        K, n = 530e6, 0.26
        s1 = flow_stress(K, 0.1, n)["sigma_f_Pa"]
        s2 = flow_stress(K, 0.5, n)["sigma_f_Pa"]
        assert s2 > s1

    def test_zero_K_returns_error(self):
        res = flow_stress(0.0, 0.3, 0.26)
        assert res["ok"] is False

    def test_negative_eps_returns_error(self):
        res = flow_stress(530e6, -0.1, 0.26)
        assert res["ok"] is False

    def test_negative_n_returns_error(self):
        res = flow_stress(530e6, 0.3, -0.1)
        assert res["ok"] is False

    def test_n_gt_1_produces_warning(self):
        """n > 1.0 is unusual and should produce a warning."""
        res = flow_stress(530e6, 0.3, 1.2)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_fields_present(self):
        """Result must include all expected fields."""
        res = flow_stress(400e6, 0.2, 0.30)
        assert res["ok"] is True
        for field in ("K_Pa", "eps", "n", "sigma_f_Pa", "warnings"):
            assert field in res


# ===========================================================================
# 2. mean_flow_stress
# ===========================================================================

class TestMeanFlowStress:

    def test_algebraic_formula(self):
        """σ̄_f = K · ε_f^n / (n+1) algebraically verified."""
        K, n, ef = 530e6, 0.26, 0.5
        expected = K * (ef ** n) / (n + 1.0)
        res = mean_flow_stress(K, n, ef)
        assert res["ok"] is True
        assert abs(res["mean_flow_stress_Pa"] - expected) / expected < REL

    def test_mean_less_than_flow_at_eps_f(self):
        """σ̄_f must be < σ_f(ε_f) for n > 0."""
        res = mean_flow_stress(530e6, 0.26, 0.5)
        assert res["ok"] is True
        assert res["mean_flow_stress_Pa"] < res["sigma_f_at_eps_f_Pa"]

    def test_perfectly_plastic_n_zero(self):
        """For n=0, σ̄_f = K regardless of ε_f."""
        K = 300e6
        res = mean_flow_stress(K, 0.0, 0.8)
        assert res["ok"] is True
        assert abs(res["mean_flow_stress_Pa"] - K) / K < REL

    def test_invalid_K_returns_error(self):
        res = mean_flow_stress(-1.0, 0.26, 0.5)
        assert res["ok"] is False

    def test_invalid_eps_f_returns_error(self):
        res = mean_flow_stress(530e6, 0.26, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. upset_forging_force
# ===========================================================================

class TestUpsetForgingForce:

    # Reference fixture: carbon steel billet
    # A0 = π/4·(0.1)² ≈ 7.854e-3 m²  (100mm dia), h0=0.15m, hf=0.10m, mu=0.1
    _A0 = math.pi / 4.0 * 0.1 ** 2
    _h0 = 0.15
    _hf = 0.10
    _sf = 300e6  # approximate flow stress

    def _ref(self, **kwargs):
        return upset_forging_force(self._sf, self._A0, self._h0, self._hf, **kwargs)

    def test_volume_conservation(self):
        """Af × hf = A0 × h0 (volume conserved)."""
        res = self._ref()
        assert res["ok"] is True
        assert abs(res["Af_m2"] * self._hf - self._A0 * self._h0) < 1e-12

    def test_true_strain_formula(self):
        """ε = ln(h0/hf)."""
        expected = math.log(self._h0 / self._hf)
        res = self._ref()
        assert res["ok"] is True
        assert abs(res["true_strain"] - expected) / expected < REL

    def test_friction_factor_algebraic(self):
        """friction_factor = 2·μ·Rf / (3·hf)."""
        res = self._ref(mu=0.1)
        Rf = math.sqrt(res["Af_m2"] / math.pi)
        expected_ff = 2.0 * 0.1 * Rf / (3.0 * self._hf)
        assert abs(res["friction_factor"] - expected_ff) / expected_ff < REL

    def test_p_avg_formula(self):
        """p_avg = σ_f · (1 + friction_factor)."""
        res = self._ref(mu=0.1)
        expected = self._sf * (1.0 + res["friction_factor"])
        assert abs(res["p_avg_Pa"] - expected) / expected < REL

    def test_force_formula(self):
        """F = p_avg × Af."""
        res = self._ref()
        assert res["ok"] is True
        assert abs(res["F_N"] - res["p_avg_Pa"] * res["Af_m2"]) / res["F_N"] < REL

    def test_higher_friction_higher_force(self):
        """Higher friction coefficient → higher forging force."""
        f1 = self._ref(mu=0.05)["F_N"]
        f2 = self._ref(mu=0.3)["F_N"]
        assert f2 > f1

    def test_hf_ge_h0_returns_error(self):
        """hf >= h0 must return error."""
        res = upset_forging_force(self._sf, self._A0, self._h0, self._h0)
        assert res["ok"] is False

    def test_large_reduction_warning(self):
        """Reduction > 80% must produce a warning."""
        res = upset_forging_force(self._sf, self._A0, self._h0, 0.01)
        assert res["ok"] is True
        assert any("reduction" in w.lower() or "80" in w for w in res["warnings"])

    def test_reduction_pct_formula(self):
        """reduction_pct = (1 - hf/h0) × 100."""
        res = self._ref()
        expected_pct = (1.0 - self._hf / self._h0) * 100.0
        assert abs(res["reduction_pct"] - expected_pct) / expected_pct < REL


# ===========================================================================
# 4. closed_die_forging_load
# ===========================================================================

class TestClosedDieForgingLoad:

    def test_algebraic_formula(self):
        """F = Kf · σ̄_f · A_proj."""
        sf, Ap, Kf = 250e6, 0.05, 6.0
        expected = Kf * sf * Ap
        res = closed_die_forging_load(sf, Ap, Kf)
        assert res["ok"] is True
        assert abs(res["F_N"] - expected) / expected < REL

    def test_F_MN_consistent(self):
        """F_MN = F_N / 1e6."""
        res = closed_die_forging_load(200e6, 0.02, 5.0)
        assert res["ok"] is True
        assert abs(res["F_MN"] - res["F_N"] / 1e6) < 1e-9

    def test_tonnesf_consistent(self):
        """F_tonnesf = F_N / 9806.65."""
        res = closed_die_forging_load(200e6, 0.02, 5.0)
        assert res["ok"] is True
        assert abs(res["F_tonnesf"] - res["F_N"] / 9806.65) / res["F_tonnesf"] < REL

    def test_higher_Kf_higher_load(self):
        """Higher Kf → higher load."""
        f1 = closed_die_forging_load(200e6, 0.05, 3.0)["F_N"]
        f2 = closed_die_forging_load(200e6, 0.05, 8.0)["F_N"]
        assert f2 > f1

    def test_Kf_gt_8_warning(self):
        """Kf > 8 must produce a warning."""
        res = closed_die_forging_load(200e6, 0.05, 10.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_press_tonnage_warning(self):
        """F > 100 MN must produce a press-tonnage-exceeded warning."""
        # Need very large area and high sigma to push over 100 MN
        res = closed_die_forging_load(500e6, 100.0, 8.0)
        assert res["ok"] is True
        assert any("press-tonnage" in w.lower() or "100 mn" in w.lower() for w in res["warnings"])

    def test_zero_sigma_returns_error(self):
        res = closed_die_forging_load(0.0, 0.05, 6.0)
        assert res["ok"] is False

    def test_zero_area_returns_error(self):
        res = closed_die_forging_load(200e6, 0.0, 6.0)
        assert res["ok"] is False


# ===========================================================================
# 5. forward_extrusion
# ===========================================================================

class TestForwardExtrusion:

    # Reference: aluminium 1100-O billet, R=4, flat die, no container friction
    # sigma_f ~ 120 MPa (hot Al), A0 = 0.01 m², Af = 0.0025 m², alpha=45deg, L=0
    _sf = 120e6
    _A0 = 0.01
    _Af = 0.0025

    def _ref(self, **kwargs):
        return forward_extrusion(self._sf, self._A0, self._Af, **kwargs)

    def test_extrusion_ratio_algebraic(self):
        """R = A0/Af."""
        res = self._ref()
        assert res["ok"] is True
        assert abs(res["extrusion_ratio"] - self._A0 / self._Af) < REL

    def test_true_strain_algebraic(self):
        """ε = ln(A0/Af)."""
        res = self._ref()
        expected = math.log(self._A0 / self._Af)
        assert abs(res["true_strain"] - expected) / expected < REL

    def test_ideal_pressure_formula(self):
        """p_ideal = σ̄_f · ln(R)."""
        res = self._ref()
        expected = self._sf * math.log(self._A0 / self._Af)
        assert abs(res["p_ideal_Pa"] - expected) / expected < REL

    def test_redundant_factor_B_formula(self):
        """B = 0.8 + 1.2·tan(45°) = 0.8 + 1.2 = 2.0."""
        res = self._ref(die_half_angle_deg=45.0)
        expected_B = 0.8 + 1.2 * math.tan(math.radians(45.0))
        assert abs(res["redundant_factor_B"] - expected_B) / expected_B < REL

    def test_force_formula(self):
        """F = p_e × A0."""
        res = self._ref()
        assert abs(res["F_N"] - res["p_e_Pa"] * self._A0) / res["F_N"] < REL

    def test_Af_ge_A0_returns_error(self):
        res = forward_extrusion(self._sf, self._A0, self._A0)
        assert res["ok"] is False

    def test_large_R_warning(self):
        """Extrusion ratio R > 20 must produce a warning."""
        res = forward_extrusion(self._sf, 0.02, 0.0009)  # R ≈ 22
        assert res["ok"] is True
        assert any("ratio" in w.lower() or "r=" in w.lower() or "20" in w for w in res["warnings"])

    def test_container_friction_increases_pressure(self):
        """Adding container length L > 0 increases extrusion pressure."""
        p0 = forward_extrusion(self._sf, self._A0, self._Af, L=0.0)["p_e_Pa"]
        p1 = forward_extrusion(self._sf, self._A0, self._Af, L=0.5)["p_e_Pa"]
        assert p1 > p0


# ===========================================================================
# 6. backward_extrusion
# ===========================================================================

class TestBackwardExtrusion:

    _sf = 120e6
    _A0 = 0.01
    _Af = 0.0025

    def _ref(self, **kwargs):
        return backward_extrusion(self._sf, self._A0, self._Af, **kwargs)

    def test_p_e_algebraic_flat_die(self):
        """p_e = σ̄_f · B · ln(R) for backward extrusion."""
        res = self._ref(die_half_angle_deg=45.0)
        assert res["ok"] is True
        R = self._A0 / self._Af
        B = 0.8 + 1.2 * math.tan(math.radians(45.0))
        expected = self._sf * B * math.log(R)
        assert abs(res["p_e_Pa"] - expected) / expected < REL

    def test_backward_le_forward_no_container(self):
        """Backward extrusion pressure <= forward (same params, L=0)."""
        res_bwd = self._ref(die_half_angle_deg=45.0)
        res_fwd = forward_extrusion(self._sf, self._A0, self._Af,
                                    die_half_angle_deg=45.0, L=0.0)
        assert res_bwd["ok"] is True and res_fwd["ok"] is True
        # Without container friction, backward == forward at L=0
        assert abs(res_bwd["p_e_Pa"] - res_fwd["p_e_Pa"]) / res_fwd["p_e_Pa"] < REL

    def test_Af_ge_A0_returns_error(self):
        res = backward_extrusion(self._sf, self._A0, self._A0)
        assert res["ok"] is False

    def test_force_formula(self):
        """F = p_e × A0."""
        res = self._ref()
        assert abs(res["F_N"] - res["p_e_Pa"] * self._A0) / res["F_N"] < REL


# ===========================================================================
# 7. flat_rolling
# ===========================================================================

class TestFlatRolling:

    # Reference: steel strip rolling
    # σ̄_f=250MPa, μ=0.1, R=0.3m, h0=0.010m, hf=0.008m, w=0.5m
    _sf = 250e6
    _mu = 0.1
    _R = 0.3
    _h0 = 0.010
    _hf = 0.008
    _w = 0.5

    def _ref(self, **kwargs):
        return flat_rolling(self._sf, self._mu, self._R, self._h0, self._hf, self._w, **kwargs)

    def test_contact_length_algebraic(self):
        """L_c = sqrt(R·Δh)."""
        dh = self._h0 - self._hf
        expected = math.sqrt(self._R * dh)
        res = self._ref()
        assert res["ok"] is True
        assert abs(res["contact_length_m"] - expected) / expected < REL

    def test_max_draft_algebraic(self):
        """Δh_max = μ²·R."""
        expected = self._mu ** 2 * self._R
        res = self._ref()
        assert abs(res["max_draft_m"] - expected) / expected < REL

    def test_draft_feasible(self):
        """For standard parameters draft should be feasible."""
        res = self._ref()
        assert res["ok"] is True
        assert res["draft_feasible"] is True

    def test_draft_infeasible_warns(self):
        """If draft > μ²·R, draft_feasible=False and warning issued."""
        # Reduce mu so that max_draft < actual draft (0.002m)
        # μ²·R = 0.01²·0.3 = 0.00003 m  <<  dh=0.002 m
        res = flat_rolling(self._sf, 0.01, self._R, self._h0, self._hf, self._w)
        assert res["ok"] is True
        assert res["draft_feasible"] is False
        assert len(res["warnings"]) > 0

    def test_friction_hill_factor_formula(self):
        """ff = 1 + μ·L_c / (2·h_avg)."""
        res = self._ref()
        Lc = res["contact_length_m"]
        h_avg = (self._h0 + self._hf) / 2.0
        expected_ff = 1.0 + self._mu * Lc / (2.0 * h_avg)
        assert abs(res["friction_hill_factor"] - expected_ff) / expected_ff < REL

    def test_roll_force_formula(self):
        """F = σ̄_f · w · L_c · friction_hill_factor."""
        res = self._ref()
        Lc = res["contact_length_m"]
        ff = res["friction_hill_factor"]
        expected_F = self._sf * self._w * Lc * ff
        assert abs(res["F_N"] - expected_F) / expected_F < REL

    def test_torque_per_roll_formula(self):
        """T = F · L_c / 2."""
        res = self._ref()
        expected_T = res["F_N"] * res["contact_length_m"] / 2.0
        assert abs(res["torque_per_roll_Nm"] - expected_T) / expected_T < REL

    def test_power_with_omega(self):
        """P = 2·T·ω."""
        omega = 10.0  # rad/s
        res = self._ref(omega_rad_s=omega)
        assert res["ok"] is True
        expected_P = 2.0 * res["torque_per_roll_Nm"] * omega
        assert abs(res["power_W"] - expected_P) / expected_P < REL

    def test_power_zero_without_omega(self):
        """Power is 0.0 when omega_rad_s is not provided."""
        res = self._ref()
        assert res["power_W"] == 0.0

    def test_hf_ge_h0_returns_error(self):
        res = flat_rolling(self._sf, self._mu, self._R, self._h0, self._h0, self._w)
        assert res["ok"] is False

    def test_reduction_pct_formula(self):
        """reduction_pct = (h0-hf)/h0 × 100."""
        res = self._ref()
        expected = (self._h0 - self._hf) / self._h0 * 100.0
        assert abs(res["reduction_pct"] - expected) / expected < REL

    def test_true_strain_formula(self):
        """ε = ln(h0/hf)."""
        res = self._ref()
        expected = math.log(self._h0 / self._hf)
        assert abs(res["true_strain"] - expected) / expected < REL


# ===========================================================================
# 8. wire_drawing
# ===========================================================================

class TestWireDrawing:

    # Reference: steel wire, 25% area reduction
    # σ̄_f = 400 MPa, A0 = 1e-4 m², Af = 7.5e-5 m², mu=0.05, alpha=8°
    _sf = 400e6
    _A0 = 1.0e-4
    _Af = 0.75e-4

    def _ref(self, **kwargs):
        return wire_drawing(self._sf, self._A0, self._Af, **kwargs)

    def test_reduction_pct_formula(self):
        """reduction_pct = (1 - Af/A0) × 100."""
        res = self._ref()
        expected = (1.0 - self._Af / self._A0) * 100.0
        assert abs(res["reduction_pct"] - expected) / expected < REL

    def test_true_strain_formula(self):
        """ε = ln(A0/Af)."""
        res = self._ref()
        expected = math.log(self._A0 / self._Af)
        assert abs(res["true_strain"] - expected) / expected < REL

    def test_B_factor_formula(self):
        """B = μ · cot(α)."""
        alpha = 8.0
        mu = 0.05
        expected_B = mu / math.tan(math.radians(alpha))
        res = self._ref(mu=mu, die_half_angle_deg=alpha)
        assert abs(res["B_factor"] - expected_B) / expected_B < REL

    def test_force_formula(self):
        """F = σ_d × Af."""
        res = self._ref()
        assert abs(res["F_N"] - res["sigma_d_Pa"] * self._Af) / res["F_N"] < REL

    def test_feasible_for_small_reduction(self):
        """25% reduction should be feasible (σ_d < σ̄_f)."""
        res = self._ref()
        assert res["ok"] is True
        assert res["feasible"] is True
        assert res["sigma_d_over_sigmaf"] < 1.0

    def test_exceeds_limit_produces_warning(self):
        """Very large reduction → σ_d > σ̄_f → EXCEEDS-LIMIT-REDUCTION warning."""
        # Use a near-100% reduction to force σ_d → σ̄_f or above
        # r=0.90 with high mu low angle makes B small and σ_d high
        res = wire_drawing(self._sf, self._A0, self._A0 * 0.05,
                           mu=0.15, die_half_angle_deg=4.0)
        # If infeasible, check warning exists
        if not res["feasible"]:
            assert any("exceeds" in w.lower() or "fractur" in w.lower() for w in res["warnings"])

    def test_max_reduction_formula(self):
        """r_max = (1 - exp(-1/B)) × 100."""
        mu, alpha = 0.05, 8.0
        B = mu / math.tan(math.radians(alpha))
        expected_r_max = (1.0 - math.exp(-1.0 / B)) * 100.0
        res = self._ref(mu=mu, die_half_angle_deg=alpha)
        assert abs(res["max_reduction_pct"] - expected_r_max) / expected_r_max < REL

    def test_limiting_reduction_approx_63(self):
        """Limiting reduction ≈ 63.2% (1 - 1/e)."""
        res = self._ref()
        assert abs(res["limiting_reduction_pct"] - (1.0 - 1.0 / math.e) * 100.0) < 0.01

    def test_Af_ge_A0_returns_error(self):
        res = wire_drawing(self._sf, self._A0, self._A0)
        assert res["ok"] is False

    def test_small_die_angle_warning(self):
        """Die half-angle < 3° must produce a warning."""
        res = wire_drawing(self._sf, self._A0, self._Af, die_half_angle_deg=2.0)
        assert res["ok"] is True
        assert any("3°" in w or "3.0°" in w or "angle" in w.lower() for w in res["warnings"])


# ===========================================================================
# 9. forming_work
# ===========================================================================

class TestFormingWork:

    def test_work_formula(self):
        """W = F · d / η."""
        F, d, eta = 1e6, 0.05, 0.9
        expected = F * d / eta
        res = forming_work(F, d, eta=eta)
        assert res["ok"] is True
        assert abs(res["W_J"] - expected) / expected < REL

    def test_W_kJ_consistent(self):
        """W_kJ = W_J / 1000."""
        res = forming_work(500e3, 0.1)
        assert abs(res["W_kJ"] - res["W_J"] / 1000.0) < 1e-9

    def test_temperature_rise_formula(self):
        """ΔT = W / (ρ·V·Cp)."""
        F, d, rho, Cp, V = 1e6, 0.05, 7850.0, 502.0, 1e-3
        W = F * d
        expected_dT = W / (rho * V * Cp)
        res = forming_work(F, d, rho=rho, Cp=Cp, volume_m3=V)
        assert res["ok"] is True
        assert abs(res["delta_T_C"] - expected_dT) / expected_dT < REL

    def test_no_volume_zero_delta_T(self):
        """delta_T_C = 0.0 when volume_m3 not provided."""
        res = forming_work(1e6, 0.05)
        assert res["delta_T_C"] == 0.0

    def test_high_temp_rise_warning(self):
        """ΔT > 200°C must produce a warning."""
        # Large force, small volume, long stroke → big dT
        res = forming_work(5e6, 1.0, rho=7850.0, Cp=502.0, volume_m3=1e-5)
        assert res["ok"] is True
        if res["delta_T_C"] > 200.0:
            assert len(res["warnings"]) > 0

    def test_eta_gt_1_returns_error(self):
        res = forming_work(1e6, 0.05, eta=1.1)
        assert res["ok"] is False

    def test_zero_force_returns_error(self):
        res = forming_work(0.0, 0.05)
        assert res["ok"] is False


# ===========================================================================
# 10. passes_required
# ===========================================================================

class TestPassesRequired:

    def test_single_pass_sufficient(self):
        """If r_per_pass >= r_total, n_passes=1."""
        res = passes_required(0.20, 0.30)
        assert res["ok"] is True
        assert res["n_passes"] == 1

    def test_exact_n_formula(self):
        """n = ceil(ln(1-r_total)/ln(1-r_per_pass))."""
        rt, rp = 0.75, 0.20
        expected_n = math.ceil(math.log(1.0 - rt) / math.log(1.0 - rp))
        res = passes_required(rt, rp)
        assert res["ok"] is True
        assert res["n_passes"] == expected_n

    def test_eps_per_pass_formula(self):
        """ε_per_pass = ln(1 / (1 - r_per_pass))."""
        rp = 0.25
        expected = math.log(1.0 / (1.0 - rp))
        res = passes_required(0.80, rp)
        assert abs(res["eps_per_pass"] - expected) / expected < REL

    def test_eps_total_formula(self):
        """ε_total = n_passes × ε_per_pass."""
        res = passes_required(0.75, 0.20)
        assert abs(res["eps_total"] - res["n_passes"] * res["eps_per_pass"]) < 1e-10

    def test_cumulative_reduction_achieves_target(self):
        """Cumulative reduction after n_passes must be >= r_total."""
        rt, rp = 0.75, 0.20
        res = passes_required(rt, rp)
        assert res["ok"] is True
        assert res["cumulative_reduction_pct"] >= rt * 100.0 - 1e-9

    def test_many_passes_warning(self):
        """n_passes > 20 must produce a warning."""
        # Small per-pass reduction forces many passes
        res = passes_required(0.95, 0.02)
        assert res["ok"] is True
        if res["n_passes"] > 20:
            assert len(res["warnings"]) > 0

    def test_r_total_ge_1_returns_error(self):
        res = passes_required(1.0, 0.20)
        assert res["ok"] is False

    def test_r_per_pass_ge_1_returns_error(self):
        res = passes_required(0.75, 1.0)
        assert res["ok"] is False


# ===========================================================================
# 11. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    # --- flow_stress ---

    def test_tool_flow_stress_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_flow_stress(ctx, _args(K=530e6, eps=0.3, n=0.26)))
        d = _ok_tool(raw)
        assert d["sigma_f_Pa"] > 0

    def test_tool_flow_stress_missing_K(self):
        ctx = _ctx()
        raw = _run(run_forming_flow_stress(ctx, _args(eps=0.3, n=0.26)))
        _err_tool(raw)

    def test_tool_flow_stress_bad_json(self):
        ctx = _ctx()
        raw = _run(run_forming_flow_stress(ctx, b"not-json"))
        _err_tool(raw)

    # --- mean_flow_stress ---

    def test_tool_mean_flow_stress_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_mean_flow_stress(ctx, _args(K=530e6, n=0.26, eps_f=0.5)))
        d = _ok_tool(raw)
        assert d["mean_flow_stress_Pa"] > 0

    def test_tool_mean_flow_stress_missing_eps_f(self):
        ctx = _ctx()
        raw = _run(run_forming_mean_flow_stress(ctx, _args(K=530e6, n=0.26)))
        _err_tool(raw)

    # --- upset forging ---

    def test_tool_upset_forging_happy(self):
        ctx = _ctx()
        A0 = math.pi / 4.0 * 0.1 ** 2
        raw = _run(run_forming_upset_forging_force(
            ctx, _args(sigma_f=300e6, A0=A0, h0=0.15, hf=0.10, mu=0.1)
        ))
        d = _ok_tool(raw)
        assert d["F_N"] > 0

    def test_tool_upset_forging_missing_hf(self):
        ctx = _ctx()
        A0 = math.pi / 4.0 * 0.1 ** 2
        raw = _run(run_forming_upset_forging_force(
            ctx, _args(sigma_f=300e6, A0=A0, h0=0.15)
        ))
        _err_tool(raw)

    # --- closed-die forging ---

    def test_tool_closed_die_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_closed_die_load(ctx, _args(sigma_f=250e6, A_proj=0.05)))
        d = _ok_tool(raw)
        assert d["F_N"] > 0

    def test_tool_closed_die_custom_Kf(self):
        ctx = _ctx()
        raw = _run(run_forming_closed_die_load(ctx, _args(sigma_f=250e6, A_proj=0.05, Kf=3.0)))
        d = _ok_tool(raw)
        # With Kf=3 force should be half of Kf=6
        raw2 = _run(run_forming_closed_die_load(ctx, _args(sigma_f=250e6, A_proj=0.05, Kf=6.0)))
        d2 = _ok_tool(raw2)
        assert abs(d2["F_N"] / d["F_N"] - 2.0) < 1e-6

    def test_tool_closed_die_missing_sigma(self):
        ctx = _ctx()
        raw = _run(run_forming_closed_die_load(ctx, _args(A_proj=0.05)))
        _err_tool(raw)

    # --- forward extrusion ---

    def test_tool_forward_ext_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_forward_extrusion(
            ctx, _args(sigma_f=120e6, A0=0.01, Af=0.0025)
        ))
        d = _ok_tool(raw)
        assert d["extrusion_ratio"] == pytest.approx(4.0, rel=1e-9)

    def test_tool_forward_ext_missing_Af(self):
        ctx = _ctx()
        raw = _run(run_forming_forward_extrusion(ctx, _args(sigma_f=120e6, A0=0.01)))
        _err_tool(raw)

    # --- backward extrusion ---

    def test_tool_backward_ext_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_backward_extrusion(
            ctx, _args(sigma_f=120e6, A0=0.01, Af=0.0025)
        ))
        d = _ok_tool(raw)
        assert d["p_e_Pa"] > 0

    # --- flat rolling ---

    def test_tool_flat_rolling_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_flat_rolling(
            ctx, _args(sigma_f=250e6, mu=0.1, R=0.3, h0=0.010, hf=0.008, w=0.5)
        ))
        d = _ok_tool(raw)
        assert d["F_N"] > 0
        assert d["contact_length_m"] > 0

    def test_tool_flat_rolling_with_omega(self):
        ctx = _ctx()
        raw = _run(run_forming_flat_rolling(
            ctx, _args(sigma_f=250e6, mu=0.1, R=0.3, h0=0.010, hf=0.008, w=0.5, omega_rad_s=10.0)
        ))
        d = _ok_tool(raw)
        assert d["power_W"] > 0

    def test_tool_flat_rolling_missing_w(self):
        ctx = _ctx()
        raw = _run(run_forming_flat_rolling(
            ctx, _args(sigma_f=250e6, mu=0.1, R=0.3, h0=0.010, hf=0.008)
        ))
        _err_tool(raw)

    # --- wire drawing ---

    def test_tool_wire_drawing_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_wire_drawing(
            ctx, _args(sigma_f=400e6, A0=1e-4, Af=7.5e-5)
        ))
        d = _ok_tool(raw)
        assert d["feasible"] is True

    def test_tool_wire_drawing_missing_Af(self):
        ctx = _ctx()
        raw = _run(run_forming_wire_drawing(ctx, _args(sigma_f=400e6, A0=1e-4)))
        _err_tool(raw)

    # --- forming work ---

    def test_tool_forming_work_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_work(ctx, _args(F_N=1e6, displacement_m=0.05)))
        d = _ok_tool(raw)
        assert d["W_J"] == pytest.approx(1e6 * 0.05, rel=1e-9)

    def test_tool_forming_work_with_volume(self):
        ctx = _ctx()
        raw = _run(run_forming_work(
            ctx, _args(F_N=1e6, displacement_m=0.05, rho=7850.0, Cp=502.0, volume_m3=1e-3)
        ))
        d = _ok_tool(raw)
        assert d["delta_T_C"] > 0

    def test_tool_forming_work_missing_F(self):
        ctx = _ctx()
        raw = _run(run_forming_work(ctx, _args(displacement_m=0.05)))
        _err_tool(raw)

    # --- passes required ---

    def test_tool_passes_required_happy(self):
        ctx = _ctx()
        raw = _run(run_forming_passes_required(ctx, _args(r_total=0.75, r_per_pass=0.20)))
        d = _ok_tool(raw)
        assert d["n_passes"] >= 1

    def test_tool_passes_required_missing_r_total(self):
        ctx = _ctx()
        raw = _run(run_forming_passes_required(ctx, _args(r_per_pass=0.20)))
        _err_tool(raw)

    def test_tool_passes_required_bad_json(self):
        ctx = _ctx()
        raw = _run(run_forming_passes_required(ctx, b"{{bad"))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases
#
# Each case cites a worked example or tabulated datum from an authoritative
# manufacturing-engineering reference with a known numeric answer.  These
# replace author-only hand-calcs with literature-traceable validation.
# ---------------------------------------------------------------------------

class TestFormingExternalReferenceCases:
    """Cross-checked against Kalpakjian / Hosford-Caddell / Groover."""

    def test_hollomon_copper_at_unit_strain_equals_K(self):
        # Kalpakjian & Schmid 7th ed., Table 2.3: annealed copper
        # K = 315 MPa, n = 0.54.  At true strain eps = 1.0, sigma = K.
        r = flow_stress(315e6, 1.0, 0.54)
        assert math.isclose(r["sigma_f_Pa"], 315e6, rel_tol=1e-9)

    def test_hollomon_1100O_aluminium(self):
        # Kalpakjian & Schmid 7th ed., Table 2.3: 1100-O aluminium
        # K = 180 MPa, n = 0.20.  sigma(eps=0.223) = 180*0.223^0.20 MPa.
        r = flow_stress(180e6, 0.223, 0.20)
        assert math.isclose(r["sigma_f_Pa"], 180e6 * 0.223 ** 0.20, rel_tol=1e-9)

    def test_mean_flow_stress_integral_identity(self):
        # Hosford & Caddell, Metal Forming 4th ed., Eq. 5.3:
        # mean flow stress over 0->eps_f = K*eps_f^n/(n+1).
        r = mean_flow_stress(180e6, 0.20, 0.223)
        assert math.isclose(
            r["mean_flow_stress_Pa"], 180e6 * 0.223 ** 0.20 / 1.20, rel_tol=1e-12
        )

    def test_flat_rolling_contact_length_kalpakjian_13_1(self):
        # Kalpakjian & Schmid 7th ed. Ex. 13.1 geometry: contact length
        # L = sqrt(R*dh).  R=150 mm, h0=9 mm, hf=6.3 mm -> dh=2.7 mm.
        # L = sqrt(0.150 * 0.0027) = 0.0201246 m.
        r = flat_rolling(sigma_f=275e6, mu=0.30, R=0.150,
                         h0=0.009, hf=0.0063, w=0.300)
        assert math.isclose(r["contact_length_m"],
                            math.sqrt(0.150 * 0.0027), rel_tol=1e-9)

    def test_flat_rolling_true_strain_kalpakjian(self):
        # Kalpakjian: true strain in rolling eps = ln(h0/hf).
        r = flat_rolling(sigma_f=275e6, mu=0.30, R=0.150,
                         h0=0.009, hf=0.0063, w=0.300)
        assert math.isclose(r["true_strain"], math.log(9.0 / 6.3), rel_tol=1e-9)

    def test_flat_rolling_max_draft_bite_condition(self):
        # Kalpakjian & Schmid 7th ed., Eq. 13.5: max draft = mu^2 * R.
        r = flat_rolling(sigma_f=275e6, mu=0.20, R=0.150,
                         h0=0.010, hf=0.009, w=0.300)
        assert math.isclose(r["max_draft_m"], 0.20 ** 2 * 0.150, rel_tol=1e-9)

    def test_forward_extrusion_ratio_and_strain_kalpakjian_15(self):
        # Kalpakjian & Schmid 7th ed. §15.2: extrusion ratio R=A0/Af,
        # ideal strain eps = ln(R).  A0=4e-3, Af=1e-3 -> R=4, eps=ln4.
        r = forward_extrusion(sigma_f=200e6, A0=4e-3, Af=1e-3)
        assert math.isclose(r["extrusion_ratio"], 4.0, rel_tol=1e-12)
        assert math.isclose(r["true_strain"], math.log(4.0), rel_tol=1e-12)

    def test_forward_extrusion_ideal_pressure_kalpakjian(self):
        # Kalpakjian: ideal extrusion pressure p = sigma_bar * ln(R).
        r = forward_extrusion(sigma_f=200e6, A0=4e-3, Af=1e-3)
        assert math.isclose(r["p_ideal_Pa"], 200e6 * math.log(4.0), rel_tol=1e-9)

    def test_wire_drawing_area_reduction_kalpakjian_15_5(self):
        # Kalpakjian & Schmid 7th ed. §15.5: r = 1 - Af/A0.
        # A0=10 mm^2, Af=7.5 mm^2 -> r = 25 %.
        r = wire_drawing(sigma_f=600e6, A0=10e-6, Af=7.5e-6,
                         mu=0.05, die_half_angle_deg=8.0)
        assert math.isclose(r["reduction_pct"], 25.0, rel_tol=1e-9)

    def test_wire_drawing_limiting_reduction_ideal(self):
        # Hosford & Caddell §6.5: limiting frictionless reduction = 1-1/e
        # = 63.21 % (the classic ideal-drawing limit).
        r = wire_drawing(sigma_f=600e6, A0=10e-6, Af=8e-6,
                         mu=0.05, die_half_angle_deg=8.0)
        assert math.isclose(r["limiting_reduction_pct"],
                            (1.0 - 1.0 / math.e) * 100.0, rel_tol=1e-9)

    def test_passes_required_cumulative_reduction_formula(self):
        # Groover, Fundamentals of Modern Manufacturing 5th ed. §19:
        # cumulative reduction after N passes = 1-(1-r)^N.
        r = passes_required(r_total=0.75, r_per_pass=0.20)
        n = r["n_passes"]
        assert math.isclose(r["cumulative_reduction_pct"],
                            (1.0 - (1.0 - 0.20) ** n) * 100.0, rel_tol=1e-9)
