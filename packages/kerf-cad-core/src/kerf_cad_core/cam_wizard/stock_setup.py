"""
kerf_cad_core.cam_wizard.stock_setup — stock-setup wizard for CNC machining.

Four pure-Python public functions:

  recommend_stock(part_aabb, material, surplus_mm)
      Given a part's axis-aligned bounding box and chosen material, return the
      closest standard stock size (rectangular bar/plate, round bar, or billet),
      waste %, and cost estimate.

  recommend_orientation(part_geometry_summary)
      Choose the best part orientation in stock to minimise total Z-depth of
      machining, limit overhangs, and reduce re-fixturing.  Returns a rotation
      as a unit quaternion + composite score.

  fixture_suggestion(orientation, stock_size, features_to_machine)
      Suggest clamping method (vise / chuck / soft-jaw / fixture-plate-tabs /
      vacuum / magnet) plus clamp positions and, if needed, fixture-tab
      quantity/positions.

  setup_sheet(stock, orientation, fixture)
      Produce a setup-sheet dict containing a text diagram of the orientation,
      zero point, and clamping arrangement for the machinist.

Design constraints
------------------
* Pure Python only — no OCC, no numpy, no external libraries.
* All functions accept plain dicts / scalars; never raise.
* Errors are returned as ``{"ok": False, "reason": "..."}``.
* Material properties are looked up via ``kerf_cad_core.matsel.db``
  (density kg/m³, cost_rel).
* @register LLM tools so the chat agent can invoke them directly.

Standard stock tables
---------------------
Rectangular bar/plate — EN/ISO preferred section widths (mm):
  6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100,
  120, 150, 200, 250, 300 (same series for both cross-section axes).

Standard lengths: 250, 500, 1000, 2000, 3000 mm.

Round bar (diameter, mm):
  3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80,
  90, 100, 110, 120, 150, 200, 250, 300.

References
----------
EN 10060:2003 Hot-rolled round steel bars.
EN 10058:2003 Hot-rolled flat steel bars.
Machinery's Handbook 30th ed. — Stock and material procurement.

Author: imranparuk
"""
from __future__ import annotations

import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

# ---------------------------------------------------------------------------
# Standard stock size tables (mm)
# ---------------------------------------------------------------------------

# Preferred cross-section widths for rectangular bar / plate stock
_RECT_WIDTHS_MM: list[float] = [
    6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50,
    60, 70, 80, 90, 100, 120, 150, 200, 250, 300,
]

# Preferred lengths for bar/plate stock
_STD_LENGTHS_MM: list[float] = [250, 500, 1000, 2000, 3000]

# Preferred round bar diameters (mm)
_ROUND_DIAMETERS_MM: list[float] = [
    3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50,
    60, 70, 80, 90, 100, 110, 120, 150, 200, 250, 300,
]

# Aspect ratio at which a rectangular part is considered "plate-like"
_PLATE_ASPECT_THRESHOLD = 4.0

# ---------------------------------------------------------------------------
# Material property helpers
# ---------------------------------------------------------------------------

# Approximate density (kg/m³) by material family keyword — fallback when
# matsel.db is not available or the material string is free-form.
_FAMILY_DENSITY: dict[str, float] = {
    "aluminum": 2700.0,
    "aluminium": 2700.0,
    "al": 2700.0,
    "steel": 7850.0,
    "stainless": 8000.0,
    "brass": 8500.0,
    "copper": 8940.0,
    "titanium": 4430.0,
    "ti": 4430.0,
    "magnesium": 1770.0,
    "mg": 1770.0,
    "cast_iron": 7200.0,
    "iron": 7200.0,
    "nylon": 1140.0,
    "plastic": 1100.0,
    "wood": 530.0,
}

# Approximate cost per kg (USD) by family keyword — rough market values for
# raw stock.  Used when matsel.db is unavailable.
_FAMILY_COST_PER_KG: dict[str, float] = {
    "aluminum": 2.50,
    "aluminium": 2.50,
    "al": 2.50,
    "steel": 0.90,
    "stainless": 3.20,
    "brass": 4.00,
    "copper": 7.50,
    "titanium": 35.0,
    "ti": 35.0,
    "magnesium": 3.50,
    "mg": 3.50,
    "cast_iron": 0.70,
    "iron": 0.70,
    "nylon": 2.00,
    "plastic": 1.50,
    "wood": 0.30,
}


def _material_props(material: str) -> tuple[float, float]:
    """Return (density_kg_m3, cost_per_kg_usd) for *material*.

    Tries matsel.db first; falls back to family keyword table; defaults to
    steel values when unknown.
    """
    # Try exact matsel lookup
    try:
        from kerf_cad_core.matsel.db import get_material, _DB
        mat_data = get_material(material)
        if mat_data is not None:
            density = float(mat_data["density"])
            # cost_rel is dimensionless (steel=1.0); scale to USD/kg using
            # steel base of 0.90 USD/kg.
            cost_per_kg = float(mat_data["cost_rel"]) * 0.90
            return density, cost_per_kg
    except Exception:
        pass

    # Try family keyword matching (case-insensitive substring)
    mat_lower = material.lower()
    for key, density in _FAMILY_DENSITY.items():
        if key in mat_lower:
            cost = _FAMILY_COST_PER_KG.get(key, 0.90)
            return density, cost

    # Unknown material — default to mild steel
    return 7850.0, 0.90


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _next_standard(value: float, table: list[float]) -> float:
    """Return the smallest entry in *table* that is >= *value*."""
    for v in sorted(table):
        if v >= value:
            return v
    return sorted(table)[-1]  # part larger than largest standard — return max


