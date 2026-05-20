"""
geom/io/threemf.py
==================
Pure-Python 3MF read/write for sealed-manifold triangle meshes (GK-78).

3MF Specification Summary
--------------------------
A .3mf file is a ZIP archive containing at minimum:

* ``[Content_Types].xml``   — IANA content-type manifest
* ``_rels/.rels``           — Open Packaging Conventions root relationship
* ``3D/3dmodel.model``      — the primary model XML document
* ``Thumbnail/thumbnail.png`` (optional) — preview image (any PNG bytes)

The model XML uses namespace ``http://schemas.microsoft.com/3dmanufacturing/core/2015/02``
(abbreviated to the ``p:`` prefix in this module).  Material and colour
information lives in a second namespace for the materials extension:
``http://schemas.microsoft.com/3dmanufacturing/material/2015/02``.

Data model accepted / returned
--------------------------------
``verts``   — list of [x, y, z] in mm (float)
``faces``   — list of [i, j, k] 0-based vertex indices
``materials`` — optional list of dicts, each with at minimum ``"name"`` and
               one of ``"r","g","b"`` (0-255 int) or ``"color"`` ("#rrggbb")
``colors``  — optional list of ``"#rrggbbaa"`` / ``"#rrggbb"`` strings,
               indexed by face index
``face_material_ids`` — optional list of int, len == len(faces), 0-based index
               into materials list; ``-1`` / None means unassigned

Public API
----------
``read_threemf(path) -> dict``
    Load a .3mf file.  Returns a dict with keys:
    ``verts``, ``faces``, ``materials``, ``face_material_ids``,
    ``thumbnail_png`` (bytes or None), ``metadata`` (dict str→str).

``write_threemf(path, mesh_or_body, materials=None, colours=None, thumbnail_png=None)``
    Write a .3mf file.  *mesh_or_body* may be:
      - a dict with ``"verts"`` and ``"faces"``
      - any object with ``.verts`` / ``.vertices`` and ``.faces`` attributes

Exceptions
----------
``ThreeMFReadError``   — fatal parse errors
``ThreeMFWriteError``  — fatal serialisation errors

References
----------
* 3MF Core Specification 1.3 (https://github.com/3MFConsortium/spec_core)
* 3MF Materials and Properties Extension 1.2.1
* Open Packaging Conventions (ECMA-376 Part 2)
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

_NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_NS_MAT = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

_CT_MODEL = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
_CT_REL = "application/vnd.openxmlformats-package.relationships+xml"
_CT_PNG = "image/png"
_CT_OPC_TYPES = "application/vnd.openxmlformats-package.content-types+xml"

_REL_TYPE_3DMODEL = (
    "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
)
_REL_TYPE_THUMBNAIL = (
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ThreeMFReadError(Exception):
    """Raised when the 3MF parser encounters a fatal error."""


class ThreeMFWriteError(Exception):
    """Raised when the 3MF serialiser encounters a fatal error."""


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def _parse_color(css: str) -> Tuple[int, int, int, int]:
    """Parse ``#rrggbb`` or ``#rrggbbaa`` → (r, g, b, a) each 0-255."""
    css = css.strip().lstrip("#")
    if len(css) == 6:
        r = int(css[0:2], 16)
        g = int(css[2:4], 16)
        b = int(css[4:6], 16)
        return r, g, b, 255
    if len(css) == 8:
        r = int(css[0:2], 16)
        g = int(css[2:4], 16)
        b = int(css[4:6], 16)
        a = int(css[6:8], 16)
        return r, g, b, a
    raise ValueError(f"Cannot parse colour string: #{css!r}")


def _color_to_css(r: int, g: int, b: int, a: int = 255) -> str:
    if a == 255:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"#{r:02x}{g:02x}{b:02x}{a:02x}"


def _mat_to_css(mat: dict) -> str:
    """Convert a material dict to a CSS colour string."""
    if "color" in mat:
        return mat["color"]
    r = int(mat.get("r", 128))
    g = int(mat.get("g", 128))
    b = int(mat.get("b", 128))
    a = int(mat.get("a", 255))
    return _color_to_css(r, g, b, a)


