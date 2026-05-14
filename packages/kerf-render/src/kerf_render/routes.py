"""
Blender Cycles render engine route.

POST /run-render
Body: {
    "version": 1,
    "name": str,
    "scene_file_id": str,
    "mesh_b64": str,           # base64 OBJ/STL/GLB bytes
    "mesh_format": str,        # "obj" | "stl" | "glb"
    "camera": {
        "position": [x, y, z],
        "target": [x, y, z],
        "up": [x, y, z],
        "fov_deg": float,
        "type": "perspective" | "ortho"
    },
    "lights": [...],
    "materials_override": {"*": {...}},
    "environment": {"kind": "color", "color": "#202020"} | {"kind": "hdri", ...},
    "render_settings": {
        "resolution": [width, height],
        "samples": int,
        "denoise": bool,
        "output_format": "png" | "exr"
    }
}

Returns: { "output_b64": str, "format": str, "render_seconds": float }
"""

import base64
import os
import shutil
import subprocess
import tempfile
import textwrap
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

router = APIRouter()

_BLENDER_AVAILABLE = shutil.which("blender") is not None


class CameraSettings(BaseModel):
    position: List[float] = Field(default=[3000, -3000, 2000])
    target: List[float] = Field(default=[0, 0, 500])
    up: List[float] = Field(default=[0, 0, 1])
    fov_deg: float = 45.0
    type: str = "perspective"


class LightSettings(BaseModel):
    id: str = ""
    kind: str = "sun"
    direction: Optional[List[float]] = None
    position: Optional[List[float]] = None
    size_mm: Optional[float] = None
    intensity: float = 5.0
    color: str = "#ffffff"


class EnvironmentSettings(BaseModel):
    kind: str = "color"
    color: Optional[str] = "#202020"
    file_id: Optional[str] = None


class RenderSettings(BaseModel):
    resolution: List[int] = Field(default=[1920, 1080])
    samples: int = 128
    denoise: bool = True
    output_format: str = "png"


class RenderRequest(BaseModel):
    version: int = 1
    name: str = "Render"
    scene_file_id: str = ""
    mesh_b64: str = ""
    mesh_format: str = "obj"
    camera: CameraSettings = Field(default_factory=CameraSettings)
    lights: List[Dict[str, Any]] = Field(default_factory=list)
    materials_override: Dict[str, Any] = Field(default_factory=dict)
    environment: Dict[str, Any] = Field(default_factory=lambda: {"kind": "color", "color": "#202020"})
    render_settings: RenderSettings = Field(default_factory=RenderSettings)


def _hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return r, g, b


