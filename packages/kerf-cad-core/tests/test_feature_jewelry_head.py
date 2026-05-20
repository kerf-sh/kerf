"""
test_feature_jewelry_head.py — T-11 hermetic pytest suite
==========================================================

Scope: kerf_cad_core.jewelry.head_wizard + kerf_cad_core.jewelry.gallery
       — parametric head/prong wizard and gallery sub-structure builder.

Success criteria (from testing-breakdown.md T-11):
  - 25 head-style × stone-cut combinations
  - 4/6/8 prong counts, basket, cathedral, halo styles
  - Attach point: head outer diameter > stone_mm (stone seated inside head)
  - Boundary / malformed / idempotency cases

All tests are pure-Python — no OCC, no DB, no network.
"""

from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Imports from head_wizard
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.head_wizard import (
    HEAD_STYLES,
    STONE_CUTS,
    _HEAD_DEFAULT_PRONG_COUNT,
    _HEAD_PRONG_DEFAULTS,
    _METAL_DENSITY,
    _POINTED_CUTS,
    _FANCY_CUTS_WITH_CORNERS,
    _ROUND_OVAL_CUTS,
    _MIN_METAL_WALL_MM,
    _MIN_PRONG_WIRE_MM,
    stone_girdle_radius,
    girdle_contact_point,
    prong_angles_for_cut,
    build_head_node,
    build_ring_builder_node,
    head_library_entry,
    _ring_size_to_id_mm,
    _us_size_to_id_mm,
)

# ---------------------------------------------------------------------------
# Imports from gallery
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.gallery import (
    basket_geometry,
    under_bezel_gallery_geometry,
    cathedral_shoulder_geometry,
    trellis_shoulder_geometry,
    peg_head_adapter_geometry,
    basket_metal_volume_mm3,
    basket_surface_area_mm2,
    metal_weight_grams,
    min_wire_diameter_check,
    _VALID_CUTOUT_STYLES,
    _VALID_BORDER_STYLES,
)

# ---------------------------------------------------------------------------
# 25 head-style × stone-cut combinations
# 5 head styles × 5 stone cuts = 25
# Covers: 4-prong, 6-prong, 8-prong (double_claw), basket, halo
# Stone cuts span round, fancy-corner, pointed, oval, bezel families
# ---------------------------------------------------------------------------

_HEAD_STYLES_5 = [
    "four_prong_solitaire",   # 4 prongs
    "six_prong_solitaire",    # 6 prongs
    "double_claw",            # 8 prongs (4 × 2)
    "basket",                 # basket/gallery rail
    "halo",                   # concentric accent ring
]

_STONE_CUTS_5 = [
    "round_brilliant",   # classic round
    "princess",          # fancy square-corner
    "oval",              # elongated round
    "marquise",          # pointed (V-prong)
    "emerald",           # rectangular step-cut
]

_STONE_MM = 6.5  # 1 ct equivalent round brilliant diameter


# ---------------------------------------------------------------------------
# Matrix 1: head_library_entry — 25 combos produce valid spec
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_head_library_entry_shape(style: str, cut: str):
    """head_library_entry must return a dict with all required keys for every
    style/cut combination."""
    spec = head_library_entry(style, cut, _STONE_MM)

    required = {
        "head_style", "cut", "stone_mm",
        "prong_count", "prong_wire_dia", "claw_length", "claw_tip_radius",
        "seat_angle_deg", "gallery_rail", "bezel_wall", "bezel_height",
        "start_angle_deg", "recommended_for",
    }
    assert required <= set(spec.keys()), (
        f"{style}/{cut}: missing keys {required - set(spec.keys())}"
    )
    assert spec["head_style"] == style
    assert spec["cut"] == cut
    assert spec["stone_mm"] == pytest.approx(_STONE_MM)


@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_head_library_entry_prong_positive(style: str, cut: str):
    """Prong dimensions from library must all be non-negative; prong_wire_dia
    >= _MIN_PRONG_WIRE_MM when prong_count > 0."""
    spec = head_library_entry(style, cut, _STONE_MM)
    assert spec["prong_wire_dia"] >= 0.0
    assert spec["claw_length"] >= 0.0
    assert spec["claw_tip_radius"] >= 0.0
    if spec["prong_count"] > 0:
        assert spec["prong_wire_dia"] >= _MIN_PRONG_WIRE_MM, (
            f"{style}/{cut}: prong_wire_dia {spec['prong_wire_dia']} below minimum"
        )


@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_head_library_entry_bezel_valid(style: str, cut: str):
    """Bezel dimensions must be >= _MIN_METAL_WALL_MM wall and positive height."""
    spec = head_library_entry(style, cut, _STONE_MM)
    assert spec["bezel_wall"] >= _MIN_METAL_WALL_MM, (
        f"{style}/{cut}: bezel_wall {spec['bezel_wall']} < minimum {_MIN_METAL_WALL_MM}"
    )
    assert spec["bezel_height"] > 0.0


