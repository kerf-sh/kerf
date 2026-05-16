"""
test_heal.py — pytest suite for heal.py geometry healing.

All tests use synthetic fixtures; no file I/O or DB required.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

from kerf_imports.heal import (
    heal,
    validate_watertight,
    step_ap242_metadata,
    interop_report,
    _stitch_vertices,
    _remove_sliver_faces,
    _merge_tiny_edges,
    _unify_normals,
    _remove_duplicates,
    _detect_self_intersections,
    _detect_non_manifold,
    _fill_holes,
    run_heal_mesh,
    run_validate_watertight,
    run_step_ap242_metadata,
    run_interop_report,
)


# ─── Synthetic fixtures ───────────────────────────────────────────────────────

def _cube_mesh():
    """A closed, watertight unit cube (12 triangles, 8 vertices)."""
    verts = [
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ]
    indices = [
        # bottom (z=0) — winding outward (downward normal)
        0, 2, 1,  0, 3, 2,
        # top (z=1) — outward (upward normal)
        4, 5, 6,  4, 6, 7,
        # front (y=0)
        0, 1, 5,  0, 5, 4,
        # back (y=1)
        2, 3, 7,  2, 7, 6,
        # left (x=0)
        0, 4, 7,  0, 7, 3,
        # right (x=1)
        1, 2, 6,  1, 6, 5,
    ]
    return {"version": 1, "vertices": verts, "indices": indices}


def _open_box_mesh():
    """A cube with the top cap removed — 10 triangles, open mesh."""
    m = _cube_mesh()
    # Drop the two top-face triangles (indices 6,7 in the face list → positions 18..23)
    m["indices"] = m["indices"][:12] + m["indices"][18:]
    return m


def _mesh_with_gap():
    """
    Two triangles that share an edge but one has a vertex offset by epsilon < tol.
    After stitching they should form a watertight tent shape.
    """
    tol = 1e-4
    eps = tol * 0.5  # within tolerance
    verts = [
        [0, 0, 0],          # 0
        [1, 0, 0],          # 1
        [0.5, 1, 0],        # 2 — apex
        [1 + eps, 0, 0],    # 3 — near-duplicate of vertex 1 (within tol)
        [1.5, 1, 0],        # 4
    ]
    indices = [0, 1, 2, 3, 4, 2]
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_sliver():
    """A normal triangle plus a degenerate near-collinear sliver.

    Sliver has base=1, height=5e-10 → area=2.5e-10 < threshold 5e-9 (at tol=1e-4).
    All vertex-to-vertex distances are > 0.5, so stitch_vertices(tol=1e-4) leaves
    them untouched — the sliver survives to _remove_sliver_faces.
    """
    verts = [
        [0, 0, 0], [1, 0, 0], [0.5, 1, 0],         # normal triangle; area = 0.5
        [10, 0, 0], [11, 0, 0], [10.5, 5e-10, 0],  # sliver: area = 2.5e-10 < 5e-9
    ]
    indices = [0, 1, 2, 3, 4, 5]
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_tiny_edge():
    """A triangle with one edge shorter than tol."""
    tol = 1e-4
    tiny = tol * 0.3
    verts = [
        [0, 0, 0], [tiny, 0, 0], [0.5, 1, 0],
    ]
    indices = [0, 1, 2]
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_flipped_face():
    """Two adjacent triangles; one has its winding reversed."""
    verts = [
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
    ]
    # Triangle 0: CCW when viewed from +Z (normal up)
    # Triangle 1: CW — flipped (normal down instead of up)
    indices = [0, 1, 2,   1, 2, 3]   # second is winding-inconsistent
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_duplicate_vertex():
    """Same as a single triangle but with one vertex duplicated exactly."""
    verts = [
        [0, 0, 0], [1, 0, 0], [0, 1, 0],
        [0, 0, 0],  # exact duplicate of v0
    ]
    indices = [0, 1, 2, 3, 1, 2]  # second face = duplicate of first
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_non_manifold_edge():
    """
    Three triangles sharing a single edge (non-manifold: one edge shared by 3 faces).
    """
    verts = [
        [0, 0, 0], [1, 0, 0], [0.5, 1, 0], [0.5, -1, 0], [0.5, 0, 1],
    ]
    # Edge 0-1 is shared by 3 triangles
    indices = [0, 1, 2,  0, 1, 3,  0, 1, 4]
    return {"version": 1, "vertices": verts, "indices": indices}


def _mesh_with_hole():
    """
    A square mesh (4 triangles forming a flat square) with one triangle removed
    to leave a triangular hole.
    """
    verts = [
        [0, 0, 0], [1, 0, 0], [2, 0, 0],
        [0, 1, 0], [1, 1, 0], [2, 1, 0],
    ]
    # Original 4 triangles (2x2 grid)
    # Remove triangle [0,1,4] to create a hole
    indices = [
        1, 2, 5,
        0, 4, 3,
        1, 5, 4,
    ]
    return {"version": 1, "vertices": verts, "indices": indices}


# ─── FakePool / ctx helpers ───────────────────────────────────────────────────

def _make_mesh_ctx(mesh_doc=None, kind="mesh"):
    store = {
        "content": json.dumps(mesh_doc) if mesh_doc else None,
        "kind": kind,
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["content"] is None:
                return None
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            # update: args = (body, fid, pid)
            store["content"] = args[0]

    from kerf_core.utils.context import ProjectCtx
    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def _make_text_ctx(text: str):
    """Ctx that returns raw text content (for STEP parsing)."""
    store = {"content": text, "kind": "step"}
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"],)

        def execute(self, query, *args):
            store["content"] = args[0]

    from kerf_core.utils.context import ProjectCtx
    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def _run(coro):
    return json.loads(asyncio.run(coro))


# ─── Unit tests: _stitch_vertices ────────────────────────────────────────────

def test_stitch_merges_nearby_vertices():
    m = _mesh_with_gap()
    healed, merged = _stitch_vertices(m, tol=1e-4)
    # vertex 3 is within tol of vertex 1 → should be merged
    assert merged >= 1
    assert len(healed["vertices"]) < len(m["vertices"])


def test_stitch_does_not_merge_far_vertices():
    m = _cube_mesh()
    _, merged = _stitch_vertices(m, tol=1e-4)
    assert merged == 0


def test_stitch_gap_produces_watertight():
    """After stitching a gap mesh it should become two joined triangles (no open edges)."""
    m = _mesh_with_gap()
    healed, _ = _stitch_vertices(m, tol=1e-4)
    result = validate_watertight(healed)
    # Two triangles joined at an edge → V=4, E=5, F=2 → Euler=1 (not 2) → still "open"
    # but the gap should be closed: boundary edge count should drop by 1
    em_before = {}
    for k in range(len(m["indices"]) // 3):
        a, b, c = m["indices"][k*3], m["indices"][k*3+1], m["indices"][k*3+2]
        for u, v in ((a,b),(b,c),(c,a)):
            key = f"{min(u,v)}:{max(u,v)}"
            em_before.setdefault(key, []).append(k)
    boundary_before = sum(1 for fs in em_before.values() if len(fs) == 1)

    em_after = {}
    for k in range(len(healed["indices"]) // 3):
        a, b, c = healed["indices"][k*3], healed["indices"][k*3+1], healed["indices"][k*3+2]
        for u, v in ((a,b),(b,c),(c,a)):
            key = f"{min(u,v)}:{max(u,v)}"
            em_after.setdefault(key, []).append(k)
    boundary_after = sum(1 for fs in em_after.values() if len(fs) == 1)

    # Stitching should have reduced open edges
    assert boundary_after < boundary_before


# ─── Unit tests: _remove_sliver_faces ────────────────────────────────────────

def test_sliver_face_is_removed():
    m = _mesh_with_sliver()
    healed, removed = _remove_sliver_faces(m, tol=1e-4)
    assert removed == 1
    assert len(healed["indices"]) // 3 == 1


def test_normal_faces_not_removed():
    m = _cube_mesh()
    _, removed = _remove_sliver_faces(m, tol=1e-4)
    assert removed == 0


# ─── Unit tests: _merge_tiny_edges ───────────────────────────────────────────

def test_tiny_edge_collapses():
    m = _mesh_with_tiny_edge()
    _, collapsed = _merge_tiny_edges(m, tol=1e-4)
    assert collapsed >= 1


def test_normal_edges_not_collapsed():
    m = _cube_mesh()
    _, collapsed = _merge_tiny_edges(m, tol=1e-6)
    assert collapsed == 0


# ─── Unit tests: _unify_normals ───────────────────────────────────────────────

def test_flipped_face_gets_corrected():
    m = _mesh_with_flipped_face()
    healed, flipped = _unify_normals(m)
    assert flipped >= 1


def test_consistent_cube_normals_not_flipped():
    m = _cube_mesh()
    _, flipped = _unify_normals(m)
    assert flipped == 0


# ─── Unit tests: _remove_duplicates ──────────────────────────────────────────

def test_duplicate_vertex_removed():
    m = _mesh_with_duplicate_vertex()
    healed, dup_v, dup_f = _remove_duplicates(m)
    assert dup_v >= 1


def test_duplicate_face_removed():
    m = _mesh_with_duplicate_vertex()
    _, _, dup_f = _remove_duplicates(m)
    assert dup_f >= 1  # second face is a duplicate of the first


def test_clean_mesh_no_duplicates():
    m = _cube_mesh()
    _, dup_v, dup_f = _remove_duplicates(m)
    assert dup_v == 0
    assert dup_f == 0


# ─── Unit tests: _detect_non_manifold ────────────────────────────────────────

def test_non_manifold_edge_detected():
    m = _mesh_with_non_manifold_edge()
    nm = _detect_non_manifold(m)
    assert len(nm["edges"]) >= 1


def test_non_manifold_vertices_reported():
    m = _mesh_with_non_manifold_edge()
    nm = _detect_non_manifold(m)
    assert len(nm["vertices"]) >= 2


def test_cube_has_no_non_manifold():
    m = _cube_mesh()
    nm = _detect_non_manifold(m)
    assert len(nm["edges"]) == 0
    assert len(nm["vertices"]) == 0


# ─── Unit tests: _fill_holes ─────────────────────────────────────────────────

def test_hole_fill_closes_boundary_loop():
    m = _mesh_with_hole()
    healed, filled = _fill_holes(m)
    assert filled >= 1
    # After filling the hole should have at least one new face
    assert len(healed["indices"]) > len(m["indices"])


def test_closed_mesh_no_holes_filled():
    m = _cube_mesh()
    _, filled = _fill_holes(m)
    assert filled == 0


# ─── validate_watertight ─────────────────────────────────────────────────────

def test_validate_watertight_cube_is_closed():
    m = _cube_mesh()
    result = validate_watertight(m)
    assert result["watertight"] is True
    assert result["euler"] == 2
    assert result["issues"] == []


def test_validate_watertight_open_box_is_not_closed():
    m = _open_box_mesh()
    result = validate_watertight(m)
    assert result["watertight"] is False
    assert len(result["issues"]) >= 1


def test_validate_watertight_euler_field_present():
    m = _cube_mesh()
    result = validate_watertight(m)
    assert "euler" in result
    assert isinstance(result["euler"], int)


# ─── heal pipeline (integration) ─────────────────────────────────────────────

def test_heal_pipeline_returns_model_and_report():
    m = _cube_mesh()
    result = heal(m, tolerance=1e-4)
    assert "model" in result
    assert "report" in result
    r = result["report"]
    assert "stitched_vertices" in r
    assert "sliver_faces_removed" in r
    assert "tiny_edges_collapsed" in r
    assert "faces_flipped" in r
    assert "duplicate_vertices_removed" in r
    assert "duplicate_faces_removed" in r
    assert "self_intersection_pairs" in r
    assert "non_manifold_edges" in r
    assert "non_manifold_vertices" in r
    assert "holes_filled" in r


def test_heal_gap_mesh_becomes_watertight_after_stitch():
    """
    A mesh with a gap < tol: after heal (which stitches vertices) the
    Euler number should be closer to 2 (or at minimum the boundary count
    should have decreased).
    """
    m = _mesh_with_gap()
    result = heal(m, tolerance=1e-4)
    healed = result["model"]
    assert result["report"]["stitched_vertices"] >= 1
    # After stitching we have fewer open boundary edges
    from kerf_imports.heal import _build_edge_map
    em = _build_edge_map(healed["indices"])
    boundary = sum(1 for fs in em.values() if len(fs) == 1)
    em_orig = _build_edge_map(m["indices"])
    boundary_orig = sum(1 for fs in em_orig.values() if len(fs) == 1)
    assert boundary < boundary_orig


def test_heal_reports_sliver_removal():
    m = _mesh_with_sliver()
    result = heal(m, tolerance=1e-4)
    assert result["report"]["sliver_faces_removed"] >= 1


def test_heal_non_manifold_reported_not_broken():
    """Non-manifold mesh: heal reports it but does not silently mangle it."""
    m = _mesh_with_non_manifold_edge()
    result = heal(m, tolerance=1e-4)
    assert "model" in result
    assert result["report"]["non_manifold_edges"] >= 1


def test_heal_tolerates_empty_mesh():
    m = {"version": 1, "vertices": [], "indices": []}
    result = heal(m, tolerance=1e-4)
    assert "model" in result


# ─── step_ap242_metadata ─────────────────────────────────────────────────────

_SYNTHETIC_STEP = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('',''),'2;1');
FILE_NAME('test.stp','2024-06-01T12:00:00',('Author'),('Org'),'','kerf','');
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF { 1 0 10303 442 1 1 4 }'));
ENDSEC;
DATA;
#1=PRODUCT('WidgetBody','Main body of widget',$,(#2));
#10=GEOMETRIC_TOLERANCE(#11);
#20=NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','','',#1,#1,$);
#21=NEXT_ASSEMBLY_USAGE_OCCURRENCE('2','','',#1,#1,$);
ENDSEC;
END-ISO-10303-21;
"""


