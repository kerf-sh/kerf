"""
kerf_cad_core.geotech — geotechnical and foundation engineering calculators.

Pure-Python module; no OCC dependency.  Distinct from civil/ submodules
(alignment = road geometry, hydraulics = open-channel/pipe flow).

Submodules
----------
foundation    — bearing capacity, settlement, earth pressure, retaining-wall
                stability, slope stability, pile capacity (pure Python / math only)
liquefaction  — seismic liquefaction triggering analysis: CSR (Seed & Idriss 1971),
                CRR from SPT (Youd et al. 2001), CRR from CPT (Robertson & Wride 1998),
                FS_L, post-triggering settlement (Tokimatsu & Seed 1987)
tools         — LLM tool wrappers registered with the Kerf tool registry
liq_tools     — LLM tool wrappers for liquefaction analysis

Public API (re-exported for convenience)
-----------------------------------------
    from kerf_cad_core.geotech import (
        bearing_capacity,
        settlement,
        lateral_earth_pressure,
        retaining_wall_stability,
        slope_stability_infinite,
        pile_axial_capacity,
        csr_seed_idriss,
        crr_from_spt,
        crr_from_cpt,
        liquefaction_safety_factor,
        post_triggering_settlement,
    )

References
----------
Das, B.M. "Principles of Geotechnical Engineering", 9th ed.
Bowles, J.E. "Foundation Analysis and Design", 5th ed.
Terzaghi, K. "Theoretical Soil Mechanics" (1943).
Meyerhof, G.G. "The Ultimate Bearing Capacity of Foundations" (1951).
Rankine, W.J.M. (1857); Coulomb, C.-A. (1776).
Seed, H.B. & Idriss, I.M. (1971). ASCE J. Soil Mech. Found. Div., 97(9).
Youd, T.L. et al. (2001). ASCE J. Geotech. Geoenviron. Eng., 127(10).
Robertson, P.K. & Wride, C.E. (1998). Can. Geotech. J., 35:442-459.
Tokimatsu, K. & Seed, H.B. (1987). ASCE J. Geotech. Eng., 113(8).

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.geotech.foundation import (
    bearing_capacity,
    settlement,
    lateral_earth_pressure,
    retaining_wall_stability,
    slope_stability_infinite,
    pile_axial_capacity,
)
from kerf_cad_core.geotech.liquefaction import (
    csr_seed_idriss,
    crr_from_spt,
    crr_from_cpt,
    liquefaction_safety_factor,
    post_triggering_settlement,
)

__all__ = [
    "bearing_capacity",
    "settlement",
    "lateral_earth_pressure",
    "retaining_wall_stability",
    "slope_stability_infinite",
    "pile_axial_capacity",
    "csr_seed_idriss",
    "crr_from_spt",
    "crr_from_cpt",
    "liquefaction_safety_factor",
    "post_triggering_settlement",
]
