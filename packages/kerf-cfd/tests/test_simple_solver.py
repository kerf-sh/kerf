"""
Test suite for kerf_cfd.simple_solver — FV-SIMPLE incompressible RANS solver.

Validates the staggered-grid SIMPLE solver against the canonical
lid-driven cavity benchmark of Ghia, Ghia & Shin (1982).

References
----------
[Patankar1980]  Patankar S. V., *Numerical Heat Transfer and Fluid Flow*,
                Hemisphere, 1980.  SIMPLE algorithm §6.7.
[Ferziger2002]  Ferziger J. H., Perić M., *Computational Methods for Fluid
                Dynamics*, 3rd ed., Springer, 2002.  §7.3-7.4.
[Versteeg1995]  Versteeg H. K., Malalasekera W., *An Introduction to
                Computational Fluid Dynamics*, Longman, 1995.  Ch. 6.
[RhieChow1983]  Rhie C. M., Chow W. L., AIAA J. 21 (11) (1983) 1525-1532.
[Ghia1982]      Ghia U., Ghia K. N., Shin C. T., J. Comput. Phys. 48 (1982)
                387-411.  Lid-driven cavity reference data Re = 100.
"""

from __future__ import annotations

import math
import os
import sys

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
_HERE    = os.path.dirname(os.path.abspath(__file__))
_PKG_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

import pytest

