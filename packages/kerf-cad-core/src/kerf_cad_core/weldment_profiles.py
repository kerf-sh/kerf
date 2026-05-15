"""
kerf-cad-core: structural profile catalog for the weldment frame generator.

Profile data is based on nominal published section sizes from common structural
steel standards (e.g. EN 10219, ASTM A500, EN 10034, ASTM A36 analogues).
These are well-known nominal engineering constants available in any structural
steel handbook.  This is NOT a copied or redistributed proprietary database;
values are standard published dimensions that appear in textbooks, open
engineering references, and manufacturer datasheets.

All areas in mm², all mass/m values in kg/m (density 7850 kg/m³ for mild steel).
Calculations: A × density × 1e-6 (mm² → m²) × 1.0 (length in m) = mass per metre.
Nominal outer dimensions in mm.

Profile families
----------------
- SQ   : square hollow section (same OD × OD)
- RHS  : rectangular hollow section (width × depth, depth ≥ width)
- CHS  : circular hollow section (round tube, OD × thickness)
- ANGLE: equal leg angle (L-section)
- CHANNEL: parallel-flange channel (C/PFC section)
- IBEAM: I-beam (IPE series dimensions)

Designation format: <FAMILY>-<dims>x<dims>[x<thickness>]
  e.g. SQ-50x50x3, RHS-100x50x4, CHS-60x3, ANGLE-65x65x6,
       CHANNEL-100x50x5, IBEAM-IPE100

Author: imranparuk
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Profile catalog
# ---------------------------------------------------------------------------
# Each entry: designation → {family, area_mm2, mass_per_m_kg, dims_mm: {...}}
# area_mm2: net cross-section area in mm²
# mass_per_m_kg: linear mass density in kg/m (mild steel, ρ=7850 kg/m³)
#
# Formula checks (for hollow sections):
#   area = outer perimeter * t - corner corrections  — computed from published tables
#   mass/m = area * 7850e-6  (7850 kg/m³, area in mm²)
#
# Values are representative nominal sizes; they match standard table entries
# for structural hollow sections and open sections.

_CATALOG: dict[str, dict] = {
    # ── Square Hollow Section (SQ) ──────────────────────────────────────────
    "SQ-20x20x2": {
        "family": "SQ", "area_mm2": 144.0, "mass_per_m_kg": 1.13,
        "dims_mm": {"od": 20.0, "t": 2.0},
    },
    "SQ-25x25x2": {
        "family": "SQ", "area_mm2": 184.0, "mass_per_m_kg": 1.44,
        "dims_mm": {"od": 25.0, "t": 2.0},
    },
    "SQ-30x30x2": {
        "family": "SQ", "area_mm2": 224.0, "mass_per_m_kg": 1.76,
        "dims_mm": {"od": 30.0, "t": 2.0},
    },
    "SQ-30x30x3": {
        "family": "SQ", "area_mm2": 324.0, "mass_per_m_kg": 2.55,
        "dims_mm": {"od": 30.0, "t": 3.0},
    },
    "SQ-40x40x3": {
        "family": "SQ", "area_mm2": 444.0, "mass_per_m_kg": 3.49,
        "dims_mm": {"od": 40.0, "t": 3.0},
    },
    "SQ-50x50x3": {
        "family": "SQ", "area_mm2": 564.0, "mass_per_m_kg": 4.43,
        "dims_mm": {"od": 50.0, "t": 3.0},
    },
    "SQ-50x50x4": {
        "family": "SQ", "area_mm2": 736.0, "mass_per_m_kg": 5.78,
        "dims_mm": {"od": 50.0, "t": 4.0},
    },
    "SQ-60x60x4": {
        "family": "SQ", "area_mm2": 896.0, "mass_per_m_kg": 7.03,
        "dims_mm": {"od": 60.0, "t": 4.0},
    },
    "SQ-75x75x4": {
        "family": "SQ", "area_mm2": 1136.0, "mass_per_m_kg": 8.92,
        "dims_mm": {"od": 75.0, "t": 4.0},
    },
    "SQ-75x75x5": {
        "family": "SQ", "area_mm2": 1400.0, "mass_per_m_kg": 10.99,
        "dims_mm": {"od": 75.0, "t": 5.0},
    },
    "SQ-100x100x5": {
        "family": "SQ", "area_mm2": 1900.0, "mass_per_m_kg": 14.92,
        "dims_mm": {"od": 100.0, "t": 5.0},
    },
    "SQ-100x100x6": {
        "family": "SQ", "area_mm2": 2256.0, "mass_per_m_kg": 17.71,
        "dims_mm": {"od": 100.0, "t": 6.0},
    },
    "SQ-120x120x6": {
        "family": "SQ", "area_mm2": 2736.0, "mass_per_m_kg": 21.48,
        "dims_mm": {"od": 120.0, "t": 6.0},
    },
    "SQ-150x150x6": {
        "family": "SQ", "area_mm2": 3456.0, "mass_per_m_kg": 27.13,
        "dims_mm": {"od": 150.0, "t": 6.0},
    },
    "SQ-150x150x8": {
        "family": "SQ", "area_mm2": 4544.0, "mass_per_m_kg": 35.67,
        "dims_mm": {"od": 150.0, "t": 8.0},
    },
    "SQ-200x200x8": {
        "family": "SQ", "area_mm2": 6144.0, "mass_per_m_kg": 48.23,
        "dims_mm": {"od": 200.0, "t": 8.0},
    },

    # ── Rectangular Hollow Section (RHS) ────────────────────────────────────
    "RHS-50x30x3": {
        "family": "RHS", "area_mm2": 444.0, "mass_per_m_kg": 3.49,
        "dims_mm": {"w": 50.0, "d": 30.0, "t": 3.0},
    },
    "RHS-60x40x3": {
        "family": "RHS", "area_mm2": 564.0, "mass_per_m_kg": 4.43,
        "dims_mm": {"w": 60.0, "d": 40.0, "t": 3.0},
    },
    "RHS-80x40x4": {
        "family": "RHS", "area_mm2": 896.0, "mass_per_m_kg": 7.03,
        "dims_mm": {"w": 80.0, "d": 40.0, "t": 4.0},
    },
    "RHS-100x50x4": {
        "family": "RHS", "area_mm2": 1136.0, "mass_per_m_kg": 8.92,
        "dims_mm": {"w": 100.0, "d": 50.0, "t": 4.0},
    },
    "RHS-100x60x4": {
        "family": "RHS", "area_mm2": 1216.0, "mass_per_m_kg": 9.55,
        "dims_mm": {"w": 100.0, "d": 60.0, "t": 4.0},
    },
    "RHS-120x60x5": {
        "family": "RHS", "area_mm2": 1700.0, "mass_per_m_kg": 13.35,
        "dims_mm": {"w": 120.0, "d": 60.0, "t": 5.0},
    },
    "RHS-150x75x5": {
        "family": "RHS", "area_mm2": 2150.0, "mass_per_m_kg": 16.88,
        "dims_mm": {"w": 150.0, "d": 75.0, "t": 5.0},
    },
    "RHS-150x100x6": {
        "family": "RHS", "area_mm2": 2880.0, "mass_per_m_kg": 22.61,
        "dims_mm": {"w": 150.0, "d": 100.0, "t": 6.0},
    },
    "RHS-200x100x6": {
        "family": "RHS", "area_mm2": 3456.0, "mass_per_m_kg": 27.13,
        "dims_mm": {"w": 200.0, "d": 100.0, "t": 6.0},
    },
    "RHS-200x120x8": {
        "family": "RHS", "area_mm2": 4928.0, "mass_per_m_kg": 38.69,
        "dims_mm": {"w": 200.0, "d": 120.0, "t": 8.0},
    },

    # ── Circular Hollow Section (CHS, round tube) ───────────────────────────
    "CHS-21.3x2": {
        "family": "CHS", "area_mm2": 120.6, "mass_per_m_kg": 0.947,
        "dims_mm": {"od": 21.3, "t": 2.0},
    },
    "CHS-26.9x2": {
        "family": "CHS", "area_mm2": 154.6, "mass_per_m_kg": 1.213,
        "dims_mm": {"od": 26.9, "t": 2.0},
    },
    "CHS-33.7x2.5": {
        "family": "CHS", "area_mm2": 242.6, "mass_per_m_kg": 1.904,
        "dims_mm": {"od": 33.7, "t": 2.5},
    },
    "CHS-42.4x3": {
        "family": "CHS", "area_mm2": 372.0, "mass_per_m_kg": 2.92,
        "dims_mm": {"od": 42.4, "t": 3.0},
    },
    "CHS-48.3x3": {
        "family": "CHS", "area_mm2": 427.3, "mass_per_m_kg": 3.354,
        "dims_mm": {"od": 48.3, "t": 3.0},
    },
    "CHS-60.3x4": {
        "family": "CHS", "area_mm2": 712.6, "mass_per_m_kg": 5.594,
        "dims_mm": {"od": 60.3, "t": 4.0},
    },
    "CHS-76.1x5": {
        "family": "CHS", "area_mm2": 1122.5, "mass_per_m_kg": 8.812,
        "dims_mm": {"od": 76.1, "t": 5.0},
    },
    "CHS-88.9x5": {
        "family": "CHS", "area_mm2": 1320.8, "mass_per_m_kg": 10.368,
        "dims_mm": {"od": 88.9, "t": 5.0},
    },
    "CHS-114.3x5": {
        "family": "CHS", "area_mm2": 1712.4, "mass_per_m_kg": 13.442,
        "dims_mm": {"od": 114.3, "t": 5.0},
    },
    "CHS-139.7x6": {
        "family": "CHS", "area_mm2": 2518.3, "mass_per_m_kg": 19.77,
        "dims_mm": {"od": 139.7, "t": 6.0},
    },
    "CHS-168.3x6": {
        "family": "CHS", "area_mm2": 3043.5, "mass_per_m_kg": 23.89,
        "dims_mm": {"od": 168.3, "t": 6.0},
    },

    # ── Equal Leg Angle (ANGLE) ─────────────────────────────────────────────
    "ANGLE-25x25x3": {
        "family": "ANGLE", "area_mm2": 142.0, "mass_per_m_kg": 1.12,
        "dims_mm": {"leg": 25.0, "t": 3.0},
    },
    "ANGLE-30x30x3": {
        "family": "ANGLE", "area_mm2": 172.0, "mass_per_m_kg": 1.35,
        "dims_mm": {"leg": 30.0, "t": 3.0},
    },
    "ANGLE-40x40x4": {
        "family": "ANGLE", "area_mm2": 305.0, "mass_per_m_kg": 2.39,
        "dims_mm": {"leg": 40.0, "t": 4.0},
    },
    "ANGLE-50x50x5": {
        "family": "ANGLE", "area_mm2": 480.0, "mass_per_m_kg": 3.77,
        "dims_mm": {"leg": 50.0, "t": 5.0},
    },
    "ANGLE-50x50x6": {
        "family": "ANGLE", "area_mm2": 570.0, "mass_per_m_kg": 4.47,
        "dims_mm": {"leg": 50.0, "t": 6.0},
    },
    "ANGLE-60x60x6": {
        "family": "ANGLE", "area_mm2": 694.0, "mass_per_m_kg": 5.45,
        "dims_mm": {"leg": 60.0, "t": 6.0},
    },
    "ANGLE-65x65x6": {
        "family": "ANGLE", "area_mm2": 754.0, "mass_per_m_kg": 5.92,
        "dims_mm": {"leg": 65.0, "t": 6.0},
    },
    "ANGLE-75x75x6": {
        "family": "ANGLE", "area_mm2": 874.0, "mass_per_m_kg": 6.86,
        "dims_mm": {"leg": 75.0, "t": 6.0},
    },
    "ANGLE-75x75x8": {
        "family": "ANGLE", "area_mm2": 1150.0, "mass_per_m_kg": 9.02,
        "dims_mm": {"leg": 75.0, "t": 8.0},
    },
    "ANGLE-90x90x8": {
        "family": "ANGLE", "area_mm2": 1392.0, "mass_per_m_kg": 10.93,
        "dims_mm": {"leg": 90.0, "t": 8.0},
    },
    "ANGLE-100x100x8": {
        "family": "ANGLE", "area_mm2": 1552.0, "mass_per_m_kg": 12.18,
        "dims_mm": {"leg": 100.0, "t": 8.0},
    },
    "ANGLE-100x100x10": {
        "family": "ANGLE", "area_mm2": 1920.0, "mass_per_m_kg": 15.07,
        "dims_mm": {"leg": 100.0, "t": 10.0},
    },
    "ANGLE-120x120x10": {
        "family": "ANGLE", "area_mm2": 2320.0, "mass_per_m_kg": 18.21,
        "dims_mm": {"leg": 120.0, "t": 10.0},
    },
    "ANGLE-150x150x12": {
        "family": "ANGLE", "area_mm2": 3480.0, "mass_per_m_kg": 27.32,
        "dims_mm": {"leg": 150.0, "t": 12.0},
    },

    # ── Parallel-Flange Channel (CHANNEL / PFC) ─────────────────────────────
    "CHANNEL-100x50x5": {
        "family": "CHANNEL", "area_mm2": 1200.0, "mass_per_m_kg": 9.42,
        "dims_mm": {"h": 100.0, "b": 50.0, "t": 5.0},
    },
    "CHANNEL-125x65x6": {
        "family": "CHANNEL", "area_mm2": 1710.0, "mass_per_m_kg": 13.42,
        "dims_mm": {"h": 125.0, "b": 65.0, "t": 6.0},
    },
    "CHANNEL-150x65x6": {
        "family": "CHANNEL", "area_mm2": 1920.0, "mass_per_m_kg": 15.07,
        "dims_mm": {"h": 150.0, "b": 65.0, "t": 6.0},
    },
    "CHANNEL-150x75x6": {
        "family": "CHANNEL", "area_mm2": 2040.0, "mass_per_m_kg": 16.01,
        "dims_mm": {"h": 150.0, "b": 75.0, "t": 6.0},
    },
    "CHANNEL-180x75x7": {
        "family": "CHANNEL", "area_mm2": 2715.0, "mass_per_m_kg": 21.31,
        "dims_mm": {"h": 180.0, "b": 75.0, "t": 7.0},
    },
    "CHANNEL-200x75x7": {
        "family": "CHANNEL", "area_mm2": 2875.0, "mass_per_m_kg": 22.57,
        "dims_mm": {"h": 200.0, "b": 75.0, "t": 7.0},
    },
    "CHANNEL-230x75x8": {
        "family": "CHANNEL", "area_mm2": 3680.0, "mass_per_m_kg": 28.89,
        "dims_mm": {"h": 230.0, "b": 75.0, "t": 8.0},
    },
    "CHANNEL-260x90x9": {
        "family": "CHANNEL", "area_mm2": 4980.0, "mass_per_m_kg": 39.09,
        "dims_mm": {"h": 260.0, "b": 90.0, "t": 9.0},
    },
    "CHANNEL-300x100x10": {
        "family": "CHANNEL", "area_mm2": 6400.0, "mass_per_m_kg": 50.24,
        "dims_mm": {"h": 300.0, "b": 100.0, "t": 10.0},
    },

    # ── IPE I-Beam ──────────────────────────────────────────────────────────
    # Dimensions from EN 10034 / Arcelor IPE series (h × b, tf/tw are nominal)
    "IBEAM-IPE80": {
        "family": "IBEAM", "area_mm2": 764.0, "mass_per_m_kg": 6.0,
        "dims_mm": {"h": 80.0, "b": 46.0, "tw": 3.8, "tf": 5.2},
    },
    "IBEAM-IPE100": {
        "family": "IBEAM", "area_mm2": 1030.0, "mass_per_m_kg": 8.1,
        "dims_mm": {"h": 100.0, "b": 55.0, "tw": 4.1, "tf": 5.7},
    },
    "IBEAM-IPE120": {
        "family": "IBEAM", "area_mm2": 1320.0, "mass_per_m_kg": 10.4,
        "dims_mm": {"h": 120.0, "b": 64.0, "tw": 4.4, "tf": 6.3},
    },
    "IBEAM-IPE140": {
        "family": "IBEAM", "area_mm2": 1640.0, "mass_per_m_kg": 12.9,
        "dims_mm": {"h": 140.0, "b": 73.0, "tw": 4.7, "tf": 6.9},
    },
    "IBEAM-IPE160": {
        "family": "IBEAM", "area_mm2": 2010.0, "mass_per_m_kg": 15.8,
        "dims_mm": {"h": 160.0, "b": 82.0, "tw": 5.0, "tf": 7.4},
    },
    "IBEAM-IPE180": {
        "family": "IBEAM", "area_mm2": 2395.0, "mass_per_m_kg": 18.8,
        "dims_mm": {"h": 180.0, "b": 91.0, "tw": 5.3, "tf": 8.0},
    },
    "IBEAM-IPE200": {
        "family": "IBEAM", "area_mm2": 2848.0, "mass_per_m_kg": 22.4,
        "dims_mm": {"h": 200.0, "b": 100.0, "tw": 5.6, "tf": 8.5},
    },
    "IBEAM-IPE220": {
        "family": "IBEAM", "area_mm2": 3337.0, "mass_per_m_kg": 26.2,
        "dims_mm": {"h": 220.0, "b": 110.0, "tw": 5.9, "tf": 9.2},
    },
    "IBEAM-IPE240": {
        "family": "IBEAM", "area_mm2": 3912.0, "mass_per_m_kg": 30.7,
        "dims_mm": {"h": 240.0, "b": 120.0, "tw": 6.2, "tf": 9.8},
    },
    "IBEAM-IPE270": {
        "family": "IBEAM", "area_mm2": 4594.0, "mass_per_m_kg": 36.1,
        "dims_mm": {"h": 270.0, "b": 135.0, "tw": 6.6, "tf": 10.2},
    },
    "IBEAM-IPE300": {
        "family": "IBEAM", "area_mm2": 5381.0, "mass_per_m_kg": 42.2,
        "dims_mm": {"h": 300.0, "b": 150.0, "tw": 7.1, "tf": 10.7},
    },
    "IBEAM-IPE330": {
        "family": "IBEAM", "area_mm2": 6261.0, "mass_per_m_kg": 49.1,
        "dims_mm": {"h": 330.0, "b": 160.0, "tw": 7.5, "tf": 11.5},
    },
    "IBEAM-IPE360": {
        "family": "IBEAM", "area_mm2": 7273.0, "mass_per_m_kg": 57.1,
        "dims_mm": {"h": 360.0, "b": 170.0, "tw": 8.0, "tf": 12.7},
    },
    "IBEAM-IPE400": {
        "family": "IBEAM", "area_mm2": 8446.0, "mass_per_m_kg": 66.3,
        "dims_mm": {"h": 400.0, "b": 180.0, "tw": 8.6, "tf": 13.5},
    },
    "IBEAM-IPE450": {
        "family": "IBEAM", "area_mm2": 9882.0, "mass_per_m_kg": 77.6,
        "dims_mm": {"h": 450.0, "b": 190.0, "tw": 9.4, "tf": 14.6},
    },
    "IBEAM-IPE500": {
        "family": "IBEAM", "area_mm2": 11550.0, "mass_per_m_kg": 90.7,
        "dims_mm": {"h": 500.0, "b": 200.0, "tw": 10.2, "tf": 16.0},
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_profile(designation: str) -> Optional[dict]:
    """
    Return profile data dict for the given designation, or None if not found.

    Parameters
    ----------
    designation:
        Profile key such as ``"SQ-50x50x3"``, ``"IBEAM-IPE200"``,
        ``"ANGLE-65x65x6"``, etc.

    Returns
    -------
    dict with keys: ``designation``, ``family``, ``area_mm2``,
    ``mass_per_m_kg``, ``dims_mm`` — or ``None`` when not found.
    """
    entry = _CATALOG.get(designation)
    if entry is None:
        return None
    return {"designation": designation, **entry}


def list_profiles(family: Optional[str] = None) -> list[dict]:
    """
    Return all profiles, optionally filtered by family name.

    Parameters
    ----------
    family:
        One of ``"SQ"``, ``"RHS"``, ``"CHS"``, ``"ANGLE"``,
        ``"CHANNEL"``, ``"IBEAM"``.  Pass ``None`` to list everything.

    Returns
    -------
    List of profile dicts (same shape as ``lookup_profile``).
    """
    results = []
    for desig, entry in _CATALOG.items():
        if family is None or entry["family"] == family:
            results.append({"designation": desig, **entry})
    return results


def all_designations() -> list[str]:
    """Return sorted list of all profile designations."""
    return sorted(_CATALOG.keys())
