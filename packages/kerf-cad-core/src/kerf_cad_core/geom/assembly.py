"""GK-122: Interference / collision detection between two Body objects.
GK-123: Clearance / minimum-gap analysis between two Body objects.

Pure-Python implementation (no OCCT dependency). Uses :func:`body_intersection`
(GK-18) to compute the overlapping region, then :func:`body_mass_props` to
measure its volume.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from kerf_cad_core.geom.brep import Body, SphereSurface, CylinderSurface, TorusSurface, Plane
from kerf_cad_core.geom.boolean import body_intersection
from kerf_cad_core.geom.mass_props import body_mass_props

# Type alias for a 3-D point returned as a plain list of floats.
Point3 = List[float]


# ---------------------------------------------------------------------------
# Internal helpers: surface parameter-domain detection
# ---------------------------------------------------------------------------

def _face_surface_samples(face, face_grid: int = 6) -> list:
    """Return a flat list of 3-D sample points for *face*'s underlying surface.

    The parameter domain is determined as follows:

    * :class:`~kerf_cad_core.geom.brep.SphereSurface`:
      ``u ∈ [0, 2π], v ∈ [−π/2, π/2]``
    * :class:`~kerf_cad_core.geom.brep.CylinderSurface` /
      :class:`~kerf_cad_core.geom.brep.TorusSurface`:
      ``u ∈ [0, 2π]``; ``v`` bounded by projecting loop vertices onto axis.
    * :class:`~kerf_cad_core.geom.brep.Plane` and everything else:
      Derive UV bounds by projecting all loop vertices onto the surface axes
      (or fall back to ``[0, 1] × [0, 1]`` if no loop data is available).
    """
    surf = face.surface
    pts: list = []

    try:
        if isinstance(surf, SphereSurface):
            us = np.linspace(0.0, 2.0 * math.pi, face_grid, endpoint=False)
            # Always include the equator (v=0) and the poles in the latitude
            # grid so that the closest-point estimate is tight regardless of
            # which axis the separation vector points along.
            vs_base = np.linspace(-math.pi / 2.0, math.pi / 2.0, face_grid)
            vs = np.unique(np.concatenate([vs_base, [0.0]]))
            for u in us:
                for v in vs:
                    p = surf.evaluate(float(u), float(v))
                    pts.append(p.tolist())
            return pts

        # Gather 3-D vertex positions from all loops on this face.
        vert_pts = []
        for loop in face.loops:
            for v in loop.vertices():
                vert_pts.append(v.point)

        if isinstance(surf, (CylinderSurface, TorusSurface)):
            # Full angular sweep.
            us = np.linspace(0.0, 2.0 * math.pi, face_grid, endpoint=False)
            # v range: project vertex positions onto the axis direction.
            if vert_pts and isinstance(surf, CylinderSurface):
                axis = surf.axis
                centre = surf.center
                projs = [float(np.dot(p - centre, axis)) for p in vert_pts]
                v0, v1 = min(projs), max(projs)
            else:
                v0, v1 = 0.0, 1.0
            vs = np.linspace(v0, v1, face_grid)
            for u in us:
                for v in vs:
                    p = surf.evaluate(float(u), float(v))
                    pts.append(p.tolist())
            return pts

        # Generic / Plane: project vertices to derive UV bounds.
        if vert_pts and isinstance(surf, Plane):
            origin = surf.origin
            xa = surf.x_axis
            ya = surf.y_axis
            us_v = [float(np.dot(p - origin, xa)) for p in vert_pts]
            vs_v = [float(np.dot(p - origin, ya)) for p in vert_pts]
            u0, u1 = min(us_v), max(us_v)
            v0, v1 = min(vs_v), max(vs_v)
        else:
            u0, u1, v0, v1 = 0.0, 1.0, 0.0, 1.0

        us = np.linspace(u0, u1, face_grid)
        vs = np.linspace(v0, v1, face_grid)
        for u in us:
            for v in vs:
                p = surf.evaluate(float(u), float(v))
                pts.append(p.tolist())

    except Exception:  # pragma: no cover – defensive for exotic surface types
        pass

    return pts


def interference(
    body_a: Body,
    body_b: Body,
    tol: float = 1e-6,
    vol_tol: float = 1e-10,
) -> dict:
    """Detect geometric interference (overlap) between two solid bodies.

    Parameters
    ----------
    body_a:
        First :class:`~kerf_cad_core.geom.brep.Body`.
    body_b:
        Second :class:`~kerf_cad_core.geom.brep.Body`.
    tol:
        Geometric tolerance forwarded to :func:`body_intersection`.
    vol_tol:
        Volume threshold below which the intersection is treated as empty
        (handles degenerate face-touching / edge-touching cases that produce
        a zero-volume shell).  Default 1e-10.

    Returns
    -------
    dict with keys:

    ``"interferes"``
        ``True`` when the overlap volume exceeds *vol_tol*.
    ``"volume"``
        Absolute volume of the intersection region (``0.0`` when disjoint).
    ``"region"``
        The intersection :class:`~kerf_cad_core.geom.brep.Body` when
        *interferes* is ``True``, otherwise ``None``.
    """
    region = body_intersection(body_a, body_b, tol=tol)

    # An empty Body (no faces) means the inputs are disjoint.
    if not region.all_faces():
        return {"interferes": False, "volume": 0.0, "region": None}

    props = body_mass_props(region)
    vol = abs(props["volume"])

    if vol <= vol_tol:
        return {"interferes": False, "volume": 0.0, "region": None}

    return {"interferes": True, "volume": vol, "region": region}


# ---------------------------------------------------------------------------
# GK-123: Clearance / minimum-gap analysis
# ---------------------------------------------------------------------------

def _sample_body_points(
    body: Body,
    edge_samples: int = 8,
    face_grid: int = 6,
) -> np.ndarray:
    """Return a (N, 3) array of representative surface sample points for *body*.

    Strategy (pure-Python, no OCCT):
      1. All B-rep vertices.
      2. Interior samples along every edge (``edge_samples`` per edge).
      3. Grid samples over each face's underlying surface (``face_grid × face_grid``
         per face), using type-specific parameter domains (see
         :func:`_face_surface_samples`).
      4. If the body has *no* vertices (degenerate), fall back to the origin so
         that the caller still gets a non-empty array.
    """
    pts: list = []

    # 1. Vertices
    for v in body.all_vertices():
        pts.append(v.point.tolist())

    # 2. Edge interior samples
    for edge in body.all_edges():
        ts = np.linspace(edge.t0, edge.t1, edge_samples + 2)[1:-1]
        for t in ts:
            try:
                p = edge.point(float(t))
                pts.append(p.tolist())
            except Exception:  # pragma: no cover – defensive
                pass

    # 3. Face surface grid samples
    for face in body.all_faces():
        pts.extend(_face_surface_samples(face, face_grid=face_grid))

    if not pts:
        pts.append([0.0, 0.0, 0.0])

    return np.array(pts, dtype=float)


def _closest_pair(
    pts_a: np.ndarray,
    pts_b: np.ndarray,
) -> Tuple[int, int, float]:
    """Brute-force O(|A|·|B|) closest pair search.

    Returns ``(idx_a, idx_b, distance)``.

    For typical B-rep bodies (hundreds of sample points) this is fast enough.
    A vectorised implementation avoids a Python loop over all pairs.
    """
    # Compute all pairwise distances in one vectorised call.
    # Shape: (len_a, 1, 3) - (1, len_b, 3) → (len_a, len_b, 3)
    diff = pts_a[:, np.newaxis, :] - pts_b[np.newaxis, :, :]  # (A, B, 3)
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)               # (A, B)
    flat_idx = int(np.argmin(dist2))
    ia = flat_idx // pts_b.shape[0]
    ib = flat_idx % pts_b.shape[0]
    return ia, ib, float(math.sqrt(dist2[ia, ib]))


def clearance(
    body_a: Body,
    body_b: Body,
    edge_samples: int = 8,
    face_grid: int = 6,
) -> dict:
    """Compute the minimum gap (clearance) between two :class:`Body` objects.

    The algorithm samples vertices and edge-interior points from each body's
    B-rep topology, then finds the closest pair of sample points via a
    vectorised brute-force search.  For disjoint convex bodies the vertex /
    edge samples are sufficient to locate the true minimum gap; for non-convex
    bodies the result is an upper-bound approximation whose accuracy improves
    with *edge_samples*.

    Parameters
    ----------
    body_a, body_b:
        The two :class:`~kerf_cad_core.geom.brep.Body` objects to analyse.
        They may be disjoint, touching, or overlapping.
    edge_samples:
        Number of interior sample points taken along each B-rep edge
        (in addition to the two endpoint vertices).  Default ``8``.

    Returns
    -------
    dict with keys:

    ``"gap"``
        Minimum distance between the two bodies' surface samples.
        Returns ``0.0`` (or a small negative value from the sample
        approximation) when the bodies overlap.
    ``"witness_a"``
        :data:`Point3` — the sample point on *body_a* closest to *body_b*.
    ``"witness_b"``
        :data:`Point3` — the sample point on *body_b* closest to *body_a*.

    Notes
    -----
    * Pure-Python / NumPy — no OCCT dependency.
    * The gap value is the *sample-based* distance; for curved surfaces it is
      an approximation (always ≥ the true minimum gap for convex shapes).
    * To detect interference (gap < 0), use :func:`interference` which
      computes the exact boolean intersection volume.

    Examples
    --------
    Two unit spheres with centres 5 units apart, radii 1 each::

        result = clearance(sphere_a, sphere_b)
        # result["gap"] ≈ 3.0  (5 − 1 − 1)
    """
    pts_a = _sample_body_points(body_a, edge_samples=edge_samples, face_grid=face_grid)
    pts_b = _sample_body_points(body_b, edge_samples=edge_samples, face_grid=face_grid)

    ia, ib, gap = _closest_pair(pts_a, pts_b)

    # When bodies overlap the surface-sample distance is always ≥ 0 because
    # all samples lie on the outer surface.  Detect interference and return
    # gap = 0.0 so callers can test ``gap ≤ 0`` as the overlap predicate.
    if gap > 0.0:
        iresult = interference(body_a, body_b)
        if iresult["interferes"]:
            # Pick representative witness points: closest surface samples
            # still make sense as contact-region indicators.
            return {
                "gap": 0.0,
                "witness_a": pts_a[ia].tolist(),
                "witness_b": pts_b[ib].tolist(),
            }

    return {
        "gap": gap,
        "witness_a": pts_a[ia].tolist(),
        "witness_b": pts_b[ib].tolist(),
    }
