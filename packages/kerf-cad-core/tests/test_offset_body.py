"""
test_offset_body.py
===================
GK-120 — Hermetic pytest oracle for offset_body / uniform body offset.

Oracle contracts
----------------
1.  offset_body(sphere(r), d)  → validated Body with SphereSurface.radius == r+d
2.  Negative offset shrinks the sphere (r=5, d=-1 → radius 4).
3.  offset_body is importable from kerf_cad_core.geom.
4.  Collapsing offset (d <= -r) raises ValueError.
5.  offset_body(make_box(...), d)  → validated planar-faced body with expanded dims.
6.  Torus offset → validated body with new minor_radius.
7.  Zero distance → geometrically unchanged body (same radius ± tol).
8.  validate_body passes on every result body.
9.  Input type guard: non-Body raises ValueError.
10. Non-finite distance raises ValueError.

Run:
    python -m pytest packages/kerf-cad-core/tests/test_offset_body.py -q
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom import offset_body
from kerf_cad_core.geom.brep import (
    SphereSurface,
    TorusSurface,
    make_box,
    make_sphere,
    make_torus,
    validate_body,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sphere_radius(body) -> float:
    """Extract the SphereSurface radius from a single-face sphere body."""
    face = body.solids[0].shells[0].faces[0]
    assert isinstance(face.surface, SphereSurface), f"Expected SphereSurface, got {type(face.surface)}"
    return face.surface.radius


def _torus_minor_radius(body) -> float:
    """Extract the TorusSurface minor_radius from a single-face torus body."""
    face = body.solids[0].shells[0].faces[0]
    assert isinstance(face.surface, TorusSurface), f"Expected TorusSurface, got {type(face.surface)}"
    return face.surface.minor_radius


TOL = 1e-9


# ---------------------------------------------------------------------------
# 1.  Sphere oracle: offset by +d grows radius to r+d
# ---------------------------------------------------------------------------

class TestOffsetBodySphereGrow:
    def test_unit_sphere_grow_1(self):
        r, d = 1.0, 1.0
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL

    def test_sphere_radius_5_grow_2(self):
        r, d = 5.0, 2.0
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL

    def test_sphere_small_grow(self):
        r, d = 0.5, 0.001
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL

    def test_sphere_large_grow(self):
        r, d = 100.0, 50.0
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL


# ---------------------------------------------------------------------------
# 2.  Sphere oracle: negative offset shrinks radius to r+d
# ---------------------------------------------------------------------------

class TestOffsetBodySphereShrink:
    def test_sphere_shrink_1(self):
        r, d = 3.0, -1.0
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL

    def test_sphere_shrink_half(self):
        r = 4.0
        b = offset_body(make_sphere(radius=r), -r / 2)
        assert abs(_sphere_radius(b) - r / 2) < TOL

    def test_sphere_shrink_small(self):
        r, d = 10.0, -0.001
        b = offset_body(make_sphere(radius=r), d)
        assert abs(_sphere_radius(b) - (r + d)) < TOL


# ---------------------------------------------------------------------------
# 3.  Import from kerf_cad_core.geom
# ---------------------------------------------------------------------------

class TestOffsetBodyImport:
    def test_importable_from_geom(self):
        from kerf_cad_core.geom import offset_body as _ob
        assert callable(_ob)

    def test_in_all(self):
        import kerf_cad_core.geom as geom_mod
        assert "offset_body" in geom_mod.__all__


# ---------------------------------------------------------------------------
# 4.  Collapsing offset raises ValueError
# ---------------------------------------------------------------------------

class TestOffsetBodyCollapseError:
    def test_sphere_collapse_exact(self):
        r = 2.0
        with pytest.raises(ValueError, match="collapses|radius"):
            offset_body(make_sphere(radius=r), -r)

    def test_sphere_collapse_over(self):
        with pytest.raises(ValueError):
            offset_body(make_sphere(radius=1.0), -5.0)


# ---------------------------------------------------------------------------
# 5.  Box (planar-faced) offset
# ---------------------------------------------------------------------------

class TestOffsetBodyBox:
    def test_box_grow_validated(self):
        b = make_box(size=(2.0, 3.0, 4.0))
        b2 = offset_body(b, 1.0)
        res = validate_body(b2)
        assert res["ok"], res["errors"]

    def test_box_shrink_validated(self):
        b = make_box(size=(4.0, 4.0, 4.0))
        b2 = offset_body(b, -0.5)
        res = validate_body(b2)
        assert res["ok"], res["errors"]

    def test_box_zero_offset_validated(self):
        b = make_box(size=(3.0, 3.0, 3.0))
        b2 = offset_body(b, 0.0)
        res = validate_body(b2)
        assert res["ok"], res["errors"]


# ---------------------------------------------------------------------------
# 6.  Torus offset
# ---------------------------------------------------------------------------

class TestOffsetBodyTorus:
    def test_torus_grow(self):
        major, minor, d = 3.0, 0.5, 0.2
        b = offset_body(make_torus(major_radius=major, minor_radius=minor), d)
        assert abs(_torus_minor_radius(b) - (minor + d)) < TOL

    def test_torus_shrink(self):
        major, minor, d = 3.0, 1.0, -0.3
        b = offset_body(make_torus(major_radius=major, minor_radius=minor), d)
        assert abs(_torus_minor_radius(b) - (minor + d)) < TOL

    def test_torus_validated(self):
        b = offset_body(make_torus(major_radius=4.0, minor_radius=0.5), 0.1)
        res = validate_body(b)
        assert res["ok"], res["errors"]

    def test_torus_collapse_raises(self):
        with pytest.raises(ValueError):
            offset_body(make_torus(major_radius=3.0, minor_radius=1.0), -1.0)


# ---------------------------------------------------------------------------
# 7.  Zero distance: geometrically unchanged
# ---------------------------------------------------------------------------

class TestOffsetBodyZero:
    def test_sphere_zero(self):
        r = 7.0
        b = offset_body(make_sphere(radius=r), 0.0)
        assert abs(_sphere_radius(b) - r) < TOL

    def test_sphere_zero_validated(self):
        b = offset_body(make_sphere(radius=2.0), 0.0)
        res = validate_body(b)
        assert res["ok"], res["errors"]


# ---------------------------------------------------------------------------
# 8.  validate_body passes on every result
# ---------------------------------------------------------------------------

class TestOffsetBodyValidated:
    def test_sphere_grow_valid(self):
        res = validate_body(offset_body(make_sphere(radius=2.0), 0.5))
        assert res["ok"], res["errors"]

    def test_sphere_shrink_valid(self):
        res = validate_body(offset_body(make_sphere(radius=5.0), -1.0))
        assert res["ok"], res["errors"]

    def test_torus_valid(self):
        res = validate_body(offset_body(make_torus(major_radius=3.0, minor_radius=0.5), 0.1))
        assert res["ok"], res["errors"]


# ---------------------------------------------------------------------------
# 9.  Input type guard
# ---------------------------------------------------------------------------

class TestOffsetBodyTypeGuard:
    def test_non_body_raises(self):
        with pytest.raises((ValueError, TypeError)):
            offset_body("not a body", 1.0)  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises((ValueError, TypeError)):
            offset_body(None, 1.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 10.  Non-finite distance raises ValueError
# ---------------------------------------------------------------------------

class TestOffsetBodyBadDistance:
    def test_nan_distance(self):
        with pytest.raises(ValueError):
            offset_body(make_sphere(radius=1.0), float("nan"))

    def test_inf_distance(self):
        with pytest.raises(ValueError):
            offset_body(make_sphere(radius=1.0), float("inf"))
