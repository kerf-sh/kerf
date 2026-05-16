"""
Hermetic tests for kerf_cad_core.lighting — illumination engineering calculators.

Coverage:
  design.room_cavity_ratio          — RCR formula
  design.coefficient_of_utilization — CU table interpolation
  design.light_loss_factor          — LLF product
  design.luminaires_for_target_lux  — lumen method N (ceiling)
  design.lux_from_luminaires        — inverse lumen method
  design.spacing_to_mounting_height_ratio — S/MH + uniformity warning
  design.uniformity_check           — U = E_min / E_avg
  design.horizontal_illuminance     — inverse-square cosine law
  design.vertical_illuminance       — sin×cos form
  design.multi_luminaire_illuminance — superposition
  design.luminance_from_illuminance — L = E·ρ/π
  design.exitance                   — M = E·ρ
  design.contrast_ratio             — Weber contrast
  design.ugr                        — CIE 117 glare rating
  design.road_luminance             — R-table roadway model
  design.pole_spacing               — S = SH × H
  design.roadway_utilization        — lumen utilisation method
  design.emergency_lux_at_floor     — E = I/d²
  design.emergency_spacing          — midpoint lux solve
  design.lamp_lumens_per_watt       — efficacy lookup
  design.lamp_energy                — energy Wh / kWh
  design.lpd_check                  — ASHRAE + Title24 LPD check
  tools.*                           — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified against IES HB-10 lumen method and inverse-square point method
hand calculations.

References
----------
IES Lighting Handbook, 10th ed. (IESNA, 2011)
CIE 117-1995 — Discomfort Glare in Interior Lighting
EN 12464-1:2021 — Light and Lighting
ASHRAE 90.1-2022, §9 — Lighting

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.lighting.design import (
    room_cavity_ratio,
    coefficient_of_utilization,
    light_loss_factor,
    luminaires_for_target_lux,
    lux_from_luminaires,
    spacing_to_mounting_height_ratio,
    uniformity_check,
    horizontal_illuminance,
    vertical_illuminance,
    multi_luminaire_illuminance,
    luminance_from_illuminance,
    exitance,
    contrast_ratio,
    ugr,
    road_luminance,
    pole_spacing,
    roadway_utilization,
    emergency_lux_at_floor,
    emergency_spacing,
    lamp_lumens_per_watt,
    lamp_energy,
    lpd_check,
)
from kerf_cad_core.lighting.tools import (
    run_lighting_room_cavity_ratio,
    run_lighting_cu,
    run_lighting_llf,
    run_lighting_n_luminaires,
    run_lighting_lux_from_n,
    run_lighting_smh,
    run_lighting_uniformity,
    run_lighting_eh,
    run_lighting_ev,
    run_lighting_multi,
    run_lighting_luminance,
    run_lighting_exitance,
    run_lighting_contrast,
    run_lighting_ugr,
    run_lighting_road_luminance,
    run_lighting_pole_spacing,
    run_lighting_roadway_util,
    run_lighting_emergency_lux,
    run_lighting_emergency_spacing,
    run_lighting_lamp_lpw,
    run_lighting_energy,
    run_lighting_lpd,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


# ---------------------------------------------------------------------------
# 1. room_cavity_ratio
# ---------------------------------------------------------------------------

def test_rcr_square_room():
    # 10 × 10 room, cavity height 2.4 m
    # RCR = 5 × 2.4 × (10 + 10) / (10 × 10) = 5 × 2.4 × 20 / 100 = 2.4
    r = room_cavity_ratio(10.0, 10.0, 2.4)
    assert r["ok"] is True
    assert abs(r["rcr"] - 2.4) < 1e-4


def test_rcr_rectangular_room():
    # IES HB-10 example: 8 × 6 room, h_c = 2.0 m
    # RCR = 5 × 2.0 × (8 + 6) / (8 × 6) = 5 × 2 × 14 / 48 ≈ 2.9167
    r = room_cavity_ratio(8.0, 6.0, 2.0)
    assert r["ok"] is True
    assert abs(r["rcr"] - (5 * 2.0 * 14 / 48)) < 1e-3


def test_rcr_invalid_zero_length():
    r = room_cavity_ratio(0.0, 5.0, 2.0)
    assert r["ok"] is False


def test_rcr_invalid_negative_height():
    r = room_cavity_ratio(5.0, 5.0, -1.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 2. coefficient_of_utilization
# ---------------------------------------------------------------------------

def test_cu_rcr_zero():
    # At RCR=0 the CU equals the table value at index 0 (80/50 key ≈ 1.19)
    r = coefficient_of_utilization(0.0, rho_ceiling_pct=80, rho_walls_pct=50)
    assert r["ok"] is True
    assert abs(r["cu"] - 1.19) < 0.01


def test_cu_rcr_5_interp():
    # At RCR=5 exactly, CU for 70/50 key should equal table[5] = 0.69
    r = coefficient_of_utilization(5.0, rho_ceiling_pct=70, rho_walls_pct=50)
    assert r["ok"] is True
    assert abs(r["cu"] - 0.69) < 0.01


def test_cu_rcr_interpolated():
    # RCR=2.5, 80/50 key: values[2]=0.97, values[3]=0.88 → 0.97+0.5*(0.88-0.97)=0.925
    r = coefficient_of_utilization(2.5, rho_ceiling_pct=80, rho_walls_pct=50)
    assert r["ok"] is True
    assert abs(r["cu"] - 0.925) < 0.005


def test_cu_rcr_negative():
    r = coefficient_of_utilization(-1.0)
    assert r["ok"] is False


def test_cu_rcr_clamped_to_10():
    r = coefficient_of_utilization(15.0, rho_ceiling_pct=80, rho_walls_pct=50)
    assert r["ok"] is True
    assert r["rcr_used"] == 10.0


# ---------------------------------------------------------------------------
# 3. light_loss_factor
# ---------------------------------------------------------------------------

def test_llf_defaults():
    r = light_loss_factor()
    assert r["ok"] is True
    # LLF = 0.85 × 0.90 × 1.0 × 1.0 = 0.765
    assert abs(r["llf"] - 0.765) < 1e-5


def test_llf_custom():
    r = light_loss_factor(lld=0.80, ldd=0.85, ballast_factor=1.0,
                           temperature_factor=0.95)
    assert r["ok"] is True
    expected = 0.80 * 0.85 * 1.0 * 0.95
    assert abs(r["llf"] - expected) < 1e-6


def test_llf_invalid_zero():
    r = light_loss_factor(lld=0.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 4. luminaires_for_target_lux
# ---------------------------------------------------------------------------

def test_n_luminaires_basic():
    # N = ceil( (500 × 100) / (3200 × 1 × 0.65 × 0.80) ) = ceil(50000/1664) = ceil(30.05) = 31
    r = luminaires_for_target_lux(100.0, 500.0, 3200.0,
                                   lamps_per_luminaire=1, cu=0.65, llf=0.80)
    assert r["ok"] is True
    assert r["n_luminaires"] == 31
    # actual lux: 31 × 3200 × 0.65 × 0.80 / 100 = 514.24
    assert abs(r["actual_lux"] - 31 * 3200 * 0.65 * 0.80 / 100) < 0.05


def test_n_luminaires_two_lamp():
    # 2-lamp luminaire: lumens_per_luminaire = 2 × 2000 = 4000
    # N = ceil( (300 × 50) / (2000 × 2 × 0.70 × 0.75) ) = ceil(15000/2100) = ceil(7.14) = 8
    r = luminaires_for_target_lux(50.0, 300.0, 2000.0,
                                   lamps_per_luminaire=2, cu=0.70, llf=0.75)
    assert r["ok"] is True
    assert r["n_luminaires"] == 8


def test_n_luminaires_invalid_area():
    r = luminaires_for_target_lux(0.0, 500.0, 3200.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. lux_from_luminaires
# ---------------------------------------------------------------------------

def test_lux_from_n_roundtrip():
    # Use same params as test_n_luminaires_basic; 31 luminaires → ~514 lx
    r = lux_from_luminaires(31, 3200.0, cu=0.65, llf=0.80, area_m2=100.0)
    assert r["ok"] is True
    expected = 31 * 3200 * 0.65 * 0.80 / 100.0
    assert abs(r["avg_lux"] - expected) < 0.05


def test_lux_from_n_zero_luminaires():
    r = lux_from_luminaires(0, 3200.0, cu=0.65, llf=0.80, area_m2=100.0)
    assert r["ok"] is True
    assert r["avg_lux"] == 0.0


# ---------------------------------------------------------------------------
# 6. spacing_to_mounting_height_ratio
# ---------------------------------------------------------------------------

def test_smh_typical():
    r = spacing_to_mounting_height_ratio(2.4, 3.0)
    assert r["ok"] is True
    assert abs(r["s_mh"] - 2.4 / 3.0) < 1e-4
    # 0.8 < 1.5 — no warning
    assert r["warnings"] == []


def test_smh_poor_uniformity_warning():
    r = spacing_to_mounting_height_ratio(5.0, 3.0)
    assert r["ok"] is True
    assert r["s_mh"] > 1.5
    assert any("poor-uniformity" in w for w in r["warnings"])


def test_smh_invalid():
    r = spacing_to_mounting_height_ratio(0.0, 3.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 7. uniformity_check
# ---------------------------------------------------------------------------

def test_uniformity_pass():
    r = uniformity_check(350.0, 500.0)
    assert r["ok"] is True
    assert abs(r["uniformity"] - 0.70) < 1e-4
    assert r["passed"] is True
    assert r["warnings"] == []


def test_uniformity_fail():
    r = uniformity_check(200.0, 500.0)
    assert r["ok"] is True
    assert r["passed"] is False
    assert any("poor-uniformity" in w for w in r["warnings"])


def test_uniformity_invalid_min_exceeds_avg():
    r = uniformity_check(600.0, 500.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 8. horizontal_illuminance — point method
# ---------------------------------------------------------------------------

def test_eh_nadir():
    # θ=0: E_h = I/d² = 1000/4 = 250 lx
    r = horizontal_illuminance(1000.0, 2.0, 0.0)
    assert r["ok"] is True
    assert abs(r["e_horizontal_lux"] - 250.0) < 1e-4


def test_eh_30deg():
    # θ=30°: E_h = I cos(30°) / d²
    I, d, theta = 1000.0, 3.0, 30.0
    expected = I * math.cos(math.radians(theta)) / (d ** 2)
    r = horizontal_illuminance(I, d, theta)
    assert r["ok"] is True
    assert abs(r["e_horizontal_lux"] - expected) < 1e-4


def test_eh_invalid_angle():
    r = horizontal_illuminance(500.0, 2.0, 90.0)
    assert r["ok"] is False


def test_eh_zero_intensity():
    r = horizontal_illuminance(0.0, 2.0, 0.0)
    assert r["ok"] is True
    assert r["e_horizontal_lux"] == 0.0


# ---------------------------------------------------------------------------
# 9. vertical_illuminance
# ---------------------------------------------------------------------------

def test_ev_45deg():
    # θ=45°: E_v = I sin(45°) cos(45°) / d² = I × 0.5 / d²
    I, d = 1000.0, 2.0
    expected = I * math.sin(math.radians(45)) * math.cos(math.radians(45)) / (d ** 2)
    r = vertical_illuminance(I, d, 45.0)
    assert r["ok"] is True
    assert abs(r["e_vertical_lux"] - expected) < 1e-4


def test_ev_zero_angle():
    # θ=0: E_v = 0 (vertical plane tangent to beam)
    r = vertical_illuminance(1000.0, 2.0, 0.0)
    assert r["ok"] is True
    assert abs(r["e_vertical_lux"]) < 1e-9


# ---------------------------------------------------------------------------
# 10. multi_luminaire_illuminance
# ---------------------------------------------------------------------------

def test_multi_two_luminaires():
    # Two identical luminaires at (0,0,3) and (4,0,3), target point at (2,0,0)
    # Each luminaire is 2 m horizontally from midpoint (2,0,0):
    #   d = sqrt((2-0)² + (0-0)² + (0-3)²) = sqrt(4 + 9) = sqrt(13)
    # h = 3 (luminaire z - point z), cos_theta = 3 / sqrt(13)
    # E_h_each = I × cos_theta / d²
    I = 500.0
    lums = [
        {"x": 0.0, "y": 0.0, "z": 3.0, "intensity_cd": I},
        {"x": 4.0, "y": 0.0, "z": 3.0, "intensity_cd": I},
    ]
    pt = {"x": 2.0, "y": 0.0, "z": 0.0}
    r = multi_luminaire_illuminance(lums, pt)
    assert r["ok"] is True
    d = math.sqrt(2.0 ** 2 + 9.0)  # sqrt(4 + 9) = sqrt(13) for each luminaire
    cos_t = 3.0 / d
    e_each = I * cos_t / (d ** 2)
    expected_total = 2 * e_each
    assert abs(r["total_lux"] - expected_total) < 0.005


def test_multi_empty_list():
    r = multi_luminaire_illuminance([], {"x": 0, "y": 0, "z": 0})
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 11. luminance_from_illuminance
# ---------------------------------------------------------------------------

def test_luminance_basic():
    # L = 500 × 0.5 / π ≈ 79.577 cd/m²
    r = luminance_from_illuminance(500.0, 0.5)
    assert r["ok"] is True
    assert abs(r["luminance_cd_m2"] - 500.0 * 0.5 / math.pi) < 1e-4


def test_luminance_zero_reflectance():
    r = luminance_from_illuminance(500.0, 0.0)
    assert r["ok"] is True
    assert r["luminance_cd_m2"] == 0.0


def test_luminance_invalid_reflectance():
    r = luminance_from_illuminance(500.0, 1.5)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 12. exitance
# ---------------------------------------------------------------------------

def test_exitance_basic():
    # M = 500 × 0.7 = 350 lm/m²
    r = exitance(500.0, 0.7)
    assert r["ok"] is True
    assert abs(r["exitance_lm_m2"] - 350.0) < 1e-6


# ---------------------------------------------------------------------------
# 13. contrast_ratio
# ---------------------------------------------------------------------------

def test_contrast_positive():
    # (300 - 100) / 100 = 2.0
    r = contrast_ratio(300.0, 100.0)
    assert r["ok"] is True
    assert abs(r["contrast"] - 2.0) < 1e-6


def test_contrast_negative():
    # (50 - 100) / 100 = -0.5
    r = contrast_ratio(50.0, 100.0)
    assert r["ok"] is True
    assert abs(r["contrast"] - (-0.5)) < 1e-6


def test_contrast_invalid_bg_zero():
    r = contrast_ratio(100.0, 0.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 14. ugr
# ---------------------------------------------------------------------------

def test_ugr_basic():
    # Single glare source: Li=10000, Ω=0.0003, p=2.0, Lb=30
    # UGR = 8 × log10(0.25/30 × 10000² × 0.0003 / 4.0)
    #      = 8 × log10(0.25/30 × 7500000)
    Lb = 30.0
    Li = [10000.0]
    Omega = [0.0003]
    p = [2.0]
    summation = (10000.0 ** 2) * 0.0003 / (2.0 ** 2)
    expected = 8.0 * math.log10(0.25 / Lb * summation)
    r = ugr(Lb, Li, Omega, p)
    assert r["ok"] is True
    assert abs(r["ugr"] - expected) < 0.01


def test_ugr_warning_high():
    # Engineered to produce UGR > 28
    r = ugr(1.0, [100000.0], [0.01], [1.0])
    assert r["ok"] is True
    assert r["ugr"] > 28
    assert any("glare-exceeds" in w for w in r["warnings"])


def test_ugr_invalid_empty():
    r = ugr(30.0, [], [], [])
    assert r["ok"] is False


def test_ugr_invalid_background_zero():
    r = ugr(0.0, [1000.0], [0.001], [1.5])
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 15. road_luminance
# ---------------------------------------------------------------------------

def test_road_luminance_basic():
    # L = I × r / H²;  H = d × cos(θ)
    # I=5000, d=10, θ=45°, r=0.07 → H=10×cos45≈7.071
    # L = 5000 × 0.07 / (7.071²) ≈ 7.0
    I, d, theta, r_f = 5000.0, 10.0, 45.0, 0.07
    H = d * math.cos(math.radians(theta))
    expected = I * r_f / (H ** 2)
    r = road_luminance(I, d, theta, r_f)
    assert r["ok"] is True
    assert abs(r["luminance_cd_m2"] - expected) < 1e-4


def test_road_luminance_invalid_90deg():
    r = road_luminance(5000.0, 10.0, 90.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 16. pole_spacing
# ---------------------------------------------------------------------------

def test_pole_spacing_basic():
    # spacing = 3.0 × 10 = 30 m
    r = pole_spacing(10.0, 3.0)
    assert r["ok"] is True
    assert abs(r["spacing_m"] - 30.0) < 1e-6


def test_pole_spacing_default_ratio():
    r = pole_spacing(8.0)
    assert r["ok"] is True
    assert abs(r["spacing_m"] - 24.0) < 1e-6


# ---------------------------------------------------------------------------
# 17. roadway_utilization
# ---------------------------------------------------------------------------

def test_roadway_utilization_basic():
    # E = 15000 × 0.4 / (7 × 30) = 6000 / 210 ≈ 28.57 lx
    r = roadway_utilization(15000.0, 0.4, 7.0, 30.0, 10.0)
    assert r["ok"] is True
    expected_lux = 15000 * 0.4 / (7.0 * 30.0)
    assert abs(r["avg_road_lux"] - expected_lux) < 0.01
    # L ≈ E × 0.07
    assert abs(r["avg_road_luminance_cd_m2"] - expected_lux * 0.07) < 0.001


# ---------------------------------------------------------------------------
# 18. emergency_lux_at_floor
# ---------------------------------------------------------------------------

def test_emergency_lux_nadir():
    # E = I / d² = 100 / 4 = 25 lx
    r = emergency_lux_at_floor(100.0, 2.0)
    assert r["ok"] is True
    assert abs(r["e_floor_lux"] - 25.0) < 1e-4


def test_emergency_lux_warning_below_1():
    # E = 0.5 / 4 = 0.125 lx < 1.0 → warning
    r = emergency_lux_at_floor(0.5, 2.0)
    assert r["ok"] is True
    assert any("under-lit" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# 19. emergency_spacing
# ---------------------------------------------------------------------------

def test_emergency_spacing_basic():
    # E_mid = I / (h² + (s/2)²) = 1 → s = 2×sqrt(I - h²)
    # I=100, h=2.5, s = 2×sqrt(100-6.25)=2×sqrt(93.75)≈19.36 m
    r = emergency_spacing(2.5, 1.0, 100.0)
    assert r["ok"] is True
    expected = 2.0 * math.sqrt(100.0 - 2.5 ** 2)
    assert abs(r["max_spacing_m"] - expected) < 0.01


def test_emergency_spacing_under_lit():
    # h=5 m, I=10 cd, E_target=1 lx → I/E=10 < h²=25 → zero spacing
    r = emergency_spacing(5.0, 1.0, 10.0)
    assert r["ok"] is True
    assert r["max_spacing_m"] == 0.0
    assert any("under-lit" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# 20. lamp_lumens_per_watt
# ---------------------------------------------------------------------------

def test_lamp_lpw_led():
    r = lamp_lumens_per_watt("led_standard")
    assert r["ok"] is True
    assert r["lumens_per_watt"] == 100.0


def test_lamp_lpw_incandescent():
    r = lamp_lumens_per_watt("incandescent")
    assert r["ok"] is True
    assert r["lumens_per_watt"] == 15.0


def test_lamp_lpw_unknown():
    r = lamp_lumens_per_watt("plasma_arc")
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 21. lamp_energy
# ---------------------------------------------------------------------------

def test_lamp_energy_basic():
    # 100 W × 8760 h = 876 000 Wh = 876 kWh
    r = lamp_energy(100.0, 8760.0)
    assert r["ok"] is True
    assert abs(r["energy_Wh"] - 876000.0) < 0.1
    assert abs(r["energy_kWh"] - 876.0) < 0.001


def test_lamp_energy_invalid():
    r = lamp_energy(0.0, 100.0)
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 22. lpd_check
# ---------------------------------------------------------------------------

def test_lpd_compliant():
    # 1000 W / 100 m² = 10.0 W/m² ≤ ASHRAE office 10.8 W/m²
    r = lpd_check(1000.0, 100.0, "office", "ASHRAE")
    assert r["ok"] is True
    assert r["compliant"] is True
    assert r["warnings"] == []


def test_lpd_non_compliant():
    # 2000 W / 100 m² = 20.0 W/m² > ASHRAE office 10.8 W/m²
    r = lpd_check(2000.0, 100.0, "office", "ASHRAE")
    assert r["ok"] is True
    assert r["compliant"] is False
    assert any("LPD-over-allowance" in w for w in r["warnings"])


def test_lpd_title24_warehouse():
    # Title-24 warehouse allowance = 6.9 W/m²
    r = lpd_check(500.0, 100.0, "warehouse", "Title24")
    assert r["ok"] is True
    assert r["allowance_W_m2"] == 6.9


def test_lpd_unknown_building():
    r = lpd_check(1000.0, 100.0, "underwater_cave", "ASHRAE")
    assert r["ok"] is False


# ---------------------------------------------------------------------------
# 23. LLM tool wrappers — happy path
# ---------------------------------------------------------------------------

def test_tool_rcr_happy():
    raw = _run(run_lighting_room_cavity_ratio(
        _ctx(), _args(length_m=10.0, width_m=10.0, height_cavity_m=2.4)
    ))
    d = _ok_tool(raw)
    assert abs(d["rcr"] - 2.4) < 0.01


def test_tool_cu_happy():
    raw = _run(run_lighting_cu(
        _ctx(), _args(rcr=5.0, rho_ceiling_pct=70, rho_walls_pct=50)
    ))
    d = _ok_tool(raw)
    assert "cu" in d


def test_tool_llf_defaults():
    raw = _run(run_lighting_llf(_ctx(), _args()))
    d = _ok_tool(raw)
    assert abs(d["llf"] - 0.765) < 0.001


def test_tool_n_luminaires_happy():
    raw = _run(run_lighting_n_luminaires(
        _ctx(), _args(area_m2=100.0, target_lux=500.0,
                      lumens_per_lamp=3200.0, cu=0.65, llf=0.80)
    ))
    d = _ok_tool(raw)
    assert d["n_luminaires"] >= 1


def test_tool_eh_happy():
    raw = _run(run_lighting_eh(
        _ctx(), _args(intensity_cd=1000.0, distance_m=2.0)
    ))
    d = _ok_tool(raw)
    assert abs(d["e_horizontal_lux"] - 250.0) < 0.01


def test_tool_lpd_happy():
    raw = _run(run_lighting_lpd(
        _ctx(), _args(total_watts=1000.0, area_m2=100.0,
                      building_type="office", standard="ASHRAE")
    ))
    d = _ok_tool(raw)
    assert d["compliant"] is True


# ---------------------------------------------------------------------------
# 24. LLM tool wrappers — error paths
# ---------------------------------------------------------------------------

def test_tool_rcr_missing_param():
    raw = _run(run_lighting_room_cavity_ratio(
        _ctx(), _args(length_m=10.0, width_m=10.0)
    ))
    _err_tool(raw)


def test_tool_eh_invalid_json():
    raw = _run(run_lighting_eh(_ctx(), b"not json"))
    _err_tool(raw)


def test_tool_ugr_missing_param():
    raw = _run(run_lighting_ugr(
        _ctx(), _args(
            background_luminance_cd_m2=30.0,
            luminaire_luminances_cd_m2=[1000.0],
            solid_angles_sr=[0.001],
        )
    ))
    _err_tool(raw)


def test_tool_lamp_lpw_unknown():
    raw = _run(run_lighting_lamp_lpw(_ctx(), _args(lamp_type="fusion")))
    _err_tool(raw)


def test_tool_emergency_spacing_happy():
    raw = _run(run_lighting_emergency_spacing(
        _ctx(), _args(mounting_height_m=3.0, min_lux_target=1.0, intensity_cd=100.0)
    ))
    d = _ok_tool(raw)
    assert d["max_spacing_m"] > 0


def test_tool_roadway_util_happy():
    raw = _run(run_lighting_roadway_util(
        _ctx(), _args(
            luminaire_lumens=15000.0,
            utilization_factor=0.4,
            road_width_m=7.0,
            spacing_m=30.0,
            mounting_height_m=10.0,
        )
    ))
    d = _ok_tool(raw)
    assert d["avg_road_lux"] > 0
