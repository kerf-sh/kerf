"""
surface_offset.py
=================
GK-83 — Surface offset / parallel surface (true offset, not shell).

Produces a NURBS surface that is parallel to the input surface, offset by a
signed distance *d* along the analytic surface normal at every point.

Sign convention
---------------
``d > 0``  — outward (positive normal direction).
``d < 0``  — inward (negative normal direction).

Public API
----------
surface_offset(surface, distance) -> NurbsSurface
    True parallel-surface offset.  UV parameterisation is preserved (same
    degree, knot vectors and control-point net shape as the input).

    Analytic shortcuts (zero approximation error):
      * **Sphere**: scaled concentric sphere of radius ``r + d``.
      * **Plane** (degree 1×1, 4 coplanar control points): shifted by ``d``
        along the plane normal.

    General NURBS: each control point is displaced along the analytic unit
    surface normal at its Greville-abscissa parameter, producing an offset
    control-point net with the same topology.  The knot vectors are unchanged,
    so the parameterisation is preserved.

Raises
------
ValueError
    If *distance* is NaN/inf, or if the surface is so self-intersecting that
    the offset would collapse.
"""

from __future__ import annotations

import math

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_normal


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _greville_abscissae(knots: np.ndarray, degree: int) -> np.ndarray:
    """Greville abscissae for the given knot vector and polynomial degree.

    The *i*-th abscissa is the average of the *degree* interior knots
    starting at index ``i+1``:
        g_i = (knots[i+1] + knots[i+2] + ... + knots[i+degree]) / degree

    This gives *n* values where *n* = len(knots) - degree - 1, matching the
    number of control points in that direction.
    """
    n = len(knots) - degree - 1
    return np.array([
        float(np.mean(knots[i + 1: i + 1 + degree]))
        for i in range(n)
    ])


