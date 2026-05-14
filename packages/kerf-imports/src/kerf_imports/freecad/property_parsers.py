"""
property_parsers.py — FreeCAD typed XML property converters.

Dispatch table mapping ``App::Property*`` type strings to converter
functions that turn the inner XML element into a Python-native value.

Every converter receives the *inner* XML element (the child of
``<Property name="..." type="...">``) and the zip archive (for
``FileIncluded`` blob extraction).

Unmapped types are marked as ``_UNKNOWN_<type>`` with the raw element
text preserved so downstream tasks can flag them without crashing.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from .types import LinkRef


# ---------------------------------------------------------------------------
# Primitive converters
# ---------------------------------------------------------------------------

def _parse_float(elem: ET.Element, _zf: zipfile.ZipFile | None) -> float | None:
    v = elem.get("value")
    return float(v) if v is not None else None


def _parse_int(elem: ET.Element, _zf: zipfile.ZipFile | None) -> int | None:
    v = elem.get("value")
    return int(v) if v is not None else None


def _parse_bool(elem: ET.Element, _zf: zipfile.ZipFile | None) -> bool | None:
    v = elem.get("value")
    if v is None:
        return None
    return v.strip().lower() in ("1", "true")


def _parse_string(elem: ET.Element, _zf: zipfile.ZipFile | None) -> str | None:
    v = elem.get("v") or elem.get("value") or elem.text
    return v


def _parse_unicode_string(elem: ET.Element, _zf: zipfile.ZipFile | None) -> str | None:
    # FreeCAD uses <String value="..."/> or <String v="..."/>
    return _parse_string(elem, _zf)


# ---------------------------------------------------------------------------
# Geometric types
# ---------------------------------------------------------------------------

def _parse_vector(elem: ET.Element, _zf: zipfile.ZipFile | None) -> dict[str, float]:
    """
    ``<Vector x="..." y="..." z="..."/>``
    → ``{"x": float, "y": float, "z": float}``
    """
    return {
        "x": float(elem.get("x", 0)),
        "y": float(elem.get("y", 0)),
        "z": float(elem.get("z", 0)),
    }


def _parse_placement(elem: ET.Element, _zf: zipfile.ZipFile | None) -> dict[str, Any]:
    """
    ``<Placement ... />`` has ``Px``, ``Py``, ``Pz`` (position) and either
    quaternion ``Q0``–``Q3`` or axis+angle ``Ax``/``Ay``/``Az``/``A``.
    Returns a dict with both representations as available.
    """
    result: dict[str, Any] = {}
    # Position
    for k in ("Px", "Py", "Pz"):
        if elem.get(k) is not None:
            result[k] = float(elem.get(k))  # type: ignore[arg-type]
    # Quaternion
    for k in ("Q0", "Q1", "Q2", "Q3"):
        if elem.get(k) is not None:
            result[k] = float(elem.get(k))  # type: ignore[arg-type]
    # Axis + angle (older FreeCAD versions or alternative representation)
    for k in ("Ax", "Ay", "Az", "A"):
        if elem.get(k) is not None:
            result[k] = float(elem.get(k))  # type: ignore[arg-type]
    return result


def _parse_matrix(elem: ET.Element, _zf: zipfile.ZipFile | None) -> dict[str, float]:
    """
    ``<Matrix A11="..." A12="..." ... A44="..."/>`` → flat dict of all Aij
    """
    result: dict[str, float] = {}
    for i in range(1, 5):
        for j in range(1, 5):
            k = f"A{i}{j}"
            if elem.get(k) is not None:
                result[k] = float(elem.get(k))  # type: ignore[arg-type]
    return result


# ---------------------------------------------------------------------------
# List types
# ---------------------------------------------------------------------------

def _parse_float_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[float]:
    """
    Two formats seen in the wild:
      <FloatList count="3">1.0 2.0 3.0</FloatList>
      <FloatList count="3"><Float value="1.0"/><Float value="2.0"/>...</FloatList>
    """
    children = list(elem)
    if children:
        return [float(c.get("value", 0)) for c in children]
    text = (elem.text or "").strip()
    if text:
        return [float(x) for x in text.split()]
    return []


def _parse_int_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[int]:
    children = list(elem)
    if children:
        return [int(c.get("value", 0)) for c in children]
    text = (elem.text or "").strip()
    if text:
        return [int(x) for x in text.split()]
    return []


def _parse_string_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[str]:
    """``<StringList count="N"><String value="..."/>...</StringList>``"""
    result = []
    for child in elem:
        v = child.get("v") or child.get("value") or child.text or ""
        result.append(v)
    return result


def _parse_vector_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[dict[str, float]]:
    return [_parse_vector(c, _zf) for c in elem if c.tag in ("Vector", "v")]


# ---------------------------------------------------------------------------
# Link types
# ---------------------------------------------------------------------------

def _parse_link(elem: ET.Element, _zf: zipfile.ZipFile | None) -> LinkRef | None:
    """
    ``<Link value="ObjectName"/>``
    → ``LinkRef("ObjectName")``
    """
    v = elem.get("value")
    return LinkRef(v) if v else None


def _parse_link_sub(elem: ET.Element, _zf: zipfile.ZipFile | None) -> LinkRef | None:
    """
    ``<LinkSub value="ObjectName"><Sub value="Edge1"/><Sub value="Face2"/>``
    or older format: ``<LinkSub value="ObjectName" sub="Edge1"/>``
    """
    target = elem.get("value")
    if not target:
        return None
    subs: list[str] = []
    # New format: child <Sub> elements
    for child in elem:
        if child.tag in ("Sub", "sub"):
            s = child.get("v") or child.get("value") or child.text or ""
            if s:
                subs.append(s)
    # Old format: single "sub" attribute
    if not subs:
        s = elem.get("sub")
        if s:
            subs = [s]
    return LinkRef(target, subs)


def _parse_link_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[LinkRef]:
    """
    ``<LinkList count="N"><Link value="Name1"/>...</LinkList>``
    """
    result = []
    for child in elem:
        ref = _parse_link(child, _zf)
        if ref is not None:
            result.append(ref)
    return result


def _parse_link_sub_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[LinkRef]:
    result = []
    for child in elem:
        ref = _parse_link_sub(child, _zf)
        if ref is not None:
            result.append(ref)
    return result


# ---------------------------------------------------------------------------
# File / blob types
# ---------------------------------------------------------------------------

def _parse_file_included(
    elem: ET.Element, zf: zipfile.ZipFile | None
) -> bytes | str:
    """
    ``<FileIncluded file="PartShape1.brp"/>``

    If the zip archive is supplied, return the raw bytes of the referenced
    member.  Otherwise return the filename string (for tests that build an
    archive separately).
    """
    fname = elem.get("file") or elem.get("v") or ""
    if not fname:
        return b""
    if zf is not None:
        try:
            return zf.read(fname)
        except KeyError:
            return fname  # member not found — return the name as a fallback
    return fname  # no zip supplied


# ---------------------------------------------------------------------------
# Complex sub-object types
# ---------------------------------------------------------------------------

def _parse_geometry_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[dict]:
    """
    ``<GeometryList count="N"><Geometry type="...">...</Geometry>...</GeometryList>``

    Returns a list of dicts with at minimum ``{"type": str}``.
    Additional child tags (Start, End, Center, etc.) are captured as nested
    dicts keyed by tag name.
    """
    result = []
    for geom in elem.iter("Geometry"):
        entry: dict[str, Any] = {"type": geom.get("type", "")}
        for child in geom:
            entry[child.tag] = dict(child.attrib)
        result.append(entry)
    return result


def _parse_constraint_list(elem: ET.Element, _zf: zipfile.ZipFile | None) -> list[dict]:
    """
    ``<ConstraintList count="N"><Constrain Name="..." Type="..." .../>...</ConstraintList>``

    Returns a list of dicts from all ``<Constrain>`` element attributes.
    Numeric ``Type`` is coerced to ``int``.
    """
    result = []
    for c in elem:
        if c.tag != "Constrain":
            continue
        entry = dict(c.attrib)
        if "Type" in entry:
            try:
                entry["Type"] = int(entry["Type"])
            except ValueError:
                pass
        for k in ("First", "Second", "Third", "FirstPos", "SecondPos", "ThirdPos"):
            if k in entry:
                try:
                    entry[k] = int(entry[k])
                except ValueError:
                    pass
        if "Value" in entry:
            try:
                entry["Value"] = float(entry["Value"])
            except ValueError:
                pass
        result.append(entry)
    return result


def _parse_quantity(elem: ET.Element, _zf: zipfile.ZipFile | None) -> dict[str, Any]:
    """
    ``<Quantity v="10" unit="mm"/>``
    → ``{"value": 10.0, "unit": "mm"}``
    """
    v = elem.get("v") or elem.get("value")
    return {
        "value": float(v) if v is not None else None,
        "unit": elem.get("unit") or elem.get("u", ""),
    }


def _parse_angle(elem: ET.Element, zf: zipfile.ZipFile | None) -> dict[str, Any]:
    return _parse_quantity(elem, zf)


def _parse_path(elem: ET.Element, _zf: zipfile.ZipFile | None) -> str:
    return elem.get("v") or elem.get("value") or elem.text or ""


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
# Maps the ``type="App::Property*"`` string (full or suffix) to a converter.
# Both full names and the bare suffix after ``::`` are registered so the
# lookup works whether the parser finds the full type string or just the
# suffix.

_CONVERTERS: dict[str, Any] = {
    # --- primitives ---
    "App::PropertyFloat": _parse_float,
    "PropertyFloat": _parse_float,
    "Float": _parse_float,

    "App::PropertyInteger": _parse_int,
    "PropertyInteger": _parse_int,
    "Integer": _parse_int,

    "App::PropertyBool": _parse_bool,
    "PropertyBool": _parse_bool,
    "Bool": _parse_bool,

    "App::PropertyString": _parse_string,
    "PropertyString": _parse_string,
    "String": _parse_string,

    "App::PropertyUnicodeString": _parse_unicode_string,
    "PropertyUnicodeString": _parse_unicode_string,
    "UnicodeString": _parse_unicode_string,

    "App::PropertyEnumeration": _parse_string,
    "PropertyEnumeration": _parse_string,
    "Enumeration": _parse_string,

    # --- geometry ---
    "App::PropertyVector": _parse_vector,
    "PropertyVector": _parse_vector,
    "Vector": _parse_vector,

    "App::PropertyVectorList": _parse_vector_list,
    "PropertyVectorList": _parse_vector_list,
    "VectorList": _parse_vector_list,

    "App::PropertyPlacement": _parse_placement,
    "PropertyPlacement": _parse_placement,
    "Placement": _parse_placement,

    "App::PropertyMatrix": _parse_matrix,
    "PropertyMatrix": _parse_matrix,
    "Matrix": _parse_matrix,

    # --- numeric lists ---
    "App::PropertyFloatList": _parse_float_list,
    "PropertyFloatList": _parse_float_list,
    "FloatList": _parse_float_list,

    "App::PropertyIntegerList": _parse_int_list,
    "PropertyIntegerList": _parse_int_list,
    "IntegerList": _parse_int_list,

    # --- string lists ---
    "App::PropertyStringList": _parse_string_list,
    "PropertyStringList": _parse_string_list,
    "StringList": _parse_string_list,

    # --- links ---
    "App::PropertyLink": _parse_link,
    "PropertyLink": _parse_link,
    "Link": _parse_link,

    "App::PropertyLinkSub": _parse_link_sub,
    "PropertyLinkSub": _parse_link_sub,
    "LinkSub": _parse_link_sub,

    "App::PropertyLinkList": _parse_link_list,
    "PropertyLinkList": _parse_link_list,
    "LinkList": _parse_link_list,

    "App::PropertyLinkSubList": _parse_link_sub_list,
    "PropertyLinkSubList": _parse_link_sub_list,
    "LinkSubList": _parse_link_sub_list,

    # --- files / blobs ---
    "App::PropertyFileIncluded": _parse_file_included,
    "PropertyFileIncluded": _parse_file_included,
    "FileIncluded": _parse_file_included,

    # --- FreeCAD sketch-specific ---
    "Sketcher::PropertyConstraintList": _parse_constraint_list,
    "PropertyConstraintList": _parse_constraint_list,
    "ConstraintList": _parse_constraint_list,

    "Part::PropertyGeometryList": _parse_geometry_list,
    "PropertyGeometryList": _parse_geometry_list,
    "GeometryList": _parse_geometry_list,

    # --- quantities ---
    "App::PropertyQuantity": _parse_quantity,
    "PropertyQuantity": _parse_quantity,
    "Quantity": _parse_quantity,

    "App::PropertyAngle": _parse_angle,
    "PropertyAngle": _parse_angle,
    "Angle": _parse_angle,

    "App::PropertyLength": _parse_quantity,
    "PropertyLength": _parse_quantity,
    "Length": _parse_quantity,

    # --- paths ---
    "App::PropertyPath": _parse_path,
    "PropertyPath": _parse_path,
    "Path": _parse_path,
}


def parse_property(
    type_str: str,
    inner_elem: ET.Element,
    zf: zipfile.ZipFile | None = None,
) -> Any:
    """
    Convert a single FreeCAD property to a Python-native value.

    Parameters
    ----------
    type_str :
        The ``type="..."`` attribute from ``<Property>``,
        e.g. ``"App::PropertyFloat"``.
    inner_elem :
        The first child element of ``<Property>`` (the actual value holder).
    zf :
        Open ``zipfile.ZipFile`` for blob extraction (may be ``None``).

    Returns
    -------
    Any
        A Python-native value, or a string ``"_UNKNOWN_<type>"`` if the
        type is not in the dispatch table.
    """
    converter = _CONVERTERS.get(type_str)

    # Also try the bare suffix after "::"
    if converter is None and "::" in type_str:
        suffix = type_str.split("::")[-1]
        converter = _CONVERTERS.get(suffix)

    if converter is not None:
        try:
            return converter(inner_elem, zf)
        except Exception:
            # Parsing failed; return sentinel rather than crash
            return f"_UNKNOWN_{type_str}"

    return f"_UNKNOWN_{type_str}"


def supported_types() -> list[str]:
    """Return the sorted list of fully-qualified type strings we handle."""
    return sorted(
        {k for k in _CONVERTERS if k.startswith("App::") or k.startswith("Sketcher::") or k.startswith("Part::")}
    )
