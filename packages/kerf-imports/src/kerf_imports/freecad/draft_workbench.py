"""
draft_workbench.py — Tier 3: FreeCAD Draft Workbench objects → Kerf sketch/feature.

Translates:
  - ``Draft::Wire``      → Kerf ``.sketch`` (polyline entities)
  - ``Draft::Rectangle`` → Kerf ``.sketch`` (4-line rectangle)
  - ``Draft::Circle``    → Kerf ``.sketch`` (circle entity)
  - ``Draft::Array``     → Kerf ``.feature`` node with ``op="draft_array"``
  - ``Draft::Clone``     → Kerf ``.feature`` node with ``op="draft_clone"``
  - ``Draft::Polygon``   → Kerf ``.sketch`` (polygon approximated as lines)
  - ``Draft::Ellipse``   → Kerf ``.sketch`` (ellipse, construction-only with warning)
  - ``Draft::BSpline``   → Kerf ``.sketch`` (B-spline, construction-only with warning)

Unsupported Draft types: warn-and-skip (never raise).

Usage::

    from kerf_imports.freecad.draft_workbench import (
        translate_draft_object,
        is_draft_sketch_type,
        is_draft_feature_type,
    )

    result = translate_draft_object(obj)
    # result["kind"]     — "sketch" | "feature" | "skipped"
    # result["payload"]  — .sketch or .feature payload dict (for kind != "skipped")
    # result["warnings"] — list of warning strings
"""
from __future__ import annotations

import logging
import math
from typing import Any

from .types import FCStdObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type classification
# ---------------------------------------------------------------------------

# Draft types that map to .sketch files
_DRAFT_SKETCH_TYPES: frozenset[str] = frozenset({
    "Draft::Wire",
    "Draft::Rectangle",
    "Draft::Circle",
    "Draft::Polygon",
    "Draft::Ellipse",
    "Draft::BSpline",
    "Draft::BezCurve",
})

# Draft types that map to .feature nodes
_DRAFT_FEATURE_TYPES: frozenset[str] = frozenset({
    "Draft::Array",
    "Draft::Clone",
    "Draft::PathArray",
    "Draft::PathTwistedArray",
    "Draft::Mirror",
})

ALL_DRAFT_TYPES: frozenset[str] = _DRAFT_SKETCH_TYPES | _DRAFT_FEATURE_TYPES


def is_draft_sketch_type(type_str: str) -> bool:
    """Return True if *type_str* is a Draft type that maps to a .sketch file."""
    return type_str in _DRAFT_SKETCH_TYPES


def is_draft_feature_type(type_str: str) -> bool:
    """Return True if *type_str* is a Draft type that maps to a .feature node."""
    return type_str in _DRAFT_FEATURE_TYPES


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def translate_draft_object(obj: FCStdObject) -> dict[str, Any]:
    """
    Translate one Draft Workbench object to a Kerf payload.

    Parameters
    ----------
    obj :
        A parsed :class:`~kerf_imports.freecad.types.FCStdObject` whose
        ``type`` starts with ``"Draft::"``.

    Returns
    -------
    dict with keys:
        ``kind``     — ``"sketch"`` | ``"feature"`` | ``"skipped"``
        ``payload``  — sketch or feature payload dict (absent when kind=="skipped")
        ``name``     — suggested file name (e.g. ``"MyWire.sketch"``)
        ``warnings`` — list of warning strings
    """
    warnings: list[str] = []

    if obj.type in _DRAFT_SKETCH_TYPES:
        try:
            payload = _to_sketch(obj, warnings)
        except Exception as exc:
            logger.warning(
                "Draft sketch '%s' (%s): translation error — %s",
                obj.name, obj.type, exc,
            )
            warnings.append(
                f"Draft object '{obj.name}' ({obj.type}): translation failed — {exc}"
            )
            return {"kind": "skipped", "warnings": warnings}

        label = obj.label or obj.name
        return {
            "kind": "sketch",
            "name": f"{label}.sketch",
            "freecad_name": obj.name,
            "payload": payload,
            "warnings": warnings,
        }

    if obj.type in _DRAFT_FEATURE_TYPES:
        try:
            payload = _to_feature(obj, warnings)
        except Exception as exc:
            logger.warning(
                "Draft feature '%s' (%s): translation error — %s",
                obj.name, obj.type, exc,
            )
            warnings.append(
                f"Draft object '{obj.name}' ({obj.type}): translation failed — {exc}"
            )
            return {"kind": "skipped", "warnings": warnings}

        label = obj.label or obj.name
        return {
            "kind": "feature",
            "name": f"{label}.feature",
            "freecad_name": obj.name,
            "payload": payload,
            "warnings": warnings,
        }

    # Unknown Draft type — warn and skip
    warnings.append(
        f"Draft object '{obj.name}' ({obj.type}): unsupported type — skipped."
    )
    return {"kind": "skipped", "warnings": warnings}


# ---------------------------------------------------------------------------
# Sketch translators
# ---------------------------------------------------------------------------

def _to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """Dispatch to the appropriate sketch translator for the Draft type."""
    if obj.type == "Draft::Wire":
        return _wire_to_sketch(obj, warnings)
    if obj.type == "Draft::Rectangle":
        return _rectangle_to_sketch(obj, warnings)
    if obj.type == "Draft::Circle":
        return _circle_to_sketch(obj, warnings)
    if obj.type == "Draft::Polygon":
        return _polygon_to_sketch(obj, warnings)
    if obj.type in ("Draft::Ellipse",):
        return _ellipse_to_sketch(obj, warnings)
    if obj.type in ("Draft::BSpline", "Draft::BezCurve"):
        return _bspline_to_sketch(obj, warnings)

    warnings.append(
        f"Draft sketch '{obj.name}' ({obj.type}): no dedicated translator — "
        "emitting empty sketch."
    )
    return _empty_sketch(obj)


def _wire_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::Wire → list of line segments.

    FreeCAD stores the wire's vertices in a ``Points`` VectorList property.
    A closed wire has ``Closed = True``.
    """
    points = obj.properties.get("Points") or []
    # Points may be a list of dicts {"x":..., "y":..., "z":...} or similar
    pts = [_vec3(p) for p in points if _is_vector(p)]

    closed = bool(obj.properties.get("Closed"))
    make_face = bool(obj.properties.get("MakeFace"))

    entities: list[dict[str, Any]] = []
    if len(pts) >= 2:
        seg_pts = list(pts)
        if closed and seg_pts[0] != seg_pts[-1]:
            seg_pts.append(seg_pts[0])  # close the loop
        for i in range(len(seg_pts) - 1):
            entities.append({
                "id": f"g{i}",
                "type": "line",
                "start": _vec2d(seg_pts[i]),
                "end": _vec2d(seg_pts[i + 1]),
            })
    else:
        warnings.append(
            f"Draft::Wire '{obj.name}': fewer than 2 points — no segments emitted."
        )

    return _build_sketch_payload(obj, entities, [], warnings)


def _rectangle_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::Rectangle → 4 line segments (axis-aligned bounding box).

    FreeCAD properties: ``Length`` (X), ``Height`` (Y), ``Placement``.
    The rectangle is placed at the Placement origin.
    """
    length = _get_scalar(obj.properties, "Length") or 0.0
    height = _get_scalar(obj.properties, "Height") or 0.0

    # Placement gives us the origin + rotation, but for sketch import we
    # flatten to XY at origin (placement → sketch plane is resolved at T4+).
    # Emit a simple axis-aligned rectangle at origin.
    x0, y0 = 0.0, 0.0
    x1, y1 = length, height

    entities: list[dict[str, Any]] = [
        {"id": "g0", "type": "line", "start": {"x": x0, "y": y0}, "end": {"x": x1, "y": y0}},
        {"id": "g1", "type": "line", "start": {"x": x1, "y": y0}, "end": {"x": x1, "y": y1}},
        {"id": "g2", "type": "line", "start": {"x": x1, "y": y1}, "end": {"x": x0, "y": y1}},
        {"id": "g3", "type": "line", "start": {"x": x0, "y": y1}, "end": {"x": x0, "y": y0}},
    ]
    return _build_sketch_payload(obj, entities, [], warnings)


