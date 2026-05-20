"""
test_gk88_loop_slide.py
=======================
Hermetic oracle tests for GK-88: subd_loop_slide.

Oracle: loop-slide a box edge-loop by t along adjacent faces →
  - vertex positions move by t * edge_length in the face-tangent direction
  - topology (V count, E count, F count) is identical to the input cage

No OCC, no DB, no network.
"""

from __future__ import annotations

import math
from typing import List, Set, Tuple

import pytest

from kerf_cad_core.geom.subd_authoring import (
    SubDCage,
    create_subd_primitive,
    subd_loop_slide,
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


def _box_middle_loop_eids(cage: SubDCage) -> List[int]:
    """Return the 4 edge ids that form the equatorial loop of a 2×2×2 box.

    The box has 8 vertices, 12 edges, 6 faces.  The equatorial loop (z-axis
    cross-section) consists of the 4 horizontal edges at y=-1 and y=+1 that
    span x.  We look for edges where both endpoints have the same |z| value
    and both z values are the same (i.e., edges on the side faces but at
    neither top nor bottom).

    More robustly we pick edges that are *not* on the top (z=+1) or bottom
    (z=-1) faces: we exclude edges that lie on the top or bottom face
    and choose the 4 that form a horizontal ring.
    """
    edges = cage.cage_edges()
    verts = cage.vertices

    # The cube (width=2, height=2, depth=2) has vertices at ±1.
    # Top face: z=+1, bottom face: z=-1, side faces connect them.
    # A "middle loop" doesn't really exist on a plain 6-face box —
    # we instead target the 4 side-face edges that are NOT on the
    # top or bottom boundaries: i.e. the 4 horizontal-belt edges.
    # On a plain box these are on the top (+z) ring OR bottom (-z) ring.
    # For a proper ring-slide test we pick one full horizontal ring:
    # the 4 edges where both endpoints have z = +1 (the top rim).

    top_z = 1.0
    eids: List[int] = []
    for eid, (a, b) in enumerate(edges):
        za = verts[a][2]
        zb = verts[b][2]
        if abs(za - top_z) < 1e-9 and abs(zb - top_z) < 1e-9:
            eids.append(eid)
    return eids


# ---------------------------------------------------------------------------
# Test 1: t=0 is identity
# ---------------------------------------------------------------------------

def test_loop_slide_identity():
    cage = create_subd_primitive("cube", width=2, height=2, depth=2)
    eids = _box_middle_loop_eids(cage)
    result = subd_loop_slide(cage, eids, t=0.0)

    # Vertex positions must be unchanged
    for orig, slid in zip(cage.vertices, result.vertices):
        assert orig == pytest.approx(slid, abs=1e-12)


# ---------------------------------------------------------------------------
# Test 2: topology (V/E/F) unchanged after slide
# ---------------------------------------------------------------------------

def test_loop_slide_topology_unchanged():
    cage = create_subd_primitive("cube", width=2, height=2, depth=2)
    eids = _box_middle_loop_eids(cage)

    V_before = cage.num_vertices
    E_before = _count_unique_edges(cage)
    F_before = cage.num_faces

    for t in [0.5, -0.5, 1.0, -1.0, 0.25]:
        result = subd_loop_slide(cage, eids, t=t)
        assert result.num_vertices == V_before, f"V changed at t={t}"
        assert _count_unique_edges(result) == E_before, f"E changed at t={t}"
        assert result.num_faces == F_before, f"F changed at t={t}"


# ---------------------------------------------------------------------------
# Test 3: vertex positions move by t * edge_length in face-tangent direction
# ---------------------------------------------------------------------------

def test_loop_slide_vertex_displacement_proportional():
    """Oracle: slide the top-rim loop of a 2x2x2 box by t=0.5.

    The top-rim edges are at z=+1.  Each rim vertex has two adjacent faces:
    the top face and one side face.  Sliding by t=0.5 should move each rim
    vertex halfway from z=+1 toward z=-1 (down along the side face).

    For a uniform cube, the side face height is 2 (from z=-1 to z=+1),
    so t=0.5 → vertex moves by 0.5 * 2 = 1 unit in -z direction.
    Expected final z = 1.0 - 1.0 = 0.0.
    """
    cage = create_subd_primitive("cube", width=2, height=2, depth=2)
    eids = _box_middle_loop_eids(cage)

    result = subd_loop_slide(cage, eids, t=0.5)

    # Identify the top-rim vertices in the original cage
    top_verts = [i for i, v in enumerate(cage.vertices) if abs(v[2] - 1.0) < 1e-9]
    assert len(top_verts) == 4, "cube should have 4 top-rim vertices"

    for vi in top_verts:
        orig = cage.vertices[vi]
        slid = result.vertices[vi]

        # x and y should not change (sliding along z)
        assert slid[0] == pytest.approx(orig[0], abs=1e-9), f"x changed for v{vi}"
        assert slid[1] == pytest.approx(orig[1], abs=1e-9), f"y changed for v{vi}"

        # z should move from +1 to 0 (t=0.5, edge_length=2, so Δz = -1)
        assert slid[2] == pytest.approx(0.0, abs=1e-9), f"z wrong for v{vi}: {slid[2]}"


# ---------------------------------------------------------------------------
# Test 4: t=+1 moves vertex to the position of the opposite edge endpoint
# ---------------------------------------------------------------------------

def test_loop_slide_full_slide():
    """t=1 should move each top-rim vertex to the corresponding bottom-rim position."""
    cage = create_subd_primitive("cube", width=2, height=2, depth=2)
    eids = _box_middle_loop_eids(cage)

    result = subd_loop_slide(cage, eids, t=1.0)

    top_verts = [i for i, v in enumerate(cage.vertices) if abs(v[2] - 1.0) < 1e-9]
    for vi in top_verts:
        slid = result.vertices[vi]
        orig = cage.vertices[vi]
        assert slid[0] == pytest.approx(orig[0], abs=1e-9)
        assert slid[1] == pytest.approx(orig[1], abs=1e-9)
        # z=+1 should have moved to z=-1 (the bottom-rim z)
        assert slid[2] == pytest.approx(-1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 5: t=-1 is symmetric (moves toward positive normal side)
# ---------------------------------------------------------------------------

def test_loop_slide_negative_t():
    """t=-1 from the top rim: moving "up" has no further room (already at top),
    so by symmetry the displacement is in the +z direction of the face.

    For the top rim this means: the only adjacent direction is *downward*
    (toward the bottom) — the top face is adjacent but its opposite edge
    is still the bottom rim.  So t=-1 should be the mirror of t=+1.

    We just verify that t=-1 and t=+1 produce z displacements of equal
    magnitude (|Δz| = 2) in opposite directions.
    """
    cage = create_subd_primitive("cube", width=2, height=2, depth=2)
    eids = _box_middle_loop_eids(cage)

    pos = subd_loop_slide(cage, eids, t=1.0)
    neg = subd_loop_slide(cage, eids, t=-1.0)

    top_verts = [i for i, v in enumerate(cage.vertices) if abs(v[2] - 1.0) < 1e-9]
    for vi in top_verts:
        orig = cage.vertices[vi]
        dz_pos = pos.vertices[vi][2] - orig[2]
        dz_neg = neg.vertices[vi][2] - orig[2]
        assert abs(abs(dz_pos) - abs(dz_neg)) < 1e-9, (
            f"|Δz| not symmetric: +t gives {dz_pos}, -t gives {dz_neg}"
        )
        assert dz_pos * dz_neg <= 0.0 + 1e-9, (
            f"Δz should be in opposite directions: {dz_pos}, {dz_neg}"
        )


# ---------------------------------------------------------------------------
# Test 6: never raises on bad input
# ---------------------------------------------------------------------------

def test_loop_slide_never_raises():
    cage = create_subd_primitive("cube")

    # Empty edge loop
    result = subd_loop_slide(cage, [], t=0.5)
    assert result.num_vertices == cage.num_vertices

    # Out-of-range edge ids
    result = subd_loop_slide(cage, [9999, -1], t=0.5)
    assert result.num_vertices == cage.num_vertices

    # t=0 is identity
    result = subd_loop_slide(cage, [0, 1, 2, 3], t=0.0)
    assert result.num_vertices == cage.num_vertices


# ---------------------------------------------------------------------------
# Test 7: export available from geom public facade
# ---------------------------------------------------------------------------

def test_geom_init_exports_loop_slide():
    from kerf_cad_core.geom import subd_loop_slide as fn
    assert callable(fn)
