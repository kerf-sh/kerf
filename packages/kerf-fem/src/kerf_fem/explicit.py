"""
Explicit dynamics / crash seed — central-difference time integration.

Public entry-point
------------------
    solve_explicit(model, duration, kind) -> dict

kind values
-----------
  "spring_mass"  : 1-DOF or N-DOF lumped spring-mass chain.  Elastic or
                   bilinear-plastic material.  Optional Cowper-Symonds
                   strain-rate hardening.  Optional rigid-wall penalty contact.
  "bar_wave"     : 1-D elastic bar with lumped mass; wave-propagation test.
  "frame_crush"  : 2-D lumped frame: bar elements with lumped mass at nodes;
                   crash into rigid wall.

Integration scheme: central-difference explicit (leapfrog).

  Start-up (n=0):
      Compute a[0] from initial x[0], v[0].
      v[1/2]   = v[0]   + a[0] * dt/2        (half-step velocity)

  Each step n = 0, 1, ...:
      x[n+1]   = x[n]   + v[n+1/2] * dt      (position update)
      a[n]     = F(x[n]) / m                  (acceleration at n)
      v[n+3/2] = v[n+1/2] + a[n] * dt        (velocity update)

  KE is computed using the mid-step velocity v[n+1/2] (before position update)
  immediately after position update — it represents KE at step n.

  Internal energy accumulation:
      IE[n+1] = IE[n] + F_int(x[n]) · (x[n+1] - x[n])

  This is the standard Belytschko/Hughes central-difference explicit scheme.

CFL stable time-step: dt = safety * L_min / c, c = sqrt(E/rho).
For spring-mass: dt = safety * 2 / omega_max, omega_max = sqrt(k_eff_max / m_min).

Energy accounting
-----------------
  KE[n]  = 0.5 * sum(m_i * v_i[n+1/2]^2)    — mid-step velocity
  IE[n]  += F_int[n] · dx[n]                  — incremental internal work
  CE[n]  += |F_contact[n] · dx[n]|             — contact dissipation
  For undamped elastic, elastic |ΔE_total / E_ref| < 1%

Never raises; returns {"ok": False, "reason": ...} on error.
Pure-Python — no numpy/scipy.

Model format (dict)
-------------------
  For spring_mass:
    masses   : list of floats [m0, m1, ...]      (N free nodes)
    springs  : list of [i, j, k, [sy0, [H, [C, [p]]]]]
               i, j     : node indices
               k        : spring stiffness [N/m]
               sy0      : optional yield force [N]  (default 1e30 = elastic)
               H        : optional hardening stiffness [N/m]
               C, p     : Cowper-Symonds coefficients
    init_vel : optional list of initial velocities (length = len(masses))
    fixed_dofs : optional list of node indices to pin (zero displacement)
    wall     : optional {"pos": float, "penalty": float}

  For bar_wave:
    E, rho, L, n_elem, area
    fixed_left  : bool (default True)
    fixed_right : bool (default False)
    init_vel_node, init_vel_val  : initial velocity on one node
    impulse_node, impulse_force, impulse_duration : step-force excitation

  For frame_crush:
    nodes       : [[x,y], ...]
    elements    : [[i,j], ...]
    masses      : [m0, m1, ...]  (one per node)
    E, area, rho (rho used for CFL)
    sigma_y0, H  : optional plastic material
    fixed_dofs   : list of DOF indices (2*node for x, 2*node+1 for y)
    init_vel_dofs: [[dof, vel], ...]
    wall         : {"pos": float, "penalty": float, "axis": 0|1}

safety_factor : float — CFL safety factor (default 0.9)

Returns
-------
  {
    "ok"          : bool,
    "t"           : [float, ...],
    "x"           : [[float,...], ...],   # displacement at each time step
    "v"           : [[float,...], ...],   # mid-step velocity
    "KE"          : [float, ...],         # kinetic energy (mid-step)
    "IE"          : [float, ...],         # cumulative internal energy
    "CE"          : [float, ...],         # cumulative contact energy (penalty)
    "dt"          : float,
    "n_steps"     : int,
    "energy_error": float,
    "warnings"    : [str, ...],
    "reason"      : str   (only when ok=False)
  }
"""

from __future__ import annotations

import math
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_fem._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


# ===========================================================================
# Scalar helpers
# ===========================================================================

def _sign(x: float) -> float:
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return 0.0


# ===========================================================================
# CFL time-step formula
# ===========================================================================

def _cfl_dt(L_min: float, E: float, rho: float,
            safety: float = 0.9) -> float:
    """
    CFL critical time step for a bar element:
        dt = safety * L_min / c,  c = sqrt(E / rho)
    """
    c = math.sqrt(E / rho)
    return safety * L_min / c


# ===========================================================================
# 1-D uniaxial spring element (elastic + bilinear-plastic + Cowper-Symonds)
# ===========================================================================

class _Spring1D:
    """
    Uniaxial spring connecting nodes i and j in a 1-D spring-mass system.

    Spring force = k * (elastic_elongation),  capped by yield surface.
    eps_p accumulates plastic elongation.
    Cowper-Symonds: effective yield = sy0 * (1 + (strain_rate/C)^(1/p))
    """

    __slots__ = ("ki", "kj", "k", "sy0", "H", "C", "p", "eps_p")

    def __init__(self, ki: int, kj: int, k: float,
                 sy0: float = 1e30, H: float = 0.0,
                 C: float = 0.0, p: float = 1.0):
        self.ki = ki
        self.kj = kj
        self.k = k
        self.sy0 = sy0
        self.H = H
        self.C = C
        self.p = p
        self.eps_p = 0.0   # accumulated plastic elongation

    def force(self, x: list[float], v_half: list[float],
              dt: float) -> float:
        """
        Return axial force on node kj (positive = tension pulling kj in + direction).
        Updates plastic state in place.
        """
        delta_u = x[self.kj] - x[self.ki]          # total elongation
        delta_u_dot = v_half[self.kj] - v_half[self.ki]  # elongation rate

        # Elastic trial force
        f_trial = self.k * (delta_u - self.eps_p)

        # Yield force (with optional C-S strain-rate hardening)
        fy = self.sy0 + self.H * abs(self.eps_p)
        if self.C > 0.0 and dt > 0.0:
            eps_dot = abs(delta_u_dot)  # elongation rate (relative velocity)
            fy = fy * (1.0 + (eps_dot / self.C) ** (1.0 / self.p))

        # 1-D return mapping
        if abs(f_trial) <= fy:
            return f_trial
        else:
            sign_f = _sign(f_trial)
            delta_lambda = (abs(f_trial) - fy) / (self.k + self.H)
            self.eps_p += delta_lambda * sign_f
            return sign_f * fy


# ===========================================================================
# Solver: spring_mass (1-D, N nodes)
# ===========================================================================

