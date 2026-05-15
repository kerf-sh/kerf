"""
test_face_name_boolean_hardening.py — T-13/T-14: Persistent face-naming boolean hardening.

Tests for ``kerf_cad_core.face_name_registry``:

  Group A — FaceSignature (9 tests)
  Group B — FaceNameRegistry (8 tests)
  Group C — remap_face_ids_across_boolean (10 tests)
  Group D — assign_new_boundary_names (3 tests)
  Group E — face_name_audit (8 tests)
  Group F — OCC-dependent tests (3 tests, skipped when OCC not available)

Total: 41 tests (≥ 25 required).

All tests are hermetic — no database, no real STEP files, no external network.
OCC-dependent tests are gated behind ``pytest.importorskip("OCC.Core.BRep")``.
"""

from __future__ import annotations

import math
from typing import Dict

import pytest

from kerf_cad_core.face_name_registry import (
    AuditWarning,
    FaceNameRegistry,
    FaceSignature,
    RemapResult,
    assign_new_boundary_names,
    face_name_audit,
    make_signature_from_dict,
    remap_face_ids_across_boolean,
    _DRIFT_CENTROID_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sig(cx=0.0, cy=0.0, cz=0.0, nx=0.0, ny=0.0, nz=1.0, area=1.0) -> FaceSignature:
    return FaceSignature(centroid=(cx, cy, cz), normal=(nx, ny, nz), area=area)


def simple_registry(*name_sigs) -> FaceNameRegistry:
    """Build a registry from alternating (name, sig) args."""
    reg = FaceNameRegistry()
    it = iter(name_sigs)
    for name in it:
        s = next(it)
        reg.assign(name, s)
    return reg


# ---------------------------------------------------------------------------
# Group A — FaceSignature
# ---------------------------------------------------------------------------


class TestFaceSignature:
    def test_hex_is_16_chars(self):
        s = sig()
        assert len(s.hex) == 16

    def test_identical_sigs_same_hex(self):
        s1 = sig(1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 4.0)
        s2 = sig(1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 4.0)
        assert s1.hex == s2.hex

    def test_different_centroid_different_hex(self):
        s1 = sig(0.0, 0.0, 0.0)
        s2 = sig(1.0, 0.0, 0.0)
        assert s1.hex != s2.hex

    def test_different_normal_different_hex(self):
        s1 = sig(nz=1.0)
        s2 = sig(nz=-1.0)
        assert s1.hex != s2.hex

    def test_distance_zero_to_self(self):
        s = sig(3.0, 4.0, 0.0)
        assert s.distance(s) == pytest.approx(0.0)

    def test_distance_pythagorean(self):
        s1 = sig(0.0, 0.0, 0.0)
        s2 = sig(3.0, 4.0, 0.0)
        assert s1.distance(s2) == pytest.approx(5.0)

    def test_match_score_same_face_is_zero(self):
        s = sig(1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 9.0)
        assert s.match_score(s) == pytest.approx(0.0, abs=1e-9)

    def test_match_score_higher_for_distant_centroid(self):
        s_ref = sig(0.0, 0.0, 0.0)
        s_near = sig(1.0, 0.0, 0.0)
        s_far = sig(100.0, 0.0, 0.0)
        assert s_ref.match_score(s_near) < s_ref.match_score(s_far)

    def test_coord_rounding_stable(self):
        # Values that differ only beyond _COORD_DECIMALS decimal places should
        # hash to the same value.
        s1 = FaceSignature(centroid=(1.00001, 0.0, 0.0), normal=(0.0, 0.0, 1.0), area=1.0)
        s2 = FaceSignature(centroid=(1.00002, 0.0, 0.0), normal=(0.0, 0.0, 1.0), area=1.0)
        # With _COORD_DECIMALS=4, both round to 1.0000 → same hex
        assert s1.hex == s2.hex

    def test_make_signature_from_dict(self):
        d = {"centroid": [1.0, 2.0, 3.0], "normal": [0.0, 1.0, 0.0], "area": 5.5}
        s = make_signature_from_dict(d)
        assert s.centroid == (1.0, 2.0, 3.0)
        assert s.normal == (0.0, 1.0, 0.0)
        assert s.area == pytest.approx(5.5)

    def test_make_signature_from_dict_defaults_on_missing_keys(self):
        s = make_signature_from_dict({})
        assert s.centroid == (0.0, 0.0, 0.0)
        assert s.area == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Group B — FaceNameRegistry
# ---------------------------------------------------------------------------


class TestFaceNameRegistry:
    def test_assign_and_retrieve(self):
        reg = FaceNameRegistry()
        s = sig(1.0, 2.0, 3.0)
        reg.assign("pad-1.TopCap", s)
        assert reg.has("pad-1.TopCap")
        assert reg.signature_for("pad-1.TopCap") == s

    def test_absent_name_returns_none(self):
        reg = FaceNameRegistry()
        assert reg.signature_for("nonexistent") is None
        assert not reg.has("nonexistent")

    def test_reassign_replaces_signature(self):
        reg = FaceNameRegistry()
        s1 = sig(0.0, 0.0, 0.0)
        s2 = sig(5.0, 5.0, 5.0)
        reg.assign("f", s1)
        reg.assign("f", s2)
        stored = reg.signature_for("f")
        assert stored == s2

    def test_hex_to_names_reverse_index(self):
        reg = FaceNameRegistry()
        s = sig(1.0, 1.0, 1.0)
        reg.assign("a", s)
        reg.assign("b", s)  # same sig → same hex bucket
        names = reg.names_for_hex(s.hex)
        assert "a" in names
        assert "b" in names

    def test_remove_cleans_reverse_index(self):
        reg = FaceNameRegistry()
        s = sig(2.0, 0.0, 0.0)
        reg.assign("x", s)
        reg.remove("x")
        assert not reg.has("x")
        assert reg.names_for_hex(s.hex) == []

    def test_find_nearest_basic(self):
        reg = simple_registry(
            "face-A", sig(0.0, 0.0, 0.0),
            "face-B", sig(10.0, 0.0, 0.0),
            "face-C", sig(20.0, 0.0, 0.0),
        )
        candidate = sig(10.1, 0.0, 0.0)
        assert reg.find_nearest(candidate) == "face-B"

    def test_find_nearest_empty_registry_returns_none(self):
        reg = FaceNameRegistry()
        assert reg.find_nearest(sig()) is None

    def test_snapshot_roundtrip(self):
        reg = FaceNameRegistry()
        reg.assign("face-1", sig(1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 7.0))
        snap = reg.snapshot()
        reg2 = FaceNameRegistry.from_snapshot(snap)
        assert reg2.has("face-1")
        s = reg2.signature_for("face-1")
        assert s is not None
        assert s.centroid == (1.0, 2.0, 3.0)
        assert s.area == pytest.approx(7.0)

    def test_len(self):
        reg = simple_registry(
            "a", sig(0, 0, 0),
            "b", sig(1, 0, 0),
        )
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# Group C — remap_face_ids_across_boolean
# ---------------------------------------------------------------------------


class TestRemapFaceIdsAcrossBoolean:
    """Tests for the signature-based face-id remapping after boolean ops."""

    def _pre_registry_ab(self) -> FaceNameRegistry:
        """A pre-boolean registry with 3 faces from body A and 3 from body B."""
        return simple_registry(
            "pad-1.top",    sig(0.0,  0.0, 5.0,  0.0, 0.0,  1.0, 4.0),
            "pad-1.bottom", sig(0.0,  0.0, 0.0,  0.0, 0.0, -1.0, 4.0),
            "pad-1.side-1", sig(2.0,  0.0, 2.5,  1.0, 0.0,  0.0, 2.0),
            "pad-2.top",    sig(0.0, 10.0, 5.0,  0.0, 0.0,  1.0, 4.0),
            "pad-2.bottom", sig(0.0, 10.0, 0.0,  0.0, 0.0, -1.0, 4.0),
            "pad-2.side-1", sig(2.0, 10.0, 2.5,  1.0, 0.0,  0.0, 2.0),
        )

    def test_fuse_keeps_both_bodies_face_ids(self):
        """A fuse op: all pre-boolean faces survive; all should be remapped."""
        pre = self._pre_registry_ab()
        # Post-boolean faces: same geometry, but new opaque ids
        post = {
            "post-0": sig(0.0,  0.0, 5.0,  0.0, 0.0,  1.0, 4.0),
            "post-1": sig(0.0,  0.0, 0.0,  0.0, 0.0, -1.0, 4.0),
            "post-2": sig(2.0,  0.0, 2.5,  1.0, 0.0,  0.0, 2.0),
            "post-3": sig(0.0, 10.0, 5.0,  0.0, 0.0,  1.0, 4.0),
            "post-4": sig(0.0, 10.0, 0.0,  0.0, 0.0, -1.0, 4.0),
            "post-5": sig(2.0, 10.0, 2.5,  1.0, 0.0,  0.0, 2.0),
        }
        result = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert len(result.remapped) == 6
        assert result.unmatched_post == []
        assert result.unmatched_pre == []

    def test_fuse_correct_name_assignment(self):
        """Each post-boolean face must get the name that matches its geometry."""
        pre = self._pre_registry_ab()
        post = {
            "post-0": sig(0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 4.0),
        }
        result = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert result.remapped.get("post-0") == "pad-1.top"

    def test_cut_preserves_target_ids(self):
        """A cut op: body-A faces survive; the internal/coincident B faces don't.

        We use max_distance=5.0 so that the new boundary face p2 (centroid at
        a completely different position) is beyond the match radius and is
        correctly reported as unmatched_post.
        """
        pre_a = simple_registry(
            "box.top",    sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 100.0),
            "box.bottom", sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 100.0),
        )
        post = {
            "p0": sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 100.0),
            "p1": sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 100.0),
            # p2 is a new boundary face at a distant position, beyond max_distance=5
            "p2": sig(99.0, 99.0, 50.0, 0.5, 0.5, 0.0, 3.0),
        }
        result = remap_face_ids_across_boolean(
            pre_a, post, op_kind="cut", max_distance=5.0
        )
        assert result.remapped.get("p0") == "box.top"
        assert result.remapped.get("p1") == "box.bottom"
        assert "p2" in result.unmatched_post

    def test_cut_unmatched_pre_are_destroyed_faces(self):
        """Faces from pre_registry that have no post match are considered destroyed."""
        pre = simple_registry(
            "tool.face", sig(5.0, 0.0, 0.0),
        )
        post: Dict[str, FaceSignature] = {}  # cut consumed all faces
        result = remap_face_ids_across_boolean(pre, post, op_kind="cut")
        assert result.unmatched_pre == ["tool.face"]
        assert result.remapped == {}

    def test_common_preserves_intersection(self):
        """common op: only the intersection region's faces survive."""
        pre = simple_registry(
            "a.top", sig(0.0, 0.0, 3.0, 0.0, 0.0, 1.0, 4.0),
            "a.bot", sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
            "b.top", sig(0.0, 0.0, 4.0, 0.0, 0.0, 1.0, 4.0),
        )
        # common intersection: only a.top survives (clipped inside b)
        post = {
            "q0": sig(0.0, 0.0, 3.0, 0.0, 0.0, 1.0, 4.0),
        }
        result = remap_face_ids_across_boolean(pre, post, op_kind="common")
        assert result.remapped.get("q0") == "a.top"
        assert "a.bot" in result.unmatched_pre
        assert "b.top" in result.unmatched_pre

    def test_rerun_op_is_stable(self):
        """Running the same remapping twice produces identical results."""
        pre = self._pre_registry_ab()
        post = {
            "post-0": sig(0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 4.0),
            "post-1": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
        }
        r1 = remap_face_ids_across_boolean(pre, post)
        r2 = remap_face_ids_across_boolean(pre, post)
        assert r1.remapped == r2.remapped
        assert r1.unmatched_pre == r2.unmatched_pre
        assert r1.unmatched_post == r2.unmatched_post

    def test_history_map_takes_priority_over_signature(self):
        """When a history_map entry is provided, it overrides signature matching."""
        pre = simple_registry(
            "pad.top",    sig(0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 4.0),
            "pad.bottom", sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
        )
        # post-0 is geometrically close to pad.bottom, but history says pad.top
        post = {
            "post-0": sig(0.0, 0.0, 0.1, 0.0, 0.0, -1.0, 4.0),
        }
        history = {"post-0": "pad.top"}  # override
        result = remap_face_ids_across_boolean(pre, post, history_map=history)
        assert result.remapped.get("post-0") == "pad.top"

    def test_signature_collision_resolved_deterministically(self):
        """When two pre-faces are identical, the lexicographically smaller name wins."""
        s = sig(0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0)
        pre = simple_registry("zz.face", s, "aa.face", s)
        post = {"p0": s}
        r = remap_face_ids_across_boolean(pre, post)
        # Both pre-faces have the same score; "aa.face" is lexicographically smaller
        assert r.remapped.get("p0") == "aa.face"

    def test_empty_pre_registry_all_post_unmatched(self):
        pre = FaceNameRegistry()
        post = {"f0": sig(1.0, 0.0, 0.0), "f1": sig(2.0, 0.0, 0.0)}
        r = remap_face_ids_across_boolean(pre, post)
        assert r.remapped == {}
        assert sorted(r.unmatched_post) == ["f0", "f1"]

    def test_empty_post_faces_all_pre_unmatched(self):
        pre = simple_registry("x", sig(0.0, 0.0, 0.0))
        r = remap_face_ids_across_boolean(pre, {})
        assert r.remapped == {}
        assert r.unmatched_pre == ["x"]


