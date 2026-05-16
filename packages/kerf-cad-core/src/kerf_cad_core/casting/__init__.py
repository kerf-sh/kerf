"""
kerf_cad_core.casting — metal sand/investment casting design calculators.

Public API (re-exported for convenience):

    from kerf_cad_core.casting import (
        shrinkage_allowance,
        draft_angle_volume,
        chvorinov_solidification,
        riser_size,
        gating_system,
        casting_yield,
        pouring_guidance,
    )

References
----------
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed., Ch. 11
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering and Technology", 7th ed.
Campbell, J. "Castings", 2nd ed.
AFS (American Foundry Society) — Gating and Risering manuals

Author: imranparuk
"""

from kerf_cad_core.casting.design import (
    shrinkage_allowance,
    draft_angle_volume,
    chvorinov_solidification,
    riser_size,
    gating_system,
    casting_yield,
    pouring_guidance,
)

__all__ = [
    "shrinkage_allowance",
    "draft_angle_volume",
    "chvorinov_solidification",
    "riser_size",
    "gating_system",
    "casting_yield",
    "pouring_guidance",
]