def _solve_spring_mass(
    model: dict,
    duration: float,
    safety: float,
) -> dict[str, Any]:
    """
    Central-difference explicit integration for N-DOF spring-mass system.

    Nodes 0..N-1 each have one DOF (x-displacement).
    fixed_dofs entries are kept at zero displacement and zero velocity.
    """
    masses_raw = model.get("masses", [])
    springs_raw = model.get("springs", [])
    init_vel_raw = model.get("init_vel", [])
    wall_cfg = model.get("wall")
    fixed_nodes = set(int(d) for d in model.get("fixed_dofs", []))

    if not masses_raw:
        return {"ok": False, "reason": "spring_mass: masses list is empty"}

    N = len(masses_raw)
    masses = [float(m) for m in masses_raw]

    # Free DOF set
    free = [i for i in range(N) if i not in fixed_nodes]
    if not free:
        return {"ok": False, "reason": "spring_mass: all nodes are fixed"}

    # Build springs
    springs: list[_Spring1D] = []
    for s in springs_raw:
        ki, kj = int(s[0]), int(s[1])
        k = float(s[2])
        sy0 = float(s[3]) if len(s) > 3 else 1e30
        H = float(s[4]) if len(s) > 4 else 0.0
        C = float(s[5]) if len(s) > 5 else 0.0
        p_cs = float(s[6]) if len(s) > 6 else 1.0
        springs.append(_Spring1D(ki, kj, k, sy0, H, C, p_cs))

    # CFL time step: omega_max = sqrt(k_eff / m) for connected nodes
    # k_eff at node i = sum of springs attached to i
    k_eff = [0.0] * N
    for sp in springs:
        k_eff[sp.ki] += sp.k
        k_eff[sp.kj] += sp.k

    dt = float("inf")
    for i in free:
        if k_eff[i] > 0.0 and masses[i] > 0.0:
            omega_sq = k_eff[i] / masses[i]
            dt_i = safety * 2.0 / math.sqrt(omega_sq)
            if dt_i < dt:
                dt = dt_i

    if not math.isfinite(dt) or dt <= 0.0:
        # No springs connected to free nodes — free particles, no stability limit
        dt = duration / 100.0

    n_steps = max(1, int(math.ceil(duration / dt)))
    dt = duration / n_steps

    # Initial conditions
    x = [0.0] * N
    v = [0.0] * N   # current full-step velocity (used for startup half-step)
    if init_vel_raw:
        for i, vi in enumerate(init_vel_raw):
            if i < N:
                v[i] = float(vi)
    # Zero out fixed nodes
    for d in fixed_nodes:
        if d < N:
            v[d] = 0.0

    # Wall config
    wall_pos = None
    wall_penalty = 1e10
    if wall_cfg:
        wall_pos = float(wall_cfg.get("pos", 1e30))
        wall_penalty = float(wall_cfg.get("penalty", 1e10))

    def _spring_forces(x_cur: list[float],
                       v_cur: list[float]) -> list[float]:
        """
        Compute nodal spring forces without advancing plastic state.
        Returns list of length N.
        """
        f = [0.0] * N
        for sp in springs:
            # Temporarily compute force without advancing state
            delta_u = x_cur[sp.kj] - x_cur[sp.ki]
            delta_u_dot = v_cur[sp.kj] - v_cur[sp.ki]
            f_trial = sp.k * (delta_u - sp.eps_p)
            fy = sp.sy0 + sp.H * abs(sp.eps_p)
            if sp.C > 0.0:
                fy = fy * (1.0 + (abs(delta_u_dot) / sp.C) ** (1.0 / sp.p))
            f_sp = f_trial if abs(f_trial) <= fy else _sign(f_trial) * fy
            # Spring tension (f_sp > 0) pulls ki toward kj and kj toward ki
            f[sp.ki] += f_sp
            f[sp.kj] -= f_sp
        if wall_pos is not None:
            for i in free:
                gap = x_cur[i] - wall_pos
                if gap > 0.0:
                    f[i] += -wall_penalty * gap
        return f

    def _advance_springs(x_cur: list[float],
                         v_cur: list[float]) -> list[float]:
        """
        Compute nodal spring forces AND advance plastic state.
        Returns list of length N (internal forces only, no wall).
        """
        f = [0.0] * N
        for sp in springs:
            f_sp = sp.force(x_cur, v_cur, dt)
            # Spring tension (f_sp > 0) pulls ki toward kj and kj toward ki
            f[sp.ki] += f_sp
            f[sp.kj] -= f_sp
        return f

    # -----------------------------------------------------------------------
    # Start-up half-step: v[1/2] = v[0] + a[0] * dt/2
    # -----------------------------------------------------------------------
    f0 = _spring_forces(x, v)
    a0 = [0.0] * N
    for i in free:
        a0[i] = f0[i] / masses[i]

    # v_half = v[0] + a[0]*dt/2
    v_half = [v[i] + a0[i] * dt * 0.5 for i in range(N)]
    for d in fixed_nodes:
        if d < N:
            v_half[d] = 0.0

    # -----------------------------------------------------------------------
    # Energy at step 0
    # KE uses v_half = v[1/2]
    # IE = 0 at t=0
    # -----------------------------------------------------------------------
    KE0 = sum(0.5 * masses[i] * v_half[i] ** 2 for i in free)

    t_hist = [0.0]
    x_hist = [x[:]]
    v_hist = [v_half[:]]
    KE_hist = [KE0]
    IE_hist = [0.0]
    CE_hist = [0.0]

    IE = 0.0
    CE = 0.0
    t = 0.0

    # -----------------------------------------------------------------------
    # Time-stepping loop
    # -----------------------------------------------------------------------
    for _step in range(n_steps):
        # Internal forces at x[n] (advance plastic state)
        f_int = _advance_springs(x, v_half)

        # Contact forces at x[n]
        f_con = [0.0] * N
        if wall_pos is not None:
            for i in free:
                gap = x[i] - wall_pos
                if gap > 0.0:
                    f_con[i] = -wall_penalty * gap

        # Total force
        f_tot = [f_int[i] + f_con[i] for i in range(N)]

        # Acceleration a[n] = f[n] / m
        a = [0.0] * N
        for i in free:
            a[i] = f_tot[i] / masses[i]

        # Position update: x[n+1] = x[n] + v[n+1/2] * dt
        x_new = [x[i] + v_half[i] * dt for i in range(N)]
        for d in fixed_nodes:
            if d < N:
                x_new[d] = 0.0

        # --- Energy accounting ---
        # dIE = F_int[n] · (x[n+1] - x[n])
        # Sign convention: F_int here is the resisting force vector on each node
        # Work done by spring forces on the system (going into stored energy)
        dx = [x_new[i] - x[i] for i in range(N)]
        dIE = -sum(f_int[i] * dx[i] for i in range(N))
        IE += dIE

        # Contact energy: work done against the penalty spring
        # penalty force is restorative (-penalty*gap), so work into contact = -F_con·dx
        dCE = -sum(f_con[i] * dx[i] for i in range(N))
        CE += dCE

        # Velocity update: v[n+3/2] = v[n+1/2] + a[n] * dt
        v_half_new = [v_half[i] + a[i] * dt for i in range(N)]
        for d in fixed_nodes:
            if d < N:
                v_half_new[d] = 0.0

        x = x_new
        v_half = v_half_new
        t += dt

        # KE at v[n+3/2]
        KE = sum(0.5 * masses[i] * v_half[i] ** 2 for i in free)

        t_hist.append(t)
        x_hist.append(x[:])
        v_hist.append(v_half[:])
        KE_hist.append(KE)
        IE_hist.append(IE)
        CE_hist.append(CE)

    # Energy conservation error
    E_initial = KE_hist[0] + IE_hist[0]
    E_final = KE_hist[-1] + IE_hist[-1]
    E_scale = max(abs(E_initial), abs(E_final), 1e-30)
    energy_error = abs(E_final - E_initial) / E_scale

    return {
        "ok": True,
        "t": t_hist,
        "x": x_hist,
        "v": v_hist,
        "KE": KE_hist,
        "IE": IE_hist,
        "CE": CE_hist,
        "dt": dt,
        "n_steps": n_steps,
        "energy_error": energy_error,
        "warnings": [],
    }


