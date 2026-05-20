"""
test_feature_jewelry_bezel_auto.py
===================================

T-3: Jewelry — bezel_auto wizard

Spec: 25 stone shapes (round/oval/marquise/pear/cushion/emerald + irregular
cabochons); generated bezel wall thickness & seat depth within spec; clean
boolean (no error key in returned dict).

Coverage breakdown:
  - 25 parametrised stone-shape permutations across bezel_auto_from_stone
  - Wall-thickness within-spec check for every shape
  - Seat-groove depth within-spec check for every shape
  - No "error" key ("clean boolean") for every shape
  - Boundary: minimum-size stone (0.5 mm)
  - Boundary: large stone (30 mm)
  - Malformed: non-positive stone_mm → error dict (never raises)
  - Malformed: unknown cut → error dict
  - Malformed: unknown style → error dict
  - Malformed: bad edge_treatment → error dict
  - Idempotency: calling twice with same args produces equivalent geometry
  - Cabochon-style irregular stones round-trip cleanly
  - Tube setting: 25 sizes round-trip wall + volume correctness
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.bezel_auto import (
    BEZEL_STYLES,
    _MIN_WALL_TABLE,
    _min_wall_for_stone,
    bezel_auto_from_stone,
    tube_setting_auto,
)

# ---------------------------------------------------------------------------
# 25 stone shapes drawn from the full GEMSTONE_CUTS set.
# Includes round/oval/marquise/pear/cushion/emerald/cabochon and assorted fancy.
# ---------------------------------------------------------------------------

_STONE_SHAPES: list[tuple[str, float]] = [
    # round / brilliant family
    ("round_brilliant",  6.5),
    ("old_european",     7.0),
    ("old_mine",         7.5),
    ("single_cut",       2.0),
    ("rose_cut",         5.0),
    # oval / elongated rounds
    ("oval",             7.7),
    ("briolette",        5.0),
    # emerald / step-cut family
    ("emerald",          8.0),
    ("asscher",          7.0),
    ("baguette",         4.0),
    ("square_emerald",   7.5),
    ("tapered_baguette", 5.0),
    ("ceylon",           6.0),
    ("french_cut",       4.5),
    ("flanders",         6.5),
    # cushion / radiant
    ("cushion",          6.0),
    ("radiant",          7.0),
    # marquise / pear / heart / pointed ends
    ("marquise",        10.0),
    ("pear",             9.0),
    ("heart",            8.0),
    ("bullet",           5.0),
    ("half_moon",        6.0),
    # fancy polygonal
    ("princess",         5.5),
    ("trillion",         7.0),
    # kite/shield class (irregular cabochon-adjacent)
    ("kite",             6.0),
]

assert len(_STONE_SHAPES) == 25, f"Need exactly 25 shapes, got {len(_STONE_SHAPES)}"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _wall_in_spec(spec: dict) -> bool:
    """Return True if wall_thickness_mm >= min_wall_mm."""
    return spec["wall_thickness_mm"] >= spec["min_wall_mm"]


def _seat_depth_in_spec(spec: dict) -> bool:
    """
    Seat groove depth must be 0.10 mm (industry standard).
    seat_groove_z_mm must be < bezel_height_mm and >= 0.1 mm.
    """
    return (
        abs(spec["seat_groove_depth_mm"] - 0.10) < 1e-6
        and spec["seat_groove_z_mm"] < spec["bezel_height_mm"]
        and spec["seat_groove_z_mm"] >= 0.10
    )


def _clean_boolean(spec: dict) -> bool:
    """Return True if no 'error' key — represents a valid boolean result."""
    return "error" not in spec


# ---------------------------------------------------------------------------
# 1. Parametrised: 25 stone shapes — clean boolean, wall within spec,
#    seat depth within spec  (3 assertions × 25 = 75 cases)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES)
def test_clean_boolean_no_error(cut: str, stone_mm: float):
    """Every recognised cut produces a spec dict with no 'error' key."""
    spec = bezel_auto_from_stone(cut, stone_mm, "straight")
    assert _clean_boolean(spec), f"Unexpected error for {cut}: {spec.get('error')}"


@pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES)
def test_wall_thickness_within_spec(cut: str, stone_mm: float):
    """Auto-computed wall must be >= min_wall_mm for every stone shape."""
    spec = bezel_auto_from_stone(cut, stone_mm, "straight")
    assert "error" not in spec
    assert _wall_in_spec(spec), (
        f"{cut} @ {stone_mm} mm: wall {spec['wall_thickness_mm']:.4f} < "
        f"min {spec['min_wall_mm']:.4f}"
    )


@pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES)
def test_seat_depth_within_spec(cut: str, stone_mm: float):
    """Seat groove depth 0.10 mm; z-pos within [0.10, bezel_height)."""
    spec = bezel_auto_from_stone(cut, stone_mm, "straight")
    assert "error" not in spec
    assert _seat_depth_in_spec(spec), (
        f"{cut} @ {stone_mm}: seat_depth={spec.get('seat_groove_depth_mm')}, "
        f"seat_z={spec.get('seat_groove_z_mm')}, "
        f"height={spec.get('bezel_height_mm')}"
    )


# ---------------------------------------------------------------------------
# 2. All bezel styles × canonical stone — clean boolean
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style", sorted(BEZEL_STYLES))
def test_all_styles_clean_boolean(style: str):
    """Every bezel style must produce a valid spec for round_brilliant."""
    spec = bezel_auto_from_stone("round_brilliant", 6.5, style)
    assert _clean_boolean(spec), f"style={style}: {spec.get('error')}"
    assert spec["style"] == style


# ---------------------------------------------------------------------------
# 3. Boundary: minimum-size stone
# ---------------------------------------------------------------------------

class TestBoundaryMinStone:
    def test_tiny_stone_no_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 0.5, "straight")
        assert _clean_boolean(spec)

    def test_tiny_stone_wall_gte_min(self):
        spec = bezel_auto_from_stone("round_brilliant", 0.5, "straight")
        assert spec["wall_thickness_mm"] >= spec["min_wall_mm"]

    def test_tiny_stone_height_floor(self):
        """Even sub-1 mm stone should meet the 0.5 mm height floor."""
        spec = bezel_auto_from_stone("single_cut", 0.5, "straight")
        assert spec["bezel_height_mm"] >= 0.5

    def test_tiny_stone_seat_groove_z_floor(self):
        spec = bezel_auto_from_stone("round_brilliant", 0.5, "straight")
        assert spec["seat_groove_z_mm"] >= 0.10


# ---------------------------------------------------------------------------
# 4. Boundary: large stone
# ---------------------------------------------------------------------------

class TestBoundaryLargeStone:
    def test_large_stone_no_error(self):
        spec = bezel_auto_from_stone("emerald", 30.0, "straight")
        assert _clean_boolean(spec)

    def test_large_stone_wall_gte_max_min(self):
        """30 mm stone falls in the ≥ 20 mm bracket → min_wall = 0.70."""
        spec = bezel_auto_from_stone("emerald", 30.0, "straight")
        assert spec["min_wall_mm"] == pytest.approx(0.70)
        assert spec["wall_thickness_mm"] >= 0.70

    def test_large_stone_height_proportional(self):
        """Bezel height grows with stone size."""
        h_small = bezel_auto_from_stone("round_brilliant", 6.0, "straight")["bezel_height_mm"]
        h_large = bezel_auto_from_stone("round_brilliant", 30.0, "straight")["bezel_height_mm"]
        assert h_large > h_small

    def test_large_stone_outer_gt_inner(self):
        spec = bezel_auto_from_stone("oval", 30.0, "straight")
        assert spec["outer_long_mm"] > spec["inner_long_mm"]


# ---------------------------------------------------------------------------
# 5. Malformed input — never raises, returns error dict
# ---------------------------------------------------------------------------

class TestMalformedInputs:
    def test_unknown_cut_returns_error(self):
        spec = bezel_auto_from_stone("dragon_blood", 6.5, "straight")
        assert "error" in spec

    def test_zero_stone_mm_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 0.0, "straight")
        assert "error" in spec

    def test_negative_stone_mm_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", -3.0, "straight")
        assert "error" in spec

    def test_unknown_style_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "flying_saucer")
        assert "error" in spec

    def test_bad_edge_treatment_returns_error(self):
        spec = bezel_auto_from_stone(
            "round_brilliant", 6.5, "straight", edge_treatment="electro_etch"
        )
        assert "error" in spec

    def test_non_numeric_stone_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", "big", "straight")  # type: ignore[arg-type]
        assert "error" in spec

    def test_tube_zero_stone_returns_error(self):
        spec = tube_setting_auto(0)
        assert "error" in spec

    def test_tube_negative_stone_returns_error(self):
        spec = tube_setting_auto(-1.0)
        assert "error" in spec

    def test_tube_non_numeric_returns_error(self):
        spec = tube_setting_auto("six")  # type: ignore[arg-type]
        assert "error" in spec


# ---------------------------------------------------------------------------
# 6. Idempotency: same args → same geometry (different node_id is fine)
# ---------------------------------------------------------------------------

class TestIdempotency:
    _FIELDS = [
        "inner_long_mm", "inner_short_mm", "inner_profile_shape",
        "wall_thickness_mm", "min_wall_mm", "outer_long_mm", "outer_short_mm",
        "bezel_height_mm", "seat_groove_z_mm", "seat_groove_depth_mm",
    ]

    @pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES[:10])
    def test_geometry_idempotent(self, cut: str, stone_mm: float):
        """Two calls with identical args must yield identical geometry fields."""
        spec_a = bezel_auto_from_stone(cut, stone_mm, "straight")
        spec_b = bezel_auto_from_stone(cut, stone_mm, "straight")
        for field in self._FIELDS:
            assert spec_a[field] == pytest.approx(spec_b[field], abs=1e-9), (
                f"Field {field!r} differs between calls for {cut}"
            )

    def test_tube_geometry_idempotent(self):
        """Tube-setting for same stone_mm must produce identical geometry."""
        a = tube_setting_auto(6.5, wall_thickness=0.5, tube_height=2.0)
        b = tube_setting_auto(6.5, wall_thickness=0.5, tube_height=2.0)
        for field in ("id_mm", "od_mm", "wall_thickness_mm", "tube_height_mm", "_volume_mm3"):
            assert a[field] == pytest.approx(b[field], abs=1e-9)

    def test_node_ids_differ_across_calls(self):
        """Each call generates a fresh node UUID (not idempotent by design)."""
        s1 = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        s2 = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert s1["id"] != s2["id"]


# ---------------------------------------------------------------------------
# 7. Cabochon / irregular stone shapes
# ---------------------------------------------------------------------------

class TestCabochonIrregular:
    """Cabochon and bead-family cuts that map to circle / ellipse profiles."""

    def test_cabochon_circle_profile(self):
        spec = bezel_auto_from_stone("cabochon", 8.0, "straight")
        assert spec["inner_profile_shape"] == "circle"

    def test_cabochon_no_error(self):
        spec = bezel_auto_from_stone("cabochon", 8.0, "straight")
        assert _clean_boolean(spec)

    def test_cabochon_wall_within_spec(self):
        spec = bezel_auto_from_stone("cabochon", 8.0, "straight")
        assert _wall_in_spec(spec)

    def test_cabochon_seat_within_spec(self):
        spec = bezel_auto_from_stone("cabochon", 8.0, "straight")
        assert _seat_depth_in_spec(spec)

    def test_briolette_clean_boolean(self):
        spec = bezel_auto_from_stone("briolette", 5.0, "straight")
        assert _clean_boolean(spec)

    def test_portuguese_clean_boolean(self):
        spec = bezel_auto_from_stone("portuguese", 7.0, "straight")
        assert _clean_boolean(spec)

    def test_lozenge_clean_boolean(self):
        spec = bezel_auto_from_stone("lozenge", 6.0, "straight")
        assert _clean_boolean(spec)

    def test_shield_clean_boolean(self):
        spec = bezel_auto_from_stone("shield", 5.5, "straight")
        assert _clean_boolean(spec)

    def test_trapezoid_clean_boolean(self):
        spec = bezel_auto_from_stone("trapezoid", 6.0, "straight")
        assert _clean_boolean(spec)

    def test_calf_head_clean_boolean(self):
        spec = bezel_auto_from_stone("calf_head", 7.0, "straight")
        assert _clean_boolean(spec)


# ---------------------------------------------------------------------------
# 8. Tube setting — 25 sizes round-trip
# ---------------------------------------------------------------------------

_TUBE_SIZES: list[float] = [
    1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5,
    6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 11.0,
    12.0, 14.0, 16.0, 20.0, 25.0,
]

assert len(_TUBE_SIZES) == 25


@pytest.mark.parametrize("stone_mm", _TUBE_SIZES)
def test_tube_id_od_relationship(stone_mm: float):
    """OD = ID + 2 × wall for every tube size."""
    spec = tube_setting_auto(stone_mm)
    assert "error" not in spec
    assert spec["od_mm"] == pytest.approx(
        spec["id_mm"] + 2.0 * spec["wall_thickness_mm"], abs=1e-4
    )


@pytest.mark.parametrize("stone_mm", _TUBE_SIZES)
def test_tube_volume_exact_formula(stone_mm: float):
    """Volume = (OD² - ID²) × π/4 × height (exact annular cylinder formula)."""
    spec = tube_setting_auto(stone_mm)
    assert "error" not in spec
    od, id_, h = spec["od_mm"], spec["id_mm"], spec["tube_height_mm"]
    expected = (od ** 2 - id_ ** 2) * math.pi / 4.0 * h
    assert spec["_volume_mm3"] == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize("stone_mm", _TUBE_SIZES)
def test_tube_wall_gte_min_wall(stone_mm: float):
    """Auto wall must be >= min_wall for every tube size."""
    spec = tube_setting_auto(stone_mm)
    assert "error" not in spec
    assert spec["wall_thickness_mm"] >= spec["min_wall_mm"]


# ---------------------------------------------------------------------------
# 9. inner_long / inner_short geometric correctness for specific cuts
# ---------------------------------------------------------------------------

class TestInnerProfileGeometry:
    """Per-cut inner bore dimension correctness vs. declared aspect ratio."""

    @pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES)
    def test_inner_long_equals_stone_plus_two_clearances(self, cut: str, stone_mm: float):
        clearance = 0.05
        spec = bezel_auto_from_stone(cut, stone_mm, "straight",
                                     girdle_clearance_mm=clearance)
        assert "error" not in spec
        assert spec["inner_long_mm"] == pytest.approx(
            stone_mm + 2.0 * clearance, abs=1e-4
        )

    @pytest.mark.parametrize("cut, stone_mm", _STONE_SHAPES)
    def test_inner_short_lte_inner_long(self, cut: str, stone_mm: float):
        """Short axis can never exceed long axis."""
        spec = bezel_auto_from_stone(cut, stone_mm, "straight")
        assert "error" not in spec
        assert spec["inner_short_mm"] <= spec["inner_long_mm"] + 1e-9
