"""
kerf_cad_core.fea.solver — pure-Python 1D/2D finite-element solver seed.

Provides two public solvers:

  solve_truss(nodes, elements, supports, loads)
      Assemble and solve a 2-D pin-jointed truss / bar network.
      Uses direct stiffness method; boundary conditions applied by
      row/column zeroing + diagonal penalty; solved via pure-Python
      Gaussian elimination (no numpy).

  solve_bar_plastic(length, area, E, sigma_y, H, force, steps)
      1-D uniaxial bar with bilinear isotropic-hardening plasticity.
      Newton-Raphson load stepping + return-mapping radial correction
      (reduces to 1-D: σ_trial − E × Δε_p = σ_y + H × α).

No external dependencies (no numpy / scipy).  All functions return plain
dicts and NEVER raise.

Units
-----
All inputs/outputs use consistent SI units:
  lengths  — metres (m)
  areas    — m²
  forces   — Newtons (N)
  stress   — Pascals (Pa)
  modulus  — Pascals (Pa)
  strain   — dimensionless

Data structures
---------------
nodes    : list of [x, y] pairs — node coordinates (m)
elements : list of [i, j] pairs — node index pairs (0-based)
supports : dict {node_index: {"ux": bool, "uy": bool}} — True = fixed DOF
loads    : dict {node_index: {"fx": float, "fy": float}} — applied forces (N)

References
----------
Cook, R.D. et al. "Concepts and Applications of Finite Element Analysis", 4th ed.
Crisfield, M.A. "Non-linear Finite Element Analysis of Solids and Structures", Vol.1.
de Souza Neto, E.A. et al. "Computational Methods for Plasticity", Wiley.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _matmul(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """Matrix multiplication A @ B for square n×n matrices."""
    n = len(A)
    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for k in range(n):
            if A[i][k] == 0.0:
                continue
            for j in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C


def _matvec(A: list[list[float]], x: list[float]) -> list[float]:
    """Matrix-vector product A @ x."""
    n = len(A)
    y = [0.0] * n
    for i in range(n):
        s = 0.0
        for j in range(n):
            s += A[i][j] * x[j]
        y[i] = s
    return y


def _gaussian_elimination(A: list[list[float]], b: list[float]) -> list[float] | None:
    """
    Solve A x = b via Gaussian elimination with partial pivoting.

    Returns the solution vector x, or None if the system is singular
    (pivot < _TOL_PIVOT).  A and b are modified in place (copies are
    made internally).
    """
    _TOL_PIVOT = 1e-30
    n = len(b)
    # Deep-copy A and b so callers keep their originals
    M = [row[:] for row in A]
    rhs = b[:]

    for col in range(n):
        # Find pivot
        pivot_row = col
        pivot_val = abs(M[col][col])
        for row in range(col + 1, n):
            if abs(M[row][col]) > pivot_val:
                pivot_val = abs(M[row][col])
                pivot_row = row

        if pivot_val < _TOL_PIVOT:
            return None  # singular

        # Swap rows
        if pivot_row != col:
            M[col], M[pivot_row] = M[pivot_row], M[col]
            rhs[col], rhs[pivot_row] = rhs[pivot_row], rhs[col]

        # Eliminate below
        inv_pivot = 1.0 / M[col][col]
        for row in range(col + 1, n):
            factor = M[row][col] * inv_pivot
            if factor == 0.0:
                continue
            for j in range(col, n):
                M[row][j] -= factor * M[col][j]
            rhs[row] -= factor * rhs[col]

    # Back substitution
    x = [0.0] * n
    for row in range(n - 1, -1, -1):
        s = rhs[row]
        for j in range(row + 1, n):
            s -= M[row][j] * x[j]
        x[row] = s / M[row][row]

    return x


# ---------------------------------------------------------------------------
# 2-D truss element stiffness matrix
# ---------------------------------------------------------------------------

def _truss_element_stiffness(
    x1: float, y1: float, x2: float, y2: float, E: float, A: float
) -> tuple[list[list[float]], float, float, float]:
    """
    Return (k_local, c, s, L) for a 2-D bar/truss element.

    k_local is the 4×4 global-frame stiffness contribution:
        k = (EA/L) * [[c², cs, -c², -cs],
                       [cs, s², -cs, -s²],
                       [-c²,-cs, c²,  cs],
                       [-cs,-s²,  cs,  s²]]
    where c = cos(θ), s = sin(θ), θ = angle to x-axis.
    """
    dx = x2 - x1
    dy = y2 - y1
    L = math.sqrt(dx * dx + dy * dy)
    if L < 1e-30:
        # Zero-length element — return zero stiffness; handled as error upstream
        return [[0.0] * 4 for _ in range(4)], 0.0, 0.0, 0.0
    c = dx / L
    s = dy / L
    k = E * A / L
    # Trigonometric products
    cc = c * c
    ss = s * s
    cs = c * s
    ke = [
        [ k*cc,  k*cs, -k*cc, -k*cs],
        [ k*cs,  k*ss, -k*cs, -k*ss],
        [-k*cc, -k*cs,  k*cc,  k*cs],
        [-k*cs, -k*ss,  k*cs,  k*ss],
    ]
    return ke, c, s, L


# ---------------------------------------------------------------------------
# Public solver 1: 2-D linear truss
# ---------------------------------------------------------------------------

def solve_truss(
    nodes: list,
    elements: list,
    supports: dict,
    loads: dict,
    *,
    E: float = 200e9,
    A: float = 1e-4,
) -> dict:
    """
    Assemble and solve a 2-D pin-jointed linear elastic truss.

    Parameters
    ----------
    nodes : list of [x, y]
        Node coordinates in metres.  At least 2 nodes required.
    elements : list of [i, j]
        Pairs of node indices (0-based) defining each bar element.
        At least 1 element required.
    supports : dict
        {node_index: {"ux": bool, "uy": bool}}
        True marks that DOF as fixed (zero displacement).
        Enough supports to prevent rigid-body motion required for a
        non-singular system.
    loads : dict
        {node_index: {"fx": float, "fy": float}}
        Applied nodal forces in Newtons.  Nodes absent from this dict
        have zero applied force.
    E : float
        Young's modulus (Pa), default 200 GPa (steel).  Must be > 0.
        If all elements carry the same modulus this is the scalar to use.
        Per-element E is not yet supported.
    A : float
        Cross-sectional area (m²), default 1e-4 m².  Must be > 0.
        Per-element area is not yet supported.

    Returns
    -------
    dict
        ok               : True on success
        displacements    : list of [ux, uy] per node (m)
        reactions        : list of [rx, ry] per node (N); non-zero only
                           at supported DOFs
        element_forces   : list of axial force per element (N);
                           positive = tension
        element_stresses : list of axial stress per element (Pa)
        element_strains  : list of axial strain per element
        warnings         : list of warning strings (never raises)

    Errors returned as {"ok": False, "reason": "..."}.  Never raises.
    """
    warnings: list[str] = []

    # ----- Validate inputs --------------------------------------------------
    if not isinstance(nodes, (list, tuple)) or len(nodes) < 2:
        return _err("nodes must be a list of at least 2 [x, y] pairs")
    if not isinstance(elements, (list, tuple)) or len(elements) < 1:
        return _err("elements must be a list of at least 1 [i, j] pair")
    if not isinstance(supports, dict):
        return _err("supports must be a dict {node_index: {ux, uy}}")
    if not isinstance(loads, dict):
        return _err("loads must be a dict {node_index: {fx, fy}}")

    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("A", A)
    if err:
        return _err(err)

    n_nodes = len(nodes)
    n_dof = 2 * n_nodes  # 2 DOFs per node (ux, uy)

    # Validate node coordinates
    node_coords: list[tuple[float, float]] = []
    for idx, nd in enumerate(nodes):
        try:
            x, y = float(nd[0]), float(nd[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"nodes[{idx}] must be [x, y], got {nd!r}")
        if not (math.isfinite(x) and math.isfinite(y)):
            return _err(f"nodes[{idx}] coordinates must be finite")
        node_coords.append((x, y))

    # Validate elements
    elem_list: list[tuple[int, int]] = []
    for idx, el in enumerate(elements):
        try:
            i, j = int(el[0]), int(el[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"elements[{idx}] must be [i, j], got {el!r}")
        if not (0 <= i < n_nodes):
            return _err(f"elements[{idx}] node index i={i} out of range [0, {n_nodes-1}]")
        if not (0 <= j < n_nodes):
            return _err(f"elements[{idx}] node index j={j} out of range [0, {n_nodes-1}]")
        if i == j:
            return _err(f"elements[{idx}] degenerate: i == j == {i}")
        elem_list.append((i, j))

    # ----- Assemble global stiffness matrix K (n_dof × n_dof) ---------------
    K = [[0.0] * n_dof for _ in range(n_dof)]

    for el_idx, (ni, nj) in enumerate(elem_list):
        x1, y1 = node_coords[ni]
        x2, y2 = node_coords[nj]
        ke, c, s, L = _truss_element_stiffness(x1, y1, x2, y2, E, A)
        if L < 1e-30:
            warnings.append(
                f"elements[{el_idx}] has near-zero length ({L:.3e} m) — skipped"
            )
            continue
        # DOF mapping: node ni → [2*ni, 2*ni+1], node nj → [2*nj, 2*nj+1]
        dofs = [2*ni, 2*ni+1, 2*nj, 2*nj+1]
        for a in range(4):
            for b in range(4):
                K[dofs[a]][dofs[b]] += ke[a][b]

    # ----- Assemble load vector f -------------------------------------------
    f = [0.0] * n_dof
    for node_idx, fdict in loads.items():
        ni = int(node_idx)
        if not (0 <= ni < n_nodes):
            warnings.append(f"loads: node index {ni} out of range — ignored")
            continue
        fx = float(fdict.get("fx", 0.0))
        fy = float(fdict.get("fy", 0.0))
        f[2*ni]   += fx
        f[2*ni+1] += fy

    # ----- Apply boundary conditions (penalty / zeroing method) -------------
    # Fixed DOFs: zero out row and column, set diagonal to 1, rhs to 0.
    fixed_dofs: set[int] = set()
    for node_idx, sdict in supports.items():
        ni = int(node_idx)
        if not (0 <= ni < n_nodes):
            warnings.append(f"supports: node index {ni} out of range — ignored")
            continue
        if sdict.get("ux", False):
            fixed_dofs.add(2*ni)
        if sdict.get("uy", False):
            fixed_dofs.add(2*ni+1)

    if len(fixed_dofs) == 0:
        warnings.append(
            "No DOFs are fixed — system may be singular (rigid-body motion possible)"
        )

    # Zero-out rows and columns for fixed DOFs, set diagonal to 1, rhs to 0.
    # We work on a copy for the K_mod so we can compute reactions later.
    K_mod = [row[:] for row in K]
    f_mod = f[:]
    for dof in fixed_dofs:
        for j in range(n_dof):
            K_mod[dof][j] = 0.0
            K_mod[j][dof] = 0.0
        K_mod[dof][dof] = 1.0
        f_mod[dof] = 0.0

    # For free DOFs with zero diagonal (singularity from zero-stiffness direction,
    # e.g. uy for a fully horizontal bar), add a small penalty to stabilise the
    # system.  These DOFs will have zero force and near-zero displacement.
    _K_max = max(abs(K_mod[i][i]) for i in range(n_dof)) if n_dof > 0 else 1.0
    _penalty = _K_max * 1e-12 if _K_max > 0 else 1.0
    for dof in range(n_dof):
        if dof not in fixed_dofs and abs(K_mod[dof][dof]) < 1e-30:
            K_mod[dof][dof] = _penalty
            # leave f_mod[dof] as is (should be 0 or near-0 for a valid structure)

    # ----- Solve K_mod u = f_mod --------------------------------------------
    u = _gaussian_elimination(K_mod, f_mod)
    if u is None:
        return _err(
            "Global stiffness matrix is singular — check supports (rigid-body "
            "motion) or element connectivity"
        )

    # ----- Compute reactions = K_original @ u − f_applied ------------------
    Ku = _matvec(K, u)
    reactions_flat = [Ku[i] - f[i] for i in range(n_dof)]

    # ----- Compute element forces / stresses / strains ----------------------
    element_forces: list[float] = []
    element_stresses: list[float] = []
    element_strains: list[float] = []

    for ni, nj in elem_list:
        x1, y1 = node_coords[ni]
        x2, y2 = node_coords[nj]
        dx = x2 - x1
        dy = y2 - y1
        L = math.sqrt(dx * dx + dy * dy)
        if L < 1e-30:
            element_forces.append(0.0)
            element_stresses.append(0.0)
            element_strains.append(0.0)
            continue
        c = dx / L
        s = dy / L
        # Axial deformation: δ = c*(u_j_x - u_i_x) + s*(u_j_y - u_i_y)
        u_ix = u[2*ni]
        u_iy = u[2*ni+1]
        u_jx = u[2*nj]
        u_jy = u[2*nj+1]
        delta = c * (u_jx - u_ix) + s * (u_jy - u_iy)
        strain = delta / L
        stress = E * strain
        force = stress * A
        element_forces.append(force)
        element_stresses.append(stress)
        element_strains.append(strain)

    # ----- Package output ----------------------------------------------------
    displacements = [[u[2*i], u[2*i+1]] for i in range(n_nodes)]
    reactions = [
        [reactions_flat[2*i], reactions_flat[2*i+1]] for i in range(n_nodes)
    ]

    return {
        "ok": True,
        "displacements": displacements,
        "reactions": reactions,
        "element_forces": element_forces,
        "element_stresses": element_stresses,
        "element_strains": element_strains,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public solver 2: 1-D elastoplastic bar (bilinear isotropic hardening)
# ---------------------------------------------------------------------------

def solve_bar_plastic(
    length: float,
    area: float,
    E: float,
    sigma_y: float,
    H: float,
    force: float,
    steps: int = 20,
    *,
    nr_max_iter: int = 50,
    nr_tol: float = 1e-10,
) -> dict:
    """
    1-D uniaxial bar with bilinear isotropic-hardening plasticity.

    The bar is fixed at x=0 and loaded axially at x=length.
    Material model: bilinear isotropic hardening
        σ = E × ε          (elastic, |σ| ≤ σ_y + H × α)
        σ = (σ_y + H×α) × sign(σ_trial)   (yield surface)
    where α is the accumulated equivalent plastic strain.

    Load is ramped from 0 to `force` in `steps` equal increments.
    At each step a Newton-Raphson loop enforces equilibrium using the
    consistent tangent modulus and a return-mapping correction.

    Parameters
    ----------
    length : float
        Bar length (m).  Must be > 0.
    area : float
        Cross-sectional area (m²).  Must be > 0.
    E : float
        Young's modulus (Pa).  Must be > 0.
    sigma_y : float
        Initial yield stress (Pa).  Must be > 0.
    H : float
        Plastic hardening modulus (Pa).  Must be >= 0.
        H = 0 → perfect plasticity.
        H > 0 → isotropic hardening.
    force : float
        Total applied axial force (N).  May be negative (compression).
    steps : int
        Number of load increments (default 20).  Must be >= 1.
    nr_max_iter : int
        Maximum Newton-Raphson iterations per step (default 50).
    nr_tol : float
        Convergence tolerance on residual force (default 1e-10).

    Returns
    -------
    dict
        ok              : True on success
        displacement    : list of float — axial tip displacement per step (m)
        stress          : list of float — axial stress per step (Pa)
        strain          : list of float — total axial strain per step
        plastic_strain  : list of float — accumulated plastic strain per step
        plastic         : bool — True if any plastic deformation occurred
        force_applied   : list of float — applied force at each step (N)
        converged       : list of bool — Newton-Raphson convergence per step
        iterations      : list of int — NR iterations used per step
        warnings        : list of str — non-fatal warnings (never raises)

    Notes
    -----
    For a single-DOF system the consistent tangent is simply E_T = E·H/(E+H)
    (elastic: E_T = E; yielded: E_T = EH/(E+H)).  The return-mapping reduces to:

        σ_trial = σ_n + E × Δε
        f_trial = |σ_trial| − (σ_y + H × α_n) > 0 → plastic step
        Δγ = f_trial / (E + H)
        α_{n+1} = α_n + Δγ
        σ_{n+1} = σ_trial − E × Δγ × sign(σ_trial)

    Errors returned as {"ok": False, "reason": "..."}.  Never raises.
    """
    warnings_out: list[str] = []

    # ----- Input validation -------------------------------------------------
    err = _guard_positive("length", length)
    if err:
        return _err(err)
    err = _guard_positive("area", area)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("sigma_y", sigma_y)
    if err:
        return _err(err)
    err = _guard_nonneg("H", H)
    if err:
        return _err(err)
    try:
        force = float(force)
        if not math.isfinite(force):
            return _err("force must be a finite number")
    except (TypeError, ValueError):
        return _err(f"force must be a number, got {force!r}")
    try:
        steps = int(steps)
    except (TypeError, ValueError):
        return _err(f"steps must be an integer, got {steps!r}")
    if steps < 1:
        return _err(f"steps must be >= 1, got {steps}")

    L = float(length)
    A = float(area)
    E_val = float(E)
    sy = float(sigma_y)
    H_val = float(H)

    # Axial stiffness of bar: k = EA/L
    k = E_val * A / L

    # State variables (accumulated over steps)
    sigma_n = 0.0   # current stress (Pa)
    eps_p_n = 0.0   # current accumulated plastic strain
    u_n = 0.0       # current tip displacement (m)

    disp_hist: list[float] = []
    stress_hist: list[float] = []
    strain_hist: list[float] = []
    eps_p_hist: list[float] = []
    force_hist: list[float] = []
    converged_hist: list[bool] = []
    iter_hist: list[int] = []
    any_plastic = False

    delta_f = force / steps  # force increment per step

    for step in range(steps):
        f_target = delta_f * (step + 1)

        # Newton-Raphson loop
        u_iter = u_n
        sigma_iter = sigma_n
        eps_p_iter = eps_p_n
        converged = False
        n_iter = 0

        for _nr in range(nr_max_iter):
            n_iter += 1

            # Strain from current displacement trial
            eps_total = u_iter / L

            # Return-mapping at this NR iterate.
            # Always use the *committed* plastic strain (eps_p_n) as predictor
            # base so that the plastic correction delta_gamma is computed from
            # scratch each iterate (standard algorithmic tangent approach).
            eps_p_local = eps_p_n  # local alias; will be updated if plastic

            # Trial stress (predictor) — elastic step from committed state
            sigma_trial = E_val * (eps_total - eps_p_local)

            # Yield check against committed yield surface
            yield_stress = sy + H_val * eps_p_local
            f_trial = abs(sigma_trial) - yield_stress

            if f_trial <= 0.0:
                # Elastic — no correction needed
                sigma_iter = sigma_trial
                eps_p_iter = eps_p_local
                E_tan = E_val
            else:
                # Plastic — return mapping (radial)
                sign_trial = 1.0 if sigma_trial >= 0.0 else -1.0
                delta_gamma = f_trial / (E_val + H_val)
                eps_p_iter = eps_p_local + delta_gamma
                sigma_iter = (yield_stress + H_val * delta_gamma) * sign_trial
                # Consistent tangent for isotropic hardening
                if E_val + H_val > 0.0:
                    E_tan = E_val * H_val / (E_val + H_val)
                else:
                    E_tan = 0.0
                any_plastic = True

            # Residual: internal force − external force
            f_int = sigma_iter * A
            residual = f_int - f_target

            if abs(residual) <= nr_tol:
                converged = True
                break

            # Tangent stiffness: k_tan = E_tan * A / L
            k_tan = E_tan * A / L
            if abs(k_tan) < 1e-30:
                warnings_out.append(
                    f"step {step+1}: tangent stiffness near zero — NR stalled"
                )
                break

            du = -residual / k_tan
            u_iter += du

        if not converged:
            warnings_out.append(
                f"step {step+1}: Newton-Raphson did not converge in "
                f"{nr_max_iter} iterations (residual={residual:.3e})"
            )

        # Update committed state
        u_n = u_iter
        sigma_n = sigma_iter
        eps_p_n = eps_p_iter

        eps_total_final = u_n / L

        disp_hist.append(u_n)
        stress_hist.append(sigma_n)
        strain_hist.append(eps_total_final)
        eps_p_hist.append(eps_p_n)
        force_hist.append(f_target)
        converged_hist.append(converged)
        iter_hist.append(n_iter)

    return {
        "ok": True,
        "displacement": disp_hist,
        "stress": stress_hist,
        "strain": strain_hist,
        "plastic_strain": eps_p_hist,
        "plastic": any_plastic,
        "force_applied": force_hist,
        "converged": converged_hist,
        "iterations": iter_hist,
        "warnings": warnings_out,
    }
