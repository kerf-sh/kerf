"""
test_subd_bevel_weight.py
=========================
Hermetic pytest oracle for GK-107: bevel weight per edge (graded crease).

Oracle guarantees
-----------------
* weight=1.0  → limit surface positions match those produced by
  subd_set_crease(cage, eid, math.inf) — hard-crease limit.
* weight=0.0  → limit surface positions match the smooth (no-crease) limit.
* intermediate weight → positions lie strictly between smooth and hard limits
  (i.e. strictly closer to smooth than weight=1.0 and strictly further than
  weight=0.0 for vertices incident on the weighted edge).

No OCC, no database, no network.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import pytest

from kerf_cad_core.geom.subd_authoring import (
    SubDCage,
    create_subd_primitive,
    subd_set_crease,
    subd_set_bevel_weight,
    to_subd_surface,
)
from kerf_cad_core.geom.subd_to_nurbs import (
    subd_limit_positions,
    subd_limit_positions_bevel_weighted,
)
from kerf_cad_core.geom.subd import SubDMesh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cage_to_mesh_no_crease(cage: SubDCage) -> SubDMesh:
    """Return SubDMesh from cage with all creases stripped."""
    return SubDMesh(
        vertices=[list(v) for v in cage.vertices],
        faces=[list(f) for f in cage.faces],
        creases={},
    )


def _cage_to_mesh_hard_crease(cage: SubDCage, edge_id: int) -> SubDMesh:
    """Return SubDMesh from cage with a hard crease (1.0) on the given edge."""
    edges = cage.cage_edges()
    a, b = edges[edge_id]
    return SubDMesh(
        vertices=[list(v) for v in cage.vertices],
        faces=[list(f) for f in cage.faces],
        creases={(min(a, b), max(a, b)): 1.0},
    )


def _limit_positions_smooth(cage: SubDCage) -> List[np.ndarray]:
    mesh = _cage_to_mesh_no_crease(cage)
    return subd_limit_positions(mesh)


def _limit_positions_hard(cage: SubDCage, edge_id: int) -> List[np.ndarray]:
    mesh = _cage_to_mesh_hard_crease(cage, edge_id)
    return subd_limit_positions(mesh)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cube_cage() -> SubDCage:
    return create_subd_primitive("cube", width=2, height=2, depth=2)


# ---------------------------------------------------------------------------
# Unit: subd_set_bevel_weight API
# ---------------------------------------------------------------------------

def test_bevel_weight_stored(cube_cage):
    """Weight is stored in bevel_weights; doesn't touch sharpness."""
    edges = cube_cage.cage_edges()
    eid = 0
    result = subd_set_bevel_weight(cube_cage, eid, 0.5)
    assert result.bevel_weights.get(eid) == pytest.approx(0.5)
    assert result.sharpness == {}  # sharpness dict untouched


def test_bevel_weight_zero_removes_entry(cube_cage):
    """Setting weight=0.0 removes the entry (no-op on smooth)."""
    eid = 0
    c1 = subd_set_bevel_weight(cube_cage, eid, 0.7)
    c2 = subd_set_bevel_weight(c1, eid, 0.0)
    assert eid not in c2.bevel_weights


def test_bevel_weight_clamped(cube_cage):
    """Weights outside [0,1] are clamped."""
    eid = 0
    c_high = subd_set_bevel_weight(cube_cage, eid, 5.0)
    assert c_high.bevel_weights[eid] == pytest.approx(1.0)
    c_neg = subd_set_bevel_weight(cube_cage, eid, -0.3)
    assert eid not in c_neg.bevel_weights


def test_bevel_weight_invalid_edge_noop(cube_cage):
    """Out-of-range edge id returns an unchanged copy, never raises."""
    result = subd_set_bevel_weight(cube_cage, 9999, 0.5)
    assert result.bevel_weights == {}


