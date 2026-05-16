"""
parasolid_reader.py — Pure-Python X_T (Parasolid text-transmit) reader.

Parses Parasolid X_T ASCII files into a Kerf B-rep-like model:
  - Assembly / body tree
  - Topology graph: body → shell → face → loop → edge → vertex (+ fins)
  - Analytic surface geometry: plane, cylinder, cone, sphere, torus, b_surface
  - Analytic curve geometry:  line, circle, ellipse, b_curve
  - Names and user attributes (from ATTRIB_* records)

Downstream consumers (AFR, heal) receive a face/edge inventory via
``parse_xt``, which returns a plain dict and never raises.

X_T schema reference (abbreviated):
  Header block:  SCH_* key/value pairs, BEGN / END markers
  Data block:    numbered records, one per line (or continuation lines)
    record format:  <index> <TYPE> <field0> <field1> ...

Entity types handled:
  Topology:  body, shell, face, loop, edge, vertex, fin
  Geometry:  plane, cylinder, cone, sphere, torus, b_surface,
             line, circle, ellipse, b_curve
  Assembly:  assembly, instance, transform
  Names:     attrib_string, attrib_real, attrib_int, attrib_gen, name
  Unsupported types: warning logged, record skipped.

All public functions return dicts and never raise — errors surface as
{"ok": False, "reason": "..."}.

LLM tool ``import_xt`` is registered via @register mirroring the
kerf-imports pattern; gated on availability (always True for pure-Python).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import warnings
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FLOAT_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _tok(s: str) -> list[str]:
    """Tokenise a whitespace-separated record field string."""
    return s.split()


def _floats(tokens: list[str], start: int, count: int) -> list[float]:
    """Extract *count* floats from *tokens* starting at *start*."""
    out = []
    for i in range(count):
        try:
            out.append(float(tokens[start + i]))
        except (IndexError, ValueError):
            out.append(0.0)
    return out


def _ints(tokens: list[str], start: int, count: int) -> list[int]:
    """Extract *count* ints from *tokens* starting at *start*."""
    out = []
    for i in range(count):
        try:
            out.append(int(tokens[start + i]))
        except (IndexError, ValueError):
            out.append(0)
    return out


def _vec3(tokens: list[str], start: int) -> dict:
    x, y, z = _floats(tokens, start, 3)
    return {"x": x, "y": y, "z": z}


def _strip_string_field(s: str) -> str:
    """Remove surrounding quotes from an X_T string field if present."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# Header parser
# ---------------------------------------------------------------------------

def _parse_header(lines: list[str]) -> tuple[dict, int]:
    """
    Parse the X_T header block.

    The header begins at line 0 and ends at the first non-SCH/non-blank
    line that is not a recognised header keyword, OR when a numbered record
    line is encountered.

    Returns (header_dict, first_data_line_index).
    """
    header: dict[str, Any] = {}
    i = 0
    header_keys = {
        "SCH_PARASOLID_TRANSMIT", "SCH_FORMAT_TYPE", "SCH_FORMAT_OPTION",
        "SCH_SCHEMA_VERSION", "SCH_TRANSMIT_DATE", "SCH_TRANSMIT_TIME",
        "SCH_SENDER_VERSION", "SCH_SENDER_SYSTEM", "SCH_SENDER_USER",
        "SCH_RECEIVER_VERSION", "SCH_RECEIVER_SYSTEM", "SCH_END_OF_HEADER",
        "SCH_ATTRIBS", "SCH_UNITS",
        "BEGIN_OF_HEADER", "END_OF_HEADER",
        "BEGN", "END",
    }
    in_header = True
    while i < len(lines) and in_header:
        raw = lines[i].rstrip()
        stripped = raw.strip()

        # Blank lines are fine inside the header
        if not stripped:
            i += 1
            continue

        # A line starting with a digit is the beginning of the data section
        if stripped and stripped[0].isdigit():
            break

        # Key-value header line: KEY value  or  KEY (no value)
        parts = stripped.split(None, 1)
        key = parts[0].upper()

        if key in header_keys or key.startswith("SCH_"):
            value = parts[1].strip() if len(parts) > 1 else True
            # Some values are quoted
            if isinstance(value, str):
                value = _strip_string_field(value)
            header[key] = value
            i += 1
            # END_OF_HEADER / SCH_END_OF_HEADER marks the end
            if key in ("END_OF_HEADER", "SCH_END_OF_HEADER", "END"):
                i += 1
                break
        else:
            # Not a recognised header key — assume data section has started
            break

    return header, i


# ---------------------------------------------------------------------------
# Record tokeniser
# ---------------------------------------------------------------------------

def _collect_records(lines: list[str], start: int) -> list[tuple[int, str, list[str]]]:
    """
    Collect X_T data records from *lines* beginning at *start*.

    X_T records start with an integer index on the first token.
    Continuation lines (no leading integer) are appended to the previous
    record's token list.

    Returns list of (record_index, record_type, tokens)
    where tokens does NOT include index or type.
    """
    records: list[tuple[int, str, list[str]]] = []
    current_tokens: list[str] = []
    current_idx: int = -1
    current_type: str = ""

    for line in lines[start:]:
        stripped = line.rstrip()
        if not stripped:
            continue
        tokens = stripped.split()
        if not tokens:
            continue

        # New record: first token must be a non-negative integer
        try:
            idx = int(tokens[0])
            if idx >= 0 and len(tokens) >= 2:
                # Save previous record
                if current_type:
                    records.append((current_idx, current_type, current_tokens))
                current_idx = idx
                current_type = tokens[1].lower()
                current_tokens = tokens[2:]
                continue
        except ValueError:
            pass

        # Continuation line: append to current record
        if current_type:
            current_tokens.extend(tokens)

    # Last record
    if current_type:
        records.append((current_idx, current_type, current_tokens))

    return records


# ---------------------------------------------------------------------------
# Geometry parsers
# ---------------------------------------------------------------------------

def _parse_plane(idx: int, tokens: list[str]) -> dict:
    """plane: origin(3) normal(3) [ref_dir(3)]"""
    origin = _vec3(tokens, 0)
    normal = _vec3(tokens, 3)
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    r: dict = {"kind": "plane", "origin": origin, "normal": normal}
    if ref_dir:
        r["ref_dir"] = ref_dir
    return r


def _parse_cylinder(idx: int, tokens: list[str]) -> dict:
    """cylinder: origin(3) axis(3) ref_dir(3) radius"""
    origin = _vec3(tokens, 0)
    axis = _vec3(tokens, 3)
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    radius = float(tokens[9]) if len(tokens) > 9 else (float(tokens[6]) if len(tokens) > 6 else 0.0)
    # Some formats: origin(3) axis(3) radius
    if len(tokens) == 7:
        radius = float(tokens[6])
        ref_dir = None
    elif len(tokens) >= 10:
        radius = float(tokens[9])
    return {
        "kind": "cylinder",
        "origin": origin,
        "axis": axis,
        "ref_dir": ref_dir,
        "radius": radius,
    }


def _parse_cone(idx: int, tokens: list[str]) -> dict:
    """cone: origin(3) axis(3) ref_dir(3) half_angle radius"""
    origin = _vec3(tokens, 0)
    axis = _vec3(tokens, 3)
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    half_angle = float(tokens[9]) if len(tokens) > 9 else 0.0
    radius = float(tokens[10]) if len(tokens) > 10 else 0.0
    return {
        "kind": "cone",
        "origin": origin,
        "axis": axis,
        "ref_dir": ref_dir,
        "half_angle": half_angle,
        "radius": radius,
    }


def _parse_sphere(idx: int, tokens: list[str]) -> dict:
    """sphere: centre(3) [axis(3) [ref_dir(3)]] radius

    Compact form: centre(3) radius → 4 tokens
    With axis:    centre(3) axis(3) radius → 7 tokens
    Full form:    centre(3) axis(3) ref_dir(3) radius → 10 tokens
    """
    centre = _vec3(tokens, 0)
    n = len(tokens)
    if n <= 4:
        # compact: centre(3) radius
        radius = float(tokens[3]) if n == 4 else 0.0
        axis = None
    elif n <= 7:
        # centre(3) axis(3) radius
        axis = _vec3(tokens, 3)
        radius = float(tokens[6]) if n >= 7 else 0.0
    else:
        # full: centre(3) axis(3) ref_dir(3) radius
        axis = _vec3(tokens, 3)
        radius = float(tokens[9]) if n > 9 else 0.0
    return {
        "kind": "sphere",
        "centre": centre,
        "axis": axis,
        "radius": radius,
    }


def _parse_torus(idx: int, tokens: list[str]) -> dict:
    """torus: centre(3) axis(3) ref_dir(3) major_radius minor_radius"""
    centre = _vec3(tokens, 0)
    axis = _vec3(tokens, 3) if len(tokens) >= 6 else None
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    major_r = float(tokens[9]) if len(tokens) > 9 else 0.0
    minor_r = float(tokens[10]) if len(tokens) > 10 else 0.0
    return {
        "kind": "torus",
        "centre": centre,
        "axis": axis,
        "ref_dir": ref_dir,
        "major_radius": major_r,
        "minor_radius": minor_r,
    }


def _parse_b_surface(idx: int, tokens: list[str]) -> dict:
    """b_surface: degree_u degree_v n_u n_v [knots…] [poles…]"""
    deg_u = int(tokens[0]) if tokens else 0
    deg_v = int(tokens[1]) if len(tokens) > 1 else 0
    n_u = int(tokens[2]) if len(tokens) > 2 else 0
    n_v = int(tokens[3]) if len(tokens) > 3 else 0
    return {
        "kind": "b_surface",
        "degree_u": deg_u,
        "degree_v": deg_v,
        "n_u": n_u,
        "n_v": n_v,
        "token_count": len(tokens),
    }


def _parse_line(idx: int, tokens: list[str]) -> dict:
    """line: origin(3) direction(3)"""
    origin = _vec3(tokens, 0)
    direction = _vec3(tokens, 3) if len(tokens) >= 6 else {"x": 1.0, "y": 0.0, "z": 0.0}
    return {"kind": "line", "origin": origin, "direction": direction}


def _parse_circle(idx: int, tokens: list[str]) -> dict:
    """circle: centre(3) axis(3) ref_dir(3) radius"""
    centre = _vec3(tokens, 0)
    axis = _vec3(tokens, 3) if len(tokens) >= 6 else None
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    radius = float(tokens[9]) if len(tokens) > 9 else 0.0
    if len(tokens) == 4:
        radius = float(tokens[3])
    return {"kind": "circle", "centre": centre, "axis": axis, "ref_dir": ref_dir, "radius": radius}


def _parse_ellipse(idx: int, tokens: list[str]) -> dict:
    """ellipse: centre(3) axis(3) ref_dir(3) major_radius minor_radius"""
    centre = _vec3(tokens, 0)
    axis = _vec3(tokens, 3) if len(tokens) >= 6 else None
    ref_dir = _vec3(tokens, 6) if len(tokens) >= 9 else None
    major_r = float(tokens[9]) if len(tokens) > 9 else 0.0
    minor_r = float(tokens[10]) if len(tokens) > 10 else 0.0
    return {
        "kind": "ellipse",
        "centre": centre,
        "axis": axis,
        "ref_dir": ref_dir,
        "major_radius": major_r,
        "minor_radius": minor_r,
    }


def _parse_b_curve(idx: int, tokens: list[str]) -> dict:
    """b_curve: degree n_poles [knots…] [poles…]"""
    degree = int(tokens[0]) if tokens else 0
    n_poles = int(tokens[1]) if len(tokens) > 1 else 0
    return {
        "kind": "b_curve",
        "degree": degree,
        "n_poles": n_poles,
        "token_count": len(tokens),
    }


_GEOM_PARSERS = {
    "plane": _parse_plane,
    "cylinder": _parse_cylinder,
    "cone": _parse_cone,
    "sphere": _parse_sphere,
    "torus": _parse_torus,
    "b_surface": _parse_b_surface,
    "b-surface": _parse_b_surface,
    "bsurf": _parse_b_surface,
    "line": _parse_line,
    "circle": _parse_circle,
    "ellipse": _parse_ellipse,
    "b_curve": _parse_b_curve,
    "b-curve": _parse_b_curve,
    "bcurve": _parse_b_curve,
}


# ---------------------------------------------------------------------------
# Topology parsers
# ---------------------------------------------------------------------------

def _ref(tokens: list[str], pos: int) -> Optional[int]:
    """Read an entity reference (integer index) at *pos*."""
    try:
        v = int(tokens[pos])
        return v if v > 0 else None
    except (IndexError, ValueError):
        return None


def _parse_body(idx: int, tokens: list[str]) -> dict:
    """body: ref_shell ref_next_body [name_ref]"""
    shell_ref = _ref(tokens, 0)
    return {"kind": "body", "shell_ref": shell_ref, "face_refs": [], "edge_refs": [], "vertex_refs": []}


def _parse_shell(idx: int, tokens: list[str]) -> dict:
    """shell: ref_face ref_next_shell [body_ref]"""
    face_ref = _ref(tokens, 0)
    return {"kind": "shell", "face_ref": face_ref}


def _parse_face(idx: int, tokens: list[str]) -> dict:
    """face: ref_loop ref_next_face ref_surf sense [name_ref]"""
    loop_ref = _ref(tokens, 0)
    next_face = _ref(tokens, 1)
    surf_ref = _ref(tokens, 2)
    # sense: 0=forward, 1=reversed
    sense_tok = tokens[3] if len(tokens) > 3 else "0"
    try:
        sense = int(sense_tok)
    except ValueError:
        sense = 0
    return {
        "kind": "face",
        "loop_ref": loop_ref,
        "next_face": next_face,
        "surf_ref": surf_ref,
        "sense": sense,
    }


def _parse_loop(idx: int, tokens: list[str]) -> dict:
    """loop: ref_fin ref_next_loop ref_face"""
    fin_ref = _ref(tokens, 0)
    next_loop = _ref(tokens, 1)
    face_ref = _ref(tokens, 2)
    return {"kind": "loop", "fin_ref": fin_ref, "next_loop": next_loop, "face_ref": face_ref}


def _parse_edge(idx: int, tokens: list[str]) -> dict:
    """edge: ref_start_vertex ref_end_vertex ref_curve [sense]"""
    v_start = _ref(tokens, 0)
    v_end = _ref(tokens, 1)
    curve_ref = _ref(tokens, 2)
    return {
        "kind": "edge",
        "v_start": v_start,
        "v_end": v_end,
        "curve_ref": curve_ref,
    }


def _parse_vertex(idx: int, tokens: list[str]) -> dict:
    """vertex: ref_point [edge_ref]"""
    point_ref = _ref(tokens, 0)
    return {"kind": "vertex", "point_ref": point_ref}


def _parse_fin(idx: int, tokens: list[str]) -> dict:
    """fin: ref_edge ref_next_fin ref_loop sense"""
    edge_ref = _ref(tokens, 0)
    next_fin = _ref(tokens, 1)
    loop_ref = _ref(tokens, 2)
    sense_tok = tokens[3] if len(tokens) > 3 else "0"
    try:
        sense = int(sense_tok)
    except ValueError:
        sense = 0
    return {
        "kind": "fin",
        "edge_ref": edge_ref,
        "next_fin": next_fin,
        "loop_ref": loop_ref,
        "sense": sense,
    }


def _parse_point(idx: int, tokens: list[str]) -> dict:
    """point: x y z"""
    x, y, z = _floats(tokens, 0, 3)
    return {"kind": "point", "x": x, "y": y, "z": z}


def _parse_transform(idx: int, tokens: list[str]) -> dict:
    """transform: matrix3x3(9) translation(3) [scale]"""
    matrix = _floats(tokens, 0, 9)
    translation = _floats(tokens, 9, 3)
    scale = float(tokens[12]) if len(tokens) > 12 else 1.0
    return {"kind": "transform", "matrix": matrix, "translation": translation, "scale": scale}


def _parse_instance(idx: int, tokens: list[str]) -> dict:
    """instance: ref_body ref_transform [ref_next_instance]"""
    body_ref = _ref(tokens, 0)
    transform_ref = _ref(tokens, 1)
    return {"kind": "instance", "body_ref": body_ref, "transform_ref": transform_ref}


def _parse_assembly(idx: int, tokens: list[str]) -> dict:
    """assembly: ref_first_instance [name_ref]"""
    instance_ref = _ref(tokens, 0)
    return {"kind": "assembly", "instance_ref": instance_ref}


def _parse_name(idx: int, tokens: list[str]) -> dict:
    """name: 'string_value' ref_next_name"""
    value = _strip_string_field(tokens[0]) if tokens else ""
    next_name = _ref(tokens, 1) if len(tokens) > 1 else None
    return {"kind": "name", "value": value, "next_name": next_name}


def _parse_attrib_string(idx: int, tokens: list[str]) -> dict:
    """attrib_string: key value [ref_next]"""
    key = _strip_string_field(tokens[0]) if tokens else ""
    value = _strip_string_field(tokens[1]) if len(tokens) > 1 else ""
    return {"kind": "attrib_string", "key": key, "value": value}


def _parse_attrib_real(idx: int, tokens: list[str]) -> dict:
    """attrib_real: key value [ref_next]"""
    key = _strip_string_field(tokens[0]) if tokens else ""
    try:
        value = float(tokens[1]) if len(tokens) > 1 else 0.0
    except ValueError:
        value = 0.0
    return {"kind": "attrib_real", "key": key, "value": value}


def _parse_attrib_int(idx: int, tokens: list[str]) -> dict:
    """attrib_int: key value [ref_next]"""
    key = _strip_string_field(tokens[0]) if tokens else ""
    try:
        value = int(tokens[1]) if len(tokens) > 1 else 0
    except ValueError:
        value = 0
    return {"kind": "attrib_int", "key": key, "value": value}


def _parse_attrib_gen(idx: int, tokens: list[str]) -> dict:
    """attrib_gen: generic catch-all"""
    return {"kind": "attrib_gen", "tokens": tokens[:8]}


_TOPO_PARSERS: dict[str, Any] = {
    "body": _parse_body,
    "shell": _parse_shell,
    "face": _parse_face,
    "loop": _parse_loop,
    "edge": _parse_edge,
    "vertex": _parse_vertex,
    "fin": _parse_fin,
    "point": _parse_point,
    "transform": _parse_transform,
    "instance": _parse_instance,
    "assembly": _parse_assembly,
    "name": _parse_name,
    "attrib_string": _parse_attrib_string,
    "attrib_real": _parse_attrib_real,
    "attrib_int": _parse_attrib_int,
    "attrib_gen": _parse_attrib_gen,
}


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------

def _build_model(
    header: dict,
    records: list[tuple[int, str, list[str]]],
) -> dict:
    """
    Build the Kerf B-rep model dict from parsed records.

    Returns:
    {
      "header": {...},
      "entities": {idx: {...}},   # raw entity map
      "bodies": [idx, ...],
      "faces":  [idx, ...],
      "edges":  [idx, ...],
      "vertices": [idx, ...],
      "shells": [idx, ...],
      "loops":  [idx, ...],
      "fins":   [idx, ...],
      "geometry": {idx: {...}},   # surface / curve records
      "attributes": [{key, value, entity_ref}, ...],
      "names": {idx: str},
      "instances": [idx, ...],
      "assemblies": [idx, ...],
      "skipped_types": [str, ...],
      "warnings": [str, ...],
    }
    """
    entities: dict[int, dict] = {}
    geometry: dict[int, dict] = {}
    warnings_out: list[str] = []
    skipped_types: set[str] = set()

    for idx, rtype, tokens in records:
        if rtype in _TOPO_PARSERS:
            rec = _TOPO_PARSERS[rtype](idx, tokens)
            rec["_idx"] = idx
            entities[idx] = rec
        elif rtype in _GEOM_PARSERS:
            geom = _GEOM_PARSERS[rtype](idx, tokens)
            geom["_idx"] = idx
            geometry[idx] = geom
            entities[idx] = geom
        else:
            if rtype not in skipped_types:
                msg = f"parasolid_reader: unsupported record type '{rtype}' (index {idx}) — skipped"
                warnings.warn(msg)
                logger.warning(msg)
                skipped_types.add(rtype)

    # Classify by kind
    bodies = [idx for idx, e in entities.items() if e.get("kind") == "body"]
    shells = [idx for idx, e in entities.items() if e.get("kind") == "shell"]
    faces = [idx for idx, e in entities.items() if e.get("kind") == "face"]
    loops = [idx for idx, e in entities.items() if e.get("kind") == "loop"]
    edges = [idx for idx, e in entities.items() if e.get("kind") == "edge"]
    vertices = [idx for idx, e in entities.items() if e.get("kind") == "vertex"]
    fins = [idx for idx, e in entities.items() if e.get("kind") == "fin"]
    instances = [idx for idx, e in entities.items() if e.get("kind") == "instance"]
    assemblies = [idx for idx, e in entities.items() if e.get("kind") == "assembly"]

    # Names
    names: dict[int, str] = {}
    for idx, e in entities.items():
        if e.get("kind") == "name":
            names[idx] = e.get("value", "")

    # Attributes
    attrib_kinds = {"attrib_string", "attrib_real", "attrib_int", "attrib_gen"}
    attributes: list[dict] = []
    for idx, e in entities.items():
        if e.get("kind") in attrib_kinds:
            attributes.append({"entity_ref": idx, "key": e.get("key", ""), "value": e.get("value")})

    return {
        "header": header,
        "entities": entities,
        "bodies": bodies,
        "shells": shells,
        "faces": faces,
        "loops": loops,
        "edges": edges,
        "vertices": vertices,
        "fins": fins,
        "geometry": geometry,
        "attributes": attributes,
        "names": names,
        "instances": instances,
        "assemblies": assemblies,
        "skipped_types": sorted(skipped_types),
        "warnings": warnings_out,
    }


# ---------------------------------------------------------------------------
# Adjacency helpers
# ---------------------------------------------------------------------------

def _face_edges(model: dict, face_idx: int) -> list[int]:
    """Return list of edge indices reachable from *face_idx* via loops+fins."""
    entities = model["entities"]
    face = entities.get(face_idx, {})
    edge_idxs: list[int] = []
    visited_loops: set[int] = set()

    loop_ref = face.get("loop_ref")
    while loop_ref and loop_ref not in visited_loops:
        visited_loops.add(loop_ref)
        loop = entities.get(loop_ref, {})
        if not loop:
            break

        fin_ref = loop.get("fin_ref")
        visited_fins: set[int] = set()
        while fin_ref and fin_ref not in visited_fins:
            visited_fins.add(fin_ref)
            fin = entities.get(fin_ref, {})
            if not fin:
                break
            er = fin.get("edge_ref")
            if er and er not in edge_idxs:
                edge_idxs.append(er)
            fin_ref = fin.get("next_fin")

        loop_ref = loop.get("next_loop")

    return edge_idxs


def _body_faces(model: dict, body_idx: int) -> list[int]:
    """Walk shell → face linked-list for *body_idx*, returning face indices."""
    entities = model["entities"]
    body = entities.get(body_idx, {})
    face_idxs: list[int] = []
    visited_shells: set[int] = set()

    shell_ref = body.get("shell_ref")
    while shell_ref and shell_ref not in visited_shells:
        visited_shells.add(shell_ref)
        shell = entities.get(shell_ref, {})
        if not shell:
            break

        face_ref = shell.get("face_ref")
        visited_faces: set[int] = set()
        while face_ref and face_ref not in visited_faces:
            visited_faces.add(face_ref)
            face = entities.get(face_ref, {})
            if not face:
                break
            face_idxs.append(face_ref)
            face_ref = face.get("next_face")

        # Move to next shell if exists — shells don't have a linked list in
        # the simple case, break after first shell
        break

    return face_idxs


def _edge_vertices(model: dict, edge_idx: int) -> list[int]:
    """Return [v_start, v_end] for *edge_idx* (omit None refs)."""
    edge = model["entities"].get(edge_idx, {})
    out = []
    for k in ("v_start", "v_end"):
        v = edge.get(k)
        if v is not None:
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Inventory builder (for AFR / heal consumers)
# ---------------------------------------------------------------------------

