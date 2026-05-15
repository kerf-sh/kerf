"""ISO 7089 — plain washer, normal series, product grade A (200 HV).

Authored reference generator (human-written, MIT).  The SIZES table holds
the standard's own tabulated dimensions (d1 inner Ø, d2 outer Ø, h
thickness) for the M3..M24 range — uncopyrightable facts, transcribed once
and frozen here so ``enumerate`` never needs the LLM again.

Geometry = an annular disc: an outer cylinder with the bore cut out, built
purely by composing the Kerf OCCT kernel facade (cylinder + boolean cut).
"""

from __future__ import annotations

import math

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "iso_7089_flat_washer",
    "name": "ISO 7089 flat washer",
    "standard": "ISO 7089",
    "domain": "mechanical",
    "category": "mechanical/washer",
    "units": "mm",
}


def _row(size, d1, d2, h):
    vol = math.pi * ((d2 / 2.0) ** 2 - (d1 / 2.0) ** 2) * h
    return {
        "size": size,
        "params": {"inner_d": d1, "outer_d": d2, "thickness": h},
        "expect": {"bbox_mm": [d2, d2, h], "volume_mm3": round(vol, 2)},
    }


# ISO 7089, normal series (size, d1 inner Ø, d2 outer Ø, h thickness) mm.
SIZES = [
    _row("M3", 3.2, 7.0, 0.5),
    _row("M4", 4.3, 9.0, 0.8),
    _row("M5", 5.3, 10.0, 1.0),
    _row("M6", 6.4, 12.0, 1.6),
    _row("M8", 8.4, 16.0, 1.6),
    _row("M10", 10.5, 20.0, 2.0),
    _row("M12", 13.0, 24.0, 2.5),
    _row("M16", 17.0, 30.0, 3.0),
    _row("M20", 21.0, 37.0, 3.0),
    _row("M24", 25.0, 44.0, 4.0),
]


def build(row: dict):
    p = row["params"]
    disc = kernel.cylinder(radius=p["outer_d"] / 2.0, height=p["thickness"])
    bore = kernel.cylinder(
        radius=p["inner_d"] / 2.0, height=p["thickness"] * 2.0
    )
    return kernel.cut(disc, bore)
