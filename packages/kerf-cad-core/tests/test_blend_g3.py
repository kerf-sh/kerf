"""GK-62 — blend_srf_g3: degree-7 Bezier strip with analytic G3 enforcement.

Verifies the new ``blend_srf_g3`` function added to ``geom/blend_srf.py``:

  * Importable from ``blend_srf`` and ``geom`` package.
  * Returns a degree-7 NurbsSurface (8 CP rows in v).
  * G3 oracle (``curvature_rate_continuity_residual``) residual < 1e-5 for
    both seams on flat-plane and cubic-z surfaces.
  * G0 boundary interpolation: seam curves lie on the support seams to 1e-9.
  * Does NOT break blend_srf_g1 (additive — both co-exist).
  * Rejects blend_dist ≤ 0 with ValueError.
  * Third-derivative continuity verified via the analytic oracle on both seams.

All tests are hermetic: no network, no OCCT, no external fixtures.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_evaluate
from kerf_cad_core.geom.surface_fillet import (
    curvature_comb_continuity_residual,
    curvature_rate_continuity_residual,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _clamped(n: int, degree: int) -> np.ndarray:
    inner = max(0, n - degree - 1)
    parts = [np.zeros(degree + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(degree + 1))
    return np.concatenate(parts)


def _plane_surface(
    origin=(0.0, 0.0, 0.0),
    x_axis=(1.0, 0.0, 0.0),
    y_axis=(0.0, 1.0, 0.0),
    nu: int = 5,
    nv: int = 5,
    degree: int = 3,
) -> NurbsSurface:
    """A flat NURBS plane patch with nu×nv control points."""
    origin = np.asarray(origin, dtype=float)
    xa = np.asarray(x_axis, dtype=float)
    ya = np.asarray(y_axis, dtype=float)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = origin + (i / (nu - 1)) * xa + (j / (nv - 1)) * ya
    deg = min(degree, nu - 1, nv - 1)
    return NurbsSurface(
        degree_u=deg, degree_v=deg,
        control_points=cp,
        knots_u=_clamped(nu, deg),
        knots_v=_clamped(nv, deg),
    )


def _cubic_z_surface(amplitude: float = 0.1, nu: int = 5) -> NurbsSurface:
    """S(u,v) = (u, v, A*v^3) — degree-3 Bezier in v with non-zero dκ/ds."""
    nv = 4
    nu_use = max(nu, 4)
    cp = np.zeros((nu_use, nv, 3))
    v_cp = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
    z_cp = [0.0, 0.0, 0.0, amplitude]
    for i in range(nu_use):
        u = i / (nu_use - 1)
        for j in range(nv):
            cp[i, j] = np.array([u, v_cp[j], z_cp[j]])
    deg_u = min(3, nu_use - 1)
    return NurbsSurface(
        degree_u=deg_u, degree_v=3,
        control_points=cp,
        knots_u=_clamped(nu_use, deg_u),
        knots_v=_clamped(nv, 3),
    )


def _reverse_cubic_z_surface(amplitude: float = 0.1, nu: int = 5) -> NurbsSurface:
    """S(u,v) = (u, v, A*(1-v)^3) — reverse cubic, v=0 meets cubic's v=1."""
    nv = 4
    nu_use = max(nu, 4)
    cp = np.zeros((nu_use, nv, 3))
    v_cp = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
    z_cp = [amplitude, 2.0 * amplitude / 3.0, amplitude / 3.0, 0.0]
    for i in range(nu_use):
        u = i / (nu_use - 1)
        for j in range(nv):
            cp[i, j] = np.array([u, v_cp[j], z_cp[j]])
    deg_u = min(3, nu_use - 1)
    return NurbsSurface(
        degree_u=deg_u, degree_v=3,
        control_points=cp,
        knots_u=_clamped(nu_use, deg_u),
        knots_v=_clamped(nv, 3),
    )


# ---------------------------------------------------------------------------
# 1. Import and API contract
# ---------------------------------------------------------------------------


class TestImportContract:
    def test_blend_srf_g3_importable_from_blend_srf_module(self):
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        assert callable(blend_srf_g3)

    def test_blend_srf_g3_importable_from_geom_package(self):
        from kerf_cad_core.geom import blend_srf_g3
        assert callable(blend_srf_g3)

    def test_blend_srf_g3_in_geom_all(self):
        import kerf_cad_core.geom as geom
        assert "blend_srf_g3" in geom.__all__

    def test_blend_srf_g1_still_importable(self):
        """GK-43 blend_srf_g1 must NOT be broken by adding blend_srf_g3."""
        from kerf_cad_core.geom.blend_srf import blend_srf_g1
        assert callable(blend_srf_g1)

    def test_blend_srf_g3_returns_nurbs_surface(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        result = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        assert isinstance(result, NurbsSurface)

    def test_blend_srf_g3_degree_v_is_7(self):
        """Cross-boundary direction must be degree 7 (8 control rows = G3 at both ends)."""
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        result = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        assert result.degree_v == 7, (
            f"Expected degree_v=7 for G3 strip, got {result.degree_v}"
        )

    def test_blend_srf_g3_has_8_cp_rows_in_v(self):
        """8 control rows in v are required to enforce G3 at both seams."""
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        result = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        assert result.num_control_points_v == 8, (
            f"Expected 8 CP rows in v, got {result.num_control_points_v}"
        )


# ---------------------------------------------------------------------------
# 2. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_zero_blend_dist_raises_value_error(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        with pytest.raises(ValueError):
            blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.0)

    def test_negative_blend_dist_raises_value_error(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        with pytest.raises(ValueError):
            blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=-0.5)


# ---------------------------------------------------------------------------
# 3. G0 boundary interpolation
# ---------------------------------------------------------------------------


class TestG0BoundaryInterpolation:
    """The blend's v=bv_min iso-curve must lie on surf1's seam and
    v=bv_max iso-curve must lie on surf2's seam (to 1e-9)."""

    def test_seam_a_on_surf1_seam_flat_planes(self):
        s1 = _plane_surface(origin=(0.0, 0.0, 0.0))
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=10)
        bu_min = float(blend.knots_u[blend.degree_u])
        bu_max = float(blend.knots_u[-blend.degree_u - 1])
        bv_min = float(blend.knots_v[blend.degree_v])
        max_err = 0.0
        for t in np.linspace(0.0, 1.0, 20):
            bu = bu_min + (bu_max - bu_min) * t
            p = np.asarray(surface_evaluate(blend, bu, bv_min), dtype=float)[:3]
            err = max(abs(p[1] - 1.0), abs(p[2] - 0.0))
            max_err = max(max_err, err)
        assert max_err < 1e-9, (
            f"Blend seam A not on surf1's seam (y=1, z=0): max_err={max_err:.2e}"
        )

    def test_seam_b_on_surf2_seam_flat_planes(self):
        s1 = _plane_surface(origin=(0.0, 0.0, 0.0))
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=10)
        bu_min = float(blend.knots_u[blend.degree_u])
        bu_max = float(blend.knots_u[-blend.degree_u - 1])
        bv_max = float(blend.knots_v[-blend.degree_v - 1])
        max_err = 0.0
        for t in np.linspace(0.0, 1.0, 20):
            bu = bu_min + (bu_max - bu_min) * t
            p = np.asarray(surface_evaluate(blend, bu, bv_max), dtype=float)[:3]
            err = max(abs(p[1] - 1.0), abs(p[2] - 0.0))
            max_err = max(max_err, err)
        assert max_err < 1e-9, (
            f"Blend seam B not on surf2's seam (y=1, z=0): max_err={max_err:.2e}"
        )

    def test_seam_a_on_cubic_z_seam(self):
        amp = 0.1
        s1 = _cubic_z_surface(amplitude=amp)
        s2 = _plane_surface(origin=(0.0, 1.0, amp))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=3, edge2_idx=0, blend_dist=0.15, samples=10)
        bu_min = float(blend.knots_u[blend.degree_u])
        bu_max = float(blend.knots_u[-blend.degree_u - 1])
        bv_min = float(blend.knots_v[blend.degree_v])
        max_err = 0.0
        for t in np.linspace(0.0, 1.0, 20):
            bu = bu_min + (bu_max - bu_min) * t
            p = np.asarray(surface_evaluate(blend, bu, bv_min), dtype=float)[:3]
            err = max(abs(p[1] - 1.0), abs(p[2] - amp))
            max_err = max(max_err, err)
        assert max_err < 1e-9, (
            f"Blend seam A not on cubic seam (y=1, z={amp}): max_err={max_err:.2e}"
        )


