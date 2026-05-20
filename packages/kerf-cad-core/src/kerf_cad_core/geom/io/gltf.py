"""
geom/io/gltf.py
===============
Pure-Python glTF 2.0 / GLB read + write for triangle meshes with PBR materials
(GK-79).

glTF 2.0 Format Summary
-----------------------
A .gltf file is a JSON document that may reference external binary buffers
(.bin files).  A .glb file (binary glTF) packs everything into a single binary
container:

  Byte  0 ..  3  : magic   0x46546C67 ("glTF")
  Byte  4 ..  7  : version 2 (uint32 LE)
  Byte  8 .. 11  : total file length (uint32 LE)
  Chunk 0        : JSON chunk  (type 0x4E4F534A "JSON")
  Chunk 1        : BIN  chunk  (type 0x004E4942 "BIN\\x00")

Each chunk:
  Byte 0..3 : chunk length (uint32 LE)
  Byte 4..7 : chunk type  (uint32 LE)
  Byte 8..  : chunk data (padded to 4-byte alignment)

Data model accepted / returned
-------------------------------
``verts``     — list of [x, y, z] floats
``faces``     — list of [i, j, k] 0-based vertex indices
``normals``   — optional list of [nx, ny, nz] per-vertex normals
``uvs``       — optional list of [u, v] per-vertex texture coordinates
``materials`` — optional list of PBR material dicts:
                  ``name``         (str)
                  ``base_color``   ([r, g, b, a] floats 0–1, default [1,1,1,1])
                  ``metallic``     (float 0–1, default 0.0)
                  ``roughness``    (float 0–1, default 0.5)
                  ``emissive``     ([r, g, b] floats 0–1, default [0,0,0])
                  ``double_sided`` (bool, default False)
                  ``alpha_mode``   ("OPAQUE" | "MASK" | "BLEND", default "OPAQUE")
``material_indices`` — optional list of int, one per mesh primitive / face group

Public API
----------
``read_gltf(path) -> dict``
    Load a .gltf or .glb file.  Returns a dict with keys:
    ``verts``, ``faces``, ``normals`` (may be empty), ``uvs`` (may be empty),
    ``materials``, ``material_indices``, ``metadata`` (dict str→str).

``write_gltf(path, mesh_or_body, materials=None, *, binary=True)``
    Write a .glb (binary=True, default) or .gltf + .bin (binary=False) file.
    *mesh_or_body* may be:
      - a dict with ``"verts"`` and ``"faces"`` (and optionally ``"normals"``,
        ``"uvs"``, ``"material_indices"``)
      - any object with ``.verts``/``.vertices`` and ``.faces`` attributes

Exceptions
----------
``GltfReadError``   — fatal parse errors
``GltfWriteError``  — fatal serialisation errors

References
----------
* glTF 2.0 Specification (https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
* Binary glTF (GLB) spec §5
"""

from __future__ import annotations

import base64
import json
import math
import struct
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public exception types
# ---------------------------------------------------------------------------

class GltfReadError(Exception):
    """Raised when a glTF / GLB file cannot be parsed."""


class GltfWriteError(Exception):
    """Raised when mesh data cannot be serialised to glTF / GLB."""


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_MAGIC = 0x46546C67        # "glTF"
_VERSION = 2
_CHUNK_JSON = 0x4E4F534A   # "JSON"
_CHUNK_BIN  = 0x004E4942   # "BIN\x00"

# glTF accessor component types
_FLOAT = 5126
_UNSIGNED_INT = 5125
_UNSIGNED_SHORT = 5123
_UNSIGNED_BYTE = 5121

# glTF accessor types
_SCALAR = "SCALAR"
_VEC2   = "VEC2"
_VEC3   = "VEC3"
_VEC4   = "VEC4"


# ---------------------------------------------------------------------------
# Helpers — pack/unpack binary buffer data
# ---------------------------------------------------------------------------

def _pad4(n: int) -> int:
    """Round *n* up to the next multiple of 4."""
    return (n + 3) & ~3


def _pack_floats(values: list) -> bytes:
    """Pack a flat sequence of floats as little-endian float32."""
    return struct.pack(f"<{len(values)}f", *values)


def _pack_uints(values: list, byte_width: int) -> bytes:
    """Pack a flat sequence of unsigned integers with the given byte width."""
    fmt = {1: "B", 2: "H", 4: "I"}[byte_width]
    return struct.pack(f"<{len(values)}{fmt}", *values)


