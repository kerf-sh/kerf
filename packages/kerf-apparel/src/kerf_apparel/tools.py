"""
LLM tool definitions for kerf-apparel.

Registered tools
----------------
apparel_grade_bodice   — grade a bodice across a size run
apparel_add_seam       — add seam allowance to a named size block
apparel_make_marker    — nest pieces and report utilisation
"""

from __future__ import annotations

import json

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_apparel._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx

from kerf_apparel.blocks import get_measurements, bodice_front, bodice_back, sleeve, pants_front, pants_back
from kerf_apparel.grading import grade_bodice, grade_sleeve, grade_pants, bust_girth_from_piece
from kerf_apparel.seam_allowance import add_seam_allowance
from kerf_apparel.marker_making import make_marker


# ------------------------------------------------------------------ #
# apparel_grade_bodice                                                 #
# ------------------------------------------------------------------ #

grade_bodice_spec = ToolSpec(
    name="apparel_grade_bodice",
    description=(
        "Grade a bodice block across a size run. "
        "Returns bust girth and bounding-box dimensions for each size."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "base_size": {
                "type": "string",
                "description": "Base size, e.g. 'M', 'L', '10', '12'.",
            },
            "size_run": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional explicit size run, e.g. ['S','M','L']. Defaults to full alpha or numeric run.",
            },
        },
        "required": ["base_size"],
    },
)


@register(grade_bodice_spec, write=False)
async def run_grade_bodice(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    base_size = a.get("base_size", "").strip()
    if not base_size:
        return err_payload("base_size is required", "BAD_ARGS")

    size_run = a.get("size_run") or None

    try:
        graded = grade_bodice(base_size, size_run)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    result = {}
    for size in graded.size_run:
        front_key = f"{size}_front"
        front = graded.pieces.get(front_key)
        if not front:
            continue
        bb = front.bounding_box()
        result[size] = {
            "bust_girth_cm": bust_girth_from_piece(front),
            "width_cm": round(bb[2] - bb[0], 2),
            "height_cm": round(bb[3] - bb[1], 2),
        }

    return ok_payload({"base_size": base_size, "sizes": result})


# ------------------------------------------------------------------ #
# apparel_add_seam                                                     #
# ------------------------------------------------------------------ #

add_seam_spec = ToolSpec(
    name="apparel_add_seam",
    description=(
        "Add seam allowance to a standard block for a given size. "
        "Returns the expanded bounding box and area."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "enum": ["bodice_front", "bodice_back", "sleeve", "pants_front", "pants_back"],
                "description": "Which block to operate on.",
            },
            "size": {
                "type": "string",
                "description": "Size label, e.g. 'M', 'L', '12'.",
            },
            "seam_allowance_cm": {
                "type": "number",
                "description": "Seam allowance in cm (positive). Typical: 1.0 or 1.5.",
            },
        },
        "required": ["block", "size", "seam_allowance_cm"],
    },
)


