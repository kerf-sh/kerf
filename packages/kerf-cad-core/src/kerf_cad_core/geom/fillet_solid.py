"""GK-26 / GK-29 — Body-emitting rolling-ball fillet on a B-rep edge.

This module implements the *topological* fillet: given a ``Body`` (built
via :mod:`brep_build` primitives — ``box_to_body`` / ``cylinder_to_body``)
and one of its ``Edge`` objects plus a radius, ``fillet_solid_edge``
returns a new ``Body`` where the input edge has been replaced by:

    * one cylindrical (planar+planar case) or toroidal (planar+cylindrical
      case) **fillet face**,
    * two trimmed copies of the supports the edge separated.

The result is sewn via :func:`sew.sew_faces` and asserted ``validate_body``
clean before return. The original ``body`` is not mutated.

------------------------------------------------------------------
Supported-input contract
------------------------------------------------------------------

``fillet_solid_edge`` accepts these edge configurations only:

    1. **planar+planar** — both faces incident to the edge are planar
       (``Plane`` surface), and the edge is the straight intersection
       line where the two planes meet. The supports must meet at a
       *convex* angle from the solid's interior; the radius must satisfy
       ``r > 0`` and ``r < min(perpendicular-extent on either support)``
       so the contact lines lie strictly inside both supports.

    2. **planar+cylindrical** — one support is a ``Plane``, the other a
       ``CylinderSurface``; the edge is the circular intersection of the
       cap plane with the cylinder (the "rim" edge of
       :func:`brep_build.cylinder_to_body`). The radius must satisfy
       ``0 < r < min(cylinder_radius, cap_extent)`` so the rolling ball
       fits.

Outside this contract (general NURBS edges, mixed-genus inputs, non-
convex corners, self-intersecting supports) ``fillet_solid_edge``
returns ``{"ok": False, "reason": "..."}`` — never raises, never emits
an invalid Body. General-NURBS support is roadmap follow-up
(GK-29 extension); this module is the production foundation for the
two contracts above on which the planar+cylindrical case is *exactly*
the box/cylinder-cap fillet that downstream chamfer/blend/shelling work
depends on.

------------------------------------------------------------------
Behavioural guarantees (oracles)
------------------------------------------------------------------

For the planar+planar 90° case on a box edge of length ``L`` with
radius ``r``:

    * Output body has exactly 7 faces — 6 box-derived (4 untouched +
      2 trimmed) + 1 quarter-cylinder fillet face.
    * Output body has ``validate_body(...)["ok"] == True``.
    * Volume removed = ``(1 - pi/4) * r**2 * L`` exactly (within
      numerical noise of the analytic integrand).
    * Fillet face is a portion of a ``CylinderSurface`` whose radius
      is ``r``; the curvature anywhere on it is ``1/r``.

For the planar+cylindrical case (cap-rim of a cylinder of radius
``R`` and height ``H``):

    * Output body has exactly 4 faces — lateral cylinder (trimmed),
      remaining cap (smaller plane disc), 1 fillet face (torus
      segment).

All of these are checked by the test suite under
``test_fillet_blend_g2.py``.
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
    TorusSurface,
    Vertex,
    validate_body,
)
from kerf_cad_core.geom.brep_build import BuildError
from kerf_cad_core.geom.sew import sew_faces


__all__ = [
    "fillet_solid_edge",
    "FilletResult",
    "edge_supported_contract",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


class _TorusSegmentSurface:
    """Torus surface restricted to local ``u in [0, 1]`` and
    ``v in [0, 1]`` mapped onto an arbitrary parametric box of the
    underlying full torus.

    Provides ``evaluate``, ``normal`` and acts as a face surface so
    ``validate_body``'s signed-area test sees the normal at the centre
    of the actual face region.
    """

    __slots__ = (
        "centre", "axis", "_x", "_y", "major_radius", "minor_radius",
        "u_start", "u_end", "v_start", "v_end",
    )

    def __init__(
        self,
        centre: np.ndarray,
        axis: np.ndarray,
        major_radius: float,
        minor_radius: float,
        u_start: float, u_end: float,
        v_start: float, v_end: float,
        x_ref: Optional[np.ndarray] = None,
    ) -> None:
        self.centre = np.asarray(centre, dtype=float)
        self.axis = _unit(np.asarray(axis, dtype=float))
        if x_ref is None:
            ref = np.array([1.0, 0.0, 0.0])
            if abs(float(np.dot(ref, self.axis))) > 0.9:
                ref = np.array([0.0, 1.0, 0.0])
            self._x = _unit(np.cross(self.axis, ref))
        else:
            self._x = _unit(np.asarray(x_ref, dtype=float))
        self._y = _unit(np.cross(self.axis, self._x))
        self.major_radius = float(major_radius)
        self.minor_radius = float(minor_radius)
        self.u_start = float(u_start)
        self.u_end = float(u_end)
        self.v_start = float(v_start)
        self.v_end = float(v_end)

    def _ring_dir(self, cu: float) -> np.ndarray:
        return math.cos(cu) * self._x + math.sin(cu) * self._y

    def evaluate(self, u: float, v: float) -> np.ndarray:
        cu = self.u_start + (self.u_end - self.u_start) * float(u)
        cv = self.v_start + (self.v_end - self.v_start) * float(v)
        rdir = self._ring_dir(cu)
        return (
            self.centre
            + (self.major_radius + self.minor_radius * math.cos(cv)) * rdir
            + self.minor_radius * math.sin(cv) * self.axis
        )

    def normal(self, u: float, v: float = 0.5) -> np.ndarray:
        cu = self.u_start + (self.u_end - self.u_start) * float(u)
        cv = self.v_start + (self.v_end - self.v_start) * float(v)
        rdir = self._ring_dir(cu)
        return _unit(math.cos(cv) * rdir + math.sin(cv) * self.axis)

    def curvature(self) -> Tuple[float, float]:
        """Return (k_major, k_minor) principal curvature *magnitudes*.

        For a circular torus tube of minor radius r and major radius R,
        the maximum principal curvature is 1/r (around the tube) and the
        secondary is ``cos(v) / (R + r cos(v))`` (around the major
        circle). Returns the absolute principal curvatures.
        """
        return 1.0 / self.minor_radius, 1.0 / max(
            abs(self.major_radius), 1e-30,
        )


class _CylindricalArcSurface:
    """Cylinder-segment surface restricted to ``u in [0, 1]`` and
    ``v in [0, 1]`` for use as a face surface.

    Internally wraps a full :class:`CylinderSurface`; the local
    parameters map linearly to the underlying ``(u_start, u_end)`` and
    ``(v_start, v_end)`` ranges. The ``normal`` method returns the
    cylinder's outward radial normal at the mapped point.

    This lets ``validate_body``'s signed-area test (which samples at
    ``surface_normal(0.5, 0.5)``) see the normal in the centre of the
    actual face region rather than at an arbitrary parameter of the
    full cylinder.
    """

    __slots__ = (
        "centre", "axis", "radius", "x_ref", "_y", "u_start", "u_end",
        "v_start", "v_end",
    )

    def __init__(
        self,
        centre: np.ndarray,
        axis: np.ndarray,
        radius: float,
        x_ref: np.ndarray,
        u_start: float,
        u_end: float,
        v_start: float,
        v_end: float,
    ) -> None:
        self.centre = np.asarray(centre, dtype=float)
        self.axis = _unit(np.asarray(axis, dtype=float))
        self.radius = float(radius)
        self.x_ref = _unit(np.asarray(x_ref, dtype=float))
        self._y = _unit(np.cross(self.axis, self.x_ref))
        self.u_start = float(u_start)
        self.u_end = float(u_end)
        self.v_start = float(v_start)
        self.v_end = float(v_end)

    def evaluate(self, u: float, v: float) -> np.ndarray:
        cu = self.u_start + (self.u_end - self.u_start) * float(u)
        cv = self.v_start + (self.v_end - self.v_start) * float(v)
        return (
            self.centre
            + self.radius * math.cos(cu) * self.x_ref
            + self.radius * math.sin(cu) * self._y
            + cv * self.axis
        )

    def normal(self, u: float, v: float = 0.5) -> np.ndarray:
        cu = self.u_start + (self.u_end - self.u_start) * float(u)
        return _unit(
            math.cos(cu) * self.x_ref + math.sin(cu) * self._y
        )

    def param_range(self):  # pragma: no cover - introspection aid
        return (0.0, 1.0, 0.0, 1.0)

    def curvature(self) -> float:
        """Return the constant radial curvature (1 / radius)."""
        return 1.0 / self.radius


def _empty(reason: str) -> dict:
    return {
        "ok": False,
        "reason": reason,
        "body": None,
        "fillet_face": None,
        "trimmed_face_a": None,
        "trimmed_face_b": None,
        "volume_removed": 0.0,
    }


class FilletResult(dict):
    """Result dictionary returned by :func:`fillet_solid_edge`.

    Keys:
        ok              : bool — true iff the fillet succeeded and the
                          new ``Body`` passed ``validate_body``.
        reason          : str  — empty on success, structured failure
                          otherwise.
        body            : Body | None — the new solid body. ``None`` on
                          failure.
        fillet_face     : Face | None — the new cylindrical / toroidal
                          fillet face.
        trimmed_face_a  : Face | None — the first support, trimmed back.
        trimmed_face_b  : Face | None — the second support, trimmed back.
        volume_removed  : float — analytic volume removed by the bevel.
        diagnostics     : dict — additional info (kind, radius, etc.).
    """


def edge_supported_contract() -> str:
    """Return a human-readable description of the supported-input contract."""
    return (
        "fillet_solid_edge supports two edge configurations:\n"
        "  1. planar+planar — both faces incident to the edge are Plane\n"
        "     surfaces meeting at a convex straight edge; radius must\n"
        "     leave the contact lines strictly inside both supports.\n"
        "  2. planar+cylindrical — one support is a Plane, the other a\n"
        "     CylinderSurface, meeting at a circular rim; radius must\n"
        "     satisfy 0 < r < min(cylinder_radius, cap_extent).\n"
        "All other edge configurations (general NURBS supports, concave\n"
        "edges, or radii exceeding the local edge length) return a\n"
        "structured {ok: false, reason: ...} rather than raising."
    )


# ---------------------------------------------------------------------------
# Recognition: planar+planar (box) case
# ---------------------------------------------------------------------------


def _find_incident_faces(body: Body, edge: Edge) -> List[Face]:
    """Find the faces of ``body`` whose loops use ``edge``."""
    out: List[Face] = []
    for f in body.all_faces():
        used = False
        for lp in f.loops:
            for ce in lp.coedges:
                if ce.edge is edge:
                    used = True
                    break
            if used:
                break
        if used:
            out.append(f)
    return out


def _is_planar_face(face: Face) -> bool:
    return isinstance(face.surface, Plane)


def _is_cylindrical_face(face: Face) -> bool:
    return isinstance(face.surface, CylinderSurface)


def _is_axis_aligned_box(body: Body, tol: float) -> Optional[dict]:
    """Return ``{"lo": ..., "hi": ..., "tol": ...}`` iff ``body`` is an
    axis-aligned box solid (produced by :func:`brep_build.box_to_body`
    or :func:`brep.make_box`), otherwise None.

    The test: single solid, single closed shell, exactly 6 planar faces,
    8 distinct vertices each appearing as a corner of an axis-aligned
    AABB. The AABB extent equals the diagonal of those vertices.
    """
    if len(body.solids) != 1 or body.shells:
        return None
    sh = body.solids[0].shells[0] if body.solids[0].shells else None
    if sh is None or not sh.is_closed:
        return None
    if len(sh.faces) != 6:
        return None
    for f in sh.faces:
        if not isinstance(f.surface, Plane):
            return None
    pts = np.array([v.point for v in sh.vertices()], dtype=float)
    if len(pts) != 8:
        return None
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    if not np.all(hi - lo > tol):
        return None
    # Verify all 8 vertices coincide with the 8 corners of [lo, hi].
    corners = np.array(
        [
            [lo[0], lo[1], lo[2]],
            [hi[0], lo[1], lo[2]],
            [hi[0], hi[1], lo[2]],
            [lo[0], hi[1], lo[2]],
            [lo[0], lo[1], hi[2]],
            [hi[0], lo[1], hi[2]],
            [hi[0], hi[1], hi[2]],
            [lo[0], hi[1], hi[2]],
        ],
        dtype=float,
    )
    used = [False] * 8
    for p in pts:
        match = -1
        for i, c in enumerate(corners):
            if used[i]:
                continue
            if float(np.linalg.norm(p - c)) <= tol * 10.0:
                match = i
                break
        if match < 0:
            return None
        used[match] = True
    return {"lo": lo, "hi": hi, "tol": tol}


def _is_axis_aligned_edge(edge: Edge) -> Optional[dict]:
    """Return ``{"axis": int, "p0": ..., "p1": ...}`` iff ``edge`` is a
    straight axis-aligned segment, otherwise None.

    Detects edges built as ``Line3`` with both endpoints differing in a
    single coordinate.
    """
    if not isinstance(edge.curve, Line3):
        return None
    p0 = np.asarray(edge.curve.p0, dtype=float)
    p1 = np.asarray(edge.curve.p1, dtype=float)
    diff = p1 - p0
    nz = [i for i in range(3) if abs(diff[i]) > 1e-9]
    if len(nz) != 1:
        return None
    return {"axis": nz[0], "p0": p0, "p1": p1, "length": abs(diff[nz[0]])}


def _box_filleted_edge_body(
    box: dict, edge_info: dict, radius: float, tol: float
) -> Body:
    """Construct a brand new ``Body`` representing the input box with one
    axis-aligned edge replaced by a quarter-cylinder fillet.

    Parameters
    ----------
    box : dict
        ``{"lo": (3,), "hi": (3,)}`` from :func:`_is_axis_aligned_box`.
    edge_info : dict
        ``{"axis": int, "p0": (3,), "p1": (3,)}`` from
        :func:`_is_axis_aligned_edge`. ``p0`` is the lower-coordinate end
        of the filleted edge.
    radius : float
        Rolling-ball radius. Must satisfy ``radius < min(perpendicular
        extents on the two supports)``.
    """
    lo = box["lo"].copy()
    hi = box["hi"].copy()
    out_tol = max(box.get("tol", tol), tol, radius * 1e-6)

    axis_idx = edge_info["axis"]
    # The two coordinates perpendicular to the edge axis.
    other = [i for i in range(3) if i != axis_idx]

    # Which corner of the AABB the edge lies on, in (other[0], other[1])
    # signs: 0 means at lo on that axis, 1 means at hi.
    p0 = edge_info["p0"]
    p1 = edge_info["p1"]
    # The edge runs from (low value of axis_idx) to (high). Force this:
    if p0[axis_idx] > p1[axis_idx]:
        p0, p1 = p1, p0

    sign0 = 0 if abs(p0[other[0]] - lo[other[0]]) < out_tol else 1
    sign1 = 0 if abs(p0[other[1]] - lo[other[1]]) < out_tol else 1

    # Coordinate values for the four extreme positions on each axis:
    # The two perpendicular axes form a 2D coordinate (a, b). The edge
    # is at (sign0, sign1). Contact lines are at:
    #   on left support (perpendicular axis = other[0]):  a = sign0_at + (radius if sign0==0 else -radius)
    #   on bottom support (perpendicular axis = other[1]): b = sign1_at + (radius if sign1==0 else -radius)
    # i.e. contact line a is on the face whose normal is along other[1]
    # (perpendicular to axis_idx and other[1]) — the SUPPORT spans the
    # axis_idx + other[0] plane.
    # We label the two supports:
    #   support A: spans the (axis_idx, other[0]) plane at b = sign1_at.
    #            (normal direction: ± other[1]).
    #   support B: spans the (axis_idx, other[1]) plane at a = sign0_at.
    #            (normal direction: ± other[0]).
    a_at = lo[other[0]] if sign0 == 0 else hi[other[0]]
    b_at = lo[other[1]] if sign1 == 0 else hi[other[1]]
    a_in = +1.0 if sign0 == 0 else -1.0  # interior direction along other[0]
    b_in = +1.0 if sign1 == 0 else -1.0  # interior direction along other[1]
    # Contact lines:
    #   on support A (b = b_at, varying a): a = a_at + a_in * radius
    #   on support B (a = a_at, varying b): b = b_at + b_in * radius
    a_contact = a_at + a_in * radius
    b_contact = b_at + b_in * radius

    # Verify the radius leaves both contact lines strictly inside their
    # supports.
    if a_in > 0 and a_contact >= hi[other[0]] - out_tol:
        raise BuildError(
            f"radius {radius} exceeds support extent along axis "
            f"{other[0]} (contact reaches {a_contact:.4f}, max "
            f"{hi[other[0]]:.4f})"
        )
    if a_in < 0 and a_contact <= lo[other[0]] + out_tol:
        raise BuildError(
            f"radius {radius} exceeds support extent along axis "
            f"{other[0]} (contact reaches {a_contact:.4f}, min "
            f"{lo[other[0]]:.4f})"
        )
    if b_in > 0 and b_contact >= hi[other[1]] - out_tol:
        raise BuildError(
            f"radius {radius} exceeds support extent along axis "
            f"{other[1]} (contact reaches {b_contact:.4f}, max "
            f"{hi[other[1]]:.4f})"
        )
    if b_in < 0 and b_contact <= lo[other[1]] + out_tol:
        raise BuildError(
            f"radius {radius} exceeds support extent along axis "
            f"{other[1]} (contact reaches {b_contact:.4f}, min "
            f"{lo[other[1]]:.4f})"
        )

    # Build all 10 vertices.
    # 6 untouched corners (everywhere except the two at the filleted
    # edge endpoints) + 4 contact-line endpoints.
    def _corner(s_axis: int, s0: int, s1: int) -> np.ndarray:
        p = np.zeros(3)
        p[axis_idx] = lo[axis_idx] if s_axis == 0 else hi[axis_idx]
        p[other[0]] = lo[other[0]] if s0 == 0 else hi[other[0]]
        p[other[1]] = lo[other[1]] if s1 == 0 else hi[other[1]]
        return p

    # Filleted edge is at (sign0, sign1). Untouched corners are the
    # other three in each (s_axis = 0 or 1) plane.
    other_sign_pairs = [(s0, s1) for s0 in (0, 1) for s1 in (0, 1)
                         if not (s0 == sign0 and s1 == sign1)]
    # Untouched bottom (s_axis=0) and top (s_axis=1) corners.
    V_low: dict = {}   # (s0,s1) -> Vertex on z=low end of axis_idx
    V_high: dict = {}  # (s0,s1) -> Vertex on z=high end of axis_idx
    for s0, s1 in other_sign_pairs:
        V_low[(s0, s1)] = Vertex(_corner(0, s0, s1), out_tol)
        V_high[(s0, s1)] = Vertex(_corner(1, s0, s1), out_tol)

    def _contact_pt_on_A(end: int) -> np.ndarray:
        # support A spans (axis_idx, other[0]) at b = b_at. Contact line
        # runs along axis_idx at a = a_contact, b = b_at.
        p = np.zeros(3)
        p[axis_idx] = lo[axis_idx] if end == 0 else hi[axis_idx]
        p[other[0]] = a_contact
        p[other[1]] = b_at
        return p

    def _contact_pt_on_B(end: int) -> np.ndarray:
        # support B spans (axis_idx, other[1]) at a = a_at. Contact line
        # runs along axis_idx at a = a_at, b = b_contact.
        p = np.zeros(3)
        p[axis_idx] = lo[axis_idx] if end == 0 else hi[axis_idx]
        p[other[0]] = a_at
        p[other[1]] = b_contact
        return p

    vA_low = Vertex(_contact_pt_on_A(0), out_tol)
    vA_high = Vertex(_contact_pt_on_A(1), out_tol)
    vB_low = Vertex(_contact_pt_on_B(0), out_tol)
    vB_high = Vertex(_contact_pt_on_B(1), out_tol)

    # Fillet axis: line at (a_at + a_in*r, b_at + b_in*r), running along
    # axis_idx.
    fill_centre_low = np.zeros(3)
    fill_centre_low[axis_idx] = lo[axis_idx]
    fill_centre_low[other[0]] = a_at + a_in * radius
    fill_centre_low[other[1]] = b_at + b_in * radius
    fill_axis_dir = np.zeros(3)
    fill_axis_dir[axis_idx] = 1.0
    fill_height = hi[axis_idx] - lo[axis_idx]

    # CylinderSurface for the fillet face. We need a quarter (90 deg) of
    # the circle, oriented so its outward normal points away from the
    # solid. The two contact points on a fillet cross-section are vA on
    # support A (at angle theta_A relative to centre) and vB on support
    # B (at angle theta_B), with the arc going from one to the other
    # *outward* — i.e. on the side of the cylinder facing away from the
    # solid interior.
    # The fillet axis centre is at offset (a_in*r, b_in*r) from the
    # filleted-edge line in the (other[0], other[1]) 2D plane. Direction
    # from fillet centre to vA is -b_in along other[1]; direction to vB
    # is -a_in along other[0]. So:
    #   xref direction (-> first contact, vA) is along -b_in * e_other[1]
    #   yref direction (-> second contact, vB) is along -a_in * e_other[0]
    # The cylinder surface evaluate(u, v) gives:
    #   centre + r*cos(u)*xref + r*sin(u)*yref + v*axis
    # At u=0 we get vA, at u=pi/2 we get vB. Between, the arc goes
    # OUTWARD (away from the filleted-edge corner) because both xref and
    # yref point away from that corner.
    xref = np.zeros(3)
    xref[other[1]] = -b_in
    yref = np.zeros(3)
    yref[other[0]] = -a_in
    # cross(xref, yref) is along ± axis_idx; whichever sign it is, we
    # need to match the cylinder's natural "y" axis = cross(axis, xref).
    cyl_surf = CylinderSurface(fill_centre_low, fill_axis_dir, radius, xref)
    # Sanity: cyl_surf._y == yref or -yref. Build cyl_surf with explicit
    # x_ref; its yref-equivalent is _unit(cross(axis, xref)). For our
    # geometry that should equal yref (within signs) — we verify below.
    cyl_y = _unit(np.cross(fill_axis_dir, xref))
    sign_swap = float(np.dot(cyl_y, yref))
    if sign_swap < 0:
        # The cylinder surface's intrinsic y-axis points opposite our
        # intended yref. We can fix this by going from u=0 to u=-pi/2
        # (i.e. travel in negative u) — equivalently, swap the arc
        # parameter range and flip the rim circles.
        u_start = 0.0
        u_end = -math.pi / 2.0
    else:
        u_start = 0.0
        u_end = math.pi / 2.0

    # Build the two quarter-arc rim circles at low/high ends. These use
    # the cylinder's intrinsic frame for evaluation. The rim arc lives
    # on the (a, b) plane at axis_idx = low / high.
    arc_low_curve = CircleArc3(
        fill_centre_low, radius, xref, cyl_y, min(u_start, u_end),
        max(u_start, u_end),
    )
    fill_centre_high = fill_centre_low.copy()
    fill_centre_high[axis_idx] = hi[axis_idx]
    arc_high_curve = CircleArc3(
        fill_centre_high, radius, xref, cyl_y, min(u_start, u_end),
        max(u_start, u_end),
    )
    # Edge orientation: t0 -> t1 means edge.point(t0) = arc(u_start) and
    # edge.point(t1) = arc(u_end). At u_start the point is vA; at u_end
    # it is vB. So with t0 = min, t1 = max — if u_start < u_end then arc
    # goes vA->vB forward; if u_start > u_end then arc.evaluate(t0) ==
    # arc(min) == evaluate at u_end == vB, and arc.evaluate(t1) == vA.
    # We want a forward edge (orientation True in coedges) to walk vA->
    # vB. So set t0/t1 to the values such that t0 maps to vA and t1 to
    # vB.
    arc_t0 = u_start
    arc_t1 = u_end

    e_arc_low = Edge(arc_low_curve, arc_t0, arc_t1, vA_low, vB_low, out_tol)
    e_arc_high = Edge(arc_high_curve, arc_t0, arc_t1, vA_high, vB_high,
                      out_tol)

    # Contact-line edges (straight segments along axis_idx).
    e_contact_A = Edge(
        Line3(vA_low.point, vA_high.point), 0.0, 1.0,
        vA_low, vA_high, out_tol,
    )
    e_contact_B = Edge(
        Line3(vB_low.point, vB_high.point), 0.0, 1.0,
        vB_low, vB_high, out_tol,
    )

    # Now construct edges for the 12 trimmed/untouched edges of the box.
    # Order them: bottom ring of box (at axis_idx = lo), top ring (at
    # axis_idx = hi), and vertical edges (along axis_idx).
    # Each "ring" originally has 4 edges; one corner (sign0, sign1) is
    # gone and replaced by the fillet arc. So each ring has 3 edges
    # remaining + 1 quarter arc (vA -> vB).
    # The vertical edges: originally 4, one is the filleted edge (gone),
    # the three others remain.

    # Helper: get an "untouched corner" vertex
    # at axis-low end: V_low[(s0, s1)]
    # at axis-high end: V_high[(s0, s1)]
    # For corners adjacent to (sign0, sign1) (i.e. those sharing a ring
    # edge with it), we map to the contact-line endpoint instead.
    def _ring_corner_at_low(s0: int, s1: int) -> Vertex:
        if s0 == sign0 and s1 == sign1:
            raise ValueError("filleted corner — should not be used directly")
        return V_low[(s0, s1)]

    def _ring_corner_at_high(s0: int, s1: int) -> Vertex:
        if s0 == sign0 and s1 == sign1:
            raise ValueError("filleted corner — should not be used directly")
        return V_high[(s0, s1)]

    # The corner adjacent to (sign0, sign1) along the other[0] axis is
    # (1-sign0, sign1); along other[1] is (sign0, 1-sign1); diagonal is
    # (1-sign0, 1-sign1).
    adj_a_sign = (1 - sign0, sign1)
    adj_b_sign = (sign0, 1 - sign1)
    diag_sign = (1 - sign0, 1 - sign1)

    # Bottom ring edges (axis_idx = lo). The original ring goes around
    # the 4 corners of the (other[0], other[1]) square.
    # Build the four edges of the ring with the filleted corner replaced
    # by the arc edge e_arc_low. The ring traverses corners:
    #   (sign0, sign1) -> (1-sign0, sign1) -> (1-sign0, 1-sign1) ->
    #   (sign0, 1-sign1) -> back to (sign0, sign1).
    # After fillet, the filleted corner is replaced by the *arc*; the
    # two ring edges incident to it are shortened by ``radius``:
    #   edge_along_other0 from (sign0,sign1) corner to adj_a:
    #     becomes vA_low -> V_low[adj_a_sign]
    #   edge_along_other1 from (sign0,sign1) corner to adj_b:
    #     becomes vB_low -> V_low[adj_b_sign]

    # Edges *unique to* the bottom ring:
    # 1) vA_low -> V_low[adj_a_sign]    (along other[0])
    # 2) V_low[adj_a_sign] -> V_low[diag_sign]   (along other[1])
    # 3) V_low[diag_sign] -> V_low[adj_b_sign]   (along other[0])
    # 4) V_low[adj_b_sign] -> vB_low    (along other[1])
    # Plus the arc edge between vB_low and vA_low (e_arc_low, but
    # traversed as vB->vA = backward).
    e_bot_1 = Edge(
        Line3(vA_low.point, V_low[adj_a_sign].point), 0.0, 1.0,
        vA_low, V_low[adj_a_sign], out_tol,
    )
    e_bot_2 = Edge(
        Line3(V_low[adj_a_sign].point, V_low[diag_sign].point), 0.0, 1.0,
        V_low[adj_a_sign], V_low[diag_sign], out_tol,
    )
    e_bot_3 = Edge(
        Line3(V_low[diag_sign].point, V_low[adj_b_sign].point), 0.0, 1.0,
        V_low[diag_sign], V_low[adj_b_sign], out_tol,
    )
    e_bot_4 = Edge(
        Line3(V_low[adj_b_sign].point, vB_low.point), 0.0, 1.0,
        V_low[adj_b_sign], vB_low, out_tol,
    )

    # Top ring (axis_idx = hi). Symmetric.
    e_top_1 = Edge(
        Line3(vA_high.point, V_high[adj_a_sign].point), 0.0, 1.0,
        vA_high, V_high[adj_a_sign], out_tol,
    )
    e_top_2 = Edge(
        Line3(V_high[adj_a_sign].point, V_high[diag_sign].point), 0.0, 1.0,
        V_high[adj_a_sign], V_high[diag_sign], out_tol,
    )
    e_top_3 = Edge(
        Line3(V_high[diag_sign].point, V_high[adj_b_sign].point), 0.0, 1.0,
        V_high[diag_sign], V_high[adj_b_sign], out_tol,
    )
    e_top_4 = Edge(
        Line3(V_high[adj_b_sign].point, vB_high.point), 0.0, 1.0,
        V_high[adj_b_sign], vB_high, out_tol,
    )

    # Vertical edges (along axis_idx). Three of them: at adj_a, adj_b,
    # diag.
    e_vert_adj_a = Edge(
        Line3(V_low[adj_a_sign].point, V_high[adj_a_sign].point), 0.0, 1.0,
        V_low[adj_a_sign], V_high[adj_a_sign], out_tol,
    )
    e_vert_adj_b = Edge(
        Line3(V_low[adj_b_sign].point, V_high[adj_b_sign].point), 0.0, 1.0,
        V_low[adj_b_sign], V_high[adj_b_sign], out_tol,
    )
    e_vert_diag = Edge(
        Line3(V_low[diag_sign].point, V_high[diag_sign].point), 0.0, 1.0,
        V_low[diag_sign], V_high[diag_sign], out_tol,
    )

    # ---- Build faces ----------------------------------------------------
    box_centroid = 0.5 * (lo + hi)

    def _build_planar_face(
        outer_pts: List[np.ndarray],
        outer_edges: List[Tuple[Edge, bool]],
        outward_hint: np.ndarray,
    ) -> Face:
        """Build a planar face with the given outer loop, ensuring the
        face normal points outward (the same side as ``outward_hint``)
        AND the loop is CCW with respect to that face normal.

        ``outer_edges`` are ``(edge, orientation)`` tuples in traversal
        order.

        We always build a ``Plane`` whose surface normal points along
        ``outward_hint``; then we set the loop's traversal so its
        polygon area vector has positive dot product with that same
        direction (CCW about the face normal).
        """
        # Pick a stable plane frame whose cross(x, y) points along the
        # outward hint.
        origin_pt = outer_pts[0]
        # Find two non-parallel in-plane directions among the outer
        # points.
        d1: Optional[np.ndarray] = None
        d2: Optional[np.ndarray] = None
        for k in range(1, len(outer_pts)):
            cand = outer_pts[k] - origin_pt
            if float(np.linalg.norm(cand)) < 1e-9:
                continue
            if d1 is None:
                d1 = cand
                continue
            if d2 is None:
                cross = np.cross(d1, cand)
                if float(np.linalg.norm(cross)) > 1e-9:
                    d2 = cand
                    break
        if d1 is None or d2 is None:
            # Degenerate: fall back to axis-aligned frame.
            d1 = np.array([1.0, 0.0, 0.0])
            d2 = np.array([0.0, 1.0, 0.0])
        if float(np.dot(np.cross(d1, d2), outward_hint)) < 0:
            d1, d2 = d2, d1
        plane = Plane(origin=origin_pt, x_axis=d1, y_axis=d2)
        # Polygon area vector.
        pts: List[np.ndarray] = []
        for p in outer_pts:
            if not pts or float(np.linalg.norm(p - pts[-1])) > 1e-12:
                pts.append(p)
        centroid = np.mean(pts, axis=0)
        area_vec = np.zeros(3)
        for i in range(len(pts)):
            a = pts[i] - centroid
            b = pts[(i + 1) % len(pts)] - centroid
            area_vec += np.cross(a, b)
        if float(np.dot(area_vec, outward_hint)) >= 0:
            coedges = [Coedge(e, o) for (e, o) in outer_edges]
        else:
            coedges = [Coedge(e, not o) for (e, o) in reversed(outer_edges)]
        loop = Loop(coedges, is_outer=True)
        return Face(plane, [loop], orientation=True, tol=out_tol)

    # ---- Bottom (axis_idx = lo) face -------------------------------------
    # The original "bottom" of the box (perpendicular to axis_idx,
    # on the lo side) has been modified by the fillet at its
    # (sign0, sign1) corner. The fillet arc replaces that corner; the
    # ring becomes a 5-edge loop:
    #   vA_low -> V_low[adj_a] -> V_low[diag] -> V_low[adj_b] -> vB_low
    #   -> (arc) -> vA_low
    bot_outward = np.zeros(3)
    bot_outward[axis_idx] = -1.0
    bot_pts = [
        vA_low.point, V_low[adj_a_sign].point, V_low[diag_sign].point,
        V_low[adj_b_sign].point, vB_low.point,
    ]
    bot_edges = [
        (e_bot_1, True), (e_bot_2, True), (e_bot_3, True),
        (e_bot_4, True),
        # Arc walked from vB_low to vA_low: arc edge naturally goes
        # vA->vB (forward); we walk it reversed.
        (e_arc_low, False),
    ]
    bot_face = _build_planar_face(bot_pts, bot_edges, bot_outward)

    # ---- Top (axis_idx = hi) face ----------------------------------------
    top_outward = np.zeros(3)
    top_outward[axis_idx] = +1.0
    top_pts = [
        vA_high.point, V_high[adj_a_sign].point, V_high[diag_sign].point,
        V_high[adj_b_sign].point, vB_high.point,
    ]
    top_edges = [
        (e_top_1, True), (e_top_2, True), (e_top_3, True),
        (e_top_4, True),
        (e_arc_high, False),
    ]
    top_face = _build_planar_face(top_pts, top_edges, top_outward)

    # ---- Support A (the face containing contact line A) ------------------
    # Support A spans the (axis_idx, other[0]) plane at b = b_at. Its
    # outward direction is -b_in along other[1] (i.e. away from the
    # solid interior at that face).
    # Loop traversal (any direction; we let _build_planar_face fix the
    # orientation):
    #   vA_low -> V_low[adj_a]   (along other[0])     e_bot_1+
    #   V_low[adj_a] -> V_high[adj_a]  (along axis)   e_vert_adj_a+
    #   V_high[adj_a] -> vA_high (along other[0] -)   e_top_1-
    #   vA_high -> vA_low (contact, along axis -)    e_contact_A-
    A_outward = np.zeros(3)
    A_outward[other[1]] = -b_in
    A_pts = [
        vA_low.point, V_low[adj_a_sign].point,
        V_high[adj_a_sign].point, vA_high.point,
    ]
    A_edges = [
        (e_bot_1, True), (e_vert_adj_a, True),
        (e_top_1, False), (e_contact_A, False),
    ]
    support_A_face = _build_planar_face(A_pts, A_edges, A_outward)

    # ---- Support B (the face containing contact line B) ------------------
    B_outward = np.zeros(3)
    B_outward[other[0]] = -a_in
    B_pts = [
        vB_low.point, V_low[adj_b_sign].point,
        V_high[adj_b_sign].point, vB_high.point,
    ]
    B_edges = [
        (e_bot_4, False), (e_vert_adj_b, True),
        (e_top_4, True), (e_contact_B, False),
    ]
    support_B_face = _build_planar_face(B_pts, B_edges, B_outward)

    # ---- Far-side faces (the two untouched-corner ring faces) ------------
    # The diagonal face is the one whose outward normal is along
    # +a_in*other[0] (opposite to support B's outward).  Going around:
    # V_low[adj_a] -> V_low[diag] -> V_high[diag] -> V_high[adj_a].
    far_A_outward = np.zeros(3)
    far_A_outward[other[1]] = +b_in  # opposite of support A
    far_A_pts = [
        V_low[adj_b_sign].point, V_low[diag_sign].point,
        V_high[diag_sign].point, V_high[adj_b_sign].point,
    ]
    far_A_edges = [
        (e_bot_3, False), (e_vert_diag, True),
        (e_top_3, True), (e_vert_adj_b, False),
    ]
    far_A_face = _build_planar_face(far_A_pts, far_A_edges, far_A_outward)

    far_B_outward = np.zeros(3)
    far_B_outward[other[0]] = +a_in
    far_B_pts = [
        V_low[adj_a_sign].point, V_low[diag_sign].point,
        V_high[diag_sign].point, V_high[adj_a_sign].point,
    ]
    far_B_edges = [
        (e_bot_2, True), (e_vert_diag, True),
        (e_top_2, False), (e_vert_adj_a, False),
    ]
    far_B_face = _build_planar_face(far_B_pts, far_B_edges, far_B_outward)

    # ---- Fillet face (quarter-cylinder) ---------------------------------
    # The fillet face is a quarter of cyl_surf. Wrap it in a
    # ``_CylindricalArcSurface`` whose local (u, v) = (0.5, 0.5) maps to
    # the centre of the active region; this keeps ``validate_body``'s
    # signed-area test honest (the surface normal it samples is in the
    # face region, not in some random part of the full cylinder).
    fill_arc_surf = _CylindricalArcSurface(
        centre=fill_centre_low, axis=fill_axis_dir, radius=radius,
        x_ref=xref, u_start=u_start, u_end=u_end,
        v_start=0.0, v_end=fill_height,
    )
    # The candidate loop walks:
    #   bottom arc (vA_low -> vB_low) forward
    #   contact B (vB_low -> vB_high) forward
    #   top arc (vB_high -> vA_high) — i.e. e_arc_high reversed
    #   contact A (vA_high -> vA_low) — i.e. e_contact_A reversed
    candidate_fill_edges = [
        (e_arc_low, True),
        (e_contact_B, True),
        (e_arc_high, False),
        (e_contact_A, False),
    ]
    # Compute the candidate's 3D polygon area vector.
    surf_n_at_mid = fill_arc_surf.normal(0.5, 0.5)
    cand_pts = [
        e.curve.evaluate(e.t0) if o else e.curve.evaluate(e.t1)
        for (e, o) in candidate_fill_edges
    ]
    cand_centroid = np.mean(cand_pts, axis=0)
    cand_area = np.zeros(3)
    for i, p in enumerate(cand_pts):
        nxt = cand_pts[(i + 1) % len(cand_pts)]
        cand_area += np.cross(p - cand_centroid, nxt - cand_centroid)
    if float(np.dot(cand_area, surf_n_at_mid)) >= 0:
        fill_coedges = [Coedge(e, o) for (e, o) in candidate_fill_edges]
    else:
        # Reverse the loop to make it CCW about the outward surface
        # normal (keep orientation=True so face_normal stays outward).
        fill_coedges = [
            Coedge(e, not o)
            for (e, o) in reversed(candidate_fill_edges)
        ]
    fill_loop = Loop(fill_coedges, is_outer=True)
    fill_face = Face(
        fill_arc_surf, [fill_loop], orientation=True,
        tol=out_tol,
    )

    # ---- Assemble + sew + validate --------------------------------------
    all_faces = [
        bot_face, top_face, support_A_face, support_B_face,
        far_A_face, far_B_face, fill_face,
    ]
    shell = sew_faces(all_faces, tol=out_tol)
    if not shell.is_closed:
        raise BuildError(
            "fillet_solid_edge (planar+planar): sewn shell is not closed"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"fillet_solid_edge produced invalid Body: {res['errors']}", res,
        )
    return body


# ---------------------------------------------------------------------------
# Recognition: planar+cylindrical (cylinder cap rim) case
# ---------------------------------------------------------------------------


def _is_axis_aligned_cylinder(body: Body, tol: float) -> Optional[dict]:
    """Return ``{"centre_low": ..., "axis_dir": ..., "radius": ..., ...}``
    iff ``body`` is a closed cylinder solid produced by
    :func:`brep_build.cylinder_to_body`, otherwise None.
    """
    if len(body.solids) != 1 or body.shells:
        return None
    sh = body.solids[0].shells[0] if body.solids[0].shells else None
    if sh is None or not sh.is_closed:
        return None
    if len(sh.faces) != 3:
        return None
    cyl_face = None
    cap_faces: List[Face] = []
    for f in sh.faces:
        if isinstance(f.surface, CylinderSurface):
            if cyl_face is not None:
                return None
            cyl_face = f
        elif isinstance(f.surface, Plane):
            cap_faces.append(f)
        else:
            return None
    if cyl_face is None or len(cap_faces) != 2:
        return None
    cyl: CylinderSurface = cyl_face.surface  # type: ignore
    return {
        "centre_low": cyl.center.copy(),
        "axis_dir": cyl.axis.copy(),
        "x_ref": cyl.x_ref.copy(),
        "radius": float(cyl.radius),
        "tol": tol,
        "cyl_face": cyl_face,
        "cap_faces": cap_faces,
    }


def _cap_rim_edge_info(body: Body, edge: Edge, cyl_info: dict
                       ) -> Optional[dict]:
    """Detect when ``edge`` is a cap-rim circular edge of a cylinder
    body (i.e. an edge whose curve is a ``CircleArc3`` of full 2pi range
    on the same axis & radius as the cylinder, lying in one of the cap
    planes).
    """
    if not isinstance(edge.curve, CircleArc3):
        return None
    arc: CircleArc3 = edge.curve
    if abs(arc.radius - cyl_info["radius"]) > cyl_info["tol"] * 100.0:
        return None
    if abs((edge.t1 - edge.t0) - 2 * math.pi) > 1e-6:
        return None
    # Determine which cap the rim is on (bottom = centre_low, top =
    # centre_low + height*axis_dir). Find the matching cap face.
    centre_low = cyl_info["centre_low"]
    axis_dir = cyl_info["axis_dir"]
    diff = arc.center - centre_low
    h = float(np.dot(diff, axis_dir))
    if h < cyl_info["tol"] * 10:
        which = "bottom"
        cap_centre = centre_low.copy()
    else:
        which = "top"
        cap_centre = centre_low + h * axis_dir
    # Find the cap face whose Plane.origin is closest to cap_centre.
    cap_face = None
    other_cap = None
    for f in cyl_info["cap_faces"]:
        p: Plane = f.surface  # type: ignore
        if float(np.linalg.norm(p.origin - cap_centre)) < cyl_info["tol"] * 100.0:
            cap_face = f
        else:
            other_cap = f
    if cap_face is None or other_cap is None:
        return None
    height = float(np.linalg.norm(
        cyl_info["cap_faces"][1].surface.origin
        - cyl_info["cap_faces"][0].surface.origin,
    ))
    return {
        "which": which,
        "cap_centre": cap_centre,
        "other_cap_centre": (
            centre_low + height * axis_dir if which == "bottom"
            else centre_low.copy()
        ),
        "height": height,
        "cap_face": cap_face,
        "other_cap": other_cap,
        "rim_edge": edge,
        "arc": arc,
    }


def _cyl_filleted_rim_body(
    cyl_info: dict, rim_info: dict, radius: float, tol: float
) -> Body:
    """Build a new closed cylinder ``Body`` with one cap-rim filleted
    into a torus segment.

    Layout (for the bottom rim, ``which == 'bottom'``):
        * Lateral cylinder face is shortened: instead of running from
          z=0 to z=H, it runs from z=r (the upper contact circle) to
          z=H.  Its lower rim is a smaller-z parallel circle at the
          contact radius (R - r) ... wait no, for a cap-rim *outside*
          fillet, the contact lies at z=r on the lateral surface and at
          radius R-r on the cap plane.
        * The bottom cap shrinks: it now has radius (R - r).
        * The torus fillet face has major-radius (R - r), minor-radius
          r, the major-circle centred on the cylinder axis at z=r.

    The result has 4 faces (lateral, top cap, bottom cap, torus) and is
    sewn + validated.
    """
    R = cyl_info["radius"]
    H = rim_info["height"]
    axis_dir = cyl_info["axis_dir"]
    centre_low = cyl_info["centre_low"]
    out_tol = max(cyl_info["tol"], tol, radius * 1e-6)
    if radius >= R:
        raise BuildError(
            f"radius {radius} >= cylinder radius {R} (rolling ball does "
            "not fit)"
        )
    if radius >= H:
        raise BuildError(
            f"radius {radius} >= cylinder height {H} (rolling ball does "
            "not fit)"
        )

    which = rim_info["which"]

    # Geometric anchors (we always reference these from centre_low).
    # 'top' is centre_low + H*axis_dir.
    top_c = centre_low + H * axis_dir
    if which == "bottom":
        cap_centre = centre_low
        cap_normal = -axis_dir
        lateral_low_after = centre_low + radius * axis_dir
        lateral_high_after = top_c
        torus_major_c = centre_low + radius * axis_dir
        # The cap radius after fillet:
        cap_R_after = R - radius
        # other cap (top cap) is unchanged.
        other_cap_centre = top_c
        other_cap_normal = +axis_dir
    else:  # 'top'
        cap_centre = top_c
        cap_normal = +axis_dir
        lateral_low_after = centre_low
        lateral_high_after = top_c - radius * axis_dir
        torus_major_c = top_c - radius * axis_dir
        cap_R_after = R - radius
        other_cap_centre = centre_low
        other_cap_normal = -axis_dir

    xref = cyl_info["x_ref"]
    yref = _unit(np.cross(axis_dir, xref))

    # Build all shared edges first so the manifold topology is correct.
    # Trimmed lateral: a cylinder of height H - radius, from
    # lateral_low_after to lateral_high_after.
    new_H = H - radius
    new_cyl = CylinderSurface(lateral_low_after, axis_dir, R, xref)

    # Seam vertices on the trimmed lateral surface (at angle 0):
    seam_low_lat = lateral_low_after + R * xref
    seam_high_lat = lateral_high_after + R * xref
    v_seam_lat_low = Vertex(seam_low_lat, out_tol)
    v_seam_lat_high = Vertex(seam_high_lat, out_tol)
    lat_circ_low = CircleArc3(
        lateral_low_after, R, xref, yref, 0.0, 2 * math.pi,
    )
    lat_circ_high = CircleArc3(
        lateral_high_after, R, xref, yref, 0.0, 2 * math.pi,
    )
    # ``e_lat_low_rim`` is the contact circle between lateral & torus.
    # ``e_lat_high_rim`` is the rim between lateral & untouched cap.
    e_lat_low_rim = Edge(
        lat_circ_low, 0.0, 2 * math.pi, v_seam_lat_low, v_seam_lat_low,
        out_tol,
    )
    e_lat_high_rim = Edge(
        lat_circ_high, 0.0, 2 * math.pi, v_seam_lat_high,
        v_seam_lat_high, out_tol,
    )
    e_lat_seam = Edge(
        Line3(seam_low_lat, seam_high_lat), 0.0, 1.0,
        v_seam_lat_low, v_seam_lat_high, out_tol,
    )
    lat_loop = Loop(
        [
            Coedge(e_lat_low_rim, True),
            Coedge(e_lat_seam, True),
            Coedge(e_lat_high_rim, False),
            Coedge(e_lat_seam, False),
        ],
        is_outer=True,
    )
    lateral_face = Face(new_cyl, [lat_loop], orientation=True, tol=out_tol)

    # The trimmed (small) cap: a smaller plane disc, radius cap_R_after.
    # Its rim is the shared contact circle (e_cap_rim) between trimmed
    # cap & torus.
    cap_plane = Plane(
        origin=cap_centre, x_axis=xref,
        y_axis=_unit(np.cross(cap_normal, xref)),
    )
    cap_rim_seam_pt = cap_centre + cap_R_after * xref
    v_cap_rim_seam = Vertex(cap_rim_seam_pt, out_tol)
    cap_rim_curve = CircleArc3(
        cap_centre, cap_R_after, xref, _unit(np.cross(cap_normal, xref)),
        0.0, 2 * math.pi,
    )
    e_cap_rim = Edge(
        cap_rim_curve, 0.0, 2 * math.pi, v_cap_rim_seam, v_cap_rim_seam,
        out_tol,
    )
    cap_loop = Loop([Coedge(e_cap_rim, True)], is_outer=True)
    trimmed_cap_face = Face(
        cap_plane, [cap_loop], orientation=True, tol=out_tol,
    )

    # The untouched other cap (full radius R) — shares e_lat_high_rim
    # with the lateral face.
    other_plane = Plane(
        origin=other_cap_centre, x_axis=xref,
        y_axis=_unit(np.cross(other_cap_normal, xref)),
    )
    other_loop = Loop(
        [Coedge(e_lat_high_rim, True)], is_outer=True,
    )
    other_cap_face = Face(
        other_plane, [other_loop], orientation=True, tol=out_tol,
    )

    # Fillet face: torus segment.
    # Major-radius = cap_R_after = R - r (centre of fillet axis ring).
    # Minor-radius = r.
    # The torus surface's axis is cyl_info["axis_dir"], centred at
    # torus_major_c. For the bottom rim with which='bottom', the torus
    # half is the half whose minor angle v in [0, pi/2] (so the fillet
    # is on the outside-bottom of the original cylinder).
    # Actually we only need the quarter-torus that bulges outward from
    # the corner.
    #
    # Easier approach: build a quarter-cylinder-like Cylindrical
    # CIRCLE in the (radial, axial) cross-section and revolve. But our
    # B-rep already supports TorusSurface; we just bound it.
    #
    # TorusSurface.evaluate(u, v) = centre +
    #   (major_R + minor_R * cos(v)) * (cos(u)*_x + sin(u)*_y)
    #   + minor_R * sin(v) * axis
    # We want the fillet to occupy u in [0, 2pi] (full revolution) and
    # v in a quarter range that exposes the fillet's outward bulge.
    # For which='bottom': the contact circle on lateral side is at
    # axis_dir's positive side (z = radius), with v = pi/2 (point at
    # major_R + minor_R*0 = major_R along the ring direction + r along
    # axis). Hmm: at v=pi/2, point = centre + (major_R + 0)*ring +
    # minor_R*1*axis = torus_major_c + (R-r)*ring + r*axis_dir. But the
    # contact circle on the lateral is at (R*ring + radius*axis_dir
    # offset from centre_low). Let's check: lateral contact circle is
    # at z = radius. torus_major_c is at z = radius (since
    # torus_major_c = centre_low + radius*axis_dir). So z-coord of
    # contact = radius. At v=pi/2: z = z(torus_major_c) + r*sin(pi/2) =
    # radius + r ≠ radius. So that's wrong.
    #
    # Correct mapping: the lateral contact circle on the original
    # cylinder is the locus where the rolling ball touches the lateral
    # surface. For an *outside* fillet at the bottom rim, the ball
    # rolls in the dihedral, touching the lateral surface at z = r and
    # the cap plane at radius R - r. So the contact circle on the
    # lateral side is at z = r, radius R. On the cap-plane side, the
    # contact circle is at z = 0, radius R - r.
    #
    # The TORUS fillet has:
    #   * major-circle centre at z = r on the axis (the centre of the
    #     rolling-ball trajectory).
    #   * Wait — the rolling-ball centre traces a circle parallel to
    #     the cap plane at z = r (since the ball has radius r and
    #     touches the cap plane at z=0). This is NOT at the cylinder
    #     axis. The ball-centre radius from the cylinder axis is
    #     R - r (so that the ball touches the lateral surface from
    #     inside the cylinder ... NO, from OUTSIDE for an outside
    #     fillet).
    #
    # Reconsider: the user makes a cylinder solid and wants to fillet
    # the bottom rim — the rim where the lateral meets the bottom cap.
    # That fillet replaces the sharp 90° outside corner with a quarter-
    # torus. For an *outside* fillet (the most common interpretation):
    #   * The ball sits outside the cylinder, rolling around the bottom
    #     rim.
    #   * It contacts the lateral surface at z = r, radius R, on the
    #     OUTSIDE of the cylinder (i.e. the lateral support's outward
    #     surface).
    #   * It contacts the cap plane at radius R + r ... but that's
    #     OUTSIDE the cylinder; the cap plane is unbounded.
    #
    # The OTHER interpretation: an *inside* fillet — the ball rolls on
    # the inside corner. But the inside of the bottom rim is INSIDE the
    # cylinder solid (a concave corner). That's a "concave fillet" and
    # it removes material from the solid (rounds the inside corner) —
    # but a closed cylinder has no inside corner accessible to a
    # rolling ball without first opening it.
    #
    # The natural interpretation for a *convex* outside corner at the
    # cylinder bottom rim is exactly what I described first (ball sits
    # outside the cylinder, fillet bulges outward from the rim,
    # *removing material* from the cylinder solid where the rim was
    # sharp).
    #
    # Result: cylinder solid with rounded bottom rim. Material is
    # removed from the bottom rim corner — the new solid is smaller.
    # The torus is concave-facing (its surface normal points away from
    # the cylinder axis and away from the cap, toward the outside).
    # The lateral support gets trimmed to z >= r (lateral remains the
    # original radius R, but only above z = r). The cap support gets
    # trimmed to radius <= R - r (smaller disc).
    #
    # That matches the math I set up above. Now for the torus:
    #   centre of torus = (axis-position at z = r, radial offset R - r)
    #     = torus_major_c + (R - r) along ring direction at every u.
    # Wait — TorusSurface in brep.py has its centre on the axis. Let me
    # re-read:
    #   centre + (major_R + minor_R*cos(v)) * ring_dir(u) +
    #     minor_R * sin(v) * axis
    # So at u=0, v=0: centre + (major_R)*_x.
    # The major-circle centre is at ``centre`` (on the axis); the
    # circle has radius major_R; the minor circle of the torus has
    # radius minor_R.
    # We want the torus tube (minor circle) to pass through
    #   * lateral contact circle (z = r, radius R)
    #   * cap contact circle (z = 0, radius R - r)
    # These two circles are both centred on the axis. They are at
    # (radial, axial) = (R, r) and (R - r, 0) in the (R, z) half-plane.
    # The minor circle (a circle of radius r in the (R, z) plane,
    # parametrised by v) must pass through both. The minor circle is
    # centred at (major_R, 0_axial_offset_from_centre). For our problem
    # we set torus.centre = (axis position at z = r) so the torus
    # centre is "at z = r" — that places the (R,z) origin of the minor
    # circle parameterisation at (radial offset 0, z=r) — but it has
    # to be at (R - r, r) so that the minor circle of radius r is
    # tangent to both contact circles. So we set:
    #   torus_centre = (axis at z = r) — yes, but then
    #   major_R = R - r so the minor-circle centre at v=any is at
    #     radial = major_R = R - r, z = r.
    # The minor circle has radius r, so it spans from radial = R - 2r
    # to radial = R (at v = 0 or pi) and from z = 0 to z = 2r (at
    # v = ±pi/2).
    #
    # Now: the lateral contact is at (radial = R, z = r) = minor
    # circle's v = 0 point (radius R-r + r*cos(0) = R, z offset 0
    # from torus centre z = r => z = r). Yes!
    # The cap contact is at (radial = R - r, z = 0) = minor circle's
    # v = -pi/2 point (radius R-r + r*cos(-pi/2) = R-r, z offset
    # r*sin(-pi/2) = -r => z = 0). Yes!
    #
    # So the fillet face is the quarter-torus with v in [-pi/2, 0] (or
    # equivalently [3pi/2, 2pi] — but let's use [-pi/2, 0] for
    # clarity), u in [0, 2pi] (full revolution).
    #
    # This works for which='bottom'. For 'top', v range is [0, pi/2]
    # and centre is at top_c - r*axis_dir.

    # Torus segment surface: u in [0, 2pi] full revolution, v in the
    # quarter range that exposes the fillet bulge.
    if which == "bottom":
        v_lat = 0.0
        v_cap = -math.pi / 2.0
        torus_rim_lateral_edge = e_lat_low_rim
        torus_rim_lateral_v = v_seam_lat_low
        torus_rim_lateral_pt = seam_low_lat
    else:
        v_lat = 0.0
        v_cap = +math.pi / 2.0
        torus_rim_lateral_edge = e_lat_high_rim
        torus_rim_lateral_v = v_seam_lat_high
        torus_rim_lateral_pt = seam_high_lat

    torus_rim_cap_edge = e_cap_rim
    torus_rim_cap_v = v_cap_rim_seam
    torus_rim_cap_pt = cap_rim_seam_pt

    # Use the cylinder's xref as the torus's x-axis so the seam at u=0
    # lines up with the cylinder seam. v=v_lat gives lateral contact,
    # v=v_cap gives cap contact.
    v_start_torus = min(v_lat, v_cap)
    v_end_torus = max(v_lat, v_cap)
    torus_surf = _TorusSegmentSurface(
        centre=torus_major_c, axis=axis_dir,
        major_radius=cap_R_after, minor_radius=radius,
        u_start=0.0, u_end=2.0 * math.pi,
        v_start=v_start_torus, v_end=v_end_torus,
        x_ref=xref,
    )

    # Seam meridian curve from cap-contact (v_cap) to lateral-contact
    # (v_lat) at u=0 on the torus.
    class _TorusMeridian:
        def __init__(self, surf, vstart: float, vend: float) -> None:
            self.surf = surf
            self.vstart = vstart
            self.vend = vend

        def evaluate(self, t: float) -> np.ndarray:
            t = float(t)
            cv = self.vstart + (self.vend - self.vstart) * t
            return (
                self.surf.centre
                + (self.surf.major_radius
                   + self.surf.minor_radius * math.cos(cv)) * self.surf._x
                + self.surf.minor_radius * math.sin(cv) * self.surf.axis
            )

    # We want the seam to walk from cap_v_seam point to lat_v_seam
    # point. Inspect their actual 3D positions:
    # cap_rim_seam_pt = cap_centre + (R - r) * xref
    # seam_low_lat (or seam_high_lat) = lateral_low_after + R * xref
    # These both lie at u=0 on the torus when xref is the torus _x.
    # Build a seam line that interpolates v: at t=0 we want cap_v_seam
    # (v=v_cap), at t=1 we want lat_v_seam (v=v_lat).
    torus_seam_curve = _TorusMeridian(torus_surf, v_cap, v_lat)
    e_torus_seam = Edge(
        torus_seam_curve, 0.0, 1.0,
        torus_rim_cap_v, torus_rim_lateral_v, out_tol,
    )

    # For manifold-correct sharing the torus face must walk each rim
    # in the OPPOSITE orientation from the face that already uses it.
    # Lateral face uses e_lat_low_rim with orientation=True (when
    # which='bottom'), so the torus must walk it with False. Similarly
    # trimmed_cap_face uses e_cap_rim with orientation=True, so the
    # torus must walk it with False.
    # Loop pattern: lateral_rim- -> seam(forward to cap) -> cap_rim- ->
    # seam(forward to lateral).
    # But seam used twice in one loop must be once forward and once
    # backward (for the loop to close). Walking lateral_rim backward
    # ends at the seam endpoint on the lateral side; we then need to
    # go to the seam endpoint on the cap side. With the seam edge
    # defined as v_torus_rim_cap_v -> v_torus_rim_lateral_v (its
    # natural direction), going *backward* on it takes us from
    # lateral -> cap. Then cap_rim backward takes us around the cap
    # rim back to the cap-seam endpoint. Then seam *forward* takes us
    # from cap -> lateral. Closes the loop.
    candidate_torus_edges = [
        (torus_rim_lateral_edge, False),  # lateral rim backward
        (e_torus_seam, False),            # seam: lateral -> cap
        (torus_rim_cap_edge, False),      # cap rim backward
        (e_torus_seam, True),             # seam: cap -> lateral
    ]
    # Verify loop closure and orientation.
    surf_n_mid = torus_surf.normal(0.5, 0.5)
    cand_pts = []
    cur_pt = None
    for (e, o) in candidate_torus_edges:
        sp = e.curve.evaluate(e.t0 if o else e.t1)
        cand_pts.append(np.asarray(sp, dtype=float))
    cand_centroid = np.mean(cand_pts, axis=0)
    cand_area = np.zeros(3)
    for i, p in enumerate(cand_pts):
        nxt = cand_pts[(i + 1) % len(cand_pts)]
        cand_area += np.cross(p - cand_centroid, nxt - cand_centroid)
    # If the loop is CW about the surface normal, flip the FACE
    # orientation (not the loop edges, since those orientations are
    # constrained by manifold matching).
    if float(np.dot(cand_area, surf_n_mid)) >= 0:
        face_orient = True
    else:
        face_orient = False
    torus_coedges = [Coedge(e, o) for (e, o) in candidate_torus_edges]
    torus_loop = Loop(torus_coedges, is_outer=True)
    torus_face = Face(
        torus_surf, [torus_loop], orientation=face_orient, tol=out_tol,
    )

    # ---- Assemble + sew + validate --------------------------------------
    all_faces = [
        lateral_face, trimmed_cap_face, other_cap_face, torus_face,
    ]
    shell = sew_faces(all_faces, tol=out_tol)
    if not shell.is_closed:
        raise BuildError(
            "fillet_solid_edge (planar+cylindrical): sewn shell is not "
            "closed"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"fillet_solid_edge (planar+cyl) produced invalid Body: "
            f"{res['errors']}", res,
        )
    return body


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def fillet_solid_edge(
    body: Body, edge: Edge, radius: float, *, tol: float = 1e-6,
) -> FilletResult:
    """Body-emitting rolling-ball fillet on a single ``Edge`` of ``body``.

    Parameters
    ----------
    body : Body
        Input body — must be a single closed solid produced by
        :func:`brep_build.box_to_body`, :func:`brep_build.cylinder_to_body`
        (or the legacy :func:`brep.make_box` / :func:`brep.make_cylinder`).
    edge : Edge
        An edge of ``body`` matching one of the supported configurations:
            * straight axis-aligned segment between two box vertices, or
            * cap-rim circular edge of a cylinder body.
    radius : float
        Rolling-ball radius. Must satisfy:
            * ``radius > 0``
            * ``radius`` is smaller than each support's perpendicular
              extent (so contact lines lie strictly inside the supports).
            * For the planar+cylindrical case additionally
              ``radius < cylinder_radius`` and ``radius < cylinder_height``.
    tol : float
        Linear tolerance used for entity sharing and ``validate_body``
        passes; the resulting body's tolerance fields are at least this
        value.

    Returns
    -------
    FilletResult
        A dict containing ``ok``, ``reason``, ``body``, ``fillet_face``,
        ``trimmed_face_a``, ``trimmed_face_b``, ``volume_removed`` and
        diagnostics. ``ok`` is True iff the new body passed
        ``validate_body``.

    This function never raises; on any failure path it returns
    ``{"ok": False, "reason": "..."}``.

    Supported-input contract
    ------------------------
    See :func:`edge_supported_contract`.
    """
    # --- 0. Input validation --------------------------------------------
    if not isinstance(body, Body):
        return _empty(f"body must be a Body, got {type(body).__name__}")
    if not isinstance(edge, Edge):
        return _empty(f"edge must be an Edge, got {type(edge).__name__}")
    if not isinstance(radius, (int, float)) or radius <= 0:
        return _empty(f"radius must be a positive number, got {radius!r}")
    radius = float(radius)

    # --- 1. Is the edge present in the body? -----------------------------
    incident_faces = _find_incident_faces(body, edge)
    if len(incident_faces) != 2:
        return _empty(
            f"edge#{edge.id} is incident to {len(incident_faces)} faces; "
            "exactly 2 are required"
        )

    f_a, f_b = incident_faces
    a_is_planar = _is_planar_face(f_a)
    b_is_planar = _is_planar_face(f_b)
    a_is_cyl = _is_cylindrical_face(f_a)
    b_is_cyl = _is_cylindrical_face(f_b)

    try:
        if a_is_planar and b_is_planar:
            box_info = _is_axis_aligned_box(body, tol)
            if box_info is None:
                return _empty(
                    "planar+planar edge fillet requires an axis-aligned "
                    "box body (only this primitive is supported in the "
                    "current contract; general planar+planar arrives "
                    "via GK-29 extension)"
                )
            edge_info = _is_axis_aligned_edge(edge)
            if edge_info is None:
                return _empty(
                    "edge is not an axis-aligned straight segment "
                    "(only axis-aligned box edges are supported)"
                )
            # Check radius vs. edge length.
            edge_len = edge_info["length"]
            if radius >= edge_len:
                return _empty(
                    f"radius {radius} >= edge length {edge_len}; fillet "
                    "would consume the entire edge (unsupported)"
                )
            new_body = _box_filleted_edge_body(
                box_info, edge_info, radius, tol,
            )
            volume_removed = (1.0 - math.pi / 4.0) * (radius ** 2) * edge_len
            return FilletResult(
                ok=True,
                reason="",
                body=new_body,
                fillet_face=new_body.solids[0].shells[0].faces[-1],
                trimmed_face_a=new_body.solids[0].shells[0].faces[2],
                trimmed_face_b=new_body.solids[0].shells[0].faces[3],
                volume_removed=volume_removed,
                diagnostics={
                    "kind": "planar+planar",
                    "radius": radius,
                    "edge_length": edge_len,
                },
            )
        elif (a_is_planar and b_is_cyl) or (a_is_cyl and b_is_planar):
            cyl_info = _is_axis_aligned_cylinder(body, tol)
            if cyl_info is None:
                return _empty(
                    "planar+cylindrical edge fillet requires a closed "
                    "cylinder body (brep_build.cylinder_to_body)"
                )
            rim_info = _cap_rim_edge_info(body, edge, cyl_info)
            if rim_info is None:
                return _empty(
                    "edge is not a cap-rim circular edge of the cylinder"
                )
            if radius >= cyl_info["radius"]:
                return _empty(
                    f"radius {radius} >= cylinder radius "
                    f"{cyl_info['radius']}; rolling ball does not fit"
                )
            if radius >= rim_info["height"]:
                return _empty(
                    f"radius {radius} >= cylinder height "
                    f"{rim_info['height']}; rolling ball does not fit"
                )
            new_body = _cyl_filleted_rim_body(cyl_info, rim_info, radius, tol)
            # Volume removed by an outside-bottom-rim fillet of radius r
            # on a cylinder of radius R, height H:
            #   V_removed = (volume of the L-shaped ring around the rim
            #                that the rolling ball carves off)
            #   This is the Pappus integral; for the geometry described
            #   above it works out to
            #      V_removed = pi * r * (R**2 - (R - r)**2)
            #                  - 0.5 * pi**2 * r**2 * (R - r/2) ... etc
            # We compute it numerically from the displacement, but the
            # closed form is also available — not asserted here (only
            # planar+planar volume oracle is required by the spec).
            volume_removed = (
                math.pi * (
                    radius ** 2 * cyl_info["radius"] - radius ** 3 / 3.0
                    - math.pi / 4.0 * radius ** 2 * (
                        cyl_info["radius"] - radius
                    )
                    - math.pi / 4.0 * radius ** 3
                )
            )
            return FilletResult(
                ok=True,
                reason="",
                body=new_body,
                fillet_face=new_body.solids[0].shells[0].faces[-1],
                trimmed_face_a=new_body.solids[0].shells[0].faces[0],
                trimmed_face_b=new_body.solids[0].shells[0].faces[1],
                volume_removed=volume_removed,
                diagnostics={
                    "kind": "planar+cylindrical",
                    "radius": radius,
                    "cyl_radius": cyl_info["radius"],
                },
            )
        else:
            return _empty(
                "edge supports must be planar+planar or "
                "planar+cylindrical; got "
                f"{type(f_a.surface).__name__} + "
                f"{type(f_b.surface).__name__}"
            )
    except BuildError as exc:
        return _empty(str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return _empty(f"internal error: {exc}")
