"""
kerf_cad_core.gearstrength — AGMA 2001 gear stress & rating (pure Python).

Distinct from:
  kerf_cad_core.gears       — tooth geometry / involute profiles
  kerf_cad_core.gearbox     — gear-train assembly / ratio / shaft table

This module implements the AGMA 2001-D04 strength / rating layer:

  rating.agma_bending_stress(...)   — AGMA bending stress σ_t (psi or MPa)
  rating.agma_contact_stress(...)   — AGMA contact (pitting) stress σ_c
  rating.agma_dynamic_factor(...)   — Dynamic factor Kv from quality number Qv
  rating.agma_geometry_factor_J(...)— Bending geometry factor J (spur/helical approx)
  rating.agma_geometry_factor_I(...)— Pitting geometry factor I
  rating.agma_safety_factors(...)   — SF (bending) and SH (contact) vs allowable
  rating.agma_power_rating(...)     — Max safe power/torque for a given gear set
  rating.agma_service_life(...)     — Stress-cycle factors YN / ZN & equivalent life

All functions return plain dicts:
    success → {"ok": True, ...}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise.

References
----------
AGMA 2001-D04 — Fundamental Rating Factors and Calculation Methods for
    Involute Spur and Helical Gear Teeth
Shigley's Mechanical Engineering Design, 10th ed., §§ 14-1 to 14-5

Author: imranparuk
"""

from kerf_cad_core.gearstrength.rating import (
    agma_bending_stress,
    agma_contact_stress,
    agma_dynamic_factor,
    agma_geometry_factor_J,
    agma_geometry_factor_I,
    agma_safety_factors,
    agma_power_rating,
    agma_service_life,
)

__all__ = [
    "agma_bending_stress",
    "agma_contact_stress",
    "agma_dynamic_factor",
    "agma_geometry_factor_J",
    "agma_geometry_factor_I",
    "agma_safety_factors",
    "agma_power_rating",
    "agma_service_life",
]
