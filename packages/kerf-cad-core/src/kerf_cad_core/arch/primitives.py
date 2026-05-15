"""
kerf_cad_core.arch.primitives
==============================

Pure-Python parametric data model for architectural BIM primitives.

All dimensions are in **millimetres** throughout — inputs and outputs.

Primitives
----------
  WallLayer   — a single material layer within a composite wall cross-section
  WallSpec    — full wall descriptor (baseline, height, optional layers)
  DoorSpec    — door hosted in a wall
  WindowSpec  — window hosted in a wall (adds sill height)
  SlabSpec    — horizontal slab defined by a polygon outline + thickness
  OpeningSpec — generic rectangular or arched void hosted in a wall

Builder functions
-----------------
  build_wall(...)     -> dict   # parametric recipe + quantity data
  build_door(...)     -> dict
  build_window(...)   -> dict
  build_slab(...)     -> dict
  build_opening(...)  -> dict

Each builder returns a self-contained dict that downstream workers can use to
create geometry.  Builders never raise on invalid input — they return a dict
with ``ok=False`` and an ``errors`` list so the LLM can recover gracefully.

Wall quantities
---------------
  length      = distance(start, end)                            [mm]
  gross_area  = length * height                                 [mm²]
  gross_volume= length * height * total_thickness               [mm³]
  net_volume  = gross_volume − Σ opening_volumes               [mm³]

Slab quantities
---------------
  area        = shoelace formula over outline polygon            [mm²]
  volume      = area * thickness                                 [mm³]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SWING_TYPES = frozenset(
    ["hinged_left", "hinged_right", "double", "sliding", "folding", "pivot"]
)
_VALID_OPERATION_TYPES = frozenset(
    ["fixed", "casement", "sliding", "awning", "hopper", "tilt_turn", "louvre"]
)
_VALID_ARCH_TYPES = frozenset(["rectangular", "arched"])


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class WallLayer:
    """One material layer in a composite wall cross-section.

    Attributes
    ----------
    name : str
        Human-readable material name, e.g. "brick", "insulation", "plaster".
    thickness : float
        Layer thickness in millimetres (must be > 0).
    """
    name: str
    thickness: float  # mm


@dataclass
class WallSpec:
    """Full parametric description of a wall element.

    Attributes
    ----------
    start : tuple[float, float]
        Baseline start point (x, y) in mm (plan view, Z=0 datum).
    end : tuple[float, float]
        Baseline end point (x, y) in mm.
    height : float
        Wall height in mm (must be > 0).
    thickness : float
        Total wall thickness in mm (must be > 0).  If ``layers`` is provided
        this is automatically derived as the sum of layer thicknesses.
    layers : list[WallLayer]
        Optional ordered layers (exterior → interior).  When provided,
        ``thickness`` is the sum of ``layer.thickness`` for each layer.
    id : str
        Optional wall identifier for cross-referencing openings.
    """
    start: tuple[float, float]
    end: tuple[float, float]
    height: float  # mm
    thickness: float  # mm
    layers: list[WallLayer] = field(default_factory=list)
    id: str = ""


@dataclass
class DoorSpec:
    """Parametric door hosted in a wall.

    Attributes
    ----------
    width : float
        Door clear opening width in mm.
    height : float
        Door clear opening height in mm.
    wall_ref : str
        ID of the host wall.
    position_along_wall : float
        Distance from the wall start point to the near edge of the door
        opening, measured along the wall baseline in mm.
    swing : str
        Door operation type: one of "hinged_left", "hinged_right", "double",
        "sliding", "folding", "pivot".
    id : str
        Optional door identifier.
    """
    width: float  # mm
    height: float  # mm
    wall_ref: str
    position_along_wall: float  # mm
    swing: str = "hinged_left"
    id: str = ""


@dataclass
class WindowSpec:
    """Parametric window hosted in a wall.

    Attributes
    ----------
    width : float
        Window clear opening width in mm.
    height : float
        Window clear opening height in mm.
    sill_height : float
        Height of the window sill above the floor level in mm.
    wall_ref : str
        ID of the host wall.
    position_along_wall : float
        Distance from the wall start point to the near edge of the window
        opening, measured along the wall baseline in mm.
    operation : str
        Window operation type: one of "fixed", "casement", "sliding",
        "awning", "hopper", "tilt_turn", "louvre".
    id : str
        Optional window identifier.
    """
    width: float   # mm
    height: float  # mm
    sill_height: float  # mm
    wall_ref: str
    position_along_wall: float  # mm
    operation: str = "casement"
    id: str = ""


@dataclass
class SlabSpec:
    """Parametric horizontal slab.

    Attributes
    ----------
    outline : list[tuple[float, float]]
        Plan-view polygon vertices (x, y) in mm, in order (CW or CCW).
        Must have at least 3 vertices.  The polygon is automatically closed
        (the last edge connects the final vertex back to the first).
    thickness : float
        Slab thickness in mm (must be > 0).
    level : float
        Z-elevation of the slab top surface in mm.
    id : str
        Optional slab identifier.
    """
    outline: list[tuple[float, float]]
    thickness: float  # mm
    level: float = 0.0  # mm, top-of-slab elevation
    id: str = ""


@dataclass
class OpeningSpec:
    """Generic void cut into a wall (used for doors, windows, or bespoke
    openings).

    Attributes
    ----------
    width : float
        Opening width in mm.
    height : float
        Opening height in mm.
    sill_height : float
        Height of the opening's bottom edge above the floor level in mm.
    wall_ref : str
        ID of the host wall.
    position_along_wall : float
        Distance from the wall start point to the near edge of the opening,
        measured along the wall baseline in mm.
    arch_type : str
        "rectangular" (default) or "arched".  Arched openings have a
        semicircular head; the rise is width/2.
    id : str
        Optional opening identifier.
    """
    width: float   # mm
    height: float  # mm
    sill_height: float = 0.0  # mm
    wall_ref: str = ""
    position_along_wall: float = 0.0  # mm
    arch_type: str = "rectangular"
    id: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance between two 2-D points."""
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def _shoelace_area(vertices: list[tuple[float, float]]) -> float:
    """Compute the signed area of a polygon using the shoelace formula.

    Returns the absolute value so both CW and CCW orderings work.
    """
    n = len(vertices)
    total = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _opening_volume(opening: dict, wall_thickness: float) -> float:
    """Compute the cut volume of an opening dict (result of build_opening)."""
    w = opening["width_mm"]
    h = opening["height_mm"]
    arch = opening.get("arch_type", "rectangular")
    if arch == "arched":
        rect_area = w * h
        semi_area = math.pi * (w / 2.0) ** 2 / 2.0
        area = rect_area + semi_area
    else:
        area = w * h
    return area * wall_thickness


