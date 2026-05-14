"""kerf-chat plugin entry-point.

Provides the LLM agent loop.  The llm.py module hosts both the FastAPI router
(``llm_router``) and the agent loop.  This plugin mounts that router.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest, ToolSpec as CoreToolSpec

logger = logging.getLogger(__name__)

PLUGIN_DEPENDS = ["kerf-api"]

# Path to the llm_docs corpus (bundled with this package).
LLM_DOCS_PATH = Path(__file__).parent.parent.parent / "llm_docs"


def _register_tools(ctx) -> None:
    """Register kerf-chat's built-in LLM tools into ctx.tools."""
    try:
        from kerf_chat.tools.docs import search_kerf_docs_spec, run_search_kerf_docs
        core_spec = CoreToolSpec(
            name=search_kerf_docs_spec.name,
            description=search_kerf_docs_spec.description,
            parameters=search_kerf_docs_spec.input_schema,
        )
        ctx.tools.register(search_kerf_docs_spec.name, core_spec, run_search_kerf_docs)
        logger.info("kerf-chat: registered tool '%s'", search_kerf_docs_spec.name)
    except Exception as exc:
        logger.warning("kerf-chat: failed to register search_kerf_docs: %s", exc)


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

    # Register built-in LLM tools.
    _register_tools(ctx)

    return PluginManifest(
        name="kerf-chat",
        version="0.1.0",
        provides=["chat.llm", "chat.tools-dispatch", "chat.search-docs"],
        depends=["kerf-api"],
    )
