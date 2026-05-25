"""
kerf-textiles plugin entry-point.

Registers:
  - FastAPI router  POST /weave  POST /knit
  - LLM tool        textiles_generate  (via ctx.tools.register)

All generators are pure Python — no optional heavy dependencies.
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""
    from kerf_textiles.routes import router
    app.include_router(router)

    from kerf_textiles.tools import textiles_generate_spec, run_textiles_generate
    ctx.tools.register("textiles_generate", textiles_generate_spec, run_textiles_generate)

    from kerf_textiles.tools import textiles_cloth_drape_spec, run_textiles_cloth_drape
    ctx.tools.register("textiles_cloth_drape", textiles_cloth_drape_spec, run_textiles_cloth_drape)

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="textiles",
            version="0.1.0",
            provides=["textiles.weave", "textiles.knit", "textiles.draft", "textiles.drape"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "textiles",
            "version": "0.1.0",
            "provides": ["textiles.weave", "textiles.knit", "textiles.draft", "textiles.drape"],
            "depends": [],
        }
