"""
kerf_cad_core.procsim.solidification
=====================================
Transient casting solidification simulation using the enthalpy method.

Two public simulation functions:

  solidify_1d(length_m, n_cells, dt, n_steps, alloy, T_pour, T_mold,
              h_interface, probes)
      1-D explicit finite-difference transient heat conduction with latent
      heat handled via the apparent-specific-heat / enthalpy formulation.
      Returns time-stepping results: solid-fraction field at each timestep,
      per-cell solidification times, hot-spot index, thermal-modulus map, and
      cooling curves at requested probe positions.

  solidify_2d(grid, dt, n_steps, alloy, T_pour, T_mold, h_interface, probes)
      2-D explicit finite-difference on a rectangular domain described by
      ``grid = (nx, ny, dx, dy)``.  Same field outputs as the 1-D variant.

Helper query functions (read-only, never raise):

  alloy_properties(name)          → {"ok": bool, ...thermo fields...}
  chvorinov_time(V_m3, A_m2, B, n) → scalar solidification-time estimate (s)

LLM tools (gated on kerf_chat / kerf_core availability):

  run_solidify_1d      — wrap solidify_1d
  run_solidify_2d      — wrap solidify_2d
  run_alloy_properties — wrap alloy_properties

Design notes
------------
* Pure Python; no numpy / scipy / external deps.
* Explicit Euler time integration — stable when dt <= dx²/(2α) (CFL condition
  checked and returned as metadata).
* Enthalpy method: each cell carries enthalpy H; temperature and solid fraction
  are recovered from H via the piecewise alloy phase diagram.
* Mold interface: Robin boundary condition via a lumped heat-transfer coefficient
  h_interface [W·m⁻²·K⁻¹] at all external faces of the casting domain.  The
  mold temperature T_mold is held constant (infinite-mold assumption).
* Never raises.  All public functions return {"ok": bool, ...}.

References
----------
Voller, V.R. & Prakash, C. (1987). "A fixed grid numerical modelling
    methodology for convection–diffusion mushy region phase-change problems."
    Int. J. Heat Mass Transfer 30(8): 1709–1719.
Flemings, M.C. (1974). "Solidification Processing." McGraw-Hill.
Chvorinov, N. (1940). "Theory of the solidification of castings." Giesserei 27.
ASM Handbook Vol. 15: Casting. ASM International.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Alloy thermo-physical properties
# ---------------------------------------------------------------------------
# All properties at mean temperature between liquidus and solidus.
# Keys:
#   T_liq   — liquidus temperature (°C)
#   T_sol   — solidus temperature  (°C)
#   L       — latent heat of fusion  (J·kg⁻¹)
#   k       — thermal conductivity   (W·m⁻¹·K⁻¹)
#   cp      — specific heat capacity (J·kg⁻¹·K⁻¹)  (solid+liquid average)
#   rho     — density                (kg·m⁻³)

_ALLOYS: Dict[str, Dict[str, float]] = {
    "aluminium": {
        "T_liq": 660.0, "T_sol": 580.0,
        "L": 397_000.0, "k": 160.0, "cp": 900.0, "rho": 2700.0,
    },
    "steel": {
        "T_liq": 1500.0, "T_sol": 1400.0,
        "L": 272_000.0, "k": 35.0, "cp": 600.0, "rho": 7850.0,
    },
    "bronze": {
        "T_liq": 1000.0, "T_sol": 880.0,
        "L": 180_000.0, "k": 50.0, "cp": 380.0, "rho": 8800.0,
    },
    "za": {
        # ZA-8 / ZA-12 zinc-aluminium die-casting alloy
        "T_liq": 404.0, "T_sol": 375.0,
        "L": 113_000.0, "k": 115.0, "cp": 420.0, "rho": 6300.0,
    },
}

# Convenience aliases accepted by the public API
_ALLOY_ALIASES: Dict[str, str] = {
    "al": "aluminium",
    "aluminum": "aluminium",
    "aluminium_alloy": "aluminium",
    "steel_carbon": "steel",
    "carbon_steel": "steel",
    "cast_steel": "steel",
    "bronze_alloy": "bronze",
    "za8": "za",
    "za12": "za",
    "zinc_aluminium": "za",
}


def _resolve_alloy(name: str) -> Optional[str]:
    key = name.strip().lower()
    if key in _ALLOYS:
        return key
    return _ALLOY_ALIASES.get(key)


def alloy_properties(name: str) -> Dict[str, Any]:
    """Return thermo-physical properties for *name*.

    Returns
    -------
    dict with ok=True and keys: T_liq, T_sol, L, k, cp, rho, alpha_m2_s.
    Returns ok=False with reason on unknown alloy.  Never raises.
    """
    try:
        key = _resolve_alloy(name)
        if key is None:
            known = sorted(_ALLOYS.keys()) + sorted(_ALLOY_ALIASES.keys())
            return {"ok": False, "reason": f"unknown alloy '{name}'. Known: {known}"}
        p = _ALLOYS[key]
        alpha = p["k"] / (p["rho"] * p["cp"])
        return {
            "ok": True,
            "canonical_name": key,
            "T_liq": p["T_liq"],
            "T_sol": p["T_sol"],
            "L": p["L"],
            "k": p["k"],
            "cp": p["cp"],
            "rho": p["rho"],
            "alpha_m2_s": alpha,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Enthalpy ↔ temperature / solid-fraction helpers
# ---------------------------------------------------------------------------

def _H_from_T(T: float, T_liq: float, T_sol: float,
              cp: float, L: float) -> float:
    """Enthalpy [J·kg⁻¹] relative to solidus, from temperature [°C].

    Below solidus  : H = cp * (T - T_sol)
    Mushy zone     : H = cp * (T - T_sol) + L * (T - T_sol)/(T_liq - T_sol)
    Above liquidus : H = cp * (T - T_sol) + L
    """
    if T <= T_sol:
        return cp * (T - T_sol)
    if T >= T_liq:
        dT = T_liq - T_sol
        return cp * (T - T_sol) + L
    # mushy zone
    f_l = (T - T_sol) / (T_liq - T_sol)  # liquid fraction
    return cp * (T - T_sol) + L * f_l


def _T_and_fs_from_H(H: float, T_liq: float, T_sol: float,
                     cp: float, L: float) -> Tuple[float, float]:
    """Recover temperature [°C] and solid fraction [0..1] from enthalpy.

    Returns (T, f_s) where f_s = 1 means fully solid.
    """
    dT_range = T_liq - T_sol if T_liq > T_sol else 1e-9

    # Fully solid
    if H <= 0.0:
        T = T_sol + H / cp
        return T, 1.0

    # Fully liquid
    if H >= L + cp * (T_liq - T_sol):
        T = T_sol + (H - L) / cp
        return T, 0.0

    # Mushy zone: H = cp*(T - T_sol) + L*(T - T_sol)/dT_range
    #  H = (T - T_sol) * (cp + L/dT_range)
    T = T_sol + H / (cp + L / dT_range)
    f_l = (T - T_sol) / dT_range
    f_l = max(0.0, min(1.0, f_l))
    return T, 1.0 - f_l


# ---------------------------------------------------------------------------
# Chvorinov cross-check helper
# ---------------------------------------------------------------------------

def chvorinov_time(V_m3: float, A_m2: float,
                   B: float = 600.0, n: float = 2.0) -> float:
    """Chvorinov's rule: t = B · (V/A)^n  [seconds]."""
    if V_m3 <= 0.0 or A_m2 <= 0.0 or B <= 0.0 or n <= 0.0:
        return float("nan")
    return B * (V_m3 / A_m2) ** n


