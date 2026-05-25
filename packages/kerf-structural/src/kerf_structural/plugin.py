"""
kerf-structural plugin entry-point.

Registers:
  - LLM tools:  structural_rc_beam, structural_steel_beam,
                structural_rebar, structural_loads,
                aisc_compression, aisc_flexure, aisc_combined,
                aisc_member_check,
                structural_cfs_flexure, structural_cfs_compression,
                structural_cfs_web_crippling,
                structural_masonry_flexure, structural_masonry_shear,
                structural_masonry_axial
"""

from __future__ import annotations

from fastapi import FastAPI


async def register(app: FastAPI, ctx):
    """Plugin entry-point — called by the kerf-core plugin loader at startup."""

    from kerf_structural.tools import (
        rc_beam_spec, run_rc_beam,
        steel_beam_spec, run_steel_beam,
        rebar_spec, run_rebar,
        loads_spec, run_loads,
    )

    ctx.tools.register("structural_rc_beam",   rc_beam_spec,   run_rc_beam)
    ctx.tools.register("structural_steel_beam", steel_beam_spec, run_steel_beam)
    ctx.tools.register("structural_rebar",      rebar_spec,     run_rebar)
    ctx.tools.register("structural_loads",      loads_spec,     run_loads)

    # AISC 360-22 Chapters E / F / H full member checks
    from kerf_structural.aisc_member import (
        aisc_compression_spec, run_aisc_compression,
        aisc_flexure_spec, run_aisc_flexure,
        aisc_combined_spec, run_aisc_combined,
        aisc_member_check_spec, run_aisc_member_check,
    )
    ctx.tools.register("aisc_compression",  aisc_compression_spec,  run_aisc_compression)
    ctx.tools.register("aisc_flexure",      aisc_flexure_spec,      run_aisc_flexure)
    ctx.tools.register("aisc_combined",     aisc_combined_spec,     run_aisc_combined)
    ctx.tools.register("aisc_member_check", aisc_member_check_spec, run_aisc_member_check)

    # AISI S100-16 Cold-Formed Steel (new — 2026-05-25)
    from kerf_structural.cold_formed_steel import (
        cfs_flexure_spec, run_cfs_flexure,
        cfs_compression_spec, run_cfs_compression,
        cfs_web_crippling_spec, run_cfs_web_crippling,
    )
    ctx.tools.register("structural_cfs_flexure",       cfs_flexure_spec,        run_cfs_flexure)
    ctx.tools.register("structural_cfs_compression",   cfs_compression_spec,    run_cfs_compression)
    ctx.tools.register("structural_cfs_web_crippling", cfs_web_crippling_spec,  run_cfs_web_crippling)

    # TMS 402-16 Masonry ASD (new — 2026-05-25)
    from kerf_structural.masonry import (
        masonry_flexure_spec, run_masonry_flexure,
        masonry_shear_spec, run_masonry_shear,
        masonry_axial_spec, run_masonry_axial,
    )
    ctx.tools.register("structural_masonry_flexure", masonry_flexure_spec, run_masonry_flexure)
    ctx.tools.register("structural_masonry_shear",   masonry_shear_spec,   run_masonry_shear)
    ctx.tools.register("structural_masonry_axial",   masonry_axial_spec,   run_masonry_axial)

    provides = [
        "structural.rc-beam",
        "structural.steel-beam",
        "structural.rebar-detailing",
        "structural.load-combinations",
        "structural.aisc-compression",
        "structural.aisc-flexure",
        "structural.aisc-combined",
        "structural.aisc-member-check",
        "structural.cfs-flexure",
        "structural.cfs-compression",
        "structural.cfs-web-crippling",
        "structural.masonry-flexure",
        "structural.masonry-shear",
        "structural.masonry-axial",
    ]

    try:
        from kerf_core.plugin import PluginManifest
        return PluginManifest(
            name="structural",
            version="0.1.0",
            provides=provides,
            depends=[],
        )
    except ImportError:
        return {
            "name": "structural",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }
