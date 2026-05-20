"""
kerf_mates.synthesis.gear_train — gear-train synthesis.

Given a target gear ratio and an optional speed range, return a 1- or
2-stage spur-gear configuration with standard module, integer tooth counts,
and centre distance.

Public API
----------
synthesise_gear_train(target_ratio, *, speed_range_rpm=(0, 10000),
                      tol_ratio=0.02, prefer_stages=None,
                      pressure_angle_deg=20.0) -> dict

    target_ratio      : desired output/input ratio (> 1 for reduction,
                        < 1 for overdrive, i.e. z2/z1 per stage product)
    speed_range_rpm   : (min_rpm, max_rpm) tuple for the input shaft
                        (used to select appropriate module; default (0, 10000))
    tol_ratio         : acceptable fractional error in total ratio
                        (default 0.02 = 2%)
    prefer_stages     : 1 or 2 — force 1-stage or 2-stage split.
                        None = automatic (1 stage if ratio <= 6, else 2).
    pressure_angle_deg: standard pressure angle (default 20°)

    Returns dict:
        ok              bool
        stages          int     (1 or 2)
        total_ratio     float   actual achieved ratio
        ratio_error     float   |actual - target| / target
        stage_configs   list    per-stage dicts:
            module              float   ISO standard module (mm)
            z1                  int     pinion teeth
            z2                  int     gear teeth
            ratio               float   z2/z1
            centre_distance_mm  float   m(z1+z2)/2
            pitch_diameter_1_mm float   m*z1
            pitch_diameter_2_mm float   m*z2
        warnings        list[str]
        reason          str     (only when ok=False)

ISO standard modules
--------------------
ISO 54 preferred series (first choice): 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20
Second choice: 1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 7, 9, 11, 14, 18

Tooth-count limits
------------------
Minimum: 17 (no undercut at α=20° without profile shift)
Maximum: 150 (practical limit for spur gears)

For a 2-stage train the target ratio is split roughly equally between
stages to minimise centre distance: r1 ≈ r2 ≈ √target_ratio.

References
----------
ISO 54:1996 — Cylindrical gears — ISO system of accuracy (module values)
Shigley's Mechanical Engineering Design, 10th ed., Ch. 13.
Norton, R.L. (2012). Design of Machinery, 5th ed., Ch. 11.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ISO 54 preferred module series (first choice)
_ISO_MODULES_FIRST = [
    0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0,
    6.0, 8.0, 10.0, 12.0, 16.0, 20.0,
]

# ISO 54 second choice modules
_ISO_MODULES_SECOND = [
    0.7, 0.9, 1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5,
    7.0, 9.0, 11.0, 14.0, 18.0,
]

_ISO_MODULES_ALL = sorted(set(_ISO_MODULES_FIRST + _ISO_MODULES_SECOND))

_Z_MIN = 17     # minimum teeth (no undercut at α=20°)
_Z_MAX = 150    # practical maximum teeth

_ALPHA_DEFAULT = 20.0   # degrees


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _centre_distance(m: float, z1: int, z2: int) -> float:
    """Standard centre distance (mm): a = m·(z1+z2)/2."""
    return m * (z1 + z2) / 2.0


def _find_tooth_pair(
    target_ratio: float,
    tol: float,
    module: float,
) -> tuple[int, int, float] | None:
    """
    Search for (z1, z2) integer tooth pair closest to target_ratio = z2/z1,
    within [_Z_MIN, _Z_MAX].

    Returns (z1, z2, actual_ratio) or None if no pair found within tolerance.
    """
    best: tuple[int, int, float] | None = None
    best_err = float("inf")

    for z1 in range(_Z_MIN, _Z_MAX + 1):
        # z2 = round(z1 * target_ratio)
        z2_float = z1 * target_ratio
        for z2 in (math.floor(z2_float), math.ceil(z2_float)):
            z2 = int(z2)
            if z2 < _Z_MIN or z2 > _Z_MAX:
                continue
            actual = z2 / z1
            err = abs(actual - target_ratio) / target_ratio
            if err < best_err:
                best_err = err
                best = (z1, z2, actual)
            if err <= tol:
                # Good enough — but keep looking for a more exact match
                # among smaller tooth counts (smaller = smaller gears)
                if z1 >= _Z_MIN + 5:
                    break

    if best is not None and best_err <= tol:
        return best
    return None


def _select_module(max_speed_rpm: float, z_min: int) -> float:
    """
    Heuristic module selection based on speed range.
    Higher speed → smaller module (finer teeth, less dynamic impact).
    Lower speed / high torque → larger module.
    """
    if max_speed_rpm > 5000:
        # Fine pitch for high speed
        candidates = [m for m in _ISO_MODULES_FIRST if m <= 3.0]
    elif max_speed_rpm > 1000:
        candidates = [m for m in _ISO_MODULES_FIRST if 1.0 <= m <= 6.0]
    else:
        candidates = [m for m in _ISO_MODULES_FIRST if m >= 2.0]

    return candidates[0] if candidates else 2.0


def _build_stage(
    z1: int,
    z2: int,
    module: float,
    pressure_angle_deg: float = _ALPHA_DEFAULT,
) -> dict[str, Any]:
    """Build a stage configuration dict."""
    ratio = z2 / z1
    cd = _centre_distance(module, z1, z2)
    return {
        "module":              module,
        "z1":                  z1,
        "z2":                  z2,
        "ratio":               round(ratio, 8),
        "centre_distance_mm":  round(cd, 6),
        "pitch_diameter_1_mm": round(module * z1, 6),
        "pitch_diameter_2_mm": round(module * z2, 6),
        "pressure_angle_deg":  pressure_angle_deg,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesise_gear_train(
    target_ratio: float,
    *,
    speed_range_rpm: tuple[float, float] = (0.0, 10000.0),
    tol_ratio: float = 0.02,
    prefer_stages: int | None = None,
    pressure_angle_deg: float = _ALPHA_DEFAULT,
) -> dict[str, Any]:
    """
    Synthesise a 1- or 2-stage spur-gear train for a target ratio.

    Parameters
    ----------
    target_ratio      : desired overall ratio (z2/z1 per stage, product).
                        > 1 = reduction; < 1 = overdrive; = 1 = 1:1.
    speed_range_rpm   : (min_rpm, max_rpm) for the input shaft, used to
                        select appropriate module (default (0, 10000)).
    tol_ratio         : fractional tolerance on the achieved ratio
                        (default 0.02 — within 2% of target).
    prefer_stages     : 1 or 2, or None for automatic selection.
    pressure_angle_deg: standard pressure angle in degrees (default 20.0).

    Returns
    -------
    dict
        ok              bool
        stages          int    number of stages
        total_ratio     float  achieved overall ratio (product of z2/z1)
        ratio_error     float  |achieved − target| / target
        stage_configs   list   per-stage dicts
        warnings        list[str]
        reason          str    (only when ok=False)
    """
    warnings_list: list[str] = []

    # -- Validate -------------------------------------------------------------
    try:
        target_ratio = float(target_ratio)
    except (TypeError, ValueError):
        return _err(f"target_ratio must be a number, got {target_ratio!r}")
    if not math.isfinite(target_ratio) or target_ratio <= 0:
        return _err(f"target_ratio must be > 0 and finite, got {target_ratio}")

    try:
        min_rpm, max_rpm = float(speed_range_rpm[0]), float(speed_range_rpm[1])
    except (TypeError, ValueError, IndexError):
        return _err(f"speed_range_rpm must be a (min, max) tuple of numbers")
    if min_rpm < 0 or max_rpm < 0:
        return _err("speed_range_rpm values must be >= 0")
    max_rpm_eff = max(max_rpm, 1.0)

    try:
        tol_ratio = float(tol_ratio)
    except (TypeError, ValueError):
        return _err(f"tol_ratio must be a number, got {tol_ratio!r}")
    if not math.isfinite(tol_ratio) or tol_ratio <= 0:
        return _err(f"tol_ratio must be > 0, got {tol_ratio}")

    if prefer_stages is not None and prefer_stages not in (1, 2):
        return _err(f"prefer_stages must be 1, 2, or None; got {prefer_stages!r}")

    try:
        pressure_angle_deg = float(pressure_angle_deg)
    except (TypeError, ValueError):
        return _err(f"pressure_angle_deg must be a number")
    if not (10.0 < pressure_angle_deg < 30.0):
        return _err(
            f"pressure_angle_deg must be in (10°, 30°); got {pressure_angle_deg}"
        )

    # -- Choose number of stages ----------------------------------------------
    if prefer_stages is not None:
        n_stages_target = prefer_stages
    else:
        # Single stage feasible up to ~1:6 ratio (z_min=17, z_max=150 → max ratio ~8.8)
        # but > 1:6 gets into large gear diameters; use 2 stages for ratio > 6
        if target_ratio > 6.0 or target_ratio < 1.0 / 6.0:
            n_stages_target = 2
        else:
            n_stages_target = 1

    module = _select_module(max_rpm_eff, _Z_MIN)

    # -- Try all standard modules in priority order ---------------------------
    def _try_single_stage(
        ratio: float, tol: float
    ) -> tuple[int, int, float, float] | None:
        """Returns (z1, z2, actual_ratio, module) or None."""
        for m in _ISO_MODULES_FIRST + _ISO_MODULES_SECOND:
            pair = _find_tooth_pair(ratio, tol, m)
            if pair:
                z1, z2, actual = pair
                return z1, z2, actual, m
        return None

    # -- 1-stage synthesis ----------------------------------------------------
    def synthesise_1stage() -> dict[str, Any] | None:
        res = _try_single_stage(target_ratio, tol_ratio)
        if res is None:
            return None
        z1, z2, actual_ratio, m = res
        err = abs(actual_ratio - target_ratio) / target_ratio
        stage = _build_stage(z1, z2, m, pressure_angle_deg)
        return {
            "ok":             True,
            "stages":         1,
            "total_ratio":    round(actual_ratio, 8),
            "ratio_error":    round(err, 8),
            "stage_configs":  [stage],
            "warnings":       [],
        }

    # -- 2-stage synthesis ----------------------------------------------------
    def synthesise_2stage() -> dict[str, Any] | None:
        # Split into two equal stages: r1 = r2 = sqrt(target_ratio)
        r_stage = math.sqrt(target_ratio)

        # Try a range of splits around sqrt
        best: dict[str, Any] | None = None
        best_err = float("inf")

        # Enumerate split ratios
        splits: list[float] = [r_stage]
        for delta in [0.9, 1.1, 0.8, 1.2, 0.7, 1.3]:
            r1_cand = r_stage * delta
            r2_cand = target_ratio / r1_cand
            if r2_cand > 0:
                splits.append(r1_cand)

        for r1_target in splits:
            r2_target = target_ratio / r1_target
            if r1_target <= 0 or r2_target <= 0:
                continue

            res1 = _try_single_stage(r1_target, tol_ratio * 2)
            if res1 is None:
                continue
            z1_a, z2_a, actual_r1, m1 = res1

            # Adjusted target for stage 2 given actual stage 1
            r2_adj = target_ratio / actual_r1

            res2 = _try_single_stage(r2_adj, tol_ratio * 2)
            if res2 is None:
                continue
            z1_b, z2_b, actual_r2, m2 = res2

            overall = actual_r1 * actual_r2
            err = abs(overall - target_ratio) / target_ratio
            if err < best_err and err <= tol_ratio:
                best_err = err
                best = {
                    "ok":          True,
                    "stages":      2,
                    "total_ratio": round(overall, 8),
                    "ratio_error": round(err, 8),
                    "stage_configs": [
                        _build_stage(z1_a, z2_a, m1, pressure_angle_deg),
                        _build_stage(z1_b, z2_b, m2, pressure_angle_deg),
                    ],
                    "warnings": [],
                }

        return best

    # -- Main synthesis logic --------------------------------------------------
    result: dict[str, Any] | None = None

    if n_stages_target == 1:
        result = synthesise_1stage()
        if result is None:
            warnings_list.append(
                f"Single-stage synthesis failed for ratio {target_ratio:.4g}; "
                "falling back to 2-stage."
            )
            result = synthesise_2stage()
    else:
        result = synthesise_2stage()
        if result is None:
            warnings_list.append(
                f"2-stage synthesis failed for ratio {target_ratio:.4g}; "
                "trying single-stage."
            )
            result = synthesise_1stage()

    if result is None:
        # Last resort: widen tolerance to 5%
        warnings_list.append(
            f"No exact solution within tol={tol_ratio:.1%}; "
            "widening to 5% tolerance."
        )
        res1 = _try_single_stage(target_ratio, 0.05)
        if res1:
            z1, z2, actual, m = res1
            err = abs(actual - target_ratio) / target_ratio
            result = {
                "ok":            True,
                "stages":        1,
                "total_ratio":   round(actual, 8),
                "ratio_error":   round(err, 8),
                "stage_configs": [_build_stage(z1, z2, m, pressure_angle_deg)],
                "warnings":      [],
            }

    if result is None:
        return _err(
            f"Could not find a valid spur-gear configuration for "
            f"target_ratio={target_ratio:.4g} within any tolerance. "
            "The ratio may be outside the achievable range for standard "
            f"modules and tooth counts [{_Z_MIN}–{_Z_MAX}]."
        )

    # Annotate module preference warnings
    for i, sc in enumerate(result["stage_configs"]):
        m = sc["module"]
        if m not in _ISO_MODULES_FIRST:
            result["warnings"].append(
                f"Stage {i + 1}: module {m} mm is an ISO second-choice value. "
                "Prefer first-choice modules (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6 …) "
                "when possible for standard tooling."
            )

        # Undercut check
        if sc["z1"] < _Z_MIN:
            result["warnings"].append(
                f"Stage {i + 1}: pinion z1={sc['z1']} < {_Z_MIN} — "
                "undercut risk at 20° pressure angle; apply profile shift."
            )

    warnings_list.extend(result.pop("warnings", []))
    result["warnings"] = warnings_list

    return result
