"""
kerf-rules plugin entry-point.

The rules engine is a pure library used by other plugins (BIM, structural,
mechanical) to evaluate compliance rule packs. This plugin registers no HTTP
routes and no LLM tools — it only declares its presence so the plugin loader
records `kerf-rules` in the manifest and downstream plugins know the engine
is importable.
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="rules",
            version="0.1.0",
            provides=["rules.engine"],
            depends=[],
        )
    except ImportError:
        return {
            "name": "rules",
            "version": "0.1.0",
            "provides": ["rules.engine"],
            "depends": [],
        }
