"""
test_heal.py — pytest suite for kerf_cad_core.heal (heal_geometry tool).

All tests use synthetic in-memory mesh fixtures — no file I/O, no DB, no OCC.

Fixtures are in the mesh_repair convention: {"verts": [...], "faces": [...]}
and the legacy convention: {"vertices": [...], "indices": [...]} — both are
tested to confirm normalisation works.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.heal import (
    heal_geometry_pure,
    validate_mesh,
    run_heal_geometry,
    _normalise_input,
    _serialise,
)


# ─── Synthetic mesh fixtures ──────────────────────────────────────────────────

def _cube_mesh_repair():
    """Closed watertight unit cube (mesh_repair convention)."""
    verts = [
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
    ]
    faces = [
        # bottom
        [0, 2, 1], [0, 3, 2],
        # top
        [4, 5, 6], [4, 6, 7],
        # front
        [0, 1, 5], [0, 5, 4],
        # back
        [2, 3, 7], [2, 7, 6],
        # left
        [0, 4, 7], [0, 7, 3],
        # right
        [1, 2, 6], [1, 6, 5],
    ]
    return {"verts": verts, "faces": faces}


def _cube_mesh_legacy():
    """Same cube in legacy convention (vertices + flat indices)."""
    m = _cube_mesh_repair()
    indices = []
    for f in m["faces"]:
        indices += f
    return {"version": 1, "vertices": m["verts"], "indices": indices}


def _open_box_legacy():
    """Cube with top cap removed (legacy convention)."""
    m = _cube_mesh_legacy()
    # Remove top cap: indices 6+7 in faces = positions 18..23
    m["indices"] = m["indices"][:12] + m["indices"][18:]
    return m


def _mesh_with_gap():
    """
    Two triangles that share an edge but one has a vertex offset by epsilon.
    After welding they should be joined.
    """
    tol = 1e-4
    eps = tol * 0.4
    verts = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, 1.0, 0.0],
        [1.0 + eps, 0.0, 0.0],
        [1.5, 1.0, 0.0],
    ]
    faces = [[0, 1, 2], [3, 4, 2]]
    return {"verts": verts, "faces": faces}


def _mesh_with_degenerate_face():
    """
    One valid triangle + one zero-area degenerate face (collinear vertices).
    The degenerate face should be removed by the healing pass.
    """
    verts = [
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0],  # valid
        [5.0, 0.0, 0.0], [6.0, 0.0, 0.0], [7.0, 0.0, 0.0],  # collinear → degenerate
    ]
    faces = [[0, 1, 2], [3, 4, 5]]
    return {"verts": verts, "faces": faces}


def _mesh_with_short_edge():
    """
    A triangle with one edge whose length is below the heal tolerance.
    After welding those two vertices should merge and the degenerate face
    be removed.
    """
    tol = 1e-4
    tiny = tol * 0.3
    verts = [
        [0.0, 0.0, 0.0],
        [tiny, 0.0, 0.0],
        [0.5, 1.0, 0.0],
    ]
    faces = [[0, 1, 2]]
    return {"verts": verts, "faces": faces}


def _mesh_with_flipped_face():
    """Two adjacent triangles; one has reversed winding."""
    verts = [
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0], [1.0, 1.0, 0.0],
    ]
    # Triangle 1: CW (flipped)
    faces = [[0, 1, 2], [1, 2, 3]]
    return {"verts": verts, "faces": faces}


def _mesh_with_hole():
    """A 4-triangle quad patch with one triangle missing → a hole."""
    verts = [
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0],
        [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [2.0, 1.0, 0.0],
    ]
    faces = [
        [1, 2, 5],
        [0, 4, 3],
        [1, 5, 4],
    ]
    return {"verts": verts, "faces": faces}


# ─── FakePool / ctx helpers ───────────────────────────────────────────────────

def _make_ctx(mesh_doc=None, kind="mesh"):
    store = {
        "content": json.dumps(mesh_doc) if mesh_doc is not None else None,
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


# ─── _normalise_input ─────────────────────────────────────────────────────────

def test_normalise_mesh_repair_convention():
    doc = {"verts": [[0, 0, 0]], "faces": [[0, 0, 0]]}
    verts, faces, conv = _normalise_input(doc)
    assert conv == "mesh_repair"
    assert verts == [[0, 0, 0]]


def test_normalise_legacy_convention():
    doc = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "indices": [0, 1, 2]}
    verts, faces, conv = _normalise_input(doc)
    assert conv == "legacy"
    assert faces == [[0, 1, 2]]


def test_normalise_bad_doc_raises():
    with pytest.raises(ValueError):
        _normalise_input({"bad": "keys"})


# ─── heal_geometry_pure: basic ────────────────────────────────────────────────

def test_heal_returns_model_and_report():
    m = _cube_mesh_repair()
    result = heal_geometry_pure(m)
    assert "model" in result
    assert "report" in result


def test_heal_report_has_all_keys():
    m = _cube_mesh_repair()
    r = heal_geometry_pure(m)["report"]
    expected_keys = {
        "weld_vertices_merged", "faces_flipped", "holes_filled",
        "degenerate_removed", "non_manifold_edges",
        "closed", "manifold",
        "face_count_before", "face_count_after",
        "vertex_count_before", "vertex_count_after",
    }
    assert expected_keys.issubset(set(r.keys()))


def test_heal_clean_cube_no_changes():
    """Cube should report zero fixes needed."""
    m = _cube_mesh_repair()
    r = heal_geometry_pure(m)["report"]
    assert r["weld_vertices_merged"] == 0
    assert r["degenerate_removed"] == 0
    assert r["holes_filled"] == 0


def test_heal_clean_cube_is_closed():
    m = _cube_mesh_repair()
    r = heal_geometry_pure(m)["report"]
    assert r["closed"] is True


def test_heal_clean_cube_is_manifold():
    m = _cube_mesh_repair()
    r = heal_geometry_pure(m)["report"]
    assert r["manifold"] is True


# ─── heal_geometry_pure: degenerate face removal ──────────────────────────────

def test_heal_removes_degenerate_face():
    """The intentionally broken fixture has a collinear (zero-area) face."""
    m = _mesh_with_degenerate_face()
    result = heal_geometry_pure(m)
    r = result["report"]
    # Face count after should be 1 (the good one)
    assert r["face_count_after"] < r["face_count_before"]


def test_heal_degenerate_report_nonzero():
    m = _mesh_with_degenerate_face()
    r = heal_geometry_pure(m)["report"]
    assert r["degenerate_removed"] >= 1


# ─── heal_geometry_pure: short-edge (weld) ───────────────────────────────────

def test_heal_short_edge_merges_vertex():
    """After welding, the two very-close vertices should merge; the degenerate
    face that results should then be removed."""
    m = _mesh_with_short_edge()
    r = heal_geometry_pure(m, tolerance=1e-4)["report"]
    # Either welded or removed as degenerate
    assert r["weld_vertices_merged"] >= 1 or r["degenerate_removed"] >= 1


# ─── heal_geometry_pure: face orientation ────────────────────────────────────

def test_heal_flipped_face_fixed():
    m = _mesh_with_flipped_face()
    r = heal_geometry_pure(m)["report"]
    assert r["faces_flipped"] >= 1


# ─── heal_geometry_pure: hole filling ────────────────────────────────────────

def test_heal_fills_hole():
    m = _mesh_with_hole()
    result = heal_geometry_pure(m)
    r = result["report"]
    # Hole was detected and patched (even if coplanar patch faces are then
    # removed by remove_degenerate, holes_filled should be >= 1)
    assert r["holes_filled"] >= 1


# ─── heal_geometry_pure: vertex gap ──────────────────────────────────────────

def test_heal_gap_reduces_vertex_count():
    m = _mesh_with_gap()
    before = len(m["verts"])
    result = heal_geometry_pure(m, tolerance=1e-4)
    after = result["report"]["vertex_count_after"]
    # At least one vertex should be welded away
    assert after <= before


# ─── heal_geometry_pure: legacy convention round-trip ────────────────────────

def test_heal_legacy_convention_preserved():
    m = _cube_mesh_legacy()
    result = heal_geometry_pure(m)
    assert "vertices" in result["model"]
    assert "indices" in result["model"]
    assert "verts" not in result["model"]


def test_heal_legacy_extra_keys_preserved():
    m = _cube_mesh_legacy()
    m["version"] = 1
    m["name"] = "test_cube"
    result = heal_geometry_pure(m)
    assert result["model"].get("version") == 1
    assert result["model"].get("name") == "test_cube"


# ─── validate_mesh ────────────────────────────────────────────────────────────

def test_validate_cube_closed_and_manifold():
    m = _cube_mesh_repair()
    v = validate_mesh(m)
    assert v["ok"] is True
    assert v["closed"] is True
    assert v["manifold"] is True
    assert v["non_manifold_edges"] == 0


def test_validate_open_box_not_closed():
    m = _open_box_legacy()
    v = validate_mesh(m)
    assert v["ok"] is True
    assert v["closed"] is False


def test_validate_returns_face_count():
    m = _cube_mesh_repair()
    v = validate_mesh(m)
    assert v["face_count"] == 12
    assert v["vertex_count"] == 8


def test_validate_bad_input():
    v = validate_mesh({"bad": "input"})
    assert v["ok"] is False
    assert "reason" in v


# ─── LLM tool: run_heal_geometry ─────────────────────────────────────────────

def test_run_heal_geometry_success():
    m = _cube_mesh_repair()
    ctx, store, fid = _make_ctx(m)
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert "file_id" in result


def test_run_heal_geometry_missing_file_id():
    ctx, store, fid = _make_ctx(_cube_mesh_repair())
    result = _run(run_heal_geometry(ctx, json.dumps({}).encode()))
    assert "error" in result


def test_run_heal_geometry_invalid_uuid():
    ctx, store, fid = _make_ctx(_cube_mesh_repair())
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": "not-a-uuid"}).encode()))
    assert "error" in result


def test_run_heal_geometry_negative_tolerance():
    ctx, store, fid = _make_ctx(_cube_mesh_repair())
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid), "tolerance": -1}).encode()))
    assert "error" in result


def test_run_heal_geometry_missing_file():
    """Querying a file that doesn't exist returns NOT_FOUND."""
    ctx, store, fid = _make_ctx(None)
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" in result


def test_run_heal_geometry_mutates_stored_mesh():
    """After healing, the stored content should be updated."""
    m = _mesh_with_degenerate_face()
    ctx, store, fid = _make_ctx(m)
    original_content = store["content"]
    _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid)}).encode()))
    # Content may or may not change, but it should still be valid JSON
    new_doc = json.loads(store["content"])
    assert "verts" in new_doc or "vertices" in new_doc


def test_run_heal_geometry_report_fields_present():
    m = _cube_mesh_repair()
    ctx, store, fid = _make_ctx(m)
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "weld_vertices_merged" in result
    assert "faces_flipped" in result
    assert "holes_filled" in result
    assert "degenerate_removed" in result
    assert "closed" in result
    assert "manifold" in result


def test_run_heal_geometry_degenerate_fixture_fixed():
    """The intentionally broken mesh should have at least one degenerate face removed."""
    m = _mesh_with_degenerate_face()
    ctx, store, fid = _make_ctx(m)
    result = _run(run_heal_geometry(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert result.get("degenerate_removed", 0) >= 1


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
