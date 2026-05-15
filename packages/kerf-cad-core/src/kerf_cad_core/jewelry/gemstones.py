"""
Parametric gemstone solid generator.

Supported cuts
--------------
round_brilliant  57/58 facets — the GIA standard.
princess         Square modified brilliant (4-fold symmetry).
oval             Elliptical modified brilliant.
emerald          Rectangular step cut.
marquise         Boat-shaped modified brilliant.
pear             Teardrop modified brilliant.
cushion          Square/rectangular cushion modified brilliant.

Each cut is described by a *proportions dict* whose keys follow GIA/AGS
conventions (all linear dimensions as mm, angles in degrees).

Carat ↔ mm formulae
--------------------
These are empirical diamond weight approximations used industry-wide.

Round brilliant (1 ct ≈ 6.5 mm diameter):
    carat = (diameter_mm / 6.5) ** 3

    Derivation: density of diamond ≈ 3.51 g/cm³; a brilliant approximates a
    flattened cylinder.  The cube exponent captures the volume scaling.
    Inversion: diameter_mm = 6.5 * carat**(1/3)

Other cuts use an equivalent-diameter conversion via their aspect ratio
relative to round brilliant.  E.g. a 1 ct princess ≈ 5.5 mm side length.

Industry reference proportions
-------------------------------
Round brilliant (ideal / "Tolkowsky"):
    table_pct        : 53–58 %   (table width / girdle diameter)
    crown_angle_deg  : 34.5°
    pavilion_angle_deg: 40.75°
    girdle_pct       : 2.5 % (thin-medium girdle thickness / diameter)
    total_depth_pct  : 61–62 %

Princess:
    table_pct: 75 %, crown_angle_deg: 30°, pavilion_angle_deg: 42°,
    pavilion_depth_pct: 43 %, total_depth_pct: 68 %

Emerald:
    table_pct: 60 %, crown_angle_deg: 15°, step_rows: 3,
    total_depth_pct: 60 %, corner_cut_ratio: 0.15

LLM-facing tools
----------------
  jewelry_create_gemstone  — appends a gemstone node to a .feature file
"""

from __future__ import annotations

import json
import uuid
from typing import Optional, NamedTuple

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    read_feature_content,
    append_feature_node,
    next_node_id,
)


# ---------------------------------------------------------------------------
# Cut registry
# ---------------------------------------------------------------------------

GEMSTONE_CUTS = {
    "round_brilliant",
    "princess",
    "oval",
    "emerald",
    "marquise",
    "pear",
    "cushion",
}


# ---------------------------------------------------------------------------
# Carat ↔ mm sizing
# ---------------------------------------------------------------------------

# Exponent k for: carat = (dim_mm / ref_mm) ** k
# ref_mm = diameter at 1 carat; k = 3 for a cubic scaling approximation.

_CARAT_REF: dict[str, tuple[float, float]] = {
    # (ref_diameter_mm, exponent)
    "round_brilliant": (6.5, 3.0),
    "princess":        (5.5, 3.0),   # side length
    "oval":            (7.7, 3.0),   # long axis
    "emerald":         (7.0, 3.0),   # long axis
    "marquise":        (10.0, 3.0),  # long axis
    "pear":            (8.0, 3.0),   # long axis
    "cushion":         (5.5, 3.0),   # side length
}


def carat_from_mm(cut: str, dim_mm: float) -> float:
    """Return estimated carat weight from the primary dimension in mm.

    For round_brilliant, dim_mm is the girdle diameter.
    For all other cuts, dim_mm is the long-axis length.

    Formula: carat = (dim_mm / ref_mm) ** exponent
    where ref_mm is the ~1-carat dimension for that cut.
    """
    if cut not in _CARAT_REF:
        raise ValueError(f"Unknown cut: {cut!r}")
    if dim_mm <= 0:
        raise ValueError("dim_mm must be positive")
    ref_mm, exp = _CARAT_REF[cut]
    return (dim_mm / ref_mm) ** exp


