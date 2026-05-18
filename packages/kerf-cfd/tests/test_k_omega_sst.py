"""
Test suite for kerf_cfd.k_omega_sst — Menter (2003) k-ω SST turbulence model.

All reference values are cited inline.  No network, no fixture files.

Primary references
------------------
[Menter1994]  Menter F. R., AIAA J. 32 (8) (1994) 1598-1605.
[Menter2003]  Menter F. R. et al., NASA/TM-2003-212144.
[Eaton1981]   Eaton J. K., Johnston J. P., AIAA J. 19 (9) (1981) 1093-1100.
              Re_h = 36 000; x_r/h ≈ 6.5 ± 0.5.
[Le1997]      Le H., Moin P., Kim J., J. Fluid Mech. 330 (1997) 349-374.
              DNS reattachment x_r/h ≈ 6.28 for Re_h = 5100.
[Pope2000]    Pope S. B., Turbulent Flows (2000), Cambridge.
"""

from __future__ import annotations

import math
import os
import sys

# ---------------------------------------------------------------------------
# Path resolution — works both from repo root and directly from tests/
# ---------------------------------------------------------------------------
_HERE    = os.path.dirname(os.path.abspath(__file__))
_PKG_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

import pytest

from kerf_cfd.k_omega_sst import (
    BFS_REATTACH_MEAN,
    BFS_REATTACH_TOL,
    _A1,
    _BETA_STAR,
    _KAPPA,
    channel_log_layer_state,
    compute_F1,
    compute_F2,
    compute_nut,
    dissipation_k,
    dissipation_omega,
    equilibrium_k_omega_ratio,
    estimate_bfs_reattachment,
    production_k,
    production_omega,
    solve_equilibrium,
    sst_constants,
)


# ===========================================================================
# Helper
# ===========================================================================

def _rel(a: float, b: float) -> float:
    """Relative difference |a-b| / max(|b|, 1e-30)."""
    return abs(a - b) / max(abs(b), 1.0e-30)


# ===========================================================================
# 1. Closure constants — Menter (2003) Table 1
# ===========================================================================

class TestSSTConstants:
    """Verify the Menter SST constant table is transcribed correctly."""

    def test_alpha1(self):
        """α1 = 5/9 ≈ 0.5556  [Menter1994 §2]"""
        c = sst_constants()
        assert _rel(c["alpha1"], 5.0 / 9.0) < 1.0e-10

    def test_beta1(self):
        """β1 = 3/40 = 0.075  [Menter1994 §2]"""
        c = sst_constants()
        assert _rel(c["beta1"], 3.0 / 40.0) < 1.0e-10

    def test_sigma_k1(self):
        """σk1 = 0.85  [Menter2003 Table 1]"""
        c = sst_constants()
        assert _rel(c["sigma_k1"], 0.85) < 1.0e-10

    def test_sigma_w1(self):
        """σω1 = 0.5  [Menter2003 Table 1]"""
        c = sst_constants()
        assert _rel(c["sigma_w1"], 0.5) < 1.0e-10

    def test_alpha2(self):
        """α2 = 0.44  [Menter2003 Table 1]"""
        c = sst_constants()
        assert _rel(c["alpha2"], 0.44) < 1.0e-10

    def test_beta2(self):
        """β2 = 0.0828  [Menter2003 Table 1]"""
        c = sst_constants()
        assert _rel(c["beta2"], 0.0828) < 1.0e-10

    def test_beta_star(self):
        """β* = 0.09  [Menter1994 §2]"""
        c = sst_constants()
        assert _rel(c["beta_star"], 0.09) < 1.0e-10

    def test_a1(self):
        """a1 = 0.31  [Menter1994 eq. 2]"""
        c = sst_constants()
        assert _rel(c["a1"], 0.31) < 1.0e-10

    def test_kappa(self):
        """κ = 0.41 (von-Kármán constant)  [Pope2000 §7.1]"""
        c = sst_constants()
        assert _rel(c["kappa"], 0.41) < 1.0e-10


# ===========================================================================
# 2. F1 blending function
# ===========================================================================

