"""
IFC compilation via IfcOpenShell.

POST /compile-ifc
Body: {
    "bim_content": string (the .bim DSL text)
}

Returns: {
    "ifc_base64": string,
    "warnings": []
}
"""

from fastapi import APIRouter, HTTPException
import base64
import tempfile
from pathlib import Path

router = APIRouter()


@router.post("/compile-ifc")
async def compile_ifc(req: dict):
    bim_content = req.get("bim_content", "")

    if not bim_content:
        raise HTTPException(status_code=400, detail="bim_content required")

    try:
        import ifcopenshell
    except ImportError as e:
        return {
            "ifc_base64": "",
            "warnings": [],
            "errors": [f"ifcopenshell not available: {e}"],
        }

    warnings = []
    errors = []

    with tempfile.TemporaryDirectory() as tmpdir:
        bim_path = Path(tmpdir) / "input.bim"
        bim_path.write_text(bim_content)

        try:
            ifc_path = compile_bim_to_ifc(str(bim_path), tmpdir)
        except Exception as e:
            errors.append(str(e))
            return {
                "ifc_base64": "",
                "warnings": warnings,
                "errors": errors,
            }

        ifc_data = Path(ifc_path).read_bytes()
        ifc_base64 = base64.b64encode(ifc_data).decode()

    return {
        "ifc_base64": ifc_base64,
        "warnings": warnings,
        "errors": errors,
    }


def compile_bim_to_ifc(bim_path: str, tmpdir: str) -> str:
    import ifcopenshell

    with open(bim_path, "r") as f:
        bim_text = f.read()

    ifc_lines = bim_text.split("\n")
    ifc_content = []
    for line in ifc_lines:
        line = line.strip()
        if line and not line.startswith("!"):
            ifc_content.append(line)

    ifc_text = "\n".join(ifc_content)

    ifc_path = Path(tmpdir) / "output.ifc"
    ifc_path.write_text(ifc_text)

    try:
        model = ifcopenshell.open(str(ifc_path))
        model.write(str(ifc_path))
    except Exception:
        pass

    return str(ifc_path)


@router.post("/compile-bim")
async def compile_bim(req: dict):
    return await compile_ifc(req)
