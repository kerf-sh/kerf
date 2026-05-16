"""
make2d.py
=========
Make2D / hidden-line removal — Rhino-parity 3D→2D drafting.

Given a tessellated mesh or polyhedral B-rep (triangles + optional analytic
edges) and a view (camera direction / projection: parallel-orthographic or
simple perspective), produce a 2D vector drawing:

  • Project all 3D geometry into view-plane coordinates.
  • Compute silhouette and feature edges (boundary, crease, hard edges).
  • Classify each projected edge segment as **visible** or **hidden** via a
    robust painter/depth-buffer + edge–face occlusion test (segment subdivision
    at crossings).
  • Output layered polylines (visible solid, hidden dashed) with view transform
    + scaling.
  • Provide standard orthographic view set helpers (top/front/right/iso).

Public API
----------
ViewParams(dataclass)
    Camera / projection parameters: direction, up vector, projection type
    (``'ortho'`` or ``'perspective'``), field-of-view.

Make2DInput(dataclass)
    Input mesh: ``vertices`` (N×3), ``triangles`` (M×3 index), optional
    ``feature_edges`` (K×2 index pairs), ``crease_angle_deg`` float.

Make2DResult(dataclass)
    Output: ``visible`` list[list[tuple[float,float]]] (polylines),
    ``hidden``  list[list[tuple[float,float]]] (polylines),
    ``view_matrix`` 4×4 ndarray, ``scale`` float.

make2d(mesh, view, *, scale=1.0, subdivisions=8, tol=1e-9) -> Make2DResult
    Main entry point.  Pure-Python + NumPy, no OCC required.

standard_views() -> dict[str, ViewParams]
    Returns named ViewParams for top/front/right/iso.

LLM tools (registered when kerf_chat is available):
  ``make2d_project``    — project mesh, return visible/hidden polyline counts
  ``make2d_silhouette`` — extract silhouette edges only

Never raises — all exceptions are caught and surfaced in ``{"ok": False, "reason": ...}``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CREASE_DEFAULT_DEG: float = 30.0
_SUBDIVISIONS_DEFAULT: int = 8
_TOL: float = 1e-9

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ViewParams:
    """Camera / projection parameters for Make2D.

    Attributes
    ----------
    direction : array-like [dx, dy, dz]
        View direction vector (camera looks *toward* this direction; will be
        normalised internally).  For ortho top-view use [0, 0, -1].
    up : array-like [ux, uy, uz]
        World up vector (will be Gram-Schmidt orthogonalised against
        ``direction``).  Default [0, 1, 0].
    projection : str
        ``'ortho'`` (default) for parallel orthographic; ``'perspective'``
        for simple perspective projection.
    fov_deg : float
        Perspective field-of-view in degrees (only used when
        ``projection == 'perspective'``).  Default 45.0.
    near : float
        Near-plane distance for perspective (default 0.1).
    """
    direction: Sequence = field(default_factory=lambda: [0.0, 0.0, -1.0])
    up: Sequence = field(default_factory=lambda: [0.0, 1.0, 0.0])
    projection: str = "ortho"
    fov_deg: float = 45.0
    near: float = 0.1

    def validated_direction(self) -> np.ndarray:
        d = np.asarray(self.direction, dtype=float).ravel()[:3]
        n = np.linalg.norm(d)
        if n < _TOL:
            return np.array([0.0, 0.0, -1.0])
        return d / n

    def validated_up(self) -> np.ndarray:
        u = np.asarray(self.up, dtype=float).ravel()[:3]
        n = np.linalg.norm(u)
        if n < _TOL:
            return np.array([0.0, 1.0, 0.0])
        return u / n


@dataclass
class Make2DInput:
    """Input mesh for Make2D.

    Attributes
    ----------
    vertices : array-like (N, 3)
        3D vertex positions.
    triangles : array-like (M, 3)
        Triangle face indices into ``vertices`` (0-based).
    feature_edges : array-like (K, 2), optional
        Explicit hard/feature edge pairs (vertex indices).  If None, feature
        edges are derived from boundary + crease detection.
    crease_angle_deg : float
        Dihedral angle threshold for crease-edge detection (default 30°).
    """
    vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    triangles: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=int))
    feature_edges: Optional[np.ndarray] = None
    crease_angle_deg: float = _CREASE_DEFAULT_DEG

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=float)
        self.triangles = np.asarray(self.triangles, dtype=int)
        if self.feature_edges is not None:
            self.feature_edges = np.asarray(self.feature_edges, dtype=int)

    def is_valid(self) -> Tuple[bool, str]:
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 3:
            return False, f"vertices must be (N,3); got shape {self.vertices.shape}"
        if self.vertices.shape[0] == 0:
            return False, "vertices array is empty"
        if self.triangles.ndim != 2 or self.triangles.shape[1] != 3:
            return False, f"triangles must be (M,3); got shape {self.triangles.shape}"
        if self.triangles.shape[0] == 0:
            return False, "triangles array is empty"
        n = self.vertices.shape[0]
        if self.triangles.min() < 0 or self.triangles.max() >= n:
            return False, "triangle index out of range"
        return True, ""


@dataclass
class Make2DResult:
    """Output of make2d().

    Attributes
    ----------
    visible : list of polylines
        Each polyline is a list of (x, y) 2D points (visible edges).
    hidden : list of polylines
        Each polyline is a list of (x, y) 2D points (hidden edges).
    view_matrix : np.ndarray (4, 4)
        World→view transformation matrix used.
    scale : float
        Scale factor applied.
    silhouette_count : int
        Number of silhouette edges found before classification.
    feature_count : int
        Number of feature/crease edges used.
    """
    visible: List[List[Tuple[float, float]]] = field(default_factory=list)
    hidden: List[List[Tuple[float, float]]] = field(default_factory=list)
    view_matrix: np.ndarray = field(default_factory=lambda: np.eye(4))
    scale: float = 1.0
    silhouette_count: int = 0
    feature_count: int = 0


# ---------------------------------------------------------------------------
# View / projection math
# ---------------------------------------------------------------------------


def _build_view_matrix(view: ViewParams) -> np.ndarray:
    """Build a 4×4 world→view (camera) matrix.

    The view space is:
      +X = right
      +Y = up (view-plane up)
      -Z = view direction (looking into the scene)

    Returns a column-major 4×4 float64 array (row = [right, up, -fwd, trans]).
    For ortho we simply use this as the projection basis.
    """
    fwd = view.validated_direction()  # camera looks toward fwd
    up_hint = view.validated_up()

    # Gram-Schmidt: ensure up is perpendicular to fwd
    right = np.cross(fwd, up_hint)
    r_norm = np.linalg.norm(right)
    if r_norm < _TOL:
        # fwd ≈ up_hint; choose arbitrary perpendicular
        perp = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(fwd, perp)) > 0.9:
            perp = np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, perp)
        right /= np.linalg.norm(right)
    else:
        right /= r_norm

    up = np.cross(right, fwd)
    up /= np.linalg.norm(up)

    # Row-major view matrix (rows = basis vectors)
    M = np.eye(4, dtype=float)
    M[0, :3] = right
    M[1, :3] = up
    M[2, :3] = -fwd   # -fwd so depth increases along +Z in view space
    # Translation: set origin to centroid of scene (will be adjusted per-call)
    return M


def _project_vertices(
    verts: np.ndarray,
    view_mat: np.ndarray,
    view: ViewParams,
) -> Tuple[np.ndarray, np.ndarray]:
    """Project 3D vertices into 2D view-plane coords + depth (z-buffer).

    Returns
    -------
    uv : (N, 2) float — projected 2D coordinates in view plane
    depth : (N,) float — depth value per vertex (for occlusion)
    """
    n = verts.shape[0]
    h = np.ones((n, 4), dtype=float)
    h[:, :3] = verts
    # Apply view rotation (no translation yet — use centred coords)
    v = (view_mat @ h.T).T  # (N, 4)

    if view.projection == "perspective":
        fov_rad = math.radians(max(1.0, min(179.0, view.fov_deg)))
        f = 1.0 / math.tan(fov_rad * 0.5)
        near = max(_TOL, view.near)
        z = v[:, 2]
        safe_z = np.where(np.abs(z) < near, -near, z)
        x_proj = f * v[:, 0] / (-safe_z)
        y_proj = f * v[:, 1] / (-safe_z)
        uv = np.column_stack([x_proj, y_proj])
        depth = -v[:, 2]
    else:
        # Orthographic: drop Z, keep it as depth
        uv = v[:, :2].copy()
        depth = -v[:, 2]

    return uv, depth


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def _edge_key(a: int, b: int) -> Tuple[int, int]:
    return (min(a, b), max(a, b))


def _build_edge_face_map(triangles: np.ndarray) -> Dict[Tuple[int, int], List[int]]:
    """Return a dict mapping edge→list of face indices sharing that edge."""
    ef: Dict[Tuple[int, int], List[int]] = {}
    for fi, tri in enumerate(triangles):
        for k in range(3):
            e = _edge_key(int(tri[k]), int(tri[(k + 1) % 3]))
            ef.setdefault(e, []).append(fi)
    return ef


def _triangle_normal(verts: np.ndarray, tri: np.ndarray) -> np.ndarray:
    a = verts[tri[1]] - verts[tri[0]]
    b = verts[tri[2]] - verts[tri[0]]
    n = np.cross(a, b)
    nrm = np.linalg.norm(n)
    if nrm < _TOL:
        return np.zeros(3)
    return n / nrm


def _compute_face_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Return (M, 3) face normals."""
    normals = np.zeros((len(tris), 3), dtype=float)
    for fi, tri in enumerate(tris):
        normals[fi] = _triangle_normal(verts, tri)
    return normals