# ---------------------------------------------------------------------------
# Builder: Wall
# ---------------------------------------------------------------------------

def build_wall(
    start: tuple[float, float],
    end: tuple[float, float],
    height: float,
    thickness: Optional[float] = None,
    layers: Optional[list[dict]] = None,
    id: str = "",
) -> dict:
    """Build a parametric wall recipe.

    Parameters
    ----------
    start : (x, y)   mm
    end   : (x, y)   mm
    height: float     mm — must be > 0
    thickness: float  mm — required unless layers is provided
    layers: list of {"name": str, "thickness": float} — optional
    id : str — optional wall identifier

    Returns
    -------
    dict with keys:
      ok          : bool
      errors      : list[str]   (empty on success)
      op          : "arch_wall"
      id          : str
      start       : [x, y]
      end         : [x, y]
      height_mm   : float
      thickness_mm: float
      layers      : list[{name, thickness}]
      length_mm   : float
      gross_area_mm2   : float
      gross_volume_mm3 : float
    """
    errors: list[str] = []

    # Validate start / end
    if not (isinstance(start, (list, tuple)) and len(start) == 2):
        errors.append("start must be a 2-element [x, y] coordinate")
    if not (isinstance(end, (list, tuple)) and len(end) == 2):
        errors.append("end must be a 2-element [x, y] coordinate")

    if height is None or not isinstance(height, (int, float)):
        errors.append("height must be a number")
    elif height <= 0:
        errors.append(f"height must be > 0; got {height}")

    # Normalise layers
    parsed_layers: list[WallLayer] = []
    if layers:
        for i, lyr in enumerate(layers):
            if not isinstance(lyr, dict):
                errors.append(f"layers[{i}] must be a dict with 'name' and 'thickness'")
                continue
            lname = str(lyr.get("name", "")).strip()
            lt = lyr.get("thickness")
            if not lname:
                errors.append(f"layers[{i}].name is required")
            if lt is None or not isinstance(lt, (int, float)) or lt <= 0:
                errors.append(f"layers[{i}].thickness must be > 0; got {lt}")
            else:
                parsed_layers.append(WallLayer(name=lname, thickness=float(lt)))

    if parsed_layers:
        derived_thickness = sum(l.thickness for l in parsed_layers)
    else:
        derived_thickness = None

    if thickness is not None:
        if not isinstance(thickness, (int, float)) or thickness <= 0:
            errors.append(f"thickness must be > 0; got {thickness}")
        else:
            # If layers also given, layers win; thickness is informational
            if not parsed_layers:
                derived_thickness = float(thickness)
    else:
        if not parsed_layers:
            errors.append("thickness is required when no layers are provided")

    if errors:
        return {"ok": False, "errors": errors}

    length = _distance(tuple(start), tuple(end))
    gross_area = length * float(height)
    gross_volume = gross_area * derived_thickness

    return {
        "ok": True,
        "errors": [],
        "op": "arch_wall",
        "id": id,
        "start": list(start),
        "end": list(end),
        "height_mm": float(height),
        "thickness_mm": derived_thickness,
        "layers": [{"name": l.name, "thickness_mm": l.thickness} for l in parsed_layers],
        "length_mm": length,
        "gross_area_mm2": gross_area,
        "gross_volume_mm3": gross_volume,
    }


