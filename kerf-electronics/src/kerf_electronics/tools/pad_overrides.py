import json
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register


def _get_pad(circuit_json: dict, pad_id: str) -> dict | None:
    if isinstance(circuit_json, list):
        for el in circuit_json:
            if isinstance(el, dict) and el.get('pcb_smtpad_id') == pad_id:
                return el
        return None
    if isinstance(circuit_json, dict):
        if circuit_json.get('pcb_smtpad_id') == pad_id:
            return circuit_json
        pads = circuit_json.get('pcb_smtpad') or circuit_json.get('pcb_smtpad')
        if isinstance(pads, list):
            for pad in pads:
                if isinstance(pad, dict) and pad.get('pcb_smtpad_id') == pad_id:
                    return pad
    return None


set_pad_mask_override_spec = ToolSpec(
    name="set_pad_mask_override",
    description=(
        "Set or update the solder-mask aperture expansion for a specific SMT pad. "
        "Positive expansion_mm opens the mask window (removes mask), "
        "e.g. for a QFN exposed thermal pad where no solder mask should cover the pad. "
        "Pass expansion_mm=0 to suppress mask entirely if the pad's own mask_override is used."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "pad_id": {"type": "string"},
            "expansion_mm": {"type": "number"},
        },
        "required": ["circuit_json", "pad_id", "expansion_mm"],
    },
)


@register(set_pad_mask_override_spec, write=True)
async def set_pad_mask_override(ctx: Any, args: bytes) -> str:
    try:
        kwargs = json.loads(args)
    except Exception as e:
        return err_payload(str(e), "PARSE_ERROR")

    circuit_json = kwargs.get("circuit_json")
    pad_id = kwargs.get("pad_id")
    expansion_mm = kwargs.get("expansion_mm")

    if not isinstance(expansion_mm, (int, float)) or expansion_mm < 0:
        return err_payload("expansion_mm must be a non-negative number", "VALIDATION_ERROR")

    pad = _get_pad(circuit_json, pad_id)
    if pad is None:
        return err_payload(f"pad not found: {pad_id}", "NOT_FOUND")

    pad["mask_override"] = {"expansion_mm": float(expansion_mm)}
    return ok_payload({"circuit_json": circuit_json, "pad_id": pad_id, "expansion_mm": expansion_mm})


set_pad_paste_override_spec = ToolSpec(
    name="set_pad_paste_override",
    description=(
        "Set or update the solder-paste stencil aperture for a specific SMT pad. "
        "Use scale (< 1.0) to reduce paste coverage for fine-pitch parts. "
        "Use offset_mm to shift the aperture. "
        "Use polygon to define a fully custom aperture shape."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "pad_id": {"type": "string"},
            "scale": {"type": "number"},
            "offset_mm": {"type": "number"},
            "polygon": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
            },
        },
        "required": ["circuit_json", "pad_id"],
    },
)


@register(set_pad_paste_override_spec, write=True)
async def set_pad_paste_override(ctx: Any, args: bytes) -> str:
    try:
        kwargs = json.loads(args)
    except Exception as e:
        return err_payload(str(e), "PARSE_ERROR")

    circuit_json = kwargs.get("circuit_json")
    pad_id = kwargs.get("pad_id")
    scale = kwargs.get("scale")
    offset_mm = kwargs.get("offset_mm")
    polygon = kwargs.get("polygon")

    if scale is not None and (not isinstance(scale, (int, float)) or scale < 0):
        return err_payload("scale must be a non-negative number", "VALIDATION_ERROR")
    if offset_mm is not None and not isinstance(offset_mm, (int, float)):
        return err_payload("offset_mm must be a number", "VALIDATION_ERROR")
    if polygon is not None:
        if not isinstance(polygon, list) or len(polygon) < 3:
            return err_payload("polygon must be an array of at least 3 [x, y] points", "VALIDATION_ERROR")

    pad = _get_pad(circuit_json, pad_id)
    if pad is None:
        return err_payload(f"pad not found: {pad_id}", "NOT_FOUND")

    override = {}
    if scale is not None:
        override["scale"] = float(scale)
    if offset_mm is not None:
        override["offset_mm"] = float(offset_mm)
    if polygon is not None:
        override["polygon"] = polygon

    pad["paste_override"] = override
    return ok_payload({"circuit_json": circuit_json, "pad_id": pad_id, "paste_override": override})


clear_pad_overrides_spec = ToolSpec(
    name="clear_pad_overrides",
    description="Remove mask_override and paste_override from a specific pad, reverting to board defaults.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "pad_id": {"type": "string"},
        },
        "required": ["circuit_json", "pad_id"],
    },
)


@register(clear_pad_overrides_spec, write=True)
async def clear_pad_overrides(ctx: Any, args: bytes) -> str:
    try:
        kwargs = json.loads(args)
    except Exception as e:
        return err_payload(str(e), "PARSE_ERROR")

    circuit_json = kwargs.get("circuit_json")
    pad_id = kwargs.get("pad_id")

    pad = _get_pad(circuit_json, pad_id)
    if pad is None:
        return err_payload(f"pad not found: {pad_id}", "NOT_FOUND")

    if "mask_override" in pad:
        del pad["mask_override"]
    if "paste_override" in pad:
        del pad["paste_override"]

    return ok_payload({"circuit_json": circuit_json, "pad_id": pad_id})