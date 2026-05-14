"""
stairs.py — LLM tools for parametric staircase creation and editing.

Stairs are stored as files with kind='stair' and a JSON payload.
2R+T comfort formula: 2 × riser_height_mm + tread_depth_mm ∈ [550, 700].
"""

import json
import math
import uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ── pure geometry helpers ──────────────────────────────────────────────────────

def _default_stair(total_rise_mm: float, total_run_mm: float) -> dict:
    return {
        "version": 1,
        "total_rise_mm": total_rise_mm,
        "total_run_mm": total_run_mm,
        "tread_depth_mm": 280,
        "riser_height_mm": 175,
        "nosing_mm": 25,
        "width_mm": 1000,
        "flights": [],
        "landings": [],
        "handedness": "right",
    }


def validate_stair_doc(doc: dict) -> list[str]:
    errors = []
    r = doc.get("riser_height_mm")
    t = doc.get("tread_depth_mm")

    if not isinstance(r, (int, float)) or r < 100 or r > 220:
        errors.append(f"riser_height_mm ({r}) must be in [100, 220]")
    if not isinstance(t, (int, float)) or t < 200 or t > 350:
        errors.append(f"tread_depth_mm ({t}) must be in [200, 350]")
    if isinstance(r, (int, float)) and isinstance(t, (int, float)):
        formula = 2 * r + t
        if formula < 550 or formula > 700:
            errors.append(f"2R+T ({formula}) must be in [550, 700]")
    return errors


def _straight_stair(
    total_rise_mm: float,
    total_run_mm: float,
    start_point: list,
    direction: list,
    riser_height_mm: float = 175,
) -> dict:
    step_count = max(1, round(total_rise_mm / riser_height_mm))
    doc = _default_stair(total_rise_mm, total_run_mm)
    doc["riser_height_mm"] = riser_height_mm
    doc["flights"] = [{
        "id": "flight-1",
        "start_point": list(start_point),
        "direction": list(direction),
        "step_count": step_count,
    }]
    return doc


def _l_shape_stair(
    total_rise_mm: float,
    start_point: list,
    leg1_run: float,
    leg2_run: float,
    landing_size: list,
    riser_height_mm: float = 175,
) -> dict:
    steps_per_leg = max(1, round((total_rise_mm / riser_height_mm) / 2))
    sx, sy, sz = start_point

    landing_z = sz + steps_per_leg * riser_height_mm

    doc = _default_stair(total_rise_mm, leg1_run + leg2_run)
    doc["riser_height_mm"] = riser_height_mm
    doc["flights"] = [
        {
            "id": "flight-1",
            "start_point": [sx, sy, sz],
            "direction": [1, 0, 0],
            "step_count": steps_per_leg,
        },
        {
            "id": "flight-2",
            "start_point": [sx + leg1_run, sy, landing_z],
            "direction": [0, 1, 0],
            "step_count": steps_per_leg,
        },
    ]
    doc["landings"] = [{
        "id": "landing-1",
        "position": [sx + leg1_run, sy, landing_z],
        "size_mm": list(landing_size),
    }]
    return doc


def _u_shape_stair(
    total_rise_mm: float,
    start_point: list,
    leg_run: float,
    landing_size: list,
    riser_height_mm: float = 175,
    width_mm: float = 1000,
) -> dict:
    steps_per_leg = max(1, round((total_rise_mm / riser_height_mm) / 2))
    sx, sy, sz = start_point

    landing_z = sz + steps_per_leg * riser_height_mm

    doc = _default_stair(total_rise_mm, leg_run * 2)
    doc["riser_height_mm"] = riser_height_mm
    doc["width_mm"] = width_mm
    doc["flights"] = [
        {
            "id": "flight-1",
            "start_point": [sx, sy, sz],
            "direction": [1, 0, 0],
            "step_count": steps_per_leg,
        },
        {
            "id": "flight-2",
            "start_point": [sx + leg_run, sy + width_mm, landing_z],
            "direction": [-1, 0, 0],
            "step_count": steps_per_leg,
        },
    ]
    doc["landings"] = [{
        "id": "landing-1",
        "position": [sx + leg_run, sy, landing_z],
        "size_mm": list(landing_size),
    }]
    return doc


# ── file I/O helpers ───────────────────────────────────────────────────────────

def _read_stair(ctx: ProjectCtx, file_id: uuid.UUID):
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
            file_id, ctx.project_id,
        )
        if not row:
            return None, "NOT_FOUND"
        content, kind = row
        if kind != "stair":
            return None, f"expected kind=stair, got {kind}"
        doc = json.loads(content) if content and content.strip() else {}
        return doc, None
    except Exception as e:
        return None, str(e)


def _write_stair(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict) -> str | None:
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


def _create_file(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict) -> str | None:
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "insert into files (id, project_id, kind, content, created_at, updated_at) "
            "values ($1, $2, 'stair', $3, now(), now())",
            file_id, ctx.project_id, body,
        )
        return None
    except Exception as e:
        return str(e)


# ── create_stair ───────────────────────────────────────────────────────────────

create_stair_spec = ToolSpec(
    name="create_stair",
    description=(
        "Create a parametric staircase file. "
        "Supports straight, L-shaped (90°), and U-shaped (180°) stairs. "
        "Returns the file_id of the created stair document."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Optional UUID for the new stair file."},
            "total_rise_mm": {"type": "number", "description": "Total vertical rise in mm."},
            "total_run_mm": {"type": "number", "description": "Total horizontal run in mm."},
            "kind": {
                "type": "string",
                "enum": ["straight", "L", "U"],
                "description": "Stair shape: straight, L (90°), or U (180°).",
            },
            "start_point": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] bottom start point in mm.",
            },
            "direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[dx, dy, dz] direction vector for straight stair.",
            },
            "riser_height_mm": {"type": "number", "description": "Riser height mm (default 175)."},
            "tread_depth_mm": {"type": "number", "description": "Tread depth mm (default 280)."},
            "width_mm": {"type": "number", "description": "Stair width mm (default 1000)."},
        },
        "required": ["total_rise_mm", "total_run_mm", "kind", "start_point"],
    },
)


@register(create_stair_spec, write=True)
async def run_create_stair(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    total_rise_mm = a.get("total_rise_mm")
    total_run_mm = a.get("total_run_mm")
    kind = a.get("kind", "straight")
    start_point = a.get("start_point")

    if not isinstance(total_rise_mm, (int, float)) or total_rise_mm <= 0:
        return err_payload("total_rise_mm must be a positive number", "BAD_ARGS")
    if not isinstance(total_run_mm, (int, float)) or total_run_mm <= 0:
        return err_payload("total_run_mm must be a positive number", "BAD_ARGS")
    if kind not in ("straight", "L", "U"):
        return err_payload("kind must be 'straight', 'L', or 'U'", "BAD_ARGS")
    if not isinstance(start_point, list) or len(start_point) != 3:
        return err_payload("start_point must be [x, y, z]", "BAD_ARGS")

    riser_height_mm = float(a.get("riser_height_mm", 175))
    tread_depth_mm = float(a.get("tread_depth_mm", 280))
    width_mm = float(a.get("width_mm", 1000))

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id) if raw_id else uuid.uuid4()
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    if kind == "straight":
        direction = a.get("direction", [1, 0, 0])
        if not isinstance(direction, list) or len(direction) != 3:
            return err_payload("direction must be [dx, dy, dz]", "BAD_ARGS")
        doc = _straight_stair(total_rise_mm, total_run_mm, start_point, direction, riser_height_mm)

    elif kind == "L":
        leg1 = total_run_mm / 2
        leg2 = total_run_mm / 2
        landing_size = [width_mm + 200, width_mm]
        doc = _l_shape_stair(total_rise_mm, start_point, leg1, leg2, landing_size, riser_height_mm)

    else:  # U
        leg_run = total_run_mm / 2
        landing_size = [width_mm + 200, width_mm]
        doc = _u_shape_stair(total_rise_mm, start_point, leg_run, landing_size, riser_height_mm, width_mm)

    doc["tread_depth_mm"] = tread_depth_mm
    doc["width_mm"] = width_mm

    err = _create_file(ctx, fid, doc)
    if err:
        return err_payload(f"create file: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "kind": kind, "flights": len(doc["flights"])})


# ── add_stair_flight ───────────────────────────────────────────────────────────

add_stair_flight_spec = ToolSpec(
    name="add_stair_flight",
    description="Append a new flight to an existing stair file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the stair file."},
            "start": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] start point of flight.",
            },
            "direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[dx, dy, dz] direction vector.",
            },
            "step_count": {"type": "integer", "description": "Number of steps in this flight."},
        },
        "required": ["file_id", "start", "direction", "step_count"],
    },
)