# ---------------------------------------------------------------------------
# 4. G3 oracle — flat planes (κ = 0, dκ/ds = 0 everywhere)
# ---------------------------------------------------------------------------


class TestG3OracleFlatPlanes:
    """For two coplanar flat surfaces the G3 oracle residual must be near zero."""

    def test_g3_oracle_residual_flat_planes(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=12)
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        assert oracle["max_g3_residual"] < 1e-5, (
            f"Oracle G3 residual for flat planes = {oracle['max_g3_residual']:.2e}"
        )

    def test_g1_oracle_residual_flat_planes(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=12)
        g12 = curvature_comb_continuity_residual(
            blend, s1, s2, edge="v1_v0", continuity="G2", samples=12,
        )
        assert g12["max_g1_residual"] < 1e-9, (
            f"G1 residual for flat planes = {g12['max_g1_residual']:.2e}"
        )

    def test_g2_oracle_residual_flat_planes(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=12)
        g12 = curvature_comb_continuity_residual(
            blend, s1, s2, edge="v1_v0", continuity="G2", samples=12,
        )
        assert g12["max_g2_residual"] < 1e-9, (
            f"G2 residual for flat planes = {g12['max_g2_residual']:.2e}"
        )

    def test_seam_a_and_b_g3_both_below_gate_flat(self):
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=12)
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        for r in oracle["seam_a_g3"]:
            assert r < 1e-5, f"seam_a_g3 entry {r:.2e} exceeds 1e-5"
        for r in oracle["seam_b_g3"]:
            assert r < 1e-5, f"seam_b_g3 entry {r:.2e} exceeds 1e-5"


# ---------------------------------------------------------------------------
# 5. G3 oracle — cubic×cubic (non-trivial curvature rate)
# ---------------------------------------------------------------------------


class TestG3OracleCubicSurfaces:
    """Two cubic-z surfaces with amplitude A=0.1; dκ/ds at the seam ≠ 0."""

    @staticmethod
    def _build(amp: float = 0.1):
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        s1 = _cubic_z_surface(amplitude=amp)
        s2 = _reverse_cubic_z_surface(amplitude=amp)
        blend = blend_srf_g3(s1, s2, edge1_idx=3, edge2_idx=0,
                             blend_dist=0.15, samples=12)
        return s1, s2, blend

    def test_g3_oracle_residual_cubic_cubic(self):
        s1, s2, blend = self._build()
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        assert oracle["max_g3_residual"] < 1e-5, (
            f"G3 oracle for cubic×cubic = {oracle['max_g3_residual']:.2e}"
        )

    def test_g1_oracle_residual_cubic_cubic(self):
        s1, s2, blend = self._build()
        g12 = curvature_comb_continuity_residual(
            blend, s1, s2, edge="v1_v0", continuity="G2", samples=12,
        )
        assert g12["max_g1_residual"] < 1e-5, (
            f"G1 residual for cubic×cubic = {g12['max_g1_residual']:.2e}"
        )

    def test_g2_oracle_residual_cubic_cubic(self):
        s1, s2, blend = self._build()
        g12 = curvature_comb_continuity_residual(
            blend, s1, s2, edge="v1_v0", continuity="G2", samples=12,
        )
        assert g12["max_g2_residual"] < 1e-5, (
            f"G2 residual for cubic×cubic = {g12['max_g2_residual']:.2e}"
        )

    def test_seam_a_g3_below_gate_cubic(self):
        s1, s2, blend = self._build()
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        for r in oracle["seam_a_g3"]:
            assert r < 1e-5, f"seam_a_g3 entry {r:.2e} exceeds 1e-5"

    def test_seam_b_g3_below_gate_cubic(self):
        s1, s2, blend = self._build()
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        for r in oracle["seam_b_g3"]:
            assert r < 1e-5, f"seam_b_g3 entry {r:.2e} exceeds 1e-5"

    @pytest.mark.parametrize("amp", [0.05, 0.1, 0.2])
    def test_g3_gate_across_amplitudes(self, amp: float):
        s1, s2, blend = self._build(amp)
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=12,
        )
        assert oracle["max_g3_residual"] < 1e-5, (
            f"G3 oracle for amp={amp}: {oracle['max_g3_residual']:.2e}"
        )


