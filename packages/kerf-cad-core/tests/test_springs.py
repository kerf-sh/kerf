"""
Hermetic tests for kerf_cad_core.springs — mechanical spring design.

Coverage:
  design.helical_compression              — rate, solid height, Wahl, stress, Goodman
  design.helical_compression_with_free_length — slenderness, buckling flag
  design.helical_extension                — rate, KB, hook stress, initial tension
  design.torsion_spring                   — angular rate, bending stress, cross-check
  design.belleville_washer                — Almen-László load, stress, P/delta queries
  tools.*                                 — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against published textbook expressions.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Ch. 10
Wahl, A.M. "Mechanical Springs", 2nd ed.
Almen & László, Trans. ASME 58 (1936) p. 305

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.springs.design import (
    helical_compression,
    helical_compression_with_free_length,
    helical_extension,
    torsion_spring,
    belleville_washer,
)
from kerf_cad_core.springs.tools import (
    run_spring_compression,
    run_spring_extension,
    run_spring_torsion,
    run_spring_belleville,
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


REL = 1e-6  # relative tolerance for floating-point checks


# ===========================================================================
# 1. helical_compression — spring rate formula
# ===========================================================================

class TestHelicalCompressionRate:

    def test_rate_formula_algebraic(self):
        """k = G d^4 / (8 D^3 N) — verify exactly."""
        d, D, N, G = 3e-3, 20e-3, 10.0, 79.3e9
        expected_k = G * d**4 / (8.0 * D**3 * N)
        res = helical_compression(d, D, N, G)
        assert res["ok"] is True
        assert abs(res["rate_N_per_m"] - expected_k) / expected_k < REL

    def test_rate_increases_with_wire_diameter(self):
        """Larger wire diameter → stiffer spring."""
        D, N, G = 20e-3, 10.0, 79.3e9
        k1 = helical_compression(2e-3, D, N, G)["rate_N_per_m"]
        k2 = helical_compression(4e-3, D, N, G)["rate_N_per_m"]
        assert k2 > k1

    def test_rate_decreases_with_more_coils(self):
        """More active coils → softer spring."""
        d, D, G = 3e-3, 20e-3, 79.3e9
        k1 = helical_compression(d, D, 5.0, G)["rate_N_per_m"]
        k2 = helical_compression(d, D, 20.0, G)["rate_N_per_m"]
        assert k2 < k1

    def test_rate_scales_fourth_power_d(self):
        """Doubling d multiplies k by 2^4 = 16."""
        D, N, G = 20e-3, 10.0, 79.3e9
        k1 = helical_compression(2e-3, D, N, G)["rate_N_per_m"]
        k2 = helical_compression(4e-3, D, N, G)["rate_N_per_m"]
        assert abs(k2 / k1 - 16.0) < 1e-9

    def test_rate_scales_inverse_N(self):
        """Doubling N halves k (k ∝ 1/N)."""
        d, D, G = 3e-3, 20e-3, 79.3e9
        k1 = helical_compression(d, D, 10.0, G)["rate_N_per_m"]
        k2 = helical_compression(d, D, 20.0, G)["rate_N_per_m"]
        assert abs(k2 / k1 - 0.5) < 1e-9


# ===========================================================================
# 2. helical_compression — Wahl factor and spring index
# ===========================================================================

class TestWahlFactor:

    def test_wahl_formula_algebraic(self):
        """Kw = (4C-1)/(4C-4) + 0.615/C."""
        d, D, N, G = 3e-3, 24e-3, 10.0, 79.3e9
        C = D / d
        expected_Kw = (4.0 * C - 1.0) / (4.0 * C - 4.0) + 0.615 / C
        res = helical_compression(d, D, N, G)
        assert res["ok"] is True
        assert abs(res["Kw"] - expected_Kw) / expected_Kw < REL

    def test_spring_index_reported(self):
        """C = D/d is correctly reported."""
        d, D, N, G = 2e-3, 20e-3, 8.0, 79.3e9
        res = helical_compression(d, D, N, G)
        assert res["ok"] is True
        assert abs(res["C"] - D / d) < 1e-12

    def test_wahl_greater_than_unity(self):
        """Kw must always be > 1 for any realistic spring index."""
        for C_val in [3.0, 5.0, 8.0, 12.0, 15.0]:
            d = 2e-3
            D = C_val * d
            res = helical_compression(d, D, 10.0, 79.3e9)
            assert res["ok"] is True
            assert res["Kw"] > 1.0


# ===========================================================================
# 3. helical_compression — solid height and end types
# ===========================================================================

class TestSolidHeight:

    def test_squared_ground_solid_height(self):
        """squared_ground: Ls = (N + 2) * d."""
        d, N = 3e-3, 10.0
        res = helical_compression(d, 20e-3, N, 79.3e9, end_type="squared_ground")
        assert res["ok"] is True
        expected = (N + 2) * d
        assert abs(res["solid_height_m"] - expected) < 1e-12

    def test_plain_solid_height(self):
        """plain ends: Ls = N * d (no inactive coils)."""
        d, N = 4e-3, 12.0
        res = helical_compression(d, 25e-3, N, 79.3e9, end_type="plain")
        assert res["ok"] is True
        assert abs(res["solid_height_m"] - N * d) < 1e-12

    def test_plain_ground_solid_height(self):
        """plain_ground ends: Ls = (N + 1) * d."""
        d, N = 3e-3, 8.0
        res = helical_compression(d, 20e-3, N, 79.3e9, end_type="plain_ground")
        assert res["ok"] is True
        assert abs(res["solid_height_m"] - (N + 1) * d) < 1e-12

    def test_invalid_end_type_returns_error(self):
        """Unknown end_type returns ok=False."""
        res = helical_compression(3e-3, 20e-3, 10.0, 79.3e9, end_type="welded")
        assert res["ok"] is False


# ===========================================================================
# 4. helical_compression — shear stress
# ===========================================================================

class TestCompressionShearStress:

    def test_shear_stress_algebraic(self):
        """τ = Kw × 8 F D / (π d^3) at max force F = Fa + Fm."""
        d, D, N, G = 3e-3, 20e-3, 10.0, 79.3e9
        Fa, Fm = 50.0, 150.0
        res = helical_compression(d, D, N, G, Fa=Fa, Fm=Fm)
        assert res["ok"] is True
        F_max = Fa + Fm
        Kw = res["Kw"]
        expected_tau = Kw * 8.0 * F_max * D / (math.pi * d**3)
        assert abs(res["shear_stress_max_Pa"] - expected_tau) / expected_tau < REL

    def test_shear_stress_absent_without_forces(self):
        """No stress key when no forces supplied."""
        res = helical_compression(3e-3, 20e-3, 10.0, 79.3e9)
        assert res["ok"] is True
        assert "shear_stress_max_Pa" not in res


# ===========================================================================
# 5. helical_compression — Goodman fatigue
# ===========================================================================

class TestGoodmanFatigue:

    def test_goodman_passes_for_low_loads(self):
        """Low alternating and mean forces pass Goodman."""
        res = helical_compression(
            3e-3, 20e-3, 10.0, 79.3e9,
            Sut=1800e6, Se=800e6, Fa=1.0, Fm=2.0,
        )
        assert res["ok"] is True
        assert res.get("goodman_ok") is True
        assert res.get("goodman_ratio") > 0

    def test_goodman_fails_for_excessive_loads(self):
        """Very large alternating force must fail Goodman check."""
        res = helical_compression(
            1e-3, 8e-3, 5.0, 79.3e9,
            Sut=1000e6, Se=400e6, Fa=500.0, Fm=500.0,
        )
        assert res["ok"] is True  # function succeeds
        assert res.get("goodman_ok") is False
        assert any("FAILED" in w for w in res["warnings"])

    def test_goodman_ratio_formula(self):
        """goodman_ratio = τa/Sse + τm/Ssu where Ssu = 0.67 Sut."""
        d, D, N, G = 3e-3, 20e-3, 10.0, 79.3e9
        Sut, Se, Fa, Fm = 1800e6, 800e6, 20.0, 80.0
        res = helical_compression(d, D, N, G, Sut=Sut, Se=Se, Fa=Fa, Fm=Fm)
        Kw = res["Kw"]
        tau_a = Kw * 8.0 * Fa * D / (math.pi * d**3)
        tau_m = Kw * 8.0 * Fm * D / (math.pi * d**3)
        Ssu = 0.67 * Sut
        expected_ratio = tau_a / Se + tau_m / Ssu
        assert abs(res["goodman_ratio"] - expected_ratio) / expected_ratio < REL


# ===========================================================================
# 6. helical_compression — buckling / slenderness
# ===========================================================================

class TestBucklingSlenderness:

    def test_slenderness_computed_from_free_length(self):
        """slenderness = free_length / D."""
        d, D, N, G = 3e-3, 20e-3, 10.0, 79.3e9
        L_free = 0.1  # m
        res = helical_compression_with_free_length(d, D, N, G, L_free)
        assert res["ok"] is True
        assert abs(res["slenderness"] - L_free / D) < 1e-12

    def test_buckling_warning_when_slender(self):
        """Slenderness > 4 should produce a buckling warning."""
        d, D, N, G = 1e-3, 8e-3, 10.0, 79.3e9
        L_free = 0.5  # very long → L/D = 62.5
        res = helical_compression_with_free_length(d, D, N, G, L_free)
        assert res["ok"] is True
        assert any("Buckling" in w or "buckling" in w for w in res["warnings"])

    def test_no_buckling_warning_for_compact_spring(self):
        """Short spring (low slenderness) should not warn about buckling."""
        d, D, N, G = 3e-3, 20e-3, 6.0, 79.3e9
        L_free = 0.05  # L/D = 2.5 < 4
        res = helical_compression_with_free_length(d, D, N, G, L_free)
        assert res["ok"] is True
        assert not any("Buckling" in w or "buckling" in w for w in res["warnings"])


# ===========================================================================
# 7. helical_compression — input validation
# ===========================================================================

class TestCompressionValidation:

    def test_negative_d_returns_error(self):
        res = helical_compression(-1e-3, 20e-3, 10.0, 79.3e9)
        assert res["ok"] is False

    def test_zero_N_returns_error(self):
        res = helical_compression(3e-3, 20e-3, 0.0, 79.3e9)
        assert res["ok"] is False

    def test_negative_G_returns_error(self):
        res = helical_compression(3e-3, 20e-3, 10.0, -1.0)
        assert res["ok"] is False

    def test_negative_Fa_returns_error(self):
        res = helical_compression(3e-3, 20e-3, 10.0, 79.3e9, Fa=-10.0)
        assert res["ok"] is False


# ===========================================================================
# 8. helical_extension — rate and KB
# ===========================================================================

class TestHelicalExtension:

    def test_extension_rate_same_formula_as_compression(self):
        """Extension rate k = G d^4 / (8 D^3 N) — same formula."""
        d, D, N, G = 2.5e-3, 18e-3, 8.0, 79.3e9
        expected_k = G * d**4 / (8.0 * D**3 * N)
        res = helical_extension(d, D, N, G)
        assert res["ok"] is True
        assert abs(res["rate_N_per_m"] - expected_k) / expected_k < REL

    def test_hook_stress_concentration_KB_formula(self):
        """KB = (4C^2 - C - 1) / (4C(C-1))."""
        d, D, N, G = 2e-3, 16e-3, 10.0, 79.3e9
        C = D / d
        expected_KB = (4.0 * C**2 - C - 1.0) / (4.0 * C * (C - 1.0))
        res = helical_extension(d, D, N, G)
        assert res["ok"] is True
        assert abs(res["KB"] - expected_KB) / expected_KB < REL

    def test_hook_bending_stress_algebraic(self):
        """σ_hook = KB × 16 F D / (π d³)."""
        d, D, N, G = 2e-3, 16e-3, 10.0, 79.3e9
        Fa, Fm = 30.0, 70.0
        res = helical_extension(d, D, N, G, Fa=Fa, Fm=Fm)
        assert res["ok"] is True
        F_max = Fa + Fm
        KB = res["KB"]
        expected = KB * 16.0 * F_max * D / (math.pi * d**3)
        assert abs(res["hook_bending_stress_Pa"] - expected) / expected < REL

    def test_initial_tension_warning(self):
        """Fi > Fm should warn that spring may not open."""
        res = helical_extension(
            2e-3, 16e-3, 10.0, 79.3e9,
            Fm=10.0, initial_tension_N=50.0,
        )
        assert res["ok"] is True
        assert any("initial tension" in w.lower() or "Fi" in w for w in res["warnings"])

    def test_extension_negative_d_returns_error(self):
        res = helical_extension(-1e-3, 16e-3, 10.0, 79.3e9)
        assert res["ok"] is False

    def test_extension_negative_Fa_returns_error(self):
        res = helical_extension(2e-3, 16e-3, 10.0, 79.3e9, Fa=-5.0)
        assert res["ok"] is False


# ===========================================================================
# 9. torsion_spring — angular rate
# ===========================================================================

class TestTorsionSpring:

    def test_angular_rate_per_rev_formula(self):
        """k_rev = E d^4 / (64 D N)."""
        d, D, N, E = 3e-3, 20e-3, 10.0, 200e9
        expected = E * d**4 / (64.0 * D * N)
        res = torsion_spring(d, D, N, E)
        assert res["ok"] is True
        assert abs(res["rate_Nm_per_rev"] - expected) / expected < REL

    def test_angular_rate_per_rad_from_per_rev(self):
        """rate_rad = rate_rev / (2π)."""
        d, D, N, E = 3e-3, 20e-3, 10.0, 200e9
        res = torsion_spring(d, D, N, E)
        assert res["ok"] is True
        expected_rad = res["rate_Nm_per_rev"] / (2.0 * math.pi)
        assert abs(res["rate_Nm_per_rad"] - expected_rad) / expected_rad < REL

    def test_bending_stress_algebraic(self):
        """σ = Ki × 32 T / (π d³)."""
        d, D, N, E, T = 3e-3, 20e-3, 10.0, 200e9, 5.0
        res = torsion_spring(d, D, N, E, torque_Nm=T)
        assert res["ok"] is True
        Ki = res["curvature_correction_Ki"]
        expected = Ki * 32.0 * T / (math.pi * d**3)
        assert abs(res["bending_stress_Pa"] - expected) / expected < REL

    def test_curvature_correction_Ki_formula(self):
        """Ki = (4C^2 - C - 1) / (4C(C-1))."""
        d, D, N, E = 2e-3, 16e-3, 8.0, 200e9
        C = D / d
        expected_Ki = (4.0 * C**2 - C - 1.0) / (4.0 * C * (C - 1.0))
        res = torsion_spring(d, D, N, E)
        assert res["ok"] is True
        assert abs(res["curvature_correction_Ki"] - expected_Ki) / expected_Ki < REL

    def test_torque_from_deflection(self):
        """T_from_deflection = k_rev × (theta_deg / 360)."""
        d, D, N, E = 3e-3, 20e-3, 10.0, 200e9
        theta = 180.0  # degrees
        res = torsion_spring(d, D, N, E, angular_deflection_deg=theta)
        assert res["ok"] is True
        k_rev = res["rate_Nm_per_rev"]
        expected = k_rev * (theta / 360.0)
        assert abs(res["torque_from_deflection_Nm"] - expected) / expected < REL

    def test_consistency_warning_when_torque_and_deflection_disagree(self):
        """Supply inconsistent torque and deflection → warning."""
        d, D, N, E = 3e-3, 20e-3, 10.0, 200e9
        # k_rev ≈ 200e9 * (3e-3)^4 / (64 * 20e-3 * 10) = small number
        k_rev = E * d**4 / (64.0 * D * N)
        # correct T for 90 deg
        T_correct = k_rev * 0.25  # 90 deg = 0.25 rev
        # deliberately provide a very different torque (100× off)
        res = torsion_spring(d, D, N, E, torque_Nm=T_correct * 100.0,
                             angular_deflection_deg=90.0)
        assert res["ok"] is True
        assert any("differ" in w.lower() for w in res["warnings"])

    def test_torsion_negative_d_returns_error(self):
        res = torsion_spring(-1e-3, 20e-3, 10.0, 200e9)
        assert res["ok"] is False

    def test_torsion_zero_E_returns_error(self):
        res = torsion_spring(3e-3, 20e-3, 10.0, 0.0)
        assert res["ok"] is False

    def test_torsion_negative_torque_returns_error(self):
        res = torsion_spring(3e-3, 20e-3, 10.0, 200e9, torque_Nm=-1.0)
        assert res["ok"] is False


# ===========================================================================
# 10. belleville_washer — Almen-László
# ===========================================================================

class TestBellevilleWasher:

    def _standard_params(self):
        """A typical small Belleville disc spring in steel."""
        return dict(De=50e-3, Di=25.4e-3, t=2.5e-3, h0=1.5e-3, E=200e9, nu=0.3)

    def test_returns_ok(self):
        res = belleville_washer(**self._standard_params())
        assert res["ok"] is True

    def test_P_flat_positive(self):
        """P to flatten disc must be positive for valid geometry."""
        res = belleville_washer(**self._standard_params())
        assert res["P_flat_N"] > 0

    def test_alpha_beta_positive(self):
        """Geometric constants α, β must be positive for R > 1."""
        res = belleville_washer(**self._standard_params())
        assert res["alpha_factor"] > 0
        assert res["beta_factor"] > 0

    def test_delta_at_flat_equals_h0(self):
        """P at delta=h0 must equal P_flat_N."""
        p = self._standard_params()
        res = belleville_washer(**p, delta_target=p["h0"])
        assert res["ok"] is True
        assert abs(res["P_at_delta_target_N"] - res["P_flat_N"]) / res["P_flat_N"] < 1e-10

    def test_P_at_half_h0(self):
        """P at delta=h0/2 must be strictly between 0 and P_flat."""
        p = self._standard_params()
        res = belleville_washer(**p, delta_target=p["h0"] / 2.0)
        assert res["ok"] is True
        assert 0 < res["P_at_delta_target_N"] < res["P_flat_N"]

    def test_delta_at_P_flat(self):
        """Bisection: deflection at P_flat must converge to h0."""
        p = self._standard_params()
        res_flat = belleville_washer(**p)
        res = belleville_washer(**p, P_target=res_flat["P_flat_N"] * 0.999)
        assert res["ok"] is True
        assert res["delta_at_P_target_m"] == pytest.approx(p["h0"], rel=0.01)

    def test_small_load_gives_small_deflection(self):
        """A small P_target should yield small deflection."""
        p = self._standard_params()
        P_flat = belleville_washer(**p)["P_flat_N"]
        res = belleville_washer(**p, P_target=P_flat * 0.01)
        assert res["ok"] is True
        assert res["delta_at_P_target_m"] < p["h0"] * 0.1

    def test_stiffer_disc_from_larger_t(self):
        """Thicker disc must produce higher P_flat (more load at flat)."""
        p = self._standard_params()
        p2 = {**p, "t": p["t"] * 2, "h0": p["h0"]}
        P1 = belleville_washer(**p)["P_flat_N"]
        P2 = belleville_washer(**p2)["P_flat_N"]
        assert P2 > P1

    def test_snap_through_warning_high_h0_t(self):
        """h0/t > 1.5 should trigger snap-through warning."""
        p = self._standard_params()
        p_snap = {**p, "h0": p["t"] * 2.0}  # h0/t = 2.0
        res = belleville_washer(**p_snap)
        assert res["ok"] is True
        assert any("snap" in w.lower() or "non-linear" in w.lower() for w in res["warnings"])

    def test_Di_equals_De_returns_error(self):
        """Di >= De must return ok=False."""
        p = self._standard_params()
        res = belleville_washer(De=p["De"], Di=p["De"], t=p["t"], h0=p["h0"],
                                E=p["E"], nu=p["nu"])
        assert res["ok"] is False

    def test_nu_out_of_range_returns_error(self):
        """Poisson's ratio > 0.5 must return ok=False."""
        p = self._standard_params()
        res = belleville_washer(**{**p, "nu": 0.6})
        assert res["ok"] is False

    def test_zero_E_returns_error(self):
        p = self._standard_params()
        res = belleville_washer(**{**p, "E": 0.0})
        assert res["ok"] is False

    def test_negative_t_returns_error(self):
        p = self._standard_params()
        res = belleville_washer(**{**p, "t": -1e-3})
        assert res["ok"] is False


