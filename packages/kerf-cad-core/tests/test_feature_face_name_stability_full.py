"""
test_feature_face_name_stability_full.py — T-47: Persistent face naming (Phase 4).

Tests ``kerf_cad_core.face_name_registry`` across 25 rebuild scenarios spanning:

  Group A  — Boolean rebuild stability            (6 tests)
  Group B  — Pattern (linear / circular) rebuild  (5 tests)
  Group C  — Mates / assembly rebuild             (5 tests)
  Group D  — Sweep / loft rebuild                 (5 tests)
  Group E  — Collision + rename determinism       (4 tests)

Success criteria
----------------
- Names survive rebuild (same geometry → same persistent name).
- Rename-on-collision is deterministic (lexicographic tie-break).
- All 25 tests pass with zero OCC or DB dependencies.
"""

from __future__ import annotations

import math
from typing import Dict, List

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
# Shared helpers
# ---------------------------------------------------------------------------

def sig(
    cx: float = 0.0,
    cy: float = 0.0,
    cz: float = 0.0,
    nx: float = 0.0,
    ny: float = 0.0,
    nz: float = 1.0,
    area: float = 1.0,
) -> FaceSignature:
    return FaceSignature(centroid=(cx, cy, cz), normal=(nx, ny, nz), area=area)


def reg_from(*pairs) -> FaceNameRegistry:
    """Build a FaceNameRegistry from (name, sig) pairs."""
    r = FaceNameRegistry()
    it = iter(pairs)
    for name in it:
        r.assign(name, next(it))
    return r


def doc_with(*nodes: dict) -> dict:
    return {"features": list(nodes)}


def node(nid: str, **kw) -> dict:
    return {"id": nid, "op": "op", **kw}


# ─────────────────────────────────────────────────────────────────────────────
# Group A — Boolean rebuild stability
# ─────────────────────────────────────────────────────────────────────────────


