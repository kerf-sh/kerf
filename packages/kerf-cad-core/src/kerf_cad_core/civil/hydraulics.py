"""
kerf_cad_core.civil.hydraulics — Pipe-network hydraulics and open-channel flow.

Provides:
  PipeNetwork  — Steady-state pressurised pipe network solver.
                 Nodes carry demand (L/s) and elevation (m).
                 Pipes carry length (m), diameter (m), roughness (mm).
                 Solver: Hardy-Cross iterative loop-correction method with a
                 linear-theory first-step initialisation.
                 Head-loss: Hazen-Williams *or* Darcy-Weisbach (user's choice).

  solve_pipe_network() — Functional entry-point; returns NodeResult / PipeResult
                         dicts.  Never raises — returns {ok: False, reason: ...}.

  manning_normal_depth() — Gravity-sewer / open-channel single-reach helper.
                           Manning's equation for a *rectangular* cross-section.
                           Returns normal depth, velocity, Froude number, and flow
                           regime.  Never raises.

References
----------
  Hardy-Cross (1936) "Analysis of flow in networks of conduits or conductors",
      Univ. Illinois Bull. 286.
  Hazen-Williams: hf = 10.67 · L · Q^1.852 / (C^1.852 · D^4.87)   [SI, Q in m³/s]
  Darcy-Weisbach: hf = f · (L/D) · V²/(2g);  friction factor by Colebrook-White
      iterative, seeded with Swamee-Jain approximation.
  Manning's: Q = (1/n) · A · R^(2/3) · S^(1/2);  normal depth by bisection.

Units: SI throughout (metres, m³/s, Pa).  Internal Q in m³/s; velocities m/s.
Author: imranparuk
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665          # gravitational acceleration (m/s²)
_WATER_RHO = 1000.0   # water density (kg/m³)
_WATER_NU = 1.004e-6  # kinematic viscosity of water at ~20 °C (m²/s)
_EPS = 1e-12


# ---------------------------------------------------------------------------
# Data classes — network definition
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Pressure node in a pipe network.

    Parameters
    ----------
    node_id : str
        Unique identifier.
    elevation : float
        Elevation above datum (m).
    demand : float
        External demand/withdrawal, positive = consumer, negative = source
        (m³/s).  The network must have at least one supply node (demand < 0).
    head_fixed : Optional[float]
        If given, this node is a *reservoir* / fixed-head node and its head
        is held at this value throughout the solve.  demand is ignored for
        fixed-head nodes during balancing but is reported.
    """
    node_id: str
    elevation: float
    demand: float = 0.0
    head_fixed: Optional[float] = None


@dataclass
class Pipe:
    """Pipe segment between two nodes.

    Parameters
    ----------
    pipe_id : str
        Unique identifier.
    start_node : str
        Identifier of the upstream/start node.
    end_node : str
        Identifier of the downstream/end node.
    length : float
        Pipe length (m), > 0.
    diameter : float
        Internal diameter (m), > 0.
    roughness : float
        Absolute roughness (mm).  Used in Darcy-Weisbach.
        For Hazen-Williams supply a *C factor* via ``hw_c`` instead.
    hw_c : float
        Hazen-Williams C coefficient (dimensionless).  Default 120.
        Only used when head_loss_method='hazen-williams'.
    """
    pipe_id: str
    start_node: str
    end_node: str
    length: float
    diameter: float
    roughness: float = 0.1        # mm
    hw_c: float = 120.0


# ---------------------------------------------------------------------------
# Head-loss functions
# ---------------------------------------------------------------------------

def _hazen_williams_hf(q_m3s: float, pipe: Pipe) -> float:
    """Hazen-Williams head loss (m) for flow q_m3s (m³/s).

    Formula (SI):
        hf = 10.67 · L · Q^1.852 / (C^1.852 · D^4.87)
    Reference: Hazen-Williams (empirical, water ~15 °C).
    """
    sign = 1.0 if q_m3s >= 0 else -1.0
    q = abs(q_m3s)
    if q < _EPS:
        return 0.0
    c = pipe.hw_c
    d = pipe.diameter
    hf = 10.67 * pipe.length * (q ** 1.852) / ((c ** 1.852) * (d ** 4.87))
    return sign * hf


def _hazen_williams_dhf_dq(q_m3s: float, pipe: Pipe) -> float:
    """∂hf/∂Q for Hazen-Williams (used in Hardy-Cross correction)."""
    q = abs(q_m3s)
    if q < _EPS:
        q = _EPS
    c = pipe.hw_c
    d = pipe.diameter
    dhf = 1.852 * 10.67 * pipe.length * (q ** 0.852) / ((c ** 1.852) * (d ** 4.87))
    return dhf


