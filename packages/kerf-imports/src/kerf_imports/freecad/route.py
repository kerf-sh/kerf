"""
route.py — FastAPI routes for FreeCAD import.

POST /import-freecad-project
    Full T1+T3+T4+T5 pipeline + Tier 2 (Spreadsheet, TechDraw, Materials)
    + Tier 3 (PartDesign datums, Draft Workbench objects).
    Accepts a .FCStd binary upload.  Returns::

        {
          "created_files": [
            {
              "kind": "sketch" | "feature" | "assembly" | "equations"
                      | "drawing" | "material",
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
            "constraints_dropped": N,
            "spreadsheets": N,
            "drawings": N,
            "materials": N,
            "datums": N,
            "draft_objects": N
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
from kerf_imports.freecad.spreadsheet import translate_spreadsheet
from kerf_imports.freecad.techdraw import translate_drawpage
from kerf_imports.freecad.materials import translate_material
from kerf_imports.freecad.datums import build_datum_map, sketch_attachment_from_datum
from kerf_imports.freecad.draft_workbench import translate_draft_object, ALL_DRAFT_TYPES

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /import-freecad-project — full T1+T3+T4+T5 + Tier 2 pipeline
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

    Tier 2 additions over T1: Spreadsheet::Sheet → .equations,
    TechDraw::DrawPage → .drawing, App::MaterialObject → .material.
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

    # ── Tier 3 pre-pass: build datum map (used to enrich sketch planes) ───────
    try:
        datum_map = build_datum_map(doc)
    except Exception as exc:
        logger.warning("Tier 3 datum map build failed: %s", exc)
        datum_map = {}

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

        # Tier 3: enrich sketch plane with datum attachment, if any
        if datum_map:
            datum_attach = sketch_attachment_from_datum(sketch_obj, datum_map)
            if datum_attach is not None:
                sketch_payload["plane"]["datum_attachment"] = datum_attach

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

    # ── Tier 2: Spreadsheet → .equations ─────────────────────────────────────
    sheet_objects = doc.objects_by_type("Spreadsheet::Sheet")
    spreadsheets_translated = 0

    for sheet_obj in sheet_objects:
        try:
            eq_payload = translate_spreadsheet(sheet_obj)
        except Exception as exc:
            warnings.append(
                f"spreadsheet '{sheet_obj.name}': translation failed — {exc}"
            )
            continue

        warnings.extend(eq_payload.get("warnings") or [])
        sheet_label = sheet_obj.label or sheet_obj.name
        filename = f"{sheet_label}.equations"
        spreadsheets_translated += 1

        created_files.append({
            "kind": "equations",
            "name": filename,
            "freecad_name": sheet_obj.name,
            "placeholder_id": None,
            "payload": eq_payload,
        })

    # ── Tier 2: TechDraw DrawPage → .drawing ─────────────────────────────────
    page_objects = doc.objects_by_type("TechDraw::DrawPage")
    drawings_translated = 0

    for page_obj in page_objects:
        try:
            drawing_payload = translate_drawpage(page_obj, doc)
        except Exception as exc:
            warnings.append(
                f"TechDraw page '{page_obj.name}': translation failed — {exc}"
            )
            continue

        warnings.extend(drawing_payload.get("warnings") or [])
        page_label = page_obj.label or page_obj.name
        filename = f"{page_label}.drawing"
        drawings_translated += 1

        created_files.append({
            "kind": "drawing",
            "name": filename,
            "freecad_name": page_obj.name,
            "placeholder_id": None,
            "payload": drawing_payload,
        })

    # ── Tier 2: App::MaterialObject → .material ───────────────────────────────
    material_objects = doc.objects_by_type("App::MaterialObject")
    materials_translated = 0

    for mat_obj in material_objects:
        try:
            mat_payload = translate_material(mat_obj)
        except Exception as exc:
            warnings.append(
                f"material '{mat_obj.name}': translation failed — {exc}"
            )
            continue

        warnings.extend(mat_payload.get("warnings") or [])
        mat_label = mat_obj.label or mat_obj.name
        filename = f"{mat_label}.material"
        materials_translated += 1

        created_files.append({
            "kind": "material",
            "name": filename,
            "freecad_name": mat_obj.name,
            "placeholder_id": None,
            "payload": mat_payload,
        })

    # ── Tier 3: PartDesign datums → .sketch plane refs ───────────────────────
    # Datums themselves are not emitted as standalone files; they enrich sketches
    # above.  Count them for stats.
    datums_translated = len(datum_map)

    # ── Tier 3: Draft Workbench objects → .sketch / .feature ─────────────────
    # Collect ALL Draft:: objects — known types produce files, unknown types
    # call translate_draft_object which emits a skip-with-warning result.
    draft_translated = 0
    draft_objects = [o for o in doc.objects if o.type.startswith("Draft::")]

    for draft_obj in draft_objects:
        try:
            draft_result = translate_draft_object(draft_obj)
        except Exception as exc:
            warnings.append(
                f"Draft object '{draft_obj.name}' ({draft_obj.type}): "
                f"translation failed — {exc}"
            )
            continue

        warnings.extend(draft_result.get("warnings") or [])

        if draft_result.get("kind") == "skipped":
            continue

        created_files.append({
            "kind": draft_result["kind"],
            "name": draft_result.get("name", f"{draft_obj.label}.{draft_result['kind']}"),
            "freecad_name": draft_result.get("freecad_name", draft_obj.name),
            "placeholder_id": None,
            "payload": draft_result.get("payload", {}),
        })
        draft_translated += 1

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
        "spreadsheets": spreadsheets_translated,
        "drawings": drawings_translated,
        "materials": materials_translated,
        "datums": datums_translated,
        "draft_objects": draft_translated,
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
