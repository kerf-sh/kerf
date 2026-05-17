"""
kerf_bim.family.library.windows
=================================

Pre-populated parametric window families for the BIM family library.

Families:
    single_hung        — lower sash slides up
    double_hung        — both sashes slide vertically
    casement           — side-hinged outward-opening sash
    awning             — top-hinged outward-opening sash
    fixed              — non-operable fixed-light
    sliding            — horizontal sliding sash(es)
    picture            — large fixed lite, typically floor-to-ceiling
    bay                — three-panel angled bay projection
    bow                — multi-panel curved bow projection

All dimensions in mm.
"""
from __future__ import annotations

from kerf_bim.family.family import (
    FamilyDefinition,
    FamilyType,
    Parameter,
    make_family,
    make_type,
)

__all__ = [
    "single_hung",
    "double_hung",
    "casement",
    "awning",
    "fixed",
    "sliding",
    "picture",
    "bay",
    "bow",
    "ALL_WINDOW_FAMILIES",
]


# ---------------------------------------------------------------------------
# single_hung
# ---------------------------------------------------------------------------

single_hung: FamilyDefinition = make_family(
    name="Single Hung Window",
    category="Window",
    type_parameters=[
        Parameter("width",            "length", default=762.0,  description="Rough opening width (mm)"),
        Parameter("height",           "length", default=1066.8, description="Rough opening height (mm)"),
        Parameter("frame_depth",      "length", default=89.0,   description="Frame depth / wall thickness (mm)"),
        Parameter("glazing",          "string", default="double",
                  description="Glazing: single/double/triple"),
        Parameter("grille_pattern",   "string", default="none",
                  description="Grille pattern: none/colonial/prairie"),
    ],
    instance_parameters=[
        Parameter("frame_material",  "material", default="vinyl",   description="Frame material id"),
        Parameter("sill_material",   "material", default="pine",    description="Sill material id"),
        Parameter("egress",          "boolean",  default=False,     description="Egress-compliant opening"),
    ],
    description="Single hung window — lower sash slides vertically.",
)

_sh_types: list[FamilyType] = [
    make_type(single_hung, "2-0 × 3-0",   {"width": 609.6,  "height":  914.4}),
    make_type(single_hung, "2-0 × 4-0",   {"width": 609.6,  "height": 1219.2}),
    make_type(single_hung, "3-0 × 4-0",   {"width": 914.4,  "height": 1219.2}),
    make_type(single_hung, "3-0 × 5-0",   {"width": 914.4,  "height": 1524.0}),
    make_type(single_hung, "600 × 900",    {"width": 600.0,  "height":  900.0}),
    make_type(single_hung, "600 × 1200",   {"width": 600.0,  "height": 1200.0}),
    make_type(single_hung, "900 × 1200",   {"width": 900.0,  "height": 1200.0}),
    make_type(single_hung, "900 × 1500",   {"width": 900.0,  "height": 1500.0}),
]
single_hung._library_types = _sh_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# double_hung
# ---------------------------------------------------------------------------

double_hung: FamilyDefinition = make_family(
    name="Double Hung Window",
    category="Window",
    type_parameters=[
        Parameter("width",          "length", default=762.0,  description="Rough opening width (mm)"),
        Parameter("height",         "length", default=1066.8, description="Rough opening height (mm)"),
        Parameter("frame_depth",    "length", default=89.0,   description="Frame depth (mm)"),
        Parameter("glazing",        "string", default="double",
                  description="Glazing unit type: single/double/triple"),
        Parameter("grille_pattern", "string", default="none",
                  description="Grille pattern: none/colonial/prairie"),
        Parameter("tilt_in",        "boolean", default=True,  description="Tilt-in sashes for cleaning"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="vinyl",  description="Frame material id"),
        Parameter("egress",         "boolean",  default=False,    description="Egress-compliant opening"),
    ],
    description="Double hung window — both sashes operable.",
)

