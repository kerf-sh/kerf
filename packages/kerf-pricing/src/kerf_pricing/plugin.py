"""kerf-pricing plugin entry-point.

Cloud-gated (proprietary).  When ``ctx.cloud_enabled`` is False, returns a
dormant manifest and mounts nothing.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest


logger = logging.getLogger(__name__)


async def register(app: FastAPI, ctx) -> PluginManifest:
    if not ctx.cloud_enabled:
        ctx.logger.info("kerf-pricing: cloud_enabled=False — plugin dormant")
        return PluginManifest(
            name="kerf-pricing",
            version="0.1.0",
            provides=[],
            depends=["kerf-auth"],
        )

    # ── HTTP routes ─────────────────────────────────────────────────────────
    from kerf_pricing.routes import router
    app.include_router(router, prefix="/api", tags=["pricing"])
    ctx.logger.info("kerf-pricing: registered /api/admin/pricing[/refresh] routes")

    # ── Background refresh worker ───────────────────────────────────────────
    workers_registry = getattr(ctx, "workers", None)
    if workers_registry is not None and not ctx.local_mode:
        try:
            from kerf_pricing.worker import PricingRefreshWorker

            async def _factory():
                return PricingRefreshWorker(pool=ctx.pool)

            workers_registry.register("pricing_refresh", _factory)
            ctx.logger.info("kerf-pricing: PricingRefreshWorker registered")
        except Exception as exc:
            ctx.logger.warning(
                "kerf-pricing: failed to register PricingRefreshWorker: %s", exc
            )

    return PluginManifest(
        name="kerf-pricing",
        version="0.1.0",
        provides=["pricing.live"],
        depends=["kerf-auth"],
    )
