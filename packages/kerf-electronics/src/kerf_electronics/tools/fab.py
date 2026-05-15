"""
LLM tools for PCB fabrication output generation.

Tools:
  export_gerber       — CircuitJSON → Gerber RS-274X per-layer file set
  export_fab_package  — CircuitJSON → zip bundle (Gerbers + Excellon + P&P +
                        fab BOM + IPC-2581) ready for upload to a fab house

These tools accept circuit_json (parsed CircuitJSON array) and return
structured payloads.  The actual file bytes / zip content is returned as
base64-encoded data so the LLM can offer the user a download link.
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_electronics.fab.gerber import export_gerber
from kerf_electronics.fab.excellon import export_excellon
from kerf_electronics.fab.pnp import export_pnp
from kerf_electronics.fab.fab_bom import export_fab_bom
from kerf_electronics.fab.ipc2581 import export_ipc2581


# ─── export_gerber ────────────────────────────────────────────────────────────

export_gerber_spec = ToolSpec(
    name="export_gerber",
    description=(
        "Export a CircuitJSON board as Gerber RS-274X files (one per layer). "
        "Returns a list of {filename, content_b64} objects — one entry per layer "
        "(GTL top copper, GBL bottom copper, GTO/GBO silkscreen, GTS/GBS soldermask, "
        "GKO board outline, inner layers if present). "
        "Pass the circuit_json array from the active .circuit.tsx file. "
        "Use this to generate individual Gerber files; for a complete fab package "
        "use export_fab_package instead."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the board file.",
                "items": {"type": "object"},
            },
            "stem": {
                "type": "string",
                "description": "Base filename stem (no extension). Defaults to 'board'.",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(export_gerber_spec)
async def run_export_gerber(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    stem = a.get("stem", "board") or "board"

    try:
        files = export_gerber(circuit_json, stem=stem)
    except Exception as e:
        return err_payload(f"Gerber export failed: {e}", "EXPORT_ERROR")

    layers = [
        {
            "filename": fname,
            "content_b64": base64.b64encode(content.encode()).decode(),
        }
        for fname, content in sorted(files.items())
    ]

    return ok_payload({
        "layer_count": len(layers),
        "layers": layers,
        "message": (
            f"Exported {len(layers)} Gerber layer(s). "
            "Decode each content_b64 to obtain the RS-274X file text."
        ),
    })


# ─── export_fab_package ───────────────────────────────────────────────────────

export_fab_package_spec = ToolSpec(
    name="export_fab_package",
    description=(
        "Bundle a complete PCB fabrication package from a CircuitJSON board. "
        "Returns a zip archive (base64-encoded) containing: "
        "Gerber RS-274X per-layer files, Excellon drill file(s), "
        "pick-and-place CSVs (top + bottom), fab BOM CSV, and an IPC-2581 XML. "
        "This is the deliverable a fab house ingests (upload to JLC/PCBWay/MacroFab). "
        "The zip filename is <stem>-fab.zip."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the board file.",
                "items": {"type": "object"},
            },
            "stem": {
                "type": "string",
                "description": "Base filename stem used for all files (default: 'board').",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(export_fab_package_spec)
async def run_export_fab_package(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    stem = a.get("stem", "board") or "board"

    try:
        gerber_files = export_gerber(circuit_json, stem=stem)
        drill_files = export_excellon(circuit_json, stem=stem)
        pnp_files = export_pnp(circuit_json, stem=stem)
        bom_files = export_fab_bom(circuit_json, stem=stem)
        ipc_files = export_ipc2581(circuit_json, stem=stem)
    except Exception as e:
        return err_payload(f"fab package export failed: {e}", "EXPORT_ERROR")

    all_files: dict[str, str] = {}
    all_files.update(gerber_files)
    all_files.update(drill_files)
    all_files.update(pnp_files)
    all_files.update(bom_files)
    all_files.update(ipc_files)

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, content in sorted(all_files.items()):
            zf.writestr(fname, content.encode("utf-8"))

    zip_bytes = buf.getvalue()
    zip_b64 = base64.b64encode(zip_bytes).decode()
    zip_filename = f"{stem}-fab.zip"

    manifest = sorted(all_files.keys())

    return ok_payload({
        "zip_filename": zip_filename,
        "zip_b64": zip_b64,
        "zip_size_bytes": len(zip_bytes),
        "manifest": manifest,
        "gerber_layers": sorted(gerber_files.keys()),
        "drill_files": sorted(drill_files.keys()),
        "pnp_files": sorted(pnp_files.keys()),
        "bom_files": sorted(bom_files.keys()),
        "ipc2581_file": sorted(ipc_files.keys()),
        "message": (
            f"Fab package ready: {zip_filename} ({len(zip_bytes):,} bytes). "
            f"Contains {len(manifest)} files: "
            f"{len(gerber_files)} Gerber layer(s), "
            f"{len(drill_files)} drill file(s), "
            f"{len(pnp_files)} P&P CSV(s), "
            f"{len(bom_files)} BOM CSV(s), "
            f"{len(ipc_files)} IPC-2581 XML(s)."
        ),
    })
