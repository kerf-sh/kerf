"""
kerf_cad_core.windload — ASCE 7 wind loading on structures.

Public API (re-exported for convenience):

    from kerf_cad_core.windload import (
        velocity_pressure_exposure_Kz,
        topographic_factor_Kzt,
        ground_elevation_factor_Ke,
        velocity_pressure_qz,
        gust_effect_factor_G,
        gust_effect_factor_Gf,
        mwfrs_wall_pressure,
        mwfrs_roof_pressure,
        components_cladding_GCp,
        base_shear_overturning,
        along_wind_drift,
    )

Scope: structural wind loading per ASCE 7-22 Chapters 26–27.
Distinct from kerf_cad_core.aero (flight aerodynamics) and
kerf_cad_core.hvac (duct pressure calculations).

References
----------
ASCE/SEI 7-22 — Minimum Design Loads and Associated Criteria for Buildings
and Other Structures (Chapters 26–27, C27, 30)

Author: imranparuk
"""

from kerf_cad_core.windload.asce7 import (
    velocity_pressure_exposure_Kz,
    topographic_factor_Kzt,
    ground_elevation_factor_Ke,
    velocity_pressure_qz,
    gust_effect_factor_G,
    gust_effect_factor_Gf,
    mwfrs_wall_pressure,
    mwfrs_roof_pressure,
    components_cladding_GCp,
    base_shear_overturning,
    along_wind_drift,
)

__all__ = [
    "velocity_pressure_exposure_Kz",
    "topographic_factor_Kzt",
    "ground_elevation_factor_Ke",
    "velocity_pressure_qz",
    "gust_effect_factor_G",
    "gust_effect_factor_Gf",
    "mwfrs_wall_pressure",
    "mwfrs_roof_pressure",
    "components_cladding_GCp",
    "base_shear_overturning",
    "along_wind_drift",
]