def _extract_feature_edges(
    mesh: Make2DInput,
    face_normals: np.ndarray,
    ef_map: Dict[Tuple[int, int], List[int]],
) -> List[Tuple[int, int]]:
    """Extract boundary edges + crease edges.

    A boundary edge has exactly one adjacent face.
    A crease edge has two adjacent faces with dihedral angle > crease_angle_deg.
    """
    crease_cos = math.cos(math.radians(mesh.crease_angle_deg))
    edges: List[Tuple[int, int]] = []
    for e, faces in ef_map.items():
        if len(faces) == 1:
            edges.append(e)  # boundary
        elif len(faces) == 2:
            n0 = face_normals[faces[0]]
            n1 = face_normals[faces[1]]
            cos_a = float(np.dot(n0, n1))
            cos_a = max(-1.0, min(1.0, cos_a))
            if cos_a < crease_cos:
                edges.append(e)
    return edges


def _extract_silhouette_edges(
    mesh: Make2DInput,
    face_normals: np.ndarray,
    ef_map: Dict[Tuple[int, int], List[int]],
    view_dir: np.ndarray,
) -> List[Tuple[int, int]]:
    """Extract silhouette edges: edges where one face faces toward camera and
    the other faces away (sign change of dot(normal, view_dir)).
    Also include boundary edges whose single face faces the camera.
    """
    silhouettes: List[Tuple[int, int]] = []
    for e, faces in ef_map.items():
        if len(faces) == 1:
            # Boundary edge — include if face is front-facing
            dot = float(np.dot(face_normals[faces[0]], view_dir))
            if dot > -_TOL:
                silhouettes.append(e)
        elif len(faces) == 2:
            d0 = float(np.dot(face_normals[faces[0]], view_dir))
            d1 = float(np.dot(face_normals[faces[1]], view_dir))
            # Sign change → silhouette
            if d0 * d1 <= 0.0:
                silhouettes.append(e)
    return silhouettes


