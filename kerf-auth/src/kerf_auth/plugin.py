"""kerf-auth plugin entry-point.

Registers /auth/* and /api/api-tokens routes.
"""
from __future__ import annotations

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest


async def register(app: FastAPI, ctx) -> PluginManifest:
    from kerf_auth.routes import router, api_tokens_router

    app.include_router(router, prefix="/auth", tags=["auth"])
    app.include_router(api_tokens_router, prefix="/api", tags=["api-tokens"])

    ctx.logger.info("kerf-auth: registered /auth and /api/api-tokens routes")

    return PluginManifest(
        name="kerf-auth",
        version="0.1.0",
        provides=["auth.jwt", "auth.api-token", "auth.session"],
        depends=[],
    )
