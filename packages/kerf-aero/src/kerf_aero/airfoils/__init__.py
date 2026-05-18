"""
kerf_aero.airfoils — aerospace airfoil library.

Provides:
- NACA 4-digit analytic generator (:func:`naca4`)
- NACA 5-digit analytic generator (:func:`naca5`)
- Selig-format coordinate loader (:func:`selig_load`) with 40+ inline entries
- Airfoil catalogue registry (:data:`AIRFOIL_CATALOGUE`)
"""

from kerf_aero.airfoils.naca import naca4, naca5, parse_naca5
from kerf_aero.airfoils.selig import selig_load, SELIG_SLUGS
from kerf_aero.airfoils.database import (
    AIRFOIL_CATALOGUE,
    AirfoilEntry,
    get_entry,
    list_by_category,
)

__all__ = [
    # NACA generators
    "naca4",
    "naca5",
    "parse_naca5",
    # Selig loader
    "selig_load",
    "SELIG_SLUGS",
    # Catalogue
    "AIRFOIL_CATALOGUE",
    "AirfoilEntry",
    "get_entry",
    "list_by_category",
]
