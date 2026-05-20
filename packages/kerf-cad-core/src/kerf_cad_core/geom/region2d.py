"""2D planar-region boolean operations → Face with inner loops.

GK-56: union / difference / intersection on closed planar curve loops
(Line3 / CircleArc3 edges) producing a :class:`~kerf_cad_core.geom.brep.Face`
whose outer loop is **CCW** and whose inner (hole) loops are **CW** per the
B-rep contract in ``BREP_CONTRACT.md``.

Algorithm
---------
1. **Project to 2-D** — auto-detect the common plane from the first loop.
2. **Tessellate arcs** — adaptively subdivide arcs into chords; polyline
   representation is used only for intersection finding.
3. **Greiner-Hormann clipping** — find all crossing points, classify
   entry/exit, trace result polygons.
4. **Classify outer vs hole** — for multi-polygon results (e.g.
   difference with B fully inside A returns outer + hole) determine
   which polygon is the outer boundary and which are holes.
5. **Reconstruct Loop objects** — map polyline edges back to
   :class:`Line3` segments; future versions may recover arcs.
6. **Build Face** — outer loop marked ``is_outer=True`` (CCW in 2-D),
   hole loops marked ``is_outer=False`` (CW in 2-D, i.e. reversed).

Public API
----------
.. code-block:: python

    from kerf_cad_core.geom.region2d import (
        region_union,
        region_intersection,
        region_difference,
        region_area,
        make_rect_loop,
        make_circle_loop,
    )

    face = region_difference(square_loop, circle_loop)
    area = region_area(face)          # signed; outer CCW ⇒ positive

The convenience helpers :func:`make_rect_loop` and :func:`make_circle_loop`
build CCW input loops in the z=0 plane.

Oracle
------
``area(unit_square − inscribed_unit_circle) == 1 − π·r²`` to ≤ 1 × 10⁻⁷.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    CircleArc3,
    Coedge,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Vertex,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOL = 1e-9
_ARC_CHORD_TOL = 1e-4  # chord-height tolerance when tessellating arcs
_MIN_ARC_SEGS = 8      # minimum segments per arc


# ---------------------------------------------------------------------------
# 2-D coordinate frame
# ---------------------------------------------------------------------------

@dataclass
class _Plane2D:
    """Local 2-D frame embedded in 3-D."""
    origin: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray
    normal: np.ndarray

    def to_2d(self, p3: np.ndarray) -> np.ndarray:
        d = np.asarray(p3, dtype=float) - self.origin
        return np.array([np.dot(d, self.x_axis), np.dot(d, self.y_axis)])

    def to_3d(self, p2: np.ndarray) -> np.ndarray:
        return (
            self.origin
            + float(p2[0]) * self.x_axis
            + float(p2[1]) * self.y_axis
        )


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-14 else v


def _detect_plane(loop: Loop) -> Optional[_Plane2D]:
    """Derive a 2-D frame from a Loop's geometry."""
    pts = _sample_loop_3d(loop, 6)
    if len(pts) < 3:
        return None
    o = pts[0]
    x = None
    for p in pts[1:]:
        d = p - o
        if np.linalg.norm(d) > 1e-10:
            x = _unit(d)
            break
    if x is None:
        return None
    n = None
    for p in pts[2:]:
        d = p - o
        c = np.cross(x, d)
        if np.linalg.norm(c) > 1e-10:
            n = _unit(c)
            break
    if n is None:
        # all collinear — pick arbitrary perpendicular
        if abs(x[0]) < 0.9:
            n = _unit(np.cross(x, np.array([1.0, 0.0, 0.0])))
        else:
            n = _unit(np.cross(x, np.array([0.0, 1.0, 0.0])))
    y = _unit(np.cross(n, x))
    return _Plane2D(origin=o.copy(), x_axis=x, y_axis=y, normal=n)


def _sample_loop_3d(loop: Loop, per_edge: int = 4) -> List[np.ndarray]:
    pts: List[np.ndarray] = []
    for ce in loop.coedges:
        e = ce.edge
        curve = e.curve
        t0, t1 = (e.t0, e.t1) if ce.orientation else (e.t1, e.t0)
        for i in range(per_edge):
            t = t0 + (t1 - t0) * i / per_edge
            pts.append(np.asarray(curve.evaluate(t), dtype=float))
    return pts


