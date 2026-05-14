"""
kerf-workers plugin registration.

Provides the generic worker harness (BaseWorker, JobMixin, runner).
Concrete workers (FEM, CAM, SPICE, Tess) live in their respective plugins
and register themselves via WorkerRegistry.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# ── WorkerRegistry ───────────────────────────────────────────────────────────
# Other plugins call WorkerRegistry.register(worker_cls) at plugin load time.
# The runner then instantiates and starts registered workers.

_worker_registry: list = []


class WorkerRegistry:
    """Simple registry for worker classes contributed by other plugins."""

    @classmethod
    def register(cls, worker_cls) -> None:
        _worker_registry.append(worker_cls)

    @classmethod
    def all(cls) -> list:
        return list(_worker_registry)


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""

    # Expose WorkerRegistry on the context so other plugins can register workers
    if hasattr(ctx, "workers"):
        ctx.workers.registry = WorkerRegistry
    else:
        logger.warning("kerf-workers: ctx.workers not available; WorkerRegistry standalone only")

    provides = ["workers.harness"]

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "workers",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="workers",
        version="0.1.0",
        provides=provides,
        depends=[],
    )
