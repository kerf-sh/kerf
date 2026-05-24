"""
kerf-marine plugin entry-point.

Registers:
  - LLM tools: marine_hydrostatics, marine_box_barge, marine_stability_gz
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_marine.tools import (
        marine_hydrostatics_spec, run_marine_hydrostatics,
        marine_box_barge_spec, run_marine_box_barge,
        marine_stability_gz_spec, run_marine_stability_gz,
    )
    from kerf_marine.holtrop_mennen import (
        holtrop_mennen_spec, run_holtrop_mennen,
    )
    ctx.tools.register(
        "marine_hydrostatics",
        marine_hydrostatics_spec,
        run_marine_hydrostatics,
    )
    ctx.tools.register(
        "marine_box_barge",
        marine_box_barge_spec,
        run_marine_box_barge,
    )
    ctx.tools.register(
        "marine_stability_gz",
        marine_stability_gz_spec,
        run_marine_stability_gz,
    )
    ctx.tools.register(
        "holtrop_mennen_resistance",
        holtrop_mennen_spec,
        run_holtrop_mennen,
    )

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="marine",
            version="0.1.0",
            provides=["marine.hydrostatics", "marine.stability", "marine.sections", "marine.resistance"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "marine",
            "version": "0.1.0",
            "provides": ["marine.hydrostatics", "marine.stability", "marine.sections", "marine.resistance"],
            "depends": [],
        }