# ---------------------------------------------------------------------------
# Tessellation
# ---------------------------------------------------------------------------

def _arc_pts_2d(arc: CircleArc3, t0: float, t1: float,
                plane: _Plane2D, chord_tol: float) -> List[np.ndarray]:
    span = abs(t1 - t0)
    if arc.radius > 1e-12 and chord_tol > 0:
        dtheta_max = 2.0 * math.sqrt(2.0 * chord_tol / arc.radius)
        n = max(_MIN_ARC_SEGS, math.ceil(span / dtheta_max))
    else:
        n = _MIN_ARC_SEGS
    return [
        plane.to_2d(np.asarray(arc.evaluate(t0 + (t1 - t0) * i / n), dtype=float))
        for i in range(n + 1)
    ]


def _tessellate_loop(loop: Loop, plane: _Plane2D) -> List[np.ndarray]:
    """Return closed 2-D polyline (last pt = first pt omitted)."""
    poly: List[np.ndarray] = []
    for ce in loop.coedges:
        e = ce.edge
        curve = e.curve
        t0, t1 = (e.t0, e.t1) if ce.orientation else (e.t1, e.t0)
        if isinstance(curve, CircleArc3):
            pts = _arc_pts_2d(curve, t0, t1, plane, _ARC_CHORD_TOL)
            poly.extend(pts[:-1])   # drop repeated end
        else:
            p0 = plane.to_2d(np.asarray(curve.evaluate(t0), dtype=float))
            poly.append(p0)
    return poly


# ---------------------------------------------------------------------------
# 2-D polygon helpers
# ---------------------------------------------------------------------------

def _signed_area_2d(poly: List[np.ndarray]) -> float:
    """Signed shoelace area (+CCW)."""
    n = len(poly)
    acc = 0.0
    for i in range(n):
        x0, y0 = poly[i][0], poly[i][1]
        x1, y1 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        acc += x0 * y1 - x1 * y0
    return acc * 0.5


def _point_in_poly(pt: np.ndarray, poly: List[np.ndarray]) -> bool:
    """Ray-casting test."""
    x, y = float(pt[0]), float(pt[1])
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-300) + xi
        ):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Greiner-Hormann clipping
# ---------------------------------------------------------------------------

@dataclass
class _GH:
    """Node in GH doubly-linked circular list."""
    pt: np.ndarray
    alpha: float = 0.0
    intersect: bool = False
    entry: bool = False
    checked: bool = False
    next: Optional["_GH"] = None
    prev: Optional["_GH"] = None
    neighbour: Optional["_GH"] = None


def _seg_isect(a0: np.ndarray, a1: np.ndarray,
               b0: np.ndarray, b1: np.ndarray) -> Optional[Tuple[float, float]]:
    da, db = a1 - a0, b1 - b0
    denom = da[0] * db[1] - da[1] * db[0]
    if abs(denom) < 1e-14:
        return None
    dx, dy = b0[0] - a0[0], b0[1] - a0[1]
    alpha = (dx * db[1] - dy * db[0]) / denom
    beta  = (dx * da[1] - dy * da[0]) / denom
    eps = 1e-9
    if eps < alpha < 1.0 - eps and eps < beta < 1.0 - eps:
        return alpha, beta
    return None


def _build_list(poly: List[np.ndarray]) -> List[_GH]:
    nodes = [_GH(pt=p.copy()) for p in poly]
    n = len(nodes)
    for i in range(n):
        nodes[i].next = nodes[(i + 1) % n]
        nodes[i].prev = nodes[(i - 1) % n]
    return nodes


def _insert_ordered(start: _GH, end: _GH, new: _GH) -> None:
    cur = start
    while cur.next is not end:
        nxt = cur.next
        if nxt.intersect and nxt.alpha > new.alpha:
            break
        cur = nxt
    nxt = cur.next
    cur.next = new
    new.prev = cur
    new.next = nxt
    nxt.prev = new


