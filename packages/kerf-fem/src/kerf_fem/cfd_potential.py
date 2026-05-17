"""
2-D incompressible, inviscid potential flow on a structured Cartesian grid.

Formulation
-----------
For irrotational, incompressible flow the velocity field admits a scalar
velocity potential φ with  u = ∂φ/∂x,  v = ∂φ/∂y,  satisfying the Laplace
equation

        Δφ = 0   on  Ω

with mixed Dirichlet / Neumann boundary conditions:

    Dirichlet:   φ = φ_b                on  Γ_D
    Neumann  :   ∂φ/∂n = U·n            on  Γ_N   (mass-flux specified)

The equivalent stream-function formulation uses

        Δψ = 0,    u = ∂ψ/∂y,  v = −∂ψ/∂x

so that streamlines are level-sets of ψ and ψ is constant on a solid body.
Either field may be solved here; the analytic helpers and tests use ψ for
flow-around-body problems (Dirichlet ψ on the body, ψ = U_∞ y on the far
field) and φ for source/sink/uniform flow superpositions.

Discretisation
--------------
Standard 5-point finite differences on a uniform rectangular grid of
(nx × ny) nodes spaced (dx, dy):

        (φ_{i+1,j} − 2φ_{i,j} + φ_{i-1,j}) / dx²
      + (φ_{i,j+1} − 2φ_{i,j} + φ_{i,j-1}) / dy² = 0

Boundary nodes are tagged by `mask`:
    0 = interior   (Laplace residual)
    1 = Dirichlet  (value fixed)
    2 = Neumann    (∂φ/∂n imposed; uses one-sided 2nd-order stencil)
    3 = solid body interior (φ fixed to body-constant, excluded from solve)

The linear system K·u = b is solved by Gauss-Seidel iteration with
successive over-relaxation (SOR, ω = 1.7 default). Convergence is declared
when the L∞-norm of the residual falls below `tol` (default 1e-7) or
when ‖Δu‖_∞ < tol · max(‖u‖_∞, 1).

Pressure recovery
-----------------
Once the velocity field is known, pressure follows from Bernoulli's
equation along a streamline (or globally for irrotational flow):

        p + ½ ρ V² = p_∞ + ½ ρ V_∞²

The dimensionless surface pressure coefficient is

        Cp = (p − p_∞) / (½ ρ V_∞²) = 1 − (V / V_∞)²

For uniform flow past a 2-D cylinder of radius R the exact analytic result
(Lamb, *Hydrodynamics* §69; Kundu & Cohen *Fluid Mechanics* §6.5) is

        Cp(θ) = 1 − 4 sin²θ

with stagnation points at θ = 0 and θ = π.

Scope / limits
--------------
- 2-D only; structured Cartesian grids only.
- Inviscid, incompressible, irrotational.  No vorticity, no boundary
  layers, no separation.  D'Alembert's paradox: drag is identically zero
  on closed bodies.
- Solid bodies are represented by stair-step boundary masks; curved walls
  alias to roughly O(h) accuracy.  Refine the grid for cleaner Cp.
- No turbulence model — that's the laminar Navier-Stokes module's
  responsibility (`cfd_navier_stokes.py`).

All routines are pure Python (no numpy/scipy).  They never raise; errors
are returned as {"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Grid construction helpers
# ---------------------------------------------------------------------------

def make_grid(
    nx: int,
    ny: int,
    x_range: tuple[float, float] = (0.0, 1.0),
    y_range: tuple[float, float] = (0.0, 1.0),
) -> dict[str, Any]:
    """
    Build a uniform Cartesian grid descriptor.

    Returns dict with:
        nx, ny      grid dimensions (node count)
        dx, dy      cell spacings
        x, y        coordinate arrays
        x_range, y_range  spatial extents
    """
    if nx < 3 or ny < 3:
        return {"ok": False, "reason": "nx and ny must each be >= 3"}
    x0, x1 = x_range
    y0, y1 = y_range
    if x1 <= x0 or y1 <= y0:
        return {"ok": False, "reason": "x_range / y_range must be increasing"}

    dx = (x1 - x0) / (nx - 1)
    dy = (y1 - y0) / (ny - 1)
    x = [x0 + i * dx for i in range(nx)]
    y = [y0 + j * dy for j in range(ny)]
    return {
        "ok": True,
        "nx": nx, "ny": ny,
        "dx": dx, "dy": dy,
        "x": x, "y": y,
        "x_range": (x0, x1),
        "y_range": (y0, y1),
    }


def _zeros2(nx: int, ny: int) -> list[list[float]]:
    return [[0.0] * ny for _ in range(nx)]


def _ints2(nx: int, ny: int, fill: int = 0) -> list[list[int]]:
    return [[fill] * ny for _ in range(nx)]


# ---------------------------------------------------------------------------
# Core Laplace SOR solver
# ---------------------------------------------------------------------------

def solve_laplace(
    grid: dict[str, Any],
    mask: list[list[int]],
    bc_value: list[list[float]],
    bc_neumann: list[list[float]] | None = None,
    omega: float = 1.7,
    tol: float = 1.0e-7,
    max_iter: int = 20000,
    initial: list[list[float]] | None = None,
) -> dict[str, Any]:
    """
    Solve Δφ = 0 on a structured grid via Gauss-Seidel + SOR.

    Parameters
    ----------
    grid       : output of `make_grid`
    mask[i][j] : node tag — 0 interior, 1 Dirichlet, 2 Neumann, 3 solid-interior
    bc_value   : nx×ny array; Dirichlet value at mask==1 or 3 nodes
    bc_neumann : nx×ny array; ∂φ/∂n value at mask==2 nodes
                 (n is the outward grid-aligned normal; for Neumann on the
                  left wall n=-x̂, on the right n=+x̂, similarly y.)
    omega      : SOR relaxation factor in (1, 2); 1.0 = pure Gauss-Seidel
    tol        : convergence tolerance on max |Δφ| between iterations
    max_iter   : iteration cap

    Returns
    -------
    dict with:
        ok          bool
        phi         nx×ny array
        iters       iterations used
        residual    final L∞-residual
        converged   bool
    """
    if not grid.get("ok", False):
        return {"ok": False, "reason": "invalid grid"}
    nx = grid["nx"]; ny = grid["ny"]
    dx = grid["dx"]; dy = grid["dy"]
    if omega <= 0 or omega >= 2:
        return {"ok": False, "reason": "omega must be in (0, 2)"}

    inv_dx2 = 1.0 / (dx * dx)
    inv_dy2 = 1.0 / (dy * dy)
    denom = 2.0 * (inv_dx2 + inv_dy2)
    if denom < 1e-30:
        return {"ok": False, "reason": "degenerate grid spacing"}

    if bc_neumann is None:
        bc_neumann = _zeros2(nx, ny)

    # Validate shapes
    for arr, name in ((mask, "mask"), (bc_value, "bc_value"), (bc_neumann, "bc_neumann")):
        if len(arr) != nx or any(len(row) != ny for row in arr):
            return {"ok": False, "reason": f"{name} shape must be {nx}x{ny}"}

    # Initialise φ: Dirichlet values where prescribed, else 0 or supplied init
    if initial is not None:
        if len(initial) != nx or any(len(row) != ny for row in initial):
            return {"ok": False, "reason": "initial shape mismatch"}
        phi = [row[:] for row in initial]
    else:
        phi = _zeros2(nx, ny)

    for i in range(nx):
        for j in range(ny):
            m = mask[i][j]
            if m == 1 or m == 3:
                phi[i][j] = bc_value[i][j]

    iters = 0
    converged = False
    last_res = float("inf")

    for it in range(max_iter):
        max_delta = 0.0
        max_val = 1.0

        for i in range(nx):
            for j in range(ny):
                m = mask[i][j]
                if m == 1 or m == 3:
                    continue  # fixed values

                # Standard 5-point stencil with mirrored ghost for Neumann
                # boundary handling (one-sided 2nd-order: ghost node value
                # set so that the centred difference reproduces ∂φ/∂n).
                if i == 0:
                    phi_w = phi[1][j] - 2.0 * dx * (-bc_neumann[i][j] if m == 2 else 0.0)
                else:
                    phi_w = phi[i - 1][j]

                if i == nx - 1:
                    phi_e = phi[nx - 2][j] + 2.0 * dx * (bc_neumann[i][j] if m == 2 else 0.0)
                else:
                    phi_e = phi[i + 1][j]

                if j == 0:
                    phi_s = phi[i][1] - 2.0 * dy * (-bc_neumann[i][j] if m == 2 else 0.0)
                else:
                    phi_s = phi[i][j - 1]

                if j == ny - 1:
                    phi_n = phi[i][ny - 2] + 2.0 * dy * (bc_neumann[i][j] if m == 2 else 0.0)
                else:
                    phi_n = phi[i][j + 1]

                new_val = (
                    (phi_e + phi_w) * inv_dx2
                    + (phi_n + phi_s) * inv_dy2
                ) / denom

                old_val = phi[i][j]
                relaxed = old_val + omega * (new_val - old_val)
                delta = abs(relaxed - old_val)
                if delta > max_delta:
                    max_delta = delta
                av = abs(relaxed)
                if av > max_val:
                    max_val = av
                phi[i][j] = relaxed

        iters = it + 1
        last_res = max_delta
        if max_delta < tol * max_val:
            converged = True
            break

    return {
        "ok": True,
        "phi": phi,
        "iters": iters,
        "residual": last_res,
        "converged": converged,
    }


# ---------------------------------------------------------------------------
# Velocity and pressure recovery
# ---------------------------------------------------------------------------

def velocity_from_potential(
    grid: dict[str, Any],
    phi: list[list[float]],
) -> dict[str, Any]:
    """
    Recover velocity field from a velocity-potential field via central
    differences (one-sided at boundaries).

        u = ∂φ/∂x,    v = ∂φ/∂y
    """
    nx = grid["nx"]; ny = grid["ny"]
    dx = grid["dx"]; dy = grid["dy"]
    u = _zeros2(nx, ny)
    v = _zeros2(nx, ny)

    for i in range(nx):
        for j in range(ny):
            if i == 0:
                u[i][j] = (phi[1][j] - phi[0][j]) / dx
            elif i == nx - 1:
                u[i][j] = (phi[nx - 1][j] - phi[nx - 2][j]) / dx
            else:
                u[i][j] = (phi[i + 1][j] - phi[i - 1][j]) / (2.0 * dx)

            if j == 0:
                v[i][j] = (phi[i][1] - phi[i][0]) / dy
            elif j == ny - 1:
                v[i][j] = (phi[i][ny - 1] - phi[i][ny - 2]) / dy
            else:
                v[i][j] = (phi[i][j + 1] - phi[i][j - 1]) / (2.0 * dy)

    return {"ok": True, "u": u, "v": v}


def velocity_from_streamfunction(
    grid: dict[str, Any],
    psi: list[list[float]],
) -> dict[str, Any]:
    """
    Recover velocity field from a stream-function field.

        u =  ∂ψ/∂y,    v = −∂ψ/∂x
    """
    nx = grid["nx"]; ny = grid["ny"]
    dx = grid["dx"]; dy = grid["dy"]
    u = _zeros2(nx, ny)
    v = _zeros2(nx, ny)

    for i in range(nx):
        for j in range(ny):
            if j == 0:
                u[i][j] = (psi[i][1] - psi[i][0]) / dy
            elif j == ny - 1:
                u[i][j] = (psi[i][ny - 1] - psi[i][ny - 2]) / dy
            else:
                u[i][j] = (psi[i][j + 1] - psi[i][j - 1]) / (2.0 * dy)

            if i == 0:
                v[i][j] = -(psi[1][j] - psi[0][j]) / dx
            elif i == nx - 1:
                v[i][j] = -(psi[nx - 1][j] - psi[nx - 2][j]) / dx
            else:
                v[i][j] = -(psi[i + 1][j] - psi[i - 1][j]) / (2.0 * dx)

    return {"ok": True, "u": u, "v": v}


def pressure_bernoulli(
    u: list[list[float]],
    v: list[list[float]],
    v_inf: float,
    rho: float = 1.0,
    p_inf: float = 0.0,
) -> dict[str, Any]:
    """
    Apply Bernoulli's equation pointwise:

        p(x,y) = p_∞ + ½ ρ (V_∞² − V²)

    Returns p and Cp = (p−p_∞)/(½ρV_∞²) = 1 − (V/V_∞)².
    """
    if abs(v_inf) < 1e-14:
        return {"ok": False, "reason": "v_inf must be non-zero"}
    nx = len(u); ny = len(u[0]) if nx > 0 else 0
    p = _zeros2(nx, ny)
    Cp = _zeros2(nx, ny)
    half_rho_v2_inf = 0.5 * rho * v_inf * v_inf
    for i in range(nx):
        for j in range(ny):
            V2 = u[i][j] * u[i][j] + v[i][j] * v[i][j]
            p[i][j] = p_inf + 0.5 * rho * (v_inf * v_inf - V2)
            Cp[i][j] = 1.0 - V2 / (v_inf * v_inf)
    return {"ok": True, "p": p, "Cp": Cp, "q_inf": half_rho_v2_inf}


# ---------------------------------------------------------------------------
# Analytic test problems
# ---------------------------------------------------------------------------

def uniform_flow(
    nx: int = 41, ny: int = 41,
    v_inf: float = 1.0,
    x_range: tuple[float, float] = (0.0, 1.0),
    y_range: tuple[float, float] = (0.0, 1.0),
) -> dict[str, Any]:
    """
    Set up and solve a uniform-flow potential problem with linear φ = V_∞ x.

    Used as a self-consistency check: the solver must reproduce φ_exact
    exactly (up to round-off) when Dirichlet boundary values match the
    analytic field on all four edges.
    """
    grid = make_grid(nx, ny, x_range, y_range)
    if not grid["ok"]:
        return grid

    mask = _ints2(nx, ny, 0)
    bc_value = _zeros2(nx, ny)
    for i in range(nx):
        for j in range(ny):
            if i == 0 or i == nx - 1 or j == 0 or j == ny - 1:
                mask[i][j] = 1
                bc_value[i][j] = v_inf * grid["x"][i]

    sol = solve_laplace(grid, mask, bc_value, tol=1e-10)
    if not sol["ok"]:
        return sol

    phi = sol["phi"]
    vel = velocity_from_potential(grid, phi)
    return {
        "ok": True,
        "grid": grid,
        "phi": phi,
        "u": vel["u"],
        "v": vel["v"],
        "iters": sol["iters"],
        "converged": sol["converged"],
    }


def cylinder_streamfunction(
    R: float = 0.2,
    v_inf: float = 1.0,
    domain_half: float = 1.0,
    nx: int = 81,
    ny: int = 81,
    tol: float = 1e-7,
    max_iter: int = 30000,
) -> dict[str, Any]:
    """
    Uniform flow over a 2-D circular cylinder, stream-function formulation.

    Analytic solution (Lamb §69):

        ψ(r, θ) = V_∞ y (1 − R² / r²)

    enforced as Dirichlet values on the entire outer rectangle and on the
    cylinder boundary (ψ = 0 on the body).  The numerical solution should
    reproduce ψ — and hence the surface Cp(θ) = 1 − 4 sin²θ — to better
    than ~5 % on a moderate (81×81) grid with stair-step body mask.

    Reference: Lamb H., *Hydrodynamics* (6th ed., 1932), Article 69, p. 75;
    Kundu P. & Cohen I., *Fluid Mechanics* (4th ed., 2008), §6.5.

    Returns
    -------
    dict with ok, grid, psi, u, v, cylinder_mask, plus arrays of surface
    points and Cp values:
        theta_surf  list[float]    angle around cylinder (rad)
        Cp_surf     list[float]    numerical Cp(θ) at sampled angles
        Cp_exact    list[float]    1 − 4 sin²(θ)
    """
    if R <= 0 or R >= domain_half:
        return {"ok": False, "reason": "need 0 < R < domain_half"}

    grid = make_grid(nx, ny, (-domain_half, domain_half), (-domain_half, domain_half))
    if not grid["ok"]:
        return grid

    x = grid["x"]; y = grid["y"]
    mask = _ints2(nx, ny, 0)
    bc_value = _zeros2(nx, ny)

    # Solid-interior nodes: ψ = 0
    for i in range(nx):
        for j in range(ny):
            r = math.hypot(x[i], y[j])
            if r <= R:
                mask[i][j] = 3
                bc_value[i][j] = 0.0

    # Outer Dirichlet: ψ_exact = V_∞ y (1 − R²/r²); fall back to V_∞ y far field
    for i in range(nx):
        for j in range(ny):
            if i == 0 or i == nx - 1 or j == 0 or j == ny - 1:
                if mask[i][j] != 3:
                    r = math.hypot(x[i], y[j])
                    if r < 1e-12:
                        psi_b = 0.0
                    else:
                        psi_b = v_inf * y[j] * (1.0 - (R * R) / (r * r))
                    mask[i][j] = 1
                    bc_value[i][j] = psi_b

    # Initial guess: uniform flow ψ = V_∞ y outside body
    initial = _zeros2(nx, ny)
    for i in range(nx):
        for j in range(ny):
            if mask[i][j] != 3:
                initial[i][j] = v_inf * y[j]

    sol = solve_laplace(
        grid, mask, bc_value,
        omega=1.85, tol=tol, max_iter=max_iter, initial=initial,
    )
    if not sol["ok"]:
        return sol

    psi = sol["phi"]
    vel = velocity_from_streamfunction(grid, psi)

    # Sample Cp on a circle of radius r_sample > R.  We compare the
    # numerical Cp against the analytic Cp at the SAME r_sample (not at
    # r=R, where the formula 1−4sin²θ is exact only on the body surface).
    #
    # Exact velocity field for uniform flow past a cylinder:
    #     V_r(r,θ) = V_∞ cosθ (1 − R²/r²)
    #     V_θ(r,θ) = −V_∞ sinθ (1 + R²/r²)
    # so  Cp_exact(r,θ) = 1 − (V_r² + V_θ²) / V_∞².
    # At r = R this collapses to Cp = 1 − 4 sin²θ.
    dx = grid["dx"]; dy = grid["dy"]
    r_sample = R + 2.0 * max(dx, dy)
    n_theta = 36
    thetas: list[float] = []
    Cp_surf: list[float] = []
    Cp_exact_r: list[float] = []
    Cp_exact_surface: list[float] = []
    for k in range(n_theta):
        theta = 2.0 * math.pi * k / n_theta
        thetas.append(theta)
        xs = r_sample * math.cos(theta)
        ys = r_sample * math.sin(theta)
        ui = (xs - x[0]) / dx
        vj = (ys - y[0]) / dy
        i0 = max(0, min(nx - 2, int(math.floor(ui))))
        j0 = max(0, min(ny - 2, int(math.floor(vj))))
        a = ui - i0; b = vj - j0
        uu = (
            (1 - a) * (1 - b) * vel["u"][i0][j0]
            + a * (1 - b) * vel["u"][i0 + 1][j0]
            + (1 - a) * b * vel["u"][i0][j0 + 1]
            + a * b * vel["u"][i0 + 1][j0 + 1]
        )
        vv = (
            (1 - a) * (1 - b) * vel["v"][i0][j0]
            + a * (1 - b) * vel["v"][i0 + 1][j0]
            + (1 - a) * b * vel["v"][i0][j0 + 1]
            + a * b * vel["v"][i0 + 1][j0 + 1]
        )
        V2_num = uu * uu + vv * vv
        Cp_surf.append(1.0 - V2_num / (v_inf * v_inf))

        # Analytic Cp at r_sample, θ
        rs = r_sample
        R2_over_r2 = (R * R) / (rs * rs)
        Vr_ex = v_inf * math.cos(theta) * (1.0 - R2_over_r2)
        Vt_ex = -v_inf * math.sin(theta) * (1.0 + R2_over_r2)
        V2_ex = Vr_ex * Vr_ex + Vt_ex * Vt_ex
        Cp_exact_r.append(1.0 - V2_ex / (v_inf * v_inf))

        # Analytic Cp on body surface r=R (textbook result)
        Cp_exact_surface.append(1.0 - 4.0 * math.sin(theta) ** 2)

    return {
        "ok": True,
        "grid": grid,
        "psi": psi,
        "u": vel["u"],
        "v": vel["v"],
        "iters": sol["iters"],
        "converged": sol["converged"],
        "theta_surf": thetas,
        "Cp_surf": Cp_surf,
        "Cp_exact": Cp_exact_r,
        "Cp_exact_surface": Cp_exact_surface,
        "r_sample": r_sample,
        "R": R,
        "v_inf": v_inf,
    }


def cylinder_Cp_analytic(theta: float) -> float:
    """
    Exact surface pressure coefficient for uniform flow over a 2-D cylinder:

        Cp(θ) = 1 − 4 sin²θ

    Lamb, *Hydrodynamics* (6th ed.), Article 69.
    """
    s = math.sin(theta)
    return 1.0 - 4.0 * s * s


def cylinder_velocity_analytic(
    r: float, theta: float, R: float, v_inf: float = 1.0,
) -> tuple[float, float]:
    """
    Exact velocity field around a 2-D cylinder (uniform flow + doublet):

        V_r(r,θ) =  V_∞ cosθ (1 − R²/r²)
        V_θ(r,θ) = −V_∞ sinθ (1 + R²/r²)

    Returns the velocity in polar components (V_r, V_θ).  At r = R the
    radial component vanishes (no flow through the body), V_θ = −2 V_∞ sinθ,
    and Cp = 1 − 4 sin²θ.

    Reference: Kundu & Cohen *Fluid Mechanics* §6.5.
    """
    if r <= 0:
        return 0.0, 0.0
    R2r2 = (R * R) / (r * r)
    Vr = v_inf * math.cos(theta) * (1.0 - R2r2)
    Vt = -v_inf * math.sin(theta) * (1.0 + R2r2)
    return Vr, Vt


def cylinder_streamfunction_analytic(
    x: float, y: float, R: float, v_inf: float = 1.0,
) -> float:
    """
    Exact stream function for uniform flow past a 2-D cylinder:

        ψ(x,y) = V_∞ y (1 − R²/(x²+y²))

    ψ = 0 on the cylinder surface r = R.
    """
    r2 = x * x + y * y
    if r2 < 1e-30:
        return 0.0
    return v_inf * y * (1.0 - (R * R) / r2)


def doublet_stagnation_points() -> dict[str, Any]:
    """
    Front & rear stagnation points of uniform flow + doublet (the analytic
    flow past a 2-D cylinder).

    Stagnation occurs where the tangential surface velocity vanishes:
    V_θ(R, θ) = −2 V_∞ sin θ = 0  ⇒  θ = 0, π.

    Returns
    -------
    {"front": 0.0, "rear": math.pi}
    """
    return {"ok": True, "front": 0.0, "rear": math.pi}


# ---------------------------------------------------------------------------
# LLM tool registration (gated)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, register, ok_payload, err_payload
except ImportError:
    try:
        from kerf_fem._compat import ToolSpec, register, ok_payload, err_payload
    except ImportError:
        ToolSpec = register = ok_payload = err_payload = None


def _maybe_register():
    if ToolSpec is None or register is None:
        return

    import json

    spec = ToolSpec(
        name="cfd_potential_cylinder",
        description=(
            "2-D incompressible potential flow over a circular cylinder via "
            "stream-function FD on a structured Cartesian grid. Returns "
            "surface Cp(θ) and compares to the analytic 1 − 4 sin²θ."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "radius": {"type": "number", "description": "cylinder radius"},
                "v_inf":  {"type": "number", "description": "freestream speed"},
                "nx":     {"type": "integer"},
                "ny":     {"type": "integer"},
            },
            "required": ["radius"],
        },
    )

    @register(spec)
    async def _run(ctx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as e:
            return err_payload(f"invalid args: {e}", "BAD_ARGS")
        R = float(a.get("radius", 0.2))
        v_inf = float(a.get("v_inf", 1.0))
        nx = int(a.get("nx", 81)); ny = int(a.get("ny", 81))
        result = cylinder_streamfunction(R=R, v_inf=v_inf, nx=nx, ny=ny)
        return ok_payload(result)


_maybe_register()
