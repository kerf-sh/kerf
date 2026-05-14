"""
kerf-tess plugin entry point.

Registers the /run-tess HTTP route and (when cloud_enabled and not local_mode)
registers the AutoTessWorker with the WorkerRegistry.

Entry-point (pyproject.toml):
    [project.entry-points."kerf.plugins"]
    tess = "kerf_tess.plugin:register"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ── kerf_core contract (built by kerf-core agent in parallel) ─────────────────
try:
    from kerf_core.plugin import PluginContext, PluginManifest  # type: ignore[import]
    _KERF_CORE_AVAILABLE = True
except ImportError:
    _KERF_CORE_AVAILABLE = False

    class PluginManifest:  # type: ignore[no-redef]
        def __init__(self, *, name: str, version: str, provides: list, depends: list):
            self.name = name
            self.version = version
            self.provides = provides
            self.depends = depends

    class PluginContext:  # type: ignore[no-redef]
        pool = None
        storage = None
        config = None
        tools = None
        workers = None
        logger = logging.getLogger("kerf_tess.ctx")
        cloud_enabled: bool = False
        local_mode: bool = True


# ── OCC availability (inherited from kerf-cad-core) ───────────────────────────
try:
    from kerf_cad_core import _OCC_AVAILABLE
except ImportError:
    _OCC_AVAILABLE = False


async def register(app, ctx: "PluginContext") -> "PluginManifest":
    """Plugin entry-point.

    1. Mounts the /run-tess route.
    2. When cloud_enabled and not local_mode, registers AutoTessWorker.
    3. Returns manifest; provides list is empty when pythonOCC is absent.
    """
    # ── mount route ───────────────────────────────────────────────────────────
    from kerf_tess.routes import router
    app.include_router(router)
    logger.info("kerf-tess: /run-tess route mounted")

    # ── worker registration ───────────────────────────────────────────────────
    cloud_enabled = getattr(ctx, "cloud_enabled", False)
    local_mode = getattr(ctx, "local_mode", True)

    if cloud_enabled and not local_mode:
        try:
            from kerf_tess.worker import AutoTessWorker

            workers_registry = getattr(ctx, "workers", None)
            if workers_registry is not None:
                workers_registry.register(
                    "auto_tess",
                    factory=AutoTessWorker,
                )
                logger.info("kerf-tess: AutoTessWorker registered")
            else:
                logger.warning(
                    "kerf-tess: ctx.workers is None — AutoTessWorker not registered"
                )
        except Exception as exc:
            logger.exception("kerf-tess: failed to register AutoTessWorker: %s", exc)
    else:
        logger.info(
            "kerf-tess: cloud worker skipped (cloud_enabled=%s local_mode=%s)",
            cloud_enabled,
            local_mode,
        )

    # ── manifest ──────────────────────────────────────────────────────────────
    provides = ["tess.step-to-glb"] if _OCC_AVAILABLE else []
    if not _OCC_AVAILABLE:
        logger.warning(
            "kerf-tess: pythonOCC not available — tess.step-to-glb capability absent. "
            "Tessellation falls back to Node sidecar (occt-import-js)."
        )

    return PluginManifest(
        name="tess",
        version="0.1.0",
        provides=provides,
        depends=["cad-core"],
    )