def _phase1(nodes_a: List[_GH], nodes_b: List[_GH],
            poly_a: List[np.ndarray], poly_b: List[np.ndarray]) -> None:
    na, nb = len(nodes_a), len(nodes_b)
    for i in range(na):
        a0, a1 = poly_a[i], poly_a[(i + 1) % na]
        hits: List[Tuple[float, float, int]] = []
        for j in range(nb):
            r = _seg_isect(a0, a1, poly_b[j], poly_b[(j + 1) % nb])
            if r is not None:
                hits.append((r[0], r[1], j))
        hits.sort(key=lambda x: x[0])
        for alpha, beta, j in hits:
            pt = a0 + alpha * (a1 - a0)
            # Classify: entry = point just past crossing is inside poly_b
            step = min(0.01, (1.0 - alpha) * 0.5)
            mid = a0 + (alpha + step) * (a1 - a0)
            entry_a = _point_in_poly(mid, poly_b)
            na_node = _GH(pt=pt.copy(), alpha=alpha, intersect=True, entry=entry_a)
            nb_node = _GH(pt=pt.copy(), alpha=beta,  intersect=True, entry=not entry_a)
            na_node.neighbour = nb_node
            nb_node.neighbour = na_node
            _insert_ordered(nodes_a[i], nodes_a[(i + 1) % na], na_node)
            _insert_ordered(nodes_b[j], nodes_b[(j + 1) % nb], nb_node)


def _all_nodes(head: _GH) -> List[_GH]:
    out = [head]
    cur = head.next
    while cur is not head:
        out.append(cur)
        cur = cur.next
    return out


def _gh_trace(list_a: List[_GH], list_b: List[_GH],
              operation: str) -> List[List[np.ndarray]]:
    # For union: start at exit nodes; for intersection: start at entry nodes
    start_flag = operation == "intersection"
    for v in list_a:
        v.checked = False
    for v in list_b:
        v.checked = False

    result: List[List[np.ndarray]] = []
    for start in list_a:
        if not start.intersect or start.checked or start.entry != start_flag:
            continue
        poly_out = [start.pt.copy()]
        start.checked = True
        cur = start
        on_a = True
        guard = len(list_a) + len(list_b) + 4
        for _ in range(guard):
            cur = cur.next
            if cur.intersect:
                if cur.checked:
                    break
                cur.checked = True
                if cur.neighbour:
                    cur.neighbour.checked = True
                on_a = not on_a
                cur = cur.neighbour
                if cur is None or cur is start:
                    break
            poly_out.append(cur.pt.copy())
            if cur is start:
                break
        if len(poly_out) >= 3:
            result.append(poly_out)
    return result


def _clip(poly_a: List[np.ndarray], poly_b: List[np.ndarray],
          operation: str) -> List[List[np.ndarray]]:
    """Full GH pipeline on two CCW 2-D polylines. Returns list of result polys."""
    # Ensure both are CCW before operations
    if _signed_area_2d(poly_a) < 0:
        poly_a = list(reversed(poly_a))
    if _signed_area_2d(poly_b) < 0:
        poly_b = list(reversed(poly_b))

    if operation == "difference":
        # A − B  ≡  A ∩ complement(B)  ≡  reverse B to make it CW
        poly_b = list(reversed(poly_b))

    # Check for interior intersections
    na, nb = len(poly_a), len(poly_b)
    has_x = any(
        _seg_isect(poly_a[i], poly_a[(i + 1) % na],
                   poly_b[j], poly_b[(j + 1) % nb]) is not None
        for i in range(na)
        for j in range(nb)
    )

    if not has_x:
        # Try a small perturbation to handle vertex-on-boundary degeneracies
        scale = max(
            abs(poly_a[i][k] - poly_a[j][k])
            for i in range(na) for j in range(na) for k in range(2)
        ) if na > 1 else 1.0
        eps = scale * 1e-5
        centroid_b = np.mean(poly_b, axis=0)
        poly_b_pert = [centroid_b + (1.0 - eps) * (p - centroid_b) for p in poly_b]
        if any(
            _seg_isect(poly_a[i], poly_a[(i + 1) % na],
                       poly_b_pert[j], poly_b_pert[(j + 1) % nb]) is not None
            for i in range(na) for j in range(nb)
        ):
            poly_b = poly_b_pert
            has_x = True

    if not has_x:
        return _no_intersect(poly_a, poly_b, operation)

    nodes_a = _build_list(poly_a)
    nodes_b = _build_list(poly_b)
    _phase1(nodes_a, nodes_b, poly_a, poly_b)
    la = _all_nodes(nodes_a[0])
    lb = _all_nodes(nodes_b[0])
    result = _gh_trace(la, lb, operation)
    if not result:
        return _no_intersect(poly_a, poly_b, operation)
    return result