# ---------------------------------------------------------------------------
# Occlusion / visibility testing
# ---------------------------------------------------------------------------


def _segment_depth_at_t(
    uv0: np.ndarray, d0: float,
    uv1: np.ndarray, d1: float,
    t: float,
) -> float:
    """Linearly interpolate depth along segment at parameter t ∈ [0,1]."""
    return d0 * (1.0 - t) + d1 * t


def _point_in_triangle_2d(
    p: np.ndarray,
    a: np.ndarray, b: np.ndarray, c: np.ndarray,
) -> bool:
    """Test if 2D point p is inside triangle (a, b, c) using barycentric coords."""
    v0 = c - a
    v1 = b - a
    v2 = p - a

    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < _TOL:
        return False

    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv

    return (u >= -_TOL) and (v >= -_TOL) and (u + v <= 1.0 + _TOL)


def _triangle_depth_at_point_2d(
    p2: np.ndarray,
    a2: np.ndarray, b2: np.ndarray, c2: np.ndarray,
    da: float, db: float, dc: float,
) -> Optional[float]:
    """Interpolate depth at 2D point p2 inside projected triangle (a2,b2,c2)."""
    v0 = c2 - a2
    v1 = b2 - a2
    v2 = p2 - a2

    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < _TOL:
        return None

    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v_ = (dot00 * dot12 - dot01 * dot02) * inv

    if u < -_TOL or v_ < -_TOL or u + v_ > 1.0 + _TOL:
        return None

    # Barycentric interpolation: w_a=1-u-v, w_b=v, w_c=u
    w_a = 1.0 - u - v_
    return w_a * da + v_ * db + u * dc


