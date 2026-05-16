"""
kerf_cad_core.surveying — Land surveying computation / COGO.

Pure-Python traverse, coordinate geometry, and area math module.
Distinct from civil/alignment (road horizontal/vertical curves):
this module handles traverse/COGO/area computations.

Submodules:
  cogo  — bearing/azimuth, forward/inverse, traverse adjustment,
           area, intersections, resection, level-loop adjustment
  tools — LLM tool wrappers registered with the Kerf tool registry

Public API (re-exported for convenience):

    from kerf_cad_core.surveying import (
        dms_to_dd,
        dd_to_dms,
        bearing_to_azimuth,
        azimuth_to_bearing,
        forward,
        inverse,
        traverse_misclosure,
        traverse_adjust,
        area_by_coordinates,
        area_by_dmd,
        line_line_intersection,
        line_circle_intersection,
        point_of_intersection,
        resection,
        level_loop_adjust,
    )

References
----------
Surveying (Bannister, Raymond, Baker) — 7th ed.
Wolf & Ghilani, "Elementary Surveying" — 14th ed.
Bureau of Land Management "Manual of Surveying Instructions" — 2009

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.surveying.cogo import (
    dms_to_dd,
    dd_to_dms,
    bearing_to_azimuth,
    azimuth_to_bearing,
    forward,
    inverse,
    traverse_misclosure,
    traverse_adjust,
    area_by_coordinates,
    area_by_dmd,
    line_line_intersection,
    line_circle_intersection,
    point_of_intersection,
    resection,
    level_loop_adjust,
)

__all__ = [
    "dms_to_dd",
    "dd_to_dms",
    "bearing_to_azimuth",
    "azimuth_to_bearing",
    "forward",
    "inverse",
    "traverse_misclosure",
    "traverse_adjust",
    "area_by_coordinates",
    "area_by_dmd",
    "line_line_intersection",
    "line_circle_intersection",
    "point_of_intersection",
    "resection",
    "level_loop_adjust",
]
