"""
route.py — FastAPI routes for FreeCAD import.

POST /import-freecad-project
    Full T1+T3+T4+T5 pipeline.  Accepts a .FCStd binary upload.
    Returns::

        {
          "created_files": [
            {
              "kind": "sketch" | "feature" | "assembly",
              "name": "Sketch.sketch",
              "placeholder_id": null,
              "freecad_name": "Sketch",
              "payload": { ... }     # inline Kerf file JSON
            },
            ...
          ],
          "stats": {
            "bodies": N,
            "sketches": N,
            "features_lifted": N,
            "brep_blobs_lifted": N,
            "constraints_translated": N,
            "constraints_dropped": N
          },
          "warnings": [ "...", ... ],
          "import_folder": "/freecad_import"
        }

POST /import-freecad  (legacy stub — kept for backwards compat, redirects shape)
    Returns the old ``{geometry_json, warnings, errors}`` shape from the
    legacy stub so existing callers don't break.  The new endpoint is
    ``/import-freecad-project``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File

from kerf_imports.freecad.parser import parse_fcstd
from kerf_imports.freecad.types import FCStdParseError, FCStdUnsupportedVersionError
from kerf_imports.freecad.sketch import translate_sketch
from kerf_imports.freecad.features import build_metadata_tree
from kerf_imports.freecad.assembly import build_assembly

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /import-freecad-project — full T1+T3+T4+T5 pipeline
# ---------------------------------------------------------------------------

@router.post("/import-freecad-project")
async def import_freecad_project(
    file: UploadFile = File(...),
    import_folder: Optional[str] = Query(default="/freecad_import"),
):
    """
    Parse a .FCStd file and return a structured import result.

    Does not persist anything to the database — that is the LLM tool's job
    (T7).  Returns the full structured response so the caller can insert
    files in PG.
    """
    if not file.filename.lower().endswith((".fcstd", ".fcstd")):
        raise HTTPException(
            status_code=400,
            detail="Only .FCStd files are supported by this endpoint.",
        )

    content: bytes = await file.read()
    warnings: list[str] = []

    # ── T1: Parse .FCStd ─────────────────────────────────────────────────────
    try:
        doc = parse_fcstd(content)
    except FCStdUnsupportedVersionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FCStdParseError as exc:
        raise HTTPException(status_code=400, detail=f"FCStd parse error: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error parsing .FCStd")
        raise HTTPException(status_code=500, detail=f"Unexpected parse error: {exc}")

    # ── Counters ─────────────────────────────────────────────────────────────
    constraints_translated = 0
    constraints_dropped = 0
    brep_blobs_lifted = 0

    created_files: list[dict[str, Any]] = []

    # ── T3: Translate Sketcher objects → .sketch ─────────────────────────────
    sketch_objects = doc.objects_by_type("Sketcher::SketchObject")
    sketch_name_to_label: dict[str, str] = {}

    for sketch_obj in sketch_objects:
        try:
            sketch_payload = translate_sketch(sketch_obj)
        except Exception as exc:
            warnings.append(
                f"sketch '{sketch_obj.name}': translation failed — {exc}"
            )
            continue

        warnings.extend(sketch_payload.get("warnings") or [])

        # Count constraints
        constraints_translated += len(sketch_payload.get("constraints") or [])
        raw_constraints = sketch_obj.properties.get("Constraints") or []
        dropped = len(raw_constraints) - len(sketch_payload.get("constraints") or [])
        constraints_dropped += max(0, dropped)

        sketch_label = sketch_obj.label or sketch_obj.name
        sketch_name_to_label[sketch_obj.name] = sketch_label
        filename = f"{sketch_label}.sketch"

        created_files.append({
            "kind": "sketch",
            "name": filename,
            "freecad_name": sketch_obj.name,
            "placeholder_id": None,
            "payload": sketch_payload,
        })

    # ── T4: Build PartDesign feature-tree metadata ────────────────────────────
    try:
        feature_payloads = build_metadata_tree(doc)
    except Exception as exc:
        logger.exception("T4 build_metadata_tree failed")
        raise HTTPException(status_code=500, detail=f"Feature metadata error: {exc}")

    for fp in feature_payloads:
        # Locate the import_brep node to capture asset placeholder
        import_brep_node = next(
            (n for n in fp.nodes if n.kind == "import_brep"), None
        )
        placeholder_id: str | None = None
        if import_brep_node:
            asset_id = import_brep_node.params.get("asset_id")
            if asset_id:
                placeholder_id = asset_id
                brep_blobs_lifted += 1

        feature_filename = f"{fp.body_label}.feature"
        feature_payload = {
            "nodes": [
                {"kind": n.kind, **n.params}
                for n in fp.nodes
            ],
        }

        created_files.append({
            "kind": "feature",
            "name": feature_filename,
            "freecad_name": fp.body_name,
            "placeholder_id": placeholder_id,
            "payload": feature_payload,
        })

    # ── T5: Assembly (only for multi-Body docs) ───────────────────────────────
    try:
        assembly_payload = build_assembly(doc, feature_payloads)
    except Exception as exc:
        logger.exception("T5 build_assembly failed")
        warnings.append(f"assembly generation failed: {exc}")
        assembly_payload = None

    if assembly_payload is not None:
        created_files.append({
            "kind": "assembly",
            "name": "main.assembly",
            "freecad_name": None,
            "placeholder_id": None,
            "payload": assembly_payload,
        })

    # ── Stats ─────────────────────────────────────────────────────────────────
    bodies = doc.objects_by_type("PartDesign::Body")
    features_lifted = sum(
        1 for n in (
            node
            for fp in feature_payloads
            for node in fp.nodes
            if node.kind != "import_brep"
        )
        if True
    )

    stats = {
        "bodies": len(bodies) or len(feature_payloads),
        "sketches": len(sketch_objects),
        "features_lifted": features_lifted,
        "brep_blobs_lifted": brep_blobs_lifted,
        "constraints_translated": constraints_translated,
        "constraints_dropped": constraints_dropped,
    }

    return {
        "created_files": created_files,
        "stats": stats,
        "warnings": warnings,
        "import_folder": import_folder or "/freecad_import",
    }


# ---------------------------------------------------------------------------
# POST /import-freecad — legacy stub (kept for backwards compat)
# ---------------------------------------------------------------------------

@router.post("/import-freecad")
async def import_freecad_legacy(
    file: UploadFile = File(...)
):
    """
    Legacy FreeCAD import route.  Kept for backwards compatibility.
    Returns the old ``{geometry_json, warnings, errors}`` shape.
    New callers should use ``POST /import-freecad-project``.
    """
    warnings: list[str] = []
    errors: list[str] = []

    if not file.filename.lower().endswith(".fcstd"):
        raise HTTPException(status_code=400, detail="Only .FCStd files are supported.")

    content = await file.read()

    try:
        doc = parse_fcstd(content)
        bodies = doc.objects_by_type("PartDesign::Body")
        geometry_data = {
            "type": "freecad_document",
            "program_version": doc.program_version,
            "shapes": [
                {"name": b.name, "label": b.label, "type": b.type}
                for b in bodies
            ],
        }
        import json
        geometry_json = json.dumps(geometry_data)
    except FCStdUnsupportedVersionError as exc:
        errors.append(str(exc))
        geometry_json = ""
    except Exception as exc:
        errors.append(str(exc))
        geometry_json = ""

    return {
        "geometry_json": geometry_json,
        "warnings": warnings,
        "errors": errors,
    }