# ===========================================================================
# Solver: bar_wave (1-D elastic bar, wave propagation)
# ===========================================================================

def _solve_bar_wave(
    model: dict,
    duration: float,
    safety: float,
) -> dict[str, Any]:
    """
    1-D elastic bar: lumped mass, central-difference explicit.
    n_elem bar elements, n_elem+1 nodes.
    DOF: scalar axial displacement u_i.
    """
    E = float(model.get("E", 2e11))
    rho = float(model.get("rho", 7800.0))
    L = float(model.get("L", 1.0))
    n_elem = int(model.get("n_elem", 10))
    A = float(model.get("area", 1e-4))
    fixed_left = bool(model.get("fixed_left", True))
    fixed_right = bool(model.get("fixed_right", False))
    impulse_node_raw = model.get("impulse_node")
    impulse_force = float(model.get("impulse_force", 0.0))
    impulse_duration = float(model.get("impulse_duration", 0.0))
    init_vel_node_raw = model.get("init_vel_node")
    init_vel_val = float(model.get("init_vel_val", 0.0))

    if n_elem < 1:
        return {"ok": False, "reason": "bar_wave: n_elem must be >= 1"}
    if L <= 0.0:
        return {"ok": False, "reason": "bar_wave: L must be positive"}
    if E <= 0.0 or rho <= 0.0:
        return {"ok": False, "reason": "bar_wave: E and rho must be positive"}

    n_nodes = n_elem + 1
    Le = L / n_elem

    # CFL
    dt = _cfl_dt(Le, E, rho, safety)
    n_steps = max(1, int(math.ceil(duration / dt)))
    dt = duration / n_steps

    # Lumped mass (consistent with Hinton/Rock/Zienkiewicz lumping)
    # Interior: rho*A*Le; Boundary: rho*A*Le/2
    masses = [rho * A * Le] * n_nodes
    masses[0] = rho * A * Le * 0.5
    masses[n_nodes - 1] = rho * A * Le * 0.5

    fixed_dofs: set[int] = set()
    if fixed_left:
        fixed_dofs.add(0)
    if fixed_right:
        fixed_dofs.add(n_nodes - 1)

    free = [i for i in range(n_nodes) if i not in fixed_dofs]

    # Bar element stiffness
    bar_k = E * A / Le  # k_e = EA/L

    def _bar_internal_forces(x_cur: list[float]) -> list[float]:
        """
        Nodal forces from bar elements (elastic).
        Tension (N_bar > 0) pulls ni toward nj (+) and nj toward ni (−).
        """
        f = [0.0] * n_nodes
        for e in range(n_elem):
            ni, nj = e, e + 1
            du = x_cur[nj] - x_cur[ni]
            N_bar = bar_k * du  # positive = tension
            f[ni] += N_bar   # pulled toward nj
            f[nj] -= N_bar   # pulled toward ni
        return f

    # Initial conditions
    x = [0.0] * n_nodes
    v = [0.0] * n_nodes
    if init_vel_node_raw is not None:
        inode = int(init_vel_node_raw)
        if 0 <= inode < n_nodes and inode not in fixed_dofs:
            v[inode] = init_vel_val

    # External force function
    def _ext_force(t_cur: float) -> list[float]:
        f = [0.0] * n_nodes
        if (impulse_node_raw is not None and impulse_force != 0.0
                and t_cur < impulse_duration):
            inode = int(impulse_node_raw)
            if 0 <= inode < n_nodes and inode not in fixed_dofs:
                f[inode] += impulse_force
        return f

    # Start-up: a[0] from f_int[x=0] + f_ext[t=0]
    f_int0 = _bar_internal_forces(x)
    f_ext0 = _ext_force(0.0)
    a0 = [0.0] * n_nodes
    for i in free:
        a0[i] = (f_int0[i] + f_ext0[i]) / masses[i]

    v_half = [v[i] + a0[i] * dt * 0.5 for i in range(n_nodes)]
    for d in fixed_dofs:
        v_half[d] = 0.0

    KE0 = sum(0.5 * masses[i] * v_half[i] ** 2 for i in free)

    t_hist = [0.0]
    x_hist = [x[:]]
    v_hist = [v_half[:]]
    KE_hist = [KE0]
    IE_hist = [0.0]
    CE_hist = [0.0]

    IE = 0.0
    t = 0.0
    warnings_list: list[str] = []

    for _step in range(n_steps):
        f_int = _bar_internal_forces(x)
        f_ext = _ext_force(t)

        f_tot = [f_int[i] + f_ext[i] for i in range(n_nodes)]

        a = [0.0] * n_nodes
        for i in free:
            a[i] = f_tot[i] / masses[i]

        # Position update
        x_prev = x[:]
        x_new = [x[i] + v_half[i] * dt for i in range(n_nodes)]
        for d in fixed_dofs:
            x_new[d] = 0.0

        # Internal energy: work done against internal forces
        dx = [x_new[i] - x_prev[i] for i in range(n_nodes)]
        dIE = -sum(f_int[i] * dx[i] for i in range(n_nodes))
        IE += dIE

        # Velocity update
        v_half_new = [v_half[i] + a[i] * dt for i in range(n_nodes)]
        for d in fixed_dofs:
            v_half_new[d] = 0.0

        x = x_new
        v_half = v_half_new
        t += dt

        KE = sum(0.5 * masses[i] * v_half[i] ** 2 for i in free)

        t_hist.append(t)
        x_hist.append(x[:])
        v_hist.append(v_half[:])
        KE_hist.append(KE)
        IE_hist.append(IE)
        CE_hist.append(0.0)

    E_initial = KE_hist[0] + IE_hist[0]
    E_final = KE_hist[-1] + IE_hist[-1]
    E_scale = max(abs(E_initial), abs(E_final), 1e-30)
    energy_error = abs(E_final - E_initial) / E_scale

    return {
        "ok": True,
        "t": t_hist,
        "x": x_hist,
        "v": v_hist,
        "KE": KE_hist,
        "IE": IE_hist,
        "CE": CE_hist,
        "dt": dt,
        "n_steps": n_steps,
        "energy_error": energy_error,
        "warnings": warnings_list,
    }


