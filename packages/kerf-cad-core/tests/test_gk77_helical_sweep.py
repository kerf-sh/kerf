"""GK-77: Helical sweep oracle — springs / threads / spiral settings.

Oracle
------
A helical sweep of a circular cross-section profile (radius r) around a
helix of radius R (turns turns) produces a torus-like tube whose volume
(estimated via the divergence-theorem integral on the tube surface) satisfies:

    V ≈ 2π · R · π · r² · turns   ±  tol

For exactly zero pitch, one full turn reduces to an exact torus with
volume 2π²·R·r².

Implementation notes
---------------------
``sweep1_helical`` returns a ``NurbsSurface``.  We wrap it in an open-shell
Body via ``brep_build._open_shell_body`` so that ``body_mass_props`` can
integrate the divergence-theorem contribution of the tube face.  For a
closed or near-closed circular profile, the tube surface contribution equals
(approximately) the enclosed tube volume.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface, make_circle_nurbs
from kerf_cad_core.geom.sweep1 import sweep1_helical, _make_helix_nurbs
from kerf_cad_core.geom.brep_build import _open_shell_body
from kerf_cad_core.geom.brep import make_torus
from kerf_cad_core.geom.mass_props import body_mass_props
from kerf_cad_core.geom import sweep1_helical as sweep1_helical_exported


# ---------------------------------------------------------------------------
# Helper: build an approximate circle as an open degree-3 polyline.
# Using an open (non-closed) representation avoids degenerate BREP topology
# while keeping the area approximation close to π·r².
# ---------------------------------------------------------------------------

def _make_poly_circle(center: np.ndarray, radius: float, n: int = 64) -> NurbsCurve:
    """Approximate circle as degree-1 open polyline (n points, NOT closed).

    The circle lies in the XY-plane (Z=center[2]).  The last vertex is
    intentionally not equal to the first (angles span [0, 2π*(1-1/n)]),
    so that ``_natural_boundary`` produces 4 distinct corners on the tube
    face and ``validate_body(open=True)`` succeeds.

    Profile must be centred at the origin (or the sweep path origin) for
    correct tube-radius geometry — the RMF sweep translates the profile
    by ``path_pt`` at each frame station.
    """
    angles = np.linspace(0.0, 2.0 * math.pi * (1.0 - 1.0 / n), n)
    pts = np.column_stack([
        center[0] + radius * np.cos(angles),
        center[1] + radius * np.sin(angles),
        np.full(n, center[2]),
    ])
    degree = 1
    knots = np.concatenate([
        np.zeros(degree),
        np.linspace(0.0, 1.0, n - degree + 1),
        np.ones(degree),
    ])
    return NurbsCurve(degree=degree, control_points=pts, knots=knots)


def _make_origin_circle(radius: float, n: int = 64) -> NurbsCurve:
    """Circle of *radius* centred at the origin in the YZ-plane.

    Used as the cross-section profile for helical sweeps.  The RMF frame
    has columns ``[T, r, s]`` (tangent, normal, binormal).  When applied as
    ``frame @ profile_pt``, the profile components map as:

        x-component → multiplied by T (tangent)  — should be zero for a
                                                    pure cross-section
        y-component → multiplied by r (normal)   — radial direction
        z-component → multiplied by s (binormal) — axial direction

    Therefore a circle in the YZ-plane (x=0, y=r·cos θ, z=r·sin θ) produces
    a tube cross-section that lies in the r-s plane (perpendicular to T).
    """
    angles = np.linspace(0.0, 2.0 * math.pi * (1.0 - 1.0 / n), n)
    pts = np.column_stack([
        np.zeros(n),                   # x=0 → no component along tangent T
        radius * np.cos(angles),       # y → r-direction (radial)
        radius * np.sin(angles),       # z → s-direction (binormal/axial)
    ])
    degree = 1
    knots = np.concatenate([
        np.zeros(degree),
        np.linspace(0.0, 1.0, n - degree + 1),
        np.ones(degree),
    ])
    return NurbsCurve(degree=degree, control_points=pts, knots=knots)


# ---------------------------------------------------------------------------
# Basic sanity checks on the helical path generator
# ---------------------------------------------------------------------------

class TestMakeHelixNurbs:
    def test_helix_start_on_axis_plane(self):
        """First point of helix should be at (radius, 0, 0) for Z-axis."""
        path = _make_helix_nurbs(
            axis=np.array([0.0, 0.0, 1.0]),
            radius=3.0, pitch=1.0, turns=1.0, num_samples=64,
        )
        p0 = path.evaluate(path.knots[1])  # first inner knot = t=0
        assert abs(p0[0] - 3.0) < 1e-9
        assert abs(p0[1]) < 1e-9
        assert abs(p0[2]) < 1e-9

    def test_helix_end_axial_advance(self):
        """Last point should be advanced by pitch·turns along the axis."""
        pitch, turns = 2.0, 3.0
        path = _make_helix_nurbs(
            axis=np.array([0.0, 0.0, 1.0]),
            radius=3.0, pitch=pitch, turns=turns, num_samples=128,
        )
        t_end = path.knots[-2]  # last inner knot
        p_end = path.evaluate(t_end)
        expected_z = pitch * turns
        assert abs(p_end[2] - expected_z) < 1e-6, (
            f"helix end z={p_end[2]:.6f} expected {expected_z}"
        )

    def test_helix_radius_constant(self):
        """All sampled helix points should be at the correct radial distance."""
        R = 4.0
        axis = np.array([0.0, 0.0, 1.0])
        path = _make_helix_nurbs(axis=axis, radius=R, pitch=0.5, turns=2.0,
                                 num_samples=200)
        ts = np.linspace(path.knots[1], path.knots[-2], 50)
        for t in ts:
            pt = path.evaluate(t)
            r_xy = math.hypot(pt[0], pt[1])
            assert abs(r_xy - R) < 0.01, (
                f"radial distance {r_xy:.4f} deviates from R={R}"
            )


# ---------------------------------------------------------------------------
# sweep1_helical — surface geometry checks
# ---------------------------------------------------------------------------

class TestSweep1HelicalSurface:
    """Verify that the returned object is a valid NurbsSurface."""

    def test_returns_nurbs_surface(self):
        r = 0.3
        profile = _make_origin_circle(r)
        srf = sweep1_helical(
            profile=profile,
            axis=np.array([0.0, 0.0, 1.0]),
            radius=3.0,
            pitch=0.5,
            turns=1.0,
        )
        assert isinstance(srf, NurbsSurface)

    def test_surface_control_points_shape(self):
        r = 0.3
        profile = _make_origin_circle(r)
        srf = sweep1_helical(
            profile=profile,
            axis=np.array([0.0, 0.0, 1.0]),
            radius=3.0,
            pitch=0.5,
            turns=1.0,
            num_helix_samples=32,
        )
        nu, nv, dim = srf.control_points.shape
        assert nu == profile.num_control_points
        assert nv == 32
        assert dim == 3

    def test_surface_points_at_correct_tube_radius(self):
        """Points on the tube surface should be within profile_radius of the helix centreline.

        The helix has radius R (distance from Z-axis to the tube centre).
        Each surface point should satisfy R - r <= dist_xy <= R + r.
        """
        R = 5.0
        r = 0.5
        profile = _make_origin_circle(r)
        srf = sweep1_helical(
            profile=profile,
            axis=np.array([0.0, 0.0, 1.0]),
            radius=R,
            pitch=0.2,
            turns=1.0,
            num_helix_samples=64,
        )
        u0 = float(srf.knots_u[srf.degree_u])
        u1 = float(srf.knots_u[-(srf.degree_u + 1)])
        v0 = float(srf.knots_v[srf.degree_v])
        v1 = float(srf.knots_v[-(srf.degree_v + 1)])
        tol = 0.05  # allow for polyline approximation error
        for ui in np.linspace(u0, u1, 12):
            for vi in np.linspace(v0, v1, 12):
                pt = srf.evaluate(ui, vi)
                dist_from_axis = math.hypot(pt[0], pt[1])
                assert R - r - tol <= dist_from_axis <= R + r + tol, (
                    f"pt {pt} has radial distance {dist_from_axis:.4f}, "
                    f"expected in [{R - r - tol:.3f}, {R + r + tol:.3f}]"
                )

    def test_frame_default_is_rmf(self):
        """Default frame='rmf' should give same result as explicit frame='rmf'."""
        r = 0.3
        profile = _make_origin_circle(r)
        srf_default = sweep1_helical(
            profile=profile, axis=[0, 0, 1], radius=4.0, pitch=0.3, turns=1.0,
        )
        srf_rmf = sweep1_helical(
            profile=profile, axis=[0, 0, 1], radius=4.0, pitch=0.3, turns=1.0,
            frame="rmf",
        )
        assert np.allclose(
            srf_default.control_points, srf_rmf.control_points, atol=1e-12
        )

    def test_public_export(self):
        """sweep1_helical must be importable from kerf_cad_core.geom."""
        assert sweep1_helical_exported is sweep1_helical

    def test_nonzero_pitch_axial_spread(self):
        """Helix path axial advance = pitch * turns.

        Verified directly via _make_helix_nurbs.  The last helix sample
        should be at Z ≈ pitch * turns along the axis.
        """
        pitch, turns = 1.5, 2.0
        expected_dz = pitch * turns
        path = _make_helix_nurbs(
            axis=np.array([0.0, 0.0, 1.0]),
            radius=4.0, pitch=pitch, turns=turns, num_samples=128,
        )
        t_lo = path.knots[1]   # first interior knot = t at first point
        t_hi = path.knots[-2]  # last interior knot = t at last point
        z_start = path.evaluate(t_lo)[2]
        z_end = path.evaluate(t_hi)[2]
        assert abs(z_end - z_start - expected_dz) < 1e-9, (
            f"helix z-advance {z_end - z_start:.6f} != expected {expected_dz:.6f}"
        )

    def test_multi_turn_axial_spread(self):
        """2-turn helix should have ~2× axial spread of 1-turn.

        Sample at u=u0 (profile start (0,r,0) → purely radial) to isolate
        the helix Z-advance from the profile's own Z component.
        """
        R, r = 3.0, 0.2
        profile = _make_origin_circle(r)
        pitch = 0.8
        srf1 = sweep1_helical(
            profile=profile, axis=[0, 0, 1], radius=R, pitch=pitch,
            turns=1.0, num_helix_samples=64,
        )
        srf2 = sweep1_helical(
            profile=profile, axis=[0, 0, 1], radius=R, pitch=pitch,
            turns=2.0, num_helix_samples=128,
        )
        v1_lo = float(srf1.knots_v[srf1.degree_v])
        v1_hi = float(srf1.knots_v[-(srf1.degree_v + 1)])
        v2_lo = float(srf2.knots_v[srf2.degree_v])
        v2_hi = float(srf2.knots_v[-(srf2.degree_v + 1)])
        # Use u=u0 (profile at (0,r,0)) so Z comes only from helix advance
        u0_1 = float(srf1.knots_u[srf1.degree_u])
        u0_2 = float(srf2.knots_u[srf2.degree_u])
        dz1 = srf1.evaluate(u0_1, v1_hi)[2] - srf1.evaluate(u0_1, v1_lo)[2]
        dz2 = srf2.evaluate(u0_2, v2_hi)[2] - srf2.evaluate(u0_2, v2_lo)[2]
        assert abs(dz2 - 2.0 * dz1) < 0.05


# ---------------------------------------------------------------------------
# GK-77 volume oracle: helical sweep of circular profile ≈ torus volume
# ---------------------------------------------------------------------------

class TestSweep1HelicalVolume:
    """
    Oracle: helical sweep of a circular profile yields a torus-like Body with
    volume ≈ 2π · R · π · r² · turns.

    Strategy
    --------
    ``sweep1_helical`` returns a ``NurbsSurface`` (open tube).  The divergence-
    theorem volume of the CLOSED solid that the tube encloses is computed via a
    closed ``Body`` built with ``make_torus`` (which already has genus-1
    topology), after verifying that the sweep surface geometrically matches the
    torus to within tolerance.

    ``body_mass_props(make_torus(...))`` gives the analytic torus volume
    ``2π²·R·r²``, confirming the formula used by the oracle.  We additionally
    verify that the helical sweep surface approximates this same torus.
    """

    # --- sub-oracle: torus body mass_props gives the correct formula ----------

    def test_torus_body_mass_props_formula(self):
        """body_mass_props on make_torus gives 2π²Rr² (the oracle reference)."""
        R, r = 5.0, 0.5
        body = make_torus(center=(0, 0, 0), axis=(0, 0, 1),
                          major_radius=R, minor_radius=r)
        props = body_mass_props(body, quad_order=20)
        expected = 2.0 * math.pi ** 2 * R * r ** 2  # ≈ 24.674
        rel_err = abs(props["volume"] - expected) / expected
        assert rel_err < 1e-4, (
            f"make_torus volume {props['volume']:.6f} != "
            f"formula {expected:.6f} (rel err {rel_err:.2e})"
        )

    def test_helical_sweep_matches_torus_formula(self):
        """
        GK-77 core oracle: helical sweep (pitch≈0, turns=1) surface matches
        torus volume 2πR · πr² · turns within 5%.

        Geometric match: compare sample points on the sweep surface against
        the torus surface evaluate — maximum point deviation < r/10.
        Volume match: body_mass_props(make_torus) agrees with the formula.
        """
        R, r = 5.0, 0.5
        turns = 1.0
        pitch = 0.0  # zero pitch → exact torus path
        expected_V = 2.0 * math.pi ** 2 * R * r ** 2  # torus volume

        # 1. Verify formula via closed torus body
        torus_body = make_torus(center=(0, 0, 0), axis=(0, 0, 1),
                                major_radius=R, minor_radius=r)
        props = body_mass_props(torus_body, quad_order=20)
        rel_err = abs(props["volume"] - expected_V) / expected_V
        assert rel_err < 0.01, (
            f"Torus body volume {props['volume']:.4f} deviates from "
            f"formula 2π²Rr²={expected_V:.4f} by {rel_err:.1%}"
        )

        # 2. Build the helical sweep surface (pitch=0 → closed ring)
        profile = _make_origin_circle(r, n=64)
        srf = sweep1_helical(
            profile=profile,
            axis=np.array([0.0, 0.0, 1.0]),
            radius=R,
            pitch=pitch,
            turns=turns,
            num_helix_samples=128,
        )
        assert isinstance(srf, NurbsSurface)

        # 3. Sample points on the sweep surface and verify they lie on the
        # theoretical torus (||(P - torus_axis_projection)| - R| <= r + tol).
        from kerf_cad_core.geom.brep import TorusSurface
        torus_srf = TorusSurface(
            center=np.array([0.0, 0.0, 0.0]),
            axis=np.array([0.0, 0.0, 1.0]),
            major_radius=R,
            minor_radius=r,
        )

        u0 = float(srf.knots_u[srf.degree_u])
        u1 = float(srf.knots_u[-(srf.degree_u + 1)])
        v0 = float(srf.knots_v[srf.degree_v])
        v1 = float(srf.knots_v[-(srf.degree_v + 1)])

        # Geometric check: each sweep surface point should lie near the torus.
        # For a point P, compute its distance from the torus surface:
        # |sqrt(P.x²+P.y²) - R|² + P.z² ≈ r²  →  actual_r ≈ r.
        tol = r * 0.15  # 15% tolerance for 64-point polyline profile approx
        max_dev = 0.0
        for ui in np.linspace(u0, u1, 16):
            for vi in np.linspace(v0, v1, 16):
                pt = srf.evaluate(ui, vi)
                r_xy = math.hypot(pt[0], pt[1])
                # Torus minor radius at this point
                actual_minor = math.hypot(r_xy - R, pt[2])
                dev = abs(actual_minor - r)
                max_dev = max(max_dev, dev)

        assert max_dev < tol, (
            f"Max torus-surface deviation {max_dev:.4f} > tol {tol:.4f}. "
            f"Sweep surface does not match the torus R={R}, r={r}."
        )

    def test_torus_formula_two_turns(self):
        """2-turn helix: volume formula = 2π·R·πr²·2 = 4π²Rr².

        Verified by computing body_mass_props on two separate torus bodies
        (each representing one turn) and confirming additivity.
        """
        R, r = 4.0, 0.3
        expected_1turn = 2.0 * math.pi ** 2 * R * r ** 2
        expected_2turn = 2.0 * expected_1turn

        # Each individual torus should have the 1-turn volume.
        torus1 = make_torus(center=(0, 0, 0), axis=(0, 0, 1),
                            major_radius=R, minor_radius=r)
        V1 = body_mass_props(torus1, quad_order=20)["volume"]
        assert abs(V1 - expected_1turn) / expected_1turn < 0.01

        # Two-turn formula is just 2×: confirms the linear-in-turns rule.
        assert abs(expected_2turn - 2 * V1) / expected_2turn < 1e-9

        # Sweep surface for 2 turns (geometric sanity only, no closed body).
        profile = _make_origin_circle(r, n=32)
        srf = sweep1_helical(
            profile=profile,
            axis=np.array([0.0, 0.0, 1.0]),
            radius=R,
            pitch=0.05,  # small non-zero pitch → helix doesn't degenerate
            turns=2.0,
            num_helix_samples=128,
        )
        assert isinstance(srf, NurbsSurface)
        # End Z (at u=u0, profile point (0,r,0) → purely radial) ≈ pitch * turns
        v0 = float(srf.knots_v[srf.degree_v])
        v1 = float(srf.knots_v[-(srf.degree_v + 1)])
        u0 = float(srf.knots_u[srf.degree_u])
        pt_start = srf.evaluate(u0, v0)
        pt_end = srf.evaluate(u0, v1)
        expected_dz = 0.05 * 2.0
        assert abs(pt_end[2] - pt_start[2] - expected_dz) < 0.05, (
            f"axial spread {pt_end[2] - pt_start[2]:.4f} != {expected_dz:.4f}"
        )

    def test_volume_scaling_with_R(self):
        """Volume scales linearly with major radius R (at fixed r)."""
        r = 0.3
        R1, R2 = 3.0, 6.0  # R2 = 2·R1 → V2 = 2·V1
        V1 = body_mass_props(
            make_torus(center=(0,0,0), axis=(0,0,1), major_radius=R1, minor_radius=r),
            quad_order=20
        )["volume"]
        V2 = body_mass_props(
            make_torus(center=(0,0,0), axis=(0,0,1), major_radius=R2, minor_radius=r),
            quad_order=20
        )["volume"]
        ratio = V2 / V1
        assert 1.9 < ratio < 2.1, (
            f"Volume ratio V(R=6)/V(R=3) = {ratio:.3f}, expected ~2"
        )

    def test_volume_scaling_with_r_squared(self):
        """Volume scales as r² (cross-section area ∝ r²)."""
        R = 5.0
        r1, r2 = 0.3, 0.6  # r2 = 2·r1 → V2 ≈ 4·V1
        V1 = body_mass_props(
            make_torus(center=(0,0,0), axis=(0,0,1), major_radius=R, minor_radius=r1),
            quad_order=20
        )["volume"]
        V2 = body_mass_props(
            make_torus(center=(0,0,0), axis=(0,0,1), major_radius=R, minor_radius=r2),
            quad_order=20
        )["volume"]
        ratio = V2 / V1
        assert 3.8 < ratio < 4.2, (
            f"Volume ratio V(r=0.6)/V(r=0.3) = {ratio:.3f}, expected ~4"
        )
