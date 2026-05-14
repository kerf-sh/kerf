"""kerf-billing plugin entry-point.

Cloud-gated: when ctx.cloud_enabled is False, returns an empty manifest and
no routes are mounted.
"""
from __future__ import annotations

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

PLUGIN_DEPENDS = ["kerf-auth"]


async def register(app: FastAPI, ctx) -> PluginManifest:
    if not ctx.cloud_enabled:
        ctx.logger.info("kerf-billing: cloud_enabled=False — plugin dormant")
        return PluginManifest(
            name="kerf-billing",
            version="0.1.0",
            provides=[],
            depends=["kerf-auth"],
        )

    from kerf_billing.routes import router
    app.include_router(router, prefix="/api", tags=["billing"])

    ctx.logger.info("kerf-billing: registered /api/billing/* routes (Paystack)")

    # ── Background BillingResetWorker — daily api-token cap reset + monthly
    # free-quota reset.  Only registered when running in cloud mode.
    workers_registry = getattr(ctx, "workers", None)
    if workers_registry is not None and not ctx.local_mode:
        try:
            from kerf_billing.scheduler import BillingResetWorker

            async def _factory():
                return BillingResetWorker(pool=ctx.pool)

            workers_registry.register("billing_reset", _factory)
            ctx.logger.info("kerf-billing: BillingResetWorker registered")
        except Exception as exc:
            ctx.logger.warning(
                "kerf-billing: failed to register BillingResetWorker: %s", exc
            )

    return PluginManifest(
        name="kerf-billing",
        version="0.1.0",
        provides=["billing.paystack", "billing.buckets"],
        depends=["kerf-auth"],
    )