# ---------------------------------------------------------------------------
# Builder: Door
# ---------------------------------------------------------------------------

def build_door(
    width: float,
    height: float,
    wall_ref: str,
    position_along_wall: float,
    wall_length: float,
    wall_height: float,
    wall_thickness: float,
    swing: str = "hinged_left",
    id: str = "",
) -> dict:
    """Build a parametric door recipe.

    Parameters
    ----------
    width              : float  mm — door clear opening width (> 0)
    height             : float  mm — door clear opening height (> 0)
    wall_ref           : str    — id of the host wall
    position_along_wall: float  mm — distance from wall start to near door edge
    wall_length        : float  mm — total wall baseline length
    wall_height        : float  mm — host wall height (for fit validation)
    wall_thickness     : float  mm — host wall thickness (for cut volume)
    swing              : str    — one of _VALID_SWING_TYPES
    id                 : str    — optional door identifier

    Returns
    -------
    dict with keys:
      ok, errors, op, id, wall_ref, width_mm, height_mm, swing,
      position_along_wall_mm, cut_box (width×height×wall_thickness),
      opening_volume_mm3, panel_params
    """
    errors: list[str] = []

    if not isinstance(width, (int, float)) or width <= 0:
        errors.append(f"width must be > 0; got {width}")
    if not isinstance(height, (int, float)) or height <= 0:
        errors.append(f"height must be > 0; got {height}")
    if not wall_ref or not str(wall_ref).strip():
        errors.append("wall_ref is required")
    if not isinstance(position_along_wall, (int, float)) or position_along_wall < 0:
        errors.append(f"position_along_wall must be >= 0; got {position_along_wall}")
    if swing not in _VALID_SWING_TYPES:
        errors.append(
            f"swing '{swing}' is not valid. Use one of: {sorted(_VALID_SWING_TYPES)}"
        )
    if not isinstance(wall_length, (int, float)) or wall_length <= 0:
        errors.append(f"wall_length must be > 0; got {wall_length}")
    if not isinstance(wall_height, (int, float)) or wall_height <= 0:
        errors.append(f"wall_height must be > 0; got {wall_height}")
    if not isinstance(wall_thickness, (int, float)) or wall_thickness <= 0:
        errors.append(f"wall_thickness must be > 0; got {wall_thickness}")

    # Fit validation (only if basic params are valid)
    if not errors:
        far_edge = float(position_along_wall) + float(width)
        if far_edge > float(wall_length):
            errors.append(
                f"Door does not fit: position_along_wall ({position_along_wall}) + "
                f"width ({width}) = {far_edge} > wall_length ({wall_length})"
            )
        if float(height) > float(wall_height):
            errors.append(
                f"Door does not fit: door height ({height}) > wall height ({wall_height})"
            )

    if errors:
        return {"ok": False, "errors": errors}

    opening_volume = float(width) * float(height) * float(wall_thickness)

    return {
        "ok": True,
        "errors": [],
        "op": "arch_door",
        "id": id,
        "wall_ref": str(wall_ref),
        "width_mm": float(width),
        "height_mm": float(height),
        "sill_height_mm": 0.0,
        "swing": swing,
        "position_along_wall_mm": float(position_along_wall),
        "cut_box": {
            "width_mm": float(width),
            "height_mm": float(height),
            "depth_mm": float(wall_thickness),
        },
        "opening_volume_mm3": opening_volume,
        "panel_params": {
            "panel_width_mm": float(width),
            "panel_height_mm": float(height),
            "swing": swing,
        },
    }