_dh_types: list[FamilyType] = [
    make_type(double_hung, "2-0 × 3-0",  {"width": 609.6,  "height":  914.4}),
    make_type(double_hung, "2-0 × 4-0",  {"width": 609.6,  "height": 1219.2}),
    make_type(double_hung, "3-0 × 4-0",  {"width": 914.4,  "height": 1219.2}),
    make_type(double_hung, "3-0 × 5-0",  {"width": 914.4,  "height": 1524.0}),
    make_type(double_hung, "4-0 × 5-0",  {"width": 1219.2, "height": 1524.0}),
    make_type(double_hung, "600 × 900",   {"width": 600.0,  "height":  900.0}),
    make_type(double_hung, "900 × 1200",  {"width": 900.0,  "height": 1200.0}),
    make_type(double_hung, "1200 × 1500", {"width": 1200.0, "height": 1500.0}),
]
double_hung._library_types = _dh_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# casement
# ---------------------------------------------------------------------------

casement: FamilyDefinition = make_family(
    name="Casement Window",
    category="Window",
    type_parameters=[
        Parameter("width",       "length",  default=609.6,  description="Rough opening width (mm)"),
        Parameter("height",      "length",  default=1066.8, description="Rough opening height (mm)"),
        Parameter("frame_depth", "length",  default=89.0,   description="Frame depth (mm)"),
        Parameter("hinge_side",  "string",  default="left", description="Hinge side: left/right"),
        Parameter("glazing",     "string",  default="double", description="Glazing type"),
        Parameter("screen",      "boolean", default=True,   description="Include insect screen"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="vinyl", description="Frame material id"),
        Parameter("hardware",       "string",   default="crank", description="Hardware: crank/lever"),
    ],
    description="Side-hinged casement window, outswing.",
)

_ca_types: list[FamilyType] = [
    make_type(casement, "1-6 × 3-0",  {"width": 457.2,  "height":  914.4}),
    make_type(casement, "2-0 × 3-0",  {"width": 609.6,  "height":  914.4}),
    make_type(casement, "2-0 × 4-0",  {"width": 609.6,  "height": 1219.2}),
    make_type(casement, "2-4 × 4-0",  {"width": 711.2,  "height": 1219.2}),
    make_type(casement, "2-4 × 5-0",  {"width": 711.2,  "height": 1524.0}),
    make_type(casement, "450 × 900",   {"width": 450.0,  "height":  900.0}),
    make_type(casement, "600 × 1200",  {"width": 600.0,  "height": 1200.0}),
    make_type(casement, "600 × 1500",  {"width": 600.0,  "height": 1500.0}),
]
casement._library_types = _ca_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# awning
# ---------------------------------------------------------------------------

awning: FamilyDefinition = make_family(
    name="Awning Window",
    category="Window",
    type_parameters=[
        Parameter("width",       "length", default=762.0, description="Rough opening width (mm)"),
        Parameter("height",      "length", default=457.2, description="Rough opening height (mm)"),
        Parameter("frame_depth", "length", default=89.0,  description="Frame depth (mm)"),
        Parameter("glazing",     "string", default="double", description="Glazing type"),
        Parameter("screen",      "boolean", default=True, description="Include insect screen"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="aluminum", description="Frame material id"),
        Parameter("hardware",       "string",   default="crank",    description="Hardware type"),
    ],
    description="Top-hinged awning window, outswing.",
)

_aw_types: list[FamilyType] = [
    make_type(awning, "2-0 × 1-6",  {"width": 609.6,  "height": 457.2}),
    make_type(awning, "3-0 × 1-6",  {"width": 914.4,  "height": 457.2}),
    make_type(awning, "4-0 × 2-0",  {"width": 1219.2, "height": 609.6}),
    make_type(awning, "600 × 400",   {"width": 600.0,  "height": 400.0}),
    make_type(awning, "900 × 600",   {"width": 900.0,  "height": 600.0}),
    make_type(awning, "1200 × 600",  {"width": 1200.0, "height": 600.0}),
]
awning._library_types = _aw_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# fixed
# ---------------------------------------------------------------------------

fixed: FamilyDefinition = make_family(
    name="Fixed Window",
    category="Window",
    type_parameters=[
        Parameter("width",       "length", default=1219.2, description="Rough opening width (mm)"),
        Parameter("height",      "length", default=1524.0, description="Rough opening height (mm)"),
        Parameter("frame_depth", "length", default=89.0,   description="Frame depth (mm)"),
        Parameter("glazing",     "string", default="double", description="Glazing type"),
        Parameter("shape",       "string", default="rectangular",
                  description="Shape: rectangular/arched/circular"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="vinyl", description="Frame material id"),
        Parameter("spandrel",       "boolean",  default=False,   description="Spandrel/opaque panel"),
    ],
    description="Non-operable fixed light window.",
)

_fx_types: list[FamilyType] = [
    make_type(fixed, "2-0 × 2-0",   {"width": 609.6,  "height":  609.6}),
    make_type(fixed, "3-0 × 3-0",   {"width": 914.4,  "height":  914.4}),
    make_type(fixed, "4-0 × 4-0",   {"width": 1219.2, "height": 1219.2}),
    make_type(fixed, "4-0 × 5-0",   {"width": 1219.2, "height": 1524.0}),
    make_type(fixed, "6-0 × 4-0",   {"width": 1828.8, "height": 1219.2}),
    make_type(fixed, "900 × 1200",   {"width": 900.0,  "height": 1200.0}),
    make_type(fixed, "1200 × 1200",  {"width": 1200.0, "height": 1200.0}),
    make_type(fixed, "1800 × 1200",  {"width": 1800.0, "height": 1200.0}),
]
fixed._library_types = _fx_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# sliding
# ---------------------------------------------------------------------------

sliding: FamilyDefinition = make_family(
    name="Sliding Window",
    category="Window",
    type_parameters=[
        Parameter("width",       "length",  default=1219.2, description="Rough opening width (mm)"),
        Parameter("height",      "length",  default=914.4,  description="Rough opening height (mm)"),
        Parameter("frame_depth", "length",  default=89.0,   description="Frame depth (mm)"),
        Parameter("panel_count", "integer", default=2,      description="Number of panels (2 or 3)"),
        Parameter("glazing",     "string",  default="double", description="Glazing type"),
        Parameter("screen",      "boolean", default=True,   description="Include insect screen"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="aluminum", description="Frame material id"),
    ],
    description="Horizontal sliding sash window.",
)

_sl_types: list[FamilyType] = [
    make_type(sliding, "3-0 × 3-0",  {"width": 914.4,  "height":  914.4}),
    make_type(sliding, "4-0 × 3-0",  {"width": 1219.2, "height":  914.4}),
    make_type(sliding, "5-0 × 3-0",  {"width": 1524.0, "height":  914.4}),
    make_type(sliding, "6-0 × 4-0",  {"width": 1828.8, "height": 1219.2}),
    make_type(sliding, "1200 × 900",  {"width": 1200.0, "height":  900.0}),
    make_type(sliding, "1500 × 1200", {"width": 1500.0, "height": 1200.0}),
    make_type(sliding, "1800 × 1200", {"width": 1800.0, "height": 1200.0}),
]
sliding._library_types = _sl_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# picture
# ---------------------------------------------------------------------------

picture: FamilyDefinition = make_family(
    name="Picture Window",
    category="Window",
    type_parameters=[
        Parameter("width",       "length", default=1828.8, description="Rough opening width (mm)"),
        Parameter("height",      "length", default=1524.0, description="Rough opening height (mm)"),
        Parameter("frame_depth", "length", default=89.0,   description="Frame depth (mm)"),
        Parameter("glazing",     "string", default="double", description="Glazing type"),
        Parameter("low_e",       "boolean", default=True,  description="Low-E coating"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="wood_clad",  description="Frame material id"),
        Parameter("sash_divided",   "boolean",  default=False,        description="Divided-light appearance"),
    ],
    description="Large fixed-light picture window, typically floor-to-ceiling or oversized.",
)