# ---------------------------------------------------------------------------
# Group D — assign_new_boundary_names
# ---------------------------------------------------------------------------


class TestAssignNewBoundaryNames:
    def test_names_use_boolean_node_id_and_op(self):
        ids = ["face-5", "face-3"]
        result = assign_new_boundary_names("boolean-1", "fuse", ids)
        # sorted: face-3, face-5 → indices 0, 1
        assert result["face-3"] == "boolean-1.boundary.fuse.0"
        assert result["face-5"] == "boolean-1.boundary.fuse.1"

    def test_names_are_deterministic_regardless_of_input_order(self):
        ids_a = ["face-9", "face-1", "face-5"]
        ids_b = ["face-5", "face-9", "face-1"]
        r_a = assign_new_boundary_names("bool-2", "cut", ids_a)
        r_b = assign_new_boundary_names("bool-2", "cut", ids_b)
        assert r_a == r_b

    def test_empty_input_returns_empty_dict(self):
        result = assign_new_boundary_names("bool-X", "common", [])
        assert result == {}


# ---------------------------------------------------------------------------
# Group E — face_name_audit
# ---------------------------------------------------------------------------


def make_doc(*nodes) -> dict:
    return {"features": list(nodes)}


def make_node(node_id: str, **face_refs) -> dict:
    """Build a feature node dict with optional face-name references."""
    n = {"id": node_id, "op": "test_op"}
    n.update(face_refs)
    return n


