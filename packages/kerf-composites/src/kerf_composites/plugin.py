"""
kerf-composites plugin entry-point.

Registers:
  - LLM tools: layup_analysis
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_composites.tools import layup_analysis_spec, run_layup_analysis
    ctx.tools.register("layup_analysis", layup_analysis_spec, run_layup_analysis)

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="composites",
            version="0.1.0",
            provides=["composites.layup", "composites.clt", "composites.failure", "composites.drape"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "composites",
            "version": "0.1.0",
            "provides": ["composites.layup", "composites.clt", "composites.failure", "composites.drape"],
            "depends": [],
        }
