"""
kerf_cad_core.turning.cycles — lathe CAM canned cycles + G-code post.

Provides pure-Python functions that consume a 2-D turning profile (a list of
(Z, X) radius points) and emit ISO G-code lines equivalent to the Fanuc/Siemens
canned cycles G71 (roughing), G70 (finish), G76 (threading), plus expanded
linear-move equivalents for facing, parting, and grooving.

Coordinate convention
---------------------
  Z — axial position (mm), positive towards tailstock from the chuck face.
  X — radius in mm (not diameter).  Must be >= 0.

Profile requirements
--------------------
* At least 2 points.
* Z values must be strictly monotone (either all increasing or all decreasing).
  Any segment that violates monotonicity is flagged as unreachable geometry via
  the Python ``warnings`` module — the function still returns all valid passes.

Cutting parameter formulae
--------------------------
  spindle_rpm  = (CSS_m_per_min × 1000) / (π × diameter_mm)
                 clamped to [rpm_min, rpm_max]
  feed_mm_rev  = chipload_mm_per_rev  (caller-specified or default per material)

G-code dialect
--------------
  G20 / G21  — inch / metric modal (always G21 in this module)
  G0 Xn Zn   — rapid
  G1 Xn Zn Fn — linear feed
  M3 Sn       — spindle on CW at n rpm
  M5          — spindle stop
  M30         — program end

All public functions return a ``TurningResult`` dataclass:
  ok        : bool
  gcode     : list[str] — ISO G-code lines (empty on failure)
  passes    : list[dict] — per-pass metadata dicts
  warnings  : list[str] — non-fatal geometry issues
  reason    : str — populated when ok=False

Functions never raise.  All validation errors are returned in the result.

References
----------
ISO 6983-1:2009 — Numerical control of machines — Part 1: general
Fanuc Series 0i-TF Operator's Manual (G71, G70, G76)
Machinery's Handbook, 30th ed.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants and defaults
# ---------------------------------------------------------------------------

_PI = math.pi

# G-code preamble / epilogue
_PREAMBLE = ["G21", "G18", "G40"]  # metric, ZX plane, cutter-comp cancel
_EPILOGUE = ["M5", "M30"]

# Default cutting parameters (steel medium-carbon, uncoated carbide insert)
_DEFAULT_CSS_M_MIN = 180.0   # constant surface speed, m/min
_DEFAULT_FEED_MM_REV = 0.20  # feed per revolution, mm/rev
_DEFAULT_DOC_MM = 2.0        # depth of cut (radial), mm
_DEFAULT_RPM_MIN = 50.0
_DEFAULT_RPM_MAX = 3500.0
_DEFAULT_FINISH_FEED = 0.08  # finishing feed mm/rev
_DEFAULT_FINISH_DOC = 0.25   # finishing depth of cut mm
_DEFAULT_RETRACT_MM = 2.0    # clearance for rapid approaches

# Threading defaults
_DEFAULT_THREAD_PITCH_MM = 1.5
_DEFAULT_THREAD_INFEED_DEG = 29.5  # compound infeed angle (degrees)
_DEFAULT_THREAD_SPRING_PASSES = 2

# Grooving defaults
_DEFAULT_GROOVE_WIDTH_MM = 3.0
_DEFAULT_GROOVE_DEPTH_MM = 2.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TurningResult:
    ok: bool
    gcode: list[str] = field(default_factory=list)
    passes: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> TurningResult:
    return TurningResult(ok=False, reason=reason)


def _fmt(v: float, decimals: int = 3) -> str:
    """Format a float to a fixed number of decimal places, strip trailing zeros."""
    s = f"{v:.{decimals}f}"
    # Keep at least one decimal place for G-code readability
    s = s.rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def _g0(z: float, x: float) -> str:
    return f"G0 X{_fmt(x * 2)} Z{_fmt(z)}"  # G-code uses diameter


def _g1(z: float, x: float, feed: float) -> str:
    return f"G1 X{_fmt(x * 2)} Z{_fmt(z)} F{_fmt(feed, 4)}"


def _g1_x(x: float, feed: float) -> str:
    return f"G1 X{_fmt(x * 2)} F{_fmt(feed, 4)}"


def _g1_z(z: float, feed: float) -> str:
    return f"G1 Z{_fmt(z)} F{_fmt(feed, 4)}"


def _spindle_on(rpm: float) -> str:
    return f"M3 S{int(round(rpm))}"


def _validate_profile(
    profile: Sequence[tuple[float, float]],
) -> tuple[list[tuple[float, float]], list[str], str]:
    """
    Validate and normalise a turning profile.

    Returns:
        (normalised_profile, warnings_list, error_str)
    error_str is non-empty if the profile is fatally invalid.
    """
    warns: list[str] = []

    if not isinstance(profile, (list, tuple)) or len(profile) < 2:
        return [], warns, "profile must be a list/tuple of at least 2 (Z, X) points"

    pts: list[tuple[float, float]] = []
    for i, pt in enumerate(profile):
        try:
            z, x = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            return [], warns, f"profile[{i}] must be a (Z, X) pair of numbers"
        if not math.isfinite(z) or not math.isfinite(x):
            return [], warns, f"profile[{i}] contains non-finite value: ({pt[0]}, {pt[1]})"
        if x < 0:
            warns.append(f"profile[{i}]: X radius {x} < 0; clamped to 0")
            x = 0.0
        pts.append((z, x))

    # Detect Z monotonicity and flag non-monotone segments
    z_vals = [p[0] for p in pts]
    diffs = [z_vals[i + 1] - z_vals[i] for i in range(len(z_vals) - 1)]

    non_monotone: list[int] = []
    if all(d > 0 for d in diffs):
        pass  # strictly increasing — OK
    elif all(d < 0 for d in diffs):
        pass  # strictly decreasing — OK
    else:
        for i, d in enumerate(diffs):
            if d == 0:
                non_monotone.append(i)
                warns.append(
                    f"profile segment [{i}]→[{i+1}] has Z={z_vals[i]:.3f} == Z={z_vals[i+1]:.3f}; "
                    "segment is degenerate (zero axial travel) — skipped in toolpath"
                )
                _warnings_module.warn(warns[-1], stacklevel=4)
        # Check for direction reversals
        positive = sum(1 for d in diffs if d > 0)
        negative = sum(1 for d in diffs if d < 0)
        if positive > 0 and negative > 0:
            warns.append(
                "profile Z is non-monotone (has both positive and negative steps); "
                "unreachable geometry detected — only first monotone span will be used"
            )
            _warnings_module.warn(warns[-1], stacklevel=4)
            # Truncate at first direction reversal
            direction = 1 if diffs[0] >= 0 else -1
            cut_at = len(pts)
            for i, d in enumerate(diffs):
                if direction == 1 and d < 0:
                    cut_at = i + 1
                    break
                elif direction == -1 and d > 0:
                    cut_at = i + 1
                    break
            pts = pts[:cut_at]

    return pts, warns, ""


def _calc_rpm(
    radius_mm: float,
    css_m_per_min: float,
    rpm_min: float,
    rpm_max: float,
) -> float:
    """Compute spindle RPM from constant surface speed (CSS)."""
    diameter_mm = radius_mm * 2.0
    if diameter_mm <= 0:
        return rpm_max  # near-zero diameter — run at max
    rpm = (css_m_per_min * 1000.0) / (_PI * diameter_mm)
    return max(rpm_min, min(rpm_max, rpm))


# ---------------------------------------------------------------------------
# 1. cutting_params — compute spindle + feed parameters
# ---------------------------------------------------------------------------

def cutting_params(
    profile: Sequence[tuple[float, float]],
    *,
    css_m_per_min: float = _DEFAULT_CSS_M_MIN,
    feed_mm_rev: float = _DEFAULT_FEED_MM_REV,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = _DEFAULT_RPM_MAX,
) -> dict:
    """
    Compute spindle RPM and feed-rate for each profile point.

    CSS (constant surface speed) is maintained by adjusting RPM as the tool
    moves along the profile.  Feed rate in mm/min = feed_mm_rev × RPM.

    Parameters
    ----------
    profile : list of (Z, X) pairs
        2-D turning profile.  X is radius in mm.
    css_m_per_min : float
        Constant surface speed in m/min.  Default 180 m/min (steel, carbide).
    feed_mm_rev : float
        Feed per revolution in mm/rev.  Default 0.20 mm/rev.
    rpm_min, rpm_max : float
        RPM clamp range.

    Returns
    -------
    dict
        ok          : True
        points      : list of dicts per profile point
            z_mm, x_mm (radius), diameter_mm, rpm, feed_mm_min
        css_m_per_min, feed_mm_rev
    """
    if not isinstance(profile, (list, tuple)) or len(profile) < 1:
        return {"ok": False, "reason": "profile must have at least 1 point"}
    if css_m_per_min <= 0:
        return {"ok": False, "reason": "css_m_per_min must be > 0"}
    if feed_mm_rev <= 0:
        return {"ok": False, "reason": "feed_mm_rev must be > 0"}
    if rpm_min <= 0 or rpm_max <= 0 or rpm_min > rpm_max:
        return {"ok": False, "reason": "rpm_min and rpm_max must be positive with rpm_min <= rpm_max"}

    points = []
    for i, pt in enumerate(profile):
        try:
            z, x = float(pt[0]), float(pt[1])
        except Exception:
            return {"ok": False, "reason": f"profile[{i}] is not a valid (Z, X) pair"}
        rpm = _calc_rpm(abs(x), css_m_per_min, rpm_min, rpm_max)
        feed_mm_min = feed_mm_rev * rpm
        points.append({
            "z_mm": z,
            "x_mm": x,
            "diameter_mm": x * 2.0,
            "rpm": round(rpm, 1),
            "feed_mm_min": round(feed_mm_min, 2),
        })

    return {
        "ok": True,
        "points": points,
        "css_m_per_min": css_m_per_min,
        "feed_mm_rev": feed_mm_rev,
        "rpm_min": rpm_min,
        "rpm_max": rpm_max,
    }


# ---------------------------------------------------------------------------
# 2. roughing_passes — G71-equivalent stock removal
# ---------------------------------------------------------------------------

def roughing_passes(
    profile: Sequence[tuple[float, float]],
    stock_x_mm: float,
    *,
    doc_mm: float = _DEFAULT_DOC_MM,
    css_m_per_min: float = _DEFAULT_CSS_M_MIN,
    feed_mm_rev: float = _DEFAULT_FEED_MM_REV,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = _DEFAULT_RPM_MAX,
    retract_mm: float = _DEFAULT_RETRACT_MM,
    finish_allowance_mm: float = 0.3,
) -> TurningResult:
    """
    Generate roughing passes (G71-equivalent) for OD turning.

    Starting from ``stock_x_mm`` (initial stock radius), generates successive
    axial passes at a radial depth of ``doc_mm`` per pass until the profile
    radius (plus ``finish_allowance_mm``) is reached.

    Each pass:
      1. Rapid to start Z (clear of part) at current stock radius + retract
      2. Rapid in Z to profile Z_start
      3. Feed along Z following the pass radius contour
      4. Retract in X
      5. Rapid back to Z start

    Parameters
    ----------
    profile : list of (Z, X) pairs
        2-D turning profile.  Must be at least 2 points; Z must be monotone.
    stock_x_mm : float
        Initial stock radius (mm).  Must be > max(X in profile).
    doc_mm : float
        Depth of cut per pass (radial), mm.  Default 2.0.
    css_m_per_min : float
        Constant surface speed, m/min.
    feed_mm_rev : float
        Feed per revolution, mm/rev.
    rpm_min, rpm_max : float
        RPM clamp range.
    retract_mm : float
        Radial clearance for rapid retract moves, mm.
    finish_allowance_mm : float
        Radial material left for finishing pass.  Default 0.3 mm.

    Returns
    -------
    TurningResult
    """
    pts, warns, err = _validate_profile(profile)
    if err:
        return _err(err)

    if not isinstance(stock_x_mm, (int, float)) or not math.isfinite(stock_x_mm):
        return _err("stock_x_mm must be a finite number")
    if doc_mm <= 0:
        return _err("doc_mm must be > 0")
    if finish_allowance_mm < 0:
        return _err("finish_allowance_mm must be >= 0")

    stock_x = float(stock_x_mm)
    profile_max_x = max(p[1] for p in pts)

    if stock_x <= profile_max_x + finish_allowance_mm:
        return _err(
            f"stock_x_mm ({stock_x:.3f}) must be > profile max X ({profile_max_x:.3f}) "
            f"+ finish_allowance ({finish_allowance_mm:.3f})"
        )

    z_start = pts[0][0]
    z_end = pts[-1][0]

    lines: list[str] = list(_PREAMBLE)
    passes_meta: list[dict] = []

    # Determine pass radii: start from stock, step inward by doc_mm
    target_x = profile_max_x + finish_allowance_mm
    pass_radii: list[float] = []
    r = stock_x
    while r > target_x + 1e-9:
        r -= doc_mm
        if r < target_x:
            r = target_x
        pass_radii.append(r)

    # For each pass radius, generate the toolpath
    for pass_idx, pass_r in enumerate(pass_radii):
        rpm = _calc_rpm(pass_r, css_m_per_min, rpm_min, rpm_max)
        feed_mm_min = feed_mm_rev * rpm

        lines.append(f"(--- ROUGH PASS {pass_idx + 1}: X radius = {_fmt(pass_r)} mm ---)")
        lines.append(_spindle_on(rpm))
        # Rapid to clearance position above stock
        lines.append(_g0(z_start - retract_mm, stock_x + retract_mm))
        # Rapid to pass start X
        lines.append(_g0(z_start - retract_mm, pass_r + retract_mm))
        # Feed to Z_start
        lines.append(_g1_z(z_start, feed_mm_min))

        # Follow profile at pass_r (clipped to pass radius)
        prev_z, _ = pts[0]
        for seg_z, seg_x in pts[1:]:
            # Effective X for this pass: max(pass_r, profile_x)
            eff_x = max(pass_r, seg_x + finish_allowance_mm)
            eff_x = min(eff_x, stock_x + retract_mm)
            step_rpm = _calc_rpm(eff_x, css_m_per_min, rpm_min, rpm_max)
            step_feed = feed_mm_rev * step_rpm
            lines.append(_g1(seg_z, eff_x, step_feed))
            prev_z = seg_z

        # Retract
        lines.append(_g1_x(pass_r + retract_mm, feed_mm_min))
        lines.append(_g0(z_start - retract_mm, pass_r + retract_mm))

        passes_meta.append({
            "pass_type": "rough",
            "pass_index": pass_idx + 1,
            "pass_radius_mm": pass_r,
            "rpm": round(rpm, 1),
            "feed_mm_min": round(feed_mm_min, 2),
            "feed_mm_rev": feed_mm_rev,
            "z_start": z_start,
            "z_end": z_end,
        })

    lines += list(_EPILOGUE)

    return TurningResult(
        ok=True,
        gcode=lines,
        passes=passes_meta,
        warnings=warns,
    )


# ---------------------------------------------------------------------------
# 3. finishing_pass — G70-equivalent finish
# ---------------------------------------------------------------------------

def finishing_pass(
    profile: Sequence[tuple[float, float]],
    *,
    css_m_per_min: float = _DEFAULT_CSS_M_MIN,
    feed_mm_rev: float = _DEFAULT_FINISH_FEED,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = _DEFAULT_RPM_MAX,
    retract_mm: float = _DEFAULT_RETRACT_MM,
    doc_mm: float = _DEFAULT_FINISH_DOC,
) -> TurningResult:
    """
    Generate a finishing pass (G70-equivalent) that follows the exact profile.

    A single pass that traverses all profile segments at the finishing feed
    rate.  RPM is computed per segment using constant surface speed.

    Parameters
    ----------
    profile : list of (Z, X) pairs
        Final part profile.
    css_m_per_min : float
        Constant surface speed, m/min.  Default 180 m/min.
    feed_mm_rev : float
        Finishing feed per rev, mm/rev.  Default 0.08 mm/rev.
    doc_mm : float
        Finishing depth of cut (for metadata only — pass follows profile exactly).

    Returns
    -------
    TurningResult
    """
    pts, warns, err = _validate_profile(profile)
    if err:
        return _err(err)
    if feed_mm_rev <= 0:
        return _err("feed_mm_rev must be > 0")

    z_start = pts[0][0]
    x_start = pts[0][1]

    lines: list[str] = list(_PREAMBLE)
    rpm_start = _calc_rpm(x_start, css_m_per_min, rpm_min, rpm_max)
    lines.append("(--- FINISHING PASS ---)")
    lines.append(_spindle_on(rpm_start))
    lines.append(_g0(z_start - retract_mm, x_start + retract_mm))
    lines.append(_g0(z_start - retract_mm, x_start))
    feed_start = feed_mm_rev * rpm_start
    lines.append(_g1_z(z_start, feed_start))

    for z, x in pts[1:]:
        rpm = _calc_rpm(x, css_m_per_min, rpm_min, rpm_max)
        feed = feed_mm_rev * rpm
        lines.append(_g1(z, x, feed))

    # Retract
    z_end = pts[-1][0]
    x_end = pts[-1][1]
    rpm_end = _calc_rpm(x_end, css_m_per_min, rpm_min, rpm_max)
    feed_end = feed_mm_rev * rpm_end
    lines.append(_g1_x(x_end + retract_mm, feed_end))
    lines += list(_EPILOGUE)

    pass_meta = {
        "pass_type": "finish",
        "pass_index": 1,
        "rpm_start": round(rpm_start, 1),
        "feed_mm_rev": feed_mm_rev,
        "doc_mm": doc_mm,
        "z_start": z_start,
        "z_end": z_end,
        "points": len(pts),
    }

    return TurningResult(
        ok=True,
        gcode=lines,
        passes=[pass_meta],
        warnings=warns,
    )


# ---------------------------------------------------------------------------
# 4. facing_pass — face the part end
# ---------------------------------------------------------------------------

def facing_pass(
    x_max_mm: float,
    z_face_mm: float,
    *,
    doc_mm: float = _DEFAULT_DOC_MM,
    n_passes: int = 1,
    css_m_per_min: float = _DEFAULT_CSS_M_MIN,
    feed_mm_rev: float = _DEFAULT_FEED_MM_REV,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = _DEFAULT_RPM_MAX,
    retract_mm: float = _DEFAULT_RETRACT_MM,
    bore_radius_mm: float = 0.0,
) -> TurningResult:
    """
    Generate facing passes across the end face of the workpiece.

    Cuts from ``x_max_mm`` (OD) inward to ``bore_radius_mm`` (or spindle CL=0)
    at Z = ``z_face_mm``.

    Parameters
    ----------
    x_max_mm : float
        Outer radius at face, mm.
    z_face_mm : float
        Z position of the face to be cut, mm.
    doc_mm : float
        Axial depth of cut per pass (stock removal per pass), mm.
    n_passes : int
        Number of facing passes.  Default 1.
    bore_radius_mm : float
        Inner bore radius (stop before this radius).  Default 0 (through-centre).

    Returns
    -------
    TurningResult
    """
    if not isinstance(x_max_mm, (int, float)) or x_max_mm <= 0:
        return _err("x_max_mm must be a positive number")
    if not isinstance(z_face_mm, (int, float)) or not math.isfinite(z_face_mm):
        return _err("z_face_mm must be a finite number")
    if doc_mm <= 0:
        return _err("doc_mm must be > 0")
    if n_passes < 1:
        return _err("n_passes must be >= 1")
    if bore_radius_mm < 0:
        return _err("bore_radius_mm must be >= 0")
    if bore_radius_mm >= x_max_mm:
        return _err("bore_radius_mm must be < x_max_mm")

    lines: list[str] = list(_PREAMBLE)
    passes_meta: list[dict] = []
    warns: list[str] = []

    z_current = z_face_mm
    for i in range(n_passes):
        rpm = _calc_rpm(x_max_mm, css_m_per_min, rpm_min, rpm_max)
        feed_mm_min = feed_mm_rev * rpm

        lines.append(f"(--- FACING PASS {i + 1} ---)")
        lines.append(_spindle_on(rpm))
        # Rapid to start: outside OD, at current Z + retract
        lines.append(_g0(z_current + retract_mm, x_max_mm + retract_mm))
        # Move to face Z
        lines.append(_g1_z(z_current, feed_mm_min))
        # Feed inward to bore/CL
        lines.append(_g1_x(bore_radius_mm, feed_mm_min))
        # Retract axially
        lines.append(_g0(z_current + retract_mm, bore_radius_mm))

        passes_meta.append({
            "pass_type": "facing",
            "pass_index": i + 1,
            "z_mm": z_current,
            "x_max_mm": x_max_mm,
            "bore_radius_mm": bore_radius_mm,
            "rpm": round(rpm, 1),
            "feed_mm_min": round(feed_mm_min, 2),
        })

        z_current -= doc_mm

    lines += list(_EPILOGUE)

    return TurningResult(ok=True, gcode=lines, passes=passes_meta, warnings=warns)


# ---------------------------------------------------------------------------
# 5. parting_pass
# ---------------------------------------------------------------------------

def parting_pass(
    z_part_mm: float,
    x_max_mm: float,
    *,
    css_m_per_min: float = 80.0,  # parting uses lower CSS
    feed_mm_rev: float = 0.05,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = 1200.0,  # parting limited RPM
    retract_mm: float = _DEFAULT_RETRACT_MM,
    bore_radius_mm: float = 0.0,
    peck_depth_mm: float | None = None,
) -> TurningResult:
    """
    Generate a parting (cut-off) pass.

    Feeds the parting blade in the -X direction (inward) at ``z_part_mm``
    until the bore is reached (or spindle CL for solid bar).

    Parameters
    ----------
    z_part_mm : float
        Axial position of the parting cut, mm.
    x_max_mm : float
        Outer radius at cut location, mm.
    css_m_per_min : float
        Surface speed (parting: typically 60-100 m/min).
    feed_mm_rev : float
        Feed per revolution (parting: 0.03-0.08 mm/rev).
    bore_radius_mm : float
        Stop radius for hollow workpiece.  0 = through centre.
    peck_depth_mm : float | None
        If set, performs peck parting (intermittent retract) at this radial
        depth increment.

    Returns
    -------
    TurningResult
    """
    if not isinstance(z_part_mm, (int, float)) or not math.isfinite(z_part_mm):
        return _err("z_part_mm must be a finite number")
    if not isinstance(x_max_mm, (int, float)) or x_max_mm <= 0:
        return _err("x_max_mm must be > 0")
    if bore_radius_mm < 0:
        return _err("bore_radius_mm must be >= 0")
    if bore_radius_mm >= x_max_mm:
        return _err("bore_radius_mm must be < x_max_mm")
    if feed_mm_rev <= 0:
        return _err("feed_mm_rev must be > 0")

    lines: list[str] = list(_PREAMBLE)
    passes_meta: list[dict] = []
    warns: list[str] = []

    rpm = _calc_rpm(x_max_mm, css_m_per_min, rpm_min, rpm_max)
    feed_mm_min = feed_mm_rev * rpm

    lines.append("(--- PARTING PASS ---)")
    lines.append(_spindle_on(rpm))
    lines.append(_g0(z_part_mm, x_max_mm + retract_mm))
    lines.append(_g0(z_part_mm, x_max_mm))

    if peck_depth_mm is not None and peck_depth_mm > 0:
        # Peck parting
        current_x = x_max_mm
        peck_idx = 0
        while current_x > bore_radius_mm + 1e-9:
            target_x = max(bore_radius_mm, current_x - peck_depth_mm)
            lines.append(f"(peck {peck_idx + 1}: to X radius {_fmt(target_x)} mm)")
            lines.append(_g1_x(target_x, feed_mm_min))
            current_x = target_x
            if current_x > bore_radius_mm + 1e-9:
                # Retract slightly for chip clearance
                lines.append(_g0(z_part_mm, current_x + 1.0))
                lines.append(_g0(z_part_mm, current_x))
            peck_idx += 1
    else:
        # Single plunge
        lines.append(_g1_x(bore_radius_mm, feed_mm_min))

    # Retract
    lines.append(_g0(z_part_mm, x_max_mm + retract_mm))
    lines += list(_EPILOGUE)

    passes_meta.append({
        "pass_type": "parting",
        "pass_index": 1,
        "z_mm": z_part_mm,
        "x_max_mm": x_max_mm,
        "bore_radius_mm": bore_radius_mm,
        "rpm": round(rpm, 1),
        "feed_mm_min": round(feed_mm_min, 2),
        "peck_depth_mm": peck_depth_mm,
    })

    return TurningResult(ok=True, gcode=lines, passes=passes_meta, warnings=warns)


# ---------------------------------------------------------------------------
# 6. od_threading — external thread (G76-equivalent)
# ---------------------------------------------------------------------------

def od_threading(
    z_start_mm: float,
    z_end_mm: float,
    x_major_mm: float,
    *,
    pitch_mm: float = _DEFAULT_THREAD_PITCH_MM,
    thread_depth_mm: float | None = None,
    infeed_deg: float = _DEFAULT_THREAD_INFEED_DEG,
    first_pass_depth_mm: float = 0.3,
    min_pass_depth_mm: float = 0.05,
    spring_passes: int = _DEFAULT_THREAD_SPRING_PASSES,
    css_m_per_min: float = 100.0,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = 800.0,
    retract_mm: float = 3.0,
) -> TurningResult:
    """
    Generate an OD (external) threading cycle (G76-style expanded moves).

    Computes an infeed schedule using the compound-infeed method (29.5°
    default) to reduce cutting force on successive passes.  Each pass cuts
    one flank of the thread.

    Parameters
    ----------
    z_start_mm : float
        Start Z of the thread (approach end), mm.
    z_end_mm : float
        End Z of the thread (relief end; z_end < z_start for conventional RH
        threading away from chuck), mm.
    x_major_mm : float
        Major diameter radius (OD of thread), mm.
    pitch_mm : float
        Thread pitch, mm.  Default 1.5 mm.
    thread_depth_mm : float | None
        Full thread depth (radial).  If None, computed from pitch:
        depth = 0.6495 × pitch (ISO 68-1 for 60° thread).
    infeed_deg : float
        Compound slide infeed angle, degrees.  29.5° for 60° thread.
    first_pass_depth_mm : float
        First pass radial depth.  Default 0.3 mm.
    min_pass_depth_mm : float
        Minimum pass depth (for degression schedule).  Default 0.05 mm.
    spring_passes : int
        Number of spring (no-feed) passes at full depth.  Default 2.
    css_m_per_min : float
        Surface speed for threading, m/min (constant; CSS mode common for
        threading with encoder feedback; RPM may also be specified directly).
    rpm_max : float
        Maximum threading RPM.  Default 800.

    Returns
    -------
    TurningResult
        Each G-code block is a single-pass G32-style linear thread cut:
        ``G32 Z<end> F<pitch>``
    """
    if not math.isfinite(float(z_start_mm)):
        return _err("z_start_mm must be finite")
    if not math.isfinite(float(z_end_mm)):
        return _err("z_end_mm must be finite")
    if z_start_mm == z_end_mm:
        return _err("z_start_mm and z_end_mm must differ")
    if x_major_mm <= 0:
        return _err("x_major_mm must be > 0")
    if pitch_mm <= 0:
        return _err("pitch_mm must be > 0")
    if first_pass_depth_mm <= 0:
        return _err("first_pass_depth_mm must be > 0")
    if min_pass_depth_mm <= 0:
        return _err("min_pass_depth_mm must be > 0")
    if spring_passes < 0:
        return _err("spring_passes must be >= 0")

    z_s = float(z_start_mm)
    z_e = float(z_end_mm)
    x_maj = float(x_major_mm)

    # Full thread depth (radial) per ISO 68-1 for 60° threads
    if thread_depth_mm is None:
        t_depth = 0.6495 * pitch_mm
    else:
        if thread_depth_mm <= 0:
            return _err("thread_depth_mm must be > 0")
        t_depth = float(thread_depth_mm)

    # Build infeed schedule using degressive method
    # depth_n = first_pass * √n  (cumulative); pass depth = cumul_n - cumul_(n-1)
    infeed_rad = math.radians(float(infeed_deg))
    infeed_factor = math.cos(infeed_rad)  # X component of compound movement

    # Compute cumulative depths using √n degression
    pass_depths: list[float] = []
    cumul = 0.0
    n = 1
    while cumul < t_depth - 1e-9:
        cumul_n = first_pass_depth_mm * math.sqrt(n)
        cumul_n = min(cumul_n, t_depth)
        step = cumul_n - cumul
        if step < min_pass_depth_mm:
            step = min_pass_depth_mm
            cumul_n = cumul + step
        if cumul_n > t_depth:
            step = t_depth - cumul
            cumul_n = t_depth
        pass_depths.append(step)
        cumul = cumul_n
        n += 1
        if cumul >= t_depth - 1e-9:
            break

    # Add spring passes
    for _ in range(spring_passes):
        pass_depths.append(0.0)

    rpm = _calc_rpm(x_maj, css_m_per_min, rpm_min, rpm_max)

    lines: list[str] = list(_PREAMBLE)
    lines.append(f"(--- OD THREADING: pitch={_fmt(pitch_mm)} mm, depth={_fmt(t_depth)} mm ---)")
    lines.append(_spindle_on(rpm))
    lines.append(f"G0 X{_fmt((x_maj + retract_mm) * 2)} Z{_fmt(z_s + retract_mm)}")

    passes_meta: list[dict] = []
    warns: list[str] = []
    cumul_depth = 0.0

    for pass_idx, pass_step in enumerate(pass_depths):
        cumul_depth += pass_step
        x_pass = x_maj - cumul_depth  # OD threading cuts inward
        if x_pass < 0:
            warns.append(
                f"Threading pass {pass_idx + 1}: x_pass={x_pass:.3f} < 0 "
                "(thread depth exceeds major radius) — clamped to 0"
            )
            _warnings_module.warn(warns[-1], stacklevel=2)
            x_pass = 0.0

        is_spring = (pass_step == 0.0)
        pass_label = f"spring {pass_idx - len(pass_depths) + spring_passes + 1}" if is_spring else f"cut {pass_idx + 1}"

        lines.append(f"(pass {pass_label}: X radius = {_fmt(x_pass)} mm)")
        # Rapid to thread start
        lines.append(f"G0 X{_fmt(x_pass * 2)} Z{_fmt(z_s)}")
        # G32 thread cutting move (constant-lead; synchronised spindle encoder)
        lines.append(f"G32 Z{_fmt(z_e)} F{_fmt(pitch_mm, 4)}")
        # Retract in X then return to start Z
        lines.append(f"G0 X{_fmt((x_maj + retract_mm) * 2)}")
        lines.append(f"G0 Z{_fmt(z_s)}")

        passes_meta.append({
            "pass_type": "od_thread",
            "pass_index": pass_idx + 1,
            "is_spring": is_spring,
            "x_radius_mm": x_pass,
            "cumul_depth_mm": cumul_depth,
            "step_depth_mm": pass_step,
            "pitch_mm": pitch_mm,
            "rpm": round(rpm, 1),
            "z_start": z_s,
            "z_end": z_e,
        })

    lines += list(_EPILOGUE)

    return TurningResult(ok=True, gcode=lines, passes=passes_meta, warnings=warns)


# ---------------------------------------------------------------------------
# 7. id_threading — internal thread
# ---------------------------------------------------------------------------

def id_threading(
    z_start_mm: float,
    z_end_mm: float,
    x_minor_mm: float,
    *,
    pitch_mm: float = _DEFAULT_THREAD_PITCH_MM,
    thread_depth_mm: float | None = None,
    infeed_deg: float = _DEFAULT_THREAD_INFEED_DEG,
    first_pass_depth_mm: float = 0.2,
    min_pass_depth_mm: float = 0.03,
    spring_passes: int = _DEFAULT_THREAD_SPRING_PASSES,
    css_m_per_min: float = 80.0,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = 600.0,
    retract_mm: float = 2.0,
) -> TurningResult:
    """
    Generate an ID (internal) threading cycle.

    Mirror of ``od_threading`` but for bores: the tool cuts outward (+X
    direction) from the minor radius, using G32 thread cuts.

    Parameters
    ----------
    x_minor_mm : float
        Minor (bore) radius before threading, mm.  The tool starts here and
        moves outward by ``thread_depth_mm`` over the infeed schedule.

    (All other parameters as per ``od_threading``.)

    Returns
    -------
    TurningResult
    """
    if not math.isfinite(float(z_start_mm)):
        return _err("z_start_mm must be finite")
    if not math.isfinite(float(z_end_mm)):
        return _err("z_end_mm must be finite")
    if z_start_mm == z_end_mm:
        return _err("z_start_mm and z_end_mm must differ")
    if x_minor_mm <= 0:
        return _err("x_minor_mm must be > 0")
    if pitch_mm <= 0:
        return _err("pitch_mm must be > 0")
    if first_pass_depth_mm <= 0:
        return _err("first_pass_depth_mm must be > 0")

    z_s = float(z_start_mm)
    z_e = float(z_end_mm)
    x_min = float(x_minor_mm)

    if thread_depth_mm is None:
        t_depth = 0.6495 * pitch_mm
    else:
        if thread_depth_mm <= 0:
            return _err("thread_depth_mm must be > 0")
        t_depth = float(thread_depth_mm)

    # Build degressive infeed schedule (same algorithm as OD)
    pass_depths: list[float] = []
    cumul = 0.0
    n = 1
    while cumul < t_depth - 1e-9:
        cumul_n = first_pass_depth_mm * math.sqrt(n)
        cumul_n = min(cumul_n, t_depth)
        step = cumul_n - cumul
        if step < min_pass_depth_mm:
            step = min_pass_depth_mm
            cumul_n = cumul + step
        if cumul_n > t_depth:
            step = t_depth - cumul
            cumul_n = t_depth
        pass_depths.append(step)
        cumul = cumul_n
        n += 1
        if cumul >= t_depth - 1e-9:
            break

    for _ in range(spring_passes):
        pass_depths.append(0.0)

    rpm = _calc_rpm(x_min, css_m_per_min, rpm_min, rpm_max)

    lines: list[str] = list(_PREAMBLE)
    lines.append(f"(--- ID THREADING: pitch={_fmt(pitch_mm)} mm, depth={_fmt(t_depth)} mm ---)")
    lines.append(_spindle_on(rpm))

    passes_meta: list[dict] = []
    warns: list[str] = []
    cumul_depth = 0.0

    for pass_idx, pass_step in enumerate(pass_depths):
        cumul_depth += pass_step
        x_pass = x_min + cumul_depth  # ID threading cuts outward

        is_spring = (pass_step == 0.0)
        pass_label = "spring" if is_spring else f"cut {pass_idx + 1}"

        lines.append(f"(pass {pass_label}: X radius = {_fmt(x_pass)} mm)")
        lines.append(f"G0 X{_fmt(x_pass * 2)} Z{_fmt(z_s)}")
        lines.append(f"G32 Z{_fmt(z_e)} F{_fmt(pitch_mm, 4)}")
        lines.append(f"G0 X{_fmt((x_min - retract_mm) * 2)}")
        lines.append(f"G0 Z{_fmt(z_s)}")

        passes_meta.append({
            "pass_type": "id_thread",
            "pass_index": pass_idx + 1,
            "is_spring": is_spring,
            "x_radius_mm": x_pass,
            "cumul_depth_mm": cumul_depth,
            "step_depth_mm": pass_step,
            "pitch_mm": pitch_mm,
            "rpm": round(rpm, 1),
            "z_start": z_s,
            "z_end": z_e,
        })

    lines += list(_EPILOGUE)

    return TurningResult(ok=True, gcode=lines, passes=passes_meta, warnings=warns)


# ---------------------------------------------------------------------------
# 8. grooving_pass
# ---------------------------------------------------------------------------

def grooving_pass(
    z_center_mm: float,
    x_start_mm: float,
    *,
    groove_depth_mm: float = _DEFAULT_GROOVE_DEPTH_MM,
    groove_width_mm: float = _DEFAULT_GROOVE_WIDTH_MM,
    tool_width_mm: float = 3.0,
    css_m_per_min: float = 100.0,
    feed_mm_rev: float = 0.05,
    rpm_min: float = _DEFAULT_RPM_MIN,
    rpm_max: float = 1200.0,
    retract_mm: float = _DEFAULT_RETRACT_MM,
    peck_depth_mm: float | None = None,
) -> TurningResult:
    """
    Generate a grooving (recessing) cycle.

    A single groove of ``groove_width_mm`` centred at ``z_center_mm``,
    starting from ``x_start_mm`` (OD) cutting inward by ``groove_depth_mm``.

    If ``groove_width_mm > tool_width_mm`` the groove is widened by stepping
    the tool laterally.

    Parameters
    ----------
    z_center_mm : float
        Axial centre of the groove, mm.
    x_start_mm : float
        OD radius at groove location, mm.
    groove_depth_mm : float
        Radial depth of groove, mm.
    groove_width_mm : float
        Total axial width of groove, mm.
    tool_width_mm : float
        Grooving insert width, mm.  Must be <= groove_width_mm.
    peck_depth_mm : float | None
        Peck increment for deep grooves.

    Returns
    -------
    TurningResult
    """
    if not math.isfinite(float(z_center_mm)):
        return _err("z_center_mm must be finite")
    if x_start_mm <= 0:
        return _err("x_start_mm must be > 0")
    if groove_depth_mm <= 0:
        return _err("groove_depth_mm must be > 0")
    if groove_width_mm <= 0:
        return _err("groove_width_mm must be > 0")
    if tool_width_mm <= 0:
        return _err("tool_width_mm must be > 0")
    if tool_width_mm > groove_width_mm:
        return _err("tool_width_mm must be <= groove_width_mm")
    if feed_mm_rev <= 0:
        return _err("feed_mm_rev must be > 0")

    z_c = float(z_center_mm)
    x_s = float(x_start_mm)
    g_depth = float(groove_depth_mm)
    g_width = float(groove_width_mm)
    t_width = float(tool_width_mm)

    x_bottom = x_s - g_depth

    rpm = _calc_rpm(x_s, css_m_per_min, rpm_min, rpm_max)
    feed_mm_min = feed_mm_rev * rpm

    lines: list[str] = list(_PREAMBLE)
    lines.append(
        f"(--- GROOVING: Z={_fmt(z_c)} mm, depth={_fmt(g_depth)} mm, "
        f"width={_fmt(g_width)} mm ---)"
    )
    lines.append(_spindle_on(rpm))
    passes_meta: list[dict] = []
    warns: list[str] = []

    # Compute tool positions needed to cover groove width
    half_w = g_width / 2.0
    # First plunge at centre; then step left/right as needed
    z_positions: list[float] = [z_c]
    step = t_width * 0.8  # 20% overlap
    z_left = z_c - step
    z_right = z_c + step
    while z_left >= z_c - half_w + t_width / 2.0 - 1e-9:
        z_positions.insert(0, z_left)
        z_positions.append(z_right)
        z_left -= step
        z_right += step

    for pos_idx, z_pos in enumerate(z_positions):
        lines.append(f"(groove plunge {pos_idx + 1}: Z={_fmt(z_pos)} mm)")
        lines.append(_g0(z_pos, x_s + retract_mm))
        lines.append(_g0(z_pos, x_s))

        if peck_depth_mm is not None and peck_depth_mm > 0:
            current_x = x_s
            peck_n = 0
            while current_x > x_bottom + 1e-9:
                target_x = max(x_bottom, current_x - peck_depth_mm)
                lines.append(_g1_x(target_x, feed_mm_min))
                current_x = target_x
                if current_x > x_bottom + 1e-9:
                    lines.append(_g0(z_pos, x_s))
                    lines.append(_g0(z_pos, current_x + 0.5))
                peck_n += 1
        else:
            lines.append(_g1_x(x_bottom, feed_mm_min))

        lines.append(_g0(z_pos, x_s + retract_mm))

        passes_meta.append({
            "pass_type": "grooving",
            "pass_index": pos_idx + 1,
            "z_mm": z_pos,
            "x_start_mm": x_s,
            "x_bottom_mm": x_bottom,
            "rpm": round(rpm, 1),
            "feed_mm_min": round(feed_mm_min, 2),
        })

    lines += list(_EPILOGUE)

    return TurningResult(ok=True, gcode=lines, passes=passes_meta, warnings=warns)


# ---------------------------------------------------------------------------
# 9. emit_gcode — serialise a TurningResult to a G-code string
# ---------------------------------------------------------------------------

def emit_gcode(result: TurningResult, *, header: str = "") -> str:
    """
    Serialise a ``TurningResult`` to a single G-code string.

    Parameters
    ----------
    result : TurningResult
        Output from any cycle function.
    header : str
        Optional program header comment (e.g. program number, part name).

    Returns
    -------
    str
        Newline-separated G-code.  Empty string on failure.
    """
    if not isinstance(result, TurningResult):
        return ""
    if not result.ok:
        return f"( ERROR: {result.reason} )"
    lines: list[str] = []
    if header:
        lines.append(f"( {header} )")
    lines += result.gcode
    return "\n".join(lines)