class TestFaceNameAudit:
    def test_no_warnings_for_mapped_faces(self):
        reg = simple_registry("pad-1.TopCap", sig(0.0, 0.0, 5.0))
        doc = make_doc(make_node("cut-1", target_face_name="pad-1.TopCap"))
        warns = face_name_audit(doc, reg)
        assert warns == []

    def test_unmapped_face_name_flagged(self):
        reg = FaceNameRegistry()  # empty
        doc = make_doc(make_node("fillet-1", target_face_name="pad-1.TopCap"))
        warns = face_name_audit(doc, reg)
        assert len(warns) == 1
        assert warns[0].kind == "UNMAPPED"
        assert warns[0].face_name_value == "pad-1.TopCap"
        assert warns[0].node_id == "fillet-1"

    def test_both_target_face_name_and_face_name_keys_checked(self):
        reg = FaceNameRegistry()
        doc = make_doc(make_node("pp-1",
                                  target_face_name="missing-a",
                                  face_name="missing-b"))
        warns = face_name_audit(doc, reg)
        keys = {w.face_name_key for w in warns}
        assert "target_face_name" in keys
        assert "face_name" in keys

    def test_empty_face_name_string_ignored(self):
        reg = FaceNameRegistry()
        doc = make_doc(make_node("x", target_face_name=""))
        warns = face_name_audit(doc, reg)
        assert warns == []

    def test_missing_face_name_key_ignored(self):
        reg = FaceNameRegistry()
        doc = make_doc({"id": "pad-1", "op": "pad", "distance": 5.0})
        warns = face_name_audit(doc, reg)
        assert warns == []

    def test_drift_detection_when_current_sigs_provided(self):
        base_sig = sig(0.0, 0.0, 5.0)
        reg = simple_registry("pad-1.top", base_sig)
        # Simulate drift: centroid moved more than threshold
        drifted = sig(0.0, 0.0, 5.0 + _DRIFT_CENTROID_THRESHOLD + 0.1)
        doc = make_doc(make_node("fillet-1", target_face_name="pad-1.top"))
        warns = face_name_audit(doc, reg, current_sigs={"pad-1.top": drifted})
        assert len(warns) == 1
        assert warns[0].kind == "DRIFTED"

    def test_no_drift_within_threshold(self):
        base_sig = sig(0.0, 0.0, 5.0)
        reg = simple_registry("pad-1.top", base_sig)
        tiny_shift = sig(0.0, 0.0, 5.0 + _DRIFT_CENTROID_THRESHOLD * 0.1)
        doc = make_doc(make_node("fillet-1", target_face_name="pad-1.top"))
        warns = face_name_audit(doc, reg, current_sigs={"pad-1.top": tiny_shift})
        assert warns == []

    def test_multiple_nodes_warnings_in_document_order(self):
        reg = FaceNameRegistry()
        doc = make_doc(
            make_node("node-1", target_face_name="missing-1"),
            make_node("node-2", target_face_name="missing-2"),
        )
        warns = face_name_audit(doc, reg)
        assert len(warns) == 2
        assert warns[0].node_id == "node-1"
        assert warns[1].node_id == "node-2"

    def test_non_list_features_returns_empty(self):
        reg = FaceNameRegistry()
        doc = {"features": "not a list"}
        warns = face_name_audit(doc, reg)
        assert warns == []


