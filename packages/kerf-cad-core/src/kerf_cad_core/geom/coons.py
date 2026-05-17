"""
coons.py
========
Bilinearly-blended Coons patch, edge surface, and bilinear patch primitives.

All functions return a NurbsSurface (from kerf_cad_core.geom.nurbs).

Theory
------
The classical bilinearly-blended Coons patch (Steven A. Coons, 1967) fills a
four-boundary-curve patch by:

    S(u,v) = (1-v)*c0_u(u) + v*c1_u(u)
           + (1-u)*c0_v(v) + u*c1_v(v)
           - bilinear corner interpolant

where the bilinear corner interpolant removes the double-counting of the
corners:

    B(u,v) = (1-u)(1-v)*P00 + u*(1-v)*P10 + (1-u)*v*P01 + u*v*P11

The four curves must satisfy boundary-correspondence: c0_u(0) == c0_v(0),
c0_u(1) == c1_v(0), c1_u(0) == c0_v(1), c1_u(1) == c1_v(1).

Implementation strategy
-----------------------
We evaluate the Coons formula on a dense (nu x nv) grid of parameter pairs and
fit an interpolating degree-(1,1) NurbsSurface through those grid points
(exact, no approximation error).  The grid size is controlled by the
``grid_n`` parameter (default 16) giving (grid_n x grid_n) control points.
For the *linear* Coons patch constructed from four straight-line boundary
segments the formula collapses to a bilinear surface which is represented
exactly by a degree-(1,1) patch; for curved boundaries a higher-degree
representation is used (degree-3 in each direction, lofted through the grid).

Public API
----------
coons_patch(c0_u, c1_u, c0_v, c1_v, *, tol, grid_n) -> NurbsSurface
edge_surface(c0_u, c1_u, *, grid_n) -> NurbsSurface
bilinear_patch(p00, p10, p01, p11) -> NurbsSurface
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    make_line_nurbs,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(u: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, u))


def _eval_curve(curve: NurbsCurve, t: float) -> np.ndarray:
    """Evaluate *curve* at parameter *t* clamped to its domain."""
    u0 = float(curve.knots[curve.degree])
    u1 = float(curve.knots[-curve.degree - 1])
    return curve.evaluate(_clamp(t * (u1 - u0) + u0, u0, u1))


def _corner(curve: NurbsCurve, end: int) -> np.ndarray:
    """Return the start (end=0) or end (end=1) point of *curve*."""
    return _eval_curve(curve, float(end))


def _make_clamped_knots(n: int, degree: int) -> np.ndarray:
    """Clamped uniform knot vector for *n* control points of given *degree*."""
    m = n + degree + 1
    knots = np.zeros(m)
    knots[:degree + 1] = 0.0
    knots[-(degree + 1):] = 1.0
    n_inner = m - 2 * (degree + 1)
    if n_inner > 0:
        inner = np.linspace(0.0, 1.0, n_inner + 2)[1:-1]
        knots[degree + 1:degree + 1 + n_inner] = inner
    return knots


def _interpolating_surface(pts: np.ndarray, degree_u: int, degree_v: int) -> NurbsSurface:
    """Build an interpolating NurbsSurface through an (nu x nv x 3) point grid.

    Uses global B-spline interpolation (Piegl & Tiller §9.2) in each
    parametric direction with chord-length parameterisation.

    For the special case degree=1 in both directions (bilinear grid) the
    control points ARE the grid points — no system solve needed.
    """
    nu, nv, dim = pts.shape

    if degree_u == 1 and degree_v == 1:
        knots_u = _make_clamped_knots(nu, 1)
        knots_v = _make_clamped_knots(nv, 1)
        return NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=pts.copy(),
            knots_u=knots_u, knots_v=knots_v,
        )

    # Chord-length parameter values in u direction (average across v columns).
    params_u = _chord_params(pts, axis=0)   # (nu,)
    params_v = _chord_params(pts, axis=1)   # (nv,)

    knots_u = _params_to_knots(params_u, degree_u)
    knots_v = _params_to_knots(params_v, degree_v)

    # Solve for control points: first in the v direction for each u row,
    # then in the u direction for each resulting v column.
    cp_tmp = np.zeros((nu, nv, dim))
    for i in range(nu):
        cp_tmp[i] = _bspline_interpolate_row(pts[i], params_v, knots_v, degree_v)

    cp_final = np.zeros((nu, nv, dim))
    for j in range(nv):
        cp_final[:, j, :] = _bspline_interpolate_row(cp_tmp[:, j, :], params_u, knots_u, degree_u)

    return NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=cp_final,
        knots_u=knots_u, knots_v=knots_v,
    )


def _chord_params(pts: np.ndarray, axis: int) -> np.ndarray:
    """Chord-length parameters along the given axis (0=u, 1=v)."""
    if axis == 0:
        # Average chord lengths across v columns.
        n = pts.shape[0]
        if n == 1:
            return np.array([0.0])
        total = np.zeros(n)
        nv = pts.shape[1]
        for j in range(nv):
            col = pts[:, j, :]
            dists = np.linalg.norm(np.diff(col, axis=0), axis=1)
            cumul = np.concatenate([[0.0], np.cumsum(dists)])
            L = cumul[-1]
            if L > 1e-14:
                total += cumul / L
            else:
                total += np.linspace(0.0, 1.0, n)
        return total / nv
    else:
        # Average chord lengths across u rows.
        n = pts.shape[1]
        if n == 1:
            return np.array([0.0])
        total = np.zeros(n)
        nu = pts.shape[0]
        for i in range(nu):
            row = pts[i, :, :]
            dists = np.linalg.norm(np.diff(row, axis=0), axis=1)
            cumul = np.concatenate([[0.0], np.cumsum(dists)])
            L = cumul[-1]
            if L > 1e-14:
                total += cumul / L
            else:
                total += np.linspace(0.0, 1.0, n)
        return total / nu


def _params_to_knots(params: np.ndarray, degree: int) -> np.ndarray:
    """Piegl & Tiller Eq. 9.8 — averaging knot vector from parameter values."""
    n = len(params)
    m = n + degree + 1
    knots = np.zeros(m)
    knots[:degree + 1] = 0.0
    knots[-(degree + 1):] = 1.0
    for j in range(1, n - degree):
        knots[j + degree] = np.sum(params[j:j + degree]) / degree
    return knots


def _bspline_interpolate_row(pts: np.ndarray, params: np.ndarray,
                              knots: np.ndarray, degree: int) -> np.ndarray:
    """Interpolate 1D polyline *pts* at *params* using B-spline of *degree*.

    Solves the linear system N * P = Q where N is the collocation matrix of
    basis functions at the given parameter values.
    """
    n = len(pts)
    dim = pts.shape[1]
    N_mat = _collocation_matrix(params, knots, degree, n)
    cp = np.zeros((n, dim))
    for d in range(dim):
        cp[:, d] = np.linalg.solve(N_mat, pts[:, d])
    return cp


def _collocation_matrix(params: np.ndarray, knots: np.ndarray,
                         degree: int, n: int) -> np.ndarray:
    """Build the (n x n) B-spline collocation matrix N[i,j] = N_{j,p}(params[i])."""
    from kerf_cad_core.geom.nurbs import _basis_funcs, find_span
    N_mat = np.zeros((n, n))
    for i, u in enumerate(params):
        span = find_span(n - 1, degree, float(u), knots)
        basis = _basis_funcs(span, float(u), degree, knots)
        for j, b in enumerate(basis):
            N_mat[i, span - degree + j] = b
    return N_mat


# ---------------------------------------------------------------------------
# Corner agreement check
# ---------------------------------------------------------------------------

def _check_corners(c0_u: NurbsCurve, c1_u: NurbsCurve,
                   c0_v: NurbsCurve, c1_v: NurbsCurve,
                   tol: float) -> Optional[str]:
    """Return an error string if any pair of coincident corners disagrees by > tol."""
    # Corner layout:
    #   c0_u(0) == c0_v(0)  → P00
    #   c0_u(1) == c1_v(0)  → P10
    #   c1_u(0) == c0_v(1)  → P01
    #   c1_u(1) == c1_v(1)  → P11
    pairs = [
        ("c0_u(0)", _corner(c0_u, 0), "c0_v(0)", _corner(c0_v, 0)),
        ("c0_u(1)", _corner(c0_u, 1), "c1_v(0)", _corner(c1_v, 0)),
        ("c1_u(0)", _corner(c1_u, 0), "c0_v(1)", _corner(c0_v, 1)),
        ("c1_u(1)", _corner(c1_u, 1), "c1_v(1)", _corner(c1_v, 1)),
    ]
    for label_a, pa, label_b, pb in pairs:
        d = np.linalg.norm(np.asarray(pa, dtype=float)[:3] - np.asarray(pb, dtype=float)[:3])
        if d > tol:
            return (
                f"Corner mismatch: {label_a}={pa[:3]} vs {label_b}={pb[:3]} "
                f"distance={d:.6g} > tol={tol:.6g}"
            )
    return None


# ---------------------------------------------------------------------------
# Coons patch — bilinearly-blended formula
# ---------------------------------------------------------------------------

def coons_patch(
    c0_u: NurbsCurve,
    c1_u: NurbsCurve,
    c0_v: NurbsCurve,
    c1_v: NurbsCurve,
    *,
    tol: float = 1e-6,
    grid_n: int = 16,
) -> NurbsSurface:
    """Bilinearly-blended Coons patch filling the four-boundary-curve loop.

    Parameters
    ----------
    c0_u : boundary curve at v=0, evaluated over u in [0,1]
    c1_u : boundary curve at v=1, evaluated over u in [0,1]
    c0_v : boundary curve at u=0, evaluated over v in [0,1]
    c1_v : boundary curve at u=1, evaluated over v in [0,1]
    tol  : corner-agreement tolerance (default 1e-6)
    grid_n : number of evaluation points per direction (default 16)

    Returns
    -------
    NurbsSurface — degree (3,3) interpolating surface through the Coons grid.
        For straight-line boundaries a degree (1,1) exact patch is returned.

    Raises
    ------
    ValueError : if any of the four corner pairs disagree by more than *tol*.
    """
    err = _check_corners(c0_u, c1_u, c0_v, c1_v, tol)
    if err is not None:
        raise ValueError(f"coons_patch: {err}")

    # Four corners from c0_u endpoints (authoritative).
    P00 = np.asarray(_corner(c0_u, 0), dtype=float)
    P10 = np.asarray(_corner(c0_u, 1), dtype=float)
    P01 = np.asarray(_corner(c1_u, 0), dtype=float)
    P11 = np.asarray(_corner(c1_u, 1), dtype=float)

    # Ensure 3D.
    def _to3(p: np.ndarray) -> np.ndarray:
        p = p.ravel()
        if p.shape[0] < 3:
            p = np.concatenate([p, np.zeros(3 - p.shape[0])])
        return p[:3]

    P00 = _to3(P00)
    P10 = _to3(P10)
    P01 = _to3(P01)
    P11 = _to3(P11)

    # Determine whether all 4 boundary curves are linear (degree 1 and 2
    # control points = straight lines).  If so, use an exact (1,1) patch.
    def _is_linear(c: NurbsCurve) -> bool:
        return c.degree == 1 and c.num_control_points == 2

    all_linear = all(_is_linear(c) for c in (c0_u, c1_u, c0_v, c1_v))
    if all_linear:
        return bilinear_patch(P00, P10, P01, P11)

    # General case: evaluate Coons formula on grid_n x grid_n parameter grid.
    us = np.linspace(0.0, 1.0, grid_n)
    vs = np.linspace(0.0, 1.0, grid_n)

    grid = np.zeros((grid_n, grid_n, 3))
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            # Two ruled surfaces (lofts between opposite boundaries):
            ru = (1.0 - v) * _to3(_eval_curve(c0_u, u)) + v * _to3(_eval_curve(c1_u, u))
            rv = (1.0 - u) * _to3(_eval_curve(c0_v, v)) + u * _to3(_eval_curve(c1_v, v))
            # Bilinear corner correction:
            bl = ((1.0 - u) * (1.0 - v) * P00
                  + u * (1.0 - v) * P10
                  + (1.0 - u) * v * P01
                  + u * v * P11)
            grid[i, j] = ru + rv - bl

    # Choose degree — use cubic when we have enough grid points.
    deg = min(3, grid_n - 1)
    return _interpolating_surface(grid, deg, deg)


# ---------------------------------------------------------------------------
# Edge surface — exact ruled surface between two profile curves
# ---------------------------------------------------------------------------

def _make_compatible(c0: NurbsCurve, c1: NurbsCurve):
    """Return two curves with the same degree and knot vector.

    Degree is elevated to the maximum of the two, then knots are unified
    by inserting the knots of each curve into the other until both share
    the same knot vector.
    """
    from kerf_cad_core.geom.nurbs import knot_insertion

    # Step 1 — equalise degree by elevation of the lower-degree curve.
    target_degree = max(c0.degree, c1.degree)
    c0, c1 = _degree_elevate_to(c0, target_degree), _degree_elevate_to(c1, target_degree)

    # Step 2 — unify knot vectors: for each knot in c1 that is missing from c0,
    # insert it into c0 (and vice versa), respecting multiplicities.
    c0 = _match_knots(c0, c1)
    c1 = _match_knots(c1, c0)

    return c0, c1


def _degree_elevate_to(curve: NurbsCurve, target: int) -> NurbsCurve:
    """Elevate *curve* degree to *target* via repeated single-step elevation.

    Uses a simple Bezier-based degree elevation for uniform clamped curves.
    For the purposes of ruled surfaces we only need degree elevation from
    1 → 2 (lines to match quadratic arcs) or 2 → 3, so the simple approach
    is sufficient.
    """
    if curve.degree >= target:
        return curve
    from kerf_cad_core.geom.nurbs import degree_elevation
    return degree_elevation(curve, target)


def _match_knots(c: NurbsCurve, ref: NurbsCurve) -> NurbsCurve:
    """Insert into *c* any interior knots present in *ref* but missing from *c*.

    Only interior knots (strictly between the first and last knot value) are
    inserted; end-multiplicity clamping is already guaranteed by construction.
    """
    from kerf_cad_core.geom.nurbs import knot_insertion

    p = c.degree
    u0, u1 = c.knots[p], c.knots[-p - 1]

    # Collect distinct interior knots of ref with their multiplicities.
    ref_interior = {}
    rp = ref.degree
    for k in ref.knots[rp:-rp - 1]:
        if u0 < k < u1:
            ref_interior[float(k)] = ref_interior.get(float(k), 0) + 1

    # Count existing multiplicities in c.
    c_mult = {}
    for k in c.knots:
        fk = float(k)
        if u0 < fk < u1:
            c_mult[fk] = c_mult.get(fk, 0) + 1

    # Insert missing repetitions.
    result = c
    for k, mult in sorted(ref_interior.items()):
        have = c_mult.get(k, 0)
        need = mult - have
        for _ in range(need):
            result = knot_insertion(result, k)

    return result


def edge_surface(
    c0_u: NurbsCurve,
    c1_u: NurbsCurve,
    *,
    grid_n: int = 16,
) -> NurbsSurface:
    """Exact ruled surface (loft) between two curves — the Coons edge-surface.

    The surface is defined by:

        S(u, v) = (1 - v) * c0_u(u) + v * c1_u(u)

    This is represented *exactly* as a NURBS tensor product by making the two
    boundary curves compatible (same degree and knot vector) and stacking their
    control nets:  the v=0 row is c0_u's control net and the v=1 row is
    c1_u's control net.  The v-direction degree is 1 (linear blend), giving
    degree (p, 1) where p is the (elevated) u-degree.

    The ``grid_n`` parameter is accepted for API compatibility but not used
    in the exact construction.

    Parameters
    ----------
    c0_u : start profile curve  (v=0)
    c1_u : end profile curve    (v=1)
    grid_n : unused (retained for API compatibility)

    Returns
    -------
    NurbsSurface — degree-(p,1) exact ruled surface.
    """
    c0, c1 = _make_compatible(c0_u, c1_u)

    P0 = c0.control_points   # (n, dim)
    P1 = c1.control_points   # (n, dim)
    n, dim = P0.shape

    # Promote to 3D if needed.
    if dim < 3:
        pad = np.zeros((n, 3 - dim))
        P0 = np.hstack([P0, pad])
        P1 = np.hstack([P1, pad])
        dim = 3

    # Control net: shape (n, 2, 3); i=0 → c0, i=1 → c1 (v direction).
    cps = np.stack([P0, P1], axis=1)   # (n, 2, 3)

    knots_u = c0.knots.copy()
    knots_v = np.array([0.0, 0.0, 1.0, 1.0])

    # Handle rational curves: weights for the ruled surface are the same as
    # the original curve weights (linear blend of homogeneous coords).
    weights = None
    if c0.weights is not None or c1.weights is not None:
        w0 = c0.weights if c0.weights is not None else np.ones(n)
        w1 = c1.weights if c1.weights is not None else np.ones(n)
        weights = np.stack([w0, w1], axis=1)   # (n, 2)

    return NurbsSurface(
        degree_u=c0.degree,
        degree_v=1,
        control_points=cps,
        knots_u=knots_u,
        knots_v=knots_v,
        weights=weights,
    )


# ---------------------------------------------------------------------------
# Bilinear patch — 4-corner special case
# ---------------------------------------------------------------------------

def bilinear_patch(
    p00: np.ndarray,
    p10: np.ndarray,
    p01: np.ndarray,
    p11: np.ndarray,
) -> NurbsSurface:
    """Bilinear Coons patch interpolating the four corner points.

    The resulting degree-(1,1) NurbsSurface satisfies:
        S(0,0) = p00,  S(1,0) = p10,  S(0,1) = p01,  S(1,1) = p11.

    Parameters
    ----------
    p00 : corner at (u=0, v=0)
    p10 : corner at (u=1, v=0)
    p01 : corner at (u=0, v=1)
    p11 : corner at (u=1, v=1)

    Returns
    -------
    NurbsSurface — degree (1,1), 2x2 control net.
    """
    def _to3(p) -> np.ndarray:
        p = np.asarray(p, dtype=float).ravel()
        if p.shape[0] < 3:
            p = np.concatenate([p, np.zeros(3 - p.shape[0])])
        return p[:3]

    P00 = _to3(p00)
    P10 = _to3(p10)
    P01 = _to3(p01)
    P11 = _to3(p11)

    # Control point layout: cps[i, j] where i indexes u, j indexes v.
    # For a (1,1) patch, cps[0,0]=P00, cps[1,0]=P10, cps[0,1]=P01, cps[1,1]=P11.
    cps = np.array([[P00, P01], [P10, P11]])  # shape (2, 2, 3)

    knots_u = np.array([0.0, 0.0, 1.0, 1.0])
    knots_v = np.array([0.0, 0.0, 1.0, 1.0])

    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cps,
        knots_u=knots_u, knots_v=knots_v,
    )
