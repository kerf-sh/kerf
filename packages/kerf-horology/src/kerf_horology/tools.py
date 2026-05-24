"""LLM-callable tools for the horology plugin.

These are thin wrappers around the underlying computation modules that
present a clean JSON-serialisable interface for Kerf's tool-call layer.

Tools
-----
train_calculator
    Given a target frequency (Hz) and power-reserve (hours), returns the
    required gear-train ratio, barrel turns to store, and a 3-stage
    integer wheel/pinion factorisation.

check_tooth_profile
    Validates the involute tooth profile for a given module, tooth count,
    and pressure angle, returning pass/fail and any failure reasons.

escapement_geometry
    Compute Swiss lever escapement geometry: draw angle, lift angle,
    drop, impulse force, energy per impulse, and self-consistency check.

mainspring_torque_tool
    Return mainspring barrel torque (N·mm) at a given winding state.

power_reserve
    Estimate usable power reserve (hours) given mainspring and gear-train
    parameters.

balance_period_tool
    Compute balance-wheel oscillation period and beat rate from inertia
    and hairspring stiffness.

isochronism
    Check isochronism of the balance-hairspring oscillator.
"""

from __future__ import annotations

import math
from typing import Any, Tuple

from kerf_partsgen.generators.horology.involute import check_involute_profile
from kerf_partsgen.generators.horology.train_calculator import compute_train_ratio
from kerf_horology.escapement import swiss_lever_geometry
from kerf_horology.mainspring import mainspring_torque, power_reserve_hours
from kerf_horology.balance import (
    balance_period,
    beats_per_hour,
    isochronism_check,
    hairspring_stiffness,
)


def _train_calculator(
    freq_hz: float,
    power_reserve_hours: float,
    escape_wheel_teeth: int = 15,
    barrel_turns_per_day: float = 7.5,
) -> dict[str, Any]:
    """Compute gear-train ratio for a mechanical watch movement.

    Parameters
    ----------
    freq_hz:
        Balance-wheel frequency in Hz (e.g. 3.0 for 21 600 bph).
    power_reserve_hours:
        Required power reserve in hours (e.g. 48 for two-day reserve).
    escape_wheel_teeth:
        Escape-wheel tooth count (default 15, Swiss lever standard).
    barrel_turns_per_day:
        Mainspring barrel turns per 24-hour day (default 7.5, ETA 2824).

    Returns
    -------
    dict with keys:
        required_ratio (float): total gear ratio barrel → escape wheel
        barrel_turns_stored (float): turns stored for the power reserve
        stages (list): [{wheel_teeth, pinion_leaves, ratio}, ...]
        achieved_ratio (float): product of stage ratios
        ratio_error_pct (float): deviation from required ratio (%)
    """
    spec = compute_train_ratio(
        freq_hz=freq_hz,
        power_reserve_hours=power_reserve_hours,
        escape_wheel_teeth=escape_wheel_teeth,
        barrel_turns_per_day=barrel_turns_per_day,
    )
    return {
        "freq_hz": spec.freq_hz,
        "power_reserve_hours": spec.power_reserve_hours,
        "escape_wheel_teeth": spec.escape_wheel_teeth,
        "barrel_turns_per_day": spec.barrel_turns_per_day,
        "required_ratio": round(spec.required_ratio, 4),
        "barrel_turns_stored": round(spec.barrel_turns_stored, 3),
        "stages": [
            {
                "wheel_teeth": s.wheel_teeth,
                "pinion_leaves": s.pinion_leaves,
                "ratio": round(s.ratio, 6),
            }
            for s in spec.stages
        ],
        "achieved_ratio": round(spec.achieved_ratio, 4),
        "ratio_error_pct": round(spec.ratio_error_pct, 4),
    }


def _check_tooth_profile(
    module: float,
    num_teeth: int,
    pressure_angle_deg: float = 20.0,
) -> dict[str, Any]:
    """Validate an involute tooth profile.

    Parameters
    ----------
    module:
        Tooth module in mm (pitch_diameter / num_teeth).
    num_teeth:
        Number of teeth on the gear.
    pressure_angle_deg:
        Pressure angle in degrees (20.0 standard for Swiss watches).

    Returns
    -------
    dict with keys:
        passed (bool): True if all geometry criteria pass
        reasons (list[str]): failure reasons (empty when passed)
        r_base (float): base-circle radius (mm)
        r_pitch (float): pitch radius (mm)
        r_tip (float): tip-circle radius (mm)
    """
    result = check_involute_profile(module, num_teeth, pressure_angle_deg)
    return {
        "passed": result.passed,
        "reasons": result.reasons,
        "r_base_mm": round(result.r_base, 6),
        "r_pitch_mm": round(result.r_pitch, 6),
        "r_tip_mm": round(result.r_tip, 6),
        "n_profile_points": result.n_points,
    }


