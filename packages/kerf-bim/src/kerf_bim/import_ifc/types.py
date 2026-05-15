"""
types.py — dataclasses for the IFC import pipeline.

IFCImportResult carries the structured output of parse_ifc_file().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class IFCImportError(RuntimeError):
    """Raised for fatal import problems (missing dependency, unreadable file)."""


class IFCOpenShellNotInstalled(IFCImportError):
    """Raised when ifcopenshell is not importable."""
    def __init__(self) -> None:
        super().__init__(
            "IfcOpenShell not installed — install with: pip install ifcopenshell"
        )


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class IFCImportResult:
    """
    Structured output of parse_ifc_file().

    bim_payload : dict
        A JSON-serialisable dict that conforms to the .bim JSON schema
        (version, name, site, levels, walls, slabs, spaces, openings, mep).
    stats : dict
        Counts of translated entities by type.
    warnings : list[str]
        Non-fatal translation issues — geometry fallbacks, skipped Tier-2
        features, missing property sets, etc.
    families : list[dict]
        .family.json payloads extracted from IFC type objects (Tier 2).
        Each entry is a JSON-serialisable dict conforming to the .family.json
        schema.  Empty list when no type objects are present.
    schedules : list[dict]
        .schedule.json payloads extracted from IFC quantity sets (Tier 2).
        One entry per unique IfcElementQuantity name.  Empty when absent.
    views : list[dict]
        .view.json payloads extracted from IFC representation contexts (Tier 2).
        One entry per IfcGeometricRepresentationContext/SubContext.
    """
    bim_payload: dict[str, Any]
    stats: dict[str, int]
    warnings: list[str] = field(default_factory=list)
    families: list[dict[str, Any]] = field(default_factory=list)
    schedules: list[dict[str, Any]] = field(default_factory=list)
    views: list[dict[str, Any]] = field(default_factory=list)
