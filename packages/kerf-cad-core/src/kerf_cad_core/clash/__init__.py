"""
kerf_cad_core.clash — Cross-discipline clash / interference detection.

Detects three categories of spatial conflict between component instances:

  hard        — bounding volumes or triangle meshes actually intersect
                (penetration depth > 0)
  clearance   — components are closer than a user-specified minimum gap
                (0 <= separation < min_clearance)
  coincident  — components share an identical bounding-box centre to
                within floating-point tolerance (duplicate placement)

Discipline support
------------------
Each ComponentShape accepts an optional ``discipline`` tag (e.g. "structural",
"mep", "architectural", "civil", "mechanical", "electrical").  The
clash_detect output includes a ``by_discipline_pair`` summary keyed by
canonical pair strings like "architectural vs mep".

Entry points
------------
    from kerf_cad_core.clash import clash_detect, ClashReport
    result = clash_detect(components, min_clearance=1.0)
    report = ClashReport(result)
    struct_vs_mep = report.clashes_for_pair("structural", "mep")

See detect.py for the full API.
"""

from kerf_cad_core.clash.detect import (
    ClashType,
    ClashRecord,
    ClashReport,
    ComponentShape,
    clash_detect,
)

__all__ = [
    "ClashType",
    "ClashRecord",
    "ClashReport",
    "ComponentShape",
    "clash_detect",
]
