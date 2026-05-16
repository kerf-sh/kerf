"""
kerf_cad_core.psychro — ASHRAE psychrometrics & HVAC load calculations.

Distinct from hvac/ (duct sizing) and thermocycle/ (power/refrigeration cycles).
Covers moist-air properties, state-point solving, load formulas, cooling-coil
analysis, evaporative cooling, and altitude pressure correction.

Public API (re-exported for convenience):

    from kerf_cad_core.psychro import (
        sat_pressure,
        altitude_pressure,
        humidity_ratio_from_rh,
        humidity_ratio_from_twb,
        relative_humidity,
        dew_point,
        wet_bulb,
        enthalpy,
        enthalpy_ip,
        specific_volume,
        state_point,
        mix_air_streams,
        sensible_load_ip,
        latent_load_ip,
        total_load_ip,
        coil_adp,
        coil_leaving_conditions,
        evaporative_cooling,
    )

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapter 1: Psychrometrics
Hyland, R.W. & Wexler, A. (1983) ASHRAE Trans. 89(2A):500-519

Author: imranparuk
"""

from kerf_cad_core.psychro.air import (
    sat_pressure,
    altitude_pressure,
    humidity_ratio_from_rh,
    humidity_ratio_from_twb,
    relative_humidity,
    dew_point,
    wet_bulb,
    enthalpy,
    enthalpy_ip,
    specific_volume,
    state_point,
    mix_air_streams,
    sensible_load_ip,
    latent_load_ip,
    total_load_ip,
    coil_adp,
    coil_leaving_conditions,
    evaporative_cooling,
)

__all__ = [
    "sat_pressure",
    "altitude_pressure",
    "humidity_ratio_from_rh",
    "humidity_ratio_from_twb",
    "relative_humidity",
    "dew_point",
    "wet_bulb",
    "enthalpy",
    "enthalpy_ip",
    "specific_volume",
    "state_point",
    "mix_air_streams",
    "sensible_load_ip",
    "latent_load_ip",
    "total_load_ip",
    "coil_adp",
    "coil_leaving_conditions",
    "evaporative_cooling",
]
