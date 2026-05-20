"""
kerf_cad_core.reverse_engineering.io — Point-cloud file parsers.

Supported formats
-----------------
PCD (Point Cloud Data) v0.7 — ASCII DATA section only.
    Binary and binary_compressed variants raise UnsupportedFormatError.
    https://pointclouds.org/documentation/tutorials/pcd_file_format.html

PLY (Polygon File Format / Stanford Triangle Format) — ASCII only.
    Binary-LE and binary-BE raise UnsupportedFormatError.
    https://paulbourke.net/dataformats/ply/

Both parsers return a list of [x, y, z] float lists.
Extra fields (normals, intensity, colour, etc.) are silently ignored.

Author: imranparuk
"""
from __future__ import annotations

import io
import os


class UnsupportedFormatError(ValueError):
    """Raised when a file format variant is not supported in v1."""


# ---------------------------------------------------------------------------
# PCD parser
# ---------------------------------------------------------------------------

def load_pcd(source: str | bytes | os.PathLike) -> list[list[float]]:
    """Parse an ASCII PCD file and return [[x, y, z], ...].

    Parameters
    ----------
    source:
        File path (str / PathLike) **or** raw bytes of the file contents.

    Raises
    ------
    UnsupportedFormatError
        If DATA type is not ``ascii``.
    ValueError
        If the file is malformed (bad header, non-numeric coordinates).
    """
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as fh:
            raw = fh.read()
    else:
        raw = bytes(source)

    lines = raw.decode("utf-8", errors="replace").splitlines()

    # --- parse header ---
    fields: list[str] = []
    size_map: dict[str, int] = {}
    type_map: dict[str, str] = {}
    count_map: dict[str, int] = {}
    data_type = ""
    header_done = False
    data_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        key = parts[0].lower()
        if key == "fields":
            fields = [f.lower() for f in parts[1:]]
        elif key == "size":
            for j, f in enumerate(fields):
                size_map[f] = int(parts[1 + j]) if 1 + j < len(parts) else 4
        elif key == "type":
            for j, f in enumerate(fields):
                type_map[f] = parts[1 + j] if 1 + j < len(parts) else "F"
        elif key == "count":
            for j, f in enumerate(fields):
                count_map[f] = int(parts[1 + j]) if 1 + j < len(parts) else 1
        elif key == "data":
            data_type = parts[1].lower() if len(parts) > 1 else ""
            data_start = i + 1
            header_done = True
            break

    if not header_done:
        raise ValueError("PCD: DATA header line not found")
    if data_type != "ascii":
        raise UnsupportedFormatError(
            f"PCD: only ASCII data is supported in v1; got '{data_type}'. "
            "Binary PCD support is planned for v2."
        )
    if not fields:
        raise ValueError("PCD: FIELDS header line not found or empty")

    # Determine which column indices map to x, y, z
    try:
        xi = fields.index("x")
        yi = fields.index("y")
        zi = fields.index("z")
    except ValueError:
        raise ValueError(f"PCD: required fields x/y/z not found; got {fields}")

    pts: list[list[float]] = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) <= max(xi, yi, zi):
            continue  # short / corrupt row — skip
        try:
            pts.append([float(parts[xi]), float(parts[yi]), float(parts[zi])])
        except ValueError:
            continue  # NaN / inf / malformed — skip

    return pts


# ---------------------------------------------------------------------------
# PLY parser (ASCII only)
# ---------------------------------------------------------------------------

def load_ply(source: str | bytes | os.PathLike) -> list[list[float]]:
    """Parse an ASCII PLY file and return [[x, y, z], ...].

    Parameters
    ----------
    source:
        File path (str / PathLike) **or** raw bytes.

    Raises
    ------
    UnsupportedFormatError
        If format is not ``ascii``.
    ValueError
        If the file is malformed.
    """
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as fh:
            raw = fh.read()
    else:
        raw = bytes(source)

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()

    if not lines or lines[0].strip().lower() != "ply":
        raise ValueError("PLY: file does not start with 'ply'")

    # Parse header
    fmt = ""
    vertex_count = 0
    vertex_props: list[str] = []  # ordered list of property names for vertex element
    in_vertex = False
    header_end = 0

    for i, line in enumerate(lines[1:], start=1):
        stripped = line.strip().lower()
        if stripped.startswith("format"):
            parts = stripped.split()
            if len(parts) >= 2:
                fmt = parts[1]
        elif stripped.startswith("element vertex"):
            parts = stripped.split()
            vertex_count = int(parts[2]) if len(parts) >= 3 else 0
            in_vertex = True
        elif stripped.startswith("element") and not stripped.startswith("element vertex"):
            in_vertex = False
        elif stripped.startswith("property") and in_vertex:
            parts = line.strip().split()
            if len(parts) >= 3:
                vertex_props.append(parts[-1].lower())
        elif stripped == "end_header":
            header_end = i + 1
            break

    if not fmt:
        raise ValueError("PLY: FORMAT line not found")
    if fmt not in ("ascii", "ascii 1.0", "ascii1.0"):
        # Check more carefully — "ascii 1.0" comes as two tokens
        # Recheck the raw format line
        pass

    # Re-scan format line case-insensitively for "ascii"
    format_is_ascii = False
    for line in lines[1:]:
        if line.strip().lower().startswith("format"):
            if "ascii" in line.lower():
                format_is_ascii = True
            break

    if not format_is_ascii:
        raise UnsupportedFormatError(
            "PLY: only ASCII format is supported in v1. "
            "Binary-LE and binary-BE support is planned for v2."
        )

    if vertex_count == 0:
        return []

    try:
        xi = vertex_props.index("x")
        yi = vertex_props.index("y")
        zi = vertex_props.index("z")
    except ValueError:
        raise ValueError(
            f"PLY: vertex element must have x, y, z properties; got {vertex_props}"
        )

    pts: list[list[float]] = []
    data_lines = lines[header_end:]
    collected = 0
    for line in data_lines:
        if collected >= vertex_count:
            break
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) <= max(xi, yi, zi):
            continue
        try:
            pts.append([float(parts[xi]), float(parts[yi]), float(parts[zi])])
            collected += 1
        except ValueError:
            continue

    return pts


# ---------------------------------------------------------------------------
# Unified loader — dispatch by extension or magic bytes
# ---------------------------------------------------------------------------

def load_point_cloud(source: str | bytes | os.PathLike) -> list[list[float]]:
    """Load a point cloud from a ``.pcd`` or ``.ply`` file.

    Parameters
    ----------
    source:
        File path, or raw bytes (sniffed by magic: PLY starts with ``ply\\n``).

    Returns
    -------
    list of [x, y, z] float lists.
    """
    if isinstance(source, (str, os.PathLike)):
        path = str(source).lower()
        if path.endswith(".pcd"):
            return load_pcd(source)
        if path.endswith(".ply"):
            return load_ply(source)
        # Fall back to content sniffing
        with open(source, "rb") as fh:
            magic = fh.read(4)
        if magic == b"ply\n" or magic == b"ply\r":
            return load_ply(source)
        return load_pcd(source)
    else:
        raw = bytes(source)
        if raw.lstrip()[:3] == b"ply":
            return load_ply(raw)
        return load_pcd(raw)