def mm_from_carat(cut: str, carat: float) -> float:
    """Return the primary dimension in mm for a given carat weight.

    Inverse of carat_from_mm:
        dim_mm = ref_mm * carat ** (1 / exponent)
    """
    if cut not in _CARAT_REF:
        raise ValueError(f"Unknown cut: {cut!r}")
    if carat <= 0:
        raise ValueError("carat must be positive")
    ref_mm, exp = _CARAT_REF[cut]
    return ref_mm * (carat ** (1.0 / exp))


# ---------------------------------------------------------------------------
# Industry-standard default proportions per cut
# ---------------------------------------------------------------------------

class GemProportions(NamedTuple):
    """All dimensions in mm (relative to the girdle diameter = 1 when normalised).
    Angles in degrees.
    """
    cut: str
    # Primary sizing
    diameter_mm: float          # girdle diameter (round) or long-axis (others)
    aspect_ratio: float         # width / long-axis  (1.0 for round/square)
    # Crown
    table_pct: float            # table width / girdle diameter, percent
    crown_angle_deg: float
    crown_height_pct: float     # crown height / diameter, percent
    # Pavilion
    pavilion_angle_deg: float
    pavilion_depth_pct: float   # pavilion depth / diameter, percent
    # Girdle
    girdle_pct: float           # girdle thickness / diameter, percent
    # Derived
    total_depth_pct: float      # crown + girdle + pavilion
    # Cut-specific extras
    extras: dict


def gemstone_proportions(
    cut: str,
    diameter_mm: Optional[float] = None,
    carat: Optional[float] = None,
    *,
    # Optional overrides (None = use industry default)
    table_pct: Optional[float] = None,
    crown_angle_deg: Optional[float] = None,
    pavilion_angle_deg: Optional[float] = None,
    girdle_pct: Optional[float] = None,
    aspect_ratio: Optional[float] = None,
) -> GemProportions:
    """Return a GemProportions for the given cut + sizing.

    Exactly one of diameter_mm or carat must be provided.
    """
    if cut not in GEMSTONE_CUTS:
        raise ValueError(f"Unknown cut {cut!r}. Valid: {sorted(GEMSTONE_CUTS)}")

    # Resolve sizing
    if diameter_mm is not None and carat is not None:
        raise ValueError("Provide diameter_mm OR carat, not both")
    if diameter_mm is None and carat is None:
        raise ValueError("One of diameter_mm or carat is required")
    if carat is not None:
        if carat <= 0:
            raise ValueError("carat must be positive")
        diameter_mm = mm_from_carat(cut, carat)
    if diameter_mm <= 0:
        raise ValueError("diameter_mm must be positive")

    # Industry defaults per cut
    _defaults = _CUT_DEFAULTS[cut]

    ta_pct    = table_pct         if table_pct         is not None else _defaults["table_pct"]
    ca_deg    = crown_angle_deg   if crown_angle_deg    is not None else _defaults["crown_angle_deg"]
    pa_deg    = pavilion_angle_deg if pavilion_angle_deg is not None else _defaults["pavilion_angle_deg"]
    gi_pct    = girdle_pct        if girdle_pct         is not None else _defaults["girdle_pct"]
    ar        = aspect_ratio      if aspect_ratio        is not None else _defaults.get("aspect_ratio", 1.0)

    # Compute derived heights (fraction of diameter)
    import math
    # crown_height = (diameter/2 * (1 - table_fraction)) * tan(crown_angle)
    # simplified to the standard parameterisation
    table_fraction = ta_pct / 100.0
    crown_h_pct = _defaults.get("crown_height_pct") or (
        (1 - table_fraction) / 2 * math.tan(math.radians(ca_deg)) * 100
    )
    pav_d_pct = _defaults.get("pavilion_depth_pct") or (
        0.5 * math.tan(math.radians(pa_deg)) * 100
    )
    gi_mm_pct = gi_pct
    total = crown_h_pct + gi_mm_pct + pav_d_pct

    return GemProportions(
        cut=cut,
        diameter_mm=diameter_mm,
        aspect_ratio=ar,
        table_pct=ta_pct,
        crown_angle_deg=ca_deg,
        crown_height_pct=crown_h_pct,
        pavilion_angle_deg=pa_deg,
        pavilion_depth_pct=pav_d_pct,
        girdle_pct=gi_mm_pct,
        total_depth_pct=total,
        extras=dict(_defaults.get("extras", {})),
    )