def _build_blender_script(req: RenderRequest, mesh_path: str, output_path: str) -> str:
    """Build a self-contained Blender Python script as a string."""

    cam = req.camera
    rs = req.render_settings
    env = req.environment

    cam_pos = list(cam.position)
    cam_target = list(cam.target)
    cam_up = list(cam.up)

    # Scale mm → m (Blender native is metres)
    scale = 0.001

    cam_pos_m = [v * scale for v in cam_pos]
    cam_target_m = [v * scale for v in cam_target]

    res_x, res_y = rs.resolution[0], rs.resolution[1]
    samples = rs.samples
    denoise = rs.denoise
    out_fmt = rs.output_format.upper()
    fov_rad = cam.fov_deg * 3.14159265 / 180.0

    # Environment
    env_kind = env.get("kind", "color")
    env_color_hex = env.get("color", "#202020")
    env_r, env_g, env_b = _hex_to_rgb(env_color_hex)

    # Materials override
    mat_override = req.materials_override
    mat_any = mat_override.get("*", {})
    if mat_any:
        mat_base_hex = mat_any.get("base_color", "#888888")
        mat_roughness = float(mat_any.get("roughness", 0.5))
        mat_metallic = float(mat_any.get("metallic", 0.0))
        mat_r, mat_g, mat_b = _hex_to_rgb(mat_base_hex)
    else:
        mat_r, mat_g, mat_b = 0.533, 0.533, 0.533
        mat_roughness = 0.5
        mat_metallic = 0.0

    # Lights block
    lights_lines = []
    for idx, light in enumerate(req.lights):
        kind = light.get("kind", "sun")
        intensity = float(light.get("intensity", 5.0))
        color_hex = light.get("color", "#ffffff")
        lr, lg, lb = _hex_to_rgb(color_hex)

        lights_lines.append(f"    # light {idx}")
        lights_lines.append(f"    bpy.ops.object.light_add(type={repr(kind.upper())}, location=(0,0,0))")
        lights_lines.append(f"    light_obj = bpy.context.active_object")
        lights_lines.append(f"    light_obj.name = {repr(light.get('id', f'light_{idx}'))}")
        lights_lines.append(f"    light_obj.data.energy = {intensity}")
        lights_lines.append(f"    light_obj.data.color = ({lr}, {lg}, {lb})")

        if kind == "sun":
            direction = light.get("direction", [-1, -1, -2])
            # convert direction to rotation: point -Z at direction
            dx, dy, dz = [float(v) for v in direction]
            lights_lines.append(f"    import mathutils")
            lights_lines.append(f"    dir_vec = mathutils.Vector(({dx}, {dy}, {dz})).normalized()")
            lights_lines.append(f"    light_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()")
        elif kind in ("area", "point", "spot"):
            pos = light.get("position", [2000, 2000, 3000])
            pos_m = [float(v) * scale for v in pos]
            lights_lines.append(f"    light_obj.location = ({pos_m[0]}, {pos_m[1]}, {pos_m[2]})")
            if kind == "area" and light.get("size_mm"):
                size_m = float(light["size_mm"]) * scale
                lights_lines.append(f"    light_obj.data.size = {size_m}")

    lights_code = "\n".join(lights_lines) if lights_lines else "    pass  # no lights"

    mesh_fmt = req.mesh_format.lower()
    if mesh_fmt == "obj":
        import_call = f"    bpy.ops.wm.obj_import(filepath={repr(mesh_path)})"
    elif mesh_fmt == "stl":
        import_call = f"    bpy.ops.import_mesh.stl(filepath={repr(mesh_path)})"
    elif mesh_fmt in ("glb", "gltf"):
        import_call = f"    bpy.ops.import_scene.gltf(filepath={repr(mesh_path)})"
    else:
        import_call = f"    bpy.ops.wm.obj_import(filepath={repr(mesh_path)})"

    cam_type_blender = "PERSP" if cam.type == "perspective" else "ORTHO"

    script = textwrap.dedent(f"""\
        import bpy
        import math

        # ── reset ──────────────────────────────────────────────────────────────
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # ── import mesh ────────────────────────────────────────────────────────
{import_call}

        # ── scale imported objects (mm → m) ────────────────────────────────────
        for obj in bpy.context.selected_objects:
            obj.scale = (0.001, 0.001, 0.001)
        bpy.ops.object.transform_apply(scale=True)

        # ── apply material override to all mesh objects ─────────────────────────
        mat = bpy.data.materials.new(name="KerfMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = ({mat_r}, {mat_g}, {mat_b}, 1.0)
            bsdf.inputs["Roughness"].default_value = {mat_roughness}
            bsdf.inputs["Metallic"].default_value = {mat_metallic}
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                obj.data.materials.clear()
                obj.data.materials.append(mat)

        # ── camera ─────────────────────────────────────────────────────────────
        cam_data = bpy.data.cameras.new("KerfCam")
        cam_data.type = '{cam_type_blender}'
        cam_data.lens_unit = 'FOV'
        cam_data.angle = {fov_rad}
        cam_obj = bpy.data.objects.new("KerfCam", cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
        bpy.context.scene.camera = cam_obj

        import mathutils
        cam_pos = mathutils.Vector(({cam_pos_m[0]}, {cam_pos_m[1]}, {cam_pos_m[2]}))
        cam_target = mathutils.Vector(({cam_target_m[0]}, {cam_target_m[1]}, {cam_target_m[2]}))
        cam_obj.location = cam_pos
        direction = cam_target - cam_pos
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = rot_quat.to_euler()

        # ── world background ────────────────────────────────────────────────────
        world = bpy.data.worlds.new("KerfWorld")
        bpy.context.scene.world = world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value = ({env_r}, {env_g}, {env_b}, 1.0)
            bg.inputs["Strength"].default_value = 1.0

        # ── lights ─────────────────────────────────────────────────────────────
{lights_code}

        # ── render settings ─────────────────────────────────────────────────────
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = {samples}
        scene.cycles.use_denoising = {str(denoise)}
        scene.render.resolution_x = {res_x}
        scene.render.resolution_y = {res_y}
        scene.render.image_settings.file_format = '{out_fmt}'
        scene.render.filepath = {repr(output_path)}

        # ── render ──────────────────────────────────────────────────────────────
        bpy.ops.render.render(write_still=True)
    """)
    return script


@router.post("/run-render")
async def run_render(req: RenderRequest):
    """
    Run a Blender Cycles render from a .render scene description.

    Returns {output_b64, format, render_seconds} on success.
    If blender binary is not on PATH, returns a clear error immediately.
    """
    if not _BLENDER_AVAILABLE:
        return {
            "status": "error",
            "output_b64": "",
            "format": req.render_settings.output_format,
            "render_seconds": 0.0,
            "error": (
                "blender binary not found on PATH. "
                "Install Blender and ensure the 'blender' command is accessible. "
                "See https://www.blender.org/download/"
            ),
        }

    out_fmt = req.render_settings.output_format.lower()
    ext = ".png" if out_fmt == "png" else ".exr"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write mesh to tmp file
        mesh_ext = f".{req.mesh_format.lower()}"
        mesh_path = os.path.join(tmpdir, f"scene{mesh_ext}")
        if req.mesh_b64:
            mesh_bytes = base64.b64decode(req.mesh_b64)
            with open(mesh_path, "wb") as f:
                f.write(mesh_bytes)
        else:
            # Minimal fallback: empty OBJ so Blender doesn't crash
            with open(mesh_path, "w") as f:
                f.write("# empty\n")

        output_path = os.path.join(tmpdir, f"render{ext}")
        script_path = os.path.join(tmpdir, "render_script.py")

        script = _build_blender_script(req, mesh_path, output_path)
        with open(script_path, "w") as f:
            f.write(script)

        t0 = time.time()
        try:
            result = subprocess.run(
                ["blender", "-b", "--python", script_path, "-noaudio"],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "output_b64": "",
                "format": out_fmt,
                "render_seconds": 0.0,
                "error": "blender binary not found on PATH.",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "output_b64": "",
                "format": out_fmt,
                "render_seconds": time.time() - t0,
                "error": "Render timed out after 600 seconds.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "output_b64": "",
                "format": out_fmt,
                "render_seconds": time.time() - t0,
                "error": f"subprocess error: {exc}",
            }

        render_seconds = time.time() - t0

        if result.returncode != 0:
            stderr = (result.stderr or "")[-2000:]
            stdout = (result.stdout or "")[-2000:]
            return {
                "status": "error",
                "output_b64": "",
                "format": out_fmt,
                "render_seconds": render_seconds,
                "error": f"Blender exited with code {result.returncode}. stderr: {stderr} stdout: {stdout}",
            }

        # EXR renders may append frame number suffix
        if not os.path.exists(output_path):
            # Try with frame suffix e.g. render0001.png
            candidates = [
                os.path.join(tmpdir, f)
                for f in os.listdir(tmpdir)
                if f.startswith("render") and f.endswith(ext)
            ]
            if candidates:
                output_path = sorted(candidates)[-1]

        if not os.path.exists(output_path):
            return {
                "status": "error",
                "output_b64": "",
                "format": out_fmt,
                "render_seconds": render_seconds,
                "error": f"Render completed but output file not found. stdout: {(result.stdout or '')[-1000:]}",
            }

        with open(output_path, "rb") as f:
            output_b64 = base64.b64encode(f.read()).decode("ascii")

    return {
        "status": "ok",
        "output_b64": output_b64,
        "format": out_fmt,
        "render_seconds": render_seconds,
    }
