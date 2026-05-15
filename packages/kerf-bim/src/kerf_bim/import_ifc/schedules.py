"""
schedules.py — IFC quantity sets → .schedule.json payload.

IFC quantity set model
----------------------
IFC encodes element quantities (areas, volumes, lengths, counts) via
IfcElementQuantity, which is related to elements through
IfcRelDefinesByProperties.  Each IfcElementQuantity has a Name
(e.g. "Qto_WallBaseQuantities") and a list of Quantities that are
IfcQuantityLength, IfcQuantityArea, IfcQuantityVolume, IfcQuantityCount,
IfcQuantityWeight, or IfcQuantityTime.

Translation approach
--------------------
For each IfcElementQuantity in the model we produce one .schedule.json that:

  - name         : the quantity set name (e.g. "Qto_WallBaseQuantities")
  - target_category: inferred from the host element's IFC class
  - columns      : one per quantity, with field=quantity_name, label=name+unit
  - filters      : empty (import-time schedules capture the full data set)
  - rows         : one per host element (element name + quantity values)

.schedule.json payload (schema version 1)
-----------------------------------------
{
    "version": 1,
    "name": "Qto_WallBaseQuantities",
    "target_category": "Wall",
    "filters": [],
    "columns": [
        {"field": "name",   "label": "Element"},
        {"field": "Height", "label": "Height (mm)", "format": "decimal"},
        {"field": "Length", "label": "Length (mm)", "format": "decimal"},
        ...
    ],
    "group_by": null,
    "sort_by": "name",
    "rows": [
        {"name": "Wall-01", "Height": 3000.0, "Length": 5000.0},
        ...
    ],
    "ifc_source": "IfcElementQuantity",
}

Caveats
-------
- Multi-element multi-pset IFC files may produce many schedule payloads.
  The caller (parser.py) groups by quantity-set name and merges rows.
- Unit normalisation is not performed: values are taken as-is from IFC
  (should already be in project units, i.e. mm for Kerf).
- IfcPropertySet (non-quantity) is intentionally excluded here; property
  sets are attached to family params via families.py.
"""
from __future__ import annotations

from typing import Any


# Map IFC quantity class → unit label suffix for column headers
_QTY_UNIT_SUFFIX: dict[str, str] = {
    "IfcQuantityLength":  "mm",
    "IfcQuantityArea":    "mm²",
    "IfcQuantityVolume":  "mm³",
    "IfcQuantityCount":   "",
    "IfcQuantityWeight":  "kg",
    "IfcQuantityTime":    "s",
}

# Map IFC quantity class → attribute that holds the numeric value
_QTY_VALUE_ATTR: dict[str, str] = {
    "IfcQuantityLength":  "LengthValue",
    "IfcQuantityArea":    "AreaValue",
    "IfcQuantityVolume":  "VolumeValue",
    "IfcQuantityCount":   "CountValue",
    "IfcQuantityWeight":  "WeightValue",
    "IfcQuantityTime":    "TimeValue",
}

# IFC element class → schedule target_category
_CLASS_TO_CATEGORY: dict[str, str] = {
    "IfcWall":           "Wall",
    "IfcWallStandardCase": "Wall",
    "IfcSlab":           "Slab",
    "IfcSpace":          "Space",
    "IfcDoor":           "Door",
    "IfcWindow":         "Window",
    "IfcColumn":         "Column",
    "IfcBeam":           "Beam",
}


def _category_for_element(ifc_element) -> str:
    ifc_class = getattr(ifc_element, "is_a", lambda: "")()
    return _CLASS_TO_CATEGORY.get(ifc_class, "Element")


def _quantity_value(ifc_qty) -> float | int | None:
    """Extract numeric value from an IFC quantity entity."""
    qty_class = getattr(ifc_qty, "is_a", lambda: "")()
    value_attr = _QTY_VALUE_ATTR.get(qty_class)
    if value_attr is None:
        return None
    raw = getattr(ifc_qty, value_attr, None)
    if raw is None:
        return None
    try:
        if qty_class == "IfcQuantityCount":
            return int(raw)
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_quantity_schedules(
    ifc_file,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """
    Walk all IfcRelDefinesByProperties relationships and collect
    IfcElementQuantity sets.

    Returns a list of .schedule.json payload dicts, one per unique
    quantity-set name.  Multiple elements contributing to the same
    quantity-set name have their rows merged.

    Args:
        ifc_file:  An open ifcopenshell file object.
        warnings:  Mutable list; non-fatal issues appended here.
    """
    # Accumulator: qset_name → {columns, category, rows}
    qset_accumulator: dict[str, dict[str, Any]] = {}

    try:
        rels = ifc_file.by_type("IfcRelDefinesByProperties")
    except Exception as exc:
        warnings.append(f"IfcRelDefinesByProperties query failed: {exc}")
        return []

    for rel in rels:
        try:
            _process_rel(rel, qset_accumulator, warnings)
        except Exception as exc:
            rel_gid = getattr(rel, "GlobalId", "?")
            warnings.append(f"quantity-set relation {rel_gid!r}: processing failed ({exc}); skipped")

    # Convert accumulator to list of schedule payloads
    schedules: list[dict[str, Any]] = []
    for qset_name, acc in qset_accumulator.items():
        col_fields = list(acc["column_order"])
        columns = [{"field": "name", "label": "Element"}]
        for field in col_fields:
            col_info = acc["columns"][field]
            label = col_info["label"]
            columns.append({
                "field": field,
                "label": label,
                "format": col_info["format"],
            })

        schedules.append({
            "version": 1,
            "name": qset_name,
            "target_category": acc["category"],
            "filters": [],
            "columns": columns,
            "group_by": None,
            "sort_by": "name",
            "rows": acc["rows"],
            "ifc_source": "IfcElementQuantity",
        })

    return schedules


def _process_rel(rel, accumulator: dict[str, Any], warnings: list[str]) -> None:
    """Process one IfcRelDefinesByProperties relation."""
    pdef = getattr(rel, "RelatingPropertyDefinition", None)
    if pdef is None:
        return

    pdef_type = getattr(pdef, "is_a", lambda: "")()
    if "ElementQuantity" not in pdef_type:
        return  # Only process quantity sets here

    qset_name = str(getattr(pdef, "Name", None) or "UnnamedQuantitySet")
    quantities = getattr(pdef, "Quantities", None) or []
    if not quantities:
        return

    related_objects = getattr(rel, "RelatedObjects", None) or []

    # Ensure the accumulator entry exists
    if qset_name not in accumulator:
        accumulator[qset_name] = {
            "category": "Element",
            "columns": {},     # field_name → {label, format}
            "column_order": [], # preserves insertion order
            "rows": [],
        }

    entry = accumulator[qset_name]

    # Register columns from this quantity set
    for qty in quantities:
        qty_class = getattr(qty, "is_a", lambda: "")()
        qty_name = str(getattr(qty, "Name", None) or "")
        if not qty_name:
            continue

        if qty_name not in entry["columns"]:
            unit_suffix = _QTY_UNIT_SUFFIX.get(qty_class, "")
            label = f"{qty_name} ({unit_suffix})" if unit_suffix else qty_name
            fmt = "decimal" if qty_class not in ("IfcQuantityCount",) else "integer"
            entry["columns"][qty_name] = {"label": label, "format": fmt}
            entry["column_order"].append(qty_name)

    # Add rows for each related element
    for elem in related_objects:
        try:
            category = _category_for_element(elem)
            # Update the schedule category from the first concrete element
            if entry["category"] == "Element":
                entry["category"] = category

            elem_name = str(getattr(elem, "Name", None) or getattr(elem, "GlobalId", "?"))
            row: dict[str, Any] = {"name": elem_name}

            for qty in quantities:
                qty_name = str(getattr(qty, "Name", None) or "")
                if not qty_name:
                    continue
                value = _quantity_value(qty)
                row[qty_name] = value

            entry["rows"].append(row)
        except Exception as exc:
            elem_gid = getattr(elem, "GlobalId", "?")
            warnings.append(f"quantity schedule {qset_name!r}: element {elem_gid!r} row failed ({exc}); skipped")
