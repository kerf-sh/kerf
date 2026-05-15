"""Trivial sample generator (test fixture): a 3-size parametric block.

Honest geometry: bbox + volume declared by the table exactly match what the
kernel builds, so every size PASSES the gate. Used by the hermetic
enumeration test.
"""

from kerf_partsgen import kernel

FAMILY = {
    "family_id": "sample_block",
    "name": "Sample test block",
    "standard": "KERF-TEST",
    "domain": "mechanical",
    "category": "mechanical/test",
    "units": "mm",
}

SIZES = [
    {"size": "S", "params": {"l": 10.0, "w": 8.0, "h": 5.0},
     "expect": {"bbox_mm": [10.0, 8.0, 5.0], "volume_mm3": 400.0}},
    {"size": "M", "params": {"l": 20.0, "w": 12.0, "h": 6.0},
     "expect": {"bbox_mm": [20.0, 12.0, 6.0], "volume_mm3": 1440.0}},
    {"size": "L", "params": {"l": 40.0, "w": 25.0, "h": 10.0},
     "expect": {"bbox_mm": [40.0, 25.0, 10.0], "volume_mm3": 10000.0}},
]


def build(row):
    p = row["params"]
    return kernel.box(p["l"], p["w"], p["h"])
