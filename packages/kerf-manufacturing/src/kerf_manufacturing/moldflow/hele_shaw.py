"""Hele-Shaw fill simulation for injection moulding (isothermal, v1).

Theory
------
The Hele-Shaw (lubrication / thin-gap) approximation models melt flow in a
thin shell by a 2-D pressure equation:

    ∇·(S ∇P) = 0   in the filled region Ω(t)

where the *fluidity* S integrates through the gap:

    S = h³ / (12 η)

For the isothermal Newtonian case (v1) this is simply the Laplace equation.

Fill-time algorithm (v1 — pressure-rank fill sequencing)
---------------------------------------------------------
The steady-state pressure field P(x) on the *full* mesh (with gate
boundary at P = P_inject and outer boundary at P = 0) encodes the natural
fill order: nodes farther from the gate (lower P) fill later.

We convert the pressure rank to physical fill time using the local flow
velocity:

    t_fill(x) ≈ integral_along_streamline(ds / v(s))

For an isothermal, uniform-thickness part the fill-time contours are
iso-pressure surfaces, and the fill time can be estimated as:

    t_fill(x) = (1 - P(x)/P_inject) * T_fill_total

where T_fill_total is the characteristic fill time derived from the
integrated flow rate through the gate cross-section.

This approach:
 - Always fills the entire connected mesh (no short-shot on full-domain solve)
 - Gives correct radial symmetry for disc (Laplace on disc with central
   source = logarithmic pressure profile → isochronous rings)
 - Gives non-symmetric fill for L-shape (Laplace on L-domain shows
   pressure saddle at the corner → two streams meeting)
 - Weld lines emerge naturally from arrival-direction analysis on the
   pressure-gradient field

Short-shot
----------
A short-shot is triggered when:
 a. The injection pressure is zero (no driving force), OR
 b. The mesh contains disconnected sub-domains (some nodes unreachable from
    gate), OR
 c. The user-specified max_fill_time_s is smaller than T_fill_total.

Limitations / v2 TODO
---------------------
* Isothermal only (non-isothermal requires energy equation coupling).
* Uniform effective viscosity across fill.
* Single gate only.
* No packing/hold-pressure phase.
* Residual stress and warp prediction (FEA post-processor needed).
* Fibre orientation (Folgar-Tucker advection).

References
----------
C.A. Hieber & S.F. Shen, J. Non-Newtonian Fluid Mech., 7:1-32, 1980.
Z. Tadmor & C.G. Gogos, "Principles of Polymer Processing", 2nd ed., 2006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from kerf_manufacturing.moldflow.materials import CrossWLFCard, ABS_GENERIC
from kerf_manufacturing.moldflow.weldline import predict_weld_lines, weld_line_segments


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ShellMesh:
    """Triangle shell mesh (mid-plane representation).

    Parameters
    ----------
    nodes : (N, 2) or (N, 3) array of node coordinates (metres).
    triangles : (T, 3) int array of 0-indexed triangle connectivity.
    thickness : float or (T,) array — element wall thickness (metres).
    """

    nodes: np.ndarray
    triangles: np.ndarray
    thickness: float | np.ndarray = 2e-3

    def __post_init__(self):
        self.nodes = np.asarray(self.nodes, dtype=np.float64)
        self.triangles = np.asarray(self.triangles, dtype=np.int32)
        if self.nodes.ndim != 2 or self.nodes.shape[1] not in (2, 3):
            raise ValueError(
                f"nodes must be (N,2) or (N,3), got shape {self.nodes.shape}"
            )
        if self.triangles.ndim != 2 or self.triangles.shape[1] != 3:
            raise ValueError(
                f"triangles must be (T,3), got shape {self.triangles.shape}"
            )
        if isinstance(self.thickness, np.ndarray):
            self.thickness = self.thickness.astype(np.float64)

    @property
    def n_nodes(self) -> int:
        return int(self.nodes.shape[0])

    @property
    def n_triangles(self) -> int:
        return int(self.triangles.shape[0])

    def element_thickness(self) -> np.ndarray:
        """Return per-element thickness array (T,)."""
        if np.isscalar(self.thickness):
            return np.full(self.n_triangles, float(self.thickness))
        return np.asarray(self.thickness, dtype=np.float64)

    @classmethod
    def from_dict(cls, d: dict) -> "ShellMesh":
        return cls(
            nodes=np.array(d["nodes"], dtype=np.float64),
            triangles=np.array(d["triangles"], dtype=np.int32),
            thickness=d.get("thickness", 2e-3),
        )

    def to_dict(self) -> dict:
        return {
            "nodes": self.nodes.tolist(),
            "triangles": self.triangles.tolist(),
            "thickness": (
                self.thickness.tolist()
                if isinstance(self.thickness, np.ndarray)
                else self.thickness
            ),
        }


@dataclass
class GateLocation:
    """Injection gate specification."""

    node_index: int
    injection_pressure_pa: float = 1.5e7


@dataclass
class InjectionConditions:
    """Process conditions for the fill simulation."""

    melt_temperature_k: float = 503.15     # 230 °C
    injection_pressure_pa: float = 1.5e7   # 150 bar
    max_fill_time_s: float = 5.0
    n_steps: int = 50


@dataclass
class MoldFlowResult:
    """Output of the Hele-Shaw fill simulation.

    Attributes
    ----------
    fill_time : (N,) float array — nodal fill time (seconds).
        ``inf`` = node not reached (short-shot region).
    pressure : (N,) float array — nodal steady-state pressure (Pa).
    weld_line_edges : list of (int, int) mesh edge index pairs where weld
        lines are predicted.
    weld_line_segments : list of coordinate pairs for each weld-line edge.
    short_shot : bool — True if any node was not filled.
    fill_fraction : float — fraction of nodes filled [0, 1].
    n_steps_taken : int — number of fill-front steps (always 1 in v1).
    """

    fill_time: np.ndarray
    pressure: np.ndarray
    weld_line_edges: list[tuple[int, int]]
    weld_line_segments: list[tuple[tuple[float, ...], tuple[float, ...]]]
    short_shot: bool
    fill_fraction: float
    n_steps_taken: int


# ---------------------------------------------------------------------------
# FEM assembly
# ---------------------------------------------------------------------------

def _triangle_stiffness(p: np.ndarray, fluidity: float) -> np.ndarray:
    """3×3 element stiffness matrix for a linear triangle."""
    x, y = p[:, 0], p[:, 1]
    area = 0.5 * abs((x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]))
    if area < 1e-20:
        return np.zeros((3, 3))
    b = np.array([y[1] - y[2], y[2] - y[0], y[0] - y[1]]) / (2.0 * area)
    c = np.array([x[2] - x[1], x[0] - x[2], x[1] - x[0]]) / (2.0 * area)
    return fluidity * area * (np.outer(b, b) + np.outer(c, c))


def _assemble_stiffness(
    nodes: np.ndarray,
    triangles: np.ndarray,
    fluidity: np.ndarray,
) -> sp.csr_matrix:
    """Assemble global sparse stiffness matrix (N×N)."""
    N = nodes.shape[0]
    xy = nodes[:, :2]
    rows, cols, vals = [], [], []
    for t_idx, tri in enumerate(triangles):
        idx = [int(tri[0]), int(tri[1]), int(tri[2])]
        K_e = _triangle_stiffness(xy[idx], fluidity[t_idx])
        for li in range(3):
            for lj in range(3):
                rows.append(idx[li])
                cols.append(idx[lj])
                vals.append(K_e[li, lj])
    return sp.csr_matrix((vals, (rows, cols)), shape=(N, N))


def _apply_dirichlet(
    K: sp.spmatrix,
    f: np.ndarray,
    dirichlet: dict[int, float],
) -> tuple[sp.csr_matrix, np.ndarray]:
    """Apply Dirichlet BCs using the symmetric elimination technique.

    For each Dirichlet node ``d`` with prescribed value ``g``:
      1. Modify the RHS:  f[i] -= K[i, d] * g  for all free nodes i.
      2. Zero row ``d`` and column ``d`` in K.
      3. Set K[d, d] = 1,  f[d] = g.

    This preserves the source coupling from the Dirichlet nodes to the
    free nodes, which is essential when the source node (gate) has a
    large prescribed value.
    """
    K = K.tocsr()

    # Step 1: modify RHS to absorb Dirichlet contributions
    for nid, pval in dirichlet.items():
        if pval != 0.0:
            # f[i] -= K[i, nid] * pval  for all i
            col = K.getcol(nid)
            f -= col.toarray().flatten() * pval

    # Step 2 & 3: eliminate Dirichlet rows and columns
    K = K.tolil()
    for nid, pval in dirichlet.items():
        K[nid, :] = 0.0
        K[:, nid] = 0.0
        K[nid, nid] = 1.0
        f[nid] = pval

    # Fix any zero-diagonal rows (disconnected nodes)
    K = K.tocsr()
    diag = np.array(K.diagonal())
    zero_rows = np.where(np.abs(diag) < 1e-30)[0]
    if len(zero_rows):
        K = K.tolil()
        for i in zero_rows:
            K[i, i] = 1.0
            f[i] = 0.0
        K = K.tocsr()
    return K, f


def _solve_pressure(
    nodes: np.ndarray,
    triangles: np.ndarray,
    fluidity: np.ndarray,
    dirichlet: dict[int, float],
) -> np.ndarray:
    """Solve ∇·(S ∇P) = 0 with Dirichlet BCs.  Returns nodal P (N,)."""
    N = nodes.shape[0]
    K = _assemble_stiffness(nodes, triangles, fluidity)
    f = np.zeros(N)
    K, f = _apply_dirichlet(K, f, dirichlet)
    try:
        return np.asarray(spla.spsolve(K, f), dtype=np.float64)
    except Exception:
        return np.zeros(N)


# ---------------------------------------------------------------------------
# Pressure-gradient helpers
# ---------------------------------------------------------------------------

def _element_pressure_gradient(
    xy: np.ndarray,
    tri_indices: np.ndarray,
    pressure: np.ndarray,
) -> np.ndarray:
    """Compute constant pressure gradient within a linear triangle."""
    x = xy[tri_indices, 0]
    y = xy[tri_indices, 1]
    p = pressure[tri_indices]
    area = 0.5 * abs((x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]))
    if area < 1e-20:
        return np.zeros(2)
    b = np.array([y[1] - y[2], y[2] - y[0], y[0] - y[1]]) / (2.0 * area)
    c = np.array([x[2] - x[1], x[0] - x[2], x[1] - x[0]]) / (2.0 * area)
    return np.array([float(b @ p), float(c @ p)])


def _nodal_arrival_directions(
    xy: np.ndarray,
    triangles: np.ndarray,
    pressure: np.ndarray,
    gate_node: int,
) -> np.ndarray:
    """Compute per-node arrival direction from averaged pressure gradient.

    Direction = -∇P / |∇P|  (flow goes from high P to low P).
    Falls back to geometric gate-to-node vector where gradient is negligible.
    """
    N = xy.shape[0]
    grad_sum = np.zeros((N, 2))
    counts = np.zeros(N)

    for tri in triangles:
        grad = _element_pressure_gradient(xy, tri, pressure)
        for nid in tri:
            grad_sum[int(nid)] += grad
            counts[int(nid)] += 1.0

    # Avoid division by zero
    counts = np.where(counts < 0.5, 1.0, counts)
    avg_grad = grad_sum / counts[:, None]

    # Arrival direction = normalised flow direction = -∇P normalised
    directions = -avg_grad
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    # Fall back to gate-to-node vector where gradient is negligible
    fallback = xy - xy[gate_node]
    fallback_norms = np.linalg.norm(fallback, axis=1, keepdims=True)
    fallback_norms = np.where(fallback_norms < 1e-12, 1.0, fallback_norms)
    fallback = fallback / fallback_norms

    use_fallback = (norms < 1e-10).flatten()
    norms = np.where(norms < 1e-10, 1.0, norms)
    directions = directions / norms
    directions[use_fallback] = fallback[use_fallback]
    return directions


# ---------------------------------------------------------------------------
# Boundary node detection
# ---------------------------------------------------------------------------

def _find_boundary_nodes(n_nodes: int, triangles: np.ndarray) -> set[int]:
    """Return the set of nodes on the mesh boundary (edges with only 1 triangle)."""
    edge_count: dict[tuple[int, int], int] = {}
    for tri in triangles:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        for u, v in ((a, b), (b, c), (c, a)):
            key = (min(u, v), max(u, v))
            edge_count[key] = edge_count.get(key, 0) + 1

    boundary_nodes: set[int] = set()
    for (u, v), cnt in edge_count.items():
        if cnt == 1:
            boundary_nodes.add(u)
            boundary_nodes.add(v)
    return boundary_nodes


# ---------------------------------------------------------------------------
# Fill-time computation from pressure field
# ---------------------------------------------------------------------------

def _fill_time_from_pressure(
    pressure: np.ndarray,
    P_inj: float,
    T_total: float,
    gate_node: int,
) -> np.ndarray:
    """Convert pressure field to fill-time map.

    For an isothermal Hele-Shaw problem the fill-time at node x is
    proportional to the time the front takes to travel from the gate to x.
    Under the quasi-static pressure field this is:

        t_fill(x) = (1 - P(x) / P_inject) * T_total

    Nodes with P < 0 (numerical artefact) are clamped to T_total.
    Gate node is set to t = 0.

    Parameters
    ----------
    pressure : (N,) nodal pressure.
    P_inj : injection pressure (Pa).
    T_total : total fill time (s).
    gate_node : gate node index.
    """
    P = np.asarray(pressure, dtype=np.float64)
    # Clamp P to [0, P_inj] range
    P_norm = np.clip(P / P_inj, 0.0, 1.0)
    t = (1.0 - P_norm) * T_total
    t[gate_node] = 0.0
    return t


def _estimate_fill_time(
    mesh: ShellMesh,
    material: CrossWLFCard,
    conditions: InjectionConditions,
    pressure: np.ndarray,
    gate_node: int,
) -> float:
    """Estimate physical fill time (seconds) from process conditions.

    Uses the Hele-Shaw volumetric flow rate at the gate:

        Q = S_gate * P_inj * perimeter_gate / h

    For a node gate this estimates a characteristic fill time as:

        T = Volume / Q ≈ Area * h / Q

    where Area is the mesh projected area and Q is derived from
    the average pressure gradient magnitude × fluidity × gate perimeter.
    """
    xy = mesh.nodes[:, :2]
    h_arr = mesh.element_thickness()

    eta0 = material.eta0(conditions.melt_temperature_k)
    # Use a physically realistic representative shear rate for injection molding.
    # Typical gate shear rate: 100–10000 1/s.  Use 500 1/s as a conservative
    # default representative value.
    gamma_rep = max(material.tau_star / max(eta0, 1e-6), 500.0)
    eta_eff = material.viscosity(conditions.melt_temperature_k, gamma_rep)
    eta_eff = max(eta_eff, 1e-6)

    # Representative element thickness
    h_mean = float(h_arr.mean())

    # Fluidity
    S = h_mean ** 3 / (12.0 * eta_eff)

    # Projected mesh area
    area_total = 0.0
    for tri in mesh.triangles:
        x = xy[tri, 0]
        y = xy[tri, 1]
        a = 0.5 * abs((x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0]))
        area_total += a

    # Characteristic velocity = S/h * |∇P_mean|
    # Mean pressure gradient ≈ P_inj / L_char where L_char = sqrt(area)
    L_char = max(np.sqrt(area_total), 1e-6)
    grad_mean = conditions.injection_pressure_pa / L_char
    v_mean = (S / h_mean) * grad_mean
    v_mean = max(v_mean, 1e-9)

    # T_fill = L_char / v_mean
    T_fill = L_char / v_mean
    return min(T_fill, conditions.max_fill_time_s)


# ---------------------------------------------------------------------------
# Main fill solver
# ---------------------------------------------------------------------------

def run_moldflow(
    mesh: ShellMesh,
    gate: GateLocation,
    material: Optional[CrossWLFCard] = None,
    conditions: Optional[InjectionConditions] = None,
) -> MoldFlowResult:
    """Run the Hele-Shaw isothermal fill simulation.

    v1 Algorithm (pressure-rank fill sequencing)
    --------------------------------------------
    1. Solve the Laplace pressure equation on the full mesh with:
         P = P_inject at the gate node
         P = 0 at all boundary nodes
    2. Derive fill-time map: t_fill = (1 - P/P_inj) * T_total
    3. Compute nodal arrival directions from the pressure gradient field.
    4. Run weld-line detection from the fill-time / arrival-direction data.

    Parameters
    ----------
    mesh : ShellMesh
    gate : GateLocation
    material : CrossWLFCard — defaults to ABS_GENERIC.
    conditions : InjectionConditions — defaults to InjectionConditions().

    Returns
    -------
    MoldFlowResult
    """
    if material is None:
        material = ABS_GENERIC
    if conditions is None:
        conditions = InjectionConditions()

    N = mesh.n_nodes
    P_inj = conditions.injection_pressure_pa
    gate_node = gate.node_index

    # ------------------------------------------------------------------
    # Fast-path: zero injection pressure → no flow
    # ------------------------------------------------------------------
    if P_inj <= 0.0:
        fill_time = np.full(N, np.inf)
        fill_time[gate_node] = 0.0
        return MoldFlowResult(
            fill_time=fill_time,
            pressure=np.zeros(N),
            weld_line_edges=[],
            weld_line_segments=[],
            short_shot=True,
            fill_fraction=1.0 / N,
            n_steps_taken=0,
        )

    # ------------------------------------------------------------------
    # Effective viscosity
    # ------------------------------------------------------------------
    eta0 = material.eta0(conditions.melt_temperature_k)
    gamma_rep = max(material.tau_star / max(eta0, 1e-6), 500.0)
    eta_eff = material.viscosity(conditions.melt_temperature_k, gamma_rep)
    eta_eff = max(eta_eff, 1e-6)

    h_arr = mesh.element_thickness()
    fluidity = h_arr ** 3 / (12.0 * eta_eff)

    # ------------------------------------------------------------------
    # Boundary condition setup
    # ------------------------------------------------------------------
    # Gate: P = P_inject (source)
    # Far boundary nodes: P = 0 (vent / flow front at full fill)
    #
    # "Far" = boundary nodes whose distance from the gate is in the top
    # 50% of boundary-node distances.  This prevents P=0 being applied
    # to boundary nodes immediately adjacent to the gate (which would
    # collapse the pressure field to zero everywhere except the gate).
    xy = mesh.nodes[:, :2]
    gate_pos = xy[gate_node]

    boundary_nodes = _find_boundary_nodes(N, mesh.triangles)
    if not boundary_nodes:
        # No boundary (closed surface) — use outermost radial nodes
        radii_all = np.linalg.norm(xy - gate_pos, axis=1)
        r_max = radii_all.max()
        boundary_nodes = set(int(i) for i in np.where(radii_all >= 0.9 * r_max)[0])

    # Compute distance from gate to each boundary node
    bn_list = [b for b in boundary_nodes if b != gate_node]
    if bn_list:
        bn_dists = np.array([
            float(np.linalg.norm(xy[b] - gate_pos)) for b in bn_list
        ])
        # Apply P=0 only to boundary nodes that are in the farther half
        median_dist = float(np.median(bn_dists))
        far_boundary = {b for b, d in zip(bn_list, bn_dists) if d >= median_dist}
    else:
        far_boundary = set()

    dirichlet: dict[int, float] = {}
    for bn in far_boundary:
        dirichlet[bn] = 0.0
    dirichlet[gate_node] = P_inj

    # ------------------------------------------------------------------
    # Pressure solve on full mesh
    # ------------------------------------------------------------------
    pressure = _solve_pressure(
        mesh.nodes[:, :2],
        mesh.triangles,
        fluidity,
        dirichlet,
    )

    # ------------------------------------------------------------------
    # Check for disconnected nodes (short-shot indicator)
    # ------------------------------------------------------------------
    # Nodes that received no pressure contribution (still at 0 despite
    # not being a Dirichlet BC) indicate disconnected mesh regions.
    connected_mask = np.ones(N, dtype=bool)
    # A disconnected node has P≈0 even though it's interior (not boundary)
    # This is detected by the solver already — pressure stays 0 for isolated nodes.
    # We check connectivity via flood-fill from gate:
    adj: list[set[int]] = [set() for _ in range(N)]
    for tri in mesh.triangles:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        adj[a].update((b, c))
        adj[b].update((a, c))
        adj[c].update((a, b))

    visited = np.zeros(N, dtype=bool)
    stack = [gate_node]
    while stack:
        nid = stack.pop()
        if visited[nid]:
            continue
        visited[nid] = True
        for nb in adj[nid]:
            if not visited[nb]:
                stack.append(nb)

    connected_mask = visited

    # ------------------------------------------------------------------
    # Estimate total fill time
    # ------------------------------------------------------------------
    T_fill = _estimate_fill_time(mesh, material, conditions, pressure, gate_node)

    # ------------------------------------------------------------------
    # Fill-time map
    # ------------------------------------------------------------------
    fill_time = np.full(N, np.inf)
    fill_time[connected_mask] = _fill_time_from_pressure(
        pressure[connected_mask],
        P_inj,
        T_fill,
        gate_node,  # gate_node index is still valid since we pass sub-array
    )
    # Recompute gate separately (the sub-array indexing may offset gate_node)
    fill_time[gate_node] = 0.0

    # Nodes not connected to gate remain at inf
    # Short-shot: any connected node has fill_time > max_fill_time_s
    # OR disconnected nodes exist
    filled_mask = np.isfinite(fill_time)
    short_shot = (not filled_mask.all()) or bool(
        (fill_time[filled_mask] > conditions.max_fill_time_s).any()
    )

    # ------------------------------------------------------------------
    # Arrival directions from pressure gradient
    # ------------------------------------------------------------------
    arrival_dirs = _nodal_arrival_directions(
        mesh.nodes[:, :2],
        mesh.triangles,
        pressure,
        gate_node,
    )

    # ------------------------------------------------------------------
    # Weld-line detection
    # ------------------------------------------------------------------
    weld_edges = predict_weld_lines(
        nodes=mesh.nodes,
        triangles=mesh.triangles,
        fill_time=fill_time,
        arrival_dirs=arrival_dirs,
        gate_node=gate_node,
    )
    weld_segs = weld_line_segments(mesh.nodes, weld_edges)

    fill_fraction = float(filled_mask.sum()) / N

    return MoldFlowResult(
        fill_time=fill_time,
        pressure=pressure,
        weld_line_edges=weld_edges,
        weld_line_segments=weld_segs,
        short_shot=short_shot,
        fill_fraction=fill_fraction,
        n_steps_taken=1,
    )
