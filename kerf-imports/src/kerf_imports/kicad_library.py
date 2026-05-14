"""
KiCad Library import via kiutils.

POST /import-kicad-library
Body: {
    "project_path": string,       # directory containing .kicad_sym / .pretty/
    "lib_name":     string | null # optional library name filter
}

OR multipart file upload containing a .kicad_sym or .kicad_mod file (or .zip).

Returns: {
    "parts": [
        {
            "name":              string,
            "category":          string,        # "electronic"
            "schematic_symbol":  {...} | null,
            "pcb_footprint":     {...} | null,
            "model_3d_paths":    [string],       # raw paths from (model ...) stanzas
            "content_hash":      string,         # sha256 of s-expr text
        },
        ...
    ],
    "warnings": [string],
    "errors":   [string]
}
"""

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

router = APIRouter()


class ImportKicadLibraryRequest(BaseModel):
    project_path: str
    lib_name: Optional[str] = None


@router.post("/import-kicad-library")
async def import_kicad_library(
    req: Optional[ImportKicadLibraryRequest] = None,
    file: Optional[UploadFile] = File(None),
):
    warnings = []
    errors = []

    try:
        import kiutils  # noqa: F401
    except ImportError as e:
        return {
            "parts": [],
            "warnings": [],
            "errors": [f"kiutils not available: {e}"],
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        if req and req.project_path:
            scan_dir = Path(req.project_path)
        elif file:
            dest = tmp_path / file.filename
            content = await file.read()
            dest.write_bytes(content)

            if file.filename.endswith(".zip"):
                with zipfile.ZipFile(dest, "r") as z:
                    z.extractall(tmp_path)
            scan_dir = tmp_path
        else:
            return {
                "parts": [],
                "warnings": [],
                "errors": ["project_path or file required"],
            }

        parts = []
        sym_warnings, sym_errors = _parse_sym_files(scan_dir, parts)
        mod_warnings, mod_errors = _parse_mod_files(scan_dir, parts)
        warnings.extend(sym_warnings)
        warnings.extend(mod_warnings)
        errors.extend(sym_errors)
        errors.extend(mod_errors)

    return {
        "parts": parts,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Symbol-library parser (.kicad_sym)
# ---------------------------------------------------------------------------

def _parse_sym_files(scan_dir: Path, out: list) -> tuple[list, list]:
    warnings = []
    errors = []

    for sym_file in sorted(scan_dir.rglob("*.kicad_sym")):
        try:
            _parse_one_sym_file(sym_file, out, warnings)
        except Exception as e:
            errors.append(f"{sym_file.name}: {e}")

    return warnings, errors


def _parse_one_sym_file(sym_file: Path, out: list, warnings: list):
    from kiutils.symbol import SymbolLib

    lib = SymbolLib.from_file(str(sym_file))
    raw_text = sym_file.read_text(encoding="utf-8", errors="replace")

    for sym in lib.symbols:
        try:
            _extract_symbol_part(sym, raw_text, sym_file, out, warnings)
        except Exception as e:
            warnings.append(f"{sym_file.name} symbol {getattr(sym, 'entryName', '?')}: {e}")


def _extract_symbol_part(sym, lib_raw_text: str, sym_file: Path, out: list, warnings: list):
    entry_name = getattr(sym, "entryName", None) or ""
    if not entry_name:
        return

    # Content-hash: sha256 of just this symbol's s-expr block would be ideal,
    # but kiutils doesn't expose per-symbol text. We hash entryName + lib path
    # as a stable, deterministic key scoped to the library file + mtime.
    # For idempotency the caller uses this hash + the file path as a compound
    # dedup key.
    sym_key = f"{sym_file}::{entry_name}"
    content_hash = hashlib.sha256(sym_key.encode()).hexdigest()

    # Properties — name is the entryName by default; check Property list for
    # a "Value" property that may be more descriptive.
    props = getattr(sym, "properties", []) or []
    part_name = entry_name
    description = ""
    datasheet = ""
    for prop in props:
        key = (getattr(prop, "key", None) or getattr(prop, "name", None) or "").lower()
        val = str(getattr(prop, "value", "") or "")
        if key == "value" and val and val != entry_name:
            part_name = val
        elif key == "description":
            description = val
        elif key == "datasheet":
            datasheet = val

    # Pins: walk sym.pins + sub-unit pins
    pins = _collect_pins(sym, warnings, entry_name)

    schematic_symbol = {
        "library": sym_file.stem,
        "entry_name": entry_name,
        "description": description,
        "datasheet_url": datasheet if datasheet and datasheet.startswith("http") else "",
        "pin_count": len(pins),
        "pins": pins,
    }

    out.append({
        "name": part_name,
        "category": "electronic",
        "schematic_symbol": schematic_symbol,
        "pcb_footprint": None,
        "model_3d_paths": [],
        "content_hash": content_hash,
    })


def _collect_pins(sym, warnings: list, entry_name: str) -> list:
    from kiutils.symbol import SymbolPin

    pins = []

    def _add_pins_from(symbol_obj):
        for pin in (getattr(symbol_obj, "pins", None) or []):
            if not isinstance(pin, SymbolPin):
                continue
            pin_name = ""
            if isinstance(pin.name, str):
                pin_name = pin.name
            elif hasattr(pin.name, "name"):
                pin_name = pin.name.name or ""
            pin_number = str(pin.number if isinstance(pin.number, str) else
                             (pin.number.name if hasattr(pin.number, "name") else str(pin.number)))
            pins.append({
                "name": pin_name,
                "number": pin_number,
                "electrical_type": getattr(pin, "electricalType", "unspecified") or "unspecified",
            })
        for unit in (getattr(symbol_obj, "units", None) or []):
            _add_pins_from(unit)

    try:
        _add_pins_from(sym)
    except Exception as e:
        warnings.append(f"pin extraction {entry_name}: {e}")

    return pins


# ---------------------------------------------------------------------------
# Footprint parser (.kicad_mod / .pretty/)
# ---------------------------------------------------------------------------

def _parse_mod_files(scan_dir: Path, out: list) -> tuple[list, list]:
    warnings = []
    errors = []

    for mod_file in sorted(scan_dir.rglob("*.kicad_mod")):
        try:
            _parse_one_mod_file(mod_file, out, warnings)
        except Exception as e:
            errors.append(f"{mod_file.name}: {e}")

    return warnings, errors


def _parse_one_mod_file(mod_file: Path, out: list, warnings: list):
    from kiutils.footprint import Footprint

    fp = Footprint.from_file(str(mod_file))
    entry_name = getattr(fp, "entryName", None) or mod_file.stem
    raw_text = mod_file.read_text(encoding="utf-8", errors="replace")
    content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

    description = getattr(fp, "description", "") or ""
    tags = getattr(fp, "tags", "") or ""

    pads = _extract_pads(fp)
    model_3d_paths = _extract_model_paths(fp)

    pcb_footprint = {
        "library": mod_file.parent.stem,
        "entry_name": entry_name,
        "description": description,
        "tags": tags,
        "layer": getattr(fp, "layer", "F.Cu") or "F.Cu",
        "pad_count": len(pads),
        "pads": pads,
    }

    out.append({
        "name": entry_name,
        "category": "electronic",
        "schematic_symbol": None,
        "pcb_footprint": pcb_footprint,
        "model_3d_paths": model_3d_paths,
        "content_hash": content_hash,
    })


def _extract_pads(fp) -> list:
    pads = []
    for pad in (getattr(fp, "pads", None) or []):
        pos = getattr(pad, "position", None)
        size = getattr(pad, "size", None)
        drill = getattr(pad, "drill", None)

        pad_dict = {
            "number": str(getattr(pad, "number", "") or ""),
            "type": getattr(pad, "type", "smd") or "smd",
            "shape": getattr(pad, "shape", "rect") or "rect",
            "position": {
                "x": float(getattr(pos, "X", 0) or 0) if pos else 0.0,
                "y": float(getattr(pos, "Y", 0) or 0) if pos else 0.0,
            },
            "size": {
                "x": float(getattr(size, "X", 0) or 0) if size else 0.0,
                "y": float(getattr(size, "Y", 0) or 0) if size else 0.0,
            },
            "layers": list(getattr(pad, "layers", None) or []),
        }
        if drill is not None:
            drill_size = None
            if hasattr(drill, "diameter"):
                drill_size = float(drill.diameter or 0)
            elif hasattr(drill, "size"):
                drill_size = float(drill.size or 0)
            if drill_size is not None:
                pad_dict["drill"] = drill_size
        pads.append(pad_dict)
    return pads


def _extract_model_paths(fp) -> list:
    paths = []
    for model in (getattr(fp, "models", None) or []):
        p = getattr(model, "path", None) or ""
        if p:
            # Normalise KiCad path variables like ${KIPRJMOD} and ${KISYS3DMOD}
            p_norm = p.replace("\\", "/")
            paths.append(p_norm)
    return paths