def _no_intersect(poly_a: List[np.ndarray], poly_b: List[np.ndarray],
                  operation: str) -> List[List[np.ndarray]]:
    """Handle case where no interior intersections exist.

    For the ``difference`` operation, ``poly_b`` has already been reversed
    (made CW) before this function is called.  We restore the original CCW
    orientation of B to run containment tests.
    """
    area_a = abs(_signed_area_2d(poly_a))
    # For difference poly_b is already reversed (CW); restore CCW for area + centroid
    poly_b_orig = list(reversed(poly_b)) if operation == "difference" else poly_b
    area_b = abs(_signed_area_2d(poly_b_orig))

    centroid_a = np.mean(poly_a, axis=0)
    centroid_b = np.mean(poly_b_orig, axis=0)

    b_centroid_in_a = _point_in_poly(centroid_b, poly_a)
    a_centroid_in_b = _point_in_poly(centroid_a, poly_b_orig)

    # Near-identical check (same shape, same centroid)
    tol_area = 1e-6 * max(area_a, area_b, 1e-12)
    same = (abs(area_a - area_b) < tol_area and
            float(np.linalg.norm(centroid_a - centroid_b)) <
            1e-6 * (math.sqrt(max(area_a, area_b)) + 1e-12))

    # Containment classification:
    #   B inside A:  b_centroid_in_a AND area_b <= area_a
    #   A inside B:  a_centroid_in_b AND area_a <= area_b
    # When centroids coincide we fall back to area comparison alone.
    b_inside_a = b_centroid_in_a and area_b <= area_a
    a_inside_b = a_centroid_in_b and area_a <= area_b

    if operation == "union":
        if same or b_inside_a:
            return [poly_a]
        if a_inside_b:
            return [poly_b_orig]
        return [poly_a, poly_b_orig]  # disjoint: return both CCW

    elif operation == "intersection":
        if same:
            return [poly_a]
        if b_inside_a:
            return [poly_b_orig]   # B is the smaller; intersection = B
        if a_inside_b:
            return [poly_a]        # A is the smaller; intersection = A
        return []                  # truly disjoint

    else:  # difference
        if same:
            return []              # A − A = empty
        if a_inside_b:
            return []              # A is inside B → A − B = empty
        if b_inside_a:
            # B is a hole inside A.
            # poly_b is already CW (reversed for difference).
            # Return [outer_CCW, hole_CW].
            return [poly_a, poly_b]
        return [poly_a]            # disjoint: A unchanged


# ---------------------------------------------------------------------------
# Build Loop + Face from 2-D polygons
# ---------------------------------------------------------------------------

def _poly_to_loop(poly2d: List[np.ndarray], plane: _Plane2D,
                  is_outer: bool) -> Loop:
    """Convert a 2-D polygon to a Loop of Line3 edges.

    ``is_outer=True``  → polygon oriented CCW in 2-D (positive area).
    ``is_outer=False`` → polygon oriented CW  in 2-D (negative area = hole).
    """
    area = _signed_area_2d(poly2d)
    if is_outer and area < 0:
        poly2d = list(reversed(poly2d))
    elif (not is_outer) and area > 0:
        poly2d = list(reversed(poly2d))

    n = len(poly2d)
    coedges: List[Coedge] = []
    for i in range(n):
        p0_3d = plane.to_3d(poly2d[i])
        p1_3d = plane.to_3d(poly2d[(i + 1) % n])
        v0 = Vertex(point=p0_3d)
        v1 = Vertex(point=p1_3d)
        line = Line3(p0=p0_3d, p1=p1_3d)
        edge = Edge(curve=line, t0=0.0, t1=1.0, v_start=v0, v_end=v1)
        coedges.append(Coedge(edge=edge, orientation=True))
    return Loop(coedges=coedges, is_outer=is_outer)


