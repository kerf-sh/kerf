"""
Tests for kerf_fem.buckling — linear eigenvalue buckling analysis.

Validation targets
------------------
1. Pinned-pinned Euler column:  Pcr = π²EI/L²     (K_eff = 1.0)
2. Fixed-free Euler column:     Pcr = π²EI/(2L)²  (K_eff = 2.0)
3. Higher mode:                 Pcr_2 ≈ 4 × Pcr_1  (pinned-pinned)
4. Closed-form helper euler_column_pcr
5. Tool handler valid/bad JSON
"""

from __future__ import annotations

import json
import math
import asyncio
import pytest

from kerf_fem.buckling import buckling_linear, euler_column_pcr


# ---------------------------------------------------------------------------
# Shared geometry / material
# ---------------------------------------------------------------------------

E = 200e9       # Pa  (steel)
I = 1e-6        # m⁴  (10 mm × 10 mm square: I = (0.01)⁴/12 ≈ 8.3e-10, but let's use round value)
A = 1e-4        # m²
L = 1.0         # m


# ---------------------------------------------------------------------------
# §1  Closed-form helper
# ---------------------------------------------------------------------------

class TestEulerColumnClosedForm:

    def test_pinned_pinned(self):
        res = euler_column_pcr(E, I, L, K_factor=1.0)
        assert res["ok"]
        expected = math.pi**2 * E * I / L**2
        assert abs(res["P_cr"] - expected) / expected < 1e-12

    def test_fixed_free(self):
        res = euler_column_pcr(E, I, L, K_factor=2.0)
        assert res["ok"]
        Le = 2.0 * L
        expected = math.pi**2 * E * I / Le**2
        assert abs(res["P_cr"] - expected) / expected < 1e-12

    def test_fixed_fixed(self):
        res = euler_column_pcr(E, I, L, K_factor=0.5)
        assert res["ok"]
        Le = 0.5 * L
        expected = math.pi**2 * E * I / Le**2
        assert abs(res["P_cr"] - expected) / expected < 1e-12

    def test_invalid_E(self):
        res = euler_column_pcr(-1.0, I, L)
        assert not res["ok"]
        assert "E" in res["reason"]

    def test_invalid_I(self):
        res = euler_column_pcr(E, 0.0, L)
        assert not res["ok"]

    def test_invalid_L(self):
        res = euler_column_pcr(E, I, -1.0)
        assert not res["ok"]

    def test_invalid_K_factor(self):
        res = euler_column_pcr(E, I, L, K_factor=0.0)
        assert not res["ok"]


# ---------------------------------------------------------------------------
# §2  FEM: pinned-pinned column
# ---------------------------------------------------------------------------

