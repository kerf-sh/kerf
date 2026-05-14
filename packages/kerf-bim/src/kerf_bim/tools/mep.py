"""mep.py — LLM tools for MEP (Mechanical/Electrical/Plumbing) routing."""

import json
import math
import uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

# ── Schema helpers ────────────────────────────────────────────────────────────

VALID_KINDS = {"duct", "pipe", "conduit"}
VALID_MATERIALS = {
    "galvanized_steel", "stainless_steel", "copper", "pvc", "hdpe", "cast_iron", "concrete"
}

DEFAULT_MATERIAL = {
    "duct": "galvanized_steel",
    "pipe": "copper",
    "conduit": "pvc",
}

DEFAULT_SIZE_MM = {
    "duct": 400,
    "pipe": 50,
    "conduit": 25,
}

FILE_EXTENSION = {
    "duct": "duct.json",
    "pipe": "pipe.json",
    "conduit": "conduit.json",
}


def _default_route(kind: str, system_name: str, size_mm: float | None = None, material: str | None = None) -> dict:
    return {
        "version": 1,
        "kind": kind,
        "system_name": system_name,
        "system_color": "#5da9ff",
        "material": material or DEFAULT_MATERIAL[kind],
        "size_mm": size_mm or DEFAULT_SIZE_MM[kind],
        "width_mm": None,
        "height_mm": None,
        "insulation_thickness_mm": 25 if kind == "duct" else 0,
        "segments": [],
        "fittings": [],
        "endpoints": [],
    }


def _dist3(a, b) -> float:
    return math.sqrt((b[0]-a[0])**2 + (b[1]-a[1])**2 + (b[2]-a[2])**2)


# ── create_mep_route ──────────────────────────────────────────────────────────

create_mep_route_spec = ToolSpec(
    name="create_mep_route",
    description=(
        "Create a new MEP (Mechanical/Electrical/Plumbing) route file. "
        "Creates a .duct.json, .pipe.json, or .conduit.json file in the project. "
        "Returns the new file_id and an empty route skeleton."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["duct", "pipe", "conduit"],
                "description": "Type of MEP route",
            },
            "system_name": {
                "type": "string",
                "description": "System name, e.g. 'Supply Air', 'Domestic Cold Water', 'Power Conduit'",
            },
            "size_mm": {
                "type": "number",
                "description": "Nominal diameter in mm (e.g. 200 for a 200mm duct). For rectangular ducts use width_mm/height_mm instead.",
            },
            "material": {
                "type": "string",
                "enum": ["galvanized_steel", "stainless_steel", "copper", "pvc", "hdpe", "cast_iron", "concrete"],
                "description": "Pipe/duct material",
            },
            "width_mm": {
                "type": "number",
                "description": "Width for rectangular ducts (mm)",
            },
            "height_mm": {
                "type": "number",
                "description": "Height for rectangular ducts (mm)",
            },
            "folder_path": {
                "type": "string",
                "description": "Optional folder path in the project (e.g. '/MEP'). Defaults to '/MEP'.",
            },
        },
        "required": ["kind", "system_name"],
    },
)


@register(create_mep_route_spec, write=True)
async def create_mep_route(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    kind = a.get("kind", "")
    system_name = a.get("system_name", "").strip()

    if kind not in VALID_KINDS:
        return err_payload(f"kind must be one of {sorted(VALID_KINDS)}", "BAD_ARGS")
    if not system_name:
        return err_payload("system_name is required", "BAD_ARGS")

    size_mm = a.get("size_mm") or DEFAULT_SIZE_MM[kind]
    material = a.get("material") or DEFAULT_MATERIAL[kind]
    if material not in VALID_MATERIALS:
        return err_payload(f"material must be one of {sorted(VALID_MATERIALS)}", "BAD_ARGS")

    route = _default_route(kind, system_name, size_mm, material)
    if a.get("width_mm"):
        route["width_mm"] = float(a["width_mm"])
        route["size_mm"] = None
    if a.get("height_mm"):
        route["height_mm"] = float(a["height_mm"])

    folder_path = (a.get("folder_path") or "/MEP").rstrip("/")
    safe_name = system_name.replace(" ", "_").replace("/", "-")
    file_name = f"{safe_name}.{FILE_EXTENSION[kind]}"
    full_path = f"{folder_path}/{file_name}"

    content_json = json.dumps(route, indent=2)

    # Ensure folder exists
    folder_parts = [p for p in folder_path.split("/") if p]
    parent_id = None
    for i, part in enumerate(folder_parts):
        parent_path = "/" + "/".join(folder_parts[:i]) if i > 0 else "/"
        row = await ctx.pool.fetchrow(
            "SELECT id FROM files WHERE project_id=$1 AND path=$2 AND kind='folder' AND deleted_at IS NULL",
            ctx.project_id, parent_path + ("/" if parent_path != "/" else "") + part if parent_path == "/" else f"{parent_path}/{part}",
        )
        if row:
            parent_id = row["id"]
        else:
            parent_id = await ctx.pool.fetchval(
                "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES($1,$2,$3,'folder','{}') RETURNING id",
                ctx.project_id, parent_id, part,
            )

    # Create the file
    file_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES($1,$2,$3,$4,$5) RETURNING id",
        ctx.project_id, parent_id, file_name, kind, content_json,
    )

    return ok_payload({
        "file_id": str(file_id),
        "path": full_path,
        "kind": kind,
        "route": route,
    })