# Industry-standard defaults
_CUT_DEFAULTS: dict[str, dict] = {
    "round_brilliant": {
        "table_pct": 57.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 16.2,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.1,
        "girdle_pct": 2.5,
        "aspect_ratio": 1.0,
        "extras": {"facet_count": 57, "culet": "none"},
    },
    "princess": {
        "table_pct": 75.0,
        "crown_angle_deg": 30.0,
        "crown_height_pct": 10.5,
        "pavilion_angle_deg": 42.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {"facet_count": 57},
    },
    "oval": {
        "table_pct": 56.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.66,       # width = 0.66 × length (typical 1.35:1 L:W)
        "extras": {"facet_count": 57},
    },
    "emerald": {
        "table_pct": 60.0,
        "crown_angle_deg": 15.0,
        "crown_height_pct": 8.0,
        "pavilion_angle_deg": 45.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 0.71,       # width = 0.71 × length (standard ~1.4:1)
        "extras": {"step_rows": 3, "corner_cut_ratio": 0.15},
    },
    "marquise": {
        "table_pct": 56.0,
        "crown_angle_deg": 33.5,
        "crown_height_pct": 14.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.50,       # width = 0.50 × length (~2:1 L:W)
        "extras": {"facet_count": 57},
    },
    "pear": {
        "table_pct": 55.0,
        "crown_angle_deg": 35.0,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.5,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.62,       # width = 0.62 × length
        "extras": {"facet_count": 57},
    },
    "cushion": {
        "table_pct": 60.0,
        "crown_angle_deg": 35.0,
        "crown_height_pct": 14.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.5,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {"corner_radius_pct": 15},  # corner radius as % of side
    },
}


# ---------------------------------------------------------------------------
# Feature node helpers
# ---------------------------------------------------------------------------

def _gemstone_node(
    node_id: str,
    cut: str,
    diameter_mm: float,
    props: GemProportions,
    position: Optional[list] = None,
    orientation_deg: Optional[list] = None,
    material: str = "diamond",
) -> dict:
    """Build the JSON feature node for a gemstone."""
    node: dict = {
        "id": node_id,
        "op": "gemstone",
        "cut": cut,
        "diameter_mm": diameter_mm,
        "aspect_ratio": props.aspect_ratio,
        "table_pct": props.table_pct,
        "crown_angle_deg": props.crown_angle_deg,
        "crown_height_pct": props.crown_height_pct,
        "pavilion_angle_deg": props.pavilion_angle_deg,
        "pavilion_depth_pct": props.pavilion_depth_pct,
        "girdle_pct": props.girdle_pct,
        "total_depth_pct": props.total_depth_pct,
        "material": material,
    }
    if props.extras:
        node["extras"] = props.extras
    if position is not None:
        node["position"] = position
    if orientation_deg is not None:
        node["orientation_deg"] = orientation_deg
    return node


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_gemstone
# ---------------------------------------------------------------------------

jewelry_create_gemstone_spec = ToolSpec(
    name="jewelry_create_gemstone",
    description=(
        "Append a `gemstone` node to a `.feature` file. "
        "Generates a parametric gemstone solid with industry-standard proportions. "
        "Supported cuts: round_brilliant, princess, oval, emerald, marquise, pear, cushion. "
        "Size the stone by carat OR by diameter_mm (long axis for non-round cuts). "
        "Carat formula: carat = (diameter_mm / ref_mm)^3 where ref_mm is ~6.5 for "
        "round brilliant at 1 ct. The gemstone node stores proportions used by the OCCT "
        "worker to build a closed solid (pavilion cone + girdle cylinder + crown prism). "
        "Use jewelry_cut_gem_seat to cut the matching seat from a ring shank or bezel."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "cut": {
                "type": "string",
                "enum": sorted(GEMSTONE_CUTS),
                "description": (
                    "Gemstone cut style. "
                    "round_brilliant=57 facets, princess=square, oval=elliptical, "
                    "emerald=step cut, marquise=boat, pear=teardrop, cushion=soft square."
                ),
            },
            "carat": {
                "type": "number",
                "description": (
                    "Stone weight in carats. Converted to mm via the carat formula. "
                    "Provide carat OR diameter_mm, not both."
                ),
            },
            "diameter_mm": {
                "type": "number",
                "description": (
                    "Primary dimension in mm: girdle diameter (round brilliant) or "
                    "long axis (all other cuts). Provide diameter_mm OR carat, not both."
                ),
            },
            "material": {
                "type": "string",
                "description": "Stone material label, e.g. 'diamond', 'ruby', 'sapphire'. Default: 'diamond'.",
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] placement in model space (mm). Default: [0, 0, 0].",
            },
            "orientation_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[rx, ry, rz] Euler angles in degrees. Default: [0, 0, 0].",
            },
            "table_pct": {"type": "number", "description": "Table width override (% of diameter). Optional."},
            "crown_angle_deg": {"type": "number", "description": "Crown angle override (degrees). Optional."},
            "pavilion_angle_deg": {"type": "number", "description": "Pavilion angle override (degrees). Optional."},
            "girdle_pct": {"type": "number", "description": "Girdle thickness override (% of diameter). Optional."},
            "aspect_ratio": {
                "type": "number",
                "description": "Width/length ratio override. 1.0=square/round. Default per cut.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "cut"],
    },
)


