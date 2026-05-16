"""
kerf_cad_core.windturbine — wind-turbine power & rotor sizing calculators.

Distinct from:
  - kerf_cad_core.aero          (aircraft aerodynamics, lift/drag, propulsion)
  - kerf_cad_core.solarpv       (photovoltaic system sizing)
  - kerf_cad_core.hydroturbine  (hydraulic turbines, Francis/Pelton/Kaplan)
  - kerf_cad_core.turbo         (gas/steam turbomachinery, compressors)

Covers:
  Available wind power (P = ½·ρ·A·V³), Betz limit (Cp_max = 16/27),
  rotor diameter from rated power & Cp, tip-speed ratio & rotor speed,
  gearbox ratio from generator RPM, thrust & overturning moment,
  blade-element-momentum simplified (annulus a/a′ iteration → Cp),
  Weibull/Rayleigh wind speed distribution → AEP & capacity factor,
  power-curve model (cut-in/rated/cut-out, cubic ramp),
  air-density correction (altitude + temperature), Jensen single-wake model,
  sound-power vs distance (logarithmic), tower-shadow note,
  generator sizing from rated electrical output.

Public API (re-exported for convenience):

    from kerf_cad_core.windturbine import (
        available_power,
        betz_limit,
        rotor_diameter,
        rotor_speed,
        gearbox_ratio,
        thrust_force,
        overturning_moment,
        blade_element_momentum,
        weibull_aep,
        rayleigh_aep,
        power_curve,
        air_density,
        jensen_wake,
        sound_pressure_distance,
        capacity_factor,
    )

References
----------
Burton, T. et al., "Wind Energy Handbook", 2nd ed., Wiley (2011).
Betz, A. (1920) — momentum theory maximum Cp = 16/27.
Jensen, N.O. (1983) — wake decay model.
IEC 61400-1:2019 — Wind turbine design requirements.

Author: imranparuk
"""

from kerf_cad_core.windturbine.rotor import (
    available_power,
    betz_limit,
    rotor_diameter,
    rotor_speed,
    gearbox_ratio,
    thrust_force,
    overturning_moment,
    blade_element_momentum,
    weibull_aep,
    rayleigh_aep,
    power_curve,
    air_density,
    jensen_wake,
    sound_pressure_distance,
    capacity_factor,
)

__all__ = [
    "available_power",
    "betz_limit",
    "rotor_diameter",
    "rotor_speed",
    "gearbox_ratio",
    "thrust_force",
    "overturning_moment",
    "blade_element_momentum",
    "weibull_aep",
    "rayleigh_aep",
    "power_curve",
    "air_density",
    "jensen_wake",
    "sound_pressure_distance",
    "capacity_factor",
]
