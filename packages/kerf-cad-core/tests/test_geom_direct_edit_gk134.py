"""
test_geom_direct_edit_gk134.py
==============================
Hermetic oracle tests for GK-134: direct modelling — push_pull_face /
move_face.

Oracles
-------
1. push_pull_face on a box top-face:
   volume_after = volume_before + face_area * distance  (± rel_tol)
   topology unchanged: same V, E, F counts.

2. move_face with the zero vector is an identity (volume unchanged,
   topology unchanged).

3. move_face along the face normal matches push_pull_face (same volume
   change).

4. Exports are visible in kerf_cad_core.geom namespace.

5. Out-of-range face_id raises ValueError.

No network, no OCCT, no external fixtures.
"""
from __future__ import annotations

import pytest
import numpy as np

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.direct_edit import move_face, push_pull_face
from kerf_cad_core.geom.history.direct_edit import _body_volume


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _box(dx=2.0, dy=3.0, dz=4.0):
    return box_to_body(corner=(0.0, 0.0, 0.0), dx=dx, dy=dy, dz=dz)


def _topo_counts(body):
    return {
        "V": len(body.all_vertices()),
        "E": len(body.all_edges()),
        "F": len(body.all_faces()),
    }


def _face_id_with_normal(body, target_normal):
    """Return the integer face index whose outward normal ≈ target_normal."""
    tn = np.asarray(target_normal, dtype=float)
    for idx, f in enumerate(body.all_faces()):
        n = np.asarray(f.surface.normal(0.5, 0.5), dtype=float)
        nm = float(np.linalg.norm(n))
        if nm < 1e-14:
            continue
        n = n / nm
        if float(np.linalg.norm(n - tn)) < 1e-6:
            return idx
    raise AssertionError(f"no face with normal {target_normal}")


def _face_area_for_normal(body, target_normal):
    """Polygon area (triangle-fan) of the face whose outward normal ≈ target."""
    tn = np.asarray(target_normal, dtype=float)
    for f in body.all_faces():
        n = np.asarray(f.surface.normal(0.5, 0.5), dtype=float)
        nm = float(np.linalg.norm(n))
        if nm < 1e-14:
            continue
        n = n / nm
        if float(np.linalg.norm(n - tn)) < 1e-6:
            outer = f.outer_loop()
            if outer is None or len(outer.coedges) < 3:
                return 0.0
            pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
            p0 = pts[0]
            total = 0.0
            for i in range(1, len(pts) - 1):
                a = pts[i] - p0
                b = pts[i + 1] - p0
                total += 0.5 * float(np.linalg.norm(np.cross(a, b)))
            return total
    raise AssertionError(f"no face with normal {target_normal}")


# ---------------------------------------------------------------------------
# Oracle 1: push_pull_face — volume change = face_area * distance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d", [0.5, 1.0, 2.0])
def test_push_pull_top_face_outward_volume(d):
    """Push the +Z (top) face up by d: volume must increase by face_area*d."""
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    area = _face_area_for_normal(body, (0.0, 0.0, 1.0))  # = 2*3 = 6

    body_after = push_pull_face(body, fid, d)

    vol_before = _body_volume(body)
    vol_after = _body_volume(body_after)
    assert vol_after - vol_before == pytest.approx(area * d, rel=1e-5)


def test_push_pull_top_face_inward_volume():
    """Push the +Z face inward by 1.0: volume must decrease by face_area*1."""
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    area = _face_area_for_normal(body, (0.0, 0.0, 1.0))

    body_after = push_pull_face(body, fid, -1.0)

    vol_before = _body_volume(body)
    vol_after = _body_volume(body_after)
    assert vol_before - vol_after == pytest.approx(area * 1.0, rel=1e-5)


# ---------------------------------------------------------------------------
# Oracle 1b: topology unchanged (V/E/F counts identical)
# ---------------------------------------------------------------------------

