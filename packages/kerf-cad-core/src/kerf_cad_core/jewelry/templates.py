"""
kerf_cad_core.jewelry.templates
================================

Jewelry preset/template library — a starter-template registry so users can
drop a complete jewelry piece into the scene from a chat prompt.

Each template is a *parametric recipe dict* that describes a complete jewelry
piece by referencing the tools already wired in the occtWorker.  Templates do
NOT invoke OCCT geometry themselves; they return a structured recipe that
downstream tool-chains execute via existing ops (ring_shank, prong_head,
gem_seat, finding, etc.).

Template IDs are stable keys suitable for URL slugs and CLI flags (lowercase,
underscores).

## Two LLM tools

``list_jewelry_templates``
    Read-only.  Returns the full catalog, optionally filtered by category.
    No project context required.

``instantiate_jewelry_template``
    Read-only (returns a recipe dict — callers write nodes separately).
    Accepts a ``template_id`` and an optional ``overrides`` dict that
    deep-merges on top of the template defaults.

## Recipe schema

Each recipe is a dict with the following top-level keys::

    {
      "template_id":   str,            # stable slug key
      "name":          str,            # human-readable display name
      "category":      str,            # rings | earrings | pendants | bracelets | misc
      "description":   str,            # one-line description for the LLM
      "metal":         str,            # default alloy key (from metal_cost.METAL_DENSITY_G_CM3)
      "components":    list[dict],     # ordered list of component specs (see below)
      "tags":          list[str],      # searchable tags
    }

Each component dict has::

    {
      "tool":    str,                  # LLM tool name to invoke
      "role":    str,                  # human label for this component in the piece
      "params":  dict,                 # default parameter values for the tool
    }

## Alloy keys

All ``metal`` values must be valid keys in
``kerf_cad_core.jewelry.metal_cost.METAL_DENSITY_G_CM3``.

## Gem cut keys

All ``cut`` values must be members of
``kerf_cad_core.jewelry.gemstones.GEMSTONE_CUTS``.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401 — required by @register


# ---------------------------------------------------------------------------
# Validation helpers (import-time guard — keeps templates self-consistent)
# ---------------------------------------------------------------------------

def _valid_alloys() -> frozenset:
    from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3
    return frozenset(METAL_DENSITY_G_CM3.keys())


def _valid_cuts() -> frozenset:
    from kerf_cad_core.jewelry.gemstones import GEMSTONE_CUTS
    return frozenset(GEMSTONE_CUTS)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: list[dict] = []
_TEMPLATE_INDEX: dict[str, dict] = {}


def _reg(t: dict) -> dict:
    """Register a template dict; return it for readability."""
    _TEMPLATES.append(t)
    _TEMPLATE_INDEX[t["template_id"]] = t
    return t


# ===========================================================================
# RINGS (10)
# ===========================================================================

_reg({
    "template_id": "ring_solitaire_round",
    "name": "Solitaire Ring — Round Brilliant",
    "category": "rings",
    "description": (
        "Classic six-prong solitaire engagement ring with a round-brilliant "
        "centre stone on a plain tapered shank."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 2.2,
                "thickness": 1.8,
                "profile": "comfort_fit",
                "shoulder_style": "tapered",
                "taper_ratio": 0.75,
            },
        },
        {
            "tool": "jewelry_create_prong_head",
            "role": "centre_head",
            "params": {
                "stone_diameter_mm": 6.5,
                "cut": "round_brilliant",
                "prong_count": 6,
                "head_style": "basket",
                "prong_height_mm": 4.5,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.5,
                "material": "diamond",
            },
        },
    ],
    "tags": ["engagement", "solitaire", "round", "classic", "six-prong"],
})

_reg({
    "template_id": "ring_solitaire_oval",
    "name": "Solitaire Ring — Oval Cut",
    "category": "rings",
    "description": (
        "Four-prong solitaire with an oval-cut centre stone; slightly elongated "
        "shank shoulders to frame the stone."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 2.0,
                "thickness": 1.8,
                "profile": "comfort_fit",
                "shoulder_style": "tapered",
                "taper_ratio": 0.80,
            },
        },
        {
            "tool": "jewelry_create_prong_head",
            "role": "centre_head",
            "params": {
                "stone_diameter_mm": 8.0,
                "cut": "oval",
                "prong_count": 4,
                "head_style": "standard",
                "prong_height_mm": 4.0,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "oval",
                "diameter_mm": 8.0,
                "material": "diamond",
            },
        },
    ],
    "tags": ["engagement", "solitaire", "oval", "four-prong"],
})

_reg({
    "template_id": "ring_solitaire_cushion",
    "name": "Solitaire Ring — Cushion Cut",
    "category": "rings",
    "description": (
        "Soft, romantic cushion-cut solitaire with a basket-prong head and "
        "gently tapered shank in rose gold."
    ),
    "metal": "18k_rose",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 2.0,
                "thickness": 1.8,
                "profile": "comfort_fit",
                "shoulder_style": "tapered",
                "taper_ratio": 0.80,
            },
        },
        {
            "tool": "jewelry_create_prong_head",
            "role": "centre_head",
            "params": {
                "stone_diameter_mm": 7.0,
                "cut": "cushion",
                "prong_count": 4,
                "head_style": "basket",
                "prong_height_mm": 4.2,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "cushion",
                "diameter_mm": 7.0,
                "material": "diamond",
            },
        },
    ],
    "tags": ["engagement", "solitaire", "cushion", "rose-gold", "romantic"],
})

_reg({
    "template_id": "ring_solitaire_emerald",
    "name": "Solitaire Ring — Emerald Cut",
    "category": "rings",
    "description": (
        "Art-deco inspired emerald-cut solitaire with a bezel-accent head and "
        "sleek straight-sided shank in platinum."
    ),
    "metal": "platinum_950",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 2.4,
                "thickness": 2.0,
                "profile": "flat",
                "shoulder_style": "straight",
                "taper_ratio": 1.0,
            },
        },
        {
            "tool": "jewelry_create_bezel",
            "role": "centre_setting",
            "params": {
                "stone_diameter_mm": 9.0,
                "cut": "emerald",
                "bezel_style": "partial",
                "bezel_height_mm": 3.5,
                "wall_thickness_mm": 0.9,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "emerald",
                "diameter_mm": 9.0,
                "material": "diamond",
            },
        },
    ],
    "tags": ["engagement", "solitaire", "emerald-cut", "platinum", "art-deco"],
})

_reg({
    "template_id": "ring_three_stone",
    "name": "Three-Stone Ring",
    "category": "rings",
    "description": (
        "Past-present-future three-stone ring: round-brilliant centre flanked "
        "by two graduated round side stones on a cathedral shank."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 2.4,
                "thickness": 1.9,
                "profile": "comfort_fit",
                "shoulder_style": "cathedral",
                "taper_ratio": 0.70,
            },
        },
        {
            "tool": "jewelry_create_three_stone_setting",
            "role": "three_stone_head",
            "params": {
                "centre_diameter_mm": 6.5,
                "side_diameter_mm": 4.0,
                "cut": "round_brilliant",
                "prong_count": 4,
                "side_spacing_mm": 0.3,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.5,
                "material": "diamond",
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "side_stones",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 4.0,
                "material": "diamond",
                "count": 2,
            },
        },
    ],
    "tags": ["engagement", "three-stone", "past-present-future", "round"],
})

_reg({
    "template_id": "ring_halo",
    "name": "Halo Engagement Ring",
    "category": "rings",
    "description": (
        "Round-brilliant centre stone surrounded by a micro-pavé diamond halo "
        "on a pavé-set split shank."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 1.8,
                "thickness": 1.6,
                "profile": "comfort_fit",
                "shoulder_style": "split_pave",
                "taper_ratio": 0.65,
            },
        },
        {
            "tool": "jewelry_create_halo_setting",
            "role": "halo_head",
            "params": {
                "centre_diameter_mm": 6.5,
                "cut": "round_brilliant",
                "halo_stone_diameter_mm": 1.3,
                "halo_stone_count": 22,
                "prong_count": 4,
                "halo_height_offset_mm": 0.5,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.5,
                "material": "diamond",
            },
        },
    ],
    "tags": ["engagement", "halo", "pave", "split-shank"],
})

_reg({
    "template_id": "ring_eternity",
    "name": "Full Eternity Band",
    "category": "rings",
    "description": (
        "Full-circle channel-set round-brilliant eternity band — the classic "
        "anniversary ring."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_eternity_band",
            "role": "eternity_band",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 3.5,
                "stone_diameter_mm": 2.5,
                "stone_cut": "round_brilliant",
                "coverage": "full",
                "setting_style": "channel",
                "thickness": 2.0,
            },
        },
    ],
    "tags": ["anniversary", "eternity", "channel", "full-circle"],
})

_reg({
    "template_id": "ring_signet",
    "name": "Classic Signet Ring",
    "category": "rings",
    "description": (
        "Traditional oval-face signet ring with a flat engravable seal, "
        "milgrain border, and comfort-fit shank."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_signet_ring",
            "role": "signet_ring",
            "params": {
                "ring_size": 10,
                "system": "US",
                "face_shape": "oval",
                "face_width_mm": 14.0,
                "face_height_mm": 12.0,
                "face_depth_mm": 1.5,
                "shank_width_mm": 4.5,
                "shank_thickness_mm": 2.2,
                "band_profile": "comfort_fit",
                "milgrain": True,
            },
        },
    ],
    "tags": ["signet", "engraving", "classic", "traditional"],
})

_reg({
    "template_id": "ring_mens_band",
    "name": "Men's Comfort-Fit Band",
    "category": "rings",
    "description": (
        "6 mm wide men's comfort-fit wedding band in 14k yellow gold with "
        "a satin-brushed finish and bevelled edges."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_mens_band",
            "role": "mens_band",
            "params": {
                "ring_size": 10,
                "system": "US",
                "band_width": 6.0,
                "thickness": 2.2,
                "profile": "euro",
                "edge_style": "bevelled",
                "surface_finish": "satin",
                "comfort_fit": True,
            },
        },
    ],
    "tags": ["wedding", "mens", "band", "comfort-fit", "satin"],
})

_reg({
    "template_id": "ring_tension",
    "name": "Tension-Set Ring",
    "category": "rings",
    "description": (
        "Modern tension-set ring: a round-brilliant stone held between two "
        "platinum arms by spring pressure alone — no prongs, no bezel."
    ),
    "metal": "platinum_950",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "tension_shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 3.0,
                "thickness": 2.5,
                "profile": "flat",
                "shoulder_style": "tension",
                "taper_ratio": 1.0,
            },
        },
        {
            "tool": "jewelry_create_tension_setting",
            "role": "tension_setting",
            "params": {
                "stone_diameter_mm": 6.5,
                "cut": "round_brilliant",
                "gap_depth_mm": 3.2,
                "seat_angle_deg": 45.0,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "centre_stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.5,
                "material": "diamond",
            },
        },
    ],
    "tags": ["modern", "tension", "platinum", "minimalist"],
})

_reg({
    "template_id": "ring_pave_band",
    "name": "Pavé Band",
    "category": "rings",
    "description": (
        "Glamorous half-eternity pavé band with 1.3 mm round-brilliant melee "
        "set in micro-pavé across the top 180° in 18k white gold."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_ring_shank",
            "role": "shank",
            "params": {
                "ring_size": 7,
                "system": "US",
                "band_width": 3.0,
                "thickness": 1.8,
                "profile": "comfort_fit",
                "shoulder_style": "straight",
                "taper_ratio": 1.0,
            },
        },
        {
            "tool": "jewelry_create_pave_array",
            "role": "pave_top",
            "params": {
                "stone_diameter_mm": 1.3,
                "cut": "round_brilliant",
                "coverage_deg": 180,
                "rows": 1,
                "setting_depth_mm": 0.8,
            },
        },
    ],
    "tags": ["pave", "half-eternity", "sparkle", "band"],
})


# ===========================================================================
# EARRINGS (5)
# ===========================================================================

_reg({
    "template_id": "earring_stud",
    "name": "Diamond Stud Earrings",
    "category": "earrings",
    "description": (
        "Classic four-prong round-brilliant diamond studs on push-back posts, "
        "0.50 ct each, in 18k white gold."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_earrings",
            "role": "stud_pair",
            "params": {
                "style": "stud",
                "stone_diameter_mm": 5.0,
                "stone_cut": "round_brilliant",
                "setting_style": "prong",
                "prong_count": 4,
                "post_diameter_mm": 0.76,
                "back_style": "butterfly",
                "pair": True,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stones",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 5.0,
                "material": "diamond",
                "count": 2,
            },
        },
    ],
    "tags": ["stud", "earrings", "classic", "everyday"],
})

_reg({
    "template_id": "earring_drop",
    "name": "Drop Earrings",
    "category": "earrings",
    "description": (
        "Elegant drop earrings with a round-brilliant centre stone suspended "
        "from a simple loop bail on a lever-back wire."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_earrings",
            "role": "drop_pair",
            "params": {
                "style": "drop",
                "drop_length_mm": 20.0,
                "stone_diameter_mm": 6.0,
                "stone_cut": "round_brilliant",
                "setting_style": "bezel",
                "ear_wire_style": "lever_back",
                "pair": True,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stones",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.0,
                "material": "sapphire",
                "count": 2,
            },
        },
    ],
    "tags": ["drop", "earrings", "lever-back", "elegant"],
})

_reg({
    "template_id": "earring_hoop",
    "name": "Classic Hoop Earrings",
    "category": "earrings",
    "description": (
        "30 mm inner-diameter round hoop earrings with a plain round-wire "
        "cross-section and hinged click closure, in 14k yellow gold."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_earrings",
            "role": "hoop_pair",
            "params": {
                "style": "hoop",
                "hoop_inner_diameter_mm": 30.0,
                "wire_diameter_mm": 2.0,
                "hoop_profile": "round",
                "closure": "click",
                "pair": True,
            },
        },
    ],
    "tags": ["hoop", "earrings", "classic", "everyday"],
})

_reg({
    "template_id": "earring_chandelier",
    "name": "Chandelier Earrings",
    "category": "earrings",
    "description": (
        "Three-tier chandelier earrings with pavé-set melee at each tier, "
        "dropping 45 mm total on lever-back wires, in 18k yellow gold."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_earrings",
            "role": "chandelier_pair",
            "params": {
                "style": "chandelier",
                "tier_count": 3,
                "total_drop_mm": 45.0,
                "stone_diameter_mm": 1.5,
                "stone_cut": "round_brilliant",
                "setting_style": "pave",
                "ear_wire_style": "lever_back",
                "pair": True,
            },
        },
    ],
    "tags": ["chandelier", "earrings", "formal", "statement"],
})

_reg({
    "template_id": "earring_huggie",
    "name": "Huggie Hoop Earrings",
    "category": "earrings",
    "description": (
        "10 mm huggie hoops with a pavé-set outside face — the compact, "
        "everyday hoop that hugs the earlobe."
    ),
    "metal": "14k_white",
    "components": [
        {
            "tool": "jewelry_create_earrings",
            "role": "huggie_pair",
            "params": {
                "style": "huggie",
                "hoop_inner_diameter_mm": 10.0,
                "band_width_mm": 5.0,
                "wall_thickness_mm": 1.5,
                "stone_diameter_mm": 1.3,
                "stone_cut": "round_brilliant",
                "setting_style": "pave",
                "closure": "click",
                "pair": True,
            },
        },
    ],
    "tags": ["huggie", "hoop", "earrings", "pave", "everyday"],
})


# ===========================================================================
# PENDANTS (5)
# ===========================================================================

_reg({
    "template_id": "pendant_solitaire",
    "name": "Solitaire Pendant",
    "category": "pendants",
    "description": (
        "Simple six-prong round-brilliant solitaire pendant on a pinch bail, "
        "designed to sit on a 1 mm box chain."
    ),
    "metal": "18k_white",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "pendant_body",
            "params": {
                "style": "solitaire",
                "stone_diameter_mm": 6.5,
                "stone_cut": "round_brilliant",
                "setting_style": "prong",
                "prong_count": 6,
                "bail_style": "pinch",
                "bail_width_mm": 3.5,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.5,
                "material": "diamond",
            },
        },
    ],
    "tags": ["pendant", "solitaire", "round", "everyday"],
})

_reg({
    "template_id": "pendant_halo",
    "name": "Halo Pendant",
    "category": "pendants",
    "description": (
        "Round-brilliant centre stone in a micro-pavé halo, suspended from a "
        "classic loop bail. Vintage-inspired look."
    ),
    "metal": "14k_white",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "pendant_body",
            "params": {
                "style": "halo",
                "stone_diameter_mm": 6.0,
                "stone_cut": "round_brilliant",
                "halo_stone_diameter_mm": 1.3,
                "halo_stone_count": 18,
                "bail_style": "loop",
                "bail_width_mm": 3.0,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 6.0,
                "material": "diamond",
            },
        },
    ],
    "tags": ["pendant", "halo", "pave", "vintage"],
})

_reg({
    "template_id": "pendant_locket",
    "name": "Classic Round Locket",
    "category": "pendants",
    "description": (
        "38 mm diameter hinged round locket with engraved floral lid motif "
        "and snap closure — holds a photograph or keepsake."
    ),
    "metal": "sterling_925",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "locket_body",
            "params": {
                "style": "locket",
                "outline_shape": "round",
                "width_mm": 38.0,
                "height_mm": 38.0,
                "depth_mm": 8.0,
                "hinge_style": "pin",
                "closure_style": "snap",
                "bail_style": "loop",
                "engraving_hint": "floral_scroll",
            },
        },
    ],
    "tags": ["locket", "pendant", "keepsake", "heirloom"],
})

_reg({
    "template_id": "pendant_bar",
    "name": "Bar Pendant",
    "category": "pendants",
    "description": (
        "Minimalist 30 × 4 mm horizontal bar pendant with optional name "
        "engraving, on a top-drilled suspension bail."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "bar_body",
            "params": {
                "style": "bar",
                "outline_shape": "rectangle",
                "width_mm": 30.0,
                "height_mm": 4.0,
                "depth_mm": 2.0,
                "bail_style": "top_drilled",
                "engraving_hint": "name_plate",
            },
        },
    ],
    "tags": ["bar", "pendant", "minimalist", "modern", "engraving"],
})

_reg({
    "template_id": "pendant_cross",
    "name": "Cross Pendant",
    "category": "pendants",
    "description": (
        "Latin cross pendant (30 mm tall, 20 mm wide) in sterling silver with "
        "a polished finish and a simple oval bail."
    ),
    "metal": "sterling_925",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "cross_body",
            "params": {
                "style": "cross",
                "outline_shape": "cross",
                "width_mm": 20.0,
                "height_mm": 30.0,
                "depth_mm": 2.5,
                "cross_arm_width_mm": 6.0,
                "bail_style": "loop",
                "surface_finish": "polish",
            },
        },
    ],
    "tags": ["cross", "pendant", "religious", "silver"],
})


# ===========================================================================
# BRACELETS (5)
# ===========================================================================

_reg({
    "template_id": "bracelet_tennis",
    "name": "Tennis Bracelet",
    "category": "bracelets",
    "description": (
        "Classic inline tennis bracelet: 2.0 mm round-brilliant diamonds in "
        "four-prong settings, ~7 inch length, in 14k white gold with box clasp."
    ),
    "metal": "14k_white",
    "components": [
        {
            "tool": "jewelry_create_bangle",
            "role": "tennis_base",
            "params": {
                "form": "tennis",
                "wrist_size": 7.0,
                "wrist_size_system": "US_inches",
                "stone_diameter_mm": 2.0,
                "stone_cut": "round_brilliant",
                "stone_count": 46,
                "setting_style": "prong",
                "clasp_style": "box",
                "cross_section": "round",
                "wire_diameter_mm": 1.2,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stones",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 2.0,
                "material": "diamond",
                "count": 46,
            },
        },
    ],
    "tags": ["tennis", "bracelet", "diamonds", "classic", "formal"],
})

_reg({
    "template_id": "bracelet_charm",
    "name": "Charm Bracelet",
    "category": "bracelets",
    "description": (
        "Sterling silver charm bracelet — anchor chain with lobster-claw clasp "
        "and three jump-ring attachment points for charms."
    ),
    "metal": "sterling_925",
    "components": [
        {
            "tool": "jewelry_create_chain",
            "role": "chain",
            "params": {
                "style": "anchor",
                "length_mm": 180.0,
                "link_width_mm": 4.0,
                "wire_diameter_mm": 1.2,
                "finish": "polish",
            },
        },
        {
            "tool": "jewelry_create_finding",
            "role": "clasp",
            "params": {
                "family": "clasp",
                "kind": "lobster_claw",
                "width_mm": 12.0,
            },
        },
    ],
    "tags": ["charm", "bracelet", "chain", "silver"],
})

_reg({
    "template_id": "bracelet_bangle",
    "name": "Plain Bangle",
    "category": "bracelets",
    "description": (
        "Simple 3 mm round-wire bangle in 18k yellow gold — stackable, "
        "polished finish, US size 7.5 (65 mm inner diameter)."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_bangle",
            "role": "bangle",
            "params": {
                "form": "bangle",
                "wrist_size": 7.5,
                "wrist_size_system": "US_inches",
                "cross_section": "round",
                "wire_diameter_mm": 3.0,
                "surface_finish": "polish",
            },
        },
    ],
    "tags": ["bangle", "bracelet", "plain", "stackable"],
})

_reg({
    "template_id": "bracelet_cuff",
    "name": "Wide Cuff Bracelet",
    "category": "bracelets",
    "description": (
        "25 mm wide open cuff bracelet in sterling silver with a hammered "
        "outer surface and rounded inner bore for comfort."
    ),
    "metal": "sterling_925",
    "components": [
        {
            "tool": "jewelry_create_bangle",
            "role": "cuff",
            "params": {
                "form": "cuff",
                "wrist_size": 7.5,
                "wrist_size_system": "US_inches",
                "cross_section": "flat",
                "band_width_mm": 25.0,
                "wall_thickness_mm": 1.5,
                "surface_finish": "hammer",
                "opening_gap_mm": 18.0,
            },
        },
    ],
    "tags": ["cuff", "bracelet", "wide", "hammered", "statement"],
})

_reg({
    "template_id": "bracelet_link",
    "name": "Curb Link Bracelet",
    "category": "bracelets",
    "description": (
        "Classic curb-link (gourmette) bracelet in 14k yellow gold — 8 mm "
        "flat twisted oval links, lobster-claw clasp, 7 inch length."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_chain",
            "role": "chain",
            "params": {
                "style": "curb",
                "length_mm": 178.0,
                "link_width_mm": 8.0,
                "wire_diameter_mm": 1.8,
                "finish": "polish",
            },
        },
        {
            "tool": "jewelry_create_finding",
            "role": "clasp",
            "params": {
                "family": "clasp",
                "kind": "lobster_claw",
                "width_mm": 14.0,
            },
        },
    ],
    "tags": ["curb", "link", "bracelet", "chain", "classic"],
})


# ===========================================================================
# BROOCHES / MISC (5)
# ===========================================================================

_reg({
    "template_id": "misc_brooch",
    "name": "Oval Brooch",
    "category": "misc",
    "description": (
        "40 × 28 mm oval brooch with a pavé-set diamond border, plain polished "
        "centre, pin-stem finding, and roller catch."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_brooch",
            "role": "brooch_body",
            "params": {
                "shape": "oval",
                "width_mm": 40.0,
                "height_mm": 28.0,
                "depth_mm": 3.0,
                "border_setting": "pave",
                "border_stone_diameter_mm": 1.3,
                "border_stone_cut": "round_brilliant",
                "pin_style": "swivel",
                "catch_style": "roller",
            },
        },
    ],
    "tags": ["brooch", "oval", "pave", "formal"],
})

_reg({
    "template_id": "misc_cufflink",
    "name": "Round Cufflinks",
    "category": "misc",
    "description": (
        "Classic 16 mm round-face toggle cufflinks in 14k yellow gold with "
        "a plain polished disc face — ideal for engraving."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_cufflink",
            "role": "cufflink_pair",
            "params": {
                "face_shape": "round",
                "face_diameter_mm": 16.0,
                "face_depth_mm": 3.0,
                "back_style": "toggle",
                "bar_length_mm": 16.0,
                "bar_diameter_mm": 3.5,
                "surface_finish": "polish",
                "pair": True,
            },
        },
    ],
    "tags": ["cufflinks", "round", "toggle", "formal", "menswear"],
})

_reg({
    "template_id": "misc_tie_pin",
    "name": "Tie Pin (Stick Pin)",
    "category": "misc",
    "description": (
        "70 mm stick pin with a 4 mm round-brilliant diamond set in a six-prong "
        "head and a barrel safety catch, in 14k yellow gold."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_finding",
            "role": "pin_stem",
            "params": {
                "family": "pin_finding",
                "kind": "stick_pin",
                "length_mm": 70.0,
                "wire_diameter_mm": 0.8,
            },
        },
        {
            "tool": "jewelry_create_prong_head",
            "role": "pin_head",
            "params": {
                "stone_diameter_mm": 4.0,
                "cut": "round_brilliant",
                "prong_count": 6,
                "head_style": "standard",
                "prong_height_mm": 3.0,
            },
        },
        {
            "tool": "jewelry_create_gemstone",
            "role": "stone",
            "params": {
                "cut": "round_brilliant",
                "diameter_mm": 4.0,
                "material": "diamond",
            },
        },
        {
            "tool": "jewelry_create_finding",
            "role": "safety_catch",
            "params": {
                "family": "pin_finding",
                "kind": "catch_barrel",
                "wire_diameter_mm": 0.8,
            },
        },
    ],
    "tags": ["tie-pin", "stick-pin", "formal", "menswear"],
})

_reg({
    "template_id": "misc_lapel_pin",
    "name": "Lapel Pin",
    "category": "misc",
    "description": (
        "25 mm custom-shape lapel pin with a flat engraved disc face and "
        "butterfly clutch back, in 14k yellow gold — adaptable to any shape."
    ),
    "metal": "14k_yellow",
    "components": [
        {
            "tool": "jewelry_create_brooch",
            "role": "lapel_body",
            "params": {
                "shape": "round",
                "width_mm": 25.0,
                "height_mm": 25.0,
                "depth_mm": 2.5,
                "pin_style": "straight",
                "catch_style": "butterfly_clutch",
                "surface_finish": "polish",
            },
        },
    ],
    "tags": ["lapel-pin", "badge", "menswear", "engraving"],
})

_reg({
    "template_id": "misc_signet_pendant",
    "name": "Signet Pendant",
    "category": "misc",
    "description": (
        "Oval engravable seal face on a pendant bail — wearable signet for "
        "those who prefer a necklace to a ring, in 18k yellow gold."
    ),
    "metal": "18k_yellow",
    "components": [
        {
            "tool": "jewelry_create_pendant",
            "role": "signet_face",
            "params": {
                "style": "locket",
                "outline_shape": "oval",
                "width_mm": 20.0,
                "height_mm": 24.0,
                "depth_mm": 4.0,
                "bail_style": "loop",
                "engraving_hint": "monogram_seal",
                "surface_finish": "polish",
            },
        },
        {
            "tool": "jewelry_create_finding",
            "role": "bail",
            "params": {
                "family": "bail",
                "kind": "loop",
                "wire_diameter_mm": 1.5,
                "loop_diameter_mm": 5.0,
            },
        },
    ],
    "tags": ["signet", "pendant", "engraving", "seal", "necklace"],
})


# ===========================================================================
# Catalog accessor
# ===========================================================================

def get_template(template_id: str) -> dict | None:
    """Return a deep copy of the template dict for ``template_id``, or None."""
    t = _TEMPLATE_INDEX.get(template_id)
    return copy.deepcopy(t) if t is not None else None


def list_templates(category: str | None = None) -> list[dict]:
    """Return catalog summary rows (id, name, category, description, tags)."""
    rows = []
    for t in _TEMPLATES:
        if category is not None and t["category"] != category:
            continue
        rows.append({
            "template_id": t["template_id"],
            "name": t["name"],
            "category": t["category"],
            "description": t["description"],
            "metal": t["metal"],
            "tags": t["tags"],
            "component_count": len(t["components"]),
        })
    return rows


def instantiate(template_id: str, overrides: dict | None = None) -> dict | None:
    """
    Return a fully resolved recipe for *template_id* with *overrides* applied.

    *overrides* is a shallow-merge dict whose keys match top-level recipe fields.
    For ``components``, a list of ``{"index": int, "params": dict}`` entries may
    be supplied to patch individual component params.

    Returns None when template_id is not found.
    """
    t = get_template(template_id)
    if t is None:
        return None
    if overrides:
        # Shallow-merge top-level scalar fields.
        for k, v in overrides.items():
            if k == "components":
                # Patch by index
                for patch in v:
                    idx = patch.get("index")
                    params = patch.get("params", {})
                    if idx is not None and 0 <= idx < len(t["components"]):
                        t["components"][idx]["params"].update(params)
            else:
                t[k] = v
    return t


# ===========================================================================
# LLM tool — list_jewelry_templates
# ===========================================================================

list_jewelry_templates_spec = ToolSpec(
    name="list_jewelry_templates",
    description=(
        "List all jewelry preset templates in the Kerf template library.\n"
        "\n"
        "Returns a catalog of ready-made jewelry recipes that the user can "
        "instantiate and customise.  Each template describes a complete piece "
        "(rings, earrings, pendants, bracelets, brooches/misc) with sensible "
        "defaults for metal, gem cut, and dimensions.\n"
        "\n"
        "Optional filter: pass a `category` to narrow results.\n"
        "\n"
        "Categories: rings | earrings | pendants | bracelets | misc\n"
        "\n"
        "After listing, call `instantiate_jewelry_template` with a `template_id` "
        "to get the full parametric recipe."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": (
                    "Optional category filter.  One of: rings, earrings, "
                    "pendants, bracelets, misc.  Omit to return all templates."
                ),
                "enum": ["rings", "earrings", "pendants", "bracelets", "misc"],
            },
        },
        "required": [],
    },
)


@register(list_jewelry_templates_spec, write=False)
async def run_list_jewelry_templates(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args else {}
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    category = a.get("category")
    if category is not None:
        valid_cats = {"rings", "earrings", "pendants", "bracelets", "misc"}
        if category not in valid_cats:
            return err_payload(
                f"Unknown category '{category}'. Valid: {sorted(valid_cats)}",
                "BAD_ARGS",
            )

    rows = list_templates(category=category)
    return ok_payload({
        "templates": rows,
        "total": len(rows),
        "categories": ["rings", "earrings", "pendants", "bracelets", "misc"],
    })


# ===========================================================================
# LLM tool — instantiate_jewelry_template
# ===========================================================================

instantiate_jewelry_template_spec = ToolSpec(
    name="instantiate_jewelry_template",
    description=(
        "Instantiate a jewelry template recipe by ID, with optional parameter overrides.\n"
        "\n"
        "Returns a complete parametric recipe dict listing the ordered tool calls "
        "and their default parameters needed to build the piece.  The recipe does "
        "NOT execute geometry — pass each component's tool + params to the "
        "appropriate jewelry tool (jewelry_create_ring_shank, jewelry_create_gemstone, "
        "etc.) to append nodes to a .feature file.\n"
        "\n"
        "Use `list_jewelry_templates` first to discover valid template_ids.\n"
        "\n"
        "Overrides allow the user to customise the recipe:\n"
        "  - Top-level fields (metal, name) can be replaced directly.\n"
        "  - Individual component params are patched via the `components` override "
        "    list: [{\"index\": 0, \"params\": {\"ring_size\": 8}}].\n"
        "\n"
        "Example: instantiate template 'ring_solitaire_round' for US size 8 "
        "in 14k yellow gold:\n"
        "  template_id: 'ring_solitaire_round'\n"
        "  overrides: {\"metal\": \"14k_yellow\", \"components\": "
        "[{\"index\": 0, \"params\": {\"ring_size\": 8}}]}"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": (
                    "Stable template slug.  Use list_jewelry_templates to enumerate "
                    "valid IDs."
                ),
            },
            "overrides": {
                "type": "object",
                "description": (
                    "Optional overrides applied on top of template defaults.  "
                    "Top-level keys (metal, name) replace values directly.  "
                    "The special 'components' key accepts a list of "
                    "{\"index\": int, \"params\": dict} patch objects that merge "
                    "into the component's params at the given index."
                ),
                "additionalProperties": True,
            },
        },
        "required": ["template_id"],
    },
)


@register(instantiate_jewelry_template_spec, write=False)
async def run_instantiate_jewelry_template(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args else {}
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    template_id = a.get("template_id")
    if not template_id:
        return err_payload("template_id is required", "BAD_ARGS")
    if not isinstance(template_id, str):
        return err_payload("template_id must be a string", "BAD_ARGS")
    template_id = template_id.strip()

    overrides: dict | None = a.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        return err_payload("overrides must be an object", "BAD_ARGS")

    # Validate metal override if provided
    if overrides and "metal" in overrides:
        from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3
        metal_key = overrides["metal"]
        if metal_key not in METAL_DENSITY_G_CM3:
            valid = ", ".join(sorted(METAL_DENSITY_G_CM3.keys()))
            return err_payload(
                f"Unknown metal override '{metal_key}'. Valid keys: {valid}",
                "BAD_ARGS",
            )

    recipe = instantiate(template_id, overrides)
    if recipe is None:
        known = sorted(_TEMPLATE_INDEX.keys())
        return err_payload(
            f"Unknown template_id '{template_id}'. Known IDs: {known}",
            "BAD_ARGS",
        )

    return ok_payload(recipe)
