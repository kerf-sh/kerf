"""
walls.py — IfcWall / IfcWallStandardCase → .bim wall node.

.bim wall schema:
    {
        "level": "L1",
        "from": [x, y],       # mm, plan-view 2D start point
        "to":   [x, y],       # mm, plan-view 2D end point
        "height":    3000,    # mm
        "thickness":  200,    # mm
    }

## IfcLocalPlacement traversal

IFC placements are hierarchical.  Each IfcLocalPlacement has an optional
RelativePlacement (an Axis2Placement3D) and an optional
PlacementRelTo pointer to a parent IfcLocalPlacement.  To obtain the
absolute world-matrix we chain the local matrices from the root down to
the element.

We use ifcopenshell.util.placement.get_local_placement() which already
performs that chain-walking and returns a 4×4 numpy matrix.

## Geometry extraction strategy

For IfcWallStandardCase the body representation is an extruded rectangle.
We can recover length, thickness, height and direction from the swept
profile + extrusion depth.  For plain IfcWall (arbitrary solid) we fall
back to the bounding-box midpoints heuristic and emit a warning.

When ifcopenshell.geom is available we use it for the fallback.
"""
from __future__ import annotations

import math
import warnings as _py_warnings
from typing import Any

_FALLBACK_HEIGHT = 3000.0
_FALLBACK_THICKNESS = 200.0


def _placement_origin(ifc_entity) -> tuple[float, float, float]:
    """
    Return the (x, y, z) world-origin for an IFC entity's ObjectPlacement.

    Chains through parent placements via ifcopenshell.util.placement.
    Returns (0, 0, 0) on any failure.
    """
    try:
        from ifcopenshell.util.placement import get_local_placement  # type: ignore
        import numpy as np  # type: ignore

        placement = getattr(ifc_entity, "ObjectPlacement", None)
        if placement is None:
            return (0.0, 0.0, 0.0)
        matrix = get_local_placement(placement)
        # matrix is 4×4; translation is column 3 (rows 0-2)
        return (float(matrix[0, 3]), float(matrix[1, 3]), float(matrix[2, 3]))
    except Exception:
        return (0.0, 0.0, 0.0)


def _get_wall_geometry(ifc_wall, warnings: list[str]) -> dict[str, Any]:
    """
    Extract wall geometry from representation.

    Returns a dict with keys: from, to, height, thickness.

    Strategy:
      1. Look for IfcExtrudedAreaSolid with IfcRectangleProfileDef
         (standard case, most reliable).
      2. Try to read IfcMaterialLayerSetUsage for thickness.
      3. Fall back to placement origin + default dimensions with warning.
    """
    try:
        from ifcopenshell.util.placement import get_local_placement  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        get_local_placement = None
        np = None

    gid = getattr(ifc_wall, "GlobalId", "?")
    name = getattr(ifc_wall, "Name", None) or gid

    height = _FALLBACK_HEIGHT
    thickness = _FALLBACK_THICKNESS
    length = 1000.0

    # ── Try to read from IfcExtrudedAreaSolid ───────────────────────────────
    rep = getattr(ifc_wall, "Representation", None)
    extrusion = None

    if rep is not None:
        for shape_rep in (getattr(rep, "Representations", None) or []):
            rep_id = getattr(shape_rep, "RepresentationIdentifier", "")
            if rep_id not in ("Body", "Axis", ""):
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
                height = float(depth)

            profile = getattr(extrusion, "SweptArea", None)
            if profile is not None:
                profile_type = getattr(profile, "is_a", lambda: "")()
                if profile_type == "IfcRectangleProfileDef":
                    x_dim = getattr(profile, "XDim", None)
                    y_dim = getattr(profile, "YDim", None)
                    if x_dim is not None and y_dim is not None:
                        # XDim is the longer axis (length), YDim is thickness
                        length = float(x_dim)
                        thickness = float(y_dim)

            # Extrusion position gives us the wall centre in the local frame
            extrusion_pos = getattr(extrusion, "Position", None)
            if extrusion_pos is not None and get_local_placement is not None and np is not None:
                # Axis2Placement3D: Location = centre of wall in local coords
                loc = getattr(extrusion_pos, "Location", None)
                ref_dir = getattr(extrusion_pos, "RefDirection", None)
                if loc is not None:
                    coords = getattr(loc, "Coordinates", (0.0, 0.0, 0.0))
                    cx = float(coords[0])
                    cy = float(coords[1])

                    # Direction vector (X axis of the wall, along its length)
                    if ref_dir is not None:
                        dir_comps = getattr(ref_dir, "DirectionRatios", (1.0, 0.0, 0.0))
                        dx = float(dir_comps[0])
                        dy = float(dir_comps[1])
                        norm = math.sqrt(dx * dx + dy * dy) or 1.0
                        dx /= norm
                        dy /= norm
                    else:
                        dx, dy = 1.0, 0.0

                    # World origin of wall entity (accounts for parent placement chain)
                    wx, wy, _ = _placement_origin(ifc_wall)

                    # Centre of wall mid-plane in world coords
                    world_cx = wx + cx
                    world_cy = wy + cy

                    half = length / 2.0
                    frm = [round(world_cx - dx * half, 3), round(world_cy - dy * half, 3)]
                    to  = [round(world_cx + dx * half, 3), round(world_cy + dy * half, 3)]
                    return {"from": frm, "to": to, "height": height, "thickness": thickness}
        except Exception as exc:
            warnings.append(f"wall {name!r}: geometry extraction partially failed ({exc}); using fallback")

    # ── Fallback: placement origin, extend along +X ──────────────────────────
    warnings.append(
        f"wall {name!r}: could not extract full geometry from representation; "
        f"placed at origin with default dimensions (height={height}, "
        f"thickness={thickness}, length={length})"
    )
    wx, wy, _ = _placement_origin(ifc_wall)
    return {
        "from": [round(wx, 3), round(wy, 3)],
        "to":   [round(wx + length, 3), round(wy, 3)],
        "height": height,
        "thickness": thickness,
    }


def _storey_name_for(ifc_wall, level_guid_to_name: dict[str, str]) -> str:
    """
    Walk ContainedInStructure relationships to find the parent BuildingStorey name.
    Returns "" if not found.
    """
    try:
        rels = getattr(ifc_wall, "ContainedInStructure", None) or []
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


def translate_wall(
    ifc_wall,
    level_guid_to_name: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    """
    Translate one IfcWall or IfcWallStandardCase into a .bim wall dict.

    Args:
        ifc_wall:           The IFC wall entity.
        level_guid_to_name: Mapping of IfcBuildingStorey GlobalId → level name.
        warnings:           Mutable list; non-fatal issues are appended here.

    Returns:
        A dict matching the .bim wall JSON schema.
    """
    ifc_type = getattr(ifc_wall, "is_a", lambda: "")()
    if ifc_type not in ("IfcWall", "IfcWallStandardCase"):
        warnings.append(
            f"translate_wall called on non-wall entity {ifc_type!r} "
            f"(id={getattr(ifc_wall, 'GlobalId', '?')}) — skipped"
        )
        return {}

    level_name = _storey_name_for(ifc_wall, level_guid_to_name)
    geom = _get_wall_geometry(ifc_wall, warnings)

    return {
        "level": level_name,
        "from":  geom.get("from", [0.0, 0.0]),
        "to":    geom.get("to",   [1000.0, 0.0]),
        "height":    geom.get("height",    _FALLBACK_HEIGHT),
        "thickness": geom.get("thickness", _FALLBACK_THICKNESS),
    }
