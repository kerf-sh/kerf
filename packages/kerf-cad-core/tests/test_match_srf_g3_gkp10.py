"""GK-P10 — MatchSrf G3 (curvature-rate / dκ/ds continuity).

``match_surface_edge`` previously topped out at G2 (normal-curvature matching).
GK-P10 adds ``continuity="G3"``: a fourth-control-row adjustment that drives the
source's cross-boundary arc-length curvature rate dκ/ds to the target's at the
seam.

Oracle: the analytic third-order NURBS curvature rate.  The independent
cross-check uses ``surface_fillet._cross_boundary_curvature_rate`` — the *same*
math that backs the GK-62 ``curvature_rate_continuity_residual`` G3 gate — so
the test verifies the matched edge passes the production G3 residual gate, not
merely the in-module verifier.

Hermetic: pure Python + NumPy.
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.match_srf import (
    match_surface_edge,
    verify_seam_g3_analytic,
)
from kerf_cad_core.geom.surface_fillet import _cross_boundary_curvature_rate


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


def _surf(zfun, x0=0.0, deg=3, nu=6, nv=4) -> NurbsSurface:
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


def _gate_residual_via_fillet_oracle(src, src_edge, tgt, tgt_edge,
                                     n=9) -> float:
    """Max |dκ_src/ds − dκ_tgt/ds| sampled along the seam using the
    surface_fillet third-derivative curvature-rate oracle (the GK-62 gate
    math), evaluated independently of match_srf's own verifier."""
    su0 = float(src.knots_u[src.degree_u])
    su1 = float(src.knots_u[-src.degree_u - 1])
    sv0 = float(src.knots_v[src.degree_v])
    sv1 = float(src.knots_v[-src.degree_v - 1])
    tu0 = float(tgt.knots_u[tgt.degree_u])
    tu1 = float(tgt.knots_u[-tgt.degree_u - 1])
    tv0 = float(tgt.knots_v[tgt.degree_v])
    tv1 = float(tgt.knots_v[-tgt.degree_v - 1])

    def _seam(surf, edge, t):
        u0 = float(surf.knots_u[surf.degree_u])
        u1 = float(surf.knots_u[-surf.degree_u - 1])
        v0 = float(surf.knots_v[surf.degree_v])
        v1 = float(surf.knots_v[-surf.degree_v - 1])
        if edge == "u0":
            return _cross_boundary_curvature_rate(surf, u0, v0 + t * (v1 - v0),
                                                  cross_dir="u")
        if edge == "u1":
            return _cross_boundary_curvature_rate(surf, u1, v0 + t * (v1 - v0),
                                                  cross_dir="u")
        if edge == "v0":
            return _cross_boundary_curvature_rate(surf, u0 + t * (u1 - u0), v0,
                                                  cross_dir="v")
        return _cross_boundary_curvature_rate(surf, u0 + t * (u1 - u0), v1,
                                              cross_dir="v")

    worst = 0.0
    for i in range(n):
        t = i / (n - 1)
        d = abs(_seam(src, src_edge, t) - _seam(tgt, tgt_edge, t))
        worst = max(worst, d)
    return worst


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_g3_added_to_valid_continuity():
    from kerf_cad_core.geom.match_srf import _VALID_CONTINUITY
    assert "G3" in _VALID_CONTINUITY


def test_g3_match_drives_residual_below_gate():
    """A flat source matched G3 to a curved (cubic) target's edge passes the
    analytic G3 residual gate."""
    tgt = _surf(lambda x, y: 0.5 * x ** 3 + 0.2 * x ** 2)
    src = _surf(lambda x, y: 0.0, x0=1.0)  # flat, meets tgt's u1 at its u0

    before = verify_seam_g3_analytic(src, "u0", tgt, "u1")
    assert before > 1e-3, "fixture must start G3-discontinuous"

    res = match_surface_edge(tgt, "u1", src, "u0", "G3")
    assert res.ok, res.reason
    assert res.continuity_achieved == "G3"
    assert res.max_curvature_rate_deviation < 1e-7

    # G0/G1/G2 stay clean (G3 must not break the lower orders).
    assert res.max_position_deviation < 1e-9
    assert res.max_tangent_deviation < 1e-7
    assert res.max_curvature_deviation < 1e-6


def test_g3_passes_independent_fillet_oracle_gate():
    """The matched edge passes the GK-62 dκ/ds gate computed by the
    *surface_fillet* curvature-rate oracle (independent of match_srf)."""
    tgt = _surf(lambda x, y: 0.4 * x ** 3 - 0.15 * x ** 2 + 0.05 * x * y)
    src = _surf(lambda x, y: 0.0, x0=1.0)

    before = _gate_residual_via_fillet_oracle(src, "u0", tgt, "u1")
    res = match_surface_edge(tgt, "u1", src, "u0", "G3")
    assert res.ok, res.reason
    after = _gate_residual_via_fillet_oracle(res.modified_surface, "u0",
                                             tgt, "u1")
    assert after < 1e-6, f"fillet-oracle G3 residual {after} (was {before})"
    assert after < before


def test_g3_requires_degree_3():
    """A degree-2 source cannot be matched at G3."""
    tgt = _surf(lambda x, y: 0.5 * x ** 3, deg=3, nu=6)
    src2 = _surf(lambda x, y: 0.0, x0=1.0, deg=2, nu=4)
    res = match_surface_edge(tgt, "u1", src2, "u0", "G3")
    assert not res.ok
    assert "degree" in res.reason.lower()


def test_g3_requires_four_source_rows():
    """A source with only 3 inward CP rows cannot satisfy G3."""
    tgt = _surf(lambda x, y: 0.5 * x ** 3, deg=3, nu=6)
    src = _surf(lambda x, y: 0.0, x0=1.0, deg=3, nu=4)  # exactly 4 rows OK...
    # build a 3-row source: nu must give only 3 rows in u → nu=3 invalid for
    # deg 3; instead match on the v edge of a surface with nv=3 (too few).
    src_thin = _surf(lambda x, y: 0.0, x0=1.0, deg=3, nu=6, nv=4)
    # v-direction has nv=4 rows; reduce by matching 'v0' on a nv=3 surface.
    # Use a degree-2 v with 3 rows to force the row-count guard.
    ku = _knots(6, 3)
    kv = _knots(3, 2)
    cp = np.zeros((6, 3, 3))
    for i in range(6):
        for j in range(3):
            cp[i, j] = [1.0 + i / 5.0, j / 2.0, 0.0]
    src3 = NurbsSurface(degree_u=3, degree_v=2, control_points=cp,
                        knots_u=ku, knots_v=kv)
    res = match_surface_edge(tgt, "v1", src3, "v0", "G3")
    assert not res.ok


def test_g3_identity_target_is_already_g3():
    """Matching a surface's edge to a geometrically-identical target yields a
    ~zero G3 correction (idempotence)."""
    tgt = _surf(lambda x, y: 0.3 * x ** 3 + 0.1 * x * y)
    # Source identical to target (same patch) → already G3 at the shared edge.
    src = _surf(lambda x, y: 0.3 * x ** 3 + 0.1 * x * y)
    res = match_surface_edge(tgt, "u1", src, "u1", "G3")
    assert res.ok, res.reason
    assert res.max_curvature_rate_deviation < 1e-7
