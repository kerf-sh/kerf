"""
kerf-motion plugin entry-point.

Registers:
  - LLM tools:  simulate_motion, solve_ik, compute_workspace (via ctx.tools.register)

No external solvers or heavy deps required — the full simulation stack is
pure Python.
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by kerf-core plugin loader at startup."""

    from kerf_motion.tools import (
        simulate_motion_spec, run_simulate_motion,
        solve_ik_spec, run_solve_ik,
        compute_workspace_spec, run_compute_workspace,
    )
    ctx.tools.register("simulate_motion", simulate_motion_spec, run_simulate_motion)
    ctx.tools.register("solve_ik", solve_ik_spec, run_solve_ik)
    ctx.tools.register("compute_workspace", compute_workspace_spec, run_compute_workspace)

    provides = [
        "motion.rigid-body-dynamics",
        "motion.rk4-integrator",
        "motion.forward-kinematics",
        "motion.inverse-kinematics",
        "motion.workspace-analysis",
    ]

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="motion",
            version="0.1.0",
            provides=provides,
            depends=[],
        )
    except ImportError:
        return {
            "name": "motion",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }
