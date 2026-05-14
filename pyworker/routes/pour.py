"""
Copper pour fill computation.

POST /compute-pour-fill
Body: {
    "pour": {
        "polygon": [{"x": float, "y": float}, ...],
        "layer": str,        // "top_copper" | "bottom_copper" | "inner_1" | ...
        "net_id": str,
        "clearance_mm": float,
        "thermal_relief": {"gap": float, "spoke_width": float, "spoke_count": int},
        "min_thickness_mm": float,
        "priority": int
    },
    "board_state": {
        "traces": [...],     // list of trace objects: {points:[{x,y}], net_id}
        "pads": [...]        // list of pad objects: {x, y, layer, net_id, diameter_mm}
    }
}

Returns:
{
    "filled_polygon": {"outer": [[x,y],...], "holes": [[[x,y],...], ...]},
    "thermal_spokes": [{"pad_x": x, "pad_y": y, "spokes": [{"x1","y1","x2","y2"}, ...]}, ...]
}
"""
import math

from fastapi import APIRouter, HTTPException

try:
    from shapely.geometry import Polygon, LineString, Point, MultiPolygon
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

router = APIRouter()


def _clearance_union(traces, pads, pour_net, clearance_mm):
    """Build a shapely geometry for all clearance areas (traces + non-net pads)."""
    if not SHAPELY_AVAILABLE:
        return None
    obstacles = []
    # Traces not on pour net — buffer by clearance
    for trace in traces:
        if trace.get("net_id", "") == pour_net:
            continue
        pts = trace.get("points", [])
        if len(pts) >= 2:
            coords = [(p.get("x", 0), p.get("y", 0)) for p in pts]
            ls = LineString(coords)
            obstacles.append(ls.buffer(clearance_mm))
    # Pads not on pour net — buffer by pad radius + clearance
    for pad in pads:
        if pad.get("net_id", "") == pour_net:
            continue
        px = pad.get("x", 0)
        py = pad.get("y", 0)
        r = pad.get("diameter_mm", 1.0) / 2.0 + clearance_mm
        obstacles.append(Point(px, py).buffer(r))
    if not obstacles:
        return None
    return unary_union(obstacles)


def _thermal_spokes(pad, spoke_count, gap, spoke_width):
    """Generate thermal relief spokes for a pad on the same net as the pour."""
    px = pad.get("x", 0)
    py = pad.get("y", 0)
    r = pad.get("diameter_mm", 1.0) / 2.0
    spokes = []
    for i in range(spoke_count):
        angle = math.radians(i * 360.0 / spoke_count)
        # Spoke: from just outside the pad hole outward into the pour
        x1 = px + (r + gap) * math.cos(angle)
        y1 = py + (r + gap) * math.sin(angle)
        x2 = px + (r + gap + spoke_width * 4) * math.cos(angle)
        y2 = py + (r + gap + spoke_width * 4) * math.sin(angle)
        spokes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return spokes


@router.post("/compute-pour-fill")
async def compute_pour_fill(req: dict):
    pour = req.get("pour")
    board_state = req.get("board_state", {})

    if not pour:
        raise HTTPException(status_code=400, detail="pour is required")

    polygon_pts = pour.get("polygon", [])
    if len(polygon_pts) < 3:
        raise HTTPException(status_code=400, detail="polygon must have at least 3 points")

    pour_net = pour.get("net_id", "")
    clearance_mm = pour.get("clearance_mm", 0.25)
    thermal = pour.get("thermal_relief", {})
    spoke_count = int(thermal.get("spoke_count", 4))
    spoke_width = float(thermal.get("spoke_width", 0.5))
    gap = float(thermal.get("gap", 0.25))

    traces = board_state.get("traces", [])
    pads = board_state.get("pads", [])

    # Shapely unavailable — return the raw boundary polygon with a warning
    if not SHAPELY_AVAILABLE:
        outer = [[p.get("x", 0), p.get("y", 0)] for p in polygon_pts]
        return {
            "filled_polygon": {"outer": outer, "holes": []},
            "thermal_spokes": [],
            "warning": "shapely not installed; returning boundary polygon only",
        }

    # Build the base polygon
    base_coords = [(p.get("x", 0), p.get("y", 0)) for p in polygon_pts]
    base_poly = Polygon(base_coords)
    if not base_poly.is_valid:
        base_poly = base_poly.buffer(0)  # fix self-intersections

    # Subtract clearance areas
    clearance_geom = _clearance_union(traces, pads, pour_net, clearance_mm)
    filled = base_poly
    if clearance_geom is not None:
        filled = base_poly.difference(clearance_geom)

    # If result is a MultiPolygon (pour split by obstacles), take the largest piece
    if hasattr(filled, "geoms"):
        pieces = list(filled.geoms)
        filled = max(pieces, key=lambda g: g.area) if pieces else base_poly

    outer = list(filled.exterior.coords) if hasattr(filled, "exterior") else list(base_coords)
    holes = (
        [list(interior.coords) for interior in filled.interiors]
        if hasattr(filled, "interiors")
        else []
    )

    # Generate thermal spokes for same-net pads inside the pour
    thermal_spokes = []
    for pad in pads:
        if pad.get("net_id", "") != pour_net:
            continue
        px = pad.get("x", 0)
        py = pad.get("y", 0)
        if base_poly.contains(Point(px, py)):
            spokes = _thermal_spokes(pad, spoke_count, gap, spoke_width)
            thermal_spokes.append({"pad_x": px, "pad_y": py, "spokes": spokes})

    return {
        "filled_polygon": {"outer": outer, "holes": holes},
        "thermal_spokes": thermal_spokes,
    }