# ---------------------------------------------------------------------------
# 6. Third-derivative continuity: analytic oracle confirms seam-by-seam
# ---------------------------------------------------------------------------


class TestThirdDerivativeContinuity:
    """Verify d³S/dv³ continuity (G3) across the join via the T-104a analytic
    oracle.  The oracle computes dκ/ds at each seam sample and compares the
    blend's value against the support surface.  We check that:

      * max_g3_residual < 1e-5 (the DoD gate).
      * seam_a_g3 and seam_b_g3 per-sample lists are both below 1e-5.
    """

    def test_third_deriv_continuity_flat_planes_oracle(self):
        """Oracle confirms G3 (third-derivative / curvature-rate) for flat planes."""
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2, samples=12)
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=16,
        )
        assert oracle["max_g3_residual"] < 1e-5, (
            f"Oracle G3 (flat planes) = {oracle['max_g3_residual']:.2e}"
        )
        for r in oracle["seam_a_g3"]:
            assert r < 1e-5, f"seam_a_g3 entry {r:.2e} > 1e-5"
        for r in oracle["seam_b_g3"]:
            assert r < 1e-5, f"seam_b_g3 entry {r:.2e} > 1e-5"

    def test_third_deriv_continuity_cubic_surfaces_oracle(self):
        """Oracle confirms G3 (third-derivative / curvature-rate) for cubic×cubic."""
        s1 = _cubic_z_surface(amplitude=0.1)
        s2 = _reverse_cubic_z_surface(amplitude=0.1)
        from kerf_cad_core.geom.blend_srf import blend_srf_g3
        blend = blend_srf_g3(s1, s2, edge1_idx=3, edge2_idx=0, blend_dist=0.15, samples=12)
        oracle = curvature_rate_continuity_residual(
            blend, s1, s2, edge="v1_v0", samples=16,
        )
        assert oracle["max_g3_residual"] < 1e-5, (
            f"Oracle G3 (cubic) = {oracle['max_g3_residual']:.2e}"
        )
        for r in oracle["seam_a_g3"]:
            assert r < 1e-5, f"seam_a_g3 entry {r:.2e} > 1e-5"
        for r in oracle["seam_b_g3"]:
            assert r < 1e-5, f"seam_b_g3 entry {r:.2e} > 1e-5"


# ---------------------------------------------------------------------------
# 7. blend_srf_g1 not broken (GK-43 non-regression)
# ---------------------------------------------------------------------------


class TestGK43NonRegression:
    """blend_srf_g1 must continue to work after adding blend_srf_g3."""

    def test_blend_srf_g1_still_works_flat(self):
        from kerf_cad_core.geom.blend_srf import blend_srf_g1
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        result = blend_srf_g1(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        assert isinstance(result, NurbsSurface)

    def test_blend_srf_g1_g3_coexist(self):
        """Both blend_srf_g1 and blend_srf_g3 importable and functional simultaneously."""
        from kerf_cad_core.geom.blend_srf import blend_srf_g1, blend_srf_g3
        s1 = _plane_surface()
        s2 = _plane_surface(origin=(0.0, 1.0, 0.0))
        r1 = blend_srf_g1(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        r3 = blend_srf_g3(s1, s2, edge1_idx=4, edge2_idx=0, blend_dist=0.2)
        assert isinstance(r1, NurbsSurface)
        assert isinstance(r3, NurbsSurface)
        # G3 strip has more control rows than G1 strip
        assert r3.num_control_points_v == 8
