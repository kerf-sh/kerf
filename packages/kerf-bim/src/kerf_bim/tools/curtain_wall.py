"""
curtain_wall.py — LLM tools for parametric curtain wall (Revit-style panel grid).

Curtain walls are stored as files with kind='curtain_wall' and a JSON payload.
"""

import json
import math
import uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def _default_curtain_wall(base_curve_or_wall_id):
    return {
        "version": 1,
        "name": "Curtain Wall",
        "base_curve_or_wall_id": base_curve_or_wall_id,
        "height_mm": 3000,
        "u_divisions": [{"type": "count", "value": 4}],
        "v_divisions": [{"type": "count", "value": 6}],
        "panel_type": {
            "kind": "glass",
            "material_id": None,
            "color": None,
        },
        "mullion_type": {
            "profile": "square",
            "size_mm": 50,
            "color": None,
        },
        "top_rail": {
            "profile": "square",
            "size_mm": 50,
            "visible": True,
        },
        "bottom_rail": {
            "profile": "square",
            "size_mm": 50,
            "visible": True,
        },
    }


def _validate_curtain_wall_doc(doc):
    errors = []
    if doc.get("version") != 1:
        errors.append("version must be 1")

    h = doc.get("height_mm")
    if not isinstance(h, (int, float)) or h <= 0:
        errors.append("height_mm must be a positive number")

    for axis in ["u_divisions", "v_divisions"]:
        divs = doc.get(axis, [])
        if not isinstance(divs, list) or len(divs) == 0:
            errors.append(f"{axis} must be a non-empty array")
            continue
        for i, d in enumerate(divs):
            if not isinstance(d, dict):
                errors.append(f"{axis}[{i}] must be an object")
                continue
            if d.get("type") not in ("count", "spacing", "mixed"):
                errors.append(f"{axis}[{i}].type must be 'count', 'spacing', or 'mixed'")
            if d.get("type") == "count":
                v = d.get("value")
                if not isinstance(v, int) or v < 1:
                    errors.append(f"{axis}[{i}].value must be a positive integer for type='count'")
            if d.get("type") == "spacing":
                v = d.get("value")
                if not isinstance(v, (int, float)) or v <= 0:
                    errors.append(f"{axis}[{i}].value must be a positive number for type='spacing'")

    pt = doc.get("panel_type", {})
    if pt.get("kind") not in ("glass", "solid", "opening"):
        errors.append("panel_type.kind must be 'glass', 'solid', or 'opening'")

    mt = doc.get("mullion_type", {})
    if mt.get("profile") not in ("square", "round"):
        errors.append("mullion_type.profile must be 'square' or 'round'")
    if not isinstance(mt.get("size_mm"), (int, float)) or mt.get("size_mm", 0) <= 0:
        errors.append("mullion_type.size_mm must be a positive number")

    return errors


def _read_curtain_wall(ctx, file_id):
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
            file_id, ctx.project_id,
        )
        if not row:
            return None, "NOT_FOUND"
        content, kind = row
        if kind != "curtain_wall":
            return None, f"expected kind=curtain_wall, got {kind}"
        doc = json.loads(content) if content and content.strip() else {}
        return doc, None
    except Exception as e:
        return None, str(e)


def _write_curtain_wall(ctx, file_id, doc):
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


def _create_file(ctx, file_id, doc):
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "insert into files (id, project_id, kind, content, created_at, updated_at) "
            "values ($1, $2, 'curtain_wall', $3, now(), now())",
            file_id, ctx.project_id, body,
        )
        return None
    except Exception as e:
        return str(e)


def _set_division_scheme(doc, axis, divisions):
    key = "u_divisions" if axis == "u" else "v_divisions"
    return {**doc, key: divisions}


def _set_panel_type(doc, panel_type_obj):
    return {**doc, "panel_type": {**doc.get("panel_type", {}), **panel_type_obj}}


def _set_mullion_type(doc, mullion_type_obj):
    return {**doc, "mullion_type": {**doc.get("mullion_type", {}), **mullion_type_obj}}


# ── create_curtain_wall ─────────────────────────────────────────────────────────

create_curtain_wall_spec = ToolSpec(
    name="create_curtain_wall",
    description=(
        "Create a parametric curtain wall file attached to a base curve or wall. "
        "u_divisions and v_divisions control the panel grid."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Optional UUID for the new curtain wall file."},
            "base_curve_or_wall_id": {"type": "string", "description": "ID of the base curve or wall to attach to."},
            "height_mm": {"type": "number", "description": "Wall height in mm (default 3000)."},
            "u_divisions": {
                "type": "array",
                "description": "Array of division specs for u-direction (along base curve).",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["count", "spacing", "mixed"]},
                        "value": {},
                    },
                    "required": ["type", "value"],
                },
            },
            "v_divisions": {
                "type": "array",
                "description": "Array of division specs for v-direction (height).",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["count", "spacing", "mixed"]},
                        "value": {},
                    },
                    "required": ["type", "value"],
                },
            },
            "panel_kind": {"type": "string", "enum": ["glass", "solid", "opening"], "description": "Panel type (default glass)."},
        },
        "required": ["base_curve_or_wall_id"],
    },
)


@register(create_curtain_wall_spec, write=True)
async def run_create_curtain_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    base_id = a.get("base_curve_or_wall_id", "")
    if not base_id:
        return err_payload("base_curve_or_wall_id is required", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id) if raw_id else uuid.uuid4()
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc = _default_curtain_wall(base_id)
    doc["height_mm"] = float(a.get("height_mm", 3000))

    if "u_divisions" in a:
        doc["u_divisions"] = a["u_divisions"]
    if "v_divisions" in a:
        doc["v_divisions"] = a["v_divisions"]
    if "panel_kind" in a:
        doc["panel_type"]["kind"] = a["panel_kind"]

    err = _create_file(ctx, fid, doc)
    if err:
        return err_payload(f"create file: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "height_mm": doc["height_mm"]})


# ── set_curtain_wall_division ────────────────────────────────────────────────────

set_curtain_wall_division_spec = ToolSpec(
    name="set_curtain_wall_division",
    description="Update u or v division scheme on an existing curtain wall file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the curtain wall file."},
            "axis": {"type": "string", "enum": ["u", "v"], "description": "Which axis to set."},
            "divisions": {
                "type": "array",
                "description": "Array of division specs.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["count", "spacing", "mixed"]},
                        "value": {},
                    },
                    "required": ["type", "value"],
                },
            },
        },
        "required": ["file_id", "axis", "divisions"],
    },
)


@register(set_curtain_wall_division_spec, write=True)
async def run_set_curtain_wall_division(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    axis = a.get("axis")
    if axis not in ("u", "v"):
        return err_payload("axis must be 'u' or 'v'", "BAD_ARGS")

    divisions = a.get("divisions")
    if not isinstance(divisions, list) or len(divisions) == 0:
        return err_payload("divisions must be a non-empty array", "BAD_ARGS")

    doc, err = _read_curtain_wall(ctx, fid)
    if err:
        return err_payload(f"read curtain wall: {err}", "NOT_FOUND")

    doc = _set_division_scheme(doc, axis, divisions)

    err = _write_curtain_wall(ctx, fid, doc)
    if err:
        return err_payload(f"write curtain wall: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "axis": axis, "divisions": divisions})


# ── set_curtain_wall_panel_type ──────────────────────────────────────────────────

set_curtain_wall_panel_type_spec = ToolSpec(
    name="set_curtain_wall_panel_type",
    description="Update panel type on an existing curtain wall file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the curtain wall file."},
            "panel_type": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["glass", "solid", "opening"]},
                    "material_id": {"type": "string"},
                    "color": {"type": "string"},
                },
                "required": ["kind"],
            },
        },
        "required": ["file_id", "panel_type"],
    },
)


@register(set_curtain_wall_panel_type_spec, write=True)
async def run_set_curtain_wall_panel_type(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    panel_type = a.get("panel_type", {})
    if not isinstance(panel_type, dict):
        return err_payload("panel_type must be an object", "BAD_ARGS")
    if panel_type.get("kind") not in ("glass", "solid", "opening"):
        return err_payload("panel_type.kind must be 'glass', 'solid', or 'opening'", "BAD_ARGS")

    doc, err = _read_curtain_wall(ctx, fid)
    if err:
        return err_payload(f"read curtain wall: {err}", "NOT_FOUND")

    doc = _set_panel_type(doc, panel_type)

    err = _write_curtain_wall(ctx, fid, doc)
    if err:
        return err_payload(f"write curtain wall: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "panel_type": doc["panel_type"]})


# ── set_curtain_wall_mullion_type ────────────────────────────────────────────────

set_curtain_wall_mullion_type_spec = ToolSpec(
    name="set_curtain_wall_mullion_type",
    description="Update mullion type on an existing curtain wall file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the curtain wall file."},
            "mullion_type": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "enum": ["square", "round"]},
                    "size_mm": {"type": "number"},
                    "color": {"type": "string"},
                },
                "required": ["profile", "size_mm"],
            },
        },
        "required": ["file_id", "mullion_type"],
    },
)


@register(set_curtain_wall_mullion_type_spec, write=True)
async def run_set_curtain_wall_mullion_type(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    mullion_type = a.get("mullion_type", {})
    if not isinstance(mullion_type, dict):
        return err_payload("mullion_type must be an object", "BAD_ARGS")
    if mullion_type.get("profile") not in ("square", "round"):
        return err_payload("mullion_type.profile must be 'square' or 'round'", "BAD_ARGS")
    if not isinstance(mullion_type.get("size_mm"), (int, float)) or mullion_type.get("size_mm") <= 0:
        return err_payload("mullion_type.size_mm must be a positive number", "BAD_ARGS")

    doc, err = _read_curtain_wall(ctx, fid)
    if err:
        return err_payload(f"read curtain wall: {err}", "NOT_FOUND")

    doc = _set_mullion_type(doc, mullion_type)

    err = _write_curtain_wall(ctx, fid, doc)
    if err:
        return err_payload(f"write curtain wall: {err}", "ERROR")

    return ok_payload({"file_id": str(fid), "mullion_type": doc["mullion_type"]})


# ── validate_curtain_wall ─────────────────────────────────────────────────────────

validate_curtain_wall_spec = ToolSpec(
    name="validate_curtain_wall",
    description="Validate a curtain wall file for schema correctness.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the curtain wall file."},
        },
        "required": ["file_id"],
    },
)


@register(validate_curtain_wall_spec, write=False)
async def run_validate_curtain_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_id = a.get("file_id", "").strip()
    try:
        fid = uuid.UUID(raw_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_curtain_wall(ctx, fid)
    if err:
        return err_payload(f"read curtain wall: {err}", "NOT_FOUND")

    errors = _validate_curtain_wall_doc(doc)
    ok = len(errors) == 0
    return ok_payload({"ok": ok, "errors": errors})