from kerf_cfd.simple_solver import (
    GHIA_INTERIOR_MASK,
    GHIA_RE100_U,
    GHIA_RE100_Y,
    GHIA_TOLERANCE,
    SolverConfig,
    SolverState,
    _interp1d,
    compare_ghia_re100,
    max_continuity_residual,
    solve_simple,
    u_on_vertical_centreline,
    v_on_horizontal_centreline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cavity_32x32() -> dict:
    """Run the 32 × 32 Re=100 cavity once and cache result."""
    return compare_ghia_re100(nx=32, ny=32, max_outer=4000, tol_residual=1.0e-7)


# Module-level fixture so the solver runs only once across all tests
_RESULT_32 = None


def _get_result() -> dict:
    global _RESULT_32
    if _RESULT_32 is None:
        _RESULT_32 = _run_cavity_32x32()
    return _RESULT_32


# ===========================================================================
# 1. Solver configuration sanity
# ===========================================================================

class TestSolverConfig:
    """Basic config validation."""

    def test_default_config_creates(self):
        cfg = SolverConfig()
        assert cfg.nx == 32
        assert cfg.ny == 32

    def test_custom_re(self):
        cfg = SolverConfig(Re=400.0)
        assert cfg.Re == 400.0

    def test_nu_computed_correctly(self):
        """ν = U_ref·L / Re = 1·1/100 = 0.01 for default cavity."""
        cfg = SolverConfig(nx=8, ny=8, Re=100.0, U_ref=1.0, L=1.0)
        state = solve_simple(cfg)
        assert math.isclose(state.nu, 0.01, rel_tol=1.0e-9)


# ===========================================================================
# 2. Solver state structure
# ===========================================================================

class TestSolverStateStructure:
    """Verify output array shapes and basic physical constraints."""

    def test_u_array_shape(self):
        """u array is [ny] × [nx+1] (staggered east faces)."""
        cfg = SolverConfig(nx=16, ny=16, max_outer=10)
        state = solve_simple(cfg)
        assert len(state.u) == 16
        assert len(state.u[0]) == 17   # nx+1

    def test_v_array_shape(self):
        """v array is [ny+1] × [nx] (staggered north faces)."""
        cfg = SolverConfig(nx=16, ny=16, max_outer=10)
        state = solve_simple(cfg)
        assert len(state.v) == 17      # ny+1
        assert len(state.v[0]) == 16

    def test_p_array_shape(self):
        """p array is [ny] × [nx] (cell centres)."""
        cfg = SolverConfig(nx=16, ny=16, max_outer=10)
        state = solve_simple(cfg)
        assert len(state.p) == 16
        assert len(state.p[0]) == 16

    def test_residual_list_grows(self):
        cfg = SolverConfig(nx=8, ny=8, max_outer=20)
        state = solve_simple(cfg)
        assert len(state.residual_u) == state.n_iter

    def test_n_iter_positive(self):
        cfg = SolverConfig(nx=8, ny=8, max_outer=5)
        state = solve_simple(cfg)
        assert state.n_iter >= 1


# ===========================================================================
# 3. Wall boundary conditions (no-slip)
# ===========================================================================

class TestBoundaryConditions:
    """No-slip walls and lid velocity must be enforced."""

    def setup_method(self):
        """Small 16×16 cavity for fast BC checks."""
        cfg = SolverConfig(
            nx=16, ny=16, Re=100.0,
            alpha_u=0.7, alpha_p=0.3,
            max_outer=500, tol_residual=1.0e-5,
        )
        self.state = solve_simple(cfg)
        self.nx = 16
        self.ny = 16

    def test_left_wall_u_zero(self):
        """u = 0 at left wall face (i=0) for all j."""
        for j in range(self.ny):
            assert self.state.u[j][0] == 0.0, f"u[{j}][0] = {self.state.u[j][0]}"

    def test_right_wall_u_zero(self):
        """u = 0 at right wall face (i=nx) for all j."""
        for j in range(self.ny):
            assert self.state.u[j][self.nx] == 0.0

    def test_bottom_wall_v_zero(self):
        """v = 0 at bottom wall face (j=0)."""
        for i in range(self.nx):
            assert self.state.v[0][i] == 0.0

    def test_top_wall_v_zero(self):
        """v = 0 at top wall face (j=ny): no flow through solid lid."""
        for i in range(self.nx):
            assert self.state.v[self.ny][i] == 0.0

    def test_velocity_finite(self):
        """All velocity values must be finite (no NaN/Inf)."""
        for j in range(self.ny):
            for i in range(self.nx + 1):
                assert math.isfinite(self.state.u[j][i])
        for j in range(self.ny + 1):
            for i in range(self.nx):
                assert math.isfinite(self.state.v[j][i])

    def test_pressure_finite(self):
        """Pressure values must be finite."""
        for j in range(self.ny):
            for i in range(self.nx):
                assert math.isfinite(self.state.p[j][i])


# ===========================================================================
# 4. Mass conservation (divergence-free)
# ===========================================================================

class TestMassConservation:
    """
    The staggered-grid SIMPLE enforces exact discrete continuity.
    After convergence, max|(ue−uw)Δy + (vn−vs)Δx| must be near zero.

    Reference: Patankar (1980) §6.7; Ferziger & Perić (2002) §7.4.
    """

    def test_continuity_satisfied_32x32(self):
        """
        Max continuity residual ≤ 1 × 10⁻⁴ on converged 32×32 mesh.

        The staggered grid provides an exact discrete continuity statement;
        the small residual comes from incomplete p' equation convergence
        (80 inner Gauss-Seidel sweeps).  [Patankar1980 §6.7]
        """
        r = _get_result()
        div = r["max_div"]
        assert div <= 1.0e-4, (
            f"Max divergence {div:.2e} > 1e-4 — pressure-correction not enforcing "
            f"continuity.  Check Rhie-Chow d-coefficients or inner-loop count."
        )

    def test_continuity_small_mesh(self):
        """Mass residual ≤ 1e-4 on a 16×16 mesh (fast)."""
        cfg = SolverConfig(nx=16, ny=16, Re=100.0,
                           alpha_u=0.7, alpha_p=0.3,
                           max_outer=1000, tol_residual=1.0e-7,
                           n_inner_p=80)
        state = solve_simple(cfg)
        div = max_continuity_residual(state, nx=16, ny=16)
        assert div <= 1.0e-4, f"16×16 divergence {div:.2e} too large"


# ===========================================================================
# 5. Qualitative flow physics
# ===========================================================================

class TestFlowPhysics:
    """
    The lid-driven cavity at Re=100 has a primary clockwise vortex.
    The u-velocity profile on x=0.5 must be:
      - Positive near the lid (driven by lid)
      - Negative in the lower interior (recirculation)
    [Ghia1982; Patankar1980 §6.7]
    """

    def test_u_positive_near_lid(self):
        """
        u > 0 in the upper quarter of the cavity (y > 0.75) on x=0.5.
        Lid drives positive u flow.  [Ghia1982 Table 1: u=0.84 at y=0.98]
        """
        r = _get_result()
        # The y-grid has u-faces at y=(j+0.5)/32; find those above y=0.75
        # u_kerf at y=0.8516 should be positive (Ghia=0.23)
        idx = GHIA_RE100_Y.index(0.8516)
        assert r["u_kerf"][idx] > 0.05, (
            f"u at y=0.85 = {r['u_kerf'][idx]:.4f}, expected > 0 (lid-driven region)"
        )

    def test_u_negative_in_core(self):
        """
        u < 0 in the recirculating core (y ≈ 0.5) on x=0.5.
        Return flow is leftward.  [Ghia1982 Table 1: u=−0.21 at y=0.45]
        """
        r = _get_result()
        idx = GHIA_RE100_Y.index(0.5000)
        assert r["u_kerf"][idx] < -0.03, (
            f"u at y=0.5 = {r['u_kerf'][idx]:.4f}, expected negative (recirculation)"
        )

    def test_u_zero_at_bottom(self):
        """u = 0 at bottom wall (no-slip).  [Ghia1982: u=0 at y=0]"""
        r = _get_result()
        idx = GHIA_RE100_Y.index(0.0000)
        assert abs(r["u_kerf"][idx]) < 0.05, (
            f"u at y=0 = {r['u_kerf'][idx]:.4f}, expected ≈ 0"
        )

    def test_circulation_sign(self):
        """
        Primary vortex is clockwise: lid moves right → fluid falls at right wall.
        On y=0.5 centreline, v at x≈0.75 should be NEGATIVE (downward).

        Ghia (1982) Table 2 v-velocity on y=0.5:
          At x=0.7656 (near right wall): v ≈ −0.175  [Ghia1982 Table 2]
        Clockwise vortex: u>0 near top, v<0 near right, u<0 in core, v>0 near left.
        [Ghia1982; Patankar1980 §6.7]
        """
        cfg = SolverConfig(nx=32, ny=32, Re=100.0,
                           max_outer=4000, tol_residual=1.0e-7)
        state = solve_simple(cfg)
        x_c, v_c = v_on_horizontal_centreline(state, nx=32, ny=32)
        # x ≈ 0.75 → i=23 → x = (23+0.5)/32 ≈ 0.734; v < 0 (fluid falling)
        v_right = v_c[23]
        assert v_right < -0.05, (
            f"v at x≈0.73 = {v_right:.4f}, expected < −0.05 (downward, clockwise vortex)"
        )
        # And v > 0 on the left side (rising)
        v_left = v_c[6]   # x = (6+0.5)/32 ≈ 0.203
        assert v_left > 0.05, (
            f"v at x≈0.20 = {v_left:.4f}, expected > +0.05 (upward, clockwise vortex)"
        )


# ===========================================================================
# 6. Numerical oracle: Ghia (1982) benchmark, Re = 100
# ===========================================================================

class TestGhiaBenchmark:
    """
    Quantitative validation against the canonical Ghia et al. (1982) benchmark.

    Grid:      32 × 32 uniform Cartesian (staggered MAC)
    Scheme:    First-order upwind convection + second-order central diffusion
    Coupling:  SIMPLE (Patankar 1980 §6.7)
    Tolerance: max|u_kerf − u_Ghia| ≤ 0.06 U_lid  at interior points
               (points away from the lid boundary layer where upwind smearing
               is negligible; see Ferziger & Perić 2002 §7.5 for context)

    The near-lid region (y > 0.95) is EXCLUDED from the quantitative tolerance
    because first-order upwind adds O(Δx) artificial viscosity that smears
    the thin lid boundary layer on coarse meshes.  This is a known property
    of the upwind scheme, not a solver error.

    References: [Ghia1982]; [Patankar1980 §5.2]; [Ferziger2002 §7.5].
    """

    def test_solver_converged(self):
        """Solver must converge within 4 000 outer iterations."""
        r = _get_result()
        assert r["converged"], (
            f"Solver did not converge in {r['n_iter']} iterations.  "
            f"Last u-residual: check solver settings."
        )

    def test_within_tolerance_interior(self):
        """
        max|u_kerf − u_Ghia| ≤ 0.06 U_lid at interior validation points.

        Interior = Ghia table points with y ∈ [0.07, 0.85] (away from lid).
        Tolerance 0.06 is consistent with 32×32 first-order upwind accuracy
        documented in Ferziger & Perić (2002) §7.5.

        [Ghia1982; Patankar1980; Ferziger2002]
        """
        r = _get_result()
        assert r["within_tolerance"], (
            f"Interior max error = {r['max_error_interior']:.4f}, "
            f"tolerance = {r['tolerance']:.4f}.  "
            f"Ghia (1982) reference: J. Comput. Phys. 48 (1982) 387-411."
        )

    def test_u_at_y0_8516_within_tol(self):
        """
        u(y=0.8516) ∈ [Ghia ± 0.06].

        Ghia (1982) Table 1, Re=100: u = +0.23151 at y = 0.8516.
        """
        r = _get_result()
        k = GHIA_RE100_Y.index(0.8516)
        err = abs(r["u_kerf"][k] - GHIA_RE100_U[k])
        assert err <= GHIA_TOLERANCE, (
            f"y=0.8516: |u_kerf={r['u_kerf'][k]:.5f} − u_Ghia={GHIA_RE100_U[k]:.5f}| "
            f"= {err:.5f} > {GHIA_TOLERANCE}  [Ghia1982 Table 1]"
        )

    def test_u_at_y0_5000_within_tol(self):
        """
        u(y=0.5) ∈ [Ghia ± 0.06].

        Ghia (1982) Table 1, Re=100: u = −0.20581 at y = 0.5000.
        """
        r = _get_result()
        k = GHIA_RE100_Y.index(0.5000)
        err = abs(r["u_kerf"][k] - GHIA_RE100_U[k])
        assert err <= GHIA_TOLERANCE, (
            f"y=0.50: |u_kerf={r['u_kerf'][k]:.5f} − u_Ghia={GHIA_RE100_U[k]:.5f}| "
            f"= {err:.5f} > {GHIA_TOLERANCE}  [Ghia1982 Table 1]"
        )

    def test_u_at_y0_2813_within_tol(self):
        """
        u(y=0.2813) ∈ [Ghia ± 0.06].

        Ghia (1982) Table 1, Re=100: u = −0.15662 at y = 0.2813.
        """
        r = _get_result()
        k = GHIA_RE100_Y.index(0.2813)
        err = abs(r["u_kerf"][k] - GHIA_RE100_U[k])
        assert err <= GHIA_TOLERANCE, (
            f"y=0.28: err={err:.5f} > {GHIA_TOLERANCE}  [Ghia1982 Table 1]"
        )

    def test_error_report_structure(self):
        """compare_ghia_re100 must return all required keys."""
        r = _get_result()
        for key in ("ok", "converged", "n_iter", "nu", "max_div",
                    "max_error_interior", "max_error_all",
                    "tolerance", "within_tolerance",
                    "errors", "y_ghia", "u_ghia", "u_kerf", "reference"):
            assert key in r, f"Missing key in result dict: {key}"

    def test_reference_cites_ghia(self):
        """Reference string must cite Ghia 1982."""
        r = _get_result()
        assert "Ghia" in r["reference"]
        assert "1982" in r["reference"]

    def test_errors_list_length_matches_ghia(self):
        """errors list must have same length as GHIA_RE100_Y."""
        r = _get_result()
        assert len(r["errors"])  == len(GHIA_RE100_Y)
        assert len(r["u_kerf"]) == len(GHIA_RE100_Y)

    def test_nu_matches_re(self):
        """ν = U·L/Re = 1·1/100 = 0.01 for Re=100."""
        r = _get_result()
        assert math.isclose(r["nu"], 0.01, rel_tol=1.0e-9), (
            f"ν = {r['nu']}, expected 0.01 for Re=100"
        )


# ===========================================================================
# 7. Interpolation helper
# ===========================================================================

class TestInterpolation:
    """Verify the 1-D linear interpolation used for Ghia comparison."""

    def test_exact_at_node(self):
        xs = [0.0, 0.5, 1.0]
        ys = [0.0, 1.0, 0.0]
        assert _interp1d(xs, ys, 0.5) == pytest.approx(1.0)

    def test_linear_midpoint(self):
        xs = [0.0, 1.0]
        ys = [0.0, 2.0]
        assert _interp1d(xs, ys, 0.5) == pytest.approx(1.0)

    def test_clamp_below(self):
        xs = [0.0, 1.0]
        ys = [3.0, 5.0]
        assert _interp1d(xs, ys, -1.0) == pytest.approx(3.0)

    def test_clamp_above(self):
        xs = [0.0, 1.0]
        ys = [3.0, 5.0]
        assert _interp1d(xs, ys, 2.0) == pytest.approx(5.0)


# ===========================================================================
# 8. Post-processing helpers
# ===========================================================================

class TestPostProcessing:
    """Verify centreline extraction functions."""

    def test_u_centreline_length(self):
        """u_on_vertical_centreline returns ny points."""
        r = _get_result()
        # Re-run to get state
        cfg = SolverConfig(nx=32, ny=32, max_outer=4000, tol_residual=1.0e-7)
        state = solve_simple(cfg)
        y_c, u_c = u_on_vertical_centreline(state, nx=32, ny=32)
        assert len(y_c) == 32
        assert len(u_c) == 32

    def test_v_centreline_length(self):
        """v_on_horizontal_centreline returns nx points."""
        cfg = SolverConfig(nx=32, ny=32, max_outer=4000, tol_residual=1.0e-7)
        state = solve_simple(cfg)
        x_c, v_c = v_on_horizontal_centreline(state, nx=32, ny=32)
        assert len(x_c) == 32
        assert len(v_c) == 32

    def test_u_centreline_y_range(self):
        """y coordinates in [0, 1] for unit-square cavity."""
        cfg = SolverConfig(nx=16, ny=16, max_outer=10)
        state = solve_simple(cfg)
        y_c, _ = u_on_vertical_centreline(state, nx=16, ny=16)
        assert y_c[0]  > 0.0
        assert y_c[-1] < 1.0


# ===========================================================================
# 9. Convergence history
# ===========================================================================

class TestConvergenceHistory:
    """Verify residuals are stored and decrease monotonically (trend)."""

    def test_residual_positive(self):
        """All residuals must be non-negative."""
        r = _get_result()
        cfg = SolverConfig(nx=16, ny=16, max_outer=200, tol_residual=1.0e-5)
        state = solve_simple(cfg)
        assert all(x >= 0 for x in state.residual_u)

    def test_residual_decreases_trend(self):
        """Average of last-10 residuals < average of first-10 (solver converging)."""
        cfg = SolverConfig(nx=16, ny=16, max_outer=500, tol_residual=1.0e-6)
        state = solve_simple(cfg)
        if len(state.residual_u) >= 20:
            first_avg = sum(state.residual_u[:10]) / 10
            last_avg  = sum(state.residual_u[-10:]) / 10
            assert last_avg < first_avg, (
                "Residual not decreasing: solver may be diverging"
            )


# ===========================================================================
# 10. GHIA mask and module constants
# ===========================================================================

class TestGhiaConstants:
    """Verify Ghia reference data integrity."""

    def test_y_and_u_same_length(self):
        assert len(GHIA_RE100_Y) == len(GHIA_RE100_U)

    def test_mask_same_length(self):
        assert len(GHIA_INTERIOR_MASK) == len(GHIA_RE100_Y)

    def test_lid_excluded(self):
        """y = 1.0 (lid) must be excluded from interior mask."""
        idx = GHIA_RE100_Y.index(1.0000)
        assert not GHIA_INTERIOR_MASK[idx]

    def test_bottom_excluded(self):
        """y = 0.0 (bottom wall) excluded from interior mask."""
        idx = GHIA_RE100_Y.index(0.0000)
        assert not GHIA_INTERIOR_MASK[idx]

    def test_bulk_included(self):
        """y = 0.5 (bulk flow) included in interior mask."""
        idx = GHIA_RE100_Y.index(0.5000)
        assert GHIA_INTERIOR_MASK[idx]

    def test_tolerance_positive(self):
        assert GHIA_TOLERANCE > 0.0

    def test_u_at_lid_is_one(self):
        """Ghia Table 1: u = 1.0 at y = 1.0 (lid)."""
        idx = GHIA_RE100_Y.index(1.0000)
        assert GHIA_RE100_U[idx] == pytest.approx(1.0)

    def test_u_at_wall_is_zero(self):
        """Ghia Table 1: u = 0.0 at y = 0.0 (wall)."""
        idx = GHIA_RE100_Y.index(0.0000)
        assert GHIA_RE100_U[idx] == pytest.approx(0.0)
