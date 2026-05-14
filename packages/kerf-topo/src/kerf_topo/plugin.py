"""
kerf-topo plugin entry-point.

Registers:
  - FastAPI router  POST /run-topo
  - LLM tool        topo_run  (via ctx.tools.register)

Heavy deps (dolfinx, gmsh, scikit-image, scipy, pythonocc-core) are optional.
The plugin always loads; `provides` is filtered to reflect what works.
"""

from __future__ import annotations

from fastapi import FastAPI

# ── dependency gates ──────────────────────────────────────────────────────────

_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

_GMSH_AVAILABLE = False
try:
    import gmsh  # noqa: F401
    _GMSH_AVAILABLE = True
except ImportError:
    pass

_SKIMAGE_AVAILABLE = False
try:
    import skimage  # noqa: F401
    _SKIMAGE_AVAILABLE = True
except ImportError:
    pass


# ── register ──────────────────────────────────────────────────────────────────

async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_topo.routes import router
    app.include_router(router)

    # Register LLM tool
    from kerf_topo.tools import topo_run_spec, run_topo_run
    ctx.tools.register("topo_run", topo_run_spec, run_topo_run)

    # topo.simp is only fully functional when dolfinx + skimage are present
    provides = []
    if _DOLFINX_AVAILABLE and _SKIMAGE_AVAILABLE:
        provides.append("topo.simp")

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="topo",
            version="0.1.0",
            provides=provides,
            depends=["fem", "cad-core"],
        )
    except ImportError:
        return {
            "name": "topo",
            "version": "0.1.0",
            "provides": provides,
            "depends": ["fem", "cad-core"],
        }
