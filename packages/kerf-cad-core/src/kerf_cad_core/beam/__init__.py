"""
kerf_cad_core.beam — beam & cross-section analysis (pure Python).

Distinct from:
  kerf_cad_core.struct  — frame/truss structural analysis
  kerf_cad_core.fea     — finite-element analysis

Provides:
  section_properties  — area, centroid, Ix, Iy, Sx, Sy, plastic Z, r_g, J
  beam_loads          — deflection/slope/moment/shear for standard load cases
  superpose           — linear superposition combiner
  buckling            — Euler + Johnson short-column
  combined_stress     — axial + bending σ_combined
  mohr_circle         — principal stresses & max shear from σ, τ
  shear_flow          — VQ/It shear stress in a cross-section

Public API (re-exported for convenience):

    from kerf_cad_core.beam import (
        section_properties,
        beam_loads,
        superpose,
        buckling,
        combined_stress,
        mohr_circle,
        shear_flow,
    )

References
----------
Roark's Formulas for Stress and Strain, 8th ed. (Young & Budynas)
Hibbeler, Mechanics of Materials, 10th ed.
AISC Steel Construction Manual, 15th ed. — Johnson formula

Author: imranparuk
"""

from kerf_cad_core.beam.analysis import (
    section_properties,
    beam_loads,
    superpose,
    buckling,
    combined_stress,
    mohr_circle,
    shear_flow,
)

__all__ = [
    "section_properties",
    "beam_loads",
    "superpose",
    "buckling",
    "combined_stress",
    "mohr_circle",
    "shear_flow",
]
