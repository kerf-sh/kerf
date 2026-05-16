"""
Schematic capture — data model + tool API for the Kerf electronics schematic editor.

This module provides the backend model and operations that the chat agent and
frontend editor both use.  It is pure Python (stdlib only) and follows the
kerf never-raise contract: all public functions return a plain dict; errors
are indicated by ``{"ok": False, "reason": "..."}`` rather than raising.

Data model
----------
Symbol     — a placed component instance (lib_ref, designator R1/U1/…, value,
             pin map, position).
Wire       — a list of (x, y) endpoint-pairs forming orthogonal wire segments.
Junction   — explicit solder dot at a 3-or-more-way wire intersection.
Label      — a net label (global) or hierarchical port label attached to a wire.
Sheet      — one schematic page; contains symbols, wires, junctions, labels,
             buses and sub-sheet references.
Bus        — a named net bundle grouping a set of net names.
Schematic  — the top-level container: ``sheets`` dict (id→Sheet) plus
             ``active_sheet`` id.

Operations
----------
place_symbol(lib_ref, designator, value, position)
    → dict  Place a new symbol on the active sheet.

connect_wires(points)
    → dict  Append a wire path (list of [x,y] pairs) to the active sheet.

auto_connect(pin_a, pin_b)
    → dict  Route a 1-bend orthogonal wire between two pin coordinates.

add_junction(at)
    → dict  Place a junction dot at (x, y).

add_label(at, net_name)
    → dict  Attach a global net label at (x, y).

hierarchical_port(sheet, port_name, direction)
    → dict  Declare a hierarchical sheet-pin on the given sheet.

build_netlist(schematic)
    → dict  Trace connectivity and return a JSON netlist + KiCad-classic
            netlist string.

validate_erc(schematic)
    → dict  Electrical Rules Check: unconnected pins, conflicting drivers,
            net name collisions, dangling wires.

load_kicad_sch(text)
    → dict  Parse a minimal KiCad v6+ S-expression schematic.

save_kicad_sch(schematic, sheet_id)
    → dict  Serialise one sheet as a KiCad v6 S-expression schematic.

KiCad S-expression format
--------------------------
KiCad 6+ uses a Lisp-like S-expression (.kicad_sch).  This module handles
a *minimal* subset sufficient for a 2-resistor test schematic: ``(kicad_sch
…)``, ``(lib_symbols …)``, ``(symbol …)``, ``(wire …)``, ``(junction …)``,
``(net_tie_pad_groups …)`` and ``(label …)``.  Round-trip fidelity is limited
to the elements this module creates; unknown tokens are preserved verbatim in
the ``raw_extra`` field of the returned Sheet.

Author: imranparuk
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Internal sentinel / helpers
# ──────────────────────────────────────────────────────────────────────────────

Point = tuple[float, float]   # (x, y) in mm (KiCad grid units)


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _ok(**kw) -> dict:
    return {"ok": True, **kw}


def _pt(raw) -> Point | None:
    """Coerce raw value to a (x, y) float tuple; return None on failure."""
    try:
        x, y = float(raw[0]), float(raw[1])
        return (x, y)
    except Exception:
        return None


def _snap(val: float, grid: float = 50.0) -> float:
    """Snap to KiCad default 50-mil (1.27 mm) grid — used for auto_connect."""
    if grid <= 0:
        return val
    return round(round(val / grid) * grid, 10)


# ──────────────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Symbol:
    """A placed component instance on a schematic sheet."""
    lib_ref: str                      # e.g. "Device:R", "Device:C"
    designator: str                   # e.g. "R1", "U1"
    value: str                        # e.g. "10k", "100nF"
    position: Point                   # (x, y) in mm
    pins: dict[str, Point] = field(default_factory=dict)
    # pin_name → (x, y) absolute on-sheet coordinate
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Wire:
    """An ordered sequence of (x, y) waypoints forming connected wire segments."""
    points: list[Point]               # ≥ 2 points
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Junction:
    """An explicit solder-dot at a multi-way wire intersection."""
    at: Point
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Label:
    """A net label (global) or hierarchical port label."""
    at: Point
    net_name: str
    direction: str = "input"          # "input" | "output" | "bidirectional" | "passive"
    is_hierarchical: bool = False
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Bus:
    """A named net bundle."""
    name: str                         # e.g. "DATA[7:0]"
    net_names: list[str] = field(default_factory=list)
    # Expanded net names, e.g. ["DATA0", …, "DATA7"]
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Sheet:
    """One schematic page."""
    sheet_id: str
    name: str = "Root"
    symbols: list[Symbol] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)
    junctions: list[Junction] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    buses: list[Bus] = field(default_factory=list)
    # Sub-sheet references: list of {"sheet_id": str, "name": str, "at": Point}
    sub_sheets: list[dict] = field(default_factory=list)
    # Hierarchical ports exposed by this sheet to the parent
    hier_ports: list[Label] = field(default_factory=list)
    # Verbatim unrecognised S-expression tokens from a KiCad load
    raw_extra: list[str] = field(default_factory=list)


@dataclass
class Schematic:
    """Top-level container."""
    sheets: dict[str, Sheet] = field(default_factory=dict)
    active_sheet: str = ""

    def _active(self) -> Sheet | None:
        return self.sheets.get(self.active_sheet)

    def new_sheet(self, name: str = "Root") -> Sheet:
        sid = str(uuid.uuid4())
        s = Sheet(sheet_id=sid, name=name)
        self.sheets[sid] = s
        if not self.active_sheet:
            self.active_sheet = sid
        return s


# ──────────────────────────────────────────────────────────────────────────────
# Operations
# ──────────────────────────────────────────────────────────────────────────────

def place_symbol(
    schematic: Schematic,
    lib_ref: str,
    designator: str,
    value: str,
    position: Any,
    pins: dict | None = None,
) -> dict:
    """
    Place a symbol on the active sheet.

    Parameters
    ----------
    schematic  : Schematic
    lib_ref    : str   library:symbol name, e.g. "Device:R"
    designator : str   reference designator, e.g. "R1"
    value      : str   component value, e.g. "10k"
    position   : sequence(x, y) in mm
    pins       : optional dict mapping pin name → [x, y] (absolute coords)

    Returns
    -------
    dict with ok, symbol_uuid, designator on success.
    """
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet; call schematic.new_sheet() first")
    if not lib_ref or not isinstance(lib_ref, str):
        return _err("lib_ref must be a non-empty string")
    if not designator or not isinstance(designator, str):
        return _err("designator must be a non-empty string")
    pt = _pt(position)
    if pt is None:
        return _err("position must be a sequence of two numbers")
    # Uniqueness check
    existing = {s.designator for s in sheet.symbols}
    if designator in existing:
        return _err(f"designator '{designator}' already exists on sheet '{sheet.name}'")
    sym = Symbol(
        lib_ref=lib_ref,
        designator=designator,
        value=str(value) if value is not None else "",
        position=pt,
        pins={k: tuple(v) for k, v in (pins or {}).items()},
    )
    sheet.symbols.append(sym)
    return _ok(symbol_uuid=sym.uuid, designator=designator)


def connect_wires(schematic: Schematic, points: Any) -> dict:
    """
    Append a wire path (list of [x, y] waypoints) to the active sheet.

    At least 2 points are required.  Returns wire_uuid on success.
    """
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet")
    try:
        pts = [_pt(p) for p in points]
    except Exception as exc:
        return _err(f"could not parse points: {exc}")
    if any(p is None for p in pts):
        return _err("each point must be a sequence of two numbers")
    if len(pts) < 2:
        return _err("at least 2 points required to form a wire")
    w = Wire(points=pts)
    sheet.wires.append(w)
    return _ok(wire_uuid=w.uuid, segments=len(pts) - 1)


def auto_connect(
    schematic: Schematic,
    pin_a: Any,
    pin_b: Any,
) -> dict:
    """
    Route a 1-bend orthogonal wire between two pin coordinates.

    The bend is placed at (pin_a[0], pin_b[1]) — horizontal first, then
    vertical.  If pins are already collinear (same x or same y) a straight
    segment is added.  Returns the created wire's uuid.
    """
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet")
    a = _pt(pin_a)
    b = _pt(pin_b)
    if a is None:
        return _err("pin_a must be a sequence of two numbers")
    if b is None:
        return _err("pin_b must be a sequence of two numbers")
    ax, ay = a
    bx, by = b
    if abs(ax - bx) < 1e-9 or abs(ay - by) < 1e-9:
        # Already collinear → straight wire
        pts = [a, b]
    else:
        # 1-bend: horizontal segment first, then vertical
        mid = (bx, ay)
        pts = [a, mid, b]
    w = Wire(points=pts)
    sheet.wires.append(w)
    return _ok(wire_uuid=w.uuid, bend=(len(pts) == 3), points=[[p[0], p[1]] for p in pts])


def add_junction(schematic: Schematic, at: Any) -> dict:
    """Place a junction dot at coordinate *at*."""
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet")
    pt = _pt(at)
    if pt is None:
        return _err("at must be a sequence of two numbers")
    j = Junction(at=pt)
    sheet.junctions.append(j)
    return _ok(junction_uuid=j.uuid, at=list(pt))


def add_label(schematic: Schematic, at: Any, net_name: str) -> dict:
    """
    Attach a global net label at coordinate *at* with name *net_name*.
    """
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet")
    pt = _pt(at)
    if pt is None:
        return _err("at must be a sequence of two numbers")
    if not net_name or not isinstance(net_name, str):
        return _err("net_name must be a non-empty string")
    lbl = Label(at=pt, net_name=net_name, is_hierarchical=False)
    sheet.labels.append(lbl)
    return _ok(label_uuid=lbl.uuid, net_name=net_name)


def hierarchical_port(
    schematic: Schematic,
    sheet_id: str,
    port_name: str,
    direction: str = "input",
) -> dict:
    """
    Declare a hierarchical sheet-pin (port) on the named sheet.

    The port is added to ``sheet.hier_ports`` so that ``build_netlist``
    can propagate the net through the sheet boundary.

    Parameters
    ----------
    schematic  : Schematic
    sheet_id   : str   target sheet id (must exist in schematic.sheets)
    port_name  : str   port / net name as seen from the parent
    direction  : str   "input" | "output" | "bidirectional" | "passive"
    """
    sheet = schematic.sheets.get(sheet_id)
    if sheet is None:
        return _err(f"sheet '{sheet_id}' not found")
    valid_dirs = {"input", "output", "bidirectional", "passive"}
    if direction not in valid_dirs:
        return _err(f"direction must be one of {sorted(valid_dirs)}")
    if not port_name or not isinstance(port_name, str):
        return _err("port_name must be a non-empty string")
    # Deduplicate: if a port of the same name already exists, update direction
    for p in sheet.hier_ports:
        if p.net_name == port_name:
            p.direction = direction
            return _ok(port_uuid=p.uuid, port_name=port_name, updated=True)
    port = Label(at=(0.0, 0.0), net_name=port_name, direction=direction,
                 is_hierarchical=True)
    sheet.hier_ports.append(port)
    return _ok(port_uuid=port.uuid, port_name=port_name, updated=False)


# ──────────────────────────────────────────────────────────────────────────────
# Connectivity / netlist
# ──────────────────────────────────────────────────────────────────────────────

def _pt_on_segment(p: Point, a: Point, b: Point, tol: float = 1e-6) -> bool:
    """
    Return True if point *p* lies on the axis-aligned line segment (a, b).
    Only handles horizontal and vertical segments (KiCad orthogonal wires).
    """
    px, py = p
    ax, ay = a
    bx, by = b
    if abs(ay - by) < tol:
        # Horizontal segment
        if abs(py - ay) > tol:
            return False
        return min(ax, bx) - tol <= px <= max(ax, bx) + tol
    if abs(ax - bx) < tol:
        # Vertical segment
        if abs(px - ax) > tol:
            return False
        return min(ay, by) - tol <= py <= max(ay, by) + tol
    # Diagonal: not used in orthogonal schematics; fall back to endpoint check
    return False


def _build_wire_graph(
    sheet: Sheet,
    extra_points: list[Point] | None = None,
) -> dict[Point, set[Point]]:
    """
    Build a point-adjacency graph for all wire segments on a sheet.

    If *extra_points* is provided (e.g. pin coordinates, label positions),
    any extra point that lies in the interior of a wire segment is inserted
    as a node that connects to both segment endpoints.  This allows pins and
    labels placed mid-segment to be found in the correct connected component.
    """
    def _round(p: Point) -> Point:
        return (round(p[0], 6), round(p[1], 6))

    graph: dict[Point, set[Point]] = {}

    def _add_edge(a: Point, b: Point):
        a, b = _round(a), _round(b)
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)

    extra = [_round(ep) for ep in (extra_points or [])]

    for wire in sheet.wires:
        pts = wire.points
        for i in range(len(pts) - 1):
            seg_a = pts[i]
            seg_b = pts[i + 1]
            # Find any extra points that lie on this segment
            mid_pts = [
                ep for ep in extra
                if ep != _round(seg_a) and ep != _round(seg_b)
                and _pt_on_segment(ep, seg_a, seg_b)
            ]
            # Build the full ordered list of nodes on this segment
            seg_nodes: list[Point] = [_round(seg_a)]
            if mid_pts:
                # Sort along the segment
                ax, ay = seg_a
                bx, by = seg_b
                if abs(bx - ax) >= abs(by - ay):
                    # Horizontal: sort by x
                    mid_pts.sort(key=lambda p: p[0])
                else:
                    # Vertical: sort by y
                    mid_pts.sort(key=lambda p: p[1])
                seg_nodes.extend(mid_pts)
            seg_nodes.append(_round(seg_b))
            for j in range(len(seg_nodes) - 1):
                _add_edge(seg_nodes[j], seg_nodes[j + 1])
    return graph


def _connected_components(graph: dict[Point, set[Point]]) -> list[set[Point]]:
    """Return connected components via iterative BFS."""
    visited: set[Point] = set()
    components: list[set[Point]] = []
    for node in graph:
        if node in visited:
            continue
        comp: set[Point] = set()
        queue = [node]
        while queue:
            cur = queue.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.add(cur)
            queue.extend(graph.get(cur, set()) - visited)
        components.append(comp)
    return components


def _pt_near(a: Point, b: Point, tol: float = 1e-4) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _find_net(point: Point, components: list[set[Point]], net_map: dict) -> str | None:
    """Return the net name for a point that lies in a labelled component."""
    rp = (round(point[0], 6), round(point[1], 6))
    for comp in components:
        if rp in comp:
            return net_map.get(id(comp))
    return None


def build_netlist(schematic: Schematic) -> dict:
    """
    Trace connectivity across all sheets and return a JSON netlist plus a
    KiCad-classic (legacy) netlist string.

    The returned dict has:
        ok         : True
        nets       : list of { net_name, pins: [ {ref, pin} ] }
        netlist_json : str (JSON)
        netlist_kicad : str (KiCad legacy .net format)
        net_count  : int
        pin_count  : int
    """
    # Collect all nets across sheets ─────────────────────────────────────
    all_nets: dict[str, list[dict]] = {}   # net_name → [{ref, pin, sheet}]

    for sheet_id, sheet in schematic.sheets.items():
        # Gather all significant points so interior pin/label positions are
        # inserted into the wire graph as explicit nodes.
        extra_pts: list[Point] = []
        for sym in sheet.symbols:
            extra_pts.extend(sym.pins.values())
        for lbl in sheet.labels + sheet.hier_ports:
            extra_pts.append(lbl.at)

        graph = _build_wire_graph(sheet, extra_points=extra_pts)
        components = _connected_components(graph)

        # Map component id → net name (labels win; fallback to auto-name)
        net_map: dict[int, str] = {}
        for lbl in sheet.labels + sheet.hier_ports:
            rp = (round(lbl.at[0], 6), round(lbl.at[1], 6))
            for comp in components:
                if rp in comp:
                    net_map[id(comp)] = lbl.net_name
                    break

        # Assign auto-names to unlabelled components
        _counter = [0]
        for comp in components:
            if id(comp) not in net_map:
                _counter[0] += 1
                net_map[id(comp)] = f"Net-({sheet.name}-{_counter[0]})"

        # Map pin coordinates to nets
        def _pin_net(pin_pt: Point) -> str:
            rp = (round(pin_pt[0], 6), round(pin_pt[1], 6))
            for comp in components:
                if rp in comp:
                    return net_map[id(comp)]
            # Pin not on any wire → unconnected sentinel
            return f"UNCONNECTED-({sheet_id[:8]})"

        for sym in sheet.symbols:
            for pin_name, pin_coord in sym.pins.items():
                net = _pin_net(pin_coord)
                all_nets.setdefault(net, []).append(
                    {"ref": sym.designator, "pin": pin_name, "sheet": sheet_id}
                )

        # Propagate hierarchical ports to parent net
        for port in sheet.hier_ports:
            rp = (round(port.at[0], 6), round(port.at[1], 6))
            for comp in components:
                if rp in comp:
                    net_name = net_map.get(id(comp), port.net_name)
                    all_nets.setdefault(net_name, []).append(
                        {"ref": f"(hier:{sheet.name})", "pin": port.net_name,
                         "sheet": sheet_id}
                    )

    nets_list = [
        {"net_name": name, "pins": pins}
        for name, pins in sorted(all_nets.items())
    ]

    import json as _json
    netlist_json = _json.dumps({"nets": nets_list}, indent=2)

    # KiCad legacy .net ───────────────────────────────────────────────────
    lines = ["(export (version D)", " (nets"]
    for idx, net in enumerate(nets_list, start=1):
        pin_strs = " ".join(
            f'(node (ref "{p["ref"]}") (pin "{p["pin"]}"))'
            for p in net["pins"]
        )
        lines.append(f'  (net (code {idx}) (name "{net["net_name"]}") {pin_strs})')
    lines += [" )", ")"]
    netlist_kicad = "\n".join(lines)

    total_pins = sum(len(n["pins"]) for n in nets_list)
    return _ok(
        nets=nets_list,
        netlist_json=netlist_json,
        netlist_kicad=netlist_kicad,
        net_count=len(nets_list),
        pin_count=total_pins,
    )


# ──────────────────────────────────────────────────────────────────────────────
# ERC — Electrical Rules Check
# ──────────────────────────────────────────────────────────────────────────────

def validate_erc(schematic: Schematic) -> dict:
    """
    Run an Electrical Rules Check and return a list of violations.

    Checks performed
    ----------------
    1. Unconnected pins — symbol pins not on any wire and not labelled.
    2. Conflicting net drivers — two output-direction labels on the same net.
    3. Net name collisions — same net name used as both hierarchical port and
       global label on the same sheet.
    4. Dangling wire ends — a wire endpoint that touches no other wire, pin or
       label.
    5. Missing symbol — designator exists but no pins defined (lib_ref unknown).
    6. Duplicate designators across the whole schematic.

    Returns
    -------
    dict with ok, violations (list of {code, message, sheet, ref?}),
    error_count, warning_count.
    """
    violations: list[dict] = []

    def _viol(code: str, msg: str, sheet_name: str, ref: str = ""):
        violations.append({"code": code, "message": msg,
                           "sheet": sheet_name, "ref": ref})

    # Global duplicate designator check
    all_designators: dict[str, list[str]] = {}  # designator → [sheet_names]
    for sheet in schematic.sheets.values():
        for sym in sheet.symbols:
            all_designators.setdefault(sym.designator, []).append(sheet.name)
    for des, sheets in all_designators.items():
        if len(sheets) > 1:
            _viol("ERC_DUPLICATE_DESIGNATOR",
                  f"Designator '{des}' appears on multiple sheets: {sheets}",
                  sheets[0], des)

    for sheet_id, sheet in schematic.sheets.items():
        # Collect extra points for interior-segment node insertion
        extra_pts_erc: list[Point] = []
        for sym in sheet.symbols:
            extra_pts_erc.extend(sym.pins.values())
        for lbl in sheet.labels + sheet.hier_ports:
            extra_pts_erc.append(lbl.at)

        graph = _build_wire_graph(sheet, extra_points=extra_pts_erc)
        components = _connected_components(graph)

        # All graph nodes (includes inserted interior points)
        graph_pts: set[Point] = set(graph.keys())

        # Build a set of labelled points
        labelled_pts: set[Point] = set()
        label_net_dir: dict[str, list[str]] = {}  # net → [directions]
        for lbl in sheet.labels + sheet.hier_ports:
            rp = (round(lbl.at[0], 6), round(lbl.at[1], 6))
            labelled_pts.add(rp)
            label_net_dir.setdefault(lbl.net_name, []).append(lbl.direction)

        # Build component net map
        net_map: dict[int, str] = {}
        for lbl in sheet.labels + sheet.hier_ports:
            rp = (round(lbl.at[0], 6), round(lbl.at[1], 6))
            for comp in components:
                if rp in comp:
                    net_map[id(comp)] = lbl.net_name
                    break

        def _pin_on_wire(pin_pt: Point) -> bool:
            rp = (round(pin_pt[0], 6), round(pin_pt[1], 6))
            return rp in graph_pts

        def _pin_on_label(pin_pt: Point) -> bool:
            rp = (round(pin_pt[0], 6), round(pin_pt[1], 6))
            return rp in labelled_pts

        # 1. Unconnected pins
        for sym in sheet.symbols:
            if not sym.pins:
                _viol("ERC_MISSING_PINS",
                      f"Symbol '{sym.designator}' ({sym.lib_ref}) has no pins defined",
                      sheet.name, sym.designator)
                continue
            for pin_name, pin_coord in sym.pins.items():
                if not _pin_on_wire(pin_coord) and not _pin_on_label(pin_coord):
                    _viol("ERC_UNCONNECTED_PIN",
                          f"Pin '{pin_name}' of '{sym.designator}' is unconnected",
                          sheet.name, sym.designator)

        # 2. Conflicting drivers (two 'output' labels on same net)
        for net_name, directions in label_net_dir.items():
            out_count = directions.count("output")
            if out_count > 1:
                _viol("ERC_CONFLICTING_DRIVER",
                      f"Net '{net_name}' has {out_count} output drivers",
                      sheet.name)

        # 3. Net name collision — same name used as both global + hierarchical
        global_nets = {lbl.net_name for lbl in sheet.labels}
        hier_nets = {lbl.net_name for lbl in sheet.hier_ports}
        for name in global_nets & hier_nets:
            _viol("ERC_NET_NAME_COLLISION",
                  f"Net name '{name}' used as both global label and hierarchical port",
                  sheet.name)

        # 4. Dangling wire ends — wire endpoint touched by only one segment
        endpoint_count: dict[Point, int] = {}
        for wire in sheet.wires:
            for p in wire.points:
                rp = (round(p[0], 6), round(p[1], 6))
                endpoint_count[rp] = endpoint_count.get(rp, 0) + 1
        pin_pts: set[Point] = set()
        for sym in sheet.symbols:
            for pc in sym.pins.values():
                pin_pts.add((round(pc[0], 6), round(pc[1], 6)))

        for wire in sheet.wires:
            for p in (wire.points[0], wire.points[-1]):
                rp = (round(p[0], 6), round(p[1], 6))
                touches = endpoint_count.get(rp, 0)
                if touches <= 1 and rp not in labelled_pts and rp not in pin_pts:
                    _viol("ERC_DANGLING_WIRE",
                          f"Wire endpoint at ({p[0]}, {p[1]}) is dangling",
                          sheet.name)

    error_codes = {"ERC_UNCONNECTED_PIN", "ERC_CONFLICTING_DRIVER",
                   "ERC_DUPLICATE_DESIGNATOR", "ERC_NET_NAME_COLLISION",
                   "ERC_MISSING_PINS"}
    warning_codes = {"ERC_DANGLING_WIRE"}
    errors = [v for v in violations if v["code"] in error_codes]
    warnings_ = [v for v in violations if v["code"] in warning_codes]
    return _ok(
        violations=violations,
        error_count=len(errors),
        warning_count=len(warnings_),
        passed=(len(errors) == 0),
    )


# ──────────────────────────────────────────────────────────────────────────────
# KiCad .kicad_sch (v6+) S-expression I/O
# ──────────────────────────────────────────────────────────────────────────────

# Minimal tokeniser for KiCad S-expressions ──────────────────────────────────

def _tokenise(text: str) -> list[str]:
    """
    Split KiCad S-expression text into a flat token list.
    Tokens: '(', ')', quoted strings (unescaped), bare words.
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\n\r':
            i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == '\\' and j + 1 < n:
                    j += 1
                    buf.append(text[j])
                else:
                    buf.append(text[j])
                j += 1
            tokens.append('"' + ''.join(buf) + '"')
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\n\r()':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_sexp(tokens: list[str], pos: int) -> tuple[Any, int]:
    """
    Recursive S-expression parser.  Returns (parsed_node, next_pos).
    A node is either a string or a list [head, child1, …].
    """
    if pos >= len(tokens):
        return None, pos
    tok = tokens[pos]
    if tok == '(':
        pos += 1  # consume '('
        node = []
        while pos < len(tokens) and tokens[pos] != ')':
            child, pos = _parse_sexp(tokens, pos)
            node.append(child)
        pos += 1  # consume ')'
        return node, pos
    else:
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1], pos + 1
        return tok, pos + 1


