"""
kerf_cad_core.jewelry.cad_qc
=============================

Pre-production CAD quality-control checker for jewelry models.

Audits a jewelry feature-model dict for castability/printability before the
model is sent to a casting house, DMLS bureau, or resin-print farm.

## Model dict schema (all keys optional; missing keys yield graceful warnings)

    {
      "process":          str,    # "cast" | "dmls" | "resin_print"  (default "cast")
      "alloy":            str,    # alloy key from metal_cost (default "18k_yellow")
      "walls": [                  # list of wall/section feature dicts
        {
          "id":           str,    # unique location label  (default "wall_<n>")
          "thickness_mm": float,  # measured wall thickness in mm
        }, ...
      ],
      "prongs": [                 # prong feature dicts
        {
          "id":           str,
          "base_mm":      float,  # prong base diameter/width in mm
          "tip_mm":       float,  # prong tip diameter/width in mm (optional)
          "height_mm":    float,  # prong height in mm (optional)
        }, ...
      ],
      "stones": [                 # stone placement dicts
        {
          "id":           str,
          "girdle_mm":    float,  # girdle diameter in mm
          "seat_depth_mm": float, # depth of the stone seat/bearing in mm (optional)
          "clearance_to_neighbor_mm": float,  # metal between this stone and nearest (optional)
          "clearance_to_edge_mm":     float,  # metal between stone and outer edge (optional)
        }, ...
      ],
      "topology": {               # mesh/solid topology summary
        "is_manifold":  bool,     # True if the shell is closed / watertight
        "naked_edge_count": int,  # number of unmatched boundary edges (0 = clean)
      },
      "draw_direction": str,      # dominant pull axis for mould: "+z"/"-z"/"+x"/"-x"…
      "undercut_faces": [         # list of face ids with undercut geometry
        {"id": str, "angle_deg": float}, ...
      ],
      "hollows": [                # hollow cavity descriptors
        {
          "id":          str,
          "access_open": bool,    # True if a drain/sprue hole exists
          "sprue_dia_mm": float,  # diameter of access hole (0 if closed)
        }, ...
      ],
      "rails": [                  # thin rail / knife-edge feature dicts
        {
          "id":          str,
          "width_mm":    float,   # narrowest cross-section width
          "height_mm":   float,   # height of the rail (optional)
        }, ...
      ],
      "drill_features": [         # drilled or bur-cut holes
        {
          "id":          str,
          "radius_mm":   float,   # minimum bur/drill radius used
        }, ...
      ],
      "weight_g":         float,  # current model weight in grams
      "target_weight_g":  float,  # target weight (optional; omit to skip weight check)
      "weight_tolerance_pct": float,  # allowed ± % from target (default 10)
      "thresholds": {             # optional override block — any key overrides the default
        "cast_min_wall_mm":     float,
        "dmls_min_wall_mm":     float,
        "resin_min_wall_mm":    float,
        "min_prong_base_mm":    float,
        "min_stone_clearance_mm": float,
        "min_seat_depth_pct":   float,  # seat depth as % of girdle (default 25)
        "min_drill_radius_mm":  float,
        "knife_edge_threshold_mm": float,
        "rail_aspect_warn":     float,  # height/width ratio above which to warn
      }
    }

## Rule IDs and severities

    WALL_THIN          FAIL  — wall thickness below process minimum
    PRONG_BASE         WARN  — prong base below recommended minimum
    STONE_CLEARANCE    FAIL  — stone-to-stone or stone-to-edge clearance too tight
    SEAT_DEPTH         WARN  — seat depth shallower than girdle fraction
    MANIFOLD           FAIL  — open shell / naked edges present
    UNDERCUT           WARN  — undercut faces detected for mould/casting
    HOLLOW_ACCESS      FAIL  — hollow cavity with no drain/sprue access
    KNIFE_EDGE         WARN  — rail or section below knife-edge threshold
    DRILL_RADIUS       WARN  — drill/bur radius below castable minimum
    WEIGHT_BAND        WARN  — model weight outside target band

## Output schema

    {
      "ok":     bool,           # False only on internal error / missing required field
      "reason": str,            # populated when ok is False
      "verdict": str,           # "ready" | "rework" | "n/a" (no rules ran)
      "process": str,
      "alloy":   str,
      "results": [              # one dict per rule evaluation (sorted by severity)
        {
          "rule_id":    str,
          "severity":   str,    # "FAIL" | "WARN" | "PASS"
          "location":   str,    # feature id or "global"
          "measured":   float | None,
          "threshold":  float | None,
          "message":    str,
        }, ...
      ],
      "fix_list": [             # only FAIL/WARN items, priority-ordered
        {"priority": int, "rule_id": str, "location": str, "message": str}, ...
      ],
    }

## Never raises.

All entry paths catch exceptions and return {"ok": False, "reason": ...}.

## LLM tools registered (gated)

    jewelry_cad_qc
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3, METAL_LABELS
from kerf_cad_core.jewelry.hollowing import _HOLE_DIA_MIN_MM as _DRAIN_HOLE_MIN
from kerf_cad_core.jewelry.production import _SPRUE_DIA_MIN_MM

# ---------------------------------------------------------------------------
# Default threshold tables
# ---------------------------------------------------------------------------

# Minimum wall thickness per process (mm).
# Cast (lost-wax):   0.8 mm — RhinoGold / MatrixGold production guideline; Stuller
# DMLS (metal SLM): 0.4 mm — EOS M 290 recommended minimum for jewelry
# Resin (castable): 0.6 mm — Formlabs Castable Wax 40 specification
_DEFAULT_MIN_WALL: Dict[str, float] = {
    "cast":        0.8,
    "dmls":        0.4,
    "resin_print": 0.6,
}

# Minimum prong base diameter (mm).
# Industry bench rule: ≥ 0.8 mm base for a four-prong setting on a 1 ct round.
# Below 0.7 mm the prong cannot be formed and polished without shearing.
_DEFAULT_MIN_PRONG_BASE_MM: float = 0.7

# Minimum stone-to-stone / stone-to-edge metal clearance (mm).
# MatrixGold default pavé separation is 0.15 mm; cast minimum is 0.20 mm.
_DEFAULT_MIN_STONE_CLEARANCE_MM: float = 0.20

# Seat depth as a percentage of girdle diameter.
# Benchmark: pavilion depth ≈ 43% for round brilliant; seat should capture ≥ 25%
# of the girdle for the stone to be stable.
_DEFAULT_MIN_SEAT_DEPTH_PCT: float = 25.0

# Minimum drill / bur radius (mm).
# Standard jewellery bur sets bottom at 0.3 mm radius.
_DEFAULT_MIN_DRILL_RADIUS_MM: float = 0.3

# Knife-edge threshold (mm): a section thinner than this is a structural hazard.
_DEFAULT_KNIFE_EDGE_THRESHOLD_MM: float = 0.4

# Rail aspect-ratio warn threshold: height / width.
# A tall narrow rail is structurally weak; threshold 5:1 is a common bench rule.
_DEFAULT_RAIL_ASPECT_WARN: float = 5.0

# Weight tolerance default (±%).
_DEFAULT_WEIGHT_TOLERANCE_PCT: float = 10.0

# Valid processes.
_VALID_PROCESSES = {"cast", "dmls", "resin_print"}

# Severity ordering (lower int = higher priority in the fix list).
_SEVERITY_PRIORITY: Dict[str, int] = {"FAIL": 0, "WARN": 1, "PASS": 2}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bad(reason: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason}


def _result(
    rule_id: str,
    severity: str,
    location: str,
    measured: Optional[float],
    threshold: Optional[float],
    message: str,
) -> Dict[str, Any]:
    return {
        "rule_id":   rule_id,
        "severity":  severity,
        "location":  location,
        "measured":  measured,
        "threshold": threshold,
        "message":   message,
    }


def _thresholds(overrides: Optional[Dict[str, Any]], process: str) -> Dict[str, float]:
    """Merge defaults with any caller-supplied overrides."""
    ov = overrides or {}
    return {
        "min_wall_mm": float(
            ov.get(f"{process}_min_wall_mm",
                   ov.get("min_wall_mm",
                          _DEFAULT_MIN_WALL.get(process, _DEFAULT_MIN_WALL["cast"])))
        ),
        "min_prong_base_mm":     float(ov.get("min_prong_base_mm",     _DEFAULT_MIN_PRONG_BASE_MM)),
        "min_stone_clearance_mm": float(ov.get("min_stone_clearance_mm", _DEFAULT_MIN_STONE_CLEARANCE_MM)),
        "min_seat_depth_pct":    float(ov.get("min_seat_depth_pct",    _DEFAULT_MIN_SEAT_DEPTH_PCT)),
        "min_drill_radius_mm":   float(ov.get("min_drill_radius_mm",   _DEFAULT_MIN_DRILL_RADIUS_MM)),
        "knife_edge_threshold_mm": float(ov.get("knife_edge_threshold_mm", _DEFAULT_KNIFE_EDGE_THRESHOLD_MM)),
        "rail_aspect_warn":      float(ov.get("rail_aspect_warn",      _DEFAULT_RAIL_ASPECT_WARN)),
        "weight_tolerance_pct":  float(ov.get("weight_tolerance_pct",  _DEFAULT_WEIGHT_TOLERANCE_PCT)),
    }


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------

def _check_walls(walls: List[Dict], thresh: Dict, process: str) -> List[Dict]:
    results = []
    min_wall = thresh["min_wall_mm"]
    for i, wall in enumerate(walls):
        wid = str(wall.get("id", f"wall_{i + 1}"))
        try:
            t = float(wall["thickness_mm"])
        except (KeyError, TypeError, ValueError):
            results.append(_result(
                "WALL_THIN", "WARN", wid, None, min_wall,
                f"thickness_mm missing or non-numeric for {wid}; skipping wall check"
            ))
            continue
        if t < min_wall:
            results.append(_result(
                "WALL_THIN", "FAIL", wid, round(t, 4), min_wall,
                f"{wid}: wall {t:.3f} mm < {process} minimum {min_wall:.3f} mm — thin wall will crack during casting/build"
            ))
        else:
            results.append(_result(
                "WALL_THIN", "PASS", wid, round(t, 4), min_wall,
                f"{wid}: wall {t:.3f} mm ≥ {process} minimum {min_wall:.3f} mm"
            ))
    return results


def _check_prongs(prongs: List[Dict], thresh: Dict) -> List[Dict]:
    results = []
    min_base = thresh["min_prong_base_mm"]
    for i, prong in enumerate(prongs):
        pid = str(prong.get("id", f"prong_{i + 1}"))
        try:
            base = float(prong["base_mm"])
        except (KeyError, TypeError, ValueError):
            results.append(_result(
                "PRONG_BASE", "WARN", pid, None, min_base,
                f"base_mm missing or non-numeric for {pid}; skipping prong check"
            ))
            continue
        if base < min_base:
            sev = "FAIL" if base < min_base * 0.8 else "WARN"
            results.append(_result(
                "PRONG_BASE", sev, pid, round(base, 4), min_base,
                f"{pid}: prong base {base:.3f} mm < recommended {min_base:.3f} mm — may shear during polishing"
            ))
        else:
            results.append(_result(
                "PRONG_BASE", "PASS", pid, round(base, 4), min_base,
                f"{pid}: prong base {base:.3f} mm ≥ {min_base:.3f} mm"
            ))
        # Optional taper check: tip should be ≥ 40 % of base.
        tip_raw = prong.get("tip_mm")
        if tip_raw is not None:
            try:
                tip = float(tip_raw)
                taper_ratio = tip / base if base > 0 else 1.0
                if taper_ratio < 0.30:
                    results.append(_result(
                        "PRONG_BASE", "WARN", pid, round(tip, 4), round(base * 0.30, 4),
                        f"{pid}: prong tip {tip:.3f} mm is less than 30% of base ({base:.3f} mm) — aggressive taper may snap"
                    ))
            except (TypeError, ValueError):
                pass
    return results


def _check_stones(stones: List[Dict], thresh: Dict) -> List[Dict]:
    results = []
    min_cl = thresh["min_stone_clearance_mm"]
    min_seat_pct = thresh["min_seat_depth_pct"]
    for i, stone in enumerate(stones):
        sid = str(stone.get("id", f"stone_{i + 1}"))
        girdle = stone.get("girdle_mm")

        # Clearance to nearest neighbour
        cl = stone.get("clearance_to_neighbor_mm")
        if cl is not None:
            try:
                cl_f = float(cl)
                if cl_f < min_cl:
                    results.append(_result(
                        "STONE_CLEARANCE", "FAIL", sid, round(cl_f, 4), min_cl,
                        f"{sid}: stone-to-stone clearance {cl_f:.3f} mm < {min_cl:.3f} mm — metal too thin to invest and polish"
                    ))
                else:
                    results.append(_result(
                        "STONE_CLEARANCE", "PASS", sid, round(cl_f, 4), min_cl,
                        f"{sid}: stone-to-stone clearance {cl_f:.3f} mm ≥ {min_cl:.3f} mm"
                    ))
            except (TypeError, ValueError):
                pass

        # Clearance to outer edge
        cl_edge = stone.get("clearance_to_edge_mm")
        if cl_edge is not None:
            try:
                cl_edge_f = float(cl_edge)
                if cl_edge_f < min_cl:
                    results.append(_result(
                        "STONE_CLEARANCE", "FAIL", f"{sid}_edge", round(cl_edge_f, 4), min_cl,
                        f"{sid}: stone-to-edge clearance {cl_edge_f:.3f} mm < {min_cl:.3f} mm"
                    ))
                else:
                    results.append(_result(
                        "STONE_CLEARANCE", "PASS", f"{sid}_edge", round(cl_edge_f, 4), min_cl,
                        f"{sid}: stone-to-edge clearance {cl_edge_f:.3f} mm ≥ {min_cl:.3f} mm"
                    ))
            except (TypeError, ValueError):
                pass

        # Seat depth vs girdle diameter
        seat = stone.get("seat_depth_mm")
        if seat is not None and girdle is not None:
            try:
                seat_f = float(seat)
                girdle_f = float(girdle)
                if girdle_f > 0:
                    actual_pct = (seat_f / girdle_f) * 100.0
                    threshold_depth = girdle_f * min_seat_pct / 100.0
                    if actual_pct < min_seat_pct:
                        results.append(_result(
                            "SEAT_DEPTH", "WARN", sid, round(seat_f, 4), round(threshold_depth, 4),
                            f"{sid}: seat depth {seat_f:.3f} mm ({actual_pct:.1f}% of girdle) < {min_seat_pct:.0f}% threshold — stone may rock or fall out"
                        ))
                    else:
                        results.append(_result(
                            "SEAT_DEPTH", "PASS", sid, round(seat_f, 4), round(threshold_depth, 4),
                            f"{sid}: seat depth {seat_f:.3f} mm ({actual_pct:.1f}% of girdle) ≥ {min_seat_pct:.0f}% threshold"
                        ))
            except (TypeError, ValueError):
                pass

    return results


def _check_manifold(topology: Optional[Dict]) -> List[Dict]:
    if topology is None:
        return []
    results = []
    is_manifold = topology.get("is_manifold")
    naked = topology.get("naked_edge_count", 0)

    if is_manifold is False or (isinstance(naked, (int, float)) and naked > 0):
        naked_count = int(naked) if isinstance(naked, (int, float)) else "unknown"
        results.append(_result(
            "MANIFOLD", "FAIL", "global", float(naked_count) if isinstance(naked_count, int) else None, 0.0,
            f"Open shell detected: {naked_count} naked edge(s) — model must be watertight/manifold before production"
        ))
    else:
        results.append(_result(
            "MANIFOLD", "PASS", "global", 0.0, 0.0,
            "Shell is closed and manifold"
        ))
    return results


def _check_undercuts(undercut_faces: Optional[List[Dict]], draw_direction: Optional[str]) -> List[Dict]:
    if not undercut_faces:
        return []
    results = []
    for i, face in enumerate(undercut_faces):
        fid = str(face.get("id", f"face_{i + 1}"))
        angle = face.get("angle_deg")
        draw = draw_direction or "unspecified"
        try:
            angle_f = float(angle) if angle is not None else None
        except (TypeError, ValueError):
            angle_f = None
        msg = (
            f"{fid}: undercut relative to draw direction '{draw}'"
            + (f" at {angle_f:.1f}°" if angle_f is not None else "")
            + " — requires split mould, flexible mould, or design change for lost-wax casting"
        )
        results.append(_result(
            "UNDERCUT", "WARN", fid, angle_f, None, msg
        ))
    return results


def _check_hollows(hollows: Optional[List[Dict]], thresh: Dict) -> List[Dict]:
    if not hollows:
        return []
    results = []
    min_sprue = float(_SPRUE_DIA_MIN_MM)  # 2.0 mm from production.py
    for i, hollow in enumerate(hollows):
        hid = str(hollow.get("id", f"hollow_{i + 1}"))
        access_open = hollow.get("access_open", False)
        sprue_dia = hollow.get("sprue_dia_mm", 0.0)
        try:
            sprue_f = float(sprue_dia)
        except (TypeError, ValueError):
            sprue_f = 0.0

        if not access_open or sprue_f < _DRAIN_HOLE_MIN:
            results.append(_result(
                "HOLLOW_ACCESS", "FAIL", hid, sprue_f if sprue_f > 0 else None, _DRAIN_HOLE_MIN,
                f"{hid}: hollow cavity has no adequate sprue/drain access (diameter {sprue_f:.2f} mm < {_DRAIN_HOLE_MIN:.2f} mm) — investment will trap; casting will fail"
            ))
        else:
            results.append(_result(
                "HOLLOW_ACCESS", "PASS", hid, round(sprue_f, 4), _DRAIN_HOLE_MIN,
                f"{hid}: hollow has access hole {sprue_f:.2f} mm ≥ {_DRAIN_HOLE_MIN:.2f} mm minimum"
            ))
    return results


def _check_rails(rails: Optional[List[Dict]], thresh: Dict) -> List[Dict]:
    if not rails:
        return []
    results = []
    ke_thresh = thresh["knife_edge_threshold_mm"]
    aspect_warn = thresh["rail_aspect_warn"]
    for i, rail in enumerate(rails):
        rid = str(rail.get("id", f"rail_{i + 1}"))
        try:
            width = float(rail["width_mm"])
        except (KeyError, TypeError, ValueError):
            results.append(_result(
                "KNIFE_EDGE", "WARN", rid, None, ke_thresh,
                f"width_mm missing for {rid}; skipping knife-edge check"
            ))
            continue
        if width < ke_thresh:
            results.append(_result(
                "KNIFE_EDGE", "WARN", rid, round(width, 4), ke_thresh,
                f"{rid}: rail width {width:.3f} mm < knife-edge threshold {ke_thresh:.3f} mm — structurally weak; will distort under polishing"
            ))
        else:
            results.append(_result(
                "KNIFE_EDGE", "PASS", rid, round(width, 4), ke_thresh,
                f"{rid}: rail width {width:.3f} mm ≥ {ke_thresh:.3f} mm"
            ))
        # Aspect ratio check
        height_raw = rail.get("height_mm")
        if height_raw is not None:
            try:
                height = float(height_raw)
                if width > 0:
                    aspect = height / width
                    if aspect > aspect_warn:
                        results.append(_result(
                            "KNIFE_EDGE", "WARN", f"{rid}_aspect", round(aspect, 2), aspect_warn,
                            f"{rid}: rail aspect ratio {aspect:.1f} (height/width) > {aspect_warn:.0f} — tall thin rail is fragile"
                        ))
            except (TypeError, ValueError):
                pass
    return results


def _check_drills(drill_features: Optional[List[Dict]], thresh: Dict) -> List[Dict]:
    if not drill_features:
        return []
    results = []
    min_r = thresh["min_drill_radius_mm"]
    for i, feat in enumerate(drill_features):
        did = str(feat.get("id", f"drill_{i + 1}"))
        try:
            r = float(feat["radius_mm"])
        except (KeyError, TypeError, ValueError):
            results.append(_result(
                "DRILL_RADIUS", "WARN", did, None, min_r,
                f"radius_mm missing for {did}; skipping drill-radius check"
            ))
            continue
        if r < min_r:
            results.append(_result(
                "DRILL_RADIUS", "WARN", did, round(r, 4), min_r,
                f"{did}: drill/bur radius {r:.3f} mm < minimum {min_r:.3f} mm — standard bur sets cannot achieve this radius"
            ))
        else:
            results.append(_result(
                "DRILL_RADIUS", "PASS", did, round(r, 4), min_r,
                f"{did}: drill/bur radius {r:.3f} mm ≥ {min_r:.3f} mm"
            ))
    return results


def _check_weight(
    weight_g: Optional[float],
    target_g: Optional[float],
    tol_pct: float,
) -> List[Dict]:
    if weight_g is None or target_g is None:
        return []
    try:
        w = float(weight_g)
        t = float(target_g)
    except (TypeError, ValueError):
        return []
    if t <= 0:
        return []
    delta_pct = abs(w - t) / t * 100.0
    threshold = t * tol_pct / 100.0
    if delta_pct > tol_pct:
        return [_result(
            "WEIGHT_BAND", "WARN", "global", round(w, 4), round(t, 4),
            f"Weight {w:.4f} g is {delta_pct:.1f}% from target {t:.4f} g (tolerance ±{tol_pct:.0f}%)"
        )]
    return [_result(
        "WEIGHT_BAND", "PASS", "global", round(w, 4), round(t, 4),
        f"Weight {w:.4f} g within ±{tol_pct:.0f}% of target {t:.4f} g"
    )]


# ---------------------------------------------------------------------------
# Fix list builder
# ---------------------------------------------------------------------------

def _build_fix_list(results: List[Dict]) -> List[Dict]:
    """Build a priority-ordered fix list from FAIL/WARN results."""
    items = [r for r in results if r["severity"] in ("FAIL", "WARN")]
    # Sort: FAIL before WARN, then by rule_id alphabetically for determinism
    items.sort(key=lambda r: (_SEVERITY_PRIORITY[r["severity"]], r["rule_id"], r["location"]))
    fix_list = []
    for priority, item in enumerate(items, start=1):
        fix_list.append({
            "priority": priority,
            "rule_id":  item["rule_id"],
            "location": item["location"],
            "severity": item["severity"],
            "message":  item["message"],
        })
    return fix_list


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cad_qc(model: Any) -> Dict[str, Any]:
    """
    Audit a jewelry feature-model dict for castability/printability.

    Parameters
    ----------
    model : dict
        Jewelry feature-model as described in the module docstring.

    Returns
    -------
    dict
        QC report; "ok" is False only on internal error.  "verdict" is
        "ready" (no FAIL/WARN) or "rework" (at least one FAIL or WARN).
        Never raises.
    """
    try:
        return _cad_qc_inner(model)
    except Exception as exc:
        return {"ok": False, "reason": f"cad_qc internal error: {exc}"}


def _cad_qc_inner(model: Any) -> Dict[str, Any]:
    if not isinstance(model, dict):
        return _bad("model must be a dict")

    process = str(model.get("process", "cast")).strip().lower()
    if process not in _VALID_PROCESSES:
        process = "cast"  # graceful fallback

    alloy = str(model.get("alloy", "18k_yellow")).strip().lower()
    # Normalise unknown alloy keys gracefully
    if alloy not in METAL_DENSITY_G_CM3:
        alloy = "18k_yellow"

    thresh = _thresholds(model.get("thresholds"), process)

    all_results: List[Dict] = []

    # --- Wall thickness ---------------------------------------------------
    walls = model.get("walls") or []
    if isinstance(walls, list):
        all_results.extend(_check_walls(walls, thresh, process))

    # --- Prongs ----------------------------------------------------------
    prongs = model.get("prongs") or []
    if isinstance(prongs, list):
        all_results.extend(_check_prongs(prongs, thresh))

    # --- Stones (clearance + seat depth) ---------------------------------
    stones = model.get("stones") or []
    if isinstance(stones, list):
        all_results.extend(_check_stones(stones, thresh))

    # --- Manifold / topology ---------------------------------------------
    topology = model.get("topology")
    if isinstance(topology, dict):
        all_results.extend(_check_manifold(topology))
    elif topology is not None:
        # Wrong type: emit a warning rather than crashing
        all_results.append(_result(
            "MANIFOLD", "WARN", "global", None, None,
            "topology field is not a dict; manifold check skipped"
        ))

    # --- Undercuts -------------------------------------------------------
    undercuts = model.get("undercut_faces")
    draw_dir = model.get("draw_direction")
    if undercuts is not None and isinstance(undercuts, list):
        all_results.extend(_check_undercuts(undercuts, draw_dir))

    # --- Hollow access ---------------------------------------------------
    hollows = model.get("hollows")
    if hollows is not None and isinstance(hollows, list):
        all_results.extend(_check_hollows(hollows, thresh))

    # --- Rails / knife-edges ---------------------------------------------
    rails = model.get("rails")
    if rails is not None and isinstance(rails, list):
        all_results.extend(_check_rails(rails, thresh))

    # --- Drill / bur radius ----------------------------------------------
    drills = model.get("drill_features")
    if drills is not None and isinstance(drills, list):
        all_results.extend(_check_drills(drills, thresh))

    # --- Weight band -----------------------------------------------------
    weight_g = model.get("weight_g")
    target_g = model.get("target_weight_g")
    tol_pct = thresh["weight_tolerance_pct"]
    all_results.extend(_check_weight(weight_g, target_g, tol_pct))

    # --- Verdict ---------------------------------------------------------
    if not all_results:
        verdict = "n/a"
    else:
        has_fail_or_warn = any(r["severity"] in ("FAIL", "WARN") for r in all_results)
        verdict = "rework" if has_fail_or_warn else "ready"

    fix_list = _build_fix_list(all_results)

    return {
        "ok":       True,
        "verdict":  verdict,
        "process":  process,
        "alloy":    alloy,
        "alloy_label": METAL_LABELS.get(alloy, alloy),
        "results":  all_results,
        "fix_list": fix_list,
    }


# ---------------------------------------------------------------------------
# LLM tool spec and runner
# ---------------------------------------------------------------------------

_cad_qc_spec = ToolSpec(
    name="jewelry_cad_qc",
    description=(
        "Pre-production CAD quality-control checker for jewelry models.\n\n"
        "Audits a jewelry feature-model dict for castability/printability before "
        "sending to a casting house, DMLS bureau, or resin-print farm.\n\n"
        "Rules checked:\n"
        "  WALL_THIN          — wall thickness vs process minimum (cast 0.8 mm / "
        "DMLS 0.4 mm / resin 0.6 mm)\n"
        "  PRONG_BASE         — prong base diameter vs recommended minimum (0.7 mm)\n"
        "  STONE_CLEARANCE    — stone-to-stone and stone-to-edge metal clearance\n"
        "  SEAT_DEPTH         — stone seat depth vs girdle fraction\n"
        "  MANIFOLD           — closed shell / no naked edges\n"
        "  UNDERCUT           — undercut faces flagged with draw direction\n"
        "  HOLLOW_ACCESS      — hollow cavities must have a drain/sprue hole\n"
        "  KNIFE_EDGE         — thin rails and knife-edge sections\n"
        "  DRILL_RADIUS       — minimum bur/drill radius achievable by bench tools\n"
        "  WEIGHT_BAND        — model weight within target band\n\n"
        "Returns: verdict ('ready' / 'rework'), per-rule pass/warn/fail results "
        "with measured value, threshold, and location id; priority-ordered fix list.\n\n"
        "All thresholds are configurable via the 'thresholds' sub-dict.\n"
        "Processes: 'cast' (default), 'dmls', 'resin_print'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "model": {
                "type": "object",
                "description": (
                    "Jewelry feature-model dict.  Keys: process, alloy, walls, prongs, "
                    "stones, topology, draw_direction, undercut_faces, hollows, rails, "
                    "drill_features, weight_g, target_weight_g, weight_tolerance_pct, "
                    "thresholds.  All optional; missing keys yield graceful warnings."
                ),
            },
        },
        "required": ["model"],
    },
)


@register(_cad_qc_spec, write=False)
async def run_jewelry_cad_qc(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_cad_qc."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    model = a.get("model")
    if model is None:
        return err_payload("model is required", "BAD_ARGS")
    if not isinstance(model, dict):
        return err_payload("model must be a dict", "BAD_ARGS")

    result = cad_qc(model)
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)
