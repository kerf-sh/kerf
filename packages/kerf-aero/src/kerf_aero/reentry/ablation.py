"""
kerf_aero.reentry.ablation — 1-D transient heat-conduction + ablation solver.

Method
------
Finite-difference (explicit) 1-D transient heat conduction through a
multi-layer TPS stack with an energy-balance ablation boundary condition
at the surface.

The ablation front is tracked via an energy-balance moving-boundary model:
the surface is held at the ablation temperature T_abl when the net
inbound flux exceeds the re-radiation and ablation energy demand; surplus
energy drives mass loss at a rate

    ṁ" = (q_net − q_rad) / h_abl      [kg/(m²·s)]

and the surface recedes at

    ṡ = ṁ" / ρ_eff                     [m/s]

where ρ_eff = (ρ_virgin + ρ_char) / 2 is the effective density during
charring.  This is a simplified ``B-prime'' (B') model adequate for a
first-pass 1-D analysis.

Nodes are fixed in space (Eulerian); the ablation front position is tracked
as a continuous variable and the outermost nodes are removed when the surface
recedes past them.

Discretisation
--------------
Interior nodes (Fourier explicit):

    ρ·cp·ΔT/Δt = k·(T_{i+1} − 2·T_i + T_{i-1}) / Δx²

Surface node (energy balance):

    q_in = q_reradiation + q_conduction + q_ablation

    q_in(t)     — imposed heat flux [W/m²]
    q_rerad     = ε·σ·T_s⁴               [W/m²]  re-radiation loss
    q_cond      = k·(T_s − T_1) / Δx    [W/m²]  conduction into stack
    q_abl       = ṁ"·h_abl              [W/m²]  ablation energy sink

When T_s < T_abl (no ablation), the surface BC switches to a pure
conduction + re-radiation balance and T_s is solved from the energy balance
implicitly (Newton's method, 1-node).

Stability
---------
The explicit Fourier method requires Δt ≤ Δx²·ρ·cp / (2·k) for each layer.
The solver automatically clips Δt to the minimum stability limit across all
layers.

Output
------
:class:`AblationResult` — surface temperature, recession depth, bondline
temperature, and total ablated mass, all as time-series arrays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from kerf_aero.reentry.materials import MaterialProperties
from kerf_aero.reentry.tps_stack import TPSStack, StackLayer


SIGMA: float = 5.6704e-8   # Stefan–Boltzmann constant [W/(m²·K⁴)]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class AblationResult:
    """Time-series output from the ablation solver.

    Attributes
    ----------
    times : list[float]
        Time samples [s].
    T_surface : list[float]
        Surface temperature at each time [K].
    recession_m : list[float]
        Cumulative recession depth at each time [m].
    T_bondline : list[float]
        Temperature at the back-face (bondline) at each time [K].
    ablated_mass_kg_m2 : list[float]
        Cumulative ablated mass per unit area [kg/m²].
    T_full : list[list[float]]
        Full temperature profile at each time step (optional; may be empty
        if store_full_profile=False to save memory).
    """

    times: list[float] = field(default_factory=list)
    T_surface: list[float] = field(default_factory=list)
    recession_m: list[float] = field(default_factory=list)
    T_bondline: list[float] = field(default_factory=list)
    ablated_mass_kg_m2: list[float] = field(default_factory=list)
    T_full: list[list[float]] = field(default_factory=list)

    @property
    def peak_surface_temp(self) -> float:
        """Peak surface temperature [K]."""
        return max(self.T_surface) if self.T_surface else 0.0

    @property
    def total_recession_m(self) -> float:
        """Total ablation recession depth [m]."""
        return self.recession_m[-1] if self.recession_m else 0.0

    @property
    def peak_bondline_temp(self) -> float:
        """Peak bondline (back-face) temperature [K]."""
        return max(self.T_bondline) if self.T_bondline else 0.0

    @property
    def total_ablated_mass_kg_m2(self) -> float:
        """Total ablated mass per unit area [kg/m²]."""
        return self.ablated_mass_kg_m2[-1] if self.ablated_mass_kg_m2 else 0.0


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def _interp_flux(flux_profile: list[tuple[float, float]], t: float) -> float:
    """Linearly interpolate heat flux at time t from the profile table."""
    if t <= flux_profile[0][0]:
        return flux_profile[0][1]
    if t >= flux_profile[-1][0]:
        return flux_profile[-1][1]
    for i in range(len(flux_profile) - 1):
        t0, q0 = flux_profile[i]
        t1, q1 = flux_profile[i + 1]
        if t0 <= t <= t1:
            alpha = (t - t0) / (t1 - t0)
            return q0 + alpha * (q1 - q0)
    return flux_profile[-1][1]


def _stability_dt(
    nodes_mat: list[MaterialProperties],
    dx_per_node: list[float],
    safety: float = 0.45,
) -> float:
    """Compute maximum stable explicit time-step across all nodes."""
    dt_min = 1e9
    for mat, dx in zip(nodes_mat, dx_per_node):
        alpha = mat.k / (mat.rho_virgin * mat.cp)  # thermal diffusivity
        dt_lim = safety * dx**2 / alpha
        if dt_lim < dt_min:
            dt_min = dt_lim
    return dt_min


def _surface_temperature_no_ablation(
    q_in: float,
    T_1: float,
    k_surface: float,
    dx: float,
    emissivity: float,
    T_init: float,
    max_iter: int = 50,
    tol: float = 1.0,
) -> float:
    """Solve for surface temperature when no ablation occurs (Newton iteration).

    Energy balance at surface node:
        q_in = ε·σ·T_s⁴ + k·(T_s − T_1)/Δx

    Parameters
    ----------
    q_in : float
        Incoming heat flux [W/m²].
    T_1 : float
        Temperature of next interior node [K].
    k_surface : float
        Thermal conductivity at surface [W/(m·K)].
    dx : float
        Spacing between surface and first interior node [m].
    emissivity : float
        Surface emissivity.
    T_init : float
        Initial guess for T_s [K].
    """
    T_s = T_init
    k_over_dx = k_surface / dx
    for _ in range(max_iter):
        f = emissivity * SIGMA * T_s**4 + k_over_dx * (T_s - T_1) - q_in
        df = 4.0 * emissivity * SIGMA * T_s**3 + k_over_dx
        dT = -f / df
        T_s += dT
        if abs(dT) < tol:
            break
        if T_s < 100.0:
            T_s = 100.0
    return T_s


def solve(
    stack: TPSStack,
    flux_profile: list[tuple[float, float]],
    T_initial: float = 300.0,
    dt_max: float | None = None,
    store_full_profile: bool = False,
    enable_ablation: bool = True,
    output_interval: float = 1.0,
) -> AblationResult:
    """Run the 1-D transient ablation solver.

    Parameters
    ----------
    stack : TPSStack
        Multi-layer TPS stack (outermost layer first).
    flux_profile : list of (t, q) tuples
        Heat-flux time-history [W/m²] as (time_s, flux_W_m2) pairs.
        Must be monotonically increasing in time.
    T_initial : float
        Uniform initial temperature [K].
    dt_max : float or None
        Maximum allowed time step [s].  If None the stability limit is used.
    store_full_profile : bool
        If True, store the full temperature profile at each output time.
    enable_ablation : bool
        If False, the ablation front is disabled (pure conduction + re-radiation).
        Surface temperature floats freely above T_abl.
    output_interval : float
        Interval between saved output snapshots [s].

    Returns
    -------
    AblationResult
    """
    if not stack.layers:
        raise ValueError("TPSStack has no layers.")
    if len(flux_profile) < 2:
        raise ValueError("flux_profile must have at least 2 points.")

    # ------------------------------------------------------------------
    # Build nodal arrays
    # ------------------------------------------------------------------
    # Nodes are built per-layer, sharing boundary nodes between layers.
    # We store: position, temperature, material, dx_left, dx_right.

    positions = stack.node_positions()           # absolute depth [m] from surface
    materials = stack.node_materials()
    N = len(positions)

    if N < 2:
        raise ValueError("Stack must produce at least 2 nodes.")

    # Node spacing (for conduction flux calculations)
    # dx[i] = distance from node i to node i+1
    dx = [positions[i + 1] - positions[i] for i in range(N - 1)]

    # Initial temperature field
    T = [T_initial] * N

    # ------------------------------------------------------------------
    # Time-stepping setup
    # ------------------------------------------------------------------
    # Per-node dx for stability calculation (use midpoint spacing)
    dx_per_node = [dx[0]] + [
        0.5 * (dx[i - 1] + dx[i]) for i in range(1, N - 1)
    ] + [dx[-1]]

    dt_stable = _stability_dt(materials, dx_per_node)
    if dt_max is not None:
        dt = min(dt_max, dt_stable)
    else:
        dt = dt_stable

    t_start = flux_profile[0][0]
    t_end = flux_profile[-1][0]

    # ------------------------------------------------------------------
    # Tracking variables
    # ------------------------------------------------------------------
    result = AblationResult()
    recession = 0.0         # cumulative recession [m]
    ablated_mass = 0.0      # kg/m²
    surface_node_offset = 0 # index of first active node

    t = t_start
    t_last_output = t_start - output_interval   # force first output

    # Surface material (outermost layer)
    surf_mat = stack.layers[0].material

    # ------------------------------------------------------------------
    # Main integration loop
    # ------------------------------------------------------------------
    while t <= t_end + 1e-12:

        # ---- Save output snapshot ----
        if t >= t_last_output + output_interval - 1e-9:
            s = surface_node_offset
            T_surf = T[s]
            T_bond = T[-1]
            result.times.append(t)
            result.T_surface.append(T_surf)
            result.recession_m.append(recession)
            result.T_bondline.append(T_bond)
            result.ablated_mass_kg_m2.append(ablated_mass)
            if store_full_profile:
                result.T_full.append(list(T))
            t_last_output = t

        # ---- Interpolate incoming flux ----
        q_in = _interp_flux(flux_profile, t)

        # ---- Surface boundary condition ----
        s = surface_node_offset   # index of current surface node
        mat_s = materials[s]
        T_s = T[s]
        T_1 = T[s + 1] if s + 1 < N else T[s]
        dx_s = dx[s] if s < len(dx) else dx[-1]

        q_rerad = mat_s.emissivity * SIGMA * T_s**4
        q_cond = mat_s.k * (T_s - T_1) / dx_s   # into the stack

        if enable_ablation and T_s >= mat_s.T_ablation and mat_s.h_ablation > 0.0:
            # Ablating regime: surface held at T_abl; excess flux → mass loss
            T[s] = mat_s.T_ablation
            q_net = q_in - q_rerad - q_cond
            if q_net > 0.0:
                rho_eff = 0.5 * (mat_s.rho_virgin + mat_s.rho_char)
                mdot = q_net / mat_s.h_ablation          # kg/(m²·s)
                recession_rate = mdot / rho_eff          # m/s
                recession += recession_rate * dt
                ablated_mass += mdot * dt
        else:
            # Non-ablating regime: solve for T_s from energy balance
            T_s_new = _surface_temperature_no_ablation(
                q_in, T_1, mat_s.k, dx_s, mat_s.emissivity, T_s
            )
            T[s] = T_s_new

        # ---- Interior nodes: explicit Fourier update ----
        T_new = list(T)
        for i in range(s + 1, N - 1):
            mat = materials[i]
            alpha = mat.k / (mat.rho_virgin * mat.cp)
            dx_l = dx[i - 1]
            dx_r = dx[i]
            dx_avg = 0.5 * (dx_l + dx_r)
            # Non-uniform spacing: central difference
            d2T = (T[i + 1] - T[i]) / dx_r - (T[i] - T[i - 1]) / dx_l
            d2T /= dx_avg
            T_new[i] = T[i] + dt * alpha * d2T

        # ---- Back-face (bondline) — insulated (adiabatic) ----
        # Real structure would have convective or radiative BC; we use
        # adiabatic for worst-case bondline temperature estimate.
        T_new[N - 1] = T_new[N - 2]  # zero-gradient BC

        T = T_new

        # ---- Remove nodes consumed by recession ----
        # When the recession depth exceeds the position of the first
        # remaining node, that node is gone.
        while surface_node_offset < N - 2:
            if recession >= positions[surface_node_offset]:
                surface_node_offset += 1
            else:
                break

        # ---- Advance time ----
        t += dt

    # Ensure the final state is recorded
    s = surface_node_offset
    result.times.append(t)
    result.T_surface.append(T[s])
    result.recession_m.append(recession)
    result.T_bondline.append(T[-1])
    result.ablated_mass_kg_m2.append(ablated_mass)

    return result


# ---------------------------------------------------------------------------
# Analytic semi-infinite slab (verification oracle, no ablation)
# ---------------------------------------------------------------------------

def analytic_semiinfinite_surface_temperature(
    q_W_m2: float,
    t_s: float,
    rho: float,
    cp: float,
    k: float,
) -> float:
    """Analytic surface temperature for constant-flux semi-infinite slab.

    For a semi-infinite solid initially at T=0 subjected to a constant
    surface heat flux q [W/m²] from t=0:

        T_surface(t) = (2·q / k) · sqrt(α·t / π)

    where α = k / (ρ·cp) is the thermal diffusivity.

    Reference: Carslaw & Jaeger, "Conduction of Heat in Solids", 2nd ed.,
    §2.4, Eq. (5).

    Parameters
    ----------
    q_W_m2 : float
        Applied surface heat flux [W/m²].
    t_s : float
        Time [s].
    rho : float
        Density [kg/m³].
    cp : float
        Specific heat [J/(kg·K)].
    k : float
        Thermal conductivity [W/(m·K)].

    Returns
    -------
    float
        Temperature rise at the surface above the initial temperature [K].
    """
    alpha = k / (rho * cp)   # thermal diffusivity [m²/s]
    return (2.0 * q_W_m2 / k) * math.sqrt(alpha * t_s / math.pi)


def analytic_semiinfinite_temperature_profile(
    q_W_m2: float,
    t_s: float,
    x_m: float,
    rho: float,
    cp: float,
    k: float,
) -> float:
    """Analytic temperature at depth x for constant-flux semi-infinite slab.

    T(x, t) = (2·q/k)·sqrt(α·t/π)·exp(−x²/(4·α·t))
              − q·x/k · erfc(x / (2·sqrt(α·t)))

    Parameters
    ----------
    q_W_m2, t_s, rho, cp, k : float
        As in :func:`analytic_semiinfinite_surface_temperature`.
    x_m : float
        Depth below surface [m].

    Returns
    -------
    float
        Temperature rise above initial temperature at (x, t) [K].
    """
    alpha = k / (rho * cp)
    sqrt_at = math.sqrt(alpha * t_s)
    xi = x_m / (2.0 * sqrt_at) if sqrt_at > 0 else 1e30
    exp_term = math.exp(-xi**2)
    erfc_term = math.erfc(xi)
    return (2.0 * q_W_m2 / k) * sqrt_at / math.sqrt(math.pi) * exp_term \
           - (q_W_m2 * x_m / k) * erfc_term
