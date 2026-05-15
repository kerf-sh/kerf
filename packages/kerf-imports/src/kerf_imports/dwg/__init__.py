"""
kerf_imports.dwg
================
DWG ingest bridge (T-8).

Converts .dwg files to DXF via an optional ``libredwg`` bridge, then
routes the result through the existing DXF reader + mapper pipeline.

Two bridge back-ends are tried in order:
  1. Python binding  — ``import libredwg``  (pip install libredwg)
  2. CLI subprocess  — ``dwgread`` binary on $PATH (from libredwg package)

If neither is available the bridge is *disabled*; callers receive a
friendly ``{ok: false, reason: "DWG bridge not available …"}`` result
rather than an exception.

Public API::

    from kerf_imports.dwg import convert_dwg_to_dxf, dwg_bridge_available

    if dwg_bridge_available():
        dxf_text = convert_dwg_to_dxf(dwg_bytes)
"""
from kerf_imports.dwg.bridge import (  # noqa: F401
    dwg_bridge_available,
    convert_dwg_to_dxf,
    DwgBridgeUnavailable,
    DwgConversionError,
)