def test_push_pull_topology_unchanged():
    """After push_pull, V/E/F counts must match the original box."""
    body = _box()
    before = _topo_counts(body)
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    body_after = push_pull_face(body, fid, 1.5)
    after = _topo_counts(body_after)
    assert after == before


def test_push_pull_result_is_valid():
    """push_pull_face result must pass validate_body."""
    body = _box()
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    body_after = push_pull_face(body, fid, 0.75)
    validate_body(body_after)


# ---------------------------------------------------------------------------
# Oracle 2: move_face with zero vector is identity
# ---------------------------------------------------------------------------

def test_move_face_zero_vec_is_identity():
    """move_face by [0,0,0] must return a body with identical volume + topology."""
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    vol_before = _body_volume(body)
    topo_before = _topo_counts(body)

    for fid in range(len(body.all_faces())):
        body_after = move_face(body, fid, [0.0, 0.0, 0.0])
        assert _body_volume(body_after) == pytest.approx(vol_before, rel=1e-9)
        assert _topo_counts(body_after) == topo_before


# ---------------------------------------------------------------------------
# Oracle 3: move_face along normal matches push_pull_face
# ---------------------------------------------------------------------------

def test_move_face_along_normal_matches_push_pull():
    """move_face by (normal*d) must yield the same volume as push_pull_face(d)."""
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    d = 1.0
    normal = np.array([0.0, 0.0, 1.0])

    body_pp = push_pull_face(body, fid, d)
    body_mv = move_face(body, fid, (normal * d).tolist())

    assert _body_volume(body_mv) == pytest.approx(_body_volume(body_pp), rel=1e-9)


def test_move_face_in_plane_component_has_no_effect():
    """A translation vector perpendicular to the face normal produces no
    volume change (the in-plane component is discarded)."""
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    vol_before = _body_volume(body)
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    # Move purely in-plane (no Z component for +Z face)
    body_after = move_face(body, fid, [5.0, -3.0, 0.0])
    assert _body_volume(body_after) == pytest.approx(vol_before, rel=1e-9)


# ---------------------------------------------------------------------------
# Oracle 4: symbols visible in geom namespace
# ---------------------------------------------------------------------------

def test_geom_namespace_exports():
    """push_pull_face and move_face must be importable from geom namespace."""
    import kerf_cad_core.geom as geom
    assert hasattr(geom, "push_pull_face")
    assert hasattr(geom, "move_face")
    assert geom.push_pull_face is push_pull_face
    assert geom.move_face is move_face


def test_geom_all_includes_new_symbols():
    """push_pull_face and move_face must appear in geom.__all__."""
    import kerf_cad_core.geom as geom
    assert "push_pull_face" in geom.__all__
    assert "move_face" in geom.__all__


# ---------------------------------------------------------------------------
# Oracle 5: out-of-range face_id raises ValueError
# ---------------------------------------------------------------------------

def test_push_pull_out_of_range_raises():
    body = _box()
    n = len(body.all_faces())  # 6 for a box
    with pytest.raises(ValueError, match="face_id"):
        push_pull_face(body, n, 1.0)
    with pytest.raises(ValueError, match="face_id"):
        push_pull_face(body, -1, 1.0)


def test_move_face_out_of_range_raises():
    body = _box()
    n = len(body.all_faces())
    with pytest.raises(ValueError, match="face_id"):
        move_face(body, n, [0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="face_id"):
        move_face(body, -1, [0.0, 0.0, 1.0])


# ---------------------------------------------------------------------------
# Immutability: original body is never mutated
# ---------------------------------------------------------------------------

def test_push_pull_does_not_mutate_input():
    body = _box()
    vol_before = _body_volume(body)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    push_pull_face(body, fid, 2.0)
    assert _body_volume(body) == pytest.approx(vol_before, rel=1e-12)


def test_move_face_does_not_mutate_input():
    body = _box()
    vol_before = _body_volume(body)
    fid = _face_id_with_normal(body, (0.0, 1.0, 0.0))
    move_face(body, fid, [0.0, 1.0, 0.0])
    assert _body_volume(body) == pytest.approx(vol_before, rel=1e-12)
