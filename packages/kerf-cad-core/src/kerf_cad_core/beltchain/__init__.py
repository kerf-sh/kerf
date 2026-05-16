"""
kerf_cad_core.beltchain — belt & chain power-transmission drive selection.

Distinct from gearbox/gearstrength/gears.py; covers flexible-element drives:

  V-belt drives (classical / narrow):
    design power, belt length & centre distance, wrap angle,
    number of belts, capstan tensions, shaft load.

  Timing / synchronous belts:
    pitch selection, teeth-in-mesh, belt width.

  Roller chain drives (ANSI/ISO):
    pitch selection, sprocket pitch diameter, chain length in pitches,
    service-factor corrected power, lubrication regime, safety factor.

Public API (re-exported for convenience):

    from kerf_cad_core.beltchain import (
        vbelt_design,
        timing_belt_design,
        chain_drive_design,
    )

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 17-1 to 17-12
Mott, R.L. "Machine Elements in Mechanical Design", 5th ed., Chs. 7 & 9
ANSI/RMA IP-20 — V-Belt Engineering Standard
ANSI/ASME B29.1 — Roller Chain Standard

Author: imranparuk
"""

from kerf_cad_core.beltchain.drives import (
    vbelt_design,
    timing_belt_design,
    chain_drive_design,
)

__all__ = [
    "vbelt_design",
    "timing_belt_design",
    "chain_drive_design",
]
