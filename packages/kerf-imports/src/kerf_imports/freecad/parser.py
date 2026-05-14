"""
parser.py — parse_fcstd: the main entry point for T1.

Pure Python, stdlib only.  No FreeCAD or Coin3D install required.

Usage::

    from kerf_imports.freecad.parser import parse_fcstd

    doc = parse_fcstd("/path/to/file.FCStd")
    doc = parse_fcstd(Path("/path/to/file.FCStd"))
    doc = parse_fcstd(raw_bytes)         # bytes from an upload etc.

Returns an :class:`~kerf_imports.freecad.types.FCStdDocument`.
Raises :class:`~kerf_imports.freecad.types.FCStdUnsupportedVersionError`
for ``SchemaVersion < 4``.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

from .types import (
    FCStdDocument,
    FCStdObject,
    FCStdParseError,
    FCStdUnsupportedVersionError,
)
from .property_parsers import parse_property

# Minimum supported SchemaVersion (FreeCAD 0.19+)
_MIN_SCHEMA_VERSION = 4

PathOrBytes = Union[str, Path, bytes, bytearray]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_fcstd(source: PathOrBytes) -> FCStdDocument:
    """
    Parse a ``.FCStd`` file and return an in-memory :class:`FCStdDocument`.

    Parameters
    ----------
    source :
        A file-system path (``str`` or ``pathlib.Path``) or raw bytes
        (e.g. from an HTTP upload or ``open(..., "rb").read()``).

    Returns
    -------
    FCStdDocument

    Raises
    ------
    FCStdUnsupportedVersionError
        If ``Document.xml`` contains ``SchemaVersion < 4``.
    FCStdParseError
        If the archive is malformed or ``Document.xml`` is missing.
    """
    if isinstance(source, (bytes, bytearray)):
        zf_source: Union[str, io.BytesIO] = io.BytesIO(source)
    else:
        zf_source = str(source)

    try:
        with zipfile.ZipFile(zf_source, "r") as zf:
            return _parse_zip(zf)
    except zipfile.BadZipFile as exc:
        raise FCStdParseError(f"Not a valid .FCStd archive: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_zip(zf: zipfile.ZipFile) -> FCStdDocument:
    names = set(zf.namelist())

    # ------------------------------------------------------------------
    # 1. Collect raw XML members and BRep blobs
    # ------------------------------------------------------------------
    raw_xml: dict[str, bytes] = {}
    brep_blobs: dict[str, bytes] = {}

    for name in names:
        if name.endswith(".xml"):
            raw_xml[name] = zf.read(name)
        elif name.endswith(".brp") or name.endswith(".brep"):
            brep_blobs[name] = zf.read(name)

    # ------------------------------------------------------------------
    # 2. Parse Document.xml
    # ------------------------------------------------------------------
    if "Document.xml" not in names:
        raise FCStdParseError("Document.xml not found in .FCStd archive")

    doc_bytes = raw_xml.get("Document.xml") or zf.read("Document.xml")
    try:
        root = ET.fromstring(doc_bytes)
    except ET.ParseError as exc:
        raise FCStdParseError(f"Document.xml is not valid XML: {exc}") from exc

    # ------------------------------------------------------------------
    # 3. Schema version gate
    # ------------------------------------------------------------------
    schema_version_str = root.get("SchemaVersion", "0")
    try:
        schema_version = int(schema_version_str)
    except ValueError:
        raise FCStdParseError(
            f"SchemaVersion '{schema_version_str}' is not an integer"
        )
    if schema_version < _MIN_SCHEMA_VERSION:
        raise FCStdUnsupportedVersionError(schema_version)

    program_version = root.get("ProgramVersion", "")

    # ------------------------------------------------------------------
    # 4. Build object type map from <Objects> block
    # ------------------------------------------------------------------
    # <Objects Count="N">
    #   <Object type="PartDesign::Body" name="Body" label="Body" .../>
    #   ...
    # </Objects>
    obj_meta: dict[str, dict[str, str]] = {}  # name → {type, label}
    objects_elem = root.find("Objects")
    if objects_elem is not None:
        for obj_elem in objects_elem:
            name = obj_elem.get("name", "")
            type_ = obj_elem.get("type", "")
            label = obj_elem.get("label") or obj_elem.get("Label") or name
            if name:
                obj_meta[name] = {"type": type_, "label": label}

    # ------------------------------------------------------------------
    # 5. Parse <ObjectData> block
    # ------------------------------------------------------------------
    objects: list[FCStdObject] = []
    obj_data_elem = root.find("ObjectData")
    if obj_data_elem is not None:
        for obj_elem in obj_data_elem:
            obj_name = obj_elem.get("name", "")
            meta = obj_meta.get(obj_name, {})
            obj = FCStdObject(
                name=obj_name,
                type=meta.get("type", ""),
                label=meta.get("label", obj_name),
                properties=_parse_properties(obj_elem, zf),
            )
            objects.append(obj)

    # ------------------------------------------------------------------
    # 6. Parse global document-level properties (rare but preserve them)
    # ------------------------------------------------------------------
    global_props: dict[str, dict] = {}
    for props_elem in root.findall("Properties"):
        parsed = _parse_properties(props_elem, zf)
        global_props.update(parsed)

    return FCStdDocument(
        schema_version=schema_version,
        program_version=program_version,
        objects=objects,
        properties=global_props,
        brep_blobs=brep_blobs,
        raw_xml=raw_xml,
    )


def _parse_properties(
    parent: ET.Element, zf: zipfile.ZipFile
) -> dict[str, object]:
    """
    Parse the ``<Properties>`` block inside an ``<Object>`` element
    (or directly on a parent element).

    Returns a dict of ``{property_name: typed_value}``.
    """
    props: dict[str, object] = {}

    # The properties block may be a direct child named "Properties"
    # or the parent itself may be the properties container.
    props_container = parent.find("Properties")
    if props_container is None:
        # Parent is the container itself (global doc props path)
        props_container = parent

    for prop_elem in props_container:
        if prop_elem.tag != "Property":
            continue
        prop_name = prop_elem.get("name", "")
        type_str = prop_elem.get("type", "")
        if not prop_name:
            continue

        # The value is in the first child element of <Property>
        children = list(prop_elem)
        if not children:
            props[prop_name] = None
            continue

        inner = children[0]
        value = parse_property(type_str, inner, zf)
        props[prop_name] = value

    return props
