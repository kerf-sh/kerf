"""
railings.py — LLM tools for parametric railing and handrail creation.

Railings are stored as files with kind='railing' and a JSON payload.
A railing follows either an explicit path or the edge of a stair.
"""

import json
import math
import uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ── pure helpers ───────────────────────────────────────────────────────────────

def _default_railing(path: list, height_mm: float = 1000) -> dict:
    return {
        "version": 1,
        "path": [{"x": float(p["x"]), "y": float(p["y"]), "z": float(p["z"])} for p in path],
        "height_mm": height_mm,
        "top_rail": {
            "profile": "round",
            "size_mm": 50,
            "offset_mm": 0,
        },
        "posts": {
            "spacing_mm": 1200,
            "profile": "round",
            "size_mm": 40,
            "height_mm": height_mm,
        },
        "balusters": {
            "spacing_mm": 120,
            "profile": "round",
            "size_mm": 14,
            "height_mm": max(0, height_mm - 100),
        },
    }


def validate_railing_doc(doc: dict) -> list[str]:
    errors = []
    path = doc.get("path", [])
    if not isinstance(path, list) or len(path) < 2:
        errors.append("path must have at least 2 points")

    h = doc.get("height_mm")
    if not isinstance(h, (int, float)) or h < 600 or h > 1200:
        errors.append(f"height_mm ({h}) must be in [600, 1200]")

    valid_profiles = {"round", "square", "flat"}
    tr = doc.get("top_rail", {})
    if tr.get("profile") not in valid_profiles:
        errors.append(f"top_rail.profile must be one of {sorted(valid_profiles)}")
    if not isinstance(tr.get("size_mm"), (int, float)) or tr.get("size_mm", 0) <= 0:
        errors.append("top_rail.size_mm must be a positive number")

    posts = doc.get("posts", {})
    if not isinstance(posts.get("spacing_mm"), (int, float)) or posts.get("spacing_mm", 0) <= 0:
        errors.append("posts.spacing_mm must be a positive number")

    bals = doc.get("balusters", {})
    if not isinstance(bals.get("spacing_mm"), (int, float)) or bals.get("spacing_mm", 0) <= 0:
        errors.append("balusters.spacing_mm must be a positive number")

    return errors


def _path_length(path: list) -> float:
    total = 0.0
    for i in range(1, len(path)):
        dx = path[i]["x"] - path[i - 1]["x"]
        dy = path[i]["y"] - path[i - 1]["y"]
        dz = path[i]["z"] - path[i - 1]["z"]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def _interpolate(path: list, t: float) -> dict:
    remaining = t
    for i in range(1, len(path)):
        dx = path[i]["x"] - path[i - 1]["x"]
        dy = path[i]["y"] - path[i - 1]["y"]
        dz = path[i]["z"] - path[i - 1]["z"]
        seg = math.sqrt(dx * dx + dy * dy + dz * dz)
        if remaining <= seg + 1e-9:
            u = remaining / seg if seg > 0 else 0
            return {
                "x": path[i - 1]["x"] + u * dx,
                "y": path[i - 1]["y"] + u * dy,
                "z": path[i - 1]["z"] + u * dz,
            }
        remaining -= seg
    return dict(path[-1])


def compute_post_positions(path: list, spacing: float) -> list:
    if not path or len(path) < 2:
        return []
    total = _path_length(path)
    if total <= 0:
        return [dict(path[0])]
    count = max(2, math.ceil(total / spacing) + 1)
    step = total / (count - 1)
    return [_interpolate(path, i * step) for i in range(count)]


def compute_baluster_positions(path: list, spacing: float) -> list:
    if not path or len(path) < 2:
        return []
    total = _path_length(path)
    if total <= 0:
        return []
    count = math.floor(total / spacing)
    if count <= 0:
        return []
    step = total / (count + 1)
    return [_interpolate(path, i * step) for i in range(1, count + 1)]


def _stair_edge_path(stair: dict, offset: float) -> list:
    """Walk along stair flight nosings and return path points."""
    riser = stair.get("riser_height_mm", 175)
    tread = stair.get("tread_depth_mm", 280)
    pts = []

    for flight in stair.get("flights", []):
        sp = flight["start_point"]
        d = flight["direction"]
        n = flight["step_count"]

        dlen = math.sqrt(d[0] ** 2 + d[1] ** 2) or 1
        ux, uy = d[0] / dlen, d[1] / dlen
        # Perpendicular for lateral offset
        px, py = -uy, ux

        for i in range(n + 1):
            pt = {
                "x": sp[0] + ux * tread * i + px * offset,
                "y": sp[1] + uy * tread * i + py * offset,
                "z": sp[2] + riser * i,
            }
            if not pts or (pts[-1]["x"] != pt["x"] or pts[-1]["y"] != pt["y"] or pts[-1]["z"] != pt["z"]):
                pts.append(pt)

    return pts


# ── file I/O ───────────────────────────────────────────────────────────────────

def _read_railing(ctx, file_id: uuid.UUID):
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
            file_id, ctx.project_id,
        )
        if not row:
            return None, "NOT_FOUND"
        content, kind = row
        if kind != "railing":
            return None, f"expected kind=railing, got {kind}"
        doc = json.loads(content) if content and content.strip() else {}
        return doc, None
    except Exception as e:
        return None, str(e)


def _read_stair(ctx, file_id: uuid.UUID):
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


def _create_file(ctx, file_id: uuid.UUID, doc: dict) -> str | None:
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "insert into files (id, project_id, kind, content, created_at, updated_at) "
            "values ($1, $2, 'railing', $3, now(), now())",
            file_id, ctx.project_id, body,
        )
        return None
    except Exception as e:
        return str(e)