class TestBooleanRebuildStability:
    """Face names stay stable when a boolean op is rebuilt with identical geometry."""

    # A1 ─────────────────────────────────────────────────────────────────────

    def test_fuse_all_faces_remapped_on_rebuild(self):
        """Rebuild fuse: every pre-boolean name is re-assigned on the second eval."""
        pre = reg_from(
            "pad.top",    sig(0.0, 0.0, 5.0, 0.0, 0.0,  1.0, 16.0),
            "pad.bot",    sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 16.0),
            "tool.top",   sig(0.0, 8.0, 5.0, 0.0, 0.0,  1.0, 16.0),
            "tool.bot",   sig(0.0, 8.0, 0.0, 0.0, 0.0, -1.0, 16.0),
        )
        # Rebuild produces identical post-face geometry
        post: Dict[str, FaceSignature] = {
            "f0": sig(0.0, 0.0, 5.0, 0.0, 0.0,  1.0, 16.0),
            "f1": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 16.0),
            "f2": sig(0.0, 8.0, 5.0, 0.0, 0.0,  1.0, 16.0),
            "f3": sig(0.0, 8.0, 0.0, 0.0, 0.0, -1.0, 16.0),
        }
        r1 = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        # Re-run (rebuild simulation) must produce identical mapping
        r2 = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert r1.remapped == r2.remapped
        assert r1.unmatched_pre == r2.unmatched_pre == []
        assert r1.unmatched_post == r2.unmatched_post == []

    # A2 ─────────────────────────────────────────────────────────────────────

    def test_cut_rebuild_preserves_target_names(self):
        """Rebuild cut: cut-body faces survive with original names."""
        pre = reg_from(
            "box.top",  sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 100.0),
            "box.bot",  sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 100.0),
            "box.left", sig(-5.0, 0.0, 5.0, -1.0, 0.0, 0.0, 50.0),
        )
        post = {
            "p0": sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 100.0),
            "p1": sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 100.0),
            "p2": sig(-5.0, 0.0, 5.0, -1.0, 0.0, 0.0, 50.0),
            # new boundary face
            "p3": sig(3.0, 0.0, 5.0, 1.0, 0.0, 0.0, 5.0),
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="cut", max_distance=20.0)
        assert r.remapped["p0"] == "box.top"
        assert r.remapped["p1"] == "box.bot"
        assert r.remapped["p2"] == "box.left"
        assert "p3" in r.unmatched_post

    # A3 ─────────────────────────────────────────────────────────────────────

    def test_common_rebuild_only_intersection_faces_survive(self):
        """Rebuild common: only faces within the intersection get re-assigned."""
        pre = reg_from(
            "a.top",   sig(0.0, 0.0, 3.0, 0.0, 0.0,  1.0, 4.0),
            "a.bot",   sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
            "b.side",  sig(5.0, 0.0, 2.0, 1.0, 0.0,  0.0, 3.0),
        )
        # common destroys b.side; a.top and a.bot survive inside intersection
        post = {
            "q0": sig(0.0, 0.0, 3.0, 0.0, 0.0,  1.0, 4.0),
            "q1": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="common")
        assert r.remapped["q0"] == "a.top"
        assert r.remapped["q1"] == "a.bot"
        assert "b.side" in r.unmatched_pre

    # A4 ─────────────────────────────────────────────────────────────────────

    def test_history_map_override_stable_across_rebuilds(self):
        """History map entries always take priority; consistent across two rebuilds."""
        pre = reg_from(
            "face.A", sig(0.0, 0.0, 1.0),
            "face.B", sig(0.0, 0.0, 2.0),
        )
        post = {
            "new-0": sig(0.0, 0.0, 2.0),  # signature matches face.B
            "new-1": sig(0.0, 0.0, 1.0),  # signature matches face.A
        }
        # History says new-0 → face.A (override signature match)
        history = {"new-0": "face.A"}
        r1 = remap_face_ids_across_boolean(pre, post, history_map=history)
        r2 = remap_face_ids_across_boolean(pre, post, history_map=history)
        assert r1.remapped == r2.remapped
        assert r1.remapped["new-0"] == "face.A"

    # A5 ─────────────────────────────────────────────────────────────────────

    def test_boundary_names_stable_across_rebuilds(self):
        """New boundary faces always get the same deterministic name on rebuild."""
        unmatched = ["pf7", "pf2", "pf5"]
        names_run1 = assign_new_boundary_names("bool-1", "fuse", unmatched)
        names_run2 = assign_new_boundary_names("bool-1", "fuse", unmatched)
        assert names_run1 == names_run2
        # Sorted: pf2=0, pf5=1, pf7=2
        assert names_run1["pf2"] == "bool-1.boundary.fuse.0"
        assert names_run1["pf5"] == "bool-1.boundary.fuse.1"
        assert names_run1["pf7"] == "bool-1.boundary.fuse.2"

    # A6 ─────────────────────────────────────────────────────────────────────

    def test_chained_booleans_names_survive(self):
        """Faces persist through two successive boolean ops without name loss."""
        # Step 1: first fuse
        pre1 = reg_from(
            "a.top", sig(0.0, 0.0, 5.0, 0.0, 0.0,  1.0, 4.0),
            "a.bot", sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
        )
        post1 = {
            "pf0": sig(0.0, 0.0, 5.0, 0.0, 0.0,  1.0, 4.0),
            "pf1": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),
            "pf2": sig(2.0, 0.0, 2.5, 1.0, 0.0,  0.0, 2.0),  # boundary
        }
        r1 = remap_face_ids_across_boolean(pre1, post1, op_kind="fuse")
        b1_names = assign_new_boundary_names("bool-1", "fuse", r1.unmatched_post)

        # Build intermediate registry
        mid_reg = FaceNameRegistry()
        for pid, pname in r1.remapped.items():
            mid_reg.assign(pname, post1[pid])
        for pid, bname in b1_names.items():
            mid_reg.assign(bname, post1[pid])

        # Step 2: second cut
        post2 = {
            "qf0": sig(0.0, 0.0, 5.0, 0.0, 0.0,  1.0, 4.0),  # a.top survives
            "qf1": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 4.0),  # a.bot survives
            "qf3": sig(9.0, 0.0, 2.5, 1.0, 0.0,  0.0, 2.0),  # new boundary
        }
        r2 = remap_face_ids_across_boolean(mid_reg, post2, op_kind="cut",
                                            max_distance=20.0)
        assert r2.remapped.get("qf0") == "a.top"
        assert r2.remapped.get("qf1") == "a.bot"


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Pattern rebuild stability
# ─────────────────────────────────────────────────────────────────────────────