class TestPinnedPinnedBuckling:
    """
    Pinned-pinned: w=0 at both ends, θ free.
    Pcr_analytical = π²EI/L²
    FEM with 12 elements should be < 1% error.
    """

    SUPPORTS = [
        {"type": "pinned", "x": 0.0},
        {"type": "pinned", "x": L},
    ]

    def test_first_mode_within_1pct(self):
        P_ref = 1.0  # unit reference load → λ₁ = P_cr
        res = buckling_linear(E, I, A, L, P_ref, self.SUPPORTS, n_elem=12, n_modes=1)
        assert res["ok"], res.get("reason")
        lam1 = res["buckling_factors"][0]
        P_cr_fem = lam1 * P_ref
        P_cr_exact = math.pi**2 * E * I / L**2
        err = abs(P_cr_fem - P_cr_exact) / P_cr_exact
        assert err < 0.01, (
            f"Pinned-pinned first Pcr: FEM={P_cr_fem:.4e}, exact={P_cr_exact:.4e}, err={err*100:.2f}%"
        )

    def test_critical_loads_list(self):
        res = buckling_linear(E, I, A, L, 1.0, self.SUPPORTS, n_elem=12, n_modes=2)
        assert res["ok"]
        assert len(res["critical_loads"]) >= 1
        assert len(res["buckling_factors"]) == len(res["critical_loads"])

    def test_second_mode_approx_four_times_first(self):
        """
        For pinned-pinned, Pcr_n = n² × Pcr_1, so Pcr_2 ≈ 4 × Pcr_1.
        FEM approximation: within 5%.
        """
        res = buckling_linear(E, I, A, L, 1.0, self.SUPPORTS, n_elem=20, n_modes=2)
        assert res["ok"]
        if len(res["buckling_factors"]) >= 2:
            lam1, lam2 = res["buckling_factors"][0], res["buckling_factors"][1]
            ratio = lam2 / lam1
            assert abs(ratio - 4.0) / 4.0 < 0.05, (
                f"Mode ratio {ratio:.3f} expected ~4.0 for pinned-pinned"
            )

    def test_mode_shapes_length(self):
        res = buckling_linear(E, I, A, L, 1.0, self.SUPPORTS, n_elem=12, n_modes=2)
        assert res["ok"]
        n_dof_expected = 2 * (12 + 1)  # 2*(n_elem+1)
        for ms in res["mode_shapes"]:
            assert len(ms) == n_dof_expected

    def test_first_mode_normalised(self):
        """Mode shape max transverse displacement should be 1.0 (normalised)."""
        res = buckling_linear(E, I, A, L, 1.0, self.SUPPORTS, n_elem=12, n_modes=1)
        assert res["ok"]
        ms = res["mode_shapes"][0]
        n_nodes = 13
        w_vals = [abs(ms[2 * nd]) for nd in range(n_nodes)]
        assert abs(max(w_vals) - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# §3  FEM: fixed-free (cantilever) column
# ---------------------------------------------------------------------------

class TestFixedFreeBuckling:
    """
    Fixed-free: w=0, θ=0 at x=0; free at x=L.
    Pcr_analytical = π²EI/(2L)²
    """

    SUPPORTS = [
        {"type": "fixed", "x": 0.0},
    ]

    def test_first_mode_within_2pct(self):
        """Fixed-free FEM needs more elements; tolerance 2%."""
        P_ref = 1.0
        res = buckling_linear(E, I, A, L, P_ref, self.SUPPORTS, n_elem=20, n_modes=1)
        assert res["ok"], res.get("reason")
        lam1 = res["buckling_factors"][0]
        P_cr_fem = lam1 * P_ref
        Le = 2.0 * L
        P_cr_exact = math.pi**2 * E * I / Le**2
        err = abs(P_cr_fem - P_cr_exact) / P_cr_exact
        assert err < 0.02, (
            f"Fixed-free first Pcr: FEM={P_cr_fem:.4e}, exact={P_cr_exact:.4e}, err={err*100:.2f}%"
        )


# ---------------------------------------------------------------------------
# §4  Input validation
# ---------------------------------------------------------------------------

class TestBucklingInputValidation:

    SUPPORTS = [
        {"type": "pinned", "x": 0.0},
        {"type": "pinned", "x": L},
    ]

    def test_negative_E(self):
        res = buckling_linear(-E, I, A, L, 1.0, self.SUPPORTS)
        assert not res["ok"]

    def test_zero_I(self):
        res = buckling_linear(E, 0.0, A, L, 1.0, self.SUPPORTS)
        assert not res["ok"]

    def test_negative_L(self):
        res = buckling_linear(E, I, A, -1.0, 1.0, self.SUPPORTS)
        assert not res["ok"]

    def test_zero_P_ref(self):
        res = buckling_linear(E, I, A, L, 0.0, self.SUPPORTS)
        assert not res["ok"]

    def test_unknown_support_type(self):
        bad_supports = [{"type": "roller", "x": 0.0}]
        res = buckling_linear(E, I, A, L, 1.0, bad_supports)
        assert not res["ok"]

    def test_n_elem_too_small(self):
        res = buckling_linear(E, I, A, L, 1.0, self.SUPPORTS, n_elem=1)
        assert not res["ok"]


# ---------------------------------------------------------------------------
# §5  Tool handler
# ---------------------------------------------------------------------------

class TestBucklingToolHandler:

    def test_valid_payload(self):
        from kerf_fem.tools import run_fem_buckling_linear
        payload = {
            "E": E, "I": I, "A": A, "L": L, "P_ref": 1.0,
            "supports": [
                {"type": "pinned", "x": 0.0},
                {"type": "pinned", "x": L},
            ],
        }
        raw = asyncio.run(run_fem_buckling_linear(None, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert result.get("ok") is True
        assert "buckling_factors" in result

    def test_bad_json(self):
        from kerf_fem.tools import run_fem_buckling_linear
        raw = asyncio.run(run_fem_buckling_linear(None, b"not json {{{"))
        result = json.loads(raw)
        assert "error" in result

    def test_missing_required_field(self):
        from kerf_fem.tools import run_fem_buckling_linear
        payload = {"E": E, "I": I}  # missing A, L, P_ref, supports
        raw = asyncio.run(run_fem_buckling_linear(None, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert "error" in result

    def test_tool_spec_name(self):
        from kerf_fem.tools import fem_buckling_linear_spec
        assert fem_buckling_linear_spec.name == "fem_buckling_linear"