# ---------------------------------------------------------------------------
# Matrix 2: build_head_node — attach point / seated stone check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_build_head_node_outer_dia_exceeds_stone(style: str, cut: str):
    """Head outer diameter must exceed stone_mm — the stone seats *inside*
    the head (attach-point coincidence check)."""
    spec = head_library_entry(style, cut, _STONE_MM)
    node = build_head_node(
        node_id="test-n1",
        head_style=style,
        cut=cut,
        stone_mm=_STONE_MM,
        prong_count=spec["prong_count"],
        prong_wire_dia=spec["prong_wire_dia"],
        claw_length=spec["claw_length"],
        claw_tip_radius=spec["claw_tip_radius"],
        seat_angle_deg=spec["seat_angle_deg"],
        gallery_rail=spec["gallery_rail"],
        bezel_wall=spec["bezel_wall"],
        bezel_height=spec["bezel_height"],
        start_angle_deg=spec["start_angle_deg"],
    )

    # _head_outer_dia = stone_mm + 2 × prong_wire_dia >= stone_mm
    assert node["_head_outer_dia"] >= _STONE_MM, (
        f"{style}/{cut}: _head_outer_dia {node['_head_outer_dia']} < stone_mm {_STONE_MM}"
    )


@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_build_head_node_prong_angles_count(style: str, cut: str):
    """prong_angles_deg list must have exactly prong_count entries."""
    spec = head_library_entry(style, cut, _STONE_MM)
    node = build_head_node(
        node_id="test-n2",
        head_style=style,
        cut=cut,
        stone_mm=_STONE_MM,
        prong_count=spec["prong_count"],
        prong_wire_dia=spec["prong_wire_dia"],
        claw_length=spec["claw_length"],
        claw_tip_radius=spec["claw_tip_radius"],
        seat_angle_deg=spec["seat_angle_deg"],
        gallery_rail=spec["gallery_rail"],
        bezel_wall=spec["bezel_wall"],
        bezel_height=spec["bezel_height"],
        start_angle_deg=spec["start_angle_deg"],
    )
    assert len(node["prong_angles_deg"]) == spec["prong_count"], (
        f"{style}/{cut}: expected {spec['prong_count']} prong angles, "
        f"got {len(node['prong_angles_deg'])}"
    )
    assert len(node["contact_points_mm"]) == spec["prong_count"]


@pytest.mark.parametrize("style,cut", [
    (style, cut) for style in _HEAD_STYLES_5 for cut in _STONE_CUTS_5
])
def test_build_head_node_angles_in_range(style: str, cut: str):
    """All prong_angles_deg must be in [0, 360)."""
    spec = head_library_entry(style, cut, _STONE_MM)
    node = build_head_node(
        node_id="test-n3",
        head_style=style,
        cut=cut,
        stone_mm=_STONE_MM,
        prong_count=spec["prong_count"],
        prong_wire_dia=spec["prong_wire_dia"],
        claw_length=spec["claw_length"],
        claw_tip_radius=spec["claw_tip_radius"],
        seat_angle_deg=spec["seat_angle_deg"],
        gallery_rail=spec["gallery_rail"],
        bezel_wall=spec["bezel_wall"],
        bezel_height=spec["bezel_height"],
        start_angle_deg=spec["start_angle_deg"],
    )
    for ang in node["prong_angles_deg"]:
        assert 0.0 <= ang < 360.0, (
            f"{style}/{cut}: angle {ang} outside [0, 360)"
        )


# ---------------------------------------------------------------------------
# Specific prong-count checks for 4/6/8 prong styles
# ---------------------------------------------------------------------------

def test_four_prong_solitaire_prong_count():
    """four_prong_solitaire must default to 4 prongs."""
    spec = head_library_entry("four_prong_solitaire", "round_brilliant", 6.5)
    assert spec["prong_count"] == 4


def test_six_prong_solitaire_prong_count():
    """six_prong_solitaire must default to 6 prongs."""
    spec = head_library_entry("six_prong_solitaire", "round_brilliant", 6.5)
    assert spec["prong_count"] == 6


def test_double_claw_prong_count():
    """double_claw must default to 8 prongs (4 stations × 2 claws)."""
    spec = head_library_entry("double_claw", "round_brilliant", 6.5)
    assert spec["prong_count"] == 8


def test_full_bezel_zero_prongs():
    """full_bezel must have prong_count == 0 (no prongs)."""
    spec = head_library_entry("full_bezel", "round_brilliant", 6.5)
    assert spec["prong_count"] == 0


def test_tension_zero_prongs():
    """tension must have prong_count == 0."""
    spec = head_library_entry("tension", "round_brilliant", 6.5)
    assert spec["prong_count"] == 0


