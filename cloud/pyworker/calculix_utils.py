"""
CalculiX utilities for stress/modal analysis.
Writes .inp file, runs ccx, parses .dat and .frd files.
"""

import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def run_static_analysis(mesh_path: str, material_props: dict,
                        boundary_conditions: list, loads: list,
                        analysis_type: str = "linear_static") -> dict:
    if analysis_type == "linear_static":
        return _run_calculix_static(mesh_path, material_props, boundary_conditions, loads)
    elif analysis_type == "modal":
        return _run_calculix_modal(mesh_path, material_props, boundary_conditions)
    elif analysis_type == "thermal":
        return _run_calculix_thermal(mesh_path, material_props, boundary_conditions, loads)
    else:
        raise ValueError(f"unknown analysis_type: {analysis_type}")


def _ccx_available() -> bool:
    result = subprocess.run(["which", "ccx"], capture_output=True, text=True)
    return result.returncode == 0


def _msh_to_inp(mesh_path: str, material_props: dict,
                boundary_conditions: list, loads: list,
                analysis_type: str) -> str:
    import meshio

    msh = meshio.read(mesh_path)

    nodes = msh.points
    node_id_map = {}
    for i, pt in enumerate(nodes):
        node_id_map[i] = i + 1

    elements = []
    elem_id = 1
    for cell_block in msh.cells:
        if cell_block.type in ("tetra", "triangle"):
            for row in cell_block.data:
                elem_nodes = [node_id_map[n] for n in row]
                elements.append((elem_id, cell_block.type, elem_nodes))
                elem_id += 1

    E = material_props["E"]
    nu = material_props["nu"]
    rho = material_props.get("rho", 7850.0)
    yield_strength = material_props.get("yield_strength", 250e6)

    inp_lines = [
        "*HEADING",
        f"CalculiX Analysis - {analysis_type}",
        "**",
        "*INCLUDE,INPUT=nodes.inc",
    ]

    elem_type_map = {
        "tetra": "C3D4",
        "triangle": "CPS3",
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.inc', delete=False) as f:
        for i, pt in enumerate(nodes):
            f.write(f"{i + 1},{pt[0]},{pt[1]},{pt[2]}\n")
        nodes_inc = f.name

    for elem_id, elem_type, elem_nodes in elements:
        if analysis_type == "thermal":
            inp_lines.append(f"*ELEMENT,TYPE=C3D4,ELEMENT={elem_id}")
        else:
            inp_lines.append(f"*ELEMENT,TYPE={elem_type_map.get(elem_type, 'C3D4')},ELEMENT={elem_id}")
        for n in elem_nodes:
            inp_lines.append(f"{elem_id},{n}")
        break

    inp_lines.extend([
        "**",
        f"*MATERIAL,NAME=STEEL",
        f"*ELASTIC",
        f"{E},{nu}",
        f"*DENSITY",
        f"{rho}",
        "**",
        "** BOUNDARY CONDITIONS",
        "**",
    ])

    for i, bc in enumerate(boundary_conditions):
        if bc["type"] == "fixed":
            for tag in bc.get("face_tags", []):
                inp_lines.append(f"*BOUNDARY,OP=NEW")
                inp_lines.append(f"Fixed_{tag},1,6,0")
        elif bc["type"] == "displacement":
            for tag in bc.get("face_tags", []):
                ux = bc.get("ux", 0)
                uy = bc.get("uy", 0)
                uz = bc.get("uz", 0)
                dofs = []
                if ux != 0: dofs.append("1")
                if uy != 0: dofs.append("2")
                if uz != 0: dofs.append("3")
                if dofs:
                    inp_lines.append(f"*BOUNDARY")
                    inp_lines.append(f"Disp_{tag},{dofs[0]},1,{ux}")

    if loads:
        for i, load in enumerate(loads):
            if load["type"] == "pressure":
                inp_lines.append(f"*CLOAD")
                inp_lines.append(f"Pressure_{i},1,{load['value']}")
            elif load["type"] == "force":
                inp_lines.append(f"*CLOAD")
                inp_lines.append(f"Force_{i},3,{load['value']}")

    if analysis_type == "linear_static":
        inp_lines.extend([
            "**",
            "** STEP",
            "**",
            "*STEP,NAME=StaticLoad",
            "*STATIC",
            "**",
            "*NODE FILE,OUTPUT=2,U",
            "*EL FILE,STRESS",
            "*END STEP",
        ])
    elif analysis_type == "modal":
        freq_range = material_props.get("freq_range", [0, 1000])
        inp_lines.extend([
            "**",
            "*STEP,NAME=Modal",
            "*MODAL,DAMPING=0.02",
            "*FREQUENCY,SIMULATE=10",
            f"{freq_range[0]},{freq_range[1]}",
            "*NODE FILE,U",
            "*EL FILE,STRESS",
            "*END STEP",
        ])
    elif analysis_type == "thermal":
        inp_lines.extend([
            "**",
            "*STEP,NAME=Thermal",
            "*HEAT TRANSFER,STEADY STATE",
            "*DFLUX",
            "*END STEP",
        ])

    return "\n".join(inp_lines)


def _parse_calculix_dat(dat_path: Path) -> dict:
    if not dat_path.exists():
        return {"error": f"CalculiX .dat file not found: {dat_path}"}

    content = dat_path.read_text()

    displacements = []
    stresses = []
    frequencies = []
    warnings = []
    errors = []

    disp_match = re.search(r"DISPLACEMENTS\s+([\s\S]*?)(?=\n\s*\n|\*\*\*)", content)
    if disp_match:
        disp_text = disp_match.group(1)
        for line in disp_text.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                try:
                    ux, uy, uz = float(parts[1]), float(parts[2]), float(parts[3])
                    displacements.append([ux, uy, uz])
                except ValueError:
                    pass

    stress_match = re.search(r"STRESSES\s+([\s\S]*?)(?=\n\s*\n|\*\*\*)", content)
    if stress_match:
        stress_text = stress_match.group(1)
        for line in stress_text.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 7 and parts[0].isdigit():
                try:
                    sx, sy, sz = float(parts[1]), float(parts[2]), float(parts[3])
                    txy, tyz, txz = float(parts[4]), float(parts[5]), float(parts[6])
                    von_mises = (0.5 * ((sx - sy)**2 + (sy - sz)**2 + (sz - sx)**2 +
                                       6 * (txy**2 + tyz**2 + txz**2))) ** 0.5
                    stresses.append({"von_mises": von_mises, "sx": sx, "sy": sy, "sz": sz})
                except ValueError:
                    pass

    freq_match = re.search(r"EIGENVALUES\s+([\s\S]*?)(?=\n\s*\n|\*\*\*)", content)
    if freq_match:
        freq_text = freq_match.group(1)
        for line in freq_text.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                try:
                    freq = float(parts[1])
                    frequencies.append(freq)
                except ValueError:
                    pass

    return {
        "displacements": displacements,
        "stresses": stresses,
        "frequencies": frequencies,
        "warnings": warnings,
        "errors": errors,
    }


def _run_calculix_static(mesh_path: str, material_props: dict,
                         boundary_conditions: list, loads: list) -> dict:
    return _run_calculix_analysis(mesh_path, material_props, boundary_conditions, loads, "linear_static")


def _run_calculix_modal(mesh_path: str, material_props: dict,
                        boundary_conditions: list) -> dict:
    return _run_calculix_analysis(mesh_path, material_props, boundary_conditions, [], "modal")


def _run_calculix_thermal(mesh_path: str, material_props: dict,
                           boundary_conditions: list, loads: list) -> dict:
    return _run_calculix_analysis(mesh_path, material_props, boundary_conditions, loads, "thermal")


def _run_calculix_analysis(mesh_path: str, material_props: dict,
                           boundary_conditions: list, loads: list,
                           analysis_type: str) -> dict:
    if not _ccx_available():
        raise RuntimeError("CalculiX (ccx) not installed or not in PATH")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        inp_path = tmpdir / "analysis.inp"
        dat_path = tmpdir / "analysis.dat"
        frd_path = tmpdir / "analysis.frd"

        inp_content = _msh_to_inp(mesh_path, material_props, boundary_conditions, loads, analysis_type)
        inp_path.write_text(inp_content)

        proc = subprocess.run(
            ["ccx", "analysis"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if proc.returncode != 0:
            if "cannot open" in proc.stderr.lower() or "error" in proc.stderr.lower():
                raise RuntimeError(f"CalculiX failed: {proc.stderr[:1000]}")
            raise RuntimeError(f"CalculiX failed (code {proc.returncode}): {proc.stderr[:1000]}")

        result = _parse_calculix_dat(dat_path)

        if "error" in result and result["error"]:
            raise RuntimeError(result["error"])

        if analysis_type == "linear_static":
            max_disp = 0.0
            if result.get("displacements"):
                for d in result["displacements"]:
                    disp_mag = (d[0]**2 + d[1]**2 + d[2]**2) ** 0.5
                    max_disp = max(max_disp, disp_mag)

            max_stress = 0.0
            if result.get("stresses"):
                max_stress = max(s.get("von_mises", 0) for s in result["stresses"])

            yield_strength = material_props.get("yield_strength", 250e6)
            fos = yield_strength / max_stress if max_stress > 0 else float('inf')

            return {
                "max_vonmises_stress": max_stress,
                "max_displacement": max_disp,
                "fos": fos,
                "displacements": [((d[0]**2 + d[1]**2 + d[2]**2) ** 0.5) for d in result.get("displacements", [])],
                "stresses": [s.get("von_mises", 0) for s in result.get("stresses", [])],
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            }
        elif analysis_type == "modal":
            return {
                "frequencies": result.get("frequencies", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            }
        elif analysis_type == "thermal":
            return {
                "temperatures": result.get("temperatures", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            }

        return result
