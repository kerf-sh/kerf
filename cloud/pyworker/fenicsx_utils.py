"""
FEniCSx utilities for stress/modal/thermal analysis.
"""

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def run_static_analysis(mesh_path: str, material_props: dict,
                        boundary_conditions: list, loads: list,
                        analysis_type: str = "linear_static") -> dict:
    if analysis_type == "linear_static":
        return _run_linear_static(mesh_path, material_props, boundary_conditions, loads)
    elif analysis_type == "modal":
        return _run_modal(mesh_path, material_props, boundary_conditions)
    elif analysis_type == "thermal":
        return _run_thermal(mesh_path, material_props, boundary_conditions, loads)
    else:
        raise ValueError(f"unknown analysis_type: {analysis_type}")


def _build_fenicsx_script(mesh_path: str, material_props: dict,
                           boundary_conditions: list, loads: list,
                           analysis_type: str) -> str:
    return f"""
import json
import logging
import numpy as np
from pathlib import Path

try:
    import dolfinx
    from dolfinx.fem import FunctionSpace, Function, ConstantDomain, dirichletbc, form
    from dolfinx.fem.petsc import LinearProblem, NonlinearProblem
    from dolfinx.mesh import read_mesh
    from dolfinx.io import XDMFFile
    from dolfinx.plot import vtk_mesh
    import meshio
    import ufl
    from ufl import (TrialFunction, TestFunction, VectorElement,
                     FiniteElement, dot, grad, inner, identity, sqrt,
                     LabeledMesh)
    from petsc4py import PETSc
    import scipy.sparse as sp

    MESH_PATH = "{mesh_path}"
    MATERIAL_PROPS = {json.dumps(material_props)}
    BOUNDARY_CONDITIONS = {json.dumps(boundary_conditions)}
    LOADS = {json.dumps(loads)}
    ANALYSIS_TYPE = "{analysis_type}"

    E = MATERIAL_PROPS["E"]
    nu = MATERIAL_PROPS["nu"]
    rho = MATERIAL_PROPS.get("rho", 7850.0)

    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))

    def msh_to_xdmf(msh_path):
        msh = meshio.read(msh_path)
        for cell_block in msh.cells:
            if cell_block.type == "tetra":
                return meshio.Mesh(
                    points=msh.points,
                    cells=[meshio.CellBlock(
                        type="tetrahedron",
                        data=cell_block.data
                    )],
                    cell_data=msh.cell_data
                )
        for cell_block in msh.cells:
            if cell_block.type == "triangle":
                return meshio.Mesh(
                    points=msh.points,
                    cells=[meshio.CellBlock(
                        type="triangle",
                        data=cell_block.data
                    )],
                    cell_data=msh.cell_data
                )
        raise ValueError("No tetrahedra or triangles found in mesh")

    mesh_xdmf = Path("/tmp") / "fenicsx_mesh.xdmf"
    msh_xdmf = msh_to_xdmf(MESH_PATH)
    meshio.write(str(mesh_xdmf), msh_xdmf)

    with XDMFFile(dolfinx.MPI.comm_world, str(mesh_xdmf), "r") as xdmf:
        domain = xdmf.read_mesh(dolfinx.mesh.GhostMode.shared_facet)
        cell_tags = xdmf.read_meshtags(domain, "facet_tags")
        domain.topology.create_connectivity(domain.topology.dim - 1, domain.topology.dim)

    xdmf.unlink()

    def sigma(u):
        return lam * ufl.div(u) * ufl.Identity(3) + mu * (ufl.grad(u) + ufl.grad(u).T)

    def von_mises(s):
        s_dev = s - (1/3) * ufl.tr(s) * ufl.Identity(3)
        return ufl.sqrt(3/2 * inner(s_dev, s_dev))

    if ANALYSIS_TYPE == "linear_static":
        V = VectorFunctionSpace(domain, ("Lagrange", 1))
        u = Function(V)
        v = TestFunction(V)

        bcs = []
        for bc in BOUNDARY_CONDITIONS:
            if bc["type"] == "fixed":
                facets = np.where(cell_tags.values == bc["face_tags"][0])[0] if bc["face_tags"] else np.array([], dtype=np.int32)
                if len(facets) == 0 and bc["face_tags"]:
                    facets = np.where(np.isin(cell_tags.values, bc["face_tags"]))[0]
                if len(facets) > 0:
                    dofs = dolfinx.fem.locate_dofs_topological(V, domain.topology.dim - 1, facets)
                    bcs.append(dirichletbc(np.zeros(3, dtype=PETSc.ScalarType), dofs, V))
            elif bc["type"] == "displacement":
                facets = np.where(np.isin(cell_tags.values, bc["face_tags"]))[0] if bc["face_tags"] else np.array([], dtype=np.int32)
                if len(facets) > 0:
                    dofs = dolfinx.fem.locate_dofs_topological(V, domain.topology.dim - 1, facets)
                    bcs.append(dirichletbc(np.array([bc.get("ux", 0), bc.get("uy", 0), bc.get("uz", 0)], dtype=PETSc.ScalarType), dofs, V))

        F_expr = dolfinx.fem.Constant(domain, np.zeros(3, dtype=PETSc.ScalarType))
        for load in LOADS:
            if load["type"] == "force":
                facets = np.where(np.isin(cell_tags.values, load["face_tags"]))[0] if load["face_tags"] else np.array([], dtype=np.int32)
                if len(facets) > 0:
                    existing = F_expr.value.copy()
                    existing += np.array([0, 0, load["value"]], dtype=PETSc.ScalarType)
                    F_expr.value = existing

        a = inner(sigma(u), grad(v)) * ufl.dx
        L = dot(F_expr, v) * ufl.dx

        problem = LinearProblem(a, L, bcs=bcs, petsc_options={{"ksp_type": "preonly", "pc_type": "lu"}})
        u_sol = problem.solve()

        disp_arr = u_sol.x.array.reshape(-1, 3)
        u_magnitude = np.linalg.norm(disp_arr, axis=1)

        stress_expr = sigma(u_sol)
        V_s = FunctionSpace(domain, ("Lagrange", 0))
        sigma_val = Function(V_s)
        sigma_val.interpolate(lambda x: np.zeros((9, x.shape[1]), dtype=PETSc.ScalarType))
        von_mises_expr = von_mises(stress_expr)
        von_mises_fn = Function(V_s)
        von_mises_fn.interpolate(von_mises_expr)

        vm_arr = von_mises_fn.x.array
        max_stress = float(np.max(vm_arr)) if len(vm_arr) > 0 else 0.0
        max_disp = float(np.max(u_magnitude)) if len(u_magnitude) > 0 else 0.0

        result = {{
            "max_vonmises_stress": max_stress,
            "max_displacement": max_disp,
            "displacements": u_magnitude.tolist(),
            "stresses": vm_arr.tolist() if len(vm_arr) > 0 else [],
            "warnings": [],
            "errors": []
        }}

    elif ANALYSIS_TYPE == "modal":
        V = VectorFunctionSpace(domain, ("Lagrange", 1))
        u = TrialFunction(V)
        v = TestFunction(V)

        k = dolfinx.fem.Constant(domain, PETSc.ScalarType(0))
        mass_form = rho * dot(u, v) * ufl.dx
        stiffness_form = inner(sigma(u), grad(v)) * ufl.dx

        M = dolfinx.fem.assemble_matrix(form(mass_form))
        K = dolfinx.fem.assemble_matrix(form(stiffness_form))
        M.assemble()
        K.assemble()

        from slepc4py import SLEPc
        Eps = SLEPc.EPS().create()
        Eps.setOperators(K, M)
        Eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
        Eps.setDimensions(10, SLEPc.DECIDE)
        Eps.setTolerances(max_it=1000)
        Eps.solve()

        nconv = Eps.getConverged()
        frequencies = []
        mode_shapes = []
        for i in range(min(nconv, 10)):
            vr, wr = K.getVecs()
            wi = Eps.getEigenpair(i, vr, wr)
            freq = np.sqrt(abs(wr)) / (2 * np.pi)
            frequencies.append(float(freq))
            mode_shapes.append(vr.array.reshape(-1, 3).tolist())

        result = {{
            "frequencies": frequencies,
            "mode_shapes": mode_shapes,
            "warnings": [],
            "errors": []
        }}

    elif ANALYSIS_TYPE == "thermal":
        V = FunctionSpace(domain, ("Lagrange", 1))
        u = Function(V)
        v = TestFunction(V)

        k = dolfinx.fem.Constant(domain, PETSc.ScalarType(material_props.get("k", 205.0)))
        rho_c = dolfinx.fem.Constant(domain, PETSc.ScalarType(material_props.get("rho_c", 7900 * 500)))
        Q = dolfinx.fem.Constant(domain, PETSc.ScalarType(0))

        a = k * dot(grad(u), grad(v)) * ufl.dx + rho_c * u * v * ufl.dx
        L = Q * v * ufl.dx

        bcs = []
        for bc in BOUNDARY_CONDITIONS:
            if bc["type"] == "fixed":
                facets = np.where(np.isin(cell_tags.values, bc["face_tags"]))[0] if bc["face_tags"] else np.array([], dtype=np.int32)
                if len(facets) > 0:
                    dofs = dolfinx.fem.locate_dofs_topological(V, domain.topology.dim - 1, facets)
                    bcs.append(dirichletbc(dolfinx.fem.Constant(domain, PETSc.ScalarType(bc.get("temperature", 0))), dofs, V))

        problem = LinearProblem(a, L, bcs=bcs, petsc_options={{"ksp_type": "preonly", "pc_type": "lu"}})
        T = problem.solve()

        result = {{
            "temperatures": T.x.array.tolist(),
            "warnings": [],
            "errors": []
        }}

    print("FEM_RESULT:" + json.dumps(result))

except Exception as e:
    import traceback
    print("FEM_ERROR:" + json.dumps({{"error": str(e), "trace": traceback.format_exc()}}))
"""


