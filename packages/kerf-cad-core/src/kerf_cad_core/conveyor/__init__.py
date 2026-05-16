"""
kerf_cad_core.conveyor — bulk-material conveyor design calculators.

Distinct from kerf_cad_core.beltchain (V-belt/chain power transmission).
This module covers material-handling conveyors:

  Belt conveyor (CEMA-style troughed/flat):
    Volumetric and mass capacity, effective tension, drive power,
    slack-side tension, belt rating index, idler load, takeup tension,
    max inclination vs angle of repose.

  Screw conveyor (CEMA):
    Capacity, material/drive/incline power, shaft torque, fill ratio.

  Bucket elevator:
    Capacity, lift power, belt tension, motor sizing.

Public API (re-exported for convenience):

    from kerf_cad_core.conveyor import (
        belt_conveyor,
        screw_conveyor,
        bucket_elevator,
    )

References
----------
CEMA — Belt Conveyors for Bulk Materials, 7th ed.
CEMA — Screw Conveyors for Bulk Materials, 5th ed.
Fenner Dunlop — Conveyor Handbook, 2009

Author: imranparuk
"""

from kerf_cad_core.conveyor.design import (
    belt_conveyor,
    screw_conveyor,
    bucket_elevator,
)

__all__ = [
    "belt_conveyor",
    "screw_conveyor",
    "bucket_elevator",
]
