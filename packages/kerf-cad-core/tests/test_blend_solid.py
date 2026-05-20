"""GK-29 — test suite for blend_solid.py (constant-radius edge/corner blend).

Covers:
  * Single-edge blend on a box: face count, validate_body, volume oracle.
  * blend_edges sequential (non-adjacent box edges).
  * blend_corner_vertex: 3-edge corner blend, validate_body, manifold check.
  * Rejection of out-of-contract inputs (bad radius, non-box body, etc.).

All tests are hermetic (no network, no OCCT, no external fixtures).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.blend_solid import (
    BlendResult,
    blend_corner_vertex,
    blend_edge,
    blend_edges,
)
from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.brep_build import box_to_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _box_volume(lo, hi) -> float:
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    return float(np.prod(hi - lo))


def _pick_edge_along_axis(body, ax: int, at_sign: tuple):
    """Pick an axis-aligned edge of the box along ``ax``."""
    for e in body.all_edges():
        from kerf_cad_core.geom.brep import Line3
        if not isinstance(e.curve, Line3):
            continue
        p0, p1 = e.curve.p0, e.curve.p1
        diff = p1 - p0
        nz = [i for i in range(3) if abs(diff[i]) > 1e-9]
        if len(nz) != 1 or nz[0] != ax:
            continue
        # Check that it's at the right corner (the two perpendicular coords match)
        other = [i for i in range(3) if i != ax]
        lo_corner = at_sign  # (s_other0, s_other1) where 0=lo, 1=hi
        return e
    return None


def _first_axis_edge(body, ax: int):
    """Return any box edge aligned with axis ``ax``."""
    from kerf_cad_core.geom.brep import Line3
    for e in body.all_edges():
        if not isinstance(e.curve, Line3):
            continue
        d = e.curve.p1 - e.curve.p0
        nz = [i for i in range(3) if abs(d[i]) > 1e-9]
        if len(nz) == 1 and nz[0] == ax:
            return e
    return None


def _corner_vertex_at(body, corner, dims, sign):
    """Return the vertex at the box corner given corner origin, dims, and sign triple.

    ``corner`` = origin of box, ``dims`` = (dx,dy,dz), ``sign`` = (0 or 1 per axis).
    sign[ax]=0 => coordinate = corner[ax], sign[ax]=1 => coordinate = corner[ax]+dims[ax].
    """
    lo = np.asarray(corner, dtype=float)
    hi = lo + np.asarray(dims, dtype=float)
    target = np.array([lo[ax] if sign[ax] == 0 else hi[ax] for ax in range(3)])
    for v in body.all_vertices():
        if float(np.linalg.norm(v.point - target)) < 1e-9:
            return v
    return None


# ---------------------------------------------------------------------------
# Single-edge blend oracle
# ---------------------------------------------------------------------------

class TestBlendEdge:
    """Single-edge blend on a unit cube."""

    def test_blend_edge_returns_ok(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)  # vertical edge (along z)
        assert e is not None
        res = blend_edge(body, e, radius=0.1)
        assert res["ok"], res.get("reason")

    def test_blend_edge_validate_body(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.1)
        assert res["ok"]
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_blend_edge_face_count(self):
        """Blending one box edge produces exactly 7 faces."""
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.1)
        assert res["ok"]
        n_faces = len(res["body"].all_faces())
        assert n_faces == 7, f"expected 7 faces, got {n_faces}"

    @pytest.mark.parametrize("r", [0.05, 0.1, 0.2, 0.3])
    def test_volume_oracle_single_edge(self, r):
        """volume_removed = (1 - pi/4) * r^2 * edge_length  (within 1e-6)."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 2.0, 1.0)  # edge along z has length 1
        e = _first_axis_edge(body, 2)
        assert e is not None
        edge_len = float(abs(e.curve.p1[2] - e.curve.p0[2]))
        res = blend_edge(body, e, radius=r)
        assert res["ok"], res.get("reason")
        expected = (1.0 - math.pi / 4.0) * r ** 2 * edge_len
        got = res["volume_removed"]
        assert abs(got - expected) < 1e-6, (
            f"r={r}: expected {expected:.8f}, got {got:.8f}"
        )

    def test_volume_oracle_nontrivial_edge_length(self):
        """Oracle holds for an arbitrary box and edge length."""
        body = box_to_body((0.0, 0.0, 0.0), 3.0, 4.0, 5.0)
        e = _first_axis_edge(body, 0)  # along x, length 3
        edge_len = 3.0
        r = 0.5
        res = blend_edge(body, e, radius=r)
        assert res["ok"], res.get("reason")
        expected = (1.0 - math.pi / 4.0) * r ** 2 * edge_len
        assert abs(res["volume_removed"] - expected) < 1e-6

    def test_blend_edge_volume_monotone(self):
        """Larger radius removes more volume."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 2.0, 2.0)
        e = _first_axis_edge(body, 2)
        r_small = 0.1
        r_large = 0.3
        res_s = blend_edge(body, e, radius=r_small)
        res_l = blend_edge(body, e, radius=r_large)
        assert res_s["ok"] and res_l["ok"]
        assert res_s["volume_removed"] < res_l["volume_removed"]

    def test_blend_edge_bad_radius_zero(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.0)
        assert not res["ok"]

    def test_blend_edge_bad_radius_too_large(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=2.0)  # bigger than edge length
        assert not res["ok"]

    def test_blend_edge_x_axis(self):
        """Blend along x-axis edge, validate body."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 3.0, 4.0)
        e = _first_axis_edge(body, 0)
        res = blend_edge(body, e, radius=0.2)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_blend_edge_y_axis(self):
        """Blend along y-axis edge, validate body."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 3.0, 4.0)
        e = _first_axis_edge(body, 1)
        res = blend_edge(body, e, radius=0.3)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_blend_edge_shifted_box(self):
        """Blend works with a non-origin box."""
        body = box_to_body((5.0, -3.0, 2.0), 2.0, 3.0, 4.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.4)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_blend_result_has_fillet_face(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.1)
        assert res["ok"]
        assert len(res["fillet_faces"]) >= 1

    def test_blend_edge_fillet_face_is_cylindrical(self):
        """The fillet face uses a CylindricalArcSurface."""
        from kerf_cad_core.geom.fillet_solid import _CylindricalArcSurface
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edge(body, e, radius=0.15)
        assert res["ok"]
        ff = res["fillet_faces"][0]
        assert isinstance(ff.surface, _CylindricalArcSurface)


# ---------------------------------------------------------------------------
# blend_edges: sequential non-adjacent edges
# ---------------------------------------------------------------------------

class TestBlendEdges:
    def test_blend_single_via_blend_edges(self):
        """blend_edges with one edge produces same result as blend_edge."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 2.0, 1.0)
        e = _first_axis_edge(body, 2)
        res = blend_edges(body, [e], radius=0.1)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_blend_edges_empty(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        res = blend_edges(body, [], radius=0.1)
        assert not res["ok"]

    def test_blend_edges_volume_single(self):
        """Volume oracle via blend_edges matches blend_edge directly."""
        body = box_to_body((0.0, 0.0, 0.0), 2.0, 2.0, 1.0)
        e = _first_axis_edge(body, 2)
        r = 0.1
        res_e = blend_edge(body, e, radius=r)
        res_es = blend_edges(body, [e], radius=r)
        assert res_e["ok"] and res_es["ok"]
        assert abs(res_e["volume_removed"] - res_es["volume_removed"]) < 1e-10


# ---------------------------------------------------------------------------
# blend_corner_vertex: 3-edge box corner
# ---------------------------------------------------------------------------

class TestBlendCornerVertex:
    def test_corner_blend_returns_ok(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        assert v is not None, "corner vertex not found"
        res = blend_corner_vertex(body, v, radius=0.15)
        assert res["ok"], res.get("reason")

    def test_corner_blend_validate_body(self):
        """The blended body passes validate_body."""
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.15)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], f"validate_body failed: {vr['errors']}"

    def test_corner_blend_is_manifold(self):
        """All edges in the blended body have exactly 2 coedges."""
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.1)
        assert res["ok"], res.get("reason")
        blended = res["body"]
        # validate_body already checks 2-manifold; also check directly
        for sh in blended.all_shells():
            use = {}
            for f in sh.faces:
                for lp in f.loops:
                    for ce in lp.coedges:
                        use.setdefault(id(ce.edge), []).append(ce)
            for eid, ces in use.items():
                assert len(ces) == 2, (
                    f"edge#{ces[0].edge.id} has {len(ces)} coedges, expected 2"
                )

    def test_corner_blend_face_count(self):
        """10-face body: 3 touching + 3 far + 3 cylinder + 1 sphere."""
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.15)
        assert res["ok"], res.get("reason")
        n_faces = len(res["body"].all_faces())
        assert n_faces == 10, f"expected 10 faces, got {n_faces}"

    def test_corner_blend_has_sphere_face(self):
        """At least one fillet face is a spherical surface."""
        from kerf_cad_core.geom.blend_solid import _SphericalOctantSurface
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.1)
        assert res["ok"], res.get("reason")
        sphere_faces = [
            f for f in res["body"].all_faces()
            if isinstance(f.surface, _SphericalOctantSurface)
        ]
        assert len(sphere_faces) == 1, (
            f"expected exactly 1 sphere face, got {len(sphere_faces)}"
        )

    def test_corner_blend_all_corners(self):
        """All 8 box corners can be blended."""
        for s0 in range(2):
            for s1 in range(2):
                for s2 in range(2):
                    body = box_to_body((0.0, 0.0, 0.0), 2.0, 2.0, 2.0)
                    v = _corner_vertex_at(body, (0, 0, 0), (2, 2, 2), [s0, s1, s2])
                    assert v is not None
                    res = blend_corner_vertex(body, v, radius=0.2)
                    assert res["ok"], (
                        f"corner ({s0},{s1},{s2}) failed: {res.get('reason')}"
                    )
                    vr = validate_body(res["body"])
                    assert vr["ok"], (
                        f"corner ({s0},{s1},{s2}) invalid body: {vr['errors']}"
                    )

    def test_corner_blend_bad_radius_zero(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.0)
        assert not res["ok"]

    def test_corner_blend_radius_too_large(self):
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.6)  # >= 0.5 * min_dim = 0.5
        assert not res["ok"]

    def test_corner_blend_non_box_body(self):
        """Cylinder body is rejected."""
        from kerf_cad_core.geom.brep_build import cylinder_to_body
        from kerf_cad_core.geom.brep import Vertex
        body = cylinder_to_body((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), radius=1.0, height=2.0)
        dummy_v = Vertex(np.array([0.0, 0.0, 0.0]))
        res = blend_corner_vertex(body, dummy_v, radius=0.1)
        assert not res["ok"]
        assert "box" in res["reason"].lower() or "axis" in res["reason"].lower()

    def test_corner_blend_shifted_box(self):
        """Corner blend works for a box not at the origin."""
        body = box_to_body((3.0, -1.0, 5.0), 2.0, 3.0, 4.0)
        v = _corner_vertex_at(body, (3, -1, 5), (2, 3, 4), [0, 0, 0])
        assert v is not None
        res = blend_corner_vertex(body, v, radius=0.3)
        assert res["ok"], res.get("reason")
        vr = validate_body(res["body"])
        assert vr["ok"], vr["errors"]

    def test_corner_blend_fillet_faces_cylindrical(self):
        """3 of the fillet faces are cylindrical arc surfaces."""
        from kerf_cad_core.geom.fillet_solid import _CylindricalArcSurface
        body = box_to_body((0.0, 0.0, 0.0), 1.0, 1.0, 1.0)
        v = _corner_vertex_at(body, (0, 0, 0), (1, 1, 1), [0, 0, 0])
        res = blend_corner_vertex(body, v, radius=0.1)
        assert res["ok"], res.get("reason")
        cyl_faces = [
            f for f in res["body"].all_faces()
            if isinstance(f.surface, _CylindricalArcSurface)
        ]
        assert len(cyl_faces) == 3, f"expected 3 cylindrical faces, got {len(cyl_faces)}"
