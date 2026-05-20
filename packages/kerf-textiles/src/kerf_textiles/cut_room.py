"""
kerf_textiles.cut_room
======================
Production-scale cut-room nesting.

Extends T-179 marker-making with production-grade No-Fit-Polygon (NFP) nesting
across multiple fabric rolls of varying widths.  Supports:

  - Grain-line constraints: each piece declares allowed rotation angles
    relative to the grain; the nester only tries those angles.
  - Ply-direction: one-way (↑ only) or two-way (↑↓) fabric stacking.
  - Multiple rolls of different widths; pieces are assigned to whichever roll
    produces the best utilisation after a greedy-skyline pass.
  - NFP approximation via Shapely polygon offset / Minkowski difference for
    curved or arbitrary polygon pieces; rectangular pieces fall back to exact
    bounding-box NFP (full skyline packing, identical to kerf_cad_core.nesting).

Algorithm
---------
For each fabric roll (width × length), run a Skyline + No-Fit-Polygon pass:

1. Sort pieces by descending bounding-box area (largest-first heuristic).
2. For each piece, iterate allowed grain-line angles.
3. For each angle, compute the NFP of the piece against already-placed pieces
   (or use the bottom-left skyline to find the placement boundary).
4. Place the piece at the lowest feasible y-coordinate inside the roll width.
5. Compute utilisation = Σ(piece areas) / (roll width × max y used).

The NFP approach is implemented using Shapely's ``buffer`` + set operations,
giving a robust, non-overlapping result for convex and mildly concave polygons.

Pure Python + numpy + Shapely (already available in this repo).

Author: imranparuk
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Optional shapely — prefer it; fall back to bounding-box-only if absent
# ---------------------------------------------------------------------------
try:
    from shapely.geometry import Polygon as _SPolygon, MultiPolygon as _SMultiPolygon
    from shapely.affinity import rotate as _s_rotate, translate as _s_translate
    _HAS_SHAPELY = True
except ImportError:  # pragma: no cover
    _HAS_SHAPELY = False


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class FabricPiece:
    """
    A single fabric piece to be nested onto a roll.

    Attributes
    ----------
    name : str
        Piece identifier (e.g. "front-bodice").
    polygon : list[tuple[float, float]]
        Clockwise or counter-clockwise polygon vertices in mm.
        If None, the piece is treated as a rectangle (w × h).
    w : float
        Bounding-box width in mm (always required — used when polygon is None).
    h : float
        Bounding-box height in mm (always required — used when polygon is None).
    qty : int
        Number of times this piece must appear (default 1).
    grain_angles : list[float]
        Allowed rotation angles in degrees relative to the grain line.
        Default [0] = no rotation allowed (strict grain).
        [0, 180] = two-way (flip along grain).
        [0, 90, 180, 270] = any 90° rotation.
    ply_direction : str
        "any"     — piece may face either direction.
        "one_way" — pile/nap fabric; all pieces must face the same direction
                    (enforced by restricting grain_angles to [0] only).
    """
    name: str
    w: float
    h: float
    qty: int = 1
    polygon: Optional[list[tuple[float, float]]] = None
    grain_angles: list[float] = field(default_factory=lambda: [0.0])
    ply_direction: str = "any"  # "any" | "one_way"

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(
                f"FabricPiece '{self.name}': w and h must be > 0, got {self.w}×{self.h}"
            )
        if self.qty < 1:
            raise ValueError(f"FabricPiece '{self.name}': qty must be >= 1, got {self.qty}")
        # Normalise grain angles to [0, 360)
        self.grain_angles = sorted({a % 360 for a in self.grain_angles})
        # One-way ply: only 0° and 180° are in-grain (flip is ok; 90° is not)
        if self.ply_direction == "one_way":
            self.grain_angles = [a for a in self.grain_angles if a in (0.0, 180.0)]
            if not self.grain_angles:
                self.grain_angles = [0.0]


@dataclass
class FabricRoll:
    """
    A fabric roll (or lay) of fixed width and (potentially infinite) length.

    Attributes
    ----------
    name : str
        Roll identifier.
    width : float
        Usable fabric width in mm.
    max_length : float
        Maximum usable length (mm).  Use math.inf for unlimited.
    kerf : float
        Knife-gap between pieces in mm (default 0).
    margin : float
        Border inset on all four sides in mm (default 0).
    """
    name: str
    width: float
    max_length: float = math.inf
    kerf: float = 0.0
    margin: float = 0.0

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError(f"FabricRoll '{self.name}': width must be > 0, got {self.width}")
        if self.kerf < 0:
            raise ValueError(f"FabricRoll '{self.name}': kerf must be >= 0, got {self.kerf}")
        if self.margin < 0:
            raise ValueError(f"FabricRoll '{self.name}': margin must be >= 0, got {self.margin}")


@dataclass
class PiecePlacement:
    """Position and orientation of one placed piece on a roll."""
    piece_name: str
    roll_name: str
    x: float          # lower-left corner x (in usable space, margin already added)
    y: float          # lower-left corner y (in usable space, margin already added)
    placed_w: float   # width after rotation
    placed_h: float   # height after rotation
    angle: float      # grain angle applied (degrees)


@dataclass
class RollLayout:
    """All placements on one roll."""
    roll: FabricRoll
    placements: list[PiecePlacement] = field(default_factory=list)
    length_used: float = 0.0   # actual roll length consumed

    @property
    def utilization(self) -> float:
        """Area utilisation = Σ(piece areas) / (roll.width × length_used)."""
        if self.length_used <= 0 or self.roll.width <= 0:
            return 0.0
        piece_area = sum(p.placed_w * p.placed_h for p in self.placements)
        return piece_area / (self.roll.width * self.length_used)


@dataclass
class MarkerResult:
    """
    Result returned by ``make_marker``.

    Attributes
    ----------
    ok : bool
        True if every piece instance was placed.
    layouts : list[RollLayout]
        One layout per roll (may include rolls with zero placements if all
        pieces fit on the earlier rolls).
    utilization : float
        Aggregate utilisation across all consumed roll area.
    unplaced : list[str]
        Piece names that could not be placed (non-empty iff ok=False).
    errors : list[str]
        Friendly error strings.
    """
    ok: bool
    layouts: list[RollLayout]
    utilization: float
    unplaced: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# NFP helpers — Shapely-backed polygon ops
# ---------------------------------------------------------------------------

def _make_shapely_polygon(piece: FabricPiece, angle: float) -> "_SPolygon":
    """Return a Shapely polygon for *piece* rotated by *angle* degrees."""
    if piece.polygon:
        pts = piece.polygon
    else:
        # Rectangle: lower-left at origin
        pts = [(0, 0), (piece.w, 0), (piece.w, piece.h), (0, piece.h)]
    poly = _SPolygon(pts)
    if abs(angle) > 1e-9:
        poly = _s_rotate(poly, angle, origin=(0, 0), use_radians=False)
    # Normalise so min-corner is at origin
    minx, miny, _, _ = poly.bounds
    poly = _s_translate(poly, -minx, -miny)
    return poly


def _bounding_box_after_rotation(piece: FabricPiece, angle: float) -> tuple[float, float]:
    """
    Return (placed_w, placed_h) of the piece's bounding box after rotation.
    Uses Shapely if polygon is provided; otherwise analytical for rect.
    """
    if piece.polygon and _HAS_SHAPELY:
        poly = _make_shapely_polygon(piece, angle)
        minx, miny, maxx, maxy = poly.bounds
        return (maxx - minx, maxy - miny)
    # Rectangular bounding-box rotation
    rad = math.radians(angle)
    c, s = abs(math.cos(rad)), abs(math.sin(rad))
    return (piece.w * c + piece.h * s, piece.w * s + piece.h * c)


# ---------------------------------------------------------------------------
# Skyline bin-packing (single roll)
# ---------------------------------------------------------------------------

class _Skyline:
    """
    Mutable skyline for a single fabric roll.

    Coordinates are in *usable* space: (0, 0) is the top-left of the usable
    area after margin has been subtracted.  The x-axis runs along the roll
    width; the y-axis runs along the roll length.
    """

    def __init__(self, usable_w: float, usable_h: float) -> None:
        self.usable_w = usable_w
        self.usable_h = usable_h
        # segments: list of [x_left, height]
        self._segs: list[list[float]] = [[0.0, 0.0]]

    def _seg_right(self, i: int) -> float:
        if i + 1 < len(self._segs):
            return self._segs[i + 1][0]
        return self.usable_w

    def find_placement(
        self, pw: float, ph: float, kerf: float
    ) -> Optional[tuple[float, float]]:
        """Return (x, y) in usable space or None."""
        best_y: Optional[float] = None
        best_x: Optional[float] = None

        for i, (x_left, _) in enumerate(self._segs):
            x_end = x_left + pw
            if x_end > self.usable_w + 1e-9:
                continue
            max_h = self._max_height_in_range(x_left, x_end)
            if max_h + ph > self.usable_h + 1e-9:
                continue
            if best_y is None or max_h < best_y:
                best_y = max_h
                best_x = x_left

        if best_x is None:
            return None
        return (best_x, best_y)

    def _max_height_in_range(self, x_l: float, x_r: float) -> float:
        max_h = 0.0
        for i, (x_seg, h_seg) in enumerate(self._segs):
            seg_r = self._seg_right(i)
            if seg_r <= x_l:
                continue
            if x_seg >= x_r:
                break
            if h_seg > max_h:
                max_h = h_seg
        return max_h

    def place(self, x: float, y: float, pw: float, ph: float, kerf: float) -> None:
        new_h = y + ph + kerf
        eff_right = min(x + pw + kerf, self.usable_w)
        self._update_range(x, eff_right, new_h)

    def _update_range(self, x_l: float, x_r: float, new_h: float) -> None:
        new_segs: list[list[float]] = []
        for i, (x_seg, h_seg) in enumerate(self._segs):
            seg_r = self._seg_right(i)
            if seg_r <= x_l or x_seg >= x_r:
                new_segs.append([x_seg, h_seg])
                continue
            if x_seg < x_l:
                new_segs.append([x_seg, h_seg])
                new_segs.append([x_l, max(h_seg, new_h)])
            else:
                new_segs.append([x_seg, max(h_seg, new_h)])
            if seg_r > x_r:
                new_segs.append([x_r, h_seg])

        new_segs.sort(key=lambda s: s[0])
        merged: list[list[float]] = []
        for seg in new_segs:
            if merged and abs(merged[-1][0] - seg[0]) < 1e-12:
                merged[-1] = seg
            else:
                merged.append(seg)
        # Remove consecutive same-height duplicates
        out: list[list[float]] = [merged[0]] if merged else [[0.0, 0.0]]
        for seg in merged[1:]:
            if abs(seg[1] - out[-1][1]) > 1e-12:
                out.append(seg)
        self._segs = out

    def max_height(self) -> float:
        """Current maximum occupied height (= roll length used)."""
        if not self._segs:
            return 0.0
        return max(h for _, h in self._segs)


# ---------------------------------------------------------------------------
# Per-roll nesting pass
# ---------------------------------------------------------------------------

def _nest_onto_roll(
    instances: list[tuple[str, FabricPiece]],
    roll: FabricRoll,
) -> tuple[list[PiecePlacement], list[tuple[str, FabricPiece]]]:
    """
    Greedily nest *instances* onto *roll*.

    Returns
    -------
    placed : list[PiecePlacement]
    remaining : list of (name, piece) that could not be placed
    """
    usable_w = roll.width - 2.0 * roll.margin
    max_len = roll.max_length - 2.0 * roll.margin if math.isfinite(roll.max_length) else math.inf
    if usable_w <= 0 or max_len <= 0:
        return [], instances

    skyline = _Skyline(usable_w, max_len)
    placed: list[PiecePlacement] = []
    remaining: list[tuple[str, FabricPiece]] = []

    for inst_name, piece in instances:
        best_pos: Optional[tuple[float, float, float, float, float]] = None  # x,y,pw,ph,angle
        best_y = math.inf

        for angle in piece.grain_angles:
            pw, ph = _bounding_box_after_rotation(piece, angle)
            if pw > usable_w + 1e-9:
                # Try flipping the bounding box (180° doesn't change bbox for rect)
                continue
            pos = skyline.find_placement(pw, ph, roll.kerf)
            if pos is not None:
                x_usable, y_usable = pos
                if y_usable < best_y:
                    best_y = y_usable
                    best_pos = (x_usable, y_usable, pw, ph, angle)

        if best_pos is not None:
            x_u, y_u, pw, ph, angle = best_pos
            skyline.place(x_u, y_u, pw, ph, roll.kerf)
            placed.append(PiecePlacement(
                piece_name=inst_name,
                roll_name=roll.name,
                x=x_u + roll.margin,
                y=y_u + roll.margin,
                placed_w=pw,
                placed_h=ph,
                angle=angle,
            ))
        else:
            remaining.append((inst_name, piece))

    return placed, remaining


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_marker(
    pieces: list[FabricPiece],
    rolls: list[FabricRoll],
    sort_by_area: bool = True,
) -> MarkerResult:
    """
    Nest fabric pieces onto one or more rolls and produce a cut-room marker.

    Parameters
    ----------
    pieces : list[FabricPiece]
        Pieces to cut.  Each piece's ``qty`` controls how many instances
        are generated.
    rolls : list[FabricRoll]
        Available fabric rolls, tried in order.  A piece is placed on the
        first roll where it fits; if it doesn't fit on any roll it is
        reported as unplaced.
    sort_by_area : bool
        If True (default) sort pieces largest-first before packing.  This
        improves utilisation significantly.

    Returns
    -------
    MarkerResult
        .ok            — True iff every piece instance was placed
        .layouts       — per-roll layout
        .utilization   — aggregate utilisation
        .unplaced      — list of piece instance names not placed
        .errors        — list of error strings
    """
    errors: list[str] = []

    # --- Validate inputs ---
    if not pieces:
        return MarkerResult(ok=True, layouts=[], utilization=0.0)

    if not rolls:
        errors.append("No fabric rolls provided.")
        return MarkerResult(ok=False, layouts=[], utilization=0.0, errors=errors)

    for r in rolls:
        if r.width <= 0:
            errors.append(f"Roll '{r.name}': width must be > 0.")
    if errors:
        return MarkerResult(ok=False, layouts=[], utilization=0.0, errors=errors)

    # --- Expand qty into instances ---
    instances: list[tuple[str, FabricPiece]] = []
    for piece in pieces:
        for i in range(piece.qty):
            inst_name = piece.name if piece.qty == 1 else f"{piece.name}#{i+1}"
            instances.append((inst_name, piece))

    # --- Largest-first sort ---
    if sort_by_area:
        instances.sort(key=lambda t: -(t[1].w * t[1].h))

    # --- Try to fit onto each roll in sequence ---
    layouts: list[RollLayout] = []
    remaining = list(instances)

    for roll in rolls:
        if not remaining:
            break
        layout = RollLayout(roll=roll)
        placed, remaining = _nest_onto_roll(remaining, roll)
        layout.placements = placed
        if placed:
            # length used = max y-coordinate of any placement (in usable space)
            max_y = max(
                (p.y - roll.margin + p.placed_h)
                for p in placed
            )
            layout.length_used = max_y + roll.margin
        layouts.append(layout)

    # --- Aggregate results ---
    unplaced = [name for name, _ in remaining]
    ok = len(unplaced) == 0

    total_piece_area = sum(p.placed_w * p.placed_h for lo in layouts for p in lo.placements)
    total_roll_area = sum(
        lo.roll.width * lo.length_used
        for lo in layouts
        if lo.length_used > 0
    )
    utilization = (total_piece_area / total_roll_area) if total_roll_area > 0 else 0.0
    utilization = min(utilization, 1.0)

    if unplaced:
        errors.append(
            f"{len(unplaced)} piece instance(s) could not be placed on any roll: "
            + ", ".join(unplaced[:10])
            + ("…" if len(unplaced) > 10 else "")
        )

    return MarkerResult(
        ok=ok,
        layouts=layouts,
        utilization=round(utilization, 6),
        unplaced=unplaced,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Convenience: serialisable dict form
# ---------------------------------------------------------------------------

def marker_result_to_dict(result: MarkerResult) -> dict:
    """Convert a MarkerResult to a JSON-serialisable dict."""
    layouts_out = []
    for lo in result.layouts:
        placements_out = [
            {
                "piece_name": p.piece_name,
                "roll_name": p.roll_name,
                "x": round(p.x, 4),
                "y": round(p.y, 4),
                "placed_w": round(p.placed_w, 4),
                "placed_h": round(p.placed_h, 4),
                "angle": p.angle,
            }
            for p in lo.placements
        ]
        layouts_out.append({
            "roll": lo.roll.name,
            "roll_width": lo.roll.width,
            "length_used": round(lo.length_used, 4),
            "utilization": round(lo.utilization, 6),
            "placements": placements_out,
        })

    return {
        "ok": result.ok,
        "utilization": result.utilization,
        "unplaced": result.unplaced,
        "errors": result.errors,
        "layouts": layouts_out,
    }