def _circle_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::Circle → circle or arc entity.

    Properties: ``Radius``, ``FirstAngle``, ``LastAngle`` (arc if they differ),
    ``Placement`` (center).
    """
    radius = _get_scalar(obj.properties, "Radius") or 0.0
    first_angle = _get_scalar(obj.properties, "FirstAngle")
    last_angle = _get_scalar(obj.properties, "LastAngle")

    is_arc = (
        first_angle is not None
        and last_angle is not None
        and abs(first_angle - last_angle) > 1e-6
        and not (abs(first_angle) < 1e-6 and abs(last_angle) >= 359.9)
    )

    if is_arc:
        entity: dict[str, Any] = {
            "id": "g0",
            "type": "arc",
            "center": {"x": 0.0, "y": 0.0},  # placement resolves at T4+
            "radius": radius,
            "start_angle": float(first_angle or 0.0),  # degrees (FreeCAD stores as degrees)
            "end_angle": float(last_angle or 0.0),
        }
    else:
        entity = {
            "id": "g0",
            "type": "circle",
            "center": {"x": 0.0, "y": 0.0},
            "radius": radius,
        }

    return _build_sketch_payload(obj, [entity], [], warnings)


def _polygon_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::Polygon → N-sided polygon approximated as N line segments.

    Properties: ``FacesNumber`` (vertex count), ``Radius`` (circumscribed),
    ``DrawMode`` ("inscribed"/"circumscribed").
    """
    n_sides = int(obj.properties.get("FacesNumber") or 6)
    radius = _get_scalar(obj.properties, "Radius") or 1.0
    draw_mode = (obj.properties.get("DrawMode") or "inscribed").lower()

    # For circumscribed mode: the radius is the inradius; compute circumradius.
    r = radius
    if "circum" in draw_mode and n_sides > 0:
        r = radius / math.cos(math.pi / n_sides)

    entities: list[dict[str, Any]] = []
    pts = []
    for i in range(n_sides):
        angle = 2 * math.pi * i / n_sides
        pts.append({"x": r * math.cos(angle), "y": r * math.sin(angle)})

    for i in range(n_sides):
        nxt = (i + 1) % n_sides
        entities.append({
            "id": f"g{i}",
            "type": "line",
            "start": pts[i],
            "end": pts[nxt],
        })

    warnings.append(
        f"Draft::Polygon '{obj.name}': {n_sides}-sided polygon imported as "
        f"{n_sides} line segments — regular-polygon constraints not preserved."
    )
    return _build_sketch_payload(obj, entities, [], warnings)