# ===========================================================================
# 2-D bar element (for frame_crush)
# ===========================================================================

class _Bar2D:
    """
    2-node axial bar element in 2-D space with optional bilinear plasticity.
    DOFs: [u_i, v_i, u_j, v_j] (flat displacement array indexing).
    """

    __slots__ = ("ni", "nj", "E", "A", "L0", "sy0", "H", "eps_p")

    def __init__(self, ni: int, nj: int, E: float, A: float, L0: float,
                 sy0: float = 1e30, H: float = 0.0):
        self.ni = ni
        self.nj = nj
        self.E = E
        self.A = A
        self.L0 = L0
        self.sy0 = sy0
        self.H = H
        self.eps_p = 0.0

    def forces_2d(self, x: list[float]) -> tuple[float, float, float, float]:
        """
        Compute nodal forces. x is the flat displacement array.
        Returns (fi_x, fi_y, fj_x, fj_y).
        Advances plastic state.
        """
        ni, nj = self.ni, self.nj
        # Deformed tip positions
        xi = x[2 * ni];     yi = x[2 * ni + 1]
        xj = x[2 * nj];     yj = x[2 * nj + 1]
        dxd = xj - xi
        dyd = yj - yi
        Ld = math.sqrt(dxd * dxd + dyd * dyd)
        if Ld < 1e-14:
            return 0.0, 0.0, 0.0, 0.0

        cd, sd = dxd / Ld, dyd / Ld

        # Small-strain axial strain
        eps_total = (Ld - self.L0) / self.L0
        eps_e = eps_total - self.eps_p

        sigma_trial = self.E * eps_e
        fy = self.sy0 + self.H * abs(self.eps_p)

        if abs(sigma_trial) <= fy:
            sigma = sigma_trial
        else:
            sign_s = _sign(sigma_trial)
            dl = (abs(sigma_trial) - fy) / (self.E + self.H)
            self.eps_p += dl * sign_s
            sigma = sign_s * fy

        N = sigma * self.A   # axial force resultant

        # Tension (N > 0) pulls ni toward nj and nj toward ni
        return (N * cd, N * sd, -N * cd, -N * sd)


