"""
kerf_cad_core.aero — applied aerodynamics calculators.

Distinct from fluidpower/, pumpsys/, pneumatics/, hvac/.
Covers atmosphere, airfoil/wing performance, drag buildup, flight mechanics,
propulsion (actuator disc / propeller), and range/endurance (Breguet).

Public API (re-exported for convenience):

    from kerf_cad_core.aero import (
        isa_atmosphere,
        dynamic_pressure,
        reynolds_number,
        mach_number,
        prandtl_glauert_factor,
        thin_airfoil_cl,
        thin_airfoil_cm,
        finite_wing_lift_slope,
        finite_wing_cl,
        induced_drag_coefficient,
        total_drag_coefficient,
        ld_ratio,
        best_glide_cl,
        level_flight_thrust,
        level_flight_power,
        stall_speed,
        climb_rate,
        actuator_disc_thrust,
        propeller_ideal_efficiency,
        breguet_range,
        breguet_endurance,
    )

References
----------
Anderson, J.D. — Introduction to Flight, 8th ed.
Anderson, J.D. — Fundamentals of Aerodynamics, 6th ed.
ICAO Doc 7488 — Manual of the ICAO Standard Atmosphere, 3rd ed.

Author: imranparuk
"""

from kerf_cad_core.aero.flow import (
    isa_atmosphere,
    dynamic_pressure,
    reynolds_number,
    mach_number,
    prandtl_glauert_factor,
    thin_airfoil_cl,
    thin_airfoil_cm,
    finite_wing_lift_slope,
    finite_wing_cl,
    induced_drag_coefficient,
    total_drag_coefficient,
    ld_ratio,
    best_glide_cl,
    level_flight_thrust,
    level_flight_power,
    stall_speed,
    climb_rate,
    actuator_disc_thrust,
    propeller_ideal_efficiency,
    breguet_range,
    breguet_endurance,
)

__all__ = [
    "isa_atmosphere",
    "dynamic_pressure",
    "reynolds_number",
    "mach_number",
    "prandtl_glauert_factor",
    "thin_airfoil_cl",
    "thin_airfoil_cm",
    "finite_wing_lift_slope",
    "finite_wing_cl",
    "induced_drag_coefficient",
    "total_drag_coefficient",
    "ld_ratio",
    "best_glide_cl",
    "level_flight_thrust",
    "level_flight_power",
    "stall_speed",
    "climb_rate",
    "actuator_disc_thrust",
    "propeller_ideal_efficiency",
    "breguet_range",
    "breguet_endurance",
]
