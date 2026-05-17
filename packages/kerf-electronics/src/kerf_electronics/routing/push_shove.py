"""
Push-and-shove diff-pair router for Kerf PCB.

Pure-Python implementation; no external dependencies beyond the stdlib.

Public API
----------
push_shove_segment(existing_segments, new_segment, board, design_rules) -> result
    Push neighbouring tracks aside to make room for new_segment while
    respecting clearance from design_rules.

route_diff_pair(net_pos, net_neg, start, end, spacing, board) -> (segs_pos, segs_neg, vias)
    Auto-route a coupled differential pair maintaining spacing ± tolerance.

tune_diff_pair_skew(diff_pair_segs, target_length_diff_mm) -> tuned_segs
    Adjust path lengths so len(pos) - len(neg) matches target_skew (typically 0).

validate_diff_pair(segs_pos, segs_neg, design_rules) -> {ok, violations[]}
    Check spacing, coupled-pair length match, max via count.

LLM tool wrappers (registered via @register from _compat.py):
    push_shove_segment_tool
    route_diff_pair_tool
    tune_diff_pair_skew_tool
    validate_diff_pair_tool
"""

from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from kerf_electronics._compat import ToolSpec, err_payload, ok_payload, register


# ── Geometry primitives ────────────────────────────────────────────────────────