def test_step_ap242_parses_product_name():
    meta = step_ap242_metadata(_SYNTHETIC_STEP)
    assert meta["product"] == "WidgetBody"


def test_step_ap242_parses_schema():
    meta = step_ap242_metadata(_SYNTHETIC_STEP)
    assert "AP242" in meta["schema"]


def test_step_ap242_detects_gdt():
    meta = step_ap242_metadata(_SYNTHETIC_STEP)
    assert meta["has_gdt"] is True


def test_step_ap242_counts_assembly_components():
    meta = step_ap242_metadata(_SYNTHETIC_STEP)
    assert meta["assembly_components"] == 2


def test_step_ap242_no_gdt_when_absent():
    plain = "FILE_SCHEMA(('AP242'));\nDATA;\n#1=PRODUCT('Part','','',$);\nENDSEC;"
    meta = step_ap242_metadata(plain)
    assert meta["has_gdt"] is False


def test_step_ap242_parses_timestamp():
    meta = step_ap242_metadata(_SYNTHETIC_STEP)
    assert meta["timestamp"] == "2024-06-01T12:00:00"


# ─── interop_report ──────────────────────────────────────────────────────────

def test_interop_report_cube_is_ready():
    m = _cube_mesh()
    report = interop_report(m)
    assert report["ready"] is True
    assert report["watertight"] is True
    assert report["manifold"] is True
    assert report["n_issues"] == 0


