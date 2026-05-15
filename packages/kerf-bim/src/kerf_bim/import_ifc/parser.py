"""
parser.py — top-level IFC file parser.

parse_ifc_file(path) → IFCImportResult

Walks the IFC model by entity type (Tier 1 + Tier 2 set):
    IfcSite               → site metadata
    IfcBuildingStorey     → level nodes
    IfcWall               → wall nodes  (includes IfcWallStandardCase)
    IfcWallStandardCase   → wall nodes  (explicit query for software that
                            writes both types)
    IfcSlab               → slab nodes
    IfcSpace              → space nodes
    IfcWindow / IfcDoor   → openings[] nodes  [Tier 2]
    IfcFlowSegment etc.   → mep[] nodes       [Tier 2]

Tier-2 structural types (IfcColumn, IfcBeam, IfcCurtainWall, IfcRailing,
IfcStairFlight, IfcMember, IfcPlate, families, schedules, views) are
skipped with a summary warning.

## Placement chain note

IfcLocalPlacement is hierarchical.  Each IfcLocalPlacement has:
  - RelativePlacement: Axis2Placement3D (the local 4×4)
  - PlacementRelTo:    pointer to parent IfcLocalPlacement (or None for site)

ifcopenshell.util.placement.get_local_placement() walks this chain
automatically and returns the absolute 4×4 world matrix — our translator
modules call it rather than implementing the traversal themselves.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from kerf_bim.import_ifc.types import IFCImportResult, IFCImportError, IFCOpenShellNotInstalled
from kerf_bim.import_ifc.sites import translate_site
from kerf_bim.import_ifc.levels import translate_level
from kerf_bim.import_ifc.walls import translate_wall
from kerf_bim.import_ifc.slabs import translate_slab
from kerf_bim.import_ifc.spaces import translate_space
from kerf_bim.import_ifc.openings import translate_opening
from kerf_bim.import_ifc.mep import translate_mep_element, MEP_QUERY_TYPES
from kerf_bim.import_ifc.families import translate_type_object, TYPE_OBJECT_QUERY_TYPES
from kerf_bim.import_ifc.schedules import extract_quantity_schedules
from kerf_bim.import_ifc.views import extract_views

logger = logging.getLogger(__name__)

# Tier-2 structural entity types still intentionally skipped (not yet supported).
# Windows, doors, and MEP distribution elements are now translated (Tier 2).
_TIER2_SKIPPED_TYPES = (
    "IfcColumn",
    "IfcBeam",
    "IfcCurtainWall",
    "IfcRailing",
    "IfcStairFlight",
    "IfcMember",
    "IfcPlate",
)


def parse_ifc_file(path: Path) -> IFCImportResult:
    """
    Parse an IFC file and return an IFCImportResult.

    Parameters
    ----------
    path : Path
        Path to the .ifc file on disk.

    Returns
    -------
    IFCImportResult

    Raises
    ------
    IFCOpenShellNotInstalled
        If ifcopenshell is not importable.
    IFCImportError
        If the file cannot be opened or is not a valid IFC file.
    """
    try:
        import ifcopenshell  # type: ignore
    except ImportError:
        raise IFCOpenShellNotInstalled()

    if not Path(path).exists():
        raise IFCImportError(f"IFC file not found: {path}")

    try:
        ifc_file = ifcopenshell.open(str(path))
    except Exception as exc:
        raise IFCImportError(f"Failed to open IFC file {path}: {exc}") from exc

    warnings: list[str] = []
    bim: dict[str, Any] = {
        "version": 1,
        "name": "",
        "levels": [],
        "walls": [],
        "slabs": [],
        "spaces": [],
        "openings": [],
        "mep": [],
    }
    # These are produced as separate JSON documents alongside the .bim file.
    # They are stored on IFCImportResult.families / .schedules / .views.
    families: list[dict[str, Any]] = []
    schedules: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []

    # ── Project name from IfcProject ────────────────────────────────────────
    try:
        projects = ifc_file.by_type("IfcProject")
        if projects:
            bim["name"] = str(getattr(projects[0], "Name", None) or "Imported Project")
        else:
            bim["name"] = "Imported Project"
    except Exception:
        bim["name"] = "Imported Project"

    # ── Site ────────────────────────────────────────────────────────────────
    sites = []
    try:
        sites = ifc_file.by_type("IfcSite")
    except Exception as exc:
        warnings.append(f"IfcSite query failed: {exc}")

    if sites:
        bim["site"] = translate_site(sites[0])
        if len(sites) > 1:
            warnings.append(
                f"{len(sites)} IfcSite entities found; only the first is translated "
                "(multi-site projects are not yet supported)"
            )

    # ── Levels ──────────────────────────────────────────────────────────────
    storeys = []
    try:
        storeys = ifc_file.by_type("IfcBuildingStorey")
    except Exception as exc:
        warnings.append(f"IfcBuildingStorey query failed: {exc}")

    # Build GlobalId → level name map for downstream translators
    level_guid_to_name: dict[str, str] = {}

    for storey in storeys:
        try:
            level = translate_level(storey)
            bim["levels"].append(level)
            gid = getattr(storey, "GlobalId", "")
            level_guid_to_name[gid] = level["name"]
        except Exception as exc:
            gid = getattr(storey, "GlobalId", "?")
            warnings.append(f"level {gid!r}: translation failed ({exc}); skipped")

    if not bim["levels"]:
        warnings.append(
            "No IfcBuildingStorey entities found; elements will have empty level references"
        )

    # ── Walls ───────────────────────────────────────────────────────────────
    # Query both IfcWall and IfcWallStandardCase; de-duplicate by GlobalId
    wall_entities: dict[str, Any] = {}
    for wtype in ("IfcWall", "IfcWallStandardCase"):
        try:
            for w in ifc_file.by_type(wtype):
                gid = getattr(w, "GlobalId", id(w))
                wall_entities[gid] = w
        except Exception as exc:
            warnings.append(f"{wtype} query failed: {exc}")

    for gid, ifc_wall in wall_entities.items():
        try:
            wall_node = translate_wall(ifc_wall, level_guid_to_name, warnings)
            if wall_node:
                bim["walls"].append(wall_node)
        except Exception as exc:
            warnings.append(f"wall {gid!r}: translation error ({exc}); skipped")

    # ── Slabs ────────────────────────────────────────────────────────────────
    try:
        slab_entities = ifc_file.by_type("IfcSlab")
    except Exception as exc:
        slab_entities = []
        warnings.append(f"IfcSlab query failed: {exc}")

    for ifc_slab in slab_entities:
        gid = getattr(ifc_slab, "GlobalId", "?")
        try:
            slab_node = translate_slab(ifc_slab, level_guid_to_name, warnings)
            if slab_node:
                bim["slabs"].append(slab_node)
        except Exception as exc:
            warnings.append(f"slab {gid!r}: translation error ({exc}); skipped")

    # ── Spaces ───────────────────────────────────────────────────────────────
    try:
        space_entities = ifc_file.by_type("IfcSpace")
    except Exception as exc:
        space_entities = []
        warnings.append(f"IfcSpace query failed: {exc}")

    for ifc_space in space_entities:
        gid = getattr(ifc_space, "GlobalId", "?")
        try:
            space_node = translate_space(ifc_space, level_guid_to_name, warnings)
            if space_node:
                bim["spaces"].append(space_node)
        except Exception as exc:
            warnings.append(f"space {gid!r}: translation error ({exc}); skipped")

    # ── Openings: IfcWindow + IfcDoor ────────────────────────────────────────
    opening_entities: dict[str, Any] = {}
    for otype in ("IfcWindow", "IfcDoor"):
        try:
            for elem in ifc_file.by_type(otype):
                gid = getattr(elem, "GlobalId", id(elem))
                opening_entities[gid] = elem
        except Exception as exc:
            warnings.append(f"{otype} query failed: {exc}")

    for gid, ifc_opening in opening_entities.items():
        try:
            opening_node = translate_opening(ifc_opening, level_guid_to_name, warnings)
            if opening_node:
                bim["openings"].append(opening_node)
        except Exception as exc:
            warnings.append(f"opening {gid!r}: translation error ({exc}); skipped")

    # ── MEP: IfcDistributionElement subtypes ─────────────────────────────────
    mep_entities: dict[str, Any] = {}
    for mep_type in MEP_QUERY_TYPES:
        try:
            for elem in ifc_file.by_type(mep_type):
                gid = getattr(elem, "GlobalId", id(elem))
                mep_entities[gid] = elem
        except Exception as exc:
            warnings.append(f"{mep_type} query failed: {exc}")

    for gid, ifc_mep in mep_entities.items():
        try:
            mep_node = translate_mep_element(ifc_mep, level_guid_to_name, warnings)
            if mep_node:
                bim["mep"].append(mep_node)
        except Exception as exc:
            warnings.append(f"mep element {gid!r}: translation error ({exc}); skipped")

    # ── Families: IFC type objects ───────────────────────────────────────────
    type_entities: dict[str, Any] = {}
    for type_query in TYPE_OBJECT_QUERY_TYPES:
        try:
            for elem in ifc_file.by_type(type_query):
                gid = getattr(elem, "GlobalId", id(elem))
                type_entities[gid] = elem
        except Exception as exc:
            warnings.append(f"{type_query} query failed: {exc}")

    for gid, ifc_type_obj in type_entities.items():
        try:
            family_payload = translate_type_object(ifc_type_obj, warnings)
            if family_payload:
                families.append(family_payload)
        except Exception as exc:
            warnings.append(f"type object {gid!r}: translation error ({exc}); skipped")

    # ── Schedules: IFC quantity sets ─────────────────────────────────────────
    try:
        schedules = extract_quantity_schedules(ifc_file, warnings)
    except Exception as exc:
        warnings.append(f"quantity schedule extraction failed: {exc}")

    # ── Views: IFC representation contexts ───────────────────────────────────
    try:
        views = extract_views(ifc_file, warnings)
    except Exception as exc:
        warnings.append(f"view context extraction failed: {exc}")

    # ── Tier-2 structural skip summary ───────────────────────────────────────
    tier2_counts: dict[str, int] = {}
    for t2_type in _TIER2_SKIPPED_TYPES:
        try:
            entities = ifc_file.by_type(t2_type)
            if entities:
                tier2_counts[t2_type] = len(entities)
        except Exception:
            pass

    if tier2_counts:
        summary = ", ".join(f"{t}×{n}" for t, n in sorted(tier2_counts.items()))
        warnings.append(
            f"Tier-2 structural entity types skipped (not yet supported): {summary}. "
            "These will be supported in a future IFC import release."
        )

    stats = {
        "sites":     len(sites),
        "levels":    len(bim["levels"]),
        "walls":     len(bim["walls"]),
        "slabs":     len(bim["slabs"]),
        "spaces":    len(bim["spaces"]),
        "openings":  len(bim["openings"]),
        "mep":       len(bim["mep"]),
        "families":  len(families),
        "schedules": len(schedules),
        "views":     len(views),
    }

    return IFCImportResult(
        bim_payload=bim,
        stats=stats,
        warnings=warnings,
        families=families,
        schedules=schedules,
        views=views,
    )
