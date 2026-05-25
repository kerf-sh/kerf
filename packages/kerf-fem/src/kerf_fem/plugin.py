"""
kerf-fem plugin entry-point.

Registers:
  - FastAPI router  POST /run-fem
  - LLM tools       fem_run, fem_job_status  (via ctx.tools.register)
  - LLM tools       fem_acoustics, fem_electrostatics, fem_magnetostatics,
                    cfd_navier_stokes_steady, cfd_potential_cylinder
                    (via import-triggered self-registration)
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
        fem_buckling_linear_spec, run_fem_buckling_linear,
        fem_harmonic_response_spec, run_fem_harmonic_response,
        fem_random_vibration_psd_spec, run_fem_random_vibration_psd,
    )
    ctx.tools.register("fem_run", fem_run_spec, run_fem_run)
    ctx.tools.register("fem_job_status", fem_job_status_spec, run_fem_job_status)
    ctx.tools.register("fem_nonlinear_bar", fem_nonlinear_bar_spec, run_fem_nonlinear_bar)
    ctx.tools.register("fem_truss_plastic", fem_truss_plastic_spec, run_fem_truss_plastic)
    ctx.tools.register("fem_buckling_linear", fem_buckling_linear_spec, run_fem_buckling_linear)
    ctx.tools.register("fem_harmonic_response", fem_harmonic_response_spec, run_fem_harmonic_response)
    ctx.tools.register("fem_random_vibration_psd", fem_random_vibration_psd_spec, run_fem_random_vibration_psd)
    from kerf_fem.nonlinear import _fem_nonlinear_spec, run_fem_nonlinear; ctx.tools.register("fem_nonlinear", _fem_nonlinear_spec, run_fem_nonlinear)
    from kerf_fem.fatigue_fem import _fem_fatigue_spec, run_fem_fatigue; ctx.tools.register("fem_fatigue", _fem_fatigue_spec, run_fem_fatigue)  # kerf-fem: fatigue & durability
    from kerf_fem.plate import _fem_plate_static_spec, run_fem_plate_static_solve; ctx.tools.register("fem_plate_static_solve", _fem_plate_static_spec, run_fem_plate_static_solve)  # kerf-fem: MITC4 plate/shell
    import kerf_fem.em_highfreq  # kerf-fem: high-frequency EM (waveguide, S-params, FDTD) — self-registers fem_em_highfreq tool on import
    import kerf_fem.acoustics_fem  # kerf-fem: acoustics FEM (cavity modes, BEM radiation) — self-registers fem_acoustics
    import kerf_fem.em_field  # kerf-fem: electrostatics + magnetostatics — self-registers fem_electrostatics, fem_magnetostatics
    import kerf_fem.cfd_navier_stokes  # kerf-fem: 2-D projection NS solver — self-registers cfd_navier_stokes_steady
    import kerf_fem.cfd_potential  # kerf-fem: potential-flow cylinder — self-registers cfd_potential_cylinder

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
    provides = [
        "fem.nonlinear", "fem.electromagnetics",
        "fem.acoustics", "fem.electrostatics", "fem.magnetostatics",
        "fem.cfd-navier-stokes", "fem.cfd-potential",
        "fem.buckling", "fem.harmonic-response", "fem.random-vibration",
    ]
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
