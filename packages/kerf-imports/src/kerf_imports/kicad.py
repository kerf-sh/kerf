"""
KiCad project import via kiutils.

POST /import-kicad
Body: {
    "project_path": string
}

OR multipart file upload with the KiCad project files.

Returns: {
    "circuit_json": string,
    "warnings": []
}
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import json
import tempfile
import zipfile
import os
from pathlib import Path
from typing import Optional

from kerf_imports._compat import safe_basename, _safe_extract

router = APIRouter()


@router.post("/import-kicad")
async def import_kicad(
    req: Optional[dict] = None,
    file: Optional[UploadFile] = File(None)
):
    warnings = []
    errors = []

    try:
        import kiutils
    except ImportError as e:
        return {
            "circuit_json": "",
            "warnings": [],
            "errors": [f"kiutils not available: {e}"],
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        if req and req.get("project_path"):
            project_path = req["project_path"]
            try:
                circuit_json = parse_kicad_project(project_path)
            except Exception as e:
                errors.append(str(e))
                return {
                    "circuit_json": "",
                    "warnings": warnings,
                    "errors": errors,
                }

        elif file:
            try:
                safe_name = safe_basename(file.filename or "")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            file_path = tmp_path / safe_name
            content = await file.read()
            file_path.write_bytes(content)

            if safe_name.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as z:
                    _safe_extract(z, tmp_path)

            kicad_projects = list(tmp_path.glob("*.kicad_pro"))
            if not kicad_projects:
                kicad_projects = list(tmp_path.glob("*.kicad_sch"))

            if kicad_projects:
                try:
                    circuit_json = parse_kicad_project(str(kicad_projects[0].parent))
                except Exception as e:
                    errors.append(str(e))
                    return {
                        "circuit_json": "",
                        "warnings": warnings,
                        "errors": errors,
                    }
            else:
                errors.append("No KiCad project files found in upload")
                return {
                    "circuit_json": "",
                    "warnings": warnings,
                    "errors": errors,
                }
        else:
            raise HTTPException(status_code=400, detail="project_path or file required")

    return {
        "circuit_json": circuit_json,
        "warnings": warnings,
        "errors": errors,
    }


def _safe_get(obj, *attrs, default=None):
    """Safely walk an attribute chain, returning default on any AttributeError."""
    cur = obj
    for attr in attrs:
        try:
            cur = getattr(cur, attr)
        except AttributeError:
            return default
    return cur if cur is not None else default


def parse_kicad_project(project_path: str) -> str:
    from kiutils.schematic import Schematic
    from kiutils.pcb import Pcb
    import json

    project_dir = Path(project_path)
    result = {
        "schematics": [],
        "pcbs": [],
        "warnings": [],
        "errors": [],
    }

    for sch_file in sorted(project_dir.glob("*.kicad_sch")):
        try:
            sch = Schematic.from_file(str(sch_file))
            sch_dict = {
                "filename": sch_file.name,
                "title_block": {},
                "components": [],
                "nets": [],
            }

            # Title block
            tb = _safe_get(sch, 'titleBlock')
            if tb:
                sch_dict["title_block"] = {
                    "title": _safe_get(tb, 'title', default='') or '',
                    "company": _safe_get(tb, 'company', default='') or '',
                    "rev": _safe_get(tb, 'revision', default='') or '',
                }

            # Schematic symbols (components)
            symbols = _safe_get(sch, 'schematicSymbols') or []
            for sym in symbols:
                try:
                    ref = ''
                    value = ''
                    # Properties list: [{key, value}] or dict-like
                    props = _safe_get(sym, 'properties') or []
                    for prop in props:
                        pkey = _safe_get(prop, 'key') or _safe_get(prop, 'name') or ''
                        pval = _safe_get(prop, 'value') or ''
                        if pkey.lower() == 'reference':
                            ref = str(pval)
                        elif pkey.lower() == 'value':
                            value = str(pval)

                    # Fallback: direct attributes
                    if not ref:
                        ref = str(_safe_get(sym, 'reference') or _safe_get(sym, 'ref') or '')
                    if not value:
                        value = str(_safe_get(sym, 'value') or '')

                    # Position
                    pos = _safe_get(sym, 'position') or _safe_get(sym, 'pos')
                    x = float(_safe_get(pos, 'X', default=0) or 0) if pos else 0.0
                    y = float(_safe_get(pos, 'Y', default=0) or 0) if pos else 0.0

                    if ref or value:
                        sch_dict["components"].append({
                            "ref": ref,
                            "value": value,
                            "x": x,
                            "y": y,
                        })
                except Exception as sym_err:
                    result["warnings"].append(f"{sch_file.name}: symbol parse error: {sym_err}")

            # Nets from netlist if available
            try:
                nets = _safe_get(sch, 'nets') or []
                for net in nets:
                    net_name = str(_safe_get(net, 'name') or '')
                    pins = []
                    for pin in (_safe_get(net, 'pins') or []):
                        pin_ref = str(_safe_get(pin, 'ref') or _safe_get(pin, 'component') or '')
                        pin_num = str(_safe_get(pin, 'pin') or _safe_get(pin, 'number') or '')
                        if pin_ref:
                            pins.append(f"{pin_ref}.{pin_num}" if pin_num else pin_ref)
                    sch_dict["nets"].append({"name": net_name, "pins": pins})
            except Exception:
                pass  # nets extraction is best-effort

            result["schematics"].append(sch_dict)
        except Exception as e:
            result["errors"].append(f"{sch_file.name}: {e}")

    for pcb_file in sorted(project_dir.glob("*.kicad_pcb")):
        try:
            pcb = Pcb.from_file(str(pcb_file))
            footprints_list = _safe_get(pcb, 'footprints') or []
            fps = []
            for fp in footprints_list:
                try:
                    ref = str(_safe_get(fp, 'entryName') or _safe_get(fp, 'reference') or '')
                    value = ''
                    # value from properties
                    for prop in (_safe_get(fp, 'properties') or []):
                        pkey = _safe_get(prop, 'key') or _safe_get(prop, 'name') or ''
                        if pkey.lower() == 'value':
                            value = str(_safe_get(prop, 'value') or '')
                            break
                    pos = _safe_get(fp, 'position') or _safe_get(fp, 'pos')
                    x = float(_safe_get(pos, 'X', default=0) or 0) if pos else 0.0
                    y = float(_safe_get(pos, 'Y', default=0) or 0) if pos else 0.0
                    layer = str(_safe_get(fp, 'layer') or 'F.Cu')
                    fps.append({"ref": ref, "value": value, "x": x, "y": y, "layer": layer})
                except Exception as fp_err:
                    result["warnings"].append(f"{pcb_file.name}: footprint parse error: {fp_err}")

            result["pcbs"].append({
                "filename": pcb_file.name,
                "footprint_count": len(footprints_list),
                "footprints": fps,
            })
        except Exception as e:
            result["errors"].append(f"{pcb_file.name}: {e}")

    return json.dumps(result)
