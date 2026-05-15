"""
Hermetic tests for kerf_cad_core.fea — 1D/2D finite-element solver seed.

Coverage
--------
solver.solve_truss       — linear 2-D pin-jointed truss
solver.solve_bar_plastic — 1-D bar with bilinear isotropic-hardening plasticity
tools.*                  — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Results verified algebraically against closed-form solutions.

References
----------
Cook, R.D. et al. "Concepts and Applications of Finite Element Analysis", 4th ed.
de Souza Neto, E.A. et al. "Computational Methods for Plasticity", Wiley.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.fea.solver import solve_truss, solve_bar_plastic
from kerf_cad_core.fea.tools import (
    run_fea_solve_truss,
    run_fea_solve_bar_plastic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-6  # relative tolerance for floating-point checks


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


# ---------------------------------------------------------------------------
# Canonical test structures
# ---------------------------------------------------------------------------

def _simple_bar():
    """Single 1-D horizontal bar: node 0 at (0,0) fixed, node 1 at (1,0) loaded."""
    nodes = [[0.0, 0.0], [1.0, 0.0]]
    elements = [[0, 1]]
    supports = {0: {"ux": True, "uy": True}}
    loads = {1: {"fx": 1000.0, "fy": 0.0}}
    return nodes, elements, supports, loads


def _three_bar_truss():
    """
    Three-bar planar truss:
      Node 0: (0,0) — pinned (ux, uy fixed)
      Node 1: (1,0) — roller (uy fixed only)
      Node 2: (0.5, 1.0) — free (loaded)
    Elements: 0-2, 1-2, 0-1
    Load: 5000 N downward at node 2.
    """
    nodes = [[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]]
    elements = [[0, 2], [1, 2], [0, 1]]
    supports = {
        0: {"ux": True, "uy": True},
        1: {"ux": False, "uy": True},
    }
    loads = {2: {"fx": 0.0, "fy": -5000.0}}
    return nodes, elements, supports, loads


# ===========================================================================
# 1. solve_truss — input validation
# ===========================================================================

class TestSolveTrussValidation:

    def test_too_few_nodes(self):
        res = solve_truss([[0, 0]], [[0, 1]], {0: {"ux": True, "uy": True}}, {})
        assert res["ok"] is False

    def test_empty_elements(self):
        res = solve_truss([[0, 0], [1, 0]], [], {0: {"ux": True, "uy": True}}, {})
        assert res["ok"] is False

    def test_node_out_of_range_in_element(self):
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 5]]  # node 5 doesn't exist
        supports = {0: {"ux": True, "uy": True}}
        loads = {}
        res = solve_truss(nodes, elements, supports, loads)
        assert res["ok"] is False

    def test_degenerate_element_same_node(self):
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 0]]
        supports = {0: {"ux": True, "uy": True}}
        res = solve_truss(nodes, elements, supports, {})
        assert res["ok"] is False

    def test_negative_E_returns_error(self):
        n, e, s, l = _simple_bar()
        res = solve_truss(n, e, s, l, E=-1.0)
        assert res["ok"] is False

    def test_zero_A_returns_error(self):
        n, e, s, l = _simple_bar()
        res = solve_truss(n, e, s, l, A=0.0)
        assert res["ok"] is False


# ===========================================================================
# 2. solve_truss — single bar (analytically exact)
# ===========================================================================

class TestSolveTrussSingleBar:
    """
    A single horizontal bar of length L = 1 m, fixed at node 0, force F at
    node 1 in the x direction.  Closed-form:
        u_x = F·L / (E·A)
        σ = F / A
        ε = σ / E
    """

    def test_displacement_axial_formula(self):
        """u_x at loaded end = F·L/(E·A)."""
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": 1000.0, "fy": 0.0}}
        E, A, F, L = 200e9, 1e-4, 1000.0, 1.0
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        u_expected = F * L / (E * A)
        u_actual = res["displacements"][1][0]
        assert abs(u_actual - u_expected) / u_expected < REL

    def test_fixed_node_zero_displacement(self):
        """Fixed node 0 must have zero displacement."""
        n, e, s, l = _simple_bar()
        res = solve_truss(n, e, s, l)
        assert res["ok"] is True
        assert abs(res["displacements"][0][0]) < 1e-20
        assert abs(res["displacements"][0][1]) < 1e-20

    def test_element_stress(self):
        """σ = F / A for single-bar tension."""
        E, A, F = 200e9, 1e-4, 1000.0
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": F, "fy": 0.0}}
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        assert abs(res["element_stresses"][0] - F / A) / (F / A) < REL

    def test_element_strain(self):
        """ε = σ / E for linear elastic bar."""
        E, A, F = 200e9, 1e-4, 1000.0
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": F, "fy": 0.0}}
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        eps_expected = (F / A) / E
        assert abs(res["element_strains"][0] - eps_expected) / eps_expected < REL

    def test_reaction_equal_applied_force(self):
        """Reaction at fixed node must equal -F in x."""
        E, A, F = 200e9, 1e-4, 1000.0
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": F, "fy": 0.0}}
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        rx = res["reactions"][0][0]
        assert abs(rx + F) / F < REL  # rx ≈ -F

    def test_element_force_positive_tension(self):
        """Axial force must be positive (tension) when pulled."""
        E, A, F = 200e9, 1e-4, 1000.0
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": F, "fy": 0.0}}
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        assert res["element_forces"][0] > 0

    def test_output_lengths_match_inputs(self):
        """Output arrays must have correct lengths."""
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        res = solve_truss(nodes, elements, {0: {"ux": True, "uy": True}}, {1: {"fx": 500.0, "fy": 0.0}})
        assert res["ok"] is True
        assert len(res["displacements"]) == 2
        assert len(res["reactions"]) == 2
        assert len(res["element_forces"]) == 1
        assert len(res["element_stresses"]) == 1
        assert len(res["element_strains"]) == 1

    def test_compression_negative_stress(self):
        """Compressive load → negative stress."""
        E, A, F = 200e9, 1e-4, -1000.0
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": F, "fy": 0.0}}
        res = solve_truss(nodes, elements, supports, loads, E=E, A=A)
        assert res["ok"] is True
        assert res["element_stresses"][0] < 0

    def test_stiffness_proportional_to_EA_over_L(self):
        """Doubling E doubles stiffness → halves displacement."""
        nodes = [[0.0, 0.0], [1.0, 0.0]]
        elements = [[0, 1]]
        supports = {0: {"ux": True, "uy": True}}
        loads = {1: {"fx": 1000.0, "fy": 0.0}}
        u1 = solve_truss(nodes, elements, supports, loads, E=200e9, A=1e-4)["displacements"][1][0]
        u2 = solve_truss(nodes, elements, supports, loads, E=400e9, A=1e-4)["displacements"][1][0]
        assert abs(u1 / u2 - 2.0) < 1e-9


# ===========================================================================
# 3. solve_truss — three-bar truss
# ===========================================================================

class TestSolveTrussThreeBar:

    def test_returns_ok(self):
        n, e, s, l = _three_bar_truss()
        res = solve_truss(n, e, s, l)
        assert res["ok"] is True

    def test_three_nodes_three_elements_shape(self):
        n, e, s, l = _three_bar_truss()
        res = solve_truss(n, e, s, l)
        assert len(res["displacements"]) == 3
        assert len(res["element_forces"]) == 3

    def test_global_force_equilibrium(self):
        """Sum of all reaction forces must equal the applied loads."""
        n, e, s, l = _three_bar_truss()
        res = solve_truss(n, e, s, l)
        assert res["ok"] is True
        # Sum of reactions in y must equal +5000 (opposite to applied -5000)
        ry_sum = sum(r[1] for r in res["reactions"])
        assert abs(ry_sum - 5000.0) / 5000.0 < 1e-5

    def test_vertical_symmetry_horizontal_reactions(self):
        """Symmetric three-bar truss: sum of all x-reactions must vanish (no net horizontal)."""
        n, e, s, l = _three_bar_truss()
        res = solve_truss(n, e, s, l)
        rx_total = sum(r[0] for r in res["reactions"])
        # Net horizontal reaction must be near-zero (applied load is purely vertical)
        assert abs(rx_total) < 1e-6

    def test_diagonal_members_compressive_under_downward_load(self):
        """Outer diagonal members must be in compression when apex is pushed down.

        The apex (node 2) moves downward → diagonals shorten → compression.
        The bottom chord (node 0 to node 1) is in tension.
        """
        n, e, s, l = _three_bar_truss()
        res = solve_truss(n, e, s, l)
        # Elements 0 and 1 are the diagonal members (0-2 and 1-2)
        assert res["element_forces"][0] < 0
        assert res["element_forces"][1] < 0
        # Element 2 (bottom chord, 0-1) must be in tension
        assert res["element_forces"][2] > 0


# ===========================================================================
# 4. solve_bar_plastic — input validation
# ===========================================================================

class TestSolveBarPlasticValidation:

    def test_negative_length_error(self):
        res = solve_bar_plastic(-1.0, 1e-4, 200e9, 250e6, 10e9, 5000.0)
        assert res["ok"] is False

    def test_zero_area_error(self):
        res = solve_bar_plastic(1.0, 0.0, 200e9, 250e6, 10e9, 5000.0)
        assert res["ok"] is False

    def test_negative_E_error(self):
        res = solve_bar_plastic(1.0, 1e-4, -1.0, 250e6, 10e9, 5000.0)
        assert res["ok"] is False

    def test_negative_sigma_y_error(self):
        res = solve_bar_plastic(1.0, 1e-4, 200e9, -100.0, 10e9, 5000.0)
        assert res["ok"] is False

    def test_negative_H_error(self):
        res = solve_bar_plastic(1.0, 1e-4, 200e9, 250e6, -1.0, 5000.0)
        assert res["ok"] is False

    def test_zero_steps_error(self):
        res = solve_bar_plastic(1.0, 1e-4, 200e9, 250e6, 10e9, 5000.0, steps=0)
        assert res["ok"] is False

    def test_infinite_force_error(self):
        res = solve_bar_plastic(1.0, 1e-4, 200e9, 250e6, 10e9, float("inf"))
        assert res["ok"] is False


# ===========================================================================
# 5. solve_bar_plastic — elastic regime (force below yield)
# ===========================================================================

class TestSolveBarPlasticElastic:
    """Force is small enough that the bar stays elastic throughout."""

    def _params(self):
        return dict(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,  # yield at 250 MPa
            H=10e9,
            force=10000.0,  # σ = 10000/1e-4 = 100 MPa << 250 MPa
            steps=5,
        )

    def test_returns_ok(self):
        res = solve_bar_plastic(**self._params())
        assert res["ok"] is True

    def test_no_plastic_deformation(self):
        """Force below yield → plastic flag must be False."""
        res = solve_bar_plastic(**self._params())
        assert res["plastic"] is False

    def test_plastic_strain_zero(self):
        """All plastic strains must be zero in elastic range."""
        res = solve_bar_plastic(**self._params())
        for eps_p in res["plastic_strain"]:
            assert abs(eps_p) < 1e-20

    def test_displacement_matches_hookes_law(self):
        """u = F·L/(E·A) at final step in elastic range."""
        p = self._params()
        res = solve_bar_plastic(**p)
        assert res["ok"] is True
        u_expected = p["force"] * p["length"] / (p["E"] * p["area"])
        u_actual = res["displacement"][-1]
        assert abs(u_actual - u_expected) / u_expected < REL

    def test_stress_equals_F_over_A(self):
        """σ = F/A at final step (elastic)."""
        p = self._params()
        res = solve_bar_plastic(**p)
        sigma_expected = p["force"] / p["area"]
        assert abs(res["stress"][-1] - sigma_expected) / sigma_expected < REL

    def test_strain_equals_sigma_over_E(self):
        """ε = σ/E in elastic range."""
        p = self._params()
        res = solve_bar_plastic(**p)
        eps_expected = (p["force"] / p["area"]) / p["E"]
        assert abs(res["strain"][-1] - eps_expected) / eps_expected < REL

    def test_output_arrays_length(self):
        """Output arrays must have length == steps."""
        p = self._params()
        res = solve_bar_plastic(**p)
        n = p["steps"]
        for key in ("displacement", "stress", "strain", "plastic_strain",
                    "force_applied", "converged", "iterations"):
            assert len(res[key]) == n, f"key {key!r} has wrong length"

    def test_all_steps_converged(self):
        """All NR steps should converge in elastic regime."""
        res = solve_bar_plastic(**self._params())
        assert all(res["converged"])

    def test_force_ramp_linear(self):
        """Applied force at each step must be proportional to step number."""
        p = self._params()
        res = solve_bar_plastic(**p)
        delta_f = p["force"] / p["steps"]
        for i, f in enumerate(res["force_applied"]):
            expected = delta_f * (i + 1)
            assert abs(f - expected) / abs(expected) < REL


# ===========================================================================
# 6. solve_bar_plastic — plastic regime (force above yield)
# ===========================================================================

class TestSolveBarPlasticYielded:
    """Force is large enough to drive the bar into plasticity."""

    def _params(self):
        # σ_yield = 250 MPa with A=1e-4 → F_yield = 25 000 N
        # Apply 50 000 N → definitely plastic
        return dict(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,
            H=10e9,
            force=50000.0,
            steps=20,
        )

    def test_returns_ok(self):
        res = solve_bar_plastic(**self._params())
        assert res["ok"] is True

    def test_plastic_flag_true(self):
        """Plastic flag must be True when force exceeds yield."""
        res = solve_bar_plastic(**self._params())
        assert res["plastic"] is True

    def test_plastic_strain_positive_at_final_step(self):
        """Accumulated plastic strain must be positive after yielding."""
        res = solve_bar_plastic(**self._params())
        assert res["plastic_strain"][-1] > 0.0

    def test_stress_bounded_by_hardened_yield_surface(self):
        """Final stress must not exceed σ_y + H × α (yield surface)."""
        p = self._params()
        res = solve_bar_plastic(**p)
        alpha = res["plastic_strain"][-1]
        yield_surface = p["sigma_y"] + p["H"] * alpha
        sigma_final = abs(res["stress"][-1])
        # Allow small numerical tolerance
        assert sigma_final <= yield_surface + 1.0  # 1 Pa tolerance

    def test_total_strain_exceeds_elastic_strain_at_yield(self):
        """Total strain must exceed elastic yield strain when plastic."""
        p = self._params()
        eps_yield = p["sigma_y"] / p["E"]
        res = solve_bar_plastic(**p)
        assert res["strain"][-1] > eps_yield

    def test_consistent_strain_decomposition(self):
        """ε_total = ε_elastic + ε_plastic (strain decomposition)."""
        p = self._params()
        res = solve_bar_plastic(**p)
        eps_total = res["strain"][-1]
        sigma = res["stress"][-1]
        eps_plastic = res["plastic_strain"][-1]
        eps_elastic = sigma / p["E"]
        assert abs(eps_total - (eps_elastic + eps_plastic)) / (abs(eps_total) + 1e-30) < 1e-6

    def test_all_steps_converged(self):
        """Newton-Raphson should converge for all steps."""
        res = solve_bar_plastic(**self._params())
        assert all(res["converged"])

    def test_perfect_plasticity_constant_stress_after_yield(self):
        """H=0: stress saturates at sigma_y after yielding."""
        res = solve_bar_plastic(
            length=1.0, area=1e-4, E=200e9,
            sigma_y=250e6, H=0.0, force=50000.0, steps=20,
        )
        assert res["ok"] is True
        assert res["plastic"] is True
        # Stress at final step must equal sigma_y (within tolerance)
        assert abs(res["stress"][-1] - 250e6) / 250e6 < 1e-6


# ===========================================================================
# 7. solve_bar_plastic — single step, exact analytical check
# ===========================================================================

class TestSolveBarPlasticAnalytical:

    def test_single_elastic_step_exact(self):
        """
        With steps=1 and force below yield, displacement must exactly match F·L/(E·A).
        """
        L, A, E, sy, H = 2.0, 5e-4, 100e9, 500e6, 20e9
        F = 1e5  # σ = 1e5/5e-4 = 2e8 Pa << 500 MPa → elastic
        res = solve_bar_plastic(L, A, E, sy, H, F, steps=1)
        assert res["ok"] is True
        u_expected = F * L / (E * A)
        assert abs(res["displacement"][0] - u_expected) / u_expected < REL

    def test_hardening_increases_yield_stress_monotonically(self):
        """σ_y + H*α must increase monotonically across steps."""
        p = dict(length=1.0, area=1e-4, E=200e9, sigma_y=250e6, H=50e9, force=60000.0, steps=10)
        res = solve_bar_plastic(**p)
        assert res["ok"] is True
        eff_yield = [p["sigma_y"] + p["H"] * ep for ep in res["plastic_strain"]]
        for i in range(1, len(eff_yield)):
            assert eff_yield[i] >= eff_yield[i - 1] - 1e-10

    def test_compression_produces_negative_stress(self):
        """Compressive force must yield negative stress even in plastic range."""
        res = solve_bar_plastic(1.0, 1e-4, 200e9, 250e6, 10e9, -50000.0, steps=10)
        assert res["ok"] is True
        assert res["stress"][-1] < 0


# ===========================================================================
# 8. LLM tool wrappers — fea_solve_truss
# ===========================================================================

class TestToolFEASolveTruss:

    def test_happy_path_single_bar(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_truss(ctx, _args(
            nodes=[[0.0, 0.0], [1.0, 0.0]],
            elements=[[0, 1]],
            supports={"0": {"ux": True, "uy": True}},
            loads={"1": {"fx": 1000.0, "fy": 0.0}},
            E=200e9,
            A=1e-4,
        )))
        d = _ok_tool(raw)
        assert len(d["displacements"]) == 2
        assert d["displacements"][1][0] > 0

    def test_missing_nodes_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_truss(ctx, _args(
            elements=[[0, 1]],
            supports={"0": {"ux": True, "uy": True}},
            loads={},
        )))
        _err_tool(raw)

    def test_missing_loads_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_truss(ctx, _args(
            nodes=[[0.0, 0.0], [1.0, 0.0]],
            elements=[[0, 1]],
            supports={"0": {"ux": True, "uy": True}},
        )))
        _err_tool(raw)

    def test_bad_json_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_truss(ctx, b"not valid json"))
        _err_tool(raw)

    def test_three_bar_truss_tool(self):
        ctx = _ctx()
        nodes, elements, supports, loads = _three_bar_truss()
        raw = _run(run_fea_solve_truss(ctx, _args(
            nodes=nodes,
            elements=elements,
            supports={str(k): v for k, v in supports.items()},
            loads={str(k): v for k, v in loads.items()},
        )))
        d = _ok_tool(raw)
        assert len(d["element_forces"]) == 3


# ===========================================================================
# 9. LLM tool wrappers — fea_solve_bar_plastic
# ===========================================================================

class TestToolFEASolveBarPlastic:

    def test_happy_path_elastic(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,
            H=10e9,
            force=10000.0,
            steps=5,
        )))
        d = _ok_tool(raw)
        assert d["plastic"] is False
        assert len(d["displacement"]) == 5

    def test_happy_path_plastic(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,
            H=10e9,
            force=50000.0,
        )))
        d = _ok_tool(raw)
        assert d["plastic"] is True

    def test_missing_E_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            sigma_y=250e6,
            H=10e9,
            force=10000.0,
        )))
        _err_tool(raw)

    def test_missing_sigma_y_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            E=200e9,
            H=10e9,
            force=10000.0,
        )))
        _err_tool(raw)

    def test_bad_json_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, b"{bad json}"))
        _err_tool(raw)

    def test_negative_H_tool_error(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,
            H=-1.0,
            force=10000.0,
        )))
        _err_tool(raw)

    def test_single_step_tool(self):
        ctx = _ctx()
        raw = _run(run_fea_solve_bar_plastic(ctx, _args(
            length=1.0,
            area=1e-4,
            E=200e9,
            sigma_y=250e6,
            H=0.0,
            force=10000.0,
            steps=1,
        )))
        d = _ok_tool(raw)
        assert len(d["displacement"]) == 1
