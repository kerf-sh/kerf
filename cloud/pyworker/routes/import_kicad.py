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
            file_path = tmp_path / file.filename
            content = await file.read()
            file_path.write_bytes(content)

            if file.filename.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as z:
                    z.extractall(tmp_path)

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


def parse_kicad_project(project_path: str) -> str:
    from kiutils.schematic import Schematic
    from kiutils.pcb import Pcb
    import json

    project_dir = Path(project_path)
    result = {
        "schematics": [],
        "pcbs": [],
        "symbols": [],
        "footprints": [],
    }

    for sch_file in project_dir.glob("*.kicad_sch"):
        try:
            sch = Schematic.from_file(str(sch_file))
            sch_dict = {
                "filename": sch_file.name,
                "sheet": str(sch.filePath) if hasattr(sch, 'filePath') else "",
                "title_block": {},
            }
            if hasattr(sch, 'titleBlock') and sch.titleBlock:
                tb = sch.titleBlock
                sch_dict["title_block"] = {
                    "title": getattr(tb, 'title', '') or '',
                    "company": getattr(tb, 'company', '') or '',
                    "rev": getattr(tb, 'revision', '') or '',
                }
            result["schematics"].append(sch_dict)
        except Exception as e:
            pass

    for pcb_file in project_dir.glob("*.kicad_pcb"):
        try:
            pcb = Pcb.from_file(str(pcb_file))
            pcb_dict = {
                "filename": pcb_file.name,
                "footprints": len(getattr(pcb, 'footprints', [])),
            }
            result["pcbs"].append(pcb_dict)
        except Exception as e:
            pass

    return json.dumps(result)
