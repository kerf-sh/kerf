"""
SPICE simulation via native ngspice batch mode.

POST /run-spice
Body: {
    "netlist": string,   -- SPICE .cir netlist text
    "analysis": {        -- analysis specification
        "type": "tran"|"dc"|"ac"|"op",
        "tstep"?: "1us",
        "tstop"?: "10ms",
        "vstart"?: number,
        "vstop"?: number,
        "vstep"?: number,
    }
}

ngspice is invoked as: ngspice -b -o output.raw input.cir
- -b: batch mode (no interactive console)
- -o: specifies output.raw file for waveform data

The .print lines in the netlist direct ngspice to output columnar
data that we parse into waveform arrays.
"""

import json
import subprocess
import tempfile
import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

Waveform = dict  # {name, kind, xUnit, yUnit, x: list[float], y: list[float]}


@router.post("/run-spice")
async def run_spice(req: dict):
    netlist = req.get("netlist", "")
    analysis = req.get("analysis", {})

    if not netlist.strip():
        raise HTTPException(status_code=400, detail="netlist is required")

    with tempfile.TemporaryDirectory() as tmpdir:
        cir_path = Path(tmpdir) / "input.cir"
        raw_path = Path(tmpdir) / "output.raw"
        lst_path = Path(tmpdir) / "output.lis"

        cir_path.write_text(netlist)

        try:
            result = run_ngspice(
                str(cir_path),
                str(raw_path),
                str(lst_path),
                analysis,
                tmpdir,
            )
        except Exception as e:
            return {"waveforms": [], "warnings": [], "errors": [str(e)]}

    return result


def run_ngspice(cir_path: str, raw_path: str, lst_path: str,
                analysis: dict, tmpdir: str) -> dict:
    cmd = ["ngspice", "-b", "-o", raw_path, cir_path]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=tmpdir,
        )
    except subprocess.TimeoutExpired:
        return {"waveforms": [], "warnings": [], "errors": ["ngspice timed out after 300s"]}

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""

    errors = []
    warnings = []

    if proc.returncode != 0:
        errors.append(f"ngspice exit {proc.returncode}: {stderr[:500]}")

    if not os.path.exists(raw_path):
        return {"waveforms": [], "warnings": warnings, "errors": errors}

    waveforms = parse_raw_file(raw_path)

    return {
        "waveforms": waveforms,
        "warnings": warnings,
        "errors": errors,
    }


def parse_raw_file(raw_path: str) -> list[Waveform]:
    waveforms = []
    content = Path(raw_path).read_text()
    lines = content.splitlines()

    if not lines:
        return waveforms

    if lines[0].startswith("Title:"):
        lines = lines[1:]

    if not lines or lines[0].strip() != "Variables:":
        return waveforms

    idx = 1
    num_vars = 0
    var_names = []
    var_types = []

    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1
        if line == "":
            continue
        if line == "Values:":
            break
        parts = line.split()
        if len(parts) >= 2:
            num_vars = int(parts[0])
            var_names.append(parts[1])
            var_types.append(parts[2] if len(parts) > 2 else "")
        if len(var_names) >= num_vars:
            break

    if not var_names or not lines or lines[idx - 1].strip() != "Values:":
        return waveforms

    idx += 1

    x_vals = []
    y_vals_by_var = [[] for _ in var_names]

    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1
        if not line:
            continue
        if line == "Binary:":
            break
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            point_idx = int(parts[0].strip())
            x_val = float(parts[1].strip())
        except ValueError:
            continue

        if len(x_vals) == 0 or x_vals[-1] != x_val:
            x_vals.append(x_val)

        col = 2
        for vi in range(len(var_names)):
            if col < len(parts):
                try:
                    y_val = float(parts[col].strip())
                except ValueError:
                    y_val = 0.0
                y_vals_by_var[vi].append(y_val)
            col += 1

    xUnit = ""
    yUnit = ""

    for vi, (name, vtype) in enumerate(zip(var_names, var_types)):
        kind = "V" if vtype.upper() in ("V", "VOLTAGE") else "I" if vtype.upper() in ("I", "CURRENT") else ""
        y_vals = y_vals_by_var[vi]

        waveforms.append({
            "name": name,
            "kind": kind,
            "xUnit": xUnit,
            "yUnit": yUnit,
            "x": x_vals[:len(y_vals)],
            "y": y_vals,
        })

    return waveforms
