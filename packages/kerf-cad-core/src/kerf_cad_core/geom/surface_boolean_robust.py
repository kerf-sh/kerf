"""
surface_boolean_robust.py
=========================
Robustness layer for dense-NURBS surface booleans (T-37).

Public API
----------
surface_health_check(srf) -> dict
    Validates a NurbsSurface for degenerate/near-zero-area patches and
    self-intersecting control net.  Returns a dict with:
        ok         : bool
        warnings   : list[str]   (non-fatal issues)
        errors     : list[str]   (fatal; ok==False)

surface_boolean_robust(srf_a, srf_b, kind, *, bbox_tol=None, occ_fn=None) -> dict
    Robust wrapper around any surface-boolean back-end.  Returns:
        ok         : bool
        result     : value returned by occ_fn on success, else None
        reason     : str  (human-readable failure description, set when ok==False)
        retried    : bool (True when the first attempt failed and retry succeeded)
        tolerance  : float (the tolerance actually used)

Guards applied (pure-Python, no OCC required):
  1. Input sanitation — surface_health_check on both surfaces; rejects
     degenerate or self-intersecting control nets immediately.
  2. Tolerance auto-scaling — default tolerance is scaled to
     bbox_diagonal * 1e-4, clamped to [1e-7, 1e-2].
  3. Retry-with-relaxed-tolerance — if occ_fn raises or returns a falsy
     result, one retry is made with tolerance * 10, still within the clamp.
  4. Never raises — all exceptions are caught and surfaced in the return dict.

OCC-dependent execution is isolated behind the ``occ_fn`` parameter so the
pure-Python guards can be unit-tested without OCC installed.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Literal, Optional

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOL_MIN: float = 1e-7
_TOL_MAX: float = 1e-2
_TOL_FRACTION: float = 1e-4   # fraction of bbox diagonal
_TOL_RELAX_FACTOR: float = 10.0

BooleanKind = Literal["cut", "fuse", "common"]
_VALID_KINDS = frozenset({"cut", "fuse", "common"})


# ---------------------------------------------------------------------------
# surface_health_check
# ---------------------------------------------------------------------------

def surface_health_check(srf: Any) -> dict:
    """Validate a NurbsSurface for boolean suitability.

    Parameters
    ----------
    srf : NurbsSurface
        The surface to check.

    Returns
    -------
    dict with keys:
        ok       : bool
        warnings : list[str]   (non-fatal)
        errors   : list[str]   (fatal — boolean will be rejected)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── Type guard ──────────────────────────────────────────────────────────
    if not isinstance(srf, NurbsSurface):
        errors.append(
            f"expected NurbsSurface, got {type(srf).__name__}"
        )
        return {"ok": False, "errors": errors, "warnings": warnings}

    cp = srf.control_points  # shape (nu, nv, dim)

    # ── Degenerate-patch detection: near-zero-area patches ─────────────────
    # A patch is degenerate if all four corners of any (i,j) quad are
    # coincident (within tolerance) or if adjacent rows/cols collapse.
    nu, nv, dim = cp.shape
    _DEGEN_TOL = 1e-10

    degen_count = 0
    for i in range(nu - 1):
        for j in range(nv - 1):
            a = cp[i,     j    ]
            b = cp[i + 1, j    ]
            c = cp[i,     j + 1]
            d = cp[i + 1, j + 1]
            # Compute approximate patch area via cross product of diagonals
            diag1 = d - a
            diag2 = c - b
            if dim >= 3:
                cross = np.cross(diag1[:3], diag2[:3])
                area = 0.5 * np.linalg.norm(cross)
            else:
                # 2-D fallback
                area = 0.5 * abs(
                    diag1[0] * diag2[1] - diag1[1] * diag2[0]
                ) if dim >= 2 else 0.0
            if area < _DEGEN_TOL:
                degen_count += 1

    total_patches = max(1, (nu - 1) * (nv - 1))
    degen_fraction = degen_count / total_patches

    if degen_fraction >= 1.0:
        errors.append(
            f"all {degen_count} patches are degenerate (near-zero area); "
            "surface cannot be used for boolean operations"
        )
    elif degen_fraction > 0.5:
        errors.append(
            f"{degen_count}/{total_patches} patches are degenerate "
            f"({degen_fraction:.0%}); surface is too degenerate for boolean"
        )
    elif degen_count > 0:
        warnings.append(
            f"{degen_count}/{total_patches} degenerate patch(es) detected; "
            "boolean may produce open edges near those patches"
        )

    # ── Self-intersecting control net ───────────────────────────────────────
    # Check for self-intersection in the control net by looking for
    # sign changes in consecutive cross-products of the net spans.
    # This is a cheap heuristic (not a rigorous test) but catches common
    # cases such as folded/twisted control grids.
    if nu >= 3 and nv >= 2 and dim >= 2:
        self_intersect = _check_control_net_self_intersection(cp)
        if self_intersect:
            errors.append(
                "control net is self-intersecting (twisted or folded rows/columns); "
                "boolean result would be undefined"
            )

    # ── Duplicate control points ─────────────────────────────────────────────
    flat = cp.reshape(-1, dim)
    if len(flat) >= 2:
        # Check consecutive pairs in row-major order
        diffs = np.linalg.norm(np.diff(flat, axis=0), axis=1)
        n_dup = int(np.sum(diffs < _DEGEN_TOL))
        if n_dup > 0:
            warnings.append(
                f"{n_dup} pair(s) of consecutive duplicate control points; "
                "consider knot removal before boolean"
            )

    # ── Degree sanity ────────────────────────────────────────────────────────
    if srf.degree_u < 1 or srf.degree_v < 1:
        errors.append(
            f"surface degree must be >= 1; got degree_u={srf.degree_u}, "
            f"degree_v={srf.degree_v}"
        )

    if srf.degree_u > 9 or srf.degree_v > 9:
        warnings.append(
            f"very high degree surface (degree_u={srf.degree_u}, "
            f"degree_v={srf.degree_v}); boolean may be slow or numerically "
            "unstable — consider degree reduction"
        )

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings}


