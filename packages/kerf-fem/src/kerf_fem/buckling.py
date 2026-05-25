"""
Linear eigenvalue buckling analysis for beam/column elements.

Solves the generalised eigenproblem:

    K · φ = λ · Kg · φ

where K is the elastic stiffness, Kg is the geometric (initial-stress)
stiffness assembled from an axial pre-stress state, and λ are the buckling
load factors.  The smallest positive λ gives the first (lowest) buckling
load: P_buckling = λ · P_ref.

Element formulations
--------------------
Euler-Bernoulli beam (bending buckling)
    K_e   — Hermite cubic stiffness (exact, matches modal.py)
    Kg_e  — consistent geometric stiffness under axial load N_e:

        Kg_e = N_e / (30 h) * [[36,   3h,  -36,   3h],
                                [ 3h,  4h², -3h,  -h²],
                                [-36, -3h,   36,  -3h],
                                [ 3h, -h²,  -3h,  4h²]]

    Reference: McGuire, Gallagher & Ziemian, "Matrix Structural Analysis"
    2nd ed., eq. (15.3-4); Bazant & Cedolin, Stability of Structures §3.1.

Axial bar (column) member
    Same element topology: translational DOFs only, no rotation.
    For pure axial-only buckling of a truss member, lateral degree-of-freedom
    coupling drives the mode, so the beam formulation above is used with the
    entire column modelled as a sequence of Hermite-beam elements.

Validated against closed-form Euler critical loads:
    Pinned-pinned:  Pcr = π² E I / L²           (K_eff = 1.0)
    Fixed-free:     Pcr = π² E I / (2L)²         (K_eff = 2.0)

Public entry-points
-------------------
    buckling_linear(E, I, A, L, P_ref, supports, *, n_elem=12, n_modes=3)
        -> dict { ok, buckling_factors, critical_loads, mode_shapes }

    euler_column_pcr(E, I, L, K_factor=1.0)
        -> dict { ok, P_cr, K_factor, effective_length }

All routines are pure Python (no numpy / scipy) and never raise; errors return
{"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import math
from typing import Any

# Re-use the Cholesky-based generalised eigensolver from modal.py
from kerf_fem.modal import (
    _cholesky,
    _solve_lower,
    _solve_upper,
    _jacobi_symmetric,
    _gen_eig_chol,
    _Ke_beam,
)


# ---------------------------------------------------------------------------
# Geometric stiffness matrix for Hermite-cubic beam element under axial N
# ---------------------------------------------------------------------------

def _Kge_beam(N: float, h: float) -> list[list[float]]:
    """
    Consistent geometric (initial-stress) stiffness for a Hermite cubic
    Euler-Bernoulli beam element carrying axial force N (positive = compression).

    Reference: McGuire, Gallagher & Ziemian "Matrix Structural Analysis"
    2nd ed., §15.3, eq. (15.3-4).

    DOF ordering: [w_i, θ_i, w_j, θ_j]
    """
    s = N / (30.0 * h)
    h2 = h * h
    return [
        [ 36 * s,   3 * h * s,  -36 * s,   3 * h * s],
        [  3 * h * s,  4 * h2 * s,  -3 * h * s,  -h2 * s],
        [-36 * s,  -3 * h * s,   36 * s,  -3 * h * s],
        [  3 * h * s,   -h2 * s,  -3 * h * s,   4 * h2 * s],
    ]


# ---------------------------------------------------------------------------
# Internal: solve K φ = λ Kg φ  (Kg may not be positive-definite)
# ---------------------------------------------------------------------------

def _gen_eig_buckling(
    K: list[list[float]],
    Kg: list[list[float]],
) -> tuple[list[float], list[list[float]]] | None:
    """
    Solve  K φ = λ Kg φ  for the smallest positive eigenvalues.

    Strategy: since K is SPD and Kg is symmetric but possibly indefinite,
    we perform Cholesky on K and reduce to a standard problem:

        L L^T = K
        Â = L^{-1} Kg L^{-T}        (symmetric)
        Â y = μ y   where μ = 1/λ
        φ = L^{-T} y
        λ = 1/μ  (small positive μ → large λ; large positive μ → small λ)

    Returns (eigenvalues λ ascending-positive, eigenvectors) or None on failure.
    """
    L = _cholesky(K)
    if L is None:
        return None
    n = len(K)

    # Compute Y = L^{-1} Kg  (column by column)
    Y = [[0.0] * n for _ in range(n)]
    for col in range(n):
        bcol = [Kg[row][col] for row in range(n)]
        ycol = _solve_lower(L, bcol)
        for r in range(n):
            Y[r][col] = ycol[r]

    # Compute Â = Y L^{-T}  (= L^{-1} Kg L^{-T}) by solving L Z = Y^T column-wise
    A_hat = [[0.0] * n for _ in range(n)]
    for col in range(n):
        bcol = [Y[col][r] for r in range(n)]
        zcol = _solve_lower(L, bcol)
        for r in range(n):
            A_hat[r][col] = zcol[r]

    # Symmetrise (numerical hygiene)
    for i in range(n):
        for j in range(i + 1, n):
            v = 0.5 * (A_hat[i][j] + A_hat[j][i])
            A_hat[i][j] = v
            A_hat[j][i] = v

    # Eigenvalues μ of Â  →  λ = 1/μ
    mu_vals, eigvecs_y = _jacobi_symmetric(A_hat)

    # Transform eigenvectors back: φ = L^{-T} y
    eigvecs_phi = [[0.0] * n for _ in range(n)]
    for k in range(n):
        ycol = [eigvecs_y[r][k] for r in range(n)]
        phi = _solve_upper(L, ycol)
        for r in range(n):
            eigvecs_phi[r][k] = phi[r]

    # Convert μ → λ = 1/μ, keep only positive λ (positive μ > 0)
    pairs = []
    for i, mu in enumerate(mu_vals):
        if mu > 1e-12:  # positive μ → positive λ (buckling)
            lam = 1.0 / mu
            pairs.append((lam, i))

    if not pairs:
        return None

    # Sort by ascending λ
    pairs.sort(key=lambda p: p[0])
    lam_sorted = [p for p, _ in pairs]
    vecs_sorted = [[eigvecs_phi[r][idx] for r in range(n)] for _, idx in pairs]

    return lam_sorted, vecs_sorted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def buckling_linear(
    E: float,
    I: float,
    A: float,
    L: float,
    P_ref: float,
    supports: list[dict],
    *,
    n_elem: int = 12,
    n_modes: int = 3,
) -> dict[str, Any]:
    """
    Linear eigenvalue buckling of an Euler-Bernoulli column.

    The pre-stress state is uniform axial compression: N = P_ref (per element,
    i.e. the reference load is applied as a constant compressive axial force
    along the full column).

    Parameters
    ----------
    E        : Young's modulus [Pa]
    I        : Second moment of area (bending) [m⁴]
    A        : Cross-section area [m²]  (used for reference only, not in Ke)
    L        : Column length [m]
    P_ref    : Reference axial compressive load [N] (used to assemble Kg)
    supports : List of BC dicts, same format as modal.beam_natural_frequencies:
               {"type": "pinned" | "fixed", "x": position_along_beam}
    n_elem   : Number of Hermite beam elements (default 12)
    n_modes  : Number of lowest buckling modes to return (default 3)

    Returns
    -------
    {
      ok               : bool,
      buckling_factors : list[float]   — λ_i such that P_cr_i = λ_i * P_ref,
      critical_loads   : list[float]   — P_cr_i [N],
      mode_shapes      : list[list]    — transverse displacement DOFs per mode,
    }
    """
    if E <= 0:
        return {"ok": False, "reason": "E must be positive"}
    if I <= 0:
        return {"ok": False, "reason": "I must be positive"}
    if L <= 0:
        return {"ok": False, "reason": "L must be positive"}
    if P_ref <= 0:
        return {"ok": False, "reason": "P_ref must be positive (compressive reference load)"}
    if n_elem < 2:
        return {"ok": False, "reason": "n_elem must be >= 2"}
    if n_modes < 1:
        return {"ok": False, "reason": "n_modes must be >= 1"}

    EI = E * I
    h = L / n_elem
    n_nodes = n_elem + 1
    n_dof = 2 * n_nodes  # (w, θ) per node

    # Assemble global K and Kg
    K = [[0.0] * n_dof for _ in range(n_dof)]
    Kg = [[0.0] * n_dof for _ in range(n_dof)]

    Ke = _Ke_beam(EI, h)
    Kge = _Kge_beam(P_ref, h)

    for e in range(n_elem):
        dofs = [2 * e, 2 * e + 1, 2 * (e + 1), 2 * (e + 1) + 1]
        for i in range(4):
            for j in range(4):
                K[dofs[i]][dofs[j]] += Ke[i][j]
                Kg[dofs[i]][dofs[j]] += Kge[i][j]

    # Parse boundary conditions → fixed DOF set
    fixed_set: set[int] = set()
    for bc in supports:
        btype = bc.get("type", "")
        xpos = float(bc.get("x", 0.0))
        node = round(xpos / h)
        node = max(0, min(n_elem, node))
        if btype == "fixed":
            fixed_set.add(2 * node)       # w
            fixed_set.add(2 * node + 1)   # θ
        elif btype == "pinned":
            fixed_set.add(2 * node)       # w only
        else:
            return {"ok": False, "reason": f"unknown support type {btype!r}"}

    free = [i for i in range(n_dof) if i not in fixed_set]
    if len(free) < 2:
        return {"ok": False, "reason": "no free DOFs after applying boundary conditions"}

    # Reduce to free DOFs
    Kr = [[K[i][j] for j in free] for i in free]
    Kgr = [[Kg[i][j] for j in free] for i in free]

    result = _gen_eig_buckling(Kr, Kgr)
    if result is None:
        return {"ok": False, "reason": "eigensolver failed (K not positive-definite or no positive buckling factors)"}

    lam_list, vecs_list = result

    take_n = min(n_modes, len(lam_list))
    lam_out = lam_list[:take_n]
    p_cr_out = [lam * P_ref for lam in lam_out]

    # Expand mode shapes to full DOF vector
    mode_shapes_full: list[list[float]] = []
    for k in range(take_n):
        full = [0.0] * n_dof
        phi_free = vecs_list[k]
        for fi, dof in enumerate(free):
            full[dof] = phi_free[fi]
        # Normalise by max absolute transverse displacement
        max_w = max((abs(full[2 * nd]) for nd in range(n_nodes)), default=1.0)
        if max_w > 1e-30:
            full = [v / max_w for v in full]
        mode_shapes_full.append(full)

    return {
        "ok": True,
        "buckling_factors": lam_out,
        "critical_loads": p_cr_out,
        "mode_shapes": mode_shapes_full,
    }


def euler_column_pcr(
    E: float,
    I: float,
    L: float,
    K_factor: float = 1.0,
) -> dict[str, Any]:
    """
    Closed-form Euler critical buckling load for a slender column.

        P_cr = π² E I / (K_eff * L)²

    K_factor (effective-length factor):
        1.0  — pinned-pinned       (Euler case 1)
        2.0  — fixed-free (flag)   (Euler case 2)
        0.7  — fixed-pinned
        0.5  — fixed-fixed

    Reference: Timoshenko & Gere, Theory of Elastic Stability §2.1 (1961).

    Returns
    -------
    { ok, P_cr [N], K_factor, effective_length [m] }
    """
    if E <= 0:
        return {"ok": False, "reason": "E must be positive"}
    if I <= 0:
        return {"ok": False, "reason": "I must be positive"}
    if L <= 0:
        return {"ok": False, "reason": "L must be positive"}
    if K_factor <= 0:
        return {"ok": False, "reason": "K_factor must be positive"}

    Le = K_factor * L
    P_cr = math.pi ** 2 * E * I / (Le ** 2)
    return {
        "ok": True,
        "P_cr": P_cr,
        "K_factor": K_factor,
        "effective_length": Le,
    }