# ---------------------------------------------------------------------------
# 1-D solidification solver
# ---------------------------------------------------------------------------

def solidify_1d(
    length_m: float,
    n_cells: int,
    dt: float,
    n_steps: int,
    alloy: str = "aluminium",
    T_pour: float = 720.0,
    T_mold: float = 25.0,
    h_interface: float = 1000.0,
    probes: Optional[Sequence[float]] = None,
    use_latent: bool = True,
) -> Dict[str, Any]:
    """1-D transient solidification on a bar domain [0, length_m].

    The casting occupies the full domain.  Both ends are Robin boundaries
    (mold interface).  Interior uses explicit finite-difference heat equation
    with enthalpy to handle latent heat.

    Parameters
    ----------
    length_m    : domain length [m]
    n_cells     : number of uniform finite-difference cells
    dt          : time step [s]
    n_steps     : total number of time steps to march
    alloy       : alloy name (see alloy_properties)
    T_pour      : initial uniform temperature of the melt [°C]
    T_mold      : mold temperature held constant at both ends [°C]
    h_interface : heat-transfer coefficient at mold/metal interface [W·m⁻²·K⁻¹]
    probes      : list of positions [m] at which to record cooling curves;
                  defaults to [0.0, length_m/2, length_m]
    use_latent  : if False, set L=0 (for latent-heat comparison tests)

    Returns
    -------
    dict with ok=True and fields:
      cells_x          — list of cell-centre x positions [m]
      solidification_time_s — per-cell time at which f_s first reaches 1.0 (None = not yet)
      final_solid_fraction  — f_s at each cell at end of simulation [0..1]
      thermal_modulus       — modulus proxy per cell: cell half-length (for 1-D)
      hot_spot_index        — index of cell that solidifies last (max solid. time)
      hot_spot_x            — position [m] of hot-spot cell
      cooling_curves        — {probe_x: [(time_s, T_C), ...]} for each probe
      total_time_s          — total simulated time [s]
      cfl_fourier           — Fourier number per step (stability indicator; ≤0.5 required)
      dt_s                  — actual time step used [s]
      warnings              — list of string warnings
    """
    try:
        return _solidify_1d_inner(
            length_m=length_m, n_cells=n_cells, dt=dt, n_steps=n_steps,
            alloy=alloy, T_pour=T_pour, T_mold=T_mold,
            h_interface=h_interface, probes=probes, use_latent=use_latent,
        )
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _solidify_1d_inner(
    length_m, n_cells, dt, n_steps, alloy, T_pour, T_mold,
    h_interface, probes, use_latent,
) -> Dict[str, Any]:
    # -- Validate inputs -------------------------------------------------- #
    if length_m <= 0.0:
        return {"ok": False, "reason": "length_m must be > 0"}
    if n_cells < 2:
        return {"ok": False, "reason": "n_cells must be >= 2"}
    if dt <= 0.0:
        return {"ok": False, "reason": "dt must be > 0"}
    if n_steps < 1:
        return {"ok": False, "reason": "n_steps must be >= 1"}
    if h_interface < 0.0:
        return {"ok": False, "reason": "h_interface must be >= 0"}

    ap = alloy_properties(alloy)
    if not ap["ok"]:
        return ap  # propagate error

    T_liq = ap["T_liq"]
    T_sol = ap["T_sol"]
    L     = ap["L"] if use_latent else 0.0
    k     = ap["k"]
    cp    = ap["cp"]
    rho   = ap["rho"]
    alpha = k / (rho * cp)

    dx = length_m / n_cells
    warnings: List[str] = []

    # CFL/Fourier stability check for explicit scheme
    fo = alpha * dt / (dx * dx)
    if fo > 0.5:
        warnings.append(
            f"Fourier number {fo:.4f} > 0.5 — explicit scheme may be unstable. "
            f"Reduce dt or increase n_cells."
        )

    if T_pour < T_liq:
        warnings.append(
            f"T_pour ({T_pour}°C) < T_liq ({T_liq}°C) — melt is below liquidus at pour."
        )

    # Cell centres
    xs = [dx * (i + 0.5) for i in range(n_cells)]

    # Probe setup: snap each probe position to nearest cell index
    if probes is None:
        probes = [0.0, length_m / 2.0, length_m]
    probe_indices: List[int] = []
    probe_xs: List[float] = []
    for px in probes:
        idx = min(range(n_cells), key=lambda i: abs(xs[i] - px))
        if idx not in probe_indices:
            probe_indices.append(idx)
            probe_xs.append(xs[idx])

    cooling_curves: Dict[float, List[Tuple[float, float]]] = {
        px: [] for px in probe_xs
    }

    # Initialise enthalpy field
    H = [_H_from_T(T_pour, T_liq, T_sol, cp, L) for _ in range(n_cells)]

    # Per-cell solidification time (set when f_s first reaches 1.0)
    sol_time: List[Optional[float]] = [None] * n_cells

    # Advance in time
    for step in range(n_steps):
        t = step * dt
        H_new = list(H)

        for i in range(n_cells):
            T_i, _ = _T_and_fs_from_H(H[i], T_liq, T_sol, cp, L)

            # Left neighbour flux
            if i == 0:
                # Robin BC: left mold interface
                q_left = h_interface * (T_mold - T_i)  # W·m⁻²
            else:
                T_im1, _ = _T_and_fs_from_H(H[i - 1], T_liq, T_sol, cp, L)
                q_left = k * (T_im1 - T_i) / dx

            # Right neighbour flux
            if i == n_cells - 1:
                # Robin BC: right mold interface
                q_right = h_interface * (T_mold - T_i)
            else:
                T_ip1, _ = _T_and_fs_from_H(H[i + 1], T_liq, T_sol, cp, L)
                q_right = k * (T_ip1 - T_i) / dx

            # Net heat flux → enthalpy rate  (rho * dH/dt = div·q)
            dH_dt = (q_left + q_right) / (rho * dx)
            H_new[i] = H[i] + dt * dH_dt

        H = H_new

        # Record cooling curves and solidification times
        for ci, px in zip(probe_indices, probe_xs):
            T_ci, _ = _T_and_fs_from_H(H[ci], T_liq, T_sol, cp, L)
            cooling_curves[px].append((t + dt, T_ci))

        for i in range(n_cells):
            if sol_time[i] is None:
                _, fs = _T_and_fs_from_H(H[i], T_liq, T_sol, cp, L)
                if fs >= 1.0:
                    sol_time[i] = t + dt

    # Final solid fraction
    final_fs = []
    for i in range(n_cells):
        _, fs = _T_and_fs_from_H(H[i], T_liq, T_sol, cp, L)
        final_fs.append(fs)

    # Hot-spot: cell with the latest (maximum) solidification time
    # Cells that have not yet solidified by end of sim get time = total_time+dt
    total_time = n_steps * dt
    effective_sol = [
        (st if st is not None else total_time + dt)
        for st in sol_time
    ]
    hot_spot_index = max(range(n_cells), key=lambda i: effective_sol[i])
    hot_spot_x = xs[hot_spot_index]

    # Thermal modulus proxy for 1-D: distance from cell centre to nearest
    # cooling boundary.  Interior cells are farthest from the boundary and
    # therefore have the highest modulus (last to freeze = hot-spot).
    thermal_modulus = []
    for i in range(n_cells):
        # Distance to nearest end (in cells), plus half a cell for the centre
        dist = (min(i, n_cells - 1 - i) + 0.5) * dx
        thermal_modulus.append(dist)

    return {
        "ok": True,
        "cells_x": xs,
        "solidification_time_s": sol_time,
        "final_solid_fraction": final_fs,
        "thermal_modulus": thermal_modulus,
        "hot_spot_index": hot_spot_index,
        "hot_spot_x": hot_spot_x,
        "cooling_curves": cooling_curves,
        "total_time_s": total_time,
        "cfl_fourier": fo,
        "dt_s": dt,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2-D solidification solver
# ---------------------------------------------------------------------------

def solidify_2d(
    grid: Tuple[int, int, float, float],
    dt: float,
    n_steps: int,
    alloy: str = "aluminium",
    T_pour: float = 720.0,
    T_mold: float = 25.0,
    h_interface: float = 1000.0,
    probes: Optional[Sequence[Tuple[float, float]]] = None,
    use_latent: bool = True,
) -> Dict[str, Any]:
    """2-D transient solidification on a rectangular casting domain.

    Parameters
    ----------
    grid        : (nx, ny, dx, dy) — number of cells and cell dimensions [m]
    dt          : time step [s]
    n_steps     : total number of time steps
    alloy       : alloy name
    T_pour      : initial melt temperature [°C]
    T_mold      : constant mold temperature at all domain boundaries [°C]
    h_interface : heat-transfer coefficient at mold/metal interface [W·m⁻²·K⁻¹]
    probes      : list of (x, y) positions [m] for cooling curve sampling;
                  defaults to corners + centre
    use_latent  : if False, set L=0

    Returns
    -------
    dict with ok=True and 2-D field outputs:
      cells_xy             — flat list of (x, y) cell-centre positions, row-major (y outer)
      solidification_time_s — flat list (None = not solidified)
      final_solid_fraction  — flat list [0..1]
      thermal_modulus       — flat list: effective V/A modulus proxy [m]
      hot_spot_index        — flat index of last-to-freeze cell
      hot_spot_xy           — (x, y) of hot-spot
      cooling_curves        — {(x,y): [(t_s, T_C), ...]}
      total_time_s          — total simulated time [s]
      cfl_fourier_x         — Fourier number in x
      cfl_fourier_y         — Fourier number in y
      dt_s                  — actual time step used [s]
      warnings              — list of string warnings
    """
    try:
        return _solidify_2d_inner(
            grid=grid, dt=dt, n_steps=n_steps,
            alloy=alloy, T_pour=T_pour, T_mold=T_mold,
            h_interface=h_interface, probes=probes, use_latent=use_latent,
        )
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _solidify_2d_inner(
    grid, dt, n_steps, alloy, T_pour, T_mold, h_interface, probes, use_latent,
) -> Dict[str, Any]:
    nx, ny, dx, dy = grid
    nx = int(nx)
    ny = int(ny)

    if nx < 2 or ny < 2:
        return {"ok": False, "reason": "grid must have nx>=2 and ny>=2"}
    if dx <= 0.0 or dy <= 0.0:
        return {"ok": False, "reason": "dx and dy must be > 0"}
    if dt <= 0.0:
        return {"ok": False, "reason": "dt must be > 0"}
    if n_steps < 1:
        return {"ok": False, "reason": "n_steps must be >= 1"}
    if h_interface < 0.0:
        return {"ok": False, "reason": "h_interface must be >= 0"}

    ap = alloy_properties(alloy)
    if not ap["ok"]:
        return ap

    T_liq = ap["T_liq"]
    T_sol = ap["T_sol"]
    L     = ap["L"] if use_latent else 0.0
    k     = ap["k"]
    cp    = ap["cp"]
    rho   = ap["rho"]

    warnings: List[str] = []

    alpha = k / (rho * cp)
    fo_x  = alpha * dt / (dx * dx)
    fo_y  = alpha * dt / (dy * dy)
    if fo_x + fo_y > 0.5:
        warnings.append(
            f"2-D Fourier number fo_x+fo_y = {fo_x+fo_y:.4f} > 0.5 — "
            "scheme may be unstable."
        )

    if T_pour < T_liq:
        warnings.append(
            f"T_pour ({T_pour}°C) < T_liq ({T_liq}°C) — melt below liquidus at pour."
        )

    # Cell centres: row-major indexing → flat index = j*nx + i
    # i = x-index (0..nx-1), j = y-index (0..ny-1)
    def _idx(i: int, j: int) -> int:
        return j * nx + i

    xs_c = [dx * (i + 0.5) for i in range(nx)]
    ys_c = [dy * (j + 0.5) for j in range(ny)]
    cells_xy = [(xs_c[i], ys_c[j]) for j in range(ny) for i in range(nx)]

    # Probe setup: snap to nearest cell
    if probes is None:
        probes = [
            (xs_c[0],      ys_c[0]),
            (xs_c[nx - 1], ys_c[0]),
            (xs_c[0],      ys_c[ny - 1]),
            (xs_c[nx - 1], ys_c[ny - 1]),
            (xs_c[nx // 2], ys_c[ny // 2]),
        ]

    def _snap(px: float, py: float) -> int:
        best = 0
        best_d = float("inf")
        for j in range(ny):
            for i in range(nx):
                d = (xs_c[i] - px) ** 2 + (ys_c[j] - py) ** 2
                if d < best_d:
                    best_d = d
                    best = _idx(i, j)
        return best

    probe_flat: List[Tuple[Tuple[float, float], int]] = []
    seen: set = set()
    for px, py in probes:
        fi = _snap(px, py)
        if fi not in seen:
            seen.add(fi)
            cx, cy = cells_xy[fi]
            probe_flat.append(((cx, cy), fi))

    cooling_curves: Dict[Tuple[float, float], List[Tuple[float, float]]] = {
        key: [] for key, _ in probe_flat
    }

    # Initialise enthalpy
    N = nx * ny
    H = [_H_from_T(T_pour, T_liq, T_sol, cp, L)] * N
    sol_time: List[Optional[float]] = [None] * N

    for step in range(n_steps):
        t = step * dt
        H_new = list(H)

        for j in range(ny):
            for i in range(nx):
                fi = _idx(i, j)
                T_ij, _ = _T_and_fs_from_H(H[fi], T_liq, T_sol, cp, L)

                # x-fluxes
                if i == 0:
                    q_xm = h_interface * (T_mold - T_ij)
                else:
                    T_l, _ = _T_and_fs_from_H(H[_idx(i - 1, j)], T_liq, T_sol, cp, L)
                    q_xm = k * (T_l - T_ij) / dx

                if i == nx - 1:
                    q_xp = h_interface * (T_mold - T_ij)
                else:
                    T_r, _ = _T_and_fs_from_H(H[_idx(i + 1, j)], T_liq, T_sol, cp, L)
                    q_xp = k * (T_r - T_ij) / dx

                # y-fluxes
                if j == 0:
                    q_ym = h_interface * (T_mold - T_ij)
                else:
                    T_d, _ = _T_and_fs_from_H(H[_idx(i, j - 1)], T_liq, T_sol, cp, L)
                    q_ym = k * (T_d - T_ij) / dy

                if j == ny - 1:
                    q_yp = h_interface * (T_mold - T_ij)
                else:
                    T_u, _ = _T_and_fs_from_H(H[_idx(i, j + 1)], T_liq, T_sol, cp, L)
                    q_yp = k * (T_u - T_ij) / dy

                dH_dt = (q_xm + q_xp) / (rho * dx) + (q_ym + q_yp) / (rho * dy)
                H_new[fi] = H[fi] + dt * dH_dt

        H = H_new

        t_next = t + dt
        for (px, py), fi in probe_flat:
            T_fi, _ = _T_and_fs_from_H(H[fi], T_liq, T_sol, cp, L)
            cooling_curves[(px, py)].append((t_next, T_fi))

        for fi in range(N):
            if sol_time[fi] is None:
                _, fs = _T_and_fs_from_H(H[fi], T_liq, T_sol, cp, L)
                if fs >= 1.0:
                    sol_time[fi] = t_next

    # Final solid fraction
    final_fs = []
    for fi in range(N):
        _, fs = _T_and_fs_from_H(H[fi], T_liq, T_sol, cp, L)
        final_fs.append(fs)

    total_time = n_steps * dt
    effective_sol = [
        (st if st is not None else total_time + dt)
        for st in sol_time
    ]
    hot_spot_index = max(range(N), key=lambda i: effective_sol[i])
    hot_spot_xy = cells_xy[hot_spot_index]

    # Thermal modulus proxy: minimum distance from the cell centre to the
    # nearest cooling boundary in each axis.  Interior cells have the largest
    # modulus (farthest from any cooling surface) and solidify last.
    # mod = min( dist_x_to_nearest_boundary, dist_y_to_nearest_boundary )
    # where dist = (min_idx + 0.5) * cell_size
    thermal_modulus = []
    for j in range(ny):
        for i in range(nx):
            dist_x = (min(i, nx - 1 - i) + 0.5) * dx
            dist_y = (min(j, ny - 1 - j) + 0.5) * dy
            mod = min(dist_x, dist_y)
            thermal_modulus.append(mod)

    return {
        "ok": True,
        "cells_xy": cells_xy,
        "solidification_time_s": sol_time,
        "final_solid_fraction": final_fs,
        "thermal_modulus": thermal_modulus,
        "hot_spot_index": hot_spot_index,
        "hot_spot_xy": hot_spot_xy,
        "cooling_curves": cooling_curves,
        "total_time_s": total_time,
        "cfl_fourier_x": fo_x,
        "cfl_fourier_y": fo_y,
        "dt_s": dt,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# LLM tool wrappers (gated on kerf_chat / kerf_core availability)
# ---------------------------------------------------------------------------

try:
    import json as _json
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False

if _REGISTRY_AVAILABLE:

    # ------------------------------------------------------------------ #
    # solidification_alloy_properties                                      #
    # ------------------------------------------------------------------ #

    _alloy_props_spec = ToolSpec(
        name="solidification_alloy_properties",
        description=(
            "Return thermo-physical properties for a casting alloy used in\n"
            "solidification simulation.\n"
            "\n"
            "Returns T_liq, T_sol, L (latent heat), k (conductivity), cp, rho,\n"
            "and alpha (thermal diffusivity).\n"
            "\n"
            "Supported alloys: aluminium, steel, bronze, za (zinc-aluminium).\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "alloy": {
                    "type": "string",
                    "description": (
                        "Alloy name. Supported: 'aluminium', 'steel', 'bronze', 'za'."
                    ),
                },
            },
            "required": ["alloy"],
        },
    )

    @register(_alloy_props_spec, write=False)
    async def run_alloy_properties(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        if not a.get("alloy"):
            return _json.dumps({"ok": False, "reason": "alloy is required"})
        result = alloy_properties(a["alloy"])
        return ok_payload(result) if result["ok"] else _json.dumps(result)

    # ------------------------------------------------------------------ #
    # solidification_run_1d                                                #
    # ------------------------------------------------------------------ #

    _solidify_1d_spec = ToolSpec(
        name="solidification_run_1d",
        description=(
            "Run a 1-D transient casting solidification simulation.\n"
            "\n"
            "Uses the enthalpy method with explicit finite differences to model\n"
            "heat conduction and latent-heat release in a bar-shaped casting.\n"
            "Returns per-cell solid fraction, solidification times, hot-spot\n"
            "location, thermal modulus map, and cooling curves at probe points.\n"
            "\n"
            "Cross-check: compare solidification_time_s[hot_spot] with\n"
            "Chvorinov's rule t = B*(V/A)^2.\n"
            "\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "length_m": {
                    "type": "number",
                    "description": "Casting bar length [m]. Must be > 0.",
                },
                "n_cells": {
                    "type": "integer",
                    "description": "Number of finite-difference cells (>=2).",
                },
                "dt": {
                    "type": "number",
                    "description": "Time step [s]. Must be > 0.",
                },
                "n_steps": {
                    "type": "integer",
                    "description": "Number of time steps to march.",
                },
                "alloy": {
                    "type": "string",
                    "description": "Alloy name: 'aluminium', 'steel', 'bronze', 'za'.",
                },
                "T_pour": {
                    "type": "number",
                    "description": "Initial pour temperature [°C].",
                },
                "T_mold": {
                    "type": "number",
                    "description": "Constant mold temperature [°C]. Default 25.",
                },
                "h_interface": {
                    "type": "number",
                    "description": "Mold/metal interface heat-transfer coefficient [W·m⁻²·K⁻¹].",
                },
                "probes": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Probe positions [m] for cooling curves.",
                },
                "use_latent": {
                    "type": "boolean",
                    "description": "Include latent heat (default true).",
                },
            },
            "required": ["length_m", "n_cells", "dt", "n_steps"],
        },
    )

    @register(_solidify_1d_spec, write=False)
    async def run_solidify_1d(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("length_m", "n_cells", "dt", "n_steps"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        kwargs: dict = {}
        for opt in ("alloy", "T_pour", "T_mold", "h_interface", "probes", "use_latent"):
            if opt in a:
                kwargs[opt] = a[opt]
        result = solidify_1d(
            length_m=a["length_m"],
            n_cells=int(a["n_cells"]),
            dt=a["dt"],
            n_steps=int(a["n_steps"]),
            **kwargs,
        )
        return ok_payload(result) if result["ok"] else _json.dumps(result)

    # ------------------------------------------------------------------ #
    # solidification_run_2d                                                #
    # ------------------------------------------------------------------ #

    _solidify_2d_spec = ToolSpec(
        name="solidification_run_2d",
        description=(
            "Run a 2-D transient casting solidification simulation on a\n"
            "rectangular domain.\n"
            "\n"
            "Uses the enthalpy method with explicit 2-D finite differences.\n"
            "All four edges are mold boundaries (Robin BC).\n"
            "Returns flat-list per-cell fields and cooling curves at probes.\n"
            "\n"
            "Hot-spot (last region to freeze) predicts shrinkage-porosity risk.\n"
            "\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "nx": {
                    "type": "integer",
                    "description": "Number of cells in x direction (>=2).",
                },
                "ny": {
                    "type": "integer",
                    "description": "Number of cells in y direction (>=2).",
                },
                "dx": {
                    "type": "number",
                    "description": "Cell width in x [m]. Must be > 0.",
                },
                "dy": {
                    "type": "number",
                    "description": "Cell height in y [m]. Must be > 0.",
                },
                "dt": {
                    "type": "number",
                    "description": "Time step [s]. Must be > 0.",
                },
                "n_steps": {
                    "type": "integer",
                    "description": "Number of time steps.",
                },
                "alloy": {
                    "type": "string",
                    "description": "Alloy name.",
                },
                "T_pour": {
                    "type": "number",
                    "description": "Pour temperature [°C].",
                },
                "T_mold": {
                    "type": "number",
                    "description": "Mold temperature [°C].",
                },
                "h_interface": {
                    "type": "number",
                    "description": "Interface heat-transfer coefficient [W·m⁻²·K⁻¹].",
                },
                "probes": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "description": "List of [x, y] probe positions [m].",
                },
                "use_latent": {
                    "type": "boolean",
                    "description": "Include latent heat (default true).",
                },
            },
            "required": ["nx", "ny", "dx", "dy", "dt", "n_steps"],
        },
    )

    @register(_solidify_2d_spec, write=False)
    async def run_solidify_2d(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("nx", "ny", "dx", "dy", "dt", "n_steps"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        grid = (int(a["nx"]), int(a["ny"]), float(a["dx"]), float(a["dy"]))
        kwargs: dict = {}
        for opt in ("alloy", "T_pour", "T_mold", "h_interface", "use_latent"):
            if opt in a:
                kwargs[opt] = a[opt]
        if "probes" in a:
            kwargs["probes"] = [tuple(p) for p in a["probes"]]
        result = solidify_2d(
            grid=grid,
            dt=float(a["dt"]),
            n_steps=int(a["n_steps"]),
            **kwargs,
        )
        return ok_payload(result) if result["ok"] else _json.dumps(result)
