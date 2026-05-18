"""kicad_io.py — bidirectional bridge between Circuit JSON and KiCad v6/v7 format.

Public API
----------
circuit_json_to_kicad_pcb(circuit_json) -> str
    Emit a KiCad v6/v7 .kicad_pcb s-expression string.

circuit_json_to_kicad_sch(circuit_json) -> str
    Emit a KiCad v6 .kicad_sch s-expression string.

kicad_pcb_to_circuit_json(text) -> dict
    Parse a .kicad_pcb string and return a Circuit-JSON list.
    Round-trip guarantee: component refs, net names, and footprint names
    survive a circuit_json → kicad_pcb → circuit_json cycle.

All functions are pure Python; no external dependencies required.
"""

from __future__ import annotations

import re
from typing import Any


# ─── Pure-Python S-expression lexer ───────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lex a KiCad s-expression string into a flat token list.

    Tokens are:  '('  ')'  quoted-string  bare-atom  number
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            # quoted string — handle escaped quotes
            j = i + 1
            buf: list[str] = []
            while j < n:
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                elif ch == '"':
                    j += 1
                    break
                else:
                    buf.append(ch)
                    j += 1
            tokens.append('"' + "".join(buf) + '"')
            i = j
        else:
            # bare atom (number, keyword, uuid …)
            j = i
            while j < n and text[j] not in " \t\r\n()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse(tokens: list[str], pos: int = 0) -> tuple[Any, int]:
    """Recursively parse tokenised s-expression into nested Python lists.

    Each list node is  [keyword, child, child, ...]  where children may be
    strings or nested lists.  Returns (node, next_pos).
    """
    if pos >= len(tokens):
        return None, pos
    tok = tokens[pos]
    if tok == "(":
        pos += 1  # consume '('
        node: list[Any] = []
        while pos < len(tokens) and tokens[pos] != ")":
            child, pos = _parse(tokens, pos)
            node.append(child)
        pos += 1  # consume ')'
        return node, pos
    elif tok == ")":
        raise ValueError(f"Unexpected ')' at token position {pos}")
    else:
        # atom — strip surrounding quotes if present
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1], pos + 1
        return tok, pos + 1


def _parse_sexpr(text: str) -> Any:
    """Parse a complete s-expression string.  Returns the root node."""
    tokens = _tokenize(text)
    if not tokens:
        return []
    node, _ = _parse(tokens, 0)
    return node


# ─── Pure-Python S-expression emitter ─────────────────────────────────────────

