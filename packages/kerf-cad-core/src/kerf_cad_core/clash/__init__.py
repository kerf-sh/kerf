"""
kerf_cad_core.clash — Cross-discipline clash / interference detection.

Detects three categories of spatial conflict between component instances:

  hard        — bounding volumes or triangle meshes actually intersect
                (penetration depth > 0)
  clearance   — components are closer than a user-specified minimum gap
                (0 <= separation < min_clearance)
  coincident  — components share an identical bounding-box centre to
                within floating-point tolerance (duplicate placement)

Entry point
-----------
    from kerf_cad_core.clash import clash_detect
    result = clash_detect(components, min_clearance=1.0)

See detect.py for the full API.
"""

from kerf_cad_core.clash.detect import (
    ClashType,
    ClashRecord,
    ComponentShape,
    clash_detect,
)

__all__ = [
    "ClashType",
    "ClashRecord",
    "ComponentShape",
    "clash_detect",
]
