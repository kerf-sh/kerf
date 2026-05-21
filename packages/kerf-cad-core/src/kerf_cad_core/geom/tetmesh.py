"""GK-136 — Delaunay volume mesh (tetrahedralization) of a closed Body for FEM.

Public API
----------
tetrahedralize(body, max_volume=None) -> dict
    Produce a tetrahedral volume mesh for *body*.

    Parameters
    ----------
    body : Body
        A closed (watertight) B-rep body.
    max_volume : float or None
        If given, tetrahedra with signed volume > max_volume are split by
        inserting their centroid and re-running the Delaunay step.  This
        provides a simple size-control mechanism without requiring an
        external mesh generator.

    Returns
    -------
    dict with keys:

    ``nodes``
        ``numpy.ndarray`` of shape ``(N, 3)``, dtype float64 — unique mesh
        vertices in world coordinates.
    ``tets``
        ``numpy.ndarray`` of shape ``(T, 4)``, dtype int64 — each row is
        four 0-based indices into ``nodes`` forming one tetrahedron.
        All tetrahedra are positively oriented: the signed volume
        ``(1/6) * det([b-a, c-a, d-a])`` is **strictly positive**.

Algorithm
---------
1. Sample the body surface + interior to obtain a point cloud.
2. Run ``scipy.spatial.Delaunay`` on the cloud.
3. Discard any tetrahedron whose centroid lies outside the body
   (tested via ray-casting against the body's faces).
4. Flip any negatively-oriented tetrahedron by swapping two vertex indices
   so that all surviving tetrahedra have positive signed volume.
5. Optional: if *max_volume* is given, split oversized tetrahedra and
   re-run Delaunay once.

Pure-Python / NumPy / SciPy only.  No OCCT, no C extensions beyond those
already pulled in by numpy/scipy.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.spatial import Delaunay

from kerf_cad_core.geom.brep import Body, Face


# ---------------------------------------------------------------------------
# Internal helpers: surface sampling
# ---------------------------------------------------------------------------

def _face_param_bounds(face: Face):
    """Return (u_lo, u_hi, v_lo, v_hi) for *face*'s surface."""
    surface = face.surface
    cls = type(surface).__name__

    if cls == "SphereSurface":
        return (0.0, 2 * math.pi, -math.pi / 2, math.pi / 2)
    if cls == "TorusSurface":
        return (0.0, 2 * math.pi, 0.0, 2 * math.pi)
    if cls == "CylinderSurface":
        axis = getattr(surface, "axis", np.array([0.0, 0.0, 1.0]))
        c = getattr(surface, "center", np.zeros(3))
        # Try to find height extent from loop vertices
        outer = face.outer_loop()
        if outer is not None:
            pts = []
            for ce in outer.coedges:
                try:
                    pts.append(np.asarray(ce.start_point(), dtype=float))
                except Exception:  # noqa: BLE001
                    pass
            if pts:
                arr = np.array(pts)
                vs = [(arr[i] - c) @ np.asarray(axis, dtype=float) for i in range(len(arr))]
                v_lo, v_hi = float(min(vs)), float(max(vs))
                if abs(v_hi - v_lo) < 1e-10:
                    v_lo, v_hi = v_lo - 1.0, v_hi + 1.0
                return (0.0, 2 * math.pi, v_lo, v_hi)
        return (0.0, 2 * math.pi, -1.0, 1.0)
    if cls == "Plane":
        outer = face.outer_loop()
        if outer is not None:
            pts = []
            for ce in outer.coedges:
                try:
                    pts.append(np.asarray(ce.start_point(), dtype=float))
                except Exception:  # noqa: BLE001
                    pass
            if pts:
                arr = np.array(pts)
                o = np.asarray(surface.origin, dtype=float)
                ex = np.asarray(surface.x_axis, dtype=float)
                ey = np.asarray(surface.y_axis, dtype=float)
                us = [(arr[i] - o) @ ex for i in range(len(arr))]
                vs_list = [(arr[i] - o) @ ey for i in range(len(arr))]
                m = 0.01
                return (min(us) - m, max(us) + m, min(vs_list) - m, max(vs_list) + m)
        return (-1.0, 1.0, -1.0, 1.0)
    if hasattr(surface, "u_knots") and hasattr(surface, "v_knots"):
        uk = surface.u_knots
        vk = surface.v_knots
        return (float(uk[0]), float(uk[-1]), float(vk[0]), float(vk[-1]))
    return (0.0, 1.0, 0.0, 1.0)


