"""
kerf_cad_core.steelconn.tools — LLM tool wrappers for steel connection design.

Registers ten tools with the Kerf tool registry:

  bolt_shear_capacity      — AISC J3.6 bolt shear strength
  bolt_bearing_capacity    — AISC J3.10 bearing on connected material
  bolt_tension_capacity    — AISC J3.6 bolt tension strength
  slip_critical_capacity   — AISC J3.8 slip-critical connection
  block_shear_capacity     — AISC J4.3 block shear rupture
  bolt_group_eccentric     — eccentric bolt group (IC + elastic methods)
  fillet_weld_capacity     — AISC J2.4 fillet weld group capacity
  weld_group_elastic_vector — elastic vector method for weld group
  electrode_strength       — electrode classification strength table
  base_plate_bearing       — AISC J8 column base plate bearing check

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
AISC 360-22 — Specification for Structural Steel Buildings
AISC Steel Construction Manual, 16th edition

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.steelconn.connections import (
    bolt_shear_capacity,
    bolt_bearing_capacity,
    bolt_tension_capacity,
    slip_critical_capacity,
    block_shear_capacity,
    bolt_group_eccentric,
    fillet_weld_capacity,
    weld_group_elastic_vector,
    electrode_strength,
    base_plate_bearing,
)


# ---------------------------------------------------------------------------
# Tool: electrode_strength
# ---------------------------------------------------------------------------

_electrode_strength_spec = ToolSpec(
    name="electrode_strength",
    description=(
        "Return tabulated Fexx (electrode classification strength) for a standard "
        "SMAW/FCAW electrode designation.\n"
        "\n"
        "Supported: E60, E70, E80, E90, E100, E110.\n"
        "\n"
        "Returns Fexx_Pa and Fexx_ksi.\n"
        "Errors: {ok:false, reason} for unknown designation.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {
                "type": "string",
                "enum": ["E60", "E70", "E80", "E90", "E100", "E110"],
                "description": "Electrode designation per AWS A5.1/A5.20.",
            },
        },
        "required": ["designation"],
    },
)


@register(_electrode_strength_spec, write=False)
async def run_electrode_strength(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("designation") is None:
        return json.dumps({"ok": False, "reason": "designation is required"})
    return ok_payload(electrode_strength(a["designation"]))


# ---------------------------------------------------------------------------
# Tool: bolt_shear_capacity
# ---------------------------------------------------------------------------

_bolt_shear_spec = ToolSpec(
    name="bolt_shear_capacity",
    description=(
        "Compute nominal bolt shear strength per AISC 360-22 J3.6.\n"
        "\n"
        "Rn = Fnv × Ab × n_bolts × shear_planes\n"
        "\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).  Returns Rn, design capacity, "
        "utilization ratio, and governing limit state.\n"
        "\n"
        "Common Fnv values (MPa):\n"
        "  A325N (threads in plane): 372 MPa\n"
        "  A325X (threads excluded): 462 MPa\n"
        "  A490N: 457 MPa,  A490X: 572 MPa\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Ab": {
                "type": "number",
                "description": "Gross bolt cross-sectional area (mm²). Must be > 0.",
            },
            "Fnv": {
                "type": "number",
                "description": "Nominal shear stress of bolt (Pa). See AISC Table J3.2.",
            },
            "n_bolts": {
                "type": "integer",
                "description": "Number of bolts. Must be >= 1.",
            },
            "shear_planes": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Shear planes: 1 (single shear) or 2 (double shear). Default 1.",
            },
            "Vu": {
                "type": "number",
                "description": "Applied shear force (N). Used to compute utilization ratio.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "Design method: 'LRFD' (default, φ=0.75) or 'ASD' (Ω=2.00).",
            },
        },
        "required": ["Ab", "Fnv", "n_bolts"],
    },
)


@register(_bolt_shear_spec, write=False)
async def run_bolt_shear_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("Ab", "Fnv", "n_bolts"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("shear_planes", "Vu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(bolt_shear_capacity(a["Ab"], a["Fnv"], a["n_bolts"], **kw))


# ---------------------------------------------------------------------------
# Tool: bolt_bearing_capacity
# ---------------------------------------------------------------------------

_bolt_bearing_spec = ToolSpec(
    name="bolt_bearing_capacity",
    description=(
        "Compute bolt bearing strength on connected material (AISC 360-22 J3.10).\n"
        "\n"
        "Deformation-controlled: Rn = 2.4 × d × t × Fu × n_bolts\n"
        "Clear-distance check:   Rn = 1.2 × lc × t × Fu × n_bolts  (if lc given)\n"
        "Governing (lesser) value is reported.\n"
        "\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fu": {
                "type": "number",
                "description": "Ultimate tensile stress of connected material (Pa).",
            },
            "t": {
                "type": "number",
                "description": "Thickness of connected material (mm). Must be > 0.",
            },
            "d": {
                "type": "number",
                "description": "Nominal bolt diameter (mm). Must be > 0.",
            },
            "n_bolts": {
                "type": "integer",
                "description": "Number of bolts. Must be >= 1.",
            },
            "lc": {
                "type": "number",
                "description": (
                    "Clear distance in direction of force (mm). "
                    "If provided, the 1.2lc·t·Fu check is also evaluated."
                ),
            },
            "Vu": {
                "type": "number",
                "description": "Applied shear force (N). Used for utilization.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default) or 'ASD'.",
            },
        },
        "required": ["Fu", "t", "d", "n_bolts"],
    },
)


@register(_bolt_bearing_spec, write=False)
async def run_bolt_bearing_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("Fu", "t", "d", "n_bolts"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("lc", "Vu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(bolt_bearing_capacity(a["Fu"], a["t"], a["d"], a["n_bolts"], **kw))


# ---------------------------------------------------------------------------
# Tool: bolt_tension_capacity
# ---------------------------------------------------------------------------

_bolt_tension_spec = ToolSpec(
    name="bolt_tension_capacity",
    description=(
        "Compute nominal bolt tension strength (AISC 360-22 J3.6).\n"
        "\n"
        "Rn = Fnt × Ab × n_bolts\n"
        "\n"
        "Common Fnt values (MPa): A307=310, A325=621, A490=780.\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Ab": {
                "type": "number",
                "description": "Gross bolt area (mm²). Must be > 0.",
            },
            "Fnt": {
                "type": "number",
                "description": "Nominal tensile stress of bolt (Pa). See AISC Table J3.2.",
            },
            "n_bolts": {
                "type": "integer",
                "description": "Number of bolts in tension. Must be >= 1.",
            },
            "Tu": {
                "type": "number",
                "description": "Applied tensile force (N). Used for utilization.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default) or 'ASD'.",
            },
        },
        "required": ["Ab", "Fnt", "n_bolts"],
    },
)


@register(_bolt_tension_spec, write=False)
async def run_bolt_tension_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("Ab", "Fnt", "n_bolts"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("Tu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(bolt_tension_capacity(a["Ab"], a["Fnt"], a["n_bolts"], **kw))


# ---------------------------------------------------------------------------
# Tool: slip_critical_capacity
# ---------------------------------------------------------------------------

_slip_critical_spec = ToolSpec(
    name="slip_critical_capacity",
    description=(
        "Compute slip-critical connection capacity (AISC 360-22 J3.8).\n"
        "\n"
        "Rn = μ × 1.13 × hf × Pt × n_faying × n_bolts\n"
        "\n"
        "μ = 0.35 (Class A: unpainted clean mill scale) or 0.50 (Class B).\n"
        "hf = 1.0 (STD holes), 0.85 (oversized), 0.70 (short-slotted ⊥).\n"
        "Supports LRFD (φ=1.00) and ASD (Ω=1.50).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mu": {
                "type": "number",
                "description": (
                    "Mean slip coefficient: 0.35 (Class A) or 0.50 (Class B). "
                    "Must be in (0, 1]."
                ),
            },
            "Pt": {
                "type": "number",
                "description": (
                    "Minimum fastener tension (N). AISC Table J3.1: "
                    "3/4\" A325=133400N, 7/8\" A325=178200N."
                ),
            },
            "n_bolts": {
                "type": "integer",
                "description": "Number of bolts. Must be >= 1.",
            },
            "n_faying": {
                "type": "integer",
                "description": "Number of faying (slip) surfaces. Default 1.",
            },
            "hole_factor": {
                "type": "number",
                "description": (
                    "Hole factor hf: 1.0 standard round (default), "
                    "0.85 oversized, 0.70 short-slotted perpendicular to load."
                ),
            },
            "Vu": {
                "type": "number",
                "description": "Applied shear (N). Used for utilization.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default, φ=1.00) or 'ASD' (Ω=1.50).",
            },
        },
        "required": ["mu", "Pt", "n_bolts"],
    },
)


@register(_slip_critical_spec, write=False)
async def run_slip_critical_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("mu", "Pt", "n_bolts"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("n_faying", "hole_factor", "Vu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(slip_critical_capacity(a["mu"], a["Pt"], a["n_bolts"], **kw))


# ---------------------------------------------------------------------------
# Tool: block_shear_capacity
# ---------------------------------------------------------------------------

_block_shear_spec = ToolSpec(
    name="block_shear_capacity",
    description=(
        "Compute block shear rupture capacity (AISC 360-22 J4.3).\n"
        "\n"
        "Rn = min(\n"
        "    0.6·Fu·Anv + Ubs·Fu·Ant,   [shear rupture + tension rupture]\n"
        "    0.6·Fy·Agv + Ubs·Fu·Ant,   [shear yield  + tension rupture]\n"
        ")\n"
        "\n"
        "Ubs = 1.0 for uniform tension distribution (most connections).\n"
        "Ubs = 0.5 for non-uniform (beam webs with multiple bolt rows).\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fu": {
                "type": "number",
                "description": "Ultimate tensile stress of material (Pa). Must be > 0.",
            },
            "Fy": {
                "type": "number",
                "description": "Yield stress of material (Pa). Must be > 0.",
            },
            "Agv": {
                "type": "number",
                "description": "Gross area in shear (mm²). Must be > 0.",
            },
            "Anv": {
                "type": "number",
                "description": "Net area in shear (mm²). Must be > 0.",
            },
            "Ant": {
                "type": "number",
                "description": "Net area in tension (mm²). Must be > 0.",
            },
            "Ubs": {
                "type": "number",
                "description": (
                    "Tension stress distribution factor: 1.0 (default, uniform) "
                    "or 0.5 (non-uniform). Must be in (0, 1]."
                ),
            },
            "Vu": {
                "type": "number",
                "description": "Applied force (N). Used for utilization.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default) or 'ASD'.",
            },
        },
        "required": ["Fu", "Fy", "Agv", "Anv", "Ant"],
    },
)


@register(_block_shear_spec, write=False)
async def run_block_shear_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("Fu", "Fy", "Agv", "Anv", "Ant"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("Ubs", "Vu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(block_shear_capacity(a["Fu"], a["Fy"], a["Agv"], a["Anv"], a["Ant"], **kw))


# ---------------------------------------------------------------------------
# Tool: bolt_group_eccentric
# ---------------------------------------------------------------------------

_bolt_group_eccentric_spec = ToolSpec(
    name="bolt_group_eccentric",
    description=(
        "Compute eccentric bolt group capacity ratio.\n"
        "\n"
        "Two methods:\n"
        "  'IC' (default) — Instantaneous Center of Rotation (AISC Table 7-7 approach).\n"
        "  'elastic'      — Elastic Vector Method (conservative closed-form).\n"
        "\n"
        "Applies P at eccentricity e (mm) from the bolt-group centroid.\n"
        "Returns utilization ratio and governing bolt index.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bolt_coords": {
                "type": "array",
                "description": (
                    "List of [x_mm, y_mm] coordinates for each bolt. "
                    "Minimum 2 bolts required."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "minItems": 2,
            },
            "P": {
                "type": "number",
                "description": "Applied shear force (N). Must be > 0.",
            },
            "e": {
                "type": "number",
                "description": "Eccentricity of P from bolt-group centroid (mm). Must be >= 0.",
            },
            "method_beg": {
                "type": "string",
                "enum": ["IC", "elastic"],
                "description": "'IC' (default) or 'elastic'.",
            },
            "Vn_per_bolt": {
                "type": "number",
                "description": (
                    "Individual bolt design shear capacity (N). "
                    "Required for absolute utilization in 'elastic' method."
                ),
            },
        },
        "required": ["bolt_coords", "P", "e"],
    },
)


@register(_bolt_group_eccentric_spec, write=False)
async def run_bolt_group_eccentric(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("bolt_coords", "P", "e"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("method_beg", "Vn_per_bolt"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(bolt_group_eccentric(a["bolt_coords"], a["P"], a["e"], **kw))


# ---------------------------------------------------------------------------
# Tool: fillet_weld_capacity
# ---------------------------------------------------------------------------

_fillet_weld_spec = ToolSpec(
    name="fillet_weld_capacity",
    description=(
        "Compute fillet weld group capacity (AISC 360-22 J2.4).\n"
        "\n"
        "Rn = 0.60 × Fexx × (1 + 0.50·sin¹·⁵θ) × throat × L × n_welds\n"
        "\n"
        "D_sixteenths: weld size in sixteenths of an inch (e.g. 5 = 5/16\").\n"
        "θ = angle between weld axis and load direction (0° parallel, 90° transverse).\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D_sixteenths": {
                "type": "number",
                "description": "Weld size in sixteenths of an inch. E.g. 5 = 5/16\" weld.",
            },
            "L_weld": {
                "type": "number",
                "description": "Total effective weld length (mm). Must be > 0.",
            },
            "Fexx": {
                "type": "number",
                "description": "Electrode classification strength (Pa). E70 = 482.6e6 Pa.",
            },
            "angle_deg": {
                "type": "number",
                "description": (
                    "Angle between weld axis and load direction (degrees, 0–90). "
                    "0° = parallel (shear), 90° = transverse (tension). Default 0."
                ),
            },
            "n_welds": {
                "type": "integer",
                "description": "Number of identical weld lines (e.g. 2 for double-sided). Default 1.",
            },
            "Vu": {
                "type": "number",
                "description": "Applied load (N). Used for utilization.",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default) or 'ASD'.",
            },
        },
        "required": ["D_sixteenths", "L_weld", "Fexx"],
    },
)


@register(_fillet_weld_spec, write=False)
async def run_fillet_weld_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D_sixteenths", "L_weld", "Fexx"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    for k in ("angle_deg", "n_welds", "Vu", "method"):
        if k in a:
            kw[k] = a[k]
    return ok_payload(fillet_weld_capacity(a["D_sixteenths"], a["L_weld"], a["Fexx"], **kw))


# ---------------------------------------------------------------------------
# Tool: weld_group_elastic_vector
# ---------------------------------------------------------------------------

_weld_group_spec = ToolSpec(
    name="weld_group_elastic_vector",
    description=(
        "Elastic vector method for a general weld group under eccentric load.\n"
        "\n"
        "Each weld segment is described by (x0,y0,x1,y1,D_sixteenths,Fexx_Pa).\n"
        "The group centroid and polar moment of inertia (Iu) are computed "
        "analytically.\n"
        "\n"
        "Returns utilization ratio and governing stress.\n"
        "Supports LRFD (φ=0.75) and ASD (Ω=2.00).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "weld_segments": {
                "type": "array",
                "description": (
                    "List of weld segments. Each element: "
                    "[x0_mm, y0_mm, x1_mm, y1_mm, D_sixteenths, Fexx_Pa]."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 6,
                    "maxItems": 6,
                },
                "minItems": 1,
            },
            "P": {
                "type": "number",
                "description": "Applied force magnitude in +y direction (N). Must be > 0.",
            },
            "ex": {
                "type": "number",
                "description": "x-eccentricity of load from weld-group centroid (mm).",
            },
            "ey": {
                "type": "number",
                "description": "y-eccentricity of load from weld-group centroid (mm).",
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default) or 'ASD'.",
            },
        },
        "required": ["weld_segments", "P", "ex", "ey"],
    },
)


@register(_weld_group_spec, write=False)
async def run_weld_group_elastic_vector(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("weld_segments", "P", "ex", "ey"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    if "method" in a:
        kw["method"] = a["method"]
    return ok_payload(weld_group_elastic_vector(
        a["weld_segments"], a["P"], a["ex"], a["ey"], **kw
    ))


# ---------------------------------------------------------------------------
# Tool: base_plate_bearing
# ---------------------------------------------------------------------------

_base_plate_spec = ToolSpec(
    name="base_plate_bearing",
    description=(
        "Bearing stress check for a column base plate on grout/concrete "
        "(AISC 360-22 J8).\n"
        "\n"
        "Checks:  fp_actual = P / (B × N)  vs  fp_allow = φ × fp_prime  (LRFD)\n"
        "                                    or  fp_prime / Ω            (ASD)\n"
        "\n"
        "fp_prime is typically 0.85 × f'c (ACI 318 bearing limit).\n"
        "Default φ=0.65, Ω=2.31 per AISC J8.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {
                "type": "number",
                "description": "Column axial load (N). Must be > 0.",
            },
            "B": {
                "type": "number",
                "description": "Base plate width (mm). Must be > 0.",
            },
            "N": {
                "type": "number",
                "description": "Base plate length/depth (mm). Must be > 0.",
            },
            "fp_prime": {
                "type": "number",
                "description": (
                    "Allowable bearing pressure (Pa). Typically 0.85 × f'c. "
                    "For f'c=28 MPa: fp_prime = 0.85 × 28e6 = 23.8e6 Pa."
                ),
            },
            "method": {
                "type": "string",
                "enum": ["LRFD", "ASD"],
                "description": "'LRFD' (default, φ=0.65) or 'ASD' (Ω=2.31).",
            },
        },
        "required": ["P", "B", "N", "fp_prime"],
    },
)


@register(_base_plate_spec, write=False)
async def run_base_plate_bearing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("P", "B", "N", "fp_prime"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kw: dict = {}
    if "method" in a:
        kw["method"] = a["method"]
    return ok_payload(base_plate_bearing(a["P"], a["B"], a["N"], a["fp_prime"], **kw))
