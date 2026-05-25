"""
jt_reader.py — Siemens JT file importer (pure Python, stdlib only).

Parses JT v8 and v10 files:
  - File header (magic, version, TOC offset)
  - Table of Contents (segment descriptors: GUID, offset, length, type)
  - LSG (Logical Scene Graph) segments → assembly tree
    (part nodes, instance transforms, part names, metadata properties)
  - Tessellated geometry segments (triangle strips → verts + faces)
    with ZLIB-compressed payloads
  - LOD / TriStripSet shape segments

Produces a Kerf model:
  {
    "ok": True,
    "version": "10.0",          # or "8.0" etc.
    "assembly": [node, ...],    # list of assembly nodes (tree)
    "meshes": {                 # part_id → mesh dict
      "<guid>": {
        "vertices": [[x,y,z], ...],
        "indices":  [i0, i1, i2, ...],   # triangle list
      }
    },
    "properties": {             # part_id → {key: value}
      "<guid>": {...}
    },
    "warnings": [str, ...]
  }

Assembly node:
  {
    "id":        str,           # GUID string
    "name":      str,
    "transform": [[float*4]*4], # 4×4 row-major; None if identity
    "children":  [node, ...]
  }

Never raises — errors surface as {"ok": False, "reason": "..."}.

LLM tool registered via @register, gated on "imports.jt".
"""

from __future__ import annotations

import io
import json
import math
import struct
import uuid
import warnings
import zlib
from typing import Any, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx


# ─── JT magic bytes ───────────────────────────────────────────────────────────

_JT_MAGIC = b"Version "          # 8 bytes — JT magic prefix

# Segment type GUID constants (lower 4 bytes of well-known GUIDs)
# JT spec uses 128-bit GUIDs stored as 4 uint32s (big-endian in v8, LE in v10).
# We match by the segment-type identifier embedded in the segment header.

_SEG_TYPE_LSG        = 0x10DD1035   # Logical Scene Graph
_SEG_TYPE_TESS       = 0x10DD1046   # TriStripSet / tessellation
_SEG_TYPE_SHAPE      = 0x10DD1038   # Shape LOD
_SEG_TYPE_META       = 0x10DD103A   # Meta-data/property segment
_SEG_TYPE_XTWB       = 0x10DD1056   # XT B-rep (skip with warning)


# ─── Low-level reader ─────────────────────────────────────────────────────────

class _Reader:
    """Thin wrapper around a bytes buffer with positional reads."""

    __slots__ = ("_buf", "_pos", "_le")

    def __init__(self, buf: bytes, little_endian: bool = True) -> None:
        self._buf = buf
        self._pos = 0
        self._le = little_endian

    # ── position ──

    @property
    def pos(self) -> int:
        return self._pos

    def seek(self, offset: int) -> None:
        self._pos = offset

    def remaining(self) -> int:
        return len(self._buf) - self._pos

    # ── primitive reads ──

    def _fmt(self, fmt_le: str, fmt_be: str, size: int):
        if self._pos + size > len(self._buf):
            raise EOFError(f"truncated: need {size} bytes at offset {self._pos}")
        chunk = self._buf[self._pos:self._pos + size]
        self._pos += size
        return struct.unpack_from(fmt_le if self._le else fmt_be, chunk)[0]

    def u8(self)  -> int:   return self._fmt("<B", ">B", 1)
    def i8(self)  -> int:   return self._fmt("<b", ">b", 1)
    def u16(self) -> int:   return self._fmt("<H", ">H", 2)
    def i16(self) -> int:   return self._fmt("<h", ">h", 2)
    def u32(self) -> int:   return self._fmt("<I", ">I", 4)
    def i32(self) -> int:   return self._fmt("<i", ">i", 4)
    def u64(self) -> int:   return self._fmt("<Q", ">Q", 8)
    def i64(self) -> int:   return self._fmt("<q", ">q", 8)
    def f32(self) -> float: return self._fmt("<f", ">f", 4)
    def f64(self) -> float: return self._fmt("<d", ">d", 8)

    def raw(self, n: int) -> bytes:
        if self._pos + n > len(self._buf):
            raise EOFError(f"truncated: need {n} bytes at offset {self._pos}")
        chunk = self._buf[self._pos:self._pos + n]
        self._pos += n
        return chunk

    def guid(self) -> str:
        """Read a 128-bit GUID as 4 uint32 values → canonical dash-format string."""
        a = self.u32()
        b = self.u32()
        c = self.u32()
        d = self.u32()
        # Format: {AAAAAAAA-BBBBCCCC-DDDDEEEE-FFFFFFFF} -> UUID string
        raw = struct.pack(">IIII", a, b, c, d)
        return str(uuid.UUID(bytes=raw))

    def counted_string(self) -> str:
        """Read a Pascal-style counted UTF-16 string (uint16 length + UTF-16LE chars)."""
        n = self.u16()
        if n == 0:
            return ""
        raw = self.raw(n * 2)
        try:
            return raw.decode("utf-16-le", errors="replace")
        except Exception:
            return raw.hex()

    def matrix4x4(self) -> list[list[float]]:
        """Read a 4×4 column-major float64 matrix, return as row-major list-of-lists."""
        vals = [self.f64() for _ in range(16)]
        # JT stores column-major; transpose to row-major
        return [
            [vals[0],  vals[4],  vals[8],  vals[12]],
            [vals[1],  vals[5],  vals[9],  vals[13]],
            [vals[2],  vals[6],  vals[10], vals[14]],
            [vals[3],  vals[7],  vals[11], vals[15]],
        ]


# ─── Header parsing ───────────────────────────────────────────────────────────

def _parse_header(buf: bytes) -> dict:
    """
    Parse the JT file header.

    JT header layout (v8 and v10 share the same first 80 bytes):
      Bytes 0-7:   ASCII magic "Version " (8 bytes)
      Bytes 8-17:  Version string, e.g. "8.0\x00\x00..." or "10.0\x00..." (10 bytes)
      Byte  18:    Byte order marker (0=big-endian, 1=little-endian)
      Bytes 19-22: Reserved / int32
      Bytes 23-30: TOC offset (int64)
      (v9+) Bytes 31-46: LSG segment ID (GUID of the root LSG)

    Returns dict with: version, little_endian, toc_offset, lsg_guid.
    """
    if len(buf) < 80:
        raise ValueError(f"file too short for JT header: {len(buf)} bytes")

    magic = buf[:8]
    if magic != _JT_MAGIC:
        raise ValueError(f"not a JT file: magic={magic!r}")

    version_raw = buf[8:18].split(b"\x00")[0]
    try:
        version = version_raw.decode("ascii").strip()
    except Exception:
        version = version_raw.hex()

    byte_order = buf[18]
    little_endian = (byte_order != 0)  # 0=BE, anything else=LE

    r = _Reader(buf, little_endian=little_endian)
    r.seek(19)
    _reserved = r.i32()
    toc_offset = r.i64()

    lsg_guid = None
    major = _version_major(version)
    if major >= 9 and len(buf) >= 47:
        r.seek(31)
        lsg_guid = r.guid()

    return {
        "version": version,
        "major": major,
        "little_endian": little_endian,
        "toc_offset": toc_offset,
        "lsg_guid": lsg_guid,
    }


def _version_major(version: str) -> int:
    try:
        return int(version.split(".")[0])
    except Exception:
        return 0