@register(add_stair_flight_spec, write=True)
async def run_add_stair_flight(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    start = a.get("start")
    direction = a.get("direction")
    step_count = a.get("step_count")

    if not isinstance(start, list) or len(start) != 3:
        return err_payload("start must be [x, y, z]", "BAD_ARGS")
    if not isinstance(direction, list) or len(direction) != 3:
        return err_payload("direction must be [dx, dy, dz]", "BAD_ARGS")
    if not isinstance(step_count, int) or step_count <= 0:
        return err_payload("step_count must be a positive integer", "BAD_ARGS")

    doc, err = _read_stair(ctx, fid)
    if err:
        return err_payload(f"read stair: {err}", "NOT_FOUND")

    existing = doc.get("flights", [])
    n = len(existing) + 1
    flight = {
        "id": f"flight-{n}",
        "start_point": [float(v) for v in start],
        "direction": [float(v) for v in direction],
        "step_count": int(step_count),
    }
    doc["flights"] = existing + [flight]

    err = _write_stair(ctx, fid, doc)
    if err:
        return err_payload(f"write stair: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "flight_id": flight["id"], "step_count": step_count})


# ── add_stair_landing ──────────────────────────────────────────────────────────

add_stair_landing_spec = ToolSpec(
    name="add_stair_landing",
    description="Append a landing platform to an existing stair file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the stair file."},
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] corner position of landing.",
            },
            "size_mm": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[width, depth] of landing in mm.",
            },
        },
        "required": ["file_id", "position", "size_mm"],
    },
)


@register(add_stair_landing_spec, write=True)
async def run_add_stair_landing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    position = a.get("position")
    size_mm = a.get("size_mm")

    if not isinstance(position, list) or len(position) != 3:
        return err_payload("position must be [x, y, z]", "BAD_ARGS")
    if not isinstance(size_mm, list) or len(size_mm) != 2:
        return err_payload("size_mm must be [width, depth]", "BAD_ARGS")

    doc, err = _read_stair(ctx, fid)
    if err:
        return err_payload(f"read stair: {err}", "NOT_FOUND")

    existing = doc.get("landings", [])
    n = len(existing) + 1
    landing = {
        "id": f"landing-{n}",
        "position": [float(v) for v in position],
        "size_mm": [float(v) for v in size_mm],
    }
    doc["landings"] = existing + [landing]

    err = _write_stair(ctx, fid, doc)
    if err:
        return err_payload(f"write stair: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "landing_id": landing["id"]})


# ── validate_stair ─────────────────────────────────────────────────────────────

validate_stair_spec = ToolSpec(
    name="validate_stair",
    description=(
        "Validate a stair file against building-code comfort rules. "
        "Checks riser height [100, 220], tread depth [200, 350], and 2R+T [550, 700]."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the stair file."},
        },
        "required": ["file_id"],
    },
)


@register(validate_stair_spec, write=False)
async def run_validate_stair(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_stair(ctx, fid)
    if err:
        return err_payload(f"read stair: {err}", "NOT_FOUND")

    errors = validate_stair_doc(doc)
    ok = len(errors) == 0
    return ok_payload({"ok": ok, "errors": errors})
