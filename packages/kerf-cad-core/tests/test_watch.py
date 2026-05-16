"""
Tests for kerf_cad_core.jewelry.watch

Hermetic pure-Python tests (no OCCT, no network, no DB).

Coverage:
  - compute_watch_params: default round case
  - case bore >= movement diameter + clearance (ETA2824, NH35)
  - lug-to-lug == case_dia + 2·lug_length (default and explicit)
  - dive bezel has exactly 120 teeth and 120 clicks
  - crystal seat aperture == crystal_aperture_mm returned in spec
  - NH35 movement ring fits (dial_aperture >= movement_diameter)
  - end-link width == strap_width_mm
  - weight == density * volume  (round-trip)
  - WR gasket groove present when water_resistance_m > 30
  - WR gasket groove absent when water_resistance_m == 0
  - cushion and tonneau case shapes produce valid specs
  - smooth / fluted bezels have no teeth
  - snap and exhibition casebacks produce valid specs
  - caliber catalog: ETA2824 and SW200 both Ø 25.6 mm
  - caliber catalog: Miyota9015 and NH35 both Ø 28.5 mm
  - invalid case shape raises ValueError
  - invalid bezel style raises ValueError
  - invalid caseback style raises ValueError
  - invalid metal key raises ValueError
  - unknown caliber raises ValueError
  - lug_to_lug_mm < case_dia + 2·lug raises ValueError
  - case bore too small for movement raises ValueError
  - spring_bar_bore >= lug_width raises ValueError
  - crown_tube_od >= crown_dia raises ValueError
  - negative water_resistance raises ValueError
  - platinum_950 density applied correctly
  - titanium case weight is lower than 18k equivalent
  - explicit movement_diameter_mm path (no caliber)
  - caseback_thread_pitch absent for snap back
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.watch import (
    CALIBER_CATALOG,
    DIVE_BEZEL_TEETH,
    compute_watch_params,
    build_watch_node,
)
from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3

_PI = math.pi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def default_params(**overrides):
    """Return compute_watch_params() with optional keyword overrides."""
    return compute_watch_params(**overrides)


# ---------------------------------------------------------------------------
# 1. Default round case returns well-formed dict
# ---------------------------------------------------------------------------

def test_default_round_case_returns_dict():
    p = default_params()
    assert p["op"] == "watch"
    assert p["case_shape"] == "round"
    assert isinstance(p["case_diameter_mm"], float)
    assert p["weight_g"] > 0


# ---------------------------------------------------------------------------
# 2. Case bore >= movement diameter + clearance (ETA2824)
# ---------------------------------------------------------------------------

def test_case_bore_ge_movement_diam_eta2824():
    p = default_params(caliber="ETA2824", case_diameter_mm=40.0, bezel_width_mm=2.5)
    movement_diam = CALIBER_CATALOG["ETA2824"]["movement_diameter_mm"]  # 25.6
    clearance = 0.3
    assert p["case_bore_mm"] >= movement_diam + clearance


# ---------------------------------------------------------------------------
# 3. Case bore >= movement diameter + clearance (NH35)
# ---------------------------------------------------------------------------

def test_case_bore_ge_movement_diam_nh35():
    p = default_params(caliber="NH35", case_diameter_mm=40.0, bezel_width_mm=2.5)
    movement_diam = CALIBER_CATALOG["NH35"]["movement_diameter_mm"]  # 28.5
    clearance = 0.3
    assert p["case_bore_mm"] >= movement_diam + clearance


# ---------------------------------------------------------------------------
# 4. lug_to_lug_mm == case_dia + 2·lug_length (default computation)
# ---------------------------------------------------------------------------

def test_lug_to_lug_default():
    p = default_params(case_diameter_mm=40.0, lug_length_mm=10.0)
    assert abs(p["lug_to_lug_mm"] - (40.0 + 2.0 * 10.0)) < 1e-6


# ---------------------------------------------------------------------------
# 5. lug_to_lug_mm == case_dia + 2·lug_length (explicit equal value)
# ---------------------------------------------------------------------------

def test_lug_to_lug_explicit_equal():
    p = default_params(case_diameter_mm=38.0, lug_length_mm=9.0, lug_to_lug_mm=56.0)
    assert abs(p["lug_to_lug_mm"] - 56.0) < 1e-6


# ---------------------------------------------------------------------------
# 6. Dive bezel has exactly 120 teeth
# ---------------------------------------------------------------------------

def test_dive_bezel_120_teeth():
    p = default_params(bezel_style="dive")
    assert p["bezel_teeth"] == 120


# ---------------------------------------------------------------------------
# 7. Dive bezel has exactly 120 clicks per rotation
# ---------------------------------------------------------------------------

def test_dive_bezel_120_clicks():
    p = default_params(bezel_style="dive")
    assert p["bezel_clicks_per_rotation"] == 120


# ---------------------------------------------------------------------------
# 8. Crystal seat aperture == crystal_aperture in spec
# ---------------------------------------------------------------------------

def test_crystal_seat_aperture_equals_crystal_aperture():
    p = default_params()
    assert abs(p["crystal_seat_aperture_mm"] - p["crystal_aperture_mm"]) < 1e-9


# ---------------------------------------------------------------------------
# 9. NH35 movement ring fits: dial_aperture >= movement_diameter
# ---------------------------------------------------------------------------

def test_nh35_movement_ring_fits():
    p = default_params(caliber="NH35", case_diameter_mm=42.0)
    movement_diam = CALIBER_CATALOG["NH35"]["movement_diameter_mm"]  # 28.5
    assert p["dial_aperture_mm"] >= movement_diam


# ---------------------------------------------------------------------------
# 10. End-link width == strap_width_mm
# ---------------------------------------------------------------------------

def test_end_link_width_equals_strap_width():
    p = default_params(strap_width_mm=20.0)
    assert abs(p["end_link_width_mm"] - 20.0) < 1e-9


# ---------------------------------------------------------------------------
# 11. Weight == density * volume (round-trip)
# ---------------------------------------------------------------------------

def test_weight_equals_density_times_volume():
    metal = "18k_yellow"
    p = default_params(metal=metal)
    density = METAL_DENSITY_G_CM3[metal]
    volume_cm3 = p["total_volume_mm3"] / 1000.0
    expected_g = density * volume_cm3
    assert abs(p["weight_g"] - expected_g) < 0.001


# ---------------------------------------------------------------------------
# 12. WR gasket groove present when water_resistance_m > 30
# ---------------------------------------------------------------------------

def test_wr_gasket_groove_present_when_wr_over_30():
    p = default_params(water_resistance_m=50.0)
    assert p["gasket_groove_present"] is True


# ---------------------------------------------------------------------------
# 13. WR gasket groove absent when water_resistance_m == 0 and no gasket args
# ---------------------------------------------------------------------------

def test_wr_gasket_groove_absent_when_wr_zero():
    p = default_params(water_resistance_m=0.0)
    assert p["gasket_groove_present"] is False


# ---------------------------------------------------------------------------
# 14. Cushion case shape produces valid spec
# ---------------------------------------------------------------------------

def test_cushion_case_shape():
    p = default_params(case_shape="cushion", case_diameter_mm=38.0)
    assert p["case_shape"] == "cushion"
    assert p["cushion_radius_mm"] is not None
    assert p["total_volume_mm3"] > 0


# ---------------------------------------------------------------------------
# 15. Tonneau case shape produces valid spec
# ---------------------------------------------------------------------------

def test_tonneau_case_shape():
    p = default_params(case_shape="tonneau", case_diameter_mm=36.0)
    assert p["case_shape"] == "tonneau"
    assert p["total_volume_mm3"] > 0


# ---------------------------------------------------------------------------
# 16. Smooth bezel has no teeth
# ---------------------------------------------------------------------------

def test_smooth_bezel_no_teeth():
    p = default_params(bezel_style="smooth")
    assert p["bezel_teeth"] is None
    assert p["bezel_clicks_per_rotation"] is None


# ---------------------------------------------------------------------------
# 17. Fluted bezel has no teeth (counts only for dive)
# ---------------------------------------------------------------------------

def test_fluted_bezel_no_teeth():
    p = default_params(bezel_style="fluted")
    assert p["bezel_teeth"] is None


# ---------------------------------------------------------------------------
# 18. Snap caseback produces valid spec
# ---------------------------------------------------------------------------

def test_snap_caseback():
    p = default_params(caseback_style="snap")
    assert p["caseback_style"] == "snap"


# ---------------------------------------------------------------------------
# 19. Exhibition caseback produces valid spec
# ---------------------------------------------------------------------------

def test_exhibition_caseback():
    p = default_params(caseback_style="exhibition")
    assert p["caseback_style"] == "exhibition"


# ---------------------------------------------------------------------------
# 20. ETA2824 caliber has movement_diameter_mm == 25.6
# ---------------------------------------------------------------------------

def test_caliber_eta2824_movement_diam():
    p = default_params(caliber="ETA2824", case_diameter_mm=40.0)
    assert abs(p["movement_diameter_mm"] - 25.6) < 1e-9


# ---------------------------------------------------------------------------
# 21. SW200 caliber has same movement_diameter as ETA2824 (25.6 mm)
# ---------------------------------------------------------------------------

def test_caliber_sw200_matches_eta2824():
    eta = CALIBER_CATALOG["ETA2824"]["movement_diameter_mm"]
    sw = CALIBER_CATALOG["SW200"]["movement_diameter_mm"]
    assert abs(eta - sw) < 1e-9


# ---------------------------------------------------------------------------
# 22. Miyota9015 caliber has movement_diameter_mm == 28.5
# ---------------------------------------------------------------------------

def test_caliber_miyota9015_movement_diam():
    p = default_params(caliber="Miyota9015", case_diameter_mm=42.0)
    assert abs(p["movement_diameter_mm"] - 28.5) < 1e-9


# ---------------------------------------------------------------------------
# 23. NH35 caliber has movement_diameter_mm == 28.5
# ---------------------------------------------------------------------------

def test_caliber_nh35_movement_diam():
    assert abs(CALIBER_CATALOG["NH35"]["movement_diameter_mm"] - 28.5) < 1e-9


# ---------------------------------------------------------------------------
# 24. Invalid case shape raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_case_shape_raises():
    with pytest.raises(ValueError, match="case_shape"):
        compute_watch_params(case_shape="hexagon")


# ---------------------------------------------------------------------------
# 25. Invalid bezel style raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_bezel_style_raises():
    with pytest.raises(ValueError, match="bezel_style"):
        compute_watch_params(bezel_style="ceramic")


# ---------------------------------------------------------------------------
# 26. Invalid caseback style raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_caseback_raises():
    with pytest.raises(ValueError, match="caseback_style"):
        compute_watch_params(caseback_style="glued")


# ---------------------------------------------------------------------------
# 27. Invalid metal key raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_metal_raises():
    with pytest.raises(ValueError, match="metal"):
        compute_watch_params(metal="unobtanium")


# ---------------------------------------------------------------------------
# 28. Unknown caliber raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_caliber_raises():
    with pytest.raises(ValueError, match="caliber"):
        compute_watch_params(caliber="Valjoux7750", case_diameter_mm=40.0)


# ---------------------------------------------------------------------------
# 29. lug_to_lug_mm < case_dia + 2·lug raises ValueError
# ---------------------------------------------------------------------------

def test_lug_to_lug_too_small_raises():
    with pytest.raises(ValueError, match="lug_to_lug_mm"):
        compute_watch_params(
            case_diameter_mm=40.0,
            lug_length_mm=10.0,
            lug_to_lug_mm=50.0,  # needs >= 60
        )


# ---------------------------------------------------------------------------
# 30. Case bore too small for movement raises ValueError
# ---------------------------------------------------------------------------

def test_case_bore_too_small_raises():
    # bezel_width=14 → bore = 40 - 28 = 12 mm, movement NH35 = 28.5 + 0.3 = 28.8
    with pytest.raises(ValueError, match="bore"):
        compute_watch_params(
            caliber="NH35",
            case_diameter_mm=40.0,
            bezel_width_mm=14.0,
        )


# ---------------------------------------------------------------------------
# 31. spring_bar_bore >= lug_width raises ValueError
# ---------------------------------------------------------------------------

def test_spring_bar_bore_too_large_raises():
    with pytest.raises(ValueError, match="spring_bar_bore_mm"):
        compute_watch_params(spring_bar_bore_mm=25.0, lug_width_mm=20.0)


# ---------------------------------------------------------------------------
# 32. crown_tube_od >= crown_dia raises ValueError
# ---------------------------------------------------------------------------

def test_crown_tube_too_large_raises():
    with pytest.raises(ValueError, match="crown_tube_od_mm"):
        compute_watch_params(crown_tube_od_mm=7.0, crown_diameter_mm=6.0)


# ---------------------------------------------------------------------------
# 33. Negative water_resistance raises ValueError
# ---------------------------------------------------------------------------

def test_negative_water_resistance_raises():
    with pytest.raises(ValueError, match="water_resistance_m"):
        compute_watch_params(water_resistance_m=-10.0)


# ---------------------------------------------------------------------------
# 34. Platinum 950 density applied correctly
# ---------------------------------------------------------------------------

def test_platinum_density_applied():
    p = default_params(metal="platinum_950")
    assert abs(p["density_g_cm3"] - METAL_DENSITY_G_CM3["platinum_950"]) < 1e-9


# ---------------------------------------------------------------------------
# 35. Titanium case is lighter than 18k gold equivalent
# ---------------------------------------------------------------------------

def test_titanium_lighter_than_gold():
    p_ti = default_params(metal="titanium")
    p_18k = default_params(metal="18k_yellow")
    assert p_ti["weight_g"] < p_18k["weight_g"]


# ---------------------------------------------------------------------------
# 36. Explicit movement_diameter_mm path (no caliber key)
# ---------------------------------------------------------------------------

def test_explicit_movement_diameter_mm():
    p = default_params(movement_diameter_mm=26.0, case_diameter_mm=40.0)
    assert abs(p["movement_diameter_mm"] - 26.0) < 1e-9
    assert p["caliber"] is None


# ---------------------------------------------------------------------------
# 37. Caseback thread pitch absent (None) for snap back
# ---------------------------------------------------------------------------

def test_snap_caseback_no_thread_pitch():
    p = default_params(caseback_style="snap")
    assert p["caseback_thread_pitch_mm"] is None


# ---------------------------------------------------------------------------
# 38. build_watch_node returns node with 'id' and 'file_id'
# ---------------------------------------------------------------------------

def test_build_watch_node_has_id():
    import uuid
    fid = uuid.uuid4()
    node = build_watch_node(file_id=fid)
    assert "id" in node
    assert node["file_id"] == str(fid)
    assert node["op"] == "watch"


# ---------------------------------------------------------------------------
# 39. WR gasket groove present at exactly 30 m boundary (False below, True above)
# ---------------------------------------------------------------------------

def test_wr_gasket_groove_boundary():
    p30 = default_params(water_resistance_m=30.0)
    assert p30["gasket_groove_present"] is False
    p31 = default_params(water_resistance_m=31.0)
    assert p31["gasket_groove_present"] is True


# ---------------------------------------------------------------------------
# 40. Gasket groove present when gasket_width_mm > 0 even at 0 m WR
# ---------------------------------------------------------------------------

def test_gasket_groove_present_via_gasket_width():
    p = default_params(water_resistance_m=0.0, gasket_width_mm=0.8)
    assert p["gasket_groove_present"] is True


# ---------------------------------------------------------------------------
# 41. Gasket groove present when gasket_profile is set even at 0 m WR
# ---------------------------------------------------------------------------

def test_gasket_groove_present_via_gasket_profile():
    p = default_params(water_resistance_m=0.0, gasket_profile="o_ring")
    assert p["gasket_groove_present"] is True


# ---------------------------------------------------------------------------
# 42. Cushion case: explicit cushion_radius_mm accepted
# ---------------------------------------------------------------------------

def test_cushion_explicit_radius():
    p = default_params(case_shape="cushion", case_diameter_mm=40.0, cushion_radius_mm=5.0)
    assert abs(p["cushion_radius_mm"] - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# 43. DIVE_BEZEL_TEETH constant matches spec value
# ---------------------------------------------------------------------------

def test_dive_bezel_teeth_constant():
    assert DIVE_BEZEL_TEETH == 120


# ---------------------------------------------------------------------------
# 44. Domed sapphire crystal style accepted
# ---------------------------------------------------------------------------

def test_domed_sapphire_crystal():
    p = default_params(crystal_style="domed_sapphire")
    assert p["crystal_style"] == "domed_sapphire"


# ---------------------------------------------------------------------------
# 45. Weight formula: platinum_950 case heavier than titanium at same geometry
# ---------------------------------------------------------------------------

def test_platinum_heavier_than_titanium():
    kwargs = dict(
        case_diameter_mm=38.0,
        lug_length_mm=9.0,
        case_thickness_mm=10.0,
    )
    p_pt = compute_watch_params(metal="platinum_950", **kwargs)
    p_ti = compute_watch_params(metal="titanium", **kwargs)
    assert p_pt["weight_g"] > p_ti["weight_g"]
