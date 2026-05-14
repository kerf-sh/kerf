import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

# Gate dolfinx — import only if available; pyworker must boot without it.
_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

ENGINE_PENDING_WARNING = "Engine pending — FEniCSx (dolfinx) not yet installed."

_CALCULIX_PENDING_WARNING = "Engine pending — CalculiX (ccx) not installed or not in PATH."


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

    # Return early with warning sentinel when dolfinx is absent and fenicsx
    # is the requested solver — mirror the /run-topo pattern.
    if solver == "fenicsx" and not _DOLFINX_AVAILABLE:
        return {
            "status": "pending",
            "warnings": [ENGINE_PENDING_WARNING],
            "errors": [],
        }

    # Gate CalculiX — check binary presence without importing anything heavy.
    if solver == "calculix":
        import shutil
        if not shutil.which("ccx"):
            return {
                "status": "pending",
                "warnings": [_CALCULIX_PENDING_WARNING],
                "errors": [],
            }

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

    gmsh.initialize()
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
    """
    Run a FEniCSx analysis directly in-process.

    dolfinx availability is already confirmed by the caller (run_fem checks
    _DOLFINX_AVAILABLE before reaching here for fenicsx solver).
    """
    from kerf_fem import fenicsx_utils  # package-relative import

    return fenicsx_utils.run_static_analysis(
        mesh_path=mesh_path,
        material_props=material_props,
        boundary_conditions=boundary_conditions,
        loads=loads,
        analysis_type=analysis_type,
    )


def run_calculix(mesh_path: str, analysis_type: str, material_props: dict,
                 boundary_conditions: list, loads: list, tmpdir: str) -> dict:
    from kerf_fem import calculix_utils  # package-relative import

    return calculix_utils.run_static_analysis(
        mesh_path=mesh_path,
        material_props=material_props,
        boundary_conditions=boundary_conditions,
        loads=loads,
        analysis_type=analysis_type,
    )
