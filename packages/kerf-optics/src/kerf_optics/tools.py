"""
kerf_optics LLM tools — paraxial ray-trace and lens design.

Registered via plugin.py at startup.

Tools
-----
optics_trace_ray    — trace a ray (or bundle) through a multi-element lens
                      system and return spot size / focal length.
optics_lens_design  — first-order design helper: given target EFL and object
                      distance, solve for element parameters.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_optics._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# optics_trace_ray
# ---------------------------------------------------------------------------

optics_trace_ray_spec = ToolSpec(
    name="optics_trace_ray",
    description=(
        "Trace a ray (or a ray bundle) through a multi-element paraxial lens "
        "system using the ABCD ray-transfer matrix formalism.  Returns ray "
        "heights at each surface, effective focal length, and RMS spot radius "
        "at the exit plane.  Supports thin lenses, free-space gaps, curved "
        "interfaces, mirrors, and aperture stops."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": (
                    "Ordered list of optical elements (first = closest to source). "
                    "Each element is a dict with a 'type' key and type-specific "
                    "parameters:\n"
                    "  {type:'thin_lens', f:<focal_length_m>}\n"
                    "  {type:'free_space', d:<distance_m>, n:<index, default 1.0>}\n"
                    "  {type:'curved_interface', R:<radius_m>, n1:<from_index>, n2:<to_index>}\n"
                    "  {type:'mirror', R:<radius_m>}\n"
                    "  {type:'aperture', diameter:<m>}\n"
                    "  {type:'detector'}"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                    },
                    "required": ["type"],
                },
                "minItems": 1,
            },
            "rays": {
                "type": "array",
                "description": (
                    "Ray bundle: list of [y0, nu0] initial ray states. "
                    "y0 = height (m), nu0 = reduced angle n*theta. "
                    "Default: [[0.001, 0.0]] (on-axis marginal ray, h=1 mm)."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        },
        "required": ["elements"],
    },
)


def _build_element(spec: dict):
    """Deserialise an element dict into the appropriate Element object."""
    from kerf_optics.lens_system import (
        ThinLens, FreeSpace, CurvedInterface, Mirror, Aperture, Detector
    )

    etype = spec.get("type", "").lower()
    if etype == "thin_lens":
        return ThinLens(f=float(spec["f"]))
    elif etype == "free_space":
        return FreeSpace(d=float(spec["d"]), n=float(spec.get("n", 1.0)))
    elif etype == "curved_interface":
        return CurvedInterface(
            R=float(spec["R"]),
            n1=float(spec["n1"]),
            n2=float(spec["n2"]),
        )
    elif etype == "mirror":
        return Mirror(R=float(spec["R"]))
    elif etype == "aperture":
        return Aperture(diameter=float(spec["diameter"]))
    elif etype == "detector":
        return Detector()
    else:
        raise ValueError(f"unknown element type: {spec.get('type')!r}")


async def run_optics_trace_ray(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_optics.lens_system import LensSystem

        raw_elements = args["elements"]
        elements = [_build_element(e) for e in raw_elements]

        raw_rays = args.get("rays")
        if raw_rays is None:
            rays = [(0.001, 0.0)]  # default: 1 mm marginal ray
        else:
            rays = [(float(r[0]), float(r[1])) for r in raw_rays]

        system = LensSystem(elements)
        M = system.system_matrix()
        histories = system.trace_bundle(rays)

        # Spot diagram
        spot = system.spot_diagram()

        # EFL if system has power
        C = M[1, 0]
        efl = (-1.0 / C) if abs(C) > 1e-14 else None

        # Format ray histories
        ray_data = []
        for i, hist in enumerate(histories):
            ray_data.append({
                "ray_index": i,
                "y0": hist[0][0],
                "nu0": hist[0][1],
                "surfaces": [
                    {"y": round(y, 8), "nu": round(nu, 8)}
                    for y, nu in hist[1:]
                ],
                "final_height": round(hist[-1][0], 8),
            })

        payload: dict[str, Any] = {
            "n_elements": len(elements),
            "efl": round(efl, 8) if efl is not None else None,
            "system_matrix": {
                "A": round(M[0, 0], 8),
                "B": round(M[0, 1], 8),
                "C": round(M[1, 0], 8),
                "D": round(M[1, 1], 8),
            },
            "rays": ray_data,
            "spot": {
                "rms_spot_m": round(spot["rms_spot"], 10),
                "n_rays": spot["n_rays"],
            },
        }
        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "OPTICS_ERROR")


# ---------------------------------------------------------------------------
# optics_lens_design
# ---------------------------------------------------------------------------

optics_lens_design_spec = ToolSpec(
    name="optics_lens_design",
    description=(
        "First-order paraxial lens design helper. Given a target effective "
        "focal length (EFL) and conjugate distances (object and image), "
        "solves for the lens arrangement and returns the thin-lens system "
        "parameters.  For a single-lens system, uses the thin-lens equation "
        "1/f = 1/di - 1/do. For a two-lens telephoto, computes the "
        "separation required to achieve the target EFL."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target_efl": {
                "type": "number",
                "description": "Target effective focal length in metres.",
            },
            "object_distance": {
                "type": "number",
                "description": "Object distance (m) — positive = real object to the left.",
            },
            "design_type": {
                "type": "string",
                "enum": ["single", "telephoto"],
                "description": "'single' (one thin lens) or 'telephoto' (two lenses). Default 'single'.",
            },
            "f1": {
                "type": "number",
                "description": "(telephoto only) Focal length of the first element (m).",
            },
            "f2": {
                "type": "number",
                "description": "(telephoto only) Focal length of the second element (m). "
                               "If omitted, solved from target_efl and f1.",
            },
        },
        "required": ["target_efl", "object_distance"],
    },
)


async def run_optics_lens_design(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_optics.lens_system import LensSystem, FreeSpace, ThinLens
        from kerf_optics.ray_transfer import focal_length as _efl, image_distance as _imgdist

        target_efl = float(args["target_efl"])
        do = float(args["object_distance"])
        design_type = args.get("design_type", "single")

        if design_type == "single":
            # Thin-lens equation: 1/di = 1/f + 1/do  (note: do is positive)
            # Using sign convention di = 1/(1/f - 1/do) for do positive
            f = target_efl
            # image distance from thin lens equation
            if abs(1.0 / f - 1.0 / do) < 1e-14:
                raise ValueError("object at the focal point; image at infinity")
            di = 1.0 / (1.0 / f - 1.0 / do)

            system = LensSystem([FreeSpace(do), ThinLens(f), FreeSpace(di)])
            M = system.system_matrix()

            payload = {
                "design_type": "single",
                "f": f,
                "object_distance": do,
                "image_distance": round(di, 6),
                "efl_achieved": round(_efl(ThinLens(f).matrices()[0]), 6),
                "magnification": round(di / do, 6),
                "elements": [
                    {"type": "free_space", "d": do},
                    {"type": "thin_lens", "f": f},
                    {"type": "free_space", "d": round(di, 6)},
                ],
            }

        elif design_type == "telephoto":
            f1 = float(args.get("f1", target_efl * 1.5))
            if "f2" in args:
                f2 = float(args["f2"])
                # Compute separation from EFL formula:
                #   1/EFL = 1/f1 + 1/f2 - d/(f1*f2)  →  d = (1/f1 + 1/f2 - 1/EFL) * f1*f2
                d = (1.0 / f1 + 1.0 / f2 - 1.0 / target_efl) * f1 * f2
            else:
                # Solve f2 from EFL formula with a default separation d = f1/4
                d = f1 / 4.0
                # 1/EFL = 1/f1 + 1/f2 - d/(f1*f2)
                # 1/f2 = 1/EFL - 1/f1 + d/(f1*f2) — needs rearrangement
                # 1/f2 * (1 - d/f1) = 1/EFL - 1/f1
                # (1/f2) = (1/EFL - 1/f1) / (1 - d/f1)
                denom = 1.0 - d / f1
                if abs(denom) < 1e-14:
                    raise ValueError(f"degenerate telephoto: d == f1 ({f1})")
                inv_f2 = (1.0 / target_efl - 1.0 / f1) / denom
                if abs(inv_f2) < 1e-14:
                    raise ValueError("f2 → infinity; unsolvable telephoto")
                f2 = 1.0 / inv_f2

            # Build system up to lens2 (no image plane yet) and find image distance
            pre_system = LensSystem([FreeSpace(do), ThinLens(f1), FreeSpace(d), ThinLens(f2)])
            M = pre_system.system_matrix()

            # Image is located where height of an on-axis ray = 0; for ABCD: di = -D/C
            C = M[1, 0]
            if abs(C) < 1e-14:
                raise ValueError("telephoto system has no power")
            achieved_efl = -1.0 / C
            di = -M[1, 1] / C  # image distance from last element

            payload = {
                "design_type": "telephoto",
                "f1": round(f1, 6),
                "f2": round(f2, 6),
                "separation": round(d, 6),
                "object_distance": do,
                "image_distance_from_lens2": round(di, 6),
                "efl_achieved": round(achieved_efl, 6),
                "elements": [
                    {"type": "free_space", "d": do},
                    {"type": "thin_lens", "f": round(f1, 6)},
                    {"type": "free_space", "d": round(d, 6)},
                    {"type": "thin_lens", "f": round(f2, 6)},
                    {"type": "free_space", "d": round(di, 6)},
                ],
            }

        else:
            return err_payload(f"unknown design_type: {design_type!r}", "BAD_ARGS")

        return ok_payload(payload)

    except Exception as exc:
        return err_payload(str(exc), "OPTICS_DESIGN_ERROR")