def _part_volume_mm3(aabb: dict) -> float:
    """Return part volume in mm³ from its AABB."""
    dx = abs(aabb.get("max_x", 0) - aabb.get("min_x", 0))
    dy = abs(aabb.get("max_y", 0) - aabb.get("min_y", 0))
    dz = abs(aabb.get("max_z", 0) - aabb.get("min_z", 0))
    return dx * dy * dz


def _aabb_dims(aabb: dict) -> tuple[float, float, float]:
    """Return (dx, dy, dz) sorted largest first."""
    dx = abs(aabb.get("max_x", 0) - aabb.get("min_x", 0))
    dy = abs(aabb.get("max_y", 0) - aabb.get("min_y", 0))
    dz = abs(aabb.get("max_z", 0) - aabb.get("min_z", 0))
    return tuple(sorted([dx, dy, dz], reverse=True))  # (L, W, H)


# ---------------------------------------------------------------------------
# Public API — recommend_stock
# ---------------------------------------------------------------------------

def recommend_stock(
    part_aabb: dict[str, float],
    material: str,
    surplus_mm: float = 2.0,
) -> dict[str, Any]:
    """Choose the closest standard stock size for *part_aabb*.

    Parameters
    ----------
    part_aabb : dict
        Bounding box with keys ``min_x``, ``max_x``, ``min_y``, ``max_y``,
        ``min_z``, ``max_z`` in millimetres.
    material : str
        Material name or family keyword (e.g. ``"Al_6061_T6"``, ``"aluminum"``,
        ``"steel"``).
    surplus_mm : float
        Minimum additional material on each face (default 2.0 mm) to allow
        facing cuts before reaching part dimensions.

    Returns
    -------
    dict
        ok            : True
        stock_type    : "rect_bar" | "round_bar" | "plate"
        dimensions_mm : dict describing the stock (width/height/length or
                        diameter/length)
        part_dims_mm  : (L, W, H) sorted largest first
        waste_pct     : float — (stock_volume - part_volume) / stock_volume * 100
        cost_estimate : dict — {"currency": "USD", "amount": float,
                                "basis": "density × volume × price_per_kg"}
        material_used : str  — resolved material identifier
        warnings      : list[str]
    """
    warnings: list[str] = []

    # Validate AABB
    required_keys = {"min_x", "max_x", "min_y", "max_y", "min_z", "max_z"}
    missing = required_keys - set(part_aabb.keys())
    if missing:
        return {"ok": False, "reason": f"part_aabb missing keys: {sorted(missing)}"}

    try:
        surplus_mm = float(surplus_mm)
    except (TypeError, ValueError):
        warnings.append(f"Invalid surplus_mm {surplus_mm!r}; using 2.0 mm")
        surplus_mm = 2.0

    if surplus_mm < 0:
        warnings.append("surplus_mm is negative; clamped to 0")
        surplus_mm = 0.0

    try:
        L, W, H = _aabb_dims(part_aabb)  # mm, sorted largest first
    except Exception as exc:
        return {"ok": False, "reason": f"Could not parse part_aabb: {exc}"}

    # Required envelope (add surplus on both faces)
    req_L = L + 2 * surplus_mm
    req_W = W + 2 * surplus_mm
    req_H = H + 2 * surplus_mm

    # Determine whether part is better suited to round bar
    # Heuristic: if two of three dimensions are within 20% of each other
    # and the third is ≥ 2× either, consider round bar
    dims = sorted([L, W, H], reverse=True)
    is_shaft_like = (dims[1] > 0 and abs(dims[1] - dims[2]) / dims[1] < 0.20
                     and dims[0] >= 2.0 * dims[1])

    # Plate-like: largest dimension / smallest ≥ threshold and middle is not shaft
    is_plate_like = (H > 0 and W / H >= _PLATE_ASPECT_THRESHOLD
                     and not is_shaft_like)

    density_kg_m3, cost_per_kg = _material_props(material)
    part_vol_mm3 = _part_volume_mm3(part_aabb)

    if is_shaft_like:
        # Round bar: diameter = circumscribed circle of cross-section (W×H)
        cross_diag = math.sqrt(req_W ** 2 + req_H ** 2)
        stock_dia = _next_standard(cross_diag, _ROUND_DIAMETERS_MM)
        stock_len = _next_standard(req_L, _STD_LENGTHS_MM)

        stock_vol_mm3 = math.pi * (stock_dia / 2) ** 2 * stock_len
        waste_pct = max(0.0, (stock_vol_mm3 - part_vol_mm3) / stock_vol_mm3 * 100)

        stock_vol_m3 = stock_vol_mm3 * 1e-9
        stock_mass_kg = stock_vol_m3 * density_kg_m3
        cost_amount = stock_mass_kg * cost_per_kg

        return {
            "ok": True,
            "stock_type": "round_bar",
            "dimensions_mm": {
                "diameter": stock_dia,
                "length": stock_len,
            },
            "part_dims_mm": {"L": L, "W": W, "H": H},
            "waste_pct": round(waste_pct, 1),
            "cost_estimate": {
                "currency": "USD",
                "amount": round(cost_amount, 2),
                "basis": "density × stock_volume × price_per_kg",
                "density_kg_m3": density_kg_m3,
                "stock_mass_kg": round(stock_mass_kg, 4),
                "price_per_kg": cost_per_kg,
            },
            "material_used": material,
            "warnings": warnings,
        }

    elif is_plate_like:
        # Plate: width × length × thickness
        stock_thick = _next_standard(req_H, _RECT_WIDTHS_MM)
        stock_width = _next_standard(req_W, _RECT_WIDTHS_MM)
        stock_length = _next_standard(req_L, _STD_LENGTHS_MM)

        stock_vol_mm3 = stock_thick * stock_width * stock_length
        waste_pct = max(0.0, (stock_vol_mm3 - part_vol_mm3) / stock_vol_mm3 * 100)

        stock_vol_m3 = stock_vol_mm3 * 1e-9
        stock_mass_kg = stock_vol_m3 * density_kg_m3
        cost_amount = stock_mass_kg * cost_per_kg

        return {
            "ok": True,
            "stock_type": "plate",
            "dimensions_mm": {
                "width": stock_width,
                "length": stock_length,
                "thickness": stock_thick,
            },
            "part_dims_mm": {"L": L, "W": W, "H": H},
            "waste_pct": round(waste_pct, 1),
            "cost_estimate": {
                "currency": "USD",
                "amount": round(cost_amount, 2),
                "basis": "density × stock_volume × price_per_kg",
                "density_kg_m3": density_kg_m3,
                "stock_mass_kg": round(stock_mass_kg, 4),
                "price_per_kg": cost_per_kg,
            },
            "material_used": material,
            "warnings": warnings,
        }

    else:
        # Rectangular bar / billet
        stock_H = _next_standard(req_H, _RECT_WIDTHS_MM)
        stock_W = _next_standard(req_W, _RECT_WIDTHS_MM)
        stock_L = _next_standard(req_L, _STD_LENGTHS_MM)

        stock_vol_mm3 = stock_H * stock_W * stock_L
        waste_pct = max(0.0, (stock_vol_mm3 - part_vol_mm3) / stock_vol_mm3 * 100)

        stock_vol_m3 = stock_vol_mm3 * 1e-9
        stock_mass_kg = stock_vol_m3 * density_kg_m3
        cost_amount = stock_mass_kg * cost_per_kg

        return {
            "ok": True,
            "stock_type": "rect_bar",
            "dimensions_mm": {
                "width": stock_W,
                "height": stock_H,
                "length": stock_L,
            },
            "part_dims_mm": {"L": L, "W": W, "H": H},
            "waste_pct": round(waste_pct, 1),
            "cost_estimate": {
                "currency": "USD",
                "amount": round(cost_amount, 2),
                "basis": "density × stock_volume × price_per_kg",
                "density_kg_m3": density_kg_m3,
                "stock_mass_kg": round(stock_mass_kg, 4),
                "price_per_kg": cost_per_kg,
            },
            "material_used": material,
            "warnings": warnings,
        }