@register(add_seam_spec, write=False)
async def run_add_seam(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    block_name = a.get("block", "").strip()
    size = a.get("size", "").strip()
    try:
        offset = float(a.get("seam_allowance_cm", 0))
    except (TypeError, ValueError):
        return err_payload("seam_allowance_cm must be a number", "BAD_ARGS")

    if offset <= 0:
        return err_payload("seam_allowance_cm must be positive", "BAD_ARGS")

    try:
        m = get_measurements(size)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    _generators = {
        "bodice_front": lambda m: bodice_front(m["bust"], m["waist"], m["hip"], m["back_length"]),
        "bodice_back": lambda m: bodice_back(m["bust"], m["waist"], m["hip"], m["back_length"]),
        "sleeve": lambda m: sleeve(m["bust"], m["sleeve_length"]),
        "pants_front": lambda m: pants_front(m["waist"], m["hip"], m["inseam"], m["rise"]),
        "pants_back": lambda m: pants_back(m["waist"], m["hip"], m["inseam"], m["rise"]),
    }
    gen = _generators.get(block_name)
    if not gen:
        return err_payload(f"unknown block {block_name!r}", "BAD_ARGS")

    piece = gen(m)
    with_sa = add_seam_allowance(piece, offset)

    bb_orig = piece.bounding_box()
    bb_new = with_sa.bounding_box()

    return ok_payload({
        "block": block_name,
        "size": size,
        "seam_allowance_cm": offset,
        "original_area_cm2": round(piece.area(), 2),
        "expanded_area_cm2": round(with_sa.area(), 2),
        "original_bbox": {
            "width": round(bb_orig[2] - bb_orig[0], 2),
            "height": round(bb_orig[3] - bb_orig[1], 2),
        },
        "expanded_bbox": {
            "width": round(bb_new[2] - bb_new[0], 2),
            "height": round(bb_new[3] - bb_new[1], 2),
        },
    })


# ------------------------------------------------------------------ #
# apparel_make_marker                                                  #
# ------------------------------------------------------------------ #

make_marker_spec = ToolSpec(
    name="apparel_make_marker",
    description=(
        "Nest pattern pieces for one size on a given fabric width using BL-fill heuristic. "
        "Reports fabric utilisation percentage."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "size": {
                "type": "string",
                "description": "Size label, e.g. 'M'.",
            },
            "blocks": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["bodice_front", "bodice_back", "sleeve", "pants_front", "pants_back"],
                },
                "description": "Which blocks to include in the marker.",
            },
            "fabric_width_cm": {
                "type": "number",
                "description": "Usable fabric width in cm. Typical: 150.",
            },
        },
        "required": ["size", "blocks", "fabric_width_cm"],
    },
)


# ---------------------------------------------------------------------------
# Tool: apparel_generate_block
# ---------------------------------------------------------------------------

generate_block_spec = ToolSpec(
    name="apparel_generate_block",
    description=(
        "Generate a single parametric pattern block from custom body measurements "
        "or a standard size. Supported blocks: bodice_front, bodice_back, sleeve, "
        "pants_front, pants_back. "
        "Returns the closed outline (list of [x,y] cm), bounding box, area (cm²), "
        "perimeter (cm), grain line, and measurement labels. "
        "Use 'size' for standard sizing (XS/S/M/L/XL/XXL or US 0–22) "
        "or provide individual measurements in cm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "enum": ["bodice_front", "bodice_back", "sleeve", "pants_front", "pants_back"],
                "description": "Which pattern block to generate.",
            },
            "size": {
                "type": "string",
                "description": (
                    "Standard size label (e.g. 'M', 'L', '12'). "
                    "If provided, overrides individual measurement fields."
                ),
            },
            "bust": {"type": "number", "description": "Bust circumference [cm]."},
            "waist": {"type": "number", "description": "Waist circumference [cm]."},
            "hip": {"type": "number", "description": "Hip circumference [cm]."},
            "back_length": {"type": "number", "description": "Back waist length (nape to waist) [cm]."},
            "sleeve_length": {"type": "number", "description": "Sleeve length [cm] (for sleeve block)."},
            "inseam": {"type": "number", "description": "Inseam length [cm] (for pants blocks)."},
            "rise": {"type": "number", "description": "Rise [cm] (for pants blocks)."},
            "ease_bust": {"type": "number", "description": "Bust ease to add [cm] (default 4)."},
            "ease_waist": {"type": "number", "description": "Waist ease to add [cm] (default 2)."},
            "ease_hip": {"type": "number", "description": "Hip ease to add [cm] (default 4)."},
        },
        "required": ["block"],
    },
)