def _find_child(node: list, key: str) -> list | None:
    """Return the first child list whose head equals *key*."""
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == key:
            return child
    return None


def _find_all_children(node: list, key: str) -> list[list]:
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def load_kicad_sch(text: str) -> dict:
    """
    Parse a minimal KiCad v6+ S-expression schematic (.kicad_sch) and return
    a ``Schematic`` containing the parsed sheet.

    Only the following tokens are parsed; anything else is preserved verbatim
    in ``Sheet.raw_extra``:

    * ``(kicad_sch …)``          — top-level wrapper
    * ``(symbol …)``             — placed component instance
    * ``(wire (pts …) …)``       — wire segment
    * ``(junction (at x y) …)``  — solder dot
    * ``(label (at x y) … (text "…") …)``  — net label

    Returns
    -------
    dict with ok, schematic (Schematic).
    """
    if not text or not isinstance(text, str):
        return _err("text must be a non-empty string")
    try:
        tokens = _tokenise(text.strip())
        if not tokens:
            return _err("empty S-expression")
        root, _ = _parse_sexp(tokens, 0)
    except Exception as exc:
        return _err(f"parse error: {exc}")

    if not isinstance(root, list) or not root or root[0] != 'kicad_sch':
        return _err("not a kicad_sch S-expression")

    sch = Schematic()
    sheet = sch.new_sheet("Root")

    raw_extra: list[str] = []

    for child in root[1:]:
        if not isinstance(child, list) or not child:
            continue
        head = child[0]

        if head == 'symbol':
            # Placed instance: (symbol (lib_id "…") (at x y …) (reference "…") (value "…"))
            lib_id_node = _find_child(child, 'lib_id')
            lib_ref = lib_id_node[1] if lib_id_node and len(lib_id_node) > 1 else 'unknown'
            at_node = _find_child(child, 'at')
            try:
                x, y = float(at_node[1]), float(at_node[2]) if at_node else (0.0, 0.0)
            except Exception:
                x, y = 0.0, 0.0
            # Properties: reference + value
            ref_val = 'U?'
            val_str = ''
            for prop in _find_all_children(child, 'property'):
                if len(prop) >= 3 and prop[1] == 'Reference':
                    ref_val = str(prop[2])
                elif len(prop) >= 3 and prop[1] == 'Value':
                    val_str = str(prop[2])
            sym = Symbol(
                lib_ref=lib_ref,
                designator=ref_val,
                value=val_str,
                position=(x, y),
            )
            sheet.symbols.append(sym)

        elif head == 'wire':
            pts_node = _find_child(child, 'pts')
            if pts_node:
                xy_nodes = _find_all_children(pts_node, 'xy')
                pts = []
                for xy in xy_nodes:
                    try:
                        pts.append((float(xy[1]), float(xy[2])))
                    except Exception:
                        pass
                if len(pts) >= 2:
                    sheet.wires.append(Wire(points=pts))

        elif head == 'junction':
            at_node = _find_child(child, 'at')
            if at_node and len(at_node) >= 3:
                try:
                    j = Junction(at=(float(at_node[1]), float(at_node[2])))
                    sheet.junctions.append(j)
                except Exception:
                    pass

        elif head == 'label':
            at_node = _find_child(child, 'at')
            # text can be the 2nd positional element or in a (text "…") child
            net_name = ''
            text_node = _find_child(child, 'text')
            if text_node and len(text_node) > 1:
                net_name = str(text_node[1])
            elif len(child) > 1 and isinstance(child[1], str):
                net_name = child[1]
            at_pt = (0.0, 0.0)
            if at_node and len(at_node) >= 3:
                try:
                    at_pt = (float(at_node[1]), float(at_node[2]))
                except Exception:
                    pass
            if net_name:
                sheet.labels.append(Label(at=at_pt, net_name=net_name))

        else:
            raw_extra.append(head)

    sheet.raw_extra = raw_extra
    return _ok(schematic=sch)


