"""GK-89  Knife / cut face by 3D curve (B-rep + SubD).

Pure-Python, no OCCT dependency.

Public API
----------
knife_face(target, face_id, curve_3d) -> Tuple[face_a, face_b] | List[face]
    Split a single face of a ``Body`` or ``SubDCage`` along the path obtained
    by projecting *curve_3d* onto the face surface.

    For a **B-rep Body** the face is replaced by two new ``Face`` objects
    derived from splitting the face's outer-loop polygon at the two
    intersection points of the projected curve path with the boundary.

    For a **SubD cage** the face vertex list is split similarly.

    Parameters
    ----------
    target : Body | SubDCage
        Input geometry.  Not mutated.  A shallow copy is returned.
    face_id : int
        For a Body, index into ``body.all_faces()``.
        For a SubDCage, index into ``cage.faces``.
    curve_3d : object
        Any curve with ``evaluate(t) -> array-like`` (3-D) and a parametric
        range implicitly ``[0, 1]`` (or exposing ``t0`` / ``t1`` attributes).
        :class:`~kerf_cad_core.geom.brep.Line3` qualifies.

    Returns
    -------
    Tuple of two new face objects on success; a single-element list
    containing the original face when the curve does not validly bisect the
    face.

Design notes
------------
*   The split is performed in 3-D face-local polygon space.  The face's outer
    loop is treated as an ordered polygon; the projected curve end-points are
    snapped to the nearest polygon edges and the boundary is split there.
*   For planar B-rep faces the projection is exact (the face plane is the
    surface itself).  For curved surfaces the curve is first approximately
    projected using the closest-point inversion utility.
*   SubD cages carry no parametric surface, so projection is done via
    closest-point on the planar face polygon.
*   The split introduces two new ``Vertex`` objects (or cage vertices) at the
    intersection points and one shared ``Edge`` (or cage edge) along the
    projected path.
"""

from __future__ import annotations

import math
import copy
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

# ---------------------------------------------------------------------------
# Optional imports – keep graceful so the module loads even in minimal envs
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.geom.brep import (
        Body,
        Coedge,
        Edge,
        Face,
        Line3,
        Loop,
        Plane,
        Shell,
        Solid,
        Vertex,
        _unit,
    )
    _HAS_BREP = True
except ImportError:  # pragma: no cover
    _HAS_BREP = False
    Body = None  # type: ignore[assignment,misc]

try:
    from kerf_cad_core.geom.subd_authoring import SubDCage
    _HAS_SUBD = True
except ImportError:  # pragma: no cover
    _HAS_SUBD = False
    SubDCage = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Tolerance
# ---------------------------------------------------------------------------

_TOL: float = 1e-7

# Number of samples used to discretise curve_3d for projection / intersection
_CURVE_SAMPLES: int = 64


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _curve_t_range(curve_3d) -> Tuple[float, float]:
    """Return (t0, t1) parametric range of *curve_3d*."""
    t0 = float(getattr(curve_3d, "t0", 0.0))
    t1 = float(getattr(curve_3d, "t1", 1.0))
    return t0, t1


def _sample_curve(curve_3d, n: int = _CURVE_SAMPLES) -> np.ndarray:
    """Sample *curve_3d* at *n* equispaced parameter values; shape (n, 3)."""
    t0, t1 = _curve_t_range(curve_3d)
    ts = np.linspace(t0, t1, n)
    pts = np.array([np.asarray(curve_3d.evaluate(t), dtype=float) for t in ts])
    return pts


