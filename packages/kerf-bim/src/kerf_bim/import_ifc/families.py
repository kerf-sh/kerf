"""
families.py — IFC type objects → .family.json payload.

IFC type model
--------------
IFC uses "type objects" (IfcTypeObject and its subtypes) to express reusable
parametric templates — the direct equivalent of Revit families.  Key concrete
subtypes:

  IfcWindowType   (IFC4)  / IfcWindowStyle  (IFC2x3)
  IfcDoorType     (IFC4)  / IfcDoorStyle    (IFC2x3)
  IfcWallType
  IfcSlabType
  IfcColumnType
  IfcBeamType
  IfcFlowTerminalType  (MEP equipment types)
  IfcFlowSegmentType
  ...and ~80 more concrete type subtypes

Type objects carry:
  - Name / Description
  - HasPropertySets → IfcPropertySet → HasProperties → IfcPropertySingleValue
  - ElementType (predefined type label, e.g. "SINGLE_PANEL" for windows)

Each type object may also have HasTypes → IfcRelDefinesByType → RelatedObjects
giving the instances.

.family.json payload (schema version 1)
-----------------------------------------
{
    "version": 1,
    "name": "Single Panel Window",
    "category": "Window",           # normalised from ifc_class
    "params": [                     # from IfcPropertySet properties
        {"name": "width",  "type": "number", "unit": "mm", "default": 900},
        ...
    ],
    "types": [],                    # no nested types extracted at this tier
    "host_rules": {},               # not populated from IFC at Tier 2
    "representation": {},           # geometry ref not resolved at Tier 2
    "ifc_guid": "...",              # GlobalId for round-trip
    "ifc_class": "IfcWindowType",   # raw IFC class
}

Property extraction
-------------------
We walk HasPropertySets → IfcPropertySet.HasProperties and extract
IfcPropertySingleValue entries.  Values can be IfcLengthMeasure,
IfcPositiveLengthMeasure, IfcReal, IfcLabel, IfcBoolean, IfcInteger.

Unknown or complex value types are stringified and emitted as "string" params
with a comment warning appended to the warnings list.
"""
from __future__ import annotations

from typing import Any


# Map IFC type class name fragments → .family.json category string
_CLASS_TO_CATEGORY: dict[str, str] = {
    "Window":          "Window",
    "Door":            "Door",
    "Wall":            "Wall",
    "Slab":            "Floor",
    "Roof":            "Roof",
    "Column":          "Column",
    "Beam":            "Beam",
    "Stair":           "Stair",
    "Railing":         "Railing",
    "Ceiling":         "Ceiling",
    "Curtain":         "CurtainWall",
    "Furniture":       "Furniture",
    "FlowTerminal":    "MEP",
    "FlowSegment":     "MEP",
    "FlowFitting":     "MEP",
    "EnergyConversion":"MEP",
    "FlowMoving":      "MEP",
}

# IFC value type → param type mapping
_VALUE_TYPE_MAP: dict[str, str] = {
    "IfcLengthMeasure":         "number",
    "IfcPositiveLengthMeasure": "number",
    "IfcReal":                  "number",
    "IfcRatioMeasure":          "number",
    "IfcInteger":               "number",
    "IfcCountMeasure":          "number",
    "IfcLabel":                 "string",
    "IfcText":                  "string",
    "IfcIdentifier":            "string",
    "IfcBoolean":               "boolean",
    "IfcLogical":               "boolean",
}

# IFC value types carrying millimetre measures (so we emit unit="mm")
_MM_VALUE_TYPES = frozenset({
    "IfcLengthMeasure",
    "IfcPositiveLengthMeasure",
})


def _category_from_ifc_class(ifc_class: str) -> str:
    """Normalise IFC type class name to .family.json category string."""
    for fragment, category in _CLASS_TO_CATEGORY.items():
        if fragment in ifc_class:
            return category
    return "Generic"


def _extract_params_from_psets(
    ifc_type,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """
    Walk HasPropertySets → IfcPropertySet → HasProperties and extract
    IfcPropertySingleValue entries as param dicts.
    """
    params: list[dict[str, Any]] = []
    gid = getattr(ifc_type, "GlobalId", "?")

    try:
        psets = getattr(ifc_type, "HasPropertySets", None) or []
        for pset in psets:
            pset_type = getattr(pset, "is_a", lambda: "")()
            if "PropertySet" not in pset_type:
                continue
            properties = getattr(pset, "HasProperties", None) or []
            for prop in properties:
                prop_type = getattr(prop, "is_a", lambda: "")()
                if "SingleValue" not in prop_type:
                    continue
                try:
                    param = _extract_single_value_param(prop, warnings, gid)
                    if param:
                        params.append(param)
                except Exception as exc:
                    prop_name = getattr(prop, "Name", "?")
                    warnings.append(
                        f"type {gid!r}: property {prop_name!r} extraction failed ({exc}); skipped"
                    )
    except Exception as exc:
        warnings.append(f"type {gid!r}: property set extraction failed ({exc})")

    return params


def _extract_single_value_param(
    ifc_prop,
    warnings: list[str],
    parent_gid: str,
) -> dict[str, Any] | None:
    """Convert one IfcPropertySingleValue into a param dict."""
    prop_name = str(getattr(ifc_prop, "Name", None) or "")
    if not prop_name:
        return None

    nominal_value = getattr(ifc_prop, "NominalValue", None)
    if nominal_value is None:
        # param with no value — emit as string with None default
        return {"name": prop_name, "type": "string", "default": None}

    value_type = getattr(nominal_value, "is_a", lambda: "")()
    param_type = _VALUE_TYPE_MAP.get(value_type, "string")

    raw_value = getattr(nominal_value, "wrappedValue", None)

    param: dict[str, Any] = {"name": prop_name, "type": param_type}

    if param_type == "number" and raw_value is not None:
        try:
            param["default"] = float(raw_value)
        except (TypeError, ValueError):
            param["default"] = None
        if value_type in _MM_VALUE_TYPES:
            param["unit"] = "mm"
    elif param_type == "boolean":
        if raw_value is not None:
            param["default"] = bool(raw_value)
    else:
        # string (or unknown value type — stringified with warning)
        if value_type and value_type not in _VALUE_TYPE_MAP:
            warnings.append(
                f"type {parent_gid!r}: property {prop_name!r} has unknown value type "
                f"{value_type!r}; emitted as string"
            )
        if raw_value is not None:
            param["default"] = str(raw_value)

    return param


def translate_type_object(
    ifc_type,
    warnings: list[str],
) -> dict[str, Any]:
    """
    Translate one IFC type object into a .family.json payload dict.

    Args:
        ifc_type:   The IFC type entity (IfcWindowType, IfcDoorType, etc.).
        warnings:   Mutable list; non-fatal issues appended here.

    Returns:
        A dict matching the .family.json schema, or {} on hard failure.
    """
    ifc_class = getattr(ifc_type, "is_a", lambda: "")()
    if not ifc_class:
        return {}

    gid = getattr(ifc_type, "GlobalId", "")
    name = str(getattr(ifc_type, "Name", None) or gid)
    description = str(getattr(ifc_type, "Description", None) or "")
    category = _category_from_ifc_class(ifc_class)

    params = _extract_params_from_psets(ifc_type, warnings)

    return {
        "version": 1,
        "name": name,
        "description": description,
        "category": category,
        "params": params,
        "types": [],
        "host_rules": {},
        "representation": {},
        "ifc_guid": gid,
        "ifc_class": ifc_class,
    }


# IFC type-object entity classes to query.
# We query the abstract IfcTypeObject first (catches everything in one pass if
# the IFC file uses the abstract form), then fall back to concrete subtype
# queries for files that register types under concrete classes only.
TYPE_OBJECT_QUERY_TYPES = (
    "IfcTypeObject",
    "IfcWindowType",
    "IfcWindowStyle",
    "IfcDoorType",
    "IfcDoorStyle",
    "IfcWallType",
    "IfcSlabType",
    "IfcColumnType",
    "IfcBeamType",
    "IfcFlowTerminalType",
    "IfcFlowSegmentType",
    "IfcFlowFittingType",
)
