"""
kerf_cad_core.solarpv — photovoltaic system sizing calculators.

Distinct from:
  - kerf_cad_core.heatxfer     (general heat transfer)
  - kerf_cad_core.thermocycle  (power/refrigeration cycles)
  - kerf-electronics powerconv (DC/DC, inverter circuit design)

Covers:
  Solar geometry (declination, hour angle, altitude, azimuth, sunrise/sunset,
  day length), plane-of-array irradiance (isotropic-sky transposition from
  GHI/DNI/DHI), optimal fixed tilt, array sizing, module string sizing,
  inverter DC/AC ratio, off-grid battery bank, cable sizing, energy yield,
  performance ratio, specific yield, and row spacing / shading.

Public API (re-exported for convenience):

    from kerf_cad_core.solarpv import (
        solar_declination,
        equation_of_time,
        solar_hour_angle,
        solar_position,
        sunrise_sunset,
        day_length,
        poa_irradiance,
        optimal_tilt,
        array_size,
        module_string_sizing,
        inverter_dc_ac_ratio,
        battery_bank,
        cable_sizing,
        energy_yield,
        row_spacing,
    )

References
----------
Duffie, J.A. & Beckman, W.A., "Solar Engineering of Thermal Processes", 4th ed.
Perez, R. et al. (1990) — All-weather model for sky luminance distribution.
Isotropic sky model — Liu & Jordan (1963).
IEC 60364-5-52 — Cable current-carrying capacity.
AS/NZS 4777.1 — Grid connection of energy systems via inverters.

Author: imranparuk
"""

from kerf_cad_core.solarpv.sizing import (
    solar_declination,
    equation_of_time,
    solar_hour_angle,
    solar_position,
    sunrise_sunset,
    day_length,
    poa_irradiance,
    optimal_tilt,
    array_size,
    module_string_sizing,
    inverter_dc_ac_ratio,
    battery_bank,
    cable_sizing,
    energy_yield,
    row_spacing,
)

__all__ = [
    "solar_declination",
    "equation_of_time",
    "solar_hour_angle",
    "solar_position",
    "sunrise_sunset",
    "day_length",
    "poa_irradiance",
    "optimal_tilt",
    "array_size",
    "module_string_sizing",
    "inverter_dc_ac_ratio",
    "battery_bank",
    "cable_sizing",
    "energy_yield",
    "row_spacing",
]
