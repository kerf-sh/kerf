"""OpenLane/OpenROAD RTL-to-GDS-II flow orchestrator.

Subprocess wrapper that drives the full OpenLane flow:

    synthesis (Yosys)
    → floorplan (OpenROAD)
    → placement (OpenROAD)
    → CTS — clock tree synthesis (OpenROAD)
    → routing (OpenROAD)
    → GDS-out (KLayout / Magic)

This module only *orchestrates*; it does not implement the EDA steps itself.
It delegates to the ``openlane`` CLI (OpenLane 2) or the legacy
``flow.tcl`` script (OpenLane 1) found on PATH / via ``OPENLANE_ROOT``.

Pending-sentinel pattern
------------------------
If neither ``openlane`` nor ``flow.tcl`` is found on PATH the function
returns a :class:`FlowResult` with ``status="pending"`` rather than raising,
so callers can display a "tool not installed" banner instead of crashing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from kerf_silicon.openlane.config import build_config, write_config


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FlowResult:
    """Outcome of a single OpenLane flow run.

    Attributes:
        status:   ``"success"`` | ``"error"`` | ``"pending"``
        gds_path: Absolute path to the generated GDS-II file, or ``""`` when
                  the flow did not reach GDS-out.
        log_path: Absolute path to the primary log file, or ``""`` when no
                  subprocess was launched.
        returncode: Subprocess exit code, or ``None`` when status is pending.
        warnings: Non-fatal messages collected during the run.
    """

    status: str
    gds_path: str = ""
    log_path: str = ""
    returncode: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_openlane_cmd() -> Optional[List[str]]:
    """Return the command-list for running OpenLane, or None if absent.

    Search order:
    1. ``openlane`` on PATH  (OpenLane 2 CLI)
    2. ``$OPENLANE_ROOT/flow.tcl`` driven by ``tclsh``  (OpenLane 1 legacy)
    """
    if shutil.which("openlane"):
        return ["openlane"]

    openlane_root = os.environ.get("OPENLANE_ROOT", "")
    if openlane_root:
        tcl = Path(openlane_root) / "flow.tcl"
        if tcl.is_file():
            tclsh = shutil.which("tclsh") or "tclsh"
            return [tclsh, str(tcl)]

    return None


def _locate_gds(run_dir: Path, design_name: str) -> str:
    """Best-effort search for the GDS-II file produced by OpenLane.

    OpenLane 2 writes to ``<run_dir>/final/gds/<design>.gds``.
    OpenLane 1 legacy writes to ``<run_dir>/results/final/gds/<design>.gds``.
    """
    candidates = [
        run_dir / "final" / "gds" / f"{design_name}.gds",
        run_dir / "results" / "final" / "gds" / f"{design_name}.gds",
        run_dir / "final" / "gds" / f"{design_name}.gds.gz",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Broader glob fallback
    matches = list(run_dir.rglob("*.gds"))
    if matches:
        return str(matches[0])
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: Flow steps executed in order — listed for documentation; the subprocess
#: handles them internally.
FLOW_STEPS = [
    "synthesis",       # Yosys
    "floorplan",       # OpenROAD
    "placement",       # OpenROAD
    "cts",             # clock tree synthesis — OpenROAD
    "routing",         # OpenROAD
    "gds_out",         # KLayout / Magic
]


def run_flow(
    design_name: str,
    verilog_files: List[str],
    *,
    pdk: str = "sky130A",
    clock_period: float = 10.0,
    clock_port: str = "clk",
    die_area: tuple = (0, 0, 100, 100),
    run_dir: Optional[str] = None,
    extra_config: Optional[dict] = None,
    timeout: int = 3600,
) -> FlowResult:
    """Run the full OpenLane RTL-to-GDS-II flow for a design.

    Args:
        design_name:   Top-level module name.
        verilog_files: List of Verilog source paths.
        pdk:           PDK identifier passed to OpenLane (default ``"sky130A"``).
        clock_period:  Target clock period in nanoseconds.
        clock_port:    Primary clock port name.
        die_area:      Die bounding box ``(x0, y0, x1, y1)`` in µm.
        run_dir:       Directory for flow artifacts.  A temporary directory is
                       created when ``None``.
        extra_config:  Additional keys merged into ``config.json``.
        timeout:       Subprocess timeout in seconds (default 3600 s / 1 h).

    Returns:
        :class:`FlowResult`.  ``status="pending"`` when ``openlane`` / ``flow.tcl``
        is not found on PATH; ``status="success"`` on zero exit code;
        ``status="error"`` on non-zero exit code or subprocess failure.
    """
    cmd = _find_openlane_cmd()
    if cmd is None:
        return FlowResult(
            status="pending",
            warnings=["openlane not found on PATH — install OpenLane to run the flow."],
        )

    # Build run directory
    _tmp_dir = None
    if run_dir is None:
        _tmp_dir = tempfile.mkdtemp(prefix=f"kerf_openlane_{design_name}_")
        run_dir = _tmp_dir

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    # Write config.json
    cfg = build_config(
        design_name,
        verilog_files,
        clock_port=clock_port,
        clock_period=clock_period,
        pdk=pdk,
        die_area=die_area,
    )
    if extra_config:
        cfg.update(extra_config)

    config_path = write_config(cfg, run_path / "config.json")
    log_path = str(run_path / "flow.log")

    # Assemble command
    # OpenLane 2: openlane --run-dir <dir> <config>
    # OpenLane 1: tclsh flow.tcl -design <dir> -tag run1 -config config.json
    if cmd[0] == "openlane":
        full_cmd = cmd + ["--run-dir", str(run_path), str(config_path)]
    else:
        # Legacy flow.tcl invocation
        full_cmd = cmd + [
            "-design", str(run_path),
            "-tag", "kerf_run",
            "-config", str(config_path),
            "-overwrite",
        ]

    warnings: List[str] = []

    try:
        with open(log_path, "w") as log_fh:
            result = subprocess.run(
                full_cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
    except FileNotFoundError as exc:
        return FlowResult(
            status="pending",
            log_path=log_path,
            warnings=[f"openlane executable not found: {exc}"],
        )
    except subprocess.TimeoutExpired:
        return FlowResult(
            status="error",
            log_path=log_path,
            returncode=-1,
            warnings=[f"Flow timed out after {timeout}s"],
        )
    except Exception as exc:  # noqa: BLE001
        return FlowResult(
            status="error",
            log_path=log_path,
            returncode=-1,
            warnings=[f"Unexpected error launching flow: {exc}"],
        )

    gds_path = _locate_gds(run_path, design_name)
    status = "success" if result.returncode == 0 else "error"

    if result.returncode != 0:
        warnings.append(f"Flow exited with code {result.returncode} — check {log_path}")

    return FlowResult(
        status=status,
        gds_path=gds_path,
        log_path=log_path,
        returncode=result.returncode,
        warnings=warnings,
    )