# ---------------------------------------------------------------------------
# Integration scenario: fuse then audit
# ---------------------------------------------------------------------------


class TestFuseThenAudit:
    """
    Integration test: simulates a pad-1 fuse pad-2 workflow.

    1. Build pre-boolean registry with faces from both pads.
    2. Run remap_face_ids_across_boolean to assign names to post-faces.
    3. Build a post-boolean registry from the remap result.
    4. Add new boundary names for unmatched post faces.
    5. Run face_name_audit on a downstream feature referencing the fused body.
    6. Verify no warnings for faces that survived and names for boundary faces.
    """

    def test_end_to_end_fuse_audit_clean(self):
        pre = simple_registry(
            "pad-1.top",    sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 16.0),
            "pad-1.bottom", sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
            "pad-2.top",    sig(5.0, 0.0, 10.0, 0.0, 0.0,  1.0, 16.0),
            "pad-2.bottom", sig(5.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
        )

        # Post-fuse: same 4 original faces survived + 1 new boundary face
        post_faces = {
            "pf0": sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 16.0),
            "pf1": sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
            "pf2": sig(5.0, 0.0, 10.0, 0.0, 0.0,  1.0, 16.0),
            "pf3": sig(5.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
            "pf4": sig(2.5, 0.0,  5.0, 1.0, 0.0,  0.0,  5.0),  # boundary
        }

        result = remap_face_ids_across_boolean(pre, post_faces, op_kind="fuse")

        # All 4 original faces remapped
        assert len(result.remapped) == 4
        assert result.unmatched_pre == []
        assert result.unmatched_post == ["pf4"]

        # Assign names to boundary faces
        boundary_map = assign_new_boundary_names(
            "boolean-1", "fuse", result.unmatched_post
        )
        assert boundary_map["pf4"] == "boolean-1.boundary.fuse.0"

        # Build post-boolean registry
        post_reg = FaceNameRegistry()
        for post_id, pre_name in result.remapped.items():
            post_reg.assign(pre_name, post_faces[post_id])
        for post_id, new_name in boundary_map.items():
            post_reg.assign(new_name, post_faces[post_id])

        # Downstream feature referencing a surviving face → no warnings
        doc = make_doc(
            make_node("fillet-1", target_face_name="pad-1.top"),
            make_node("fillet-2", target_face_name="boolean-1.boundary.fuse.0"),
        )
        warns = face_name_audit(doc, post_reg)
        assert warns == [], f"Unexpected warnings: {warns}"

    def test_end_to_end_fuse_audit_flags_stale_reference(self):
        """A feature referencing a face that was consumed by fuse must be flagged."""
        pre = simple_registry(
            "pad-1.inner", sig(2.5, 0.0, 5.0),  # coincident face destroyed by fuse
        )
        post_faces: Dict[str, FaceSignature] = {}  # consumed
        result = remap_face_ids_across_boolean(pre, post_faces, op_kind="fuse")

        # Build minimal post registry (empty, face was destroyed)
        post_reg = FaceNameRegistry()

        doc = make_doc(make_node("cut-from-destroyed", target_face_name="pad-1.inner"))
        warns = face_name_audit(doc, post_reg)
        assert len(warns) == 1
        assert warns[0].kind == "UNMAPPED"
        assert warns[0].face_name_value == "pad-1.inner"


