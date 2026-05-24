"""
kerf_cad_core.plumbing.design — pure-Python building plumbing & sanitary engineering.

Implements eleven public functions covering:

  hunter_demand_gpm          — fixture units → design demand (GPM) via Hunter curve,
                                flush-tank and flush-valve system types
  size_supply_pipe           — supply pipe sizing: Hazen-Williams + available pressure
                                budget (static + meter loss + friction + residual)
  dfu_to_drain_size          — drainage fixture units (DFU) → building drain, branch
                                and stack diameter per IPC/UPC tables
  vent_size                  — vent pipe sizing by DFU and developed length (IPC Table
                                906.2)
  trap_arm_slope             — trap-to-vent slope and distance check (IPC §1002.1)
  drain_slope_manning        — drain slope vs full/half-flow capacity (Manning n=0.013)
  hot_water_heater_size      — storage water heater sizing: peak hourly demand,
                                recovery rate, storage volume (ASHRAE)
  hw_recirculation_loop      — hot-water recirculation loop pipe size, pump head, and
                                heat loss (ASHRAE Applications §50)
  storm_drain_leader          — roof storm-drain & leader sizing by rainfall intensity ×
                                roof area (IPC Table 1106.2)
  water_hammer_arrestor      — fixture units → PDI sizing guide WH-201 unit selection
  expansion_tank_heater      — closed-loop water-heater expansion tank sizing
                                (ASME/ASHRAE pressure/volume method)

All functions return a plain dict:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Under-pressure / pipe-undersized / slope-out-of-range
conditions are reported in the "warnings" list, never as errors.

Units
-----
  flow         — US gallons per minute (gpm) for supply/demand
  pressure     — pounds per square inch (psi)
  pipe sizes   — nominal inches (NPS) or nominal mm where noted
  length       — feet (ft) unless noted
  area         — square feet (ft²) for roof drainage
  temperature  — degrees Fahrenheit (°F) unless noted
  volume       — US gallons (gal)
  heat         — BTU/hr

References
----------
IPC (2021) — International Plumbing Code
UPC (2021) — Uniform Plumbing Code
Hunter, R.B. (1940) — Methods of Estimating Loads in Plumbing Systems (BMS 65)
ASHRAE Handbook — HVAC Applications (2019), Chapter 50: Service Water Heating
PDI WH-201 — Water Hammer Arrestor Sizing Guide
ASME A112.26.1 — Water Hammer Arrester Standard

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HUNTER_FT: list[tuple[float, float]] = [
    # (FU, GPM) flush-tank — IPC E103.3(2) / NBS BMS65 Table 1
    (1,    3.0),
    (2,    5.0),
    (3,    6.5),
    (4,    8.0),
    (5,    9.4),
    (6,   10.7),
    (8,   12.3),
    (10,  13.7),
    (12,  14.9),
    (14,  16.0),
    (16,  17.0),
    (18,  18.0),
    (20,  18.9),
    (25,  21.0),
    (30,  23.0),
    (40,  25.5),
    (50,  26.0),
    (60,  29.0),
    (70,  31.8),
    (80,  34.0),
    (90,  36.0),
    (100, 37.0),
    (120, 41.0),
    (140, 45.0),
    (160, 49.0),
    (180, 52.0),
    (200, 55.0),
    (250, 62.5),
    (300, 70.0),
    (400, 85.0),
    (500, 100.0),
    (750, 132.0),
    (1000, 162.0),
    (1500, 215.0),
    (2000, 262.0),
    (3000, 350.0),
    (4000, 430.0),
    (5000, 500.0),
]

_HUNTER_FV: list[tuple[float, float]] = [
    # (FU, GPM) flush-valve — IPC E103.3(3) / NBS BMS65 Table 3
    (5,   15.0),
    (6,   17.4),
    (8,   19.8),
    (10,  22.5),
    (12,  24.2),
    (14,  26.0),
    (16,  27.8),
    (18,  29.4),
    (20,  31.0),
    (25,  35.3),
    (30,  39.0),
    (40,  44.0),
    (50,  51.0),
    (60,  55.0),
    (70,  59.0),
    (80,  63.0),
    (90,  66.0),
    (100, 70.0),
    (120, 77.0),
    (140, 84.0),
    (160, 91.0),
    (180, 98.0),
    (200, 105.0),
    (250, 115.0),
    (300, 124.0),
    (400, 143.0),
    (500, 160.0),
    (750, 205.0),
    (1000, 240.0),
    (1500, 300.0),
    (2000, 358.0),
    (3000, 445.0),
    (4000, 525.0),
    (5000, 593.0),
]


def _interpolate_hunter(fu: float, table: list[tuple[float, float]]) -> float:
    """Linear interpolation (or extrapolation at ends) of a Hunter table."""
    if fu <= table[0][0]:
        return table[0][1]
    if fu >= table[-1][0]:
        # Linear extrapolation beyond last point using last two points
        x0, y0 = table[-2]
        x1, y1 = table[-1]
        return y1 + (fu - x1) * (y1 - y0) / (x1 - x0)
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= fu <= x1:
            return y0 + (fu - x0) * (y1 - y0) / (x1 - x0)
    return table[-1][1]  # fallback


# ---------------------------------------------------------------------------
# IPC supply pipe capacity table (Hazen-Williams C=150, velocity ≤ 8 fps)
# NPS size → inside diameter (inches) for standard copper type L
# ---------------------------------------------------------------------------
_COPPER_L_ID: dict[str, float] = {
    "3/8":  0.430,
    "1/2":  0.545,
    "3/4":  0.785,
    "1":    1.025,
    "1-1/4": 1.265,
    "1-1/2": 1.505,
    "2":    1.985,
    "2-1/2": 2.465,
    "3":    2.945,
    "4":    3.905,
    "6":    5.881,
}

_SUPPLY_NPS_ORDER = [
    "3/8", "1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2", "3", "4", "6"
]

# Hazen-Williams friction loss (psi/ft):
# hf/L = 4.52 × Q^1.85 / (C^1.85 × d^4.87)
_HW_C_SUPPLY = 150.0  # smooth copper / plastic


def _hw_loss_psi_per_ft(q_gpm: float, d_inch: float, C: float = 150.0) -> float:
    """Hazen-Williams friction loss per foot of pipe (psi/ft)."""
    if q_gpm <= 0 or d_inch <= 0:
        return 0.0
    return 4.52 * (q_gpm ** 1.85) / (C ** 1.85 * d_inch ** 4.87)


def _pipe_velocity_fps(q_gpm: float, d_inch: float) -> float:
    """Mean velocity in a circular pipe (ft/s)."""
    if d_inch <= 0:
        return 0.0
    area_ft2 = math.pi / 4.0 * (d_inch / 12.0) ** 2
    return (q_gpm / 7.48052 / 60.0) / area_ft2  # gpm → ft³/s → fps


# ---------------------------------------------------------------------------
# IPC/UPC drainage pipe size tables
# ---------------------------------------------------------------------------
# IPC Table 710.1(1) — building drain and horizontal branch pipe sizing
# (min slope 1/4" per foot = 2.08%)
# Columns: NPS nominal, max DFU for horizontal branch, max DFU for building drain
_IPC_HORIZ_BRANCH: dict[str, int] = {
    # NPS: max DFU on horizontal branch (IPC T710.1(1))
    "1-1/4": 1,
    "1-1/2": 3,
    "2":     6,
    "2-1/2": 12,
    "3":     20,
    "4":     160,
    "5":     360,
    "6":     620,
    "8":     1400,
    "10":    2500,
    "12":    3900,
}

_IPC_BLDG_DRAIN: dict[str, int] = {
    # NPS: max DFU on building drain / sewer (IPC T710.1(2))
    "2":     21,
    "2-1/2": 24,
    "3":     42,
    "4":     216,
    "5":     480,
    "6":     840,
    "8":     1920,
    "10":    3500,
    "12":    5600,
}

_IPC_STACK: dict[str, int] = {
    # NPS: max DFU on drainage stack (IPC T710.1(3), any single floor branch ≤ 1/2 total)
    "1-1/2": 4,
    "2":     10,
    "2-1/2": 20,
    "3":     48,
    "4":     240,
    "5":     540,
    "6":     960,
    "8":     2200,
    "10":    3800,
    "12":    6000,
}

_DRAIN_NPS_ORDER = [
    "1-1/4", "1-1/2", "2", "2-1/2", "3", "4", "5", "6", "8", "10", "12"
]

# Inside diameter (inches) for schedule-40 DWV pipe (per IPC/UPC nominal)
_DWV_ID: dict[str, float] = {
    "1-1/4": 1.380,
    "1-1/2": 1.590,
    "2":     2.067,
    "2-1/2": 2.469,
    "3":     3.068,
    "4":     4.026,
    "5":     5.047,
    "6":     6.065,
    "8":     7.981,
    "10":    10.020,
    "12":    11.938,
}

# ---------------------------------------------------------------------------
# IPC Table 906.2 — vent pipe sizing (developed length vs DFU)
# ---------------------------------------------------------------------------
# Rows: vent NPS; Columns: DFU served + max developed length in feet
# Simplified representative limits from IPC Table 906.2 (2021)
_VENT_TABLE: dict[str, list[tuple[int, float]]] = {
    # NPS: list of (max_DFU, max_developed_length_ft) pairs
    "1-1/4": [(1,   30.0)],
    "1-1/2": [(8,   50.0), (3,  150.0), (1,  unlimited := 999999.0)],
    "2":     [(24,  60.0), (12, 100.0), (8,  200.0), (4,  999999.0)],
    "2-1/2": [(42,  80.0), (20, 150.0), (10, 350.0), (6,  999999.0)],
    "3":     [(72, 100.0), (30, 200.0), (16, 500.0), (10, 999999.0)],
    "4":     [(500, 300.0),(300, 600.0),(100, 999999.0)],
    "5":     [(1100,400.0),(700, 900.0),(400, 999999.0)],
    "6":     [(2400,500.0),(1400,1100.0),(1000,999999.0)],
}

_VENT_NPS_ORDER = ["1-1/4", "1-1/2", "2", "2-1/2", "3", "4", "5", "6"]

del unlimited  # clean namespace


def _select_vent_size(dfu: int, dev_length_ft: float) -> str | None:
    """
    Select the smallest vent NPS from IPC Table 906.2 that satisfies both
    the DFU served and developed length constraints.
    """
    for nps in _VENT_NPS_ORDER:
        if nps not in _VENT_TABLE:
            continue
        for max_dfu, max_len in _VENT_TABLE[nps]:
            if dfu <= max_dfu and dev_length_ft <= max_len:
                return nps
    return None  # exceeds all table entries


# ---------------------------------------------------------------------------
# PDI WH-201 water hammer arrestor sizing table
# ---------------------------------------------------------------------------
# PDI sizing unit letter corresponds to fixture unit range at the branch.
# PDI Guide WH-201, Table 1.
_PDI_SIZING: list[tuple[range, str]] = [
    (range(1, 12),   "A"),   # 1–11 FU → Size A
    (range(12, 33),  "B"),   # 12–32 FU → Size B
    (range(33, 61),  "C"),   # 33–60 FU → Size C
    (range(61, 113), "D"),   # 61–112 FU → Size D
    (range(113, 155),"E"),   # 113–154 FU → Size E
    (range(155, 330),"F"),   # 155–329 FU → Size F
]


def _pdi_unit(fu: int) -> str:
    """Return PDI size letter for a fixture unit count (WH-201)."""
    for rng, letter in _PDI_SIZING:
        if fu in rng:
            return letter
    # > 329 FU: two or more Size F units
    return "F (multiple)"


# ===========================================================================
# 1. hunter_demand_gpm
# ===========================================================================

def hunter_demand_gpm(
    fixture_units: float,
    system_type: str = "flush_tank",
) -> dict:
    """
    Convert total fixture units (FU) to design demand flow (GPM) via the
    Hunter probability curve (BMS 65, 1940).

    The Hunter curve models the simultaneous-use probability for a building
    water supply.  Two curves are provided:

    flush_tank  — Typical residential/light-commercial systems with gravity
                  flush tanks.  Lower peak demand.  (IPC Table E103.3(2))
    flush_valve — Systems with flush-valve (Flushometer) water closets or
                  urinals.  Higher peak demand.  (IPC Table E103.3(3))

    Parameters
    ----------
    fixture_units : float
        Total supply fixture units (WSFU) for the system.  Must be > 0.
        Common values: lavatory=1, shower=2, water_closet_FT=3,
        water_closet_FV=6, kitchen_sink=2, bathtub=2, dishwasher=2,
        washing_machine=2, hose_bib=3.
    system_type : str
        'flush_tank' (default) or 'flush_valve'.

    Returns
    -------
    dict
        ok               : True
        fixture_units    : FU input
        system_type      : system type used
        demand_gpm       : design demand (gpm) from Hunter curve
        warnings         : list of warning strings

    Units: flow in US gpm.

    References
    ----------
    Hunter, R.B. (1940) BMS 65, NBS
    IPC (2021) Appendix E, Tables E103.3(2)/(3)
    """
    warnings: list[str] = []

    err = _guard_positive("fixture_units", fixture_units)
    if err:
        return _err(err)

    st = str(system_type).strip().lower().replace("-", "_").replace(" ", "_")
    if st not in ("flush_tank", "flush_valve"):
        return _err(
            f"system_type must be 'flush_tank' or 'flush_valve', got {system_type!r}."
        )

    table = _HUNTER_FT if st == "flush_tank" else _HUNTER_FV
    demand = _interpolate_hunter(float(fixture_units), table)

    if fixture_units > 5000:
        warnings.append(
            f"Fixture units {fixture_units} exceeds Hunter curve table range (5000 FU). "
            "Demand extrapolated; verify with utility."
        )

    return {
        "ok": True,
        "fixture_units": float(fixture_units),
        "system_type": st,
        "demand_gpm": round(demand, 2),
        "warnings": warnings,
    }


# ===========================================================================
# 2. size_supply_pipe
# ===========================================================================

def size_supply_pipe(
    demand_gpm: float,
    available_pressure_psi: float,
    pipe_length_ft: float,
    elevation_diff_ft: float = 0.0,
    meter_loss_psi: float = 0.0,
    residual_pressure_psi: float = 8.0,
    material: str = "copper_l",
    velocity_limit_fps: float = 8.0,
) -> dict:
    """
    Select the minimum nominal pipe size for a cold-water supply branch.

    The available pressure budget is allocated as:
        ΔP_available = P_static - P_elevation - P_meter - P_residual
        ΔP_available ≥ ΔP_friction = (hf/L) × L

    Uses the Hazen-Williams equation (C = 150 for copper/plastic).
    Also enforces a velocity limit (default 8 ft/s per IPC §604.3).

    Parameters
    ----------
    demand_gpm : float
        Design flow demand at the fixture or branch (gpm).  Must be > 0.
    available_pressure_psi : float
        Static supply pressure at the meter or main connection (psi).  Must be > 0.
    pipe_length_ft : float
        Developed length of the supply pipe run including equivalent fittings
        length (ft).  Must be > 0.
    elevation_diff_ft : float
        Elevation from supply main to fixture (ft, positive = fixture above main).
        0.433 psi per foot is deducted.  Default 0.
    meter_loss_psi : float
        Pressure loss through the water meter at demand_gpm (psi).  Default 0.
    residual_pressure_psi : float
        Minimum required residual pressure at the fixture (psi).
        IPC §604.3: 8 psi minimum for most fixtures; 20 psi for flush valves.
        Default 8 psi.
    material : str
        Pipe material: 'copper_l' (default, C=150), 'galvanized' (C=120),
        'cpvc' (C=150), 'pex' (C=150).
    velocity_limit_fps : float
        Maximum allowable pipe velocity (ft/s).  Default 8.0 (IPC §604.3).

    Returns
    -------
    dict
        ok                    : True
        demand_gpm            : flow demand
        available_pressure_psi: static supply pressure
        elevation_loss_psi    : pressure loss due to elevation (psi)
        meter_loss_psi        : meter pressure loss (psi)
        residual_pressure_psi : required residual at fixture
        pressure_for_friction_psi : budget remaining for pipe friction
        recommended_nps       : smallest NPS that satisfies pressure + velocity
        pipe_id_inch          : inside diameter of recommended pipe (inches)
        friction_loss_psi     : actual friction loss in recommended pipe (psi)
        velocity_fps          : flow velocity in recommended pipe (ft/s)
        pressure_at_fixture_psi : estimated pressure at fixture (psi)
        warnings              : list of warning strings

    Units: flow gpm, pressure psi, length ft, velocity ft/s.

    References
    ----------
    IPC (2021) §604, Appendix E
    Hazen-Williams: hf/L = 4.52 × Q^1.85 / (C^1.85 × d^4.87)
    """
    warnings: list[str] = []

    for field, val in [
        ("demand_gpm", demand_gpm),
        ("available_pressure_psi", available_pressure_psi),
        ("pipe_length_ft", pipe_length_ft),
    ]:
        e = _guard_positive(field, val)
        if e:
            return _err(e)

    e = _guard_nonneg("elevation_diff_ft", elevation_diff_ft)
    if e:
        return _err(e)
    e = _guard_nonneg("meter_loss_psi", meter_loss_psi)
    if e:
        return _err(e)
    e = _guard_positive("residual_pressure_psi", residual_pressure_psi)
    if e:
        return _err(e)
    e = _guard_positive("velocity_limit_fps", velocity_limit_fps)
    if e:
        return _err(e)

    # Hazen-Williams C coefficient
    mat = str(material).strip().lower()
    hw_c_map = {
        "copper_l": 150.0,
        "copper":   150.0,
        "cpvc":     150.0,
        "pex":      150.0,
        "galvanized": 120.0,
        "steel":    120.0,
        "cast_iron": 100.0,
    }
    C = hw_c_map.get(mat, 150.0)

    elev_psi = float(elevation_diff_ft) * 0.433
    budget_psi = float(available_pressure_psi) - elev_psi - float(meter_loss_psi) - float(residual_pressure_psi)

    if budget_psi <= 0:
        warnings.append(
            f"Pressure budget for friction is {budget_psi:.2f} psi (≤ 0). "
            "Available pressure is insufficient even before pipe friction losses. "
            "Increase supply pressure or reduce elevation/meter losses."
        )

    Q = float(demand_gpm)
    L = float(pipe_length_ft)

    recommended_nps: str | None = None
    chosen_id: float = 0.0

    for nps in _SUPPLY_NPS_ORDER:
        d = _COPPER_L_ID[nps]
        hf = _hw_loss_psi_per_ft(Q, d, C) * L
        v = _pipe_velocity_fps(Q, d)
        # Select first size where friction fits budget AND velocity is acceptable
        if hf <= max(budget_psi, 0.0) and v <= float(velocity_limit_fps):
            recommended_nps = nps
            chosen_id = d
            break

    if recommended_nps is None:
        # Fall back to largest size
        recommended_nps = _SUPPLY_NPS_ORDER[-1]
        chosen_id = _COPPER_L_ID[recommended_nps]
        warnings.append(
            "No standard pipe size satisfies both pressure budget and velocity limit. "
            "Returning largest catalogued size (6\"). Redesign supply system."
        )

    friction_loss = _hw_loss_psi_per_ft(Q, chosen_id, C) * L
    velocity = _pipe_velocity_fps(Q, chosen_id)
    p_fixture = float(available_pressure_psi) - elev_psi - float(meter_loss_psi) - friction_loss

    if p_fixture < float(residual_pressure_psi):
        warnings.append(
            f"UNDER-PRESSURE AT FIXTURE: estimated pressure {p_fixture:.1f} psi is below "
            f"required residual {residual_pressure_psi} psi. "
            "Increase supply pressure or upsize pipe."
        )

    if velocity > float(velocity_limit_fps):
        warnings.append(
            f"PIPE UNDERSIZED: velocity {velocity:.1f} ft/s in NPS {recommended_nps} exceeds "
            f"limit of {velocity_limit_fps} ft/s (IPC §604.3). Consider upsizing."
        )

    return {
        "ok": True,
        "demand_gpm": Q,
        "available_pressure_psi": float(available_pressure_psi),
        "elevation_loss_psi": round(elev_psi, 3),
        "meter_loss_psi": float(meter_loss_psi),
        "residual_pressure_psi": float(residual_pressure_psi),
        "pressure_for_friction_psi": round(budget_psi, 3),
        "recommended_nps": recommended_nps,
        "pipe_id_inch": chosen_id,
        "friction_loss_psi": round(friction_loss, 3),
        "velocity_fps": round(velocity, 2),
        "pressure_at_fixture_psi": round(p_fixture, 2),
        "warnings": warnings,
    }


# ===========================================================================
# 3. dfu_to_drain_size
# ===========================================================================

def dfu_to_drain_size(
    dfu: int,
    pipe_type: str = "horizontal_branch",
) -> dict:
    """
    Select the minimum drainage pipe NPS for a given drainage fixture unit (DFU)
    load per IPC Table 710.1.

    Three pipe contexts are supported:
        horizontal_branch — individual fixture branch or horizontal drain
        building_drain    — building drain or sanitary sewer to street
        stack             — soil/waste stack (vertical)

    Parameters
    ----------
    dfu : int
        Total drainage fixture units served.  Must be >= 1.
        Common values: lavatory=1, shower=2, bathtub=2, water_closet=4,
        kitchen_sink=2, floor_drain=2, clothes_washer=3, dishwasher=2,
        urinal=2 (flush_valve=4).
    pipe_type : str
        'horizontal_branch' (default), 'building_drain', or 'stack'.

    Returns
    -------
    dict
        ok              : True
        dfu             : DFU input
        pipe_type       : pipe_type used
        recommended_nps : minimum NPS satisfying the DFU load
        pipe_id_inch    : nominal inside diameter (schedule-40 DWV, inches)
        warnings        : list of warning strings

    Units: NPS in nominal inches; id in actual inches.

    References
    ----------
    IPC (2021) Table 710.1(1)/(2)/(3)
    """
    warnings: list[str] = []

    try:
        dfu_int = int(dfu)
    except (TypeError, ValueError):
        return _err(f"dfu must be an integer, got {dfu!r}")
    if dfu_int < 1:
        return _err("dfu must be >= 1")

    pt = str(pipe_type).strip().lower().replace("-", "_").replace(" ", "_")
    if pt == "horizontal_branch":
        table = _IPC_HORIZ_BRANCH
    elif pt == "building_drain":
        table = _IPC_BLDG_DRAIN
    elif pt == "stack":
        table = _IPC_STACK
    else:
        return _err(
            f"pipe_type must be 'horizontal_branch', 'building_drain', or 'stack', "
            f"got {pipe_type!r}."
        )

    chosen_nps: str | None = None
    for nps in _DRAIN_NPS_ORDER:
        if nps in table and dfu_int <= table[nps]:
            chosen_nps = nps
            break

    if chosen_nps is None:
        warnings.append(
            f"DFU load {dfu_int} exceeds IPC table range for {pt}. "
            "Using 12\" — verify with engineer."
        )
        chosen_nps = "12"

    id_inch = _DWV_ID.get(chosen_nps, 0.0)

    if dfu_int > table.get(chosen_nps, 0) * 0.9:
        warnings.append(
            f"DFU load {dfu_int} is within 10% of capacity for NPS {chosen_nps}. "
            "Consider upsizing one size."
        )

    return {
        "ok": True,
        "dfu": dfu_int,
        "pipe_type": pt,
        "recommended_nps": chosen_nps,
        "pipe_id_inch": id_inch,
        "warnings": warnings,
    }


# ===========================================================================
# 4. vent_size
# ===========================================================================

def vent_size(
    dfu_served: int,
    developed_length_ft: float,
) -> dict:
    """
    Select the minimum vent pipe NPS per IPC Table 906.2.

    The vent pipe must satisfy both the DFU load and the developed length from
    the trap to the vent terminal (or to the vent stack connection).

    Parameters
    ----------
    dfu_served : int
        Drainage fixture units drained through the trap or branch that this
        vent serves.  Must be >= 1.
    developed_length_ft : float
        Developed (measured along pipe) length of the vent run from trap to
        vent stack or open air terminal (ft).  Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        dfu_served          : DFU input
        developed_length_ft : developed length input (ft)
        recommended_nps     : minimum vent NPS satisfying both constraints
        warnings            : list of warning strings

    Units: length ft, NPS nominal inches.

    References
    ----------
    IPC (2021) Table 906.2 — Size and Length of Vents
    """
    warnings: list[str] = []

    try:
        dfu_int = int(dfu_served)
    except (TypeError, ValueError):
        return _err(f"dfu_served must be an integer, got {dfu_served!r}")
    if dfu_int < 1:
        return _err("dfu_served must be >= 1")

    e = _guard_positive("developed_length_ft", developed_length_ft)
    if e:
        return _err(e)

    nps = _select_vent_size(dfu_int, float(developed_length_ft))
    if nps is None:
        nps = "6"
        warnings.append(
            f"DFU {dfu_int} and length {developed_length_ft:.0f} ft exceeds IPC Table "
            "906.2 range. Using 6\" — verify with engineer."
        )

    if developed_length_ft > 200:
        warnings.append(
            "Long vent run > 200 ft; verify adequate slope (min 1/4\"/ft) and "
            "consider additional relief vents."
        )

    return {
        "ok": True,
        "dfu_served": dfu_int,
        "developed_length_ft": float(developed_length_ft),
        "recommended_nps": nps,
        "warnings": warnings,
    }


# ===========================================================================
# 5. trap_arm_slope
# ===========================================================================

def trap_arm_slope(
    trap_arm_length_ft: float,
    trap_size_nps: str,
    slope_in_per_ft: float = 0.25,
) -> dict:
    """
    Check trap-arm slope and length compliance per IPC §1002.1.

    The trap arm is the drain pipe segment between the trap outlet weir and the
    vent connection.  IPC limits:
      - Max trap arm length depends on trap size (IPC Table 1002.1)
      - Slope: 1/4" per foot (2.08%) recommended; >1/2" per foot is prohibited
        (creates back-siphonage)
      - Slope must be ≥ 1/8" per foot (1.04%) to maintain self-cleaning velocity

    Parameters
    ----------
    trap_arm_length_ft : float
        Actual trap arm length from trap outlet to vent (ft).  Must be > 0.
    trap_size_nps : str
        Nominal trap/trap-arm pipe size.  Supported: '1-1/4', '1-1/2', '2',
        '3', '4' and larger.
    slope_in_per_ft : float
        Actual slope of trap arm (inches drop per foot of run).
        Default 0.25 (1/4" per foot).

    Returns
    -------
    dict
        ok                   : True
        trap_arm_length_ft   : actual trap arm length (ft)
        trap_size_nps        : NPS used
        slope_in_per_ft      : slope used (in/ft)
        slope_pct            : slope expressed as percent (%)
        max_arm_length_ft    : IPC Table 1002.1 maximum (ft)
        arm_length_ok        : True if ≤ max
        slope_ok             : True if 1/8 ≤ slope ≤ 1/4 in/ft (code range)
        warnings             : list of warning strings

    Units: length ft, slope in/ft.

    References
    ----------
    IPC (2021) §1002.1, Table 1002.1 — Trap Arm Length
    """
    warnings: list[str] = []

    e = _guard_positive("trap_arm_length_ft", trap_arm_length_ft)
    if e:
        return _err(e)
    e = _guard_positive("slope_in_per_ft", slope_in_per_ft)
    if e:
        return _err(e)

    # IPC Table 1002.1 maximum trap arm lengths (ft)
    _trap_arm_max: dict[str, float] = {
        "1-1/4": 2.5,
        "1-1/2": 3.5,
        "2":     5.0,
        "3":     6.0,
        "4":     10.0,
    }

    nps_str = str(trap_size_nps).strip()
    if nps_str not in _trap_arm_max:
        # For sizes > 4" use 10 ft as a default (unlimited per some interpretations)
        max_len = 10.0
        warnings.append(
            f"Trap size NPS {trap_size_nps!r} not in IPC Table 1002.1. "
            "Using 10 ft default maximum."
        )
    else:
        max_len = _trap_arm_max[nps_str]

    arm_ok = float(trap_arm_length_ft) <= max_len
    if not arm_ok:
        warnings.append(
            f"TRAP ARM TOO LONG: {trap_arm_length_ft:.2f} ft exceeds IPC §1002.1 "
            f"maximum of {max_len:.1f} ft for NPS {nps_str}. Move vent closer to trap."
        )

    s = float(slope_in_per_ft)
    slope_pct = s / 12.0 * 100.0  # in/ft → percent

    slope_ok = (1.0 / 8.0) <= s <= (1.0 / 2.0)
    if s < 1.0 / 8.0:
        warnings.append(
            f"SLOPE-OUT-OF-RANGE: slope {s:.3f} in/ft is below minimum 1/8 in/ft "
            "(IPC §704.1). Drain may not self-clean."
        )
    if s > 1.0 / 2.0:
        warnings.append(
            f"SLOPE-OUT-OF-RANGE: slope {s:.3f} in/ft exceeds maximum 1/2 in/ft "
            "(IPC §1002.1). Trap seal may be siphoned."
        )

    return {
        "ok": True,
        "trap_arm_length_ft": float(trap_arm_length_ft),
        "trap_size_nps": nps_str,
        "slope_in_per_ft": s,
        "slope_pct": round(slope_pct, 3),
        "max_arm_length_ft": max_len,
        "arm_length_ok": arm_ok,
        "slope_ok": slope_ok,
        "warnings": warnings,
    }


# ===========================================================================
# 6. drain_slope_manning
# ===========================================================================

def drain_slope_manning(
    pipe_nps: str,
    slope_in_per_ft: float,
    n_manning: float = 0.013,
) -> dict:
    """
    Compute full-flow and half-flow drain capacity using Manning's equation.

    Manning's equation for circular pipe:
        Q = (1.486/n) × A × R^(2/3) × S^(1/2)

    where R = hydraulic radius = d/4 for full flow, A = π d²/4 for full flow,
    and for half flow R = d/4, A = π d²/8 (analytically exact).

    IPC §704.1 minimum slope: 1/4" per foot for pipes ≤ 3"; 1/8" per foot
    for pipes ≥ 4".

    Parameters
    ----------
    pipe_nps : str
        Nominal pipe size.  Must be in DWV table: '1-1/4' through '12'.
    slope_in_per_ft : float
        Drain slope in inches per foot (in/ft).  Must be > 0.
    n_manning : float
        Manning roughness coefficient.  Default 0.013 (PVC/ABS DWV).
        Use 0.015 for cast iron, 0.012 for smooth plastic.

    Returns
    -------
    dict
        ok                : True
        pipe_nps          : NPS used
        pipe_id_inch      : inside diameter (in)
        slope_in_per_ft   : slope input (in/ft)
        slope_ft_per_ft   : slope as dimensionless ratio
        slope_pct         : slope as percent
        full_flow_gpm     : full-flow capacity (gpm)
        half_flow_gpm     : half-flow capacity (gpm)
        full_flow_fps     : full-flow velocity (ft/s)
        half_flow_fps     : half-flow velocity (ft/s)
        slope_ok          : True if slope meets IPC §704.1 minimum for pipe size
        warnings          : list of warning strings

    Units: flow gpm, velocity ft/s, length ft.

    References
    ----------
    IPC (2021) §704.1 — Slope of Horizontal Drainage Pipe
    Manning (1891) Transactions ASCE
    """
    warnings: list[str] = []

    nps_str = str(pipe_nps).strip()
    if nps_str not in _DWV_ID:
        return _err(
            f"pipe_nps {pipe_nps!r} not recognised. "
            f"Supported: {list(_DWV_ID.keys())}"
        )

    e = _guard_positive("slope_in_per_ft", slope_in_per_ft)
    if e:
        return _err(e)
    e = _guard_positive("n_manning", n_manning)
    if e:
        return _err(e)

    d_inch = _DWV_ID[nps_str]
    d_ft = d_inch / 12.0
    S = float(slope_in_per_ft) / 12.0  # in/ft → ft/ft

    # IPC §704.1 minimum slope
    # Pipes ≤ 3" NPS: min 1/4" per foot
    # Pipes ≥ 4" NPS: min 1/8" per foot
    _large_nps = {"4", "5", "6", "8", "10", "12"}
    min_slope = 1.0 / 8.0 if nps_str in _large_nps else 1.0 / 4.0
    slope_ok = float(slope_in_per_ft) >= min_slope

    if not slope_ok:
        warnings.append(
            f"SLOPE-OUT-OF-RANGE: slope {slope_in_per_ft:.3f} in/ft is below IPC "
            f"§704.1 minimum of {min_slope:.3f} in/ft for NPS {nps_str}."
        )

    n = float(n_manning)

    # Full flow
    A_full = math.pi / 4.0 * d_ft ** 2  # ft²
    R_full = d_ft / 4.0                  # ft (R = A/P = (π d²/4)/(π d) = d/4)
    V_full_fps = (1.486 / n) * (R_full ** (2.0 / 3.0)) * (S ** 0.5)
    Q_full_cfs = V_full_fps * A_full
    Q_full_gpm = Q_full_cfs * 7.48052 * 60.0

    # Half flow (analytically: R = d/4, A = π d²/8; V = same as full for d/4 R;
    # but Manning for half-full circular pipe: R_half = d/4 exactly → same R as full;
    # V_half = V_full; Q_half = Q_full / 2)
    # Note: this is the exact analytical result for a circular pipe at half-full depth.
    Q_half_gpm = Q_full_gpm / 2.0
    V_half_fps = V_full_fps  # same velocity at half-full for circular pipe (Manning)

    return {
        "ok": True,
        "pipe_nps": nps_str,
        "pipe_id_inch": d_inch,
        "slope_in_per_ft": float(slope_in_per_ft),
        "slope_ft_per_ft": round(S, 6),
        "slope_pct": round(S * 100.0, 4),
        "full_flow_gpm": round(Q_full_gpm, 2),
        "half_flow_gpm": round(Q_half_gpm, 2),
        "full_flow_fps": round(V_full_fps, 3),
        "half_flow_fps": round(V_half_fps, 3),
        "slope_ok": slope_ok,
        "warnings": warnings,
    }


# ===========================================================================
# 7. hot_water_heater_size
# ===========================================================================

def hot_water_heater_size(
    occupancy_type: str,
    num_units: float,
    inlet_temp_f: float = 55.0,
    supply_temp_f: float = 120.0,
    recovery_efficiency: float = 0.80,
    fuel_btu_hr: float | None = None,
) -> dict:
    """
    Size a storage water heater (peak hourly demand, recovery, storage volume).

    Uses ASHRAE Applications (2019) Chapter 50 per-occupancy peak demand and
    storage guidelines for sizing service hot-water heaters.

    Parameters
    ----------
    occupancy_type : str
        Building occupancy type.  Supported:
            'apartment'   — per unit
            'dormitory'   — per student
            'motel'       — per room
            'hotel'       — per room
            'office'      — per person
            'restaurant'  — per seat (per meal)
            'school_elem' — per student
            'school_high' — per student
            'hospital'    — per bed
    num_units : float
        Number of units/rooms/persons/seats as applicable.  Must be > 0.
    inlet_temp_f : float
        Cold water supply temperature (°F).  Default 55 °F.
    supply_temp_f : float
        Desired hot-water supply temperature (°F).  Default 120 °F.
    recovery_efficiency : float
        Heater thermal efficiency (0 < η ≤ 1).  Default 0.80.
    fuel_btu_hr : float | None
        Heater fuel input rate (BTU/hr).  If None, sized to meet peak hour demand.

    Returns
    -------
    dict
        ok                   : True
        occupancy_type       : occupancy used
        num_units            : number of units
        peak_hourly_gal      : peak hourly hot-water demand (gallons)
        daily_demand_gal     : average daily demand (gallons)
        delta_T_f            : temperature rise (°F)
        recovery_rate_gph    : required recovery rate (gallons per hour)
        heater_btu_hr        : required heater input (BTU/hr)
        storage_volume_gal   : recommended storage volume (gallons)
        warnings             : list of warning strings

    Units: flow gallons, temperature °F, heat BTU/hr.

    References
    ----------
    ASHRAE Handbook — HVAC Applications (2019), Chapter 50, Tables 7–9
    """
    warnings: list[str] = []

    # ASHRAE Chapter 50 Table 7 — daily demand and peak hour percentages
    # (daily_gal_per_unit, peak_hour_fraction_of_daily)
    _ASHRAE_HW: dict[str, tuple[float, float]] = {
        "apartment":   (60.0,  0.17),   # 60 gal/day/unit, 17% in peak hour
        "dormitory":   (13.1,  0.30),
        "motel":       (40.0,  0.13),
        "hotel":       (50.0,  0.12),
        "office":      (1.0,   0.25),   # 1 gal/person/day
        "restaurant":  (2.4,   0.33),   # per meal (seat)
        "school_elem": (0.6,   0.33),
        "school_high": (1.8,   0.33),
        "hospital":    (90.0,  0.12),
    }

    ot = str(occupancy_type).strip().lower().replace("-", "_").replace(" ", "_")
    if ot not in _ASHRAE_HW:
        return _err(
            f"occupancy_type {occupancy_type!r} not supported. "
            f"Supported: {sorted(_ASHRAE_HW.keys())}."
        )

    e = _guard_positive("num_units", num_units)
    if e:
        return _err(e)
    e = _guard_positive("inlet_temp_f", inlet_temp_f)
    if e:
        return _err(e)
    e = _guard_positive("supply_temp_f", supply_temp_f)
    if e:
        return _err(e)

    if supply_temp_f <= inlet_temp_f:
        return _err(
            f"supply_temp_f ({supply_temp_f}°F) must be > inlet_temp_f ({inlet_temp_f}°F)."
        )

    e = _guard_positive("recovery_efficiency", recovery_efficiency)
    if e:
        return _err(e)
    if recovery_efficiency > 1.0:
        return _err("recovery_efficiency must be ≤ 1.0")

    daily_per_unit, peak_fraction = _ASHRAE_HW[ot]
    daily_gal = daily_per_unit * float(num_units)
    peak_hour_gal = daily_gal * peak_fraction

    delta_T = float(supply_temp_f) - float(inlet_temp_f)

    # BTU to heat one gallon: 8.33 lb/gal × 1 BTU/(lb·°F)
    BTU_PER_GAL = 8.33
    recovery_rate_gph = peak_hour_gal  # must recover peak hour demand in one hour
    heater_btu_hr_required = (recovery_rate_gph * BTU_PER_GAL * delta_T) / float(recovery_efficiency)

    if fuel_btu_hr is not None:
        e = _guard_positive("fuel_btu_hr", fuel_btu_hr)
        if e:
            return _err(e)
        actual_recovery_gph = (float(fuel_btu_hr) * float(recovery_efficiency)) / (BTU_PER_GAL * delta_T)
        if actual_recovery_gph < recovery_rate_gph:
            warnings.append(
                f"UNDERSIZED HEATER: fuel input {fuel_btu_hr:.0f} BTU/hr provides "
                f"{actual_recovery_gph:.1f} gph recovery — less than peak demand "
                f"{recovery_rate_gph:.1f} gph. Increase heater size or add storage."
            )
        heater_btu_hr_used = float(fuel_btu_hr)
    else:
        heater_btu_hr_used = heater_btu_hr_required

    # Storage volume recommendation: ASHRAE — typically 1.5× peak hour demand
    # for apartment/hotel; higher fraction for low-demand occupancies
    storage_gal = peak_hour_gal * 1.5

    if supply_temp_f < 120.0:
        warnings.append(
            f"Supply temperature {supply_temp_f}°F is below 120°F recommended minimum "
            "(ASHRAE/ASSE 1070). Risk of Legionella growth."
        )
    if supply_temp_f > 140.0:
        warnings.append(
            f"Supply temperature {supply_temp_f}°F exceeds 140°F; "
            "scald risk — install thermostatic mixing valve (ASSE 1017)."
        )

    return {
        "ok": True,
        "occupancy_type": ot,
        "num_units": float(num_units),
        "peak_hourly_gal": round(peak_hour_gal, 1),
        "daily_demand_gal": round(daily_gal, 1),
        "delta_T_f": round(delta_T, 1),
        "recovery_rate_gph": round(recovery_rate_gph, 1),
        "heater_btu_hr": round(heater_btu_hr_used, 0),
        "storage_volume_gal": round(storage_gal, 1),
        "warnings": warnings,
    }


# ===========================================================================
# 8. hw_recirculation_loop
# ===========================================================================

def hw_recirculation_loop(
    loop_length_ft: float,
    pipe_nps: str,
    supply_temp_f: float = 140.0,
    ambient_temp_f: float = 70.0,
    insulation_r_value: float = 4.0,
) -> dict:
    """
    Size a hot-water recirculation loop: pump flow, pipe heat loss, pump head.

    The recirculation loop maintains hot water within a few degrees of the set
    point at all fixtures.  The minimum recirculation flow must compensate for
    heat loss from the distribution pipe.

    Heat loss per foot:
        q = (T_supply - T_ambient) / (R_insulation + R_pipe)
    where R_pipe is assumed small (smooth copper), so:
        q ≈ (T_supply - T_ambient) / R_insulation  [BTU/hr per foot]

    The return pump must deliver enough flow to absorb this heat loss with a
    temperature drop ΔT_drop = 10°F (typical design criterion, ASHRAE §50.6):
        Q_recirc_gpm = q_total_btu_hr / (500 × ΔT_drop)

    Parameters
    ----------
    loop_length_ft : float
        Total developed length of the hot-water distribution loop (ft).
        Must be > 0.
    pipe_nps : str
        Hot-water supply pipe NPS.  Must be in copper-L table.
    supply_temp_f : float
        Hot-water supply temperature (°F).  Default 140 °F.
    ambient_temp_f : float
        Ambient temperature around the pipes (°F).  Default 70 °F.
    insulation_r_value : float
        Pipe insulation R-value (hr·ft²·°F/BTU per inch of insulation thickness).
        Default 4.0 (approx. 1\" fiberglass, for a 1\" pipe).
        Use R=0 for uninsulated pipe (conservative).

    Returns
    -------
    dict
        ok                    : True
        loop_length_ft        : loop length (ft)
        pipe_nps              : NPS used
        supply_temp_f         : supply temperature (°F)
        ambient_temp_f        : ambient temperature (°F)
        insulation_r_value    : R-value used
        heat_loss_btu_hr_ft   : heat loss per foot of pipe (BTU/hr/ft)
        total_heat_loss_btu_hr: total loop heat loss (BTU/hr)
        recirc_flow_gpm       : required recirculation flow (gpm)
        pump_head_ft          : estimated pump head (ft WC) via Hazen-Williams
        warnings              : list of warning strings

    Units: flow gpm, temperature °F, length ft, heat BTU/hr.

    References
    ----------
    ASHRAE Handbook — HVAC Applications (2019), §50.6 — Recirculating Systems
    """
    warnings: list[str] = []

    e = _guard_positive("loop_length_ft", loop_length_ft)
    if e:
        return _err(e)

    nps_str = str(pipe_nps).strip()
    if nps_str not in _COPPER_L_ID:
        return _err(
            f"pipe_nps {pipe_nps!r} not recognised. "
            f"Supported: {list(_COPPER_L_ID.keys())}"
        )

    e = _guard_positive("supply_temp_f", supply_temp_f)
    if e:
        return _err(e)
    e = _guard_positive("insulation_r_value", insulation_r_value) if insulation_r_value > 0 else None
    if e:
        return _err(e)

    delta_T = float(supply_temp_f) - float(ambient_temp_f)
    if delta_T <= 0:
        return _err(
            "supply_temp_f must be > ambient_temp_f for heat loss calculation."
        )

    # Heat loss per foot: q (BTU/hr/ft) = ΔT / R_total
    # For a cylindrical pipe, R = R_insulation for simplified flat-wall approx.
    # R_insulation is given as total R-value (hr·ft²·°F/BTU); treat as thermal
    # resistance for a nominal 1 ft² of pipe surface.
    # More precisely, R per linear foot = R_value / (π × d_inch/12)
    d_ft = _COPPER_L_ID[nps_str] / 12.0
    circum_ft = math.pi * d_ft  # ft

    if float(insulation_r_value) > 0:
        R_total = float(insulation_r_value) / circum_ft  # hr·°F/BTU per linear foot
    else:
        # Uninsulated: use convective surface resistance only (approx. 0.5 hr·ft²·°F/BTU)
        R_surface = 0.5
        R_total = R_surface / circum_ft
        warnings.append(
            "Insulation R-value is 0 (uninsulated pipe). Heat loss will be high; "
            "insulation strongly recommended (ASHRAE §50.6)."
        )

    q_per_ft = delta_T / R_total  # BTU/hr/ft
    q_total = q_per_ft * float(loop_length_ft)  # BTU/hr

    # Required recirculation flow:
    # Q = q_total / (500 × ΔT_drop) where 500 = 8.33 lb/gal × 60 min/hr
    # ASHRAE design uses ΔT_drop = 10°F
    delta_T_drop = 10.0
    q_recirc_gpm = q_total / (500.0 * delta_T_drop)

    if q_recirc_gpm < 0.1:
        q_recirc_gpm = 0.1  # minimum practical pump flow
        warnings.append(
            "Calculated recirculation flow < 0.1 gpm; set to practical minimum 0.1 gpm."
        )

    # Pump head: Hazen-Williams friction × loop length
    d_inch = _COPPER_L_ID[nps_str]
    hf_psi = _hw_loss_psi_per_ft(q_recirc_gpm, d_inch, _HW_C_SUPPLY) * float(loop_length_ft)
    pump_head_ft = hf_psi * 2.31  # psi → ft WC (1 psi = 2.31 ft WC)

    if q_recirc_gpm > 2.0:
        warnings.append(
            f"Recirculation flow {q_recirc_gpm:.2f} gpm is high; "
            "verify loop insulation and consider upsizing insulation thickness."
        )

    return {
        "ok": True,
        "loop_length_ft": float(loop_length_ft),
        "pipe_nps": nps_str,
        "supply_temp_f": float(supply_temp_f),
        "ambient_temp_f": float(ambient_temp_f),
        "insulation_r_value": float(insulation_r_value),
        "heat_loss_btu_hr_ft": round(q_per_ft, 3),
        "total_heat_loss_btu_hr": round(q_total, 1),
        "recirc_flow_gpm": round(q_recirc_gpm, 3),
        "pump_head_ft": round(pump_head_ft, 3),
        "warnings": warnings,
    }


# ===========================================================================
# 9. storm_drain_leader
# ===========================================================================

def storm_drain_leader(
    roof_area_ft2: float,
    rainfall_rate_in_hr: float,
    leader_type: str = "vertical",
) -> dict:
    """
    Size roof storm drain leaders and horizontal storm drains.

    IPC Table 1106.2 / 1106.3: storm-drain leader capacity at 100-year rainfall
    intensity.  Flow is computed as:
        Q_gpm = roof_area_ft2 × rainfall_rate_in_hr / 96.23
    (derived from: 1 in/hr over 1 ft² = 0.00694 gpm ≈ 1/144 gpm)

    IPC Table 1106.2 lists vertical round roof-drain leader capacities (gpm)
    by diameter.  Table 1106.3 gives horizontal storm drain capacities.

    Parameters
    ----------
    roof_area_ft2 : float
        Horizontal roof area draining to this leader (ft²).  Must be > 0.
    rainfall_rate_in_hr : float
        Design rainfall rate (in/hr).  Use 100-year storm intensity for the
        project location.  Must be > 0.
    leader_type : str
        'vertical' (default) — vertical roof leader/downspout
        'horizontal'         — horizontal storm drain

    Returns
    -------
    dict
        ok                  : True
        roof_area_ft2       : roof area (ft²)
        rainfall_rate_in_hr : rainfall rate (in/hr)
        design_flow_gpm     : design storm-flow (gpm)
        leader_type         : leader type used
        recommended_nps     : minimum leader/drain NPS
        pipe_id_inch        : inside diameter of recommended pipe (inches)
        warnings            : list of warning strings

    Units: flow gpm, area ft², rainfall in/hr.

    References
    ----------
    IPC (2021) Table 1106.2 — Size of Vertical Conductors and Leaders
    IPC (2021) Table 1106.3 — Size of Horizontal Storm Drainage Piping
    """
    warnings: list[str] = []

    e = _guard_positive("roof_area_ft2", roof_area_ft2)
    if e:
        return _err(e)
    e = _guard_positive("rainfall_rate_in_hr", rainfall_rate_in_hr)
    if e:
        return _err(e)

    lt = str(leader_type).strip().lower().replace("-", "_")
    if lt not in ("vertical", "horizontal"):
        return _err(
            f"leader_type must be 'vertical' or 'horizontal', got {leader_type!r}."
        )

    # Q (gpm) = area (ft²) × rainfall (in/hr) / 96.23
    # Factor: 1 in/hr × 1 ft² = (1/12 ft/hr × 1 ft²) = (1/12)/3600 ft³/s = 7.48×60/12/3600 gpm = 1/96.23 gpm
    Q_gpm = float(roof_area_ft2) * float(rainfall_rate_in_hr) / 96.23

    # IPC Table 1106.2 — vertical leader capacity (gpm)
    _VERT_LEADER: list[tuple[str, float]] = [
        ("2",    34.0),
        ("2-1/2", 78.0),
        ("3",    139.0),
        ("4",    320.0),
        ("5",    625.0),
        ("6",    1100.0),
        ("8",    2600.0),
    ]

    # IPC Table 1106.3 — horizontal storm drain at 1/8" per foot slope (gpm)
    _HORIZ_STORM: list[tuple[str, float]] = [
        ("3",    75.0),
        ("4",    200.0),
        ("5",    398.0),
        ("6",    695.0),
        ("8",    1580.0),
        ("10",   2855.0),
        ("12",   4600.0),
        ("15",   8650.0),
    ]

    # DWV inside diameter for nominal storm drain sizes
    _STORM_ID: dict[str, float] = {
        "2":     2.067,
        "2-1/2": 2.469,
        "3":     3.068,
        "4":     4.026,
        "5":     5.047,
        "6":     6.065,
        "8":     7.981,
        "10":    10.020,
        "12":    11.938,
        "15":    15.0,   # approximate
    }

    table = _VERT_LEADER if lt == "vertical" else _HORIZ_STORM

    chosen_nps: str | None = None
    for nps, cap_gpm in table:
        if Q_gpm <= cap_gpm:
            chosen_nps = nps
            break

    if chosen_nps is None:
        chosen_nps = table[-1][0]
        warnings.append(
            f"PIPE UNDERSIZED: design flow {Q_gpm:.1f} gpm exceeds capacity of "
            f"largest standard {lt} leader ({table[-1][1]:.0f} gpm, NPS {table[-1][0]}\"). "
            "Use multiple leaders or contact engineer."
        )

    id_inch = _STORM_ID.get(chosen_nps, 0.0)

    if rainfall_rate_in_hr > 12.0:
        warnings.append(
            f"Rainfall rate {rainfall_rate_in_hr} in/hr is very high. "
            "Verify 100-year storm intensity for project location."
        )

    return {
        "ok": True,
        "roof_area_ft2": float(roof_area_ft2),
        "rainfall_rate_in_hr": float(rainfall_rate_in_hr),
        "design_flow_gpm": round(Q_gpm, 2),
        "leader_type": lt,
        "recommended_nps": chosen_nps,
        "pipe_id_inch": id_inch,
        "warnings": warnings,
    }


# ===========================================================================
# 10. water_hammer_arrestor
# ===========================================================================

def water_hammer_arrestor(
    fixture_units: int,
    location: str = "supply_branch",
) -> dict:
    """
    Select a water hammer arrestor (WHA) size per PDI WH-201.

    PDI WH-201 divides fixture unit loads into six size categories (A–F).
    A single WHA is typically installed at each branch serving quick-closing
    valves (solenoid valves, washing machines, dishwashers, etc.).

    Parameters
    ----------
    fixture_units : int
        Total supply fixture units on the branch to be protected.  Must be >= 1.
        WHA is sized for all fixtures on the branch up to the device.
    location : str
        Descriptive location label (informational only).  Default 'supply_branch'.

    Returns
    -------
    dict
        ok              : True
        fixture_units   : FU input
        location        : location label
        pdi_size        : PDI WH-201 size letter (A–F, or 'F (multiple)')
        description     : size description
        warnings        : list of warning strings

    Units: dimensionless (PDI sizing guide categories).

    References
    ----------
    PDI WH-201 (2017) — Water Hammer Arrestor Sizing Guide
    ASME A112.26.1 — Water Hammer Arresters
    """
    warnings: list[str] = []

    try:
        fu_int = int(fixture_units)
    except (TypeError, ValueError):
        return _err(f"fixture_units must be an integer, got {fixture_units!r}")
    if fu_int < 1:
        return _err("fixture_units must be >= 1")

    pdi_size = _pdi_unit(fu_int)

    _PDI_DESC = {
        "A": "PDI Size A: 1–11 FU — small branch (lavatory, dishwasher)",
        "B": "PDI Size B: 12–32 FU — single-family home branch",
        "C": "PDI Size C: 33–60 FU — multi-unit residential branch",
        "D": "PDI Size D: 61–112 FU — commercial branch",
        "E": "PDI Size E: 113–154 FU — large commercial branch",
        "F": "PDI Size F: 155–329 FU — industrial branch",
        "F (multiple)": "PDI Size F (multiple): > 329 FU — use two or more Size F units",
    }

    desc = _PDI_DESC.get(pdi_size, pdi_size)

    if fu_int > 329:
        warnings.append(
            f"Fixture units {fu_int} exceeds single Size F limit (329 FU). "
            "Install two or more Size F water hammer arrestors."
        )

    return {
        "ok": True,
        "fixture_units": fu_int,
        "location": str(location),
        "pdi_size": pdi_size,
        "description": desc,
        "warnings": warnings,
    }


# ===========================================================================
# 11. expansion_tank_heater
# ===========================================================================

def expansion_tank_heater(
    system_water_volume_gal: float,
    supply_temp_f: float = 120.0,
    cold_fill_temp_f: float = 40.0,
    system_pressure_psi: float = 80.0,
    relief_valve_psi: float = 150.0,
) -> dict:
    """
    Size a diaphragm-type expansion tank for a closed water-heater system.

    For a closed (no back-flow) water-heating system, thermal expansion of water
    increases system pressure.  An expansion tank accommodates this volume change.

    ASME/ASHRAE sizing equation (simplified for water heaters):
        V_tank = V_sys × (v_hot/v_cold - 1) / (1 - P_fill/P_max)

    where:
        V_sys   = system water volume (gal)
        v_hot   = specific volume of water at supply temp
        v_cold  = specific volume of water at cold fill temp
        P_fill  = absolute pre-charge pressure = P_static + 14.7 (psia)
        P_max   = absolute maximum system pressure (relief valve setting + 14.7 psia)

    Parameters
    ----------
    system_water_volume_gal : float
        Total system water volume (gallons) — heater tank + distribution piping.
        Must be > 0.
    supply_temp_f : float
        Hot-water supply temperature (°F).  Default 120 °F.
    cold_fill_temp_f : float
        Cold-water fill temperature (°F).  Default 40 °F.
    system_pressure_psi : float
        Static fill pressure at the expansion tank (psi gauge).  Default 80 psi.
    relief_valve_psi : float
        Temperature/pressure relief valve setting (psi gauge).  Default 150 psi.

    Returns
    -------
    dict
        ok                        : True
        system_water_volume_gal   : system volume (gal)
        supply_temp_f             : supply temperature (°F)
        cold_fill_temp_f          : cold fill temperature (°F)
        system_pressure_psi       : fill pressure (psig)
        relief_valve_psi          : T&P relief valve setting (psig)
        v_hot_ft3_lb              : specific volume at supply temp (ft³/lb)
        v_cold_ft3_lb             : specific volume at cold fill temp (ft³/lb)
        volume_expansion_gal      : volume of water expansion (gal)
        expansion_tank_volume_gal : minimum expansion tank acceptance volume (gal)
        warnings                  : list of warning strings

    Units: volume gallons, temperature °F, pressure psi (gauge).

    References
    ----------
    ASME A112.4.3M — Plumbing Fixture Fittings
    ASHRAE Handbook — HVAC Applications (2019), §50.7 — Expansion Tanks
    Incropera, DeWitt — Fundamentals of Heat and Mass Transfer (water properties)
    """
    warnings: list[str] = []

    e = _guard_positive("system_water_volume_gal", system_water_volume_gal)
    if e:
        return _err(e)
    e = _guard_positive("supply_temp_f", supply_temp_f)
    if e:
        return _err(e)
    e = _guard_positive("cold_fill_temp_f", cold_fill_temp_f)
    if e:
        return _err(e)
    e = _guard_positive("system_pressure_psi", system_pressure_psi)
    if e:
        return _err(e)
    e = _guard_positive("relief_valve_psi", relief_valve_psi)
    if e:
        return _err(e)

    if supply_temp_f <= cold_fill_temp_f:
        return _err(
            f"supply_temp_f ({supply_temp_f}°F) must be > cold_fill_temp_f ({cold_fill_temp_f}°F)."
        )

    if relief_valve_psi <= system_pressure_psi:
        return _err(
            f"relief_valve_psi ({relief_valve_psi}) must be > system_pressure_psi ({system_pressure_psi})."
        )

    # Specific volume of water (ft³/lb) using tabulated IAPWS-IF97 values
    # with linear interpolation.  Valid range 32–212°F.
    # Table: (T_fahrenheit, specific_volume_ft3_lb)
    _SV_TABLE: list[tuple[float, float]] = [
        (32.0,  0.016021),   # 0°C
        (39.2,  0.016019),   # 4°C (maximum density)
        (50.0,  0.016023),   # 10°C
        (68.0,  0.016047),   # 20°C
        (86.0,  0.016088),   # 30°C
        (104.0, 0.016144),   # 40°C
        (122.0, 0.016212),   # 50°C
        (140.0, 0.016292),   # 60°C
        (158.0, 0.016383),   # 70°C
        (176.0, 0.016483),   # 80°C
        (194.0, 0.016594),   # 90°C
        (212.0, 0.016714),   # 100°C
    ]

    def _specific_volume_ft3_lb(T_f: float) -> float:
        """Specific volume of liquid water (ft³/lb) at T°F via table interpolation."""
        T = float(T_f)
        if T <= _SV_TABLE[0][0]:
            return _SV_TABLE[0][1]
        if T >= _SV_TABLE[-1][0]:
            return _SV_TABLE[-1][1]
        for i in range(len(_SV_TABLE) - 1):
            x0, y0 = _SV_TABLE[i]
            x1, y1 = _SV_TABLE[i + 1]
            if x0 <= T <= x1:
                return y0 + (T - x0) * (y1 - y0) / (x1 - x0)
        return _SV_TABLE[-1][1]

    v_hot = _specific_volume_ft3_lb(float(supply_temp_f))
    v_cold = _specific_volume_ft3_lb(float(cold_fill_temp_f))

    # Expansion factor
    expansion_factor = v_hot / v_cold - 1.0
    V_sys = float(system_water_volume_gal)
    V_expansion_gal = V_sys * expansion_factor

    # Acceptance volume (diaphragm tank sizing):
    P_fill_abs = float(system_pressure_psi) + 14.7   # psia
    P_max_abs = float(relief_valve_psi) + 14.7       # psia

    acceptance_volume_gal = V_expansion_gal / (1.0 - P_fill_abs / P_max_abs)

    # Round up to nearest commercial size
    tank_volume_gal = acceptance_volume_gal * 1.10  # 10% safety factor

    if tank_volume_gal < 2.0:
        tank_volume_gal = 2.0  # minimum commercial size

    if float(supply_temp_f) > 140.0:
        warnings.append(
            f"Supply temperature {supply_temp_f}°F exceeds 140°F; "
            "verify T&P relief valve rating (ASME 120 psi / 210°F for residential)."
        )

    if acceptance_volume_gal < 0:
        warnings.append(
            "Acceptance volume calculation yielded negative value. "
            "Check that relief_valve_psi >> system_pressure_psi."
        )
        acceptance_volume_gal = 0.0
        tank_volume_gal = 2.0

    return {
        "ok": True,
        "system_water_volume_gal": V_sys,
        "supply_temp_f": float(supply_temp_f),
        "cold_fill_temp_f": float(cold_fill_temp_f),
        "system_pressure_psi": float(system_pressure_psi),
        "relief_valve_psi": float(relief_valve_psi),
        "v_hot_ft3_lb": round(v_hot, 6),
        "v_cold_ft3_lb": round(v_cold, 6),
        "volume_expansion_gal": round(V_expansion_gal, 3),
        "expansion_tank_volume_gal": round(tank_volume_gal, 2),
        "warnings": warnings,
    }
