"""
OpenFOAM bridge — case execution and result parsing.

High-level workflow
-------------------
1. Call :func:`build_case` (from :mod:`openfoam_case_template`) to write a
   complete case directory tree.
2. Optionally run ``blockMesh`` to generate the mesh.
3. Call :func:`run_solver` to shell out to ``simpleFoam`` or ``pimpleFoam``.
4. Call :func:`parse_postprocessing` to extract scalar timeseries from the
   ``postProcessing/`` directory that OpenFOAM writes.

Graceful degrade
----------------
When the requested binary (e.g. ``simpleFoam``) is not on PATH the functions
return a result dict with ``status == "pending"`` and a human-readable warning
— the same sentinel pattern used by ``calculix_utils.py`` and
``fenicsx_utils.py``.

Hagen-Poiseuille analytic oracle
---------------------------------
``pipe_friction_factor_laminar(Re)`` returns the Darcy-Weisbach friction
factor for laminar pipe flow:

    f = 64 / Re                        (Moody chart laminar branch)

This is the independent pure-Python reference used by the test suite to
validate that any OpenFOAM run producing a pressure drop is consistent with
the analytic solution to within 1 %.

Reference: White F.M., Fluid Mechanics, 8th ed., §6.4;
           Munson, Okiishi, Huebsch, Rothmayer, Fundamentals of Fluid
           Mechanics, 7th ed., §8.3.

Scope / limits
--------------
- Parsing covers the ``postProcessing/<function-name>/<time>/`` layout that
  OpenFOAM's ``forces`` and ``fieldAverage`` function objects produce.
- Only ASCII result files are supported (``writeFormat ascii;``).
- Errors in subprocess execution are surfaced via the ``errors`` list in the
  returned dict rather than raised exceptions.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Binary availability (lazy-cached)
# ---------------------------------------------------------------------------

_BINARY_CACHE: dict[str, bool] = {}


def _binary_available(name: str) -> bool:
    if name not in _BINARY_CACHE:
        _BINARY_CACHE[name] = shutil.which(name) is not None
    return _BINARY_CACHE[name]


ENGINE_PENDING_WARNING = (
    "Engine pending — OpenFOAM ({binary}) not installed or not in PATH."
)


# ---------------------------------------------------------------------------
# Analytic oracle — Hagen-Poiseuille (Darcy-Weisbach laminar)
# ---------------------------------------------------------------------------

def pipe_friction_factor_laminar(Re: float) -> float:
    """
    Darcy-Weisbach friction factor for laminar pipe flow.

        f = 64 / Re

    Valid for Re < 2300 (laminar regime).

    Parameters
    ----------
    Re : float
        Reynolds number (must be > 0).

    Returns
    -------
    float
        Darcy-Weisbach friction factor.

    Raises
    ------
    ValueError
        If Re <= 0.

    Reference
    ---------
    White F.M., Fluid Mechanics, 8th ed., §6.4, eq. (6.13).
    """
    if Re <= 0:
        raise ValueError(f"Reynolds number must be positive; got {Re}")
    return 64.0 / Re


def pipe_pressure_drop_hagen_poiseuille(
    u_mean: float,
    length: float,
    diameter: float,
    nu: float,
    rho: float = 1.0,
) -> dict[str, float]:
    """
    Compute Hagen-Poiseuille pressure drop for laminar pipe flow.

        ΔP = f * (L/D) * (ρ U²) / 2   with  f = 64/Re,  Re = U*D/ν

    Parameters
    ----------
    u_mean : float
        Mean cross-section velocity (m/s).
    length : float
        Pipe length (m).
    diameter : float
        Pipe (hydraulic) diameter (m).
    nu : float
        Kinematic viscosity (m²/s).
    rho : float
        Fluid density (kg/m³), default 1.

    Returns
    -------
    dict with keys:
        Re              Reynolds number
        f               Darcy friction factor (64/Re)
        delta_p         pressure drop (Pa)
        dp_per_length   pressure gradient (Pa/m)

    Reference
    ---------
    White F.M., Fluid Mechanics, 8th ed., §8.2, eq. (8.12).
    """
    Re = u_mean * diameter / nu
    f = pipe_friction_factor_laminar(Re)
    dynamic_pressure = 0.5 * rho * u_mean ** 2
    delta_p = f * (length / diameter) * dynamic_pressure
    return {
        "Re": Re,
        "f": f,
        "delta_p": delta_p,
        "dp_per_length": delta_p / length,
    }


# ---------------------------------------------------------------------------
# blockMesh runner
# ---------------------------------------------------------------------------

def run_blockmesh(case_dir: str | Path, timeout: int = 120) -> dict[str, Any]:
    """
    Run ``blockMesh`` in *case_dir*.

    Returns
    -------
    dict with keys:
        status      "ok" | "pending" | "error"
        warnings    list[str]
        errors      list[str]
        stdout      str  (raw blockMesh output)
        elapsed     float  (wall seconds)
    """
    case_dir = Path(case_dir).resolve()

    if not _binary_available("blockMesh"):
        return {
            "status": "pending",
            "warnings": [ENGINE_PENDING_WARNING.format(binary="blockMesh")],
            "errors": [],
            "stdout": "",
            "elapsed": 0.0,
        }

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            ["blockMesh", "-case", str(case_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [],
            "errors": [f"blockMesh timed out after {timeout}s"],
            "stdout": "",
            "elapsed": time.monotonic() - t0,
        }
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        return {
            "status": "error",
            "warnings": [],
            "errors": [
                f"blockMesh exited with code {result.returncode}",
                result.stderr.strip(),
            ],
            "stdout": result.stdout,
            "elapsed": elapsed,
        }

    return {
        "status": "ok",
        "warnings": [],
        "errors": [],
        "stdout": result.stdout,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# Solver runner
# ---------------------------------------------------------------------------

def run_solver(
    case_dir: str | Path,
    solver: str = "simpleFoam",
    *,
    timeout: int = 600,
    log_file: str | None = None,
) -> dict[str, Any]:
    """
    Run *solver* on *case_dir*.

    The solver is invoked as::

        <solver> -case <case_dir>

    stdout is captured and optionally written to *log_file* inside *case_dir*.

    Returns
    -------
    dict with keys:
        status      "ok" | "pending" | "error"
        warnings    list[str]
        errors      list[str]
        stdout      str
        returncode  int | None
        elapsed     float  (wall seconds)
    """
    case_dir = Path(case_dir).resolve()

    if not _binary_available(solver):
        return {
            "status": "pending",
            "warnings": [ENGINE_PENDING_WARNING.format(binary=solver)],
            "errors": [],
            "stdout": "",
            "returncode": None,
            "elapsed": 0.0,
        }

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            [solver, "-case", str(case_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "warnings": [],
            "errors": [f"{solver} timed out after {timeout}s"],
            "stdout": "",
            "returncode": None,
            "elapsed": time.monotonic() - t0,
        }
    elapsed = time.monotonic() - t0

    if log_file is not None:
        (case_dir / log_file).write_text(result.stdout)

    if result.returncode != 0:
        return {
            "status": "error",
            "warnings": [],
            "errors": [
                f"{solver} exited with code {result.returncode}",
                result.stderr.strip(),
            ],
            "stdout": result.stdout,
            "returncode": result.returncode,
            "elapsed": elapsed,
        }

    return {
        "status": "ok",
        "warnings": [],
        "errors": [],
        "stdout": result.stdout,
        "returncode": result.returncode,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# postProcessing/ parser
# ---------------------------------------------------------------------------

# Match lines like:  0.001   (1.23e-4 -2.3e-5 0)   # forces
_VECTOR_RE = re.compile(
    r"^\s*(\S+)"                  # time/iteration
    r"\s+\("                      # opening paren
    r"\s*(\S+)\s+(\S+)\s+(\S+)"  # x y z
    r"\s*\)"                      # closing paren
)
# Match lines like:   0.001   1.23e-4             # scalar field
_SCALAR_RE = re.compile(r"^\s*(\S+)\s+(\S+)\s*$")


def _safe_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, OverflowError):
        return None


def parse_forces_dat(dat_path: str | Path) -> list[dict[str, Any]]:
    """
    Parse an OpenFOAM ``postProcessing/forces/<time>/force.dat`` file.

    Each non-comment line has the form::

        <time>  (<Fx> <Fy> <Fz>)  (<Mx> <My> <Mz>)

    Returns a list of dicts:
        time, Fx, Fy, Fz, Mx, My, Mz
    """
    records: list[dict[str, Any]] = []
    dat_path = Path(dat_path)
    if not dat_path.exists():
        return records

    for raw_line in dat_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Two vector groups: forces then moments
        # Format: time  (Fx Fy Fz)  (Mx My Mz)
        m = re.match(
            r"^\s*(\S+)"
            r"\s+\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)"
            r"\s+\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)",
            raw_line,
        )
        if m:
            t, fx, fy, fz, mx, my, mz = m.groups()
            row: dict[str, Any] = {
                "time": _safe_float(t),
                "Fx": _safe_float(fx),
                "Fy": _safe_float(fy),
                "Fz": _safe_float(fz),
                "Mx": _safe_float(mx),
                "My": _safe_float(my),
                "Mz": _safe_float(mz),
            }
            records.append(row)
    return records


def parse_scalar_dat(dat_path: str | Path) -> list[dict[str, Any]]:
    """
    Parse a two-column (time, value) postProcessing data file.

    Returns a list of dicts with keys ``time`` and ``value``.
    """
    records: list[dict[str, Any]] = []
    dat_path = Path(dat_path)
    if not dat_path.exists():
        return records

    for raw_line in dat_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _SCALAR_RE.match(line)
        if m:
            t_str, v_str = m.groups()
            records.append({
                "time": _safe_float(t_str),
                "value": _safe_float(v_str),
            })
    return records


def parse_postprocessing(case_dir: str | Path) -> dict[str, Any]:
    """
    Walk ``<case_dir>/postProcessing/`` and collect all result files.

    Returns
    -------
    dict with keys:
        status          "ok" | "empty"
        function_names  list[str]   — names of function-object subdirectories found
        data            dict        — keyed by "<function>/<time>/<filename>"
                                      value is list of parsed row dicts

    Each row dict has at minimum a ``time`` key; forces files add
    Fx/Fy/Fz/Mx/My/Mz; scalar files add ``value``.
    """
    case_dir = Path(case_dir).resolve()
    pp_dir = case_dir / "postProcessing"

    if not pp_dir.is_dir():
        return {
            "status": "empty",
            "function_names": [],
            "data": {},
        }

    function_names: list[str] = []
    data: dict[str, Any] = {}

    for fn_dir in sorted(pp_dir.iterdir()):
        if not fn_dir.is_dir():
            continue
        function_names.append(fn_dir.name)

        for time_dir in sorted(fn_dir.iterdir()):
            if not time_dir.is_dir():
                continue

            for dat_file in sorted(time_dir.iterdir()):
                if not dat_file.is_file():
                    continue
                key = f"{fn_dir.name}/{time_dir.name}/{dat_file.name}"

                name_lower = dat_file.name.lower()
                if "force" in name_lower:
                    data[key] = parse_forces_dat(dat_file)
                else:
                    data[key] = parse_scalar_dat(dat_file)

    return {
        "status": "ok" if data else "empty",
        "function_names": function_names,
        "data": data,
    }


# ---------------------------------------------------------------------------
# High-level convenience
# ---------------------------------------------------------------------------

def run_case(
    case_dir: str | Path,
    solver: str = "simpleFoam",
    *,
    run_blockmesh_first: bool = True,
    solver_timeout: int = 600,
    log_file: str | None = "log.simpleFoam",
) -> dict[str, Any]:
    """
    Run a complete OpenFOAM case: optionally blockMesh, then the solver,
    then parse postProcessing/.

    Returns
    -------
    dict with keys:
        status          "ok" | "pending" | "error"
        blockmesh       dict  (result of run_blockmesh, or None)
        solver          dict  (result of run_solver)
        postprocessing  dict  (result of parse_postprocessing, or None)
        warnings        list[str]
        errors          list[str]
    """
    case_dir = Path(case_dir).resolve()
    warnings: list[str] = []
    errors: list[str] = []

    bm_result: dict[str, Any] | None = None
    if run_blockmesh_first:
        bm_result = run_blockmesh(case_dir)
        if bm_result["status"] == "pending":
            return {
                "status": "pending",
                "blockmesh": bm_result,
                "solver": None,
                "postprocessing": None,
                "warnings": bm_result["warnings"],
                "errors": [],
            }
        if bm_result["status"] == "error":
            return {
                "status": "error",
                "blockmesh": bm_result,
                "solver": None,
                "postprocessing": None,
                "warnings": [],
                "errors": bm_result["errors"],
            }

    solver_result = run_solver(case_dir, solver, timeout=solver_timeout,
                               log_file=log_file)
    warnings.extend(solver_result.get("warnings", []))
    errors.extend(solver_result.get("errors", []))

    if solver_result["status"] == "pending":
        return {
            "status": "pending",
            "blockmesh": bm_result,
            "solver": solver_result,
            "postprocessing": None,
            "warnings": warnings,
            "errors": errors,
        }

    if solver_result["status"] == "error":
        return {
            "status": "error",
            "blockmesh": bm_result,
            "solver": solver_result,
            "postprocessing": None,
            "warnings": warnings,
            "errors": errors,
        }

    pp_result = parse_postprocessing(case_dir)

    return {
        "status": "ok",
        "blockmesh": bm_result,
        "solver": solver_result,
        "postprocessing": pp_result,
        "warnings": warnings,
        "errors": errors,
    }
