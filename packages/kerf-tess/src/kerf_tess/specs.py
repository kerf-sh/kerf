"""
Tessellation I/O specs shared between the HTTP route and the background worker.

TessInputSpec / TessResult mirror the shape used in backend/workers/tess_worker.py
so that callers can import from a single stable location without a backend dependency.
"""

from __future__ import annotations

from typing import Optional


class TessInputSpec:
    def __init__(
        self,
        resolution: int = 50000,
        export_format: str = "glb",
        scale: float = 1.0,
    ):
        self.resolution = resolution
        self.export_format = export_format
        self.scale = scale

    @classmethod
    def from_dict(cls, d: dict) -> "TessInputSpec":
        return cls(
            resolution=d.get("resolution", 50000),
            export_format=d.get("export_format", "glb"),
            scale=float(d.get("scale", 1.0)),
        )

    def to_dict(self) -> dict:
        return {
            "resolution": self.resolution,
            "export_format": self.export_format,
            "scale": self.scale,
        }


class TessResult:
    def __init__(
        self,
        output_key: str = "",
        warnings: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        self.output_key = output_key
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dict(self) -> dict:
        return {
            "output_key": self.output_key,
            "warnings": self.warnings,
            "errors": self.errors,
        }
