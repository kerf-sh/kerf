"""
Raymer conceptual-sizing method — Chapter 6 of:

    Raymer D. P., "Aircraft Design: A Conceptual Approach," 6th ed. (2018).

The sizing loop iterates on gross take-off weight W_0 until the empty-weight
regression prediction is consistent with the fuel and payload fractions.

Algorithm summary
-----------------
1.  From the mission profile, compute the fuel fraction  W_f/W_0.
2.  Express the empty-weight fraction as a regression power law:
        W_e/W_0 = A · W_0^C   (Raymer Table 6.2, or user-supplied A, C)
3.  The weight equation is:
        W_0 = W_payload + W_crew + W_fuel + W_empty
            = W_payload + W_crew + (W_f/W_0)·W_0 + (W_e/W_0)·W_0
    rearranged:
        W_0 · [1 - W_f/W_0 - A·W_0^C] = W_payload + W_crew
4.  Solve for W_0 by fixed-point / bisection iteration.
5.  Derive wing area from wing loading W/S and thrust from T/W ratio.

Unit conventions
----------------
- Weights   : lbf
- Areas     : ft²
- Distances : nm (nautical miles)
- Speeds    : ktas (knots true airspeed)
- TSFC      : lbf_fuel / (lbf_thrust · hr)

References
----------
[R6.2]  Raymer, Table 6.2 — A, C regression coefficients by aircraft class.
[R6.3]  Raymer, §6.3    — Sizing to takeoff weight.
[R5.1]  Raymer, §5.1    — Statistical empty-weight fractions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TypedDict

from .mission_profile import MissionProfile


# ---------------------------------------------------------------------------
# Empty-weight regression coefficients (Raymer Table 6.2)
# Values: (A, C) where  W_e/W_0 = A * W_0^C
# ---------------------------------------------------------------------------

RAYMER_EMPTY_WEIGHT_COEFFICIENTS: dict[str, tuple[float, float]] = {
    # Aircraft class            : (A,      C)
    # Coefficients for  W_e/W_0 = A * W_0^C,  W_0 in lbf.
    # Fitted to published OEW/MTOW data unless marked [R6.2].
    "sailplane_unpowered":      (0.86,  -0.05),  # [R6.2] approx
    "sailplane_powered":        (0.91,  -0.05),  # [R6.2] approx
    "homebuilt_metal_wood":     (1.19,  -0.09),  # [R6.2]
    "homebuilt_composite":      (0.99,  -0.09),  # [R6.2]
    "general_aviation_single":  (2.36,  -0.18),  # [R6.2] Cessna/Piper class
    "general_aviation_twin":    (1.51,  -0.10),  # [R6.2]
    "agricultural":             (0.74,   0.03),  # [R6.2] approx
    "twin_turboprop":           (0.96,  -0.05),  # [R6.2]
    "flying_boat":              (1.09,  -0.05),  # [R6.2] approx
    "jet_trainer":              (1.59,  -0.10),  # [R6.2]
    "jet_fighter":              (2.34,  -0.13),  # [R6.2]
    "military_cargo_bomber":    (0.93,  -0.07),  # fitted: C-17/C-5 OEW/MTOW
    # jet_transport: A, C fitted to published OEW/MTOW for 737-800 (0.524 at
    # 174,200 lb) and 777-300ER (0.452 at 775,000 lb); gives ~0.53 at 150 klb.
    "jet_transport":            (1.731, -0.099),
}


@dataclass
class AircraftParams:
    """
    Design parameters for conceptual sizing.

    Parameters
    ----------
    payload_lb:
        Useful payload (passengers + cargo, etc.) in lb.
    crew_lb:
        Total crew weight in lb (included in useful load for some categories).
    wing_loading_lb_ft2:
        Design wing loading W/S in lb/ft².
    thrust_to_weight:
        Sea-level static T/W ratio (thrust-to-weight).
    aircraft_class:
        Key into ``RAYMER_EMPTY_WEIGHT_COEFFICIENTS``; ignored when ``A`` and
        ``C`` are supplied directly.
    A:
        Empty-weight regression coefficient A (overrides aircraft_class lookup).
    C:
        Empty-weight regression exponent C (overrides aircraft_class lookup).
    W0_guess_lb:
        Initial guess for TOGW in lb (default 5000).
    max_iterations:
        Maximum iterations for the fixed-point loop.
    tolerance:
        Convergence criterion on W_0 (lb).
    """

    payload_lb: float
    crew_lb: float
    wing_loading_lb_ft2: float
    thrust_to_weight: float
    aircraft_class: str = "general_aviation_single"
    A: float | None = None
    C: float | None = None
    W0_guess_lb: float = 5_000.0
    max_iterations: int = 200
    tolerance: float = 0.1  # lb


class SizingResult(TypedDict):
    """Output of :func:`size_aircraft`."""

    W_0: float          # Gross take-off weight, lb
    W_empty: float      # Empty weight, lb
    W_fuel: float       # Usable + trapped fuel, lb
    wing_area: float    # Reference wing area, ft²
    thrust: float       # Required sea-level static thrust, lbf


def _empty_weight_fraction(W0: float, A: float, C: float) -> float:
    """Raymer empty-weight regression: W_e/W_0 = A * W_0^C."""
    return A * (W0 ** C)


def size_aircraft(
    mission: MissionProfile,
    params: AircraftParams,
) -> SizingResult:
    """
    Iterate on gross take-off weight W_0 using the Raymer weight-fraction method.

    Algorithm
    ---------
    The weight equation is::

        W_0 = (W_payload + W_crew) / (1 - f_fuel - f_empty(W_0))

    where ``f_fuel = W_fuel/W_0`` comes from the mission profile and
    ``f_empty(W_0) = A * W_0^C`` is the statistical regression.

    We use a successive-substitution (fixed-point) loop, which converges for
    the majority of practical aircraft.  The loop starts from ``params.W0_guess_lb``
    and terminates when |ΔW_0| < ``params.tolerance``.

    Parameters
    ----------
    mission:
        A :class:`~kerf_aero.sizing.mission_profile.MissionProfile` instance
        defining the flight mission.
    params:
        An :class:`AircraftParams` instance with design requirements.

    Returns
    -------
    SizingResult
        Dictionary with keys: ``W_0``, ``W_empty``, ``W_fuel``,
        ``wing_area``, ``thrust``.

    Raises
    ------
    ValueError
        If the sizing loop fails to converge within ``params.max_iterations``.
    """
    # Resolve A, C
    if params.A is not None and params.C is not None:
        A, C = params.A, params.C
    else:
        if params.aircraft_class not in RAYMER_EMPTY_WEIGHT_COEFFICIENTS:
            raise ValueError(
                f"Unknown aircraft_class '{params.aircraft_class}'. "
                f"Available: {list(RAYMER_EMPTY_WEIGHT_COEFFICIENTS)}"
            )
        A, C = RAYMER_EMPTY_WEIGHT_COEFFICIENTS[params.aircraft_class]

    # Mission fuel fraction (includes trapped-fuel allowance)
    f_fuel = mission.fuel_fraction()

    W_fixed = params.payload_lb + params.crew_lb
    W0 = params.W0_guess_lb

    for _ in range(params.max_iterations):
        f_empty = _empty_weight_fraction(W0, A, C)
        denominator = 1.0 - f_fuel - f_empty
        if denominator <= 0.0:
            # Likely the guess is wildly off; nudge upward
            W0 *= 2.0
            continue
        W0_new = W_fixed / denominator
        if abs(W0_new - W0) < params.tolerance:
            W0 = W0_new
            break
        # Relaxation: blend to avoid oscillation
        W0 = 0.5 * W0 + 0.5 * W0_new
    else:
        raise ValueError(
            f"Raymer sizing loop did not converge after {params.max_iterations} "
            f"iterations (last W_0={W0:.1f} lb)."
        )

    f_empty_final = _empty_weight_fraction(W0, A, C)
    W_fuel = f_fuel * W0
    W_empty = f_empty_final * W0
    wing_area = W0 / params.wing_loading_lb_ft2
    thrust = params.thrust_to_weight * W0

    return SizingResult(
        W_0=W0,
        W_empty=W_empty,
        W_fuel=W_fuel,
        wing_area=wing_area,
        thrust=thrust,
    )


# ---------------------------------------------------------------------------
# Breguet helpers (standalone, for direct use / testing)
# ---------------------------------------------------------------------------


def breguet_range_fraction(
    range_nm: float,
    velocity_ktas: float,
    ld_ratio: float,
    tsfc: float,
) -> float:
    """
    Return the weight fraction W_end/W_start for a cruise segment.

    Breguet range equation (consistent units: nm, nm/hr, /hr)::

        W_end/W_start = exp(-R · c_j / (V · L/D))

    Parameters
    ----------
    range_nm:
        Cruise range in nautical miles.
    velocity_ktas:
        True airspeed in knots (= nm/hr).
    ld_ratio:
        Aerodynamic efficiency L/D.
    tsfc:
        Thrust-specific fuel consumption in lbf_fuel/(lbf_thrust·hr).

    Returns
    -------
    float
        Weight fraction W_end/W_start (< 1 for fuel-burning cruise).
    """
    return math.exp(-(range_nm * tsfc) / (velocity_ktas * ld_ratio))


def breguet_range_nm(
    W_start: float,
    W_end: float,
    velocity_ktas: float,
    ld_ratio: float,
    tsfc: float,
) -> float:
    """
    Return the cruise range in nautical miles given start/end weights.

    Inverse Breguet::

        R = (V · L/D / c_j) · ln(W_start / W_end)

    Parameters
    ----------
    W_start:
        Weight at start of cruise (any consistent weight unit).
    W_end:
        Weight at end of cruise.
    velocity_ktas:
        True airspeed in knots.
    ld_ratio:
        Lift-to-drag ratio.
    tsfc:
        TSFC in /hr.

    Returns
    -------
    float
        Range in nautical miles.
    """
    if W_end <= 0 or W_start <= W_end:
        raise ValueError("W_start must be greater than W_end > 0")
    return (velocity_ktas * ld_ratio / tsfc) * math.log(W_start / W_end)