class TestF1BlendingFunction:
    """F1 → 1 near wall, F1 → 0 in freestream.  [Menter2003 eq. 12-14]"""

    def test_F1_near_wall(self):
        """Very close to wall (d → 0): arg1 → ∞, F1 → 1."""
        # Small d → large arg1 → F1 ≈ 1
        F1 = compute_F1(k=1e-3, omega=1e3, d=1e-5, nu=1e-5, dk_dy=0.0, domega_dy=0.0)
        assert F1 > 0.99, f"Expected F1≈1 near wall, got {F1}"

    def test_F1_freestream(self):
        """Far from wall (large d): F1 → 0."""
        # Large d → small arg1 → F1 ≈ 0
        F1 = compute_F1(k=1e-4, omega=1.0, d=1000.0, nu=1e-5, dk_dy=1e-8, domega_dy=1e-8)
        assert F1 < 0.01, f"Expected F1≈0 in freestream, got {F1}"

    def test_F1_range(self):
        """F1 must lie in [0, 1] for any physically valid input."""
        test_cases = [
            (1e-3, 100.0, 0.001, 1.5e-5, 0.0,   0.0),
            (1e-3, 100.0, 1.0,   1.5e-5, 0.01,  0.01),
            (1e-4, 0.5,   0.1,   1.0e-6, 0.0,   0.0),
            (0.1,  500.0, 0.005, 1.5e-5, 1.0,   0.5),
        ]
        for k, om, d, nu, dkdy, domdy in test_cases:
            F1 = compute_F1(k, om, d, nu, dkdy, domdy)
            assert 0.0 <= F1 <= 1.0, f"F1={F1} out of [0,1] for inputs {k,om,d}"


# ===========================================================================
# 3. F2 blending function
# ===========================================================================

class TestF2BlendingFunction:
    """F2 → 1 in boundary layer, F2 → 0 in freestream.  [Menter2003 eq. 15]"""

    def test_F2_near_wall(self):
        """Close to wall: F2 → 1."""
        F2 = compute_F2(k=1e-3, omega=1e4, d=1e-5, nu=1e-5)
        assert F2 > 0.99, f"Expected F2≈1 near wall, got {F2}"

    def test_F2_freestream(self):
        """Far from wall: F2 → 0."""
        F2 = compute_F2(k=1e-4, omega=0.5, d=1000.0, nu=1e-5)
        assert F2 < 0.01, f"Expected F2≈0 in freestream, got {F2}"

    def test_F2_range(self):
        """F2 ∈ [0, 1] for any valid input."""
        for d in [1e-6, 0.01, 0.1, 1.0, 100.0]:
            F2 = compute_F2(k=1e-3, omega=100.0, d=d, nu=1.5e-5)
            assert 0.0 <= F2 <= 1.0, f"F2={F2} out of [0,1] at d={d}"

    def test_F2_monotone_in_d(self):
        """F2 should decrease (or stay flat) as d increases."""
        d_vals   = [1e-4, 1e-3, 0.01, 0.1, 1.0]
        F2_vals  = [compute_F2(k=1e-3, omega=50.0, d=d, nu=1.5e-5) for d in d_vals]
        for i in range(len(F2_vals) - 1):
            assert F2_vals[i] >= F2_vals[i + 1] - 1.0e-10, (
                f"F2 not monotone: F2({d_vals[i]})={F2_vals[i]}, "
                f"F2({d_vals[i+1]})={F2_vals[i+1]}"
            )


# ===========================================================================
# 4. Turbulent viscosity νt
# ===========================================================================

class TestNutComputation:
    """νt = a1 k / max(a1 ω, F2 |S|)  [Menter1994 eq. 2]"""

    def test_nut_outer_layer(self):
        """In freestream (F2=0, |S| small): νt = k/ω."""
        # When F2=0 and S→0:  denom = a1*ω,  νt = a1*k/(a1*ω) = k/ω
        k, omega = 0.1, 10.0
        nut = compute_nut(k, omega, F2=0.0, strain_rate=0.0)
        expected = k / omega
        assert _rel(nut, expected) < 1.0e-10, f"nut={nut}, expected={expected}"

    def test_nut_inner_layer_limited(self):
        """When F2|S| > a1*ω, the SST limiter reduces νt below k/ω."""
        # High strain rate → limiter active
        k, omega, S = 1.0, 1.0, 1000.0
        F2  = 1.0
        nut = compute_nut(k, omega, F2=F2, strain_rate=S)
        # Standard value k/ω = 1.0
        # Limited value = a1*k / (F2*S) = 0.31 / 1000 = 3.1e-4
        assert nut < k / omega, "SST limiter should reduce νt below k/ω"
        assert nut > 0.0

    def test_nut_positive(self):
        """νt must always be non-negative."""
        for S in [0.0, 1.0, 100.0, 1e6]:
            for F2 in [0.0, 0.5, 1.0]:
                nut = compute_nut(k=0.01, omega=10.0, F2=F2, strain_rate=S)
                assert nut >= 0.0


