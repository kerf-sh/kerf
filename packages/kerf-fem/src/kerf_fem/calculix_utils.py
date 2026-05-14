"""
CalculiX utilities for static and modal analysis.
Writes .inp file, runs ccx, parses .dat (eigenvalues) and .frd (mode shapes).
"""

import logging
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CALCULIX_AVAILABLE: Optional[bool] = None


def _ccx_available() -> bool:
    global _CALCULIX_AVAILABLE
    if _CALCULIX_AVAILABLE is None:
        _CALCULIX_AVAILABLE = shutil.which("ccx") is not None
    return _CALCULIX_AVAILABLE


ENGINE_PENDING_WARNING = "Engine pending — CalculiX (ccx) not installed or not in PATH."


def run_static_analysis(mesh_path: str, material_props: dict,
                        boundary_conditions: list, loads: list,
                        analysis_type: str = "linear_static") -> dict:
    if not _ccx_available():
        return {
            "status": "pending",
            "warnings": [ENGINE_PENDING_WARNING],
            "errors": [],
        }
    if analysis_type == "linear_static":
        return _run_calculix_static(mesh_path, material_props, boundary_conditions, loads)
    elif analysis_type == "modal":
        return _run_calculix_modal(mesh_path, material_props, boundary_conditions)
    elif analysis_type == "thermal":
        return _run_calculix_thermal(mesh_path, material_props, boundary_conditions, loads)
    else:
        raise ValueError(f"unknown analysis_type: {analysis_type}")


# ---------------------------------------------------------------------------
# INP deck writers
# ---------------------------------------------------------------------------

def _write_nodes_and_elements(inp_lines: list, nodes, elements: list,
                               elem_type_map: dict) -> None:
    """Append *NODE and *ELEMENT blocks to inp_lines in-place."""
    inp_lines.append("*NODE")
    for i, pt in enumerate(nodes):
        inp_lines.append(f"{i + 1},{pt[0]:.10g},{pt[1]:.10g},{pt[2]:.10g}")

    # Group elements by type.
    by_type: dict = {}
    for (eid, etype, enodes) in elements:
        by_type.setdefault(etype, []).append((eid, enodes))

    for etype, egroup in by_type.items():
        ccx_type = elem_type_map.get(etype, "C3D4")
        inp_lines.append(f"*ELEMENT,TYPE={ccx_type},ELSET=Eall")
        for eid, enodes in egroup:
            inp_lines.append(f"{eid}," + ",".join(str(n) for n in enodes))


def _write_material(inp_lines: list, E: float, nu: float, rho: float) -> None:
    inp_lines.extend([
        "**",
        "*MATERIAL,NAME=MAT",
        "*ELASTIC",
        f"{E:.6g},{nu:.6g}",
        "*DENSITY",
        f"{rho:.6g}",
        "*SOLID SECTION,ELSET=Eall,MATERIAL=MAT",
        "",
    ])


def _write_fixed_bc(inp_lines: list, fixed_node_sets: list) -> None:
    """Write *BOUNDARY for each pre-defined node-set name."""
    for nset in fixed_node_sets:
        inp_lines.append("*BOUNDARY")
        inp_lines.append(f"{nset},1,3,0.0")


def _build_face_node_sets(nodes, elements: list, face_tags: list) -> dict:
    """
    CalculiX doesn't have Gmsh physical-group awareness. We approximate
    boundary-condition faces by partitioning boundary (surface-exposed) nodes
    by their spatial position.  For simple geometries the canonical Gmsh face
    ordering maps to: tag 1 → x=xmin face, tag 2 → x=xmax, etc.  We sort faces
    by their centroid coordinate and assign tags 1…N in that order.

    Returns {tag_int → set_name} and emits *NSET blocks into inp_lines.
    """
    import numpy as np

    pts = np.array(nodes)
    bounds = {
        "xmin": pts[:, 0].min(), "xmax": pts[:, 0].max(),
        "ymin": pts[:, 1].min(), "ymax": pts[:, 1].max(),
        "zmin": pts[:, 2].min(), "zmax": pts[:, 2].max(),
    }
    tol = max(
        bounds["xmax"] - bounds["xmin"],
        bounds["ymax"] - bounds["ymin"],
        bounds["zmax"] - bounds["zmin"],
    ) * 0.02  # 2% of bounding box

    # The 6 axis-aligned face planes, ordered by typical Gmsh tag assignment.
    planes = [
        ("xmin", 0, bounds["xmin"]),
        ("xmax", 0, bounds["xmax"]),
        ("ymin", 1, bounds["ymin"]),
        ("ymax", 1, bounds["ymax"]),
        ("zmin", 2, bounds["zmin"]),
        ("zmax", 2, bounds["zmax"]),
    ]

    tag_to_set = {}
    for tag in face_tags:
        idx = tag - 1  # convert 1-based tag to 0-based plane index
        if idx < 0 or idx >= len(planes):
            continue
        label, axis, coord = planes[idx]
        node_ids = [
            i + 1 for i, pt in enumerate(nodes)
            if abs(pt[axis] - coord) <= tol
        ]
        if not node_ids:
            continue
        set_name = f"BC{tag}"
        tag_to_set[tag] = (set_name, node_ids)

    return tag_to_set