# ---------------------------------------------------------------------------
# Minimal PNG helper — write a 1×1 transparent PNG from raw bytes
# ---------------------------------------------------------------------------

def _png_signature() -> bytes:
    return b"\x89PNG\r\n\x1a\n"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    import zlib
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def _make_trivial_png() -> bytes:
    """Return a minimal valid 1×1 white PNG as a bytes object."""
    import zlib
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1×1 RGB
    # Raw image: filter byte 0x00, then R G B
    raw = b"\x00\xff\xff\xff"
    idat = zlib.compress(raw)
    return (
        _png_signature()
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# XML building helpers
# ---------------------------------------------------------------------------

def _qn(local: str, ns: str = _NS_CORE) -> str:
    """Return Clark-notation qualified name."""
    return f"{{{ns}}}{local}"


def _build_model_xml(
    verts: List[List[float]],
    faces: List[List[int]],
    materials: Optional[List[dict]],
    colours: Optional[List[str]],
    face_material_ids: Optional[List[int]],
    metadata: Optional[Dict[str, str]] = None,
) -> bytes:
    """Serialise mesh + optional materials/colours to 3dmodel.model XML bytes."""

    # Register namespaces so ET uses clean prefixes.
    # Do NOT also add xmlns:m as a manual attribute — ET.write adds it
    # automatically when the namespace is first used, and a duplicate
    # attribute is an XML error.
    ET.register_namespace("", _NS_CORE)
    ET.register_namespace("m", _NS_MAT)

    root = ET.Element(
        _qn("model"),
        {
            "unit": "millimeter",
            "xml:lang": "en-US",
        },
    )

    # --- metadata ---
    if metadata:
        for k, v in metadata.items():
            meta_el = ET.SubElement(root, _qn("metadata"), {"name": k})
            meta_el.text = str(v)

    # --- resources ---
    resources = ET.SubElement(root, _qn("resources"))

    mat_resource_id: Optional[int] = None
    col_group_id: Optional[int] = None

    resource_id_counter = [1]  # mutable in closure

    def next_id() -> int:
        rid = resource_id_counter[0]
        resource_id_counter[0] += 1
        return rid

    # materials extension: basematerials group
    if materials:
        mat_resource_id = next_id()
        base_mat_el = ET.SubElement(
            resources,
            _qn("basematerials", _NS_CORE),
            {"id": str(mat_resource_id)},
        )
        for m in materials:
            attrs: dict = {"displaycolor": _mat_to_css(m)}
            if "name" in m:
                attrs["name"] = m["name"]
            ET.SubElement(base_mat_el, _qn("base", _NS_CORE), attrs)

    # colour group (per-face colour override)
    if colours:
        col_group_id = next_id()
        cg_el = ET.SubElement(
            resources,
            _qn("colorgroup", _NS_MAT),
            {"id": str(col_group_id)},
        )
        for c in colours:
            try:
                r, g, b, a = _parse_color(c)
            except ValueError:
                r, g, b, a = 128, 128, 128, 255
            ET.SubElement(
                cg_el,
                _qn("color", _NS_MAT),
                {"color": _color_to_css(r, g, b, a)},
            )

    # object
    obj_id = next_id()
    obj_el = ET.SubElement(
        resources,
        _qn("object"),
        {"id": str(obj_id), "type": "model"},
    )
    if mat_resource_id is not None:
        obj_el.set("pid", str(mat_resource_id))

    mesh_el = ET.SubElement(obj_el, _qn("mesh"))

    # vertices
    verts_el = ET.SubElement(mesh_el, _qn("vertices"))
    for v in verts:
        ET.SubElement(
            verts_el,
            _qn("vertex"),
            {
                "x": f"{v[0]:.8g}",
                "y": f"{v[1]:.8g}",
                "z": f"{v[2]:.8g}",
            },
        )

    # triangles
    tris_el = ET.SubElement(mesh_el, _qn("triangles"))
    for fi, f in enumerate(faces):
        attrs = {
            "v1": str(f[0]),
            "v2": str(f[1]),
            "v3": str(f[2]),
        }
        # per-face material id
        if face_material_ids is not None and fi < len(face_material_ids):
            mid = face_material_ids[fi]
            if mid is not None and mid >= 0:
                attrs["pid"] = str(mat_resource_id)
                attrs["p1"] = str(mid)
                attrs["p2"] = str(mid)
                attrs["p3"] = str(mid)
        # per-face colour (only if no material assigned)
        elif colours is not None and fi < len(colours) and col_group_id is not None:
            attrs["pid"] = str(col_group_id)
            attrs["p1"] = str(fi)
        ET.SubElement(tris_el, _qn("triangle"), attrs)

    # build
    build = ET.SubElement(root, _qn("build"))
    ET.SubElement(build, _qn("item"), {"objectid": str(obj_id)})

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(
        buf,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# OPC (Open Packaging Conventions) asset builders
# ---------------------------------------------------------------------------

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    '  <Default Extension="rels" ContentType="{ct_rel}"/>\n'
    '  <Default Extension="png"  ContentType="image/png"/>\n'
    '  <Override PartName="/3D/3dmodel.model" ContentType="{ct_model}"/>\n'
    "</Types>\n"
).format(ct_rel=_CT_REL, ct_model=_CT_MODEL)

_RELS_XML_NO_THUMB = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    '  <Relationship Id="rel0" Type="{rel_model}" Target="/3D/3dmodel.model"/>\n'
    "</Relationships>\n"
).format(rel_model=_REL_TYPE_3DMODEL)

_RELS_XML_THUMB = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    '  <Relationship Id="rel0" Type="{rel_model}" Target="/3D/3dmodel.model"/>\n'
    '  <Relationship Id="rel1" Type="{rel_thumb}" Target="/Thumbnail/thumbnail.png"/>\n'
    "</Relationships>\n"
).format(rel_model=_REL_TYPE_3DMODEL, rel_thumb=_REL_TYPE_THUMBNAIL)


# ---------------------------------------------------------------------------
# Public write
# ---------------------------------------------------------------------------


def write_threemf(
    path: str,
    mesh_or_body,
    materials: Optional[List[dict]] = None,
    colours: Optional[List[str]] = None,
    thumbnail_png: Optional[bytes] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> None:
    """Write a mesh (or Body) to a 3MF archive at *path*.

    Parameters
    ----------
    path : str
        Destination file path (will be overwritten).
    mesh_or_body :
        One of:
        - a ``dict`` with ``"verts"`` and ``"faces"`` keys;
        - an object with ``.verts`` / ``.vertices`` and ``.faces`` attributes.
    materials : list of dict, optional
        Each dict should have ``"name"`` (str) plus colour information as one
        of: ``"color"`` ("#rrggbb[aa]"), or ``"r"``/``"g"``/``"b"`` ints.
    colours : list of str, optional
        Per-face colour overrides as ``"#rrggbb"`` / ``"#rrggbbaa"`` strings.
        Length should match ``len(faces)``.
    thumbnail_png : bytes, optional
        Raw PNG bytes for the package thumbnail.  Pass ``None`` to omit.
    metadata : dict, optional
        Key→value pairs written as ``<metadata>`` elements in the model XML.

    Raises
    ------
    ThreeMFWriteError
        If the mesh data is invalid or the archive cannot be written.
    """
    # --- normalise input mesh ---
    try:
        if isinstance(mesh_or_body, dict):
            verts = mesh_or_body["verts"]
            faces = mesh_or_body["faces"]
            face_material_ids = mesh_or_body.get("face_material_ids", None)
        else:
            verts = getattr(
                mesh_or_body, "verts", getattr(mesh_or_body, "vertices", None)
            )
            faces = getattr(mesh_or_body, "faces", None)
            face_material_ids = getattr(
                mesh_or_body, "face_material_ids", None
            )
    except (KeyError, AttributeError) as exc:
        raise ThreeMFWriteError(f"Cannot extract verts/faces from mesh_or_body: {exc}") from exc

    if verts is None or faces is None:
        raise ThreeMFWriteError("mesh_or_body must provide 'verts' and 'faces'")

    try:
        verts = [list(v) for v in verts]
        faces = [list(f) for f in faces]
    except Exception as exc:
        raise ThreeMFWriteError(f"Invalid verts/faces structure: {exc}") from exc

    # --- build XML ---
    try:
        model_xml = _build_model_xml(
            verts, faces, materials, colours, face_material_ids, metadata
        )
    except Exception as exc:
        raise ThreeMFWriteError(f"Failed to build 3dmodel.model XML: {exc}") from exc

    # --- write ZIP ---
    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            if thumbnail_png is not None:
                zf.writestr("_rels/.rels", _RELS_XML_THUMB)
                zf.writestr("Thumbnail/thumbnail.png", thumbnail_png)
            else:
                zf.writestr("_rels/.rels", _RELS_XML_NO_THUMB)
            zf.writestr("3D/3dmodel.model", model_xml)
    except ThreeMFWriteError:
        raise
    except Exception as exc:
        raise ThreeMFWriteError(f"Failed to write 3MF archive '{path}': {exc}") from exc


# ---------------------------------------------------------------------------
# Public read
# ---------------------------------------------------------------------------


def read_threemf(path: str) -> dict:
    """Read a .3mf file and return a mesh dict.

    Returns
    -------
    dict with keys:
        ``verts``             — list of [x, y, z]
        ``faces``             — list of [i, j, k]
        ``materials``         — list of dicts (may be empty)
        ``face_material_ids`` — list of int (same length as faces; -1 = none)
        ``thumbnail_png``     — bytes or None
        ``metadata``          — dict str→str

    Raises
    ------
    ThreeMFReadError
        If the archive is missing required parts or the XML is malformed.
    """
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise ThreeMFReadError(f"Not a valid ZIP/3MF archive: {path!r}") from exc
    except FileNotFoundError as exc:
        raise ThreeMFReadError(f"File not found: {path!r}") from exc

    with zf:
        namelist = zf.namelist()

        # --- locate 3dmodel.model via _rels/.rels or fallback ---
        model_path = _locate_model(zf, namelist)

        try:
            model_xml_bytes = zf.read(model_path)
        except KeyError as exc:
            raise ThreeMFReadError(
                f"Cannot read model file '{model_path}' from archive"
            ) from exc

        # --- thumbnail ---
        thumbnail_png: Optional[bytes] = None
        for candidate in ("Thumbnail/thumbnail.png", "thumbnail.png"):
            if candidate in namelist:
                thumbnail_png = zf.read(candidate)
                break

        # --- parse XML ---
        try:
            root = ET.fromstring(model_xml_bytes)
        except ET.ParseError as exc:
            raise ThreeMFReadError(f"Malformed 3dmodel.model XML: {exc}") from exc

        verts, faces, materials, face_material_ids, metadata = _parse_model_xml(root)

    return {
        "verts": verts,
        "faces": faces,
        "materials": materials,
        "face_material_ids": face_material_ids,
        "thumbnail_png": thumbnail_png,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Internal parse helpers
# ---------------------------------------------------------------------------


def _locate_model(zf: zipfile.ZipFile, namelist: List[str]) -> str:
    """Return the archive-relative path to the 3dmodel.model file."""
    # Try _rels/.rels first
    if "_rels/.rels" in namelist:
        try:
            rels_xml = zf.read("_rels/.rels")
            rels_root = ET.fromstring(rels_xml)
            for rel in rels_root:
                rtype = rel.get("Type", "")
                if _REL_TYPE_3DMODEL in rtype:
                    target = rel.get("Target", "")
                    # Strip leading slash for zipfile lookup
                    target = target.lstrip("/")
                    if target:
                        return target
        except Exception:
            pass

    # Fallback: look for any *.model file
    for name in namelist:
        if name.endswith(".model"):
            return name

    # Last fallback: 3D/3dmodel.model
    if "3D/3dmodel.model" in namelist:
        return "3D/3dmodel.model"

    raise ThreeMFReadError("Cannot locate 3dmodel.model in archive")


def _parse_model_xml(
    root: ET.Element,
) -> Tuple[
    List[List[float]],
    List[List[int]],
    List[dict],
    List[int],
    Dict[str, str],
]:
    """Parse a <model> XML element and return (verts, faces, materials, face_material_ids, metadata)."""

    # Helper: strip namespace from tag
    def _local(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _find_all(parent: ET.Element, localname: str) -> List[ET.Element]:
        return [c for c in parent if _local(c.tag) == localname]

    def _find_one(parent: ET.Element, localname: str) -> Optional[ET.Element]:
        found = _find_all(parent, localname)
        return found[0] if found else None

    # Metadata
    metadata: Dict[str, str] = {}
    for m in _find_all(root, "metadata"):
        name = m.get("name", "")
        if name:
            metadata[name] = m.text or ""

    # Resources
    resources_el = _find_one(root, "resources")
    if resources_el is None:
        raise ThreeMFReadError("<resources> element not found in model")

    # basematerials
    # Map resource id → list of material dicts
    mat_groups: Dict[str, List[dict]] = {}
    for el in _find_all(resources_el, "basematerials"):
        gid = el.get("id", "")
        mats: List[dict] = []
        for base in _find_all(el, "base"):
            m_dict: dict = {}
            if "name" in base.attrib:
                m_dict["name"] = base.attrib["name"]
            dc = base.get("displaycolor", "")
            if dc:
                m_dict["color"] = dc
                try:
                    r, g, b, a = _parse_color(dc)
                    m_dict["r"] = r
                    m_dict["g"] = g
                    m_dict["b"] = b
                    m_dict["a"] = a
                except ValueError:
                    pass
            mats.append(m_dict)
        mat_groups[gid] = mats

    # First object element
    obj_el: Optional[ET.Element] = None
    obj_pid: Optional[str] = None
    for el in _find_all(resources_el, "object"):
        if el.get("type", "model") in ("model", ""):
            obj_el = el
            obj_pid = el.get("pid")
            break

    if obj_el is None:
        raise ThreeMFReadError("No <object> with type='model' found in <resources>")

    mesh_el = _find_one(obj_el, "mesh")
    if mesh_el is None:
        raise ThreeMFReadError("<mesh> element not found in object")

    # Vertices
    verts_el = _find_one(mesh_el, "vertices")
    if verts_el is None:
        raise ThreeMFReadError("<vertices> not found in mesh")

    verts: List[List[float]] = []
    for v in _find_all(verts_el, "vertex"):
        try:
            x = float(v.get("x", 0))
            y = float(v.get("y", 0))
            z = float(v.get("z", 0))
        except ValueError as exc:
            raise ThreeMFReadError(f"Invalid vertex coordinate: {exc}") from exc
        verts.append([x, y, z])

    # Triangles
    tris_el = _find_one(mesh_el, "triangles")
    if tris_el is None:
        raise ThreeMFReadError("<triangles> not found in mesh")

    faces: List[List[int]] = []
    face_material_ids: List[int] = []

    for tri in _find_all(tris_el, "triangle"):
        try:
            v1 = int(tri.get("v1", 0))
            v2 = int(tri.get("v2", 0))
            v3 = int(tri.get("v3", 0))
        except ValueError as exc:
            raise ThreeMFReadError(f"Invalid triangle vertex index: {exc}") from exc
        faces.append([v1, v2, v3])

        # Resolve material id
        pid = tri.get("pid", obj_pid)
        p1 = tri.get("p1")
        mid = -1
        if pid is not None and p1 is not None and pid in mat_groups:
            try:
                mid = int(p1)
            except ValueError:
                mid = -1
        face_material_ids.append(mid)

    # Flatten materials: use the pid from the object (first group)
    materials: List[dict] = []
    if obj_pid and obj_pid in mat_groups:
        materials = mat_groups[obj_pid]
    elif mat_groups:
        # fallback: use first group
        materials = next(iter(mat_groups.values()))

    return verts, faces, materials, face_material_ids, metadata
