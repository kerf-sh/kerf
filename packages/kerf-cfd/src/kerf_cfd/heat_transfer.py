"""
Conjugate heat transfer + buoyancy-driven natural convection.

Two solvers are provided:

1. **CompositeWallCHT** — 1-D conjugate heat transfer through a composite
   wall of N layers with arbitrary thickness and conductivity.  The exact
   analytic series-resistance solution is used; no iteration is required.
   Supports convective boundary conditions (h, T_fluid) on both sides.

2. **CavityNaturalConvection** — 2-D Boussinesq natural convection in a
   square cavity with differentially heated vertical walls (the canonical
   de Vahl Davis benchmark).  Uses a projection-method Navier-Stokes solver
   coupled to a convection-diffusion energy equation.

Physical model
--------------
Boussinesq approximation for buoyancy:

    ρ ≈ ρ₀ [1 − β (T − T_ref)]

so the only body force is:

    f_y = −g β (T − T_ref)          (upward positive)

Dimensionless form (L = cavity height, ΔT = T_hot − T_cold):

    Ra = g β ΔT L³ / (ν α)
    Pr = ν / α

Benchmark (de Vahl Davis 1983)
-------------------------------
Ra = 10⁴, Pr = 0.71 →  Nu_avg = 2.243  (±1 %)
Published range from multiple sources: 2.20 – 2.28

Reference:
  de Vahl Davis G., "Natural convection of air in a square cavity:
  a bench mark numerical solution", Int. J. Numer. Meth. Fluids 3 (1983)
  249–264.

Validation tolerance used here: ±3 % (absolute, on Nu_avg).

All routines are pure Python (stdlib only).  Results are returned as
plain dicts with an "ok" key; errors set ok=False and add "reason".
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# 1.  Composite-wall conjugate heat transfer (analytic)
# ---------------------------------------------------------------------------

class CompositeWallCHT:
    """
    1-D steady conjugate heat transfer through a composite wall.

    Layers are numbered 0 … N-1 from left (x=0) to right (x=L_total).

    Parameters
    ----------
    layers : list of {"thickness": float, "k": float}
        Each entry is one solid layer.  thickness [m], k [W/(m·K)].
    h_left : float, optional
        Convective film coefficient [W/(m²·K)] on the left surface.
        0 → adiabatic; None or 0 → no convection (Dirichlet T_left).
    T_fluid_left : float, optional
        Fluid temperature on the left [K or °C].  Required if h_left > 0.
    h_right : float, optional
        Convective film coefficient on the right surface.
    T_fluid_right : float, optional
        Fluid temperature on the right.  Required if h_right > 0.

    Direct Dirichlet mode
    ---------------------
    If h_left == 0 (or omitted) set ``T_left`` when calling ``solve()``.
    Similarly for the right boundary.

    Usage
    -----
    >>> wall = CompositeWallCHT(
    ...     layers=[{"thickness": 0.01, "k": 50.0},   # steel
    ...             {"thickness": 0.05, "k": 0.04},   # insulation
    ...             {"thickness": 0.003, "k": 1.0}],  # concrete
    ...     h_left=500.0, T_fluid_left=200.0,
    ...     h_right=10.0, T_fluid_right=20.0,
    ... )
    >>> result = wall.solve()
    """

    def __init__(
        self,
        layers: list[dict[str, float]],
        h_left: float = 0.0,
        T_fluid_left: float = 0.0,
        h_right: float = 0.0,
        T_fluid_right: float = 0.0,
    ) -> None:
        self._layers = layers
        self._h_left = h_left
        self._T_fluid_left = T_fluid_left
        self._h_right = h_right
        self._T_fluid_right = T_fluid_right

    # ------------------------------------------------------------------
    def solve(
        self,
        T_left: float | None = None,
        T_right: float | None = None,
    ) -> dict[str, Any]:
        """
        Compute the steady 1-D heat flux and temperature profile.

        Parameters
        ----------
        T_left : float, optional
            Dirichlet temperature at x=0.  Used when h_left == 0.
        T_right : float, optional
            Dirichlet temperature at x=L.  Used when h_right == 0.

        Returns
        -------
        dict with:
            ok            : bool
            q_flux        : heat flux  [W/m²]  (positive = left→right)
            T_interfaces  : list of temperatures at each interface [K/°C]
                            index 0 = left surface, …, index N = right surface
            R_total       : total thermal resistance [m²·K/W]
        """
        # --- validate layers ---
        if not self._layers:
            return {"ok": False, "reason": "layers must not be empty"}
        for i, lyr in enumerate(self._layers):
            if lyr.get("thickness", 0) <= 0:
                return {"ok": False, "reason": f"layer {i}: thickness must be > 0"}
            if lyr.get("k", 0) <= 0:
                return {"ok": False, "reason": f"layer {i}: k must be > 0"}

        # --- build resistance chain ---
        R_left_conv  = 1.0 / self._h_left  if self._h_left  > 0.0 else 0.0
        R_right_conv = 1.0 / self._h_right if self._h_right > 0.0 else 0.0

        R_solid = [lyr["thickness"] / lyr["k"] for lyr in self._layers]
        R_total = R_left_conv + sum(R_solid) + R_right_conv

        if R_total <= 0.0:
            return {"ok": False, "reason": "total resistance is zero"}

        # --- determine boundary temperatures ---
        if self._h_left > 0.0:
            T_L = self._T_fluid_left
        elif T_left is not None:
            T_L = T_left
        else:
            return {"ok": False, "reason": "T_left required when h_left == 0"}

        if self._h_right > 0.0:
            T_R = self._T_fluid_right
        elif T_right is not None:
            T_R = T_right
        else:
            return {"ok": False, "reason": "T_right required when h_right == 0"}

        # --- heat flux (positive left→right) ---
        q = (T_L - T_R) / R_total

        # --- interface temperatures ---
        # T_interfaces[0] = left wall surface
        # T_interfaces[1..N-1] = inter-layer interfaces
        # T_interfaces[N] = right wall surface
        T_interfaces: list[float] = []
        T_cur = T_L - q * R_left_conv
        T_interfaces.append(T_cur)
        for R_s in R_solid:
            T_cur = T_cur - q * R_s
            T_interfaces.append(T_cur)

        return {
            "ok": True,
            "q_flux": q,
            "T_interfaces": T_interfaces,
            "R_total": R_total,
        }


# ---------------------------------------------------------------------------
# Convenience wrapper (module-level)
# ---------------------------------------------------------------------------

def composite_wall_heat_flux(
    layers: list[dict[str, float]],
    T_hot: float,
    T_cold: float,
) -> dict[str, Any]:
    """
    Compute 1-D heat flux through a layered wall between two Dirichlet surfaces.

    Parameters
    ----------
    layers  : list of {"thickness": float, "k": float}
    T_hot   : temperature of the hot (left) surface [K or °C]
    T_cold  : temperature of the cold (right) surface [K or °C]

    Returns
    -------
    dict with ok, q_flux, T_interfaces, R_total
    """
    wall = CompositeWallCHT(layers)
    return wall.solve(T_left=T_hot, T_right=T_cold)


# ---------------------------------------------------------------------------
# 2.  2-D natural convection in a square cavity (Boussinesq)
# ---------------------------------------------------------------------------
#
# Domain: unit square [0,1]×[0,1]
#   left wall  (x=0): T = T_hot  (hot)
#   right wall (x=1): T = T_cold (cold)
#   top/bottom walls: adiabatic (∂T/∂n = 0), no-slip
#
# Dimensionless groups: Ra = g β ΔT L³/(ν α), Pr = ν/α
# Here we work with dimensional variables scaled so L=1, ΔT=1, ρ=1, and
# recover dimensional quantities via the Rayleigh number.
#
# Numerics:
#   - Staggered grid, projection method (Chorin 1968)
#   - Energy equation: explicit convection + implicit diffusion (operator split)
#   - Buoyancy term (Boussinesq): f_y = Ra/Pr · θ  (dimensionless form)
#
# Dimensionless variables (L=1, ΔT=1, U_ref = α/L → velocity scale):
#   u* = u / (α/L)       →  advection term has factor 1
#   t* = t / (L²/α)
#   θ  = (T − T_cold)/ΔT  ∈ [0,1]
#
# Momentum eqs (dimensionless, Pr and Ra enter):
#   ∂u*/∂t* + (u*·∇)u* = −∇p* + Pr ∇²u*
#   ∂v*/∂t* + (u*·∇)v* = −∇p* + Pr ∇²v* + Ra·Pr · θ
#   ∇·u* = 0
#
# Energy eq:
#   ∂θ/∂t* + (u*·∇)θ = ∇²θ
#
# ---------------------------------------------------------------------------

def _z2(nr: int, nc: int) -> list[list[float]]:
    """Return nr×nc zero matrix."""
    return [[0.0] * nc for _ in range(nr)]


def _copy2(A: list[list[float]]) -> list[list[float]]:
    return [row[:] for row in A]


class CavityNaturalConvection:
    """
    2-D natural convection in a differentially heated square cavity.

    Solves the Boussinesq Navier-Stokes + energy equations on a uniform
    staggered Cartesian grid using Chorin's projection method.

    Parameters
    ----------
    Ra : float
        Rayleigh number.  Ra = g β ΔT L³ / (ν α).
    Pr : float
        Prandtl number.  Pr = ν / α.
    n  : int
        Number of interior cells in each direction.  Grid is n×n.
        Minimum 8; 32 is recommended for Ra ≤ 10⁵.
    max_steps : int
        Maximum pseudo-time steps.
    tol : float
        Convergence tolerance on max(|u_new − u_old|).
    """

    def __init__(
        self,
        Ra: float = 1e4,
        Pr: float = 0.71,
        n: int = 32,
        max_steps: int = 40000,
        tol: float = 1e-5,
    ) -> None:
        if Ra <= 0:
            raise ValueError("Ra must be positive")
        if Pr <= 0:
            raise ValueError("Pr must be positive")
        if n < 8:
            raise ValueError("n must be >= 8")
        self.Ra = Ra
        self.Pr = Pr
        self.n = n
        self.max_steps = max_steps
        self.tol = tol

    # ------------------------------------------------------------------
    def solve(self) -> dict[str, Any]:
        """
        Integrate to steady state and return Nu_avg and field data.

        Returns
        -------
        dict with:
            ok          : bool
            Nu_avg      : average Nusselt number on the hot wall
            steps       : number of time steps taken
            converged   : bool
            T           : 2-D temperature field θ, shape (n, n), row=j (y), col=i (x)
            U           : x-velocity on staggered faces
            V           : y-velocity on staggered faces
        """
        Ra = self.Ra
        Pr = self.Pr
        n  = self.n

        dx = 1.0 / n
        dy = dx  # square grid

        # ---------------------------------------------------------------
        # Field arrays  (all dimensionless)
        # Staggered MAC layout:
        #   P[i][j]  pressure at cell centre  i=0..n-1, j=0..n-1
        #   U[i][j]  x-velocity at right face of cell i  →  i=0..n, j=0..n-1
        #   V[i][j]  y-velocity at top  face of cell j  →  i=0..n-1, j=0..n
        #   T[i][j]  temperature at cell centre   i=0..n-1, j=0..n-1
        # ---------------------------------------------------------------
        P = _z2(n, n)
        U = _z2(n + 1, n)
        V = _z2(n, n + 1)
        T = _z2(n, n)   # θ = (T−T_cold)/ΔT; hot wall=1, cold wall=0

        # Initial temperature: linear profile from hot (x=0) to cold (x=1)
        for i in range(n):
            xc = (i + 0.5) * dx
            for j in range(n):
                T[i][j] = 1.0 - xc

        # ---------------------------------------------------------------
        # Time-step selection (von Neumann stability for diffusion term)
        # dt ≤ 0.25 * dx² / max(Pr, 1)   (energy eq has diffusivity 1,
        #                                   momentum has Pr)
        # ---------------------------------------------------------------
        dt_diff = 0.20 * dx * dx / max(Pr, 1.0)
        dt = dt_diff

        converged = False
        steps = 0

        for step in range(self.max_steps):
            # ----- 1. Boundary conditions on U, V, T -------------------
            # Temperature BCs
            # Hot wall left (x=0): ghost cell → T[−1][j] such that
            #   0.5*(T_ghost + T[0][j]) = 1  ⟹  T_ghost = 2 − T[0][j]
            # Cold wall right (x=1): T_ghost = −T[n-1][j]
            # Top/bottom: adiabatic ∂T/∂n=0 → T_ghost = T interior

            # Velocity BCs: no-slip on all walls
            # Left wall: U[0][j] = 0  (normal velocity)
            # Right wall: U[n][j] = 0
            # Bottom wall: V[i][0] = 0  (normal velocity)
            # Top wall: V[i][n] = 0

            for j in range(n):
                U[0][j]   = 0.0
                U[n][j]   = 0.0
            for i in range(n):
                V[i][0]   = 0.0
                V[i][n]   = 0.0

            # ----- 2. Provisional velocity (explicit, no pressure) -----
            Ust = _z2(n + 1, n)
            Vst = _z2(n, n + 1)

            # -- u* (interior faces i=1..n-1) --
            for i in range(1, n):
                for j in range(n):
                    # cell-centre u via averaging adjacent faces
                    u_c = U[i][j]

                    # Convective: (u ∂u/∂x + v ∂u/∂y) at face (i, j)
                    # x-advection: central diff in u
                    dudx = (U[i + 1][j] - U[i - 1][j]) / (2.0 * dx) if i < n else 0.0
                    # y-advection: v at face (i,j) by averaging 4 neighbours
                    v_sw = V[i - 1][j]     if i > 0 else 0.0
                    v_se = V[i][j]
                    v_nw = V[i - 1][j + 1] if i > 0 else 0.0
                    v_ne = V[i][j + 1]
                    v_at_u = 0.25 * (v_sw + v_se + v_nw + v_ne)
                    dudy_c = (U[i][j + 1] - U[i][j - 1]) / (2.0 * dy) if 0 < j < n - 1 else (
                        (U[i][j + 1] - U[i][j]) / dy if j == 0 else (U[i][j] - U[i][j - 1]) / dy
                    )

                    conv = u_c * dudx + v_at_u * dudy_c

                    # Viscous: Pr * (∂²u/∂x² + ∂²u/∂y²)
                    d2udx2 = (U[i + 1][j] - 2.0 * U[i][j] + U[i - 1][j]) / (dx * dx)
                    # y-2nd diff needs ghost values
                    u_south = -U[i][j] if j == 0 else U[i][j - 1]       # no-slip ghost
                    u_north = -U[i][j] if j == n - 1 else U[i][j + 1]   # no-slip ghost
                    d2udy2 = (u_north - 2.0 * U[i][j] + u_south) / (dy * dy)

                    visc = Pr * (d2udx2 + d2udy2)

                    Ust[i][j] = U[i][j] + dt * (-conv + visc)

            # -- v* (interior faces j=1..n-1) --
            for i in range(n):
                for j in range(1, n):
                    v_c = V[i][j]

                    # x-advection: u at face (i,j) by averaging
                    u_sw = U[i][j - 1]     if j > 0 else 0.0
                    u_nw = U[i][j]
                    u_se = U[i + 1][j - 1] if j > 0 else 0.0
                    u_ne = U[i + 1][j]
                    u_at_v = 0.25 * (u_sw + u_nw + u_se + u_ne)
                    dvdx_c = (V[i + 1][j] - V[i - 1][j]) / (2.0 * dx) if 0 < i < n - 1 else (
                        (V[i + 1][j] - V[i][j]) / dx if i == 0 else (V[i][j] - V[i - 1][j]) / dx
                    )

                    dvdy = (V[i][j + 1] - V[i][j - 1]) / (2.0 * dy)

                    conv = u_at_v * dvdx_c + v_c * dvdy

                    # Viscous
                    v_west = -V[i][j] if i == 0 else V[i - 1][j]       # no-slip ghost
                    v_east = -V[i][j] if i == n - 1 else V[i + 1][j]
                    d2vdx2 = (v_east - 2.0 * V[i][j] + v_west) / (dx * dx)
                    d2vdy2 = (V[i][j + 1] - 2.0 * V[i][j] + V[i][j - 1]) / (dy * dy)

                    visc = Pr * (d2vdx2 + d2vdy2)

                    # Buoyancy: Ra * Pr * θ_at_v_face (average of two cells)
                    theta_south = T[i][j - 1]
                    theta_north = T[i][j]
                    theta_v = 0.5 * (theta_south + theta_north)
                    buoy = Ra * Pr * theta_v

                    Vst[i][j] = V[i][j] + dt * (-conv + visc + buoy)

            # Wall boundary conditions on provisional velocity
            for j in range(n):
                Ust[0][j] = 0.0
                Ust[n][j] = 0.0
            for i in range(n):
                Vst[i][0] = 0.0
                Vst[i][n] = 0.0

            # ----- 3. Pressure Poisson (SOR) ----------------------------
            # ∇²p = (1/dt) * ∇·u*
            # Neumann BCs: ∂p/∂n = 0 on all walls

            omega_sor = 1.7
            for _ in range(50):
                P_old = _copy2(P)
                for i in range(n):
                    for j in range(n):
                        div_ust = (Ust[i + 1][j] - Ust[i][j]) / dx + (Vst[i][j + 1] - Vst[i][j]) / dy
                        rhs = div_ust / dt

                        # neighbours with Neumann ghost (mirror)
                        p_w = P[i - 1][j] if i > 0 else P[i][j]
                        p_e = P[i + 1][j] if i < n - 1 else P[i][j]
                        p_s = P[i][j - 1] if j > 0 else P[i][j]
                        p_n = P[i][j + 1] if j < n - 1 else P[i][j]

                        p_gs = (p_w + p_e) / (dx * dx) + (p_s + p_n) / (dy * dy) - rhs
                        p_gs /= (2.0 / (dx * dx) + 2.0 / (dy * dy))

                        P[i][j] = (1.0 - omega_sor) * P[i][j] + omega_sor * p_gs
                # pin pressure at corner to prevent drift
                p00 = P[0][0]
                for i in range(n):
                    for j in range(n):
                        P[i][j] -= p00

            # ----- 4. Velocity correction --------------------------------
            U_new = _z2(n + 1, n)
            V_new = _z2(n, n + 1)

            for i in range(1, n):
                for j in range(n):
                    dpdx = (P[i][j] - P[i - 1][j]) / dx
                    U_new[i][j] = Ust[i][j] - dt * dpdx

            for i in range(n):
                for j in range(1, n):
                    dpdy = (P[i][j] - P[i][j - 1]) / dy
                    V_new[i][j] = Vst[i][j] - dt * dpdy

            # enforce wall BCs
            for j in range(n):
                U_new[0][j] = 0.0
                U_new[n][j] = 0.0
            for i in range(n):
                V_new[i][0] = 0.0
                V_new[i][n] = 0.0

            # ----- 5. Energy equation (explicit) -------------------------
            T_new = _z2(n, n)
            for i in range(n):
                for j in range(n):
                    # Convective: u ∂θ/∂x + v ∂θ/∂y  (upwind for stability)
                    # u at cell centre = 0.5*(U[i][j] + U[i+1][j])
                    u_c = 0.5 * (U[i][j] + U[i + 1][j])
                    v_c = 0.5 * (V[i][j] + V[i][j + 1])

                    # x-direction: ghost cells for temperature
                    # Hot wall (i=0, x=0): T_ghost = 2 - T[0][j]
                    # Cold wall (i=n-1, x=1): T_ghost = -T[n-1][j]
                    t_w = (2.0 - T[0][j])    if i == 0     else T[i - 1][j]
                    t_e = (-T[n - 1][j])      if i == n - 1 else T[i + 1][j]

                    # y-direction: adiabatic top/bottom
                    t_s = T[i][0]     if j == 0     else T[i][j - 1]
                    t_n = T[i][n - 1] if j == n - 1 else T[i][j + 1]

                    # upwind convection
                    dtdx = (T[i][j] - t_w) / dx if u_c >= 0.0 else (t_e - T[i][j]) / dx
                    dtdy = (T[i][j] - t_s) / dy if v_c >= 0.0 else (t_n - T[i][j]) / dy
                    conv_T = u_c * dtdx + v_c * dtdy

                    # diffusion (∇²θ)
                    d2tdx2 = (t_e - 2.0 * T[i][j] + t_w) / (dx * dx)
                    d2tdy2 = (t_n - 2.0 * T[i][j] + t_s) / (dy * dy)
                    diff_T = d2tdx2 + d2tdy2

                    T_new[i][j] = T[i][j] + dt * (-conv_T + diff_T)

            # ----- 6. Convergence check ----------------------------------
            max_du = 0.0
            for i in range(n + 1):
                for j in range(n):
                    d = abs(U_new[i][j] - U[i][j])
                    if d > max_du:
                        max_du = d

            # Update fields
            U = U_new
            V = V_new
            T = T_new
            steps += 1

            if max_du < self.tol and step > 100:
                converged = True
                break

        # ----- 7. Compute Nusselt number on the hot wall ---------------
        # Nu_local(j) = −∂θ/∂x |_{x=0}  (L=1, ΔT=1)
        #
        # The cell centre nearest the hot wall is at x = dx/2.
        # The ghost cell (one spacing dx to the left) satisfies:
        #   0.5 * (T_ghost + T[0][j]) = 1.0   →  T_ghost = 2 − T[0][j]
        #
        # Second-order central difference across the wall:
        #   ∂θ/∂x |_{x=0} ≈ (T[0][j] − T_ghost) / (2·(dx/2))
        #                  = (T[0][j] − (2 − T[0][j])) / dx
        #                  = 2·(T[0][j] − 1) / dx
        #
        # Nu_local = −∂θ/∂x = 2·(1 − T[0][j]) / dx

        nu_sum = 0.0
        for j in range(n):
            nu_sum += 2.0 * (1.0 - T[0][j]) / dx
        Nu_avg = nu_sum / n

        return {
            "ok": True,
            "Nu_avg": Nu_avg,
            "steps": steps,
            "converged": converged,
            "T": T,
            "U": U,
            "V": V,
        }


def cavity_nusselt(
    Ra: float = 1e4,
    Pr: float = 0.71,
    n: int = 32,
    max_steps: int = 40000,
    tol: float = 1e-5,
) -> dict[str, Any]:
    """
    Compute average Nusselt number for natural convection in a square cavity.

    Convenience wrapper around :class:`CavityNaturalConvection`.

    Parameters
    ----------
    Ra : Rayleigh number
    Pr : Prandtl number
    n  : grid size (n×n cells)
    max_steps : iteration limit
    tol : convergence tolerance

    Returns
    -------
    dict with ok, Nu_avg, steps, converged
    """
    solver = CavityNaturalConvection(Ra=Ra, Pr=Pr, n=n, max_steps=max_steps, tol=tol)
    return solver.solve()
