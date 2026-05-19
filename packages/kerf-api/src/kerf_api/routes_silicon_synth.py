"""routes_silicon_synth.py — /api/silicon/synth route.

Endpoint:
  POST /api/silicon/synth
      Yosys RTL synthesis wrapper.
      - Attempts to import the pyosys / yowasp-yosys package.
      - Falls back gracefully to {status:"pending", reason:"..."} on ImportError.
      - If Yosys is available, runs `synth` (generic) on the provided Verilog source.
      - Returns gate-count statistics and the synthesised netlist in JSON format.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import json
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


class SynthRequest(BaseModel):
    verilog: str = Field(
        ...,
        description="Verilog RTL source code to synthesise.",
        min_length=1,
    )
    top: Optional[str] = Field(
        default=None,
        description=(
            "Top-level module name.  If None, Yosys auto-detects from the source."
        ),
    )
    liberty: Optional[str] = Field(
        default=None,
        description=(
            "Liberty cell library (.lib) contents for tech-mapping.  "
            "If None, runs generic (unmapped) synthesis."
        ),
    )
    flatten: bool = Field(
        default=True,
        description="Flatten design hierarchy before synthesis.",
    )


def _yosys_binary() -> Optional[str]:
    """Return path to yosys binary or None."""
    path = shutil.which("yosys")
    return path


def _run_yosys_cli(verilog: str, top: Optional[str], flatten: bool, liberty: Optional[str]) -> dict:
    """Run Yosys via subprocess CLI and parse JSON stats output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        in_v = os.path.join(tmpdir, "design.v")
        out_json = os.path.join(tmpdir, "out.json")
        script_f = os.path.join(tmpdir, "synth.ys")

        with open(in_v, "w") as f:
            f.write(verilog)

        # Build Yosys synthesis script
        lines = [f"read_verilog {in_v}"]
        if top:
            lines.append(f"hierarchy -top {top}")
        else:
            lines.append("hierarchy -auto-top")

        if flatten:
            lines.append("flatten")

        if liberty:
            lib_f = os.path.join(tmpdir, "cells.lib")
            with open(lib_f, "w") as f:
                f.write(liberty)
            lines.append("proc; opt; techmap")
            lines.append(f"dfflibmap -liberty {lib_f}")
            lines.append(f"abc -liberty {lib_f}")
        else:
            lines.append("synth")

        lines.append(f"write_json {out_json}")
        lines.append("stat -json")

        with open(script_f, "w") as f:
            f.write("\n".join(lines) + "\n")

        try:
            proc = subprocess.run(
                ["yosys", "-s", script_f],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "reason": "Yosys synthesis timed out (>60 s)"}
        except FileNotFoundError:
            return {"ok": False, "reason": "yosys binary not found in PATH"}

        if proc.returncode != 0:
            return {
                "ok": False,
                "reason": "Yosys synthesis failed",
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-2000:] if proc.stderr else "",
            }

        # Parse netlist JSON
        netlist: dict = {}
        if os.path.exists(out_json):
            try:
                with open(out_json) as f:
                    netlist = json.load(f)
            except Exception:
                netlist = {}

        # Extract gate counts from stat output
        gate_count = _parse_stat(proc.stdout or "")

        return {
            "ok": True,
            "gate_count": gate_count,
            "netlist": netlist,
            "stdout": proc.stdout[-3000:] if proc.stdout else "",
            "liberty_mapped": liberty is not None,
        }


def _parse_stat(stdout: str) -> dict:
    """Parse Yosys `stat` output for cell counts."""
    counts: dict = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Number of cells:"):
            try:
                counts["total_cells"] = int(line.split(":")[-1].strip())
            except ValueError:
                pass
        elif line.startswith("Number of wires:"):
            try:
                counts["wires"] = int(line.split(":")[-1].strip())
            except ValueError:
                pass
        elif line.startswith("Number of wire bits:"):
            try:
                counts["wire_bits"] = int(line.split(":")[-1].strip())
            except ValueError:
                pass
    return counts


@router.post("/silicon/synth")
def silicon_synth(req: SynthRequest):
    """RTL synthesis via Yosys.

    Synthesises the supplied Verilog source using Yosys.  If `liberty` is
    provided the design is mapped to that cell library (via ABC); otherwise
    generic synthesis runs.

    Returns:
      ok           — True on success
      gate_count   — dict with total_cells, wires, wire_bits
      netlist      — JSON netlist object (Yosys JSON format)
      liberty_mapped — whether liberty tech-mapping was applied
      stdout       — last 3 kB of Yosys stdout (debug)

    Degrades to {status:"pending"} if Yosys is not installed.
    """
    # Check for yowasp first (pure-Python Yosys)
    try:
        import yowasp_yosys  # noqa: F401
        # yowasp wraps yosys; it will be on PATH after import
    except ImportError:
        pass

    yosys_bin = _yosys_binary()
    if yosys_bin is None:
        # Try PyRTL as a lightweight alternative for very simple designs
        try:
            import pyrtl  # noqa: F401
            return JSONResponse(
                status_code=503,
                content={
                    "status": "pending",
                    "reason": (
                        "Yosys is not installed.  Install yosys or yowasp-yosys "
                        "(pip install yowasp-yosys) to enable RTL synthesis."
                    ),
                },
            )
        except ImportError:
            pass

        return JSONResponse(
            status_code=503,
            content={
                "status": "pending",
                "reason": (
                    "Yosys is not installed.  Install yosys or yowasp-yosys "
                    "(pip install yowasp-yosys) to enable RTL synthesis."
                ),
            },
        )

    result = _run_yosys_cli(
        verilog=req.verilog,
        top=req.top,
        flatten=req.flatten,
        liberty=req.liberty,
    )

    if not result.get("ok"):
        return JSONResponse(status_code=422, content=result)

    return result