def _ellipse_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::Ellipse → construction ellipse entity (Kerf v1 does not natively
    parametrise ellipses; emitted as construction-only with a warning).
    """
    minor = _get_scalar(obj.properties, "MinorRadius") or 0.0
    major = _get_scalar(obj.properties, "MajorRadius") or 0.0

    entity: dict[str, Any] = {
        "id": "g0",
        "type": "ellipse",
        "construction": True,
        "center": {"x": 0.0, "y": 0.0},
        "minor_radius": minor,
        "major_radius": major,
    }

    warnings.append(
        f"Draft::Ellipse '{obj.name}': ellipses are imported as "
        "construction-only in Kerf v1."
    )
    return _build_sketch_payload(obj, [entity], [], warnings)


def _bspline_to_sketch(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """
    Draft::BSpline / BezCurve → construction B-spline entity.
    """
    points = obj.properties.get("Points") or []
    pts = [_vec2d(_vec3(p)) for p in points if _is_vector(p)]

    entity: dict[str, Any] = {
        "id": "g0",
        "type": "bspline",
        "construction": True,
        "control_points": pts,
    }

    warnings.append(
        f"{obj.type} '{obj.name}': B-spline/Bezier curves are imported as "
        "construction-only in Kerf v1."
    )
    return _build_sketch_payload(obj, [entity], [], warnings)


def _empty_sketch(obj: FCStdObject) -> dict[str, Any]:
    return _build_sketch_payload(obj, [], [], [])


def _build_sketch_payload(
    obj: FCStdObject,
    entities: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    """Build a standard Kerf .sketch payload dict."""
    plane: dict[str, Any] = {"type": "world_xy"}

    placement = obj.properties.get("Placement")
    if placement and isinstance(placement, dict):
        plane["freecad_placement"] = placement

    return {
        "entities": entities,
        "constraints": constraints,
        "plane": plane,
        "warnings": list(warnings),
        "freecad_ref": {
            "type": obj.type,
            "name": obj.name,
            "label": obj.label,
        },
    }


# ---------------------------------------------------------------------------
# Feature translators
# ---------------------------------------------------------------------------

def _to_feature(obj: FCStdObject, warnings: list[str]) -> dict[str, Any]:
    """Translate a Draft feature type to a Kerf .feature node payload."""
    if obj.type in ("Draft::Array", "Draft::PathArray", "Draft::PathTwistedArray"):
        node = _array_to_feature_node(obj, warnings)
    elif obj.type == "Draft::Clone":
        node = _clone_to_feature_node(obj, warnings)
    elif obj.type == "Draft::Mirror":
        node = _mirror_to_feature_node(obj, warnings)
    else:
        warnings.append(
            f"Draft feature '{obj.name}' ({obj.type}): no dedicated translator — "
            "emitting generic draft_feature node."
        )
        node = {
            "kind": "draft_feature",
            "read_only": True,
            "freecad_ref": {"type": obj.type, "name": obj.name, "label": obj.label},
        }

    return {"nodes": [node]}


def _array_to_feature_node(
    obj: FCStdObject, warnings: list[str]
) -> dict[str, Any]:
    """
    Draft::Array (ortho / polar / path) → ``draft_array`` feature node.

    Key properties:
      - ``ArrayType``   — "ortho" | "polar" | "circular"
      - ``Base``        — LinkRef to source object
      - ``NumberX``, ``NumberY``, ``NumberZ`` — ortho counts
      - ``IntervalX``, ``IntervalY``, ``IntervalZ`` — ortho spacings (Vectors)
      - ``NumberPolar`` — polar count
      - ``Angle``       — polar sweep angle
      - ``Axis``        — polar axis vector
      - ``Center``      — polar center vector
    """
    from .types import LinkRef

    node: dict[str, Any] = {
        "kind": "draft_array",
        "read_only": True,
        "freecad_ref": {"type": obj.type, "name": obj.name, "label": obj.label},
    }

    array_type = (obj.properties.get("ArrayType") or "ortho").lower()
    node["array_type"] = array_type

    # Source object
    base = obj.properties.get("Base")
    if isinstance(base, LinkRef):
        node["base_object"] = base.target_name

    if array_type in ("ortho", ""):
        for k in ("NumberX", "NumberY", "NumberZ"):
            v = obj.properties.get(k)
            if isinstance(v, int):
                node[k.lower()] = v
            elif v is not None:
                try:
                    node[k.lower()] = int(v)
                except (TypeError, ValueError):
                    pass
        for k in ("IntervalX", "IntervalY", "IntervalZ"):
            v = obj.properties.get(k)
            if isinstance(v, dict):
                node[k.lower()] = v

    elif array_type in ("polar", "circular"):
        for k in ("NumberPolar",):
            v = obj.properties.get(k)
            if isinstance(v, int):
                node["number_polar"] = v
        angle = _get_scalar(obj.properties, "Angle")
        if angle is not None:
            node["angle"] = angle
        axis = obj.properties.get("Axis")
        if isinstance(axis, dict):
            node["axis"] = axis
        center = obj.properties.get("Center")
        if isinstance(center, dict):
            node["center"] = center

    return node


def _clone_to_feature_node(
    obj: FCStdObject, warnings: list[str]
) -> dict[str, Any]:
    """
    Draft::Clone → ``draft_clone`` feature node.

    Key properties:
      - ``Objects``  — list of LinkRef (source objects)
      - ``Scale``    — Vector with scale factors
    """
    from .types import LinkRef

    node: dict[str, Any] = {
        "kind": "draft_clone",
        "read_only": True,
        "freecad_ref": {"type": obj.type, "name": obj.name, "label": obj.label},
    }

    objects = obj.properties.get("Objects") or []
    source_names: list[str] = []
    for item in objects:
        if isinstance(item, LinkRef):
            source_names.append(item.target_name)
        elif isinstance(item, str):
            source_names.append(item)
    if source_names:
        node["source_objects"] = source_names

    scale = obj.properties.get("Scale")
    if isinstance(scale, dict):
        node["scale"] = {
            "x": float(scale.get("x", 1.0) or 1.0),
            "y": float(scale.get("y", 1.0) or 1.0),
            "z": float(scale.get("z", 1.0) or 1.0),
        }

    return node


def _mirror_to_feature_node(
    obj: FCStdObject, warnings: list[str]
) -> dict[str, Any]:
    """Draft::Mirror → ``draft_mirror`` feature node."""
    from .types import LinkRef

    node: dict[str, Any] = {
        "kind": "draft_mirror",
        "read_only": True,
        "freecad_ref": {"type": obj.type, "name": obj.name, "label": obj.label},
    }

    source = obj.properties.get("Source")
    if isinstance(source, LinkRef):
        node["source_object"] = source.target_name

    p1 = obj.properties.get("P1")
    p2 = obj.properties.get("P2")
    if isinstance(p1, dict):
        node["mirror_p1"] = p1
    if isinstance(p2, dict):
        node["mirror_p2"] = p2

    return node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_scalar(props: dict, key: str) -> float | None:
    """Extract a scalar from a property dict (handles Quantity dicts)."""
    v = props.get(key)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "value" in v:
        try:
            return float(v["value"])
        except (TypeError, ValueError):
            return None
    return None


def _is_vector(v: Any) -> bool:
    """Return True if *v* looks like a 3D vector dict."""
    return isinstance(v, dict) and (
        "x" in v or "y" in v or "z" in v
    )


def _vec3(v: Any) -> dict[str, float]:
    """Normalise a vector-like value to {x, y, z}."""
    if not isinstance(v, dict):
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    return {
        "x": float(v.get("x", 0) or 0),
        "y": float(v.get("y", 0) or 0),
        "z": float(v.get("z", 0) or 0),
    }


def _vec2d(v: dict[str, float]) -> dict[str, float]:
    """Project a 3D vector onto the XY plane (drop z)."""
    return {"x": v.get("x", 0.0), "y": v.get("y", 0.0)}
