"""
kerf_cad_core.sysml1d.network — acausal 1D lumped-parameter system simulation.

Domains supported via the effort/flow analogy
----------------------------------------------
  Domain       effort (e)   flow (f)      R           C           L
  electrical   voltage (V)  current (A)   resistance  capacitance inductance
  thermal      temp (K)     heat-flow (W) R_th        C_th        —
  hydraulic    pressure (Pa) flow (m³/s)  R_hyd       C_hyd(acc)  L_hyd(inertance)
  mechanical   force (N)    velocity(m/s) damper       mass        spring^-1

Element catalogue
-----------------
  R, L, C            — resistor/inductance/capacitance (all domains)
  VSource, ISource   — ideal effort/flow source
  Diode              — nonlinear: i = Is*(exp(v/Vt)-1)

Assembly
--------
  Generalised modified-nodal analysis (MNA).  One extra unknown (branch
  current) is added for every voltage source and inductor.  The DAE is
  index-1.

Integration
-----------
  Implicit trapezoidal (Crank–Nicolson) companion models:

    Capacitor companion  (trapezoidal, per Pillage & Rohrer 1990):
        At step n+1, with h = dt:
            i_{n+1} = (2C/h)*(v_{n+1} - v_n) - i_n
        Stamp as: Geq = 2C/h in G,  Ieq = (2C/h)*v_n + i_n  as a current src.

    Inductor companion (trapezoidal):
        At step n+1:
            v_{n+1} = (2L/h)*(i_{n+1} - i_n) - v_n
        → Req = 2L/h in series, Veq = (2L/h)*i_n + v_n as voltage src term.
        In MNA the inductor already contributes a branch-current unknown j_L:
            stamp as: R_eq in the (j_L, j_L) position + Veq in the RHS.

Newton–Raphson for nonlinear elements (Diode):
  Linearise each nonlinear element around current operating point, add
  companion conductance+current to G_dyn, iterate to convergence.

Steady-state
------------
  Set h → ∞: capacitors open-circuit (Geq = 0), inductors short-circuit
  (Req = 0, i.e. treat as wire).  Solved by direct LU.

References
----------
  Pillage, L.T., Rohrer, R.A., Visweswariah, C. — "Electronic Circuit and
      System Simulation Methods", McGraw-Hill 1995.
  Ho, C.W., Ruehli, A.E., Brennan, P.A. — "The modified nodal approach to
      network analysis", IEEE TCAS 1975.

Author: imranparuk
"""

from __future__ import annotations

import json
import math
from typing import Any

# ---------------------------------------------------------------------------
# Tiny dense-matrix linear algebra (no numpy)
# ---------------------------------------------------------------------------

def _zeros(n: int) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _vecz(n: int) -> list[float]:
    return [0.0] * n


def _mat_copy(A: list[list[float]]) -> list[list[float]]:
    return [row[:] for row in A]


def _vec_copy(v: list[float]) -> list[float]:
    return v[:]


