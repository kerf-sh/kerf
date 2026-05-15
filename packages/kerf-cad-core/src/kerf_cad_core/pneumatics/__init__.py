"""
kerf_cad_core.pneumatics — pneumatic (compressible-air) actuator & valve sizing.

Distinct from:
  kerf_cad_core.fluidpower — hydraulic (incompressible) fluid-power systems

This module covers industrial compressed-air / pneumatic systems:
cylinders, valves (ISO 6358 / Cv), receivers/tanks, FRL pressure drop,
blowdown/charge times, and air consumption.

Public API (re-exported for convenience):

    from kerf_cad_core.pneumatics import (
        cylinder,
        air_consumption,
        valve_flow_iso6358,
        valve_flow_cv,
        receiver_sizing,
        blowdown_time,
        charge_time,
        frl_pressure_drop,
    )

References
----------
ISO 6358-1:2013 — Pneumatic fluid power; Determination of flow-rate
  characteristics of components using compressible fluids
SMC Technical Data — Pneumatic Actuator Selection Guide
Parker Hannifin Pneumatics — P3E Actuator Catalogue
Festo Pneumatic Fundamentals (2nd ed.)
NFPA T3.21.3 — Cylinder force and speed calculations

Author: imranparuk
"""

from kerf_cad_core.pneumatics.circuit import (
    cylinder,
    air_consumption,
    valve_flow_iso6358,
    valve_flow_cv,
    receiver_sizing,
    blowdown_time,
    charge_time,
    frl_pressure_drop,
)

__all__ = [
    "cylinder",
    "air_consumption",
    "valve_flow_iso6358",
    "valve_flow_cv",
    "receiver_sizing",
    "blowdown_time",
    "charge_time",
    "frl_pressure_drop",
]