def _msh_to_inp_static(mesh_path: str, material_props: dict,
                        boundary_conditions: list, loads: list) -> str:
    import meshio

    msh = meshio.read(mesh_path)
    nodes = msh.points

    elements = []
    elem_id = 1
    elem_type_map = {"tetra": "C3D4", "triangle": "CPS3"}
    for cell_block in msh.cells:
        if cell_block.type in elem_type_map:
            for row in cell_block.data:
                elem_nodes = [int(n) + 1 for n in row]
                elements.append((elem_id, cell_block.type, elem_nodes))
                elem_id += 1

    E = material_props["E"]
    nu = material_props["nu"]
    rho = material_props.get("rho", 7850.0)

    inp = []
    inp.append("*HEADING")
    inp.append("CalculiX static analysis")
    _write_nodes_and_elements(inp, nodes, elements, elem_type_map)
    _write_material(inp, E, nu, rho)

    # Collect all face_tags that appear in BCs.
    all_tags = []
    for bc in boundary_conditions:
        all_tags.extend(bc.get("face_tags", []))

    face_sets = _build_face_node_sets(nodes, elements, all_tags)
    for tag, (set_name, node_ids) in face_sets.items():
        inp.append(f"*NSET,NSET={set_name}")
        inp.append(",".join(str(n) for n in node_ids))

    inp.extend(["**", "*STEP,NAME=Static", "*STATIC"])
    inp.append("**")

    for bc in boundary_conditions:
        if bc["type"] == "fixed":
            for tag in bc.get("face_tags", []):
                if tag in face_sets:
                    set_name = face_sets[tag][0]
                    inp.append("*BOUNDARY")
                    inp.append(f"{set_name},1,3,0.0")

    for load in (loads or []):
        if load["type"] in ("pressure", "force"):
            inp.append("*CLOAD")
            node_id = 1  # fallback: apply to first node
            inp.append(f"{node_id},3,{load['value']}")

    inp.extend([
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ])
    return "\n".join(inp)


def _msh_to_inp_modal(mesh_path: str, material_props: dict,
                       boundary_conditions: list, num_modes: int = 10) -> str:
    import meshio

    msh = meshio.read(mesh_path)
    nodes = msh.points

    elements = []
    elem_id = 1
    elem_type_map = {"tetra": "C3D4", "triangle": "CPS3"}
    for cell_block in msh.cells:
        if cell_block.type in elem_type_map:
            for row in cell_block.data:
                elem_nodes = [int(n) + 1 for n in row]
                elements.append((elem_id, cell_block.type, elem_nodes))
                elem_id += 1

    E = material_props["E"]
    nu = material_props["nu"]
    rho = material_props.get("rho", 7850.0)

    inp = []
    inp.append("*HEADING")
    inp.append("CalculiX modal analysis")
    _write_nodes_and_elements(inp, nodes, elements, elem_type_map)
    _write_material(inp, E, nu, rho)

    all_tags = []
    for bc in boundary_conditions:
        all_tags.extend(bc.get("face_tags", []))

    face_sets = _build_face_node_sets(nodes, elements, all_tags)
    for tag, (set_name, node_ids) in face_sets.items():
        inp.append(f"*NSET,NSET={set_name}")
        inp.append(",".join(str(n) for n in node_ids))

    # Boundary conditions must go BEFORE the *STEP block in CalculiX modal.
    for bc in boundary_conditions:
        if bc["type"] == "fixed":
            for tag in bc.get("face_tags", []):
                if tag in face_sets:
                    set_name = face_sets[tag][0]
                    inp.append("*BOUNDARY")
                    inp.append(f"{set_name},1,3,0.0")

    inp.extend([
        "**",
        f"*STEP,NAME=Modal",
        f"*FREQUENCY,NMODES={num_modes}",
        "**",
        "*NODE FILE",
        "U",
        "*END STEP",
    ])
    return "\n".join(inp)