def test_bevel_weight_immutable(cube_cage):
    """subd_set_bevel_weight returns a new cage; original is unchanged."""
    eid = 0
    _ = subd_set_bevel_weight(cube_cage, eid, 0.9)
    assert eid not in cube_cage.bevel_weights


def test_bevel_weight_exported_from_geom():
    """subd_set_bevel_weight is exported from kerf_cad_core.geom."""
    from kerf_cad_core import geom
    assert hasattr(geom, "subd_set_bevel_weight")


# ---------------------------------------------------------------------------
# Oracle 1: weight=0.0 → smooth limit
# ---------------------------------------------------------------------------

def test_weight_zero_matches_smooth_limit(cube_cage):
    """
    A cage with bevel weight 0.0 on an edge must produce the same CC limit
    positions as a cage with no crease on that edge.
    """
    eid = 0
    # Explicitly set weight=0 then strip (same as no entry)
    cage_w0 = subd_set_bevel_weight(cube_cage, eid, 0.0)

    # Smooth limit via SubDMesh (no creases)
    smooth_lim = _limit_positions_smooth(cube_cage)

    # Bevel-weight-aware limit (no weights → smooth)
    bw_lim = subd_limit_positions_bevel_weighted(cage_w0)

    for i, (sp, bp) in enumerate(zip(smooth_lim, bw_lim)):
        np.testing.assert_allclose(
            bp, sp, atol=1e-12,
            err_msg=f"vertex {i}: weight=0 should match smooth limit",
        )


# ---------------------------------------------------------------------------
# Oracle 2: weight=1.0 → hard-crease limit
# ---------------------------------------------------------------------------

def test_weight_one_matches_hard_crease_limit(cube_cage):
    """
    A cage with bevel weight 1.0 on an edge must produce CC limit positions
    that match subd_set_crease(cage, eid, math.inf) for vertices incident
    on that edge.
    """
    eid = 0
    edges = cube_cage.cage_edges()
    a, b = edges[eid]

    # Hard crease via subd_set_crease
    cage_hard = subd_set_crease(cube_cage, eid, math.inf)
    hard_mesh = cage_hard.to_subd_mesh()
    hard_lim = subd_limit_positions(hard_mesh)

    # Bevel weight = 1.0
    cage_bw1 = subd_set_bevel_weight(cube_cage, eid, 1.0)
    bw_lim = subd_limit_positions_bevel_weighted(cage_bw1)

    # Vertices incident on the creased edge must match
    for vi in (a, b):
        np.testing.assert_allclose(
            bw_lim[vi], hard_lim[vi], atol=1e-9,
            err_msg=f"vertex {vi}: weight=1.0 should match hard-crease limit",
        )


# ---------------------------------------------------------------------------
# Oracle 3: intermediate weight lies strictly between smooth and hard limits
# ---------------------------------------------------------------------------

def test_intermediate_weight_between_smooth_and_hard(cube_cage):
    """
    For weight=0.5, each vertex on the weighted edge must lie strictly
    between the smooth limit and the hard-crease limit.
    """
    eid = 0
    edges = cube_cage.cage_edges()
    a, b = edges[eid]

    smooth_lim = _limit_positions_smooth(cube_cage)
    hard_lim = _limit_positions_hard(cube_cage, eid)

    cage_bw = subd_set_bevel_weight(cube_cage, eid, 0.5)
    bw_lim = subd_limit_positions_bevel_weighted(cage_bw)

    for vi in (a, b):
        sp = smooth_lim[vi]
        hp = hard_lim[vi]
        mp = bw_lim[vi]

        # Displacement from smooth to hard limit
        delta = np.linalg.norm(hp - sp)
        if delta < 1e-12:
            # Smooth and hard limits coincide → bevel has no geometric effect
            continue

        # Distance from smooth to intermediate must be strictly less than
        # distance from smooth to hard (i.e. 0 < frac < 1).
        d_from_smooth = np.linalg.norm(mp - sp)
        frac = d_from_smooth / delta
        assert 0.0 < frac < 1.0, (
            f"vertex {vi}: intermediate weight not strictly between limits "
            f"(frac={frac:.4f})"
        )


