import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Route:
    net_id: str
    layer: str
    points: list[tuple[float, float]] = field(default_factory=list)
    width: float = 0.0


@dataclass
class Via:
    net_id: str
    x: float
    y: float
    via_type: str = "via"


@dataclass
class RoutingResult:
    routes: list[Route] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    nets_routed: int = 0
    nets_unrouted: int = 0
    total_segments: int = 0
    total_vias: int = 0


def ses_to_routes(ses: str) -> dict[str, Any]:
    result = RoutingResult()

    net_blocks = re.findall(r'\(net\s+(\S+)\s*\((?:pins|nodes)[^)]*\)(.*?)\)\s*\)', ses, re.DOTALL)

    for net_id, net_content in net_blocks:
        fanout_vias = re.findall(r'\(fanout_via\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s+via\d+\)', net_content)
        for x, y in fanout_vias:
            result.vias.append(Via(net_id=net_id, x=float(x), y=float(y)))

        wire_matches = re.findall(r'\(wire\s+\S+\s+(\S+)\s+\(([\d.]+)\s+([\d.]+)\)\s+\(([\d.]+)\s+([\d.]+)\)\)', net_content)
        for width, x1, y1, x2, y2 in wire_matches:
            result.routes.append(Route(
                net_id=net_id,
                layer="top",
                points=[(float(x1), float(y1)), (float(x2), float(y2))],
                width=float(width),
            ))

        via_placements = re.findall(r'\(via\s+via\d+\s+\(([\d.]+)\s+([\d.]+)\)\)', net_content)
        for x, y in via_placements:
            result.vias.append(Via(net_id=net_id, x=float(x), y=float(y)))

    unrouted_match = re.search(r'unrouted\s+(\d+)', ses)
    if unrouted_match:
        result.nets_unrouted = int(unrouted_match.group(1))

    total_vias_match = re.search(r'vias\s+(\d+)', ses)
    if total_vias_match:
        result.total_vias = int(total_vias_match.group(1))

    total_segments_match = re.search(r'wires\s+(\d+)', ses)
    if total_segments_match:
        result.total_segments = int(total_segments_match.group(1))

    net_count_match = re.search(r'nets\s+(\d+)', ses)
    if net_count_match:
        nets_count = int(net_count_match.group(1))
        result.nets_routed = nets_count - result.nets_unrouted

    return {
        "routes": [
            {
                "net_id": r.net_id,
                "layer": r.layer,
                "points": r.points,
            }
            for r in result.routes
        ],
        "vias": [
            {
                "net_id": v.net_id,
                "x": v.x,
                "y": v.y,
                "type": v.via_type,
            }
            for v in result.vias
        ],
        "nets_routed": result.nets_routed,
        "nets_unrouted": result.nets_unrouted,
        "segments_routed": result.total_segments,
        "vias_placed": result.total_vias,
    }


def parse_ses_file(ses_path: str) -> dict[str, Any]:
    with open(ses_path, "r") as f:
        content = f.read()
    return ses_to_routes(content)
