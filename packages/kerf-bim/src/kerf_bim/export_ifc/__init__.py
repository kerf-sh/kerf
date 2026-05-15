"""
kerf_bim.export_ifc — .bim building model → IFC STEP-physical-file (Tier 1).

Public surface:
    export_ifc(model: dict, schema: str = "IFC2X3") -> IFCExportResult
    IFCExportResult, IFCExportError
"""
from kerf_bim.export_ifc.writer import export_ifc, IFCExportResult, IFCExportError

__all__ = [
    "export_ifc",
    "IFCExportResult",
    "IFCExportError",
]