# ---------------------------------------------------------------------------
# gallery_rail flag checks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style", ["basket", "four_prong_solitaire", "six_prong_solitaire"])
def test_gallery_rail_styles(style: str):
    """basket / four_prong_solitaire / six_prong_solitaire must have gallery_rail=True."""
    spec = head_library_entry(style, "round_brilliant", 6.5)
    assert spec["gallery_rail"] is True, f"{style}: expected gallery_rail=True"


@pytest.mark.parametrize("style", ["full_bezel", "tension", "v_prong", "half_bezel", "halo", "double_claw"])
def test_no_gallery_rail_styles(style: str):
    """Non-gallery styles must have gallery_rail=False."""
    spec = head_library_entry(style, "round_brilliant", 6.5)
    assert spec["gallery_rail"] is False, f"{style}: expected gallery_rail=False"


# ---------------------------------------------------------------------------
# Prong angular placement (prong_angles_for_cut)
# ---------------------------------------------------------------------------

def test_round_even_spacing_4():
    """Round brilliant with 4 prongs must be at 0, 90, 180, 270."""
    angles = prong_angles_for_cut("round_brilliant", 4)
    assert len(angles) == 4
    expected = [0.0, 90.0, 180.0, 270.0]
    for a, e in zip(sorted(angles), expected):
        assert a == pytest.approx(e, abs=1e-6)


def test_round_even_spacing_6():
    """Round brilliant with 6 prongs must be at 60-degree intervals."""
    angles = prong_angles_for_cut("round_brilliant", 6)
    assert len(angles) == 6
    diffs = [
        (angles[(i + 1) % 6] - angles[i]) % 360.0
        for i in range(6)
    ]
    for d in diffs:
        assert d == pytest.approx(60.0, abs=1e-4)


def test_princess_4_prong_corner_biased():
    """princess with 4 prongs must use corner-biased placement (45° offsets)."""
    angles = prong_angles_for_cut("princess", 4)
    assert len(angles) == 4
    # First corner at 45°
    assert 45.0 in [pytest.approx(a, abs=1e-4) for a in angles]


def test_marquise_2_prong_tip_placement():
    """marquise with 2 prongs must place at 0° (tip) and 180° (opposing tip)."""
    angles = prong_angles_for_cut("marquise", 2)
    assert len(angles) == 2
    assert 0.0 in [pytest.approx(a, abs=1e-4) for a in angles]
    assert 180.0 in [pytest.approx(a, abs=1e-4) for a in angles]


def test_trillion_3_prong_120_degree():
    """trillion with 3 prongs must place at 120-degree intervals."""
    angles = prong_angles_for_cut("trillion", 3)
    assert len(angles) == 3
    diffs = sorted([(angles[(i + 1) % 3] - angles[i]) % 360.0 for i in range(3)])
    for d in diffs:
        assert d == pytest.approx(120.0, abs=1e-3)


def test_zero_prong_count_returns_empty():
    """prong_angles_for_cut with 0 prongs returns empty list."""
    angles = prong_angles_for_cut("round_brilliant", 0)
    assert angles == []