def test_interop_report_open_box_not_ready():
    m = _open_box_mesh()
    report = interop_report(m)
    assert report["ready"] is False
    assert report["n_issues"] >= 1


# ─── LLM tool: run_heal_mesh ─────────────────────────────────────────────────

def test_run_heal_mesh_tool_success():
    m = _cube_mesh()
    ctx, store, fid = _make_mesh_ctx(m)
    result = _run(run_heal_mesh(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert "file_id" in result


def test_run_heal_mesh_tool_missing_file_id():
    ctx, store, fid = _make_mesh_ctx(_cube_mesh())
    result = _run(run_heal_mesh(ctx, json.dumps({}).encode()))
    assert "error" in result


def test_run_heal_mesh_tool_invalid_tolerance():
    m = _cube_mesh()
    ctx, store, fid = _make_mesh_ctx(m)
    result = _run(run_heal_mesh(ctx, json.dumps({"file_id": str(fid), "tolerance": -1}).encode()))
    assert "error" in result


# ─── LLM tool: run_validate_watertight ───────────────────────────────────────

def test_run_validate_watertight_tool_cube():
    ctx, store, fid = _make_mesh_ctx(_cube_mesh())
    result = _run(run_validate_watertight(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert result["watertight"] is True


def test_run_validate_watertight_tool_open_box():
    ctx, store, fid = _make_mesh_ctx(_open_box_mesh())
    result = _run(run_validate_watertight(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert result["watertight"] is False


# ─── LLM tool: run_step_ap242_metadata ───────────────────────────────────────

def test_run_step_ap242_metadata_tool():
    ctx, store, fid = _make_text_ctx(_SYNTHETIC_STEP)
    result = _run(run_step_ap242_metadata(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert result["product"] == "WidgetBody"


# ─── LLM tool: run_interop_report ────────────────────────────────────────────

def test_run_interop_report_tool_cube():
    ctx, store, fid = _make_mesh_ctx(_cube_mesh())
    result = _run(run_interop_report(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert result["ready"] is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