def _swamee_jain_f(re: float, relative_roughness: float) -> float:
    """Swamee-Jain explicit friction-factor approximation (±3% vs. Colebrook)."""
    if re < 1.0:
        re = 1.0
    eps_d = relative_roughness
    # Turbulent regime
    if eps_d < _EPS:
        eps_d = _EPS
    f = 0.25 / (math.log10(eps_d / 3.7 + 5.74 / (re ** 0.9))) ** 2
    return f


def _colebrook_white_f(re: float, relative_roughness: float, f0: float) -> float:
    """Colebrook-White friction factor by 5 fixed-point iterations (from Swamee-Jain seed)."""
    eps_d = relative_roughness
    f = f0
    for _ in range(5):
        rhs = -2.0 * math.log10(eps_d / 3.7 + 2.51 / (re * math.sqrt(f)))
        f_new = 1.0 / (rhs ** 2) if abs(rhs) > _EPS else f
        f = f_new
    return f


def _darcy_weisbach_hf(q_m3s: float, pipe: Pipe) -> float:
    """Darcy-Weisbach head loss (m).  Friction factor by Colebrook-White."""
    sign = 1.0 if q_m3s >= 0 else -1.0
    q = abs(q_m3s)
    d = pipe.diameter
    area = math.pi * d ** 2 / 4.0
    if q < _EPS or area < _EPS:
        return 0.0
    v = q / area
    re = v * d / _WATER_NU
    eps_d = (pipe.roughness * 1e-3) / d  # roughness in metres
    if re < 2300.0:
        # Laminar
        f = 64.0 / max(re, 1.0)
    else:
        f0 = _swamee_jain_f(re, eps_d)
        f = _colebrook_white_f(re, eps_d, f0)
    hf = f * (pipe.length / d) * (v ** 2) / (2.0 * _G)
    return sign * hf


def _darcy_weisbach_dhf_dq(q_m3s: float, pipe: Pipe) -> float:
    """∂hf/∂Q for Darcy-Weisbach (numerical, centred difference 0.1 %)."""
    q = abs(q_m3s)
    dq = max(q * 1e-3, 1e-9)
    hfp = _darcy_weisbach_hf(q + dq, pipe)
    hfm = _darcy_weisbach_hf(q - dq, pipe)
    return (hfp - hfm) / (2.0 * dq)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PipeResult:
    pipe_id: str
    start_node: str
    end_node: str
    flow_m3s: float       # m³/s  (positive = start→end direction)
    velocity_ms: float    # m/s
    headloss_m: float     # m  (positive = head drops from start to end)
    diameter_m: float
    length_m: float

    def to_dict(self) -> dict:
        return {
            "pipe_id": self.pipe_id,
            "start_node": self.start_node,
            "end_node": self.end_node,
            "flow_L_per_s": round(self.flow_m3s * 1000.0, 6),
            "flow_m3_per_s": round(self.flow_m3s, 9),
            "velocity_m_per_s": round(self.velocity_ms, 4),
            "headloss_m": round(self.headloss_m, 4),
            "diameter_m": self.diameter_m,
            "length_m": self.length_m,
        }


@dataclass
class NodeResult:
    node_id: str
    elevation_m: float
    head_m: float        # hydraulic head (m above datum)
    pressure_m: float    # pressure head = head - elevation (m)
    pressure_kPa: float  # pressure_m × ρg / 1000
    demand_m3s: float
    is_fixed: bool

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "elevation_m": self.elevation_m,
            "head_m": round(self.head_m, 4),
            "pressure_head_m": round(self.pressure_m, 4),
            "pressure_kPa": round(self.pressure_kPa, 3),
            "demand_L_per_s": round(self.demand_m3s * 1000.0, 6),
            "is_fixed_head": self.is_fixed,
        }