def _write_railing(ctx, file_id: uuid.UUID, doc: dict) -> str | None:
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


# ── create_railing ─────────────────────────────────────────────────────────────

create_railing_spec = ToolSpec(
    name="create_railing",
    description=(
        "Create a parametric railing file from an explicit path. "
        "The path is a list of {x,y,z} points in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Optional UUID for the new railing file."},
            "path": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                    },
                    "required": ["x", "y", "z"],
                },
                "description": "List of {x,y,z} waypoints defining the railing centre-line.",
            },
            "height_mm": {"type": "number", "description": "Top-rail height in mm (default 1000)."},
        },
        "required": ["path"],
    },
)


@register(create_railing_spec, write=True)
async def run_create_railing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path")
    if not isinstance(path, list) or len(path) < 2:
        return err_payload("path must be an array with at least 2 points", "BAD_ARGS")

    for i, p in enumerate(path):
        if not isinstance(p, dict) or not all(k in p for k in ("x", "y", "z")):
            return err_payload(f"path[{i}] must have x, y, z keys", "BAD_ARGS")

    height_mm = float(a.get("height_mm", 1000))

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id) if raw_id else uuid.uuid4()
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc = _default_railing(path, height_mm)
    err = _create_file(ctx, fid, doc)
    if err:
        return err_payload(f"create file: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "points": len(path), "height_mm": height_mm})


# ── railing_from_stair ─────────────────────────────────────────────────────────

railing_from_stair_spec = ToolSpec(
    name="railing_from_stair",
    description=(
        "Generate a railing along the edge(s) of an existing stair. "
        "side = 'left' | 'right' | 'both'. "
        "When side='both', two railing files are created."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stair_file_id": {"type": "string", "description": "UUID of the source stair file."},
            "side": {
                "type": "string",
                "enum": ["left", "right", "both"],
                "description": "Which edge(s) to add railing to.",
            },
            "output_file_id": {
                "type": "string",
                "description": "Optional UUID for the output railing file (ignored when side='both').",
            },
            "height_mm": {"type": "number", "description": "Railing height mm (default 1000)."},
        },
        "required": ["stair_file_id", "side"],
    },
)


@register(railing_from_stair_spec, write=True)
async def run_railing_from_stair(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_stair = a.get("stair_file_id", "").strip()
    try:
        stair_fid = uuid.UUID(raw_stair)
    except Exception:
        return err_payload("stair_file_id must be a valid UUID", "BAD_ARGS")

    side = a.get("side", "right")
    if side not in ("left", "right", "both"):
        return err_payload("side must be 'left', 'right', or 'both'", "BAD_ARGS")

    height_mm = float(a.get("height_mm", 1000))

    stair_doc, err = _read_stair(ctx, stair_fid)
    if err:
        return err_payload(f"read stair: {err}", "NOT_FOUND")

    width_mm = stair_doc.get("width_mm", 1000)

    def make_railing(offset):
        path = _stair_edge_path(stair_doc, offset)
        return _default_railing(path, height_mm)

    if side == "both":
        left_fid = uuid.uuid4()
        right_fid = uuid.uuid4()

        err1 = _create_file(ctx, left_fid, make_railing(0))
        if err1:
            return err_payload(f"create left railing: {err1}", "ERROR")
        err2 = _create_file(ctx, right_fid, make_railing(width_mm))
        if err2:
            return err_payload(f"create right railing: {err2}", "ERROR")

        return ok_payload({
            "side": "both",
            "left_file_id": str(left_fid),
            "right_file_id": str(right_fid),
        })

    raw_out = a.get("output_file_id", "").strip()
    try:
        out_fid = uuid.UUID(raw_out) if raw_out else uuid.uuid4()
    except Exception:
        return err_payload("output_file_id must be a valid UUID", "BAD_ARGS")

    offset = width_mm if side == "right" else 0
    doc = make_railing(offset)
    err = _create_file(ctx, out_fid, doc)
    if err:
        return err_payload(f"create railing: {err}", "ERROR")

    return ok_payload({"file_id": str(out_fid), "side": side, "points": len(doc["path"])})


# ── set_baluster_spacing ───────────────────────────────────────────────────────

set_baluster_spacing_spec = ToolSpec(
    name="set_baluster_spacing",
    description="Update the baluster spacing on an existing railing file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the railing file."},
            "spacing_mm": {"type": "number", "description": "New baluster centre-to-centre spacing in mm."},
        },
        "required": ["file_id", "spacing_mm"],
    },
)


@register(set_baluster_spacing_spec, write=True)
async def run_set_baluster_spacing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    spacing_mm = a.get("spacing_mm")
    if not isinstance(spacing_mm, (int, float)) or spacing_mm <= 0:
        return err_payload("spacing_mm must be a positive number", "BAD_ARGS")

    doc, err = _read_railing(ctx, fid)
    if err:
        return err_payload(f"read railing: {err}", "NOT_FOUND")

    doc.setdefault("balusters", {})["spacing_mm"] = float(spacing_mm)

    err = _write_railing(ctx, fid, doc)
    if err:
        return err_payload(f"write railing: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "spacing_mm": float(spacing_mm)})


# ── validate_railing ───────────────────────────────────────────────────────────

validate_railing_spec = ToolSpec(
    name="validate_railing",
    description="Validate a railing file for structural and code compliance.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the railing file."},
        },
        "required": ["file_id"],
    },
)


@register(validate_railing_spec, write=False)
async def run_validate_railing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_railing(ctx, fid)
    if err:
        return err_payload(f"read railing: {err}", "NOT_FOUND")

    errors = validate_railing_doc(doc)
    ok = len(errors) == 0
    return ok_payload({"ok": ok, "errors": errors})
