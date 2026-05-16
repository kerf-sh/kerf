"""
kerf-cad-core: sheet metal bend table — T-4.

Per-material K-factor / bend-allowance / bend-deduction lookup by
material + thickness + inner radius + bend angle, with air-bend /
bottoming / coining process variants and spring-back estimate.

Public API
----------
bend_table(material, thickness, inner_radius, angle_deg, process)
    → {ok, k_factor, bend_allowance, bend_deduction, setback,
        neutral_axis_offset, spring_back_angle_deg}

apply_bend_table(flat_pattern, bends)
    → {ok, flat_length, bends:[{...}]}

custom_table_load(rows)
    → {ok, loaded}

LLM tools registered via @register, mirroring sheet_metal.py pattern.

Formula reference
-----------------
DIN 6935 / Machinery's Handbook (29th ed.) / SolidWorks Sheet Metal Help:
    Neutral-axis radius r_n = r + K·t
    Bend allowance  BA = (π/180)·angle·(r + K·t)
    Outside set-back OSSB = tan(angle/2)·(r + t)
    Bend deduction  BD = 2·OSSB − BA
    Spring-back: Δθ ≈ C_sb·(Y / E)·(r/t + 0.5)   (approx. Hosford §7)

K-factor as a function of r/t (DIN 6935 / common shop tables):
    r/t < 1   → K ≈ 0.33  (hard materials / severe bend)
    r/t 1–3   → K ≈ 0.33 + (r/t − 1)/2 × (K_max − 0.33)
    r/t ≥ 3   → K ≈ K_max  (material-specific ceiling)

Process modifiers (air-bend / bottoming / coining):
    air-bend   — K as computed above
    bottoming  — K × 0.90  (tool forces neutral axis inward ~10%)
    coining    — K × 1.10  (full-penetration coining; K may exceed 0.50)

Author: imranparuk
"""
from __future__ import annotations

import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401 — type annotation only


# ---------------------------------------------------------------------------
# Built-in material table
# ---------------------------------------------------------------------------

# Each entry: (K_min, K_max, yield_strength_MPa, elastic_modulus_GPa,
#              springback_coeff)
# K_min  — K-factor at r/t < 1 (severe bend, neutral axis moves inward)
# K_max  — K-factor at r/t ≥ 3 (gentle bend, neutral axis approaches 0.50)
# yield_strength_MPa, elastic_modulus_GPa — used in spring-back estimate
# springback_coeff — dimensionless multiplier in Δθ = C_sb·(Y/E)·(r/t + 0.5)

_MATERIAL_TABLE: dict[str, tuple[float, float, float, float, float]] = {
    # material_key:       K_min  K_max  Y(MPa)  E(GPa)  C_sb
    "mild_steel":         (0.33, 0.44,  250.0,  200.0,  0.78),
    "stainless":          (0.31, 0.38,  310.0,  193.0,  1.10),
    "aluminum_5052":      (0.40, 0.50,  195.0,   70.0,  0.65),
    "aluminum_6061":      (0.38, 0.48,  276.0,   69.0,  0.72),
    "brass":              (0.38, 0.46,  200.0,  100.0,  0.58),
    "copper":             (0.40, 0.50,  210.0,  120.0,  0.55),
}

# Normalised aliases so callers can use common strings
_ALIASES: dict[str, str] = {
    "mild steel":         "mild_steel",
    "ms":                 "mild_steel",
    "steel":              "mild_steel",
    "stainless steel":    "stainless",
    "ss":                 "stainless",
    "304":                "stainless",
    "316":                "stainless",
    "al5052":             "aluminum_5052",
    "al 5052":            "aluminum_5052",
    "5052":               "aluminum_5052",
    "al6061":             "aluminum_6061",
    "al 6061":            "aluminum_6061",
    "6061":               "aluminum_6061",
    "aluminium_5052":     "aluminum_5052",
    "aluminium_6061":     "aluminum_6061",
    "aluminium":          "aluminum_5052",
    "aluminum":           "aluminum_5052",
}

# Shop-override table: populated by custom_table_load().
# Key: (material_key, thickness_mm, inner_radius_mm, process) → k_factor
_CUSTOM_TABLE: dict[tuple, float] = {}


# ---------------------------------------------------------------------------
# Process modifiers
# ---------------------------------------------------------------------------

_PROCESS_K_MODIFIER: dict[str, float] = {
    "air_bend":   1.00,
    "air-bend":   1.00,
    "air":        1.00,
    "bottoming":  0.90,
    "bottom":     0.90,
    "coining":    1.10,
    "coin":       1.10,
}

_VALID_PROCESSES = {"air_bend", "bottoming", "coining"}


# ---------------------------------------------------------------------------
# Core calculation helpers
# ---------------------------------------------------------------------------

def _resolve_material(material: str) -> str | None:
    """Return canonical material key or None if unknown."""
    key = material.strip().lower().replace("-", "_")
    if key in _MATERIAL_TABLE:
        return key
    return _ALIASES.get(key)


def _resolve_process(process: str) -> str | None:
    """Return canonical process key or None if unknown."""
    p = process.strip().lower()
    canonical = _PROCESS_K_MODIFIER.get(p)
    if canonical is None:
        return None
    # Map to canonical name
    if p in ("air_bend", "air-bend", "air"):
        return "air_bend"
    if p in ("bottoming", "bottom"):
        return "bottoming"
    if p in ("coining", "coin"):
        return "coining"
    return None


def _k_from_r_over_t(r_over_t: float, k_min: float, k_max: float) -> float:
    """
    Interpolate K-factor linearly between k_min and k_max based on r/t.

    Region        r/t         K
    ─────────────────────────────
    Severe bend   < 1         k_min
    Transition    1 ≤ r/t < 3 linear interpolation
    Gentle bend   ≥ 3         k_max

    This approximates the DIN 6935 lookup table monotone behaviour.
    """
    if r_over_t < 1.0:
        return k_min
    if r_over_t >= 3.0:
        return k_max
    # Linear interpolation in [1, 3) → [k_min, k_max)
    t = (r_over_t - 1.0) / 2.0   # 0..1 within the transition band
    return k_min + t * (k_max - k_min)


def _compute_bend(
    material_key: str,
    thickness: float,
    inner_radius: float,
    angle_deg: float,
    process_key: str,
) -> dict:
    """
    Core bend-table calculation.  All dimensions in mm, angle in degrees.

    Returns a plain dict (no ok wrapper); the caller wraps.
    """
    k_min, k_max, yield_mpa, e_gpa, c_sb = _MATERIAL_TABLE[material_key]

    r_over_t = inner_radius / thickness

    # Check for shop override first
    override_key = (material_key, round(thickness, 4), round(inner_radius, 4), process_key)
    if override_key in _CUSTOM_TABLE:
        k = _CUSTOM_TABLE[override_key]
    else:
        k_air = _k_from_r_over_t(r_over_t, k_min, k_max)
        process_mod = _PROCESS_K_MODIFIER.get(process_key, 1.0)
        k = k_air * process_mod
        # Clamp to sane physical range
        k = max(0.01, min(0.99, k))

    # Neutral-axis offset (mm from inside surface)
    neutral_axis_offset = k * thickness

    # Bend allowance  BA = (π/180)·angle·(r + K·t)   [DIN 6935]
    angle_rad = math.radians(angle_deg)
    bend_allowance = angle_rad * (inner_radius + k * thickness)

    # Outside set-back  OSSB = tan(angle/2)·(r + t)
    half_rad = math.radians(angle_deg / 2.0)
    setback = math.tan(half_rad) * (inner_radius + thickness)

    # Bend deduction  BD = 2·OSSB − BA
    bend_deduction = 2.0 * setback - bend_allowance

    # Spring-back  Δθ ≈ C_sb·(Y/E)·(r/t + 0.5)   (Hosford approx.)
    # E in MPa for consistent units
    e_mpa = e_gpa * 1000.0
    spring_back_deg = math.degrees(c_sb * (yield_mpa / e_mpa) * (r_over_t + 0.5))

    return {
        "material": material_key,
        "process": process_key,
        "thickness_mm": thickness,
        "inner_radius_mm": inner_radius,
        "angle_deg": angle_deg,
        "r_over_t": round(r_over_t, 4),
        "k_factor": round(k, 6),
        "neutral_axis_offset_mm": round(neutral_axis_offset, 6),
        "bend_allowance_mm": round(bend_allowance, 6),
        "setback_mm": round(setback, 6),
        "bend_deduction_mm": round(bend_deduction, 6),
        "spring_back_angle_deg": round(spring_back_deg, 4),
    }


# ---------------------------------------------------------------------------
# Public Python API (importable directly by tests / kerf_core callers)
# ---------------------------------------------------------------------------

def bend_table(
    material: str,
    thickness: float,
    inner_radius: float,
    angle_deg: float,
    process: str = "air_bend",
) -> dict:
    """
    Look up bend parameters for a given material/process combination.

    Parameters
    ----------
    material:     Material name (e.g. "mild_steel", "stainless", "aluminum_5052").
    thickness:    Sheet thickness in mm.  Must be > 0.
    inner_radius: Inside bend radius in mm.  Must be > 0.
    angle_deg:    Bend angle in degrees, (0, 180].
    process:      "air_bend" (default), "bottoming", or "coining".

    Returns
    -------
    {"ok": True, ...} on success, {"ok": False, "reason": "..."} on error.
    Never raises.
    """
    try:
        material_key = _resolve_material(material)
        if material_key is None:
            known = sorted(_MATERIAL_TABLE)
            return {"ok": False, "reason": f"unknown material '{material}'; known: {known}"}

        process_norm = process.strip().lower()
        # Canonical key lookup
        if process_norm in ("air_bend", "air-bend", "air"):
            process_key = "air_bend"
        elif process_norm in ("bottoming", "bottom"):
            process_key = "bottoming"
        elif process_norm in ("coining", "coin"):
            process_key = "coining"
        else:
            return {"ok": False, "reason": f"unknown process '{process}'; valid: air_bend, bottoming, coining"}

        thickness = float(thickness)
        inner_radius = float(inner_radius)
        angle_deg = float(angle_deg)

        if thickness <= 0:
            return {"ok": False, "reason": f"thickness must be > 0; got {thickness}"}
        if inner_radius <= 0:
            return {"ok": False, "reason": f"inner_radius must be > 0; got {inner_radius}"}
        if angle_deg <= 0 or angle_deg > 180:
            return {"ok": False, "reason": f"angle_deg must be in (0, 180]; got {angle_deg}"}

        result = _compute_bend(material_key, thickness, inner_radius, angle_deg, process_key)
        return {"ok": True, **result}

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def apply_bend_table(
    flat_pattern: dict,
    bends: list[dict],
) -> dict:
    """
    Recompute the developed flat length of a multi-bend part using table-derived
    bend allowances rather than a scalar k_factor.

    Parameters
    ----------
    flat_pattern:
        Dict with at least:
            "base_length"   — straight length before first bend (mm)
        Typically the output dict from sheet_metal.compute_unfold or an
        existing flat_pattern node.

    bends:
        List of bend descriptors, each with:
            "material"      — material name (required)
            "thickness"     — sheet thickness mm (required)
            "inner_radius"  — inside bend radius mm (required)
            "angle_deg"     — bend angle degrees (required)
            "flange_length" — straight segment after this bend mm (required)
            "process"       — optional, default "air_bend"

    Returns
    -------
    {"ok": True, "flat_length": ..., "bends": [{...per-bend result...}]}
    or {"ok": False, "reason": "..."}.  Never raises.
    """
    try:
        base_length = float(flat_pattern.get("base_length", 0))
        if base_length <= 0:
            return {"ok": False, "reason": "flat_pattern.base_length must be > 0"}
        if not isinstance(bends, list) or len(bends) == 0:
            return {"ok": False, "reason": "bends must be a non-empty list"}

        total = base_length
        resolved_bends: list[dict] = []

        for i, b in enumerate(bends):
            mat = b.get("material", "")
            t = b.get("thickness")
            r = b.get("inner_radius")
            ang = b.get("angle_deg")
            fl = b.get("flange_length")
            proc = b.get("process", "air_bend")

            if not mat:
                return {"ok": False, "reason": f"bends[{i}].material is required"}
            for fname, fval in (("thickness", t), ("inner_radius", r),
                                ("angle_deg", ang), ("flange_length", fl)):
                if fval is None:
                    return {"ok": False, "reason": f"bends[{i}].{fname} is required"}

            bt = bend_table(mat, float(t), float(r), float(ang), proc)
            if not bt["ok"]:
                return {"ok": False, "reason": f"bends[{i}]: {bt['reason']}"}

            fl = float(fl)
            if fl <= 0:
                return {"ok": False, "reason": f"bends[{i}].flange_length must be > 0"}

            ba = bt["bend_allowance_mm"]
            total += ba + fl
            resolved_bends.append({
                "bend_index": i,
                "flange_length_mm": fl,
                **bt,
            })

        return {
            "ok": True,
            "base_length_mm": base_length,
            "flat_length_mm": round(total, 6),
            "bends": resolved_bends,
        }

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def custom_table_load(rows: list[dict]) -> dict:
    """
    Load shop-specific K-factor overrides into the module-level custom table.

    Each row must have:
        material      — material name (resolved via alias table)
        thickness     — sheet thickness mm
        inner_radius  — inside bend radius mm
        process       — "air_bend", "bottoming", or "coining"
        k_factor      — override K-factor (0 < k < 1)

    Returns {"ok": True, "loaded": N} or {"ok": False, "reason": "..."}.
    Never raises.
    """
    try:
        if not isinstance(rows, list):
            return {"ok": False, "reason": "rows must be a list of dicts"}

        loaded = 0
        for i, row in enumerate(rows):
            mat = row.get("material", "")
            mat_key = _resolve_material(mat)
            if mat_key is None:
                return {"ok": False, "reason": f"rows[{i}]: unknown material '{mat}'"}

            try:
                t = float(row["thickness"])
                r = float(row["inner_radius"])
                k = float(row["k_factor"])
            except (KeyError, TypeError, ValueError) as e:
                return {"ok": False, "reason": f"rows[{i}]: {e}"}

            proc_raw = row.get("process", "air_bend")
            proc_norm = proc_raw.strip().lower()
            if proc_norm in ("air_bend", "air-bend", "air"):
                proc_key = "air_bend"
            elif proc_norm in ("bottoming", "bottom"):
                proc_key = "bottoming"
            elif proc_norm in ("coining", "coin"):
                proc_key = "coining"
            else:
                return {"ok": False, "reason": f"rows[{i}]: unknown process '{proc_raw}'"}

            if k <= 0 or k >= 1:
                return {"ok": False, "reason": f"rows[{i}]: k_factor must be in (0, 1); got {k}"}

            _CUSTOM_TABLE[(mat_key, round(t, 4), round(r, 4), proc_key)] = k
            loaded += 1

        return {"ok": True, "loaded": loaded}

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# LLM tool: bend_table_lookup
# ---------------------------------------------------------------------------

_bend_table_lookup_spec = ToolSpec(
    name="bend_table_lookup",
    description=(
        "Look up sheet-metal bend parameters (K-factor, bend allowance, bend "
        "deduction, setback, neutral-axis offset, spring-back angle) for a "
        "given material, sheet thickness, inside bend radius, bend angle, and "
        "bend process. "
        "Built-in materials: mild_steel, stainless, aluminum_5052, "
        "aluminum_6061, brass, copper. "
        "Processes: air_bend (default), bottoming, coining. "
        "Formula: BA = (π/180)·angle·(r + K·t)  per DIN 6935. "
        "BD = 2·OSSB − BA where OSSB = tan(angle/2)·(r+t). "
        "Spring-back uses Hosford approximation. "
        "Returns {k_factor, bend_allowance_mm, bend_deduction_mm, setback_mm, "
        "neutral_axis_offset_mm, spring_back_angle_deg}. "
        "Use apply_bend_table_to_flat_pattern for full flat-length recomputation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": (
                    "Material name. Accepted values (case-insensitive): "
                    "mild_steel, stainless, aluminum_5052, aluminum_6061, "
                    "brass, copper. Common aliases also accepted."
                ),
            },
            "thickness": {
                "type": "number",
                "description": "Sheet thickness (mm). Must be > 0.",
            },
            "inner_radius": {
                "type": "number",
                "description": "Inside bend radius (mm). Must be > 0.",
            },
            "angle_deg": {
                "type": "number",
                "description": "Bend angle in degrees, in (0, 180].",
            },
            "process": {
                "type": "string",
                "enum": ["air_bend", "bottoming", "coining"],
                "description": (
                    "Bend process. "
                    "air_bend (default) — K interpolated from r/t; "
                    "bottoming — K × 0.90 (tool forces neutral axis inward); "
                    "coining — K × 1.10 (full-penetration coining)."
                ),
            },
        },
        "required": ["material", "thickness", "inner_radius", "angle_deg"],
    },
)


@register(_bend_table_lookup_spec, write=False)
async def run_bend_table_lookup(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    material     = a.get("material", "")
    thickness    = a.get("thickness")
    inner_radius = a.get("inner_radius")
    angle_deg    = a.get("angle_deg")
    process      = a.get("process", "air_bend")

    if not material:
        return err_payload("material is required", "BAD_ARGS")
    if thickness is None:
        return err_payload("thickness is required", "BAD_ARGS")
    if inner_radius is None:
        return err_payload("inner_radius is required", "BAD_ARGS")
    if angle_deg is None:
        return err_payload("angle_deg is required", "BAD_ARGS")

    result = bend_table(material, thickness, inner_radius, angle_deg, process)
    if not result["ok"]:
        return err_payload(result["reason"], "BAD_ARGS")
    del result["ok"]
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: apply_bend_table_to_flat_pattern
# ---------------------------------------------------------------------------

_apply_bend_table_spec = ToolSpec(
    name="apply_bend_table_to_flat_pattern",
    description=(
        "Recompute the developed flat length of a multi-bend sheet-metal part "
        "using per-material bend-table allowances (K-factor from DIN 6935 r/t "
        "interpolation) rather than a single scalar k_factor. "
        "Input: flat_pattern dict with base_length, plus a list of bend "
        "descriptors (material, thickness, inner_radius, angle_deg, "
        "flange_length, optional process). "
        "Output: flat_length_mm + per-bend breakdown (BA, BD, K, spring-back). "
        "Use bend_table_lookup for a single bend without flat-pattern context."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "flat_pattern": {
                "type": "object",
                "description": (
                    "Flat-pattern descriptor. Must include: "
                    "base_length (mm, > 0) — straight length of the base segment."
                ),
                "properties": {
                    "base_length": {"type": "number"},
                },
                "required": ["base_length"],
            },
            "bends": {
                "type": "array",
                "description": "Ordered list of bends from base toward the last flange.",
                "items": {
                    "type": "object",
                    "properties": {
                        "material":      {"type": "string"},
                        "thickness":     {"type": "number"},
                        "inner_radius":  {"type": "number"},
                        "angle_deg":     {"type": "number"},
                        "flange_length": {"type": "number"},
                        "process": {
                            "type": "string",
                            "enum": ["air_bend", "bottoming", "coining"],
                        },
                    },
                    "required": ["material", "thickness", "inner_radius",
                                 "angle_deg", "flange_length"],
                },
            },
        },
        "required": ["flat_pattern", "bends"],
    },
)


@register(_apply_bend_table_spec, write=False)
async def run_apply_bend_table(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    fp    = a.get("flat_pattern")
    bends = a.get("bends")

    if not isinstance(fp, dict):
        return err_payload("flat_pattern must be an object", "BAD_ARGS")
    if not isinstance(bends, list):
        return err_payload("bends must be an array", "BAD_ARGS")

    result = apply_bend_table(fp, bends)
    if not result["ok"]:
        return err_payload(result["reason"], "BAD_ARGS")
    del result["ok"]
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: bend_table_custom_load
# ---------------------------------------------------------------------------

_custom_table_load_spec = ToolSpec(
    name="bend_table_custom_load",
    description=(
        "Load shop-specific K-factor overrides into the in-process bend table. "
        "Rows must specify material, thickness (mm), inner_radius (mm), process "
        "and k_factor. Once loaded, bend_table_lookup and "
        "apply_bend_table_to_flat_pattern prefer the custom value over the "
        "built-in DIN 6935 interpolation for exact (material, thickness, "
        "inner_radius, process) matches. "
        "Use this to import measured press-brake data or tooling-specific tables."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "description": "Override rows to load.",
                "items": {
                    "type": "object",
                    "properties": {
                        "material":      {"type": "string"},
                        "thickness":     {"type": "number"},
                        "inner_radius":  {"type": "number"},
                        "process": {
                            "type": "string",
                            "enum": ["air_bend", "bottoming", "coining"],
                        },
                        "k_factor":      {"type": "number"},
                    },
                    "required": ["material", "thickness", "inner_radius",
                                 "process", "k_factor"],
                },
            },
        },
        "required": ["rows"],
    },
)


@register(_custom_table_load_spec, write=False)
async def run_bend_table_custom_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    rows = a.get("rows")
    if not isinstance(rows, list):
        return err_payload("rows must be an array", "BAD_ARGS")

    result = custom_table_load(rows)
    if not result["ok"]:
        return err_payload(result["reason"], "BAD_ARGS")
    del result["ok"]
    return ok_payload(result)
