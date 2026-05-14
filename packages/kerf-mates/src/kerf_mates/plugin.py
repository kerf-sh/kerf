"""
kerf-mates plugin entry-point.

Registers:
  - FastAPI router  POST /run-mates
  - LLM tools:
      add_mate, delete_mate, list_mates, solve_assembly
    (all registered via ctx.tools.register)

python-solvespace is optional — the pure-Python gradient-descent solver
works without it; the optional fast-path is gated at call time.
"""

from __future__ import annotations

from fastapi import FastAPI

# ── dependency gates ──────────────────────────────────────────────────────────

_SOLVESPACE_AVAILABLE = False
try:
    import python_solvespace  # noqa: F401
    _SOLVESPACE_AVAILABLE = True
except ImportError:
    pass


# ── register ──────────────────────────────────────────────────────────────────

async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_mates.routes import router
    app.include_router(router)

    # Register LLM tools
    from kerf_mates.tools import (
        add_mate_spec, run_add_mate,
        delete_mate_spec, run_delete_mate,
        list_mates_spec, run_list_mates,
        solve_assembly_spec, run_solve_assembly,
    )
    ctx.tools.register("add_mate", add_mate_spec, run_add_mate)
    ctx.tools.register("delete_mate", delete_mate_spec, run_delete_mate)
    ctx.tools.register("list_mates", list_mates_spec, run_list_mates)
    ctx.tools.register("solve_assembly", solve_assembly_spec, run_solve_assembly)

    # Pure-Python gradient-descent solver always available;
    # python-solvespace is the optional fast-path.
    provides = ["mates.gradient-descent"]
    if _SOLVESPACE_AVAILABLE:
        provides.append("mates.solver")

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="mates",
            version="0.1.0",
            provides=provides,
            depends=[],
        )
    except ImportError:
        return {
            "name": "mates",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }
