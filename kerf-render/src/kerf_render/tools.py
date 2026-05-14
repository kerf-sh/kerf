"""
render.py — LLM tools for Blender Cycles render-quality output.

File format (.render):
  {
    "version": 1,
    "name": "Hero shot",
    "scene_file_id": "<uuid>",
    "camera": {
      "position": [3000, -3000, 2000],
      "target": [0, 0, 500],
      "up": [0, 0, 1],
      "fov_deg": 45,
      "type": "perspective"
    },
    "lights": [...],
    "materials_override": {
      "*": {"kind": "principled", "base_color": "#888888", "roughness": 0.5, "metallic": 0.0}
    },
    "environment": {"kind": "color", "color": "#202020"},
    "render_settings": {
      "resolution": [1920, 1080],
      "samples": 128,
      "denoise": true,
      "output_format": "png"
    }
  }
"""

import json
import math
import uuid
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ─── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_CAMERA = {
    "position": [3000, -3000, 2000],
    "target": [0, 0, 500],
    "up": [0, 0, 1],
    "fov_deg": 45,
    "type": "perspective",
}

DEFAULT_LIGHTS = [
    {
        "id": "key",
        "kind": "sun",
        "direction": [-1, -1, -2],
        "intensity": 5,
        "color": "#ffffff",
    },
    {
        "id": "fill",
        "kind": "area",
        "position": [3000, 2000, 2000],
        "size_mm": 1000,
        "intensity": 2,
        "color": "#e8f0ff",
    },
    {
        "id": "back",
        "kind": "sun",
        "direction": [1, 0.5, -0.5],
        "intensity": 1,
        "color": "#fff0e0",
    },
]

DEFAULT_RENDER_SETTINGS = {
    "resolution": [1920, 1080],
    "samples": 128,
    "denoise": True,
    "output_format": "png",
}


def _default_render_doc(scene_file_id: str, name: str = "Render") -> dict:
    return {
        "version": 1,
        "name": name,
        "scene_file_id": scene_file_id,
        "camera": dict(DEFAULT_CAMERA),
        "lights": [dict(l) for l in DEFAULT_LIGHTS],
        "materials_override": {
            "*": {
                "kind": "principled",
                "base_color": "#888888",
                "roughness": 0.5,
                "metallic": 0.0,
            }
        },
        "environment": {"kind": "color", "color": "#202020"},
        "render_settings": dict(DEFAULT_RENDER_SETTINGS),
    }


def _serialize(doc: dict) -> str:
    return json.dumps(doc, indent=2)


def _parse(s: str) -> dict:
    if not s or not s.strip():
        return _default_render_doc("")
    try:
        return json.loads(s)
    except Exception:
        return _default_render_doc("")


async def _load_render_file(ctx: ProjectCtx, file_id: str):
    """Fetch row from files table by id. Returns (row, doc) or raises."""
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return None, None

    row = await ctx.pool.fetchrow(
        "SELECT id, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return None, None
    doc = _parse(row["content"] or "")
    return row, doc


async def _save_render_file(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict):
    content = _serialize(doc)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        content, file_id, ctx.project_id,
    )
    return content


# ─── create_render ─────────────────────────────────────────────────────────────

create_render_spec = ToolSpec(
    name="create_render",
    description=(
        "Create a new .render file with default 3-point lighting and camera. "
        "Use this as the starting point before tweaking camera or lights."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "scene_file_id": {
                "type": "string",
                "description": "UUID of the feature, mesh, or STEP file to render.",
            },
            "name": {"type": "string", "description": "Human-readable render name."},
            "resolution": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[width, height] in pixels. Default [1920, 1080].",
            },
            "samples": {
                "type": "integer",
                "description": "Cycles samples. Higher = better quality, slower. Default 128.",
            },
            "parent_folder_id": {
                "type": "string",
                "description": "Optional parent folder UUID.",
            },
        },
        "required": ["scene_file_id"],
    },
)


@register(create_render_spec, write=True)
async def create_render(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    scene_file_id = a.get("scene_file_id", "").strip()
    if not scene_file_id:
        return err_payload("scene_file_id is required", "BAD_ARGS")

    name = a.get("name", "Render").strip() or "Render"
    doc = _default_render_doc(scene_file_id, name)

    if a.get("resolution"):
        res = a["resolution"]
        if isinstance(res, list) and len(res) == 2:
            doc["render_settings"]["resolution"] = [int(res[0]), int(res[1])]

    if a.get("samples"):
        doc["render_settings"]["samples"] = int(a["samples"])

    content = _serialize(doc)
    new_id = uuid.uuid4()
    parent_id = a.get("parent_folder_id") or None
    if parent_id:
        try:
            parent_id = uuid.UUID(parent_id)
        except Exception:
            parent_id = None

    safe_name = name.replace("/", "_")
    path_prefix = await ctx.pool.fetchval(
        "SELECT COALESCE(path, '/') FROM files WHERE id = $1 AND project_id = $2",
        parent_id, ctx.project_id,
    ) if parent_id else "/"
    path = path_prefix.rstrip("/") + "/" + safe_name + ".render"

    await ctx.pool.execute(
        """INSERT INTO files (id, project_id, parent_id, name, path, kind, content, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, 'render', $6, now(), now())""",
        new_id, ctx.project_id, parent_id, name + ".render", path, content,
    )

    return ok_payload({
        "file_id": str(new_id),
        "name": name,
        "path": path,
        "scene_file_id": scene_file_id,
    })


# ─── set_render_camera ─────────────────────────────────────────────────────────

set_render_camera_spec = ToolSpec(
    name="set_render_camera",
    description="Update the camera position, target, and field of view on a .render file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] in millimetres.",
            },
            "target": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] look-at point in millimetres.",
            },
            "up": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Up vector, default [0, 0, 1].",
            },
            "fov_deg": {"type": "number", "description": "Horizontal field-of-view in degrees."},
            "type": {
                "type": "string",
                "enum": ["perspective", "ortho"],
            },
        },
        "required": ["file_id", "position", "target"],
    },
)


@register(set_render_camera_spec, write=True)
async def set_render_camera(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row, doc = await _load_render_file(ctx, file_id)
    if row is None:
        return err_payload(f"render file not found: {file_id}", "NOT_FOUND")
    if row["kind"] != "render":
        return err_payload(f"file is not a .render file (kind={row['kind']})", "BAD_KIND")

    cam = doc.setdefault("camera", dict(DEFAULT_CAMERA))
    if a.get("position"):
        cam["position"] = list(a["position"])
    if a.get("target"):
        cam["target"] = list(a["target"])
    if a.get("up"):
        cam["up"] = list(a["up"])
    if a.get("fov_deg") is not None:
        cam["fov_deg"] = float(a["fov_deg"])
    if a.get("type"):
        cam["type"] = a["type"]

    await _save_render_file(ctx, row["id"], doc)
    return ok_payload({"file_id": file_id, "camera": cam})


# ─── add_render_light ──────────────────────────────────────────────────────────

add_render_light_spec = ToolSpec(
    name="add_render_light",
    description=(
        "Add a light to a .render file. "
        "kind: 'sun' (directional), 'area' (soft box), 'point', 'spot'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "id": {"type": "string", "description": "Unique light ID (e.g. 'key', 'fill')."},
            "kind": {
                "type": "string",
                "enum": ["sun", "area", "point", "spot"],
            },
            "direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[dx, dy, dz] for sun lights.",
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] in mm for area/point/spot.",
            },
            "intensity": {"type": "number"},
            "color": {"type": "string", "description": "Hex color e.g. '#ffffff'."},
            "size_mm": {"type": "number", "description": "Area light size in mm."},
        },
        "required": ["file_id", "kind"],
    },
)


@register(add_render_light_spec, write=True)
async def add_render_light(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row, doc = await _load_render_file(ctx, file_id)
    if row is None:
        return err_payload(f"render file not found: {file_id}", "NOT_FOUND")
    if row["kind"] != "render":
        return err_payload(f"file is not a .render file (kind={row['kind']})", "BAD_KIND")

    lights = doc.setdefault("lights", [])
    light_id = a.get("id") or f"light_{len(lights)}"

    light: dict[str, Any] = {"id": light_id, "kind": a["kind"]}
    if a.get("direction"):
        light["direction"] = list(a["direction"])
    if a.get("position"):
        light["position"] = list(a["position"])
    if a.get("intensity") is not None:
        light["intensity"] = float(a["intensity"])
    else:
        light["intensity"] = 5.0
    if a.get("color"):
        light["color"] = a["color"]
    else:
        light["color"] = "#ffffff"
    if a.get("size_mm") is not None:
        light["size_mm"] = float(a["size_mm"])

    lights.append(light)
    await _save_render_file(ctx, row["id"], doc)
    return ok_payload({"file_id": file_id, "light": light, "light_count": len(lights)})


# ─── set_render_material_override ─────────────────────────────────────────────

set_render_material_override_spec = ToolSpec(
    name="set_render_material_override",
    description=(
        "Set a material override on a .render file. "
        "Use target_pattern '*' to override all objects. "
        "material.kind must be 'principled'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "target_pattern": {
                "type": "string",
                "description": "Object name glob. Use '*' for all.",
            },
            "material": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["principled"]},
                    "base_color": {"type": "string"},
                    "roughness": {"type": "number"},
                    "metallic": {"type": "number"},
                    "emission": {"type": "string"},
                    "emission_strength": {"type": "number"},
                    "alpha": {"type": "number"},
                },
                "required": ["kind"],
            },
        },
        "required": ["file_id", "target_pattern", "material"],
    },
)


@register(set_render_material_override_spec, write=True)
async def set_render_material_override(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    pattern = a.get("target_pattern", "").strip()
    material = a.get("material", {})

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not pattern:
        return err_payload("target_pattern is required", "BAD_ARGS")
    if not material.get("kind"):
        return err_payload("material.kind is required", "BAD_ARGS")

    row, doc = await _load_render_file(ctx, file_id)
    if row is None:
        return err_payload(f"render file not found: {file_id}", "NOT_FOUND")
    if row["kind"] != "render":
        return err_payload(f"file is not a .render file (kind={row['kind']})", "BAD_KIND")

    overrides = doc.setdefault("materials_override", {})
    overrides[pattern] = material
    await _save_render_file(ctx, row["id"], doc)
    return ok_payload({"file_id": file_id, "target_pattern": pattern, "material": material})


# ─── run_render ────────────────────────────────────────────────────────────────

run_render_spec = ToolSpec(
    name="run_render",
    description=(
        "Execute a Blender Cycles render for a .render file. "
        "Fetches the referenced geometry, posts to pyworker /run-render, "
        "stores the output PNG/EXR as a derived artifact, and returns an image URL. "
        "Blender must be installed on the worker host."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the .render file to execute.",
            },
        },
        "required": ["file_id"],
    },
)


@register(run_render_spec, write=True)
async def run_render(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row, doc = await _load_render_file(ctx, file_id)
    if row is None:
        return err_payload(f"render file not found: {file_id}", "NOT_FOUND")
    if row["kind"] != "render":
        return err_payload(f"file is not a .render file (kind={row['kind']})", "BAD_KIND")

    scene_file_id = doc.get("scene_file_id", "").strip()
    if not scene_file_id:
        return err_payload("render file has no scene_file_id", "BAD_RENDER")

    # Fetch the scene geometry content
    try:
        scene_uuid = uuid.UUID(scene_file_id)
    except Exception:
        return err_payload(f"invalid scene_file_id: {scene_file_id}", "BAD_RENDER")

    scene_row = await ctx.pool.fetchrow(
        "SELECT id, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        scene_uuid, ctx.project_id,
    )
    if not scene_row:
        return err_payload(f"scene file not found: {scene_file_id}", "NOT_FOUND")

    # Determine mesh format from file kind
    kind_to_fmt = {
        "step": "obj",
        "mesh": "obj",
        "feature": "obj",
        "file": "obj",
    }
    mesh_format = kind_to_fmt.get(scene_row["kind"], "obj")

    # Encode scene content as b64 for pyworker
    import base64
    scene_content = scene_row["content"] or ""
    mesh_b64 = base64.b64encode(scene_content.encode()).decode() if scene_content else ""

    # Build pyworker payload
    payload = dict(doc)
    payload["mesh_b64"] = mesh_b64
    payload["mesh_format"] = mesh_format

    req_url = "http://localhost:9090/run-render"
    try:
        response = ctx.http_client.post(
            req_url,
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
            timeout=660.0,
        )
    except Exception as exc:
        return err_payload(
            f"pyworker unreachable: {exc}. Ensure pyworker is running and Blender is installed.",
            "WORKER_UNAVAILABLE",
        )

    if response.status_code != 200:
        return err_payload(
            f"pyworker returned HTTP {response.status_code}",
            "WORKER_ERROR",
        )

    try:
        engine_resp = response.json()
    except Exception:
        return err_payload("invalid pyworker response (not JSON)", "WORKER_ERROR")

    status = engine_resp.get("status", "error")
    if status == "error":
        return err_payload(
            engine_resp.get("error", "Render failed"),
            "RENDER_ERROR",
        )

    output_b64 = engine_resp.get("output_b64", "")
    out_fmt = engine_resp.get("format", "png")
    render_seconds = engine_resp.get("render_seconds", 0.0)

    # Store output as derived artifact (best-effort)
    image_url = ""
    if output_b64 and ctx.storage:
        try:
            import base64 as _b64
            img_bytes = _b64.b64decode(output_b64)
            artifact_key = f"renders/{ctx.project_id}/{file_id}.{out_fmt}"
            image_url = await ctx.storage.put(artifact_key, img_bytes, content_type=f"image/{out_fmt}")
        except Exception:
            pass  # storage failure is non-fatal; b64 still returned

    return ok_payload({
        "status": "ok",
        "file_id": file_id,
        "output_b64": output_b64,
        "format": out_fmt,
        "render_seconds": render_seconds,
        "image_url": image_url,
    })
