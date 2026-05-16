"""
section_contour.py
==================
Pure-Python Section / Contour / Silhouette / Isoline curves
(Rhino Section, Contour, Silhouette parity).

Operates on plain indexed triangle meshes (verts/faces lists) and on
NurbsSurface objects from geom/nurbs.py.  Never raises; all failures are
returned as ``{"ok": False, "reason": "..."}``.

Public API
----------
section_by_plane(mesh_or_surface, plane) -> dict
    Intersect a mesh or surface with a plane and return ordered polyline loops.
    For a mesh:   Marching-Triangles — sign-change test per triangle edge.
    For a surface: UV-grid sampling + isoline extraction by linear interpolation.
    Returns:
        ok, loops (list[list[[x,y,z]]]), loop_count, plane_normal, plane_d.

contour(mesh_or_surface, axis_dir, spacing, *, origin=None) -> dict
    Emit a series of parallel section curves at fixed spacing along *axis_dir*.
    Returns:
        ok, sections (list[dict — one per level, each with z_value and loops]),
        level_count.

silhouette(mesh, view_dir) -> dict
    Silhouette edges: sign-change of dot(face_normal, view_dir) across adjacent
    faces.  Returns polyline chains as lists of [x,y,z].
    Returns:
        ok, chains (list[list[[x,y,z]]]), edge_count.

isoline(surface, direction, value, *, num_samples=64) -> dict
    Direct isoparametric curve: direction ∈ {"u","v"}.
    Returns:
        ok, points (list[[x,y,z]]), parameter_direction, parameter_value.

All output polylines are plain Python lists of [x, y, z] floats.
LLM tools registered via @register (gated, mirrors trim_curve.py pattern).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, find_span

# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

Vert = List[float]  # [x, y, z]
Face = List[int]    # [i, j, k]
Point3 = List[float]
Polyline = List[Point3]


# ---------------------------------------------------------------------------
# Correct Cox-de Boor basis functions (same pattern as surface_analysis.py)
# ---------------------------------------------------------------------------

def _basis_fns(i: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    N = np.zeros(degree + 1)
    N[0] = 1.0
    left = np.zeros(degree + 1)
    right = np.zeros(degree + 1)
    for j in range(1, degree + 1):
        left[j] = u - knots[i + 1 - j]
        right[j] = knots[i + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            if abs(denom) < 1e-15:
                temp = 0.0
            else:
                temp = N[r] / denom
            N[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        N[j] = saved
    return N


def _eval_surface(surf: NurbsSurface, u: float, v: float) -> np.ndarray:
    nu = surf.num_control_points_u
    nv = surf.num_control_points_v
    span_u = find_span(nu - 1, surf.degree_u, u, surf.knots_u)
    span_v = find_span(nv - 1, surf.degree_v, v, surf.knots_v)
    Nu = _basis_fns(span_u, u, surf.degree_u, surf.knots_u)
    Nv = _basis_fns(span_v, v, surf.degree_v, surf.knots_v)
    dim = surf.control_points.shape[2]
    result = np.zeros(dim)
    for i in range(surf.degree_u + 1):
        for j in range(surf.degree_v + 1):
            idx_i = span_u - surf.degree_u + i
            idx_j = span_v - surf.degree_v + j
            result += Nu[i] * Nv[j] * surf.control_points[idx_i, idx_j]
    return result


# ---------------------------------------------------------------------------
# Plane helpers
# ---------------------------------------------------------------------------

def _parse_plane(plane: Any) -> Tuple[np.ndarray, float]:
    """Parse plane specification into (normal, d) where n·x = d.

    Accepts:
      {"normal": [nx, ny, nz], "d": d}
      {"normal": [nx, ny, nz], "point": [px, py, pz]}
      (normal_array, d_scalar)
      (normal_array, point_array)  — tuple of two array-likes
    """
    if isinstance(plane, dict):
        n = np.asarray(plane["normal"], dtype=float)
        nrm = float(np.linalg.norm(n))
        if nrm < 1e-15:
            raise ValueError("plane normal is zero vector")
        n /= nrm
        if "d" in plane:
            d = float(plane["d"])
        elif "point" in plane:
            p = np.asarray(plane["point"], dtype=float)
            d = float(np.dot(n, p))
        else:
            raise ValueError("plane dict must have 'd' or 'point'")
        return n, d

    if isinstance(plane, (list, tuple)) and len(plane) == 2:
        n = np.asarray(plane[0], dtype=float).ravel()
        nrm = float(np.linalg.norm(n))
        if nrm < 1e-15:
            raise ValueError("plane normal is zero vector")
        n /= nrm
        second = np.asarray(plane[1], dtype=float).ravel()
        if second.size == 1:
            d = float(second[0])
        else:
            d = float(np.dot(n, second[:3]))
        return n, d

    raise ValueError(f"unrecognised plane specification: {plane!r}")


def _signed_dist(v: Sequence[float], n: np.ndarray, d: float) -> float:
    return float(np.dot(n, np.asarray(v, dtype=float)[:3])) - d


# ---------------------------------------------------------------------------
# Mesh section helpers — Marching-Triangles
# ---------------------------------------------------------------------------

def _lerp3(a: Sequence[float], b: Sequence[float], t: float) -> Point3:
    ax, ay, az = float(a[0]), float(a[1]), float(a[2])
    bx, by, bz = float(b[0]), float(b[1]), float(b[2])
    return [ax + t * (bx - ax), ay + t * (by - ay), az + t * (bz - az)]


def _edge_key(i: int, j: int) -> Tuple[int, int]:
    return (min(i, j), max(i, j))


def _section_mesh(
    verts: List[Vert],
    faces: List[Face],
    n: np.ndarray,
    d: float,
) -> List[Polyline]:
    """Marching-Triangles plane section of an indexed triangle mesh."""
    if not verts or not faces:
        return []

    # signed distance per vertex
    sd = [_signed_dist(v, n, d) for v in verts]

    # collect edge-crossing segments
    segments: List[Tuple[Point3, Point3]] = []
    for face in faces:
        if len(face) < 3:
            continue
        i, j, k = int(face[0]), int(face[1]), int(face[2])
        if i >= len(verts) or j >= len(verts) or k >= len(verts):
            continue
        s = [sd[i], sd[j], sd[k]]
        pts = [verts[i], verts[j], verts[k]]
        # find the two edges that cross the plane
        cross_pts: List[Point3] = []
        edges = [(0, 1), (1, 2), (2, 0)]
        for ea, eb in edges:
            sa, sb = s[ea], s[eb]
            if (sa >= 0.0) != (sb >= 0.0):
                denom = sb - sa
                if abs(denom) < 1e-15:
                    t = 0.5
                else:
                    t = -sa / denom
                t = max(0.0, min(1.0, t))
                cross_pts.append(_lerp3(pts[ea], pts[eb], t))
        if len(cross_pts) == 2:
            segments.append((cross_pts[0], cross_pts[1]))

    return _chain_segments(segments)


def _pt_key(p: Point3, tol: float = 1e-9) -> Tuple[int, int, int]:
    scale = 1.0 / max(tol, 1e-12)
    return (round(p[0] * scale), round(p[1] * scale), round(p[2] * scale))


def _chain_segments(segments: List[Tuple[Point3, Point3]], tol: float = 1e-9) -> List[Polyline]:
    """Chain disconnected line segments into ordered polylines."""
    if not segments:
        return []

    # Build adjacency: endpoint_key -> list of (other_endpoint_key, seg_idx, is_start)
    key_to_pt: Dict[Tuple, Point3] = {}
    adj: Dict[Tuple, List[Tuple]] = defaultdict(list)

    for idx, (a, b) in enumerate(segments):
        ka = _pt_key(a, tol)
        kb = _pt_key(b, tol)
        key_to_pt[ka] = a
        key_to_pt[kb] = b
        adj[ka].append((kb, idx, True))
        adj[kb].append((ka, idx, False))

    used: set = set()
    chains: List[Polyline] = []

    for start_key in list(adj.keys()):
        if all(idx in used for (_, idx, _) in adj[start_key]):
            continue
        # start a new chain
        chain: Polyline = [key_to_pt[start_key]]
        cur = start_key
        while True:
            moved = False
            for (nxt, idx, _) in adj[cur]:
                if idx not in used:
                    used.add(idx)
                    chain.append(key_to_pt[nxt])
                    cur = nxt
                    moved = True
                    break
            if not moved:
                break
        if len(chain) >= 2:
            chains.append(chain)

    return chains


# ---------------------------------------------------------------------------
# Surface section helpers — UV-grid sampling + isoline extraction
# ---------------------------------------------------------------------------

def _section_surface(
    surf: NurbsSurface,
    n: np.ndarray,
    d: float,
    nu: int = 80,
    nv: int = 80,
) -> List[Polyline]:
    """Section a NurbsSurface by a plane via UV-grid sampling and linear interpolation."""
    u_min = float(surf.knots_u[0])
    u_max = float(surf.knots_u[-1])
    v_min = float(surf.knots_v[0])
    v_max = float(surf.knots_v[-1])

    us = np.linspace(u_min, u_max, max(nu, 4))
    vs = np.linspace(v_min, v_max, max(nv, 4))

    # evaluate grid
    grid = np.zeros((len(us), len(vs), 3))
    sd = np.zeros((len(us), len(vs)))
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            p = _eval_surface(surf, u, v)[:3]
            grid[i, j] = p
            sd[i, j] = float(np.dot(n, p)) - d

    segments: List[Tuple[Point3, Point3]] = []

    # walk horizontal grid lines (constant i, varying j)
    for i in range(len(us)):
        for j in range(len(vs) - 1):
            sa, sb = sd[i, j], sd[i, j + 1]
            if (sa >= 0.0) != (sb >= 0.0):
                t = -sa / (sb - sa) if abs(sb - sa) > 1e-15 else 0.5
                pa = grid[i, j].tolist()
                pb = grid[i, j + 1].tolist()
                segments.append((_lerp3(pa, pb, t), None))  # type: ignore[arg-type]

    # walk vertical grid lines (constant j, varying i)
    for j in range(len(vs)):
        for i in range(len(us) - 1):
            sa, sb = sd[i, j], sd[i + 1, j]
            if (sa >= 0.0) != (sb >= 0.0):
                t = -sa / (sb - sa) if abs(sb - sa) > 1e-15 else 0.5
                pa = grid[i, j].tolist()
                pb = grid[i + 1, j].tolist()
                segments.append((_lerp3(pa, pb, t), None))  # type: ignore[arg-type]

    # walk diagonal grid cells (marching squares on quad grid)
    segs2: List[Tuple[Point3, Point3]] = []
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            corners = [
                (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            ]
            s_vals = [sd[ci, cj] for ci, cj in corners]
            pts = [grid[ci, cj].tolist() for ci, cj in corners]
            cross_pts: List[Point3] = []
            edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
            for ea, eb in edges:
                sa, sb = s_vals[ea], s_vals[eb]
                if (sa >= 0.0) != (sb >= 0.0):
                    denom = sb - sa
                    t = -sa / denom if abs(denom) > 1e-15 else 0.5
                    t = max(0.0, min(1.0, t))
                    cross_pts.append(_lerp3(pts[ea], pts[eb], t))
            if len(cross_pts) == 2:
                segs2.append((cross_pts[0], cross_pts[1]))
            elif len(cross_pts) == 4:
                segs2.append((cross_pts[0], cross_pts[1]))
                segs2.append((cross_pts[2], cross_pts[3]))

    return _chain_segments(segs2) if segs2 else []


# ---------------------------------------------------------------------------
# section_by_plane
# ---------------------------------------------------------------------------

def section_by_plane(
    mesh_or_surface: Any,
    plane: Any,
    *,
    nu: int = 80,
    nv: int = 80,
) -> dict:
    """Intersect a mesh or NURBS surface with a plane and return ordered polyline loops.

    Parameters
    ----------
    mesh_or_surface :
        Either a dict/tuple ``(verts, faces)`` for a triangle mesh, or a
        ``NurbsSurface`` instance.
    plane :
        Plane specification — see ``_parse_plane`` for accepted formats.
    nu, nv :
        UV grid resolution when mesh_or_surface is a NurbsSurface.

    Returns
    -------
    dict
        ok, loops (list of polylines), loop_count, plane_normal, plane_d.
        On failure: {ok: False, reason: str}.
    """
    try:
        n, d = _parse_plane(plane)
    except Exception as exc:
        return {"ok": False, "reason": f"invalid plane: {exc}"}

    try:
        if isinstance(mesh_or_surface, NurbsSurface):
            loops = _section_surface(mesh_or_surface, n, d, nu=nu, nv=nv)
        else:
            verts, faces = _unpack_mesh(mesh_or_surface)
            loops = _section_mesh(verts, faces, n, d)
    except Exception as exc:
        return {"ok": False, "reason": f"section_by_plane failed: {exc}"}

    return {
        "ok": True,
        "loops": loops,
        "loop_count": len(loops),
        "plane_normal": n.tolist(),
        "plane_d": float(d),
    }


# ---------------------------------------------------------------------------
# contour
# ---------------------------------------------------------------------------

def contour(
    mesh_or_surface: Any,
    axis_dir: Sequence[float],
    spacing: float,
    *,
    origin: Optional[Sequence[float]] = None,
) -> dict:
    """Emit parallel section curves at fixed spacing along an axis.

    Parameters
    ----------
    mesh_or_surface :
        Mesh (verts, faces) or NurbsSurface.
    axis_dir :
        Direction vector for the sectioning axis (need not be unit-length).
    spacing :
        Distance between consecutive planes (> 0).
    origin :
        Point on the first plane.  Defaults to the geometry bounding-box min
        projected onto the axis.

    Returns
    -------
    dict
        ok, sections (list of {level_index, value, loops}), level_count.
    """
    try:
        axis = np.asarray(axis_dir, dtype=float).ravel()[:3]
        nrm = float(np.linalg.norm(axis))
        if nrm < 1e-15:
            return {"ok": False, "reason": "axis_dir is a zero vector"}
        axis = axis / nrm

        if not isinstance(spacing, (int, float)) or spacing <= 0:
            return {"ok": False, "reason": f"spacing must be a positive number; got {spacing!r}"}

        # Determine projection range of the geometry along the axis
        try:
            all_pts = _get_all_points(mesh_or_surface)
        except Exception as exc:
            return {"ok": False, "reason": f"failed to extract geometry points: {exc}"}

        if not all_pts:
            return {"ok": False, "reason": "no geometry points found"}

        projs = [float(np.dot(axis, np.asarray(p, dtype=float)[:3])) for p in all_pts]
        proj_min = min(projs)
        proj_max = max(projs)

        if origin is not None:
            o = np.asarray(origin, dtype=float).ravel()[:3]
            start_d = float(np.dot(axis, o))
        else:
            start_d = proj_min

        # Generate levels
        levels: List[float] = []
        t = start_d
        while t <= proj_max + spacing * 1e-6:
            if t >= proj_min - spacing * 1e-6:
                levels.append(t)
            t += spacing

        sections = []
        for idx, level_d in enumerate(levels):
            plane = (axis.tolist(), float(level_d))
            result = section_by_plane(mesh_or_surface, plane)
            sections.append({
                "level_index": idx,
                "value": level_d,
                "loops": result.get("loops", []),
            })

        return {
            "ok": True,
            "sections": sections,
            "level_count": len(sections),
        }
    except Exception as exc:
        return {"ok": False, "reason": f"contour failed: {exc}"}


# ---------------------------------------------------------------------------
# silhouette
# ---------------------------------------------------------------------------

def _face_normal(verts: List[Vert], face: Face) -> Optional[np.ndarray]:
    if len(face) < 3:
        return None
    i, j, k = int(face[0]), int(face[1]), int(face[2])
    if i >= len(verts) or j >= len(verts) or k >= len(verts):
        return None
    a = np.asarray(verts[i], dtype=float)[:3]
    b = np.asarray(verts[j], dtype=float)[:3]
    c = np.asarray(verts[k], dtype=float)[:3]
    n = np.cross(b - a, c - a)
    nrm = float(np.linalg.norm(n))
    if nrm < 1e-15:
        return None
    return n / nrm


def silhouette(
    mesh: Any,
    view_dir: Sequence[float],
) -> dict:
    """Extract silhouette edges from a triangle mesh.

    A silhouette edge is shared by two faces whose normals straddle the
    sign boundary of dot(normal, view_dir): one face faces toward the viewer,
    the other faces away.  Boundary (naked) edges are also included when the
    single adjacent face is a silhouette.

    Parameters
    ----------
    mesh :
        Triangle mesh as (verts, faces) pair.
    view_dir :
        View direction vector (from viewer toward scene, need not be unit).

    Returns
    -------
    dict
        ok, chains (list of polylines), edge_count.
    """
    try:
        vd = np.asarray(view_dir, dtype=float).ravel()[:3]
        nrm = float(np.linalg.norm(vd))
        if nrm < 1e-15:
            return {"ok": False, "reason": "view_dir is a zero vector"}
        vd = vd / nrm

        verts, faces = _unpack_mesh(mesh)

        if not verts or not faces:
            return {"ok": True, "chains": [], "edge_count": 0}

        # compute dot(face_normal, view_dir) per face
        face_dots: List[Optional[float]] = []
        for face in faces:
            fn = _face_normal(verts, face)
            if fn is None:
                face_dots.append(None)
            else:
                face_dots.append(float(np.dot(fn, vd)))

        # build edge → list of incident face indices
        edge_faces: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for fi, face in enumerate(faces):
            if len(face) < 3:
                continue
            i, j, k = int(face[0]), int(face[1]), int(face[2])
            edge_faces[_edge_key(i, j)].append(fi)
            edge_faces[_edge_key(j, k)].append(fi)
            edge_faces[_edge_key(k, i)].append(fi)

        sil_edges: List[Tuple[int, int]] = []
        for (vi, vj), f_idxs in edge_faces.items():
            if len(f_idxs) == 1:
                # boundary edge — include if its single face is a silhouette
                d = face_dots[f_idxs[0]]
                if d is not None and abs(d) < 0.3:
                    sil_edges.append((vi, vj))
            elif len(f_idxs) >= 2:
                d0 = face_dots[f_idxs[0]]
                d1 = face_dots[f_idxs[1]]
                if d0 is not None and d1 is not None:
                    if (d0 >= 0.0) != (d1 >= 0.0):
                        sil_edges.append((vi, vj))

        segs: List[Tuple[Point3, Point3]] = []
        for vi, vj in sil_edges:
            if vi < len(verts) and vj < len(verts):
                segs.append((
                    [float(x) for x in verts[vi][:3]],
                    [float(x) for x in verts[vj][:3]],
                ))

        chains = _chain_segments(segs)
        return {
            "ok": True,
            "chains": chains,
            "edge_count": len(sil_edges),
        }
    except Exception as exc:
        return {"ok": False, "reason": f"silhouette failed: {exc}"}


# ---------------------------------------------------------------------------
# isoline
# ---------------------------------------------------------------------------

def isoline(
    surface: NurbsSurface,
    direction: str,
    value: float,
    *,
    num_samples: int = 64,
) -> dict:
    """Extract an isoparametric curve from a NurbsSurface.

    Parameters
    ----------
    surface : NurbsSurface
    direction : str
        'u' — fix U at *value*, vary V.
        'v' — fix V at *value*, vary U.
    value : float
        Parameter value (must be within the surface's knot span).
    num_samples : int
        Number of sample points along the iso-direction.

    Returns
    -------
    dict
        ok, points (list of [x,y,z]), parameter_direction, parameter_value.
    """
    try:
        if not isinstance(surface, NurbsSurface):
            return {"ok": False, "reason": f"expected NurbsSurface, got {type(surface).__name__}"}

        direction = str(direction).strip().lower()
        if direction not in ("u", "v"):
            return {"ok": False, "reason": f"direction must be 'u' or 'v'; got {direction!r}"}

        ns = max(2, int(num_samples))

        u_min = float(surface.knots_u[0])
        u_max = float(surface.knots_u[-1])
        v_min = float(surface.knots_v[0])
        v_max = float(surface.knots_v[-1])

        if direction == "u":
            # clamp u to domain
            u_val = float(np.clip(value, u_min, u_max))
            vs = np.linspace(v_min, v_max, ns)
            points = [_eval_surface(surface, u_val, v).tolist()[:3] for v in vs]
            return {
                "ok": True,
                "points": points,
                "parameter_direction": "u",
                "parameter_value": u_val,
            }
        else:
            v_val = float(np.clip(value, v_min, v_max))
            us = np.linspace(u_min, u_max, ns)
            points = [_eval_surface(surface, u, v_val).tolist()[:3] for u in us]
            return {
                "ok": True,
                "points": points,
                "parameter_direction": "v",
                "parameter_value": v_val,
            }
    except Exception as exc:
        return {"ok": False, "reason": f"isoline failed: {exc}"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _unpack_mesh(mesh_or_surface: Any) -> Tuple[List[Vert], List[Face]]:
    """Extract (verts, faces) from various input forms."""
    if isinstance(mesh_or_surface, dict):
        verts = list(mesh_or_surface.get("verts", mesh_or_surface.get("vertices", [])))
        faces = list(mesh_or_surface.get("faces", mesh_or_surface.get("triangles", [])))
        return verts, faces
    if isinstance(mesh_or_surface, (list, tuple)) and len(mesh_or_surface) == 2:
        return list(mesh_or_surface[0]), list(mesh_or_surface[1])
    raise TypeError(
        "mesh must be a (verts, faces) tuple/list or dict with 'verts'/'faces' keys; "
        f"got {type(mesh_or_surface).__name__}"
    )


def _get_all_points(mesh_or_surface: Any) -> List[Point3]:
    """Return a flat list of 3D points for bounding-box computation."""
    if isinstance(mesh_or_surface, NurbsSurface):
        nu, nv = 20, 20
        u_min = float(mesh_or_surface.knots_u[0])
        u_max = float(mesh_or_surface.knots_u[-1])
        v_min = float(mesh_or_surface.knots_v[0])
        v_max = float(mesh_or_surface.knots_v[-1])
        pts = []
        for u in np.linspace(u_min, u_max, nu):
            for v in np.linspace(v_min, v_max, nv):
                pts.append(_eval_surface(mesh_or_surface, u, v).tolist()[:3])
        return pts
    verts, _ = _unpack_mesh(mesh_or_surface)
    return [list(v)[:3] for v in verts]


# ---------------------------------------------------------------------------
# Polyline length helper (used in tests)
# ---------------------------------------------------------------------------

def polyline_length(pts: Polyline) -> float:
    """Compute the total arc length of a polyline."""
    total = 0.0
    for i in range(len(pts) - 1):
        a = np.asarray(pts[i], dtype=float)
        b = np.asarray(pts[i + 1], dtype=float)
        total += float(np.linalg.norm(b - a))
    return total


# ---------------------------------------------------------------------------
# LLM tool registration
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:

    # ------------------------------------------------------------------
    # section_by_plane tool
    # ------------------------------------------------------------------

    _section_spec = ToolSpec(
        name="section_by_plane",
        description=(
            "Intersect a triangle mesh with a plane and return ordered polyline loops "
            "(Marching-Triangles algorithm).  Each loop is a list of [x, y, z] points.\n"
            "\n"
            "Returns:\n"
            "  ok         : bool\n"
            "  loops      : list of polylines (each loop is a list of [x,y,z])\n"
            "  loop_count : int\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "description": "Mesh vertices as [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "description": "Triangle faces as [[i,j,k], ...] (0-based indices).",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "plane_normal": {
                    "type": "array",
                    "description": "Plane normal vector [nx, ny, nz].",
                    "items": {"type": "number"},
                },
                "plane_d": {
                    "type": "number",
                    "description": "Plane offset: points x on the plane satisfy n·x = d.",
                },
            },
            "required": ["verts", "faces", "plane_normal", "plane_d"],
        },
    )

    @register(_section_spec)
    async def run_section_by_plane(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        verts = a.get("verts")
        faces = a.get("faces")
        plane_normal = a.get("plane_normal")
        plane_d = a.get("plane_d")

        if verts is None or faces is None or plane_normal is None or plane_d is None:
            return err_payload("verts, faces, plane_normal, plane_d are required", "BAD_ARGS")

        result = section_by_plane(
            (verts, faces),
            {"normal": plane_normal, "d": plane_d},
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({
            "loops": result["loops"],
            "loop_count": result["loop_count"],
            "plane_normal": result["plane_normal"],
            "plane_d": result["plane_d"],
        })

    # ------------------------------------------------------------------
    # contour tool
    # ------------------------------------------------------------------

    _contour_spec = ToolSpec(
        name="contour_curves",
        description=(
            "Generate a series of parallel section curves at fixed spacing along an axis "
            "(Rhino Contour parity).  Works on triangle meshes.\n"
            "\n"
            "Returns:\n"
            "  ok          : bool\n"
            "  sections    : list of {level_index, value, loops}\n"
            "  level_count : int\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "axis_dir": {
                    "type": "array",
                    "description": "Axis direction vector [dx, dy, dz].",
                    "items": {"type": "number"},
                },
                "spacing": {
                    "type": "number",
                    "description": "Distance between consecutive planes (> 0).",
                },
                "origin": {
                    "type": "array",
                    "description": "Optional point on the first plane [x, y, z].",
                    "items": {"type": "number"},
                },
            },
            "required": ["verts", "faces", "axis_dir", "spacing"],
        },
    )

    @register(_contour_spec)
    async def run_contour_curves(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        verts = a.get("verts")
        faces = a.get("faces")
        axis_dir = a.get("axis_dir")
        spacing = a.get("spacing")
        origin = a.get("origin")

        if verts is None or faces is None or axis_dir is None or spacing is None:
            return err_payload("verts, faces, axis_dir, spacing are required", "BAD_ARGS")

        result = contour(
            (verts, faces),
            axis_dir,
            spacing,
            origin=origin,
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({
            "sections": result["sections"],
            "level_count": result["level_count"],
        })

    # ------------------------------------------------------------------
    # silhouette tool
    # ------------------------------------------------------------------

    _silhouette_spec = ToolSpec(
        name="silhouette_curves",
        description=(
            "Extract silhouette edges from a triangle mesh for a given view direction "
            "(Rhino Silhouette parity).  Returns polyline chains.\n"
            "\n"
            "Returns:\n"
            "  ok         : bool\n"
            "  chains     : list of polylines\n"
            "  edge_count : int\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "view_dir": {
                    "type": "array",
                    "description": "View direction vector [dx, dy, dz] (from viewer toward scene).",
                    "items": {"type": "number"},
                },
            },
            "required": ["verts", "faces", "view_dir"],
        },
    )

    @register(_silhouette_spec)
    async def run_silhouette_curves(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        verts = a.get("verts")
        faces = a.get("faces")
        view_dir = a.get("view_dir")

        if verts is None or faces is None or view_dir is None:
            return err_payload("verts, faces, view_dir are required", "BAD_ARGS")

        result = silhouette((verts, faces), view_dir)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({
            "chains": result["chains"],
            "edge_count": result["edge_count"],
        })
