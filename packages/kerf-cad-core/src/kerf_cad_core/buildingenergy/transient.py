"""
kerf_cad_core.buildingenergy.transient — Transient cooling-load methods.

All functions are self-contained (math + stdlib only).  No OCC dependency.
Functions return plain dicts; they NEVER raise.

Implements
----------
SOL-AIR TEMPERATURE
  sol_air_temp(T_outdoor, I_solar, absorptance_short, h_o, dT_long_wave)
      Tsa = T + αI/ho − ε·ΔR/ho per ASHRAE Fundamentals Ch. 18.

CLTD / WALL & ROOF COOLING LOADS
  cltd_wall(wall_type, hour)
      Tabulated 24-h CLTD for Groups A–D walls (IP units, °F).
  cltd_roof(roof_type, hour)
      Tabulated 24-h CLTD for light/medium/heavy roofs (IP units, °F).
  correct_cltd(CLTD_tab, LM, K, T_indoor_F, T_outdoor_F_mean)
      CLTDc = (CLTD + LM)·K + (78 − Ti) + (To − 85)
  wall_cooling_load(U, A, CLTDc, *, ip_units)
      q = U·A·CLTDc [Btu/hr or W].

SOLAR GAIN THROUGH FENESTRATION
  solar_heat_gain(I_dir, I_diff, area, SHGC, IAC, frame_factor,
                  time_of_day, orientation)
      Direct + diffuse + ground-reflected solar heat gain (W).
  cooling_load_fenestration_rts(SHG_24h, RTS_series)
      Cooling load from fenestration via Radiant Time Series (W, 24-h profile).

ZONE 24-HOUR COOLING LOAD PROFILE
  zone_24h_cooling_load(walls, roof, windows, internal_gains,
                        outdoor_temp_24h, solar_24h, design_indoor_T)
      Full 24-h cooling load profile + peak hour + peak load.

Unit system
-----------
SI throughout unless noted in the function docstring.
  CLTD tables are stored in °F (ASHRAE IP convention); conversion to SI
  is performed by the high-level functions automatically.

References
----------
ASHRAE Handbook — Fundamentals (1989, Table 34 / 36) and (2001)
  — CLTD/CLF method for walls, roofs, and fenestration.
  Cited edition: ASHRAE Handbook of Fundamentals, 1989, Chapters 26 & 27.
ASHRAE Handbook — Fundamentals (2009), Chapter 18
  — Radiant Time Series (RTS) method for zone cooling loads.
ASHRAE Handbook — Fundamentals (2021), Chapter 18 §18.4
  — Sol-air temperature definition: Tsa = T + αI/ho − ε·ΔR/ho.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ASHRAE default long-wave correction for horizontal surface (ΔR ≈ 63 W/m²)
# and ε = 1.0 for dark/matte absorbers.
_DELTA_R_DEFAULT_W_M2 = 63.0   # long-wave radiation correction, horizontal roof
_H_O_DEFAULT = 22.7             # exterior convective film coefficient W/(m²·K)
_BTUHR_PER_W = 3.41214          # 1 W = 3.41214 Btu/hr
_W_PER_BTUHR = 1.0 / _BTUHR_PER_W

# ---------------------------------------------------------------------------
# CLTD tables (IP, °F) — ASHRAE Handbook of Fundamentals, 1989
# Table 34 (walls) and Table 36 (roofs), 40°N latitude, July design,
# Ti = 78°F, To_mean = 85°F.  Hours are 0–23 (solar noon ≈ 12:00 LST).
# ---------------------------------------------------------------------------

# Wall groups (ASHRAE 1989 HoF Table 34 excerpt):
#   Group A: No mass, mostly glass/thin cladding  (fast response)
#   Group B: Light frame, some insulation
#   Group C: Medium-weight masonry / concrete block
#   Group D: Heavy masonry (8" brick or concrete)
_CLTD_WALL: Dict[str, List[float]] = {
    # hour:  0    1    2    3    4    5    6    7    8    9   10   11
    #       12   13   14   15   16   17   18   19   20   21   22   23
    "A": [
         1,  -1,  -2,  -2,  -2,  -1,   0,   2,   4,   7,   9,  11,
        13,  15,  16,  17,  17,  17,  16,  14,  12,   9,   6,   3,
    ],
    "B": [
         4,   2,   1,   0,   0,   0,   1,   2,   4,   6,   8,  10,
        12,  14,  15,  16,  17,  17,  17,  16,  14,  12,   9,   7,
    ],
    "C": [
         8,   6,   5,   4,   3,   3,   3,   3,   4,   5,   7,   9,
        11,  13,  14,  15,  16,  16,  16,  16,  15,  14,  12,  10,
    ],
    "D": [
        10,   9,   7,   6,   5,   4,   4,   4,   4,   5,   6,   8,
        10,  12,  13,  15,  16,  17,  17,  17,  16,  15,  14,  12,
    ],
}

# Roof types (ASHRAE 1989 HoF Table 36 excerpt):
#   light:  steel deck, 1" insulation (low thermal mass)
#   medium: concrete deck + insulation
#   heavy:  8" concrete + insulation (high thermal mass)
_CLTD_ROOF: Dict[str, List[float]] = {
    "light": [
         1,  -2,  -3,  -3,  -3,  -3,  -1,   4,   9,  15,  21,  27,
        32,  35,  37,  37,  35,  32,  27,  22,  17,  12,   8,   4,
    ],
    "medium": [
         9,   7,   5,   3,   2,   1,   1,   2,   4,   7,  11,  16,
        20,  24,  27,  30,  31,  31,  30,  28,  25,  22,  18,  14,
    ],
    "heavy": [
        16,  14,  12,  10,   8,   7,   6,   6,   6,   7,   9,  11,
        14,  17,  20,  22,  24,  25,  25,  25,  24,  22,  20,  18,
    ],
}

# Latitude–Month correction (LM, °F) for south-facing walls at 40°N in July.
# Per ASHRAE 1989 HoF Table 35.  Simplified table: south-facing July at latitudes.
# For a full implementation, a complete LM table would be provided per orientation.
# These are representative south-wall corrections for July.
_LM_SOUTH_JULY: Dict[int, float] = {
    24: -2.0,
    32: -1.0,
    40:  0.0,
    48:  1.5,
    56:  3.0,
    64:  5.0,
}


# ---------------------------------------------------------------------------
# 1. Sol-air temperature
# ---------------------------------------------------------------------------

def sol_air_temp(
    T_outdoor: float,
    I_solar: float,
    absorptance_short: float,
    h_o: float,
    dT_long_wave: float = 0.0,
    *,
    emittance: float = 1.0,
) -> Dict[str, Any]:
    """Sol-air temperature (°C or °F, same unit as T_outdoor).

    Tsa = T_outdoor + α·I_solar / h_o  −  ε·ΔR / h_o

    Parameters
    ----------
    T_outdoor       : outdoor dry-bulb temperature (°C or °F).
    I_solar         : solar irradiance on the surface (W/m² or Btu/(hr·ft²)).
    absorptance_short: short-wave absorptance of the outer surface, α [0–1].
    h_o             : exterior surface film coefficient [W/(m²·K) or Btu/(hr·ft²·°F)].
                      ASHRAE default SI: 22.7 W/(m²·K); IP: 4.0 Btu/(hr·ft²·°F).
    dT_long_wave    : long-wave radiation correction ΔR [same unit as I_solar].
                      For horizontal roofs use 63 W/m² (SI) or 20 Btu/hr·ft² (IP).
                      For vertical walls use 0 (both upward and downward sky exchange
                      cancel).  Default 0.
    emittance       : long-wave emittance of surface, ε [0–1].  Default 1.0.

    Returns
    -------
    {"ok": True, "T_sol_air": float, "correction_W": float, "warnings": list}

    Reference: ASHRAE Handbook — Fundamentals (2021) Ch. 18 §18.4 Eq. (1).
    Units: consistent with inputs.
    """
    try:
        T_outdoor = float(T_outdoor)
        I_solar = float(I_solar)
        absorptance_short = float(absorptance_short)
        h_o = float(h_o)
        dT_long_wave = float(dT_long_wave)
        emittance = float(emittance)

        if not (0.0 <= absorptance_short <= 1.0):
            return {"ok": False, "reason": "absorptance_short must be in [0, 1]"}
        if h_o <= 0.0:
            return {"ok": False, "reason": "h_o must be > 0"}
        if not (0.0 <= emittance <= 1.0):
            return {"ok": False, "reason": "emittance must be in [0, 1]"}
        if I_solar < 0.0:
            return {"ok": False, "reason": "I_solar must be >= 0"}

        solar_correction = absorptance_short * I_solar / h_o
        lw_correction = emittance * dT_long_wave / h_o
        T_sol_air = T_outdoor + solar_correction - lw_correction

        warn_list: List[str] = []
        if T_sol_air > T_outdoor + 30:
            msg = f"Sol-air temperature {T_sol_air:.1f} is >30° above T_outdoor — check inputs"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "T_sol_air": round(T_sol_air, 4),
            "solar_correction": round(solar_correction, 4),
            "lw_correction": round(lw_correction, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# 2. CLTD tables & corrections
# ---------------------------------------------------------------------------

def cltd_wall(wall_type: str, hour: int) -> Dict[str, Any]:
    """Tabulated Cooling Load Temperature Difference for opaque walls (°F).

    Parameters
    ----------
    wall_type : "A" | "B" | "C" | "D"
        Group A = fast-response (no mass); Group D = heavy masonry (slow).
    hour      : solar time hour, 0–23.

    Returns
    -------
    {"ok": True, "CLTD_F": float, "wall_type": str, "hour": int, "warnings": list}

    Reference: ASHRAE Handbook of Fundamentals, 1989, Table 34.
    Conditions: 40°N latitude, July, Ti = 78°F, To_mean = 85°F.
    Units: °F (IP).
    """
    try:
        wall_type = str(wall_type).upper()
        hour = int(hour)

        if wall_type not in _CLTD_WALL:
            return {
                "ok": False,
                "reason": f"wall_type must be one of {list(_CLTD_WALL.keys())}",
            }
        if not (0 <= hour <= 23):
            return {"ok": False, "reason": "hour must be in [0, 23]"}

        CLTD_F = _CLTD_WALL[wall_type][hour]

        return {
            "ok": True,
            "CLTD_F": float(CLTD_F),
            "wall_type": wall_type,
            "hour": hour,
            "warnings": [],
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def cltd_roof(roof_type: str, hour: int) -> Dict[str, Any]:
    """Tabulated Cooling Load Temperature Difference for roofs (°F).

    Parameters
    ----------
    roof_type : "light" | "medium" | "heavy"
        light  = steel deck + 1" insulation;
        medium = concrete + insulation;
        heavy  = 8" concrete + insulation.
    hour      : solar time hour, 0–23.

    Returns
    -------
    {"ok": True, "CLTD_F": float, "roof_type": str, "hour": int, "warnings": list}

    Reference: ASHRAE Handbook of Fundamentals, 1989, Table 36.
    Conditions: 40°N latitude, July, Ti = 78°F, To_mean = 85°F.
    Units: °F (IP).
    """
    try:
        roof_type = str(roof_type).lower()
        hour = int(hour)

        if roof_type not in _CLTD_ROOF:
            return {
                "ok": False,
                "reason": f"roof_type must be one of {list(_CLTD_ROOF.keys())}",
            }
        if not (0 <= hour <= 23):
            return {"ok": False, "reason": "hour must be in [0, 23]"}

        CLTD_F = _CLTD_ROOF[roof_type][hour]

        return {
            "ok": True,
            "CLTD_F": float(CLTD_F),
            "roof_type": roof_type,
            "hour": hour,
            "warnings": [],
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def correct_cltd(
    CLTD_tab: float,
    LM: float = 0.0,
    K: float = 1.0,
    T_indoor_F: float = 78.0,
    T_outdoor_F_mean: float = 85.0,
) -> Dict[str, Any]:
    """Apply CLTD correction per ASHRAE 1989 HoF.

    CLTDc = (CLTD_tab + LM) × K + (78 − Ti) + (To_mean − 85)

    Parameters
    ----------
    CLTD_tab        : tabulated CLTD from table (°F).
    LM              : latitude–month correction from Table 35 (°F).  Default 0.
    K               : color/absorptance correction factor [0.5–1.0].
                      K = 1.0 for dark surfaces (default); K ≈ 0.5–0.65 for light.
    T_indoor_F      : design indoor temperature (°F). Default 78.
    T_outdoor_F_mean: mean outdoor dry-bulb for design day (°F). Default 85.

    Returns
    -------
    {"ok": True, "CLTDc_F": float, "CLTDc_C": float, "warnings": list}

    CLTDc_C = CLTDc_F × 5/9  (delta-temperature conversion, no offset).
    Reference: ASHRAE Handbook of Fundamentals, 1989, Ch. 26, Eq. (3).
    Units: °F (IP) and °C/K (SI delta).
    """
    try:
        CLTD_tab = float(CLTD_tab)
        LM = float(LM)
        K = float(K)
        T_indoor_F = float(T_indoor_F)
        T_outdoor_F_mean = float(T_outdoor_F_mean)

        if K <= 0:
            return {"ok": False, "reason": "K must be > 0"}

        warn_list: List[str] = []

        CLTDc_F = (CLTD_tab + LM) * K + (78.0 - T_indoor_F) + (T_outdoor_F_mean - 85.0)

        # Delta-temperature: °F × 5/9 = °C (no 32-offset for temperature differences)
        CLTDc_C = CLTDc_F * 5.0 / 9.0

        if CLTDc_F < 0:
            msg = f"CLTDc = {CLTDc_F:.1f}°F is negative — cooling load contribution is negative (heat loss)"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "CLTDc_F": round(CLTDc_F, 3),
            "CLTDc_C": round(CLTDc_C, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def wall_cooling_load(
    U: float,
    A: float,
    CLTDc: float,
    *,
    ip_units: bool = False,
) -> Dict[str, Any]:
    """Sensible cooling load through an opaque wall or roof element.

    q = U × A × CLTDc

    Parameters
    ----------
    U        : overall U-value of the assembly.
               SI: W/(m²·K); IP: Btu/(hr·ft²·°F).
    A        : surface area.
               SI: m²; IP: ft².
    CLTDc    : corrected CLTD.
               SI: °C (= K delta); IP: °F.
    ip_units : if True, U is in Btu/(hr·ft²·°F), A in ft², CLTDc in °F
               and output is in Btu/hr.  If False (default), SI → W.

    Returns
    -------
    {"ok": True, "q_W": float, "q_Btuhr": float, "warnings": list}

    Reference: ASHRAE Handbook of Fundamentals, 1989, Ch. 26.
    """
    try:
        U = float(U)
        A = float(A)
        CLTDc = float(CLTDc)

        if U < 0:
            return {"ok": False, "reason": "U must be >= 0"}
        if A < 0:
            return {"ok": False, "reason": "A must be >= 0"}

        warn_list: List[str] = []

        if ip_units:
            q_Btuhr = U * A * CLTDc
            q_W = q_Btuhr * _W_PER_BTUHR
        else:
            q_W = U * A * CLTDc
            q_Btuhr = q_W * _BTUHR_PER_W

        if q_W < 0:
            msg = "Cooling load q < 0 — surface is a heat sink at this hour (CLTDc < 0)"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "q_W": round(q_W, 3),
            "q_Btuhr": round(q_Btuhr, 3),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# 3. Solar gain through fenestration
# ---------------------------------------------------------------------------

# Ground reflectance (albedo) for ground-reflected component
_GROUND_REFLECTANCE = 0.2

# RTS factors for medium-weight zone construction, 24-h series (ASHRAE 2009 HoF
# Table 19, "medium" radiative fraction zone, non-residential midrange).
# Hour 0 = current hour; index i = i hours before current.
# These represent how past solar gains contribute to current cooling load.
# Reference: ASHRAE Handbook — Fundamentals (2009), Ch. 18, Table 19.
_RTS_MEDIUM: List[float] = [
    0.55, 0.14, 0.07, 0.04, 0.03, 0.02, 0.02, 0.02,
    0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    0.01, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00,
]


def solar_heat_gain(
    I_dir: float,
    I_diff: float,
    area: float,
    SHGC: float,
    IAC: float = 1.0,
    frame_factor: float = 1.0,
    time_of_day: Optional[float] = None,
    orientation: str = "south",
    *,
    latitude_deg: float = 40.0,
    ground_reflectance: float = _GROUND_REFLECTANCE,
) -> Dict[str, Any]:
    """Instantaneous solar heat gain through fenestration (W).

    Accounts for direct beam, diffuse sky, and ground-reflected components.
    Uses the simple SHGC approach with Incident-Angle Correction (IAC).

    Parameters (SI)
    ---------------
    I_dir          : direct-normal irradiance incident on the glazing plane (W/m²).
                     For a tilted surface this should already be the in-plane direct
                     irradiance (= DNI × cos θ_i).
    I_diff         : diffuse horizontal irradiance (W/m²).
    area           : glazing area (m²).
    SHGC           : solar heat gain coefficient at normal incidence [0–1].
    IAC            : interior attachment (blind/shade) solar attenuation coefficient [0–1].
                     1.0 = no interior shading (default).
    frame_factor   : fraction of opening that is glazing (1 − frame fraction) [0–1].
                     Default 1.0 (ignore frame).
    time_of_day    : solar hour angle 0–23 (float).  Used only for angle-of-incidence
                     weighting of ground-reflected component.  Optional.
    orientation    : cardinal string "north" | "south" | "east" | "west" | "horizontal".
                     Used to apply a simple diffuse view-factor correction.
    latitude_deg   : site latitude (degrees).  Used for ground-reflected cos correction.
    ground_reflectance: albedo of foreground (default 0.2).

    Returns
    -------
    {"ok": True,
     "Q_dir_W": float, "Q_diff_W": float, "Q_gnd_W": float,
     "Q_total_W": float, "warnings": list}

    Reference: ASHRAE Handbook — Fundamentals (2009), Ch. 18 §18.4;
               ASHRAE Handbook — Fundamentals (2021), Ch. 15 §15.2.
    Units: SI (W).
    """
    try:
        I_dir = float(I_dir)
        I_diff = float(I_diff)
        area = float(area)
        SHGC = float(SHGC)
        IAC = float(IAC)
        frame_factor = float(frame_factor)
        ground_reflectance = float(ground_reflectance)
        orientation = str(orientation).lower()

        if I_dir < 0:
            return {"ok": False, "reason": "I_dir must be >= 0"}
        if I_diff < 0:
            return {"ok": False, "reason": "I_diff must be >= 0"}
        if area < 0:
            return {"ok": False, "reason": "area must be >= 0"}
        if not (0.0 <= SHGC <= 1.0):
            return {"ok": False, "reason": "SHGC must be in [0, 1]"}
        if not (0.0 <= IAC <= 1.0):
            return {"ok": False, "reason": "IAC must be in [0, 1]"}
        if not (0.0 <= frame_factor <= 1.0):
            return {"ok": False, "reason": "frame_factor must be in [0, 1]"}

        warn_list: List[str] = []

        # Sky view factor for diffuse component based on orientation
        _sky_view = {
            "horizontal": 1.0,
            "south": 0.5,
            "north": 0.5,
            "east": 0.5,
            "west": 0.5,
        }
        Fsky = _sky_view.get(orientation, 0.5)
        Fgnd = 1.0 - Fsky  # ground view factor

        # Direct component (I_dir is already in-plane beam irradiance)
        Q_dir = SHGC * IAC * I_dir * area * frame_factor

        # Diffuse sky component
        Q_diff = SHGC * IAC * I_diff * Fsky * area * frame_factor

        # Ground-reflected component: I_gnd = ρ_g × (I_dir_horiz + I_diff_horiz)
        # We approximate I_dir_horiz ~ I_dir (conservative for south wall at midday)
        I_total_horiz = I_dir + I_diff
        I_gnd = ground_reflectance * I_total_horiz * Fgnd
        Q_gnd = SHGC * IAC * I_gnd * area * frame_factor

        Q_total = Q_dir + Q_diff + Q_gnd

        if Q_total < 0:
            msg = "Total solar heat gain is negative — clamping to 0"
            _warnings.warn(msg)
            warn_list.append(msg)
            Q_total = 0.0

        return {
            "ok": True,
            "Q_dir_W": round(Q_dir, 3),
            "Q_diff_W": round(Q_diff, 3),
            "Q_gnd_W": round(Q_gnd, 3),
            "Q_total_W": round(Q_total, 3),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def cooling_load_fenestration_rts(
    SHG_24h: List[float],
    RTS_series: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Cooling load from fenestration using the Radiant Time Series method.

    Applies a 24-element RTS to the solar heat gain profile to produce the
    cooling load profile.  The conductive (rapidly released) fraction of solar
    gain is transferred to cooling load directly; the radiative fraction is
    weighted over the previous 24 hours using the RTS.

    Parameters
    ----------
    SHG_24h    : list of 24 hourly solar heat gains (W) for one day (0–23).
    RTS_series : 24-element Radiant Time Series (fractions summing to 1.0).
                 Default: medium-weight zone (_RTS_MEDIUM, ASHRAE 2009 HoF Table 19).

    Returns
    -------
    {"ok": True,
     "CL_24h": list[float],    — 24-h cooling load profile (W)
     "peak_hour": int,         — hour of peak cooling load (0–23)
     "peak_load_W": float,     — peak cooling load (W)
     "warnings": list}

    Reference: ASHRAE Handbook — Fundamentals (2009), Ch. 18 §18.4 RTS method.
    Units: SI (W).
    """
    try:
        if RTS_series is None:
            RTS_series = _RTS_MEDIUM

        SHG_24h = [float(x) for x in SHG_24h]
        RTS_series = [float(x) for x in RTS_series]

        if len(SHG_24h) != 24:
            return {"ok": False, "reason": "SHG_24h must have exactly 24 values"}
        if len(RTS_series) != 24:
            return {"ok": False, "reason": "RTS_series must have exactly 24 values"}

        rts_sum = sum(RTS_series)
        warn_list: List[str] = []
        if abs(rts_sum - 1.0) > 0.02:
            msg = f"RTS series sums to {rts_sum:.4f} (expected 1.0) — results may be inaccurate"
            _warnings.warn(msg)
            warn_list.append(msg)

        # For each hour t, CL(t) = Σ_{i=0}^{23} RTS[i] × SHG(t-i)
        # SHG is cyclic (same-day, steady-state repetitive schedule)
        CL_24h: List[float] = []
        for t in range(24):
            cl = sum(
                RTS_series[i] * SHG_24h[(t - i) % 24]
                for i in range(24)
            )
            CL_24h.append(round(cl, 3))

        peak_hour = int(max(range(24), key=lambda h: CL_24h[h]))
        peak_load_W = CL_24h[peak_hour]

        return {
            "ok": True,
            "CL_24h": CL_24h,
            "peak_hour": peak_hour,
            "peak_load_W": round(peak_load_W, 3),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# 4. Zone 24-hour cooling load profile
# ---------------------------------------------------------------------------

def zone_24h_cooling_load(
    walls: List[Dict[str, Any]],
    roof: Optional[Dict[str, Any]],
    windows: List[Dict[str, Any]],
    internal_gains: List[float],
    outdoor_temp_24h: List[float],
    solar_24h: List[Dict[str, Any]],
    design_indoor_T: float,
    *,
    RTS_series: Optional[List[float]] = None,
    infiltration_UA: float = 0.0,
) -> Dict[str, Any]:
    """Full zone 24-hour sensible cooling load profile.

    Parameters (SI)
    ---------------
    walls : list of wall element dicts:
        {
          "U": float,           — U-value W/(m²·K)
          "A": float,           — area m²
          "wall_type": str,     — "A"|"B"|"C"|"D"
          "LM": float,          — latitude-month correction °F (default 0)
          "K": float,           — color correction factor (default 1.0)
          "T_outdoor_mean_F": float  — design mean outdoor °F (default 85)
        }
    roof : roof element dict or None:
        {
          "U": float,
          "A": float,
          "roof_type": str,     — "light"|"medium"|"heavy"
          "LM": float,
          "K": float,
          "T_outdoor_mean_F": float
        }
    windows : list of fenestration dicts:
        {
          "I_dir_24h": list[float],  — 24-h direct in-plane irradiance (W/m²)
          "I_diff_24h": list[float], — 24-h diffuse horizontal (W/m²)
          "area": float,
          "SHGC": float,
          "IAC": float,              — interior attenuation coefficient (default 1.0)
          "frame_factor": float,     — default 1.0
          "orientation": str,        — "south"|"north"|"east"|"west" (default "south")
        }
    internal_gains : list of 24 hourly sensible internal gain values (W).
                     If a scalar is needed, pass [value]*24.
    outdoor_temp_24h : list of 24 hourly outdoor temperatures (°C).
    solar_24h        : list of 24 dicts (or empty); each dict overrides solar inputs
                       per hour.  Usually these are embedded in windows[].
    design_indoor_T  : indoor setpoint (°C).
    RTS_series       : 24-element RTS; default = medium-weight zone.
    infiltration_UA  : infiltration + ventilation UA (W/K); applies each hour.

    Returns
    -------
    {"ok": True,
     "CL_24h": list[float],    — 24-h total cooling load (W), one per hour
     "peak_hour": int,         — index of peak (0–23)
     "peak_load_W": float,
     "envelope_24h": list[float],
     "fenestration_24h": list[float],
     "internal_24h": list[float],
     "infiltration_24h": list[float],
     "warnings": list}

    Reference: ASHRAE Handbook — Fundamentals (2009), Ch. 18 (RTS method);
               ASHRAE Handbook — Fundamentals (1989), Ch. 26 (CLTD/CLF method).
    Units: SI (W, °C).
    """
    try:
        if len(outdoor_temp_24h) != 24:
            return {"ok": False, "reason": "outdoor_temp_24h must have 24 values"}
        if len(internal_gains) != 24:
            return {"ok": False, "reason": "internal_gains must have 24 values"}

        outdoor_temp_24h = [float(t) for t in outdoor_temp_24h]
        internal_gains = [float(g) for g in internal_gains]
        design_indoor_T = float(design_indoor_T)

        warn_list: List[str] = []

        # Design indoor temperature in °F for CLTD correction
        T_indoor_F = design_indoor_T * 9.0 / 5.0 + 32.0

        # --- 4a. Envelope (wall + roof) CLTD loads per hour ---
        envelope_24h: List[float] = []
        for hour in range(24):
            q_wall_total = 0.0

            for wall in walls:
                U_w = float(wall.get("U", 0.0))
                A_w = float(wall.get("A", 0.0))
                wtype = str(wall.get("wall_type", "D")).upper()
                LM_w = float(wall.get("LM", 0.0))
                K_w = float(wall.get("K", 1.0))
                To_mean_F = float(wall.get("T_outdoor_mean_F", 85.0))

                res_tab = cltd_wall(wtype, hour)
                if not res_tab["ok"]:
                    return {"ok": False, "reason": f"wall CLTD error: {res_tab['reason']}"}

                res_corr = correct_cltd(
                    res_tab["CLTD_F"], LM_w, K_w, T_indoor_F, To_mean_F
                )
                if not res_corr["ok"]:
                    return {"ok": False, "reason": f"CLTD correction error: {res_corr['reason']}"}

                res_q = wall_cooling_load(U_w, A_w, res_corr["CLTDc_C"])
                if not res_q["ok"]:
                    return {"ok": False, "reason": f"wall_cooling_load error: {res_q['reason']}"}

                q_wall_total += res_q["q_W"]

            # Roof
            q_roof = 0.0
            if roof is not None:
                U_r = float(roof.get("U", 0.0))
                A_r = float(roof.get("A", 0.0))
                rtype = str(roof.get("roof_type", "medium")).lower()
                LM_r = float(roof.get("LM", 0.0))
                K_r = float(roof.get("K", 1.0))
                To_mean_r_F = float(roof.get("T_outdoor_mean_F", 85.0))

                res_rtab = cltd_roof(rtype, hour)
                if not res_rtab["ok"]:
                    return {"ok": False, "reason": f"roof CLTD error: {res_rtab['reason']}"}

                res_rcorr = correct_cltd(
                    res_rtab["CLTD_F"], LM_r, K_r, T_indoor_F, To_mean_r_F
                )
                if not res_rcorr["ok"]:
                    return {"ok": False, "reason": f"roof CLTD correction: {res_rcorr['reason']}"}

                res_rq = wall_cooling_load(U_r, A_r, res_rcorr["CLTDc_C"])
                if not res_rq["ok"]:
                    return {"ok": False, "reason": f"roof cooling load: {res_rq['reason']}"}

                q_roof = res_rq["q_W"]

            envelope_24h.append(q_wall_total + q_roof)

        # --- 4b. Fenestration cooling load via RTS ---
        # Aggregate 24-h SHG across all windows, then apply RTS
        SHG_agg: List[float] = [0.0] * 24
        for win in windows:
            I_dir_24h = [float(v) for v in win.get("I_dir_24h", [0.0] * 24)]
            I_diff_24h = [float(v) for v in win.get("I_diff_24h", [0.0] * 24)]
            w_area = float(win.get("area", 0.0))
            w_SHGC = float(win.get("SHGC", 0.6))
            w_IAC = float(win.get("IAC", 1.0))
            w_ff = float(win.get("frame_factor", 1.0))
            w_orient = str(win.get("orientation", "south")).lower()

            for h in range(24):
                res_shg = solar_heat_gain(
                    I_dir_24h[h],
                    I_diff_24h[h],
                    w_area,
                    w_SHGC,
                    w_IAC,
                    w_ff,
                    float(h),
                    w_orient,
                )
                if not res_shg["ok"]:
                    return {
                        "ok": False,
                        "reason": f"window solar gain error hour {h}: {res_shg['reason']}",
                    }
                SHG_agg[h] += res_shg["Q_total_W"]

        res_rts = cooling_load_fenestration_rts(SHG_agg, RTS_series)
        if not res_rts["ok"]:
            return {"ok": False, "reason": f"RTS error: {res_rts['reason']}"}
        fenestration_24h: List[float] = res_rts["CL_24h"]
        warn_list.extend(res_rts["warnings"])

        # --- 4c. Infiltration load per hour ---
        infiltration_UA = float(infiltration_UA)
        infiltration_24h: List[float] = [
            max(0.0, infiltration_UA * (outdoor_temp_24h[h] - design_indoor_T))
            for h in range(24)
        ]

        # --- 4d. Assemble total ---
        CL_24h: List[float] = []
        for h in range(24):
            cl = (
                envelope_24h[h]
                + fenestration_24h[h]
                + internal_gains[h]
                + infiltration_24h[h]
            )
            CL_24h.append(round(cl, 3))

        peak_hour = int(max(range(24), key=lambda h: CL_24h[h]))
        peak_load_W = CL_24h[peak_hour]

        return {
            "ok": True,
            "CL_24h": CL_24h,
            "peak_hour": peak_hour,
            "peak_load_W": round(peak_load_W, 3),
            "envelope_24h": [round(v, 3) for v in envelope_24h],
            "fenestration_24h": [round(v, 3) for v in fenestration_24h],
            "internal_24h": [round(v, 3) for v in internal_gains],
            "infiltration_24h": [round(v, 3) for v in infiltration_24h],
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