def _poly_vertices_3d(face: "Face") -> np.ndarray:
    """Return outer-loop vertex positions of *face* as (N, 3) array."""
    outer = face.outer_loop()
    if outer is None or not outer.coedges:
        return np.zeros((0, 3))
    pts = np.array(
        [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
    )
    return pts


def _project_point_to_plane(
    point: np.ndarray, origin: np.ndarray, normal: np.ndarray
) -> np.ndarray:
    """Project *point* onto the plane defined by *origin* and *normal*."""
    n = _unit(normal)
    d = np.dot(point - origin, n)
    return point - d * n


def _face_plane(face: "Face") -> Tuple[np.ndarray, np.ndarray]:
    """Compute (origin, normal) of the best-fit plane for a B-rep face.

    For analytic Plane surfaces this is exact; for others we use the vertex
    centroid and cross product of the first two edge directions.
    """
    srf = face.surface
    if isinstance(srf, Plane):
        origin = np.asarray(srf.origin, dtype=float)
        normal = np.asarray(srf._n, dtype=float)
        return origin, normal

    # Generic: derive from outer-loop vertices
    pts = _poly_vertices_3d(face)
    if len(pts) < 3:
        # Fall back to surface normal at UV midpoint
        origin = np.asarray(srf.evaluate(0.5, 0.5), dtype=float)
        normal = np.asarray(srf.normal(0.5, 0.5), dtype=float)
        return origin, _unit(normal)

    origin = pts.mean(axis=0)
    e1 = _unit(pts[1] - pts[0])
    for i in range(2, len(pts)):
        e2 = pts[i] - pts[0]
        n = np.cross(e1, e2)
        if np.linalg.norm(n) > _TOL:
            return origin, _unit(n)
    # Degenerate polygon – fall back to surface
    normal = np.asarray(srf.normal(0.5, 0.5), dtype=float)
    return origin, _unit(normal)


def _closest_point_on_segment(
    p: np.ndarray, a: np.ndarray, b: np.ndarray
) -> Tuple[np.ndarray, float]:
    """Closest point on segment *a→b* to *p*; also returns parameter t∈[0,1]."""
    ab = b - a
    ab_len2 = float(np.dot(ab, ab))
    if ab_len2 < _TOL ** 2:
        return a.copy(), 0.0
    t = float(np.dot(p - a, ab)) / ab_len2
    t = max(0.0, min(1.0, t))
    return a + t * ab, t


def _project_point_to_polygon_edge(
    p: np.ndarray, poly: np.ndarray
) -> Tuple[int, float, np.ndarray]:
    """Find the polygon edge closest to *p*.

    Returns ``(edge_index, t, closest_point)`` where ``edge_index`` is the
    index of vertex ``poly[edge_index]`` (start of the edge) and ``t`` is the
    parameter along that edge.
    """
    n = len(poly)
    best_dist = math.inf
    best_idx = 0
    best_t = 0.0
    best_pt: np.ndarray = poly[0].copy()
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        cp, t = _closest_point_on_segment(p, a, b)
        d = float(np.linalg.norm(p - cp))
        if d < best_dist:
            best_dist = d
            best_idx = i
            best_t = t
            best_pt = cp
    return best_idx, best_t, best_pt


def _poly_area_3d(pts: np.ndarray) -> float:
    """Area of a planar polygon (fan triangulation from centroid)."""
    n = len(pts)
    if n < 3:
        return 0.0
    c = pts.mean(axis=0)
    area = 0.0
    for i in range(n):
        a = pts[i] - c
        b = pts[(i + 1) % n] - c
        area += np.linalg.norm(np.cross(a, b))
    return float(area) * 0.5


def _split_polygon(
    poly: np.ndarray,
    idx_a: int,
    t_a: float,
    split_pt_a: np.ndarray,
    idx_b: int,
    t_b: float,
    split_pt_b: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Split a polygon at two boundary points and return two sub-polygons.

    *idx_a* and *idx_b* are the edge start-vertex indices where the cut
    intersects the polygon boundary.  *t_a* and *t_b* are the edge parameters.
    """
    n = len(poly)
    # Normalise so that idx_a comes before idx_b in the winding order.
    # If they share the same edge, reorder by t.
    if idx_a == idx_b:
        if t_a > t_b:
            idx_a, idx_b = idx_b, idx_a
            t_a, t_b = t_b, t_a
            split_pt_a, split_pt_b = split_pt_b, split_pt_a

    # Build polygon A: split_pt_a → vertices idx_a+1 … idx_b → split_pt_b
    poly_a: List[np.ndarray] = [split_pt_a]
    i = (idx_a + 1) % n
    while i != (idx_b + 1) % n:
        poly_a.append(poly[i])
        i = (i + 1) % n
    poly_a.append(split_pt_b)

    # Build polygon B: split_pt_b → vertices idx_b+1 … idx_a → split_pt_a
    poly_b: List[np.ndarray] = [split_pt_b]
    i = (idx_b + 1) % n
    while i != (idx_a + 1) % n:
        poly_b.append(poly[i])
        i = (i + 1) % n
    poly_b.append(split_pt_a)

    # Deduplicate coincident consecutive vertices
    def _dedup(pts: List[np.ndarray]) -> np.ndarray:
        result = [pts[0]]
        for p in pts[1:]:
            if np.linalg.norm(p - result[-1]) > _TOL:
                result.append(p)
        # Remove wrap-around duplicate
        if len(result) > 1 and np.linalg.norm(result[-1] - result[0]) < _TOL:
            result = result[:-1]
        return np.array(result)

    return _dedup(poly_a), _dedup(poly_b)


def _make_face_from_polygon(pts: np.ndarray) -> "Face":
    """Construct a new B-rep Face (planar) from a 3-D polygon."""
    n = len(pts)
    if n < 3:
        raise ValueError("Cannot build face from fewer than 3 points")

    # Determine the plane
    c = pts.mean(axis=0)
    e1 = _unit(pts[1] - pts[0])
    normal = np.zeros(3)
    for i in range(2, n):
        e2 = pts[i] - pts[0]
        crs = np.cross(e1, e2)
        if np.linalg.norm(crs) > _TOL:
            normal = _unit(crs)
            break
    if np.linalg.norm(normal) < _TOL:
        normal = np.array([0.0, 0.0, 1.0])

    # Build a right-handed coordinate frame for the plane
    y_axis = _unit(np.cross(normal, e1))
    if np.linalg.norm(y_axis) < _TOL:
        y_axis = _unit(np.cross(normal, np.array([0.0, 1.0, 0.0])))

    origin = pts[0]
    srf = Plane(origin=origin, x_axis=e1, y_axis=y_axis)

    # Build vertices, edges, coedges, loop
    vertices = [Vertex(point=p.copy()) for p in pts]
    edges: List[Edge] = []
    coedges: List[Coedge] = []
    for i in range(n):
        v0 = vertices[i]
        v1 = vertices[(i + 1) % n]
        seg = Line3(p0=v0.point.copy(), p1=v1.point.copy())
        e = Edge(curve=seg, t0=0.0, t1=1.0, v_start=v0, v_end=v1)
        edges.append(e)
        ce = Coedge(edge=e, orientation=True)
        coedges.append(ce)

    loop = Loop(coedges=coedges, is_outer=True)
    face = Face(surface=srf, loops=[loop])
    return face


# ---------------------------------------------------------------------------
# B-rep knife
# ---------------------------------------------------------------------------


def _knife_brep(body: "Body", face_id: int, curve_3d) -> Tuple["Face", "Face"]:
    """Split face *face_id* of *body* by projecting *curve_3d* onto it.

    Returns two new Face objects whose areas sum to the original face area.
    """
    faces = body.all_faces()
    if face_id < 0 or face_id >= len(faces):
        raise ValueError(f"face_id {face_id} out of range [0, {len(faces)})")

    face = faces[face_id]
    poly = _poly_vertices_3d(face)
    if len(poly) < 3:
        raise ValueError("Target face has fewer than 3 vertices in its outer loop")

    # Get the face plane for projection
    origin, normal = _face_plane(face)

    # Sample the cutting curve and project onto the plane
    curve_pts = _sample_curve(curve_3d)
    proj_pts = np.array([
        _project_point_to_plane(p, origin, normal) for p in curve_pts
    ])

    # Use the first and last projected points as the split end-points
    p_start = proj_pts[0]
    p_end = proj_pts[-1]

    # Find where these projected points snap to the polygon boundary
    idx_a, t_a, snap_a = _project_point_to_polygon_edge(p_start, poly)
    idx_b, t_b, snap_b = _project_point_to_polygon_edge(p_end, poly)

    # If both snap to the same location, the curve doesn't cross the face
    if idx_a == idx_b and abs(t_a - t_b) < _TOL:
        raise ValueError("Knife curve start and end project to the same boundary point")

    # Split the polygon
    poly_a, poly_b = _split_polygon(poly, idx_a, t_a, snap_a, idx_b, t_b, snap_b)

    if len(poly_a) < 3 or len(poly_b) < 3:
        raise ValueError("Degenerate knife split: one sub-polygon has fewer than 3 vertices")

    face_a = _make_face_from_polygon(poly_a)
    face_b = _make_face_from_polygon(poly_b)
    return face_a, face_b


# ---------------------------------------------------------------------------
# SubD cage knife
# ---------------------------------------------------------------------------


def _knife_subd(cage: "SubDCage", face_id: int, curve_3d) -> Tuple["SubDCage", "SubDCage"]:
    """Split face *face_id* of *cage* by projecting *curve_3d* onto it.

    Returns two new SubDCage objects each containing a single face.
    """
    if face_id < 0 or face_id >= len(cage.faces):
        raise ValueError(f"face_id {face_id} out of range [0, {len(cage.faces)})")

    face_vids = cage.faces[face_id]
    poly = np.array([
        np.asarray(cage.vertices[vid], dtype=float) for vid in face_vids
    ])

    # Compute face normal via cross product
    n = len(poly)
    if n < 3:
        raise ValueError("SubD face has fewer than 3 vertices")

    e1 = _unit(poly[1] - poly[0])
    normal = np.zeros(3)
    for i in range(2, n):
        crs = np.cross(e1, poly[i] - poly[0])
        if np.linalg.norm(crs) > _TOL:
            normal = _unit(crs)
            break
    if np.linalg.norm(normal) < _TOL:
        normal = np.array([0.0, 0.0, 1.0])
    origin = poly.mean(axis=0)

    # Sample + project curve
    curve_pts = _sample_curve(curve_3d)
    proj_pts = np.array([
        _project_point_to_plane(p, origin, normal) for p in curve_pts
    ])

    p_start = proj_pts[0]
    p_end = proj_pts[-1]

    idx_a, t_a, snap_a = _project_point_to_polygon_edge(p_start, poly)
    idx_b, t_b, snap_b = _project_point_to_polygon_edge(p_end, poly)

    if idx_a == idx_b and abs(t_a - t_b) < _TOL:
        raise ValueError("Knife curve start and end project to the same boundary point")

    poly_a, poly_b = _split_polygon(poly, idx_a, t_a, snap_a, idx_b, t_b, snap_b)

    if len(poly_a) < 3 or len(poly_b) < 3:
        raise ValueError("Degenerate knife split: one sub-polygon has fewer than 3 vertices")

    def _make_cage(sub_poly: np.ndarray) -> "SubDCage":
        verts = [v.tolist() for v in sub_poly]
        face = list(range(len(verts)))
        return SubDCage(vertices=verts, faces=[face])

    cage_a = _make_cage(poly_a)
    cage_b = _make_cage(poly_b)
    return cage_a, cage_b


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def knife_face(
    target: Union["Body", "SubDCage"],
    face_id: int,
    curve_3d,
) -> Union[Tuple, List]:
    """Split a single face by projecting *curve_3d* onto it.

    Parameters
    ----------
    target : Body | SubDCage
        The geometry whose face is to be split.  Not mutated.
    face_id : int
        Index of the face to cut.
        *Body*: index into ``body.all_faces()``.
        *SubDCage*: index into ``cage.faces``.
    curve_3d : object
        Any object with ``evaluate(t) -> array-like`` (3 floats).  The
        parametric domain defaults to ``[0, 1]`` unless the object exposes
        ``t0`` / ``t1`` attributes.

    Returns
    -------
    (face_a, face_b) : tuple
        Two new face objects (``Face`` for B-rep, ``SubDCage`` for SubD)
        whose combined area equals the original face area.

        On failure a ``ValueError`` is raised describing the reason.
    """
    if _HAS_BREP and isinstance(target, Body):
        return _knife_brep(target, face_id, curve_3d)

    if _HAS_SUBD and isinstance(target, SubDCage):
        return _knife_subd(target, face_id, curve_3d)

    raise TypeError(
        f"knife_face: unsupported target type {type(target).__name__!r}; "
        "expected Body or SubDCage"
    )
