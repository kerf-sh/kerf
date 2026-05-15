"""
kerf_cad_core.vibration — mechanical vibration analysis.

Public API (re-exported for convenience):

    from kerf_cad_core.vibration import (
        sdof_natural_frequency,
        sdof_damped_frequency,
        sdof_damping_ratio_log_decrement,
        sdof_free_response,
        sdof_harmonic_magnification,
        sdof_harmonic_phase,
        sdof_base_transmissibility,
        sdof_rotating_unbalance,
        dof2_eigen,
        beam_natural_frequency,
        shaft_whirl_rayleigh,
        isolator_stiffness,
    )

Distinct from:
  - kinematics/  : linkage motion and cam follower geometry
  - fea/         : finite-element structural analysis

References
----------
Rao, S.S. "Mechanical Vibrations", 5th ed. (Pearson)
Inman, D.J. "Engineering Vibration", 4th ed. (Pearson)
Thomson, W.T. "Theory of Vibration with Applications", 5th ed.

Author: imranparuk
"""

from kerf_cad_core.vibration.dynamics import (
    sdof_natural_frequency,
    sdof_damped_frequency,
    sdof_damping_ratio_log_decrement,
    sdof_free_response,
    sdof_harmonic_magnification,
    sdof_harmonic_phase,
    sdof_base_transmissibility,
    sdof_rotating_unbalance,
    dof2_eigen,
    beam_natural_frequency,
    shaft_whirl_rayleigh,
    isolator_stiffness,
)

__all__ = [
    "sdof_natural_frequency",
    "sdof_damped_frequency",
    "sdof_damping_ratio_log_decrement",
    "sdof_free_response",
    "sdof_harmonic_magnification",
    "sdof_harmonic_phase",
    "sdof_base_transmissibility",
    "sdof_rotating_unbalance",
    "dof2_eigen",
    "beam_natural_frequency",
    "shaft_whirl_rayleigh",
    "isolator_stiffness",
]
