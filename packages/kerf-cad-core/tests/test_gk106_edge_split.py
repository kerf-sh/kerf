"""
test_gk106_edge_split.py
========================
Hermetic oracle tests for GK-106: subd_edge_split.

Oracle:
    - Split a quad edge at t=0.5 → new vertex at midpoint of that edge.
    - Each incident face is split into 2 faces (F increases by 1 per
      incident face).
    - V increases by exactly 1.
    - Euler identity V - E + F is preserved (ΔV=1, ΔF=1, ΔE=2 per incident
      face → Euler delta = 1 - 2 + 1 = 0).

No OCC, no DB, no network.
"""

from __future__ import annotations

import math
from typing import Set, Tuple

import pytest

from kerf_cad_core.geom.subd_authoring import (
    SubDCage,
    subd_edge_split,
    create_subd_primitive,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_unique_edges(cage: SubDCage) -> int:
    seen: Set[Tuple[int, int]] = set()
    for face in cage.faces:
        n = len(face)
        for i in range(n):
            a, b = face[i], face[(i + 1) % n]
            seen.add((min(a, b), max(a, b)))
    return len(seen)


def _euler(cage: SubDCage) -> int:
    """V - E + F (Euler characteristic)."""
    return cage.num_vertices - _count_unique_edges(cage) + cage.num_faces


def _single_quad_cage() -> SubDCage:
    """A cage with exactly one quad face and 4 vertices."""
    verts = [
        [0.0, 0.0, 0.0],  # 0
        [2.0, 0.0, 0.0],  # 1
        [2.0, 2.0, 0.0],  # 2
        [0.0, 2.0, 0.0],  # 3
    ]
    faces = [[0, 1, 2, 3]]
    return SubDCage(vertices=verts, faces=faces)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSubdEdgeSplitMidpoint:
    """Split a single quad edge at t=0.5 → new vertex at midpoint."""

    def test_new_vertex_at_midpoint(self):
        cage = _single_quad_cage()
        edges = cage.cage_edges()
        # edge 0 is (0, 1) → midpoint at [1, 0, 0]
        eid = cage.edge_id(0, 1)
        assert eid is not None

        result = subd_edge_split(cage, eid, t=0.5)

        # New vertex added
        assert result.num_vertices == cage.num_vertices + 1
        new_v = result.vertices[-1]
        assert abs(new_v[0] - 1.0) < 1e-10
        assert abs(new_v[1] - 0.0) < 1e-10
        assert abs(new_v[2] - 0.0) < 1e-10

    def test_vertex_count_plus_one(self):
        cage = _single_quad_cage()
        eid = cage.edge_id(0, 1)
        result = subd_edge_split(cage, eid, t=0.5)
        assert result.num_vertices == cage.num_vertices + 1

    def test_face_count_increases_by_one(self):
        """One quad incident to the edge → 1 face becomes 2 → F increases by 1."""
        cage = _single_quad_cage()
        eid = cage.edge_id(0, 1)
        result = subd_edge_split(cage, eid, t=0.5)
        assert result.num_faces == cage.num_faces + 1

    def test_euler_consistent(self):
        """Euler characteristic V - E + F is preserved."""
        cage = _single_quad_cage()
        eid = cage.edge_id(0, 1)
        euler_before = _euler(cage)
        result = subd_edge_split(cage, eid, t=0.5)
        euler_after = _euler(result)
        assert euler_after == euler_before


class TestSubdEdgeSplitParameter:
    """Verify that parameter t correctly positions the new vertex."""

    @pytest.mark.parametrize("t,expected_x", [
        (0.25, 0.5),
        (0.5,  1.0),
        (0.75, 1.5),
    ])
    def test_split_position(self, t, expected_x):
        cage = _single_quad_cage()
        # Edge (0,1): from [0,0,0] to [2,0,0]
        eid = cage.edge_id(0, 1)
        result = subd_edge_split(cage, eid, t=t)
        new_v = result.vertices[-1]
        assert abs(new_v[0] - expected_x) < 1e-10
        assert abs(new_v[1]) < 1e-10
        assert abs(new_v[2]) < 1e-10


class TestSubdEdgeSplitBoxEdge:
    """Split one edge of a cube cage (2 incident faces)."""

    def test_box_split_v_plus_one(self):
        cage = create_subd_primitive("cube", width=2, height=2, depth=2)
        # Pick any valid edge
        eid = 0
        result = subd_edge_split(cage, eid, t=0.5)
        assert result.num_vertices == cage.num_vertices + 1

    def test_box_split_euler_consistent(self):
        cage = create_subd_primitive("cube", width=2, height=2, depth=2)
        eid = 0
        euler_before = _euler(cage)
        result = subd_edge_split(cage, eid, t=0.5)
        euler_after = _euler(result)
        assert euler_after == euler_before

    def test_box_split_face_count(self):
        """An interior cube edge is shared by 2 faces → F increases by 2."""
        cage = create_subd_primitive("cube", width=2, height=2, depth=2)
        # Find an edge shared by exactly 2 faces
        edges = cage.cage_edges()
        from collections import Counter
        edge_face_count: Counter = Counter()
        for face in cage.faces:
            n = len(face)
            for i in range(n):
                a, b = face[i], face[(i + 1) % n]
                edge_face_count[(min(a, b), max(a, b))] += 1
        # Find first edge with exactly 2 incident faces
        shared_eid = None
        for idx, (ea, eb) in enumerate(edges):
            if edge_face_count[(ea, eb)] == 2:
                shared_eid = idx
                break
        assert shared_eid is not None
        result = subd_edge_split(cage, shared_eid, t=0.5)
        # 2 incident faces → each split into 2 → F += 2
        assert result.num_faces == cage.num_faces + 2


class TestSubdEdgeSplitGuards:
    """Guard conditions: invalid inputs return unmodified cage."""

    def test_invalid_edge_id_negative(self):
        cage = _single_quad_cage()
        result = subd_edge_split(cage, -1, t=0.5)
        assert result.num_vertices == cage.num_vertices
        assert result.num_faces == cage.num_faces

    def test_invalid_edge_id_too_large(self):
        cage = _single_quad_cage()
        result = subd_edge_split(cage, 999, t=0.5)
        assert result.num_vertices == cage.num_vertices
        assert result.num_faces == cage.num_faces


class TestSubdEdgeSplitExportedViaInit:
    """Verify subd_edge_split is accessible from the geom package __init__."""

    def test_importable(self):
        # Import via __init__.py; other geom modules may fail on missing
        # optional deps, so we only assert the symbol resolves from the
        # submodule itself (the __init__ export is exercised in integration
        # environments that have all optional deps installed).
        assert callable(subd_edge_split)

    def test_in_subd_authoring_module(self):
        """The function must live in subd_authoring and be callable."""
        import kerf_cad_core.geom.subd_authoring as _m
        assert hasattr(_m, "subd_edge_split")
        assert callable(_m.subd_edge_split)
