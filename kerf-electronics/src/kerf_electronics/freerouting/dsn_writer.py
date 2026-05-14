from dataclasses import dataclass
from typing import Any


@dataclass
class AutorouteParams:
    trace_width_mm: float = 0.2
    via_diameter_mm: float = 0.6
    via_drill_mm: float = 0.3
    clearance_mm: float = 0.2
    routing_layers: str = "1top,16bot"
    cost_dihedral: float = 90
    cost_via: float = 50


def circuit_to_dsn(circuit: dict, params: AutorouteParams | None = None) -> str:
    if params is None:
        params = AutorouteParams()

    outline = circuit.get("board_outline", [])
    components = circuit.get("components", [])
    nets = circuit.get("nets", [])

    via_dia_mils = params.via_diameter_mm * 39.3701
    via_drill_mils = params.via_drill_mm * 39.3701
    trace_width_mils = params.trace_width_mm * 39.3701
    clearance_mils = params.clearance_mm * 39.3701

    layer_map = _build_layer_map(params.routing_layers)
    layer_count = len(layer_map)

    lines = []
    lines.append("(specctra_schema ses")
    lines.append("  (lefteye_industry)")
    lines.append("  (parser")
    lines.append("    (parser_version \"1.0\")")
    lines.append("  )")
    lines.append("  (library")
    lines.append("    (ladder_eye_industry)")
    lines.append(f"    (trace_width {trace_width_mils})")
    lines.append("    (via {")
    lines.append(f"      via [via] {via_dia_mils} {via_drill_mils}")
    lines.append(f"      clearance {clearance_mils}")
    lines.append("    })")
    lines.append("    (layer")
    for idx, (layer_id, layer_name) in enumerate(layer_map.items()):
        if layer_name == "top":
            layer_type = "component"
        elif layer_name == "bot":
            layer_type = "soldermask"
        else:
            layer_type = "inner"
        lines.append(f"      layer {layer_id} {layer_name} {layer_type}")
    lines.append("    )")
    lines.append("  )")

    lines.append("  (circuit")
    lines.append("    (clarity_eye_industry)")
    lines.append("    (bounds -10000 -10000 1000000 1000000)")
    lines.append("    (route_params")
    lines.append(f"      trace_width {trace_width_mils}")
    lines.append(f"      via {via_dia_mils} {via_drill_mils}")
    lines.append(f"      clearance {clearance_mils}")
    lines.append(f"      cost_via {params.cost_via}")
    lines.append(f"      cost_dihedral {params.cost_dihedral})")
    lines.append("    (layer_rule 1top")
    lines.append("      (active_pin on)")
    lines.append("      (fanout off)")
    lines.append("      (autoroute on)")
    lines.append("      (nets")
    for net in nets:
        net_id = net.get("id", "unnamed")
        lines.append(f"        net {net_id}")
    lines.append("      )")
    lines.append("    )")
    lines.append("    (layer_rule 16bot")
    lines.append("      (active_pin on)")
    lines.append("      (fanout off)")
    lines.append("      (autoroute on)")
    lines.append("    )")

    if outline:
        lines.append("    (outline")
        outline_pts = []
        for pt in outline:
            x, y = pt[0] * 1000, pt[1] * 1000
            outline_pts.append(f"{x} {y}")
        lines.append("      (polygon " + " ".join(outline_pts) + "))")

    lines.append("    (placement")
    for comp in components:
        comp_id = comp.get("id", "U")
        pos = comp.get("position", [0, 0])
        rotation = comp.get("rotation", 0)
        x, y = pos[0] * 1000, pos[1] * 1000
        footprint = comp.get("footprint", "unknown")
        lines.append(f"      component {comp_id} {footprint} {x} {y} R{rotation}")
    lines.append("    )")

    lines.append("    (net")
    for net in nets:
        net_id = net.get("id", "unnamed")
        pins = net.get("pins", [])
        lines.append(f"      net {net_id} (pins")
        for pin in pins:
            comp_id = pin.get("component", "U")
            pin_num = pin.get("pin", 0)
            lines.append(f"        {comp_id}.{pin_num}")
        lines.append("      )")
    lines.append("    )")

    lines.append("  )")
    lines.append(")")

    return "\n".join(lines)


def _build_layer_map(routing_layers: str) -> dict[int, str]:
    layer_map = {}
    parts = routing_layers.split(",")
    for part in parts:
        part = part.strip()
        if part == "1top":
            layer_map[1] = "top"
        elif part == "16bot":
            layer_map[16] = "bot"
        elif part.startswith("2mid"):
            layer_map[2] = "mid1"
        elif part.startswith("3mid"):
            layer_map[3] = "mid2"
        else:
            layer_map[len(layer_map) + 1] = part
    if not layer_map:
        layer_map = {1: "top", 16: "bot"}
    return layer_map


def dsn_to_circuit(dsn: str) -> dict:
    circuit = {
        "board_outline": [],
        "components": [],
        "nets": [],
    }
    return circuit
