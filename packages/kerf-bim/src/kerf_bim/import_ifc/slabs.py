"""
slabs.py — IfcSlab → .bim slab node.

.bim slab schema:
    {
        "level": "L1",
        "boundary": [[x0, y0], [x1, y1], ...],   # mm, plan-view polygon
        "thickness": 200,                           # mm
    }

Geometry extraction:
  - IfcExtrudedAreaSolid with IfcArbitraryClosedProfileDef → read polyline
    boundary and extrusion depth.
  - IfcExtrudedAreaSolid with IfcRectangleProfileDef → reconstruct
    rectangular boundary from XDim × YDim centred at profile position.
  - Anything else → default 1m×1m square with warning.
"""
from __future__ import annotations

import math
from typing import Any

_FALLBACK_THICKNESS = 200.0


def _placement_origin(ifc_entity) -> tuple[float, float, float]:
    """World-space origin of entity's ObjectPlacement. Returns (0,0,0) on failure."""
    try:
        from ifcopenshell.util.placement import get_local_placement  # type: ignore
        placement = getattr(ifc_entity, "ObjectPlacement", None)
        if placement is None:
            return (0.0, 0.0, 0.0)
        m = get_local_placement(placement)
        return (float(m[0, 3]), float(m[1, 3]), float(m[2, 3]))
    except Exception:
        return (0.0, 0.0, 0.0)


def _storey_name_for(ifc_slab, level_guid_to_name: dict[str, str]) -> str:
    try:
        rels = getattr(ifc_slab, "ContainedInStructure", None) or []
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


def _extract_boundary_and_thickness(
    ifc_slab,
    warnings: list[str],
) -> tuple[list[list[float]], float]:
    """
    Try to extract the plan-view boundary polygon and thickness.

    Returns (boundary, thickness) where boundary is a list of [x, y] points.
    """
    gid = getattr(ifc_slab, "GlobalId", "?")
    name = getattr(ifc_slab, "Name", None) or gid

    thickness = _FALLBACK_THICKNESS
    boundary: list[list[float]] = []

    rep = getattr(ifc_slab, "Representation", None)
    extrusion = None

    if rep is not None:
        for shape_rep in (getattr(rep, "Representations", None) or []):
            rep_id = getattr(shape_rep, "RepresentationIdentifier", "")
            if rep_id not in ("Body", ""):
                continue
            for item in (getattr(shape_rep, "Items", None) or []):
                ifc_type = getattr(item, "is_a", lambda: "")()
                if ifc_type == "IfcExtrudedAreaSolid":
                    extrusion = item
                    break
            if extrusion is not None:
                break

    if extrusion is not None:
        try:
            depth = getattr(extrusion, "Depth", None)
            if depth is not None:
                thickness = float(depth)

            profile = getattr(extrusion, "SweptArea", None)
            if profile is not None:
                profile_type = getattr(profile, "is_a", lambda: "")()

                if profile_type == "IfcArbitraryClosedProfileDef":
                    outer = getattr(profile, "OuterCurve", None)
                    if outer is not None:
                        pts = getattr(outer, "Points", None) or []
                        for pt in pts:
                            coords = getattr(pt, "Coordinates", None)
                            if coords is not None:
                                x = float(coords[0])
                                y = float(coords[1])
                                boundary.append([round(x, 3), round(y, 3)])
                        # Remove closing duplicate if present
                        if len(boundary) > 1 and boundary[0] == boundary[-1]:
                            boundary = boundary[:-1]

                elif profile_type == "IfcRectangleProfileDef":
                    x_dim = float(getattr(profile, "XDim", 1000) or 1000)
                    y_dim = float(getattr(profile, "YDim", 1000) or 1000)
                    hx = x_dim / 2.0
                    hy = y_dim / 2.0

                    # Get profile position offset
                    pos = getattr(profile, "Position", None)
                    cx, cy = 0.0, 0.0
                    if pos is not None:
                        loc = getattr(pos, "Location", None)
                        if loc is not None:
                            c = getattr(loc, "Coordinates", (0.0, 0.0))
                            cx = float(c[0])
                            cy = float(c[1])
                    boundary = [
                        [round(cx - hx, 3), round(cy - hy, 3)],
                        [round(cx + hx, 3), round(cy - hy, 3)],
                        [round(cx + hx, 3), round(cy + hy, 3)],
                        [round(cx - hx, 3), round(cy + hy, 3)],
                    ]
        except Exception as exc:
            warnings.append(
                f"slab {name!r}: geometry extraction failed ({exc}); using default boundary"
            )

    if not boundary:
        warnings.append(
            f"slab {name!r}: no boundary extracted; using 1000×1000 default"
        )
        wx, wy, _ = _placement_origin(ifc_slab)
        boundary = [
            [round(wx, 3),        round(wy, 3)],
            [round(wx + 1000, 3), round(wy, 3)],
            [round(wx + 1000, 3), round(wy + 1000, 3)],
            [round(wx, 3),        round(wy + 1000, 3)],
        ]

    return boundary, thickness


def translate_slab(
    ifc_slab,
    level_guid_to_name: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    """
    Translate one IfcSlab entity into a .bim slab dict.

    Only FLOOR and ROOF predefined types are relevant for Tier 1.
    LANDING, BASESLAB, NOTDEFINED are also accepted (no warning).
    """
    level_name = _storey_name_for(ifc_slab, level_guid_to_name)
    boundary, thickness = _extract_boundary_and_thickness(ifc_slab, warnings)

    return {
        "level": level_name,
        "boundary": boundary,
        "thickness": thickness,
    }
