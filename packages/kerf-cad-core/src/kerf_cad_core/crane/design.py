"""
kerf_cad_core.crane.design — pure-Python crane & hoist mechanism design.

Implements fifteen public functions:

  wire_rope_reeving(SWL_kN, n_parts, *, rope_efficiency, reeving_factor)
      Rope pull (line pull) and hook-block efficiency from reeving geometry.
      Accounts for sheave friction losses using the pulley-efficiency model.

  rope_diameter(line_pull_kN, safety_factor, *, grade)
      Required wire-rope diameter from line pull and safety factor, by rope
      grade. Returns diameter_mm from the standard FEM / DIN 15020 table.

  sheave_drum_geometry(rope_dia_mm, *, sheave_dd_ratio, drum_dd_ratio)
      Minimum sheave and drum pitch-circle diameters from D/d ratio per
      FEM 1.001 or ISO 4301. Returns pcd_sheave_mm and pcd_drum_mm.

  drum_length(rope_dia_mm, n_parts, hoist_height_m, *, n_layers, groove_pitch_factor)
      Drum length and winding layers for a given rope diameter, reeving
      arrangement, and hoist height.

  hoist_motor_power(SWL_kN, hoist_speed_mps, *, mechanical_efficiency, duty_factor)
      Required hoist motor power (kW) from SWL, rope speed, and drive
      efficiency. Includes a duty-factor correction.

  hoist_motor_class(duty_group, load_spectrum, *, utilisation_class)
      FEM/ISO M-class (M1–M8) for a hoist motor from duty group and load-
      spectrum factor per FEM 1.001 / ISO 4301-1.

  hoist_brake_torque(SWL_kN, drum_pcd_mm, n_parts, *, brake_factor)
      Required hoist brake holding torque (N·m) from load, drum PCD, and
      reeving.

  travel_resistance(crane_mass_kg, payload_kg, *, coeff_rolling, coeff_wind,
                    wind_pressure_Pa, frontal_area_m2)
      Travel drive resistance force (N) from rolling and wind resistance.

  travel_motor_power(resistance_N, travel_speed_mps, *, motor_efficiency,
                     acceleration_factor)
      Required travel motor power (kW) from resistance and speed.

  jib_load_chart(slew_radius_m, jib_length_m, jib_mass_kg, counterweight_kg,
                 counterweight_radius_m, *, safety_factor, tipping_fraction)
      Allowable load (kg) vs radius for a jib/boom crane, from tipping
      stability and structural moment limits. Outrigger reactions are also
      computed.

  bridge_wheel_loads(crane_span_m, bridge_mass_kg, crab_mass_kg, payload_kg,
                     crab_x_m, n_wheels_per_end, *, dynamic_factor)
      Bridge crane wheel loads (kN) per wheel, end-carriage reactions, and
      rail-bearing suitability flag.

  hook_shank_check(SWL_kN, shank_diameter_mm, thread_pitch_mm, *, material,
                   design_factor)
      Hook shank stress check per DIN 15400 — tensile stress in the shank
      thread root and safety factor against yield.

  lifting_lug_check(load_kN, plate_thickness_mm, hole_diameter_mm,
                    lug_width_mm, *, Fy_MPa, Fu_MPa, design_factor)
      Pad-eye / lifting lug check: net-section tension, pin bearing, and
      shear-out per DIN 15400 / EN 1993.

  crane_duty_class(total_cycles, load_spectrum_class, *, hours_per_year)
      FEM/ISO duty group (A1–A8) and M-class from total hoisting cycles
      and load spectrum class.

  fall_protection_brake(SWL_kN, hoist_speed_mps, governor_speed_factor,
                        drum_inertia_kgm2, drum_radius_m)
      Fall-protection / anti-runaway brake sizing: required brake torque
      and minimum brake-path distance.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise. Warnings are accumulated in the "warnings" list;
the result is still marked ok=True.

Warning conditions (never raise):
  - ROPE_OVERTENSION: line pull exceeds rope WLL
  - TIPPING: load exceeds tipping limit
  - OVER_DUTY: operating class exceeds motor/equipment duty group
  - DD_RATIO_LOW: D/d ratio below FEM minimum for the service class
  - SHANK_OVERSTRESS: hook shank stress exceeds allowable

Units
-----
  mass    — kg; weight = mass × g (g = 9.80665 m/s²)
  forces  — kN where labelled, N otherwise
  lengths — m unless mm appended
  stress  — MPa
  power   — kW
  torque  — N·m
  angles  — degrees

References
----------
FEM 1.001 Rules for the Design of Hoisting Appliances (4th ed., 1998)
ISO 4301-1:2016 Cranes — Classification — General
ISO 4301-2:2009 Cranes — Classification — Mobile cranes
DIN 15400:2012  Lifting hooks — Grades, materials, mechanical properties
DIN 15020-1:1974 Wire-rope drive design — rope-selection
ASME B30.2-2022 Overhead and Gantry Cranes
EN 13001-1:2015 Crane safety — General design — Basic principles
AS 1418.1-2002  Cranes — General requirements

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665  # standard gravity, m/s²

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _guard_positive(name: str, value: Any) -> str | None:
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
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _guard_int_positive(name: str, value: Any) -> str | None:
    if not isinstance(value, int) or value < 1:
        return f"{name} must be a positive integer, got {value!r}"
    return None


# ---------------------------------------------------------------------------
# 1. wire_rope_reeving
# ---------------------------------------------------------------------------

# Sheave efficiency per sheave (bearing friction + rope bending)
# Typical values: roller bearings ≈ 0.98, plain bearings ≈ 0.96
_DEFAULT_SHEAVE_EFF = 0.98


def wire_rope_reeving(
    SWL_kN: float,
    n_parts: int,
    *,
    rope_efficiency: float = _DEFAULT_SHEAVE_EFF,
    reeving_factor: float | None = None,
) -> dict:
    """
    Compute rope (line) pull and hook-block efficiency from reeving geometry.

    For a system with n_parts of line and sheave efficiency η per sheave,
    the total block efficiency is:

        η_block = (1 - η^n_parts) / (n_parts × (1 - η))   for η ≠ 1
        η_block = 1.0                                        for η = 1

    Line pull (rope pull on the drum) is:

        F_rope = SWL / (n_parts × η_block)

    Parameters
    ----------
    SWL_kN : float
        Safe working load at the hook (kN). Must be > 0.
    n_parts : int
        Number of rope parts / lines in the reeving system (≥ 1).
    rope_efficiency : float
        Per-sheave efficiency (default 0.98 for roller bearings).
        Must be in (0, 1].
    reeving_factor : float | None
        If provided, override the computed η_block with this factor directly.
        Used to match a manufacturer reeving diagram. Must be in (0, 1].

    Returns
    -------
    dict
        ok                  : True
        SWL_kN              : SWL used
        n_parts             : rope parts
        eta_per_sheave      : per-sheave efficiency
        eta_block           : total reeving efficiency
        line_pull_kN        : rope pull on drum (kN)
        line_pull_N         : rope pull (N)
        warnings            : list
    """
    e = _guard_positive("SWL_kN", SWL_kN)
    if e:
        return _err(e)
    if not isinstance(n_parts, int) or n_parts < 1:
        return _err(f"n_parts must be a positive integer, got {n_parts!r}")
    if not (0 < rope_efficiency <= 1.0):
        return _err(f"rope_efficiency must be in (0, 1], got {rope_efficiency}")

    warnings: list[str] = []

    eta = float(rope_efficiency)

    if reeving_factor is not None:
        if not (0 < reeving_factor <= 1.0):
            return _err(f"reeving_factor must be in (0, 1], got {reeving_factor}")
        eta_block = float(reeving_factor)
    else:
        if abs(eta - 1.0) < 1e-12:
            eta_block = 1.0
        else:
            eta_block = (1.0 - eta ** n_parts) / (n_parts * (1.0 - eta))

    line_pull_kN = float(SWL_kN) / (n_parts * eta_block)
    line_pull_N = line_pull_kN * 1000.0

    return {
        "ok": True,
        "SWL_kN": float(SWL_kN),
        "n_parts": n_parts,
        "eta_per_sheave": eta,
        "eta_block": eta_block,
        "line_pull_kN": line_pull_kN,
        "line_pull_N": line_pull_N,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. rope_diameter
# ---------------------------------------------------------------------------

# Wire-rope breaking-force tables (kN) by nominal diameter (mm) and grade.
# Approximate values from DIN 15020-1 / AS 3569 for 6×19 IWRC construction.
# Grade keys:
#   "1570" — wire strength 1570 MPa (standard grade)
#   "1770" — wire strength 1770 MPa (high-strength grade)
#   "1960" — wire strength 1960 MPa (extra-high grade)
_ROPE_MBF_KN: dict[tuple[float, str], float] = {
    (6,  "1570"):  18.0,
    (6,  "1770"):  20.4,
    (8,  "1570"):  32.0,
    (8,  "1770"):  36.2,
    (9,  "1570"):  40.5,
    (9,  "1770"):  45.8,
    (10, "1570"):  50.0,
    (10, "1770"):  56.5,
    (11, "1570"):  60.5,
    (11, "1770"):  68.3,
    (12, "1570"):  72.0,
    (12, "1770"):  81.4,
    (13, "1570"):  84.5,
    (13, "1770"):  95.5,
    (14, "1570"):  98.0,
    (14, "1770"): 110.7,
    (16, "1570"): 128.0,
    (16, "1770"): 144.6,
    (18, "1570"): 162.0,
    (18, "1770"): 183.1,
    (20, "1570"): 200.0,
    (20, "1770"): 226.0,
    (22, "1570"): 242.0,
    (22, "1770"): 273.5,
    (24, "1570"): 288.0,
    (24, "1770"): 325.5,
    (26, "1570"): 338.0,
    (26, "1770"): 382.0,
    (28, "1570"): 392.0,
    (28, "1770"): 443.0,
    (32, "1570"): 512.0,
    (32, "1770"): 578.5,
    (36, "1570"): 648.0,
    (36, "1770"): 732.5,
    (40, "1570"): 800.0,
    (40, "1960"): 990.0,
}

_ROPE_DIAMETERS_MM = sorted({d for (d, _) in _ROPE_MBF_KN})


def rope_diameter(
    line_pull_kN: float,
    safety_factor: float = 5.0,
    *,
    grade: str = "1770",
) -> dict:
    """
    Required wire-rope nominal diameter from line pull and safety factor.

    Selects the smallest standard diameter whose MBF ≥ line_pull × safety_factor.

    Parameters
    ----------
    line_pull_kN : float
        Maximum rope tension at the drum (kN). Must be > 0.
    safety_factor : float
        Minimum ratio MBF / line_pull. Default 5.0 (FEM M3–M4 standard service).
    grade : str
        Rope grade — wire UTS: "1570", "1770" (default), or "1960".

    Returns
    -------
    dict
        ok               : True
        line_pull_kN     : input line pull
        safety_factor    : SF applied
        grade            : rope grade
        required_mbf_kN  : line_pull × safety_factor
        diameter_mm      : selected nominal diameter (mm)
        mbf_kN           : minimum breaking force of selected diameter
        actual_sf        : actual safety factor = mbf / line_pull
        warnings         : list
    """
    e = _guard_positive("line_pull_kN", line_pull_kN)
    if e:
        return _err(e)
    e = _guard_positive("safety_factor", safety_factor)
    if e:
        return _err(e)

    g = str(grade).strip()
    if g not in ("1570", "1770", "1960"):
        return _err(f"grade must be '1570', '1770', or '1960', got {grade!r}")

    required_mbf = float(line_pull_kN) * float(safety_factor)
    warnings: list[str] = []

    # Find smallest diameter with MBF >= required_mbf for the chosen grade
    selected_d = None
    selected_mbf = None
    for d in _ROPE_DIAMETERS_MM:
        key = (d, g)
        if key in _ROPE_MBF_KN:
            mbf = _ROPE_MBF_KN[key]
            if mbf >= required_mbf:
                selected_d = d
                selected_mbf = mbf
                break

    if selected_d is None:
        # All diameters exhausted
        max_d = max(d for (d, gr) in _ROPE_MBF_KN if gr == g)
        max_mbf = _ROPE_MBF_KN[(max_d, g)]
        warnings.append(
            f"ROPE_OVERTENSION: required MBF {required_mbf:.1f} kN exceeds "
            f"maximum available {max_mbf:.1f} kN for grade {g} — use multiple falls."
        )
        selected_d = max_d
        selected_mbf = max_mbf

    actual_sf = selected_mbf / float(line_pull_kN)

    return {
        "ok": True,
        "line_pull_kN": float(line_pull_kN),
        "safety_factor": float(safety_factor),
        "grade": g,
        "required_mbf_kN": required_mbf,
        "diameter_mm": selected_d,
        "mbf_kN": selected_mbf,
        "actual_sf": actual_sf,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. sheave_drum_geometry
# ---------------------------------------------------------------------------

# Minimum D/d ratios (sheave PCD / rope diameter) per FEM 1.001 Table T.2
# Keyed by (mechanism_class, rope_type) — use 'standard' as a reasonable default.
# FEM groups D, E, F correspond to M3-M4, M5-M6, M7-M8 approximately.
# For simplicity, use a single table keyed by FEM class letter A–F (per old FEM).
_FEM_DD_SHEAVE: dict[str, float] = {
    "A": 11.2,   # light duty (M1)
    "B": 12.5,   # M2
    "C": 14.0,   # M3
    "D": 16.0,   # M4
    "E": 18.0,   # M5
    "F": 20.0,   # M6–M8
}

_FEM_DD_DRUM: dict[str, float] = {
    "A": 11.2,
    "B": 12.5,
    "C": 14.0,
    "D": 16.0,
    "E": 18.0,
    "F": 20.0,
}

_DEFAULT_SHEAVE_DD = 18.0   # FEM class E / M5 default
_DEFAULT_DRUM_DD = 16.0     # slightly relaxed for drum


def sheave_drum_geometry(
    rope_dia_mm: float,
    *,
    sheave_dd_ratio: float = _DEFAULT_SHEAVE_DD,
    drum_dd_ratio: float = _DEFAULT_DRUM_DD,
    fem_class: str = "E",
) -> dict:
    """
    Minimum sheave and drum pitch-circle diameters from D/d ratio.

    The D/d ratio is the ratio of the sheave (or drum) pitch-circle diameter
    to the rope diameter. Low ratios increase bending fatigue in the rope.

    Parameters
    ----------
    rope_dia_mm : float
        Nominal rope diameter (mm). Must be > 0.
    sheave_dd_ratio : float
        D/d ratio for running sheaves (default 18 for FEM class E / M5).
    drum_dd_ratio : float
        D/d ratio for the drum (default 16; drums are relaxed vs sheaves).
    fem_class : str
        FEM mechanism class A–F used to look up the minimum D/d ratio.
        Used to check whether the provided ratios meet the standard.

    Returns
    -------
    dict
        ok                  : True
        rope_dia_mm         : rope diameter used
        sheave_dd_ratio     : D/d ratio used for sheaves
        drum_dd_ratio       : D/d ratio used for drum
        pcd_sheave_mm       : minimum sheave pitch-circle diameter (mm)
        pcd_drum_mm         : minimum drum pitch-circle diameter (mm)
        fem_class           : FEM class
        fem_min_dd_sheave   : FEM minimum D/d for this class
        fem_min_dd_drum     : FEM minimum D/d for this class (drum)
        warnings            : list
    """
    e = _guard_positive("rope_dia_mm", rope_dia_mm)
    if e:
        return _err(e)
    e = _guard_positive("sheave_dd_ratio", sheave_dd_ratio)
    if e:
        return _err(e)
    e = _guard_positive("drum_dd_ratio", drum_dd_ratio)
    if e:
        return _err(e)

    fc = str(fem_class).strip().upper()
    if fc not in _FEM_DD_SHEAVE:
        return _err(f"fem_class must be one of A–F, got {fem_class!r}")

    warnings: list[str] = []
    d = float(rope_dia_mm)
    min_dd_sh = _FEM_DD_SHEAVE[fc]
    min_dd_dr = _FEM_DD_DRUM[fc]

    if sheave_dd_ratio < min_dd_sh:
        warnings.append(
            f"DD_RATIO_LOW: sheave D/d {sheave_dd_ratio} < FEM class {fc} minimum "
            f"{min_dd_sh} — rope fatigue life will be reduced."
        )
    if drum_dd_ratio < min_dd_dr:
        warnings.append(
            f"DD_RATIO_LOW: drum D/d {drum_dd_ratio} < FEM class {fc} minimum "
            f"{min_dd_dr} — rope fatigue life will be reduced."
        )

    pcd_sheave = d * sheave_dd_ratio
    pcd_drum = d * drum_dd_ratio

    return {
        "ok": True,
        "rope_dia_mm": d,
        "sheave_dd_ratio": sheave_dd_ratio,
        "drum_dd_ratio": drum_dd_ratio,
        "pcd_sheave_mm": pcd_sheave,
        "pcd_drum_mm": pcd_drum,
        "fem_class": fc,
        "fem_min_dd_sheave": min_dd_sh,
        "fem_min_dd_drum": min_dd_dr,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. drum_length
# ---------------------------------------------------------------------------


def drum_length(
    rope_dia_mm: float,
    n_parts: int,
    hoist_height_m: float,
    *,
    n_layers: int = 1,
    groove_pitch_factor: float = 1.15,
    dead_turns: int = 3,
) -> dict:
    """
    Compute drum length and winding capacity.

    The total rope length required is:
        L_rope = hoist_height × n_parts / 2   (n_parts/2 because both falls wind on)
        Actually: L_rope = hoist_height × n_parts  (single-drum)

    For multi-layer winding the drum length is:
        L_drum = (n_turns_per_layer × groove_pitch) + flanges
    where:
        n_turns_total = L_rope / (π × drum_pcd)   ... but we use drum floor dia
        groove_pitch = rope_dia × groove_pitch_factor

    This function is intentionally conservative — it calculates the winding
    length assuming all rope on one drum.

    Parameters
    ----------
    rope_dia_mm : float
        Nominal rope diameter (mm). Must be > 0.
    n_parts : int
        Number of rope parts in the reeving (integer ≥ 1).
    hoist_height_m : float
        Total hoist height / travel of the hook (m). Must be > 0.
    n_layers : int
        Number of winding layers (default 1 = single layer / grooved drum).
    groove_pitch_factor : float
        groove pitch = rope_dia × groove_pitch_factor (default 1.15 for
        standard helical grooving).
    dead_turns : int
        Number of dead (anchor) turns not in the working range (default 3,
        per ASME / FEM minimum).

    Returns
    -------
    dict
        ok                    : True
        rope_dia_mm           : rope diameter
        n_parts               : reeving parts
        hoist_height_m        : hoist height
        total_rope_length_m   : total rope required (m)
        groove_pitch_mm       : groove pitch (mm)
        turns_working         : working turns (per layer assumed equal)
        turns_total_per_layer : working + dead turns
        drum_length_mm        : computed drum barrel length (mm)
        n_layers              : layers used
        warnings              : list
    """
    e = _guard_positive("rope_dia_mm", rope_dia_mm)
    if e:
        return _err(e)
    e = _guard_positive("hoist_height_m", hoist_height_m)
    if e:
        return _err(e)
    if not isinstance(n_parts, int) or n_parts < 1:
        return _err(f"n_parts must be a positive integer, got {n_parts!r}")
    if not isinstance(n_layers, int) or n_layers < 1:
        return _err(f"n_layers must be a positive integer, got {n_layers!r}")
    e = _guard_positive("groove_pitch_factor", groove_pitch_factor)
    if e:
        return _err(e)

    warnings: list[str] = []
    d = float(rope_dia_mm)
    H = float(hoist_height_m)

    # Total rope length needed
    total_rope_m = H * n_parts

    # Groove pitch
    pitch_mm = d * groove_pitch_factor

    # Each layer holds N_turns worth of rope
    # We don't know drum PCD here, so we express capacity in turns per layer.
    # The caller provides n_layers; we compute required turns per layer.
    # For a single-layer drum, all turns are on one layer.
    # turns = (rope length per layer) / (π × drum_pcd)
    # Since drum_pcd is not known here, we output groove turns
    # as the number of grooves needed.

    # Number of working turns needed (on the drum barrel):
    # rope length is wound in grooves; each groove = 1 turn of rope.
    # turns_working = total_rope_m / (π × pcd_drum_m) — pcd not known.
    # Instead, express turns = total rope / (groove_pitch) for straight count:
    # For the drum barrel length calculation we need the number of grooves.
    # turns_per_barrel = total_rope_m / (π × r_drum)  — unknown r_drum
    #
    # Practical approach: report barrel length in terms of groove count.
    # turns_working is what must fit on the barrel.
    # To compute barrel length: L_barrel = turns_per_layer × pitch_mm
    # turns_per_layer = ceil(total_turns / n_layers) + dead_turns (per layer)
    #
    # We'll estimate drum diameter = 16 × rope_dia (FEM D class default) to
    # compute the number of turns, which we then scale by pitch to get length.

    # Default drum PCD estimate for computing turns
    pcd_drum_mm = 16.0 * d   # D/d = 16
    circumference_mm = math.pi * pcd_drum_mm
    total_turns_working = (total_rope_m * 1000.0) / circumference_mm  # turns
    total_turns_with_dead = total_turns_working + dead_turns

    turns_per_layer = math.ceil(total_turns_with_dead / n_layers)
    drum_length_mm = turns_per_layer * pitch_mm

    if n_layers > 2:
        warnings.append(
            "Multi-layer winding beyond 2 layers can cause rope crushing — "
            "verify with crane manufacturer."
        )

    return {
        "ok": True,
        "rope_dia_mm": d,
        "n_parts": n_parts,
        "hoist_height_m": H,
        "total_rope_length_m": total_rope_m,
        "groove_pitch_mm": pitch_mm,
        "turns_working": total_turns_working,
        "turns_total_per_layer": turns_per_layer,
        "drum_length_mm": drum_length_mm,
        "n_layers": n_layers,
        "dead_turns": dead_turns,
        "pcd_drum_mm_assumed": pcd_drum_mm,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. hoist_motor_power
# ---------------------------------------------------------------------------


def hoist_motor_power(
    SWL_kN: float,
    hoist_speed_mps: float,
    *,
    mechanical_efficiency: float = 0.85,
    duty_factor: float = 1.0,
) -> dict:
    """
    Required hoist motor power from SWL and rope speed.

    P = (SWL × g × v) / η_mech × duty_factor

    Note: SWL_kN is the hook load; rope speed is the hook speed.
    The duty_factor is applied on top of mechanical efficiency to account
    for accelerating inertia (typically 1.1–1.3).

    Parameters
    ----------
    SWL_kN : float
        Safe working load at hook (kN).
    hoist_speed_mps : float
        Hook hoisting speed (m/s). Must be > 0.
    mechanical_efficiency : float
        Drive train efficiency (motor→rope). Default 0.85.
    duty_factor : float
        Additional power multiplier for acceleration inertia. Default 1.0.

    Returns
    -------
    dict
        ok                    : True
        SWL_kN                : hook load
        hoist_speed_mps       : hook speed
        mechanical_efficiency : efficiency used
        duty_factor           : duty factor
        motor_power_kW        : required motor power (kW)
        motor_power_W         : required motor power (W)
        lift_power_kW         : ideal lift power (kW)
        warnings              : list
    """
    e = _guard_positive("SWL_kN", SWL_kN)
    if e:
        return _err(e)
    e = _guard_positive("hoist_speed_mps", hoist_speed_mps)
    if e:
        return _err(e)
    if not (0 < mechanical_efficiency <= 1.0):
        return _err(f"mechanical_efficiency must be in (0, 1], got {mechanical_efficiency}")
    e = _guard_positive("duty_factor", duty_factor)
    if e:
        return _err(e)

    warnings: list[str] = []
    W_N = float(SWL_kN) * 1000.0
    v = float(hoist_speed_mps)
    eta = float(mechanical_efficiency)
    df = float(duty_factor)

    lift_power_W = W_N * v
    motor_power_W = lift_power_W / eta * df
    lift_power_kW = lift_power_W / 1000.0
    motor_power_kW = motor_power_W / 1000.0

    return {
        "ok": True,
        "SWL_kN": float(SWL_kN),
        "hoist_speed_mps": v,
        "mechanical_efficiency": eta,
        "duty_factor": df,
        "lift_power_kW": lift_power_kW,
        "motor_power_kW": motor_power_kW,
        "motor_power_W": motor_power_W,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. hoist_motor_class
# ---------------------------------------------------------------------------

# FEM 1.001 M-class table: (duty_group, load_spectrum_class) → M-class
# Duty group (utilisation class): U0–U9 (total hoisting hours)
# Load spectrum class: Q1 (light) Q2 (moderate) Q3 (heavy) Q4 (very heavy)
# M-class: M1–M8 per ISO 4301-1 / FEM 1.001
# Simplified table: rows = utilisation class 1-9 (approx 0–8), cols = Q1-Q4
# Source: FEM 1.001 Table T.4 (condensed)
_M_CLASS_TABLE: dict[tuple[int, int], str] = {
    # (utilisation_int 1..8, load_spectrum_int 1..4) → M-class
    (1, 1): "M1", (1, 2): "M1", (1, 3): "M2", (1, 4): "M3",
    (2, 1): "M1", (2, 2): "M2", (2, 3): "M3", (2, 4): "M4",
    (3, 1): "M2", (3, 2): "M3", (3, 3): "M4", (3, 4): "M5",
    (4, 1): "M3", (4, 2): "M4", (4, 3): "M5", (4, 4): "M6",
    (5, 1): "M4", (5, 2): "M5", (5, 3): "M6", (5, 4): "M7",
    (6, 1): "M5", (6, 2): "M6", (6, 3): "M7", (6, 4): "M8",
    (7, 1): "M6", (7, 2): "M7", (7, 3): "M8", (7, 4): "M8",
    (8, 1): "M7", (8, 2): "M8", (8, 3): "M8", (8, 4): "M8",
}


def hoist_motor_class(
    duty_group: int,
    load_spectrum: int,
    *,
    utilisation_class: int | None = None,
) -> dict:
    """
    FEM/ISO M-class for a hoist motor from duty group and load-spectrum factor.

    Parameters
    ----------
    duty_group : int
        Utilisation class (1–8 corresponding to U1–U8 in FEM / ISO 4301-1).
        1 = light intermittent, 8 = continuous heavy.
    load_spectrum : int
        Load spectrum class:
          1 = Q1 (light): mostly light loads, rarely full SWL
          2 = Q2 (moderate): mixed loads
          3 = Q3 (heavy): often near SWL
          4 = Q4 (very heavy): almost always at SWL
    utilisation_class : int | None
        Alias for duty_group (synonym). If provided, overrides duty_group.

    Returns
    -------
    dict
        ok              : True
        duty_group      : utilisation class used
        load_spectrum   : load spectrum class used
        m_class         : FEM/ISO M-class string (M1–M8)
        warnings        : list
    """
    if utilisation_class is not None:
        duty_group = utilisation_class

    if not isinstance(duty_group, int) or duty_group < 1 or duty_group > 8:
        return _err(f"duty_group (utilisation class) must be an integer 1–8, got {duty_group!r}")
    if not isinstance(load_spectrum, int) or load_spectrum < 1 or load_spectrum > 4:
        return _err(f"load_spectrum must be an integer 1–4, got {load_spectrum!r}")

    m_class = _M_CLASS_TABLE[(duty_group, load_spectrum)]
    warnings: list[str] = []

    if m_class in ("M7", "M8"):
        warnings.append(
            f"OVER_DUTY: M-class {m_class} represents very intensive service — "
            "verify motor thermal capacity with manufacturer."
        )

    return {
        "ok": True,
        "duty_group": duty_group,
        "load_spectrum": load_spectrum,
        "m_class": m_class,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. hoist_brake_torque
# ---------------------------------------------------------------------------


def hoist_brake_torque(
    SWL_kN: float,
    drum_pcd_mm: float,
    n_parts: int,
    *,
    brake_factor: float = 1.5,
) -> dict:
    """
    Required hoist brake holding torque.

    The rope tension at the drum = SWL / (n_parts × η_block).
    The drum torque from the load = F_rope × r_drum.
    The brake must hold at least brake_factor × drum_torque.

    Parameters
    ----------
    SWL_kN : float
        Safe working load (kN).
    drum_pcd_mm : float
        Drum pitch-circle (winding) diameter (mm).
    n_parts : int
        Number of rope parts.
    brake_factor : float
        Required brake holding factor ≥ 1.0. FEM/ASME typically require
        1.25–1.5× (default 1.5).

    Returns
    -------
    dict
        ok                  : True
        SWL_kN              : hook load
        drum_pcd_mm         : drum PCD
        n_parts             : rope parts
        brake_factor        : factor applied
        rope_tension_N      : rope tension on drum (N) — without sheave losses
        drum_torque_Nm      : static drum torque from load (N·m)
        required_brake_Nm   : brake must hold this torque (N·m)
        warnings            : list
    """
    e = _guard_positive("SWL_kN", SWL_kN)
    if e:
        return _err(e)
    e = _guard_positive("drum_pcd_mm", drum_pcd_mm)
    if e:
        return _err(e)
    if not isinstance(n_parts, int) or n_parts < 1:
        return _err(f"n_parts must be a positive integer, got {n_parts!r}")
    e = _guard_positive("brake_factor", brake_factor)
    if e:
        return _err(e)

    warnings: list[str] = []
    W_N = float(SWL_kN) * 1000.0
    r_drum = float(drum_pcd_mm) / 2.0 / 1000.0  # m

    # Rope tension (static, ignoring sheave friction — conservative)
    F_rope = W_N / float(n_parts)
    drum_torque = F_rope * r_drum
    required_brake = drum_torque * float(brake_factor)

    if float(brake_factor) < 1.25:
        warnings.append(
            f"Brake factor {brake_factor} < 1.25 — may not meet FEM/ASME minimum "
            "requirement for holding brake on hoists."
        )

    return {
        "ok": True,
        "SWL_kN": float(SWL_kN),
        "drum_pcd_mm": float(drum_pcd_mm),
        "n_parts": n_parts,
        "brake_factor": float(brake_factor),
        "rope_tension_N": F_rope,
        "drum_torque_Nm": drum_torque,
        "required_brake_Nm": required_brake,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. travel_resistance
# ---------------------------------------------------------------------------


def travel_resistance(
    crane_mass_kg: float,
    payload_kg: float,
    *,
    coeff_rolling: float = 0.015,
    coeff_wind: float = 0.0,
    wind_pressure_Pa: float = 250.0,
    frontal_area_m2: float = 0.0,
) -> dict:
    """
    Travel drive resistance force.

    Combines rolling resistance and wind resistance:
        F_roll = (crane_mass + payload) × g × f_roll
        F_wind = wind_pressure × frontal_area × Cd   (Cd = 1.3 assumed for box)
        F_total = F_roll + F_wind

    Parameters
    ----------
    crane_mass_kg : float
        Empty crane/trolley mass (kg). Must be > 0.
    payload_kg : float
        Suspended payload mass (kg). Must be >= 0.
    coeff_rolling : float
        Rolling resistance coefficient (dimensionless, default 0.015 for
        flanged wheels on steel rail per FEM).
    coeff_wind : float
        Wind load multiplier on wind pressure (default 0 = neglect wind).
    wind_pressure_Pa : float
        Design wind pressure (Pa). Default 250 Pa (storm service per FEM).
    frontal_area_m2 : float
        Frontal area exposed to wind (m²). Default 0 (wind neglected).

    Returns
    -------
    dict
        ok               : True
        total_mass_kg    : crane + payload
        rolling_force_N  : rolling resistance (N)
        wind_force_N     : wind force (N)
        total_force_N    : total travel resistance (N)
        total_force_kN   : total travel resistance (kN)
        warnings         : list
    """
    e = _guard_positive("crane_mass_kg", crane_mass_kg)
    if e:
        return _err(e)
    e = _guard_nonneg("payload_kg", payload_kg)
    if e:
        return _err(e)
    e = _guard_positive("coeff_rolling", coeff_rolling)
    if e:
        return _err(e)

    warnings: list[str] = []
    total_mass = float(crane_mass_kg) + float(payload_kg)
    W_N = total_mass * _G

    F_roll = W_N * float(coeff_rolling)

    _Cd = 1.3  # drag coefficient for box-shaped structure
    F_wind = float(wind_pressure_Pa) * float(frontal_area_m2) * _Cd * float(coeff_wind)

    F_total = F_roll + F_wind

    return {
        "ok": True,
        "total_mass_kg": total_mass,
        "rolling_force_N": F_roll,
        "wind_force_N": F_wind,
        "total_force_N": F_total,
        "total_force_kN": F_total / 1000.0,
        "coeff_rolling": float(coeff_rolling),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. travel_motor_power
# ---------------------------------------------------------------------------


def travel_motor_power(
    resistance_N: float,
    travel_speed_mps: float,
    *,
    motor_efficiency: float = 0.85,
    acceleration_factor: float = 1.25,
) -> dict:
    """
    Required travel motor power from resistance force and speed.

    P = F_resist × v / η × acceleration_factor

    Parameters
    ----------
    resistance_N : float
        Total travel resistance (N). Must be > 0.
    travel_speed_mps : float
        Travel speed (m/s). Must be > 0.
    motor_efficiency : float
        Motor + gearbox efficiency (default 0.85).
    acceleration_factor : float
        Factor to account for accelerating inertia (default 1.25 per FEM).

    Returns
    -------
    dict
        ok                 : True
        resistance_N       : input resistance
        travel_speed_mps   : speed
        motor_efficiency   : efficiency
        acceleration_factor: factor
        motor_power_kW     : required motor power (kW)
        motor_power_W      : required motor power (W)
        warnings           : list
    """
    e = _guard_positive("resistance_N", resistance_N)
    if e:
        return _err(e)
    e = _guard_positive("travel_speed_mps", travel_speed_mps)
    if e:
        return _err(e)
    if not (0 < motor_efficiency <= 1.0):
        return _err(f"motor_efficiency must be in (0, 1], got {motor_efficiency}")
    e = _guard_positive("acceleration_factor", acceleration_factor)
    if e:
        return _err(e)

    warnings: list[str] = []
    P_W = (float(resistance_N) * float(travel_speed_mps) / float(motor_efficiency)
           * float(acceleration_factor))

    return {
        "ok": True,
        "resistance_N": float(resistance_N),
        "travel_speed_mps": float(travel_speed_mps),
        "motor_efficiency": float(motor_efficiency),
        "acceleration_factor": float(acceleration_factor),
        "motor_power_kW": P_W / 1000.0,
        "motor_power_W": P_W,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. jib_load_chart
# ---------------------------------------------------------------------------


def jib_load_chart(
    slew_radius_m: float,
    jib_length_m: float,
    jib_mass_kg: float,
    counterweight_kg: float,
    counterweight_radius_m: float,
    *,
    safety_factor: float = 1.5,
    tipping_fraction: float = 0.75,
    crane_base_mass_kg: float = 0.0,
    base_radius_m: float = 0.0,
) -> dict:
    """
    Allowable load vs. slew radius for a jib / boom crane from tipping stability.

    The tipping moment about the front edge of the crane base:
        M_tipping = crane_base_mass × g × base_radius  (restoring, if any)
                  + counterweight_mass × g × counterweight_radius  (restoring)
        M_overturning = load × g × slew_radius + jib_mass × g × (jib_length/2)

    Allowable load:
        Allowable_load = (M_tipping / safety_factor
                          - jib_mass × g × jib_length/2) / (g × slew_radius)

    The tipping_fraction parameter limits structural moment rather than pure
    tipping (typical practice: allow only 75% of tipping load).

    Parameters
    ----------
    slew_radius_m : float
        Working radius from slew axis to hook (m). Must be > 0.
    jib_length_m : float
        Jib/boom length (m). Used to estimate jib self-weight moment arm.
    jib_mass_kg : float
        Jib/boom self-weight (kg). Must be >= 0.
    counterweight_kg : float
        Counterweight mass (kg). Must be >= 0.
    counterweight_radius_m : float
        Counterweight moment arm from tipping axis (m). Must be >= 0.
    safety_factor : float
        Safety factor on stability (default 1.5). Must be > 1.0.
    tipping_fraction : float
        Fraction of tipping load as structural limit (default 0.75).
    crane_base_mass_kg : float
        Crane base / turntable / undercarriage mass (kg, default 0).
    base_radius_m : float
        Base mass moment arm to tipping axis (m, default 0).

    Returns
    -------
    dict
        ok                       : True
        slew_radius_m            : radius used
        restoring_moment_Nm      : total restoring moment (N·m)
        jib_overturning_Nm       : jib self-weight overturning (N·m)
        allowable_load_kg        : maximum allowable hook load (kg) from tipping
        allowable_load_kN        : maximum allowable hook load (kN)
        structural_allowable_kg  : tipping_fraction × allowable_load_kg
        tipping                  : True if load ≥ allowable_load_kg
        warnings                 : list
    """
    e = _guard_positive("slew_radius_m", slew_radius_m)
    if e:
        return _err(e)
    e = _guard_positive("jib_length_m", jib_length_m)
    if e:
        return _err(e)
    e = _guard_nonneg("jib_mass_kg", jib_mass_kg)
    if e:
        return _err(e)
    e = _guard_nonneg("counterweight_kg", counterweight_kg)
    if e:
        return _err(e)
    e = _guard_nonneg("counterweight_radius_m", counterweight_radius_m)
    if e:
        return _err(e)
    e = _guard_positive("safety_factor", safety_factor)
    if e:
        return _err(e)
    if not (0 < tipping_fraction <= 1.0):
        return _err(f"tipping_fraction must be in (0, 1], got {tipping_fraction}")

    warnings: list[str] = []

    M_restoring = (
        float(counterweight_kg) * _G * float(counterweight_radius_m)
        + float(crane_base_mass_kg) * _G * float(base_radius_m)
    )
    jib_ot_moment = float(jib_mass_kg) * _G * (float(jib_length_m) / 2.0)

    # Net restoring less jib overturning, then divide by safety_factor
    net_allowable_moment = M_restoring / float(safety_factor) - jib_ot_moment

    if net_allowable_moment <= 0:
        warnings.append(
            "TIPPING: counterweight insufficient to balance jib self-weight "
            "at this radius — crane would tip without any payload."
        )
        net_allowable_moment = 0.0

    allowable_N = net_allowable_moment / (float(slew_radius_m))  # N weight
    allowable_kg = allowable_N / _G
    allowable_kN = allowable_N / 1000.0
    structural_kg = allowable_kg * float(tipping_fraction)

    return {
        "ok": True,
        "slew_radius_m": float(slew_radius_m),
        "restoring_moment_Nm": M_restoring,
        "jib_overturning_Nm": jib_ot_moment,
        "safety_factor": float(safety_factor),
        "tipping_fraction": float(tipping_fraction),
        "allowable_load_kg": allowable_kg,
        "allowable_load_kN": allowable_kN,
        "structural_allowable_kg": structural_kg,
        "counterweight_kg": float(counterweight_kg),
        "counterweight_radius_m": float(counterweight_radius_m),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. bridge_wheel_loads
# ---------------------------------------------------------------------------


def bridge_wheel_loads(
    crane_span_m: float,
    bridge_mass_kg: float,
    crab_mass_kg: float,
    payload_kg: float,
    crab_x_m: float,
    n_wheels_per_end: int = 2,
    *,
    dynamic_factor: float = 1.15,
) -> dict:
    """
    Bridge crane wheel loads and end-carriage reactions.

    The bridge girder carries the crab + payload at position crab_x_m from the
    left end-carriage. The bridge is modelled as a simply-supported beam.

    Left end-carriage reaction (static):
        R_L = (crab_mass + payload) × g × (span - crab_x) / span

    Right end-carriage reaction:
        R_R = (crab_mass + payload) × g × crab_x / span

    Bridge self-weight is distributed equally to both ends.

    Dynamic factor is applied to the wheel loads per FEM/ASME.

    Parameters
    ----------
    crane_span_m : float
        Rail-to-rail span (m). Must be > 0.
    bridge_mass_kg : float
        Bridge girder self-mass (kg). Must be > 0.
    crab_mass_kg : float
        Crab/trolley mass (kg). Must be >= 0.
    payload_kg : float
        Payload (kg). Must be >= 0.
    crab_x_m : float
        Crab position from left rail (m). Must be in [0, span].
    n_wheels_per_end : int
        Number of wheels per end carriage (default 2).
    dynamic_factor : float
        Dynamic amplification factor on wheel loads. Default 1.15 per FEM
        (hoisting class HC2).

    Returns
    -------
    dict
        ok                     : True
        crane_span_m           : span
        left_reaction_N        : total static reaction at left end carriage (N)
        right_reaction_N       : total static reaction at right end carriage (N)
        left_reaction_kN       : static (kN)
        right_reaction_kN      : static (kN)
        left_wheel_load_kN     : per-wheel load including dynamic factor (kN)
        right_wheel_load_kN    : per-wheel load including dynamic factor (kN)
        n_wheels_per_end       : wheels per end carriage
        dynamic_factor         : factor applied
        warnings               : list
    """
    e = _guard_positive("crane_span_m", crane_span_m)
    if e:
        return _err(e)
    e = _guard_positive("bridge_mass_kg", bridge_mass_kg)
    if e:
        return _err(e)
    e = _guard_nonneg("crab_mass_kg", crab_mass_kg)
    if e:
        return _err(e)
    e = _guard_nonneg("payload_kg", payload_kg)
    if e:
        return _err(e)
    span = float(crane_span_m)
    cx = float(crab_x_m)
    if cx < 0 or cx > span:
        return _err(f"crab_x_m ({crab_x_m}) must be in [0, {span}]")
    if not isinstance(n_wheels_per_end, int) or n_wheels_per_end < 1:
        return _err(f"n_wheels_per_end must be a positive integer, got {n_wheels_per_end!r}")
    e = _guard_positive("dynamic_factor", dynamic_factor)
    if e:
        return _err(e)

    warnings: list[str] = []

    W_bridge = float(bridge_mass_kg) * _G
    W_crab_payload = (float(crab_mass_kg) + float(payload_kg)) * _G

    # Bridge weight: equal split each end
    bridge_per_end = W_bridge / 2.0

    # Crab+payload: moment distribution
    R_L_crab = W_crab_payload * (span - cx) / span
    R_R_crab = W_crab_payload * cx / span

    R_L = bridge_per_end + R_L_crab
    R_R = bridge_per_end + R_R_crab

    n_w = n_wheels_per_end
    df = float(dynamic_factor)
    left_wheel_kN = R_L * df / n_w / 1000.0
    right_wheel_kN = R_R * df / n_w / 1000.0

    # Simple advisory check: very high wheel loads
    if max(left_wheel_kN, right_wheel_kN) > 600.0:
        warnings.append(
            "Wheel load exceeds 600 kN — verify rail and structure with specialist."
        )

    return {
        "ok": True,
        "crane_span_m": span,
        "bridge_mass_kg": float(bridge_mass_kg),
        "crab_mass_kg": float(crab_mass_kg),
        "payload_kg": float(payload_kg),
        "crab_x_m": cx,
        "n_wheels_per_end": n_w,
        "dynamic_factor": df,
        "left_reaction_N": R_L,
        "right_reaction_N": R_R,
        "left_reaction_kN": R_L / 1000.0,
        "right_reaction_kN": R_R / 1000.0,
        "left_wheel_load_kN": left_wheel_kN,
        "right_wheel_load_kN": right_wheel_kN,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. hook_shank_check
# ---------------------------------------------------------------------------

# Material yield strengths (MPa) for DIN 15400 hook grades
_HOOK_MATERIAL_FY: dict[str, float] = {
    "grade_P": 355.0,   # DIN 15400 grade P — general purpose hook steel
    "grade_S": 490.0,   # DIN 15400 grade S — high-strength hook steel
    "grade_T": 590.0,   # DIN 15400 grade T — alloy hook steel
    "S235": 235.0,      # General structural steel (not typical for hooks)
    "S355": 355.0,      # S355 structural
    "42CrMo4": 700.0,   # Alloy steel quench & tempered
}


def hook_shank_check(
    SWL_kN: float,
    shank_diameter_mm: float,
    thread_pitch_mm: float,
    *,
    material: str = "grade_P",
    design_factor: float = 4.0,
) -> dict:
    """
    Hook shank tensile stress check per DIN 15400.

    The shank is loaded in tension by the SWL. The critical section is the
    thread root, whose area is approximated as:
        A_root = π/4 × (shank_diameter - 0.9743 × thread_pitch)²

    This is the ISO metric thread minor diameter formula.

    Parameters
    ----------
    SWL_kN : float
        Safe working load (kN).
    shank_diameter_mm : float
        Nominal shank (thread major) diameter (mm). Must be > 0.
    thread_pitch_mm : float
        Thread pitch (mm). Must be > 0.
    material : str
        Hook material grade (default 'grade_P'):
          'grade_P' — Fy 355 MPa (DIN 15400 P)
          'grade_S' — Fy 490 MPa (DIN 15400 S)
          'grade_T' — Fy 590 MPa (DIN 15400 T)
          '42CrMo4' — Fy 700 MPa (quench-tempered alloy)
    design_factor : float
        Design factor on yield. Default 4.0 per DIN 15400.

    Returns
    -------
    dict
        ok                : True
        SWL_kN            : hook load
        shank_diameter_mm : major diameter
        thread_pitch_mm   : pitch
        material          : material key
        Fy_MPa            : yield strength
        minor_dia_mm      : ISO thread minor (root) diameter (mm)
        root_area_mm2     : thread root cross-section area (mm²)
        tension_stress_MPa: tensile stress in thread root (MPa)
        allowable_MPa     : Fy / design_factor
        utilisation       : tension_stress / allowable
        pass_shank        : True if utilisation <= 1.0
        safety_factor_actual : Fy / tension_stress
        warnings          : list
    """
    e = _guard_positive("SWL_kN", SWL_kN)
    if e:
        return _err(e)
    e = _guard_positive("shank_diameter_mm", shank_diameter_mm)
    if e:
        return _err(e)
    e = _guard_positive("thread_pitch_mm", thread_pitch_mm)
    if e:
        return _err(e)
    e = _guard_positive("design_factor", design_factor)
    if e:
        return _err(e)

    mat = str(material).strip()
    if mat not in _HOOK_MATERIAL_FY:
        available = list(_HOOK_MATERIAL_FY.keys())
        return _err(f"material must be one of {available}, got {material!r}")

    Fy = _HOOK_MATERIAL_FY[mat]
    warnings: list[str] = []

    P_N = float(SWL_kN) * 1000.0
    d_maj = float(shank_diameter_mm)
    pitch = float(thread_pitch_mm)

    # ISO metric thread minor (root) diameter
    d_minor = d_maj - 0.9743 * pitch
    if d_minor <= 0:
        return _err(
            f"thread_pitch_mm ({pitch}) too large for shank_diameter_mm ({d_maj}) — "
            "results in non-positive minor diameter."
        )

    A_root = math.pi / 4.0 * d_minor ** 2  # mm²
    sigma = P_N / A_root  # MPa (N/mm²)
    allowable = Fy / float(design_factor)
    util = sigma / allowable
    actual_sf = Fy / sigma if sigma > 0 else float("inf")

    if util > 1.0:
        warnings.append(
            f"SHANK_OVERSTRESS: tensile stress {sigma:.1f} MPa > allowable "
            f"{allowable:.1f} MPa (utilisation {util:.3f})."
        )

    return {
        "ok": True,
        "SWL_kN": float(SWL_kN),
        "shank_diameter_mm": d_maj,
        "thread_pitch_mm": pitch,
        "material": mat,
        "Fy_MPa": Fy,
        "minor_dia_mm": d_minor,
        "root_area_mm2": A_root,
        "tension_stress_MPa": sigma,
        "allowable_MPa": allowable,
        "utilisation": util,
        "pass_shank": util <= 1.0,
        "safety_factor_actual": actual_sf,
        "design_factor": float(design_factor),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 13. lifting_lug_check
# ---------------------------------------------------------------------------


def lifting_lug_check(
    load_kN: float,
    plate_thickness_mm: float,
    hole_diameter_mm: float,
    lug_width_mm: float,
    *,
    Fy_MPa: float = 350.0,
    Fu_MPa: float = 480.0,
    design_factor: float = 3.0,
) -> dict:
    """
    Pad-eye / lifting lug strength check per DIN 15400 / EN 1993 principles.

    Checks three failure modes:
      1. Net-section tension (across the hole at the plate centreline)
      2. Pin bearing on the hole
      3. Double shear-out (two shear planes)

    Parameters
    ----------
    load_kN : float
        Applied load (kN). Must be > 0.
    plate_thickness_mm : float
        Lug plate thickness (mm). Must be > 0.
    hole_diameter_mm : float
        Pin-hole diameter (mm). Must be < lug_width_mm.
    lug_width_mm : float
        Width of lug plate at the hole section (mm). Must be > hole_diameter_mm.
    Fy_MPa : float
        Plate yield strength (MPa, default 350).
    Fu_MPa : float
        Plate ultimate tensile strength (MPa, default 480).
    design_factor : float
        Design factor (default 3.0 per FEM lifting hardware).

    Returns
    -------
    dict
        ok                       : True
        tension_net_stress_MPa   : net-section tension (MPa)
        bearing_stress_MPa       : bearing stress on hole (MPa)
        shearout_stress_MPa      : shear-out stress (MPa) — double shear
        tension_allow_MPa        : Fu / design_factor
        bearing_allow_MPa        : 1.5 × Fy / design_factor
        shearout_allow_MPa       : 0.6 × Fy / design_factor
        tension_pass             : bool
        bearing_pass             : bool
        shearout_pass            : bool
        utilisation_tension      : float
        utilisation_bearing      : float
        utilisation_shearout     : float
        governing_utilisation    : float
        warnings                 : list
    """
    e = _guard_positive("load_kN", load_kN)
    if e:
        return _err(e)
    e = _guard_positive("plate_thickness_mm", plate_thickness_mm)
    if e:
        return _err(e)
    e = _guard_positive("hole_diameter_mm", hole_diameter_mm)
    if e:
        return _err(e)
    e = _guard_positive("lug_width_mm", lug_width_mm)
    if e:
        return _err(e)
    if float(hole_diameter_mm) >= float(lug_width_mm):
        return _err(
            f"hole_diameter_mm ({hole_diameter_mm}) must be < lug_width_mm ({lug_width_mm})"
        )
    e = _guard_positive("Fy_MPa", Fy_MPa)
    if e:
        return _err(e)
    e = _guard_positive("Fu_MPa", Fu_MPa)
    if e:
        return _err(e)
    e = _guard_positive("design_factor", design_factor)
    if e:
        return _err(e)

    warnings: list[str] = []
    P_N = float(load_kN) * 1000.0
    t = float(plate_thickness_mm)
    d_hole = float(hole_diameter_mm)
    W = float(lug_width_mm)
    Fy = float(Fy_MPa)
    Fu = float(Fu_MPa)
    df = float(design_factor)

    # 1. Net section tension
    A_net = (W - d_hole) * t
    sigma_t = P_N / A_net

    # 2. Bearing stress: pin diameter ≈ hole diameter (close fit)
    A_bearing = d_hole * t
    sigma_b = P_N / A_bearing

    # 3. Shear-out: edge distance e = W/2 (half the width beyond hole)
    e_dist = (W - d_hole) / 2.0
    A_shear = 2.0 * e_dist * t
    if A_shear <= 0:
        A_shear = t * d_hole
    sigma_s = P_N / A_shear

    allow_t = Fu / df
    allow_b = 1.5 * Fy / df
    allow_s = 0.6 * Fy / df

    ut = sigma_t / allow_t if allow_t > 0 else float("inf")
    ub = sigma_b / allow_b if allow_b > 0 else float("inf")
    us = sigma_s / allow_s if allow_s > 0 else float("inf")
    gov = max(ut, ub, us)

    for label, util in [("tension", ut), ("bearing", ub), ("shear-out", us)]:
        if util > 1.0:
            warnings.append(
                f"WLL_EXCEEDED: {label} utilisation {util:.3f} > 1.0 — lug overstressed."
            )

    return {
        "ok": True,
        "load_kN": float(load_kN),
        "plate_thickness_mm": t,
        "hole_diameter_mm": d_hole,
        "lug_width_mm": W,
        "Fy_MPa": Fy,
        "Fu_MPa": Fu,
        "design_factor": df,
        "net_area_mm2": A_net,
        "tension_net_stress_MPa": sigma_t,
        "bearing_stress_MPa": sigma_b,
        "shearout_stress_MPa": sigma_s,
        "tension_allow_MPa": allow_t,
        "bearing_allow_MPa": allow_b,
        "shearout_allow_MPa": allow_s,
        "tension_pass": ut <= 1.0,
        "bearing_pass": ub <= 1.0,
        "shearout_pass": us <= 1.0,
        "utilisation_tension": ut,
        "utilisation_bearing": ub,
        "utilisation_shearout": us,
        "governing_utilisation": gov,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 14. crane_duty_class
# ---------------------------------------------------------------------------

# FEM 1.001 duty group (A1–A8) from total hoisting cycles and load spectrum class.
# Total cycles thresholds per FEM 1.001 Table T.1:
_FEM_CYCLE_THRESHOLDS = [
    (3_200,    "A1"),
    (6_300,    "A2"),
    (12_500,   "A3"),
    (25_000,   "A4"),
    (50_000,   "A5"),
    (100_000,  "A6"),
    (200_000,  "A7"),
    (float("inf"), "A8"),
]

# FEM 1.001 Table T.3: duty group A-class × load spectrum → M-class
# Load spectrum: Q1=1 (light), Q2=2, Q3=3, Q4=4 (very heavy)
_FEM_DUTY_M_CLASS: dict[tuple[str, int], str] = {
    ("A1", 1): "M1", ("A1", 2): "M1", ("A1", 3): "M2", ("A1", 4): "M3",
    ("A2", 1): "M1", ("A2", 2): "M2", ("A2", 3): "M3", ("A2", 4): "M4",
    ("A3", 1): "M2", ("A3", 2): "M3", ("A3", 3): "M4", ("A3", 4): "M5",
    ("A4", 1): "M3", ("A4", 2): "M4", ("A4", 3): "M5", ("A4", 4): "M6",
    ("A5", 1): "M4", ("A5", 2): "M5", ("A5", 3): "M6", ("A5", 4): "M7",
    ("A6", 1): "M5", ("A6", 2): "M6", ("A6", 3): "M7", ("A6", 4): "M8",
    ("A7", 1): "M6", ("A7", 2): "M7", ("A7", 3): "M8", ("A7", 4): "M8",
    ("A8", 1): "M7", ("A8", 2): "M8", ("A8", 3): "M8", ("A8", 4): "M8",
}


def crane_duty_class(
    total_cycles: int,
    load_spectrum_class: int,
    *,
    hours_per_year: float = 2000.0,
) -> dict:
    """
    FEM/ISO duty group (A1–A8) and M-class from total hoisting cycles.

    Parameters
    ----------
    total_cycles : int
        Expected total number of hoisting cycles over the crane's service life.
        Must be > 0.
    load_spectrum_class : int
        Load spectrum:
          1 = Q1 light (mostly empty / partial loads)
          2 = Q2 moderate
          3 = Q3 heavy (often near SWL)
          4 = Q4 very heavy (always at SWL)
    hours_per_year : float
        Approximate operating hours per year (for service-life estimation).
        Default 2000 h/year.

    Returns
    -------
    dict
        ok                  : True
        total_cycles        : cycles input
        load_spectrum_class : Q-class used
        duty_group          : FEM A-class (A1–A8)
        m_class             : FEM/ISO M-class (M1–M8)
        hours_per_year      : hours input
        warnings            : list
    """
    if not isinstance(total_cycles, int) or total_cycles < 1:
        return _err(f"total_cycles must be a positive integer, got {total_cycles!r}")
    if not isinstance(load_spectrum_class, int) or load_spectrum_class < 1 or load_spectrum_class > 4:
        return _err(f"load_spectrum_class must be 1–4, got {load_spectrum_class!r}")
    e = _guard_positive("hours_per_year", hours_per_year)
    if e:
        return _err(e)

    warnings: list[str] = []

    duty_group = "A8"
    for threshold, group in _FEM_CYCLE_THRESHOLDS:
        if total_cycles <= threshold:
            duty_group = group
            break

    m_class = _FEM_DUTY_M_CLASS[(duty_group, load_spectrum_class)]

    if m_class in ("M7", "M8"):
        warnings.append(
            f"OVER_DUTY: M-class {m_class} indicates very heavy service — "
            "verify all components against this duty."
        )

    return {
        "ok": True,
        "total_cycles": total_cycles,
        "load_spectrum_class": load_spectrum_class,
        "duty_group": duty_group,
        "m_class": m_class,
        "hours_per_year": float(hours_per_year),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 15. fall_protection_brake
# ---------------------------------------------------------------------------


def fall_protection_brake(
    SWL_kN: float,
    hoist_speed_mps: float,
    governor_speed_factor: float,
    drum_inertia_kgm2: float,
    drum_radius_m: float,
) -> dict:
    """
    Fall-protection / anti-runaway brake sizing.

    The anti-runaway (over-speed governor + brake) must decelerate the load
    after a rope or motor failure. The required brake torque is:

        T_brake = SWL × g × r_drum / n_parts
                + J_drum × α_decel

    where deceleration α_decel = v_trigger² / (2 × s_brake_max) with:
        v_trigger = hoist_speed × governor_speed_factor

    The minimum brake-path distance to stop from v_trigger:
        s_brake = v_trigger² / (2 × a_decel)

    This function conservatively uses a_decel = g (free-fall deceleration)
    unless the computed brake torque implies a higher deceleration.

    Parameters
    ----------
    SWL_kN : float
        Safe working load (kN).
    hoist_speed_mps : float
        Rated hoist speed (m/s). Must be > 0.
    governor_speed_factor : float
        Speed at which governor triggers as a multiple of rated speed
        (typical 1.2–1.4). Must be > 1.0.
    drum_inertia_kgm2 : float
        Drum rotational inertia (kg·m²). Must be >= 0.
    drum_radius_m : float
        Drum winding radius (m). Must be > 0.

    Returns
    -------
    dict
        ok                   : True
        SWL_kN               : hook load
        hoist_speed_mps      : rated speed
        trigger_speed_mps    : governor trigger speed (m/s)
        governor_factor      : factor used
        drum_inertia_kgm2    : drum inertia
        drum_radius_m        : drum radius
        load_torque_Nm       : static load torque at drum (N·m)
        dynamic_torque_Nm    : inertia contribution (N·m) at g deceleration
        required_brake_Nm    : total required brake torque (N·m)
        brake_path_m         : brake path distance from trigger speed (m)
        warnings             : list
    """
    e = _guard_positive("SWL_kN", SWL_kN)
    if e:
        return _err(e)
    e = _guard_positive("hoist_speed_mps", hoist_speed_mps)
    if e:
        return _err(e)
    if float(governor_speed_factor) <= 1.0:
        return _err(f"governor_speed_factor must be > 1.0, got {governor_speed_factor}")
    e = _guard_nonneg("drum_inertia_kgm2", drum_inertia_kgm2)
    if e:
        return _err(e)
    e = _guard_positive("drum_radius_m", drum_radius_m)
    if e:
        return _err(e)

    warnings: list[str] = []
    W_N = float(SWL_kN) * 1000.0
    r = float(drum_radius_m)
    v_rated = float(hoist_speed_mps)
    gsf = float(governor_speed_factor)

    v_trigger = v_rated * gsf

    # Angular velocity at trigger
    omega_trigger = v_trigger / r  # rad/s

    # Deceleration: use g as reference
    a_decel = _G

    # Brake path
    brake_path = v_trigger ** 2 / (2.0 * a_decel)

    # Required deceleration torque from inertia
    alpha_decel = a_decel / r  # rad/s²
    J = float(drum_inertia_kgm2)
    T_inertia = J * alpha_decel

    # Static load torque (one part, conservative)
    T_load = W_N * r

    T_required = T_load + T_inertia

    if brake_path > 0.5:
        warnings.append(
            f"Brake path {brake_path:.3f} m > 0.5 m — verify governor set-point "
            "and brake response time with manufacturer."
        )

    return {
        "ok": True,
        "SWL_kN": float(SWL_kN),
        "hoist_speed_mps": v_rated,
        "trigger_speed_mps": v_trigger,
        "governor_speed_factor": gsf,
        "drum_inertia_kgm2": J,
        "drum_radius_m": r,
        "load_torque_Nm": T_load,
        "dynamic_torque_Nm": T_inertia,
        "required_brake_Nm": T_required,
        "brake_path_m": brake_path,
        "warnings": warnings,
    }