def _lu_solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Solve Ax = b via partial-pivoting Gaussian elimination in-place copy."""
    n = len(b)
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Partial pivot
        max_row = col
        max_val = abs(M[col][col])
        for row in range(col + 1, n):
            if abs(M[row][col]) > max_val:
                max_val = abs(M[row][col])
                max_row = row
        M[col], M[max_row] = M[max_row], M[col]

        pivot = M[col][col]
        if abs(pivot) < 1e-300:
            raise ValueError("Singular matrix during LU solve")

        for row in range(col + 1, n):
            factor = M[row][col] / pivot
            for k in range(col, n + 1):
                M[row][k] -= factor * M[col][k]

    # Back-substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]

    return x


def _norm_inf(v: list[float]) -> float:
    return max(abs(x) for x in v) if v else 0.0


# ---------------------------------------------------------------------------
# Element definitions
# ---------------------------------------------------------------------------

class Element:
    """Base class for all network elements."""

    def __init__(self, name: str, n_plus: str, n_minus: str):
        self.name = name
        self.n_plus = n_plus
        self.n_minus = n_minus

    # Subclasses override the stamp methods below.

    def stamp_dc(
        self,
        G: list[list[float]],
        b: list[float],
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
    ) -> None:
        """Stamp the DC (steady-state) MNA contribution."""

    def stamp_transient(
        self,
        G: list[list[float]],
        b: list[float],
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        h: float,
        state: dict[str, float],
    ) -> None:
        """Stamp the transient companion model; default = same as DC."""
        self.stamp_dc(G, b, node_idx, branch_idx)

    def stamp_nl(
        self,
        G: list[list[float]],
        b: list[float],
        node_idx: dict[str, int],
        x: list[float],
    ) -> None:
        """Stamp nonlinear contribution (Newton iteration). Default: no-op."""


# ---- Resistor ---------------------------------------------------------------

class R(Element):
    """Resistor / thermal-R / hydraulic-R / mechanical damper.

    All described by  e_+ − e_- = R * f,  i.e.  conductance G = 1/R.
    """

    def __init__(self, name: str, n_plus: str, n_minus: str, resistance: float):
        super().__init__(name, n_plus, n_minus)
        if resistance <= 0:
            raise ValueError(f"Resistance must be > 0 (got {resistance!r})")
        self.resistance = float(resistance)

    def _stamp(
        self,
        G: list[list[float]],
        node_idx: dict[str, int],
        conductance: float,
    ) -> None:
        g = conductance
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        if p >= 0:
            G[p][p] += g
        if m >= 0:
            G[m][m] += g
        if p >= 0 and m >= 0:
            G[p][m] -= g
            G[m][p] -= g

    def stamp_dc(self, G, b, node_idx, branch_idx):
        self._stamp(G, node_idx, 1.0 / self.resistance)

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        self._stamp(G, node_idx, 1.0 / self.resistance)


# ---- Capacitor --------------------------------------------------------------

class C(Element):
    """Capacitor / thermal capacitance / hydraulic accumulator / mass.

    Trapezoidal companion (Pillage 1995, §4.3):
        i_{n+1} = Geq * (v_{n+1}) - Ieq
        where  Geq = 2C/h,
               Ieq = 2C/h * v_n + i_n   (= Geq*v_n + i_n)

    State keys:
        <name>_v   — voltage across capacitor at previous step
        <name>_i   — current through capacitor at previous step
    """

    def __init__(self, name: str, n_plus: str, n_minus: str, capacitance: float):
        super().__init__(name, n_plus, n_minus)
        if capacitance <= 0:
            raise ValueError(f"Capacitance must be > 0 (got {capacitance!r})")
        self.capacitance = float(capacitance)

    def stamp_dc(self, G, b, node_idx, branch_idx):
        # DC steady state: capacitor = open circuit → no stamp
        pass

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        C_val = self.capacitance
        Geq = 2.0 * C_val / h

        v_prev = state.get(f"{self.name}_v", 0.0)
        i_prev = state.get(f"{self.name}_i", 0.0)

        # Ieq is the equivalent current source value pointing into n_plus
        Ieq = Geq * v_prev + i_prev

        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)

        if p >= 0:
            G[p][p] += Geq
        if m >= 0:
            G[m][m] += Geq
        if p >= 0 and m >= 0:
            G[p][m] -= Geq
            G[m][p] -= Geq

        # Current source Ieq flowing from n_minus into n_plus
        if p >= 0:
            b[p] += Ieq
        if m >= 0:
            b[m] -= Ieq

    def update_state(
        self,
        state: dict[str, float],
        x: list[float],
        node_idx: dict[str, int],
        h: float,
    ) -> None:
        """After solving x, compute new capacitor current and store state."""
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        v_p = x[p] if p >= 0 else 0.0
        v_m = x[m] if m >= 0 else 0.0
        v_new = v_p - v_m

        C_val = self.capacitance
        Geq = 2.0 * C_val / h
        v_prev = state.get(f"{self.name}_v", 0.0)
        i_prev = state.get(f"{self.name}_i", 0.0)

        i_new = Geq * (v_new - v_prev) - i_prev

        state[f"{self.name}_v"] = v_new
        state[f"{self.name}_i"] = i_new


# ---- Inductor ---------------------------------------------------------------

class L(Element):
    """Inductor / hydraulic inertance.

    Introduces a branch-current unknown j_L (index in branch_idx[name]).

    MNA stamp (DC): short circuit — stamp as voltage source V = 0.
    Trapezoidal companion:
        v_{n+1} = Req * j_{n+1} - Veq
        where  Req = 2L/h,
               Veq = (2L/h) * j_n + v_n   (Pillage 1995, §4.3)

    State keys:
        <name>_i   — branch current at previous step
        <name>_v   — voltage across inductor at previous step
    """

    def __init__(self, name: str, n_plus: str, n_minus: str, inductance: float):
        super().__init__(name, n_plus, n_minus)
        if inductance <= 0:
            raise ValueError(f"Inductance must be > 0 (got {inductance!r})")
        self.inductance = float(inductance)

    def _stamp_vsource_style(
        self,
        G: list[list[float]],
        b: list[float],
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        Req: float,
        Veq: float,
    ) -> None:
        """Stamp inductor as: v_p - v_m - Req*j = Veq."""
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        k = branch_idx[self.name]  # branch current row/col

        if p >= 0:
            G[p][k] += 1.0
            G[k][p] += 1.0
        if m >= 0:
            G[m][k] -= 1.0
            G[k][m] -= 1.0

        G[k][k] -= Req
        b[k] += Veq

    def stamp_dc(self, G, b, node_idx, branch_idx):
        # DC: inductor = wire → Req = 0, Veq = 0
        self._stamp_vsource_style(G, b, node_idx, branch_idx, 0.0, 0.0)

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        L_val = self.inductance
        Req = 2.0 * L_val / h
        i_prev = state.get(f"{self.name}_i", 0.0)
        v_prev = state.get(f"{self.name}_v", 0.0)
        # Trapezoidal: v_{n+1} = (2L/h)*(i_{n+1} - i_n) - v_n
        # KVL row:  v_p - v_m - Req*j = Veq  where Veq = -(Req*i_n + v_n)
        Veq = -(Req * i_prev + v_prev)
        self._stamp_vsource_style(G, b, node_idx, branch_idx, Req, Veq)

    def update_state(
        self,
        state: dict[str, float],
        x: list[float],
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        h: float,
    ) -> None:
        """After solving x, record new inductor current and voltage."""
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        k = branch_idx[self.name]

        v_p = x[p] if p >= 0 else 0.0
        v_m = x[m] if m >= 0 else 0.0
        v_new = v_p - v_m
        i_new = x[k]

        state[f"{self.name}_i"] = i_new
        state[f"{self.name}_v"] = v_new


# ---- Voltage Source ---------------------------------------------------------

class VSource(Element):
    """Ideal voltage source (effort source in any domain).

    Introduces branch-current unknown j_V.
    Stamp: v_p - v_m = V(t)
    """

    def __init__(
        self,
        name: str,
        n_plus: str,
        n_minus: str,
        voltage: float = 0.0,
        waveform: str = "dc",
    ):
        super().__init__(name, n_plus, n_minus)
        self.voltage = float(voltage)
        self.waveform = waveform  # "dc" | "step" | "sin" (future)

    def _v_at(self, t: float) -> float:
        return self.voltage  # dc only for now

    def _stamp_at(
        self,
        G: list[list[float]],
        b: list[float],
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        t: float,
    ) -> None:
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        k = branch_idx[self.name]

        if p >= 0:
            G[p][k] += 1.0
            G[k][p] += 1.0
        if m >= 0:
            G[m][k] -= 1.0
            G[k][m] -= 1.0

        b[k] += self._v_at(t)

    def stamp_dc(self, G, b, node_idx, branch_idx):
        self._stamp_at(G, b, node_idx, branch_idx, 0.0)

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        t = state.get("_t", 0.0)
        self._stamp_at(G, b, node_idx, branch_idx, t)


# ---- Current Source ---------------------------------------------------------

class ISource(Element):
    """Ideal current source (flow source in any domain)."""

    def __init__(self, name: str, n_plus: str, n_minus: str, current: float = 0.0):
        super().__init__(name, n_plus, n_minus)
        self.current = float(current)

    def _stamp(
        self,
        b: list[float],
        node_idx: dict[str, int],
    ) -> None:
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)
        if p >= 0:
            b[p] += self.current
        if m >= 0:
            b[m] -= self.current

    def stamp_dc(self, G, b, node_idx, branch_idx):
        self._stamp(b, node_idx)

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        self._stamp(b, node_idx)


# ---- Diode (nonlinear) -------------------------------------------------------

class Diode(Element):
    """Ideal exponential diode: i = Is * (exp(v/Vt) - 1).

    Uses Newton-linearised companion per iteration:
        i ≈ G_d * v - I_d
        G_d = Is/Vt * exp(v_k/Vt)
        I_d = G_d * v_k - Is * (exp(v_k/Vt) - 1)
    """

    def __init__(
        self,
        name: str,
        n_plus: str,
        n_minus: str,
        Is: float = 1e-14,
        Vt: float = 0.02585,
    ):
        super().__init__(name, n_plus, n_minus)
        self.Is = float(Is)
        self.Vt = float(Vt)

    def stamp_dc(self, G, b, node_idx, branch_idx):
        # Initial operating point (v=0 → i=0)
        pass  # nonlinear; handled via stamp_nl in Newton loop

    def stamp_transient(self, G, b, node_idx, branch_idx, h, state):
        pass  # handled via stamp_nl

    def stamp_nl(self, G, b, node_idx, x):
        """Linearised stamp around current solution x."""
        p = node_idx.get(self.n_plus, -1)
        m = node_idx.get(self.n_minus, -1)

        v_p = x[p] if p >= 0 else 0.0
        v_m = x[m] if m >= 0 else 0.0
        v_d = v_p - v_m

        # Clamp exponent to avoid overflow
        exp_arg = min(v_d / self.Vt, 300.0)
        exp_val = math.exp(exp_arg)
        i_d = self.Is * (exp_val - 1.0)
        Gd = (self.Is / self.Vt) * exp_val  # dI/dV
        Id = Gd * v_d - i_d  # Norton equivalent current source

        # Stamp Norton equivalent
        if p >= 0:
            G[p][p] += Gd
            b[p] += Id
        if m >= 0:
            G[m][m] += Gd
            b[m] -= Id
        if p >= 0 and m >= 0:
            G[p][m] -= Gd
            G[m][p] -= Gd


# ---------------------------------------------------------------------------
# Network builder
# ---------------------------------------------------------------------------

class Network:
    """Acausal lumped-parameter network.

    Usage::

        net = Network()
        net.add(VSource("V1", "n1", "GND", voltage=10.0))
        net.add(R("R1", "n1", "n2", 1000.0))
        net.add(C("C1", "n2", "GND", 1e-6))

        result = simulate(net, t_end=5e-3, dt=1e-6)
        voltages = result["nodes"]["n2"]  # list of node voltages at each time
    """

    def __init__(self):
        self._elements: list[Element] = []

    def add(self, element: Element) -> "Network":
        """Add an element to the network.  Returns self for chaining."""
        self._elements.append(element)
        return self

    # ------------------------------------------------------------------
    # Internal: index assignment
    # ------------------------------------------------------------------

    def _build_indices(self) -> tuple[dict[str, int], dict[str, int], int]:
        """Return (node_idx, branch_idx, n_total).

        node_idx  maps non-ground node name → row/col index (0-based).
        branch_idx maps element name → extra row/col for branch current.
        GND (case-insensitive, also "0") is reference node → not in node_idx.
        """
        ground_names = {"gnd", "0", "ground"}

        # Collect all unique node names in stable order
        seen_nodes: list[str] = []
        seen_set: set[str] = set()
        for el in self._elements:
            for nd in (el.n_plus, el.n_minus):
                if nd.lower() not in ground_names and nd not in seen_set:
                    seen_set.add(nd)
                    seen_nodes.append(nd)

        node_idx: dict[str, int] = {nd: i for i, nd in enumerate(seen_nodes)}

        # Branch-current unknowns: VSource and Inductor
        branch_idx: dict[str, int] = {}
        extra = len(node_idx)
        for el in self._elements:
            if isinstance(el, (VSource, L)):
                branch_idx[el.name] = extra
                extra += 1

        return node_idx, branch_idx, extra

    # ------------------------------------------------------------------
    # Assemble and solve
    # ------------------------------------------------------------------

    def _assemble(
        self,
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        n: int,
        h: float,
        state: dict[str, float],
        transient: bool,
        nl_x: list[float] | None = None,
    ) -> tuple[list[list[float]], list[float]]:
        """Assemble G matrix and b RHS."""
        G = _zeros(n)
        b = _vecz(n)

        for el in self._elements:
            if transient:
                el.stamp_transient(G, b, node_idx, branch_idx, h, state)
            else:
                el.stamp_dc(G, b, node_idx, branch_idx)

        # Nonlinear elements (Newton linearisation)
        if nl_x is not None:
            for el in self._elements:
                el.stamp_nl(G, b, node_idx, nl_x)

        return G, b

    def _solve_dc(
        self,
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        n: int,
        nl_tol: float = 1e-9,
        nl_max_iter: int = 100,
    ) -> list[float]:
        """Solve DC (steady-state) with Newton–Raphson for nonlinear elements."""
        has_nl = any(isinstance(el, Diode) for el in self._elements)

        state: dict[str, float] = {}
        x = _vecz(n)

        if not has_nl:
            G, b = self._assemble(node_idx, branch_idx, n, 0.0, state, False, None)
            return _lu_solve(G, b)

        # Newton loop
        for _it in range(nl_max_iter):
            G, b = self._assemble(node_idx, branch_idx, n, 0.0, state, False, x)
            x_new = _lu_solve(G, b)
            dx = [x_new[i] - x[i] for i in range(n)]
            x = x_new
            if _norm_inf(dx) < nl_tol:
                break

        return x

    def _solve_step(
        self,
        node_idx: dict[str, int],
        branch_idx: dict[str, int],
        n: int,
        h: float,
        state: dict[str, float],
        nl_tol: float = 1e-9,
        nl_max_iter: int = 50,
    ) -> list[float]:
        """Solve one transient step via implicit trapezoidal + Newton."""
        has_nl = any(isinstance(el, Diode) for el in self._elements)

        # Initial guess: previous solution
        x = state.get("_x_prev", _vecz(n))
        if not isinstance(x, list):
            x = list(x)

        if not has_nl:
            G, b = self._assemble(node_idx, branch_idx, n, h, state, True, None)
            return _lu_solve(G, b)

        # Newton loop for nonlinear elements
        for _it in range(nl_max_iter):
            G, b = self._assemble(node_idx, branch_idx, n, h, state, True, x)
            x_new = _lu_solve(G, b)
            dx = [x_new[i] - x[i] for i in range(n)]
            x = x_new
            if _norm_inf(dx) < nl_tol:
                break

        return x


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _vsource_names(net: Network) -> set[str]:
    """Return the set of VSource element names in the network.

    The MNA convention for voltage sources produces a branch-current variable
    whose sign is opposite to the physically delivered current (j_V_internal =
    −I_delivered).  We negate these at output time so that callers see the
    conventional "current out of n_plus" sign.
    """
    return {el.name for el in net._elements if isinstance(el, VSource)}


def steady_state(net: Network) -> dict[str, Any]:
    """Compute the DC operating point of the network.

    Returns
    -------
    dict with keys:
        ``nodes``    — dict mapping node name → DC voltage/effort
        ``branches`` — dict mapping branch name → DC current/flow
        ``ok``       — True
    """
    node_idx, branch_idx, n = net._build_indices()
    x = net._solve_dc(node_idx, branch_idx, n)

    vs_names = _vsource_names(net)
    nodes = {name: x[idx] for name, idx in node_idx.items()}
    branches = {
        name: (-x[idx] if name in vs_names else x[idx])
        for name, idx in branch_idx.items()
    }

    return {"ok": True, "nodes": nodes, "branches": branches}


def simulate(
    net: Network,
    t_end: float,
    dt: float,
    t_start: float = 0.0,
    initial_conditions: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Transient simulation using implicit trapezoidal integration.

    Parameters
    ----------
    net : Network
        The assembled network.
    t_end : float
        End time (seconds / domain-appropriate unit).
    dt : float
        Time step (must be > 0).
    t_start : float
        Start time (default 0).
    initial_conditions : dict, optional
        Map of ``"<element_name>_v"`` / ``"<element_name>_i"`` to initial
        values.  Capacitor voltages default to 0; inductor currents default
        to 0.

    Returns
    -------
    dict with keys:
        ``t``        — list of time points (length N+1)
        ``nodes``    — dict mapping node name → list of effort values (len N+1)
        ``branches`` — dict mapping branch name → list of flow values (len N+1)
        ``ok``       — True
    """
    if dt <= 0:
        return {"ok": False, "reason": "dt must be > 0"}
    if t_end <= t_start:
        return {"ok": False, "reason": "t_end must be > t_start"}

    node_idx, branch_idx, n_total = net._build_indices()
    vs_names = _vsource_names(net)

    # Initialise state
    state: dict[str, Any] = {}
    if initial_conditions:
        state.update(initial_conditions)
    state["_t"] = t_start

    # Compute IC solution (t=0): use DC solve to get operating point,
    # then honour initial capacitor voltages from user.
    # For capacitors with specified IC, pre-load their state.
    for el in net._elements:
        if isinstance(el, C):
            if f"{el.name}_v" not in state:
                state[f"{el.name}_v"] = 0.0
            if f"{el.name}_i" not in state:
                state[f"{el.name}_i"] = 0.0
        if isinstance(el, L):
            if f"{el.name}_i" not in state:
                state[f"{el.name}_i"] = 0.0
            if f"{el.name}_v" not in state:
                state[f"{el.name}_v"] = 0.0

    # Get initial x by solving with DC (to capture sources)
    x0 = net._solve_dc(node_idx, branch_idx, n_total)

    # But override with actual capacitor ICs for the voltage reading
    # (The DC solve gives V through R network etc.)
    # For clean start, use DC solution as initial x.
    state["_x_prev"] = x0

    def _branch_val(name: str, raw: float) -> float:
        """Apply sign convention: VSource branch currents are negated at output."""
        return -raw if name in vs_names else raw

    # Collect results
    t_vals: list[float] = [t_start]
    node_vals: dict[str, list[float]] = {
        nd: [x0[idx]] for nd, idx in node_idx.items()
    }
    branch_vals: dict[str, list[float]] = {
        br: [_branch_val(br, x0[idx])] for br, idx in branch_idx.items()
    }

    t = t_start
    while t < t_end - 1e-15 * dt:
        h = min(dt, t_end - t)
        t_new = t + h
        state["_t"] = t_new

        x = net._solve_step(node_idx, branch_idx, n_total, h, state)

        # Update reactive element states (trapezoidal post-step)
        for el in net._elements:
            if isinstance(el, C):
                el.update_state(state, x, node_idx, h)
            elif isinstance(el, L):
                el.update_state(state, x, node_idx, branch_idx, h)

        state["_x_prev"] = x
        t = t_new

        t_vals.append(t)
        for nd, idx in node_idx.items():
            node_vals[nd].append(x[idx])
        for br, idx in branch_idx.items():
            branch_vals[br].append(_branch_val(br, x[idx]))

    return {
        "ok": True,
        "t": t_vals,
        "nodes": node_vals,
        "branches": branch_vals,
    }


