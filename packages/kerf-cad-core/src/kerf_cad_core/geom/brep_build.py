"""Canonical bridge from analytic-geometry verbs to validated B-rep ``Body``.

This module is the **production** path that consumers should reach for when
they need real, structurally-validated topology around their geometry. The
constructors in :mod:`kerf_cad_core.geom.brep` (``make_box``,
``make_cylinder``, ``make_sphere`` ...) remain as in-source demonstrations
that the topology contract is satisfiable; everything in *this* file is
the user-facing builder layer that:

  * takes geometric verbs (a NURBS surface, an analytic ``Plane`` /
    ``CylinderSurface`` / ``SphereSurface`` / ``TorusSurface``, a quartet
    of bounding curves, or a primitive description),
  * stitches the topology hierarchy
    ``Vertex -> Edge -> Coedge -> Loop -> Face -> Shell -> Solid -> Body``,
  * and ends every public constructor with an internal ``validate_body``
    assertion, so the keystone now *guards real geometry*.

Design notes
------------

* No existing geom module is modified. We only consume the frozen public
  API of :mod:`brep` (``Vertex``, ``Edge``, ``Coedge``, ``Loop``, ``Face``,
  ``Shell``, ``Solid``, ``Body``, the analytic adapters, and
  ``validate_body``).

* For a NURBS surface ``surface_to_face`` slices the parametric domain on
  its four boundaries into 4 isocurves and 4 corner vertices. The
  resulting outer loop is checked to be CCW with respect to the surface
  normal at the central sample; if it is CW we reverse it. This makes
  ``validate_body`` clean for any sufficiently regular bicubic patch.

* For an explicit ``outer_loop_curves`` sequence we treat the provided
  curves as already-bounding the surface and use their endpoint
  coincidence (within ``tol``) to share vertices.

* ``surfaces_to_shell`` performs an O(F + V + E) sew: vertices within
  ``sew_tol`` collapse to a single representative; edges that share both
  endpoint-representatives (and have coincident midpoint samples) collapse
  similarly, with the original two coedges re-pointed at the shared edge.
  After sewing we recompute ``is_closed`` exactly by manifold count: a
  closed shell is one where every edge is used by exactly two coedges of
  opposite orientation.

Every public constructor here ends with an internal ``validate_body(...)``
check and raises ``BuildError`` on any error.
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
    SphereSurface,
    Solid,
    TorusSurface,
    Vertex,
    validate_body,
)


# ---------------------------------------------------------------------------
# Public errors
# ---------------------------------------------------------------------------


class BuildError(RuntimeError):
    """Raised when a brep_build constructor produces invalid topology.

    The error carries the ``validate_body`` payload so callers can inspect
    the structured ``errors`` list rather than just a string.
    """

    def __init__(self, msg: str, payload: Optional[dict] = None) -> None:
        super().__init__(msg)
        self.payload = payload or {"ok": False, "errors": [msg]}


# ---------------------------------------------------------------------------
# Lightweight isocurve adapter for NurbsSurface / analytic surfaces
# ---------------------------------------------------------------------------


@dataclass
class _SurfaceIsoCurve:
    """A boundary isocurve of a parametric surface.

    ``axis`` is ``'u'`` if we fix ``v`` and sweep ``u``, ``'v'`` otherwise.
    ``t0`` / ``t1`` are the parametric range of the *swept* coordinate
    (matching the edge's ``[t0, t1]``).
    """

    surface: object
    axis: str
    fixed: float
    t0: float
    t1: float

    def evaluate(self, t: float) -> np.ndarray:
        if self.axis == "u":
            return np.asarray(self.surface.evaluate(t, self.fixed), dtype=float)
        return np.asarray(self.surface.evaluate(self.fixed, t), dtype=float)

    def derivative(self, t: float, order: int = 1) -> np.ndarray:  # noqa: ARG002
        h = 1e-6
        a = self.evaluate(t - h)
        b = self.evaluate(t + h)
        return (b - a) / (2.0 * h)


# ---------------------------------------------------------------------------
# Parameter-range introspection
# ---------------------------------------------------------------------------


def _surface_param_box(surface: object) -> Tuple[float, float, float, float]:
    """Return ``(u0, u1, v0, v1)`` for any surface we know how to bound.

    Handles ``NurbsSurface`` (proper knot range), the analytic ``Plane``
    (unit square), ``CylinderSurface`` (``u`` in [0, 2pi], ``v`` in [0, 1]
    -- caller passes the correct height as a separate primitive
    constructor), ``SphereSurface`` (longitude / latitude), and
    ``TorusSurface`` (two periodic angles). For a fully arbitrary surface
    with no ``param_range`` hint we return the unit square.
    """
    if hasattr(surface, "knots_u") and hasattr(surface, "knots_v"):
        ku, kv = surface.knots_u, surface.knots_v
        du, dv = surface.degree_u, surface.degree_v
        return (
            float(ku[du]), float(ku[-(du + 1)]),
            float(kv[dv]), float(kv[-(dv + 1)]),
        )
    if isinstance(surface, Plane):
        return 0.0, 1.0, 0.0, 1.0
    if isinstance(surface, CylinderSurface):
        return 0.0, 2.0 * math.pi, 0.0, 1.0
    if isinstance(surface, SphereSurface):
        return 0.0, 2.0 * math.pi, -math.pi / 2.0, math.pi / 2.0
    if isinstance(surface, TorusSurface):
        return 0.0, 2.0 * math.pi, 0.0, 2.0 * math.pi
    pr = getattr(surface, "param_range", None)
    if pr is not None:
        u0, u1, v0, v1 = pr
        return float(u0), float(u1), float(v0), float(v1)
    return 0.0, 1.0, 0.0, 1.0


def _surface_normal_at(surface: object, u: float, v: float) -> np.ndarray:
    if hasattr(surface, "normal"):
        n = np.asarray(surface.normal(u, v), dtype=float)
    else:
        h = 1e-6
        p = np.asarray(surface.evaluate(u, v), dtype=float)
        du = np.asarray(surface.evaluate(u + h, v), dtype=float) - p
        dv = np.asarray(surface.evaluate(u, v + h), dtype=float) - p
        n = np.cross(du, dv)
    nrm = float(np.linalg.norm(n))
    return n / nrm if nrm > 1e-14 else n


# ---------------------------------------------------------------------------
# Outer-loop construction
# ---------------------------------------------------------------------------


def _natural_boundary(
    surface: object, tol: float
) -> Tuple[List[Vertex], List[Tuple[Edge, bool]]]:
    """Build 4 corner vertices + 4 isocurve (edge, orientation) pairs for a
    parametric box.

    Traversal order: (u0,v0) -> (u1,v0) -> (u1,v1) -> (u0,v1) -> (u0,v0).
    Edges are returned as ``(edge, orientation)`` pairs already aligned to
    that traversal direction.
    """
    u0, u1, v0, v1 = _surface_param_box(surface)
    P00 = np.asarray(surface.evaluate(u0, v0), dtype=float)
    P10 = np.asarray(surface.evaluate(u1, v0), dtype=float)
    P11 = np.asarray(surface.evaluate(u1, v1), dtype=float)
    P01 = np.asarray(surface.evaluate(u0, v1), dtype=float)
    v00 = Vertex(P00, tol)
    v10 = Vertex(P10, tol)
    v11 = Vertex(P11, tol)
    v01 = Vertex(P01, tol)
    # Each edge is stored in its natural parametric direction; we record
    # whether the traversal walks the edge forwards (True) or backwards.
    e_bot = Edge(_SurfaceIsoCurve(surface, "u", v0, u0, u1),
                 u0, u1, v00, v10, tol)        # walked v00->v10 = forwards
    e_rgt = Edge(_SurfaceIsoCurve(surface, "v", u1, v0, v1),
                 v0, v1, v10, v11, tol)        # walked v10->v11 = forwards
    e_top = Edge(_SurfaceIsoCurve(surface, "u", v1, u0, u1),
                 u0, u1, v01, v11, tol)        # walked v11->v01 = backwards
    e_lft = Edge(_SurfaceIsoCurve(surface, "v", u0, v0, v1),
                 v0, v1, v00, v01, tol)        # walked v01->v00 = backwards
    return (
        [v00, v10, v11, v01],
        [(e_bot, True), (e_rgt, True), (e_top, False), (e_lft, False)],
    )


def _curve_endpoint_param_range(curve: object) -> Tuple[float, float]:
    """Best-effort ``(t0, t1)`` for an arbitrary curve."""
    for attr in ("param_range", "_param_range"):
        pr = getattr(curve, attr, None)
        if pr is not None:
            return float(pr[0]), float(pr[1])
    if hasattr(curve, "knots") and hasattr(curve, "degree"):
        k = np.asarray(curve.knots, dtype=float)
        d = int(curve.degree)
        return float(k[d]), float(k[-(d + 1)])
    return 0.0, 1.0


def _share_or_make_vertex(
    point: np.ndarray, pool: List[Vertex], tol: float
) -> Vertex:
    for v in pool:
        if float(np.linalg.norm(v.point - point)) <= max(v.tol, tol):
            return v
    v = Vertex(np.asarray(point, dtype=float), tol)
    pool.append(v)
    return v


def _explicit_loop(
    curves: Sequence[object], tol: float
) -> Tuple[List[Vertex], List[Tuple[Edge, bool]]]:
    """Build a closed chain of vertices+edges from caller-supplied curves.

    Endpoints within ``tol`` are merged into a single ``Vertex``; the last
    edge's endpoint is re-pointed at the first vertex if they coincide so
    the loop closes cleanly. Edges are returned as ``(edge, orientation)``
    pairs; orientation is always ``True`` for explicit curves because we
    assume the caller has already ordered them in traversal direction.
    """
    if len(curves) < 1:
        raise BuildError("explicit outer loop must have at least one curve")
    pool: List[Vertex] = []
    edges: List[Tuple[Edge, bool]] = []
    for c in curves:
        t0, t1 = _curve_endpoint_param_range(c)
        p0 = np.asarray(c.evaluate(t0), dtype=float)
        p1 = np.asarray(c.evaluate(t1), dtype=float)
        v0 = _share_or_make_vertex(p0, pool, tol)
        v1 = _share_or_make_vertex(p1, pool, tol)
        edges.append((Edge(c, t0, t1, v0, v1, tol), True))
    # close the loop: stitch last edge's v_end to first edge's v_start
    last_e, _ = edges[-1]
    first_e, _ = edges[0]
    if last_e.v_end is not first_e.v_start:
        if float(np.linalg.norm(
            last_e.v_end.point - first_e.v_start.point
        )) <= tol * 10.0:
            last_e.v_end = first_e.v_start
    return pool, edges


def _outer_loop_ccw(
    surface: object, edge_orients: Sequence[Tuple[Edge, bool]]
) -> Tuple[List[Coedge], bool]:
    """Build coedges traversing ``edge_orients`` and orient the loop CCW
    with respect to the surface normal at the surface centre.

    Returns ``(coedges, was_reversed)``. Each input pair already encodes
    the *intended* traversal direction (``orientation`` is the coedge
    direction relative to the edge's natural ``v_start -> v_end``).
    """
    coedges = [Coedge(e, o) for (e, o) in edge_orients]
    u0, u1, v0, v1 = _surface_param_box(surface)
    u_mid, v_mid = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
    n = _surface_normal_at(surface, u_mid, v_mid)
    pts: List[np.ndarray] = []
    for ce in coedges:
        p = np.asarray(ce.start_point(), dtype=float)
        if not pts or float(np.linalg.norm(p - pts[-1])) > 1e-12:
            pts.append(p)
    if len(pts) < 3:
        return coedges, False
    centroid = np.mean(pts, axis=0)
    area_vec = np.zeros(3)
    m = len(pts)
    for i in range(m):
        a = pts[i] - centroid
        b = pts[(i + 1) % m] - centroid
        area_vec += np.cross(a, b)
    signed = float(np.dot(area_vec, n) * 0.5)
    if signed >= 0:
        return coedges, False
    # CW with respect to the normal -> reverse traversal so coedges become
    # CCW. Reverse order + flip every orientation.
    rev = [(e, not o) for (e, o) in reversed(edge_orients)]
    coedges = [Coedge(e, o) for (e, o) in rev]
    return coedges, True


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def surface_to_face(
    surface: object,
    outer_loop_curves: Optional[Sequence[object]] = None,
    inner_loops: Optional[Sequence[Sequence[object]]] = None,
    tol: float = 1e-7,
) -> Face:
    """Wrap a parametric surface in a topologically-correct ``Face``.

    Parameters
    ----------
    surface
        Anything with ``evaluate(u, v)``. ``NurbsSurface`` and the analytic
        adapters in :mod:`brep` (``Plane`` / ``CylinderSurface`` /
        ``SphereSurface`` / ``TorusSurface``) all qualify.
    outer_loop_curves
        Optional ordered sequence of bounding 3D curves whose endpoint
        chain forms a closed loop around the face. When ``None`` the four
        natural parametric boundaries of the surface are used.
    inner_loops
        Optional list of inner (hole) loops; each is a sequence of curves.
    tol
        Tolerance for vertex sharing and face/edge tolerance fields.

    The produced face is wrapped in a transient single-face open
    ``Shell``/``Body`` and ``validate_body`` is asserted clean. Returns
    the unattached ``Face`` (the transient shell is discarded; the face's
    ``.shell`` reference is reset to ``None`` so callers can sew it into
    their own shell).
    """
    if outer_loop_curves is None:
        _verts, edge_orients = _natural_boundary(surface, tol)
    else:
        _verts, edge_orients = _explicit_loop(outer_loop_curves, tol)

    coedges, _ = _outer_loop_ccw(surface, edge_orients)
    outer = Loop(coedges, is_outer=True)
    face = Face(surface, [outer], orientation=True, tol=tol)

    if inner_loops:
        for ring_curves in inner_loops:
            _ring_verts, ring_edge_orients = _explicit_loop(ring_curves, tol)
            ring_coedges, _ = _outer_loop_ccw(surface, ring_edge_orients)
            # _outer_loop_ccw gives CCW; inner loops must be CW wrt normal
            ring_coedges = [Coedge(c.edge, not c.orientation) for c in
                            reversed(ring_coedges)]
            face.add_loop(Loop(ring_coedges, is_outer=False))

    # A bare Face is below the granularity of validate_body (which gates
    # on the *body-wide* Euler-Poincare residual). Run the same structural
    # / orientation / tolerance checks that validate_body performs, minus
    # the Euler residual (it only makes sense for closed bodies) and the
    # closed-shell manifold gate (this face is not yet in a shell).
    errors = _validate_face_local(face)
    if errors:
        raise BuildError(
            f"surface_to_face produced invalid Face: {errors}",
            {"ok": False, "errors": errors},
        )
    return face


def _validate_face_local(face: Face) -> List[str]:
    """Structural / orientation / tolerance check for a single Face.

    Mirrors checks 2/3/5/6 from :func:`brep.validate_body` (loop closure,
    outer-CCW & inner-CW, tolerance monotonicity, no dangling/duplicate
    coedges) but skips the body-level Euler-Poincare residual and the
    closed-shell 2-manifold gate.
    """
    from kerf_cad_core.geom.brep import _loop_signed_area_about_normal

    errs: List[str] = []
    outer = face.outer_loop()
    if outer is None:
        errs.append(f"face#{face.id} has no outer loop")
        return errs
    for lp in face.loops:
        if not lp.coedges:
            errs.append(f"face#{face.id} loop#{lp.id} has no coedges")
            continue
        n = len(lp.coedges)
        for i, ce in enumerate(lp.coedges):
            nxt = lp.coedges[(i + 1) % n]
            if ce.next is not nxt:
                errs.append(
                    f"face#{face.id} loop#{lp.id} coedge#{ce.id} "
                    "next link inconsistent"
                )
            etol = max(ce.edge.tol, nxt.edge.tol)
            gap = float(np.linalg.norm(ce.end_point() - nxt.start_point()))
            if gap > 10.0 * max(etol, 1e-9):
                errs.append(
                    f"face#{face.id} loop#{lp.id} open at coedge#{ce.id} "
                    f"(gap={gap:.3e} > tol)"
                )
            if ce.end_vertex() is not nxt.start_vertex():
                if not ce.end_vertex().coincident(nxt.start_vertex()):
                    errs.append(
                        f"face#{face.id} loop#{lp.id} vertex discontinuity "
                        f"at coedge#{ce.id}"
                    )
        # orientation
        signed = _loop_signed_area_about_normal(lp, face)
        if signed is not None:
            if lp is outer and signed < 0:
                errs.append(
                    f"face#{face.id} outer loop#{lp.id} is CW "
                    "(expected CCW wrt surface normal)"
                )
            if lp is not outer and signed > 0:
                errs.append(
                    f"face#{face.id} inner loop#{lp.id} is CCW "
                    "(expected CW wrt surface normal)"
                )
    # tolerance monotonicity
    for lp in face.loops:
        for ce in lp.coedges:
            e = ce.edge
            if e.tol < face.tol - 1e-15:
                errs.append(
                    f"tolerance inversion: edge#{e.id}.tol < face#{face.id}.tol"
                )
            for v in (e.v_start, e.v_end):
                if v.tol < e.tol - 1e-15:
                    errs.append(
                        f"tolerance inversion: vertex#{v.id}.tol < "
                        f"edge#{e.id}.tol"
                    )
    # duplicate coedge check
    for lp in face.loops:
        seen = set()
        for ce in lp.coedges:
            key = (id(ce.edge), ce.orientation)
            if key in seen:
                errs.append(
                    f"face#{face.id} loop#{lp.id} duplicate coedge for "
                    f"edge#{ce.edge.id} orientation={ce.orientation}"
                )
            seen.add(key)
    return errs


def surfaces_to_shell(
    faces: Sequence[Face],
    sew_tol: float = 1e-6,
) -> Shell:
    """Combine multiple ``Face``s into a sewn ``Shell``.

    Vertices within ``sew_tol`` of each other are merged into one shared
    ``Vertex``; edges whose both endpoint-representatives match (and whose
    midpoint samples coincide within ``sew_tol``) are merged so the two
    incident coedges share a single physical ``Edge``. After sewing,
    ``is_closed`` is set exactly: every edge must be used by exactly two
    coedges of opposite orientation.
    """
    if not faces:
        raise BuildError("surfaces_to_shell requires at least one face")

    # 1) build the union-find on vertices keyed by identity then by
    #    spatial coincidence within sew_tol
    all_vertices: List[Vertex] = []
    seen = set()
    for f in faces:
        for lp in f.loops:
            for ce in lp.coedges:
                for v in (ce.edge.v_start, ce.edge.v_end):
                    if id(v) not in seen:
                        seen.add(id(v))
                        all_vertices.append(v)

    # map id(vertex) -> representative Vertex (a key vertex per cluster)
    rep_of: dict = {}
    cluster_reps: List[Vertex] = []
    for v in all_vertices:
        found = None
        for rep in cluster_reps:
            if float(np.linalg.norm(v.point - rep.point)) <= sew_tol:
                found = rep
                break
        if found is None:
            cluster_reps.append(v)
            rep_of[id(v)] = v
        else:
            rep_of[id(v)] = found
            # vertex.tol monotonicity: a merged cluster's tol must be at
            # least as large as any constituent tol (BREP_CONTRACT §4.5)
            if v.tol > found.tol:
                found.tol = v.tol

    # 2) rewrite every edge's v_start / v_end to its representative; bump
    #    edge tol to be >= face tol of incident faces (tolerance
    #    monotonicity), and >= sew_tol so the loop-closure gap test in
    #    validate_body accepts cross-face seams.
    edges_seen: List[Edge] = []
    for f in faces:
        for lp in f.loops:
            for ce in lp.coedges:
                e = ce.edge
                e.v_start = rep_of[id(e.v_start)]
                e.v_end = rep_of[id(e.v_end)]
                if e not in edges_seen:
                    edges_seen.append(e)
                if e.tol < f.tol:
                    e.tol = f.tol
                if e.tol < sew_tol:
                    e.tol = sew_tol
                # vertex tol monotonicity wrt the (potentially bumped)
                # edge tol; the representative has already been bumped
                for v in (e.v_start, e.v_end):
                    if v.tol < e.tol:
                        v.tol = e.tol

    # 3) edge merging: two edges with the same endpoint-rep pair AND
    #    coincident midpoint samples collapse to one shared physical edge,
    #    and the two coedges are re-pointed onto the survivor.
    rep_map_edge: dict = {}  # id(edge) -> survivor Edge
    edge_clusters: List[Edge] = []
    for e in edges_seen:
        key_a = (id(e.v_start), id(e.v_end))
        key_b = (id(e.v_end), id(e.v_start))
        mid = 0.5 * (e.point(e.t0) + e.point(e.t1))
        survivor: Optional[Edge] = None
        for cand in edge_clusters:
            ck = (id(cand.v_start), id(cand.v_end))
            if ck != key_a and ck != key_b:
                continue
            cmid = 0.5 * (cand.point(cand.t0) + cand.point(cand.t1))
            if float(np.linalg.norm(mid - cmid)) <= sew_tol * 100.0:
                survivor = cand
                break
        if survivor is None:
            edge_clusters.append(e)
            rep_map_edge[id(e)] = e
        else:
            rep_map_edge[id(e)] = survivor

    # 4) repoint coedges, and update edge.coedges to reflect the survivor
    for f in faces:
        for lp in f.loops:
            for ce in lp.coedges:
                old = ce.edge
                new = rep_map_edge[id(old)]
                if new is not old:
                    # we may need to flip orientation if the survivor runs
                    # the other way round
                    if (
                        old.v_start is new.v_end
                        and old.v_end is new.v_start
                    ):
                        ce.orientation = not ce.orientation
                    ce.edge = new
                    if ce not in new.coedges:
                        new.coedges.append(ce)
                    # purge the old edge's stale coedge list
                    old.coedges = []

    # 5) decide closedness exactly: every edge used by exactly 2 coedges of
    #    opposite orientation
    use: dict = {}
    for f in faces:
        for lp in f.loops:
            for ce in lp.coedges:
                use.setdefault(id(ce.edge), []).append(ce)
    is_closed = True
    for ces in use.values():
        if len(ces) != 2 or ces[0].orientation == ces[1].orientation:
            is_closed = False
            break

    shell = Shell(list(faces), is_closed=is_closed)
    if is_closed:
        # Full validate_body path: a closed shell wrapped in a solid is a
        # legitimate target for the body-wide Euler-Poincare check.
        transient_body = Body(solids=[Solid([shell])])
        res = validate_body(transient_body)
        if not res["ok"]:
            raise BuildError(
                f"surfaces_to_shell produced invalid closed Shell: "
                f"{res['errors']}",
                res,
            )
        transient_body.solids = []
        shell.solid = None
    else:
        # Open shells skip the Euler-Poincare gate and the closed-manifold
        # gate. Walk every face structurally instead.
        errs: List[str] = []
        for f in shell.faces:
            errs.extend(_validate_face_local(f))
        if errs:
            raise BuildError(
                f"surfaces_to_shell produced invalid open Shell: {errs}",
                {"ok": False, "errors": errs},
            )
    return shell


def closed_shell_to_solid(shell: Shell) -> Solid:
    """Wrap a closed ``Shell`` as the outer shell of a new ``Solid``.

    The resulting solid is placed in a transient single-solid ``Body`` and
    ``validate_body`` is asserted clean. Returns the unattached ``Solid``.
    """
    if not shell.is_closed:
        raise BuildError("closed_shell_to_solid requires a closed shell")
    solid = Solid([shell])
    transient = Body(solids=[solid])
    res = validate_body(transient)
    if not res["ok"]:
        raise BuildError(
            f"closed_shell_to_solid produced invalid Solid: {res['errors']}",
            res,
        )
    # detach
    transient.solids = []
    return solid


# ---------------------------------------------------------------------------
# Analytic primitive constructors (production path)
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


def _perp(axis: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(ref, axis))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    return _unit(np.cross(axis, ref))


def box_to_body(
    corner: Sequence[float],
    dx: float,
    dy: float,
    dz: float,
    tol: float = 1e-7,
) -> Body:
    """Build an axis-aligned box ``Body`` from a corner + extents.

    Topology: V=8, E=12, F=6, S=1, G=0. ``validate_body`` is asserted
    clean before return.
    """
    ox, oy, oz = (float(c) for c in corner)
    P = [
        np.array([ox, oy, oz]),
        np.array([ox + dx, oy, oz]),
        np.array([ox + dx, oy + dy, oz]),
        np.array([ox, oy + dy, oz]),
        np.array([ox, oy, oz + dz]),
        np.array([ox + dx, oy, oz + dz]),
        np.array([ox + dx, oy + dy, oz + dz]),
        np.array([ox, oy + dy, oz + dz]),
    ]
    V = [Vertex(p, tol) for p in P]

    edef = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    E = {
        pair: Edge(Line3(P[pair[0]], P[pair[1]]), 0.0, 1.0,
                   V[pair[0]], V[pair[1]], tol)
        for pair in edef
    }

    def edge_for(a: int, b: int):
        if (a, b) in E:
            return E[(a, b)], True
        return E[(b, a)], False

    face_rings = [
        [0, 3, 2, 1],  # bottom (z-)
        [4, 5, 6, 7],  # top (z+)
        [0, 1, 5, 4],  # front (y-)
        [1, 2, 6, 5],  # right (x+)
        [2, 3, 7, 6],  # back (y+)
        [3, 0, 4, 7],  # left (x-)
    ]
    faces: List[Face] = []
    for ring in face_rings:
        coedges = []
        for i in range(4):
            a, b = ring[i], ring[(i + 1) % 4]
            e, o = edge_for(a, b)
            coedges.append(Coedge(e, o))
        loop = Loop(coedges, is_outer=True)
        p0, p1, p2 = P[ring[0]], P[ring[1]], P[ring[3]]
        plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
        faces.append(Face(plane, [loop], orientation=True, tol=tol))

    shell = Shell(faces, is_closed=True)
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"box_to_body produced invalid Body: {res['errors']}", res
        )
    return body


def cylinder_to_body(
    axis_pt: Sequence[float],
    axis_dir: Sequence[float],
    radius: float,
    height: float,
    tol: float = 1e-7,
) -> Body:
    """Build a closed cylinder ``Body`` matching the documented seam
    topology of :func:`brep.make_cylinder`.

    Topology: V=2 (two seam endpoints), E=3 (two rim circles + one
    straight seam), F=3 (lateral + 2 caps), L=4 (the lateral face's loop
    walks the seam there-and-back).
    """
    c = np.asarray(axis_pt, dtype=float)
    ax = _unit(np.asarray(axis_dir, dtype=float))
    xref = _perp(ax)
    yref = _unit(np.cross(ax, xref))
    top_c = c + height * ax

    cyl = CylinderSurface(c, ax, radius, xref)
    bottom_plane = Plane(origin=c, x_axis=xref, y_axis=yref)
    top_plane = Plane(origin=top_c, x_axis=xref, y_axis=-yref)

    seam_b = c + radius * xref
    seam_t = top_c + radius * xref
    vb = Vertex(seam_b, tol)
    vt = Vertex(seam_t, tol)

    bottom_circle = CircleArc3(c, radius, xref, yref, 0.0, 2 * math.pi)
    top_circle = CircleArc3(top_c, radius, xref, yref, 0.0, 2 * math.pi)
    e_bottom = Edge(bottom_circle, 0.0, 2 * math.pi, vb, vb, tol)
    e_top = Edge(top_circle, 0.0, 2 * math.pi, vt, vt, tol)
    e_seam = Edge(Line3(seam_b, seam_t), 0.0, 1.0, vb, vt, tol)

    side_loop = Loop(
        [
            Coedge(e_bottom, True),
            Coedge(e_seam, True),
            Coedge(e_top, False),
            Coedge(e_seam, False),
        ],
        is_outer=True,
    )
    side_face = Face(cyl, [side_loop], orientation=True, tol=tol)
    bottom_face = Face(
        bottom_plane,
        [Loop([Coedge(e_bottom, False)], is_outer=True)],
        orientation=True,
        tol=tol,
    )
    top_face = Face(
        top_plane,
        [Loop([Coedge(e_top, True)], is_outer=True)],
        orientation=True,
        tol=tol,
    )

    shell = Shell([side_face, bottom_face, top_face], is_closed=True)
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"cylinder_to_body produced invalid Body: {res['errors']}", res
        )
    return body


def sphere_to_body(
    centre: Sequence[float],
    radius: float,
    tol: float = 1e-7,
) -> Body:
    """Build a closed sphere ``Body`` matching :func:`brep.make_sphere`.

    Topology: V=2 (poles), E=1 (one meridian seam), F=1, L=1, G=0, S=1.
    The lone face's single loop traverses the seam forward then backward
    (pole singularities collapse).
    """
    c = np.asarray(centre, dtype=float)
    sph = SphereSurface(c, radius)
    north = Vertex(c + np.array([0.0, 0.0, radius]), tol)
    south = Vertex(c - np.array([0.0, 0.0, radius]), tol)

    class _Meridian:
        def evaluate(self, t: float) -> np.ndarray:
            v = -math.pi / 2 + t * math.pi
            return sph.evaluate(0.0, v)

    seam = Edge(_Meridian(), 0.0, 1.0, south, north, tol)
    loop = Loop(
        [Coedge(seam, True), Coedge(seam, False)],
        is_outer=True,
    )
    face = Face(sph, [loop], orientation=True, tol=tol)
    shell = Shell([face], is_closed=True)
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"sphere_to_body produced invalid Body: {res['errors']}", res
        )
    return body


def revolve_to_body(
    profile: object,
    axis_point: Sequence[float],
    axis_dir: Sequence[float],
    tol: float = 1e-7,
) -> "Body":
    """Build a closed ``Body`` from a full 360° revolve of a profile curve.

    Reuses the ``make_cylinder`` seam topology pattern extended to an
    arbitrary NURBS profile curve.  The profile is revolved around the axis
    defined by *axis_point* / *axis_dir*.  Topology is chosen automatically:

    * **Both endpoints off-axis** — cylinder topology: 2 seam vertices, 3
      edges (2 rim circles + 1 seam line), 3 faces (lateral + 2 planar
      caps), 1 shell, G=0.  ``V-E+F-H = 2-3+3-0 = 2 = 2(1-0)``.
    * **Start endpoint on-axis (bottom pole)** — cone / half-dome: 2
      vertices (pole + seam top), 2 edges (top rim circle + seam), 2 faces
      (lateral + 1 cap), G=0.  ``V-E+F-H = 2-2+2-0 = 2 = 2(1-0)``.
    * **End endpoint on-axis (top pole)** — symmetric mirror of above.
    * **Both endpoints on-axis (spindle/sphere)** — 2 pole vertices, 1 seam
      edge, 1 face, G=0.  ``V-E+F-H = 2-1+1-0 = 2 = 2(1-0)``.

    The profile curve must expose:
    * ``control_points`` — ``np.ndarray`` of shape ``(n, 3)`` or ``(n, 4)``
    * ``degree`` — integer
    * ``knots`` — ``np.ndarray``

    Parameters
    ----------
    profile
        A ``NurbsCurve`` (or any object with the three attributes above).
    axis_point, axis_dir
        Axis of revolution.  *axis_dir* need not be unit-length.
    tol
        Topological and geometric tolerance.

    Returns
    -------
    Body
        A validated closed ``Body``.

    Raises
    ------
    BuildError
        If ``validate_body`` fails on the produced body.
    """
    from kerf_cad_core.geom.revolve_srf import revolve_surface, evaluate_revolve

    ax_pt = np.asarray(axis_point, dtype=float)
    ax = _unit(np.asarray(axis_dir, dtype=float))

    # ------------------------------------------------------------------
    # 1. Build the lateral NURBS surface (full 360° revolve).
    # ------------------------------------------------------------------
    lateral_srf = revolve_surface(profile, ax_pt, ax, 0.0, 2.0 * math.pi, tol=tol)

    # ------------------------------------------------------------------
    # 2. Sample profile endpoints to determine geometry.
    # ------------------------------------------------------------------
    prof_cp = np.asarray(profile.control_points, dtype=float)
    prof_knots = np.asarray(profile.knots, dtype=float)
    prof_deg = int(profile.degree)
    t_start = float(prof_knots[prof_deg])
    t_end = float(prof_knots[-(prof_deg + 1)])

    # Evaluate start/end of the profile (seam positions at v=0).
    # evaluate_revolve at v=t_start/t_end, u=0 gives the seam points.
    # But simpler: directly evaluate the profile's endpoints.
    def _eval_profile(t: float) -> np.ndarray:
        """Evaluate profile curve at parameter t."""
        from kerf_cad_core.geom.nurbs import find_span
        from kerf_cad_core.geom.revolve_srf import _basis_funcs

        cp_raw = prof_cp
        if cp_raw.shape[1] == 4:
            w_col = cp_raw[:, 3]
            xyz = cp_raw[:, :3]
        else:
            w_col = np.ones(cp_raw.shape[0])
            xyz = cp_raw[:, :3]

        n = cp_raw.shape[0]
        span = find_span(n - 1, prof_deg, t, prof_knots)
        N = _basis_funcs(span, t, prof_deg, prof_knots)
        pt = np.zeros(3)
        w = 0.0
        for i in range(prof_deg + 1):
            idx = span - prof_deg + i
            pt += N[i] * w_col[idx] * xyz[idx]
            w += N[i] * w_col[idx]
        if abs(w) > 1e-15:
            pt /= w
        return pt

    p_start = _eval_profile(t_start)  # bottom seam point (v=0 of revolve)
    p_end = _eval_profile(t_end)      # top seam point (v=0 of revolve)

    # Radii of start/end points from axis
    def _radius(pt: np.ndarray) -> float:
        d = pt - ax_pt
        proj = float(np.dot(d, ax))
        foot = ax_pt + proj * ax
        return float(np.linalg.norm(pt - foot))

    r_start = _radius(p_start)
    r_end = _radius(p_end)
    pole_start = r_start < tol * 10.0
    pole_end = r_end < tol * 10.0

    # ------------------------------------------------------------------
    # 3. Build seam curve (the profile itself at u=0, i.e. the start
    #    angle of the revolve maps v-parameter of the revolve surface
    #    to points along the profile).
    #
    #    The seam runs from p_start to p_end in 3-D.
    #    We model it as a _SurfaceIsoCurve on the lateral surface at u=0
    #    (the lateral surface's knots_v spans t_start..t_end for u).
    # ------------------------------------------------------------------

    # Lateral surface param box: u in [0, 2pi], v in [t_start, t_end]
    u_start = float(lateral_srf.knots_v[lateral_srf.degree_v])
    u_end_v = float(lateral_srf.knots_v[-(lateral_srf.degree_v + 1)])
    # Note: lateral_srf degree_u = profile.degree, degree_v = 2 (arc)
    #       knots_u = profile.knots, knots_v = arc knot vector (0..1 or similar)
    # The seam runs along knots_u at the boundary of the arc (v=0 in arc param).
    # Evaluate the lateral surface at v_arc=u_start (seam, angle=0) varying u_prof.

    class _SeamCurve:
        """Isocurve of the lateral surface at the seam angle (v=v_arc_start)."""
        def __init__(self, srf, v_fixed, t0, t1):
            self._srf = srf
            self._v = v_fixed
            self.t0 = t0
            self.t1 = t1

        def evaluate(self, t: float) -> np.ndarray:
            return evaluate_revolve(self._srf, t, self._v)

    seam_crv = _SeamCurve(lateral_srf, u_start, t_start, t_end)

    # ------------------------------------------------------------------
    # 4. Build rim circle curves at start and end of profile.
    # ------------------------------------------------------------------
    # The revolve surface's knots_u are from the profile; we fix u=t_start
    # or u=t_end and let v sweep 0..2pi (the arc dimension).
    # We use the analytic CircleArc3 for the cap rims (more robust than
    # isocurves since we know they are circles).

    def _foot_and_radial(pt: np.ndarray):
        d = pt - ax_pt
        proj = float(np.dot(d, ax))
        foot = ax_pt + proj * ax
        radial = pt - foot
        r = float(np.linalg.norm(radial))
        return foot, radial, r

    foot_s, radial_s, r_s = _foot_and_radial(p_start)
    foot_e, radial_e, r_e = _foot_and_radial(p_end)

    # x/y axes for each circle (derived from the radial direction at seam)
    def _circle_axes(radial: np.ndarray, r: float):
        if r > 1e-14:
            x_ax = radial / r
        else:
            x_ax = _perp(ax)
        y_ax = _unit(np.cross(ax, x_ax))
        return x_ax, y_ax

    xb, yb = _circle_axes(radial_s, r_s)
    xt, yt = _circle_axes(radial_e, r_e)

    # ------------------------------------------------------------------
    # 5. Construct topology.
    # ------------------------------------------------------------------
    # We build the 4 standard cases:
    #   (A) neither pole  → cylinder topology
    #   (B) start pole    → top cone / half-dome
    #   (C) end pole      → bottom cone / half-dome
    #   (D) both poles    → spindle / football / sphere-like
    # ------------------------------------------------------------------

    if not pole_start and not pole_end:
        # ── Case A: cylinder topology ─────────────────────────────────
        # V=2, E=3, F=3, L=4 (lateral has 1 loop with 4 coedges)
        # Euler: 2-3+3-1 = 1... wait, H = L-F = 4-3 = 1? No:
        # L = total loops over all faces = 1 (lateral) + 1 (bot cap) + 1 (top cap) = 3
        # H = L - F = 3 - 3 = 0
        # V-E+F-H = 2-3+3-0 = 2 = 2*(1-0) ✓
        # The lateral face loop has 4 coedges (bottom_circle, seam_fwd,
        # top_circle_rev, seam_rev) — but L counts loops not coedges.

        v_seam_b = Vertex(p_start, tol)
        v_seam_t = Vertex(p_end, tol)

        # Bottom rim circle: full circle from v_seam_b back to v_seam_b
        bot_circle_crv = CircleArc3(foot_s, r_s, xb, yb, 0.0, 2 * math.pi)
        e_bot = Edge(bot_circle_crv, 0.0, 2 * math.pi, v_seam_b, v_seam_b, tol)

        # Top rim circle
        top_circle_crv = CircleArc3(foot_e, r_e, xt, yt, 0.0, 2 * math.pi)
        e_top = Edge(top_circle_crv, 0.0, 2 * math.pi, v_seam_t, v_seam_t, tol)

        # Seam edge along the profile
        e_seam = Edge(seam_crv, t_start, t_end, v_seam_b, v_seam_t, tol)

        # Lateral face loop: bottom(+) → seam(+) → top(-) → seam(-)
        lat_loop = Loop(
            [
                Coedge(e_bot, True),
                Coedge(e_seam, True),
                Coedge(e_top, False),
                Coedge(e_seam, False),
            ],
            is_outer=True,
        )
        lat_face = Face(lateral_srf, [lat_loop], orientation=True, tol=tol)

        # Bottom cap: disk at profile start
        # The cap plane has outward normal pointing away from body interior.
        # The bottom cap's outward normal points in -ax direction (downward).
        bot_plane = Plane(origin=foot_s, x_axis=xb, y_axis=yb)
        bot_loop = Loop([Coedge(e_bot, False)], is_outer=True)
        bot_face = Face(bot_plane, [bot_loop], orientation=True, tol=tol)

        # Top cap: outward normal in +ax direction.
        top_plane = Plane(origin=foot_e, x_axis=xt, y_axis=-yt)
        top_loop = Loop([Coedge(e_top, True)], is_outer=True)
        top_face = Face(top_plane, [top_loop], orientation=True, tol=tol)

        shell = Shell([lat_face, bot_face, top_face], is_closed=True)

    elif pole_start and not pole_end:
        # ── Case B: bottom pole ───────────────────────────────────────
        # V=2 (pole_b + seam_t), E=2 (top rim + seam), F=2 (lateral + top cap)
        # L=2 (1 loop per face), H=0, G=0
        # V-E+F-H = 2-2+2-0 = 2 ✓
        v_pole_b = Vertex(p_start, tol)
        v_seam_t = Vertex(p_end, tol)

        top_circle_crv = CircleArc3(foot_e, r_e, xt, yt, 0.0, 2 * math.pi)
        e_top = Edge(top_circle_crv, 0.0, 2 * math.pi, v_seam_t, v_seam_t, tol)
        e_seam = Edge(seam_crv, t_start, t_end, v_pole_b, v_seam_t, tol)

        # Lateral face loop: seam(+) → top(-) → seam(-)
        lat_loop = Loop(
            [
                Coedge(e_seam, True),
                Coedge(e_top, False),
                Coedge(e_seam, False),
            ],
            is_outer=True,
        )
        lat_face = Face(lateral_srf, [lat_loop], orientation=True, tol=tol)

        top_plane = Plane(origin=foot_e, x_axis=xt, y_axis=-yt)
        top_loop = Loop([Coedge(e_top, True)], is_outer=True)
        top_face = Face(top_plane, [top_loop], orientation=True, tol=tol)

        shell = Shell([lat_face, top_face], is_closed=True)

    elif not pole_start and pole_end:
        # ── Case C: top pole ──────────────────────────────────────────
        # V=2 (seam_b + pole_t), E=2 (bottom rim + seam), F=2
        # V-E+F-H = 2-2+2-0 = 2 ✓
        v_seam_b = Vertex(p_start, tol)
        v_pole_t = Vertex(p_end, tol)

        bot_circle_crv = CircleArc3(foot_s, r_s, xb, yb, 0.0, 2 * math.pi)
        e_bot = Edge(bot_circle_crv, 0.0, 2 * math.pi, v_seam_b, v_seam_b, tol)
        e_seam = Edge(seam_crv, t_start, t_end, v_seam_b, v_pole_t, tol)

        # Lateral face loop: bot(+) → seam(+) → seam(-)
        lat_loop = Loop(
            [
                Coedge(e_bot, True),
                Coedge(e_seam, True),
                Coedge(e_seam, False),
            ],
            is_outer=True,
        )
        lat_face = Face(lateral_srf, [lat_loop], orientation=True, tol=tol)

        bot_plane = Plane(origin=foot_s, x_axis=xb, y_axis=yb)
        bot_loop = Loop([Coedge(e_bot, False)], is_outer=True)
        bot_face = Face(bot_plane, [bot_loop], orientation=True, tol=tol)

        shell = Shell([lat_face, bot_face], is_closed=True)

    else:
        # ── Case D: both poles (spindle) ──────────────────────────────
        # V=2 (pole_b + pole_t), E=1 (seam), F=1, L=1, H=0, G=0
        # V-E+F-H = 2-1+1-0 = 2 ✓  (same as sphere)
        v_pole_b = Vertex(p_start, tol)
        v_pole_t = Vertex(p_end, tol)
        e_seam = Edge(seam_crv, t_start, t_end, v_pole_b, v_pole_t, tol)
        lat_loop = Loop(
            [Coedge(e_seam, True), Coedge(e_seam, False)],
            is_outer=True,
        )
        lat_face = Face(lateral_srf, [lat_loop], orientation=True, tol=tol)
        shell = Shell([lat_face], is_closed=True)

    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"revolve_to_body produced invalid Body: {res['errors']}", res
        )
    return body


__all__ = [
    "BuildError",
    "surface_to_face",
    "surfaces_to_shell",
    "closed_shell_to_solid",
    "box_to_body",
    "cylinder_to_body",
    "sphere_to_body",
    "revolve_to_body",
]


def extrude_to_body(
    profile_vertices: Sequence[Sequence[float]],
    direction: Sequence[float],
    tol: float = 1e-7,
) -> Body:
    """Extrude a closed planar polygon (cap-style) into a solid ``Body``.

    Parameters
    ----------
    profile_vertices
        Ordered sequence of N 3-D points forming a **closed** planar polygon.
        The polygon must be convex or at least simply connected (no
        self-intersections).  The last point need not repeat the first.
    direction
        3-D extrusion vector whose magnitude is the extrusion height.
    tol
        Topological tolerance for ``Vertex`` / ``Edge`` / ``Face``.

    Returns
    -------
    Body
        A closed solid with N+2 faces (N side quads + bottom cap + top cap),
        2N vertices, 3N edges.  For a 4-sided polygon (rectangle/square) the
        oracle is V=8, E=12, F=6 — identical to a box.  ``validate_body`` is
        asserted clean before return.

    Notes
    -----
    The bottom cap normal points *opposite* to ``direction`` (outward from the
    solid); the top cap normal points *along* ``direction``.  Side face normals
    point radially outward.
    """
    verts_raw = [np.asarray(p, dtype=float).reshape(3) for p in profile_vertices]
    n = len(verts_raw)
    if n < 3:
        raise BuildError(
            f"extrude_to_body requires at least 3 profile vertices; got {n}"
        )
    d = np.asarray(direction, dtype=float).reshape(3)
    d_len = float(np.linalg.norm(d))
    if d_len < 1e-14:
        raise BuildError("extrude_to_body direction vector has zero length")

    # Compute profile normal to detect and enforce CCW bottom winding.
    # For each polygon vertex pair compute the cross product accumulation.
    centroid_bot = np.mean(verts_raw, axis=0)
    area_vec = np.zeros(3)
    for i in range(n):
        a = verts_raw[i] - centroid_bot
        b = verts_raw[(i + 1) % n] - centroid_bot
        area_vec += np.cross(a, b)
    # We want the bottom face normal to point anti-parallel to d (outward).
    # If area_vec is parallel to d, the polygon is wound CCW w.r.t. d; we
    # want it wound CW w.r.t. d so the bottom face normal (= profile normal
    # from CCW winding via right-hand rule) opposes d.
    # Equivalently: bottom loops should be wound CW when viewed from the d
    # direction, i.e. CCW when viewed from -d (the outward direction).
    # Reverse if area_vec is anti-parallel to d (which means CCW from -d is
    # actually CW — the normal already matches -d via the polygon's current
    # winding; in that case leave it as-is).
    # Simpler: we want area_vec · d < 0 for correct outward-normal bottom.
    if float(np.dot(area_vec, d)) > 0:
        # Currently wound CCW w.r.t. d -> reverse so it winds CW w.r.t. d
        # (= CCW w.r.t. -d, outward normal = -d direction).
        verts_raw = list(reversed(verts_raw))

    # Build 2N vertices
    bot_V = [Vertex(p.copy(), tol) for p in verts_raw]
    top_V = [Vertex(p + d, tol) for p in verts_raw]

    # Build edges
    # Bottom ring: bot_V[i] -> bot_V[(i+1)%n]
    bot_edges: List[Edge] = []
    for i in range(n):
        p0 = bot_V[i].point
        p1 = bot_V[(i + 1) % n].point
        bot_edges.append(Edge(Line3(p0, p1), 0.0, 1.0, bot_V[i], bot_V[(i + 1) % n], tol))

    # Top ring: top_V[i] -> top_V[(i+1)%n]
    top_edges: List[Edge] = []
    for i in range(n):
        p0 = top_V[i].point
        p1 = top_V[(i + 1) % n].point
        top_edges.append(Edge(Line3(p0, p1), 0.0, 1.0, top_V[i], top_V[(i + 1) % n], tol))

    # Vertical edges: bot_V[i] -> top_V[i]
    vert_edges: List[Edge] = []
    for i in range(n):
        p0 = bot_V[i].point
        p1 = top_V[i].point
        vert_edges.append(Edge(Line3(p0, p1), 0.0, 1.0, bot_V[i], top_V[i], tol))

    d_unit = d / d_len

    # -----------------------------------------------------------------------
    # Bottom cap face: loop traverses bot_V[0] -> bot_V[1] -> ... -> bot_V[n-1]
    # (forward, using orientation=True for each bot_edge[i]).
    # After the `verts_raw` winding normalisation (area_vec · d < 0), the
    # polygon normal (from CCW right-hand rule) already points in the -d
    # direction.  The Plane's x_axis × y_axis must equal -d_unit.
    # With x_axis = edge_dir and y_axis = (-d_unit) × edge_dir the product
    # is edge_dir × ((-d_unit) × edge_dir) = -d_unit (by triple-product
    # identity, given edge_dir ⊥ d_unit for a planar profile). ✓
    bot_coedges: List[Coedge] = [Coedge(bot_edges[i], True) for i in range(n)]
    bot_loop = Loop(bot_coedges, is_outer=True)
    x_axis_bot = _unit(verts_raw[1] - verts_raw[0])
    y_axis_bot = _unit(np.cross(-d_unit, x_axis_bot))
    bot_plane = Plane(origin=verts_raw[0].copy(), x_axis=x_axis_bot, y_axis=y_axis_bot)
    bot_face = Face(bot_plane, [bot_loop], orientation=True, tol=tol)

    # -----------------------------------------------------------------------
    # Top cap face: loop traverses top_V[n-1] -> top_V[n-2] -> ... -> top_V[0]
    # (reversed relative to the bottom), so the right-hand normal points in
    # the +d direction (outward from the top of the solid).
    # Coedge k uses top_edges[(n-1-k) % n] reversed:
    #   k=0: top_edges[n-1] reversed  -> top_V[0] -> top_V[n-1]
    #   k=1: top_edges[n-2] reversed  -> top_V[n-1] -> top_V[n-2]
    #   ...
    # Traversal sequence: top_V[0], top_V[n-1], top_V[n-2], ..., top_V[1]
    # which is a valid (cyclic) reversed polygon.
    # The Plane's x_axis × y_axis must equal +d_unit.
    # With x_axis = edge_dir and y_axis = d_unit × edge_dir the product is
    # edge_dir × (d_unit × edge_dir) = d_unit. ✓
    top_coedges: List[Coedge] = [
        Coedge(top_edges[(n - 1 - k) % n], False) for k in range(n)
    ]
    top_loop = Loop(top_coedges, is_outer=True)
    x_axis_top = _unit(verts_raw[1] - verts_raw[0])
    y_axis_top = _unit(np.cross(d_unit, x_axis_top))
    top_plane = Plane(origin=(verts_raw[0] + d).copy(), x_axis=x_axis_top, y_axis=y_axis_top)
    top_face = Face(top_plane, [top_loop], orientation=True, tol=tol)

    # -----------------------------------------------------------------------
    # Side faces: one per edge i -> j where j=(i+1)%n.
    # CCW traversal (outward normal = d_unit × edge_dir by right-hand rule):
    #   bot_V[i] -> top_V[i] -> top_V[j] -> bot_V[j] -> bot_V[i]
    # Coedges:
    #   vert_edge[i]     forward  (bot_V[i]   -> top_V[i])
    #   top_edge[i]      forward  (top_V[i]   -> top_V[j])
    #   vert_edge[j]     reversed (top_V[j]   -> bot_V[j])
    #   bot_edge[i]      reversed (bot_V[j]   -> bot_V[i])
    #
    # 2-manifold consistency:
    #   • bot_edges[i] reversed here ↔ forward in bottom cap → opposite ✓
    #   • top_edges[i] forward here  ↔ reversed in top cap   → opposite ✓
    #   • vert_edges[i] forward here ↔ reversed in side face (i-1) → opposite ✓
    #   • vert_edges[j] reversed here↔ forward in side face i+1    → opposite ✓
    #
    # Plane: x_axis = edge_dir, y_axis = d_unit → x × y = edge_dir × d_unit
    # = -(d_unit × edge_dir) = -outward. So we flip: x_axis = -d_unit, y_axis = edge_dir
    # → x × y = (-d_unit) × edge_dir = -(d_unit × edge_dir) ... still wrong.
    # Correct: outward_normal = cross(d_unit, edge_dir).
    # Use x_axis = d_unit, y_axis = edge_dir → x × y = d_unit × edge_dir = outward ✓
    side_faces: List[Face] = []
    for i in range(n):
        j = (i + 1) % n
        ce0 = Coedge(vert_edges[i], True)       # bot_V[i]   -> top_V[i]
        ce1 = Coedge(top_edges[i], True)        # top_V[i]   -> top_V[j]
        ce2 = Coedge(vert_edges[j], False)      # top_V[j]   -> bot_V[j]
        ce3 = Coedge(bot_edges[i], False)       # bot_V[j]   -> bot_V[i]
        side_loop = Loop([ce0, ce1, ce2, ce3], is_outer=True)
        p_i = bot_V[i].point
        p_j = bot_V[j].point
        edge_dir = _unit(p_j - p_i)
        sx = d_unit              # x-axis = extrusion direction
        sy = edge_dir            # y-axis = edge direction  →  x×y = d_unit × edge_dir = outward ✓
        side_plane = Plane(origin=p_i.copy(), x_axis=sx, y_axis=sy)
        side_faces.append(Face(side_plane, [side_loop], orientation=True, tol=tol))

    # -----------------------------------------------------------------------
    all_faces: List[Face] = [bot_face, top_face] + side_faces
    shell = Shell(all_faces, is_closed=True)
    body = Body(solids=[Solid([shell])])
    res = validate_body(body)
    if not res["ok"]:
        raise BuildError(
            f"extrude_to_body produced invalid Body: {res['errors']}", res
        )
    return body


__all__ = [
    "BuildError",
    "surface_to_face",
    "surfaces_to_shell",
    "closed_shell_to_solid",
    "box_to_body",
    "cylinder_to_body",
    "sphere_to_body",
    "extrude_to_body",
]