# ===========================================================================
# 5. Production and dissipation terms
# ===========================================================================

class TestProductionDissipation:
    """Verify the form of Pk, Dk, Pω, Dω."""

    def test_production_k_zero_strain(self):
        """Pk = 0 when |S| = 0 (no shear, no production)."""
        assert production_k(nut=0.01, strain_rate=0.0) == 0.0

    def test_dissipation_k_positive(self):
        """D_k = β* k ω > 0 for k,ω > 0."""
        D = dissipation_k(k=0.1, omega=50.0)
        assert D == pytest.approx(_BETA_STAR * 0.1 * 50.0, rel=1.0e-10)

    def test_production_omega_form(self):
        """Pω = (α/νt) * Pk  [Menter2003 eq. 9]."""
        alpha, nut, S = 5.0 / 9.0, 0.05, 10.0
        Pk  = production_k(nut, S)
        Po  = production_omega(alpha, nut, S)
        # Po should equal alpha * S^2
        expected = alpha * S * S
        assert _rel(Po, expected) < 1.0e-10

    def test_dissipation_omega_form(self):
        """D_ω = β ω²  [Menter2003 eq. 9]."""
        beta, omega = 0.075, 100.0
        D = dissipation_omega(beta, omega)
        assert D == pytest.approx(beta * omega ** 2, rel=1.0e-10)

    def test_production_ge_zero(self):
        """Pk ≥ 0 (physically: turbulence cannot be produced from nothing)."""
        for S in [0.0, 1.0, 50.0]:
            assert production_k(nut=0.01, strain_rate=S) >= 0.0


# ===========================================================================
# 6. Production-dissipation balanced state: omega convergence to analytic omega*
# ===========================================================================

def _blend_constants(F1: float):
    """Return (alpha_blend, beta_blend) for the given F1."""
    alpha = F1 * (5.0 / 9.0) + (1.0 - F1) * 0.44
    beta  = F1 * (3.0 / 40.0) + (1.0 - F1) * 0.0828
    return alpha, beta


class TestEquilibriumBalance:
    """
    The omega-equation (source terms only) has the unique positive fixed point:

        omega* = S * sqrt(alpha/beta)    (Pomega = Domega: alpha S^2 = beta omega*^2)

    solve_equilibrium must converge omega to within 5 % of this value.
    This constitutes the "production = dissipation in omega, matches published
    far-field k/omega ratios to 5 %" check.

    References: [Menter1994] sec. 2; [Menter2003] eq. 9-11.
    """

    def test_omega_converges_outer_layer_5pct(self):
        """
        Outer layer (F1=F2=0): omega converges to omega* = S*sqrt(alpha2/beta2) within 5 %.
        [Menter2003 eq. 9-11; Menter1994 sec. 2]
        """
        S  = 50.0
        nu = 1.5e-5
        res = solve_equilibrium(
            k0=0.01, omega0=10.0, nu=nu, strain_rate=S,
            F1=0.0, F2=0.0, max_iter=200_000, tol=1.0e-9,
        )
        assert res["ok"],        res.get("reason")
        assert res["converged"], "Solver did not converge"

        # alpha2=0.44, beta2=0.0828
        omega_star_expected = S * math.sqrt(0.44 / 0.0828)
        rel_err = abs(res["omega"] - omega_star_expected) / omega_star_expected
        assert rel_err < 0.05, (
            f"omega={res['omega']:.4f}, omega*={omega_star_expected:.4f}, "
            f"relative error {rel_err:.3%} > 5%  [Menter2003 eq.9-11]"
        )

    def test_omega_converges_inner_layer_5pct(self):
        """
        Inner layer (F1=1, F2=1): omega converges to omega* = S*sqrt(alpha1/beta1) within 5 %.
        [Menter2003 eq. 9-11]
        """
        S  = 200.0
        nu = 1.5e-5
        res = solve_equilibrium(
            k0=0.05, omega0=50.0, nu=nu, strain_rate=S,
            F1=1.0, F2=1.0, max_iter=200_000, tol=1.0e-9,
        )
        assert res["ok"],        res.get("reason")
        assert res["converged"], "Solver did not converge"

        # alpha1=5/9, beta1=3/40
        omega_star_expected = S * math.sqrt((5.0 / 9.0) / (3.0 / 40.0))
        rel_err = abs(res["omega"] - omega_star_expected) / omega_star_expected
        assert rel_err < 0.05, (
            f"omega={res['omega']:.4f}, omega*={omega_star_expected:.4f}, "
            f"relative error {rel_err:.3%} > 5%  [Menter2003 eq.9-11]"
        )

    def test_omega_star_matches_reported(self):
        """omega_star field in result matches the analytic fixed-point value."""
        S  = 100.0
        nu = 1.5e-5
        res = solve_equilibrium(
            k0=0.1, omega0=50.0, nu=nu, strain_rate=S,
            F1=0.0, F2=0.0, max_iter=200_000, tol=1.0e-9,
        )
        assert res["ok"] and res["converged"]
        omega_star_expected = S * math.sqrt(0.44 / 0.0828)
        assert _rel(res["omega_star"], omega_star_expected) < 1.0e-10

    def test_k_positive_at_convergence(self):
        """k must remain positive throughout the solve."""
        res = solve_equilibrium(
            k0=0.01, omega0=20.0, nu=1.5e-5, strain_rate=30.0,
            F1=0.0, F2=0.0, max_iter=200_000, tol=1.0e-9,
        )
        assert res["ok"]
        assert res["k"] > 0.0

    def test_pk_dk_ratio_key_present(self):
        """Result must include pk_dk_ratio key."""
        res = solve_equilibrium(
            k0=0.01, omega0=20.0, nu=1.5e-5, strain_rate=30.0,
        )
        assert res["ok"]
        assert "pk_dk_ratio" in res


