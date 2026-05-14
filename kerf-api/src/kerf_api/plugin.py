"""kerf-api plugin entry-point.

Registers /api/* routes.
"""
from __future__ import annotations

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

PLUGIN_DEPENDS = ["kerf-auth"]


async def register(app: FastAPI, ctx) -> PluginManifest:
    from kerf_api.routes import router
    app.include_router(router, prefix="/api", tags=["api"])

    ctx.logger.info("kerf-api: registered /api routes")

    return PluginManifest(
        name="kerf-api",
        version="0.1.0",
        provides=["api.rest", "files.crud", "projects.crud"],
        depends=["kerf-auth"],
    )
