"""
kerf_cad_core.jewelry.chain
============================

Parametric chain / bracelet / necklace generator.

Provides:
  - Chain link generators (cable, curb, figaro, rope, box, snake, byzantine,
    mariner/anchor, rolo, bismark, wheat, herringbone, omega, popcorn,
    ball, singapore) — each fully parametric; emits a node-spec describing the
    repeating link geometry and overall chain assembly.
  - Clasps (lobster, spring_ring, toggle, box_clasp) as parametric attachment
    nodes.
  - Standard-length helpers (bracelet 7"/18 cm, necklace 16/18/20/24",
    anklet 9–11", men's 20–30", choker/collar sizes) with link-count ↔ length
    round-trips.
  - Wire-gauge preset table (fine/medium/heavy per style) via
    ``gauge_preset`` parameter.
  - Metal weight estimator: ``chain_weight_estimate``.
  - LLM tools: jewelry_create_chain (write), jewelry_chain_length (read).

Composed chain pieces (v3)
---------------------------
Higher-level builders that compose ``chain_assembly`` link hints to describe
more complex finished pieces.  Each returns a *composed spec* dict with an
``op`` of the piece type; the dict carries one or more ``chain_assembly``
sub-specs (``chains`` list) plus piece-specific fields.  The occtWorker
evaluates these as ``opChainAssembly`` calls with the extra overlay hints.

  tennis_bracelet_spec       — continuous stone line in flexible link mount
  station_necklace_spec      — periodic stone stations on a thin chain
  lariat_spec                — open-ended Y-necklace with a slide
  charm_bracelet_spec        — base chain + N jump-ring attach points
  multi_strand_spec          — 2–5 parallel chains joined at connectors
  extender_chain_spec        — adjustable extender with end loops

LLM tools registered (v3, composed pieces)
--------------------------------------------
    jewelry_create_tennis_bracelet
    jewelry_create_station_necklace
    jewelry_create_lariat
    jewelry_create_charm_bracelet
    jewelry_create_multi_strand
    jewelry_create_extender_chain

Geometry strategy
-----------------
Chain links are geometrically complex interlocking tori / swept paths.  Rather
than hand-rolling OCCT here, every link/clasp function returns a *node spec*
dict.  The occtWorker's ``opChainLink`` / ``opChainAssembly`` / ``opClasp``
operators consume these dicts and tessellate the geometry.  This matches the
pattern used by ring_shank and gem_seat.

Node-spec schema (``chain_assembly``)
--------------------------------------
::

    {
      "id":              "<node-id>",
      "op":              "chain_assembly",
      "style":           "<link style name>",

      // Link geometry params
      "wire_gauge_mm":   float,      # wire / rod diameter, mm
      "link_length_mm":  float,      # outer length of one link, mm
      "link_width_mm":   float,      # outer width of one link, mm
      "link_count":      int,        # number of links in the chain

      // Style-specific hints used by the worker (may be absent for some styles)
      "link_hints":      dict,       # see per-style docs below

      // Assembly hints
      "total_length_mm": float,      # = link_pitch_mm × link_count
      "link_pitch_mm":   float,      # centre-to-centre advance per link
      "open_ends":       bool,       # True → leave both end-links open for clasp attachment

      // Optional graduated flag (links scale linearly from centre toward ends)
      "graduated":       bool,       # optional — default absent/false

      // Optional clasp sub-node (inlined, not a separate feature node)
      "clasp":           dict | null
    }

Node-spec schema (``clasp`` — inline sub-node or standalone)
-------------------------------------------------------------
::

    {
      "id":              "<node-id>",
      "op":              "clasp",
      "style":           "<clasp style>",
      "wire_gauge_mm":   float,      # matching wire gauge
      "clasp_hints":     dict        # style-specific params
    }

LLM tools registered
---------------------
    jewelry_create_chain
    jewelry_chain_length
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    read_feature_content,
    append_feature_node,
    next_node_id,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PI = math.pi

# Supported link styles
_VALID_LINK_STYLES = frozenset([
    "cable",
    "curb",
    "figaro",
    "rope",
    "box",
    "snake",
    "byzantine",
    "mariner",      # also known as anchor chain
    # v2 additions
    "rolo",         # round/belcher — wide round links, 1:1 aspect
    "bismark",      # multi-row parallel interlocked links
    "wheat",        # spiga — twisted figure-8 links in a helical spiral
    "herringbone",  # flat V-shaped woven surface
    "omega",        # solid curved plates on a fabric/box spine (distinct from snake)
    "popcorn",      # bumpy spherical bead-like links
    "ball",         # smooth spherical beads on wire (bead chain)
    "singapore",    # twisted curb — diagonal figure-8 twist pattern
])

# Style aliases (accepted but normalised)
_STYLE_ALIASES: dict[str, str] = {
    "anchor":          "mariner",
    "diamond_cut_curb": "curb",  # handled via link_hints
    "belcher":         "rolo",
    "spiga":           "wheat",
    "bead":            "ball",
    "bead_chain":      "ball",
}

# Supported clasp styles
_VALID_CLASP_STYLES = frozenset([
    "lobster",
    "spring_ring",
    "toggle",
    "box_clasp",
])

# Standard chain lengths (name → mm)
_STANDARD_LENGTHS_MM: dict[str, float] = {
    # Anklets
    "anklet_9in":      228.6,
    "anklet_9.5in":    241.3,
    "anklet_10in":     254.0,
    "anklet_10.5in":   266.7,
    "anklet_11in":     279.4,
    # Bracelets
    "bracelet_6.5in":  165.1,
    "bracelet_7in":    177.8,
    "bracelet_7.5in":  190.5,
    "bracelet_8in":    203.2,
    # Choker / collar
    "choker_14in":     355.6,
    "choker_16in":     406.4,
    # Necklaces
    "collar_14in":     355.6,
    "collar_16in":     406.4,
    "princess_18in":   457.2,
    "matinee_20in":    508.0,
    "matinee_22in":    558.8,
    "opera_24in":      609.6,
    "opera_28in":      711.2,
    "rope_30in":       762.0,
    "rope_36in":       914.4,
    # Men's chain lengths (longer necklaces)
    "mens_20in":       508.0,
    "mens_22in":       558.8,
    "mens_24in":       609.6,
    "mens_26in":       660.4,
    "mens_28in":       711.2,
    "mens_30in":       762.0,
    # Metric bracelet
    "bracelet_18cm":   180.0,
    "bracelet_19cm":   190.0,
    "bracelet_20cm":   200.0,
    # Metric necklace
    "necklace_40cm":   400.0,
    "necklace_45cm":   450.0,
    "necklace_50cm":   500.0,
    "necklace_60cm":   600.0,
    # Metric men's / long
    "necklace_55cm":   550.0,
    "necklace_70cm":   700.0,
    "necklace_75cm":   750.0,
}

# Wire-gauge to typical link-length multiplier (outer link length ≈ multiplier × wire_gauge)
# These are empirical defaults — the LLM/user can override.
_STYLE_LINK_MULTIPLIERS: dict[str, tuple[float, float]] = {
    # (length_mult, width_mult) — both relative to wire_gauge_mm
    "cable":      (3.5, 2.5),
    "curb":       (3.0, 2.5),
    "figaro":     (3.5, 2.5),   # mixed links (3 short + 1 long)
    "rope":       (2.5, 2.0),
    "box":        (2.0, 2.0),
    "snake":      (2.2, 2.8),
    "byzantine":  (3.8, 2.5),
    "mariner":    (4.0, 2.8),
    # v2 additions
    "rolo":       (2.5, 2.5),   # near-round links; roughly 1:1 aspect
    "bismark":    (3.2, 4.0),   # wide multi-row; width dominates
    "wheat":      (3.0, 2.2),   # spiga twist; compact width
    "herringbone":(1.5, 3.5),   # short pitch, very wide flat surface
    "omega":      (1.8, 4.5),   # plate-width >> gauge; very wide flat collar
    "popcorn":    (3.0, 3.0),   # near-spherical bumps; square aspect
    "ball":       (2.8, 2.8),   # spherical beads; square aspect
    "singapore":  (3.0, 2.5),   # twisted curb; similar to curb defaults
}

# ---------------------------------------------------------------------------
# Gauge presets: named weight classes → wire_gauge_mm per style
# ---------------------------------------------------------------------------

#: Gauge preset table: style → {"fine": mm, "medium": mm, "heavy": mm}
#: Values represent typical industry wire gauges in mm.
GAUGE_PRESETS: dict[str, dict[str, float]] = {
    "cable":      {"fine": 0.7,  "medium": 1.0,  "heavy": 1.5},
    "curb":       {"fine": 0.8,  "medium": 1.2,  "heavy": 1.8},
    "figaro":     {"fine": 0.8,  "medium": 1.1,  "heavy": 1.6},
    "rope":       {"fine": 0.6,  "medium": 0.9,  "heavy": 1.3},
    "box":        {"fine": 0.8,  "medium": 1.2,  "heavy": 1.8},
    "snake":      {"fine": 0.9,  "medium": 1.4,  "heavy": 2.0},
    "byzantine":  {"fine": 0.7,  "medium": 1.0,  "heavy": 1.4},
    "mariner":    {"fine": 1.0,  "medium": 1.5,  "heavy": 2.2},
    "rolo":       {"fine": 1.0,  "medium": 1.5,  "heavy": 2.2},
    "bismark":    {"fine": 0.9,  "medium": 1.3,  "heavy": 1.9},
    "wheat":      {"fine": 0.7,  "medium": 1.0,  "heavy": 1.5},
    "herringbone":{"fine": 1.0,  "medium": 1.5,  "heavy": 2.2},
    "omega":      {"fine": 1.2,  "medium": 1.8,  "heavy": 2.5},
    "popcorn":    {"fine": 1.0,  "medium": 1.5,  "heavy": 2.0},
    "ball":       {"fine": 1.0,  "medium": 1.5,  "heavy": 2.5},
    "singapore":  {"fine": 0.8,  "medium": 1.1,  "heavy": 1.6},
}

_VALID_GAUGE_WEIGHTS = frozenset(["fine", "medium", "heavy"])


# ---------------------------------------------------------------------------
# Link-pitch helpers
# ---------------------------------------------------------------------------

def link_pitch(style: str, link_length_mm: float, link_width_mm: float,
               wire_gauge_mm: float) -> float:
    """Return centre-to-centre advance per link in mm.

    The pitch is the distance the chain advances for each link.  For most
    interlocking-ring styles the pitch is roughly the inner length of the link
    (= link_length − 2 × wire_gauge) because each new link passes through the
    previous one.

    Parameters
    ----------
    style : str
    link_length_mm : float   Outer link length.
    link_width_mm  : float   Outer link width (used for box/snake flat links).
    wire_gauge_mm  : float   Wire diameter.

    Returns
    -------
    float   Pitch in mm.
    """
    inner_len = link_length_mm - 2.0 * wire_gauge_mm
    if style in ("box", "snake", "omega"):
        # Box, snake, omega: links/plates sit side-by-side along the length;
        # pitch ≈ link_length / 2 (alternating orientation overlap)
        return max(link_length_mm * 0.5, wire_gauge_mm * 1.1)
    elif style == "byzantine":
        # Byzantine has a more compact, dense pattern
        return max(inner_len * 0.7, wire_gauge_mm * 1.1)
    elif style in ("rope", "wheat"):
        # Rope / wheat (spiga): continuous twist; pitch per link is quite small
        return max(inner_len * 0.5, wire_gauge_mm * 1.1)
    elif style == "herringbone":
        # Herringbone: extremely flat; very short pitch (nearly continuous surface)
        return max(link_length_mm * 0.4, wire_gauge_mm * 1.1)
    elif style == "bismark":
        # Bismark: multi-row; slightly more compact than cable
        return max(inner_len * 0.8, wire_gauge_mm * 1.1)
    elif style in ("ball", "popcorn"):
        # Ball / popcorn: beads sit centre-to-centre ≈ link_length
        return max(link_length_mm, wire_gauge_mm * 1.1)
    else:
        return max(inner_len, wire_gauge_mm * 1.1)


# ---------------------------------------------------------------------------
# Per-style link-hints builders
# ---------------------------------------------------------------------------

def _cable_hints(wire_gauge_mm: float, link_length_mm: float,
                 link_width_mm: float) -> dict:
    """Alternating round-wire ovals, every other link rotated 90°."""
    aspect = link_length_mm / link_width_mm if link_width_mm > 0 else 1.4
    return {
        "type": "cable",
        "aspect_ratio": round(aspect, 3),
        "cross_section": "round",
        "alternating_rotation_deg": 90,
    }


def _curb_hints(wire_gauge_mm: float, link_length_mm: float,
                link_width_mm: float, *, diamond_cut: bool = False,
                flat: bool = False) -> dict:
    """Curb (flat/diamond-cut optional): twisted links lying flat."""
    h: dict = {
        "type": "curb",
        "cross_section": "round",
        "twist_deg": 180,
        "flat_face": flat,
        "diamond_cut": diamond_cut,
    }
    if diamond_cut:
        # Diamond-cut: faceted flat faces along the outer surface
        h["diamond_facets"] = 4
    if flat:
        # Flat curb: wire is flattened to roughly 60% of gauge in the thin axis
        h["flat_ratio"] = 0.6
    return h


def _figaro_hints(wire_gauge_mm: float, link_length_mm: float,
                  link_width_mm: float, *,
                  long_link_ratio: float = 2.5) -> dict:
    """Figaro: repeating pattern of (typically) 3 short + 1 elongated link."""
    short_len = link_length_mm
    long_len = link_length_mm * long_link_ratio
    return {
        "type": "figaro",
        "pattern": [1, 1, 1, long_link_ratio],  # 3 short, 1 long (ratio)
        "short_link_length_mm": round(short_len, 3),
        "long_link_length_mm": round(long_len, 3),
        "cross_section": "round",
    }


def _rope_hints(wire_gauge_mm: float, link_length_mm: float,
                link_width_mm: float, *, twist_angle_deg: float = 45.0) -> dict:
    """Rope: small oval links twisted into a continuous helical spiral."""
    return {
        "type": "rope",
        "twist_angle_deg": twist_angle_deg,
        "cross_section": "round",
        "helix_radius_mult": 0.55,   # helix radius = mult × link_width
    }


def _box_hints(wire_gauge_mm: float, link_length_mm: float,
               link_width_mm: float) -> dict:
    """Box: square cross-section tubes, joined end-to-end with a rotary joint."""
    tube_wall = round(wire_gauge_mm * 0.4, 3)
    return {
        "type": "box",
        "cross_section": "square",
        "tube_wall_mm": tube_wall,
        "inner_width_mm": round(link_width_mm - 2 * tube_wall, 3),
    }


def _snake_hints(wire_gauge_mm: float, link_length_mm: float,
                 link_width_mm: float) -> dict:
    """Snake (omega): wide flat scalloped elements on a fine box core."""
    scale_width = round(link_width_mm * 1.2, 3)
    return {
        "type": "snake",
        "cross_section": "scalloped_flat",
        "scale_width_mm": scale_width,
        "scale_height_mm": round(wire_gauge_mm * 0.8, 3),
        "core_width_mm": round(link_width_mm * 0.35, 3),
    }


def _byzantine_hints(wire_gauge_mm: float, link_length_mm: float,
                     link_width_mm: float) -> dict:
    """Byzantine: complex repeating 4-link cluster with locking side rings."""
    return {
        "type": "byzantine",
        "cross_section": "round",
        "cluster_links": 4,    # 4 links per pattern unit
        "side_ring_id_mult": 1.0,  # inner diameter = wire_gauge × mult
        "pattern_unit_length_mm": round(link_length_mm * 2.8, 3),
    }


def _mariner_hints(wire_gauge_mm: float, link_length_mm: float,
                   link_width_mm: float) -> dict:
    """Mariner/anchor: oval links with a perpendicular central bar (stabiliser)."""
    bar_width = round(link_width_mm - 2 * wire_gauge_mm, 3)
    return {
        "type": "mariner",
        "cross_section": "round",
        "central_bar": True,
        "central_bar_width_mm": max(bar_width, wire_gauge_mm),
        "central_bar_diameter_mm": round(wire_gauge_mm * 0.8, 3),
    }


def _rolo_hints(wire_gauge_mm: float, link_length_mm: float,
                link_width_mm: float) -> dict:
    """Rolo (belcher): wide round links with near-1:1 aspect; alternating 90° rotation."""
    aspect = link_length_mm / link_width_mm if link_width_mm > 0 else 1.0
    return {
        "type": "rolo",
        "cross_section": "round",
        "aspect_ratio": round(aspect, 3),
        "alternating_rotation_deg": 90,
        "inner_diameter_mm": round(link_width_mm - 2.0 * wire_gauge_mm, 3),
    }


def _bismark_hints(wire_gauge_mm: float, link_length_mm: float,
                   link_width_mm: float, *, rows: int = 2) -> dict:
    """Bismark: multiple parallel rows of interlocked oval links woven together."""
    return {
        "type": "bismark",
        "cross_section": "round",
        "rows": rows,
        "row_spacing_mm": round(link_width_mm / max(rows, 1), 3),
        "alternating_rotation_deg": 90,
    }


def _wheat_hints(wire_gauge_mm: float, link_length_mm: float,
                 link_width_mm: float) -> dict:
    """Wheat (spiga): figure-8 twisted links spiralling into a rope-like strand."""
    return {
        "type": "wheat",
        "cross_section": "round",
        "twist_angle_deg": 45.0,          # default spiga helix angle
        "figure8_ratio": round(link_length_mm / max(link_width_mm, wire_gauge_mm), 3),
        "helix_radius_mult": 0.45,        # helix radius = mult × link_width
    }


def _herringbone_hints(wire_gauge_mm: float, link_length_mm: float,
                       link_width_mm: float) -> dict:
    """Herringbone: flat V-shaped woven surface; no visible individual links."""
    return {
        "type": "herringbone",
        "cross_section": "flat",
        "surface_width_mm": round(link_width_mm, 3),
        "v_angle_deg": 45.0,              # angle of the V chevron
        "layer_count": 2,                 # doubled layer for classic herringbone
        "thickness_mm": round(wire_gauge_mm * 0.5, 3),
    }


def _omega_hints(wire_gauge_mm: float, link_length_mm: float,
                 link_width_mm: float) -> dict:
    """Omega: solid curved metal plates on a fine box/fabric core spine.

    Note: the existing ``snake`` style uses ``type='snake'`` for scalloped
    elements.  This ``omega`` style explicitly uses curved plates — a distinct
    construction mapped onto the same ``cross_section='scalloped_flat'`` hint
    so the worker renders a similar flat-plate geometry.
    """
    plate_w = round(link_width_mm * 1.1, 3)
    return {
        "type": "omega",
        "cross_section": "scalloped_flat",
        "plate_width_mm": plate_w,
        "plate_height_mm": round(wire_gauge_mm * 0.6, 3),
        "core_width_mm": round(link_width_mm * 0.25, 3),
        "plate_curvature": "convex",      # plates curve outward
    }


def _popcorn_hints(wire_gauge_mm: float, link_length_mm: float,
                   link_width_mm: float) -> dict:
    """Popcorn: bumpy spheroidal bead-like links, wider than they are long."""
    sphere_d = round(min(link_length_mm, link_width_mm), 3)
    return {
        "type": "popcorn",
        "cross_section": "round",
        "sphere_diameter_mm": sphere_d,
        "neck_diameter_mm": round(wire_gauge_mm * 1.2, 3),
        "texture": "smooth_sphere",
    }


def _ball_hints(wire_gauge_mm: float, link_length_mm: float,
                link_width_mm: float) -> dict:
    """Ball/bead chain: smooth spherical beads connected by short cylindrical necks."""
    bead_d = round(min(link_length_mm, link_width_mm), 3)
    neck_d = round(wire_gauge_mm * 0.9, 3)
    return {
        "type": "ball",
        "cross_section": "round",
        "bead_diameter_mm": bead_d,
        "neck_diameter_mm": neck_d,
        "neck_length_mm": round(wire_gauge_mm * 0.5, 3),
        "texture": "smooth_sphere",
    }


def _singapore_hints(wire_gauge_mm: float, link_length_mm: float,
                     link_width_mm: float) -> dict:
    """Singapore (twisted curb): figure-8 links twisted 90° — diagonal facets."""
    return {
        "type": "singapore",
        "cross_section": "round",
        "twist_deg": 90,
        "diamond_facets": 0,              # no diamond-cut; natural twist reflection
        "diagonal_angle_deg": 45.0,
        "flat_face": False,
    }


_LINK_HINT_BUILDERS = {
    "cable":      _cable_hints,
    "curb":       _curb_hints,
    "figaro":     _figaro_hints,
    "rope":       _rope_hints,
    "box":        _box_hints,
    "snake":      _snake_hints,
    "byzantine":  _byzantine_hints,
    "mariner":    _mariner_hints,
    # v2 additions
    "rolo":       _rolo_hints,
    "bismark":    _bismark_hints,
    "wheat":      _wheat_hints,
    "herringbone":_herringbone_hints,
    "omega":      _omega_hints,
    "popcorn":    _popcorn_hints,
    "ball":       _ball_hints,
    "singapore":  _singapore_hints,
}

# kwargs forwarded to each hint builder (subset that each style accepts)
_STYLE_EXTRA_KWARGS: dict[str, set[str]] = {
    "curb":    {"diamond_cut", "flat"},
    "figaro":  {"long_link_ratio"},
    "rope":    {"twist_angle_deg"},
    "bismark": {"rows"},
}


# ---------------------------------------------------------------------------
# Per-style clasp hints
# ---------------------------------------------------------------------------

def _lobster_hints(wire_gauge_mm: float) -> dict:
    body_len = round(wire_gauge_mm * 6.0, 3)
    body_w   = round(wire_gauge_mm * 3.5, 3)
    return {
        "type": "lobster",
        "body_length_mm": body_len,
        "body_width_mm":  body_w,
        "spring_type":    "lobster_claw_spring",
        "gate_type":      "swivel",
    }


def _spring_ring_hints(wire_gauge_mm: float) -> dict:
    od = round(wire_gauge_mm * 5.0, 3)
    return {
        "type": "spring_ring",
        "outer_diameter_mm": od,
        "inner_diameter_mm": round(od - 2 * wire_gauge_mm, 3),
        "spring_type":       "internal_coil",
    }


def _toggle_hints(wire_gauge_mm: float) -> dict:
    ring_id = round(wire_gauge_mm * 5.5, 3)
    bar_len = round(wire_gauge_mm * 8.0, 3)
    return {
        "type": "toggle",
        "ring_inner_diameter_mm": ring_id,
        "bar_length_mm":          bar_len,
        "bar_diameter_mm":        round(wire_gauge_mm * 1.2, 3),
    }


def _box_clasp_hints(wire_gauge_mm: float) -> dict:
    box_len = round(wire_gauge_mm * 7.0, 3)
    box_w   = round(wire_gauge_mm * 4.0, 3)
    box_h   = round(wire_gauge_mm * 3.0, 3)
    return {
        "type": "box_clasp",
        "box_length_mm":  box_len,
        "box_width_mm":   box_w,
        "box_height_mm":  box_h,
        "tab_spring":     True,
        "safety_catch":   False,
    }


_CLASP_HINT_BUILDERS = {
    "lobster":     _lobster_hints,
    "spring_ring": _spring_ring_hints,
    "toggle":      _toggle_hints,
    "box_clasp":   _box_clasp_hints,
}


# ---------------------------------------------------------------------------
# Core computation: compute_chain_params
# ---------------------------------------------------------------------------

def compute_chain_params(
    style: str,
    wire_gauge_mm: float,
    *,
    link_length_mm: Optional[float] = None,
    link_width_mm: Optional[float] = None,
    link_count: Optional[int] = None,
    total_length_mm: Optional[float] = None,
    standard_length: Optional[str] = None,
    # Style-specific overrides
    diamond_cut: bool = False,
    flat: bool = False,
    long_link_ratio: float = 2.5,
    twist_angle_deg: float = 45.0,
    rows: int = 2,                   # bismark style: number of parallel rows
    # Options
    open_ends: bool = True,
    graduated: bool = False,         # links scale linearly from centre toward ends
    gauge_preset: Optional[str] = None,  # "fine"/"medium"/"heavy" → sets wire_gauge_mm
) -> dict:
    """Compute and validate the full parametric chain spec.

    Exactly one of ``link_count``, ``total_length_mm``, or
    ``standard_length`` must be provided to determine the chain length.
    ``link_length_mm`` and ``link_width_mm`` default to gauge-based values
    when omitted.

    Parameters
    ----------
    style : str
        Chain link style — one of the ``_VALID_LINK_STYLES`` values.
    wire_gauge_mm : float
        Wire / rod cross-section diameter in mm.  Must be > 0.
    link_length_mm : float, optional
        Outer link length in mm.  Defaults to gauge × style multiplier.
    link_width_mm : float, optional
        Outer link width in mm.  Defaults to gauge × style multiplier.
    link_count : int, optional
        Number of links; mutually exclusive with total_length_mm /
        standard_length.
    total_length_mm : float, optional
        Desired total chain length in mm; link_count is derived.
    standard_length : str, optional
        Named standard length key (e.g. "bracelet_7in", "princess_18in").
        Resolves to a total_length_mm then derives link_count.
    diamond_cut : bool
        Curb style only — apply diamond-cut facets.
    flat : bool
        Curb style only — flatten the wire cross-section.
    long_link_ratio : float
        Figaro style only — ratio of the long link's length to the short link.
    twist_angle_deg : float
        Rope/wheat style — helix twist angle per link (degrees).
    rows : int
        Bismark style only — number of parallel link rows (default 2).
    open_ends : bool
        Leave end-links open for clasp attachment (default True).
    graduated : bool
        When True, the ``graduated`` hint is set in the node spec; the worker
        scales links linearly from the centre toward the ends (default False).
    gauge_preset : str, optional
        Named weight class — ``"fine"``, ``"medium"``, or ``"heavy"`` — that
        overrides ``wire_gauge_mm`` with a style-appropriate default from the
        ``GAUGE_PRESETS`` table.  Mutually exclusive with supplying an explicit
        non-zero ``wire_gauge_mm`` that differs from the preset; the preset
        wins when both are supplied.

    Returns
    -------
    dict
        Full chain spec suitable for a ``chain_assembly`` feature node.

    Raises
    ------
    ValueError
        On any invalid or inconsistent parameter.
    """
    # --- Normalise / validate style ---
    style = str(style).strip().lower()
    style = _STYLE_ALIASES.get(style, style)
    if style not in _VALID_LINK_STYLES:
        raise ValueError(
            f"Unknown chain style {style!r}. "
            f"Valid styles: {sorted(_VALID_LINK_STYLES)}. "
            f"Aliases: {sorted(_STYLE_ALIASES)}."
        )

    # --- Apply gauge preset (overrides wire_gauge_mm) ---
    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        wire_gauge_mm = GAUGE_PRESETS[style][gp]

    # --- Validate wire gauge ---
    if wire_gauge_mm <= 0:
        raise ValueError(f"wire_gauge_mm must be > 0; got {wire_gauge_mm}")
    if wire_gauge_mm > 20.0:
        raise ValueError(
            f"wire_gauge_mm={wire_gauge_mm} is unrealistically large (> 20 mm). "
            "Please check the units — the value must be in millimetres."
        )

    # --- Default link dimensions from gauge multipliers ---
    len_mult, wid_mult = _STYLE_LINK_MULTIPLIERS[style]
    if link_length_mm is None:
        link_length_mm = round(wire_gauge_mm * len_mult, 3)
    if link_width_mm is None:
        link_width_mm = round(wire_gauge_mm * wid_mult, 3)

    if link_length_mm <= 0:
        raise ValueError(f"link_length_mm must be > 0; got {link_length_mm}")
    if link_width_mm <= 0:
        raise ValueError(f"link_width_mm must be > 0; got {link_width_mm}")
    if link_length_mm < wire_gauge_mm:
        raise ValueError(
            f"link_length_mm ({link_length_mm}) must be >= wire_gauge_mm ({wire_gauge_mm})"
        )
    if link_width_mm < wire_gauge_mm:
        raise ValueError(
            f"link_width_mm ({link_width_mm}) must be >= wire_gauge_mm ({wire_gauge_mm})"
        )

    # --- Resolve total_length_mm / link_count ---
    _count_sources = sum([
        link_count is not None,
        total_length_mm is not None,
        standard_length is not None,
    ])
    if _count_sources == 0:
        raise ValueError(
            "One of link_count, total_length_mm, or standard_length is required "
            "to determine the chain length."
        )
    if _count_sources > 1:
        raise ValueError(
            "Provide exactly one of link_count, total_length_mm, or standard_length; "
            f"got {_count_sources} sources."
        )

    if standard_length is not None:
        if standard_length not in _STANDARD_LENGTHS_MM:
            raise ValueError(
                f"Unknown standard_length {standard_length!r}. "
                f"Valid names: {sorted(_STANDARD_LENGTHS_MM)}."
            )
        total_length_mm = _STANDARD_LENGTHS_MM[standard_length]

    # Compute pitch
    pitch_mm = link_pitch(style, link_length_mm, link_width_mm, wire_gauge_mm)

    if total_length_mm is not None:
        if total_length_mm <= 0:
            raise ValueError(f"total_length_mm must be > 0; got {total_length_mm}")
        link_count = max(1, round(total_length_mm / pitch_mm))
    else:
        if not isinstance(link_count, int) or link_count < 1:
            raise ValueError(
                f"link_count must be a positive integer; got {link_count!r}"
            )

    # Recompute actual total length from link_count
    actual_total_mm = round(link_count * pitch_mm, 3)

    # --- Build style-specific link hints ---
    builder = _LINK_HINT_BUILDERS[style]
    kwargs: dict = {}
    if style in _STYLE_EXTRA_KWARGS:
        allowed = _STYLE_EXTRA_KWARGS[style]
        if "diamond_cut" in allowed:
            kwargs["diamond_cut"] = diamond_cut
        if "flat" in allowed:
            kwargs["flat"] = flat
        if "long_link_ratio" in allowed:
            kwargs["long_link_ratio"] = long_link_ratio
        if "twist_angle_deg" in allowed:
            kwargs["twist_angle_deg"] = twist_angle_deg
        if "rows" in allowed:
            kwargs["rows"] = rows
    link_hints = builder(wire_gauge_mm, link_length_mm, link_width_mm, **kwargs)

    spec: dict = {
        "style": style,
        "wire_gauge_mm": round(wire_gauge_mm, 4),
        "link_length_mm": round(link_length_mm, 4),
        "link_width_mm": round(link_width_mm, 4),
        "link_count": link_count,
        "link_hints": link_hints,
        "total_length_mm": actual_total_mm,
        "link_pitch_mm": round(pitch_mm, 4),
        "open_ends": open_ends,
    }
    if graduated:
        spec["graduated"] = True
    return spec


# ---------------------------------------------------------------------------
# Clasp computation
# ---------------------------------------------------------------------------

def compute_clasp_params(
    style: str,
    wire_gauge_mm: float,
) -> dict:
    """Return a validated clasp sub-spec dict.

    Parameters
    ----------
    style : str
        One of ``_VALID_CLASP_STYLES``.
    wire_gauge_mm : float
        Matching chain wire gauge in mm.

    Returns
    -------
    dict
        Clasp spec (no ``id`` — assigned by the caller).

    Raises
    ------
    ValueError
        On invalid style or gauge.
    """
    style = str(style).strip().lower()
    if style not in _VALID_CLASP_STYLES:
        raise ValueError(
            f"Unknown clasp style {style!r}. "
            f"Valid: {sorted(_VALID_CLASP_STYLES)}."
        )
    if wire_gauge_mm <= 0:
        raise ValueError(f"wire_gauge_mm must be > 0; got {wire_gauge_mm}")

    hints = _CLASP_HINT_BUILDERS[style](wire_gauge_mm)
    return {
        "op": "clasp",
        "style": style,
        "wire_gauge_mm": round(wire_gauge_mm, 4),
        "clasp_hints": hints,
    }


# ---------------------------------------------------------------------------
# Standard-length helpers (public API)
# ---------------------------------------------------------------------------

def chain_length_to_link_count(
    total_length_mm: float,
    link_pitch_mm: float,
) -> int:
    """Convert a total chain length in mm to a link count.

    Parameters
    ----------
    total_length_mm : float   Target chain length, mm.
    link_pitch_mm   : float   Centre-to-centre advance per link, mm.

    Returns
    -------
    int   Number of links (rounded to nearest integer, minimum 1).

    Raises
    ------
    ValueError
        If either argument is non-positive.
    """
    if total_length_mm <= 0:
        raise ValueError(f"total_length_mm must be > 0; got {total_length_mm}")
    if link_pitch_mm <= 0:
        raise ValueError(f"link_pitch_mm must be > 0; got {link_pitch_mm}")
    return max(1, round(total_length_mm / link_pitch_mm))


def link_count_to_chain_length(
    link_count: int,
    link_pitch_mm: float,
) -> float:
    """Convert a link count to actual chain length in mm.

    Parameters
    ----------
    link_count    : int    Number of links.
    link_pitch_mm : float  Centre-to-centre advance per link, mm.

    Returns
    -------
    float   Total chain length in mm.

    Raises
    ------
    ValueError
        If link_count < 1 or link_pitch_mm <= 0.
    """
    if link_count < 1:
        raise ValueError(f"link_count must be >= 1; got {link_count}")
    if link_pitch_mm <= 0:
        raise ValueError(f"link_pitch_mm must be > 0; got {link_pitch_mm}")
    return round(link_count * link_pitch_mm, 4)


def standard_length_names() -> list[str]:
    """Return sorted list of standard chain-length keys."""
    return sorted(_STANDARD_LENGTHS_MM.keys())


# ---------------------------------------------------------------------------
# Weight estimate helper
# ---------------------------------------------------------------------------

def chain_weight_estimate(
    style: str,
    wire_gauge_mm: float,
    total_length_mm: float,
    density_g_per_cm3: float,
    *,
    fill_factor: Optional[float] = None,
) -> float:
    """Estimate the metal mass of a chain in grams.

    The formula approximates the metal volume per unit length of chain as the
    cross-sectional area of the wire (a circle of diameter ``wire_gauge_mm``)
    multiplied by an empirical *fill factor* that accounts for how much of the
    chain's swept length is actually metal (versus open space between links).

    Formula::

        wire_area   = π × (wire_gauge_mm / 2)² mm²
        volume_mm3  = wire_area × fill_factor × total_length_mm
        mass_g      = volume_mm3 × density_g_per_cm3 × 1e-3

    The fill factor (dimensionless, 0–1) is style-dependent and derived from
    empirical observations of typical chain constructions.  Users may override
    it for custom structures.

    Parameters
    ----------
    style : str
        Chain link style (resolved through aliases).  Used to look up the
        default fill factor.
    wire_gauge_mm : float
        Wire / rod diameter in mm.  Must be > 0.
    total_length_mm : float
        Total chain length in mm.  Must be > 0.
    density_g_per_cm3 : float
        Metal density in g/cm³.  E.g. 18-karat yellow gold ≈ 15.5, sterling
        silver ≈ 10.3, 14-karat white gold ≈ 13.0.  Must be > 0.
    fill_factor : float, optional
        Override the style default (0 < fill_factor ≤ 1).

    Returns
    -------
    float
        Estimated chain mass in grams (rounded to 3 decimal places).

    Raises
    ------
    ValueError
        On invalid inputs.

    Notes
    -----
    This is an *approximation*.  Actual cast or assembled chains vary by
    manufacturer.  For a production cost quote, multiply by the spot price
    per gram of the chosen alloy.
    """
    # Validate style
    norm_style = str(style).strip().lower()
    norm_style = _STYLE_ALIASES.get(norm_style, norm_style)
    if norm_style not in _VALID_LINK_STYLES:
        raise ValueError(
            f"Unknown chain style {style!r}. "
            f"Valid: {sorted(_VALID_LINK_STYLES)}."
        )
    if wire_gauge_mm <= 0:
        raise ValueError(f"wire_gauge_mm must be > 0; got {wire_gauge_mm}")
    if total_length_mm <= 0:
        raise ValueError(f"total_length_mm must be > 0; got {total_length_mm}")
    if density_g_per_cm3 <= 0:
        raise ValueError(
            f"density_g_per_cm3 must be > 0; got {density_g_per_cm3}"
        )

    # Default fill factors per style (empirical)
    _FILL_FACTORS: dict[str, float] = {
        "cable":      0.55,
        "curb":       0.65,
        "figaro":     0.55,
        "rope":       0.70,
        "box":        0.40,   # mostly hollow tube
        "snake":      0.60,
        "byzantine":  0.75,   # dense weave
        "mariner":    0.55,
        "rolo":       0.50,
        "bismark":    0.80,   # multi-row, very dense
        "wheat":      0.65,
        "herringbone":0.85,   # near-solid surface
        "omega":      0.70,
        "popcorn":    0.55,
        "ball":       0.50,
        "singapore":  0.60,
    }

    if fill_factor is not None:
        ff = float(fill_factor)
        if not (0 < ff <= 1.0):
            raise ValueError(
                f"fill_factor must be in (0, 1]; got {fill_factor}"
            )
    else:
        ff = _FILL_FACTORS[norm_style]

    # Wire cross-section area in mm²
    radius_mm = wire_gauge_mm / 2.0
    wire_area_mm2 = _PI * radius_mm ** 2

    # Volume in mm³
    volume_mm3 = wire_area_mm2 * ff * total_length_mm

    # Convert mm³ → cm³ (1 cm³ = 1000 mm³) then × density
    mass_g = volume_mm3 * density_g_per_cm3 * 1e-3

    return round(mass_g, 3)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_chain_length  (read — no DB write)
# ---------------------------------------------------------------------------

jewelry_chain_length_spec = ToolSpec(
    name="jewelry_chain_length",
    description=(
        "Read-only helper: convert between chain total_length_mm and link_count "
        "for a given link style and wire gauge, OR look up a standard length by name.\n\n"
        "Standard length names (use as standard_length param):\n"
        "  Anklets: anklet_9in, anklet_9.5in, anklet_10in, anklet_10.5in, anklet_11in.\n"
        "  Bracelets: bracelet_6.5in, bracelet_7in, bracelet_7.5in, bracelet_8in, "
        "bracelet_18cm, bracelet_19cm, bracelet_20cm.\n"
        "  Chokers: choker_14in, choker_16in.\n"
        "  Necklaces: collar_14in, collar_16in, princess_18in, matinee_20in, "
        "matinee_22in, opera_24in, opera_28in, rope_30in, rope_36in, "
        "necklace_40cm, necklace_45cm, necklace_50cm, necklace_55cm, "
        "necklace_60cm, necklace_70cm, necklace_75cm.\n"
        "  Men's: mens_20in, mens_22in, mens_24in, mens_26in, mens_28in, mens_30in.\n\n"
        "Modes (provide exactly one):\n"
        "  1. standard_length + style + wire_gauge_mm → link_count + total_length_mm\n"
        "  2. total_length_mm  + style + wire_gauge_mm → link_count\n"
        "  3. link_count       + style + wire_gauge_mm → total_length_mm\n\n"
        "Use jewelry_create_chain to actually build the feature node."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Chain link style.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire diameter in mm (e.g. 0.8 for fine, 1.5 for medium).",
            },
            "link_length_mm": {
                "type": "number",
                "description": (
                    "Outer link length mm. If omitted, uses a gauge-based default "
                    "for the chosen style."
                ),
            },
            "link_width_mm": {
                "type": "number",
                "description": "Outer link width mm. If omitted, uses gauge-based default.",
            },
            "standard_length": {
                "type": "string",
                "description": (
                    "Named standard length (e.g. 'bracelet_7in', 'princess_18in'). "
                    "Mutually exclusive with total_length_mm and link_count."
                ),
            },
            "total_length_mm": {
                "type": "number",
                "description": "Target total chain length mm. Mutually exclusive with standard_length / link_count.",
            },
            "link_count": {
                "type": "integer",
                "description": "Number of links. Mutually exclusive with total_length_mm / standard_length.",
            },
        },
        "required": ["style", "wire_gauge_mm"],
    },
)


@register(jewelry_chain_length_spec, write=False)
async def run_jewelry_chain_length(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    style         = str(a.get("style", "")).strip().lower()
    wire_gauge_mm = a.get("wire_gauge_mm")
    link_length_mm = a.get("link_length_mm", None)
    link_width_mm  = a.get("link_width_mm", None)
    standard_length = a.get("standard_length", None)
    total_length_mm = a.get("total_length_mm", None)
    link_count      = a.get("link_count", None)

    # --- Validate style ---
    resolved_style = _STYLE_ALIASES.get(style, style)
    if resolved_style not in _VALID_LINK_STYLES:
        return err_payload(
            f"Unknown style {style!r}. Valid: {sorted(_VALID_LINK_STYLES)}",
            "BAD_ARGS",
        )

    # --- Validate wire_gauge_mm ---
    if wire_gauge_mm is None:
        return err_payload("wire_gauge_mm is required", "BAD_ARGS")
    try:
        wire_gauge_mm = float(wire_gauge_mm)
    except (TypeError, ValueError):
        return err_payload("wire_gauge_mm must be a number", "BAD_ARGS")
    if wire_gauge_mm <= 0:
        return err_payload("wire_gauge_mm must be > 0", "BAD_ARGS")

    # --- Parse optional link dims ---
    if link_length_mm is not None:
        try:
            link_length_mm = float(link_length_mm)
        except (TypeError, ValueError):
            return err_payload("link_length_mm must be a number", "BAD_ARGS")
        if link_length_mm <= 0:
            return err_payload("link_length_mm must be > 0", "BAD_ARGS")

    if link_width_mm is not None:
        try:
            link_width_mm = float(link_width_mm)
        except (TypeError, ValueError):
            return err_payload("link_width_mm must be a number", "BAD_ARGS")
        if link_width_mm <= 0:
            return err_payload("link_width_mm must be > 0", "BAD_ARGS")

    # --- Exactly one length source ---
    sources = sum([
        standard_length is not None,
        total_length_mm is not None,
        link_count is not None,
    ])
    if sources == 0:
        return err_payload(
            "Provide exactly one of standard_length, total_length_mm, or link_count",
            "BAD_ARGS",
        )
    if sources > 1:
        return err_payload(
            "Provide exactly one of standard_length, total_length_mm, or link_count; "
            f"got {sources}",
            "BAD_ARGS",
        )

    # Resolve standard_length → total_length_mm
    if standard_length is not None:
        if standard_length not in _STANDARD_LENGTHS_MM:
            return err_payload(
                f"Unknown standard_length {standard_length!r}. "
                f"Valid: {sorted(_STANDARD_LENGTHS_MM)}",
                "BAD_ARGS",
            )
        total_length_mm = _STANDARD_LENGTHS_MM[standard_length]

    # Compute defaults for link dims
    len_mult, wid_mult = _STYLE_LINK_MULTIPLIERS[resolved_style]
    if link_length_mm is None:
        link_length_mm = round(wire_gauge_mm * len_mult, 3)
    if link_width_mm is None:
        link_width_mm = round(wire_gauge_mm * wid_mult, 3)

    pitch_mm = link_pitch(
        resolved_style, link_length_mm, link_width_mm, wire_gauge_mm
    )

    if total_length_mm is not None:
        try:
            total_length_mm = float(total_length_mm)
        except (TypeError, ValueError):
            return err_payload("total_length_mm must be a number", "BAD_ARGS")
        if total_length_mm <= 0:
            return err_payload("total_length_mm must be > 0", "BAD_ARGS")
        computed_count = chain_length_to_link_count(total_length_mm, pitch_mm)
        actual_len = link_count_to_chain_length(computed_count, pitch_mm)
        return ok_payload({
            "style": resolved_style,
            "wire_gauge_mm": wire_gauge_mm,
            "link_length_mm": link_length_mm,
            "link_width_mm": link_width_mm,
            "link_pitch_mm": round(pitch_mm, 4),
            "requested_length_mm": total_length_mm,
            "link_count": computed_count,
            "actual_total_length_mm": actual_len,
            "standard_length": standard_length,
        })
    else:
        # link_count → length
        try:
            link_count = int(link_count)
        except (TypeError, ValueError):
            return err_payload("link_count must be an integer", "BAD_ARGS")
        if link_count < 1:
            return err_payload("link_count must be >= 1", "BAD_ARGS")
        actual_len = link_count_to_chain_length(link_count, pitch_mm)
        return ok_payload({
            "style": resolved_style,
            "wire_gauge_mm": wire_gauge_mm,
            "link_length_mm": link_length_mm,
            "link_width_mm": link_width_mm,
            "link_pitch_mm": round(pitch_mm, 4),
            "link_count": link_count,
            "total_length_mm": actual_len,
        })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_chain  (write)
# ---------------------------------------------------------------------------

jewelry_create_chain_spec = ToolSpec(
    name="jewelry_create_chain",
    description=(
        "Append a `chain_assembly` node to a `.feature` file.\n\n"
        "Builds a fully parametric chain from one of sixteen link styles:\n"
        "  cable       — alternating round-wire ovals (classic)\n"
        "  curb        — twisted flat links; set diamond_cut=true for faceted finish\n"
        "  figaro      — repeating 3-short + 1-long link pattern\n"
        "  rope        — small ovals twisted into a continuous helix\n"
        "  box         — square tube links joined end-to-end\n"
        "  snake       — wide flat scalloped elements\n"
        "  byzantine   — complex 4-link cluster weave\n"
        "  mariner     — oval links with a central stabiliser bar (anchor chain)\n"
        "  rolo        — round/belcher: wide round links, ~1:1 aspect\n"
        "  bismark     — multi-row parallel interlocked links; use rows= to set count\n"
        "  wheat       — spiga: twisted figure-8 links in a helical spiral\n"
        "  herringbone — flat V-shaped woven surface; very wide, no visible links\n"
        "  omega       — solid curved plates on a fabric/box core spine\n"
        "  popcorn     — bumpy spheroidal bead-like links\n"
        "  ball        — smooth spherical beads on wire (bead chain)\n"
        "  singapore   — twisted curb: figure-8 links rotated 90°\n\n"
        "Specify chain length via exactly one of:\n"
        "  standard_length (e.g. 'bracelet_7in', 'princess_18in', 'anklet_9in',\n"
        "                   'mens_24in', 'choker_16in')\n"
        "  total_length_mm\n"
        "  link_count\n\n"
        "Use gauge_preset='fine'/'medium'/'heavy' instead of wire_gauge_mm for "
        "quick weight selection.\n\n"
        "Set graduated=true for a necklace that scales links from centre outward.\n\n"
        "Optionally attach a clasp inline by providing clasp_style.\n"
        "All dimensions in mm.  The occtWorker opChainAssembly evaluates the "
        "node and builds the repeating link geometry."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Chain link style.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": (
                    "Wire / rod cross-section diameter in mm. "
                    "Typical range: 0.5 (very fine) – 3.0 (heavy). "
                    "Default 1.0 mm."
                ),
            },
            "link_length_mm": {
                "type": "number",
                "description": (
                    "Outer link length mm. "
                    "If omitted, uses a gauge-based default for the chosen style."
                ),
            },
            "link_width_mm": {
                "type": "number",
                "description": "Outer link width mm. If omitted, uses gauge-based default.",
            },
            "standard_length": {
                "type": "string",
                "description": (
                    "Named standard chain length. One of: "
                    + ", ".join(sorted(_STANDARD_LENGTHS_MM))
                    + ". Mutually exclusive with total_length_mm and link_count."
                ),
            },
            "total_length_mm": {
                "type": "number",
                "description": (
                    "Desired total chain length in mm. "
                    "Mutually exclusive with standard_length and link_count."
                ),
            },
            "link_count": {
                "type": "integer",
                "description": (
                    "Exact number of links. "
                    "Mutually exclusive with total_length_mm and standard_length."
                ),
            },
            "diamond_cut": {
                "type": "boolean",
                "description": "Curb style only — apply diamond-cut faceting. Default false.",
            },
            "flat": {
                "type": "boolean",
                "description": "Curb style only — flatten the wire cross-section. Default false.",
            },
            "long_link_ratio": {
                "type": "number",
                "description": (
                    "Figaro style only — ratio of the long link length to the short "
                    "link length. Default 2.5."
                ),
            },
            "twist_angle_deg": {
                "type": "number",
                "description": "Rope style only — helix twist angle per link (degrees). Default 45.",
            },
            "open_ends": {
                "type": "boolean",
                "description": "Leave end-links open for clasp attachment. Default true.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": (
                    "Optionally attach a clasp inline. One of: "
                    + ", ".join(sorted(_VALID_CLASP_STYLES))
                    + ". The clasp sub-spec is embedded in the node."
                ),
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": (
                    "Named weight class: 'fine', 'medium', or 'heavy'. "
                    "Selects a style-appropriate wire_gauge_mm from the GAUGE_PRESETS "
                    "table and overrides the wire_gauge_mm parameter."
                ),
            },
            "rows": {
                "type": "integer",
                "description": "Bismark style only — number of parallel link rows. Default 2.",
            },
            "graduated": {
                "type": "boolean",
                "description": (
                    "When true, adds a 'graduated' hint so the worker scales links "
                    "linearly from the centre toward the ends. Default false."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "style", "wire_gauge_mm"],
    },
)


@register(jewelry_create_chain_spec, write=True)
async def run_jewelry_create_chain(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str     = a.get("file_id", "").strip()
    style           = a.get("style", "").strip()
    wire_gauge_mm   = a.get("wire_gauge_mm", None)
    link_length_mm  = a.get("link_length_mm", None)
    link_width_mm   = a.get("link_width_mm", None)
    standard_length = a.get("standard_length", None)
    total_length_mm = a.get("total_length_mm", None)
    link_count      = a.get("link_count", None)
    diamond_cut     = bool(a.get("diamond_cut", False))
    flat            = bool(a.get("flat", False))
    long_link_ratio = a.get("long_link_ratio", 2.5)
    twist_angle_deg = a.get("twist_angle_deg", 45.0)
    rows            = a.get("rows", 2)
    open_ends       = bool(a.get("open_ends", True))
    graduated       = bool(a.get("graduated", False))
    gauge_preset    = a.get("gauge_preset", None)
    clasp_style     = a.get("clasp_style", None)
    node_id         = a.get("id", "").strip()

    # --- Required field checks ---
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not style:
        return err_payload("style is required", "BAD_ARGS")
    # wire_gauge_mm is required unless gauge_preset is supplied
    if wire_gauge_mm is None and gauge_preset is None:
        return err_payload("wire_gauge_mm is required (or provide gauge_preset)", "BAD_ARGS")

    # --- Numeric coercions ---
    if wire_gauge_mm is not None:
        try:
            wire_gauge_mm = float(wire_gauge_mm)
        except (TypeError, ValueError):
            return err_payload("wire_gauge_mm must be a number", "BAD_ARGS")
    else:
        # gauge_preset will set it inside compute_chain_params; use sentinel
        wire_gauge_mm = 1.0  # placeholder; overridden by gauge_preset

    if link_length_mm is not None:
        try:
            link_length_mm = float(link_length_mm)
        except (TypeError, ValueError):
            return err_payload("link_length_mm must be a number", "BAD_ARGS")

    if link_width_mm is not None:
        try:
            link_width_mm = float(link_width_mm)
        except (TypeError, ValueError):
            return err_payload("link_width_mm must be a number", "BAD_ARGS")

    if total_length_mm is not None:
        try:
            total_length_mm = float(total_length_mm)
        except (TypeError, ValueError):
            return err_payload("total_length_mm must be a number", "BAD_ARGS")

    if link_count is not None:
        try:
            link_count = int(link_count)
        except (TypeError, ValueError):
            return err_payload("link_count must be an integer", "BAD_ARGS")

    try:
        long_link_ratio = float(long_link_ratio)
    except (TypeError, ValueError):
        return err_payload("long_link_ratio must be a number", "BAD_ARGS")

    try:
        twist_angle_deg = float(twist_angle_deg)
    except (TypeError, ValueError):
        return err_payload("twist_angle_deg must be a number", "BAD_ARGS")

    try:
        rows = int(rows)
    except (TypeError, ValueError):
        return err_payload("rows must be an integer", "BAD_ARGS")

    # --- Validate file_id UUID ---
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    # --- Compute chain params (validates style, dims, length source) ---
    try:
        chain_params = compute_chain_params(
            style=style,
            wire_gauge_mm=wire_gauge_mm,
            link_length_mm=link_length_mm,
            link_width_mm=link_width_mm,
            link_count=link_count,
            total_length_mm=total_length_mm,
            standard_length=standard_length,
            diamond_cut=diamond_cut,
            flat=flat,
            long_link_ratio=long_link_ratio,
            twist_angle_deg=twist_angle_deg,
            rows=rows,
            open_ends=open_ends,
            graduated=graduated,
            gauge_preset=gauge_preset,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    # --- Optional clasp ---
    clasp_sub: Optional[dict] = None
    if clasp_style:
        clasp_style_norm = str(clasp_style).strip().lower()
        if clasp_style_norm not in _VALID_CLASP_STYLES:
            return err_payload(
                f"Unknown clasp_style {clasp_style!r}. "
                f"Valid: {sorted(_VALID_CLASP_STYLES)}",
                "BAD_ARGS",
            )
        try:
            clasp_sub = compute_clasp_params(clasp_style_norm, wire_gauge_mm)
        except ValueError as e:
            return err_payload(str(e), "BAD_ARGS")

    # --- Load feature file ---
    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "chain_assembly")

    node: dict = {
        "id": node_id,
        "op": "chain_assembly",
        **chain_params,
        "clasp": clasp_sub,
    }

    _, saved_node_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_node_id,
        "op": "chain_assembly",
        "style": chain_params["style"],
        "wire_gauge_mm": chain_params["wire_gauge_mm"],
        "link_count": chain_params["link_count"],
        "total_length_mm": chain_params["total_length_mm"],
        "link_pitch_mm": chain_params["link_pitch_mm"],
        "clasp": clasp_sub["style"] if clasp_sub else None,
    })


# ===========================================================================
# v3 — COMPOSED CHAIN PIECES
# ===========================================================================
#
# Each builder composes existing chain_assembly link hints and emits a
# higher-level spec dict.  The ``op`` key identifies the piece type; the dict
# carries one or more ``chain_assembly`` sub-specs (``chains`` list) plus
# piece-specific hint fields.  The occtWorker evaluates these as standard
# ``opChainAssembly`` calls with the extra overlay hints applied on top.
#
# Contract:
#   - Every builder calls compute_chain_params() / compute_clasp_params() —
#     no new geometry primitives.
#   - Every builder raises ValueError on bad input (validated the same way as
#     compute_chain_params).
#   - Weight is via chain_weight_estimate (existing estimator).
#   - FeatureView inspector: deferred — the composed nodes use existing
#     ``chain_assembly`` ops and can be evaluated by the worker immediately;
#     only the inspector panel UI for the composed piece types is pending.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers shared by composed pieces
# ---------------------------------------------------------------------------

def _resolve_length(
    total_length_mm: Optional[float],
    standard_length: Optional[str],
    link_count: Optional[int],
) -> tuple[Optional[float], Optional[int]]:
    """Resolve the three mutually-exclusive length sources.

    Returns (total_length_mm, link_count) with at most one set.
    Raises ValueError when more than one source is provided.
    """
    sources = sum([
        total_length_mm is not None,
        standard_length is not None,
        link_count is not None,
    ])
    if sources > 1:
        raise ValueError(
            "Provide exactly one of total_length_mm, standard_length, or link_count."
        )
    if standard_length is not None:
        if standard_length not in _STANDARD_LENGTHS_MM:
            raise ValueError(
                f"Unknown standard_length {standard_length!r}. "
                f"Valid: {sorted(_STANDARD_LENGTHS_MM)}."
            )
        total_length_mm = _STANDARD_LENGTHS_MM[standard_length]
    return total_length_mm, link_count


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0; got {value}")


def _require_int_ge(value: int, minimum: int, name: str) -> None:
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}; got {value!r}")


# ---------------------------------------------------------------------------
# 1. Tennis bracelet / riviera line
# ---------------------------------------------------------------------------

def tennis_bracelet_spec(
    *,
    stone_size_mm: float = 3.0,
    stone_count: Optional[int] = None,
    total_length_mm: Optional[float] = None,
    standard_length: Optional[str] = None,
    link_style: str = "cable",
    wire_gauge_mm: float = 0.8,
    clasp_style: str = "box_clasp",
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build a tennis bracelet / riviera line spec.

    A continuous line of equal round stones in flexible link mounts.
    Composes ``cable``-family link hints with a ``stone_station`` overlay;
    the ``stone_count`` controls spacing.

    Parameters
    ----------
    stone_size_mm : float
        Diameter of each round stone in mm (default 3.0).
    stone_count : int, optional
        Exact number of stones.  Mutually exclusive with total_length_mm /
        standard_length.  When omitted one of the other two must be given.
    total_length_mm : float, optional
        Desired bracelet length in mm; stone_count is derived.
    standard_length : str, optional
        Named standard length key.
    link_style : str
        Chain link style for the flexible mounts (default ``"cable"``).
    wire_gauge_mm : float
        Wire gauge in mm (default 0.8).
    clasp_style : str
        Clasp style (default ``"box_clasp"`` — flat profile suits tennis).
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="tennis_bracelet"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    _require_positive(stone_size_mm, "stone_size_mm")

    # Resolve gauge preset
    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        norm_style = _STYLE_ALIASES.get(str(link_style).strip().lower(),
                                         str(link_style).strip().lower())
        if norm_style not in _VALID_LINK_STYLES:
            raise ValueError(
                f"Unknown link_style {link_style!r}."
            )
        wire_gauge_mm = GAUGE_PRESETS[norm_style][gp]

    # Resolve length
    tl, lc = _resolve_length(total_length_mm, standard_length, stone_count)

    # Stone pitch = stone diameter + small gap (15% of stone size)
    stone_pitch_mm = round(stone_size_mm * 1.15, 4)

    if tl is not None:
        _require_positive(tl, "total_length_mm")
        derived_count = max(1, round(tl / stone_pitch_mm))
    elif lc is not None:
        _require_int_ge(lc, 1, "stone_count")
        derived_count = lc
        tl = round(lc * stone_pitch_mm, 3)
    else:
        raise ValueError(
            "One of stone_count, total_length_mm, or standard_length is required."
        )

    if tl is None:
        tl = round(derived_count * stone_pitch_mm, 3)

    # Compose a chain_assembly sub-spec: one link per stone, link_length ≈ stone_pitch
    link_length_mm = stone_pitch_mm
    link_width_mm = max(stone_size_mm * 0.7, wire_gauge_mm)
    chain_sub = compute_chain_params(
        link_style,
        wire_gauge_mm=wire_gauge_mm,
        link_length_mm=link_length_mm,
        link_width_mm=link_width_mm,
        link_count=derived_count,
        open_ends=True,
    )

    # Stone-station overlay hint (consumed by the worker on top of link_hints)
    stone_station_hints = {
        "type": "stone_station",
        "station_type": "tennis_mount",
        "stone_shape": "round",
        "stone_size_mm": stone_size_mm,
        "stone_count": derived_count,
        "station_pitch_mm": stone_pitch_mm,
        "prong_count": 4,
    }

    clasp_sub = compute_clasp_params(clasp_style, wire_gauge_mm)
    weight_g = chain_weight_estimate(
        link_style, wire_gauge_mm, tl, density_g_per_cm3=15.5
    )

    return {
        "op": "tennis_bracelet",
        "stone_size_mm": stone_size_mm,
        "stone_count": derived_count,
        "total_length_mm": round(tl, 3),
        "stone_pitch_mm": stone_pitch_mm,
        "stone_station_hints": stone_station_hints,
        "chains": [chain_sub],
        "clasp": clasp_sub,
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — tennis bracelet

_tennis_bracelet_spec_obj = ToolSpec(
    name="jewelry_create_tennis_bracelet",
    description=(
        "Append a tennis-bracelet / riviera-line node to a `.feature` file.\n\n"
        "A continuous line of equal round stones set in flexible link mounts. "
        "Composes existing chain_assembly link hints (default `cable`) with "
        "stone-station overlay hints.\n\n"
        "Specify piece length via exactly one of: stone_count, total_length_mm, "
        "standard_length.\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "stone_size_mm": {
                "type": "number",
                "description": "Round stone diameter in mm. Default 3.0.",
            },
            "stone_count": {
                "type": "integer",
                "description": "Exact number of stones. Mutually exclusive with total_length_mm / standard_length.",
            },
            "total_length_mm": {
                "type": "number",
                "description": "Desired bracelet length mm. Mutually exclusive with stone_count / standard_length.",
            },
            "standard_length": {
                "type": "string",
                "description": (
                    "Named standard length (e.g. 'bracelet_7in'). "
                    "Mutually exclusive with stone_count / total_length_mm."
                ),
            },
            "link_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Chain link style for flexible mounts. Default 'cable'.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire gauge mm. Default 0.8.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp style. Default 'box_clasp'.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_tennis_bracelet_spec_obj, write=True)
async def run_jewelry_create_tennis_bracelet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = tennis_bracelet_spec(
            stone_size_mm=float(a.get("stone_size_mm", 3.0)),
            stone_count=int(a["stone_count"]) if "stone_count" in a else None,
            total_length_mm=float(a["total_length_mm"]) if "total_length_mm" in a else None,
            standard_length=a.get("standard_length"),
            link_style=a.get("link_style", "cable"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 0.8)),
            clasp_style=a.get("clasp_style", "box_clasp"),
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "tennis_bracelet")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "tennis_bracelet",
        "stone_count": spec["stone_count"],
        "total_length_mm": spec["total_length_mm"],
        "clasp": spec["clasp"]["style"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })


# ---------------------------------------------------------------------------
# 2. Station / by-the-yard necklace
# ---------------------------------------------------------------------------

def station_necklace_spec(
    *,
    stone_size_mm: float = 4.0,
    station_count: int = 5,
    station_spacing_mm: float = 50.0,
    carrier_style: str = "cable",
    wire_gauge_mm: float = 0.7,
    clasp_style: str = "lobster",
    total_length_mm: Optional[float] = None,
    standard_length: Optional[str] = None,
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build a station / by-the-yard necklace spec.

    Periodic stone stations spaced along a thin carrier chain.

    Parameters
    ----------
    stone_size_mm : float
        Stone diameter in mm (default 4.0).
    station_count : int
        Number of stone stations (default 5).
    station_spacing_mm : float
        Centre-to-centre spacing between stations in mm (default 50.0).
    carrier_style : str
        Chain link style for the carrier (default ``"cable"``).
    wire_gauge_mm : float
        Carrier wire gauge in mm (default 0.7).
    clasp_style : str
        Clasp style (default ``"lobster"``).
    total_length_mm : float, optional
        Override total necklace length; station_spacing is preserved.
    standard_length : str, optional
        Named standard length key.
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="station_necklace"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    _require_positive(stone_size_mm, "stone_size_mm")
    _require_positive(station_spacing_mm, "station_spacing_mm")
    _require_int_ge(station_count, 1, "station_count")

    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        norm_style = _STYLE_ALIASES.get(str(carrier_style).strip().lower(),
                                         str(carrier_style).strip().lower())
        if norm_style not in _VALID_LINK_STYLES:
            raise ValueError(f"Unknown carrier_style {carrier_style!r}.")
        wire_gauge_mm = GAUGE_PRESETS[norm_style][gp]

    # Resolve total length
    if standard_length is not None:
        if standard_length not in _STANDARD_LENGTHS_MM:
            raise ValueError(
                f"Unknown standard_length {standard_length!r}. "
                f"Valid: {sorted(_STANDARD_LENGTHS_MM)}."
            )
        total_length_mm = _STANDARD_LENGTHS_MM[standard_length]

    if total_length_mm is not None:
        _require_positive(total_length_mm, "total_length_mm")
    else:
        # Derive from station count and spacing
        total_length_mm = round(station_spacing_mm * (station_count + 1), 3)

    # Compose carrier chain sub-spec
    chain_sub = compute_chain_params(
        carrier_style,
        wire_gauge_mm=wire_gauge_mm,
        total_length_mm=total_length_mm,
        open_ends=True,
    )

    # Station hint overlay
    station_hints = {
        "type": "stone_station",
        "station_type": "bezel_or_prong",
        "stone_shape": "round",
        "stone_size_mm": stone_size_mm,
        "station_count": station_count,
        "station_spacing_mm": station_spacing_mm,
        "station_positions": "evenly_spaced",
    }

    clasp_sub = compute_clasp_params(clasp_style, wire_gauge_mm)
    weight_g = chain_weight_estimate(
        carrier_style, wire_gauge_mm, total_length_mm, density_g_per_cm3=15.5
    )

    return {
        "op": "station_necklace",
        "stone_size_mm": stone_size_mm,
        "station_count": station_count,
        "station_spacing_mm": station_spacing_mm,
        "total_length_mm": round(total_length_mm, 3),
        "station_hints": station_hints,
        "chains": [chain_sub],
        "clasp": clasp_sub,
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — station necklace

_station_necklace_spec_obj = ToolSpec(
    name="jewelry_create_station_necklace",
    description=(
        "Append a station / by-the-yard necklace node to a `.feature` file.\n\n"
        "Periodic stone stations spaced along a thin carrier chain. "
        "Composes existing chain_assembly link hints (default `cable`) with "
        "stone-station spacing hints.\n\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "stone_size_mm": {
                "type": "number",
                "description": "Stone diameter mm. Default 4.0.",
            },
            "station_count": {
                "type": "integer",
                "description": "Number of stone stations. Default 5.",
            },
            "station_spacing_mm": {
                "type": "number",
                "description": "Centre-to-centre spacing between stations mm. Default 50.0.",
            },
            "carrier_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Carrier chain link style. Default 'cable'.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Carrier wire gauge mm. Default 0.7.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp style. Default 'lobster'.",
            },
            "total_length_mm": {
                "type": "number",
                "description": "Override total necklace length mm.",
            },
            "standard_length": {
                "type": "string",
                "description": "Named standard length key.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_station_necklace_spec_obj, write=True)
async def run_jewelry_create_station_necklace(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = station_necklace_spec(
            stone_size_mm=float(a.get("stone_size_mm", 4.0)),
            station_count=int(a.get("station_count", 5)),
            station_spacing_mm=float(a.get("station_spacing_mm", 50.0)),
            carrier_style=a.get("carrier_style", "cable"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 0.7)),
            clasp_style=a.get("clasp_style", "lobster"),
            total_length_mm=float(a["total_length_mm"]) if "total_length_mm" in a else None,
            standard_length=a.get("standard_length"),
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "station_necklace")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "station_necklace",
        "station_count": spec["station_count"],
        "total_length_mm": spec["total_length_mm"],
        "clasp": spec["clasp"]["style"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })


# ---------------------------------------------------------------------------
# 3. Lariat / Y-necklace
# ---------------------------------------------------------------------------

def lariat_spec(
    *,
    body_length_mm: float = 400.0,
    drop_length_mm: float = 80.0,
    body_style: str = "cable",
    drop_style: Optional[str] = None,
    wire_gauge_mm: float = 0.8,
    slide_type: str = "loop_slide",
    terminal_stone_mm: float = 5.0,
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build a lariat / Y-necklace spec.

    Open-ended body chain with a sliding drop pendant.  No clasp — the body
    passes through the slide so that the drop hangs at the front.

    Parameters
    ----------
    body_length_mm : float
        Total length of the main body chain in mm (default 400.0).
    drop_length_mm : float
        Length of the drop (tail) chain in mm (default 80.0).
    body_style : str
        Link style for the body (default ``"cable"``).
    drop_style : str, optional
        Link style for the drop; defaults to ``body_style``.
    wire_gauge_mm : float
        Wire gauge in mm for both body and drop (default 0.8).
    slide_type : str
        Slide mechanism hint: ``"loop_slide"`` (default) or ``"bail_slide"``.
    terminal_stone_mm : float
        Diameter of a round terminal stone at the drop end in mm (default 5.0).
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="lariat"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    _require_positive(body_length_mm, "body_length_mm")
    _require_positive(drop_length_mm, "drop_length_mm")
    _require_positive(terminal_stone_mm, "terminal_stone_mm")

    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        norm_body = _STYLE_ALIASES.get(str(body_style).strip().lower(),
                                        str(body_style).strip().lower())
        if norm_body not in _VALID_LINK_STYLES:
            raise ValueError(f"Unknown body_style {body_style!r}.")
        wire_gauge_mm = GAUGE_PRESETS[norm_body][gp]

    if drop_style is None:
        drop_style = body_style

    # Compose body chain sub-spec (open_ends=False — lariat has no clasp ends)
    body_sub = compute_chain_params(
        body_style,
        wire_gauge_mm=wire_gauge_mm,
        total_length_mm=body_length_mm,
        open_ends=False,
    )

    # Compose drop chain sub-spec
    drop_sub = compute_chain_params(
        drop_style,
        wire_gauge_mm=wire_gauge_mm,
        total_length_mm=drop_length_mm,
        open_ends=False,
    )

    # Slide hint
    slide_hints = {
        "type": "slide",
        "slide_mechanism": slide_type,
        "inner_diameter_mm": round(wire_gauge_mm * 4.0, 3),
    }

    # Terminal stone hint
    terminal_hints = {
        "type": "stone_station",
        "station_type": "drop_terminal",
        "stone_shape": "round",
        "stone_size_mm": terminal_stone_mm,
        "station_count": 1,
    }

    total_metal_mm = body_length_mm + drop_length_mm
    weight_g = chain_weight_estimate(
        body_style, wire_gauge_mm, total_metal_mm, density_g_per_cm3=15.5
    )

    return {
        "op": "lariat",
        "body_length_mm": round(body_length_mm, 3),
        "drop_length_mm": round(drop_length_mm, 3),
        "slide_type": slide_type,
        "terminal_stone_mm": terminal_stone_mm,
        "slide_hints": slide_hints,
        "terminal_hints": terminal_hints,
        "chains": [body_sub, drop_sub],
        "clasp": None,   # lariat has no traditional clasp
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — lariat

_lariat_spec_obj = ToolSpec(
    name="jewelry_create_lariat",
    description=(
        "Append a lariat / Y-necklace node to a `.feature` file.\n\n"
        "Open-ended body chain with a sliding drop pendant (no clasp). "
        "Composes two chain_assembly sub-specs (body + drop) with a slide hint "
        "and terminal stone hint.\n\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "body_length_mm": {
                "type": "number",
                "description": "Main body chain length mm. Default 400.0.",
            },
            "drop_length_mm": {
                "type": "number",
                "description": "Drop (tail) chain length mm. Default 80.0.",
            },
            "body_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Link style for the body. Default 'cable'.",
            },
            "drop_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Link style for the drop; defaults to body_style.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire gauge mm for body and drop. Default 0.8.",
            },
            "slide_type": {
                "type": "string",
                "enum": ["loop_slide", "bail_slide"],
                "description": "Slide mechanism hint. Default 'loop_slide'.",
            },
            "terminal_stone_mm": {
                "type": "number",
                "description": "Diameter of terminal stone at drop end mm. Default 5.0.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_lariat_spec_obj, write=True)
async def run_jewelry_create_lariat(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = lariat_spec(
            body_length_mm=float(a.get("body_length_mm", 400.0)),
            drop_length_mm=float(a.get("drop_length_mm", 80.0)),
            body_style=a.get("body_style", "cable"),
            drop_style=a.get("drop_style"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 0.8)),
            slide_type=a.get("slide_type", "loop_slide"),
            terminal_stone_mm=float(a.get("terminal_stone_mm", 5.0)),
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "lariat")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "lariat",
        "body_length_mm": spec["body_length_mm"],
        "drop_length_mm": spec["drop_length_mm"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })


# ---------------------------------------------------------------------------
# 4. Charm bracelet
# ---------------------------------------------------------------------------

def charm_bracelet_spec(
    *,
    base_style: str = "rolo",
    wire_gauge_mm: float = 1.2,
    total_length_mm: Optional[float] = None,
    standard_length: Optional[str] = None,
    link_count: Optional[int] = None,
    charm_count: int = 8,
    clasp_style: str = "lobster",
    jump_ring_gauge_mm: Optional[float] = None,
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build a charm bracelet spec.

    A base chain with N evenly-spaced jump-ring attach points for charms.
    Rolo / belcher links are the traditional choice because their wide round
    openings accept jump rings easily.

    Parameters
    ----------
    base_style : str
        Link style for the base chain (default ``"rolo"``).
    wire_gauge_mm : float
        Wire gauge for the base chain in mm (default 1.2).
    total_length_mm : float, optional
        Total bracelet length in mm.
    standard_length : str, optional
        Named standard length key.
    link_count : int, optional
        Exact number of base links.
    charm_count : int
        Number of jump-ring attach points (default 8).
    clasp_style : str
        Clasp style (default ``"lobster"``).
    jump_ring_gauge_mm : float, optional
        Wire gauge of the jump rings in mm; defaults to ``wire_gauge_mm * 0.7``.
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="charm_bracelet"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    _require_int_ge(charm_count, 1, "charm_count")

    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        norm_base = _STYLE_ALIASES.get(str(base_style).strip().lower(),
                                        str(base_style).strip().lower())
        if norm_base not in _VALID_LINK_STYLES:
            raise ValueError(f"Unknown base_style {base_style!r}.")
        wire_gauge_mm = GAUGE_PRESETS[norm_base][gp]

    tl, lc = _resolve_length(total_length_mm, standard_length, link_count)
    if tl is None and lc is None:
        raise ValueError(
            "One of total_length_mm, standard_length, or link_count is required."
        )

    # Compose base chain sub-spec
    if tl is not None:
        chain_sub = compute_chain_params(
            base_style,
            wire_gauge_mm=wire_gauge_mm,
            total_length_mm=tl,
            open_ends=True,
        )
    else:
        chain_sub = compute_chain_params(
            base_style,
            wire_gauge_mm=wire_gauge_mm,
            link_count=lc,
            open_ends=True,
        )

    actual_length = chain_sub["total_length_mm"]

    if jump_ring_gauge_mm is None:
        jump_ring_gauge_mm = round(wire_gauge_mm * 0.7, 3)
    _require_positive(jump_ring_gauge_mm, "jump_ring_gauge_mm")

    # Evenly spaced attach-point positions (fraction of total length)
    spacing = actual_length / (charm_count + 1)
    attach_positions_mm = [
        round(spacing * (i + 1), 3) for i in range(charm_count)
    ]

    attach_hints = {
        "type": "jump_ring_attach",
        "count": charm_count,
        "positions_mm": attach_positions_mm,
        "jump_ring_inner_diameter_mm": round(wire_gauge_mm * 2.5, 3),
        "jump_ring_wire_gauge_mm": jump_ring_gauge_mm,
    }

    clasp_sub = compute_clasp_params(clasp_style, wire_gauge_mm)
    weight_g = chain_weight_estimate(
        base_style, wire_gauge_mm, actual_length, density_g_per_cm3=15.5
    )

    return {
        "op": "charm_bracelet",
        "charm_count": charm_count,
        "total_length_mm": actual_length,
        "attach_hints": attach_hints,
        "chains": [chain_sub],
        "clasp": clasp_sub,
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — charm bracelet

_charm_bracelet_spec_obj = ToolSpec(
    name="jewelry_create_charm_bracelet",
    description=(
        "Append a charm bracelet node to a `.feature` file.\n\n"
        "A base chain with N evenly-spaced jump-ring attach points for charms. "
        "Composes existing chain_assembly link hints (default `rolo`) with "
        "jump-ring attach-point hints.\n\n"
        "Specify piece length via exactly one of: link_count, total_length_mm, "
        "standard_length.\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "base_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Link style for the base chain. Default 'rolo'.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire gauge mm. Default 1.2.",
            },
            "total_length_mm": {
                "type": "number",
                "description": "Total bracelet length mm.",
            },
            "standard_length": {
                "type": "string",
                "description": "Named standard length key.",
            },
            "link_count": {
                "type": "integer",
                "description": "Exact number of base links.",
            },
            "charm_count": {
                "type": "integer",
                "description": "Number of jump-ring attach points. Default 8.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp style. Default 'lobster'.",
            },
            "jump_ring_gauge_mm": {
                "type": "number",
                "description": "Jump ring wire gauge mm. Defaults to wire_gauge_mm × 0.7.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_charm_bracelet_spec_obj, write=True)
async def run_jewelry_create_charm_bracelet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = charm_bracelet_spec(
            base_style=a.get("base_style", "rolo"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 1.2)),
            total_length_mm=float(a["total_length_mm"]) if "total_length_mm" in a else None,
            standard_length=a.get("standard_length"),
            link_count=int(a["link_count"]) if "link_count" in a else None,
            charm_count=int(a.get("charm_count", 8)),
            clasp_style=a.get("clasp_style", "lobster"),
            jump_ring_gauge_mm=float(a["jump_ring_gauge_mm"]) if "jump_ring_gauge_mm" in a else None,
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "charm_bracelet")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "charm_bracelet",
        "charm_count": spec["charm_count"],
        "total_length_mm": spec["total_length_mm"],
        "clasp": spec["clasp"]["style"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })


# ---------------------------------------------------------------------------
# 5. Multi-strand / layered
# ---------------------------------------------------------------------------

_MAX_STRANDS = 5
_MIN_STRANDS = 2


def multi_strand_spec(
    *,
    strand_count: int = 3,
    strand_styles: Optional[list] = None,
    wire_gauge_mm: float = 0.8,
    total_length_mm: Optional[float] = None,
    standard_length: Optional[str] = None,
    link_count: Optional[int] = None,
    clasp_style: str = "box_clasp",
    connector_type: str = "multi_strand_box",
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build a multi-strand / layered chain spec.

    Two to five parallel chains joined at a connector + clasp.

    Parameters
    ----------
    strand_count : int
        Number of parallel strands, 2–5 (default 3).
    strand_styles : list[str], optional
        Link style for each strand.  If shorter than ``strand_count``, the
        last entry is repeated.  Defaults to all ``"cable"``.
    wire_gauge_mm : float
        Wire gauge for all strands in mm (default 0.8).
    total_length_mm : float, optional
        Length of each strand in mm.
    standard_length : str, optional
        Named standard length key.
    link_count : int, optional
        Exact link count for each strand.
    clasp_style : str
        Clasp style (default ``"box_clasp"`` — multi-tab suits multi-strand).
    connector_type : str
        Connector / end-bar hint: ``"multi_strand_box"`` (default) or
        ``"end_bar"``.
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="multi_strand"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    if not isinstance(strand_count, int) or not (_MIN_STRANDS <= strand_count <= _MAX_STRANDS):
        raise ValueError(
            f"strand_count must be an integer between {_MIN_STRANDS} and "
            f"{_MAX_STRANDS}; got {strand_count!r}."
        )

    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        # Use first strand style for preset lookup
        first_style = (strand_styles[0] if strand_styles else "cable")
        norm_first = _STYLE_ALIASES.get(str(first_style).strip().lower(),
                                         str(first_style).strip().lower())
        if norm_first not in _VALID_LINK_STYLES:
            raise ValueError(f"Unknown strand style {first_style!r}.")
        wire_gauge_mm = GAUGE_PRESETS[norm_first][gp]

    # Resolve strand styles list
    if strand_styles is None:
        strand_styles = ["cable"] * strand_count
    else:
        # Extend / pad to strand_count
        if len(strand_styles) < strand_count:
            strand_styles = list(strand_styles) + [strand_styles[-1]] * (
                strand_count - len(strand_styles)
            )
        strand_styles = strand_styles[:strand_count]

    tl, lc = _resolve_length(total_length_mm, standard_length, link_count)
    if tl is None and lc is None:
        raise ValueError(
            "One of total_length_mm, standard_length, or link_count is required."
        )

    # Build each strand sub-spec
    chain_subs = []
    for style in strand_styles:
        if tl is not None:
            sub = compute_chain_params(
                style,
                wire_gauge_mm=wire_gauge_mm,
                total_length_mm=tl,
                open_ends=True,
            )
        else:
            sub = compute_chain_params(
                style,
                wire_gauge_mm=wire_gauge_mm,
                link_count=lc,
                open_ends=True,
            )
        chain_subs.append(sub)

    actual_length = chain_subs[0]["total_length_mm"]

    connector_hints = {
        "type": "connector",
        "connector_style": connector_type,
        "strand_count": strand_count,
        "strand_spacing_mm": round(wire_gauge_mm * 3.0, 3),
    }

    clasp_sub = compute_clasp_params(clasp_style, wire_gauge_mm)
    total_metal_mm = actual_length * strand_count
    weight_g = chain_weight_estimate(
        strand_styles[0], wire_gauge_mm, total_metal_mm, density_g_per_cm3=15.5
    )

    return {
        "op": "multi_strand",
        "strand_count": strand_count,
        "strand_styles": strand_styles,
        "total_length_mm": actual_length,
        "connector_hints": connector_hints,
        "chains": chain_subs,
        "clasp": clasp_sub,
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — multi-strand

_multi_strand_spec_obj = ToolSpec(
    name="jewelry_create_multi_strand",
    description=(
        "Append a multi-strand / layered chain node to a `.feature` file.\n\n"
        "Two to five parallel chains joined at a connector and clasp. "
        "Composes chain_assembly sub-specs for each strand with a connector hint.\n\n"
        "Specify strand length via exactly one of: link_count, total_length_mm, "
        "standard_length.\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "strand_count": {
                "type": "integer",
                "description": f"Number of parallel strands ({_MIN_STRANDS}–{_MAX_STRANDS}). Default 3.",
            },
            "strand_styles": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(_VALID_LINK_STYLES)},
                "description": (
                    "Link style per strand. Padded/truncated to strand_count. "
                    "Defaults to all 'cable'."
                ),
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire gauge mm for all strands. Default 0.8.",
            },
            "total_length_mm": {
                "type": "number",
                "description": "Length of each strand mm.",
            },
            "standard_length": {
                "type": "string",
                "description": "Named standard length key.",
            },
            "link_count": {
                "type": "integer",
                "description": "Exact link count per strand.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp style. Default 'box_clasp'.",
            },
            "connector_type": {
                "type": "string",
                "enum": ["multi_strand_box", "end_bar"],
                "description": "Connector / end-bar type hint. Default 'multi_strand_box'.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_multi_strand_spec_obj, write=True)
async def run_jewelry_create_multi_strand(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = multi_strand_spec(
            strand_count=int(a.get("strand_count", 3)),
            strand_styles=a.get("strand_styles"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 0.8)),
            total_length_mm=float(a["total_length_mm"]) if "total_length_mm" in a else None,
            standard_length=a.get("standard_length"),
            link_count=int(a["link_count"]) if "link_count" in a else None,
            clasp_style=a.get("clasp_style", "box_clasp"),
            connector_type=a.get("connector_type", "multi_strand_box"),
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "multi_strand")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "multi_strand",
        "strand_count": spec["strand_count"],
        "strand_styles": spec["strand_styles"],
        "total_length_mm": spec["total_length_mm"],
        "clasp": spec["clasp"]["style"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })


# ---------------------------------------------------------------------------
# 6. Extender chain
# ---------------------------------------------------------------------------

def extender_chain_spec(
    *,
    extender_style: str = "cable",
    wire_gauge_mm: float = 0.7,
    extender_length_mm: float = 50.0,
    loop_count: int = 5,
    loop_spacing_mm: Optional[float] = None,
    end_ring_style: str = "lobster",
    gauge_preset: Optional[str] = None,
) -> dict:
    """Build an adjustable extender chain spec.

    A short chain with a series of end loops that allow the clasp to be
    attached at different positions for adjustable length.

    Parameters
    ----------
    extender_style : str
        Link style for the extender (default ``"cable"``).
    wire_gauge_mm : float
        Wire gauge in mm (default 0.7).
    extender_length_mm : float
        Total extender chain length in mm (default 50.0).
    loop_count : int
        Number of attachment loops along the extender (default 5).
    loop_spacing_mm : float, optional
        Spacing between loops in mm; defaults to
        ``extender_length_mm / (loop_count + 1)``.
    end_ring_style : str
        Clasp style attached to the extender end (default ``"lobster"``).
    gauge_preset : str, optional
        ``"fine"``, ``"medium"``, or ``"heavy"``; overrides ``wire_gauge_mm``.

    Returns
    -------
    dict
        Composed spec with ``op="extender_chain"``.

    Raises
    ------
    ValueError
        On invalid inputs.
    """
    _require_positive(extender_length_mm, "extender_length_mm")
    _require_int_ge(loop_count, 1, "loop_count")

    if gauge_preset is not None:
        gp = str(gauge_preset).strip().lower()
        if gp not in _VALID_GAUGE_WEIGHTS:
            raise ValueError(
                f"Unknown gauge_preset {gauge_preset!r}. "
                f"Valid: {sorted(_VALID_GAUGE_WEIGHTS)}."
            )
        norm_ext = _STYLE_ALIASES.get(str(extender_style).strip().lower(),
                                       str(extender_style).strip().lower())
        if norm_ext not in _VALID_LINK_STYLES:
            raise ValueError(f"Unknown extender_style {extender_style!r}.")
        wire_gauge_mm = GAUGE_PRESETS[norm_ext][gp]

    if loop_spacing_mm is None:
        loop_spacing_mm = round(extender_length_mm / (loop_count + 1), 3)
    _require_positive(loop_spacing_mm, "loop_spacing_mm")

    # Compose the extender chain sub-spec
    chain_sub = compute_chain_params(
        extender_style,
        wire_gauge_mm=wire_gauge_mm,
        total_length_mm=extender_length_mm,
        open_ends=True,
    )

    actual_length = chain_sub["total_length_mm"]

    # Loop positions along the extender
    loop_positions_mm = [
        round(loop_spacing_mm * (i + 1), 3) for i in range(loop_count)
    ]

    loop_hints = {
        "type": "end_loops",
        "loop_count": loop_count,
        "loop_positions_mm": loop_positions_mm,
        "loop_inner_diameter_mm": round(wire_gauge_mm * 3.0, 3),
        "loop_wire_gauge_mm": round(wire_gauge_mm * 0.8, 3),
    }

    clasp_sub = compute_clasp_params(end_ring_style, wire_gauge_mm)
    weight_g = chain_weight_estimate(
        extender_style, wire_gauge_mm, actual_length, density_g_per_cm3=15.5
    )

    return {
        "op": "extender_chain",
        "extender_length_mm": round(actual_length, 3),
        "loop_count": loop_count,
        "loop_spacing_mm": loop_spacing_mm,
        "loop_hints": loop_hints,
        "chains": [chain_sub],
        "clasp": clasp_sub,
        "estimated_weight_18k_gold_g": weight_g,
    }


# ToolSpec + runner — extender chain

_extender_chain_spec_obj = ToolSpec(
    name="jewelry_create_extender_chain",
    description=(
        "Append an extender chain node to a `.feature` file.\n\n"
        "A short chain with a series of end loops for adjustable length attachment. "
        "Composes a single chain_assembly sub-spec with loop-position hints.\n\n"
        "All dimensions in mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "extender_style": {
                "type": "string",
                "enum": sorted(_VALID_LINK_STYLES),
                "description": "Link style for the extender. Default 'cable'.",
            },
            "wire_gauge_mm": {
                "type": "number",
                "description": "Wire gauge mm. Default 0.7.",
            },
            "extender_length_mm": {
                "type": "number",
                "description": "Total extender length mm. Default 50.0.",
            },
            "loop_count": {
                "type": "integer",
                "description": "Number of attachment loops. Default 5.",
            },
            "loop_spacing_mm": {
                "type": "number",
                "description": "Spacing between loops mm. Defaults to extender_length / (loop_count+1).",
            },
            "end_ring_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp at the extender end. Default 'lobster'.",
            },
            "gauge_preset": {
                "type": "string",
                "enum": sorted(_VALID_GAUGE_WEIGHTS),
                "description": "Named weight class overriding wire_gauge_mm.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id"],
    },
)


@register(_extender_chain_spec_obj, write=True)
async def run_jewelry_create_extender_chain(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        spec = extender_chain_spec(
            extender_style=a.get("extender_style", "cable"),
            wire_gauge_mm=float(a.get("wire_gauge_mm", 0.7)),
            extender_length_mm=float(a.get("extender_length_mm", 50.0)),
            loop_count=int(a.get("loop_count", 5)),
            loop_spacing_mm=float(a["loop_spacing_mm"]) if "loop_spacing_mm" in a else None,
            end_ring_style=a.get("end_ring_style", "lobster"),
            gauge_preset=a.get("gauge_preset"),
        )
    except (ValueError, KeyError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = a.get("id", "").strip() or next_node_id(content, "extender_chain")
    node = {"id": node_id, **spec}

    _, saved_id, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": saved_id,
        "op": "extender_chain",
        "extender_length_mm": spec["extender_length_mm"],
        "loop_count": spec["loop_count"],
        "clasp": spec["clasp"]["style"],
        "estimated_weight_18k_gold_g": spec["estimated_weight_18k_gold_g"],
    })