# ---------------------------------------------------------------------------
# Domain convenience constructors
# ---------------------------------------------------------------------------

def make_thermal_r(name: str, n_hot: str, n_cold: str, R_th: float) -> R:
    """Thermal resistor.  effort=temperature(K), flow=heat-flow(W)."""
    return R(name, n_hot, n_cold, R_th)


def make_thermal_c(name: str, n_hot: str, n_ref: str, C_th: float) -> C:
    """Thermal capacitance.  C_th in J/K."""
    return C(name, n_hot, n_ref, C_th)


def make_thermal_source(name: str, n_plus: str, n_minus: str, Q: float) -> ISource:
    """Heat source (flow source) Q watts."""
    return ISource(name, n_plus, n_minus, Q)


def make_hydraulic_r(name: str, n_in: str, n_out: str, R_hyd: float) -> R:
    """Hydraulic resistance.  effort=pressure(Pa), flow=volumetric-flow(m³/s)."""
    return R(name, n_in, n_out, R_hyd)


def make_hydraulic_c(name: str, n_in: str, n_ref: str, C_hyd: float) -> C:
    """Hydraulic accumulator / compliance.  C_hyd in m³/Pa."""
    return C(name, n_in, n_ref, C_hyd)


def make_hydraulic_l(name: str, n_in: str, n_out: str, L_hyd: float) -> L:
    """Hydraulic inertance.  L_hyd in kg/m⁴."""
    return L(name, n_in, n_out, L_hyd)