# ===========================================================================
# 11. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_spring_compression_happy_path(self):
        ctx = _ctx()
        raw = _run(run_spring_compression(ctx, _args(
            d=3e-3, D=20e-3, N=10.0, G=79.3e9
        )))
        d = _ok_tool(raw)
        assert d["rate_N_per_m"] > 0
        assert d["Kw"] > 1.0

    def test_run_spring_compression_with_stress(self):
        ctx = _ctx()
        raw = _run(run_spring_compression(ctx, _args(
            d=3e-3, D=20e-3, N=10.0, G=79.3e9, Fa=50.0, Fm=100.0
        )))
        d = _ok_tool(raw)
        assert d["shear_stress_max_Pa"] > 0

    def test_run_spring_compression_missing_d(self):
        ctx = _ctx()
        raw = _run(run_spring_compression(ctx, _args(D=20e-3, N=10.0, G=79.3e9)))
        _err_tool(raw)

    def test_run_spring_compression_bad_json(self):
        ctx = _ctx()
        raw = _run(run_spring_compression(ctx, b"not json"))
        _err_tool(raw)

    def test_run_spring_compression_with_free_length(self):
        ctx = _ctx()
        raw = _run(run_spring_compression(ctx, _args(
            d=3e-3, D=20e-3, N=10.0, G=79.3e9, free_length_m=0.08
        )))
        d = _ok_tool(raw)
        assert "slenderness" in d
        assert abs(d["slenderness"] - 0.08 / 20e-3) < 1e-10

    def test_run_spring_extension_happy_path(self):
        ctx = _ctx()
        raw = _run(run_spring_extension(ctx, _args(
            d=2e-3, D=16e-3, N=8.0, G=79.3e9, Fa=20.0, Fm=50.0
        )))
        d = _ok_tool(raw)
        assert d["rate_N_per_m"] > 0
        assert d["KB"] > 1.0
        assert d["hook_bending_stress_Pa"] > 0

    def test_run_spring_extension_missing_G(self):
        ctx = _ctx()
        raw = _run(run_spring_extension(ctx, _args(d=2e-3, D=16e-3, N=8.0)))
        _err_tool(raw)

    def test_run_spring_torsion_happy_path(self):
        ctx = _ctx()
        raw = _run(run_spring_torsion(ctx, _args(
            d=3e-3, D=20e-3, N=10.0, E=200e9, torque_Nm=5.0
        )))
        d = _ok_tool(raw)
        assert d["rate_Nm_per_rev"] > 0
        assert d["bending_stress_Pa"] > 0

    def test_run_spring_torsion_missing_E(self):
        ctx = _ctx()
        raw = _run(run_spring_torsion(ctx, _args(d=3e-3, D=20e-3, N=10.0)))
        _err_tool(raw)

    def test_run_spring_belleville_happy_path(self):
        ctx = _ctx()
        raw = _run(run_spring_belleville(ctx, _args(
            De=50e-3, Di=25.4e-3, t=2.5e-3, h0=1.5e-3, E=200e9, nu=0.3
        )))
        d = _ok_tool(raw)
        assert d["P_flat_N"] > 0
        assert d["alpha_factor"] > 0

    def test_run_spring_belleville_with_P_target(self):
        ctx = _ctx()
        raw = _run(run_spring_belleville(ctx, _args(
            De=50e-3, Di=25.4e-3, t=2.5e-3, h0=1.5e-3, E=200e9, nu=0.3,
            P_target=1000.0
        )))
        d = _ok_tool(raw)
        assert "delta_at_P_target_m" in d

    def test_run_spring_belleville_with_delta_target(self):
        ctx = _ctx()
        raw = _run(run_spring_belleville(ctx, _args(
            De=50e-3, Di=25.4e-3, t=2.5e-3, h0=1.5e-3, E=200e9, nu=0.3,
            delta_target=0.75e-3
        )))
        d = _ok_tool(raw)
        assert "P_at_delta_target_N" in d

    def test_run_spring_belleville_missing_nu(self):
        ctx = _ctx()
        raw = _run(run_spring_belleville(ctx, _args(
            De=50e-3, Di=25.4e-3, t=2.5e-3, h0=1.5e-3, E=200e9
        )))
        _err_tool(raw)

    def test_run_spring_belleville_bad_json(self):
        ctx = _ctx()
        raw = _run(run_spring_belleville(ctx, b"{bad"))
        _err_tool(raw)
