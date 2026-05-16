"""
LLM tools for one-click PCB fab bundle generation.

Tools:
  fab_bundle_export — CircuitJSON + vendor → zip-ready file dict (base64 zip)
  fab_readme_export — CircuitJSON + vendor → vendor-specific README.txt text
  fab_vendor_presets — list all supported vendors and their default options

The bundle includes vendor-specific naming for Gerber layers, Excellon drill
files, pick-and-place CSV, BOM CSV, optional IPC-2581, and a README.txt with
stackup / surface finish / upload instructions.

Supported vendors: jlcpcb, pcbway, oshpark, seeed, allpcb.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_electronics.fab.bundle import (
    fab_bundle,
    fab_readme,
    bundle_zip,
    vendor_presets,
)


# ─── fab_bundle_export ────────────────────────────────────────────────────────

fab_bundle_export_spec = ToolSpec(
    name="fab_bundle_export",
    description=(
        "Generate a one-click PCB fabrication bundle from a CircuitJSON board, "
        "ready to upload to a fab house. "
        "Returns a zip archive (base64-encoded) containing vendor-specific "
        "Gerber files (one per layer, with the fab house's expected naming), "
        "Excellon drill file, pick-and-place CSV, BOM CSV, optional IPC-2581 "
        "XML, and a README.txt with stackup/upload instructions. "
        "Supported vendors: jlcpcb (default), pcbway, oshpark, seeed, allpcb. "
        "JLCPCB output uses 'gerber_*.gbr' naming + CPL/BOM format required by "
        "their upload portal. OSHPark output uses standard Gerber extensions "
        "(.GTL/.GBL/.GTS etc.) that their parser detects automatically. "
        "Use this for the 'export to fab' / 'download gerbers' user action."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the board file.",
                "items": {"type": "object"},
            },
            "vendor": {
                "type": "string",
                "description": (
                    "Target fab house. One of: jlcpcb, pcbway, oshpark, seeed, allpcb. "
                    "Defaults to 'jlcpcb'."
                ),
                "enum": ["jlcpcb", "pcbway", "oshpark", "seeed", "allpcb"],
            },
            "stem": {
                "type": "string",
                "description": (
                    "Base filename stem used for all output files (e.g. 'my-board'). "
                    "Defaults to 'board'."
                ),
            },
            "copper_weight": {
                "type": "string",
                "description": (
                    "Copper weight for outer layers, e.g. '1oz', '2oz'. Default '1oz'."
                ),
            },
            "surface_finish": {
                "type": "string",
                "description": (
                    "PCB surface finish. Common values: 'HASL(with lead)', 'HASL(lead free)', "
                    "'ENIG', 'OSP'. Vendor default if omitted."
                ),
            },
            "soldermask": {
                "type": "string",
                "description": (
                    "Soldermask colour: 'green', 'black', 'blue', 'red', 'white', 'yellow', "
                    "'purple'. Default 'green'."
                ),
            },
            "silkscreen": {
                "type": "string",
                "description": "Silkscreen colour: 'white' or 'black'. Default 'white'.",
            },
            "board_thickness": {
                "type": "string",
                "description": (
                    "Board thickness string, e.g. '1.6mm', '0.8mm', '2.0mm'. Default '1.6mm'."
                ),
            },
            "special": {
                "type": "string",
                "description": "Special fabrication instructions appended to the README.",
            },
            "include_ipc2581": {
                "type": "boolean",
                "description": (
                    "If true, include an IPC-2581 XML in the bundle. "
                    "Default: false for JLCPCB/OSHPark, true for PCBWay."
                ),
            },
        },
        "required": ["circuit_json"],
    },
)


@register(fab_bundle_export_spec)
async def run_fab_bundle_export(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    vendor = str(a.get("vendor", "jlcpcb") or "jlcpcb").lower().strip()

    # Build options dict from explicit args (only keys that were provided)
    options: dict = {}
    for key in (
        "stem", "copper_weight", "surface_finish", "soldermask",
        "silkscreen", "board_thickness", "special", "include_ipc2581",
    ):
        if key in a and a[key] is not None:
            options[key] = a[key]

    file_dict = fab_bundle(circuit_json, vendor=vendor, options=options)

    if "ERROR" in file_dict:
        error_msg = file_dict["ERROR"].decode("utf-8") if isinstance(file_dict["ERROR"], bytes) else str(file_dict["ERROR"])
        return err_payload(error_msg, "BAD_ARGS")

    zip_bytes = bundle_zip(file_dict)
    zip_b64 = base64.b64encode(zip_bytes).decode()

    stem = options.get("stem", "board") or "board"
    zip_filename = f"{stem}-{vendor}-fab.zip"

    manifest = sorted(file_dict.keys())

    # Categorise files for the summary
    gerber_files = [f for f in manifest if f.endswith(".gbr") or
                    any(f.endswith(f".{ext}") for ext in ["GTL", "GBL", "GTS", "GBS", "GTO", "GBO", "GTP", "GBP", "GKO"])]
    drill_files = [f for f in manifest if f.endswith(".DRL") or f.endswith(".drl")]
    pnp_files = [f for f in manifest if "pnp" in f.lower() or "cpl" in f.lower()]
    bom_files = [f for f in manifest if "bom" in f.lower()]
    readme_files = [f for f in manifest if f == "README.txt"]
    ipc_files = [f for f in manifest if f.endswith(".xml")]

    from kerf_electronics.fab.bundle import _VENDOR_NAMES
    vendor_name = _VENDOR_NAMES.get(vendor, vendor.upper())

    return ok_payload({
        "zip_filename": zip_filename,
        "zip_b64": zip_b64,
        "zip_size_bytes": len(zip_bytes),
        "vendor": vendor,
        "manifest": manifest,
        "gerber_files": gerber_files,
        "drill_files": drill_files,
        "pnp_files": pnp_files,
        "bom_files": bom_files,
        "readme": readme_files,
        "ipc_files": ipc_files,
        "message": (
            f"{vendor_name} fab bundle ready: {zip_filename} "
            f"({len(zip_bytes):,} bytes, {len(manifest)} files). "
            f"{len(gerber_files)} Gerber layer(s), "
            f"{len(drill_files)} drill file(s), "
            f"{len(pnp_files)} PnP CSV(s), "
            f"{len(bom_files)} BOM CSV(s). "
            "Decode zip_b64 to get the ZIP archive."
        ),
    })


# ─── fab_readme_export ────────────────────────────────────────────────────────

fab_readme_export_spec = ToolSpec(
    name="fab_readme_export",
    description=(
        "Generate a vendor-specific README.txt for a PCB fabrication bundle. "
        "The README includes: PCB stackup description, copper weight, surface "
        "finish, soldermask/silkscreen colours, board dimensions (extracted from "
        "the CircuitJSON), file contents list, and step-by-step upload instructions "
        "for the chosen fab house. "
        "Use this when the user wants to see or preview the fab instructions, or "
        "when generating a fab package for a human to review before uploading."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array (used to extract board dimensions).",
                "items": {"type": "object"},
            },
            "vendor": {
                "type": "string",
                "description": "Target fab house. One of: jlcpcb, pcbway, oshpark, seeed, allpcb.",
                "enum": ["jlcpcb", "pcbway", "oshpark", "seeed", "allpcb"],
            },
            "copper_weight": {"type": "string"},
            "surface_finish": {"type": "string"},
            "soldermask": {"type": "string"},
            "silkscreen": {"type": "string"},
            "board_thickness": {"type": "string"},
            "special": {"type": "string"},
            "stem": {"type": "string"},
        },
        "required": ["circuit_json"],
    },
)


@register(fab_readme_export_spec)
async def run_fab_readme_export(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        circuit_json = []

    vendor = str(a.get("vendor", "jlcpcb") or "jlcpcb").lower().strip()

    options: dict = {}
    for key in ("stem", "copper_weight", "surface_finish", "soldermask",
                "silkscreen", "board_thickness", "special", "include_ipc2581"):
        if key in a and a[key] is not None:
            options[key] = a[key]

    readme_text = fab_readme(circuit_json, vendor=vendor, options=options)

    from kerf_electronics.fab.bundle import _VENDOR_NAMES
    vendor_name = _VENDOR_NAMES.get(vendor, vendor.upper())

    return ok_payload({
        "vendor": vendor,
        "readme_text": readme_text,
        "line_count": readme_text.count("\n"),
        "message": (
            f"README.txt generated for {vendor_name} "
            f"({readme_text.count(chr(10))} lines). "
            "See readme_text for the full content."
        ),
    })


# ─── fab_vendor_presets ───────────────────────────────────────────────────────

fab_vendor_presets_spec = ToolSpec(
    name="fab_vendor_presets",
    description=(
        "Return the list of supported PCB fab vendors and their default fabrication "
        "options (copper weight, surface finish, soldermask, silkscreen, board "
        "thickness, whether IPC-2581 is included by default). "
        "Use this to discover supported vendors before calling fab_bundle_export, "
        "or to show the user what options are available."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


@register(fab_vendor_presets_spec)
async def run_fab_vendor_presets(ctx: Any, args: bytes) -> str:
    presets = vendor_presets()
    return ok_payload({
        "vendors": list(presets.keys()),
        "presets": presets,
        "message": (
            f"Supported vendors: {', '.join(presets.keys())}. "
            "See presets for each vendor's default options."
        ),
    })