# ---------------------------------------------------------------------------
# Public API — recommend_orientation
# ---------------------------------------------------------------------------

# Orientation strategy table: each entry is a candidate rotation described by
# which part axis is mapped to machine +Z (pointing up from the table).
# We enumerate all 6 face orientations.
_ORIENTATIONS: list[dict] = [
    # name, quaternion (w,x,y,z), z_axis_part_face, description
    {"name": "flat_XY",       "quat": (1.0, 0.0, 0.0, 0.0),
     "z_face": "bottom", "description": "Widest face sits on machine table (Z = part height)"},
    {"name": "flat_XY_flip",  "quat": (0.0, 1.0, 0.0, 0.0),
     "z_face": "top",    "description": "Widest face sits on machine table, flipped 180° about X"},
    {"name": "on_edge_XZ",    "quat": (0.707, 0.0, 0.0, 0.707),
     "z_face": "side_W", "description": "Part stands on its width face (Z = part width)"},
    {"name": "on_edge_XZ_f",  "quat": (0.707, 0.0, 0.0, -0.707),
     "z_face": "side_W2","description": "Part stands on opposite width face"},
    {"name": "on_end_YZ",     "quat": (0.707, 0.0, 0.707, 0.0),
     "z_face": "end_L",  "description": "Part stands on its end face (Z = part length)"},
    {"name": "on_end_YZ_f",   "quat": (0.707, 0.0, -0.707, 0.0),
     "z_face": "end_L2", "description": "Part stands on opposite end face"},
]