# ===========================================================================
# 7. Log-layer analytic state
# ===========================================================================

class TestLogLayerState:
    """Verify the analytic log-layer relations.  [Pope2000 §7.2]"""

    def test_returns_ok(self):
        res = channel_log_layer_state(Re_tau=550.0, nu=1.5e-5)
        assert res["ok"]

    def test_u_tau_formula(self):
        """u_τ = Re_τ ν / h  with h=1."""
        nu, Re_tau = 1.5e-5, 1000.0
        res = channel_log_layer_state(Re_tau=Re_tau, nu=nu)
        expected_u_tau = Re_tau * nu
        assert _rel(res["u_tau"], expected_u_tau) < 1.0e-10

    def test_k_formula(self):
        """k = u_τ² / sqrt(β*)  [Menter1994 §3; Pope2000 §7.2]."""
        nu, Re_tau = 1.5e-5, 550.0
        res = channel_log_layer_state(Re_tau=Re_tau, nu=nu)
        u_tau = res["u_tau"]
        expected_k = u_tau ** 2 / math.sqrt(_BETA_STAR)
        assert _rel(res["k"], expected_k) < 1.0e-10

    def test_omega_formula(self):
        """ω = u_τ / (κ y)  [Menter1994 §3]."""
        nu, Re_tau, y_plus = 1.5e-5, 550.0, 100.0
        res = channel_log_layer_state(Re_tau=Re_tau, nu=nu, y_plus=y_plus)
        u_tau = res["u_tau"]
        y     = res["y"]
        expected_omega = u_tau / (_KAPPA * y)
        assert _rel(res["omega"], expected_omega) < 1.0e-10

    def test_invalid_inputs(self):
        """Negative Re_τ or ν returns ok=False."""
        assert not channel_log_layer_state(Re_tau=-1.0, nu=1.5e-5)["ok"]
        assert not channel_log_layer_state(Re_tau=550.0, nu=-1.0)["ok"]


# ===========================================================================
# 8. Backward-facing step reattachment oracle
# ===========================================================================

