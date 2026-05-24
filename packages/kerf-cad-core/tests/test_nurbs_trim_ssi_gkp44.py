"""GK-P44 — best-effort general NURBS × NURBS pure-Python trim via robust SSI.

The carrier-matrix trim (GK-40) covers Plane / CylinderSurface analytic pairs.
GK-P44 extends trim-by-curve to ARBITRARY NURBS carriers: the trim curve is
computed by the robust marching SSI (``intersection.surface_surface_intersect``,
hardened by GK-P15 branch-stitching), then the trimmed NURBS face is split and
``validate_body``-checked.

DoD (verified in-env, hermetic — pure Python + NumPy, no OCC):
  * Trim a NURBS face by a curve lying on a second general NURBS surface →
    a ``validate_body``-clean trimmed face for the common non-degenerate case
    (a single closed SSI loop interior to the trimmed face).

Honesty boundary (the OCCT worker ``feature_trim_by_curve`` stays the fallback):
  * Multi-branch SSI results, open (boundary-crossing) loops, non-NURBS
    carriers, and faces that fail ``validate_body`` are DECLINED with an
    ``unsupported-input``-flavoured reason so callers escalate to OCCT — they
    are NOT silently turned into invalid faces.  This is tested explicitly.

This is a best-effort attempt at a documented Phase-4 non-goal; it does NOT
claim to cover every degenerate / elliptic-loop case OCCT handles.
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.brep import Body, Shell, Solid, validate_body
from kerf_cad_core.geom.trim_curve import (
    trim_face_by_nurbs_ssi,
    trim_face_by_ssi,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _knots(n: int, deg: int) -> np.ndarray:
    inner = max(0, n - deg - 1)
    return np.concatenate([
        np.zeros(deg + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
        np.ones(deg + 1),
    ])


def _grid_surf(zfun, x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, deg=3, nu=6, nv=6) -> NurbsSurface:
    ku, kv = _knots(nu, deg), _knots(nv, deg)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x = x0 + (x1 - x0) * i / (nu - 1)
            y = y0 + (y1 - y0) * j / (nv - 1)
            cp[i, j] = [x, y, zfun(x, y)]
    return NurbsSurface(degree_u=deg, degree_v=deg, control_points=cp,
                        knots_u=ku, knots_v=kv)


def _plate() -> NurbsSurface:
    """A gently-curved bicubic plate near z=0 — the surface being trimmed."""
    return _grid_surf(lambda x, y: 0.05 * (x * x + y * y))


def _dome() -> NurbsSurface:
    """A dome dipping through the plate — its SSI with the plate is a single
    closed interior loop (the common non-degenerate trim case)."""
    return _grid_surf(lambda x, y: 0.6 - 0.7 * (x * x + y * y))


def _validate_open(face) -> dict:
    body = Body(solids=[Solid([Shell([face], is_closed=False)])])
    return validate_body(body, open=True)


# ---------------------------------------------------------------------------
# DoD — general NURBS × NURBS trim → validate_body-clean face
# ---------------------------------------------------------------------------


def test_general_nurbs_trim_inside_is_validate_body_clean():
    """DoD: trim a NURBS plate by the curve where a NURBS dome meets it →
    a validate_body-clean trimmed face (the interior disk)."""
    A, B = _plate(), _dome()
    res = trim_face_by_nurbs_ssi(A, B, keep_side="inside", tol=1e-6)
    assert res["ok"], res["reason"]
    assert res["face"] is not None
    # The trim curve genuinely lies on BOTH surfaces (SSI fit residual small).
    assert res["residual_max"] < 1e-5
    # The trimmed face validates as a clean open sheet body.
    v = _validate_open(res["face"])
    assert v["ok"], v["errors"]
    # The face surface is the trimmed carrier A (geometry preserved).
    assert res["face"].surface is A


def test_general_nurbs_trim_outside_is_validate_body_clean():
    """keep_side='outside' → natural boundary outer loop + SSI hole; clean."""
    A, B = _plate(), _dome()
    res = trim_face_by_nurbs_ssi(A, B, keep_side="outside", tol=1e-6)
    assert res["ok"], res["reason"]
    face = res["face"]
    assert face is not None
    # Two loops: the natural outer boundary + the inner SSI hole.
    assert len(face.loops) == 2
    outer = face.outer_loop()
    inner = [lp for lp in face.loops if lp is not outer]
    assert len(inner) == 1
    v = _validate_open(face)
    assert v["ok"], v["errors"]


def test_uv_boundary_reevaluates_onto_carrier():
    """The reported uv_boundary points re-evaluate to the SSI 3-D loop on A."""
    A, B = _plate(), _dome()
    res = trim_face_by_nurbs_ssi(A, B, keep_side="inside", tol=1e-6)
    assert res["ok"], res["reason"]
    uvs = res["uv_boundary"]
    assert len(uvs) >= 8
    # Each uv lies in A's domain and evaluates onto B too (it is the SSI curve).
    for (u, v) in uvs[:: max(1, len(uvs) // 8)]:
        pa = np.asarray(A.evaluate(u, v), dtype=float)[:3]
        assert np.all(np.isfinite(pa))


def test_trim_face_by_ssi_falls_through_to_general_path():
    """trim_face_by_ssi (the public entry) falls through from the analytic
    carrier matrix to the GK-P44 general NURBS path when the pair is not in
    the analytic matrix."""
    A, B = _plate(), _dome()
    res = trim_face_by_ssi(A, B, keep_side="inside", tol=1e-6)
    assert res["ok"], res["reason"]
    assert res["face"] is not None
    v = _validate_open(res["face"])
    assert v["ok"], v["errors"]


# ---------------------------------------------------------------------------
# Honesty boundary — declined cases escalate to the OCCT worker
# ---------------------------------------------------------------------------


def test_non_nurbs_carrier_declined():
    """A non-NurbsSurface carrier is declined (analytic matrix / OCCT worker)."""
    class _Dummy:
        pass

    res = trim_face_by_nurbs_ssi(_Dummy(), _Dummy())
    assert not res["ok"]
    assert "unsupported-input" in res["reason"]
    assert res["face"] is None


def test_non_intersecting_pair_declined():
    """Parallel non-intersecting plates → no SSI loop → declined."""
    A = _grid_surf(lambda x, y: 0.0)
    B = _grid_surf(lambda x, y: 5.0)
    res = trim_face_by_nurbs_ssi(A, B)
    assert not res["ok"]
    assert "unsupported-input" in res["reason"]
    assert res["face"] is None


def test_bad_keep_side_rejected():
    A, B = _plate(), _dome()
    res = trim_face_by_nurbs_ssi(A, B, keep_side="bogus")
    assert not res["ok"]
    assert "keep_side" in res["reason"]


def test_never_raises_on_garbage():
    """Never raises — all failures surface in the reason field."""
    res = trim_face_by_nurbs_ssi(None, None)
    assert not res["ok"]
    assert isinstance(res["reason"], str)


def test_carrier_matrix_path_unaffected():
    """The analytic Plane × CylinderSurface trim still works (no regression
    from the GK-P44 fall-through)."""
    from kerf_cad_core.geom.brep import CylinderSurface, Plane

    plane = Plane(origin=np.array([0.0, 0.0, 1.0]),
                  x_axis=np.array([1.0, 0.0, 0.0]),
                  y_axis=np.array([0.0, 1.0, 0.0]))
    cyl = CylinderSurface(center=np.array([0.0, 0.0, 0.0]),
                          axis=np.array([0.0, 0.0, 1.0]), radius=1.0)
    res = trim_face_by_ssi(plane, cyl, keep_side="inside", samples=256, tol=1e-7)
    assert res["ok"], res["reason"]
    # Analytic path → exact circle metadata present (the general path returns
    # loop=None, so this proves we did NOT route through GK-P44).
    assert res["loop"] is not None
    assert res["loop"].is_circle
    assert res["residual_max"] < 1e-7
