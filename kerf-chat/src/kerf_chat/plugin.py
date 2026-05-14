"""kerf-chat plugin entry-point.

Provides the LLM agent loop.  The llm.py module hosts both the FastAPI router
(``llm_router``) and the agent loop.  This plugin mounts that router.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

PLUGIN_DEPENDS = ["kerf-api"]

# Path to the llm_docs corpus (bundled with this package).
LLM_DOCS_PATH = Path(__file__).parent.parent.parent / "llm_docs"


async def register(app: FastAPI, ctx) -> PluginManifest:
    # llm.py uses module-level get_settings() and acts as a singleton.
    # It exposes an APIRouter at module import time.
    from kerf_chat import llm as _llm
    router = getattr(_llm, "router", None)
    if router is not None:
        app.include_router(router, prefix="/api", tags=["chat"])
        ctx.logger.info("kerf-chat: registered chat router")
    else:
        ctx.logger.warning("kerf-chat: no router exported from llm.py")

    return PluginManifest(
        name="kerf-chat",
        version="0.1.0",
        provides=["chat.llm", "chat.tools-dispatch"],
        depends=["kerf-api"],
    )
