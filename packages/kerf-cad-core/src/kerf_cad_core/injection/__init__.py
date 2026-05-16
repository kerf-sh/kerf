"""
kerf_cad_core.injection — plastic injection-moulding process design.

Distinct from ``kerf_cad_core.casting`` (metal sand/investment casting).

Public API (re-exported for convenience):

    from kerf_cad_core.injection import (
        polymer_properties,
        clamp_tonnage,
        shot_volume_weight,
        gate_runner_sizing,
        cooling_time,
        flow_length_feasibility,
        shrinkage_sink_estimate,
        cycle_time_breakdown,
        cavities_from_tonnage,
        draft_ejection_force,
    )

References
----------
Rosato, D.V. & Rosato, M.G. "Injection Moulding Handbook", 3rd ed.
Brydson, J.A. "Plastics Materials", 7th ed.
Menges, G. et al. "How to Make Injection Molds", 3rd ed.

Author: imranparuk
"""

from kerf_cad_core.injection.process import (
    polymer_properties,
    clamp_tonnage,
    shot_volume_weight,
    gate_runner_sizing,
    cooling_time,
    flow_length_feasibility,
    shrinkage_sink_estimate,
    cycle_time_breakdown,
    cavities_from_tonnage,
    draft_ejection_force,
)

__all__ = [
    "polymer_properties",
    "clamp_tonnage",
    "shot_volume_weight",
    "gate_runner_sizing",
    "cooling_time",
    "flow_length_feasibility",
    "shrinkage_sink_estimate",
    "cycle_time_breakdown",
    "cavities_from_tonnage",
    "draft_ejection_force",
]
