"""
kerf_cad_core.clutchbrake — friction clutch & brake design calculators.

Public API (re-exported for convenience):

    from kerf_cad_core.clutchbrake import (
        disc_clutch_torque,
        cone_clutch_torque,
        band_brake_torque,
        drum_brake_torque,
        disc_brake_torque,
        engagement_energy,
        temperature_rise,
        heat_dissipation_area,
        wear_pv_check,
        engagement_time,
        friction_material_props,
    )

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 16-1 to 16-12
Juvinall & Marshek, Fundamentals of Machine Component Design, 5th ed., §§ 18.1-18.9
Norton, Machine Design, 5th ed., Chapter 16

Author: imranparuk
"""

from kerf_cad_core.clutchbrake.design import (
    disc_clutch_torque,
    cone_clutch_torque,
    band_brake_torque,
    drum_brake_torque,
    disc_brake_torque,
    engagement_energy,
    temperature_rise,
    heat_dissipation_area,
    wear_pv_check,
    engagement_time,
    friction_material_props,
)

__all__ = [
    "disc_clutch_torque",
    "cone_clutch_torque",
    "band_brake_torque",
    "drum_brake_torque",
    "disc_brake_torque",
    "engagement_energy",
    "temperature_rise",
    "heat_dissipation_area",
    "wear_pv_check",
    "engagement_time",
    "friction_material_props",
]