def _check_control_net_self_intersection(cp: np.ndarray) -> bool:
    """Return True if the control-net rows show a sign-flip in orientation.

    We compute the cross-product of consecutive row-span vectors along the
    U direction at each V column.  A sign change indicates a fold/twist.
    Only the XY components are used (first 2 coords), which handles both
    2-D and 3-D surfaces projected onto their dominant plane.
    """
    nu, nv, dim = cp.shape
    if dim < 2:
        return False

    for v in range(nv):
        signs = []
        for u in range(nu - 2):
            # Vector from cp[u,v] -> cp[u+1,v] and cp[u+1,v] -> cp[u+2,v]
            span1 = cp[u + 1, v, :2] - cp[u,     v, :2]
            span2 = cp[u + 2, v, :2] - cp[u + 1, v, :2]
            cross_z = span1[0] * span2[1] - span1[1] * span2[0]
            if abs(cross_z) > 1e-14:
                signs.append(1 if cross_z > 0 else -1)
        # If we have both positive and negative, the net folds on itself
        if signs and min(signs) < 0 < max(signs):
            return True

    return False


# ---------------------------------------------------------------------------
# Bounding-box helpers
# ---------------------------------------------------------------------------

def _compute_bbox_diagonal(srf_a: NurbsSurface, srf_b: NurbsSurface) -> float:
    """Return the diagonal length of the combined bounding box of both surfaces."""
    pts_a = srf_a.control_points.reshape(-1, srf_a.control_points.shape[2])
    pts_b = srf_b.control_points.reshape(-1, srf_b.control_points.shape[2])
    all_pts = np.vstack([pts_a, pts_b])
    bbox_min = all_pts.min(axis=0)
    bbox_max = all_pts.max(axis=0)
    diag = float(np.linalg.norm(bbox_max - bbox_min))
    return diag if diag > 0 else 1.0


def _auto_tolerance(srf_a: NurbsSurface, srf_b: NurbsSurface) -> float:
    """Compute a tolerance scaled to the combined bounding box."""
    diag = _compute_bbox_diagonal(srf_a, srf_b)
    tol = diag * _TOL_FRACTION
    return float(np.clip(tol, _TOL_MIN, _TOL_MAX))


def _relaxed_tolerance(tol: float) -> Optional[float]:
    """Return a relaxed tolerance (tol * factor), or None if already at max."""
    relaxed = tol * _TOL_RELAX_FACTOR
    if relaxed > _TOL_MAX:
        return None
    return relaxed


# ---------------------------------------------------------------------------
# surface_boolean_robust
# ---------------------------------------------------------------------------

