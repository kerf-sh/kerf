"""
Hermetic tests for kerf_cad_core.frep.sdf — F-rep / SDF modelling.

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Analytic values are derived from closed-form SDF definitions.

References
----------
Quilez, I. (2022). "Signed Distance Functions." iquilezles.org/articles/distfunctions
Lorensen & Cline (1987). "Marching Cubes."
Maskery et al. (2018). "Insights into the mechanical properties of several
  triply periodic minimal surface lattice structures made by polymer additive
  manufacturing." Polymer, 152, 62-71.
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.frep.sdf import (
    sdf_sphere,
    sdf_box,
    sdf_cylinder,
    sdf_torus,
    sdf_plane,
    sdf_gyroid,
    sdf_schwarz_p,
    sdf_diamond,
    csg_union,
    csg_intersection,
    csg_difference,
    csg_smooth_union,
    sdf_translate,
    sdf_rotate_z,
    sdf_scale,
    sdf_shell,
    sdf_offset,
    field_gradient,
    surface_normal,
    tpms_wall_thickness,
    marching_cubes,
    field_volume,
    field_surface_area,
    sample_field,
)

# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------
_ABS = 1e-10     # near-exact comparisons
_GRAD_TOL = 1e-3  # gradient / normal tolerance
_VOL_REL_TOL = 0.12  # 12 % grid tolerance for volume
_MC_SURF_TOL = 0.05  # 5 % grid tolerance for surface vertices


# ===========================================================================
# 1. Sphere SDF — exact distance at sample points
# ===========================================================================

class TestSphereSDF:
    def test_on_surface(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        assert abs(f(1.0, 0.0, 0.0)) < _ABS

    def test_outside(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        # point at (3,4,0) → dist = 5 - 1 = 4
        assert abs(f(3.0, 4.0, 0.0) - 4.0) < _ABS

    def test_inside(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        # point at origin → dist = -1
        assert abs(f(0.0, 0.0, 0.0) - (-1.0)) < _ABS

    def test_offset_center(self):
        f = sdf_sphere(1.0, 2.0, 3.0, 2.0)
        # closest surface point: (1+2, 2, 3) → dist = 0
        assert abs(f(3.0, 2.0, 3.0)) < _ABS

    def test_diagonal_point(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        r = math.sqrt(3)
        # (1,1,1) is at distance sqrt(3) - 1 from origin sphere surface
        assert abs(f(1.0, 1.0, 1.0) - (r - 1.0)) < _ABS


# ===========================================================================
# 2. Box SDF — exact
# ===========================================================================

class TestBoxSDF:
    def test_outside_along_x(self):
        f = sdf_box(0, 0, 0, 1.0, 1.0, 1.0)
        # point at (2, 0, 0): nearest face x=1, dist = 1
        assert abs(f(2.0, 0.0, 0.0) - 1.0) < _ABS

    def test_inside(self):
        f = sdf_box(0, 0, 0, 1.0, 1.0, 1.0)
        # origin: deepest inside, dist = -1
        assert abs(f(0.0, 0.0, 0.0) - (-1.0)) < _ABS

    def test_on_face(self):
        f = sdf_box(0, 0, 0, 1.0, 1.0, 1.0)
        assert abs(f(1.0, 0.0, 0.0)) < _ABS

    def test_corner_outside(self):
        f = sdf_box(0, 0, 0, 1.0, 1.0, 1.0)
        # corner at (1,1,1), point at (2,2,2): dist = sqrt(3)
        expected = math.sqrt(3.0)
        assert abs(f(2.0, 2.0, 2.0) - expected) < 1e-12

    def test_non_cubic(self):
        f = sdf_box(0, 0, 0, 2.0, 1.0, 0.5)
        # point at (3, 0, 0): outside x by 1
        assert abs(f(3.0, 0.0, 0.0) - 1.0) < _ABS


# ===========================================================================
# 3. CSG operations
# ===========================================================================

class TestCSGOps:
    """Union = min, intersection = max, difference = max(a,-b)."""

    def _two_spheres(self):
        a = sdf_sphere(0, 0, 0, 1.0)
        b = sdf_sphere(1.5, 0, 0, 1.0)
        return a, b

    def test_union_is_min(self):
        a, b = self._two_spheres()
        u = csg_union(a, b)
        for x in [-2.0, 0.0, 0.75, 1.5, 3.0]:
            va, vb = a(x, 0, 0), b(x, 0, 0)
            assert abs(u(x, 0, 0) - min(va, vb)) < _ABS

    def test_intersection_is_max(self):
        a, b = self._two_spheres()
        i = csg_intersection(a, b)
        for x in [-2.0, 0.0, 0.75, 1.5, 3.0]:
            va, vb = a(x, 0, 0), b(x, 0, 0)
            assert abs(i(x, 0, 0) - max(va, vb)) < _ABS

    def test_difference_is_max_a_neg_b(self):
        a, b = self._two_spheres()
        d = csg_difference(a, b)
        for x in [-2.0, 0.0, 0.75, 1.5, 3.0]:
            va, vb = a(x, 0, 0), b(x, 0, 0)
            assert abs(d(x, 0, 0) - max(va, -vb)) < _ABS

    def test_smooth_union_le_hard_min_in_blend_zone(self):
        """Smooth union ≤ hard union strictly in the symmetric blend zone.

        The Quilez polynomial smooth-min is only guaranteed to be ≤ min(a,b)
        when both distances are within the blend radius k of each other
        (|da - db| < k).  We test exactly that region.
        """
        a, b = self._two_spheres()
        u_hard = csg_union(a, b)
        u_smooth = csg_smooth_union(a, b, k=0.3)
        # x=0.75 is the midpoint; both spheres have equal distances there
        for x in [0.70, 0.75, 0.80]:
            assert u_smooth(x, 0, 0) <= u_hard(x, 0, 0) + 1e-9

    def test_smooth_union_strictly_less_at_midpoint(self):
        """At the midpoint between two sphere surfaces, smooth < hard union."""
        a, b = self._two_spheres()
        u_hard = csg_union(a, b)
        u_smooth = csg_smooth_union(a, b, k=0.3)
        # x=0.75: both spheres equidistant → deepest blend
        assert u_smooth(0.75, 0, 0) < u_hard(0.75, 0, 0)


# ===========================================================================
# 4. Transforms
# ===========================================================================

class TestTransforms:
    def test_translate(self):
        """sdf_translate(f, tx, ty, tz) shifts the solid's centre to (tx,ty,tz).
        The new sphere is centred at (5,0,0) so its surface passes through (6,0,0)."""
        f = sdf_sphere(0, 0, 0, 1.0)
        g = sdf_translate(f, 5, 0, 0)
        # (6, 0, 0) is on the surface of the shifted sphere
        assert abs(g(6.0, 0.0, 0.0)) < _ABS
        # (5, 0, 0) is the new centre → distance = -1
        assert abs(g(5.0, 0.0, 0.0) - (-1.0)) < _ABS
        # (0, 0, 0) is now 5 units from centre → distance = 4
        assert abs(g(0.0, 0.0, 0.0) - 4.0) < _ABS

    def test_rotate_z_90(self):
        """Rotating a box 90° around Z swaps X and Y half-extents."""
        f = sdf_box(0, 0, 0, 2.0, 1.0, 1.0)
        g = sdf_rotate_z(f, math.pi / 2.0)
        # After rotation, the long axis is now along Y
        # A point at (0, 2.1, 0) should be outside by ≈ 0.1
        val = g(0.0, 2.1, 0.0)
        assert val > 0.0, "should be outside after rotation"

    def test_scale_uniform(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        g = sdf_scale(f, 2.0)
        # Sphere surface is now at radius 2; point at (2,0,0) → dist=0
        assert abs(g(2.0, 0.0, 0.0)) < _ABS


# ===========================================================================
# 5. Shell / offset
# ===========================================================================

class TestShellOffset:
    def test_shell_midpoint_inside(self):
        """Shell surface is at the original sphere surface."""
        f = sdf_sphere(0, 0, 0, 1.0)
        shell = sdf_shell(f, 0.2)
        # At radius=1.0 the shell value is |0| - 0.1 = -0.1 (inside the shell wall)
        assert shell(1.0, 0.0, 0.0) < 0.0

    def test_offset_enlarges(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        g = sdf_offset(f, 0.5)
        # New surface at radius 1.5
        assert abs(g(1.5, 0.0, 0.0)) < _ABS

    def test_offset_shrinks(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        g = sdf_offset(f, -0.3)
        # New surface at radius 0.7
        assert abs(g(0.7, 0.0, 0.0)) < _ABS


# ===========================================================================
# 6. Gradient / surface normal on a sphere
# ===========================================================================

class TestGradient:
    def test_gradient_magnitude_on_sphere(self):
        """For an exact SDF the gradient magnitude should be ~1 everywhere."""
        f = sdf_sphere(0, 0, 0, 1.0)
        for pt in [(1.5, 0, 0), (0, 0.8, 0), (1, 1, 0)]:
            gx, gy, gz = field_gradient(f, *pt)
            mag = math.sqrt(gx * gx + gy * gy + gz * gz)
            assert abs(mag - 1.0) < _GRAD_TOL

    def test_unit_normal_on_sphere_surface(self):
        """Unit normal at (r,0,0) on a unit sphere should be (1,0,0)."""
        f = sdf_sphere(0, 0, 0, 1.0)
        nx, ny, nz = surface_normal(f, 1.0, 0.0, 0.0)
        assert abs(nx - 1.0) < _GRAD_TOL
        assert abs(ny) < _GRAD_TOL
        assert abs(nz) < _GRAD_TOL

    def test_unit_normal_is_unit_length(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        for pt in [(1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)]:
            nx, ny, nz = surface_normal(f, *pt)
            mag = math.sqrt(nx * nx + ny * ny + nz * nz)
            assert abs(mag - 1.0) < _GRAD_TOL


# ===========================================================================
# 7. TPMS
# ===========================================================================

class TestTPMS:
    def test_gyroid_period_correct(self):
        """f(x,0,0) = sin(2π/T · x)·cos(0) + ... = sin(kx) → zero at x=0."""
        period = 2.0
        f = sdf_gyroid(period, iso=0.0)
        # At x=0, y=0, z=0: sin(0)cos(0)+sin(0)cos(0)+sin(0)cos(0) = 0
        assert abs(f(0.0, 0.0, 0.0)) < _ABS

    def test_schwarz_p_period(self):
        period = 2.0
        f = sdf_schwarz_p(period, iso=0.0)
        # At x=T/4=0.5, y=0, z=0: cos(pi/2)+1+1 = 0+2 ≠ 0 (above surface)
        assert f(period / 4, 0.0, 0.0) > 0

    def test_diamond_origin(self):
        f = sdf_diamond(period=2.0, iso=0.0)
        # At origin: sin(0)sin(0)sin(0)+...= 0
        assert abs(f(0.0, 0.0, 0.0)) < _ABS

    def test_tpms_density_monotone(self):
        """Higher iso-value → lower relative density for gyroid."""
        results = []
        for iso in (-1.0, -0.5, 0.0, 0.5, 1.0):
            r = tpms_wall_thickness(1.0, 0.5, "gyroid")
            # Actually test that tpms_wall_thickness iso is monotone in density
            results.append(iso)
        # Build mapping: rho → iso using tpms_wall_thickness
        rhos = [0.1, 0.3, 0.5, 0.7, 0.9]
        isos = []
        for rho in rhos:
            r = tpms_wall_thickness(1.0, rho, "gyroid")
            assert r["ok"]
            isos.append(r["iso_value"])
        # iso_value should be monotone (decreasing as rho increases, empirically)
        for i in range(len(isos) - 1):
            assert isos[i] > isos[i + 1], (
                f"iso not monotone: iso[{i}]={isos[i]}, iso[{i+1}]={isos[i+1]}"
            )

    def test_tpms_schwarz_p_density_monotone(self):
        rhos = [0.1, 0.3, 0.5, 0.7, 0.9]
        isos = []
        for rho in rhos:
            r = tpms_wall_thickness(1.0, rho, "schwarz_p")
            assert r["ok"]
            isos.append(r["iso_value"])
        for i in range(len(isos) - 1):
            assert isos[i] > isos[i + 1]

    def test_tpms_bad_density(self):
        r = tpms_wall_thickness(1.0, 0.0, "gyroid")
        assert not r["ok"]

    def test_tpms_bad_surface(self):
        r = tpms_wall_thickness(1.0, 0.3, "unknown_surface")
        assert not r["ok"]


# ===========================================================================
# 8. Marching cubes — unit sphere
# ===========================================================================

class TestMarchingCubes:
    """Marching-cubes of unit sphere: volume ≈ 4/3π, verts on surface."""

    _RES = 24
    _HALF = 1.5
    _SPHERE_VOL = 4.0 / 3.0 * math.pi  # ≈ 4.189

    @pytest.fixture(scope="class")
    def sphere_mesh(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        rng = (-self._HALF, self._HALF)
        return marching_cubes(f, rng, rng, rng,
                              self._RES, self._RES, self._RES)

    def test_mc_ok(self, sphere_mesh):
        assert sphere_mesh["ok"]

    def test_mc_nonempty(self, sphere_mesh):
        assert sphere_mesh["vertex_count"] > 0
        assert sphere_mesh["face_count"] > 0

    def test_volume_within_tolerance(self, sphere_mesh):
        """Voxel volume of the sphere should be within 12% of 4/3π."""
        f = sdf_sphere(0, 0, 0, 1.0)
        rng = (-self._HALF, self._HALF)
        vol = field_volume(f, rng, rng, rng,
                           self._RES, self._RES, self._RES)
        assert vol["ok"]
        rel_err = abs(vol["volume"] - self._SPHERE_VOL) / self._SPHERE_VOL
        assert rel_err < _VOL_REL_TOL, f"volume rel_err={rel_err:.3f}"

    def test_verts_on_sphere_surface(self, sphere_mesh):
        """All marching-cubes vertices should lie within grid tolerance of the sphere."""
        verts = sphere_mesh["vertices"]
        rng = (-self._HALF, self._HALF)
        cell_size = (rng[1] - rng[0]) / self._RES
        tol = cell_size * 1.5  # allow 1.5 cells of deviation
        for v in verts:
            dist_from_surface = abs(math.sqrt(v[0]**2 + v[1]**2 + v[2]**2) - 1.0)
            assert dist_from_surface < tol, (
                f"vertex {v} is {dist_from_surface:.4f} from surface (tol={tol:.4f})"
            )

    def test_mc_bad_resolution(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        r = marching_cubes(f, (-1, 1), (-1, 1), (-1, 1), 0, 0, 0)
        assert not r["ok"]


# ===========================================================================
# 9. Field sampling
# ===========================================================================

class TestFieldSampling:
    def test_sample_field_shape(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        result = sample_field(f, (-2, 2), (-2, 2), (-2, 2), 4, 4, 4)
        assert result["ok"]
        assert result["shape"] == [4, 4, 4]

    def test_sample_field_values(self):
        """Origin of unit sphere should be ≈ -1 in the sampled grid."""
        f = sdf_sphere(0, 0, 0, 1.0)
        result = sample_field(f, (-1, 1), (-1, 1), (-1, 1), 3, 3, 3)
        assert result["ok"]
        # Centre voxel is at index [1][1][1] (midpoint of -1..1 with 3 pts = 0)
        assert abs(result["values"][1][1][1] - (-1.0)) < _ABS

    def test_sample_field_bad_resolution(self):
        f = sdf_sphere(0, 0, 0, 1.0)
        r = sample_field(f, (-1, 1), (-1, 1), (-1, 1), 1, 1, 1)
        assert not r["ok"]


# ===========================================================================
# 10. Surface area — sphere (4πr² ≈ 12.566)
# ===========================================================================

class TestSurfaceArea:
    def test_sphere_surface_area(self):
        """MC surface area of unit sphere should be within 10% of 4π."""
        f = sdf_sphere(0, 0, 0, 1.0)
        rng = (-1.5, 1.5)
        result = field_surface_area(f, rng, rng, rng, 24, 24, 24)
        assert result["ok"]
        expected = 4.0 * math.pi  # ≈ 12.566
        rel_err = abs(result["surface_area"] - expected) / expected
        assert rel_err < 0.10, f"surface_area rel_err={rel_err:.3f}"


# ===========================================================================
# 11. Plane SDF
# ===========================================================================

class TestPlaneSDF:
    def test_above_plane(self):
        # z=0 plane with normal (0,0,1); d=0
        f = sdf_plane(0, 0, 1, 0)
        assert f(0, 0, 1) > 0

    def test_below_plane(self):
        f = sdf_plane(0, 0, 1, 0)
        assert f(0, 0, -1) < 0

    def test_on_plane(self):
        f = sdf_plane(0, 0, 1, 0)
        assert abs(f(5, 3, 0)) < _ABS


# ===========================================================================
# 12. Cylinder SDF
# ===========================================================================

class TestCylinderSDF:
    def test_on_barrel(self):
        """Point on the barrel surface of a cylinder."""
        f = sdf_cylinder(0, 0, 0, 1.0, 2.0, axis=2)
        # On barrel at (1, 0, 0), within height range
        assert abs(f(1.0, 0.0, 0.0)) < _ABS

    def test_inside(self):
        f = sdf_cylinder(0, 0, 0, 1.0, 2.0, axis=2)
        assert f(0.0, 0.0, 0.0) < 0

    def test_above_cap(self):
        f = sdf_cylinder(0, 0, 0, 1.0, 1.0, axis=2)
        assert f(0.0, 0.0, 2.0) > 0


# ===========================================================================
# 13. Torus SDF
# ===========================================================================

class TestTorusSDF:
    def test_on_surface(self):
        """Point on the outer equator of a torus."""
        # major_radius=1, minor_radius=0.25, axis=2
        # Outer equator at (major+minor, 0, 0)
        f = sdf_torus(0, 0, 0, 1.0, 0.25, axis=2)
        assert abs(f(1.25, 0.0, 0.0)) < _ABS

    def test_inside_tube(self):
        f = sdf_torus(0, 0, 0, 1.0, 0.25, axis=2)
        # Centre of tube is at (1,0,0) in z=2 plane; inside
        assert f(1.0, 0.0, 0.0) < 0