# ── add_mep_segment ───────────────────────────────────────────────────────────

add_mep_segment_spec = ToolSpec(
    name="add_mep_segment",
    description=(
        "Add a segment (straight run, elbow, or vertical drop) to an existing MEP route file. "
        "Coordinates are in mm. Returns the updated route."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .duct.json / .pipe.json / .conduit.json file"},
            "from": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3, "maxItems": 3,
                "description": "[x, y, z] start point in mm",
            },
            "to": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3, "maxItems": 3,
                "description": "[x, y, z] end point in mm",
            },
            "kind": {
                "type": "string",
                "enum": ["straight", "elbow", "vertical"],
                "description": "Segment kind (default: straight)",
            },
            "elbow_radius_mm": {
                "type": "number",
                "description": "Elbow bend radius in mm (required when kind=elbow)",
            },
            "segment_id": {
                "type": "string",
                "description": "Optional explicit segment ID; auto-generated if not provided",
            },
        },
        "required": ["file_id", "from", "to"],
    },
)


@register(add_mep_segment_spec, write=True)
async def add_mep_segment(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    from_pt = a.get("from")
    to_pt = a.get("to")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not from_pt or len(from_pt) != 3:
        return err_payload("from must be [x,y,z]", "BAD_ARGS")
    if not to_pt or len(to_pt) != 3:
        return err_payload("to must be [x,y,z]", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except ValueError:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT id, kind, content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")
    if row["kind"] not in VALID_KINDS:
        return err_payload(f"file is not an MEP route (kind={row['kind']})", "BAD_KIND")

    try:
        route = json.loads(row["content"])
    except Exception:
        return err_payload("failed to parse route content", "PARSE_ERROR")

    seg_id = a.get("segment_id") or f"s_{uuid.uuid4().hex[:8]}"
    existing_ids = {s["id"] for s in route.get("segments", [])}
    if seg_id in existing_ids:
        return err_payload(f"segment id already exists: {seg_id}", "DUPLICATE_ID")

    seg_kind = a.get("kind", "straight")
    segment = {"id": seg_id, "from": from_pt, "to": to_pt, "kind": seg_kind}
    if seg_kind == "elbow" and a.get("elbow_radius_mm"):
        segment["elbow_radius_mm"] = float(a["elbow_radius_mm"])

    route.setdefault("segments", []).append(segment)

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2",
        json.dumps(route, indent=2), fid,
    )

    return ok_payload({"segment_id": seg_id, "route": route})


# ── add_mep_fitting ───────────────────────────────────────────────────────────

add_mep_fitting_spec = ToolSpec(
    name="add_mep_fitting",
    description=(
        "Add a fitting (tee, reducer, transition, cap, or cross) to an MEP route file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": ["tee", "reducer", "transition", "cap", "cross"],
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3, "maxItems": 3,
                "description": "[x, y, z] fitting location in mm",
            },
            "branches": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Segment IDs that connect to this fitting (for tee/cross)",
            },
            "fitting_id": {
                "type": "string",
                "description": "Optional explicit fitting ID",
            },
        },
        "required": ["file_id", "kind", "position"],
    },
)