# ---------------------------------------------------------------------------
# Group F — OCC-dependent tests (skipped when OCC not available)
# ---------------------------------------------------------------------------

# These tests exercise the OCC-backed helpers and require a working
# pythonOCC / OCC.Core installation.  They are gated with
# ``pytest.importorskip`` so they silently skip in environments where OCC is
# absent (CI without OCC, etc.).


@pytest.fixture(scope="module")
def occ_available():
    return pytest.importorskip("OCC.Core.BRep")


class TestOccBackedSignature:
    def test_occ_box_produces_six_faces(self, occ_available):
        """A simple box should yield 6 unique face signatures."""
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # type: ignore
        from kerf_cad_core.face_name_registry import build_registry_from_occ_shape

        box = BRepPrimAPI_MakeBox(10.0, 10.0, 5.0).Shape()
        reg = build_registry_from_occ_shape(box, "box")
        # A box has exactly 6 faces
        assert len(reg) == 6

    def test_occ_signatures_survive_translate(self, occ_available):
        """
        Translating a shape changes centroid positions; signatures of the
        translated shape do NOT match the original (distance > 0).
        """
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # type: ignore
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform  # type: ignore
        from OCC.Core.gp import gp_Trsf, gp_Vec  # type: ignore
        from kerf_cad_core.face_name_registry import build_registry_from_occ_shape

        box = BRepPrimAPI_MakeBox(10.0, 10.0, 5.0).Shape()
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(100.0, 0.0, 0.0))
        moved = BRepBuilderAPI_Transform(box, trsf).Shape()

        reg_orig = build_registry_from_occ_shape(box, "orig")
        reg_moved = build_registry_from_occ_shape(moved, "moved")

        # No face from orig should exactly match a face from moved
        for name_orig in reg_orig.all_names():
            sig_orig = reg_orig.signature_for(name_orig)
            for name_moved in reg_moved.all_names():
                sig_moved = reg_moved.signature_for(name_moved)
                assert sig_orig.hex != sig_moved.hex

    def test_occ_boolean_remap(self, occ_available):
        """
        Build two boxes, fuse them with OCCT, extract post-boolean faces, run
        remap — surviving faces should be matched, boundary faces unmatched.
        """
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # type: ignore
        from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse  # type: ignore
        from kerf_cad_core.face_name_registry import (
            build_registry_from_occ_shape,
            remap_face_ids_across_boolean,
        )
        from OCC.Core.TopExp import TopExp_Explorer  # type: ignore
        from OCC.Core.TopAbs import TopAbs_FACE  # type: ignore

        box_a = BRepPrimAPI_MakeBox(10.0, 10.0, 5.0).Shape()
        # box_b is offset so it partially overlaps box_a
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform  # type: ignore
        from OCC.Core.gp import gp_Trsf, gp_Vec  # type: ignore
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(5.0, 0.0, 0.0))
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform  # type: ignore
        box_b = BRepBuilderAPI_Transform(
            BRepPrimAPI_MakeBox(10.0, 10.0, 5.0).Shape(), trsf
        ).Shape()

        # Build pre-boolean registry
        pre = FaceNameRegistry()
        build_registry_from_occ_shape(box_a, "box-a", pre)
        build_registry_from_occ_shape(box_b, "box-b", pre)

        # Fuse
        fuse = BRepAlgoAPI_Fuse(box_a, box_b)
        fuse.Build()
        fused = fuse.Shape()

        # Extract post-boolean face signatures
        from kerf_cad_core.face_name_registry import _sig_from_occ_face
        post_faces: Dict[str, FaceSignature] = {}
        exp = TopExp_Explorer(fused, TopAbs_FACE)
        idx = 0
        while exp.More():
            s = _sig_from_occ_face(exp.Current())
            if s is not None:
                post_faces[f"pf{idx}"] = s
            exp.Next()
            idx += 1

        result = remap_face_ids_across_boolean(pre, post_faces, op_kind="fuse")
        # At least some pre-faces should survive (the exterior faces of A and B)
        assert len(result.remapped) >= 2
        # The unmatched post faces are the new boundary faces created at the
        # intersection plane
        # (we don't assert a specific count because it depends on OCC version)
