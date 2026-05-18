"""
Citable reference-value tests for kerf-landscape.

Analytic oracles
----------------
* Rational Method: Q = C · i · A
  American Society of Civil Engineers / WEF MoEP 92, §3.2 (1992).
  For C = 0.6, i = 2 in/hr, A = 1 acre → Q = 1.2 cfs exactly.

* Contour at z = 0 on a flat plane: no segments (the whole surface is at the
  level; marching squares returns empty for a fully-above or fully-below cell).

* Flow accumulation: on a constant downhill slope, all cells route to the
  low edge.  The low-edge cells therefore accumulate all upstream cells.

All tests are hermetic — no external files, no skips, all must pass.
"""

from __future__ import annotations

import math
import pytest


# ===========================================================================
# 1.  Rational Method — Q = C · i · A
#     ASCE/WEF Manual of Engineering Practice No. 92 (1992) §3.2
#     For C=0.6, i=2 in/hr, A=1 acre → Q = 1.2 cfs (exact)
# ===========================================================================

def test_rational_method_analytic_value():
    """Q = C · i · A = 0.6 × 2 × 1 = 1.2 cfs   (ASCE MoEP 92, §3.2)."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=0.6, i_in_per_hr=2.0, A_acres=1.0)
    assert result["ok"]
    assert abs(result["Q_cfs"] - 1.2) / 1.2 < 0.01   # within 1 %


def test_rational_method_analytic_value_exact():
    """Q = C · i · A is exact to float precision (no discretisation)."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=0.6, i_in_per_hr=2.0, A_acres=1.0)
    assert result["ok"]
    assert result["Q_cfs"] == pytest.approx(1.2, rel=1e-12)


def test_rational_method_m3s_conversion():
    """Q_m3s = Q_cfs × 0.028316846."""
    from kerf_landscape.drainage import rational_method, _CFS_TO_M3S

    result = rational_method(C=0.6, i_in_per_hr=2.0, A_acres=1.0)
    assert result["ok"]
    assert result["Q_m3s"] == pytest.approx(1.2 * _CFS_TO_M3S, rel=1e-9)


def test_rational_method_zero_area():
    """Zero area → Q = 0."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=0.5, i_in_per_hr=3.0, A_acres=0.0)
    assert result["ok"]
    assert result["Q_cfs"] == pytest.approx(0.0, abs=1e-15)


def test_rational_method_zero_intensity():
    """Zero intensity → Q = 0."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=0.8, i_in_per_hr=0.0, A_acres=5.0)
    assert result["ok"]
    assert result["Q_cfs"] == pytest.approx(0.0, abs=1e-15)


