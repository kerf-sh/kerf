"""kerf-v1 plugin entry-point.

Registers /v1/rpc — JSON-RPC 2.0 dispatcher for kerf-sdk.
"""
from __future__ import annotations

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

PLUGIN_DEPENDS = ["kerf-api", "kerf-auth"]


async def register(app: FastAPI, ctx) -> PluginManifest:
    from kerf_v1.routes import router
    app.include_router(router, prefix="/v1", tags=["v1"])

    ctx.logger.info("kerf-v1: registered /v1/rpc")

    return PluginManifest(
        name="kerf-v1",
        version="0.1.0",
        provides=["v1.rpc"],
        depends=["kerf-api", "kerf-auth"],
    )
