"""LLM tool: verify_pin_mapping(fw_path, pcb_path)

Cross-checks that the firmware's pin assignments agree with the PCB netlist.

Detects:
- Pins the firmware uses that don't exist on the MCU footprint in the PCB.
- Firmware driving a pin as OUTPUT when the PCB routes it to an INPUT_ONLY net.
- Incomplete I2C bus (SDA declared but SCL absent, or vice versa).
- Pin-net mismatch (firmware uses pin 21 for SDA but PCB routes SDA to pin 22).

Schema
------
{
  "fw_path":  "<absolute path to firmware sketch file (.ino) or directory>",
  "pcb_path": "<absolute path to .kicad_pcb file>",
  "mcu_ref":  "<optional KiCad ref, e.g. U1; omit to auto-detect first U* part>"
}

Returns
-------
ok_payload({
    "ok": bool,
    "missing_pins": [...],
    "wrong_load": [...],
    "bus_incomplete": [...],
    "pin_mismatch": [...]
})
err_payload(...) on I/O or parse failure.

Error codes
-----------
  BAD_ARGS         — missing required arguments
  FW_NOT_FOUND     — firmware path does not exist
  PCB_NOT_FOUND    — pcb_path does not exist
  PARSE_ERROR      — failed to parse PCB or firmware
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_firmware._compat import (  # type: ignore
        ToolSpec, err_payload, ok_payload, register, ProjectCtx,
    )

from kerf_firmware.pcb_xcheck import verify


_spec = ToolSpec(
    name="verify_pin_mapping",
    description=(
        "Cross-check the firmware's pin assignments against the PCB netlist. "
        "Detects: pins used in firmware that don't exist on the MCU footprint; "
        "firmware driving an OUTPUT pin that the PCB routes to an INPUT_ONLY net; "
        "incomplete I2C bus (SDA without SCL or vice versa); "
        "pin–net mismatches (e.g. firmware uses pin 21 for SDA but PCB routes SDA to pin 22). "
        "Provide the path to the firmware .ino file (or its directory) and the .kicad_pcb file. "
        "Optionally specify mcu_ref (e.g. 'U1') to target a specific MCU footprint; "
        "defaults to the first 'U*' footprint found in the PCB."
    ),
    input_schema={
        "type": "object",
        "required": ["fw_path", "pcb_path"],
        "properties": {
            "fw_path": {
                "type": "string",
                "description": (
                    "Absolute path to the firmware sketch (.ino) or to a directory "
                    "containing .ino / .cpp / .h source files."
                ),
            },
            "pcb_path": {
                "type": "string",
                "description": "Absolute path to the KiCad v6/v7 .kicad_pcb file.",
            },
            "mcu_ref": {
                "type": "string",
                "description": (
                    "KiCad component reference for the MCU (e.g. 'U1'). "
                    "Defaults to the first 'U*' footprint in the PCB."
                ),
                "default": None,
            },
        },
    },
)


@register(_spec)
def verify_pin_mapping(args: dict[str, Any], ctx: "ProjectCtx | None" = None) -> str:
    fw_path_raw = args.get("fw_path", "")
    pcb_path_raw = args.get("pcb_path", "")
    mcu_ref = args.get("mcu_ref") or None

    if not fw_path_raw or not pcb_path_raw:
        return err_payload("fw_path and pcb_path are required", "BAD_ARGS")

    fw_path = Path(fw_path_raw)
    pcb_path = Path(pcb_path_raw)

    # ── Load firmware sources ─────────────────────────────────────────────────
    if not fw_path.exists():
        return err_payload(f"Firmware path not found: {fw_path}", "FW_NOT_FOUND")

    fw_sources: list[str] = []
    if fw_path.is_dir():
        extensions = {".ino", ".cpp", ".c", ".h"}
        for fpath in fw_path.rglob("*"):
            if fpath.suffix.lower() in extensions:
                try:
                    fw_sources.append(fpath.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    else:
        try:
            fw_sources.append(fw_path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            return err_payload(str(exc), "FW_NOT_FOUND")

    if not fw_sources:
        return err_payload(
            f"No .ino/.cpp/.h source files found at: {fw_path}", "FW_NOT_FOUND"
        )

    # ── Load PCB ──────────────────────────────────────────────────────────────
    if not pcb_path.exists():
        return err_payload(f"PCB file not found: {pcb_path}", "PCB_NOT_FOUND")

    try:
        pcb_text = pcb_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return err_payload(str(exc), "PCB_NOT_FOUND")

    # ── Cross-check ───────────────────────────────────────────────────────────
    try:
        report = verify(fw_sources=fw_sources, pcb_text=pcb_text, mcu_ref=mcu_ref)
    except Exception as exc:  # noqa: BLE001
        return err_payload(f"Parse/compare error: {exc}", "PARSE_ERROR")

    return ok_payload(report.as_dict())
