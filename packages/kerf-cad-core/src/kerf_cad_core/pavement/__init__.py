"""
kerf_cad_core.pavement — highway & airfield pavement design.

Distinct from civil/alignment (road geometry), geotech/ (foundations),
and concrete/ (structural concrete).

Public API (re-exported for convenience):

    from kerf_cad_core.pavement import (
        aashto93_flexible_sn,
        aashto93_flexible_layers,
        esals_design,
        esal_growth_factor,
        load_equivalency_factor,
        cbr_to_mr,
        cbr_to_k,
        boussinesq_stress,
        aashto93_rigid_thickness,
        joint_spacing,
        dowel_bar_size,
        frost_penetration_depth,
        overlay_thickness_sn,
        asphalt_quantity,
    )

References
----------
AASHTO Guide for Design of Pavement Structures, 1993 (AASHTO '93)
PCA Design of Concrete Airport Pavement, 1955
Boussinesq (1885) point-load stress in elastic half-space

Author: imranparuk
"""

from kerf_cad_core.pavement.design import (
    aashto93_flexible_sn,
    aashto93_flexible_layers,
    esals_design,
    esal_growth_factor,
    load_equivalency_factor,
    cbr_to_mr,
    cbr_to_k,
    boussinesq_stress,
    aashto93_rigid_thickness,
    joint_spacing,
    dowel_bar_size,
    frost_penetration_depth,
    overlay_thickness_sn,
    asphalt_quantity,
)

__all__ = [
    "aashto93_flexible_sn",
    "aashto93_flexible_layers",
    "esals_design",
    "esal_growth_factor",
    "load_equivalency_factor",
    "cbr_to_mr",
    "cbr_to_k",
    "boussinesq_stress",
    "aashto93_rigid_thickness",
    "joint_spacing",
    "dowel_bar_size",
    "frost_penetration_depth",
    "overlay_thickness_sn",
    "asphalt_quantity",
]