@register(jewelry_create_gemstone_spec, write=True)
async def run_jewelry_create_gemstone(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str     = a.get("file_id", "").strip()
    cut             = a.get("cut", "").strip()
    carat           = a.get("carat", None)
    diameter_mm     = a.get("diameter_mm", None)
    material        = a.get("material", "diamond")
    position        = a.get("position", None)
    orientation_deg = a.get("orientation_deg", None)
    node_id         = a.get("id", "").strip()

    prop_overrides = {
        k: a.get(k)
        for k in ("table_pct", "crown_angle_deg", "pavilion_angle_deg", "girdle_pct", "aspect_ratio")
        if a.get(k) is not None
    }

    # Validate required fields
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    if cut not in GEMSTONE_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid cuts: {sorted(GEMSTONE_CUTS)}", "BAD_ARGS"
        )

    if carat is not None and diameter_mm is not None:
        return err_payload("Provide carat OR diameter_mm, not both", "BAD_ARGS")
    if carat is None and diameter_mm is None:
        return err_payload("One of carat or diameter_mm is required", "BAD_ARGS")

    if carat is not None:
        try:
            carat = float(carat)
        except Exception:
            return err_payload("carat must be a number", "BAD_ARGS")
        if carat <= 0:
            return err_payload("carat must be positive", "BAD_ARGS")

    if diameter_mm is not None:
        try:
            diameter_mm = float(diameter_mm)
        except Exception:
            return err_payload("diameter_mm must be a number", "BAD_ARGS")
        if diameter_mm <= 0:
            return err_payload("diameter_mm must be positive", "BAD_ARGS")

    # Validate numeric overrides
    for key in ("table_pct", "crown_angle_deg", "pavilion_angle_deg", "girdle_pct"):
        val = prop_overrides.get(key)
        if val is not None:
            try:
                prop_overrides[key] = float(val)
            except Exception:
                return err_payload(f"{key} must be a number", "BAD_ARGS")
            if prop_overrides[key] <= 0:
                return err_payload(f"{key} must be positive", "BAD_ARGS")

    ar = prop_overrides.get("aspect_ratio")
    if ar is not None:
        try:
            prop_overrides["aspect_ratio"] = float(ar)
        except Exception:
            return err_payload("aspect_ratio must be a number", "BAD_ARGS")
        if prop_overrides["aspect_ratio"] <= 0:
            return err_payload("aspect_ratio must be positive", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    # Resolve proportions
    try:
        props = gemstone_proportions(
            cut,
            diameter_mm=diameter_mm,
            carat=carat,
            **prop_overrides,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    if not node_id:
        node_id = next_node_id(content, "gemstone")

    node = _gemstone_node(
        node_id,
        cut,
        props.diameter_mm,
        props,
        position=position,
        orientation_deg=orientation_deg,
        material=str(material) if material else "diamond",
    )

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "gemstone",
        "cut": cut,
        "diameter_mm": props.diameter_mm,
        "carat_approx": round(carat_from_mm(cut, props.diameter_mm), 3),
        "total_depth_mm": round(props.total_depth_pct / 100 * props.diameter_mm, 3),
    })
