"""
kerf_cad_core.hydrology — Stormwater & drainage hydrology.

Distinct from civil.hydraulics (pressurised pipe networks); this module
covers rainfall-runoff, peak flow, time of concentration, IDF intensity,
detention-basin storage routing, and storm-sewer pipe sizing.

Public API (re-exported for convenience):

    from kerf_cad_core.hydrology import (
        rational_peak_flow,
        composite_runoff_coeff,
        scs_runoff_depth,
        scs_peak_flow,
        time_of_concentration,
        idf_intensity,
        detention_storage_modified_rational,
        storage_indication_route,
        storm_sewer_pipe_size,
    )

References
----------
ASCE/EWRI 45-05  — Rational Method for stormwater peak flow
TR-55 (USDA SCS 1986)  — Urban Hydrology for Small Watersheds
NRCS National Engineering Handbook Part 630 (NEH-630)
Chow, Maidment & Mays (1988) — Applied Hydrology

Author: imranparuk
"""

from kerf_cad_core.hydrology.runoff import (
    rational_peak_flow,
    composite_runoff_coeff,
    scs_runoff_depth,
    scs_peak_flow,
    time_of_concentration,
    idf_intensity,
    detention_storage_modified_rational,
    storage_indication_route,
    storm_sewer_pipe_size,
)

__all__ = [
    "rational_peak_flow",
    "composite_runoff_coeff",
    "scs_runoff_depth",
    "scs_peak_flow",
    "time_of_concentration",
    "idf_intensity",
    "detention_storage_modified_rational",
    "storage_indication_route",
    "storm_sewer_pipe_size",
]
