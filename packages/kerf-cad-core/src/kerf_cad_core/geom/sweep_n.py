"""sweep_n: N-rail sweep surface generation (GK-90).

Generalises sweep2 to 3 or more guide rails.  The profile evolves at each
station along the rails so that it simultaneously passes through (or between)
all rail positions, weighted by their barycentric coordinates relative to the
centroid.

For exactly 2 rails the function delegates to sweep2_rmf (fallback path).

Frame computation:
  frame='rmf'  — Wang 2008 rotation-minimising frame propagated along the
                 centroid spine of all rails (default, torsion-free).
"""
from __future__ import annotations

from typing import List

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.sweep1 import compute_rmf_frames
from kerf_cad_core.geom.sweep2 import sweep2_rmf


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sample_rails(rails: List[NurbsCurve], n: int) -> np.ndarray:
    """Sample *n* points on each rail uniformly.

    Returns an array of shape (R, n, 3) where R = len(rails).
    """
    ts = np.linspace(0.0, 1.0, n)
    return np.array([[rail.evaluate(t) for t in ts] for rail in rails])


def _centroid_spine(rail_pts: np.ndarray) -> np.ndarray:
    """Compute the centroid spine from rail_pts (R, n, 3) → (n, 3)."""
    return rail_pts.mean(axis=0)


def _spine_tangents(spine: np.ndarray) -> np.ndarray:
    """Compute unit tangents along a polyline (n, 3) → (n, 3)."""
    n = len(spine)
    tangents = np.zeros_like(spine)
    tangents[0] = spine[1] - spine[0]
    tangents[-1] = spine[-1] - spine[-2]
    tangents[1:-1] = spine[2:] - spine[:-2]
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms = np.where(norms < 1e-15, 1.0, norms)
    return tangents / norms


def _build_knots_v(n: int, degree: int) -> np.ndarray:
    """Build a clamped uniform knot vector for *n* control points at *degree*."""
    interior = n - degree - 1
    if interior <= 0:
        inner = np.array([])
    else:
        inner = np.linspace(0.0, 1.0, interior + 2)[1:-1]
    return np.concatenate([np.zeros(degree + 1), inner, np.ones(degree + 1)])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sweep_n(
    profile: NurbsCurve,
    rails: List[NurbsCurve],
    frame: str = "rmf",
) -> NurbsSurface:
    """Sweep *profile* along *rails* (3 or more guide rails).

    The profile is placed at each station so that it spans all rail positions.
    The centroid of the rail positions at each station defines the spine;
    an RMF frame (Wang 2008) is propagated along it.  Profile control points
    are mapped to world space using a weighted blend of all rail positions
    relative to the profile's local parameter.

    Parameters
    ----------
    profile : NurbsCurve
        The cross-section profile curve to sweep.
    rails : list of NurbsCurve
        Three or more guide rails.  For exactly 2 rails the function falls
        back to ``sweep2_rmf``.
    frame : {'rmf'}
        Frame type.  Only 'rmf' (rotation-minimising, Wang 2008) is
        supported.

    Returns
    -------
    NurbsSurface
        The swept surface.
    """
    if not isinstance(rails, (list, tuple)):
        raise TypeError("rails must be a list of NurbsCurve")
    R = len(rails)
    if R < 2:
        raise ValueError("sweep_n requires at least 2 rails")
    if any(r.degree < 1 for r in rails):
        raise ValueError("All rails must have degree >= 1")
    if profile.degree < 1:
        raise ValueError("Profile must have degree >= 1")
    if frame not in ("rmf",):
        raise ValueError(f"Unsupported frame type: {frame!r}")

    # --- 2-rail fallback ---
    if R == 2:
        return sweep2_rmf(profile, rails[0], rails[1])

    # --- N-rail (3+) path ---
    num_profile_pts = profile.num_control_points
    # Use enough stations to represent the rail geometry well.
    # We sample at max(rail.num_control_points) stations.
    n = max(r.num_control_points for r in rails)
    n = max(n, 4)

    # rail_pts[r, i] = position on rail r at station i.  shape: (R, n, 3)
    rail_pts = _sample_rails(rails, n)

    # Centroid spine
    spine = _centroid_spine(rail_pts)          # (n, 3)
    tangents = _spine_tangents(spine)          # (n, 3)

    # RMF frames along centroid spine
    rmf_frames = compute_rmf_frames(tangents, points=spine)  # list of (3,3)

    # Profile parameter t_j maps profile control point j to a value in [0, 1].
    profile_ts = (
        np.linspace(0.0, 1.0, num_profile_pts)
        if num_profile_pts > 1
        else np.array([0.5])
    )

    # control_points[j, i] = world position of profile cp j at station i.
    control_points = np.zeros((num_profile_pts, n, 3))

    for i in range(n):
        # Rail positions at this station.
        rpts = rail_pts[:, i, :]   # (R, 3)
        centroid = rpts.mean(axis=0)
        frame_mat = rmf_frames[i]   # (3, 3) columns = [T, r, s]

        for j in range(num_profile_pts):
            t_j = profile_ts[j]

            # Map profile parameter t_j ∈ [0,1] to a rail index (possibly
            # fractional) so that t_j=0 corresponds to rail 0 and t_j=1
            # to rail R-1.  Linear interpolation between adjacent rails.
            rail_idx_float = t_j * (R - 1)
            lo = int(np.floor(rail_idx_float))
            hi = min(lo + 1, R - 1)
            alpha = rail_idx_float - lo

            # Base position: interpolated between two adjacent rail positions.
            base_pt = (1.0 - alpha) * rpts[lo] + alpha * rpts[hi]

            # Local profile offset in the RMF frame.
            local_offset = frame_mat @ profile.control_points[j]

            # World point = interpolated rail base + frame-local profile offset.
            control_points[j, i] = base_pt + local_offset

    # Build knot vectors.
    knots_u = profile.knots.copy()
    degree_v = max(r.degree for r in rails)
    # Ensure degree_v does not exceed n-1.
    degree_v = min(degree_v, n - 1)
    knots_v = _build_knots_v(n, degree_v)

    return NurbsSurface(
        degree_u=profile.degree,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v,
    )