def _sample_face_points(face: Face, n_uv: int = 10) -> np.ndarray:
    """Sample *n_uv × n_uv* points from the parametric domain of *face*."""
    u_lo, u_hi, v_lo, v_hi = _face_param_bounds(face)
    surface = face.surface
    du = (u_hi - u_lo) / n_uv
    dv = (v_hi - v_lo) / n_uv
    us = np.linspace(u_lo + du / 2, u_hi - du / 2, n_uv)
    vs = np.linspace(v_lo + dv / 2, v_hi - dv / 2, n_uv)
    pts = []
    for u in us:
        for v in vs:
            try:
                p = np.asarray(surface.evaluate(u, v), dtype=float)
                if np.all(np.isfinite(p)):
                    pts.append(p)
            except Exception:  # noqa: BLE001
                pass
    return np.array(pts, dtype=float) if pts else np.empty((0, 3), dtype=float)


def _body_bbox(body: Body) -> tuple:
    """Axis-aligned bounding box of the body."""
    faces = body.all_faces()
    lo = np.full(3, +1e30)
    hi = np.full(3, -1e30)
    for face in faces:
        pts = _sample_face_points(face, n_uv=12)
        if len(pts):
            lo = np.minimum(lo, pts.min(axis=0))
            hi = np.maximum(hi, pts.max(axis=0))
    return lo, hi


# ---------------------------------------------------------------------------
# Point-in-body test: ray casting
# ---------------------------------------------------------------------------

def _ray_face_intersect(
    origin: np.ndarray,
    direction: np.ndarray,
    face: Face,
    n_uv: int = 16,
) -> int:
    """Count (approximate) ray–face intersections using parametric sampling.

    For analytic planar faces we test exact intersection with the infinite
    plane, then check (via nearest-sample) if the hit point is inside the
    face's boundary.  For non-planar or generic faces we fall back to a
    dense parametric sample: the triangle formed by each sample cell is
    tested for intersection.

    Returns an integer parity count (0 or 1 per call).
    """
    surface = face.surface
    cls = type(surface).__name__

    if cls == "Plane":
        # Exact plane intersection
        n = np.asarray(surface._n, dtype=float)
        o_s = np.asarray(surface.origin, dtype=float)
        denom = float(np.dot(direction, n))
        if abs(denom) < 1e-14:
            return 0
        t = float(np.dot(o_s - origin, n)) / denom
        if t <= 1e-10:
            return 0
        hit = origin + t * direction
        # Check hit is within the planar face using parametric bounds
        ex = np.asarray(surface.x_axis, dtype=float)
        ey = np.asarray(surface.y_axis, dtype=float)
        u_lo, u_hi, v_lo, v_hi = _face_param_bounds(face)
        hu = float(np.dot(hit - o_s, ex))
        hv = float(np.dot(hit - o_s, ey))
        if u_lo <= hu <= u_hi and v_lo <= hv <= v_hi:
            return 1
        return 0

    # Generic: use dense grid of quad cells → two triangles per cell
    u_lo, u_hi, v_lo, v_hi = _face_param_bounds(face)
    n_s = n_uv
    us = np.linspace(u_lo, u_hi, n_s + 1)
    vs = np.linspace(v_lo, v_hi, n_s + 1)
    count = 0

    def _eval(u, v):
        try:
            p = np.asarray(surface.evaluate(u, v), dtype=float)
            return p if np.all(np.isfinite(p)) else None
        except Exception:  # noqa: BLE001
            return None

    def _tri_intersect(a, b, c):
        """Möller–Trumbore ray–triangle intersection; t > 0."""
        edge1 = b - a
        edge2 = c - a
        h = np.cross(direction, edge2)
        det = float(np.dot(edge1, h))
        if abs(det) < 1e-14:
            return False
        inv_det = 1.0 / det
        s = origin - a
        u = float(np.dot(s, h)) * inv_det
        if u < 0.0 or u > 1.0:
            return False
        q = np.cross(s, edge1)
        v = float(np.dot(direction, q)) * inv_det
        if v < 0.0 or u + v > 1.0:
            return False
        t = float(np.dot(edge2, q)) * inv_det
        return t > 1e-10

    for i in range(n_s):
        for j in range(n_s):
            p00 = _eval(us[i], vs[j])
            p10 = _eval(us[i + 1], vs[j])
            p01 = _eval(us[i], vs[j + 1])
            p11 = _eval(us[i + 1], vs[j + 1])
            if p00 is None or p10 is None or p01 is None or p11 is None:
                continue
            if _tri_intersect(p00, p10, p01):
                count += 1
            if _tri_intersect(p10, p11, p01):
                count += 1
    return count % 2


