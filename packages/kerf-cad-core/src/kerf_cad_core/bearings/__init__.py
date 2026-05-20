"""
kerf_cad_core.bearings — rolling-element bearing selection & life calculators.

Public API (re-exported for convenience):

    from kerf_cad_core.bearings import (
        bearing_rating_life,
        bearing_equivalent_load,
        bearing_adjusted_life,
        bearing_static_safety,
        bearing_required_capacity,
        bearing_limiting_speed,
        bearing_grease_interval,
        bearing_select,
    )

References
----------
ISO 281:2007 — Rolling bearings — Dynamic load ratings and rating life
ISO 76:2006  — Static load ratings
SKF Bearing Catalogue, 2018 edition (tables 1, 4, 5, A)
Shigley's Mechanical Engineering Design, 10th ed., Ch. 11

Author: imranparuk
"""

from kerf_cad_core.bearings.select import (
    bearing_rating_life,
    bearing_equivalent_load,
    bearing_adjusted_life,
    bearing_static_safety,
    bearing_required_capacity,
    bearing_limiting_speed,
    bearing_grease_interval,
    bearing_select,
)
from kerf_cad_core.bearings.housing import (
    bearing_housing_fit,
    bearing_shoulder_geometry,
)

__all__ = [
    "bearing_rating_life",
    "bearing_equivalent_load",
    "bearing_adjusted_life",
    "bearing_static_safety",
    "bearing_required_capacity",
    "bearing_limiting_speed",
    "bearing_grease_interval",
    "bearing_select",
    "bearing_housing_fit",
    "bearing_shoulder_geometry",
]
