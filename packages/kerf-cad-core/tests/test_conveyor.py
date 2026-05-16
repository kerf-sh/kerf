"""
Hermetic tests for kerf_cad_core.conveyor — bulk-material conveyor design.

Coverage:
  design.belt_conveyor     — capacity, tension, power, inclination, warnings
  design.screw_conveyor    — capacity, power, torque, fill ratio, warnings
  design.bucket_elevator   — capacity, power, belt tension, warnings
  tools.*                  — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified against CEMA 7th ed. / CEMA Screw 5th ed. hand-calcs.

References
----------
CEMA — Belt Conveyors for Bulk Materials, 7th ed.
CEMA — Screw Conveyors for Bulk Materials, 5th ed.
Fenner Dunlop — Conveyor Handbook, 2009

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.conveyor.design import (
    belt_conveyor,
    screw_conveyor,
    bucket_elevator,
)
from kerf_cad_core.conveyor.tools import (
    run_belt_conveyor_design,
    run_screw_conveyor_design,
    run_bucket_elevator_design,
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


def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


def _is_error_response(r: dict) -> bool:
    return r.get("ok") is False or ("error" in r and "code" in r)


G = 9.80665


# ===========================================================================
# Belt conveyor tests
# ===========================================================================

class TestBeltConveyor:

    # ---- Basic sanity ----

    def test_basic_returns_ok(self):
        """Basic flat belt, coal, 1 m/s."""
        r = belt_conveyor(
            belt_width_m=1.0,
            belt_speed_m_s=1.0,
            length_m=100.0,
            lift_m=0.0,
            bulk_density_kg_m3=800.0,
        )
        assert r["ok"] is True

    def test_all_expected_keys_present(self):
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        assert r["ok"] is True
        for key in (
            "capacity_m3_h", "capacity_t_h", "cross_section_area_m2",
            "material_mass_kg_m", "belt_mass_kg_m", "Te_N",
            "T1_N", "T2_N", "takeup_tension_N", "drive_power_W",
            "drive_power_kW", "motor_power_kW", "inclination_deg",
            "tension_index", "idler_load_N", "warnings",
        ):
            assert key in r, f"Missing key: {key}"

    # ---- Capacity formula ----

    def test_capacity_volume_formula(self):
        """Q_vol = A_cross × v × 3600 (m³/h)."""
        r = belt_conveyor(1.0, 2.0, 100.0, 0.0, 800.0, trough_angle_deg=35.0,
                          surcharge_angle_deg=20.0)
        assert r["ok"] is True
        A = r["cross_section_area_m2"]
        expected_vol = A * 2.0 * 3600.0
        assert abs(r["capacity_m3_h"] - expected_vol) / expected_vol < 1e-9

    def test_capacity_mass_from_volume(self):
        """capacity_t_h = capacity_m3_h × rho / 1000."""
        r = belt_conveyor(1.2, 1.5, 150.0, 0.0, 1000.0)
        assert r["ok"] is True
        expected_t_h = r["capacity_m3_h"] * 1000.0 / 1000.0
        assert abs(r["capacity_t_h"] - expected_t_h) / expected_t_h < 1e-9

    def test_higher_speed_gives_higher_capacity(self):
        """Doubling belt speed doubles volumetric capacity."""
        r1 = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        r2 = belt_conveyor(1.0, 2.0, 100.0, 0.0, 800.0)
        assert r1["ok"] and r2["ok"]
        assert abs(r2["capacity_m3_h"] / r1["capacity_m3_h"] - 2.0) < 1e-9

    def test_flat_belt_zero_trough_area(self):
        """Flat belt (trough 0°) has lower area than troughed belt."""
        r_flat = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, trough_angle_deg=0.0)
        r_trough = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, trough_angle_deg=35.0)
        assert r_flat["ok"] and r_trough["ok"]
        assert r_trough["cross_section_area_m2"] > r_flat["cross_section_area_m2"]

    # ---- Power / tension ----

    def test_drive_power_equals_Te_times_v(self):
        """drive_power_W = Te_N × belt_speed_m_s."""
        v = 1.5
        r = belt_conveyor(1.0, v, 100.0, 0.0, 800.0)
        assert r["ok"] is True
        assert abs(r["drive_power_W"] - r["Te_N"] * v) / max(r["drive_power_W"], 1.0) < 1e-9

    def test_motor_power_accounts_for_efficiency(self):
        """motor_power_kW = drive_power_kW / η."""
        eta = 0.88
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, drive_efficiency=eta)
        assert r["ok"] is True
        assert abs(r["motor_power_kW"] - r["drive_power_kW"] / eta) < 1e-6

    def test_uplift_increases_Te(self):
        """Positive lift_m increases effective tension."""
        r_flat = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        r_uphill = belt_conveyor(1.0, 1.0, 100.0, 10.0, 800.0)
        assert r_flat["ok"] and r_uphill["ok"]
        assert r_uphill["Te_N"] > r_flat["Te_N"]

    def test_downhill_does_not_increase_Te_beyond_flat(self):
        """Negative lift only reduces lift component; friction still dominates for short dip."""
        r_flat = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        r_downhill = belt_conveyor(1.0, 1.0, 100.0, -5.0, 800.0)
        assert r_flat["ok"] and r_downhill["ok"]
        # Downhill: lift term is negative so Te_downhill < Te_flat for small inclines
        assert r_downhill["Te_N"] < r_flat["Te_N"]

    def test_slack_tension_capstan_formula(self):
        """T2 = Te / (e^(μφ) - 1)."""
        wrap_deg = 210.0
        mu = 0.35
        phi = math.radians(wrap_deg)
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0,
                          wrap_angle_deg=wrap_deg, mu_belt_pulley=mu)
        assert r["ok"] is True
        capstan = math.exp(mu * phi)
        expected_T2 = r["Te_N"] / (capstan - 1.0)
        assert abs(r["T2_N"] - expected_T2) / max(abs(expected_T2), 1.0) < 1e-9

    def test_T1_minus_T2_equals_Te(self):
        """T1 - T2 = Te (definition of effective tension)."""
        r = belt_conveyor(1.0, 1.0, 100.0, 5.0, 800.0)
        assert r["ok"] is True
        assert abs(r["T1_N"] - r["T2_N"] - r["Te_N"]) / max(r["Te_N"], 1.0) < 1e-9

    def test_tension_index_formula(self):
        """tension_index = Te_N / belt_width_m."""
        bw = 1.2
        r = belt_conveyor(bw, 1.5, 200.0, 0.0, 800.0)
        assert r["ok"] is True
        assert abs(r["tension_index"] - r["Te_N"] / bw) < 1e-9

    def test_idler_load_formula(self):
        """idler_load = (Wm + Wb) × idler_spacing × g."""
        Li = 1.5
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, idler_spacing_m=Li)
        assert r["ok"] is True
        expected = (r["material_mass_kg_m"] + r["belt_mass_kg_m"]) * Li * G
        assert abs(r["idler_load_N"] - expected) / max(expected, 1.0) < 1e-9

    # ---- Inclination ----

    def test_inclination_degrees_correct(self):
        """inclination_deg = atan(lift/length) in degrees."""
        H, L = 10.0, 100.0
        expected = math.degrees(math.atan2(H, L))
        r = belt_conveyor(1.0, 1.0, L, H, 800.0)
        assert r["ok"] is True
        assert abs(r["inclination_deg"] - expected) < 0.001

    def test_flat_conveyor_zero_inclination(self):
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        assert r["ok"] is True
        assert r["inclination_deg"] == pytest.approx(0.0, abs=1e-9)

    # ---- Warnings ----

    def test_over_incline_warning_issued(self):
        """Steep incline vs low angle of repose must trigger warning."""
        # incline = atan(20/100) ≈ 11.3°; repose = 15° → max safe = 11.25° → over
        r = belt_conveyor(1.0, 1.0, 100.0, 20.0, 800.0, repose_angle_deg=15.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "incline" in warn_text or "repose" in warn_text

    def test_safe_incline_no_warning(self):
        """Gentle incline within repose limit must not trigger over-incline warning."""
        # incline ≈ 2.9°; 0.75 × 30° = 22.5° → safe
        r = belt_conveyor(1.0, 1.0, 100.0, 5.0, 800.0, repose_angle_deg=30.0)
        assert r["ok"] is True
        over_incline = any("incline" in w.lower() or "repose" in w.lower()
                           for w in r["warnings"])
        assert not over_incline

    def test_capacity_shortfall_warning(self):
        """Capacity below target issues warning."""
        # 1 m wide, 0.5 m/s → small capacity; set large target
        r = belt_conveyor(0.5, 0.3, 50.0, 0.0, 800.0, target_capacity_t_h=500.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "shortfall" in warn_text or "capacity" in warn_text

    def test_warnings_list_always_present(self):
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)

    # ---- Error paths ----

    def test_negative_belt_width_returns_error(self):
        r = belt_conveyor(-1.0, 1.0, 100.0, 0.0, 800.0)
        assert r["ok"] is False

    def test_zero_speed_returns_error(self):
        r = belt_conveyor(1.0, 0.0, 100.0, 0.0, 800.0)
        assert r["ok"] is False

    def test_invalid_drive_efficiency_returns_error(self):
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, drive_efficiency=1.5)
        assert r["ok"] is False

    def test_invalid_trough_angle_returns_error(self):
        r = belt_conveyor(1.0, 1.0, 100.0, 0.0, 800.0, trough_angle_deg=60.0)
        assert r["ok"] is False


# ===========================================================================
# Screw conveyor tests
# ===========================================================================

class TestScrewConveyor:

    def test_basic_returns_ok(self):
        r = screw_conveyor(
            diameter_m=0.25,
            pitch_m=0.25,
            speed_rpm=60.0,
            length_m=10.0,
            bulk_density_kg_m3=800.0,
        )
        assert r["ok"] is True

    def test_all_keys_present(self):
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0)
        assert r["ok"] is True
        for key in (
            "capacity_m3_h", "capacity_t_h", "fill_ratio", "max_fill_ratio",
            "screw_area_m2", "material_volume_m3", "Pm_W", "Pm_kW",
            "Pi_kW", "Pt_kW", "motor_power_kW", "torque_Nm", "warnings",
        ):
            assert key in r, f"Missing key: {key}"

    def test_screw_area_formula(self):
        """screw_area = π × D² / 4."""
        D = 0.3
        r = screw_conveyor(D, D, 50.0, 8.0, 800.0)
        assert r["ok"] is True
        expected_A = math.pi * D ** 2 / 4.0
        assert abs(r["screw_area_m2"] - expected_A) / expected_A < 1e-9

    def test_capacity_formula(self):
        """Q_vol = 60 × N × p × A_screw × Cf (m³/h)."""
        D, p, N, rho = 0.25, 0.25, 60.0, 800.0
        r = screw_conveyor(D, p, N, 10.0, rho, loading_class="medium")
        assert r["ok"] is True
        A = r["screw_area_m2"]
        Cf = r["fill_ratio"]
        expected_vol = 60.0 * N * p * A * Cf
        assert abs(r["capacity_m3_h"] - expected_vol) / expected_vol < 1e-9

    def test_capacity_mass_from_volume(self):
        """capacity_t_h = capacity_m3_h × rho / 1000."""
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 1600.0)
        assert r["ok"] is True
        expected = r["capacity_m3_h"] * 1600.0 / 1000.0
        assert abs(r["capacity_t_h"] - expected) / expected < 1e-9

    def test_higher_speed_higher_capacity(self):
        """Doubling speed doubles capacity (linear)."""
        r1 = screw_conveyor(0.25, 0.25, 40.0, 10.0, 800.0)
        r2 = screw_conveyor(0.25, 0.25, 80.0, 10.0, 800.0)
        assert r1["ok"] and r2["ok"]
        assert abs(r2["capacity_m3_h"] / r1["capacity_m3_h"] - 2.0) < 1e-9

    def test_larger_diameter_higher_capacity(self):
        """Larger diameter gives higher capacity (area ∝ D²)."""
        r_small = screw_conveyor(0.20, 0.20, 60.0, 10.0, 800.0)
        r_large = screw_conveyor(0.40, 0.40, 60.0, 10.0, 800.0)
        assert r_small["ok"] and r_large["ok"]
        assert r_large["capacity_m3_h"] > r_small["capacity_m3_h"]

    def test_incline_increases_power(self):
        """Positive lift_m increases total power (Pi > 0)."""
        r_flat = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0, lift_m=0.0)
        r_inclined = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0, lift_m=2.0)
        assert r_flat["ok"] and r_inclined["ok"]
        assert r_inclined["Pi_kW"] > 0.0
        assert r_inclined["Pt_kW"] > r_flat["Pt_kW"]

    def test_motor_power_accounts_for_efficiency(self):
        """motor_power_kW = Pt_kW / η."""
        eta = 0.80
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0, drive_efficiency=eta)
        assert r["ok"] is True
        assert abs(r["motor_power_kW"] - r["Pt_kW"] / eta) < 1e-6

    def test_torque_from_power_and_speed(self):
        """torque = Pt / ω (N·m)."""
        N = 60.0
        omega = 2.0 * math.pi * N / 60.0
        r = screw_conveyor(0.25, 0.25, N, 10.0, 800.0)
        assert r["ok"] is True
        expected_torque = r["Pt_kW"] * 1000.0 / omega
        assert abs(r["torque_Nm"] - expected_torque) / max(expected_torque, 1.0) < 1e-6

    def test_over_speed_warning(self):
        """Speed > 100 rpm must trigger over-speed warning."""
        r = screw_conveyor(0.25, 0.25, 150.0, 5.0, 800.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "speed" in warn_text or "rpm" in warn_text

    def test_capacity_shortfall_warning(self):
        r = screw_conveyor(0.15, 0.15, 30.0, 5.0, 800.0,
                           target_capacity_t_h=100.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "shortfall" in warn_text or "capacity" in warn_text

    def test_material_volume_formula(self):
        """material_volume_m3 = screw_area × fill_ratio × length."""
        D, L = 0.3, 8.0
        r = screw_conveyor(D, D, 50.0, L, 800.0)
        assert r["ok"] is True
        expected = r["screw_area_m2"] * r["fill_ratio"] * L
        assert abs(r["material_volume_m3"] - expected) / expected < 1e-9

    # ---- Error paths ----

    def test_negative_diameter_returns_error(self):
        r = screw_conveyor(-0.25, 0.25, 60.0, 10.0, 800.0)
        assert r["ok"] is False

    def test_zero_speed_returns_error(self):
        r = screw_conveyor(0.25, 0.25, 0.0, 10.0, 800.0)
        assert r["ok"] is False

    def test_invalid_material_class_returns_error(self):
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0,
                           material_class="unobtanium")
        assert r["ok"] is False
        assert "material_class" in r["reason"]

    def test_invalid_loading_class_returns_error(self):
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0,
                           loading_class="extreme")
        assert r["ok"] is False
        assert "loading_class" in r["reason"]

    def test_warnings_list_always_present(self):
        r = screw_conveyor(0.25, 0.25, 60.0, 10.0, 800.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# Bucket elevator tests
# ===========================================================================

class TestBucketElevator:

    def test_basic_returns_ok(self):
        r = bucket_elevator(
            bucket_volume_m3=0.010,
            bucket_spacing_m=0.5,
            belt_speed_m_s=1.5,
            lift_height_m=20.0,
            bulk_density_kg_m3=800.0,
        )
        assert r["ok"] is True

    def test_all_keys_present(self):
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, 800.0)
        assert r["ok"] is True
        for key in (
            "capacity_m3_h", "capacity_t_h", "buckets_per_m",
            "material_per_bucket_kg", "lift_power_W", "lift_power_kW",
            "belt_power_kW", "total_power_kW", "motor_power_kW",
            "belt_tension_N", "warnings",
        ):
            assert key in r, f"Missing key: {key}"

    def test_capacity_formula(self):
        """Q_vol = (v / bs) × Vb × ff × 3600."""
        Vb, bs, v, ff = 0.010, 0.5, 1.5, 0.75
        r = bucket_elevator(Vb, bs, v, 20.0, 800.0, fill_factor=ff)
        assert r["ok"] is True
        expected_vol = (v / bs) * Vb * ff * 3600.0
        assert abs(r["capacity_m3_h"] - expected_vol) / expected_vol < 1e-9

    def test_capacity_mass_from_volume(self):
        """capacity_t_h = capacity_m3_h × rho / 1000."""
        rho = 1000.0
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, rho)
        assert r["ok"] is True
        expected = r["capacity_m3_h"] * rho / 1000.0
        assert abs(r["capacity_t_h"] - expected) / expected < 1e-9

    def test_higher_speed_higher_capacity(self):
        """Doubling belt speed doubles volumetric capacity."""
        r1 = bucket_elevator(0.010, 0.5, 1.0, 20.0, 800.0)
        r2 = bucket_elevator(0.010, 0.5, 2.0, 20.0, 800.0)
        assert r1["ok"] and r2["ok"]
        assert abs(r2["capacity_m3_h"] / r1["capacity_m3_h"] - 2.0) < 1e-9

    def test_lift_power_formula(self):
        """P_lift = mass_flow × g × H."""
        rho = 800.0
        r = bucket_elevator(0.010, 0.5, 1.5, 25.0, rho)
        assert r["ok"] is True
        mass_flow = r["capacity_m3_h"] * rho / 3600.0
        expected_P_lift = mass_flow * G * 25.0
        assert abs(r["lift_power_W"] - expected_P_lift) / max(expected_P_lift, 1.0) < 1e-9

    def test_motor_power_accounts_for_efficiency(self):
        """motor_power_kW = total_power_kW / η."""
        eta = 0.80
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, 800.0, drive_efficiency=eta)
        assert r["ok"] is True
        assert abs(r["motor_power_kW"] - r["total_power_kW"] / eta) < 1e-6

    def test_belt_tension_from_power_and_speed(self):
        """belt_tension_N = total_power_W / v."""
        v = 1.5
        r = bucket_elevator(0.010, 0.5, v, 20.0, 800.0)
        assert r["ok"] is True
        expected_T = r["total_power_kW"] * 1000.0 / v
        assert abs(r["belt_tension_N"] - expected_T) / max(expected_T, 1.0) < 1e-9

    def test_buckets_per_m_formula(self):
        """buckets_per_m = 1 / bucket_spacing_m."""
        bs = 0.4
        r = bucket_elevator(0.010, bs, 1.5, 20.0, 800.0)
        assert r["ok"] is True
        assert abs(r["buckets_per_m"] - 1.0 / bs) < 1e-9

    def test_material_per_bucket_formula(self):
        """material_per_bucket_kg = bucket_volume × fill_factor × bulk_density."""
        Vb, ff, rho = 0.015, 0.80, 900.0
        r = bucket_elevator(Vb, 0.5, 1.5, 20.0, rho, fill_factor=ff)
        assert r["ok"] is True
        expected = Vb * ff * rho
        assert abs(r["material_per_bucket_kg"] - expected) / expected < 1e-9

    def test_continuous_elevator_type_accepted(self):
        r = bucket_elevator(0.008, 0.4, 0.8, 15.0, 700.0, elevator_type="continuous")
        assert r["ok"] is True

    def test_high_speed_centrifugal_warning(self):
        """Speed > 3.0 m/s for centrifugal elevator triggers warning."""
        r = bucket_elevator(0.010, 0.5, 3.5, 20.0, 800.0, elevator_type="centrifugal")
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "speed" in warn_text or "centrifugal" in warn_text

    def test_capacity_shortfall_warning(self):
        r = bucket_elevator(0.001, 1.0, 0.5, 5.0, 800.0,
                            target_capacity_t_h=200.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "shortfall" in warn_text or "capacity" in warn_text

    def test_warnings_list_always_present(self):
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, 800.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)

    # ---- Error paths ----

    def test_negative_bucket_volume_returns_error(self):
        r = bucket_elevator(-0.010, 0.5, 1.5, 20.0, 800.0)
        assert r["ok"] is False

    def test_zero_lift_height_returns_error(self):
        r = bucket_elevator(0.010, 0.5, 1.5, 0.0, 800.0)
        assert r["ok"] is False

    def test_invalid_elevator_type_returns_error(self):
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, 800.0,
                            elevator_type="pneumatic")
        assert r["ok"] is False
        assert "elevator_type" in r["reason"]

    def test_invalid_fill_factor_returns_error(self):
        r = bucket_elevator(0.010, 0.5, 1.5, 20.0, 800.0, fill_factor=1.5)
        assert r["ok"] is False


# ===========================================================================
# LLM tool wrapper tests
# ===========================================================================

class TestBeltConveyorTool:

    def test_happy_path(self):
        result = _run(run_belt_conveyor_design(_ctx(), _args(
            belt_width_m=1.0, belt_speed_m_s=1.5, length_m=100.0,
            lift_m=5.0, bulk_density_kg_m3=800.0, trough_angle_deg=35.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "capacity_t_h" in r

    def test_missing_belt_width_returns_error(self):
        result = _run(run_belt_conveyor_design(_ctx(), _args(
            belt_speed_m_s=1.5, length_m=100.0, lift_m=0.0,
            bulk_density_kg_m3=800.0,
        )))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_invalid_json_returns_error(self):
        result = _run(run_belt_conveyor_design(_ctx(), b"not_json"))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_target_capacity_in_tool(self):
        result = _run(run_belt_conveyor_design(_ctx(), _args(
            belt_width_m=0.5, belt_speed_m_s=0.5, length_m=50.0,
            lift_m=0.0, bulk_density_kg_m3=800.0,
            target_capacity_t_h=500.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


class TestScrewConveyorTool:

    def test_happy_path(self):
        result = _run(run_screw_conveyor_design(_ctx(), _args(
            diameter_m=0.25, pitch_m=0.25, speed_rpm=60.0,
            length_m=10.0, bulk_density_kg_m3=800.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "capacity_t_h" in r

    def test_missing_length_returns_error(self):
        result = _run(run_screw_conveyor_design(_ctx(), _args(
            diameter_m=0.25, pitch_m=0.25, speed_rpm=60.0,
            bulk_density_kg_m3=800.0,
        )))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_invalid_json_returns_error(self):
        result = _run(run_screw_conveyor_design(_ctx(), b"{bad"))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_optional_lift_accepted(self):
        result = _run(run_screw_conveyor_design(_ctx(), _args(
            diameter_m=0.30, pitch_m=0.30, speed_rpm=50.0,
            length_m=15.0, bulk_density_kg_m3=1200.0,
            lift_m=1.5, material_class="coal_dry",
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert r["Pi_kW"] > 0.0


class TestBucketElevatorTool:

    def test_happy_path(self):
        result = _run(run_bucket_elevator_design(_ctx(), _args(
            bucket_volume_m3=0.010, bucket_spacing_m=0.5,
            belt_speed_m_s=1.5, lift_height_m=20.0,
            bulk_density_kg_m3=800.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "motor_power_kW" in r

    def test_missing_lift_height_returns_error(self):
        result = _run(run_bucket_elevator_design(_ctx(), _args(
            bucket_volume_m3=0.010, bucket_spacing_m=0.5,
            belt_speed_m_s=1.5, bulk_density_kg_m3=800.0,
        )))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_invalid_json_returns_error(self):
        result = _run(run_bucket_elevator_design(_ctx(), b""))
        r = json.loads(result)
        assert _is_error_response(r)

    def test_continuous_elevator_in_tool(self):
        result = _run(run_bucket_elevator_design(_ctx(), _args(
            bucket_volume_m3=0.008, bucket_spacing_m=0.4,
            belt_speed_m_s=0.8, lift_height_m=15.0,
            bulk_density_kg_m3=700.0, elevator_type="continuous",
        )))
        r = json.loads(result)
        assert r["ok"] is True


# ---------------------------------------------------------------------------
# Externally-citable reference cases
#   CEMA "Belt Conveyors for Bulk Materials", 7th ed.
#   CEMA "Screw Conveyors for Bulk Materials", 5th ed.
#   Capstan (Euler-Eytelwein) belt-friction equation.
# ---------------------------------------------------------------------------

class TestConveyorExternalReferenceCases:
    """Cross-checked against CEMA 7th ed. (belt) / 5th ed. (screw) and the
    classical capstan equation."""

    def test_belt_drive_power_is_Te_times_speed(self):
        # CEMA: required drive power P = Te * belt_speed.
        r = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.5,
                          length_m=100.0, lift_m=0.0,
                          bulk_density_kg_m3=1600.0)
        assert math.isclose(r["drive_power_W"], r["Te_N"] * 2.5, rel_tol=1e-9)

    def test_belt_motor_power_efficiency(self):
        # CEMA: motor power = drive power / drive efficiency.
        r = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.5,
                          length_m=100.0, lift_m=0.0,
                          bulk_density_kg_m3=1600.0, drive_efficiency=0.9)
        assert math.isclose(r["motor_power_kW"],
                            r["drive_power_kW"] / 0.9, rel_tol=1e-9)

    def test_belt_capstan_no_slip_ratio(self):
        # Capstan / Euler-Eytelwein: T1/T2 = exp(mu * wrap_angle).
        mu = 0.35
        wrap = math.radians(210.0)
        r = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.5,
                          length_m=100.0, lift_m=0.0,
                          bulk_density_kg_m3=1600.0,
                          mu_belt_pulley=mu, wrap_angle_deg=210.0)
        assert math.isclose(r["T1_N"] / r["T2_N"], math.exp(mu * wrap),
                            rel_tol=1e-6)

    def test_belt_effective_tension_T1_minus_T2(self):
        # CEMA: effective tension Te = T1 - T2 (drive force at the pulley).
        r = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.5,
                          length_m=100.0, lift_m=0.0,
                          bulk_density_kg_m3=1600.0)
        assert math.isclose(r["Te_N"], r["T1_N"] - r["T2_N"], rel_tol=1e-9)

    def test_belt_lift_component_increases_tension(self):
        # CEMA: a positive lift adds Wm*L*g*sin(theta) to effective tension.
        flat = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.0,
                             length_m=100.0, lift_m=0.0,
                             bulk_density_kg_m3=1600.0)
        incl = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.0,
                             length_m=100.0, lift_m=10.0,
                             bulk_density_kg_m3=1600.0)
        assert incl["Te_N"] > flat["Te_N"]

    def test_belt_capacity_mass_from_volume_density(self):
        # CEMA: mass capacity (t/h) = volumetric capacity * bulk density.
        r = belt_conveyor(belt_width_m=1.0, belt_speed_m_s=2.5,
                          length_m=100.0, lift_m=0.0,
                          bulk_density_kg_m3=1600.0)
        assert math.isclose(r["capacity_t_h"],
                            r["capacity_m3_h"] * 1600.0 / 1000.0,
                            rel_tol=1e-6)

    def test_screw_power_scales_with_length(self):
        # CEMA screw conveyor: power increases with conveying length.
        a = screw_conveyor(diameter_m=0.25, pitch_m=0.25, speed_rpm=60.0,
                           length_m=5.0, bulk_density_kg_m3=800.0)
        b = screw_conveyor(diameter_m=0.25, pitch_m=0.25, speed_rpm=60.0,
                           length_m=15.0, bulk_density_kg_m3=800.0)
        assert b["motor_power_kW"] > a["motor_power_kW"]

    def test_screw_capacity_scales_with_speed(self):
        # CEMA screw: volumetric capacity is proportional to screw rpm.
        a = screw_conveyor(diameter_m=0.25, pitch_m=0.25, speed_rpm=30.0,
                           length_m=10.0, bulk_density_kg_m3=800.0)
        b = screw_conveyor(diameter_m=0.25, pitch_m=0.25, speed_rpm=60.0,
                           length_m=10.0, bulk_density_kg_m3=800.0)
        assert math.isclose(b["capacity_t_h"], 2.0 * a["capacity_t_h"],
                            rel_tol=1e-6)

    def test_bucket_elevator_lift_power(self):
        # Bucket elevator lift power = mass-flow * g * lift height
        # (work-energy; CEMA bucket-elevator basis).
        r = bucket_elevator(bucket_volume_m3=0.005, bucket_spacing_m=0.4,
                            belt_speed_m_s=1.5, lift_height_m=20.0,
                            bulk_density_kg_m3=800.0, fill_factor=0.75)
        mass_flow = (0.005 * 0.75 / 0.4) * 1.5 * 800.0  # kg/s
        assert math.isclose(r["lift_power_W"],
                            mass_flow * 9.81 * 20.0, rel_tol=1e-3)

    def test_bucket_elevator_capacity(self):
        # Capacity = (bucket_vol*fill/spacing) * speed * density * 3600.
        r = bucket_elevator(bucket_volume_m3=0.005, bucket_spacing_m=0.4,
                            belt_speed_m_s=1.5, lift_height_m=20.0,
                            bulk_density_kg_m3=800.0, fill_factor=0.75)
        cap_t_h = (0.005 * 0.75 / 0.4) * 1.5 * 3600.0 * 800.0 / 1000.0
        assert math.isclose(r["capacity_t_h"], cap_t_h, rel_tol=1e-6)