@register(add_mep_fitting_spec, write=True)
async def add_mep_fitting(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    fitting_kind = a.get("kind", "")
    position = a.get("position")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if fitting_kind not in {"tee", "reducer", "transition", "cap", "cross"}:
        return err_payload("kind must be one of tee, reducer, transition, cap, cross", "BAD_ARGS")
    if not position or len(position) != 3:
        return err_payload("position must be [x,y,z]", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except ValueError:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT id, kind, content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")
    if row["kind"] not in VALID_KINDS:
        return err_payload(f"file is not an MEP route (kind={row['kind']})", "BAD_KIND")

    try:
        route = json.loads(row["content"])
    except Exception:
        return err_payload("failed to parse route content", "PARSE_ERROR")

    fitting_id = a.get("fitting_id") or f"f_{uuid.uuid4().hex[:8]}"
    existing_ids = {f["id"] for f in route.get("fittings", [])}
    if fitting_id in existing_ids:
        return err_payload(f"fitting id already exists: {fitting_id}", "DUPLICATE_ID")

    fitting = {"id": fitting_id, "kind": fitting_kind, "position": position}
    if a.get("branches"):
        fitting["branches"] = a["branches"]

    route.setdefault("fittings", []).append(fitting)

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2",
        json.dumps(route, indent=2), fid,
    )

    return ok_payload({"fitting_id": fitting_id, "route": route})


# ── auto_route_mep ────────────────────────────────────────────────────────────

auto_route_mep_spec = ToolSpec(
    name="auto_route_mep",
    description=(
        "Auto-route an MEP run between two named endpoints using A* pathfinding. "
        "Optionally reads obstacles (walls/floors/columns) from a BIM file. "
        "Populates segments with elbows at turns. Returns the updated route."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "MEP route file UUID"},
            "start_endpoint_id": {"type": "string", "description": "Source endpoint id"},
            "end_endpoint_id": {"type": "string", "description": "Sink endpoint id"},
            "bim_file_id_for_obstacles": {
                "type": "string",
                "description": "Optional BIM file UUID to extract wall/floor obstacles from",
            },
            "grid_size_mm": {
                "type": "number",
                "description": "A* grid cell size in mm (default 300). Smaller = more precise but slower.",
            },
        },
        "required": ["file_id", "start_endpoint_id", "end_endpoint_id"],
    },
)


@register(auto_route_mep_spec, write=True)
async def auto_route_mep(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    start_id = a.get("start_endpoint_id", "")
    end_id = a.get("end_endpoint_id", "")
    grid_mm = float(a.get("grid_size_mm", 300))

    if not file_id or not start_id or not end_id:
        return err_payload("file_id, start_endpoint_id, end_endpoint_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except ValueError:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT id, kind, content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")
    if row["kind"] not in VALID_KINDS:
        return err_payload(f"file is not an MEP route", "BAD_KIND")

    try:
        route = json.loads(row["content"])
    except Exception:
        return err_payload("failed to parse route content", "PARSE_ERROR")

    # Find endpoints
    endpoints_by_id = {ep["id"]: ep for ep in route.get("endpoints", [])}
    if start_id not in endpoints_by_id:
        return err_payload(f"start endpoint not found: {start_id}", "NOT_FOUND")
    if end_id not in endpoints_by_id:
        return err_payload(f"end endpoint not found: {end_id}", "NOT_FOUND")

    start_pos = endpoints_by_id[start_id]["position"]
    end_pos = endpoints_by_id[end_id]["position"]

    # Collect obstacles from BIM file if given
    obstacles = []
    bim_fid = a.get("bim_file_id_for_obstacles")
    if bim_fid:
        try:
            bim_uuid = uuid.UUID(bim_fid)
            bim_row = await ctx.pool.fetchrow(
                "SELECT content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
                bim_uuid, ctx.project_id,
            )
            if bim_row:
                bim = json.loads(bim_row["content"])
                for el in bim.get("elements", []):
                    bbox = el.get("bounding_box")
                    if bbox and "min" in bbox and "max" in bbox:
                        obstacles.append(bbox)
        except Exception:
            pass  # Non-fatal: proceed without obstacles

    # Run A*
    result = _astar_3d(start_pos, end_pos, obstacles, grid_mm)
    polyline = result["polyline"]
    warning = result.get("warning")

    # Build segments
    elbow_r = (route.get("size_mm") or 200) * 1.5
    new_segments = []
    for i in range(len(polyline) - 1):
        frm = polyline[i]
        to = polyline[i + 1]
        is_elbow = i > 0
        is_vertical = (frm[0] == to[0] and frm[1] == to[1] and frm[2] != to[2])
        seg_kind = "vertical" if is_vertical else ("elbow" if is_elbow else "straight")
        seg = {"id": f"s_{uuid.uuid4().hex[:8]}", "from": frm, "to": to, "kind": seg_kind}
        if seg_kind == "elbow":
            seg["elbow_radius_mm"] = elbow_r
        new_segments.append(seg)

    route.setdefault("segments", []).extend(new_segments)

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2",
        json.dumps(route, indent=2), fid,
    )

    resp = {"segments_added": len(new_segments), "route": route}
    if warning:
        resp["warning"] = warning
    return ok_payload(resp)