@register(generate_block_spec, write=False)
async def run_generate_block(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    block_name = a.get("block", "").strip()
    if block_name not in ("bodice_front", "bodice_back", "sleeve", "pants_front", "pants_back"):
        return err_payload(f"unknown block {block_name!r}", "BAD_ARGS")

    # Resolve measurements — size table overrides individual fields if 'size' provided
    size = a.get("size", "").strip()
    if size:
        try:
            m = get_measurements(size)
        except ValueError as e:
            return err_payload(str(e), "BAD_ARGS")
    else:
        # Manual measurements
        m = {}
        for field_name in ("bust", "waist", "hip", "back_length", "sleeve_length", "inseam", "rise"):
            if field_name in a:
                try:
                    m[field_name] = float(a[field_name])
                except (TypeError, ValueError):
                    return err_payload(f"{field_name} must be a number", "BAD_ARGS")

    ease_bust = float(a.get("ease_bust", 4.0))
    ease_waist = float(a.get("ease_waist", 2.0))
    ease_hip = float(a.get("ease_hip", 4.0))

    try:
        if block_name == "bodice_front":
            piece = bodice_front(
                m["bust"], m["waist"], m["hip"], m["back_length"],
                ease_bust=ease_bust, ease_waist=ease_waist, ease_hip=ease_hip,
            )
        elif block_name == "bodice_back":
            piece = bodice_back(
                m["bust"], m["waist"], m["hip"], m["back_length"],
                ease_bust=ease_bust, ease_waist=ease_waist, ease_hip=ease_hip,
            )
        elif block_name == "sleeve":
            piece = sleeve(m["bust"], m["sleeve_length"])
        elif block_name == "pants_front":
            piece = pants_front(m["waist"], m["hip"], m["inseam"], m["rise"])
        elif block_name == "pants_back":
            piece = pants_back(m["waist"], m["hip"], m["inseam"], m["rise"])
        else:
            return err_payload(f"unknown block {block_name!r}", "BAD_ARGS")
    except KeyError as e:
        return err_payload(f"missing measurement: {e}", "BAD_ARGS")
    except Exception as e:
        return err_payload(str(e), "APPAREL_ERROR")

    bbox = piece.bounding_box()
    grain = None
    if piece.grain_line:
        grain = [[round(v, 2) for v in piece.grain_line[0]],
                 [round(v, 2) for v in piece.grain_line[1]]]

    return ok_payload({
        "block": block_name,
        "size": size if size else "custom",
        "outline": [[round(x, 3), round(y, 3)] for x, y in piece.outline],
        "n_points": len(piece.outline),
        "bounding_box_cm": {
            "min_x": round(bbox[0], 3),
            "min_y": round(bbox[1], 3),
            "max_x": round(bbox[2], 3),
            "max_y": round(bbox[3], 3),
            "width": round(bbox[2] - bbox[0], 3),
            "height": round(bbox[3] - bbox[1], 3),
        },
        "area_cm2": round(piece.area(), 2),
        "perimeter_cm": round(piece.perimeter(), 2),
        "grain_line": grain,
        "labels": {k: round(float(v), 3) for k, v in piece.labels.items()},
    })


@register(make_marker_spec, write=False)
async def run_make_marker(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    size = a.get("size", "").strip()
    block_names = a.get("blocks", [])
    try:
        fabric_width = float(a.get("fabric_width_cm", 0))
    except (TypeError, ValueError):
        return err_payload("fabric_width_cm must be a number", "BAD_ARGS")

    if fabric_width <= 0:
        return err_payload("fabric_width_cm must be positive", "BAD_ARGS")

    try:
        m = get_measurements(size)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    _generators = {
        "bodice_front": lambda m: bodice_front(m["bust"], m["waist"], m["hip"], m["back_length"]),
        "bodice_back": lambda m: bodice_back(m["bust"], m["waist"], m["hip"], m["back_length"]),
        "sleeve": lambda m: sleeve(m["bust"], m["sleeve_length"]),
        "pants_front": lambda m: pants_front(m["waist"], m["hip"], m["inseam"], m["rise"]),
        "pants_back": lambda m: pants_back(m["waist"], m["hip"], m["inseam"], m["rise"]),
    }

    pieces = []
    for bn in block_names:
        gen = _generators.get(bn)
        if not gen:
            return err_payload(f"unknown block {bn!r}", "BAD_ARGS")
        pieces.append(gen(m))

    result = make_marker(pieces, fabric_width)

    return ok_payload({
        "size": size,
        "fabric_width_cm": fabric_width,
        "marker_length_cm": round(result.marker_length, 2),
        "utilisation_pct": round(result.utilisation, 1),
        "unplaced": result.unplaced,
        "placements": [
            {
                "name": pp.name,
                "x": round(pp.x, 2),
                "y": round(pp.y, 2),
                "width": round(pp.width, 2),
                "height": round(pp.height, 2),
            }
            for pp in result.placements
        ],
    })
