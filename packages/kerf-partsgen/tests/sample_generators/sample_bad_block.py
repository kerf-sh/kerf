"""Deliberately-WRONG sample generator (test fixture).

The size table declares a bounding box / volume that is grossly different
from what `build()` actually produces (off by ~10x). The verification gate
MUST catch this and emit FAIL — proving a green check means measured
geometry, never "the LLM replied".
"""

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "sample_bad_block",
    "name": "Sample bad block",
    "standard": "KERF-TEST",
    "domain": "mechanical",
    "category": "mechanical/test",
    "units": "mm",
}

SIZES = [
    # Declares a 100x100x100 / 1e6 mm^3 block but builds a tiny 5x5x5 one.
    {"size": "X", "params": {"l": 5.0, "w": 5.0, "h": 5.0},
     "expect": {"bbox_mm": [100.0, 100.0, 100.0], "volume_mm3": 1_000_000.0}},
]


def build(row):
    p = row["params"]
    return kernel.box(p["l"], p["w"], p["h"])
