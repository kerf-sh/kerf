"""kerf-cloud plugin entry-point.

Cloud-gated: when ctx.cloud_enabled is False, returns an empty manifest and
no routes are mounted.
"""
from __future__ import annotations

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

PLUGIN_DEPENDS = ["kerf-auth", "kerf-api"]


async def register(app: FastAPI, ctx) -> PluginManifest:
    if not ctx.cloud_enabled:
        ctx.logger.info("kerf-cloud: cloud_enabled=False — plugin dormant")
        return PluginManifest(
            name="kerf-cloud",
            version="0.1.0",
            provides=[],
            depends=["kerf-auth", "kerf-api"],
        )

    from kerf_cloud.routes import router, github_oauth_router
    app.include_router(router, prefix="/api", tags=["cloud"])
    app.include_router(github_oauth_router, prefix="/auth", tags=["github-oauth"])

    ctx.logger.info("kerf-cloud: registered /api/projects/*/git/* and /auth/github/* routes")

    return PluginManifest(
        name="kerf-cloud",
        version="0.1.0",
        provides=["cloud.workshop", "cloud.git"],
        depends=["kerf-auth", "kerf-api"],
    )