# ── compute_route_pressure_drop ───────────────────────────────────────────────

compute_route_pressure_drop_spec = ToolSpec(
    name="compute_route_pressure_drop",
    description=(
        "Compute the pressure drop along an MEP route. "
        "For pipes: Darcy-Weisbach with Swamee-Jain friction factor. "
        "For ducts: equivalent-length method at 1 Pa/m. "
        "For conduits: returns 0 (electrical). "
        "Returns pressure drop in Pa and route length in m."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "fluid": {
                "type": "object",
                "description": "Fluid properties (optional). Keys: density_kg_m3 (default 1000), velocity_m_s (default 1.5), viscosity_Pa_s (default 0.001).",
                "properties": {
                    "density_kg_m3": {"type": "number"},
                    "velocity_m_s": {"type": "number"},
                    "viscosity_Pa_s": {"type": "number"},
                },
            },
        },
        "required": ["file_id"],
    },
)

ROUGHNESS_MM = {
    "galvanized_steel": 0.046,
    "stainless_steel": 0.015,
    "copper": 0.0015,
    "pvc": 0.0015,
    "hdpe": 0.007,
    "cast_iron": 0.26,
    "concrete": 1.5,
}


@register(compute_route_pressure_drop_spec, write=False)
async def compute_route_pressure_drop(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except ValueError:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")
    if row["kind"] not in VALID_KINDS:
        return err_payload(f"file is not an MEP route", "BAD_KIND")

    try:
        route = json.loads(row["content"])
    except Exception:
        return err_payload("failed to parse route content", "PARSE_ERROR")

    kind = route.get("kind", row["kind"])
    if kind == "conduit":
        return ok_payload({"pressure_drop_pa": 0.0, "length_m": 0.0, "note": "Conduit: no fluid pressure drop"})

    length_mm = sum(_dist3(s["from"], s["to"]) for s in route.get("segments", []))
    length_m = length_mm / 1000.0

    if length_m == 0:
        return ok_payload({"pressure_drop_pa": 0.0, "length_m": 0.0})

    diameter_m = (route.get("size_mm") or 200) / 1000.0
    fluid = a.get("fluid") or {}
    rho = float(fluid.get("density_kg_m3", 1000))
    v = float(fluid.get("velocity_m_s", 1.5))
    mu = float(fluid.get("viscosity_Pa_s", 0.001))

    if kind == "duct":
        size_correction = 200.0 / (route.get("size_mm") or 200)
        dp = length_m * 1.0 * size_correction
        return ok_payload({
            "pressure_drop_pa": round(dp, 3),
            "length_m": round(length_m, 3),
            "method": "equivalent_length_1Pa_per_m",
        })

    # Darcy-Weisbach for pipe
    Re = (rho * v * diameter_m) / mu
    roughness = ROUGHNESS_MM.get(route.get("material", "galvanized_steel"), 0.046)
    epsilon_D = (roughness / 1000.0) / diameter_m

    if Re < 2300:
        f = 64.0 / Re
    else:
        # Swamee-Jain
        f = 0.25 / (math.log10(epsilon_D / 3.7 + 5.74 / (Re ** 0.9)) ** 2)

    dp = f * (length_m / diameter_m) * (rho * v * v / 2.0)

    return ok_payload({
        "pressure_drop_pa": round(dp, 3),
        "length_m": round(length_m, 3),
        "reynolds_number": round(Re, 1),
        "friction_factor": round(f, 6),
        "method": "darcy_weisbach_swamee_jain",
    })


# ── A* implementation (3D grid) ───────────────────────────────────────────────

def _astar_3d(start, end, obstacles, grid_mm=300):
    """
    3D A* on a coarse grid. Max 100×100×30 grid.
    Returns { polyline: [[x,y,z], ...], warning?: str }
    """
    import heapq

    mins = [min(start[i], end[i]) for i in range(3)]
    maxs = [max(start[i], end[i]) for i in range(3)]

    pad = grid_mm * 3
    origin = [mins[i] - pad for i in range(3)]
    span = [maxs[i] - mins[i] + pad * 2 for i in range(3)]

    gx = int(math.ceil(span[0] / grid_mm)) + 1
    gy = int(math.ceil(span[1] / grid_mm)) + 1
    gz = int(math.ceil(span[2] / grid_mm)) + 1

    if gx > 100 or gy > 100 or gz > 30:
        return {
            "polyline": [start, end],
            "warning": f"Grid too large ({gx}×{gy}×{gz} > 100×100×30); returning straight line.",
        }

    def to_grid(pt):
        return (
            round((pt[0] - origin[0]) / grid_mm),
            round((pt[1] - origin[1]) / grid_mm),
            round((pt[2] - origin[2]) / grid_mm),
        )

    def to_world(gi, gj, gk):
        return [
            origin[0] + gi * grid_mm,
            origin[1] + gj * grid_mm,
            origin[2] + gk * grid_mm,
        ]

    def in_bounds(i, j, k):
        return 0 <= i < gx and 0 <= j < gy and 0 <= k < gz

    # Build obstacle grid
    blocked = [[[False] * gz for _ in range(gy)] for _ in range(gx)]
    for obs in obstacles:
        mn, mx = obs["min"], obs["max"]
        gi0 = max(0, int(math.floor((mn[0] - origin[0]) / grid_mm)))
        gj0 = max(0, int(math.floor((mn[1] - origin[1]) / grid_mm)))
        gk0 = max(0, int(math.floor((mn[2] - origin[2]) / grid_mm)))
        gi1 = min(gx - 1, int(math.ceil((mx[0] - origin[0]) / grid_mm)))
        gj1 = min(gy - 1, int(math.ceil((mx[1] - origin[1]) / grid_mm)))
        gk1 = min(gz - 1, int(math.ceil((mx[2] - origin[2]) / grid_mm)))
        for i in range(gi0, gi1 + 1):
            for j in range(gj0, gj1 + 1):
                for k in range(gk0, gk1 + 1):
                    if in_bounds(i, j, k):
                        blocked[i][j][k] = True

    si, sj, sk = to_grid(start)
    ei, ej, ek = to_grid(end)

    def h(i, j, k):
        return abs(i - ei) + abs(j - ej) + abs(k - ek)

    DIRS = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]

    g_score = {(si, sj, sk): 0}
    came_from = {}
    heap = [(h(si, sj, sk), 0, si, sj, sk)]
    visited = set()

    found = False
    while heap:
        _, g, ci, cj, ck = heapq.heappop(heap)
        node = (ci, cj, ck)
        if node in visited:
            continue
        visited.add(node)
        if node == (ei, ej, ek):
            found = True
            break
        for di, dj, dk in DIRS:
            ni, nj, nk = ci + di, cj + dj, ck + dk
            if not in_bounds(ni, nj, nk):
                continue
            if blocked[ni][nj][nk]:
                continue
            nb = (ni, nj, nk)
            ng = g + 1
            if ng < g_score.get(nb, float("inf")):
                g_score[nb] = ng
                came_from[nb] = node
                heapq.heappush(heap, (ng + h(ni, nj, nk), ng, ni, nj, nk))

    if not found:
        return {
            "polyline": [start, end],
            "warning": "A* could not find a path; returning straight line.",
        }

    # Reconstruct
    path = []
    cur = (ei, ej, ek)
    while cur in came_from:
        path.append(to_world(*cur))
        cur = came_from[cur]
    path.append(to_world(si, sj, sk))
    path.reverse()

    # Simplify collinear
    def simplify(pts):
        if len(pts) <= 2:
            return pts
        result = [pts[0]]
        for i in range(1, len(pts) - 1):
            prev = result[-1]
            cur2 = pts[i]
            nxt = pts[i + 1]
            d1 = [cur2[k] - prev[k] for k in range(3)]
            d2 = [nxt[k] - cur2[k] for k in range(3)]
            cross = [
                d1[1]*d2[2] - d1[2]*d2[1],
                d1[2]*d2[0] - d1[0]*d2[2],
                d1[0]*d2[1] - d1[1]*d2[0],
            ]
            if not all(abs(c) < 1e-9 for c in cross):
                result.append(cur2)
        result.append(pts[-1])
        return result

    return {"polyline": simplify(path)}
