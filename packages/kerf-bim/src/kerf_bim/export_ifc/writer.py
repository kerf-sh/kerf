"""
writer.py — .bim building model dict → IFC STEP-physical-file text.

export_ifc(model, schema="IFC2X3") → IFCExportResult

Tier 1 scope
------------
- IFC header: FILE_DESCRIPTION / FILE_NAME / FILE_SCHEMA
- IfcUnitAssignment (SI metres — IFC stores in metres; Kerf model in mm,
  so we scale mm → m on write)
- IfcGeometricRepresentationContext (3D model context)
- IfcOwnerHistory (minimal owner/application)
- Spatial structure: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey
- Elements with IfcExtrudedAreaSolid body representations:
    IfcWall, IfcSlab, IfcColumn, IfcBeam, IfcDoor, IfcWindow
- IfcLocalPlacement hierarchy matching the spatial structure
- IfcRelAggregates + IfcRelContainedInSpatialStructure relationships

## Unit convention

The .bim model carries dimensions in **millimetres** (matching the IFC
import module's output convention).  The IFC STEP file uses **metres** when
the IfcSIUnit for LENGTHUNIT is METRE (no prefix).  We divide all linear
dimensions by 1000 when writing the STEP file.

The STEP file is a pure ASCII text document — no external library required.

## STEP entity numbering

All #N references use a single monotonically-increasing counter supplied by
_IDGen.  The counter starts at 1.

## Validation

A minimal syntactic validation pass is run before returning:
- All #N forward-references must be defined somewhere in the DATA section.
- The file must end with ENDSEC; END-ISO-10303-21;

Raises IFCExportError on invalid model input.
"""
from __future__ import annotations

