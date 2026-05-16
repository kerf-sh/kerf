"""
kerf_cad_core.ergonomics — human-factors / ergonomics engineering calculators.

Public API (re-exported for convenience):

    from kerf_cad_core.ergonomics import (
        anthropometric_percentile,
        design_for_range,
        niosh_rwl,
        lifting_index,
        snook_push_pull,
        grip_strength_percentile,
        pinch_strength_percentile,
        rula_score,
        reba_score,
        workstation_heights,
        visual_angle,
        min_character_size,
        metabolic_expenditure,
        rest_allowance,
        reach_envelope,
    )

References
----------
NIOSH (1994) — Revised NIOSH Lifting Equation (Applications Manual)
Waters et al. (1993) — Revised NIOSH Equation for the Design and Evaluation of
    Manual Lifting Tasks.  Ergonomics 36(7):749-776.
Snook & Ciriello (1991) — The design of manual handling tasks: revised tables
    of maximum acceptable weights and forces.  Ergonomics 34(9):1197-1213.
McAtamney & Corlett (1993) — RULA: a survey method for the investigation of
    work-related upper limb disorders.  Applied Ergonomics 24(2):91-99.
Hignett & McAtamney (2000) — Rapid Entire Body Assessment (REBA).
    Applied Ergonomics 31(2):201-205.
NASA-STD-3001 — Human Integration Design Handbook (HIDH), Vol. 1 & 2.
ANSI/HFES 100-2007 — Human Factors Engineering of Computer Workstations.
Kroemer & Grandjean — Fitting the Task to the Human, 5th ed.
Chaffin, Andersson, Martin — Occupational Biomechanics, 4th ed.

Author: imranparuk
"""

from kerf_cad_core.ergonomics.human import (
    anthropometric_percentile,
    design_for_range,
    niosh_rwl,
    lifting_index,
    snook_push_pull,
    grip_strength_percentile,
    pinch_strength_percentile,
    rula_score,
    reba_score,
    workstation_heights,
    visual_angle,
    min_character_size,
    metabolic_expenditure,
    rest_allowance,
    reach_envelope,
)

__all__ = [
    "anthropometric_percentile",
    "design_for_range",
    "niosh_rwl",
    "lifting_index",
    "snook_push_pull",
    "grip_strength_percentile",
    "pinch_strength_percentile",
    "rula_score",
    "reba_score",
    "workstation_heights",
    "visual_angle",
    "min_character_size",
    "metabolic_expenditure",
    "rest_allowance",
    "reach_envelope",
]
