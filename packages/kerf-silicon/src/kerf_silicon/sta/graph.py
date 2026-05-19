"""graph.py — Timing graph construction and topological sort.

The timing graph is a DAG where:
* Nodes represent signal pins (instance/port + pin name).
* Directed edges carry a propagation delay (ns) derived from Liberty LUTs.

Nodes are typed:
* ``INPUT_PORT``   — primary input (feeds the design from outside)
* ``OUTPUT_PORT``  — primary output (fan-out endpoint)
* ``CELL_IN``      — input pin of a cell instance
* ``CELL_OUT``     — output pin of a cell instance

An edge connects the driver (CELL_OUT or INPUT_PORT) of a net to every
load (CELL_IN or OUTPUT_PORT) on the same net.  A second edge set is the
pin-internal arc: CELL_IN → CELL_OUT with the cell propagation delay.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from kerf_silicon.liberty.ast import Cell as LibertyCell, LibertyLibrary, LUTable


# ---------------------------------------------------------------------------
# Node / Edge types
# ---------------------------------------------------------------------------


class NodeKind(Enum):
    INPUT_PORT = auto()
    OUTPUT_PORT = auto()
    CELL_IN = auto()
    CELL_OUT = auto()


@dataclass
class TimingNode:
    """A node in the timing graph."""
    id: str                     # unique node identifier, e.g. "u1/A" or "clk"
    kind: NodeKind
    instance: str = ""          # cell instance name (empty for ports)
    pin: str = ""               # pin name within the cell
    arrival: float = 0.0        # forward arrival time (ns) — filled by propagate
    required: float = float("inf")  # backward required time (ns) — filled by propagate
    slack: float = float("inf")     # required - arrival

    @property
    def is_endpoint(self) -> bool:
        return self.kind in (NodeKind.OUTPUT_PORT, NodeKind.CELL_IN)

    @property
    def is_startpoint(self) -> bool:
        return self.kind in (NodeKind.INPUT_PORT, NodeKind.CELL_OUT)


@dataclass
class TimingEdge:
    """A directed edge in the timing graph."""
    src: str        # source node id
    dst: str        # destination node id
    delay: float = 0.0   # propagation delay on this edge (ns)
    is_false: bool = False  # True when flagged by set_false_path


# ---------------------------------------------------------------------------
# Timing graph
# ---------------------------------------------------------------------------


class TimingGraph:
    """Directed acyclic timing graph built from a netlist + Liberty library.

    Parameters
    ----------
    netlist : dict
        Gate-level netlist in the T-234 JSON format::

            {
              "module": "top",
              "ports": {
                "clk":   {"direction": "input"},
                "in_a":  {"direction": "input"},
                "out_z": {"direction": "output"}
              },
              "instances": {
                "u1": {"cell": "sky130_fd_sc_hd__inv_1",
                       "connections": {"A": "in_a", "Y": "net1"}},
                "u2": {"cell": "sky130_fd_sc_hd__inv_1",
                       "connections": {"A": "net1", "Y": "out_z"}}
              }
            }

    liberty : LibertyLibrary
        Parsed Liberty library (from T-241).

    transition_ns : float
        Default input transition time for NLDM LUT interpolation (ns).

    load_cap_pf : float
        Default output load capacitance for NLDM LUT interpolation (pF).
    """

    def __init__(
        self,
        netlist: dict,
        liberty: LibertyLibrary,
        transition_ns: float = 0.05,
        load_cap_pf: float = 0.005,
    ) -> None:
        self._netlist = netlist
        self._liberty = liberty
        self._transition_ns = transition_ns
        self._load_cap_pf = load_cap_pf

        # id → node
        self.nodes: Dict[str, TimingNode] = {}
        # src → list of edges
        self._out_edges: Dict[str, List[TimingEdge]] = {}
        # dst → list of edges (reverse, for backward propagation)
        self._in_edges: Dict[str, List[TimingEdge]] = {}
        # all edges in insertion order
        self.edges: List[TimingEdge] = []

        # Build indexed Liberty cell map
        self._lib_cells: Dict[str, LibertyCell] = {
            c.name: c for c in liberty.cells
        }

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _add_node(self, node: TimingNode) -> None:
        self.nodes[node.id] = node
        self._out_edges.setdefault(node.id, [])
        self._in_edges.setdefault(node.id, [])

    def _add_edge(self, edge: TimingEdge) -> None:
        self.edges.append(edge)
        self._out_edges.setdefault(edge.src, []).append(edge)
        self._in_edges.setdefault(edge.dst, []).append(edge)

    def _build(self) -> None:
        ports = self._netlist.get("ports", {})
        instances = self._netlist.get("instances", {})

        # 1. Create port nodes
        for pname, pinfo in ports.items():
            direction = pinfo.get("direction", "input")
            kind = NodeKind.INPUT_PORT if direction == "input" else NodeKind.OUTPUT_PORT
            self._add_node(TimingNode(id=pname, kind=kind, pin=pname))

        # 2. Create instance pin nodes and internal cell arcs
        for inst_name, inst_info in instances.items():
            cell_name = inst_info.get("cell", "")
            connections = inst_info.get("connections", {})
            lib_cell = self._lib_cells.get(cell_name)

            # Create CELL_IN nodes for input pins
            for pin_name, net_name in connections.items():
                direction = self._pin_direction(lib_cell, pin_name)
                if direction == "input":
                    nid = f"{inst_name}/{pin_name}"
                    self._add_node(TimingNode(
                        id=nid, kind=NodeKind.CELL_IN,
                        instance=inst_name, pin=pin_name,
                    ))
                elif direction == "output":
                    nid = f"{inst_name}/{pin_name}"
                    self._add_node(TimingNode(
                        id=nid, kind=NodeKind.CELL_OUT,
                        instance=inst_name, pin=pin_name,
                    ))

            # Internal cell arcs: CELL_IN → CELL_OUT
            if lib_cell:
                for out_pin in lib_cell.pins:
                    if out_pin.direction != "output":
                        continue
                    out_nid = f"{inst_name}/{out_pin.name}"
                    for arc in out_pin.timing_arcs:
                        if not arc.related_pin:
                            continue
                        in_nid = f"{inst_name}/{arc.related_pin}"
                        if in_nid not in self.nodes or out_nid not in self.nodes:
                            continue
                        delay = self._lut_delay(arc)
                        self._add_edge(TimingEdge(
                            src=in_nid, dst=out_nid, delay=delay
                        ))
            else:
                # Unknown cell — create zero-delay arcs for all in→out combos
                in_pins = [
                    p for p, n in connections.items()
                    if self._pin_direction(None, p) != "output"
                ]
                out_pins = [
                    p for p, n in connections.items()
                    if self._pin_direction(None, p) == "output"
                ]
                # Heuristic: outputs end with Y/Z/Q, inputs are everything else
                in_nodes = [f"{inst_name}/{p}" for p in connections
                            if not p.startswith(("Y", "Z", "Q"))
                            and f"{inst_name}/{p}" in self.nodes
                            and self.nodes[f"{inst_name}/{p}"].kind == NodeKind.CELL_IN]
                out_nodes = [f"{inst_name}/{p}" for p in connections
                             if f"{inst_name}/{p}" in self.nodes
                             and self.nodes[f"{inst_name}/{p}"].kind == NodeKind.CELL_OUT]
                for i in in_nodes:
                    for o in out_nodes:
                        self._add_edge(TimingEdge(src=i, dst=o, delay=0.0))

        # 3. Net edges: driver → loads
        #    driver = INPUT_PORT or CELL_OUT driving net_name
        #    loads  = CELL_IN or OUTPUT_PORT driven by net_name
        net_drivers: Dict[str, str] = {}   # net_name → driver node id
        net_loads: Dict[str, List[str]] = {}  # net_name → [load node ids]

        # Ports drive/receive nets with their own name
        for pname, pinfo in ports.items():
            direction = pinfo.get("direction", "input")
            if direction == "input":
                net_drivers[pname] = pname
            else:
                net_loads.setdefault(pname, []).append(pname)

        for inst_name, inst_info in instances.items():
            cell_name = inst_info.get("cell", "")
            lib_cell = self._lib_cells.get(cell_name)
            connections = inst_info.get("connections", {})
            for pin_name, net_name in connections.items():
                direction = self._pin_direction(lib_cell, pin_name)
                nid = f"{inst_name}/{pin_name}"
                if nid not in self.nodes:
                    continue
                if direction == "output":
                    net_drivers[net_name] = nid
                else:
                    net_loads.setdefault(net_name, []).append(nid)

        # Create net edges (zero wire delay in v1; SPEF would add RC)
        for net_name, driver_id in net_drivers.items():
            for load_id in net_loads.get(net_name, []):
                self._add_edge(TimingEdge(src=driver_id, dst=load_id, delay=0.0))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pin_direction(
        lib_cell: Optional[LibertyCell], pin_name: str
    ) -> str:
        """Return 'input' or 'output' for *pin_name* in *lib_cell*.

        Falls back to a heuristic when the cell is not in the library.
        """
        if lib_cell is not None:
            for p in lib_cell.pins:
                if p.name == pin_name:
                    return p.direction or "input"
        # Heuristic: Y / Z / Q prefix → output
        if pin_name.startswith(("Y", "Z", "Q")):
            return "output"
        return "input"

    def _lut_delay(self, arc) -> float:
        """Interpolate cell delay from a TimingArc's NLDM LUT.

        Uses ``cell_rise`` if available, else ``cell_fall``, else 0.
        The LUT is indexed by (input_transition, output_capacitance).
        Uses the Liberty template from the library to get index axes.
        """
        lut: Optional[LUTable] = arc.cell_rise or arc.cell_fall
        if lut is None:
            return 0.0

        # Get index axes from the matching lu_table_template
        tmpl = None
        for t in self._liberty.lu_table_templates:
            if t.name == lut.template:
                tmpl = t
                break

        if tmpl is not None and tmpl.index_1 and tmpl.index_2:
            idx1 = tmpl.index_1  # input_transition axis
            idx2 = tmpl.index_2  # output_cap axis
            nrows = len(idx1)
            ncols = len(idx2)
        else:
            # Guess a square layout if no template
            n = int(len(lut.values) ** 0.5 + 0.5)
            nrows = n
            ncols = n
            # Default axes: evenly-spaced 0..1
            idx1 = [i / max(n - 1, 1) for i in range(n)]
            idx2 = [i / max(n - 1, 1) for i in range(n)]

        return _nldm_interp(
            lut.values, idx1, idx2, nrows, ncols,
            self._transition_ns, self._load_cap_pf
        )

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def topological_order(self) -> List[str]:
        """Return a list of node IDs in topological order (Kahn's algorithm).

        Raises ValueError if a cycle is detected (not expected in a valid
        combinational netlist; register feedback paths should be cut at FF
        boundaries in v1).
        """
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        for edge in self.edges:
            if edge.dst in in_degree:
                in_degree[edge.dst] += 1

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        order: List[str] = []

        while queue:
            nid = queue.popleft()
            order.append(nid)
            for edge in self._out_edges.get(nid, []):
                dst = edge.dst
                in_degree[dst] -= 1
                if in_degree[dst] == 0:
                    queue.append(dst)

        if len(order) != len(self.nodes):
            raise ValueError(
                "Timing graph contains a cycle — cannot perform topological sort. "
                f"Processed {len(order)}/{len(self.nodes)} nodes."
            )
        return order

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def successors(self, node_id: str) -> List[TimingEdge]:
        return self._out_edges.get(node_id, [])

    def predecessors(self, node_id: str) -> List[TimingEdge]:
        return self._in_edges.get(node_id, [])

    def endpoints(self) -> List[str]:
        """Return all endpoint node IDs (OUTPUT_PORT and CELL_IN of registers).

        In v1 all CELL_IN nodes are considered endpoints (no FF identification).
        For a cleaner report, callers filter to OUTPUT_PORT for primary outputs.
        """
        return [
            nid for nid, n in self.nodes.items()
            if n.kind in (NodeKind.OUTPUT_PORT,)
        ]

    def startpoints(self) -> List[str]:
        return [
            nid for nid, n in self.nodes.items()
            if n.kind == NodeKind.INPUT_PORT
        ]


# ---------------------------------------------------------------------------
# NLDM LUT bilinear interpolation
# ---------------------------------------------------------------------------


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _interp_1d(axis: List[float], idx: float) -> Tuple[int, int, float]:
    """Find the two surrounding indices in *axis* for value *idx*.

    Returns ``(i_lo, i_hi, frac)`` where ``frac`` is the linear fraction
    between ``axis[i_lo]`` and ``axis[i_hi]``.
    """
    n = len(axis)
    if n == 1:
        return 0, 0, 0.0
    if idx <= axis[0]:
        return 0, 0, 0.0
    if idx >= axis[-1]:
        return n - 1, n - 1, 0.0
    for i in range(n - 1):
        if axis[i] <= idx <= axis[i + 1]:
            span = axis[i + 1] - axis[i]
            frac = (idx - axis[i]) / span if span > 0 else 0.0
            return i, i + 1, frac
    return n - 2, n - 1, 1.0


def _nldm_interp(
    values: List[float],
    idx1: List[float],
    idx2: List[float],
    nrows: int,
    ncols: int,
    trans: float,
    cap: float,
) -> float:
    """Bilinear interpolation into an NLDM lookup table.

    The table is stored row-major: ``values[r * ncols + c]``.

    Parameters
    ----------
    values : flat list of floats (length nrows*ncols)
    idx1   : axis for rows (input transition)
    idx2   : axis for cols (output capacitance)
    nrows, ncols : table dimensions
    trans  : query input transition (ns)
    cap    : query output capacitance (pF)
    """
    if not values:
        return 0.0

    # Clamp to actual table bounds
    r0, r1, rf = _interp_1d(idx1[:nrows], trans)
    c0, c1, cf = _interp_1d(idx2[:ncols], cap)

    def v(r: int, c: int) -> float:
        idx = r * ncols + c
        if idx < len(values):
            return values[idx]
        return values[-1]

    # Bilinear interpolation
    v00 = v(r0, c0)
    v01 = v(r0, c1)
    v10 = v(r1, c0)
    v11 = v(r1, c1)

    interp_r0 = v00 + cf * (v01 - v00)
    interp_r1 = v10 + cf * (v11 - v10)
    return interp_r0 + rf * (interp_r1 - interp_r0)
