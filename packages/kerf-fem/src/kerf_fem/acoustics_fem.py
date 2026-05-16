"""
1-D / 2-D Helmholtz finite-element acoustics.

Solves:  ∇²p + k²p = 0   (Helmholtz equation, time-harmonic)

Capabilities
------------
cavity_modes_1d        — resonant frequencies + mode shapes of a 1-D acoustic tube
cavity_modes_2d        — resonant frequencies + mode shapes of a 2-D rectangular cavity
                         (triangular FEM, generalised eigenproblem K φ = λ M φ)
forced_response_1d     — driven response at a given frequency with a point source
forced_response_2d     — driven response at a given frequency on a 2-D mesh
transmission_loss      — mass-law transmission loss of a limp partition
duct_cut_on            — plane-wave cut-on frequency of a rectangular duct
absorbing_boundary_1d  — Robin (impedance) BC + resonance peak at absorbing end

All routines are pure Python (hand-rolled dense linear algebra, no numpy/scipy).
None of them raise; errors are returned as {"ok": False, "reason": "..."}.

LLM tool registration is gated on kerf_chat availability.

Physical conventions
--------------------
SI units throughout.  Speed of sound c in m/s, lengths in m, frequencies in Hz.

FEM mesh dict
-------------
    {
      "nodes":    [[x0,y0], [x1,y1], ...],          # float 2-D coords [m]
      "elements": [[n0,n1,n2], ...],                 # 0-based CCW triangles
    }

Dirichlet BC dict  { node_index: value, ... }
Robin BC list      [{"nodes": [i,j,...], "Z": z_value}, ...]   (edge segments)
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Dense linear-algebra helpers (pure Python)
# ---------------------------------------------------------------------------

def _gauss_solve(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Partial-pivot Gaussian elimination. Returns x or None if singular."""
    n = len(b)
    aug = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        max_row, max_val = col, abs(aug[col][col])
        for row in range(col + 1, n):
            v = abs(aug[row][col])
            if v > max_val:
                max_val = v
                max_row = row
        aug[col], aug[max_row] = aug[max_row], aug[col]
        pivot = aug[col][col]
        if abs(pivot) < 1e-15:
            return None
        inv_p = 1.0 / pivot
        for row in range(col + 1, n):
            f = aug[row][col] * inv_p
            for j in range(col, n + 1):
                aug[row][j] -= f * aug[col][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = aug[i][n]
        for j in range(i + 1, n):
            x[i] -= aug[i][j] * x[j]
        if abs(aug[i][i]) < 1e-15:
            return None
        x[i] /= aug[i][i]
    return x


def _mat_vec(A: list[list[float]], x: list[float]) -> list[float]:
    n = len(x)
    return [sum(A[i][j] * x[j] for j in range(n)) for i in range(n)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _scale(a: list[float], s: float) -> list[float]:
    return [v * s for v in a]


def _add(a: list[float], b: list[float]) -> list[float]:
    return [ai + bi for ai, bi in zip(a, b)]


def _norm(a: list[float]) -> float:
    return math.sqrt(_dot(a, a))


def _zeros(n: int) -> list[float]:
    return [0.0] * n


def _zeros2(n: int) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _identity(n: int) -> list[list[float]]:
    I = _zeros2(n)
    for i in range(n):
        I[i][i] = 1.0
    return I


def _mat_mat(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    n = len(A)
    m = len(B[0])
    k = len(B)
    C = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            s = 0.0
            for p in range(k):
                s += A[i][p] * B[p][j]
            C[i][j] = s
    return C


def _transpose(A: list[list[float]]) -> list[list[float]]:
    n = len(A)
    m = len(A[0])
    return [[A[i][j] for i in range(n)] for j in range(m)]


# ---------------------------------------------------------------------------
# Generalised eigenproblem: K v = λ M v
# via Cholesky of M then QR iteration on M^{-1/2} K M^{-1/2}
# For the small reduced systems here (<<100 DOF) dense methods are fine.
# ---------------------------------------------------------------------------

def _cholesky(A: list[list[float]]) -> list[list[float]] | None:
    """Lower Cholesky factor L s.t. A = L L^T.  Returns None if not PD."""
    n = len(A)
    L = _zeros2(n)
    for i in range(n):
        s = A[i][i]
        for k in range(i):
            s -= L[i][k] * L[i][k]
        if s <= 0.0:
            return None
        L[i][i] = math.sqrt(s)
        inv_lii = 1.0 / L[i][i]
        for j in range(i + 1, n):
            t = A[j][i]
            for k in range(i):
                t -= L[j][k] * L[i][k]
            L[j][i] = t * inv_lii
    return L


def _forward_sub(L: list[list[float]], b: list[float]) -> list[float]:
    """Solve L x = b (lower triangular)."""
    n = len(b)
    x = [0.0] * n
    for i in range(n):
        s = b[i]
        for j in range(i):
            s -= L[i][j] * x[j]
        x[i] = s / L[i][i]
    return x


def _back_sub(Lt: list[list[float]], b: list[float]) -> list[float]:
    """Solve L^T x = b (upper triangular from lower L)."""
    n = len(b)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = b[i]
        for j in range(i + 1, n):
            s -= Lt[j][i] * x[j]
        x[i] = s / Lt[i][i]
    return x


def _solve_chol(L: list[list[float]], b: list[float]) -> list[float]:
    """Solve A x = b where L is Cholesky factor of A."""
    y = _forward_sub(L, b)
    return _back_sub(L, y)


def _qr_decompose(A: list[list[float]]) -> tuple[list[list[float]], list[list[float]]]:
    """
    Householder QR decomposition of A (n×n).
    Returns (Q, R) with Q orthogonal, R upper triangular.
    """
    n = len(A)
    Q = _identity(n)
    R = [row[:] for row in A]
    for k in range(n - 1):
        # Extract column k from row k downward
        x = [R[i][k] for i in range(k, n)]
        norm_x = _norm(x)
        if norm_x < 1e-14:
            continue
        # Householder reflector
        sign = 1.0 if x[0] >= 0.0 else -1.0
        u0 = x[0] + sign * norm_x
        v = [u0] + x[1:]
        norm_v2 = _dot(v, v)
        if norm_v2 < 1e-28:
            continue
        # Apply H = I - 2 v v^T / (v^T v) to R from left
        for j in range(n):
            dot_vR = sum(v[i] * R[k + i][j] for i in range(len(v)))
            factor = 2.0 * dot_vR / norm_v2
            for i in range(len(v)):
                R[k + i][j] -= factor * v[i]
        # Apply H to Q from right (accumulate Q)
        for i in range(n):
            dot_Qv = sum(Q[i][k + p] * v[p] for p in range(len(v)))
            factor = 2.0 * dot_Qv / norm_v2
            for p in range(len(v)):
                Q[i][k + p] -= factor * v[p]
    return Q, R


def _symmetric_qr_eigenvalues(
    A: list[list[float]],
    max_iter: int = 30,
    tol: float = 1e-8,
) -> tuple[list[float], list[list[float]]]:
    """
    QR algorithm with Wilkinson shift for a real symmetric matrix.
    Returns (eigenvalues, eigenvectors).  Eigenvalues in ascending order.
    """
    n = len(A)
    T = [row[:] for row in A]
    V = _identity(n)  # accumulates orthogonal transformations

    for _ in range(max_iter * n):
        # Check for convergence: off-diagonal sub-diagonal elements
        converged = True
        for i in range(n - 1):
            if abs(T[i + 1][i]) > tol * (abs(T[i][i]) + abs(T[i + 1][i + 1])):
                converged = False
                break
        if converged:
            break

        # Wilkinson shift using trailing 2×2
        d = (T[n - 2][n - 2] - T[n - 1][n - 1]) / 2.0
        sign_d = 1.0 if d >= 0.0 else -1.0
        b2 = T[n - 1][n - 2] * T[n - 1][n - 2]
        mu = T[n - 1][n - 1] - b2 / (abs(d) + math.sqrt(d * d + b2) + 1e-300) * sign_d

        # Shift
        for i in range(n):
            T[i][i] -= mu

        Q, R = _qr_decompose(T)
        # T_new = R Q + mu I
        T = _mat_mat(R, Q)
        for i in range(n):
            T[i][i] += mu
        # Ensure symmetry
        for i in range(n):
            for j in range(i + 1, n):
                s = 0.5 * (T[i][j] + T[j][i])
                T[i][j] = s
                T[j][i] = s
        V = _mat_mat(V, Q)

    eigenvalues = [T[i][i] for i in range(n)]
    eigenvectors = [[V[i][j] for i in range(n)] for j in range(n)]  # column j = evec j

    # Sort ascending
    pairs = sorted(zip(eigenvalues, eigenvectors), key=lambda p: p[0])
    eigenvalues = [p[0] for p in pairs]
    eigenvectors = [p[1] for p in pairs]
    return eigenvalues, eigenvectors


def _lu_factor(A: list[list[float]]) -> tuple[list[list[float]], list[int]] | None:
    """
    In-place LU factorisation with partial pivoting.
    Returns (LU, piv) or None if singular.
    LU stores L (unit lower) and U (upper) in the same array.
    piv[i] = row index swapped with row i.
    """
    n = len(A)
    LU = [row[:] for row in A]
    piv = list(range(n))
    for k in range(n):
        # Find pivot
        max_val, max_row = abs(LU[k][k]), k
        for i in range(k + 1, n):
            if abs(LU[i][k]) > max_val:
                max_val = abs(LU[i][k])
                max_row = i
        if max_val < 1e-15:
            return None
        LU[k], LU[max_row] = LU[max_row], LU[k]
        piv[k] = max_row
        inv_ukk = 1.0 / LU[k][k]
        for i in range(k + 1, n):
            LU[i][k] *= inv_ukk
            for j in range(k + 1, n):
                LU[i][j] -= LU[i][k] * LU[k][j]
    return LU, piv


def _lu_solve(LU: list[list[float]], piv: list[int], b: list[float]) -> list[float]:
    """Solve LU x = b given the LU factorisation with pivoting."""
    n = len(b)
    x = b[:]
    # Apply row permutations
    for k in range(n):
        x[k], x[piv[k]] = x[piv[k]], x[k]
    # Forward substitution (unit lower)
    for i in range(1, n):
        for j in range(i):
            x[i] -= LU[i][j] * x[j]
    # Back substitution
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n):
            x[i] -= LU[i][j] * x[j]
        x[i] /= LU[i][i]
    return x


def _rayleigh_quotient(K: list[list[float]], M: list[list[float]], v: list[float]) -> float:
    """Rayleigh quotient  λ ≈ vᵀKv / vᵀMv."""
    Kv = _mat_vec(K, v)
    Mv = _mat_vec(M, v)
    denom = _dot(v, Mv)
    if abs(denom) < 1e-30:
        return 0.0
    return _dot(v, Kv) / denom


def _generalised_eigenproblem(
    K: list[list[float]],
    M: list[list[float]],
    n_modes: int,
    max_iter: int = 60,
    tol: float = 1e-7,
) -> tuple[list[float], list[list[float]]] | None:
    """
    Solve K v = λ M v for the smallest n_modes eigenvalues/vectors.

    Algorithm: shifted inverse iteration with M-orthogonal deflation.
    For each mode in turn:
      1. Shift A_shift = K - σ M (σ slightly below current target)
      2. Factor A_shift with LU
      3. Power-iterate: v ← A_shift⁻¹ M v,  M-orthogonalise against found modes
      4. Rayleigh quotient refinement

    Cost: O(n² × max_iter × n_modes) — much cheaper than full QR for n_modes << n.

    Returns (eigenvalues, eigenvectors) in ascending order, or None on failure.
    """
    n = len(K)
    n_req = min(n_modes, n)

    eigenvalues: list[float] = []
    eigenvectors: list[list[float]] = []

    # Starting shift: just below zero (acoustic modes start at 0 for rigid BC)
    sigma = -1e-6

    for mode_idx in range(n_req):
        # Build shifted matrix  A_shift = K - sigma * M
        A_shift = [[K[i][j] - sigma * M[i][j] for j in range(n)] for i in range(n)]
        fac = _lu_factor(A_shift)
        if fac is None:
            # Shift by a tiny amount to avoid exact singularity
            sigma -= 1.0
            A_shift = [[K[i][j] - sigma * M[i][j] for j in range(n)] for i in range(n)]
            fac = _lu_factor(A_shift)
            if fac is None:
                return None
        LU, piv = fac

        # Initial vector: unit in first unoccupied DOF
        import random as _random
        _rng_seed = 42 + mode_idx
        v = [float((i + _rng_seed) % 7 + 1) for i in range(n)]

        # M-orthogonalise against already-found modes
        for k in range(mode_idx):
            ev_k = eigenvectors[k]
            Mev = _mat_vec(M, ev_k)
            coeff = _dot(v, Mev)
            v = [v[i] - coeff * ev_k[i] for i in range(n)]

        # Normalise v w.r.t. M-norm
        Mv = _mat_vec(M, v)
        nrm = math.sqrt(_dot(v, Mv))
        if nrm < 1e-30:
            v = [1.0 if i == mode_idx % n else 0.0 for i in range(n)]
            Mv = _mat_vec(M, v)
            nrm = math.sqrt(_dot(v, Mv))
        v = [vi / nrm for vi in v]

        lam_prev = 0.0
        for it in range(max_iter):
            # w = A_shift⁻¹ M v
            Mv = _mat_vec(M, v)
            w = _lu_solve(LU, piv, Mv)

            # M-orthogonalise against found modes
            for k in range(mode_idx):
                ev_k = eigenvectors[k]
                Mw = _mat_vec(M, w)
                coeff = _dot(w, _mat_vec(M, ev_k))
                w = [w[i] - coeff * ev_k[i] for i in range(n)]

            # M-normalise
            Mw = _mat_vec(M, w)
            nrm = math.sqrt(_dot(w, Mw))
            if nrm < 1e-30:
                break
            v = [wi / nrm for wi in w]

            # Rayleigh quotient in original problem
            lam = _rayleigh_quotient(K, M, v)
            if it > 0 and abs(lam - lam_prev) < tol * (1.0 + abs(lam)):
                break
            lam_prev = lam

            # Update shift toward converged value (speeds convergence)
            if it % 5 == 4 and abs(lam) < 1e12:
                sigma = lam - 1e-4 * (1.0 + abs(lam))
                A_shift2 = [[K[i][j] - sigma * M[i][j] for j in range(n)] for i in range(n)]
                fac2 = _lu_factor(A_shift2)
                if fac2 is not None:
                    LU, piv = fac2

        lam_final = _rayleigh_quotient(K, M, v)
        eigenvalues.append(lam_final)
        eigenvectors.append(v)

        # Update shift for next mode (just above current eigenvalue)
        sigma = lam_final + 1e-4 * (1.0 + abs(lam_final))

    # Sort ascending
    pairs = sorted(zip(eigenvalues, eigenvectors), key=lambda p: p[0])
    eigenvalues = [p[0] for p in pairs]
    eigenvectors = [p[1] for p in pairs]

    return eigenvalues, eigenvectors


# ---------------------------------------------------------------------------
# Triangle geometry helper
# ---------------------------------------------------------------------------

def _tri_area_and_grad(
    x0: float, y0: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> tuple[float, list[float], list[float]]:
    """
    Linear triangle shape-function gradients.
    b = [y1-y2, y2-y0, y0-y1],  c = [x2-x1, x0-x2, x1-x0]
    Area = 0.5 * (b0*c1 - b1*c0)
    """
    b = [y1 - y2, y2 - y0, y0 - y1]
    c = [x2 - x1, x0 - x2, x1 - x0]
    area = 0.5 * (b[0] * c[1] - b[1] * c[0])
    return area, b, c


# ---------------------------------------------------------------------------
# Helmholtz FEM assembly — 2-D triangular mesh
# ---------------------------------------------------------------------------

def _assemble_helmholtz(
    nodes: list,
    elements: list,
    k_sq: float,
    robin_edges: list | None = None,
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Assemble stiffness K and mass M for the Helmholtz operator:

        (∇φᵢ · ∇φⱼ − k² φᵢ φⱼ) = 0  →  (K − k² M) p = 0

    K_ij = ∫ ∇φᵢ · ∇φⱼ dΩ
    M_ij = ∫ φᵢ φⱼ dΩ

    Robin (absorbing) BC: adds complex-valued impedance term.
    For real-valued modal analysis this adds a damping-like boundary contribution.

    robin_edges: list of {"nodes": [i, j], "Z": z} where Z = ρ c / R  (admittance-like).
    """
    n_nodes = len(nodes)
    K = [[0.0] * n_nodes for _ in range(n_nodes)]
    M = [[0.0] * n_nodes for _ in range(n_nodes)]

    for tri in elements:
        n0, n1, n2 = tri
        x0, y0 = nodes[n0]
        x1, y1 = nodes[n1]
        x2, y2 = nodes[n2]

        area, b, c = _tri_area_and_grad(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-30:
            continue
        if area < 0.0:
            n1, n2 = n2, n1
            x1, y1 = nodes[n1]
            x2, y2 = nodes[n2]
            area, b, c = _tri_area_and_grad(x0, y0, x1, y1, x2, y2)
            if abs(area) < 1e-30:
                continue

        local_nodes = [n0, n1, n2]
        inv_4a = 1.0 / (4.0 * area)

        for i_loc in range(3):
            for j_loc in range(3):
                # Stiffness: ∫ ∇φᵢ · ∇φⱼ = (bᵢbⱼ + cᵢcⱼ) / (4A)
                K[local_nodes[i_loc]][local_nodes[j_loc]] += (
                    (b[i_loc] * b[j_loc] + c[i_loc] * c[j_loc]) * inv_4a
                )
                # Mass: ∫ φᵢ φⱼ = A/12 for i≠j, A/6 for i==j
                if i_loc == j_loc:
                    M[local_nodes[i_loc]][local_nodes[j_loc]] += area / 6.0
                else:
                    M[local_nodes[i_loc]][local_nodes[j_loc]] += area / 12.0

    return K, M


def _assemble_1d_helmholtz(
    n_nodes: int,
    L: float,
    k_sq: float,
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Assemble K and M for a 1-D Helmholtz rod of length L, uniform mesh.

    K_ij = ∫ dφᵢ/dx dφⱼ/dx dx
    M_ij = ∫ φᵢ φⱼ dx

    Uses linear (hat) shape functions on a uniform mesh.
    """
    n = n_nodes
    h = L / (n - 1)
    K = [[0.0] * n for _ in range(n)]
    M = [[0.0] * n for _ in range(n)]
    for e in range(n - 1):
        # Element stiffness
        K[e][e]         += 1.0 / h
        K[e][e + 1]     -= 1.0 / h
        K[e + 1][e]     -= 1.0 / h
        K[e + 1][e + 1] += 1.0 / h
        # Element mass (consistent)
        M[e][e]         += h / 3.0
        M[e][e + 1]     += h / 6.0
        M[e + 1][e]     += h / 6.0
        M[e + 1][e + 1] += h / 3.0
    return K, M


# ---------------------------------------------------------------------------
# Dirichlet BC application
# ---------------------------------------------------------------------------

def _apply_dirichlet_kf(
    K: list[list[float]],
    f: list[float],
    dirichlet_bc: dict,
) -> None:
    """Apply Dirichlet BCs in-place (row/column elimination)."""
    n = len(f)
    for d_raw, g in dirichlet_bc.items():
        d = int(d_raw)
        g = float(g)
        for i in range(n):
            if i != d:
                f[i] -= K[i][d] * g
        for j in range(n):
            K[d][j] = 0.0
            K[j][d] = 0.0
        K[d][d] = 1.0
        f[d] = g


def _apply_dirichlet_km(
    K: list[list[float]],
    M: list[list[float]],
    constrained_dofs: list[int],
) -> list[int]:
    """
    Remove Dirichlet DOFs from K and M by zeroing rows/cols and setting
    K[d][d]=1, M[d][d]=0.  Returns list of free DOFs.
    """
    n = len(K)
    c_set = set(constrained_dofs)
    for d in c_set:
        for j in range(n):
            K[d][j] = 0.0
            K[j][d] = 0.0
            M[d][j] = 0.0
            M[j][d] = 0.0
        K[d][d] = 1.0
        M[d][d] = 0.0   # will be removed from reduced system
    return [i for i in range(n) if i not in c_set]


def _reduce(mat: list[list[float]], free_dofs: list[int]) -> list[list[float]]:
    """Extract sub-matrix for free DOFs."""
    n = len(free_dofs)
    return [[mat[free_dofs[i]][free_dofs[j]] for j in range(n)] for i in range(n)]


def _expand_mode(mode_reduced: list[float], free_dofs: list[int], n_total: int) -> list[float]:
    """Expand a reduced eigenvector back to full DOF vector."""
    v = [0.0] * n_total
    for k, dof in enumerate(free_dofs):
        v[dof] = mode_reduced[k]
    return v


# ---------------------------------------------------------------------------
# Public API — 1-D closed tube (closed-closed, rigid walls)
# ---------------------------------------------------------------------------

def cavity_modes_1d(
    L: float,
    c: float,
    n_nodes: int = 41,
    n_modes: int = 6,
    bc_left: str = "rigid",
    bc_right: str = "rigid",
) -> dict[str, Any]:
    """
    Modal analysis of a 1-D acoustic tube (duct).

    Solves K v = λ M v on a uniform mesh.
    Rigid wall (Neumann) BC: natural (no action).
    Open end (Dirichlet p=0) BC: applied explicitly.

    Parameters
    ----------
    L        : tube length [m]
    c        : speed of sound [m/s]
    n_nodes  : number of uniform mesh nodes (default 41)
    n_modes  : number of modes to return
    bc_left  : "rigid" (closed) or "open" (pressure node, p=0)
    bc_right : "rigid" (closed) or "open"

    Returns
    -------
    dict:
        ok            bool
        frequencies   list[float]   Hz, ascending
        mode_shapes   list[list[float]]  one per mode, nodal pressure values
        x_coords      list[float]   node x-positions [m]
    """
    if L <= 0.0:
        return {"ok": False, "reason": "L must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if n_nodes < 3:
        return {"ok": False, "reason": "n_nodes must be >= 3"}

    K, M = _assemble_1d_helmholtz(n_nodes, L, 0.0)

    constrained = []
    if bc_left == "open":
        constrained.append(0)
    if bc_right == "open":
        constrained.append(n_nodes - 1)

    # For all-Neumann (rigid) BCs the assembled K is singular: eigenvalue 0
    # corresponds to the trivial uniform-pressure mode (rigid-body acoustic
    # mode).  Request one extra eigenvalue so we can discard it and still
    # return n_modes non-trivial results.
    all_neumann = (len(constrained) == 0)

    free_dofs = [i for i in range(n_nodes) if i not in constrained]
    Kr = _reduce(K, free_dofs)
    Mr = _reduce(M, free_dofs)

    n_free = len(free_dofs)
    n_req = min(n_modes + (1 if all_neumann else 0), n_free)
    if n_req < 1:
        return {"ok": False, "reason": "no free DOFs after applying BCs"}

    result = _generalised_eigenproblem(Kr, Mr, n_req)
    if result is None:
        return {"ok": False, "reason": "eigenproblem failed (mass matrix not positive definite)"}

    eigenvalues, eigenvectors = result

    # Threshold: eigenvalue is "trivial" when the frequency it implies is
    # less than 1 % of the expected first acoustic mode  c / (2L).
    # λ = (2π f / c)²  →  λ_thresh = (0.01 · π / L)²
    trivial_lam_thresh = (0.01 * math.pi / L) ** 2

    frequencies = []
    mode_shapes = []
    x_coords = [i * L / (n_nodes - 1) for i in range(n_nodes)]

    for idx in range(len(eigenvalues)):
        if len(frequencies) >= n_modes:
            break
        lam = eigenvalues[idx]
        if lam < 0.0:
            lam = 0.0
        if all_neumann and lam < trivial_lam_thresh:
            continue  # skip trivial rigid-body (uniform-pressure) mode
        freq = c * math.sqrt(lam) / (2.0 * math.pi)
        frequencies.append(freq)
        mode_full = _expand_mode(eigenvectors[idx], free_dofs, n_nodes)
        mode_shapes.append(mode_full)

    return {
        "ok": True,
        "frequencies": frequencies,
        "mode_shapes": mode_shapes,
        "x_coords": x_coords,
    }


# ---------------------------------------------------------------------------
# Public API — 2-D rectangular cavity modes (triangular FEM)
# ---------------------------------------------------------------------------

def _rect_acoustic_mesh(Lx: float, Ly: float, nx: int, ny: int) -> dict:
    """Uniform rectangular mesh of CCW right-triangles."""
    nodes = []
    for i in range(nx + 1):
        for j in range(ny + 1):
            nodes.append([i * Lx / nx, j * Ly / ny])
    elements = []
    for i in range(nx):
        for j in range(ny):
            n00 = i * (ny + 1) + j
            n10 = (i + 1) * (ny + 1) + j
            n01 = i * (ny + 1) + (j + 1)
            n11 = (i + 1) * (ny + 1) + (j + 1)
            elements.append([n00, n10, n11])
            elements.append([n00, n11, n01])
    return {"nodes": nodes, "elements": elements}


def cavity_modes_2d(
    Lx: float,
    Ly: float,
    c: float,
    nx: int = 10,
    ny: int = 10,
    n_modes: int = 8,
    bc: str = "rigid",
    mesh: dict | None = None,
) -> dict[str, Any]:
    """
    Modal analysis of a 2-D acoustic cavity.

    Parameters
    ----------
    Lx, Ly   : cavity dimensions [m]
    c        : speed of sound [m/s]
    nx, ny   : mesh divisions (used if mesh is None)
    n_modes  : number of modes requested
    bc       : "rigid" (all walls Neumann, p=0 excluded) or "open" (all walls p=0)
    mesh     : optional pre-built mesh dict; if None, a uniform rect mesh is used

    Returns
    -------
    dict:
        ok            bool
        frequencies   list[float]   Hz
        mode_shapes   list[list[float]]  nodal pressure (full mesh)
        nodes         list[[float,float]]
        elements      list[[int,int,int]]
    """
    if Lx <= 0.0 or Ly <= 0.0:
        return {"ok": False, "reason": "Lx and Ly must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if n_modes < 1:
        return {"ok": False, "reason": "n_modes must be >= 1"}

    if mesh is None:
        # Scale nx so that cells are (approximately) square — isotropic mesh
        # density is required for accurate eigenvalue convergence when Lx ≠ Ly.
        # ny is treated as the base resolution; nx is adjusted to match h_x ≈ h_y.
        nx_iso = max(nx, round(ny * Lx / Ly))
        mesh = _rect_acoustic_mesh(Lx, Ly, nx_iso, ny)

    nodes = mesh["nodes"]
    elements = mesh["elements"]

    if len(nodes) < 3:
        return {"ok": False, "reason": "mesh must have at least 3 nodes"}
    if len(elements) < 1:
        return {"ok": False, "reason": "mesh must have at least 1 element"}

    K, M = _assemble_helmholtz(nodes, elements, 0.0)

    # Dirichlet BCs for "open" walls
    constrained = []
    if bc == "open":
        tol = 1e-10
        for i, (x, y) in enumerate(nodes):
            on_wall = (
                abs(x) < tol or abs(x - Lx) < tol or
                abs(y) < tol or abs(y - Ly) < tol
            )
            if on_wall:
                constrained.append(i)

    # For all-Neumann (rigid) BCs the assembled K is singular: eigenvalue 0
    # corresponds to the trivial uniform-pressure rigid-body mode.  Request
    # one extra eigenvalue so we can discard it and still return n_modes
    # non-trivial acoustic modes.
    all_neumann = (len(constrained) == 0)

    free_dofs = [i for i in range(len(nodes)) if i not in set(constrained)]
    if len(free_dofs) < 1:
        return {"ok": False, "reason": "no free DOFs after applying BCs"}

    Kr = _reduce(K, free_dofs)
    Mr = _reduce(M, free_dofs)

    n_req = min(n_modes + (1 if all_neumann else 0), len(free_dofs))
    result = _generalised_eigenproblem(Kr, Mr, n_req)
    if result is None:
        return {"ok": False, "reason": "eigenproblem failed"}

    eigenvalues, eigenvectors = result
    frequencies = []
    mode_shapes = []
    n_total = len(nodes)

    # Threshold for the trivial uniform-pressure mode: use the smaller cavity
    # dimension to estimate the first non-trivial eigenvalue scale.
    L_min = min(Lx, Ly)
    trivial_lam_thresh = (0.01 * math.pi / L_min) ** 2

    for idx in range(len(eigenvalues)):
        if len(frequencies) >= n_modes:
            break
        lam = eigenvalues[idx]
        if lam < 0.0:
            lam = 0.0
        if all_neumann and lam < trivial_lam_thresh:
            continue  # skip trivial rigid-body (uniform-pressure) mode
        freq = c * math.sqrt(lam) / (2.0 * math.pi)
        frequencies.append(freq)
        mode_full = _expand_mode(eigenvectors[idx], free_dofs, n_total)
        mode_shapes.append(mode_full)

    return {
        "ok": True,
        "frequencies": frequencies,
        "mode_shapes": mode_shapes,
        "nodes": nodes,
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# Public API — forced response (1-D)
# ---------------------------------------------------------------------------

def forced_response_1d(
    L: float,
    c: float,
    freq: float,
    source_node: int,
    source_amplitude: float = 1.0,
    n_nodes: int = 41,
    bc_left: str = "rigid",
    bc_right: str = "rigid",
) -> dict[str, Any]:
    """
    Forced harmonic response of a 1-D acoustic duct at a given frequency.

    Solves (K - k² M) p = f  where f is a unit point source.

    Parameters
    ----------
    L                : tube length [m]
    c                : speed of sound [m/s]
    freq             : driving frequency [Hz]
    source_node      : node index of the point velocity source
    source_amplitude : source amplitude (default 1.0)
    n_nodes          : mesh nodes
    bc_left/bc_right : "rigid" or "open"

    Returns
    -------
    dict:
        ok             bool
        pressure       list[float]   real part of nodal pressure
        x_coords       list[float]
        k              float   wave-number [rad/m]
    """
    if L <= 0.0:
        return {"ok": False, "reason": "L must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if freq < 0.0:
        return {"ok": False, "reason": "freq must be non-negative"}
    if not (0 <= source_node < n_nodes):
        return {"ok": False, "reason": "source_node out of range"}

    k = 2.0 * math.pi * freq / c
    k_sq = k * k

    K, M = _assemble_1d_helmholtz(n_nodes, L, k_sq)

    # System: (K - k² M) p = f
    # Subtract k² M from K
    A = [[K[i][j] - k_sq * M[i][j] for j in range(n_nodes)] for i in range(n_nodes)]

    # Build load vector
    f = [0.0] * n_nodes
    f[source_node] = float(source_amplitude)

    # Apply BCs
    constrained = {}
    if bc_left == "open":
        constrained[0] = 0.0
    if bc_right == "open":
        constrained[n_nodes - 1] = 0.0

    _apply_dirichlet_kf(A, f, constrained)

    p = _gauss_solve(A, f)
    if p is None:
        return {"ok": False, "reason": "singular system (at or near resonance with no damping)"}

    x_coords = [i * L / (n_nodes - 1) for i in range(n_nodes)]
    return {
        "ok": True,
        "pressure": p,
        "x_coords": x_coords,
        "k": k,
    }


# ---------------------------------------------------------------------------
# Public API — forced response (2-D)
# ---------------------------------------------------------------------------

def forced_response_2d(
    Lx: float,
    Ly: float,
    c: float,
    freq: float,
    source_node: int,
    source_amplitude: float = 1.0,
    nx: int = 8,
    ny: int = 8,
    bc: str = "rigid",
    mesh: dict | None = None,
) -> dict[str, Any]:
    """
    Forced harmonic response of a 2-D acoustic cavity.

    Solves (K - k² M) p = f with a point source at source_node.

    Returns
    -------
    dict:
        ok          bool
        pressure    list[float]  nodal pressure values
        nodes       list[[float,float]]
        k           float
    """
    if Lx <= 0.0 or Ly <= 0.0:
        return {"ok": False, "reason": "Lx and Ly must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if freq < 0.0:
        return {"ok": False, "reason": "freq must be non-negative"}

    if mesh is None:
        mesh = _rect_acoustic_mesh(Lx, Ly, nx, ny)

    nodes = mesh["nodes"]
    elements = mesh["elements"]
    n_total = len(nodes)

    if not (0 <= source_node < n_total):
        return {"ok": False, "reason": "source_node out of range"}

    k = 2.0 * math.pi * freq / c
    k_sq = k * k

    K, M = _assemble_helmholtz(nodes, elements, 0.0)

    # A = K - k² M
    A = [[K[i][j] - k_sq * M[i][j] for j in range(n_total)] for i in range(n_total)]
    f = [0.0] * n_total
    f[source_node] = float(source_amplitude)

    # Dirichlet BCs
    constrained = {}
    if bc == "open":
        tol = 1e-10
        for i, (x, y) in enumerate(nodes):
            if abs(x) < tol or abs(x - Lx) < tol or abs(y) < tol or abs(y - Ly) < tol:
                constrained[i] = 0.0

    _apply_dirichlet_kf(A, f, constrained)

    p = _gauss_solve(A, f)
    if p is None:
        return {"ok": False, "reason": "singular system (at or near resonance with no damping)"}

    return {
        "ok": True,
        "pressure": p,
        "nodes": nodes,
        "k": k,
    }


# ---------------------------------------------------------------------------
# Public API — transmission loss (mass law)
# ---------------------------------------------------------------------------

def transmission_loss(
    freq: float,
    surface_density: float,
    c: float = 343.0,
    rho: float = 1.21,
    angle_deg: float = 0.0,
) -> dict[str, Any]:
    """
    Transmission loss of a limp, infinite partition (mass law).

    Normal incidence (angle_deg=0):
        TL = 20 log10(1 + (ω m'' / 2 ρ c))

    Oblique incidence (field incidence):
        TL = 20 log10(|1 + j ω m'' cos θ / (2 ρ c)|)

    Parameters
    ----------
    freq            : frequency [Hz]
    surface_density : mass per unit area m'' [kg/m²]
    c               : speed of sound in medium [m/s]
    rho             : air density [kg/m³]
    angle_deg       : angle of incidence [degrees], 0 = normal

    Returns
    -------
    dict:
        ok   bool
        TL   float   transmission loss [dB]
        tau  float   transmission coefficient (0–1)
        freq float   echo of input frequency
    """
    if freq <= 0.0:
        return {"ok": False, "reason": "freq must be positive"}
    if surface_density <= 0.0:
        return {"ok": False, "reason": "surface_density must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if rho <= 0.0:
        return {"ok": False, "reason": "rho must be positive"}

    omega = 2.0 * math.pi * freq
    theta = math.radians(angle_deg)
    cos_theta = math.cos(theta)

    # τ = |1 / (1 + j ω m'' cos θ / (2 ρ c))|²
    z = omega * surface_density * cos_theta / (2.0 * rho * c)
    tau = 1.0 / (1.0 + z * z)
    TL = -10.0 * math.log10(tau)

    return {"ok": True, "TL": TL, "tau": tau, "freq": freq}


# ---------------------------------------------------------------------------
# Public API — duct cut-on frequency
# ---------------------------------------------------------------------------

def duct_cut_on(
    width: float,
    c: float = 343.0,
    height: float | None = None,
    mode_m: int = 1,
    mode_n: int = 0,
) -> dict[str, Any]:
    """
    Cut-on frequency for a rectangular duct.

    For mode (m, n):
        f_cut = (c/2) * sqrt((m/width)² + (n/height)²)

    For a 2-D duct (no height), only m matters:
        f_cut = m * c / (2 * width)

    Parameters
    ----------
    width   : duct width [m]
    c       : speed of sound [m/s]
    height  : duct height [m], optional
    mode_m  : lateral mode index (default 1)
    mode_n  : vertical mode index (default 0)

    Returns
    -------
    dict:
        ok         bool
        f_cut      float   Hz
        mode       [int, int]
        wavelength float   cut-on wavelength [m]
    """
    if width <= 0.0:
        return {"ok": False, "reason": "width must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if height is not None and height <= 0.0:
        return {"ok": False, "reason": "height must be positive if provided"}
    if mode_m < 0 or mode_n < 0:
        return {"ok": False, "reason": "mode indices must be non-negative"}
    if mode_m == 0 and mode_n == 0:
        return {"ok": False, "reason": "mode (0,0) is the plane wave — no cut-on frequency"}

    km = mode_m / width
    kn = (mode_n / height) if (height is not None and height > 0.0) else 0.0
    f_cut = (c / 2.0) * math.sqrt(km * km + kn * kn)
    wavelength = c / f_cut if f_cut > 0.0 else float("inf")

    return {
        "ok": True,
        "f_cut": f_cut,
        "mode": [mode_m, mode_n],
        "wavelength": wavelength,
    }


# ---------------------------------------------------------------------------
# Public API — absorbing boundary (Robin BC) on a 1-D tube
# ---------------------------------------------------------------------------

def absorbing_boundary_1d(
    L: float,
    c: float,
    rho: float,
    freq_range: list[float],
    specific_impedance: float,
    n_nodes: int = 51,
    n_modes: int = 6,
    source_node: int = 0,
    source_amplitude: float = 1.0,
    bc_left: str = "rigid",
) -> dict[str, Any]:
    """
    Frequency-sweep forced response of a 1-D tube with an absorbing (Robin) end.

    The absorbing termination at x=L applies a Robin condition:
        dp/dn = -j k p / (Z_s)   →  boundary term -jω/(cZ_s) ∫ p q ds

    For simplicity (real arithmetic only), we add the real part of the Robin
    contribution to the system, which gives the resistive damping of the
    boundary.  This is appropriate for verifying resonance reduction rather
    than exact complex scattering.

    Parameters
    ----------
    L                  : tube length [m]
    c                  : speed of sound [m/s]
    rho                : air density [kg/m³]
    freq_range         : list of frequencies to sweep [Hz]
    specific_impedance : normalised specific impedance Z_s = Z / (ρ c)
                         (1.0 = anechoic, large = nearly rigid)
    n_nodes            : mesh nodes
    n_modes            : eigenvalues to return
    source_node        : index of source node
    source_amplitude   : excitation amplitude
    bc_left            : "rigid" or "open"

    Returns
    -------
    dict:
        ok              bool
        frequencies     list[float]   swept frequencies
        pressure_rms    list[float]   rms pressure at node 0 vs frequency
        modal_freqs     list[float]   estimated resonant frequencies [Hz]
    """
    if L <= 0.0:
        return {"ok": False, "reason": "L must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if rho <= 0.0:
        return {"ok": False, "reason": "rho must be positive"}
    if specific_impedance <= 0.0:
        return {"ok": False, "reason": "specific_impedance must be positive"}
    if not freq_range:
        return {"ok": False, "reason": "freq_range must not be empty"}
    if not (0 <= source_node < n_nodes):
        return {"ok": False, "reason": "source_node out of range"}

    h = L / (n_nodes - 1)
    # Robin admittance coefficient at the termination node
    # Adds  (1 / Z_s) to the node at x=L in the imaginary part.
    # For real damping in a real solve, we treat it as a small real penalty:
    # This physically means a purely resistive termination.
    admittance = 1.0 / (specific_impedance)  # normalised

    # Unconstrained K, M
    K0, M0 = _assemble_1d_helmholtz(n_nodes, L, 0.0)

    # Constrained DOFs
    constrained_dofs = []
    if bc_left == "open":
        constrained_dofs.append(0)

    pressure_rms = []
    for freq in freq_range:
        k = 2.0 * math.pi * freq / c
        k_sq = k * k

        # Assemble A = K - k² M
        A = [[K0[i][j] - k_sq * M0[i][j] for j in range(n_nodes)]
             for i in range(n_nodes)]

        # Add Robin damping at right end (x = L, node n_nodes-1)
        # Adds  (k * admittance) to diagonal as a real damping-like term
        # This models energy absorption: the boundary acts as a dashpot.
        if k > 1e-12:
            A[n_nodes - 1][n_nodes - 1] += k * admittance

        f = [0.0] * n_nodes
        f[source_node] = float(source_amplitude)

        bc_dict = {}
        for d in constrained_dofs:
            bc_dict[d] = 0.0
        _apply_dirichlet_kf(A, f, bc_dict)

        p = _gauss_solve(A, f)
        if p is None:
            pressure_rms.append(0.0)
        else:
            rms = math.sqrt(sum(v * v for v in p) / n_nodes)
            pressure_rms.append(rms)

    # Modal frequencies (rigid tube)
    modal_result = cavity_modes_1d(L, c, n_nodes=n_nodes, n_modes=n_modes,
                                   bc_left=bc_left, bc_right="rigid")
    modal_freqs = modal_result.get("frequencies", []) if modal_result["ok"] else []

    return {
        "ok": True,
        "frequencies": list(freq_range),
        "pressure_rms": pressure_rms,
        "modal_freqs": modal_freqs,
    }


# ---------------------------------------------------------------------------
# Analytic helpers (cross-check references)
# ---------------------------------------------------------------------------

def closed_tube_modes(L: float, c: float, n_max: int = 5) -> dict[str, Any]:
    """
    Analytic resonant frequencies of a closed-closed (rigid-wall) tube.

    f_n = n · c / (2 L),  n = 1, 2, ...

    Parameters
    ----------
    L     : tube length [m]
    c     : speed of sound [m/s]
    n_max : number of modes to return

    Returns
    -------
    dict: ok, frequencies [Hz], mode_numbers [int]
    """
    if L <= 0.0:
        return {"ok": False, "reason": "L must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if n_max < 1:
        return {"ok": False, "reason": "n_max must be >= 1"}
    freqs = [n * c / (2.0 * L) for n in range(1, n_max + 1)]
    return {"ok": True, "frequencies": freqs, "mode_numbers": list(range(1, n_max + 1))}


def open_tube_modes(L: float, c: float, n_max: int = 5) -> dict[str, Any]:
    """
    Analytic resonant frequencies of an open-open (both ends p=0) tube.

    f_n = n · c / (2 L),  n = 1, 2, ...

    Same series as closed-closed but physically different mode shapes.

    Returns
    -------
    dict: ok, frequencies [Hz]
    """
    return closed_tube_modes(L, c, n_max)


def open_closed_tube_modes(L: float, c: float, n_max: int = 5) -> dict[str, Any]:
    """
    Analytic resonant frequencies of an open-closed (quarter-wave) tube.

    f_n = (2n-1) · c / (4 L),  n = 1, 2, ...

    Returns
    -------
    dict: ok, frequencies [Hz]
    """
    if L <= 0.0:
        return {"ok": False, "reason": "L must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    if n_max < 1:
        return {"ok": False, "reason": "n_max must be >= 1"}
    freqs = [(2 * n - 1) * c / (4.0 * L) for n in range(1, n_max + 1)]
    return {"ok": True, "frequencies": freqs, "mode_numbers": [2 * n - 1 for n in range(1, n_max + 1)]}


def rectangular_cavity_modes_2d(
    Lx: float,
    Ly: float,
    c: float,
    p_max: int = 3,
    q_max: int = 3,
) -> dict[str, Any]:
    """
    Analytic resonant frequencies of a 2-D rigid rectangular cavity.

    f_{pq} = (c/2) * sqrt((p/Lx)² + (q/Ly)²)

    p, q in 0..p_max (excluding p=q=0).

    Returns
    -------
    dict: ok, frequencies [Hz], modes [[p,q]]
    """
    if Lx <= 0.0 or Ly <= 0.0:
        return {"ok": False, "reason": "Lx and Ly must be positive"}
    if c <= 0.0:
        return {"ok": False, "reason": "c must be positive"}
    pairs = []
    for p in range(p_max + 1):
        for q in range(q_max + 1):
            if p == 0 and q == 0:
                continue
            f = (c / 2.0) * math.sqrt((p / Lx) ** 2 + (q / Ly) ** 2)
            pairs.append((f, [p, q]))
    pairs.sort(key=lambda x: x[0])
    return {
        "ok": True,
        "frequencies": [x[0] for x in pairs],
        "modes": [x[1] for x in pairs],
    }


# ---------------------------------------------------------------------------
# Mode orthogonality / energy check
# ---------------------------------------------------------------------------

def mode_orthogonality(
    mode_i: list[float],
    mode_j: list[float],
    M: list[list[float]] | None = None,
    n_nodes: int | None = None,
    L: float | None = None,
) -> dict[str, Any]:
    """
    Check orthogonality of two mode shapes with respect to mass matrix M.

    <i, j>_M = φᵢᵀ M φⱼ

    If M is None and n_nodes + L are given, builds the 1-D consistent mass.

    Returns
    -------
    dict: ok, dot_product, is_orthogonal (|dot| < tol)
    """
    if len(mode_i) != len(mode_j):
        return {"ok": False, "reason": "mode shapes must have same length"}
    n = len(mode_i)

    if M is None:
        if n_nodes is None or L is None:
            return {"ok": False, "reason": "provide either M or n_nodes+L"}
        _, M = _assemble_1d_helmholtz(n_nodes, L, 0.0)

    Mj = _mat_vec(M, mode_j)
    dot = _dot(mode_i, Mj)
    tol = 1e-4 * max(_norm(mode_i), _norm(mode_j), 1e-30)

    return {
        "ok": True,
        "dot_product": dot,
        "is_orthogonal": abs(dot) < tol,
    }


# ---------------------------------------------------------------------------
# LLM tool registration (gated)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, register, ok_payload, err_payload
except ImportError:
    try:
        from kerf_fem._compat import ToolSpec, register, ok_payload, err_payload
    except ImportError:
        ToolSpec = None
        register = None
        ok_payload = None
        err_payload = None


def _maybe_register():
    if ToolSpec is None or register is None:
        return

    import json

    _acoustics_fem_spec = ToolSpec(
        name="fem_acoustics",
        description=(
            "Helmholtz FEM acoustics solver. Modes of 1-D tubes and 2-D cavities, "
            "forced response, transmission loss (mass law), duct cut-on frequency, "
            "absorbing (Robin) boundary, and mode orthogonality checks. "
            "Pure-Python, no heavy deps. Returns resonant frequencies, mode shapes, "
            "and field quantities."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "enum": [
                        "cavity_modes_1d",
                        "cavity_modes_2d",
                        "forced_response_1d",
                        "forced_response_2d",
                        "transmission_loss",
                        "duct_cut_on",
                        "absorbing_boundary_1d",
                        "closed_tube_modes",
                        "open_tube_modes",
                        "open_closed_tube_modes",
                        "rectangular_cavity_modes_2d",
                    ],
                    "description": "Which analysis to run.",
                },
                "L": {"type": "number", "description": "Tube length [m]"},
                "Lx": {"type": "number", "description": "Cavity x-dimension [m]"},
                "Ly": {"type": "number", "description": "Cavity y-dimension [m]"},
                "c": {"type": "number", "description": "Speed of sound [m/s]"},
                "freq": {"type": "number", "description": "Driving frequency [Hz]"},
                "freq_range": {"type": "array", "items": {"type": "number"}},
                "n_modes": {"type": "integer", "default": 6},
                "n_nodes": {"type": "integer", "default": 41},
                "nx": {"type": "integer", "default": 10},
                "ny": {"type": "integer", "default": 10},
                "bc": {"type": "string", "enum": ["rigid", "open"]},
                "bc_left": {"type": "string", "enum": ["rigid", "open"]},
                "bc_right": {"type": "string", "enum": ["rigid", "open"]},
                "source_node": {"type": "integer"},
                "source_amplitude": {"type": "number"},
                "surface_density": {"type": "number", "description": "[kg/m²]"},
                "rho": {"type": "number", "description": "Air density [kg/m³]"},
                "angle_deg": {"type": "number", "description": "Angle of incidence [deg]"},
                "width": {"type": "number", "description": "Duct width [m]"},
                "height": {"type": "number", "description": "Duct height [m]"},
                "mode_m": {"type": "integer"},
                "mode_n": {"type": "integer"},
                "specific_impedance": {"type": "number"},
                "n_max": {"type": "integer"},
                "p_max": {"type": "integer"},
                "q_max": {"type": "integer"},
            },
            "required": ["analysis"],
        },
    )

    @register(_acoustics_fem_spec)
    async def _run_acoustics_fem(ctx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as e:
            return err_payload(f"invalid args: {e}", "BAD_ARGS")

        analysis = a.get("analysis", "")

        if analysis == "cavity_modes_1d":
            result = cavity_modes_1d(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                n_nodes=int(a.get("n_nodes", 41)),
                n_modes=int(a.get("n_modes", 6)),
                bc_left=a.get("bc_left", "rigid"),
                bc_right=a.get("bc_right", "rigid"),
            )
        elif analysis == "cavity_modes_2d":
            result = cavity_modes_2d(
                Lx=float(a.get("Lx", 1.0)),
                Ly=float(a.get("Ly", 1.0)),
                c=float(a.get("c", 343.0)),
                nx=int(a.get("nx", 10)),
                ny=int(a.get("ny", 10)),
                n_modes=int(a.get("n_modes", 8)),
                bc=a.get("bc", "rigid"),
            )
        elif analysis == "forced_response_1d":
            result = forced_response_1d(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                freq=float(a.get("freq", 100.0)),
                source_node=int(a.get("source_node", 0)),
                source_amplitude=float(a.get("source_amplitude", 1.0)),
                n_nodes=int(a.get("n_nodes", 41)),
                bc_left=a.get("bc_left", "rigid"),
                bc_right=a.get("bc_right", "rigid"),
            )
        elif analysis == "forced_response_2d":
            result = forced_response_2d(
                Lx=float(a.get("Lx", 1.0)),
                Ly=float(a.get("Ly", 1.0)),
                c=float(a.get("c", 343.0)),
                freq=float(a.get("freq", 100.0)),
                source_node=int(a.get("source_node", 0)),
                source_amplitude=float(a.get("source_amplitude", 1.0)),
                nx=int(a.get("nx", 8)),
                ny=int(a.get("ny", 8)),
                bc=a.get("bc", "rigid"),
            )
        elif analysis == "transmission_loss":
            result = transmission_loss(
                freq=float(a.get("freq", 1000.0)),
                surface_density=float(a.get("surface_density", 10.0)),
                c=float(a.get("c", 343.0)),
                rho=float(a.get("rho", 1.21)),
                angle_deg=float(a.get("angle_deg", 0.0)),
            )
        elif analysis == "duct_cut_on":
            height = a.get("height")
            result = duct_cut_on(
                width=float(a.get("width", 0.1)),
                c=float(a.get("c", 343.0)),
                height=float(height) if height is not None else None,
                mode_m=int(a.get("mode_m", 1)),
                mode_n=int(a.get("mode_n", 0)),
            )
        elif analysis == "absorbing_boundary_1d":
            result = absorbing_boundary_1d(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                rho=float(a.get("rho", 1.21)),
                freq_range=a.get("freq_range", []),
                specific_impedance=float(a.get("specific_impedance", 1.0)),
                n_nodes=int(a.get("n_nodes", 51)),
                n_modes=int(a.get("n_modes", 6)),
                source_node=int(a.get("source_node", 0)),
                source_amplitude=float(a.get("source_amplitude", 1.0)),
                bc_left=a.get("bc_left", "rigid"),
            )
        elif analysis == "closed_tube_modes":
            result = closed_tube_modes(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                n_max=int(a.get("n_max", 5)),
            )
        elif analysis == "open_tube_modes":
            result = open_tube_modes(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                n_max=int(a.get("n_max", 5)),
            )
        elif analysis == "open_closed_tube_modes":
            result = open_closed_tube_modes(
                L=float(a.get("L", 1.0)),
                c=float(a.get("c", 343.0)),
                n_max=int(a.get("n_max", 5)),
            )
        elif analysis == "rectangular_cavity_modes_2d":
            result = rectangular_cavity_modes_2d(
                Lx=float(a.get("Lx", 1.0)),
                Ly=float(a.get("Ly", 1.0)),
                c=float(a.get("c", 343.0)),
                p_max=int(a.get("p_max", 3)),
                q_max=int(a.get("q_max", 3)),
            )
        else:
            return err_payload(f"unknown analysis: {analysis!r}", "BAD_ARGS")

        return ok_payload(result)


_maybe_register()
