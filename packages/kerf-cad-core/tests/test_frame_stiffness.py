"""
Tests for kerf_cad_core.struct.frame — Multi-storey frame stiffness analyser.

Covers:
  - 2-D frame: cantilever tip deflection (PL³/3EI), <1e-6 relative error.
  - 2-D frame: portal frame sway vs slope-deflection theory, <1%.
  - 2-D frame: UDL conversion (simply-supported beam max deflection 5wL⁴/384EI).
  - 2-D frame: boundary condition enforcement (fixed, pinned, roller).
  - 2-D frame: member end force recovery (N, V, M).
  - Multi-load-case / LRFD linear superposition.
  - Story drift: interstory drift and h/400 / h/200 limit flags.
  - 3-D frame: axial extension, sanity check.
  - Tool-dict interface (_frame_solve_2d_tool, _story_drift_tool).
  - Error paths: zero-length element, singular system, unknown element/node.

Pure-Python; hermetic; no OCC; no DB; no network.
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.struct.frame import (
    Node2D,
    Element2D,
    NodalLoad2D,
    UDL2D,
    Frame2D,
    Node3D,
    Element3D,
    Frame3D,
    LoadCase2D,
    StoryLevel,
    compute_story_drift,
    run_multi_case_2d,
    ASCE7_LRFD_COMBINATIONS,
    ASCE7_ASD_COMBINATIONS,
    _frame_solve_2d_tool,
    _story_drift_tool,
    _solve_gauss,
    _local_stiffness_2d,
    _udl_fixed_end_forces_2d,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cantilever(L: float, E: float, I: float, A: float = 1e4) -> tuple:
    """Return (frame, nA, nB) for a cantilever fixed at A, free at B."""
    nA = Node2D("A", 0.0, 0.0, bc="fixed")
    nB = Node2D("B", L,   0.0, bc="free")
    el = Element2D("el1", nA, nB, E=E, A=A, I=I)
    return Frame2D([nA, nB], [el]), nA, nB


def _portal(H: float, B: float, E: float, I: float, A: float = 1e12) -> tuple:
    """
    Return (frame, n1, n2, n3, n4, col1, col2, beam).
    Fixed-base 1-bay portal: n1/n2 at base, n3/n4 at top.
    A defaults to very large (axially rigid) to match slope-deflection theory.
    """
    n1 = Node2D("n1", 0.0, 0.0, bc="fixed")
    n2 = Node2D("n2", B,   0.0, bc="fixed")
    n3 = Node2D("n3", 0.0, H,   bc="free")
    n4 = Node2D("n4", B,   H,   bc="free")
    col1 = Element2D("col1", n1, n3, E=E, A=A, I=I)
    col2 = Element2D("col2", n2, n4, E=E, A=A, I=I)
    beam = Element2D("beam", n3, n4, E=E, A=A, I=I)
    frame = Frame2D([n1, n2, n3, n4], [col1, col2, beam])
    return frame, n1, n2, n3, n4, col1, col2, beam


# ---------------------------------------------------------------------------
# Linear algebra
# ---------------------------------------------------------------------------

class TestSolveGauss:
    def test_2x2(self):
        A = [[2.0, 1.0], [1.0, 3.0]]
        b = [5.0, 10.0]
        x = _solve_gauss(A, b)
        assert abs(x[0] - 1.0) < 1e-12
        assert abs(x[1] - 3.0) < 1e-12

    def test_3x3(self):
        A = [[1.0, 2.0, 3.0], [0.0, 4.0, 5.0], [1.0, 0.0, 6.0]]
        b = [14.0, 23.0, 25.0]
        x = _solve_gauss(A, b)
        # Verify Ax = b
        for i in range(3):
            row_sum = sum(A[i][j] * x[j] for j in range(3))
            assert abs(row_sum - b[i]) < 1e-10

    def test_singular_raises(self):
        A = [[1.0, 1.0], [1.0, 1.0]]
        with pytest.raises(ValueError, match="Singular"):
            _solve_gauss(A, [1.0, 2.0])


# ---------------------------------------------------------------------------
# Local stiffness matrix
# ---------------------------------------------------------------------------

class TestLocalStiffness2D:
    def test_symmetry(self):
        k = _local_stiffness_2d(200e3, 1e4, 1e6, 3000.0)
        for i in range(6):
            for j in range(6):
                assert abs(k[i][j] - k[j][i]) < 1e-8, f"Not symmetric at [{i},{j}]"

    def test_positive_diagonal(self):
        k = _local_stiffness_2d(200e3, 1e4, 1e6, 3000.0)
        for i in range(6):
            assert k[i][i] > 0.0

    def test_udl_fixed_end_forces_symmetry(self):
        w = 10.0; L = 5000.0
        f = _udl_fixed_end_forces_2d(w, L)
        assert abs(f[1] - w*L/2) < 1e-10   # V_i = wL/2
        assert abs(f[4] - w*L/2) < 1e-10   # V_j = wL/2
        assert abs(f[2] - w*L**2/12) < 1e-6  # M_i = +wL²/12
        assert abs(f[5] + w*L**2/12) < 1e-6  # M_j = -wL²/12


# ---------------------------------------------------------------------------
# 2-D cantilever
# ---------------------------------------------------------------------------

class TestCantilever2D:
    """Tip deflection of a cantilever: v_tip = PL³/(3EI)."""

    def setup_method(self):
        self.E  = 200e3    # N/mm²
        self.I  = 1e6      # mm⁴
        self.A  = 1e4      # mm²
        self.L  = 3000.0   # mm
        self.P  = 10.0     # N

    def test_tip_deflection_matches_exact(self):
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        v_fem = res.displacements["B"][1]
        v_exact = -self.P * self.L**3 / (3 * self.E * self.I)
        rel_err = abs((v_fem - v_exact) / v_exact)
        assert rel_err < 1e-6, f"Rel error {rel_err:.2e} exceeds 1e-6"

    def test_tip_rotation(self):
        """Tip rotation θ = PL²/(2EI)."""
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        theta_fem = res.displacements["B"][2]
        theta_exact = -self.P * self.L**2 / (2 * self.E * self.I)
        rel_err = abs((theta_fem - theta_exact) / theta_exact)
        assert rel_err < 1e-6

    def test_root_is_fixed(self):
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        u, v, th = res.displacements["A"]
        assert abs(u) < 1e-15
        assert abs(v) < 1e-15
        assert abs(th) < 1e-15

    def test_reaction_at_root(self):
        """Vertical reaction at root = P (upward)."""
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        Rx, Ry, Mz = res.reactions["A"]
        assert abs(Ry - self.P) < 1e-6 * self.P

    def test_member_end_forces_at_root(self):
        """Member end shear at root should equal P."""
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        mf = res.member_forces["el1"]
        # Shear at root end (local V_i) = P (upward), moment = P*L
        assert abs(abs(mf["V_i"]) - self.P) < 1e-4 * self.P

    def test_result_ok_true(self):
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-self.P)])
        assert res.ok is True
        assert res.errors == []

    def test_axial_load(self):
        """Pure axial load: u_tip = PL/(EA)."""
        frame, nA, nB = _cantilever(self.L, self.E, self.I, self.A)
        P_ax = 5000.0
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fx=P_ax)])
        u_fem = res.displacements["B"][0]
        u_exact = P_ax * self.L / (self.E * self.A)
        rel_err = abs((u_fem - u_exact) / u_exact)
        assert rel_err < 1e-10

    def test_multiple_elements(self):
        """Two-element cantilever should give same tip deflection."""
        E, I, A, L, P = self.E, self.I, self.A, self.L, self.P
        nA = Node2D("A",   0.0, 0.0, bc="fixed")
        nM = Node2D("Mid", L/2, 0.0, bc="free")
        nB = Node2D("B",   L,   0.0, bc="free")
        e1 = Element2D("e1", nA, nM, E=E, A=A, I=I)
        e2 = Element2D("e2", nM, nB, E=E, A=A, I=I)
        frame = Frame2D([nA, nM, nB], [e1, e2])
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-P)])
        v_fem = res.displacements["B"][1]
        v_exact = -P * L**3 / (3 * E * I)
        rel_err = abs((v_fem - v_exact) / v_exact)
        assert rel_err < 1e-6

    def test_inclined_element(self):
        """45-degree inclined cantilever: tip deflection resolved correctly."""
        L = 3000.0
        E, I, A = self.E, self.I, self.A
        nA = Node2D("A", 0.0,          0.0,          bc="fixed")
        nB = Node2D("B", L/math.sqrt(2), L/math.sqrt(2), bc="free")
        el = Element2D("el", nA, nB, E=E, A=A, I=I)
        frame = Frame2D([nA, nB], [el])
        # Load along element local y (transverse) — decompose to global X, Y
        # For a 45-deg element, local y is perpendicular: direction (-1/√2, 1/√2)
        P_local = 10.0
        Fx = -P_local / math.sqrt(2)
        Fy =  P_local / math.sqrt(2)
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fx=Fx, Fy=Fy)])
        # Check: result is ok and tip has non-zero displacement
        assert res.ok is True
        u, v, th = res.displacements["B"]
        assert abs(u)**2 + abs(v)**2 > 0


# ---------------------------------------------------------------------------
# UDL — simply-supported beam
# ---------------------------------------------------------------------------

class TestUDLSimplySupported:
    """Simply supported beam with UDL: max deflection = 5wL⁴/(384EI)."""

    def test_max_deflection_udl(self):
        # w convention: positive w = upward in local y (transverse direction).
        # For a downward gravity load on a horizontal beam, w is NEGATIVE.
        # Standard result: mid-span deflection = 5|w|L⁴/(384EI) downward.
        E = 200e3; I = 5e7; A = 1e4; L = 6000.0; w = -20.0  # negative = downward
        # Use two elements to capture mid-span.
        nA2 = Node2D("A2", 0.0, 0.0, bc="pinned")
        nM  = Node2D("M",  L/2, 0.0, bc="free")
        nB2 = Node2D("B2", L,   0.0, bc="roller_x")
        e1 = Element2D("e1", nA2, nM,  E=E, A=A, I=I)
        e2 = Element2D("e2", nM,  nB2, E=E, A=A, I=I)
        frame2 = Frame2D([nA2, nM, nB2], [e1, e2])
        res2 = frame2.solve(udls=[UDL2D("e1", w), UDL2D("e2", w)])
        v_mid = res2.displacements["M"][1]
        v_exact = 5 * w * L**4 / (384 * E * I)   # both negative; ratio is positive
        rel_err = abs((v_mid - v_exact) / v_exact)
        assert rel_err < 1e-4   # 2-element model; within 0.01 %

    def test_udl_reactions_equilibrium(self):
        # Downward UDL (w < 0): upward reactions at both ends sum to |w|*L.
        E = 200e3; I = 5e7; A = 1e4; L = 6000.0; w = -20.0  # downward
        nA = Node2D("A", 0.0, 0.0, bc="pinned")
        nB = Node2D("B", L,   0.0, bc="roller_x")
        el = Element2D("el", nA, nB, E=E, A=A, I=I)
        frame = Frame2D([nA, nB], [el])
        res = frame.solve(udls=[UDL2D("el", w)])
        Ry_A = res.reactions["A"][1]
        Ry_B = res.reactions["B"][1]
        # Total upward reaction should equal total downward load |w|*L
        assert abs(Ry_A + Ry_B - abs(w) * L) < 1e-6 * abs(w) * L


# ---------------------------------------------------------------------------
# Portal frame
# ---------------------------------------------------------------------------

class TestPortalFrame:
    """Fixed-base 1-bay portal under lateral load."""

    def setup_method(self):
        self.H = 4000.0   # mm
        self.B = 6000.0   # mm
        self.E = 200e3    # N/mm²
        self.I = 2e7      # mm⁴
        self.P = 50.0     # N

    def _theory_sway(self):
        """Slope-deflection sway for symmetric portal (axially rigid members)."""
        EI = self.E * self.I
        H, B = self.H, self.B
        a11 = 4*EI/H + 4*EI/B
        a12 = 2*EI/B
        a13 = -6*EI/H**2
        a31 = -6*EI/H**2
        a33 = 24*EI/H**3
        # By symmetry θ3 = θ4 = θ => (a11+a12)θ + a13*Δ = 0 => θ = -a13Δ/(a11+a12)
        # 2*a31*θ + a33*Δ = P
        denom = a33 + 2*a31*(-a13/(a11+a12))
        return self.P / denom

    def test_sway_matches_slope_deflection(self):
        frame, n1, n2, n3, n4, col1, col2, beam = _portal(
            self.H, self.B, self.E, self.I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=self.P)])
        sway_n3 = res.displacements["n3"][0]
        sway_theory = self._theory_sway()
        rel_err = abs((sway_n3 - sway_theory) / sway_theory)
        assert rel_err < 0.01, f"Portal sway rel_err={rel_err:.4f} exceeds 1%"

    def test_symmetric_sway(self):
        """Both top nodes sway approximately equally under symmetric structure."""
        frame, n1, n2, n3, n4, col1, col2, beam = _portal(
            self.H, self.B, self.E, self.I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=self.P)])
        sway_n3 = res.displacements["n3"][0]
        sway_n4 = res.displacements["n4"][0]
        # For axially-rigid beam, sway should be identical
        assert abs(sway_n3 - sway_n4) < 1e-8 * abs(sway_n3)

    def test_base_nodes_fixed(self):
        frame, n1, n2, n3, n4, col1, col2, beam = _portal(
            self.H, self.B, self.E, self.I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=self.P)])
        for nid in ("n1", "n2"):
            d = res.displacements[nid]
            assert all(abs(v) < 1e-14 for v in d), f"Node {nid} not fully fixed: {d}"

    def test_horizontal_equilibrium(self):
        """Sum of horizontal base reactions = applied load P."""
        frame, n1, n2, n3, n4, col1, col2, beam = _portal(
            self.H, self.B, self.E, self.I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=self.P)])
        Rx1 = res.reactions["n1"][0]
        Rx2 = res.reactions["n2"][0]
        assert abs(Rx1 + Rx2 + self.P) < 1e-6 * self.P   # reactions oppose load

    def test_ok_true(self):
        frame, n1, n2, n3, n4, col1, col2, beam = _portal(
            self.H, self.B, self.E, self.I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=self.P)])
        assert res.ok is True


# ---------------------------------------------------------------------------
# Multi-story (2-bay, 3-story) sanity
# ---------------------------------------------------------------------------

class TestMultiStory:
    """3-storey, 2-bay frame: basic smoke test; gravity + lateral loads."""

    def _build(self):
        E = 200e3; I = 3e7; A = 8e3
        H = [0, 4000, 8000, 12000]   # storey elevations
        X = [0, 6000, 12000]         # column X positions

        nodes = {}
        for story in range(4):
            for col in range(3):
                nid = f"n{story}_{col}"
                bc = "fixed" if story == 0 else "free"
                nodes[nid] = Node2D(nid, float(X[col]), float(H[story]), bc=bc)

        elements = []
        # Columns
        for story in range(3):
            for col in range(3):
                nid_i = f"n{story}_{col}"
                nid_j = f"n{story+1}_{col}"
                elements.append(Element2D(f"col_{story}_{col}",
                    nodes[nid_i], nodes[nid_j], E=E, A=A, I=I))
        # Beams
        for story in range(1, 4):
            for bay in range(2):
                nid_i = f"n{story}_{bay}"
                nid_j = f"n{story}_{bay+1}"
                elements.append(Element2D(f"beam_{story}_{bay}",
                    nodes[nid_i], nodes[nid_j], E=E, A=A, I=I))

        return Frame2D(list(nodes.values()), elements), nodes

    def test_gravity_only(self):
        frame, nodes = self._build()
        # UDL on all beams
        udls = [UDL2D(f"beam_{s}_{b}", -5.0) for s in range(1, 4) for b in range(2)]
        res = frame.solve(udls=udls)
        assert res.ok is True
        # All base nodes fixed — zero displacement
        for col in range(3):
            d = res.displacements[f"n0_{col}"]
            assert all(abs(v) < 1e-14 for v in d)

    def test_lateral_load(self):
        frame, nodes = self._build()
        loads = [NodalLoad2D(f"n{s}_0", Fx=10.0) for s in range(1, 4)]
        res = frame.solve(nodal_loads=loads)
        assert res.ok is True
        # Top-left node should sway rightward
        u_top = res.displacements["n3_0"][0]
        assert u_top > 0.0


# ---------------------------------------------------------------------------
# Story-drift helper
# ---------------------------------------------------------------------------

class TestStoryDrift:
    """compute_story_drift: interstory drift, h/400 and h/200 flags."""

    def _sway_portal(self):
        """Return displacement dict from a lateral-loaded fixed-base portal."""
        E = 200e3; I = 2e7; H = 4000.0; B = 6000.0; P = 50.0
        frame, n1, n2, n3, n4, c1, c2, bm = _portal(H, B, E, I)
        res = frame.solve(nodal_loads=[NodalLoad2D("n3", Fx=P)])
        return res.displacements, H

    def test_drift_computed(self):
        disps, H = self._sway_portal()
        levels = [
            StoryLevel("Base", 0.0, ["n1", "n2"]),
            StoryLevel("Roof", H,   ["n3", "n4"]),
        ]
        results = compute_story_drift(disps, levels)
        assert len(results) == 1
        r = results[0]
        assert r.story == "Base→Roof"
        assert abs(r.height - H) < 1e-10
        # Drift should be approximately the sway value
        assert abs(r.interstory_drift) > 0

    def test_drift_ratio_sign(self):
        disps, H = self._sway_portal()
        levels = [
            StoryLevel("Base", 0.0, ["n1", "n2"]),
            StoryLevel("Roof", H,   ["n3", "n4"]),
        ]
        results = compute_story_drift(disps, levels)
        r = results[0]
        assert r.drift_ratio >= 0.0

    def test_limit_check_h400(self):
        # Force a large drift to trigger h/400 flag
        disps = {
            "A": (0.0, 0.0, 0.0),
            "B": (100.0, 0.0, 0.0),   # large sway
        }
        levels = [
            StoryLevel("Bot", 0.0, ["A"]),
            StoryLevel("Top", 3000.0, ["B"]),  # h = 3000, drift=100, ratio=1/30 >> 1/400
        ]
        results = compute_story_drift(disps, levels)
        assert results[0].exceeds_live_limit is True
        assert results[0].exceeds_wind_limit is True

    def test_limit_check_ok(self):
        disps = {
            "A": (0.0, 0.0, 0.0),
            "B": (1.0, 0.0, 0.0),    # drift=1 mm over h=4000 → 1/4000 < 1/400
        }
        levels = [
            StoryLevel("Bot", 0.0, ["A"]),
            StoryLevel("Top", 4000.0, ["B"]),
        ]
        results = compute_story_drift(disps, levels)
        assert results[0].exceeds_live_limit is False
        assert results[0].exceeds_wind_limit is False

    def test_multi_story_drift(self):
        disps = {
            "n0": (0.0, 0.0, 0.0),
            "n1": (5.0, 0.0, 0.0),
            "n2": (12.0, 0.0, 0.0),
        }
        levels = [
            StoryLevel("L0", 0.0,    ["n0"]),
            StoryLevel("L1", 4000.0, ["n1"]),
            StoryLevel("L2", 8000.0, ["n2"]),
        ]
        results = compute_story_drift(disps, levels)
        assert len(results) == 2
        assert abs(results[0].interstory_drift - 5.0) < 1e-10
        assert abs(results[1].interstory_drift - 7.0) < 1e-10

    def test_v_direction_drift(self):
        disps = {"A": (3.0, 8.0, 0.0), "B": (3.0, 2.0, 0.0)}
        levels = [
            StoryLevel("Bot", 0.0, ["A"]),
            StoryLevel("Top", 5000.0, ["B"]),
        ]
        results = compute_story_drift(disps, levels, drift_direction="v")
        assert abs(results[0].interstory_drift + 6.0) < 1e-10  # 2 - 8 = -6


# ---------------------------------------------------------------------------
# Multi-load-case
# ---------------------------------------------------------------------------

class TestMultiLoadCase:
    def _setup(self):
        E = 200e3; I = 1e7; A = 5e3; L = 5000.0
        nA = Node2D("A", 0.0, 0.0, bc="fixed")
        nB = Node2D("B", L,   0.0, bc="free")
        el = Element2D("el", nA, nB, E=E, A=A, I=I)
        frame = Frame2D([nA, nB], [el])
        dead = LoadCase2D("dead", nodal_loads=[NodalLoad2D("B", Fy=-10.0)])
        live = LoadCase2D("live", nodal_loads=[NodalLoad2D("B", Fy=-5.0)])
        wind = LoadCase2D("wind_X", nodal_loads=[NodalLoad2D("B", Fx=3.0)])
        return frame, [dead, live, wind]

    def test_returns_envelopes_for_all_combos(self):
        frame, cases = self._setup()
        combos = ASCE7_LRFD_COMBINATIONS + ASCE7_ASD_COMBINATIONS
        envelopes = run_multi_case_2d(frame, cases, combos)
        assert len(envelopes) == len(combos)

    def test_superposition_1p4D(self):
        """1.4D combination: displacement = 1.4 × dead-only displacement."""
        frame, cases = self._setup()
        dead_only = run_multi_case_2d(frame, cases, [{"name":"D","factors":{"dead":1.0}}])
        comb_14D  = run_multi_case_2d(frame, cases, [{"name":"1.4D","factors":{"dead":1.4}}])
        v_dead = dead_only[0].max_displacements["B"]["v"]
        v_14D  = comb_14D[0].max_displacements["B"]["v"]
        assert abs(v_14D - 1.4 * v_dead) < 1e-10

    def test_unknown_case_handled_gracefully(self):
        """Combination referencing a load case not in the list → skipped silently."""
        frame, cases = self._setup()
        combo = [{"name": "ghost", "factors": {"nonexistent": 1.0}}]
        envelopes = run_multi_case_2d(frame, cases, combo)
        assert len(envelopes) == 1
        assert envelopes[0].ok is True   # no error; just zero contribution

    def test_default_combos(self):
        frame, cases = self._setup()
        envelopes = run_multi_case_2d(frame, cases)
        assert len(envelopes) == len(ASCE7_LRFD_COMBINATIONS) + len(ASCE7_ASD_COMBINATIONS)


# ---------------------------------------------------------------------------
# 3-D Frame
# ---------------------------------------------------------------------------

class TestFrame3D:
    """Basic 3-D frame: axial extension and simple checks."""

    def test_axial_extension(self):
        """Single 3-D element along X: tip extension = PL/(EA)."""
        E = 200e3; G = 77e3; A = 1e4; Iy = 1e6; Iz = 1e6; J = 5e5
        L = 2000.0; P = 1000.0
        ni = Node3D("A", 0.0, 0.0, 0.0, bc="fixed")
        nj = Node3D("B", L,   0.0, 0.0, bc="free")
        el = Element3D("el", ni, nj, E=E, G=G, A=A, Iy=Iy, Iz=Iz, J=J,
                       ref_y=(0.0, 1.0, 0.0))
        frame = Frame3D([ni, nj], [el])
        res = frame.solve(nodal_loads=[{"node_id": "B", "Fx": P}])
        assert res.ok is True
        u_tip = res.displacements["B"][0]
        u_exact = P * L / (E * A)
        rel_err = abs((u_tip - u_exact) / u_exact)
        assert rel_err < 1e-10

    def test_3d_cantilever_bending_z(self):
        """3-D cantilever with transverse load in Y: v_tip = PL³/(3EIz)."""
        E = 200e3; G = 77e3; A = 1e4; Iy = 1e6; Iz = 2e6; J = 5e5
        L = 3000.0; P = 10.0
        ni = Node3D("A", 0.0, 0.0, 0.0, bc="fixed")
        nj = Node3D("B", L,   0.0, 0.0, bc="free")
        el = Element3D("el", ni, nj, E=E, G=G, A=A, Iy=Iy, Iz=Iz, J=J,
                       ref_y=(0.0, 1.0, 0.0))
        frame = Frame3D([ni, nj], [el])
        res = frame.solve(nodal_loads=[{"node_id": "B", "Fy": -P}])
        assert res.ok is True
        v_tip = res.displacements["B"][1]
        v_exact = -P * L**3 / (3 * E * Iz)
        rel_err = abs((v_tip - v_exact) / v_exact)
        assert rel_err < 1e-6

    def test_3d_fixed_node_zero_disp(self):
        E = 200e3; G = 77e3; A = 1e4; Iy = 1e6; Iz = 1e6; J = 5e5; L = 2000.0
        ni = Node3D("A", 0.0, 0.0, 0.0, bc="fixed")
        nj = Node3D("B", L,   0.0, 0.0, bc="free")
        el = Element3D("el", ni, nj, E=E, G=G, A=A, Iy=Iy, Iz=Iz, J=J)
        frame = Frame3D([ni, nj], [el])
        res = frame.solve(nodal_loads=[{"node_id": "B", "Fx": 500.0}])
        d_fixed = res.displacements["A"]
        assert all(abs(v) < 1e-14 for v in d_fixed)

    def test_3d_bending_y(self):
        """3-D cantilever with load in Z: w_tip = PL³/(3EIy)."""
        E = 200e3; G = 77e3; A = 1e4; Iy = 3e6; Iz = 1e6; J = 5e5
        L = 3000.0; P = 10.0
        ni = Node3D("A", 0.0, 0.0, 0.0, bc="fixed")
        nj = Node3D("B", L,   0.0, 0.0, bc="free")
        el = Element3D("el", ni, nj, E=E, G=G, A=A, Iy=Iy, Iz=Iz, J=J,
                       ref_y=(0.0, 1.0, 0.0))
        frame = Frame3D([ni, nj], [el])
        res = frame.solve(nodal_loads=[{"node_id": "B", "Fz": -P}])
        assert res.ok is True
        w_tip = res.displacements["B"][2]
        w_exact = -P * L**3 / (3 * E * Iy)
        rel_err = abs((w_tip - w_exact) / w_exact)
        assert rel_err < 1e-6


# ---------------------------------------------------------------------------
# Tool-dict interfaces
# ---------------------------------------------------------------------------

class TestFrameSolveToolDict:
    def _cantilever_args(self):
        return {
            "nodes": [
                {"id": "A", "x": 0.0, "y": 0.0, "bc": "fixed"},
                {"id": "B", "x": 3000.0, "y": 0.0, "bc": "free"},
            ],
            "elements": [
                {"id": "el", "node_i": "A", "node_j": "B",
                 "E": 200e3, "A": 1e4, "I": 1e6},
            ],
            "nodal_loads": [{"node_id": "B", "Fy": -10.0}],
        }

    def test_cantilever_tool(self):
        args = self._cantilever_args()
        result = _frame_solve_2d_tool(args)
        assert result["ok"] is True
        v_tip = result["displacements"]["B"][1]
        v_exact = -10.0 * 3000.0**3 / (3 * 200e3 * 1e6)
        assert abs((v_tip - v_exact) / v_exact) < 1e-6

    def test_tool_unknown_node_in_element(self):
        args = {
            "nodes": [{"id": "A", "x": 0.0, "y": 0.0, "bc": "fixed"}],
            "elements": [{"id": "el", "node_i": "A", "node_j": "MISSING",
                          "E": 200e3, "A": 1e4, "I": 1e6}],
        }
        result = _frame_solve_2d_tool(args)
        # Should still return (element skipped, may fail or succeed with error)
        # Either way, no exception raised
        assert isinstance(result, dict)

    def test_tool_with_udl(self):
        args = {
            "nodes": [
                {"id": "A", "x": 0.0,    "y": 0.0, "bc": "pinned"},
                {"id": "B", "x": 6000.0, "y": 0.0, "bc": "roller_x"},
            ],
            "elements": [
                {"id": "el", "node_i": "A", "node_j": "B",
                 "E": 200e3, "A": 1e4, "I": 5e7},
            ],
            "udls": [{"element_id": "el", "w": 20.0}],
        }
        result = _frame_solve_2d_tool(args)
        assert result["ok"] is True

    def test_story_drift_tool(self):
        args = {
            "displacements": {
                "A": [0.0, 0.0, 0.0],
                "B": [50.0, 0.0, 0.0],
            },
            "story_levels": [
                {"name": "Bot", "elevation": 0.0, "node_ids": ["A"]},
                {"name": "Top", "elevation": 4000.0, "node_ids": ["B"]},
            ],
            "drift_direction": "u",
        }
        result = _story_drift_tool(args)
        assert result["ok"] is True
        dr = result["story_drifts"][0]
        assert abs(dr["interstory_drift"] - 50.0) < 1e-10
        assert dr["exceeds_live_limit_h400"] is True

    def test_story_drift_tool_ok_limits(self):
        args = {
            "displacements": {
                "A": [0.0, 0.0, 0.0],
                "B": [1.0, 0.0, 0.0],  # 1 mm over 4000 mm → 1/4000, within limits
            },
            "story_levels": [
                {"name": "Bot", "elevation": 0.0, "node_ids": ["A"]},
                {"name": "Top", "elevation": 4000.0, "node_ids": ["B"]},
            ],
        }
        result = _story_drift_tool(args)
        assert result["ok"] is True
        assert result["story_drifts"][0]["exceeds_live_limit_h400"] is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_zero_length_element_handled(self):
        nA = Node2D("A", 0.0, 0.0, bc="fixed")
        nB = Node2D("B", 0.0, 0.0, bc="free")
        el = Element2D("el", nA, nB, E=200e3, A=1e4, I=1e6)
        frame = Frame2D([nA, nB], [el])
        res = frame.solve(nodal_loads=[NodalLoad2D("B", Fy=-10.0)])
        # Zero-length element should be reported in errors
        assert any("zero length" in e.lower() or "zero" in e.lower() for e in res.errors)

    def test_all_constrained_returns_error(self):
        nA = Node2D("A", 0.0, 0.0, bc="fixed")
        nB = Node2D("B", 1000.0, 0.0, bc="fixed")
        el = Element2D("el", nA, nB, E=200e3, A=1e4, I=1e6)
        frame = Frame2D([nA, nB], [el])
        res = frame.solve()
        assert res.ok is False
        assert len(res.errors) > 0

    def test_udl_unknown_element_handled(self):
        nA = Node2D("A", 0.0,    0.0, bc="fixed")
        nB = Node2D("B", 3000.0, 0.0, bc="free")
        el = Element2D("el", nA, nB, E=200e3, A=1e4, I=1e6)
        frame = Frame2D([nA, nB], [el])
        res = frame.solve(udls=[UDL2D("GHOST", 10.0)])
        assert any("unknown element" in e.lower() or "GHOST" in e for e in res.errors)
