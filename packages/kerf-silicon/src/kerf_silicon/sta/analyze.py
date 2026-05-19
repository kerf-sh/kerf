"""analyze.py — Forward arrival + backward required propagation, slack computation.

Algorithm
---------
1. Build a TimingGraph from the netlist + Liberty library.
2. Apply SDC ``create_clock`` to derive the clock period.
3. Apply ``set_input_delay`` to set arrival times at input ports.
4. Apply ``set_false_path`` / ``set_max_delay`` to mark/override edges.
5. Forward propagation (topological order): arrival = max(predecessor arrival + edge delay).
6. Set required times at output ports from clock period and ``set_output_delay``.
7. Backward propagation (reverse topological order): required = min(successor required - edge delay).
8. Slack = required - arrival (positive = timing met; negative = violation).
9. Collect worst-N paths by tracing back from the most-critical endpoints.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from kerf_silicon.liberty.ast import LibertyLibrary
from kerf_silicon.sta.graph import NodeKind, TimingEdge, TimingGraph
from kerf_silicon.sta.sdc_reader import SDCConstraints


# ---------------------------------------------------------------------------
# Report data classes
# ---------------------------------------------------------------------------


@dataclass
class PathSegment:
    """One hop in a timing path."""
    node_id: str
    arrival: float   # cumulative arrival at this node


@dataclass
class PathReport:
    """A single timing path from a startpoint to an endpoint."""
    startpoint: str
    endpoint: str
    arrival: float       # arrival time at endpoint (ns)
    required: float      # required time at endpoint (ns)
    slack: float         # required - arrival
    segments: List[PathSegment] = field(default_factory=list)

    @property
    def is_violated(self) -> bool:
        return self.slack < 0.0


@dataclass
class STAReport:
    """Full STA report for a single analysis run."""
    clock_period_ns: float
    worst_paths: List[PathReport] = field(default_factory=list)
    # worst slack at each endpoint (keyed by node id)
    endpoint_slack: Dict[str, float] = field(default_factory=dict)
    setup_violations: List[PathReport] = field(default_factory=list)

    @property
    def worst_slack(self) -> float:
        if not self.endpoint_slack:
            return float("inf")
        return min(self.endpoint_slack.values())

    @property
    def has_violations(self) -> bool:
        return bool(self.setup_violations)


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------


def analyze(
    netlist: dict,
    liberty: LibertyLibrary,
    constraints: Optional[SDCConstraints] = None,
    worst_n: int = 10,
    transition_ns: float = 0.05,
    load_cap_pf: float = 0.005,
) -> STAReport:
    """Run static timing analysis on *netlist* with *liberty* and *constraints*.

    Parameters
    ----------
    netlist : dict
        Gate-level netlist (T-234 JSON format).
    liberty : LibertyLibrary
        Parsed Liberty library (T-241).
    constraints : SDCConstraints, optional
        Parsed SDC constraints.  If None, a default 10 ns clock is assumed.
    worst_n : int
        Number of worst paths to include in the report.
    transition_ns : float
        Default input transition time for NLDM interpolation.
    load_cap_pf : float
        Default output load capacitance for NLDM interpolation.

    Returns
    -------
    STAReport
    """
    if constraints is None:
        constraints = SDCConstraints()

    # Determine clock period
    clock_period_ns = 10.0  # default 100 MHz
    if constraints.clocks:
        clock_period_ns = constraints.clocks[0].period_ns

    # Build timing graph
    graph = TimingGraph(
        netlist, liberty,
        transition_ns=transition_ns,
        load_cap_pf=load_cap_pf,
    )

    # Mark false paths
    false_path_set: set[Tuple[str, str]] = set()
    for fp in constraints.false_paths:
        false_path_set.add((fp.from_, fp.to))

    for edge in graph.edges:
        src_node = graph.nodes.get(edge.src)
        dst_node = graph.nodes.get(edge.dst)
        if src_node and dst_node:
            for fp_from, fp_to in false_path_set:
                if (not fp_from or fp_from in edge.src) and (
                    not fp_to or fp_to in edge.dst
                ):
                    edge.is_false = True

    # Topological order
    topo_order = graph.topological_order()

    # ----------------------------------------------------------------
    # Forward propagation — arrival times
    # ----------------------------------------------------------------

    # Initialise all arrivals to 0
    for node in graph.nodes.values():
        node.arrival = 0.0

    # Apply set_input_delay
    input_delay_map: Dict[str, float] = {}
    for id_entry in constraints.input_delays:
        for port in id_entry.ports:
            input_delay_map[port] = id_entry.delay_ns

    for nid in topo_order:
        node = graph.nodes[nid]

        if node.kind == NodeKind.INPUT_PORT:
            node.arrival = input_delay_map.get(nid, 0.0)
            continue

        # arrival = max over all non-false incoming edges of (pred.arrival + edge.delay)
        max_arr = 0.0
        for edge in graph.predecessors(nid):
            if edge.is_false:
                continue
            src_node = graph.nodes.get(edge.src)
            if src_node is None:
                continue
            candidate = src_node.arrival + edge.delay
            if candidate > max_arr:
                max_arr = candidate
        node.arrival = max_arr

    # ----------------------------------------------------------------
    # Set required times at endpoints
    # ----------------------------------------------------------------

    # Apply set_output_delay
    output_delay_map: Dict[str, float] = {}
    for od_entry in constraints.output_delays:
        for port in od_entry.ports:
            output_delay_map[port] = od_entry.delay_ns

    # Apply set_max_delay overrides (keyed by (from, to))
    max_delay_map: Dict[Tuple[str, str], float] = {}
    for md in constraints.max_delays:
        max_delay_map[(md.from_, md.to)] = md.delay_ns

    for nid, node in graph.nodes.items():
        if node.kind == NodeKind.OUTPUT_PORT:
            od = output_delay_map.get(nid, 0.0)
            # required = clock_period - output_delay
            node.required = clock_period_ns - od
        else:
            node.required = float("inf")

    # ----------------------------------------------------------------
    # Backward propagation — required times
    # ----------------------------------------------------------------

    for nid in reversed(topo_order):
        node = graph.nodes[nid]

        if node.kind == NodeKind.OUTPUT_PORT:
            # already set above
            pass
        else:
            # required = min over all non-false outgoing edges of (succ.required - edge.delay)
            min_req = float("inf")
            for edge in graph.successors(nid):
                if edge.is_false:
                    continue
                dst_node = graph.nodes.get(edge.dst)
                if dst_node is None:
                    continue
                candidate = dst_node.required - edge.delay
                if candidate < min_req:
                    min_req = candidate
            if min_req < float("inf"):
                node.required = min_req

    # ----------------------------------------------------------------
    # Compute slack
    # ----------------------------------------------------------------

    for node in graph.nodes.values():
        if node.required == float("inf"):
            node.slack = float("inf")
        else:
            node.slack = node.required - node.arrival

    # ----------------------------------------------------------------
    # Collect endpoint slacks
    # ----------------------------------------------------------------

    endpoint_slack: Dict[str, float] = {}
    for nid in graph.endpoints():
        node = graph.nodes[nid]
        endpoint_slack[nid] = node.slack

    # ----------------------------------------------------------------
    # Trace worst-N paths
    # ----------------------------------------------------------------

    # Sort endpoints by slack (most critical first)
    sorted_endpoints = sorted(
        endpoint_slack.items(), key=lambda kv: kv[1]
    )

    worst_paths: List[PathReport] = []
    for ep_id, ep_slack in sorted_endpoints[:worst_n]:
        path = _trace_path(graph, ep_id)
        if path:
            worst_paths.append(path)

    setup_violations = [p for p in worst_paths if p.is_violated]

    report = STAReport(
        clock_period_ns=clock_period_ns,
        worst_paths=worst_paths,
        endpoint_slack=endpoint_slack,
        setup_violations=setup_violations,
    )
    return report


# ---------------------------------------------------------------------------
# Path tracing — backward greedy from endpoint
# ---------------------------------------------------------------------------


def _trace_path(graph: TimingGraph, endpoint_id: str) -> Optional[PathReport]:
    """Trace the critical (highest-arrival) path from a startpoint to *endpoint_id*.

    Performs a greedy backward walk: at each node pick the predecessor with
    the highest arrival time, following the critical path.
    """
    ep_node = graph.nodes.get(endpoint_id)
    if ep_node is None:
        return None

    segments: List[PathSegment] = []
    current_id = endpoint_id

    visited: set[str] = set()
    while True:
        if current_id in visited:
            break  # cycle guard
        visited.add(current_id)
        node = graph.nodes.get(current_id)
        if node is None:
            break
        segments.append(PathSegment(node_id=current_id, arrival=node.arrival))

        # Find the non-false predecessor with the highest arrival contribution
        best_pred_id: Optional[str] = None
        best_arrival = -math.inf
        for edge in graph.predecessors(current_id):
            if edge.is_false:
                continue
            src_node = graph.nodes.get(edge.src)
            if src_node is None:
                continue
            candidate = src_node.arrival + edge.delay
            if candidate > best_arrival:
                best_arrival = candidate
                best_pred_id = edge.src

        if best_pred_id is None:
            break  # reached a startpoint
        current_id = best_pred_id

    segments.reverse()
    if not segments:
        return None

    startpoint = segments[0].node_id

    return PathReport(
        startpoint=startpoint,
        endpoint=endpoint_id,
        arrival=ep_node.arrival,
        required=ep_node.required,
        slack=ep_node.slack,
        segments=segments,
    )
