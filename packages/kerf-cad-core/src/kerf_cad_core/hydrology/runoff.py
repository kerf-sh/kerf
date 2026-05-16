"""
kerf_cad_core.hydrology.runoff — Stormwater / drainage hydrology calculations.

Distinct from civil.hydraulics (pressurised pipe-network flow).
This module covers rainfall-runoff analysis, peak flow estimation,
time of concentration, IDF intensity, detention-basin storage routing,
and rational-method storm-sewer pipe sizing.

All functions return plain dicts::

    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Non-fatal conditions (undersized pipe, freeboard
exceedance) are appended to the ``"warnings"`` list in the result.

Public functions
----------------
rational_peak_flow(C, i_mm_hr, A_ha)
    Rational method peak flow.  Q = C·i·A.

composite_runoff_coeff(areas)
    Area-weighted composite runoff coefficient from sub-areas.

scs_runoff_depth(P_mm, CN)
    SCS curve-number runoff depth (NEH-630 / TR-55).

scs_peak_flow(CN, A_km2, tc_hr, P_mm)
    SCS/TR-55 graphical-peak-rate approximation.

time_of_concentration(method, **kwargs)
    Time of concentration.  Methods: "kirpich", "nrcs_velocity", "sheet_shallow_channel".

idf_intensity(duration_min, a, b, c)
    IDF intensity from fitted formula  i = a / (t + b)^c  [mm/hr].

detention_storage_modified_rational(Q_in_cms, Q_out_cms, tc_hr)
    Required detention volume by modified-rational method.

storage_indication_route(inflow_series, outflow_rating, dt_s, S0_m3)
    Simple storage-indication (Puls) routing through a detention basin.

storm_sewer_pipe_size(Q_cms, slope, n, min_d_m, max_d_m)
    Select standard circular pipe diameter by Manning full-flow.
    Warns on undersized pipe or freeboard exceedance.

Units
-----
All SI unless explicitly stated.  Intensity in mm/hr; areas in ha or km²
where noted; flow in m³/s; volumes in m³; time in hours or minutes where noted.

References
----------
ASCE/EWRI 45-05 — Rational Method for stormwater peak flow
TR-55 (USDA SCS 1986) — Urban Hydrology for Small Watersheds
NRCS National Engineering Handbook Part 630 (NEH-630)
Chow, Maidment & Mays (1988) — Applied Hydrology, McGraw-Hill
Kirpich, Z.P. (1940) — Time of Concentration of Small Agricultural Watersheds,
    Civil Engineering vol. 10

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665       # gravitational acceleration (m/s²)
_EPS = 1.0e-12

# NRCS velocity-method overland-flow velocity factors (ft/s per unit slope^0.5)
# keyed by cover description → k factor (ft/s)
# Reference: TR-55 Table 3-1 (converted to m/s internally)
_NRCS_K_COVERS: dict[str, float] = {
    "forest_with_litter": 0.9,       # ft/s
    "range_grass":        2.5,
    "short_grass_pasture": 2.5,
    "cultivated_straight_rows": 2.5,
    "nearly_bare_fallow": 5.0,
    "grassed_waterway":   7.0,
    "paved_gutter":       20.0,
    "concrete_channel":   20.0,
}

# Manning's n for pipe materials — full-flow pipe sizing
_MANNING_N_PIPE: dict[str, float] = {
    "concrete": 0.013,
    "pvc":      0.010,
    "hdpe":     0.011,
    "clay":     0.013,
    "cast_iron": 0.013,
}

# Standard circular pipe diameters (m) — ASTM / ISO nominal series
_STANDARD_DIAMETERS_M: list[float] = [
    0.150, 0.200, 0.225, 0.250, 0.300, 0.375, 0.450, 0.525,
    0.600, 0.675, 0.750, 0.900, 1.050, 1.200, 1.350, 1.500,
    1.650, 1.800, 2.100, 2.400, 2.700, 3.000,
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    """Return error string if *value* is not a finite positive number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    """Return error string if *value* is not a finite non-negative number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# ---------------------------------------------------------------------------
# 1.  Rational method peak flow
# ---------------------------------------------------------------------------

def rational_peak_flow(
    C: float,
    i_mm_hr: float,
    A_ha: float,
) -> dict:
    """Rational method peak flow.

    Formula:  Q = C · i · A / 360
    where Q is in m³/s, i in mm/hr, A in ha.

    The conversion factor 360 = 3600 s/hr × 1000 mm/m × 10000 m²/ha × 1e-6
    collapses to  Q[m³/s] = C · (i/1000/3600) · (A × 10000)
                           = C · i · A / 360.

    Parameters
    ----------
    C       : Runoff coefficient (0 < C ≤ 1.0).
    i_mm_hr : Rainfall intensity (mm/hr) for the design return period.
    A_ha    : Catchment area (ha).

    Returns
    -------
    dict {ok, Q_m3s, Q_L_per_s, warnings}

    References
    ----------
    ASCE/EWRI 45-05 — Rational Method for stormwater peak flow.
    """
    e = (_guard_positive("C", C) or
         _guard_positive("i_mm_hr", i_mm_hr) or
         _guard_positive("A_ha", A_ha))
    if e:
        return _err(e)
    C = float(C)
    i = float(i_mm_hr)
    A = float(A_ha)
    if C > 1.0:
        return _err(f"C must be <= 1.0 (runoff coefficient), got {C}")

    Q = C * i * A / 360.0   # m³/s
    warns: list[str] = []
    return {
        "ok": True,
        "Q_m3s": round(Q, 6),
        "Q_L_per_s": round(Q * 1000.0, 4),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2.  Composite runoff coefficient
# ---------------------------------------------------------------------------

def composite_runoff_coeff(areas: list[dict]) -> dict:
    """Area-weighted composite runoff coefficient.

    Parameters
    ----------
    areas : list of dicts, each with:
        {C: float (0–1), area_ha: float (> 0)}

    Returns
    -------
    dict {ok, C_composite, total_area_ha, warnings}
    """
    if not isinstance(areas, list) or len(areas) == 0:
        return _err("areas must be a non-empty list")

    total_w = 0.0
    total_CA = 0.0
    for i, item in enumerate(areas):
        if not isinstance(item, dict):
            return _err(f"areas[{i}] must be an object")
        e = _guard_positive(f"areas[{i}].area_ha", item.get("area_ha"))
        if e:
            return _err(e)
        c_val = item.get("C")
        if c_val is None:
            return _err(f"areas[{i}] missing 'C'")
        e2 = _guard_positive(f"areas[{i}].C", c_val)
        if e2:
            return _err(e2)
        c = float(c_val)
        a = float(item["area_ha"])
        if c > 1.0:
            return _err(f"areas[{i}].C must be <= 1.0, got {c}")
        total_w += a
        total_CA += c * a

    C_comp = total_CA / total_w
    return {
        "ok": True,
        "C_composite": round(C_comp, 6),
        "total_area_ha": round(total_w, 6),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 3.  SCS curve-number runoff depth
# ---------------------------------------------------------------------------

def scs_runoff_depth(P_mm: float, CN: float) -> dict:
    """SCS/NRCS curve-number runoff depth.

    The SCS method (NEH-630, TR-55):
        S = 25400/CN − 254    (potential maximum retention, mm)
        Ia = 0.2 · S          (initial abstraction, mm)
        Q = (P − Ia)² / (P − Ia + S)   if  P > Ia, else 0

    Parameters
    ----------
    P_mm : Total storm rainfall (mm).
    CN   : SCS runoff curve number (1–100).

    Returns
    -------
    dict {ok, Q_mm, S_mm, Ia_mm, warnings}

    References
    ----------
    USDA NRCS NEH Part 630, Chapter 10 (2004).
    """
    e = (_guard_nonneg("P_mm", P_mm) or
         _guard_positive("CN", CN))
    if e:
        return _err(e)
    P = float(P_mm)
    CN = float(CN)
    if CN > 100.0:
        return _err(f"CN must be <= 100, got {CN}")
    if CN < 1.0:
        return _err(f"CN must be >= 1, got {CN}")

    S = 25400.0 / CN - 254.0   # mm
    Ia = 0.2 * S
    warns: list[str] = []
    if P <= Ia:
        Q = 0.0
    else:
        Q = (P - Ia) ** 2 / (P - Ia + S)

    return {
        "ok": True,
        "Q_mm": round(Q, 4),
        "S_mm": round(S, 4),
        "Ia_mm": round(Ia, 4),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4.  SCS / TR-55 graphical peak flow
# ---------------------------------------------------------------------------

# TR-55 unit-peak-discharge (qu) lookup by Ia/P ratio (0.10, 0.20, 0.30, 0.35, 0.40, 0.45, 0.50)
# at tc from 0.1 to 2.0 hr.  qu in m³/s per km² per mm of runoff depth (converted from cfs/mi²/in).
# Conversion: 1 cfs/mi²/in = 4.329e-3 m³/s·km²⁻¹·mm⁻¹  (Appendix B, TR-55)
_CFS_PER_MI2_IN_TO_M3S_KM2_MM = 4.329e-3

# TR-55 Table B-1/B-2 unit peak discharges (cfs / mi² / in)  [Ia/P = 0.10 columns only]
# tc_hr → qu (cfs/mi²/in) for Ia/P = 0.10 and Ia/P = 0.30
# Source: TR-55 Appendix B, SCS 1986.  Approximate tabular values.
# For intermediate Ia/P we linearly interpolate between the 0.10 and 0.30 columns.
_TR55_TC_HR = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
               1.2, 1.4, 1.6, 1.8, 2.0]

# qu in cfs/mi²/in  (Ia/P = 0.10 and 0.30)
_TR55_QU_010 = [483, 433, 393, 362, 337, 316, 298, 282, 268, 256,
                235, 217, 203, 190, 179]
_TR55_QU_030 = [284, 255, 232, 213, 197, 184, 173, 163, 154, 146,
                133, 122, 113, 106, 99]


def _tr55_qu(tc_hr: float, ia_p_ratio: float) -> float:
    """Interpolate TR-55 unit peak discharge (m³/s per km² per mm runoff)."""
    # Clamp Ia/P ratio to [0.10, 0.30]
    frac = min(max(ia_p_ratio, 0.10), 0.30)
    weight = (frac - 0.10) / 0.20   # 0 at 0.10, 1 at 0.30

    tc = max(0.1, min(tc_hr, 2.0))
    # Find bounding indices in _TR55_TC_HR
    tcs = _TR55_TC_HR
    if tc <= tcs[0]:
        i0, i1 = 0, 0
    elif tc >= tcs[-1]:
        i0, i1 = len(tcs) - 1, len(tcs) - 1
    else:
        i0 = 0
        for k in range(len(tcs) - 1):
            if tcs[k] <= tc <= tcs[k + 1]:
                i0 = k
                break
        i1 = i0 + 1

    if i0 == i1:
        qu010 = _TR55_QU_010[i0]
        qu030 = _TR55_QU_030[i0]
    else:
        t_frac = (tc - tcs[i0]) / (tcs[i1] - tcs[i0])
        qu010 = _TR55_QU_010[i0] + t_frac * (_TR55_QU_010[i1] - _TR55_QU_010[i0])
        qu030 = _TR55_QU_030[i0] + t_frac * (_TR55_QU_030[i1] - _TR55_QU_030[i0])

    qu_cfs = qu010 + weight * (qu030 - qu010)
    return qu_cfs * _CFS_PER_MI2_IN_TO_M3S_KM2_MM


def scs_peak_flow(
    CN: float,
    A_km2: float,
    tc_hr: float,
    P_mm: float,
) -> dict:
    """SCS/TR-55 graphical-peak-rate peak flow.

    Procedure (TR-55 Chapter 4):
        1. Compute runoff depth Q_mm from CN and P_mm.
        2. Compute Ia/P = (0.2·S) / P.
        3. Look up unit peak discharge qu (m³/s per km² per mm) from
           TR-55 Appendix B using tc and Ia/P (interpolated).
        4. Qp = qu × A × Q_mm.

    Parameters
    ----------
    CN    : SCS curve number (1–100).
    A_km2 : Drainage area (km²).
    tc_hr : Time of concentration (hr, 0.1–2.0 hr valid TR-55 range).
    P_mm  : 24-hour design rainfall (mm).

    Returns
    -------
    dict {ok, Qp_m3s, Q_mm, qu_m3s_per_km2_per_mm, Ia_P_ratio, warnings}
    """
    e = (_guard_positive("CN", CN) or
         _guard_positive("A_km2", A_km2) or
         _guard_positive("tc_hr", tc_hr) or
         _guard_positive("P_mm", P_mm))
    if e:
        return _err(e)
    CN_f = float(CN)
    A = float(A_km2)
    tc = float(tc_hr)
    P = float(P_mm)

    if CN_f > 100 or CN_f < 1:
        return _err(f"CN must be 1–100, got {CN_f}")

    runoff = scs_runoff_depth(P, CN_f)
    if not runoff["ok"]:
        return _err(runoff["reason"])

    Q_mm = runoff["Q_mm"]
    S_mm = runoff["S_mm"]
    Ia = 0.2 * S_mm

    warns: list[str] = []
    if P < _EPS:
        return _err("P_mm must be > 0")

    ia_p = Ia / P
    if ia_p > 0.5:
        warns.append(
            f"Ia/P = {ia_p:.3f} > 0.50; TR-55 is not applicable for very large "
            "initial abstraction relative to rainfall.  Results are extrapolated."
        )

    qu = _tr55_qu(tc, ia_p)

    if tc < 0.1 or tc > 2.0:
        warns.append(
            f"tc_hr = {tc:.3f} is outside the TR-55 valid range [0.1, 2.0] hr. "
            "qu is extrapolated at boundary."
        )

    Qp = qu * A * Q_mm   # m³/s

    return {
        "ok": True,
        "Qp_m3s": round(Qp, 6),
        "Q_mm": round(Q_mm, 4),
        "qu_m3s_per_km2_per_mm": round(qu, 6),
        "Ia_P_ratio": round(ia_p, 4),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5.  Time of concentration
# ---------------------------------------------------------------------------

def _kirpich_tc(L_m: float, H_m: float) -> dict:
    """Kirpich (1940) time of concentration for small agricultural watersheds.

    tc = 0.0195 · L^0.77 / S^0.385   (minutes)
    S = H / L  (average slope, m/m)

    Parameters
    ----------
    L_m : Channel length from headwater to outlet (m).
    H_m : Total elevation difference (m).

    Returns {ok, tc_hr, tc_min, method, warnings}
    """
    e = (_guard_positive("L_m", L_m) or _guard_positive("H_m", H_m))
    if e:
        return _err(e)
    L = float(L_m)
    H = float(H_m)
    S = H / L
    # Kirpich formula (SI version):
    #   tc [min] = 0.0195 × L[m]^0.77 × S^-0.385
    tc_min = 0.0195 * (L ** 0.77) * (S ** -0.385)
    return {
        "ok": True,
        "tc_hr": round(tc_min / 60.0, 5),
        "tc_min": round(tc_min, 4),
        "method": "kirpich",
        "warnings": [],
    }


def _nrcs_velocity_tc(
    L_m: float,
    slope: float,
    cover: str,
) -> dict:
    """NRCS velocity method for time of concentration (TR-55 §3).

    V = k · sqrt(slope)   [ft/s → converted to m/s]
    tc = L / V             [s → hours]

    cover must be one of:
        'forest_with_litter', 'range_grass', 'short_grass_pasture',
        'cultivated_straight_rows', 'nearly_bare_fallow',
        'grassed_waterway', 'paved_gutter', 'concrete_channel'

    Parameters
    ----------
    L_m    : Flow length (m).
    slope  : Average slope (m/m).
    cover  : Land cover type string (see above).
    """
    e = (_guard_positive("L_m", L_m) or _guard_positive("slope", slope))
    if e:
        return _err(e)
    L = float(L_m)
    S = float(slope)
    if cover not in _NRCS_K_COVERS:
        valid = ", ".join(sorted(_NRCS_K_COVERS.keys()))
        return _err(f"cover '{cover}' not recognised; valid: {valid}")

    k_fps = _NRCS_K_COVERS[cover]   # ft/s
    # V [ft/s] = k * sqrt(S);  convert to m/s: 1 ft = 0.3048 m
    V_fps = k_fps * math.sqrt(S)
    V_ms = V_fps * 0.3048
    tc_s = L / V_ms
    tc_hr = tc_s / 3600.0
    warns: list[str] = []
    if tc_hr < 0.1:
        warns.append(
            f"tc = {tc_hr:.4f} hr is very short; NRCS velocity method is intended "
            "for overland/shallow concentrated flow segments."
        )
    return {
        "ok": True,
        "tc_hr": round(tc_hr, 5),
        "tc_min": round(tc_hr * 60.0, 4),
        "velocity_m_per_s": round(V_ms, 4),
        "method": "nrcs_velocity",
        "warnings": warns,
    }


def _sheet_shallow_channel_tc(
    sheet_length_m: float,
    sheet_n: float,
    sheet_P2_mm: float,
    sheet_slope: float,
    shallow_length_m: float,
    shallow_slope: float,
    shallow_cover: str,
    channel_length_m: float,
    channel_slope: float,
    channel_area_m2: float,
    channel_wetted_perim_m: float,
    channel_n: float,
) -> dict:
    """Three-segment time of concentration (TR-55 §3.1–3.3).

    Segment 1 — Sheet flow (TR-55 eq. 3-3):
        tt = 0.091 · (n · L)^0.8 / (P2^0.5 · slope^0.4)   [hr]
    where n is Manning's n for sheet flow, L in m, P2 = 2-yr 24-hr rainfall in mm.

    Segment 2 — Shallow concentrated flow:
        Uses NRCS velocity method.

    Segment 3 — Channel flow:
        V = (1/n) · R^(2/3) · S^(1/2)   (Manning; R = A/P)
        tt = L / V   [s → hr]

    Returns {ok, tc_hr, tc_min, tt_sheet_hr, tt_shallow_hr, tt_channel_hr, warnings}
    """
    warns: list[str] = []

    # --- Segment 1: Sheet flow ---
    e = (_guard_positive("sheet_length_m", sheet_length_m) or
         _guard_positive("sheet_n", sheet_n) or
         _guard_positive("sheet_P2_mm", sheet_P2_mm) or
         _guard_positive("sheet_slope", sheet_slope))
    if e:
        return _err(e)
    s1_L = float(sheet_length_m)
    s1_n = float(sheet_n)
    s1_P2 = float(sheet_P2_mm)
    s1_S = float(sheet_slope)
    if s1_L > 300.0:
        warns.append(
            f"sheet_length_m = {s1_L:.1f} m exceeds the TR-55 recommended maximum "
            "of ~100 m (300 ft) for the sheet-flow equation."
        )
    # TR-55 Eq. 3-3 (SI adaptation):
    #   tt [hr] = 0.091 × (n × L)^0.8 / (P2_mm/25.4)^0.5 / S^0.4
    # P2 must be in inches for the standard constant; convert
    P2_in = s1_P2 / 25.4
    # L in feet for standard constant; convert
    L_ft = s1_L / 0.3048
    tt_sheet_hr = 0.091 * ((s1_n * L_ft) ** 0.8) / (P2_in ** 0.5) / (s1_S ** 0.4)

    # --- Segment 2: Shallow concentrated flow ---
    e2 = (_guard_positive("shallow_length_m", shallow_length_m) or
          _guard_positive("shallow_slope", shallow_slope))
    if e2:
        return _err(e2)
    sc_res = _nrcs_velocity_tc(
        float(shallow_length_m), float(shallow_slope), shallow_cover
    )
    if not sc_res["ok"]:
        return _err(f"shallow segment: {sc_res['reason']}")
    tt_shallow_hr = sc_res["tc_hr"]
    warns.extend(sc_res.get("warnings", []))

    # --- Segment 3: Channel flow ---
    e3 = (_guard_positive("channel_length_m", channel_length_m) or
          _guard_positive("channel_slope", channel_slope) or
          _guard_positive("channel_area_m2", channel_area_m2) or
          _guard_positive("channel_wetted_perim_m", channel_wetted_perim_m) or
          _guard_positive("channel_n", channel_n))
    if e3:
        return _err(e3)
    ch_A = float(channel_area_m2)
    ch_P = float(channel_wetted_perim_m)
    ch_S = float(channel_slope)
    ch_n = float(channel_n)
    ch_L = float(channel_length_m)
    R = ch_A / ch_P
    V_ch = (1.0 / ch_n) * (R ** (2.0 / 3.0)) * math.sqrt(ch_S)
    if V_ch < _EPS:
        return _err("channel velocity is effectively zero; check channel_slope and channel_n")
    tt_channel_hr = (ch_L / V_ch) / 3600.0

    tc_hr = tt_sheet_hr + tt_shallow_hr + tt_channel_hr
    return {
        "ok": True,
        "tc_hr": round(tc_hr, 5),
        "tc_min": round(tc_hr * 60.0, 4),
        "tt_sheet_hr": round(tt_sheet_hr, 5),
        "tt_shallow_hr": round(tt_shallow_hr, 5),
        "tt_channel_hr": round(tt_channel_hr, 5),
        "method": "sheet_shallow_channel",
        "warnings": warns,
    }


def time_of_concentration(method: str, **kwargs) -> dict:
    """Time of concentration dispatcher.

    Parameters
    ----------
    method : str
        One of: 'kirpich', 'nrcs_velocity', 'sheet_shallow_channel'.

    For 'kirpich':
        L_m : Channel length (m).
        H_m : Elevation drop (m).

    For 'nrcs_velocity':
        L_m    : Flow length (m).
        slope  : Average slope (m/m).
        cover  : Land cover string (see _NRCS_K_COVERS keys).

    For 'sheet_shallow_channel':
        sheet_length_m, sheet_n, sheet_P2_mm, sheet_slope,
        shallow_length_m, shallow_slope, shallow_cover,
        channel_length_m, channel_slope, channel_area_m2,
        channel_wetted_perim_m, channel_n.

    Returns
    -------
    dict {ok, tc_hr, tc_min, method, warnings, ...method-specific keys}
    """
    if method == "kirpich":
        L = kwargs.get("L_m")
        H = kwargs.get("H_m")
        if L is None:
            return _err("kirpich requires L_m")
        if H is None:
            return _err("kirpich requires H_m")
        return _kirpich_tc(float(L), float(H))

    elif method == "nrcs_velocity":
        L = kwargs.get("L_m")
        slope = kwargs.get("slope")
        cover = kwargs.get("cover", "")
        if L is None:
            return _err("nrcs_velocity requires L_m")
        if slope is None:
            return _err("nrcs_velocity requires slope")
        if not cover:
            return _err("nrcs_velocity requires cover")
        return _nrcs_velocity_tc(float(L), float(slope), str(cover))

    elif method == "sheet_shallow_channel":
        required = [
            "sheet_length_m", "sheet_n", "sheet_P2_mm", "sheet_slope",
            "shallow_length_m", "shallow_slope", "shallow_cover",
            "channel_length_m", "channel_slope", "channel_area_m2",
            "channel_wetted_perim_m", "channel_n",
        ]
        for r in required:
            if r not in kwargs:
                return _err(f"sheet_shallow_channel requires '{r}'")
        return _sheet_shallow_channel_tc(
            sheet_length_m=float(kwargs["sheet_length_m"]),
            sheet_n=float(kwargs["sheet_n"]),
            sheet_P2_mm=float(kwargs["sheet_P2_mm"]),
            sheet_slope=float(kwargs["sheet_slope"]),
            shallow_length_m=float(kwargs["shallow_length_m"]),
            shallow_slope=float(kwargs["shallow_slope"]),
            shallow_cover=str(kwargs["shallow_cover"]),
            channel_length_m=float(kwargs["channel_length_m"]),
            channel_slope=float(kwargs["channel_slope"]),
            channel_area_m2=float(kwargs["channel_area_m2"]),
            channel_wetted_perim_m=float(kwargs["channel_wetted_perim_m"]),
            channel_n=float(kwargs["channel_n"]),
        )

    else:
        valid = "kirpich, nrcs_velocity, sheet_shallow_channel"
        return _err(f"unknown method '{method}'; valid: {valid}")


# ---------------------------------------------------------------------------
# 6.  IDF intensity from fitted formula
# ---------------------------------------------------------------------------

def idf_intensity(
    duration_min: float,
    a: float,
    b: float,
    c: float,
) -> dict:
    """IDF rainfall intensity from fitted formula.

    Formula:  i = a / (t + b)^c   [mm/hr]
    where t is duration in minutes.

    Typical parameter sources: regional IDF studies, NOAA Atlas 14,
    SANRAL (South Africa), etc.

    Parameters
    ----------
    duration_min : Storm duration / time of concentration (min), > 0.
    a            : Scale coefficient (mm/hr · min^c).
    b            : Time offset (min), >= 0.
    c            : Decay exponent (dimensionless), > 0.

    Returns
    -------
    dict {ok, intensity_mm_hr, duration_min, warnings}
    """
    e = (_guard_positive("duration_min", duration_min) or
         _guard_positive("a", a) or
         _guard_nonneg("b", b) or
         _guard_positive("c", c))
    if e:
        return _err(e)
    t = float(duration_min)
    a_f = float(a)
    b_f = float(b)
    c_f = float(c)

    denom = (t + b_f) ** c_f
    if denom < _EPS:
        return _err(f"(duration_min + b)^c ≈ 0; check parameters")
    i = a_f / denom
    warns: list[str] = []
    return {
        "ok": True,
        "intensity_mm_hr": round(i, 4),
        "duration_min": t,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7.  Detention basin — modified-rational method storage
# ---------------------------------------------------------------------------

def detention_storage_modified_rational(
    Q_in_cms: float,
    Q_out_cms: float,
    tc_hr: float,
) -> dict:
    """Required detention basin volume by modified-rational method.

    The modified-rational method estimates required storage volume as:
        V = (Q_in − Q_out) × tc × 3600 × correction_factor

    The correction factor = 0.5 (triangular hydrograph approximation):
        V ≈ 0.5 × (Q_in − Q_out) × tc × 3600   [m³]

    This is the simplest formulation, valid for small urban catchments where
    the rational method is applicable (A < ~80 ha, tc < 3 hr).

    Parameters
    ----------
    Q_in_cms  : Pre-development (or design-storm) inflow peak (m³/s).
    Q_out_cms : Allowable release rate / outflow (m³/s).
    tc_hr     : Time of concentration (hr).

    Returns
    -------
    dict {ok, V_m3, Q_in_cms, Q_out_cms, tc_hr, warnings}

    References
    ----------
    Wanielista, Kersten & Eaglin (1997) — Hydrology: Water Quantity and Quality
    Control, 2nd ed., §7.4.
    """
    e = (_guard_positive("Q_in_cms", Q_in_cms) or
         _guard_nonneg("Q_out_cms", Q_out_cms) or
         _guard_positive("tc_hr", tc_hr))
    if e:
        return _err(e)
    Qi = float(Q_in_cms)
    Qo = float(Q_out_cms)
    tc = float(tc_hr)

    warns: list[str] = []
    if Qo >= Qi:
        warns.append(
            f"Q_out_cms ({Qo:.4f}) >= Q_in_cms ({Qi:.4f}); no detention required. "
            "V returned as 0."
        )
        V = 0.0
    else:
        V = 0.5 * (Qi - Qo) * tc * 3600.0

    return {
        "ok": True,
        "V_m3": round(V, 3),
        "Q_in_cms": Qi,
        "Q_out_cms": Qo,
        "tc_hr": tc,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 8.  Storage-indication (Puls) routing
# ---------------------------------------------------------------------------

def storage_indication_route(
    inflow_series: list[float],
    outflow_rating: list[dict],
    dt_s: float,
    S0_m3: float = 0.0,
) -> dict:
    """Simple storage-indication (Puls / level-pool) routing.

    Routing equation (continuity):
        (I1 + I2)/2 · Δt − (O1 + O2)/2 · Δt = S2 − S1
    Rearranged to the storage-indication form:
        (S2/Δt + O2/2) = (I1 + I2)/2 + (S1/Δt − O1/2)

    The outflow is determined from the storage-indication curve
    (S/Δt + O/2) vs O via linear interpolation of the provided
    outflow_rating table {storage_m3, outflow_m3s}.

    Parameters
    ----------
    inflow_series : list of float
        Inflow hydrograph ordinates (m³/s) at equal time steps dt_s.
    outflow_rating : list of dict
        Stage-storage-outflow table.  Each entry:
        {storage_m3: float, outflow_m3s: float}.
        Must be sorted by storage_m3 ascending.  At least 2 entries required.
    dt_s : float
        Time step (s), > 0.
    S0_m3 : float
        Initial storage in basin (m³, >= 0, default 0).

    Returns
    -------
    dict {ok, outflow_m3s, storage_m3, peak_outflow_m3s,
          peak_storage_m3, warnings}
    outflow_m3s and storage_m3 are lists (same length as inflow_series).

    References
    ----------
    Chow, Maidment & Mays (1988) — Applied Hydrology, §8.4.
    """
    if not isinstance(inflow_series, list) or len(inflow_series) < 2:
        return _err("inflow_series must be a list with at least 2 ordinates")
    e = (_guard_positive("dt_s", dt_s) or _guard_nonneg("S0_m3", S0_m3))
    if e:
        return _err(e)
    if not isinstance(outflow_rating, list) or len(outflow_rating) < 2:
        return _err("outflow_rating must be a list with at least 2 entries")

    # Parse rating table
    S_tbl: list[float] = []
    O_tbl: list[float] = []
    for i, row in enumerate(outflow_rating):
        if not isinstance(row, dict):
            return _err(f"outflow_rating[{i}] must be an object")
        s_val = row.get("storage_m3")
        o_val = row.get("outflow_m3s")
        if s_val is None:
            return _err(f"outflow_rating[{i}] missing 'storage_m3'")
        if o_val is None:
            return _err(f"outflow_rating[{i}] missing 'outflow_m3s'")
        e2 = (_guard_nonneg(f"rating[{i}].storage_m3", s_val) or
              _guard_nonneg(f"rating[{i}].outflow_m3s", o_val))
        if e2:
            return _err(e2)
        S_tbl.append(float(s_val))
        O_tbl.append(float(o_val))

    # Verify sorted
    for i in range(len(S_tbl) - 1):
        if S_tbl[i + 1] <= S_tbl[i]:
            return _err(
                f"outflow_rating must be sorted by storage_m3 ascending; "
                f"entry {i+1} ({S_tbl[i+1]}) <= entry {i} ({S_tbl[i]})"
            )

    dt = float(dt_s)
    S0 = float(S0_m3)

    # Build storage-indication lookup: SI = S/dt + O/2
    SI_tbl = [S_tbl[k] / dt + O_tbl[k] / 2.0 for k in range(len(S_tbl))]

    def outflow_from_storage(S: float) -> float:
        """Linear interpolation of outflow from storage."""
        if S <= S_tbl[0]:
            return O_tbl[0]
        if S >= S_tbl[-1]:
            return O_tbl[-1]
        for k in range(len(S_tbl) - 1):
            if S_tbl[k] <= S <= S_tbl[k + 1]:
                frac = (S - S_tbl[k]) / (S_tbl[k + 1] - S_tbl[k])
                return O_tbl[k] + frac * (O_tbl[k + 1] - O_tbl[k])
        return O_tbl[-1]

    def storage_from_si(si_val: float) -> float:
        """Inverse interpolation: storage from storage-indication value."""
        if si_val <= SI_tbl[0]:
            return S_tbl[0]
        if si_val >= SI_tbl[-1]:
            return S_tbl[-1]
        for k in range(len(SI_tbl) - 1):
            if SI_tbl[k] <= si_val <= SI_tbl[k + 1]:
                frac = (si_val - SI_tbl[k]) / (SI_tbl[k + 1] - SI_tbl[k])
                return S_tbl[k] + frac * (S_tbl[k + 1] - S_tbl[k])
        return S_tbl[-1]

    # Route
    inflow = [float(x) for x in inflow_series]
    n = len(inflow)
    outflow_out: list[float] = [0.0] * n
    storage_out: list[float] = [0.0] * n

    S = S0
    O = outflow_from_storage(S)
    outflow_out[0] = O
    storage_out[0] = S

    warns: list[str] = []
    SI_max = SI_tbl[-1]
    for i in range(1, n):
        I1 = inflow[i - 1]
        I2 = inflow[i]
        # RHS: (I1+I2)/2 + (S1/dt - O1/2)
        rhs = (I1 + I2) / 2.0 + (S / dt - O / 2.0)
        # Warn if routing demand exceeds rating table
        if rhs > SI_max:
            warns.append(
                f"Step {i}: storage-indication value {rhs:.2f} exceeds rating "
                f"table maximum {SI_max:.2f} — basin overtopping may occur."
            )
        # Solve for S2 using inverse SI lookup (clamped to table range)
        S2 = storage_from_si(rhs)
        O2 = outflow_from_storage(S2)
        outflow_out[i] = O2
        storage_out[i] = S2
        S = S2
        O = O2

    peak_out = max(outflow_out)
    peak_stor = max(storage_out)
    return {
        "ok": True,
        "outflow_m3s": [round(x, 6) for x in outflow_out],
        "storage_m3": [round(x, 3) for x in storage_out],
        "peak_outflow_m3s": round(peak_out, 6),
        "peak_storage_m3": round(peak_stor, 3),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 9.  Storm-sewer pipe sizing (Manning full-flow, rational method)
# ---------------------------------------------------------------------------

def storm_sewer_pipe_size(
    Q_cms: float,
    slope: float,
    n: float = 0.013,
    min_d_m: float = 0.150,
    max_d_m: float = 3.0,
    freeboard_fraction: float = 0.85,
) -> dict:
    """Select storm-sewer pipe diameter by Manning full-flow.

    Manning's equation for a full circular pipe:
        Q_full = (1/n) · (π/4)·D² · (D/4)^(2/3) · S^(1/2)
               = (1/n) · (π/4) · D^(8/3) / 4^(2/3) · S^(1/2)

    The smallest standard diameter where Q_full ≥ Q_design / freeboard_fraction
    is selected.  If no standard diameter is sufficient, the function returns
    the minimum required diameter and issues a warning.

    A freeboard check: if Q_design / Q_full > freeboard_fraction,
    a warning is added (pipe hydraulically full; no freeboard).

    Parameters
    ----------
    Q_cms             : Design peak flow (m³/s).
    slope             : Pipe hydraulic gradient (m/m), > 0.
    n                 : Manning's roughness (default 0.013 concrete).
    min_d_m           : Minimum acceptable diameter (m, default 0.15 m = 150 mm).
    max_d_m           : Maximum diameter to consider (m, default 3.0 m).
    freeboard_fraction: Design flow / full-flow capacity ratio (default 0.85,
                        i.e. pipe designed to flow 85% full).

    Returns
    -------
    dict {ok, diameter_m, diameter_mm, Q_full_m3s, utilisation,
          freeboard_ok, warnings}

    References
    ----------
    ASCE MOP 36 (2007) — Design and Construction of Sanitary and Storm Sewers.
    Ven Te Chow (1959) — Open-Channel Hydraulics, §4.2.
    """
    e = (_guard_positive("Q_cms", Q_cms) or
         _guard_positive("slope", slope) or
         _guard_positive("n", n) or
         _guard_positive("min_d_m", min_d_m) or
         _guard_positive("max_d_m", max_d_m) or
         _guard_positive("freeboard_fraction", freeboard_fraction))
    if e:
        return _err(e)
    Q = float(Q_cms)
    S = float(slope)
    n_f = float(n)
    min_d = float(min_d_m)
    max_d = float(max_d_m)
    fb = float(freeboard_fraction)

    if fb > 1.0:
        return _err(f"freeboard_fraction must be <= 1.0, got {fb}")
    if min_d > max_d:
        return _err(f"min_d_m ({min_d}) > max_d_m ({max_d})")

    sqrt_S = math.sqrt(S)

    def q_full(d: float) -> float:
        """Manning full-flow capacity for circular pipe diameter d (m)."""
        # Q = (1/n) * A * R^(2/3) * S^(1/2)
        # A = π/4 * d², R = d/4
        A = math.pi / 4.0 * d * d
        R = d / 4.0
        return (1.0 / n_f) * A * (R ** (2.0 / 3.0)) * sqrt_S

    Q_design_full = Q / fb   # required full-flow capacity

    warns: list[str] = []

    # Try standard diameters
    selected_d: float | None = None
    for d in _STANDARD_DIAMETERS_M:
        if d < min_d or d > max_d:
            continue
        if q_full(d) >= Q_design_full:
            selected_d = d
            break

    if selected_d is None:
        # Compute required diameter analytically:
        # Q_design_full = (1/n) * π/4 * d² * (d/4)^(2/3) * sqrt(S)
        # = (1/n) * π/4 * d^(8/3) / 4^(2/3) * sqrt(S)
        # d^(8/3) = Q_design_full * n * 4 / π * 4^(2/3) / sqrt(S)
        k = (Q_design_full * n_f * 4.0 / math.pi *
             (4.0 ** (2.0 / 3.0)) / sqrt_S)
        d_req = k ** (3.0 / 8.0)
        warns.append(
            f"No standard diameter <= {max_d:.3f} m satisfies Q = {Q:.4f} m³/s "
            f"with freeboard fraction {fb}; minimum required diameter = "
            f"{d_req*1000:.0f} mm.  Consider a non-standard or box culvert."
        )
        selected_d = d_req

    Qf = q_full(selected_d)
    utilisation = Q / Qf if Qf > _EPS else 0.0
    freeboard_ok = utilisation <= fb

    if not freeboard_ok:
        warns.append(
            f"Pipe utilisation {utilisation:.3f} > freeboard_fraction {fb:.2f}; "
            "pipe is hydraulically full.  Increase diameter or slope."
        )

    # Minimum velocity check (self-cleansing): 0.6 m/s
    A_sel = math.pi / 4.0 * selected_d ** 2
    V_full = Qf / A_sel if A_sel > _EPS else 0.0
    if V_full < 0.6:
        warns.append(
            f"Full-flow velocity {V_full:.2f} m/s < 0.6 m/s; risk of sediment "
            "deposition (self-cleansing velocity not achieved)."
        )

    return {
        "ok": True,
        "diameter_m": round(selected_d, 4),
        "diameter_mm": round(selected_d * 1000.0, 1),
        "Q_full_m3s": round(Qf, 6),
        "Q_design_m3s": round(Q, 6),
        "utilisation": round(utilisation, 4),
        "freeboard_ok": freeboard_ok,
        "warnings": warns,
    }