# ===========================================================================
# Solver: frame_crush (2-D lumped frame)
# ===========================================================================

def _solve_frame_crush(
    model: dict,
    duration: float,
    safety: float,
) -> dict[str, Any]:
    """
    2-D lumped frame crash analysis.
    Each node has 2 DOFs (x, y).
    Bar elements carry axial force only (truss approximation).
    """
    nodes_raw = model.get("nodes", [])
    elements_raw = model.get("elements", [])
    masses_raw = model.get("masses", [])
    E = float(model.get("E", 2e11))
    A = float(model.get("area", 1e-4))
    rho = float(model.get("rho", 7800.0))
    sy0 = float(model.get("sigma_y0", 1e30))
    H_mod = float(model.get("H", 0.0))
    fixed_dofs_raw = list(model.get("fixed_dofs", []))
    init_vel_dofs = list(model.get("init_vel_dofs", []))
    wall_cfg = model.get("wall")

    n_nodes = len(nodes_raw)
    n_dofs = 2 * n_nodes

    if n_nodes == 0:
        return {"ok": False, "reason": "frame_crush: no nodes provided"}
    if not elements_raw:
        return {"ok": False, "reason": "frame_crush: no elements provided"}

    # Reference node coordinates
    node_X = [float(nodes_raw[i][0]) for i in range(n_nodes)]
    node_Y = [float(nodes_raw[i][1]) for i in range(n_nodes)]

    # Build bar elements; find minimum length for CFL
    bars: list[_Bar2D] = []
    L_min = float("inf")
    for e_raw in elements_raw:
        ni, nj = int(e_raw[0]), int(e_raw[1])
        dx = node_X[nj] - node_X[ni]
        dy = node_Y[nj] - node_Y[ni]
        Le = math.sqrt(dx * dx + dy * dy)
        if Le < 1e-14:
            return {"ok": False, "reason": "frame_crush: degenerate element (zero length)"}
        if Le < L_min:
            L_min = Le
        bars.append(_Bar2D(ni, nj, E, A, Le, sy0, H_mod))

    # Nodal masses
    if masses_raw and len(masses_raw) == n_nodes:
        node_masses = [float(m) for m in masses_raw]
    else:
        # Distribute bar mass to nodes
        node_masses = [0.0] * n_nodes
        for bar in bars:
            m_elem = rho * A * bar.L0
            node_masses[bar.ni] += m_elem * 0.5
            node_masses[bar.nj] += m_elem * 0.5

    # CFL
    dt = _cfl_dt(L_min, E, rho, safety)
    n_steps = max(1, int(math.ceil(duration / dt)))
    dt = duration / n_steps

    # DOF masses (two per node)
    dof_masses = []
    for m in node_masses:
        dof_masses.append(m)
        dof_masses.append(m)

    fixed_dofs: set[int] = set(int(d) for d in fixed_dofs_raw)
    free_dofs = [i for i in range(n_dofs) if i not in fixed_dofs]

    # Displacements (flat [u0, v0, u1, v1, ...])
    x = [0.0] * n_dofs
    v = [0.0] * n_dofs
    for entry in init_vel_dofs:
        dof_idx = int(entry[0])
        vel_val = float(entry[1])
        if 0 <= dof_idx < n_dofs and dof_idx not in fixed_dofs:
            v[dof_idx] = vel_val

    # Wall
    wall_pos = None
    wall_penalty = 1e10
    wall_axis = 0  # 0 = x-direction, 1 = y-direction
    if wall_cfg:
        wall_pos = float(wall_cfg.get("pos", 1e30))
        wall_penalty = float(wall_cfg.get("penalty", 1e10))
        wall_axis = int(wall_cfg.get("axis", 0))

    def _frame_int_forces(x_cur: list[float]) -> list[float]:
        f = [0.0] * n_dofs
        for bar in bars:
            fi_x, fi_y, fj_x, fj_y = bar.forces_2d(x_cur)
            f[2 * bar.ni]     += fi_x
            f[2 * bar.ni + 1] += fi_y
            f[2 * bar.nj]     += fj_x
            f[2 * bar.nj + 1] += fj_y
        return f

    def _wall_forces(x_cur: list[float]) -> list[float]:
        f = [0.0] * n_dofs
        if wall_pos is None:
            return f
        for node_i in range(n_nodes):
            axis_dof = 2 * node_i + wall_axis
            if axis_dof in fixed_dofs:
                continue
            # Current coordinate along wall normal axis
            if wall_axis == 0:
                coord = node_X[node_i] + x_cur[2 * node_i]
            else:
                coord = node_Y[node_i] + x_cur[2 * node_i + 1]
            gap = coord - wall_pos
            if gap > 0.0:
                f[axis_dof] += -wall_penalty * gap
        return f

    # Start-up
    f_int0 = _frame_int_forces(x)
    f_wal0 = _wall_forces(x)
    a0 = [0.0] * n_dofs
    for i in free_dofs:
        if dof_masses[i] > 0.0:
            a0[i] = (f_int0[i] + f_wal0[i]) / dof_masses[i]

    v_half = [v[i] + a0[i] * dt * 0.5 for i in range(n_dofs)]
    for d in fixed_dofs:
        if d < n_dofs:
            v_half[d] = 0.0

    KE0 = sum(0.5 * dof_masses[i] * v_half[i] ** 2
              for i in free_dofs if dof_masses[i] > 0.0)

    t_hist = [0.0]
    x_hist = [x[:]]
    v_hist = [v_half[:]]
    KE_hist = [KE0]
    IE_hist = [0.0]
    CE_hist = [0.0]

    IE = 0.0
    CE = 0.0
    t = 0.0

    for _step in range(n_steps):
        f_int = _frame_int_forces(x)
        f_wal = _wall_forces(x)

        f_tot = [f_int[i] + f_wal[i] for i in range(n_dofs)]

        a = [0.0] * n_dofs
        for i in free_dofs:
            if dof_masses[i] > 0.0:
                a[i] = f_tot[i] / dof_masses[i]

        x_prev = x[:]
        x_new = [x[i] + v_half[i] * dt for i in range(n_dofs)]
        for d in fixed_dofs:
            if d < n_dofs:
                x_new[d] = 0.0

        dx = [x_new[i] - x_prev[i] for i in range(n_dofs)]
        dIE = -sum(f_int[i] * dx[i] for i in range(n_dofs))
        IE += dIE
        dCE = -sum(f_wal[i] * dx[i] for i in range(n_dofs))
        CE += dCE

        v_half_new = [v_half[i] + a[i] * dt for i in range(n_dofs)]
        for d in fixed_dofs:
            if d < n_dofs:
                v_half_new[d] = 0.0

        x = x_new
        v_half = v_half_new
        t += dt

        KE = sum(0.5 * dof_masses[i] * v_half[i] ** 2
                 for i in free_dofs if dof_masses[i] > 0.0)

        t_hist.append(t)
        x_hist.append(x[:])
        v_hist.append(v_half[:])
        KE_hist.append(KE)
        IE_hist.append(IE)
        CE_hist.append(CE)

    E_initial = KE_hist[0] + IE_hist[0]
    E_final = KE_hist[-1] + IE_hist[-1]
    E_scale = max(abs(E_initial), abs(E_final), 1e-30)
    energy_error = abs(E_final - E_initial) / E_scale

    return {
        "ok": True,
        "t": t_hist,
        "x": x_hist,
        "v": v_hist,
        "KE": KE_hist,
        "IE": IE_hist,
        "CE": CE_hist,
        "dt": dt,
        "n_steps": n_steps,
        "energy_error": energy_error,
        "warnings": [],
    }


