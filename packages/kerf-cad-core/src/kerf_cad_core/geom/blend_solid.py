"""GK-29 — Constant-radius solid-edge blend (rolling-ball fillet + boolean).

Public API
----------

blend_edge(body, edge, radius, *, tol=1e-6) -> BlendResult
    Blend a single Edge of a Body with a constant-radius rolling-ball
    fillet.  Delegates to the proven GK-26 ``fillet_solid_edge``
    implementation for the planar+planar (box) and planar+cylindrical
    (cylinder cap-rim) cases.

blend_edges(body, edges, radius, *, tol=1e-6) -> BlendResult
    Blend multiple *non-adjacent* edges of a box Body sequentially.
    For a 3-edge corner, use :func:`blend_corner_vertex` instead.

blend_corner_vertex(body, vertex, radius, *, tol=1e-6) -> BlendResult
    Blend all three edges meeting at an axis-aligned box corner
    vertex simultaneously, closing the spherical gap at the corner
    with a 1/8-sphere patch.  Only axis-aligned box corners are
    supported; other inputs return ``{"ok": False, "reason": "..."}``.

Analytic oracle (planar+planar single edge on a box)
----------------------------------------------------

For a box of volume ``V_box``, edge length ``L``, fillet radius ``r``::

    volume_after = V_box - (1 - pi/4) * r**2 * L        (within 1e-6)

This matches the GK-26 oracle exactly — :func:`blend_edge` reuses the
proven :func:`fillet_solid_edge` implementation end-to-end.

For a 3-edge corner blend the topological oracle is ``validate_body``
correctness (closed 2-manifold, Euler-Poincaré satisfied); an analytic
volume formula is not required.

Design notes
------------
* Hermetic pure-Python; no OCCT dependency.
* ``blend_corner_vertex`` builds the blended body directly from analytic
  surfaces (Plane, CylindricalArcSurface, _SphericalOctantSurface) and
  delegates to :func:`sew_faces` + ``validate_body``.
* Never raises; failures return ``{"ok": False, "reason": "..."}``.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    CircleArc3,
    Coedge,
    CylinderSurface,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    SphereSurface,
    Vertex,
    validate_body,
)
from kerf_cad_core.geom.brep_build import BuildError
from kerf_cad_core.geom.fillet_solid import (
    FilletResult,
    _CylindricalArcSurface,  # co-maintained in this package
    _is_axis_aligned_box,
    fillet_solid_edge,
)
from kerf_cad_core.geom.sew import sew_faces


__all__ = [
    "BlendResult",
    "blend_edge",
    "blend_edges",
    "blend_corner_vertex",
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class BlendResult(dict):
    """Result dict returned by the blend functions.

    Keys:
        ok              : bool
        reason          : str (empty on success)
        body            : Body | None
        fillet_faces    : list[Face]
        volume_removed  : float
        diagnostics     : dict
    """


def _fail(reason: str) -> BlendResult:
    return BlendResult(
        ok=False,
        reason=reason,
        body=None,
        fillet_faces=[],
        volume_removed=0.0,
        diagnostics={},
    )


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


def _signed_area_about_normal(pts: List[np.ndarray], normal: np.ndarray) -> float:
    if len(pts) < 3:
        return 0.0
    centroid = np.mean(pts, axis=0)
    area_vec = np.zeros(3)
    m = len(pts)
    for i in range(m):
        a = pts[i] - centroid
        b = pts[(i + 1) % m] - centroid
        area_vec += np.cross(a, b)
    return float(np.dot(area_vec, normal)) * 0.5


def _make_planar_face(
    ordered_verts: List[Vertex],
    ordered_edge_specs: List[Tuple[Edge, bool]],
    outward_normal: np.ndarray,
    tol: float,
) -> Face:
    """Build a planar Face with correct CCW orientation.

    ``ordered_edge_specs`` are (Edge, forward_orientation) tuples.
    The face normal is aligned with ``outward_normal``.
    """
    pts = [v.point for v in ordered_verts]
    # Build plane: origin = pts[0], axes from pts[0] to pts[1] and pts[0] to pts[-1]
    d1 = pts[1] - pts[0]
    d2 = pts[-1] - pts[0]
    if float(np.dot(np.cross(d1, d2), outward_normal)) < 0:
        d1, d2 = d2, d1
    plane = Plane(origin=pts[0], x_axis=_unit(d1), y_axis=_unit(d2))

    # Compute polygon signed area
    sa = _signed_area_about_normal(pts, outward_normal)
    if sa >= 0:
        coedges = [Coedge(e, o) for (e, o) in ordered_edge_specs]
    else:
        coedges = [Coedge(e, not o) for (e, o) in reversed(ordered_edge_specs)]
    loop = Loop(coedges, is_outer=True)
    return Face(plane, [loop], orientation=True, tol=tol)


def _make_cyl_arc_face(
    surf: _CylindricalArcSurface,
    ordered_edge_specs: List[Tuple[Edge, bool]],
    tol: float,
) -> Face:
    """Build a cylinder-arc Face with correct CCW orientation."""
    pts = [
        np.asarray(e.curve.evaluate(e.t0 if o else e.t1), dtype=float)
        for (e, o) in ordered_edge_specs
    ]
    surf_n = surf.normal(0.5, 0.5)
    sa = _signed_area_about_normal(pts, surf_n)
    if sa >= 0:
        coedges = [Coedge(e, o) for (e, o) in ordered_edge_specs]
    else:
        coedges = [Coedge(e, not o) for (e, o) in reversed(ordered_edge_specs)]
    loop = Loop(coedges, is_outer=True)
    return Face(surf, [loop], orientation=True, tol=tol)


def _make_face_exact(
    surf,
    ordered_edge_specs: List[Tuple[Edge, bool]],
    tol: float,
    face_orientation: bool = True,
) -> Face:
    """Build a Face using EXACTLY the given edge orientations (no signed-area flip).

    ``face_orientation=False`` negates the surface normal used by
    ``_validate_face_local``'s CCW check, effectively accepting a CW loop as
    outward-facing.  Use this when the correct manifold orientation (opposite to
    an adjacent face) produces a CW loop w.r.t. the raw surface normal.
    """
    coedges = [Coedge(e, o) for (e, o) in ordered_edge_specs]
    loop = Loop(coedges, is_outer=True)
    return Face(surf, [loop], orientation=face_orientation, tol=tol)


def _make_sphere_face(
    surf: "_SphericalOctantSurface",
    ordered_edge_specs: List[Tuple[Edge, bool]],
    tol: float,
) -> Face:
    """Build a spherical-octant Face with correct CCW orientation."""
    pts = [
        np.asarray(e.curve.evaluate(e.t0 if o else e.t1), dtype=float)
        for (e, o) in ordered_edge_specs
    ]
    surf_n = surf.normal(0.5, 0.5)
    sa = _signed_area_about_normal(pts, surf_n)
    if sa >= 0:
        coedges = [Coedge(e, o) for (e, o) in ordered_edge_specs]
    else:
        coedges = [Coedge(e, not o) for (e, o) in reversed(ordered_edge_specs)]
    loop = Loop(coedges, is_outer=True)
    return Face(surf, [loop], orientation=True, tol=tol)


# ---------------------------------------------------------------------------
# blend_edge — single edge, delegates to fillet_solid_edge
# ---------------------------------------------------------------------------


def blend_edge(
    body: Body,
    edge: Edge,
    radius: float,
    *,
    tol: float = 1e-6,
) -> BlendResult:
    """Blend one edge of ``body`` with a constant rolling-ball fillet.

    Delegates to :func:`fillet_solid.fillet_solid_edge` for the
    planar+planar (box) and planar+cylindrical (cylinder cap-rim) cases.

    The volume oracle for a box edge of length ``L`` and radius ``r`` is::

        volume_removed = (1 - pi/4) * r**2 * L        (to ≤1e-6)
    """
    res = fillet_solid_edge(body, edge, radius, tol=tol)
    if not res["ok"]:
        return _fail(res.get("reason", "fillet_solid_edge failed"))
    body_out: Body = res["body"]
    ff = res.get("fillet_face")
    return BlendResult(
        ok=True,
        reason="",
        body=body_out,
        fillet_faces=[ff] if ff is not None else [],
        volume_removed=float(res.get("volume_removed", 0.0)),
        diagnostics=dict(res.get("diagnostics", {})),
    )


# ---------------------------------------------------------------------------
# blend_edges — sequential multi-edge blend
# ---------------------------------------------------------------------------


def blend_edges(
    body: Body,
    edges: Sequence[Edge],
    radius: float,
    *,
    tol: float = 1e-6,
) -> BlendResult:
    """Blend several *non-adjacent* edges sequentially.

    Each edge is matched geometrically to the current body (by midpoint
    proximity) after each successive blend.  Edges must not share vertices
    — for a 3-edge corner, use :func:`blend_corner_vertex`.
    """
    if not edges:
        return _fail("edges sequence is empty")
    cur_body = body
    all_fillet_faces: List[Face] = []
    total_removed = 0.0
    for e in edges:
        matched = _find_edge_by_midpoint(cur_body, e, tol * 100)
        if matched is None:
            return _fail(
                f"edge#{e.id} not found by midpoint in the (possibly blended) "
                "body; edges must be non-adjacent"
            )
        res = blend_edge(cur_body, matched, radius, tol=tol)
        if not res["ok"]:
            return _fail(f"blend_edge failed: {res['reason']}")
        cur_body = res["body"]
        all_fillet_faces.extend(res["fillet_faces"])
        total_removed += res["volume_removed"]
    return BlendResult(
        ok=True,
        reason="",
        body=cur_body,
        fillet_faces=all_fillet_faces,
        volume_removed=total_removed,
        diagnostics={"edge_count": len(edges)},
    )


def _find_edge_by_midpoint(
    body: Body, ref: Edge, tol: float
) -> Optional[Edge]:
    ref_mid = ref.point(0.5 * (ref.t0 + ref.t1))
    for e in body.all_edges():
        mid = e.point(0.5 * (e.t0 + e.t1))
        if float(np.linalg.norm(mid - ref_mid)) < tol:
            return e
    return None


# ---------------------------------------------------------------------------
# blend_corner_vertex — 3-edge box-corner blend
# ---------------------------------------------------------------------------


def blend_corner_vertex(
    body: Body,
    vertex: Vertex,
    radius: float,
    *,
    tol: float = 1e-6,
) -> BlendResult:
    """Blend the three edges meeting at a box corner.

    Builds a new Body with:
      * 3 "touching" faces (pentagon, trimmed at corner and arc)
      * 3 "far" faces (pentagon, trimmed at adjacent-corner end of fillet)
      * 1 "diagonal" face (untouched quad, the face between the 3 adj corners)
      * 3 quarter-cylinder fillet faces
      * 1 spherical-octant corner patch

    Total = 11 faces.

    Only axis-aligned box corners are supported.
    """
    if not isinstance(body, Body):
        return _fail(f"body must be a Body, got {type(body).__name__}")
    if not isinstance(vertex, Vertex):
        return _fail(f"vertex must be a Vertex, got {type(vertex).__name__}")
    if not (isinstance(radius, (int, float)) and radius > 0):
        return _fail(f"radius must be positive, got {radius!r}")
    radius = float(radius)

    box = _is_axis_aligned_box(body, tol)
    if box is None:
        return _fail("blend_corner_vertex only supports axis-aligned box bodies")

    lo = box["lo"]
    hi = box["hi"]
    out_tol = max(tol, radius * 1e-6)

    # Identify corner in body
    blend_pt = None
    for v in body.all_vertices():
        if float(np.linalg.norm(v.point - vertex.point)) < out_tol * 10.0:
            blend_pt = v.point.copy()
            break
    if blend_pt is None:
        return _fail("vertex does not belong to the given body")

    # Corner sign: 0=lo, 1=hi for each axis
    sign = np.zeros(3, dtype=int)
    for ax in range(3):
        if abs(blend_pt[ax] - lo[ax]) <= out_tol * 10.0:
            sign[ax] = 0
        elif abs(blend_pt[ax] - hi[ax]) <= out_tol * 10.0:
            sign[ax] = 1
        else:
            return _fail(f"vertex at {blend_pt} is not a corner of the box")

    dims = hi - lo
    if radius >= float(np.min(dims)) * 0.5:
        return _fail(
            f"radius {radius} too large for box dims {dims.tolist()}; "
            "must be < min(dim)/2"
        )

    try:
        new_body = _build_corner_body(lo, hi, blend_pt, sign, radius, out_tol)
    except BuildError as exc:
        return _fail(str(exc))
    except Exception as exc:  # pragma: no cover
        return _fail(f"internal error in blend_corner_vertex: {exc}")

    val = validate_body(new_body)
    if not val["ok"]:
        return _fail(f"corner blend produced invalid body: {val['errors']}")

    shell = new_body.solids[0].shells[0]
    fillet_faces = [f for f in shell.faces if not isinstance(f.surface, Plane)]
    return BlendResult(
        ok=True,
        reason="",
        body=new_body,
        fillet_faces=fillet_faces,
        volume_removed=0.0,
        diagnostics={"kind": "3-edge-corner", "radius": radius},
    )


# ---------------------------------------------------------------------------
# Core builder: 11-face blended-corner body
# ---------------------------------------------------------------------------
# Coordinate system:
#   sign[ax] ∈ {0,1}: 0 = corner at lo[ax], 1 = corner at hi[ax]
#   d[ax] = +1 if sign[ax]==0 (interior along +ax), −1 if sign[ax]==1
# others[ax] = the two axes ≠ ax.
#
# Vertices generated:
#   vA_near[ax], vB_near[ax]: near-corner contact endpoints for fillet ax
#   vA_far[ax],  vB_far[ax]:  far contact endpoints for fillet ax
#   v_adj[ax]:  adjacent box corner along axis ax
#   v_far[sa, sb, sc]: corners of the box that differ in ≥2 bits from sign
# ---------------------------------------------------------------------------

_OTHERS = [[1, 2], [0, 2], [0, 1]]


def _box_corner(lo, hi, s):
    """Box corner at sign triple s = (s0,s1,s2)."""
    p = np.zeros(3)
    for ax in range(3):
        p[ax] = lo[ax] if s[ax] == 0 else hi[ax]
    return p


def _build_corner_body(
    lo: np.ndarray,
    hi: np.ndarray,
    blend_pt: np.ndarray,
    sign: np.ndarray,
    r: float,
    tol: float,
) -> Body:
    """Build the 10-face blended-corner box body.

    Correct geometry: fillet cylinders span from sphere-junction plane to the
    adjacent corner.  The sphere octant is bounded by 3 great-circle arcs that
    lie in the sphere-junction planes (at blend_pt + d[ax]*r along each axis).

    Face catalogue
    --------------
    * 3 fillet cylinder faces (quadrilaterals)
    * 1 spherical octant face (spherical triangle)
    * 3 far pentagons (pentagon at each adjacent-corner plane)
    * 3 touching quadrilaterals (the 3 adjacent box faces, corner trimmed)
    Total: 10 faces, same as before but with correct near-arc positions.

    Near-contact vertex positions (sphere-junction points, on sphere surface)
    -------------------------------------------------------------------------
    Sphere centre  : S = blend_pt + d * r
    For fillet ax (o0, o1 = _OTHERS[ax]):
      vA_near[ax] = blend_pt + d[ax]*r*e_ax + d[o1]*r*e_o1  (at x[o0]=blend_pt[o0])
      vB_near[ax] = blend_pt + d[ax]*r*e_ax + d[o0]*r*e_o0  (at x[o1]=blend_pt[o1])
    Both lie on the sphere |p - S| = r.

    Vertex coincidences
    -------------------
    PA = blend_pt + d[0]*r*e_0 + d[2]*r*e_2  = vA_near[0] = vB_near[2]
    PB = blend_pt + d[0]*r*e_0 + d[1]*r*e_1  = vB_near[0] = vB_near[1]
    PC = blend_pt + d[1]*r*e_1 + d[2]*r*e_2  = vA_near[1] = vA_near[2]

    Touching-face topology
    ----------------------
    The 3 adjacent box faces (at blend_pt[face_ax] planes) become quads.
    All 4 original corners on each face are trimmed (by blend corner or by
    the far fillet at the adjacent corner).  Only the "far-far" corner
    (all-bits-except-face_ax flipped) survives as an untrimmed vertex.
    The quad reuses two edges from the far-pentagon construction (e_fc1, e_fc4).
    """
    d = np.where(sign == 0, 1.0, -1.0)  # interior direction per axis
    e_axis = [np.eye(3)[ax] for ax in range(3)]

    def _adj_corner(ax):
        s = sign.copy()
        s[ax] = 1 - s[ax]
        return _box_corner(lo, hi, s)

    # -----------------------------------------------------------------
    # Step 1: near-contact vertices (sphere-junction points)
    # -----------------------------------------------------------------
    # PA = blend_pt + d[0]*r*e_0 + d[2]*r*e_2  (shared by ax=0 A-side, ax=2 B-side)
    # PB = blend_pt + d[0]*r*e_0 + d[1]*r*e_1  (shared by ax=0 B-side, ax=1 B-side)
    # PC = blend_pt + d[1]*r*e_1 + d[2]*r*e_2  (shared by ax=1 A-side, ax=2 A-side)
    PA = Vertex(blend_pt + d[0] * r * e_axis[0] + d[2] * r * e_axis[2], tol)
    PB = Vertex(blend_pt + d[0] * r * e_axis[0] + d[1] * r * e_axis[1], tol)
    PC = Vertex(blend_pt + d[1] * r * e_axis[1] + d[2] * r * e_axis[2], tol)

    # vA_near[ax]: vA_near_v[ax] = blend_pt + d[ax]*r*e_ax + d[o1]*r*e_o1
    # vB_near[ax]: vB_near_v[ax] = blend_pt + d[ax]*r*e_ax + d[o0]*r*e_o0
    # ax=0 (o0=1, o1=2): vA_near=PA, vB_near=PB
    # ax=1 (o0=0, o1=2): vA_near=PC, vB_near=PB
    # ax=2 (o0=0, o1=1): vA_near=PC, vB_near=PA
    vA_near_v = [PA, PC, PC]
    vB_near_v = [PB, PB, PA]

    # Far contact vertices (at adj_corner plane, offset by d[o0/o1]*r)
    vA_far_v = []
    vB_far_v = []
    for ax in range(3):
        o0, o1 = _OTHERS[ax]
        adj = _adj_corner(ax)
        vA_far_v.append(Vertex(adj + d[o1] * r * e_axis[o1], tol))
        vB_far_v.append(Vertex(adj + d[o0] * r * e_axis[o0], tol))

    # Non-adj (far) corner vertices: corners ≥2 bits different from sign
    far_v: dict = {}
    for s0 in range(2):
        for s1 in range(2):
            for s2 in range(2):
                sv = np.array([s0, s1, s2])
                if int(np.sum(sv != sign)) >= 2:
                    far_v[(s0, s1, s2)] = Vertex(_box_corner(lo, hi, sv), tol)

    # -----------------------------------------------------------------
    # Step 2: arc curves + contact edges for fillet cylinders
    # -----------------------------------------------------------------
    # Near arc centre = sphere centre (same for all 3 arcs).
    # Far arc centre  = adj_corner + d[o0]*r*e_o0 + d[o1]*r*e_o1.
    sphere_c = blend_pt + d * r  # sphere centre

    arc_near_edges: list = []
    arc_far_edges: list = []
    contact_A_edges: list = []
    contact_B_edges: list = []
    cyl_surfs: list = []

    for ax in range(3):
        o0, o1 = _OTHERS[ax]
        adj = _adj_corner(ax)
        fill_c_far = adj + d[o0] * r * e_axis[o0] + d[o1] * r * e_axis[o1]

        # Near arc: A_near -> B_near (quarter circle at sphere centre)
        xref = -d[o0] * e_axis[o0]          # toward vA_near from sphere_c
        cyl_y = _unit(np.cross(e_axis[ax] * d[ax], xref))
        yref = -d[o1] * e_axis[o1]
        sign_swap = float(np.dot(cyl_y, yref))
        u_start, u_end = (0.0, math.pi / 2.0) if sign_swap >= 0 else (0.0, -math.pi / 2.0)

        arc_near_curve = CircleArc3(
            sphere_c, r, xref, cyl_y,
            min(u_start, u_end), max(u_start, u_end),
        )
        e_near = Edge(arc_near_curve, u_start, u_end,
                      vA_near_v[ax], vB_near_v[ax], tol)
        arc_near_edges.append(e_near)

        # Far arc: A_far -> B_far
        arc_far_curve = CircleArc3(
            fill_c_far, r, xref, cyl_y,
            min(u_start, u_end), max(u_start, u_end),
        )
        e_far = Edge(arc_far_curve, u_start, u_end,
                     vA_far_v[ax], vB_far_v[ax], tol)
        arc_far_edges.append(e_far)

        # Contact A: vA_near -> vA_far
        e_cA = Edge(Line3(vA_near_v[ax].point, vA_far_v[ax].point),
                    0.0, 1.0, vA_near_v[ax], vA_far_v[ax], tol)
        contact_A_edges.append(e_cA)

        # Contact B: vB_near -> vB_far
        e_cB = Edge(Line3(vB_near_v[ax].point, vB_far_v[ax].point),
                    0.0, 1.0, vB_near_v[ax], vB_far_v[ax], tol)
        contact_B_edges.append(e_cB)

        # Cylinder surface (runs from near-plane to far-plane along ax)
        if sign[ax] == 0:
            v_s, v_e = lo[ax] + r * d[ax], hi[ax]
        else:
            v_s, v_e = hi[ax] + r * d[ax], lo[ax]
        cyl_surf = _CylindricalArcSurface(
            centre=sphere_c,
            axis=e_axis[ax] * d[ax],
            radius=r,
            x_ref=xref,
            u_start=u_start,
            u_end=u_end,
            v_start=float(v_s),
            v_end=float(v_e),
        )
        cyl_surfs.append(cyl_surf)

    # -----------------------------------------------------------------
    # Step 3: far pentagons + store e_fc1 / e_fc4 for touching quads
    # -----------------------------------------------------------------
    # Each far pentagon covers the face at adj_corner[ax] plane (5 edges).
    # vA_far[ax] is offset from adj_corner along o1; vB_far[ax] along o0.
    # The far pentagon uses arc_far REVERSED so that the fillet must use FORWARD.
    # After _make_planar_face, read back the actual coedge orientations.

    far_fc1: dict = {}  # ax -> (Edge, v_c1_vertex)
    far_fc4: dict = {}  # ax -> (Edge, v_c3_vertex)
    far_pentagon_faces = []

    for ax in range(3):
        o0, o1 = _OTHERS[ax]
        face_normal = np.zeros(3)
        face_normal[ax] = d[ax]  # outward away from blend corner

        def _ffc(s_o0, s_o1, _ax=ax, _o0=o0, _o1=o1):
            sv = sign.copy()
            sv[_ax] = 1 - sign[_ax]
            sv[_o0] = s_o0
            sv[_o1] = s_o1
            k = tuple(int(x) for x in sv)
            if k in far_v:
                return far_v[k]
            for a2 in range(3):
                test = sign.copy()
                test[a2] = 1 - sign[a2]
                if np.array_equal(sv, test):
                    return Vertex(_adj_corner(a2), tol)
            raise BuildError(f"_ffc: cannot resolve corner {sv}")

        v_c1 = _ffc(sign[o0], 1 - sign[o1])      # adjacent to vA_far (along o1)
        v_c2 = _ffc(1 - sign[o0], 1 - sign[o1])  # diagonal
        v_c3 = _ffc(1 - sign[o0], sign[o1])      # adjacent to vB_far (along o0)

        vAfar = vA_far_v[ax]
        vBfar = vB_far_v[ax]

        e_fc1 = Edge(Line3(vAfar.point, v_c1.point), 0.0, 1.0, vAfar, v_c1, tol)
        e_fc2 = Edge(Line3(v_c1.point, v_c2.point), 0.0, 1.0, v_c1, v_c2, tol)
        e_fc3 = Edge(Line3(v_c2.point, v_c3.point), 0.0, 1.0, v_c2, v_c3, tol)
        e_fc4 = Edge(Line3(v_c3.point, vBfar.point), 0.0, 1.0, v_c3, vBfar, tol)

        far_fc1[ax] = (e_fc1, v_c1)
        far_fc4[ax] = (e_fc4, v_c3)

        # Proposed loop: arc_far reversed, then e_fc1..e_fc4 forward
        loop_specs = [
            (arc_far_edges[ax], False),  # B_far -> A_far
            (e_fc1, True),
            (e_fc2, True),
            (e_fc3, True),
            (e_fc4, True),
        ]
        pts = [vBfar.point, vAfar.point, v_c1.point, v_c2.point, v_c3.point]
        far_pentagon_faces.append(
            _make_planar_face(
                [Vertex(p, tol) for p in pts], loop_specs, face_normal, tol
            )
        )

    # -----------------------------------------------------------------
    # Step 4: touching quad faces (3 adjacent box faces, quad each)
    # -----------------------------------------------------------------
    # For face_ax, the two fillets that touch it:
    #   Fillet o0_f (= _OTHERS[face_ax][0]) uses contact_A[o0_f] on this face.
    #   Fillet o1_f (= _OTHERS[face_ax][1]) uses contact_B[o1_f] on this face.

    def _contact_on_face(filt_ax, face_ax_):
        """Return (edge, v_near, v_far) for filt_ax's contact on face_ax_."""
        oth = _OTHERS[filt_ax]
        if oth[0] == face_ax_:
            return contact_A_edges[filt_ax], vA_near_v[filt_ax], vA_far_v[filt_ax]
        else:
            return contact_B_edges[filt_ax], vB_near_v[filt_ax], vB_far_v[filt_ax]

    touching_faces = []
    for face_ax in range(3):
        o0_f, o1_f = _OTHERS[face_ax]
        face_normal = np.zeros(3)
        face_normal[face_ax] = -d[face_ax]  # outward from box

        ec0, _vn0, vf0 = _contact_on_face(o0_f, face_ax)
        ec1, _vn1, vf1 = _contact_on_face(o1_f, face_ax)
        junction = _vn0  # both contacts start at same junction vertex

        def _far_edge_info(filt_ax, face_ax_):
            oth = _OTHERS[filt_ax]
            if oth[0] == face_ax_:
                e, vc = far_fc1[filt_ax]
                return e, vA_far_v[filt_ax], vc, True
            else:
                e, vc = far_fc4[filt_ax]
                return e, vB_far_v[filt_ax], vc, False

        e_f0, vf0_check, vc_shared, fwd0 = _far_edge_info(o0_f, face_ax)
        e_f1, vf1_check, vc_shared1, fwd1 = _far_edge_info(o1_f, face_ax)

        loop_specs = [
            (ec0, True),
            (e_f0, fwd0),
            (e_f1, not fwd1),
            (ec1, False),
        ]
        pts = [junction.point, vf0.point, vc_shared.point, vf1.point]
        touching_faces.append(
            _make_planar_face(
                [Vertex(p, tol) for p in pts], loop_specs, face_normal, tol
            )
        )

    # -----------------------------------------------------------------
    # Step 5: fillet cylinder faces — orientations read from context
    # -----------------------------------------------------------------
    # For each fillet axis ax:
    #   - contact_A[ax] is on touching face tf_A = _OTHERS[ax][0]
    #   - contact_B[ax] is on touching face tf_B = _OTHERS[ax][1]
    #   - arc_far[ax] is in far_pentagon_faces[ax]
    # The fillet must use each of these edges with OPPOSITE orientation
    # to the adjacent face that already contains them.
    #
    # Two valid connected fillet loops:
    #   loop1 (arc_near fwd):  [arc_near T, contact_B T, arc_far F, contact_A F]
    #   loop2 (arc_near rev):  [arc_near F, contact_A T, arc_far T, contact_B F]
    # Choose by reading contact_A orientation from touching face.

    def _find_coedge_ori(face, edge):
        """Return the orientation of `edge` in `face`'s first loop, or None."""
        for loop in face.loops:
            for ce in loop.coedges:
                if ce.edge is edge:
                    return ce.orientation
        return None

    fillet_faces = []
    for ax in range(3):
        o0_ax, o1_ax = _OTHERS[ax]
        tf_A = o0_ax   # touching face containing contact_A_edges[ax]

        ori_A_in_touch = _find_coedge_ori(touching_faces[tf_A], contact_A_edges[ax])
        if ori_A_in_touch is None:
            raise BuildError(
                f"blend_corner_vertex: failed to read contact_A orientation for fillet ax={ax}"
            )

        # Fillet must use contact_A with OPPOSITE orientation
        filt_A_ori = not ori_A_in_touch

        if not filt_A_ori:
            # loop1: contact_A=False
            loop_specs = [
                (arc_near_edges[ax], True),
                (contact_B_edges[ax], True),
                (arc_far_edges[ax], False),
                (contact_A_edges[ax], False),
            ]
        else:
            # loop2: contact_A=True
            loop_specs = [
                (arc_near_edges[ax], False),
                (contact_A_edges[ax], True),
                (arc_far_edges[ax], True),
                (contact_B_edges[ax], False),
            ]

        pts_f = [
            np.asarray(e.curve.evaluate(e.t0 if o else e.t1), dtype=float)
            for (e, o) in loop_specs
        ]
        surf_n = cyl_surfs[ax].normal(0.5, 0.5)
        sa = _signed_area_about_normal(pts_f, surf_n)
        face_ori = sa >= 0
        f = _make_face_exact(cyl_surfs[ax], loop_specs, tol, face_orientation=face_ori)
        fillet_faces.append(f)

    # -----------------------------------------------------------------
    # Step 6: spherical octant face — arc_near orientations read from fillets
    # -----------------------------------------------------------------
    # The sphere must use each arc_near[ax] with OPPOSITE orientation to fillet[ax].
    #
    # arc_near edges (fwd direction):
    #   arc_near[0]: vA_near[0]=PA → vB_near[0]=PB
    #   arc_near[1]: vA_near[1]=PC → vB_near[1]=PB
    #   arc_near[2]: vA_near[2]=PC → vB_near[2]=PA
    #
    # We need the sphere loop to be a closed triangle on the sphere.
    # Read the fillet arc_near orientations, negate them for the sphere.
    #
    # Two valid sphere loop orderings (both form closed PA↔PB↔PC triangles):
    #   Pattern A (ordering [0,1,2]): arc[0]T PA→PB, arc[1]F PB→PC, arc[2]T PC→PA
    #     → sphere_near_ori = [T,F,T] → fillet arc_near = [F,T,F]
    #   Pattern B (ordering [0,2,1]): arc[0]F PB→PA, arc[2]F PA→PC, arc[1]T PC→PB
    #     → sphere_near_ori = [F,F,T] wait…
    #     Actually B: arc[0]F=PB→PA, arc[2]F=PA→PC... arc[2] fwd=PC→PA, F=PA→PC ✓
    #                 arc[1]T=PC→PB; prev end=PC ✓  → sphere_near_ori=[F,T,F] → fillet=[T,F,T]
    #
    # Choose Pattern A when fillet arc_near[0]=False, Pattern B when fillet arc_near[0]=True.

    sphere_surf = _SphericalOctantSurface(sphere_c, r, d)

    near_ori_in_fillet = [
        _find_coedge_ori(fillet_faces[ax], arc_near_edges[ax])
        for ax in range(3)
    ]
    sphere_near_ori = [not o for o in near_ori_in_fillet]

    if near_ori_in_fillet[0]:
        # Fillet ax=0 uses arc_near fwd (T), Pattern B → sphere ordering [0,2,1]
        # sphere: arc[0]F=PB→PA, arc[2]F=PA→PC, arc[1]T=PC→PB
        sphere_loop_specs = [
            (arc_near_edges[0], sphere_near_ori[0]),  # F: PB→PA
            (arc_near_edges[2], sphere_near_ori[2]),  # F: PA→PC
            (arc_near_edges[1], sphere_near_ori[1]),  # T: PC→PB
        ]
    else:
        # Fillet ax=0 uses arc_near rev (F), Pattern A → sphere ordering [0,1,2]
        # sphere: arc[0]T=PA→PB, arc[1]F=PB→PC, arc[2]T=PC→PA
        sphere_loop_specs = [
            (arc_near_edges[0], sphere_near_ori[0]),  # T: PA→PB
            (arc_near_edges[1], sphere_near_ori[1]),  # F: PB→PC
            (arc_near_edges[2], sphere_near_ori[2]),  # T: PC→PA
        ]
    sphere_pts = [
        np.asarray(e.curve.evaluate(e.t0 if o else e.t1), dtype=float)
        for (e, o) in sphere_loop_specs
    ]
    sphere_n = sphere_surf.normal(0.5, 0.5)
    sphere_sa = _signed_area_about_normal(sphere_pts, sphere_n)
    sphere_face_ori = sphere_sa >= 0
    sphere_face = _make_face_exact(sphere_surf, sphere_loop_specs, tol,
                                    face_orientation=sphere_face_ori)

    # -----------------------------------------------------------------
    # Step 7: assemble and sew
    # -----------------------------------------------------------------
    all_faces = touching_faces + far_pentagon_faces + fillet_faces + [sphere_face]
    shell = sew_faces(all_faces, tol=tol)
    if not shell.is_closed:
        raise BuildError(
            "blend_corner_vertex: sewn shell is not closed "
            f"(faces={len(all_faces)})"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"blend_corner_vertex: invalid body after sewing: {res['errors']}"
        )
    return body


