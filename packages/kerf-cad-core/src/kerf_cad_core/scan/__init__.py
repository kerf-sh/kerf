"""
kerf_cad_core.scan — Scan-to-CAD point-cloud ingestion and primitive fitting.

Sub-modules:
    fit    — plane, sphere, cylinder fitting via RANSAC + closed-form solvers
    tools  — LLM tool wrappers (scan_load, scan_fit_plane, scan_fit_sphere,
              scan_fit_cylinder, scan_segment)

Author: imranparuk
"""
from __future__ import annotations
