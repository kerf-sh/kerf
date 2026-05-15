"""
kerf_cad_core.jewelry.chain
============================

Parametric chain / bracelet / necklace generator.

Provides:
  - Chain link generators (cable, curb, figaro, rope, box, snake, byzantine,
    mariner/anchor) — each fully parametric; emits a node-spec describing the
    repeating link geometry and overall chain assembly.
  - Clasps (lobster, spring_ring, toggle, box_clasp) as parametric attachment
    nodes.
  - Standard-length helpers (bracelet 7"/18 cm, necklace 16/18/20/24") with
    link-count ↔ length round-trips.
  - LLM tools: jewelry_create_chain (write), jewelry_chain_length (read).

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
])

# Style aliases (accepted but normalised)
_STYLE_ALIASES: dict[str, str] = {
    "anchor": "mariner",
    "diamond_cut_curb": "curb",  # handled via link_hints
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
    # Bracelets
    "bracelet_6.5in":  165.1,
    "bracelet_7in":    177.8,
    "bracelet_7.5in":  190.5,
    "bracelet_8in":    203.2,
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
    # Metric bracelet
    "bracelet_18cm":   180.0,
    "bracelet_19cm":   190.0,
    "bracelet_20cm":   200.0,
    # Metric necklace
    "necklace_40cm":   400.0,
    "necklace_45cm":   450.0,
    "necklace_50cm":   500.0,
    "necklace_60cm":   600.0,
}

# Wire-gauge to typical link-length multiplier (outer link length ≈ multiplier × wire_gauge)
# These are empirical defaults — the LLM/user can override.
_STYLE_LINK_MULTIPLIERS: dict[str, tuple[float, float]] = {
    # (length_mult, width_mult) — both relative to wire_gauge_mm
    "cable":    (3.5, 2.5),
    "curb":     (3.0, 2.5),
    "figaro":   (3.5, 2.5),   # mixed links (3 short + 1 long)
    "rope":     (2.5, 2.0),
    "box":      (2.0, 2.0),
    "snake":    (2.2, 2.8),
    "byzantine":(3.8, 2.5),
    "mariner":  (4.0, 2.8),
}


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
    if style in ("box", "snake"):
        # Box and snake chains: links sit side-by-side along the length;
        # pitch ≈ link_length / 2 (alternating orientation overlap)
        return max(link_length_mm * 0.5, wire_gauge_mm * 1.1)
    elif style == "byzantine":
        # Byzantine has a more compact, dense pattern
        return max(inner_len * 0.7, wire_gauge_mm * 1.1)
    elif style == "rope":
        # Rope: continuous twist; pitch per link is quite small
        return max(inner_len * 0.5, wire_gauge_mm * 1.1)
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


_LINK_HINT_BUILDERS = {
    "cable":    _cable_hints,
    "curb":     _curb_hints,
    "figaro":   _figaro_hints,
    "rope":     _rope_hints,
    "box":      _box_hints,
    "snake":    _snake_hints,
    "byzantine":_byzantine_hints,
    "mariner":  _mariner_hints,
}

# kwargs forwarded to each hint builder (subset that each style accepts)
_STYLE_EXTRA_KWARGS: dict[str, set[str]] = {
    "curb":    {"diamond_cut", "flat"},
    "figaro":  {"long_link_ratio"},
    "rope":    {"twist_angle_deg"},
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
    # Options
    open_ends: bool = True,
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
        Rope style only — helix twist angle per link (degrees).
    open_ends : bool
        Leave end-links open for clasp attachment (default True).

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
    link_hints = builder(wire_gauge_mm, link_length_mm, link_width_mm, **kwargs)

    return {
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
# LLM tool: jewelry_chain_length  (read — no DB write)
# ---------------------------------------------------------------------------

jewelry_chain_length_spec = ToolSpec(
    name="jewelry_chain_length",
    description=(
        "Read-only helper: convert between chain total_length_mm and link_count "
        "for a given link style and wire gauge, OR look up a standard bracelet / "
        "necklace length by name.\n\n"
        "Standard length names (use as standard_length param):\n"
        "  Bracelets: bracelet_6.5in, bracelet_7in, bracelet_7.5in, bracelet_8in, "
        "bracelet_18cm, bracelet_19cm, bracelet_20cm.\n"
        "  Necklaces: collar_14in, collar_16in, princess_18in, matinee_20in, "
        "matinee_22in, opera_24in, opera_28in, rope_30in, rope_36in, "
        "necklace_40cm, necklace_45cm, necklace_50cm, necklace_60cm.\n\n"
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
        "Builds a fully parametric chain from one of eight link styles:\n"
        "  cable       — alternating round-wire ovals (classic)\n"
        "  curb        — twisted flat links; set diamond_cut=true for faceted finish\n"
        "  figaro      — repeating 3-short + 1-long link pattern\n"
        "  rope        — small ovals twisted into a continuous helix\n"
        "  box         — square tube links joined end-to-end\n"
        "  snake       — wide flat scalloped elements (omega)\n"
        "  byzantine   — complex 4-link cluster weave\n"
        "  mariner     — oval links with a central stabiliser bar (anchor chain)\n\n"
        "Specify chain length via exactly one of:\n"
        "  standard_length (e.g. 'bracelet_7in', 'princess_18in')\n"
        "  total_length_mm\n"
        "  link_count\n\n"
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
    open_ends       = bool(a.get("open_ends", True))
    clasp_style     = a.get("clasp_style", None)
    node_id         = a.get("id", "").strip()

    # --- Required field checks ---
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not style:
        return err_payload("style is required", "BAD_ARGS")
    if wire_gauge_mm is None:
        return err_payload("wire_gauge_mm is required", "BAD_ARGS")

    # --- Numeric coercions ---
    try:
        wire_gauge_mm = float(wire_gauge_mm)
    except (TypeError, ValueError):
        return err_payload("wire_gauge_mm must be a number", "BAD_ARGS")

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
            open_ends=open_ends,
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
