"""
kerf_cad_core.welding — weld PROCESS engineering.

Covers heat input, preheat, consumables, deposition, and distortion.

Distinct from:
  steelconn/  — structural joint *capacity* (AISC shear/tension/bearing)
  weldment.py — geometric weld bead / weldment *modelling*

Public API (re-exported for convenience):

    from kerf_cad_core.welding import (
        arc_heat_input,
        carbon_equivalent_iiw,
        preheat_temperature,
        cooling_time_t85,
        fillet_weld_volume,
        groove_weld_volume,
        deposition_time,
        electrode_consumption,
        number_of_passes,
        angular_distortion,
        longitudinal_distortion,
        interpass_temperature_check,
    )

References
----------
AWS D1.1/D1.1M:2020 — Structural Welding Code (Steel)
IIW Doc. IXJ-123-85 — Carbon equivalent formula
Yurioka N. et al. (1983) — Preheat and cold-cracking susceptibility
Lincoln Electric "The Procedure Handbook of Arc Welding", 14th ed.
Radaj D. — Heat Effects of Welding, Springer, 1992

Author: imranparuk
"""

from kerf_cad_core.welding.process import (
    arc_heat_input,
    carbon_equivalent_iiw,
    preheat_temperature,
    cooling_time_t85,
    fillet_weld_volume,
    groove_weld_volume,
    deposition_time,
    electrode_consumption,
    number_of_passes,
    angular_distortion,
    longitudinal_distortion,
    interpass_temperature_check,
)

__all__ = [
    "arc_heat_input",
    "carbon_equivalent_iiw",
    "preheat_temperature",
    "cooling_time_t85",
    "fillet_weld_volume",
    "groove_weld_volume",
    "deposition_time",
    "electrode_consumption",
    "number_of_passes",
    "angular_distortion",
    "longitudinal_distortion",
    "interpass_temperature_check",
]