def test_start_angle_offset():
    """start_angle_deg offsets all positions consistently."""
    angles_0 = prong_angles_for_cut("round_brilliant", 4, 0.0)
    angles_45 = prong_angles_for_cut("round_brilliant", 4, 45.0)
    for a0, a45 in zip(angles_0, angles_45):
        assert (a45 - a0) % 360.0 == pytest.approx(45.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Stone girdle radius / contact points
# ---------------------------------------------------------------------------

def test_girdle_radius_round():
    """Round brilliant girdle radius must equal stone_mm / 2."""
    r = stone_girdle_radius("round_brilliant", 6.5)
    assert r == pytest.approx(3.25)


def test_girdle_radius_fancy_corner_larger():
    """Fancy-corner cut girdle radius must be larger than simple radius (diagonal)."""
    r_round = stone_girdle_radius("round_brilliant", 6.5)
    r_princess = stone_girdle_radius("princess", 6.5)
    # princess half-diagonal = (6.5/2) * sqrt(2) > 6.5/2
    assert r_princess > r_round


def test_girdle_contact_round_on_circle():
    """Contact point for round brilliant must lie exactly on the girdle circle."""
    stone_mm = 8.0
    for angle in [0.0, 45.0, 90.0, 135.0, 180.0, 270.0]:
        x, y = girdle_contact_point("round_brilliant", stone_mm, angle)
        dist = math.sqrt(x ** 2 + y ** 2)
        assert dist == pytest.approx(stone_mm / 2.0, rel=1e-6), (
            f"angle={angle}: dist {dist} != {stone_mm / 2.0}"
        )


def test_girdle_contact_pointed_ellipse():
    """Marquise contact point at tip (angle=0) must lie on the ellipse outline.

    The marquise girdle is modelled as an ellipse with a=stone_mm/2 (length semi-axis)
    and b=stone_mm*0.55/2 (width semi-axis).  At angle=0 (north), the math angle
    is π/2 so cos=0, sin=1; the ellipse formula gives r = (a*b)/sqrt(b²×0 + a²×1) = b.
    Hence y = b = stone_mm*0.55/2 and x ≈ 0.
    """
    stone_mm = 10.0
    a = stone_mm / 2.0
    b = stone_mm * 0.55 / 2.0
    x, y = girdle_contact_point("marquise", stone_mm, 0.0)
    assert abs(x) < 1e-4
    assert y == pytest.approx(b, rel=1e-3)


def test_girdle_contact_fancy_on_square_boundary():
    """Princess contact point must lie on the bounding square boundary."""
    stone_mm = 6.5
    half = stone_mm / 2.0
    for angle in [45.0, 135.0, 225.0, 315.0]:
        x, y = girdle_contact_point("princess", stone_mm, angle)
        # At least one coordinate should be at the half-size boundary
        on_boundary = (
            abs(abs(x) - half) < 1e-6 or abs(abs(y) - half) < 1e-6
        )
        assert on_boundary, (
            f"angle={angle}: ({x}, {y}) not on square boundary (half={half})"
        )


# ---------------------------------------------------------------------------
# Ring size conversions
# ---------------------------------------------------------------------------

def test_us_size_6_inner_dia():
    """US size 6 ring must have inner diameter ~ 16.51 mm."""
    id_mm = _ring_size_to_id_mm("us", 6)
    assert id_mm == pytest.approx(16.51, abs=0.02)


def test_us_size_0_minimum():
    """US size 0 must return the formula intercept value."""
    id_mm = _ring_size_to_id_mm("us", 0)
    assert id_mm == pytest.approx(11.63, rel=1e-4)


def test_uk_size_N():
    """UK size N must return circumference / π (known value ~54.4 / π)."""
    id_mm = _ring_size_to_id_mm("uk", "N")
    expected = 54.4 / math.pi
    assert id_mm == pytest.approx(expected, rel=1e-4)


def test_eu_size_50():
    """EU size 50 (circumference 50 mm) must return 50 / π."""
    id_mm = _ring_size_to_id_mm("eu", 50)
    assert id_mm == pytest.approx(50.0 / math.pi, rel=1e-4)


def test_jp_size_10():
    """JP size 10 must return known circumference (46.2 mm) / π."""
    id_mm = _ring_size_to_id_mm("jp", 10)
    assert id_mm == pytest.approx(46.2 / math.pi, rel=1e-4)


# ---------------------------------------------------------------------------
# build_ring_builder_node — weight estimate & min-metal check
# ---------------------------------------------------------------------------

def test_ring_builder_node_keys():
    """build_ring_builder_node must return all required output keys."""
    node = build_ring_builder_node(
        node_id="rb-1",
        head_node_id="head-1",
        shank_profile="comfort_fit",
        band_width=3.0,
        band_thickness=1.5,
        ring_size=6.0,
        size_system="us",
        metal="18k_yellow",
        seat_height_mm=1.0,
    )
    for key in ("_inner_dia_mm", "_weight_g", "_warnings", "op"):
        assert key in node, f"missing key: {key}"
    assert node["op"] == "jewelry_ring_builder"


def test_ring_builder_node_weight_positive():
    """Estimated weight must be > 0 for any valid inputs."""
    node = build_ring_builder_node(
        node_id="rb-2",
        head_node_id="head-2",
        shank_profile="d_shape",
        band_width=2.5,
        band_thickness=1.2,
        ring_size=7.0,
        size_system="us",
        metal="platinum",
        seat_height_mm=0.0,
    )
    assert node["_weight_g"] > 0.0


def test_ring_builder_thin_band_triggers_warning():
    """band_thickness below _MIN_METAL_WALL_MM should generate a warning."""
    node = build_ring_builder_node(
        node_id="rb-3",
        head_node_id="head-3",
        shank_profile="flat",
        band_width=2.0,
        band_thickness=0.1,   # below 0.25 mm minimum
        ring_size=5.0,
        size_system="us",
        metal="14k_yellow",
        seat_height_mm=0.0,
    )
    assert len(node["_warnings"]) > 0, "expected a warning for thin band"


def test_ring_builder_inner_dia_matches_us_formula():
    """inner_dia_mm from ring_builder must match _ring_size_to_id_mm directly."""
    size = 8.0
    node = build_ring_builder_node(
        node_id="rb-4",
        head_node_id="head-4",
        shank_profile="half_round",
        band_width=3.0,
        band_thickness=1.5,
        ring_size=size,
        size_system="us",
        metal="18k_white",
        seat_height_mm=0.5,
    )
    expected = _ring_size_to_id_mm("us", size)
    assert node["_inner_dia_mm"] == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Gallery module — basket_geometry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prong_count,stone_mm", [
    (4, 5.0), (6, 6.5), (4, 8.0), (6, 10.0), (8, 4.0),
])
def test_basket_geometry_output_keys(prong_count: int, stone_mm: float):
    """basket_geometry must return all required keys for various prong/stone combos."""
    geom = basket_geometry(
        prong_count=prong_count,
        stone_diameter_mm=stone_mm,
        wire_diameter_mm=1.0,
        basket_height_mm=4.0,
    )
    required = {
        "op", "prong_count", "stone_diameter_mm", "wire_diameter_mm",
        "basket_height_mm", "head_outer_radius_mm", "base_outer_radius_mm",
        "rail_count", "rail_positions_mm", "total_rail_length_mm",
        "prong_positions_deg", "prong_length_mm", "cutout_style",
        "scallop_count_per_bay", "diagonal_struts", "splay_angle_deg",
    }
    assert required <= set(geom.keys()), (
        f"{prong_count}/{stone_mm}: missing {required - set(geom.keys())}"
    )
    assert geom["op"] == "jewelry_gallery_basket"


