"""
kerf_cad_core.firesafety — fire-protection engineering calculators.

Distinct from kerf_cad_core.hvac (HVAC duct sizing),
kerf_cad_core.buildingenergy (thermal loads),
kerf_cad_core.channel (open-channel hydraulics), and
kerf_cad_core.civil (civil/structural analysis).

Public API (re-exported for convenience):

    from kerf_cad_core.firesafety import (
        sprinkler_hydraulic_demand,
        fire_pump_sizing,
        water_supply_adequacy,
        egress_analysis,
        design_fire_tsquared,
        detector_activation_time,
        smoke_control_exhaust,
        fire_resistance_heat_transfer,
        required_fire_rating,
    )

References
----------
NFPA 13 (2022) — Standard for the Installation of Sprinkler Systems
NFPA 92 (2021) — Standard for Smoke Control Systems
NFPA 101 (2021) — Life Safety Code
SFPE Handbook of Fire Protection Engineering, 5th ed.
Hazen-Williams coefficient C for schedule-40 steel pipe

Author: imranparuk
"""

from kerf_cad_core.firesafety.fire import (
    sprinkler_hydraulic_demand,
    fire_pump_sizing,
    water_supply_adequacy,
    egress_analysis,
    design_fire_tsquared,
    detector_activation_time,
    smoke_control_exhaust,
    fire_resistance_heat_transfer,
    required_fire_rating,
)

__all__ = [
    "sprinkler_hydraulic_demand",
    "fire_pump_sizing",
    "water_supply_adequacy",
    "egress_analysis",
    "design_fire_tsquared",
    "detector_activation_time",
    "smoke_control_exhaust",
    "fire_resistance_heat_transfer",
    "required_fire_rating",
]