# ---------------------------------------------------------------------------
# Builder: Window
# ---------------------------------------------------------------------------

def build_window(
    width: float,
    height: float,
    sill_height: float,
    wall_ref: str,
    position_along_wall: float,
    wall_length: float,
    wall_height: float,
    wall_thickness: float,
    operation: str = "casement",
    id: str = "",
) -> dict:
    """Build a parametric window recipe.

    Parameters
    ----------
    width              : float  mm — window clear opening width (> 0)
    height             : float  mm — window clear opening height (> 0)
    sill_height        : float  mm — sill height above floor (>= 0)
    wall_ref           : str    — id of the host wall
    position_along_wall: float  mm — distance from wall start to near window edge
    wall_length        : float  mm — total wall baseline length
    wall_height        : float  mm — host wall height
    wall_thickness     : float  mm — host wall thickness
    operation          : str    — one of _VALID_OPERATION_TYPES
    id                 : str    — optional window identifier

    Returns
    -------
    dict with keys:
      ok, errors, op, id, wall_ref, width_mm, height_mm, sill_height_mm,
      operation, position_along_wall_mm, cut_box, opening_volume_mm3,
      panel_params, head_height_mm
    """
    errors: list[str] = []

    if not isinstance(width, (int, float)) or width <= 0:
        errors.append(f"width must be > 0; got {width}")
    if not isinstance(height, (int, float)) or height <= 0:
        errors.append(f"height must be > 0; got {height}")
    if not isinstance(sill_height, (int, float)) or sill_height < 0:
        errors.append(f"sill_height must be >= 0; got {sill_height}")
    if not wall_ref or not str(wall_ref).strip():
        errors.append("wall_ref is required")
    if not isinstance(position_along_wall, (int, float)) or position_along_wall < 0:
        errors.append(f"position_along_wall must be >= 0; got {position_along_wall}")
    if operation not in _VALID_OPERATION_TYPES:
        errors.append(
            f"operation '{operation}' is not valid. Use one of: {sorted(_VALID_OPERATION_TYPES)}"
        )
    if not isinstance(wall_length, (int, float)) or wall_length <= 0:
        errors.append(f"wall_length must be > 0; got {wall_length}")
    if not isinstance(wall_height, (int, float)) or wall_height <= 0:
        errors.append(f"wall_height must be > 0; got {wall_height}")
    if not isinstance(wall_thickness, (int, float)) or wall_thickness <= 0:
        errors.append(f"wall_thickness must be > 0; got {wall_thickness}")

    # Fit validation
    if not errors:
        far_edge = float(position_along_wall) + float(width)
        if far_edge > float(wall_length):
            errors.append(
                f"Window does not fit: position_along_wall ({position_along_wall}) + "
                f"width ({width}) = {far_edge} > wall_length ({wall_length})"
            )
        head_height = float(sill_height) + float(height)
        if head_height > float(wall_height):
            errors.append(
                f"Window does not fit: sill_height ({sill_height}) + height ({height}) = "
                f"{head_height} > wall_height ({wall_height})"
            )

    if errors:
        return {"ok": False, "errors": errors}

    opening_volume = float(width) * float(height) * float(wall_thickness)
    head_height = float(sill_height) + float(height)

    return {
        "ok": True,
        "errors": [],
        "op": "arch_window",
        "id": id,
        "wall_ref": str(wall_ref),
        "width_mm": float(width),
        "height_mm": float(height),
        "sill_height_mm": float(sill_height),
        "head_height_mm": head_height,
        "operation": operation,
        "position_along_wall_mm": float(position_along_wall),
        "cut_box": {
            "width_mm": float(width),
            "height_mm": float(height),
            "depth_mm": float(wall_thickness),
            "sill_height_mm": float(sill_height),
        },
        "opening_volume_mm3": opening_volume,
        "panel_params": {
            "panel_width_mm": float(width),
            "panel_height_mm": float(height),
            "sill_height_mm": float(sill_height),
            "operation": operation,
        },
    }


