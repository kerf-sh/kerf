"""
CalculiX subprocess bridge — general-purpose solver interface.

Public API
----------
    CalculiXBridge.solve(mesh, materials, boundary_conditions,
                         *, analysis_type="linear_static") -> Result

The bridge writes a CalculiX ``.inp`` deck to a temporary directory,
shells out to ``ccx -i <prefix>``, then parses the resulting ``.dat``
and/or ``.frd`` files and returns a normalised ``Result`` object.

When ``ccx`` is not on PATH, ``solve`` raises ``CalculiXNotAvailable``
(a ``RuntimeError`` subclass) so tests can ``pytest.skip`` cleanly.

Supported ``analysis_type`` values
-----------------------------------
"linear_static"    : *STEP / *STATIC — displacements + von-Mises stresses
"modal"            : *FREQUENCY — natural frequencies + mode shapes
"nonlinear_static" : *STEP,NLGEOM / *STATIC — large-displacement static
"contact"          : *STEP,NLGEOM / *STATIC with *CONTACT PAIR surface-to-
                     surface frictionless contact (pair 1: slave Sslave /
                     master Smaster)

Mesh format
-----------
  nodes    : list of [x, y, z]  (3-D)
  elements : list of (elem_id, elem_type, [node_ids ...])
             elem_type one of: "tetra" (C3D4), "hex" (C3D8), "wedge" (C3D6)

Materials format
----------------
  list of dicts, each:
    { "name": str, "E": float, "nu": float, "rho": float (opt) }

boundary_conditions format
--------------------------
  list of dicts, each one of:
    { "type": "fixed",       "node_set": str, "dofs": "1,3" }
    { "type": "displacement","node_set": str, "dof": int, "value": float }
    { "type": "cload",       "node_set": str, "dof": int, "value": float }
    { "type": "pressure",    "surface": str,  "value": float }
    { "type": "contact",     "slave": str,    "master": str,
                             "penalty": float (opt, default 1e5) }

Result object fields
--------------------
  ok           : bool
  analysis_type: str
  displacements: list[dict]  — {node_id, ux, uy, uz, mag}
  stresses     : list[dict]  — {elem_id, von_mises, sx, sy, sz, ...}
  frequencies  : list[float] — natural frequencies in Hz (modal only)
  mode_shapes  : list[list[dict]] — per-mode list of {node_id, ux, uy, uz}
  contact_pressure: float | None  — max contact pressure extracted from .dat
  warnings     : list[str]
  errors       : list[str]
  raw_stdout   : str          — ccx stdout (truncated to 4 kB)
  raw_stderr   : str          — ccx stderr (truncated to 4 kB)
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
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability sentinel
# ---------------------------------------------------------------------------

class CalculiXNotAvailable(RuntimeError):
    """Raised when the ``ccx`` binary cannot be found on PATH."""


def _ccx_available() -> bool:
    return shutil.which("ccx") is not None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class Result:
    ok: bool
    analysis_type: str
    displacements: list[dict] = field(default_factory=list)
    stresses: list[dict] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)
    mode_shapes: list[list[dict]] = field(default_factory=list)
    contact_pressure: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""


# ---------------------------------------------------------------------------
# CCX element type mapping
# ---------------------------------------------------------------------------

_ELEM_TYPE_MAP = {
    "tetra":  "C3D4",
    "tet4":   "C3D4",
    "tet10":  "C3D10",
    "hex":    "C3D8",
    "hex8":   "C3D8",
    "hex20":  "C3D20",
    "wedge":  "C3D6",
    "wedge6": "C3D6",
    "tri":    "CPS3",
    "quad":   "CPS4",
}


# ---------------------------------------------------------------------------
# INP deck builder
# ---------------------------------------------------------------------------

class _InpDeck:
    """Build a CalculiX ``.inp`` input deck incrementally."""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def raw(self, text: str) -> "_InpDeck":
        self._lines.append(text)
        return self

    def comment(self, text: str) -> "_InpDeck":
        self._lines.append(f"** {text}")
        return self

    def heading(self, title: str = "CalculiX analysis") -> "_InpDeck":
        self._lines.extend(["*HEADING", title])
        return self

    def nodes(self, node_list: list) -> "_InpDeck":
        """Emit *NODE block.  node_list: [(id, x, y, z), ...]"""
        self._lines.append("*NODE")
        for nid, x, y, z in node_list:
            self._lines.append(f"{nid},{x:.10g},{y:.10g},{z:.10g}")
        return self

    def elements(self, elem_list: list, elset: str = "Eall") -> "_InpDeck":
        """
        Emit *ELEMENT blocks grouped by type.
        elem_list: [(eid, etype_str, [nids ...]), ...]
        """
        by_type: dict[str, list] = {}
        for eid, etype, nids in elem_list:
            ccx_type = _ELEM_TYPE_MAP.get(etype, "C3D4")
            by_type.setdefault(ccx_type, []).append((eid, nids))

        for ccx_type, group in by_type.items():
            self._lines.append(f"*ELEMENT,TYPE={ccx_type},ELSET={elset}")
            for eid, nids in group:
                self._lines.append(f"{eid}," + ",".join(str(n) for n in nids))
        return self

    def nset(self, name: str, node_ids: list[int]) -> "_InpDeck":
        self._lines.append(f"*NSET,NSET={name}")
        # CalculiX allows up to 16 entries per line
        chunk = 16
        for i in range(0, len(node_ids), chunk):
            self._lines.append(",".join(str(n) for n in node_ids[i:i + chunk]))
        return self

    def elset(self, name: str, elem_ids: list[int]) -> "_InpDeck":
        self._lines.append(f"*ELSET,ELSET={name}")
        chunk = 16
        for i in range(0, len(elem_ids), chunk):
            self._lines.append(",".join(str(e) for e in elem_ids[i:i + chunk]))
        return self

    def surface(self, name: str, elset: str, face: str = "S1") -> "_InpDeck":
        self._lines.append(f"*SURFACE,NAME={name}")
        self._lines.append(f"{elset},{face}")
        return self

    def material(self, name: str, E: float, nu: float,
                 rho: Optional[float] = None) -> "_InpDeck":
        self._lines.extend([
            "**",
            f"*MATERIAL,NAME={name}",
            "*ELASTIC",
            f"{E:.6g},{nu:.6g}",
        ])
        if rho is not None:
            self._lines.extend(["*DENSITY", f"{rho:.6g}"])
        return self

    def solid_section(self, elset: str, material: str) -> "_InpDeck":
        self._lines.append(f"*SOLID SECTION,ELSET={elset},MATERIAL={material}")
        self._lines.append("")
        return self

    def boundary(self, nset_name: str, dof_start: int, dof_end: int,
                 value: float = 0.0) -> "_InpDeck":
        self._lines.extend([
            "*BOUNDARY",
            f"{nset_name},{dof_start},{dof_end},{value:.6g}",
        ])
        return self

    def cload(self, nset_name: str, dof: int, value: float) -> "_InpDeck":
        self._lines.extend([
            "*CLOAD",
            f"{nset_name},{dof},{value:.6g}",
        ])
        return self

    def dload_pressure(self, surface: str, value: float) -> "_InpDeck":
        self._lines.extend([
            "*DLOAD",
            f"{surface},P,{value:.6g}",
        ])
        return self

    def contact_pair(self, slave: str, master: str,
                     penalty: float = 1e5) -> "_InpDeck":
        self._lines.extend([
            "*SURFACE INTERACTION,NAME=FRIC",
            "*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR",
            f"{penalty:.6g}",
            f"*CONTACT PAIR,INTERACTION=FRIC,TYPE=SURFACE TO SURFACE",
            f"{slave},{master}",
        ])
        return self

    def step_static(self, nlgeom: bool = False,
                    name: str = "Static") -> "_InpDeck":
        flag = ",NLGEOM" if nlgeom else ""
        self._lines.extend([
            "**",
            f"*STEP,NAME={name}{flag}",
            "*STATIC",
            "**",
        ])
        return self

    def step_frequency(self, nmodes: int = 10,
                       name: str = "Modal") -> "_InpDeck":
        self._lines.extend([
            "**",
            f"*STEP,NAME={name}",
            f"*FREQUENCY,NMODES={nmodes}",
            "**",
        ])
        return self

    def node_file(self, *fields) -> "_InpDeck":
        self._lines.append("*NODE FILE")
        self._lines.append(",".join(fields) if fields else "U")
        return self

    def el_file(self, *fields) -> "_InpDeck":
        self._lines.append("*EL FILE")
        self._lines.append(",".join(fields) if fields else "S")
        return self

    def node_print(self, nset: str, *fields) -> "_InpDeck":
        self._lines.append(f"*NODE PRINT,NSET={nset}")
        self._lines.append(",".join(fields) if fields else "U")
        return self

    def el_print(self, elset: str, *fields) -> "_InpDeck":
        self._lines.append(f"*EL PRINT,ELSET={elset}")
        self._lines.append(",".join(fields) if fields else "S")
        return self

    def contact_print(self, surface: str) -> "_InpDeck":
        self._lines.extend([
            f"*CONTACT PRINT,SLAVE={surface}",
            "CSTRESS",
        ])
        return self

    def end_step(self) -> "_InpDeck":
        self._lines.append("*END STEP")
        return self

    def build(self) -> str:
        return "\n".join(self._lines) + "\n"


# ---------------------------------------------------------------------------
# .frd parser — displacements + mode shapes
# ---------------------------------------------------------------------------

def _parse_frd_displacements(frd_path: Path) -> list[dict]:
    """
    Extract displacement field from a CalculiX .frd file.
    Returns list of {node_id, ux, uy, uz, mag}.
    """
    if not frd_path.exists():
        return []

    displacements: list[dict] = []
    in_disp_block = False

    try:
        content = frd_path.read_text(errors="replace")
        for line in content.splitlines():
            stripped = line.rstrip()
            if len(stripped) < 3:
                continue
            record = stripped[:3].strip()

            if record == "-4":
                in_disp_block = "DISP" in stripped.upper() or " U " in stripped.upper()

            elif record == "-1" and in_disp_block:
                parts = stripped.split()
                if len(parts) >= 4:
                    try:
                        node_id = int(parts[0].lstrip("-"))
                        vals = [float(v) for v in parts[1:4]]
                        ux, uy, uz = vals[0], vals[1], vals[2]
                        mag = math.sqrt(ux * ux + uy * uy + uz * uz)
                        displacements.append({
                            "node_id": node_id,
                            "ux": ux, "uy": uy, "uz": uz, "mag": mag,
                        })
                    except (ValueError, IndexError):
                        pass

            elif record == "-3":
                if in_disp_block and displacements:
                    break
                in_disp_block = False
    except Exception as exc:
        logger.warning("frd displacement parse error: %s", exc)

    return displacements


def _parse_frd_mode_shapes(frd_path: Path,
                            num_modes: int) -> list[list[dict]]:
    """
    Extract per-mode displacement blocks from a CalculiX .frd modal file.
    Returns list[list[dict]]  — outer: per mode, inner: per node.
    """
    if not frd_path.exists():
        return []

    mode_shapes: list[list[dict]] = []
    current_nodes: list[dict] = []
    in_disp_block = False

    try:
        for line in frd_path.read_text(errors="replace").splitlines():
            stripped = line.rstrip()
            if len(stripped) < 3:
                continue
            record = stripped[:3].strip()

            if record == "-4":
                in_disp_block = ("DISP" in stripped.upper()
                                 or " U " in stripped.upper())
                current_nodes = []

            elif record == "-1" and in_disp_block:
                parts = stripped.split()
                if len(parts) >= 4:
                    try:
                        node_id = int(parts[0].lstrip("-"))
                        vals = [float(v) for v in parts[1:4]]
                        current_nodes.append({
                            "node_id": node_id,
                            "ux": vals[0], "uy": vals[1], "uz": vals[2],
                        })
                    except (ValueError, IndexError):
                        pass

            elif record == "-3" and in_disp_block:
                if current_nodes:
                    mode_shapes.append(current_nodes)
                current_nodes = []
                in_disp_block = False
                if len(mode_shapes) >= num_modes:
                    break

    except Exception as exc:
        logger.warning("frd mode-shape parse error: %s", exc)

    return mode_shapes


# ---------------------------------------------------------------------------
# .dat parser — eigenvalues, stresses, contact
# ---------------------------------------------------------------------------

def _parse_dat_eigenvalues(content: str) -> list[float]:
    """
    Parse CalculiX eigenvalue table from .dat content.
    Returns list of frequencies in Hz.
    """
    frequencies: list[float] = []
    block = re.search(
        r"E\s*I\s*G\s*E\s*N\s*V\s*A\s*L\s*U\s*E\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return frequencies

    for line in block.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                ev = float(parts[1])
                if ev > 0:
                    frequencies.append(math.sqrt(ev) / (2.0 * math.pi))
            except ValueError:
                pass
    return frequencies


def _parse_dat_stresses(content: str) -> list[dict]:
    """
    Parse integration-point stress output from .dat content.
    Returns list of {elem_id, sx, sy, sz, txy, tyz, txz, von_mises}.
    """
    stresses: list[dict] = []
    # CalculiX .dat stress block header contains 'S T R E S S'
    block = re.search(
        r"S\s*T\s*R\s*E\s*S\s*S\s*E\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return stresses

    for line in block.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 7 and parts[0].isdigit():
            try:
                eid = int(parts[0])
                sx, sy, sz = float(parts[1]), float(parts[2]), float(parts[3])
                txy, tyz, txz = float(parts[4]), float(parts[5]), float(parts[6])
                vm = math.sqrt(0.5 * (
                    (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2
                    + 6.0 * (txy ** 2 + tyz ** 2 + txz ** 2)
                ))
                stresses.append({
                    "elem_id": eid,
                    "sx": sx, "sy": sy, "sz": sz,
                    "txy": txy, "tyz": tyz, "txz": txz,
                    "von_mises": vm,
                })
            except (ValueError, IndexError):
                pass
    return stresses


def _parse_dat_contact_pressure(content: str) -> Optional[float]:
    """
    Extract the maximum contact pressure (CSTRESS) from .dat output.
    CalculiX writes CSTRESS blocks with contact node pressures.
    Returns the maximum absolute pressure value found, or None.
    """
    # Pattern: CSTRESS section with per-node pressure values
    block = re.search(
        r"C\s*S\s*T\s*R\s*E\s*S\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return None

    max_p: Optional[float] = None
    for line in block.group(1).splitlines():
        parts = line.split()
        # Lines: node_id  p_n  p_t1  p_t2  (pressure components)
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                p = abs(float(parts[1]))
                if max_p is None or p > max_p:
                    max_p = p
            except ValueError:
                pass
    return max_p


# ---------------------------------------------------------------------------
# Core bridge class
# ---------------------------------------------------------------------------

class CalculiXBridge:
    """
    Subprocess wrapper for the CalculiX ``ccx`` solver.

    Usage::

        bridge = CalculiXBridge()
        result = bridge.solve(mesh, materials, bcs, analysis_type="linear_static")

    Raises ``CalculiXNotAvailable`` when ``ccx`` is absent from PATH so
    callers (and tests) can detect the missing-binary condition and skip.
    """

    # Maximum bytes of stdout/stderr retained in Result
    _CAPTURE_LIMIT = 4096

    def __init__(self, timeout: int = 600) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def solve(
        self,
        mesh: dict,
        materials: list[dict],
        boundary_conditions: list[dict],
        *,
        analysis_type: str = "linear_static",
    ) -> Result:
        """
        Run a CalculiX analysis and return a normalised ``Result``.

        Parameters
        ----------
        mesh : dict
            ``{"nodes": [[x,y,z],...], "elements": [(id, type, [nids]),...]}``
        materials : list[dict]
            ``[{"name": str, "E": float, "nu": float, "rho": float?}, ...]``
        boundary_conditions : list[dict]
            See module docstring for supported BC types.
        analysis_type : str
            One of ``"linear_static"``, ``"modal"``,
            ``"nonlinear_static"``, ``"contact"``.

        Returns
        -------
        Result

        Raises
        ------
        CalculiXNotAvailable
            When ``ccx`` is not on PATH.
        ValueError
            When ``analysis_type`` is not recognised.
        """
        if not _ccx_available():
            raise CalculiXNotAvailable(
                "ccx (CalculiX) binary not found on PATH. "
                "Install via e.g. `brew install calculix` or "
                "`apt install calculix`."
            )

        supported = ("linear_static", "modal", "nonlinear_static", "contact")
        if analysis_type not in supported:
            raise ValueError(
                f"analysis_type must be one of {supported!r}, "
                f"got {analysis_type!r}"
            )

        with tempfile.TemporaryDirectory(prefix="kerf_ccx_") as tmp:
            tmpdir = Path(tmp)
            prefix = "analysis"

            inp_text = self._build_inp(mesh, materials, boundary_conditions,
                                       analysis_type)
            (tmpdir / f"{prefix}.inp").write_text(inp_text)

            proc = subprocess.run(
                ["ccx", "-i", prefix],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            stdout = proc.stdout[-self._CAPTURE_LIMIT:]
            stderr = proc.stderr[-self._CAPTURE_LIMIT:]

            if proc.returncode != 0:
                return Result(
                    ok=False,
                    analysis_type=analysis_type,
                    errors=[
                        f"ccx exited with code {proc.returncode}: "
                        f"{stderr[:500]}"
                    ],
                    raw_stdout=stdout,
                    raw_stderr=stderr,
                )

            return self._parse_results(
                tmpdir, prefix, analysis_type, stdout, stderr
            )

    def write_inp(
        self,
        mesh: dict,
        materials: list[dict],
        boundary_conditions: list[dict],
        analysis_type: str = "linear_static",
    ) -> str:
        """Return the INP deck as a string without running ccx."""
        return self._build_inp(mesh, materials, boundary_conditions,
                               analysis_type)

    # ------------------------------------------------------------------
    # INP deck construction
    # ------------------------------------------------------------------

    def _build_inp(
        self,
        mesh: dict,
        materials: list[dict],
        boundary_conditions: list[dict],
        analysis_type: str,
    ) -> str:
        nodes_raw = mesh.get("nodes", [])
        elems_raw = mesh.get("elements", [])

        # Normalise node list → [(id, x, y, z)]
        node_list: list[tuple] = []
        for i, pt in enumerate(nodes_raw):
            nid = pt[0] if len(pt) == 4 else i + 1
            coords = pt[-3:] if len(pt) >= 3 else list(pt) + [0.0] * (3 - len(pt))
            node_list.append((int(nid), float(coords[0]),
                               float(coords[1]), float(coords[2])))

        # Normalise element list → [(eid, etype_str, [nids])]
        elem_list: list[tuple] = []
        for item in elems_raw:
            if len(item) == 3:
                eid, etype, nids = item
            else:
                eid, etype, nids = item[0], "tetra", list(item[1:])
            elem_list.append((int(eid), str(etype), [int(n) for n in nids]))

        deck = _InpDeck()
        deck.heading(f"Kerf FEM — {analysis_type}")
        deck.nodes(node_list)
        deck.elements(elem_list)

        # Emit node sets referenced by BCs (collect named sets)
        named_nsets: dict[str, list[int]] = {}
        for bc in boundary_conditions:
            ns = bc.get("node_set")
            if ns and ns not in named_nsets:
                # Caller may supply pre-built node_ids in "node_ids" key
                nids = bc.get("node_ids", [])
                if nids:
                    named_nsets[ns] = [int(n) for n in nids]

        for ns_name, ns_ids in named_nsets.items():
            deck.nset(ns_name, ns_ids)

        # Materials
        mat_names = []
        for mat in (materials or []):
            mname = mat.get("name", "MAT")
            E = float(mat.get("E", 200e9))
            nu = float(mat.get("nu", 0.3))
            rho = mat.get("rho")
            deck.material(mname, E, nu,
                          rho=float(rho) if rho is not None else None)
            mat_names.append(mname)

        # Solid section using first material (or MAT if none provided)
        mat_for_section = mat_names[0] if mat_names else "MAT"
        deck.solid_section("Eall", mat_for_section)

        # Pre-step BCs (fixed / prescribed displacement)
        nlgeom = analysis_type in ("nonlinear_static", "contact")

        for bc in boundary_conditions:
            bc_type = bc.get("type", "")
            if bc_type == "fixed":
                ns = bc.get("node_set", "Nfix")
                dofs = bc.get("dofs", "1,3")
                dof_parts = [int(d.strip()) for d in str(dofs).split(",")]
                d_start = dof_parts[0]
                d_end = dof_parts[-1] if len(dof_parts) > 1 else d_start
                deck.boundary(ns, d_start, d_end, 0.0)
            elif bc_type == "displacement":
                ns = bc.get("node_set", "Ndisp")
                dof = int(bc.get("dof", 1))
                value = float(bc.get("value", 0.0))
                deck.boundary(ns, dof, dof, value)

        # Contact interaction (before *STEP in CalculiX)
        for bc in boundary_conditions:
            if bc.get("type") == "contact":
                slave = bc.get("slave", "Sslave")
                master = bc.get("master", "Smaster")
                penalty = float(bc.get("penalty", 1e5))
                deck.contact_pair(slave, master, penalty)

        # Step block
        if analysis_type == "modal":
            nmodes = 10
            for mat in (materials or []):
                nmodes = int(mat.get("num_modes", nmodes))
            deck.step_frequency(nmodes)
        else:
            deck.step_static(nlgeom=nlgeom)

        # In-step loads
        for bc in boundary_conditions:
            bc_type = bc.get("type", "")
            if bc_type == "cload":
                ns = bc.get("node_set", "Nload")
                dof = int(bc.get("dof", 3))
                value = float(bc.get("value", 0.0))
                deck.cload(ns, dof, value)
            elif bc_type == "pressure":
                surf = bc.get("surface", "Sload")
                value = float(bc.get("value", 0.0))
                deck.dload_pressure(surf, value)

        # Output requests
        if analysis_type == "modal":
            deck.node_file("U")
        else:
            deck.node_file("U")
            deck.el_file("S")
            deck.node_print("Nall", "U")
            deck.el_print("Eall", "S")

            # Contact stress output
            for bc in boundary_conditions:
                if bc.get("type") == "contact":
                    slave = bc.get("slave", "Sslave")
                    deck.contact_print(slave)

        deck.end_step()
        return deck.build()

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def _parse_results(
        self,
        tmpdir: Path,
        prefix: str,
        analysis_type: str,
        stdout: str,
        stderr: str,
    ) -> Result:
        dat_path = tmpdir / f"{prefix}.dat"
        frd_path = tmpdir / f"{prefix}.frd"

        dat_content = dat_path.read_text(errors="replace") if dat_path.exists() else ""

        result = Result(
            ok=True,
            analysis_type=analysis_type,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )

        if analysis_type == "modal":
            result.frequencies = _parse_dat_eigenvalues(dat_content)
            result.mode_shapes = _parse_frd_mode_shapes(frd_path, 100)
        else:
            result.displacements = _parse_frd_displacements(frd_path)
            result.stresses = _parse_dat_stresses(dat_content)
            if analysis_type == "contact":
                result.contact_pressure = _parse_dat_contact_pressure(dat_content)

        return result
