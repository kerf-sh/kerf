"""
kerf_cad_core.pumpsys — centrifugal-pump & system-curve engineering.

Distinct from civil/hydraulics (pipe-network solver) and fluidpower/
(hydraulic actuators) — this module covers pump selection / operating point.

Public API (re-exported for convenience):

    from kerf_cad_core.pumpsys import (
        system_curve,
        system_K_from_pipe,
        pump_curve_from_points,
        operating_point,
        hydraulic_power,
        npsh_available,
        npsh_check,
        affinity_speed,
        affinity_trim,
        pumps_in_series,
        pumps_in_parallel,
        specific_speed,
        minimum_flow_note,
    )

References
----------
Kaplan, I. et al., "Pump Handbook", 4th ed., McGraw-Hill (2010).
White, F.M., "Fluid Mechanics", 8th ed., McGraw-Hill (2016).
HI (Hydraulic Institute) Standards.

Author: imranparuk
"""

from kerf_cad_core.pumpsys.curve import (
    system_curve,
    system_K_from_pipe,
    pump_curve_from_points,
    operating_point,
    hydraulic_power,
    npsh_available,
    npsh_check,
    affinity_speed,
    affinity_trim,
    pumps_in_series,
    pumps_in_parallel,
    specific_speed,
    minimum_flow_note,
)

__all__ = [
    "system_curve",
    "system_K_from_pipe",
    "pump_curve_from_points",
    "operating_point",
    "hydraulic_power",
    "npsh_available",
    "npsh_check",
    "affinity_speed",
    "affinity_trim",
    "pumps_in_series",
    "pumps_in_parallel",
    "specific_speed",
    "minimum_flow_note",
]