# ===========================================================================
# Public API
# ===========================================================================

def solve_explicit(
    model: dict,
    duration: float,
    kind: str,
    *,
    safety_factor: float = 0.9,
) -> dict[str, Any]:
    """
    Explicit dynamics / crash analysis via central-difference time integration.

    Parameters
    ----------
    model       : problem-specific model dict (see module docstring)
    duration    : simulation end time [s]
    kind        : "spring_mass" | "bar_wave" | "frame_crush"
    safety_factor : CFL safety factor (default 0.9)

    Returns
    -------
    See module docstring for full output schema.
    """
    try:
        return _solve_explicit_inner(model, duration, kind, safety_factor)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"unexpected error: {exc}",
            "t": [], "x": [], "v": [], "KE": [], "IE": [], "CE": [],
            "dt": 0.0, "n_steps": 0, "energy_error": 0.0, "warnings": [],
        }


def _solve_explicit_inner(
    model: dict,
    duration: float,
    kind: str,
    safety: float,
) -> dict[str, Any]:
    if not isinstance(model, dict):
        return {"ok": False, "reason": "model must be a dict",
                "t": [], "x": [], "v": [], "KE": [], "IE": [], "CE": [],
                "dt": 0.0, "n_steps": 0, "energy_error": 0.0, "warnings": []}
    if duration <= 0.0:
        return {"ok": False, "reason": "duration must be positive",
                "t": [], "x": [], "v": [], "KE": [], "IE": [], "CE": [],
                "dt": 0.0, "n_steps": 0, "energy_error": 0.0, "warnings": []}
    if kind not in ("spring_mass", "bar_wave", "frame_crush"):
        return {
            "ok": False,
            "reason": f"kind must be spring_mass/bar_wave/frame_crush, got {kind!r}",
            "t": [], "x": [], "v": [], "KE": [], "IE": [], "CE": [],
            "dt": 0.0, "n_steps": 0, "energy_error": 0.0, "warnings": [],
        }

    if kind == "spring_mass":
        return _solve_spring_mass(model, duration, safety)
    elif kind == "bar_wave":
        return _solve_bar_wave(model, duration, safety)
    else:
        return _solve_frame_crush(model, duration, safety)


