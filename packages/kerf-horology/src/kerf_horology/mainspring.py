"""Mainspring barrel torque physics.

The mainspring stores energy as a coiled flat spring inside the barrel.
Torque versus winding state is approximately linear (Hooke's law) over
the usable range, tapering off at near-full and near-empty states.

Public API
----------
mainspring_torque(turns, full_turns, max_torque_Nmm, residual_factor)
    → torque in N·mm at the given winding state.

power_reserve_hours(barrel_turns, escape_train_torque_required_Nmm,
                    gear_ratio, beats_per_hour,
                    full_turns, max_torque_Nmm, residual_factor)
    → usable hours of power reserve.
"""

from __future__ import annotations

import math


def mainspring_torque(
    turns: float,
    full_turns: float,
    max_torque_Nmm: float,
    residual_factor: float = 0.5,
) -> float:
    """Return mainspring torque (N·mm) at a given winding state.

    The torque model is linear between the wound and run-down states,
    with a small residual torque remaining at zero turns to represent the
    inner coil pre-tension (the spring never goes completely slack):

        T(n) = residual_torque + (max_torque - residual_torque) × (n / full_turns)

    where:
        residual_torque = residual_factor × max_torque

    Parameters
    ----------
    turns : float
        Current winding state in barrel turns (0 = fully run down,
        full_turns = fully wound).
    full_turns : float
        Number of barrel turns from fully run down to fully wound.
        Typical wristwatch mainspring: 5–8 turns.
    max_torque_Nmm : float
        Torque at full wind in N·mm.  Typical wristwatch: 3–8 N·mm at barrel.
    residual_factor : float
        Fraction of max_torque remaining at zero turns (default 0.5).
        A value of 0 means the torque reaches zero when fully run down.
        The standard Reymondin model uses ~0.5 (half torque at run-down).

    Returns
    -------
    float
        Torque in N·mm.  Clamped to [residual_torque, max_torque].

    Raises
    ------
    ValueError
        If full_turns ≤ 0, max_torque_Nmm ≤ 0, or residual_factor not in
        [0, 1).
    """
    if full_turns <= 0:
        raise ValueError(f"full_turns must be positive, got {full_turns}")
    if max_torque_Nmm <= 0:
        raise ValueError(f"max_torque_Nmm must be positive, got {max_torque_Nmm}")
    if not (0.0 <= residual_factor < 1.0):
        raise ValueError(
            f"residual_factor must be in [0, 1), got {residual_factor}"
        )

    residual_torque = residual_factor * max_torque_Nmm
    t_fraction = max(0.0, min(1.0, turns / full_turns))
    torque = residual_torque + (max_torque_Nmm - residual_torque) * t_fraction
    return torque


