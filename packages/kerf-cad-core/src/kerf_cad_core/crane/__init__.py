"""
kerf_cad_core.crane — crane & hoist mechanism design calculators.

Distinct from rigging/ (slings, CG, lift plans) and beam/ and steelconn/.
This module covers the crane machinery itself: wire-rope hoists, reeving,
drives, motors, jib/gantry geometry, wheel loads, hook & lug design,
and FEM/ISO duty classification.

Public API (re-exported for convenience):

    from kerf_cad_core.crane import (
        wire_rope_reeving,
        rope_diameter,
        sheave_drum_geometry,
        drum_length,
        hoist_motor_power,
        hoist_motor_class,
        hoist_brake_torque,
        travel_resistance,
        travel_motor_power,
        jib_load_chart,
        bridge_wheel_loads,
        hook_shank_check,
        lifting_lug_check,
        crane_duty_class,
        fall_protection_brake,
    )

References
----------
FEM 1.001 Rules for the Design of Hoisting Appliances (4th ed.)
ISO 4301-1:2016 — Cranes — Classification — General
DIN 15400 — Lifting hooks — Grades, materials, mechanical properties
ASME B30.2 — Overhead and Gantry Cranes
AS 1418 — Cranes, hoists and winches

Author: imranparuk
"""

from kerf_cad_core.crane.design import (
    wire_rope_reeving,
    rope_diameter,
    sheave_drum_geometry,
    drum_length,
    hoist_motor_power,
    hoist_motor_class,
    hoist_brake_torque,
    travel_resistance,
    travel_motor_power,
    jib_load_chart,
    bridge_wheel_loads,
    hook_shank_check,
    lifting_lug_check,
    crane_duty_class,
    fall_protection_brake,
)

__all__ = [
    "wire_rope_reeving",
    "rope_diameter",
    "sheave_drum_geometry",
    "drum_length",
    "hoist_motor_power",
    "hoist_motor_class",
    "hoist_brake_torque",
    "travel_resistance",
    "travel_motor_power",
    "jib_load_chart",
    "bridge_wheel_loads",
    "hook_shank_check",
    "lifting_lug_check",
    "crane_duty_class",
    "fall_protection_brake",
]
