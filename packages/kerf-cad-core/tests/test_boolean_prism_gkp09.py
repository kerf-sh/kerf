"""GK-P09 — general planar-faced (prismatic) solid boolean.

The closed-form box/cyl/sphere handlers only cover axis-aligned analytic
primitives.  GK-P09 extends ``body_union`` / ``body_intersection`` /
``body_difference`` to arbitrary planar-faced prisms (a planar polygon profile
extruded along a single axis) — the wall-meets-wall / wall-meets-roof / general
non-axis-aligned prismatic CSG flagged by the kernel-parity survey.

Every assertion uses an **exact analytic oracle**: the regularised boolean of
two coaxial coplanar-base prisms equals (2-D regularised profile boolean area)
× (extrusion height).  The body volume is recovered independently via the
divergence theorem and compared against that oracle.  This is the same
self-contained-oracle convention used by ``test_boolean_solid.py`` and is the
pure-Python stand-in for an OCCT-worker parity check (OCCT is WASM-blocked /
not installed in this environment; the analytic value *is* what OCCT computes).

All hermetic: pure Python + NumPy.  No OCCT, no DB, no network.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import Body, validate_body
from kerf_cad_core.geom.brep_build import BuildError, extrude_to_body
from kerf_cad_core.geom.boolean import (
    body_difference,
    body_intersection,
    body_union,
)
from kerf_cad_core.geom import region2d
from kerf_cad_core.geom.boolean import _profile_to_loop, _try_recognise_prism


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rot2(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def _rot_polygon(poly2d, theta: float, cx: float, cy: float):
    """Rotate a 2-D polygon by ``theta`` and translate to (cx, cy), at z=0."""
    R = _rot2(theta)
    off = np.array([cx, cy])
    return [[*(R @ np.asarray(p, float) + off), 0.0] for p in poly2d]


def _prism(poly2d, theta, cx, cy, height, tol=1e-7) -> Body:
    profile = _rot_polygon(poly2d, theta, cx, cy)
    return extrude_to_body(profile, [0.0, 0.0, height], tol=tol)


def _body_volume(body: Body) -> float:
    """Divergence-theorem volume of a closed planar-faced (multi-solid) body."""
    total = 0.0
    for sh in body.all_shells():
        if not sh.is_closed:
            continue
        for f in sh.faces:
            outer = f.outer_loop()
            if outer is None:
                continue
            pts = []
            for ce in outer.coedges:
                p = np.asarray(ce.start_point(), dtype=float)
                if not pts or float(np.linalg.norm(p - pts[-1])) > 1e-12:
                    pts.append(p)
            if len(pts) < 3:
                continue
            n = f.surface_normal(0.5, 0.5)
            c = np.mean(pts, axis=0)
            area_vec = np.zeros(3)
            m = len(pts)
            for i in range(m):
                area_vec += np.cross(pts[i] - c, pts[(i + 1) % m] - c)
            area = float(np.dot(area_vec, n) * 0.5)
            total += float(np.dot(c, n)) * area / 3.0
    return total


def _oracle_volume(a_poly2d, b_poly2d, theta_a, ca, theta_b, cb,
                   height_a, height_b, operation) -> float:
    """Exact (2-D regularised profile boolean area) × height oracle."""
    pa = extrude_to_body(_rot_polygon(a_poly2d, theta_a, *ca),
                         [0, 0, height_a])
    pb = extrude_to_body(_rot_polygon(b_poly2d, theta_b, *cb),
                         [0, 0, height_b])
    sa = _try_recognise_prism(pa)
    sb = _try_recognise_prism(pb)
    fa = _profile_to_loop(sa.profile, 1e-7)
    fb = _profile_to_loop(sb.profile, 1e-7)
    face = region2d._boolean(fa, fb, operation)
    area = region2d.region_area(face) if face is not None else 0.0
    height = min(height_a, height_b) if operation == "intersection" else height_a
    return area * height


_SQUARE = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
_LSHAPE = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]  # non-convex


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------


def test_recognise_rotated_prism():
    p = _prism(_SQUARE, math.radians(37), 0.3, -0.2, 2.0)
    shape = _try_recognise_prism(p)
    assert shape is not None
    assert abs(shape.height - 2.0) < 1e-9
    assert abs(abs(float(np.dot(shape.axis, [0, 0, 1]))) - 1.0) < 1e-9
    assert shape.profile.shape[0] == 4


def test_recognise_lshape_prism():
    p = _prism(_LSHAPE, math.radians(20), 0.0, 0.0, 1.5)
    shape = _try_recognise_prism(p)
    assert shape is not None
    assert shape.profile.shape[0] == 6


# ---------------------------------------------------------------------------
# DoD: union / intersect / difference on two non-axis-aligned prisms,
#      validate_body-clean AND volume == analytic oracle.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op_name,op_fn", [
    ("union", body_union),
    ("intersection", body_intersection),
    ("difference", body_difference),
])
def test_rotated_square_prisms_clean_and_exact(op_name, op_fn):
    theta = math.radians(30.0)
    H = 2.0
    A = _prism(_SQUARE, theta, 0.0, 0.0, H)
    B = _prism(_SQUARE, theta, 0.8, 0.4, H)

    result = op_fn(A, B, tol=1e-6)
    res = validate_body(result)
    assert res["ok"], f"{op_name} produced invalid body: {res['errors']}"

    oracle = _oracle_volume(
        _SQUARE, _SQUARE, theta, (0.0, 0.0), theta, (0.8, 0.4), H, H, op_name,
    )
    vol = _body_volume(result)
    assert abs(vol - oracle) < 1e-6, (
        f"{op_name}: body volume {vol} != oracle {oracle}"
    )


def test_inclusion_exclusion_volume_identity():
    """vol(A∪B) == vol(A) + vol(B) − vol(A∩B) (regularised, non-axis-aligned)."""
    theta = math.radians(22.5)
    H = 1.7
    A = _prism(_SQUARE, theta, 0.0, 0.0, H)
    B = _prism(_SQUARE, theta, 0.9, 0.5, H)

    vA = _body_volume(A)
    vB = _body_volume(B)
    vU = _body_volume(body_union(A, B))
    vI = _body_volume(body_intersection(A, B))
    assert abs(vU - (vA + vB - vI)) < 1e-6


def test_nonconvex_lshape_intersection_clean():
    """Non-convex (L-shaped) prism intersection is validate-clean + exact."""
    theta = math.radians(15.0)
    H = 1.0
    A = _prism(_LSHAPE, theta, 0.0, 0.0, H)
    B = _prism(_SQUARE, theta, 1.0, 1.0, H)

    result = body_intersection(A, B, tol=1e-6)
    res = validate_body(result)
    assert res["ok"], res["errors"]

    oracle = _oracle_volume(
        _LSHAPE, _SQUARE, theta, (0.0, 0.0), theta, (1.0, 1.0), H, H,
        "intersection",
    )
    assert abs(_body_volume(result) - oracle) < 1e-6


def test_disjoint_prisms_union_two_solids():
    """Two disjoint prisms union into a two-solid body with summed volume."""
    H = 1.0
    A = _prism(_SQUARE, 0.0, 0.0, 0.0, H)
    B = _prism(_SQUARE, 0.0, 5.0, 0.0, H)  # far apart, no overlap
    u = body_union(A, B, tol=1e-6)
    assert validate_body(u)["ok"]
    assert len(u.solids) == 2
    assert abs(_body_volume(u) - (_body_volume(A) + _body_volume(B))) < 1e-6


def test_disjoint_prisms_intersection_empty():
    H = 1.0
    A = _prism(_SQUARE, 0.0, 0.0, 0.0, H)
    B = _prism(_SQUARE, 0.0, 5.0, 0.0, H)
    inter = body_intersection(A, B, tol=1e-6)
    assert validate_body(inter)["ok"]
    assert len(inter.solids) == 0


def test_non_coaxial_prisms_raise_unsupported():
    """Two *non-axis-aligned* prisms with different extrusion axes keep the
    strict contract (they cannot reach the AABB fast-path)."""
    # Rotated square so it is NOT an AABB, extruded along Z.
    A = _prism(_SQUARE, math.radians(30), 0.0, 0.0, 2.0)
    # Rotated square, extruded along X (different, non-axis-aligned prism).
    Rb = _rot2(math.radians(30))
    prof_b = [[0.0, *(Rb @ np.array([px, py]))] for (px, py) in _SQUARE]
    B = extrude_to_body(prof_b, [3.0, 0.0, 0.0])
    assert _try_recognise_prism(A) is not None
    assert _try_recognise_prism(B) is not None
    with pytest.raises(BuildError):
        body_union(A, B, tol=1e-6)


def test_difference_fully_inside_hole_raises_unsupported():
    """A − (smaller prism strictly inside) would need a hole profile; the
    pure-prism path raises unsupported-input (rotated, so no AABB fast-path)."""
    H = 1.0
    theta = math.radians(30)
    A = _prism(_SQUARE, theta, 0.0, 0.0, H)            # rotated 2x2
    B = _prism([(-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4)],
               theta, 0.0, 0.0, H)                      # rotated 0.8x0.8 inside
    assert _try_recognise_prism(A) is not None
    assert _try_recognise_prism(B) is not None
    with pytest.raises(BuildError):
        body_difference(A, B, tol=1e-6)
