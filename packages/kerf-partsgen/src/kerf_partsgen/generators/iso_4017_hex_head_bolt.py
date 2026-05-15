"""ISO 4017 — hexagon head set screw / fully-threaded hex bolt.

Authored reference generator (human-written, MIT).  SIZES freezes the
standard's tabulated head dimensions — width across flats ``s`` and head
height ``k`` — for M3..M24, plus a representative shank length per size.
These are uncopyrightable facts, transcribed once and frozen here.

Geometry (composed purely from the Kerf OCCT kernel facade):
  hex head  = hexagonal prism by width-across-flats (kernel.hex_prism)
  shank     = plain cylinder at the nominal major diameter (libraries do
              not cut real helical threads — thread is the cylindrical
              envelope; this matches how Kerf models fastener parts)
  union the two, with a small chamfer on the free shank end.

Expected bbox / volume are derived from the same standard dimensions in
``_row`` so the verification gate checks the built solid against the table,
not against the LLM.
"""

from __future__ import annotations

import math

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "iso_4017_hex_head_bolt",
    "name": "ISO 4017 hex head bolt",
    "standard": "ISO 4017",
    "domain": "mechanical",
    "category": "mechanical/fastener",
    "units": "mm",
}


def _row(size, nominal_d, across_flats, head_h, length):
    # Hex head circumscribed-circle Ø (corner-to-corner) sets the XY bbox.
    circum_d = across_flats / math.cos(math.pi / 6.0)
    hex_area = (3.0 * math.sqrt(3.0) / 2.0) * (circum_d / 2.0) ** 2
    vol = hex_area * head_h + math.pi * (nominal_d / 2.0) ** 2 * length
    return {
        "size": size,
        "params": {
            "nominal_d": nominal_d,
            "across_flats": across_flats,
            "head_h": head_h,
            "length": length,
        },
        "expect": {
            "bbox_mm": [
                round(circum_d, 3),
                round(circum_d, 3),
                round(head_h + length, 3),
            ],
            "volume_mm3": round(vol, 2),
        },
    }


# ISO 4017 (size, nominal Ø d, s across-flats, k head height, l length) mm.
SIZES = [
    _row("M3", 3, 5.5, 2.0, 16),
    _row("M4", 4, 7.0, 2.8, 20),
    _row("M5", 5, 8.0, 3.5, 25),
    _row("M6", 6, 10.0, 4.0, 30),
    _row("M8", 8, 13.0, 5.3, 40),
    _row("M10", 10, 16.0, 6.4, 50),
    _row("M12", 12, 18.0, 7.5, 60),
    _row("M16", 16, 24.0, 10.0, 80),
    _row("M20", 20, 30.0, 12.5, 100),
    _row("M24", 24, 36.0, 15.0, 120),
]


def build(row: dict):
    p = row["params"]
    head_h = p["head_h"]
    length = p["length"]

    # Head sits on the XY plane (z in [-head_h, 0]); shank runs +Z.
    head = kernel.hex_prism(across_flats=p["across_flats"], height=head_h)
    head = kernel.translate(head, 0.0, 0.0, -head_h / 2.0)

    shank = kernel.cylinder(radius=p["nominal_d"] / 2.0, height=length)
    shank = kernel.translate(shank, 0.0, 0.0, length / 2.0)
    shank = kernel.chamfer_top_edge(shank, min(0.6, p["nominal_d"] * 0.12))

    return kernel.union(head, shank)