@dataclass
class NetworkResult:
    converged: bool
    iterations: int
    max_loop_correction_m: float  # final loop head-error (m)
    nodes: list[NodeResult] = field(default_factory=list)
    pipes: list[PipeResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "converged": self.converged,
            "iterations": self.iterations,
            "max_loop_correction_m": round(self.max_loop_correction_m, 6),
            "nodes": [n.to_dict() for n in self.nodes],
            "pipes": [p.to_dict() for p in self.pipes],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Network topology helpers
# ---------------------------------------------------------------------------

def _find_loops_with_directions(
    pipes: list[Pipe],
    node_ids: set[str],
) -> list[list[tuple[str, int]]]:
    """Extract a fundamental independent loop basis using the chord (co-tree) method.

    A spanning tree of N nodes has N-1 tree edges.  Each remaining pipe (chord)
    introduces exactly one independent loop: the unique path in the spanning
    tree connecting the chord's two endpoints, plus the chord itself.

    Returns a list of loops.  Each loop is a list of (pipe_id, direction)
    tuples where:
      direction = +1  — pipe traversed in its natural start→end direction
                        within the loop orientation.
      direction = -1  — traversed end→start.

    Hardy-Cross sign convention:
      Head-loss contribution of pipe (pid, d) to the loop sum is d * hf(d*q).
      Correction: q_pid += d * ΔQ  (preserves node continuity throughout).

    The chord method guarantees independent loops with no redundancy, which
    is essential for Hardy-Cross convergence.
    """
    from collections import deque

    pipe_lookup: dict[str, Pipe] = {p.pipe_id: p for p in pipes}

    # ── Build BFS spanning tree ───────────────────────────────────────────
    # Adjacency: node → [(neighbour, pipe_id)]
    adj: dict[str, list[tuple[str, str]]] = {n: [] for n in node_ids}
    for p in pipes:
        adj[p.start_node].append((p.end_node, p.pipe_id))
        adj[p.end_node].append((p.start_node, p.pipe_id))

    root = min(node_ids)  # deterministic
    visited: set[str] = {root}
    # tree_parent[node] = pipe_id that connects node to its parent
    tree_parent: dict[str, str] = {}
    tree_pipes: set[str] = set()
    bfs_q: deque[str] = deque([root])

    while bfs_q:
        cur = bfs_q.popleft()
        for nb, pid in adj[cur]:
            if nb not in visited:
                visited.add(nb)
                tree_parent[nb] = pid
                tree_pipes.add(pid)
                bfs_q.append(nb)

    # Chord pipes (non-tree pipes)
    chord_pipes = [p for p in pipes if p.pipe_id not in tree_pipes]

    # ── For each chord, find the unique tree path ─────────────────────────
    # tree_path(u, v) returns ordered list of node ids from u to v in tree.
    def tree_ancestors(node: str) -> list[str]:
        """Return path from node to root as list of node ids."""
        path = [node]
        cur = node
        while cur != root:
            pid = tree_parent.get(cur)
            if pid is None:
                break
            p = pipe_lookup[pid]
            cur = p.start_node if p.end_node == cur else p.end_node
            path.append(cur)
        return path

    def tree_path(u: str, v: str) -> list[str]:
        """Return node sequence from u to v via the spanning tree."""
        u_ancestors = tree_ancestors(u)   # [u, ..., root]
        v_ancestors = tree_ancestors(v)   # [v, ..., root]
        u_set = {n: i for i, n in enumerate(u_ancestors)}
        v_set = {n: i for i, n in enumerate(v_ancestors)}
        # Find LCA (lowest common ancestor)
        lca = None
        for n in u_ancestors:
            if n in v_set:
                lca = n
                break
        if lca is None:
            return []
        u_to_lca = u_ancestors[:u_set[lca] + 1]
        v_to_lca = v_ancestors[:v_set[lca]]
        # path is u_to_lca + reversed(v_to_lca without lca)
        return u_to_lca + list(reversed(v_to_lca))

    loops: list[list[tuple[str, int]]] = []

    for chord in chord_pipes:
        # Loop = tree path from chord.start_node to chord.end_node + chord
        path = tree_path(chord.start_node, chord.end_node)
        if len(path) < 2:
            continue   # disconnected — skip

        loop: list[tuple[str, int]] = []
        valid = True

        # Tree edges along the path
        for i in range(len(path) - 1):
            a = path[i]
            b = path[i + 1]
            # Find the tree pipe between a and b
            tree_pid = None
            for nb, pid in adj[a]:
                if nb == b and pid in tree_pipes:
                    tree_pid = pid
                    break
            if tree_pid is None:
                # Try other direction
                for nb, pid in adj[b]:
                    if nb == a and pid in tree_pipes:
                        tree_pid = pid
                        break
            if tree_pid is None:
                valid = False
                break
            p = pipe_lookup[tree_pid]
            dirn = +1 if p.start_node == a else -1
            loop.append((tree_pid, dirn))

        if not valid:
            continue

        # Add the chord itself (goes from path[-1] to path[0], closing the loop)
        # But we define the loop orientation as start_node → ... → end_node → (chord back)
        # The chord connects chord.start_node to chord.end_node.
        # Loop orientation: path[0] (= chord.start_node) → ... → path[-1] (= chord.end_node)
        # then chord back: path[-1] → path[0].
        # Chord direction in loop: if chord.start_node == path[-1] → +1 (natural end of path → chord start)
        # Since path ends at chord.end_node, the chord closes via chord.end_node → chord.start_node,
        # which is REVERSE of the chord's natural direction (start→end).
        # Hmm: the path goes from chord.start_node to chord.end_node; closing via the chord
        # goes chord.end_node → chord.start_node, which is the -1 direction for the chord.
        # BUT we could also orient the loop the other way. Either works as long as consistent.
        # Use: chord is traversed in its natural direction (+1) to close the loop,
        # which means path[-1] (chord.end_node) arrives at chord.end_node and we go back
        # via chord (end→start = -1) to close. OR: define loop as going chord.start→end (+1),
        # and the path is from chord.start to chord.end in REVERSE direction (end→start).
        # Let's use: chord = +1 (natural start→end direction),
        # and the tree path is from chord.end to chord.start (REVERSED).

        # Re-derive with chord in +1 direction:
        # Loop orientation: chord.start_node → chord.end_node (via chord, +1)
        #                   then chord.end_node → chord.start_node (via tree path, reversed)
        # Actually let's just redo with path reversed if needed.
        # Simpler: define loop as: chord (+1) followed by reversed tree path.

        loop2: list[tuple[str, int]] = []
        # Chord goes chord.start_node → chord.end_node (+1 natural)
        loop2.append((chord.pipe_id, +1))
        # Then tree path from chord.end_node back to chord.start_node (reversed)
        path_rev = list(reversed(path))  # path_rev[0] = chord.end_node, path_rev[-1] = chord.start_node
        valid2 = True
        for i in range(len(path_rev) - 1):
            a = path_rev[i]
            b = path_rev[i + 1]
            tree_pid = None
            for nb, pid in adj[a]:
                if nb == b and pid in tree_pipes:
                    tree_pid = pid
                    break
            if tree_pid is None:
                for nb, pid in adj[b]:
                    if nb == a and pid in tree_pipes:
                        tree_pid = pid
                        break
            if tree_pid is None:
                valid2 = False
                break
            p = pipe_lookup[tree_pid]
            dirn = +1 if p.start_node == a else -1
            loop2.append((tree_pid, dirn))

        if valid2 and len(loop2) >= 3:
            loops.append(loop2)
        elif valid and len(loop) >= 3:
            # Fallback: use loop with chord as -1 at end
            loop.append((chord.pipe_id, -1))
            loops.append(loop)

    return loops


def _init_flows_spanning_tree(
    pipe_objs: list[Pipe],
    node_map: dict[str, Node],
) -> dict[str, float]:
    """Initialise pipe flows satisfying node continuity on a spanning tree.

    Strategy:
      1. Build a spanning tree rooted at any fixed-head node (BFS).
      2. Set all non-tree (chord) pipes to a small seed flow.
      3. Traverse tree leaves → root, setting each tree pipe's flow so that
         continuity (inflow = outflow + demand) is satisfied at each leaf.

    This ensures the initial flows respect mass balance at every node,
    which is a prerequisite for Hardy-Cross correctness.
    """
    from collections import deque, defaultdict

    # Identify the root (first fixed-head node, alphabetical)
    fixed = [n for n in node_map.values() if n.head_fixed is not None]
    root = min(fixed, key=lambda n: n.node_id).node_id

    # BFS to build a spanning tree
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for p in pipe_objs:
        adj[p.start_node].append((p.end_node, p.pipe_id))
        adj[p.end_node].append((p.start_node, p.pipe_id))

    tree_pipes: set[str] = set()         # pipe_ids in spanning tree
    tree_parent: dict[str, Optional[tuple[str, str]]] = {root: None}  # node → (parent_node, pipe_id)
    visited: set[str] = {root}
    queue: deque[str] = deque([root])
    bfs_order: list[str] = [root]

    while queue:
        cur = queue.popleft()
        for nb, pid in adj[cur]:
            if nb not in visited:
                visited.add(nb)
                tree_parent[nb] = (cur, pid)
                tree_pipes.add(pid)
                queue.append(nb)
                bfs_order.append(nb)

    pipe_map = {p.pipe_id: p for p in pipe_objs}

    # Seed: small positive flow for all pipes
    total_demand = sum(
        max(node_map[nid].demand / 1000.0, 0.0)
        for nid in node_map
        if node_map[nid].head_fixed is None
    )
    seed = max(total_demand / max(len(pipe_objs), 1), 1e-5)
    flows: dict[str, float] = {p.pipe_id: seed for p in pipe_objs}

    # Process tree nodes from leaves to root (reverse BFS order)
    for node_id in reversed(bfs_order):
        if node_id == root:
            continue
        info = tree_parent.get(node_id)
        if info is None:
            continue
        parent_nid, tree_pid = info

        # Net inflow to this node from all NON-TREE pipes connected to it
        inflow_non_tree = 0.0
        for nb, pid in adj[node_id]:
            if pid in tree_pipes:
                continue
            p = pipe_map[pid]
            if p.end_node == node_id:
                inflow_non_tree += flows[pid]
            else:
                inflow_non_tree -= flows[pid]

        # Also sum inflow from tree children of this node
        inflow_from_children = 0.0
        for nb, pid in adj[node_id]:
            if pid not in tree_pipes:
                continue
            # Is nb a child of node_id in the tree?
            if tree_parent.get(nb) and tree_parent[nb][0] == node_id:
                p = pipe_map[pid]
                # Child's tree pipe flows toward node_id (inflow)
                if p.end_node == node_id:
                    inflow_from_children += flows[pid]
                else:
                    inflow_from_children -= flows[pid]

        demand_m3s = node_map[node_id].demand / 1000.0
        # Set tree pipe from parent → this node to satisfy continuity
        # net_inflow = inflow_non_tree + inflow_from_children + q_tree_from_parent = demand
        q_needed = demand_m3s - inflow_non_tree - inflow_from_children

        p = pipe_map[tree_pid]
        # The tree pipe goes from parent_nid toward node_id
        if p.start_node == parent_nid:
            # Positive q = flow start→end = parent→node (inflow to node)
            flows[tree_pid] = q_needed
        else:
            # p.end_node == parent_nid → positive q = flow start→end = node→parent
            # So inflow to node from this pipe is -flows[tree_pid]
            flows[tree_pid] = -q_needed

    return flows


# ---------------------------------------------------------------------------
# Main solver: Hardy-Cross loop-correction method
# ---------------------------------------------------------------------------

def solve_pipe_network(
    nodes: list[dict],
    pipes: list[dict],
    head_loss_method: str = "hazen-williams",
    max_iterations: int = 100,
    tolerance_m: float = 1e-4,
) -> dict:
    """Solve a steady-state pressurised pipe network.

    Parameters
    ----------
    nodes : list of dicts
        Each dict: {node_id, elevation, demand [optional, default 0],
                    head_fixed [optional]}.
        demand in L/s (positive = withdrawal, negative = supply).
    pipes : list of dicts
        Each dict: {pipe_id, start_node, end_node, length, diameter,
                    roughness [mm, default 0.1], hw_c [default 120]}.
        length in m, diameter in m.
    head_loss_method : 'hazen-williams' | 'darcy-weisbach'
    max_iterations : int
        Hardy-Cross iteration cap.
    tolerance_m : float
        Convergence criterion: max |ΔQ correction| per loop < tolerance_m.
        Default 1e-4 m³/s.

    Returns
    -------
    dict with {ok, converged, iterations, nodes, pipes, warnings} or
         {ok: False, reason: str}.

    Algorithm
    ---------
    1. Validate topology (at least one fixed-head node, unique IDs, valid pipe
       references, positive dimensions).
    2. Initialise pipe flows satisfying node continuity on a BFS spanning tree.
    3. Extract independent loop basis (cycle basis via DFS back-edges).
    4. Hardy-Cross loop corrections with proper pipe direction tracking:
           ΔQ_loop = −Σ(dir·hF) / Σ|∂hF/∂Q|
       applied to each loop; each pipe's flow corrected by dir·ΔQ.
       Repeat until max |ΔQ| < tolerance or max_iter reached.
    5. Compute heads by BFS traversal from fixed-head node(s).
    6. Report per-pipe flow/velocity/headloss and per-node pressure.

    Reference: Hardy-Cross (1936), Univ. Illinois Bull. 286;
               Hazen-Williams (1905); Colebrook-White (1939).
    """
    # ── Parse & validate ──────────────────────────────────────────────────
    try:
        node_objs, pipe_objs, err = _parse_network(nodes, pipes)
    except Exception as exc:
        return {"ok": False, "reason": f"parse error: {exc}"}
    if err:
        return {"ok": False, "reason": err}

    method = head_loss_method.lower().strip()
    if method not in ("hazen-williams", "darcy-weisbach"):
        return {"ok": False, "reason": (
            "head_loss_method must be 'hazen-williams' or 'darcy-weisbach'; "
            f"got '{head_loss_method}'"
        )}

    if method == "hazen-williams":
        hf_fn = _hazen_williams_hf
        dhf_fn = _hazen_williams_dhf_dq
    else:
        hf_fn = _darcy_weisbach_hf
        dhf_fn = _darcy_weisbach_dhf_dq

    node_map: dict[str, Node] = {n.node_id: n for n in node_objs}
    pipe_map: dict[str, Pipe] = {p.pipe_id: p for p in pipe_objs}
    node_ids = set(node_map.keys())

    fixed_nodes = [n for n in node_objs if n.head_fixed is not None]
    if not fixed_nodes:
        return {"ok": False, "reason": (
            "Network has no fixed-head node (reservoir). "
            "At least one node must have head_fixed set."
        )}

    # ── Initialise flows (spanning-tree, satisfies continuity) ───────────
    flows: dict[str, float] = _init_flows_spanning_tree(pipe_objs, node_map)

    # ── Identify loops with pipe directions ──────────────────────────────
    loops = _find_loops_with_directions(pipe_objs, node_ids)

    warnings: list[str] = []
    converged = True
    iterations = 0
    max_corr = 0.0

    if loops:
        converged = False
        for it in range(max_iterations):
            max_corr = 0.0
            for loop in loops:
                # loop is list of (pipe_id, direction)
                # direction = +1: pipe traversed in its defined direction in the loop
                # direction = -1: pipe traversed against its defined direction
                # Head loss around loop (signed): Σ dir * hf(dir * q)
                sum_hf = 0.0
                sum_dhf = 0.0
                for pid, dirn in loop:
                    pipe = pipe_map[pid]
                    q = flows[pid]
                    # Signed head loss: if pipe is traversed backward in loop,
                    # flip the sign of both q and hf
                    hf = dirn * hf_fn(dirn * q, pipe)
                    dhf = dhf_fn(q, pipe)   # always positive magnitude
                    sum_hf += hf
                    sum_dhf += dhf
                if sum_dhf < _EPS:
                    continue
                delta_q = -sum_hf / sum_dhf
                for pid, dirn in loop:
                    # Correct flow; direction determines whether ΔQ adds or subtracts
                    flows[pid] += dirn * delta_q
                max_corr = max(max_corr, abs(delta_q))
            iterations = it + 1
            if max_corr < tolerance_m:
                converged = True
                break

        if not converged:
            warnings.append(
                f"Hardy-Cross did not converge after {max_iterations} iterations; "
                f"max loop correction = {max_corr:.6f} m³/s (tolerance = {tolerance_m}). "
                "Results are approximate."
            )

    # ── Compute heads by BFS from fixed-head nodes ────────────────────────
    heads: dict[str, float] = {}
    for n in fixed_nodes:
        heads[n.node_id] = n.head_fixed  # type: ignore[assignment]

    queue_h: list[str] = [n.node_id for n in fixed_nodes]
    visited_h: set[str] = set(queue_h)
    while queue_h:
        current = queue_h.pop(0)
        for pipe in pipe_objs:
            if pipe.start_node == current and pipe.end_node not in visited_h:
                q = flows[pipe.pipe_id]
                hf = hf_fn(q, pipe)
                heads[pipe.end_node] = heads[current] - hf
                visited_h.add(pipe.end_node)
                queue_h.append(pipe.end_node)
            elif pipe.end_node == current and pipe.start_node not in visited_h:
                q = flows[pipe.pipe_id]
                hf = hf_fn(q, pipe)
                heads[pipe.start_node] = heads[current] + hf
                visited_h.add(pipe.start_node)
                queue_h.append(pipe.start_node)

    for nid in node_ids:
        if nid not in heads:
            heads[nid] = 0.0
            warnings.append(
                f"Node '{nid}' head could not be computed (disconnected?); set to 0."
            )

    # ── Assemble results ──────────────────────────────────────────────────
    node_results: list[NodeResult] = []
    for n in node_objs:
        h = heads[n.node_id]
        p_m = h - n.elevation
        node_results.append(NodeResult(
            node_id=n.node_id,
            elevation_m=n.elevation,
            head_m=h,
            pressure_m=p_m,
            pressure_kPa=p_m * _WATER_RHO * _G / 1000.0,
            demand_m3s=n.demand / 1000.0,
            is_fixed=(n.head_fixed is not None),
        ))

    pipe_results: list[PipeResult] = []
    for p in pipe_objs:
        q = flows[p.pipe_id]
        area = math.pi * p.diameter ** 2 / 4.0
        v = abs(q) / area if area > _EPS else 0.0
        hf = hf_fn(q, p)
        pipe_results.append(PipeResult(
            pipe_id=p.pipe_id,
            start_node=p.start_node,
            end_node=p.end_node,
            flow_m3s=q,
            velocity_ms=v,
            headloss_m=hf,
            diameter_m=p.diameter,
            length_m=p.length,
        ))

    result = NetworkResult(
        converged=converged,
        iterations=iterations,
        max_loop_correction_m=max_corr,
        nodes=node_results,
        pipes=pipe_results,
        warnings=warnings,
    )
    out = result.to_dict()
    out["ok"] = True
    return out


def _pipe_direction(pipe: Pipe, node_id: str) -> int:
    """Return +1 if node is downstream, -1 if upstream, 0 if not connected."""
    if pipe.end_node == node_id:
        return 1
    if pipe.start_node == node_id:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

def _parse_network(
    raw_nodes: list[dict],
    raw_pipes: list[dict],
) -> tuple[list[Node], list[Pipe], Optional[str]]:
    """Parse and validate raw dicts into Node/Pipe objects.

    Returns (nodes, pipes, error_string_or_None).
    """
    if not isinstance(raw_nodes, list) or len(raw_nodes) < 2:
        return [], [], "nodes must be a list with at least 2 entries"
    if not isinstance(raw_pipes, list) or len(raw_pipes) < 1:
        return [], [], "pipes must be a list with at least 1 entry"

    nodes: list[Node] = []
    seen_nids: set[str] = set()
    for i, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            return [], [], f"nodes[{i}] must be an object"
        nid = str(raw.get("node_id", "")).strip()
        if not nid:
            return [], [], f"nodes[{i}] missing 'node_id'"
        if nid in seen_nids:
            return [], [], f"duplicate node_id '{nid}'"
        seen_nids.add(nid)
        try:
            elev = float(raw.get("elevation", 0.0))
            demand = float(raw.get("demand", 0.0))   # L/s
        except (TypeError, ValueError) as exc:
            return [], [], f"nodes[{i}] numeric parse error: {exc}"
        hf_raw = raw.get("head_fixed")
        head_fixed: Optional[float] = None
        if hf_raw is not None:
            try:
                head_fixed = float(hf_raw)
            except (TypeError, ValueError) as exc:
                return [], [], f"nodes[{i}] head_fixed parse error: {exc}"
        nodes.append(Node(
            node_id=nid,
            elevation=elev,
            demand=demand,
            head_fixed=head_fixed,
        ))

    pipes: list[Pipe] = []
    seen_pids: set[str] = set()
    for i, raw in enumerate(raw_pipes):
        if not isinstance(raw, dict):
            return [], [], f"pipes[{i}] must be an object"
        pid = str(raw.get("pipe_id", "")).strip()
        if not pid:
            return [], [], f"pipes[{i}] missing 'pipe_id'"
        if pid in seen_pids:
            return [], [], f"duplicate pipe_id '{pid}'"
        seen_pids.add(pid)
        sn = str(raw.get("start_node", "")).strip()
        en = str(raw.get("end_node", "")).strip()
        if sn not in seen_nids:
            return [], [], f"pipes[{i}] start_node '{sn}' not in nodes"
        if en not in seen_nids:
            return [], [], f"pipes[{i}] end_node '{en}' not in nodes"
        if sn == en:
            return [], [], f"pipes[{i}] start_node == end_node (self-loop) '{sn}'"
        try:
            length = float(raw.get("length", 0))
            diameter = float(raw.get("diameter", 0))
        except (TypeError, ValueError) as exc:
            return [], [], f"pipes[{i}] numeric parse error: {exc}"
        if length <= 0:
            return [], [], f"pipes[{i}] length must be > 0; got {length}"
        if diameter <= 0:
            return [], [], f"pipes[{i}] diameter must be > 0; got {diameter}"
        roughness = float(raw.get("roughness", 0.1))
        hw_c = float(raw.get("hw_c", 120.0))
        pipes.append(Pipe(
            pipe_id=pid,
            start_node=sn,
            end_node=en,
            length=length,
            diameter=diameter,
            roughness=roughness,
            hw_c=hw_c,
        ))

    return nodes, pipes, None


# ---------------------------------------------------------------------------
# Manning's open-channel single-reach helper
# ---------------------------------------------------------------------------

@dataclass
class ManningResult:
    """Results from Manning normal-depth calculation (rectangular channel)."""
    ok: bool
    normal_depth_m: float = 0.0
    velocity_ms: float = 0.0
    flow_area_m2: float = 0.0
    wetted_perimeter_m: float = 0.0
    hydraulic_radius_m: float = 0.0
    froude_number: float = 0.0
    flow_regime: str = ""   # 'subcritical' | 'critical' | 'supercritical'
    channel_full: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "ok": self.ok,
        }
        if not self.ok:
            d["reason"] = self.reason
            return d
        d.update({
            "normal_depth_m": round(self.normal_depth_m, 6),
            "velocity_m_per_s": round(self.velocity_ms, 4),
            "flow_area_m2": round(self.flow_area_m2, 6),
            "wetted_perimeter_m": round(self.wetted_perimeter_m, 6),
            "hydraulic_radius_m": round(self.hydraulic_radius_m, 6),
            "froude_number": round(self.froude_number, 4),
            "flow_regime": self.flow_regime,
            "channel_full": self.channel_full,
        })
        return d


