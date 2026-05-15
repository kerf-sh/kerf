"""DIN 125 — plain washer, Form A (normal series).

Authored generator (human-written, MIT).  SIZES freezes the standard's
tabulated dimensions for M1.6..M36: inner diameter ``d1``, outer diameter
``d2``, thickness ``h``.  DIN 125 Form A covers a wider size range than
ISO 7089 and uses slightly different inner-diameter clearances at several
sizes (e.g. M16, M20, M24 differ).  These are uncopyrightable dimensional
facts, transcribed once and frozen here.

Geometry (composed purely from the Kerf OCCT kernel facade):
  annular disc = outer cylinder with the bore cut out
  (identical construction to iso_7089_flat_washer; different table)

Dimension source: DIN 125-1:1984 (replicated as ISO 7089 for the
M3..M24 overlap; DIN 125 additionally covers M1.6..M2.5 and M30..M36).
All dimension values are standard tabulated facts; the code is original.
"""

from __future__ import annotations

import math

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "din_125_plain_washer",
    "name": "DIN 125 plain washer",
    "standard": "DIN 125",
    "domain": "mechanical",
    "category": "mechanical/washer",
    "units": "mm",
}


def _row(size, d1, d2, h):
    """Build one SIZES row.

    bbox XY: outer diameter d2 (circular disc).
    bbox Z:  thickness h.
    volume:  analytical annulus volume.
    """
    vol = math.pi * ((d2 / 2.0) ** 2 - (d1 / 2.0) ** 2) * h
    return {
        "size": size,
        "params": {"inner_d": d1, "outer_d": d2, "thickness": h},
        "expect": {
            "bbox_mm": [d2, d2, h],
            "volume_mm3": round(vol, 2),
        },
    }


# DIN 125-1:1984 Form A (size, d1 inner Ø, d2 outer Ø, h thickness) mm.
# Covers the full standard range M1.6..M36.
SIZES = [
    _row("M1.6", 1.7,  4.0, 0.3),
    _row("M2",   2.2,  5.0, 0.3),
    _row("M2.5", 2.7,  6.0, 0.5),
    _row("M3",   3.2,  7.0, 0.5),
    _row("M4",   4.3,  9.0, 0.8),
    _row("M5",   5.3, 10.0, 1.0),
    _row("M6",   6.4, 12.0, 1.6),
    _row("M8",   8.4, 16.0, 1.6),
    _row("M10", 10.5, 20.0, 2.0),
    _row("M12", 13.0, 24.0, 2.5),
    _row("M16", 17.0, 30.0, 3.0),
    _row("M20", 21.0, 37.0, 3.0),
    _row("M24", 25.0, 44.0, 4.0),
    _row("M30", 31.0, 56.0, 4.0),
    _row("M36", 37.0, 66.0, 5.0),
]


def build(row: dict):
    p = row["params"]
    disc = kernel.cylinder(radius=p["outer_d"] / 2.0, height=p["thickness"])
    bore = kernel.cylinder(
        radius=p["inner_d"] / 2.0, height=p["thickness"] * 2.0
    )
    return kernel.cut(disc, bore)