class TestPatternRebuildStability:
    """Face names remain stable when pattern instances are rebuilt."""

    # B1 ─────────────────────────────────────────────────────────────────────

    def test_linear_pattern_instance_faces_stable(self):
        """Linear pattern: each instance's top face keeps its registry name."""
        # Simulate 3 instances of a pad pattern at x=0, x=10, x=20
        pre = FaceNameRegistry()
        for i in range(3):
            pre.assign(f"pad-pattern.inst{i}.top", sig(float(i * 10), 0.0, 5.0, 0.0, 0.0,  1.0, 4.0))
            pre.assign(f"pad-pattern.inst{i}.bot", sig(float(i * 10), 0.0, 0.0, 0.0, 0.0, -1.0, 4.0))

        # Rebuild: identical geometry, new opaque ids
        post: Dict[str, FaceSignature] = {}
        for i in range(3):
            post[f"rf{i*2}"]   = sig(float(i * 10), 0.0, 5.0, 0.0, 0.0,  1.0, 4.0)
            post[f"rf{i*2+1}"] = sig(float(i * 10), 0.0, 0.0, 0.0, 0.0, -1.0, 4.0)

        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert len(r.remapped) == 6
        assert r.unmatched_pre == []
        assert r.unmatched_post == []

    # B2 ─────────────────────────────────────────────────────────────────────

    def test_linear_pattern_adding_instance_keeps_old_names(self):
        """Adding a new instance doesn't disturb existing instance names."""
        pre = reg_from(
            "pat.inst0.top", sig(0.0, 0.0, 5.0),
            "pat.inst1.top", sig(10.0, 0.0, 5.0),
        )
        # Rebuild with 3 instances (new instance at x=20)
        post = {
            "r0": sig(0.0, 0.0, 5.0),
            "r1": sig(10.0, 0.0, 5.0),
            "r2": sig(20.0, 0.0, 5.0),  # new
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert r.remapped["r0"] == "pat.inst0.top"
        assert r.remapped["r1"] == "pat.inst1.top"
        assert "r2" in r.unmatched_post

    # B3 ─────────────────────────────────────────────────────────────────────

    def test_circular_pattern_faces_stable(self):
        """Circular pattern: 4 instances around a circle, names survive rebuild."""
        pre = FaceNameRegistry()
        for i in range(4):
            angle = i * math.pi / 2.0
            cx = round(10.0 * math.cos(angle), 4)
            cy = round(10.0 * math.sin(angle), 4)
            pre.assign(f"circ-pat.inst{i}.face", sig(cx, cy, 2.0))

        post: Dict[str, FaceSignature] = {}
        for i in range(4):
            angle = i * math.pi / 2.0
            cx = round(10.0 * math.cos(angle), 4)
            cy = round(10.0 * math.sin(angle), 4)
            post[f"cf{i}"] = sig(cx, cy, 2.0)

        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert len(r.remapped) == 4
        assert r.unmatched_pre == []
        assert r.unmatched_post == []

    # B4 ─────────────────────────────────────────────────────────────────────

    def test_pattern_removing_instance_marks_unmatched(self):
        """Reducing instance count marks removed instances as unmatched_pre."""
        pre = reg_from(
            "pat.inst0.top", sig(0.0, 0.0, 5.0),
            "pat.inst1.top", sig(10.0, 0.0, 5.0),
            "pat.inst2.top", sig(20.0, 0.0, 5.0),  # will be removed
        )
        # Rebuild with only 2 instances
        post = {
            "r0": sig(0.0, 0.0, 5.0),
            "r1": sig(10.0, 0.0, 5.0),
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="cut")
        assert "pat.inst2.top" in r.unmatched_pre
        assert len(r.remapped) == 2

    # B5 ─────────────────────────────────────────────────────────────────────

    def test_pattern_rebuild_idempotent(self):
        """Pattern remap is idempotent: three successive rebuilds give same result."""
        pre = reg_from(
            "pat.f0", sig(0.0, 0.0, 1.0),
            "pat.f1", sig(5.0, 0.0, 1.0),
        )
        post = {"p0": sig(0.0, 0.0, 1.0), "p1": sig(5.0, 0.0, 1.0)}
        results = [remap_face_ids_across_boolean(pre, post) for _ in range(3)]
        assert results[0].remapped == results[1].remapped == results[2].remapped


# ─────────────────────────────────────────────────────────────────────────────
# Group C — Mates / assembly rebuild
# ─────────────────────────────────────────────────────────────────────────────


class TestMatesAssemblyRebuild:
    """Mate reference faces remain stable when the assembly is rebuilt."""

    # C1 ─────────────────────────────────────────────────────────────────────

    def test_planar_mate_face_stable(self):
        """A planar mate's reference face survives a rebuild without rename."""
        reg = reg_from("part-A.mate-face", sig(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 25.0))
        # Rebuild: same signature, new id
        post = {"nf0": sig(0.0, 0.0, 10.0, 0.0, 0.0, 1.0, 25.0)}
        r = remap_face_ids_across_boolean(reg, post, op_kind="fuse")
        assert r.remapped["nf0"] == "part-A.mate-face"

    # C2 ─────────────────────────────────────────────────────────────────────

    def test_cylindrical_mate_face_stable(self):
        """Cylindrical mate face (axis-aligned normal) stays stable after rebuild."""
        reg = reg_from("shaft.cyl-face", sig(5.0, 0.0, 5.0, 1.0, 0.0, 0.0, round(math.pi * 10.0, 6)))
        post = {"cf0": sig(5.0, 0.0, 5.0, 1.0, 0.0, 0.0, round(math.pi * 10.0, 6))}
        r = remap_face_ids_across_boolean(reg, post, op_kind="fuse")
        assert r.remapped["cf0"] == "shaft.cyl-face"

    # C3 ─────────────────────────────────────────────────────────────────────

    def test_mate_face_audit_no_warnings_after_rebuild(self):
        """After rebuild, audit of a document referencing the mate face is clean."""
        reg = reg_from("housing.flange", sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 50.0))
        post = {"bf0": sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 50.0)}
        r = remap_face_ids_across_boolean(reg, post)

        post_reg = FaceNameRegistry()
        for pid, pname in r.remapped.items():
            post_reg.assign(pname, post[pid])

        d = doc_with(node("mate-1", target_face_name="housing.flange"))
        warns = face_name_audit(d, post_reg)
        assert warns == []

    # C4 ─────────────────────────────────────────────────────────────────────

    def test_mate_face_audit_flags_stale_after_geometry_change(self):
        """When the mated face geometry changes beyond threshold, audit warns DRIFTED."""
        original_sig = sig(0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 50.0)
        reg = reg_from("housing.flange", original_sig)

        # Geometry shifted by more than drift threshold
        shifted = sig(0.0, 0.0, _DRIFT_CENTROID_THRESHOLD + 0.05, 0.0, 0.0, -1.0, 50.0)
        d = doc_with(node("mate-1", target_face_name="housing.flange"))
        warns = face_name_audit(d, reg, current_sigs={"housing.flange": shifted})
        assert len(warns) == 1
        assert warns[0].kind == "DRIFTED"
        assert warns[0].node_id == "mate-1"

    # C5 ─────────────────────────────────────────────────────────────────────

    def test_multiple_mates_all_stable(self):
        """An assembly with 4 mate references; all survive a clean rebuild."""
        face_sigs = {
            "a.top":   sig(0.0, 0.0, 10.0, 0.0, 0.0,  1.0, 25.0),
            "a.bot":   sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 25.0),
            "b.left":  sig(-5.0, 0.0, 5.0, -1.0, 0.0, 0.0, 20.0),
            "b.right": sig( 5.0, 0.0, 5.0,  1.0, 0.0, 0.0, 20.0),
        }
        pre = FaceNameRegistry()
        for name, s in face_sigs.items():
            pre.assign(name, s)

        post = {f"pf{i}": s for i, (_, s) in enumerate(face_sigs.items())}
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert len(r.remapped) == 4
        assert r.unmatched_pre == []


