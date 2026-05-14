"""
kerf-cam plugin entry-point.

Registers:
  - FastAPI router  POST /run-cam
  - LLM tools       cam_run, cam_job_status  (via ctx.tools.register)
  - background worker for cam_jobs table     (via ctx.workers.register)

Heavy deps (opencamlib, pythonocc-core) are optional — the plugin still
loads and returns a mock toolpath when they are absent.
"""

from __future__ import annotations

from fastapi import FastAPI

# ── dependency gates ──────────────────────────────────────────────────────────

_OCL_AVAILABLE = False
try:
    import opencamlib  # noqa: F401
    _OCL_AVAILABLE = True
except ImportError:
    pass

_OCC_AVAILABLE = False
try:
    from OCC.Core.STEPControl import STEPControl_Reader  # noqa: F401
    _OCC_AVAILABLE = True
except ImportError:
    pass


# ── register ──────────────────────────────────────────────────────────────────

async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_cam.routes import router
    app.include_router(router)

    # Register LLM tools
    from kerf_cam.tools import (
        cam_run_spec, run_cam_run,
        cam_job_status_spec, run_cam_job_status,
    )
    ctx.tools.register("cam_run", cam_run_spec, run_cam_run)
    ctx.tools.register("cam_job_status", cam_job_status_spec, run_cam_job_status)

    # Register background worker
    from kerf_cam.worker import CAMWorker
    ctx.workers.register(
        "cam",
        CAMWorker(
            pool=ctx.pool,
            storage_getter=lambda: ctx.storage,
            pyworker_url=ctx.config.get("pyworker_url", "http://localhost:8090"),
        ),
    )

    # Capabilities depend on available deps
    provides = ["cam.2_5d"]   # pure-Python mock always available
    if _OCL_AVAILABLE:
        provides += ["cam.parallel-3d", "cam.waterline", "cam.lathe"]

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="cam",
            version="0.1.0",
            provides=provides,
            depends=["cad-core"],
        )
    except ImportError:
        return {
            "name": "cam",
            "version": "0.1.0",
            "provides": provides,
            "depends": ["cad-core"],
        }
