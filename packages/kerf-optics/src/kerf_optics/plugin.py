"""
kerf-optics plugin entry-point.

Registers:
  - LLM tools: optics_trace_ray, optics_lens_design
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_optics.tools import (
        optics_trace_ray_spec, run_optics_trace_ray,
        optics_lens_design_spec, run_optics_lens_design,
    )
    ctx.tools.register("optics_trace_ray", optics_trace_ray_spec, run_optics_trace_ray)
    ctx.tools.register("optics_lens_design", optics_lens_design_spec, run_optics_lens_design)

    provides = ["optics.paraxial", "optics.abcd"]

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="optics",
            version="0.1.0",
            provides=provides,
            depends=[],
        )
    except ImportError:
        return {
            "name": "optics",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }
