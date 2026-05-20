"""
kerf_electronics.harness3d — 3D in-vehicle wiring harness routing through the DMU.

Modules
-------
router      A* grid router for Manhattan-ish polyline routing through AABB obstacles
library     Automotive connector / bundle / segment library (≥ 20 standard parts)
formboard   3D harness → 2D flat-pattern + length table
report      Per-circuit length / gauge / voltage-drop report
"""

from kerf_electronics.harness3d.router import (
    AABB,
    HarnessEdge,
    RouteResult,
    route_harness_3d,
)
from kerf_electronics.harness3d.library import (
    ConnectorSpec,
    CONNECTOR_LIBRARY,
    lookup_connector,
)
from kerf_electronics.harness3d.formboard import (
    FormboardResult,
    flatten_harness,
)
from kerf_electronics.harness3d.report import (
    CircuitReport,
    HarnessReport,
    voltage_drop_report,
)

__all__ = [
    # router
    "AABB",
    "HarnessEdge",
    "RouteResult",
    "route_harness_3d",
    # library
    "ConnectorSpec",
    "CONNECTOR_LIBRARY",
    "lookup_connector",
    # formboard
    "FormboardResult",
    "flatten_harness",
    # report
    "CircuitReport",
    "HarnessReport",
    "voltage_drop_report",
]