# ---------------------------------------------------------------------------
# Builder: Slab
# ---------------------------------------------------------------------------

def build_slab(
    outline: list,
    thickness: float,
    level: float = 0.0,
    id: str = "",
) -> dict:
    """Build a parametric slab recipe.

    Parameters
    ----------
    outline  : list of [x, y] pairs  mm — polygon vertices (>= 3 points)
    thickness: float  mm — slab thickness (> 0)
    level    : float  mm — Z-elevation of slab top surface (default 0)
    id       : str    — optional slab identifier

    Returns
    -------
    dict with keys:
      ok, errors, op, id, outline, thickness_mm, level_mm,
      area_mm2, volume_mm3
    """
    errors: list[str] = []

    if not isinstance(outline, (list, tuple)) or len(outline) < 3:
        errors.append("outline must have at least 3 vertices")
    else:
        for i, pt in enumerate(outline):
            if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
                errors.append(f"outline[{i}] must be a 2-element [x, y] pair")

    if not isinstance(thickness, (int, float)) or thickness <= 0:
        errors.append(f"thickness must be > 0; got {thickness}")

    if not isinstance(level, (int, float)):
        errors.append(f"level must be a number; got {level}")

    if errors:
        return {"ok": False, "errors": errors}

    verts = [(float(p[0]), float(p[1])) for p in outline]
    area = _shoelace_area(verts)
    volume = area * float(thickness)

    return {
        "ok": True,
        "errors": [],
        "op": "arch_slab",
        "id": id,
        "outline": [[v[0], v[1]] for v in verts],
        "thickness_mm": float(thickness),
        "level_mm": float(level),
        "area_mm2": area,
        "volume_mm3": volume,
    }


# ---------------------------------------------------------------------------
# Builder: Opening
# ---------------------------------------------------------------------------

