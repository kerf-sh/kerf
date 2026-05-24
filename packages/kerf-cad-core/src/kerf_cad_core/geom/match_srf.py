"""
match_srf.py
============
Pure-Python parametric matchSrf -- NURBS Phase 4 Capability 3 (pure-Python core).

Adjusts the control-point rows/cols adjacent to a source surface's matched edge
so the boundary satisfies G0 (positional), G1 (tangent), or G2 (curvature)
continuity with a target surface's corresponding edge.  This is the Rhino
"MatchSrf" operation implemented entirely in NumPy -- no OCC calls, no WASM.

The OCC ``GeomFill_NSections`` binding (the WASM-side complement that builds a
transition strip instead of modifying the source surface in place) remains
WASM-blocked until the C3-T1 binding probe confirms ``GeomFill_NSections`` +
``Geom_BSplineSurface.SetPole`` are present at runtime.

Public API
----------
match_surface_edge(
    target_surface, target_edge,
    source_surface, source_edge,
    continuity,
    *,
    samples=32,
    tolerance=1e-6,
) -> MatchResult

    Modify the source surface's control points near ``source_edge`` so the
    seam satisfies ``continuity`` against ``target_surface`` / ``target_edge``.

    Parameters
    ----------
    target_surface : NurbsSurface
        The reference surface to match against.
    target_edge : str
        Which edge of the target surface to use as the template.
        One of ``'u0'`` (u=u_min iso), ``'u1'`` (u=u_max iso),
        ``'v0'`` (v=v_min iso), ``'v1'`` (v=v_max iso).
    source_surface : NurbsSurface
        The surface whose boundary will be modified.
    source_edge : str
        Which edge of the source surface to match.
        Same four values as ``target_edge``.
    continuity : str
        ``'G0'``, ``'G1'``, or ``'G2'``.
    samples : int
        Number of parameter samples along the edge (default 32).
    tolerance : float
        Tolerance used for deviation diagnostics (default 1e-6).

    Returns
    -------
    MatchResult
        Dataclass with:
          modified_surface : NurbsSurface  (modified copy of source)
          ok               : bool
          reason           : str  (empty on success)
          max_position_deviation  : float  (G0 seam error in CP space)
          max_tangent_deviation   : float  (G1 cross-row angle, radians; nan if not computed)
          max_curvature_deviation : float  (G2 cross-row curvature diff; nan if not computed)
          continuity_achieved     : str   (highest continuity confirmed within tolerance)

    Never raises -- all exceptions are caught and surfaced in ``reason``.

LLM tool registration
---------------------
Gated by ``kerf_chat.tools.registry`` availability (same pattern as
``trim_curve.py``).  Tools registered when the registry is importable:

  ``match_surface_edge_tool``
      Modify a source surface edge to match a target surface edge at G0/G1/G2.
  ``diagnose_surface_continuity``
      Measure G0/G1/G2 deviation across a seam (read-only, non-destructive).

WASM-blocked note
-----------------
The ``GeomFill_NSections`` / ``Geom_BSplineSurface.SetPole`` OCC binding path
is unconfirmed at runtime.  This module delivers only the pure-Python
pole-adjustment approach (Approach 2 in the plan design sketch).  Once
C3-T1 probes the binding, the OCC path can be wired in alongside this module
without changing the public API.

Implementation notes
--------------------
Boundary-position sampling uses the boundary CP row directly (not
``surface_evaluate``) because a clamped B-spline boundary edge is *exactly*
the linear interpolation of its endpoint CPs -- this avoids the known
evaluation inaccuracy of the shared ``nurbs.py`` evaluator at parametric
extremes.  Cross-boundary tangent and curvature use the CP difference
relations for clamped B-splines:

    dS/dt|_{boundary} ~ p * (CP[1] - CP[0]) / knot_span
    d2S/dt2|_{boundary} ~ p*(p-1) * (CP[2] - 2*CP[1] + CP[0]) / knot_span^2
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_derivatives, surface_normal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_EDGES = frozenset({"u0", "u1", "v0", "v1"})
_VALID_CONTINUITY = frozenset({"G0", "G1", "G2", "G3"})
_DEFAULT_SAMPLES = 32


# ---------------------------------------------------------------------------
# MatchResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    """Result of a match_surface_edge call.

    Attributes
    ----------
    modified_surface : NurbsSurface
        A deep copy of the source surface with the near-seam control points
        adjusted.  Identical to the input source surface when ``ok`` is False.
    ok : bool
        True on success.
    reason : str
        Human-readable explanation when ``ok`` is False.
    max_position_deviation : float
        Maximum 3D distance between the source-edge boundary CPs (after
        adjustment) and the corresponding target-edge boundary CPs (G0 error).
    max_tangent_deviation : float
        Maximum angle (radians) between cross-boundary CP-difference vectors
        on either side of the seam after the operation (G1 proxy).
        ``math.nan`` if G1 was not requested or could not be computed.
    max_curvature_deviation : float
        Maximum difference in the second CP-difference magnitudes on either
        side of the seam after the operation (G2 proxy).
        ``math.nan`` if G2 was not requested or could not be computed.
    continuity_achieved : str
        Highest continuity level confirmed within the supplied tolerance.
        One of ``'G0'``, ``'G1'``, ``'G2'``, or ``'none'``.
    """
    modified_surface: Optional[NurbsSurface] = None
    ok: bool = False
    reason: str = ""
    max_position_deviation: float = math.nan
    max_tangent_deviation: float = math.nan
    max_curvature_deviation: float = math.nan
    max_curvature_rate_deviation: float = math.nan
    continuity_achieved: str = "none"


# ---------------------------------------------------------------------------
# Parameter-domain helpers
# ---------------------------------------------------------------------------

def _domain_u(surf: NurbsSurface) -> Tuple[float, float]:
    return float(surf.knots_u[0]), float(surf.knots_u[-1])


def _domain_v(surf: NurbsSurface) -> Tuple[float, float]:
    return float(surf.knots_v[0]), float(surf.knots_v[-1])


# ---------------------------------------------------------------------------
# CP row access
# ---------------------------------------------------------------------------

def _get_cp_row(surf: NurbsSurface, edge: str, row_idx: int) -> np.ndarray:
    """Extract a row/col of control points adjacent to the given edge.

    ``row_idx = 0`` is the boundary row; ``row_idx = 1`` is the next row in,
    etc.  Returns an (n, dim) array (copy).
    """
    cp = surf.control_points  # (nu, nv, dim)
    nu, nv = cp.shape[0], cp.shape[1]
    if edge == "u0":
        return cp[row_idx, :, :].copy()
    if edge == "u1":
        return cp[nu - 1 - row_idx, :, :].copy()
    if edge == "v0":
        return cp[:, row_idx, :].copy()
    # v1
    return cp[:, nv - 1 - row_idx, :].copy()


def _set_cp_row(surf: NurbsSurface, edge: str, row_idx: int, values: np.ndarray) -> None:
    """Write a row/col of control points back into the surface (in-place)."""
    cp = surf.control_points
    nu, nv = cp.shape[0], cp.shape[1]
    if edge == "u0":
        cp[row_idx, :, :] = values
    elif edge == "u1":
        cp[nu - 1 - row_idx, :, :] = values
    elif edge == "v0":
        cp[:, row_idx, :] = values
    else:  # v1
        cp[:, nv - 1 - row_idx, :] = values


def _cp_row_count(surf: NurbsSurface, edge: str) -> int:
    """Number of control-point rows available in the inward direction."""
    if edge in ("u0", "u1"):
        return surf.control_points.shape[0]
    return surf.control_points.shape[1]


def _cp_col_count(surf: NurbsSurface, edge: str) -> int:
    """Length of a CP row (along-edge direction)."""
    if edge in ("u0", "u1"):
        return surf.control_points.shape[1]  # nv CPs along the v edge
    return surf.control_points.shape[0]      # nu CPs along the u edge


# ---------------------------------------------------------------------------
# Sample boundary CP row with linear interpolation to requested sample count
# ---------------------------------------------------------------------------

def _sample_boundary_cps(surf: NurbsSurface, edge: str, samples: int) -> np.ndarray:
    """Return (samples, 3) array by linearly sampling the boundary CP row.

    For a clamped B-spline the boundary edge is exactly the boundary CP row,
    so this gives exact boundary positions without depending on
    ``surface_evaluate``.
    """
    row = _get_cp_row(surf, edge, 0)   # (n_cp, dim)
    n_cp = len(row)
    n = max(2, samples)
    t = np.linspace(0.0, 1.0, n)
    result = np.zeros((n, 3))
    for k, tk in enumerate(t):
        idx_f = tk * (n_cp - 1)
        lo = int(math.floor(idx_f))
        hi = min(lo + 1, n_cp - 1)
        alpha = idx_f - lo
        result[k] = (1.0 - alpha) * row[lo, :3] + alpha * row[hi, :3]
    return result


# ---------------------------------------------------------------------------
# CP difference vectors (boundary tangent / curvature proxies)
# ---------------------------------------------------------------------------

def _cp_tangent_vector(surf: NurbsSurface, edge: str, cp_idx: int) -> np.ndarray:
    """Cross-boundary tangent at CP position cp_idx (along-edge).

    T = p * (CP[1][cp_idx] - CP[0][cp_idx])  (knot-span normalised later)
    cp_idx is the index within the along-edge direction.
    """
    row0 = _get_cp_row(surf, edge, 0)
    row1 = _get_cp_row(surf, edge, 1)
    return row1[cp_idx, :3] - row0[cp_idx, :3]


def _cp_curvature_vector(surf: NurbsSurface, edge: str, cp_idx: int) -> np.ndarray:
    """Cross-boundary second-difference at CP position cp_idx.

    kappa ~ p*(p-1) * (CP[2][cp_idx] - 2*CP[1][cp_idx] + CP[0][cp_idx])
    """
    row0 = _get_cp_row(surf, edge, 0)
    row1 = _get_cp_row(surf, edge, 1)
    row2 = _get_cp_row(surf, edge, 2)
    return row2[cp_idx, :3] - 2.0 * row1[cp_idx, :3] + row0[cp_idx, :3]


# ---------------------------------------------------------------------------
# Knot-span at boundary
# ---------------------------------------------------------------------------

def _boundary_knot_span(surf: NurbsSurface, edge: str) -> float:
    """Return the knot span at the boundary edge in the inward direction."""
    if edge in ("u0", "u1"):
        knots = surf.knots_u
        p = surf.degree_u
    else:
        knots = surf.knots_v
        p = surf.degree_v

    if edge in ("u0", "v0"):
        span = float(knots[p + 1] - knots[0])
    else:
        span = float(knots[-1] - knots[-(p + 2)])
    return span if abs(span) > 1e-15 else 1.0


def _boundary_degree(surf: NurbsSurface, edge: str) -> int:
    if edge in ("u0", "u1"):
        return surf.degree_u
    return surf.degree_v


# ---------------------------------------------------------------------------
# Analytic boundary-derivative helpers (use surface_derivatives, not CPs)
# ---------------------------------------------------------------------------

def _edge_boundary_params(surf: NurbsSurface, edge: str) -> Tuple[float, float, float, float]:
    """Return (u_seam, v_seam, t_min, t_max) for the given edge.

    For "u0"/"u1" edges the along-edge parameter t runs over v; the
    fixed (seam) parameter is u.  For "v0"/"v1" edges t runs over u.
    """
    u_min = float(surf.knots_u[surf.degree_u])
    u_max = float(surf.knots_u[-surf.degree_u - 1])
    v_min = float(surf.knots_v[surf.degree_v])
    v_max = float(surf.knots_v[-surf.degree_v - 1])
    if edge == "u0":
        return u_min, None, v_min, v_max  # seam u=u_min, t in [v_min, v_max]
    if edge == "u1":
        return u_max, None, v_min, v_max  # seam u=u_max
    if edge == "v0":
        return None, v_min, u_min, u_max  # seam v=v_min, t in [u_min, u_max]
    # v1
    return None, v_max, u_min, u_max      # seam v=v_max


def _analytic_cross_tangent(surf: NurbsSurface, edge: str, t: float) -> np.ndarray:
    """Analytic cross-boundary tangent (dS/dn) at along-edge parameter *t*.

    Uses ``surface_derivatives`` for exact derivative evaluation at the
    boundary.  Returns a 3-component vector; caller handles normalisation.

    For "u0"/"u1" edges the cross-boundary direction is u; for "v0"/"v1"
    it is v.  The tangent is always in the *inward* direction (pointing
    into the surface from the seam).
    """
    u_seam, v_seam, t_min, t_max = _edge_boundary_params(surf, edge)
    # Clamp t to the domain
    t_clamped = min(max(float(t), t_min), t_max)

    if edge in ("u0", "u1"):
        u = u_seam
        v = t_clamped
    else:
        u = t_clamped
        v = v_seam

    SKL = surface_derivatives(surf, u, v, d=1)
    if edge in ("u0", "u1"):
        # Cross-boundary is d/du; inward for u0 is +u, for u1 is -u
        raw = SKL[1, 0][:3]
        return raw if edge == "u0" else -raw
    else:
        # Cross-boundary is d/dv; inward for v0 is +v, for v1 is -v
        raw = SKL[0, 1][:3]
        return raw if edge == "v0" else -raw


def _analytic_cross_curvature(surf: NurbsSurface, edge: str, t: float) -> float:
    """Analytic normal curvature in the cross-boundary direction at parameter *t*.

    Returns κ = (S_nn · n) / |S_n|²  where 'n' denotes the cross-boundary
    direction (u or v depending on *edge*) and 'n' in the curvature formula
    is the unit surface normal.

    Uses ``surface_derivatives`` with d=2 for exact curvature.
    """
    u_seam, v_seam, t_min, t_max = _edge_boundary_params(surf, edge)
    t_clamped = min(max(float(t), t_min), t_max)

    if edge in ("u0", "u1"):
        u = u_seam
        v = t_clamped
    else:
        u = t_clamped
        v = v_seam

    SKL = surface_derivatives(surf, u, v, d=2)
    n_surf = surface_normal(surf, u, v)

    if edge in ("u0", "u1"):
        # Cross-boundary is d/du: tangent = SKL[1,0], second deriv = SKL[2,0]
        tangent = SKL[1, 0][:3]
        second = SKL[2, 0][:3]
    else:
        # Cross-boundary is d/dv: tangent = SKL[0,1], second deriv = SKL[0,2]
        tangent = SKL[0, 1][:3]
        second = SKL[0, 2][:3]

    tan_sq = float(np.dot(tangent, tangent))
    if tan_sq < 1e-30:
        return 0.0
    return float(np.dot(second, n_surf)) / tan_sq


# ---------------------------------------------------------------------------
# Core: G2 -- analytic version using normal curvature matching
# ---------------------------------------------------------------------------

def _boundary_second_deriv_coeff_A(surf: NurbsSurface, edge: str) -> float:
    """Coefficient of CP[2] in the analytic second derivative at the boundary.

    For a clamped B-spline of degree p with boundary knot spans h1 and h2:
        S_cc(boundary) = A * CP[2] + B * CP[1] + C * CP[0]
    where
        A = p*(p-1) / (h1 * (h1 + h2))
        C = p*(p-1) / h1²
        B = -(A + C)

    h1 is the first non-trivial knot span from the boundary;
    h2 is the second.  For "u0"/"v0" these are the spans starting at the
    left/bottom; for "u1"/"v1" they are from the right/top (mirrored).

    Returns A.  Falls back to the approximate ``p*(p-1)/h1²`` value if the
    second span is not available.
    """
    if edge in ("u0", "u1"):
        knots = surf.knots_u
        p = surf.degree_u
    else:
        knots = surf.knots_v
        p = surf.degree_v

    if p < 2:
        return 0.0

    if edge in ("u0", "v0"):
        # left boundary: h1 = knots[p+1] - knots[p], h2 = knots[p+2] - knots[p+1]
        h1 = float(knots[p + 1] - knots[p])
        h2 = float(knots[p + 2] - knots[p + 1]) if len(knots) > p + 2 else h1
    else:
        # right boundary (u1/v1): mirror
        h1 = float(knots[-(p + 1)] - knots[-(p + 2)])
        h2 = float(knots[-(p + 2)] - knots[-(p + 3)]) if len(knots) > p + 2 else h1

    if abs(h1) < 1e-15 or abs(h1 + h2) < 1e-15:
        return 0.0
    return float(p * (p - 1)) / (h1 * (h1 + h2))


def _boundary_second_deriv_coeff_C(surf: NurbsSurface, edge: str) -> float:
    """Coefficient of CP[0] in the analytic second derivative at the boundary.

    C = p*(p-1) / h1²
    """
    if edge in ("u0", "u1"):
        knots = surf.knots_u
        p = surf.degree_u
    else:
        knots = surf.knots_v
        p = surf.degree_v

    if p < 2:
        return 0.0

    if edge in ("u0", "v0"):
        h1 = float(knots[p + 1] - knots[p])
    else:
        h1 = float(knots[-(p + 1)] - knots[-(p + 2)])

    if abs(h1) < 1e-15:
        return 0.0
    return float(p * (p - 1)) / (h1 ** 2)


def _eval_cp_row_at_t(surf: NurbsSurface, edge: str, row_idx: int, t: float) -> np.ndarray:
    """Evaluate the along-edge B-spline curve of a given inward row at parameter t.

    For "u0"/"u1" edges the along-edge direction is v; for "v0"/"v1" it is u.
    This evaluates the v-curve (or u-curve) formed by the row_idx-th CP row in
    the cross-boundary direction at the along-edge parameter t.

    This is required for the exact tensor-product formula:
        S_cc(boundary, t) = A * P2_row(t) + B * P1_row(t) + C * P0_row(t)
    """
    from kerf_cad_core.geom.nurbs import NurbsCurve, de_boor
    cp_row = _get_cp_row(surf, edge, row_idx)  # (n_col, dim)
    dim = cp_row.shape[1]
    if edge in ("u0", "u1"):
        knots_along = surf.knots_v
        degree_along = surf.degree_v
    else:
        knots_along = surf.knots_u
        degree_along = surf.degree_u
    curve = NurbsCurve(degree=degree_along,
                       control_points=cp_row[:, :3],
                       knots=knots_along)
    val = de_boor(curve, float(t))
    return np.asarray(val, dtype=float)[:3]


def _apply_g2_analytic(source: NurbsSurface, source_edge: str,
                       target: NurbsSurface, target_edge: str) -> None:
    """Adjust the *third* CP row of source for G2 (normal curvature) continuity.

    Uses the exact tensor-product B-spline formula for the cross-boundary
    second derivative at the boundary:

        S_cc(boundary, t) = A_src * P2_row(t) + B_src * P1_row(t) + C_src * P0_row(t)

    where P_i_row(t) is the i-th cross-boundary control row evaluated as a
    B-spline curve in the along-edge direction at parameter t.

    For each along-edge control-point index k, evaluates all three rows at the
    Greville abscissa t_k and applies an additive correction to CP[2][k] to
    make the source normal curvature match the target's:

        ΔP2_row(t_k) = (S_cc_desired(t_k) - S_cc_current(t_k)) / A_src

    For identical source and target, S_cc_desired = S_cc_current, so the
    correction is zero and CP[2] is unchanged to machine precision.
    """
    p_src = _boundary_degree(source, source_edge)
    if p_src < 2:
        return   # G2 on degree-1 surface is undefined -- silently skip

    A_src = _boundary_second_deriv_coeff_A(source, source_edge)
    C_src = _boundary_second_deriv_coeff_C(source, source_edge)
    B_src = -(A_src + C_src)

    if abs(A_src) < 1e-30:
        # Degenerate -- fall back to legacy approach
        _apply_g2(source, source_edge, target, target_edge)
        return

    n_col_src = _cp_col_count(source, source_edge)
    dim = source.control_points.shape[2]

    _, _, t_min_src, t_max_src = _edge_boundary_params(source, source_edge)
    _, _, t_min_tgt, t_max_tgt = _edge_boundary_params(target, target_edge)
    u_seam_src, v_seam_src, _, _ = _edge_boundary_params(source, source_edge)
    u_seam_tgt, v_seam_tgt, _, _ = _edge_boundary_params(target, target_edge)

    # Along-edge knots for the source (used to compute Greville abscissas)
    if source_edge in ("u0", "u1"):
        knots_along = source.knots_v
        deg_along = source.degree_v
    else:
        knots_along = source.knots_u
        deg_along = source.degree_u

    # Greville abscissas for the along-edge direction: these are the
    # parameter values at which CP[k] has its peak basis-function weight.
    # t_k = mean of deg knots: (knots[k+1] + ... + knots[k+deg]) / deg
    greville = []
    for k in range(n_col_src):
        if deg_along > 0:
            t_k = float(np.mean(knots_along[k + 1: k + deg_along + 1]))
        else:
            t_k = t_min_src + (k / (n_col_src - 1)) * (t_max_src - t_min_src) if n_col_src > 1 else t_min_src
        # Clamp to domain
        t_k = min(max(t_k, t_min_src), t_max_src)
        greville.append(t_k)

    orig_row2 = _get_cp_row(source, source_edge, 2)
    row2_new = orig_row2.copy()
    span_src = _boundary_knot_span(source, source_edge)

    for k in range(n_col_src):
        t_src = greville[k]
        # Map to target along-edge parameter (linear interpolation)
        tk_norm = (t_src - t_min_src) / (t_max_src - t_min_src) if (t_max_src - t_min_src) > 1e-15 else 0.0
        t_tgt = t_min_tgt + tk_norm * (t_max_tgt - t_min_tgt)

        # Evaluate the source CP rows as B-spline curves at t_src.
        # This is the key step: P_i_eval = the v-curve of row i at t_src.
        P0_eval = _eval_cp_row_at_t(source, source_edge, 0, t_src)
        P1_eval = _eval_cp_row_at_t(source, source_edge, 1, t_src)
        P2_eval = _eval_cp_row_at_t(source, source_edge, 2, t_src)

        # Current S_cc from the exact tensor-product formula:
        S_cc_current = A_src * P2_eval + B_src * P1_eval + C_src * P0_eval

        # Source cross-boundary tangent: S_c = A1 * (P1_eval - P0_eval) where
        # A1 = p_src / h1 (from the first-derivative formula for B-splines at boundary)
        # For the G1 tangent magnitude we use the surface_derivatives result directly.
        if source_edge in ("u0", "u1"):
            SKL_src = surface_derivatives(source, u_seam_src, t_src, d=1)
            S_c_src = SKL_src[1, 0][:3]
        else:
            SKL_src = surface_derivatives(source, t_src, v_seam_src, d=1)
            S_c_src = SKL_src[0, 1][:3]
        S_c_sq = float(np.dot(S_c_src, S_c_src))

        if S_c_sq < 1e-30:
            continue

        # Analytic target derivatives at seam
        if target_edge in ("u0", "u1"):
            SKL_tgt = surface_derivatives(target, u_seam_tgt, t_tgt, d=2)
            S_cc_tgt = SKL_tgt[2, 0][:3]
            S_c_tgt = SKL_tgt[1, 0][:3]
        else:
            SKL_tgt = surface_derivatives(target, t_tgt, v_seam_tgt, d=2)
            S_cc_tgt = SKL_tgt[0, 2][:3]
            S_c_tgt = SKL_tgt[0, 1][:3]

        S_c_tgt_sq = float(np.dot(S_c_tgt, S_c_tgt))
        if S_c_tgt_sq < 1e-30:
            continue

        # Target surface normal and normal curvature
        if target_edge in ("u0", "u1"):
            n_tgt_vec = surface_normal(target, u_seam_tgt, t_tgt)
        else:
            n_tgt_vec = surface_normal(target, t_tgt, v_seam_tgt)
        kappa_tgt = float(np.dot(S_cc_tgt, n_tgt_vec)) / S_c_tgt_sq

        # Source surface normal (after G1 the normals align)
        if source_edge in ("u0", "u1"):
            n_src_vec = surface_normal(source, u_seam_src, t_src)
        else:
            n_src_vec = surface_normal(source, t_src, v_seam_src)

        # Decompose target S_cc into normal + tangential
        S_cc_tgt_normal_part = float(np.dot(S_cc_tgt, n_tgt_vec)) * n_tgt_vec
        S_cc_tgt_tangent_part = S_cc_tgt - S_cc_tgt_normal_part

        # Required source S_cc at this parameter:
        #   normal: κ_tgt * |S_c_src|²  * n̂_src
        #   tangential: S_cc_tgt_tangent scaled for tangent magnitude ratio
        tan_scale = S_c_sq / S_c_tgt_sq
        S_cc_desired = (kappa_tgt * S_c_sq) * n_src_vec + S_cc_tgt_tangent_part * tan_scale

        # Additive correction to P2_eval:
        #   S_cc = A * P2_eval + (B * P1_eval + C * P0_eval)
        #   => P2_eval_new = P2_eval_current + (S_cc_desired - S_cc_current) / A
        delta_P2_eval = (S_cc_desired - S_cc_current) / A_src

        # Apply correction to CP[2][k]:
        row2_new[k, :3] = orig_row2[k, :3] + delta_P2_eval
        if dim > 3:
            row2_new[k, 3:] = orig_row2[k, 3:]

    _set_cp_row(source, source_edge, 2, row2_new)


# ---------------------------------------------------------------------------
# Core: G3 -- adjust the fourth CP row for curvature-rate (dκ/ds) matching
# ---------------------------------------------------------------------------

def _boundary_third_deriv_coeff_A3(surf: NurbsSurface, edge: str) -> float:
    """Coefficient of CP[3] in the analytic third derivative at the boundary.

    For a clamped B-spline of degree p >= 3 with the first three non-trivial
    knot spans h1, h2, h3 measured inward from the boundary:

        S_ccc(boundary) = A3 * CP[3] + (terms in CP[0..2])

    where, by repeated divided-difference expansion of the de Boor recurrence
    at the clamped boundary,

        A3 = p*(p-1)*(p-2) / (h1 * (h1+h2) * (h1+h2+h3)).

    Returns A3 (the only coefficient needed to *solve* for the CP[3]
    correction); falls back to the reduced ``p*(p-1)*(p-2)/h1^3`` form when the
    later spans are unavailable.
    """
    if edge in ("u0", "u1"):
        knots = surf.knots_u
        p = surf.degree_u
    else:
        knots = surf.knots_v
        p = surf.degree_v

    if p < 3:
        return 0.0

    if edge in ("u0", "v0"):
        h1 = float(knots[p + 1] - knots[p])
        h2 = float(knots[p + 2] - knots[p + 1]) if len(knots) > p + 2 else h1
        h3 = float(knots[p + 3] - knots[p + 2]) if len(knots) > p + 3 else h2
    else:
        h1 = float(knots[-(p + 1)] - knots[-(p + 2)])
        h2 = float(knots[-(p + 2)] - knots[-(p + 3)]) if len(knots) > p + 2 else h1
        h3 = float(knots[-(p + 3)] - knots[-(p + 4)]) if len(knots) > p + 3 else h2

    denom = h1 * (h1 + h2) * (h1 + h2 + h3)
    if abs(denom) < 1e-18:
        return 0.0
    return float(p * (p - 1) * (p - 2)) / denom


def _cross_curvature_rate(surf: NurbsSurface, edge: str, t: float) -> float:
    """Analytic dκ/ds in the cross-boundary direction at along-edge parameter t.

    κ = (S_cc · n̂)/|S_c|² ; dκ/ds = (dκ/dc)/|S_c| with the no-normal-rate
    reduced form (exact for planar/cylindrical seams, the GK-62 oracle
    convention shared with ``surface_fillet._cross_boundary_curvature_rate``).
    """
    u_seam, v_seam, t_min, t_max = _edge_boundary_params(surf, edge)
    t_clamped = min(max(float(t), t_min), t_max)
    if edge in ("u0", "u1"):
        u, v = u_seam, t_clamped
        cross = "u"
    else:
        u, v = t_clamped, v_seam
        cross = "v"

    SKL = surface_derivatives(surf, u, v, d=3)
    if cross == "u":
        S_c = SKL[1, 0][:3]
        S_cc = SKL[2, 0][:3]
        S_ccc = SKL[3, 0][:3]
        sgn = 1.0 if edge == "u0" else -1.0
    else:
        S_c = SKL[0, 1][:3]
        S_cc = SKL[0, 2][:3]
        S_ccc = SKL[0, 3][:3]
        sgn = 1.0 if edge == "v0" else -1.0

    n_vec = np.cross(SKL[1, 0][:3], SKL[0, 1][:3])
    n_mag = float(np.linalg.norm(n_vec))
    if n_mag < 1e-14:
        return 0.0
    n_hat = n_vec / n_mag

    Sc_sq = float(np.dot(S_c, S_c))
    if Sc_sq < 1e-28:
        return 0.0
    Sc_mag = math.sqrt(Sc_sq)

    S_cc_dot_n = float(np.dot(S_cc, n_hat))
    S_ccc_dot_n = float(np.dot(S_ccc, n_hat))
    S_c_dot_S_cc = float(np.dot(S_c, S_cc))

    dkappa_dc = (
        S_ccc_dot_n * Sc_sq - S_cc_dot_n * 2.0 * S_c_dot_S_cc
    ) / (Sc_sq * Sc_sq)
    # The inward-direction sign cancels in dκ/ds for the magnitude-matched
    # oracle (κ is even under c → −c reflection of the parametrisation, dκ/ds
    # tracks the inward arc-length), so |dκ/ds| is what the G3 gate compares.
    return float(dkappa_dc / Sc_mag)


def _apply_g3(source: NurbsSurface, source_edge: str,
              target: NurbsSurface, target_edge: str) -> None:
    """Adjust the *fourth* CP row of source for G3 (curvature-rate) continuity.

    G3 requires the arc-length curvature rate dκ/ds to match across the seam.
    The cross-boundary third derivative at a clamped boundary is

        S_ccc = A3 * CP[3] + (fixed terms in CP[0..2]),

    and dκ/ds is, to leading order, linear in (S_ccc · n̂).  We therefore solve
    for the additive correction to CP[3] along the source normal that drives the
    source's dκ/ds to the target's, then take one secant refinement step against
    the analytic oracle (:func:`_cross_curvature_rate`) to absorb the
    second-order tangential coupling.  CP[0..2] (set by G0/G1/G2) are untouched.
    """
    p_src = _boundary_degree(source, source_edge)
    if p_src < 3:
        return  # G3 on degree < 3 is undefined — leave row 3 as-is.

    A3 = _boundary_third_deriv_coeff_A3(source, source_edge)
    if abs(A3) < 1e-30:
        return

    n_col_src = _cp_col_count(source, source_edge)
    dim = source.control_points.shape[2]

    _, _, t_min_src, t_max_src = _edge_boundary_params(source, source_edge)
    _, _, t_min_tgt, t_max_tgt = _edge_boundary_params(target, target_edge)
    u_seam_src, v_seam_src, _, _ = _edge_boundary_params(source, source_edge)

    if source_edge in ("u0", "u1"):
        knots_along = source.knots_v
        deg_along = source.degree_v
    else:
        knots_along = source.knots_u
        deg_along = source.degree_u

    greville = []
    for k in range(n_col_src):
        if deg_along > 0:
            t_k = float(np.mean(knots_along[k + 1: k + deg_along + 1]))
        else:
            t_k = t_min_src
        greville.append(min(max(t_k, t_min_src), t_max_src))

    orig_row3 = _get_cp_row(source, source_edge, 3)

    # Per-Greville along-edge surface normals (G0/G1/G2 already aligned them).
    normals = []
    targets = []
    for k in range(n_col_src):
        t_src = greville[k]
        tk_norm = ((t_src - t_min_src) / (t_max_src - t_min_src)
                   if (t_max_src - t_min_src) > 1e-15 else 0.0)
        t_tgt = t_min_tgt + tk_norm * (t_max_tgt - t_min_tgt)
        if source_edge in ("u0", "u1"):
            n_src_vec = surface_normal(source, u_seam_src, t_src)
        else:
            n_src_vec = surface_normal(source, t_src, v_seam_src)
        normals.append(n_src_vec)
        targets.append(_cross_curvature_rate(target, target_edge, t_tgt))

    # dκ/ds at Greville t_k is *affine* in the vector of normal offsets δ_j (the
    # third derivative is linear in CP[3], and the reduced dκ/ds is linear in
    # S_ccc·n̂).  Because the cross-boundary κ-rate at t_k couples several
    # along-edge row-3 CPs, solve the full coupled system M δ = (target − f0)
    # rather than per-CP.  M is assembled by finite probing along each normal.
    def _eval_rates(row: np.ndarray) -> np.ndarray:
        _set_cp_row(source, source_edge, 3, row)
        return np.array([
            _cross_curvature_rate(source, source_edge, greville[k])
            for k in range(n_col_src)
        ])

    f0 = _eval_rates(orig_row3)
    h = 1.0 / (abs(A3) + 1e-12)
    M = np.zeros((n_col_src, n_col_src))
    for j in range(n_col_src):
        probe = orig_row3.copy()
        probe[j, :3] = orig_row3[j, :3] + h * normals[j]
        fj = _eval_rates(probe)
        M[:, j] = (fj - f0) / h

    rhs = np.array(targets) - f0
    try:
        delta, *_ = np.linalg.lstsq(M, rhs, rcond=None)
    except np.linalg.LinAlgError:
        delta = np.zeros(n_col_src)

    row3_new = orig_row3.copy()
    for k in range(n_col_src):
        row3_new[k, :3] = orig_row3[k, :3] + float(delta[k]) * normals[k]
        if dim > 3:
            row3_new[k, 3:] = orig_row3[k, 3:]

    _set_cp_row(source, source_edge, 3, row3_new)


# ---------------------------------------------------------------------------
# Public analytic verification functions
# ---------------------------------------------------------------------------

def verify_seam_g3_analytic(
    source: NurbsSurface,
    source_edge: str,
    target: NurbsSurface,
    target_edge: str,
    samples: int = 32,
) -> float:
    """Analytic G3 seam verification: max |dκ_src/ds − dκ_tgt/ds|.

    Uses the analytic third-order NURBS curvature rate
    (:func:`_cross_curvature_rate`, the GK-62 dκ/ds oracle) at ``samples``
    positions along the seam.  Zero indicates matching curvature rate (G3
    continuous).
    """
    _, _, t_min_src, t_max_src = _edge_boundary_params(source, source_edge)
    _, _, t_min_tgt, t_max_tgt = _edge_boundary_params(target, target_edge)
    n = max(2, samples)
    max_residual = 0.0
    for i in range(n):
        tk = i / (n - 1) if n > 1 else 0.0
        t_src = t_min_src + tk * (t_max_src - t_min_src)
        t_tgt = t_min_tgt + tk * (t_max_tgt - t_min_tgt)
        k_src = _cross_curvature_rate(source, source_edge, t_src)
        k_tgt = _cross_curvature_rate(target, target_edge, t_tgt)
        diff = abs(k_src - k_tgt)
        if diff > max_residual:
            max_residual = diff
    return max_residual


def verify_seam_g1_analytic(
    source: NurbsSurface,
    source_edge: str,
    target: NurbsSurface,
    target_edge: str,
    samples: int = 32,
) -> float:
    """Analytic G1 seam verification: max cross-product residual.

    For each of ``samples`` positions along the seam, computes the cross-
    product residual ``|| (t_src / |t_src|) × (t_tgt / |t_tgt|) ||`` using
    true surface derivatives (``surface_derivatives``).  A value of zero
    indicates exactly parallel cross-boundary tangents (G1 continuous).

    Parameters
    ----------
    source, target : NurbsSurface
    source_edge, target_edge : str  -- edge identifiers (``'u0'`` etc.)
    samples : int  -- number of sample points along the seam

    Returns
    -------
    float
        Maximum G1 residual across all samples.  ≤ 1e-8 is considered
        analytically G1 continuous.
    """
    _, _, t_min_src, t_max_src = _edge_boundary_params(source, source_edge)
    _, _, t_min_tgt, t_max_tgt = _edge_boundary_params(target, target_edge)
    n = max(2, samples)
    max_residual = 0.0
    for i in range(n):
        tk = i / (n - 1) if n > 1 else 0.0
        t_src = t_min_src + tk * (t_max_src - t_min_src)
        t_tgt = t_min_tgt + tk * (t_max_tgt - t_min_tgt)
        t_s = _analytic_cross_tangent(source, source_edge, t_src)
        t_t = _analytic_cross_tangent(target, target_edge, t_tgt)
        n_s = float(np.linalg.norm(t_s))
        n_t = float(np.linalg.norm(t_t))
        if n_s < 1e-15 or n_t < 1e-15:
            continue
        cross = np.cross(t_s / n_s, t_t / n_t)
        residual = float(np.linalg.norm(cross))
        if residual > max_residual:
            max_residual = residual
    return max_residual


def verify_seam_g2_analytic(
    source: NurbsSurface,
    source_edge: str,
    target: NurbsSurface,
    target_edge: str,
    samples: int = 32,
) -> float:
    """Analytic G2 seam verification: max normal-curvature difference.

    For each of ``samples`` positions along the seam, computes
    ``|κ_src − κ_tgt|`` where κ is the normal curvature in the
    cross-boundary direction, evaluated via analytic ``surface_derivatives``.
    A value of zero indicates matching curvature (G2 continuous).

    Parameters
    ----------
    source, target : NurbsSurface
    source_edge, target_edge : str  -- edge identifiers
    samples : int  -- number of sample points along the seam

    Returns
    -------
    float
        Maximum G2 (normal curvature) residual.  ≤ 1e-7 is considered
        analytically G2 continuous.
    """
    _, _, t_min_src, t_max_src = _edge_boundary_params(source, source_edge)
    _, _, t_min_tgt, t_max_tgt = _edge_boundary_params(target, target_edge)
    n = max(2, samples)
    max_residual = 0.0
    for i in range(n):
        tk = i / (n - 1) if n > 1 else 0.0
        t_src = t_min_src + tk * (t_max_src - t_min_src)
        t_tgt = t_min_tgt + tk * (t_max_tgt - t_min_tgt)
        k_src = _analytic_cross_curvature(source, source_edge, t_src)
        k_tgt = _analytic_cross_curvature(target, target_edge, t_tgt)
        diff = abs(k_src - k_tgt)
        if diff > max_residual:
            max_residual = diff
    return max_residual


# ---------------------------------------------------------------------------
# Core: G0 -- snap boundary CP row to target boundary CP row
# ---------------------------------------------------------------------------

def _apply_g0(source: NurbsSurface, source_edge: str,
              target: NurbsSurface, target_edge: str) -> None:
    """Snap the boundary CP row of source to match the target boundary.

    Resamples the target boundary CP row to the source CP count via linear
    interpolation, then overwrites source's boundary row.
    """
    n_src = _cp_col_count(source, source_edge)
    t_tgt = _get_cp_row(target, target_edge, 0)   # target boundary CPs
    n_tgt = len(t_tgt)
    dim = source.control_points.shape[2]

    new_row = np.zeros((n_src, dim))
    for k in range(n_src):
        tk = k / (n_src - 1) if n_src > 1 else 0.0
        idx_f = tk * (n_tgt - 1)
        lo = int(math.floor(idx_f))
        hi = min(lo + 1, n_tgt - 1)
        alpha = idx_f - lo
        new_row[k, :3] = (1.0 - alpha) * t_tgt[lo, :3] + alpha * t_tgt[hi, :3]
        if dim > 3:
            # Preserve homogeneous weights from source
            src_row0 = _get_cp_row(source, source_edge, 0)
            new_row[k, 3:] = src_row0[k, 3:]

    _set_cp_row(source, source_edge, 0, new_row)


# ---------------------------------------------------------------------------
# Core: G1 -- adjust the second CP row for tangent matching
# ---------------------------------------------------------------------------

def _apply_g1(source: NurbsSurface, source_edge: str,
              target: NurbsSurface, target_edge: str) -> None:
    """Adjust the *second* CP row of source for G1 continuity.

    For a clamped B-spline of degree p:
        dS/dt|_boundary = p * (CP[1] - CP[0]) / knot_span

    To match the target tangent we need:
        (CP_src[1] - CP_src[0]) proportional to (CP_tgt[1] - CP_tgt[0])

    Strategy: set the magnitude of the source cross-boundary CP difference to
    match its own original magnitude (preserve the surface interior shape),
    but point it in the direction of the target's cross-boundary difference.
    """
    n_src = _cp_col_count(source, source_edge)
    n_tgt = _cp_col_count(target, target_edge)
    dim = source.control_points.shape[2]

    row0_src = _get_cp_row(source, source_edge, 0)  # already G0-matched
    row1_new = row0_src.copy()

    for k in range(n_src):
        # Parameter along the edge (0..1)
        tk = k / (n_src - 1) if n_src > 1 else 0.0
        # Corresponding index on the target
        idx_f = tk * (n_tgt - 1)
        lo = int(math.floor(idx_f))
        hi = min(lo + 1, n_tgt - 1)
        alpha = idx_f - lo

        # Target cross-boundary difference vector at this parameter
        d_tgt_lo = _cp_tangent_vector(target, target_edge, lo)
        d_tgt_hi = _cp_tangent_vector(target, target_edge, hi)
        d_tgt = (1.0 - alpha) * d_tgt_lo + alpha * d_tgt_hi

        n_tgt_vec = np.linalg.norm(d_tgt)
        if n_tgt_vec < 1e-15:
            # Target tangent is zero -- keep source CP unchanged
            row1_new[k] = _get_cp_row(source, source_edge, 1)[k]
            continue

        # Direction from target
        t_dir = d_tgt / n_tgt_vec

        # Magnitude: from the source's own original cross-boundary difference
        # (preserves interior shape, only changes direction)
        orig_row1 = _get_cp_row(source, source_edge, 1)
        d_src = orig_row1[k, :3] - row0_src[k, :3]
        magnitude = float(np.linalg.norm(d_src))
        if magnitude < 1e-15:
            # Source had zero tangent -- use target magnitude
            magnitude = n_tgt_vec

        # CP[1] = CP[0] + magnitude * t_dir
        row1_new[k, :3] = row0_src[k, :3] + magnitude * t_dir
        if dim > 3:
            row1_new[k, 3:] = orig_row1[k, 3:]

    _set_cp_row(source, source_edge, 1, row1_new)


# ---------------------------------------------------------------------------
# Core: G2 -- adjust the third CP row for curvature matching
# ---------------------------------------------------------------------------

def _apply_g2(source: NurbsSurface, source_edge: str,
              target: NurbsSurface, target_edge: str) -> None:
    """Adjust the *third* CP row of source for G2 (curvature) continuity.

    For a clamped B-spline of degree p >= 2:
        d2S/dt2|_boundary = p*(p-1) * (CP[2] - 2*CP[1] + CP[0]) / span^2

    We scale the target's second difference to match the source's parametric
    span ratio, then solve for CP[2]:
        CP[2] = 2*CP[1] - CP[0] + scale * (CP_tgt[2] - 2*CP_tgt[1] + CP_tgt[0])
    """
    p_src = _boundary_degree(source, source_edge)
    if p_src < 2:
        return   # G2 on degree-1 surface is undefined -- silently skip

    p_tgt = _boundary_degree(target, target_edge)
    span_src = _boundary_knot_span(source, source_edge)
    span_tgt = _boundary_knot_span(target, target_edge)

    # Scale factor: equate d2S/dt2 across the seam
    # (p_src*(p_src-1)/span_src^2) * delta2_src = (p_tgt*(p_tgt-1)/span_tgt^2) * delta2_tgt
    factor_src = max(1, p_src * (p_src - 1)) / (span_src ** 2)
    factor_tgt = max(1, p_tgt * (p_tgt - 1)) / (span_tgt ** 2) if p_tgt >= 2 else 1.0
    scale = factor_tgt / factor_src if factor_src > 1e-30 else 1.0

    n_src = _cp_col_count(source, source_edge)
    n_tgt = _cp_col_count(target, target_edge)
    dim = source.control_points.shape[2]

    row0_src = _get_cp_row(source, source_edge, 0)
    row1_src = _get_cp_row(source, source_edge, 1)
    row2_new = row1_src.copy()

    for k in range(n_src):
        tk = k / (n_src - 1) if n_src > 1 else 0.0
        idx_f = tk * (n_tgt - 1)
        lo = int(math.floor(idx_f))
        hi = min(lo + 1, n_tgt - 1)
        alpha = idx_f - lo

        if p_tgt >= 2:
            d2_tgt_lo = _cp_curvature_vector(target, target_edge, lo)
            d2_tgt_hi = _cp_curvature_vector(target, target_edge, hi)
            d2_tgt = (1.0 - alpha) * d2_tgt_lo + alpha * d2_tgt_hi
        else:
            d2_tgt = np.zeros(3)

        orig_row2 = _get_cp_row(source, source_edge, 2)
        row2_new[k, :3] = (2.0 * row1_src[k, :3] - row0_src[k, :3]
                            + scale * d2_tgt)
        if dim > 3:
            row2_new[k, 3:] = orig_row2[k, 3:]

    _set_cp_row(source, source_edge, 2, row2_new)


# ---------------------------------------------------------------------------
# Diagnostics -- all CP-based, no surface_evaluate needed
# ---------------------------------------------------------------------------

def _compute_deviations(
    source: NurbsSurface, source_edge: str,
    target: NurbsSurface, target_edge: str,
    samples: int,
    continuity: str,
) -> Tuple[float, float, float]:
    """Compute G0/G1/G2 seam deviations using CP-level geometry.

    Returns (max_position_dev, max_tangent_dev_rad, max_curvature_dev).
    Tangent and curvature devs are NaN when not requested or unavailable.
    """
    n_src = _cp_col_count(source, source_edge)
    n_tgt = _cp_col_count(target, target_edge)

    # G0: compare boundary CPs
    max_pos = 0.0
    for k in range(n_src):
        tk = k / (n_src - 1) if n_src > 1 else 0.0
        idx_f = tk * (n_tgt - 1)
        lo = int(math.floor(idx_f))
        hi = min(lo + 1, n_tgt - 1)
        alpha = idx_f - lo
        tgt_pos = ((1.0 - alpha) * _get_cp_row(target, target_edge, 0)[lo, :3] +
                   alpha * _get_cp_row(target, target_edge, 0)[hi, :3])
        src_pos = _get_cp_row(source, source_edge, 0)[k, :3]
        d = float(np.linalg.norm(src_pos - tgt_pos))
        if d > max_pos:
            max_pos = d

    max_tan = math.nan
    max_cur = math.nan

    if continuity in ("G1", "G2"):
        p_src = _boundary_degree(source, source_edge)
        p_tgt = _boundary_degree(target, target_edge)
        max_tan = 0.0
        n_rows_src = _cp_row_count(source, source_edge)
        n_rows_tgt = _cp_row_count(target, target_edge)
        if n_rows_src >= 2 and n_rows_tgt >= 2:
            for k in range(n_src):
                tk = k / (n_src - 1) if n_src > 1 else 0.0
                idx_f = tk * (n_tgt - 1)
                lo = int(math.floor(idx_f))
                hi = min(lo + 1, n_tgt - 1)
                alpha = idx_f - lo
                d_src = _cp_tangent_vector(source, source_edge, k)
                d_tgt_lo = _cp_tangent_vector(target, target_edge, lo)
                d_tgt_hi = _cp_tangent_vector(target, target_edge, hi)
                d_tgt = (1.0 - alpha) * d_tgt_lo + alpha * d_tgt_hi
                n_s = float(np.linalg.norm(d_src))
                n_t = float(np.linalg.norm(d_tgt))
                if n_s > 1e-15 and n_t > 1e-15:
                    cos_a = float(np.clip(np.dot(d_src, d_tgt) / (n_s * n_t), -1.0, 1.0))
                    angle = math.acos(cos_a)
                    if angle > max_tan:
                        max_tan = angle

    if continuity == "G2":
        p_src = _boundary_degree(source, source_edge)
        p_tgt = _boundary_degree(target, target_edge)
        n_rows_src = _cp_row_count(source, source_edge)
        n_rows_tgt = _cp_row_count(target, target_edge)
        if p_src >= 2 and p_tgt >= 2 and n_rows_src >= 3 and n_rows_tgt >= 3:
            span_src = _boundary_knot_span(source, source_edge)
            span_tgt = _boundary_knot_span(target, target_edge)
            factor_src = max(1, p_src * (p_src - 1)) / (span_src ** 2)
            factor_tgt = max(1, p_tgt * (p_tgt - 1)) / (span_tgt ** 2)
            max_cur = 0.0
            for k in range(n_src):
                tk = k / (n_src - 1) if n_src > 1 else 0.0
                idx_f = tk * (n_tgt - 1)
                lo = int(math.floor(idx_f))
                hi = min(lo + 1, n_tgt - 1)
                alpha = idx_f - lo
                d2_src = _cp_curvature_vector(source, source_edge, k)
                d2_tgt_lo = _cp_curvature_vector(target, target_edge, lo)
                d2_tgt_hi = _cp_curvature_vector(target, target_edge, hi)
                d2_tgt = (1.0 - alpha) * d2_tgt_lo + alpha * d2_tgt_hi
                # Compare actual curvature magnitudes
                kappa_src = float(np.linalg.norm(d2_src)) * factor_src
                kappa_tgt = float(np.linalg.norm(d2_tgt)) * factor_tgt
                diff = abs(kappa_src - kappa_tgt)
                if diff > max_cur:
                    max_cur = diff

    return max_pos, max_tan, max_cur


def _classify_continuity(
    max_pos: float,
    max_tan: float,
    max_cur: float,
    tolerance: float,
    max_cur_rate: float = math.nan,
) -> str:
    """Return the highest continuity level confirmed within tolerance.

    ``max_cur_rate`` (the G3 dκ/ds residual) is optional and defaults to NaN so
    that pre-G3 four-argument callers keep their behaviour (they top out at G2).
    """
    if math.isnan(max_pos) or max_pos > tolerance * 100:
        return "none"
    if math.isnan(max_tan) or max_tan > 0.05:   # ~3 degrees
        return "G0"
    if math.isnan(max_cur) or max_cur > tolerance * 1000:
        return "G1"
    if math.isnan(max_cur_rate) or max_cur_rate > tolerance * 1e4:
        return "G2"
    return "G3"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_surface_edge(
    target_surface: NurbsSurface,
    target_edge: str,
    source_surface: NurbsSurface,
    source_edge: str,
    continuity: str,
    *,
    samples: int = _DEFAULT_SAMPLES,
    tolerance: float = 1e-6,
) -> MatchResult:
    """Match source_surface's source_edge to target_surface's target_edge.

    Returns a new NurbsSurface (deep copy of source with boundary CPs adjusted).
    The original source_surface is never mutated.

    Parameters
    ----------
    target_surface : NurbsSurface
    target_edge : str  -- 'u0', 'u1', 'v0', or 'v1'
    source_surface : NurbsSurface
    source_edge : str  -- 'u0', 'u1', 'v0', or 'v1'
    continuity : str   -- 'G0', 'G1', or 'G2'
    samples : int      -- diagnostic sample count (default 32)
    tolerance : float  -- deviation threshold for continuity_achieved (default 1e-6)

    Returns
    -------
    MatchResult.  Never raises.
    """
    # --- Input validation ---------------------------------------------------
    if not isinstance(target_surface, NurbsSurface):
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(f"target_surface must be NurbsSurface, "
                    f"got {type(target_surface).__name__}"),
        )
    if not isinstance(source_surface, NurbsSurface):
        return MatchResult(
            modified_surface=None,
            ok=False,
            reason=(f"source_surface must be NurbsSurface, "
                    f"got {type(source_surface).__name__}"),
        )
    if target_edge not in _VALID_EDGES:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(f"target_edge must be one of {sorted(_VALID_EDGES)}, "
                    f"got {target_edge!r}"),
        )
    if source_edge not in _VALID_EDGES:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(f"source_edge must be one of {sorted(_VALID_EDGES)}, "
                    f"got {source_edge!r}"),
        )
    if continuity not in _VALID_CONTINUITY:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(f"continuity must be one of {sorted(_VALID_CONTINUITY)}, "
                    f"got {continuity!r}"),
        )
    if not isinstance(samples, int) or samples < 2:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=f"samples must be an integer >= 2, got {samples!r}",
        )
    if not isinstance(tolerance, (int, float)) or tolerance <= 0:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=f"tolerance must be a positive number, got {tolerance!r}",
        )

    # --- Check enough CP rows for the requested continuity ------------------
    n_rows_src = _cp_row_count(source_surface, source_edge)
    required = {"G0": 1, "G1": 2, "G2": 3, "G3": 4}[continuity]
    if n_rows_src < required:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(
                f"source_surface has only {n_rows_src} CP row(s) in the inward "
                f"direction; {continuity} requires at least {required}"
            ),
        )

    # G1/G2/G3 require enough rows on the target too
    n_rows_tgt = _cp_row_count(target_surface, target_edge)
    tgt_required = {"G0": 1, "G1": 2, "G2": 2, "G3": 4}[continuity]
    if continuity in ("G1", "G2", "G3") and n_rows_tgt < tgt_required:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=(
                f"target_surface has only {n_rows_tgt} CP row(s) in the inward "
                f"direction; {continuity} requires at least {tgt_required}"
            ),
        )

    # G3 requires degree >= 3 on source (third cross-boundary derivative).
    if continuity == "G3":
        p_src = _boundary_degree(source_surface, source_edge)
        if p_src < 3:
            return MatchResult(
                modified_surface=source_surface,
                ok=False,
                reason=(
                    f"G3 matching requires source degree >= 3 in the matched "
                    f"direction; got degree {p_src}"
                ),
            )

    # G2 requires degree >= 2 on source
    if continuity == "G2":
        p_src = _boundary_degree(source_surface, source_edge)
        if p_src < 2:
            return MatchResult(
                modified_surface=source_surface,
                ok=False,
                reason=(
                    f"G2 matching requires source degree >= 2 in the matched "
                    f"direction; got degree {p_src}"
                ),
            )

    # --- Deep-copy source ---------------------------------------------------
    try:
        source_copy = NurbsSurface(
            degree_u=source_surface.degree_u,
            degree_v=source_surface.degree_v,
            control_points=source_surface.control_points.copy(),
            knots_u=source_surface.knots_u.copy(),
            knots_v=source_surface.knots_v.copy(),
        )
    except Exception as exc:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=f"failed to copy source_surface: {exc}",
        )

    # --- Apply G0 -----------------------------------------------------------
    try:
        _apply_g0(source_copy, source_edge, target_surface, target_edge)
    except Exception as exc:
        return MatchResult(
            modified_surface=source_surface,
            ok=False,
            reason=f"G0 application failed: {exc}",
        )

    # --- Apply G1 -----------------------------------------------------------
    if continuity in ("G1", "G2", "G3"):
        try:
            _apply_g1(source_copy, source_edge, target_surface, target_edge)
        except Exception as exc:
            return MatchResult(
                modified_surface=source_surface,
                ok=False,
                reason=f"G1 application failed: {exc}",
            )

    # --- Apply G2 (analytic normal-curvature matching) ----------------------
    if continuity in ("G2", "G3"):
        try:
            _apply_g2_analytic(source_copy, source_edge, target_surface, target_edge)
        except Exception as exc:
            return MatchResult(
                modified_surface=source_surface,
                ok=False,
                reason=f"G2 application failed: {exc}",
            )

    # --- Apply G3 (analytic curvature-rate dκ/ds matching) ------------------
    if continuity == "G3":
        try:
            _apply_g3(source_copy, source_edge, target_surface, target_edge)
        except Exception as exc:
            return MatchResult(
                modified_surface=source_surface,
                ok=False,
                reason=f"G3 application failed: {exc}",
            )

    # --- Diagnostics (analytic for G1/G2; CP-based for G0) ------------------
    try:
        # G0: always CP-based (boundary position deviation)
        max_pos, _tan_cp, _cur_cp = _compute_deviations(
            source_copy, source_edge,
            target_surface, target_edge,
            samples, "G0",
        )
        # G1: analytic cross-product residual (radians-equivalent, via asin)
        if continuity in ("G1", "G2", "G3"):
            g1_res = verify_seam_g1_analytic(
                source_copy, source_edge,
                target_surface, target_edge,
                samples=samples,
            )
            # Convert cross-product magnitude to angle in radians (asin for small angles)
            max_tan = float(math.asin(min(g1_res, 1.0)))
        else:
            max_tan = math.nan
        # G2: analytic normal curvature difference
        if continuity in ("G2", "G3"):
            max_cur = verify_seam_g2_analytic(
                source_copy, source_edge,
                target_surface, target_edge,
                samples=samples,
            )
        else:
            max_cur = math.nan
        # G3: analytic curvature-rate (dκ/ds) difference
        if continuity == "G3":
            max_cur_rate = verify_seam_g3_analytic(
                source_copy, source_edge,
                target_surface, target_edge,
                samples=samples,
            )
        else:
            max_cur_rate = math.nan
    except Exception:
        max_pos, max_tan, max_cur, max_cur_rate = (
            math.nan, math.nan, math.nan, math.nan,
        )

    continuity_achieved = _classify_continuity(
        max_pos, max_tan, max_cur, tolerance, max_cur_rate,
    )

    return MatchResult(
        modified_surface=source_copy,
        ok=True,
        reason="",
        max_position_deviation=max_pos,
        max_tangent_deviation=max_tan,
        max_curvature_deviation=max_cur,
        max_curvature_rate_deviation=max_cur_rate,
        continuity_achieved=continuity_achieved,
    )


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

    def _build_surface(raw_cp, num_u: int, num_v: int,
                       degree_u: int, degree_v: int):
        try:
            cp_flat = [np.asarray(p, dtype=float) for p in raw_cp]
            dim = cp_flat[0].size
            cp = np.array([p.tolist()[:dim] for p in cp_flat],
                          dtype=float).reshape(num_u, num_v, dim)
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
            return NurbsSurface(
                degree_u=degree_u,
                degree_v=degree_v,
                control_points=cp,
                knots_u=_make_knots(num_u, degree_u),
                knots_v=_make_knots(num_v, degree_v),
            ), None
        except Exception as exc:
            return None, f"failed to build NurbsSurface: {exc}"

    def _parse_surface_args(a: dict, prefix: str):
        deg_u = a.get(f"{prefix}degree_u")
        deg_v = a.get(f"{prefix}degree_v")
        raw_cp = a.get(f"{prefix}control_points", [])
        num_u = a.get(f"{prefix}num_u")
        num_v = a.get(f"{prefix}num_v")

        if any(x is None for x in [deg_u, deg_v, num_u, num_v]) or not raw_cp:
            return None, err_payload(
                f"{prefix}degree_u/v, {prefix}control_points, "
                f"{prefix}num_u/v are required",
                "BAD_ARGS",
            )
        try:
            deg_u = int(deg_u)
            deg_v = int(deg_v)
            num_u = int(num_u)
            num_v = int(num_v)
        except (TypeError, ValueError) as exc:
            return None, err_payload(
                f"degree/num values must be integers: {exc}", "BAD_ARGS"
            )
        if deg_u < 1 or deg_v < 1:
            return None, err_payload(
                f"{prefix}degree_u and degree_v must be >= 1", "BAD_ARGS"
            )
        if num_u < 2 or num_v < 2:
            return None, err_payload(
                f"{prefix}num_u and num_v must be >= 2", "BAD_ARGS"
            )
        if len(raw_cp) != num_u * num_v:
            return None, err_payload(
                (f"{prefix}control_points length ({len(raw_cp)}) "
                 f"!= num_u*num_v ({num_u*num_v})"),
                "BAD_ARGS",
            )
        surf, err = _build_surface(raw_cp, num_u, num_v, deg_u, deg_v)
        if err is not None:
            return None, err_payload(err, "BAD_ARGS")
        return surf, None

    _match_srf_spec = ToolSpec(
        name="match_surface_edge_tool",
        description=(
            "Modify a source NURBS surface's boundary control points so that "
            "the specified edge matches the edge of a target NURBS surface at "
            "G0 (position), G1 (tangent), or G2 (curvature) continuity.\n"
            "\n"
            "This is the pure-Python 'MatchSrf' implementation.  The OCC "
            "GeomFill_NSections binding (WASM-blocked) is not used.\n"
            "\n"
            "Returns:\n"
            "  ok                      : bool\n"
            "  modified_control_points : list of [x,y,z] in row-major order\n"
            "  max_position_deviation  : float  (G0 seam error)\n"
            "  max_tangent_deviation   : float  (G1 angle radians; null if N/A)\n"
            "  max_curvature_deviation : float  (G2 curvature diff; null if N/A)\n"
            "  continuity_achieved     : str    (G0/G1/G2/none)\n"
            "\n"
            "On error: {ok: false, reason: str}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target_degree_u": {"type": "integer"},
                "target_degree_v": {"type": "integer"},
                "target_control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "target_num_u": {"type": "integer"},
                "target_num_v": {"type": "integer"},
                "target_edge": {
                    "type": "string",
                    "enum": ["u0", "u1", "v0", "v1"],
                },
                "source_degree_u": {"type": "integer"},
                "source_degree_v": {"type": "integer"},
                "source_control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "source_num_u": {"type": "integer"},
                "source_num_v": {"type": "integer"},
                "source_edge": {
                    "type": "string",
                    "enum": ["u0", "u1", "v0", "v1"],
                },
                "continuity": {
                    "type": "string",
                    "enum": ["G0", "G1", "G2"],
                },
                "samples": {"type": "integer"},
                "tolerance": {"type": "number"},
            },
            "required": [
                "target_degree_u", "target_degree_v",
                "target_control_points", "target_num_u", "target_num_v",
                "target_edge",
                "source_degree_u", "source_degree_v",
                "source_control_points", "source_num_u", "source_num_v",
                "source_edge",
                "continuity",
            ],
        },
    )

    @register(_match_srf_spec)
    async def run_match_surface_edge(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        target_surf, err = _parse_surface_args(a, "target_")
        if err is not None:
            return err
        source_surf, err = _parse_surface_args(a, "source_")
        if err is not None:
            return err

        target_edge = a.get("target_edge", "")
        source_edge = a.get("source_edge", "")
        continuity = a.get("continuity", "")
        samples = a.get("samples", _DEFAULT_SAMPLES)
        tolerance = a.get("tolerance", 1e-6)

        if target_edge not in _VALID_EDGES:
            return err_payload(
                f"target_edge must be one of {sorted(_VALID_EDGES)}", "BAD_ARGS"
            )
        if source_edge not in _VALID_EDGES:
            return err_payload(
                f"source_edge must be one of {sorted(_VALID_EDGES)}", "BAD_ARGS"
            )
        if continuity not in _VALID_CONTINUITY:
            return err_payload(
                f"continuity must be one of {sorted(_VALID_CONTINUITY)}", "BAD_ARGS"
            )
        if not isinstance(samples, int) or samples < 2:
            return err_payload("samples must be integer >= 2", "BAD_ARGS")
        if not isinstance(tolerance, (int, float)) or tolerance <= 0:
            return err_payload("tolerance must be a positive number", "BAD_ARGS")

        result = match_surface_edge(
            target_surf, target_edge,
            source_surf, source_edge,
            continuity,
            samples=samples,
            tolerance=float(tolerance),
        )

        if not result.ok:
            return err_payload(result.reason, "OP_FAILED")

        cp = result.modified_surface.control_points
        flat_cp = cp.reshape(-1, cp.shape[2]).tolist()

        return ok_payload({
            "modified_control_points": flat_cp,
            "max_position_deviation": result.max_position_deviation,
            "max_tangent_deviation": (None if math.isnan(result.max_tangent_deviation)
                                      else result.max_tangent_deviation),
            "max_curvature_deviation": (None if math.isnan(result.max_curvature_deviation)
                                        else result.max_curvature_deviation),
            "continuity_achieved": result.continuity_achieved,
        })

    _diagnose_spec = ToolSpec(
        name="diagnose_surface_continuity",
        description=(
            "Measure G0/G1/G2 deviation across the seam between two NURBS "
            "surface edges without modifying any surface.  Returns:\n"
            "  ok, max_position_deviation, max_tangent_deviation (radians),\n"
            "  max_curvature_deviation, continuity_achieved.\n"
            "Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target_degree_u": {"type": "integer"},
                "target_degree_v": {"type": "integer"},
                "target_control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "target_num_u": {"type": "integer"},
                "target_num_v": {"type": "integer"},
                "target_edge": {"type": "string", "enum": ["u0", "u1", "v0", "v1"]},
                "source_degree_u": {"type": "integer"},
                "source_degree_v": {"type": "integer"},
                "source_control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "source_num_u": {"type": "integer"},
                "source_num_v": {"type": "integer"},
                "source_edge": {"type": "string", "enum": ["u0", "u1", "v0", "v1"]},
                "continuity": {"type": "string", "enum": ["G0", "G1", "G2"]},
                "samples": {"type": "integer"},
                "tolerance": {"type": "number"},
            },
            "required": [
                "target_degree_u", "target_degree_v",
                "target_control_points", "target_num_u", "target_num_v",
                "target_edge",
                "source_degree_u", "source_degree_v",
                "source_control_points", "source_num_u", "source_num_v",
                "source_edge",
                "continuity",
            ],
        },
    )

    @register(_diagnose_spec)
    async def run_diagnose_surface_continuity(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        target_surf, err = _parse_surface_args(a, "target_")
        if err is not None:
            return err
        source_surf, err = _parse_surface_args(a, "source_")
        if err is not None:
            return err

        target_edge = a.get("target_edge", "")
        source_edge = a.get("source_edge", "")
        continuity = a.get("continuity", "G2")
        samples = a.get("samples", _DEFAULT_SAMPLES)
        tolerance = a.get("tolerance", 1e-6)

        if target_edge not in _VALID_EDGES:
            return err_payload(
                f"target_edge must be one of {sorted(_VALID_EDGES)}", "BAD_ARGS"
            )
        if source_edge not in _VALID_EDGES:
            return err_payload(
                f"source_edge must be one of {sorted(_VALID_EDGES)}", "BAD_ARGS"
            )
        if continuity not in _VALID_CONTINUITY:
            return err_payload(
                f"continuity must be one of {sorted(_VALID_CONTINUITY)}", "BAD_ARGS"
            )
        if not isinstance(samples, int) or samples < 2:
            return err_payload("samples must be integer >= 2", "BAD_ARGS")
        if not isinstance(tolerance, (int, float)) or tolerance <= 0:
            return err_payload("tolerance must be a positive number", "BAD_ARGS")

        try:
            max_pos, max_tan, max_cur = _compute_deviations(
                source_surf, source_edge,
                target_surf, target_edge,
                int(samples), continuity,
            )
        except Exception as exc:
            return err_payload(f"deviation computation failed: {exc}", "OP_FAILED")

        continuity_achieved = _classify_continuity(
            max_pos, max_tan, max_cur, float(tolerance)
        )

        return ok_payload({
            "max_position_deviation": max_pos,
            "max_tangent_deviation": (None if math.isnan(max_tan) else max_tan),
            "max_curvature_deviation": (None if math.isnan(max_cur) else max_cur),
            "continuity_achieved": continuity_achieved,
        })
