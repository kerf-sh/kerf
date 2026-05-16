"""
kerf_cad_core.packaging — protective-packaging & shipping design.

Distinct from nesting/ (2D cut nesting) and costing/.

Public API (re-exported for convenience):

    from kerf_cad_core.packaging import (
        box_compression_strength,
        pallet_pattern,
        shipping_weight,
        cushion_design,
        shock_transmissibility,
        container_fill,
        stretch_wrap,
    )

References
----------
McKee, R.C. (1963) — Box Compression: A Simple Formula.
TAPPI T804 — Compression Test of Fiberboard Shipping Containers.
ASTM D1596 — Shock-Absorbing Characteristics of Packaging Material.
ISTA 2A/2B — Packaged-Product Performance Testing.
EUMOS 40509 — Test Method for Unitised Loads; Containment Force.
NMFC Item 360 — Freight Classification by Density.
ISO 668:2020 — Series 1 Freight Containers — Classification.

Author: imranparuk
"""

from kerf_cad_core.packaging.design import (
    box_compression_strength,
    pallet_pattern,
    shipping_weight,
    cushion_design,
    shock_transmissibility,
    container_fill,
    stretch_wrap,
)

__all__ = [
    "box_compression_strength",
    "pallet_pattern",
    "shipping_weight",
    "cushion_design",
    "shock_transmissibility",
    "container_fill",
    "stretch_wrap",
]