def _quote(s: str) -> str:
    """Wrap *s* in double quotes, escaping internal backslash and quote chars."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class _Sexp:
    """Lightweight s-expression builder.

    Usage::

        s = _Sexp("kicad_pcb")
        s.attr("version", 20211014)
        with s.child("general") as g:
            g.attr("thickness", 1.6)
        print(s.render())
    """

    def __init__(self, tag: str, indent: int = 0):
        self._tag = tag
        self._indent = indent
        self._children: list[str | _Sexp] = []

    # ── fluent helpers ─────────────────────────────────────────────────────────

    def atom(self, value: str | int | float) -> "_Sexp":
        """Append a bare atom (unquoted) child."""
        self._children.append(str(value))
        return self

    def quoted(self, value: str) -> "_Sexp":
        """Append a quoted string atom."""
        self._children.append(_quote(value))
        return self

    def attr(self, key: str, value: str | int | float, quote_value: bool = False) -> "_Sexp":
        """Append  (key value)  inline."""
        if quote_value or isinstance(value, str) and not _looks_like_number(value):
            self._children.append(f"({key} {_quote(str(value))})")
        else:
            self._children.append(f"({key} {value})")
        return self

    def child(self, tag: str) -> "_Sexp":
        """Create and register a child _Sexp node; return it."""
        c = _Sexp(tag, self._indent + 2)
        self._children.append(c)
        return c

    # ── rendering ──────────────────────────────────────────────────────────────

    def render(self, indent: int | None = None) -> str:
        ind = self._indent if indent is None else indent
        prefix = " " * ind

        # Decide whether to render inline or multiline.
        # Inline when all children are atoms (no nested _Sexp).
        all_atoms = all(isinstance(c, str) for c in self._children)
        if all_atoms:
            inner = " ".join(self._children)
            if inner:
                return f"{prefix}({self._tag} {inner})"
            return f"{prefix}({self._tag})"

        # Multiline
        lines = [f"{prefix}({self._tag}"]
        for c in self._children:
            if isinstance(c, str):
                lines.append(f"{prefix}  {c}")
            else:
                lines.append(c.render(ind + 2))
        lines.append(f"{prefix})")
        return "\n".join(lines)


def _looks_like_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


# ─── Circuit-JSON helpers ──────────────────────────────────────────────────────

def _by_type(circuit_json: list, *types: str) -> list[dict]:
    """Return all entries whose 'type' is in *types*."""
    type_set = set(types)
    return [e for e in (circuit_json or []) if isinstance(e, dict) and e.get("type") in type_set]


def _index_by(items: list[dict], key: str) -> dict[str, dict]:
    return {item[key]: item for item in items if key in item}


# KiCad layer name mapping (Circuit JSON layer → KiCad canonical name)
_CJ_TO_KICAD_LAYER: dict[str, str] = {
    "top_copper":    "F.Cu",
    "bottom_copper": "B.Cu",
    "top_silkscreen": "F.SilkS",
    "bottom_silkscreen": "B.SilkS",
    "top_mask":      "F.Mask",
    "bottom_mask":   "B.Mask",
    "edge_cuts":     "Edge.Cuts",
}

_KICAD_TO_CJ_LAYER: dict[str, str] = {v: k for k, v in _CJ_TO_KICAD_LAYER.items()}

_KICAD_PCB_LAYERS = [
    (0,  "F.Cu",       "signal"),
    (1,  "In1.Cu",     "signal"),
    (2,  "In2.Cu",     "signal"),
    (31, "B.Cu",       "signal"),
    (32, "B.Adhes",    "user"),
    (33, "F.Adhes",    "user"),
    (34, "B.Paste",    "user"),
    (35, "F.Paste",    "user"),
    (36, "B.SilkS",    "user"),
    (37, "F.SilkS",    "user"),
    (38, "B.Mask",     "user"),
    (39, "F.Mask",     "user"),
    (40, "Dwgs.User",  "user"),
    (41, "Cmts.User",  "user"),
    (42, "Eco1.User",  "user"),
    (43, "Eco2.User",  "user"),
    (44, "Edge.Cuts",  "user"),
    (45, "Margin",     "user"),
    (46, "B.CrtYd",    "user"),
    (47, "F.CrtYd",    "user"),
    (48, "B.Fab",      "user"),
    (49, "F.Fab",      "user"),
]


# ─── circuit_json_to_kicad_pcb ─────────────────────────────────────────────────

def circuit_json_to_kicad_pcb(circuit_json: list) -> str:
    """Convert Circuit JSON to a KiCad v6 .kicad_pcb s-expression string.

    Covers:
    - Standard layer table
    - Setup block with default rules
    - Net declarations (net 0 = empty, then one per source_net / source_trace)
    - Footprints (one per pcb_component) with ref and value text
    - PCB trace segments on F.Cu
    """
    cj = circuit_json or []

    source_components = _by_type(cj, "source_component")
    pcb_components    = _by_type(cj, "pcb_component")
    source_nets       = _by_type(cj, "source_net")
    source_traces     = _by_type(cj, "source_trace")
    pcb_traces        = _by_type(cj, "pcb_trace")

    # Build component lookup: source_component_id → source_component
    sc_by_id = _index_by(source_components, "source_component_id")

    # ── Net table ─────────────────────────────────────────────────────────────
    # Collect unique net names.  Empty net is always index 0.
    net_names: list[str] = [""]   # index 0 = unconnected
    seen_nets: set[str] = set()
    for sn in source_nets:
        name = sn.get("name", sn["source_net_id"])
        if name not in seen_nets:
            net_names.append(name)
            seen_nets.add(name)
    # also harvest net names from traces that have no source_net entry
    for st in source_traces:
        for nid in st.get("connected_source_net_ids", []):
            # look up net name
            sn = next((n for n in source_nets if n.get("source_net_id") == nid), None)
            name = sn["name"] if sn and "name" in sn else nid
            if name not in seen_nets:
                net_names.append(name)
                seen_nets.add(name)
    net_index: dict[str, int] = {n: i for i, n in enumerate(net_names)}

    # ── Root node ─────────────────────────────────────────────────────────────
    root = _Sexp("kicad_pcb")
    root.atom("version 20211014")
    root.atom("generator kerf_electronics")

    # general
    gen = root.child("general")
    gen.attr("thickness", 1.6)

    # paper
    root.child("paper").atom("A4")

    # layers
    layers = root.child("layers")
    for lid, lname, ltype in _KICAD_PCB_LAYERS:
        ln = layers.child(str(lid))
        ln.quoted(lname)
        ln.atom(ltype)

    # setup
    setup = root.child("setup")
    rules = setup.child("rules")
    rules.attr("min_clearance", "0.0")
    rules.attr("min_track_width", "0.0")
    rules.attr("min_via_annular_width", "0.0")
    rules.attr("min_via_diameter", "0.0")
    rules.attr("min_hole_to_hole", "0.0")
    rules.attr("allow_microvias", 0)
    rules.attr("allow_blind_buried_vias", 0)
    rules.attr("aux_axis_origin", 0)
    setup.attr("grid_origin", "0 0")

    # nets
    for i, name in enumerate(net_names):
        n = root.child("net")
        n.atom(str(i))
        n.quoted(name)

    # footprints
    for pcb_comp in pcb_components:
        scid = pcb_comp.get("source_component_id", "")
        sc = sc_by_id.get(scid, {})
        ref   = sc.get("name", scid)
        value = sc.get("value", "")
        fp_name = sc.get("footprint", "Device:R")
        x = float(pcb_comp.get("x", 0.0))
        y = float(pcb_comp.get("y", 0.0))
        rot = float(pcb_comp.get("rotation", 0.0))
        layer_cj = pcb_comp.get("layer", "top_copper")
        layer_kicad = _CJ_TO_KICAD_LAYER.get(layer_cj, "F.Cu")

        fp = root.child("footprint")
        fp.quoted(fp_name)
        fp.attr("layer", layer_kicad, quote_value=True)
        tstamp = f"fp_{scid}"
        fp.attr("tstamp", tstamp, quote_value=True)

        # at
        at = fp.child("at")
        at.atom(f"{x:.4f}")
        at.atom(f"{y:.4f}")
        if rot != 0.0:
            at.atom(f"{rot:.4f}")

        # description / tags from value
        if value:
            fp.attr("descr", value, quote_value=True)

        # reference text
        ref_txt = fp.child("fp_text")
        ref_txt.atom("reference")
        ref_txt.quoted(ref)
        ref_at = ref_txt.child("at")
        ref_at.atom("0")
        ref_at.atom("-1.0")
        ref_txt.attr("layer", "F.SilkS", quote_value=True)
        ref_eff = ref_txt.child("effects")
        ref_eff_font = ref_eff.child("font")
        ref_eff_font.attr("size", "1 1")
        ref_eff_font.attr("thickness", "0.15")

        # value text
        val_txt = fp.child("fp_text")
        val_txt.atom("value")
        val_txt.quoted(value if value else ref)
        val_at = val_txt.child("at")
        val_at.atom("0")
        val_at.atom("1.0")
        val_txt.attr("layer", "F.Fab", quote_value=True)
        val_eff = val_txt.child("effects")
        val_eff_font = val_eff.child("font")
        val_eff_font.attr("size", "1 1")
        val_eff_font.attr("thickness", "0.15")

    # segments (pcb_trace)
    for pt in pcb_traces:
        route = pt.get("route", [])
        width = float(pt.get("width", 0.2))
        layer_cj = pt.get("layer", "top_copper")
        layer_kicad = _CJ_TO_KICAD_LAYER.get(layer_cj, "F.Cu")

        # Determine net index from associated source_trace
        trace_net_index = 0
        st_id = pt.get("source_trace_id")
        if st_id:
            st = next((t for t in source_traces if t.get("source_trace_id") == st_id), None)
            if st:
                for nid in st.get("connected_source_net_ids", []):
                    sn = next((n for n in source_nets if n.get("source_net_id") == nid), None)
                    name = sn["name"] if sn and "name" in sn else nid
                    trace_net_index = net_index.get(name, 0)
                    break

        for i in range(len(route) - 1):
            p1 = route[i]
            p2 = route[i + 1]
            seg = root.child("segment")
            s = seg.child("start")
            s.atom(f"{float(p1['x']):.4f}")
            s.atom(f"{float(p1['y']):.4f}")
            e = seg.child("end")
            e.atom(f"{float(p2['x']):.4f}")
            e.atom(f"{float(p2['y']):.4f}")
            seg.attr("width", f"{width:.4f}")
            seg.attr("layer", layer_kicad, quote_value=True)
            seg.attr("net", trace_net_index)

    return root.render(0)


# ─── circuit_json_to_kicad_sch ─────────────────────────────────────────────────

def circuit_json_to_kicad_sch(circuit_json: list) -> str:
    """Convert Circuit JSON to a KiCad v6 .kicad_sch s-expression string.

    Covers:
    - Standard schematic header (version, uuid)
    - lib_symbols section (one symbol per unique footprint)
    - symbol instances (one per source_component) with ref/value properties
    - Wire segments from source_traces
    - net_labels for source_nets
    """
    cj = circuit_json or []

    source_components = _by_type(cj, "source_component")
    source_ports      = _by_type(cj, "source_port")
    source_traces     = _by_type(cj, "source_trace")
    source_nets       = _by_type(cj, "source_net")

    sc_by_id = _index_by(source_components, "source_component_id")
    port_by_id = _index_by(source_ports, "source_port_id")

    # Net lookup: net_id → net_name
    net_by_id: dict[str, str] = {}
    for sn in source_nets:
        net_by_id[sn["source_net_id"]] = sn.get("name", sn["source_net_id"])

    root = _Sexp("kicad_sch")
    root.atom("version 20211123")
    root.atom("generator kerf_electronics")

    # Paper
    root.child("paper").quoted("A4")

    # lib_symbols — minimal stub entries
    libs = root.child("lib_symbols")
    seen_fps: set[str] = set()
    for sc in source_components:
        fp = sc.get("footprint", "Device:R")
        lib_sym_name = fp.replace(":", "_")
        if lib_sym_name not in seen_fps:
            seen_fps.add(lib_sym_name)
            sym = libs.child("symbol")
            sym.quoted(lib_sym_name)
            sym.attr("pin_names_offset", "0")
            sym.attr("in_bom", "yes")
            sym.attr("on_board", "yes")

    # Place symbols in a grid (4 columns, auto-increment y)
    col_count = 4
    spacing_x = 15.0
    spacing_y = 10.0

    for idx, sc in enumerate(source_components):
        col = idx % col_count
        row = idx // col_count
        sx = col * spacing_x
        sy = row * spacing_y

        fp = sc.get("footprint", "Device:R")
        lib_sym_name = fp.replace(":", "_")
        ref = sc.get("name", sc["source_component_id"])
        value = sc.get("value", "")

        sym = root.child("symbol")
        sym.quoted(lib_sym_name)

        at = sym.child("at")
        at.atom(f"{sx:.4f}")
        at.atom(f"{sy:.4f}")
        at.atom("0")

        sym.attr("unit", "1")

        # Reference property
        p_ref = sym.child("property")
        p_ref.quoted("Reference")
        p_ref.quoted(ref)
        p_ref.attr("id", "0")
        p_ref_at = p_ref.child("at")
        p_ref_at.atom(f"{sx:.4f}")
        p_ref_at.atom(f"{sy - 1.5:.4f}")
        p_ref_at.atom("0")

        # Value property
        p_val = sym.child("property")
        p_val.quoted("Value")
        p_val.quoted(value if value else ref)
        p_val.attr("id", "1")
        p_val_at = p_val.child("at")
        p_val_at.atom(f"{sx:.4f}")
        p_val_at.atom(f"{sy + 1.5:.4f}")
        p_val_at.atom("0")

        # Footprint property
        p_fp = sym.child("property")
        p_fp.quoted("Footprint")
        p_fp.quoted(fp)
        p_fp.attr("id", "2")
        p_fp_at = p_fp.child("at")
        p_fp_at.atom(f"{sx:.4f}")
        p_fp_at.atom(f"{sy:.4f}")
        p_fp_at.atom("0")

    # Wire stubs for traces (minimal — one wire per connected pair of ports)
    for st in source_traces:
        port_ids = st.get("connected_source_port_ids", [])
        if len(port_ids) < 2:
            continue
        # Simple: connect consecutive port pairs with wire stubs
        for i in range(len(port_ids) - 1):
            p1_id = port_ids[i]
            p2_id = port_ids[i + 1]
            p1 = port_by_id.get(p1_id, {})
            p2 = port_by_id.get(p2_id, {})
            # derive schematic positions from component positions
            c1 = sc_by_id.get(p1.get("source_component_id", ""), {})
            c2 = sc_by_id.get(p2.get("source_component_id", ""), {})
            idx1 = source_components.index(c1) if c1 in source_components else 0
            idx2 = source_components.index(c2) if c2 in source_components else 0
            x1 = (idx1 % col_count) * spacing_x + 0.5
            y1 = (idx1 // col_count) * spacing_y
            x2 = (idx2 % col_count) * spacing_x - 0.5
            y2 = (idx2 // col_count) * spacing_y

            wire = root.child("wire")
            pts = wire.child("pts")
            xy1 = pts.child("xy")
            xy1.atom(f"{x1:.4f}")
            xy1.atom(f"{y1:.4f}")
            xy2 = pts.child("xy")
            xy2.atom(f"{x2:.4f}")
            xy2.atom(f"{y2:.4f}")
            wire.attr("stroke", "default")

    # net_labels for source_nets
    for sn in source_nets:
        name = sn.get("name", sn["source_net_id"])
        lbl = root.child("label")
        lbl.quoted(name)
        lbl.child("at").atom("0").atom("0").atom("0")
        lbl.attr("fields_autoplaced", "")

    return root.render(0)


# ─── kicad_pcb_to_circuit_json ─────────────────────────────────────────────────

def kicad_pcb_to_circuit_json(text: str) -> list:
    """Parse a KiCad v6/v7 .kicad_pcb string and return a Circuit-JSON list.

    Recovers:
    - source_component entries for each footprint (ref → name)
    - pcb_component entries with position/rotation/layer
    - source_net entries from the net table
    - pcb_trace entries from segment nodes
    """
    root = _parse_sexpr(text)
    if not isinstance(root, list) or not root:
        return []

    # root[0] should be the tag "kicad_pcb"
    nodes = root[1:]  # skip tag

    cj: list[dict] = []

    # ── Net table ─────────────────────────────────────────────────────────────
    net_index_to_name: dict[int, str] = {}
    net_name_to_id: dict[str, str] = {}

    for node in nodes:
        if not isinstance(node, list) or not node or node[0] != "net":
            continue
        # (net <index> <name>)
        if len(node) >= 3:
            try:
                idx = int(node[1])
            except (ValueError, TypeError):
                continue
            name = node[2] if isinstance(node[2], str) else str(node[2])
            if name:  # skip empty-net slot 0
                net_index_to_name[idx] = name
                nid = f"sn_{_slugify(name)}"
                net_name_to_id[name] = nid
                cj.append({
                    "type": "source_net",
                    "source_net_id": nid,
                    "name": name,
                })

    # ── Footprints ────────────────────────────────────────────────────────────
    sc_seen: set[str] = set()
    pcb_comp_index = 0

    for node in nodes:
        if not isinstance(node, list) or not node or node[0] != "footprint":
            continue

        # footprint name is node[1]
        fp_name = node[1] if len(node) > 1 and isinstance(node[1], str) else "Unknown"

        ref = ""
        value = ""
        x = 0.0
        y = 0.0
        rot = 0.0
        layer_kicad = "F.Cu"
        tstamp = ""

        for child in node[2:]:
            if not isinstance(child, list) or not child:
                continue
            tag = child[0]

            if tag == "at" and len(child) >= 3:
                try:
                    x = float(child[1])
                    y = float(child[2])
                    if len(child) >= 4:
                        rot = float(child[3])
                except (ValueError, TypeError):
                    pass

            elif tag == "layer" and len(child) >= 2:
                layer_kicad = child[1] if isinstance(child[1], str) else "F.Cu"

            elif tag == "tstamp" and len(child) >= 2:
                tstamp = child[1] if isinstance(child[1], str) else ""

            elif tag == "fp_text" and len(child) >= 3:
                kind = child[1]
                val  = child[2] if isinstance(child[2], str) else ""
                if kind == "reference":
                    ref = val
                elif kind == "value":
                    value = val

        if not ref:
            ref = f"FP{pcb_comp_index}"

        scid = f"sc_{_slugify(ref)}"
        # emit source_component once per unique ref
        if scid not in sc_seen:
            sc_seen.add(scid)
            cj.append({
                "type": "source_component",
                "source_component_id": scid,
                "name": ref,
                "value": value,
                "footprint": fp_name,
            })

        layer_cj = _KICAD_TO_CJ_LAYER.get(layer_kicad, "top_copper")
        pcb_cid = tstamp if tstamp else f"pcb_{_slugify(ref)}_{pcb_comp_index}"
        cj.append({
            "type": "pcb_component",
            "pcb_component_id": pcb_cid,
            "source_component_id": scid,
            "x": x,
            "y": y,
            "rotation": rot,
            "layer": layer_cj,
        })
        pcb_comp_index += 1

    # ── Segments ──────────────────────────────────────────────────────────────
    seg_index = 0
    # Group segments by net to create pcb_trace entries
    net_segments: dict[str, list[dict]] = {}

    for node in nodes:
        if not isinstance(node, list) or not node or node[0] != "segment":
            continue

        sx = sy = ex = ey = 0.0
        width = 0.2
        seg_layer = "F.Cu"
        net_idx = 0

        for child in node[1:]:
            if not isinstance(child, list) or not child:
                continue
            tag = child[0]
            if tag == "start" and len(child) >= 3:
                try:
                    sx = float(child[1]); sy = float(child[2])
                except (ValueError, TypeError):
                    pass
            elif tag == "end" and len(child) >= 3:
                try:
                    ex = float(child[1]); ey = float(child[2])
                except (ValueError, TypeError):
                    pass
            elif tag == "width" and len(child) >= 2:
                try:
                    width = float(child[1])
                except (ValueError, TypeError):
                    pass
            elif tag == "layer" and len(child) >= 2:
                seg_layer = child[1] if isinstance(child[1], str) else "F.Cu"
            elif tag == "net" and len(child) >= 2:
                try:
                    net_idx = int(child[1])
                except (ValueError, TypeError):
                    pass

        net_name = net_index_to_name.get(net_idx, "")
        key = f"{net_name}|{seg_layer}|{width}"
        if key not in net_segments:
            net_segments[key] = []
        net_segments[key].append({
            "start": {"x": sx, "y": sy},
            "end": {"x": ex, "y": ey},
            "layer": _KICAD_TO_CJ_LAYER.get(seg_layer, "top_copper"),
            "width": width,
            "net_name": net_name,
        })
        seg_index += 1

    for key, segs in net_segments.items():
        net_name = segs[0]["net_name"]
        layer_cj = segs[0]["layer"]
        width    = segs[0]["width"]
        stid = f"st_{_slugify(net_name)}_{_slugify(key[:20])}" if net_name else f"st_{seg_index}"

        # Build route: chain endpoints
        route = []
        for seg in segs:
            route.append(seg["start"])
            route.append(seg["end"])

        net_ids = []
        if net_name and net_name in net_name_to_id:
            net_ids = [net_name_to_id[net_name]]

        cj.append({
            "type": "pcb_trace",
            "pcb_trace_id": f"pcbt_{_slugify(key[:20])}",
            "source_trace_id": stid,
            "route": route,
            "width": width,
            "layer": layer_cj,
        })
        if net_ids:
            cj.append({
                "type": "source_trace",
                "source_trace_id": stid,
                "connected_source_port_ids": [],
                "connected_source_net_ids": net_ids,
            })

    return cj


# ─── Utility ───────────────────────────────────────────────────────────────────

def _slugify(s: str) -> str:
    """Convert a string to a safe identifier fragment (lowercase, underscores)."""
    return re.sub(r"[^a-zA-Z0-9]", "_", s).lower()
