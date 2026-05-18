"""
Tests for kerf_cfd.heat_transfer.

Two analytic oracle test groups:

1. Composite-wall conjugate heat transfer (3 layers) — series-resistance oracle.
   The analytic solution is exact; tolerance 0.1 % on q_flux and interface
   temperatures.

2. 2-D natural convection in a square cavity (Ra=10⁴, Pr=0.71) — de Vahl Davis
   (1983) benchmark Nu_avg = 2.243; tolerance 3 %.

References
----------
[dVD83]  de Vahl Davis G., "Natural convection of air in a square cavity: a
         bench mark numerical solution", Int. J. Numer. Meth. Fluids 3 (1983)
         249–264.
[Incrop]  Incropera F. P. et al., Fundamentals of Heat and Mass Transfer,
          7th ed., Wiley (2011), Chapter 3.
"""

from __future__ import annotations

import math
import sys
import os

# ---------------------------------------------------------------------------
# Ensure the package is importable whether tests are run from repo root or
# from the package directory.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

import pytest

from kerf_cfd.heat_transfer import (
    CompositeWallCHT,
    CavityNaturalConvection,
    cavity_nusselt,
    composite_wall_heat_flux,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _rel_err(computed: float, reference: float) -> float:
    """Relative error |computed − reference| / |reference|."""
    if reference == 0.0:
        return abs(computed)
    return abs(computed - reference) / abs(reference)


# ===========================================================================
# 1.  Composite-wall conjugate heat transfer — analytic series-resistance
# ===========================================================================
#
# Oracle derivation (Incropera Ch. 3, eq. 3.19):
#
#   q = (T_hot − T_cold) / R_total
#   R_total = Σ (t_i / k_i)
#   T_interface_k = T_hot − q * Σ_{i=0}^{k-1} (t_i / k_i)
#
# ===========================================================================

class TestCompositeWallCHT:
    """Series-resistance oracle for a 3-layer composite wall."""

    # 3-layer wall: steel | insulation | concrete
    LAYERS = [
        {"thickness": 0.010, "k": 50.0},    # steel,      R = 0.010/50    = 2.0e-4
        {"thickness": 0.050, "k":  0.04},   # insulation, R = 0.050/0.04  = 1.25
        {"thickness": 0.003, "k":  1.0},    # concrete,   R = 0.003/1.0   = 3.0e-3
    ]
    T_HOT  = 300.0   # °C
    T_COLD =  20.0   # °C

    @staticmethod
    def _oracle(layers, T_hot, T_cold):
        """Exact analytic solution via series resistance."""
        R_layers = [lyr["thickness"] / lyr["k"] for lyr in layers]
        R_total  = sum(R_layers)
        q_flux   = (T_hot - T_cold) / R_total
        T_ifaces = [T_hot]
        T_cur    = T_hot
        for R in R_layers:
            T_cur -= q_flux * R
            T_ifaces.append(T_cur)
        return {"q_flux": q_flux, "T_interfaces": T_ifaces, "R_total": R_total}

    def test_q_flux_matches_oracle(self):
        """Heat flux must match series-resistance oracle to 0.1 %."""
        ref = self._oracle(self.LAYERS, self.T_HOT, self.T_COLD)
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        assert _rel_err(result["q_flux"], ref["q_flux"]) < 1e-3, (
            f"q_flux mismatch: {result['q_flux']:.6g} vs oracle {ref['q_flux']:.6g}"
        )

    def test_R_total_matches_oracle(self):
        """R_total must match oracle to 0.1 %."""
        ref = self._oracle(self.LAYERS, self.T_HOT, self.T_COLD)
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        assert _rel_err(result["R_total"], ref["R_total"]) < 1e-3

    def test_interface_temperatures_match_oracle(self):
        """All interface temperatures must match oracle to 0.1 %."""
        ref = self._oracle(self.LAYERS, self.T_HOT, self.T_COLD)
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        assert len(result["T_interfaces"]) == len(ref["T_interfaces"])
        for k, (computed, reference) in enumerate(
            zip(result["T_interfaces"], ref["T_interfaces"])
        ):
            err = _rel_err(computed, reference)
            assert err < 1e-3, (
                f"Interface {k}: T={computed:.4f} vs oracle {reference:.4f} "
                f"(rel err {err:.2e})"
            )

    def test_cold_surface_temperature_matches_T_cold(self):
        """Last interface temperature must equal T_cold."""
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        last_T = result["T_interfaces"][-1]
        assert _rel_err(last_T, self.T_COLD) < 1e-9, (
            f"Last T_interface={last_T} should equal T_cold={self.T_COLD}"
        )

    def test_number_of_interfaces(self):
        """N layers → N+1 interface temperatures (left wall + N interiors + right wall)."""
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        assert len(result["T_interfaces"]) == len(self.LAYERS) + 1

    def test_convective_bc_both_sides(self):
        """Convective BCs on both sides: q = (T_fl_hot − T_fl_cold) / R_total."""
        h_left  = 500.0
        h_right =  10.0
        T_fl_l  = 300.0
        T_fl_r  =  20.0
        layers = self.LAYERS
        R_conv_l = 1.0 / h_left
        R_conv_r = 1.0 / h_right
        R_solid = sum(lyr["thickness"] / lyr["k"] for lyr in layers)
        R_total_ref = R_conv_l + R_solid + R_conv_r
        q_ref = (T_fl_l - T_fl_r) / R_total_ref

        wall = CompositeWallCHT(
            layers=layers,
            h_left=h_left, T_fluid_left=T_fl_l,
            h_right=h_right, T_fluid_right=T_fl_r,
        )
        result = wall.solve()
        assert result["ok"] is True
        assert _rel_err(result["q_flux"], q_ref) < 1e-3, (
            f"q_flux={result['q_flux']:.6g} vs oracle {q_ref:.6g}"
        )
        assert _rel_err(result["R_total"], R_total_ref) < 1e-3

    def test_single_layer(self):
        """1-layer wall: q = k * ΔT / t."""
        layer = [{"thickness": 0.1, "k": 2.0}]
        T_hot, T_cold = 100.0, 0.0
        q_ref = 2.0 * (100.0 - 0.0) / 0.1   # = 2000 W/m²
        result = composite_wall_heat_flux(layer, T_hot, T_cold)
        assert result["ok"] is True
        assert _rel_err(result["q_flux"], q_ref) < 1e-9

    def test_heat_flows_from_hot_to_cold(self):
        """q_flux must be positive (hot left → cold right)."""
        result = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        assert result["ok"] is True
        assert result["q_flux"] > 0.0

    def test_zero_layers_returns_error(self):
        """Empty layers list → error."""
        result = composite_wall_heat_flux([], 100.0, 0.0)
        assert result["ok"] is False

    def test_negative_thickness_returns_error(self):
        """Non-positive thickness → error."""
        result = composite_wall_heat_flux([{"thickness": -0.01, "k": 1.0}], 100.0, 0.0)
        assert result["ok"] is False

    def test_zero_conductivity_returns_error(self):
        """Non-positive conductivity → error."""
        result = composite_wall_heat_flux([{"thickness": 0.01, "k": 0.0}], 100.0, 0.0)
        assert result["ok"] is False

    def test_missing_T_left_returns_error(self):
        """Missing Dirichlet T_left when h_left==0 → error."""
        wall = CompositeWallCHT(layers=self.LAYERS, h_right=10.0, T_fluid_right=20.0)
        result = wall.solve()
        assert result["ok"] is False

    def test_reverse_temperature_gradient(self):
        """Swapping hot/cold reverses the sign of q_flux."""
        r1 = composite_wall_heat_flux(self.LAYERS, self.T_HOT, self.T_COLD)
        r2 = composite_wall_heat_flux(self.LAYERS, self.T_COLD, self.T_HOT)
        assert r1["ok"] is True and r2["ok"] is True
        assert abs(r1["q_flux"] + r2["q_flux"]) < 1e-9

    def test_five_layer_wall(self):
        """5-layer wall series-resistance oracle."""
        layers = [
            {"thickness": 0.005, "k": 60.0},
            {"thickness": 0.020, "k":  0.8},
            {"thickness": 0.100, "k":  0.03},
            {"thickness": 0.020, "k":  0.8},
            {"thickness": 0.005, "k": 60.0},
        ]
        T_hot, T_cold = 200.0, 10.0
        ref = TestCompositeWallCHT._oracle(layers, T_hot, T_cold)
        result = composite_wall_heat_flux(layers, T_hot, T_cold)
        assert result["ok"] is True
        assert _rel_err(result["q_flux"], ref["q_flux"]) < 1e-3

    def test_equal_temperatures_zero_flux(self):
        """T_hot == T_cold → q_flux == 0."""
        result = composite_wall_heat_flux(self.LAYERS, 100.0, 100.0)
        assert result["ok"] is True
        assert abs(result["q_flux"]) < 1e-12


# ===========================================================================
# 2.  2-D natural convection — de Vahl Davis (1983) benchmark
# ===========================================================================
#
# Ra = 10⁴, Pr = 0.71 → Nu_avg = 2.243  (de Vahl Davis 1983 Table 1)
# Tolerance: ±3 % (absolute on Nu_avg) per task specification.
#
# Grid n=32 is sufficient for Ra=10⁴ (boundary layer δ ≈ 0.1 L).
# ===========================================================================

# Reference value
_NU_AVG_REF = 2.243    # de Vahl Davis 1983 Table 1, Ra=10⁴, Pr=0.71
_NU_TOL     = 0.03     # 3 % relative tolerance


@pytest.fixture(scope="module")
def cavity_result():
    """Run the cavity solver once and share the result across all tests."""
    solver = CavityNaturalConvection(Ra=1e4, Pr=0.71, n=32, max_steps=50000, tol=1e-5)
    result = solver.solve()
    return result


class TestCavityNaturalConvection:
    """de Vahl Davis benchmark for the square-cavity natural-convection solver."""

    def test_solver_ok(self, cavity_result):
        """Solver must return ok=True."""
        assert cavity_result["ok"] is True

    def test_nu_avg_de_vahl_davis(self, cavity_result):
        """
        Nu_avg for Ra=10⁴, Pr=0.71 must match de Vahl Davis (1983) Table 1
        within ±3 % [dVD83].
        """
        Nu = cavity_result["Nu_avg"]
        err = _rel_err(Nu, _NU_AVG_REF)
        assert err < _NU_TOL, (
            f"Nu_avg={Nu:.4f} differs from de Vahl Davis reference "
            f"{_NU_AVG_REF} by {err*100:.1f}% (limit {_NU_TOL*100:.0f}%)"
        )

    def test_nu_avg_positive(self, cavity_result):
        """Nu_avg must be positive."""
        assert cavity_result["Nu_avg"] > 0.0

    def test_nu_avg_exceeds_1(self, cavity_result):
        """Nu_avg > 1 indicates convection is active (pure conduction → Nu=1)."""
        assert cavity_result["Nu_avg"] > 1.0

    def test_temperature_field_shape(self, cavity_result):
        """Temperature field must be n×n."""
        T = cavity_result["T"]
        n = 32
        assert len(T) == n
        for row in T:
            assert len(row) == n

    def test_temperature_bounds(self, cavity_result):
        """All cell temperatures must be in [0, 1] (dimensionless θ)."""
        T = cavity_result["T"]
        for row in T:
            for val in row:
                assert -0.05 <= val <= 1.05, f"T={val} out of [0,1]"

    def test_hot_wall_hotter_than_cold(self, cavity_result):
        """Left column (near hot wall) must be hotter than right column."""
        T = cavity_result["T"]
        n = len(T)
        avg_left  = sum(T[0][j]     for j in range(n)) / n
        avg_right = sum(T[n - 1][j] for j in range(n)) / n
        assert avg_left > avg_right, (
            f"Left avg T={avg_left:.4f} not > right avg T={avg_right:.4f}"
        )

    def test_no_fluid_at_walls(self, cavity_result):
        """Normal velocity at all walls must be (nearly) zero."""
        U = cavity_result["U"]
        V = cavity_result["V"]
        n = len(cavity_result["T"])
        tol = 1e-10
        # Left wall: U[0][j]
        for j in range(n):
            assert abs(U[0][j]) < tol, f"U at left wall j={j}: {U[0][j]}"
        # Right wall: U[n][j]
        for j in range(n):
            assert abs(U[n][j]) < tol, f"U at right wall j={j}: {U[n][j]}"
        # Bottom wall: V[i][0]
        for i in range(n):
            assert abs(V[i][0]) < tol, f"V at bottom wall i={i}: {V[i][0]}"
        # Top wall: V[i][n]
        for i in range(n):
            assert abs(V[i][n]) < tol, f"V at top wall i={i}: {V[i][n]}"

    def test_steps_taken(self, cavity_result):
        """Must have run at least one step."""
        assert cavity_result["steps"] > 0


class TestCavityNaturalConvectionUnit:
    """Lightweight unit tests that do not require running the full solver."""

    def test_invalid_ra_raises(self):
        with pytest.raises(ValueError, match="Ra"):
            CavityNaturalConvection(Ra=0.0)

    def test_invalid_pr_raises(self):
        with pytest.raises(ValueError, match="Pr"):
            CavityNaturalConvection(Pr=-1.0)

    def test_small_n_raises(self):
        with pytest.raises(ValueError, match="n"):
            CavityNaturalConvection(n=4)

    def test_convenience_wrapper_returns_dict(self):
        """cavity_nusselt() is a thin wrapper; smoke-test with minimal grid."""
        result = cavity_nusselt(Ra=1e3, Pr=0.71, n=8, max_steps=5000, tol=1e-4)
        assert isinstance(result, dict)
        assert result["ok"] is True
        assert "Nu_avg" in result

    def test_conduction_limit_ra_near_zero(self):
        """
        At Ra→0 (pure conduction) Nu_avg → 1.
        Use Ra=1 as a surrogate for the conduction limit.
        """
        result = cavity_nusselt(Ra=1.0, Pr=0.71, n=16, max_steps=30000, tol=1e-5)
        assert result["ok"] is True
        assert abs(result["Nu_avg"] - 1.0) < 0.05, (
            f"Ra=1 Nu_avg={result['Nu_avg']:.4f} should be ~1 (conduction limit)"
        )
