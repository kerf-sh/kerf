"""
kerf-fem plugin entry-point.

Registers:
  - FastAPI router  POST /run-fem
  - LLM tools       fem_run, fem_job_status  (via ctx.tools.register)
  - background worker for fem_jobs table     (via ctx.workers.register)

Heavy deps (dolfinx, slepc4py) are optional — the plugin still loads
with a reduced `provides` list when they are absent.
"""

from __future__ import annotations

import shutil

from fastapi import FastAPI

# ── dependency gates ──────────────────────────────────────────────────────────

_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

_SLEPC_AVAILABLE = False
try:
    from slepc4py import SLEPc  # noqa: F401
    _SLEPC_AVAILABLE = True
except ImportError:
    pass

_CALCULIX_AVAILABLE = shutil.which("ccx") is not None


# ── register ──────────────────────────────────────────────────────────────────

async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_fem.routes import router
    app.include_router(router)

    # Register LLM tools
    from kerf_fem.tools import (
        fem_run_spec, run_fem_run,
        fem_job_status_spec, run_fem_job_status,
        fem_nonlinear_bar_spec, run_fem_nonlinear_bar,
        fem_truss_plastic_spec, run_fem_truss_plastic,
    )
    ctx.tools.register("fem_run", fem_run_spec, run_fem_run)
    ctx.tools.register("fem_job_status", fem_job_status_spec, run_fem_job_status)
    ctx.tools.register("fem_nonlinear_bar", fem_nonlinear_bar_spec, run_fem_nonlinear_bar)
    ctx.tools.register("fem_truss_plastic", fem_truss_plastic_spec, run_fem_truss_plastic)
    from kerf_fem.nonlinear import _fem_nonlinear_spec, run_fem_nonlinear; ctx.tools.register("fem_nonlinear", _fem_nonlinear_spec, run_fem_nonlinear)

    # Register background worker
    from kerf_fem.worker import FEMWorker
    fem_worker = FEMWorker(
        pool=ctx.pool,
        storage_getter=lambda: ctx.storage,
        pyworker_url=getattr(ctx.config, "pyworker_url", "http://localhost:8090"),
    )

    async def _fem_factory():
        return fem_worker

    ctx.workers.register("fem", _fem_factory)

    # Build `provides` list based on available deps
    # fem.nonlinear is pure-Python — always available
    provides = ["fem.nonlinear", "fem.electromagnetics"]
    if _DOLFINX_AVAILABLE:
        provides.append("fem.linear-static")
        provides.append("fem.thermal")
        if _SLEPC_AVAILABLE:
            provides.append("fem.modal")
    if _CALCULIX_AVAILABLE:
        if "fem.linear-static" not in provides:
            provides.append("fem.linear-static")
        if "fem.modal" not in provides:
            provides.append("fem.modal")

    # Return manifest as a plain dict (PluginManifest from kerf_core when available)
    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="fem",
            version="0.1.0",
            provides=provides,
            depends=["cad-core"],
        )
    except ImportError:
        return {
            "name": "fem",
            "version": "0.1.0",
            "provides": provides,
            "depends": ["cad-core"],
        }
