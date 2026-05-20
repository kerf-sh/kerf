"""
geom/io/obj.py
==============
Pure-Python OBJ read + write with group and MTL support (GK-80).

Wavefront OBJ format overview
------------------------------
An OBJ file is a plain-text geometry file.  Each meaningful line starts
with a keyword token:

    v   x y z [w]        — geometric vertex (w optional, ignored on read)
    vn  nx ny nz         — vertex normal
    vt  u v [w]          — texture coordinate (w optional)
    f   v[/vt[/vn]] ...  — polygon face (1-based indices, negative = relative)
    g   name [name ...]  — group name(s) for following faces
    usemtl name          — material name for following faces
    mtllib filename      — associate an MTL file
    o   name             — object name (parsed but not surfaced)
    s   group|off        — smoothing group (parsed but not surfaced)
    #   ...              — comment

MTL file keywords used here:
    newmtl name          — start a new material
    Kd r g b             — diffuse colour (0-1 float each)
    Ka r g b             — ambient colour
    Ks r g b             — specular colour
    Ns exponent          — specular exponent
    d alpha              — dissolve (opacity)
    Tr alpha             — transparency (1-d)
    map_Kd filename      — diffuse texture map
    illum n              — illumination model

Data model
----------
``read_obj`` returns a dict:

    {
        "verts":     [[x, y, z], ...],          # float list-of-lists
        "normals":   [[nx, ny, nz], ...],        # may be empty
        "texcoords": [[u, v], ...],              # may be empty
        "faces":     [
            {
                "verts":    [i, ...],            # 0-based vertex indices
                "normals":  [ni, ...] | None,    # 0-based or None
                "texcoords":[ti, ...] | None,    # 0-based or None
                "group":    str | None,
                "material": str | None,
            },
            ...
        ],
        "groups":    [str, ...],                 # ordered, unique group names seen
        "materials": {name: {kd, ka, ks, ...}}, # dict of material dicts; empty {}
        "mtllib":    str | None,                 # filename on the mtllib line
    }

``write_obj`` accepts:
    - a dict with ``"verts"`` and ``"faces"`` (as above or simple int-index lists)
    - any object with ``.verts``/``.vertices`` and ``.faces`` attributes

Public API
----------
``read_obj(path) -> dict``
``write_obj(path, mesh_or_body, *, groups=None, materials=None)``

Exceptions
----------
``ObjReadError``   — fatal parse errors
``ObjWriteError``  — fatal serialisation errors
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ObjReadError(Exception):
    """Raised when an OBJ (or companion MTL) file cannot be parsed."""


class ObjWriteError(Exception):
    """Raised when an OBJ (or companion MTL) file cannot be written."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_float_triple(parts: List[str], line_no: int, keyword: str) -> List[float]:
    """Parse exactly 3 floats from *parts*; raise ObjReadError on failure."""
    if len(parts) < 3:
        raise ObjReadError(
            f"line {line_no}: '{keyword}' expects 3 values, got {len(parts)}"
        )
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError as exc:
        raise ObjReadError(f"line {line_no}: cannot parse floats in '{keyword}': {exc}") from exc


def _parse_vertex(parts: List[str], line_no: int) -> List[float]:
    """Parse a 'v' line.  Accepts 3 or 4 components (w is discarded)."""
    if len(parts) < 3:
        raise ObjReadError(
            f"line {line_no}: 'v' expects at least 3 values, got {len(parts)}"
        )
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError as exc:
        raise ObjReadError(f"line {line_no}: cannot parse vertex: {exc}") from exc


def _parse_texcoord(parts: List[str], line_no: int) -> List[float]:
    """Parse a 'vt' line.  Accepts 1-3 components; always returns 2."""
    if len(parts) < 1:
        raise ObjReadError(f"line {line_no}: 'vt' expects at least 1 value")
    try:
        u = float(parts[0])
        v = float(parts[1]) if len(parts) >= 2 else 0.0
        return [u, v]
    except ValueError as exc:
        raise ObjReadError(f"line {line_no}: cannot parse texcoord: {exc}") from exc


def _resolve_index(raw: int, count: int, line_no: int, kind: str) -> int:
    """Convert a 1-based OBJ index (positive or negative) to 0-based."""
    if raw == 0:
        raise ObjReadError(f"line {line_no}: {kind} index 0 is invalid in OBJ")
    if raw > 0:
        idx = raw - 1
    else:
        idx = count + raw  # negative relative index
    if idx < 0 or idx >= count:
        raise ObjReadError(
            f"line {line_no}: {kind} index {raw} out of range (have {count})"
        )
    return idx


def _parse_face_token(token: str, n_verts: int, n_texcoords: int, n_normals: int,
                      line_no: int) -> Tuple[int, Optional[int], Optional[int]]:
    """
    Parse one face token of the form ``v``, ``v/vt``, ``v//vn``, or ``v/vt/vn``.
    Returns ``(vi, ti, ni)`` as 0-based indices; ti / ni may be None.
    """
    parts = token.split("/")
    try:
        vi = _resolve_index(int(parts[0]), n_verts, line_no, "vertex")
    except ValueError as exc:
        raise ObjReadError(f"line {line_no}: bad face vertex '{parts[0]}': {exc}") from exc

    ti: Optional[int] = None
    ni: Optional[int] = None

    if len(parts) >= 2 and parts[1] != "":
        try:
            ti = _resolve_index(int(parts[1]), n_texcoords, line_no, "texcoord")
        except ValueError as exc:
            raise ObjReadError(
                f"line {line_no}: bad face texcoord '{parts[1]}': {exc}"
            ) from exc

    if len(parts) >= 3 and parts[2] != "":
        try:
            ni = _resolve_index(int(parts[2]), n_normals, line_no, "normal")
        except ValueError as exc:
            raise ObjReadError(
                f"line {line_no}: bad face normal '{parts[2]}': {exc}"
            ) from exc

    return vi, ti, ni


# ---------------------------------------------------------------------------
# MTL parser
# ---------------------------------------------------------------------------