def _polys_to_face(polys: List[List[np.ndarray]], plane: _Plane2D) -> Optional[Face]:
    """Convert a list of result polygons to a Face with outer + hole loops.

    Classification logic:
    - The polygon with the largest absolute area becomes the outer loop (CCW).
    - All other polygons whose signed area (relative to the outer loop's CCW
      orientation) is negative become hole loops (CW).
    - Polygons entirely inside the outer loop with positive area (islands)
      become additional outer loops on separate faces; for the boolean
      primitives here there is at most one outer + N holes.
    """
    if not polys:
        return None

    # Sort by absolute area descending; first is the outer boundary
    areas = [_signed_area_2d(p) for p in polys]
    abs_areas = [abs(a) for a in areas]
    idx_outer = max(range(len(polys)), key=lambda i: abs_areas[i])

    outer_poly = polys[idx_outer]
    # Ensure outer is CCW
    if areas[idx_outer] < 0:
        outer_poly = list(reversed(outer_poly))
    outer_loop = _poly_to_loop(outer_poly, plane, is_outer=True)

    hole_loops: List[Loop] = []
    for i, poly in enumerate(polys):
        if i == idx_outer:
            continue
        # Treat every other polygon as a hole (CW)
        hl = _poly_to_loop(poly, plane, is_outer=False)
        hole_loops.append(hl)

    # Build Plane surface for the Face
    surface = Plane(
        origin=plane.origin.copy(),
        x_axis=plane.x_axis.copy(),
        y_axis=plane.y_axis.copy(),
    )
    loops = [outer_loop] + hole_loops
    return Face(surface=surface, loops=loops)


# ---------------------------------------------------------------------------
# Area utility (works on Face or individual Loop)
# ---------------------------------------------------------------------------

def region_area(face_or_loop, plane: Optional[_Plane2D] = None) -> float:
    """Signed 2-D area of a :class:`Face` or :class:`Loop`.

    For a :class:`Face`, sums the signed areas of all loops (outer CCW →
    positive; inner CW → negative), giving the net filled area.
    For a single :class:`Loop`, returns the signed area of that loop.

    Sign convention: positive = counter-clockwise when viewed along the
    plane normal.
    """
    if isinstance(face_or_loop, Face):
        total = 0.0
        for lp in face_or_loop.loops:
            total += _loop_area(lp, plane)
        return total
    return _loop_area(face_or_loop, plane)


def _arc_area_exact(arc: CircleArc3, t0: float, t1: float,
                    plane: _Plane2D) -> float:
    """Exact signed area contribution of a :class:`CircleArc3` coedge.

    Uses the analytic form of Green's theorem ``½∮(x dy − y dx)`` for a
    circular arc.  The arc center and radius are projected into the 2-D
    frame; the arc parameter ``t`` is the angle in the arc's own plane, so
    this remains exact regardless of tessellation.

    For the 2-D projection of center ``(cx, cy)`` and radius ``r``:

    .. math::

        \\frac{1}{2}\\int_{t_0}^{t_1}\\bigl(x\\,dy - y\\,dx\\bigr)
        = \\frac{r}{2}\\bigl[c_x(\\sin t_1 - \\sin t_0)
                            - c_y(\\cos t_1 - \\cos t_0)
                            + r(t_1 - t_0)\\bigr]

    This is the exact (not approximated) signed area.
    """
    c3 = np.asarray(arc.center, dtype=float)
    cx, cy = plane.to_2d(c3)
    r = arc.radius

    # The arc.evaluate uses arc's own x_axis / y_axis, which may not align
    # with the plane.  Project one point to figure out the angular offset.
    # p(t) = center + r*cos(t)*x_axis + r*sin(t)*y_axis
    # In 2-D:
    #   px(t) = cx + r*cos(t)*dot(x_axis,plane.x) + r*sin(t)*dot(y_axis,plane.x)
    #         = cx + r*(a*cos(t) + b*sin(t))
    #   py(t) = cy + r*cos(t)*dot(x_axis,plane.y) + r*sin(t)*dot(y_axis,plane.y)
    #         = cy + r*(c*cos(t) + d*sin(t))
    # where a=dot(x_axis,plane.x), b=dot(y_axis,plane.x), etc.
    a = float(np.dot(arc.x_axis, plane.x_axis))
    b = float(np.dot(arc.y_axis, plane.x_axis))
    c = float(np.dot(arc.x_axis, plane.y_axis))
    d = float(np.dot(arc.y_axis, plane.y_axis))

    # ½∫(x dy − y dx) over [t0, t1]
    # x(t) = cx + r*(a cos t + b sin t)
    # y(t) = cy + r*(c cos t + d sin t)
    # dx = r*(-a sin t + b cos t) dt
    # dy = r*(-c sin t + d cos t) dt
    #
    # x dy − y dx =
    #   [cx + r*(a cos t + b sin t)]*r*(-c sin t + d cos t) dt
    # − [cy + r*(c cos t + d sin t)]*r*(-a sin t + b cos t) dt
    #
    # Constant × variable terms:
    #   cx * r * (d cos t - c sin t)
    # - cy * r * (b cos t - a sin t)
    # + r² * [(a cos t + b sin t)(d cos t - c sin t)
    #       - (c cos t + d sin t)(b cos t - a sin t)]
    #
    # The r² bracket expands to:
    #   ad cos²t - ac sin t cos t + bd sin t cos t - bc sin²t
    # − [bc cos²t - ac sin t cos t + bd sin t cos t - ad sin²t]
    # = ad cos²t - bc sin²t - bc cos²t + ad sin²t
    # = ad(cos²t + sin²t) - bc(sin²t + cos²t)
    # = ad - bc   (a constant!)
    #
    # So: x dy − y dx = [cx*r*(d cos t - c sin t) - cy*r*(b cos t - a sin t)
    #                    + r²*(ad-bc)] dt
    #
    # Integrating from t0 to t1:
    # ½ * { cx*r*[d sin t + c cos t] - cy*r*[b sin t - a cos t]
    #       + r²*(ad-bc)*t } |_{t0}^{t1}

    def F(t: float) -> float:
        return (
            cx * r * (d * math.sin(t) + c * math.cos(t))
            - cy * r * (b * math.sin(t) - a * math.cos(t))
            + r * r * (a * d - b * c) * t
        )

    return 0.5 * (F(t1) - F(t0))