def _unpack_floats(data: bytes, count: int, offset: int = 0) -> list:
    return list(struct.unpack_from(f"<{count}f", data, offset))


def _unpack_uints(data: bytes, count: int, offset: int = 0, byte_width: int = 4) -> list:
    fmt = {1: "B", 2: "H", 4: "I"}[byte_width]
    return list(struct.unpack_from(f"<{count}{fmt}", data, offset))


# ---------------------------------------------------------------------------
# Helpers — normalise mesh_or_body input
# ---------------------------------------------------------------------------

def _extract_mesh(mesh_or_body: Any) -> dict:
    """Return a normalised dict with ``verts``, ``faces``, etc."""
    if isinstance(mesh_or_body, dict):
        mesh = dict(mesh_or_body)
    else:
        verts = getattr(mesh_or_body, "verts", None) or getattr(mesh_or_body, "vertices", None)
        faces = getattr(mesh_or_body, "faces", None)
        if verts is None or faces is None:
            raise GltfWriteError(
                "mesh_or_body must be a dict or have .verts/.vertices and .faces attributes"
            )
        mesh = {"verts": verts, "faces": faces}
        for attr in ("normals", "uvs", "material_indices"):
            val = getattr(mesh_or_body, attr, None)
            if val is not None:
                mesh[attr] = val

    verts = mesh.get("verts") or mesh.get("vertices") or []
    faces = mesh.get("faces", [])
    normals = mesh.get("normals", [])
    uvs = mesh.get("uvs", [])
    material_indices = mesh.get("material_indices", [])

    def _to_list(x):
        return x.tolist() if hasattr(x, "tolist") else list(x)

    return {
        "verts": _to_list(verts),
        "faces": _to_list(faces),
        "normals": _to_list(normals),
        "uvs": _to_list(uvs),
        "material_indices": _to_list(material_indices),
    }


# ---------------------------------------------------------------------------
# Helpers — GLB binary container
# ---------------------------------------------------------------------------

def _build_glb(json_bytes: bytes, bin_bytes: bytes) -> bytes:
    """Assemble a GLB binary container from JSON and BIN chunk payloads."""
    json_pad = _pad4(len(json_bytes))
    json_chunk = json_bytes + b" " * (json_pad - len(json_bytes))

    bin_pad = _pad4(len(bin_bytes)) if bin_bytes else 0
    bin_chunk = bin_bytes + b"\x00" * (bin_pad - len(bin_bytes)) if bin_bytes else b""

    header_size = 12
    json_chunk_size = 8 + len(json_chunk)
    bin_chunk_size  = 8 + len(bin_chunk) if bin_chunk else 0
    total = header_size + json_chunk_size + bin_chunk_size

    parts = [
        struct.pack("<III", _MAGIC, _VERSION, total),
        struct.pack("<II", len(json_chunk), _CHUNK_JSON),
        json_chunk,
    ]
    if bin_chunk:
        parts.append(struct.pack("<II", len(bin_chunk), _CHUNK_BIN))
        parts.append(bin_chunk)

    return b"".join(parts)