def make_mech_r(name: str, n_a: str, n_b: str, b_damp: float) -> R:
    """Mechanical damper.  effort=force(N), flow=velocity(m/s)."""
    return R(name, n_a, n_b, b_damp)


def make_mech_m(name: str, n_a: str, n_ref: str, mass: float) -> C:
    """Mass (effort=force, flow=velocity → mass analogous to capacitor)."""
    return C(name, n_a, n_ref, mass)


def make_mech_k(name: str, n_a: str, n_b: str, stiffness: float) -> L:
    """Spring (stiffness k → inductance 1/k)."""
    return L(name, n_a, n_b, 1.0 / stiffness)


def make_force_source(name: str, n_plus: str, n_minus: str, force: float) -> ISource:
    """Constant force source."""
    return ISource(name, n_plus, n_minus, force)


# ---------------------------------------------------------------------------
# LLM tool registration
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx  # noqa: F401 — type hint

    _sysml1d_simulate_spec = ToolSpec(
        name="sysml1d_simulate",
        description=(
            "Acausal 1D lumped-parameter network simulation (electrical, thermal, "
            "hydraulic, mechanical domains via effort/flow analogy).\n"
            "\n"
            "Assembles a generalised MNA system and integrates with implicit "
            "trapezoidal (Crank–Nicolson) + Newton–Raphson.  Pure Python — no "
            "numpy dependency.\n"
            "\n"
            "Elements: R, L, C, VSource, ISource, Diode.\n"
            "Convenience factories: make_thermal_r/c/source, make_hydraulic_r/c/l, "
            "make_mech_r/m/k/force_source.\n"
            "\n"
            "Returns {ok:true, t:[...], nodes:{...}, branches:{...}} for transient; "
            "{ok:true, nodes:{...}, branches:{...}} for steady-state.\n"
            "Errors returned as {ok:false, reason:...} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "description": (
                        "List of element descriptors. Each has: "
                        "{type, name, n_plus, n_minus, ...params}. "
                        "Types: R, L, C, VSource, ISource, Diode."
                    ),
                    "items": {"type": "object"},
                },
                "t_end": {
                    "type": "number",
                    "description": "Simulation end time (s). Omit for steady-state only.",
                },
                "dt": {
                    "type": "number",
                    "description": "Time step (s). Required for transient.",
                },
                "t_start": {
                    "type": "number",
                    "description": "Start time (default 0).",
                },
                "initial_conditions": {
                    "type": "object",
                    "description": (
                        "Map of '<element_name>_v' or '<element_name>_i' to "
                        "initial value."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["transient", "dc"],
                    "description": "'transient' (default) or 'dc' for DC operating point.",
                },
            },
            "required": ["elements"],
        },
    )

    @register(_sysml1d_simulate_spec, write=False)
    async def run_sysml1d_simulate(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        try:
            net = Network()
            for el_def in a.get("elements", []):
                el_type = el_def.get("type", "")
                name = el_def.get("name", "")
                n_plus = el_def.get("n_plus", "")
                n_minus = el_def.get("n_minus", "GND")

                if el_type == "R":
                    net.add(R(name, n_plus, n_minus, el_def["resistance"]))
                elif el_type == "C":
                    net.add(C(name, n_plus, n_minus, el_def["capacitance"]))
                elif el_type == "L":
                    net.add(L(name, n_plus, n_minus, el_def["inductance"]))
                elif el_type == "VSource":
                    net.add(
                        VSource(name, n_plus, n_minus, el_def.get("voltage", 0.0))
                    )
                elif el_type == "ISource":
                    net.add(
                        ISource(name, n_plus, n_minus, el_def.get("current", 0.0))
                    )
                elif el_type == "Diode":
                    net.add(
                        Diode(
                            name,
                            n_plus,
                            n_minus,
                            Is=el_def.get("Is", 1e-14),
                            Vt=el_def.get("Vt", 0.02585),
                        )
                    )
                else:
                    return err_payload(f"unknown element type: {el_type!r}", "BAD_ARGS")

            mode = a.get("mode", "transient")
            if mode == "dc":
                result = steady_state(net)
            else:
                t_end = a.get("t_end")
                dt = a.get("dt")
                if t_end is None or dt is None:
                    return err_payload("t_end and dt required for transient mode", "BAD_ARGS")
                result = simulate(
                    net,
                    t_end=t_end,
                    dt=dt,
                    t_start=a.get("t_start", 0.0),
                    initial_conditions=a.get("initial_conditions"),
                )

            return ok_payload(result)

        except Exception as exc:
            return err_payload(str(exc), "INTERNAL")

except ImportError:
    pass  # kerf_chat not available (e.g. during bare unit-test runs)
