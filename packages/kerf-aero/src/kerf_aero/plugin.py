"""kerf-aero plugin entry-point.

Pure-library plugin today (aerodynamics, propulsion, orbital mechanics).
HTTP routes for aero are mounted by the kerf-api plugin which imports
kerf_aero submodules directly. This plugin only declares its presence so
the loader records `kerf-aero` in the manifest.
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="aero",
            version="0.1.0",
            provides=["aero.aerodynamics", "aero.propulsion", "aero.orbital"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "aero",
            "version": "0.1.0",
            "provides": ["aero.aerodynamics", "aero.propulsion", "aero.orbital"],
            "depends": [],
        }