def _parse_glb(data: bytes) -> tuple:
    """Parse a GLB binary container. Returns (json_dict, bin_bytes)."""
    if len(data) < 12:
        raise GltfReadError("Truncated GLB header")
    magic, version, total_len = struct.unpack_from("<III", data, 0)
    if magic != _MAGIC:
        raise GltfReadError(f"Invalid GLB magic: 0x{magic:08X}")
    if version != 2:
        raise GltfReadError(f"Unsupported glTF version: {version}")
    if total_len > len(data):
        raise GltfReadError(f"GLB claims {total_len} bytes but only {len(data)} available")

    offset = 12
    json_dict = None
    bin_bytes = b""

    while offset + 8 <= total_len:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len

        if chunk_type == _CHUNK_JSON:
            try:
                json_dict = json.loads(chunk_data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise GltfReadError(f"JSON chunk parse error: {exc}") from exc
        elif chunk_type == _CHUNK_BIN:
            bin_bytes = chunk_data

    if json_dict is None:
        raise GltfReadError("No JSON chunk found in GLB")

    return json_dict, bin_bytes


# ---------------------------------------------------------------------------
# Helpers — accessor extraction
# ---------------------------------------------------------------------------

def _resolve_buffer_data(gltf: dict, buffer_views: list,
                         bin_bytes: bytes, base_dir: Path) -> list:
    """Resolve each bufferView to its raw bytes."""
    buffers_raw = []
    for buf in gltf.get("buffers", []):
        uri = buf.get("uri", "")
        if not uri:
            buffers_raw.append(bin_bytes)
        elif uri.startswith("data:"):
            try:
                _, encoded = uri.split(",", 1)
                buffers_raw.append(base64.b64decode(encoded))
            except Exception as exc:
                raise GltfReadError(f"Cannot decode data URI: {exc}") from exc
        else:
            buf_path = base_dir / uri
            try:
                buffers_raw.append(buf_path.read_bytes())
            except OSError as exc:
                raise GltfReadError(f"Cannot read buffer file {buf_path}: {exc}") from exc

    view_bytes = []
    for view in buffer_views:
        buf_idx = view["buffer"]
        byte_offset = view.get("byteOffset", 0)
        byte_length = view["byteLength"]
        if buf_idx >= len(buffers_raw):
            raise GltfReadError(f"Buffer index {buf_idx} out of range")
        raw = buffers_raw[buf_idx]
        view_bytes.append(raw[byte_offset:byte_offset + byte_length])

    return view_bytes


def _read_accessor(gltf: dict, view_bytes: list, acc_idx: int) -> list:
    """Extract values from a glTF accessor. Returns a list of scalars or tuples."""
    accessors = gltf.get("accessors", [])
    if acc_idx >= len(accessors):
        raise GltfReadError(f"Accessor index {acc_idx} out of range")
    acc = accessors[acc_idx]

    view_idx    = acc.get("bufferView")
    byte_offset = acc.get("byteOffset", 0)
    count       = acc["count"]
    comp_type   = acc["componentType"]
    acc_type    = acc["type"]

    type_counts = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
                   "MAT2": 4, "MAT3": 9, "MAT4": 16}
    n_comp = type_counts.get(acc_type, 1)

    if view_idx is None:
        zero = 0.0 if comp_type == _FLOAT else 0
        if n_comp == 1:
            return [zero] * count
        return [tuple([zero] * n_comp)] * count

    raw = view_bytes[view_idx][byte_offset:]

    if comp_type == _FLOAT:
        flat = _unpack_floats(raw, count * n_comp)
    elif comp_type == _UNSIGNED_INT:
        flat = _unpack_uints(raw, count * n_comp, byte_width=4)
    elif comp_type == _UNSIGNED_SHORT:
        flat = _unpack_uints(raw, count * n_comp, byte_width=2)
    elif comp_type == _UNSIGNED_BYTE:
        flat = _unpack_uints(raw, count * n_comp, byte_width=1)
    else:
        raise GltfReadError(f"Unsupported accessor componentType: {comp_type}")

    if n_comp == 1:
        return flat
    return [tuple(flat[i * n_comp:(i + 1) * n_comp]) for i in range(count)]


# ---------------------------------------------------------------------------
# Helpers — PBR material parsing / building
# ---------------------------------------------------------------------------

def _parse_material(mat: dict) -> dict:
    """Convert a raw glTF material JSON object to our normalised dict."""
    pbr = mat.get("pbrMetallicRoughness", {})
    base_color   = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
    metallic     = pbr.get("metallicFactor",  0.0)
    roughness    = pbr.get("roughnessFactor", 0.5)
    emissive     = mat.get("emissiveFactor",  [0.0, 0.0, 0.0])
    double_sided = mat.get("doubleSided", False)
    alpha_mode   = mat.get("alphaMode", "OPAQUE")
    name         = mat.get("name", "")
    return {
        "name":         name,
        "base_color":   list(base_color),
        "metallic":     float(metallic),
        "roughness":    float(roughness),
        "emissive":     list(emissive),
        "double_sided": bool(double_sided),
        "alpha_mode":   alpha_mode,
    }


def _build_material_json(mat: dict, idx: int) -> dict:
    """Convert our normalised material dict to a glTF material JSON object."""
    base_color = mat.get("base_color", [1.0, 1.0, 1.0, 1.0])
    if len(base_color) == 3:
        base_color = list(base_color) + [1.0]
    return {
        "name": mat.get("name", f"material_{idx}"),
        "pbrMetallicRoughness": {
            "baseColorFactor": [float(c) for c in base_color],
            "metallicFactor":  float(mat.get("metallic",  0.0)),
            "roughnessFactor": float(mat.get("roughness", 0.5)),
        },
        "emissiveFactor":  [float(c) for c in mat.get("emissive", [0.0, 0.0, 0.0])],
        "doubleSided":     bool(mat.get("double_sided", False)),
        "alphaMode":       mat.get("alpha_mode", "OPAQUE"),
    }


# ---------------------------------------------------------------------------
# Core build helpers — JSON + BIN construction
# ---------------------------------------------------------------------------

def _build_gltf_data(verts, faces, normals, uvs, materials, material_indices):
    """
    Build the glTF JSON document and the binary buffer payload.

    Returns (gltf_json_dict, bin_bytes).
    """
    if not verts:
        raise GltfWriteError("verts must not be empty")
    if not faces:
        raise GltfWriteError("faces must not be empty")

    flat_verts = []
    min_pos = [math.inf,  math.inf,  math.inf]
    max_pos = [-math.inf, -math.inf, -math.inf]
    for v in verts:
        x, y, z = float(v[0]), float(v[1]), float(v[2])
        flat_verts.extend([x, y, z])
        for i, val in enumerate([x, y, z]):
            if val < min_pos[i]:
                min_pos[i] = val
            if val > max_pos[i]:
                max_pos[i] = val

    n_verts = len(verts)
    flat_faces = []
    for f in faces:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        if not (0 <= a < n_verts and 0 <= b < n_verts and 0 <= c < n_verts):
            raise GltfWriteError(f"Face index out of range: [{a},{b},{c}] vs {n_verts} verts")
        flat_faces.extend([a, b, c])

    flat_normals = []
    if normals:
        if len(normals) != n_verts:
            raise GltfWriteError(
                f"normals length {len(normals)} != verts length {n_verts}"
            )
        for n in normals:
            flat_normals.extend([float(n[0]), float(n[1]), float(n[2])])

    flat_uvs = []
    if uvs:
        if len(uvs) != n_verts:
            raise GltfWriteError(
                f"uvs length {len(uvs)} != verts length {n_verts}"
            )
        for uv in uvs:
            flat_uvs.extend([float(uv[0]), float(uv[1])])

    bin_parts = []
    buffer_views = []
    accessors = []

    def _add_view(data, target=None):
        byte_offset = sum(len(p) for p in bin_parts)
        view = {"buffer": 0, "byteOffset": byte_offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        bin_parts.append(data)
        pad = _pad4(len(data)) - len(data)
        if pad:
            bin_parts.append(b"\x00" * pad)
        return len(buffer_views) - 1

    def _add_float_accessor(data, count, acc_type, view_idx, min_v=None, max_v=None):
        acc = {
            "bufferView": view_idx,
            "byteOffset": 0,
            "componentType": _FLOAT,
            "count": count,
            "type": acc_type,
        }
        if min_v is not None:
            acc["min"] = min_v
        if max_v is not None:
            acc["max"] = max_v
        accessors.append(acc)
        return len(accessors) - 1

    def _add_uint_accessor(data, count, view_idx, byte_width=4):
        comp_types = {1: _UNSIGNED_BYTE, 2: _UNSIGNED_SHORT, 4: _UNSIGNED_INT}
        acc = {
            "bufferView": view_idx,
            "byteOffset": 0,
            "componentType": comp_types[byte_width],
            "count": count,
            "type": _SCALAR,
        }
        accessors.append(acc)
        return len(accessors) - 1

    # POSITION accessor (ARRAY_BUFFER = 34962)
    pos_bytes = _pack_floats(flat_verts)
    pos_view  = _add_view(pos_bytes, target=34962)
    pos_acc   = _add_float_accessor(
        pos_bytes, n_verts, _VEC3, pos_view,
        min_v=[float(x) for x in min_pos],
        max_v=[float(x) for x in max_pos],
    )

    # NORMAL accessor (optional)
    norm_acc = None
    if flat_normals:
        norm_bytes = _pack_floats(flat_normals)
        norm_view  = _add_view(norm_bytes, target=34962)
        norm_acc   = _add_float_accessor(norm_bytes, n_verts, _VEC3, norm_view)

    # TEXCOORD_0 accessor (optional)
    uv_acc = None
    if flat_uvs:
        uv_bytes = _pack_floats(flat_uvs)
        uv_view  = _add_view(uv_bytes, target=34962)
        uv_acc   = _add_float_accessor(uv_bytes, n_verts, _VEC2, uv_view)

    # INDEX accessor (ELEMENT_ARRAY_BUFFER = 34963)
    if n_verts <= 255:
        byte_width = 1
    elif n_verts <= 65535:
        byte_width = 2
    else:
        byte_width = 4
    idx_bytes = _pack_uints(flat_faces, byte_width)
    idx_view  = _add_view(idx_bytes, target=34963)
    idx_acc   = _add_uint_accessor(idx_bytes, len(flat_faces), idx_view, byte_width)

    bin_bytes = b"".join(bin_parts)
    total_bin = len(bin_bytes)

    attributes = {"POSITION": pos_acc}
    if norm_acc is not None:
        attributes["NORMAL"] = norm_acc
    if uv_acc is not None:
        attributes["TEXCOORD_0"] = uv_acc

    primitive = {
        "attributes": attributes,
        "indices": idx_acc,
        "mode": 4,  # TRIANGLES
    }

    if materials and material_indices:
        mat_idx = int(material_indices[0])
        if 0 <= mat_idx < len(materials):
            primitive["material"] = mat_idx
    elif materials:
        primitive["material"] = 0

    gltf = {
        "asset": {"version": "2.0", "generator": "kerf-cad-core GK-79"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [0]}],
        "nodes":  [{"mesh": 0, "name": "mesh"}],
        "meshes": [{"name": "mesh", "primitives": [primitive]}],
        "accessors":   accessors,
        "bufferViews": buffer_views,
        "buffers":     [{"byteLength": total_bin}],
    }

    if materials:
        gltf["materials"] = [
            _build_material_json(m, i) for i, m in enumerate(materials)
        ]

    return gltf, bin_bytes


# ---------------------------------------------------------------------------
# Public API — write_gltf
# ---------------------------------------------------------------------------

def write_gltf(path, mesh_or_body, materials=None, *, binary=True):
    """
    Write a glTF 2.0 file.

    Parameters
    ----------
    path         : Output file path.
    mesh_or_body : Mesh data as a dict (with "verts"/"faces" keys) or an object
                   with ``.verts``/``.vertices`` and ``.faces`` attributes.
    materials    : Optional list of PBR material dicts (see module docstring).
    binary       : If True (default) write a single GLB file.
                   If False write a .gltf + .bin file pair.
    """
    path = Path(path)
    try:
        mesh = _extract_mesh(mesh_or_body)
    except GltfWriteError:
        raise
    except Exception as exc:
        raise GltfWriteError(f"Cannot extract mesh data: {exc}") from exc

    try:
        gltf_json, bin_bytes = _build_gltf_data(
            verts            = mesh["verts"],
            faces            = mesh["faces"],
            normals          = mesh["normals"],
            uvs              = mesh["uvs"],
            materials        = materials,
            material_indices = mesh["material_indices"],
        )
    except GltfWriteError:
        raise
    except Exception as exc:
        raise GltfWriteError(f"Error building glTF data: {exc}") from exc

    try:
        if binary:
            json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
            glb = _build_glb(json_bytes, bin_bytes)
            path.write_bytes(glb)
        else:
            bin_path = path.with_suffix(".bin")
            bin_name = bin_path.name
            if gltf_json.get("buffers"):
                gltf_json["buffers"][0]["uri"] = bin_name
            json_bytes = json.dumps(gltf_json, indent=2, separators=(",", ": ")).encode("utf-8")
            path.write_bytes(json_bytes)
            bin_path.write_bytes(bin_bytes)
    except GltfWriteError:
        raise
    except OSError as exc:
        raise GltfWriteError(f"File write error: {exc}") from exc
    except Exception as exc:
        raise GltfWriteError(f"Unexpected error writing glTF: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API — read_gltf
# ---------------------------------------------------------------------------

def read_gltf(path) -> dict:
    """
    Read a glTF 2.0 or GLB file.

    Parameters
    ----------
    path : Path to a .gltf or .glb file.

    Returns
    -------
    dict with keys:
        ``verts``            — list of [x, y, z] floats
        ``faces``            — list of [i, j, k] ints
        ``normals``          — list of [nx, ny, nz] floats (may be empty)
        ``uvs``              — list of [u, v] floats (may be empty)
        ``materials``        — list of PBR material dicts (may be empty)
        ``material_indices`` — list of int (may be empty)
        ``metadata``         — dict str->str (asset extras)
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GltfReadError(f"Cannot read file {path}: {exc}") from exc

    base_dir = path.parent

    if len(raw) >= 4 and struct.unpack_from("<I", raw, 0)[0] == _MAGIC:
        try:
            gltf, bin_bytes = _parse_glb(raw)
        except GltfReadError:
            raise
        except Exception as exc:
            raise GltfReadError(f"GLB parse error: {exc}") from exc
    else:
        try:
            gltf = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GltfReadError(f"JSON parse error: {exc}") from exc
        bin_bytes = b""

    try:
        return _decode_gltf(gltf, bin_bytes, base_dir)
    except GltfReadError:
        raise
    except Exception as exc:
        raise GltfReadError(f"Error decoding glTF data: {exc}") from exc


def _decode_gltf(gltf: dict, bin_bytes: bytes, base_dir: Path) -> dict:
    """Decode a parsed glTF JSON document and binary buffer."""
    buffer_views_raw = gltf.get("bufferViews", [])
    view_bytes = _resolve_buffer_data(gltf, buffer_views_raw, bin_bytes, base_dir)

    materials = [_parse_material(m) for m in gltf.get("materials", [])]

    scene_idx = gltf.get("scene", 0)
    scenes    = gltf.get("scenes", [])
    nodes     = gltf.get("nodes",  [])
    meshes    = gltf.get("meshes", [])

    primitive    = None
    material_idx = None

    if scenes and scene_idx < len(scenes):
        node_queue = list(scenes[scene_idx].get("nodes", []))
        while node_queue:
            nidx = node_queue.pop(0)
            if nidx >= len(nodes):
                continue
            node = nodes[nidx]
            node_queue.extend(node.get("children", []))
            mesh_idx = node.get("mesh")
            if mesh_idx is not None and mesh_idx < len(meshes):
                prims = meshes[mesh_idx].get("primitives", [])
                if prims:
                    primitive    = prims[0]
                    material_idx = primitive.get("material")
                    break

    if primitive is None and meshes:
        prims = meshes[0].get("primitives", [])
        if prims:
            primitive    = prims[0]
            material_idx = primitive.get("material")

    if primitive is None:
        raise GltfReadError("No mesh primitives found in glTF file")

    attributes = primitive.get("attributes", {})

    pos_acc_idx = attributes.get("POSITION")
    if pos_acc_idx is None:
        raise GltfReadError("Mesh primitive missing POSITION attribute")
    pos_raw = _read_accessor(gltf, view_bytes, pos_acc_idx)
    verts = [list(p) for p in pos_raw]

    idx_acc_idx = primitive.get("indices")
    faces = []
    if idx_acc_idx is not None:
        idx_flat = _read_accessor(gltf, view_bytes, idx_acc_idx)
        n_tris = len(idx_flat) // 3
        faces = [[idx_flat[i * 3], idx_flat[i * 3 + 1], idx_flat[i * 3 + 2]]
                 for i in range(n_tris)]
    else:
        n_v = len(verts)
        faces = [[i, i + 1, i + 2] for i in range(0, n_v - 2, 3)]

    normals = []
    norm_acc_idx = attributes.get("NORMAL")
    if norm_acc_idx is not None:
        normals_raw = _read_accessor(gltf, view_bytes, norm_acc_idx)
        normals = [list(n) for n in normals_raw]

    uvs = []
    uv_acc_idx = attributes.get("TEXCOORD_0")
    if uv_acc_idx is not None:
        uvs_raw = _read_accessor(gltf, view_bytes, uv_acc_idx)
        uvs = [list(uv) for uv in uvs_raw]

    material_indices = []
    if material_idx is not None:
        material_indices = [int(material_idx)]

    asset    = gltf.get("asset", {})
    extras   = asset.get("extras", {})
    metadata = {str(k): str(v) for k, v in extras.items()}
    if "generator" in asset:
        metadata["generator"] = str(asset["generator"])

    return {
        "verts":            verts,
        "faces":            faces,
        "normals":          normals,
        "uvs":              uvs,
        "materials":        materials,
        "material_indices": material_indices,
        "metadata":         metadata,
    }
