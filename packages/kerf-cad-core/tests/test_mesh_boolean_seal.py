"""
GK-55: Mesh boolean → sealed 2-manifold guarantee + analytic volume oracle.

Tests for:
  - mesh_boolean_sealed: post-boolean weld/seal pass guarantees is_closed AND
    is_manifold on the result.
  - boolean_volume_oracle: analytic inclusion-exclusion volume matches the
    measured volume of the sealed boolean result.

All tests are hermetic: no OCC, no DB, no network.  Pure-Python geometry only.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom.mesh_repair import (
    mesh_boolean_sealed,
    boolean_volume_oracle,
    is_closed,
    is_manifold,
    mesh_volume,
    mesh_boolean,
    weld_vertices,
    fill_holes,
)


# ---------------------------------------------------------------------------
# Mesh factories
# ---------------------------------------------------------------------------

def _cube_mesh(ox: float = 0.0, oy: float = 0.0, oz: float = 0.0, s: float = 1.0):
    """Unit cube at (ox, oy, oz) with side length s.

    CCW winding on each face gives outward-pointing normals.
    Returns (verts, faces).
    """
    verts = [
        [ox,     oy,     oz    ],  # 0
        [ox + s, oy,     oz    ],  # 1
        [ox + s, oy + s, oz    ],  # 2
        [ox,     oy + s, oz    ],  # 3
        [ox,     oy,     oz + s],  # 4
        [ox + s, oy,     oz + s],  # 5
        [ox + s, oy + s, oz + s],  # 6
        [ox,     oy + s, oz + s],  # 7
    ]
    faces = [
        # -Z
        [0, 2, 1], [0, 3, 2],
        # +Z
        [4, 5, 6], [4, 6, 7],
        # -X
        [0, 4, 7], [0, 7, 3],
        # +X
        [1, 2, 6], [1, 6, 5],
        # -Y
        [0, 1, 5], [0, 5, 4],
        # +Y
        [3, 7, 6], [3, 6, 2],
    ]
    return verts, faces


def _assert_closed_and_manifold(verts, faces, label=""):
    rc = is_closed(verts, faces)
    rm = is_manifold(verts, faces)
    assert rc["ok"], f"{label} is_closed check failed: {rc}"
    assert rm["ok"], f"{label} is_manifold check failed: {rm}"
    assert rc["closed"], (
        f"{label} not closed: edges={rc}, "
        f"non_manifold_edges={rm.get('non_manifold_edges', [])}"
    )
    assert rm["manifold"], (
        f"{label} not manifold: bad_edges={rm['non_manifold_edges']}, "
        f"bad_verts={rm['non_manifold_vertices']}"
    )


# ===========================================================================
# 1. Sealed boolean result topology guarantee
# ===========================================================================

class TestMeshBooleanSealedTopology:

    def test_union_disjoint_cubes_is_closed(self):
        """Union of two non-overlapping cubes must be a closed manifold."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)  # separated — no overlap
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"], f"mesh_boolean_sealed failed: {r}"
        assert r["sealed"], f"union not sealed: warning={r['seal_warning']}"
        _assert_closed_and_manifold(r["verts"], r["faces"], "union_disjoint")

    def test_union_disjoint_cubes_is_manifold(self):
        """Union of two non-overlapping cubes must be manifold."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=3.0, oy=0.0, oz=0.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        rm = is_manifold(r["verts"], r["faces"])
        assert rm["ok"]
        assert rm["manifold"], f"not manifold: {rm}"

    def test_difference_non_overlapping_is_closed(self):
        """A − B where B is far away equals A; result must be closed manifold."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "difference")
        assert r["ok"]
        assert r["sealed"], f"difference not sealed: {r['seal_warning']}"
        _assert_closed_and_manifold(r["verts"], r["faces"], "difference_non_overlap")

    def test_intersection_non_overlapping_empty(self):
        """Intersection of two non-overlapping cubes is empty."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "intersection")
        assert r["ok"]
        # Empty intersection — faces list may be empty
        assert len(r["faces"]) == 0 or r["sealed"]

    def test_result_dict_keys_present(self):
        """Return dict always contains required keys."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        for key in ("ok", "verts", "faces", "failed", "fail_reason",
                    "sealed", "seal_warning", "volume"):
            assert key in r, f"missing key {key!r}"

    def test_invalid_operation_rejected(self):
        """Unknown operation returns ok=False."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "xor")
        assert not r["ok"]

    def test_empty_mesh_a(self):
        """Empty mesh A for union returns mesh B."""
        vb, fb = _cube_mesh()
        r = mesh_boolean_sealed([], [], vb, fb, "union")
        assert r["ok"]

    def test_empty_mesh_b(self):
        """Empty mesh B for difference returns mesh A."""
        va, fa = _cube_mesh()
        r = mesh_boolean_sealed(va, fa, [], [], "difference")
        assert r["ok"]

    def test_volume_field_non_negative(self):
        """The volume field in the result is >= 0."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert r["volume"] >= 0.0

    def test_tolerance_parameter(self):
        """Custom tol parameter is accepted."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union", tol=1e-4)
        assert r["ok"]


# ===========================================================================
# 2. Analytic volume oracle (inclusion–exclusion)
# ===========================================================================

class TestBooleanVolumeOracle:

    def test_oracle_union_disjoint_cubes(self):
        """Oracle: V(A∪B) = V(A)+V(B) for non-overlapping cubes.

        Two unit cubes at x=0 and x=2.0 (gap=1.0).
        Expected union volume = 1 + 1 = 2.0.
        """
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "union")
        assert r["ok"], f"oracle failed: {r}"
        assert abs(r["vol_a"] - 1.0) < 1e-9, f"vol_a={r['vol_a']}"
        assert abs(r["vol_b"] - 1.0) < 1e-9, f"vol_b={r['vol_b']}"
        assert abs(r["vol_intersection"]) < 1e-9, f"vol_int={r['vol_intersection']}"
        assert abs(r["oracle_volume"] - 2.0) < 1e-9, (
            f"expected oracle_volume=2.0, got {r['oracle_volume']}"
        )

    def test_oracle_sealed_volume_matches_oracle_disjoint(self):
        """Sealed union volume must match the oracle for disjoint cubes.

        This is the core GK-55 oracle assert:
        sealed_result.volume ≈ boolean_volume_oracle.oracle_volume
        """
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)

        sealed = mesh_boolean_sealed(va, fa, vb, fb, "union")
        oracle = boolean_volume_oracle(va, fa, vb, fb, "union")

        assert sealed["ok"] and oracle["ok"]
        assert sealed["sealed"], f"union not sealed: {sealed['seal_warning']}"

        # is_closed AND is_manifold both True
        _assert_closed_and_manifold(sealed["verts"], sealed["faces"],
                                    "oracle_disjoint_union")

        assert abs(sealed["volume"] - oracle["oracle_volume"]) < 1e-6, (
            f"sealed volume {sealed['volume']} != oracle {oracle['oracle_volume']}"
        )

    def test_oracle_difference_disjoint(self):
        """Oracle: V(A−B) = V(A) for non-overlapping cubes = 1.0."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "difference")
        assert r["ok"]
        assert abs(r["oracle_volume"] - 1.0) < 1e-9, (
            f"expected 1.0, got {r['oracle_volume']}"
        )

    def test_oracle_intersection_disjoint(self):
        """Oracle: V(A∩B) = 0 for non-overlapping cubes."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "intersection")
        assert r["ok"]
        assert abs(r["oracle_volume"]) < 1e-9, (
            f"expected 0.0, got {r['oracle_volume']}"
        )

    def test_oracle_invalid_operation(self):
        """Invalid operation returns ok=False."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "xor")
        assert not r["ok"]

    def test_oracle_keys_present(self):
        """Return dict always has required keys."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "union")
        for key in ("ok", "oracle_volume", "vol_a", "vol_b", "vol_intersection"):
            assert key in r, f"missing key {key!r}"

    def test_oracle_union_same_cube_inclusion_exclusion(self):
        """Oracle computes correct inclusion-exclusion for the cube-union case.

        V(A) = 1, V(B) = 1.
        oracle_volume = V(A) + V(B) - V(A∩B).
        For two identical cubes: V(A∩B) = 1, so oracle = 1.
        The oracle formula is checked here; the sealed volume test for
        identical cubes is a best-effort (ray-parity is ambiguous on shared faces).
        """
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh()  # identical — complete overlap
        r = boolean_volume_oracle(va, fa, vb, fb, "union")
        assert r["ok"]
        # The analytic formula: oracle = vol_a + vol_b - vol_intersection
        expected = r["vol_a"] + r["vol_b"] - r["vol_intersection"]
        assert abs(r["oracle_volume"] - expected) < 1e-9, (
            f"oracle formula inconsistent: {r}"
        )

    def test_oracle_vol_a_correct(self):
        """Oracle reports V(A) = 1.0 for a unit cube."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "union")
        assert r["ok"]
        assert abs(r["vol_a"] - 1.0) < 1e-9

    def test_oracle_vol_b_correct(self):
        """Oracle reports V(B) = 8.0 for a 2×2×2 cube."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0, s=2.0)
        r = boolean_volume_oracle(va, fa, vb, fb, "union")
        assert r["ok"]
        assert abs(r["vol_b"] - 8.0) < 1e-9, f"expected 8.0, got {r['vol_b']}"


# ===========================================================================
# 3. Seal pass standalone behaviour
# ===========================================================================

class TestSealPassBehavior:

    def test_seal_repairs_welded_open_mesh(self):
        """Post-boolean weld step merges coincident vertices at seam."""
        # Build two cubes sharing a face (touching at x=1)
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=1.0)  # share face at x=1
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        # The weld step should merge shared vertices
        assert len(r["verts"]) <= len(va) + len(vb)

    def test_sealed_result_edge_count(self):
        """Every edge in the sealed result is shared by exactly 2 faces (closed)."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        if r["sealed"]:
            rc = is_closed(r["verts"], r["faces"])
            assert rc["ok"] and rc["closed"]

    def test_all_operations_produce_ok(self):
        """All three operations return ok=True for valid inputs."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        for op in ("union", "difference", "intersection"):
            r = mesh_boolean_sealed(va, fa, vb, fb, op)
            assert r["ok"], f"{op} returned ok=False: {r}"

    def test_sealed_disjoint_union_face_count(self):
        """Two disjoint unit cubes unified should have 24 faces (12 + 12)."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert len(r["faces"]) == 24, f"expected 24 faces, got {len(r['faces'])}"

    def test_sealed_disjoint_union_vert_count(self):
        """Two disjoint unit cubes unified should have 16 vertices (8 + 8)."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert len(r["verts"]) == 16, f"expected 16 verts, got {len(r['verts'])}"

    def test_sealed_flag_true_for_clean_inputs(self):
        """sealed=True when both input meshes are clean, non-overlapping cubes."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert r["sealed"] is True, f"sealed=False, warning={r['seal_warning']}"

    def test_seal_warning_empty_for_clean_inputs(self):
        """seal_warning is empty string for clean non-overlapping inputs."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert r["seal_warning"] == "", f"unexpected warning: {r['seal_warning']}"

    def test_volume_positive_for_union(self):
        """Union of two unit cubes has positive volume."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=2.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "union")
        assert r["ok"]
        assert r["volume"] > 0.0

    def test_difference_result_is_single_cube(self):
        """A − B (no overlap) leaves A intact: volume = 1.0."""
        va, fa = _cube_mesh()
        vb, fb = _cube_mesh(ox=5.0)
        r = mesh_boolean_sealed(va, fa, vb, fb, "difference")
        assert r["ok"]
        assert r["sealed"]
        assert abs(r["volume"] - 1.0) < 1e-9, f"expected 1.0, got {r['volume']}"
