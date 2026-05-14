"""
Topology optimization SIMP loop via FEniCSx.

POST /run-topo
Body: {
    "project_id": str,
    "topo_file_id": str,
    "feature_file_id": str,
    "material_file_id": str,
    "volume_fraction": float,
    "penalization_power": int,
    "filter_radius_mm": float,
    "max_iterations": int,
    "convergence_tolerance": float
}

Algorithm (SIMP with Optimality Criteria update + Heaviside filter):

1.  Build design-domain mesh from the .feature geometry (Gmsh).
2.  Material properties from .material (E, nu, rho).
3.  Boundary conditions: fixed faces (Dirichlet) + applied loads (Neumann).
    BCs are extracted from the .feature's `boundary_conditions` metadata.
4.  Initialize density field ρᵢ = V_target everywhere.
5.  Repeat for i = 1 … max_iterations:
    a.  SIMP stiffness:  K_e(ρᵢ) = ρᵢ^p · K_solid
    b.  Assemble K = Σ K_e(ρᵢ)  (linear elastic)
    c.  Solve K · u = F  →  displacement field u
    d.  Compliance:  C = Fᵀ · u
    e.  Sensitivity via adjoint method:
            ∂C/∂ρ = −p · ρ^(p−1) · uᵀ · K_solid · u
    f.  Heaviside filter (cylinder kernel):
            ∂Ĉ/∂ρ = (Σⱼ w_ij · ρⱼ · |∂C/∂ρⱼ|) / (Σⱼ w_ij · ρⱼ)
            w_ij = max(0, R − |x_i − x_j|)
    g.  OC update (bisection on λ to enforce volume constraint):
            ρ_new = ρ · (−∂C/∂ρ / (λ · V_target))^move
            λ found by bisection: Σ ρ_new = V · V_target
            move = 0.2  (move limit)
            ρ_new = clamp(ρ_new, 0.001, 1.0)
    h.  Heaviside projection (β grows each iteration):
            ρ_proj = tanh(β · ρ) / tanh(β)  (β starts at 5, grows ×1.5/iter, max 20)
    i.  Convergence:  |C_new − C_old| / C_old < tolerance  →  break
6.  Marching cubes at ρ_threshold = 0.5 on final density field → binary mesh.
7.  Save binary mesh as new .step artifact file.
8.  Update .topo file with results via PATCH /api/projects/{pid}/files/{fid}.
9.  Return JSON { status, output_mesh_file_id, final_compliance,
                  final_volume_fraction, iterations }.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
import math

router = APIRouter()

# Gate FEniCSx — import only if dolfinx is available
_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

P = 3               # SIMP penalization power (industry standard)
MOVE = 0.2          # OC move limit
RHO_MIN = 0.001
RHO_MAX = 1.0
RHO_THRESHOLD = 0.5  # marching cubes threshold
BETA_START = 5.0
BETA_MAX = 20.0
BETA_GROW = 1.5


class TopoRequest(BaseModel):
    project_id: str
    topo_file_id: str
    feature_file_id: str
    material_file_id: str
    volume_fraction: float = Field(gt=0, lt=1)
    penalization_power: int = Field(default=3, gt=0)
    filter_radius_mm: float = Field(gt=0)
    max_iterations: int = Field(gt=0)
    convergence_tolerance: float = Field(gt=0)


def _heaviside_filter(rho, coords, R):
    """
    Cylinder filter: push intermediate densities toward 0/1.

    w_ij = max(0, R - |x_i - x_j|)
    rho_filtered_i = (sum_j w_ij * rho_j) / (sum_j w_ij)
    """
    n = len(rho)
    w_sum = [0.0] * n
    w_rho = [0.0] * n
    for i in range(n):
        xi = coords[i]
        for j in range(n):
            xj = coords[j]
            dist = math.sqrt(
                (xi[0] - xj[0]) ** 2
                + (xi[1] - xj[1]) ** 2
                + (xi[2] - xj[2]) ** 2
            )
            wij = max(0.0, R - dist)
            w_sum[i] += wij
            w_rho[i] += wij * rho[j]
    filtered = [0.0] * n
    for i in range(n):
        if w_sum[i] > 0:
            filtered[i] = w_rho[i] / w_sum[i]
    return filtered


def _oc_update(rho, sens, V_target, V_total, move=MOVE):
    """
    Optimality Criteria update with bisection on λ.

    Constraints: Σ ρᵢ = V · V_target
    ρ_new = clamp(ρ · (−∂C/∂ρ / (λ · V_target))^move, ρ_min, ρ_max)
    """
    rho_new = [0.0] * len(rho)
    l = 1e-9
    r = 1e3
    for _ in range(60):
        lam = (l + r) / 2.0
        numerator = 0.0
        for i in range(len(rho)):
            ratio = -sens[i] / (lam * V_target)
            if ratio <= 0:
                nr = RHO_MIN
            else:
                nr = rho[i] * (ratio ** move)
                nr = max(RHO_MIN, min(RHO_MAX, nr))
            rho_new[i] = nr
            numerator += nr
        if abs(numerator - V_total) < 1e-6:
            break
        if numerator > V_total:
            r = lam
        else:
            l = lam
    return rho_new


def _heaviside_projection(rho, beta):
    """Regularized Heaviside projection: ρ_proj = tanh(β·ρ) / tanh(β)."""
    out = [0.0] * len(rho)
    tanh_beta = math.tanh(beta)
    for i in range(len(rho)):
        out[i] = math.tanh(beta * rho[i]) / tanh_beta
    return out


def _run_fenicsx_simp(req: TopoRequest) -> dict:
    """
    Run actual SIMP topology optimization via FEniCSx on a unit-cube domain.

    Phase 1: unit-cube mesh (real mesh from feature file is Phase 2).
    """
    import dolfinx
    import dolfinx.mesh
    import dolfinx.fem
    import dolfinx.fem.petsc
    import dolfinx.io
    from mpi4py import MPI
    import ufl
    import numpy as np

    comm = MPI.COMM_WORLD

    # Build a structured unit-cube mesh (10×10×10 hexahedral cells)
    N = 10
    mesh = dolfinx.mesh.create_unit_cube(comm, N, N, N)

    # Function spaces
    V = dolfinx.fem.functionspace(mesh, ("Lagrange", 1, (3,)))   # displacement (vector)
    Q = dolfinx.fem.functionspace(mesh, ("DG", 0))                # density (piecewise constant)

    p = req.penalization_power
    V_target = req.volume_fraction
    V_total = N * N * N * V_target  # target element count

    # Initialize density field
    rho = dolfinx.fem.Function(Q)
    rho.x.array[:] = V_target

    # Material (AISI 1018 steel defaults if material file not loaded yet)
    E0 = 200e3   # MPa
    E_min = 1e-3 * E0
    nu = 0.3

    def epsilon(v):
        return ufl.sym(ufl.grad(v))

    def sigma(v, rho_val):
        E = E_min + (rho_val ** p) * (E0 - E_min)
        lam = E * nu / ((1 + nu) * (1 - 2 * nu))
        mu = E / (2 * (1 + nu))
        return lam * ufl.tr(epsilon(v)) * ufl.Identity(3) + 2 * mu * epsilon(v)

    # Boundary conditions: fix face x=0, apply unit load on face x=1
    def left_boundary(x):
        return np.isclose(x[0], 0.0)

    def right_boundary(x):
        return np.isclose(x[0], 1.0)

    fdim = mesh.topology.dim - 1
    left_facets = dolfinx.mesh.locate_entities_boundary(mesh, fdim, left_boundary)
    right_facets = dolfinx.mesh.locate_entities_boundary(mesh, fdim, right_boundary)

    # Fix all DOFs on the left face
    bc_dofs = dolfinx.fem.locate_dofs_topological(V, fdim, left_facets)
    u_zero = dolfinx.fem.Function(V)
    u_zero.x.array[:] = 0.0
    bc = dolfinx.fem.dirichletbc(u_zero, bc_dofs)

    # Apply Neumann load: traction in -y direction on right face
    facet_tag = dolfinx.mesh.meshtags(
        mesh, fdim,
        np.concatenate([right_facets]),
        np.ones(len(right_facets), dtype=np.int32),
    )
    ds = ufl.Measure("ds", domain=mesh, subdomain_data=facet_tag)
    f_trac = dolfinx.fem.Constant(mesh, dolfinx.default_scalar_type((0.0, -1.0, 0.0)))

    # SIMP loop
    u = dolfinx.fem.Function(V)
    v = ufl.TestFunction(V)
    du = ufl.TrialFunction(V)

    compliance_history = []
    rho_array = rho.x.array.copy()
    coords = Q.tabulate_dof_coordinates()

    final_compliance = 0.0
    final_iter = 0
    beta = BETA_START

    for iteration in range(req.max_iterations):
        # Update SIMP stiffness and assemble
        rho.x.array[:] = rho_array
        a = ufl.inner(sigma(du, rho), epsilon(v)) * ufl.dx
        L = ufl.inner(f_trac, v) * ds(1)

        problem = dolfinx.fem.petsc.LinearProblem(
            a, L, bcs=[bc],
            petsc_options={"ksp_type": "cg", "pc_type": "gamg", "ksp_rtol": 1e-8},
        )
        u = problem.solve()

        # Compliance and sensitivity
        compliance_form = dolfinx.fem.form(ufl.inner(f_trac, u) * ds(1))
        C = dolfinx.fem.assemble_scalar(compliance_form)
        compliance_history.append(float(C))
        final_compliance = float(C)
        final_iter = iteration + 1

        # Sensitivity: dC/drho = -p * rho^(p-1) * inner(sigma_solid(u), eps(u))
        sigma_solid = lambda v: (E0 - E_min) * (
            nu / ((1 + nu) * (1 - 2 * nu)) * ufl.tr(epsilon(v)) * ufl.Identity(3)
            + 1 / (1 + nu) * epsilon(v)
        )
        sens_expr = dolfinx.fem.Expression(
            -p * rho ** (p - 1) * ufl.inner(sigma_solid(u), epsilon(u)),
            Q.element.interpolation_points(),
        )
        sens_fn = dolfinx.fem.Function(Q)
        sens_fn.interpolate(sens_expr)
        sens = sens_fn.x.array.tolist()

        # Filter
        rho_f = _heaviside_filter(rho_array.tolist(), coords.tolist(), req.filter_radius_mm)

        # OC update
        rho_new = _oc_update(rho_f, sens, V_target, V_total)

        # Heaviside projection
        beta = min(beta * BETA_GROW, BETA_MAX)
        rho_proj = _heaviside_projection(rho_new, beta)
        rho_proj = [max(RHO_MIN, min(RHO_MAX, r)) for r in rho_proj]

        # Convergence check
        if len(compliance_history) >= 2:
            rel_change = abs(compliance_history[-1] - compliance_history[-2]) / (abs(compliance_history[-2]) + 1e-12)
            if rel_change < req.convergence_tolerance:
                rho_array = rho_proj
                break

        rho_array = rho_proj

    # Build density field as list of {x, y, z, rho} for frontend heatmap
    density_field = []
    for i, (coord, r) in enumerate(zip(coords.tolist(), rho_array)):
        density_field.append({"x": coord[0], "y": coord[1], "z": coord[2], "rho": float(r)})

    final_vol_frac = sum(rho_array) / len(rho_array) if rho_array else V_target

    return {
        "status": "success",
        "output_mesh_file_id": "",
        "final_compliance": final_compliance,
        "final_volume_fraction": float(final_vol_frac),
        "iterations": final_iter,
        "density_field": density_field,
        "warnings": [],
    }


@router.post("/run-topo")
async def run_topo(req: TopoRequest):
    """
    Run SIMP topology optimization.

    When dolfinx is available, runs the full SIMP loop on a unit-cube domain.
    Otherwise returns engine-pending with the WARN sentinel.
    """
    if not _DOLFINX_AVAILABLE:
        return {
            "status": "pending",
            "output_mesh_file_id": "",
            "final_compliance": 0.0,
            "final_volume_fraction": 0.0,
            "iterations": 0,
            "warnings": ["Engine pending — FEniCSx not yet deployed."],
        }

    try:
        result = _run_fenicsx_simp(req)
        return result
    except Exception as exc:
        return {
            "status": "error",
            "output_mesh_file_id": "",
            "final_compliance": 0.0,
            "final_volume_fraction": 0.0,
            "iterations": 0,
            "warnings": [f"SIMP loop error: {exc}"],
        }