import datetime
import math
import re
import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IFCExportError(RuntimeError):
    """Raised for fatal export problems."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class IFCExportResult:
    """
    Structured output of export_ifc().

    ifc_text     : str   — the complete STEP physical file as a string.
    entity_count : int   — number of DATA section entities (#N=...) written.
    schema       : str   — "IFC2X3" or "IFC4".
    warnings     : list  — non-fatal issues (unsupported element types, etc.)
    """
    ifc_text: str
    entity_count: int
    schema: str
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ID generator
# ---------------------------------------------------------------------------


class _IDGen:
    """Thread-unsafe sequential STEP entity ID generator."""

    def __init__(self, start: int = 1) -> None:
        self._n = start

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


# ---------------------------------------------------------------------------
# STEP helpers
# ---------------------------------------------------------------------------

_MM_TO_M = 1.0 / 1000.0

# IFC GlobalId is a 22-char base64url string (a subset).  For generated
# entities we derive a deterministic ID from the entity sequence number
# so tests can be hermetic.
_BASE64_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def _ifc_guid(seed: int | str) -> str:
    """
    Generate an IFC GlobalId (22 chars from the IFC GUID alphabet).
    Uses a seed so tests are deterministic.
    """
    # Encode seed as a 22-char string using the IFC GUID character set.
    if isinstance(seed, str):
        # Deterministic: hash the string to a 128-bit integer
        import hashlib
        h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        n = h
    else:
        # Pad the integer to 128 bits
        n = int(seed) % (2 ** 128)
    chars = []
    for _ in range(22):
        chars.append(_BASE64_CHARS[n % 64])
        n //= 64
    return "".join(chars)


def _f(v: float, decimals: int = 6) -> str:
    """Format a float for STEP output. Always includes a decimal point."""
    s = f"{round(v, decimals):.6g}"
    # Ensure STEP files always have explicit decimal point for real literals
    if "." not in s and "e" not in s.lower():
        s = s + "."
    return s


def _pt3(x: float, y: float, z: float) -> str:
    return f"({_f(x)},{_f(y)},{_f(z)})"


def _pt2(x: float, y: float) -> str:
    return f"({_f(x)},{_f(y)})"


def _s(v: str | None) -> str:
    """Wrap a string value for STEP; None → $."""
    if v is None:
        return "$"
    safe = str(v).replace("'", "''")
    return f"'{safe}'"


def _ref(n: int) -> str:
    return f"#{n}"


# ---------------------------------------------------------------------------
# Core exporter
# ---------------------------------------------------------------------------


def export_ifc(
    model: dict[str, Any],
    schema: str = "IFC2X3",
    author: str = "Kerf",
    organisation: str = "Kerf",
) -> IFCExportResult:
    """
    Export a Kerf .bim model dict to an IFC STEP-physical-file string.

    Parameters
    ----------
    model : dict
        A .bim model dict as produced by the IFC import module or the Kerf
        BIM compiler.  Expected keys:
            name       : str  — project name
            levels     : list[{name, elevation}]       — mm
            walls      : list[{level, from, to, height, thickness}]   — mm
            slabs      : list[{level, boundary, thickness}]           — mm
            openings   : list[{kind, level, position, width, height}] — mm
            columns    : list[{level, position, width, depth, height}] — mm (optional)
            beams      : list[{level, start, end, width, height}]      — mm (optional)
        site (optional): {name, latitude, longitude, elevation}
    schema : str
        "IFC2X3" or "IFC4" (default: "IFC2X3").
    author : str
        Author name for the FILE_NAME header.
    organisation : str
        Organisation for the FILE_NAME and IfcOrganization.

    Returns
    -------
    IFCExportResult

    Raises
    ------
    IFCExportError
        If model is None, not a dict, or critically malformed.
    """
    if model is None:
        raise IFCExportError("model is None")
    if not isinstance(model, dict):
        raise IFCExportError(f"model must be a dict, got {type(model).__name__!r}")

    schema = schema.upper()
    if schema not in ("IFC2X3", "IFC4"):
        raise IFCExportError(f"schema must be 'IFC2X3' or 'IFC4', got {schema!r}")

    warnings: list[str] = []
    ids = _IDGen()
    lines: list[str] = []  # DATA section entities

    def entity(n: int, text: str) -> None:
        lines.append(f"#{n}={text};")

    # ── Units ────────────────────────────────────────────────────────────────
    id_unit_length  = ids.next()
    id_unit_area    = ids.next()
    id_unit_volume  = ids.next()
    id_unit_assign  = ids.next()

    entity(id_unit_length, "IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
    entity(id_unit_area,   "IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
    entity(id_unit_volume, "IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
    entity(id_unit_assign, f"IFCUNITASSIGNMENT((#{id_unit_length},#{id_unit_area},#{id_unit_volume}))")

    # ── Geometric representation context ────────────────────────────────────
    id_origin3d     = ids.next()
    id_z_dir        = ids.next()
    id_x_dir        = ids.next()
    id_axis_world   = ids.next()
    id_rep_ctx      = ids.next()

    entity(id_origin3d,   "IFCCARTESIANPOINT((0.,0.,0.))")
    entity(id_z_dir,      "IFCDIRECTION((0.,0.,1.))")
    entity(id_x_dir,      "IFCDIRECTION((1.,0.,0.))")
    entity(id_axis_world, f"IFCAXIS2PLACEMENT3D(#{id_origin3d},#{id_z_dir},#{id_x_dir})")
    entity(id_rep_ctx,    f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,#{id_axis_world},$)")

    # ── Owner / application ──────────────────────────────────────────────────
    id_org          = ids.next()
    id_person       = ids.next()
    id_pers_org     = ids.next()
    id_app          = ids.next()
    id_owner_hist   = ids.next()

    ts_now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    entity(id_org,        f"IFCORGANIZATION($,{_s(organisation)},$,$,$)")
    entity(id_person,     f"IFCPERSON($,{_s(author)},$,$,$,$,$,$)")
    entity(id_pers_org,   f"IFCPERSONANDORGANIZATION(#{id_person},#{id_org},$)")
    entity(id_app,        f"IFCAPPLICATION(#{id_org},'1.0','Kerf BIM Exporter','Kerf')")
    entity(id_owner_hist, (
        f"IFCOWNERHISTORY(#{id_pers_org},#{id_app},$,"
        f".NOTDEFINED.,$,#{id_pers_org},#{id_app},{ts_now})"
    ))

    # ── Project ──────────────────────────────────────────────────────────────
    project_name = str(model.get("name") or "Kerf Project")
    id_project   = ids.next()
    entity(id_project, (
        f"IFCPROJECT({_s(_ifc_guid('project'))},"
        f"#{id_owner_hist},{_s(project_name)},$,$,$,$,"
        f"(#{id_rep_ctx}),#{id_unit_assign})"
    ))

    # ── Site ────────────────────────────────────────────────────────────────
    site_block = model.get("site") or {}
    site_name = str(site_block.get("name") or "Site")
    site_elev = float(site_block.get("elevation") or 0.0) * _MM_TO_M

    id_site_origin = ids.next()
    id_site_ax     = ids.next()
    id_site_place  = ids.next()
    id_site        = ids.next()

    entity(id_site_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
    entity(id_site_ax,     f"IFCAXIS2PLACEMENT3D(#{id_site_origin},$,$)")
    entity(id_site_place,  f"IFCLOCALPLACEMENT($,#{id_site_ax})")
    entity(id_site, (
        f"IFCSITE({_s(_ifc_guid('site'))},"
        f"#{id_owner_hist},{_s(site_name)},$,$,"
        f"#{id_site_place},$,$,.ELEMENT.,(0,0,0,0),(0,0,0,0),"
        f"{_f(site_elev)},$,$)"
    ))

    # ── Building ────────────────────────────────────────────────────────────
    id_bldg_origin = ids.next()
    id_bldg_ax     = ids.next()
    id_bldg_place  = ids.next()
    id_bldg        = ids.next()

    entity(id_bldg_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
    entity(id_bldg_ax,     f"IFCAXIS2PLACEMENT3D(#{id_bldg_origin},$,$)")
    entity(id_bldg_place,  f"IFCLOCALPLACEMENT(#{id_site_place},#{id_bldg_ax})")
    entity(id_bldg, (
        f"IFCBUILDING({_s(_ifc_guid('building'))},"
        f"#{id_owner_hist},{_s(project_name)},$,$,"
        f"#{id_bldg_place},$,$,.ELEMENT.,$,$,$)"
    ))

    # ── Levels (IfcBuildingStorey) ────────────────────────────────────────────
    levels_data = model.get("levels") or []
    if not levels_data:
        warnings.append("no levels defined; creating a single default level 'L1' at elevation 0")
        levels_data = [{"name": "L1", "elevation": 0.0}]

    # Map level name → (storey entity id, storey placement id)
    level_name_to_ids: dict[str, tuple[int, int]] = {}
    storey_ids: list[int] = []

    for lvl in levels_data:
        lvl_name = str(lvl.get("name") or "L?")
        lvl_elev = float(lvl.get("elevation") or 0.0) * _MM_TO_M

        id_lvl_origin = ids.next()
        id_lvl_ax     = ids.next()
        id_lvl_place  = ids.next()
        id_storey     = ids.next()

        entity(id_lvl_origin, f"IFCCARTESIANPOINT((0.,0.,{_f(lvl_elev)}))")
        entity(id_lvl_ax,     f"IFCAXIS2PLACEMENT3D(#{id_lvl_origin},$,$)")
        entity(id_lvl_place,  f"IFCLOCALPLACEMENT(#{id_bldg_place},#{id_lvl_ax})")
        entity(id_storey, (
            f"IFCBUILDINGSTOREY({_s(_ifc_guid('storey_' + lvl_name))},"
            f"#{id_owner_hist},{_s(lvl_name)},$,$,"
            f"#{id_lvl_place},$,$,.ELEMENT.,{_f(lvl_elev)})"
        ))

        level_name_to_ids[lvl_name] = (id_storey, id_lvl_place)
        storey_ids.append(id_storey)

    # Fall back: the first level's placement for elements with no level match
    _default_storey_id, _default_place_id = level_name_to_ids[
        (levels_data[0].get("name") or "L1")
    ]

    def _resolve_level(level_name: str) -> tuple[int, int]:
        """Return (storey_id, storey_placement_id) for a level name."""
        if level_name in level_name_to_ids:
            return level_name_to_ids[level_name]
        return _default_storey_id, _default_place_id

    # ── Spatial relationships ────────────────────────────────────────────────
    # project → site
    id_rel_proj_site = ids.next()
    entity(id_rel_proj_site, (
        f"IFCRELAGGREGATES({_s(_ifc_guid('rel_proj_site'))},"
        f"#{id_owner_hist},$,$,#{id_project},(#{id_site}))"
    ))
    # site → building
    id_rel_site_bldg = ids.next()
    entity(id_rel_site_bldg, (
        f"IFCRELAGGREGATES({_s(_ifc_guid('rel_site_bldg'))},"
        f"#{id_owner_hist},$,$,#{id_site},(#{id_bldg}))"
    ))
    # building → storeys
    storey_ref_list = ",".join(f"#{s}" for s in storey_ids)
    id_rel_bldg_storeys = ids.next()
    entity(id_rel_bldg_storeys, (
        f"IFCRELAGGREGATES({_s(_ifc_guid('rel_bldg_storeys'))},"
        f"#{id_owner_hist},$,$,#{id_bldg},({storey_ref_list}))"
    ))

    # ── Per-storey element accumulator ──────────────────────────────────────
    # storey_id → list of element entity IDs contained in that storey
    storey_elements: dict[int, list[int]] = {sid: [] for sid in storey_ids}

    # ── Helper: emit an IfcExtrudedAreaSolid for a wall ─────────────────────

    def _emit_wall(
        w: dict[str, Any],
        idx: int,
    ) -> int | None:
        """
        Emit IFC entities for one wall.  Returns the IfcWall entity id, or
        None if the wall data is critically invalid.
        """
        try:
            frm = w.get("from") or [0.0, 0.0]
            to  = w.get("to")   or [1000.0, 0.0]
            fx, fy = float(frm[0]) * _MM_TO_M, float(frm[1]) * _MM_TO_M
            tx, ty = float(to[0])  * _MM_TO_M, float(to[1])  * _MM_TO_M

            height    = float(w.get("height")    or 3.0) * _MM_TO_M
            thickness = float(w.get("thickness") or 0.2) * _MM_TO_M
            level_nm  = str(w.get("level") or "")
            name      = str(w.get("name") or f"Wall_{idx + 1}")

            dx = tx - fx
            dy = ty - fy
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1e-9:
                warnings.append(f"wall {idx}: zero length; skipped")
                return None

            # Normalised direction along wall
            ux, uy = dx / length, dy / length
            # Centre of wall base in world coords
            cx = (fx + tx) / 2.0
            cy = (fy + ty) / 2.0

            storey_id, storey_place_id = _resolve_level(level_nm)

            # Profile definition (rectangle centred at local origin)
            id_prof_loc    = ids.next()
            id_prof_xdir   = ids.next()
            id_prof_ax     = ids.next()
            id_prof        = ids.next()
            id_ext_zdir    = ids.next()
            id_ext_origin  = ids.next()
            id_ext_ax      = ids.next()
            id_extrusion   = ids.next()
            id_shape_rep   = ids.next()
            id_prod_shape  = ids.next()
            id_elem_origin = ids.next()
            id_elem_ax     = ids.next()
            id_elem_place  = ids.next()
            id_wall        = ids.next()

            entity(id_prof_loc,    f"IFCCARTESIANPOINT(({_f(cx)},{_f(cy)},0.))")
            entity(id_prof_xdir,   f"IFCDIRECTION(({_f(ux)},{_f(uy)},0.))")
            entity(id_prof_ax,     f"IFCAXIS2PLACEMENT3D(#{id_prof_loc},#{id_z_dir},#{id_prof_xdir})")
            entity(id_prof,        f"IFCRECTANGLEPROFILEDEF(.AREA.,$,#{id_prof_ax},{_f(length)},{_f(thickness)})")
            entity(id_ext_zdir,    "IFCDIRECTION((0.,0.,1.))")
            entity(id_ext_origin,  "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_ext_ax,      f"IFCAXIS2PLACEMENT3D(#{id_ext_origin},#{id_ext_zdir},$)")
            entity(id_extrusion,   f"IFCEXTRUDEDAREASOLID(#{id_prof},#{id_ext_ax},#{id_ext_zdir},{_f(height)})")
            entity(id_shape_rep,   f"IFCSHAPEREPRESENTATION(#{id_rep_ctx},'Body','SweptSolid',(#{id_extrusion}))")
            entity(id_prod_shape,  f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{id_shape_rep}))")
            entity(id_elem_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_elem_ax,     f"IFCAXIS2PLACEMENT3D(#{id_elem_origin},$,$)")
            entity(id_elem_place,  f"IFCLOCALPLACEMENT(#{id_storey_place(storey_id)},#{id_elem_ax})")

            if schema == "IFC2X3":
                entity(id_wall, (
                    f"IFCWALLSTANDARDCASE({_s(_ifc_guid(f'wall_{idx}'))},"
                    f"#{id_owner_hist},{_s(name)},$,$,"
                    f"#{id_elem_place},#{id_prod_shape},$)"
                ))
            else:
                entity(id_wall, (
                    f"IFCWALL({_s(_ifc_guid(f'wall_{idx}'))},"
                    f"#{id_owner_hist},{_s(name)},$,$,"
                    f"#{id_elem_place},#{id_prod_shape},$,.STANDARD.)"
                ))

            storey_elements[storey_id].append(id_wall)
            return id_wall
        except Exception as exc:
            warnings.append(f"wall {idx}: export failed ({exc}); skipped")
            return None

    # ── Helper: storey placement id lookup ──────────────────────────────────
    # We need storey_id → placement_id.  Build a reverse map.
    _storey_to_placement: dict[int, int] = {}
    for _lvl in levels_data:
        _lname = str(_lvl.get("name") or "L?")
        _sid, _spid = level_name_to_ids[_lname]
        _storey_to_placement[_sid] = _spid

    def id_storey_place(storey_id: int) -> int:
        return _storey_to_placement.get(storey_id, _default_place_id)

    # ── Emit walls ──────────────────────────────────────────────────────────
    for idx, wall in enumerate(model.get("walls") or []):
        _emit_wall(wall, idx)

    # ── Emit slabs ──────────────────────────────────────────────────────────
    def _emit_slab(s: dict[str, Any], idx: int) -> int | None:
        try:
            boundary  = s.get("boundary") or []
            thickness = float(s.get("thickness") or 0.2) * _MM_TO_M
            level_nm  = str(s.get("level") or "")
            name      = str(s.get("name") or f"Slab_{idx + 1}")

            if len(boundary) < 3:
                # Default 5×5m slab
                boundary = [[0, 0], [5000, 0], [5000, 5000], [0, 5000]]
                warnings.append(f"slab {idx}: boundary has < 3 points; using default 5×5m")

            storey_id, _spid = _resolve_level(level_nm)

            # Build IfcPolyline for the profile outer curve
            pt_ids: list[int] = []
            for pt in boundary:
                px = float(pt[0]) * _MM_TO_M
                py = float(pt[1]) * _MM_TO_M
                id_pt = ids.next()
                entity(id_pt, f"IFCCARTESIANPOINT(({_f(px)},{_f(py)}))")
                pt_ids.append(id_pt)
            # Close the polyline (IFC requires the last point == first)
            pt_ids.append(pt_ids[0])
            pts_ref = ",".join(f"#{p}" for p in pt_ids)
            id_polyline = ids.next()
            entity(id_polyline, f"IFCPOLYLINE(({pts_ref}))")

            id_profile    = ids.next()
            id_ext_zdir   = ids.next()
            id_ext_origin = ids.next()
            id_ext_ax     = ids.next()
            id_extrusion  = ids.next()
            id_shape_rep  = ids.next()
            id_prod_shape = ids.next()
            id_elem_orig  = ids.next()
            id_elem_ax    = ids.next()
            id_elem_place = ids.next()
            id_slab       = ids.next()

            entity(id_profile,    f"IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,#{id_polyline})")
            entity(id_ext_zdir,   "IFCDIRECTION((0.,0.,-1.))")
            entity(id_ext_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_ext_ax,     f"IFCAXIS2PLACEMENT3D(#{id_ext_origin},#{id_ext_zdir},$)")
            entity(id_extrusion,  f"IFCEXTRUDEDAREASOLID(#{id_profile},#{id_ext_ax},#{id_ext_zdir},{_f(thickness)})")
            entity(id_shape_rep,  f"IFCSHAPEREPRESENTATION(#{id_rep_ctx},'Body','SweptSolid',(#{id_extrusion}))")
            entity(id_prod_shape, f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{id_shape_rep}))")
            entity(id_elem_orig,  "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_elem_ax,    f"IFCAXIS2PLACEMENT3D(#{id_elem_orig},$,$)")
            entity(id_elem_place, f"IFCLOCALPLACEMENT(#{id_storey_place(storey_id)},#{id_elem_ax})")
            entity(id_slab, (
                f"IFCSLAB({_s(_ifc_guid(f'slab_{idx}'))},"
                f"#{id_owner_hist},{_s(name)},$,$,"
                f"#{id_elem_place},#{id_prod_shape},$,.FLOOR.)"
            ))
            storey_elements[storey_id].append(id_slab)
            return id_slab
        except Exception as exc:
            warnings.append(f"slab {idx}: export failed ({exc}); skipped")
            return None

    for idx, slab in enumerate(model.get("slabs") or []):
        _emit_slab(slab, idx)

    # ── Emit columns ────────────────────────────────────────────────────────
    def _emit_column(c: dict[str, Any], idx: int) -> int | None:
        try:
            pos      = c.get("position") or [0.0, 0.0, 0.0]
            width    = float(c.get("width")  or 0.3) * _MM_TO_M
            depth    = float(c.get("depth")  or 0.3) * _MM_TO_M
            height   = float(c.get("height") or 3.0) * _MM_TO_M
            level_nm = str(c.get("level") or "")
            name     = str(c.get("name") or f"Column_{idx + 1}")
            px       = float(pos[0]) * _MM_TO_M
            py       = float(pos[1]) * _MM_TO_M

            storey_id, _ = _resolve_level(level_nm)

            id_prof_loc   = ids.next()
            id_prof_ax    = ids.next()
            id_prof       = ids.next()
            id_ext_zdir   = ids.next()
            id_ext_origin = ids.next()
            id_ext_ax     = ids.next()
            id_extrusion  = ids.next()
            id_shape_rep  = ids.next()
            id_prod_shape = ids.next()
            id_elem_orig  = ids.next()
            id_elem_ax    = ids.next()
            id_elem_place = ids.next()
            id_col        = ids.next()

            entity(id_prof_loc,   f"IFCCARTESIANPOINT(({_f(px)},{_f(py)}))")
            entity(id_prof_ax,    f"IFCAXIS2PLACEMENT2D(#{id_prof_loc},$)")
            entity(id_prof,       f"IFCRECTANGLEPROFILEDEF(.AREA.,$,#{id_prof_ax},{_f(width)},{_f(depth)})")
            entity(id_ext_zdir,   "IFCDIRECTION((0.,0.,1.))")
            entity(id_ext_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_ext_ax,     f"IFCAXIS2PLACEMENT3D(#{id_ext_origin},#{id_ext_zdir},$)")
            entity(id_extrusion,  f"IFCEXTRUDEDAREASOLID(#{id_prof},#{id_ext_ax},#{id_ext_zdir},{_f(height)})")
            entity(id_shape_rep,  f"IFCSHAPEREPRESENTATION(#{id_rep_ctx},'Body','SweptSolid',(#{id_extrusion}))")
            entity(id_prod_shape, f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{id_shape_rep}))")
            entity(id_elem_orig,  "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_elem_ax,    f"IFCAXIS2PLACEMENT3D(#{id_elem_orig},$,$)")
            entity(id_elem_place, f"IFCLOCALPLACEMENT(#{id_storey_place(storey_id)},#{id_elem_ax})")
            entity(id_col, (
                f"IFCCOLUMN({_s(_ifc_guid(f'col_{idx}'))},"
                f"#{id_owner_hist},{_s(name)},$,$,"
                f"#{id_elem_place},#{id_prod_shape},$)"
            ))
            storey_elements[storey_id].append(id_col)
            return id_col
        except Exception as exc:
            warnings.append(f"column {idx}: export failed ({exc}); skipped")
            return None

    for idx, col in enumerate(model.get("columns") or []):
        _emit_column(col, idx)

    # ── Emit beams ──────────────────────────────────────────────────────────
    def _emit_beam(b: dict[str, Any], idx: int) -> int | None:
        try:
            start    = b.get("start") or [0.0, 0.0, 0.0]
            end      = b.get("end")   or [5000.0, 0.0, 0.0]
            width    = float(b.get("width")  or 0.2) * _MM_TO_M
            bheight  = float(b.get("height") or 0.4) * _MM_TO_M
            level_nm = str(b.get("level") or "")
            name     = str(b.get("name") or f"Beam_{idx + 1}")

            sx, sy, sz = float(start[0]) * _MM_TO_M, float(start[1]) * _MM_TO_M, float(start[2] if len(start) > 2 else 0) * _MM_TO_M
            ex, ey, ez = float(end[0])   * _MM_TO_M, float(end[1])   * _MM_TO_M, float(end[2]   if len(end)   > 2 else 0) * _MM_TO_M

            dx, dy, dz = ex - sx, ey - sy, ez - sz
            blength = math.sqrt(dx * dx + dy * dy + dz * dz)
            if blength < 1e-9:
                warnings.append(f"beam {idx}: zero length; skipped")
                return None

            ux, uy, uz = dx / blength, dy / blength, dz / blength

            storey_id, _ = _resolve_level(level_nm)

            id_prof_ax    = ids.next()
            id_prof       = ids.next()
            id_ext_dir    = ids.next()
            id_ext_origin = ids.next()
            id_ext_ax     = ids.next()
            id_extrusion  = ids.next()
            id_shape_rep  = ids.next()
            id_prod_shape = ids.next()
            id_elem_orig  = ids.next()
            id_elem_xdir  = ids.next()
            id_elem_ax    = ids.next()
            id_elem_place = ids.next()
            id_beam       = ids.next()

            entity(id_prof_ax,    f"IFCAXIS2PLACEMENT2D($,$)")
            entity(id_prof,       f"IFCRECTANGLEPROFILEDEF(.AREA.,$,#{id_prof_ax},{_f(bheight)},{_f(width)})")
            entity(id_ext_dir,    f"IFCDIRECTION(({_f(ux)},{_f(uy)},{_f(uz)}))")
            entity(id_ext_origin, f"IFCCARTESIANPOINT(({_f(sx)},{_f(sy)},{_f(sz)}))")
            entity(id_ext_ax,     f"IFCAXIS2PLACEMENT3D(#{id_ext_origin},#{id_ext_dir},$)")
            entity(id_extrusion,  f"IFCEXTRUDEDAREASOLID(#{id_prof},#{id_ext_ax},#{id_ext_dir},{_f(blength)})")
            entity(id_shape_rep,  f"IFCSHAPEREPRESENTATION(#{id_rep_ctx},'Body','SweptSolid',(#{id_extrusion}))")
            entity(id_prod_shape, f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{id_shape_rep}))")
            entity(id_elem_orig,  f"IFCCARTESIANPOINT(({_f(sx)},{_f(sy)},{_f(sz)}))")
            entity(id_elem_xdir,  f"IFCDIRECTION(({_f(ux)},{_f(uy)},{_f(uz)}))")
            entity(id_elem_ax,    f"IFCAXIS2PLACEMENT3D(#{id_elem_orig},#{id_ext_dir},#{id_elem_xdir})")
            entity(id_elem_place, f"IFCLOCALPLACEMENT(#{id_storey_place(storey_id)},#{id_elem_ax})")
            entity(id_beam, (
                f"IFCBEAM({_s(_ifc_guid(f'beam_{idx}'))},"
                f"#{id_owner_hist},{_s(name)},$,$,"
                f"#{id_elem_place},#{id_prod_shape},$)"
            ))
            storey_elements[storey_id].append(id_beam)
            return id_beam
        except Exception as exc:
            warnings.append(f"beam {idx}: export failed ({exc}); skipped")
            return None

    for idx, beam in enumerate(model.get("beams") or []):
        _emit_beam(beam, idx)

    # ── Emit openings (doors and windows) ───────────────────────────────────
    def _emit_opening(o: dict[str, Any], idx: int) -> int | None:
        try:
            kind     = str(o.get("kind") or "window").lower()
            pos      = o.get("position") or [0.0, 0.0, 0.0]
            width    = float(o.get("width")  or 0.9) * _MM_TO_M
            oheight  = float(o.get("height") or 2.1) * _MM_TO_M
            depth    = 0.3  # default frame depth in metres
            level_nm = str(o.get("level") or "")
            name     = str(o.get("name") or f"{kind.capitalize()}_{idx + 1}")

            ox = float(pos[0]) * _MM_TO_M
            oy = float(pos[1]) * _MM_TO_M
            oz = float(pos[2] if len(pos) > 2 else 0) * _MM_TO_M

            storey_id, _ = _resolve_level(level_nm)

            id_prof_ax    = ids.next()
            id_prof       = ids.next()
            id_ext_zdir   = ids.next()
            id_ext_origin = ids.next()
            id_ext_ax     = ids.next()
            id_extrusion  = ids.next()
            id_shape_rep  = ids.next()
            id_prod_shape = ids.next()
            id_elem_orig  = ids.next()
            id_elem_ax    = ids.next()
            id_elem_place = ids.next()
            id_elem       = ids.next()

            entity(id_prof_ax,    "IFCAXIS2PLACEMENT2D($,$)")
            entity(id_prof,       f"IFCRECTANGLEPROFILEDEF(.AREA.,$,#{id_prof_ax},{_f(width)},{_f(depth)})")
            entity(id_ext_zdir,   "IFCDIRECTION((0.,0.,1.))")
            entity(id_ext_origin, "IFCCARTESIANPOINT((0.,0.,0.))")
            entity(id_ext_ax,     f"IFCAXIS2PLACEMENT3D(#{id_ext_origin},#{id_ext_zdir},$)")
            entity(id_extrusion,  f"IFCEXTRUDEDAREASOLID(#{id_prof},#{id_ext_ax},#{id_ext_zdir},{_f(oheight)})")
            entity(id_shape_rep,  f"IFCSHAPEREPRESENTATION(#{id_rep_ctx},'Body','SweptSolid',(#{id_extrusion}))")
            entity(id_prod_shape, f"IFCPRODUCTDEFINITIONSHAPE($,$,(#{id_shape_rep}))")
            entity(id_elem_orig,  f"IFCCARTESIANPOINT(({_f(ox)},{_f(oy)},{_f(oz)}))")
            entity(id_elem_ax,    f"IFCAXIS2PLACEMENT3D(#{id_elem_orig},$,$)")
            entity(id_elem_place, f"IFCLOCALPLACEMENT(#{id_storey_place(storey_id)},#{id_elem_ax})")

            if kind == "door":
                entity(id_elem, (
                    f"IFCDOOR({_s(_ifc_guid(f'door_{idx}'))},"
                    f"#{id_owner_hist},{_s(name)},$,$,"
                    f"#{id_elem_place},#{id_prod_shape},$,"
                    f"{_f(oheight)},{_f(width)})"
                ))
            else:
                entity(id_elem, (
                    f"IFCWINDOW({_s(_ifc_guid(f'window_{idx}'))},"
                    f"#{id_owner_hist},{_s(name)},$,$,"
                    f"#{id_elem_place},#{id_prod_shape},$,"
                    f"{_f(oheight)},{_f(width)})"
                ))

            storey_elements[storey_id].append(id_elem)
            return id_elem
        except Exception as exc:
            warnings.append(f"opening {idx}: export failed ({exc}); skipped")
            return None

    for idx, opening in enumerate(model.get("openings") or []):
        _emit_opening(opening, idx)

    # ── IfcRelContainedInSpatialStructure for each storey ───────────────────
    for storey_id, elem_ids in storey_elements.items():
        if not elem_ids:
            continue
        elem_refs = ",".join(f"#{e}" for e in elem_ids)
        id_rel = ids.next()
        entity(id_rel, (
            f"IFCRELCONTAINEDINSPATIALSTRUCTURE("
            f"{_s(_ifc_guid(f'contained_{storey_id}'))},"
            f"#{id_owner_hist},$,$,({elem_refs}),#{storey_id})"
        ))

    # ── Assemble STEP file ───────────────────────────────────────────────────
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    header = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        f"FILE_DESCRIPTION(('Kerf BIM IFC Export'),'{schema}');\n"
        f"FILE_NAME('{project_name}','{now_str}',('{author}'),"
        f"('{organisation}'),'Kerf BIM Exporter','Kerf BIM','');\n"
        f"FILE_SCHEMA(('{schema}'));\n"
        "ENDSEC;\n"
        "DATA;\n"
    )
    footer = "ENDSEC;\nEND-ISO-10303-21;\n"

    body = "\n".join(lines)
    ifc_text = header + body + "\n" + footer

    # ── Validation ──────────────────────────────────────────────────────────
    _validate(ifc_text, warnings)

    return IFCExportResult(
        ifc_text=ifc_text,
        entity_count=len(lines),
        schema=schema,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REF_RE = re.compile(r"#(\d+)")
_DEF_RE = re.compile(r"^#(\d+)=", re.MULTILINE)


def _validate(ifc_text: str, warnings: list[str]) -> None:
    """
    Minimal syntactic validation of the generated STEP file.

    Checks:
    1. File ends with ENDSEC; END-ISO-10303-21;
    2. All #N forward-references in the DATA section are defined.
    """
    if not ifc_text.rstrip().endswith("END-ISO-10303-21;"):
        warnings.append("VALIDATION: file does not end with END-ISO-10303-21;")

    # Extract DATA section
    data_match = re.search(r"DATA;(.+)ENDSEC;", ifc_text, re.DOTALL)
    if not data_match:
        warnings.append("VALIDATION: DATA section not found")
        return

    data_section = data_match.group(1)

    # All defined IDs
    defined = set(int(m) for m in _DEF_RE.findall(data_section))

    # All referenced IDs (from the values, not the LHS #N=)
    # Strip LHS definitions first to get RHS only
    rhs_text = _DEF_RE.sub("", data_section)
    referenced = set(int(m) for m in _REF_RE.findall(rhs_text))

    missing = referenced - defined
    if missing:
        missing_sample = sorted(missing)[:5]
        warnings.append(
            f"VALIDATION: {len(missing)} undefined #ID references "
            f"(sample: {missing_sample})"
        )
