"""
kerf-piping plugin entry-point.

Registers:
  - LLM tools: piping_route_isometric, piping_import_pid, piping_export_svg
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_piping.tools import (
        piping_route_isometric_spec, run_piping_route_isometric,
        piping_import_pid_spec, run_piping_import_pid,
        piping_export_svg_spec, run_piping_export_svg,
        piping_pipe_spec_check_spec, run_piping_pipe_spec_check,
    )
    ctx.tools.register(
        "piping_route_isometric",
        piping_route_isometric_spec,
        run_piping_route_isometric,
    )
    ctx.tools.register(
        "piping_import_pid",
        piping_import_pid_spec,
        run_piping_import_pid,
    )
    ctx.tools.register(
        "piping_export_svg",
        piping_export_svg_spec,
        run_piping_export_svg,
    )
    ctx.tools.register(
        "piping_pipe_spec_check",
        piping_pipe_spec_check_spec,
        run_piping_pipe_spec_check,
    )

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="piping",
            version="0.1.0",
            provides=["piping.pid", "piping.isometric", "piping.dxf", "piping.b31_3"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "piping",
            "version": "0.1.0",
            "provides": ["piping.pid", "piping.isometric", "piping.dxf", "piping.b31_3"],
            "depends": [],
        }
