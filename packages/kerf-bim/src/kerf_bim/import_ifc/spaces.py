"""
spaces.py — IfcSpace → .bim space node.

.bim space schema:
    {
        "level": "L1",
        "boundary": [[x0, y0], [x1, y1], ...],   # mm, plan-view polygon
        "name": "Living Room",
    }

Geometry extraction:
  - IfcExtrudedAreaSolid with closed profile → boundary polygon.
  - IfcFootprintCurve (space boundary curve) as alternative.
  - Fallback to 1m×1m square at placement origin with warning.
"""
from __future__ import annotations

from typing import Any

_FALLBACK_SIZE = 1000.0


def _placement_origin(ifc_entity) -> tuple[float, float, float]:
    try:
        from ifcopenshell.util.placement import get_local_placement  # type: ignore
        placement = getattr(ifc_entity, "ObjectPlacement", None)
        if placement is None:
            return (0.0, 0.0, 0.0)
        m = get_local_placement(placement)
        return (float(m[0, 3]), float(m[1, 3]), float(m[2, 3]))
    except Exception:
        return (0.0, 0.0, 0.0)


def _storey_name_for(ifc_space, level_guid_to_name: dict[str, str]) -> str:
    # IfcSpace can be decomposed under a storey via IfcRelAggregates
    try:
        rels = getattr(ifc_space, "Decomposes", None) or []
        for rel in rels:
            relating = getattr(rel, "RelatingObject", None)
            if relating is None:
                continue
            ifc_type = getattr(relating, "is_a", lambda: "")()
            if ifc_type == "IfcBuildingStorey":
                gid = getattr(relating, "GlobalId", "")
                return level_guid_to_name.get(gid, getattr(relating, "Name", "") or "")
    except Exception:
        pass
    # Also try ContainedInStructure (some exporters use this for spaces too)
    try:
        rels = getattr(ifc_space, "ContainedInStructure", None) or []
        for rel in rels:
            structure = getattr(rel, "RelatingStructure", None)
            if structure is None:
                continue
            ifc_type = getattr(structure, "is_a", lambda: "")()
            if ifc_type == "IfcBuildingStorey":
                gid = getattr(structure, "GlobalId", "")
                return level_guid_to_name.get(gid, getattr(structure, "Name", "") or "")
    except Exception:
        pass
    return ""


def _extract_boundary(ifc_space, warnings: list[str]) -> list[list[float]]:
    """
    Try to extract plan-view boundary polygon from space representation.
    Returns list of [x, y] points (no closing duplicate).
    """
    gid = getattr(ifc_space, "GlobalId", "?")
    name = getattr(ifc_space, "Name", None) or gid

    rep = getattr(ifc_space, "Representation", None)
    if rep is None:
        warnings.append(f"space {name!r}: no representation; using default boundary")
        wx, wy, _ = _placement_origin(ifc_space)
        s = _FALLBACK_SIZE
        return [
            [round(wx, 3),   round(wy, 3)],
            [round(wx+s, 3), round(wy, 3)],
            [round(wx+s, 3), round(wy+s, 3)],
            [round(wx, 3),   round(wy+s, 3)],
        ]

    # Prefer "FootPrint" representation identifier, fall back to "Body"
    best_rep = None
    for shape_rep in (getattr(rep, "Representations", None) or []):
        rep_id = getattr(shape_rep, "RepresentationIdentifier", "")
        if rep_id == "FootPrint":
            best_rep = shape_rep
            break
    if best_rep is None:
        for shape_rep in (getattr(rep, "Representations", None) or []):
            rep_id = getattr(shape_rep, "RepresentationIdentifier", "")
            if rep_id == "Body":
                best_rep = shape_rep
                break

    if best_rep is None:
        all_reps = getattr(rep, "Representations", None) or []
        if all_reps:
            best_rep = all_reps[0]

    if best_rep is None:
        warnings.append(f"space {name!r}: no usable representation found; using default boundary")
        wx, wy, _ = _placement_origin(ifc_space)
        s = _FALLBACK_SIZE
        return [
            [round(wx, 3),   round(wy, 3)],
            [round(wx+s, 3), round(wy, 3)],
            [round(wx+s, 3), round(wy+s, 3)],
            [round(wx, 3),   round(wy+s, 3)],
        ]

    boundary: list[list[float]] = []
    try:
        for item in (getattr(best_rep, "Items", None) or []):
            ifc_type = getattr(item, "is_a", lambda: "")()

            if ifc_type == "IfcExtrudedAreaSolid":
                profile = getattr(item, "SweptArea", None)
                if profile is not None:
                    pt = getattr(profile, "is_a", lambda: "")()
                    if pt == "IfcArbitraryClosedProfileDef":
                        outer = getattr(profile, "OuterCurve", None)
                        if outer is not None:
                            pts = getattr(outer, "Points", None) or []
                            for p in pts:
                                c = getattr(p, "Coordinates", None)
                                if c is not None:
                                    boundary.append([round(float(c[0]), 3), round(float(c[1]), 3)])
                            if boundary and boundary[0] == boundary[-1]:
                                boundary = boundary[:-1]
                            if boundary:
                                break

            elif ifc_type in ("IfcPolyline", "IfcCompositeCurve"):
                pts = getattr(item, "Points", None) or []
                for p in pts:
                    c = getattr(p, "Coordinates", None)
                    if c is not None:
                        boundary.append([round(float(c[0]), 3), round(float(c[1]), 3)])
                if boundary and boundary[0] == boundary[-1]:
                    boundary = boundary[:-1]
                if boundary:
                    break

    except Exception as exc:
        warnings.append(f"space {name!r}: boundary extraction error ({exc}); using default")
        boundary = []

    if not boundary:
        warnings.append(f"space {name!r}: could not extract boundary polygon; using default")
        wx, wy, _ = _placement_origin(ifc_space)
        s = _FALLBACK_SIZE
        boundary = [
            [round(wx, 3),   round(wy, 3)],
            [round(wx+s, 3), round(wy, 3)],
            [round(wx+s, 3), round(wy+s, 3)],
            [round(wx, 3),   round(wy+s, 3)],
        ]

    return boundary


def translate_space(
    ifc_space,
    level_guid_to_name: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    """
    Translate one IfcSpace entity into a .bim space dict.
    """
    name_attr = getattr(ifc_space, "Name", None) or ""
    long_name = getattr(ifc_space, "LongName", None) or ""
    display_name = long_name or name_attr or "Space"

    level_name = _storey_name_for(ifc_space, level_guid_to_name)
    boundary = _extract_boundary(ifc_space, warnings)

    return {
        "level": level_name,
        "boundary": boundary,
        "name": str(display_name),
    }