def _orientation_score(
    L: float, W: float, H: float,
    orientation: dict,
    has_bottom_features: bool,
    has_top_features: bool,
) -> float:
    """Score an orientation (higher = better).

    Criteria (all normalised to [0, 1]):
      1. Minimise Z-machining depth (40 % weight) — prefer shallowest Z extent.
      2. Minimise overhang (30 % weight) — prefer mounting on largest face.
      3. Reduce re-fixturing (30 % weight) — penalise if features appear on
         both the mounted face and the opposite face.

    Quaternion not used in scoring (pure geometric heuristic).
    """
    face = orientation["z_face"]

    # Determine Z depth for this orientation
    if face in ("bottom", "top"):
        z_depth = H
    elif face in ("side_W", "side_W2"):
        z_depth = W
    else:  # end faces
        z_depth = L

    # Maximum possible depth is the longest dimension
    max_depth = max(L, W, H) if max(L, W, H) > 0 else 1.0
    # Inverse of depth → lower depth scores higher
    depth_score = 1.0 - (z_depth / max_depth)

    # Overhang: smallest the z-depth, the larger the base face area
    if face in ("bottom", "top"):
        base_area = L * W
    elif face in ("side_W", "side_W2"):
        base_area = L * H
    else:
        base_area = W * H

    max_area = L * W  # flat orientation has the largest area
    if max_area > 0:
        area_score = base_area / max_area
    else:
        area_score = 0.0
    area_score = min(1.0, area_score)

    # Re-fixturing: penalise if both-face features require separate ops
    refixture_penalty = 0.0
    if has_bottom_features and has_top_features:
        if face in ("bottom", "top"):
            # Flat orientation: must flip to reach the back face
            refixture_penalty = 0.4
        else:
            refixture_penalty = 0.2

    refixture_score = 1.0 - refixture_penalty

    total = 0.40 * depth_score + 0.30 * area_score + 0.30 * refixture_score
    return round(total, 4)


