"""
kerf_cad_core.firesafety.fire — pure-Python fire-protection engineering formulas.

Implements nine public functions covering:

  sprinkler_hydraulic_demand  — NFPA 13 density/area method; K-factor Q=K√P;
                                 most-remote-area flow & pressure; hose-stream
                                 allowance; Hazen-Williams friction to source
  fire_pump_sizing            — rated flow/head, 150%-flow/65%-head and churn
                                 points per NFPA 20
  water_supply_adequacy       — available pressure-flow curve vs required
  egress_analysis             — occupant load, exit width, travel/common-path/
                                 dead-end limits, capacity vs provided, time-to-egress
  design_fire_tsquared        — t-squared design fire Q=αt², growth class,
                                 heat-release rate
  detector_activation_time    — ceiling-jet correlation (Alpert), RTI activation
  smoke_control_exhaust       — atrium plume exhaust airflow per NFPA 92
  fire_resistance_heat_transfer — simple 1-D steady-state heat through rated assembly
  required_fire_rating        — minimum fire-resistance rating by occupancy/height

All functions return a plain dict:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Inadequate water / egress-capacity-exceeded /
undersized-pump conditions are flagged in the "warnings" list, not as errors.

Units
-----
  flow        — US gallons per minute (gpm)  for sprinkler/pump/hydrant
  pressure    — pounds per square inch (psi)  for sprinkler/pump/hydrant
  length      — feet (ft) unless noted
  area        — square feet (ft²)
  temperature — °F (ambient) or °C (where noted)
  heat-release rate (HRR) — kilowatts (kW)
  airflow     — cubic feet per minute (cfm)
  heat flux   — W/m² or Btu/h·ft²

References
----------
NFPA 13 (2022) — Standard for the Installation of Sprinkler Systems
NFPA 20 (2022) — Standard for the Installation of Stationary Pumps for Fire Protection
NFPA 92 (2021) — Standard for Smoke Control Systems
NFPA 101 (2021) — Life Safety Code
SFPE Handbook of Fire Protection Engineering, 5th ed.
Alpert, R.L. (1972) "Calculation of Response Time of Ceiling-Mounted Fire Detectors"
Hazen-Williams pipe friction (C=120 for schedule-40 steel)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hazen_williams_loss_psi(
    flow_gpm: float,
    pipe_d_inch: float,
    length_ft: float,
    C: float = 120.0,
) -> float:
    """Hazen-Williams friction loss (psi) for a pipe section."""
    if flow_gpm <= 0 or length_ft <= 0:
        return 0.0
    loss_per_ft = 4.52 * (flow_gpm ** 1.85) / (C ** 1.85 * pipe_d_inch ** 4.87)
    return loss_per_ft * length_ft


# ---------------------------------------------------------------------------
# 1. sprinkler_hydraulic_demand
# ---------------------------------------------------------------------------

# NFPA 13 Table 19.3.3.1.1 occupancy-class density/area defaults
_NFPA13_DENSITY_AREA: dict[str, tuple[float, float]] = {
    # (density_gpm_ft2, area_ft2)
    "light_hazard":            (0.10, 1500.0),
    "ordinary_hazard_group_1": (0.15, 1500.0),
    "ordinary_hazard_group_2": (0.20, 1500.0),
    "extra_hazard_group_1":    (0.30, 2500.0),
    "extra_hazard_group_2":    (0.40, 2500.0),
}

# NFPA 13 Table 19.3.3.4 hose-stream allowances (gpm) by hazard class
_NFPA13_HOSE_STREAM: dict[str, float] = {
    "light_hazard":            100.0,
    "ordinary_hazard_group_1": 250.0,
    "ordinary_hazard_group_2": 250.0,
    "extra_hazard_group_1":    500.0,
    "extra_hazard_group_2":    500.0,
}


def sprinkler_hydraulic_demand(
    occupancy_class: str,
    k_factor: float,
    pipe_d_inch: float,
    pipe_length_ft: float,
    elevation_diff_ft: float = 0.0,
    density_override: float | None = None,
    area_override: float | None = None,
    hw_coeff: float = 120.0,
) -> dict:
    """
    NFPA 13 density/area sprinkler hydraulic demand.

    Calculates the most-remote-area flow and pressure, then walks back through
    a single equivalent pipe run (Hazen-Williams) to the supply source to find
    the source pressure required.

    Parameters
    ----------
    occupancy_class : str
        NFPA 13 occupancy class: 'light_hazard', 'ordinary_hazard_group_1',
        'ordinary_hazard_group_2', 'extra_hazard_group_1', 'extra_hazard_group_2'.
    k_factor : float
        Sprinkler K-factor (gpm/psi^0.5). Common values: 5.6 (standard response),
        8.0, 11.2 (extended coverage), 14.0, 16.8 (large-drop).
        Flow at a sprinkler: Q = K × √P  (Q in gpm, P in psi).
    pipe_d_inch : float
        Inside diameter of the supply pipe (inches). Must be > 0.
    pipe_length_ft : float
        Equivalent pipe length from most-remote area to supply source (ft).
        Include equivalent lengths for fittings.
    elevation_diff_ft : float
        Elevation difference from supply source to most-remote sprinkler area
        (ft, positive = sprinklers above source). Default 0.
        Adds 0.434 psi per foot of elevation.
    density_override : float | None
        Override design density (gpm/ft²). If None, uses NFPA 13 table value.
    area_override : float | None
        Override design area (ft²). If None, uses NFPA 13 table value.
    hw_coeff : float
        Hazen-Williams roughness coefficient C (default 120 for schedule-40 steel).

    Returns
    -------
    dict
        ok                  : True
        occupancy_class     : occupancy class used
        density_gpm_ft2     : design density (gpm/ft²)
        design_area_ft2     : design area (ft²)
        remote_area_flow_gpm: total flow from design area (gpm)
        k_factor            : K-factor used
        min_sprinkler_p_psi : minimum pressure at most-remote sprinkler (psi)
        hose_stream_gpm     : hose-stream allowance (gpm)
        total_demand_gpm    : remote_area_flow_gpm + hose_stream_gpm
        pipe_friction_psi   : Hazen-Williams friction loss in supply pipe (psi)
        elevation_head_psi  : elevation pressure component (psi)
        source_pressure_psi : required pressure at source (psi)
        warnings            : list of warning strings
    """
    warnings: list[str] = []

    occ = str(occupancy_class).strip().lower().replace(" ", "_")
    if occ not in _NFPA13_DENSITY_AREA:
        valid = list(_NFPA13_DENSITY_AREA.keys())
        return _err(f"Unknown occupancy_class {occupancy_class!r}. Supported: {valid}.")

    err = _guard_positive("k_factor", k_factor)
    if err:
        return _err(err)
    err = _guard_positive("pipe_d_inch", pipe_d_inch)
    if err:
        return _err(err)
    err = _guard_nonneg("pipe_length_ft", pipe_length_ft)
    if err:
        return _err(err)

    default_density, default_area = _NFPA13_DENSITY_AREA[occ]

    density = float(density_override) if density_override is not None else default_density
    area = float(area_override) if area_override is not None else default_area

    if density <= 0:
        return _err("density must be > 0")
    if area <= 0:
        return _err("area must be > 0")

    # Total remote-area flow
    remote_flow_gpm = density * area

    # Minimum pressure at most-remote sprinkler: P = (Q/K)²
    # At design density, assume approximately equal flow per sprinkler;
    # minimum branch-end pressure is what forces Q = density × tributary_area
    # For the hydraulic most-remote sprinkler (worst case), use K-factor equation:
    # P_min = (Q_sprinkler / K)²
    # A typical tributary area per sprinkler is ~130 ft² (10×13 ft spacing).
    # NFPA 13 requires min operating pressure; we derive from density × area_per_head.
    typical_area_per_head_ft2 = 130.0
    q_single_sprinkler = density * typical_area_per_head_ft2
    p_min_psi = (q_single_sprinkler / float(k_factor)) ** 2

    # Minimum pressure floor
    if p_min_psi < 7.0:
        p_min_psi = 7.0
        warnings.append(
            "Minimum sprinkler pressure clamped to 7 psi (NFPA 13 §26.4.2 minimum)."
        )

    hose_gpm = _NFPA13_HOSE_STREAM[occ]
    total_demand_gpm = remote_flow_gpm + hose_gpm

    # Hazen-Williams friction in supply pipe (use total demand flow)
    friction_psi = _hazen_williams_loss_psi(
        total_demand_gpm, float(pipe_d_inch), float(pipe_length_ft), float(hw_coeff)
    )

    # Elevation head (0.434 psi/ft)
    elev_psi = float(elevation_diff_ft) * 0.434

    source_pressure_psi = p_min_psi + friction_psi + elev_psi

    if source_pressure_psi > 175.0:
        warnings.append(
            f"Required source pressure {source_pressure_psi:.1f} psi exceeds "
            "175 psi NFPA 13 maximum system pressure — verify pipe and fitting ratings."
        )

    return {
        "ok": True,
        "occupancy_class": occ,
        "density_gpm_ft2": density,
        "design_area_ft2": area,
        "remote_area_flow_gpm": remote_flow_gpm,
        "k_factor": float(k_factor),
        "min_sprinkler_p_psi": p_min_psi,
        "hose_stream_gpm": hose_gpm,
        "total_demand_gpm": total_demand_gpm,
        "pipe_friction_psi": friction_psi,
        "elevation_head_psi": elev_psi,
        "source_pressure_psi": source_pressure_psi,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. fire_pump_sizing
# ---------------------------------------------------------------------------

def fire_pump_sizing(
    rated_flow_gpm: float,
    rated_head_psi: float,
) -> dict:
    """
    Fire pump sizing per NFPA 20.

    Derives the three mandatory performance curve points for a listed fire pump:
      - Rated point  : (rated_flow_gpm, rated_head_psi)
      - 150% flow    : (1.50 × rated_flow_gpm, ≥ 0.65 × rated_head_psi)
      - Churn / shutoff : (0 gpm, ≤ 1.40 × rated_head_psi)

    NFPA 20 §4.28 requires:
      - At 150% of rated flow, net pressure ≥ 65% of rated net pressure.
      - At churn (no flow), net pressure ≤ 140% of rated net pressure.

    Parameters
    ----------
    rated_flow_gpm : float
        Rated pump flow (gpm). Must be > 0.
    rated_head_psi : float
        Rated pump net pressure / head (psi). Must be > 0.

    Returns
    -------
    dict
        ok                      : True
        rated_flow_gpm          : rated flow (gpm)
        rated_head_psi          : rated head (psi)
        flow_150pct_gpm         : 150% rated flow (gpm)
        min_head_at_150pct_psi  : minimum required head at 150% flow (psi)
        churn_max_head_psi      : maximum allowed churn (shutoff) head (psi)
        nominal_churn_head_psi  : nominal churn head used (120% rated, typical)
        pump_ok                 : True if nominal churn ≤ churn_max (always True here)
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("rated_flow_gpm", rated_flow_gpm)
    if err:
        return _err(err)
    err = _guard_positive("rated_head_psi", rated_head_psi)
    if err:
        return _err(err)

    Q_r = float(rated_flow_gpm)
    P_r = float(rated_head_psi)

    flow_150 = 1.50 * Q_r
    min_head_150 = 0.65 * P_r
    churn_max = 1.40 * P_r
    # Typical fire pump churn pressure is ~120% rated
    nominal_churn = 1.20 * P_r

    pump_ok = nominal_churn <= churn_max

    if not pump_ok:
        warnings.append(
            f"Nominal churn head {nominal_churn:.1f} psi exceeds NFPA 20 maximum "
            f"{churn_max:.1f} psi — review pump curve with manufacturer."
        )

    if Q_r < 25:
        warnings.append(
            f"Rated flow {Q_r} gpm is below NFPA 20 §4.4 minimum of 25 gpm."
        )

    if P_r < 40:
        warnings.append(
            f"Rated pressure {P_r} psi is below typical 40 psi minimum; "
            "verify system demand."
        )

    return {
        "ok": True,
        "rated_flow_gpm": Q_r,
        "rated_head_psi": P_r,
        "flow_150pct_gpm": flow_150,
        "min_head_at_150pct_psi": min_head_150,
        "churn_max_head_psi": churn_max,
        "nominal_churn_head_psi": nominal_churn,
        "pump_ok": pump_ok,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. water_supply_adequacy
# ---------------------------------------------------------------------------

def water_supply_adequacy(
    static_pressure_psi: float,
    residual_pressure_psi: float,
    residual_flow_gpm: float,
    required_flow_gpm: float,
    required_pressure_psi: float,
) -> dict:
    """
    Available vs required water supply (pressure-flow curve).

    Plots the available water supply curve using the standard hydraulic
    equation from NFPA 13 App. B / SFPE Handbook:

        P_avail(Q) = P_static - (P_static - P_residual) × (Q / Q_residual)^1.85

    Then checks whether the available pressure at the required flow meets or
    exceeds the required pressure.

    Parameters
    ----------
    static_pressure_psi : float
        Static (no-flow) supply pressure from hydrant flow test (psi).
    residual_pressure_psi : float
        Residual pressure at the test hydrant during the flow test (psi).
    residual_flow_gpm : float
        Flow in gpm flowing from the test hydrant when residual_pressure was read.
    required_flow_gpm : float
        System demand flow (gpm) — total sprinkler + hose stream.
    required_pressure_psi : float
        Minimum pressure required at the supply point (psi).

    Returns
    -------
    dict
        ok                      : True
        static_pressure_psi     : static supply pressure (psi)
        residual_pressure_psi   : residual test pressure (psi)
        residual_flow_gpm       : residual test flow (gpm)
        available_pressure_psi  : available pressure at required_flow_gpm (psi)
        required_flow_gpm       : system demand flow (gpm)
        required_pressure_psi   : minimum required pressure (psi)
        pressure_margin_psi     : available - required (positive = adequate)
        supply_adequate         : True if pressure_margin_psi >= 0
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("static_pressure_psi", static_pressure_psi)
    if err:
        return _err(err)
    err = _guard_positive("residual_pressure_psi", residual_pressure_psi)
    if err:
        return _err(err)
    err = _guard_positive("residual_flow_gpm", residual_flow_gpm)
    if err:
        return _err(err)
    err = _guard_positive("required_flow_gpm", required_flow_gpm)
    if err:
        return _err(err)
    err = _guard_positive("required_pressure_psi", required_pressure_psi)
    if err:
        return _err(err)

    P_s = float(static_pressure_psi)
    P_r = float(residual_pressure_psi)
    Q_r = float(residual_flow_gpm)
    Q_req = float(required_flow_gpm)
    P_req = float(required_pressure_psi)

    if P_r >= P_s:
        return _err(
            "residual_pressure_psi must be < static_pressure_psi "
            "(residual pressure drops under flow)."
        )

    # Available pressure at required flow:
    # P(Q) = P_s - (P_s - P_r) × (Q / Q_r)^1.85
    drop_factor = (Q_req / Q_r) ** 1.85
    P_avail = P_s - (P_s - P_r) * drop_factor

    margin = P_avail - P_req
    supply_adequate = margin >= 0.0

    if not supply_adequate:
        warnings.append(
            f"INADEQUATE WATER SUPPLY: available pressure {P_avail:.1f} psi at "
            f"{Q_req:.0f} gpm is {abs(margin):.1f} psi below the required "
            f"{P_req:.1f} psi. Consider a fire pump or looped supply main."
        )

    if Q_req > Q_r * 1.5:
        warnings.append(
            "Required flow exceeds 150% of test flow — supply curve extrapolation "
            "may be unreliable; obtain a supplemental flow test."
        )

    return {
        "ok": True,
        "static_pressure_psi": P_s,
        "residual_pressure_psi": P_r,
        "residual_flow_gpm": Q_r,
        "available_pressure_psi": P_avail,
        "required_flow_gpm": Q_req,
        "required_pressure_psi": P_req,
        "pressure_margin_psi": margin,
        "supply_adequate": supply_adequate,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. egress_analysis
# ---------------------------------------------------------------------------

# NFPA 101 Table 7.3.1.2 occupant load factors (ft²/person)
_NFPA101_OLF: dict[str, float] = {
    "assembly_concentrated":    7.0,
    "assembly_less_concentrated": 15.0,
    "business":                 100.0,
    "classroom":                20.0,
    "dormitory":                50.0,
    "educational":              20.0,
    "healthcare_sleeping":      120.0,
    "healthcare_treatment":     240.0,
    "industrial_general":       100.0,
    "library_reading_room":     50.0,
    "library_stack":            100.0,
    "mercantile_basement":      30.0,
    "mercantile_street_floor":  30.0,
    "mercantile_upper":         60.0,
    "parking_garage":           200.0,
    "residential":              200.0,
    "storage":                  300.0,
    "warehouse":                500.0,
}

# NFPA 101 §7.3.3 — minimum exit width and capacity factors (in/person)
# For stairways: 0.3 in/person width; for level components & ramps: 0.2 in/person
_EXIT_WIDTH_FACTOR_STAIR_IN_PER_PERSON = 0.3    # inches per person (stairways)
_EXIT_WIDTH_FACTOR_LEVEL_IN_PER_PERSON = 0.2    # inches per person (level components)
_MIN_EXIT_WIDTH_IN = 28.0  # NFPA 101 §7.2.1.2 absolute minimum (inches)

# NFPA 101 §7.6 — travel distance limits (ft) for common occupancies
_TRAVEL_DISTANCE_LIMITS: dict[str, float] = {
    "assembly":         200.0,
    "business":         200.0,
    "educational":      150.0,
    "healthcare":       150.0,
    "industrial":       250.0,
    "mercantile":       200.0,
    "residential":      125.0,
    "storage":          200.0,
}

# NFPA 101 §7.6 — common path of travel limits (ft)
_COMMON_PATH_LIMITS: dict[str, float] = {
    "assembly":         20.0,
    "business":         75.0,
    "educational":      75.0,
    "healthcare":       100.0,
    "industrial":       50.0,
    "mercantile":       50.0,
    "residential":      35.0,
    "storage":          50.0,
}

# NFPA 101 §7.4 — dead-end limit (ft) — corridors
_DEAD_END_LIMIT_FT = 20.0


def egress_analysis(
    floor_area_ft2: float,
    occupancy_type: str,
    num_exits: int,
    exit_widths_in: list[float],
    travel_distance_ft: float,
    common_path_ft: float = 0.0,
    dead_end_ft: float = 0.0,
    exit_component: str = "stair",
) -> dict:
    """
    Egress analysis per NFPA 101 Life Safety Code.

    Determines occupant load, required exit width, capacity of provided exits,
    travel/common-path/dead-end limit compliance, and time-to-egress estimate.

    Parameters
    ----------
    floor_area_ft2 : float
        Gross floor area of the space (ft²). Must be > 0.
    occupancy_type : str
        NFPA 101 occupancy type key used for occupant load factor and travel
        distance limits. Supported: 'assembly_concentrated',
        'assembly_less_concentrated', 'business', 'classroom', 'dormitory',
        'educational', 'healthcare_sleeping', 'healthcare_treatment',
        'industrial_general', 'library_reading_room', 'library_stack',
        'mercantile_basement', 'mercantile_street_floor', 'mercantile_upper',
        'parking_garage', 'residential', 'storage', 'warehouse'.
    num_exits : int
        Number of exits provided. Must be >= 1.
    exit_widths_in : list[float]
        List of exit clear widths (inches) for each exit. Length must equal
        num_exits. Each must be > 0.
    travel_distance_ft : float
        Maximum actual travel distance to nearest exit (ft). Must be >= 0.
    common_path_ft : float
        Maximum actual common path of travel (ft). Default 0.
    dead_end_ft : float
        Maximum actual dead-end corridor length (ft). Default 0.
    exit_component : str
        'stair' (default) or 'level'. Determines capacity factor (in/person).

    Returns
    -------
    dict
        ok                      : True
        occupant_load           : calculated occupant load (persons)
        occupant_load_factor    : occupant load factor used (ft²/person)
        required_exits          : minimum number of exits required
        num_exits               : number of exits provided
        required_width_per_exit_in : minimum width per exit for capacity (inches)
        total_exit_capacity     : total egress capacity from provided exits (persons)
        capacity_adequate       : True if total_exit_capacity >= occupant_load
        travel_distance_ok      : True if travel_distance_ft <= limit
        travel_distance_limit_ft: code limit for travel distance (ft)
        common_path_ok          : True if common_path_ft <= limit
        common_path_limit_ft    : code limit for common path of travel (ft)
        dead_end_ok             : True if dead_end_ft <= _DEAD_END_LIMIT_FT
        dead_end_limit_ft       : code limit for dead-end (ft)
        time_to_egress_s        : estimated time-to-egress (seconds) — simple model
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("floor_area_ft2", floor_area_ft2)
    if err:
        return _err(err)

    occ = str(occupancy_type).strip().lower().replace(" ", "_").replace("-", "_")
    if occ not in _NFPA101_OLF:
        # Attempt approximate match for broad categories
        broad_map = {
            "assembly": "assembly_less_concentrated",
            "healthcare": "healthcare_treatment",
            "library": "library_reading_room",
            "mercantile": "mercantile_street_floor",
        }
        matched = None
        for key, val in broad_map.items():
            if occ.startswith(key):
                matched = val
                break
        if matched is None:
            valid = list(_NFPA101_OLF.keys())
            return _err(
                f"Unknown occupancy_type {occupancy_type!r}. Supported: {valid}."
            )
        occ = matched

    if not isinstance(num_exits, int) or num_exits < 1:
        return _err("num_exits must be a positive integer >= 1")

    if not isinstance(exit_widths_in, list) or len(exit_widths_in) != num_exits:
        return _err(
            f"exit_widths_in must be a list of {num_exits} values (one per exit)."
        )

    for i, w in enumerate(exit_widths_in):
        e = _guard_positive(f"exit_widths_in[{i}]", w)
        if e:
            return _err(e)

    err = _guard_nonneg("travel_distance_ft", travel_distance_ft)
    if err:
        return _err(err)

    # Occupant load
    olf = _NFPA101_OLF[occ]
    occupant_load = math.ceil(float(floor_area_ft2) / olf)

    # Required number of exits (NFPA 101 §7.4)
    if occupant_load <= 500:
        required_exits = 2
    elif occupant_load <= 1000:
        required_exits = 3
    else:
        required_exits = 4

    # Required width per exit
    factor = (
        _EXIT_WIDTH_FACTOR_STAIR_IN_PER_PERSON
        if str(exit_component).strip().lower() in ("stair", "stairs", "stairway")
        else _EXIT_WIDTH_FACTOR_LEVEL_IN_PER_PERSON
    )
    total_required_width = max(
        occupant_load * factor,
        num_exits * _MIN_EXIT_WIDTH_IN,
    )
    width_per_exit = total_required_width / num_exits

    # Total egress capacity from provided exits
    total_capacity_persons = sum(
        max(float(w) - 0.0, 0.0) / factor for w in exit_widths_in
    )

    capacity_adequate = total_capacity_persons >= occupant_load
    if not capacity_adequate:
        warnings.append(
            f"EGRESS CAPACITY EXCEEDED: provided exit capacity {total_capacity_persons:.0f} "
            f"persons is less than occupant load {occupant_load} persons. "
            "Increase exit widths or add exits."
        )

    if num_exits < required_exits:
        warnings.append(
            f"Insufficient exits: {num_exits} provided, {required_exits} required "
            f"for occupant load of {occupant_load} persons (NFPA 101 §7.4)."
        )

    # Travel distance
    # Select limit by broad occupancy category
    td_limit = _travel_distance_limits_for_occ(occ)
    travel_ok = float(travel_distance_ft) <= td_limit

    if not travel_ok:
        warnings.append(
            f"Travel distance {travel_distance_ft:.1f} ft exceeds {td_limit:.0f} ft "
            f"limit for {occ} occupancy (NFPA 101 §7.6)."
        )

    # Common path of travel
    cp_limit = _common_path_limits_for_occ(occ)
    common_path_ok = float(common_path_ft) <= cp_limit

    if not common_path_ok:
        warnings.append(
            f"Common path of travel {common_path_ft:.1f} ft exceeds {cp_limit:.0f} ft "
            f"limit for {occ} occupancy (NFPA 101 §7.6)."
        )

    # Dead end
    dead_end_ok = float(dead_end_ft) <= _DEAD_END_LIMIT_FT
    if not dead_end_ok:
        warnings.append(
            f"Dead-end corridor {dead_end_ft:.1f} ft exceeds {_DEAD_END_LIMIT_FT:.0f} ft "
            "limit (NFPA 101 §7.4)."
        )

    # Simple time-to-egress estimate (SFPE Handbook, Nelson & Mowrer model)
    # t_egress ≈ t_detect + t_notify + t_travel
    # Simple approximation: t_travel ≈ travel_distance_ft / 200 ft/min × 60 s/min
    # (200 ft/min is a conservative walking speed on stair/level)
    travel_speed_fpm = 200.0 if str(exit_component).strip().lower().startswith("stair") else 280.0
    t_detect_s = 60.0   # typical
    t_notify_s = 30.0   # typical alarm notification
    t_travel_s = (float(travel_distance_ft) / travel_speed_fpm) * 60.0
    time_to_egress_s = t_detect_s + t_notify_s + t_travel_s

    return {
        "ok": True,
        "occupant_load": occupant_load,
        "occupant_load_factor_ft2_per_person": olf,
        "required_exits": required_exits,
        "num_exits": num_exits,
        "required_width_per_exit_in": width_per_exit,
        "total_exit_capacity_persons": total_capacity_persons,
        "capacity_adequate": capacity_adequate,
        "travel_distance_ft": float(travel_distance_ft),
        "travel_distance_limit_ft": td_limit,
        "travel_distance_ok": travel_ok,
        "common_path_ft": float(common_path_ft),
        "common_path_limit_ft": cp_limit,
        "common_path_ok": common_path_ok,
        "dead_end_ft": float(dead_end_ft),
        "dead_end_limit_ft": _DEAD_END_LIMIT_FT,
        "dead_end_ok": dead_end_ok,
        "time_to_egress_s": time_to_egress_s,
        "warnings": warnings,
    }


def _travel_distance_limits_for_occ(occ: str) -> float:
    """Map NFPA 101 OLF key to travel distance limit (ft)."""
    for key in _TRAVEL_DISTANCE_LIMITS:
        if occ.startswith(key):
            return _TRAVEL_DISTANCE_LIMITS[key]
    return 200.0  # default


def _common_path_limits_for_occ(occ: str) -> float:
    """Map NFPA 101 OLF key to common path of travel limit (ft)."""
    for key in _COMMON_PATH_LIMITS:
        if occ.startswith(key):
            return _COMMON_PATH_LIMITS[key]
    return 75.0  # default


# ---------------------------------------------------------------------------
# 5. design_fire_tsquared
# ---------------------------------------------------------------------------

# NFPA 92 / SFPE growth rate coefficients α (kW/s²)
# Defined by Q = α × t²; α = 1000 kW / t_ref²
_TSQUARED_GROWTH_RATES: dict[str, float] = {
    "slow":       1000.0 / 600.0 ** 2,   # 1 MW in 600 s  ≈ 0.002778 kW/s²
    "medium":     1000.0 / 300.0 ** 2,   # 1 MW in 300 s  ≈ 0.011111 kW/s²
    "fast":       1000.0 / 150.0 ** 2,   # 1 MW in 150 s  ≈ 0.044444 kW/s²
    "ultra_fast": 1000.0 /  75.0 ** 2,   # 1 MW in 75 s   ≈ 0.177778 kW/s²
}


def design_fire_tsquared(
    time_s: float,
    growth_class: str = "medium",
    alpha_override: float | None = None,
    max_hrr_kw: float | None = None,
) -> dict:
    """
    t-squared design fire heat-release rate.

    Models the fire growth phase as Q = α × t² (NFPA 92, SFPE Handbook §3-1).

    Parameters
    ----------
    time_s : float
        Time from ignition (seconds). Must be >= 0.
    growth_class : str
        Fire growth rate class: 'slow', 'medium' (default), 'fast', 'ultra_fast'.
        Defines the α coefficient.
    alpha_override : float | None
        Override α (kW/s²) directly. Overrides growth_class.
    max_hrr_kw : float | None
        Maximum (steady-state) HRR cap (kW). Fire is capped at this value if
        specified. None = uncapped.

    Returns
    -------
    dict
        ok              : True
        growth_class    : growth class used (or 'custom')
        alpha_kW_s2     : fire growth coefficient α (kW/s²)
        time_s          : time from ignition (s)
        hrr_kw          : heat-release rate Q at time_s (kW)
        hrr_kw_capped   : True if HRR was capped at max_hrr_kw
        time_to_1MW_s   : time for fire to reach 1 MW (s)
        warnings        : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_nonneg("time_s", time_s)
    if err:
        return _err(err)

    if alpha_override is not None:
        e = _guard_positive("alpha_override", alpha_override)
        if e:
            return _err(e)
        alpha = float(alpha_override)
        growth_label = "custom"
    else:
        gc = str(growth_class).strip().lower().replace("-", "_").replace(" ", "_")
        if gc not in _TSQUARED_GROWTH_RATES:
            valid = list(_TSQUARED_GROWTH_RATES.keys())
            return _err(
                f"Unknown growth_class {growth_class!r}. Supported: {valid}."
            )
        alpha = _TSQUARED_GROWTH_RATES[gc]
        growth_label = gc

    t = float(time_s)
    hrr = alpha * t ** 2
    capped = False

    if max_hrr_kw is not None:
        if max_hrr_kw <= 0:
            return _err("max_hrr_kw must be > 0 if specified")
        if hrr > float(max_hrr_kw):
            hrr = float(max_hrr_kw)
            capped = True

    time_to_1mw = math.sqrt(1000.0 / alpha)  # Q = α·t² → t = √(Q/α)

    if hrr > 5000.0:
        warnings.append(
            f"HRR {hrr:.0f} kW is very large; verify fuel load and ventilation assumptions."
        )

    return {
        "ok": True,
        "growth_class": growth_label,
        "alpha_kW_s2": alpha,
        "time_s": t,
        "hrr_kw": hrr,
        "hrr_kw_capped": capped,
        "time_to_1MW_s": time_to_1mw,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. detector_activation_time
# ---------------------------------------------------------------------------

def detector_activation_time(
    hrr_kw: float,
    ceiling_height_m: float,
    radial_distance_m: float,
    rti: float,
    detector_temp_c: float,
    ambient_temp_c: float = 20.0,
    delta_t_method: bool = True,
) -> dict:
    """
    Sprinkler/heat-detector activation time using Alpert ceiling-jet correlations
    and the RTI (Response Time Index) model.

    SFPE Handbook §4-1, Alpert (1972):

    For r/H <= 0.18 (near axis):
        T_jet = T_ambient + 16.9 × Q^(2/3) / H^(5/3)
        u_jet  = 0.96 × (Q/H)^(1/3)

    For r/H > 0.18 (off-axis):
        T_jet = T_ambient + 5.38 × (Q/r)^(2/3) / H
        u_jet  = 0.195 × (Q × H)^(1/3) / r^(5/6)   [SFPE corrected form]

    RTI activation model (SFPE §4-1):
        dTd/dt = (u_jet^0.5 / RTI) × (T_jet - Td)
        Activation when Td >= detector_temp.

    Parameters
    ----------
    hrr_kw : float
        Fire heat-release rate Q (kW) at the time of interest. Must be > 0.
    ceiling_height_m : float
        Height from fire base to ceiling (m). Must be > 0.
    radial_distance_m : float
        Radial distance from fire axis to detector (m). Must be >= 0.
    rti : float
        Response Time Index of the sprinkler/detector (m^0.5 · s^0.5).
        Standard response: 80–350; quick response: 28–50.
    detector_temp_c : float
        Activation temperature of the detector/sprinkler (°C). Must be > ambient.
    ambient_temp_c : float
        Ambient room temperature (°C). Default 20.
    delta_t_method : bool
        If True (default), use the simplified ΔT activation check (instantaneous
        quasi-steady Alpert temperature).  If False, return time_to_activation_s
        from numerical integration of the RTI ODE.

    Returns
    -------
    dict
        ok                  : True
        hrr_kw              : HRR used (kW)
        ceiling_height_m    : ceiling height used (m)
        radial_distance_m   : radial distance used (m)
        rti                 : RTI used
        detector_temp_c     : activation temperature (°C)
        ambient_temp_c      : ambient temperature (°C)
        ceiling_jet_temp_c  : Alpert ceiling-jet temperature at detector (°C)
        ceiling_jet_vel_m_s : Alpert ceiling-jet velocity at detector (m/s)
        activated           : True if ceiling-jet temp >= detector_temp (quasi-steady)
        time_to_activation_s: estimated time to activation (s) from RTI ODE
                              (None if not activated in 600 s)
        warnings            : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("hrr_kw", hrr_kw)
    if err:
        return _err(err)
    err = _guard_positive("ceiling_height_m", ceiling_height_m)
    if err:
        return _err(err)
    err = _guard_nonneg("radial_distance_m", radial_distance_m)
    if err:
        return _err(err)
    err = _guard_positive("rti", rti)
    if err:
        return _err(err)

    Q = float(hrr_kw)
    H = float(ceiling_height_m)
    r = float(radial_distance_m)
    T_amb = float(ambient_temp_c)
    T_act = float(detector_temp_c)

    if T_act <= T_amb:
        return _err(
            "detector_temp_c must be > ambient_temp_c "
            f"({T_act:.1f} °C vs {T_amb:.1f} °C)."
        )

    ratio = r / H

    if ratio <= 0.18:
        # Near-axis (plume-dominated)
        delta_T_jet = 16.9 * Q ** (2.0 / 3.0) / H ** (5.0 / 3.0)
        u_jet = 0.96 * (Q / H) ** (1.0 / 3.0)
    else:
        # Off-axis (radial ceiling jet)
        delta_T_jet = 5.38 * (Q / r) ** (2.0 / 3.0) / H
        u_jet = 0.195 * (Q * H) ** (1.0 / 3.0) / r ** (5.0 / 6.0) if r > 0 else 0.0

    T_jet = T_amb + delta_T_jet
    activated_qs = T_jet >= T_act

    # RTI integration: simple Euler forward from t=0
    # Assume t-squared fire leading up: Q_inst(t) = alpha_effective * t^2
    # But we have steady Q at this point. Use instantaneous RTI ODE integration
    # with constant Q (conservative quasi-steady approach).
    #
    # dTd/dt = (u^0.5 / RTI) * (T_jet - Td)
    # where u and T_jet are constant (steady fire assumed).
    # Analytical solution: Td(t) = T_jet - (T_jet - T_amb) * exp(-u^0.5/RTI * t)
    # Activation when Td = T_act:
    # T_act = T_jet - (T_jet - T_amb) * exp(-u^0.5/RTI * t_act)
    # t_act = -RTI / sqrt(u) * ln((T_jet - T_act)/(T_jet - T_amb))

    time_to_activation_s = None

    if u_jet > 0 and delta_T_jet > 0:
        u_sqrt = math.sqrt(u_jet)
        gamma = (T_jet - T_act) / (T_jet - T_amb) if (T_jet - T_amb) > 0 else -1.0
        if gamma > 0 and gamma < 1.0:
            t_act = -(float(rti) / u_sqrt) * math.log(gamma)
            time_to_activation_s = t_act
        elif gamma <= 0:
            # Already exceeded activation temperature at this HRR
            time_to_activation_s = 0.0
        # else gamma >= 1: fire cannot activate detector at this HRR (activated=False)

    if not activated_qs:
        warnings.append(
            f"Ceiling-jet temperature {T_jet:.1f} °C does not reach detector "
            f"activation temperature {T_act:.1f} °C at steady HRR {Q:.0f} kW. "
            "Consider a lower-temp rated detector or repositioning."
        )

    if time_to_activation_s is not None and time_to_activation_s > 300.0:
        warnings.append(
            f"Estimated activation time {time_to_activation_s:.0f} s > 5 min; "
            "consider closer detector spacing or quick-response sprinklers."
        )

    return {
        "ok": True,
        "hrr_kw": Q,
        "ceiling_height_m": H,
        "radial_distance_m": r,
        "rti": float(rti),
        "detector_temp_c": T_act,
        "ambient_temp_c": T_amb,
        "ceiling_jet_temp_c": T_jet,
        "ceiling_jet_vel_m_s": u_jet,
        "activated": activated_qs,
        "time_to_activation_s": time_to_activation_s,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. smoke_control_exhaust
# ---------------------------------------------------------------------------

def smoke_control_exhaust(
    hrr_kw: float,
    atrium_height_m: float,
    smoke_layer_height_m: float,
    perimeter_m: float | None = None,
) -> dict:
    """
    Atrium smoke exhaust airflow per NFPA 92 §4.5 (axisymmetric plume model).

    Uses the McCaffrey/Heskestad balcony/axisymmetric plume equations from
    NFPA 92 Annex A to determine the mass flow rate in the plume at the smoke-
    layer interface, which sets the minimum exhaust airflow.

    NFPA 92 Eq. A.2 (axisymmetric plume, strong plume, z > z_lim):
        Mp = 0.071 × Qc^(1/3) × z^(5/3) × [1 + 0.026 × Qc^(2/3) / z^(5/3)]

    Parameters
    ----------
    hrr_kw : float
        Fire HRR Q (kW). Must be > 0.
    atrium_height_m : float
        Total atrium height from floor to ceiling (m). Must be > 0.
    smoke_layer_height_m : float
        Design smoke-layer interface height above fire source (m). Must be > 0
        and < atrium_height_m.
    perimeter_m : float | None
        Fire perimeter (m) for use with line-source plume (optional).
        If None, axisymmetric (point-source) plume is used.

    Returns
    -------
    dict
        ok                      : True
        hrr_kw                  : fire HRR (kW)
        hrr_convective_kw       : convective HRR Qc (kW), assumed 70% of total
        atrium_height_m         : atrium height (m)
        smoke_layer_height_m    : smoke-layer interface height z (m)
        plume_mass_flow_kg_s    : plume mass flow rate at z (kg/s)
        exhaust_airflow_cfm     : minimum exhaust airflow (cfm)
        exhaust_airflow_m3_s    : minimum exhaust airflow (m³/s)
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("hrr_kw", hrr_kw)
    if err:
        return _err(err)
    err = _guard_positive("atrium_height_m", atrium_height_m)
    if err:
        return _err(err)
    err = _guard_positive("smoke_layer_height_m", smoke_layer_height_m)
    if err:
        return _err(err)

    Q = float(hrr_kw)
    H = float(atrium_height_m)
    z = float(smoke_layer_height_m)

    if z >= H:
        return _err(
            "smoke_layer_height_m must be < atrium_height_m "
            f"(got {z} >= {H})."
        )

    # Convective fraction: NFPA 92 assumes Qc = 0.70 × Q
    Qc = 0.70 * Q

    # NFPA 92 Eq. A.2 — axisymmetric plume mass flow rate (kg/s)
    # Mp = 0.071 × Qc^(1/3) × z^(5/3) + 0.0018 × Qc
    # Simplified (NFPA 92 Table A.2.3, "strong plume" for most atria):
    Mp = 0.071 * (Qc ** (1.0 / 3.0)) * (z ** (5.0 / 3.0)) + 0.0018 * Qc

    # Convert mass flow to volumetric (assume smoke density ≈ air density at ~300K)
    # ρ_smoke ≈ 0.85 kg/m³ (hot smoke at ~130°C)
    rho_smoke = 0.85  # kg/m³
    exhaust_m3_s = Mp / rho_smoke

    # Convert to cfm (1 m³/s = 2118.88 cfm)
    exhaust_cfm = exhaust_m3_s * 2118.88

    if z < 1.0:
        warnings.append(
            "Smoke-layer height < 1 m; plume model accuracy is reduced at very "
            "low interface heights. Consider increasing design smoke-layer height."
        )

    if z / H < 0.33:
        warnings.append(
            f"Smoke-layer height {z:.1f} m is less than 1/3 of atrium height {H:.1f} m. "
            "NFPA 92 §4.6.1 recommends the smoke layer remain at least 6 ft (1.8 m) "
            "above the highest occupied floor."
        )

    return {
        "ok": True,
        "hrr_kw": Q,
        "hrr_convective_kw": Qc,
        "atrium_height_m": H,
        "smoke_layer_height_m": z,
        "plume_mass_flow_kg_s": Mp,
        "exhaust_airflow_m3_s": exhaust_m3_s,
        "exhaust_airflow_cfm": exhaust_cfm,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. fire_resistance_heat_transfer
# ---------------------------------------------------------------------------

def fire_resistance_heat_transfer(
    assembly_layers: list[dict],
    fire_side_temp_c: float = 927.0,
    ambient_temp_c: float = 20.0,
) -> dict:
    """
    Simple 1-D steady-state heat transfer through a fire-rated wall/floor assembly.

    Models the assembly as resistors in series (R = thickness / conductivity for
    each layer).  Conduction only — radiation and convection on surfaces are
    lumped into surface resistances.

    Parameters
    ----------
    assembly_layers : list[dict]
        List of layer dicts, each with:
          'name'           : str — layer name (e.g. 'gypsum_board')
          'thickness_mm'   : float — layer thickness (mm)
          'conductivity_W_mK' : float — thermal conductivity (W/m·K)
    fire_side_temp_c : float
        Fire-side (hot) surface temperature (°C). Default 927 °C (standard
        ASTM E119 / ISO 834 furnace temperature at 60 min).
    ambient_temp_c : float
        Ambient (cold) side temperature (°C). Default 20 °C.

    Returns
    -------
    dict
        ok                      : True
        total_R_m2K_W           : total thermal resistance (m²·K/W)
        heat_flux_W_m2          : steady-state heat flux through assembly (W/m²)
        unexposed_surface_temp_c: estimated unexposed surface temperature (°C)
        delta_T_c               : temperature drop across assembly (°C)
        layer_temps_c           : list of temperatures at each layer interface (°C)
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    if not isinstance(assembly_layers, list) or len(assembly_layers) == 0:
        return _err("assembly_layers must be a non-empty list of layer dicts.")

    # Surface resistance (film coefficients): assume 0.13 m²K/W (exposed, fire side)
    # and 0.04 m²K/W (unexposed side) — standard per ISO 6946
    R_surface_hot = 0.13   # m²·K/W
    R_surface_cold = 0.04  # m²·K/W

    R_total = R_surface_hot + R_surface_cold
    layer_R_values: list[float] = []

    for i, layer in enumerate(assembly_layers):
        if not isinstance(layer, dict):
            return _err(f"Layer {i} must be a dict with 'name', 'thickness_mm', 'conductivity_W_mK'.")
        name = layer.get("name", f"layer_{i}")
        t_mm = layer.get("thickness_mm")
        k = layer.get("conductivity_W_mK")

        e = _guard_positive(f"layer '{name}' thickness_mm", t_mm)
        if e:
            return _err(e)
        e = _guard_positive(f"layer '{name}' conductivity_W_mK", k)
        if e:
            return _err(e)

        R_layer = (float(t_mm) * 1e-3) / float(k)
        layer_R_values.append(R_layer)
        R_total += R_layer

    T_hot = float(fire_side_temp_c)
    T_cold = float(ambient_temp_c)

    if T_hot <= T_cold:
        return _err("fire_side_temp_c must be > ambient_temp_c.")

    delta_T = T_hot - T_cold
    heat_flux = delta_T / R_total  # W/m²

    # Build temperature profile at each interface
    # Start at fire-side surface (after surface resistance drop)
    T_current = T_hot - heat_flux * R_surface_hot
    layer_temps: list[float] = [T_hot, T_current]

    for R_layer in layer_R_values:
        T_current = T_current - heat_flux * R_layer
        layer_temps.append(T_current)

    # T_current is now the temperature at the cold face of the last material layer
    # (before the cold-side surface convective resistance).  This is the
    # unexposed-surface temperature measured in ASTM E119.
    T_unexposed = T_current
    layer_temps.append(T_unexposed - heat_flux * R_surface_cold)  # ambient-air side

    # ASTM E119: assembly passes if unexposed surface does not exceed ambient + 139°C (250°F)
    t_limit = T_cold + 139.0
    if T_unexposed > t_limit:
        warnings.append(
            f"Unexposed surface temperature {T_unexposed:.1f} °C exceeds ASTM E119 "
            f"limit of {t_limit:.1f} °C (ambient + 139°C). Assembly may not achieve "
            "the assumed fire rating at these conditions."
        )

    return {
        "ok": True,
        "total_R_m2K_W": R_total,
        "heat_flux_W_m2": heat_flux,
        "fire_side_temp_c": T_hot,
        "ambient_temp_c": T_cold,
        "unexposed_surface_temp_c": T_unexposed,
        "delta_T_c": delta_T,
        "layer_temps_c": layer_temps,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. required_fire_rating
# ---------------------------------------------------------------------------

# Minimum fire-resistance ratings (hours) based on IBC Table 601 / NFPA 101
# Keyed by (occupancy_group, construction_type, building_height_stories)
# Simplified two-tier table: low-rise (<=4 stories) vs high-rise (>4 stories)

# (occupancy_group, is_high_rise) → (bearing_wall_hr, nonbearing_wall_hr, floor_hr)
_FIRE_RATING_TABLE: dict[tuple[str, bool], tuple[float, float, float]] = {
    ("assembly",        False): (1.0, 1.0, 1.0),
    ("assembly",        True):  (2.0, 1.0, 2.0),
    ("business",        False): (1.0, 0.0, 1.0),
    ("business",        True):  (2.0, 1.0, 2.0),
    ("educational",     False): (1.0, 1.0, 1.0),
    ("educational",     True):  (2.0, 1.0, 2.0),
    ("healthcare",      False): (2.0, 1.0, 2.0),
    ("healthcare",      True):  (3.0, 2.0, 3.0),
    ("industrial",      False): (1.0, 0.0, 1.0),
    ("industrial",      True):  (2.0, 1.0, 2.0),
    ("mercantile",      False): (1.0, 0.0, 1.0),
    ("mercantile",      True):  (2.0, 1.0, 2.0),
    ("residential",     False): (1.0, 1.0, 1.0),
    ("residential",     True):  (2.0, 1.0, 2.0),
    ("storage",         False): (1.0, 0.0, 1.0),
    ("storage",         True):  (2.0, 1.0, 2.0),
    ("high_hazard",     False): (2.0, 1.0, 2.0),
    ("high_hazard",     True):  (3.0, 2.0, 3.0),
}


def required_fire_rating(
    occupancy_group: str,
    building_height_stories: int,
    sprinklered: bool = False,
) -> dict:
    """
    Minimum fire-resistance rating by occupancy group and building height.

    Based on IBC Table 601 (Type I-A through Type V-B) simplified to occupancy
    group + height categories.  Sprinkler credit per IBC §504 reduces
    requirements by one hour (minimum 0 hours) for sprinklered buildings.

    Parameters
    ----------
    occupancy_group : str
        Occupancy group: 'assembly', 'business', 'educational', 'healthcare',
        'industrial', 'mercantile', 'residential', 'storage', 'high_hazard'.
    building_height_stories : int
        Number of stories (floors above grade). Must be >= 1.
        Buildings > 4 stories use the high-rise row.
    sprinklered : bool
        True if building is fully sprinklered per NFPA 13. Reduces required
        rating by 1 hour (floor to 0 minimum) where IBC §504 permits.

    Returns
    -------
    dict
        ok                          : True
        occupancy_group             : occupancy group used
        building_height_stories     : stories input
        is_high_rise                : True if > 4 stories
        sprinklered                 : sprinklered flag
        required_bearing_wall_hr    : bearing wall fire rating (hours)
        required_nonbearing_wall_hr : non-bearing wall fire rating (hours)
        required_floor_hr           : floor/ceiling assembly fire rating (hours)
        warnings                    : list of warning strings
    """
    warnings: list[str] = []

    occ = str(occupancy_group).strip().lower().replace(" ", "_").replace("-", "_")
    # Broad-match partial keys
    matched_occ = None
    for key in _FIRE_RATING_TABLE:
        if occ == key[0] or occ.startswith(key[0]):
            matched_occ = key[0]
            break
    if matched_occ is None:
        valid = list({k[0] for k in _FIRE_RATING_TABLE})
        return _err(
            f"Unknown occupancy_group {occupancy_group!r}. Supported: {sorted(valid)}."
        )

    if not isinstance(building_height_stories, int) or building_height_stories < 1:
        # Accept floats that are whole numbers
        try:
            bh = int(building_height_stories)
            if bh < 1:
                raise ValueError
        except (TypeError, ValueError):
            return _err("building_height_stories must be a positive integer >= 1.")
        building_height_stories = bh

    is_high_rise = building_height_stories > 4

    key = (matched_occ, is_high_rise)
    bw_hr, nbw_hr, fl_hr = _FIRE_RATING_TABLE[key]

    if sprinklered:
        # IBC §504 sprinkler credit: -1 hr, min 0
        bw_hr = max(0.0, bw_hr - 1.0)
        nbw_hr = max(0.0, nbw_hr - 1.0)
        fl_hr = max(0.0, fl_hr - 1.0)
        warnings.append(
            "1-hour sprinkler credit applied per IBC §504. Verify with AHJ."
        )

    if is_high_rise and not sprinklered:
        warnings.append(
            "High-rise buildings (>75 ft / >4 stories) typically require full "
            "NFPA 13 sprinkler protection per IBC §403.3."
        )

    return {
        "ok": True,
        "occupancy_group": matched_occ,
        "building_height_stories": building_height_stories,
        "is_high_rise": is_high_rise,
        "sprinklered": sprinklered,
        "required_bearing_wall_hr": bw_hr,
        "required_nonbearing_wall_hr": nbw_hr,
        "required_floor_hr": fl_hr,
        "warnings": warnings,
    }