def _point_in_body(point: np.ndarray, faces: list, rng: np.random.Generator) -> bool:
    """Ray-casting point-in-body test.

    Fire three independent rays; take the majority vote of the (odd/even)
    crossing parity to reduce sensitivity to grazing/degenerate hits.
    """
    results = []
    for _ in range(3):
        # Random direction (avoid axis-aligned to reduce degeneracies)
        d = rng.standard_normal(3)
        norm = float(np.linalg.norm(d))
        if norm < 1e-14:
            d = np.array([1.0, 0.3, 0.7])
            norm = float(np.linalg.norm(d))
        d = d / norm

        total = 0
        for face in faces:
            total += _ray_face_intersect(point, d, face)
        results.append(total % 2 == 1)

    return sum(results) >= 2  # majority vote


# ---------------------------------------------------------------------------
# Signed tet volume
# ---------------------------------------------------------------------------

def _tet_signed_volume(nodes: np.ndarray, tet: np.ndarray) -> float:
    """Signed volume of tetrahedron (a, b, c, d) = det([b-a, c-a, d-a]) / 6."""
    a, b, c, d = nodes[tet[0]], nodes[tet[1]], nodes[tet[2]], nodes[tet[3]]
    m = np.array([b - a, c - a, d - a])
    return float(np.linalg.det(m)) / 6.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tetrahedralize(body: Body, max_volume: Optional[float] = None) -> dict:
    """Delaunay volume mesh of *body* for FEM hand-off.

    Parameters
    ----------
    body : Body
        A closed (watertight) B-rep body.  The function samples its
        boundary and interior to obtain seed points for Delaunay.
    max_volume : float or None
        Optional maximum tetrahedron volume.  Oversized tets are refined
        by one round of centroid insertion + re-Delaunay.

    Returns
    -------
    dict
        ``nodes``  : np.ndarray (N, 3) float64 — vertex positions
        ``tets``   : np.ndarray (T, 4) int64   — positively-oriented tets
    """
    faces = body.all_faces()
    if not faces:
        raise ValueError("body has no faces — cannot tetrahedralize")

    rng = np.random.default_rng(42)

    # ------------------------------------------------------------------
    # 1. Bounding box
    # ------------------------------------------------------------------
    lo, hi = _body_bbox(body)
    diag = float(np.linalg.norm(hi - lo))
    if diag < 1e-14:
        raise ValueError("body bounding box is degenerate")

    # ------------------------------------------------------------------
    # 2. Sample boundary points
    # ------------------------------------------------------------------
    boundary_pts = []
    for face in faces:
        pts = _sample_face_points(face, n_uv=8)
        if len(pts):
            boundary_pts.append(pts)

    if not boundary_pts:
        raise ValueError("could not sample any boundary points from body")
    boundary = np.vstack(boundary_pts)

    # ------------------------------------------------------------------
    # 3. Sample interior points via rejection sampling
    # ------------------------------------------------------------------
    # Use ~4× as many interior seeds as boundary points (capped at 500
    # for speed; FEM quality is handled by the max_volume refinement pass).
    n_interior_target = min(500, max(50, len(boundary) * 4))

    interior_pts = []
    n_attempts = 0
    max_attempts = n_interior_target * 30

    while len(interior_pts) < n_interior_target and n_attempts < max_attempts:
        batch = lo + rng.random((64, 3)) * (hi - lo)
        for pt in batch:
            if _point_in_body(pt, faces, rng):
                interior_pts.append(pt)
                if len(interior_pts) >= n_interior_target:
                    break
        n_attempts += 64

    # ------------------------------------------------------------------
    # 4. Build combined point cloud + run Delaunay
    # ------------------------------------------------------------------
    all_pts_list = [boundary]
    if interior_pts:
        all_pts_list.append(np.array(interior_pts, dtype=float))
    all_pts = np.vstack(all_pts_list)

    # De-duplicate (merge points within a small tolerance)
    tol = diag * 1e-8
    # Round to grid and use unique rows
    rounded = np.round(all_pts / tol).astype(np.int64)
    _, idx = np.unique(rounded, axis=0, return_index=True)
    all_pts = all_pts[np.sort(idx)]

    if len(all_pts) < 4:
        raise ValueError(
            f"need at least 4 distinct points for tetrahedralization, got {len(all_pts)}"
        )

    tri = Delaunay(all_pts)
    simplices = tri.simplices  # (T, 4) int32

    # ------------------------------------------------------------------
    # 5. Keep only tets whose centroid is inside the body
    # ------------------------------------------------------------------
    centroids = all_pts[simplices].mean(axis=1)  # (T, 3)
    keep_mask = np.array(
        [_point_in_body(centroids[i], faces, rng) for i in range(len(simplices))],
        dtype=bool,
    )
    kept = simplices[keep_mask].copy()

    if len(kept) == 0:
        raise ValueError("no tetrahedra survived the inside-body filter")

    # ------------------------------------------------------------------
    # 6. Ensure positive orientation (swap vertices 2 & 3 if negative)
    # ------------------------------------------------------------------
    for i, tet in enumerate(kept):
        sv = _tet_signed_volume(all_pts, tet)
        if sv < 0.0:
            kept[i, 2], kept[i, 3] = kept[i, 3], kept[i, 2]
        # Tets with zero volume are degenerate — remove them
    vol_mask = np.array(
        [abs(_tet_signed_volume(all_pts, kept[i])) > 1e-30 for i in range(len(kept))],
        dtype=bool,
    )
    kept = kept[vol_mask]

    if len(kept) == 0:
        raise ValueError("no non-degenerate tetrahedra found inside body")

    # ------------------------------------------------------------------
    # 7. Optional: max_volume refinement (one round of centroid insertion)
    # ------------------------------------------------------------------
    if max_volume is not None:
        vols = np.array(
            [_tet_signed_volume(all_pts, kept[i]) for i in range(len(kept))],
            dtype=float,
        )
        oversized = kept[vols > max_volume]
        if len(oversized):
            extra_pts = all_pts[oversized].mean(axis=1)  # centroids of big tets
            all_pts = np.vstack([all_pts, extra_pts])
            tri2 = Delaunay(all_pts)
            simplices2 = tri2.simplices
            centroids2 = all_pts[simplices2].mean(axis=1)
            keep2 = np.array(
                [_point_in_body(centroids2[j], faces, rng) for j in range(len(simplices2))],
                dtype=bool,
            )
            kept = simplices2[keep2].copy()
            for i, tet in enumerate(kept):
                sv = _tet_signed_volume(all_pts, tet)
                if sv < 0.0:
                    kept[i, 2], kept[i, 3] = kept[i, 3], kept[i, 2]
            vol_mask2 = np.array(
                [abs(_tet_signed_volume(all_pts, kept[i])) > 1e-30 for i in range(len(kept))],
                dtype=bool,
            )
            kept = kept[vol_mask2]

    # ------------------------------------------------------------------
    # 8. Remove unreferenced nodes (keep only nodes used by tets)
    # ------------------------------------------------------------------
    used = np.unique(kept.ravel())
    old_to_new = np.full(len(all_pts), -1, dtype=np.int64)
    old_to_new[used] = np.arange(len(used), dtype=np.int64)
    nodes_out = all_pts[used]
    tets_out = old_to_new[kept].astype(np.int64)

    return {"nodes": nodes_out, "tets": tets_out}
