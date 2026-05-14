"""
FreeCAD .fcstd file import via pythonocc.

POST /import-freecad
Body: multipart file upload with .fcstd file

Returns: {
    "geometry_json": string,
    "warnings": []
}
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

router = APIRouter()


@router.post("/import-freecad")
async def import_freecad(
    file: UploadFile = File(...)
):
    warnings = []
    errors = []

    if not file.filename.endswith(".fcstd"):
        raise HTTPException(status_code=400, detail="Only .fcstd files supported")

    try:
        from OCC.Core import BRepAlgoAPI, BRepBuilderAPI, TopAbs, TopLoc
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Shape
        import ifcopenshell
    except ImportError as e:
        return {
            "geometry_json": "",
            "warnings": [],
            "errors": [f"pythonocc/ifcopenshell not available: {e}"],
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        fcstd_path = tmp_path / file.filename

        content = await file.read()
        fcstd_path.write_bytes(content)

        try:
            geometry_json = parse_fcstd(str(fcstd_path), tmpdir)
        except Exception as e:
            errors.append(str(e))
            return {
                "geometry_json": "",
                "warnings": warnings,
                "errors": errors,
            }

    return {
        "geometry_json": geometry_json,
        "warnings": warnings,
        "errors": errors,
    }


def parse_fcstd(fcstd_path: str, tmpdir: str) -> str:
    import zipfile
    import json
    from pathlib import Path

    tmp_path = Path(tmpdir)

    with zipfile.ZipFile(fcstd_path, "r") as z:
        z.extractall(tmp_path)

    doc_xml = tmp_path / "Document.xml"
    if not doc_xml.exists():
        raise ValueError("Document.xml not found in .fcstd archive")

    geometry_data = {
        "type": "freecad_document",
        "shapes": [],
    }

    import xml.etree.ElementTree as ET
    tree = ET.parse(doc_xml)
    root = tree.getroot()

    ns = {"freecad": "http://www.freecadweb.org/wiki/index.php?title=Document_xml"}

    for obj in root.findall(".//BodyObject", ns):
        name = obj.get("name", "unknown")
        geometry_data["shapes"].append({
            "name": name,
            "type": obj.get("type", "unknown"),
        })

    if not geometry_data["shapes"]:
        for obj in root.iter():
            if obj.tag.endswith("Body"):
                name = obj.get("name", "unknown")
                geometry_data["shapes"].append({
                    "name": name,
                    "type": "Body",
                })

    return json.dumps(geometry_data)
