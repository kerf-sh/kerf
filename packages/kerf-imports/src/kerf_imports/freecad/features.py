"""
features.py — T4 PartDesign feature-tree metadata capture.

Usage::

    from kerf_imports.freecad.features import build_metadata_tree

    payload = build_metadata_tree(doc, brep_assets)
    # Returns a list[FeaturePayload] — one entry per PartDesign::Body.
    # Each payload.nodes starts with one import_brep node (from T2)
    # followed by read-only metadata nodes (one per Pad/Pocket/Fillet/…).

Design contract (from the plan doc):
- Every metadata node carries ``read_only: true`` and a
  ``freecad_ref: { type, name, doc }`` provenance field.
- The OCCT worker skips nodes that have ``read_only: true``; the BRep
  from the preceding ``import_brep`` node is the source of truth.
- Sketch references are emitted as relative paths: ``/<sketch_name>.sketch``.
"""
from __future__ import annotations

import logging
from typing import Any

from .types import FCStdDocument, FCStdObject, LinkRef
from .brep_importer import ImportResult, FeaturePayload, FeatureNode, build_feature_tree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FreeCAD PartDesign type → Kerf metadata op
# ---------------------------------------------------------------------------

# Mapping from FreeCAD PartDesign::* type strings to Kerf op names.
# All of these are emitted as read_only: true metadata nodes.
_PD_TYPE_TO_OP: dict[str, str] = {
    "PartDesign::Pad":              "pad",
    "PartDesign::Pocket":           "pocket",
    "PartDesign::Revolution":       "revolve",
    "PartDesign::Groove":           "revolve",   # Groove is a subtractive Revolution
    "PartDesign::Hole":             "hole",
    "PartDesign::Fillet":           "fillet",
    "PartDesign::Chamfer":          "chamfer",
    "PartDesign::Draft":            "feature_draft",
    "PartDesign::Thickness":        "shell",
    "PartDesign::LinearPattern":    "linear_pattern",
    "PartDesign::PolarPattern":     "polar_pattern",
    "PartDesign::Mirrored":         "mirror_pattern",
    "PartDesign::MultiTransform":   "feature_multi_transform",
    "PartDesign::Helix":            "feature_helix",
    "PartDesign::Rib":              "feature_rib",
    "PartDesign::AdditiveLoft":     "loft",
    "PartDesign::SubtractiveLoft":  "loft",
    "PartDesign::AdditivePipe":     "sweep1",
    "PartDesign::SubtractivePipe":  "sweep1",
    "PartDesign::AdditiveHelix":    "feature_helix",
    "PartDesign::SubtractiveHelix": "feature_helix",
    # Catch-all for future types: any PartDesign:: not listed above
}

# Features we skip entirely: they are organisational containers, not geometry ops.
_SKIP_TYPES: frozenset[str] = frozenset({
    "PartDesign::Body",
    "PartDesign::CoordinateSystem",
    "PartDesign::Point",
    "PartDesign::Line",
    "PartDesign::Plane",
    "PartDesign::ShapeBinder",
    "PartDesign::SubShapeBinder",
    "App::Origin",
    "App::Line",
    "App::Plane",
})

# Feature types that primarily operate on edge/face refs.
_EDGE_REF_TYPES: frozenset[str] = frozenset({
    "PartDesign::Fillet",
    "PartDesign::Chamfer",
    "PartDesign::Draft",
})