def _build_inventory(model: dict) -> dict:
    """
    Build a flat face/edge/vertex inventory suitable for AFR and heal modules.

    Returns:
    {
      "face_count": int,
      "edge_count": int,
      "vertex_count": int,
      "faces": [
        {
          "idx": int,
          "surf_ref": int | None,
          "surf_kind": str | None,
          "surf_params": dict | None,
          "loop_count": int,
          "edge_count": int,
        }, ...
      ],
      "edges": [
        {
          "idx": int,
          "v_start": int | None,
          "v_end": int | None,
          "curve_ref": int | None,
          "curve_kind": str | None,
        }, ...
      ],
      "vertices": [
        {
          "idx": int,
          "point_ref": int | None,
          "x": float | None,
          "y": float | None,
          "z": float | None,
        }, ...
      ],
    }
    """
    entities = model["entities"]
    geometry = model["geometry"]

    face_inventory = []
    for fidx in model["faces"]:
        face = entities.get(fidx, {})
        surf_ref = face.get("surf_ref")
        surf = geometry.get(surf_ref) if surf_ref else None
        edges = _face_edges(model, fidx)

        # Count loops
        loop_count = 0
        loop_ref = face.get("loop_ref")
        visited_loops: set = set()
        while loop_ref and loop_ref not in visited_loops:
            visited_loops.add(loop_ref)
            loop_count += 1
            lp = entities.get(loop_ref, {})
            loop_ref = lp.get("next_loop")

        face_inventory.append({
            "idx": fidx,
            "surf_ref": surf_ref,
            "surf_kind": surf.get("kind") if surf else None,
            "surf_params": {k: v for k, v in surf.items() if k not in ("kind", "_idx")} if surf else None,
            "loop_count": loop_count,
            "edge_count": len(edges),
        })

    edge_inventory = []
    for eidx in model["edges"]:
        edge = entities.get(eidx, {})
        curve_ref = edge.get("curve_ref")
        curve = geometry.get(curve_ref) if curve_ref else None
        edge_inventory.append({
            "idx": eidx,
            "v_start": edge.get("v_start"),
            "v_end": edge.get("v_end"),
            "curve_ref": curve_ref,
            "curve_kind": curve.get("kind") if curve else None,
        })

    vertex_inventory = []
    for vidx in model["vertices"]:
        vert = entities.get(vidx, {})
        pt_ref = vert.get("point_ref")
        pt = entities.get(pt_ref) if pt_ref else None
        vertex_inventory.append({
            "idx": vidx,
            "point_ref": pt_ref,
            "x": pt.get("x") if pt else None,
            "y": pt.get("y") if pt else None,
            "z": pt.get("z") if pt else None,
        })

    return {
        "face_count": len(face_inventory),
        "edge_count": len(edge_inventory),
        "vertex_count": len(vertex_inventory),
        "faces": face_inventory,
        "edges": edge_inventory,
        "vertices": vertex_inventory,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_xt(text: str) -> dict:
    """
    Parse an X_T ASCII Parasolid file from *text*.

    Returns a dict with keys:
      ok              bool — False on fatal parse error
      reason          str  — present when ok=False
      header          dict — parsed header key/values
      body_count      int
      face_count      int
      edge_count      int
      vertex_count    int
      bodies          list[int]
      inventory       dict — flat face/edge/vertex inventory
      skipped_types   list[str]
      warnings        list[str]
      _model          dict — full internal model (for advanced consumers)

    Never raises.
    """
    try:
        if not isinstance(text, str):
            return {"ok": False, "reason": "input must be a string"}
        if not text.strip():
            return {"ok": False, "reason": "empty input"}

        lines = text.splitlines()
        header, data_start = _parse_header(lines)
        records = _collect_records(lines, data_start)
        model = _build_model(header, records)
        inventory = _build_inventory(model)

        return {
            "ok": True,
            "header": header,
            "body_count": len(model["bodies"]),
            "face_count": len(model["faces"]),
            "edge_count": len(model["edges"]),
            "vertex_count": len(model["vertices"]),
            "bodies": model["bodies"],
            "inventory": inventory,
            "skipped_types": model["skipped_types"],
            "warnings": model["warnings"],
            "_model": model,
        }
    except Exception as exc:
        logger.exception("parasolid_reader: parse_xt failed")
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx

    import_xt_spec = ToolSpec(
        name="import_xt",
        description=(
            "Parse a Parasolid X_T (text-transmit) ASCII file stored as a "
            "text/plain file in the project. Returns the assembly/body tree, "
            "topology counts (faces/edges/vertices), analytic surface and curve "
            "parameters, and a flat inventory ready for AFR/heal consumption. "
            "Unsupported record types are skipped with warnings."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "UUID of the X_T file stored as kind=step or text.",
                },
            },
            "required": ["file_id"],
        },
    )

    @register(import_xt_spec, write=False)
    async def run_import_xt(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        raw = a.get("file_id", "").strip()
        if not raw:
            return err_payload("file_id is required", "BAD_ARGS")
        try:
            fid = uuid.UUID(raw)
        except Exception:
            return err_payload("file_id must be a valid UUID", "BAD_ARGS")

        row = ctx.pool.fetchone(
            "select content from files where id = $1 and project_id = $2 and deleted_at is null",
            fid, ctx.project_id,
        )
        if not row:
            return err_payload("file not found", "NOT_FOUND")

        content = row[0] if isinstance(row, (list, tuple)) else row
        if not isinstance(content, str):
            try:
                content = content.decode("utf-8", errors="replace")
            except Exception:
                content = str(content)

        result = parse_xt(content)
        if not result.get("ok"):
            return err_payload(result.get("reason", "parse failed"), "PARSE_ERROR")

        # Strip internal model from LLM response (too large)
        result.pop("_model", None)
        return ok_payload(result)

    _LLM_TOOL_REGISTERED = True

except ImportError:
    _LLM_TOOL_REGISTERED = False
