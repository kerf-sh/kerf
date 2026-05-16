"""
kerf_cad_core.jewelry.production
=================================

Jewelry production tools — MatrixGold / RhinoGold "production" tab parity.

Covers:
  - Mold-shrinkage compensation (uniform scale-up per alloy)
  - Sprue & casting-tree layout (auto-place N pieces on a tree)
  - Hallmark / stamp placement (fineness + maker mark on band inner face)
  - Wax/resin and metal weight per piece and per tree
  - Per-piece and batch cost rollup (metal + casting + labour + stones)
  - Finger-size scaling of a finished ring
  - File/polish stock allowance

All functions are pure-Python; no OCCT required.  Shrinkage data is sourced
from the sibling casting_export module so values remain consistent.

## Mold shrinkage compensation

Uniform scale-up:   scale_factor = 1 / (1 - shrinkage_pct / 100)

The wax (or resin) pattern is oversized by this factor so the cast metal
piece lands at the target dimension after solidification.

References: Legor Group alloy data sheets (2023); Platinum Guild International
technical notes; Stuller Inc. alloy reference guide; Revoire P., Aurum
Jewellery Technical Bulletin 12 (2022).

## Sprue diameter heuristic

Empirical bench rule: sprue diameter ≈ 2 × (volume_mm3)^(1/3) / 6

Simplified to: sprue_dia_mm = max(2.0, (volume_mm3 / 1000)^(1/3) × k)

The sprue must be large enough to keep the metal liquid while the thinner
sections solidify (Chvorinov's rule), yet not so large that it wastes
expensive metal.  Industry range: 2 – 6 mm for jewelry pieces.

The formula used here:
    sprue_dia_mm = clamp(2.0, 6.0, 1.5 × volume_mm3^(1/3) / 10)

(Monotonic in volume; calibrated for 200 mm³ → ~2.9 mm, 5000 mm³ → ~5.3 mm)

## Casting-tree layout

A casting tree (button + central sprue trunk + piece sprues) holds N pieces.
Parameters:
  trunk_dia_mm      — main sprue trunk, >= max(piece_sprue_dia)
  runner_spacing_mm — centre-to-centre spacing between pieces (default 8 mm)
  feed_direction    — "bottom_up" or "centrifugal"
  flask_fill_mm     — wax pattern height limit for the investment flask

Tree weight  = Σ(piece volumes × density) + trunk volume × density
Flask yield  = total metal / flask_volume_capacity (informational ratio)

## Hallmark placement spec

Returns a spec dict for recessed-text hallmark on a band inner face:
  fineness_stamp  — "750", "585", "950", etc. mapped from alloy key
  maker_mark      — 4-char maker's mark (user-supplied, default "KERF")
  face            — "inner_band" (default) or user-specified
  depth_mm        — 0.15 mm default (industry standard for laser hallmark)
  text_height_mm  — 0.8 mm default
  position        — "centre" along inner circumference

## Wax/resin and metal weight table

WAX_DENSITY_G_CM3 — typical injection wax for lost-wax casting (0.93 g/cm³)
RESIN_DENSITY_G_CM3 — castable resin (Formlabs Castable Wax, ~1.10 g/cm³)

## File/polish stock allowance

When a piece is oversize by a machining / polish allowance before finishing:
    finished_volume ≈ rough_volume × (1 - 3 × stock_mm / avg_dim_mm)

For ring bands the convention is 0.1–0.3 mm per side; default 0.15 mm.

## LLM tools registered

    jewelry_shrink_compensate        (read — scale factor per alloy)
    jewelry_casting_tree             (read — full tree layout)
    jewelry_hallmark_spec            (read — hallmark placement spec)
    jewelry_production_weights       (read — wax + metal weight table)
    jewelry_batch_cost               (read — per-piece + batch cost rollup)
    jewelry_ring_resize              (read — finger-size rescale)
    jewelry_polish_stock             (read — file/polish stock allowance)
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.jewelry.casting_export import (
    SHRINKAGE_PCT,
    _SHRINKAGE_FALLBACK,
    get_shrinkage_pct,
)
from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    METAL_HALLMARK,
    METAL_LABELS,
    metal_weight,
    casting_cost as _casting_cost,
    labour_cost as _labour_cost,
    stone_cost_line_items as _stone_cost_line_items,
)
from kerf_cad_core.jewelry.ring import ring_size_to_diameter  # for finger-size scaling

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAX_DENSITY_G_CM3: float = 0.93     # injection wax, typical lost-wax casting
RESIN_DENSITY_G_CM3: float = 1.10   # castable resin (Formlabs Castable Wax 40)

# Trunk overhead factor relative to a single piece sprue (empirical)
_TRUNK_OVERHEAD_FACTOR: float = 1.20  # trunk + button add ~20% to single-piece tree
_RUNNER_SPACING_DEFAULT_MM: float = 8.0  # centre-to-centre piece spacing on tree

# Polish stock defaults
_POLISH_STOCK_DEFAULT_MM: float = 0.15  # mm per side, industry default for rings
_POLISH_STOCK_SIDES: int = 3            # outer, top, sides of band cross-section

# Hallmark defaults
_HALLMARK_DEPTH_MM: float = 0.15
_HALLMARK_TEXT_HEIGHT_MM: float = 0.80
_HALLMARK_DEFAULT_MAKER: str = "KERF"

# Sprue diameter clamp limits (mm)
_SPRUE_DIA_MIN_MM: float = 2.0
_SPRUE_DIA_MAX_MM: float = 6.0

# US ring-size inner diameter formula coefficients (from ring.py convention)
_US_RING_BASE_MM: float = 11.63
_US_RING_STEP_MM: float = 0.8128


# ---------------------------------------------------------------------------
# 1. Mold-shrinkage compensation
# ---------------------------------------------------------------------------

def shrink_compensate(
    dimension_mm: float,
    alloy_key: str,
) -> dict:
    """
    Return the wax/resin pattern dimension needed to compensate for casting
    shrinkage for the given alloy.

    Parameters
    ----------
    dimension_mm : float
        Target finished-metal dimension in mm (must be > 0).
    alloy_key : str
        Alloy key from METAL_DENSITY_G_CM3 (e.g. "18k_yellow").

    Returns
    -------
    dict:
        alloy_key        — normalised alloy key
        alloy_label      — human-readable label
        shrinkage_pct    — per-alloy shrinkage % used
        scale_factor     — 1 / (1 - shrinkage_pct/100)
        input_mm         — original dimension
        compensated_mm   — wax/resin pattern dimension (input × scale_factor)
    """
    if dimension_mm <= 0:
        raise ValueError(f"dimension_mm must be > 0, got {dimension_mm}")
    key = alloy_key.strip().lower()
    shrinkage = get_shrinkage_pct(key)
    scale = 1.0 / (1.0 - shrinkage / 100.0)
    return {
        "alloy_key": key,
        "alloy_label": METAL_LABELS.get(key, key),
        "shrinkage_pct": shrinkage,
        "scale_factor": scale,
        "input_mm": dimension_mm,
        "compensated_mm": round(dimension_mm * scale, 6),
    }


# ---------------------------------------------------------------------------
# 2. Sprue diameter heuristic
# ---------------------------------------------------------------------------

def sprue_diameter_mm(volume_mm3: float) -> float:
    """
    Compute recommended sprue diameter (mm) for a piece of the given volume.

    Formula: clamp(2.0, 6.0, 1.5 × volume_mm3^(1/3) / 10)
    Monotonic in volume; never below 2 mm (too thin = cold shut risk) or
    above 6 mm (excessive sprue metal waste for jewelry scale).

    Parameters
    ----------
    volume_mm3 : float
        Volume of the metal body in mm³ (must be > 0).

    Returns
    -------
    float — recommended sprue diameter in mm.
    """
    if volume_mm3 <= 0:
        raise ValueError(f"volume_mm3 must be > 0, got {volume_mm3}")
    raw = 1.5 * (volume_mm3 ** (1.0 / 3.0)) / 10.0
    return round(max(_SPRUE_DIA_MIN_MM, min(_SPRUE_DIA_MAX_MM, raw)), 4)


# ---------------------------------------------------------------------------
# 3. Casting-tree layout
# ---------------------------------------------------------------------------

def casting_tree(
    piece_volume_mm3: float,
    alloy_key: str,
    n_pieces: int = 6,
    runner_spacing_mm: float = _RUNNER_SPACING_DEFAULT_MM,
    feed_direction: str = "bottom_up",
    flask_height_mm: float = 75.0,
    piece_height_mm: float = 20.0,
) -> dict:
    """
    Lay out N identical pieces on a casting tree and return tree metrics.

    Parameters
    ----------
    piece_volume_mm3 : float
        Volume of one metal-body piece in mm³.
    alloy_key : str
        Alloy key from METAL_DENSITY_G_CM3.
    n_pieces : int
        Number of pieces to mount on the tree (>= 1).
    runner_spacing_mm : float
        Centre-to-centre spacing between pieces (default 8 mm).
    feed_direction : str
        "bottom_up" (gravity feed from button) or "centrifugal".
    flask_height_mm : float
        Available height in the investment flask (mm), used for yield
        assessment.  Default 75 mm (standard 2½-inch flask).
    piece_height_mm : float
        Height of a single piece measured along the tree axis (mm).
        Used to compute pieces-per-flask-height and tree length.

    Returns
    -------
    dict:
        alloy_key              — normalised alloy key
        alloy_label            — human-readable label
        n_pieces               — piece count used
        piece_volume_mm3       — individual piece volume
        piece_sprue_dia_mm     — computed sprue diameter per piece
        trunk_dia_mm           — trunk (main sprue) diameter = 1.3 × piece_sprue_dia
        runner_spacing_mm      — spacing used
        feed_direction         — feed direction used
        density_g_cm3          — alloy density
        piece_weight_g         — single piece metal weight (g)
        pieces_weight_g        — total pieces weight (n × piece_weight_g)
        sprue_trunk_volume_mm3 — estimated trunk + button volume
        tree_metal_weight_g    — total tree metal (pieces + trunk)
        tree_length_mm         — estimated length of assembled tree
        flask_height_mm        — flask height supplied
        pieces_fit_in_flask    — how many pieces fit vertically in this flask
        flask_yield_pct        — pieces_weight_g / tree_metal_weight_g × 100
        wax_weight_g           — wax-pattern weight for one piece
        tree_wax_weight_g      — wax-pattern weight for full tree
    """
    if piece_volume_mm3 <= 0:
        raise ValueError(f"piece_volume_mm3 must be > 0, got {piece_volume_mm3}")
    if n_pieces < 1:
        raise ValueError(f"n_pieces must be >= 1, got {n_pieces}")
    if runner_spacing_mm <= 0:
        raise ValueError(f"runner_spacing_mm must be > 0, got {runner_spacing_mm}")
    if flask_height_mm <= 0:
        raise ValueError(f"flask_height_mm must be > 0, got {flask_height_mm}")
    if piece_height_mm <= 0:
        raise ValueError(f"piece_height_mm must be > 0, got {piece_height_mm}")
    key = alloy_key.strip().lower()
    if key not in METAL_DENSITY_G_CM3:
        valid = sorted(METAL_DENSITY_G_CM3)
        raise ValueError(f"Unknown alloy '{alloy_key}'. Valid: {valid}")
    if feed_direction not in ("bottom_up", "centrifugal"):
        raise ValueError(
            f"feed_direction must be 'bottom_up' or 'centrifugal', got '{feed_direction}'"
        )

    density = METAL_DENSITY_G_CM3[key]
    piece_dia_sprue = sprue_diameter_mm(piece_volume_mm3)
    trunk_dia = round(piece_dia_sprue * 1.3, 4)

    # Single piece weight (g)
    piece_weight_g = metal_weight(piece_volume_mm3, metal=key)["grams"]
    pieces_weight_g = piece_weight_g * n_pieces

    # Trunk + button volume estimate:
    # trunk length ~ n_pieces × runner_spacing / 2 (pieces on both sides)
    # button cylinder ~ 3 × trunk_dia height
    trunk_length_mm = n_pieces * runner_spacing_mm / 2.0
    trunk_vol_mm3 = math.pi * (trunk_dia / 2.0) ** 2 * trunk_length_mm
    button_vol_mm3 = math.pi * (trunk_dia / 2.0) ** 2 * (3.0 * trunk_dia)
    sprue_trunk_vol_mm3 = trunk_vol_mm3 + button_vol_mm3
    trunk_weight_g = (sprue_trunk_vol_mm3 / 1000.0) * density

    tree_metal_weight_g = pieces_weight_g + trunk_weight_g
    tree_length_mm = n_pieces * runner_spacing_mm + piece_height_mm

    pieces_fit = max(1, int(flask_height_mm / (piece_height_mm + runner_spacing_mm * 0.5)))
    flask_yield_pct = (pieces_weight_g / tree_metal_weight_g * 100.0) if tree_metal_weight_g > 0 else 0.0

    # Wax weight for one piece and full tree
    wax_weight_g = (piece_volume_mm3 / 1000.0) * WAX_DENSITY_G_CM3
    tree_wax_weight_g = wax_weight_g * n_pieces

    return {
        "alloy_key": key,
        "alloy_label": METAL_LABELS.get(key, key),
        "n_pieces": n_pieces,
        "piece_volume_mm3": piece_volume_mm3,
        "piece_sprue_dia_mm": piece_dia_sprue,
        "trunk_dia_mm": trunk_dia,
        "runner_spacing_mm": runner_spacing_mm,
        "feed_direction": feed_direction,
        "density_g_cm3": density,
        "piece_weight_g": round(piece_weight_g, 4),
        "pieces_weight_g": round(pieces_weight_g, 4),
        "sprue_trunk_volume_mm3": round(sprue_trunk_vol_mm3, 4),
        "tree_metal_weight_g": round(tree_metal_weight_g, 4),
        "tree_length_mm": round(tree_length_mm, 4),
        "flask_height_mm": flask_height_mm,
        "pieces_fit_in_flask": pieces_fit,
        "flask_yield_pct": round(flask_yield_pct, 4),
        "wax_weight_g": round(wax_weight_g, 4),
        "tree_wax_weight_g": round(tree_wax_weight_g, 4),
    }


# ---------------------------------------------------------------------------
# 4. Hallmark / stamp placement spec
# ---------------------------------------------------------------------------

def hallmark_spec(
    alloy_key: str,
    maker_mark: str = _HALLMARK_DEFAULT_MAKER,
    face: str = "inner_band",
    depth_mm: float = _HALLMARK_DEPTH_MM,
    text_height_mm: float = _HALLMARK_TEXT_HEIGHT_MM,
) -> dict:
    """
    Return a hallmark/stamp placement spec for recessed text on a band.

    Parameters
    ----------
    alloy_key : str
        Alloy key from METAL_DENSITY_G_CM3 (determines fineness stamp).
    maker_mark : str
        Maker's mark (max 8 chars).  Default "KERF".
    face : str
        Target face: "inner_band" (default) or any user label.
    depth_mm : float
        Recess depth in mm.  Default 0.15 mm (industry standard for laser).
    text_height_mm : float
        Text cap-height in mm.  Default 0.80 mm.

    Returns
    -------
    dict:
        alloy_key         — normalised alloy key
        alloy_label       — human-readable label
        fineness_stamp    — e.g. "750", "925", "950" (str)
        maker_mark        — maker mark string used
        face              — target face label
        depth_mm          — recess depth
        text_height_mm    — cap-height of text
        position          — "centre" (along inner circumference)
        method            — "laser_engrave" (preferred) or "stamp"
        full_stamp        — combined stamp string e.g. "750 KERF"
    """
    key = alloy_key.strip().lower()
    if key not in METAL_DENSITY_G_CM3:
        valid = sorted(METAL_DENSITY_G_CM3)
        raise ValueError(f"Unknown alloy '{alloy_key}'. Valid: {valid}")
    if depth_mm <= 0:
        raise ValueError(f"depth_mm must be > 0, got {depth_mm}")
    if text_height_mm <= 0:
        raise ValueError(f"text_height_mm must be > 0, got {text_height_mm}")
    maker = str(maker_mark).strip().upper()[:8] or _HALLMARK_DEFAULT_MAKER

    fineness_raw = METAL_HALLMARK.get(key)
    if fineness_raw is not None:
        fineness_stamp = str(fineness_raw)
        full_stamp = f"{fineness_stamp} {maker}"
    else:
        fineness_stamp = "—"
        full_stamp = maker  # Non-precious metals carry only maker mark

    return {
        "alloy_key": key,
        "alloy_label": METAL_LABELS.get(key, key),
        "fineness_stamp": fineness_stamp,
        "maker_mark": maker,
        "face": face,
        "depth_mm": depth_mm,
        "text_height_mm": text_height_mm,
        "position": "centre",
        "method": "laser_engrave",
        "full_stamp": full_stamp,
    }


# ---------------------------------------------------------------------------
# 5. Wax/resin and metal weight per piece and per tree
# ---------------------------------------------------------------------------

def production_weights(
    piece_volume_mm3: float,
    alloy_key: str,
    n_pieces: int = 1,
    material: str = "wax",
) -> dict:
    """
    Return wax/resin and metal weights for one piece and a batch of n_pieces.

    Parameters
    ----------
    piece_volume_mm3 : float
        Volume of one metal-body piece in mm³.
    alloy_key : str
        Alloy key for metal weight calculation.
    n_pieces : int
        Batch size.  Default 1.
    material : str
        Pattern material: "wax" or "resin".  Default "wax".

    Returns
    -------
    dict:
        piece_volume_mm3    — input piece volume
        alloy_key           — normalised alloy key
        alloy_label         — human-readable label
        pattern_material    — "wax" or "resin"
        pattern_density     — pattern material density (g/cm³)
        wax_weight_g        — one piece pattern weight (g)
        metal_weight_g      — one piece metal weight (g)
        n_pieces            — batch size
        batch_wax_weight_g  — total pattern weight for batch
        batch_metal_weight_g — total metal weight for batch
    """
    if piece_volume_mm3 <= 0:
        raise ValueError(f"piece_volume_mm3 must be > 0, got {piece_volume_mm3}")
    if n_pieces < 1:
        raise ValueError(f"n_pieces must be >= 1, got {n_pieces}")
    key = alloy_key.strip().lower()
    if key not in METAL_DENSITY_G_CM3:
        raise ValueError(f"Unknown alloy '{alloy_key}'. Valid: {sorted(METAL_DENSITY_G_CM3)}")
    mat = material.strip().lower()
    if mat == "resin":
        pattern_density = RESIN_DENSITY_G_CM3
        mat_label = "resin"
    elif mat == "wax":
        pattern_density = WAX_DENSITY_G_CM3
        mat_label = "wax"
    else:
        raise ValueError(f"material must be 'wax' or 'resin', got '{material}'")

    volume_cm3 = piece_volume_mm3 / 1000.0
    wax_g = volume_cm3 * pattern_density
    metal_g = metal_weight(piece_volume_mm3, metal=key)["grams"]

    return {
        "piece_volume_mm3": piece_volume_mm3,
        "alloy_key": key,
        "alloy_label": METAL_LABELS.get(key, key),
        "pattern_material": mat_label,
        "pattern_density": pattern_density,
        "wax_weight_g": round(wax_g, 4),
        "metal_weight_g": round(metal_g, 4),
        "n_pieces": n_pieces,
        "batch_wax_weight_g": round(wax_g * n_pieces, 4),
        "batch_metal_weight_g": round(metal_g * n_pieces, 4),
    }


# ---------------------------------------------------------------------------
# 6. Per-piece and batch cost rollup
# ---------------------------------------------------------------------------

def batch_cost(
    piece_volume_mm3: float,
    alloy_key: str,
    n_pieces: int = 1,
    metal_price_per_gram: float = 0.0,
    casting_fee_per_piece: float = 0.0,
    labour_per_piece: float = 0.0,
    stone_cost_per_piece: float = 0.0,
    casting_allowance_pct: float = 15.0,
    markup_pct: float = 0.0,
) -> dict:
    """
    Per-piece and batch cost rollup.

    Parameters
    ----------
    piece_volume_mm3 : float
        Volume of one metal-body piece in mm³.
    alloy_key : str
        Alloy key from METAL_DENSITY_G_CM3.
    n_pieces : int
        Batch size.  Default 1.
    metal_price_per_gram : float
        Metal price per gram (your currency).  Default 0.
    casting_fee_per_piece : float
        Casting house fee per piece (your currency).  Default 0.
    labour_per_piece : float
        Bench labour, setting, finishing per piece.  Default 0.
    stone_cost_per_piece : float
        Stone cost per piece.  Default 0.
    casting_allowance_pct : float
        Sprue/button overhead for metal weight calculation (default 15%).
    markup_pct : float
        Markup/margin applied to subtotal (default 0%).

    Returns
    -------
    dict:
        alloy_key              — normalised alloy key
        alloy_label            — human-readable label
        n_pieces               — batch size
        net_weight_g           — net metal weight per piece (g)
        gross_weight_g         — metal weight incl. casting allowance (g)
        metal_cost_each        — metal cost per piece
        casting_fee_each       — casting fee per piece
        labour_each            — labour per piece
        stone_cost_each        — stone cost per piece
        subtotal_each          — sum of above per piece
        markup_each            — markup on per-piece subtotal
        total_each             — subtotal_each + markup_each
        batch_metal_cost       — metal cost × n_pieces
        batch_casting_fee      — casting_fee × n_pieces
        batch_labour           — labour × n_pieces
        batch_stone_cost       — stone cost × n_pieces
        batch_subtotal         — batch sum before markup
        batch_markup           — markup on batch subtotal
        batch_total            — batch_subtotal + batch_markup
    """
    if piece_volume_mm3 <= 0:
        raise ValueError(f"piece_volume_mm3 must be > 0, got {piece_volume_mm3}")
    if n_pieces < 1:
        raise ValueError(f"n_pieces must be >= 1, got {n_pieces}")
    if metal_price_per_gram < 0:
        raise ValueError(f"metal_price_per_gram must be >= 0, got {metal_price_per_gram}")
    if casting_fee_per_piece < 0:
        raise ValueError(f"casting_fee_per_piece must be >= 0, got {casting_fee_per_piece}")
    if labour_per_piece < 0:
        raise ValueError(f"labour_per_piece must be >= 0, got {labour_per_piece}")
    if stone_cost_per_piece < 0:
        raise ValueError(f"stone_cost_per_piece must be >= 0, got {stone_cost_per_piece}")
    if casting_allowance_pct < 0:
        raise ValueError(f"casting_allowance_pct must be >= 0, got {casting_allowance_pct}")
    if markup_pct < 0:
        raise ValueError(f"markup_pct must be >= 0, got {markup_pct}")
    key = alloy_key.strip().lower()
    if key not in METAL_DENSITY_G_CM3:
        raise ValueError(f"Unknown alloy '{alloy_key}'. Valid: {sorted(METAL_DENSITY_G_CM3)}")

    # Metal cost per piece (via casting_cost helper for consistency)
    from kerf_cad_core.jewelry.metal_cost import casting_cost as _cc
    cost_result = _cc(
        volume_mm3=piece_volume_mm3,
        metal=key,
        metal_price_per_gram=metal_price_per_gram,
        casting_allowance_pct=casting_allowance_pct,
    )
    net_weight_g = cost_result["net_grams"]
    gross_weight_g = cost_result["gross_grams"]
    metal_cost_each = cost_result["metal_cost"]

    subtotal_each = metal_cost_each + casting_fee_per_piece + labour_per_piece + stone_cost_per_piece
    markup_each = subtotal_each * markup_pct / 100.0
    total_each = subtotal_each + markup_each

    batch_subtotal = subtotal_each * n_pieces
    batch_markup = batch_subtotal * markup_pct / 100.0
    batch_total = batch_subtotal + batch_markup

    return {
        "alloy_key": key,
        "alloy_label": METAL_LABELS.get(key, key),
        "n_pieces": n_pieces,
        "net_weight_g": round(net_weight_g, 4),
        "gross_weight_g": round(gross_weight_g, 4),
        "metal_cost_each": round(metal_cost_each, 4),
        "casting_fee_each": round(casting_fee_per_piece, 4),
        "labour_each": round(labour_per_piece, 4),
        "stone_cost_each": round(stone_cost_per_piece, 4),
        "subtotal_each": round(subtotal_each, 4),
        "markup_each": round(markup_each, 4),
        "total_each": round(total_each, 4),
        "batch_metal_cost": round(metal_cost_each * n_pieces, 4),
        "batch_casting_fee": round(casting_fee_per_piece * n_pieces, 4),
        "batch_labour": round(labour_per_piece * n_pieces, 4),
        "batch_stone_cost": round(stone_cost_per_piece * n_pieces, 4),
        "batch_subtotal": round(batch_subtotal, 4),
        "batch_markup": round(batch_markup, 4),
        "batch_total": round(batch_total, 4),
    }


# ---------------------------------------------------------------------------
# 7. Finger-size scaling (resize a finished ring)
# ---------------------------------------------------------------------------

def ring_resize(
    from_size: float,
    to_size: float,
    system: str = "US",
) -> dict:
    """
    Compute the scale factor to resize a finished ring from one size to another.

    The ring inner circumference scales by the ratio of inner diameters,
    which equals the ratio of inner circumferences since C = π·d.

    Parameters
    ----------
    from_size : float
        Current ring size (in the given system).
    to_size : float
        Target ring size.
    system : str
        Size system: "US" (default), "UK", "EU", "JP".

    Returns
    -------
    dict:
        system             — size system used
        from_size          — original size
        to_size            — target size
        from_diameter_mm   — inner diameter at from_size (mm)
        to_diameter_mm     — inner diameter at to_size (mm)
        from_circumference_mm — π × from_diameter_mm
        to_circumference_mm   — π × to_diameter_mm
        scale_factor       — to_diameter_mm / from_diameter_mm
        metal_change_note  — "add_metal" / "remove_metal" / "no_change"
    """
    from_d = ring_size_to_diameter(system, from_size)
    to_d = ring_size_to_diameter(system, to_size)
    scale = to_d / from_d

    if to_d > from_d:
        note = "add_metal"
    elif to_d < from_d:
        note = "remove_metal"
    else:
        note = "no_change"

    return {
        "system": system.upper(),
        "from_size": from_size,
        "to_size": to_size,
        "from_diameter_mm": round(from_d, 4),
        "to_diameter_mm": round(to_d, 4),
        "from_circumference_mm": round(math.pi * from_d, 4),
        "to_circumference_mm": round(math.pi * to_d, 4),
        "scale_factor": round(scale, 6),
        "metal_change_note": note,
    }


# ---------------------------------------------------------------------------
# 8. File/polish stock allowance
# ---------------------------------------------------------------------------

def polish_stock(
    volume_mm3: float,
    avg_dimension_mm: float,
    stock_mm: float = _POLISH_STOCK_DEFAULT_MM,
    sides: int = _POLISH_STOCK_SIDES,
) -> dict:
    """
    Estimate the rough oversize volume and metal weight overhead for file/
    polish stock allowance.

    The piece should be modelled (and cast) slightly oversize so that hand-
    filing, wheel polishing, and surface finishing remove the allowance and
    leave the finished dimension at target.

    Approximation:
        rough_volume ≈ volume_mm3 × (1 + sides × stock_mm / avg_dimension_mm)
        stock_volume  = rough_volume − volume_mm3

    Parameters
    ----------
    volume_mm3 : float
        Finished target volume in mm³.
    avg_dimension_mm : float
        Representative dimension of the piece (e.g. shank width in mm).
        Used to scale the stock volume estimate.
    stock_mm : float
        Stock allowance per side in mm.  Default 0.15 mm.
    sides : int
        Number of sides with stock.  Default 3 (outer face, top, sides).

    Returns
    -------
    dict:
        finished_volume_mm3  — input target volume
        avg_dimension_mm     — representative dimension used
        stock_mm             — per-side allowance
        sides                — sides with stock
        rough_volume_mm3     — recommended rough/cast volume
        stock_volume_mm3     — extra volume due to allowance
        stock_pct            — stock_volume / finished_volume × 100
    """
    if volume_mm3 <= 0:
        raise ValueError(f"volume_mm3 must be > 0, got {volume_mm3}")
    if avg_dimension_mm <= 0:
        raise ValueError(f"avg_dimension_mm must be > 0, got {avg_dimension_mm}")
    if stock_mm < 0:
        raise ValueError(f"stock_mm must be >= 0, got {stock_mm}")
    if sides < 0:
        raise ValueError(f"sides must be >= 0, got {sides}")

    factor = 1.0 + sides * stock_mm / avg_dimension_mm
    rough_vol = volume_mm3 * factor
    stock_vol = rough_vol - volume_mm3
    stock_pct = (stock_vol / volume_mm3) * 100.0 if volume_mm3 > 0 else 0.0

    return {
        "finished_volume_mm3": volume_mm3,
        "avg_dimension_mm": avg_dimension_mm,
        "stock_mm": stock_mm,
        "sides": sides,
        "rough_volume_mm3": round(rough_vol, 4),
        "stock_volume_mm3": round(stock_vol, 4),
        "stock_pct": round(stock_pct, 4),
    }


# ---------------------------------------------------------------------------
# LLM tool specs and runners
# ---------------------------------------------------------------------------

# --- 1. jewelry_shrink_compensate -------------------------------------------

_shrink_compensate_spec = ToolSpec(
    name="jewelry_shrink_compensate",
    description=(
        "Compute mold-shrinkage compensation: the wax or resin pattern dimension "
        "needed to produce the target finished-metal dimension after casting.\n\n"
        "Scale-up factor = 1 / (1 − shrinkage_pct / 100) per alloy.\n\n"
        "Alloy keys: 10k_yellow, 14k_yellow, 18k_yellow, 22k_yellow, 24k_yellow, "
        "10k_white, 14k_white, 18k_white, 22k_white, "
        "10k_rose, 14k_rose, 18k_rose, 22k_rose, "
        "platinum_950, platinum_900, palladium_950, palladium_500, "
        "sterling_925, fine_silver, argentium_935, titanium, brass, bronze.\n\n"
        "Returns: alloy_key, alloy_label, shrinkage_pct, scale_factor, "
        "input_mm, compensated_mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dimension_mm": {
                "type": "number",
                "description": "Target finished-metal dimension in mm (must be > 0).",
            },
            "alloy_key": {
                "type": "string",
                "description": "Alloy key, e.g. '18k_yellow', 'platinum_950', 'sterling_925'.",
            },
        },
        "required": ["dimension_mm", "alloy_key"],
    },
)


@register(_shrink_compensate_spec, write=False)
async def run_jewelry_shrink_compensate(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_shrink_compensate."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    dim = a.get("dimension_mm")
    if dim is None:
        return err_payload("dimension_mm is required", "BAD_ARGS")
    try:
        dim = float(dim)
    except (TypeError, ValueError):
        return err_payload("dimension_mm must be a number", "BAD_ARGS")

    alloy = a.get("alloy_key")
    if not alloy:
        return err_payload("alloy_key is required", "BAD_ARGS")
    alloy_key_norm = str(alloy).strip().lower()
    if alloy_key_norm not in METAL_DENSITY_G_CM3:
        valid = ", ".join(sorted(METAL_DENSITY_G_CM3))
        return err_payload(f"Unknown alloy_key '{alloy}'. Valid: {valid}", "BAD_ARGS")

    try:
        result = shrink_compensate(dim, alloy_key_norm)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"shrink_compensate error: {exc}", "ERROR")

    return ok_payload(result)


# --- 2. jewelry_casting_tree -------------------------------------------------

_casting_tree_spec = ToolSpec(
    name="jewelry_casting_tree",
    description=(
        "Auto-place N identical pieces on a casting tree and return tree metrics.\n\n"
        "Computes: per-piece sprue diameter (monotonic in volume), trunk diameter, "
        "metal weight (pieces + trunk/button), tree length, flask yield %, "
        "and wax pattern weight.\n\n"
        "Returns full tree layout dict. Use this to plan a casting run before "
        "committing to investment flask size and metal purchase."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece_volume_mm3": {
                "type": "number",
                "description": "Volume of one metal-body piece in mm³.",
            },
            "alloy_key": {
                "type": "string",
                "description": "Alloy key, e.g. '18k_yellow'.",
            },
            "n_pieces": {
                "type": "integer",
                "description": "Number of pieces to mount on the tree (default 6).",
            },
            "runner_spacing_mm": {
                "type": "number",
                "description": "Centre-to-centre spacing between pieces in mm (default 8).",
            },
            "feed_direction": {
                "type": "string",
                "description": "'bottom_up' (default) or 'centrifugal'.",
            },
            "flask_height_mm": {
                "type": "number",
                "description": "Available flask height in mm (default 75).",
            },
            "piece_height_mm": {
                "type": "number",
                "description": "Height of one piece along tree axis in mm (default 20).",
            },
        },
        "required": ["piece_volume_mm3", "alloy_key"],
    },
)


@register(_casting_tree_spec, write=False)
async def run_jewelry_casting_tree(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_casting_tree."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    vol = a.get("piece_volume_mm3")
    if vol is None:
        return err_payload("piece_volume_mm3 is required", "BAD_ARGS")
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        return err_payload("piece_volume_mm3 must be a number", "BAD_ARGS")

    alloy = a.get("alloy_key")
    if not alloy:
        return err_payload("alloy_key is required", "BAD_ARGS")

    kwargs: dict[str, Any] = {}
    for field_name, field_type, default in [
        ("n_pieces", int, 6),
        ("runner_spacing_mm", float, _RUNNER_SPACING_DEFAULT_MM),
        ("flask_height_mm", float, 75.0),
        ("piece_height_mm", float, 20.0),
    ]:
        raw = a.get(field_name)
        if raw is not None:
            try:
                kwargs[field_name] = field_type(raw)
            except (TypeError, ValueError):
                return err_payload(f"{field_name} must be a number", "BAD_ARGS")

    feed_dir = a.get("feed_direction", "bottom_up")
    if feed_dir not in ("bottom_up", "centrifugal"):
        return err_payload("feed_direction must be 'bottom_up' or 'centrifugal'", "BAD_ARGS")
    kwargs["feed_direction"] = feed_dir

    try:
        result = casting_tree(vol, str(alloy), **kwargs)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"casting_tree error: {exc}", "ERROR")

    return ok_payload(result)


# --- 3. jewelry_hallmark_spec ------------------------------------------------

_hallmark_spec_spec = ToolSpec(
    name="jewelry_hallmark_spec",
    description=(
        "Return a hallmark/stamp placement spec for a jewelry piece.\n\n"
        "Generates recessed-text hallmark data: fineness stamp (750, 585, 950, "
        "925, etc. from alloy) + maker mark, target face, depth, text height, "
        "and position.  Default face: inner_band.\n\n"
        "Non-precious metals (titanium, brass, bronze) carry only the maker mark.\n\n"
        "Returns: alloy_key, fineness_stamp, maker_mark, face, depth_mm, "
        "text_height_mm, position, method, full_stamp."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alloy_key": {
                "type": "string",
                "description": "Alloy key, e.g. '18k_yellow', 'platinum_950', 'sterling_925'.",
            },
            "maker_mark": {
                "type": "string",
                "description": "Maker's mark (max 8 chars).  Default 'KERF'.",
            },
            "face": {
                "type": "string",
                "description": "Target face label.  Default 'inner_band'.",
            },
            "depth_mm": {
                "type": "number",
                "description": "Recess depth in mm (default 0.15).",
            },
            "text_height_mm": {
                "type": "number",
                "description": "Text cap-height in mm (default 0.80).",
            },
        },
        "required": ["alloy_key"],
    },
)


@register(_hallmark_spec_spec, write=False)
async def run_jewelry_hallmark_spec(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_hallmark_spec."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    alloy = a.get("alloy_key")
    if not alloy:
        return err_payload("alloy_key is required", "BAD_ARGS")

    kwargs: dict[str, Any] = {}
    if "maker_mark" in a:
        kwargs["maker_mark"] = str(a["maker_mark"])
    if "face" in a:
        kwargs["face"] = str(a["face"])
    for field_name in ("depth_mm", "text_height_mm"):
        if field_name in a:
            try:
                kwargs[field_name] = float(a[field_name])
            except (TypeError, ValueError):
                return err_payload(f"{field_name} must be a number", "BAD_ARGS")

    try:
        result = hallmark_spec(str(alloy), **kwargs)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"hallmark_spec error: {exc}", "ERROR")

    return ok_payload(result)


# --- 4. jewelry_production_weights ------------------------------------------

_production_weights_spec = ToolSpec(
    name="jewelry_production_weights",
    description=(
        "Return wax/resin pattern weight and metal weight for one piece and a batch.\n\n"
        "Useful for purchase planning: how much wax to inject; how much metal to melt.\n\n"
        "Pattern material: 'wax' (0.93 g/cm³, injection wax) or "
        "'resin' (1.10 g/cm³, castable resin).\n\n"
        "Returns: wax_weight_g, metal_weight_g, batch_wax_weight_g, "
        "batch_metal_weight_g."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece_volume_mm3": {
                "type": "number",
                "description": "Volume of one piece in mm³.",
            },
            "alloy_key": {
                "type": "string",
                "description": "Alloy key, e.g. '18k_yellow'.",
            },
            "n_pieces": {
                "type": "integer",
                "description": "Batch size (default 1).",
            },
            "material": {
                "type": "string",
                "description": "'wax' or 'resin' (default 'wax').",
            },
        },
        "required": ["piece_volume_mm3", "alloy_key"],
    },
)


@register(_production_weights_spec, write=False)
async def run_jewelry_production_weights(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_production_weights."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    vol = a.get("piece_volume_mm3")
    if vol is None:
        return err_payload("piece_volume_mm3 is required", "BAD_ARGS")
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        return err_payload("piece_volume_mm3 must be a number", "BAD_ARGS")

    alloy = a.get("alloy_key")
    if not alloy:
        return err_payload("alloy_key is required", "BAD_ARGS")

    kwargs: dict[str, Any] = {}
    if "n_pieces" in a:
        try:
            kwargs["n_pieces"] = int(a["n_pieces"])
        except (TypeError, ValueError):
            return err_payload("n_pieces must be an integer", "BAD_ARGS")
    if "material" in a:
        kwargs["material"] = str(a["material"])

    try:
        result = production_weights(vol, str(alloy), **kwargs)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"production_weights error: {exc}", "ERROR")

    return ok_payload(result)


# --- 5. jewelry_batch_cost ---------------------------------------------------

_batch_cost_spec = ToolSpec(
    name="jewelry_batch_cost",
    description=(
        "Per-piece and batch cost rollup: metal + casting fee + labour + stones.\n\n"
        "Decomposes total cost into itemised per-piece and batch totals.\n"
        "metal_price_per_gram defaults to 0 (weight-only mode).\n\n"
        "Returns: metal_cost_each, casting_fee_each, labour_each, stone_cost_each, "
        "subtotal_each, total_each, batch_total, and all batch-level components."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece_volume_mm3": {
                "type": "number",
                "description": "Volume of one piece in mm³.",
            },
            "alloy_key": {
                "type": "string",
                "description": "Alloy key, e.g. '18k_yellow'.",
            },
            "n_pieces": {
                "type": "integer",
                "description": "Batch size (default 1).",
            },
            "metal_price_per_gram": {
                "type": "number",
                "description": "Metal price per gram (your currency, default 0).",
            },
            "casting_fee_per_piece": {
                "type": "number",
                "description": "Casting house fee per piece (default 0).",
            },
            "labour_per_piece": {
                "type": "number",
                "description": "Bench labour + setting + finishing per piece (default 0).",
            },
            "stone_cost_per_piece": {
                "type": "number",
                "description": "Total stone cost per piece (default 0).",
            },
            "casting_allowance_pct": {
                "type": "number",
                "description": "Sprue/button overhead % for metal weight (default 15).",
            },
            "markup_pct": {
                "type": "number",
                "description": "Markup % applied to subtotal (default 0).",
            },
        },
        "required": ["piece_volume_mm3", "alloy_key"],
    },
)


@register(_batch_cost_spec, write=False)
async def run_jewelry_batch_cost(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_batch_cost."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    vol = a.get("piece_volume_mm3")
    if vol is None:
        return err_payload("piece_volume_mm3 is required", "BAD_ARGS")
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        return err_payload("piece_volume_mm3 must be a number", "BAD_ARGS")

    alloy = a.get("alloy_key")
    if not alloy:
        return err_payload("alloy_key is required", "BAD_ARGS")

    kwargs: dict[str, Any] = {}
    if "n_pieces" in a:
        try:
            kwargs["n_pieces"] = int(a["n_pieces"])
        except (TypeError, ValueError):
            return err_payload("n_pieces must be an integer", "BAD_ARGS")
    for field_name in (
        "metal_price_per_gram", "casting_fee_per_piece",
        "labour_per_piece", "stone_cost_per_piece",
        "casting_allowance_pct", "markup_pct",
    ):
        if field_name in a:
            try:
                kwargs[field_name] = float(a[field_name])
            except (TypeError, ValueError):
                return err_payload(f"{field_name} must be a number", "BAD_ARGS")

    try:
        result = batch_cost(vol, str(alloy), **kwargs)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"batch_cost error: {exc}", "ERROR")

    return ok_payload(result)


# --- 6. jewelry_ring_resize --------------------------------------------------

_ring_resize_spec = ToolSpec(
    name="jewelry_ring_resize",
    description=(
        "Compute the scale factor to resize a finished ring from one finger size "
        "to another.\n\n"
        "Inner circumference scales as C = π·d where d = inner diameter.\n"
        "scale_factor = to_diameter / from_diameter.\n\n"
        "Systems: 'US' (default), 'UK', 'EU', 'JP'.\n\n"
        "Returns: from/to diameters, circumferences, scale_factor, and whether "
        "metal must be added or removed."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "from_size": {
                "type": "number",
                "description": "Current ring size (in the given system).",
            },
            "to_size": {
                "type": "number",
                "description": "Target ring size.",
            },
            "system": {
                "type": "string",
                "description": "Size system: 'US' (default), 'UK', 'EU', 'JP'.",
            },
        },
        "required": ["from_size", "to_size"],
    },
)


@register(_ring_resize_spec, write=False)
async def run_jewelry_ring_resize(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_ring_resize."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    from_size = a.get("from_size")
    to_size = a.get("to_size")
    if from_size is None:
        return err_payload("from_size is required", "BAD_ARGS")
    if to_size is None:
        return err_payload("to_size is required", "BAD_ARGS")
    try:
        from_size = float(from_size)
        to_size = float(to_size)
    except (TypeError, ValueError):
        return err_payload("from_size and to_size must be numbers", "BAD_ARGS")

    system = str(a.get("system", "US"))

    try:
        result = ring_resize(from_size, to_size, system)
    except (ValueError, KeyError) as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"ring_resize error: {exc}", "ERROR")

    return ok_payload(result)


# --- 7. jewelry_polish_stock -------------------------------------------------

_polish_stock_spec = ToolSpec(
    name="jewelry_polish_stock",
    description=(
        "Estimate rough oversize volume and metal weight overhead for file/polish "
        "stock allowance.\n\n"
        "The piece is cast oversize; hand-filing and polishing remove the stock "
        "allowance to reach the finished dimension.  Industry default: 0.15 mm "
        "per side on 3 sides.\n\n"
        "Returns: rough_volume_mm3, stock_volume_mm3, stock_pct."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "volume_mm3": {
                "type": "number",
                "description": "Finished target volume in mm³.",
            },
            "avg_dimension_mm": {
                "type": "number",
                "description": "Representative dimension (e.g. shank width) in mm.",
            },
            "stock_mm": {
                "type": "number",
                "description": "Stock allowance per side in mm (default 0.15).",
            },
            "sides": {
                "type": "integer",
                "description": "Number of sides with stock (default 3).",
            },
        },
        "required": ["volume_mm3", "avg_dimension_mm"],
    },
)


@register(_polish_stock_spec, write=False)
async def run_jewelry_polish_stock(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_polish_stock."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    vol = a.get("volume_mm3")
    avg_dim = a.get("avg_dimension_mm")
    if vol is None:
        return err_payload("volume_mm3 is required", "BAD_ARGS")
    if avg_dim is None:
        return err_payload("avg_dimension_mm is required", "BAD_ARGS")
    try:
        vol = float(vol)
        avg_dim = float(avg_dim)
    except (TypeError, ValueError):
        return err_payload("volume_mm3 and avg_dimension_mm must be numbers", "BAD_ARGS")

    kwargs: dict[str, Any] = {}
    if "stock_mm" in a:
        try:
            kwargs["stock_mm"] = float(a["stock_mm"])
        except (TypeError, ValueError):
            return err_payload("stock_mm must be a number", "BAD_ARGS")
    if "sides" in a:
        try:
            kwargs["sides"] = int(a["sides"])
        except (TypeError, ValueError):
            return err_payload("sides must be an integer", "BAD_ARGS")

    try:
        result = polish_stock(vol, avg_dim, **kwargs)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"polish_stock error: {exc}", "ERROR")

    return ok_payload(result)
