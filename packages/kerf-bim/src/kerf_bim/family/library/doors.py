"""
kerf_bim.family.library.doors
==============================

Pre-populated parametric door families for the BIM family library.

Families:
    single_swing    — single-leaf hinged door
    double_swing    — double-leaf hinged pair
    sliding         — sliding panel door
    bifold          — bifold/accordion door
    pocket          — pocket door (slides into wall cavity)
    garage          — overhead garage door (sectional)

All width/height dimensions are stored in mm (length kind).
Common imperial + metric FamilyType presets are registered on each
family so a cold-start project has a usable catalog immediately.
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
    "single_swing",
    "double_swing",
    "sliding",
    "bifold",
    "pocket",
    "garage",
    "ALL_DOOR_FAMILIES",
]


# ---------------------------------------------------------------------------
# single_swing
# ---------------------------------------------------------------------------

single_swing: FamilyDefinition = make_family(
    name="Single Swing Door",
    category="Door",
    type_parameters=[
        Parameter("width",           "length", default=914.4,  description="Clear opening width (mm)"),
        Parameter("height",          "length", default=2032.0, description="Clear opening height (mm)"),
        Parameter("panel_thickness", "length", default=44.5,   description="Door panel thickness (mm)"),
        Parameter("lite_pattern",    "string", default="none", description="Glazing lite pattern: none/half/full/sidelite"),
    ],
    instance_parameters=[
        Parameter("material",       "material", default="solid_wood",  description="Panel material id"),
        Parameter("frame_material", "material", default="pine",        description="Frame material id"),
        Parameter("handed",         "string",   default="right",       description="Hand: left or right"),
        Parameter("fire_rated",     "boolean",  default=False,         description="Fire-rated assembly"),
    ],
    description="Single-leaf hinged interior or exterior door.",
)

_sw_types: list[FamilyType] = [
    # Imperial (width × height in mm converted from inch nominal)
    make_type(single_swing, "2-0 × 6-8",  {"width": 609.6,  "height": 2032.0}),
    make_type(single_swing, "2-4 × 6-8",  {"width": 711.2,  "height": 2032.0}),
    make_type(single_swing, "2-6 × 6-8",  {"width": 762.0,  "height": 2032.0}),
    make_type(single_swing, "2-8 × 6-8",  {"width": 812.8,  "height": 2032.0}),
    make_type(single_swing, "3-0 × 6-8",  {"width": 914.4,  "height": 2032.0}),
    make_type(single_swing, "3-0 × 7-0",  {"width": 914.4,  "height": 2133.6}),
    make_type(single_swing, "3-0 × 8-0",  {"width": 914.4,  "height": 2438.4}),
    # Metric
    make_type(single_swing, "700 × 2000",  {"width": 700.0,  "height": 2000.0}),
    make_type(single_swing, "800 × 2000",  {"width": 800.0,  "height": 2000.0}),
    make_type(single_swing, "900 × 2100",  {"width": 900.0,  "height": 2100.0}),
    make_type(single_swing, "1000 × 2100", {"width": 1000.0, "height": 2100.0}),
]
single_swing._library_types = _sw_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# double_swing
# ---------------------------------------------------------------------------

double_swing: FamilyDefinition = make_family(
    name="Double Swing Door",
    category="Door",
    type_parameters=[
        Parameter("width",           "length", default=1828.8, description="Total opening width (mm)"),
        Parameter("height",          "length", default=2032.0, description="Opening height (mm)"),
        Parameter("panel_thickness", "length", default=44.5,   description="Panel thickness (mm)"),
        Parameter("lite_pattern",    "string", default="none", description="Glazing lite pattern"),
        Parameter("active_leaf",     "string", default="both", description="Active leaf(ves): left/right/both"),
    ],
    instance_parameters=[
        Parameter("material",       "material", default="solid_wood", description="Panel material id"),
        Parameter("frame_material", "material", default="pine",       description="Frame material id"),
        Parameter("fire_rated",     "boolean",  default=False,        description="Fire-rated assembly"),
    ],
    description="Pair of hinged leaves sharing a single opening.",
)

_ds_types: list[FamilyType] = [
    make_type(double_swing, "4-0 × 6-8",  {"width": 1219.2, "height": 2032.0}),
    make_type(double_swing, "5-0 × 6-8",  {"width": 1524.0, "height": 2032.0}),
    make_type(double_swing, "6-0 × 6-8",  {"width": 1828.8, "height": 2032.0}),
    make_type(double_swing, "6-0 × 8-0",  {"width": 1828.8, "height": 2438.4}),
    make_type(double_swing, "1600 × 2100", {"width": 1600.0, "height": 2100.0}),
    make_type(double_swing, "1800 × 2100", {"width": 1800.0, "height": 2100.0}),
    make_type(double_swing, "2000 × 2100", {"width": 2000.0, "height": 2100.0}),
]
double_swing._library_types = _ds_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# sliding
# ---------------------------------------------------------------------------

sliding: FamilyDefinition = make_family(
    name="Sliding Door",
    category="Door",
    type_parameters=[
        Parameter("width",        "length", default=1524.0, description="Total opening width (mm)"),
        Parameter("height",       "length", default=2032.0, description="Opening height (mm)"),
        Parameter("panel_count",  "integer", default=2,     description="Number of sliding panels"),
        Parameter("track_type",   "string",  default="top_hung", description="Track: top_hung or bottom_rolling"),
        Parameter("lite_pattern", "string",  default="full",     description="Glazing: none/partial/full"),
    ],
    instance_parameters=[
        Parameter("material",     "material", default="glass",    description="Panel material id"),
        Parameter("frame_finish", "material", default="aluminum", description="Frame finish material id"),
    ],
    description="Sliding panel door on an overhead or floor track.",
)

_sl_types: list[FamilyType] = [
    make_type(sliding, "5-0 × 6-8",   {"width": 1524.0, "height": 2032.0}),
    make_type(sliding, "6-0 × 6-8",   {"width": 1828.8, "height": 2032.0}),
    make_type(sliding, "8-0 × 6-8",   {"width": 2438.4, "height": 2032.0}),
    make_type(sliding, "1500 × 2100",  {"width": 1500.0, "height": 2100.0}),
    make_type(sliding, "1800 × 2100",  {"width": 1800.0, "height": 2100.0}),
    make_type(sliding, "2400 × 2100",  {"width": 2400.0, "height": 2100.0}),
    make_type(sliding, "3000 × 2400",  {"width": 3000.0, "height": 2400.0}),
]
sliding._library_types = _sl_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# bifold
# ---------------------------------------------------------------------------

bifold: FamilyDefinition = make_family(
    name="Bifold Door",
    category="Door",
    type_parameters=[
        Parameter("width",       "length",  default=914.4,  description="Opening width (mm)"),
        Parameter("height",      "length",  default=2032.0, description="Opening height (mm)"),
        Parameter("panel_count", "integer", default=2,      description="Number of hinged panels (even)"),
        Parameter("fold_side",   "string",  default="right", description="Side panels fold to: left/right"),
    ],
    instance_parameters=[
        Parameter("material",     "material", default="hollow_core", description="Panel material id"),
        Parameter("track_finish", "material", default="white",       description="Track finish material id"),
    ],
    description="Accordion-fold door panels on a top track.",
)

_bf_types: list[FamilyType] = [
    make_type(bifold, "2-0 × 6-8",  {"width": 609.6,  "height": 2032.0, "panel_count": 2}),
    make_type(bifold, "3-0 × 6-8",  {"width": 914.4,  "height": 2032.0, "panel_count": 2}),
    make_type(bifold, "4-0 × 6-8",  {"width": 1219.2, "height": 2032.0, "panel_count": 4}),
    make_type(bifold, "5-0 × 6-8",  {"width": 1524.0, "height": 2032.0, "panel_count": 4}),
    make_type(bifold, "6-0 × 6-8",  {"width": 1828.8, "height": 2032.0, "panel_count": 4}),
    make_type(bifold, "600 × 2100",  {"width": 600.0,  "height": 2100.0, "panel_count": 2}),
    make_type(bifold, "900 × 2100",  {"width": 900.0,  "height": 2100.0, "panel_count": 2}),
    make_type(bifold, "1200 × 2100", {"width": 1200.0, "height": 2100.0, "panel_count": 4}),
]
bifold._library_types = _bf_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# pocket
# ---------------------------------------------------------------------------

pocket: FamilyDefinition = make_family(
    name="Pocket Door",
    category="Door",
    type_parameters=[
        Parameter("width",           "length", default=914.4,  description="Clear opening width (mm)"),
        Parameter("height",          "length", default=2032.0, description="Opening height (mm)"),
        Parameter("panel_thickness", "length", default=35.0,   description="Panel thickness (mm)"),
        Parameter("cavity_depth",    "length", default=914.4,  description="Wall cavity required (mm)"),
    ],
    instance_parameters=[
        Parameter("material",     "material", default="hollow_core", description="Panel material id"),
        Parameter("hardware_set", "string",   default="standard",    description="Hardware set id"),
    ],
    description="Door panel that retracts into a wall cavity pocket.",
)

_pk_types: list[FamilyType] = [
    make_type(pocket, "2-6 × 6-8", {"width": 762.0,  "height": 2032.0, "cavity_depth": 762.0}),
    make_type(pocket, "2-8 × 6-8", {"width": 812.8,  "height": 2032.0, "cavity_depth": 812.8}),
    make_type(pocket, "3-0 × 6-8", {"width": 914.4,  "height": 2032.0, "cavity_depth": 914.4}),
    make_type(pocket, "3-0 × 7-0", {"width": 914.4,  "height": 2133.6, "cavity_depth": 914.4}),
    make_type(pocket, "800 × 2100", {"width": 800.0,  "height": 2100.0, "cavity_depth": 800.0}),
    make_type(pocket, "900 × 2100", {"width": 900.0,  "height": 2100.0, "cavity_depth": 900.0}),
]
pocket._library_types = _pk_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# garage
# ---------------------------------------------------------------------------

garage: FamilyDefinition = make_family(
    name="Garage Door",
    category="Door",
    type_parameters=[
        Parameter("width",           "length", default=2438.4, description="Opening width (mm)"),
        Parameter("height",          "length", default=1981.2, description="Opening height (mm)"),
        Parameter("section_count",   "integer", default=4,     description="Number of horizontal sections"),
        Parameter("operation",       "string",  default="sectional_overhead",
                  description="Operation: sectional_overhead / roll_up / tilt_up"),
        Parameter("insulation",      "boolean", default=True,  description="Insulated panels"),
    ],
    instance_parameters=[
        Parameter("material",    "material", default="steel",    description="Panel material id"),
        Parameter("color",       "string",   default="white",    description="Finish color"),
        Parameter("operator",    "string",   default="manual",   description="operator: manual/chain/belt/jackshaft"),
    ],
    description="Overhead sectional garage door.",
)

_ga_types: list[FamilyType] = [
    # Single-car widths
    make_type(garage, "8-0 × 7-0",   {"width": 2438.4, "height": 2133.6}),
    make_type(garage, "9-0 × 7-0",   {"width": 2743.2, "height": 2133.6}),
    make_type(garage, "10-0 × 7-0",  {"width": 3048.0, "height": 2133.6}),
    make_type(garage, "9-0 × 8-0",   {"width": 2743.2, "height": 2438.4}),
    # Double-car widths
    make_type(garage, "16-0 × 7-0",  {"width": 4876.8, "height": 2133.6}),
    make_type(garage, "18-0 × 7-0",  {"width": 5486.4, "height": 2133.6}),
    # Metric
    make_type(garage, "2500 × 2200",  {"width": 2500.0, "height": 2200.0}),
    make_type(garage, "4800 × 2200",  {"width": 4800.0, "height": 2200.0}),
]
garage._library_types = _ga_types  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

ALL_DOOR_FAMILIES: list[FamilyDefinition] = [
    single_swing,
    double_swing,
    sliding,
    bifold,
    pocket,
    garage,
]
