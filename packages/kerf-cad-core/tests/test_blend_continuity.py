"""GK-43 — Verified G1/G2 blend surface continuity tests.

Oracles
-------
* blend_srf_g1 : cross-boundary tangent residual ≤ 1e-7 (enforced by
  construction; actual should be < 1e-12 for analytic surfaces).
* blend_srf_g2 : cross-boundary tangent residual ≤ 1e-7 AND curvature
  residual ≤ 1e-7 (enforced by construction for planar/cylindrical supports;
  < 1e-10 for same-curvature pairs).

All tests are hermetic (no network, no OCCT, no external fixtures).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.blend_srf import (
    blend_srf_g1,
    blend_srf_g2,
    curvature_comb_continuity_residual,
)
from kerf_cad_core.geom.nurbs import NurbsSurface, surface_evaluate


# ---------------------------------------------------------------------------
# Surface factory helpers
# ---------------------------------------------------------------------------


def _clamped(n: int, degree: int) -> np.ndarray:
    inner = max(0, n - degree - 1)
    parts = [np.zeros(degree + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(degree + 1))
    return np.concatenate(parts)


def _make_plane(origin, x_axis, y_axis, *, nu: int = 6, nv: int = 6) -> NurbsSurface:
    """Bilinear (degree-1) or bicubic (degree-3) plane patch."""
    origin = np.asarray(origin, dtype=float)
    xa = np.asarray(x_axis, dtype=float)
    ya = np.asarray(y_axis, dtype=float)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = origin + (i / (nu - 1)) * xa + (j / (nv - 1)) * ya
    deg = min(3, nu - 1)
    degv = min(3, nv - 1)
    return NurbsSurface(
        degree_u=deg, degree_v=degv,
        control_points=cp,
        knots_u=_clamped(nu, deg),
        knots_v=_clamped(nv, degv),
    )


def _make_cylinder_surface(
    axis: str = "z",
    radius: float = 1.0,
    *,
    nu: int = 9,
    nv: int = 6,
    u_range: tuple = (0.0, math.pi / 2.0),
    v_range: tuple = (0.0, 1.0),
) -> NurbsSurface:
    """Non-rational cylinder surface patch (sufficient for curvature tests)."""
    u0, u1 = u_range
    v0, v1 = v_range
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        u = u0 + (u1 - u0) * i / (nu - 1)
        for j in range(nv):
            v = v0 + (v1 - v0) * j / (nv - 1)
            if axis == "z":
                cp[i, j] = [radius * math.cos(u), radius * math.sin(u), v]
            elif axis == "x":
                cp[i, j] = [v, radius * math.cos(u), radius * math.sin(u)]
            else:
                cp[i, j] = [radius * math.cos(u), v, radius * math.sin(u)]
    deg_u = min(3, nu - 1)
    deg_v = min(3, nv - 1)
    return NurbsSurface(
        degree_u=deg_u, degree_v=deg_v,
        control_points=cp,
        knots_u=_clamped(nu, deg_u),
        knots_v=_clamped(nv, deg_v),
    )


# ---------------------------------------------------------------------------
# GK-43 oracle tolerance
# ---------------------------------------------------------------------------

_TOL_G1 = 1e-7  # required cross-boundary tangent residual
_TOL_G2 = 1e-7  # required cross-boundary curvature residual


# ---------------------------------------------------------------------------
# blend_srf_g1 — enforced G1 tests
# ---------------------------------------------------------------------------


class TestBlendSrfG1:
    """blend_srf_g1 must enforce G1 (tangent continuity) by construction."""

    def _s1(self):
        return _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))

    def _s2(self):
        return _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))

    # --- basic API ---

    def test_returns_ok_dict_with_blend_surface(self):
        res = blend_srf_g1(self._s1(), self._s2(), edge="v1_v0", samples=12)
        assert res["ok"], res["reason"]
        assert isinstance(res["blend_surface"], NurbsSurface)

    def test_diagnostics_keys_present(self):
        res = blend_srf_g1(self._s1(), self._s2(), edge="v1_v0", samples=12)
        diag = res["diagnostics"]
        for k in ("max_g1_residual", "mean_g1_residual", "samples"):
            assert k in diag, f"missing key: {k}"

    def test_invalid_edge_rejected(self):
        res = blend_srf_g1(self._s1(), self._s2(), edge="bogus")
        assert res["ok"] is False
        assert "edge" in res["reason"].lower() or "unsupported" in res["reason"].lower()

    def test_nonpositive_blend_width_rejected(self):
        res = blend_srf_g1(self._s1(), self._s2(), blend_width=-1.0)
        assert res["ok"] is False

    def test_zero_blend_width_rejected(self):
        res = blend_srf_g1(self._s1(), self._s2(), blend_width=0.0)
        assert res["ok"] is False

    # --- G1 oracle: coplanar planes ---

    def test_g1_coplanar_planes_tangent_residual_le_tol(self):
        """Two coplanar planes: G1 residual must be ≤ 1e-7 (oracle)."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(s1, s2, edge="v1_v0", samples=16, blend_width=0.2)
        assert res["ok"]
        assert res["diagnostics"]["max_g1_residual"] <= _TOL_G1, (
            f"G1 residual {res['diagnostics']['max_g1_residual']:.2e} > {_TOL_G1}"
        )

    def test_g1_coplanar_planes_residual_near_machine_epsilon(self):
        """Coplanar planes: residual should be effectively zero (< 1e-12)."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(s1, s2, edge="v1_v0", samples=16)
        assert res["diagnostics"]["max_g1_residual"] < 1e-12

    def test_g1_perpendicular_planes_tangent_residual_le_tol(self):
        """Two perpendicular planes: G1 residual must be ≤ 1e-7 (oracle).

        Even though the two planes meet at 90°, the blend is constructed so
        its cross-boundary tangent at each seam matches the respective support.
        """
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 0, 1))
        res = blend_srf_g1(s1, s2, edge="v1_v0", samples=16, blend_width=0.3)
        assert res["ok"], res["reason"]
        assert res["diagnostics"]["max_g1_residual"] <= _TOL_G1, (
            f"G1 residual {res['diagnostics']['max_g1_residual']:.2e} > {_TOL_G1}"
        )

    def test_g1_cylinder_plane_junction_tangent_le_tol(self):
        """Cylinder seam to plane seam: G1 must hold ≤ 1e-7."""
        cyl = _make_cylinder_surface("z", radius=1.0, nv=6, v_range=(0.0, 1.0))
        # plane starts where cylinder ends at v=v_max
        v_max_cyl = float(cyl.knots_v[-cyl.degree_v - 1])
        pl = _make_plane((0, 0, v_max_cyl), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(cyl, pl, edge="v1_v0", samples=12, blend_width=0.15)
        assert res["ok"], res["reason"]
        assert res["diagnostics"]["max_g1_residual"] <= _TOL_G1, (
            f"G1 residual {res['diagnostics']['max_g1_residual']:.2e} > {_TOL_G1}"
        )

    def test_g1_u1_u0_edge_returns_surface(self):
        """'u1_u0' edge spec: blend must succeed and return a NurbsSurface."""
        # The curvature_comb_continuity_residual oracle is hardcoded for v1_v0;
        # here we verify construction only (surface is returned, ok=True).
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((1, 0, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(s1, s2, edge="u1_u0", samples=12, blend_width=0.2)
        assert res["ok"], res["reason"]
        assert isinstance(res["blend_surface"], NurbsSurface)

    def test_g1_u1_u0_tangent_continuity_direct(self):
        """'u1_u0' edge: verify G1 directly from blend derivatives (oracle bypass)."""
        from kerf_cad_core.geom.nurbs import surface_derivatives
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((1, 0, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(s1, s2, edge="u1_u0", samples=12, blend_width=0.2)
        blend = res["blend_surface"]
        # Blend seam A is at v=bv_min; surf1's seam is at u=u1_max.
        u1_max = float(s1.knots_u[-s1.degree_u - 1])
        v1_min = float(s1.knots_v[s1.degree_v])
        v1_max = float(s1.knots_v[-s1.degree_v - 1])
        bv_min = float(blend.knots_v[blend.degree_v])
        bu_min = float(blend.knots_u[blend.degree_u])
        bu_max = float(blend.knots_u[-blend.degree_u - 1])
        max_g1 = 0.0
        for t in np.linspace(0.0, 1.0, 8):
            # Parametric value along seam
            vs1_t = v1_min + (v1_max - v1_min) * t
            bu_t = bu_min + (bu_max - bu_min) * t
            # Blend's cross-boundary tangent at seam A: d/dv at v=bv_min
            SKL_b = np.asarray(surface_derivatives(blend, bu_t, bv_min, d=1), dtype=float)
            t_b = SKL_b[0, 1][:3]
            # Surf1's cross-boundary tangent at u=u1_max: d/du
            SKL_1 = np.asarray(surface_derivatives(s1, u1_max, vs1_t, d=1), dtype=float)
            t_1 = SKL_1[1, 0][:3]
            n_b, n_1 = np.linalg.norm(t_b), np.linalg.norm(t_1)
            if n_b > 1e-12 and n_1 > 1e-12:
                cross = float(np.linalg.norm(np.cross(t_b / n_b, t_1 / n_1)))
                max_g1 = max(max_g1, cross)
        assert max_g1 <= _TOL_G1, f"u1_u0 G1 residual {max_g1:.2e} > {_TOL_G1}"

    def test_g1_degree3_in_cross_boundary_direction(self):
        """Returned blend surface must be degree-3 in the cross-boundary (v) direction."""
        res = blend_srf_g1(self._s1(), self._s2(), edge="v1_v0", samples=12)
        assert res["blend_surface"].degree_v == 3

    def test_g1_seam_points_interpolated_at_corners(self):
        """Blend strip corner (clamped knots) must coincide with surf1's seam corner."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g1(s1, s2, edge="v1_v0", samples=12)
        blend = res["blend_surface"]
        u_min = float(blend.knots_u[blend.degree_u])
        u_max = float(blend.knots_u[-blend.degree_u - 1])
        v_min = float(blend.knots_v[blend.degree_v])
        # Surf1's seam corner at (u=0, v=1)
        p_blend = np.asarray(surface_evaluate(blend, u_min, v_min), dtype=float)[:3]
        p_s1 = np.asarray(surface_evaluate(s1, 0.0, 1.0), dtype=float)[:3]
        assert float(np.linalg.norm(p_blend - p_s1)) < 1e-9

    def test_g1_blend_width_changes_inner_control_positions(self):
        """Larger blend_width must move P1 (inner control) further from seam A."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 2, 0), (1, 0, 0), (0, 1, 0))
        res_narrow = blend_srf_g1(s1, s2, edge="v1_v0", samples=12, blend_width=0.1)
        res_wide = blend_srf_g1(s1, s2, edge="v1_v0", samples=12, blend_width=0.5)
        b_n = res_narrow["blend_surface"]
        b_w = res_wide["blend_surface"]
        # P1 is the second control row in v (index 1); its distance from P0
        # (seam A) should scale with blend_width.
        # P1 - P0 = (blend_width/3) * T1_hat; so |P1 - P0| scales with width.
        p0_n = b_n.control_points[0, 0, :3]
        p1_n = b_n.control_points[0, 1, :3]
        p0_w = b_w.control_points[0, 0, :3]
        p1_w = b_w.control_points[0, 1, :3]
        dist_n = float(np.linalg.norm(p1_n - p0_n))
        dist_w = float(np.linalg.norm(p1_w - p0_w))
        assert dist_w > dist_n


# ---------------------------------------------------------------------------
# blend_srf_g2 — enforced G2 tests
# ---------------------------------------------------------------------------


class TestBlendSrfG2:
    """blend_srf_g2 must enforce G1 AND G2 by construction."""

    def _s1(self):
        return _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))

    def _s2(self):
        return _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))

    # --- basic API ---

    def test_returns_ok_dict_with_blend_surface(self):
        res = blend_srf_g2(self._s1(), self._s2(), edge="v1_v0", samples=12)
        assert res["ok"], res["reason"]
        assert isinstance(res["blend_surface"], NurbsSurface)

    def test_diagnostics_keys_present(self):
        res = blend_srf_g2(self._s1(), self._s2(), edge="v1_v0", samples=12)
        diag = res["diagnostics"]
        for k in ("max_g1_residual", "max_g2_residual",
                  "mean_g1_residual", "mean_g2_residual", "samples"):
            assert k in diag, f"missing key: {k}"

    def test_invalid_edge_rejected(self):
        res = blend_srf_g2(self._s1(), self._s2(), edge="bogus")
        assert res["ok"] is False

    def test_nonpositive_blend_width_rejected(self):
        res = blend_srf_g2(self._s1(), self._s2(), blend_width=-0.5)
        assert res["ok"] is False

    def test_zero_blend_width_rejected(self):
        res = blend_srf_g2(self._s1(), self._s2(), blend_width=0.0)
        assert res["ok"] is False

    def test_degree5_in_cross_boundary_direction(self):
        """Returned blend surface must be degree-5 in the cross-boundary direction."""
        res = blend_srf_g2(self._s1(), self._s2(), edge="v1_v0", samples=12)
        assert res["blend_surface"].degree_v == 5

    # --- G1 oracle (G2 blend must also satisfy G1) ---

    def test_g2_coplanar_planes_g1_residual_le_tol(self):
        """G2 blend must still enforce G1 (≤ 1e-7) on coplanar planes."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=16, blend_width=0.2)
        assert res["ok"]
        assert res["diagnostics"]["max_g1_residual"] <= _TOL_G1, (
            f"G1 residual {res['diagnostics']['max_g1_residual']:.2e} > {_TOL_G1}"
        )

    def test_g2_perpendicular_planes_g1_residual_le_tol(self):
        """G2 blend between perpendicular planes: G1 must hold ≤ 1e-7."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 0, 1))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=16, blend_width=0.3)
        assert res["ok"]
        assert res["diagnostics"]["max_g1_residual"] <= _TOL_G1

    # --- G2 oracle: ENFORCED (analytic) ---

    def test_g2_coplanar_planes_g2_residual_le_tol(self):
        """Two coplanar planes: both have zero curvature; G2 residual ≤ 1e-7 (oracle)."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=16, blend_width=0.2)
        assert res["ok"]
        assert res["diagnostics"]["max_g2_residual"] <= _TOL_G2, (
            f"G2 residual {res['diagnostics']['max_g2_residual']:.2e} > {_TOL_G2}"
        )

    def test_g2_coplanar_planes_g2_residual_near_zero(self):
        """Coplanar planes have κ=0: G2 blend must achieve near-zero residual < 1e-10."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=16)
        assert res["diagnostics"]["max_g2_residual"] < 1e-10

    def test_g2_two_same_curvature_cylinders_g2_le_tol(self):
        """Two cylinder patches with the same curvature: G2 residual ≤ 1e-7 (oracle).

        Both cylinder patches have κ = 1/r in the cross-boundary (v) direction.
        The G2 blend must match curvature at both seams.
        """
        r = 1.5
        cyl1 = _make_cylinder_surface("z", radius=r, nv=8, v_range=(0.0, 1.0))
        cyl2 = _make_cylinder_surface("z", radius=r, nv=8, v_range=(1.0, 2.0))
        res = blend_srf_g2(cyl1, cyl2, edge="v1_v0", samples=16, blend_width=0.2)
        assert res["ok"], res["reason"]
        assert res["diagnostics"]["max_g2_residual"] <= _TOL_G2, (
            f"G2 residual {res['diagnostics']['max_g2_residual']:.2e} > {_TOL_G2}"
        )

    def test_g2_plane_to_plane_g2_residual_finite_and_le_tol(self):
        """Two planes with same orientation: G2 residual ≤ 1e-7 (oracle)."""
        s1 = _make_plane((0, 0, 0), (2, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (2, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=12, blend_width=0.15)
        assert res["ok"]
        diag = res["diagnostics"]
        assert math.isfinite(diag["max_g2_residual"])
        assert diag["max_g2_residual"] <= _TOL_G2

    def test_g2_u1_u0_edge_returns_surface_and_g1_g2_direct(self):
        """'u1_u0' edge: verify G1 and G2 directly (oracle bypass — oracle
        is hardcoded for v1_v0 edge direction)."""
        from kerf_cad_core.geom.nurbs import surface_derivatives, surface_normal
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((1, 0, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="u1_u0", samples=12, blend_width=0.2)
        assert res["ok"], res["reason"]
        assert isinstance(res["blend_surface"], NurbsSurface)
        blend = res["blend_surface"]
        u1_max = float(s1.knots_u[-s1.degree_u - 1])
        v1_min = float(s1.knots_v[s1.degree_v])
        v1_max = float(s1.knots_v[-s1.degree_v - 1])
        bv_min = float(blend.knots_v[blend.degree_v])
        bu_min = float(blend.knots_u[blend.degree_u])
        bu_max = float(blend.knots_u[-blend.degree_u - 1])
        max_g1 = 0.0
        max_g2 = 0.0
        for t in np.linspace(0.0, 1.0, 8):
            vs1_t = v1_min + (v1_max - v1_min) * t
            bu_t = bu_min + (bu_max - bu_min) * t
            SKL_b = np.asarray(surface_derivatives(blend, bu_t, bv_min, d=2), dtype=float)
            SKL_1 = np.asarray(surface_derivatives(s1, u1_max, vs1_t, d=2), dtype=float)
            t_b = SKL_b[0, 1][:3]   # blend's d/dv at seam A
            t_1 = SKL_1[1, 0][:3]   # surf1's d/du at seam
            n_b, n_1 = np.linalg.norm(t_b), np.linalg.norm(t_1)
            if n_b > 1e-12 and n_1 > 1e-12:
                max_g1 = max(max_g1, float(np.linalg.norm(np.cross(t_b / n_b, t_1 / n_1))))
            # G2 check: curvature in cross-boundary direction
            n_blend_v = np.asarray(surface_normal(blend, bu_t, bv_min), dtype=float)[:3]
            n_s1 = np.asarray(surface_normal(s1, u1_max, vs1_t), dtype=float)[:3]
            S1v_sq = max(float(np.dot(t_1, t_1)), 1e-30)
            kappa_s1 = float(np.dot(SKL_1[2, 0][:3], n_s1)) / S1v_sq
            bv_sq = max(float(np.dot(t_b, t_b)), 1e-30)
            kappa_b = float(np.dot(SKL_b[0, 2][:3], n_blend_v)) / bv_sq
            max_g2 = max(max_g2, abs(kappa_b - kappa_s1))
        assert max_g1 <= _TOL_G1, f"u1_u0 G1 residual {max_g1:.2e} > {_TOL_G1}"
        assert max_g2 <= _TOL_G2, f"u1_u0 G2 residual {max_g2:.2e} > {_TOL_G2}"

    def test_g2_blend_seam_corners_interpolated(self):
        """Blend strip (clamped knots): corner must coincide with surf1's seam corner."""
        s1 = _make_plane((0, 0, 0), (1, 0, 0), (0, 1, 0))
        s2 = _make_plane((0, 1, 0), (1, 0, 0), (0, 1, 0))
        res = blend_srf_g2(s1, s2, edge="v1_v0", samples=12)
        blend = res["blend_surface"]
        u_min = float(blend.knots_u[blend.degree_u])
        v_min = float(blend.knots_v[blend.degree_v])
        p_blend = np.asarray(surface_evaluate(blend, u_min, v_min), dtype=float)[:3]
        p_s1 = np.asarray(surface_evaluate(s1, 0.0, 1.0), dtype=float)[:3]
        assert float(np.linalg.norm(p_blend - p_s1)) < 1e-9


