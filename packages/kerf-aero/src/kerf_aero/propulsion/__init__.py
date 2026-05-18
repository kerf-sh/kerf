"""
kerf_aero.propulsion — rocket-propulsion analysis toolkit.

Sub-modules
-----------
rocket_eq   Tsiolkovsky rocket equation, Isp / c* / thrust relationships.
nozzle      Rao bell-nozzle contour, isentropic-flow tables, area ratios.
cea_lite    Simplified chemical-equilibrium kernel for canonical bipropellants.
staging     Multi-stage ΔV budgets and optimal Δv-split optimisation.

All calculations use SI units internally unless stated otherwise.
"""

from kerf_aero.propulsion.rocket_eq import (
    delta_v,
    isp_from_cstar,
    thrust_from_mass_flow,
    effective_exhaust_velocity,
    mass_ratio_for_delta_v,
    propellant_mass,
)
from kerf_aero.propulsion.nozzle import (
    exit_mach_from_area_ratio,
    area_ratio_from_pressure_ratio,
    exit_mach_from_pressure_ratio,
    nozzle_exit_conditions,
    rao_bell_contour,
    thrust_coefficient,
)
from kerf_aero.propulsion.cea_lite import (
    cea_lite,
    PROPELLANT_PAIRS,
)
from kerf_aero.propulsion.staging import (
    multistage_delta_v,
    optimal_delta_v_split,
    stage_mass_ratio,
    gravity_loss_estimate,
)

__all__ = [
    # rocket_eq
    "delta_v",
    "isp_from_cstar",
    "thrust_from_mass_flow",
    "effective_exhaust_velocity",
    "mass_ratio_for_delta_v",
    "propellant_mass",
    # nozzle
    "exit_mach_from_area_ratio",
    "area_ratio_from_pressure_ratio",
    "exit_mach_from_pressure_ratio",
    "nozzle_exit_conditions",
    "rao_bell_contour",
    "thrust_coefficient",
    # cea_lite
    "cea_lite",
    "PROPELLANT_PAIRS",
    # staging
    "multistage_delta_v",
    "optimal_delta_v_split",
    "stage_mass_ratio",
    "gravity_loss_estimate",
]

__version__ = "0.1.0"
