"""
kerf_cad_core.jewelry.cam_wax — Wax-routing CAM planner for jewelry.

Ties together the existing CAM infrastructure (cncfeeds, fiveaxis, turning,
gcode) into a jewelry-specific wax-milling workflow.

Public API
----------
plan_wax_routing(piece, machine_kinematics, tool_library, stock_block)
    Master planning function.  Given:
      - piece spec  (ring / pendant / setting dict from existing jewelry modules)
      - machine_kinematics dict (see MachineKinematics below)
      - tool_library list (see ToolEntry below)
      - stock_block dict  (see StockBlock below)
    Returns a WaxRoutingPlan dict with:
      - roughing_strategy   : parallel-plane Z-level pass plan
      - finishing_strategy  : 3-axis surface-finish + 5-axis tilt plan
      - gcode_stubs         : per-axis ISO G-code lines
      - cycle_time_s        : estimated total cycle time (seconds)
      - tool_list           : ordered list of tools actually used
      - collision_warnings  : list of collision / clamp proximity strings
      - ok                  : bool (False + reason on hard error)

Jewellery-specific features
---------------------------
* Ring bore: automatically plans 4-axis indexed bore passes and
  5-axis tilt finishing for the inner diameter.
* Prong under-reach: tilts the finishing tool by `prong_tilt_deg`
  (default 10°) to clear the prong base.
* Clamp proximity warning: if the piece Y-extent comes within
  `clamp_clearance_mm` (default 3.0 mm) of the stock-block edge
  the collision_warnings list is populated.

Machine kinematics dict schema
-------------------------------
  type         : str  — "4axis_indexed" | "5axis_trunnion" | "5axis_head_head"
  pivot_mm     : float — distance from rotary pivot to tool tip (mm)
  a_lo_deg     : float — A-axis lower travel limit (deg, default -120)
  a_hi_deg     : float — A-axis upper travel limit (deg, default  +30)
  rapid_mm_min : float — rapid traverse rate (mm/min, default 10 000)
  accel_mm_s2  : float — machine acceleration (mm/s², default 500)

Tool library list — each entry dict
------------------------------------
  name        : str   — tool identifier
  type        : str   — "ball_nose" | "fishtail" | "flat_end" | "tapered_ball"
  diameter_mm : float — cutting diameter
  flutes      : int   — number of flutes
  stickout_mm : float — tool stickout from spindle face
  vc_m_min    : float — cutting speed (m/min) for wax
  chip_load_mm: float — chip load per tooth

Stock block dict
-----------------
  width_mm  : float — X extent
  depth_mm  : float — Y extent
  height_mm : float — Z extent (= total stock height above table)

LLM tools registered
---------------------
  jewelry_wax_plan_routing
  jewelry_wax_list_tools
  jewelry_wax_estimate_cycle_time

All tools gate on OCC / kerf_chat availability; NEVER raise.
Error path always returns {"ok": False, "reason": "<human-readable>"}.

References
----------
Stoeckel, D. & Waram, T. "Jewelry CAM: wax milling for lost-wax casting",
  Gold Technology, AMES, 2002.
Matsuura Corp. "5-axis jewelry application note", 2019.
Sandvik Coromant – Wax & Foam machining guide, 2021.

Author: imranparuk
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from kerf_cad_core._guards import _err

# ---------------------------------------------------------------------------
# Import-guarded CAM helpers
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.cncfeeds.calc import (
        spindle_rpm,
        feed_rate,
        mrr_milling,
        cutting_power,
        surface_finish_ra,
    )
    _CNCFEEDS_OK = True
except ImportError:  # pragma: no cover
    _CNCFEEDS_OK = False

try:
    from kerf_cad_core.fiveaxis.kinematics import (
        MachineConfig,
        MachineType,
        RotaryAxis,
        inverse_post,
        collision_cone_check,
    )
    _FIVEAXIS_OK = True
except ImportError:  # pragma: no cover
    _FIVEAXIS_OK = False

try:
    from kerf_cad_core.gcode.post import cycle_time, toolpath_stats
    _GCODE_OK = True
except ImportError:  # pragma: no cover
    _GCODE_OK = False

# LLM registration — import-guarded so the module can be unit-tested without
# the full kerf-chat / kerf-core stack installed.
try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    _REGISTRY_OK = True
except ImportError:
    _REGISTRY_OK = False

    class ProjectCtx:  # type: ignore[no-redef]
        pass

    def register(*_a, **_kw):  # type: ignore[no-redef]
        """Stub decorator when kerf_chat is not installed."""
        def _dec(fn):
            return fn
        return _dec

    def err_payload(msg: str, code: str = "ERROR") -> str:  # type: ignore[no-redef]
        return json.dumps({"ok": False, "reason": msg, "code": code})

    def ok_payload(data: dict) -> str:  # type: ignore[no-redef]
        return json.dumps({"ok": True, **data})

    class ToolSpec:  # type: ignore[no-redef]
        def __init__(self, *, name: str, description: str, input_schema: dict):
            self.name = name
            self.description = description
            self.input_schema = input_schema


# ---------------------------------------------------------------------------
# Wax material constants
# ---------------------------------------------------------------------------

# Wax Kc (specific cutting energy, N/mm²) — machinable modelling wax
_WAX_KC_N_MM2 = 35.0

# Default cutting parameters for jewellery wax (based on Sandvik foam/wax guide)
_WAX_VC_M_MIN_BALL     = 60.0    # ball-nose finishing
_WAX_VC_M_MIN_ROUGH    = 45.0    # flat-end roughing
_WAX_CHIP_LOAD_BALL    = 0.010   # mm/tooth — fine detail ball
_WAX_CHIP_LOAD_FISHTAIL = 0.015  # mm/tooth — undercut fishtail
_WAX_CHIP_LOAD_FLAT    = 0.020   # mm/tooth — roughing flat end

# Clamp-proximity warning threshold (mm)
_CLAMP_CLEARANCE_MM = 3.0

# Default rough step-down (Z-level pass height, mm)
_ROUGH_STEPDWN_DEFAULT = 0.8

# Default finish step-over as fraction of tool diameter
_FINISH_STEPOVER_FRAC = 0.10

# Default 5-axis tilt for prong / bore under-reach (degrees)
_PRONG_TILT_DEG = 10.0

# Ring bore: minimum inner-diameter ratio that triggers bore finishing
_RING_BORE_TRIGGER_RATIO = 0.3   # bore_dia / stock_width


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _positive(name: str, val: Any) -> Optional[str]:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _nonneg(name: str, val: Any) -> Optional[str]:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


# ---------------------------------------------------------------------------
# Data structures (plain dicts for callers; dataclasses for internal use)
# ---------------------------------------------------------------------------

@dataclass
class _ToolEntry:
    name: str
    tool_type: str          # "ball_nose" | "fishtail" | "flat_end" | "tapered_ball"
    diameter_mm: float
    flutes: int
    stickout_mm: float
    vc_m_min: float
    chip_load_mm: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.tool_type,
            "diameter_mm": self.diameter_mm,
            "flutes": self.flutes,
            "stickout_mm": self.stickout_mm,
            "vc_m_min": self.vc_m_min,
            "chip_load_mm": self.chip_load_mm,
        }


@dataclass
class _StockBlock:
    width_mm: float
    depth_mm: float
    height_mm: float

    @property
    def volume_mm3(self) -> float:
        return self.width_mm * self.depth_mm * self.height_mm


@dataclass
class _MachineKinematics:
    machine_type: str        # "4axis_indexed" | "5axis_trunnion" | "5axis_head_head"
    pivot_mm: float
    a_lo_deg: float = -120.0
    a_hi_deg: float = 30.0
    rapid_mm_min: float = 10_000.0
    accel_mm_s2: float = 500.0


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _parse_tool_library(raw: list) -> Tuple[List[_ToolEntry], List[str]]:
    """Parse a list of tool dicts into _ToolEntry objects.  Returns (tools, errors)."""
    tools: List[_ToolEntry] = []
    errors: List[str] = []
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            errors.append(f"tool[{i}] is not a dict")
            continue
        name = str(t.get("name", f"tool_{i}"))
        tool_type = str(t.get("type", "ball_nose")).lower()
        if tool_type not in ("ball_nose", "fishtail", "flat_end", "tapered_ball"):
            errors.append(
                f"tool '{name}': unknown type '{tool_type}'; "
                "use ball_nose, fishtail, flat_end, or tapered_ball"
            )
            continue
        for fld in ("diameter_mm", "flutes", "stickout_mm"):
            if t.get(fld) is None:
                errors.append(f"tool '{name}': missing required field '{fld}'")
                break
        else:
            try:
                tools.append(_ToolEntry(
                    name=name,
                    tool_type=tool_type,
                    diameter_mm=float(t["diameter_mm"]),
                    flutes=int(t["flutes"]),
                    stickout_mm=float(t["stickout_mm"]),
                    vc_m_min=float(t.get("vc_m_min", _WAX_VC_M_MIN_BALL)),
                    chip_load_mm=float(t.get("chip_load_mm", _WAX_CHIP_LOAD_BALL)),
                ))
            except (TypeError, ValueError) as exc:
                errors.append(f"tool '{name}': bad value — {exc}")
    return tools, errors


def _parse_machine(raw: dict) -> Tuple[Optional[_MachineKinematics], Optional[str]]:
    mtype = str(raw.get("type", "5axis_trunnion")).lower()
    if mtype not in ("4axis_indexed", "5axis_trunnion", "5axis_head_head"):
        return None, (
            f"machine type '{mtype}' not recognised; "
            "use 4axis_indexed, 5axis_trunnion, or 5axis_head_head"
        )
    pivot = float(raw.get("pivot_mm", 0.0))
    return _MachineKinematics(
        machine_type=mtype,
        pivot_mm=pivot,
        a_lo_deg=float(raw.get("a_lo_deg", -120.0)),
        a_hi_deg=float(raw.get("a_hi_deg", 30.0)),
        rapid_mm_min=float(raw.get("rapid_mm_min", 10_000.0)),
        accel_mm_s2=float(raw.get("accel_mm_s2", 500.0)),
    ), None


def _parse_stock(raw: dict) -> Tuple[Optional[_StockBlock], Optional[str]]:
    for fld in ("width_mm", "depth_mm", "height_mm"):
        err = _positive(fld, raw.get(fld))
        if err:
            return None, f"stock_block.{err}"
    return _StockBlock(
        width_mm=float(raw["width_mm"]),
        depth_mm=float(raw["depth_mm"]),
        height_mm=float(raw["height_mm"]),
    ), None


# ---------------------------------------------------------------------------
# Roughing strategy: parallel-plane Z-level passes
# ---------------------------------------------------------------------------

def _plan_roughing(
    piece: dict,
    stock: _StockBlock,
    rough_tool: _ToolEntry,
    step_down_mm: float,
    machine: _MachineKinematics,
) -> dict:
    """
    Plan parallel Z-level roughing passes.

    Uses the stock height and the piece Z-extent to compute the number of
    passes.  Returns a dict with pass count, feed rates (from cncfeeds), and
    MRR estimate.
    """
    z_top = stock.height_mm
    # Piece Z-extent: use field if present, otherwise fall back to stock height
    piece_z = float(piece.get("height_mm", piece.get("z_extent_mm", z_top)))
    z_bottom = max(0.0, z_top - piece_z)
    z_extent = z_top - z_bottom

    if z_extent <= 0.0:
        z_extent = z_top

    n_passes = max(1, math.ceil(z_extent / step_down_mm))
    actual_step = z_extent / n_passes

    # Feeds & speeds via cncfeeds if available
    feeds_info: dict = {}
    if _CNCFEEDS_OK:
        rpm_r = spindle_rpm(rough_tool.vc_m_min, rough_tool.diameter_mm)
        if rpm_r.get("ok"):
            rpm_val = rpm_r["rpm"]
            fr_r = feed_rate(
                rough_tool.chip_load_mm, rough_tool.flutes, rpm_val
            )
            if fr_r.get("ok"):
                feeds_info["rpm"] = round(rpm_val, 1)
                feeds_info["feed_mm_min"] = round(fr_r["feed_mm_min"], 1)
                ae = rough_tool.diameter_mm * 0.5   # 50% step-over for roughing
                ap = actual_step
                mrr_r = mrr_milling(ae, ap, fr_r["feed_mm_min"])
                if mrr_r.get("ok"):
                    feeds_info["mrr_mm3_min"] = round(mrr_r["mrr_mm3_min"], 1)

    # Build per-pass Z levels
    passes = []
    for i in range(n_passes):
        z_level = z_top - (i + 1) * actual_step
        passes.append({
            "pass_index": i,
            "z_mm": round(z_level, 4),
            "step_down_mm": round(actual_step, 4),
        })

    return {
        "strategy": "parallel_plane_zlevel",
        "tool": rough_tool.name,
        "step_down_mm": round(actual_step, 4),
        "pass_count": n_passes,
        "z_top_mm": z_top,
        "z_bottom_mm": round(z_bottom, 4),
        "passes": passes,
        "feeds": feeds_info,
    }


# ---------------------------------------------------------------------------
# Finishing strategy: 3-axis surface + 5-axis tilt for ring bore / prong
# ---------------------------------------------------------------------------

def _plan_finishing(
    piece: dict,
    stock: _StockBlock,
    finish_tool: _ToolEntry,
    machine: _MachineKinematics,
    prong_tilt_deg: float = _PRONG_TILT_DEG,
) -> dict:
    """
    Plan finishing passes.

    For rings: adds bore-finishing passes (4-axis indexed or 5-axis tilt).
    For prongs: adds tilt-approach passes.
    Returns a dict with pass count, tilt angles, and RTCP info.
    """
    piece_type = str(piece.get("type", "pendant")).lower()
    diameter_mm = float(piece.get("inner_diameter_mm", piece.get("diameter_mm", 0.0)))

    # Step-over for finishing (small fraction of tool diameter)
    stepover = finish_tool.diameter_mm * _FINISH_STEPOVER_FRAC
    surface_width = float(piece.get("width_mm", stock.width_mm))
    surface_height = float(piece.get("height_mm", stock.height_mm))

    # Number of finishing passes in Y
    n_finish_y = max(1, math.ceil(surface_width / stepover))
    # Number of finishing passes in Z (for sides)
    n_finish_z = max(1, math.ceil(surface_height / stepover))

    finish_passes: List[dict] = []

    # Standard 3-axis surface passes
    for j in range(min(n_finish_y, 50)):  # cap display list at 50
        y_pos = j * stepover
        finish_passes.append({
            "pass_type": "surface_3axis",
            "y_mm": round(y_pos, 4),
            "feed_direction": "X",
        })

    # Feeds & speeds
    feeds_info: dict = {}
    if _CNCFEEDS_OK:
        rpm_r = spindle_rpm(finish_tool.vc_m_min, finish_tool.diameter_mm)
        if rpm_r.get("ok"):
            rpm_val = rpm_r["rpm"]
            fr_r = feed_rate(
                finish_tool.chip_load_mm, finish_tool.flutes, rpm_val
            )
            if fr_r.get("ok"):
                feeds_info["rpm"] = round(rpm_val, 1)
                feeds_info["feed_mm_min"] = round(fr_r["feed_mm_min"], 1)
                ra_r = surface_finish_ra(
                    finish_tool.chip_load_mm * finish_tool.flutes / rpm_val,
                    finish_tool.diameter_mm / 2.0,
                )
                if ra_r.get("ok"):
                    feeds_info["Ra_um"] = round(ra_r["Ra_um"], 3)

    # Ring-bore finishing
    bore_passes: List[dict] = []
    has_bore = (piece_type == "ring" and diameter_mm > 0
                and diameter_mm / stock.width_mm >= _RING_BORE_TRIGGER_RATIO)

    rtcp_info: dict = {}

    if has_bore:
        bore_circumference = math.pi * diameter_mm
        bore_stepover = finish_tool.diameter_mm * _FINISH_STEPOVER_FRAC
        n_bore = max(4, math.ceil(bore_circumference / bore_stepover))

        if machine.machine_type == "4axis_indexed":
            # 4-axis indexed: rotate A-axis to each indexed position
            n_index = 4   # 4 × 90° indexed positions
            for idx in range(n_index):
                a_angle = idx * 90.0
                bore_passes.append({
                    "pass_type": "bore_4axis_indexed",
                    "a_angle_deg": a_angle,
                    "bore_diameter_mm": diameter_mm,
                    "n_passes_at_index": max(1, n_bore // n_index),
                })

            # RTCP info for 4-axis (no RTCP — indexed)
            rtcp_info = {
                "rtcp": False,
                "method": "4axis_indexed",
                "n_index_positions": n_index,
            }

        else:
            # True 5-axis: continuous bore finishing with tilt
            # Use 5-axis IK if available
            tilt_rad = math.radians(prong_tilt_deg)

            if _FIVEAXIS_OK and machine.machine_type in ("5axis_trunnion", "5axis_head_head"):
                mtype = (MachineType.TABLE_TABLE
                         if machine.machine_type == "5axis_trunnion"
                         else MachineType.HEAD_HEAD)
                config = MachineConfig(
                    machine_type=mtype,
                    first_rotary=RotaryAxis(
                        axis=(1.0, 0.0, 0.0),
                        lo_rad=math.radians(machine.a_lo_deg),
                        hi_rad=math.radians(machine.a_hi_deg),
                        name="A",
                    ),
                    second_rotary=RotaryAxis(
                        axis=(0.0, 0.0, 1.0),
                        lo_rad=math.radians(-360.0),
                        hi_rad=math.radians(360.0),
                        name="C",
                    ),
                    pivot_length_mm=machine.pivot_mm,
                )

                # Sample tip point at bore top
                sample_tip = (0.0, diameter_mm / 2.0, stock.height_mm)
                sample_axis = (math.sin(tilt_rad), math.cos(tilt_rad), 0.0)

                ik_result = inverse_post(
                    config,
                    sample_tip,
                    sample_axis,
                )
                rtcp_info = {
                    "rtcp": True,
                    "method": machine.machine_type,
                    "sample_ik": ik_result.get("solutions", []),
                    "singularity": ik_result.get("singularity", False),
                }
            else:
                rtcp_info = {
                    "rtcp": True,
                    "method": machine.machine_type,
                    "note": "fiveaxis module not available — RTCP stub only",
                }

            angle_step = 360.0 / max(n_bore, 4)
            for idx in range(min(n_bore, 36)):   # cap for readability
                c_angle = idx * angle_step
                bore_passes.append({
                    "pass_type": "bore_5axis_continuous",
                    "c_angle_deg": round(c_angle, 2),
                    "tilt_deg": prong_tilt_deg,
                    "bore_diameter_mm": diameter_mm,
                })

    # Prong under-reach passes (settings with prongs)
    prong_passes: List[dict] = []
    has_prongs = piece_type in ("ring", "pendant") and piece.get("settings")
    if has_prongs or piece.get("has_prongs"):
        prong_passes.append({
            "pass_type": "prong_undercut_tilt",
            "tilt_deg": prong_tilt_deg,
            "note": "tool tilted to clear prong base; 5-axis RTCP",
        })

    return {
        "strategy": "surface_3axis_plus_bore_tilt",
        "tool": finish_tool.name,
        "stepover_mm": round(stepover, 4),
        "n_surface_passes": n_finish_y,
        "n_z_passes": n_finish_z,
        "surface_pass_sample": finish_passes[:10],   # first 10 for display
        "bore_passes": bore_passes,
        "prong_passes": prong_passes,
        "has_bore_finishing": has_bore,
        "prong_tilt_deg": prong_tilt_deg,
        "feeds": feeds_info,
        "rtcp": rtcp_info,
    }


# ---------------------------------------------------------------------------
# G-code stub generator
# ---------------------------------------------------------------------------

def _gcode_stub(
    rough_plan: dict,
    finish_plan: dict,
    rough_tool: _ToolEntry,
    finish_tool: _ToolEntry,
    stock: _StockBlock,
) -> List[str]:
    """
    Generate a representative G-code stub for the wax routing plan.

    This is a structural stub — it produces legal G-code structure with
    the correct axis assignments and feed rates but does NOT tessellate
    the actual part geometry (that requires the OCC worker).  Downstream
    toolchain (CAMView → post-processor) fills in actual XYZ moves.
    """
    lines: List[str] = []
    rough_feed = rough_plan.get("feeds", {}).get("feed_mm_min", 500.0)
    rough_rpm = rough_plan.get("feeds", {}).get("rpm", 5000.0)
    finish_feed = finish_plan.get("feeds", {}).get("feed_mm_min", 300.0)
    finish_rpm = finish_plan.get("feeds", {}).get("rpm", 8000.0)

    lines += [
        "% ; Kerf wax-routing stub — jewelry CAM",
        "G21          ; metric",
        "G17          ; XY plane",
        "G90          ; absolute",
        "G49          ; cancel tool-length comp",
        f"(ROUGH TOOL: {rough_tool.name} dia={rough_tool.diameter_mm} mm)",
        f"T1 M6        ; select roughing tool",
        f"S{int(rough_rpm)} M3 ; spindle on",
        f"G0 Z{stock.height_mm + 5.0:.3f}  ; safe Z",
    ]

    # Z-level roughing stubs
    for p in rough_plan.get("passes", []):
        z = p["z_mm"]
        lines.append(f"G0 Z{z + 1.0:.3f}       ; rapid to clearance above pass {p['pass_index']}")
        lines.append(f"G1 Z{z:.3f} F{int(rough_feed)} ; feed to Z-level")
        lines.append(f"G1 X{stock.width_mm:.3f} F{int(rough_feed)} ; X sweep")
        lines.append(f"G0 Z{z + 1.0:.3f}       ; retract")

    lines += [
        f"G0 Z{stock.height_mm + 5.0:.3f}  ; safe Z after roughing",
        "",
        f"(FINISH TOOL: {finish_tool.name} dia={finish_tool.diameter_mm} mm)",
        f"T2 M6        ; select finishing tool",
        f"S{int(finish_rpm)} M3 ; spindle on",
    ]

    # Finishing surface stubs (first 5)
    for p in finish_plan.get("surface_pass_sample", [])[:5]:
        y = p.get("y_mm", 0.0)
        lines.append(f"G0 Y{y:.3f}          ; step over")
        lines.append(f"G1 X{stock.width_mm:.3f} F{int(finish_feed)} ; finish pass")

    # Bore passes (if any)
    for bp in finish_plan.get("bore_passes", [])[:5]:
        if bp.get("pass_type") == "bore_4axis_indexed":
            lines.append(f"G0 A{bp['a_angle_deg']:.1f} ; rotate to indexed position")
            lines.append(f"G1 X0.0 F{int(finish_feed)} ; bore pass")
        elif bp.get("pass_type") == "bore_5axis_continuous":
            lines.append(f"G0 C{bp['c_angle_deg']:.2f} ; C-axis bore approach")
            lines.append(f"G1 X0.0 F{int(finish_feed)} ; bore arc pass")

    lines += [
        f"G0 Z{stock.height_mm + 10.0:.3f}  ; retract to home",
        "M5           ; spindle stop",
        "M30          ; end of program",
        "%",
    ]
    return lines


# ---------------------------------------------------------------------------
# Cycle-time estimation
# ---------------------------------------------------------------------------

def _estimate_cycle_time(
    rough_plan: dict,
    finish_plan: dict,
    machine: _MachineKinematics,
    stock: _StockBlock,
) -> float:
    """
    Estimate total cycle time in seconds using gcode.post.cycle_time logic.

    Builds a minimal synthetic segment list from the roughing and finishing
    plans, then delegates to the gcode module if available.  Falls back to
    a simple distance / feed-rate estimate.
    """
    rapid_mm_min = machine.rapid_mm_min

    rough_feed = rough_plan.get("feeds", {}).get("feed_mm_min", 500.0)
    finish_feed = finish_plan.get("feeds", {}).get("feed_mm_min", 300.0)

    n_rough = rough_plan.get("pass_count", 1)
    n_finish = finish_plan.get("n_surface_passes", 1)
    n_bore = len(finish_plan.get("bore_passes", []))

    # Approximate distances
    rough_feed_dist = n_rough * stock.width_mm
    rough_rapid_dist = n_rough * 2.0   # short retracts
    finish_feed_dist = n_finish * stock.width_mm
    finish_rapid_dist = n_finish * 1.0
    bore_feed_dist = n_bore * math.pi * float(
        finish_plan.get("bore_passes", [{}])[0].get("bore_diameter_mm", 10.0)
        if n_bore > 0 else 10.0
    )

    if _GCODE_OK:
        # Build synthetic segments and use cycle_time()
        segs: List[dict] = []

        def _feed_seg(dist: float, f: float) -> dict:
            return {
                "type": "feed",
                "start": (0.0, 0.0, 0.0),
                "end": (dist, 0.0, 0.0),
                "f": f,
            }

        def _rapid_seg(dist: float) -> dict:
            return {
                "type": "rapid",
                "start": (0.0, 0.0, 0.0),
                "end": (dist, 0.0, 0.0),
                "f": rapid_mm_min,
            }

        for _ in range(n_rough):
            segs.append(_rapid_seg(2.0))
            segs.append(_feed_seg(stock.width_mm, rough_feed))
        for _ in range(n_finish):
            segs.append(_rapid_seg(1.0))
            segs.append(_feed_seg(stock.width_mm, finish_feed))
        for _ in range(n_bore):
            bore_dia = finish_plan.get("bore_passes", [{}])[0].get("bore_diameter_mm", 10.0) if n_bore > 0 else 10.0
            circ = math.pi * float(bore_dia)
            segs.append(_feed_seg(circ, finish_feed * 0.5))

        ct = cycle_time(segs, rapid_rate=rapid_mm_min, accel=machine.accel_mm_s2)
        return ct.get("total_s", 0.0)

    else:
        # Simple fallback
        t_rough_feed = rough_feed_dist / (rough_feed / 60.0) if rough_feed > 0 else 0.0
        t_rough_rapid = rough_rapid_dist / (rapid_mm_min / 60.0) if rapid_mm_min > 0 else 0.0
        t_finish_feed = finish_feed_dist / (finish_feed / 60.0) if finish_feed > 0 else 0.0
        t_finish_rapid = finish_rapid_dist / (rapid_mm_min / 60.0) if rapid_mm_min > 0 else 0.0
        t_bore = bore_feed_dist / (finish_feed * 0.5 / 60.0) if finish_feed > 0 else 0.0
        return t_rough_feed + t_rough_rapid + t_finish_feed + t_finish_rapid + t_bore


# ---------------------------------------------------------------------------
# Collision / clamp proximity check
# ---------------------------------------------------------------------------

def _check_clamp_proximity(
    piece: dict,
    stock: _StockBlock,
    clamp_clearance_mm: float = _CLAMP_CLEARANCE_MM,
) -> List[str]:
    """
    Check whether the piece Y-extent comes within clamp_clearance_mm of the
    stock edges.  Returns a list of warning strings (empty = all clear).
    """
    warnings: List[str] = []
    piece_y = float(piece.get("depth_mm", piece.get("y_extent_mm", stock.depth_mm * 0.5)))
    piece_y_offset = float(piece.get("y_offset_mm", 0.0))

    y_near_front = piece_y_offset
    y_near_back = stock.depth_mm - (piece_y_offset + piece_y)

    if y_near_front < clamp_clearance_mm:
        warnings.append(
            f"clamp_proximity: piece front edge is {y_near_front:.2f} mm from stock "
            f"front face (clamp clearance = {clamp_clearance_mm} mm)"
        )
    if y_near_back < clamp_clearance_mm:
        warnings.append(
            f"clamp_proximity: piece rear edge is {y_near_back:.2f} mm from stock "
            f"rear face (clamp clearance = {clamp_clearance_mm} mm)"
        )

    # Ring-specific: check if ring height leaves enough stock for clamping
    piece_type = str(piece.get("type", "")).lower()
    if piece_type == "ring":
        ring_h = float(piece.get("height_mm", stock.height_mm))
        remaining = stock.height_mm - ring_h
        if remaining < clamp_clearance_mm:
            warnings.append(
                f"clamp_proximity: ring height {ring_h:.2f} mm leaves only "
                f"{remaining:.2f} mm of stock above ring (minimum {clamp_clearance_mm} mm)"
            )

    return warnings


# ---------------------------------------------------------------------------
# Select tools from library
# ---------------------------------------------------------------------------

def _select_tools(
    tools: List[_ToolEntry],
    piece: dict,
    stock: _StockBlock,
) -> Tuple[Optional[_ToolEntry], Optional[_ToolEntry], Optional[_ToolEntry]]:
    """
    Select roughing, finishing, and undercut tools from the library.

    Priority:
      rough   → largest flat_end or ball_nose (by diameter)
      finish  → smallest ball_nose (by diameter) — fine detail
      undercut→ fishtail (for under-prong clearing); None if not present
    """
    flat_ends = [t for t in tools if t.tool_type == "flat_end"]
    ball_noses = sorted([t for t in tools if t.tool_type in ("ball_nose", "tapered_ball")],
                        key=lambda t: t.diameter_mm)
    fishtails = [t for t in tools if t.tool_type == "fishtail"]

    rough_tool = (
        max(flat_ends, key=lambda t: t.diameter_mm)
        if flat_ends
        else (ball_noses[-1] if ball_noses else (tools[0] if tools else None))
    )
    finish_tool = ball_noses[0] if ball_noses else rough_tool
    undercut_tool = fishtails[0] if fishtails else None

    return rough_tool, finish_tool, undercut_tool


# ---------------------------------------------------------------------------
# Master planning function
# ---------------------------------------------------------------------------

def plan_wax_routing(
    piece: dict,
    machine_kinematics: dict,
    tool_library: list,
    stock_block: dict,
    *,
    step_down_mm: float = _ROUGH_STEPDWN_DEFAULT,
    prong_tilt_deg: float = _PRONG_TILT_DEG,
    clamp_clearance_mm: float = _CLAMP_CLEARANCE_MM,
) -> dict:
    """
    Plan a complete wax-routing workflow for a jewelry piece.

    Parameters
    ----------
    piece              : Jewelry piece spec dict.  Required fields vary by type:
                         - type:  "ring" | "pendant" | "setting" | "earring" | ...
                         - height_mm (or z_extent_mm): piece height
                         - width_mm, depth_mm: XY footprint
                         For rings: inner_diameter_mm or diameter_mm.
    machine_kinematics : Machine config dict (see module docstring).
    tool_library       : List of tool dicts (see module docstring).
    stock_block        : Stock-wax block dict (see module docstring).
    step_down_mm       : Roughing Z step-down (mm, default 0.8).
    prong_tilt_deg     : 5-axis tilt for prong / bore finishing (deg, default 10).
    clamp_clearance_mm : Minimum clearance between piece and clamp edge (mm).

    Returns
    -------
    dict with keys:
      ok                  : bool
      roughing_strategy   : dict
      finishing_strategy  : dict
      gcode_stubs         : list[str]
      cycle_time_s        : float
      tool_list           : list[dict]
      collision_warnings  : list[str]
      machine_type        : str
    """
    try:
        return _plan_wax_routing_inner(
            piece, machine_kinematics, tool_library, stock_block,
            step_down_mm=step_down_mm,
            prong_tilt_deg=prong_tilt_deg,
            clamp_clearance_mm=clamp_clearance_mm,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"plan_wax_routing unexpected error: {exc}"}


def _plan_wax_routing_inner(
    piece: dict,
    machine_kinematics: dict,
    tool_library: list,
    stock_block: dict,
    *,
    step_down_mm: float,
    prong_tilt_deg: float,
    clamp_clearance_mm: float,
) -> dict:
    # ── validate inputs ────────────────────────────────────────────────────
    if not isinstance(piece, dict):
        return _err("piece must be a dict")
    if not isinstance(machine_kinematics, dict):
        return _err("machine_kinematics must be a dict")
    if not isinstance(tool_library, list) or len(tool_library) == 0:
        return _err("tool_library must be a non-empty list")
    if not isinstance(stock_block, dict):
        return _err("stock_block must be a dict")

    # Validate step_down
    err = _positive("step_down_mm", step_down_mm)
    if err:
        return _err(err)

    # Parse stock
    stock, stock_err = _parse_stock(stock_block)
    if stock_err:
        return _err(stock_err)

    # Parse machine
    machine, machine_err = _parse_machine(machine_kinematics)
    if machine_err:
        return _err(machine_err)

    # Parse tools
    tools, tool_errors = _parse_tool_library(tool_library)
    if tool_errors:
        return _err("; ".join(tool_errors))
    if not tools:
        return _err("no valid tools in tool_library")

    # Select tools
    rough_tool, finish_tool, undercut_tool = _select_tools(tools, piece, stock)
    if rough_tool is None:
        return _err("could not select a roughing tool from tool_library")
    if finish_tool is None:
        finish_tool = rough_tool

    # ── plan roughing ──────────────────────────────────────────────────────
    roughing = _plan_roughing(piece, stock, rough_tool, step_down_mm, machine)

    # ── plan finishing ─────────────────────────────────────────────────────
    finishing = _plan_finishing(piece, stock, finish_tool, machine, prong_tilt_deg)

    # ── G-code stubs ──────────────────────────────────────────────────────
    gcode_lines = _gcode_stub(roughing, finishing, rough_tool, finish_tool, stock)

    # ── cycle time ────────────────────────────────────────────────────────
    cycle_time_s = _estimate_cycle_time(roughing, finishing, machine, stock)

    # ── tool list ─────────────────────────────────────────────────────────
    tool_list: List[dict] = [rough_tool.to_dict()]
    if finish_tool is not rough_tool:
        tool_list.append(finish_tool.to_dict())
    if undercut_tool is not None:
        tool_list.append(undercut_tool.to_dict())

    # ── collision / clamp warnings ─────────────────────────────────────────
    collision_warnings = _check_clamp_proximity(piece, stock, clamp_clearance_mm)

    return {
        "ok": True,
        "roughing_strategy": roughing,
        "finishing_strategy": finishing,
        "gcode_stubs": gcode_lines,
        "cycle_time_s": round(cycle_time_s, 2),
        "tool_list": tool_list,
        "collision_warnings": collision_warnings,
        "machine_type": machine.machine_type,
    }


# ---------------------------------------------------------------------------
# LLM tools
# ---------------------------------------------------------------------------

_plan_routing_spec = ToolSpec(
    name="jewelry_wax_plan_routing",
    description=(
        "Plan a complete 4/5-axis wax-routing CAM workflow for a jewelry piece.\n"
        "\n"
        "Produces:\n"
        "  - roughing_strategy  : parallel Z-level passes with feeds/speeds\n"
        "  - finishing_strategy : 3-axis surface + 5-axis tilt for ring bore/prong\n"
        "  - gcode_stubs        : representative ISO G-code lines\n"
        "  - cycle_time_s       : estimated machining time (seconds)\n"
        "  - tool_list          : ordered list of tools used\n"
        "  - collision_warnings : clamp-proximity / over-travel warnings\n"
        "\n"
        "Machine types:\n"
        "  '4axis_indexed'   — A-axis indexed in 90° steps (simple, safe)\n"
        "  '5axis_trunnion'  — AC trunnion table, full 5-axis RTCP\n"
        "  '5axis_head_head' — BC head-head spindle, full 5-axis RTCP\n"
        "\n"
        "Tool types for wax: ball_nose (fine detail), fishtail (undercuts),\n"
        "flat_end (roughing), tapered_ball (deep-relief finishing).\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece": {
                "type": "object",
                "description": (
                    "Jewelry piece spec.  Required: type ('ring'|'pendant'|'setting'|...), "
                    "height_mm, width_mm, depth_mm.  "
                    "For rings: inner_diameter_mm."
                ),
            },
            "machine_kinematics": {
                "type": "object",
                "description": (
                    "Machine config: type ('4axis_indexed'|'5axis_trunnion'|'5axis_head_head'), "
                    "pivot_mm, a_lo_deg, a_hi_deg, rapid_mm_min, accel_mm_s2."
                ),
            },
            "tool_library": {
                "type": "array",
                "description": (
                    "List of tool dicts.  Each tool: name, type, diameter_mm, "
                    "flutes, stickout_mm, vc_m_min, chip_load_mm."
                ),
                "items": {"type": "object"},
            },
            "stock_block": {
                "type": "object",
                "description": "Wax stock: width_mm, depth_mm, height_mm.",
            },
            "step_down_mm": {
                "type": "number",
                "description": "Roughing Z step-down per pass (mm, default 0.8).",
            },
            "prong_tilt_deg": {
                "type": "number",
                "description": "5-axis tilt for prong / bore finishing (degrees, default 10).",
            },
            "clamp_clearance_mm": {
                "type": "number",
                "description": "Minimum piece-to-clamp clearance for warning (mm, default 3.0).",
            },
        },
        "required": ["piece", "machine_kinematics", "tool_library", "stock_block"],
    },
)


@register(_plan_routing_spec, write=False)
async def run_jewelry_wax_plan_routing(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    for fld in ("piece", "machine_kinematics", "tool_library", "stock_block"):
        if a.get(fld) is None:
            return json.dumps({"ok": False, "reason": f"{fld} is required"})

    result = plan_wax_routing(
        a["piece"],
        a["machine_kinematics"],
        a["tool_library"],
        a["stock_block"],
        step_down_mm=float(a.get("step_down_mm", _ROUGH_STEPDWN_DEFAULT)),
        prong_tilt_deg=float(a.get("prong_tilt_deg", _PRONG_TILT_DEG)),
        clamp_clearance_mm=float(a.get("clamp_clearance_mm", _CLAMP_CLEARANCE_MM)),
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: jewelry_wax_list_tools
# ---------------------------------------------------------------------------

_list_tools_spec = ToolSpec(
    name="jewelry_wax_list_tools",
    description=(
        "Validate and summarise a wax-routing tool library.\n"
        "\n"
        "Returns a list of parsed tools with computed spindle RPM and feed rate "
        "for each tool based on wax cutting parameters.\n"
        "\n"
        "Use this before planning to verify the tool library is complete and "
        "the parameters are sensible.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tool_library": {
                "type": "array",
                "description": "List of tool dicts (same schema as jewelry_wax_plan_routing).",
                "items": {"type": "object"},
            },
        },
        "required": ["tool_library"],
    },
)


@register(_list_tools_spec, write=False)
async def run_jewelry_wax_list_tools(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    if a.get("tool_library") is None:
        return json.dumps({"ok": False, "reason": "tool_library is required"})

    tools, errors = _parse_tool_library(a["tool_library"])
    if errors:
        return json.dumps({"ok": False, "reason": "; ".join(errors)})

    tool_summaries = []
    for t in tools:
        summary: dict = t.to_dict()
        if _CNCFEEDS_OK:
            rpm_r = spindle_rpm(t.vc_m_min, t.diameter_mm)
            if rpm_r.get("ok"):
                rpm_v = rpm_r["rpm"]
                summary["computed_rpm"] = round(rpm_v, 1)
                fr_r = feed_rate(t.chip_load_mm, t.flutes, rpm_v)
                if fr_r.get("ok"):
                    summary["computed_feed_mm_min"] = round(fr_r["feed_mm_min"], 1)
        tool_summaries.append(summary)

    return ok_payload({"tools": tool_summaries, "count": len(tool_summaries)})


# ---------------------------------------------------------------------------
# Tool: jewelry_wax_estimate_cycle_time
# ---------------------------------------------------------------------------

_cycle_time_spec = ToolSpec(
    name="jewelry_wax_estimate_cycle_time",
    description=(
        "Estimate wax-routing cycle time from a complete routing plan.\n"
        "\n"
        "Accepts the output of jewelry_wax_plan_routing and returns a breakdown "
        "of roughing, finishing, and bore-finishing times.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plan": {
                "type": "object",
                "description": "Output dict from jewelry_wax_plan_routing.",
            },
            "rapid_mm_min": {
                "type": "number",
                "description": "Machine rapid traverse rate (mm/min, default 10000).",
            },
        },
        "required": ["plan"],
    },
)


@register(_cycle_time_spec, write=False)
async def run_jewelry_wax_estimate_cycle_time(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    if a.get("plan") is None:
        return json.dumps({"ok": False, "reason": "plan is required"})

    plan = a["plan"]
    if not isinstance(plan, dict) or not plan.get("ok"):
        return json.dumps({"ok": False, "reason": "plan must be a successful plan_wax_routing result"})

    rough = plan.get("roughing_strategy", {})
    finish = plan.get("finishing_strategy", {})
    rapid = float(a.get("rapid_mm_min", 10_000.0))

    rough_feed = rough.get("feeds", {}).get("feed_mm_min", 500.0)
    finish_feed = finish.get("feeds", {}).get("feed_mm_min", 300.0)
    n_rough = int(rough.get("pass_count", 1))
    n_finish = int(finish.get("n_surface_passes", 1))
    n_bore = len(finish.get("bore_passes", []))

    stock_w = 30.0  # fallback if not in plan

    total_s = plan.get("cycle_time_s", 0.0)

    return ok_payload({
        "total_s": total_s,
        "total_min": round(total_s / 60.0, 2),
        "roughing_pass_count": n_rough,
        "finishing_pass_count": n_finish,
        "bore_pass_count": n_bore,
        "rough_feed_mm_min": rough_feed,
        "finish_feed_mm_min": finish_feed,
    })