def _escapement_geometry(
    escape_teeth: int = 15,
    lift_deg: float = 8.0,
    draw_deg: float = 12.0,
    escape_wheel_radius_mm: float = 1.925,
    lever_arm_mm: float = 1.6,
    escape_wheel_torque_Nmm: float = 0.35,
) -> dict[str, Any]:
    """Compute Swiss lever escapement geometry.

    Parameters
    ----------
    escape_teeth : int
        Number of teeth on the escape wheel (default 15).
    lift_deg : float
        Total lever lift angle in degrees (default 8°, typical 8–12°).
    draw_deg : float
        Draw angle on locking faces in degrees (default 12°, typical 10–14°).
    escape_wheel_radius_mm : float
        Pitch-circle radius of the escape wheel (mm).
    lever_arm_mm : float
        Distance from pallet pivot to pallet stone impulse point (mm).
    escape_wheel_torque_Nmm : float
        Torque at the escape-wheel arbor (N·mm).

    Returns
    -------
    dict with keys:
        tooth_pitch_deg, half_lift_deg, impulse_face_angle_deg,
        entry_pallet_angle_deg, exit_pallet_angle_deg,
        drop_deg, impulse_force_at_balance_mN,
        energy_per_impulse_uJ, is_consistent, consistency_errors
    """
    g = swiss_lever_geometry(
        escape_teeth=escape_teeth,
        lift_deg=lift_deg,
        draw_deg=draw_deg,
        escape_wheel_radius_mm=escape_wheel_radius_mm,
        lever_arm_mm=lever_arm_mm,
        escape_wheel_torque_Nmm=escape_wheel_torque_Nmm,
    )
    return {
        "escape_teeth": g.escape_teeth,
        "lift_deg": round(g.lift_deg, 4),
        "draw_deg": round(g.draw_deg, 4),
        "tooth_pitch_deg": round(g.tooth_pitch_deg, 6),
        "half_lift_deg": round(g.half_lift_deg, 4),
        "impulse_face_angle_deg": round(g.impulse_face_angle_deg, 4),
        "entry_pallet_angle_deg": round(g.entry_pallet_angle_deg, 6),
        "exit_pallet_angle_deg": round(g.exit_pallet_angle_deg, 6),
        "drop_deg": round(g.drop_deg, 6),
        "impulse_force_at_balance_mN": round(g.impulse_force_at_balance_mN, 6),
        "energy_per_impulse_uJ": round(g.energy_per_impulse_uJ, 6),
        "is_consistent": g.is_consistent,
        "consistency_errors": g.consistency_errors,
    }


def _mainspring_torque_tool(
    turns: float,
    full_turns: float,
    max_torque_Nmm: float,
    residual_factor: float = 0.5,
) -> dict[str, Any]:
    """Return mainspring barrel torque at a given winding state.

    Parameters
    ----------
    turns : float
        Current winding state (0 = run down, full_turns = fully wound).
    full_turns : float
        Total barrel turns from run-down to fully wound.
    max_torque_Nmm : float
        Torque at full wind (N·mm).
    residual_factor : float
        Fraction of max_torque remaining at zero turns (default 0.5).

    Returns
    -------
    dict with keys:
        torque_Nmm (float): current torque
        turns_fraction (float): winding state fraction 0–1
    """
    torque = mainspring_torque(turns, full_turns, max_torque_Nmm, residual_factor)
    return {
        "torque_Nmm": round(torque, 6),
        "turns_fraction": round(max(0.0, min(1.0, turns / full_turns)), 6),
    }


def _power_reserve_tool(
    barrel_turns: float,
    escape_train_torque_required_Nmm: float,
    gear_ratio: float,
    beats_per_hour_val: int,
    full_turns: float,
    max_torque_Nmm: float,
    residual_factor: float = 0.5,
    escape_wheel_teeth: int = 15,
) -> dict[str, Any]:
    """Estimate usable power reserve in hours.

    Parameters
    ----------
    barrel_turns : float
        Winding state at start (= full_turns for fully wound spring).
    escape_train_torque_required_Nmm : float
        Minimum escape-wheel torque threshold (N·mm) at the escape wheel
        (after the gear train has divided down the barrel torque).
        Typical wristwatch escape wheel: 0.001–0.01 N·mm.
    gear_ratio : float
        Gear ratio barrel→escape-wheel (typically 3000–6000).
    beats_per_hour_val : int
        Beat rate (e.g. 28800 for ETA 2824-2).
    full_turns : float
        Mainspring full-wind turns.
    max_torque_Nmm : float
        Torque at full wind (N·mm).
    residual_factor : float
        Residual torque fraction (default 0.5).
    escape_wheel_teeth : int
        Number of teeth on the escape wheel (default 15).

    Returns
    -------
    dict with keys:
        power_reserve_hours (float)
    """
    reserve = power_reserve_hours(
        barrel_turns=barrel_turns,
        escape_train_torque_required_Nmm=escape_train_torque_required_Nmm,
        gear_ratio=gear_ratio,
        beats_per_hour=beats_per_hour_val,
        full_turns=full_turns,
        max_torque_Nmm=max_torque_Nmm,
        residual_factor=residual_factor,
        escape_wheel_teeth=escape_wheel_teeth,
    )
    return {"power_reserve_hours": round(reserve, 3)}


