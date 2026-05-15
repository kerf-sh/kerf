"""
kerf_cad_core.steelconn — structural-steel connection design (bolted & welded).

Distinct from:
  struct/   — member sizing (columns, beams, section catalog)
  weldment/ — 3-D weldment geometry modeling

This sub-package covers *connection* capacity design per AISC 360:

  Bolted connections
  ------------------
  bolt_shear_capacity        — nominal bolt shear strength (single/double shear)
  bolt_bearing_capacity      — bearing strength on connected material
  bolt_tension_capacity      — nominal bolt tension strength
  slip_critical_capacity     — Class A/B slip-critical capacity
  block_shear_capacity       — block shear rupture (AISC J4.3)
  bolt_group_eccentric       — eccentric bolt group (Instantaneous Center + Elastic)

  Welded connections
  ------------------
  fillet_weld_capacity       — fillet weld group capacity (throat × length × Fexx)
  weld_group_elastic_vector  — elastic vector method for weld group with eccentricity
  electrode_strength         — tabulated Fexx for common electrode classifications

  Base-plate connection
  ---------------------
  base_plate_bearing         — bearing check for column base plate on grout/concrete

Public API
----------
All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; overstress is flagged through warnings, not exceptions.

References
----------
AISC 360-22 — Specification for Structural Steel Buildings (LRFD + ASD)
AISC Steel Construction Manual, 16th ed.
McCormac & Csernak, Structural Steel Design, 6th ed.

Author: imranparuk
"""

from kerf_cad_core.steelconn.connections import (
    bolt_shear_capacity,
    bolt_bearing_capacity,
    bolt_tension_capacity,
    slip_critical_capacity,
    block_shear_capacity,
    bolt_group_eccentric,
    fillet_weld_capacity,
    weld_group_elastic_vector,
    electrode_strength,
    base_plate_bearing,
)

__all__ = [
    "bolt_shear_capacity",
    "bolt_bearing_capacity",
    "bolt_tension_capacity",
    "slip_critical_capacity",
    "block_shear_capacity",
    "bolt_group_eccentric",
    "fillet_weld_capacity",
    "weld_group_elastic_vector",
    "electrode_strength",
    "base_plate_bearing",
]
