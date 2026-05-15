"""
kerf_cad_core.turning — lathe / turning CAM: canned cycles + G-code post.

Public API (re-exported for convenience):

    from kerf_cad_core.turning import (
        roughing_passes,
        finishing_pass,
        facing_pass,
        parting_pass,
        od_threading,
        id_threading,
        grooving_pass,
        cutting_params,
        emit_gcode,
    )

Coordinate convention
---------------------
All profiles use (Z, X) pairs where:
  Z — axial position along the lathe axis, measured from the chuck face
      (positive towards tailstock, mm).
  X — radius (not diameter), mm; must be >= 0.

References
----------
ISO 6983-1:2009 — Numerical control of machines — Part 1: general
Machinery's Handbook, 30th ed., §§ Turning, Threading

Author: imranparuk
"""

from kerf_cad_core.turning.cycles import (
    roughing_passes,
    finishing_pass,
    facing_pass,
    parting_pass,
    od_threading,
    id_threading,
    grooving_pass,
    cutting_params,
    emit_gcode,
    TurningResult,
)

__all__ = [
    "roughing_passes",
    "finishing_pass",
    "facing_pass",
    "parting_pass",
    "od_threading",
    "id_threading",
    "grooving_pass",
    "cutting_params",
    "emit_gcode",
    "TurningResult",
]