def _read_i64_le(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<q", buf, offset)[0]


# ─── TOC parsing ─────────────────────────────────────────────────────────────

def _parse_toc(buf: bytes, hdr: dict) -> list[dict]:
    """
    Parse the Table of Contents.

    JT TOC layout at toc_offset:
      uint32  entry_count
      For each entry:
        GUID    segment_id        (16 bytes = 4 uint32)
        int64   offset            (8 bytes)
        int32   length            (4 bytes)
        uint32  attributes        (4 bytes)

    Returns list of dicts: {id, offset, length, attributes}.
    """
    offset = hdr["toc_offset"]
    le = hdr["little_endian"]

    if offset < 0 or offset + 4 > len(buf):
        raise ValueError(f"TOC offset {offset} out of bounds (file size {len(buf)})")

    r = _Reader(buf, little_endian=le)
    r.seek(offset)

    count = r.u32()
    if count > 100_000:
        raise ValueError(f"implausible TOC entry count: {count}")

    entries = []
    for _ in range(count):
        seg_id = r.guid()
        seg_offset = r.i64()
        seg_len = r.i32()
        attrs = r.u32()
        entries.append({
            "id": seg_id,
            "offset": seg_offset,
            "length": seg_len,
            "attributes": attrs,
        })

    return entries


# ─── Segment data extraction ──────────────────────────────────────────────────

def _read_segment_data(buf: bytes, entry: dict, hdr: dict) -> bytes:
    """
    Read and optionally decompress a segment's raw payload.

    Segment on-disk layout:
      int32   segment_length      (may include this field itself)
      uint32  segment_type_id     (matches _SEG_TYPE_* constants)
      uint32  compression_flag    (0=uncompressed, 2=zlib)
      [if compressed:]
        int32  uncompressed_len
      bytes   payload
    """
    offset = entry["offset"]
    length = entry["length"]

    if offset < 0 or offset + abs(length) > len(buf):
        raise ValueError(f"segment at offset {offset} len {length} out of bounds")

    seg_buf = buf[offset: offset + abs(length)]
    le = hdr["little_endian"]
    r = _Reader(seg_buf, little_endian=le)

    seg_len_field = r.i32()
    seg_type = r.u32()
    comp_flag = r.u32()

    if comp_flag == 2:
        # ZLIB-compressed
        uncompressed_len = r.i32()
        compressed = r.raw(r.remaining())
        try:
            payload = zlib.decompress(compressed)
        except zlib.error as exc:
            raise ValueError(f"zlib decompress failed: {exc}")
    else:
        payload = r.raw(r.remaining())

    return payload, seg_type


# ─── LSG / assembly tree ──────────────────────────────────────────────────────

# JT node type codes embedded in the LSG payload
_NODE_ASSEMBLY   = 0x10DD1001
_NODE_PART       = 0x10DD1002
_NODE_INSTANCE   = 0x10DD1003
_NODE_SHAPE      = 0x10DD1004
_NODE_RANGE_LOD  = 0x10DD1005
_NODE_SWITCH     = 0x10DD1006
_NODE_META       = 0x10DD100A


def _parse_lsg_segment(payload: bytes, le: bool) -> dict:
    """
    Parse a Logical Scene Graph segment.

    LSG payload:
      uint32  graph_element_count
      For each element:
        uint32  element_type_id
        uint32  node_id           (local int)
        [variable content by type]

    We walk the list and reconstruct the tree by maintaining a parent-stack
    pattern.  Returns {"nodes": [...], "root_id": int}.
    """
    r = _Reader(payload, little_endian=le)
    elem_count = r.u32()

    flat_nodes: dict[int, dict] = {}
    children_map: dict[int, list[int]] = {}
    parent_stack: list[int] = []
    root_node_id: Optional[int] = None

    for _ in range(elem_count):
        if r.remaining() < 8:
            break
        etype = r.u32()
        nid = r.u32()

        node: dict = {
            "type_id": etype,
            "id": str(nid),
            "name": "",
            "transform": None,
            "shape_segment_ids": [],
            "metadata": {},
        }

        try:
            if etype in (_NODE_ASSEMBLY, _NODE_PART, _NODE_INSTANCE, _NODE_SWITCH, _NODE_RANGE_LOD):
                node = _read_base_node(r, node)
            elif etype == _NODE_SHAPE:
                node = _read_shape_node(r, node)
            elif etype == _NODE_META:
                node = _read_meta_node(r, node)
            else:
                # Unknown type — skip 4-byte reserved field and continue
                if r.remaining() >= 4:
                    r.u32()
        except EOFError:
            break

        flat_nodes[nid] = node
        children_map.setdefault(nid, [])

        if parent_stack:
            children_map[parent_stack[-1]].append(nid)
        else:
            root_node_id = nid

        # Push/pop: assemblies and part-instances push; leaf nodes don't.
        if etype in (_NODE_ASSEMBLY, _NODE_SWITCH, _NODE_RANGE_LOD, _NODE_INSTANCE):
            child_count = flat_nodes[nid].get("_child_count", 0)
            if child_count > 0:
                parent_stack.append(nid)
            # Mark for pop after all children consumed — simplistic depth tracking
            flat_nodes[nid]["_remaining_children"] = child_count
        elif parent_stack:
            # After adding a leaf, decrement parent's remaining count
            pid = parent_stack[-1]
            flat_nodes[pid]["_remaining_children"] -= 1
            if flat_nodes[pid]["_remaining_children"] <= 0:
                parent_stack.pop()

    return {"flat": flat_nodes, "children": children_map, "root_id": root_node_id}


def _read_base_node(r: _Reader, node: dict) -> dict:
    """Read attributes common to assembly/part/instance nodes."""
    attr_flags = r.u32()

    # Name (if name flag is set)
    if attr_flags & 0x01:
        node["name"] = r.counted_string()

    # Transform (if transform flag is set)
    if attr_flags & 0x02:
        node["transform"] = r.matrix4x4()

    # Child count for assembly nodes
    if attr_flags & 0x04:
        node["_child_count"] = r.u32()
    else:
        node["_child_count"] = 0

    # Shape references (if shape flag set)
    if attr_flags & 0x08:
        n_shapes = r.u32()
        for _ in range(n_shapes):
            node["shape_segment_ids"].append(r.guid())

    return node


def _read_shape_node(r: _Reader, node: dict) -> dict:
    """Read a shape / LOD node."""
    attr_flags = r.u32()
    if attr_flags & 0x01:
        node["name"] = r.counted_string()
    n_lod = r.u32()
    for _ in range(n_lod):
        if r.remaining() >= 16:
            node["shape_segment_ids"].append(r.guid())
    node["_child_count"] = 0
    return node


def _read_meta_node(r: _Reader, node: dict) -> dict:
    """Read metadata key-value pairs."""
    if r.remaining() < 4:
        return node
    n_props = r.u32()
    for _ in range(n_props):
        if r.remaining() < 4:
            break
        key = r.counted_string()
        vtype = r.u8()
        value: Any = None
        try:
            if vtype == 1:    value = r.i32()
            elif vtype == 2:  value = r.f32()
            elif vtype == 3:  value = r.f64()
            elif vtype == 4:  value = r.counted_string()
            else:             value = r.u32()  # unknown type → consume 4 bytes
        except EOFError:
            break
        node["metadata"][key] = value
    node["_child_count"] = 0
    return node


def _build_tree(lsg: dict) -> list[dict]:
    """Convert flat LSG map + children_map into a nested tree."""
    flat = lsg["flat"]
    children = lsg["children"]
    root_id = lsg["root_id"]

    if root_id is None:
        return []

    def _recurse(nid: int) -> dict:
        n = flat.get(nid, {"id": str(nid), "name": "", "transform": None,
                            "shape_segment_ids": [], "metadata": {}})
        child_ids = children.get(nid, [])
        return {
            "id": n["id"],
            "name": n.get("name", ""),
            "transform": n.get("transform"),
            "shape_segment_ids": n.get("shape_segment_ids", []),
            "metadata": n.get("metadata", {}),
            "children": [_recurse(c) for c in child_ids],
        }

    return [_recurse(root_id)]


# ─── Tessellation segment ─────────────────────────────────────────────────────

def _parse_tess_segment(payload: bytes, le: bool) -> Optional[dict]:
    """
    Parse a TriStripSet tessellation segment.

    Payload layout (simplified — JT tess format):
      uint32  version
      float32 [8] — reserved / bounding box
      uint32  vertex_count
      float32[vertex_count * 3]  — x,y,z per vertex
      uint32  normal_count       — may be zero
      [float32[normal_count * 3]]
      uint32  strip_count
      For each strip:
        uint32  strip_len
        int32[strip_len]  — vertex indices; negative = degenerate restart

    We triangulate the strips via the standard tristrip algorithm.
    Returns {"vertices": [[x,y,z],...], "indices": [i0,i1,i2,...]} or None.
    """
    r = _Reader(payload, little_endian=le)

    if r.remaining() < 4:
        return None

    _ver = r.u32()

    # Bounding box (8 floats)
    if r.remaining() < 32:
        return None
    r.raw(32)

    if r.remaining() < 4:
        return None
    vertex_count = r.u32()

    if vertex_count == 0 or vertex_count > 10_000_000:
        return None

    if r.remaining() < vertex_count * 12:
        return None

    vertices = []
    for _ in range(vertex_count):
        x = r.f32()
        y = r.f32()
        z = r.f32()
        vertices.append([x, y, z])

    # Normals (skip)
    if r.remaining() < 4:
        return {"vertices": vertices, "indices": []}
    normal_count = r.u32()
    if normal_count > 0 and r.remaining() >= normal_count * 12:
        r.raw(normal_count * 12)

    # Triangle strips
    if r.remaining() < 4:
        return {"vertices": vertices, "indices": []}
    strip_count = r.u32()

    indices = []
    for _ in range(strip_count):
        if r.remaining() < 4:
            break
        strip_len = r.u32()
        if strip_len == 0 or r.remaining() < strip_len * 4:
            break

        strip = []
        for _ in range(strip_len):
            idx = r.i32()
            strip.append(idx)

        # Tristrip → triangles
        tri_indices = _tristrip_to_triangles(strip, vertex_count)
        indices.extend(tri_indices)

    return {"vertices": vertices, "indices": indices}


def _tristrip_to_triangles(strip: list[int], vertex_count: int) -> list[int]:
    """
    Convert a triangle strip (with possible negative degenerate markers) to
    a flat triangle index list.  Negative indices signal degenerate restart.
    """
    out: list[int] = []
    window: list[int] = []
    flip = False

    for raw_idx in strip:
        if raw_idx < 0:
            # Degenerate triangle restart — reset window
            window.clear()
            flip = False
            continue

        if raw_idx >= vertex_count:
            # Out-of-range index — skip safely
            window.clear()
            flip = False
            continue

        window.append(raw_idx)
        if len(window) > 3:
            window.pop(0)

        if len(window) == 3:
            a, b, c = window
            if a == b or b == c or a == c:
                flip = not flip
                continue
            if flip:
                out.extend([a, c, b])
            else:
                out.extend([a, b, c])
            flip = not flip

    return out


# ─── Top-level parse ──────────────────────────────────────────────────────────

def parse_jt(data: bytes) -> dict:
    """
    Parse a JT file from raw bytes.

    Returns a Kerf model dict:
      {
        "ok": True,
        "version": str,
        "assembly": [node, ...],
        "meshes": { guid: {"vertices": [...], "indices": [...]} },
        "properties": { guid: {key: value} },
        "warnings": [str, ...]
      }
    Or on failure:
      {"ok": False, "reason": str}
    """
    warns: list[str] = []

    try:
        # 1. Header
        try:
            hdr = _parse_header(data)
        except ValueError as e:
            return {"ok": False, "reason": str(e)}

        le = hdr["little_endian"]
        version = hdr["version"]
        major = hdr["major"]

        # 2. TOC
        try:
            toc = _parse_toc(data, hdr)
        except ValueError as e:
            return {"ok": False, "reason": f"TOC parse error: {e}"}

        if not toc:
            return {"ok": False, "reason": "TOC has no entries"}

        # 3. Walk segments
        lsg_data: Optional[dict] = None
        meshes: dict[str, dict] = {}
        properties: dict[str, dict] = {}
        tess_segments: dict[str, dict] = {}

        for entry in toc:
            try:
                payload, seg_type = _read_segment_data(data, entry, hdr)
            except (ValueError, EOFError) as e:
                warns.append(f"segment {entry['id']}: read error — {e}")
                continue

            if seg_type == _SEG_TYPE_XTWB:
                warns.append(f"segment {entry['id']}: XT B-rep skipped (unsupported)")
                continue

            if seg_type == _SEG_TYPE_LSG:
                try:
                    lsg_data = _parse_lsg_segment(payload, le)
                except Exception as e:
                    warns.append(f"LSG segment parse error: {e}")

            elif seg_type in (_SEG_TYPE_TESS, _SEG_TYPE_SHAPE):
                try:
                    mesh = _parse_tess_segment(payload, le)
                    if mesh is not None:
                        tess_segments[entry["id"]] = mesh
                except Exception as e:
                    warns.append(f"tess segment {entry['id']}: parse error — {e}")

            elif seg_type == _SEG_TYPE_META:
                try:
                    props = _parse_meta_segment(payload, le)
                    if props:
                        properties[entry["id"]] = props
                except Exception as e:
                    warns.append(f"meta segment {entry['id']}: parse error — {e}")

        # 4. Build assembly tree
        assembly: list[dict] = []
        if lsg_data is not None:
            try:
                assembly = _build_tree(lsg_data)
            except Exception as e:
                warns.append(f"assembly tree build error: {e}")

        # 5. Attach meshes — map shape_segment_ids → mesh dict
        for node_id, mesh in tess_segments.items():
            meshes[node_id] = mesh

        # 6. Attach per-node mesh references by walking the tree
        def _collect_node_meshes(node: dict) -> None:
            for seg_id in node.get("shape_segment_ids", []):
                if seg_id in tess_segments and seg_id not in meshes:
                    meshes[seg_id] = tess_segments[seg_id]
            for child in node.get("children", []):
                _collect_node_meshes(child)

        for root in assembly:
            _collect_node_meshes(root)

        return {
            "ok": True,
            "version": version,
            "toc_entry_count": len(toc),
            "assembly": assembly,
            "meshes": meshes,
            "properties": properties,
            "warnings": warns,
        }

    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}"}


def _parse_meta_segment(payload: bytes, le: bool) -> dict:
    """Parse a metadata segment into a {key: value} dict."""
    r = _Reader(payload, little_endian=le)
    out: dict = {}
    if r.remaining() < 4:
        return out
    n = r.u32()
    for _ in range(n):
        if r.remaining() < 4:
            break
        key = r.counted_string()
        if r.remaining() < 1:
            break
        vtype = r.u8()
        try:
            if vtype == 1:    out[key] = r.i32()
            elif vtype == 2:  out[key] = r.f32()
            elif vtype == 3:  out[key] = r.f64()
            elif vtype == 4:  out[key] = r.counted_string()
            else:             r.u32()  # skip unknown
        except EOFError:
            break
    return out


# ─── Fixture builder (used by tests and as public API) ───────────────────────

def make_minimal_jt(
    *,
    version: str = "10.0",
    n_verts: int = 3,
    include_assembly: bool = True,
    include_tess: bool = True,
    include_meta: bool = False,
    part_name: str = "TestPart",
) -> bytes:
    """
    Build a minimal valid JT file in memory (little-endian).

    This is used by the test suite to construct synthetic byte fixtures.
    Returns raw bytes of a JT file with:
      - A valid v10 header
      - A TOC with 1 (tess) or 2 (tess + LSG) entries
      - One tessellated triangle segment (3 verts, 1 triangle)
      - Optionally one LSG segment with a single part node

    Layout sizes are computed and written exactly so the parser can round-trip.
    """
    # ── Build tess payload (uncompressed) ────────────────────────────────────
    tess_payload = io.BytesIO()

    def pw_u32(v: int) -> bytes: return struct.pack("<I", v)
    def pw_i32(v: int) -> bytes: return struct.pack("<i", v)
    def pw_f32(v: float) -> bytes: return struct.pack("<f", v)
    def pw_f64(v: float) -> bytes: return struct.pack("<d", v)

    # version
    tess_payload.write(pw_u32(1))
    # bounding box (8 floats = 32 bytes)
    tess_payload.write(b"\x00" * 32)
    # vertex count + vertices
    tess_payload.write(pw_u32(n_verts))
    verts_data = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, 1.0, 0.0),
    ]
    # Pad to n_verts if needed
    while len(verts_data) < n_verts:
        verts_data.append((float(len(verts_data)), 0.0, 0.0))
    for x, y, z in verts_data[:n_verts]:
        tess_payload.write(pw_f32(x))
        tess_payload.write(pw_f32(y))
        tess_payload.write(pw_f32(z))
    # normals count = 0
    tess_payload.write(pw_u32(0))
    # strip count = 1, strip_len = 3, indices 0,1,2
    tess_payload.write(pw_u32(1))
    tess_payload.write(pw_u32(3))
    tess_payload.write(pw_i32(0))
    tess_payload.write(pw_i32(1))
    tess_payload.write(pw_i32(2))

    tess_raw = tess_payload.getvalue()

    # ── Build LSG payload ─────────────────────────────────────────────────────
    lsg_payload = io.BytesIO()

    if include_assembly:
        # 1 element: a part node
        lsg_payload.write(pw_u32(1))  # element_count

        # element type: part
        lsg_payload.write(pw_u32(_NODE_PART))
        # node id
        lsg_payload.write(pw_u32(1))
        # attr_flags: 0x01 = has name; no transform, no children, no shapes
        lsg_payload.write(pw_u32(0x01))
        # name (counted UTF-16LE)
        name_enc = part_name.encode("utf-16-le")
        lsg_payload.write(struct.pack("<H", len(part_name)))
        lsg_payload.write(name_enc)

    lsg_raw = lsg_payload.getvalue()

    # ── Wrap each payload in a segment frame ──────────────────────────────────
    def _wrap_segment(seg_type: int, payload_bytes: bytes) -> bytes:
        """
        Segment frame:
          int32  segment_length   (4 + 4 + 4 + len(payload))
          uint32 segment_type_id
          uint32 compression_flag  (0 = none)
          bytes  payload
        """
        total = 4 + 4 + 4 + len(payload_bytes)
        return (
            struct.pack("<i", total)
            + struct.pack("<I", seg_type)
            + struct.pack("<I", 0)          # uncompressed
            + payload_bytes
        )

    tess_seg = _wrap_segment(_SEG_TYPE_TESS, tess_raw)
    lsg_seg  = _wrap_segment(_SEG_TYPE_LSG,  lsg_raw) if include_assembly else b""

    # ── TOC ──────────────────────────────────────────────────────────────────
    # Layout (written after the header at byte 80):
    #   uint32  entry_count
    #   For each entry:
    #     GUID (16 bytes = 4 uint32)
    #     int64  offset  (8 bytes)
    #     int32  length  (4 bytes)
    #     uint32 attributes (4 bytes)
    # Entry size = 16 + 8 + 4 + 4 = 32 bytes

    HEADER_SIZE = 80
    # Segments come after header + TOC
    n_entries = (1 if include_tess else 0) + (1 if include_assembly else 0)
    TOC_SIZE = 4 + n_entries * 32

    # Segment positions
    seg_start = HEADER_SIZE + TOC_SIZE
    tess_offset = seg_start
    lsg_offset  = tess_offset + len(tess_seg) if include_tess else seg_start

    tess_guid = uuid.UUID("10dd1046-0000-0000-0000-000000000001")
    lsg_guid  = uuid.UUID("10dd1035-0000-0000-0000-000000000001")

    def _guid_bytes(g: uuid.UUID) -> bytes:
        raw = g.bytes  # 16 bytes, big-endian
        # Unpack as 4 big-endian uint32 then repack as 4 little-endian uint32
        a, b, c, d = struct.unpack(">IIII", raw)
        return struct.pack("<IIII", a, b, c, d)

    toc = io.BytesIO()
    toc.write(struct.pack("<I", n_entries))

    if include_tess:
        toc.write(_guid_bytes(tess_guid))
        toc.write(struct.pack("<q", tess_offset))
        toc.write(struct.pack("<i", len(tess_seg)))
        toc.write(struct.pack("<I", 0))  # attributes

    if include_assembly:
        toc.write(_guid_bytes(lsg_guid))
        toc.write(struct.pack("<q", lsg_offset))
        toc.write(struct.pack("<i", len(lsg_seg)))
        toc.write(struct.pack("<I", 0))

    toc_raw = toc.getvalue()
    toc_offset = HEADER_SIZE  # TOC starts right after the 80-byte header

    # ── Header ───────────────────────────────────────────────────────────────
    hdr = io.BytesIO()
    hdr.write(b"Version ")                          # magic (8)
    ver_bytes = version.encode("ascii")[:10].ljust(10, b"\x00")
    hdr.write(ver_bytes)                            # version string (10)
    hdr.write(b"\x01")                             # byte_order: 1 = little-endian
    hdr.write(struct.pack("<i", 0))                # reserved int32 (4)
    hdr.write(struct.pack("<q", toc_offset))       # TOC offset (8)
    # Pad to 80 bytes
    current = hdr.tell()
    if current < 80:
        hdr.write(b"\x00" * (80 - current))

    hdr_raw = hdr.getvalue()[:80]

    return hdr_raw + toc_raw + tess_seg + lsg_seg


