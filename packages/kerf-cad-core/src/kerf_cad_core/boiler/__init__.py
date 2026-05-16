"""
kerf_cad_core.boiler — steam & boiler plant engineering.

Distinct from thermocycle/ (Rankine cycle efficiency), combustion/ (fuels
chemistry), and heatxfer/ (surface heat transfer / HX sizing).

This module covers practical boiler plant calculations:

  Steam properties (IAPWS-IF97-style fitted correlations, 0.1 kPa–22 MPa)
  Boiler duty, steam output, and thermal efficiency (input-output & ASME PTC 4)
  Fuel firing rate and combustion air flow
  Blowdown rate (TDS / cycles-of-concentration) and heat loss
  Feedwater, deaerator, and economizer energy balances
  Equivalent evaporation and boiler horsepower
  Steam-pipe velocity and Darcy-Weisbach pressure drop
  Flash-steam fraction and condensate heat recovery
  Steam-trap orifice capacity
  Safety-valve relief capacity (Napier formula)

Public API (re-exported for convenience):

    from kerf_cad_core.boiler import (
        tsat_from_p, psat_from_t, steam_properties, superheat_h,
        boiler_heat_duty, boiler_steam_output,
        boiler_efficiency_io, boiler_efficiency_heat_loss,
        fuel_firing_rate, combustion_air_flow,
        blowdown_rate, blowdown_heat_loss,
        feedwater_energy_balance, deaerator_energy_balance,
        economizer_energy_balance,
        equivalent_evaporation, boiler_horsepower,
        steam_pipe_velocity, steam_pipe_pressure_drop,
        flash_steam_fraction, condensate_heat_recovery,
        steam_trap_capacity, safety_valve_napier,
    )

References
----------
ASME PTC 4-2013 — Fired Steam Generators Performance Test Codes
IAPWS-IF97 — International Association for Properties of Water and Steam
Spirax Sarco Steam Engineering Tutorials
API 520 Part I — Sizing, Selection and Installation of Pressure-Relieving Devices

Author: imranparuk
"""

from kerf_cad_core.boiler.plant import (
    tsat_from_p,
    psat_from_t,
    steam_properties,
    superheat_h,
    boiler_heat_duty,
    boiler_steam_output,
    boiler_efficiency_io,
    boiler_efficiency_heat_loss,
    fuel_firing_rate,
    combustion_air_flow,
    blowdown_rate,
    blowdown_heat_loss,
    feedwater_energy_balance,
    deaerator_energy_balance,
    economizer_energy_balance,
    equivalent_evaporation,
    boiler_horsepower,
    steam_pipe_velocity,
    steam_pipe_pressure_drop,
    flash_steam_fraction,
    condensate_heat_recovery,
    steam_trap_capacity,
    safety_valve_napier,
)

__all__ = [
    "tsat_from_p",
    "psat_from_t",
    "steam_properties",
    "superheat_h",
    "boiler_heat_duty",
    "boiler_steam_output",
    "boiler_efficiency_io",
    "boiler_efficiency_heat_loss",
    "fuel_firing_rate",
    "combustion_air_flow",
    "blowdown_rate",
    "blowdown_heat_loss",
    "feedwater_energy_balance",
    "deaerator_energy_balance",
    "economizer_energy_balance",
    "equivalent_evaporation",
    "boiler_horsepower",
    "steam_pipe_velocity",
    "steam_pipe_pressure_drop",
    "flash_steam_fraction",
    "condensate_heat_recovery",
    "steam_trap_capacity",
    "safety_valve_napier",
]
