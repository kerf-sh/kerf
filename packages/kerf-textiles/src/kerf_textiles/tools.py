"""
kerf_textiles.tools
===================
LLM tool spec + handler for textiles_generate.
"""

from __future__ import annotations

from typing import Any

textiles_generate_spec = {
    "name": "textiles_generate",
    "description": (
        "Generate a textile weave or knit structure. "
        "Returns the cell matrix, float/density statistics, and SVG preview."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["weave", "knit"],
                "description": "Whether to generate a weave or knit structure.",
            },
            "structure": {
                "type": "string",
                "description": (
                    "For weave: 'plain', 'twill', 'satin', 'jacquard'. "
                    "For knit: 'jersey', 'rib', 'interlock'."
                ),
            },
            "params": {
                "type": "object",
                "description": "Structure-specific parameters (over, under, shafts, gauge, etc.).",
            },
        },
        "required": ["type", "structure"],
    },
}


async def run_textiles_generate(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for the textiles_generate LLM tool."""
    gen_type = params.get("type", "weave")
    structure = params.get("structure", "plain")
    extra = params.get("params", {}) or {}

    if gen_type == "weave":
        from kerf_textiles.weave import plain_weave, twill_weave, satin_weave
        from kerf_textiles.export import weave_to_svg, weave_to_json
        import json

        if structure == "plain":
            result = plain_weave()
        elif structure == "twill":
            result = twill_weave(
                over=extra.get("over", 2),
                under=extra.get("under", 1),
                direction=extra.get("direction", "RH"),
            )
        elif structure == "satin":
            result = satin_weave(
                shafts=extra.get("shafts", 5),
                move=extra.get("move", 2),
            )
        else:
            return {"error": f"unknown weave structure: {structure}"}

        return {
            "name": result.name,
            "float_stats": result.float_stats,
            "analytic_warp_mean_float": result.analytic_warp_mean_float,
            "analytic_weft_mean_float": result.analytic_weft_mean_float,
            "svg": weave_to_svg(result),
        }

    elif gen_type == "knit":
        from kerf_textiles.knit import jersey_knit, rib_knit, interlock_knit
        from kerf_textiles.export import knit_to_svg

        gauge = extra.get("gauge", 5.0)
        courses_per_cm = extra.get("courses_per_cm", 7.0)
        needles = extra.get("needles", 10)
        courses = extra.get("courses", 10)

        if structure == "jersey":
            result = jersey_knit(needles=needles, courses=courses,
                                 gauge=gauge, courses_per_cm=courses_per_cm)
        elif structure == "rib":
            result = rib_knit(
                knit_count=extra.get("knit_count", 1),
                purl_count=extra.get("purl_count", 1),
                needles=needles, courses=courses,
                gauge=gauge, courses_per_cm=courses_per_cm,
            )
        elif structure == "interlock":
            result = interlock_knit(needles=needles, courses=courses,
                                    gauge=gauge, courses_per_cm=courses_per_cm)
        else:
            return {"error": f"unknown knit structure: {structure}"}

        return {
            "name": result.name,
            "density_stats": result.density_stats,
            "svg": knit_to_svg(result),
        }

    return {"error": f"unknown type: {gen_type}"}


# ---------------------------------------------------------------------------
# textiles_cloth_drape
# ---------------------------------------------------------------------------

textiles_cloth_drape_spec = {
    "name": "textiles_cloth_drape",
    "description": (
        "Cloth drape simulation using a mass-spring model.  "
        "Three modes:\n"
        "  'sphere'  — drape a square cloth over a sphere (Bridson 2003 validation).\n"
        "  'disc'    — circular cloth over a cylindrical pedestal (BS 5058 drape coefficient).\n"
        "  'free'    — rectangular cloth with pinned top corners, hanging freely.\n"
        "Returns convergence flag, max sag, drape coefficient (disc mode only), "
        "energy plateau status, and simulation summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["sphere", "disc", "free"],
                "description": "Drape scenario. Default 'sphere'.",
            },
            "cloth_size": {
                "type": "number",
                "description": "(sphere/free) Side length of the square cloth (m). Default 0.8.",
            },
            "sphere_radius": {
                "type": "number",
                "description": "(sphere) Sphere radius (m). Default 0.25.",
            },
            "cloth_radius": {
                "type": "number",
                "description": "(disc) Cloth circle radius (m). Default 0.14.",
            },
            "disc_radius": {
                "type": "number",
                "description": "(disc) Supporting disc/pedestal radius (m). Default 0.07.",
            },
            "k_bend": {
                "type": "number",
                "description": "Bending stiffness (N/m). Higher = stiffer fabric. Default 4.0.",
            },
            "steps": {
                "type": "integer",
                "description": "Maximum simulation steps. Default 1000 (fast preview).",
            },
        },
        "required": [],
    },
}


async def run_textiles_cloth_drape(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for the textiles_cloth_drape LLM tool."""
    mode = params.get("mode", "sphere")
    steps = int(params.get("steps", 1000))

    try:
        if mode == "sphere":
            from kerf_textiles.drape import drape_over_sphere
            cloth_size = float(params.get("cloth_size", 0.8))
            sphere_radius = float(params.get("sphere_radius", 0.25))
            result = drape_over_sphere(
                cloth_size=cloth_size,
                sphere_radius=sphere_radius,
                rows=12,
                cols=12,
                steps=steps,
            )
            return {
                "ok": True,
                "mode": "sphere",
                "cloth_size_m": cloth_size,
                "sphere_radius_m": sphere_radius,
                "converged": result.converged,
                "steps_taken": result.steps_taken,
                "no_penetration": result.no_penetration,
                "max_penetration_m": round(result.max_penetration, 6),
                "energy_plateau": result.energy_plateau,
                "symmetry_error_m": round(result.symmetry_error, 6),
                "n_energy_samples": len(result.energy_history),
            }

        elif mode == "disc":
            from kerf_textiles.drape import drape_on_disc
            cloth_radius = float(params.get("cloth_radius", 0.14))
            disc_radius = float(params.get("disc_radius", 0.07))
            k_bend = float(params.get("k_bend", 4.0))
            result = drape_on_disc(
                cloth_radius=cloth_radius,
                disc_radius=disc_radius,
                k_bend=k_bend,
                steps=steps,
            )
            return {
                "ok": True,
                "mode": "disc",
                "cloth_radius_m": cloth_radius,
                "disc_radius_m": disc_radius,
                "converged": result.converged,
                "steps_taken": result.steps_taken,
                "drape_coefficient": round(result.drape_coefficient, 4) if result.drape_coefficient is not None else None,
                "max_sag_m": round(result.max_sag, 6),
                "note": "Drape coefficient 0=limp, 1=stiff (BS 5058 / ASTM D 4399)",
            }

        elif mode == "free":
            from kerf_textiles.drape import drape_simulate
            cloth_size = float(params.get("cloth_size", 0.8))
            rows = 12
            cols = 12
            spacing = cloth_size / (cols - 1)
            result = drape_simulate(
                rows=rows,
                cols=cols,
                spacing=spacing,
                pin_indices=[(0, 0), (0, cols - 1)],
                steps=steps,
            )
            return {
                "ok": True,
                "mode": "free",
                "cloth_size_m": cloth_size,
                "converged": result.converged,
                "steps_taken": result.steps_taken,
                "max_sag_m": round(result.max_sag, 6),
                "n_energy_samples": len(result.energy_history),
            }

        else:
            return {"ok": False, "error": f"unknown mode: {mode!r}; choose 'sphere', 'disc', or 'free'"}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}