def build_opening(
    width: float,
    height: float,
    wall_ref: str,
    position_along_wall: float,
    wall_length: float,
    wall_height: float,
    wall_thickness: float,
    sill_height: float = 0.0,
    arch_type: str = "rectangular",
    id: str = "",
) -> dict:
    """Build a parametric generic opening (void cut) recipe.

    Parameters
    ----------
    width              : float  mm — opening width (> 0)
    height             : float  mm — opening height, measured to the top of
                                     the rectangular portion (> 0)
    wall_ref           : str    — id of the host wall
    position_along_wall: float  mm — distance from wall start to near edge
    wall_length        : float  mm — total wall baseline length
    wall_height        : float  mm — host wall height
    wall_thickness     : float  mm — host wall thickness
    sill_height        : float  mm — bottom of opening above floor (>= 0)
    arch_type          : str    — "rectangular" or "arched"
    id                 : str    — optional opening identifier

    Returns
    -------
    dict with keys:
      ok, errors, op, id, wall_ref, width_mm, height_mm, sill_height_mm,
      arch_type, position_along_wall_mm, cut_params, opening_volume_mm3
    """
    errors: list[str] = []

    if not isinstance(width, (int, float)) or width <= 0:
        errors.append(f"width must be > 0; got {width}")
    if not isinstance(height, (int, float)) or height <= 0:
        errors.append(f"height must be > 0; got {height}")
    if not isinstance(sill_height, (int, float)) or sill_height < 0:
        errors.append(f"sill_height must be >= 0; got {sill_height}")
    if not wall_ref or not str(wall_ref).strip():
        errors.append("wall_ref is required")
    if not isinstance(position_along_wall, (int, float)) or position_along_wall < 0:
        errors.append(f"position_along_wall must be >= 0; got {position_along_wall}")
    if arch_type not in _VALID_ARCH_TYPES:
        errors.append(
            f"arch_type '{arch_type}' is not valid. Use one of: {sorted(_VALID_ARCH_TYPES)}"
        )
    if not isinstance(wall_length, (int, float)) or wall_length <= 0:
        errors.append(f"wall_length must be > 0; got {wall_length}")
    if not isinstance(wall_height, (int, float)) or wall_height <= 0:
        errors.append(f"wall_height must be > 0; got {wall_height}")
    if not isinstance(wall_thickness, (int, float)) or wall_thickness <= 0:
        errors.append(f"wall_thickness must be > 0; got {wall_thickness}")

    if not errors:
        far_edge = float(position_along_wall) + float(width)
        if far_edge > float(wall_length):
            errors.append(
                f"Opening does not fit: position_along_wall ({position_along_wall}) + "
                f"width ({width}) = {far_edge} > wall_length ({wall_length})"
            )
        if arch_type == "arched":
            # Total height including arch rise = height + radius = height + width/2
            total_height = float(height) + float(width) / 2.0
        else:
            total_height = float(height)
        head_height = float(sill_height) + total_height
        if head_height > float(wall_height):
            errors.append(
                f"Opening does not fit: sill_height ({sill_height}) + "
                f"total_height ({total_height:.1f}) = {head_height:.1f} > "
                f"wall_height ({wall_height})"
            )

    if errors:
        return {"ok": False, "errors": errors}

    # Compute opening cross-section area
    if arch_type == "arched":
        rect_area = float(width) * float(height)
        semi_area = math.pi * (float(width) / 2.0) ** 2 / 2.0
        opening_area = rect_area + semi_area
        arch_rise_mm = float(width) / 2.0
    else:
        opening_area = float(width) * float(height)
        arch_rise_mm = 0.0

    opening_volume = opening_area * float(wall_thickness)

    return {
        "ok": True,
        "errors": [],
        "op": "arch_opening",
        "id": id,
        "wall_ref": str(wall_ref),
        "width_mm": float(width),
        "height_mm": float(height),
        "sill_height_mm": float(sill_height),
        "arch_type": arch_type,
        "arch_rise_mm": arch_rise_mm,
        "position_along_wall_mm": float(position_along_wall),
        "cut_params": {
            "width_mm": float(width),
            "height_mm": float(height),
            "sill_height_mm": float(sill_height),
            "arch_type": arch_type,
            "arch_rise_mm": arch_rise_mm,
            "depth_mm": float(wall_thickness),
        },
        "opening_volume_mm3": opening_volume,
    }


# ---------------------------------------------------------------------------
# Compose: wall_with_openings  (used by arch_wall_with_openings tool)
# ---------------------------------------------------------------------------

def compose_wall_with_openings(
    wall: dict,
    openings: list[dict],
) -> dict:
    """Subtract opening volumes from a wall recipe.

    Parameters
    ----------
    wall     : dict  — output of build_wall (must have ok=True)
    openings : list  — outputs of build_door / build_window / build_opening

    Returns
    -------
    dict with keys:
      ok, errors, wall, openings, net_volume_mm3
    """
    if not wall.get("ok"):
        return {
            "ok": False,
            "errors": ["wall recipe is invalid: " + "; ".join(wall.get("errors", []))],
            "wall": wall,
            "openings": openings,
        }

    errors: list[str] = []
    valid_openings: list[dict] = []

    for i, op in enumerate(openings):
        if not isinstance(op, dict):
            errors.append(f"openings[{i}] is not a dict")
            continue
        if not op.get("ok"):
            for e in op.get("errors", []):
                errors.append(f"openings[{i}]: {e}")
            continue
        valid_openings.append(op)

    if errors:
        return {
            "ok": False,
            "errors": errors,
            "wall": wall,
            "openings": openings,
        }

    total_opening_volume = sum(o.get("opening_volume_mm3", 0.0) for o in valid_openings)
    gross_volume = wall["gross_volume_mm3"]
    net_volume = gross_volume - total_opening_volume

    return {
        "ok": True,
        "errors": [],
        "wall": wall,
        "openings": valid_openings,
        "gross_volume_mm3": gross_volume,
        "total_opening_volume_mm3": total_opening_volume,
        "net_volume_mm3": net_volume,
    }
