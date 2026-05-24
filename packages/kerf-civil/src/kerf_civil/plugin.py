"""
kerf-civil plugin entry-point.

Registers:
  - LLM tools: civil_horizontal_alignment, civil_vertical_alignment,
               civil_corridor_sections, civil_earthwork_volume
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_civil.tools import (
        civil_horizontal_alignment_spec,
        run_civil_horizontal_alignment,
        civil_vertical_alignment_spec,
        run_civil_vertical_alignment,
        civil_corridor_sections_spec,
        run_civil_corridor_sections,
        civil_earthwork_volume_spec,
        run_civil_earthwork_volume,
    )

    ctx.tools.register(
        "civil_horizontal_alignment",
        civil_horizontal_alignment_spec,
        run_civil_horizontal_alignment,
    )
    ctx.tools.register(
        "civil_vertical_alignment",
        civil_vertical_alignment_spec,
        run_civil_vertical_alignment,
    )
    ctx.tools.register(
        "civil_corridor_sections",
        civil_corridor_sections_spec,
        run_civil_corridor_sections,
    )
    ctx.tools.register(
        "civil_earthwork_volume",
        civil_earthwork_volume_spec,
        run_civil_earthwork_volume,
    )

    # GK-P49: corridor B-rep / volume / IFC alignment
    try:
        from kerf_civil.tools_corridor import TOOLS as _corridor_tools
        for tool_name, tool_spec, tool_handler in _corridor_tools:
            ctx.tools.register(tool_name, tool_spec, tool_handler)
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "kerf-civil: failed to load tools_corridor: %s", _exc
        )

    provides = [
        "civil.horizontal_alignment",
        "civil.vertical_alignment",
        "civil.corridor",
        "civil.earthwork",
        "civil.corridor-brep",
        "civil.corridor-volume",
        "civil.corridor-ifc",
    ]

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="civil",
            version="0.1.0",
            provides=provides,
            depends=[],
        )
    except ImportError:
        return {
            "name": "civil",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }
