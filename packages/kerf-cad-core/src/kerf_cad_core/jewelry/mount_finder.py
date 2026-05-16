"""
kerf_cad_core.jewelry.mount_finder
====================================

Loose-stone → compatible semi-mount / finding matcher.

Given a loose stone (cut, carat OR mm dimensions, optional material/hardness)
this module ranks compatible mounts and heads from an in-module synthetic
catalog by:

  - Girdle / seat fit tolerance  (mm window, configurable)
  - Shape match                  (round, oval, cushion, princess, emerald,
                                  pear, marquise, …)
  - Setting-style suitability    per stone hardness (prong vs bezel for
                                  soft / brittle stones; Mohs < 7 → prefer bezel)
  - Carat / centre-size range    of the mount
  - Metal options                (yellow-gold, white-gold, rose-gold, platinum,
                                  sterling-silver, palladium)
  - Accent-stone count           (0 = solitaire; N = halo / side-stone count)

Return value
------------
A dict ``{"ok": True, "best": {...}, "alternatives": [...], "rejected": [...]}``
where every candidate entry contains:

  fit_mm_delta : float   — |stone_mm - mount_seat_mm| (lower is better)
  score        : float   — composite score (higher is better)
  why          : list[str]
  reject_reason: str | None  (None for accepted mounts)

Never raises — all errors are returned as ``{"ok": False, "reason": "..."}``.

LLM tools registered
---------------------
    jewelry_find_mounts  (read-only)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    GEMSTONE_DENSITIES,
    GEM_CATALOG,
    mm_from_carat,
    carat_from_mm,
)

# ---------------------------------------------------------------------------
# Shape-family normalisation
# Maps the many specific cut names to a broad shape family used for
# mount compatibility matching.
# ---------------------------------------------------------------------------

_ROUND_CUTS = frozenset({
    "round_brilliant", "old_european", "old_mine", "single_cut",
    "portuguese", "rose_cut",
})
_OVAL_CUTS = frozenset({
    "oval", "half_moon",
})
_CUSHION_CUTS = frozenset({
    "cushion", "radiant", "flanders",
})
_PRINCESS_CUTS = frozenset({
    "princess", "asscher", "square_emerald", "french_cut",
})
_EMERALD_CUTS = frozenset({
    "emerald", "baguette", "tapered_baguette", "ceylon", "lozenge",
    "trapezoid",
})
_PEAR_CUTS = frozenset({
    "pear", "briolette", "bullet", "calf_head", "shield",
})
_MARQUISE_CUTS = frozenset({
    "marquise", "kite",
})
_TRILLION_CUTS = frozenset({
    "trillion",
})
_HEART_CUTS = frozenset({
    "heart",
})

# All known shape families
_SHAPE_FAMILIES = {
    "round": _ROUND_CUTS,
    "oval": _OVAL_CUTS,
    "cushion": _CUSHION_CUTS,
    "princess": _PRINCESS_CUTS,
    "emerald": _EMERALD_CUTS,
    "pear": _PEAR_CUTS,
    "marquise": _MARQUISE_CUTS,
    "trillion": _TRILLION_CUTS,
    "heart": _HEART_CUTS,
}


def _cut_to_shape_family(cut: str) -> str:
    """Return the broad shape-family name for a cut."""
    for family, members in _SHAPE_FAMILIES.items():
        if cut in members:
            return family
    return "fancy"


# ---------------------------------------------------------------------------
# Mohs hardness lookup
# ---------------------------------------------------------------------------

def _mohs_for_material(material: str) -> Optional[float]:
    """Return the midpoint Mohs hardness for a named gem material, or None."""
    entry = GEM_CATALOG.get(material.lower().strip())
    if entry is None:
        return None
    m = entry.get("mohs")
    if isinstance(m, (list, tuple)):
        return sum(m) / len(m)
    return float(m)


# ---------------------------------------------------------------------------
# In-module mount catalog
# ---------------------------------------------------------------------------
# Each entry describes one semi-mount / head SKU.
# Fields:
#   sku          str    — unique identifier
#   label        str    — human-readable name
#   shape_families list[str]  — accepted stone shape families
#   seat_mm_min  float  — minimum stone girdle dimension accepted (mm)
#   seat_mm_max  float  — maximum stone girdle dimension accepted (mm)
#   carat_min    float  — minimum stone carat weight
#   carat_max    float  — maximum stone carat weight
#   setting_styles list[str]  — "prong", "bezel", "tension", "channel", etc.
#   metals       list[str]
#   accent_count int    — number of accent stones (0 = solitaire)
#   style_tags   list[str]  — e.g. ["solitaire", "halo", "three_stone", "vintage"]

@dataclass
class MountEntry:
    sku: str
    label: str
    shape_families: list
    seat_mm_min: float
    seat_mm_max: float
    carat_min: float
    carat_max: float
    setting_styles: list
    metals: list
    accent_count: int
    style_tags: list = field(default_factory=list)


# Tolerance used when the stone mm is outside the mount seat range but close
_DEFAULT_FIT_TOLERANCE_MM = 0.35  # mm — accept near-misses within this window


_MOUNT_CATALOG: list[MountEntry] = [
    # ── Round solitaire heads ─────────────────────────────────────────────
    MountEntry(
        sku="RSH-4P-55-65",
        label="Round 4-prong solitaire head 5.5–6.5 mm",
        shape_families=["round"],
        seat_mm_min=5.5, seat_mm_max=6.5,
        carat_min=0.60, carat_max=1.10,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="RSH-6P-60-70",
        label="Round 6-prong solitaire head 6.0–7.0 mm",
        shape_families=["round"],
        seat_mm_min=6.0, seat_mm_max=7.0,
        carat_min=0.80, carat_max=1.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="RSH-4P-70-80",
        label="Round 4-prong solitaire head 7.0–8.0 mm",
        shape_families=["round"],
        seat_mm_min=7.0, seat_mm_max=8.0,
        carat_min=1.40, carat_max=2.30,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="RSH-BZL-55-65",
        label="Round full-bezel solitaire 5.5–6.5 mm",
        shape_families=["round"],
        seat_mm_min=5.5, seat_mm_max=6.5,
        carat_min=0.60, carat_max=1.10,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    MountEntry(
        sku="RSH-BZL-60-70",
        label="Round full-bezel solitaire 6.0–7.0 mm",
        shape_families=["round"],
        seat_mm_min=6.0, seat_mm_max=7.0,
        carat_min=0.80, carat_max=1.50,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    MountEntry(
        sku="RSH-BZL-70-80",
        label="Round full-bezel solitaire 7.0–8.0 mm",
        shape_families=["round"],
        seat_mm_min=7.0, seat_mm_max=8.0,
        carat_min=1.40, carat_max=2.30,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Round halo semi-mounts ────────────────────────────────────────────
    MountEntry(
        sku="RHL-4P-55-65",
        label="Round halo semi-mount 5.5–6.5 mm (18 accent stones)",
        shape_families=["round"],
        seat_mm_min=5.5, seat_mm_max=6.5,
        carat_min=0.60, carat_max=1.10,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=18,
        style_tags=["halo"],
    ),
    MountEntry(
        sku="RHL-4P-60-70",
        label="Round halo semi-mount 6.0–7.0 mm (20 accent stones)",
        shape_families=["round"],
        seat_mm_min=6.0, seat_mm_max=7.0,
        carat_min=0.80, carat_max=1.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=20,
        style_tags=["halo"],
    ),
    # ── Oval heads / semi-mounts ──────────────────────────────────────────
    MountEntry(
        sku="OVL-4P-80-95",
        label="Oval 4-prong solitaire head 8.0–9.5 mm",
        shape_families=["oval"],
        seat_mm_min=8.0, seat_mm_max=9.5,
        carat_min=1.00, carat_max=2.00,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="OVL-BZL-80-100",
        label="Oval full-bezel 8.0–10.0 mm",
        shape_families=["oval"],
        seat_mm_min=8.0, seat_mm_max=10.0,
        carat_min=1.00, carat_max=2.50,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    MountEntry(
        sku="OVL-HL-75-90",
        label="Oval halo semi-mount 7.5–9.0 mm (22 accent stones)",
        shape_families=["oval"],
        seat_mm_min=7.5, seat_mm_max=9.0,
        carat_min=0.90, carat_max=1.80,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=22,
        style_tags=["halo"],
    ),
    # ── Cushion heads ─────────────────────────────────────────────────────
    MountEntry(
        sku="CSH-4P-55-65",
        label="Cushion 4-prong solitaire head 5.5–6.5 mm",
        shape_families=["cushion"],
        seat_mm_min=5.5, seat_mm_max=6.5,
        carat_min=0.80, carat_max=1.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire", "vintage"],
    ),
    MountEntry(
        sku="CSH-BZL-55-70",
        label="Cushion bezel 5.5–7.0 mm",
        shape_families=["cushion"],
        seat_mm_min=5.5, seat_mm_max=7.0,
        carat_min=0.80, carat_max=1.80,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern", "vintage"],
    ),
    # ── Princess heads ────────────────────────────────────────────────────
    MountEntry(
        sku="PRS-4P-50-60",
        label="Princess 4-prong solitaire head 5.0–6.0 mm",
        shape_families=["princess"],
        seat_mm_min=5.0, seat_mm_max=6.0,
        carat_min=0.80, carat_max=1.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="PRS-BZL-50-65",
        label="Princess bezel 5.0–6.5 mm",
        shape_families=["princess"],
        seat_mm_min=5.0, seat_mm_max=6.5,
        carat_min=0.80, carat_max=1.80,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Emerald heads ─────────────────────────────────────────────────────
    MountEntry(
        sku="EMR-4P-75-90",
        label="Emerald-cut 4-claw solitaire head 7.5–9.0 mm",
        shape_families=["emerald"],
        seat_mm_min=7.5, seat_mm_max=9.0,
        carat_min=1.00, carat_max=2.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="EMR-BZL-70-90",
        label="Emerald-cut bezel 7.0–9.0 mm",
        shape_families=["emerald"],
        seat_mm_min=7.0, seat_mm_max=9.0,
        carat_min=0.90, carat_max=2.50,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Pear heads ────────────────────────────────────────────────────────
    MountEntry(
        sku="PER-3P-80-95",
        label="Pear 3-prong (v-tip) solitaire head 8.0–9.5 mm",
        shape_families=["pear"],
        seat_mm_min=8.0, seat_mm_max=9.5,
        carat_min=1.00, carat_max=2.00,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="PER-BZL-75-95",
        label="Pear full-bezel 7.5–9.5 mm",
        shape_families=["pear"],
        seat_mm_min=7.5, seat_mm_max=9.5,
        carat_min=0.90, carat_max=2.00,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Marquise heads ────────────────────────────────────────────────────
    MountEntry(
        sku="MRQ-4P-90-110",
        label="Marquise 4-prong (2 v-tip) solitaire head 9.0–11.0 mm",
        shape_families=["marquise"],
        seat_mm_min=9.0, seat_mm_max=11.0,
        carat_min=0.80, carat_max=1.80,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="MRQ-BZL-85-115",
        label="Marquise full-bezel 8.5–11.5 mm",
        shape_families=["marquise"],
        seat_mm_min=8.5, seat_mm_max=11.5,
        carat_min=0.70, carat_max=2.00,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Trillion heads ────────────────────────────────────────────────────
    MountEntry(
        sku="TRL-3P-65-85",
        label="Trillion 3-prong (corner-claw) head 6.5–8.5 mm",
        shape_families=["trillion"],
        seat_mm_min=6.5, seat_mm_max=8.5,
        carat_min=0.50, carat_max=1.50,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="TRL-BZL-65-90",
        label="Trillion bezel 6.5–9.0 mm",
        shape_families=["trillion"],
        seat_mm_min=6.5, seat_mm_max=9.0,
        carat_min=0.50, carat_max=1.80,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Heart heads ───────────────────────────────────────────────────────
    MountEntry(
        sku="HRT-5P-80-100",
        label="Heart 5-prong (cleft v-tip) solitaire head 8.0–10.0 mm",
        shape_families=["heart"],
        seat_mm_min=8.0, seat_mm_max=10.0,
        carat_min=1.00, carat_max=2.20,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=0,
        style_tags=["solitaire"],
    ),
    MountEntry(
        sku="HRT-BZL-80-105",
        label="Heart bezel 8.0–10.5 mm",
        shape_families=["heart"],
        seat_mm_min=8.0, seat_mm_max=10.5,
        carat_min=1.00, carat_max=2.50,
        setting_styles=["bezel"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum", "sterling_silver"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
    # ── Three-stone semi-mounts (round centre + side) ─────────────────────
    MountEntry(
        sku="3ST-R-55-65",
        label="Three-stone round centre 5.5–6.5 mm (2 round side stones)",
        shape_families=["round"],
        seat_mm_min=5.5, seat_mm_max=6.5,
        carat_min=0.60, carat_max=1.10,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=2,
        style_tags=["three_stone"],
    ),
    MountEntry(
        sku="3ST-OV-80-95",
        label="Three-stone oval centre 8.0–9.5 mm (2 round side stones)",
        shape_families=["oval"],
        seat_mm_min=8.0, seat_mm_max=9.5,
        carat_min=1.00, carat_max=2.00,
        setting_styles=["prong"],
        metals=["yellow_gold", "white_gold", "rose_gold", "platinum"],
        accent_count=2,
        style_tags=["three_stone"],
    ),
    # ── Tension / East-West mounts ────────────────────────────────────────
    MountEntry(
        sku="TEN-RND-60-75",
        label="Tension mount round 6.0–7.5 mm",
        shape_families=["round"],
        seat_mm_min=6.0, seat_mm_max=7.5,
        carat_min=0.80, carat_max=1.80,
        setting_styles=["tension"],
        metals=["white_gold", "platinum", "palladium"],
        accent_count=0,
        style_tags=["solitaire", "modern"],
    ),
]


# ---------------------------------------------------------------------------
# Stone dimension helpers
# ---------------------------------------------------------------------------

def _stone_mm_from_input(
    cut: str,
    carat: Optional[float],
    dim_mm: Optional[float],
    material: Optional[str],
) -> tuple[float, str]:
    """Return (primary_mm, description) given carat OR mm input.

    For round cuts, primary_mm is the girdle diameter.
    For other cuts, it is the long-axis length.
    Returns (mm, desc) or raises ValueError.
    """
    if carat is not None and dim_mm is not None:
        raise ValueError("Provide carat OR dim_mm, not both")
    if carat is None and dim_mm is None:
        raise ValueError("One of carat or dim_mm is required")

    if carat is not None:
        mm = mm_from_carat(cut, carat, material=material)
        return mm, f"{carat:.2f} ct → {mm:.2f} mm ({cut})"
    else:
        return float(dim_mm), f"{dim_mm:.2f} mm ({cut})"


# ---------------------------------------------------------------------------
# Mohs-based setting-style preference
# ---------------------------------------------------------------------------

# Soft / brittle gemstones need protective bezel or low-prong settings.
# Mohs < 7 → bezel strongly preferred; tension setting avoided.
# Mohs 7–7.5 → prong acceptable but bezel also recommended.
# Mohs > 7.5 → all settings fine.

_BRITTLE_SPECIES = frozenset({
    "emerald",   # Mohs 7.5–8 but high inclusions / fractures; brittle
    "opal",      # Mohs 5.5–6.5
    "turquoise", # Mohs 5–6
    "lapis_lazuli",
    "amber",
    "coral",
    "pearl",
    "moonstone", # Mohs 6–6.5
})


def _style_suitability(
    setting_style: str,
    mohs: Optional[float],
    material: Optional[str],
) -> tuple[float, list[str]]:
    """Return (bonus, reasons) for a setting style given stone hardness.

    bonus > 0 means the style is recommended.
    bonus < 0 means it is penalised.
    """
    reasons: list[str] = []
    bonus = 0.0

    brittle = material is not None and material.lower() in _BRITTLE_SPECIES

    if mohs is not None:
        soft = mohs < 7.0
        medium = 7.0 <= mohs <= 7.5
    else:
        soft = False
        medium = False

    if soft or brittle:
        if setting_style == "bezel":
            bonus += 2.0
            reasons.append(
                "bezel preferred: protects soft/brittle stone (Mohs "
                + (f"{mohs:.1f}" if mohs else "—") + ")"
            )
        elif setting_style == "tension":
            bonus -= 3.0
            reasons.append(
                "tension setting not recommended for soft/brittle stone"
            )
        elif setting_style == "prong":
            bonus -= 1.0
            reasons.append(
                "prong exposes girdle; bezel is safer for this stone"
            )
    elif medium:
        if setting_style == "bezel":
            bonus += 0.5
            reasons.append("bezel provides extra protection for medium-hardness stone")
    else:
        # Hard stone — all settings fine, small bonus for prong (shows stone)
        if setting_style == "prong":
            bonus += 0.2
            reasons.append("prong setting maximises light return for durable stone")

    return bonus, reasons


# ---------------------------------------------------------------------------
# Core scoring logic
# ---------------------------------------------------------------------------

# Weights
_W_FIT     = 5.0   # fit accuracy (1 / (1 + delta)) scaled
_W_SHAPE   = 4.0   # shape family match
_W_CARAT   = 2.0   # carat range coverage
_W_STYLE   = 2.0   # setting-style suitability


def _score_mount(
    mount: MountEntry,
    stone_mm: float,
    stone_shape: str,
    stone_carat: Optional[float],
    mohs: Optional[float],
    material: Optional[str],
    fit_tolerance_mm: float,
) -> tuple[Optional[dict], Optional[str]]:
    """Score a single mount against the stone.

    Returns (result_dict, None) if accepted, or (None, reject_reason) if hard-rejected.
    """
    reasons: list[str] = []
    reject_reason: Optional[str] = None

    # ── Shape check ──────────────────────────────────────────────────────
    if stone_shape not in mount.shape_families:
        return None, (
            f"shape mismatch: mount accepts {mount.shape_families}, "
            f"stone is {stone_shape!r}"
        )

    # ── Fit / seat check ─────────────────────────────────────────────────
    if stone_mm < mount.seat_mm_min:
        delta = mount.seat_mm_min - stone_mm
        if delta > fit_tolerance_mm:
            return None, (
                f"stone too small: {stone_mm:.2f} mm < seat min "
                f"{mount.seat_mm_min:.2f} mm (gap {delta:.2f} mm)"
            )
    elif stone_mm > mount.seat_mm_max:
        delta = stone_mm - mount.seat_mm_max
        if delta > fit_tolerance_mm:
            return None, (
                f"stone too large: {stone_mm:.2f} mm > seat max "
                f"{mount.seat_mm_max:.2f} mm (gap {delta:.2f} mm)"
            )
    # compute delta to nearest edge (0 if inside range)
    if mount.seat_mm_min <= stone_mm <= mount.seat_mm_max:
        fit_delta = 0.0
        center = (mount.seat_mm_min + mount.seat_mm_max) / 2.0
        # prefer mounts centred near the stone
        center_delta = abs(stone_mm - center)
        reasons.append(
            f"stone {stone_mm:.2f} mm is within seat range "
            f"{mount.seat_mm_min:.2f}–{mount.seat_mm_max:.2f} mm"
        )
    else:
        fit_delta = (
            (mount.seat_mm_min - stone_mm)
            if stone_mm < mount.seat_mm_min
            else (stone_mm - mount.seat_mm_max)
        )
        center_delta = fit_delta
        reasons.append(
            f"near-fit: stone {stone_mm:.2f} mm is {fit_delta:.2f} mm outside "
            f"seat range {mount.seat_mm_min:.2f}–{mount.seat_mm_max:.2f} mm"
        )

    # ── Carat range check ────────────────────────────────────────────────
    if stone_carat is not None:
        if stone_carat < mount.carat_min:
            carat_gap = mount.carat_min - stone_carat
            if carat_gap > 0.15:
                return None, (
                    f"stone {stone_carat:.2f} ct below mount minimum "
                    f"{mount.carat_min:.2f} ct"
                )
        elif stone_carat > mount.carat_max:
            carat_gap = stone_carat - mount.carat_max
            if carat_gap > 0.15:
                return None, (
                    f"stone {stone_carat:.2f} ct exceeds mount maximum "
                    f"{mount.carat_max:.2f} ct"
                )

    # ── Shape bonus ──────────────────────────────────────────────────────
    reasons.append(f"shape family matches: {stone_shape!r}")

    # ── Setting-style suitability ────────────────────────────────────────
    style_bonus_total = 0.0
    for style in mount.setting_styles:
        sb, sr = _style_suitability(style, mohs, material)
        style_bonus_total += sb
        reasons.extend(sr)

    # ── Composite score ───────────────────────────────────────────────────
    # fit_score: max when delta=0, decays as delta increases
    fit_score = _W_FIT * (1.0 / (1.0 + center_delta))
    shape_score = _W_SHAPE  # full score if shape matches (hard reject otherwise)
    carat_score = _W_CARAT  # full score (hard reject if too far outside)
    style_score = _W_STYLE * max(0.0, (style_bonus_total + 3.0) / 6.0)  # normalise to [0,1]

    total = fit_score + shape_score + carat_score + style_score

    return {
        "sku": mount.sku,
        "label": mount.label,
        "shape_families": mount.shape_families,
        "seat_mm_range": [mount.seat_mm_min, mount.seat_mm_max],
        "carat_range": [mount.carat_min, mount.carat_max],
        "setting_styles": mount.setting_styles,
        "metals": mount.metals,
        "accent_count": mount.accent_count,
        "style_tags": mount.style_tags,
        "fit_mm_delta": round(fit_delta, 4),
        "score": round(total, 4),
        "why": reasons,
        "reject_reason": None,
    }, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_mounts(
    cut: str,
    *,
    carat: Optional[float] = None,
    dim_mm: Optional[float] = None,
    material: Optional[str] = None,
    fit_tolerance_mm: float = _DEFAULT_FIT_TOLERANCE_MM,
    catalog: Optional[list] = None,
) -> dict:
    """Find and rank compatible mounts for a loose stone.

    Parameters
    ----------
    cut : str
        Gemstone cut (one of ``GEMSTONE_CUTS``).
    carat : float, optional
        Stone carat weight.  Provide either ``carat`` or ``dim_mm``.
    dim_mm : float, optional
        Primary stone dimension in mm (diameter for round; long-axis for others).
    material : str, optional
        Gem material name (e.g. ``"opal"``), used for Mohs hardness lookup.
    fit_tolerance_mm : float
        Accept near-misses within this mm window outside the seat range.
        Default 0.35 mm.
    catalog : list, optional
        Override catalog (for testing).  Defaults to ``_MOUNT_CATALOG``.

    Returns
    -------
    dict
        ``{"ok": True, "best": {...} | None, "alternatives": [...], "rejected": [...],
           "stone_mm": float, "stone_shape": str}``
        or ``{"ok": False, "reason": "..."}`` on validation failure.
    """
    # ── Validate inputs ───────────────────────────────────────────────────
    if not cut:
        return {"ok": False, "reason": "cut is required"}
    if cut not in GEMSTONE_CUTS:
        return {"ok": False, "reason": f"unknown cut {cut!r}"}
    if carat is not None and dim_mm is not None:
        return {"ok": False, "reason": "provide carat OR dim_mm, not both"}
    if carat is None and dim_mm is None:
        return {"ok": False, "reason": "one of carat or dim_mm is required"}
    if carat is not None:
        try:
            carat = float(carat)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "carat must be a number"}
        if carat <= 0:
            return {"ok": False, "reason": "carat must be positive"}
    if dim_mm is not None:
        try:
            dim_mm = float(dim_mm)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "dim_mm must be a number"}
        if dim_mm <= 0:
            return {"ok": False, "reason": "dim_mm must be positive"}
    if fit_tolerance_mm < 0:
        return {"ok": False, "reason": "fit_tolerance_mm must be >= 0"}

    # ── Resolve stone dimensions ──────────────────────────────────────────
    try:
        stone_mm, _size_desc = _stone_mm_from_input(cut, carat, dim_mm, material)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}

    # Also compute carat from mm if only mm was given (for range checks).
    # Mount catalog carat ranges are calibrated to diamond (the standard),
    # so always derive using diamond density even if the stone is a different
    # material.  The material parameter only affects the physical carat weight,
    # not the seat-size range of the mount.
    if carat is None and dim_mm is not None:
        try:
            carat = carat_from_mm(cut, stone_mm)  # diamond-equivalent carat
        except Exception:
            carat = None

    stone_shape = _cut_to_shape_family(cut)

    # ── Mohs lookup ───────────────────────────────────────────────────────
    mohs: Optional[float] = None
    if material:
        mohs = _mohs_for_material(material)

    # ── Score each mount ──────────────────────────────────────────────────
    use_catalog = catalog if catalog is not None else _MOUNT_CATALOG

    accepted: list[dict] = []
    rejected: list[dict] = []

    for mount in use_catalog:
        result, reason = _score_mount(
            mount, stone_mm, stone_shape, carat, mohs, material, fit_tolerance_mm
        )
        if result is not None:
            accepted.append(result)
        else:
            rejected.append({
                "sku": mount.sku,
                "label": mount.label,
                "reject_reason": reason,
            })

    # ── Sort: score descending; ties broken by sku (deterministic) ────────
    accepted.sort(key=lambda r: (-r["score"], r["sku"]))

    best = accepted[0] if accepted else None
    alternatives = accepted[1:]

    return {
        "ok": True,
        "stone_mm": round(stone_mm, 4),
        "stone_shape": stone_shape,
        "stone_carat": round(carat, 4) if carat is not None else None,
        "best": best,
        "alternatives": alternatives,
        "rejected": rejected,
    }


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

jewelry_find_mounts_spec = ToolSpec(
    name="jewelry_find_mounts",
    description=(
        "Given a loose gemstone (cut + carat or mm size), rank compatible "
        "semi-mounts and heads from the Kerf mount catalog by seat fit, "
        "shape match, setting-style suitability for the stone's hardness, "
        "and carat range. Returns the best match plus ranked alternatives, "
        "with per-candidate fit_mm_delta, score, and reason notes. "
        "Soft or brittle stones (opal, emerald, moonstone, turquoise, etc.) "
        "are automatically ranked toward bezel over prong settings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cut": {
                "type": "string",
                "description": (
                    "Gemstone cut name (e.g. 'round_brilliant', 'oval', "
                    "'cushion', 'princess', 'emerald', 'pear', 'marquise')."
                ),
            },
            "carat": {
                "type": "number",
                "description": "Stone carat weight.  Provide carat OR dim_mm.",
            },
            "dim_mm": {
                "type": "number",
                "description": (
                    "Primary stone dimension in mm (diameter for round; "
                    "long-axis for other cuts).  Provide carat OR dim_mm."
                ),
            },
            "material": {
                "type": "string",
                "description": (
                    "Gem material name (e.g. 'diamond', 'ruby', 'opal', "
                    "'emerald') used for hardness-based setting advice."
                ),
            },
            "fit_tolerance_mm": {
                "type": "number",
                "description": (
                    "mm window outside the seat range that is still accepted "
                    "as a near-miss.  Default 0.35 mm."
                ),
            },
        },
        "required": ["cut"],
    },
)


@register(jewelry_find_mounts_spec, write=False)
async def run_jewelry_find_mounts(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    cut = a.get("cut", "").strip()
    carat = a.get("carat", None)
    dim_mm = a.get("dim_mm", None)
    material = a.get("material", None)
    fit_tolerance_mm = a.get("fit_tolerance_mm", _DEFAULT_FIT_TOLERANCE_MM)

    if not cut:
        return err_payload("cut is required", "BAD_ARGS")

    try:
        fit_tolerance_mm = float(fit_tolerance_mm)
    except (TypeError, ValueError):
        return err_payload("fit_tolerance_mm must be a number", "BAD_ARGS")

    result = find_mounts(
        cut,
        carat=carat,
        dim_mm=dim_mm,
        material=material,
        fit_tolerance_mm=fit_tolerance_mm,
    )

    if not result["ok"]:
        return err_payload(result["reason"], "BAD_ARGS")

    return ok_payload(result)
