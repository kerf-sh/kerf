"""
kerf_cad_core.gearbox.train — Gear-train / gearbox assembly math.

Composes one or more gear stages into a complete gear train and computes:

  - Total gear ratio  (product of stage ratios)
  - Per-shaft speed and torque (ISO / classical power-train relations)
  - Per-stage interference / undercut check  (delegates to kerf_cad_core.gears)
  - Per-stage centre distance  (ISO 21771 §10.1 standard value: m·(z1+z2)/2)
  - Shaft layout  (cumulative centre distances)
  - Efficiency estimate  (spur-mesh empirical: η_stage ≈ 0.98–0.99)

Terminology
-----------
stage   — one meshing pair: pinion (driver, z1 teeth) + gear (driven, z2 teeth)
idler   — a stage with the same shaft id on both sides  (z1 == z2 == any,
          is_idler=True); idler transmits ratio 1:1 but reverses rotation.
          Idlers are supported via an explicit flag on each stage dict.
ratio   — z2 / z1  (the "step-down" ratio for that stage; >1 = reduction)
train   — ordered list of stages sharing consecutive shafts

References
----------
Shigley's Mechanical Engineering Design (10th ed.) §13-4 to §13-7
ISO 21771:2007 §3.12  (gear ratio definition)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# ── Reuse gears.py math ───────────────────────────────────────────────────────
# We deliberately import the private helpers that back gear_pair_check so we
# never duplicate the interference / undercut logic.
from kerf_cad_core.gears import (
    _HA_COEFF,
    _HF_COEFF,
    _ALPHA_MIN,
    _ALPHA_MAX,
    _Z_UNDERCUT,
    _inv,
    _contact_ratio,
)


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

# Empirical per-mesh efficiency for a well-lubricated spur/helical pair
# (Shigley §13-7; 0.98–0.99 is standard for good practice)
_ETA_STAGE = 0.98

# Minimum / maximum teeth per stage side
_Z_MIN = 3


# ---------------------------------------------------------------------------
# Stage validation
# ---------------------------------------------------------------------------

def _validate_stage(i: int, s: dict[str, Any]) -> list[str]:
    """Return a list of error strings for stage *i* (0-indexed)."""
    errs: list[str] = []
    label = f"stage[{i}]"

    # Required numeric fields
    for key in ("z1", "z2", "module"):
        if key not in s:
            errs.append(f"{label}: missing required field '{key}'")

    if errs:
        return errs  # can't continue checking without the basics

    try:
        z1 = int(s["z1"])
    except (TypeError, ValueError):
        errs.append(f"{label}: z1 must be an integer; got {s['z1']!r}")
        z1 = 0

    try:
        z2 = int(s["z2"])
    except (TypeError, ValueError):
        errs.append(f"{label}: z2 must be an integer; got {s['z2']!r}")
        z2 = 0

    try:
        m = float(s["module"])
    except (TypeError, ValueError):
        errs.append(f"{label}: module must be a number; got {s['module']!r}")
        m = 0.0

    if z1 < _Z_MIN:
        errs.append(f"{label}: z1={z1} < {_Z_MIN} (minimum tooth count)")
    if z2 < _Z_MIN:
        errs.append(f"{label}: z2={z2} < {_Z_MIN} (minimum tooth count)")
    if m <= 0:
        errs.append(f"{label}: module={m} must be > 0")

    alpha_deg = float(s.get("pressure_angle_deg", 20.0))
    if not (_ALPHA_MIN < alpha_deg < _ALPHA_MAX):
        errs.append(
            f"{label}: pressure_angle_deg={alpha_deg} must be in "
            f"({_ALPHA_MIN}°, {_ALPHA_MAX}°)"
        )

    return errs


# ---------------------------------------------------------------------------
# Core per-stage computation
# ---------------------------------------------------------------------------

def _stage_ratio(z1: int, z2: int) -> float:
    """
    Gear ratio for a single meshing pair.

    ratio = z2 / z1  (ISO 21771 §3.12)

    For a reduction stage z2 > z1, ratio > 1.
    For an idler stage ratio = 1 (caller must set is_idler=True).
    """
    return z2 / z1


def _stage_centre_distance(m: float, z1: int, z2: int) -> float:
    """
    Standard (no profile-shift) centre distance for one stage (mm).

    a = m · (z1 + z2) / 2  (ISO 21771 §10.1)
    """
    return m * (z1 + z2) / 2.0


def _stage_interference(
    m: float,
    z1: int,
    z2: int,
    alpha_deg: float,
    x1: float,
    x2: float,
) -> list[str]:
    """
    Return a list of warning strings for undercut / tip interference using the
    same logic as gears.gear_pair_check (imported, not duplicated).

    Checks:
      1. Root-inside-base-circle undercut  (r_f < r_b)
      2. Minimum tooth count (z < _Z_UNDERCUT at zero profile shift)
      3. Tip interference (tip of one gear beyond interference point of other)
    """
    warnings: list[str] = []
    alpha = math.radians(alpha_deg)

    # Basic diameters (ISO 21771 §4)
    d1 = m * z1
    d2 = m * z2
    d_b1 = d1 * math.cos(alpha)
    d_b2 = d2 * math.cos(alpha)
    d_a1 = d1 + 2.0 * m * (_HA_COEFF + x1)
    d_a2 = d2 + 2.0 * m * (_HA_COEFF + x2)
    d_f1 = d1 - 2.0 * m * (_HF_COEFF - x1)
    d_f2 = d2 - 2.0 * m * (_HF_COEFF - x2)

    r_b1, r_b2 = d_b1 / 2.0, d_b2 / 2.0
    r_a1, r_a2 = d_a1 / 2.0, d_a2 / 2.0
    r_f1, r_f2 = d_f1 / 2.0, d_f2 / 2.0

    # Operating pressure angle (standard: no profile shift → α_w = α)
    inv_alpha = _inv(alpha)
    inv_alpha_w = inv_alpha + 2.0 * (x1 + x2) * math.tan(alpha) / (z1 + z2)
    alpha_w = alpha
    for _ in range(40):
        f  = _inv(alpha_w) - inv_alpha_w
        df = math.tan(alpha_w) ** 2
        if abs(df) < 1e-14:
            break
        delta = f / df
        alpha_w -= delta
        if abs(delta) < 1e-14:
            break
    alpha_w = max(0.001, alpha_w)

    a_w = (r_b1 + r_b2) / math.cos(alpha_w)
    p_bt = math.pi * m * math.cos(alpha)

    # Contact ratio
    eps = _contact_ratio(r_a1, r_b1, r_a2, r_b2, a_w, alpha_w, p_bt)

    # Undercut: root circle inside base circle
    if r_f1 < r_b1:
        warnings.append(
            f"Pinion undercut risk: root circle r_f={r_f1:.3f} mm inside "
            f"base circle r_b={r_b1:.3f} mm. Consider profile shift x1 >= "
            f"{round((17 - z1) / 17, 3)}."
        )
    if r_f2 < r_b2:
        warnings.append(
            f"Gear undercut risk: root circle r_f={r_f2:.3f} mm inside "
            f"base circle r_b={r_b2:.3f} mm. Consider profile shift x2 >= "
            f"{round((17 - z2) / 17, 3)}."
        )

    # Min-tooth undercut heuristic
    if z1 < _Z_UNDERCUT and abs(x1) < 0.01:
        warnings.append(
            f"Pinion z1={z1} < {_Z_UNDERCUT} with no profile shift — "
            "undercut likely; apply positive x1."
        )
    if z2 < _Z_UNDERCUT and abs(x2) < 0.01:
        warnings.append(
            f"Gear z2={z2} < {_Z_UNDERCUT} with no profile shift — "
            "undercut likely; apply positive x2."
        )

    # Tip interference
    tangent_len_1 = math.sqrt(max(0.0, r_a1**2 - r_b1**2))
    tangent_len_2 = math.sqrt(max(0.0, r_a2**2 - r_b2**2))
    line_of_action = a_w * math.sin(alpha_w)
    if tangent_len_1 > line_of_action + 1e-6:
        warnings.append(
            "Tip interference: pinion tip extends beyond interference point of gear. "
            "Reduce addendum of pinion or increase profile shift."
        )
    if tangent_len_2 > line_of_action + 1e-6:
        warnings.append(
            "Tip interference: gear tip extends beyond interference point of pinion. "
            "Reduce addendum of gear or increase profile shift."
        )

    if eps < 1.0:
        warnings.append(
            f"Contact ratio ε_α={eps:.3f} < 1.0 — discontinuous motion. "
            "Increase addendum or reduce centre distance."
        )
    elif eps < 1.2:
        warnings.append(
            f"Contact ratio ε_α={eps:.3f} < 1.2 — acceptable but low."
        )

    return warnings


# ---------------------------------------------------------------------------
# Gear-train assembly
# ---------------------------------------------------------------------------

def design_gearbox(
    stages: list[dict[str, Any]],
    input_rpm: float,
    input_torque: float,
) -> dict[str, Any]:
    """
    Compose a multi-stage gear train.

    Parameters
    ----------
    stages : list of stage dicts, each containing:
        z1              int   pinion teeth (driver)
        z2              int   gear teeth (driven)
        module          float module m (mm)
        pressure_angle_deg float  default 20.0
        profile_shift_1 float  x1, default 0.0
        profile_shift_2 float  x2, default 0.0
        eta             float  mesh efficiency, default 0.98
        is_idler        bool   if True: ratio=1, direction reversal flagged
        shaft_in        str    shaft label for the input side (optional)
        shaft_out       str    shaft label for the output side (optional)

    input_rpm    : rotational speed at the first shaft (rpm)
    input_torque : torque at the first shaft (N·m)

    Returns
    -------
    dict with keys:
        ok                  bool
        total_ratio         float   product of all stage ratios (z2/z1 per stage)
        total_efficiency    float   product of all stage efficiencies
        output_rpm          float   speed at last shaft
        output_torque       float   torque at last shaft  (= T_in · total_ratio · η_total)
        stages              list    per-stage detail dicts
        shafts              list    shaft table: shaft id, speed, torque, cumulative_centre_distance
        warnings            list    all interference/undercut warnings (stage-prefixed)
        errors              list    validation errors (populated only when ok=False)

    Torque relation (Shigley §13-4):
        T_out = T_in · ratio · η

    Speed relation (kinematic):
        n_out = n_in / ratio   (ratio = z2/z1 > 1 for reduction)

    Author: imranparuk
    """
    # ── Validate top-level inputs ──────────────────────────────────────────
    errors: list[str] = []
    if not isinstance(stages, list) or len(stages) == 0:
        errors.append("stages must be a non-empty list")
    if not isinstance(input_rpm, (int, float)) or input_rpm <= 0:
        errors.append(f"input_rpm must be > 0; got {input_rpm!r}")
    if not isinstance(input_torque, (int, float)) or input_torque <= 0:
        errors.append(f"input_torque must be > 0; got {input_torque!r}")

    if errors:
        return {"ok": False, "errors": errors}

    # ── Validate each stage ────────────────────────────────────────────────
    stage_errs: list[str] = []
    for i, s in enumerate(stages):
        if not isinstance(s, dict):
            stage_errs.append(f"stage[{i}] must be a dict; got {type(s).__name__}")
            continue
        stage_errs.extend(_validate_stage(i, s))

    if stage_errs:
        return {"ok": False, "errors": stage_errs}

    # ── Compute train ──────────────────────────────────────────────────────
    all_warnings: list[str] = []
    stage_results: list[dict[str, Any]] = []

    current_rpm    = float(input_rpm)
    current_torque = float(input_torque)
    cumulative_cd  = 0.0  # cumulative centre distance (mm)
    total_ratio    = 1.0
    total_eta      = 1.0

    for i, s in enumerate(stages):
        z1        = int(s["z1"])
        z2        = int(s["z2"])
        m         = float(s["module"])
        alpha_deg = float(s.get("pressure_angle_deg", 20.0))
        x1        = float(s.get("profile_shift_1", 0.0))
        x2        = float(s.get("profile_shift_2", 0.0))
        eta       = float(s.get("eta", _ETA_STAGE))
        is_idler  = bool(s.get("is_idler", False))
        shaft_in  = str(s.get("shaft_in",  f"shaft_{i}"))
        shaft_out = str(s.get("shaft_out", f"shaft_{i + 1}"))

        # Idler: kinematic ratio = 1, but flips rotation direction
        if is_idler:
            ratio     = 1.0
            cd        = _stage_centre_distance(m, z1, z2)
        else:
            ratio     = _stage_ratio(z1, z2)
            cd        = _stage_centre_distance(m, z1, z2)

        # Per-stage power-train
        out_rpm    = current_rpm / ratio        # n_out = n_in / (z2/z1)
        out_torque = current_torque * ratio * eta  # T_out = T_in * ratio * η

        cumulative_cd += cd
        total_ratio   *= ratio
        total_eta     *= eta

        # Interference / undercut check (reuses gears.py math)
        iw = _stage_interference(m, z1, z2, alpha_deg, x1, x2)
        for w in iw:
            all_warnings.append(f"stage[{i}]: {w}")

        stage_results.append({
            "index":              i,
            "shaft_in":           shaft_in,
            "shaft_out":          shaft_out,
            "z1":                 z1,
            "z2":                 z2,
            "module":             m,
            "pressure_angle_deg": alpha_deg,
            "profile_shift_1":    x1,
            "profile_shift_2":    x2,
            "is_idler":           is_idler,
            "ratio":              round(ratio, 8),
            "eta":                round(eta, 6),
            "centre_distance_mm": round(cd, 6),
            "cumulative_centre_distance_mm": round(cumulative_cd, 6),
            "input_rpm":          round(current_rpm, 6),
            "output_rpm":         round(out_rpm, 6),
            "input_torque_nm":    round(current_torque, 6),
            "output_torque_nm":   round(out_torque, 6),
            "interference_warnings": iw,
        })

        current_rpm    = out_rpm
        current_torque = out_torque

    # ── Shaft table ────────────────────────────────────────────────────────
    # Collect unique shafts in order of first appearance.
    # Each shaft carries the speed/torque at the point it is driven.
    shaft_map: dict[str, dict[str, Any]] = {}
    cumcd_per_shaft: dict[str, float] = {}

    # Input shaft from the first stage
    first = stage_results[0]
    shaft_map[first["shaft_in"]] = {
        "shaft_id":   first["shaft_in"],
        "rpm":        round(float(input_rpm), 6),
        "torque_nm":  round(float(input_torque), 6),
        "cumulative_centre_distance_mm": 0.0,
    }

    for sr in stage_results:
        sid = sr["shaft_out"]
        if sid not in shaft_map:
            shaft_map[sid] = {
                "shaft_id":  sid,
                "rpm":       sr["output_rpm"],
                "torque_nm": sr["output_torque_nm"],
                "cumulative_centre_distance_mm": sr["cumulative_centre_distance_mm"],
            }

    shafts = list(shaft_map.values())

    return {
        "ok":               True,
        "total_ratio":      round(total_ratio, 8),
        "total_efficiency": round(total_eta, 8),
        "output_rpm":       round(current_rpm, 6),
        "output_torque_nm": round(current_torque, 6),
        "stages":           stage_results,
        "shafts":           shafts,
        "warnings":         all_warnings,
        "errors":           [],
    }


def gearbox_ratio(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute only the total gear ratio for a list of stages.

    Returns {ok, total_ratio, stage_ratios} or {ok:False, errors:[...]}.

    total_ratio = ∏ (z2_i / z1_i)   (Shigley §13-4)
    Idler stages (is_idler=True) contribute ratio = 1.
    """
    if not isinstance(stages, list) or len(stages) == 0:
        return {"ok": False, "errors": ["stages must be a non-empty list"]}

    errs: list[str] = []
    for i, s in enumerate(stages):
        if not isinstance(s, dict):
            errs.append(f"stage[{i}] must be a dict")
            continue
        errs.extend(_validate_stage(i, s))

    if errs:
        return {"ok": False, "errors": errs}

    stage_ratios = []
    total = 1.0
    for s in stages:
        if bool(s.get("is_idler", False)):
            r = 1.0
        else:
            r = int(s["z2"]) / int(s["z1"])
        stage_ratios.append(round(r, 8))
        total *= r

    return {
        "ok":           True,
        "total_ratio":  round(total, 8),
        "stage_ratios": stage_ratios,
    }


def gearbox_shaft_table(
    stages: list[dict[str, Any]],
    input_rpm: float,
    input_torque: float,
) -> dict[str, Any]:
    """
    Return only the shaft table from design_gearbox.

    Convenience wrapper; delegates entirely to design_gearbox.
    Returns {ok, shafts:[{shaft_id, rpm, torque_nm, cumulative_centre_distance_mm}]}
    """
    result = design_gearbox(stages, input_rpm, input_torque)
    if not result["ok"]:
        return result
    return {
        "ok":     True,
        "shafts": result["shafts"],
    }
