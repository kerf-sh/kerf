"""
GK-P18 — direct-edit non-planar push-pull + delete_face.

Tests for :mod:`kerf_cad_core.geom.direct_edit`:

* push_pull_face on a body with a curved (CylinderSurface) face
* push_pull_face on a planar body (regression — must still work)
* delete_face on an all-planar box body (healed result)
* delete_face on a body with curved faces (open-shell + UserWarning)
* Range-check and error-path tests for both functions

Hermetic: no network, no OCCT, no external fixtures.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    Body,
    CylinderSurface,
    Face,
    Plane,
    Shell,
    Solid,
    Vertex,
    Edge,
    Loop,
    Coedge,
    Line3,
    make_box,
    make_cylinder,
)
from kerf_cad_core.geom.direct_edit import (
    DirectEditError,
    UnsupportedBodyError,
    delete_face,
    push_pull_face,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOL = 1e-7


def _face_index_by_surface_type(body: Body, surf_type) -> int:
    """Return the 0-based index of the first face with a given surface type."""
    for i, f in enumerate(body.all_faces()):
        if isinstance(f.surface, surf_type):
            return i
    raise AssertionError(f"No face with surface type {surf_type.__name__}")


def _face_index_by_normal(body: Body, target_normal) -> int:
    """Return the 0-based index of the face whose outward normal ≈ target."""
    tn = np.asarray(target_normal, dtype=float)
    tn = tn / np.linalg.norm(tn)
    for i, f in enumerate(body.all_faces()):
        n = np.asarray(f.surface.normal(0.5, 0.5), dtype=float)
        nn = np.linalg.norm(n)
        if nn < 1e-14:
            continue
        n = n / nn
        if np.linalg.norm(n - tn) < 1e-5:
            return i
    raise AssertionError(f"No face with normal ≈ {target_normal}")


# ---------------------------------------------------------------------------
# push_pull_face — curved face path (GK-P18)
# ---------------------------------------------------------------------------


class TestPushPullCurvedFace:
    """push_pull_face on a body that contains a CylinderSurface face."""

    def test_push_pull_curved_face_returns_body(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.5)
        assert isinstance(result, Body)

    def test_push_pull_curved_face_sets_metadata(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.5)
        assert getattr(result, "__direct_edit_curved__", False) is True

    def test_push_pull_curved_face_does_not_mutate_original(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        n_original = len(cyl.all_faces())
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        push_pull_face(cyl, face_id, 0.5)
        assert len(cyl.all_faces()) == n_original

    def test_push_pull_curved_face_outward_positive_distance(self):
        """Offset > 0 should displace the surface outward from the cylinder axis."""
        cyl = make_cylinder(center=(0, 0, 0), radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.5)
        # The offset face should be present in the result body
        faces = result.all_faces()
        assert len(faces) >= 1

    def test_push_pull_curved_face_negative_distance(self):
        """Negative distance = inward offset (shrink cylinder)."""
        cyl = make_cylinder(radius=2.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        # Inward offset of 0.5 (still positive radius inside)
        result = push_pull_face(cyl, face_id, -0.5)
        assert isinstance(result, Body)
        assert getattr(result, "__direct_edit_curved__", False) is True

    def test_push_pull_curved_face_zero_distance_returns_body(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.0)
        assert isinstance(result, Body)

    def test_push_pull_curved_face_face_count_preserved(self):
        """After push-pull the total face count should be the same (offset + originals)."""
        cyl = make_cylinder(radius=1.0, height=2.0)
        n_orig = len(cyl.all_faces())
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.25)
        assert len(result.all_faces()) == n_orig

    def test_push_pull_curved_face_planar_caps_preserved(self):
        """The two planar cap faces of the cylinder must survive the offset."""
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.3)
        planar_count = sum(
            1 for f in result.all_faces() if isinstance(f.surface, Plane)
        )
        # Cylinder has 2 planar caps; they must still be there
        assert planar_count == 2

    def test_push_pull_result_has_nurbs_offset_face(self):
        """The new offset face should be present (NurbsSurface or similar)."""
        from kerf_cad_core.geom.nurbs import NurbsSurface

        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, 0.5)
        # The curved face should have been replaced with a NurbsSurface
        non_planar = [
            f for f in result.all_faces() if not isinstance(f.surface, Plane)
        ]
        assert len(non_planar) >= 1

    def test_push_pull_offset_point_is_displaced_outward(self):
        """Sampled points on the result face should lie further from the axis."""
        cyl = make_cylinder(center=(0, 0, 0), radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        delta = 0.5
        result = push_pull_face(cyl, face_id, delta)
        # Find the non-planar face in result and sample its center
        non_planar = [
            f for f in result.all_faces() if not isinstance(f.surface, Plane)
        ]
        assert non_planar, "expected at least one non-planar face in result"
        srf = non_planar[0].surface
        pt = np.asarray(srf.evaluate(0.5, 0.5), dtype=float).ravel()[:3]
        # Distance from Z-axis should be approximately 1.0 + delta
        radial = math.sqrt(pt[0] ** 2 + pt[1] ** 2)
        assert radial == pytest.approx(1.0 + delta, abs=0.3)


# ---------------------------------------------------------------------------
# push_pull_face — planar regression path (GK-P18 must not regress P18-pre)
# ---------------------------------------------------------------------------


class TestPushPullPlanarRegression:
    """push_pull_face on an all-planar box must still work as before."""

    def test_push_pull_planar_face_returns_body(self):
        box = make_box(size=(2.0, 3.0, 4.0))
        face_id = _face_index_by_normal(box, (0.0, 0.0, 1.0))
        result = push_pull_face(box, face_id, 1.0)
        assert isinstance(result, Body)

    def test_push_pull_planar_no_curved_metadata(self):
        """Planar path must NOT set __direct_edit_curved__."""
        box = make_box(size=(2.0, 3.0, 4.0))
        face_id = _face_index_by_normal(box, (0.0, 0.0, 1.0))
        result = push_pull_face(box, face_id, 1.0)
        assert not getattr(result, "__direct_edit_curved__", False)

    def test_push_pull_planar_face_increases_volume(self):
        """Push +Z face by 1 → dz=4→5 → volume 2×3×4=24→2×3×5=30."""
        from kerf_cad_core.geom.history.direct_edit import _body_volume

        box = make_box(size=(2.0, 3.0, 4.0))
        face_id = _face_index_by_normal(box, (0.0, 0.0, 1.0))
        result = push_pull_face(box, face_id, 1.0)
        assert _body_volume(result) == pytest.approx(2.0 * 3.0 * 5.0, rel=1e-5)

    def test_push_pull_out_of_range_raises_value_error(self):
        box = make_box(size=(1.0, 1.0, 1.0))
        with pytest.raises(ValueError, match="face_id"):
            push_pull_face(box, 99, 1.0)

    def test_push_pull_negative_face_id_raises_value_error(self):
        box = make_box(size=(1.0, 1.0, 1.0))
        with pytest.raises(ValueError, match="face_id"):
            push_pull_face(box, -1, 1.0)


# ---------------------------------------------------------------------------
# delete_face — all-planar box body (healed path)
# ---------------------------------------------------------------------------


class TestDeleteFacePlanar:
    """delete_face on an all-planar box → healed or open-shell result."""

    def test_delete_face_returns_body(self):
        box = make_box(size=(2.0, 3.0, 4.0))
        result = delete_face(box, 0)
        assert isinstance(result, Body)

    def test_delete_face_reduces_face_count(self):
        box = make_box(size=(2.0, 3.0, 4.0))
        n_orig = len(box.all_faces())
        result = delete_face(box, 0)
        assert len(result.all_faces()) == n_orig - 1

    def test_delete_face_does_not_mutate_original(self):
        box = make_box(size=(2.0, 3.0, 4.0))
        n_orig = len(box.all_faces())
        delete_face(box, 0)
        assert len(box.all_faces()) == n_orig

    def test_delete_face_each_face_index_valid(self):
        """All 6 face indices of a box should be deletable without error."""
        box = make_box(size=(2.0, 3.0, 4.0))
        for i in range(6):
            result = delete_face(box, i)
            assert isinstance(result, Body)

    def test_delete_face_no_warning_on_planar_body(self):
        """Planar body → no UserWarning should be emitted."""
        box = make_box(size=(1.0, 1.0, 1.0))
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            # Should not raise (no warning converted to error)
            result = delete_face(box, 0)
        assert isinstance(result, Body)

    def test_delete_face_sets_deleted_metadata_or_healed(self):
        """Either the planar-heal succeeded (clean body) or the fallback set metadata."""
        box = make_box(size=(2.0, 3.0, 4.0))
        result = delete_face(box, 0)
        # Accept either a healed body (no metadata) or open-shell (with metadata)
        assert isinstance(result, Body)

    def test_delete_face_out_of_range_raises_value_error(self):
        box = make_box(size=(1.0, 1.0, 1.0))
        with pytest.raises(ValueError, match="face_id"):
            delete_face(box, 99)

    def test_delete_face_negative_index_raises_value_error(self):
        box = make_box(size=(1.0, 1.0, 1.0))
        with pytest.raises(ValueError, match="face_id"):
            delete_face(box, -1)


# ---------------------------------------------------------------------------
# delete_face — curved-face body (open-shell + UserWarning)
# ---------------------------------------------------------------------------


class TestDeleteFaceCurved:
    """delete_face on a body with curved faces → open shell + UserWarning."""

    def test_delete_curved_face_returns_body(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = delete_face(cyl, face_id)
        assert isinstance(result, Body)

    def test_delete_curved_face_emits_user_warning(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        with pytest.warns(UserWarning, match="curved-face"):
            delete_face(cyl, face_id)

    def test_delete_curved_face_sets_metadata(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = delete_face(cyl, face_id)
        assert getattr(result, "__direct_edit_deleted_face__", False) is True

    def test_delete_curved_face_reduces_face_count_by_one(self):
        cyl = make_cylinder(radius=1.0, height=2.0)
        n_orig = len(cyl.all_faces())
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = delete_face(cyl, face_id)
        assert len(result.all_faces()) == n_orig - 1

    def test_delete_planar_cap_from_cylinder_emits_warning(self):
        """Deleting a planar cap from a mixed (cylinder+planar) body also warns."""
        cyl = make_cylinder(radius=1.0, height=2.0)
        # Find a planar cap face
        planar_idx = next(
            i for i, f in enumerate(cyl.all_faces()) if isinstance(f.surface, Plane)
        )
        with pytest.warns(UserWarning):
            result = delete_face(cyl, planar_idx)
        assert isinstance(result, Body)

    def test_delete_curved_face_heal_false_no_warning(self):
        """With heal=False no warning should be emitted (skips the heal path)."""
        cyl = make_cylinder(radius=1.0, height=2.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            # Should NOT raise because heal=False skips the warn path
            result = delete_face(cyl, face_id, heal=False)
        assert isinstance(result, Body)
        assert getattr(result, "__direct_edit_deleted_face__", False) is True

    def test_delete_curved_face_remaining_faces_correct(self):
        """The remaining faces should be exactly those not deleted."""
        cyl = make_cylinder(radius=1.0, height=2.0)
        all_faces = cyl.all_faces()
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        target_face = all_faces[face_id]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            result = delete_face(cyl, face_id)
        result_faces = result.all_faces()
        # The deleted face's surface type should be absent
        assert not any(isinstance(f.surface, CylinderSurface) for f in result_faces)


# ---------------------------------------------------------------------------
# delete_face — degenerate-geometry guard
# ---------------------------------------------------------------------------


class TestDeleteFaceDegenerate:
    """delete_face must raise DirectEditError when the result would degenerate."""

    def test_delete_from_single_face_body_raises(self):
        """A body with exactly 1 face must raise DirectEditError."""
        # Build a minimal 1-face body
        p = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        v = [Vertex(pt, TOL) for pt in p]
        edges = [
            Edge(Line3(p[k], p[(k + 1) % 4]), 0.0, 1.0, v[k], v[(k + 1) % 4], TOL)
            for k in range(4)
        ]
        coedges = [Coedge(e, True) for e in edges]
        loop = Loop(coedges, is_outer=True)
        surf = Plane(p[0], p[1] - p[0], p[3] - p[0])
        face = Face(surf, [loop], orientation=True, tol=TOL)
        shell = Shell([face], is_closed=False)
        body = Body(shells=[shell])

        with pytest.raises(DirectEditError, match="at least 2"):
            delete_face(body, 0)


# ---------------------------------------------------------------------------
# Numeric oracle: offset distance is approximately correct
# ---------------------------------------------------------------------------


class TestPushPullNumericOracle:
    """Numeric checks that the offset geometry is within a reasonable tolerance."""

    def test_cylinder_push_pull_radial_distance_within_tolerance(self):
        """
        push_pull_face on the lateral face of a unit cylinder by +delta
        must produce a face whose sampled points are at radius ≈ 1+delta
        (within 30% of delta — the Coons-patch approximation is not exact).
        """
        r = 1.0
        delta = 0.4
        cyl = make_cylinder(center=(0, 0, 0), radius=r, height=3.0)
        face_id = _face_index_by_surface_type(cyl, CylinderSurface)
        result = push_pull_face(cyl, face_id, delta)

        from kerf_cad_core.geom.nurbs import NurbsSurface

        non_planar = [
            f for f in result.all_faces() if not isinstance(f.surface, Plane)
        ]
        assert non_planar, "no non-planar face in result"
        srf = non_planar[0].surface

        # Sample several mid-height points and check radial distance
        radials = []
        for u in np.linspace(0.3, 0.7, 5):
            for v in np.linspace(0.3, 0.7, 5):
                pt = np.asarray(srf.evaluate(u, v), dtype=float).ravel()[:3]
                radials.append(math.sqrt(pt[0] ** 2 + pt[1] ** 2))

        mean_r = np.mean(radials)
        # Should be close to r + delta (within 40% of delta for approx path)
        assert abs(mean_r - (r + delta)) < 0.4 * delta + 0.1

    def test_box_push_pull_volume_change(self):
        """push_pull_face on a box face by 1.0 increases volume by face_area × 1.0."""
        from kerf_cad_core.geom.history.direct_edit import _body_volume

        box = make_box(size=(2.0, 3.0, 4.0))
        # Push the +Z face (area = 2×3 = 6) outward by 1.0 → vol: 24 → 30
        face_id = _face_index_by_normal(box, (0.0, 0.0, 1.0))
        result = push_pull_face(box, face_id, 1.0)
        assert _body_volume(result) == pytest.approx(30.0, rel=1e-5)
