"""
views.py — IFC plan/section context → .view.json payload.

IFC drawing context model
--------------------------
IFC4 stores drawing views via IfcShapeAspect and IfcPresentationLayerAssignment,
but the more direct mechanism for plan/section views is via the drawing exchange
(IFC4-STEP / IFC-CA1) types:

  IfcAnnotation with ObjectType="DRAWING" (IFC4 annotation)
  IfcDrawingDefinition (IFC2x3 extension, rare)

In practice, most BIM authoring tools (Revit, ArchiCAD) export IFC
geometric context via IfcGeometricRepresentationContext subtypes:

  IfcGeometricRepresentationContext
      ContextType: "Model" | "Plan" | "Elevation" | "Section"
      CoordinateSpaceDimension: 2 | 3
      TrueNorth: optional direction vector
      WorldCoordinateSystem: IfcAxis2Placement3D at project origin

  IfcGeometricRepresentationSubContext
      ContextIdentifier: "Body" | "Axis" | "FootPrint" | "Sketch" |
                         "PlanView" | "SectionView" | "Elevation" etc.
      TargetScale, TargetView

We translate each IfcGeometricRepresentationSubContext (and its parent
IfcGeometricRepresentationContext if only that exists) into a .view.json
payload.

.view.json payload (schema version 1)
--------------------------------------
{
    "version": 1,
    "id": "<ifc_guid>",
    "name": "<context_type>/<context_identifier>",
    "kind": "plan" | "section" | "elevation" | "3d",
    "bim_file_id": null,            # not known at import time
    "level_id": null,               # not resolved at Tier 2
    "cut_plane_z_mm": null,
    "section_origin": null,
    "section_direction": null,
    "crop_box": null,
    "filters": [],
    "display_overrides": {},
    "annotations": [],
    "ifc_context_type": "Plan",     # raw ContextType attribute
    "ifc_context_identifier": "PlanView",  # raw ContextIdentifier
    "true_north_deg": null,         # decimal degrees from TrueNorth vector
}

Caveats
-------
- IfcAnnotation/IfcDrawingDefinition views are Tier 3 (complex geometry).
- Camera parameters, crop boxes, display overrides require IfcPresentationLayer
  traversal — deferred to Tier 3.
- true_north_deg is extracted from TrueNorth DirectionRatios where available.
"""
from __future__ import annotations

import math
from typing import Any


def _context_type_to_view_kind(context_type: str, identifier: str) -> str:
    """Map ContextType + identifier string to view kind."""
    combined = (context_type + "/" + identifier).lower()
    if "plan" in combined or "footprint" in combined:
        return "plan"
    if "section" in combined:
        return "section"
    if "elevation" in combined:
        return "elevation"
    return "3d"


def _true_north_degrees(true_north) -> float | None:
    """
    Extract decimal degrees (clockwise from project north) from an IFC
    TrueNorth direction vector (IfcDirection).
    Returns None if not resolvable.
    """
    if true_north is None:
        return None
    try:
        ratios = getattr(true_north, "DirectionRatios", None)
        if ratios is None or len(ratios) < 2:
            return None
        x = float(ratios[0])
        y = float(ratios[1])
        # atan2 gives CCW from +X; IFC TrueNorth is the direction of true north
        # in the project coordinate system (Y=north by convention).
        # Convert to clockwise degrees from north.
        angle_ccw_from_y = math.degrees(math.atan2(x, y))
        return round(angle_ccw_from_y % 360.0, 4)
    except Exception:
        return None


def translate_representation_context(
    ifc_context,
    warnings: list[str],
) -> dict[str, Any]:
    """
    Translate one IfcGeometricRepresentationContext or SubContext into a
    .view.json payload dict.

    Args:
        ifc_context:  The IFC context entity.
        warnings:     Mutable list; non-fatal issues appended here.

    Returns:
        A dict matching the .view.json schema subset, or {} on hard failure.
    """
    ifc_class = getattr(ifc_context, "is_a", lambda: "")()
    if "GeometricRepresentation" not in ifc_class:
        return {}

    context_type = str(getattr(ifc_context, "ContextType", None) or "Model")
    context_id = str(getattr(ifc_context, "ContextIdentifier", None) or "")

    gid = getattr(ifc_context, "GlobalId", None)
    if gid is None:
        # Contexts don't always carry GlobalId — use Python id as fallback
        gid = f"ctx-{id(ifc_context)}"
    else:
        gid = str(gid)

    view_name = context_type
    if context_id:
        view_name = f"{context_type}/{context_id}"

    kind = _context_type_to_view_kind(context_type, context_id)

    # TrueNorth from parent context if this is a subcontext
    true_north = getattr(ifc_context, "TrueNorth", None)
    parent_ctx = getattr(ifc_context, "ParentContext", None)
    if true_north is None and parent_ctx is not None:
        true_north = getattr(parent_ctx, "TrueNorth", None)

    true_north_deg = _true_north_degrees(true_north)

    return {
        "version": 1,
        "id": gid,
        "name": view_name,
        "kind": kind,
        "bim_file_id": None,
        "level_id": None,
        "cut_plane_z_mm": None,
        "section_origin": None,
        "section_direction": None,
        "crop_box": None,
        "filters": [],
        "display_overrides": {},
        "annotations": [],
        "ifc_context_type": context_type,
        "ifc_context_identifier": context_id,
        "true_north_deg": true_north_deg,
    }


def extract_views(
    ifc_file,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """
    Extract all geometric representation contexts from an IFC file and
    translate them to .view.json payload dicts.

    Args:
        ifc_file:   An open ifcopenshell file object.
        warnings:   Mutable list; non-fatal issues appended here.

    Returns:
        A list of .view.json payload dicts.
    """
    views: list[dict[str, Any]] = []
    seen_gids: set[str] = set()

    # Query subcontexts first (more specific), then parent contexts
    for query_type in (
        "IfcGeometricRepresentationSubContext",
        "IfcGeometricRepresentationContext",
    ):
        try:
            contexts = ifc_file.by_type(query_type)
        except Exception as exc:
            warnings.append(f"{query_type} query failed: {exc}")
            continue

        for ctx in contexts:
            try:
                payload = translate_representation_context(ctx, warnings)
                if not payload:
                    continue
                gid = payload.get("id", "")
                if gid in seen_gids:
                    continue
                seen_gids.add(gid)
                views.append(payload)
            except Exception as exc:
                ctx_name = getattr(ctx, "ContextType", "?")
                warnings.append(f"view context {ctx_name!r}: translation failed ({exc}); skipped")

    return views
