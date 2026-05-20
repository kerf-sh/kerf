"""
kerf_cad_core.fasteners.catalog — ISO/DIN/ASME fastener dimension catalog.

Covers hex bolts, hex cap screws, socket cap screws, hex nuts, and plain
washers.  All dimensions are nominal values derived from published standards
using explicit formulas; no proprietary data is redistributed.

Standards referenced
--------------------
ISO 4014:2011   Hexagon head bolts — Product grades A and B
ISO 4762:2004   Hexagon socket head cap screws — coarse thread
ISO 4032:2012   Hexagon nuts, style 1 — Product grade A and B
ISO 7089:2000   Plain washers — Normal series — Product grade A
DIN 931:1987    Hexagon head bolts (partial thread) — superseded by ISO 4014;
                  dimensions identical for M3–M64 coarse series
DIN 934:2000    Hexagon nuts — normal height; identical to ISO 4032 for M3–M64
ASME B18.2.1-2012  Square and Hex Bolts and Screws (inch)
ASME B18.2.2-2010  Square and Hex Nuts (inch)
ASME B18.22.1-1965 Plain Washers (inch)

All dimension formulae
----------------------
ISO 4014 hex head (across-flats s, head height k):
    s (AF)  = tabulated per ISO 4014 Table 2 (same as DIN 931)
    k       = tabulated per ISO 4014 Table 2
    e (circumscribed circle, min) = s / cos(30°)  [geometry; exact = s/0.866]

ISO 4032 hex nut height m (normal):
    m       = tabulated per ISO 4032 Table 1

ISO 7089 washer (inner dia d1, outer dia d2, thickness h):
    d1 = d_nom + clearance  (tabulated; clearance = 0.3 mm for M3–M12,
                              0.5 mm for M14–M24, 1.0 mm for M27–M64)
    d2, h — tabulated per ISO 7089 Table 1

ASME B18.2.1 hex bolt (Width Across Flats W, head height H):
    W, H — tabulated from ASME B18.2.1 Table 2, basic dimensions
    circumscribed diameter = W / cos(30°) = W * 2/√3

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import TypedDict


# ---------------------------------------------------------------------------
# TypedDicts
# ---------------------------------------------------------------------------

class HexBoltSpec(TypedDict):
    """ISO 4014 / DIN 931 hex bolt nominal dimensions."""
    designation: str          # e.g. "M6", "M16"
    standard: str             # "ISO 4014" | "DIN 931"
    d_nom_mm: float           # nominal thread diameter (mm)
    pitch_mm: float           # coarse thread pitch (mm)
    s_af_mm: float            # across-flats (wrench size) (mm)
    k_head_mm: float          # head height (mm)
    e_circ_mm: float          # circumscribed-circle diameter (mm); = s/cos30°
    d_washer_face_mm: float   # washer-bearing face diameter ≈ 1.5 × d_nom


class SocketCapSpec(TypedDict):
    """ISO 4762 socket cap screw nominal dimensions."""
    designation: str
    standard: str             # "ISO 4762"
    d_nom_mm: float
    pitch_mm: float
    dk_head_mm: float         # head diameter
    k_head_mm: float          # head height
    s_hex_key_mm: float       # hex socket key size (across-flats)


class HexNutSpec(TypedDict):
    """ISO 4032 / DIN 934 hex nut nominal dimensions."""
    designation: str
    standard: str             # "ISO 4032" | "DIN 934"
    d_nom_mm: float
    pitch_mm: float
    s_af_mm: float            # across-flats
    m_height_mm: float        # nut height (m)
    e_circ_mm: float          # circumscribed-circle diameter


class WasherSpec(TypedDict):
    """ISO 7089 plain washer nominal dimensions."""
    designation: str
    standard: str             # "ISO 7089"
    d_nom_mm: float           # nominal thread diameter
    d1_inner_mm: float        # inner (bore) diameter
    d2_outer_mm: float        # outer diameter
    h_thick_mm: float         # thickness


class ASMEBoltSpec(TypedDict):
    """ASME B18.2.1 hex bolt nominal dimensions (inch + mm)."""
    designation: str          # e.g. "1/4-20 UNC"
    standard: str             # "ASME B18.2.1"
    d_nom_in: float           # nominal diameter (in)
    tpi: int                  # threads per inch
    W_af_in: float            # width across flats (in)
    H_head_in: float          # head height (in)
    d_nom_mm: float           # d_nom_in × 25.4
    W_af_mm: float            # W_af_in × 25.4
    H_head_mm: float          # H_head_in × 25.4
    e_circ_mm: float          # circumscribed circle mm


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _e(s_af: float) -> float:
    """Circumscribed-circle diameter from across-flats: e = s / cos(30°)."""
    return round(s_af / math.cos(math.radians(30.0)), 3)


# ---------------------------------------------------------------------------
# ISO 4014 / DIN 931 Hex Bolt catalog  (M3–M64 coarse)
# s_af, k_head from ISO 4014:2011 Table 2 / DIN 931 Table 1 — exact nominals
# d_washer_face ≈ 1.5 × d (VDI 2230 default, also Shigley)
# ---------------------------------------------------------------------------

def _hb(desig: str, d: float, p: float, s: float, k: float) -> HexBoltSpec:
    return HexBoltSpec(
        designation=desig,
        standard="ISO 4014",
        d_nom_mm=d,
        pitch_mm=p,
        s_af_mm=s,
        k_head_mm=k,
        e_circ_mm=_e(s),
        d_washer_face_mm=round(1.5 * d, 3),
    )


# (designation, d_nom_mm, pitch_mm, s_af_mm, k_head_mm)
# Source: ISO 4014:2011 Table 2 nominal dimensions
_HEX_BOLT_DATA: list[tuple[str, float, float, float, float]] = [
    ("M3",   3.0,  0.50,  5.5,  2.0),
    ("M4",   4.0,  0.70,  7.0,  2.8),
    ("M5",   5.0,  0.80,  8.0,  3.5),
    ("M6",   6.0,  1.00, 10.0,  4.0),
    ("M8",   8.0,  1.25, 13.0,  5.3),
    ("M10", 10.0,  1.50, 17.0,  6.4),  # CORRECT: ISO 4014 s=17 for M10
    ("M12", 12.0,  1.75, 19.0,  7.5),
    ("M14", 14.0,  2.00, 22.0,  8.8),
    ("M16", 16.0,  2.00, 24.0, 10.0),
    ("M18", 18.0,  2.50, 27.0, 11.5),
    ("M20", 20.0,  2.50, 30.0, 12.5),
    ("M22", 22.0,  2.50, 34.0, 14.0),
    ("M24", 24.0,  3.00, 36.0, 15.0),
    ("M27", 27.0,  3.00, 41.0, 17.0),
    ("M30", 30.0,  3.50, 46.0, 18.7),
    ("M36", 36.0,  4.00, 55.0, 22.5),
    ("M42", 42.0,  4.50, 65.0, 26.0),
    ("M48", 48.0,  5.00, 75.0, 30.0),
    ("M56", 56.0,  5.50, 85.0, 35.0),
    ("M64", 64.0,  6.00, 95.0, 40.0),
]

HEX_BOLTS: dict[str, HexBoltSpec] = {
    desig: _hb(desig, d, p, s, k)
    for desig, d, p, s, k in _HEX_BOLT_DATA
}


# ---------------------------------------------------------------------------
# ISO 4762 Socket Cap Screw catalog  (M3–M24 coarse)
# Source: ISO 4762:2004 Table 1 — nominal (basic) dimensions
#   dk = head diameter, k = head height, s = hex key size
# ---------------------------------------------------------------------------

def _sc(desig: str, d: float, p: float, dk: float, k: float, s: float) -> SocketCapSpec:
    return SocketCapSpec(
        designation=desig,
        standard="ISO 4762",
        d_nom_mm=d,
        pitch_mm=p,
        dk_head_mm=dk,
        k_head_mm=k,
        s_hex_key_mm=s,
    )


# (designation, d_nom, pitch, dk_head, k_head, s_hex_key)
_SOCKET_CAP_DATA: list[tuple[str, float, float, float, float, float]] = [
    ("M3",   3.0,  0.50,  5.5, 3.0, 2.0),
    ("M4",   4.0,  0.70,  7.0, 4.0, 3.0),
    ("M5",   5.0,  0.80,  8.5, 5.0, 4.0),
    ("M6",   6.0,  1.00, 10.0, 6.0, 5.0),
    ("M8",   8.0,  1.25, 13.0, 8.0, 6.0),
    ("M10", 10.0,  1.50, 16.0,10.0, 8.0),
    ("M12", 12.0,  1.75, 18.0,12.0,10.0),
    ("M14", 14.0,  2.00, 21.0,14.0,12.0),
    ("M16", 16.0,  2.00, 24.0,16.0,14.0),
    ("M20", 20.0,  2.50, 30.0,20.0,17.0),
    ("M24", 24.0,  3.00, 36.0,24.0,19.0),
]

SOCKET_CAPS: dict[str, SocketCapSpec] = {
    desig: _sc(desig, d, p, dk, k, s)
    for desig, d, p, dk, k, s in _SOCKET_CAP_DATA
}


# ---------------------------------------------------------------------------
# ISO 4032 / DIN 934 Hex Nut catalog  (M3–M64 coarse)
# Source: ISO 4032:2012 Table 1 — nominal dimensions
#   s (AF) and m (height) are the basic nominal values
# ---------------------------------------------------------------------------

def _hn(desig: str, d: float, p: float, s: float, m: float) -> HexNutSpec:
    return HexNutSpec(
        designation=desig,
        standard="ISO 4032",
        d_nom_mm=d,
        pitch_mm=p,
        s_af_mm=s,
        m_height_mm=m,
        e_circ_mm=_e(s),
    )


# (designation, d_nom_mm, pitch_mm, s_af_mm, m_height_mm)
# Source: ISO 4032:2012 Table 1
_HEX_NUT_DATA: list[tuple[str, float, float, float, float]] = [
    ("M3",   3.0,  0.50,  5.5,  2.4),
    ("M4",   4.0,  0.70,  7.0,  3.2),
    ("M5",   5.0,  0.80,  8.0,  4.7),
    ("M6",   6.0,  1.00, 10.0,  5.2),
    ("M8",   8.0,  1.25, 13.0,  6.8),
    ("M10", 10.0,  1.50, 17.0,  8.4),
    ("M12", 12.0,  1.75, 19.0, 10.8),
    ("M14", 14.0,  2.00, 22.0, 12.8),
    ("M16", 16.0,  2.00, 24.0, 14.8),
    ("M18", 18.0,  2.50, 27.0, 15.8),
    ("M20", 20.0,  2.50, 30.0, 18.0),
    ("M22", 22.0,  2.50, 34.0, 19.4),
    ("M24", 24.0,  3.00, 36.0, 21.5),
    ("M27", 27.0,  3.00, 41.0, 23.8),
    ("M30", 30.0,  3.50, 46.0, 25.6),
    ("M36", 36.0,  4.00, 55.0, 31.0),
    ("M42", 42.0,  4.50, 65.0, 34.0),
    ("M48", 48.0,  5.00, 75.0, 38.0),
    ("M56", 56.0,  5.50, 85.0, 45.0),
    ("M64", 64.0,  6.00, 95.0, 51.0),
]

HEX_NUTS: dict[str, HexNutSpec] = {
    desig: _hn(desig, d, p, s, m)
    for desig, d, p, s, m in _HEX_NUT_DATA
}


# ---------------------------------------------------------------------------
# ISO 7089 Plain Washer catalog  (M3–M64)
# Source: ISO 7089:2000 Table 1 — normal series, product grade A
#   d1 = bore (d_nom + clearance), d2 = outer diameter, h = thickness
# ---------------------------------------------------------------------------

def _ws(desig: str, d: float, d1: float, d2: float, h: float) -> WasherSpec:
    return WasherSpec(
        designation=desig,
        standard="ISO 7089",
        d_nom_mm=d,
        d1_inner_mm=d1,
        d2_outer_mm=d2,
        h_thick_mm=h,
    )


# (designation, d_nom, d1_inner, d2_outer, h_thick)
# Source: ISO 7089:2000 Table 1
_WASHER_DATA: list[tuple[str, float, float, float, float]] = [
    ("M3",   3.0,  3.2,  7.0,  0.5),
    ("M4",   4.0,  4.3,  9.0,  0.8),
    ("M5",   5.0,  5.3, 10.0,  1.0),
    ("M6",   6.0,  6.4, 12.0,  1.6),
    ("M8",   8.0,  8.4, 16.0,  1.6),
    ("M10", 10.0, 10.5, 20.0,  2.0),
    ("M12", 12.0, 13.0, 24.0,  2.5),
    ("M14", 14.0, 15.0, 28.0,  2.5),
    ("M16", 16.0, 17.0, 30.0,  3.0),
    ("M18", 18.0, 19.0, 34.0,  3.0),
    ("M20", 20.0, 21.0, 37.0,  3.0),
    ("M22", 22.0, 23.0, 39.0,  3.0),
    ("M24", 24.0, 25.0, 44.0,  4.0),
    ("M27", 27.0, 28.0, 50.0,  4.0),
    ("M30", 30.0, 31.0, 56.0,  4.0),
    ("M36", 36.0, 37.0, 66.0,  5.0),
    ("M42", 42.0, 43.0, 78.0,  7.0),
    ("M48", 48.0, 50.0, 92.0,  8.0),
    ("M56", 56.0, 58.0,105.0,  9.0),
    ("M64", 64.0, 66.0,115.0,  9.0),
]

WASHERS: dict[str, WasherSpec] = {
    desig: _ws(desig, d, d1, d2, h)
    for desig, d, d1, d2, h in _WASHER_DATA
}


# ---------------------------------------------------------------------------
# ASME B18.2.1 Hex Bolt catalog  (inch)
# Source: ASME B18.2.1-2012 Table 2 — basic dimensions (nominal)
#   d_nom_in, tpi (UNC coarse), W (width across flats), H (head height)
# ---------------------------------------------------------------------------

def _ab(desig: str, d_in: float, tpi: int, W_in: float, H_in: float) -> ASMEBoltSpec:
    d_mm = round(d_in * 25.4, 4)
    W_mm = round(W_in * 25.4, 4)
    H_mm = round(H_in * 25.4, 4)
    return ASMEBoltSpec(
        designation=desig,
        standard="ASME B18.2.1",
        d_nom_in=d_in,
        tpi=tpi,
        W_af_in=W_in,
        H_head_in=H_in,
        d_nom_mm=d_mm,
        W_af_mm=W_mm,
        H_head_mm=H_mm,
        e_circ_mm=round(W_mm / math.cos(math.radians(30.0)), 3),
    )


# (designation, d_nom_in, tpi, W_af_in, H_head_in)
# Source: ASME B18.2.1-2012 Table 2 basic dimensions
_ASME_BOLT_DATA: list[tuple[str, float, int, float, float]] = [
    ("1/4-20 UNC",   0.2500, 20, 0.4375, 0.1563),
    ("5/16-18 UNC",  0.3125, 18, 0.5000, 0.1953),
    ("3/8-16 UNC",   0.3750, 16, 0.5625, 0.2344),
    ("7/16-14 UNC",  0.4375, 14, 0.6250, 0.2734),
    ("1/2-13 UNC",   0.5000, 13, 0.7500, 0.3125),
    ("5/8-11 UNC",   0.6250, 11, 0.9375, 0.3906),
    ("3/4-10 UNC",   0.7500, 10, 1.1250, 0.4688),
    ("7/8-9 UNC",    0.8750,  9, 1.3125, 0.5469),
    ("1-8 UNC",      1.0000,  8, 1.5000, 0.6250),
    ("1 1/4-7 UNC",  1.2500,  7, 1.8750, 0.7500),
]

ASME_BOLTS: dict[str, ASMEBoltSpec] = {
    desig: _ab(desig, d_in, tpi, W_in, H_in)
    for desig, d_in, tpi, W_in, H_in in _ASME_BOLT_DATA
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def lookup_hex_bolt(designation: str) -> HexBoltSpec | None:
    """Return ISO 4014 hex bolt spec for the given M-designation, or None."""
    return HEX_BOLTS.get(designation)


def lookup_socket_cap(designation: str) -> SocketCapSpec | None:
    """Return ISO 4762 socket cap spec for the given M-designation, or None."""
    return SOCKET_CAPS.get(designation)


def lookup_hex_nut(designation: str) -> HexNutSpec | None:
    """Return ISO 4032 hex nut spec for the given M-designation, or None."""
    return HEX_NUTS.get(designation)


def lookup_washer(designation: str) -> WasherSpec | None:
    """Return ISO 7089 washer spec for the given M-designation, or None."""
    return WASHERS.get(designation)


def lookup_asme_bolt(designation: str) -> ASMEBoltSpec | None:
    """Return ASME B18.2.1 bolt spec for the given designation, or None."""
    return ASME_BOLTS.get(designation)


# ---------------------------------------------------------------------------
# Hole-pattern integration helpers
# ---------------------------------------------------------------------------

def clearance_hole_diameter(designation: str, fit: str = "normal") -> float | None:
    """
    Return recommended clearance hole diameter (mm) for ISO 286-1 fits.

    Fits (ISO 273 clearance-hole series):
        "fine"   — H12 equivalent (tight clearance, ±0.1 mm)
        "normal" — H13 equivalent (standard clearance)
        "coarse" — H14 equivalent (free clearance)

    Parameters
    ----------
    designation : str
        M-designation, e.g. "M6", "M16".
    fit : str
        "fine", "normal", or "coarse".  Default "normal".

    Returns
    -------
    float or None
        Clearance hole diameter in mm, or None if designation not found.

    References
    ----------
    ISO 273:1979 — Fasteners; clearance holes for bolts and screws
    """
    bolt = lookup_hex_bolt(designation)
    if bolt is None:
        return None
    d = bolt["d_nom_mm"]
    # ISO 273 clearance series (approximate medium/large group)
    # fine ≈ d + 0.2..0.3; normal ≈ d + 0.5..1.0; coarse ≈ d + 1..3
    if fit == "fine":
        delta = 0.2 if d <= 8 else (0.3 if d <= 16 else 0.5)
    elif fit == "coarse":
        delta = 1.0 if d <= 8 else (1.5 if d <= 16 else 2.0)
    else:  # normal
        delta = 0.5 if d <= 8 else (1.0 if d <= 16 else 1.5)
    return round(d + delta, 2)


def bolt_circle_positions(
    n_bolts: int,
    pcd_mm: float,
    start_angle_deg: float = 0.0,
) -> list[tuple[float, float]]:
    """
    Return (x, y) positions (mm) of equally-spaced bolt holes on a pitch-circle.

    Parameters
    ----------
    n_bolts : int
        Number of bolts.  Must be >= 1.
    pcd_mm : float
        Pitch-circle diameter (mm).  Must be > 0.
    start_angle_deg : float
        Angle of first bolt from positive-x axis (degrees).  Default 0.

    Returns
    -------
    list of (x, y) tuples in mm, length == n_bolts.

    Raises
    ------
    ValueError
        If n_bolts < 1 or pcd_mm <= 0.
    """
    if n_bolts < 1:
        raise ValueError(f"n_bolts must be >= 1, got {n_bolts}")
    if pcd_mm <= 0:
        raise ValueError(f"pcd_mm must be > 0, got {pcd_mm}")
    r = pcd_mm / 2.0
    positions = []
    for i in range(n_bolts):
        angle_rad = math.radians(start_angle_deg + i * 360.0 / n_bolts)
        x = round(r * math.cos(angle_rad), 6)
        y = round(r * math.sin(angle_rad), 6)
        positions.append((x, y))
    return positions


def bolt_circle_pcd(
    n_bolts: int,
    spacing_mm: float,
) -> float:
    """
    Compute pitch-circle diameter from bolt count and adjacent-bolt spacing.

    PCD = spacing / sin(π / n)

    Parameters
    ----------
    n_bolts : int
        Number of equally-spaced bolts.  Must be >= 2.
    spacing_mm : float
        Centre-to-centre distance between adjacent bolts (mm).  Must be > 0.

    Returns
    -------
    float
        Pitch-circle diameter (mm).

    Raises
    ------
    ValueError
        If n_bolts < 2 or spacing_mm <= 0.
    """
    if n_bolts < 2:
        raise ValueError(f"n_bolts must be >= 2, got {n_bolts}")
    if spacing_mm <= 0:
        raise ValueError(f"spacing_mm must be > 0, got {spacing_mm}")
    return round(spacing_mm / math.sin(math.pi / n_bolts), 6)