def save_kicad_sch(schematic: Schematic, sheet_id: str | None = None) -> dict:
    """
    Serialise one sheet as a KiCad v6 S-expression schematic (.kicad_sch).

    If *sheet_id* is None the active sheet is used.

    Returns
    -------
    dict with ok, kicad_sch (str).
    """
    sid = sheet_id or schematic.active_sheet
    sheet = schematic.sheets.get(sid)
    if sheet is None:
        return _err(f"sheet '{sid}' not found")

    lines: list[str] = [
        '(kicad_sch (version 20230121) (generator kerf)',
        '  (lib_symbols)',
    ]

    for sym in sheet.symbols:
        x, y = sym.position
        lines.append(f'  (symbol (lib_id "{sym.lib_ref}") (at {x} {y} 0)')
        lines.append(f'    (property "Reference" "{sym.designator}")')
        lines.append(f'    (property "Value" "{sym.value}")')
        lines.append(f'    (uuid "{sym.uuid}")')
        lines.append('  )')

    for wire in sheet.wires:
        pts_str = ' '.join(f'(xy {p[0]} {p[1]})' for p in wire.points)
        lines.append(f'  (wire (pts {pts_str}) (uuid "{wire.uuid}"))')

    for junc in sheet.junctions:
        lines.append(f'  (junction (at {junc.at[0]} {junc.at[1]}) (uuid "{junc.uuid}"))')

    for lbl in sheet.labels:
        lines.append(
            f'  (label "{lbl.net_name}" (at {lbl.at[0]} {lbl.at[1]} 0)'
            f' (uuid "{lbl.uuid}"))'
        )

    lines.append(')')
    return _ok(kicad_sch='\n'.join(lines))


