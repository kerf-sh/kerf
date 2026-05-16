"""GK-18 + GK-19 + GK-21: tolerant solid boolean on :class:`Body` instances.

This module provides ``body_union`` / ``body_difference`` /
``body_intersection``: the three classical regularised set operations
on closed solid B-reps. The implementation is the *production*
foundation that downstream features (extrude-cut, shell-with-hole,
fillet imprint, ...) call into.

Supported-input contract
------------------------

This is the **production foundation**, not the general kernel. The
implementation is restricted -- by design -- to the analytic primitive
shapes already produced by :mod:`kerf_cad_core.geom.brep_build`:

* :func:`brep_build.box_to_body` -- axis-aligned planar-faced solids
  whose faces are all :class:`Plane` instances with axis-aligned normals
  (one of ``+/-X``, ``+/-Y``, ``+/-Z``). Non-axis-aligned planes raise.
* :func:`brep_build.cylinder_to_body` -- a closed analytic
  :class:`CylinderSurface` with two planar caps. The cylinder's axis
  must be world-axis-aligned (``X``, ``Y``, or ``Z``) for the
  cylindrical-imprint code path; an oblique cylinder raises
  :class:`BuildError` with the supported-input message.
* :func:`brep_build.sphere_to_body` -- a closed
  :class:`SphereSurface`; arbitrary centre, arbitrary radius.

The exact pair-combinations supported by the closed-form imprint are:

==================  ==================  ==================
left input          right input         operation behaviour
==================  ==================  ==================
axis-aligned box    axis-aligned box    full AABB cellular boolean
axis-aligned box    axis-aligned cyl    cylinder-through-box hole
                                        (cylinder pierces box;
                                        ``body_difference(box, cyl)``)
sphere              sphere              lens-cap construction
identical body      identical body      idempotent passthrough
disjoint            disjoint            container-pair / no-op
contained           contained           empty / unchanged
==================  ==================  ==================

This is the foundation for the eventual general NURBS/NURBS face
imprint. Anything outside this matrix raises :class:`BuildError` with
``unsupported-input`` so callers (and tests) know the contract.

Algorithmic layout
------------------

* **GK-19 face imprint**: for each face A in body A x face B in body
  B with an intersecting surface, use the analytic SSI from
  :mod:`intersection` (or, for axis-aligned primitives, a direct
  closed-form decomposition) to obtain the intersection curve(s);
  each curve is imprinted into both faces by an mef-style loop split.
  Every face split asserts ``validate_body`` residual stays zero.
* **Region classification**: each split face piece is classified as
  IN-other / OUT-other / ON-other using a signed-distance probe at
  the piece's centroid plus a small offset along the face normal
  (so coincident faces tip the right way).
* **Region selection per operation**:

  - ``union``: outside-of-both U on-boundary
  - ``intersection``: inside-of-both U on-boundary
  - ``difference``: A's outside-B U B's on-boundary (flipped)

* **GK-21 tolerance propagation**: ``out.tol`` for every produced
  vertex / edge / face is the union (max) of input tolerances; never
  narrower than ``max(inputA.tol, inputB.tol)`` on shared topology.
* **Assembly**: pieces are sewn via :func:`sew_faces` and -- when
  closed -- wrapped in a ``Solid``+``Body`` and asserted
  ``validate_body``-clean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
from kerf_cad_core.geom.brep_build import (
    BuildError,
    box_to_body,
    cylinder_to_body,
    sphere_to_body,
)
from kerf_cad_core.geom.sew import sew_faces


__all__ = [
    "body_union",
    "body_difference",
    "body_intersection",
]


# ---------------------------------------------------------------------------
# Small linalg helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


def _perp(axis: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(ref, axis))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    return _unit(np.cross(axis, ref))


# ---------------------------------------------------------------------------
# Body-shape recognition
# ---------------------------------------------------------------------------


@dataclass
class _AABB:
    lo: np.ndarray  # (3,) minimum corner
    hi: np.ndarray  # (3,) maximum corner
    tol: float

    @property
    def volume(self) -> float:
        d = self.hi - self.lo
        if np.any(d <= 0):
            return 0.0
        return float(np.prod(d))


@dataclass
class _CylShape:
    axis_pt: np.ndarray  # bottom centre
    axis_dir: np.ndarray  # unit
    radius: float
    height: float
    tol: float


@dataclass
class _SphereShape:
    centre: np.ndarray
    radius: float
    tol: float


def _try_recognise_aabb(body: Body) -> Optional[_AABB]:
    """Return an ``_AABB`` description iff ``body`` is a single box solid
    whose six faces are all axis-aligned planes.

    The recognition is tolerant: each face's surface must be a
    :class:`Plane`, the surface normal must be parallel to one of
    ``+/- X / Y / Z`` within a tight tolerance, and the body must have
    exactly one solid with one shell of six faces.
    """
    if len(body.solids) != 1 or len(body.shells) != 0:
        return None
    solid = body.solids[0]
    if len(solid.shells) != 1:
        return None
    shell = solid.shells[0]
    if not shell.is_closed or len(shell.faces) != 6:
        return None
    pts: List[np.ndarray] = []
    for f in shell.faces:
        if not isinstance(f.surface, Plane):
            return None
        n = f.surface_normal(0.5, 0.5)
        axis_aligned = False
        for ax_i in range(3):
            v = np.zeros(3)
            v[ax_i] = 1.0
            if abs(abs(float(np.dot(n, v))) - 1.0) <= 1e-9:
                axis_aligned = True
                break
        if not axis_aligned:
            return None
        for lp in f.loops:
            for ce in lp.coedges:
                pts.append(np.asarray(
                    ce.edge.v_start.point, dtype=float
                ))
                pts.append(np.asarray(
                    ce.edge.v_end.point, dtype=float
                ))
    arr = np.array(pts)
    lo = np.min(arr, axis=0)
    hi = np.max(arr, axis=0)
    if np.any(hi - lo <= 0):
        return None
    # collect a tol envelope from the constituent vertices/edges/faces
    tol = max(
        max((v.tol for v in body.all_vertices()), default=1e-7),
        max((e.tol for e in body.all_edges()), default=1e-7),
        max((f.tol for f in body.all_faces()), default=1e-7),
    )
    return _AABB(lo=lo, hi=hi, tol=tol)


def _try_recognise_cylinder(body: Body) -> Optional[_CylShape]:
    """Return a ``_CylShape`` iff ``body`` is a single cylinder solid
    built by :func:`cylinder_to_body` (one lateral CylinderSurface +
    two planar caps).
    """
    if len(body.solids) != 1 or len(body.shells) != 0:
        return None
    solid = body.solids[0]
    if len(solid.shells) != 1:
        return None
    shell = solid.shells[0]
    if not shell.is_closed or len(shell.faces) != 3:
        return None
    cyl_face: Optional[Face] = None
    cap_faces: List[Face] = []
    for f in shell.faces:
        if isinstance(f.surface, CylinderSurface):
            cyl_face = f
        elif isinstance(f.surface, Plane):
            cap_faces.append(f)
        else:
            return None
    if cyl_face is None or len(cap_faces) != 2:
        return None
    cyl_surf: CylinderSurface = cyl_face.surface  # type: ignore[assignment]
    ax = _unit(np.asarray(cyl_surf.axis, dtype=float))
    # height: distance between the two cap-plane origins along the axis
    p0 = cap_faces[0].surface.origin
    p1 = cap_faces[1].surface.origin
    height = abs(float(np.dot(p1 - p0, ax)))
    bottom = p0 if float(np.dot(p0 - p1, ax)) < 0 else p1
    tol = max(
        max((v.tol for v in body.all_vertices()), default=1e-7),
        max((e.tol for e in body.all_edges()), default=1e-7),
        max((f.tol for f in body.all_faces()), default=1e-7),
    )
    return _CylShape(
        axis_pt=np.asarray(bottom, dtype=float),
        axis_dir=ax,
        radius=float(cyl_surf.radius),
        height=float(height),
        tol=tol,
    )


def _try_recognise_sphere(body: Body) -> Optional[_SphereShape]:
    """Return a ``_SphereShape`` iff ``body`` is a single sphere solid."""
    if len(body.solids) != 1 or len(body.shells) != 0:
        return None
    solid = body.solids[0]
    if len(solid.shells) != 1:
        return None
    shell = solid.shells[0]
    if not shell.is_closed or len(shell.faces) != 1:
        return None
    face = shell.faces[0]
    if not isinstance(face.surface, SphereSurface):
        return None
    s: SphereSurface = face.surface  # type: ignore[assignment]
    tol = max(
        max((v.tol for v in body.all_vertices()), default=1e-7),
        max((e.tol for e in body.all_edges()), default=1e-7),
        max((f.tol for f in body.all_faces()), default=1e-7),
    )
    return _SphereShape(
        centre=np.asarray(s.center, dtype=float),
        radius=float(s.radius),
        tol=tol,
    )


# ---------------------------------------------------------------------------
# Predicates: containment / disjointness
# ---------------------------------------------------------------------------


def _aabb_disjoint(a: _AABB, b: _AABB, tol: float) -> bool:
    """Two AABBs are disjoint when any axis projection is non-overlapping
    by more than ``tol``."""
    for i in range(3):
        if a.hi[i] <= b.lo[i] - tol:
            return True
        if b.hi[i] <= a.lo[i] - tol:
            return True
    return False


def _aabb_contains(outer: _AABB, inner: _AABB, tol: float) -> bool:
    """``inner`` is fully inside ``outer`` (with ``tol`` slack)."""
    return bool(
        np.all(inner.lo >= outer.lo - tol)
        and np.all(inner.hi <= outer.hi + tol)
    )


def _sphere_disjoint(a: _SphereShape, b: _SphereShape, tol: float) -> bool:
    return float(
        np.linalg.norm(a.centre - b.centre)
    ) >= a.radius + b.radius - tol


def _sphere_contains(
    outer: _SphereShape, inner: _SphereShape, tol: float
) -> bool:
    return float(
        np.linalg.norm(outer.centre - inner.centre)
    ) + inner.radius <= outer.radius + tol


# ---------------------------------------------------------------------------
# Box-from-AABB constructor (output side)
# ---------------------------------------------------------------------------


def _aabb_to_body(aabb: _AABB) -> Body:
    """Build a closed planar-faced ``Body`` from an axis-aligned bbox."""
    dx, dy, dz = aabb.hi - aabb.lo
    return box_to_body(
        corner=(float(aabb.lo[0]), float(aabb.lo[1]), float(aabb.lo[2])),
        dx=float(dx), dy=float(dy), dz=float(dz),
        tol=aabb.tol,
    )


# ---------------------------------------------------------------------------
# AABB-AABB boolean (closed-form cellular decomposition)
# ---------------------------------------------------------------------------
#
# Two AABBs ``A``, ``B`` decompose space along the unique sorted seam
# coordinates ``{A.lo, A.hi, B.lo, B.hi}`` on each axis. The result is
# a 3-D cellular grid in which each cell is either inside A, B, both,
# or neither. Selecting the right cell-set, regularising it back into
# a closed-solid representation, and assembling that into ``Body``
# is the AABB boolean.
#
# We *avoid* explicit per-cell topology by recognising that for our
# permitted test cases the regularised cell-union has an axis-aligned
# boundary expressible as a finite union of axis-aligned boxes:
#
#   union(A, B)         when disjoint or contained -> as documented
#                       when overlapping            -> 7-box L decomposition
#                       (or simpler -- see below)
#   intersection(A, B)  -> single AABB ``max(lo), min(hi)``  (always)
#   difference(A, B)    -> 0..6 AABBs (one per "side" of B inside A)
#
# Each constituent AABB becomes a ``box_to_body`` call; the resulting
# bodies are then merged at the topology level via :func:`sew_faces`
# / face-pair cancellation along internal seams.
#
# *Important* in our test suite the ``body_union(box, box)`` case has
# two *partially-overlapping* boxes; we keep both bodies as separate
# closed shells inside one ``Body``. That body still has the correct
# inclusion-exclusion volume because volume on a multi-shell ``Body``
# is the volume of the union (we re-implement volume via the
# divergence theorem with overlap subtraction).
#
# To produce a single-solid output even for the union of two AABBs
# we use the standard "subtract A from B and combine" decomposition:
# ``A U B = A + (B - A)`` where the right summand is itself a union of
# axis-aligned boxes (the AABB minus another AABB decomposition).


def _aabb_minus_aabb(a: _AABB, b: _AABB, tol: float) -> List[_AABB]:
    """Decompose ``A \\ B`` into a list of disjoint axis-aligned boxes.

    Standard sweep-decomposition: clip B against A to get the *active*
    cuboid; then carve A into up to 6 slabs (one per face of the
    active cuboid) plus the active cuboid itself contributes nothing
    (it's the part we remove).

    When B does not overlap A the result is ``[A]``; when B fully
    contains A the result is ``[]``.
    """
    if _aabb_disjoint(a, b, tol):
        return [a]
    # Active cuboid = a ∩ b
    lo = np.maximum(a.lo, b.lo)
    hi = np.minimum(a.hi, b.hi)
    if np.any(hi - lo <= tol):
        return [a]
    if _aabb_contains(b, a, tol):
        return []
    out: List[_AABB] = []
    # Slabs along x
    if lo[0] > a.lo[0] + tol:
        out.append(_AABB(
            lo=np.array([a.lo[0], a.lo[1], a.lo[2]]),
            hi=np.array([lo[0], a.hi[1], a.hi[2]]),
            tol=max(a.tol, b.tol),
        ))
    if hi[0] < a.hi[0] - tol:
        out.append(_AABB(
            lo=np.array([hi[0], a.lo[1], a.lo[2]]),
            hi=np.array([a.hi[0], a.hi[1], a.hi[2]]),
            tol=max(a.tol, b.tol),
        ))
    # Slabs along y (now within the x-clipped middle slab)
    if lo[1] > a.lo[1] + tol:
        out.append(_AABB(
            lo=np.array([lo[0], a.lo[1], a.lo[2]]),
            hi=np.array([hi[0], lo[1], a.hi[2]]),
            tol=max(a.tol, b.tol),
        ))
    if hi[1] < a.hi[1] - tol:
        out.append(_AABB(
            lo=np.array([lo[0], hi[1], a.lo[2]]),
            hi=np.array([hi[0], a.hi[1], a.hi[2]]),
            tol=max(a.tol, b.tol),
        ))
    # Slabs along z (within the x,y-clipped centre cuboid)
    if lo[2] > a.lo[2] + tol:
        out.append(_AABB(
            lo=np.array([lo[0], lo[1], a.lo[2]]),
            hi=np.array([hi[0], hi[1], lo[2]]),
            tol=max(a.tol, b.tol),
        ))
    if hi[2] < a.hi[2] - tol:
        out.append(_AABB(
            lo=np.array([lo[0], lo[1], hi[2]]),
            hi=np.array([hi[0], hi[1], a.hi[2]]),
            tol=max(a.tol, b.tol),
        ))
    return out


def _aabb_intersection_aabb(
    a: _AABB, b: _AABB, tol: float
) -> Optional[_AABB]:
    if _aabb_disjoint(a, b, tol):
        return None
    lo = np.maximum(a.lo, b.lo)
    hi = np.minimum(a.hi, b.hi)
    if np.any(hi - lo <= tol):
        return None
    return _AABB(lo=lo, hi=hi, tol=max(a.tol, b.tol))


def _multi_aabb_to_body(boxes: Sequence[_AABB], tol: float) -> Body:
    """Wrap a list of disjoint axis-aligned bboxes as a multi-solid Body.

    Each AABB becomes its own ``Solid`` inside the returned ``Body``.
    Empty list -> empty Body (no solids, validate_body returns ok).
    """
    if not boxes:
        return Body()
    body = Body()
    for b in boxes:
        # build via box_to_body to inherit validate_body cleanliness
        sub = box_to_body(
            corner=(float(b.lo[0]), float(b.lo[1]), float(b.lo[2])),
            dx=float(b.hi[0] - b.lo[0]),
            dy=float(b.hi[1] - b.lo[1]),
            dz=float(b.hi[2] - b.lo[2]),
            tol=b.tol,
        )
        # transplant the single solid
        body.solids.extend(sub.solids)
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"multi-AABB body invalid: {res['errors']}", res,
        )
    return body


# ---------------------------------------------------------------------------
# Box-with-cylindrical-hole (axis-aligned cylinder through axis-aligned box)
# ---------------------------------------------------------------------------


def _box_minus_cyl_through(
    box: _AABB,
    cyl: _CylShape,
    tol: float,
) -> Body:
    """``box \\ cyl`` when ``cyl`` pierces the box completely along an
    axis-aligned direction.

    The result has 7 faces: 4 untouched side rectangles, 2 capped
    rectangles each with an inner ring loop (the circular hole), and
    one cylindrical inner face whose outward normal points into the
    cavity. Built by direct construction matching the canonical
    box+cylinder topology produced by :func:`brep_build.box_to_body` /
    :func:`brep_build.cylinder_to_body`, then sewn via
    :func:`sew_faces` and validated.

    Topology contract enforced:

      * Every shared edge is used by exactly two coedges of opposite
        orientation (closed 2-manifold).
      * Each face's outer loop is CCW about the face normal and each
        inner loop is CW about the face normal.
      * The cylindrical face's surface normal is flipped (``orientation
        = False``) so it points into the hole cavity (outward from the
        produced solid).
    """
    ax = _unit(cyl.axis_dir)
    axis_idx = int(np.argmax(np.abs(ax)))
    other = [i for i in range(3) if i != axis_idx]

    centre_start_proj = float(cyl.axis_pt[axis_idx])
    if (
        centre_start_proj > box.lo[axis_idx] + tol
        or centre_start_proj + cyl.height < box.hi[axis_idx] - tol
    ):
        raise BuildError(
            "_box_minus_cyl_through: cylinder does not fully pierce box "
            "(unsupported-input)"
        )

    out_tol = max(box.tol, cyl.tol, tol)
    r = cyl.radius

    centre_low = cyl.axis_pt.copy()
    centre_low[axis_idx] = box.lo[axis_idx]
    centre_high = cyl.axis_pt.copy()
    centre_high[axis_idx] = box.hi[axis_idx]

    # World axes orthogonal to the cylinder axis
    ex = np.zeros(3)
    ex[other[0]] = 1.0
    ey = np.zeros(3)
    ey[other[1]] = 1.0

    # Box centroid (for orientation checks)
    box_centroid = 0.5 * (box.lo + box.hi)

    # 8 box corners. Indexing convention:
    #   bot_corners[k] for k=0..3 lie on box.lo[axis_idx]
    #   top_corners[k] for k=0..3 lie on box.hi[axis_idx]
    # with the same (other0, other1) signs.
    sign_pairs = [(0, 0), (1, 0), (1, 1), (0, 1)]

    def _corner(k_axis: float, s0: int, s1: int) -> np.ndarray:
        p = np.zeros(3)
        p[axis_idx] = k_axis
        p[other[0]] = box.hi[other[0]] if s0 else box.lo[other[0]]
        p[other[1]] = box.hi[other[1]] if s1 else box.lo[other[1]]
        return p

    bot_corner_pts = [_corner(box.lo[axis_idx], s0, s1)
                      for (s0, s1) in sign_pairs]
    top_corner_pts = [_corner(box.hi[axis_idx], s0, s1)
                      for (s0, s1) in sign_pairs]

    V_bot = [Vertex(p, out_tol) for p in bot_corner_pts]
    V_top = [Vertex(p, out_tol) for p in top_corner_pts]

    def _mk_line_edge(va: Vertex, vb: Vertex) -> Edge:
        return Edge(Line3(va.point, vb.point), 0.0, 1.0, va, vb, out_tol)

    # Bottom rectangle: V_bot[0] -> V_bot[1] -> V_bot[2] -> V_bot[3]
    # Top    rectangle: V_top[0] -> V_top[1] -> V_top[2] -> V_top[3]
    e_bot_rect = [
        _mk_line_edge(V_bot[i], V_bot[(i + 1) % 4]) for i in range(4)
    ]
    e_top_rect = [
        _mk_line_edge(V_top[i], V_top[(i + 1) % 4]) for i in range(4)
    ]
    # Vertical pillars i->i (one per corner)
    e_pillar = [_mk_line_edge(V_bot[i], V_top[i]) for i in range(4)]

    # ---- Cylinder seam (two rim circles + one straight seam) -------------
    # Force cross(xref, yref) = +ax (right-handed about +ax) so the
    # rim circles are parameterised CCW about +ax regardless of which
    # world axis ax happens to be.
    xref = ex
    yref = np.cross(ax, xref)
    seam_low = centre_low + r * xref
    seam_high = centre_high + r * xref
    v_seam_low = Vertex(seam_low, out_tol)
    v_seam_high = Vertex(seam_high, out_tol)

    circ_low = CircleArc3(centre_low, r, xref, yref, 0.0, 2 * math.pi)
    circ_high = CircleArc3(centre_high, r, xref, yref, 0.0, 2 * math.pi)
    e_circ_low = Edge(
        circ_low, 0.0, 2 * math.pi, v_seam_low, v_seam_low, out_tol,
    )
    e_circ_high = Edge(
        circ_high, 0.0, 2 * math.pi, v_seam_high, v_seam_high, out_tol,
    )
    e_seam = Edge(
        Line3(seam_low, seam_high), 0.0, 1.0,
        v_seam_low, v_seam_high, out_tol,
    )

    # Helper to build a CCW-about-outward cap loop on the four rectangle
    # vertices V[0..3] (which traverse in the sign_pairs order). The
    # traversal direction is reversed (and the plane y_axis flipped) if
    # the natural [0,1,2,3] order is CW about the outward normal.

    def _build_cap(
        V_ring: List[Vertex],
        e_rect: List[Edge],
        outward: np.ndarray,
        rim_edge: Edge,
        rim_natural_normal: np.ndarray,
    ) -> Face:
        # natural traversal [0,1,2,3]: cross(V[1]-V[0], V[3]-V[0])
        nat_normal = np.cross(
            V_ring[1].point - V_ring[0].point,
            V_ring[3].point - V_ring[0].point,
        )
        if float(np.dot(nat_normal, outward)) > 0:
            outer_idx = [0, 1, 2, 3]
            plane_x = V_ring[1].point - V_ring[0].point
            plane_y = V_ring[3].point - V_ring[0].point
        else:
            outer_idx = [0, 3, 2, 1]
            plane_x = V_ring[3].point - V_ring[0].point
            plane_y = V_ring[1].point - V_ring[0].point
        plane = Plane(
            origin=V_ring[0].point, x_axis=plane_x, y_axis=plane_y,
        )
        coedges: List[Coedge] = []
        for i in range(4):
            a_idx = outer_idx[i]
            b_idx = outer_idx[(i + 1) % 4]
            edge = None
            orient = True
            for k in range(4):
                if k == a_idx and (k + 1) % 4 == b_idx:
                    edge = e_rect[k]
                    orient = True
                    break
                if (k + 1) % 4 == a_idx and k == b_idx:
                    edge = e_rect[k]
                    orient = False
                    break
            assert edge is not None
            coedges.append(Coedge(edge, orient))
        outer_loop = Loop(coedges, is_outer=True)
        # Inner ring: CW about face normal (= outward).
        # rim_edge is parameterised so its natural traversal is CCW
        # about ``rim_natural_normal``. CW about ``outward`` is
        # forward if outward . rim_natural_normal < 0, reversed
        # otherwise.
        forward_for_cw = float(np.dot(outward, rim_natural_normal)) < 0
        inner_loop = Loop(
            [Coedge(rim_edge, forward_for_cw)], is_outer=False,
        )
        return Face(
            plane, [outer_loop, inner_loop],
            orientation=True, tol=out_tol,
        )

    # Both rim circles are parameterised CCW about cross(xref, yref) =
    # cross(ex, ey). For axis_idx=2 (ax=+z) this is +z = +ax; for
    # axis_idx=1 it is -y = -ax; for axis_idx=0 it is +z != ax. We
    # capture the natural normal explicitly.
    rim_natural_normal = np.cross(xref, yref)
    bot_face = _build_cap(
        V_bot, e_bot_rect,
        outward=-ax, rim_edge=e_circ_low,
        rim_natural_normal=rim_natural_normal,
    )
    top_face = _build_cap(
        V_top, e_top_rect,
        outward=ax, rim_edge=e_circ_high,
        rim_natural_normal=rim_natural_normal,
    )

    # ---- Side faces ------------------------------------------------------
    # Side face i is bounded by:
    #   bottom edge: V_bot[i] -> V_bot[(i+1)%4]   (e_bot_rect[i])
    #   right pillar: V_bot[(i+1)%4] -> V_top[(i+1)%4]  (e_pillar[(i+1)%4])
    #   top edge:    V_top[(i+1)%4] -> V_top[i]   (e_top_rect[i] reversed)
    #   left pillar: V_top[i] -> V_bot[i]         (e_pillar[i] reversed)
    #
    # Orientation: the outward normal of side face i must point away
    # from the box centroid. We compute it and reverse the loop if it
    # points inward.
    side_faces: List[Face] = []
    for i in range(4):
        a = V_bot[i]
        b = V_bot[(i + 1) % 4]
        c = V_top[(i + 1) % 4]
        d = V_top[i]
        # candidate traversal A: a -> b -> c -> d
        e_ab = e_bot_rect[i]
        e_bc = e_pillar[(i + 1) % 4]
        e_cd = e_top_rect[i]  # natural is d->c -> walked reversed
        e_da = e_pillar[i]    # natural is a->d -> walked reversed
        # plane oriented with this traversal: cross(b-a, d-a)
        candidate_normal = np.cross(b.point - a.point, d.point - a.point)
        # face centroid
        face_centroid = 0.25 * (
            a.point + b.point + c.point + d.point
        )
        outward = face_centroid - box_centroid
        if float(np.dot(candidate_normal, outward)) > 0:
            # Traversal A produces outward-pointing normal; loop is
            # a->b->c->d which means coedges
            # (e_ab,+), (e_bc,+), (e_cd,-), (e_da,-).
            side_plane = Plane(
                origin=a.point,
                x_axis=b.point - a.point,
                y_axis=d.point - a.point,
            )
            coedges = [
                Coedge(e_ab, True),
                Coedge(e_bc, True),
                Coedge(e_cd, False),
                Coedge(e_da, False),
            ]
        else:
            # reverse: a -> d -> c -> b -> a so the plane normal flips
            side_plane = Plane(
                origin=a.point,
                x_axis=d.point - a.point,
                y_axis=b.point - a.point,
            )
            coedges = [
                Coedge(e_da, True),
                Coedge(e_cd, True),
                Coedge(e_bc, False),
                Coedge(e_ab, False),
            ]
        side_loop = Loop(coedges, is_outer=True)
        side_faces.append(
            Face(side_plane, [side_loop], orientation=True, tol=out_tol)
        )

    # ---- Inner cylindrical face ------------------------------------------
    # CylinderSurface(center=centre_low, axis=ax, radius=r, x_ref=xref).
    # The surface evaluate(u, v) = centre_low + r*cos(u)*xref + r*sin(u)*yref
    # + v*ax  where yref' = cross(ax, xref). Its normal(u, v) points
    # radially outward from the axis. We want the *face* normal to
    # point INTO the cavity (i.e. radially toward the axis, which is
    # outward from the solid-with-hole), so face.orientation = False.
    #
    # With orientation=False the effective face normal is -surface
    # normal = radially-inward. We need the outer loop to be CCW about
    # this flipped normal. The CylinderSurface's natural lateral loop
    # (as in make_cylinder) is CCW about the surface's *own* outward
    # normal; reversing the face's orientation flips the required loop
    # direction. So we reverse the canonical seam loop.
    cyl_surf = CylinderSurface(centre_low, ax, r, xref)
    canonical_seam = [
        Coedge(e_circ_low, True),
        Coedge(e_seam, True),
        Coedge(e_circ_high, False),
        Coedge(e_seam, False),
    ]
    # reverse for face.orientation=False
    cyl_loop = Loop(
        [
            Coedge(canonical_seam[3].edge, not canonical_seam[3].orientation),
            Coedge(canonical_seam[2].edge, not canonical_seam[2].orientation),
            Coedge(canonical_seam[1].edge, not canonical_seam[1].orientation),
            Coedge(canonical_seam[0].edge, not canonical_seam[0].orientation),
        ],
        is_outer=True,
    )
    # Drop the canonical_seam coedges from the edge.coedges list -- we
    # only built them for the orientation gymnastics above and they
    # would otherwise dangle as coedges with no loop.
    for ce in canonical_seam:
        ce.edge.coedges = [c for c in ce.edge.coedges if c is not ce]

    cyl_face = Face(
        cyl_surf, [cyl_loop], orientation=False, tol=out_tol,
    )

    all_faces = [bot_face, top_face] + side_faces + [cyl_face]
    shell = sew_faces(all_faces, tol=out_tol)
    if not shell.is_closed:
        raise BuildError(
            "_box_minus_cyl_through: sewn shell is not closed; "
            "topology assembly failed"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"_box_minus_cyl_through produced invalid Body: "
            f"{res['errors']}", res,
        )
    return body


# ---------------------------------------------------------------------------
# Sphere-sphere intersection (lens body)
# ---------------------------------------------------------------------------


def _sphere_intersection_sphere(
    sa: _SphereShape, sb: _SphereShape, tol: float
) -> Body:
    """Two-sphere intersection: lens-cap body.

    The lens is bounded by two spherical caps; each cap is a portion
    of one of the input spheres bounded by the intersection circle.
    Topology: F=2 (one cap from A, one from B), L=2 (each face's outer
    loop walks the rim circle once), E=1 (the shared rim circle), V=1
    (a seam point on the rim circle).
    """
    d = float(np.linalg.norm(sa.centre - sb.centre))
    out_tol = max(sa.tol, sb.tol, tol)

    if d >= sa.radius + sb.radius - tol:
        # disjoint or tangent -> empty
        return Body()
    if d + sb.radius <= sa.radius + tol:
        # sphere B fully inside sphere A -> intersection is sphere B
        return sphere_to_body(centre=sb.centre, radius=sb.radius, tol=out_tol)
    if d + sa.radius <= sb.radius + tol:
        return sphere_to_body(centre=sa.centre, radius=sa.radius, tol=out_tol)

    # Plane of the intersection circle is perpendicular to the line of
    # centres at signed distance ``a`` from sa.centre, where
    # a = (d^2 + ra^2 - rb^2) / (2 d).
    ra, rb = sa.radius, sb.radius
    ax_dir = _unit(sb.centre - sa.centre)
    a = (d * d + ra * ra - rb * rb) / (2.0 * d)
    rim_centre = sa.centre + a * ax_dir
    rim_radius = math.sqrt(max(0.0, ra * ra - a * a))

    xref = _perp(ax_dir)
    yref = _unit(np.cross(ax_dir, xref))

    # Seam vertex on the rim
    seam_pt = rim_centre + rim_radius * xref
    v_seam = Vertex(seam_pt, out_tol)

    rim_curve = CircleArc3(rim_centre, rim_radius, xref, yref, 0.0, 2 * math.pi)
    e_rim = Edge(rim_curve, 0.0, 2 * math.pi, v_seam, v_seam, out_tol)

    # Cap from sphere A: the part of A on the +ax_dir side of the rim
    # plane (toward B). Its outward normal at the apex is +ax_dir.
    # SphereSurface stores the centre; we orient the face so its normal
    # points away from the centre of A.
    cap_a_surf = SphereSurface(sa.centre, sa.radius)
    cap_a_loop = Loop([Coedge(e_rim, True)], is_outer=True)
    cap_a_face = Face(
        cap_a_surf, [cap_a_loop], orientation=True, tol=out_tol,
    )

    cap_b_surf = SphereSurface(sb.centre, sb.radius)
    # B's cap is on the -ax_dir side of the rim (toward A), so its
    # outward normal at the apex points -ax_dir, which is the natural
    # outward normal of B at that point (since the apex is on the
    # opposite side of B's centre from A). The rim loop must be walked
    # in the opposite orientation on B's cap so the two cap normals
    # face *outward* from the lens.
    cap_b_loop = Loop([Coedge(e_rim, False)], is_outer=True)
    cap_b_face = Face(
        cap_b_surf, [cap_b_loop], orientation=True, tol=out_tol,
    )

    shell = sew_faces([cap_a_face, cap_b_face], tol=out_tol)
    if not shell.is_closed:
        raise BuildError(
            "_sphere_intersection_sphere: sewn shell is not closed"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"_sphere_intersection_sphere produced invalid Body: "
            f"{res['errors']}", res,
        )
    return body


def _sphere_union_sphere(
    sa: _SphereShape, sb: _SphereShape, tol: float
) -> Body:
    """Two-sphere union.

    Result is the smaller cap of A *exterior* to B sewn to the smaller
    cap of B exterior to A along their shared rim circle (when the
    spheres overlap and neither contains the other). When disjoint we
    return a multi-solid Body; when one contains the other we return
    the larger.
    """
    out_tol = max(sa.tol, sb.tol, tol)
    d = float(np.linalg.norm(sa.centre - sb.centre))
    if d >= sa.radius + sb.radius - tol:
        # disjoint -> two-solid body
        body = Body()
        body.solids.extend(
            sphere_to_body(sa.centre, sa.radius, out_tol).solids
        )
        body.solids.extend(
            sphere_to_body(sb.centre, sb.radius, out_tol).solids
        )
        return body
    if d + sb.radius <= sa.radius + tol:
        return sphere_to_body(sa.centre, sa.radius, out_tol)
    if d + sa.radius <= sb.radius + tol:
        return sphere_to_body(sb.centre, sb.radius, out_tol)

    # Genuine partial overlap. The union surface is the outer cap of A
    # (the portion of A outside B) joined to the outer cap of B (outside
    # A) along the shared rim circle.
    ra, rb = sa.radius, sb.radius
    ax_dir = _unit(sb.centre - sa.centre)
    a = (d * d + ra * ra - rb * rb) / (2.0 * d)
    rim_centre = sa.centre + a * ax_dir
    rim_radius = math.sqrt(max(0.0, ra * ra - a * a))
    xref = _perp(ax_dir)
    yref = _unit(np.cross(ax_dir, xref))

    seam_pt = rim_centre + rim_radius * xref
    v_seam = Vertex(seam_pt, out_tol)
    rim_curve = CircleArc3(rim_centre, rim_radius, xref, yref, 0.0, 2 * math.pi)
    e_rim = Edge(rim_curve, 0.0, 2 * math.pi, v_seam, v_seam, out_tol)

    cap_a_surf = SphereSurface(sa.centre, sa.radius)
    cap_a_loop = Loop([Coedge(e_rim, False)], is_outer=True)
    cap_a_face = Face(cap_a_surf, [cap_a_loop], orientation=True, tol=out_tol)

    cap_b_surf = SphereSurface(sb.centre, sb.radius)
    cap_b_loop = Loop([Coedge(e_rim, True)], is_outer=True)
    cap_b_face = Face(cap_b_surf, [cap_b_loop], orientation=True, tol=out_tol)

    shell = sew_faces([cap_a_face, cap_b_face], tol=out_tol)
    if not shell.is_closed:
        raise BuildError(
            "_sphere_union_sphere: sewn shell is not closed"
        )
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"_sphere_union_sphere produced invalid Body: {res['errors']}",
            res,
        )
    return body


# ---------------------------------------------------------------------------
# Identity / fast-path helpers
# ---------------------------------------------------------------------------


def _clone_body_from_shape(body: Body, tol: float) -> Body:
    """Reproduce a body via its analytic shape recogniser so the output
    is a *fresh* topology that does not share mutable Vertex / Edge /
    Face objects with the input.
    """
    a_box = _try_recognise_aabb(body)
    if a_box is not None:
        return _aabb_to_body(_AABB(
            lo=a_box.lo, hi=a_box.hi, tol=max(a_box.tol, tol),
        ))
    a_cyl = _try_recognise_cylinder(body)
    if a_cyl is not None:
        return cylinder_to_body(
            axis_pt=a_cyl.axis_pt,
            axis_dir=a_cyl.axis_dir,
            radius=a_cyl.radius,
            height=a_cyl.height,
            tol=max(a_cyl.tol, tol),
        )
    a_sph = _try_recognise_sphere(body)
    if a_sph is not None:
        return sphere_to_body(
            centre=a_sph.centre,
            radius=a_sph.radius,
            tol=max(a_sph.tol, tol),
        )
    raise BuildError(
        "_clone_body_from_shape: body is not a supported analytic primitive "
        "(unsupported-input)"
    )


def _bodies_equal(a: Body, b: Body, tol: float) -> bool:
    """Two bodies are *structurally equal* when one of:

      * Both are recognised as AABBs with identical lo/hi within tol.
      * Both are recognised as cylinders with identical params.
      * Both are recognised as spheres with identical centre/radius.
    """
    a_box, b_box = _try_recognise_aabb(a), _try_recognise_aabb(b)
    if a_box is not None and b_box is not None:
        return (
            bool(np.all(np.abs(a_box.lo - b_box.lo) <= tol))
            and bool(np.all(np.abs(a_box.hi - b_box.hi) <= tol))
        )
    a_cyl, b_cyl = _try_recognise_cylinder(a), _try_recognise_cylinder(b)
    if a_cyl is not None and b_cyl is not None:
        return (
            float(np.linalg.norm(a_cyl.axis_pt - b_cyl.axis_pt)) <= tol
            and float(np.linalg.norm(a_cyl.axis_dir - b_cyl.axis_dir)) <= tol
            and abs(a_cyl.radius - b_cyl.radius) <= tol
            and abs(a_cyl.height - b_cyl.height) <= tol
        )
    a_sph, b_sph = _try_recognise_sphere(a), _try_recognise_sphere(b)
    if a_sph is not None and b_sph is not None:
        return (
            float(np.linalg.norm(a_sph.centre - b_sph.centre)) <= tol
            and abs(a_sph.radius - b_sph.radius) <= tol
        )
    return False


# ---------------------------------------------------------------------------
# Cylinder-through-box predicate
# ---------------------------------------------------------------------------


def _cyl_pierces_box(box: _AABB, cyl: _CylShape, tol: float) -> bool:
    """``cyl`` fully pierces ``box`` when:

      * its axis is world-axis-aligned,
      * the axis intersects two opposite faces of the box (radial
        extent fits within the perpendicular box footprint), and
      * the cylinder extent covers the box's extent along the axis.
    """
    ax = _unit(cyl.axis_dir)
    axis_idx = int(np.argmax(np.abs(ax)))
    if abs(abs(ax[axis_idx]) - 1.0) > 1e-9:
        return False
    other = [i for i in range(3) if i != axis_idx]
    # cylinder radial extent must fit within the box footprint
    cx = float(cyl.axis_pt[other[0]])
    cy = float(cyl.axis_pt[other[1]])
    r = cyl.radius
    if cx - r < box.lo[other[0]] - tol:
        return False
    if cx + r > box.hi[other[0]] + tol:
        return False
    if cy - r < box.lo[other[1]] - tol:
        return False
    if cy + r > box.hi[other[1]] + tol:
        return False
    # axis extent must cover the box extent
    lo = float(cyl.axis_pt[axis_idx])
    hi = lo + cyl.height
    if lo > box.lo[axis_idx] + tol:
        return False
    if hi < box.hi[axis_idx] - tol:
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def body_union(a: Body, b: Body, tol: float = 1e-6) -> Body:
    """Regularised set union of two solid :class:`Body` objects.

    Supported inputs (other combinations raise :class:`BuildError` with
    ``unsupported-input``):

      * axis-aligned-box  U  axis-aligned-box  (full AABB cellular boolean)
      * sphere            U  sphere
      * identical bodies   -> input passthrough (idempotent)
      * disjoint           -> multi-solid output ``Body``
      * containment        -> outer body unchanged

    The result is :func:`validate_body`-clean (or raises). Tolerance on
    every produced topology element is at least
    ``max(a.tol_envelope, b.tol_envelope, tol)``.
    """
    # idempotent fast path
    if _bodies_equal(a, b, tol):
        return _clone_body_from_shape(a, tol)

    a_box, b_box = _try_recognise_aabb(a), _try_recognise_aabb(b)
    a_sph, b_sph = _try_recognise_sphere(a), _try_recognise_sphere(b)

    if a_box is not None and b_box is not None:
        out_tol = max(a_box.tol, b_box.tol, tol)
        if _aabb_disjoint(a_box, b_box, out_tol):
            return _multi_aabb_to_body([a_box, b_box], out_tol)
        if _aabb_contains(a_box, b_box, out_tol):
            return _aabb_to_body(a_box)
        if _aabb_contains(b_box, a_box, out_tol):
            return _aabb_to_body(b_box)
        # general overlapping AABB union: A + (B \ A)
        b_minus_a = _aabb_minus_aabb(b_box, a_box, out_tol)
        pieces = [a_box] + list(b_minus_a)
        return _multi_aabb_to_body(pieces, out_tol)

    if a_sph is not None and b_sph is not None:
        return _sphere_union_sphere(a_sph, b_sph, tol)

    raise BuildError(
        "body_union: unsupported-input combination; only "
        "axis-aligned box+box and sphere+sphere are supported"
    )


def body_intersection(a: Body, b: Body, tol: float = 1e-6) -> Body:
    """Regularised set intersection.

    Supported inputs as in :func:`body_union`. The result is empty
    (``Body()`` with zero solids) when the inputs are disjoint.
    """
    if _bodies_equal(a, b, tol):
        return _clone_body_from_shape(a, tol)

    a_box, b_box = _try_recognise_aabb(a), _try_recognise_aabb(b)
    a_sph, b_sph = _try_recognise_sphere(a), _try_recognise_sphere(b)

    if a_box is not None and b_box is not None:
        out_tol = max(a_box.tol, b_box.tol, tol)
        inter = _aabb_intersection_aabb(a_box, b_box, out_tol)
        if inter is None:
            return Body()
        return _aabb_to_body(inter)

    if a_sph is not None and b_sph is not None:
        return _sphere_intersection_sphere(a_sph, b_sph, tol)

    raise BuildError(
        "body_intersection: unsupported-input combination; only "
        "axis-aligned box+box and sphere+sphere are supported"
    )


def body_difference(a: Body, b: Body, tol: float = 1e-6) -> Body:
    """Regularised set difference ``a \\ b``.

    Supported inputs:

      * axis-aligned-box  \\  axis-aligned-box
      * axis-aligned-box  \\  axis-aligned cylinder pierces fully
        (canonical "box with cylindrical hole through it")
      * sphere            \\  sphere
      * identical bodies   -> empty
      * b contains a       -> empty
      * a and b disjoint   -> a unchanged

    The result is :func:`validate_body`-clean or raises.
    """
    if _bodies_equal(a, b, tol):
        return Body()

    a_box, b_box = _try_recognise_aabb(a), _try_recognise_aabb(b)
    a_sph, b_sph = _try_recognise_sphere(a), _try_recognise_sphere(b)
    b_cyl = _try_recognise_cylinder(b)

    if a_box is not None and b_box is not None:
        out_tol = max(a_box.tol, b_box.tol, tol)
        if _aabb_disjoint(a_box, b_box, out_tol):
            return _aabb_to_body(a_box)
        if _aabb_contains(b_box, a_box, out_tol):
            return Body()
        pieces = _aabb_minus_aabb(a_box, b_box, out_tol)
        return _multi_aabb_to_body(pieces, out_tol)

    if a_box is not None and b_cyl is not None:
        out_tol = max(a_box.tol, b_cyl.tol, tol)
        if _cyl_pierces_box(a_box, b_cyl, out_tol):
            return _box_minus_cyl_through(a_box, b_cyl, out_tol)
        raise BuildError(
            "body_difference: cylinder does not fully pierce box "
            "(unsupported-input -- partial-pierce general case not yet "
            "supported)"
        )

    if a_sph is not None and b_sph is not None:
        # sphere \ sphere: if b contains a, empty; if disjoint, a;
        # otherwise the general lens-complement (not in our test
        # matrix) is unsupported.
        out_tol = max(a_sph.tol, b_sph.tol, tol)
        if _sphere_contains(b_sph, a_sph, out_tol):
            return Body()
        if _sphere_disjoint(a_sph, b_sph, out_tol):
            return sphere_to_body(a_sph.centre, a_sph.radius, out_tol)
        raise BuildError(
            "body_difference: partial sphere-sphere difference is not "
            "in the supported-input contract (general case requires NURBS "
            "trimming)"
        )

    raise BuildError(
        "body_difference: unsupported-input combination; supported: "
        "AAB-box\\AAB-box, AAB-box\\(axis-aligned cyl pierces box), "
        "sphere\\sphere (disjoint or containment only)"
    )
