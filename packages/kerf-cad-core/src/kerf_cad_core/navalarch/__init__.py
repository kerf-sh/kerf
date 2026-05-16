"""
kerf_cad_core.navalarch — hydrostatics & intact stability calculators.

Distinct from kerf_cad_core.marine (NURBS hull fairing): this module
performs hydrostatic calculations — displacement, form coefficients,
stability, trim, resistance — using pure Python (math module only).

Public API (re-exported for convenience):

    from kerf_cad_core.navalarch import (
        displacement_from_LBT,
        displacement_from_offsets,
        form_coefficients,
        waterplane_properties,
        vertical_centres,
        metacentric_height,
        righting_arm_GZ,
        tpc_mctc,
        free_surface_correction,
        resistance_admiralty,
        trim_from_moment,
    )

References
----------
Barras, C.B. "Ship Stability for Masters and Mates", 6th ed.
Rawson & Tupper, "Basic Ship Theory", 5th ed.
ITTC Resistance Committee recommendations.

Author: imranparuk
"""

from kerf_cad_core.navalarch.hydrostatics import (
    displacement_from_LBT,
    displacement_from_offsets,
    form_coefficients,
    waterplane_properties,
    vertical_centres,
    metacentric_height,
    righting_arm_GZ,
    tpc_mctc,
    free_surface_correction,
    resistance_admiralty,
    trim_from_moment,
)

__all__ = [
    "displacement_from_LBT",
    "displacement_from_offsets",
    "form_coefficients",
    "waterplane_properties",
    "vertical_centres",
    "metacentric_height",
    "righting_arm_GZ",
    "tpc_mctc",
    "free_surface_correction",
    "resistance_admiralty",
    "trim_from_moment",
]