# Feature types that carry sketch profile references.
_PROFILE_TYPES: frozenset[str] = frozenset({
    "PartDesign::Pad",
    "PartDesign::Pocket",
    "PartDesign::Revolution",
    "PartDesign::Groove",
    "PartDesign::Hole",
    "PartDesign::Rib",
})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_metadata_tree(
    doc: FCStdDocument,
    brep_assets: dict[str, bytes] | None = None,
) -> list[FeaturePayload]:
    """
    Walk the PartDesign features in *doc* and return one :class:`FeaturePayload`
    per top-level ``PartDesign::Body``.

    Each payload contains:
    1. An ``import_brep`` node (the BRep-lifted solid from T2).
    2. Read-only metadata nodes — one per PartDesign feature — carrying
       ``read_only: true`` and a ``freecad_ref`` provenance field.

    Parameters
    ----------
    doc :
        Parsed :class:`~kerf_imports.freecad.types.FCStdDocument`.
    brep_assets :
        Optional mapping from ``asset_id`` to raw BRep bytes — if omitted,
        :func:`build_feature_tree` (T2) is called internally to build it.

    Returns
    -------
    list[FeaturePayload]
    """
    # Build the T2 import_brep results first.
    t2_result: ImportResult = build_feature_tree(doc)

    # Index T2 features by body_name for fast lookup.
    t2_by_body: dict[str, FeaturePayload] = {
        fp.body_name: fp for fp in t2_result.features
    }

    bodies = doc.objects_by_type("PartDesign::Body")
    if not bodies:
        # Fallback: if T2 found a synthetic body, use it.
        return t2_result.features

    payloads: list[FeaturePayload] = []

    for body in bodies:
        # ── Find which features belong to this body ───────────────────────────
        body_features = _features_for_body(body, doc)

        # ── Start with the import_brep node from T2 ───────────────────────────
        t2_payload = t2_by_body.get(body.name)
        nodes: list[FeatureNode] = []
        if t2_payload:
            nodes.extend(t2_payload.nodes)
        else:
            # No BRep found — emit a placeholder import_brep node.
            nodes.append(FeatureNode(
                kind="import_brep",
                params={
                    "asset_id": None,
                    "source_body": body.name,
                    "warning": "no_brep_blob_found",
                },
            ))

        # ── Append read-only metadata nodes for each feature ──────────────────
        for feat in body_features:
            meta_node = _feature_to_metadata_node(feat, doc)
            if meta_node is not None:
                nodes.append(meta_node)

        payloads.append(FeaturePayload(
            body_name=body.name,
            body_label=body.label,
            nodes=nodes,
        ))

    return payloads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _features_for_body(
    body: FCStdObject, doc: FCStdDocument
) -> list[FCStdObject]:
    """
    Return the ordered list of PartDesign features that belong to *body*.

    FreeCAD uses a ``Model`` or ``Group`` property on the Body to list its
    members (as a list of LinkRefs).  Falling back to scanning all objects
    whose ``BaseFeature`` / ``Profile`` Link points back to an object
    already in the body.
    """
    members: list[FCStdObject] = []

    # Strategy 1: Body.Model (FreeCAD >= 0.17) or Body.Group (older)
    for prop_name in ("Model", "Group"):
        raw = body.properties.get(prop_name)
        if raw is None:
            continue
        if isinstance(raw, list):
            for ref in raw:
                if isinstance(ref, LinkRef):
                    obj = doc.object_by_name(ref.target_name)
                elif isinstance(ref, str):
                    obj = doc.object_by_name(ref)
                else:
                    continue
                if obj is not None and obj.type not in _SKIP_TYPES:
                    members.append(obj)
            if members:
                return members

    # Strategy 2: scan all non-Body objects; include those whose type is a
    # known PartDesign feature op.  This catches bodies that lack Model/Group.
    for obj in doc.objects:
        if obj.name == body.name:
            continue
        if obj.type in _SKIP_TYPES:
            continue
        if obj.type.startswith("PartDesign::") and obj.type not in _SKIP_TYPES:
            members.append(obj)

    return members


def _feature_to_metadata_node(
    feat: FCStdObject, doc: FCStdDocument
) -> FeatureNode | None:
    """
    Convert one PartDesign feature to a read-only metadata FeatureNode.

    Returns None for features that should be silently skipped.
    """
    if feat.type in _SKIP_TYPES:
        return None
    if feat.type.startswith("Sketcher::"):
        # Sketches are handled separately as .sketch files; skip here.
        return None
    if feat.type.startswith("App::"):
        return None

    # Resolve Kerf op name (fall back to generic "freecad_feature" for unknowns).
    op = _PD_TYPE_TO_OP.get(feat.type)
    if op is None:
        if feat.type.startswith("PartDesign::"):
            op = "freecad_feature"
        else:
            return None  # Non-PartDesign, non-Sketch — skip silently

    params: dict[str, Any] = {
        "read_only": True,
        "freecad_ref": {
            "type": feat.type,
            "name": feat.name,
            "label": feat.label,
        },
    }

    # ── Sketch profile reference ──────────────────────────────────────────────
    if feat.type in _PROFILE_TYPES:
        sketch_path = _resolve_sketch_path(feat, doc)
        if sketch_path:
            params["sketch_path"] = sketch_path

    # ── Dimension / depth parameters ─────────────────────────────────────────
    _extract_dimension_params(feat, op, params)

    # ── Edge/face references (fillets, chamfers, draft) ──────────────────────
    if feat.type in _EDGE_REF_TYPES:
        _extract_edge_refs(feat, params)

    # ── Pattern parameters ────────────────────────────────────────────────────
    if "pattern" in op:
        _extract_pattern_params(feat, op, params)

    # ── Loft / sweep profiles ─────────────────────────────────────────────────
    if op in ("loft", "sweep1"):
        _extract_multi_profile_params(feat, doc, params)

    return FeatureNode(kind=op, params=params)


def _resolve_sketch_path(feat: FCStdObject, doc: FCStdDocument) -> str | None:
    """Return the relative .sketch path for the feature's Profile link, or None."""
    profile_ref = feat.properties.get("Profile")
    if isinstance(profile_ref, LinkRef):
        sketch_name = profile_ref.target_name
    elif isinstance(profile_ref, str) and profile_ref:
        sketch_name = profile_ref
    else:
        return None
    sketch_obj = doc.object_by_name(sketch_name)
    if sketch_obj is None:
        return f"/{sketch_name}.sketch"
    return f"/{sketch_obj.label}.sketch"


def _extract_dimension_params(
    feat: FCStdObject, op: str, params: dict
) -> None:
    """Extract Length/Height/Angle parameters from the feature properties."""
    props = feat.properties

    # Pad / Pocket depth
    for key in ("Length", "Length2"):
        v = _get_scalar(props, key)
        if v is not None:
            params[key.lower()] = v

    # Revolution / Groove angle
    for key in ("Angle", "Angle2"):
        v = _get_scalar(props, key)
        if v is not None:
            import math
            params[key.lower()] = math.degrees(v) if v > 6.3 else v  # heuristic: radians vs degrees

    # Direction / mode enumerations
    for key in ("Midplane", "Reversed", "Symmetric"):
        v = props.get(key)
        if isinstance(v, bool):
            params[key.lower()] = v

    # Offset / taper
    for key in ("TaperAngle", "TaperAngle2", "Offset"):
        v = _get_scalar(props, key)
        if v is not None:
            params[key.lower()] = v

    # Fillet / chamfer size
    for key in ("Radius", "Size"):
        v = _get_scalar(props, key)
        if v is not None:
            params[key.lower()] = v

    # Thickness (shell)
    for key in ("Value", "Thickness"):
        v = _get_scalar(props, key)
        if v is not None:
            params["thickness"] = v
            break


def _get_scalar(props: dict, key: str) -> float | None:
    """Extract a scalar value from a property dict entry (handles Quantity dicts)."""
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


def _extract_edge_refs(feat: FCStdObject, params: dict) -> None:
    """
    Capture edge/face references for fillet, chamfer, draft features.

    FreeCAD stores these as ``LinkSubList`` (a list of LinkRef with sub-elements).
    We emit them as opaque FreeCAD edge names in ``freecad_ref.edge_names``
    (they don't drive evaluation — the node is read-only — but document intent).
    """
    base_prop = feat.properties.get("Base")
    if isinstance(base_prop, LinkRef) and base_prop.sub_elements:
        params["freecad_ref"]["edge_names"] = base_prop.sub_elements
        params["freecad_ref"]["rebind_needed"] = True


def _extract_pattern_params(feat: FCStdObject, op: str, params: dict) -> None:
    """Extract direction, count, spacing for LinearPattern / PolarPattern / Mirrored."""
    props = feat.properties
    if op == "linear_pattern":
        for k in ("Occurrences", "Length"):
            v = _get_scalar(props, k)
            if v is not None:
                params[k.lower()] = v
        direction = props.get("Direction")
        if direction is not None:
            params["direction"] = str(direction)
    elif op == "polar_pattern":
        for k in ("Occurrences", "Angle"):
            v = _get_scalar(props, k)
            if v is not None:
                params[k.lower()] = v
        axis = props.get("Axis")
        if axis is not None:
            params["axis"] = str(axis)
    elif op == "mirror_pattern":
        plane = props.get("MirrorPlane")
        if plane is not None:
            params["mirror_plane"] = str(plane)


def _extract_multi_profile_params(
    feat: FCStdObject, doc: FCStdDocument, params: dict
) -> None:
    """Extract profile list for Loft / Pipe features."""
    sections = feat.properties.get("Sections") or feat.properties.get("Profiles")
    if isinstance(sections, list):
        profile_paths = []
        for ref in sections:
            if isinstance(ref, LinkRef):
                obj = doc.object_by_name(ref.target_name)
                name = obj.label if obj else ref.target_name
                profile_paths.append(f"/{name}.sketch")
        if profile_paths:
            params["profiles"] = profile_paths

    spine = feat.properties.get("Spine") or feat.properties.get("Path")
    if isinstance(spine, LinkRef):
        obj = doc.object_by_name(spine.target_name)
        name = obj.label if obj else spine.target_name
        params["spine_path"] = f"/{name}.sketch"