def power_reserve_hours(
    barrel_turns: float,
    escape_train_torque_required_Nmm: float,
    gear_ratio: float,
    beats_per_hour: int,
    full_turns: float,
    max_torque_Nmm: float,
    residual_factor: float = 0.5,
    escape_wheel_teeth: int = 15,
) -> float:
    """Estimate usable power reserve in hours.

    Integrates the linear torque curve to find the winding angle at which
    the barrel torque (divided by gear_ratio) drops below the minimum torque
    needed to drive the escapement.

    The gear train multiplies the barrel torque (reduces speed, increases
    torque at the escape wheel), so the condition is:

        T_barrel(n) / gear_ratio >= escape_train_torque_required_Nmm

    Wait — actually the gear ratio reduces speed from barrel to escape
    wheel, meaning the escape wheel sees *less* torque than the barrel
    (speed goes up, torque goes down through a conventional gear train
    from barrel outward).  However in horology convention, the *barrel*
    output torque is already the largest torque in the train, and the
    escape wheel receives a much smaller torque due to the large gear
    ratio reducing it.  So the correct condition is:

        T_barrel(n) / gear_ratio >= escape_train_torque_required_Nmm

    where escape_train_torque_required_Nmm is the escape-wheel torque
    threshold (e.g. 0.25 N·mm).

    Parameters
    ----------
    barrel_turns : float
        Total winding from fully run-down (= full_turns for a fully wound
        mainspring).
    escape_train_torque_required_Nmm : float
        Minimum escape-wheel torque to keep the escapement running (N·mm).
        At the escape wheel, after the gear train has divided the barrel torque
        by gear_ratio.  Typical wristwatch escape-wheel torque: 0.001–0.01 N·mm.
    gear_ratio : float
        Total gear ratio barrel→escape-wheel (dimensionless, > 1).
        Typical watch: 3000–6000.
    beats_per_hour : int
        Beat rate in beats/hour (e.g. 28800 for ETA 2824-2).
    full_turns : float
        Mainspring full-wind barrel turns.
    max_torque_Nmm : float
        Torque at full wind (N·mm).
    residual_factor : float
        Fraction of max_torque at run-down (default 0.5).
    escape_wheel_teeth : int
        Number of teeth on the escape wheel (default 15, Swiss standard).
        Used to compute the barrel angular velocity from beat rate.

    Returns
    -------
    float
        Usable power reserve in hours.  Returns 0.0 if even the full-wind
        torque is insufficient.

    Notes
    -----
    The calculation finds the turns threshold ``n_threshold`` below which
    the barrel torque / gear_ratio < required escapement torque:

        T_barrel(n) / gear_ratio = escape_train_torque_required_Nmm
        residual + (max - residual) × (n / full_turns) = required × gear_ratio
        n_threshold = full_turns × (required × gear_ratio - residual) /
                      (max - residual)

    Usable turns = barrel_turns - n_threshold  (clamped to [0, full_turns]).

    Barrel angular velocity (turns/hour):

        escape_wheel_turns_per_hour = beats_per_hour / (2 × escape_wheel_teeth)
        barrel_turns_per_hour = escape_wheel_turns_per_hour / gear_ratio
                               = beats_per_hour / (2 × escape_wheel_teeth × gear_ratio)

    Power reserve = usable_turns / barrel_turns_per_hour.

    Example (ETA 2824-2):
        bph=28800, escape_teeth=15, gear_ratio≈5612
        escape_turns/h = 28800/(2×15) = 960
        barrel_turns/h = 960/5612 ≈ 0.171
        with 6.5 usable turns → 6.5/0.171 ≈ 38h  ✓
    """
    if gear_ratio <= 0:
        raise ValueError(f"gear_ratio must be positive, got {gear_ratio}")
    if beats_per_hour <= 0:
        raise ValueError(f"beats_per_hour must be positive, got {beats_per_hour}")
    if escape_train_torque_required_Nmm <= 0:
        raise ValueError(
            "escape_train_torque_required_Nmm must be positive, "
            f"got {escape_train_torque_required_Nmm}"
        )
    if escape_wheel_teeth <= 0:
        raise ValueError(
            f"escape_wheel_teeth must be positive, got {escape_wheel_teeth}"
        )

    residual_torque = residual_factor * max_torque_Nmm

    # Minimum barrel torque needed to drive escapement
    # (escape_train_torque_required is at the escape wheel; barrel produces
    #  gear_ratio times more torque)
    min_barrel_torque = escape_train_torque_required_Nmm * gear_ratio

    # Check even fully wound torque is sufficient
    if max_torque_Nmm < min_barrel_torque:
        return 0.0

    # Find n_threshold: winding state where barrel torque = min_barrel_torque
    # T(n) = residual + (max - residual) × (n / full_turns) = min_barrel_torque
    # n = full_turns × (min_barrel_torque - residual) / (max - residual)
    if max_torque_Nmm > residual_torque:
        n_threshold = full_turns * (min_barrel_torque - residual_torque) / (
            max_torque_Nmm - residual_torque
        )
    else:
        # Flat torque curve — either always sufficient or never
        n_threshold = 0.0 if residual_torque >= min_barrel_torque else full_turns

    n_threshold = max(0.0, min(full_turns, n_threshold))
    usable_turns = max(0.0, barrel_turns - n_threshold)

    # Barrel turns per hour:
    #   escape_wheel_turns_per_hour = beats_per_hour / (2 × escape_wheel_teeth)
    #   barrel_turns_per_hour = escape_wheel_turns_per_hour / gear_ratio
    barrel_turns_per_hour = beats_per_hour / (
        2.0 * escape_wheel_teeth * gear_ratio
    )

    if barrel_turns_per_hour <= 0:
        return 0.0

    return usable_turns / barrel_turns_per_hour