def _balance_period_tool(
    I_balance_gmm2: float,
    k_hairspring_Nmmrad: float,
) -> dict[str, Any]:
    """Compute balance-wheel oscillation period and beat rate.

    Parameters
    ----------
    I_balance_gmm2 : float
        Moment of inertia of the balance (g·mm²).
    k_hairspring_Nmmrad : float
        Hairspring torsional stiffness (N·mm/rad).

    Returns
    -------
    dict with keys:
        period_seconds (float): oscillation period
        bph (float): beat rate in beats per hour
    """
    T = balance_period(I_balance_gmm2, k_hairspring_Nmmrad)
    bph = beats_per_hour(T)
    return {
        "period_seconds": round(T, 8),
        "bph": round(bph, 3),
    }


def _isochronism_tool(
    I_balance_gmm2: float,
    k_hairspring_Nmmrad: float,
    amp_min_deg: float = 180.0,
    amp_max_deg: float = 300.0,
) -> dict[str, Any]:
    """Check isochronism of the balance-hairspring oscillator.

    Parameters
    ----------
    I_balance_gmm2 : float
        Balance moment of inertia (g·mm²).
    k_hairspring_Nmmrad : float
        Hairspring stiffness (N·mm/rad).
    amp_min_deg : float
        Minimum balance amplitude to test (degrees, default 180).
    amp_max_deg : float
        Maximum balance amplitude to test (degrees, default 300).

    Returns
    -------
    dict with keys:
        period_seconds, bph, delta_period_ms,
        rate_sensitivity_spd, is_isochronous, notes
    """
    result = isochronism_check(
        I_balance_gmm2=I_balance_gmm2,
        k_hairspring_Nmmrad=k_hairspring_Nmmrad,
        amplitude_range_deg=(amp_min_deg, amp_max_deg),
    )
    return {
        "period_seconds": round(result.period_at_min_amp, 8),
        "bph": round(beats_per_hour(result.period_at_min_amp), 3),
        "delta_period_ms": round(result.delta_period_ms, 6),
        "rate_sensitivity_spd": round(result.rate_sensitivity_spd, 6),
        "is_isochronous": result.is_isochronous,
        "notes": result.notes,
    }


# Registry-style tool definitions
TOOLS = [
    {
        "name": "train_calculator",
        "description": (
            "Compute the required gear-train ratio and barrel power storage "
            "for a mechanical watch movement given target frequency and "
            "power reserve."
        ),
        "fn": _train_calculator,
    },
    {
        "name": "check_tooth_profile",
        "description": (
            "Validate involute tooth profile geometry for a given module, "
            "tooth count, and pressure angle."
        ),
        "fn": _check_tooth_profile,
    },
    {
        "name": "escapement_geometry",
        "description": (
            "Compute Swiss lever escapement geometry: draw angle, lift angle, "
            "drop, impulse force and energy per beat, with self-consistency check."
        ),
        "fn": _escapement_geometry,
    },
    {
        "name": "mainspring_torque",
        "description": (
            "Return mainspring barrel torque (N·mm) at a given winding state "
            "using the linear torque model."
        ),
        "fn": _mainspring_torque_tool,
    },
    {
        "name": "power_reserve",
        "description": (
            "Estimate usable power reserve (hours) from mainspring parameters "
            "and gear-train ratio."
        ),
        "fn": _power_reserve_tool,
    },
    {
        "name": "balance_period",
        "description": (
            "Compute balance-wheel oscillation period (seconds) and beat rate "
            "(bph) from moment of inertia and hairspring stiffness."
        ),
        "fn": _balance_period_tool,
    },
    {
        "name": "isochronism",
        "description": (
            "Check isochronism of the balance-hairspring oscillator over an "
            "amplitude range, reporting period stability."
        ),
        "fn": _isochronism_tool,
    },
]
