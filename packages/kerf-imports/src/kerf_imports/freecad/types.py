"""
types.py — dataclasses for the FCStd in-memory representation.

Downstream tasks (T2 BRep-lift, T3 sketch translator, T4 feature metadata)
consume these types; nothing here imports FreeCAD.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FCStdParseError(ValueError):
    """Raised when the .FCStd archive is malformed or unreadable."""


class FCStdUnsupportedVersionError(FCStdParseError):
    """Raised when SchemaVersion < 4 (FreeCAD older than 0.19)."""
    def __init__(self, version: int) -> None:
        self.version = version
        super().__init__(
            f"FCStd SchemaVersion {version} is not supported (minimum: 4, "
            "i.e. FreeCAD 0.19+). Please re-save in FreeCAD 0.19 or newer."
        )


# ---------------------------------------------------------------------------
# Link references (no graph traversal in T1)
# ---------------------------------------------------------------------------

@dataclass
class LinkRef:
    """
    A name-based reference to another FCStd object.

    Corresponds to ``App::PropertyLink`` / ``App::PropertyLinkSub``.
    Graph traversal is deferred to T4+.
    """
    target_name: str                    # internal object name
    sub_elements: list[str] = field(default_factory=list)  # e.g. ["Edge3", "Face1"]

    def __repr__(self) -> str:
        if self.sub_elements:
            return f"LinkRef({self.target_name!r}, {self.sub_elements!r})"
        return f"LinkRef({self.target_name!r})"


# ---------------------------------------------------------------------------
# Per-object representation
# ---------------------------------------------------------------------------

@dataclass
class FCStdObject:
    """
    One ``<Object>`` entry from ``Document.xml``'s ``<ObjectData>`` block.

    ``properties`` maps property names to typed Python values.  The set of
    value types that can appear:

    * ``int``, ``float``, ``bool``, ``str`` — primitives
    * ``list[float]``, ``list[int]``, ``list[str]`` — lists
    * ``dict`` — Placement / Vector / Matrix (keys depend on sub-type)
    * ``LinkRef`` — a reference to another object by internal name
    * ``bytes`` — raw content of a ``FileIncluded`` blob (BRep etc.)
    * ``list[dict]`` — GeometryList / ConstraintList / LinkList entries
    * ``str`` prefixed ``_UNKNOWN_<type>`` — unrecognised property type;
      value is the raw XML text for the inner element
    """
    name: str                           # internal name e.g. "Body", "Sketch001"
    type: str                           # FreeCAD type e.g. "PartDesign::Body"
    label: str                          # user-visible label
    properties: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level document
# ---------------------------------------------------------------------------

@dataclass
class FCStdDocument:
    """
    The complete in-memory representation of a parsed ``.FCStd`` file.

    Attributes
    ----------
    schema_version : int
        The ``SchemaVersion`` attribute from ``<Document>``.  Must be >= 4.
    program_version : str
        The ``ProgramVersion`` attribute e.g. ``"0.21R3"``.
    objects : list[FCStdObject]
        All objects in declaration order from ``<ObjectData>``.
    properties : dict[str, dict]
        Global document-level properties (``<Properties>`` at the document
        root level, outside any object).  Rarely populated but preserved.
    brep_blobs : dict[str, bytes]
        Mapping from zip member name (e.g. ``"PartShape1.brp"``) to the raw
        ASCII BRep bytes.  Populated for every ``*.brp`` file found in the
        archive so downstream BRep-lift (T2) can locate them without re-opening
        the zip.
    raw_xml : dict[str, bytes]
        Every XML member in the zip (e.g. ``"Document.xml"``,
        ``"GuiDocument.xml"``) keyed by member name.  Preserved for
        downstream tasks that need the full XML.
    """
    schema_version: int
    program_version: str
    objects: list[FCStdObject] = field(default_factory=list)
    properties: dict[str, dict] = field(default_factory=dict)
    brep_blobs: dict[str, bytes] = field(default_factory=dict)
    raw_xml: dict[str, bytes] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def object_by_name(self, name: str) -> FCStdObject | None:
        """Return the first object with the given internal name, or None."""
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def objects_by_type(self, type_prefix: str) -> list[FCStdObject]:
        """Return all objects whose type starts with *type_prefix*."""
        return [o for o in self.objects if o.type.startswith(type_prefix)]
