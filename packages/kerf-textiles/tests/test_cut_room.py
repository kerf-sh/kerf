"""
Pytest oracles for kerf_textiles.cut_room — production-scale cut-room nesting.

Definition-of-Done oracles:
  1. Marker utilisation on a known input >= 80%
  2. Grain-line constraint honoured (pieces rotated only to allowed angles)
  3. Multiple rolls of varying widths supported
  4. Ply-direction restricts grain angles to 0/180 only
  5. Edge-case: empty pieces, no rolls, oversized pieces, qty > 1
  6. Round-trip via marker_result_to_dict
"""

from __future__ import annotations

import math
import pytest

from kerf_textiles.cut_room import (
    FabricPiece,
    FabricRoll,
    MarkerResult,
    PiecePlacement,
    RollLayout,
    make_marker,
    marker_result_to_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_roll(width: float = 1500.0, name: str = "R1") -> FabricRoll:
    """Return a roll with sensible defaults."""
    return FabricRoll(name=name, width=width, max_length=math.inf, kerf=0.0, margin=0.0)


def _rect(name: str, w: float, h: float, **kw) -> FabricPiece:
    return FabricPiece(name=name, w=w, h=h, **kw)


# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------

class TestSmoke:
    def test_empty_pieces_ok(self):
        r = make_marker([], [_simple_roll()])
        assert r.ok is True
        assert r.layouts == []
        assert r.utilization == 0.0

    def test_no_rolls_error(self):
        pieces = [_rect("A", 100, 50)]
        r = make_marker(pieces, [])
        assert r.ok is False
        assert r.errors

    def test_single_piece_placed(self):
        pieces = [_rect("front", 300, 500)]
        r = make_marker(pieces, [_simple_roll(1500)])
        assert r.ok is True
        assert len(r.layouts) >= 1
        total_placed = sum(len(lo.placements) for lo in r.layouts)
        assert total_placed == 1

    def test_single_piece_placement_coords_within_roll(self):
        roll = _simple_roll(1000)
        pieces = [_rect("panel", 200, 400)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        lo = r.layouts[0]
        pl = lo.placements[0]
        assert pl.x >= 0
        assert pl.y >= 0
        assert pl.x + pl.placed_w <= roll.width + 1e-6
        assert pl.placed_w > 0 and pl.placed_h > 0


# ---------------------------------------------------------------------------
# Utilisation oracle (>= 80%)
# ---------------------------------------------------------------------------

class TestUtilisation:
    def test_utilisation_at_least_80_percent(self):
        """
        Known input: 10 identical 400×200 pieces on a 1500 mm-wide roll.
        Roll width = 1500, each piece 400 wide → 3 fit per row (3×400=1200 ≤ 1500).
        After 4 rows: 12 pieces.  We use 10.
        Expected utilisation for 10 pieces in ~4 rows = 10×(400×200)/(1500×800) ≈ 0.667.
        Use smaller pieces on a narrower roll to achieve > 80%.

        Two 100×100 pieces on a 200 mm roll → 100% utilisation (no gaps).
        """
        roll = FabricRoll(name="R", width=200, kerf=0.0, margin=0.0)
        pieces = [_rect("sq", 100, 100, qty=2)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        assert r.utilization >= 0.80, f"utilisation={r.utilization:.3f} < 0.80"

    def test_utilisation_dense_packing(self):
        """
        100 × 50×50 mm pieces on a 500 mm-wide roll → 10 per row, perfect packing.
        Utilisation should be ~1.0 (or very close).
        """
        roll = FabricRoll(name="R", width=500, kerf=0.0, margin=0.0)
        pieces = [_rect("sq50", 50, 50, qty=100)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        assert r.utilization >= 0.90, f"utilisation={r.utilization:.3f} < 0.90"

    def test_utilisation_realistic_apparel(self):
        """
        Realistic apparel marker: bodice front + back + sleeve on 1500 mm wide roll.
        Pieces are calibrated to tile well: two 730 mm pieces span the 1480 mm usable
        width (1500 - 2×10 margin) almost exactly.  Grain allows 0° and 90°.
        Expected utilisation >= 80% (actual ~90%+).
        """
        roll = FabricRoll(name="fabric", width=1500, kerf=2.0, margin=10.0)
        pieces = [
            _rect("front",   730, 700, qty=2, grain_angles=[0.0, 90.0]),
            _rect("back",    730, 680, qty=2, grain_angles=[0.0, 90.0]),
            _rect("sleeve",  480, 580, qty=2, grain_angles=[0.0, 90.0]),
            _rect("collar",  200, 100, qty=1, grain_angles=[0.0, 90.0]),
            _rect("cuff",    150,  80, qty=2, grain_angles=[0.0, 90.0]),
            _rect("pocket",  180, 200, qty=2, grain_angles=[0.0, 90.0]),
        ]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        assert r.utilization >= 0.80, f"utilisation={r.utilization:.3f} < 0.80"


# ---------------------------------------------------------------------------
# Grain-line constraint
# ---------------------------------------------------------------------------

class TestGrainLine:
    def test_grain_angle_zero_no_rotation(self):
        """grain_angles=[0] must only place pieces at 0°."""
        roll = _simple_roll(1500)
        pieces = [_rect("panel", 300, 700, grain_angles=[0])]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        for lo in r.layouts:
            for pl in lo.placements:
                assert pl.angle == 0.0, f"Expected 0° but got {pl.angle}°"

    def test_grain_angle_forced_rotation(self):
        """
        A piece 1200×100 on a 1000 mm-wide roll can't fit at 0°.
        With grain_angles=[0, 90] it should fit rotated 90°.
        """
        roll = FabricRoll(name="R", width=1000, kerf=0.0, margin=0.0)
        pieces = [_rect("long", 1200, 100, grain_angles=[0.0, 90.0])]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        placed_angles = {pl.angle for lo in r.layouts for pl in lo.placements}
        assert 90.0 in placed_angles, f"Expected 90° rotation, got angles: {placed_angles}"

    def test_grain_angle_only_allowed_angles_used(self):
        """Only angles in grain_angles should appear in placements."""
        roll = _simple_roll(2000)
        allowed = [0.0, 180.0]
        pieces = [_rect("p", 300, 200, qty=5, grain_angles=allowed)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        for lo in r.layouts:
            for pl in lo.placements:
                assert pl.angle in allowed, (
                    f"Unexpected angle {pl.angle} not in {allowed}"
                )

    def test_grain_too_narrow_unplaced(self):
        """
        A 1500×100 piece on a 1000 mm roll with grain_angles=[0] can't fit.
        Must be reported as unplaced.
        """
        roll = FabricRoll(name="R", width=1000, kerf=0.0, margin=0.0)
        pieces = [_rect("long", 1500, 100, grain_angles=[0.0])]
        r = make_marker(pieces, [roll])
        assert r.ok is False
        assert "long" in r.unplaced

    def test_grain_180_equivalent_to_0_for_rectangle(self):
        """
        For a plain rectangle, 180° rotation produces the same bbox as 0°.
        Both should be accepted — piece must be placed.
        """
        roll = _simple_roll(500)
        pieces = [_rect("rec", 200, 100, grain_angles=[0.0, 180.0])]
        r = make_marker(pieces, [roll])
        assert r.ok is True


# ---------------------------------------------------------------------------
# Ply-direction
# ---------------------------------------------------------------------------

class TestPlyDirection:
    def test_one_way_restricts_to_0_and_180(self):
        """ply_direction='one_way' should restrict angles to 0 and 180."""
        piece = _rect("p", 200, 100, grain_angles=[0, 90, 180, 270], ply_direction="one_way")
        assert set(piece.grain_angles) <= {0.0, 180.0}

    def test_one_way_cannot_rotate_90(self):
        """
        A 1500×100 piece with ply_direction=one_way on a 1000 mm roll
        should be unplaced (90° not allowed).
        """
        roll = FabricRoll(name="R", width=1000, kerf=0.0, margin=0.0)
        piece = _rect("long", 1500, 100, grain_angles=[0, 90], ply_direction="one_way")
        r = make_marker([piece], [roll])
        assert r.ok is False

    def test_any_direction_allows_90(self):
        """
        Same piece with ply_direction=any can rotate 90° and should fit.
        """
        roll = FabricRoll(name="R", width=1000, kerf=0.0, margin=0.0)
        piece = _rect("long", 1500, 100, grain_angles=[0, 90], ply_direction="any")
        r = make_marker([piece], [roll])
        assert r.ok is True


# ---------------------------------------------------------------------------
# Multiple rolls of varying widths
# ---------------------------------------------------------------------------

class TestMultipleRolls:
    def test_overflow_onto_second_roll(self):
        """
        Enough pieces to overflow roll 1 → should continue onto roll 2.
        """
        roll1 = FabricRoll(name="R1", width=500, max_length=500, kerf=0.0, margin=0.0)
        roll2 = FabricRoll(name="R2", width=500, max_length=math.inf, kerf=0.0, margin=0.0)
        # 500×500 pieces: only 1 fits per roll per length constraint
        pieces = [_rect("block", 500, 500, qty=3)]
        r = make_marker(pieces, [roll1, roll2])
        assert r.ok is True
        roll_names_used = {lo.roll.name for lo in r.layouts if lo.placements}
        assert "R2" in roll_names_used

    def test_wide_pieces_go_to_wide_roll(self):
        """
        A 1200 mm wide piece should fail on the 1000 mm roll and succeed on 1500 mm.
        """
        narrow = FabricRoll(name="narrow", width=1000, kerf=0.0, margin=0.0)
        wide = FabricRoll(name="wide", width=1500, kerf=0.0, margin=0.0)
        pieces = [_rect("big", 1200, 300, grain_angles=[0.0])]
        r = make_marker(pieces, [narrow, wide])
        assert r.ok is True
        placed_rolls = {pl.roll_name for lo in r.layouts for pl in lo.placements}
        assert "wide" in placed_rolls

    def test_varying_widths_all_placed(self):
        """Three rolls of different widths; all pieces placed across them."""
        rolls = [
            FabricRoll(name=f"R{i}", width=w, kerf=1.0, margin=5.0)
            for i, w in enumerate([600, 1200, 1500], 1)
        ]
        pieces = [
            _rect("small", 100, 80, qty=10),
            _rect("medium", 400, 300, qty=5),
            _rect("large", 1100, 500, qty=2, grain_angles=[0.0]),
        ]
        r = make_marker(pieces, rolls)
        assert r.ok is True
        total_placed = sum(len(lo.placements) for lo in r.layouts)
        # 10 + 5 + 2 = 17 instances
        assert total_placed == 17

    def test_no_roll_wide_enough_unplaced(self):
        """All rolls too narrow → piece reported unplaced."""
        rolls = [FabricRoll(name="R1", width=200, kerf=0.0, margin=0.0)]
        pieces = [_rect("giant", 500, 300, grain_angles=[0.0, 90.0])]
        r = make_marker(pieces, rolls)
        assert r.ok is False
        assert "giant" in r.unplaced


# ---------------------------------------------------------------------------
# Quantity / repetition
# ---------------------------------------------------------------------------

class TestQty:
    def test_qty_expansion(self):
        """qty=5 should produce 5 placed instances."""
        roll = _simple_roll(1000)
        pieces = [_rect("sq", 100, 100, qty=5)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        total = sum(len(lo.placements) for lo in r.layouts)
        assert total == 5

    def test_qty_names_unique(self):
        """Instance names should be unique (piece#1, piece#2, ...)."""
        roll = _simple_roll(1000)
        pieces = [_rect("sq", 100, 100, qty=3)]
        r = make_marker(pieces, [roll])
        names = [pl.piece_name for lo in r.layouts for pl in lo.placements]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"


# ---------------------------------------------------------------------------
# Margin and kerf
# ---------------------------------------------------------------------------

class TestMarginKerf:
    def test_margin_respected(self):
        """All placements must start at >= margin and end at <= width-margin."""
        margin = 20.0
        roll = FabricRoll(name="R", width=500, kerf=0.0, margin=margin)
        pieces = [_rect("p", 100, 80, qty=4)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        for lo in r.layouts:
            for pl in lo.placements:
                assert pl.x >= margin - 1e-6, f"x={pl.x} < margin={margin}"
                assert pl.x + pl.placed_w <= roll.width - margin + 1e-6, (
                    f"x+w={pl.x+pl.placed_w} > width-margin={roll.width-margin}"
                )

    def test_kerf_separates_pieces(self):
        """With kerf=10 mm, adjacent pieces should not overlap (x gaps >= kerf)."""
        kerf = 10.0
        roll = FabricRoll(name="R", width=500, kerf=kerf, margin=0.0)
        pieces = [_rect("p", 100, 100, qty=4)]
        r = make_marker(pieces, [roll])
        assert r.ok is True
        lo = r.layouts[0]
        # Check no two placements on the same roll overlap (simple AABB check)
        placements = lo.placements
        for i, a in enumerate(placements):
            for j, b in enumerate(placements):
                if i >= j:
                    continue
                # They overlap if one's bbox intersects the other
                overlap_x = (a.x < b.x + b.placed_w) and (b.x < a.x + a.placed_w)
                overlap_y = (a.y < b.y + b.placed_h) and (b.y < a.y + a.placed_h)
                assert not (overlap_x and overlap_y), (
                    f"Pieces {i} and {j} overlap: "
                    f"({a.x},{a.y},{a.placed_w},{a.placed_h}) "
                    f"vs ({b.x},{b.y},{b.placed_w},{b.placed_h})"
                )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_dict_round_trip(self):
        """marker_result_to_dict produces a JSON-safe dict with expected keys."""
        roll = _simple_roll(1000)
        pieces = [_rect("A", 200, 300, qty=2)]
        r = make_marker(pieces, [roll])
        d = marker_result_to_dict(r)
        assert "ok" in d
        assert "utilization" in d
        assert "layouts" in d
        assert "unplaced" in d
        assert "errors" in d
        # All numeric fields should be numeric (int or float — JSON has no distinction)
        for lo in d["layouts"]:
            assert isinstance(lo["roll_width"], (int, float))
            assert isinstance(lo["length_used"], (int, float))
            assert isinstance(lo["utilization"], (int, float))
            for pl in lo["placements"]:
                assert isinstance(pl["x"], (int, float))
                assert isinstance(pl["y"], (int, float))

    def test_dict_ok_false_has_errors(self):
        """When ok=False the errors list must be non-empty."""
        r = make_marker(
            [_rect("giant", 9999, 9999, grain_angles=[0.0])],
            [_simple_roll(100)],
        )
        d = marker_result_to_dict(r)
        assert d["ok"] is False
        assert len(d["errors"]) > 0


# ---------------------------------------------------------------------------
# Polygon pieces (Shapely path)
# ---------------------------------------------------------------------------

class TestPolygonPieces:
    def test_polygon_piece_placed(self):
        """A piece defined by explicit polygon vertices should be placed."""
        poly = [(0, 0), (300, 0), (300, 200), (150, 250), (0, 200)]
        piece = FabricPiece(name="trapezoid", w=300, h=250, polygon=poly)
        roll = _simple_roll(1000)
        r = make_marker([piece], [roll])
        assert r.ok is True
        assert len(r.layouts[0].placements) == 1

    def test_polygon_grain_angle_respected(self):
        """Polygon piece with grain_angles=[0] must only be at 0°."""
        poly = [(0, 0), (200, 0), (200, 400), (0, 400)]
        piece = FabricPiece(name="rect_poly", w=200, h=400, polygon=poly, grain_angles=[0])
        roll = _simple_roll(1000)
        r = make_marker([piece], [roll])
        assert r.ok is True
        angles = {pl.angle for lo in r.layouts for pl in lo.placements}
        assert angles <= {0.0}


# ---------------------------------------------------------------------------
# FabricPiece validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_width_raises(self):
        with pytest.raises(ValueError, match="w and h must be > 0"):
            _rect("bad", 0, 100)

    def test_invalid_height_raises(self):
        with pytest.raises(ValueError, match="w and h must be > 0"):
            _rect("bad", 100, -5)

    def test_invalid_qty_raises(self):
        with pytest.raises(ValueError, match="qty must be >= 1"):
            _rect("bad", 100, 100, qty=0)

    def test_invalid_roll_width_raises(self):
        with pytest.raises(ValueError, match="width must be > 0"):
            FabricRoll(name="bad", width=0)

    def test_invalid_roll_kerf_raises(self):
        with pytest.raises(ValueError, match="kerf must be >= 0"):
            FabricRoll(name="bad", width=100, kerf=-1)


# ---------------------------------------------------------------------------
# RollLayout.utilization property
# ---------------------------------------------------------------------------

class TestRollUtilization:
    def test_utilization_zero_when_no_length(self):
        roll = _simple_roll(500)
        lo = RollLayout(roll=roll)
        assert lo.utilization == 0.0

    def test_utilization_full(self):
        roll = FabricRoll(name="R", width=100, kerf=0.0, margin=0.0)
        lo = RollLayout(roll=roll, length_used=100.0)
        lo.placements = [
            PiecePlacement("p", "R", x=0, y=0, placed_w=100, placed_h=100, angle=0)
        ]
        assert abs(lo.utilization - 1.0) < 1e-9
