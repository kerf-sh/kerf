"""
kerf_1dsim.solver
=================

DAE / ODE integrators for 1-D lumped-element systems.

Two solvers are provided:

``integrate_dae(F, t_span, x0, dx0, h, method)``
    IDA-style fixed-step BDF-1 (backward Euler) solver for index-1 DAEs.
    At each step a Newton iteration is used to solve the implicit system.

``integrate_ode(f, t_span, x0, h)``
    Forward Euler fallback for explicit ODEs  dx/dt = f(t, x).

Both return a ``SimResult`` with time array and state trajectory.

Typical usage (RC circuit)
--------------------------
::

    from kerf_1dsim.solver import integrate_dae, SimResult

    def F_rc(t, x, dx):
        # x = [v_C, i]   dx = [dv_C/dt, 0]
        V0, R, C = 1.0, 1e3, 1e-6
        return [
            C * dx[0] - x[1],       # capacitor equation
            x[0] + R * x[1] - V0,  # KVL (series)
        ]

    result = integrate_dae(F_rc, t_span=(0.0, 5e-3), x0=[0.0, 0.0],
                           dx0=[0.0, 0.0], h=1e-6)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    """Time-domain simulation result."""
    t: list[float]          # time points [s]
    x: list[list[float]]    # state/variable trajectories: x[step][var]
    converged: bool = True
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Newton solver for F(x_new) = 0
# ---------------------------------------------------------------------------

def _newton_solve(
    F: Callable[[list[float]], list[float]],
    x0: list[float],
    tol: float = 1e-10,
    max_iter: int = 50,
) -> tuple[list[float], bool]:
    """
    Solve F(x) = 0 with Newton-Raphson using finite-difference Jacobian.

    Returns (solution, converged).
    """
    x = list(x0)
    n = len(x)
    eps = 1e-8  # finite-difference step

    for _it in range(max_iter):
        fx = F(x)
        res_norm = math.sqrt(sum(fi * fi for fi in fx))
        if res_norm <= tol:
            return x, True

        # Build Jacobian via forward finite differences
        J = [[0.0] * n for _ in range(n)]
        for j in range(n):
            xp = list(x)
            xp[j] += eps
            fxp = F(xp)
            for i in range(n):
                J[i][j] = (fxp[i] - fx[i]) / eps

        # Solve J * delta = -fx  via Gaussian elimination with partial pivoting
        delta = _lu_solve(J, [-fi for fi in fx])
        if delta is None:
            # Singular Jacobian — abort
            return x, False

        # Line-search damping (simple backtracking)
        step = 1.0
        for _ in range(10):
            x_new = [x[i] + step * delta[i] for i in range(n)]
            fx_new = F(x_new)
            norm_new = math.sqrt(sum(fi * fi for fi in fx_new))
            if norm_new < res_norm:
                break
            step *= 0.5

        x = [x[i] + step * delta[i] for i in range(n)]

    # Final check
    fx = F(x)
    res_norm = math.sqrt(sum(fi * fi for fi in fx))
    return x, res_norm <= tol * 1e3  # relaxed final acceptance


def _lu_solve(A: list[list[float]], b: list[float]) -> list[float] | None:
    """
    Solve A x = b via Gaussian elimination with partial pivoting.
    Returns None if A is (near-)singular.
    """
    n = len(b)
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Find pivot
        pivot_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < 1e-15:
            return None  # singular
        M[col], M[pivot_row] = M[pivot_row], M[col]

        for row in range(col + 1, n):
            factor = M[row][col] / M[col][col]
            for k in range(col, n + 1):
                M[row][k] -= factor * M[col][k]

    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        if abs(M[i][i]) < 1e-15:
            return None
        x[i] /= M[i][i]

    return x


# ---------------------------------------------------------------------------
# BDF-1 (backward Euler) DAE integrator
# ---------------------------------------------------------------------------

def integrate_dae(
    F: Callable[[float, list[float], list[float]], list[float]],
    t_span: tuple[float, float],
    x0: list[float],
    dx0: list[float],
    h: float,
    tol: float = 1e-8,
    max_newton_iter: int = 50,
) -> SimResult:
    """
    Fixed-step BDF-1 (implicit Euler) integrator for index-1 DAEs.

    System: F(t, x, dx) = 0

    At each step the BDF-1 approximation  dx ≈ (x_new - x_old) / h  is
    substituted, giving a purely algebraic system in x_new which is solved
    with Newton iteration.

    Parameters
    ----------
    F : callable(t, x, dx) -> list[float]
        Residual function.  len(F) == len(x).
    t_span : (t0, t_end)
    x0 : list[float]
        Initial state.
    dx0 : list[float]
        Initial derivatives (consistent with F(t0, x0, dx0) ≈ 0).
    h : float
        Time step [s].
    tol : float
        Newton convergence tolerance.
    max_newton_iter : int
        Maximum Newton iterations per step.

    Returns
    -------
    SimResult
    """
    t0, t_end = t_span
    t = t0
    x = list(x0)
    n = len(x)

    t_hist = [t]
    x_hist = [list(x)]
    warnings: list[str] = []
    all_converged = True

    while t < t_end - 1e-15 * abs(t_end):
        t_new = min(t + h, t_end)
        h_eff = t_new - t
        # Skip negligibly small steps that arise from floating-point
        # accumulation at the boundary (h_eff < 1e-10 * h).
        if h_eff < h * 1e-10:
            t = t_new
            t_hist.append(t)
            x_hist.append(list(x))
            break
        x_old = list(x)

        # Residual for Newton: F(t_new, x_new, (x_new - x_old)/h_eff) = 0
        def _residual(x_new: list[float]) -> list[float]:
            dx_new = [(x_new[i] - x_old[i]) / h_eff for i in range(n)]
            return F(t_new, x_new, dx_new)

        x_new, ok = _newton_solve(_residual, x, tol=tol, max_iter=max_newton_iter)
        if not ok:
            warnings.append(f"Newton did not converge at t={t_new:.6g}")
            all_converged = False

        x = x_new
        t = t_new
        t_hist.append(t)
        x_hist.append(list(x))

    return SimResult(t=t_hist, x=x_hist, converged=all_converged, warnings=warnings)


# ---------------------------------------------------------------------------
# Forward Euler ODE fallback
# ---------------------------------------------------------------------------

def integrate_ode(
    f: Callable[[float, list[float]], list[float]],
    t_span: tuple[float, float],
    x0: list[float],
    h: float,
) -> SimResult:
    """
    Forward Euler integrator for explicit ODEs  dx/dt = f(t, x).

    Suitable for stiff-free problems; use ``integrate_dae`` for stiff/DAE systems.

    Parameters
    ----------
    f : callable(t, x) -> list[float]
        Right-hand side function.
    t_span : (t0, t_end)
    x0 : list[float]
        Initial state.
    h : float
        Time step [s].

    Returns
    -------
    SimResult
    """
    t0, t_end = t_span
    t = t0
    x = list(x0)

    t_hist = [t]
    x_hist = [list(x)]

    while t < t_end - 1e-15 * abs(t_end):
        t_new = min(t + h, t_end)
        h_eff = t_new - t
        dxdt = f(t, x)
        x = [x[i] + h_eff * dxdt[i] for i in range(len(x))]
        t = t_new
        t_hist.append(t)
        x_hist.append(list(x))

    return SimResult(t=t_hist, x=x_hist, converged=True)