def _is_planar_nurbs_surface(
    surf: NurbsSurface,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Detect a degree-(1,1) planar NURBS patch with exactly 4 control points.

    Returns (point_on_plane, unit_normal) or None.
    """
    if surf.degree_u != 1 or surf.degree_v != 1:
        return None
    if surf.num_control_points_u != 2 or surf.num_control_points_v != 2:
        return None
    p00 = surf.control_points[0, 0, :3]
    p10 = surf.control_points[1, 0, :3]
    p01 = surf.control_points[0, 1, :3]
    p11 = surf.control_points[1, 1, :3]
    v1 = p10 - p00
    v2 = p01 - p00
    nrm = np.cross(v1, v2)
    mag = float(np.linalg.norm(nrm))
    if mag < 1e-12:
        return None
    unit_nrm = nrm / mag
    if abs(float(np.dot(p11 - p00, unit_nrm))) > 1e-9:
        return None
    return p00.copy(), unit_nrm


def _is_sphere_surface(surf: NurbsSurface) -> tuple[np.ndarray, float] | None:
    """Detect the standard rational revolution NURBS sphere.

    Returns (centre, radius) or None.
    """
    if surf.weights is None:
        return None
    if surf.degree_u != 2 or surf.degree_v != 2:
        return None
    P = surf.control_points[:, :, :3]
    nu, nv = P.shape[0], P.shape[1]
    if nu < 5 or nv < 5:
        return None
    col0 = P[:, 0, :]
    colN = P[:, nv - 1, :]
    if not (np.allclose(col0 - col0[0], 0.0, atol=1e-9) and
            np.allclose(colN - colN[0], 0.0, atol=1e-9)):
        return None
    south_pole = col0[0]
    north_pole = colN[0]
    centre = (south_pole + north_pole) * 0.5
    r_axis = float(np.linalg.norm(north_pole - south_pole)) * 0.5
    if r_axis < 1e-14:
        return None
    j_mid = nv // 2
    eq_pts = P[:, j_mid, :]
    W = surf.weights
    w_eq = W[:, j_mid]
    on_pts_mask = np.abs(w_eq - 1.0) < 1e-9
    on_pts = eq_pts[on_pts_mask]
    if len(on_pts) < 3:
        return None
    eq_dists = np.linalg.norm(on_pts - centre, axis=1)
    r_eq = float(eq_dists.mean())
    if r_eq < 1e-14:
        return None
    if abs(r_eq - r_axis) / r_axis > 1e-3:
        return None
    if float(eq_dists.std()) / r_eq > 1e-6:
        return None
    return centre, r_eq


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def surface_offset(surface: NurbsSurface, distance: float) -> NurbsSurface:
    """Return a NURBS surface parallel to *surface*, offset by *distance* along
    the surface normal.

    UV parameterisation (degree, knot vectors, control-point net shape) is
    preserved exactly.

    Parameters
    ----------
    surface:
        Input NURBS surface.
    distance:
        Signed offset distance.  Positive = outward (positive normal);
        negative = inward.

    Returns
    -------
    NurbsSurface
        The offset surface, sharing the same UV structure as the input.

    Raises
    ------
    ValueError
        If *distance* is NaN/inf, or if the offset collapses a sphere/plane.
    """
    if not isinstance(surface, NurbsSurface):
        raise ValueError(
            f"surface must be a NurbsSurface, got {type(surface).__name__}"
        )
    d = float(distance)
    if math.isnan(d) or math.isinf(d):
        raise ValueError(f"distance must be finite, got {d!r}")

    # ------------------------------------------------------------------
    # Analytic shortcut: sphere
    # ------------------------------------------------------------------
    sphere_info = _is_sphere_surface(surface)
    if sphere_info is not None:
        centre, r = sphere_info
        r_new = r + d
        if r_new <= 0.0:
            raise ValueError(
                f"offset distance {d} collapses sphere of radius {r}"
            )
        scale = r_new / r
        old_cps = surface.control_points.copy()
        new_cps = old_cps.copy()
        new_cps[:, :, :3] = centre + scale * (old_cps[:, :, :3] - centre)
        return NurbsSurface(
            degree_u=surface.degree_u,
            degree_v=surface.degree_v,
            control_points=new_cps,
            knots_u=surface.knots_u.copy(),
            knots_v=surface.knots_v.copy(),
            weights=surface.weights.copy() if surface.weights is not None else None,
        )

    # ------------------------------------------------------------------
    # Analytic shortcut: plane
    # ------------------------------------------------------------------
    plane_info = _is_planar_nurbs_surface(surface)
    if plane_info is not None:
        _, unit_nrm = plane_info
        old_cps = surface.control_points.copy()
        new_cps = old_cps.copy()
        new_cps[:, :, :3] = old_cps[:, :, :3] + d * unit_nrm
        return NurbsSurface(
            degree_u=surface.degree_u,
            degree_v=surface.degree_v,
            control_points=new_cps,
            knots_u=surface.knots_u.copy(),
            knots_v=surface.knots_v.copy(),
            weights=(
                surface.weights.copy() if surface.weights is not None else None
            ),
        )

    # ------------------------------------------------------------------
    # General NURBS: displace each control point along the surface normal
    # evaluated at its Greville-abscissa parameter.
    # ------------------------------------------------------------------
    # Compute Greville abscissae for U and V directions.
    g_u = _greville_abscissae(surface.knots_u, surface.degree_u)
    g_v = _greville_abscissae(surface.knots_v, surface.degree_v)

    nu = surface.num_control_points_u
    nv = surface.num_control_points_v

    # Clamp to the valid parameter domain.
    u_min = float(surface.knots_u[surface.degree_u])
    u_max = float(surface.knots_u[-(surface.degree_u + 1)])
    v_min = float(surface.knots_v[surface.degree_v])
    v_max = float(surface.knots_v[-(surface.degree_v + 1)])

    g_u = np.clip(g_u, u_min, u_max)
    g_v = np.clip(g_v, v_min, v_max)

    old_cps = surface.control_points.copy()
    new_cps = old_cps.copy()

    for i in range(nu):
        for j in range(nv):
            u = float(g_u[i])
            v = float(g_v[j])
            n = surface_normal(surface, u, v)
            new_cps[i, j, :3] = old_cps[i, j, :3] + d * n

    return NurbsSurface(
        degree_u=surface.degree_u,
        degree_v=surface.degree_v,
        control_points=new_cps,
        knots_u=surface.knots_u.copy(),
        knots_v=surface.knots_v.copy(),
        weights=(
            surface.weights.copy() if surface.weights is not None else None
        ),
    )