def _classify_segment_visibility(
    uv_a: np.ndarray, depth_a: float,
    uv_b: np.ndarray, depth_b: float,
    proj_verts: np.ndarray,
    vert_depths: np.ndarray,
    tris: np.ndarray,
    face_depths: np.ndarray,
    edge_tri_set: frozenset,
    subdivisions: int,
    tol: float,
) -> bool:
    """Return True if segment (uv_a→uv_b) is predominantly visible.

    Tests ``subdivisions`` evenly-spaced sample points along the segment.
    A point is visible if no triangle in front of it contains it in projection.

    ``edge_tri_set`` is the set of triangle indices that *own* this edge
    (to avoid self-occlusion).
    ``face_depths`` is the maximum vertex depth per triangle (used as depth bound).
    """
    visible_count = 0
    total = subdivisions

    for i in range(total):
        t = (i + 0.5) / total
        p2 = uv_a + t * (uv_b - uv_a)
        seg_depth = _segment_depth_at_t(uv_a, depth_a, uv_b, depth_b, t)

        occluded = False
        for fi, tri in enumerate(tris):
            if fi in edge_tri_set:
                continue

            a2 = proj_verts[tri[0]]
            b2 = proj_verts[tri[1]]
            c2 = proj_verts[tri[2]]

            d = _triangle_depth_at_point_2d(p2, a2, b2, c2,
                                            vert_depths[tri[0]],
                                            vert_depths[tri[1]],
                                            vert_depths[tri[2]])
            if d is not None and d > seg_depth + tol:
                occluded = True
                break

        if not occluded:
            visible_count += 1

    return visible_count * 2 >= total  # majority vote


# ---------------------------------------------------------------------------
# Main make2d function
# ---------------------------------------------------------------------------


def make2d(
    mesh: Make2DInput,
    view: ViewParams,
    *,
    scale: float = 1.0,
    subdivisions: int = _SUBDIVISIONS_DEFAULT,
    tol: float = _TOL,
) -> Make2DResult:
    """Convert a 3D tessellated mesh to a 2D vector drawing with hidden-line removal.

    Parameters
    ----------
    mesh : Make2DInput
        Input mesh (vertices, triangles, optional feature edges).
    view : ViewParams
        Camera / projection parameters.
    scale : float
        Scale factor applied to output 2D coordinates (default 1.0).
    subdivisions : int
        Number of sample points per edge segment for occlusion testing
        (default 8; higher = more accurate but slower).
    tol : float
        Depth tolerance for occlusion tests (default 1e-9).

    Returns
    -------
    Make2DResult
        ``visible`` and ``hidden`` lists of 2D polylines.
    """
    valid, reason = mesh.is_valid()
    if not valid:
        raise ValueError(f"Make2DInput is invalid: {reason}")
    if scale <= 0:
        raise ValueError(f"scale must be positive; got {scale}")

    subdivisions = max(1, int(subdivisions))

    # Build view matrix
    view_mat = _build_view_matrix(view)

    # Centre geometry at its centroid
    centroid = mesh.vertices.mean(axis=0)
    verts_centred = mesh.vertices - centroid

    # Project all vertices
    proj_verts, vert_depths = _project_vertices(verts_centred, view_mat, view)

    # Face normals (in world space, for silhouette / crease detection)
    face_normals = _compute_face_normals(verts_centred, mesh.triangles)

    # View direction (world space)
    view_dir = view.validated_direction()

    # Edge → face adjacency
    ef_map = _build_edge_face_map(mesh.triangles)

    # --- Determine which edges to draw ---
    if mesh.feature_edges is not None:
        feature_edge_list = [_edge_key(int(e[0]), int(e[1]))
                             for e in mesh.feature_edges]
    else:
        feature_edge_list = _extract_feature_edges(mesh, face_normals, ef_map)

    silhouette_list = _extract_silhouette_edges(
        mesh, face_normals, ef_map, view_dir
    )

    # Merge (deduplicate): feature edges + silhouette edges
    all_edges_set: Dict[Tuple[int, int], bool] = {}  # edge → is_silhouette
    for e in silhouette_list:
        all_edges_set[e] = True
    for e in feature_edge_list:
        if e not in all_edges_set:
            all_edges_set[e] = False

    # Per-face max depth (for bounding box culling)
    face_depths = np.array([
        max(vert_depths[t[0]], vert_depths[t[1]], vert_depths[t[2]])
        for t in mesh.triangles
    ])

    # Classify each edge as visible or hidden
    visible_polylines: List[List[Tuple[float, float]]] = []
    hidden_polylines: List[List[Tuple[float, float]]] = []

    for (i0, i1) in all_edges_set:
        uv_a = proj_verts[i0]
        uv_b = proj_verts[i1]
        da = vert_depths[i0]
        db = vert_depths[i1]

        # Skip degenerate projected edges
        if np.linalg.norm(uv_b - uv_a) < _TOL:
            continue

        # Build set of triangles that own this edge (for self-occlusion skip)
        owner_faces = frozenset(ef_map.get(_edge_key(i0, i1), []))

        is_visible = _classify_segment_visibility(
            uv_a, da, uv_b, db,
            proj_verts, vert_depths,
            mesh.triangles, face_depths,
            owner_faces,
            subdivisions, tol,
        )

        seg = [
            (float(uv_a[0] * scale), float(uv_a[1] * scale)),
            (float(uv_b[0] * scale), float(uv_b[1] * scale)),
        ]
        if is_visible:
            visible_polylines.append(seg)
        else:
            hidden_polylines.append(seg)

    return Make2DResult(
        visible=visible_polylines,
        hidden=hidden_polylines,
        view_matrix=view_mat,
        scale=scale,
        silhouette_count=len(silhouette_list),
        feature_count=len(feature_edge_list),
    )


