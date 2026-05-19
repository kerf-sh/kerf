"""tile_constraints.py — Tiny Tapeout tile size catalogue and area validation.

Tile grid (width x height in µm):
  1x1 →  160 × 100
  2x2 →  320 × 200
  4x2 →  640 × 200
  8x2 → 1280 × 200

The tile label is «<cols>x<rows>» where cols ∈ {1,2,4,8} and rows ∈ {1,2}.
"""

from __future__ import annotations

from typing import NamedTuple

# µm per tile unit
_UM_PER_COL = 160
_UM_PER_ROW = 100

# Supported (cols, rows) pairs
VALID_TILES: dict[str, tuple[int, int]] = {
    "1x1": (1, 1),
    "2x2": (2, 2),
    "4x2": (4, 2),
    "8x2": (8, 2),
}


class TileDimensions(NamedTuple):
    label: str
    cols: int
    rows: int
    width_um: float
    height_um: float
    area_um2: float


def get_tile(label: str) -> TileDimensions:
    """Return dimensions for *label* (e.g. ``"1x1"``).

    Raises ``KeyError`` if the label is not in the catalogue.
    """
    if label not in VALID_TILES:
        raise KeyError(
            f"Unknown tile size {label!r}. Valid options: {sorted(VALID_TILES)}"
        )
    cols, rows = VALID_TILES[label]
    w = cols * _UM_PER_COL
    h = rows * _UM_PER_ROW
    return TileDimensions(
        label=label,
        cols=cols,
        rows=rows,
        width_um=float(w),
        height_um=float(h),
        area_um2=float(w * h),
    )


def validate_tile(label: str) -> TileDimensions:
    """Return tile dimensions or raise ``ValueError`` for an invalid label."""
    try:
        return get_tile(label)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def all_tiles() -> list[TileDimensions]:
    """Return all supported tile sizes ordered by area (ascending)."""
    return [get_tile(k) for k in sorted(VALID_TILES, key=lambda k: VALID_TILES[k])]