def _loop_area(loop: Loop, plane: Optional[_Plane2D] = None) -> float:
    """Exact signed 2-D area of a Loop using Green's theorem.

    For :class:`Line3` edges the shoelace formula is exact.
    For :class:`CircleArc3` edges the analytic integral is used
    (see :func:`_arc_area_exact`), giving machine-precision results.

    The accumulator collects ``x·dy − y·dx`` terms (without the ½ factor);
    the factor of ½ is applied once at the end.  Arc terms are already
    ½-scaled by :func:`_arc_area_exact`, so they are added with ×2 to
    cancel the outer ½.
    """
    if plane is None:
        plane = getattr(loop, "_region2d_plane", None)
    if plane is None:
        plane = _detect_plane(loop)
    if plane is None:
        return 0.0

    total = 0.0  # accumulates ∮(x dy − y dx) / 2  (the ½ is distributed)
    for ce in loop.coedges:
        e = ce.edge
        curve = e.curve
        t0, t1 = (e.t0, e.t1) if ce.orientation else (e.t1, e.t0)
        if isinstance(curve, CircleArc3):
            # _arc_area_exact already returns the ½-scaled value
            total += _arc_area_exact(curve, t0, t1, plane)
        else:
            # Line segment: shoelace contribution (unscaled; factor of ½ below)
            p0 = plane.to_2d(np.asarray(curve.evaluate(t0), dtype=float))
            p1 = plane.to_2d(np.asarray(curve.evaluate(t1), dtype=float))
            total += 0.5 * (p0[0] * p1[1] - p1[0] * p0[1])
    return total


# ---------------------------------------------------------------------------
# Core boolean dispatcher
# ---------------------------------------------------------------------------

def _rebuild_loop_cw(loop: Loop, plane: _Plane2D) -> Loop:
    """Return a copy of *loop* with reversed coedge orientation (CW hole loop).

    The coedge list is reversed and each coedge orientation flag is flipped.
    Curve objects are reused (not copied) to preserve exact geometry.
    """
    new_coedges: List[Coedge] = []
    for ce in reversed(loop.coedges):
        new_ce = Coedge(edge=ce.edge, orientation=not ce.orientation)
        new_coedges.append(new_ce)
    new_loop = Loop(coedges=new_coedges, is_outer=False)
    new_loop._region2d_plane = plane  # type: ignore[attr-defined]
    return new_loop