_pic_types: list[FamilyType] = [
    make_type(picture, "4-0 × 4-0",  {"width": 1219.2, "height": 1219.2}),
    make_type(picture, "6-0 × 4-0",  {"width": 1828.8, "height": 1219.2}),
    make_type(picture, "6-0 × 5-0",  {"width": 1828.8, "height": 1524.0}),
    make_type(picture, "8-0 × 5-0",  {"width": 2438.4, "height": 1524.0}),
    make_type(picture, "1500 × 1200", {"width": 1500.0, "height": 1200.0}),
    make_type(picture, "2000 × 1500", {"width": 2000.0, "height": 1500.0}),
    make_type(picture, "2400 × 1800", {"width": 2400.0, "height": 1800.0}),
]
picture._library_types = _pic_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# bay
# ---------------------------------------------------------------------------

bay: FamilyDefinition = make_family(
    name="Bay Window",
    category="Window",
    type_parameters=[
        Parameter("total_width",   "length", default=1828.8, description="Total projection width (mm)"),
        Parameter("height",        "length", default=1219.2, description="Window height (mm)"),
        Parameter("depth",         "length", default=457.2,  description="Projection depth (mm)"),
        Parameter("angle",         "angle",  default=0.7854, description="Side-panel angle rad (45° typical)"),
        Parameter("center_width",  "length", default=914.4,  description="Center-panel width (mm)"),
        Parameter("glazing",       "string", default="double", description="Glazing type"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="wood",    description="Frame material id"),
        Parameter("seat_board",     "boolean",  default=True,      description="Include window seat board"),
    ],
    description="Three-panel angled bay projection.",
)

_ba_types: list[FamilyType] = [
    make_type(bay, "6-0 × 4-0",  {"total_width": 1828.8, "height": 1219.2, "center_width":  914.4}),
    make_type(bay, "8-0 × 4-0",  {"total_width": 2438.4, "height": 1219.2, "center_width": 1219.2}),
    make_type(bay, "1800 × 1200", {"total_width": 1800.0, "height": 1200.0, "center_width":  900.0}),
    make_type(bay, "2400 × 1200", {"total_width": 2400.0, "height": 1200.0, "center_width": 1200.0}),
]
bay._library_types = _ba_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# bow
# ---------------------------------------------------------------------------

bow: FamilyDefinition = make_family(
    name="Bow Window",
    category="Window",
    type_parameters=[
        Parameter("total_width",  "length",  default=2438.4, description="Total chord width (mm)"),
        Parameter("height",       "length",  default=1219.2, description="Window height (mm)"),
        Parameter("panel_count",  "integer", default=5,      description="Number of panels (4–6 typical)"),
        Parameter("depth",        "length",  default=609.6,  description="Bow projection depth (mm)"),
        Parameter("glazing",      "string",  default="double", description="Glazing type"),
    ],
    instance_parameters=[
        Parameter("frame_material", "material", default="wood",  description="Frame material id"),
        Parameter("seat_board",     "boolean",  default=True,    description="Include window seat board"),
    ],
    description="Multi-panel curved bow projection.",
)

_bo_types: list[FamilyType] = [
    make_type(bow, "8-0 × 4-0 (4-panel)",  {"total_width": 2438.4, "height": 1219.2, "panel_count": 4}),
    make_type(bow, "8-0 × 4-0 (5-panel)",  {"total_width": 2438.4, "height": 1219.2, "panel_count": 5}),
    make_type(bow, "10-0 × 4-0 (5-panel)", {"total_width": 3048.0, "height": 1219.2, "panel_count": 5}),
    make_type(bow, "2400 × 1200 (5-panel)", {"total_width": 2400.0, "height": 1200.0, "panel_count": 5}),
    make_type(bow, "3000 × 1200 (6-panel)", {"total_width": 3000.0, "height": 1200.0, "panel_count": 6}),
]
bow._library_types = _bo_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

ALL_WINDOW_FAMILIES: list[FamilyDefinition] = [
    single_hung,
    double_hung,
    casement,
    awning,
    fixed,
    sliding,
    picture,
    bay,
    bow,
]
