import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter()

@router.post("/run-fem")
async def run_fem(req: dict):
    step_b64 = req.get("step_b64")
    input_spec = req.get("input_spec", {})

    if not step_b64:
        raise HTTPException(status_code=400, detail="step_b64 required")

    try:
        step_bytes = base64.b64decode(step_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid step_b64: {e}")

    mesh_size = input_spec.get("mesh_size", 0.01)
    solver = input_spec.get("solver", "fenicsx")
    analysis_type = input_spec.get("analysis_type", "linear_static")
    material_props = input_spec.get("material_props", {
        "E": 200e9,
        "nu": 0.3,
        "rho": 7850.0,
        "yield_strength": 250e6
    })
    boundary_conditions = input_spec.get("boundary_conditions", [])
    loads = input_spec.get("loads", [])

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = Path(tmpdir) / "input.step"
        step_path.write_bytes(step_bytes)

        try:
            msh_path = generate_mesh(str(step_path), mesh_size, tmpdir)
        except Exception as e:
            return {"error": f"meshing failed: {e}"}

        try:
            result = run_simulation(
                mesh_path=str(msh_path),
                solver=solver,
                analysis_type=analysis_type,
                material_props=material_props,
                boundary_conditions=boundary_conditions,
                loads=loads,
                tmpdir=tmpdir
            )
        except Exception as e:
            return {"error": f"simulation failed: {e}"}

    result_b64 = base64.b64encode(json.dumps(result).encode()).decode()
    return {"result_b64": result_b64}


def generate_mesh(step_path: str, mesh_size: float, tmpdir: str) -> Path:
    try:
        import gmsh
    except ImportError as e:
        raise RuntimeError(f"gmsh not installed: {e}. Install with: pip install gmsh")

    gmsh.initialize()  # noqa: gmsh is lazily imported above
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Mesh.CharacteristicSizeMax", mesh_size)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)

    try:
        _, _, data = gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        for dim_tag in data:
            gmsh.model.addPhysicalGroup(dim_tag[0], [dim_tag[1]], name=f"face_{dim_tag[1]}")

        gmsh.model.mesh.generate(3)
        msh_path = Path(tmpdir) / "mesh.msh"
        gmsh.write(str(msh_path))
    finally:
        gmsh.finalize()

    return msh_path


def run_simulation(mesh_path: str, solver: str, analysis_type: str,
                   material_props: dict, boundary_conditions: list,
                   loads: list, tmpdir: str) -> dict:
    if solver == "fenicsx":
        return run_fenicsx(mesh_path, analysis_type, material_props, boundary_conditions, loads, tmpdir)
    elif solver == "calculix":
        return run_calculix(mesh_path, analysis_type, material_props, boundary_conditions, loads, tmpdir)
    else:
        raise ValueError(f"unknown solver: {solver}")


def run_fenicsx(mesh_path: str, analysis_type: str, material_props: dict,
               boundary_conditions: list, loads: list, tmpdir: str) -> dict:
    import json as json_mod

    script = f"""
import json
import numpy as np
from fenicsx_utils import run_static_analysis

material_props = {json_mod.dumps(material_props)}
boundary_conditions = {json_mod.dumps(boundary_conditions)}
loads = {json_mod.dumps(loads)}

result = run_static_analysis(
    mesh_path="{mesh_path}",
    material_props=material_props,
    boundary_conditions=boundary_conditions,
    loads=loads,
    analysis_type="{analysis_type}"
)
print("FEM_RESULT:" + json.dumps(result))
"""

    script_path = Path(tmpdir) / "fenicsx_script.py"
    script_path.write_text(script)

    result_file = Path(tmpdir) / "result.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = "/usr/local/lib/python3.11/site-packages:" + str(Path(__file__).parent)

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env
    )

    if proc.returncode != 0:
        raise RuntimeError(f"fenicsx failed: {proc.stderr}")

    for line in proc.stdout.splitlines():
        if line.startswith("FEM_RESULT:"):
            result_data = json_mod.loads(line[len("FEM_RESULT:"):])
            return result_data

    raise RuntimeError("fenicsx produced no result")


def run_calculix(mesh_path: str, analysis_type: str, material_props: dict,
                boundary_conditions: list, loads: list, tmpdir: str) -> dict:
    import json as json_mod

    script = f"""
import json
import numpy as np
from calculix_utils import run_static_analysis

material_props = {json_mod.dumps(material_props)}
boundary_conditions = {json_mod.dumps(boundary_conditions)}
loads = {json_mod.dumps(loads)}

result = run_static_analysis(
    mesh_path="{mesh_path}",
    material_props=material_props,
    boundary_conditions=boundary_conditions,
    loads=loads,
    analysis_type="{analysis_type}"
)
print("FEM_RESULT:" + json.dumps(result))
"""

    script_path = Path(tmpdir) / "calculix_script.py"
    script_path.write_text(script)

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=600
    )

    if proc.returncode != 0:
        raise RuntimeError(f"calculix failed: {proc.stderr}")

    for line in proc.stdout.splitlines():
        if line.startswith("FEM_RESULT:"):
            result_data = json_mod.loads(line[len("FEM_RESULT:"):])
            return result_data

    raise RuntimeError("calculix produced no result")