"""
Rhino .3dm file import / export via rhino3dm (McNeel, BSD/MIT).

POST /import-3dm
    Multipart upload of a .3dm binary. Walks model.Objects and classifies
    each into one of: feature (BRep), sketch (planar/3D curve), surf
    (standalone Surface), mesh (Mesh), point (Point), or instance (InstanceReference).
    Returns {layers, files, stats}.

POST /export-3dm
    JSON body {files: [{kind, content_json}], layers: []}. Builds a
    rhino3dm.File3dm and returns the binary .3dm file.

rhino3dm import is try/except-gated so pyworker boots without it.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
import json
import tempfile
from pathlib import Path

router = APIRouter()

# ---------------------------------------------------------------------------
# Rhino type → Kerf kind
# ---------------------------------------------------------------------------

_RHINO_KIND_MAP = {
    # rhino3dm geometry class name → Kerf kind
    "Brep": "feature",
    "Extrusion": "feature",
    "SubD": "feature",
    "NurbsSurface": "surf",
    "RevSurface": "surf",
    "PlaneSurface": "surf",
    "NurbsCurve": "sketch",
    "LineCurve": "sketch",
    "ArcCurve": "sketch",
    "PolylineCurve": "sketch",
    "PolyCurve": "sketch",
    "Mesh": "mesh",
    "Point": "point",
    "PointCloud": "point",
    "InstanceReference": "instance",
    "InstanceDefinition": "instance",
}


def _classify(geom) -> str:
    """Return Kerf kind string for a rhino3dm geometry object."""
    if geom is None:
        return "unknown"
    cls = type(geom).__name__
    return _RHINO_KIND_MAP.get(cls, "unknown")


def _geom_to_json(geom, kind: str) -> dict:
    """Serialize rhino3dm geometry to a Kerf-compatible JSON dict."""
    base: dict = {"source": "rhino3dm", "kind": kind}

    try:
        if hasattr(geom, "Encode"):
            # rhino3dm objects expose Encode() → JSON string
            encoded = geom.Encode()
            if encoded:
                base["rhino_json"] = json.loads(encoded)
                return base
    except Exception:
        pass

    # Fallback: serialize what we can for simple types
    if kind == "point":
        try:
            pt = geom.Location if hasattr(geom, "Location") else geom
            base["x"] = float(pt.X)
            base["y"] = float(pt.Y)
            base["z"] = float(pt.Z)
        except Exception:
            pass

    if kind in ("sketch",) and hasattr(geom, "PointAtStart"):
        try:
            s = geom.PointAtStart
            e = geom.PointAtEnd
            base["start"] = {"x": float(s.X), "y": float(s.Y), "z": float(s.Z)}
            base["end"] = {"x": float(e.X), "y": float(e.Y), "z": float(e.Z)}
        except Exception:
            pass

    return base


# ---------------------------------------------------------------------------
# POST /import-3dm
# ---------------------------------------------------------------------------

@router.post("/import-3dm")
async def import_3dm(file: UploadFile = File(...)):
    try:
        import rhino3dm
    except ImportError as exc:
        return {
            "layers": [],
            "files": [],
            "stats": {"count_by_kind": {}},
            "errors": [f"rhino3dm not installed: {exc}"],
        }

    if not file.filename.lower().endswith(".3dm"):
        raise HTTPException(status_code=400, detail="Only .3dm files are supported")

    content = await file.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / (file.filename or "upload.3dm")
        tmp_path.write_bytes(content)

        try:
            model = rhino3dm.File3dm.Read(str(tmp_path))
        except Exception as exc:
            return {
                "layers": [],
                "files": [],
                "stats": {"count_by_kind": {}},
                "errors": [f"failed to parse .3dm: {exc}"],
            }

    if model is None:
        return {
            "layers": [],
            "files": [],
            "stats": {"count_by_kind": {}},
            "errors": ["rhino3dm returned None — file may be corrupt or unsupported version"],
        }

    # ── Layers ───────────────────────────────────────────────────────────────
    layers = []
    try:
        for layer in model.Layers:
            layers.append({
                "id": layer.Id,
                "name": layer.Name,
                "full_path": layer.FullPath,
                "color": {
                    "r": layer.Color.R,
                    "g": layer.Color.G,
                    "b": layer.Color.B,
                },
                "visible": layer.IsVisible,
                "locked": layer.IsLocked,
            })
    except Exception:
        pass

    # ── Objects ──────────────────────────────────────────────────────────────
    out_files = []
    count_by_kind: dict[str, int] = {}

    for obj in model.Objects:
        geom = obj.Geometry
        kind = _classify(geom)

        # InstanceReferences are captured as metadata only in v1
        if kind == "instance":
            meta: dict = {"source": "rhino3dm", "kind": "instance"}
            try:
                meta["instance_definition_index"] = geom.ParentIdefId
            except Exception:
                pass
            try:
                attrs = obj.Attributes
                meta["name"] = attrs.Name
                meta["layer_index"] = attrs.LayerIndex
            except Exception:
                pass
            out_files.append({
                "name": f"instance_{len(out_files)}",
                "kind": "instance",
                "content": meta,
            })
            count_by_kind["instance"] = count_by_kind.get("instance", 0) + 1
            continue

        if kind == "unknown":
            continue

        content_json = _geom_to_json(geom, kind)

        # Pull object name / layer from attributes
        obj_name = ""
        layer_index = -1
        try:
            attrs = obj.Attributes
            obj_name = attrs.Name or ""
            layer_index = attrs.LayerIndex
        except Exception:
            pass

        # Construct a filename using the kind extension
        ext_map = {
            "feature": ".feature",
            "sketch": ".sketch",
            "surf": ".surf",
            "mesh": ".mesh",
            "point": ".point",
        }
        idx = count_by_kind.get(kind, 0)
        base_name = obj_name if obj_name else f"{kind}_{idx}"
        file_name = base_name + ext_map.get(kind, "")

        if layer_index >= 0 and layer_index < len(layers):
            content_json["rhino_layer"] = layers[layer_index]["name"]

        out_files.append({
            "name": file_name,
            "kind": kind,
            "content": content_json,
        })
        count_by_kind[kind] = count_by_kind.get(kind, 0) + 1

    return {
        "layers": layers,
        "files": out_files,
        "stats": {"count_by_kind": count_by_kind},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# POST /export-3dm
# ---------------------------------------------------------------------------

@router.post("/export-3dm")
async def export_3dm(body: dict):
    try:
        import rhino3dm
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"rhino3dm not installed: {exc}")

    files = body.get("files", [])
    # layers param is accepted but not strictly required for v1
    # layer_defs = body.get("layers", [])

    model = rhino3dm.File3dm()

    for f in files:
        kind = f.get("kind", "")
        content_json = f.get("content_json") or f.get("content") or {}
        if isinstance(content_json, str):
            try:
                content_json = json.loads(content_json)
            except Exception:
                content_json = {}

        rhino_json = content_json.get("rhino_json") if isinstance(content_json, dict) else None

        try:
            if rhino_json:
                # Re-decode from rhino3dm JSON representation
                encoded = json.dumps(rhino_json)
                geom = None
                if kind == "feature":
                    geom = rhino3dm.Brep.TryConvertBrep(rhino3dm.CommonObject.Decode(encoded))
                elif kind == "mesh":
                    decoded = rhino3dm.CommonObject.Decode(encoded)
                    geom = decoded if isinstance(decoded, rhino3dm.Mesh) else None
                elif kind in ("sketch",):
                    decoded = rhino3dm.CommonObject.Decode(encoded)
                    geom = decoded if hasattr(decoded, "PointAtStart") else None
                elif kind == "surf":
                    decoded = rhino3dm.CommonObject.Decode(encoded)
                    geom = decoded if isinstance(decoded, rhino3dm.Surface) else None

                if geom is not None:
                    model.Objects.Add(geom)
            else:
                # Fallback: add a point for types we can't round-trip
                if isinstance(content_json, dict) and "x" in content_json:
                    pt = rhino3dm.Point3d(
                        float(content_json.get("x", 0)),
                        float(content_json.get("y", 0)),
                        float(content_json.get("z", 0)),
                    )
                    model.Objects.AddPoint(pt)
        except Exception:
            # Skip objects that fail to add; don't abort the whole export
            continue

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "export.3dm"
        model.Write(str(out_path), 7)  # version 7
        data = out_path.read_bytes()

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="export.3dm"'},
    )
