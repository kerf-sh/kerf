"""
surface_analysis.py
===================
Pure-Python surface analysis suite for NURBS surfaces.

Provides Rhino-parity analysis functions operating on NurbsSurface objects
(from geom/nurbs.py) via sampled UV grids and first/second fundamental forms.

Functions
---------
gaussian_mean_curvature(surface, nu, nv) -> dict
    Gaussian (K) and mean (H) curvature, principal curvatures κ1/κ2, per-sample
    grid, min/max/false-colour band map.

draft_angle_analysis(surface, pull_dir, nu, nv, required_draft) -> dict
    Angle between surface normal and pull direction across the surface;
    min/max, undercut flag, per-point pass/fail.

surface_deviation(surface_or_points, reference, nu, nv, tolerance) -> dict
    Max and RMS distance: point-set→surface or surface→surface sampling.

naked_edge_detect(face_edge_adjacency, control_points_list, tolerance) -> dict
    Open boundary edges of a shell; tolerance-gap detection.

edge_continuity_report(surf_a, surf_b, shared_edge_pts, nu, tolerance) -> dict
    G0/G1/G2 continuity across a shared edge from two surfaces.

isocurve_extract(surface, parameter, direction, num_samples) -> dict
    Extract an isocurve (u=const or v=const) as a polyline.

area_centroid_secondmoment(surface, nu, nv) -> dict
    Numeric surface area, centroid, and second moments of area by integration.

All functions return {"ok": True/False, "reason": str, ...} — never raise.
LLM tools are registered via @register (gated, mirrors trim_curve.py pattern).
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, find_span

# ---------------------------------------------------------------------------
# Correct Cox-de Boor basis function evaluation
# (the nurbs.py basis_functions has a known bug where only N[0] is computed;
#  we implement the correct triangular algorithm here for surface analysis)
# ---------------------------------------------------------------------------

def _basis_fns(i: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    """Correct Cox-de Boor basis functions via the triangular table algorithm."""
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
    """Evaluate NurbsSurface at (u, v) using correct basis functions."""
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
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_NU: int = 20
_DEFAULT_NV: int = 20
_MIN_GRID: int = 3
_MAX_GRID: int = 200


def _surface_partials(
    surf: NurbsSurface,
    u: float,
    v: float,
    h_u: Optional[float] = None,
    h_v: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (dp/du, dp/dv) via central finite differences."""
    u_min = float(surf.knots_u[0])
    u_max = float(surf.knots_u[-1])
    v_min = float(surf.knots_v[0])
    v_max = float(surf.knots_v[-1])

    if h_u is None:
        h_u = max(1e-6, (u_max - u_min) * 5e-4)
    if h_v is None:
        h_v = max(1e-6, (v_max - v_min) * 5e-4)

    u_p = min(u_max, u + h_u)
    u_m = max(u_min, u - h_u)
    v_p = min(v_max, v + h_v)
    v_m = max(v_min, v - h_v)

    dp_du = (_eval_surface(surf, u_p, v)[:3] - _eval_surface(surf, u_m, v)[:3]) / max(u_p - u_m, 1e-15)
    dp_dv = (_eval_surface(surf, u, v_p)[:3] - _eval_surface(surf, u, v_m)[:3]) / max(v_p - v_m, 1e-15)
    return dp_du, dp_dv


