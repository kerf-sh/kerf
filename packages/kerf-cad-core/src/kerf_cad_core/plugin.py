"""
kerf-cad-core plugin entry point.

Registers the ``POST /run-quad-remesh`` HTTP route and CAD-core LLM tools
(feature_cut_from_sketch, cam_layered, quad_remesh, etc.) into the tool
registry so the chat agent can invoke them.

Entry-point (pyproject.toml):
    [project.entry-points."kerf.plugins"]
    cad-core = "kerf_cad_core.plugin:register"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ── LLM tool modules provided by this plugin ─────────────────────────────────
_TOOL_MODULES = [
    "kerf_cad_core.feature_cut_from_sketch",
    "kerf_cad_core.feature_hole_pattern_from_sketch",
    "kerf_cad_core.feature_loft",
    "kerf_cad_core.feature_section",
    "kerf_cad_core.cam_layered",
    "kerf_cad_core.extrude_sketch_to_jscad",
    "kerf_cad_core.surfacing",
    "kerf_cad_core.quad_remesh",
    "kerf_cad_core.jewelry.gemstones",
    "kerf_cad_core.jewelry.gem_seat",
    "kerf_cad_core.jewelry.settings",
    "kerf_cad_core.jewelry.ring",
    "kerf_cad_core.jewelry.tool_metal_cost",
    "kerf_cad_core.jewelry.chain",
    "kerf_cad_core.jewelry.findings",
    "kerf_cad_core.jewelry.decorative",
    "kerf_cad_core.jewelry.pieces",
    "kerf_cad_core.jewelry.casting_export",
    "kerf_cad_core.jewelry.templates",
    "kerf_cad_core.jewelry.pave_wizard",
    "kerf_cad_core.jewelry.setter_checklist",
    "kerf_cad_core.sheet_metal",
    "kerf_cad_core.gdt.tools",
    "kerf_cad_core.arch.tools",
    "kerf_cad_core.struct.tools",
    "kerf_cad_core.feature_thread",
    "kerf_cad_core.assembly.tools",
    "kerf_cad_core.assembly.perf",
    "kerf_cad_core.weldment",
    "kerf_cad_core.civil.tools",
    "kerf_cad_core.civil.alignment_tools",
    "kerf_cad_core.gears",
    "kerf_cad_core.geom.surface_boolean_robust",
    "kerf_cad_core.geom.trim_curve",
    "kerf_cad_core.nesting.tools",
    "kerf_cad_core.harness.tools",
    "kerf_cad_core.clash.tools",
    "kerf_cad_core.marine.tools",
    "kerf_cad_core.scan.tools",
    "kerf_cad_core.gdt_callouts.tools",
    "kerf_cad_core.family.tools",
    "kerf_cad_core.shaft.tools",
    "kerf_cad_core.gearbox.tools",
    "kerf_cad_core.arch.spaces_tools",
    "kerf_cad_core.civil.hydraulics_tools",
    "kerf_cad_core.tolstack.tools",
    "kerf_cad_core.kinematics.tools",
    "kerf_cad_core.fea.tools",
    "kerf_cad_core.springs.tools",
    "kerf_cad_core.piping.tools",
    "kerf_cad_core.hvac.tools",
    "kerf_cad_core.turning.tools",
    "kerf_cad_core.steelconn.tools",
    "kerf_cad_core.pressvessel.tools",
    "kerf_cad_core.fasteners.tools",
    "kerf_cad_core.fluidpower.tools",
    "kerf_cad_core.gearstrength.tools",
    "kerf_cad_core.vibration.tools",
    "kerf_cad_core.fatigue.tools",
    "kerf_cad_core.matsel.tools",
    "kerf_cad_core.pneumatics.tools",
    "kerf_cad_core.heatxfer.tools",
    "kerf_cad_core.beam.tools",
    "kerf_cad_core.casting.tools",
    "kerf_cad_core.injection.tools",
    "kerf_cad_core.surveying.tools",
    "kerf_cad_core.geotech.tools",
    "kerf_cad_core.hydrology.tools",
    "kerf_cad_core.welding.tools",
    "kerf_cad_core.tolfits.tools",
    "kerf_cad_core.cncfeeds.tools",
    "kerf_cad_core.clutchbrake.tools",
    "kerf_cad_core.pumpsys.tools",
    "kerf_cad_core.beltchain.tools",
    "kerf_cad_core.acoustics.tools",
    "kerf_cad_core.bearings.tools",
    "kerf_cad_core.thermocycle.tools",
    "kerf_cad_core.robotics.tools",
    "kerf_cad_core.aero.tools",
    "kerf_cad_core.optics.tools",
    "kerf_cad_core.composites.tools",
    "kerf_cad_core.navalarch.tools",
    "kerf_cad_core.lubrication.tools",
    "kerf_cad_core.windload.tools",
    "kerf_cad_core.controls.tools",
    "kerf_cad_core.seismic.tools",
    "kerf_cad_core.concrete.tools",
    "kerf_cad_core.solarpv.tools",
    "kerf_cad_core.timber.tools",
    "kerf_cad_core.costing.tools",
    "kerf_cad_core.conveyor.tools",
    "kerf_cad_core.additive.tools",
    "kerf_cad_core.wormbevel.tools",
    "kerf_cad_core.psychro.tools",
    "kerf_cad_core.rigging.tools",
    "kerf_cad_core.packaging.tools",
    "kerf_cad_core.combustion.tools",
    "kerf_cad_core.corrosion.tools",
    "kerf_cad_core.flowmeter.tools",
    "kerf_cad_core.turbo.tools",
    "kerf_cad_core.ergonomics.tools",
    "kerf_cad_core.channel.tools",
    "kerf_cad_core.gcode.tools",
    "kerf_cad_core.cmm.tools",
    "kerf_cad_core.fiveaxis.tools",
    "kerf_cad_core.dynamics.tools",
    "kerf_cad_core.tank.tools",
    "kerf_cad_core.railway.tools",
    "kerf_cad_core.cuttingtool.tools",
    "kerf_cad_core.boiler.tools",
    "kerf_cad_core.spillway.tools",
    "kerf_cad_core.refrigeration.tools",
    "kerf_cad_core.vacuum.tools",
    "kerf_cad_core.windturbine.tools",
    "kerf_cad_core.hydroturbine.tools",
    "kerf_cad_core.forming.tools",
    "kerf_cad_core.reliability.tools",
    "kerf_cad_core.thermalcut.tools",
    "kerf_cad_core.heattreat.tools",
    "kerf_cad_core.waterhammer.tools",
    "kerf_cad_core.pavement.tools",
    "kerf_cad_core.buildingenergy.tools",
    "kerf_cad_core.firesafety.tools",
    "kerf_cad_core.mooring.tools",
    "kerf_cad_core.geodesy.tools",
    "kerf_cad_core.elevator.tools",
    "kerf_cad_core.lighting.tools",
    "kerf_cad_core.crane.tools",
    "kerf_cad_core.elecpower.tools",
    "kerf_cad_core.plumbing.tools",
    "kerf_cad_core.earthworks.tools",
    "kerf_cad_core.geom.make2d",
    "kerf_cad_core.geom.curve_toolkit",
    "kerf_cad_core.geom.surface_analysis",
    "kerf_cad_core.geom.mesh_repair",
    "kerf_cad_core.geom.unroll_srf",
    "kerf_cad_core.geom.solid_features",
    "kerf_cad_core.geom.patch_srf",
    "kerf_cad_core.geom.revolve_srf",
    "kerf_cad_core.jewelry.production",
    "kerf_cad_core.jewelry.gem_studio",
    "kerf_cad_core.jewelry.gallery",
    "kerf_cad_core.jewelry.head_wizard",
    "kerf_cad_core.geom.subd",
    "kerf_cad_core.geom.blocks",
    "kerf_cad_core.geom.mesh_to_nurbs",
    "kerf_cad_core.geom.section_contour",
    "kerf_cad_core.jewelry.eternity_auto",
    "kerf_cad_core.geom.surface_fillet",
    "kerf_cad_core.jewelry.bangle",
    "kerf_cad_core.jewelry.hollowing",
    "kerf_cad_core.jewelry.engraving",
    "kerf_cad_core.geom.match_srf",
    "kerf_cad_core.geom.intersection",
    "kerf_cad_core.jewelry.bezel_auto",
    "kerf_cad_core.jewelry.plating",
    "kerf_cad_core.jewelry.gem_cert",
    "kerf_cad_core.jewelry.bas_relief",
    "kerf_cad_core.jewelry.print_presets",
    "kerf_cad_core.jewelry.tech_drawing",
    "kerf_cad_core.jewelry.cam_wax",
    "kerf_cad_core.jewelry.filigree_advanced",
    "kerf_cad_core.quoting.fab_quote",
    "kerf_cad_core.dfm.checks",
    "kerf_cad_core.cam_wizard.stock_setup",
    "kerf_cad_core.drawings.auto_dimension",
]

# ── kerf_core contract (built by kerf-core agent in parallel) ─────────────────
# Import lazily so this plugin boots even before kerf_core is installed.
try:
    from kerf_core.plugin import PluginContext, PluginManifest  # type: ignore[import]
    _KERF_CORE_AVAILABLE = True
except ImportError:
    _KERF_CORE_AVAILABLE = False

    # Minimal stubs so the rest of this file type-checks cleanly at runtime.
    class PluginManifest:  # type: ignore[no-redef]
        def __init__(self, *, name: str, version: str, provides: list, depends: list):
            self.name = name
            self.version = version
            self.provides = provides
            self.depends = depends

    class PluginContext:  # type: ignore[no-redef]
        pass


# ── OCC availability ──────────────────────────────────────────────────────────
from kerf_cad_core.occ_helpers import _OCC_AVAILABLE

# Import the feature tools so the @register decorators fire on plugin load.
try:
    import kerf_cad_core.feature_boss_with_draft  # noqa: F401 — side-effect import
except Exception as _import_err:
    logger.warning("kerf-cad-core: could not load feature_boss_with_draft: %s", _import_err)

try:
    import kerf_cad_core.feature_hole_pattern_from_sketch  # noqa: F401 — side-effect import
except Exception as _import_err:
    logger.warning("kerf-cad-core: could not load feature_hole_pattern_from_sketch: %s", _import_err)

try:
    import kerf_cad_core.feature_loft  # noqa: F401 — side-effect import
except Exception as _import_err:
    logger.warning("kerf-cad-core: could not load feature_loft: %s", _import_err)

_PROVIDES_FULL = [
    "cad.step-io",
    "cad.brep-mesh",
    "cad.wire-extract",
    "cad.nurbs",
]


async def register(app, ctx: "PluginContext") -> "PluginManifest":
    """Plugin entry-point.

    Mounts the quad-remesh HTTP route and returns a manifest advertising
    which CAD capabilities are available (empty list when pythonOCC is not
    installed so /health/capabilities shows "cad-core dormant").
    """
    if _OCC_AVAILABLE:
        provides = _PROVIDES_FULL
        logger.info("kerf-cad-core: pythonOCC available — %s", provides)
    else:
        provides = []
        logger.warning(
            "kerf-cad-core: pythonOCC not installed — plugin dormant. "
            "Install: conda install -c conda-forge pythonocc-core"
        )

    # ── Mount HTTP routes ─────────────────────────────────────────────────
    try:
        from kerf_cad_core.routes import router as cad_router
        app.include_router(cad_router, tags=["cad-core"])
    except Exception as _route_err:  # pragma: no cover
        logger.warning("kerf-cad-core: could not mount routes: %s", _route_err)

    # ── Register LLM tools ────────────────────────────────────────────────
    _register_tools()

    return PluginManifest(
        name="cad-core",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools() -> None:
    """Import tool modules so their @register decorators fire."""
    import importlib
    for module_path in _TOOL_MODULES:
        try:
            importlib.import_module(module_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("kerf-cad-core: failed to load tool %s: %s", module_path, exc)
