"""
kerf_cad_core.ergonomics.tools — LLM tool wrappers for ergonomics engineering.

Registers tools with the Kerf tool registry:

  anthropometric_percentile   — body dimension at given percentile (z-score)
  design_for_range            — 5th–95th percentile clearance vs reach analysis
  niosh_rwl                   — NIOSH Revised Lifting Equation (RWL)
  lifting_index               — Lifting Index and risk classification
  snook_push_pull             — Snook max acceptable push/pull/carry forces
  grip_strength_percentile    — grip strength at given percentile
  pinch_strength_percentile   — lateral pinch strength at given percentile
  rula_score                  — RULA grand score from joint angles
  reba_score                  — REBA grand score from body-segment angles
  workstation_heights         — seated/standing workstation & display heights
  visual_angle                — visual angle and adequacy from viewing distance
  min_character_size          — minimum legible character height
  metabolic_expenditure       — metabolic energy expenditure + rest allowance
  rest_allowance              — rest allowance from metabolic demand
  reach_envelope              — functional reach envelope radius

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
NIOSH (1994) — Revised NIOSH Lifting Equation, DHHS (NIOSH) Publication 94-110.
Snook & Ciriello (1991) — Ergonomics 34(9):1197-1213.
McAtamney & Corlett (1993) — Applied Ergonomics 24(2):91-99.
Hignett & McAtamney (2000) — Applied Ergonomics 31(2):201-205.
ANSI/HFES 100-2007 — Human Factors Engineering of Computer Workstations.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.ergonomics.human import (
    anthropometric_percentile,
    design_for_range,
    niosh_rwl,
    lifting_index,
    snook_push_pull,
    grip_strength_percentile,
    pinch_strength_percentile,
    rula_score,
    reba_score,
    workstation_heights,
    visual_angle,
    min_character_size,
    metabolic_expenditure,
    rest_allowance,
    reach_envelope,
)


# ---------------------------------------------------------------------------
# Tool: anthropometric_percentile
# ---------------------------------------------------------------------------

_anthropometric_percentile_spec = ToolSpec(
    name="anthropometric_percentile",
    description=(
        "Return a body dimension at a given population percentile using "
        "z-score scaling from published mean + SD tables.\n"
        "\n"
        "Available dimensions include: stature, eye_height_standing, "
        "shoulder_height_standing, elbow_height_standing, "
        "hip_height_standing, reach_height_standing, sitting_height, "
        "eye_height_sitting, shoulder_height_sitting, elbow_height_sitting, "
        "shoulder_breadth, hip_breadth_sitting, chest_depth, "
        "functional_reach_forward, functional_reach_side, hand_length, "
        "hand_breadth, foot_length, foot_breadth, head_length, head_breadth, "
        "popliteal_height, thigh_clearance, knee_height_sitting, "
        "buttock_popliteal_length, and more.\n"
        "\n"
        "Returns dimension_mm at the requested percentile.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dimension": {
                "type": "string",
                "description": (
                    "Body dimension name (e.g. 'stature', 'shoulder_height_standing'). "
                    "See description for full list."
                ),
            },
            "percentile": {
                "type": "number",
                "description": (
                    "Percentile in (0, 1). E.g. 0.05 for 5th percentile, "
                    "0.50 for 50th, 0.95 for 95th."
                ),
            },
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "Population sex: 'male' (default) or 'female'.",
            },
        },
        "required": ["dimension", "percentile"],
    },
)


@register(_anthropometric_percentile_spec, write=False)
async def run_anthropometric_percentile(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dimension") is None:
        return json.dumps({"ok": False, "reason": "dimension is required"})
    if a.get("percentile") is None:
        return json.dumps({"ok": False, "reason": "percentile is required"})

    kwargs: dict = {}
    if "sex" in a:
        kwargs["sex"] = a["sex"]

    result = anthropometric_percentile(a["dimension"], a["percentile"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: design_for_range
# ---------------------------------------------------------------------------

_design_for_range_spec = ToolSpec(
    name="design_for_range",
    description=(
        "5th–95th percentile design-for-range analysis for clearance or reach.\n"
        "\n"
        "Clearance (doorway, aisle, guard opening): must accommodate the "
        "LARGEST user — returns 95th-percentile critical dimension.\n"
        "Reach (shelf, control, handle height): must accommodate the "
        "SMALLEST user — returns 5th-percentile critical dimension.\n"
        "\n"
        "Returns critical_mm, plus lo/hi values for both sexes.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dimension": {
                "type": "string",
                "description": "Body dimension name (see anthropometric_percentile).",
            },
            "application": {
                "type": "string",
                "enum": ["clearance", "reach"],
                "description": (
                    "'clearance' (default) — design for largest user; "
                    "'reach' — design for smallest user."
                ),
            },
            "lo_pctile": {
                "type": "number",
                "description": "Lower design percentile (default 0.05).",
            },
            "hi_pctile": {
                "type": "number",
                "description": "Upper design percentile (default 0.95).",
            },
            "include_both_sexes": {
                "type": "boolean",
                "description": (
                    "If true (default), span both male and female populations."
                ),
            },
        },
        "required": ["dimension"],
    },
)


@register(_design_for_range_spec, write=False)
async def run_design_for_range(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dimension") is None:
        return json.dumps({"ok": False, "reason": "dimension is required"})

    kwargs: dict = {}
    for k in ("application", "lo_pctile", "hi_pctile", "include_both_sexes"):
        if k in a:
            kwargs[k] = a[k]

    result = design_for_range(a["dimension"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: niosh_rwl
# ---------------------------------------------------------------------------

_niosh_rwl_spec = ToolSpec(
    name="niosh_rwl",
    description=(
        "NIOSH Revised Lifting Equation (1994): Recommended Weight Limit.\n"
        "\n"
        "RWL = LC × HM × VM × DM × AM × FM × CM\n"
        "where LC=23 kg, and the multipliers adjust for horizontal distance, "
        "vertical height, travel distance, asymmetry, frequency, and coupling.\n"
        "\n"
        "Also returns the Lifting Index LI = Load / RWL.\n"
        "LI > 1.0 indicates increased injury risk; LI > 3.0 is high risk.\n"
        "\n"
        "Returns RWL_kg, LI, and all six multipliers.\n"
        "Warnings are generated for LI > 1.0, poor multipliers, etc.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L_kg": {
                "type": "number",
                "description": "Actual load weight (kg). Must be >= 0.",
            },
            "H_cm": {
                "type": "number",
                "description": (
                    "Horizontal distance from body to hands (cm). "
                    "Optimal ≤ 25 cm; ≥ 63 cm → RWL → 0."
                ),
            },
            "V_cm": {
                "type": "number",
                "description": (
                    "Vertical height of hands at lift origin (cm). Range 0–175 cm. "
                    "Optimal = 75 cm (knuckle height)."
                ),
            },
            "D_cm": {
                "type": "number",
                "description": (
                    "Vertical travel distance (cm). Must be > 0. "
                    "Minimum 25 cm applied automatically."
                ),
            },
            "A_deg": {
                "type": "number",
                "description": (
                    "Asymmetry angle: body twist from sagittal plane (degrees, 0–135). "
                    "Default 0 (symmetric lift)."
                ),
            },
            "freq_per_min": {
                "type": "number",
                "description": "Lifting frequency (lifts/min). Default 0.2.",
            },
            "duration": {
                "type": "string",
                "enum": ["short", "moderate", "long"],
                "description": (
                    "Work duration: 'short' (≤1 h), 'moderate' (1–2 h), "
                    "'long' (2–8 h, default)."
                ),
            },
            "coupling": {
                "type": "string",
                "enum": ["good", "fair", "poor"],
                "description": (
                    "Hand-to-object coupling quality: 'good' (default), 'fair', 'poor'."
                ),
            },
        },
        "required": ["L_kg", "H_cm", "V_cm", "D_cm"],
    },
)


@register(_niosh_rwl_spec, write=False)
async def run_niosh_rwl(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("L_kg", "H_cm", "V_cm", "D_cm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("A_deg", "freq_per_min", "duration", "coupling"):
        if k in a:
            kwargs[k] = a[k]

    result = niosh_rwl(a["L_kg"], a["H_cm"], a["V_cm"], a["D_cm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lifting_index
# ---------------------------------------------------------------------------

_lifting_index_spec = ToolSpec(
    name="lifting_index",
    description=(
        "Compute the NIOSH Lifting Index (LI) and risk classification.\n"
        "\n"
        "LI = actual load / RWL.\n"
        "  LI ≤ 1.0  → acceptable\n"
        "  1.0 < LI ≤ 3.0 → elevated_risk\n"
        "  LI > 3.0  → high_risk (immediate redesign required)\n"
        "\n"
        "Same parameters as niosh_rwl.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L_kg": {"type": "number", "description": "Actual load (kg). >= 0."},
            "H_cm": {"type": "number", "description": "Horizontal distance (cm). > 0."},
            "V_cm": {"type": "number", "description": "Vertical origin height (cm). 0–175."},
            "D_cm": {"type": "number", "description": "Vertical travel distance (cm). > 0."},
            "A_deg": {"type": "number", "description": "Asymmetry angle (degrees). Default 0."},
            "freq_per_min": {"type": "number", "description": "Frequency (lifts/min). Default 0.2."},
            "duration": {
                "type": "string",
                "enum": ["short", "moderate", "long"],
                "description": "Duration: 'short', 'moderate', 'long' (default).",
            },
            "coupling": {
                "type": "string",
                "enum": ["good", "fair", "poor"],
                "description": "Coupling quality: 'good' (default), 'fair', 'poor'.",
            },
        },
        "required": ["L_kg", "H_cm", "V_cm", "D_cm"],
    },
)


@register(_lifting_index_spec, write=False)
async def run_lifting_index(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("L_kg", "H_cm", "V_cm", "D_cm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("A_deg", "freq_per_min", "duration", "coupling"):
        if k in a:
            kwargs[k] = a[k]

    result = lifting_index(a["L_kg"], a["H_cm"], a["V_cm"], a["D_cm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: snook_push_pull
# ---------------------------------------------------------------------------

_snook_push_pull_spec = ToolSpec(
    name="snook_push_pull",
    description=(
        "Snook & Ciriello (1991) maximum acceptable push, pull, or carry forces.\n"
        "\n"
        "Returns the maximum force (N) or weight (kg × 9.81 N) that "
        "50th-percentile workers can sustain for the given task, frequency, "
        "and distance. Optionally compare an applied force and flag exceedances.\n"
        "\n"
        "Returns max_acceptable_N and exceeds_limit flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "enum": ["push", "pull", "carry"],
                "description": "Task type: 'push', 'pull', or 'carry'.",
            },
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "Population sex: 'male' or 'female'.",
            },
            "freq_per_min": {
                "type": "number",
                "description": "Task frequency (per minute). Must be > 0.",
            },
            "distance_m": {
                "type": "number",
                "description": "Distance per task cycle (m). Must be > 0.",
            },
            "force_applied_N": {
                "type": "number",
                "description": (
                    "Actual force applied (N). If provided, compared against limit. "
                    "For carry: convert load (kg × 9.81 N)."
                ),
            },
        },
        "required": ["task", "sex", "freq_per_min", "distance_m"],
    },
)


@register(_snook_push_pull_spec, write=False)
async def run_snook_push_pull(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("task", "sex", "freq_per_min", "distance_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    fap = a.get("force_applied_N")
    result = snook_push_pull(
        a["task"], a["sex"], a["freq_per_min"], a["distance_m"],
        force_applied_N=fap,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: grip_strength_percentile
# ---------------------------------------------------------------------------

_grip_strength_spec = ToolSpec(
    name="grip_strength_percentile",
    description=(
        "Grip strength (dominant hand) at given population percentile.\n"
        "\n"
        "Based on Mathiowetz et al. (1985) normative data.\n"
        "Returns grip_strength_N.\n"
        "Warns if control resistance would exceed grip capability.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "percentile": {
                "type": "number",
                "description": "Percentile in (0, 1). E.g. 0.05 for 5th percentile.",
            },
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "'male' (default) or 'female'.",
            },
        },
        "required": ["percentile"],
    },
)


@register(_grip_strength_spec, write=False)
async def run_grip_strength_percentile(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("percentile") is None:
        return json.dumps({"ok": False, "reason": "percentile is required"})

    kwargs: dict = {}
    if "sex" in a:
        kwargs["sex"] = a["sex"]

    result = grip_strength_percentile(a["percentile"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pinch_strength_percentile
# ---------------------------------------------------------------------------

_pinch_strength_spec = ToolSpec(
    name="pinch_strength_percentile",
    description=(
        "Lateral (key) pinch strength at given population percentile.\n"
        "\n"
        "Based on Crosby & Wehbe (1994) normative data.\n"
        "Returns pinch_strength_N.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "percentile": {
                "type": "number",
                "description": "Percentile in (0, 1).",
            },
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "'male' (default) or 'female'.",
            },
        },
        "required": ["percentile"],
    },
)


@register(_pinch_strength_spec, write=False)
async def run_pinch_strength_percentile(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("percentile") is None:
        return json.dumps({"ok": False, "reason": "percentile is required"})

    kwargs: dict = {}
    if "sex" in a:
        kwargs["sex"] = a["sex"]

    result = pinch_strength_percentile(a["percentile"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rula_score
# ---------------------------------------------------------------------------

_rula_score_spec = ToolSpec(
    name="rula_score",
    description=(
        "RULA (Rapid Upper Limb Assessment) grand score from joint angles.\n"
        "\n"
        "Evaluates work-related upper-limb disorder risk from upper arm, "
        "lower arm, wrist, neck, and trunk posture angles.\n"
        "\n"
        "Grand score 1–2: acceptable. 3–4: investigate. "
        "5–6: prompt action. 7: immediate action required.\n"
        "\n"
        "Returns grand_score, action_level (1–4), and intermediate scores.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "upper_arm_angle_deg": {
                "type": "number",
                "description": (
                    "Upper arm flexion/extension from neutral (degrees). "
                    "Negative=extension, positive=flexion."
                ),
            },
            "lower_arm_angle_deg": {
                "type": "number",
                "description": "Elbow flexion from full extension (degrees). 0–140°.",
            },
            "wrist_angle_deg": {
                "type": "number",
                "description": "Wrist deviation from neutral (degrees). 0=neutral.",
            },
            "neck_angle_deg": {
                "type": "number",
                "description": "Neck flexion from neutral (degrees). 0=neutral.",
            },
            "trunk_angle_deg": {
                "type": "number",
                "description": "Trunk flexion from upright (degrees). 0=upright.",
            },
            "wrist_twisted": {
                "type": "boolean",
                "description": "Wrist significantly rotated from mid-range. Default false.",
            },
            "shoulder_raised": {
                "type": "boolean",
                "description": "Shoulder elevated/raised. Default false.",
            },
            "upper_arm_abducted": {
                "type": "boolean",
                "description": "Upper arm abducted. Default false.",
            },
            "static_or_repeated": {
                "type": "boolean",
                "description": (
                    "True if posture is static (>1 min) or repeated (>4×/min). "
                    "Default false."
                ),
            },
            "force_kg": {
                "type": "number",
                "description": "Force/load exerted (kg). Default 0.",
            },
        },
        "required": [
            "upper_arm_angle_deg", "lower_arm_angle_deg", "wrist_angle_deg",
            "neck_angle_deg", "trunk_angle_deg",
        ],
    },
)


@register(_rula_score_spec, write=False)
async def run_rula_score(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "upper_arm_angle_deg", "lower_arm_angle_deg", "wrist_angle_deg",
        "neck_angle_deg", "trunk_angle_deg",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("wrist_twisted", "shoulder_raised", "upper_arm_abducted",
              "static_or_repeated", "force_kg"):
        if k in a:
            kwargs[k] = a[k]

    result = rula_score(
        a["upper_arm_angle_deg"],
        a["lower_arm_angle_deg"],
        a["wrist_angle_deg"],
        a["neck_angle_deg"],
        a["trunk_angle_deg"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: reba_score
# ---------------------------------------------------------------------------

_reba_score_spec = ToolSpec(
    name="reba_score",
    description=(
        "REBA (Rapid Entire Body Assessment) grand score from body-segment angles.\n"
        "\n"
        "Evaluates musculoskeletal injury risk for whole-body postures including "
        "trunk, neck, legs, and upper/lower arm and wrist.\n"
        "\n"
        "REBA score 1: negligible. 2–3: low. 4–7: medium. "
        "8–10: high. 11–15: very high.\n"
        "\n"
        "Returns reba_score, action_level (1–5), and risk_level.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "trunk_angle_deg": {
                "type": "number",
                "description": "Trunk flexion from upright (degrees). 0=upright.",
            },
            "neck_angle_deg": {
                "type": "number",
                "description": "Neck flexion from neutral (degrees). 0=neutral.",
            },
            "leg_angle_deg": {
                "type": "number",
                "description": "Knee flexion from standing (degrees). 0=standing.",
            },
            "upper_arm_angle_deg": {
                "type": "number",
                "description": "Upper arm flexion/extension (degrees).",
            },
            "lower_arm_angle_deg": {
                "type": "number",
                "description": "Lower arm (elbow) angle (degrees).",
            },
            "wrist_angle_deg": {
                "type": "number",
                "description": "Wrist deviation (degrees).",
            },
            "load_kg": {
                "type": "number",
                "description": "Load/force (kg). Default 0.",
            },
            "coupling": {
                "type": "string",
                "enum": ["good", "fair", "poor"],
                "description": "Coupling quality: 'good' (default), 'fair', 'poor'.",
            },
            "activity_score": {
                "type": "integer",
                "description": "Activity adjustment: 0=none, 1=repetitive, 2=rapid change. Default 0.",
            },
        },
        "required": [
            "trunk_angle_deg", "neck_angle_deg", "leg_angle_deg",
            "upper_arm_angle_deg", "lower_arm_angle_deg", "wrist_angle_deg",
        ],
    },
)


@register(_reba_score_spec, write=False)
async def run_reba_score(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "trunk_angle_deg", "neck_angle_deg", "leg_angle_deg",
        "upper_arm_angle_deg", "lower_arm_angle_deg", "wrist_angle_deg",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("load_kg", "coupling", "activity_score"):
        if k in a:
            kwargs[k] = a[k]

    result = reba_score(
        a["trunk_angle_deg"],
        a["neck_angle_deg"],
        a["leg_angle_deg"],
        a["upper_arm_angle_deg"],
        a["lower_arm_angle_deg"],
        a["wrist_angle_deg"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: workstation_heights
# ---------------------------------------------------------------------------

_workstation_heights_spec = ToolSpec(
    name="workstation_heights",
    description=(
        "Recommended seated and standing workstation and display heights.\n"
        "\n"
        "Based on ANSI/HFES 100-2007 and Kroemer & Grandjean guidelines.\n"
        "If individual measurements are not provided, population percentile "
        "data for the specified sex is used automatically.\n"
        "\n"
        "Task types:\n"
        "  'light_assembly' — slightly below elbow (default)\n"
        "  'precision'      — above elbow (fine work, viewing close objects)\n"
        "  'heavy_work'     — well below elbow (force exertion)\n"
        "  'keyboard'       — slightly below elbow (typing)\n"
        "\n"
        "Returns seat_height range, work_surface_seated, "
        "work_surface_standing, and display_top_height_mm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "Population sex for defaults: 'male' (default) or 'female'.",
            },
            "percentile": {
                "type": "number",
                "description": "Population percentile for defaults (default 0.50 = 50th).",
            },
            "task_type": {
                "type": "string",
                "enum": ["light_assembly", "precision", "heavy_work", "keyboard"],
                "description": "Task type (default 'light_assembly').",
            },
            "stature_mm": {
                "type": "number",
                "description": "Individual stature (mm), optional.",
            },
            "popliteal_height_mm": {
                "type": "number",
                "description": "Popliteal height (mm), optional.",
            },
            "elbow_height_standing_mm": {
                "type": "number",
                "description": "Elbow height standing (mm), optional.",
            },
            "elbow_height_sitting_mm": {
                "type": "number",
                "description": "Elbow height seated above seat (mm), optional.",
            },
            "eye_height_sitting_mm": {
                "type": "number",
                "description": "Eye height seated above seat (mm), optional.",
            },
        },
        "required": [],
    },
)


@register(_workstation_heights_spec, write=False)
async def run_workstation_heights(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    for k in (
        "stature_mm", "popliteal_height_mm", "elbow_height_standing_mm",
        "elbow_height_sitting_mm", "eye_height_sitting_mm",
        "sex", "percentile", "task_type",
    ):
        if k in a:
            kwargs[k] = a[k]

    result = workstation_heights(**kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: visual_angle
# ---------------------------------------------------------------------------

_visual_angle_spec = ToolSpec(
    name="visual_angle",
    description=(
        "Visual angle subtended by an object at a given viewing distance.\n"
        "\n"
        "Minimum legibility: 20 arcmin per MIL-STD-1472G.\n"
        "Preferred for comfortable reading: 20–30+ arcmin.\n"
        "\n"
        "Returns visual_angle_arcmin and adequate_for_reading flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object_height_mm": {
                "type": "number",
                "description": "Height of the object/character (mm). Must be > 0.",
            },
            "viewing_distance_mm": {
                "type": "number",
                "description": "Viewing distance from eye to object (mm). Must be > 0.",
            },
        },
        "required": ["object_height_mm", "viewing_distance_mm"],
    },
)


@register(_visual_angle_spec, write=False)
async def run_visual_angle(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("object_height_mm", "viewing_distance_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = visual_angle(a["object_height_mm"], a["viewing_distance_mm"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: min_character_size
# ---------------------------------------------------------------------------

_min_char_size_spec = ToolSpec(
    name="min_character_size",
    description=(
        "Minimum legible character height from viewing distance.\n"
        "\n"
        "Uses: h = 2 × d × tan(alpha/2) where alpha is visual angle.\n"
        "Default minimum: 20 arcmin (MIL-STD-1472G).\n"
        "Default preferred: 30 arcmin.\n"
        "\n"
        "Returns min_char_height_mm and preferred_char_height_mm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "viewing_distance_mm": {
                "type": "number",
                "description": "Viewing distance (mm). Must be > 0.",
            },
            "min_arcmin": {
                "type": "number",
                "description": "Minimum visual angle (arcmin). Default 20.",
            },
            "preferred_arcmin": {
                "type": "number",
                "description": "Preferred visual angle (arcmin). Default 30.",
            },
        },
        "required": ["viewing_distance_mm"],
    },
)


@register(_min_char_size_spec, write=False)
async def run_min_character_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("viewing_distance_mm") is None:
        return json.dumps({"ok": False, "reason": "viewing_distance_mm is required"})

    kwargs: dict = {}
    for k in ("min_arcmin", "preferred_arcmin"):
        if k in a:
            kwargs[k] = a[k]

    result = min_character_size(a["viewing_distance_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: metabolic_expenditure
# ---------------------------------------------------------------------------

_metabolic_expenditure_spec = ToolSpec(
    name="metabolic_expenditure",
    description=(
        "Metabolic energy expenditure and rest allowance for manual work.\n"
        "\n"
        "Activity levels:\n"
        "  'rest'             —  80 W (sitting quietly)\n"
        "  'very_light'       — 175 W (office/lab seated)\n"
        "  'light'            — 280 W (light assembly, standing)\n"
        "  'moderate'         — 450 W (general assembly, slow walking)\n"
        "  'heavy'            — 600 W (heavy assembly, fast walking)\n"
        "  'very_heavy'       — 800 W (intense manual labour)\n"
        "  'extremely_heavy'  —1000 W (peak sustained effort)\n"
        "\n"
        "Sustained 8-hour ceiling: 350 W. Exceeding this requires rest breaks.\n"
        "Rest allowance computed via Murrell (1965) formula.\n"
        "\n"
        "Returns metabolic_rate_W, total_energy_kJ, rest_allowance_min.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "activity": {
                "type": "string",
                "enum": [
                    "rest", "very_light", "light", "moderate",
                    "heavy", "very_heavy", "extremely_heavy",
                ],
                "description": "Activity level (default 'moderate').",
            },
            "body_mass_kg": {
                "type": "number",
                "description": "Worker body mass (kg). Default 75 kg.",
            },
            "duration_min": {
                "type": "number",
                "description": "Task duration (minutes). Must be > 0. Default 60.",
            },
        },
        "required": [],
    },
)


@register(_metabolic_expenditure_spec, write=False)
async def run_metabolic_expenditure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    for k in ("activity", "body_mass_kg", "duration_min"):
        if k in a:
            kwargs[k] = a[k]

    result = metabolic_expenditure(**kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rest_allowance
# ---------------------------------------------------------------------------

_rest_allowance_spec = ToolSpec(
    name="rest_allowance",
    description=(
        "Rest allowance from metabolic demand using Murrell (1965) formula.\n"
        "\n"
        "R = T × (M - S) / (M - 1.5)  (W/kg units)\n"
        "where S = 1.5 W/kg (rest standard), M = task metabolic rate per kg,\n"
        "T = task duration.\n"
        "\n"
        "Returns rest_min per task_duration_min and rest_fraction.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "metabolic_rate_W": {
                "type": "number",
                "description": "Task metabolic rate (W). Must be > 0.",
            },
            "body_mass_kg": {
                "type": "number",
                "description": "Worker body mass (kg). Default 75 kg.",
            },
            "task_duration_min": {
                "type": "number",
                "description": "Task duration (minutes). Must be > 0. Default 60.",
            },
        },
        "required": ["metabolic_rate_W"],
    },
)


@register(_rest_allowance_spec, write=False)
async def run_rest_allowance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("metabolic_rate_W") is None:
        return json.dumps({"ok": False, "reason": "metabolic_rate_W is required"})

    kwargs: dict = {}
    for k in ("body_mass_kg", "task_duration_min"):
        if k in a:
            kwargs[k] = a[k]

    result = rest_allowance(a["metabolic_rate_W"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: reach_envelope
# ---------------------------------------------------------------------------

_reach_envelope_spec = ToolSpec(
    name="reach_envelope",
    description=(
        "Functional reach envelope radius for workstation layout.\n"
        "\n"
        "Returns the arm reach distance (mm) achievable by the given "
        "percentile of the population in standing or seated posture.\n"
        "\n"
        "For reach design, use the 5th percentile (smallest user) — all "
        "primary controls must be within this radius.\n"
        "\n"
        "Reach types:\n"
        "  'functional' — arm extended with shoulder rotation\n"
        "  'maximum'    — fully extended arm + body lean (~20% more)\n"
        "\n"
        "Returns reach_radius_mm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sex": {
                "type": "string",
                "enum": ["male", "female"],
                "description": "'male' (default) or 'female'.",
            },
            "percentile": {
                "type": "number",
                "description": (
                    "Design percentile (default 0.05 = 5th percentile). "
                    "Use 5th for reach design (smallest user)."
                ),
            },
            "posture": {
                "type": "string",
                "enum": ["standing", "seated"],
                "description": "'standing' (default) or 'seated'.",
            },
            "reach_type": {
                "type": "string",
                "enum": ["functional", "maximum"],
                "description": "'functional' (default) or 'maximum'.",
            },
        },
        "required": [],
    },
)


@register(_reach_envelope_spec, write=False)
async def run_reach_envelope(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    for k in ("sex", "percentile", "posture", "reach_type"):
        if k in a:
            kwargs[k] = a[k]

    result = reach_envelope(**kwargs)
    return ok_payload(result)