@pytest.mark.parametrize("prong_count,stone_mm", [
    (4, 5.0), (6, 6.5), (4, 8.0), (6, 10.0), (8, 4.0),
])
def test_basket_geometry_head_outer_radius(prong_count: int, stone_mm: float):
    """head_outer_radius_mm must be stone_mm/2 + wire_diameter_mm."""
    wire = 1.0
    geom = basket_geometry(
        prong_count=prong_count,
        stone_diameter_mm=stone_mm,
        wire_diameter_mm=wire,
        basket_height_mm=4.0,
    )
    expected = stone_mm / 2.0 + wire
    assert geom["head_outer_radius_mm"] == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize("prong_count,stone_mm", [
    (4, 5.0), (6, 6.5), (4, 8.0), (6, 10.0), (8, 4.0),
])
def test_basket_prong_positions_count(prong_count: int, stone_mm: float):
    """prong_positions_deg must contain exactly prong_count entries."""
    geom = basket_geometry(
        prong_count=prong_count,
        stone_diameter_mm=stone_mm,
        wire_diameter_mm=1.0,
        basket_height_mm=4.0,
    )
    assert len(geom["prong_positions_deg"]) == prong_count


@pytest.mark.parametrize("prong_count,stone_mm", [
    (4, 5.0), (6, 6.5), (4, 8.0), (6, 10.0), (8, 4.0),
])
def test_basket_prong_positions_evenly_spaced(prong_count: int, stone_mm: float):
    """Prong positions must be evenly spaced (360 / prong_count intervals)."""
    geom = basket_geometry(
        prong_count=prong_count,
        stone_diameter_mm=stone_mm,
        wire_diameter_mm=1.0,
        basket_height_mm=4.0,
    )
    step = 360.0 / prong_count
    positions = geom["prong_positions_deg"]
    for i in range(prong_count):
        assert positions[i] == pytest.approx(i * step, abs=1e-3)


# ---------------------------------------------------------------------------
# Gallery module — under_bezel_gallery_geometry
# ---------------------------------------------------------------------------

def test_under_bezel_gallery_circumference():
    """under_bezel circumference must equal 2π × outer_radius."""
    geom = under_bezel_gallery_geometry(
        stone_diameter_mm=7.0,
        wall_thickness_mm=0.8,
        gallery_height_mm=2.5,
    )
    outer_r = geom["outer_radius_mm"]
    expected_circ = 2 * math.pi * outer_r
    assert geom["circumference_mm"] == pytest.approx(expected_circ, rel=1e-5)


def test_under_bezel_gallery_inner_outer_radii():
    """inner_radius + wall_thickness == outer_radius."""
    stone_mm = 8.0
    wall = 1.0
    geom = under_bezel_gallery_geometry(
        stone_diameter_mm=stone_mm,
        wall_thickness_mm=wall,
        gallery_height_mm=3.0,
    )
    assert geom["inner_radius_mm"] == pytest.approx(stone_mm / 2.0, rel=1e-5)
    assert geom["outer_radius_mm"] == pytest.approx(stone_mm / 2.0 + wall, rel=1e-5)


@pytest.mark.parametrize("border", sorted(_VALID_BORDER_STYLES))
def test_under_bezel_all_border_styles(border: str):
    """All border styles must produce a valid spec without error."""
    geom = under_bezel_gallery_geometry(
        stone_diameter_mm=6.5,
        wall_thickness_mm=0.7,
        gallery_height_mm=2.0,
        border_style=border,
    )
    assert geom["border_style"] == border
    assert geom["op"] == "jewelry_gallery_under_bezel"


# ---------------------------------------------------------------------------
# Gallery module — cathedral_shoulder_geometry
# ---------------------------------------------------------------------------

def test_cathedral_shoulder_output_keys():
    """cathedral_shoulder_geometry must return all required keys."""
    geom = cathedral_shoulder_geometry(
        prong_count=4,
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        basket_height_mm=5.0,
        shank_width_mm=3.0,
    )
    for key in ("op", "arch_span_mm", "arch_rise_mm", "arch_length_mm", "shoulder_pair_count"):
        assert key in geom
    assert geom["op"] == "jewelry_gallery_cathedral"
    assert geom["shoulder_pair_count"] == 2


