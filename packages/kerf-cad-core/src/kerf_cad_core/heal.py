"""
heal.py — geometry healing LLM tool for kerf-cad-core.

Wraps the `kerf_cad_core.geom.mesh_repair.repair_pipeline` (and its constituent
helpers) into a public healing pass + LLM-callable tool `heal_geometry`.

Pipeline steps (delegated to mesh_repair):
  1. weld_vertices   — close small gaps (merge within tol)
  2. unify_normals   — BFS consistent winding / fix face orientation
  3. fill_holes      — fan-fill small boundary loops
  4. remove_degenerate — drop zero-area / short-edge faces; detect non-manifold

The `heal_geometry(file_id, tolerance)` tool reads a mesh file from the DB,
runs the pipeline, writes the healed model back, and returns a structured diff
report listing every change made.

Data model: the mesh stored in the DB uses the `mesh_repair` convention —
  {"verts": [[x,y,z],...], "faces": [[i,j,k],...]}
or the legacy `kerf_imports.heal` convention —
  {"vertices": [[x,y,z],...], "indices": [i,j,k,...]}
Both are normalised on read and written back in the input convention.

All public functions return dicts and never raise — errors surface as
{"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from kerf_cad_core.geom.mesh_repair import (
    fill_holes,
    is_closed,
    is_manifold,
    remove_degenerate,
    repair_pipeline,
    unify_normals,
    weld_vertices,
)
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

__all__ = [
    "heal_geometry_pure",
    "validate_mesh",
    "run_heal_geometry",
]


# ─── Internal: mesh normalisation ────────────────────────────────────────────

def _normalise_input(doc: dict) -> tuple[list, list, str]:
    """
    Accept either mesh convention and return (verts, faces, convention).

    Conventions:
      "mesh_repair" — {"verts": [...], "faces": [...]}
      "legacy"      — {"vertices": [...], "indices": [...]}  (flat index list)
    """
    if "verts" in doc and "faces" in doc:
        return list(doc["verts"]), [list(f) for f in doc["faces"]], "mesh_repair"

    if "vertices" in doc and "indices" in doc:
        verts = list(doc["vertices"])
        flat = doc["indices"]
        faces = [[flat[i * 3], flat[i * 3 + 1], flat[i * 3 + 2]]
                 for i in range(len(flat) // 3)]
        return verts, faces, "legacy"

    raise ValueError("doc must have 'verts'+'faces' or 'vertices'+'indices'")


def _serialise(verts: list, faces: list, convention: str, extra: dict) -> dict:
    """Re-serialise healed mesh in the same convention as the input."""
    if convention == "legacy":
        indices = []
        for f in faces:
            indices += [int(f[0]), int(f[1]), int(f[2])]
        return {**extra, "vertices": verts, "indices": indices}
    return {**extra, "verts": verts, "faces": faces}


def _extra_keys(doc: dict, convention: str) -> dict:
    skip = (
        {"verts", "faces"} if convention == "mesh_repair"
        else {"vertices", "indices"}
    )
    return {k: v for k, v in doc.items() if k not in skip}


# ─── Public pure-Python heal function ────────────────────────────────────────

def heal_geometry_pure(doc: dict, tolerance: float = 1e-4) -> dict:
    """
    Run the geometry healing pipeline on an in-memory mesh document.

    Parameters
    ----------
    doc : dict
        Mesh in either mesh_repair or legacy convention.
    tolerance : float
        Merge/stitch tolerance (default 1e-4 model units).

    Returns
    -------
    {
        "model":  dict   # healed mesh in same convention as input
        "report": {
            "weld_vertices_merged":     int,
            "faces_flipped":            int,
            "holes_filled":             int,
            "degenerate_removed":       int,
            "non_manifold_edges":       int,
            "closed":                   bool,
            "manifold":                 bool,
            "face_count_before":        int,
            "face_count_after":         int,
            "vertex_count_before":      int,
            "vertex_count_after":       int,
        }
    }
    """
    try:
        verts, faces, conv = _normalise_input(doc)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}

    face_count_before = len(faces)
    vertex_count_before = len(verts)
    extra = _extra_keys(doc, conv)

    # Step 1: weld vertices
    r_weld = weld_vertices(verts, faces, tol=tolerance)
    if not r_weld.get("ok", True):
        return {"ok": False, "reason": r_weld.get("reason", "weld_vertices failed")}
    verts = r_weld["verts"]
    faces = r_weld["faces"]
    weld_merged = r_weld.get("merged_count", 0)

    # Step 2: unify normals
    r_normals = unify_normals(verts, faces)
    if not r_normals.get("ok", True):
        return {"ok": False, "reason": r_normals.get("reason", "unify_normals failed")}
    verts = r_normals["verts"]
    faces = r_normals["faces"]
    faces_flipped = r_normals.get("flipped_count", 0)

    # Step 3: fill holes
    r_holes = fill_holes(verts, faces)
    if not r_holes.get("ok", True):
        return {"ok": False, "reason": r_holes.get("reason", "fill_holes failed")}
    verts = r_holes["verts"]
    faces = r_holes["faces"]
    holes_filled = r_holes.get("holes_filled", 0)

    # Step 4: remove degenerate faces
    r_degen = remove_degenerate(verts, faces)
    if not r_degen.get("ok", True):
        return {"ok": False, "reason": r_degen.get("reason", "remove_degenerate failed")}
    verts = r_degen["verts"]
    faces = r_degen["faces"]
    degen_removed = r_degen.get("removed_count", 0)
    _nm_raw = r_degen.get("non_manifold_edges", 0)
    # non_manifold_edges may be a list of edge pairs or an int count
    nm_edges = len(_nm_raw) if isinstance(_nm_raw, (list, tuple)) else int(_nm_raw)

    # Step 5: check closed / manifold
    r_closed = is_closed(verts, faces)
    closed = r_closed.get("closed", False) if r_closed.get("ok", True) else False

    r_manifold = is_manifold(verts, faces)
    manifold = r_manifold.get("manifold", False) if r_manifold.get("ok", True) else False

    healed_doc = _serialise(verts, faces, conv, extra)

    return {
        "model": healed_doc,
        "report": {
            "weld_vertices_merged": weld_merged,
            "faces_flipped": faces_flipped,
            "holes_filled": holes_filled,
            "degenerate_removed": degen_removed,
            "non_manifold_edges": nm_edges,
            "closed": closed,
            "manifold": manifold,
            "face_count_before": face_count_before,
            "face_count_after": len(faces),
            "vertex_count_before": vertex_count_before,
            "vertex_count_after": len(verts),
        },
    }


# ─── Validation helper ────────────────────────────────────────────────────────

def validate_mesh(doc: dict) -> dict:
    """
    Check whether a mesh document is closed and manifold.

    Returns:
      {"ok": True, "closed": bool, "manifold": bool,
       "non_manifold_edges": int, "non_manifold_vertices": int,
       "face_count": int, "vertex_count": int}
    """
    try:
        verts, faces, _conv = _normalise_input(doc)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}

    r_closed = is_closed(verts, faces)
    r_manifold = is_manifold(verts, faces)

    closed = r_closed.get("closed", False) if r_closed.get("ok", True) else False
    manifold = r_manifold.get("manifold", False) if r_manifold.get("ok", True) else False

    def _to_count(v: object) -> int:
        return len(v) if isinstance(v, (list, tuple)) else int(v or 0)

    nm_edges_raw = r_manifold.get("non_manifold_edges", 0) if r_manifold.get("ok", True) else 0
    nm_verts_raw = r_manifold.get("non_manifold_vertices", 0) if r_manifold.get("ok", True) else 0
    nm_edges = _to_count(nm_edges_raw)
    nm_verts = _to_count(nm_verts_raw)

    return {
        "ok": True,
        "closed": closed,
        "manifold": manifold,
        "non_manifold_edges": nm_edges,
        "non_manifold_vertices": nm_verts,
        "face_count": len(faces),
        "vertex_count": len(verts),
    }


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _read_mesh_doc(ctx: ProjectCtx, file_id: uuid.UUID) -> tuple[Optional[dict], Optional[str]]:
    row = ctx.pool.fetchone(
        "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
        file_id, ctx.project_id,
    )
    if not row:
        return None, "file not found"
    content, kind = row
    if kind not in ("mesh", "step", "text"):
        return None, f"file is kind={kind!r}, expected mesh/step/text"
    try:
        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")
        return json.loads(content), None
    except Exception as e:
        return None, f"JSON parse error: {e}"


def _write_mesh_doc(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict) -> Optional[str]:
    body = json.dumps(doc)
    try:
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


def _parse_file_id(a: dict) -> tuple[Optional[uuid.UUID], Optional[str]]:
    raw = a.get("file_id", "").strip()
    if not raw:
        return None, "file_id is required"
    try:
        return uuid.UUID(raw), None
    except Exception:
        return None, "file_id must be a valid UUID"


# ─── LLM tool spec ────────────────────────────────────────────────────────────

heal_geometry_spec = ToolSpec(
    name="heal_geometry",
    description=(
        "Run a full geometry healing pass on a mesh file: "
        "close small vertex gaps (weld), fix face orientation (unify normals), "
        "fill small boundary holes, and remove degenerate/zero-area faces. "
        "Returns a per-step diff report listing what was fixed. "
        "The healed model is written back to the same file_id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the mesh file to heal.",
            },
            "tolerance": {
                "type": "number",
                "description": (
                    "Merge/weld tolerance in model units. "
                    "Vertices within this distance are merged. Default: 1e-4."
                ),
            },
        },
        "required": ["file_id"],
    },
)


# ─── LLM tool handler ─────────────────────────────────────────────────────────

@register(heal_geometry_spec, write=True)
async def run_heal_geometry(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")

    tol = float(a.get("tolerance", 1e-4))
    if tol <= 0:
        return err_payload("tolerance must be positive", "BAD_ARGS")

    doc, err = _read_mesh_doc(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")

    result = heal_geometry_pure(doc, tol)
    if not result.get("model"):
        return err_payload(result.get("reason", "heal failed"), "ERROR")

    write_err = _write_mesh_doc(ctx, fid, result["model"])
    if write_err:
        return err_payload(write_err, "WRITE_ERR")

    return ok_payload({"file_id": str(fid), **result["report"]})