def _parse_mtl(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse a .mtl file and return a dict mapping material name → property dict.

    Property dict keys (all optional, present only when found):
        kd  — [r, g, b] diffuse colour (0-1 float)
        ka  — [r, g, b] ambient colour
        ks  — [r, g, b] specular colour
        ns  — float specular exponent
        d   — float dissolve (opacity)
        map_kd — str texture filename
        illum  — int illumination model
    """
    path = Path(path)
    materials: Dict[str, Any] = {}
    current: Optional[Dict[str, Any]] = None
    current_name: Optional[str] = None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ObjReadError(f"Cannot open MTL file '{path}': {exc}") from exc

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        keyword = parts[0].lower()
        rest = parts[1:]

        if keyword == "newmtl":
            if not rest:
                raise ObjReadError(f"MTL line {line_no}: 'newmtl' missing name")
            current_name = rest[0]
            current = {}
            materials[current_name] = current

        elif current is None:
            # Ignore property lines before first 'newmtl'
            continue

        elif keyword == "kd":
            current["kd"] = _parse_float_triple(rest, line_no, "Kd")
        elif keyword == "ka":
            current["ka"] = _parse_float_triple(rest, line_no, "Ka")
        elif keyword == "ks":
            current["ks"] = _parse_float_triple(rest, line_no, "Ks")
        elif keyword in ("ns", "ni"):
            if rest:
                try:
                    current[keyword] = float(rest[0])
                except ValueError:
                    pass
        elif keyword == "d":
            if rest:
                try:
                    current["d"] = float(rest[0])
                except ValueError:
                    pass
        elif keyword == "tr":
            if rest:
                try:
                    current["d"] = 1.0 - float(rest[0])  # Tr = 1 - d
                except ValueError:
                    pass
        elif keyword == "map_kd":
            if rest:
                current["map_kd"] = rest[0]
        elif keyword == "illum":
            if rest:
                try:
                    current["illum"] = int(rest[0])
                except ValueError:
                    pass

    return materials


# ---------------------------------------------------------------------------
# OBJ reader
# ---------------------------------------------------------------------------

def read_obj(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Read a Wavefront OBJ file and return a mesh dict.

    Parameters
    ----------
    path : str or Path
        Path to the ``.obj`` file.

    Returns
    -------
    dict with keys:
        verts       list[list[float]]   — [[x,y,z], ...]
        normals     list[list[float]]   — [[nx,ny,nz], ...] (may be empty)
        texcoords   list[list[float]]   — [[u,v], ...] (may be empty)
        faces       list[dict]          — see module docstring
        groups      list[str]           — ordered unique group names
        materials   dict[str, dict]     — material dicts loaded from .mtl
        mtllib      str | None          — raw mtllib filename

    Raises
    ------
    ObjReadError
        On any parse failure.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ObjReadError(f"Cannot open OBJ file '{path}': {exc}") from exc

    verts: List[List[float]] = []
    normals: List[List[float]] = []
    texcoords: List[List[float]] = []
    faces: List[Dict[str, Any]] = []
    groups_seen: List[str] = []
    groups_set: set = set()
    materials: Dict[str, Any] = {}
    mtllib: Optional[str] = None

    current_group: Optional[str] = None
    current_material: Optional[str] = None

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        # Handle line continuation (trailing backslash)
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        keyword = parts[0]
        rest = parts[1:]

        if keyword == "v":
            verts.append(_parse_vertex(rest, line_no))

        elif keyword == "vn":
            normals.append(_parse_float_triple(rest, line_no, "vn"))

        elif keyword == "vt":
            texcoords.append(_parse_texcoord(rest, line_no))

        elif keyword == "f":
            if len(rest) < 3:
                raise ObjReadError(
                    f"line {line_no}: 'f' requires at least 3 vertices, got {len(rest)}"
                )
            fv: List[int] = []
            ft: List[Optional[int]] = []
            fn: List[Optional[int]] = []
            for token in rest:
                vi, ti, ni = _parse_face_token(
                    token, len(verts), len(texcoords), len(normals), line_no
                )
                fv.append(vi)
                ft.append(ti)
                fn.append(ni)

            # Normalise: if all None, store None list
            has_t = any(x is not None for x in ft)
            has_n = any(x is not None for x in fn)
            faces.append({
                "verts": fv,
                "texcoords": ft if has_t else None,
                "normals": fn if has_n else None,
                "group": current_group,
                "material": current_material,
            })

        elif keyword == "g":
            # May be "g" (reset to default) or "g name [name ...]"
            if rest:
                # Use first name only (some exporters emit multiple)
                current_group = rest[0]
                if current_group not in groups_set:
                    groups_set.add(current_group)
                    groups_seen.append(current_group)
            else:
                current_group = None

        elif keyword == "usemtl":
            if not rest:
                raise ObjReadError(f"line {line_no}: 'usemtl' missing material name")
            current_material = rest[0]

        elif keyword == "mtllib":
            if not rest:
                raise ObjReadError(f"line {line_no}: 'mtllib' missing filename")
            mtllib = rest[0]
            # Try to load the MTL file from the same directory
            mtl_path = path.parent / mtllib
            if mtl_path.exists():
                try:
                    materials = _parse_mtl(mtl_path)
                except ObjReadError:
                    # Non-fatal: MTL missing or unreadable → empty materials
                    materials = {}
            # else: file not found → leave materials empty

        elif keyword in ("o", "s", "l", "p", "cstype", "deg", "bmat",
                         "step", "curv", "curv2", "surf", "parm", "trim",
                         "hole", "scrv", "sp", "end", "con", "mg", "bevel",
                         "c_interp", "d_interp", "lod", "maplib", "usemap",
                         "shadow_obj", "trace_obj", "ctech", "stech"):
            # Silently skip known but unhandled keywords
            pass

        # Unknown keywords are silently ignored

    return {
        "verts": verts,
        "normals": normals,
        "texcoords": texcoords,
        "faces": faces,
        "groups": groups_seen,
        "materials": materials,
        "mtllib": mtllib,
    }


# ---------------------------------------------------------------------------
# MTL writer
# ---------------------------------------------------------------------------

def _write_mtl(mtl_path: Path, materials: Dict[str, Any]) -> None:
    """
    Write a .mtl file from a materials dict.

    ``materials`` maps name → property dict.  Recognised property keys:
        kd / Kd   — [r, g, b] diffuse  (0-1 float)
        ka / Ka   — [r, g, b] ambient
        ks / Ks   — [r, g, b] specular
        ns / Ns   — float specular exponent
        d         — float dissolve
        map_kd    — str texture filename
        illum     — int illumination model
    """
    lines: List[str] = ["# MTL file written by kerf_cad_core.geom.io.obj (GK-80)", ""]

    for name, props in materials.items():
        lines.append(f"newmtl {name}")

        def _fmt3(key: str, mtl_key: str) -> None:
            val = props.get(key) or props.get(mtl_key)
            if val is not None:
                try:
                    r, g, b = float(val[0]), float(val[1]), float(val[2])
                    lines.append(f"{mtl_key} {r:.6f} {g:.6f} {b:.6f}")
                except (TypeError, IndexError, ValueError):
                    pass

        _fmt3("ka", "Ka")
        _fmt3("kd", "Kd")
        _fmt3("ks", "Ks")

        for src_key, mtl_key in [("ns", "Ns"), ("d", "d"), ("illum", "illum")]:
            val = props.get(src_key) or props.get(mtl_key)
            if val is not None:
                try:
                    if mtl_key == "illum":
                        lines.append(f"illum {int(val)}")
                    else:
                        lines.append(f"{mtl_key} {float(val):.6f}")
                except (TypeError, ValueError):
                    pass

        for src_key, mtl_key in [("map_kd", "map_Kd")]:
            val = props.get(src_key) or props.get(mtl_key)
            if val is not None:
                lines.append(f"map_Kd {val}")

        lines.append("")

    try:
        mtl_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise ObjWriteError(f"Cannot write MTL file '{mtl_path}': {exc}") from exc


# ---------------------------------------------------------------------------
# OBJ writer
# ---------------------------------------------------------------------------

def _extract_mesh(mesh_or_body: Any) -> Tuple[List[Any], List[Any]]:
    """
    Extract (verts, faces) from *mesh_or_body*.

    Accepts:
    - dict with "verts"/"vertices" and "faces"
    - object with .verts/.vertices and .faces attributes
    """
    if isinstance(mesh_or_body, dict):
        verts = mesh_or_body.get("verts") or mesh_or_body.get("vertices")
        faces = mesh_or_body.get("faces")
    else:
        verts = getattr(mesh_or_body, "verts", None) or getattr(mesh_or_body, "vertices", None)
        faces = getattr(mesh_or_body, "faces", None)

    if verts is None:
        raise ObjWriteError("mesh_or_body has no 'verts' or 'vertices'")
    if faces is None:
        raise ObjWriteError("mesh_or_body has no 'faces'")
    return list(verts), list(faces)


def write_obj(
    path: Union[str, Path],
    mesh_or_body: Any,
    *,
    groups: Optional[Dict[str, Sequence[int]]] = None,
    materials: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write a mesh (or body-like object) to a Wavefront OBJ file.

    Parameters
    ----------
    path : str or Path
        Output ``.obj`` path.  If *materials* is given a companion ``.mtl``
        file is written at the same location with the ``.obj`` replaced by
        ``.mtl``.
    mesh_or_body : dict or object
        Geometry source.  Must expose ``verts``/``vertices`` (list of
        [x,y,z]) and ``faces`` (list of [i,j,k,...] 0-based int lists
        OR list of face-dicts as produced by ``read_obj``).
    groups : dict[str, list[int]], optional
        Mapping of group name → list of 0-based face indices.  If provided
        ``g`` statements are emitted before the relevant faces.
    materials : dict[str, dict], optional
        Material property dicts (same schema as produced by ``read_obj``).
        A companion ``.mtl`` file is written and referenced via ``mtllib``.
        Face-level ``usemtl`` lines require the source ``faces`` to carry
        a ``"material"`` key (as produced by ``read_obj``).

    Raises
    ------
    ObjWriteError
        On any serialisation failure.
    """
    path = Path(path)
    try:
        raw_verts, raw_faces = _extract_mesh(mesh_or_body)
    except ObjWriteError:
        raise
    except Exception as exc:
        raise ObjWriteError(f"Cannot extract mesh: {exc}") from exc

    lines: List[str] = ["# OBJ file written by kerf_cad_core.geom.io.obj (GK-80)"]

    # --- mtllib reference ---
    mtl_filename: Optional[str] = None
    if materials:
        mtl_filename = path.stem + ".mtl"
        lines.append(f"mtllib {mtl_filename}")

    lines.append("")

    # --- vertices ---
    for v in raw_verts:
        try:
            x, y, z = float(v[0]), float(v[1]), float(v[2])
        except (TypeError, IndexError, ValueError) as exc:
            raise ObjWriteError(f"Invalid vertex {v!r}: {exc}") from exc
        lines.append(f"v {x:.10g} {y:.10g} {z:.10g}")

    lines.append("")

    # --- normals (from face dicts if present) ---
    # Collect all normals in insertion order
    normals_list: List[List[float]] = []
    normals_index: Dict[int, int] = {}  # face_idx → normal list start idx (unused currently)

    # Pre-scan for face-dict normals
    face_has_normals = False
    face_source_normals: Optional[List[List[float]]] = None
    if isinstance(mesh_or_body, dict):
        face_source_normals = mesh_or_body.get("normals")
    else:
        face_source_normals = getattr(mesh_or_body, "normals", None)

    if face_source_normals:
        face_has_normals = True
        for nrm in face_source_normals:
            lines.append(f"vn {float(nrm[0]):.10g} {float(nrm[1]):.10g} {float(nrm[2]):.10g}")
        lines.append("")

    # --- texcoords ---
    face_source_texcoords: Optional[List[List[float]]] = None
    if isinstance(mesh_or_body, dict):
        face_source_texcoords = mesh_or_body.get("texcoords")
    else:
        face_source_texcoords = getattr(mesh_or_body, "texcoords", None)

    if face_source_texcoords:
        for tc in face_source_texcoords:
            lines.append(f"vt {float(tc[0]):.10g} {float(tc[1]):.10g}")
        lines.append("")

    # --- Build group → face mapping ---
    # groups param maps name → [face_idx, ...]
    # We also honour face-level "group" keys
    face_group: List[Optional[str]] = [None] * len(raw_faces)
    face_material: List[Optional[str]] = [None] * len(raw_faces)

    for fi, face in enumerate(raw_faces):
        if isinstance(face, dict):
            face_group[fi] = face.get("group")
            face_material[fi] = face.get("material")

    if groups:
        for gname, fidxs in groups.items():
            for fi in fidxs:
                if 0 <= fi < len(raw_faces):
                    face_group[fi] = gname

    # --- Faces ---
    current_g: Optional[str] = "__UNSET__"
    current_mat: Optional[str] = "__UNSET__"

    for fi, face in enumerate(raw_faces):
        # Group change
        g = face_group[fi]
        if g != current_g:
            current_g = g
            lines.append(f"g {g}" if g else "g")

        # Material change
        if materials:
            mat = face_material[fi]
            if mat != current_mat:
                current_mat = mat
                if mat:
                    lines.append(f"usemtl {mat}")

        # Build face line
        if isinstance(face, dict):
            fv = face.get("verts", [])
            ft = face.get("texcoords")
            fn = face.get("normals")
        else:
            # Simple list of 0-based int indices
            try:
                fv = list(face)
            except TypeError:
                raise ObjWriteError(f"face {fi} is not iterable: {face!r}")
            ft = None
            fn = None

        tokens: List[str] = []
        for j, vi in enumerate(fv):
            # OBJ is 1-based
            v1 = vi + 1
            ti1 = (ft[j] + 1) if (ft and ft[j] is not None) else None
            ni1 = (fn[j] + 1) if (fn and fn[j] is not None) else None

            if ti1 is not None and ni1 is not None:
                tokens.append(f"{v1}/{ti1}/{ni1}")
            elif ti1 is not None:
                tokens.append(f"{v1}/{ti1}")
            elif ni1 is not None:
                tokens.append(f"{v1}//{ni1}")
            else:
                tokens.append(str(v1))

        if len(tokens) < 3:
            raise ObjWriteError(f"face {fi} has fewer than 3 vertices")
        lines.append("f " + " ".join(tokens))

    # Trailing newline
    lines.append("")

    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise ObjWriteError(f"Cannot write OBJ file '{path}': {exc}") from exc

    # --- Write companion MTL ---
    if materials and mtl_filename:
        mtl_path = path.parent / mtl_filename
        _write_mtl(mtl_path, materials)
