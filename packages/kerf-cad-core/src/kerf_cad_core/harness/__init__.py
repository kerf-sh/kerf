"""
kerf_cad_core.harness — 3D wiring harness routing primitive.

Route wiring harnesses in 3D through via-points and bundles.  Pure-Python,
no OCC dependency.

Submodules:
  route  — Catmull-Rom / arc-blend path smoothing, bundle geometry, BOM
  tools  — LLM tool wrappers registered with the Kerf tool registry

Units: metres (m), millimetres (mm) for wire gauge ODs.

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.harness.route import (
    Vec3,
    Segment,
    Branch,
    HarnessPath,
    route_harness,
    bundle_diameter,
    harness_bom,
    WireSpec,
    BomEntry,
    BomResult,
)

__all__ = [
    "Vec3",
    "Segment",
    "Branch",
    "HarnessPath",
    "route_harness",
    "bundle_diameter",
    "harness_bom",
    "WireSpec",
    "BomEntry",
    "BomResult",
]