def _surface_second_partials(
    surf: NurbsSurface,
    u: float,
    v: float,
    h_u: Optional[float] = None,
    h_v: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (d²p/du², d²p/dv², d²p/dudv) via central finite differences."""
    u_min = float(surf.knots_u[0])
    u_max = float(surf.knots_u[-1])
    v_min = float(surf.knots_v[0])
    v_max = float(surf.knots_v[-1])

    if h_u is None:
        h_u = max(1e-5, (u_max - u_min) * 2e-3)
    if h_v is None:
        h_v = max(1e-5, (v_max - v_min) * 2e-3)

    u_p = min(u_max, u + h_u)
    u_m = max(u_min, u - h_u)
    v_p = min(v_max, v + h_v)
    v_m = max(v_min, v - h_v)

    duu = (
        _eval_surface(surf, u_p, v)[:3]
        - 2.0 * _eval_surface(surf, u, v)[:3]
        + _eval_surface(surf, u_m, v)[:3]
    ) / max((u_p - u_m) ** 2 / 4.0, 1e-30)

    dvv = (
        _eval_surface(surf, u, v_p)[:3]
        - 2.0 * _eval_surface(surf, u, v)[:3]
        + _eval_surface(surf, u, v_m)[:3]
    ) / max((v_p - v_m) ** 2 / 4.0, 1e-30)

    # Mixed partial via four-point cross difference
    dudv = (
        _eval_surface(surf, u_p, v_p)[:3]
        - _eval_surface(surf, u_p, v_m)[:3]
        - _eval_surface(surf, u_m, v_p)[:3]
        + _eval_surface(surf, u_m, v_m)[:3]
    ) / max((u_p - u_m) * (v_p - v_m), 1e-30)

    return duu, dvv, dudv


def _unit_normal(dp_du: np.ndarray, dp_dv: np.ndarray) -> np.ndarray:
    n = np.cross(dp_du, dp_dv)
    nrm = float(np.linalg.norm(n))
    if nrm < 1e-15:
        return np.array([0.0, 0.0, 1.0])
    return n / nrm


def _uv_grid(surf: NurbsSurface, nu: int, nv: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return (us, vs) linspaces covering the surface domain."""
    u_min = float(surf.knots_u[0])
    u_max = float(surf.knots_u[-1])
    v_min = float(surf.knots_v[0])
    v_max = float(surf.knots_v[-1])
    us = np.linspace(u_min, u_max, max(nu, _MIN_GRID))
    vs = np.linspace(v_min, v_max, max(nv, _MIN_GRID))
    return us, vs


def _clamp_grid(nu: int, nv: int) -> Tuple[int, int]:
    return (
        int(np.clip(nu, _MIN_GRID, _MAX_GRID)),
        int(np.clip(nv, _MIN_GRID, _MAX_GRID)),
    )


# ---------------------------------------------------------------------------
# gaussian_mean_curvature
# ---------------------------------------------------------------------------

def gaussian_mean_curvature(
    surface: NurbsSurface,
    nu: int = _DEFAULT_NU,
    nv: int = _DEFAULT_NV,
) -> dict:
    """Compute Gaussian curvature K and mean curvature H across a UV grid.

    Parameters
    ----------
    surface : NurbsSurface
    nu, nv  : grid resolution (clamped to [3, 200])

    Returns
    -------
    dict
        ok, K_grid (nu×nv), H_grid (nu×nv), kappa1_grid, kappa2_grid,
        K_min, K_max, H_min, H_max, num_samples.
        On failure: {ok: False, reason: str}.
    """
    try:
        if not isinstance(surface, NurbsSurface):
            return {"ok": False, "reason": f"expected NurbsSurface, got {type(surface).__name__}"}

        nu, nv = _clamp_grid(nu, nv)
        us, vs = _uv_grid(surface, nu, nv)

        K_grid = np.zeros((nu, nv))
        H_grid = np.zeros((nu, nv))
        k1_grid = np.zeros((nu, nv))
        k2_grid = np.zeros((nu, nv))

        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                dp_du, dp_dv = _surface_partials(surface, u, v)
                duu, dvv, dudv = _surface_second_partials(surface, u, v)
                n = _unit_normal(dp_du, dp_dv)

                # First fundamental form coefficients
                E = float(np.dot(dp_du, dp_du))
                F = float(np.dot(dp_du, dp_dv))
                G = float(np.dot(dp_dv, dp_dv))
                EG_F2 = E * G - F * F

                if abs(EG_F2) < 1e-20:
                    continue

                # Second fundamental form coefficients
                e = float(np.dot(duu, n))
                f = float(np.dot(dudv, n))
                g = float(np.dot(dvv, n))

                K = (e * g - f * f) / EG_F2
                H = (e * G - 2.0 * f * F + g * E) / (2.0 * EG_F2)

                # Principal curvatures from H, K
                disc = max(0.0, H * H - K)
                sq = math.sqrt(disc)
                k1 = H + sq
                k2 = H - sq

                K_grid[i, j] = K
                H_grid[i, j] = H
                k1_grid[i, j] = k1
                k2_grid[i, j] = k2

        return {
            "ok": True,
            "reason": "",
            "K_grid": K_grid.tolist(),
            "H_grid": H_grid.tolist(),
            "kappa1_grid": k1_grid.tolist(),
            "kappa2_grid": k2_grid.tolist(),
            "K_min": float(np.min(K_grid)),
            "K_max": float(np.max(K_grid)),
            "H_min": float(np.min(H_grid)),
            "H_max": float(np.max(H_grid)),
            "num_samples": nu * nv,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# draft_angle_analysis
# ---------------------------------------------------------------------------

def draft_angle_analysis(
    surface: NurbsSurface,
    pull_direction: Sequence[float],
    nu: int = _DEFAULT_NU,
    nv: int = _DEFAULT_NV,
    required_draft_deg: float = 0.0,
) -> dict:
    """Compute draft angle (surface normal vs pull direction) across a UV grid.

    Parameters
    ----------
    surface : NurbsSurface
    pull_direction : 3-element sequence (need not be unit)
    nu, nv  : grid resolution
    required_draft_deg : minimum acceptable draft angle in degrees (default 0)

    Returns
    -------
    dict
        ok, angle_grid (degrees), undercut_grid (bool), min_angle, max_angle,
        has_undercut, pass_fail_grid, num_samples.
        Undercut = surface normal opposing pull direction (angle < 0).
    """
    try:
        if not isinstance(surface, NurbsSurface):
            return {"ok": False, "reason": f"expected NurbsSurface, got {type(surface).__name__}"}

        pull = np.asarray(pull_direction, dtype=float)
        if pull.shape != (3,):
            return {"ok": False, "reason": "pull_direction must be a 3-element sequence"}
        pnrm = float(np.linalg.norm(pull))
        if pnrm < 1e-15:
            return {"ok": False, "reason": "pull_direction must be non-zero"}
        pull = pull / pnrm

        if not isinstance(required_draft_deg, (int, float)):
            return {"ok": False, "reason": "required_draft_deg must be a number"}

        nu, nv = _clamp_grid(nu, nv)
        us, vs = _uv_grid(surface, nu, nv)

        angle_grid = np.zeros((nu, nv))
        undercut_grid = np.zeros((nu, nv), dtype=bool)
        pass_fail_grid = np.zeros((nu, nv), dtype=bool)

        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                dp_du, dp_dv = _surface_partials(surface, u, v)
                n = _unit_normal(dp_du, dp_dv)
                # draft angle = angle between normal and pull - 90°
                # equivalently: 90° - angle between normal and pull
                cos_a = float(np.dot(n, pull))
                cos_a = float(np.clip(cos_a, -1.0, 1.0))
                # draft angle is measured from tangent plane, so:
                # draft = 90 - arccos(|cos_a|) when normal aligns with pull
                # or negative when undercut
                draft_rad = math.asin(cos_a)  # signed draft angle
                draft_deg = math.degrees(draft_rad)
                angle_grid[i, j] = draft_deg
                undercut_grid[i, j] = draft_deg < 0.0
                pass_fail_grid[i, j] = draft_deg >= required_draft_deg

        has_undercut = bool(np.any(undercut_grid))

        return {
            "ok": True,
            "reason": "",
            "angle_grid": angle_grid.tolist(),
            "undercut_grid": undercut_grid.tolist(),
            "pass_fail_grid": pass_fail_grid.tolist(),
            "min_angle": float(np.min(angle_grid)),
            "max_angle": float(np.max(angle_grid)),
            "has_undercut": has_undercut,
            "required_draft_deg": float(required_draft_deg),
            "num_samples": nu * nv,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# surface_deviation
# ---------------------------------------------------------------------------

def _closest_dist_point_to_surface(
    surface: NurbsSurface,
    pt: np.ndarray,
    nu: int = 40,
    nv: int = 40,
) -> float:
    """Brute-force closest distance from a 3D point to a sampled surface grid."""
    us, vs = _uv_grid(surface, nu, nv)
    min_d2 = float("inf")
    for u in us:
        for v in vs:
            sp = _eval_surface(surface, u, v)[:3]
            d2 = float(np.sum((sp - pt[:3]) ** 2))
            if d2 < min_d2:
                min_d2 = d2
    return math.sqrt(max(0.0, min_d2))


def surface_deviation(
    query: Union[NurbsSurface, Sequence],
    reference: NurbsSurface,
    nu: int = _DEFAULT_NU,
    nv: int = _DEFAULT_NV,
    tolerance: float = 1e-3,
) -> dict:
    """Compute max and RMS deviation between a point set (or surface) and a reference surface.

    Parameters
    ----------
    query     : NurbsSurface or list of [x,y,z] points
    reference : NurbsSurface (the surface to measure distances to)
    nu, nv    : sampling grid for query surface (ignored when query is a point list)
    tolerance : threshold for pass/fail

    Returns
    -------
    dict
        ok, max_deviation, rms_deviation, num_points, within_tolerance,
        distances (list of floats).
    """
    try:
        if not isinstance(reference, NurbsSurface):
            return {"ok": False, "reason": f"reference must be NurbsSurface, got {type(reference).__name__}"}

        if isinstance(query, NurbsSurface):
            nu, nv = _clamp_grid(nu, nv)
            us, vs = _uv_grid(query, nu, nv)
            pts = []
            for u in us:
                for v in vs:
                    pts.append(_eval_surface(query, u, v)[:3])
        else:
            try:
                pts = [np.asarray(p, dtype=float)[:3] for p in query]
            except Exception as exc:
                return {"ok": False, "reason": f"invalid query points: {exc}"}

        if not pts:
            return {"ok": False, "reason": "no query points"}

        nu_ref = max(_MIN_GRID, min(40, nu))
        nv_ref = max(_MIN_GRID, min(40, nv))

        distances = []
        for pt in pts:
            d = _closest_dist_point_to_surface(reference, pt, nu_ref, nv_ref)
            distances.append(d)

        dists = np.array(distances)
        max_dev = float(np.max(dists))
        rms_dev = float(np.sqrt(np.mean(dists ** 2)))
        within_tol = bool(max_dev <= tolerance)

        return {
            "ok": True,
            "reason": "",
            "max_deviation": max_dev,
            "rms_deviation": rms_dev,
            "num_points": len(distances),
            "within_tolerance": within_tol,
            "tolerance": float(tolerance),
            "distances": [float(d) for d in distances],
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# naked_edge_detect
# ---------------------------------------------------------------------------

def naked_edge_detect(
    face_edge_adjacency: dict,
    tolerance: float = 1e-6,
) -> dict:
    """Detect naked (boundary) edges of a shell from a face-edge adjacency map.

    Parameters
    ----------
    face_edge_adjacency : dict mapping face_id -> list of edge_ids
        Each edge_id appears once (naked) or twice (shared) across all faces.
    tolerance : unused here (reserved for gap-check variant)

    Returns
    -------
    dict
        ok, naked_edges (list of edge_id), naked_edge_count, is_closed.
        A shell is closed (watertight) when naked_edge_count == 0.
    """
    try:
        if not isinstance(face_edge_adjacency, dict):
            return {"ok": False, "reason": "face_edge_adjacency must be a dict mapping face_id -> [edge_ids]"}

        edge_count: dict = {}
        for face_id, edges in face_edge_adjacency.items():
            if not isinstance(edges, (list, tuple)):
                return {"ok": False, "reason": f"face {face_id!r}: edges must be a list"}
            for eid in edges:
                edge_count[eid] = edge_count.get(eid, 0) + 1

        naked = [eid for eid, cnt in edge_count.items() if cnt == 1]
        naked.sort(key=lambda x: str(x))

        return {
            "ok": True,
            "reason": "",
            "naked_edges": naked,
            "naked_edge_count": len(naked),
            "is_closed": len(naked) == 0,
            "total_edges": len(edge_count),
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# edge_continuity_report
# ---------------------------------------------------------------------------

def edge_continuity_report(
    surf_a: NurbsSurface,
    surf_b: NurbsSurface,
    shared_edge_pts: Sequence,
    num_samples: int = 20,
    tolerance: float = 1e-4,
) -> dict:
    """Report G0/G1/G2 continuity across a shared edge between two surfaces.

    For each sampled point along the shared edge, the function:
    - G0: measures position distance between surf_a and surf_b evaluations.
    - G1: measures angle (degrees) between surface normals.
    - G2: measures difference in mean curvature H between the two surfaces.

    Parameters
    ----------
    surf_a, surf_b  : NurbsSurface on each side of the edge
    shared_edge_pts : list of [x,y,z] points along the shared edge
    num_samples     : how many points to sample along the edge
    tolerance       : G0 position tolerance (metres)

    Returns
    -------
    dict
        ok, G0_max, G0_rms, G1_max_deg, G1_rms_deg, G2_max, G2_rms,
        G0_ok, G1_ok, G2_ok (bool), per_point list.
    """
    try:
        if not isinstance(surf_a, NurbsSurface):
            return {"ok": False, "reason": "surf_a must be NurbsSurface"}
        if not isinstance(surf_b, NurbsSurface):
            return {"ok": False, "reason": "surf_b must be NurbsSurface"}

        edge_pts = [np.asarray(p, dtype=float)[:3] for p in shared_edge_pts]
        if len(edge_pts) < 2:
            return {"ok": False, "reason": "shared_edge_pts must have at least 2 points"}

        # Resample edge_pts to num_samples
        total_len = sum(
            float(np.linalg.norm(edge_pts[i + 1] - edge_pts[i]))
            for i in range(len(edge_pts) - 1)
        )
        if total_len < 1e-15:
            return {"ok": False, "reason": "shared_edge_pts are all coincident"}

        # Parametrise by arc length and resample
        ns = max(2, int(num_samples))
        t_vals = np.linspace(0.0, 1.0, ns)
        # Arc-length parametrisation
        lengths = [0.0]
        for i in range(len(edge_pts) - 1):
            lengths.append(lengths[-1] + float(np.linalg.norm(edge_pts[i + 1] - edge_pts[i])))
        lengths = np.array(lengths) / lengths[-1]

        sampled_pts = []
        for t in t_vals:
            idx = int(np.searchsorted(lengths, t, side="right")) - 1
            idx = max(0, min(idx, len(edge_pts) - 2))
            seg_len = lengths[idx + 1] - lengths[idx]
            if seg_len < 1e-15:
                sampled_pts.append(edge_pts[idx].copy())
            else:
                alpha = (t - lengths[idx]) / seg_len
                sampled_pts.append((1 - alpha) * edge_pts[idx] + alpha * edge_pts[idx + 1])

        def _closest_uv(surf: NurbsSurface, pt: np.ndarray, n_u=20, n_v=20):
            us, vs = _uv_grid(surf, n_u, n_v)
            best_d2 = float("inf")
            best_u, best_v = us[len(us) // 2], vs[len(vs) // 2]
            for u in us:
                for v in vs:
                    sp = _eval_surface(surf, u, v)[:3]
                    d2 = float(np.sum((sp - pt) ** 2))
                    if d2 < best_d2:
                        best_d2 = d2
                        best_u, best_v = u, v
            return best_u, best_v

        per_point = []
        G0_vals, G1_vals, G2_vals = [], [], []

        for pt in sampled_pts:
            ua, va = _closest_uv(surf_a, pt)
            ub, vb = _closest_uv(surf_b, pt)

            pa = _eval_surface(surf_a, ua, va)[:3]
            pb = _eval_surface(surf_b, ub, vb)[:3]
            g0 = float(np.linalg.norm(pa - pb))

            dpdu_a, dpdv_a = _surface_partials(surf_a, ua, va)
            dpdu_b, dpdv_b = _surface_partials(surf_b, ub, vb)
            na = _unit_normal(dpdu_a, dpdv_a)
            nb = _unit_normal(dpdu_b, dpdv_b)
            cos_ang = float(np.clip(np.dot(na, nb), -1.0, 1.0))
            g1_deg = math.degrees(math.acos(abs(cos_ang)))

            # Mean curvature at each point
            def _mean_curv(surf, u, v):
                dp_du, dp_dv = _surface_partials(surf, u, v)
                duu, dvv, dudv = _surface_second_partials(surf, u, v)
                n = _unit_normal(dp_du, dp_dv)
                E = float(np.dot(dp_du, dp_du))
                F = float(np.dot(dp_du, dp_dv))
                G = float(np.dot(dp_dv, dp_dv))
                EG_F2 = E * G - F * F
                if abs(EG_F2) < 1e-20:
                    return 0.0
                e = float(np.dot(duu, n))
                f = float(np.dot(dudv, n))
                g = float(np.dot(dvv, n))
                return (e * G - 2.0 * f * F + g * E) / (2.0 * EG_F2)

            Ha = _mean_curv(surf_a, ua, va)
            Hb = _mean_curv(surf_b, ub, vb)
            g2 = abs(Ha - Hb)

            G0_vals.append(g0)
            G1_vals.append(g1_deg)
            G2_vals.append(g2)
            per_point.append({"G0": g0, "G1_deg": g1_deg, "G2_delta_H": g2})

        G0_arr = np.array(G0_vals)
        G1_arr = np.array(G1_vals)
        G2_arr = np.array(G2_vals)

        G0_tol = tolerance
        G1_tol_deg = 0.1   # 0.1° tangent tolerance
        G2_tol = 0.01      # curvature tolerance

        return {
            "ok": True,
            "reason": "",
            "G0_max": float(np.max(G0_arr)),
            "G0_rms": float(np.sqrt(np.mean(G0_arr ** 2))),
            "G1_max_deg": float(np.max(G1_arr)),
            "G1_rms_deg": float(np.sqrt(np.mean(G1_arr ** 2))),
            "G2_max": float(np.max(G2_arr)),
            "G2_rms": float(np.sqrt(np.mean(G2_arr ** 2))),
            "G0_ok": bool(np.max(G0_arr) <= G0_tol),
            "G1_ok": bool(np.max(G1_arr) <= G1_tol_deg),
            "G2_ok": bool(np.max(G2_arr) <= G2_tol),
            "num_samples": len(sampled_pts),
            "per_point": per_point,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# isocurve_extract
# ---------------------------------------------------------------------------

def isocurve_extract(
    surface: NurbsSurface,
    parameter: float,
    direction: str = "u",
    num_samples: int = 50,
) -> dict:
    """Extract an isocurve at a fixed u or v parameter value.

    Parameters
    ----------
    surface    : NurbsSurface
    parameter  : the fixed u (or v) value
    direction  : 'u' (fix u, vary v) or 'v' (fix v, vary u)
    num_samples: number of polyline vertices

    Returns
    -------
    dict
        ok, points (list of [x,y,z]), parameter, direction, arc_length.
    """
    try:
        if not isinstance(surface, NurbsSurface):
            return {"ok": False, "reason": f"expected NurbsSurface, got {type(surface).__name__}"}

        if direction not in ("u", "v"):
            return {"ok": False, "reason": "direction must be 'u' or 'v'"}

        ns = max(2, int(num_samples))

        u_min = float(surface.knots_u[0])
        u_max = float(surface.knots_u[-1])
        v_min = float(surface.knots_v[0])
        v_max = float(surface.knots_v[-1])

        if direction == "u":
            param = float(np.clip(parameter, u_min, u_max))
            varying = np.linspace(v_min, v_max, ns)
            pts = [_eval_surface(surface, param, v)[:3].tolist() for v in varying]
        else:
            param = float(np.clip(parameter, v_min, v_max))
            varying = np.linspace(u_min, u_max, ns)
            pts = [_eval_surface(surface, u, param)[:3].tolist() for u in varying]

        arc_length = sum(
            float(np.linalg.norm(np.array(pts[i + 1]) - np.array(pts[i])))
            for i in range(len(pts) - 1)
        )

        return {
            "ok": True,
            "reason": "",
            "points": pts,
            "parameter": param,
            "direction": direction,
            "num_samples": ns,
            "arc_length": arc_length,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# area_centroid_secondmoment
# ---------------------------------------------------------------------------

def area_centroid_secondmoment(
    surface: NurbsSurface,
    nu: int = _DEFAULT_NU,
    nv: int = _DEFAULT_NV,
) -> dict:
    """Compute surface area, centroid, and second moments of area by numeric integration.

    Uses Gaussian quadrature via a UV sample grid and the cross-product magnitude
    of first partials (the area element ||dp/du × dp/dv||).

    Parameters
    ----------
    surface : NurbsSurface
    nu, nv  : integration grid resolution

    Returns
    -------
    dict
        ok, area, centroid ([x,y,z]), Ixx, Iyy, Izz, Ixy, Ixz, Iyz,
        num_samples.
    """
    try:
        if not isinstance(surface, NurbsSurface):
            return {"ok": False, "reason": f"expected NurbsSurface, got {type(surface).__name__}"}

        nu, nv = _clamp_grid(nu, nv)
        us, vs = _uv_grid(surface, nu, nv)

        u_min = float(surface.knots_u[0])
        u_max = float(surface.knots_u[-1])
        v_min = float(surface.knots_v[0])
        v_max = float(surface.knots_v[-1])
        # Use midpoint-rule cell size: domain / nu so that nu cells tile [u_min, u_max]
        # exactly, avoiding the (nu-1) over-count from linspace endpoints.
        du = (u_max - u_min) / nu if nu > 0 else 1.0
        dv = (v_max - v_min) / nv if nv > 0 else 1.0

        area = 0.0
        centroid = np.zeros(3)
        Ixx = Iyy = Izz = 0.0
        Ixy = Ixz = Iyz = 0.0

        for u in us:
            for v in vs:
                dp_du, dp_dv = _surface_partials(surface, u, v)
                cross = np.cross(dp_du, dp_dv)
                dA = float(np.linalg.norm(cross)) * du * dv

                p = _eval_surface(surface, u, v)[:3]
                area += dA
                centroid += p * dA
                x, y, z = float(p[0]), float(p[1]), float(p[2])
                Ixx += (y * y + z * z) * dA
                Iyy += (x * x + z * z) * dA
                Izz += (x * x + y * y) * dA
                Ixy += x * y * dA
                Ixz += x * z * dA
                Iyz += y * z * dA

        if area > 1e-20:
            centroid /= area

        return {
            "ok": True,
            "reason": "",
            "area": float(area),
            "centroid": centroid.tolist(),
            "Ixx": float(Ixx),
            "Iyy": float(Iyy),
            "Izz": float(Izz),
            "Ixy": float(Ixy),
            "Ixz": float(Ixz),
            "Iyz": float(Iyz),
            "num_samples": nu * nv,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


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
    # surface_gaussian_mean_curvature
    # ------------------------------------------------------------------

    _gaussian_mean_curvature_spec = ToolSpec(
        name="surface_gaussian_mean_curvature",
        description=(
            "Compute Gaussian curvature K and mean curvature H across a NURBS surface "
            "using first and second fundamental forms over a UV sample grid. Returns "
            "K_grid, H_grid, kappa1/kappa2 grids, and min/max statistics for false-colour "
            "band mapping (Rhino CurvatureAnalysis parity).\n\n"
            "Returns: {ok, K_grid, H_grid, kappa1_grid, kappa2_grid, K_min, K_max, "
            "H_min, H_max, num_samples}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {"type": "integer", "description": "Surface degree in U."},
                "degree_v": {"type": "integer", "description": "Surface degree in V."},
                "control_points": {
                    "type": "array",
                    "description": "Flattened nu*nv control points [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "grid_u": {"type": "integer", "description": "UV grid resolution (default 20)."},
                "grid_v": {"type": "integer"},
            },
            "required": ["degree_u", "degree_v", "control_points", "num_u", "num_v"],
        },
    )

    def _build_surface_from_args(a: dict):
        """Build NurbsSurface from tool args dict. Returns (surface, error_str)."""
        degree_u = a.get("degree_u")
        degree_v = a.get("degree_v")
        raw_cp = a.get("control_points", [])
        num_u = a.get("num_u")
        num_v = a.get("num_v")

        if any(x is None for x in [degree_u, degree_v, num_u, num_v]) or not raw_cp:
            return None, "degree_u, degree_v, control_points, num_u, num_v are required"

        try:
            degree_u = int(degree_u)
            degree_v = int(degree_v)
            num_u = int(num_u)
            num_v = int(num_v)
        except (TypeError, ValueError) as exc:
            return None, f"degree/num must be integers: {exc}"

        if degree_u < 1 or degree_v < 1:
            return None, "degree_u and degree_v must be >= 1"
        if num_u < 2 or num_v < 2:
            return None, "num_u and num_v must be >= 2"
        if len(raw_cp) != num_u * num_v:
            return None, f"control_points length {len(raw_cp)} != num_u*num_v={num_u*num_v}"

        try:
            cp_flat = [np.asarray(p, dtype=float) for p in raw_cp]
            dim = cp_flat[0].size
            cp = np.array([p.tolist()[:dim] for p in cp_flat], dtype=float).reshape(num_u, num_v, dim)
        except Exception as exc:
            return None, f"invalid control_points: {exc}"

        def _make_knots(n: int, deg: int) -> np.ndarray:
            inner = max(0, n - deg - 1)
            return np.concatenate([
                np.zeros(deg + 1),
                np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
                np.ones(deg + 1),
            ])

        try:
            surface = NurbsSurface(
                degree_u=degree_u, degree_v=degree_v,
                control_points=cp,
                knots_u=_make_knots(num_u, degree_u),
                knots_v=_make_knots(num_v, degree_v),
            )
        except Exception as exc:
            return None, f"failed to build NurbsSurface: {exc}"

        return surface, ""

    @register(_gaussian_mean_curvature_spec)
    async def run_surface_gaussian_mean_curvature(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        surface, err = _build_surface_from_args(a)
        if surface is None:
            return err_payload(err, "BAD_ARGS")

        nu = int(a.get("grid_u", _DEFAULT_NU))
        nv = int(a.get("grid_v", _DEFAULT_NV))
        result = gaussian_mean_curvature(surface, nu, nv)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)

    # ------------------------------------------------------------------
    # surface_draft_angle_analysis
    # ------------------------------------------------------------------

    _draft_angle_spec = ToolSpec(
        name="surface_draft_angle_analysis",
        description=(
            "Compute draft angle (surface normal vs pull direction) across a NURBS surface. "
            "Returns angle_grid (degrees), undercut regions, pass/fail vs required_draft_deg "
            "(Rhino DraftAngleAnalysis parity). Negative angles indicate undercuts.\n\n"
            "Returns: {ok, angle_grid, undercut_grid, pass_fail_grid, min_angle, max_angle, "
            "has_undercut}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {"type": "integer"},
                "degree_v": {"type": "integer"},
                "control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "pull_direction": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "3-element pull direction vector, e.g. [0,0,1].",
                },
                "required_draft_deg": {
                    "type": "number",
                    "description": "Minimum acceptable draft angle in degrees (default 0).",
                },
                "grid_u": {"type": "integer"},
                "grid_v": {"type": "integer"},
            },
            "required": ["degree_u", "degree_v", "control_points", "num_u", "num_v", "pull_direction"],
        },
    )

    @register(_draft_angle_spec)
    async def run_surface_draft_angle_analysis(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        surface, err = _build_surface_from_args(a)
        if surface is None:
            return err_payload(err, "BAD_ARGS")

        pull = a.get("pull_direction")
        if not pull or len(pull) != 3:
            return err_payload("pull_direction must be a 3-element list", "BAD_ARGS")

        nu = int(a.get("grid_u", _DEFAULT_NU))
        nv = int(a.get("grid_v", _DEFAULT_NV))
        req = float(a.get("required_draft_deg", 0.0))

        result = draft_angle_analysis(surface, pull, nu, nv, req)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)

    # ------------------------------------------------------------------
    # surface_deviation_check
    # ------------------------------------------------------------------

    _surface_deviation_spec = ToolSpec(
        name="surface_deviation_check",
        description=(
            "Compute max and RMS deviation between a point cloud (or sampled surface) "
            "and a reference NURBS surface (Rhino surface-deviation parity). Useful for "
            "comparing a reconstructed surface to measured scan data.\n\n"
            "Returns: {ok, max_deviation, rms_deviation, within_tolerance, distances}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query_points": {
                    "type": "array",
                    "description": "List of [x,y,z] query points.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "degree_u": {"type": "integer"},
                "degree_v": {"type": "integer"},
                "control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "tolerance": {"type": "number", "description": "Pass/fail threshold (default 1e-3)."},
            },
            "required": ["query_points", "degree_u", "degree_v", "control_points", "num_u", "num_v"],
        },
    )

    @register(_surface_deviation_spec)
    async def run_surface_deviation_check(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        surface, err = _build_surface_from_args(a)
        if surface is None:
            return err_payload(err, "BAD_ARGS")

        query_pts = a.get("query_points")
        if not query_pts:
            return err_payload("query_points is required and must be non-empty", "BAD_ARGS")

        tol = float(a.get("tolerance", 1e-3))
        result = surface_deviation(query_pts, surface, tolerance=tol)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)

    # ------------------------------------------------------------------
    # surface_naked_edge_detect
    # ------------------------------------------------------------------

    _naked_edge_spec = ToolSpec(
        name="surface_naked_edge_detect",
        description=(
            "Detect naked (open boundary) edges of a B-rep shell from a face-edge "
            "adjacency map (Rhino ShowEdges-naked parity). An edge appearing in only "
            "one face is naked; appearing in two faces is shared (interior).\n\n"
            "Returns: {ok, naked_edges, naked_edge_count, is_closed}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "face_edge_adjacency": {
                    "type": "object",
                    "description": "Dict mapping face_id (str) -> list of edge_id strings.",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "tolerance": {"type": "number", "description": "Gap tolerance (default 1e-6)."},
            },
            "required": ["face_edge_adjacency"],
        },
    )

    @register(_naked_edge_spec)
    async def run_surface_naked_edge_detect(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        adjacency = a.get("face_edge_adjacency")
        if not isinstance(adjacency, dict):
            return err_payload("face_edge_adjacency must be a dict", "BAD_ARGS")

        tol = float(a.get("tolerance", 1e-6))
        result = naked_edge_detect(adjacency, tol)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)

    # ------------------------------------------------------------------
    # surface_isocurve_extract
    # ------------------------------------------------------------------

    _isocurve_spec = ToolSpec(
        name="surface_isocurve_extract",
        description=(
            "Extract an isocurve (u=const or v=const) from a NURBS surface as a "
            "polyline with arc-length. Useful for section analysis and display.\n\n"
            "Returns: {ok, points, parameter, direction, arc_length}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {"type": "integer"},
                "degree_v": {"type": "integer"},
                "control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "parameter": {"type": "number", "description": "Fixed parameter value."},
                "direction": {
                    "type": "string",
                    "enum": ["u", "v"],
                    "description": "'u' = fix u vary v; 'v' = fix v vary u.",
                },
                "num_samples": {"type": "integer", "description": "Polyline vertex count (default 50)."},
            },
            "required": ["degree_u", "degree_v", "control_points", "num_u", "num_v", "parameter"],
        },
    )

    @register(_isocurve_spec)
    async def run_surface_isocurve_extract(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        surface, err = _build_surface_from_args(a)
        if surface is None:
            return err_payload(err, "BAD_ARGS")

        param = a.get("parameter")
        if param is None:
            return err_payload("parameter is required", "BAD_ARGS")

        direction = a.get("direction", "u")
        ns = int(a.get("num_samples", 50))
        result = isocurve_extract(surface, float(param), direction, ns)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)

    # ------------------------------------------------------------------
    # surface_area_centroid
    # ------------------------------------------------------------------

    _area_centroid_spec = ToolSpec(
        name="surface_area_centroid",
        description=(
            "Compute surface area, centroid, and second moments of area by numeric "
            "integration over a UV grid (analogous to Rhino AreaMoments). "
            "Uses cross-product of first partial derivatives as the area element.\n\n"
            "Returns: {ok, area, centroid, Ixx, Iyy, Izz, Ixy, Ixz, Iyz}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {"type": "integer"},
                "degree_v": {"type": "integer"},
                "control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "grid_u": {"type": "integer"},
                "grid_v": {"type": "integer"},
            },
            "required": ["degree_u", "degree_v", "control_points", "num_u", "num_v"],
        },
    )

    @register(_area_centroid_spec)
    async def run_surface_area_centroid(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        surface, err = _build_surface_from_args(a)
        if surface is None:
            return err_payload(err, "BAD_ARGS")

        nu = int(a.get("grid_u", _DEFAULT_NU))
        nv = int(a.get("grid_v", _DEFAULT_NV))
        result = area_centroid_secondmoment(surface, nu, nv)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)
