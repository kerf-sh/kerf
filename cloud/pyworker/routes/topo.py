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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import json
import math
import tempfile
import os

app = FastAPI()

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


def _simp_iteration(rho, coords, R, p, V_target, V_total, u, K_solid, F):
    """
    One SIMP iteration: filter → sensitivity → OC update → Heaviside projection.
    Returns (rho_new, compliance, converged).
    """
    rho_f = _heaviside_filter(rho, coords, R)

    sens = []
    for i in range(len(rho_f)):
        sens.append(-p * (rho_f[i] ** (p - 1)) * u[i] * K_solid * u[i])

    rho_new = _oc_update(rho_f, sens, V_target, V_total)

    beta = BETA_START
    rho_proj = _heaviside_projection(rho_new, beta)
    for i in range(len(rho_proj)):
        rho_proj[i] = max(RHO_MIN, min(RHO_MAX, rho_proj[i]))

    C = sum(F[i] * u[i] for i in range(len(u)))
    return rho_proj, C, False


@app.post("/run-topo")
async def run_topo(req: TopoRequest):
    """
    Run SIMP topology optimization.

    This is a stub that returns engine-pending until FEniCSx is deployed.
    When FEniCSx lands, replace the stub with the actual SIMP loop.
    """
    return {
        "status": "pending",
        "output_mesh_file_id": "",
        "final_compliance": 0.0,
        "final_volume_fraction": 0.0,
        "iterations": 0,
        "warnings": ["Engine pending — FEniCSx not yet deployed."],
    }