def recommend_orientation(part_geometry_summary: dict[str, Any]) -> dict[str, Any]:
    """Pick the best part orientation to minimise machining cost.

    Parameters
    ----------
    part_geometry_summary : dict
        Keys (all optional; defaults applied when absent):
          aabb         : dict — axis-aligned bounding box (same keys as
                         recommend_stock's part_aabb); required for scoring.
          features     : list[str] — feature names or keywords such as
                         "pocket", "hole", "boss", "slot", "pocket_bottom",
                         "through_hole", "back_face", "thread".
                         Presence of "back_face" or "through_hole" implies
                         features exist on the face opposite the main datum.
          notes        : str — free-text notes (not parsed; passed through).

    Returns
    -------
    dict
        ok              : True
        best_orientation: dict — {name, quaternion [w,x,y,z], description}
        score           : float — composite score (0–1; higher = better)
        all_candidates  : list — all 6 orientations with individual scores
        rationale       : str — human-readable reason
        warnings        : list[str]
    """
    warnings: list[str] = []

    if not isinstance(part_geometry_summary, dict):
        return {"ok": False, "reason": "part_geometry_summary must be a dict"}

    aabb = part_geometry_summary.get("aabb", {})
    features = part_geometry_summary.get("features", [])

    # Parse AABB if provided
    if aabb:
        required_keys = {"min_x", "max_x", "min_y", "max_y", "min_z", "max_z"}
        missing = required_keys - set(aabb.keys())
        if missing:
            warnings.append(f"aabb missing keys {sorted(missing)}; using unit cube")
            L, W, H = 1.0, 1.0, 1.0
        else:
            L, W, H = _aabb_dims(aabb)
    else:
        warnings.append("No aabb provided; using unit cube dims for scoring")
        L, W, H = 1.0, 1.0, 1.0

    # Detect feature flags
    feat_lower = [str(f).lower() for f in features]
    has_bottom_features = any(
        k in feat_lower for k in ("back_face", "bottom_face", "underside")
    )
    has_top_features = any(
        k in feat_lower for k in ("pocket", "boss", "slot", "hole",
                                   "pocket_bottom", "thread", "tap")
    )
    # through_holes imply both-face machining
    if any("through" in f for f in feat_lower):
        has_bottom_features = True
        has_top_features = True

    # Score all orientations
    candidates = []
    for ori in _ORIENTATIONS:
        score = _orientation_score(L, W, H, ori, has_bottom_features, has_top_features)
        candidates.append({
            "name": ori["name"],
            "quaternion": list(ori["quat"]),
            "description": ori["description"],
            "score": score,
        })

    # Sort best first
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    rationale = (
        f"Orientation '{best['name']}' selected (score {best['score']:.3f}). "
        f"Part dims L={L:.1f} W={W:.1f} H={H:.1f} mm. "
        f"Z-depth minimised by placing the {best['name'].replace('_',' ')} face on the table."
    )
    if has_bottom_features:
        rationale += " Note: back-face features detected — a second op (flip) will be needed."

    return {
        "ok": True,
        "best_orientation": {
            "name": best["name"],
            "quaternion": best["quaternion"],
            "description": best["description"],
        },
        "score": best["score"],
        "all_candidates": candidates,
        "rationale": rationale,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public API — fixture_suggestion
# ---------------------------------------------------------------------------

# Clamp method decision table
_CLAMP_RULES: list[dict] = [
    # (condition_fn, method, description)
    {
        "id": "vacuum",
        "desc": "Vacuum fixture (thin plate < 6 mm or low-profile flat part)",
        "min_flat_ratio": 4.0,
        "max_height_mm": 6.0,
    },
    {
        "id": "magnet",
        "desc": "Magnetic chuck (ferrous thin plate)",
        "ferrous_only": True,
        "min_flat_ratio": 3.0,
        "max_height_mm": 15.0,
    },
    {
        "id": "chuck",
        "desc": "3-jaw chuck (round bar / shaft-like parts)",
        "shaft_like": True,
    },
    {
        "id": "soft_jaw",
        "desc": "CNC soft jaws (round or irregular cross-section, short part)",
        "round_or_irregular": True,
        "max_length_ratio": 3.0,
    },
    {
        "id": "fixture_plate_tabs",
        "desc": "Fixture plate with tabs (large flat part needing edge clamping)",
        "min_flat_ratio": 3.0,
    },
    {
        "id": "vise",
        "desc": "Machinist vise (small-to-medium rectangular block)",
        "default": True,
    },
]

_FERROUS_FAMILIES = {"steel", "stainless_steel", "stainless", "cast_iron", "iron"}


def _is_ferrous(material: str) -> bool:
    """Return True if *material* is a ferrous metal."""
    mat_lower = material.lower()
    return any(f in mat_lower for f in ("steel", "iron", "cast_iron", "stainless"))


def fixture_suggestion(
    orientation: dict[str, Any],
    stock_size: dict[str, Any],
    features_to_machine: list[str] | None = None,
) -> dict[str, Any]:
    """Recommend clamping method and clamp positions.

    Parameters
    ----------
    orientation : dict
        Output from ``recommend_orientation`` (must include
        ``best_orientation.name``), or a minimal dict with ``name`` key.
    stock_size : dict
        Output from ``recommend_stock`` (must include ``stock_type`` and
        ``dimensions_mm``), or a minimal dict with those keys.
    features_to_machine : list[str] | None
        Feature keywords (same format as recommend_orientation's features).

    Returns
    -------
    dict
        ok               : True
        clamp_method     : str — "vise" | "chuck" | "soft_jaw" | "vacuum" |
                           "magnet" | "fixture_plate_tabs"
        clamp_description: str
        clamp_positions  : list[str] — textual description of clamp placement
        fixture_tabs     : dict | None — {"qty": int, "position": str} or None
        avoid_zones      : list[str] — regions to keep clear of clamps
        warnings         : list[str]
    """
    warnings: list[str] = []

    if not isinstance(orientation, dict):
        return {"ok": False, "reason": "orientation must be a dict"}
    if not isinstance(stock_size, dict):
        return {"ok": False, "reason": "stock_size must be a dict"}

    features_to_machine = features_to_machine or []

    # Extract orientation name
    ori_name = (
        orientation.get("best_orientation", {}).get("name")
        or orientation.get("name", "flat_XY")
    )

    # Extract stock geometry
    stock_type = stock_size.get("stock_type", "rect_bar")
    dims = stock_size.get("dimensions_mm", {})
    material = stock_size.get("material_used", "")

    # Determine dimensions
    length = float(dims.get("length", dims.get("l", 100.0)))
    if stock_type == "round_bar":
        width = float(dims.get("diameter", 50.0))
        height = float(dims.get("diameter", 50.0))
    else:
        width = float(dims.get("width", dims.get("w", 50.0)))
        height = float(dims.get("height", dims.get("thickness", 25.0)))

    flat_ratio = max(length, width) / max(height, 1.0)
    is_shaft = (stock_type == "round_bar"
                or "shaft" in ori_name
                or length >= 3.0 * width)
    is_thin_plate = height <= 6.0 and flat_ratio >= 4.0
    is_ferrous = _is_ferrous(material)

    feat_lower = [str(f).lower() for f in features_to_machine]
    has_thru_hole = any("through" in f for f in feat_lower)
    has_pocket = any("pocket" in f for f in feat_lower)
    has_large_features = any(
        k in feat_lower for k in ("face_mill", "large_pocket", "contour")
    )

    # Select clamp method
    if is_thin_plate and is_ferrous:
        method = "magnet"
        desc = "Magnetic chuck (ferrous thin plate)"
    elif is_thin_plate and not is_ferrous:
        method = "vacuum"
        desc = "Vacuum fixture (non-ferrous thin plate)"
    elif is_shaft:
        if length / max(width, 1.0) <= 3.0:
            method = "soft_jaw"
            desc = "CNC soft jaws (short round / shaft)"
        else:
            method = "chuck"
            desc = "3-jaw chuck (long round bar / shaft)"
    elif stock_type == "round_bar":
        method = "soft_jaw"
        desc = "CNC soft jaws (round or non-prismatic cross-section)"
    elif flat_ratio >= _PLATE_ASPECT_THRESHOLD and has_large_features:
        method = "fixture_plate_tabs"
        desc = "Fixture plate with fixture tabs (large flat part)"
    else:
        method = "vise"
        desc = "Machinist vise (small-to-medium rectangular block)"

    # Clamp positions
    clamp_positions: list[str] = []
    avoid_zones: list[str] = []

    if method == "vise":
        clamp_positions = [
            f"Jaw 1: secure against fixed jaw along length axis (bottom {min(height, 15):.0f} mm)",
            f"Jaw 2: movable jaw applies clamping force — leave top {max(height - 20, 5):.0f} mm clear",
        ]
        avoid_zones = ["Top face (primary machined face)", "All milled pocket regions"]
        if has_thru_hole:
            clamp_positions.append("Use a parallel bar under part to elevate above vise jaw — clearance for through-holes")
            avoid_zones.append("Through-hole exit zones (bottom face)")

    elif method == "chuck":
        grip_depth = min(length * 0.25, 30.0)
        clamp_positions = [
            f"3-jaw grip on raw stock end, depth {grip_depth:.0f} mm",
            "Steady rest at 2/3 length if overhang > 3× diameter",
        ]
        avoid_zones = [
            "Machined OD features beyond chuck jaw reach",
            "Face-turning region (free end)",
        ]

    elif method == "soft_jaw":
        clamp_positions = [
            "Bore soft jaws to match part OD/profile for full engagement",
            f"Engage min {min(width * 0.4, 20):.0f} mm axial depth in jaws",
        ]
        avoid_zones = ["OD features in jaw contact zone"]

    elif method == "vacuum":
        clamp_positions = [
            "Full-face vacuum pod array on bottom face",
            "Seal perimeter with edge gasket if part < 50 × 50 mm",
        ]
        avoid_zones = ["Bottom face (vacuum contact surface)"]
        if has_thru_hole:
            warnings.append("Through-holes will breach vacuum seal — use O-ring plugs or switch to clamps")

    elif method == "magnet":
        clamp_positions = [
            "Magnetic chuck: full-face contact, demagnetise after machining",
        ]
        avoid_zones = ["Bottom face (magnetic contact surface)"]

    elif method == "fixture_plate_tabs":
        tab_qty = max(2, int(length / 100))
        tab_spacing = length / (tab_qty + 1)
        clamp_positions = [
            f"Fixture plate dowel-pinned to table",
            f"{tab_qty} fixture tabs at {tab_spacing:.0f} mm spacing along length",
            "Clamp bolts in T-slots at each tab location",
        ]
        avoid_zones = ["Tab locations (cut last in operation)", "Top face features"]
    else:
        clamp_positions = ["Standard clamping per shop SOP"]
        avoid_zones = []

    # Fixture tab recommendation
    fixture_tabs: dict | None = None
    if method == "fixture_plate_tabs":
        tab_qty = max(2, int(length / 100))
        fixture_tabs = {
            "qty": tab_qty,
            "position": f"Evenly spaced along length at {length / (tab_qty + 1):.0f} mm intervals",
            "tab_width_mm": max(3.0, min(6.0, height * 0.2)),
            "tab_height_mm": max(1.0, min(3.0, height * 0.1)),
            "note": "Tab roots machined last; break off and file flush after part removal",
        }

    return {
        "ok": True,
        "clamp_method": method,
        "clamp_description": desc,
        "clamp_positions": clamp_positions,
        "fixture_tabs": fixture_tabs,
        "avoid_zones": avoid_zones,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public API — setup_sheet
# ---------------------------------------------------------------------------

def setup_sheet(
    stock: dict[str, Any],
    orientation: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Produce a setup-sheet dict for the machinist.

    Parameters
    ----------
    stock : dict
        Output from ``recommend_stock``.
    orientation : dict
        Output from ``recommend_orientation``.
    fixture : dict
        Output from ``fixture_suggestion``.

    Returns
    -------
    dict
        ok              : True
        title           : str
        stock_summary   : str — one-line stock description
        orientation_note: str — how to orient the part on the table
        zero_point      : str — recommended datum/zero location
        clamping_note   : str — one-line clamping summary
        clamp_positions : list[str]
        avoid_zones     : list[str]
        fixture_tabs    : dict | None
        text_diagram    : str — ASCII art showing stock orientation and clamp
        warnings        : list[str]
    """
    warnings: list[str] = []

    if not isinstance(stock, dict):
        return {"ok": False, "reason": "stock must be a dict"}
    if not isinstance(orientation, dict):
        return {"ok": False, "reason": "orientation must be a dict"}
    if not isinstance(fixture, dict):
        return {"ok": False, "reason": "fixture must be a dict"}

    # Stock summary
    dims = stock.get("dimensions_mm", {})
    stock_type = stock.get("stock_type", "unknown")
    material = stock.get("material_used", "unknown material")

    if stock_type == "round_bar":
        stock_summary = (
            f"Round bar  ⌀{dims.get('diameter', '?')} × {dims.get('length', '?')} mm  "
            f"[{material}]  waste {stock.get('waste_pct', '?')}%"
        )
    elif stock_type == "plate":
        stock_summary = (
            f"Plate  {dims.get('width', '?')} × {dims.get('length', '?')} × "
            f"{dims.get('thickness', '?')} mm  [{material}]  "
            f"waste {stock.get('waste_pct', '?')}%"
        )
    else:
        stock_summary = (
            f"Rect bar  {dims.get('width', '?')} × {dims.get('height', '?')} × "
            f"{dims.get('length', '?')} mm  [{material}]  "
            f"waste {stock.get('waste_pct', '?')}%"
        )

    # Orientation note
    best_ori = orientation.get("best_orientation", {})
    ori_name = best_ori.get("name", orientation.get("name", "flat_XY"))
    ori_desc = best_ori.get("description", "")
    orientation_note = f"{ori_name}: {ori_desc}" if ori_desc else ori_name

    # Zero point recommendation
    zero_point = (
        "Machine zero: lower-left front corner of stock (X0 Y0 Z0 at top face), "
        "Z=0 set to top of stock after facing pass."
    )
    if stock_type == "round_bar":
        zero_point = (
            "Machine zero: spindle centreline (X0 Y0), Z0 at part face after facing."
        )

    # Clamping note
    clamp_method = fixture.get("clamp_method", "vise")
    clamp_desc = fixture.get("clamp_description", "")
    clamping_note = f"{clamp_method.upper()}: {clamp_desc}"

    # Clamp positions and avoid zones
    clamp_positions = fixture.get("clamp_positions", [])
    avoid_zones = fixture.get("avoid_zones", [])
    fixture_tabs = fixture.get("fixture_tabs")

    # Collect warnings from sub-functions
    for d in (stock, orientation, fixture):
        warnings.extend(d.get("warnings", []))

    # Cost info
    cost = stock.get("cost_estimate", {})
    cost_line = ""
    if cost:
        cost_line = (
            f"  Estimated stock cost: USD {cost.get('amount', 'N/A')}  "
            f"(mass {cost.get('stock_mass_kg', 'N/A')} kg @ "
            f"${cost.get('price_per_kg', 'N/A')}/kg)"
        )

    # ASCII text diagram
    if stock_type == "round_bar":
        dia = dims.get("diameter", 50)
        length_val = dims.get("length", 100)
        diagram = (
            "  SETUP DIAGRAM (round bar, chuck/soft-jaw)\n"
            "  " + "=" * 50 + "\n"
            f"  [ CHUCK ]--[{'~' * 20}]-- ⌀{dia} × {length_val} mm\n"
            "             ↑ part held here            ↑ free end (face here)\n"
            "  X0 Y0 = spindle CL;  Z0 = top face after facing\n"
            "  " + "=" * 50
        )
    elif stock_type == "plate":
        w = dims.get("width", 100)
        t = dims.get("thickness", 10)
        l_val = dims.get("length", 250)
        diagram = (
            "  SETUP DIAGRAM (plate)\n"
            "  " + "=" * 50 + "\n"
            f"  |{'─' * 20}| ← {w} mm wide\n"
            f"  | PART FACE (Z+) |\n"
            f"  |{'═' * 20}| ← t={t} mm\n"
            f"  (vacuum/magnet/clamp on bottom)\n"
            f"  Length = {l_val} mm\n"
            "  X0 Y0 = lower-left corner;  Z0 = top face\n"
            "  " + "=" * 50
        )
    else:
        w = dims.get("width", 50)
        h = dims.get("height", 30)
        l_val = dims.get("length", 100)
        diagram = (
            "  SETUP DIAGRAM (rect bar / billet)\n"
            "  " + "=" * 50 + "\n"
            f"  ┌{'─' * 20}┐  ← {w} mm wide\n"
            f"  │  PART FACE (Z+)  │\n"
            f"  ├{'─' * 20}┤  H={h} mm\n"
            f"  │  VISE JAWS GRIP  │\n"
            f"  └{'─' * 20}┘\n"
            f"  Length = {l_val} mm (into page)\n"
            "  X0 Y0 = lower-left front corner;  Z0 = top face\n"
            "  " + "=" * 50
        )

    return {
        "ok": True,
        "title": f"CNC Setup Sheet — {material} {stock_type.replace('_', ' ').title()}",
        "stock_summary": stock_summary,
        "orientation_note": orientation_note,
        "zero_point": zero_point,
        "clamping_note": clamping_note,
        "clamp_positions": clamp_positions,
        "avoid_zones": avoid_zones,
        "fixture_tabs": fixture_tabs,
        "text_diagram": diagram,
        "cost_note": cost_line,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# LLM tool registrations
# ---------------------------------------------------------------------------

_recommend_stock_spec = ToolSpec(
    name="cam_recommend_stock",
    description=(
        "Stock-setup wizard: given a part's axis-aligned bounding box and chosen "
        "material, return the closest standard stock size (round bar / rect bar / "
        "plate), material waste %, and cost estimate.\n\n"
        "Standard sizes follow EN 10058/10060 preferred series.  Material lookup "
        "uses the Kerf matsel database (use matsel_list for material names) or "
        "falls back to family keyword matching (aluminum, steel, brass, titanium, "
        "stainless, copper, magnesium, cast_iron, nylon).\n\n"
        "Returns: stock_type, dimensions_mm, waste_pct, cost_estimate "
        "(density × volume × price_per_kg).\n\n"
        "Never raises.  Returns {ok:false, reason} for invalid input."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "part_aabb": {
                "type": "object",
                "description": (
                    "Axis-aligned bounding box of the part in millimetres. "
                    "Required keys: min_x, max_x, min_y, max_y, min_z, max_z."
                ),
                "properties": {
                    "min_x": {"type": "number"},
                    "max_x": {"type": "number"},
                    "min_y": {"type": "number"},
                    "max_y": {"type": "number"},
                    "min_z": {"type": "number"},
                    "max_z": {"type": "number"},
                },
                "required": ["min_x", "max_x", "min_y", "max_y", "min_z", "max_z"],
            },
            "material": {
                "type": "string",
                "description": (
                    "Material name (e.g. 'Al_6061_T6', 'AISI_4140_QT') or family "
                    "keyword (e.g. 'aluminum', 'steel', 'brass', 'titanium')."
                ),
            },
            "surplus_mm": {
                "type": "number",
                "description": (
                    "Minimum extra material on each face for facing passes (default 2.0 mm)."
                ),
            },
        },
        "required": ["part_aabb", "material"],
    },
)


@register(_recommend_stock_spec, write=False)
async def run_cam_recommend_stock(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    part_aabb = a.get("part_aabb")
    if part_aabb is None:
        return err_payload("part_aabb is required", "BAD_ARGS")
    if not isinstance(part_aabb, dict):
        return err_payload("part_aabb must be an object", "BAD_ARGS")

    material = a.get("material")
    if not material:
        return err_payload("material is required", "BAD_ARGS")

    surplus_mm = a.get("surplus_mm", 2.0)

    result = recommend_stock(part_aabb, material, surplus_mm=surplus_mm)
    if not result.get("ok"):
        return err_payload(result.get("reason", "recommend_stock failed"), "COMPUTATION_ERROR")
    return ok_payload(result)


# -----------

_recommend_orientation_spec = ToolSpec(
    name="cam_recommend_orientation",
    description=(
        "Stock-setup wizard: choose the best part orientation in stock to minimise "
        "Z-depth of machining, limit overhangs on finish features, and reduce "
        "re-fixturing.\n\n"
        "Returns: best_orientation (name + quaternion [w,x,y,z] + description), "
        "composite score (0–1), all 6 candidates with scores, and a text rationale.\n\n"
        "Never raises.  Returns {ok:false, reason} for invalid input."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "part_geometry_summary": {
                "type": "object",
                "description": (
                    "Summary of part geometry.  Keys:\n"
                    "  aabb: {min_x,max_x,min_y,max_y,min_z,max_z} — optional but recommended.\n"
                    "  features: list of keyword strings such as 'pocket', 'through_hole', "
                    "'boss', 'slot', 'back_face', 'thread'.  'through_hole' and 'back_face' "
                    "imply second-op flip needed.\n"
                    "  notes: free-text (passed through)."
                ),
            },
        },
        "required": ["part_geometry_summary"],
    },
)


@register(_recommend_orientation_spec, write=False)
async def run_cam_recommend_orientation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pgs = a.get("part_geometry_summary")
    if pgs is None:
        return err_payload("part_geometry_summary is required", "BAD_ARGS")

    result = recommend_orientation(pgs)
    if not result.get("ok"):
        return err_payload(result.get("reason", "recommend_orientation failed"), "COMPUTATION_ERROR")
    return ok_payload(result)


# -----------

_fixture_suggestion_spec = ToolSpec(
    name="cam_fixture_suggestion",
    description=(
        "Stock-setup wizard: given a part orientation and stock size, suggest the "
        "optimal clamping method (vise / 3-jaw chuck / soft-jaw / fixture-plate-tabs / "
        "vacuum / magnetic chuck), recommend clamp positions while avoiding machined "
        "regions, and return fixture-tab parameters if needed.\n\n"
        "Never raises.  Returns {ok:false, reason} for invalid input."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "orientation": {
                "type": "object",
                "description": "Output dict from cam_recommend_orientation (or minimal {name: str}).",
            },
            "stock_size": {
                "type": "object",
                "description": "Output dict from cam_recommend_stock (or minimal {stock_type, dimensions_mm, material_used}).",
            },
            "features_to_machine": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of feature keywords, e.g. ['pocket', 'through_hole', 'boss']. "
                    "Used to identify clamp-avoid zones."
                ),
            },
        },
        "required": ["orientation", "stock_size"],
    },
)


@register(_fixture_suggestion_spec, write=False)
async def run_cam_fixture_suggestion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    orientation = a.get("orientation")
    if orientation is None:
        return err_payload("orientation is required", "BAD_ARGS")
    stock_size = a.get("stock_size")
    if stock_size is None:
        return err_payload("stock_size is required", "BAD_ARGS")

    features = a.get("features_to_machine", [])

    result = fixture_suggestion(orientation, stock_size, features_to_machine=features)
    if not result.get("ok"):
        return err_payload(result.get("reason", "fixture_suggestion failed"), "COMPUTATION_ERROR")
    return ok_payload(result)


# -----------

_setup_sheet_spec = ToolSpec(
    name="cam_setup_sheet",
    description=(
        "Stock-setup wizard: produce a complete CNC setup sheet for the machinist — "
        "stock summary, orientation note, machine zero recommendation, clamping note, "
        "clamp positions, avoid zones, fixture-tab details (if any), and an ASCII "
        "text diagram of the setup.\n\n"
        "Pass the outputs of cam_recommend_stock, cam_recommend_orientation, and "
        "cam_fixture_suggestion directly as the three arguments.\n\n"
        "Never raises.  Returns {ok:false, reason} for invalid input."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stock": {
                "type": "object",
                "description": "Output dict from cam_recommend_stock.",
            },
            "orientation": {
                "type": "object",
                "description": "Output dict from cam_recommend_orientation.",
            },
            "fixture": {
                "type": "object",
                "description": "Output dict from cam_fixture_suggestion.",
            },
        },
        "required": ["stock", "orientation", "fixture"],
    },
)


@register(_setup_sheet_spec, write=False)
async def run_cam_setup_sheet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    stock = a.get("stock")
    orientation = a.get("orientation")
    fixture = a.get("fixture")

    if stock is None:
        return err_payload("stock is required", "BAD_ARGS")
    if orientation is None:
        return err_payload("orientation is required", "BAD_ARGS")
    if fixture is None:
        return err_payload("fixture is required", "BAD_ARGS")

    result = setup_sheet(stock, orientation, fixture)
    if not result.get("ok"):
        return err_payload(result.get("reason", "setup_sheet failed"), "COMPUTATION_ERROR")
    return ok_payload(result)