# ---------------------------------------------------------------------------
# Cross-check: blend_srf_g2 G2 residual is smaller than naive G1 blend
# ---------------------------------------------------------------------------


class TestG2VsG1Comparison:
    """G2 blend must achieve lower curvature residual than a G1 blend
    on surfaces where the support curvature is nonzero."""

    def test_cylinder_g2_residual_le_g1_residual(self):
        """For a cylinder seam, the G2 blend must match curvature better
        than a G1 blend that ignores curvature constraints."""
        r = 2.0
        cyl1 = _make_cylinder_surface("z", radius=r, nv=8, v_range=(0.0, 1.0))
        cyl2 = _make_cylinder_surface("z", radius=r, nv=8, v_range=(1.0, 2.0))

        res_g1 = blend_srf_g1(cyl1, cyl2, edge="v1_v0", samples=12)
        res_g2 = blend_srf_g2(cyl1, cyl2, edge="v1_v0", samples=12)

        # Compute G2 residual for the G1 blend (for comparison)
        g2_of_g1 = curvature_comb_continuity_residual(
            res_g1["blend_surface"], cyl1, cyl2,
            edge="v1_v0", continuity="G2", samples=8,
        )

        assert res_g2["diagnostics"]["max_g2_residual"] <= _TOL_G2
        # The G2 blend should achieve lower or equal curvature residual than
        # the G1 blend (which doesn't constrain curvature).
        assert (
            res_g2["diagnostics"]["max_g2_residual"]
            <= g2_of_g1["max_g2_residual"] + 1e-12
        )
