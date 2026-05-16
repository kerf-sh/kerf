"""
kerf_cad_core.jewelry.repair
============================

Jewelry repair / restoration estimator.

Produces per-repair estimates with shape::

    {
        "ok": True,
        "repair": "<repair_type>",
        "steps": [...],
        "tools": [...],
        "metal_g": float,
        "labor_min": float,
        "materials_cost": float,
        "price": float,
        "risk_notes": [...],
    }

On invalid input returns ``{"ok": False, "reason": "<message>"}`` — never raises.

## Repair types

ring_size_up      — add an arc of metal equal to the extra circumference gained by
                    going from from_size to to_size (US system).  Metal weight =
                    section_mm2 × Δcircumference × density / 1000.
ring_size_down    — remove metal + compress/reflow shank (no added metal).
half_shank        — replace the bottom half of the ring shank with a new strip.
full_shank        — replace the entire shank.
prong_retip       — re-tip (add metal blobs to worn prong tips); per prong_count.
prong_rebuild     — rebuild entire prong from base; heavier job; per prong_count.
head_replacement  — remove and re-solder a complete prong head or basket.
stone_reset       — reset a loose/removed stone; by setting_type.
chain_solder      — solder a broken chain link (single joint).
rhodium_replate   — rhodium re-plate by surface area; area_mm2 → cost.
refinish_polish   — full refinish and polish; labour-only.
clasp_replacement — remove old clasp, fit and solder a new one.

## Pricing model

    price = materials_cost + labor_cost + markup

Where:
    labor_cost = labor_min / 60 × labor_rate_per_hour
    markup      = (materials_cost + labor_cost) × markup_pct / 100

All monetary values in the caller's currency.  No live prices; caller supplies
metal_price_per_gram and labor_rate_per_hour.

## Heat-sensitive stone risk

Stone families that are vulnerable near a jeweler's torch (≥ 400 °C open flame):
emerald, opal, pearl, tanzanite, turquoise, coral, amber, peridot, topaz,
kunzite, iolite.

When any repair involves soldering / torch work AND the piece contains such a
stone, a risk note is appended.

## LLM tools registered

    jewelry_repair_estimate   — estimate a single repair
    jewelry_repair_quote      — itemised quote for a list of repairs

## Sources

  - Ring-size formulas: Hoover & Strong / kerf ring.py (_US_ID_INTERCEPT = 11.63,
    _US_ID_SLOPE = 0.8128).  Δdiameter = 0.8128 × Δsize_us.
    Δcircumference = π × Δdiameter.
  - Metal density table: kerf metal_cost.py METAL_DENSITY_G_CM3.
  - Rhodium re-plate cost: area × cost_per_mm2; typical shop rate ~$35–$65
    for a standard ring (~1500 mm² exposed surface).  Default $0.025/mm².
  - Labor benchmarks: Stuller Inc. "Repair Pricing Guide" 2024 edition;
    GIA Jeweler's Bench Reference (2nd ed.).
"""

from __future__ import annotations

import json
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Re-use density + price tables from sibling modules
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    METAL_LABELS,
    METAL_PRICE_PRESETS,
)
from kerf_cad_core.jewelry.ring import (
    _US_ID_INTERCEPT,  # 11.63 mm
    _US_ID_SLOPE,      # 0.8128 mm / US size
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PI = math.pi

# US ring-size → inner diameter
# id_mm = _US_ID_INTERCEPT + _US_ID_SLOPE * size
# Δid_mm = _US_ID_SLOPE * Δsize

# Default shank cross-section area (mm²) for a standard comfort-fit band:
# 2 mm wide × 1.5 mm thick = 3 mm²; benchers use ~2–4 mm² as the midpoint.
_DEFAULT_SECTION_MM2: float = 3.0

# Default labor rate (USD per hour)
_DEFAULT_LABOR_RATE_PER_HOUR: float = 75.0

# Default markup on top of materials + labor
_DEFAULT_MARKUP_PCT: float = 40.0

# Solder cost per joint (USD) — small amount of solder + flux
_SOLDER_COST_PER_JOINT: float = 0.50

# Rhodium plate cost per mm² of surface area (USD)
# Typical ring full-plate: $35–$65 for ~1 500 mm² → ~$0.030/mm²
_RHODIUM_COST_PER_MM2: float = 0.025

# Polish/finishing consumable cost per piece (USD)
_POLISH_CONSUMABLE: float = 2.50

# Clasp unit cost (approximate mid-market spring-ring / lobster clasp, USD)
_DEFAULT_CLASP_COST: float = 4.50

# ---------------------------------------------------------------------------
# Heat-sensitive stone families (torch / open-flame risk ≥ 400 °C)
# Source: GIA Jeweler's Bench Reference; Revoire, Aurum Technical Bulletin 9
# ---------------------------------------------------------------------------

_HEAT_SENSITIVE_STONES: frozenset[str] = frozenset([
    "emerald",
    "opal",
    "pearl",
    "tanzanite",
    "turquoise",
    "coral",
    "amber",
    "peridot",
    "topaz",
    "kunzite",
    "iolite",
])

# Repairs that involve torch / open-flame work
_TORCH_REPAIRS: frozenset[str] = frozenset([
    "ring_size_up",
    "ring_size_down",
    "half_shank",
    "full_shank",
    "prong_rebuild",
    "head_replacement",
    "chain_solder",
])

# ---------------------------------------------------------------------------
# Labor benchmarks (minutes) — Stuller 2024 bench time reference
# ---------------------------------------------------------------------------

# ring_size_up / ring_size_down: base time + time per step of size change
_SIZING_BASE_MIN: float = 20.0         # setup, cleanup, polish
_SIZING_PER_SIZE_STEP_MIN: float = 5.0  # additional time per size step

# Half/full shank replacement
_HALF_SHANK_MIN: float = 60.0
_FULL_SHANK_MIN: float = 90.0

# Prong work
_PRONG_RETIP_MIN_PER_PRONG: float = 10.0
_PRONG_REBUILD_MIN_PER_PRONG: float = 20.0

# Head replacement
_HEAD_REPLACEMENT_MIN: float = 45.0

# Stone reset by setting type (minutes)
_STONE_RESET_MIN: dict[str, float] = {
    "prong":    15.0,
    "bezel":    25.0,
    "pave":     12.0,
    "channel":  20.0,
    "flush":    15.0,
    "invisible":30.0,
    "tension":  35.0,
    "bar":      18.0,
}
_STONE_RESET_DEFAULT_MIN: float = 15.0

# Chain solder (single break)
_CHAIN_SOLDER_MIN: float = 10.0

# Rhodium re-plate (includes ultrasonic clean, rhodium bath, rinse, dry)
_RHODIUM_REPLATE_MIN: float = 20.0

# Refinish and polish (full piece)
_REFINISH_POLISH_MIN: float = 25.0

# Clasp replacement
_CLASP_REPLACEMENT_MIN: float = 20.0

# ---------------------------------------------------------------------------
# Steps and tools by repair type
# ---------------------------------------------------------------------------

_REPAIR_STEPS: dict[str, list[str]] = {
    "ring_size_up": [
        "Cut shank at base",
        "Anneal shank",
        "Stretch/mandrel to target size",
        "Solder new metal section at cut",
        "File and blend seam",
        "Re-round on mandrel",
        "Final polish",
    ],
    "ring_size_down": [
        "Cut and remove metal section at shank base",
        "Anneal and compress shank",
        "Solder seam",
        "Re-round on mandrel",
        "File and blend seam",
        "Final polish",
    ],
    "half_shank": [
        "Remove worn lower shank section",
        "Fabricate replacement half-shank strip from stock",
        "Fit and solder new shank section",
        "File, blend, and re-round",
        "Final polish",
    ],
    "full_shank": [
        "Remove entire shank",
        "Fabricate full replacement shank",
        "Fit and solder shank to head/crown",
        "File, blend, and re-round on mandrel",
        "Final polish and re-size if required",
    ],
    "prong_retip": [
        "Clean and assess each prong",
        "Apply solder / pallion to each prong tip",
        "Torch-flow solder onto prong tips",
        "File and shape prong tips",
        "Polish prong tips and check stone security",
    ],
    "prong_rebuild": [
        "Remove remnant prong material",
        "Build up prong from base with solder/metal",
        "File prong to correct profile and height",
        "Check stone seat alignment",
        "Polish rebuilt prongs",
    ],
    "head_replacement": [
        "Assess and remove worn head/basket",
        "Select or fabricate replacement head",
        "Fit and solder head to shank",
        "Check stone alignment and security",
        "File, blend and polish",
    ],
    "stone_reset": [
        "Remove and secure loose stone",
        "Inspect and clean seat",
        "Re-position stone in seat",
        "Apply setting type technique to secure stone",
        "Check alignment and security",
        "Light polish around setting",
    ],
    "chain_solder": [
        "Locate and clean break point",
        "Align chain links at break",
        "Apply solder and torch-flow joint",
        "Quench and clean",
        "Check joint strength",
    ],
    "rhodium_replate": [
        "Ultrasonic clean piece",
        "Steam clean and inspect",
        "Electrolytic pre-clean",
        "Rhodium electroplate bath",
        "Rinse and dry",
        "Inspect coverage",
    ],
    "refinish_polish": [
        "Initial file/gravel wheel to remove scratches",
        "Tripoli rouge to pre-polish",
        "High-polish buff",
        "Steam clean",
        "Inspect finish",
    ],
    "clasp_replacement": [
        "Remove old clasp (cut or open jump ring)",
        "Select replacement clasp",
        "Attach new clasp with new jump ring",
        "Solder jump ring closed",
        "Clean and inspect",
    ],
}

_REPAIR_TOOLS: dict[str, list[str]] = {
    "ring_size_up": ["ring mandrel", "rawhide mallet", "saw frame", "solder pick",
                     "torch", "file set", "flex shaft"],
    "ring_size_down": ["ring mandrel", "saw frame", "torch", "solder pick",
                       "file set", "flex shaft"],
    "half_shank": ["saw frame", "rolling mill / sheet stock", "torch", "solder pick",
                   "ring mandrel", "file set", "flex shaft"],
    "full_shank": ["saw frame", "rolling mill / sheet stock", "torch", "solder pick",
                   "ring mandrel", "file set", "flex shaft"],
    "prong_retip": ["torch", "solder pick", "solder pallions", "graver", "flex shaft",
                    "polishing motor"],
    "prong_rebuild": ["torch", "solder pick", "solder pallions", "graver", "flex shaft",
                      "burnisher", "polishing motor"],
    "head_replacement": ["saw frame", "torch", "solder pick", "file set", "flex shaft",
                         "loupe"],
    "stone_reset": ["setting tools", "graver", "burnisher", "loupe", "flex shaft"],
    "chain_solder": ["torch", "third-hand clamp", "solder pick", "binding wire",
                     "file", "polishing motor"],
    "rhodium_replate": ["ultrasonic cleaner", "steam cleaner", "rhodium plating unit",
                        "rectifier", "titanium anode"],
    "refinish_polish": ["flex shaft", "gravel/scuff wheel", "tripoli buff",
                        "rouge buff", "polishing motor", "steam cleaner"],
    "clasp_replacement": ["saw frame / side cutters", "torch", "solder pick",
                          "flat-nose pliers", "loupe"],
}

# ---------------------------------------------------------------------------
# Valid repair type keys
# ---------------------------------------------------------------------------

_VALID_REPAIRS: frozenset[str] = frozenset(_REPAIR_STEPS.keys())

# ---------------------------------------------------------------------------
# Core estimation functions
# ---------------------------------------------------------------------------

def _us_delta_circumference_mm(from_size: float, to_size: float) -> float:
    """
    Compute the change in ring circumference (mm) for a US size change.

    Formula: Δcircumference = π × Δdiameter = π × _US_ID_SLOPE × |to_size − from_size|

    Parameters
    ----------
    from_size : float
        Starting US ring size.
    to_size : float
        Target US ring size.

    Returns
    -------
    float
        Absolute change in inner circumference (mm).  Always non-negative.
    """
    delta_size = abs(to_size - from_size)
    delta_dia_mm = _US_ID_SLOPE * delta_size     # Δid_mm = slope × Δsize
    return _PI * delta_dia_mm                     # Δcirc = π × Δdia


def _ring_size_metal_grams(
    from_size: float,
    to_size: float,
    metal: str,
    section_mm2: float = _DEFAULT_SECTION_MM2,
) -> float:
    """
    Estimate the mass of metal added when sizing a ring up.

    Mass = section_mm2 × Δcircumference_mm × density_g_cm3 / 1000

    Parameters
    ----------
    from_size : float
        Starting US ring size.
    to_size : float
        Target US ring size (must be > from_size for sizing up).
    metal : str
        Metal key from METAL_DENSITY_G_CM3.
    section_mm2 : float
        Cross-sectional area of the shank strip in mm².  Default 3.0 mm².

    Returns
    -------
    float
        Metal mass in grams.
    """
    delta_circ_mm = _us_delta_circumference_mm(from_size, to_size)
    density = METAL_DENSITY_G_CM3.get(metal.strip().lower(), 0.0)
    # volume_mm3 = section_mm2 * delta_circ_mm; convert to cm3 then × density
    volume_cm3 = (section_mm2 * delta_circ_mm) / 1000.0
    return density * volume_cm3


def _heat_risk_notes(repair_type: str, stones: Optional[list[str]]) -> list[str]:
    """
    Return risk notes when torch-based repair is performed near heat-sensitive stones.

    Parameters
    ----------
    repair_type : str
        The repair type key.
    stones : list[str] or None
        Stone types present in the piece (e.g. ["emerald", "diamond"]).

    Returns
    -------
    list[str]
        Zero or more risk note strings.
    """
    if not stones or repair_type not in _TORCH_REPAIRS:
        return []
    notes: list[str] = []
    for stone in stones:
        s = stone.strip().lower()
        if s in _HEAT_SENSITIVE_STONES:
            notes.append(
                f"{stone.title()} is heat-sensitive — protect with heat sink gel / "
                f"wet paper and consider cold-connection alternative to torch work."
            )
    return notes


def estimate_repair(
    repair_type: str,
    metal: str = "18k_yellow",
    metal_price_per_gram: float = 0.0,
    labor_rate_per_hour: float = _DEFAULT_LABOR_RATE_PER_HOUR,
    markup_pct: float = _DEFAULT_MARKUP_PCT,
    stones: Optional[list[str]] = None,
    # --- ring sizing ---
    from_size: float = 0.0,
    to_size: float = 0.0,
    section_mm2: float = _DEFAULT_SECTION_MM2,
    # --- prong work ---
    prong_count: int = 4,
    # --- stone reset ---
    setting_type: str = "prong",
    # --- rhodium ---
    area_mm2: float = 1500.0,
    # --- clasp ---
    clasp_cost: float = _DEFAULT_CLASP_COST,
) -> dict:
    """
    Estimate cost and details for a single jewelry repair.

    Parameters
    ----------
    repair_type : str
        One of: ring_size_up, ring_size_down, half_shank, full_shank,
        prong_retip, prong_rebuild, head_replacement, stone_reset,
        chain_solder, rhodium_replate, refinish_polish, clasp_replacement.
    metal : str
        Alloy key (METAL_DENSITY_G_CM3 keys, e.g. "18k_yellow").
        Used for metal weight and price calculations.
    metal_price_per_gram : float
        Price per gram in caller's currency.  Default 0 (weight-only).
    labor_rate_per_hour : float
        Bench labor rate per hour.  Default $75.
    markup_pct : float
        Markup percentage applied to (materials + labor).  Default 40%.
    stones : list[str], optional
        Stone types present in the piece (for heat-risk assessment).
        E.g. ["emerald", "diamond"]. Default None.
    from_size : float
        Starting US ring size (ring_size_up / ring_size_down).
    to_size : float
        Target US ring size (ring_size_up / ring_size_down).
    section_mm2 : float
        Shank cross-section area mm² (ring_size_up / shank replacements).
        Default 3.0 mm².
    prong_count : int
        Number of prongs to retip or rebuild.  Default 4.
    setting_type : str
        Setting type for stone_reset.  Default "prong".
    area_mm2 : float
        Surface area for rhodium_replate (mm²).  Default 1500 mm².
    clasp_cost : float
        Replacement clasp unit cost.  Default $4.50.

    Returns
    -------
    dict:
        ok             — True on success
        repair         — normalised repair type string
        steps          — list of repair step strings
        tools          — list of required tools
        metal_g        — metal added (grams; 0 for labour-only repairs)
        labor_min      — estimated bench labour (minutes)
        materials_cost — cost of materials (metal + consumables)
        price          — final quoted price (materials + labour + markup)
        risk_notes     — list of risk / caution strings
    """
    rtype = repair_type.strip().lower() if repair_type else ""
    if rtype not in _VALID_REPAIRS:
        return {
            "ok": False,
            "reason": (
                f"Unknown repair_type '{repair_type}'. "
                f"Valid: {sorted(_VALID_REPAIRS)}"
            ),
        }

    metal_key = metal.strip().lower() if metal else "18k_yellow"
    if metal_key not in METAL_DENSITY_G_CM3:
        return {
            "ok": False,
            "reason": (
                f"Unknown metal '{metal}'. "
                f"Valid: {sorted(METAL_DENSITY_G_CM3)}"
            ),
        }

    if metal_price_per_gram < 0:
        return {"ok": False, "reason": "metal_price_per_gram must be >= 0"}
    if labor_rate_per_hour < 0:
        return {"ok": False, "reason": "labor_rate_per_hour must be >= 0"}
    if markup_pct < 0:
        return {"ok": False, "reason": "markup_pct must be >= 0"}

    # ── Metal grams and materials cost ─────────────────────────────────────────
    metal_g: float = 0.0
    materials_cost: float = 0.0

    if rtype == "ring_size_up":
        if to_size <= from_size:
            return {
                "ok": False,
                "reason": "to_size must be greater than from_size for ring_size_up",
            }
        metal_g = _ring_size_metal_grams(from_size, to_size, metal_key, section_mm2)
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "ring_size_down":
        # No metal added; small solder cost to re-seal
        metal_g = 0.0
        materials_cost = _SOLDER_COST_PER_JOINT

    elif rtype == "half_shank":
        # Half-shank strip: π × diameter_avg × section_mm2 / 2
        # Use a mid-range ring diameter (~17 mm, US size ~7) as default
        avg_id_mm = 17.0
        vol_cm3 = (section_mm2 * _PI * avg_id_mm / 2.0) / 1000.0
        density = METAL_DENSITY_G_CM3[metal_key]
        metal_g = density * vol_cm3
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "full_shank":
        # Full shank: π × avg_id × section_mm2
        avg_id_mm = 17.0
        vol_cm3 = (section_mm2 * _PI * avg_id_mm) / 1000.0
        density = METAL_DENSITY_G_CM3[metal_key]
        metal_g = density * vol_cm3
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "prong_retip":
        # Small blobs of metal per prong tip: ~0.02 g per prong
        metal_g_per_prong = 0.02
        metal_g = metal_g_per_prong * prong_count
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "prong_rebuild":
        # More metal per prong: ~0.08 g per prong
        metal_g_per_prong = 0.08
        metal_g = metal_g_per_prong * prong_count
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "head_replacement":
        # New head unit: ~0.5–1.5 g; use average 1.0 g as estimate
        metal_g = 1.0
        materials_cost = metal_g * metal_price_per_gram + _SOLDER_COST_PER_JOINT

    elif rtype == "stone_reset":
        # Labour-only; small consumables cost
        metal_g = 0.0
        materials_cost = _SOLDER_COST_PER_JOINT * 0.5  # minimal flux/consumables

    elif rtype == "chain_solder":
        metal_g = 0.0
        materials_cost = _SOLDER_COST_PER_JOINT

    elif rtype == "rhodium_replate":
        if area_mm2 <= 0:
            return {"ok": False, "reason": "area_mm2 must be positive for rhodium_replate"}
        metal_g = 0.0
        materials_cost = area_mm2 * _RHODIUM_COST_PER_MM2

    elif rtype == "refinish_polish":
        metal_g = 0.0
        materials_cost = _POLISH_CONSUMABLE

    elif rtype == "clasp_replacement":
        metal_g = 0.0
        materials_cost = clasp_cost + _SOLDER_COST_PER_JOINT

    # ── Labor time ─────────────────────────────────────────────────────────────
    labor_min: float = 0.0

    if rtype == "ring_size_up":
        delta_size = abs(to_size - from_size)
        labor_min = _SIZING_BASE_MIN + _SIZING_PER_SIZE_STEP_MIN * delta_size

    elif rtype == "ring_size_down":
        delta_size = abs(to_size - from_size)
        labor_min = _SIZING_BASE_MIN + _SIZING_PER_SIZE_STEP_MIN * delta_size

    elif rtype == "half_shank":
        labor_min = _HALF_SHANK_MIN

    elif rtype == "full_shank":
        labor_min = _FULL_SHANK_MIN

    elif rtype == "prong_retip":
        labor_min = _PRONG_RETIP_MIN_PER_PRONG * prong_count

    elif rtype == "prong_rebuild":
        labor_min = _PRONG_REBUILD_MIN_PER_PRONG * prong_count

    elif rtype == "head_replacement":
        labor_min = _HEAD_REPLACEMENT_MIN

    elif rtype == "stone_reset":
        stype = setting_type.strip().lower() if setting_type else "prong"
        labor_min = _STONE_RESET_MIN.get(stype, _STONE_RESET_DEFAULT_MIN)

    elif rtype == "chain_solder":
        labor_min = _CHAIN_SOLDER_MIN

    elif rtype == "rhodium_replate":
        labor_min = _RHODIUM_REPLATE_MIN

    elif rtype == "refinish_polish":
        labor_min = _REFINISH_POLISH_MIN

    elif rtype == "clasp_replacement":
        labor_min = _CLASP_REPLACEMENT_MIN

    # ── Price ─────────────────────────────────────────────────────────────────
    labor_cost = (labor_min / 60.0) * labor_rate_per_hour
    subtotal = materials_cost + labor_cost
    markup_amount = subtotal * markup_pct / 100.0
    price = subtotal + markup_amount

    # ── Risk notes ────────────────────────────────────────────────────────────
    risk_notes = _heat_risk_notes(rtype, stones)

    return {
        "ok": True,
        "repair": rtype,
        "steps": _REPAIR_STEPS[rtype],
        "tools": _REPAIR_TOOLS[rtype],
        "metal_g": round(metal_g, 5),
        "labor_min": round(labor_min, 2),
        "materials_cost": round(materials_cost, 4),
        "price": round(price, 4),
        "risk_notes": risk_notes,
    }


def estimate_repair_list(
    repairs: list[dict],
    metal: str = "18k_yellow",
    metal_price_per_gram: float = 0.0,
    labor_rate_per_hour: float = _DEFAULT_LABOR_RATE_PER_HOUR,
    markup_pct: float = _DEFAULT_MARKUP_PCT,
    stones: Optional[list[str]] = None,
) -> dict:
    """
    Produce an itemised quote for a list of repairs.

    Parameters
    ----------
    repairs : list[dict]
        Each dict must have ``repair_type`` and may include any per-repair
        kwargs accepted by ``estimate_repair``.
    metal : str
        Default alloy key for all repairs (overrideable per-item).
    metal_price_per_gram : float
        Default metal price per gram for all repairs.
    labor_rate_per_hour : float
        Bench labor rate per hour.
    markup_pct : float
        Markup percentage applied per repair.
    stones : list[str], optional
        Stone types present in the piece (shared for risk assessment).

    Returns
    -------
    dict:
        ok              — True if all repairs succeeded; False if any failed
        line_items      — list of estimate_repair results (one per repair)
        total_metal_g   — sum of metal_g across all repairs
        total_labor_min — sum of labor_min across all repairs
        total_price     — sum of price across all repairs
        errors          — list of {index, repair_type, reason} for failed repairs
    """
    if not isinstance(repairs, list):
        return {"ok": False, "reason": "repairs must be a list of repair spec dicts"}

    line_items: list[dict] = []
    errors: list[dict] = []
    total_metal_g = 0.0
    total_labor_min = 0.0
    total_price = 0.0

    for i, spec in enumerate(repairs):
        if not isinstance(spec, dict):
            errors.append({"index": i, "repair_type": None, "reason": "item must be a dict"})
            line_items.append({"ok": False, "reason": "item must be a dict"})
            continue

        rtype = spec.get("repair_type", "")
        kwargs: dict = {
            "metal": spec.get("metal", metal),
            "metal_price_per_gram": spec.get("metal_price_per_gram", metal_price_per_gram),
            "labor_rate_per_hour": spec.get("labor_rate_per_hour", labor_rate_per_hour),
            "markup_pct": spec.get("markup_pct", markup_pct),
            "stones": spec.get("stones", stones),
            "from_size": spec.get("from_size", 0.0),
            "to_size": spec.get("to_size", 0.0),
            "section_mm2": spec.get("section_mm2", _DEFAULT_SECTION_MM2),
            "prong_count": spec.get("prong_count", 4),
            "setting_type": spec.get("setting_type", "prong"),
            "area_mm2": spec.get("area_mm2", 1500.0),
            "clasp_cost": spec.get("clasp_cost", _DEFAULT_CLASP_COST),
        }

        result = estimate_repair(str(rtype), **kwargs)
        line_items.append(result)

        if result.get("ok"):
            total_metal_g += result["metal_g"]
            total_labor_min += result["labor_min"]
            total_price += result["price"]
        else:
            errors.append({
                "index": i,
                "repair_type": rtype,
                "reason": result.get("reason", "unknown error"),
            })

    return {
        "ok": len(errors) == 0,
        "line_items": line_items,
        "total_metal_g": round(total_metal_g, 5),
        "total_labor_min": round(total_labor_min, 2),
        "total_price": round(total_price, 4),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# LLM tools
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx

    # --- jewelry_repair_estimate -----------------------------------------------

    _repair_estimate_spec = ToolSpec(
        name="jewelry_repair_estimate",
        description=(
            "Estimate cost and detail for a single jewelry repair / restoration job.\n\n"
            "Repair types:\n"
            "  ring_size_up      — add metal arc for size increase (US system);\n"
            "                      metal_g = section_mm2 × π × slope × Δsize × density\n"
            "  ring_size_down    — remove metal, compress shank (no metal added)\n"
            "  half_shank        — replace lower half of ring shank\n"
            "  full_shank        — replace entire ring shank\n"
            "  prong_retip       — re-tip worn prong ends (per prong_count)\n"
            "  prong_rebuild     — rebuild entire prongs from base (per prong_count)\n"
            "  head_replacement  — replace prong head or basket\n"
            "  stone_reset       — reset loose/removed stone by setting_type\n"
            "  chain_solder      — solder a broken chain link\n"
            "  rhodium_replate   — rhodium re-plate; area_mm2 × cost/mm²\n"
            "  refinish_polish   — full refinish and polish\n"
            "  clasp_replacement — replace clasp + solder\n\n"
            "Returns: steps, tools, metal_g, labor_min, materials_cost, price, risk_notes.\n"
            "Heat-sensitive stones (emerald, opal, pearl, tanzanite, etc.) near torch "
            "work trigger risk_notes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repair_type": {
                    "type": "string",
                    "description": (
                        "Repair type key: ring_size_up, ring_size_down, half_shank, "
                        "full_shank, prong_retip, prong_rebuild, head_replacement, "
                        "stone_reset, chain_solder, rhodium_replate, refinish_polish, "
                        "clasp_replacement."
                    ),
                },
                "metal": {
                    "type": "string",
                    "description": "Alloy key, e.g. '18k_yellow', 'sterling_925', 'platinum_950'.",
                },
                "metal_price_per_gram": {
                    "type": "number",
                    "description": "Metal price per gram in your currency (default 0).",
                },
                "labor_rate_per_hour": {
                    "type": "number",
                    "description": "Bench labor rate per hour (default 75).",
                },
                "markup_pct": {
                    "type": "number",
                    "description": "Markup % on (materials + labor). Default 40.",
                },
                "stones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Stone types present in the piece (for heat-risk notes). "
                        "E.g. ['emerald', 'diamond']."
                    ),
                },
                "from_size": {
                    "type": "number",
                    "description": "Starting US ring size (ring_size_up / ring_size_down).",
                },
                "to_size": {
                    "type": "number",
                    "description": "Target US ring size (ring_size_up / ring_size_down).",
                },
                "section_mm2": {
                    "type": "number",
                    "description": "Shank cross-section area mm² (default 3.0).",
                },
                "prong_count": {
                    "type": "integer",
                    "description": "Number of prongs for prong_retip / prong_rebuild (default 4).",
                },
                "setting_type": {
                    "type": "string",
                    "description": "Setting type for stone_reset: prong, bezel, pave, channel, flush, invisible, tension, bar.",
                },
                "area_mm2": {
                    "type": "number",
                    "description": "Surface area (mm²) for rhodium_replate (default 1500).",
                },
                "clasp_cost": {
                    "type": "number",
                    "description": "Replacement clasp unit cost (default 4.50).",
                },
            },
            "required": ["repair_type"],
        },
    )

    @register(_repair_estimate_spec, write=False)
    async def run_jewelry_repair_estimate(ctx: "ProjectCtx", args: bytes) -> str:
        """LLM tool: jewelry_repair_estimate."""
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        repair_type = a.get("repair_type")
        if not repair_type:
            return err_payload("repair_type is required", "BAD_ARGS")

        kwargs: dict = {}
        str_fields = ("metal", "setting_type")
        num_fields = (
            "metal_price_per_gram", "labor_rate_per_hour", "markup_pct",
            "from_size", "to_size", "section_mm2", "area_mm2", "clasp_cost",
        )
        for f in str_fields:
            if f in a:
                kwargs[f] = str(a[f])
        for f in num_fields:
            if f in a:
                try:
                    kwargs[f] = float(a[f])
                except (TypeError, ValueError):
                    return err_payload(f"{f} must be a number", "BAD_ARGS")
        if "prong_count" in a:
            try:
                kwargs["prong_count"] = int(a["prong_count"])
            except (TypeError, ValueError):
                return err_payload("prong_count must be an integer", "BAD_ARGS")
        if "stones" in a:
            sv = a["stones"]
            if not isinstance(sv, list):
                return err_payload("stones must be an array of strings", "BAD_ARGS")
            kwargs["stones"] = [str(s) for s in sv]

        result = estimate_repair(str(repair_type), **kwargs)
        if not result.get("ok"):
            return err_payload(result.get("reason", "estimate failed"), "BAD_ARGS")
        return ok_payload(result)

    # --- jewelry_repair_quote --------------------------------------------------

    _repair_quote_spec = ToolSpec(
        name="jewelry_repair_quote",
        description=(
            "Itemised quote for a list of repairs on a single piece.\n\n"
            "Each repair in the list can override any per-repair parameter. "
            "Returns line_items[], total_metal_g, total_labor_min, total_price.\n\n"
            "Example repairs list item:\n"
            '  {"repair_type": "prong_retip", "prong_count": 6, "metal": "18k_yellow"}'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repairs": {
                    "type": "array",
                    "description": (
                        "List of repair spec dicts. Each must have 'repair_type'; "
                        "other fields are optional overrides."
                    ),
                    "items": {"type": "object"},
                },
                "metal": {
                    "type": "string",
                    "description": "Default alloy key for all repairs.",
                },
                "metal_price_per_gram": {
                    "type": "number",
                    "description": "Default metal price per gram.",
                },
                "labor_rate_per_hour": {
                    "type": "number",
                    "description": "Bench labor rate per hour (default 75).",
                },
                "markup_pct": {
                    "type": "number",
                    "description": "Default markup % (default 40).",
                },
                "stones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Stone types present (shared for risk assessment).",
                },
            },
            "required": ["repairs"],
        },
    )

    @register(_repair_quote_spec, write=False)
    async def run_jewelry_repair_quote(ctx: "ProjectCtx", args: bytes) -> str:
        """LLM tool: jewelry_repair_quote."""
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        repairs_raw = a.get("repairs")
        if repairs_raw is None:
            return err_payload("repairs is required", "BAD_ARGS")
        if not isinstance(repairs_raw, list):
            return err_payload("repairs must be an array", "BAD_ARGS")

        kwargs: dict = {}
        if "metal" in a:
            kwargs["metal"] = str(a["metal"])
        for f in ("metal_price_per_gram", "labor_rate_per_hour", "markup_pct"):
            if f in a:
                try:
                    kwargs[f] = float(a[f])
                except (TypeError, ValueError):
                    return err_payload(f"{f} must be a number", "BAD_ARGS")
        if "stones" in a:
            sv = a["stones"]
            if not isinstance(sv, list):
                return err_payload("stones must be an array of strings", "BAD_ARGS")
            kwargs["stones"] = [str(s) for s in sv]

        result = estimate_repair_list(repairs_raw, **kwargs)
        return ok_payload(result)

    _TOOL_REGISTERED = True

except ImportError:
    _TOOL_REGISTERED = False
