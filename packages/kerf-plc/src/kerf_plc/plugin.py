"""
kerf-plc plugin registration.

Wires the PLC lint route and LLM tools into a Kerf plugin app.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""
    # ── HTTP routes ──────────────────────────────────────────────────────────
    from kerf_plc.routes import router as plc_router
    app.include_router(plc_router, tags=["plc"])

    # ── LLM tools ────────────────────────────────────────────────────────────
    provides = []
    _register_tools(ctx, provides)

    # plc.lint is always declared — the route gracefully degrades when
    # MATIEC isn't installed.
    if "plc.lint" not in provides:
        provides.append("plc.lint")

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "plc",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="plc",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all PLC LLM tools into ctx.tools."""
    try:
        from kerf_plc.tools.run_plc_lint import run_plc_lint_spec, run_plc_lint
        ctx.tools.register("run_plc_lint", run_plc_lint_spec, run_plc_lint)
        provides.append("plc.lint")
    except Exception as exc:
        logger.warning("kerf-plc: failed to load run_plc_lint tool: %s", exc)

    try:
        from kerf_plc.tools.create_ladder_rung import create_ladder_rung_spec, create_ladder_rung
        ctx.tools.register("create_ladder_rung", create_ladder_rung_spec, create_ladder_rung)
        provides.append("plc.ld")
    except Exception as exc:
        logger.warning("kerf-plc: failed to load create_ladder_rung tool: %s", exc)