# ─── LLM tool ────────────────────────────────────────────────────────────────

_import_jt_spec = ToolSpec(
    name="import_jt",
    description=(
        "Import a Siemens JT file (v8–v10) into the current project. "
        "Accepts a blob_id or storage_key pointing to the uploaded .jt binary. "
        "Parses the assembly tree, tessellated meshes, and metadata properties. "
        "Creates Kerf files (one .mesh per JT part) under an import folder and "
        "returns the assembly tree, mesh statistics, and any warnings. "
        "XT B-rep segments are skipped with a warning (tessellation only). "
        "Gate: imports.jt capability."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the target Kerf project.",
            },
            "file_blob_id_or_storage_key": {
                "type": "string",
                "description": "Blob ID or storage key for the .jt binary.",
            },
            "import_folder": {
                "type": "string",
                "description": "Path in the project tree for imported files. Defaults to /jt_import.",
            },
        },
        "required": ["project_id", "file_blob_id_or_storage_key"],
    },
)


@register(_import_jt_spec, write=True)
async def run_import_jt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    project_id = a.get("project_id", "").strip()
    blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
    import_folder = a.get("import_folder", "/jt_import").strip()

    if not project_id:
        return err_payload("project_id is required", "BAD_ARGS")
    if not blob_ref:
        return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")

    # Resolve blob
    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    try:
        blob_bytes = await ctx.storage.get(blob_ref)
    except Exception as exc:
        return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

    if not blob_bytes:
        return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

    model = parse_jt(blob_bytes)
    if not model.get("ok"):
        return err_payload(model.get("reason", "JT parse failed"), "PARSE_ERROR")

    # Persist each mesh as a Kerf file
    created: list[dict] = []
    try:
        _pid = uuid.UUID(project_id)
    except Exception:
        return err_payload("project_id must be a valid UUID", "BAD_ARGS")

    for seg_id, mesh in model.get("meshes", {}).items():
        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
            "vertices": mesh["vertices"],
            "indices": mesh["indices"],
        })
        try:
            ctx.pool.execute(
                "insert into files (id, project_id, name, kind, content, created_at, updated_at) "
                "values ($1, $2, $3, $4, $5, now(), now())",
                fid, _pid,
                f"{import_folder}/{seg_id}.mesh",
                "mesh",
                content,
            )
            created.append({
                "file_id": str(fid),
                "name": f"{import_folder}/{seg_id}.mesh",
                "vertices": len(mesh["vertices"]),
                "triangles": len(mesh["indices"]) // 3,
            })
        except Exception as exc:
            model["warnings"].append(f"failed to write mesh {seg_id}: {exc}")

    return ok_payload({
        "ok": True,
        "version": model["version"],
        "toc_entry_count": model["toc_entry_count"],
        "assembly_node_count": _count_nodes(model["assembly"]),
        "meshes_created": len(created),
        "created_files": created,
        "warnings": model["warnings"],
    })


def _count_nodes(nodes: list[dict]) -> int:
    total = 0
    for n in nodes:
        total += 1
        total += _count_nodes(n.get("children", []))
    return total


# Expose TOOLS list for the plugin loader (kerf_imports.plugin._register_tools
# iterates mod.TOOLS when present).
TOOLS = [(_import_jt_spec.name, _import_jt_spec, run_import_jt)]