# ===========================================================================
# LLM tool registration
# ===========================================================================

_fem_explicit_spec = ToolSpec(
    name="fem_explicit",
    description=(
        "Run an explicit dynamics / crash simulation using central-difference "
        "time integration. Supports spring-mass systems (1-DOF and N-DOF), "
        "1-D elastic bar wave propagation, and 2-D lumped frame crush against "
        "a rigid wall. Elastic and bilinear-plastic material models; optional "
        "Cowper-Symonds strain-rate hardening; rigid-wall penalty contact. "
        "Returns time history of displacements, velocities, kinetic energy, "
        "internal energy, and contact energy."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "model": {
                "type": "object",
                "description": (
                    "Problem-specific model dict. "
                    "spring_mass: masses (list), springs (list of [i,j,k,...]), "
                    "  init_vel (list, opt), fixed_dofs (list, opt), wall (dict, opt). "
                    "bar_wave: E, rho, L, n_elem, area, fixed_left, fixed_right, "
                    "  impulse_node, impulse_force, impulse_duration (all opt). "
                    "frame_crush: nodes ([[x,y],...]), elements ([[i,j],...]), "
                    "  masses (list), E, area, rho, sigma_y0 (opt), H (opt), "
                    "  fixed_dofs (list), init_vel_dofs ([[dof,vel],...], opt), "
                    "  wall (dict, opt)."
                ),
            },
            "duration": {
                "type": "number",
                "description": "Simulation end time [s].",
            },
            "kind": {
                "type": "string",
                "enum": ["spring_mass", "bar_wave", "frame_crush"],
                "description": "Type of explicit dynamics problem.",
            },
            "safety_factor": {
                "type": "number",
                "description": "CFL safety factor (default 0.9).",
                "default": 0.9,
            },
        },
        "required": ["model", "duration", "kind"],
    },
)


@register(_fem_explicit_spec)
async def run_fem_explicit(ctx: ProjectCtx, args: bytes) -> str:
    import json
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    model = a.get("model")
    duration = a.get("duration")
    kind = a.get("kind")

    if model is None:
        return err_payload("model is required", "BAD_ARGS")
    if duration is None:
        return err_payload("duration is required", "BAD_ARGS")
    if not kind:
        return err_payload("kind is required", "BAD_ARGS")

    result = solve_explicit(
        model=model,
        duration=float(duration),
        kind=kind,
        safety_factor=float(a.get("safety_factor", 0.9)),
    )
    return json.dumps(result)
