"""
Tests for kerf_cad_core.sheet_metal_bend_table (T-4).

≥25 hermetic tests; no database, no OCCT, no ProjectCtx.

Formulae under test
───────────────────
BA  = (π/180)·angle·(r + K·t)
BD  = 2·OSSB − BA,  OSSB = tan(angle/2)·(r + t)
K monotone in r/t: K(r/t=3) ≥ K(r/t=1) ≥ K(r/t=0.5) for a given material
Spring-back: stainless > mild_steel  (higher Y/E ratio)
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.sheet_metal_bend_table import (
    bend_table,
    apply_bend_table,
    custom_table_load,
    _MATERIAL_TABLE,
    _CUSTOM_TABLE,
    _k_from_r_over_t,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ba_exact(angle_deg: float, r: float, k: float, t: float) -> float:
    """Reference formula: BA = (π/180)·angle·(r + K·t)."""
    return math.radians(angle_deg) * (r + k * t)


def _ossb(angle_deg: float, r: float, t: float) -> float:
    return math.tan(math.radians(angle_deg / 2.0)) * (r + t)


def _bd_exact(angle_deg: float, r: float, k: float, t: float) -> float:
    return 2.0 * _ossb(angle_deg, r, t) - _ba_exact(angle_deg, r, k, t)


# ---------------------------------------------------------------------------
# 1. Basic BA formula: known K round-trips exactly
# ---------------------------------------------------------------------------

def test_ba_mild_steel_90deg():
    """BA for mild_steel at 90°, r=2, t=1 matches exact formula.

    Tolerance is 1e-5 mm to accommodate the 6-decimal-place rounding of k_factor
    in the returned payload vs. the unrounded internal value.
    """
    res = bend_table("mild_steel", thickness=1.0, inner_radius=2.0, angle_deg=90.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_ba = _ba_exact(90.0, 2.0, k, 1.0)
    assert abs(res["bend_allowance_mm"] - expected_ba) < 1e-5


def test_ba_stainless_45deg():
    res = bend_table("stainless", thickness=1.5, inner_radius=3.0, angle_deg=45.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_ba = _ba_exact(45.0, 3.0, k, 1.5)
    assert abs(res["bend_allowance_mm"] - expected_ba) < 1e-5


def test_ba_aluminum_5052_120deg():
    res = bend_table("aluminum_5052", thickness=2.0, inner_radius=4.0, angle_deg=120.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_ba = _ba_exact(120.0, 4.0, k, 2.0)
    assert abs(res["bend_allowance_mm"] - expected_ba) < 1e-5


def test_ba_brass_30deg():
    res = bend_table("brass", thickness=0.8, inner_radius=1.6, angle_deg=30.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_ba = _ba_exact(30.0, 1.6, k, 0.8)
    assert abs(res["bend_allowance_mm"] - expected_ba) < 1e-5


def test_ba_copper_180deg():
    res = bend_table("copper", thickness=1.0, inner_radius=2.0, angle_deg=180.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_ba = _ba_exact(180.0, 2.0, k, 1.0)
    assert abs(res["bend_allowance_mm"] - expected_ba) < 1e-5


# ---------------------------------------------------------------------------
# 2. Bend deduction = 2·OSSB − BA
# ---------------------------------------------------------------------------

def test_bend_deduction_mild_steel():
    res = bend_table("mild_steel", 1.0, 2.0, 90.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_bd = _bd_exact(90.0, 2.0, k, 1.0)
    assert abs(res["bend_deduction_mm"] - expected_bd) < 1e-5


def test_bend_deduction_al6061():
    res = bend_table("aluminum_6061", 2.0, 3.0, 60.0)
    assert res["ok"]
    k = res["k_factor"]
    expected_bd = _bd_exact(60.0, 3.0, k, 2.0)
    assert abs(res["bend_deduction_mm"] - expected_bd) < 1e-5


def test_setback_formula():
    """OSSB = tan(angle/2)·(r+t)."""
    res = bend_table("mild_steel", 1.0, 2.0, 90.0)
    assert res["ok"]
    expected_ossb = _ossb(90.0, 2.0, 1.0)
    assert abs(res["setback_mm"] - expected_ossb) < 1e-5


# ---------------------------------------------------------------------------
# 3. K-factor monotone in r/t
# ---------------------------------------------------------------------------

def test_k_factor_monotone_mild_steel():
    """K(r/t=0.5) ≤ K(r/t=1.5) ≤ K(r/t=3.5)."""
    r_values = [0.5, 1.5, 3.5]
    t = 1.0
    k_values = [
        bend_table("mild_steel", t, r, 90.0)["k_factor"] for r in r_values
    ]
    assert k_values[0] <= k_values[1] <= k_values[2]


def test_k_factor_monotone_stainless():
    r_values = [0.8, 2.0, 4.0]
    t = 1.0
    k_values = [
        bend_table("stainless", t, r, 90.0)["k_factor"] for r in r_values
    ]
    assert k_values[0] <= k_values[1] <= k_values[2]


def test_k_factor_monotone_aluminum():
    r_values = [0.5, 1.0, 3.5]
    t = 1.0
    k_values = [
        bend_table("aluminum_5052", t, r, 90.0)["k_factor"] for r in r_values
    ]
    assert k_values[0] <= k_values[1] <= k_values[2]


# ---------------------------------------------------------------------------
# 4. Coining K > air-bend K (per process modifier)
# ---------------------------------------------------------------------------

def test_coining_k_gt_air_bend():
    k_air = bend_table("mild_steel", 1.0, 2.0, 90.0, "air_bend")["k_factor"]
    k_coin = bend_table("mild_steel", 1.0, 2.0, 90.0, "coining")["k_factor"]
    assert k_coin > k_air


def test_bottoming_k_lt_air_bend():
    k_air = bend_table("mild_steel", 1.0, 2.0, 90.0, "air_bend")["k_factor"]
    k_bot = bend_table("mild_steel", 1.0, 2.0, 90.0, "bottoming")["k_factor"]
    assert k_bot < k_air


def test_coining_k_gt_air_bend_aluminum():
    k_air = bend_table("aluminum_6061", 2.0, 3.0, 90.0, "air_bend")["k_factor"]
    k_coin = bend_table("aluminum_6061", 2.0, 3.0, 90.0, "coining")["k_factor"]
    assert k_coin > k_air


# ---------------------------------------------------------------------------
# 5. Flat length via apply_bend_table — L-bracket hand-calc
# ---------------------------------------------------------------------------

def test_apply_bend_table_l_bracket():
    """
    L-bracket: base_length=50, one 90-deg bend, flange=30, mild steel t=1, r=2.
    flat_length = 50 + BA + 30   where BA = (π/2)·(2 + K·1)
    """
    fp = {"base_length": 50.0}
    bends = [{
        "material": "mild_steel",
        "thickness": 1.0,
        "inner_radius": 2.0,
        "angle_deg": 90.0,
        "flange_length": 30.0,
        "process": "air_bend",
    }]
    res = apply_bend_table(fp, bends)
    assert res["ok"]

    k = res["bends"][0]["k_factor"]
    ba = _ba_exact(90.0, 2.0, k, 1.0)
    expected = 50.0 + ba + 30.0
    assert abs(res["flat_length_mm"] - expected) < 1e-5


def test_apply_bend_table_two_bends():
    """U-channel: base + two equal 90-deg bends + two flanges."""
    fp = {"base_length": 40.0}
    bends = [
        {"material": "mild_steel", "thickness": 1.0, "inner_radius": 2.0,
         "angle_deg": 90.0, "flange_length": 20.0},
        {"material": "mild_steel", "thickness": 1.0, "inner_radius": 2.0,
         "angle_deg": 90.0, "flange_length": 20.0},
    ]
    res = apply_bend_table(fp, bends)
    assert res["ok"]

    k0 = res["bends"][0]["k_factor"]
    k1 = res["bends"][1]["k_factor"]
    ba0 = _ba_exact(90.0, 2.0, k0, 1.0)
    ba1 = _ba_exact(90.0, 2.0, k1, 1.0)
    expected = 40.0 + ba0 + 20.0 + ba1 + 20.0
    assert abs(res["flat_length_mm"] - expected) < 1e-5


# ---------------------------------------------------------------------------
# 6. Custom table override
# ---------------------------------------------------------------------------

def test_custom_table_override_used():
    """After loading a custom row the lookup returns exactly that K-factor."""
    _CUSTOM_TABLE.clear()
    result = custom_table_load([{
        "material": "mild_steel",
        "thickness": 1.0,
        "inner_radius": 2.0,
        "process": "air_bend",
        "k_factor": 0.39,
    }])
    assert result["ok"]
    assert result["loaded"] == 1

    res = bend_table("mild_steel", 1.0, 2.0, 90.0, "air_bend")
    assert res["ok"]
    assert abs(res["k_factor"] - 0.39) < 1e-9
    _CUSTOM_TABLE.clear()   # clean up


def test_custom_table_override_apply():
    """apply_bend_table uses the custom K when present."""
    _CUSTOM_TABLE.clear()
    custom_table_load([{
        "material": "brass",
        "thickness": 1.0,
        "inner_radius": 2.0,
        "process": "air_bend",
        "k_factor": 0.42,
    }])
    fp = {"base_length": 25.0}
    bends = [{"material": "brass", "thickness": 1.0, "inner_radius": 2.0,
               "angle_deg": 90.0, "flange_length": 15.0}]
    res = apply_bend_table(fp, bends)
    assert res["ok"]
    ba_expected = _ba_exact(90.0, 2.0, 0.42, 1.0)
    assert abs(res["flat_length_mm"] - (25.0 + ba_expected + 15.0)) < 1e-5
    _CUSTOM_TABLE.clear()


# ---------------------------------------------------------------------------
# 7. Spring-back: higher-strength material → larger spring-back
# ---------------------------------------------------------------------------

def test_springback_stainless_gt_mild_steel():
    """Stainless (higher Y/E) should have larger spring-back than mild steel."""
    ms = bend_table("mild_steel", 1.0, 2.0, 90.0)
    ss = bend_table("stainless", 1.0, 2.0, 90.0)
    assert ss["spring_back_angle_deg"] > ms["spring_back_angle_deg"]


def test_springback_positive():
    """Spring-back angle must be > 0 for all built-in materials."""
    for mat in _MATERIAL_TABLE:
        res = bend_table(mat, 1.0, 2.0, 90.0)
        assert res["ok"]
        assert res["spring_back_angle_deg"] > 0


def test_springback_increases_with_r_over_t():
    """Larger r/t → larger spring-back (thinner neutral-axis stabilisation)."""
    sb_small = bend_table("mild_steel", 1.0, 1.0, 90.0)["spring_back_angle_deg"]
    sb_large = bend_table("mild_steel", 1.0, 5.0, 90.0)["spring_back_angle_deg"]
    assert sb_large > sb_small


# ---------------------------------------------------------------------------
# 8. Invalid material → graceful error
# ---------------------------------------------------------------------------

def test_invalid_material_returns_error():
    res = bend_table("unobtainium", 1.0, 2.0, 90.0)
    assert not res["ok"]
    assert "unknown material" in res["reason"].lower()


def test_invalid_process_returns_error():
    res = bend_table("mild_steel", 1.0, 2.0, 90.0, process="laser_bend")
    assert not res["ok"]
    assert "unknown process" in res["reason"].lower()


def test_zero_thickness_returns_error():
    res = bend_table("mild_steel", 0.0, 2.0, 90.0)
    assert not res["ok"]
    assert "thickness" in res["reason"].lower()


def test_angle_out_of_range():
    res = bend_table("mild_steel", 1.0, 2.0, 200.0)
    assert not res["ok"]
    assert "angle" in res["reason"].lower()


def test_custom_table_invalid_material():
    result = custom_table_load([{
        "material": "unobtainium",
        "thickness": 1.0,
        "inner_radius": 2.0,
        "process": "air_bend",
        "k_factor": 0.40,
    }])
    assert not result["ok"]


# ---------------------------------------------------------------------------
# 9. Neutral-axis offset = K × t
# ---------------------------------------------------------------------------

def test_neutral_axis_offset():
    res = bend_table("mild_steel", 2.0, 4.0, 90.0)
    assert res["ok"]
    expected = res["k_factor"] * 2.0
    assert abs(res["neutral_axis_offset_mm"] - expected) < 1e-5


# ---------------------------------------------------------------------------
# 10. Alias resolution
# ---------------------------------------------------------------------------

def test_alias_mild_steel():
    r1 = bend_table("mild_steel", 1.0, 2.0, 90.0)
    r2 = bend_table("steel", 1.0, 2.0, 90.0)
    assert r1["ok"] and r2["ok"]
    assert abs(r1["k_factor"] - r2["k_factor"]) < 1e-9


def test_alias_stainless():
    r1 = bend_table("stainless", 1.0, 2.0, 90.0)
    r2 = bend_table("304", 1.0, 2.0, 90.0)
    assert r1["ok"] and r2["ok"]
    assert abs(r1["k_factor"] - r2["k_factor"]) < 1e-9


# ---------------------------------------------------------------------------
# 11. apply_bend_table edge-case validation
# ---------------------------------------------------------------------------

def test_apply_bend_table_missing_base_length():
    res = apply_bend_table({}, [{"material": "mild_steel", "thickness": 1.0,
                                  "inner_radius": 2.0, "angle_deg": 90.0,
                                  "flange_length": 10.0}])
    assert not res["ok"]


def test_apply_bend_table_empty_bends():
    res = apply_bend_table({"base_length": 50.0}, [])
    assert not res["ok"]
