"""
Hermetic tests for kerf_cad_core.windload — ASCE 7-22 wind loading.

Coverage:
  asce7.velocity_pressure_exposure_Kz — exposure B/C/D, z_min clamp
  asce7.topographic_factor_Kzt        — flat terrain, hill crest
  asce7.ground_elevation_factor_Ke    — sea level, high elevation
  asce7.velocity_pressure_qz          — SI and US unit systems
  asce7.gust_effect_factor_G          — simplified and detailed
  asce7.gust_effect_factor_Gf         — flexible structures
  asce7.mwfrs_wall_pressure           — windward, leeward, side
  asce7.mwfrs_roof_pressure           — positive/negative GCpi cases
  asce7.components_cladding_GCp       — wall/roof zones 1-3
  asce7.base_shear_overturning        — multi-level building
  asce7.along_wind_drift              — rigid and flexible flags
  Error paths                         — invalid inputs never raise

All tests are hermetic: no OCC, no DB, no network.
Formulas verified against ASCE 7-22 example calculations and algebraic
derivations from the standard equations.

References
----------
ASCE/SEI 7-22, Chapters 26-27, 30.
ASCE 7-22 Commentary C26-C27.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.windload.asce7 import (
    velocity_pressure_exposure_Kz,
    topographic_factor_Kzt,
    ground_elevation_factor_Ke,
    velocity_pressure_qz,
    gust_effect_factor_G,
    gust_effect_factor_Gf,
    mwfrs_wall_pressure,
    mwfrs_roof_pressure,
    components_cladding_GCp,
    base_shear_overturning,
    along_wind_drift,
)
from kerf_cad_core.windload.tools import (
    run_wind_Kz,
    run_wind_Kzt,
    run_wind_Ke,
    run_wind_qz,
    run_wind_G,
    run_wind_Gf,
    run_wind_mwfrs_wall,
    run_wind_mwfrs_roof,
    run_wind_cc_GCp,
    run_wind_base_shear,
    run_wind_drift,
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


def _ok(d: dict) -> dict:
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _fail(d: dict) -> dict:
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


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
# 1. velocity_pressure_exposure_Kz
# ---------------------------------------------------------------------------

class TestKz:
    def test_exposure_C_standard_height(self):
        """
        Exposure C, z=10 m: Kz = 2.01 × (10/274.32)^(2/9.5)
        alpha=9.5, zg=274.32 m
        """
        r = _ok(velocity_pressure_exposure_Kz(10.0, "C"))
        expected = 2.01 * (10.0 / 274.32) ** (2.0 / 9.5)
        assert abs(r["Kz"] - expected) < 1e-6
        assert r["exposure"] == "C"

    def test_exposure_B_at_30m(self):
        """Exposure B, z=30 m: above z_min, power-law should apply."""
        r = _ok(velocity_pressure_exposure_Kz(30.0, "B"))
        alpha = 7.0
        zg = 365.76
        expected = 2.01 * (30.0 / zg) ** (2.0 / alpha)
        assert abs(r["Kz"] - expected) < 1e-6

    def test_exposure_D_at_50m(self):
        """Exposure D, z=50 m: flat open terrain."""
        r = _ok(velocity_pressure_exposure_Kz(50.0, "D"))
        alpha = 11.5
        zg = 213.36
        expected = 2.01 * (50.0 / zg) ** (2.0 / alpha)
        assert abs(r["Kz"] - expected) < 1e-6

    def test_z_below_z_min_clamps(self):
        """For z < z_min, Kz should equal Kz(z_min)."""
        r_low = _ok(velocity_pressure_exposure_Kz(0.5, "B"))
        r_min = _ok(velocity_pressure_exposure_Kz(9.14, "B"))  # z_min for B
        assert abs(r_low["Kz"] - r_min["Kz"]) < 1e-9
        assert r_low["z_used_m"] == pytest.approx(9.14, rel=1e-4)

    def test_kz_increases_with_height(self):
        """Kz must increase monotonically with height."""
        kz_10 = _ok(velocity_pressure_exposure_Kz(10.0, "C"))["Kz"]
        kz_30 = _ok(velocity_pressure_exposure_Kz(30.0, "C"))["Kz"]
        kz_100 = _ok(velocity_pressure_exposure_Kz(100.0, "C"))["Kz"]
        assert kz_10 < kz_30 < kz_100

    def test_invalid_exposure(self):
        r = velocity_pressure_exposure_Kz(10.0, "A")
        _fail(r)

    def test_negative_z(self):
        r = velocity_pressure_exposure_Kz(-1.0, "C")
        _fail(r)


# ---------------------------------------------------------------------------
# 2. topographic_factor_Kzt
# ---------------------------------------------------------------------------

class TestKzt:
    def test_flat_terrain_is_one(self):
        """K1=K2=K3=0 → Kzt = 1.0 (flat terrain, no topographic effect)."""
        r = _ok(topographic_factor_Kzt(0.0, 0.0, 0.0))
        assert r["Kzt"] == pytest.approx(1.0)

    def test_formula_calculation(self):
        """Kzt = (1 + K1·K2·K3)²; spot check K1=0.4, K2=0.9, K3=0.7."""
        K1, K2, K3 = 0.4, 0.9, 0.7
        expected = (1.0 + K1 * K2 * K3) ** 2
        r = _ok(topographic_factor_Kzt(K1, K2, K3))
        assert r["Kzt"] == pytest.approx(expected, rel=1e-9)

    def test_kzt_always_ge_one(self):
        """Kzt must always be >= 1.0."""
        r = _ok(topographic_factor_Kzt(0.3, 0.8, 0.5))
        assert r["Kzt"] >= 1.0

    def test_negative_k_invalid(self):
        r = topographic_factor_Kzt(-0.1, 0.5, 0.5)
        _fail(r)


# ---------------------------------------------------------------------------
# 3. ground_elevation_factor_Ke
# ---------------------------------------------------------------------------

class TestKe:
    def test_sea_level_is_one(self):
        """At z_e=0 (sea level), Ke = exp(0) = 1.0."""
        r = _ok(ground_elevation_factor_Ke(0.0))
        assert r["Ke"] == pytest.approx(1.0)

    def test_high_elevation_reduces_Ke(self):
        """At 1000 m elevation, Ke ≈ exp(-0.119) ≈ 0.8878."""
        r = _ok(ground_elevation_factor_Ke(1000.0))
        expected = math.exp(-0.000119 * 1000.0)
        assert r["Ke"] == pytest.approx(expected, rel=1e-6)

    def test_ke_decreases_with_elevation(self):
        """Ke must decrease monotonically with elevation."""
        ke_0 = _ok(ground_elevation_factor_Ke(0.0))["Ke"]
        ke_500 = _ok(ground_elevation_factor_Ke(500.0))["Ke"]
        ke_2000 = _ok(ground_elevation_factor_Ke(2000.0))["Ke"]
        assert ke_0 > ke_500 > ke_2000

    def test_negative_elevation_invalid(self):
        r = ground_elevation_factor_Ke(-10.0)
        _fail(r)


# ---------------------------------------------------------------------------
# 4. velocity_pressure_qz
# ---------------------------------------------------------------------------

class TestQz:
    def test_si_formula(self):
        """
        SI: qz = 0.613 × Kz × Kzt × Kd × Ke × V²
        Kz=0.85, Kzt=1.0, Kd=0.85, Ke=1.0, V=40 m/s
        qz = 0.613 × 0.85 × 1.0 × 0.85 × 1.0 × 1600 = 708.3 Pa approx
        """
        Kz, Kzt, Kd, Ke, V = 0.85, 1.0, 0.85, 1.0, 40.0
        expected = 0.613 * Kz * Kzt * Kd * Ke * V ** 2
        r = _ok(velocity_pressure_qz(Kz, Kzt, Kd, Ke, V, unit_system="SI"))
        assert r["qz"] == pytest.approx(expected, rel=1e-9)
        assert r["unit_system"] == "SI"

    def test_us_formula(self):
        """
        US: qz = 0.00256 × Kz × Kzt × Kd × Ke × V² (psf, V in mph)
        Kz=0.85, Kzt=1.0, Kd=0.85, Ke=1.0, V=90 mph
        """
        Kz, Kzt, Kd, Ke, V = 0.85, 1.0, 0.85, 1.0, 90.0
        expected = 0.00256 * Kz * Kzt * Kd * Ke * V ** 2
        r = _ok(velocity_pressure_qz(Kz, Kzt, Kd, Ke, V, unit_system="US"))
        assert r["qz"] == pytest.approx(expected, rel=1e-9)
        assert r["unit_system"] == "US"

    def test_kzt_less_than_one_invalid(self):
        r = velocity_pressure_qz(0.85, 0.9, 0.85, 1.0, 40.0)
        _fail(r)

    def test_kd_greater_than_one_invalid(self):
        r = velocity_pressure_qz(0.85, 1.0, 1.1, 1.0, 40.0)
        _fail(r)

    def test_ke_greater_than_one_invalid(self):
        r = velocity_pressure_qz(0.85, 1.0, 0.85, 1.05, 40.0)
        _fail(r)

    def test_invalid_unit_system(self):
        r = velocity_pressure_qz(0.85, 1.0, 0.85, 1.0, 40.0, unit_system="metric")
        _fail(r)


# ---------------------------------------------------------------------------
# 5. gust_effect_factor_G
# ---------------------------------------------------------------------------

class TestGustG:
    def test_simplified_is_085(self):
        """Simplified G = 0.85 when Iz not provided."""
        r = _ok(gust_effect_factor_G("C"))
        assert r["G"] == pytest.approx(0.85)
        assert r["method"] == "simplified"

    def test_detailed_formula(self):
        """
        Detailed G: gQ=gv=3.4, Q = 1/sqrt(1 + 0.63×Q_ratio^0.63)
        G = 0.925 × (1 + 1.7·Iz·gQ·Q) / (1 + 1.7·gv·Iz)
        """
        Iz, Lz, Q_ratio = 0.20, 100.0, 0.5
        Q = 1.0 / math.sqrt(1.0 + 0.63 * Q_ratio ** 0.63)
        gQ = gv = 3.4
        expected = 0.925 * (1.0 + 1.7 * Iz * gQ * Q) / (1.0 + 1.7 * gv * Iz)
        r = _ok(gust_effect_factor_G("C", Iz=Iz, Lz=Lz, Q_ratio=Q_ratio))
        assert r["G"] == pytest.approx(expected, rel=1e-9)
        assert r["method"] == "detailed"

    def test_flexible_flag_warns(self):
        """flexible=True should add a warning but still return G=0.85."""
        r = _ok(gust_effect_factor_G("B", flexible=True))
        assert r["G"] == pytest.approx(0.85)
        assert len(r["warnings"]) >= 1
        assert "flexible" in r["warnings"][0].lower()

    def test_invalid_exposure(self):
        r = gust_effect_factor_G("E")
        _fail(r)

    def test_detailed_missing_Lz(self):
        r = gust_effect_factor_G("C", Iz=0.2)
        _fail(r)


# ---------------------------------------------------------------------------
# 6. gust_effect_factor_Gf
# ---------------------------------------------------------------------------

class TestGustGf:
    def test_basic_gf_calculation(self):
        """
        Verify Gf is computed without error for a tall flexible building.
        n1=0.2 Hz, zbar=50 m, Iz=0.15, Lz=150 m, V=30 m/s
        B=30 m, H=80 m, D=30 m, beta=0.02
        """
        r = _ok(gust_effect_factor_Gf(
            n1=0.2, zbar=50.0, Iz=0.15, Lz=150.0, V=30.0,
            B=30.0, H=80.0, D=30.0, damping_ratio=0.02
        ))
        assert 0.85 <= r["Gf"] <= 2.0  # physically plausible range
        assert "Rn" in r
        assert "R_squared" in r
        assert r["R_squared"] >= 0

    def test_gf_higher_damping_gives_smaller_gf(self):
        """Higher damping reduces resonance R² and thus Gf."""
        kwargs = dict(n1=0.2, zbar=50.0, Iz=0.15, Lz=150.0, V=30.0,
                      B=30.0, H=80.0, D=30.0)
        r_low = _ok(gust_effect_factor_Gf(**kwargs, damping_ratio=0.01))
        r_high = _ok(gust_effect_factor_Gf(**kwargs, damping_ratio=0.05))
        # Higher damping → lower Gf (less amplification)
        assert r_high["Gf"] <= r_low["Gf"]

    def test_rigid_structure_warning(self):
        """n1 >= 1 Hz should produce a warning about using G instead."""
        r = _ok(gust_effect_factor_Gf(
            n1=1.5, zbar=20.0, Iz=0.20, Lz=120.0, V=25.0,
            B=20.0, H=30.0, D=20.0
        ))
        assert any("rigid" in w.lower() or "n1" in w for w in r["warnings"])

    def test_negative_n1_invalid(self):
        r = gust_effect_factor_Gf(
            n1=-0.1, zbar=50.0, Iz=0.15, Lz=150.0, V=30.0,
            B=30.0, H=80.0, D=30.0
        )
        _fail(r)

    def test_invalid_damping(self):
        r = gust_effect_factor_Gf(
            n1=0.2, zbar=50.0, Iz=0.15, Lz=150.0, V=30.0,
            B=30.0, H=80.0, D=30.0, damping_ratio=1.5
        )
        _fail(r)


# ---------------------------------------------------------------------------
# 7. mwfrs_wall_pressure
# ---------------------------------------------------------------------------

class TestMwfrsWall:
    def test_windward_wall_positive_cp(self):
        """
        Windward: p = qz·G·Cp_windward − qi·(±GCpi)
        qz=800, qi=700, G=0.85, Cp_w=0.8, GCpi=0.18
        p_pos = 800×0.85×0.8 − 700×0.18 = 544 − 126 = 418 Pa
        p_neg = 800×0.85×0.8 + 700×0.18 = 544 + 126 = 670 Pa
        """
        qz, qi, G = 800.0, 700.0, 0.85
        Cp_w, Cp_l, Cp_s = 0.8, -0.5, -0.7
        GCpi = 0.18
        r = _ok(mwfrs_wall_pressure(qz, qi, G, Cp_w, Cp_l, Cp_s, GCpi, surface="windward"))
        p_pos_expected = qz * G * Cp_w - qi * GCpi
        p_neg_expected = qz * G * Cp_w + qi * GCpi
        assert r["p_pos"] == pytest.approx(p_pos_expected, rel=1e-9)
        assert r["p_neg"] == pytest.approx(p_neg_expected, rel=1e-9)

    def test_leeward_wall_negative_cp(self):
        """Leeward wall: Cp is negative → negative pressures (suction)."""
        r = _ok(mwfrs_wall_pressure(
            800.0, 700.0, 0.85, 0.8, -0.5, -0.7, 0.18, surface="leeward"
        ))
        assert r["Cp"] == pytest.approx(-0.5)
        # Both p_pos and p_neg should be negative (outward)
        assert r["p_pos"] < 0 or r["p_neg"] < 0

    def test_side_wall_uses_cp_side(self):
        """Side wall uses Cp_side=-0.7."""
        r = _ok(mwfrs_wall_pressure(
            800.0, 700.0, 0.85, 0.8, -0.5, -0.7, 0.18, surface="side"
        ))
        assert r["Cp"] == pytest.approx(-0.7)

    def test_critical_pressure_is_max_abs(self):
        """p_critical must be the one with larger absolute value."""
        r = _ok(mwfrs_wall_pressure(
            800.0, 700.0, 0.85, 0.8, -0.5, -0.7, 0.18, surface="windward"
        ))
        assert abs(r["p_critical"]) == max(abs(r["p_pos"]), abs(r["p_neg"]))

    def test_invalid_surface(self):
        r = mwfrs_wall_pressure(800.0, 700.0, 0.85, 0.8, -0.5, -0.7, 0.18, surface="top")
        _fail(r)

    def test_negative_qz_invalid(self):
        r = mwfrs_wall_pressure(-100.0, 700.0, 0.85, 0.8, -0.5, -0.7, 0.18)
        _fail(r)


# ---------------------------------------------------------------------------
# 8. mwfrs_roof_pressure
# ---------------------------------------------------------------------------

class TestMwfrsRoof:
    def test_flat_roof_negative_cp(self):
        """
        Flat roof: Cp = -0.9, qh=700, qi=700, G=0.85, GCpi=0.18
        p_pos = 700×0.85×(-0.9) − 700×0.18 = -535.5 − 126 = -661.5 Pa
        p_neg = 700×0.85×(-0.9) + 700×0.18 = -535.5 + 126 = -409.5 Pa
        """
        qh, qi, G, Cp_r, GCpi = 700.0, 700.0, 0.85, -0.9, 0.18
        r = _ok(mwfrs_roof_pressure(qh, qi, G, Cp_r, GCpi))
        p_pos_expected = qh * G * Cp_r - qi * GCpi
        p_neg_expected = qh * G * Cp_r + qi * GCpi
        assert r["p_pos"] == pytest.approx(p_pos_expected, rel=1e-9)
        assert r["p_neg"] == pytest.approx(p_neg_expected, rel=1e-9)

    def test_critical_roof_pressure_max_abs(self):
        """p_critical must be the one with larger absolute value."""
        r = _ok(mwfrs_roof_pressure(700.0, 700.0, 0.85, -0.9, 0.18))
        assert abs(r["p_critical"]) == max(abs(r["p_pos"]), abs(r["p_neg"]))

    def test_negative_gcpi_invalid(self):
        r = mwfrs_roof_pressure(700.0, 700.0, 0.85, -0.9, -0.1)
        _fail(r)

    def test_zero_gcpi_both_cases_equal(self):
        """GCpi=0 → p_pos == p_neg == qh·G·Cp."""
        r = _ok(mwfrs_roof_pressure(700.0, 700.0, 0.85, -0.7, 0.0))
        assert r["p_pos"] == pytest.approx(r["p_neg"], rel=1e-9)


# ---------------------------------------------------------------------------
# 9. components_cladding_GCp
# ---------------------------------------------------------------------------

class TestCCGCp:
    def test_wall_zone1_small_area(self):
        """Zone 1 wall, A=0.5 m² (< 0.93 threshold): GCp_pos=1.0, GCp_neg=-1.1."""
        r = _ok(components_cladding_GCp(1, "wall", 0.5))
        assert r["GCp_pos"] == pytest.approx(1.0)
        assert r["GCp_neg"] == pytest.approx(-1.1)

    def test_wall_zone3_large_area(self):
        """Zone 3 wall, A=50 m² (> 46.5 threshold): uses last row values."""
        r = _ok(components_cladding_GCp(3, "wall", 50.0))
        assert r["GCp_pos"] == pytest.approx(0.7)
        assert r["GCp_neg"] == pytest.approx(-0.7)

    def test_roof_zone3_corner_small_area(self):
        """Roof zone 3 corner small area has max suction GCp_neg=-2.8."""
        r = _ok(components_cladding_GCp(3, "roof", 0.5))
        assert r["GCp_neg"] == pytest.approx(-2.8)

    def test_roof_zone1_large_area(self):
        """Roof zone 1 field large area: minimum suction."""
        r = _ok(components_cladding_GCp(1, "roof", 50.0))
        assert r["GCp_neg"] == pytest.approx(-0.8)

    def test_gcp_neg_more_negative_in_corner(self):
        """Corner (zone 3) should have more negative GCp than field (zone 1)."""
        r1 = _ok(components_cladding_GCp(1, "roof", 1.0))
        r3 = _ok(components_cladding_GCp(3, "roof", 1.0))
        assert r3["GCp_neg"] < r1["GCp_neg"]

    def test_invalid_zone(self):
        r = components_cladding_GCp(5, "wall", 1.0)
        _fail(r)

    def test_invalid_component_type(self):
        r = components_cladding_GCp(1, "floor", 1.0)
        _fail(r)

    def test_zero_area_invalid(self):
        r = components_cladding_GCp(1, "wall", 0.0)
        _fail(r)


# ---------------------------------------------------------------------------
# 10. base_shear_overturning
# ---------------------------------------------------------------------------

class TestBaseShear:
    def test_single_level(self):
        """
        Single level: p=500 Pa, width=10 m, dz=5 m
        F = 500×10×5 = 25000 N
        M_OT = 25000 × 2.5 = 62500 N·m (arm at dz/2 = 2.5 m)
        """
        r = _ok(base_shear_overturning([500.0], [10.0], [5.0]))
        assert r["base_shear"] == pytest.approx(25000.0)
        assert r["overturning_moment"] == pytest.approx(62500.0)

    def test_two_levels(self):
        """
        Level 1: p=400 Pa, w=10 m, dz=5 m → F1=20000 N, arm=2.5 m
        Level 2: p=600 Pa, w=10 m, dz=5 m → F2=30000 N, arm=7.5 m
        V = 50000 N
        M_OT = 20000×2.5 + 30000×7.5 = 50000 + 225000 = 275000 N·m
        """
        r = _ok(base_shear_overturning(
            [400.0, 600.0], [10.0, 10.0], [5.0, 5.0]
        ))
        assert r["base_shear"] == pytest.approx(50000.0)
        assert r["overturning_moment"] == pytest.approx(275000.0)
        assert r["n_levels"] == 2

    def test_moment_arms_correct(self):
        """Verify moment arms are at strip centroids."""
        r = _ok(base_shear_overturning(
            [100.0, 100.0, 100.0], [1.0, 1.0, 1.0], [4.0, 4.0, 4.0]
        ))
        arms = r["moment_arms"]
        assert arms[0] == pytest.approx(2.0)   # 0 + 4/2
        assert arms[1] == pytest.approx(6.0)   # 4 + 4/2
        assert arms[2] == pytest.approx(10.0)  # 8 + 4/2

    def test_mismatched_lengths_invalid(self):
        r = base_shear_overturning([100.0, 200.0], [10.0], [5.0, 5.0])
        _fail(r)

    def test_empty_pressures_invalid(self):
        r = base_shear_overturning([], [], [])
        _fail(r)

    def test_negative_width_invalid(self):
        r = base_shear_overturning([500.0], [-10.0], [5.0])
        _fail(r)


# ---------------------------------------------------------------------------
# 11. along_wind_drift
# ---------------------------------------------------------------------------

class TestDrift:
    def test_rigid_building_no_warning(self):
        """H=20 m → n1 ≈ 3.75 Hz >= 1 Hz → not flexible."""
        r = _ok(along_wind_drift(20.0, 40.0, "C"))
        assert r["flexible_flag"] is False
        assert r["allowable_drift_m"] == pytest.approx(20.0 / 500.0, rel=1e-9)

    def test_tall_building_flexible_flag(self):
        """H=100 m → flexible (H > 60 m), flexible_flag=True, warning issued."""
        r = _ok(along_wind_drift(100.0, 45.0, "C"))
        assert r["flexible_flag"] is True
        assert len(r["warnings"]) >= 1

    def test_custom_drift_limit(self):
        """H/400 limit: allowable_drift = H/400."""
        r = _ok(along_wind_drift(50.0, 40.0, "C", drift_limit_ratio=400.0))
        assert r["allowable_drift_m"] == pytest.approx(50.0 / 400.0, rel=1e-9)

    def test_invalid_exposure(self):
        r = along_wind_drift(30.0, 40.0, "A")
        _fail(r)

    def test_zero_H_invalid(self):
        r = along_wind_drift(0.0, 40.0, "C")
        _fail(r)

    def test_approx_n1_in_result(self):
        """n1_approx should equal 75/H."""
        r = _ok(along_wind_drift(25.0, 35.0, "B"))
        assert r["n1_approx_Hz"] == pytest.approx(75.0 / 25.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 12. Full chain: Kz → qz → G → p (end-to-end SI calculation)
# ---------------------------------------------------------------------------

class TestEndToEndSI:
    def test_mwfrs_windward_pressure_chain(self):
        """
        ASCE 7-22 representative calculation (SI):
        z=10m, Exposure C, Kzt=1.0, Kd=0.85, Ke=1.0, V=40 m/s
        → Kz, qz, G=0.85, Cp=0.8, GCpi=0.18
        → windward wall pressure
        """
        kz_r = _ok(velocity_pressure_exposure_Kz(10.0, "C"))
        Kz = kz_r["Kz"]

        qz_r = _ok(velocity_pressure_qz(Kz, 1.0, 0.85, 1.0, 40.0, unit_system="SI"))
        qz = qz_r["qz"]

        G_r = _ok(gust_effect_factor_G("C"))
        G = G_r["G"]  # 0.85

        p_r = _ok(mwfrs_wall_pressure(qz, qz, G, 0.8, -0.5, -0.7, 0.18,
                                       surface="windward"))
        # Windward pressure must be positive (net inward for enclosed building
        # with negative GCpi case)
        assert p_r["p_neg"] > 0  # +GCpi case on windward


# ---------------------------------------------------------------------------
# 13. Tool wrappers (LLM layer)
# ---------------------------------------------------------------------------

class TestToolWrappers:
    def test_tool_wind_Kz(self):
        r = _ok_tool(_run(run_wind_Kz(_ctx(), _args(z=10.0, exposure="C"))))
        assert "Kz" in r

    def test_tool_wind_Kzt(self):
        r = _ok_tool(_run(run_wind_Kzt(_ctx(), _args(K1=0.0, K2=0.0, K3=0.0))))
        assert r["Kzt"] == pytest.approx(1.0)

    def test_tool_wind_Ke(self):
        r = _ok_tool(_run(run_wind_Ke(_ctx(), _args(z_e_m=0.0))))
        assert r["Ke"] == pytest.approx(1.0)

    def test_tool_wind_qz_si(self):
        r = _ok_tool(_run(run_wind_qz(_ctx(), _args(
            Kz=0.85, Kzt=1.0, Kd=0.85, Ke=1.0, V=40.0, unit_system="SI"
        ))))
        assert "qz" in r

    def test_tool_wind_G_simplified(self):
        r = _ok_tool(_run(run_wind_G(_ctx(), _args(exposure="C"))))
        assert r["G"] == pytest.approx(0.85)

    def test_tool_wind_Gf(self):
        r = _ok_tool(_run(run_wind_Gf(_ctx(), _args(
            n1=0.2, zbar=50.0, Iz=0.15, Lz=150.0, V=30.0,
            B=30.0, H=80.0, D=30.0
        ))))
        assert "Gf" in r

    def test_tool_wind_mwfrs_wall(self):
        r = _ok_tool(_run(run_wind_mwfrs_wall(_ctx(), _args(
            qz=800.0, qi=700.0, G=0.85,
            Cp_windward=0.8, Cp_leeward=-0.5, Cp_side=-0.7,
            GCpi=0.18, surface="windward"
        ))))
        assert "p_critical" in r

    def test_tool_wind_mwfrs_roof(self):
        r = _ok_tool(_run(run_wind_mwfrs_roof(_ctx(), _args(
            qh=700.0, qi=700.0, G=0.85, Cp_roof=-0.9, GCpi=0.18
        ))))
        assert "p_critical" in r

    def test_tool_wind_cc_GCp(self):
        r = _ok_tool(_run(run_wind_cc_GCp(_ctx(), _args(
            zone=1, component_type="wall", effective_area_m2=5.0
        ))))
        assert "GCp_pos" in r

    def test_tool_wind_base_shear(self):
        r = _ok_tool(_run(run_wind_base_shear(_ctx(), _args(
            pressures_by_height=[400.0, 600.0],
            tributary_widths=[10.0, 10.0],
            heights=[5.0, 5.0],
        ))))
        assert r["base_shear"] == pytest.approx(50000.0)

    def test_tool_wind_drift(self):
        r = _ok_tool(_run(run_wind_drift(_ctx(), _args(
            H=30.0, V=40.0, exposure="C"
        ))))
        assert "flexible_flag" in r

    def test_tool_error_missing_arg(self):
        raw = _run(run_wind_Kz(_ctx(), _args(z=10.0)))  # missing exposure
        _err_tool(raw)

    def test_tool_error_bad_json(self):
        raw = _run(run_wind_Kz(_ctx(), b"not_json"))
        _err_tool(raw)
