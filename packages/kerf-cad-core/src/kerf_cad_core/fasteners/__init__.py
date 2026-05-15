"""
kerf_cad_core.fasteners — bolted-joint analysis (VDI 2230 / Shigley style).

Covers the complete bolted-joint design workflow:

  preload_from_torque     — clamp force from tightening torque (T = K·F·d)
  bolt_stiffness          — bolt stiffness from shank + thread region geometry
  clamped_stiffness       — clamped-member stiffness via frustum (VDI 2230)
  joint_load_factor       — load factor Φ (fraction of working load carried by bolt)
  bolt_working_stress     — combined tensile + torsional stress in bolt shank
  separation_safety       — joint separation safety factor (no-gapping)
  slip_safety             — friction-grip slip safety factor
  fatigue_check           — alternating bolt stress vs endurance limit
  strip_length            — thread strip/pullout length check

All functions return plain dicts:
    success  → {"ok": True, ..., "warnings": [...]}
    failure  → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise — all errors are returned, all warnings are appended.

Units (SI throughout)
---------------------
  lengths  — metres (m)
  forces   — Newtons (N)
  stress   — Pascals (Pa)
  torque   — Newton-metres (N·m)
  moduli   — Pascals (Pa)

References
----------
VDI 2230-1:2015 — Systematic calculation of highly stressed bolted joints
Shigley's Mechanical Engineering Design, 10th ed., Chapter 8
ISO 68-1:1998   — ISO general-purpose metric screw threads

Author: imranparuk
"""

from kerf_cad_core.fasteners.joint import (
    preload_from_torque,
    bolt_stiffness,
    clamped_stiffness,
    joint_load_factor,
    bolt_working_stress,
    separation_safety,
    slip_safety,
    fatigue_check,
    strip_length,
    ISO_THREAD,
)

__all__ = [
    "preload_from_torque",
    "bolt_stiffness",
    "clamped_stiffness",
    "joint_load_factor",
    "bolt_working_stress",
    "separation_safety",
    "slip_safety",
    "fatigue_check",
    "strip_length",
    "ISO_THREAD",
]
