"""
kerf_cad_core.plumbing — building plumbing & sanitary engineering calculators.

Distinct from:
  kerf_cad_core.civil.hydraulics  — pressurized network / pipe-network solver
  kerf_cad_core.piping            — process piping per ASME B31.3
  kerf_cad_core.hvac              — HVAC duct sizing
  kerf_cad_core.firesafety        — fire-protection water supply (NFPA 13/20)

Public API (re-exported for convenience):

    from kerf_cad_core.plumbing import (
        hunter_demand_gpm,
        size_supply_pipe,
        dfu_to_drain_size,
        vent_size,
        trap_arm_slope,
        drain_slope_manning,
        hot_water_heater_size,
        hw_recirculation_loop,
        storm_drain_leader,
        water_hammer_arrestor,
        expansion_tank_heater,
    )

References
----------
IPC (2021) — International Plumbing Code
UPC (2021) — Uniform Plumbing Code
Hunter, R.B. (1940) — Methods of Estimating Loads in Plumbing Systems (BMS 65)
ASHRAE Handbook — HVAC Applications (2019), Chapter 50: Service Water Heating
PDI (Plumbing & Drainage Institute) — Water Hammer Arrestor Sizing Guide WH-201

Author: imranparuk
"""

from kerf_cad_core.plumbing.design import (
    hunter_demand_gpm,
    size_supply_pipe,
    dfu_to_drain_size,
    vent_size,
    trap_arm_slope,
    drain_slope_manning,
    hot_water_heater_size,
    hw_recirculation_loop,
    storm_drain_leader,
    water_hammer_arrestor,
    expansion_tank_heater,
)

__all__ = [
    "hunter_demand_gpm",
    "size_supply_pipe",
    "dfu_to_drain_size",
    "vent_size",
    "trap_arm_slope",
    "drain_slope_manning",
    "hot_water_heater_size",
    "hw_recirculation_loop",
    "storm_drain_leader",
    "water_hammer_arrestor",
    "expansion_tank_heater",
]