# ──────────────────────────────────────────────────────────────────────────────
# Bus expansion
# ──────────────────────────────────────────────────────────────────────────────

def expand_bus(schematic: Schematic, bus_name: str) -> dict:
    """
    Expand a bus name like ``DATA[3:0]`` into individual net names
    [``DATA3``, ``DATA2``, ``DATA1``, ``DATA0``] and register the bus on the
    active sheet.

    If the bus name has no range bracket (e.g. ``CLK``), it is treated as a
    single-net bus.

    Returns
    -------
    dict with ok, bus_uuid, net_names.
    """
    sheet = schematic._active()
    if sheet is None:
        return _err("no active sheet")
    if not bus_name or not isinstance(bus_name, str):
        return _err("bus_name must be a non-empty string")

    m = re.match(r'^(\w+)\[(\d+):(\d+)\]$', bus_name.strip())
    if m:
        base = m.group(1)
        hi, lo = int(m.group(2)), int(m.group(3))
        step = 1 if lo <= hi else -1
        net_names = [f"{base}{i}" for i in range(hi, lo - step, -step)]
    else:
        net_names = [bus_name]

    bus = Bus(name=bus_name, net_names=net_names)
    sheet.buses.append(bus)
    return _ok(bus_uuid=bus.uuid, net_names=net_names)