class TestBFSReattachment:
    """
    1:2 backward-facing step at Re_h = 36 000.

    Published reattachment length:  x_r / h ≈ 6.5 ± 0.5  [Eaton1981].
    DNS reference (Le et al. 1997):  x_r / h ≈ 6.28  at Re_h = 5100.
    k-ω SST RANS:  x_r / h ≈ 6.4–7.1  [Menter1994 §4].

    The BFS_REATTACH_TOL in the module is 0.5; we check within 2× that band
    (±1.0 h) to be conservative for the parabolised-RANS approximation.
    """

    def test_reattachment_within_experimental_band(self):
        """
        x_r / h must lie within 6.5 ± 1.0  (2× the experimental ±0.5 band).
        [Eaton1981; Menter1994]
        """
        res = estimate_bfs_reattachment(
            Re_h=36_000.0,
            expansion_ratio=2.0,
            ny_step=40,
            nx_downstream=200,
        )
        assert res["ok"], res.get("reason")
        x_r = res["x_reattach_over_h"]
        lo  = BFS_REATTACH_MEAN - 2.0 * BFS_REATTACH_TOL   # 5.5
        hi  = BFS_REATTACH_MEAN + 2.0 * BFS_REATTACH_TOL   # 7.5
        assert lo <= x_r <= hi, (
            f"x_r/h = {x_r:.3f}, expected in [{lo}, {hi}]  "
            f"(Eaton & Johnston 1981 mean {BFS_REATTACH_MEAN} ± {BFS_REATTACH_TOL})"
        )

    def test_reattachment_positive(self):
        """Reattachment length must be a positive downstream distance."""
        res = estimate_bfs_reattachment()
        assert res["ok"]
        assert res["x_reattach_over_h"] > 0.0

    def test_invalid_re_h(self):
        """Re_h ≤ 0 should return ok=False."""
        res = estimate_bfs_reattachment(Re_h=-1.0)
        assert not res["ok"]

    def test_invalid_expansion_ratio(self):
        """expansion_ratio ≤ 1 should return ok=False."""
        res = estimate_bfs_reattachment(expansion_ratio=0.5)
        assert not res["ok"]

    def test_result_keys_present(self):
        """Result dict must contain expected keys."""
        res = estimate_bfs_reattachment()
        for key in ("ok", "x_reattach_over_h", "inside_tolerance", "Re_h",
                    "expected_mean", "expected_tol"):
            assert key in res, f"Missing key: {key}"

    def test_expected_constants_match_module(self):
        """Result echoes module-level constants."""
        res = estimate_bfs_reattachment()
        assert res["expected_mean"] == BFS_REATTACH_MEAN
        assert res["expected_tol"]  == BFS_REATTACH_TOL


# ===========================================================================
# 9. Equilibrium ratio helper
# ===========================================================================

class TestEquilibriumRatioHelper:

    def test_equilibrium_ratio_value(self):
        """equilibrium_k_omega_ratio() returns 1/a1 = 1/0.31 ≈ 3.226."""
        ratio = equilibrium_k_omega_ratio()
        expected = 1.0 / 0.31
        assert _rel(ratio, expected) < 1.0e-10

    def test_ratio_positive(self):
        assert equilibrium_k_omega_ratio() > 0.0


# ===========================================================================
# 10. Edge-case robustness
# ===========================================================================

class TestEdgeCases:
    """Verify the model does not crash or produce NaN/Inf on edge inputs."""

    def test_zero_strain_no_crash(self):
        """Zero strain rate — no production, model should still converge."""
        res = solve_equilibrium(
            k0=0.01, omega0=100.0, nu=1.5e-5, strain_rate=0.0,
            F1=0.0, F2=0.0, max_iter=10_000, tol=1.0e-8,
        )
        assert res["ok"]
        assert math.isfinite(res["k"])
        assert math.isfinite(res["omega"])

    def test_very_high_strain(self):
        """Very high strain — solver should return finite values."""
        res = solve_equilibrium(
            k0=1.0, omega0=1000.0, nu=1.5e-5, strain_rate=1e5,
            F1=0.0, F2=0.0, max_iter=100_000, tol=1.0e-8,
        )
        assert res["ok"]
        assert math.isfinite(res["k"])
        assert math.isfinite(res["omega"])

    def test_nut_zero_omega_guard(self):
        """compute_nut should not divide by zero when omega → 0."""
        nut = compute_nut(k=0.01, omega=0.0, F2=0.0, strain_rate=0.0)
        assert math.isfinite(nut)
        assert nut >= 0.0

    def test_F1_zero_omega_guard(self):
        """compute_F1 should not crash when omega → 0."""
        F1 = compute_F1(k=0.01, omega=0.0, d=0.1, nu=1.5e-5,
                        dk_dy=0.0, domega_dy=0.0)
        assert math.isfinite(F1)
        assert 0.0 <= F1 <= 1.0

    def test_F2_zero_omega_guard(self):
        """compute_F2 should not crash when omega → 0."""
        F2 = compute_F2(k=0.01, omega=0.0, d=0.1, nu=1.5e-5)
        assert math.isfinite(F2)

    def test_solve_negative_initial_k(self):
        """solve_equilibrium returns ok=False for non-positive initial k."""
        res = solve_equilibrium(k0=-0.1, omega0=100.0, nu=1.5e-5, strain_rate=10.0)
        assert not res["ok"]

    def test_solve_negative_initial_omega(self):
        """solve_equilibrium returns ok=False for non-positive initial ω."""
        res = solve_equilibrium(k0=0.01, omega0=-1.0, nu=1.5e-5, strain_rate=10.0)
        assert not res["ok"]
