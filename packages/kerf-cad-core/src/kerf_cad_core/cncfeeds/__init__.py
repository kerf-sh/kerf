"""
kerf_cad_core.cncfeeds — machining feeds & speeds / cutting-parameter calculator.

Distinct from:
  turning/   — lathe cycle G-code generation
  cam_layered.py — milling toolpath computation

This module computes *cutting parameters* only: RPM, feed rates, material-removal
rates, cutting power & torque, forces, chip thinning, tool deflection, surface
finish, drilling thrust & torque, and tapping speed.  Pure Python; no OCC.

Public API (re-exported for convenience):

    from kerf_cad_core.cncfeeds import (
        spindle_rpm,
        feed_rate,
        mrr_milling,
        mrr_drilling,
        mrr_turning,
        cutting_power,
        tangential_force,
        chip_thinning_factor,
        corrected_chip_load,
        tool_deflection,
        surface_finish_ra,
        drill_thrust_torque,
        tapping_speed,
    )

References
----------
Machinery's Handbook, 30th ed.
SME Fundamentals of Tool Design, 6th ed.
Kennametal / Sandvik machining data handbooks

Author: imranparuk
"""

from kerf_cad_core.cncfeeds.calc import (
    spindle_rpm,
    feed_rate,
    mrr_milling,
    mrr_drilling,
    mrr_turning,
    cutting_power,
    tangential_force,
    chip_thinning_factor,
    corrected_chip_load,
    tool_deflection,
    surface_finish_ra,
    drill_thrust_torque,
    tapping_speed,
)

__all__ = [
    "spindle_rpm",
    "feed_rate",
    "mrr_milling",
    "mrr_drilling",
    "mrr_turning",
    "cutting_power",
    "tangential_force",
    "chip_thinning_factor",
    "corrected_chip_load",
    "tool_deflection",
    "surface_finish_ra",
    "drill_thrust_torque",
    "tapping_speed",
]
