"""
datums.py — Tier 3: PartDesign datum objects → Kerf reference geometry.

Translates:
  - ``PartDesign::Plane``  → sketch plane reference dict
  - ``PartDesign::Line``   → datum axis / reference line dict
  - ``PartDesign::Point``  → datum point dict

These are emitted as entries in ``.sketch`` files (as ``datum_refs``) or
attached to feature nodes that reference them as placement origins.

Usage::

    from kerf_imports.freecad.datums import translate_datum, build_datum_map

    datum_map = build_datum_map(doc)
    # datum_map["DatumPlane"] → {"kind": "datum_plane", "placement": {...}, ...}
"""
from __future__ import annotations

import logging
import math
from typing import Any

from .types import FCStdDocument, FCStdObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FreeCAD datum type strings
# ---------------------------------------------------------------------------

_DATUM_PLANE_TYPES: frozenset[str] = frozenset({
    "PartDesign::Plane",
})

_DATUM_LINE_TYPES: frozenset[str] = frozenset({
    "PartDesign::Line",
})

_DATUM_POINT_TYPES: frozenset[str] = frozenset({
    "PartDesign::Point",
})

ALL_DATUM_TYPES: frozenset[str] = (
    _DATUM_PLANE_TYPES | _DATUM_LINE_TYPES | _DATUM_POINT_TYPES
)

# ---------------------------------------------------------------------------
# PartDesign attachment mode → Kerf plane description
# ---------------------------------------------------------------------------

# FreeCAD MapMode strings → human-readable Kerf plane type
_MAP_MODE_TO_PLANE: dict[str, str] = {
    "FlatFace":          "face",
    "TangentPlane":      "tangent_face",
    "NormalToPath":      "normal_to_path",
    "ThreePoints":       "three_point",
    "ObjectXY":          "world_xy",
    "ObjectYZ":          "world_yz",
    "ObjectXZ":          "world_xz",
    "PlaneX":            "axis_x",
    "PlaneY":            "axis_y",
    "PlaneZ":            "axis_z",
    "Concentric":        "concentric",
    "Deactivated":       "free",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def translate_datum(obj: FCStdObject) -> dict[str, Any] | None:
    """
    Translate one PartDesign datum object (Plane/Line/Point) to a Kerf dict.

    Returns ``None`` for unsupported or empty objects; never raises.

    Returns
    -------
    dict with keys:
        ``kind``            — ``"datum_plane"`` | ``"datum_line"`` | ``"datum_point"``
        ``name``            — FreeCAD internal name
        ``label``           — user-visible label
        ``placement``       — raw FreeCAD placement dict (position + rotation)
        ``map_mode``        — Kerf plane type string (from MapMode)
        ``map_reversed``    — bool
        ``support_refs``    — list of supporting geometry references (best-effort)
        ``freecad_ref``     — provenance dict
    """
    if obj.type in _DATUM_PLANE_TYPES:
        kind = "datum_plane"
    elif obj.type in _DATUM_LINE_TYPES:
        kind = "datum_line"
    elif obj.type in _DATUM_POINT_TYPES:
        kind = "datum_point"
    else:
        return None

    result: dict[str, Any] = {
        "kind": kind,
        "name": obj.name,
        "label": obj.label,
        "freecad_ref": {
            "type": obj.type,
            "name": obj.name,
            "label": obj.label,
        },
    }

    # Placement
    placement = obj.properties.get("Placement")
    if placement and isinstance(placement, dict):
        result["placement"] = placement

    # MapMode
    map_mode_raw = obj.properties.get("MapMode")
    if isinstance(map_mode_raw, str):
        result["map_mode"] = _MAP_MODE_TO_PLANE.get(map_mode_raw, map_mode_raw)
    else:
        result["map_mode"] = "free"

    # MapReversed
    map_rev = obj.properties.get("MapReversed")
    result["map_reversed"] = bool(map_rev) if map_rev is not None else False

    # Support references (the linked faces / edges that define the datum)
    support = obj.properties.get("Support")
    if support is not None:
        result["support_refs"] = _extract_support_refs(support)

    # AttachmentOffset
    att_offset = obj.properties.get("AttachmentOffset")
    if att_offset and isinstance(att_offset, dict):
        result["attachment_offset"] = att_offset

    return result


def build_datum_map(doc: FCStdDocument) -> dict[str, dict[str, Any]]:
    """
    Walk all PartDesign datum objects in *doc* and return a mapping from
    object name → translated datum dict.

    Objects that fail translation are logged and skipped.

    Parameters
    ----------
    doc :
        Parsed :class:`~kerf_imports.freecad.types.FCStdDocument`.

    Returns
    -------
    dict[str, dict]
        Mapping from FreeCAD internal object name to datum dict.
    """
    result: dict[str, dict[str, Any]] = {}

    for obj in doc.objects:
        if obj.type not in ALL_DATUM_TYPES:
            continue
        try:
            datum = translate_datum(obj)
        except Exception as exc:
            logger.warning("datum '%s' (%s): translation error — %s", obj.name, obj.type, exc)
            continue
        if datum is not None:
            result[obj.name] = datum

    return result


def sketch_attachment_from_datum(
    sketch_obj: FCStdObject, datum_map: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """
    Resolve the sketch's attachment datum, if any.

    FreeCAD stores the sketch's attachment support in ``MapMode`` + ``Support``
    (a ``LinkRef`` pointing to a datum plane or a body face).  When the support
    is a named datum in *datum_map*, we return a reference to it so Kerf can
    wire the sketch to the correct plane.

    Parameters
    ----------
    sketch_obj :
        A ``Sketcher::SketchObject`` FCStdObject.
    datum_map :
        Result of :func:`build_datum_map`.

    Returns
    -------
    dict or None
        ``{"datum_name": str, "datum_kind": str, "map_mode": str}`` if resolved;
        ``None`` if the sketch has no datum attachment or the datum is not in the map.
    """
    from .types import LinkRef  # avoid circular at module level

    support = sketch_obj.properties.get("Support")
    if support is None:
        return None

    # Support can be a single LinkRef or a list of LinkRefs
    target_name: str | None = None
    if isinstance(support, LinkRef):
        target_name = support.target_name
    elif isinstance(support, list) and support:
        first = support[0]
        if isinstance(first, LinkRef):
            target_name = first.target_name

    if target_name is None:
        return None

    datum = datum_map.get(target_name)
    if datum is None:
        return None

    return {
        "datum_name": target_name,
        "datum_label": datum.get("label", target_name),
        "datum_kind": datum.get("kind", "datum_plane"),
        "map_mode": datum.get("map_mode", "free"),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_support_refs(support: Any) -> list[dict[str, Any]]:
    """Extract human-readable support references from a Support property value."""
    from .types import LinkRef  # avoid circular at module level

    refs: list[dict[str, Any]] = []
    if isinstance(support, LinkRef):
        ref: dict[str, Any] = {"object": support.target_name}
        if support.sub_elements:
            ref["sub_elements"] = support.sub_elements
        refs.append(ref)
    elif isinstance(support, list):
        for item in support:
            if isinstance(item, LinkRef):
                r: dict[str, Any] = {"object": item.target_name}
                if item.sub_elements:
                    r["sub_elements"] = item.sub_elements
                refs.append(r)
    return refs
