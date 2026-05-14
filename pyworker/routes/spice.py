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
    },
    "probes"?: string[],  -- e.g. ["V(1)", "V(2)", "I(V1)"]
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
    probes = req.get("probes", [])

    if not netlist.strip():
        raise HTTPException(status_code=400, detail="netlist is required")

    if probes:
        netlist = inject_print_statements(netlist, probes)

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


def inject_print_statement(netlist: str, probe: str) -> str:
    analysis_type = "TRAN"
    match = re.search(r"^\.([A-Z]+)", netlist, re.MULTILINE | re.IGNORECASE)
    if match:
        analysis_type = match.group(1).upper()
    print_line = f".PRINT {analysis_type} {probe}\n"
    netlist = re.sub(r"(\.PRINT\s+[A-Z]+\s+[^\n]+\n?)$", print_line + r"\1", netlist, flags=re.MULTILINE)
    if print_line.strip() not in netlist:
        netlist = netlist + "\n" + print_line
    return netlist


def inject_print_statements(netlist: str, probes: list) -> str:
    for probe in probes:
        netlist = inject_print_statement(netlist, probe)
    return netlist


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
    except FileNotFoundError:
        return {"waveforms": [], "warnings": [], "errors": ["ngspice not installed. Install with: brew install ngspice"]}
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

    header = {}
    idx = 0
    for line in lines:
        idx += 1
        line = line.strip()
        if not line:
            continue
        if line == "Variables:":
            break
        if ":" in line:
            key, val = line.split(":", 1)
            header[key.strip()] = val.strip()

    if idx >= len(lines) or lines[idx - 1].strip() != "Variables:":
        return waveforms

    idx += 1
    num_vars = int(header.get("No. Variables", 0))
    var_names = []
    var_types = []

    while idx < len(lines) and len(var_names) < num_vars:
        line = lines[idx].strip()
        idx += 1
        if not line or line == "Values:":
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            var_names.append(parts[1].strip())
            var_types.append(parts[2].strip())

    if idx >= len(lines) or lines[idx - 1].strip() != "Values:":
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
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            point_idx = int(parts[0].strip())
            x_val = float(parts[1].strip())
        except ValueError:
            continue

        if not x_vals or x_vals[-1] != x_val:
            x_vals.append(x_val)

        for vi in range(len(var_names)):
            val_idx = vi + 2
            if val_idx < len(parts):
                try:
                    y_val = float(parts[val_idx].strip())
                except ValueError:
                    y_val = 0.0
                y_vals_by_var[vi].append(y_val)

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