# ---------------------------------------------------------------------------
# Oracle 4: to_subd_surface honors bevel weight via to_subd_mesh
# ---------------------------------------------------------------------------

def test_to_subd_surface_weight_one_vs_hard_crease(cube_cage):
    """
    to_subd_surface on a cage with bevel weight=1.0 must produce the same
    CC-subdivided mesh as to_subd_surface on a cage with subd_set_crease(inf).
    """
    eid = 0
    edges = cube_cage.cage_edges()
    a, b = edges[eid]

    # Hard crease path
    cage_hard = subd_set_crease(cube_cage, eid, math.inf)
    surf_hard = to_subd_surface(cage_hard, levels=1)

    # Bevel weight=1.0 path
    cage_bw1 = subd_set_bevel_weight(cube_cage, eid, 1.0)
    surf_bw1 = to_subd_surface(cage_bw1, levels=1)

    # Same vertex count
    assert surf_bw1.mesh.num_vertices == surf_hard.mesh.num_vertices

    # Vertex positions should match (both go through same CC + crease=1.0 path)
    verts_hard = sorted(tuple(v) for v in surf_hard.mesh.vertices)
    verts_bw1 = sorted(tuple(v) for v in surf_bw1.mesh.vertices)
    for vh, vb in zip(verts_hard, verts_bw1):
        np.testing.assert_allclose(
            np.array(vb), np.array(vh), atol=1e-9,
            err_msg="to_subd_surface: weight=1.0 should match hard-crease",
        )


def test_to_subd_surface_weight_zero_smooth(cube_cage):
    """
    to_subd_surface on a cage with bevel weight=0.0 (removed) must produce
    the same CC-subdivided mesh as a cage with no crease.
    """
    eid = 0
    # No bevel weight (smooth)
    surf_smooth = to_subd_surface(cube_cage, levels=1)

    # Weight=0 (removed)
    cage_w0 = subd_set_bevel_weight(cube_cage, eid, 0.0)
    surf_w0 = to_subd_surface(cage_w0, levels=1)

    assert surf_w0.mesh.num_vertices == surf_smooth.mesh.num_vertices

    verts_smooth = sorted(tuple(v) for v in surf_smooth.mesh.vertices)
    verts_w0 = sorted(tuple(v) for v in surf_w0.mesh.vertices)
    for vs, vw in zip(verts_smooth, verts_w0):
        np.testing.assert_allclose(
            np.array(vw), np.array(vs), atol=1e-12,
            err_msg="to_subd_surface: weight=0.0 should match smooth",
        )


# ---------------------------------------------------------------------------
# Oracle 5: subd_limit_positions_bevel_weighted direct interpolation check
# ---------------------------------------------------------------------------

def test_bevel_weight_interpolation_exact(cube_cage):
    """
    For weight w, each incident vertex's limit position must be exactly:
        smooth_lim + w * (hard_lim - smooth_lim)
    """
    eid = 0
    edges = cube_cage.cage_edges()
    a, b = edges[eid]

    smooth_lim = _limit_positions_smooth(cube_cage)
    hard_lim = _limit_positions_hard(cube_cage, eid)

    for w in (0.25, 0.5, 0.75):
        cage_bw = subd_set_bevel_weight(cube_cage, eid, w)
        bw_lim = subd_limit_positions_bevel_weighted(cage_bw)

        for vi in (a, b):
            expected = smooth_lim[vi] + w * (hard_lim[vi] - smooth_lim[vi])
            np.testing.assert_allclose(
                bw_lim[vi], expected, atol=1e-12,
                err_msg=f"vertex {vi}, weight={w}: interpolation mismatch",
            )
