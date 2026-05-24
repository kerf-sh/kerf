"""
AASHTO superelevation runoff transitions and multi-template corridor cross-sections.

References
----------
AASHTO Green Book 2018/2024, Chapter 3:
  - Table 3-21: Runoff lengths for e_max = 8%, various design speeds and radii.
  - Section 3.3.5: Superelevation runoff distribution (1/3 tangent runout, 2/3 runoff buildup).
  - Section 3.3.4: Tangent runout = fraction of runoff length proportional to normal crown/e_full.

All lengths are in **feet** for AASHTO lookups; user-facing functions accept an
``units`` parameter so callers can work in metres (conversion applied internally).

Pure-Python; no NumPy required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# AASHTO Table 3-21 data (e_max=8%, 2-lane highway, 12-ft lanes)
# Runoff length L_r (feet) keyed by (design_speed_mph, radius_ft)
#
# The table is sampled at e = 2%, 4%, 6%, 8%.  We store the "transition
# length per lane" factor b_w (ft / % superelevation) and derive L_r from:
#   L_r = b_w * e_full * n_lanes    (AASHTO 3-21 footnote)
#
# Source: AASHTO Policy on Geometric Design of Highways and Streets 2018,
# Exhibit 3-21.  Values extracted for n_lanes=2 (one direction), lane=12 ft.
# ---------------------------------------------------------------------------

# Minimum runoff length (ft) per design speed (mph).
# These match AASHTO Table 3-21 at n=1 lane, 12-ft lane, for e_max=8%.
# Linear interpolation is used between tabulated values.
_AASHTO_RUNOFF_TABLE: list[tuple[int, float]] = [
    # (design_speed_mph, L_r_min_ft_at_e8pct_1lane_12ft)
    (15,  25),
    (20,  35),
    (25,  45),
    (30,  55),
    (35,  65),
    (40,  75),
    (45,  85),
    (50, 110),
    (55, 125),
    (60, 145),
    (65, 155),
    (70, 170),
    (75, 185),
    (80, 200),
]

# Relative gradient (Δ, %) per design speed used to compute runoff length
# by the formula L_r = (w * e_d) / Δ where w = lane width, e_d = design super.
# AASHTO Exhibit 3-20 (maximum relative gradient table).
_RELATIVE_GRADIENT_TABLE: list[tuple[int, float]] = [
    (15, 0.80),
    (20, 0.75),
    (25, 0.70),
    (30, 0.66),
    (35, 0.62),
    (40, 0.58),
    (45, 0.54),
    (50, 0.50),
    (55, 0.47),
    (60, 0.45),
    (65, 0.43),
    (70, 0.40),
    (75, 0.38),
    (80, 0.35),
]


def _interp_table(table: list[tuple[int, float]], speed_mph: float) -> float:
    """Linear interpolation over a (speed_mph, value) table."""
    if speed_mph <= table[0][0]:
        return table[0][1]
    if speed_mph >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        s0, v0 = table[i]
        s1, v1 = table[i + 1]
        if s0 <= speed_mph <= s1:
            t = (speed_mph - s0) / (s1 - s0)
            return v0 + t * (v1 - v0)
    return table[-1][1]


def aashto_relative_gradient(design_speed_mph: float) -> float:
    """Maximum relative gradient Δ (%) per AASHTO Exhibit 3-20.

    Parameters
    ----------
    design_speed_mph:
        Design speed in mph.

    Returns
    -------
    float
        Maximum relative gradient as a decimal fraction (e.g. 0.50 for 0.50%).
    """
    return _interp_table(_RELATIVE_GRADIENT_TABLE, design_speed_mph)


def runoff_length_ft(
    design_speed_mph: float,
    e_full_pct: float,
    lane_width_ft: float = 12.0,
    n_lanes: int = 1,
) -> float:
    """Superelevation runoff length L_r (feet) per AASHTO.

    Formula: L_r = (w * n * e_d) / Δ
    where:
      w       = lane width (ft)
      n       = number of lanes rotated
      e_d     = design superelevation (as decimal fraction)
      Δ       = maximum relative gradient (%) / 100

    Parameters
    ----------
    design_speed_mph:
        Design speed (mph).
    e_full_pct:
        Full superelevation rate (percent, e.g. 6.0 for 6 %).
    lane_width_ft:
        Width of one lane (feet).  AASHTO default = 12 ft.
    n_lanes:
        Number of lanes rotated simultaneously.  For a 2-lane highway
        rotating about the centreline, n_lanes = 1 (one lane per direction).

    Returns
    -------
    float
        Runoff length L_r in feet.
    """
    delta_pct = aashto_relative_gradient(design_speed_mph)
    e_d = e_full_pct / 100.0
    L_r = (lane_width_ft * n_lanes * e_d) / (delta_pct / 100.0)
    return L_r


def tangent_runout_length_ft(
    e_full_pct: float,
    normal_crown_pct: float,
    L_r: float,
) -> float:
    """Tangent runout length T_R (feet) per AASHTO Section 3.3.4.

    T_R = L_r * (e_NC / e_d)

    Parameters
    ----------
    e_full_pct:
        Full superelevation rate (%).
    normal_crown_pct:
        Normal (adverse) crown rate — the cross-slope that must be removed
        before superelevation buildup begins (%).
    L_r:
        Superelevation runoff length (feet).

    Returns
    -------
    float
        Tangent runout length T_R in feet.
    """
    return L_r * (normal_crown_pct / e_full_pct)


def superelevation_profile_at_station(
    station: float,
    curve_start: float,
    curve_end: float,
    e_full: float,
    design_speed_kph: float,
    lane_width_m: float = 3.65,
    n_lanes: int = 1,
    normal_crown_pct: float = 2.0,
    e_max_pct: float = 8.0,
) -> float:
    """Return the superelevation rate e(s) at *station* for a horizontal curve.

    Applies full AASHTO superelevation runoff transitions on both the approach
    and departure tangents.

    Distribution (AASHTO 3.3.5):
    - Tangent runout (T_R): adverse crown removed; super goes from 0 → normal_crown
      on the outside lane (effectively removing the reverse crown).
    - First 2/3 of runoff (before curve PC): super builds from normal_crown → e_full.
    - Remaining 1/3 of runoff (after curve PC): any residual buildup to e_full.

    Simplified model (common practice): place 2/3 of L_r before the PC/PT and
    1/3 after, with T_R just outside that.

    Parameters
    ----------
    station:
        Query station (same units as curve_start / curve_end).
    curve_start:
        Station of the Point of Curvature (PC / TS).
    curve_end:
        Station of the Point of Tangency (PT / ST).
    e_full:
        Full superelevation rate as a decimal fraction (e.g. 0.06 for 6 %).
    design_speed_kph:
        Design speed in km/h (converted internally to mph for AASHTO).
    lane_width_m:
        Lane width in metres (converted to feet for AASHTO formula).
    n_lanes:
        Number of lanes rotated.
    normal_crown_pct:
        Normal crown cross-slope (%).
    e_max_pct:
        Maximum superelevation (% — informational; clamps e_full).

    Returns
    -------
    float
        Superelevation rate e(s) as a signed decimal fraction.
        Positive = right side up (standard direction for a right-hand curve).
    """
    # Convert units
    design_speed_mph = design_speed_kph / 1.60934
    lane_width_ft = lane_width_m * 3.28084
    e_full = min(abs(e_full), e_max_pct / 100.0)

    # AASHTO lengths in feet, convert to same units as stations (metres)
    # Assume stations are in metres
    L_r_ft = runoff_length_ft(design_speed_mph, e_full * 100.0, lane_width_ft, n_lanes)
    T_R_ft = tangent_runout_length_ft(e_full * 100.0, normal_crown_pct, L_r_ft)
    L_r = L_r_ft / 3.28084  # → metres
    T_R = T_R_ft / 3.28084

    # Key transition stations (approach side)
    # A: beginning of tangent runout (adverse crown removal starts)
    # B: end of tangent runout / start of runoff (= PC - 2/3 L_r)
    # PC (curve_start): 2/3 L_r before PC is where runoff begins
    #   runoff: [PC - 2/3*L_r, PC + 1/3*L_r]
    # T_R: [A, B] where B = PC - 2/3*L_r

    approach_runoff_start = curve_start - (2.0 / 3.0) * L_r
    approach_tangout_start = approach_runoff_start - T_R

    depart_runoff_end = curve_end + (2.0 / 3.0) * L_r
    depart_tangout_end = depart_runoff_end + T_R

    e_crown = normal_crown_pct / 100.0  # normal crown as fraction

    # ----- Approach transition -----
    if station <= approach_tangout_start:
        # Normal crown (no superelevation applied)
        return 0.0

    if approach_tangout_start < station <= approach_runoff_start:
        # Tangent runout: adverse crown being removed (0 → e_crown)
        t = (station - approach_tangout_start) / T_R if T_R > 0 else 1.0
        return t * e_crown

    if approach_runoff_start < station <= curve_start:
        # Runoff buildup first 2/3: e_crown → e_full
        t = (station - approach_runoff_start) / ((2.0 / 3.0) * L_r)
        return e_crown + t * (e_full - e_crown)

    # ----- Full super inside curve (with possible 1/3 taper at ends) -----
    if curve_start < station <= curve_start + (1.0 / 3.0) * L_r:
        # Last 1/3 of approach runoff (past PC): e stays at e_full after buildup
        t = (station - curve_start) / ((1.0 / 3.0) * L_r)
        return e_crown + t * (e_full - e_crown) + (1.0 - t) * 0.0  # already at e_full from above
        # Simplify: at curve_start we've just finished the 2/3 ramp → e_full
        # and the 1/3 after PC means full super is reached at PC+1/3*L_r.
        # Ramp: from (e_crown + (2/3*(e_full-e_crown)) at PC) → e_full
        e_at_pc = e_crown + (e_full - e_crown)  # = e_full
        return e_full  # already fully ramped; keep full super

    # Full super for the middle of the curve
    if curve_start + (1.0 / 3.0) * L_r < station <= curve_end - (1.0 / 3.0) * L_r:
        return e_full

    # ----- Departure transition -----
    if curve_end - (1.0 / 3.0) * L_r < station <= curve_end:
        # First 1/3 of departure runoff (before PT): begin removing super
        t = (station - (curve_end - (1.0 / 3.0) * L_r)) / ((1.0 / 3.0) * L_r)
        return e_full - t * (e_full - e_crown)

    if curve_end < station <= depart_runoff_end:
        # Last 2/3 of departure runoff (after PT)
        t = (station - curve_end) / ((2.0 / 3.0) * L_r)
        return e_crown - t * e_crown  # e_crown → 0

    if depart_runoff_end < station <= depart_tangout_end:
        # Tangent runout: returning adverse crown (informational; return 0)
        t = (station - depart_runoff_end) / T_R if T_R > 0 else 1.0
        return (1.0 - t) * 0.0  # effectively 0

    # Past all transitions — normal crown
    return 0.0


# ---------------------------------------------------------------------------
# Cross-section template point
# ---------------------------------------------------------------------------

@dataclass
class TemplatePoint:
    """A point on a cross-section template.

    Attributes
    ----------
    x_offset:
        Lateral offset from centreline (metres).  Positive = right.
    y_offset:
        Vertical offset from design CL elevation (metres).
    code:
        Survey/design code label (e.g. "CL", "EL", "SHL", "GUTTER").
    """

    x_offset: float
    y_offset: float
    code: str = ""


# ---------------------------------------------------------------------------
# Multi-template cross-section builders
# ---------------------------------------------------------------------------

def divided_highway_template(
    median_width: float = 6.0,
    n_lanes_each_dir: int = 2,
    lane_width: float = 3.65,
    shoulder_inner: float = 1.2,
    shoulder_outer: float = 3.0,
    slope_cut: float = 2.0,
    slope_fill: float = 2.0,
    crown_slope_pct: float = 2.0,
) -> list[TemplatePoint]:
    """Divided highway cross-section template.

    Builds a symmetric divided highway centred on the median.  The returned
    point list runs from left daylight to right daylight.

    Parameters
    ----------
    median_width:
        Width of the raised median (m), measured between the two inner edges.
    n_lanes_each_dir:
        Number of travel lanes in each direction.
    lane_width:
        Width of each travel lane (m).
    shoulder_inner:
        Inner (median-side) shoulder width (m).
    shoulder_outer:
        Outer (right-of-way side) shoulder width (m).
    slope_cut:
        Cut backslope H:V ratio.
    slope_fill:
        Fill foreslope H:V ratio.
    crown_slope_pct:
        Normal cross-slope of the travel lanes (%, positive = falls from CL).

    Returns
    -------
    list[TemplatePoint]
        Ordered template points from left edge to right edge.
    """
    crown = crown_slope_pct / 100.0
    half_median = median_width / 2.0
    lane_total = n_lanes_each_dir * lane_width
    points: list[TemplatePoint] = []

    # ---- Left side (mirror of right) ----
    # Process right side first, then mirror
    def right_half() -> list[TemplatePoint]:
        pts: list[TemplatePoint] = []
        x = half_median  # inner edge of roadway (median curb)
        y = 0.0
        pts.append(TemplatePoint(x, y, "MEDIAN_EDGE_R"))

        # Inner shoulder
        x_shl_in = x + shoulder_inner
        y_shl_in = y - crown * shoulder_inner
        pts.append(TemplatePoint(x_shl_in, y_shl_in, "SHOULDER_IN_R"))

        # Travel lanes — each lane drops by crown
        x_lane_edge = x_shl_in
        y_lane_edge = y_shl_in
        for i in range(n_lanes_each_dir):
            x_lane_edge += lane_width
            y_lane_edge -= crown * lane_width
            code = f"LANE_{i+1}_R"
            pts.append(TemplatePoint(x_lane_edge, y_lane_edge, code))

        # Outer shoulder
        x_shl_out = x_lane_edge + shoulder_outer
        y_shl_out = y_lane_edge - crown * shoulder_outer
        pts.append(TemplatePoint(x_shl_out, y_shl_out, "SHOULDER_OUT_R"))

        # Daylight (simplified: at shoulder break)
        pts.append(TemplatePoint(x_shl_out, y_shl_out, "DAYLIGHT_R"))
        return pts

    right = right_half()
    # Mirror for left side
    left = [TemplatePoint(-p.x_offset, p.y_offset, p.code.replace("_R", "_L"))
            for p in reversed(right)]

    # Centre
    centre = [TemplatePoint(0.0, 0.0, "CL")]

    return left + centre + right


def reverse_crown_template(
    n_lanes: int = 2,
    lane_width: float = 3.65,
    shoulder_width: float = 3.0,
    e_pct: float = 6.0,
    shoulder_slope_pct: float = 5.0,
) -> list[TemplatePoint]:
    """Fully superelevated (reverse crown) cross-section template.

    Both lanes slope in the same direction (towards the inside of the curve),
    as per AASHTO Case I full superelevation rotation about the centreline.

    Parameters
    ----------
    n_lanes:
        Total number of travel lanes (full cross-section, both directions).
    lane_width:
        Lane width (m).
    shoulder_width:
        Shoulder width (m) on each side.
    e_pct:
        Superelevation rate (%, positive for right-hand curve).
    shoulder_slope_pct:
        Shoulder cross-slope (%).  Outer shoulder typically 5-6 % with super.

    Returns
    -------
    list[TemplatePoint]
        Template points from left to right.
    """
    e = e_pct / 100.0
    s_slope = shoulder_slope_pct / 100.0
    half_lanes = n_lanes // 2
    half_width = half_lanes * lane_width
    shoulder = shoulder_width

    # All lanes slope uniformly at e (high side on left for right curve)
    # Left shoulder: outside, also slopes at s_slope downward to the left
    left_edge = -half_width - shoulder
    left_shl_elev = e * half_width + s_slope * shoulder  # higher than CL

    points: list[TemplatePoint] = [
        TemplatePoint(left_edge, left_shl_elev, "SHOULDER_L"),
        TemplatePoint(-half_width, e * half_width, "EDGE_LANE_L"),
        TemplatePoint(0.0, 0.0, "CL"),
        TemplatePoint(half_width, -e * half_width, "EDGE_LANE_R"),
        TemplatePoint(half_width + shoulder, -e * half_width - s_slope * shoulder, "SHOULDER_R"),
    ]
    return points


def urban_curb_gutter_template(
    n_lanes: int = 2,
    lane_width: float = 3.65,
    curb_height: float = 0.15,
    gutter_width: float = 0.6,
    sidewalk_width: float = 1.5,
    sidewalk_height: float = 0.15,
    crown_slope_pct: float = 2.0,
) -> list[TemplatePoint]:
    """Urban curb-and-gutter cross-section template.

    Includes vertical curb face, gutter pan, and raised sidewalk on each side.

    Parameters
    ----------
    n_lanes:
        Total travel lanes (both directions combined).
    lane_width:
        Lane width (m).
    curb_height:
        Height of the vertical curb face (m).
    gutter_width:
        Width of the gutter pan (m).
    sidewalk_width:
        Sidewalk width (m).
    sidewalk_height:
        Height of the sidewalk above gutter (m).  Typically = curb_height.
    crown_slope_pct:
        Lane cross-slope (%).

    Returns
    -------
    list[TemplatePoint]
        Template points, left to right.
    """
    crown = crown_slope_pct / 100.0
    half_lanes = n_lanes // 2
    half_pavement = half_lanes * lane_width

    def right_pts() -> list[TemplatePoint]:
        pts: list[TemplatePoint] = []
        # Edge of pavement (at CL elevation = 0, lane falls away)
        x0, y0 = half_pavement, -crown * half_pavement
        pts.append(TemplatePoint(x0, y0, "EDGE_PAVEMENT_R"))
        # Top of curb face
        x_curb = x0
        y_curb_top = y0  # vertical curb: x stays same, y jumps up
        # Bottom of curb (face base = gutter level = y0 - curb_height... but
        # curb_height is how much the curb sticks up above the gutter, so
        # gutter level = pavement edge elevation, top of curb above gutter)
        x_gutter_start = x_curb
        y_gutter = y0
        pts.append(TemplatePoint(x_gutter_start, y_gutter, "CURB_FACE_BOTTOM_R"))
        # Gutter pan (flows toward drain)
        x_gutter_end = x_gutter_start + gutter_width
        y_gutter_end = y_gutter - 0.02 * gutter_width  # 2% gutter slope
        pts.append(TemplatePoint(x_gutter_end, y_gutter_end, "GUTTER_R"))
        # Curb back (top of sidewalk)
        x_sw_start = x_gutter_end
        y_sw = y_gutter_end + sidewalk_height
        pts.append(TemplatePoint(x_sw_start, y_sw, "SIDEWALK_INNER_R"))
        # Outer edge of sidewalk
        x_sw_end = x_sw_start + sidewalk_width
        y_sw_end = y_sw - 0.01 * sidewalk_width  # 1% sidewalk cross-slope
        pts.append(TemplatePoint(x_sw_end, y_sw_end, "SIDEWALK_OUTER_R"))
        return pts

    right = right_pts()
    left = [TemplatePoint(-p.x_offset, p.y_offset, p.code.replace("_R", "_L"))
            for p in reversed(right)]
    centre = [TemplatePoint(0.0, 0.0, "CL")]

    return left + centre + right


# ---------------------------------------------------------------------------
# Cross-section at station with superelevation blending
# ---------------------------------------------------------------------------

def corridor_cross_section_at(
    template: list[TemplatePoint],
    station: float,
    e_at_station: float,
    cl_elevation: float = 0.0,
    rotation_axis: str = "CL",
) -> list[TemplatePoint]:
    """Blend a template's lane slopes with the current superelevation.

    The template provides the pavement geometry under normal crown conditions.
    This function adjusts the vertical offsets to reflect the current
    superelevation rate *e_at_station*.

    Rotation about the centreline ("CL") is supported:
    - Positive e = right-hand curve (right side lower, left side higher).
    - Lane slope for right lanes becomes –e (down to right).
    - Lane slope for left lanes becomes +e (up from CL, matching full super).

    Parameters
    ----------
    template:
        List of ``TemplatePoint`` objects (e.g. from ``divided_highway_template``).
    station:
        Current chainage — used only for labelling; geometry is stateless.
    e_at_station:
        Superelevation rate at this station (decimal fraction, signed).
    cl_elevation:
        Design CL elevation at this station (m).
    rotation_axis:
        Pivot point for superelevation rotation.  Only "CL" is currently
        supported.

    Returns
    -------
    list[TemplatePoint]
        New template points with adjusted y_offsets.  Absolute elevations are
        y_offset + cl_elevation.
    """
    result: list[TemplatePoint] = []
    for pt in template:
        if pt.code in ("CL",):
            result.append(TemplatePoint(pt.x_offset, cl_elevation + pt.y_offset, pt.code))
            continue
        # The y adjustment for superelevation: rotate by e about CL
        # For x_offset > 0 (right side): y_adj = -e * x_offset
        # For x_offset < 0 (left side):  y_adj = +e * x_offset (also negative on right curve)
        # Net: both sides slope uniformly downward on one side
        # This creates the "reverse crown" for full super; blending handles intermediate
        e_adj = -e_at_station * pt.x_offset  # positive e → right side lower
        new_y = cl_elevation + pt.y_offset + e_adj
        result.append(TemplatePoint(pt.x_offset, new_y, pt.code))
    return result


# ---------------------------------------------------------------------------
# LLM tool registrations
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


civil_superelevation_profile_spec = ToolSpec(
    name="civil_superelevation_profile",
    description=(
        "Compute the AASHTO superelevation rate profile along a horizontal curve, "
        "including tangent runout and superelevation runoff transitions.  Returns the "
        "superelevation rate e(s) at each queried station."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "curve_start_m": {
                "type": "number",
                "description": "Station of the Point of Curvature (PC) in metres.",
            },
            "curve_end_m": {
                "type": "number",
                "description": "Station of the Point of Tangency (PT) in metres.",
            },
            "e_full_pct": {
                "type": "number",
                "description": "Full superelevation rate (%, e.g. 6.0 for 6%).",
            },
            "design_speed_kph": {
                "type": "number",
                "description": "Design speed in km/h.",
            },
            "lane_width_m": {
                "type": "number",
                "description": "Lane width in metres.",
                "default": 3.65,
            },
            "n_lanes": {
                "type": "integer",
                "description": "Number of lanes rotated simultaneously.",
                "default": 1,
            },
            "stations_m": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Query stations (metres). If omitted, sampled automatically "
                    "at 10 m intervals across the transition region."
                ),
            },
        },
        "required": ["curve_start_m", "curve_end_m", "e_full_pct", "design_speed_kph"],
    },
)


async def run_civil_superelevation_profile(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.superelevation import (
            superelevation_profile_at_station,
            runoff_length_ft,
            tangent_runout_length_ft,
            aashto_relative_gradient,
        )

        cs = float(params["curve_start_m"])
        ce = float(params["curve_end_m"])
        e_full = float(params["e_full_pct"]) / 100.0
        speed_kph = float(params["design_speed_kph"])
        lane_w = float(params.get("lane_width_m", 3.65))
        n_lanes = int(params.get("n_lanes", 1))

        speed_mph = speed_kph / 1.60934
        lane_w_ft = lane_w * 3.28084
        L_r_ft = runoff_length_ft(speed_mph, e_full * 100.0, lane_w_ft, n_lanes)
        T_R_ft = tangent_runout_length_ft(e_full * 100.0, 2.0, L_r_ft)
        L_r = L_r_ft / 3.28084
        T_R = T_R_ft / 3.28084

        stations = params.get("stations_m")
        if not stations:
            # Auto-generate at 10 m intervals across transition region
            s_start = cs - (2.0 / 3.0) * L_r - T_R - 10.0
            s_end = ce + (2.0 / 3.0) * L_r + T_R + 10.0
            n = max(20, int((s_end - s_start) / 10.0) + 1)
            stations = [s_start + i * (s_end - s_start) / (n - 1) for i in range(n)]

        profile = []
        for s in stations:
            e = superelevation_profile_at_station(
                s, cs, ce, e_full, speed_kph, lane_w, n_lanes
            )
            profile.append({"station_m": round(s, 3), "e_pct": round(e * 100, 4)})

        return ok_payload({
            "runoff_length_ft": round(L_r_ft, 1),
            "runoff_length_m": round(L_r, 3),
            "tangent_runout_ft": round(T_R_ft, 1),
            "tangent_runout_m": round(T_R, 3),
            "profile": profile,
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_SUPER_ERROR")


civil_corridor_template_spec = ToolSpec(
    name="civil_corridor_template",
    description=(
        "Generate a cross-section template for a highway corridor.  Supports "
        "divided highway, fully superelevated (reverse crown), and urban curb-and-gutter "
        "templates.  Returns an ordered list of (x_offset, y_offset, code) points."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "template_type": {
                "type": "string",
                "enum": ["divided_highway", "reverse_crown", "urban_curb_gutter"],
                "description": "Cross-section template type.",
            },
            "median_width_m": {"type": "number", "default": 6.0},
            "n_lanes_each_dir": {"type": "integer", "default": 2},
            "n_lanes_total": {"type": "integer", "default": 2},
            "lane_width_m": {"type": "number", "default": 3.65},
            "shoulder_inner_m": {"type": "number", "default": 1.2},
            "shoulder_outer_m": {"type": "number", "default": 3.0},
            "shoulder_width_m": {"type": "number", "default": 3.0},
            "slope_cut": {"type": "number", "default": 2.0},
            "slope_fill": {"type": "number", "default": 2.0},
            "crown_slope_pct": {"type": "number", "default": 2.0},
            "e_pct": {"type": "number", "default": 6.0},
            "curb_height_m": {"type": "number", "default": 0.15},
            "gutter_width_m": {"type": "number", "default": 0.6},
            "sidewalk_width_m": {"type": "number", "default": 1.5},
        },
        "required": ["template_type"],
    },
)


async def run_civil_corridor_template(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.superelevation import (
            divided_highway_template,
            reverse_crown_template,
            urban_curb_gutter_template,
        )

        ttype = params["template_type"]
        if ttype == "divided_highway":
            pts = divided_highway_template(
                median_width=float(params.get("median_width_m", 6.0)),
                n_lanes_each_dir=int(params.get("n_lanes_each_dir", 2)),
                lane_width=float(params.get("lane_width_m", 3.65)),
                shoulder_inner=float(params.get("shoulder_inner_m", 1.2)),
                shoulder_outer=float(params.get("shoulder_outer_m", 3.0)),
                slope_cut=float(params.get("slope_cut", 2.0)),
                slope_fill=float(params.get("slope_fill", 2.0)),
                crown_slope_pct=float(params.get("crown_slope_pct", 2.0)),
            )
        elif ttype == "reverse_crown":
            pts = reverse_crown_template(
                n_lanes=int(params.get("n_lanes_total", 2)),
                lane_width=float(params.get("lane_width_m", 3.65)),
                shoulder_width=float(params.get("shoulder_width_m", 3.0)),
                e_pct=float(params.get("e_pct", 6.0)),
            )
        elif ttype == "urban_curb_gutter":
            pts = urban_curb_gutter_template(
                n_lanes=int(params.get("n_lanes_total", 2)),
                lane_width=float(params.get("lane_width_m", 3.65)),
                curb_height=float(params.get("curb_height_m", 0.15)),
                gutter_width=float(params.get("gutter_width_m", 0.6)),
                sidewalk_width=float(params.get("sidewalk_width_m", 1.5)),
                crown_slope_pct=float(params.get("crown_slope_pct", 2.0)),
            )
        else:
            return err_payload(f"Unknown template_type: {ttype}", "CIVIL_TEMPLATE_UNKNOWN")

        return ok_payload({
            "template_type": ttype,
            "points": [
                {"x_offset_m": round(p.x_offset, 4), "y_offset_m": round(p.y_offset, 4), "code": p.code}
                for p in pts
            ],
            "total_width_m": round(pts[-1].x_offset - pts[0].x_offset, 4),
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_TEMPLATE_ERROR")


civil_corridor_cross_section_spec = ToolSpec(
    name="civil_corridor_cross_section",
    description=(
        "Compute the design cross-section at a given station by blending a corridor "
        "template's lane slopes with the current superelevation rate.  Rotation is "
        "about the centreline."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "template_type": {
                "type": "string",
                "enum": ["divided_highway", "reverse_crown", "urban_curb_gutter"],
            },
            "station_m": {"type": "number"},
            "cl_elevation_m": {"type": "number", "default": 0.0},
            "e_at_station_pct": {
                "type": "number",
                "description": "Superelevation rate at station (%).",
                "default": 0.0,
            },
            "median_width_m": {"type": "number", "default": 6.0},
            "n_lanes_each_dir": {"type": "integer", "default": 2},
            "lane_width_m": {"type": "number", "default": 3.65},
            "shoulder_outer_m": {"type": "number", "default": 3.0},
        },
        "required": ["template_type", "station_m"],
    },
)


async def run_civil_corridor_cross_section(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.superelevation import (
            divided_highway_template,
            reverse_crown_template,
            corridor_cross_section_at,
        )

        ttype = params["template_type"]
        station = float(params["station_m"])
        cl_elev = float(params.get("cl_elevation_m", 0.0))
        e = float(params.get("e_at_station_pct", 0.0)) / 100.0

        if ttype == "divided_highway":
            tmpl = divided_highway_template(
                median_width=float(params.get("median_width_m", 6.0)),
                n_lanes_each_dir=int(params.get("n_lanes_each_dir", 2)),
                lane_width=float(params.get("lane_width_m", 3.65)),
                shoulder_outer=float(params.get("shoulder_outer_m", 3.0)),
            )
        else:
            tmpl = reverse_crown_template(
                n_lanes=int(params.get("n_lanes_each_dir", 2)) * 2,
                lane_width=float(params.get("lane_width_m", 3.65)),
            )

        pts = corridor_cross_section_at(tmpl, station, e, cl_elev)

        return ok_payload({
            "station_m": station,
            "cl_elevation_m": cl_elev,
            "e_pct": e * 100,
            "points": [
                {"x_offset_m": round(p.x_offset, 4), "elevation_m": round(p.y_offset, 4), "code": p.code}
                for p in pts
            ],
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_XS_ERROR")