def _run_linear_static(mesh_path: str, material_props: dict,
                       boundary_conditions: list, loads: list) -> dict:
    return _run_fenicsx_analysis(mesh_path, material_props, boundary_conditions, loads, "linear_static")


def _run_modal(mesh_path: str, material_props: dict, boundary_conditions: list) -> dict:
    return _run_fenicsx_analysis(mesh_path, material_props, boundary_conditions, [], "modal")


def _run_thermal(mesh_path: str, material_props: dict,
                 boundary_conditions: list, loads: list) -> dict:
    return _run_fenicsx_analysis(mesh_path, material_props, boundary_conditions, loads, "thermal")


def _run_fenicsx_analysis(mesh_path: str, material_props: dict,
                          boundary_conditions: list, loads: list,
                          analysis_type: str) -> dict:
    script = _build_fenicsx_script(mesh_path, material_props, boundary_conditions, loads, analysis_type)

    script_path = Path(tempfile.gettempdir()) / f"fenicsx_{analysis_type}_{id(script)}.py"
    script_path.write_text(script)

    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": "/usr/local/lib/python3.11/site-packages",
    }

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=600,
            env=env
        )
    finally:
        script_path.unlink(missing_ok=True)

    for line in (proc.stdout or "").splitlines():
        if line.startswith("FEM_RESULT:"):
            return json.loads(line[len("FEM_RESULT:"):])
        if line.startswith("FEM_ERROR:"):
            err = json.loads(line[len("FEM_ERROR:"):])
            raise RuntimeError(f"FEniCSx error: {err.get('error', 'unknown')}")

    if proc.returncode != 0:
        stderr = proc.stderr or ""
        if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
            raise RuntimeError(f"FEniCSx not installed: {stderr[:500]}")
        raise RuntimeError(f"FEniCSx failed (code {proc.returncode}): {stderr[:1000]}")

    raise RuntimeError("FEniCSx produced no result")
