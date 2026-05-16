"""
kerf_cad_core.hydrology.tools — LLM tool wrappers for stormwater hydrology.

Registers tools with the Kerf tool registry:

  hydrology_rational_peak_flow         — Rational method peak flow Q = C·i·A
  hydrology_composite_runoff_coeff     — Area-weighted composite C
  hydrology_scs_runoff_depth           — SCS curve-number runoff depth
  hydrology_scs_peak_flow              — TR-55 graphical-peak flow
  hydrology_time_of_concentration      — Tc: Kirpich / NRCS velocity / 3-segment
  hydrology_idf_intensity              — IDF intensity i = a/(t+b)^c
  hydrology_detention_storage          — Modified-rational detention volume
  hydrology_storage_indication_route   — Puls / level-pool routing
  hydrology_storm_sewer_pipe_size      — Manning full-flow pipe sizing

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": ...} — tools never raise.

Units: SI throughout (m³/s, mm, ha, km², hr, m) unless noted.

References
----------
ASCE/EWRI 45-05 — Rational Method for stormwater peak flow
TR-55 (USDA SCS 1986) — Urban Hydrology for Small Watersheds
NRCS National Engineering Handbook Part 630 (NEH-630)
Chow, Maidment & Mays (1988) — Applied Hydrology

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.hydrology.runoff import (
    rational_peak_flow,
    composite_runoff_coeff,
    scs_runoff_depth,
    scs_peak_flow,
    time_of_concentration,
    idf_intensity,
    detention_storage_modified_rational,
    storage_indication_route,
    storm_sewer_pipe_size,
)


# ---------------------------------------------------------------------------
# Tool: hydrology_rational_peak_flow
# ---------------------------------------------------------------------------

_rational_peak_spec = ToolSpec(
    name="hydrology_rational_peak_flow",
    description=(
        "Compute the rational-method peak stormwater flow.\n"
        "\n"
        "Formula:  Q = C · i · A / 360\n"
        "  Q in m³/s,  i in mm/hr,  A in ha.\n"
        "\n"
        "The Rational Method is applicable to urban catchments < ~80 ha with\n"
        "time of concentration < ~3 hr.  Use a composite C for mixed land use.\n"
        "\n"
        "Returns Q_m3s and Q_L_per_s.\n"
        "\n"
        "Reference: ASCE/EWRI 45-05."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "C": {
                "type": "number",
                "description": "Runoff coefficient (0 < C ≤ 1.0). Typical: 0.90 impervious, 0.35 lawn.",
            },
            "i_mm_hr": {
                "type": "number",
                "description": "Design rainfall intensity (mm/hr) for the return period and storm duration equal to tc.",
            },
            "A_ha": {
                "type": "number",
                "description": "Catchment area (ha).",
            },
        },
        "required": ["C", "i_mm_hr", "A_ha"],
    },
)


@register(_rational_peak_spec, write=False)
async def run_hydrology_rational_peak_flow(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("C", "i_mm_hr", "A_ha"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    result = rational_peak_flow(a["C"], a["i_mm_hr"], a["A_ha"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_composite_runoff_coeff
# ---------------------------------------------------------------------------

_composite_c_spec = ToolSpec(
    name="hydrology_composite_runoff_coeff",
    description=(
        "Compute an area-weighted composite runoff coefficient C for a catchment\n"
        "with multiple land-cover types.\n"
        "\n"
        "C_composite = Σ(C_i × A_i) / Σ(A_i)\n"
        "\n"
        "Returns C_composite and total_area_ha."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "areas": {
                "type": "array",
                "description": (
                    "List of sub-area objects, each: "
                    "{C: number (0–1), area_ha: number (> 0)}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "C": {"type": "number"},
                        "area_ha": {"type": "number"},
                    },
                    "required": ["C", "area_ha"],
                },
            },
        },
        "required": ["areas"],
    },
)


@register(_composite_c_spec, write=False)
async def run_hydrology_composite_runoff_coeff(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    areas = a.get("areas")
    if areas is None:
        return json.dumps({"ok": False, "reason": "'areas' is required"})
    if not isinstance(areas, list):
        return json.dumps({"ok": False, "reason": "'areas' must be a list"})

    result = composite_runoff_coeff(areas)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_scs_runoff_depth
# ---------------------------------------------------------------------------

_scs_runoff_depth_spec = ToolSpec(
    name="hydrology_scs_runoff_depth",
    description=(
        "Compute the SCS/NRCS curve-number runoff depth.\n"
        "\n"
        "SCS equations (NEH-630, TR-55):\n"
        "  S = 25400/CN − 254    (potential maximum retention, mm)\n"
        "  Ia = 0.2 × S          (initial abstraction, mm)\n"
        "  Q = (P − Ia)² / (P − Ia + S)   for P > Ia, else 0\n"
        "\n"
        "CN ranges: 30 (good woods, low runoff) to 98 (impervious pavement).\n"
        "AMC-II (average moisture) is assumed.\n"
        "\n"
        "Returns Q_mm (runoff depth), S_mm, Ia_mm.\n"
        "\n"
        "Reference: USDA NRCS NEH Part 630, Chapter 10 (2004)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_mm": {
                "type": "number",
                "description": "Total storm rainfall (mm), >= 0.",
            },
            "CN": {
                "type": "number",
                "description": "SCS runoff curve number (1–100).",
            },
        },
        "required": ["P_mm", "CN"],
    },
)


@register(_scs_runoff_depth_spec, write=False)
async def run_hydrology_scs_runoff_depth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P_mm", "CN"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    result = scs_runoff_depth(a["P_mm"], a["CN"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_scs_peak_flow
# ---------------------------------------------------------------------------

_scs_peak_spec = ToolSpec(
    name="hydrology_scs_peak_flow",
    description=(
        "Compute the SCS/TR-55 graphical-peak flow for a small watershed.\n"
        "\n"
        "Procedure (TR-55 Chapter 4):\n"
        "  1. Compute runoff depth Q from CN and P.\n"
        "  2. Compute Ia/P ratio.\n"
        "  3. Interpolate unit peak discharge qu from TR-55 Appendix B\n"
        "     (tabulated by tc and Ia/P).\n"
        "  4. Qp = qu × A × Q.\n"
        "\n"
        "Valid range: tc 0.1–2.0 hr; drainage areas < ~25 km²;\n"
        "24-hour Type II/III rainfall distribution.\n"
        "\n"
        "Returns Qp_m3s, Q_mm, qu, Ia_P_ratio.\n"
        "\n"
        "Reference: USDA SCS TR-55 (1986), Chapter 4."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CN": {
                "type": "number",
                "description": "SCS runoff curve number (1–100).",
            },
            "A_km2": {
                "type": "number",
                "description": "Drainage area (km²), > 0.",
            },
            "tc_hr": {
                "type": "number",
                "description": "Time of concentration (hr). TR-55 valid range: 0.1–2.0 hr.",
            },
            "P_mm": {
                "type": "number",
                "description": "24-hour design rainfall (mm), > 0.",
            },
        },
        "required": ["CN", "A_km2", "tc_hr", "P_mm"],
    },
)


@register(_scs_peak_spec, write=False)
async def run_hydrology_scs_peak_flow(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("CN", "A_km2", "tc_hr", "P_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    result = scs_peak_flow(a["CN"], a["A_km2"], a["tc_hr"], a["P_mm"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_time_of_concentration
# ---------------------------------------------------------------------------

_tc_spec = ToolSpec(
    name="hydrology_time_of_concentration",
    description=(
        "Compute the time of concentration (tc) using one of three methods.\n"
        "\n"
        "Methods:\n"
        "\n"
        "'kirpich' — Kirpich (1940) formula for small agricultural watersheds:\n"
        "    tc [min] = 0.0195 × L^0.77 × S^-0.385;  S = H/L.\n"
        "    Inputs: L_m (channel length, m), H_m (elevation drop, m).\n"
        "\n"
        "'nrcs_velocity' — NRCS velocity method (TR-55 §3.2):\n"
        "    V = k × sqrt(slope)  [ft/s, converted internally];\n"
        "    tc = L / V.\n"
        "    Inputs: L_m, slope (m/m), cover (land cover type string).\n"
        "    Valid cover types: forest_with_litter, range_grass, short_grass_pasture,\n"
        "    cultivated_straight_rows, nearly_bare_fallow, grassed_waterway,\n"
        "    paved_gutter, concrete_channel.\n"
        "\n"
        "'sheet_shallow_channel' — TR-55 three-segment method (§3.1–3.3):\n"
        "    Segment 1 (sheet flow): TR-55 Eq. 3-3.\n"
        "    Segment 2 (shallow concentrated): NRCS velocity.\n"
        "    Segment 3 (channel): Manning's equation.\n"
        "    Inputs: sheet_length_m, sheet_n, sheet_P2_mm, sheet_slope,\n"
        "            shallow_length_m, shallow_slope, shallow_cover,\n"
        "            channel_length_m, channel_slope, channel_area_m2,\n"
        "            channel_wetted_perim_m, channel_n.\n"
        "\n"
        "Returns tc_hr, tc_min, method, warnings (and method-specific sub-times)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["kirpich", "nrcs_velocity", "sheet_shallow_channel"],
                "description": "Time-of-concentration method.",
            },
            "L_m": {"type": "number", "description": "Flow/channel length (m)."},
            "H_m": {"type": "number", "description": "Elevation drop (m). Kirpich only."},
            "slope": {"type": "number", "description": "Average slope (m/m). nrcs_velocity only."},
            "cover": {"type": "string", "description": "Land cover type. nrcs_velocity only."},
            "sheet_length_m": {"type": "number"},
            "sheet_n": {"type": "number", "description": "Manning n for sheet flow."},
            "sheet_P2_mm": {"type": "number", "description": "2-yr 24-hr rainfall (mm)."},
            "sheet_slope": {"type": "number"},
            "shallow_length_m": {"type": "number"},
            "shallow_slope": {"type": "number"},
            "shallow_cover": {"type": "string"},
            "channel_length_m": {"type": "number"},
            "channel_slope": {"type": "number"},
            "channel_area_m2": {"type": "number", "description": "Channel cross-section area (m²)."},
            "channel_wetted_perim_m": {"type": "number", "description": "Channel wetted perimeter (m)."},
            "channel_n": {"type": "number", "description": "Manning n for channel."},
        },
        "required": ["method"],
    },
)


@register(_tc_spec, write=False)
async def run_hydrology_time_of_concentration(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    method = a.get("method")
    if not method:
        return json.dumps({"ok": False, "reason": "'method' is required"})

    kwargs = {k: v for k, v in a.items() if k != "method"}
    result = time_of_concentration(method, **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_idf_intensity
# ---------------------------------------------------------------------------

_idf_spec = ToolSpec(
    name="hydrology_idf_intensity",
    description=(
        "Compute design rainfall intensity from a fitted IDF (Intensity-Duration-\n"
        "Frequency) formula.\n"
        "\n"
        "Formula:  i = a / (t + b)^c   [mm/hr]\n"
        "  t = storm duration (min)\n"
        "  a, b, c = site-specific regression coefficients\n"
        "\n"
        "The parameters a, b, c are obtained by fitting regional IDF data\n"
        "(e.g. NOAA Atlas 14, SANRAL TRH 16, or similar) for the required\n"
        "return period.\n"
        "\n"
        "Returns intensity_mm_hr."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "duration_min": {
                "type": "number",
                "description": "Storm duration / time of concentration (min), > 0.",
            },
            "a": {
                "type": "number",
                "description": "IDF scale coefficient (mm/hr · min^c), > 0.",
            },
            "b": {
                "type": "number",
                "description": "IDF time offset (min), >= 0.",
            },
            "c": {
                "type": "number",
                "description": "IDF decay exponent (dimensionless), > 0.",
            },
        },
        "required": ["duration_min", "a", "b", "c"],
    },
)


@register(_idf_spec, write=False)
async def run_hydrology_idf_intensity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("duration_min", "a", "b", "c"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    result = idf_intensity(a["duration_min"], a["a"], a["b"], a["c"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_detention_storage
# ---------------------------------------------------------------------------

_detention_spec = ToolSpec(
    name="hydrology_detention_storage",
    description=(
        "Estimate required detention basin storage volume by the modified-rational\n"
        "method.\n"
        "\n"
        "V ≈ 0.5 × (Q_in − Q_out) × tc × 3600   [m³]\n"
        "(triangular hydrograph approximation)\n"
        "\n"
        "Applicable to small urban catchments (A < ~80 ha, tc < 3 hr) where the\n"
        "rational method is valid.\n"
        "\n"
        "Returns V_m3 (required storage volume)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_in_cms": {
                "type": "number",
                "description": "Pre-development or design-storm peak inflow (m³/s).",
            },
            "Q_out_cms": {
                "type": "number",
                "description": "Allowable release rate / outflow (m³/s).",
            },
            "tc_hr": {
                "type": "number",
                "description": "Time of concentration (hr).",
            },
        },
        "required": ["Q_in_cms", "Q_out_cms", "tc_hr"],
    },
)


@register(_detention_spec, write=False)
async def run_hydrology_detention_storage(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Q_in_cms", "Q_out_cms", "tc_hr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    result = detention_storage_modified_rational(
        a["Q_in_cms"], a["Q_out_cms"], a["tc_hr"]
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_storage_indication_route
# ---------------------------------------------------------------------------

_si_route_spec = ToolSpec(
    name="hydrology_storage_indication_route",
    description=(
        "Route an inflow hydrograph through a detention basin using the\n"
        "storage-indication (Puls / level-pool) method.\n"
        "\n"
        "Routing equation (continuity, Δt time step):\n"
        "    (S/Δt + O/2)|₂ = (I₁ + I₂)/2 + (S/Δt − O/2)|₁\n"
        "\n"
        "Outflow is obtained from the user-supplied stage-storage-outflow\n"
        "rating table {storage_m3, outflow_m3s} via linear interpolation.\n"
        "\n"
        "Warns if storage exceeds the rating table (overtopping risk).\n"
        "\n"
        "Returns outflow hydrograph (outflow_m3s list), storage time series\n"
        "(storage_m3 list), peak_outflow_m3s, peak_storage_m3.\n"
        "\n"
        "Reference: Chow, Maidment & Mays (1988) — Applied Hydrology, §8.4."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "inflow_series": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Inflow hydrograph ordinates (m³/s) at uniform time step dt_s.",
            },
            "outflow_rating": {
                "type": "array",
                "description": (
                    "Stage-storage-outflow table sorted by storage_m3 ascending. "
                    "Each entry: {storage_m3: number, outflow_m3s: number}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "storage_m3": {"type": "number"},
                        "outflow_m3s": {"type": "number"},
                    },
                    "required": ["storage_m3", "outflow_m3s"],
                },
            },
            "dt_s": {
                "type": "number",
                "description": "Time step (s), > 0.",
            },
            "S0_m3": {
                "type": "number",
                "description": "Initial basin storage (m³, default 0).",
            },
        },
        "required": ["inflow_series", "outflow_rating", "dt_s"],
    },
)


@register(_si_route_spec, write=False)
async def run_hydrology_storage_indication_route(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("inflow_series", "outflow_rating", "dt_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"'{field}' is required"})

    S0 = float(a.get("S0_m3", 0.0))
    result = storage_indication_route(
        a["inflow_series"], a["outflow_rating"], a["dt_s"], S0
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydrology_storm_sewer_pipe_size
# ---------------------------------------------------------------------------

_pipe_size_spec = ToolSpec(
    name="hydrology_storm_sewer_pipe_size",
    description=(
        "Select the minimum standard circular storm-sewer pipe diameter\n"
        "using Manning's full-flow equation.\n"
        "\n"
        "Manning full-flow:  Q = (1/n) · (π/4)·D² · (D/4)^(2/3) · S^(1/2)\n"
        "\n"
        "The smallest standard diameter (from the ASTM/ISO nominal series)\n"
        "where Q_full ≥ Q_design / freeboard_fraction is selected.\n"
        "If no standard size fits, the minimum required diameter is computed\n"
        "analytically and a warning is issued.\n"
        "\n"
        "Warns on: undersized pipe, freeboard exceedance, velocity below\n"
        "self-cleansing threshold (0.6 m/s).\n"
        "\n"
        "Returns diameter_m, diameter_mm, Q_full_m3s, utilisation, freeboard_ok.\n"
        "\n"
        "Reference: ASCE MOP 36 (2007); Ven Te Chow (1959)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_cms": {
                "type": "number",
                "description": "Design peak flow (m³/s), > 0.",
            },
            "slope": {
                "type": "number",
                "description": "Hydraulic gradient (m/m), > 0.",
            },
            "n": {
                "type": "number",
                "description": (
                    "Manning's roughness coefficient (default 0.013 for concrete). "
                    "Typical: 0.010 PVC, 0.011 HDPE, 0.013 concrete/clay."
                ),
            },
            "min_d_m": {
                "type": "number",
                "description": "Minimum acceptable diameter (m, default 0.15 m = 150 mm).",
            },
            "max_d_m": {
                "type": "number",
                "description": "Maximum diameter to consider (m, default 3.0 m).",
            },
            "freeboard_fraction": {
                "type": "number",
                "description": (
                    "Ratio of design flow to full-flow capacity (default 0.85). "
                    "E.g. 0.85 means pipe designed to flow 85% full."
                ),
            },
        },
        "required": ["Q_cms", "slope"],
    },
)


@register(_pipe_size_spec, write=False)
async def run_hydrology_storm_sewer_pipe_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("Q_cms") is None:
        return json.dumps({"ok": False, "reason": "'Q_cms' is required"})
    if a.get("slope") is None:
        return json.dumps({"ok": False, "reason": "'slope' is required"})

    kwargs: dict = {}
    for opt in ("n", "min_d_m", "max_d_m", "freeboard_fraction"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = storm_sewer_pipe_size(a["Q_cms"], a["slope"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)