def manning_normal_depth(
    flow_m3s: float,
    width_m: float,
    slope: float,
    manning_n: float,
    max_depth_m: float = 10.0,
) -> dict:
    """Compute normal depth for a rectangular channel using Manning's equation.

    Manning's equation (SI):
        Q = (1/n) · A · R^(2/3) · S^(1/2)
    where
        A = width × depth              (flow area, m²)
        P = width + 2 × depth          (wetted perimeter, m)
        R = A / P                      (hydraulic radius, m)
        S = longitudinal slope (m/m, > 0)
        n = Manning's roughness coefficient

    Normal depth is solved by bisection on  f(y) = Q_manning(y) − Q_given = 0.

    Parameters
    ----------
    flow_m3s : float  Target flow rate (m³/s), > 0.
    width_m  : float  Channel width (m), > 0.
    slope    : float  Longitudinal slope (m/m), > 0.
    manning_n: float  Manning's n (dimensionless), > 0.  Typical: 0.013 concrete,
                      0.025 earth, 0.015 clay sewer.
    max_depth_m: float  Search upper bound for depth bisection (m).

    Returns
    -------
    dict {ok, normal_depth_m, velocity_m_per_s, flow_area_m2,
          wetted_perimeter_m, hydraulic_radius_m, froude_number,
          flow_regime, channel_full}
    or   {ok: False, reason: str}.

    Reference: Manning (1891); Chow (1959) "Open-Channel Hydraulics".
    """
    # ── Validate ──────────────────────────────────────────────────────────
    if not isinstance(flow_m3s, (int, float)) or flow_m3s <= 0:
        return ManningResult(ok=False, reason="flow_m3s must be > 0").to_dict()
    if not isinstance(width_m, (int, float)) or width_m <= 0:
        return ManningResult(ok=False, reason="width_m must be > 0").to_dict()
    if not isinstance(slope, (int, float)) or slope <= 0:
        return ManningResult(ok=False, reason="slope must be > 0 (m/m)").to_dict()
    if not isinstance(manning_n, (int, float)) or manning_n <= 0:
        return ManningResult(ok=False, reason="manning_n must be > 0").to_dict()
    if max_depth_m <= 0:
        return ManningResult(ok=False, reason="max_depth_m must be > 0").to_dict()

    sq_s = math.sqrt(slope)

    def q_manning(y: float) -> float:
        """Flow at depth y (rectangular cross-section)."""
        if y <= 0:
            return 0.0
        a = width_m * y
        p = width_m + 2.0 * y
        r = a / p
        return (1.0 / manning_n) * a * (r ** (2.0 / 3.0)) * sq_s

    # Check whether max_depth covers the target flow
    q_max = q_manning(max_depth_m)
    channel_full = False
    if q_max < flow_m3s:
        # Extend search or flag channel-full
        channel_full = True
        # Still report at max_depth with a warning embedded in flow_regime
        y_n = max_depth_m
    else:
        # Bisection
        lo, hi = _EPS, max_depth_m
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if q_manning(mid) < flow_m3s:
                lo = mid
            else:
                hi = mid
        y_n = (lo + hi) / 2.0

    a = width_m * y_n
    p = width_m + 2.0 * y_n
    r = a / p if p > _EPS else 0.0
    v = flow_m3s / a if a > _EPS else 0.0
    # Froude number for rectangular channel: Fr = V / sqrt(g × y_n)
    fr = v / math.sqrt(_G * y_n) if y_n > _EPS else 0.0

    if fr < 0.98:
        regime = "subcritical"
    elif fr > 1.02:
        regime = "supercritical"
    else:
        regime = "critical"

    if channel_full:
        regime = "channel_full (flow exceeds capacity at max_depth)"

    return ManningResult(
        ok=True,
        normal_depth_m=y_n,
        velocity_ms=v,
        flow_area_m2=a,
        wetted_perimeter_m=p,
        hydraulic_radius_m=r,
        froude_number=fr,
        flow_regime=regime,
        channel_full=channel_full,
    ).to_dict()
