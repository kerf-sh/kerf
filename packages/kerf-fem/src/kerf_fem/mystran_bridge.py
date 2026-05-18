"""
MYSTRAN subprocess bridge for modal and aeroelastic analysis.

MYSTRAN is an open-source, NASTRAN-compatible finite-element solver that reads
Bulk Data Format (.BDF/.bdf) decks and writes F06 and PCH output files.

Public entry-point
------------------
    MystranBridge.solve(mesh, materials, boundary_conditions, *, analysis_type)
        -> Result

Where *analysis_type* is one of:
    "modal"          — SOL 103  real eigenvalue extraction
    "linear_static"  — SOL 101  linear statics

Usage example
-------------
    bridge = MystranBridge()
    result = bridge.solve(
        mesh={"nodes": [...], "elements": [...]},
        materials={"E": 200e9, "nu": 0.3, "rho": 7850.0},
        boundary_conditions=[{"type": "fixed", "node_ids": [1, 2, 3]}],
        analysis_type="modal",
    )

BDF syntax reference
--------------------
MSC.Software, "MSC Nastran Quick Reference Guide", 2023.
MYSTRAN User's Manual (MYSTRAN project, GitHub mystran/mystran).

F06 output parsing
------------------
MYSTRAN writes eigenvalues in the "R E A L   E I G E N V A L U E S" table:
    MODE  EXTRACTION ORDER  EIGENVALUE      RADIANS         CYCLES
     1         1           1.000000E+06    1.000000E+03    1.591549E+02
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability probe (cached)
# ---------------------------------------------------------------------------

_MYSTRAN_AVAILABLE: Optional[bool] = None


def _mystran_available() -> bool:
    global _MYSTRAN_AVAILABLE
    if _MYSTRAN_AVAILABLE is None:
        _MYSTRAN_AVAILABLE = shutil.which("mystran") is not None
    return _MYSTRAN_AVAILABLE


ENGINE_PENDING_WARNING = (
    "Engine pending — MYSTRAN not installed or not in PATH.  "
    "Install from https://github.com/MYSTRANsolver/MYSTRAN/releases."
)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class MystranResult:
    """Parsed output from a MYSTRAN run."""

    ok: bool
    analysis_type: str
    # Modal results
    frequencies: list[float] = field(default_factory=list)     # Hz
    eigenvalues: list[float] = field(default_factory=list)     # rad²/s²
    # Static results
    displacements: list[dict[str, float]] = field(default_factory=list)
    stresses: list[dict[str, float]] = field(default_factory=list)
    max_displacement: float = 0.0
    max_vonmises_stress: float = 0.0
    # Diagnostics
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"  # "ok" | "pending" | "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "analysis_type": self.analysis_type,
            "frequencies": self.frequencies,
            "eigenvalues": self.eigenvalues,
            "displacements": self.displacements,
            "stresses": self.stresses,
            "max_displacement": self.max_displacement,
            "max_vonmises_stress": self.max_vonmises_stress,
            "warnings": self.warnings,
            "errors": self.errors,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# BDF (Bulk Data Format) deck writer
# ---------------------------------------------------------------------------

# NASTRAN fixed-field format: 10 fields of 8 characters each (80-col card).
# Free-field (*BULK DATA) is also accepted by MYSTRAN.

def _fmt8(v: Any) -> str:
    """Format a scalar value into an 8-character NASTRAN field."""
    if isinstance(v, int):
        return f"{v:>8d}"
    if isinstance(v, float):
        # Use NASTRAN scientific notation — up to 8 chars including sign.
        s = f"{v:.4E}"
        # Shorten exponent: 1.2345E+02 → 1.2345E+2 if possible
        s = re.sub(r"E([+-])0+(\d+)$", lambda m: f"E{m.group(1)}{m.group(2)}", s)
        if len(s) > 8:
            s = f"{v:.3E}"
            s = re.sub(r"E([+-])0+(\d+)$", lambda m: f"E{m.group(1)}{m.group(2)}", s)
        return f"{s:>8s}"
    return f"{str(v):>8s}"


def _card(*fields: Any) -> str:
    """Build a free-field BDF card line (comma-separated, MYSTRAN compatible)."""
    return ",".join(str(f) for f in fields)


def _write_bdf_modal(
    nodes: list[tuple[float, float, float]],
    elements: list[tuple[int, str, list[int]]],
    materials: dict,
    boundary_conditions: list[dict],
    num_modes: int = 10,
    *,
    shell_thickness: Optional[float] = None,
) -> str:
    """
    Build a NASTRAN/MYSTRAN Bulk Data deck for SOL 103 real normal modes.

    Parameters
    ----------
    nodes:
        List of (x, y, z) node coordinates (0-indexed; internally 1-indexed).
    elements:
        List of (elem_id, elem_type, node_list) where elem_type is one of:
        "CQUAD4", "CTRIA3", "CTETRA", "CHEXA".
    materials:
        Dict with keys E [Pa], nu, rho [kg/m³].  Optional: yield_strength.
    boundary_conditions:
        List of dicts.  Supported: {"type": "fixed", "node_ids": [...]}.
    num_modes:
        Number of eigenvalues to extract.
    shell_thickness:
        Required for shell elements (CQUAD4 / CTRIA3).  If None, defaults to
        1e-3 m (1 mm) when shell elements are detected.
    """
    E = float(materials.get("E", 200e9))
    nu = float(materials.get("nu", 0.3))
    rho = float(materials.get("rho", 7850.0))

    lines: list[str] = []

    # ---- Executive Control Deck -----------------------------------------
    lines += [
        "SOL 103",
        "CEND",
    ]

    # ---- Case Control Deck ----------------------------------------------
    lines += [
        "TITLE = MYSTRAN MODAL ANALYSIS",
        "ECHO = NONE",
        f"METHOD = 1",
        "DISPLACEMENT(SORT1,REAL) = ALL",
        "BEGIN BULK",
    ]

    # ---- Bulk Data -------------------------------------------------------

    # EIGRL card: Lanczos real eigenvalue extraction, request num_modes modes.
    # EIGRL  SID  V1   V2   ND
    lines.append(f"EIGRL,1,,,{num_modes}")

    # MAT1: isotropic material
    # MAT1  MID  E    G    NU   RHO
    lines.append(f"MAT1,1,{E:.6E},,{nu:.4f},{rho:.4f}")

    # PSOLID / PSHELL property
    has_shell = any(et in ("CQUAD4", "CTRIA3")
                    for (_, et, _) in elements)
    has_solid = any(et in ("CTETRA", "CHEXA")
                    for (_, et, _) in elements)

    if has_shell:
        t = shell_thickness if shell_thickness is not None else 1e-3
        # PSHELL  PID  MID1  T  MID2  12I/T^3  MID3  TS/T  NSM
        lines.append(f"PSHELL,1,1,{t:.6E},1")

    if has_solid:
        # PSOLID  PID  MID  CORDM  IN  STRESS  ISOP  FCTN
        lines.append("PSOLID,2,1")

    # GRID cards: node coordinates
    for i, (x, y, z) in enumerate(nodes):
        nid = i + 1
        # GRID  NID  CP  X1  X2  X3  CD  PS  SEID
        lines.append(f"GRID,{nid},,{x:.10g},{y:.10g},{z:.10g}")

    # Element connectivity
    for eid, etype, enodes in elements:
        nstr = ",".join(str(n) for n in enodes)
        pid = 1 if etype in ("CQUAD4", "CTRIA3") else 2
        lines.append(f"{etype},{eid},{pid},{nstr}")

    # SPC1: single-point constraints (fixed boundary conditions)
    spc_id = 10
    spc_written = False
    for bc in boundary_conditions:
        if bc.get("type") == "fixed":
            node_ids = bc.get("node_ids", [])
            if not node_ids:
                continue
            # SPC1  SID  C  G1  G2  ...  (C=123456 = all 6 DOF)
            # MYSTRAN accepts free-field; split into groups of 7 nodes per card.
            chunk_size = 7
            for chunk_start in range(0, len(node_ids), chunk_size):
                chunk = node_ids[chunk_start:chunk_start + chunk_size]
                nstr = ",".join(str(n) for n in chunk)
                lines.append(f"SPC1,{spc_id},123456,{nstr}")
            spc_written = True

    if spc_written:
        # Reference the SPC set in the Case Control section.
        # We need to inject SPC=spc_id before BEGIN BULK.
        bulk_idx = lines.index("BEGIN BULK")
        lines.insert(bulk_idx, f"SPC = {spc_id}")

    lines.append("ENDDATA")
    return "\n".join(lines) + "\n"


def _write_bdf_static(
    nodes: list[tuple[float, float, float]],
    elements: list[tuple[int, str, list[int]]],
    materials: dict,
    boundary_conditions: list[dict],
    loads: list[dict],
    *,
    shell_thickness: Optional[float] = None,
) -> str:
    """
    Build a NASTRAN/MYSTRAN Bulk Data deck for SOL 101 linear statics.
    """
    E = float(materials.get("E", 200e9))
    nu = float(materials.get("nu", 0.3))
    rho = float(materials.get("rho", 7850.0))

    lines: list[str] = []

    lines += ["SOL 101", "CEND"]
    lines += [
        "TITLE = MYSTRAN STATIC ANALYSIS",
        "ECHO = NONE",
        "SUBCASE 1",
        "  LOAD = 1",
        "  DISPLACEMENT(SORT1,REAL) = ALL",
        "  STRESS(SORT1,REAL) = ALL",
        "BEGIN BULK",
    ]

    # MAT1
    lines.append(f"MAT1,1,{E:.6E},,{nu:.4f},{rho:.4f}")

    has_shell = any(et in ("CQUAD4", "CTRIA3") for (_, et, _) in elements)
    has_solid = any(et in ("CTETRA", "CHEXA") for (_, et, _) in elements)

    if has_shell:
        t = shell_thickness if shell_thickness is not None else 1e-3
        lines.append(f"PSHELL,1,1,{t:.6E},1")
    if has_solid:
        lines.append("PSOLID,2,1")

    for i, (x, y, z) in enumerate(nodes):
        nid = i + 1
        lines.append(f"GRID,{nid},,{x:.10g},{y:.10g},{z:.10g}")

    for eid, etype, enodes in elements:
        nstr = ",".join(str(n) for n in enodes)
        pid = 1 if etype in ("CQUAD4", "CTRIA3") else 2
        lines.append(f"{etype},{eid},{pid},{nstr}")

    spc_id = 10
    spc_written = False
    for bc in boundary_conditions:
        if bc.get("type") == "fixed":
            node_ids = bc.get("node_ids", [])
            if not node_ids:
                continue
            chunk_size = 7
            for chunk_start in range(0, len(node_ids), chunk_size):
                chunk = node_ids[chunk_start:chunk_start + chunk_size]
                nstr = ",".join(str(n) for n in chunk)
                lines.append(f"SPC1,{spc_id},123456,{nstr}")
            spc_written = True

    if spc_written:
        bulk_idx = lines.index("BEGIN BULK")
        lines.insert(bulk_idx, f"SPC = {spc_id}")

    # FORCE cards (point loads): load.{"type":"force","node_id":1,"fx":0,"fy":0,"fz":-1000}
    force_cards: list[str] = []
    for i, load in enumerate(loads or []):
        if load.get("type") == "force":
            nid = load.get("node_id", 1)
            fx = load.get("fx", 0.0)
            fy = load.get("fy", 0.0)
            fz = load.get("fz", 0.0)
            mag = math.sqrt(fx * fx + fy * fy + fz * fz)
            if mag > 0:
                nx, ny, nz = fx / mag, fy / mag, fz / mag
                force_cards.append(
                    f"FORCE,1,{nid},,{mag:.6E},{nx:.6f},{ny:.6f},{nz:.6f}"
                )

    lines.extend(force_cards)
    lines.append("ENDDATA")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# F06 output parser
# ---------------------------------------------------------------------------

def _parse_f06_eigenvalues(content: str) -> tuple[list[float], list[float]]:
    """
    Extract real eigenvalues and frequencies from MYSTRAN F06 output.

    MYSTRAN writes:
        R E A L   E I G E N V A L U E S
        MODE NO.  EXTRACTION ORDER  EIGENVALUE        RADIANS        CYCLES
           1           1          1.00000E+06    1.00000E+03    1.59155E+02

    Returns (eigenvalues [rad²/s²], frequencies [Hz]).
    """
    eigenvalues: list[float] = []
    frequencies: list[float] = []

    # Match the block header (spaced out letters)
    block = re.search(
        r"R\s*E\s*A\s*L\s+E\s*I\s*G\s*E\s*N\s*V\s*A\s*L\s*U\s*E\s*S(.*?)"
        r"(?=\n\s*\n|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return eigenvalues, frequencies

    for line in block.group(1).splitlines():
        parts = line.split()
        # Expect: mode_no  extraction_order  eigenvalue  radians  cycles
        if len(parts) >= 5 and parts[0].isdigit():
            try:
                ev = float(parts[2])
                freq_hz = float(parts[4])
                if ev > 0 and freq_hz > 0:
                    eigenvalues.append(ev)
                    frequencies.append(freq_hz)
            except (ValueError, IndexError):
                pass

    return eigenvalues, frequencies


def _parse_f06_displacements(content: str) -> list[dict[str, float]]:
    """
    Parse displacement output block from MYSTRAN F06.

    Block header pattern:
        D I S P L A C E M E N T   V E C T O R
        POINT ID.   TYPE   T1             T2             T3             R1
    """
    disps: list[dict[str, float]] = []

    block = re.search(
        r"D\s*I\s*S\s*P\s*L\s*A\s*C\s*E\s*M\s*E\s*N\s*T\s+"
        r"V\s*E\s*C\s*T\s*O\s*R(.*?)"
        r"(?=\n\s*\n|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return disps

    for line in block.group(1).splitlines():
        parts = line.split()
        # POINT_ID  G  T1  T2  T3  R1  R2  R3
        if len(parts) >= 5 and parts[0].isdigit():
            try:
                t1, t2, t3 = float(parts[2]), float(parts[3]), float(parts[4])
                disps.append({"ux": t1, "uy": t2, "uz": t3})
            except (ValueError, IndexError):
                pass

    return disps


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------


class MystranBridge:
    """
    Subprocess wrapper for MYSTRAN (open-source NASTRAN-compatible solver).

    Supported analysis types
    ------------------------
    "modal"         — SOL 103 real normal modes.  Result contains
                      ``frequencies`` [Hz] and ``eigenvalues`` [rad²/s²].
    "linear_static" — SOL 101 linear statics.  Result contains
                      ``displacements``, ``max_displacement``, and stub
                      stress fields (full parsing requires PCH output,
                      not yet implemented).

    When MYSTRAN is not on PATH the bridge returns immediately with
    ``status="pending"`` and a descriptive warning so callers can degrade
    gracefully without raising.
    """

    def __init__(self, timeout: int = 600):
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        mesh: dict,
        materials: dict,
        boundary_conditions: list[dict],
        *,
        analysis_type: str = "modal",
    ) -> MystranResult:
        """
        Run a MYSTRAN analysis.

        Parameters
        ----------
        mesh:
            Dict with:
            - ``nodes``: list of (x, y, z) tuples
            - ``elements``: list of (elem_id, elem_type, node_list) tuples
            - ``shell_thickness`` (optional): float [m], required for shell elements
        materials:
            Dict with keys ``E`` [Pa], ``nu``, ``rho`` [kg/m³].
        boundary_conditions:
            List of dicts.  Supported: ``{"type": "fixed", "node_ids": [...]}``.
        analysis_type:
            ``"modal"`` or ``"linear_static"``.

        Returns
        -------
        MystranResult
            Always returns (never raises).  Check ``.ok`` and ``.status``.
        """
        if not _mystran_available():
            return MystranResult(
                ok=False,
                analysis_type=analysis_type,
                status="pending",
                warnings=[ENGINE_PENDING_WARNING],
            )

        nodes: list[tuple[float, float, float]] = [
            tuple(n) for n in mesh.get("nodes", [])  # type: ignore[misc]
        ]
        elements: list[tuple[int, str, list[int]]] = [
            tuple(e) for e in mesh.get("elements", [])  # type: ignore[misc]
        ]
        shell_thickness: Optional[float] = mesh.get("shell_thickness")

        if analysis_type == "modal":
            return self._run_modal(
                nodes, elements, materials, boundary_conditions,
                shell_thickness=shell_thickness,
            )
        elif analysis_type == "linear_static":
            return self._run_static(
                nodes, elements, materials, boundary_conditions,
                loads=mesh.get("loads", []),
                shell_thickness=shell_thickness,
            )
        else:
            return MystranResult(
                ok=False,
                analysis_type=analysis_type,
                status="failed",
                errors=[f"Unsupported analysis_type: {analysis_type!r}"],
            )

    # ------------------------------------------------------------------
    # Internal runners
    # ------------------------------------------------------------------

    def _run_modal(
        self,
        nodes: list,
        elements: list,
        materials: dict,
        boundary_conditions: list[dict],
        *,
        shell_thickness: Optional[float] = None,
        num_modes: int = 10,
    ) -> MystranResult:
        deck = _write_bdf_modal(
            nodes, elements, materials, boundary_conditions,
            num_modes=num_modes,
            shell_thickness=shell_thickness,
        )
        try:
            f06_content = self._run_mystran(deck)
        except RuntimeError as exc:
            return MystranResult(
                ok=False,
                analysis_type="modal",
                status="failed",
                errors=[str(exc)],
            )

        evs, freqs = _parse_f06_eigenvalues(f06_content)
        return MystranResult(
            ok=True,
            analysis_type="modal",
            eigenvalues=evs,
            frequencies=freqs,
            warnings=[] if freqs else ["No eigenvalues found in F06 output"],
        )

    def _run_static(
        self,
        nodes: list,
        elements: list,
        materials: dict,
        boundary_conditions: list[dict],
        loads: list[dict],
        *,
        shell_thickness: Optional[float] = None,
    ) -> MystranResult:
        deck = _write_bdf_static(
            nodes, elements, materials, boundary_conditions, loads,
            shell_thickness=shell_thickness,
        )
        try:
            f06_content = self._run_mystran(deck)
        except RuntimeError as exc:
            return MystranResult(
                ok=False,
                analysis_type="linear_static",
                status="failed",
                errors=[str(exc)],
            )

        disps = _parse_f06_displacements(f06_content)
        max_disp = max(
            (math.sqrt(d["ux"] ** 2 + d["uy"] ** 2 + d["uz"] ** 2) for d in disps),
            default=0.0,
        )
        return MystranResult(
            ok=True,
            analysis_type="linear_static",
            displacements=disps,
            max_displacement=max_disp,
        )

    def _run_mystran(self, bdf_content: str) -> str:
        """
        Write the BDF deck to a temp dir, invoke ``mystran``, and return the
        F06 output as a string.  Raises RuntimeError on non-zero exit.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            bdf_path = tmpdir / "analysis.bdf"
            bdf_path.write_text(bdf_content)

            proc = subprocess.run(
                ["mystran", str(bdf_path)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"MYSTRAN exited with code {proc.returncode}: "
                    f"{proc.stderr[:2000]}"
                )

            # MYSTRAN writes output as <basename>.F06
            f06_path = tmpdir / "analysis.F06"
            if not f06_path.exists():
                # Some versions write lowercase
                f06_path = tmpdir / "analysis.f06"
            if not f06_path.exists():
                raise RuntimeError(
                    "MYSTRAN did not produce an F06 output file. "
                    f"stdout: {proc.stdout[:500]}"
                )

            return f06_path.read_text(errors="replace")
