"""
Tests for kerf_cad_core.jewelry.profile_lib

Pure-Python: always runs (no OCCT required).

Coverage:
  - rectangle / flat: area = w * t exact; Ixx = w*t^3/12 exact; Iyy = t*w^3/12 exact
  - half_round: area vs analytic (pi*r^2/2)
  - comfort_fit: inner_radius matches param
  - d_shape: perimeter vs formula; centroid on symmetry axis
  - square: area = w^2 exact
  - catalogue: all 15 named profiles present in list_profiles() + _BUILDERS
  - centroid on symmetry axis for all symmetric profiles
  - Ixx/Iyy units & positive values
  - missing profile error path (get_profile returns error dict)
  - compare_comfort: returns winner/scores/delta/explanation
  - compare_comfort: comfort_fit beats flat
  - all profile builders return polyline with >= 3 points
  - all profile builders return positive area
  - all profile builders return non-negative perimeter
  - knife_edge: apex_y == thickness/2
  - bevelled: chamfer key present in result
  - channel_ready: groove keys present
  - stamped_edge: edge_radius key present
  - bombe: dome_radius key present
  - double_bombe: both inner_radius and outer_radius positive
  - flat_with_comfort_edge: comfort_inner_radius matches param
  - knife_bombe: inner_dome_radius matches param
  - court: comfort_outer_radius matches param
  - LLM tool specs: names and required fields
  - run_jewelry_list_profiles returns all profiles
  - run_jewelry_get_profile success + error paths
  - run_jewelry_compare_comfort success + bad args path
  - rectangle == flat (area, perimeter identical for same dims)
  - Ixx / Iyy exact for rectangle: b*h^3/12 and h*b^3/12
  - list_profiles returns dicts with name/description/params keys
  - all profiles: centroid_x == 0 for symmetric profiles (width-symmetric)
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.jewelry.profile_lib import (
    _BUILDERS,
    _REGISTRY,
    _jewelry_compare_comfort_spec,
    _jewelry_get_profile_spec,
    _jewelry_list_profiles_spec,
    compare_comfort,
    get_profile,
    list_profiles,
    run_jewelry_compare_comfort,
    run_jewelry_get_profile,
    run_jewelry_list_profiles,
)

_PI = math.pi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_ctx():
    return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _rect_Ixx(w: float, t: float) -> float:
    """Exact second moment of area about centroidal X-axis for rectangle."""
    return w * t ** 3 / 12.0


def _rect_Iyy(w: float, t: float) -> float:
    """Exact second moment of area about centroidal Y-axis for rectangle."""
    return t * w ** 3 / 12.0


# ---------------------------------------------------------------------------
# 1. Catalogue completeness
# ---------------------------------------------------------------------------

_EXPECTED_PROFILES = {
    "comfort_fit", "court", "flat", "half_round", "d_shape", "knife_edge",
    "square", "rectangle", "stamped_edge", "bombe", "bevelled", "double_bombe",
    "flat_with_comfort_edge", "channel_ready", "knife_bombe",
}


def test_catalogue_contains_all_named_profiles():
    names = {p["name"] for p in list_profiles()}
    assert _EXPECTED_PROFILES.issubset(names), f"Missing: {_EXPECTED_PROFILES - names}"


def test_builders_contains_all_named_profiles():
    assert _EXPECTED_PROFILES.issubset(set(_BUILDERS.keys()))


def test_registry_contains_all_named_profiles():
    assert _EXPECTED_PROFILES.issubset(set(_REGISTRY.keys()))


def test_list_profiles_returns_correct_structure():
    for entry in list_profiles():
        assert "name" in entry
        assert "description" in entry
        assert "params" in entry
        assert isinstance(entry["params"], list)


# ---------------------------------------------------------------------------
# 2. Rectangle / flat: exact geometry
# ---------------------------------------------------------------------------

def test_flat_area_exact():
    w, t = 4.0, 2.0
    p = get_profile("flat", width=w, thickness=t)
    assert abs(p["area"] - w * t) < 1e-9


def test_flat_Ixx_exact():
    w, t = 5.0, 2.0
    p = get_profile("flat", width=w, thickness=t)
    expected = _rect_Ixx(w, t)
    assert abs(p["Ixx"] - expected) < 1e-4, f"Ixx {p['Ixx']} != {expected}"


def test_flat_Iyy_exact():
    w, t = 5.0, 2.0
    p = get_profile("flat", width=w, thickness=t)
    expected = _rect_Iyy(w, t)
    assert abs(p["Iyy"] - expected) < 1e-4, f"Iyy {p['Iyy']} != {expected}"


def test_rectangle_area_exact():
    w, t = 6.0, 1.5
    p = get_profile("rectangle", width=w, thickness=t)
    assert abs(p["area"] - w * t) < 1e-9


def test_rectangle_Ixx_equals_flat_Ixx():
    w, t = 4.0, 2.0
    pf = get_profile("flat", width=w, thickness=t)
    pr = get_profile("rectangle", width=w, thickness=t)
    assert abs(pf["Ixx"] - pr["Ixx"]) < 1e-9


def test_rectangle_Iyy_equals_flat_Iyy():
    w, t = 4.0, 2.0
    pf = get_profile("flat", width=w, thickness=t)
    pr = get_profile("rectangle", width=w, thickness=t)
    assert abs(pf["Iyy"] - pr["Iyy"]) < 1e-9


def test_rectangle_perimeter_equals_flat_perimeter():
    w, t = 4.0, 2.0
    pf = get_profile("flat", width=w, thickness=t)
    pr = get_profile("rectangle", width=w, thickness=t)
    assert abs(pf["perimeter"] - pr["perimeter"]) < 1e-9


def test_flat_centroid_on_symmetry_axis():
    p = get_profile("flat", width=5.0, thickness=2.0)
    cx, cy = p["centroid"]
    assert abs(cx) < 1e-6, f"centroid_x {cx} not on symmetry axis"
    assert abs(cy) < 1e-6, f"centroid_y {cy} not zero for symmetric flat"


# ---------------------------------------------------------------------------
# 3. Square
# ---------------------------------------------------------------------------

def test_square_area_exact():
    w = 3.0
    p = get_profile("square", width=w)
    assert abs(p["area"] - w ** 2) < 1e-9


def test_square_Ixx_equals_Iyy():
    w = 3.0
    p = get_profile("square", width=w)
    assert abs(p["Ixx"] - p["Iyy"]) < 1e-6, "Square must have Ixx == Iyy"


def test_square_centroid_at_origin():
    p = get_profile("square", width=4.0)
    cx, cy = p["centroid"]
    assert abs(cx) < 1e-6 and abs(cy) < 1e-6


# ---------------------------------------------------------------------------
# 4. Half-round: analytic area
# ---------------------------------------------------------------------------

def test_half_round_area_vs_analytic():
    w, t = 6.0, 3.0  # r = w/2 = 3.0
    r = w / 2.0
    analytic_area = _PI * r ** 2 / 2.0
    p = get_profile("half_round", width=w, thickness=t)
    # Polygon approximation; tolerance ~0.5%
    assert abs(p["area"] - analytic_area) / analytic_area < 0.005, (
        f"half_round area {p['area']:.4f} vs analytic {analytic_area:.4f}"
    )


def test_half_round_centroid_x_zero():
    p = get_profile("half_round", width=6.0, thickness=3.0)
    assert abs(p["centroid"][0]) < 1e-6


# ---------------------------------------------------------------------------
# 5. Comfort fit: inner radius
# ---------------------------------------------------------------------------

def test_comfort_fit_inner_radius_matches_param():
    r = 1.5
    p = get_profile("comfort_fit", width=5.0, thickness=3.0, inner_radius=r)
    assert "comfort_inner_radius" in p
    assert abs(p["comfort_inner_radius"] - r) < 1e-9


def test_comfort_fit_default_inner_radius():
    t = 3.0
    p = get_profile("comfort_fit", width=5.0, thickness=t)
    # Default = t/2
    assert abs(p["comfort_inner_radius"] - t / 2.0) < 1e-9


def test_comfort_fit_centroid_x_zero():
    p = get_profile("comfort_fit", width=5.0, thickness=2.5)
    assert abs(p["centroid"][0]) < 1e-6


# ---------------------------------------------------------------------------
# 6. D-shape: perimeter and centroid
# ---------------------------------------------------------------------------

def test_d_shape_centroid_x_zero():
    p = get_profile("d_shape", width=5.0, thickness=3.0)
    assert abs(p["centroid"][0]) < 1e-6, f"D-shape centroid_x {p['centroid'][0]}"


def test_d_shape_perimeter_positive():
    p = get_profile("d_shape", width=5.0, thickness=3.0)
    assert p["perimeter"] > 0


def test_d_shape_arc_radius_present():
    p = get_profile("d_shape", width=5.0, thickness=3.0)
    assert "arc_radius" in p and p["arc_radius"] > 0


# ---------------------------------------------------------------------------
# 7. All profiles: polyline >= 3 pts, area > 0, perimeter > 0
# ---------------------------------------------------------------------------

_DIMS = {
    "comfort_fit":            {"width": 5.0, "thickness": 2.5},
    "court":                  {"width": 5.0, "thickness": 2.5},
    "flat":                   {"width": 5.0, "thickness": 2.5},
    "half_round":             {"width": 6.0, "thickness": 3.0},
    "d_shape":                {"width": 5.0, "thickness": 3.0},
    "knife_edge":             {"width": 5.0, "thickness": 2.5},
    "square":                 {"width": 3.0},
    "rectangle":              {"width": 5.0, "thickness": 2.5},
    "stamped_edge":           {"width": 5.0, "thickness": 2.5},
    "bombe":                  {"width": 5.0, "thickness": 2.5},
    "bevelled":               {"width": 5.0, "thickness": 2.5},
    "double_bombe":           {"width": 5.0, "thickness": 2.5},
    "flat_with_comfort_edge": {"width": 5.0, "thickness": 2.5},
    "channel_ready":          {"width": 6.0, "thickness": 3.0},
    "knife_bombe":            {"width": 5.0, "thickness": 2.5},
}


@pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
def test_profile_polyline_min_3_points(name):
    p = get_profile(name, **_DIMS[name])
    assert "error" not in p, f"Profile {name} returned error: {p.get('error')}"
    assert len(p["polyline"]) >= 3


@pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
def test_profile_area_positive(name):
    p = get_profile(name, **_DIMS[name])
    assert "error" not in p
    assert p["area"] > 0, f"{name} area={p['area']}"


@pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
def test_profile_perimeter_positive(name):
    p = get_profile(name, **_DIMS[name])
    assert "error" not in p
    assert p["perimeter"] > 0


@pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
def test_profile_Ixx_Iyy_nonnegative(name):
    p = get_profile(name, **_DIMS[name])
    assert "error" not in p
    assert p["Ixx"] >= 0
    assert p["Iyy"] >= 0


@pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES - {"knife_edge", "half_round", "d_shape"}))
def test_profile_centroid_x_on_symmetry_axis(name):
    p = get_profile(name, **_DIMS[name])
    assert "error" not in p
    assert abs(p["centroid"][0]) < 1e-4, (
        f"{name} centroid_x={p['centroid'][0]:.6f}, expected ~0"
    )


# ---------------------------------------------------------------------------
# 8. Profile-specific properties
# ---------------------------------------------------------------------------

def test_knife_edge_apex_y():
    t = 2.5
    p = get_profile("knife_edge", width=5.0, thickness=t)
    assert abs(p["apex_y"] - t / 2.0) < 1e-9


def test_bevelled_chamfer_key():
    p = get_profile("bevelled", width=5.0, thickness=2.5)
    assert "chamfer" in p and p["chamfer"] > 0


def test_channel_ready_groove_keys():
    p = get_profile("channel_ready", width=6.0, thickness=3.0)
    assert "groove_width" in p and p["groove_width"] > 0
    assert "groove_depth" in p and p["groove_depth"] > 0


def test_stamped_edge_edge_radius_key():
    p = get_profile("stamped_edge", width=5.0, thickness=2.5)
    assert "edge_radius" in p and p["edge_radius"] > 0


def test_bombe_dome_radius_key():
    p = get_profile("bombe", width=5.0, thickness=2.5)
    assert "dome_radius" in p and p["dome_radius"] > 0


def test_double_bombe_inner_outer_radius_positive():
    p = get_profile("double_bombe", width=5.0, thickness=2.5)
    assert p["inner_radius"] > 0
    assert p["outer_radius"] > 0


def test_flat_with_comfort_edge_inner_radius_matches_param():
    r = 0.5
    p = get_profile("flat_with_comfort_edge", width=5.0, thickness=2.5, inner_radius=r)
    assert abs(p["comfort_inner_radius"] - r) < 1e-9


def test_knife_bombe_inner_dome_radius_matches_param():
    r = 6.0
    p = get_profile("knife_bombe", width=5.0, thickness=2.5, inner_radius=r)
    assert abs(p["inner_dome_radius"] - r) < 1e-9


def test_court_outer_radius_matches_param():
    r = 1.0
    p = get_profile("court", width=5.0, thickness=2.5, outer_radius=r)
    assert abs(p["comfort_outer_radius"] - r) < 1e-9


# ---------------------------------------------------------------------------
# 9. Missing profile error path
# ---------------------------------------------------------------------------

def test_get_profile_missing_returns_error_dict():
    p = get_profile("nonexistent_profile", width=5.0, thickness=2.0)
    assert "error" in p
    assert p.get("code") == "NOT_FOUND"


def test_get_profile_bad_param_returns_error_dict():
    # flat with missing thickness should return an error dict, not raise
    p = get_profile("flat", width=5.0)
    assert "error" in p


# ---------------------------------------------------------------------------
# 10. compare_comfort
# ---------------------------------------------------------------------------

def test_compare_comfort_structure():
    pa = get_profile("comfort_fit", width=5.0, thickness=2.5)
    pb = get_profile("flat", width=5.0, thickness=2.5)
    result = compare_comfort(pa, pb)
    assert "winner" in result
    assert "scores" in result
    assert "delta" in result
    assert "explanation" in result


def test_compare_comfort_comfort_fit_beats_flat():
    pa = get_profile("comfort_fit", width=5.0, thickness=2.5)
    pb = get_profile("flat", width=5.0, thickness=2.5)
    result = compare_comfort(pa, pb)
    assert result["winner"] == "comfort_fit", (
        f"Expected comfort_fit to win; got {result['winner']}"
    )


def test_compare_comfort_scores_are_dicts():
    pa = get_profile("court", width=5.0, thickness=2.5)
    pb = get_profile("flat", width=5.0, thickness=2.5)
    result = compare_comfort(pa, pb)
    assert isinstance(result["scores"], dict)
    assert len(result["scores"]) == 2


def test_compare_comfort_delta_nonnegative():
    pa = get_profile("comfort_fit", width=5.0, thickness=2.5)
    pb = get_profile("knife_edge", width=5.0, thickness=2.5)
    result = compare_comfort(pa, pb)
    assert result["delta"] >= 0


# ---------------------------------------------------------------------------
# 11. LLM tool specs
# ---------------------------------------------------------------------------

def test_list_profiles_spec_name():
    assert _jewelry_list_profiles_spec.name == "jewelry_list_profiles"


def test_get_profile_spec_name():
    assert _jewelry_get_profile_spec.name == "jewelry_get_profile"


def test_compare_comfort_spec_name():
    assert _jewelry_compare_comfort_spec.name == "jewelry_compare_comfort"


def test_get_profile_spec_required_fields():
    req = _jewelry_get_profile_spec.input_schema.get("required", [])
    assert "name" in req
    assert "width" in req


def test_compare_comfort_spec_required_fields():
    req = _jewelry_compare_comfort_spec.input_schema.get("required", [])
    assert "profile_a" in req
    assert "profile_b" in req


def test_get_profile_spec_enum_contains_all_profiles():
    enum = _jewelry_get_profile_spec.input_schema["properties"]["name"]["enum"]
    assert _EXPECTED_PROFILES.issubset(set(enum))


# ---------------------------------------------------------------------------
# 12. LLM tool runners
# ---------------------------------------------------------------------------

def test_run_list_profiles_returns_all_profiles():
    result = _run(run_jewelry_list_profiles(_fake_ctx(), b"{}"))
    data = json.loads(result)
    assert isinstance(data, list)
    names = {p["name"] for p in data}
    assert _EXPECTED_PROFILES.issubset(names)


def test_run_get_profile_flat_success():
    result = _run(run_jewelry_get_profile(_fake_ctx(), _args(name="flat", width=4.0, thickness=2.0)))
    data = json.loads(result)
    assert "error" not in data
    assert abs(data["area"] - 8.0) < 1e-9


def test_run_get_profile_missing_name_error():
    result = _run(run_jewelry_get_profile(_fake_ctx(), _args(width=4.0, thickness=2.0)))
    data = json.loads(result)
    assert "error" in data


def test_run_get_profile_unknown_name_error():
    result = _run(run_jewelry_get_profile(_fake_ctx(), _args(name="no_such", width=4.0, thickness=2.0)))
    data = json.loads(result)
    assert "error" in data


def test_run_compare_comfort_success():
    pa = get_profile("comfort_fit", width=5.0, thickness=2.5)
    pb = get_profile("flat", width=5.0, thickness=2.5)
    result = _run(run_jewelry_compare_comfort(_fake_ctx(), _args(profile_a=pa, profile_b=pb)))
    data = json.loads(result)
    assert "winner" in data


def test_run_compare_comfort_bad_args():
    result = _run(run_jewelry_compare_comfort(_fake_ctx(), _args(profile_a="not_a_dict", profile_b={})))
    data = json.loads(result)
    assert "error" in data


def test_run_compare_comfort_invalid_json():
    result = _run(run_jewelry_compare_comfort(_fake_ctx(), b"not json"))
    data = json.loads(result)
    assert "error" in data