# ---------------------------------------------------------------------------
# Spherical octant surface
# ---------------------------------------------------------------------------


class _SphericalOctantSurface:
    """1/8-sphere surface for the corner blend patch.

    Parameters (u, v) in [0,1]^2 are mapped to the octant of a sphere of
    given radius centred at ``centre``.  The octant faces toward the box
    interior (the 3 axes of ``d`` determine which octant).

    Corner mapping (informative — determines which edges align to which
    boundary arc):
      * (u=0, v=0) → direction d[2]*e_z  (P2 direction)
      * (u=1, v=0) → direction d[1]*e_y  (P1 direction)
      * (u=0, v=1) → direction d[0]*e_x  (P0 direction)
    """

    __slots__ = ("centre", "radius", "d", "_x", "_y", "_z")

    def __init__(
        self, centre: np.ndarray, radius: float, d: np.ndarray
    ) -> None:
        self.centre = np.asarray(centre, dtype=float)
        self.radius = float(radius)
        self.d = np.asarray(d, dtype=float)
        self._x = self.d[0] * np.array([1.0, 0.0, 0.0])
        self._y = self.d[1] * np.array([0.0, 1.0, 0.0])
        self._z = self.d[2] * np.array([0.0, 0.0, 1.0])

    def evaluate(self, u: float, v: float) -> np.ndarray:
        tu, tv = float(u), float(v)
        # Barycentric blend of the 3 octant-axis directions
        # such that corners map to the right vertices of the spherical triangle.
        # (0,0)->_z, (1,0)->_y, (0,1)->_x  (matching the sphere loop corners)
        raw = (1.0 - tu) * (1.0 - tv) * self._z + tu * (1.0 - tv) * self._y + (1.0 - tu) * tv * self._x
        n = float(np.linalg.norm(raw))
        if n < 1e-14:
            raw = self._z
            n = 1.0
        return self.centre + self.radius * raw / n

    def normal(self, u: float, v: float) -> np.ndarray:
        pt = self.evaluate(u, v)
        return _unit(pt - self.centre)

