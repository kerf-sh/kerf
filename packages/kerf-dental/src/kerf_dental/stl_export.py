"""
kerf_dental.stl_export — Binary and ASCII STL export for dental meshes.

Public API
----------
export_stl_binary(vertices, faces, path)
    Write a binary STL file from a triangle mesh.

export_stl_ascii(vertices, faces, path, solid_name)
    Write an ASCII STL file.

stl_bytes_binary(vertices, faces) -> bytes
    Return binary STL as bytes (no file I/O; useful for in-memory export or
    streaming to a mill controller).

Notes
-----
STL format (ISO/ASTM 52915 successor; original 3D Systems spec):
  Binary: 80-byte header, uint32 triangle count, then per-triangle:
    float32[3] normal, float32[3][3] vertex(1..3), uint16 attribute_byte_count
  ASCII:  "solid <name>" / "facet normal nx ny nz" / "outer loop" /
          "vertex x y z" (×3) / "endloop" / "endfacet" / "endsolid"

Normals are computed from vertex cross products (right-hand rule, outward).

References
----------
- 3D Systems, "StereoLithography Interface Specification", 1989.
- ISO/ASTM 52915:2020, "Standard specification for additive manufacturing file format (AMF)".
"""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path
from typing import Union

import numpy as np


# ---------------------------------------------------------------------------
# Normal computation helper
# ---------------------------------------------------------------------------

def _triangle_normal(v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """Compute the outward unit normal for triangle (v0, v1, v2) via cross product."""
    a = v1 - v0
    b = v2 - v0
    n = np.cross(a, b)
    norm = math.sqrt(float(n[0] ** 2 + n[1] ** 2 + n[2] ** 2))
    if norm < 1e-30:
        return np.zeros(3, dtype=np.float32)
    return (n / norm).astype(np.float32)


# ---------------------------------------------------------------------------
# Binary STL
# ---------------------------------------------------------------------------

def stl_bytes_binary(
    vertices: np.ndarray,
    faces: np.ndarray,
    header: str = "Kerf dental mesh",
) -> bytes:
    """
    Serialise a triangle mesh to binary STL format (in memory).

    Parameters
    ----------
    vertices : (V, 3) array-like — vertex coordinates in mm.
    faces    : (F, 3) array-like — triangle face indices (int).
    header   : 80-character header string (truncated / padded to exactly 80 bytes).

    Returns
    -------
    bytes — binary STL payload.

    Raises
    ------
    ValueError if vertices or faces have wrong shape.
    """
    verts = np.asarray(vertices, dtype=np.float32)
    tris = np.asarray(faces, dtype=np.int32)

    if verts.ndim != 2 or verts.shape[1] != 3:
        raise ValueError(f"vertices must be (V, 3); got shape {verts.shape}")
    if tris.ndim != 2 or tris.shape[1] != 3:
        raise ValueError(f"faces must be (F, 3); got shape {tris.shape}")

    n_tris = len(tris)

    buf = io.BytesIO()

    # 80-byte header (padded / truncated)
    hdr_bytes = header.encode("ascii", errors="replace")[:80]
    hdr_bytes = hdr_bytes.ljust(80, b"\x00")
    buf.write(hdr_bytes)

    # uint32: number of triangles
    buf.write(struct.pack("<I", n_tris))

    # Per-triangle: normal (3×float32), 3 vertices (3×3×float32), attribute (uint16)
    for tri in tris:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        normal = _triangle_normal(v0, v1, v2)

        buf.write(struct.pack("<fff", float(normal[0]), float(normal[1]), float(normal[2])))
        buf.write(struct.pack("<fff", float(v0[0]), float(v0[1]), float(v0[2])))
        buf.write(struct.pack("<fff", float(v1[0]), float(v1[1]), float(v1[2])))
        buf.write(struct.pack("<fff", float(v2[0]), float(v2[1]), float(v2[2])))
        buf.write(struct.pack("<H", 0))  # attribute byte count = 0

    return buf.getvalue()


def export_stl_binary(
    vertices: np.ndarray,
    faces: np.ndarray,
    path: Union[str, Path],
    header: str = "Kerf dental mesh",
) -> int:
    """
    Write a binary STL file from a triangle mesh.

    Parameters
    ----------
    vertices : (V, 3) array-like — vertex coordinates in mm.
    faces    : (F, 3) array-like — triangle face indices.
    path     : file path (str or Path).
    header   : up to 80-character header.

    Returns
    -------
    int — number of triangles written.
    """
    data = stl_bytes_binary(vertices, faces, header=header)
    path = Path(path)
    path.write_bytes(data)
    # Number of triangles = bytes after header (80) and count (4), each tri is 50 bytes
    n_tris = len(np.asarray(faces, dtype=np.int32))
    return n_tris


# ---------------------------------------------------------------------------
# ASCII STL
# ---------------------------------------------------------------------------

def export_stl_ascii(
    vertices: np.ndarray,
    faces: np.ndarray,
    path: Union[str, Path],
    solid_name: str = "kerf_dental",
) -> int:
    """
    Write an ASCII STL file from a triangle mesh.

    Parameters
    ----------
    vertices   : (V, 3) array-like — vertex coordinates in mm.
    faces      : (F, 3) array-like — triangle face indices.
    path       : file path (str or Path).
    solid_name : name used in 'solid <name>' and 'endsolid <name>' lines.

    Returns
    -------
    int — number of triangles written.
    """
    verts = np.asarray(vertices, dtype=np.float32)
    tris = np.asarray(faces, dtype=np.int32)

    if verts.ndim != 2 or verts.shape[1] != 3:
        raise ValueError(f"vertices must be (V, 3); got shape {verts.shape}")
    if tris.ndim != 2 or tris.shape[1] != 3:
        raise ValueError(f"faces must be (F, 3); got shape {tris.shape}")

    lines = [f"solid {solid_name}"]
    for tri in tris:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        v0, v1, v2 = verts[i0], verts[i1], verts[i2]
        normal = _triangle_normal(v0, v1, v2)
        lines.append(
            f"  facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}"
        )
        lines.append("    outer loop")
        lines.append(f"      vertex {float(v0[0]):.6e} {float(v0[1]):.6e} {float(v0[2]):.6e}")
        lines.append(f"      vertex {float(v1[0]):.6e} {float(v1[1]):.6e} {float(v1[2]):.6e}")
        lines.append(f"      vertex {float(v2[0]):.6e} {float(v2[1]):.6e} {float(v2[2]):.6e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {solid_name}")

    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return len(tris)


# ---------------------------------------------------------------------------
# Crown B-rep → STL helper (convenience wrapper)
# ---------------------------------------------------------------------------

def crown_to_stl_bytes(crown_result, fmt: str = "binary") -> bytes:
    """
    Export a CrownResult (from design_crown_anatomic) to STL bytes.

    Extracts the triangle mesh from the B-rep shell by reading each Face's
    outer loop coedge start-points.

    Parameters
    ----------
    crown_result : CrownResult — output of design_crown_anatomic() or design_crown().
    fmt          : 'binary' (default) or 'ascii'.

    Returns
    -------
    bytes — STL file bytes.

    Raises
    ------
    RuntimeError if the B-rep cannot be triangulated (non-triangular faces).
    """
    body = crown_result.body
    shell = body.solids[0].shells[0]

    vert_list = []
    face_list = []
    vert_map: dict = {}

    def _get_or_add(pt: tuple) -> int:
        key = (round(pt[0], 7), round(pt[1], 7), round(pt[2], 7))
        if key not in vert_map:
            vert_map[key] = len(vert_list)
            vert_list.append(np.array(key, dtype=np.float32))
        return vert_map[key]

    for face in shell.faces:
        outer = face.outer_loop()
        if outer is None:
            continue
        coedges = list(outer.coedges)
        if len(coedges) != 3:
            raise RuntimeError(
                f"crown_to_stl_bytes: non-triangular face with {len(coedges)} edges; "
                "only triangle-mesh crowns from design_crown_anatomic are supported."
            )
        pts = [ce.start_point() for ce in coedges]
        idxs = [_get_or_add(tuple(float(c) for c in p)) for p in pts]
        face_list.append(idxs)

    if not vert_list:
        raise RuntimeError("crown_to_stl_bytes: no triangular faces found in B-rep")

    vertices = np.array(vert_list, dtype=np.float32)
    faces = np.array(face_list, dtype=np.int32)

    if fmt == "ascii":
        buf = io.BytesIO()
        lines = ["solid kerf_crown"]
        for tri in faces:
            v0, v1, v2 = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
            n = _triangle_normal(v0, v1, v2)
            lines.append(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}")
            lines.append("    outer loop")
            for v in (v0, v1, v2):
                lines.append(f"      vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}")
            lines.append("    endloop")
            lines.append("  endfacet")
        lines.append("endsolid kerf_crown")
        return ("\n".join(lines) + "\n").encode("ascii")

    return stl_bytes_binary(vertices, faces, header="Kerf dental crown")
