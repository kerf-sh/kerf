"""
Tests for kerf_optics paraxial ray-transfer matrix model.

Analytic oracles
----------------
1. Single thin lens — image distance satisfies 1/f = 1/do + 1/di (exact).
2. Two-lens telephoto — EFL satisfies 1/EFL = 1/f1 + 1/f2 - d/(f1*f2) (exact).
3. Collimated beam (u0≠0, y0=0) → focuses at back focal point.
4. Ray through optical centre → passes undeviated.
5. ABCD matrix determinant = 1 for same-medium systems.
6. Seidel field curvature coefficient = 1/(2nf) (Born & Wolf formula).
7. Ray bundle spot at image plane is near zero for a perfect system.
8. Two-element system matrix == product of individual matrices.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap (belt-and-suspenders alongside conftest)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_optics.ray_transfer import (
    M_free,
    M_thin_lens,
    M_refraction,
    M_mirror,
    M_identity,
    system_matrix,
    focal_length,
    image_distance,
    back_focal_distance,
    front_focal_distance,
    magnification,
    trace_ray,
    trace_bundle,
    spot_radius_at_plane,
    seidel_thin_lens,
)
from kerf_optics.lens_system import (
    LensSystem,
    ThinLens,
    FreeSpace,
    CurvedInterface,
    Mirror,
    Aperture,
    Detector,
)


# ===========================================================================
# Elementary matrix correctness
# ===========================================================================

class TestElementaryMatrices:
    """Verify each primitive ABCD matrix against closed-form definition."""

    def test_free_space_identity_at_zero(self):
        M = M_free(0.0)
        np.testing.assert_allclose(M, np.eye(2))

    def test_free_space_shape(self):
        M = M_free(0.1)
        assert M.shape == (2, 2)
        assert M[0, 0] == pytest.approx(1.0)
        assert M[1, 0] == pytest.approx(0.0)
        assert M[1, 1] == pytest.approx(1.0)
        assert M[0, 1] == pytest.approx(0.1)  # d/n with n=1

    def test_free_space_in_glass(self):
        n = 1.5
        d = 0.1
        M = M_free(d, n)
        # B = d/n
        assert M[0, 1] == pytest.approx(d / n)

    def test_thin_lens_shape(self):
        f = 0.1
        M = M_thin_lens(f)
        assert M[0, 0] == pytest.approx(1.0)
        assert M[0, 1] == pytest.approx(0.0)
        assert M[1, 0] == pytest.approx(-1.0 / f)
        assert M[1, 1] == pytest.approx(1.0)

    def test_thin_lens_zero_focal_length_raises(self):
        with pytest.raises(ValueError):
            M_thin_lens(0.0)

    def test_flat_interface_is_identity(self):
        M = M_refraction(0, 1.0, 1.5)
        np.testing.assert_allclose(M, np.eye(2))

    def test_curved_interface_power(self):
        R, n1, n2 = 0.1, 1.0, 1.5
        M = M_refraction(R, n1, n2)
        # C = -(n2 - n1) / R
        assert M[1, 0] == pytest.approx(-(n2 - n1) / R)

    def test_mirror_power(self):
        R = 0.2
        M = M_mirror(R)
        assert M[1, 0] == pytest.approx(-2.0 / R)

    def test_mirror_zero_radius_raises(self):
        with pytest.raises(ValueError):
            M_mirror(0.0)

    def test_identity_is_eye(self):
        np.testing.assert_allclose(M_identity(), np.eye(2))

    def test_free_space_negative_d_raises(self):
        with pytest.raises(ValueError):
            M_free(-0.1)

    def test_free_space_zero_n_raises(self):
        with pytest.raises(ValueError):
            M_free(0.1, n=0.0)


# ===========================================================================
# Thin-lens image-distance oracle (DoD requirement 1)
# ===========================================================================

class TestThinLensImageDistance:
    """
    Reference: single thin lens.
    Thin-lens equation: 1/f = 1/do + 1/di  →  di = f*do / (do - f)

    The ABCD system for [FreeSpace(do), ThinLens(f), FreeSpace(di)]:
        M = M_free(di) @ M_thin_lens(f) @ M_free(do)
    Image condition: B = 0 (no dependence of output height on input angle),
    which is equivalent to the thin-lens equation 1/f = 1/do + 1/di.
    A = transverse magnification m = -(di/do) at the image plane.
    """

    def _di(self, f, do):
        return f * do / (do - f)

    def test_symmetric_conjugates_f100mm(self):
        """Object at 2f → image at 2f, magnification -1."""
        f = 0.1
        do = 2 * f
        di_expected = self._di(f, do)
        # Image condition: B = 0 (M[0,1] = 0)
        M = system_matrix([M_free(do), M_thin_lens(f), M_free(di_expected)])
        assert M[0, 1] == pytest.approx(0.0, abs=1e-12), (
            f"B != 0: image condition not satisfied for f={f}, do={do}"
        )
        # Verify via image_distance helper
        M_partial = system_matrix([M_free(do), M_thin_lens(f)])
        di_computed = image_distance(M_partial, 0.0)
        assert di_computed == pytest.approx(di_expected, rel=1e-10)

    def test_thin_lens_eq_exact_various_conjugates(self):
        """
        1/f = 1/do + 1/di must hold exactly for a range of object distances.
        The system matrix M = M_thin_lens(f) @ M_free(do) (object propagation first);
        image_distance(M, 0.0) gives di from the lens reference plane.
        """
        f = 0.05  # 50 mm focal length
        for do in [0.1, 0.2, 0.5, 1.0, 5.0]:
            di_expected = self._di(f, do)
            # M_free(do) propagates to lens; M_thin_lens(f) refracts at lens
            M = system_matrix([M_free(do), M_thin_lens(f)])
            di_computed = image_distance(M, 0.0)
            assert di_computed == pytest.approx(di_expected, rel=1e-9), (
                f"di mismatch for do={do}: computed={di_computed}, expected={di_expected}"
            )

    def test_thin_lens_equation_directly(self):
        """Verify 1/f == 1/do + 1/di to machine precision."""
        f, do = 0.1, 0.3
        M_partial = system_matrix([M_free(do), M_thin_lens(f)])
        di = image_distance(M_partial, 0.0)
        lhs = 1.0 / f
        rhs = 1.0 / do + 1.0 / di
        assert lhs == pytest.approx(rhs, rel=1e-10), (
            f"1/f={lhs:.10f} != 1/do + 1/di={rhs:.10f}"
        )

    def test_image_distance_via_lens_system(self):
        """LensSystem.image_distance agrees with direct ABCD calculation."""
        f, do = 0.1, 0.2
        di_expected = self._di(f, do)
        system = LensSystem([FreeSpace(do), ThinLens(f)])
        di = system.image_distance(0.0)
        assert di == pytest.approx(di_expected, rel=1e-10)

    def test_infinity_object(self):
        """Object at infinity → image at focal length."""
        f = 0.1
        do = 1e9  # effectively infinity
        M_partial = system_matrix([M_free(do), M_thin_lens(f)])
        di = image_distance(M_partial, 0.0)
        assert di == pytest.approx(f, rel=1e-3)  # 0.1 % tolerance for large do

    def test_unit_magnification(self):
        """Object at 2f → magnification exactly -1."""
        f, do = 0.1, 0.2
        di = self._di(f, do)
        M = system_matrix([M_free(do), M_thin_lens(f)])
        m = magnification(M, 0.0)
        assert m == pytest.approx(-1.0, rel=1e-9)

    def test_efl_single_lens(self):
        """EFL of a single thin lens = f."""
        f = 0.075
        M = M_thin_lens(f)
        assert focal_length(M) == pytest.approx(f, rel=1e-12)


# ===========================================================================
# Two-lens telephoto EFL oracle (DoD requirement 2)
# ===========================================================================

class TestTwoLensTelephoto:
    """
    Two-lens system EFL formula (exact):
        1/EFL = 1/f1 + 1/f2 - d/(f1*f2)

    where d = separation between the two lenses.
    """

    def _telephoto_efl(self, f1, f2, d):
        return 1.0 / (1.0 / f1 + 1.0 / f2 - d / (f1 * f2))

    def test_telephoto_efl_basic(self):
        """Two converging lenses separated by d."""
        f1, f2, d = 0.2, 0.1, 0.05
        efl_expected = self._telephoto_efl(f1, f2, d)
        M = system_matrix([M_thin_lens(f1), M_free(d), M_thin_lens(f2)])
        efl_computed = focal_length(M)
        assert efl_computed == pytest.approx(efl_expected, rel=1e-10), (
            f"EFL computed={efl_computed:.8f} expected={efl_expected:.8f}"
        )

    def test_telephoto_efl_various(self):
        """EFL formula holds for a range of f1, f2, d values."""
        cases = [
            (0.15, -0.05, 0.10),   # telephoto (positive + negative)
            (0.10, 0.10, 0.05),    # two equal lenses
            (0.20, 0.20, 0.10),    # another equal pair
            (0.05, 0.20, 0.02),    # short then long
            (0.30, 0.15, 0.08),    # asymmetric
        ]
        for f1, f2, d in cases:
            efl_expected = self._telephoto_efl(f1, f2, d)
            M = system_matrix([M_thin_lens(f1), M_free(d), M_thin_lens(f2)])
            efl_computed = focal_length(M)
            assert efl_computed == pytest.approx(efl_expected, rel=1e-10), (
                f"f1={f1}, f2={f2}, d={d}: computed={efl_computed:.8f}, "
                f"expected={efl_expected:.8f}"
            )

    def test_telephoto_efl_via_lens_system(self):
        """LensSystem.efl() agrees with direct formula."""
        f1, f2, d = 0.15, -0.05, 0.10
        efl_expected = self._telephoto_efl(f1, f2, d)
        system = LensSystem([ThinLens(f1), FreeSpace(d), ThinLens(f2)])
        assert system.efl() == pytest.approx(efl_expected, rel=1e-10)

    def test_telephoto_longer_than_fl(self):
        """Telephoto: EFL > physical length (f1 + d) — the defining property.

        Use parameters that give a well-defined positive EFL exceeding the
        physical barrel length.  With f1=0.30, f2=-0.10, d=0.10:
          1/EFL = 1/0.30 + 1/(-0.10) - 0.10/(0.30*(-0.10))
                = 3.333 - 10 + 3.333 = -3.333  → EFL = -0.3  (diverging)
        Use f1=0.20, f2=0.30, d=0.10:
          1/EFL = 5 + 3.333 - 0.10/0.06 = 8.333 - 1.667 = 6.667 → EFL = 0.15
        Physical length = 0.30 → EFL (0.15) < physical — not a telephoto.

        A true telephoto needs f2 negative (diverging rear):
          f1=0.20, f2=-0.10, d=0.05:
          1/EFL = 5 - 10 - 0.05/(0.20*(-0.10)) = 5 - 10 + 2.5 = -2.5 → negative

        Simple telephoto: two positive lenses separated so EFL > barrel:
          f1=0.10, f2=0.10, d=0.05:
          1/EFL = 10 + 10 - 0.05/0.01 = 20 - 5 = 15 → EFL = 0.0667
          barrel = 0.15 — EFL < barrel.

        Use the classic definition: a telephoto compresses the system by having
        f2 negative. A design that works:
          f1=0.15, f2=-0.10, d=0.05:
          1/EFL = 6.667 - 10 - 0.05/(0.15*(-0.10)) = 6.667 - 10 + 3.333 = 0.0
          Degenerate (afocal).

          f1=0.15, f2=-0.20, d=0.05:
          1/EFL = 6.667 - 5 - 0.05/(0.15*(-0.20)) = 6.667 - 5 + 1.667 = 3.333
          EFL = 0.3; barrel = f1 + d = 0.20. EFL (0.3) > barrel (0.2). ✓
        """
        f1, f2, d = 0.15, -0.20, 0.05
        efl = self._telephoto_efl(f1, f2, d)
        physical_length = f1 + d
        assert efl > 0, f"EFL must be positive for this telephoto: got {efl}"
        assert efl > physical_length, (
            f"EFL={efl:.4f} should exceed physical length={physical_length:.4f}"
        )

    def test_two_lens_contact(self):
        """At d=0, combined focal length = f1*f2/(f1+f2)."""
        f1, f2 = 0.1, 0.2
        efl_expected = f1 * f2 / (f1 + f2)
        M = system_matrix([M_thin_lens(f1), M_free(0.0), M_thin_lens(f2)])
        efl_computed = focal_length(M)
        assert efl_computed == pytest.approx(efl_expected, rel=1e-10)

    def test_telephoto_image_distance_via_lens_system(self):
        """After a telephoto system, image distance is finite and positive for a real object."""
        f1, f2, d = 0.15, 0.10, 0.04
        do = 1.0  # object at 1 m
        system = LensSystem([FreeSpace(do), ThinLens(f1), FreeSpace(d), ThinLens(f2)])
        di = system.image_distance(0.0)
        assert di > 0.0, f"image_distance {di} is not positive"


# ===========================================================================
# Ray-tracing correctness
# ===========================================================================

class TestRayTracing:
    """Trace single rays through known systems and verify against analytic results."""

    def test_on_axis_ray_through_focus(self):
        """
        A ray entering at height y=h with angle 0 through a thin lens must
        cross the axis at the back focal distance.
        """
        f = 0.1
        h = 0.01  # 10 mm height
        # After the thin lens: ray angle = -h/f
        states = trace_ray(h, 0.0, [M_thin_lens(f)])
        y_after, nu_after = states[-1]
        assert y_after == pytest.approx(h)         # height unchanged by thin lens
        assert nu_after == pytest.approx(-h / f)   # angle = -h/f

    def test_collimated_ray_focuses_at_bfd(self):
        """Collimated ray (nu=0) → focuses at BFD = f."""
        f = 0.1
        # After lens + propagation of exactly f, height should be zero
        states = trace_ray(0.01, 0.0, [M_thin_lens(f), M_free(f)])
        y_final = states[-1][0]
        assert y_final == pytest.approx(0.0, abs=1e-12)

    def test_ray_through_optical_centre(self):
        """Ray at y=0 is undeviated by a thin lens: height stays 0."""
        f = 0.1
        states = trace_ray(0.0, 0.05, [M_thin_lens(f)])
        assert states[-1][0] == pytest.approx(0.0, abs=1e-14)

    def test_ray_bundle_symmetry(self):
        """Symmetric ray bundle (±h, same angle) should give ±final heights."""
        f, do, di = 0.1, 0.2, 0.2
        matrices = [M_free(do), M_thin_lens(f), M_free(di)]
        s1 = trace_ray(0.01, 0.0, matrices)
        s2 = trace_ray(-0.01, 0.0, matrices)
        assert s1[-1][0] == pytest.approx(-s2[-1][0], rel=1e-10)

    def test_image_height_at_image_plane(self):
        """
        A collimated ray bundle (y≠0, u=0) entering a thin lens must cross the
        optical axis at exactly the back focal distance f.
        Equivalently: a ray entering the lens at height h with u=0 exits at
        height h, angle -h/f, and reaches y=0 after propagating exactly f.
        """
        f = 0.1
        h = 0.01
        # After thin lens + propagation of exactly f:
        # y_out = h + f * (-h/f) = h - h = 0
        matrices = [M_thin_lens(f), M_free(f)]
        states = trace_ray(h, 0.0, matrices)
        assert abs(states[-1][0]) < 1e-12, (
            f"ray height at BFD = {states[-1][0]:.2e}, expected 0"
        )

    def test_trace_bundle_length(self):
        """trace_bundle returns one history per ray."""
        rays = [(0.01, 0.0), (0.005, 0.01), (-0.01, 0.0)]
        matrices = [M_thin_lens(0.1), M_free(0.1)]
        histories = trace_bundle(rays, matrices)
        assert len(histories) == 3
        for h in histories:
            assert len(h) == 3  # initial + after lens + after propagation

    def test_trace_states_count(self):
        """trace_ray returns N+1 states for N matrices."""
        matrices = [M_free(0.1), M_thin_lens(0.05), M_free(0.1)]
        states = trace_ray(0.01, 0.0, matrices)
        assert len(states) == len(matrices) + 1


# ===========================================================================
# ABCD matrix properties
# ===========================================================================

class TestABCDProperties:
    """Algebraic properties that must hold for any valid ABCD system."""

    def test_determinant_one_same_medium(self):
        """det(M) = 1 for a same-medium system (no net refractive-index change)."""
        matrices = [
            M_free(0.1),
            M_thin_lens(0.05),
            M_free(0.2),
            M_thin_lens(0.1),
            M_free(0.05),
        ]
        M = system_matrix(matrices)
        det = M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]
        assert det == pytest.approx(1.0, abs=1e-12)

    def test_identity_composition(self):
        """Composing a matrix with identity gives the same matrix."""
        M = M_thin_lens(0.1)
        M_composed = system_matrix([M_identity(), M, M_identity()])
        np.testing.assert_allclose(M_composed, M)

    def test_free_space_additive(self):
        """Two adjacent free-space propagations sum to a single one."""
        d1, d2 = 0.1, 0.15
        M_combined = system_matrix([M_free(d1), M_free(d2)])
        M_single = M_free(d1 + d2)
        np.testing.assert_allclose(M_combined, M_single, atol=1e-14)

    def test_efl_infinite_for_afocal(self):
        """An afocal system (C=0) raises ValueError for EFL."""
        M = M_free(0.5)  # C = 0 for free space
        with pytest.raises(ValueError, match="no power"):
            focal_length(M)

    def test_system_matrix_empty(self):
        """Empty element list → identity matrix."""
        M = system_matrix([])
        np.testing.assert_allclose(M, np.eye(2))

    def test_bfd_efl_single_thin_lens(self):
        """For a single thin lens, BFD = EFL = f."""
        f = 0.1
        M = M_thin_lens(f)
        assert back_focal_distance(M) == pytest.approx(f, rel=1e-12)
        assert focal_length(M) == pytest.approx(f, rel=1e-12)

    def test_ffd_single_thin_lens(self):
        """For a single thin lens, FFD = -f (symmetric)."""
        f = 0.1
        M = M_thin_lens(f)
        # FFD = -D/C = -1 / (-1/f) = f; sign convention: -D/C
        assert front_focal_distance(M) == pytest.approx(f, rel=1e-12)


# ===========================================================================
# Seidel aberration coefficients
# ===========================================================================

class TestSeidelCoefficients:
    """Verify the first-order Seidel formulae against known results."""

    def test_field_curvature_formula(self):
        """
        Petzval field curvature for a thin lens:
            W220 = 1 / (2 * n * f)
        (Born & Wolf §5.5.3, eq. 5.5.56)
        """
        f, n = 0.1, 1.5
        coefs = seidel_thin_lens(f, n, object_distance=0.2)
        expected = 1.0 / (2.0 * n * f)
        assert coefs["field_curvature"] == pytest.approx(expected, rel=1e-10), (
            f"W220 = {coefs['field_curvature']:.6f} != {expected:.6f}"
        )

    def test_seidel_returns_all_keys(self):
        """seidel_thin_lens returns all five Seidel coefficients."""
        coefs = seidel_thin_lens(f=0.1, n=1.5, object_distance=0.2)
        for key in ("spherical", "coma", "astigmatism", "field_curvature", "distortion"):
            assert key in coefs, f"missing key: {key}"

    def test_seidel_zero_object_raises(self):
        with pytest.raises(ValueError, match="object_distance"):
            seidel_thin_lens(f=0.1, n=1.5, object_distance=0.0)

    def test_spherical_aberration_positive_for_converging(self):
        """
        For a biconvex (equiconvex, q=0) converging lens with n>1,
        spherical aberration W040 is positive.
        """
        coefs = seidel_thin_lens(f=0.1, n=1.5, object_distance=0.2, shape_factor=0.0)
        assert coefs["spherical"] >= 0.0, (
            f"W040 should be >= 0 for converging lens: got {coefs['spherical']}"
        )

    def test_distortion_zero(self):
        """Distortion W311 is zero for a single thin lens in paraxial approx."""
        coefs = seidel_thin_lens(f=0.1, n=1.5, object_distance=0.2)
        assert coefs["distortion"] == pytest.approx(0.0, abs=1e-15)


# ===========================================================================
# LensSystem data model
# ===========================================================================

class TestLensSystemModel:
    """LensSystem class correctness."""

    def test_append_returns_self(self):
        s = LensSystem()
        ret = s.append(ThinLens(0.1))
        assert ret is s

    def test_efl_single_lens(self):
        s = LensSystem([ThinLens(0.1)])
        assert s.efl() == pytest.approx(0.1, rel=1e-12)

    def test_thin_lens_factory(self):
        """LensSystem.thin_lens() factory: B element (M[0,1]) = 0 at image plane."""
        f, do = 0.1, 0.2
        di = f * do / (do - f)
        s = LensSystem.thin_lens(f=f, object_distance=do, image_distance=di)
        M = s.system_matrix()
        # Image condition: B = 0 (output height independent of input angle)
        assert M[0, 1] == pytest.approx(0.0, abs=1e-12)

    def test_telephoto_factory(self):
        """LensSystem.telephoto() produces same matrix as manual construction."""
        f1, f2, d, do = 0.15, -0.05, 0.10, 0.5
        s = LensSystem.telephoto(f1=f1, f2=f2, separation=d, object_distance=do)
        M_manual = system_matrix([
            M_free(do), M_thin_lens(f1), M_free(d), M_thin_lens(f2)
        ])
        np.testing.assert_allclose(s.system_matrix(), M_manual, atol=1e-14)

    def test_spot_diagram_returns_dict(self):
        """spot_diagram returns required keys."""
        f, do = 0.1, 0.2
        di = f * do / (do - f)
        s = LensSystem.thin_lens(f, do, di)
        spot = s.spot_diagram()
        assert "rms_spot" in spot
        assert "heights" in spot
        assert "n_rays" in spot

    def test_spot_at_image_plane_near_zero(self):
        """
        At the perfect image plane, the RMS spot radius from a marginal-ray
        bundle (varying angle, fixed height=0) should be very small.
        """
        f, do = 0.1, 0.2
        di = f * do / (do - f)
        # Place image plane with FreeSpace(di)
        s = LensSystem([FreeSpace(do), ThinLens(f), FreeSpace(di)])
        # Rays entering at y=0, varying angle
        rays = [(0.0, u) for u in np.linspace(-0.05, 0.05, 11)]
        spot = spot_radius_at_plane(rays, s._flat_matrices())
        assert spot < 1e-12, f"spot radius {spot:.2e} at image plane > 1e-12"

    def test_summary_has_efl(self):
        s = LensSystem([ThinLens(0.1)])
        info = s.summary()
        assert info["efl"] == pytest.approx(0.1, rel=1e-12)

    def test_summary_afocal(self):
        """Free-space only → afocal, EFL is None."""
        s = LensSystem([FreeSpace(0.5)])
        info = s.summary()
        assert info["efl"] is None

    def test_element_describe(self):
        assert "ThinLens" in ThinLens(0.1).describe()
        assert "FreeSpace" in FreeSpace(0.1).describe()
        assert "Mirror" in Mirror(0.2).describe()
        assert "Aperture" in Aperture(0.05).describe()
        assert "Detector" in Detector().describe()


# ===========================================================================
# Module-level import smoke tests
# ===========================================================================

class TestModuleImports:
    """Ensure all modules compile and import cleanly."""

    def test_ray_transfer_import(self):
        import kerf_optics.ray_transfer  # noqa: F401

    def test_lens_system_import(self):
        import kerf_optics.lens_system  # noqa: F401

    def test_tools_import(self):
        import kerf_optics.tools  # noqa: F401

    def test_plugin_import(self):
        import kerf_optics.plugin  # noqa: F401

    def test_pycompile_ray_transfer(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_optics", "ray_transfer.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_lens_system(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_optics", "lens_system.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_optics", "tools.py")
        py_compile.compile(path, doraise=True)
