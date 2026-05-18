"""
Pre-baked SKY130 design-rule subset for the kerf-silicon DRC engine.

All dimensions in nanometres (nm) unless noted otherwise.

Sources: SkyWater SKY130 PDK design rules, tech file revision B.
  https://skywater-pdk.readthedocs.io/en/main/rules/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RuleFamily(str, Enum):
    WIDTH = "width"
    SPACING = "spacing"
    ENCLOSURE = "enclosure"
    DENSITY = "density"
    OVERLAP = "overlap"


@dataclass
class WidthRule:
    """Minimum width for a single layer."""
    family: RuleFamily = field(default=RuleFamily.WIDTH, init=False)
    rule_name: str = ""
    layer: str = ""
    min_nm: float = 0.0
    description: str = ""


@dataclass
class SpacingRule:
    """Minimum spacing between same-layer shapes."""
    family: RuleFamily = field(default=RuleFamily.SPACING, init=False)
    rule_name: str = ""
    layer: str = ""
    min_nm: float = 0.0
    description: str = ""


@dataclass
class EnclosureRule:
    """Outer layer must enclose inner layer by at least enc_nm on all sides."""
    family: RuleFamily = field(default=RuleFamily.ENCLOSURE, init=False)
    rule_name: str = ""
    outer_layer: str = ""
    inner_layer: str = ""
    enc_nm: float = 0.0
    description: str = ""


@dataclass
class DensityRule:
    """Layer polygon density must stay within [min_pct, max_pct] of tile area."""
    family: RuleFamily = field(default=RuleFamily.DENSITY, init=False)
    rule_name: str = ""
    layer: str = ""
    min_pct: float = 0.0   # e.g. 20.0  → 20 %
    max_pct: float = 100.0  # e.g. 80.0 → 80 %
    tile_nm: float = 700_000.0  # default 700 µm tile per SKY130 density grid
    description: str = ""


@dataclass
class OverlapRule:
    """Shapes on layer_a and layer_b must NOT overlap."""
    family: RuleFamily = field(default=RuleFamily.OVERLAP, init=False)
    rule_name: str = ""
    layer_a: str = ""
    layer_b: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# SKY130 rule subset (~15 rules)
# ---------------------------------------------------------------------------
#
# Layers (abbreviated):
#   nwell      — N-well implant
#   diff       — active diffusion (COMP in some PDK references)
#   poly       — polysilicon gate
#   li1        — local interconnect (LI / M0)
#   met1       — Metal 1
#   met2       — Metal 2
#   via        — via between met1 and met2
#   npc        — nitride poly cut (salicide block)

SKY130_RULES: list = [
    # --- Width rules ---
    WidthRule(
        rule_name="nwell.1",
        layer="nwell",
        min_nm=840,
        description="nwell minimum width 0.84 µm",
    ),
    WidthRule(
        rule_name="diff.1",
        layer="diff",
        min_nm=150,
        description="diff minimum width 0.15 µm",
    ),
    WidthRule(
        rule_name="poly.1",
        layer="poly",
        min_nm=150,
        description="poly minimum width 0.15 µm",
    ),
    WidthRule(
        rule_name="li1.1",
        layer="li1",
        min_nm=170,
        description="li1 minimum width 0.17 µm",
    ),
    WidthRule(
        rule_name="met1.1",
        layer="met1",
        min_nm=140,
        description="met1 minimum width 0.14 µm",
    ),
    WidthRule(
        rule_name="met2.1",
        layer="met2",
        min_nm=140,
        description="met2 minimum width 0.14 µm",
    ),

    # --- Spacing rules ---
    SpacingRule(
        rule_name="nwell.2",
        layer="nwell",
        min_nm=1270,
        description="nwell to nwell spacing 1.27 µm",
    ),
    SpacingRule(
        rule_name="diff.2",
        layer="diff",
        min_nm=270,
        description="diff to diff spacing 0.27 µm",
    ),
    SpacingRule(
        rule_name="poly.2",
        layer="poly",
        min_nm=210,
        description="poly to poly spacing 0.21 µm",
    ),
    SpacingRule(
        rule_name="met1.2",
        layer="met1",
        min_nm=140,
        description="met1 to met1 spacing 0.14 µm",
    ),
    SpacingRule(
        rule_name="met2.2",
        layer="met2",
        min_nm=140,
        description="met2 to met2 spacing 0.14 µm",
    ),

    # --- Enclosure rules ---
    EnclosureRule(
        rule_name="nwell.enc.diff",
        outer_layer="nwell",
        inner_layer="diff",
        enc_nm=180,
        description="nwell must enclose diff by 0.18 µm on all sides",
    ),
    EnclosureRule(
        rule_name="li1.enc.via",
        outer_layer="li1",
        inner_layer="via",
        enc_nm=80,
        description="li1 must enclose via by 0.08 µm on all sides",
    ),

    # --- Density rules ---
    DensityRule(
        rule_name="met1.dens",
        layer="met1",
        min_pct=20.0,
        max_pct=80.0,
        tile_nm=700_000.0,
        description="met1 density must be between 20 % and 80 % per 700 µm tile",
    ),
    DensityRule(
        rule_name="met2.dens",
        layer="met2",
        min_pct=20.0,
        max_pct=80.0,
        tile_nm=700_000.0,
        description="met2 density must be between 20 % and 80 % per 700 µm tile",
    ),

    # --- Overlap (forbidden) rules ---
    OverlapRule(
        rule_name="nwell.novlp.pwell",
        layer_a="nwell",
        layer_b="pwell",
        description="nwell and pwell must not overlap (same potential conflict)",
    ),
]