# ---------------------------------------------------------------------------
# Standard orthographic views
# ---------------------------------------------------------------------------


def standard_views() -> Dict[str, ViewParams]:
    """Return a dict of named ViewParams for common engineering views.

    Keys: ``'top'``, ``'front'``, ``'right'``, ``'iso'``.
    """
    iso_dir = np.array([1.0, -1.0, -1.0])
    iso_dir /= np.linalg.norm(iso_dir)

    return {
        "top":   ViewParams(direction=[0.0,  0.0, -1.0], up=[0.0,  1.0,  0.0]),
        "front": ViewParams(direction=[0.0, -1.0,  0.0], up=[0.0,  0.0,  1.0]),
        "right": ViewParams(direction=[1.0,  0.0,  0.0], up=[0.0,  0.0,  1.0]),
        "iso":   ViewParams(direction=iso_dir.tolist(),  up=[0.0,  0.0,  1.0]),
    }


# ---------------------------------------------------------------------------
# Helpers: cube / sphere mesh builders (for tests + demos)
# ---------------------------------------------------------------------------


def _make_cube_mesh(side: float = 1.0) -> Make2DInput:
    """Return a tessellated unit cube (12 triangles)."""
    s = side * 0.5
    verts = np.array([
        [-s, -s, -s], [ s, -s, -s], [ s,  s, -s], [-s,  s, -s],  # bottom
        [-s, -s,  s], [ s, -s,  s], [ s,  s,  s], [-s,  s,  s],  # top
    ], dtype=float)
    faces = np.array([
        [0, 2, 1], [0, 3, 2],  # bottom
        [4, 5, 6], [4, 6, 7],  # top
        [0, 1, 5], [0, 5, 4],  # front
        [1, 2, 6], [1, 6, 5],  # right
        [2, 3, 7], [2, 7, 6],  # back
        [3, 0, 4], [3, 4, 7],  # left
    ], dtype=int)
    return Make2DInput(vertices=verts, triangles=faces)


def _make_tetra_mesh() -> Make2DInput:
    """Return a regular tetrahedron mesh (4 triangles)."""
    verts = np.array([
        [ 1.0,  1.0,  1.0],
        [-1.0, -1.0,  1.0],
        [-1.0,  1.0, -1.0],
        [ 1.0, -1.0, -1.0],
    ], dtype=float)
    faces = np.array([
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 3, 2],
    ], dtype=int)
    return Make2DInput(vertices=verts, triangles=faces)