def test_cathedral_shoulder_arch_rise_default():
    """Default arch_rise_mm must be 60% of basket_height_mm."""
    geom = cathedral_shoulder_geometry(
        prong_count=4,
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        basket_height_mm=6.0,
        shank_width_mm=3.0,
    )
    assert geom["arch_rise_mm"] == pytest.approx(6.0 * 0.6, rel=1e-4)


def test_cathedral_shoulder_arch_length_positive():
    """arch_length_mm must be > 0 for any valid input."""
    geom = cathedral_shoulder_geometry(
        prong_count=6,
        stone_diameter_mm=8.0,
        wire_diameter_mm=1.2,
        basket_height_mm=4.0,
        shank_width_mm=4.0,
    )
    assert geom["arch_length_mm"] > 0.0


# ---------------------------------------------------------------------------
# Gallery module — trellis_shoulder_geometry
# ---------------------------------------------------------------------------

def test_trellis_shoulder_output_keys():
    """trellis_shoulder_geometry must return all required keys."""
    geom = trellis_shoulder_geometry(
        prong_count=4,
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        basket_height_mm=4.0,
    )
    for key in ("op", "diagonal_length_mm", "total_trellis_wire_mm", "bay_count", "cross_count"):
        assert key in geom
    assert geom["op"] == "jewelry_gallery_trellis"


def test_trellis_bay_count_equals_prong_count():
    """bay_count must equal prong_count for a full trellis."""
    geom = trellis_shoulder_geometry(
        prong_count=6,
        stone_diameter_mm=7.0,
        wire_diameter_mm=1.0,
        basket_height_mm=5.0,
    )
    assert geom["bay_count"] == 6


def test_trellis_total_wire_scales_with_cross_count():
    """total_trellis_wire_mm must scale linearly with cross_count."""
    geom_1 = trellis_shoulder_geometry(
        prong_count=4, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0, cross_count=1,
    )
    geom_2 = trellis_shoulder_geometry(
        prong_count=4, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0, cross_count=2,
    )
    assert geom_2["total_trellis_wire_mm"] == pytest.approx(
        geom_1["total_trellis_wire_mm"] * 2, rel=1e-4
    )


# ---------------------------------------------------------------------------
# Gallery module — peg_head_adapter_geometry
# ---------------------------------------------------------------------------

def test_peg_adapter_output_keys():
    """peg_head_adapter_geometry must return all required keys."""
    geom = peg_head_adapter_geometry(
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        adapter_height_mm=2.0,
        shank_bore_diameter_mm=5.0,
    )
    for key in ("op", "peg_outer_diameter_mm", "peg_inner_diameter_mm", "adapter_height_mm"):
        assert key in geom
    assert geom["op"] == "jewelry_gallery_peg_adapter"


def test_peg_adapter_outer_equals_bore():
    """peg_outer_diameter_mm must equal shank_bore_diameter_mm."""
    bore = 5.5
    geom = peg_head_adapter_geometry(
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        adapter_height_mm=2.0,
        shank_bore_diameter_mm=bore,
    )
    assert geom["peg_outer_diameter_mm"] == pytest.approx(bore, rel=1e-5)


def test_peg_adapter_inner_less_than_outer():
    """peg_inner_diameter_mm must be < peg_outer_diameter_mm."""
    geom = peg_head_adapter_geometry(
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        adapter_height_mm=2.0,
        shank_bore_diameter_mm=5.0,
    )
    assert geom["peg_inner_diameter_mm"] < geom["peg_outer_diameter_mm"]


def test_peg_adapter_inner_minimum_0_5():
    """peg_inner_diameter_mm must be >= 0.5 mm even with thick walls."""
    geom = peg_head_adapter_geometry(
        stone_diameter_mm=6.5,
        wire_diameter_mm=10.0,   # very thick wall; inner should clamp to 0.5
        adapter_height_mm=2.0,
        shank_bore_diameter_mm=3.0,
    )
    assert geom["peg_inner_diameter_mm"] >= 0.5


# ---------------------------------------------------------------------------
# Gallery estimation helpers
# ---------------------------------------------------------------------------

def test_basket_metal_volume_positive():
    """basket_metal_volume_mm3 must be > 0 for a valid basket."""
    geom = basket_geometry(
        prong_count=4, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0,
    )
    vol = basket_metal_volume_mm3(geom)
    assert vol > 0.0


def test_basket_surface_area_positive():
    """basket_surface_area_mm2 must be > 0 for a valid basket."""
    geom = basket_geometry(
        prong_count=4, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0,
    )
    sa = basket_surface_area_mm2(geom)
    assert sa > 0.0


def test_metal_weight_grams_basic():
    """metal_weight_grams must be volume_mm3 / 1000 × density."""
    wt = metal_weight_grams(1000.0, 15.58)   # 1 cm³ of 18k yellow
    assert wt == pytest.approx(15.58, rel=1e-5)


def test_metal_weight_zero_volume():
    """Zero volume must yield zero weight."""
    wt = metal_weight_grams(0.0, 15.58)
    assert wt == pytest.approx(0.0, abs=1e-10)


def test_min_wire_check_adequate():
    """min_wire_diameter_check returns None when wire meets the minimum."""
    result = min_wire_diameter_check(wire_diameter_mm=1.0, stone_carat=0.5)
    assert result is None


def test_min_wire_check_too_thin():
    """min_wire_diameter_check returns a warning string when wire is too thin."""
    result = min_wire_diameter_check(wire_diameter_mm=0.5, stone_carat=0.5)
    assert result is not None
    assert isinstance(result, str)
    assert "0.9" in result   # recommended minimum for 0.5 ct


def test_basket_volume_more_prongs_more_metal():
    """A basket with more prongs must use more metal than one with fewer."""
    geom_4 = basket_geometry(
        prong_count=4, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0,
    )
    geom_6 = basket_geometry(
        prong_count=6, stone_diameter_mm=6.5,
        wire_diameter_mm=1.0, basket_height_mm=4.0,
    )
    vol_4 = basket_metal_volume_mm3(geom_4)
    vol_6 = basket_metal_volume_mm3(geom_6)
    assert vol_6 > vol_4


# ---------------------------------------------------------------------------
# Boundary: minimum and maximum stone sizes
# ---------------------------------------------------------------------------

def test_head_library_minimum_stone_0_5mm():
    """stone_mm = 0.5 mm (micro-setting) must produce a valid spec."""
    spec = head_library_entry("four_prong_solitaire", "round_brilliant", 0.5)
    assert spec["prong_wire_dia"] >= 0.0
    assert spec["stone_mm"] == pytest.approx(0.5)


def test_head_library_large_stone_30mm():
    """stone_mm = 30 mm (large statement stone) must scale prongs proportionally."""
    spec = head_library_entry("basket", "oval", 30.0)
    assert spec["stone_mm"] == pytest.approx(30.0)
    assert spec["prong_wire_dia"] > 0.0
    # Wire diameter should be larger for a 30 mm stone than a 6.5 mm stone
    spec_small = head_library_entry("basket", "oval", 6.5)
    assert spec["prong_wire_dia"] > spec_small["prong_wire_dia"]


def test_head_library_all_styles_all_cuts_smoke():
    """Every (style, cut) combination in the full sets must not raise."""
    for style in sorted(HEAD_STYLES):
        for cut in sorted(STONE_CUTS):
            spec = head_library_entry(style, cut, 6.5)
            assert "head_style" in spec


# ---------------------------------------------------------------------------
# Malformed input: head_library_entry
# ---------------------------------------------------------------------------

def test_head_library_invalid_style():
    """Unknown head_style must raise ValueError."""
    with pytest.raises(ValueError, match="head_style"):
        head_library_entry("unicorn_setting", "round_brilliant", 6.5)


def test_head_library_invalid_cut():
    """Unknown stone cut must raise ValueError."""
    with pytest.raises(ValueError, match="cut"):
        head_library_entry("basket", "kryptonite_cut", 6.5)


def test_head_library_zero_stone_mm():
    """stone_mm = 0 must raise ValueError."""
    with pytest.raises(ValueError):
        head_library_entry("basket", "round_brilliant", 0.0)


def test_head_library_negative_stone_mm():
    """Negative stone_mm must raise ValueError."""
    with pytest.raises(ValueError):
        head_library_entry("basket", "round_brilliant", -1.0)


# ---------------------------------------------------------------------------
# Malformed input: ring size
# ---------------------------------------------------------------------------

def test_ring_size_us_out_of_range():
    """US ring size > 16 must raise ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        _ring_size_to_id_mm("us", 20.0)


def test_ring_size_us_negative():
    """Negative US ring size must raise ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        _ring_size_to_id_mm("us", -1.0)


def test_ring_size_uk_unknown():
    """Unknown UK size string must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown UK/AU"):
        _ring_size_to_id_mm("uk", "ZZ")


def test_ring_size_eu_out_of_range():
    """EU circumference outside 41–76 must raise ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        _ring_size_to_id_mm("eu", 100.0)


def test_ring_size_jp_out_of_range():
    """JP size > 30 must raise ValueError."""
    with pytest.raises(ValueError, match="out of range"):
        _ring_size_to_id_mm("jp", 99)


def test_ring_size_unknown_system():
    """Unknown ring-size system must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown ring-size system"):
        _ring_size_to_id_mm("zz", 6)


# ---------------------------------------------------------------------------
# Malformed input: basket_geometry
# ---------------------------------------------------------------------------

def test_basket_geometry_too_few_prongs():
    """prong_count < 3 must raise ValueError."""
    with pytest.raises(ValueError):
        basket_geometry(
            prong_count=2, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
        )


def test_basket_geometry_too_many_prongs():
    """prong_count > 12 must raise ValueError."""
    with pytest.raises(ValueError):
        basket_geometry(
            prong_count=13, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
        )


def test_basket_geometry_zero_stone_dia():
    """stone_diameter_mm = 0 must raise ValueError."""
    with pytest.raises(ValueError):
        basket_geometry(
            prong_count=4, stone_diameter_mm=0.0,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
        )


def test_basket_geometry_invalid_cutout_style():
    """Unknown cutout_style must raise ValueError."""
    with pytest.raises(ValueError, match="cutout_style"):
        basket_geometry(
            prong_count=4, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
            cutout_style="galaxy",
        )


def test_basket_geometry_taper_ratio_ge_1():
    """taper_ratio >= 1.0 must raise ValueError."""
    with pytest.raises(ValueError):
        basket_geometry(
            prong_count=4, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
            taper_ratio=1.0,
        )


def test_basket_geometry_too_many_rails():
    """rail_count > 6 must raise ValueError."""
    with pytest.raises(ValueError):
        basket_geometry(
            prong_count=4, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
            rail_count=7,
        )


def test_under_bezel_invalid_border_style():
    """Unknown border_style must raise ValueError."""
    with pytest.raises(ValueError, match="border_style"):
        under_bezel_gallery_geometry(
            stone_diameter_mm=6.5, wall_thickness_mm=0.8,
            gallery_height_mm=2.5, border_style="glitter",
        )


def test_cathedral_too_many_arch_ribs():
    """arch_rib_count > 2 must raise ValueError."""
    with pytest.raises(ValueError, match="arch_rib_count"):
        cathedral_shoulder_geometry(
            prong_count=4, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
            shank_width_mm=3.0, arch_rib_count=3,
        )


def test_trellis_too_many_cross_count():
    """cross_count > 4 must raise ValueError."""
    with pytest.raises(ValueError, match="cross_count"):
        trellis_shoulder_geometry(
            prong_count=4, stone_diameter_mm=6.5,
            wire_diameter_mm=1.0, basket_height_mm=4.0,
            cross_count=5,
        )


def test_metal_weight_negative_volume():
    """Negative volume must raise ValueError."""
    with pytest.raises(ValueError):
        metal_weight_grams(-1.0, 15.58)


def test_metal_weight_zero_density():
    """Zero density must raise ValueError."""
    with pytest.raises(ValueError):
        metal_weight_grams(100.0, 0.0)


def test_min_wire_check_zero_wire():
    """wire_diameter_mm = 0 must raise ValueError."""
    with pytest.raises(ValueError):
        min_wire_diameter_check(0.0, 1.0)


def test_min_wire_check_negative_carat():
    """Negative stone_carat must raise ValueError."""
    with pytest.raises(ValueError):
        min_wire_diameter_check(1.0, -0.1)


# ---------------------------------------------------------------------------
# Idempotency: same inputs → identical outputs
# ---------------------------------------------------------------------------

def test_head_library_entry_idempotent():
    """Calling head_library_entry twice with same args returns identical dicts."""
    spec_a = head_library_entry("four_prong_solitaire", "round_brilliant", 6.5)
    spec_b = head_library_entry("four_prong_solitaire", "round_brilliant", 6.5)
    assert spec_a == spec_b


def test_build_head_node_idempotent():
    """build_head_node with same args returns identical dicts (same node_id)."""
    kwargs = dict(
        node_id="idem-1",
        head_style="six_prong_solitaire",
        cut="oval",
        stone_mm=7.0,
        prong_count=6,
        prong_wire_dia=0.9,
        claw_length=2.0,
        claw_tip_radius=0.45,
        seat_angle_deg=15.0,
        gallery_rail=True,
        bezel_wall=0.35,
        bezel_height=2.8,
        start_angle_deg=0.0,
    )
    node_a = build_head_node(**kwargs)
    node_b = build_head_node(**kwargs)
    assert node_a == node_b


def test_basket_geometry_idempotent():
    """basket_geometry with same args returns identical dicts."""
    kwargs = dict(
        prong_count=4,
        stone_diameter_mm=6.5,
        wire_diameter_mm=1.0,
        basket_height_mm=4.0,
    )
    geom_a = basket_geometry(**kwargs)
    geom_b = basket_geometry(**kwargs)
    assert geom_a == geom_b


def test_prong_angles_idempotent():
    """prong_angles_for_cut returns same list on repeated calls."""
    angles_a = prong_angles_for_cut("princess", 4, 30.0)
    angles_b = prong_angles_for_cut("princess", 4, 30.0)
    assert angles_a == angles_b


def test_girdle_contact_idempotent():
    """girdle_contact_point returns same values on repeated calls."""
    for _ in range(3):
        x, y = girdle_contact_point("oval", 8.0, 45.0)
    x2, y2 = girdle_contact_point("oval", 8.0, 45.0)
    assert x == pytest.approx(x2) and y == pytest.approx(y2)