# ─────────────────────────────────────────────────────────────────────────────
# Group D — Sweep / loft rebuild
# ─────────────────────────────────────────────────────────────────────────────


class TestSweepLoftRebuild:
    """Face names on swept/lofted bodies remain stable across rebuilds."""

    # D1 ─────────────────────────────────────────────────────────────────────

    def test_sweep_cap_faces_stable(self):
        """Sweep start/end cap faces persist with original names on rebuild."""
        pre = reg_from(
            "sweep-1.start-cap", sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 9.0),
            "sweep-1.end-cap",   sig(0.0, 0.0, 30.0, 0.0, 0.0,  1.0, 9.0),
        )
        post = {
            "sf0": sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 9.0),
            "sf1": sig(0.0, 0.0, 30.0, 0.0, 0.0,  1.0, 9.0),
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert r.remapped["sf0"] == "sweep-1.start-cap"
        assert r.remapped["sf1"] == "sweep-1.end-cap"

    # D2 ─────────────────────────────────────────────────────────────────────

    def test_sweep_rail_face_stable(self):
        """Rail (side) face of a swept body keeps its name across rebuilds."""
        pre = reg_from("sweep-1.rail", sig(3.0, 0.0, 15.0, 1.0, 0.0, 0.0, 60.0))
        post = {"rf0": sig(3.0, 0.0, 15.0, 1.0, 0.0, 0.0, 60.0)}
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert r.remapped["rf0"] == "sweep-1.rail"

    # D3 ─────────────────────────────────────────────────────────────────────

    def test_loft_section_faces_stable(self):
        """Loft between two profiles: both section faces keep their names."""
        pre = reg_from(
            "loft-1.section0", sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
            "loft-1.section1", sig(0.0, 0.0, 20.0, 0.0, 0.0,  1.0,  4.0),  # smaller top
        )
        post = {
            "lf0": sig(0.0, 0.0,  0.0, 0.0, 0.0, -1.0, 16.0),
            "lf1": sig(0.0, 0.0, 20.0, 0.0, 0.0,  1.0,  4.0),
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")
        assert r.remapped["lf0"] == "loft-1.section0"
        assert r.remapped["lf1"] == "loft-1.section1"

    # D4 ─────────────────────────────────────────────────────────────────────

    def test_sweep_profile_change_marks_end_cap_drifted(self):
        """When sweep end-cap moves (profile change), audit detects drift."""
        original = sig(0.0, 0.0, 30.0, 0.0, 0.0, 1.0, 9.0)
        reg = reg_from("sweep-1.end-cap", original)
        # Profile made longer; end cap moved
        new_end = sig(0.0, 0.0, 40.0, 0.0, 0.0, 1.0, 9.0)
        d = doc_with(node("chamfer-1", target_face_name="sweep-1.end-cap"))
        warns = face_name_audit(d, reg, current_sigs={"sweep-1.end-cap": new_end})
        assert any(w.kind == "DRIFTED" for w in warns)

    # D5 ─────────────────────────────────────────────────────────────────────

    def test_loft_rebuild_three_sections_all_matched(self):
        """Loft with 3 section faces: all three survive a clean rebuild."""
        pre = FaceNameRegistry()
        zs = [0.0, 10.0, 25.0]
        areas = [25.0, 16.0, 9.0]
        for i, (z, a) in enumerate(zip(zs, areas)):
            normal_z = -1.0 if i == 0 else 1.0
            pre.assign(f"loft-2.section{i}", sig(0.0, 0.0, z, 0.0, 0.0, normal_z, a))

        post = {
            f"lf{i}": pre.signature_for(f"loft-2.section{i}")
            for i in range(3)
        }
        r = remap_face_ids_across_boolean(pre, post, op_kind="fuse")  # type: ignore[arg-type]
        assert len(r.remapped) == 3
        assert r.unmatched_pre == []
        assert r.unmatched_post == []


# ─────────────────────────────────────────────────────────────────────────────
# Group E — Collision + rename determinism
# ─────────────────────────────────────────────────────────────────────────────


class TestCollisionAndRenameDeterminism:
    """Collision resolution and deterministic tie-breaking."""

    # E1 ─────────────────────────────────────────────────────────────────────

    def test_identical_sig_collision_lexicographic_winner(self):
        """Two faces with the same signature; lexicographically smaller name wins."""
        s = sig(0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 9.0)
        pre = reg_from("zzz.face", s, "aaa.face", s)
        post = {"pf0": s}
        r = remap_face_ids_across_boolean(pre, post)
        assert r.remapped["pf0"] == "aaa.face"

    # E2 ─────────────────────────────────────────────────────────────────────

    def test_disambiguation_suffix_deterministic(self):
        """Registry assigns stable sorted order in hex bucket for colliding entries."""
        s = sig(1.0, 1.0, 1.0)
        reg = FaceNameRegistry()
        reg.assign("face-Z", s)
        reg.assign("face-A", s)  # same sig hex as face-Z
        names = reg.names_for_hex(s.hex)
        # Bucket is kept sorted, so face-A < face-Z
        assert names == ["face-A", "face-Z"]

    # E3 ─────────────────────────────────────────────────────────────────────

    def test_snapshot_preserves_collision_bucket(self):
        """Round-trip through snapshot/from_snapshot preserves both colliding names."""
        s = sig(2.0, 3.0, 4.0, 0.0, 1.0, 0.0, 7.0)
        reg = FaceNameRegistry()
        reg.assign("beta", s)
        reg.assign("alpha", s)

        snap = reg.snapshot()
        reg2 = FaceNameRegistry.from_snapshot(snap)
        # Both names survive the round-trip
        assert reg2.has("alpha")
        assert reg2.has("beta")
        # Both share a single hex bucket post-restore
        recovered_sig = reg2.signature_for("alpha")
        assert recovered_sig is not None
        names2 = reg2.names_for_hex(recovered_sig.hex)
        assert "alpha" in names2
        assert "beta" in names2

    # E4 ─────────────────────────────────────────────────────────────────────

    def test_remap_two_equal_score_post_faces_assigned_deterministically(self):
        """When two post-faces tie for the same pre-name, tie is broken by post-id."""
        s_pre  = sig(0.0, 0.0, 5.0)
        s_same = sig(0.0, 0.0, 5.0)  # exact match (score=0) for both post candidates

        pre = reg_from("box.top", s_pre)
        # Both post-faces have score=0 against box.top; "aa-face" < "zz-face"
        post = {
            "zz-face": s_same,
            "aa-face": s_same,
        }
        r = remap_face_ids_across_boolean(pre, post)
        # Only one pre-name available; the lexicographically smaller post-id wins
        assigned_post_ids = list(r.remapped.keys())
        assert len(assigned_post_ids) == 1
        assert assigned_post_ids[0] == "aa-face"
        assert r.remapped["aa-face"] == "box.top"
        assert "zz-face" in r.unmatched_post
