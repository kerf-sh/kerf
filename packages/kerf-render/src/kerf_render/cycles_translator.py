"""kerf-render: scene translator — Kerf Body -> glTF + materials + Blender script.

This module is the *backend* foundation for the Cycles render pipeline
(task T-106a in the roadmap). It is hermetic: it does **not** import or
require ``bpy``. Instead it produces three artefacts that are consumed
by the Cycles worker (T-106b) at render time:

  1. A binary glTF (``.glb``) blob containing every Face of the input
     :class:`Body` as a separate mesh primitive, tagged with a material
     slot name. Encoded as the standard 12-byte GLB header + JSON chunk
     + BIN chunk per the Khronos glTF 2.0 spec.

  2. A ``materials_dict`` keyed by material-slot name (the *canonical*
     form from :mod:`kerf_render.material_mapping`) with the resolved
     PBR / glass parameters that should be applied. Gemstones include
     ``ior``, ``abbe``, ``dispersion=True`` and the three-term
     Sellmeier coefficients so the Blender script can wire spectral
     dispersion. Metals carry ``base_color``, ``metallic=1.0`` and
     ``roughness``.

  3. A Blender Python script (a *string*; never executed here) that,
     when run inside Blender ``bpy``, will:
        - Import the glTF via ``bpy.ops.import_scene.gltf``
        - Re-build each material as either a Principled BSDF (metals,
          plastics, opaque organics) or a Glass BSDF (gemstones), with
          dispersion enabled on Cycles 4.0+ using the per-gem Abbe
          number / Sellmeier expansion.
        - Configure a camera at the user-specified position aimed at
          the requested target.
        - Add the user-specified lights.
        - Set Cycles as the renderer, configure the output path, and
          (optionally) execute ``bpy.ops.render.render``.

The Body topology is consumed via :class:`kerf_cad_core.geom.brep.Body`
(face list, outer-loop coedge cycle, surface evaluator). Planar faces
are fan-triangulated from the loop vertices; non-planar analytic
surfaces (cylinder, sphere, torus, NURBS) are tessellated on a coarse
parametric grid clipped to the outer-loop bounding box. The result is a
mesh suitable for path-traced rendering -- not for CAM -- so a low
sample density is fine.

------------------------------------------------------------------
GLB BINARY LAYOUT (Khronos glTF 2.0)
------------------------------------------------------------------
12-byte header::

    magic    = 0x46546C67    ("glTF")
    version  = 2
    length   = total file size

Each chunk is preceded by an 8-byte chunk header::

    chunkLength = 4-byte LE uint32, length of chunkData (must be
                  multiple of 4; we pad with spaces for JSON / zeros
                  for BIN)
    chunkType   = 0x4E4F534A ("JSON") or 0x004E4942 ("BIN ")
    chunkData   = chunkLength bytes

------------------------------------------------------------------
PUBLIC API
------------------------------------------------------------------
:func:`translate_body_to_gltf_plus_materials` is the only entry point.
It returns a four-tuple ``(ok, gltf_bytes, materials_dict, script_str)``
with ``ok=True`` on success. On a recoverable failure (missing material
slot, body with zero faces, ...) it returns ``(False, b"", {}, "",
reason=str)`` instead — i.e. a dict-shaped payload. To keep the API
flat for typical callers we also expose
:func:`translate_body_to_gltf_plus_materials_dict` that returns the
combined dict.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from kerf_render.material_mapping import (
    DEFAULT_MATERIAL,
    GEMSTONE_OPTICS,
    canonical_key,
    lookup_material,
    material_kind,
)


# ---------------------------------------------------------------------------
# Scene-spec dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Camera:
    """Camera pose + intrinsics for the generated Blender script."""

    position: Tuple[float, float, float] = (0.0, 0.0, 5.0)
    target:   Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up:       Tuple[float, float, float] = (0.0, 1.0, 0.0)
    fov_deg:  float = 35.0
    name:     str = "Camera"


@dataclass
class Light:
    """A scene light: type in {"sun", "point", "area"}.

    - ``sun``: directional; position interpreted as the *direction* the
      light comes *from* (script normalises and orients accordingly).
    - ``point``: omnidirectional from ``position``; ``size`` ignored.
    - ``area``: rectangular area light; ``size`` is the side length.
    """

    type:      str = "point"
    position:  Tuple[float, float, float] = (5.0, 5.0, 5.0)
    target:    Tuple[float, float, float] = (0.0, 0.0, 0.0)
    color:     Tuple[float, float, float] = (1.0, 1.0, 1.0)
    energy:    float = 1000.0
    size:      float = 1.0
    name:      str = "Light"


@dataclass
class RenderOutput:
    """Render output specification embedded in the Blender script."""

    path:        str = "/tmp/kerf_render.png"
    resolution:  Tuple[int, int] = (1920, 1080)
    samples:     int = 256
    engine:      str = "CYCLES"
    device:      str = "GPU"
    film_transparent: bool = False


# ---------------------------------------------------------------------------
# Body -> per-face mesh tessellation
# ---------------------------------------------------------------------------


@dataclass
class _FaceMesh:
    """Triangulated mesh for one Face, plus its material slot."""

    name:           str
    vertices:       np.ndarray              # (V, 3) float32
    normals:        np.ndarray              # (V, 3) float32
    indices:        np.ndarray              # (T*3,) uint32
    material_slot:  str = "default"
    face_id:        int = 0


def _loop_polygon_3d(loop, curve_samples: int = 24) -> List[np.ndarray]:
    """Return the loop's vertex polygon as a list of 3-vectors (no duplicates).

    For loops whose coedges trace a *parametric* curve (e.g. the circle
    around a cylinder cap), we sample each coedge along the underlying
    curve so that the resulting polygon actually approximates the
    boundary geometry — not just the discrete vertex endpoints.
    """
    pts: List[np.ndarray] = []

    def _append(p: np.ndarray) -> None:
        if not pts or np.linalg.norm(p - pts[-1]) > 1e-9:
            pts.append(p)

    for ce in loop.coedges:
        edge = ce.edge
        t0, t1 = edge.t0, edge.t1
        # Detect a parametric curve worth sampling (circle / NURBS / etc.):
        curve_type = type(edge.curve).__name__
        is_curve = curve_type not in {"Line3"}
        if is_curve:
            # sample N intermediate points along the curve; respect coedge orientation
            ts = np.linspace(float(t0), float(t1), curve_samples + 1)
            samples = [np.asarray(edge.point(float(t)), dtype=float) for t in ts]
            if not ce.orientation:
                samples = list(reversed(samples))
            # avoid duplicating the previous coedge's last point
            for p in samples[:-1]:
                _append(p)
        else:
            _append(np.asarray(ce.start_point(), dtype=float))

    # drop trailing dup of starting point if present
    if len(pts) >= 2 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts.pop()
    return pts


def _is_planar_surface(surface) -> bool:
    name = type(surface).__name__
    return name == "Plane"


def _is_analytic_surface(surface) -> bool:
    """Surfaces whose ``evaluate(u, v)`` we can sample on a regular grid."""
    name = type(surface).__name__
    return name in {"CylinderSurface", "SphereSurface", "TorusSurface"}


def _face_normal_from_polygon(pts: List[np.ndarray]) -> np.ndarray:
    """Newell's method — robust face normal for a (possibly non-planar) loop."""
    if len(pts) < 3:
        return np.array([0.0, 0.0, 1.0])
    n = np.zeros(3)
    m = len(pts)
    for i in range(m):
        a = pts[i]
        b = pts[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    norm = np.linalg.norm(n)
    if norm < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    return n / norm


def _fan_triangulate(pts: List[np.ndarray]) -> List[Tuple[int, int, int]]:
    """Fan triangulation from vertex 0 — fine for convex / mildly concave loops."""
    return [(0, i, i + 1) for i in range(1, len(pts) - 1)]


def _tessellate_planar_face(face, face_idx: int, material_slot: str) -> _FaceMesh:
    outer = face.outer_loop()
    pts = _loop_polygon_3d(outer)
    if len(pts) < 3:
        # degenerate face — emit a zero-tri mesh
        return _FaceMesh(
            name=f"face_{face_idx}",
            vertices=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material_slot=material_slot,
            face_id=face.id,
        )
    n = _face_normal_from_polygon(pts)
    if not face.orientation:
        n = -n
    tris = _fan_triangulate(pts)
    verts = np.asarray(pts, dtype=np.float32)
    normals = np.tile(n.astype(np.float32), (len(pts), 1))
    idx = np.asarray(tris, dtype=np.uint32).reshape(-1)
    # ensure CCW wrt outward normal
    if len(tris) >= 1:
        a, b, c = verts[tris[0][0]], verts[tris[0][1]], verts[tris[0][2]]
        tri_n = np.cross(b - a, c - a)
        if np.dot(tri_n, n) < 0:
            # flip winding
            idx = idx.reshape(-1, 3)[:, ::-1].reshape(-1).astype(np.uint32)
    return _FaceMesh(
        name=f"face_{face_idx}",
        vertices=verts,
        normals=normals,
        indices=idx,
        material_slot=material_slot,
        face_id=face.id,
    )


def _tessellate_analytic_face(
    face,
    face_idx: int,
    material_slot: str,
    *,
    u_samples: int = 24,
    v_samples: int = 12,
) -> _FaceMesh:
    """Coarse parametric-grid tessellation for cylinder/sphere/torus faces."""
    surf = face.surface
    name = type(surf).__name__
    # parametric extents
    if name == "CylinderSurface":
        u0, u1 = 0.0, 2.0 * math.pi
        # try to infer height from incident edges if possible
        try:
            outer = face.outer_loop()
            pts = _loop_polygon_3d(outer)
            heights = [np.dot(np.asarray(p) - np.asarray(surf.center),
                              np.asarray(surf.axis)) for p in pts]
            v0, v1 = float(min(heights)), float(max(heights))
            if v1 - v0 < 1e-6:
                v0, v1 = 0.0, 1.0
        except Exception:
            v0, v1 = 0.0, 1.0
    elif name == "SphereSurface":
        u0, u1 = 0.0, 2.0 * math.pi
        v0, v1 = -0.5 * math.pi, 0.5 * math.pi
    elif name == "TorusSurface":
        u0, u1 = 0.0, 2.0 * math.pi
        v0, v1 = 0.0, 2.0 * math.pi
    else:
        # generic fallback — unit param square
        u0, u1, v0, v1 = 0.0, 1.0, 0.0, 1.0

    us = np.linspace(u0, u1, u_samples + 1)
    vs = np.linspace(v0, v1, v_samples + 1)
    verts: List[np.ndarray] = []
    normals: List[np.ndarray] = []
    for v in vs:
        for u in us:
            p = np.asarray(surf.evaluate(float(u), float(v)), dtype=np.float32)
            n = np.asarray(surf.normal(float(u), float(v)) if hasattr(surf, "normal")
                           else np.array([0.0, 0.0, 1.0]), dtype=np.float32)
            if not face.orientation:
                n = -n
            verts.append(p)
            normals.append(n)
    nu = u_samples + 1
    tris: List[int] = []
    for j in range(v_samples):
        for i in range(u_samples):
            a = j * nu + i
            b = j * nu + (i + 1)
            c = (j + 1) * nu + (i + 1)
            d = (j + 1) * nu + i
            tris.extend([a, b, c, a, c, d])
    return _FaceMesh(
        name=f"face_{face_idx}",
        vertices=np.asarray(verts, dtype=np.float32),
        normals=np.asarray(normals, dtype=np.float32),
        indices=np.asarray(tris, dtype=np.uint32),
        material_slot=material_slot,
        face_id=face.id,
    )


def _tessellate_face(face, face_idx: int, material_slot: str) -> _FaceMesh:
    if _is_planar_surface(face.surface):
        return _tessellate_planar_face(face, face_idx, material_slot)
    if _is_analytic_surface(face.surface):
        return _tessellate_analytic_face(face, face_idx, material_slot)
    # NurbsSurface / unknown — fall through to a coarse uv-grid attempt
    try:
        return _tessellate_analytic_face(face, face_idx, material_slot)
    except Exception:
        return _FaceMesh(
            name=f"face_{face_idx}",
            vertices=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material_slot=material_slot,
            face_id=face.id,
        )


# ---------------------------------------------------------------------------
# Minimal in-module glTF 2.0 binary writer
# ---------------------------------------------------------------------------


def _pad4(buf: bytes, pad_byte: int = 0) -> bytes:
    if len(buf) % 4 == 0:
        return buf
    return buf + bytes([pad_byte]) * (4 - len(buf) % 4)


def _aabb(arr: np.ndarray) -> Tuple[List[float], List[float]]:
    if arr.size == 0:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    mn = arr.min(axis=0).astype(float).tolist()
    mx = arr.max(axis=0).astype(float).tolist()
    return mn, mx


def _build_gltf(face_meshes: List[_FaceMesh]) -> Tuple[bytes, Dict[str, Any]]:
    """Build a binary glTF 2.0 file from a list of per-face meshes.

    Returns ``(glb_bytes, gltf_json_dict)``.  The JSON dict is also
    embedded in the GLB; we return it for caller-side validation /
    tests without having to re-parse the binary.
    """
    bin_chunks: List[bytes] = []
    buffer_views: List[Dict[str, Any]] = []
    accessors: List[Dict[str, Any]] = []
    meshes: List[Dict[str, Any]] = []
    nodes: List[Dict[str, Any]] = []

    bin_cursor = 0

    def _add_bv(data: bytes, target: Optional[int] = None) -> int:
        nonlocal bin_cursor
        # 4-byte alignment between buffer views
        if bin_cursor % 4 != 0:
            pad = 4 - bin_cursor % 4
            bin_chunks.append(b"\x00" * pad)
            bin_cursor += pad
        bv = {
            "buffer":     0,
            "byteOffset": bin_cursor,
            "byteLength": len(data),
        }
        if target is not None:
            bv["target"] = target
        buffer_views.append(bv)
        bin_chunks.append(data)
        bin_cursor += len(data)
        return len(buffer_views) - 1

    # root node holds all mesh nodes as children
    child_node_indices: List[int] = []

    for fm in face_meshes:
        if fm.vertices.size == 0:
            # still create a node so face/material accounting matches
            nodes.append({"name": fm.name})
            child_node_indices.append(len(nodes) - 1)
            continue

        v_bytes = fm.vertices.astype("<f4").tobytes()
        n_bytes = fm.normals.astype("<f4").tobytes()
        i_bytes = fm.indices.astype("<u4").tobytes()

        bv_v = _add_bv(v_bytes, target=34962)   # ARRAY_BUFFER
        bv_n = _add_bv(n_bytes, target=34962)
        bv_i = _add_bv(i_bytes, target=34963)   # ELEMENT_ARRAY_BUFFER

        v_min, v_max = _aabb(fm.vertices)

        acc_v = {
            "bufferView":    bv_v,
            "componentType": 5126,                 # FLOAT
            "count":         int(fm.vertices.shape[0]),
            "type":          "VEC3",
            "min":           v_min,
            "max":           v_max,
        }
        acc_n = {
            "bufferView":    bv_n,
            "componentType": 5126,
            "count":         int(fm.normals.shape[0]),
            "type":          "VEC3",
        }
        acc_i = {
            "bufferView":    bv_i,
            "componentType": 5125,                 # UNSIGNED_INT
            "count":         int(fm.indices.shape[0]),
            "type":          "SCALAR",
        }
        accessors.extend([acc_v, acc_n, acc_i])
        a_v = len(accessors) - 3
        a_n = len(accessors) - 2
        a_i = len(accessors) - 1

        prim = {
            "attributes": {"POSITION": a_v, "NORMAL": a_n},
            "indices":    a_i,
            "mode":       4,                       # TRIANGLES
            "extras":     {"material_slot": fm.material_slot,
                           "face_id": fm.face_id},
        }
        mesh = {"name": fm.name, "primitives": [prim]}
        meshes.append(mesh)

        node = {
            "name":   fm.name,
            "mesh":   len(meshes) - 1,
            "extras": {"material_slot": fm.material_slot,
                       "face_id": fm.face_id},
        }
        nodes.append(node)
        child_node_indices.append(len(nodes) - 1)

    nodes.append({
        "name":     "root",
        "children": child_node_indices,
    })
    root_node_idx = len(nodes) - 1

    bin_blob = b"".join(bin_chunks)
    if len(bin_blob) == 0:
        # synthesise a single zero byte so glTF spec compliance holds
        bin_blob = b"\x00\x00\x00\x00"

    gltf: Dict[str, Any] = {
        "asset": {"version": "2.0",
                  "generator": "kerf-render cycles_translator (T-106a)"},
        "scene":     0,
        "scenes":    [{"name": "kerf_scene", "nodes": [root_node_idx]}],
        "nodes":     nodes,
        "meshes":    meshes,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers":   [{"byteLength": len(bin_blob)}],
    }

    json_str = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_str_padded = _pad4(json_str, pad_byte=0x20)        # space pad
    bin_blob_padded = _pad4(bin_blob, pad_byte=0x00)

    total_len = 12 + 8 + len(json_str_padded) + 8 + len(bin_blob_padded)
    glb = struct.pack("<III", 0x46546C67, 2, total_len)
    glb += struct.pack("<II", len(json_str_padded), 0x4E4F534A) + json_str_padded
    glb += struct.pack("<II", len(bin_blob_padded), 0x004E4942) + bin_blob_padded
    return glb, gltf


def parse_glb_header(glb: bytes) -> Dict[str, Any]:
    """Parse a GLB blob -- header + JSON chunk -- back to a dict.

    Returns ``{"magic": int, "version": int, "length": int,
              "json": <gltf dict>, "bin_length": int}``.

    Raises :class:`ValueError` on a malformed buffer.
    """
    if len(glb) < 12:
        raise ValueError("glb buffer too short for header")
    magic, version, length = struct.unpack("<III", glb[:12])
    if magic != 0x46546C67:
        raise ValueError(f"bad glb magic 0x{magic:08x}")
    if version != 2:
        raise ValueError(f"unsupported glb version {version}")
    if length != len(glb):
        raise ValueError(f"glb length mismatch: header {length} vs actual {len(glb)}")
    # JSON chunk
    if len(glb) < 20:
        raise ValueError("missing JSON chunk header")
    j_len, j_type = struct.unpack("<II", glb[12:20])
    if j_type != 0x4E4F534A:
        raise ValueError(f"first chunk is not JSON (type=0x{j_type:08x})")
    j_data = glb[20:20 + j_len].rstrip(b"\x20\x00")
    gltf_json = json.loads(j_data.decode("utf-8"))
    bin_start = 20 + j_len
    bin_len = 0
    if len(glb) >= bin_start + 8:
        b_len, b_type = struct.unpack("<II", glb[bin_start:bin_start + 8])
        if b_type == 0x004E4942:
            bin_len = b_len
    return {
        "magic":      magic,
        "version":    version,
        "length":     length,
        "json":       gltf_json,
        "bin_length": bin_len,
    }


# ---------------------------------------------------------------------------
# Material resolution
# ---------------------------------------------------------------------------


def _resolve_materials(face_meshes: Iterable[_FaceMesh],
                       overrides: Optional[Dict[str, str]]) -> Tuple[
                           Dict[str, Dict[str, Any]], List[str]]:
    """Resolve every face's material slot to a PBR/glass parameter dict.

    Returns ``(materials_dict, missing)``.  ``materials_dict`` is keyed
    by canonical material name and includes the original slot string in
    ``"slot"`` for traceability.  ``missing`` lists slot names that
    could not be resolved (caller decides whether to fail or fall back).
    """
    out: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    seen: set = set()
    for fm in face_meshes:
        slot = fm.material_slot
        if overrides and slot in overrides:
            slot = overrides[slot]
        if slot in seen:
            continue
        seen.add(slot)
        try:
            mat = lookup_material(slot)
        except KeyError:
            missing.append(slot)
            mat = dict(DEFAULT_MATERIAL)
            mat["_fallback"] = True
        mat["slot"] = slot
        mat["kind"] = material_kind(slot)
        out[canonical_key(slot)] = mat
    return out, missing


# ---------------------------------------------------------------------------
# Blender script emitter
# ---------------------------------------------------------------------------

_BLENDER_SCRIPT_HEADER = '''"""Auto-generated by kerf-render cycles_translator (T-106a).

This script is meant to be executed inside Blender (``blender -b -P script.py``).
It will import the companion glTF, rebuild materials as Principled BSDF
(metals/plastics) or Glass BSDF with spectral dispersion (gemstones),
configure a camera + lights, and run the Cycles render.
"""

import json
import math
import os

try:
    import bpy            # type: ignore
    from mathutils import Vector, Matrix         # type: ignore
except Exception as exc:    # pragma: no cover - executed only inside Blender
    raise RuntimeError("This script must run inside Blender (bpy missing): %r" % exc)


'''


def _emit_blender_script(
    *,
    gltf_path: str,
    materials_dict: Dict[str, Dict[str, Any]],
    camera: Camera,
    lights: Sequence[Light],
    output: RenderOutput,
) -> str:
    cam_pos = tuple(float(x) for x in camera.position)
    cam_tgt = tuple(float(x) for x in camera.target)
    cam_up = tuple(float(x) for x in camera.up)
    fov_rad = float(camera.fov_deg) * math.pi / 180.0
    light_list = [
        {
            "type":     light.type,
            "position": [float(x) for x in light.position],
            "target":   [float(x) for x in light.target],
            "color":    [float(x) for x in light.color],
            "energy":   float(light.energy),
            "size":     float(light.size),
            "name":     str(light.name),
        }
        for light in lights
    ]
    render_cfg = {
        "path":              output.path,
        "resolution":        [int(output.resolution[0]), int(output.resolution[1])],
        "samples":           int(output.samples),
        "engine":            str(output.engine),
        "device":            str(output.device),
        "film_transparent":  bool(output.film_transparent),
    }
    materials_payload = {k: _strip_materials_dict_for_script(v)
                         for k, v in materials_dict.items()}

    json_block = json.dumps({
        "gltf_path":   gltf_path,
        "camera": {
            "position": list(cam_pos),
            "target":   list(cam_tgt),
            "up":       list(cam_up),
            "fov_rad":  fov_rad,
            "name":     camera.name,
        },
        "lights":    light_list,
        "render":    render_cfg,
        "materials": materials_payload,
    }, indent=2)

    body = '''
# ---------------------------------------------------------------------------
# Scene parameters (auto-generated)
# ---------------------------------------------------------------------------

SCENE_CONFIG = json.loads(r"""__SCENE_JSON__""")


def _clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)


def _look_at_matrix(position, target, up):
    pos = Vector(position)
    tgt = Vector(target)
    upv = Vector(up)
    forward = (tgt - pos).normalized()
    right = forward.cross(upv).normalized()
    real_up = right.cross(forward).normalized()
    rot = Matrix((
        (right.x, real_up.x, -forward.x, pos.x),
        (right.y, real_up.y, -forward.y, pos.y),
        (right.z, real_up.z, -forward.z, pos.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return rot


def _make_principled_material(name, params):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = tuple(params.get(
        "base_color", (0.6, 0.6, 0.6, 1.0)))
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = float(params.get("metallic", 0.0))
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = float(params.get("roughness", 0.5))
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = float(params.get("ior", 1.5))
    if "Specular" in bsdf.inputs:
        try:
            bsdf.inputs["Specular"].default_value = float(params.get("specular", 0.5))
        except Exception:
            pass
    if "Transmission" in bsdf.inputs:
        try:
            bsdf.inputs["Transmission"].default_value = float(
                params.get("transmission", 0.0))
        except Exception:
            pass
    return mat


def _make_glass_material(name, params):
    """Glass BSDF with spectral dispersion for gems (Cycles 4.0+)."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(glass.outputs[0], out.inputs[0])
    glass.inputs["Color"].default_value = tuple(params.get(
        "base_color", (0.99, 0.99, 0.99, 1.0)))
    glass.inputs["Roughness"].default_value = float(params.get("roughness", 0.0))
    glass.inputs["IOR"].default_value = float(params.get("ior", 1.5))
    # Cycles 4.0+ exposes a numeric dispersion socket on the Glass BSDF
    # driven by Abbe number (lower = stronger dispersion).
    if "Dispersion" in glass.inputs:
        abbe = float(params.get("abbe", 55.0))
        # Blender's Dispersion input takes a scalar derived from Abbe;
        # the standard inverse mapping is dispersion = 1 / abbe.
        glass.inputs["Dispersion"].default_value = 1.0 / max(abbe, 1.0)
    # Stash spectral data on the material for downstream caustic solvers
    mat["abbe"] = float(params.get("abbe", 55.0))
    mat["sellmeier"] = list(list(p) for p in params.get("sellmeier", []))
    return mat


def _build_materials():
    materials = {}
    for slot_key, params in SCENE_CONFIG["materials"].items():
        bsdf_kind = params.get("bsdf", "principled")
        if bsdf_kind == "glass":
            materials[slot_key] = _make_glass_material("kerf_" + slot_key, params)
        else:
            materials[slot_key] = _make_principled_material("kerf_" + slot_key, params)
    return materials


def _assign_materials(materials):
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        extras = obj.get("extras", {}) or {}
        slot = extras.get("material_slot") if isinstance(extras, dict) else None
        if not slot and obj.data is not None:
            slot = (obj.data.get("material_slot") if hasattr(obj.data, "get") else None)
        if not slot:
            # try to recover from node-level custom property set by the gltf importer
            slot = obj.name.split(".")[0]
        canonical = slot.strip().lower().replace(" ", "_").replace("-", "_")
        mat = materials.get(canonical)
        if mat is None:
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def _configure_camera():
    cam_cfg = SCENE_CONFIG["camera"]
    cam_data = bpy.data.cameras.new(name=cam_cfg["name"])
    cam_data.angle = float(cam_cfg["fov_rad"])
    cam_obj = bpy.data.objects.new(cam_cfg["name"], cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.matrix_world = _look_at_matrix(
        cam_cfg["position"], cam_cfg["target"], cam_cfg["up"])
    bpy.context.scene.camera = cam_obj
    return cam_obj


def _configure_lights():
    objs = []
    for light_cfg in SCENE_CONFIG["lights"]:
        ltype = light_cfg["type"].upper()
        if ltype == "SUN":
            ldata = bpy.data.lights.new(name=light_cfg["name"], type="SUN")
        elif ltype == "AREA":
            ldata = bpy.data.lights.new(name=light_cfg["name"], type="AREA")
            ldata.size = float(light_cfg["size"])
        else:
            ldata = bpy.data.lights.new(name=light_cfg["name"], type="POINT")
        ldata.color = tuple(light_cfg["color"])
        ldata.energy = float(light_cfg["energy"])
        lobj = bpy.data.objects.new(light_cfg["name"], ldata)
        lobj.location = tuple(light_cfg["position"])
        bpy.context.scene.collection.objects.link(lobj)
        objs.append(lobj)
    return objs


def _configure_render():
    rcfg = SCENE_CONFIG["render"]
    scn = bpy.context.scene
    scn.render.engine = rcfg["engine"]
    scn.render.resolution_x = int(rcfg["resolution"][0])
    scn.render.resolution_y = int(rcfg["resolution"][1])
    scn.render.filepath = rcfg["path"]
    scn.render.film_transparent = bool(rcfg["film_transparent"])
    if hasattr(scn, "cycles"):
        scn.cycles.samples = int(rcfg["samples"])
        try:
            scn.cycles.device = rcfg["device"]
        except Exception:
            pass


def main():
    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=SCENE_CONFIG["gltf_path"])
    materials = _build_materials()
    _assign_materials(materials)
    _configure_camera()
    _configure_lights()
    _configure_render()


if __name__ == "__main__":
    main()
'''
    return _BLENDER_SCRIPT_HEADER + body.replace(
        "__SCENE_JSON__", json_block.replace('"""', '\\"\\"\\"'))


def _strip_materials_dict_for_script(mat: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of the material dict safe to JSON-embed in the script."""
    out: Dict[str, Any] = {}
    for k, v in mat.items():
        if isinstance(v, tuple):
            out[k] = list(v)
        elif isinstance(v, list) and v and isinstance(v[0], tuple):
            out[k] = [list(x) for x in v]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate_body_to_gltf_plus_materials(
    body,
    *,
    camera: Optional[Camera] = None,
    lights: Optional[Sequence[Light]] = None,
    materials: Optional[Dict[int, str]] = None,
    output: Optional[RenderOutput] = None,
    gltf_path: str = "/tmp/kerf_scene.glb",
    strict: bool = False,
) -> Dict[str, Any]:
    """Translate a Kerf :class:`Body` into a glTF + materials + Blender script.

    Parameters
    ----------
    body
        Any :class:`kerf_cad_core.geom.brep.Body` (or duck-typed
        equivalent providing ``all_faces()``). Must have at least one
        face.
    camera
        Optional :class:`Camera`; defaults to ``(0,0,5)`` aimed at the
        origin.
    lights
        Optional sequence of :class:`Light` objects. Defaults to a
        single 5-unit-offset key light.
    materials
        Optional mapping from :class:`Face` ``.id`` to a material slot
        name (string). Unspecified faces fall back to ``"default"``,
        which resolves to a neutral grey Principled BSDF.
    output
        :class:`RenderOutput` describing the final image file. Defaults
        to ``/tmp/kerf_render.png`` at 1080p, 256 samples, Cycles GPU.
    gltf_path
        File path that the Blender script will use to ``import_scene.
        gltf``. The bytes themselves are returned, *not* written.
    strict
        If True, any unresolved material slot causes the call to return
        ``{"ok": False, "reason": ...}``. Defaults to False (fall back
        to a neutral grey).

    Returns
    -------
    dict
        Either::

            {"ok": True,
             "gltf_bytes":     bytes,
             "materials_dict": dict,
             "blender_script": str,
             "face_count":     int}

        or, on a recoverable failure::

            {"ok": False, "reason": str}
    """
    if body is None:
        return {"ok": False, "reason": "body is None"}

    try:
        faces = body.all_faces()
    except AttributeError:
        return {"ok": False, "reason": "body has no all_faces() accessor"}

    if not faces:
        return {"ok": False, "reason": "body has zero faces"}

    cam = camera or Camera()
    light_list = list(lights) if lights is not None else [
        Light(type="point", position=(5.0, 5.0, 5.0), energy=1000.0),
    ]
    output_cfg = output or RenderOutput()
    slot_map: Dict[int, str] = dict(materials or {})

    face_meshes: List[_FaceMesh] = []
    for idx, face in enumerate(faces):
        slot = slot_map.get(face.id, "default")
        fm = _tessellate_face(face, idx, slot)
        face_meshes.append(fm)

    materials_dict, missing = _resolve_materials(face_meshes,
                                                 overrides=None)
    if strict and missing:
        return {
            "ok": False,
            "reason": "missing material slot(s): " + ", ".join(sorted(set(missing))),
        }

    glb_bytes, _gltf_json = _build_gltf(face_meshes)
    script_str = _emit_blender_script(
        gltf_path=gltf_path,
        materials_dict=materials_dict,
        camera=cam,
        lights=light_list,
        output=output_cfg,
    )

    return {
        "ok":             True,
        "gltf_bytes":     glb_bytes,
        "materials_dict": materials_dict,
        "blender_script": script_str,
        "face_count":     len(face_meshes),
        "missing":        list(missing),
    }


def vertex_count_for_body(body) -> int:
    """Total unique mesh-vertex count emitted by the translator for ``body``.

    Useful for the round-trip / sanity tests: each Face contributes its
    own copy of its loop polygon vertices (planar faces) or its
    parametric-grid samples (analytic faces).
    """
    n = 0
    for idx, face in enumerate(body.all_faces()):
        fm = _tessellate_face(face, idx, "default")
        n += int(fm.vertices.shape[0])
    return n


__all__ = [
    "Camera",
    "Light",
    "RenderOutput",
    "translate_body_to_gltf_plus_materials",
    "parse_glb_header",
    "vertex_count_for_body",
]
