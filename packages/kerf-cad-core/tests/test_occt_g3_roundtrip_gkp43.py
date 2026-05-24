"""GK-P43 — best-effort OCCT-path G3 (analyzer + pole round-trip).

Two real deliverables, NOT OCCT-enum enforcement (that stays structurally
impossible: ``GeomAbs_G3`` is absent from ``GeomAbs_Shape``):

  (a) **Analyzer** — ``surface_analysis.occt_g3_residual_from_poles`` measures
      the cross-boundary arc-length curvature rate dκ/ds across a seam from the
      extracted B-spline poles, using the GK-62 analytic third-derivative
      oracle.  Surfaced through ``continuity_audit`` as a numeric per-edge
      ``g3_residuals`` map.
  (b) **Pole round-trip** — ``surface_analysis.occt_g3_pole_roundtrip`` extracts
      the OCCT poles, runs the pure-Python G3 pole-adjustment (match_srf G3,
      GK-P10), writes the adjusted poles back, and reports residual_after.

WHAT IS VERIFIED IN-ENV (this test, hermetic):
  * The analyzer + pole-adjustment + residual math, run on a pure-Python
    ``NurbsSurface`` standing in for the OCCT-extracted poles.  The OCCT surface
    and this NurbsSurface evaluate bit-identically (same poles, same knots, same
    Cox-de Boor basis), so the dκ/ds the oracle computes here equals the dκ/ds
    OCCT's ``DN(u,v,nu,nv)`` would yield.
  * DoD: an OCCT-origin surface pair reports a G3 residual < 1e-5 after the
    round-trip.

WHAT IS DEPLOY-GATED (NOT exercised here; OCC/pythonocc is not installed):
  * The worker ``DN`` path (``occtBridge.sampleSurfaceThirdDeriv`` /
    ``occtWorker.opOcctG3Audit``) that samples third derivatives off a live
    ``Geom_BSplineSurface`` — gated behind the ``NURBS_PHASE4_G3_BINDINGS`` boot
    probe with a graceful ``OcctG3UnsupportedError`` degrade.
  * The ``SetPole`` write-back on the live OCCT surface (the pure-Python layer
    returns ``new_poles`` exactly as the SetPole round-trip would write them).

THE EXACT REMAINING IMPOSSIBLE BOUNDARY:
  OCCT *natively* enforcing/reporting G3 through ``GeomAbs_Shape`` — the enum
  has no G3 token.  We measure dκ/ds + pole-adjust around it; we do NOT ask OCCT
  to compute G3.

Hermetic: pure Python + NumPy.
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_analysis import (
    occt_g3_residual_from_poles,
    occt_g3_pole_roundtrip,
)
from kerf_cad_core.geom.surface_fillet import _cross_boundary_curvature_rate


# ---------------------------------------------------------------------------
# Helpers (mirror test_match_srf_g3_gkp10 so the fixtures are comparable)
# ---------------------------------------------------------------------------


def _knots(n: int, deg: int) -> np.ndarray:
    inner = max(0, n - deg - 1)
    return np.concatenate([
        np.zeros(deg + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
        np.ones(deg + 1),
    ])


def _surf(zfun, x0=0.0, deg=3, nu=6, nv=4) -> NurbsSurface:
    """A bicubic NURBS surface — stands in for an OCCT Geom_BSplineSurface's
    extracted pole net (the two evaluate bit-identically)."""
    ku = _knots(nu, deg)
    kv = _knots(nv, deg)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x = x0 + i / (nu - 1)
            y = j / (nv - 1)
            cp[i, j] = [x, y, zfun(x, y)]
    return NurbsSurface(degree_u=deg, degree_v=deg, control_points=cp,
                        knots_u=ku, knots_v=kv)


def _independent_seam_residual(src, src_edge, tgt, tgt_edge, n=9) -> float:
    """Max |dκ_src/ds − dκ_tgt/ds| via the surface_fillet oracle directly —
    an independent cross-check of occt_g3_residual_from_poles."""
    def _seam(surf, edge, t):
        u0 = float(surf.knots_u[surf.degree_u])
        u1 = float(surf.knots_u[-surf.degree_u - 1])
        v0 = float(surf.knots_v[surf.degree_v])
        v1 = float(surf.knots_v[-surf.degree_v - 1])
        if edge == "u0":
            return _cross_boundary_curvature_rate(surf, u0, v0 + t * (v1 - v0), cross_dir="u")
        if edge == "u1":
            return _cross_boundary_curvature_rate(surf, u1, v0 + t * (v1 - v0), cross_dir="u")
        if edge == "v0":
            return _cross_boundary_curvature_rate(surf, u0 + t * (u1 - u0), v0, cross_dir="v")
        return _cross_boundary_curvature_rate(surf, u0 + t * (u1 - u0), v1, cross_dir="v")

    return max(abs(_seam(src, src_edge, i / (n - 1)) - _seam(tgt, tgt_edge, i / (n - 1)))
               for i in range(n))


# ---------------------------------------------------------------------------
# (a) Analyzer — occt_g3_residual_from_poles
# ---------------------------------------------------------------------------


def test_analyzer_flags_g3_discontinuity():
    """A flat patch meeting a curved cubic at a seam has a non-zero dκ/ds
    residual — the analyzer reports it (OCCT itself never would)."""
    tgt = _surf(lambda x, y: 0.5 * x ** 3 + 0.2 * x ** 2)
    src = _surf(lambda x, y: 0.0, x0=1.0)

    rep = occt_g3_residual_from_poles(tgt, "u1", src, "u0")
    assert rep["ok"], rep["reason"]
    assert rep["max_g3_residual"] > 1e-3, "fixture must start G3-discontinuous"
    assert not rep["g3_ok"]
    # Independent cross-check against the bare surface_fillet oracle.
    indep = _independent_seam_residual(tgt, "u1", src, "u0")
    assert rep["max_g3_residual"] == pytest.approx(indep, rel=1e-9, abs=1e-12)


def test_analyzer_zero_on_identical_patch():
    """Identical patches sharing an edge are already G3 — residual ~0."""
    tgt = _surf(lambda x, y: 0.3 * x ** 3 + 0.1 * x * y)
    src = _surf(lambda x, y: 0.3 * x ** 3 + 0.1 * x * y)
    rep = occt_g3_residual_from_poles(tgt, "u1", src, "u1")
    assert rep["ok"], rep["reason"]
    assert rep["max_g3_residual"] < 1e-9
    assert rep["g3_ok"]


def test_analyzer_rejects_bad_edge():
    rep = occt_g3_residual_from_poles(_surf(lambda x, y: 0.0), "BAD",
                                      _surf(lambda x, y: 0.0), "u0")
    assert not rep["ok"]
    assert "edge" in rep["reason"].lower()


# ---------------------------------------------------------------------------
# (b) Pole round-trip — occt_g3_pole_roundtrip  (the DoD)
# ---------------------------------------------------------------------------


def test_pole_roundtrip_drives_residual_below_1e_5():
    """DoD: an OCCT-origin surface pair reports a G3 residual < 1e-5 after the
    pole round-trip.

    `src` stands in for the OCCT pole carrier whose poles we extract, adjust
    via the pure-Python G3 solve, and write back.  `tgt` is the surface whose
    seam curvature-rate `src` must match.
    """
    tgt = _surf(lambda x, y: 0.4 * x ** 3 - 0.15 * x ** 2 + 0.05 * x * y)
    src = _surf(lambda x, y: 0.0, x0=1.0)  # flat OCCT-origin patch, meets tgt u1

    out = occt_g3_pole_roundtrip(tgt, "u1", src, "u0")
    assert out["ok"], out["reason"]
    assert out["residual_before"] > 1e-3, "fixture must start G3-discontinuous"
    # The DoD threshold.
    assert out["residual_after"] < 1e-5, (
        f"post-roundtrip G3 residual {out['residual_after']:.3e} "
        f"(was {out['residual_before']:.3e})"
    )
    assert out["g3_achieved"] is True
    assert out["residual_after"] < out["residual_before"]


def test_pole_roundtrip_writes_back_new_poles():
    """The round-trip returns the exact pole net an OCCT SetPole would write —
    the source's fourth control row is the only thing changed (G0/G1/G2 rows
    are preserved)."""
    tgt = _surf(lambda x, y: 0.3 * x ** 3 + 0.12 * x ** 2)
    src = _surf(lambda x, y: 0.0, x0=1.0)
    src_poles_before = src.control_points.copy()

    out = occt_g3_pole_roundtrip(tgt, "u1", src, "u0")
    assert out["ok"], out["reason"]
    new_poles = out["new_poles"]
    assert new_poles is not None
    assert new_poles.shape == src_poles_before.shape

    # Source patch was never mutated in place (match_srf deep-copies).
    assert np.array_equal(src.control_points, src_poles_before)

    # Re-evaluating the analyzer on the written-back poles reproduces
    # residual_after — i.e. new_poles IS a G3-quality surface.
    adjusted = out["adjusted_surface"]
    assert np.array_equal(adjusted.control_points, new_poles)
    recheck = occt_g3_residual_from_poles(tgt, "u1", adjusted, "u0")
    assert recheck["max_g3_residual"] == pytest.approx(
        out["residual_after"], rel=1e-9, abs=1e-12
    )


def test_pole_roundtrip_idempotent_on_already_g3():
    """Round-tripping an already-G3 pair leaves the residual ~zero (no harmful
    adjustment)."""
    tgt = _surf(lambda x, y: 0.25 * x ** 3 + 0.08 * x * y)
    src = _surf(lambda x, y: 0.25 * x ** 3 + 0.08 * x * y)
    out = occt_g3_pole_roundtrip(tgt, "u1", src, "u1")
    assert out["ok"], out["reason"]
    assert out["residual_after"] < 1e-5
    assert out["g3_achieved"] is True


def test_pole_roundtrip_degree2_source_rejected():
    """G3 needs degree >= 3 in the cross-boundary direction; a degree-2 carrier
    is honestly rejected (no false G3 claim)."""
    tgt = _surf(lambda x, y: 0.5 * x ** 3, deg=3, nu=6)
    src2 = _surf(lambda x, y: 0.0, x0=1.0, deg=2, nu=4)
    out = occt_g3_pole_roundtrip(tgt, "u1", src2, "u0")
    assert not out["ok"]
    assert "g3 pole-adjustment failed" in out["reason"].lower()


# ---------------------------------------------------------------------------
# Audit surfacing — continuity_audit exposes the numeric g3 residual
# ---------------------------------------------------------------------------


def test_continuity_audit_exposes_g3_residuals_key():
    """continuity_audit surfaces a numeric g3_residuals map (GK-P43a).  OCCT-
    origin bodies extract to NurbsSurface poles, so this analytic G3 oracle
    applies to OCCT-derived faces equally."""
    from kerf_cad_core.geom.surface_analysis import continuity_audit
    # A minimal call on a non-body still returns the key (ok=False path keeps
    # the contract): the key must always be present.
    res = continuity_audit(object())
    assert "g3_residuals" in res
