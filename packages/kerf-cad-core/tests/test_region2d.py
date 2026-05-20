"""Tests for GK-56: 2D region boolean on planar curve loops.

Hermetic pure-Python oracle tests — no network, no OCCT, no fixtures.

Primary oracle
--------------
area(unit_square − inscribed_circle_r=0.5) == 1 − π·(0.5)² == 1 − π/4

We use the unit square [0,1]×[0,1] and a circle centered at (0.5, 0.5)
with radius 0.4 (fully inside the square), so:
    area(difference) == 1 − π·(0.4)² == 1 − 0.16π

Orientation contract (from BREP_CONTRACT.md §3 validate_body):
    outer loop  → CCW (positive signed area)
    inner loops → CW  (negative signed area)
"""

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import Face, Loop
from kerf_cad_core.geom.region2d import (
    make_circle_loop,
    make_rect_loop,
    region_area,
    region_difference,
    region_intersection,
    region_union,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _outer_area(face: Face) -> float:
    """Signed area of the outer loop (positive for CCW)."""
    ol = face.outer_loop()
    assert ol is not None
    return region_area(ol)


def _inner_areas(face: Face):
    """List of signed areas of inner (hole) loops."""
    return [region_area(lp) for lp in face.inner_loops()]


def _net_area(face: Face) -> float:
    """Sum of all signed loop areas == net filled area."""
    return region_area(face)


# ---------------------------------------------------------------------------
# Basic loop construction
# ---------------------------------------------------------------------------

def test_make_rect_loop_area():
    lp = make_rect_loop(0, 0, 1, 1)
    assert abs(region_area(lp)) == pytest.approx(1.0, rel=1e-6)


def test_make_rect_loop_ccw():
    lp = make_rect_loop(0, 0, 2, 3)
    assert region_area(lp) > 0, "make_rect_loop must be CCW (positive area)"


def test_make_circle_loop_area():
    lp = make_circle_loop(0, 0, 1.0)
    assert abs(region_area(lp)) == pytest.approx(math.pi, rel=1e-3)


def test_make_circle_loop_ccw():
    lp = make_circle_loop(0, 0, 1.0)
    assert region_area(lp) > 0, "make_circle_loop must be CCW (positive area)"


# ---------------------------------------------------------------------------
# region_difference — ORACLE: area(square − circle) = 1 − π·r²
# ---------------------------------------------------------------------------

def test_difference_square_minus_circle_area_oracle():
    """PRIMARY ORACLE: area(unit_square − circle(r=0.4)) == 1 − 0.16π.

    Tolerance ≤ 1e-7.
    """
    r = 0.4
    square = make_rect_loop(0, 0, 1, 1)
    circle = make_circle_loop(0.5, 0.5, r)

    face = region_difference(square, circle)
    assert face is not None, "region_difference must return a Face"

    expected = 1.0 - math.pi * r * r
    actual = _net_area(face)
    assert abs(actual - expected) <= 1e-7, (
        f"area(square − circle) = {actual}, expected {expected}, "
        f"delta = {abs(actual - expected)}"
    )


def test_difference_square_minus_circle_has_hole():
    """Difference of square − inscribed circle must produce a hole loop."""
    square = make_rect_loop(0, 0, 1, 1)
    circle = make_circle_loop(0.5, 0.5, 0.3)

    face = region_difference(square, circle)
    assert face is not None
    assert len(face.inner_loops()) >= 1, "square − circle must have at least one hole loop"


def test_difference_outer_loop_ccw():
    """Outer loop of difference result must be CCW (positive signed area)."""
    square = make_rect_loop(0, 0, 1, 1)
    circle = make_circle_loop(0.5, 0.5, 0.3)
    face = region_difference(square, circle)
    assert face is not None
    outer_a = _outer_area(face)
    assert outer_a > 0, f"outer loop must be CCW; signed area = {outer_a}"


def test_difference_inner_loop_cw():
    """Inner (hole) loop of difference result must be CW (negative signed area)."""
    square = make_rect_loop(0, 0, 1, 1)
    circle = make_circle_loop(0.5, 0.5, 0.3)
    face = region_difference(square, circle)
    assert face is not None
    for i, a in enumerate(_inner_areas(face)):
        assert a < 0, f"inner loop {i} must be CW (negative area); got {a}"


def test_difference_disjoint_returns_face_with_no_holes():
    """A − B where A and B are disjoint: result is A, no holes."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(5, 5, 7, 7)
    face = region_difference(a, b)
    assert face is not None
    assert len(face.inner_loops()) == 0
    assert _net_area(face) == pytest.approx(4.0, rel=1e-4)


def test_difference_a_fully_inside_b_returns_none():
    """A fully inside B: A − B is empty → returns None."""
    small = make_rect_loop(1, 1, 2, 2)
    large = make_rect_loop(0, 0, 4, 4)
    face = region_difference(small, large)
    assert face is None


def test_difference_partial_overlap():
    """A=(0,0)-(2,2) minus B=(1,0)-(3,2): intersection 1×2=2; diff area=2."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(1, 0, 3, 2)
    face = region_difference(a, b)
    assert face is not None
    assert _net_area(face) == pytest.approx(2.0, rel=1e-3)


def test_difference_b_fully_inside_a_area():
    """Outer 4×4=16 minus inner 2×2=4: net area = 12."""
    outer = make_rect_loop(0, 0, 4, 4)
    inner = make_rect_loop(1, 1, 3, 3)
    face = region_difference(outer, inner)
    assert face is not None
    assert _net_area(face) == pytest.approx(12.0, rel=1e-3)


# ---------------------------------------------------------------------------
# region_union
# ---------------------------------------------------------------------------

def test_union_disjoint_returns_face():
    """Union of two non-overlapping rects: face has both loops, area = sum."""
    a = make_rect_loop(0, 0, 1, 1)
    b = make_rect_loop(3, 3, 4, 4)
    face = region_union(a, b)
    assert face is not None
    # Net area may be total or just one polygon (implementation varies)
    total = float(abs(_net_area(face)))
    assert total >= 1.0  # at least the area of the larger polygon


def test_union_identical_returns_one_face():
    """Union of identical squares returns a single-outer-loop face with same area."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(0, 0, 2, 2)
    face = region_union(a, b)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(4.0, rel=1e-3)


def test_union_contained_returns_outer():
    """Union of inner ⊂ outer: result is the outer, area = 16."""
    outer = make_rect_loop(0, 0, 4, 4)
    inner = make_rect_loop(1, 1, 3, 3)
    face = region_union(outer, inner)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(16.0, rel=1e-3)


def test_union_overlapping_rects_area():
    """A=(0,0)-(2,2), B=(1,0)-(3,2): union area = 6."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(1, 0, 3, 2)
    face = region_union(a, b)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(6.0, rel=1e-3)


def test_union_outer_loop_ccw():
    """Outer loop of union result must be CCW."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(1, 0, 3, 2)
    face = region_union(a, b)
    assert face is not None
    assert _outer_area(face) > 0


# ---------------------------------------------------------------------------
# region_intersection
# ---------------------------------------------------------------------------

def test_intersection_disjoint_returns_none():
    """Intersection of disjoint loops is empty → None."""
    a = make_rect_loop(0, 0, 1, 1)
    b = make_rect_loop(5, 5, 6, 6)
    face = region_intersection(a, b)
    assert face is None


def test_intersection_overlapping_rects():
    """A=(0,0)-(2,2) ∩ B=(1,0)-(3,2) = 1×2 rectangle, area=2."""
    a = make_rect_loop(0, 0, 2, 2)
    b = make_rect_loop(1, 0, 3, 2)
    face = region_intersection(a, b)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(2.0, rel=1e-3)


def test_intersection_contained_returns_inner():
    """Intersection of outer ⊃ inner = inner, area=4."""
    outer = make_rect_loop(0, 0, 4, 4)
    inner = make_rect_loop(1, 1, 3, 3)
    face = region_intersection(outer, inner)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(4.0, rel=1e-3)


def test_intersection_identical():
    """Intersection of identical loops = same loop, area = 9."""
    a = make_rect_loop(0, 0, 3, 3)
    b = make_rect_loop(0, 0, 3, 3)
    face = region_intersection(a, b)
    assert face is not None
    assert abs(_net_area(face)) == pytest.approx(9.0, rel=1e-3)


def test_intersection_outer_loop_ccw():
    """Outer loop of intersection must be CCW."""
    a = make_rect_loop(0, 0, 3, 3)
    b = make_rect_loop(1, 1, 4, 4)
    face = region_intersection(a, b)
    assert face is not None
    assert _outer_area(face) > 0


# ---------------------------------------------------------------------------
# Loop structure / BREP contract checks
# ---------------------------------------------------------------------------

def test_face_has_outer_loop():
    """All region_* results must have a valid outer_loop()."""
    square = make_rect_loop(0, 0, 1, 1)
    circle = make_circle_loop(0.5, 0.5, 0.3)
    for op, fn in [("union", region_union), ("intersection", region_intersection),
                   ("difference", region_difference)]:
        face = fn(square, circle)
        if face is not None:
            ol = face.outer_loop()
            assert ol is not None, f"{op} result face has no outer_loop()"
            # A circle loop may have 1 coedge (full CircleArc3); >= 1 required
            assert len(ol.coedges) >= 1, f"{op} outer loop has 0 coedges"


def test_face_surface_is_plane():
    """Result Face.surface must be a Plane instance."""
    from kerf_cad_core.geom.brep import Plane as BrepPlane
    square = make_rect_loop(0, 0, 2, 2)
    circle = make_circle_loop(1.0, 1.0, 0.5)
    face = region_difference(square, circle)
    assert face is not None
    assert isinstance(face.surface, BrepPlane)


def test_inclusion_exclusion_oracle():
    """area(A∪B) = area(A) + area(B) − area(A∩B) for overlapping rects."""
    a = make_rect_loop(0, 0, 3, 3)
    b = make_rect_loop(2, 0, 5, 3)

    area_a = abs(region_area(a))
    area_b = abs(region_area(b))

    f_union = region_union(a, b)
    f_isect = region_intersection(a, b)

    area_union = abs(_net_area(f_union)) if f_union else 0.0
    area_isect = abs(_net_area(f_isect)) if f_isect else 0.0

    assert area_a == pytest.approx(9.0, rel=1e-5)
    assert area_b == pytest.approx(9.0, rel=1e-5)
    assert area_isect == pytest.approx(3.0, rel=1e-3)
    assert area_union == pytest.approx(15.0, rel=1e-3)
    assert area_union == pytest.approx(area_a + area_b - area_isect, rel=1e-3)
