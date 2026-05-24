"""
kerf_cad_core.buildingenergy — Building energy & daylighting analysis (pure Python).

Distinct from:
  kerf_cad_core.hvac      — duct sizing & airflow
  kerf_cad_core.psychro   — moist-air / psychrometric state
  kerf_cad_core.solarpv   — photovoltaic system sizing
  kerf_cad_core.heatxfer  — conduction/convection/radiation fundamentals

This module covers:
  • Envelope thermal performance  (U-value, R-value, thermal bridging)
  • Whole-building UA & heat-loss/gain coefficient
  • Balance-point temperature, degree-day (HDD/CDD) annual energy
  • Fuel/electric cost estimation
  • Design heating & cooling load (envelope + infiltration + ventilation + internal gains)
  • Infiltration ACH via blower-door and stack+wind (AIM-2/LBL)
  • Interstitial condensation check (Glaser dew-point method)
  • Solar heat gain (SHGC, incidence, shading projection factor)
  • Daylight factor, window-to-floor ratio, no-sky-line depth
  • Overheating-hours estimate
  • EUI & ASHRAE 90.1 envelope compliance

References
----------
ASHRAE Handbook — Fundamentals (2021)
ASHRAE 90.1-2022 — Energy Standard for Buildings
CIBSE Guide A (2015) — Environmental Design
ISO 6946:2017 — Building components thermal resistance and transmittance
Glaser, H. (1958) — interstitial condensation method
IECC 2021 — International Energy Conservation Code

Author: imranparuk
"""

from kerf_cad_core.buildingenergy.energy import (
    uvalue_series,
    uvalue_parallel,
    uvalue_bridged,
    whole_building_ua,
    balance_point_temperature,
    degree_day_energy,
    annual_fuel_cost,
    design_heating_load,
    design_cooling_load,
    infiltration_ach_blower_door,
    infiltration_ach_aim2,
    glaser_condensation,
    solar_heat_gain,
    shading_projection_factor,
    daylight_factor,
    window_to_floor_ratio,
    no_sky_line_depth,
    overheating_hours,
    eui,
    ashrae901_envelope_compliance,
)

from kerf_cad_core.buildingenergy.transient import (
    sol_air_temp,
    cltd_wall,
    cltd_roof,
    correct_cltd,
    wall_cooling_load,
    solar_heat_gain as solar_heat_gain_rts,
    cooling_load_fenestration_rts,
    zone_24h_cooling_load,
)

__all__ = [
    "uvalue_series",
    "uvalue_parallel",
    "uvalue_bridged",
    "whole_building_ua",
    "balance_point_temperature",
    "degree_day_energy",
    "annual_fuel_cost",
    "design_heating_load",
    "design_cooling_load",
    "infiltration_ach_blower_door",
    "infiltration_ach_aim2",
    "glaser_condensation",
    "solar_heat_gain",
    "shading_projection_factor",
    "daylight_factor",
    "window_to_floor_ratio",
    "no_sky_line_depth",
    "overheating_hours",
    "eui",
    "ashrae901_envelope_compliance",
    # transient
    "sol_air_temp",
    "cltd_wall",
    "cltd_roof",
    "correct_cltd",
    "wall_cooling_load",
    "solar_heat_gain_rts",
    "cooling_load_fenestration_rts",
    "zone_24h_cooling_load",
]