def surface_boolean_robust(
    srf_a: Any,
    srf_b: Any,
    kind: str,
    *,
    bbox_tol: Optional[float] = None,
    occ_fn: Optional[Callable[[Any, Any, str, float], Any]] = None,
) -> dict:
    """Robust wrapper for surface boolean operations on dense NURBS.

    Parameters
    ----------
    srf_a, srf_b : NurbsSurface
        The two operand surfaces.
    kind : str
        One of "cut", "fuse", "common".
    bbox_tol : float, optional
        Override the auto-computed bbox-relative tolerance.
    occ_fn : callable, optional
        Signature: occ_fn(srf_a, srf_b, kind, tolerance) -> result.
        When None, the function performs all guards and returns
        ok=True with result=None (useful for pure-Python unit tests).
        In production, pass the OCC-backed implementation.

    Returns
    -------
    dict with keys:
        ok        : bool
        result    : Any   (occ_fn return value on success, else None)
        reason    : str   (set when ok==False)
        retried   : bool  (True if first attempt failed and retry succeeded)
        tolerance : float (tolerance actually used)
        health_a  : dict  (surface_health_check result for srf_a)
        health_b  : dict  (surface_health_check result for srf_b)
    """
    # ── Validate kind ────────────────────────────────────────────────────────
    if kind not in _VALID_KINDS:
        return {
            "ok": False,
            "result": None,
            "reason": f"invalid boolean kind '{kind}'; must be one of {sorted(_VALID_KINDS)}",
            "retried": False,
            "tolerance": 0.0,
            "health_a": {},
            "health_b": {},
        }

    # ── Input sanitation ─────────────────────────────────────────────────────
    health_a = surface_health_check(srf_a)
    health_b = surface_health_check(srf_b)

    if not health_a["ok"]:
        return {
            "ok": False,
            "result": None,
            "reason": "surface A failed health check: " + "; ".join(health_a["errors"]),
            "retried": False,
            "tolerance": 0.0,
            "health_a": health_a,
            "health_b": health_b,
        }

    if not health_b["ok"]:
        return {
            "ok": False,
            "result": None,
            "reason": "surface B failed health check: " + "; ".join(health_b["errors"]),
            "retried": False,
            "tolerance": 0.0,
            "health_a": health_a,
            "health_b": health_b,
        }

    # ── Tolerance auto-scaling ───────────────────────────────────────────────
    if bbox_tol is not None:
        if not isinstance(bbox_tol, (int, float)) or bbox_tol <= 0:
            return {
                "ok": False,
                "result": None,
                "reason": f"bbox_tol must be a positive number; got {bbox_tol!r}",
                "retried": False,
                "tolerance": 0.0,
                "health_a": health_a,
                "health_b": health_b,
            }
        tol = float(np.clip(bbox_tol, _TOL_MIN, _TOL_MAX))
    else:
        tol = _auto_tolerance(srf_a, srf_b)

    # ── No OCC back-end: guards-only mode ────────────────────────────────────
    if occ_fn is None:
        return {
            "ok": True,
            "result": None,
            "reason": "",
            "retried": False,
            "tolerance": tol,
            "health_a": health_a,
            "health_b": health_b,
        }

    # ── First attempt ────────────────────────────────────────────────────────
    try:
        result = occ_fn(srf_a, srf_b, kind, tol)
        if result is not None:
            return {
                "ok": True,
                "result": result,
                "reason": "",
                "retried": False,
                "tolerance": tol,
                "health_a": health_a,
                "health_b": health_b,
            }
        first_error = "occ_fn returned None (boolean produced no output)"
    except Exception as exc:
        first_error = str(exc)

    # ── Retry with relaxed tolerance ─────────────────────────────────────────
    relaxed = _relaxed_tolerance(tol)
    if relaxed is not None:
        try:
            result = occ_fn(srf_a, srf_b, kind, relaxed)
            if result is not None:
                return {
                    "ok": True,
                    "result": result,
                    "reason": "",
                    "retried": True,
                    "tolerance": relaxed,
                    "health_a": health_a,
                    "health_b": health_b,
                }
            retry_error = "occ_fn returned None on retry"
        except Exception as exc:
            retry_error = str(exc)
    else:
        retry_error = f"relaxed tolerance would exceed maximum ({_TOL_MAX})"

    return {
        "ok": False,
        "result": None,
        "reason": (
            f"boolean failed at tolerance {tol:.2e}: {first_error}; "
            f"retry also failed: {retry_error}"
        ),
        "retried": relaxed is not None,
        "tolerance": relaxed if relaxed is not None else tol,
        "health_a": health_a,
        "health_b": health_b,
    }
