"""
kerf_cad_core.concrete — ACI 318 reinforced-concrete design calculators.

Distinct from:
  struct/   — steel frame analysis (AISC)
  steelconn/ — steel connection design
  geotech/  — soil / foundation

Modules
-------
design              — core calculation functions (pure math, no external deps)
tools               — LLM tool wrappers (@register) for design functions
punching_torsion    — §22.6 punching shear + §22.7 torsion (SI and USC)
punching_torsion_tools — LLM tool wrappers for punching shear and torsion

Public re-exports for convenience::

    from kerf_cad_core.concrete import (
        beam_flexure,
        beam_required_As,
        beam_shear,
        tbeam_effective_flange,
        column_axial,
        column_pm_interaction,
        development_length,
        slab_one_way,
        immediate_deflection,
        crack_control,
        # punching shear (§22.6)
        critical_perimeter,
        two_way_concrete_shear_strength,
        punching_shear_check,
        # torsion (§22.7)
        cracking_torsion,
        torsion_capacity,
        combined_shear_torsion_check,
    )

Units: US-customary throughout (lb, in, kip, psi, ksi, ft) unless noted.
Punching/torsion functions accept ``metric`` kwarg (default True = SI).

References
----------
ACI 318-19 "Building Code Requirements for Structural Concrete"
McCormac, J.C. & Brown, R.H. "Design of Reinforced Concrete", 9th ed.
Wight, J.K. "Reinforced Concrete: Mechanics and Design", 8th ed.
Nilson, Darwin & Dolan "Design of Concrete Structures" 14th ed.

Author: imranparuk
"""

from kerf_cad_core.concrete.design import (
    beam_flexure,
    beam_required_As,
    beam_shear,
    tbeam_effective_flange,
    column_axial,
    column_pm_interaction,
    development_length,
    slab_one_way,
    immediate_deflection,
    crack_control,
)

from kerf_cad_core.concrete.punching_torsion import (
    critical_perimeter,
    two_way_concrete_shear_strength,
    punching_shear_check,
    cracking_torsion,
    torsion_capacity,
    combined_shear_torsion_check,
)

__all__ = [
    # design.py
    "beam_flexure",
    "beam_required_As",
    "beam_shear",
    "tbeam_effective_flange",
    "column_axial",
    "column_pm_interaction",
    "development_length",
    "slab_one_way",
    "immediate_deflection",
    "crack_control",
    # punching_torsion.py
    "critical_perimeter",
    "two_way_concrete_shear_strength",
    "punching_shear_check",
    "cracking_torsion",
    "torsion_capacity",
    "combined_shear_torsion_check",
]
