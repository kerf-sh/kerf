"""ISO 4032 — hexagon nut, style 1 (metric coarse, product grades A and B).

Authored generator (human-written, MIT).  SIZES freezes the standard's
tabulated dimensions for M3..M24: width across flats ``s``, nut height ``m``,
and nominal thread diameter ``d`` (also used for the bore clearance hole).
These are uncopyrightable dimensional facts, transcribed once and frozen here.

Geometry (composed purely from the Kerf OCCT kernel facade):
  nut body = hexagonal prism (s across-flats, m height)
  bore     = cylinder at pitch-diameter clearance, full height, cut through

Thread bore is the nominal major diameter — same smooth-cylinder convention
as all other generators in this package.

Dimension source: ISO 4032:2012, Table 1.
All dimension values are standard tabulated facts; the code is original.
"""

from __future__ import annotations

import math

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "iso_4032_hex_nut",
    "name": "ISO 4032 hex nut",
    "standard": "ISO 4032",
    "domain": "mechanical",
    "category": "mechanical/fastener",
    "units": "mm",
}


def _row(size, nominal_d, across_flats, nut_m):
    """Build one SIZES row.

    bbox XY: circumscribed-circle diameter of the hex prism (corner-to-corner).
    bbox Z: nut height m.
    volume: hex prism volume minus the through-bore.
    """
    circum_d = across_flats / math.cos(math.pi / 6.0)
    hex_area = (3.0 * math.sqrt(3.0) / 2.0) * (circum_d / 2.0) ** 2
    vol = hex_area * nut_m - math.pi * (nominal_d / 2.0) ** 2 * nut_m
    return {
        "size": size,
        "params": {
            "nominal_d": nominal_d,
            "across_flats": across_flats,
            "nut_m": nut_m,
        },
        "expect": {
            "bbox_mm": [
                round(circum_d, 3),
                round(circum_d, 3),
                round(nut_m, 3),
            ],
            "volume_mm3": round(vol, 2),
        },
    }


# ISO 4032:2012 Table 1 — (size, d nominal, s across-flats, m nut height) mm.
SIZES = [
    _row("M3",  3,  5.5, 2.4),
    _row("M4",  4,  7.0, 3.2),
    _row("M5",  5,  8.0, 4.0),
    _row("M6",  6, 10.0, 5.0),
    _row("M8",  8, 13.0, 6.5),
    _row("M10", 10, 16.0, 8.0),
    _row("M12", 12, 18.0, 10.0),
    _row("M16", 16, 24.0, 13.0),
    _row("M20", 20, 30.0, 16.0),
    _row("M24", 24, 36.0, 19.0),
]


def build(row: dict):
    p = row["params"]
    nut_m = p["nut_m"]

    # Hex prism: kernel.hex_prism is centred on origin (z in [-m/2, +m/2]).
    # Translate to sit on XY plane (z in [0, m]) for consistency with bolts.
    body = kernel.hex_prism(across_flats=p["across_flats"], height=nut_m)
    body = kernel.translate(body, 0.0, 0.0, nut_m / 2.0)

    # Through bore: cylinder at nominal thread diameter, full height + margin.
    bore = kernel.cylinder(radius=p["nominal_d"] / 2.0, height=nut_m * 2.0)
    bore = kernel.translate(bore, 0.0, 0.0, nut_m / 2.0)

    return kernel.cut(body, bore)
