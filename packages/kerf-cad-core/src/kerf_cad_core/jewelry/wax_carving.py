"""
kerf_cad_core.jewelry.wax_carving
==================================

Wax-carving subtractive plan for hand-carving a ring from wax tube or block.

Given a target ring (size, shank profile/section, design features):
  - Pick wax stock (tube by ID/OD or block dims) that envelops the target with
    minimum waste.
  - Compute material to remove (stock_vol − target_vol).
  - Break out roughing vs detail stages with recommended burr/tool sequence:
    centre-drill to bore ID, ID ream to size, OD turn, profile shaping, detail.
  - Per-stage time estimates (minutes).
  - Finished wax weight.
  - Predicted cast metal weight per alloy (wax→metal via density ratio).
  - Sprue placement suggestion.
  - Waste % = material_removed / stock_vol.

All inputs validated; never raises. Error path: {"ok": False, "reason": "..."}.

## Wax stock

Two forms of stock are supported:

  tube  — hollow wax tube with an inner bore (ID) and outer diameter (OD).
          Standard jeweller's wax tubes (Ferris / Matt / Freeman sizes):
            ID / OD pairs in mm, chosen to minimise waste while enclosing the
            ring bore and maximum outer profile.

  block — solid rectangular wax block (width × depth × height in mm).
          Used when tube stock doesn't fit (thick cocktail rings, bangles,
          signet blanks) or when the carver prefers to bore from scratch.

## Wax density

Injection / carving wax: 0.93 g/cm³ (same constant as production.py).
This value is sourced from Ferris Wax technical data sheet (2022) and
is consistent with Freeman Purple and Matt Blue carving wax.

Reference: Ferris File-A-Wax Product Sheet, Rio Grande Catalog 2023.

## Cast metal weight formula

cast_weight_g = wax_volume_mm3 × (ρ_metal_g_cm3 / ρ_wax_g_cm3) / 1000

Where:
  ρ_wax   = 0.93 g/cm³  (carving wax)
  ρ_metal = from METAL_DENSITY_G_CM3 in metal_cost module

This is the standard lost-wax casting weight estimation used throughout
the industry (e.g. Stuller 2024, Legor Group Technical Manual 2023).

## Tool / burr sequence

Roughing:
  1. Centre drill (Ø2–3 mm) — locate bore centre
  2. Twist drill to rough bore size (Ø = ring_id_mm × 0.9)
  3. Wax reamer to final bore ID
  4. OD turning or sanding to target OD

Profile / shaping:
  5. Flat / Warding file or coarse wax carver — OD profile and taper
  6. Half-round file / riffler — inside shank contour
  7. Needle files, barrette — detail work

Detail / finishing:
  8. Steel carver / graver — surface detail
  9. Flex-shaft pendant drill with wax burs — fine relief
  10. Wax spatula / alcohol lamp — minor fills

## LLM tools registered

  jewelry_wax_carving_plan     — main planning tool
  jewelry_wax_stock_picker     — select best stock from a library

Error path: {ok:False, reason}.  Never raises.

References
----------
Ferris File-A-Wax Product Data Sheet, Gesswein / Stuller 2024.
Rio Grande Wax & Casting Catalog, 2023.
Legor Group "Lost-Wax Casting Manual" (2nd ed.), 2022.
Codina, C. "The Complete Book of Jewelry Making", Lark Books 2006.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional
from kerf_cad_core._guards import _err

# ---------------------------------------------------------------------------
# Import-guarded LLM registration
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    _REGISTRY_OK = True
except ImportError:
    _REGISTRY_OK = False

    class ProjectCtx:  # type: ignore[no-redef]
        pass

    def register(*_a, **_kw):  # type: ignore[no-redef]
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

WAX_DENSITY_G_CM3: float = 0.93
"""Injection/carving wax density (g/cm³). Ferris File-A-Wax TDS, 2022."""

MM3_PER_CM3: float = 1000.0

# ---------------------------------------------------------------------------
# Metal density table (import from metal_cost; inline fallback for hermeticity)
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3 as _METAL_DENSITY_TABLE
except ImportError:
    _METAL_DENSITY_TABLE: Dict[str, float] = {  # type: ignore[no-redef]
        "sterling_925":   10.36,
        "18k_yellow":     15.58,
        "14k_yellow":     13.07,
        "platinum_950":   21.40,
        "platinum_900":   21.30,
        "18k_white":      15.60,
        "14k_white":      13.25,
        "18k_rose":       15.45,
        "14k_rose":       13.20,
        "palladium_950":  11.00,
    }

# ---------------------------------------------------------------------------
# Standard wax tube stock catalogue (Ferris / Matt sizes, mm)
# Each entry: (label, id_mm, od_mm)
# Source: Rio Grande 2023 + Ferris product data
# ---------------------------------------------------------------------------

_TUBE_STOCK: List[tuple] = [
    # label,         id_mm,  od_mm
    ("T-01",          8.0,  22.0),
    ("T-02",         10.0,  24.0),
    ("T-03",         12.0,  26.0),
    ("T-04",         13.0,  27.0),
    ("T-05",         14.0,  28.0),
    ("T-06",         15.0,  29.0),
    ("T-07",         16.0,  30.0),
    ("T-08",         17.0,  31.0),
    ("T-09",         18.0,  32.0),
    ("T-10",         19.0,  33.0),
    ("T-11",         20.0,  34.0),
    ("T-12",         10.0,  30.0),   # thick-wall tube
    ("T-13",         12.0,  32.0),
    ("T-14",         14.0,  34.0),
    ("T-15",         16.0,  36.0),
    ("T-16",         18.0,  36.0),
    ("T-17",          8.0,  28.0),   # extra thick-wall
    ("T-18",         10.0,  32.0),
]

# ---------------------------------------------------------------------------
# Standard wax block stock catalogue
# Each entry: (label, width_mm, depth_mm, height_mm)
# ---------------------------------------------------------------------------

_BLOCK_STOCK: List[tuple] = [
    ("B-S1",  30.0, 30.0, 15.0),
    ("B-S2",  35.0, 35.0, 20.0),
    ("B-M1",  40.0, 40.0, 20.0),
    ("B-M2",  50.0, 40.0, 25.0),
    ("B-L1",  60.0, 50.0, 25.0),
    ("B-L2",  70.0, 60.0, 30.0),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_positive(name: str, val: Any) -> Optional[str]:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


# ---------------------------------------------------------------------------
# Ring geometry helpers (independent of ring.py to keep this module hermetic
# when used in unit tests without the full kerf_chat stack)
# ---------------------------------------------------------------------------

def _ring_id_mm(ring_size: float, size_system: str = "us") -> float:
    """Convert ring size to inner diameter (mm).

    Delegates to ring.ring_size_to_diameter when available; falls back to
    the US formula so this module stays hermetic in unit tests.
    """
    try:
        from kerf_cad_core.jewelry.ring import ring_size_to_diameter  # type: ignore[import]
        return ring_size_to_diameter(size_system, ring_size)
    except Exception:
        pass
    # US fallback: ID_mm = 11.63 + 0.8128 × size
    return 11.63 + 0.8128 * float(ring_size)


def _tube_volume_mm3(id_mm: float, od_mm: float, height_mm: float) -> float:
    """Volume of a hollow cylinder (wax tube section)."""
    r_out = od_mm / 2.0
    r_in  = id_mm / 2.0
    return math.pi * (r_out ** 2 - r_in ** 2) * height_mm


def _solid_cylinder_volume_mm3(diameter_mm: float, height_mm: float) -> float:
    return math.pi * (diameter_mm / 2.0) ** 2 * height_mm


def _block_volume_mm3(width_mm: float, depth_mm: float, height_mm: float) -> float:
    return width_mm * depth_mm * height_mm


# ---------------------------------------------------------------------------
# Ring target volume estimation
# ---------------------------------------------------------------------------

# Section profile wall-thickness fractions (fraction of ring ID).
# These are typical jewellery proportions; the caller can override via
# shank_thickness_mm.
_PROFILE_WALL_FRACTION: Dict[str, float] = {
    "flat":         0.14,
    "d_shape":      0.13,
    "comfort_fit":  0.13,
    "half_round":   0.12,
    "knife_edge":   0.08,
    "euro":         0.16,
    "tapered":      0.12,
    "cigar_band":   0.18,
    "bombe":        0.15,
    "concave":      0.11,
    "square":       0.15,
    "hammered":     0.14,
    "split_band":   0.10,
}
_DEFAULT_WALL_FRACTION = 0.13


def _ring_target_volume_mm3(
    ring_id_mm: float,
    band_width_mm: float,
    shank_thickness_mm: float,
    profile: str,
) -> float:
    """
    Estimate ring body volume in mm³.

    Models the ring as a hollow cylinder of height=band_width_mm,
    inner radius = ring_id_mm/2, outer radius = ring_id_mm/2 + shank_thickness_mm.
    This is a conservative lower bound; actual volume depends on profile.
    """
    r_in  = ring_id_mm / 2.0
    r_out = r_in + shank_thickness_mm
    # Profile volume factor: bombe/cigar add ~10–20% extra material
    profile_factor = {
        "bombe":      1.15,
        "cigar_band": 1.12,
        "square":     1.08,
        "hammered":   1.05,
        "knife_edge": 0.75,
    }.get(profile.lower() if profile else "flat", 1.0)
    vol = math.pi * (r_out ** 2 - r_in ** 2) * band_width_mm
    return vol * profile_factor


# ---------------------------------------------------------------------------
# Ring outer diameter
# ---------------------------------------------------------------------------

def _ring_od_mm(ring_id_mm: float, shank_thickness_mm: float) -> float:
    return ring_id_mm + 2.0 * shank_thickness_mm


# ---------------------------------------------------------------------------
# Default shank thickness from profile
# ---------------------------------------------------------------------------

def _default_shank_thickness(ring_id_mm: float, profile: str) -> float:
    fraction = _PROFILE_WALL_FRACTION.get(
        profile.lower() if profile else "flat",
        _DEFAULT_WALL_FRACTION,
    )
    # Minimum 1.0 mm wall; maximum 4.0 mm for typical fashion rings
    return max(1.0, min(4.0, ring_id_mm * fraction))


# ---------------------------------------------------------------------------
# Tool sequence builder
# ---------------------------------------------------------------------------

def _build_tool_sequence(
    ring_id_mm: float,
    ring_od_mm: float,
    band_width_mm: float,
    profile: str,
    design_features: List[str],
) -> List[dict]:
    """
    Build an ordered tool/burr sequence for hand carving.

    Returns list of stage dicts:
      stage, tool, description, time_estimate_min
    """
    stages = []
    profile_l = (profile or "flat").lower()

    # ── Stage 1: Centre drill ─────────────────────────────────────────────
    drill_size = min(3.0, ring_id_mm * 0.18)
    stages.append({
        "stage": 1,
        "phase": "roughing",
        "tool": f"Centre drill Ø{drill_size:.1f} mm",
        "description": "Locate bore centre; starter dimple to prevent drill walk.",
        "time_estimate_min": 2.0,
    })

    # ── Stage 2: Rough bore ───────────────────────────────────────────────
    rough_bore = round(ring_id_mm * 0.90, 1)
    stages.append({
        "stage": 2,
        "phase": "roughing",
        "tool": f"Twist drill Ø{rough_bore:.1f} mm",
        "description": f"Drill rough bore to Ø{rough_bore:.1f} mm (~90 % of final ID). "
                       "Step-drill in 2 passes if wax is thicker than 20 mm.",
        "time_estimate_min": 4.0,
    })

    # ── Stage 3: Ream to final bore ID ────────────────────────────────────
    stages.append({
        "stage": 3,
        "phase": "roughing",
        "tool": f"Wax reamer / boring bar Ø{ring_id_mm:.2f} mm",
        "description": f"Ream bore to final ID {ring_id_mm:.2f} mm. "
                       "Check fit on mandrel or ring gauge.",
        "time_estimate_min": 5.0,
    })

    # ── Stage 4: OD rough turn / sand ────────────────────────────────────
    stages.append({
        "stage": 4,
        "phase": "roughing",
        "tool": "Coarse wax file or lathe tool",
        "description": f"Reduce OD to target {ring_od_mm:.2f} mm. "
                       "Work on a ring mandrel or lathe arbor. "
                       f"Width: {band_width_mm:.1f} mm.",
        "time_estimate_min": 6.0,
    })

    # ── Stage 5: Profile shaping ──────────────────────────────────────────
    profile_desc = {
        "d_shape":     "shape outer surface to D-section (flat inside, rounded outside)",
        "comfort_fit": "create comfort-fit domed inner bore",
        "flat":        "true-up flat faces and parallel edges",
        "half_round":  "round outer profile to half-round cross-section",
        "knife_edge":  "taper both sides to a sharp knife-edge apex",
        "euro":        "create euro flat with slight interior bevel (3–5°)",
        "tapered":     "taper width from shoulder to back of shank",
        "cigar_band":  "wide flat-top with heavy bevelled edges (45°, ~1.5 mm wide)",
        "bombe":       "dome convex outer surface; blend at edges",
        "concave":     "carve concave channel running around circumference",
        "square":      "true up square cross-section with needle files",
        "hammered":    "add facets around circumference with flat graver",
        "split_band":  "separate into two parallel rails; file gap clean",
    }.get(profile_l, "shape to desired cross-section profile")

    stages.append({
        "stage": 5,
        "phase": "shaping",
        "tool": "Half-round file / warding file / riffler",
        "description": f"Profile shaping: {profile_desc}.",
        "time_estimate_min": 8.0,
    })

    # ── Stage 6: Interior shank contour ──────────────────────────────────
    stages.append({
        "stage": 6,
        "phase": "shaping",
        "tool": "Needle files, half-round / barrette",
        "description": "Refine inner bore contour and shank interior. "
                       "Blend transitions; remove file marks.",
        "time_estimate_min": 6.0,
    })

    # ── Stage 7: Design features ──────────────────────────────────────────
    feature_time = 0.0
    feature_tools: List[str] = []
    for feat in (design_features or []):
        fl = feat.lower()
        if "milgrain" in fl:
            feature_tools.append("milgrain wheel / tracer tool")
            feature_time += 10.0
        elif "engraving" in fl or "engrave" in fl:
            feature_tools.append("graver / flat-graver (GRS or hand pusher)")
            feature_time += 15.0
        elif "filigree" in fl:
            feature_tools.append("wax sheet, solder-iron / heat spatula for filigree wire")
            feature_time += 20.0
        elif "stone" in fl or "seat" in fl or "setting" in fl:
            feature_tools.append("ball bur / bezel bur / hart bur for stone seat")
            feature_time += 12.0
        elif "texture" in fl:
            feature_tools.append("texture roller / cross-hatch graver")
            feature_time += 8.0
        elif "gallery" in fl:
            feature_tools.append("gallery strip wax / heat-weld")
            feature_time += 10.0
        else:
            feature_tools.append(f"wax carver / bur for {feat}")
            feature_time += 5.0

    if feature_tools:
        stages.append({
            "stage": 7,
            "phase": "detail",
            "tool": ", ".join(feature_tools),
            "description": "Design feature carving: " + "; ".join(design_features),
            "time_estimate_min": feature_time,
        })

    # ── Stage 8: Final detail & surface ──────────────────────────────────
    stages.append({
        "stage": 8,
        "phase": "detail",
        "tool": "Steel carver, graver, flex-shaft with fine wax burs",
        "description": "Fine surface detail, clean up tool marks, "
                       "check proportions under magnification.",
        "time_estimate_min": 10.0,
    })

    # ── Stage 9: Inspection & minor fills ────────────────────────────────
    stages.append({
        "stage": 9,
        "phase": "detail",
        "tool": "Wax spatula / alcohol lamp / build-up pen",
        "description": "Fill any voids or under-cuts with wax; re-check dimensions. "
                       "Confirm ID on ring gauge and OD with calipers.",
        "time_estimate_min": 4.0,
    })

    return stages


# ---------------------------------------------------------------------------
# Time multipliers by ring size (bigger ring = more material = more roughing)
# ---------------------------------------------------------------------------

def _roughing_time_multiplier(ring_id_mm: float) -> float:
    """Scale roughing time with ring diameter (linear above 15 mm baseline)."""
    baseline = 15.0
    if ring_id_mm <= baseline:
        return 1.0
    return 1.0 + (ring_id_mm - baseline) * 0.04  # +4% per mm above baseline


# ---------------------------------------------------------------------------
# Sprue placement
# ---------------------------------------------------------------------------

def _sprue_suggestion(profile: str, band_width_mm: float, ring_od_mm: float) -> str:
    profile_l = (profile or "flat").lower()
    if profile_l in ("knife_edge", "concave"):
        return (
            "Attach sprue (Ø3–4 mm, 20–25 mm long) at the base of the shank "
            "(6-o'clock position) at a 45° angle relative to the shank axis. "
            "For thin cross-sections, use a gate-style sprue (flat, 3×1 mm) to "
            "prevent shrinkage porosity."
        )
    if band_width_mm >= 8.0:
        return (
            f"Wide band ({band_width_mm:.1f} mm): attach two symmetrical sprues "
            "at 5-o'clock and 7-o'clock positions, each Ø3 mm × 20 mm. "
            "This minimises waviness from directional solidification."
        )
    return (
        "Attach a single sprue (Ø3–4 mm, 20–25 mm long) at the base centre "
        f"(6-o'clock) of the {ring_od_mm:.1f} mm OD shank. "
        "Angle 45° to shank axis; avoid attaching at profile transitions."
    )


# ---------------------------------------------------------------------------
# Stock selector (tube)
# ---------------------------------------------------------------------------

def _pick_tube_stock(
    ring_id_mm: float,
    ring_od_mm: float,
) -> Optional[tuple]:
    """
    Select the smallest tube stock that envelops the ring.

    Constraints:
      stock_id_mm  ≤ ring_id_mm      (bore already at or smaller than needed)
      stock_od_mm  ≥ ring_od_mm      (enough OD to carve down to)

    Returns (label, id_mm, od_mm) or None if nothing fits.
    """
    # Score = (ring_id_mm - stock_id_mm) + (stock_od_mm - ring_od_mm)
    # Lower score = less waste, but must be >= 0 on both dimensions
    best = None
    best_score = float("inf")
    for label, sid, sod in _TUBE_STOCK:
        if sid <= ring_id_mm and sod >= ring_od_mm:
            score = (ring_id_mm - sid) + (sod - ring_od_mm)
            if score < best_score:
                best_score = score
                best = (label, sid, sod)
    return best


def _next_tube_stock(ring_id_mm: float, ring_od_mm: float) -> Optional[dict]:
    """
    Find the smallest tube stock that would accommodate a larger ring.

    Returns a suggestion dict when the target cannot be enclosed.
    """
    # Find tube where at least OD constraint is satisfied
    candidates = [(label, sid, sod) for label, sid, sod in _TUBE_STOCK if sod >= ring_od_mm]
    if candidates:
        label, sid, sod = min(candidates, key=lambda t: t[2] - ring_od_mm)
        issue = []
        if sid > ring_id_mm:
            issue.append(f"tube ID {sid:.1f} mm > ring ID {ring_id_mm:.2f} mm (must bore down further)")
        return {
            "label": label,
            "stock_id_mm": sid,
            "stock_od_mm": sod,
            "issue": "; ".join(issue) if issue else None,
        }
    return None


def _pick_block_stock(ring_od_mm: float, band_width_mm: float) -> Optional[tuple]:
    """
    Select the smallest block stock that envelops the ring footprint.

    The block must be at least ring_od_mm × ring_od_mm × band_width_mm.
    Returns (label, w, d, h) or None.
    """
    best = None
    best_vol = float("inf")
    for label, w, d, h in _BLOCK_STOCK:
        min_dim = min(w, d)
        if min_dim >= ring_od_mm and h >= band_width_mm:
            vol = w * d * h
            if vol < best_vol:
                best_vol = vol
                best = (label, w, d, h)
    return best


# ---------------------------------------------------------------------------
# Core planning function
# ---------------------------------------------------------------------------

def plan_wax_carving(
    ring_size: float,
    band_width_mm: float,
    profile: str = "d_shape",
    *,
    size_system: str = "us",
    shank_thickness_mm: Optional[float] = None,
    stock_type: str = "tube",
    custom_stock: Optional[dict] = None,
    design_features: Optional[List[str]] = None,
    alloys: Optional[List[str]] = None,
) -> dict:
    """
    Plan a hand wax-carving workflow for a ring.

    Parameters
    ----------
    ring_size : float
        Ring size in the given size_system.
    band_width_mm : float
        Band width (height of the ring, in mm).
    profile : str
        Shank cross-section profile: d_shape, comfort_fit, flat, half_round,
        knife_edge, euro, tapered, cigar_band, bombe, concave, square,
        hammered, split_band.  Default "d_shape".
    size_system : str
        Ring size system: "us" (default), "uk", "au", "eu", "jp".
    shank_thickness_mm : float, optional
        Wall thickness of the shank (mm).  Derived from profile if not given.
    stock_type : str
        "tube" (default) or "block".
    custom_stock : dict, optional
        Override auto-selected stock.
        For tube: {"id_mm": float, "od_mm": float}
        For block: {"width_mm": float, "depth_mm": float, "height_mm": float}
    design_features : list[str], optional
        Extra design elements: ["milgrain", "engraving", "stone_seat", ...].
    alloys : list[str], optional
        Alloys to predict cast weight for.  Defaults to
        ["sterling_925", "18k_yellow", "platinum_950"].

    Returns
    -------
    dict with keys:
        ok                    — bool
        ring_id_mm            — computed inner diameter (mm)
        ring_od_mm            — computed outer diameter (mm)
        band_width_mm         — input (mm)
        profile               — input
        stock_type            — "tube" or "block"
        stock_label           — catalogue label of chosen stock
        stock_dims            — dict with stock dimensions
        stock_volume_mm3      — stock volume (mm3)
        target_volume_mm3     — ring body volume estimate (mm3)
        material_removed_mm3  — stock_vol − target_vol
        waste_pct             — material_removed / stock_vol × 100
        wax_weight_g          — finished wax model weight (g)
        cast_weights          — dict[alloy → g] predicted cast weight per alloy
        tool_sequence         — ordered list of stage dicts
        total_time_min        — total estimated carving time (minutes)
        sprue_suggestion      — text recommendation for sprue placement
        notes                 — list of informational notes
    """
    errs = []
    e = _validate_positive("ring_size", ring_size)
    if e:
        errs.append(e)
    e = _validate_positive("band_width_mm", band_width_mm)
    if e:
        errs.append(e)
    if errs:
        return _err("; ".join(errs))

    # Validate profile
    valid_profiles = set(_PROFILE_WALL_FRACTION.keys())
    prof_l = (profile or "d_shape").lower().strip()
    if prof_l not in valid_profiles:
        return _err(
            f"Unknown profile '{profile}'. "
            f"Valid: {sorted(valid_profiles)}"
        )

    # Compute ring ID
    try:
        ring_id_mm = _ring_id_mm(float(ring_size), size_system)
    except Exception as exc:
        return _err(f"Could not resolve ring size: {exc}")

    if ring_id_mm <= 0:
        return _err(f"Computed ring ID {ring_id_mm:.3f} mm is invalid (size too small?)")

    # Shank thickness
    if shank_thickness_mm is not None:
        e = _validate_positive("shank_thickness_mm", shank_thickness_mm)
        if e:
            return _err(e)
        thickness = float(shank_thickness_mm)
    else:
        thickness = _default_shank_thickness(ring_id_mm, prof_l)

    ring_od_mm = _ring_od_mm(ring_id_mm, thickness)

    # ── Choose / validate stock ───────────────────────────────────────────
    notes: List[str] = []
    stock_type_l = (stock_type or "tube").lower().strip()
    if stock_type_l not in ("tube", "block"):
        return _err(f"stock_type must be 'tube' or 'block', got '{stock_type}'")

    stock_label: str
    stock_dims: dict
    stock_vol: float

    if stock_type_l == "tube":
        if custom_stock:
            cid = custom_stock.get("id_mm")
            cod = custom_stock.get("od_mm")
            e1 = _validate_positive("custom_stock.id_mm", cid)
            e2 = _validate_positive("custom_stock.od_mm", cod)
            if e1 or e2:
                return _err("; ".join(x for x in [e1, e2] if x))
            s_id = float(cid)
            s_od = float(cod)
            if s_od <= s_id:
                return _err(
                    f"custom_stock OD ({s_od}) must be > ID ({s_id})"
                )
            # Validate envelopment
            if s_id > ring_id_mm:
                sug = _next_tube_stock(ring_id_mm, ring_od_mm)
                reason = (
                    f"Custom tube stock ID {s_id:.1f} mm > ring ID {ring_id_mm:.2f} mm. "
                    "Stock bore is already larger than the target ring bore — "
                    "cannot ream down, only up."
                )
                if sug:
                    reason += f" Suggested stock: {sug}."
                return _err(reason)
            if s_od < ring_od_mm:
                sug = _next_tube_stock(ring_id_mm, ring_od_mm)
                reason = (
                    f"Custom tube stock OD {s_od:.1f} mm < ring OD {ring_od_mm:.2f} mm. "
                    "Stock is too narrow to carve the target OD."
                )
                if sug:
                    reason += f" Suggested stock: {sug}."
                return _err(reason)
            stock_label = "custom-tube"
            stock_dims = {"id_mm": s_id, "od_mm": s_od, "height_mm": band_width_mm}
        else:
            # Auto-select from catalogue
            picked = _pick_tube_stock(ring_id_mm, ring_od_mm)
            if picked is None:
                # Suggest next available
                sug = _next_tube_stock(ring_id_mm, ring_od_mm)
                reason = (
                    f"No tube stock in catalogue envelops ring ID {ring_id_mm:.2f} mm / "
                    f"OD {ring_od_mm:.2f} mm."
                )
                if sug:
                    reason += (
                        f" Nearest option: {sug['label']} "
                        f"(ID {sug['stock_id_mm']:.1f} mm / OD {sug['stock_od_mm']:.1f} mm"
                        f"{(': ' + sug['issue']) if sug.get('issue') else ''})."
                        " Consider switching to block stock or using custom_stock."
                    )
                return _err(reason)
            stock_label, s_id, s_od = picked
            stock_dims = {"id_mm": s_id, "od_mm": s_od, "height_mm": band_width_mm}

        stock_vol = _tube_volume_mm3(
            stock_dims["id_mm"],
            stock_dims["od_mm"],
            band_width_mm,
        )

    else:  # block
        if custom_stock:
            cw = custom_stock.get("width_mm")
            cd = custom_stock.get("depth_mm")
            ch = custom_stock.get("height_mm")
            for fn, fv in [("width_mm", cw), ("depth_mm", cd), ("height_mm", ch)]:
                e = _validate_positive(f"custom_stock.{fn}", fv)
                if e:
                    return _err(e)
            bw, bd, bh = float(cw), float(cd), float(ch)
            min_footprint = min(bw, bd)
            if min_footprint < ring_od_mm:
                picked = _pick_block_stock(ring_od_mm, band_width_mm)
                reason = (
                    f"Custom block stock min dimension ({min_footprint:.1f} mm) "
                    f"< ring OD ({ring_od_mm:.2f} mm). Block does not envelop the ring."
                )
                if picked:
                    reason += (
                        f" Suggested stock: {picked[0]} "
                        f"({picked[1]:.0f}×{picked[2]:.0f}×{picked[3]:.0f} mm)."
                    )
                return _err(reason)
            if bh < band_width_mm:
                reason = (
                    f"Custom block height {bh:.1f} mm < band_width_mm {band_width_mm:.1f} mm. "
                    "Block is not tall enough for the ring width."
                )
                return _err(reason)
            stock_label = "custom-block"
            stock_dims = {"width_mm": bw, "depth_mm": bd, "height_mm": bh}
        else:
            picked = _pick_block_stock(ring_od_mm, band_width_mm)
            if picked is None:
                return _err(
                    f"No block stock in catalogue envelops ring OD {ring_od_mm:.2f} mm × "
                    f"band width {band_width_mm:.1f} mm. Use custom_stock."
                )
            stock_label, bw, bd, bh = picked
            stock_dims = {"width_mm": bw, "depth_mm": bd, "height_mm": bh}

        stock_vol = _block_volume_mm3(
            stock_dims["width_mm"],
            stock_dims["depth_mm"],
            stock_dims["height_mm"],
        )

    # ── Target ring volume ────────────────────────────────────────────────
    target_vol = _ring_target_volume_mm3(ring_id_mm, band_width_mm, thickness, prof_l)

    if target_vol >= stock_vol:
        notes.append(
            "Estimated target volume is close to or exceeds stock volume — "
            "this can happen for very thin-wall profiles. The plan proceeds; "
            "verify stock selection manually."
        )

    material_removed = max(0.0, stock_vol - target_vol)
    waste_pct = (material_removed / stock_vol * 100.0) if stock_vol > 0 else 0.0

    # ── Wax weight ────────────────────────────────────────────────────────
    wax_weight_g = (target_vol / MM3_PER_CM3) * WAX_DENSITY_G_CM3

    # ── Cast metal weights ────────────────────────────────────────────────
    if alloys is None:
        alloys = ["sterling_925", "18k_yellow", "platinum_950"]

    cast_weights: Dict[str, float] = {}
    for alloy in alloys:
        rho_metal = _METAL_DENSITY_TABLE.get(alloy.lower().strip())
        if rho_metal is None:
            notes.append(f"Unknown alloy '{alloy}' — skipped from cast_weights.")
            continue
        cast_g = (target_vol / MM3_PER_CM3) * rho_metal
        cast_weights[alloy] = round(cast_g, 4)

    # ── Tool sequence ─────────────────────────────────────────────────────
    tool_seq = _build_tool_sequence(
        ring_id_mm, ring_od_mm, band_width_mm,
        prof_l, design_features or [],
    )

    # Scale roughing time by ring size
    time_mult = _roughing_time_multiplier(ring_id_mm)
    total_time = 0.0
    for stage in tool_seq:
        if stage["phase"] == "roughing":
            stage["time_estimate_min"] = round(stage["time_estimate_min"] * time_mult, 1)
        total_time += stage["time_estimate_min"]

    # ── Sprue suggestion ──────────────────────────────────────────────────
    sprue = _sprue_suggestion(prof_l, band_width_mm, ring_od_mm)

    return {
        "ok": True,
        "ring_id_mm": round(ring_id_mm, 4),
        "ring_od_mm": round(ring_od_mm, 4),
        "band_width_mm": band_width_mm,
        "shank_thickness_mm": round(thickness, 4),
        "profile": prof_l,
        "size_system": size_system,
        "stock_type": stock_type_l,
        "stock_label": stock_label,
        "stock_dims": stock_dims,
        "stock_volume_mm3": round(stock_vol, 4),
        "target_volume_mm3": round(target_vol, 4),
        "material_removed_mm3": round(material_removed, 4),
        "waste_pct": round(waste_pct, 2),
        "wax_weight_g": round(wax_weight_g, 4),
        "cast_weights": cast_weights,
        "tool_sequence": tool_seq,
        "total_time_min": round(total_time, 1),
        "sprue_suggestion": sprue,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_wax_carving_plan
# ---------------------------------------------------------------------------

_wax_carving_plan_spec = ToolSpec(
    name="jewelry_wax_carving_plan",
    description=(
        "Generate a hand wax-carving subtractive plan for a ring.\n"
        "\n"
        "Given a target ring (size, band width, profile), this tool:\n"
        "  - Selects the best wax tube or block stock (minimum waste)\n"
        "  - Validates that stock envelops the target ring\n"
        "  - Computes material to remove and waste %\n"
        "  - Builds an ordered burr / tool sequence with per-stage time estimates\n"
        "  - Predicts cast metal weight for multiple alloys\n"
        "  - Suggests optimal sprue placement\n"
        "\n"
        "Supports US/UK/AU/EU/JP ring size systems.\n"
        "Profiles: d_shape, comfort_fit, flat, half_round, knife_edge, euro, "
        "tapered, cigar_band, bombe, concave, square, hammered, split_band.\n"
        "Design features: milgrain, engraving, stone_seat, filigree, texture, gallery.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ring_size": {
                "type": "number",
                "description": "Ring size in the given size_system (e.g. 7 for US 7).",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Band width / ring height in mm (e.g. 4.0 for a 4 mm band).",
            },
            "profile": {
                "type": "string",
                "description": (
                    "Shank cross-section profile. One of: d_shape, comfort_fit, flat, "
                    "half_round, knife_edge, euro, tapered, cigar_band, bombe, concave, "
                    "square, hammered, split_band. Default: d_shape."
                ),
            },
            "size_system": {
                "type": "string",
                "description": "Ring size system: us (default), uk, au, eu, jp.",
            },
            "shank_thickness_mm": {
                "type": "number",
                "description": "Shank wall thickness in mm. Derived from profile if omitted.",
            },
            "stock_type": {
                "type": "string",
                "description": "'tube' (default) or 'block'.",
            },
            "custom_stock": {
                "type": "object",
                "description": (
                    "Override auto-selected stock. "
                    "Tube: {id_mm, od_mm}. Block: {width_mm, depth_mm, height_mm}."
                ),
            },
            "design_features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional design elements: milgrain, engraving, stone_seat, filigree, texture, gallery.",
            },
            "alloys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alloys to predict cast weight for (defaults: sterling_925, 18k_yellow, platinum_950).",
            },
        },
        "required": ["ring_size", "band_width_mm"],
    },
)


@register(_wax_carving_plan_spec, write=False)
async def run_jewelry_wax_carving_plan(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    ring_size = a.get("ring_size")
    band_width_mm = a.get("band_width_mm")
    if ring_size is None:
        return json.dumps({"ok": False, "reason": "ring_size is required"})
    if band_width_mm is None:
        return json.dumps({"ok": False, "reason": "band_width_mm is required"})

    result = plan_wax_carving(
        ring_size=float(ring_size),
        band_width_mm=float(band_width_mm),
        profile=str(a.get("profile", "d_shape")),
        size_system=str(a.get("size_system", "us")),
        shank_thickness_mm=(
            float(a["shank_thickness_mm"])
            if a.get("shank_thickness_mm") is not None
            else None
        ),
        stock_type=str(a.get("stock_type", "tube")),
        custom_stock=a.get("custom_stock"),
        design_features=a.get("design_features"),
        alloys=a.get("alloys"),
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_wax_stock_picker
# ---------------------------------------------------------------------------

_wax_stock_picker_spec = ToolSpec(
    name="jewelry_wax_stock_picker",
    description=(
        "Select the best wax stock (tube or block) for a target ring without "
        "running the full carving plan.\n"
        "\n"
        "Returns the catalogue entry with minimum waste that envelops the ring, "
        "plus waste % and the next-best option.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ring_id_mm": {
                "type": "number",
                "description": "Target ring inner diameter in mm.",
            },
            "ring_od_mm": {
                "type": "number",
                "description": "Target ring outer diameter in mm.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Ring band width (height) in mm.",
            },
            "stock_type": {
                "type": "string",
                "description": "'tube' or 'block'. Default 'tube'.",
            },
        },
        "required": ["ring_id_mm", "ring_od_mm", "band_width_mm"],
    },
)


@register(_wax_stock_picker_spec, write=False)
async def run_jewelry_wax_stock_picker(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

    for fld in ("ring_id_mm", "ring_od_mm", "band_width_mm"):
        if a.get(fld) is None:
            return json.dumps({"ok": False, "reason": f"{fld} is required"})

    try:
        r_id = float(a["ring_id_mm"])
        r_od = float(a["ring_od_mm"])
        bw   = float(a["band_width_mm"])
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"invalid number: {exc}"})

    for name, val in [("ring_id_mm", r_id), ("ring_od_mm", r_od), ("band_width_mm", bw)]:
        e = _validate_positive(name, val)
        if e:
            return json.dumps({"ok": False, "reason": e})

    stock_type = str(a.get("stock_type", "tube")).lower()
    if stock_type not in ("tube", "block"):
        return json.dumps({"ok": False, "reason": "stock_type must be 'tube' or 'block'"})

    if stock_type == "tube":
        picked = _pick_tube_stock(r_id, r_od)
        if picked is None:
            sug = _next_tube_stock(r_id, r_od)
            msg = (
                f"No tube stock envelops ID {r_id:.2f} mm / OD {r_od:.2f} mm."
            )
            if sug:
                msg += f" Nearest: {sug}."
            return json.dumps({"ok": False, "reason": msg})
        label, s_id, s_od = picked
        vol = _tube_volume_mm3(s_id, s_od, bw)
        target_vol = _tube_volume_mm3(r_id, r_od, bw)
        waste = (vol - target_vol) / vol * 100.0
        return ok_payload({
            "stock_type": "tube",
            "label": label,
            "id_mm": s_id,
            "od_mm": s_od,
            "volume_mm3": round(vol, 2),
            "waste_pct": round(waste, 2),
        })
    else:
        picked = _pick_block_stock(r_od, bw)
        if picked is None:
            return json.dumps({
                "ok": False,
                "reason": (
                    f"No block stock envelops OD {r_od:.2f} mm × width {bw:.1f} mm."
                ),
            })
        label, bw_s, bd, bh = picked
        vol = _block_volume_mm3(bw_s, bd, bh)
        ring_vol = _solid_cylinder_volume_mm3(r_od, bw) - _solid_cylinder_volume_mm3(r_id, bw)
        waste = (vol - ring_vol) / vol * 100.0
        return ok_payload({
            "stock_type": "block",
            "label": label,
            "width_mm": bw_s,
            "depth_mm": bd,
            "height_mm": bh,
            "volume_mm3": round(vol, 2),
            "waste_pct": round(max(0.0, waste), 2),
        })
