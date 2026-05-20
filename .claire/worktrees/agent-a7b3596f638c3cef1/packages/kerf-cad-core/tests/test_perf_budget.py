"""GK-70: Performance budget regression tests.

Times SSI and boolean operations on the primitive matrix and asserts
against *recorded generous thresholds*.  The point is regression-catching,
not micro-benchmarking — thresholds are set with a large margin above what
was measured at implementation time.

Hermetic: pure Python + NumPy.  No OCCT, no DB, no network.

Run:
    python -m pytest packages/kerf-cad-core/tests/test_perf_budget.py -q
    python -m pytest packages/kerf-cad-core/tests/test_perf_budget.py -q -m "not slow"
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.intersection import surface_surface_intersect
from kerf_cad_core.geom.brep_build import box_to_body, cylinder_to_body, sphere_to_body
from kerf_cad_core.geom.boolean import body_difference, body_union, body_intersection


# ---------------------------------------------------------------------------
# Generous thresholds (ms) — edit upward if hardware is demonstrably slower;
# never edit downward without a corresponding performance improvement commit.
# ---------------------------------------------------------------------------

#: SSI: two unit spheres at origin / offset — marching intersection
_T_SSI_SPHERE_SPHERE_MS = 2_000       # 2 s ceiling; typical < 200 ms

#: SSI: sphere ∩ plane
_T_SSI_SPHERE_PLANE_MS = 2_000

#: SSI: cylinder ∩ plane
_T_SSI_CYL_PLANE_MS = 2_000

#: SSI: sphere ∩ cylinder
_T_SSI_SPHERE_CYL_MS = 4_000          # 4 s — two analytic surfaces marching

#: Boolean: box − box (AABB cell decomp, very fast)
_T_BOOL_BOX_MINUS_BOX_MS = 500

#: Boolean: box ∩ box
_T_BOOL_BOX_INTER_BOX_MS = 500

#: Boolean: box ∪ box
_T_BOOL_BOX_UNION_BOX_MS = 500

#: Boolean: box − cylinder (imprint path, more work)
_T_BOOL_BOX_MINUS_CYL_MS = 2_000

#: Boolean: sphere − sphere (contained / disjoint fast paths)
_T_BOOL_SPHERE_MINUS_SPHERE_DISJOINT_MS = 500

#: Boolean: sphere ∪ sphere
_T_BOOL_SPHERE_UNION_MS = 1_000

#: Boolean: sphere ∩ sphere
_T_BOOL_SPHERE_INTER_MS = 1_000

#: Primitive construction — box_to_body
_T_PRIM_BOX_MS = 200

#: Primitive construction — cylinder_to_body
_T_PRIM_CYL_MS = 200

#: Primitive construction — sphere_to_body
_T_PRIM_SPHERE_MS = 200


# ---------------------------------------------------------------------------
# NURBS primitive factories (copied from test_ssi_robust.py pattern)
# ---------------------------------------------------------------------------

_S = math.sqrt(2.0) / 2.0
_CIRC9 = [
    (1.0, 0.0, 1.0), (1.0, 1.0, _S), (0.0, 1.0, 1.0), (-1.0, 1.0, _S),
    (-1.0, 0.0, 1.0), (-1.0, -1.0, _S), (0.0, -1.0, 1.0), (1.0, -1.0, _S),
    (1.0, 0.0, 1.0),
]
_KU9 = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])


def _make_rational_sphere(center, r) -> NurbsSurface:
    """Exact NURBS sphere."""
    center = np.asarray(center, dtype=float)
    mer = [
        (0.0, -r, 1.0), (r, -r, _S), (r, 0.0, 1.0), (r, r, _S), (0.0, r, 1.0),
    ]
    cp = np.zeros((9, 5, 3))
    w = np.zeros((9, 5))
    for i, (cx, cy, cw) in enumerate(_CIRC9):
        for j, (mx, mz, mw) in enumerate(mer):
            cp[i, j] = [center[0] + mx * cx, center[1] + mx * cy,
                        center[2] + mz]
            w[i, j] = cw * mw
    kv = np.array([0, 0, 0, .5, .5, 1, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2, control_points=cp,
                        knots_u=_KU9.copy(), knots_v=kv, weights=w)


def _make_rational_cylinder(axis_pt, axis_dir, r, half_len) -> NurbsSurface:
    """Exact NURBS right circular cylinder."""
    axis_pt = np.asarray(axis_pt, dtype=float)
    axis_dir = np.asarray(axis_dir, dtype=float)
    axis_dir = axis_dir / np.linalg.norm(axis_dir)
    ref = (np.array([1.0, 0.0, 0.0]) if abs(axis_dir[0]) < 0.9
           else np.array([0.0, 1.0, 0.0]))
    e1 = ref - (ref @ axis_dir) * axis_dir
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(axis_dir, e1)
    cp = np.zeros((9, 2, 3))
    w = np.zeros((9, 2))
    for i, (cx, cy, cw) in enumerate(_CIRC9):
        radial = r * (cx * e1 + cy * e2)
        for j, t in enumerate((-half_len, half_len)):
            cp[i, j] = axis_pt + radial + t * axis_dir
            w[i, j] = cw
    kv = np.array([0, 0, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=1, control_points=cp,
                        knots_u=_KU9.copy(), knots_v=kv, weights=w)


def _make_plane(point, normal, half=3.0) -> NurbsSurface:
    """Bilinear finite plane patch."""
    point = np.asarray(point, dtype=float)
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    ref = (np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9
           else np.array([0.0, 1.0, 0.0]))
    e1 = ref - (ref @ n) * n
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    cp = np.zeros((2, 2, 3))
    for i, su in enumerate((-half, half)):
        for j, sv in enumerate((-half, half)):
            cp[i, j] = point + su * e1 + sv * e2
    k = np.array([0, 0, 1, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cp,
                        knots_u=k.copy(), knots_v=k.copy())


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ms(start: float) -> float:
    """Elapsed milliseconds since *start* (perf_counter)."""
    return (time.perf_counter() - start) * 1_000.0


# ---------------------------------------------------------------------------
# Primitive construction budgets
# ---------------------------------------------------------------------------


def test_perf_prim_box_construction():
    """box_to_body must complete within budget."""
    t0 = time.perf_counter()
    body = box_to_body([0.0, 0.0, 0.0], 2.0, 3.0, 4.0)
    elapsed = _ms(t0)
    assert body is not None
    assert elapsed < _T_PRIM_BOX_MS, (
        f"box_to_body took {elapsed:.1f} ms — budget {_T_PRIM_BOX_MS} ms"
    )


def test_perf_prim_cylinder_construction():
    """cylinder_to_body must complete within budget."""
    t0 = time.perf_counter()
    body = cylinder_to_body([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1.0, 2.0)
    elapsed = _ms(t0)
    assert body is not None
    assert elapsed < _T_PRIM_CYL_MS, (
        f"cylinder_to_body took {elapsed:.1f} ms — budget {_T_PRIM_CYL_MS} ms"
    )


def test_perf_prim_sphere_construction():
    """sphere_to_body must complete within budget."""
    t0 = time.perf_counter()
    body = sphere_to_body([0.0, 0.0, 0.0], 1.0)
    elapsed = _ms(t0)
    assert body is not None
    assert elapsed < _T_PRIM_SPHERE_MS, (
        f"sphere_to_body took {elapsed:.1f} ms — budget {_T_PRIM_SPHERE_MS} ms"
    )


# ---------------------------------------------------------------------------
# SSI performance budgets
# ---------------------------------------------------------------------------


def test_perf_ssi_sphere_sphere():
    """SSI sphere ∩ sphere must complete within budget.

    Two unit spheres offset by 1.0 — they intersect along a circle of
    radius sqrt(3)/2.  The SSI must find at least one branch.
    """
    sA = _make_rational_sphere([0.0, 0.0, 0.0], 1.0)
    sB = _make_rational_sphere([1.0, 0.0, 0.0], 1.0)

    t0 = time.perf_counter()
    result = surface_surface_intersect(sA, sB, tol=1e-4, step=0.05)
    elapsed = _ms(t0)

    assert result["ok"], f"SSI failed: {result.get('reason')}"
    assert result["branch_count"] >= 1, "Expected at least one intersection branch"
    assert elapsed < _T_SSI_SPHERE_SPHERE_MS, (
        f"SSI sphere∩sphere took {elapsed:.1f} ms — budget {_T_SSI_SPHERE_SPHERE_MS} ms"
    )


def test_perf_ssi_sphere_plane():
    """SSI sphere ∩ plane must complete within budget."""
    sph = _make_rational_sphere([0.0, 0.0, 0.0], 1.0)
    pln = _make_plane([0.0, 0.5, 0.0], [0.0, 1.0, 0.0], half=2.0)

    t0 = time.perf_counter()
    result = surface_surface_intersect(sph, pln, tol=1e-4, step=0.05)
    elapsed = _ms(t0)

    assert result["ok"], f"SSI failed: {result.get('reason')}"
    assert result["branch_count"] >= 1
    assert elapsed < _T_SSI_SPHERE_PLANE_MS, (
        f"SSI sphere∩plane took {elapsed:.1f} ms — budget {_T_SSI_SPHERE_PLANE_MS} ms"
    )


@pytest.mark.slow
def test_perf_ssi_cylinder_plane():
    """SSI cylinder ∩ plane must complete within budget (marked slow)."""
    cyl = _make_rational_cylinder([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1.0, 1.5)
    pln = _make_plane([0.0, 0.0, 0.5], [0.0, 0.0, 1.0], half=2.0)

    t0 = time.perf_counter()
    result = surface_surface_intersect(cyl, pln, tol=1e-4, step=0.05)
    elapsed = _ms(t0)

    assert result["ok"], f"SSI failed: {result.get('reason')}"
    assert result["branch_count"] >= 1
    assert elapsed < _T_SSI_CYL_PLANE_MS, (
        f"SSI cylinder∩plane took {elapsed:.1f} ms — budget {_T_SSI_CYL_PLANE_MS} ms"
    )


@pytest.mark.slow
def test_perf_ssi_sphere_cylinder():
    """SSI sphere ∩ cylinder must complete within budget (marked slow)."""
    sph = _make_rational_sphere([0.0, 0.0, 0.5], 1.2)
    cyl = _make_rational_cylinder([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1.0, 1.5)

    t0 = time.perf_counter()
    result = surface_surface_intersect(sph, cyl, tol=1e-4, step=0.05)
    elapsed = _ms(t0)

    # The sphere and cylinder may or may not intersect depending on geometry;
    # we only assert that SSI terminates (ok may be True or False for no-hit).
    assert result is not None
    assert elapsed < _T_SSI_SPHERE_CYL_MS, (
        f"SSI sphere∩cylinder took {elapsed:.1f} ms — budget {_T_SSI_SPHERE_CYL_MS} ms"
    )


# ---------------------------------------------------------------------------
# Boolean performance budgets
# ---------------------------------------------------------------------------


def test_perf_bool_box_minus_box():
    """body_difference(box, box) must complete within budget."""
    a = box_to_body([0.0, 0.0, 0.0], 4.0, 4.0, 4.0)
    b = box_to_body([2.0, 2.0, 2.0], 3.0, 3.0, 3.0)

    t0 = time.perf_counter()
    result = body_difference(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_BOX_MINUS_BOX_MS, (
        f"body_difference(box, box) took {elapsed:.1f} ms — budget {_T_BOOL_BOX_MINUS_BOX_MS} ms"
    )


def test_perf_bool_box_intersection_box():
    """body_intersection(box, box) must complete within budget."""
    a = box_to_body([0.0, 0.0, 0.0], 4.0, 4.0, 4.0)
    b = box_to_body([2.0, 2.0, 2.0], 4.0, 4.0, 4.0)

    t0 = time.perf_counter()
    result = body_intersection(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_BOX_INTER_BOX_MS, (
        f"body_intersection(box, box) took {elapsed:.1f} ms — budget {_T_BOOL_BOX_INTER_BOX_MS} ms"
    )


def test_perf_bool_box_union_box():
    """body_union(box, box) must complete within budget."""
    a = box_to_body([0.0, 0.0, 0.0], 3.0, 3.0, 3.0)
    b = box_to_body([2.0, 2.0, 2.0], 3.0, 3.0, 3.0)

    t0 = time.perf_counter()
    result = body_union(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_BOX_UNION_BOX_MS, (
        f"body_union(box, box) took {elapsed:.1f} ms — budget {_T_BOOL_BOX_UNION_BOX_MS} ms"
    )


def test_perf_bool_box_minus_cylinder():
    """body_difference(box, cyl) — the cylinder-through-box imprint path.

    This is the canonical production path exercised by every drilled-hole
    feature.  Budget: 2 s (generous margin).
    """
    # Box: 4×4×6, centred at origin for Z
    box = box_to_body([-2.0, -2.0, 0.0], 4.0, 4.0, 6.0)
    # Cylinder: radius 0.75, fully pierces the box along Z
    cyl = cylinder_to_body([0.0, 0.0, -1.0], [0.0, 0.0, 1.0], 0.75, 8.0)

    t0 = time.perf_counter()
    result = body_difference(box, cyl)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_BOX_MINUS_CYL_MS, (
        f"body_difference(box, cyl) took {elapsed:.1f} ms — budget {_T_BOOL_BOX_MINUS_CYL_MS} ms"
    )


def test_perf_bool_sphere_minus_sphere_disjoint():
    """body_difference on disjoint spheres — fast containment path."""
    a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
    b = sphere_to_body([5.0, 0.0, 0.0], 1.0)

    t0 = time.perf_counter()
    result = body_difference(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_SPHERE_MINUS_SPHERE_DISJOINT_MS, (
        f"body_difference(sphere disjoint sphere) took {elapsed:.1f} ms "
        f"— budget {_T_BOOL_SPHERE_MINUS_SPHERE_DISJOINT_MS} ms"
    )


def test_perf_bool_sphere_union():
    """body_union(sphere, sphere) — disjoint multi-solid path."""
    a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
    b = sphere_to_body([5.0, 0.0, 0.0], 1.0)

    t0 = time.perf_counter()
    result = body_union(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_SPHERE_UNION_MS, (
        f"body_union(sphere, sphere) took {elapsed:.1f} ms — budget {_T_BOOL_SPHERE_UNION_MS} ms"
    )


def test_perf_bool_sphere_intersection():
    """body_intersection(sphere, sphere) — overlapping lens path."""
    # Two spheres of radius 1 with centres 1.0 apart — overlapping lens
    a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
    b = sphere_to_body([1.0, 0.0, 0.0], 1.0)

    t0 = time.perf_counter()
    result = body_intersection(a, b)
    elapsed = _ms(t0)

    assert result is not None
    assert elapsed < _T_BOOL_SPHERE_INTER_MS, (
        f"body_intersection(sphere, sphere) took {elapsed:.1f} ms "
        f"— budget {_T_BOOL_SPHERE_INTER_MS} ms"
    )


# ---------------------------------------------------------------------------
# Primitive matrix: construction + boolean round-trip correctness sanity
# ---------------------------------------------------------------------------


def test_perf_primitive_matrix_construction_all():
    """All primitive constructors must complete well inside combined budget.

    Combined budget for 3 primitives: 600 ms total (200 ms each).
    Also checks validate_body is implicitly satisfied (constructors assert).
    """
    t0 = time.perf_counter()
    box = box_to_body([0.0, 0.0, 0.0], 2.0, 2.0, 2.0)
    cyl = cylinder_to_body([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 0.5, 3.0)
    sph = sphere_to_body([1.0, 1.0, 1.0], 0.8)
    elapsed = _ms(t0)

    assert box is not None and cyl is not None and sph is not None
    combined_budget = _T_PRIM_BOX_MS + _T_PRIM_CYL_MS + _T_PRIM_SPHERE_MS
    assert elapsed < combined_budget, (
        f"Combined primitive construction took {elapsed:.1f} ms "
        f"— combined budget {combined_budget} ms"
    )


@pytest.mark.slow
def test_perf_ssi_matrix_sphere_sphere_tight():
    """SSI sphere∩sphere with tighter tolerance — regression for analytic path.

    Uses concentric offset spheres (radius 1 and 1.5, same centre) — the
    inner sphere is fully contained so SSI finds no intersection.  Verifies
    the no-hit fast-path terminates quickly even at tighter tolerance.
    """
    sA = _make_rational_sphere([0.0, 0.0, 0.0], 1.0)
    sB = _make_rational_sphere([0.0, 0.0, 0.0], 1.5)

    t0 = time.perf_counter()
    result = surface_surface_intersect(sA, sB, tol=1e-5, step=0.02)
    elapsed = _ms(t0)

    # concentric spheres — the NURBS representations are distinct but do not
    # intersect geometrically; result may be ok=True with 0 branches or
    # ok=False (depends on seeding).  Either way it must terminate.
    assert result is not None
    assert elapsed < _T_SSI_SPHERE_SPHERE_MS, (
        f"SSI concentric spheres took {elapsed:.1f} ms "
        f"— budget {_T_SSI_SPHERE_SPHERE_MS} ms"
    )