# ---------------------------------------------------------------------------
# .dat parser (eigenvalues for modal, displacements/stresses for static)
# ---------------------------------------------------------------------------

def _parse_dat_eigenvalues(content: str) -> list:
    """
    Extract eigenvalues (ω² in rad²/s²) from the CalculiX .dat file.

    CalculiX writes an eigenvalue table with a header like:
        E I G E N V A L U E S
         MODE   EIGENVALUE     ...
    followed by rows:  <mode_num>  <eigenvalue>  ...

    Returns list of frequencies in Hz: f = sqrt(eigenvalue) / (2π).
    """
    frequencies = []
    # Find the eigenvalue table — header is spaced out in CalculiX output.
    block_match = re.search(
        r"E\s*I\s*G\s*E\s*N\s*V\s*A\s*L\s*U\s*E\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE
    )
    if not block_match:
        return frequencies

    for line in block_match.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                eigenvalue = float(parts[1])
                if eigenvalue > 0:
                    freq_hz = math.sqrt(eigenvalue) / (2.0 * math.pi)
                    frequencies.append(freq_hz)
            except ValueError:
                pass

    return frequencies


def _parse_dat_static(dat_path: Path) -> dict:
    if not dat_path.exists():
        return {"error": f"CalculiX .dat file not found: {dat_path}"}

    content = dat_path.read_text(errors="replace")
    displacements = []
    stresses = []

    disp_match = re.search(
        r"D\s*I\s*S\s*P\s*L\s*A\s*C\s*E\s*M\s*E\s*N\s*T\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE
    )
    if disp_match:
        for line in disp_match.group(1).splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                try:
                    ux, uy, uz = float(parts[1]), float(parts[2]), float(parts[3])
                    displacements.append([ux, uy, uz])
                except ValueError:
                    pass

    stress_match = re.search(
        r"S\s*T\s*R\s*E\s*S\s*S\s*E\s*S(.*?)(?=\n\s*\n|\Z)",
        content, re.DOTALL | re.IGNORECASE
    )
    if stress_match:
        for line in stress_match.group(1).splitlines():
            parts = line.split()
            if len(parts) >= 7 and parts[0].isdigit():
                try:
                    sx, sy, sz = float(parts[1]), float(parts[2]), float(parts[3])
                    txy, tyz, txz = float(parts[4]), float(parts[5]), float(parts[6])
                    vm = math.sqrt(0.5 * (
                        (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2
                        + 6 * (txy ** 2 + tyz ** 2 + txz ** 2)
                    ))
                    stresses.append({"von_mises": vm, "sx": sx, "sy": sy, "sz": sz})
                except ValueError:
                    pass

    return {"displacements": displacements, "stresses": stresses}


# ---------------------------------------------------------------------------
# .frd parser (mode shapes for modal analysis)
# ---------------------------------------------------------------------------

def _parse_frd_mode_shapes(frd_path: Path, num_modes: int) -> list:
    """
    Parse CalculiX .frd binary/ASCII results file for mode-shape displacements.

    The .frd file uses a fixed-format ASCII layout.  Each result block begins:
        -4  <set_name>  <n_dof>  <step>
    followed by component headers:
        -5  U1  ...
        -5  U2  ...
        -5  U3  ...
    and then node data lines:
        -1  <node_id>  <U1>  <U2>  <U3>
    followed by:
        -3   (end of block)

    For modal analysis CalculiX writes one block per mode.  We collect the
    first `num_modes` blocks that contain displacement (U) results.

    Returns list[list[{ux, uy, uz}]] — outer list is per mode, inner is per node.
    """
    if not frd_path.exists():
        logger.warning("CalculiX .frd not found: %s", frd_path)
        return []

    mode_shapes = []
    current_nodes = []
    in_displacement_block = False
    component_cols: list = []  # ordered component names in this block

    try:
        for raw_line in frd_path.read_text(errors="replace").splitlines():
            line = raw_line.rstrip()
            if len(line) < 3:
                continue

            record_type = line[:3].strip()

            if record_type == "-4":
                # Start of a new result block.
                # Check if it's a displacement (U) block.
                in_displacement_block = "DISP" in line.upper() or " U " in line.upper()
                component_cols = []
                current_nodes = []

            elif record_type == "-5" and in_displacement_block:
                # Component header: -5  U1  ...
                parts = line.split()
                if len(parts) >= 2:
                    component_cols.append(parts[1].upper())

            elif record_type == "-1" and in_displacement_block:
                # Node data line: -1  <id>  <v1>  <v2>  ...
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        vals = [float(v) for v in parts[1:]]
                        ux = vals[0] if len(vals) > 0 else 0.0
                        uy = vals[1] if len(vals) > 1 else 0.0
                        uz = vals[2] if len(vals) > 2 else 0.0
                        current_nodes.append({"ux": ux, "uy": uy, "uz": uz})
                    except ValueError:
                        pass

            elif record_type == "-3" and in_displacement_block:
                # End of block — save this mode shape.
                if current_nodes:
                    mode_shapes.append(current_nodes)
                current_nodes = []
                in_displacement_block = False
                if len(mode_shapes) >= num_modes:
                    break

    except Exception as e:
        logger.warning("frd parse error: %s", e)

    return mode_shapes


# ---------------------------------------------------------------------------
# Analysis runners
# ---------------------------------------------------------------------------

def _run_ccx(tmpdir: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ccx", "analysis"],
        cwd=tmpdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_calculix_static(mesh_path: str, material_props: dict,
                          boundary_conditions: list, loads: list) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        inp_path = tmpdir / "analysis.inp"
        inp_path.write_text(_msh_to_inp_static(mesh_path, material_props,
                                                boundary_conditions, loads))

        proc = _run_ccx(tmpdir)
        if proc.returncode != 0:
            raise RuntimeError(f"CalculiX failed (code {proc.returncode}): {proc.stderr[:1000]}")

        dat_path = tmpdir / "analysis.dat"
        parsed = _parse_dat_static(dat_path)
        if "error" in parsed:
            raise RuntimeError(parsed["error"])

        displacements = parsed.get("displacements", [])
        stresses = parsed.get("stresses", [])

        max_disp = max(
            (math.sqrt(d[0]**2 + d[1]**2 + d[2]**2) for d in displacements),
            default=0.0,
        )
        max_stress = max((s["von_mises"] for s in stresses), default=0.0)
        yield_strength = material_props.get("yield_strength", 250e6)
        fos = yield_strength / max_stress if max_stress > 0 else float("inf")

        node_displacements = [
            {"ux": d[0], "uy": d[1], "uz": d[2],
             "mag": math.sqrt(d[0]**2 + d[1]**2 + d[2]**2)}
            for d in displacements
        ]

        return {
            "max_vonmises_stress": max_stress,
            "max_displacement": max_disp,
            "fos": fos,
            "node_displacements": node_displacements,
            "displacements": [math.sqrt(d[0]**2 + d[1]**2 + d[2]**2) for d in displacements],
            "stresses": [s["von_mises"] for s in stresses],
            "warnings": [],
            "errors": [],
        }


def _run_calculix_modal(mesh_path: str, material_props: dict,
                         boundary_conditions: list) -> dict:
    num_modes = material_props.get("num_modes", 10)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        inp_path = tmpdir / "analysis.inp"
        inp_path.write_text(_msh_to_inp_modal(mesh_path, material_props,
                                               boundary_conditions, num_modes))

        proc = _run_ccx(tmpdir)
        if proc.returncode != 0:
            raise RuntimeError(f"CalculiX failed (code {proc.returncode}): {proc.stderr[:1000]}")

        dat_path = tmpdir / "analysis.dat"
        dat_content = dat_path.read_text(errors="replace") if dat_path.exists() else ""
        frequencies = _parse_dat_eigenvalues(dat_content)

        frd_path = tmpdir / "analysis.frd"
        mode_shapes = _parse_frd_mode_shapes(frd_path, num_modes)

        return {
            "frequencies": frequencies,
            "mode_shapes": mode_shapes,
            "warnings": [],
            "errors": [],
        }


def _run_calculix_thermal(mesh_path: str, material_props: dict,
                           boundary_conditions: list, loads: list) -> dict:
    # Thermal analysis — basic stub returning empty result.
    # Full thermal deck writer is deferred until there are thermal BCs in the schema.
    return {
        "temperatures": [],
        "warnings": ["CalculiX thermal analysis not yet implemented"],
        "errors": [],
    }
