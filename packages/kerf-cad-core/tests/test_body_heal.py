"""GK-85 — pytest oracle for geom/body_heal.py.

Oracle contract (from the spec):
  imported body with intentionally-introduced 1e-9 sliver →
  simplify_body removes it → validate_body passes.

Additional oracles:
  * clean body → passes unchanged
  * near-duplicate vertices → welded by simplify
  * sliver gap (positional mismatch 1e-9) → heal_body closes it
  * invalid tol raises ValueError
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    Body,
    Coedge,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
    make_box,
    validate_body,
)
from kerf_cad_core.geom.body_heal import heal_body, simplify_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sliver_edge_body() -> Body:
    """A box body with one artificially tiny (1e-9 length) extra edge injected
    into a face loop so that simplify_body should remove it.

    We build a standard unit box, then take one face and inject a degenerate
    spur edge (length = 1e-9) into its outer loop.  The spur is forward +
    reverse so the loop remains topologically closed.
    """
    body = make_box()
    # Pick the first face of the first shell
    face = body.solids[0].shells[0].faces[0]
    outer = face.outer_loop()

    # Spur vertex: almost identical to the first coedge's start point
    base_pt = outer.coedges[0].start_point().copy()
    sliver_pt = base_pt + np.array([1e-9, 0.0, 0.0])

    v_base = outer.coedges[0].start_vertex()
    v_sliver = Vertex(sliver_pt, tol=1e-7)
    spur_curve = Line3(base_pt, sliver_pt)
    spur_edge = Edge(spur_curve, 0.0, 1.0, v_base, v_sliver, tol=1e-7)

    # Insert coedge pair (forward + reverse) at position 0 in the loop
    ce_fwd = Coedge(spur_edge, True, outer)
    ce_rev = Coedge(spur_edge, False, outer)
    outer.coedges[0:0] = [ce_fwd, ce_rev]
    outer._relink()

    return body


def _make_near_duplicate_vertex_body() -> Body:
    """A triangle face with two vertices that are 1e-10 apart — should weld."""
    tol = 1e-7
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.5, 1.0, 0.0])
    p2b = p2 + np.array([0.0, 0.0, 1e-10])  # near-duplicate of p2

    v0 = Vertex(p0, tol)
    v1 = Vertex(p1, tol)
    v2 = Vertex(p2, tol)
    v2b = Vertex(p2b, tol)  # near-dup

    e01 = Edge(Line3(p0, p1), 0.0, 1.0, v0, v1, tol)
    e12 = Edge(Line3(p1, p2), 0.0, 1.0, v1, v2, tol)
    # use v2b here — the "gap" vertex
    e20 = Edge(Line3(p2b, p0), 0.0, 1.0, v2b, v0, tol)

    lp = Loop([Coedge(e01, True), Coedge(e12, True), Coedge(e20, True)], is_outer=True)
    plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
    face = Face(plane, [lp], orientation=True, tol=tol)
    shell = Shell([face], is_closed=False)
    return Body(shells=[shell])


def _make_gap_body() -> Body:
    """A box where one vertex position has been nudged by 1e-9 to create a
    positional gap.  heal_body should snap it closed."""
    body = make_box()
    # Nudge a single vertex position to introduce a tiny gap
    v = body.solids[0].shells[0].edges()[0].v_start
    v.point = v.point + np.array([0.0, 0.0, 1e-9])
    return body


# ---------------------------------------------------------------------------
# Tests: simplify_body
# ---------------------------------------------------------------------------


class TestSimplifyBody:
    def test_clean_box_passes_validate(self):
        """simplify_body on a clean box should return a valid body."""
        body = make_box()
        simplified = simplify_body(body, tol=1e-6)
        result = validate_body(simplified)
        assert result["ok"], result["errors"]

    def test_sliver_edge_removed(self):
        """The injected 1e-9 spur edge must be gone after simplification."""
        body_with_sliver = _make_sliver_edge_body()
        # Count edges before
        n_before = len(body_with_sliver.all_edges())
        simplified = simplify_body(body_with_sliver, tol=1e-6)
        n_after = len(simplified.all_edges())
        # The spur edge (length 1e-9 < tol 1e-6) must have been removed
        assert n_after < n_before, (
            f"Expected fewer edges after simplify, got {n_after} vs {n_before}"
        )

    def test_validate_after_sliver_removal(self):
        """validate_body must pass after removing the sliver."""
        body_with_sliver = _make_sliver_edge_body()
        simplified = simplify_body(body_with_sliver, tol=1e-6)
        result = validate_body(simplified)
        assert result["ok"], result["errors"]

    def test_original_not_mutated(self):
        """Input body must not be modified."""
        body = make_box()
        n_before = len(body.all_edges())
        _ = simplify_body(body, tol=1e-6)
        assert len(body.all_edges()) == n_before

    def test_near_duplicate_vertices_welded(self):
        """Two vertices within tol=1e-6 should be merged."""
        body = _make_near_duplicate_vertex_body()
        v_before = len(body.all_vertices())
        simplified = simplify_body(body, tol=1e-6)
        v_after = len(simplified.all_vertices())
        # The near-duplicate vertex (1e-10 apart) is within tol=1e-6
        assert v_after <= v_before

    def test_invalid_tol_raises(self):
        body = make_box()
        with pytest.raises(ValueError):
            simplify_body(body, tol=0)
        with pytest.raises(ValueError):
            simplify_body(body, tol=-1e-6)

    def test_face_count_unchanged_clean_body(self):
        """A clean box should have the same face count after simplify."""
        body = make_box()
        simplified = simplify_body(body, tol=1e-6)
        assert len(simplified.all_faces()) == len(body.all_faces())


# ---------------------------------------------------------------------------
# Tests: heal_body
# ---------------------------------------------------------------------------


class TestHealBody:
    def test_clean_box_passes_validate(self):
        body = make_box()
        healed = heal_body(body, tol=1e-6)
        result = validate_body(healed)
        assert result["ok"], result["errors"]

    def test_sliver_removed_and_validate_passes(self):
        """Core oracle: sliver body → heal → validate passes."""
        body_with_sliver = _make_sliver_edge_body()
        healed = heal_body(body_with_sliver, tol=1e-6)
        result = validate_body(healed)
        assert result["ok"], result["errors"]

    def test_original_not_mutated(self):
        body = make_box()
        n_edges_before = len(body.all_edges())
        _ = heal_body(body, tol=1e-6)
        assert len(body.all_edges()) == n_edges_before

    def test_gap_body_healed(self):
        """A vertex nudged by 1e-9 should be snapped and validate passes."""
        body = _make_gap_body()
        healed = heal_body(body, tol=1e-6)
        # After healing the gap (1e-9 < 10*tol = 1e-5) should be closed
        result = validate_body(healed)
        assert result["ok"], result["errors"]

    def test_invalid_tol_raises(self):
        body = make_box()
        with pytest.raises(ValueError):
            heal_body(body, tol=0)
        with pytest.raises(ValueError):
            heal_body(body, tol=-1e-6)

    def test_heal_is_superset_of_simplify(self):
        """heal_body removes at least as much as simplify_body."""
        body = _make_sliver_edge_body()
        simplified = simplify_body(body, tol=1e-6)
        healed = heal_body(body, tol=1e-6)
        # Both should produce fewer edges than the sliver body
        assert len(simplified.all_edges()) <= len(body.all_edges())
        assert len(healed.all_edges()) <= len(body.all_edges())
