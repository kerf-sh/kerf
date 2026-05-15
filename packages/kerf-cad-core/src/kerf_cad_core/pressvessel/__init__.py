"""
kerf_cad_core.pressvessel — ASME BPVC Section VIII Div.1 pressure-vessel sizing.

Distinct from kerf_cad_core.piping (ASME B31.3 process piping).

Public API (re-exported for convenience):

    from kerf_cad_core.pressvessel import (
        cylindrical_shell_thickness,
        spherical_head_thickness,
        ellipsoidal_head_thickness,
        torispherical_head_thickness,
        external_pressure_check,
        mawp_cylindrical,
        nozzle_reinforcement,
        hydrostatic_test_pressure,
    )

References
----------
ASME BPVC Section VIII Division 1, 2021 Edition
  UG-27  — Thickness of Shells under Internal Pressure
  UG-28  — Thickness of Shells and Tubes under External Pressure
  UG-32  — Formed Heads, and Sections, Pressure on Concave Side
  UG-37  — Reinforcement Required for Openings in Shells and Formed Heads
  UG-99  — Standard Hydrostatic Test
Megyesy, E.F. "Pressure Vessel Handbook", 14th ed.

Author: imranparuk
"""

from kerf_cad_core.pressvessel.shell import (
    cylindrical_shell_thickness,
    spherical_head_thickness,
    ellipsoidal_head_thickness,
    torispherical_head_thickness,
    external_pressure_check,
    mawp_cylindrical,
    nozzle_reinforcement,
    hydrostatic_test_pressure,
)

__all__ = [
    "cylindrical_shell_thickness",
    "spherical_head_thickness",
    "ellipsoidal_head_thickness",
    "torispherical_head_thickness",
    "external_pressure_check",
    "mawp_cylindrical",
    "nozzle_reinforcement",
    "hydrostatic_test_pressure",
]
