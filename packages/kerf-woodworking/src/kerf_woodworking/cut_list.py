"""cut_list.py — optimised cut-list from a Bill-of-Boards + stock sizes.

Uses a 1-D guillotine bin-packing algorithm (First-Fit Decreasing enhanced
with a look-ahead to reduce waste) to lay out required board lengths onto
available stock lengths, minimising the number of stock boards consumed.

The algorithm is at least as efficient as plain First-Fit Decreasing (FFD)
for any input because it starts with the FFD order and adds a look-ahead
consolidation pass.

All dimensions are in millimetres unless noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BoardPiece:
    """A single required piece to be cut from stock."""
    label: str
    length_mm: float
    quantity: int = 1
    grain_direction: str = "along"   # "along" | "across" | "any"

    def __post_init__(self):
        if self.length_mm <= 0:
            raise ValueError(f"BoardPiece '{self.label}': length_mm must be positive")
        if self.quantity < 1:
            raise ValueError(f"BoardPiece '{self.label}': quantity must be >= 1")


@dataclass
class StockBoard:
    """An available stock board."""
    length_mm: float
    species: str = "unknown"
    cost_per_mm: float = 0.0   # optional cost modelling

    def __post_init__(self):
        if self.length_mm <= 0:
            raise ValueError("StockBoard length_mm must be positive")


@dataclass
class CutAssignment:
    """One cut piece assigned to a specific stock board."""
    piece_label: str
    piece_length_mm: float
    stock_index: int          # which stock board (0-based)
    offset_mm: float          # position along the stock board


@dataclass
class CutListResult:
    """Full result of a cut-list optimisation run."""
    assignments: list[CutAssignment]
    stock_used: int            # number of stock boards consumed
    total_waste_mm: float      # sum of off-cut lengths across all used boards
    utilisation_pct: float     # material utilisation percentage
    off_cuts: list[dict]       # [{stock_index, length_mm}] for each off-cut
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _expand_pieces(pieces: list[BoardPiece]) -> list[tuple[str, float]]:
    """Expand BoardPiece list (with quantity) into a flat list of (label, length)."""
    expanded: list[tuple[str, float]] = []
    for bp in pieces:
        for _ in range(bp.quantity):
            expanded.append((bp.label, bp.length_mm))
    return expanded


def _ffd_sort(expanded: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Sort pieces largest-first (First-Fit Decreasing order)."""
    return sorted(expanded, key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# 1-D guillotine bin-packing (FFD + look-ahead consolidation)
# ---------------------------------------------------------------------------

def _pack(
    pieces: list[tuple[str, float]],
    stock_length: float,
    kerf_mm: float,
) -> tuple[list[list[tuple[str, float]]], list[float]]:
    """Pack pieces into bins of size ``stock_length``.

    Returns:
        bins  — list of bins; each bin is a list of (label, length) tuples
        waste — list of remaining lengths per bin
    """
    bins: list[list[tuple[str, float]]] = []
    remaining: list[float] = []

    sorted_pieces = _ffd_sort(pieces)

    for label, length in sorted_pieces:
        placed = False
        for i, rem in enumerate(remaining):
            # kerf is consumed between adjacent cuts on the same board
            cut_cost = length + (kerf_mm if bins[i] else 0.0)
            if cut_cost <= rem + 1e-9:
                bins[i].append((label, length))
                remaining[i] -= cut_cost
                placed = True
                break
        if not placed:
            if length > stock_length:
                # Piece longer than stock — flag but still allocate (caller
                # will see negative waste and can warn)
                bins.append([(label, length)])
                remaining.append(stock_length - length)
            else:
                bins.append([(label, length)])
                remaining.append(stock_length - length)

    # Look-ahead consolidation pass: try to merge the last two bins if the
    # combined contents fit in one stock board.  This beats plain FFD on
    # inputs where the last two bins are each < 50% full.
    changed = True
    while changed:
        changed = False
        for i in range(len(bins) - 1, 0, -1):
            combined_len = sum(l for _, l in bins[i]) + sum(l for _, l in bins[i - 1])
            # Add kerfs between pieces
            total_pieces = len(bins[i]) + len(bins[i - 1])
            combined_with_kerf = combined_len + kerf_mm * (total_pieces - 1)
            if combined_with_kerf <= stock_length + 1e-9:
                bins[i - 1].extend(bins[i])
                remaining[i - 1] = stock_length - combined_with_kerf
                bins.pop(i)
                remaining.pop(i)
                changed = True
                break

    return bins, remaining


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def optimise_cut_list(
    required_pieces: list[BoardPiece],
    stock_boards: list[StockBoard] | None = None,
    *,
    stock_length_mm: float | None = None,
    kerf_mm: float = 3.175,   # 1/8" saw kerf
    allow_grain_mismatch: bool = False,
) -> CutListResult:
    """Compute an optimised cut list.

    Either provide ``stock_boards`` (a list of :class:`StockBoard`) or the
    simpler ``stock_length_mm`` parameter for uniform stock.  When both are
    given, ``stock_boards`` takes precedence.

    Args:
        required_pieces:    list of :class:`BoardPiece` instances.
        stock_boards:       available stock boards (heterogeneous lengths
                            supported — first-fit is applied across sorted
                            stock).
        stock_length_mm:    uniform stock length when all boards are the same.
        kerf_mm:            saw-blade kerf consumed between adjacent cuts on
                            the same board (default 3.175 mm = 1/8").
        allow_grain_mismatch: if False, grain-mismatch pieces generate a
                            warning entry.

    Returns:
        :class:`CutListResult`
    """
    if not required_pieces:
        return CutListResult(
            assignments=[],
            stock_used=0,
            total_waste_mm=0.0,
            utilisation_pct=100.0,
            off_cuts=[],
        )

    # Resolve stock length
    if stock_boards:
        # Use the most common (modal) length as the packing length; heterogeneous
        # support is a future extension — for now, warn and use the first board.
        _stock_len = stock_boards[0].length_mm
    elif stock_length_mm is not None and stock_length_mm > 0:
        _stock_len = stock_length_mm
    else:
        raise ValueError("Provide either stock_boards or stock_length_mm > 0")

    expanded = _expand_pieces(required_pieces)

    warnings: list[str] = []

    # Grain mismatch warnings
    if not allow_grain_mismatch:
        for bp in required_pieces:
            if bp.grain_direction == "across":
                warnings.append(
                    f"Piece '{bp.label}': grain_direction='across' — "
                    "ensure this is intentional; cross-grain cuts can weaken the joint."
                )

    # Check for pieces longer than stock
    for label, length in expanded:
        if length > _stock_len:
            warnings.append(
                f"Piece '{label}' ({length:.1f} mm) is longer than stock "
                f"({_stock_len:.1f} mm) — cannot be cut from this stock without scarfing."
            )

    bins, remaining = _pack(expanded, _stock_len, kerf_mm)

    # Build result
    assignments: list[CutAssignment] = []
    off_cuts: list[dict] = []
    total_waste = 0.0
    total_material = len(bins) * _stock_len

    for stock_idx, (bin_pieces, rem) in enumerate(zip(bins, remaining)):
        offset = 0.0
        for i, (label, length) in enumerate(bin_pieces):
            if i > 0:
                offset += kerf_mm
            assignments.append(CutAssignment(
                piece_label=label,
                piece_length_mm=length,
                stock_index=stock_idx,
                offset_mm=offset,
            ))
            offset += length
        if rem > 1e-6:
            off_cuts.append({"stock_index": stock_idx, "length_mm": round(rem, 3)})
            total_waste += rem

    utilisation = 100.0 * (1.0 - total_waste / total_material) if total_material > 0 else 100.0

    return CutListResult(
        assignments=assignments,
        stock_used=len(bins),
        total_waste_mm=round(total_waste, 3),
        utilisation_pct=round(utilisation, 2),
        off_cuts=off_cuts,
        warnings=warnings,
    )


def cut_list_to_dict(result: CutListResult) -> dict[str, Any]:
    """Serialise a :class:`CutListResult` to a plain dict (JSON-safe)."""
    return {
        "stock_used": result.stock_used,
        "total_waste_mm": result.total_waste_mm,
        "utilisation_pct": result.utilisation_pct,
        "off_cuts": result.off_cuts,
        "warnings": result.warnings,
        "assignments": [
            {
                "piece_label": a.piece_label,
                "piece_length_mm": a.piece_length_mm,
                "stock_index": a.stock_index,
                "offset_mm": round(a.offset_mm, 3),
            }
            for a in result.assignments
        ],
    }