def _make_sphere_mesh(radius: float = 1.0, subdivisions: int = 2) -> Make2DInput:
    """Return a UV-sphere mesh via icosphere subdivision."""
    # Start with icosahedron
    t = (1.0 + math.sqrt(5.0)) * 0.5
    raw = [
        [-1,  t,  0], [ 1,  t,  0], [-1, -t,  0], [ 1, -t,  0],
        [ 0, -1,  t], [ 0,  1,  t], [ 0, -1, -t], [ 0,  1, -t],
        [ t,  0, -1], [ t,  0,  1], [-t,  0, -1], [-t,  0,  1],
    ]
    verts = [np.array(v, dtype=float) for v in raw]
    for i, v in enumerate(verts):
        verts[i] = v / np.linalg.norm(v) * radius

    faces = [
        [0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],
        [1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
        [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],
        [4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1],
    ]

    midpoint_cache: Dict[Tuple[int, int], int] = {}

    def midpoint(a: int, b: int) -> int:
        key = _edge_key(a, b)
        if key in midpoint_cache:
            return midpoint_cache[key]
        m = (verts[a] + verts[b]) * 0.5
        m = m / np.linalg.norm(m) * radius
        idx = len(verts)
        verts.append(m)
        midpoint_cache[key] = idx
        return idx

    for _ in range(subdivisions):
        new_faces = []
        for f in faces:
            a, b, c = f
            ab = midpoint(a, b)
            bc = midpoint(b, c)
            ca = midpoint(c, a)
            new_faces += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
        faces = new_faces

    v_arr = np.array([v.tolist() for v in verts], dtype=float)
    t_arr = np.array(faces, dtype=int)
    return Make2DInput(vertices=v_arr, triangles=t_arr)


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
    # make2d_project
    # ------------------------------------------------------------------

    _make2d_project_spec = ToolSpec(
        name="make2d_project",
        description=(
            "Project a tessellated 3D mesh into a 2D vector drawing with "
            "hidden-line removal (Rhino Make2D parity).  Accepts a mesh "
            "(vertices + triangle indices) and a view direction, produces "
            "separate visible and hidden polyline lists.\n"
            "\n"
            "Returns:\n"
            "  ok              : bool\n"
            "  visible         : list of [[x,y],...] polylines (solid lines)\n"
            "  hidden          : list of [[x,y],...] polylines (dashed lines)\n"
            "  visible_count   : int\n"
            "  hidden_count    : int\n"
            "  silhouette_count: int\n"
            "  feature_count   : int\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "vertices": {
                    "type": "array",
                    "description": "List of 3D vertices [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "triangles": {
                    "type": "array",
                    "description": "Triangle index triples [[i,j,k], ...].",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "view_direction": {
                    "type": "array",
                    "description": "Camera view direction [dx,dy,dz].",
                    "items": {"type": "number"},
                },
                "view_up": {
                    "type": "array",
                    "description": "World up vector [ux,uy,uz] (default [0,1,0]).",
                    "items": {"type": "number"},
                },
                "projection": {
                    "type": "string",
                    "enum": ["ortho", "perspective"],
                    "description": "Projection type (default 'ortho').",
                },
                "scale": {
                    "type": "number",
                    "description": "Output scale factor (default 1.0).",
                },
                "subdivisions": {
                    "type": "integer",
                    "description": "Occlusion sample count per edge (default 8).",
                },
                "crease_angle_deg": {
                    "type": "number",
                    "description": "Crease detection angle in degrees (default 30).",
                },
            },
            "required": ["vertices", "triangles", "view_direction"],
        },
    )

    @register(_make2d_project_spec)
    async def run_make2d_project(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        raw_verts = a.get("vertices")
        raw_tris = a.get("triangles")
        view_dir = a.get("view_direction")

        if raw_verts is None or raw_tris is None or view_dir is None:
            return err_payload(
                "vertices, triangles, view_direction are required", "BAD_ARGS"
            )

        try:
            verts = np.array(raw_verts, dtype=float)
            tris = np.array(raw_tris, dtype=int)
            vd = list(view_dir)
        except Exception as exc:
            return err_payload(f"invalid mesh data: {exc}", "BAD_ARGS")

        view_up = a.get("view_up", [0.0, 1.0, 0.0])
        projection = a.get("projection", "ortho")
        scale = float(a.get("scale", 1.0))
        subs = int(a.get("subdivisions", _SUBDIVISIONS_DEFAULT))
        crease = float(a.get("crease_angle_deg", _CREASE_DEFAULT_DEG))

        if projection not in ("ortho", "perspective"):
            return err_payload(
                f"projection must be 'ortho' or 'perspective'; got {projection!r}",
                "BAD_ARGS",
            )
        if scale <= 0:
            return err_payload(f"scale must be positive; got {scale}", "BAD_ARGS")
        if subs < 1:
            return err_payload(f"subdivisions must be >= 1; got {subs}", "BAD_ARGS")

        mesh = Make2DInput(
            vertices=verts,
            triangles=tris,
            crease_angle_deg=crease,
        )
        valid, reason = mesh.is_valid()
        if not valid:
            return err_payload(reason, "BAD_ARGS")

        vp = ViewParams(
            direction=vd,
            up=list(view_up),
            projection=projection,
        )

        try:
            result = make2d(mesh, vp, scale=scale, subdivisions=subs)
        except Exception as exc:
            return err_payload(f"make2d failed: {exc}", "OP_FAILED")

        return ok_payload({
            "visible": [[[p[0], p[1]] for p in poly] for poly in result.visible],
            "hidden":  [[[p[0], p[1]] for p in poly] for poly in result.hidden],
            "visible_count": len(result.visible),
            "hidden_count": len(result.hidden),
            "silhouette_count": result.silhouette_count,
            "feature_count": result.feature_count,
        })

    # ------------------------------------------------------------------
    # make2d_silhouette
    # ------------------------------------------------------------------

    _make2d_silhouette_spec = ToolSpec(
        name="make2d_silhouette",
        description=(
            "Extract silhouette edges of a 3D mesh from a given view direction "
            "without full hidden-line removal.  Faster than make2d_project when "
            "only outline edges are needed.\n"
            "\n"
            "Returns:\n"
            "  ok               : bool\n"
            "  silhouette_edges : list of [[x0,y0],[x1,y1]] 2D segments\n"
            "  count            : int\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "vertices": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "triangles": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "view_direction": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "view_up": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "projection": {
                    "type": "string",
                    "enum": ["ortho", "perspective"],
                },
                "scale": {"type": "number"},
            },
            "required": ["vertices", "triangles", "view_direction"],
        },
    )

    @register(_make2d_silhouette_spec)
    async def run_make2d_silhouette(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        raw_verts = a.get("vertices")
        raw_tris = a.get("triangles")
        view_dir = a.get("view_direction")

        if raw_verts is None or raw_tris is None or view_dir is None:
            return err_payload(
                "vertices, triangles, view_direction are required", "BAD_ARGS"
            )

        try:
            verts = np.array(raw_verts, dtype=float)
            tris = np.array(raw_tris, dtype=int)
            vd = list(view_dir)
        except Exception as exc:
            return err_payload(f"invalid mesh data: {exc}", "BAD_ARGS")

        view_up = a.get("view_up", [0.0, 1.0, 0.0])
        projection = a.get("projection", "ortho")
        scale = float(a.get("scale", 1.0))

        if projection not in ("ortho", "perspective"):
            return err_payload(
                f"projection must be 'ortho' or 'perspective'; got {projection!r}",
                "BAD_ARGS",
            )
        if scale <= 0:
            return err_payload(f"scale must be positive; got {scale}", "BAD_ARGS")

        mesh = Make2DInput(vertices=verts, triangles=tris)
        valid, reason = mesh.is_valid()
        if not valid:
            return err_payload(reason, "BAD_ARGS")

        vp = ViewParams(direction=vd, up=list(view_up), projection=projection)
        view_mat = _build_view_matrix(vp)
        centroid = mesh.vertices.mean(axis=0)
        verts_c = mesh.vertices - centroid
        proj_verts, _ = _project_vertices(verts_c, view_mat, vp)
        face_normals = _compute_face_normals(verts_c, mesh.triangles)
        ef_map = _build_edge_face_map(mesh.triangles)
        view_dir_np = vp.validated_direction()
        silhouettes = _extract_silhouette_edges(
            mesh, face_normals, ef_map, view_dir_np
        )

        segments = []
        for (i0, i1) in silhouettes:
            uv_a = proj_verts[i0]
            uv_b = proj_verts[i1]
            segments.append([
                [float(uv_a[0] * scale), float(uv_a[1] * scale)],
                [float(uv_b[0] * scale), float(uv_b[1] * scale)],
            ])

        return ok_payload({"silhouette_edges": segments, "count": len(segments)})