def test_rational_method_rejects_bad_C():
    """C > 1 is physically invalid → ok = False."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=1.1, i_in_per_hr=2.0, A_acres=1.0)
    assert not result["ok"]


def test_rational_method_rejects_negative_C():
    """Negative C is invalid."""
    from kerf_landscape.drainage import rational_method

    result = rational_method(C=-0.1, i_in_per_hr=2.0, A_acres=1.0)
    assert not result["ok"]


def test_rational_method_linearity_in_area():
    """Q scales linearly with A (all else equal)."""
    from kerf_landscape.drainage import rational_method

    q1 = rational_method(C=0.4, i_in_per_hr=1.5, A_acres=2.0)["Q_cfs"]
    q2 = rational_method(C=0.4, i_in_per_hr=1.5, A_acres=4.0)["Q_cfs"]
    assert q2 == pytest.approx(2.0 * q1, rel=1e-12)


# ===========================================================================
# 2.  Contour extraction — flat plane
#     Oracle: contour at z = 0 on a surface where all elevations == 0
#     gives zero segments (all cells are fully at the level; marching squares
#     case 15 / case 0 returns []).
# ===========================================================================

def test_contour_flat_plane_at_level_empty():
    """Contour at z=0 on a flat dem=0 plane returns no segments."""
    from kerf_landscape.grading import contours_from_dem

    dem = [[0.0, 0.0, 0.0],
           [0.0, 0.0, 0.0],
           [0.0, 0.0, 0.0]]
    x = [0.0, 1.0, 2.0]
    y = [0.0, 1.0, 2.0]
    result = contours_from_dem(dem, x, y, levels=[0.0])
    assert result["ok"]
    assert result["contours"][0]["level"] == 0.0
    assert len(result["contours"][0]["segments"]) == 0


def test_contour_flat_plane_below_level_empty():
    """Contour at z=5 on a dem=0 plane: all corners below → no segments."""
    from kerf_landscape.grading import contours_from_dem

    dem = [[0.0, 0.0],
           [0.0, 0.0]]
    x = [0.0, 1.0]
    y = [0.0, 1.0]
    result = contours_from_dem(dem, x, y, levels=[5.0])
    assert result["ok"]
    assert len(result["contours"][0]["segments"]) == 0


def test_contour_simple_slope():
    """A linear slope from z=0 to z=2 must yield a contour at z=1."""
    from kerf_landscape.grading import contours_from_dem

    # dem[row][col], x increases with col, y increases with row
    dem = [[0.0, 2.0],
           [0.0, 2.0]]
    x = [0.0, 1.0]
    y = [0.0, 1.0]
    result = contours_from_dem(dem, x, y, levels=[1.0])
    assert result["ok"]
    segs = result["contours"][0]["segments"]
    assert len(segs) > 0, "should find at least one segment at z=1 on a slope"


def test_contour_invalid_dem_shape():
    """Mismatched dem shape and coordinate arrays → ok=False."""
    from kerf_landscape.grading import contours_from_dem

    dem = [[0.0, 1.0], [0.0, 1.0]]
    result = contours_from_dem(dem, [0.0, 1.0, 2.0], [0.0, 1.0], [0.5])
    assert not result["ok"]


def test_contour_multiple_levels():
    """Multiple levels can be extracted in one call."""
    from kerf_landscape.grading import contours_from_dem

    dem = [[0.0, 0.0, 0.0],
           [1.0, 1.0, 1.0],
           [2.0, 2.0, 2.0]]
    x = [0.0, 1.0, 2.0]
    y = [0.0, 1.0, 2.0]
    result = contours_from_dem(dem, x, y, levels=[0.5, 1.5])
    assert result["ok"]
    assert len(result["contours"]) == 2


# ===========================================================================
# 3.  Flow accumulation — constant slope routes to low edge
#     Oracle: on an NxN grid with a uniform southward slope (y increases
#     uphill), every cell routes south; the bottom row (row 0) accumulates
#     all cells above it in its column.
# ===========================================================================

def test_flow_accumulation_constant_slope_routes_to_low_edge():
    """
    On a 4×4 grid with a uniform northward slope (row 0 = low), all flow
    routes to row 0.  Each column in row 0 therefore has accumulation = 4
    (itself + 3 upstream cells).
    """
    from kerf_landscape.drainage import flow_accumulation_d8

    # Row 0 is lowest, row 3 is highest (z increases with row index)
    n = 4
    dem = [[float(r) for _ in range(n)] for r in range(n)]
    # dem[0] = [0, 0, 0, 0], dem[3] = [3, 3, 3, 3]

    result = flow_accumulation_d8(dem, cell_size=1.0)
    assert result["ok"]

    accum = result["accumulation"]
    # Every cell in row 0 should have accumulation == n (4) because it
    # receives flow from all cells in its column.
    for col in range(n):
        assert accum[0][col] == n, (
            f"col {col}: expected {n}, got {accum[0][col]}"
        )


def test_flow_accumulation_headwater_cells_count_one():
    """Cells at the high end of a slope have accumulation == 1 (no upstream)."""
    from kerf_landscape.drainage import flow_accumulation_d8

    n = 4
    dem = [[float(r) for _ in range(n)] for r in range(n)]
    result = flow_accumulation_d8(dem, cell_size=1.0)
    assert result["ok"]
    accum = result["accumulation"]
    # Row n-1 is the highest row; no cells drain into it from further up
    for col in range(n):
        assert accum[n - 1][col] == 1


def test_flow_accumulation_total_cells_conserved():
    """Sum of accumulation on outlet row == total cell count on uniform slope."""
    from kerf_landscape.drainage import flow_accumulation_d8

    n = 5
    dem = [[float(r) for _ in range(n)] for r in range(n)]
    result = flow_accumulation_d8(dem, cell_size=1.0)
    assert result["ok"]
    accum = result["accumulation"]
    # Bottom row accumulates everything
    outlet_sum = sum(accum[0][c] for c in range(n))
    assert outlet_sum == n * n


def test_flow_accumulation_rejects_bad_input():
    """Empty dem → ok=False."""
    from kerf_landscape.drainage import flow_accumulation_d8

    result = flow_accumulation_d8([], cell_size=1.0)
    assert not result["ok"]

    result = flow_accumulation_d8([[1.0]], cell_size=0.0)
    assert not result["ok"]


# ===========================================================================
# 4.  Cut/fill volumes
# ===========================================================================

def test_cut_fill_symmetric_cut_and_fill():
    """A design surface uniformly 1 m lower yields only cut, no fill."""
    from kerf_landscape.grading import cut_fill_volumes

    existing = [[5.0, 5.0], [5.0, 5.0]]
    design   = [[4.0, 4.0], [4.0, 4.0]]
    result = cut_fill_volumes(existing, design, cell_width=1.0, cell_height=1.0)
    assert result["ok"]
    assert result["fill_m3"] == pytest.approx(0.0, abs=1e-12)
    assert result["cut_m3"] == pytest.approx(4.0, rel=1e-9)
    assert result["net_m3"] == pytest.approx(-4.0, rel=1e-9)


def test_cut_fill_balanced():
    """Half cells raised, half lowered by equal amounts → net ≈ 0."""
    from kerf_landscape.grading import cut_fill_volumes

    existing = [[5.0, 5.0], [5.0, 5.0]]
    design   = [[6.0, 4.0], [6.0, 4.0]]
    result = cut_fill_volumes(existing, design, cell_width=1.0, cell_height=1.0)
    assert result["ok"]
    assert result["net_m3"] == pytest.approx(0.0, abs=1e-12)


def test_cut_fill_rejects_mismatched_shapes():
    from kerf_landscape.grading import cut_fill_volumes

    e = [[1.0, 2.0]]
    d = [[1.0, 2.0], [3.0, 4.0]]
    result = cut_fill_volumes(e, d, cell_width=1.0, cell_height=1.0)
    assert not result["ok"]


# ===========================================================================
# 5.  Grading — grade_surface
# ===========================================================================

def test_grade_surface_flat_zero_grade():
    """Zero grade → design DEM equals origin elevation everywhere."""
    from kerf_landscape.grading import grade_surface

    dem = [[5.0, 5.0, 5.0],
           [5.0, 5.0, 5.0]]
    x = [0.0, 1.0, 2.0]
    y = [0.0, 1.0]
    result = grade_surface(dem, x, y, target_grade=0.0,
                           origin_xy=(0.0, 0.0), direction=(1.0, 0.0))
    assert result["ok"]
    for row in result["dem_design"]:
        for z in row:
            assert z == pytest.approx(5.0, abs=1e-9)


def test_grade_surface_known_slope():
    """2 % grade over 10 m → 0.2 m drop."""
    from kerf_landscape.grading import grade_surface

    dem = [[10.0, 10.0]]
    x = [0.0, 10.0]
    y = [0.0]
    result = grade_surface(dem, x, y, target_grade=0.02,
                           origin_xy=(0.0, 0.0), direction=(1.0, 0.0))
    assert result["ok"]
    # At x=10: z = 10 - 0.02*10 = 9.8
    assert result["dem_design"][0][1] == pytest.approx(9.8, rel=1e-9)


# ===========================================================================
# 6.  Planting catalogue
# ===========================================================================

def test_plant_catalogue_nonempty():
    from kerf_landscape.planting import get_plant_catalogue

    cat = get_plant_catalogue()
    assert len(cat) >= 10


def test_plant_catalogue_has_required_keys():
    from kerf_landscape.planting import get_plant_catalogue

    required = {"name", "scientific_name", "type", "zone_min", "zone_max",
                "water_use", "mature_height_m", "spread_m", "spacing_m", "sun"}
    for p in get_plant_catalogue():
        assert required <= set(p.keys()), f"Missing keys in plant: {p['name']}"


def test_filter_by_zone_9_returns_subset():
    from kerf_landscape.planting import get_plant_catalogue, filter_by_zone

    cat = get_plant_catalogue()
    zone9 = filter_by_zone(cat, 9)
    assert 0 < len(zone9) <= len(cat)
    for p in zone9:
        assert p["zone_min"] <= 9 <= p["zone_max"]


def test_filter_by_zone_excludes_incompatible():
    """Zone 1 should exclude warm-zone-only species."""
    from kerf_landscape.planting import get_plant_catalogue, filter_by_zone

    cat = get_plant_catalogue()
    z1 = filter_by_zone(cat, 1)
    for p in z1:
        assert p["zone_min"] <= 1


def test_filter_by_water_use_very_low():
    from kerf_landscape.planting import get_plant_catalogue, filter_by_water_use

    cat = get_plant_catalogue()
    very_low = filter_by_water_use(cat, "very-low")
    assert len(very_low) > 0
    for p in very_low:
        assert p["water_use"] == "very-low"


def test_plant_spacing_grid_nonempty():
    from kerf_landscape.planting import get_plant_catalogue, plant_spacing_grid

    plants = get_plant_catalogue()
    lavender = next(p for p in plants if p["name"] == "Lavender")
    result = plant_spacing_grid(lavender, area_width=5.0, area_depth=3.0)
    assert result["ok"]
    assert result["count"] > 0
    assert len(result["positions"]) == result["count"]


def test_plant_spacing_grid_positions_in_bounds():
    from kerf_landscape.planting import plant_spacing_grid

    plant = {"name": "Test", "spacing_m": 0.5}
    result = plant_spacing_grid(plant, area_width=3.0, area_depth=2.0)
    assert result["ok"]
    for x, y in result["positions"]:
        assert 0 <= x <= 3.0
        assert 0 <= y <= 2.0


# ===========================================================================
# 7.  Paver patterns
# ===========================================================================

def test_paver_stack_bond_count():
    """Stack-bond on a 2 m × 2 m area with 0.2 m × 0.1 m pavers."""
    from kerf_landscape.hardscape import paver_pattern

    result = paver_pattern("stack-bond", area_width=2.0, area_depth=2.0,
                           unit_w=0.2, unit_h=0.1, joint=0.0)
    assert result["ok"]
    assert result["count"] > 0


def test_paver_running_bond_differs_from_stack():
    """Running bond produces a different layout than stack bond."""
    from kerf_landscape.hardscape import paver_pattern

    sb = paver_pattern("stack-bond", 3.0, 3.0, 0.2, 0.1, joint=0.003)
    rb = paver_pattern("running-bond", 3.0, 3.0, 0.2, 0.1, joint=0.003)
    assert sb["ok"] and rb["ok"]
    # positions should differ (different x offsets on odd rows)
    sb_positions = set((p["x"], p["y"]) for p in sb["positions"])
    rb_positions = set((p["x"], p["y"]) for p in rb["positions"])
    assert sb_positions != rb_positions


def test_paver_invalid_pattern():
    from kerf_landscape.hardscape import paver_pattern

    result = paver_pattern("random-chaos", 2.0, 2.0, 0.2, 0.1)
    assert not result["ok"]


def test_paver_material_estimate():
    from kerf_landscape.hardscape import paver_pattern, paver_material_estimate

    pat = paver_pattern("stack-bond", 4.0, 4.0, 0.2, 0.1)
    assert pat["ok"]
    est = paver_material_estimate(pat, paver_thickness_m=0.06, waste_pct=5.0)
    assert est["ok"]
    assert est["paver_count_with_waste"] >= est["paver_count"]
    assert est["paver_volume_m3"] > 0


# ===========================================================================
# 8.  Retaining wall — Rankine Ka
#     Rankine (1857): Ka = tan²(45 - φ/2)
#     For φ = 30°: Ka = tan²(30°) = 1/3
# ===========================================================================

def test_retaining_wall_ka_30_degrees():
    """Rankine Ka for φ=30° = tan²(30°) = 1/3."""
    from kerf_landscape.hardscape import retaining_wall_layout

    result = retaining_wall_layout(height=2.0, length=10.0, soil_phi_deg=30.0)
    assert result["ok"]
    expected_Ka = math.tan(math.radians(45 - 15)) ** 2
    assert result["Ka"] == pytest.approx(expected_Ka, rel=1e-6)
    assert result["Ka"] == pytest.approx(1.0 / 3.0, rel=1e-5)


def test_retaining_wall_active_pressure():
    """P = ½ Ka γ H²; verify against analytic value."""
    from kerf_landscape.hardscape import retaining_wall_layout
    import math

    H = 3.0
    gamma = 18000.0
    phi = 30.0
    Ka = math.tan(math.radians(45 - phi / 2)) ** 2
    expected_P = 0.5 * Ka * gamma * H ** 2

    result = retaining_wall_layout(height=H, length=1.0, soil_phi_deg=phi,
                                   soil_gamma=gamma, surcharge=0.0)
    assert result["ok"]
    assert result["P_active_N_per_m"] == pytest.approx(expected_P, rel=1e-6)


def test_retaining_wall_fos_reasonable():
    """FoS against overturning must be > 0 (basic sanity)."""
    from kerf_landscape.hardscape import retaining_wall_layout

    result = retaining_wall_layout(height=2.0, length=5.0)
    assert result["ok"]
    assert result["moments_about_toe"]["FoS_overturning"] > 0


def test_retaining_wall_rejects_bad_height():
    from kerf_landscape.hardscape import retaining_wall_layout

    result = retaining_wall_layout(height=-1.0, length=5.0)
    assert not result["ok"]


# ===========================================================================
# 9.  Plant water budget
# ===========================================================================

def test_plant_water_budget_positive():
    from kerf_landscape.planting import get_plant_catalogue, plant_water_budget, filter_by_water_use

    cat = get_plant_catalogue()
    low_water = filter_by_water_use(cat, "low")[:3]
    plants = [(p, 5) for p in low_water]
    result = plant_water_budget(plants, area_m2=100.0, eto_mm_per_year=1000.0)
    assert result["ok"]
    assert result["water_L_per_year"] > 0
    # Both values are independently rounded to 1 and 3 decimal places;
    # allow for rounding difference of up to 0.01 %.
    assert result["water_m3_per_year"] == pytest.approx(
        result["water_L_per_year"] / 1000.0, rel=1e-3
    )


def test_plant_water_budget_xeriscape_uses_less():
    """Very-low water plants use less than high-water plants (same area, same ETo)."""
    from kerf_landscape.planting import plant_water_budget

    very_low_plant = {
        "name": "Agave", "spread_m": 1.0, "water_use": "very-low",
    }
    high_water_plant = {
        "name": "Lawn Grass", "spread_m": 1.0, "water_use": "high",
    }
    low_result = plant_water_budget([(very_low_plant, 10)], 100.0, 1000.0)
    high_result = plant_water_budget([(high_water_plant, 10)], 100.0, 1000.0)

    assert low_result["ok"] and high_result["ok"]
    assert low_result["water_L_per_year"] < high_result["water_L_per_year"]