def _rebuild_loop_ccw(loop: Loop, plane: _Plane2D) -> Loop:
    """Return a copy of *loop* with CCW orientation (outer loop).

    If the loop is already CCW the coedges are shallow-copied as-is; otherwise
    they are reversed and orientation-flipped.
    """
    area = _loop_area(loop, plane)
    if area >= 0:
        new_coedges = [Coedge(edge=ce.edge, orientation=ce.orientation)
                       for ce in loop.coedges]
    else:
        new_coedges = [Coedge(edge=ce.edge, orientation=not ce.orientation)
                       for ce in reversed(loop.coedges)]
    new_loop = Loop(coedges=new_coedges, is_outer=True)
    new_loop._region2d_plane = plane  # type: ignore[attr-defined]
    return new_loop


def _boolean(loop_a: Loop, loop_b: Loop, operation: str) -> Optional[Face]:
    """Core boolean operation returning a Face with correct loop orientations.

    For the containment-only case (no boundary intersections), the original
    arc / curve geometry is preserved so that ``region_area`` is exact.
    """
    plane = _detect_plane(loop_a) or _detect_plane(loop_b)
    if plane is None:
        return None

    poly_a = _tessellate_loop(loop_a, plane)
    poly_b = _tessellate_loop(loop_b, plane)
    if len(poly_a) < 3 or len(poly_b) < 3:
        return None

    # Determine whether boundary intersections exist
    na, nb = len(poly_a), len(poly_b)
    has_x = any(
        _seg_isect(poly_a[i], poly_a[(i + 1) % na],
                   poly_b[j], poly_b[(j + 1) % nb]) is not None
        for i in range(na) for j in range(nb)
    )

    # Handle vertex-on-boundary degeneracy: intersections happen at
    # polygon vertices (α=0 or α=1), which are filtered by _seg_isect.
    # Apply a small inward perturbation to poly_b to detect these cases.
    poly_b_for_clip = poly_b  # may be replaced by perturbed version
    if not has_x:
        scale = (max(
            abs(poly_a[i][k] - poly_a[j][k])
            for i in range(na) for j in range(na) for k in range(2)
        ) if na > 1 else 1.0)
        eps = scale * 1e-5
        centroid_b = np.mean(poly_b, axis=0)
        poly_b_pert = [centroid_b + (1.0 - eps) * (p - centroid_b)
                       for p in poly_b]
        if any(
            _seg_isect(poly_a[i], poly_a[(i + 1) % na],
                       poly_b_pert[j], poly_b_pert[(j + 1) % nb]) is not None
            for i in range(na) for j in range(nb)
        ):
            has_x = True
            poly_b_for_clip = poly_b_pert

    surface = Plane(
        origin=plane.origin.copy(),
        x_axis=plane.x_axis.copy(),
        y_axis=plane.y_axis.copy(),
    )

    if not has_x:
        # No boundary crossing after perturbation → purely containment or disjoint.
        # Use exact loop geometry (preserves arcs).
        area_a = abs(_signed_area_2d(poly_a))
        area_b = abs(_signed_area_2d(poly_b))
        centroid_a = np.mean(poly_a, axis=0)
        centroid_b = np.mean(poly_b, axis=0)
        b_centroid_in_a = _point_in_poly(centroid_b, poly_a)
        a_centroid_in_b = _point_in_poly(centroid_a, poly_b)
        b_inside_a = b_centroid_in_a and area_b <= area_a
        a_inside_b = a_centroid_in_b and area_a <= area_b

        tol_area = 1e-6 * max(area_a, area_b, 1e-12)
        same = abs(area_a - area_b) < tol_area and float(
            np.linalg.norm(centroid_a - centroid_b)
        ) < 1e-6 * (math.sqrt(max(area_a, area_b)) + 1e-12)

        if operation == "difference":
            if same or a_inside_b:
                return None   # A − B = empty
            if b_inside_a:
                # B is a hole inside A — preserve exact arc geometry
                outer = _rebuild_loop_ccw(loop_a, plane)
                hole  = _rebuild_loop_cw(loop_b, plane)
                return Face(surface=surface, loops=[outer, hole])
            # Disjoint: A unchanged
            outer = _rebuild_loop_ccw(loop_a, plane)
            return Face(surface=surface, loops=[outer])

        elif operation == "union":
            if same or b_inside_a:
                outer = _rebuild_loop_ccw(loop_a, plane)
                return Face(surface=surface, loops=[outer])
            if a_inside_b:
                outer = _rebuild_loop_ccw(loop_b, plane)
                return Face(surface=surface, loops=[outer])
            # Disjoint: two separate CCW loops in one face
            outer_a = _rebuild_loop_ccw(loop_a, plane)
            outer_b = _rebuild_loop_ccw(loop_b, plane)
            outer_b.is_outer = True
            return Face(surface=surface, loops=[outer_a, outer_b])

        else:  # intersection
            if same:
                outer = _rebuild_loop_ccw(loop_a, plane)
                return Face(surface=surface, loops=[outer])
            if b_inside_a:
                outer = _rebuild_loop_ccw(loop_b, plane)
                return Face(surface=surface, loops=[outer])
            if a_inside_b:
                outer = _rebuild_loop_ccw(loop_a, plane)
                return Face(surface=surface, loops=[outer])
            return None   # disjoint → empty intersection

    # Boundary intersections exist → GH clipping path
    polys = _clip(poly_a, poly_b_for_clip, operation)
    face = _polys_to_face(polys, plane)
    if face is not None:
        for lp in face.loops:
            lp._region2d_plane = plane  # type: ignore[attr-defined]
    return face


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def region_union(loop_a: Loop, loop_b: Loop) -> Optional[Face]:
    """2-D union of two planar loops → :class:`Face`.

    Returns a :class:`Face` whose outer loop (CCW) is the union boundary.
    If the loops do not overlap, the result contains two disjoint outer-loop
    polygons merged into a single :class:`Face` (the larger as outer, the
    smaller treated as a second polygon — callers that need separate faces
    should inspect ``face.loops``).
    Returns ``None`` when the input geometry is degenerate.
    """
    return _boolean(loop_a, loop_b, "union")


