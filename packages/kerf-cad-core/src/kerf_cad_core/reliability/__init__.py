"""
kerf_cad_core.reliability — systems reliability & risk analysis.

Pure-Python module (no OCC, no external numeric libraries).

Distinct from:
  fatigue/  — component fatigue life (S-N, Coffin-Manson)
  matsel/   — material selection

Public API (re-exported for convenience):

    from kerf_cad_core.reliability import (
        # Weibull distribution
        weibull_reliability,
        weibull_hazard,
        weibull_b_life,
        weibull_mttf,
        weibull_characteristic_life,
        weibull_fit,
        # Exponential distribution
        exponential_reliability,
        exponential_mtbf_ci,
        # System reliability
        system_series,
        system_parallel,
        system_k_out_of_n,
        system_bridge,
        availability,
        redundancy_gain,
        # Stress-strength interference
        stress_strength_normal,
        stress_strength_numeric,
        # FMEA
        fmea_rpn,
        fmea_criticality,
        # Fault tree
        fault_tree_top,
        fault_tree_cut_sets,
        fault_tree_importance,
        # Reliability allocation
        reliability_allocation_equal,
        reliability_allocation_agree,
        # Accelerated life
        arrhenius_af,
        inverse_power_af,
    )

References
----------
O'Connor & Kleyner, "Practical Reliability Engineering", 5th ed.
Tobias & Trindade, "Applied Reliability", 3rd ed.
MIL-HDBK-217F — Reliability Prediction of Electronic Equipment
IEEE Std 1633-2008 — Software Reliability

Author: imranparuk
"""

from kerf_cad_core.reliability.analysis import (
    weibull_reliability,
    weibull_hazard,
    weibull_b_life,
    weibull_mttf,
    weibull_characteristic_life,
    weibull_fit,
    exponential_reliability,
    exponential_mtbf_ci,
    system_series,
    system_parallel,
    system_k_out_of_n,
    system_bridge,
    availability,
    redundancy_gain,
    stress_strength_normal,
    stress_strength_numeric,
    fmea_rpn,
    fmea_criticality,
    fault_tree_top,
    fault_tree_cut_sets,
    fault_tree_importance,
    reliability_allocation_equal,
    reliability_allocation_agree,
    arrhenius_af,
    inverse_power_af,
)

__all__ = [
    "weibull_reliability",
    "weibull_hazard",
    "weibull_b_life",
    "weibull_mttf",
    "weibull_characteristic_life",
    "weibull_fit",
    "exponential_reliability",
    "exponential_mtbf_ci",
    "system_series",
    "system_parallel",
    "system_k_out_of_n",
    "system_bridge",
    "availability",
    "redundancy_gain",
    "stress_strength_normal",
    "stress_strength_numeric",
    "fmea_rpn",
    "fmea_criticality",
    "fault_tree_top",
    "fault_tree_cut_sets",
    "fault_tree_importance",
    "reliability_allocation_equal",
    "reliability_allocation_agree",
    "arrhenius_af",
    "inverse_power_af",
]