def _dist(a: Dict, b: Dict) -> float:
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def _polyline_length(points: List[Dict]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _seg_unit(a: Dict, b: Dict) -> Tuple[float, float]:
    d = _dist(a, b)
    if d < 1e-12:
        return (1.0, 0.0)
    return ((b["x"] - a["x"]) / d, (b["y"] - a["y"]) / d)


def _perp(ux: float, uy: float) -> Tuple[float, float]:
    """CCW 90-degree perpendicular of a unit vector."""
    return (-uy, ux)


def _pt(x: float, y: float) -> Dict:
    return {"x": x, "y": y}


def _offset_pt(p: Dict, nx: float, ny: float, dist: float) -> Dict:
    return {"x": p["x"] + nx * dist, "y": p["y"] + ny * dist}


# Segment-to-segment minimum distance (2-D, endpoints included).

def _pt_to_seg_dist(p: Dict, a: Dict, b: Dict) -> float:
    dx = b["x"] - a["x"]
    dy = b["y"] - a["y"]
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-24:
        return _dist(p, a)
    t = ((p["x"] - a["x"]) * dx + (p["y"] - a["y"]) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    return _dist(p, {"x": a["x"] + t * dx, "y": a["y"] + t * dy})


def _seg_seg_min_dist(a1: Dict, a2: Dict, b1: Dict, b2: Dict) -> float:
    """Minimum distance between two line segments."""
    dx1 = a2["x"] - a1["x"]
    dy1 = a2["y"] - a1["y"]
    dx2 = b2["x"] - b1["x"]
    dy2 = b2["y"] - b1["y"]
    cx = b1["x"] - a1["x"]
    cy = b1["y"] - a1["y"]
    len1_sq = dx1 * dx1 + dy1 * dy1
    len2_sq = dx2 * dx2 + dy2 * dy2

    if len1_sq < 1e-24 and len2_sq < 1e-24:
        return _dist(a1, b1)
    if len1_sq < 1e-24:
        return _pt_to_seg_dist(a1, b1, b2)
    if len2_sq < 1e-24:
        return _pt_to_seg_dist(b1, a1, a2)

    det = dx1 * dy2 - dy1 * dx2
    if abs(det) > 1e-12:
        t = (cx * dy2 - cy * dx2) / det
        u = (cx * dy1 - cy * dx1) / det
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return 0.0  # segments intersect

    return min(
        _pt_to_seg_dist(a1, b1, b2),
        _pt_to_seg_dist(a2, b1, b2),
        _pt_to_seg_dist(b1, a1, a2),
        _pt_to_seg_dist(b2, a1, a2),
    )


def _segment_pair_distance(seg_a: Dict, seg_b: Dict) -> float:
    """Minimum distance between two segments stored as {start, end} dicts."""
    return _seg_seg_min_dist(seg_a["start"], seg_a["end"], seg_b["start"], seg_b["end"])


# ── Segment data-model helpers ─────────────────────────────────────────────────

def _make_segment(
    start: Dict,
    end: Dict,
    net_id: str = "",
    layer: str = "top_copper",
    width_mm: float = 0.2,
    seg_id: Optional[str] = None,
) -> Dict:
    return {
        "id": seg_id or f"seg_{uuid.uuid4().hex[:8]}",
        "net_id": net_id,
        "layer": layer,
        "width_mm": width_mm,
        "start": {"x": start["x"], "y": start["y"]},
        "end": {"x": end["x"], "y": end["y"]},
    }


def _seg_length(seg: Dict) -> float:
    return _dist(seg["start"], seg["end"])


def _segs_total_length(segs: List[Dict]) -> float:
    return sum(_seg_length(s) for s in segs)


def _polyline_to_segments(
    points: List[Dict],
    net_id: str = "",
    layer: str = "top_copper",
    width_mm: float = 0.2,
) -> List[Dict]:
    segs = []
    for i in range(len(points) - 1):
        segs.append(_make_segment(points[i], points[i + 1], net_id, layer, width_mm))
    return segs


def _segments_to_points(segs: List[Dict]) -> List[Dict]:
    if not segs:
        return []
    pts = [{"x": segs[0]["start"]["x"], "y": segs[0]["start"]["y"]}]
    for s in segs:
        pts.append({"x": s["end"]["x"], "y": s["end"]["y"]})
    return pts


# ── push_shove_segment ─────────────────────────────────────────────────────────

_MAX_SHOVE_PASSES = 4


def push_shove_segment(
    existing_segments: List[Dict],
    new_segment: Dict,
    board: Dict,
    design_rules: Dict,
) -> Dict:
    """Push neighbouring tracks aside to make room for new_segment.

    Parameters
    ----------
    existing_segments:
        List of segment dicts ({id, net_id, layer, width_mm, start, end}).
    new_segment:
        The segment being inserted (same schema).
    board:
        PCB board dict (used for layer / boundary checks; not modified here).
    design_rules:
        Dict containing at minimum ``clearance_mm``.  Also honours
        ``min_trace_spacing_mm`` as a fallback.

    Returns
    -------
    {
        "shoved_segments": [...],     # updated copies of moved segments
        "conflicts_resolved": int,
        "conflicts_unresolved": int,
        "new_segment": {...},         # unchanged new segment
    }
    """
    clearance = float(
        design_rules.get("clearance_mm")
        or design_rules.get("min_trace_spacing_mm")
        or 0.2
    )
    layer = new_segment.get("layer", "top_copper")
    new_width = float(new_segment.get("width_mm", 0.2))

    # Work on copies so the caller's list is not mutated.
    working: List[Dict] = [deepcopy(s) for s in existing_segments]
    shoved_ids: List[str] = []
    unresolved = 0

    for _pass in range(_MAX_SHOVE_PASSES):
        changed_this_pass = False
        for i, seg in enumerate(working):
            if seg.get("layer", "top_copper") != layer:
                continue
            if seg.get("net_id") == new_segment.get("net_id"):
                continue  # same net — no clearance violation

            required_gap = clearance + new_width / 2.0 + float(seg.get("width_mm", 0.2)) / 2.0
            current_dist = _segment_pair_distance(new_segment, seg)

            if current_dist >= required_gap - 1e-9:
                continue  # already clear

            penetration = required_gap - current_dist
            # Shove direction: perpendicular to new_segment, away from it.
            ux, uy = _seg_unit(new_segment["start"], new_segment["end"])
            px, py = _perp(ux, uy)

            # Determine which side of new_segment seg centre is on.
            cx = (seg["start"]["x"] + seg["end"]["x"]) / 2
            cy = (seg["start"]["y"] + seg["end"]["y"]) / 2
            mx = (new_segment["start"]["x"] + new_segment["end"]["x"]) / 2
            my = (new_segment["start"]["y"] + new_segment["end"]["y"]) / 2
            dot = (cx - mx) * px + (cy - my) * py
            sign = 1.0 if dot >= 0 else -1.0

            shove_x = px * sign * penetration
            shove_y = py * sign * penetration

            new_start = {
                "x": seg["start"]["x"] + shove_x,
                "y": seg["start"]["y"] + shove_y,
            }
            new_end = {
                "x": seg["end"]["x"] + shove_x,
                "y": seg["end"]["y"] + shove_y,
            }
            working[i] = dict(seg)
            working[i]["start"] = new_start
            working[i]["end"] = new_end
            if seg["id"] not in shoved_ids:
                shoved_ids.append(seg["id"])
            changed_this_pass = True

        if not changed_this_pass:
            break
    else:
        # If we exit via exhaustion of passes, count remaining violations.
        for seg in working:
            if seg.get("layer", "top_copper") != layer:
                continue
            if seg.get("net_id") == new_segment.get("net_id"):
                continue
            required_gap = clearance + new_width / 2.0 + float(seg.get("width_mm", 0.2)) / 2.0
            if _segment_pair_distance(new_segment, seg) < required_gap - 1e-9:
                unresolved += 1

    return {
        "shoved_segments": working,
        "conflicts_resolved": len(shoved_ids),
        "conflicts_unresolved": unresolved,
        "new_segment": new_segment,
    }


# ── route_diff_pair ────────────────────────────────────────────────────────────

# Tolerance for length matching: ± this many mm.
_LENGTH_MATCH_TOL = 0.05


def route_diff_pair(
    net_pos: str,
    net_neg: str,
    start: Dict,
    end: Dict,
    spacing: float,
    board: Dict,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Auto-route a coupled differential pair from *start* to *end*.

    The positive trace is offset +spacing/2 perpendicular (CCW) and the
    negative trace −spacing/2.  A straight L-route is used (horizontal leg
    then vertical leg) when start and end are not collinear, so the geometry
    is always deterministic for the same input.

    Parameters
    ----------
    net_pos, net_neg:
        Net identifiers for the P and N conductors.
    start, end:
        {x, y} dicts for the route centreline endpoints.
    spacing:
        Edge-to-edge coupling gap in mm.
    board:
        PCB board dict (used for layer default).

    Returns
    -------
    (segs_pos, segs_neg, vias)
        segs_pos / segs_neg — lists of segment dicts for each conductor.
        vias — empty list (single-layer route; no vias required).
    """
    spacing = float(spacing)
    layer = board.get("default_layer") or board.get("layer") or "top_copper"
    width_mm = board.get("default_width_mm") or 0.2
    half = spacing / 2.0

    # Build a two-leg centreline: horizontal then vertical (or straight if already aligned).
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]

    if abs(dx) < 1e-9 or abs(dy) < 1e-9:
        # Already axis-aligned — single straight segment.
        centreline = [start, end]
    else:
        # L-route: go horizontal first, then vertical.
        corner = {"x": end["x"], "y": start["y"]}
        centreline = [start, corner, end]

    def _offset_polyline_pts(pts: List[Dict], offset: float) -> List[Dict]:
        n = len(pts)
        if n < 2:
            return list(pts)
        # Per-segment perpendiculars
        segs_perp = []
        for i in range(n - 1):
            ux, uy = _seg_unit(pts[i], pts[i + 1])
            px, py = _perp(ux, uy)
            segs_perp.append((px, py))
        result = []
        for i, pt in enumerate(pts):
            if i == 0:
                px, py = segs_perp[0]
            elif i == n - 1:
                px, py = segs_perp[-1]
            else:
                px = (segs_perp[i - 1][0] + segs_perp[i][0]) / 2
                py = (segs_perp[i - 1][1] + segs_perp[i][1]) / 2
                mag = math.hypot(px, py)
                if mag > 1e-12:
                    px /= mag
                    py /= mag
            result.append({"x": pt["x"] + px * offset, "y": pt["y"] + py * offset})
        return result

    pts_pos = _offset_polyline_pts(centreline, +half)
    pts_neg = _offset_polyline_pts(centreline, -half)

    segs_pos = _polyline_to_segments(pts_pos, net_pos, layer, width_mm)
    segs_neg = _polyline_to_segments(pts_neg, net_neg, layer, width_mm)
    vias: List[Dict] = []

    return segs_pos, segs_neg, vias


# ── tune_diff_pair_skew ────────────────────────────────────────────────────────

def tune_diff_pair_skew(
    diff_pair_segs: Dict,
    target_length_diff_mm: float = 0.0,
) -> Dict:
    """Adjust path lengths so len(pos) - len(neg) ≈ target_length_diff_mm.

    The shorter side gets a meander inserted on its longest segment to make
    up the delta.  Meander style: square-wave (2×amplitude per tooth) with
    amplitude chosen to fit within a 0.5 mm half-amplitude.

    Parameters
    ----------
    diff_pair_segs:
        {"segs_pos": [...], "segs_neg": [...]}
    target_length_diff_mm:
        Desired (len_pos − len_neg).  Typically 0 for skew-free routing.

    Returns
    -------
    {"segs_pos": [...], "segs_neg": [...], "length_pos_mm": float,
     "length_neg_mm": float, "delta_mm": float}
    """
    segs_pos: List[Dict] = deepcopy(diff_pair_segs.get("segs_pos") or [])
    segs_neg: List[Dict] = deepcopy(diff_pair_segs.get("segs_neg") or [])

    len_pos = _segs_total_length(segs_pos)
    len_neg = _segs_total_length(segs_neg)

    # Current difference; target = target_length_diff_mm
    current_diff = len_pos - len_neg
    correction = target_length_diff_mm - current_diff
    # correction > 0 → need to lengthen pos (or shorten neg — we lengthen shorter)
    # correction < 0 → need to lengthen neg

    if abs(correction) < 1e-6:
        return {
            "segs_pos": segs_pos,
            "segs_neg": segs_neg,
            "length_pos_mm": len_pos,
            "length_neg_mm": len_neg,
            "delta_mm": abs(current_diff - target_length_diff_mm),
        }

    if correction > 0:
        # Lengthen pos by abs(correction)
        segs_pos = _insert_meander(segs_pos, correction)
    else:
        # Lengthen neg by abs(correction)
        segs_neg = _insert_meander(segs_neg, abs(correction))

    new_len_pos = _segs_total_length(segs_pos)
    new_len_neg = _segs_total_length(segs_neg)

    return {
        "segs_pos": segs_pos,
        "segs_neg": segs_neg,
        "length_pos_mm": new_len_pos,
        "length_neg_mm": new_len_neg,
        "delta_mm": abs((new_len_pos - new_len_neg) - target_length_diff_mm),
    }


def _insert_meander(segs: List[Dict], extra_length: float) -> List[Dict]:
    """Insert a serpentine meander on the longest segment to add *extra_length* mm."""
    if not segs or extra_length < 1e-9:
        return segs

    # Find longest segment index.
    longest_i = max(range(len(segs)), key=lambda i: _seg_length(segs[i]))
    seg = segs[longest_i]
    start = seg["start"]
    end = seg["end"]
    seg_len = _seg_length(seg)

    ux, uy = _seg_unit(start, end)
    px, py = _perp(ux, uy)

    amplitude = 0.5  # mm — half-width of meander tooth
    # extra per tooth ≈ 2 * amplitude (each tooth adds two side legs of length ≈ amplitude)
    extra_per_tooth = 2.0 * amplitude
    n_teeth = max(1, math.ceil(extra_length / extra_per_tooth))

    new_pts: List[Dict] = [{"x": start["x"], "y": start["y"]}]
    sign = 1.0
    for i in range(n_teeth):
        t0 = i / n_teeth
        t1 = (i + 0.5) / n_teeth
        t2 = (i + 1) / n_teeth
        p0 = {"x": start["x"] + ux * seg_len * t0, "y": start["y"] + uy * seg_len * t0}
        p_peak = {
            "x": start["x"] + ux * seg_len * t1 + px * amplitude * sign,
            "y": start["y"] + uy * seg_len * t1 + py * amplitude * sign,
        }
        p2 = {"x": start["x"] + ux * seg_len * t2, "y": start["y"] + uy * seg_len * t2}
        new_pts.extend([p_peak, p2])
        sign = -sign

    new_pts.append({"x": end["x"], "y": end["y"]})

    # Deduplicate consecutive duplicate points that arise from the loop above.
    deduped: List[Dict] = [new_pts[0]]
    for pt in new_pts[1:]:
        if _dist(deduped[-1], pt) > 1e-9:
            deduped.append(pt)

    # Convert the meander point-list back to segment objects.
    net_id = seg.get("net_id", "")
    layer = seg.get("layer", "top_copper")
    width_mm = seg.get("width_mm", 0.2)
    meander_segs = _polyline_to_segments(deduped, net_id, layer, width_mm)

    return segs[:longest_i] + meander_segs + segs[longest_i + 1:]


# ── validate_diff_pair ─────────────────────────────────────────────────────────

_DEFAULT_MAX_VIAS = 4
_SPACING_TOL = 0.01  # mm — tolerance on spacing check
_SKEW_TOL = 0.1      # mm — max allowed |len_pos - len_neg|


def validate_diff_pair(
    segs_pos: List[Dict],
    segs_neg: List[Dict],
    design_rules: Dict,
) -> Dict:
    """Validate a routed differential pair.

    Checks
    ------
    1. Spacing between P and N segments meets ``coupling_spacing_mm`` from
       design_rules (default 0.2 mm).  Any segment-pair that is too close
       or too far (> 2× target) is a violation.
    2. Length match: |len_pos − len_neg| ≤ ``skew_max_mm`` (default 0.1 mm).
    3. Via count per conductor ≤ ``max_vias`` (default 4).

    Returns
    -------
    {"ok": bool, "violations": [{"type": str, "detail": str}, ...]}
    """
    clearance = float(design_rules.get("clearance_mm") or 0.2)
    coupling_spacing = float(design_rules.get("coupling_spacing_mm") or clearance)
    skew_max = float(design_rules.get("skew_max_mm") or _SKEW_TOL)
    max_vias = int(design_rules.get("max_vias") or _DEFAULT_MAX_VIAS)

    violations: List[Dict] = []

    # 1. Spacing check — every pos-segment vs every neg-segment on the same layer.
    min_spacing = coupling_spacing - _SPACING_TOL
    max_spacing = coupling_spacing * 2 + _SPACING_TOL

    for sp in segs_pos:
        for sn in segs_neg:
            if sp.get("layer") != sn.get("layer"):
                continue
            d = _segment_pair_distance(sp, sn)
            if d < min_spacing:
                violations.append({
                    "type": "spacing_too_close",
                    "detail": (
                        f"seg {sp['id']} vs {sn['id']}: "
                        f"distance {d:.4f} mm < {min_spacing:.4f} mm required"
                    ),
                })
            elif d > max_spacing:
                violations.append({
                    "type": "spacing_too_far",
                    "detail": (
                        f"seg {sp['id']} vs {sn['id']}: "
                        f"distance {d:.4f} mm > {max_spacing:.4f} mm (2× target)"
                    ),
                })

    # 2. Length match.
    len_pos = _segs_total_length(segs_pos)
    len_neg = _segs_total_length(segs_neg)
    delta = abs(len_pos - len_neg)
    if delta > skew_max:
        violations.append({
            "type": "length_mismatch",
            "detail": (
                f"|len_pos ({len_pos:.4f}) - len_neg ({len_neg:.4f})| = "
                f"{delta:.4f} mm > skew_max {skew_max:.4f} mm"
            ),
        })

    # 3. Via count.
    def _count_vias(segs: List[Dict]) -> int:
        return sum(1 for s in segs if s.get("type") == "via" or s.get("is_via") is True)

    vias_pos = _count_vias(segs_pos)
    vias_neg = _count_vias(segs_neg)
    for label, count in (("pos", vias_pos), ("neg", vias_neg)):
        if count > max_vias:
            violations.append({
                "type": "too_many_vias",
                "detail": f"{label} conductor has {count} vias > max {max_vias}",
            })

    return {"ok": len(violations) == 0, "violations": violations}


# ── LLM tool wrappers ──────────────────────────────────────────────────────────

# push_shove_segment_tool

_push_shove_segment_spec = ToolSpec(
    name="push_shove_segment",
    description=(
        "Push neighbouring PCB tracks aside to make room for a new segment while "
        "respecting clearance from design_rules.  Returns the updated segment list "
        "with displaced tracks and counts of resolved/unresolved conflicts."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "existing_segments": {
                "type": "array",
                "description": "Existing track segments [{id, net_id, layer, width_mm, start:{x,y}, end:{x,y}}].",
                "items": {"type": "object"},
            },
            "new_segment": {
                "type": "object",
                "description": "The new segment being inserted (same schema as existing_segments items).",
            },
            "board": {
                "type": "object",
                "description": "PCB board dict (used for layer context).",
            },
            "design_rules": {
                "type": "object",
                "description": "Design rules; must contain clearance_mm.",
            },
        },
        "required": ["existing_segments", "new_segment", "board", "design_rules"],
    },
)


@register(_push_shove_segment_spec, write=True)
async def push_shove_segment_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    existing = a.get("existing_segments")
    new_seg = a.get("new_segment")
    board = a.get("board") or {}
    rules = a.get("design_rules") or {}

    if not isinstance(existing, list):
        return err_payload("existing_segments must be an array", "BAD_ARGS")
    if not isinstance(new_seg, dict):
        return err_payload("new_segment must be an object", "BAD_ARGS")
    for key in ("start", "end"):
        if not isinstance(new_seg.get(key), dict):
            return err_payload(f"new_segment.{key} must be an {{x,y}} object", "BAD_ARGS")

    result = push_shove_segment(existing, new_seg, board, rules)
    return ok_payload(result)


# route_diff_pair_tool

_route_diff_pair_spec = ToolSpec(
    name="route_diff_pair_ps",
    description=(
        "Auto-route a coupled differential pair from start to end, maintaining "
        "coupling spacing throughout.  Returns segment lists for the positive and "
        "negative conductors plus an (empty) via list.  Use validate_diff_pair to "
        "check the result."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "net_pos": {"type": "string", "description": "Net identifier for the P conductor."},
            "net_neg": {"type": "string", "description": "Net identifier for the N conductor."},
            "start": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
                "description": "Route start point {x, y} in mm.",
            },
            "end": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
                "description": "Route end point {x, y} in mm.",
            },
            "spacing": {
                "type": "number",
                "description": "Edge-to-edge coupling gap between P and N in mm.",
            },
            "board": {
                "type": "object",
                "description": "PCB board dict (used for layer/width defaults).",
            },
        },
        "required": ["net_pos", "net_neg", "start", "end", "spacing", "board"],
    },
)


@register(_route_diff_pair_spec, write=True)
async def route_diff_pair_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    net_pos = (a.get("net_pos") or "").strip()
    net_neg = (a.get("net_neg") or "").strip()
    start = a.get("start")
    end = a.get("end")
    spacing = a.get("spacing")
    board = a.get("board") or {}

    if not net_pos:
        return err_payload("net_pos is required", "BAD_ARGS")
    if not net_neg:
        return err_payload("net_neg is required", "BAD_ARGS")
    if not isinstance(start, dict) or start.get("x") is None or start.get("y") is None:
        return err_payload("start must be {x, y}", "BAD_ARGS")
    if not isinstance(end, dict) or end.get("x") is None or end.get("y") is None:
        return err_payload("end must be {x, y}", "BAD_ARGS")
    if not isinstance(spacing, (int, float)) or spacing <= 0:
        return err_payload("spacing must be a positive number", "BAD_ARGS")

    segs_pos, segs_neg, vias = route_diff_pair(net_pos, net_neg, start, end, spacing, board)
    len_pos = _segs_total_length(segs_pos)
    len_neg = _segs_total_length(segs_neg)

    return ok_payload({
        "segs_pos": segs_pos,
        "segs_neg": segs_neg,
        "vias": vias,
        "length_pos_mm": len_pos,
        "length_neg_mm": len_neg,
        "skew_mm": abs(len_pos - len_neg),
    })


# tune_diff_pair_skew_tool

_tune_diff_pair_skew_spec = ToolSpec(
    name="tune_diff_pair_skew",
    description=(
        "Adjust the path lengths of a routed differential pair so that "
        "len(pos) − len(neg) matches target_length_diff_mm (default 0, "
        "meaning zero skew).  Inserts a serpentine meander on the shorter "
        "conductor.  Returns updated segment lists."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "segs_pos": {
                "type": "array",
                "description": "Positive conductor segments from route_diff_pair_ps.",
                "items": {"type": "object"},
            },
            "segs_neg": {
                "type": "array",
                "description": "Negative conductor segments from route_diff_pair_ps.",
                "items": {"type": "object"},
            },
            "target_length_diff_mm": {
                "type": "number",
                "description": "Desired len(pos) − len(neg) in mm.  Default: 0.",
            },
        },
        "required": ["segs_pos", "segs_neg"],
    },
)


@register(_tune_diff_pair_skew_spec, write=True)
async def tune_diff_pair_skew_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    segs_pos = a.get("segs_pos")
    segs_neg = a.get("segs_neg")
    target = a.get("target_length_diff_mm", 0.0)

    if not isinstance(segs_pos, list):
        return err_payload("segs_pos must be an array", "BAD_ARGS")
    if not isinstance(segs_neg, list):
        return err_payload("segs_neg must be an array", "BAD_ARGS")
    if not isinstance(target, (int, float)):
        return err_payload("target_length_diff_mm must be a number", "BAD_ARGS")

    result = tune_diff_pair_skew(
        {"segs_pos": segs_pos, "segs_neg": segs_neg},
        target_length_diff_mm=float(target),
    )
    return ok_payload(result)


# validate_diff_pair_tool

_validate_diff_pair_spec = ToolSpec(
    name="validate_diff_pair",
    description=(
        "Validate a routed differential pair against design rules.  Checks: "
        "spacing between P and N conductors (too close or too far); "
        "length match within skew_max_mm; via count per conductor.  "
        "Returns {ok, violations[]}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "segs_pos": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Positive conductor segments.",
            },
            "segs_neg": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Negative conductor segments.",
            },
            "design_rules": {
                "type": "object",
                "description": (
                    "Rules dict.  Keys: clearance_mm, coupling_spacing_mm, "
                    "skew_max_mm, max_vias."
                ),
            },
        },
        "required": ["segs_pos", "segs_neg", "design_rules"],
    },
)


@register(_validate_diff_pair_spec, write=False)
async def validate_diff_pair_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    segs_pos = a.get("segs_pos")
    segs_neg = a.get("segs_neg")
    rules = a.get("design_rules")

    if not isinstance(segs_pos, list):
        return err_payload("segs_pos must be an array", "BAD_ARGS")
    if not isinstance(segs_neg, list):
        return err_payload("segs_neg must be an array", "BAD_ARGS")
    if not isinstance(rules, dict):
        return err_payload("design_rules must be an object", "BAD_ARGS")

    result = validate_diff_pair(segs_pos, segs_neg, rules)
    return ok_payload(result)