def region_intersection(loop_a: Loop, loop_b: Loop) -> Optional[Face]:
    """2-D intersection of two planar loops → :class:`Face`.

    Returns ``None`` when the loops do not overlap.
    """
    return _boolean(loop_a, loop_b, "intersection")


def region_difference(loop_a: Loop, loop_b: Loop) -> Optional[Face]:
    """2-D difference *loop_a* − *loop_b* → :class:`Face`.

    When *loop_b* is entirely inside *loop_a* the result :class:`Face` has
    one outer CCW loop and one inner CW hole loop, and
    ``region_area(face) == area(A) − area(B)``.

    Returns ``None`` when the result is empty (loop_a fully inside loop_b).
    """
    return _boolean(loop_a, loop_b, "difference")


# ---------------------------------------------------------------------------
# Convenience loop builders
# ---------------------------------------------------------------------------

def make_rect_loop(x0: float, y0: float, x1: float, y1: float) -> Loop:
    """Build a CCW rectangular :class:`Loop` in the z=0 plane."""
    corners = [
        np.array([x0, y0, 0.0]),
        np.array([x1, y0, 0.0]),
        np.array([x1, y1, 0.0]),
        np.array([x0, y1, 0.0]),
    ]
    coedges: List[Coedge] = []
    n = len(corners)
    for i in range(n):
        p0, p1 = corners[i], corners[(i + 1) % n]
        v0, v1 = Vertex(point=p0), Vertex(point=p1)
        line = Line3(p0=p0, p1=p1)
        edge = Edge(curve=line, t0=0.0, t1=1.0, v_start=v0, v_end=v1)
        coedges.append(Coedge(edge=edge, orientation=True))
    return Loop(coedges=coedges, is_outer=True)


def make_circle_loop(cx: float, cy: float, radius: float,
                     n_segs: int = 64) -> Loop:
    """Build a CCW circular :class:`Loop` in the z=0 plane.

    Uses a single full-circle :class:`CircleArc3` edge (t0=0, t1=2π).
    ``n_segs`` is ignored (kept for API compatibility); arc subdivision is
    controlled by ``_ARC_CHORD_TOL`` at use time.
    """
    center = np.array([cx, cy, 0.0])
    x_axis = np.array([1.0, 0.0, 0.0])
    y_axis = np.array([0.0, 1.0, 0.0])
    arc = CircleArc3(
        center=center,
        radius=radius,
        x_axis=x_axis,
        y_axis=y_axis,
        t0=0.0,
        t1=2.0 * math.pi,
    )
    p_start = np.asarray(arc.evaluate(0.0), dtype=float)
    v = Vertex(point=p_start)
    edge = Edge(curve=arc, t0=0.0, t1=2.0 * math.pi, v_start=v, v_end=v)
    return Loop(coedges=[Coedge(edge=edge, orientation=True)], is_outer=True)
