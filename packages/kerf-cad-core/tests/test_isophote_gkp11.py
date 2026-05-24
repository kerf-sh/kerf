"""GK-P11 — isophote / environment-map (EMap) analyser.

Isophotes are the level curves of the illumination scalar μ = n̂·L̂ — the
contours of constant lighting under a directional light.  The environment-map
(EMap) inspection used by CATIA FreeStyle and Rhino EMap reads them as iso-bands
on a unit sphere.  Because the field depends only on the normal *direction*, an
isophote band runs unbroken across a G1+ join but **snaps** across a G1
discontinuity (a crease): the normal jumps, so the band index jumps.

Oracle: an exact analytic illumination scalar μ = n̂·L̂ computed from analytic
surface normals, discretised into equal-angle environment-map bands.  The break
verdict is checked against constructed-geometry ground truth (creased vs smooth,
dihedral seam vs coplanar seam).

Hermetic: pure Python + NumPy.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_analysis import (
    isophote_analysis,
    isophote_continuity_analyser,
    _isophote_band,
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


def _tent_surface() -> NurbsSurface:
    """Piecewise-linear V-ridge (true G1 crease at x = 0.5)."""
    nu, nv = 5, 4
    ku, kv = _knots(nu, 1), _knots(nv, 1)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        x = i / (nu - 1)
        z = (0.5 - x) if x < 0.5 else (x - 0.5)
        for j in range(nv):
            cp[i, j] = [x, j / (nv - 1), z]
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cp,
                        knots_u=ku, knots_v=kv)


def _smooth_surface() -> NurbsSurface:
    """Gentle smooth (G2) parabolic patch — no creases."""
    nu, nv = 6, 5
    ku, kv = _knots(nu, 3), _knots(nv, 3)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x = i / (nu - 1)
            y = j / (nv - 1)
            cp[i, j] = [x, y, 0.15 * x * x]
    return NurbsSurface(degree_u=3, degree_v=3, control_points=cp,
                        knots_u=ku, knots_v=kv)


def _flat(origin, du, dv, deg=1, nu=2, nv=2) -> NurbsSurface:
    ku, kv = _knots(nu, deg), _knots(nv, deg)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = (np.array(origin, float)
                        + i * np.array(du, float) + j * np.array(dv, float))
    return NurbsSurface(degree_u=deg, degree_v=deg, control_points=cp,
                        knots_u=ku, knots_v=kv)


_TILT = [0.7, 0.0, 0.7]  # light that distinguishes the two crease half-normals


# ---------------------------------------------------------------------------
# Band oracle
# ---------------------------------------------------------------------------


def test_isophote_band_equal_angle():
    """Band index is monotone in the illumination angle θ = acos(μ)."""
    smr = 16
    # μ=1 (θ=0) → band 0; μ=−1 (θ=π) → band smr−1; μ=0 (θ=π/2) → middle.
    assert _isophote_band(1.0, smr) == 0
    assert _isophote_band(-1.0, smr) == smr - 1
    assert _isophote_band(0.0, smr) == smr // 2
    # Monotone non-decreasing as μ decreases.
    prev = -1
    for mu in np.linspace(1.0, -1.0, 64):
        b = _isophote_band(mu, smr)
        assert b >= prev
        prev = b


# ---------------------------------------------------------------------------
# DoD: detect an isophote break across a G1 discontinuity.
# ---------------------------------------------------------------------------


def test_isophote_detects_crease_break():
    tent = _tent_surface()
    r = isophote_analysis(tent, (41, 9), 16, light_dir=_TILT)
    assert r["ok"], r["reason"]
    assert r["has_break"], "crease must produce an isophote break"
    assert r["num_breaks"] > 0
    # The break must localise at the ridge column (x ≈ 0.5, mid-u).
    mask = r["isophote_break_mask"]
    us = r["us"]
    break_us = us[np.where(mask.any(axis=1))[0]]
    assert np.all(np.abs(break_us - 0.5) < 0.1), break_us


def test_isophote_no_break_on_smooth_surface():
    smooth = _smooth_surface()
    r = isophote_analysis(smooth, (40, 20), 16, light_dir=_TILT)
    assert r["ok"], r["reason"]
    assert not r["has_break"]
    assert r["num_breaks"] == 0


def test_isophote_symmetric_crease_invisible_under_axial_light():
    """Physical correctness: a symmetric V-ridge under top-down light has
    μ = n_z identical on both halves, so the isophote is genuinely continuous —
    the analyser must NOT report a spurious break."""
    tent = _tent_surface()
    r = isophote_analysis(tent, (41, 9), 16, light_dir=[0, 0, 1])
    assert r["ok"], r["reason"]
    assert not r["has_break"]


def test_mu_grid_matches_analytic_normal_dot_light():
    """μ_grid equals n̂·L̂ from analytic normals to machine precision."""
    smooth = _smooth_surface()
    L = np.array(_TILT) / np.linalg.norm(_TILT)
    r = isophote_analysis(smooth, (12, 12), 16, light_dir=_TILT)
    from kerf_cad_core.geom.surface_analysis import _analytic_curvature_data
    us, vs = r["us"], r["vs"]
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            cd = _analytic_curvature_data(smooth, float(u), float(v))
            if cd is None:
                continue
            expected = float(np.dot(cd["n"], L))
            assert abs(r["mu_grid"][i, j] - expected) < 1e-12


# ---------------------------------------------------------------------------
# Two-surface across-edge oracle (GK-38 analogue).
# ---------------------------------------------------------------------------


def test_isophote_seam_oracle_flags_dihedral_break():
    A = _flat([0, 0, 0], [0.5, 0, 0], [0, 1, 0])           # horizontal half
    B = _flat([0.5, 0, 0], [0.35, 0, 0.35], [0, 1, 0])     # tilted-up half
    edge = [[0.5, t, 0.0] for t in np.linspace(0, 1, 5)]
    o = isophote_continuity_analyser(A, B, edge, num_samples=9,
                                     sphere_map_res=16, light_dir=_TILT)
    assert o["ok"], o["reason"]
    assert o["continuity_grade"] == "below_G1"
    assert o["max_band_jump"] >= 2


def test_isophote_seam_oracle_passes_coplanar():
    A = _flat([0, 0, 0], [0.5, 0, 0], [0, 1, 0])
    B = _flat([0.5, 0, 0], [0.5, 0, 0], [0, 1, 0])         # coplanar with A
    edge = [[0.5, t, 0.0] for t in np.linspace(0, 1, 5)]
    o = isophote_continuity_analyser(A, B, edge, num_samples=9,
                                     sphere_map_res=16, light_dir=_TILT)
    assert o["ok"], o["reason"]
    assert o["continuity_grade"] == "G1+"
    assert o["max_band_jump"] == 0


def test_isophote_analysis_bad_input():
    r = isophote_analysis("not a surface", (10, 10), 16)
    assert not r["ok"]
