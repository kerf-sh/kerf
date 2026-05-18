"""
Propulsion module tests with analytic and reference-data oracles.

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-aero/src \
        python3 -m pytest packages/kerf-aero/tests/test_propulsion.py -x -v

All tolerance thresholds are noted per-test.
"""

from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from kerf_aero.propulsion.rocket_eq import (
    delta_v,
    effective_exhaust_velocity,
    isp_from_cstar,
    mass_ratio_for_delta_v,
    propellant_mass,
    thrust_from_mass_flow,
    G0,
)
from kerf_aero.propulsion.nozzle import (
    area_ratio_from_pressure_ratio,
    exit_mach_from_area_ratio,
    exit_mach_from_pressure_ratio,
    nozzle_exit_conditions,
    rao_bell_contour,
    thrust_coefficient,
)
from kerf_aero.propulsion.cea_lite import cea_lite, PROPELLANT_PAIRS
from kerf_aero.propulsion.staging import (
    gravity_loss_estimate,
    multistage_delta_v,
    optimal_delta_v_split,
    stage_mass_ratio,
)


# ===========================================================================
# rocket_eq tests
# ===========================================================================

class TestDeltaV:
    """Tsiolkovsky rocket equation."""

    def test_oracle_mr10_isp300(self):
        """
        Analytic oracle: m0/mf = 10, Isp = 300 s
          ΔV = 300 × 9.80665 × ln(10) = 6774.19 m/s ≈ 6.774 km/s
        """
        res = delta_v(isp=300.0, m0=10_000.0, mf=1_000.0)
        assert res["ok"]
        expected = 300.0 * G0 * math.log(10.0)
        assert abs(res["delta_v_ms"] - expected) < 0.01  # <0.01 m/s error
        assert abs(res["delta_v_kms"] - expected / 1000.0) < 1e-5
        assert res["mass_ratio"] == pytest.approx(10.0, rel=1e-9)

    def test_delta_v_kms_approx_6776(self):
        """Prompt spec: ΔV ≈ 6.776 km/s (within rounding of 6.774 km/s analytic)."""
        res = delta_v(isp=300.0, m0=10_000.0, mf=1_000.0)
        # The spec says "≈ 6.776 km/s" — analytic is 6.7742 km/s; both are ≈6.77x
        assert res["ok"]
        assert abs(res["delta_v_kms"] - 6.7742) < 0.005  # within 5 m/s

    def test_saturn_v_first_stage(self):
        """
        Saturn V S-IC stage oracle:
          m0 = 2 900 000 kg, mf = 750 000 kg, Isp = 263 s
          ΔV = 263 × 9.80665 × ln(2900/750) = 3488 m/s ≈ 3.49 km/s
        """
        res = delta_v(isp=263.0, m0=2_900_000.0, mf=750_000.0)
        assert res["ok"]
        expected = 263.0 * G0 * math.log(2_900_000.0 / 750_000.0)
        assert abs(res["delta_v_ms"] - expected) < 0.1
        # Spec says ≈ 3.49 km/s
        assert 3.45 < res["delta_v_kms"] < 3.55

    def test_invalid_inputs(self):
        assert not delta_v(isp=0.0, m0=1000.0, mf=100.0)["ok"]
        assert not delta_v(isp=300.0, m0=-100.0, mf=100.0)["ok"]
        assert not delta_v(isp=300.0, m0=100.0, mf=200.0)["ok"]  # mf > m0

    def test_mass_ratio_unity(self):
        """Zero propellant → ΔV = 0."""
        res = delta_v(isp=300.0, m0=1000.0, mf=1000.0)
        assert res["ok"]
        assert res["delta_v_ms"] == pytest.approx(0.0, abs=1e-9)

    def test_ve(self):
        res = delta_v(isp=450.0, m0=1000.0, mf=100.0)
        assert res["ok"]
        assert res["ve"] == pytest.approx(450.0 * G0, rel=1e-9)


class TestEffectiveExhaustVelocity:
    def test_standard(self):
        res = effective_exhaust_velocity(450.0)
        assert res["ok"]
        assert res["ve"] == pytest.approx(450.0 * G0, rel=1e-9)

    def test_invalid(self):
        assert not effective_exhaust_velocity(-1.0)["ok"]
        assert not effective_exhaust_velocity(0.0)["ok"]


class TestMassRatio:
    def test_round_trip(self):
        """delta_v then mass_ratio_for_delta_v should recover MR."""
        mr_in = 8.0
        isp = 350.0
        dv = isp * G0 * math.log(mr_in)
        res = mass_ratio_for_delta_v(dv, isp)
        assert res["ok"]
        assert res["mass_ratio"] == pytest.approx(mr_in, rel=1e-9)

    def test_propellant_fraction(self):
        res = mass_ratio_for_delta_v(9000.0, 450.0)
        assert res["ok"]
        mr = res["mass_ratio"]
        assert res["propellant_fraction"] == pytest.approx(1.0 - 1.0 / mr, rel=1e-9)


class TestPropellantMass:
    def test_basic(self):
        dry = 5000.0
        isp = 320.0
        dv = 4000.0
        res = propellant_mass(dv, isp, dry)
        assert res["ok"]
        mr = math.exp(dv / (isp * G0))
        expected_mp = dry * (mr - 1.0)
        assert res["propellant_mass"] == pytest.approx(expected_mp, rel=1e-9)
        assert res["wet_mass"] == pytest.approx(dry + expected_mp, rel=1e-9)


class TestThrust:
    def test_basic(self):
        res = thrust_from_mass_flow(mass_flow=500.0, isp=350.0)
        assert res["ok"]
        assert res["thrust_n"] == pytest.approx(500.0 * 350.0 * G0, rel=1e-9)
        assert res["thrust_kn"] == pytest.approx(res["thrust_n"] / 1000.0, rel=1e-9)

    def test_invalid(self):
        assert not thrust_from_mass_flow(mass_flow=-1.0, isp=350.0)["ok"]
        assert not thrust_from_mass_flow(mass_flow=500.0, isp=-10.0)["ok"]


class TestIspFromCstar:
    def test_vacuum_isp(self):
        """c*=1789 m/s, γ=1.17, Ae/At=40 → Isp_vac ≈ 350 s."""
        res = isp_from_cstar(c_star=1789.0, gamma=1.17, expansion_ratio=40.0)
        assert res["ok"]
        # Reference value 350 s, allow ±3%
        assert 350.0 * 0.97 < res["isp_vac"] < 350.0 * 1.03


# ===========================================================================
# nozzle tests
# ===========================================================================

class TestIsentropicMach:
    def test_throat_unity(self):
        """Area ratio = 1 → Mach = 1."""
        res = exit_mach_from_area_ratio(1.0, gamma=1.4)
        assert res["ok"]
        assert res["mach"] == pytest.approx(1.0, abs=1e-6)

    def test_oracle_pe_pc_001_gamma_12(self):
        """
        Oracle: pe/pc = 0.01, γ = 1.2 → Me ≈ 3.398 (within ±1%).

        Analytic: Me = sqrt(2/(γ-1) · ((pc/pe)^((γ-1)/γ) − 1))
                     = sqrt(2/0.2 · (100^(0.2/1.2) − 1))
        """
        gamma = 1.2
        pe_pc = 0.01
        t = pe_pc ** (-(gamma - 1.0) / gamma) - 1.0
        me_analytic = math.sqrt(2.0 / (gamma - 1.0) * t)
        # ≈ 3.3977

        res = exit_mach_from_pressure_ratio(pe_pc, gamma)
        assert res["ok"]
        assert abs(res["mach"] - me_analytic) / me_analytic < 0.001  # within 0.1%
        assert abs(res["mach"] - 3.4) < 0.04  # within 1% of 3.4

    def test_supersonic_root_consistency(self):
        """Area ratio and back-computed Me should be consistent."""
        for ar in [2.0, 5.0, 10.0, 40.0]:
            res = exit_mach_from_area_ratio(ar, gamma=1.4)
            assert res["ok"], f"Failed at ar={ar}"
            me = res["mach"]
            # Recompute area ratio from Me
            ar_back = (1.0 / me) * (
                (2.0 / (1.4 + 1.0)) * (1.0 + (1.4 - 1.0) / 2.0 * me**2)
            ) ** ((1.4 + 1.0) / (2.0 * (1.4 - 1.0)))
            assert abs(ar_back - ar) / ar < 1e-6, f"ar={ar}: back-computed={ar_back}"

    def test_subsonic_root(self):
        res = exit_mach_from_area_ratio(2.0, gamma=1.4, supersonic=False)
        assert res["ok"]
        assert res["mach"] < 1.0

    def test_pressure_ratio_round_trip(self):
        """area_ratio_from_pressure_ratio → exit_mach should agree."""
        for pe_pc in [0.1, 0.05, 0.01, 0.001]:
            r1 = area_ratio_from_pressure_ratio(pe_pc, gamma=1.4)
            assert r1["ok"]
            r2 = exit_mach_from_area_ratio(r1["area_ratio"], gamma=1.4)
            assert r2["ok"]
            assert abs(r2["mach"] - r1["mach"]) / r1["mach"] < 1e-5

    def test_invalid_area_ratio(self):
        assert not exit_mach_from_area_ratio(0.5, gamma=1.4)["ok"]

    def test_gamma_sensitivity(self):
        """Higher γ → higher Mach for same area ratio (correct physical trend)."""
        r14 = exit_mach_from_area_ratio(10.0, gamma=1.4)
        r12 = exit_mach_from_area_ratio(10.0, gamma=1.2)
        assert r14["ok"] and r12["ok"]
        # At a fixed area ratio, larger γ produces a higher exit Mach number
        assert r14["mach"] > r12["mach"]


class TestThrustCoefficient:
    def test_vacuum_gt_sea_level(self):
        """Vacuum Cf > sea-level Cf (positive ambient reduces net thrust)."""
        res = thrust_coefficient(
            gamma=1.4, pe_over_pc=0.005, ae_over_at=20.0, pa_over_pc=0.01
        )
        assert res["ok"]
        assert res["cf_vac"] > res["cf_sea"]

    def test_cf_positive(self):
        for ae_at in [5, 20, 40, 100]:
            res = area_ratio_from_pressure_ratio(0.005, gamma=1.3)
            ar = res["area_ratio"] if res["ok"] else ae_at
            r = thrust_coefficient(gamma=1.3, pe_over_pc=0.005, ae_over_at=ar)
            assert r["ok"]
            assert r["cf_vac"] > 0

    def test_invalid_pe_pc(self):
        assert not thrust_coefficient(gamma=1.4, pe_over_pc=0.0, ae_over_at=10.0)["ok"]
        assert not thrust_coefficient(gamma=1.4, pe_over_pc=1.1, ae_over_at=10.0)["ok"]


class TestNozzleExitConditions:
    def test_exit_velocity_positive(self):
        res = nozzle_exit_conditions(
            pc=7e6, tc=3500.0, gamma=1.2, molar_mass=0.023,
            area_ratio=40.0, pa=0.0
        )
        assert res["ok"]
        assert res["exit_velocity_ms"] > 0
        assert res["c_star"] > 0
        assert res["isp_vac"] > 0

    def test_higher_area_ratio_higher_isp(self):
        base = dict(pc=7e6, tc=3500.0, gamma=1.2, molar_mass=0.023)
        r1 = nozzle_exit_conditions(**base, area_ratio=10.0)
        r2 = nozzle_exit_conditions(**base, area_ratio=60.0)
        assert r1["ok"] and r2["ok"]
        assert r2["isp_vac"] > r1["isp_vac"]


class TestRaoBellContour:
    def test_basic_shape(self):
        res = rao_bell_contour(r_throat=0.1, r_exit=0.4, length_fraction=0.8)
        assert res["ok"]
        assert len(res["contour"]) > 0
        # First point at throat, last near exit radius
        last = res["contour"][-1]
        assert abs(last["r"] - 0.4) / 0.4 < 0.05  # within 5% of r_exit
        assert res["area_ratio"] == pytest.approx(16.0, rel=0.01)  # (0.4/0.1)^2

    def test_monotone_x(self):
        res = rao_bell_contour(r_throat=0.05, r_exit=0.2, length_fraction=0.8)
        assert res["ok"]
        xs = [pt["x"] for pt in res["contour"]]
        for i in range(1, len(xs)):
            assert xs[i] >= xs[i - 1], f"Non-monotone at i={i}"

    def test_invalid(self):
        assert not rao_bell_contour(r_throat=-0.1, r_exit=0.4)["ok"]
        assert not rao_bell_contour(r_throat=0.4, r_exit=0.1)["ok"]
        assert not rao_bell_contour(r_throat=0.1, r_exit=0.4, length_fraction=0.3)["ok"]


# ===========================================================================
# cea_lite tests
# ===========================================================================

class TestCeaLite:
    def test_lox_rp1_reference(self):
        """
        LOX/RP-1 at Pc=70 bar, OF=2.3:
          c* ≈ 1790 m/s (within ±3%)
          Isp_vac ≈ 350 s (within ±3%)
        Reference: Sutton & Biblarz Table 5-5; Huzel & Huang Appendix A.
        """
        res = cea_lite("LOX/RP-1", of_ratio=2.3, pc_bar=70.0, ae_over_at=40.0)
        assert res["ok"], res.get("reason")
        assert abs(res["c_star"] - 1790.0) / 1790.0 < 0.03, f"c*={res['c_star']}"
        assert abs(res["isp_vac"] - 350.0) / 350.0 < 0.03, f"Isp_vac={res['isp_vac']}"

    def test_lox_rp1_output_completeness(self):
        res = cea_lite("LOX/RP-1", of_ratio=2.5, pc_bar=70.0)
        assert res["ok"]
        for key in ("tc_k", "gamma", "molar_mass", "c_star", "isp_vac", "isp_sl",
                    "pe_over_pc", "exit_mach", "ae_over_at"):
            assert key in res, f"Missing key: {key}"

    def test_lox_lh2(self):
        """LOX/LH2 at Pc=100 bar, OF=6: c* > 2000 m/s, Isp_vac > 400 s."""
        res = cea_lite("LOX/LH2", of_ratio=6.0, pc_bar=100.0, ae_over_at=80.0)
        assert res["ok"]
        assert res["c_star"] > 2000.0
        assert res["isp_vac"] > 400.0

    def test_n2o4_mmh(self):
        """N2O4/MMH at Pc=30 bar, OF=1.73: physical Isp range."""
        res = cea_lite("N2O4/MMH", of_ratio=1.73, pc_bar=30.0, ae_over_at=80.0)
        assert res["ok"]
        assert 200.0 < res["isp_vac"] < 450.0

    def test_lox_ch4(self):
        """LOX/CH4 at Pc=60 bar, OF=3.4: physical range."""
        res = cea_lite("LOX/CH4", of_ratio=3.4, pc_bar=60.0, ae_over_at=80.0)
        assert res["ok"]
        assert 250.0 < res["isp_vac"] < 450.0

    def test_unknown_propellant(self):
        res = cea_lite("LOX/ETHANOL", of_ratio=1.5, pc_bar=50.0)
        assert not res["ok"]
        assert "reason" in res

    def test_isp_vac_gt_isp_sl(self):
        """Vacuum Isp always greater than sea-level Isp."""
        res = cea_lite("LOX/RP-1", of_ratio=2.3, pc_bar=70.0, ae_over_at=40.0)
        assert res["ok"]
        assert res["isp_vac"] > res["isp_sl"]

    def test_tc_physical(self):
        """Chamber temperature must be in realistic range [1000, 6000] K."""
        for prop in ("LOX/RP-1", "LOX/LH2", "N2O4/MMH", "LOX/CH4"):
            model_of = {"LOX/RP-1": 2.3, "LOX/LH2": 6.0, "N2O4/MMH": 1.73, "LOX/CH4": 3.4}
            res = cea_lite(prop, of_ratio=model_of[prop], pc_bar=70.0)
            assert res["ok"]
            assert 1000.0 < res["tc_k"] < 6000.0, f"{prop}: Tc={res['tc_k']}"

    def test_propellant_pairs_keys(self):
        """Check all expected propellants are registered."""
        for name in ("LOX/RP-1", "LOX/LH2", "N2O4/MMH", "LOX/CH4"):
            assert name in PROPELLANT_PAIRS

    def test_within_of_range_flag(self):
        res = cea_lite("LOX/RP-1", of_ratio=2.3, pc_bar=70.0)
        assert res["ok"]
        assert res["within_of_range"] is True


# ===========================================================================
# staging tests
# ===========================================================================

class TestStageMassRatio:
    def test_basic(self):
        res = stage_mass_ratio(delta_v_ms=4000.0, isp=320.0)
        assert res["ok"]
        expected_mr = math.exp(4000.0 / (320.0 * G0))
        assert res["mass_ratio"] == pytest.approx(expected_mr, rel=1e-9)

    def test_propellant_fraction(self):
        res = stage_mass_ratio(delta_v_ms=3000.0, isp=300.0)
        assert res["ok"]
        assert res["propellant_fraction"] == pytest.approx(1.0 - 1.0 / res["mass_ratio"], rel=1e-9)


class TestMultistagedeltaV:
    def test_two_stage(self):
        """Two stages, each with Isp=300s and MR=3: total ΔV = 2 × 300·g0·ln3."""
        mr = 3.0
        isp = 300.0
        expected = 2.0 * isp * G0 * math.log(mr)
        stages = [
            {"isp": isp, "m0": 9000.0, "mf": 3000.0},
            {"isp": isp, "m0": 3000.0, "mf": 1000.0},
        ]
        res = multistage_delta_v(stages)
        assert res["ok"]
        assert abs(res["total_delta_v_ms"] - expected) < 0.1
        assert res["n_stages"] == 2

    def test_single_stage_agrees_rocket_eq(self):
        """Single-stage multistage_delta_v must match direct rocket equation."""
        isp, m0, mf = 450.0, 50000.0, 5000.0
        r1 = delta_v(isp=isp, m0=m0, mf=mf)
        r2 = multistage_delta_v([{"isp": isp, "m0": m0, "mf": mf}])
        assert r1["ok"] and r2["ok"]
        assert abs(r1["delta_v_ms"] - r2["total_delta_v_ms"]) < 0.001

    def test_empty_stages(self):
        assert not multistage_delta_v([])["ok"]

    def test_invalid_mass(self):
        stages = [{"isp": 300.0, "m0": 1000.0, "mf": 2000.0}]
        assert not multistage_delta_v(stages)["ok"]

    def test_stage_results_sum(self):
        """Sum of stage ΔVs equals total ΔV."""
        stages = [
            {"isp": 300.0, "m0": 5000.0, "mf": 1000.0},
            {"isp": 350.0, "m0": 2000.0, "mf": 500.0},
            {"isp": 420.0, "m0": 800.0, "mf": 200.0},
        ]
        res = multistage_delta_v(stages)
        assert res["ok"]
        total = sum(s["delta_v_ms"] for s in res["stage_results"])
        assert abs(total - res["total_delta_v_ms"]) < 1e-6


class TestOptimalSplit:
    def test_equal_isp_equal_split(self):
        """
        Equal Isp all stages → optimal = equal ΔV per stage.
        Spec: two-stage, m1/m2 = 4 with same Isp → same ΔV per stage (within 1%).
        """
        isp = 300.0
        dv_total = 8000.0
        n = 2
        res = optimal_delta_v_split(
            total_delta_v=dv_total,
            n_stages=n,
            isp_per_stage=isp,
            structural_fraction_per_stage=0.0,
            payload_mass=1000.0,
        )
        assert res["ok"], res.get("reason")
        splits = res["optimal_delta_v_split"]
        assert len(splits) == n

        # Equal split: each stage gets dv_total / n
        for dv_s in splits:
            assert abs(dv_s - dv_total / n) / (dv_total / n) < 0.01

    def test_two_stage_equal_mr_equal_dv(self):
        """
        Spec: Two-stage optimal split with m1/m2 = 4, same Isp per stage
        gives same ΔV per stage (within 1%).
        """
        isp = 350.0
        dv_each = isp * G0 * math.log(4.0)
        dv_total = 2.0 * dv_each
        res = optimal_delta_v_split(
            total_delta_v=dv_total,
            n_stages=2,
            isp_per_stage=isp,
            structural_fraction_per_stage=0.0,
            payload_mass=1000.0,
        )
        assert res["ok"]
        splits = res["optimal_delta_v_split"]
        # Each split should be dv_each
        assert abs(splits[0] - splits[1]) / dv_each < 0.01  # within 1%

    def test_total_dv_preserved(self):
        """Sum of optimal split must equal total ΔV."""
        res = optimal_delta_v_split(
            total_delta_v=9000.0,
            n_stages=3,
            isp_per_stage=310.0,
            structural_fraction_per_stage=0.08,
            payload_mass=500.0,
        )
        assert res["ok"]
        total = sum(res["optimal_delta_v_split"])
        assert abs(total - 9000.0) < 1.0

    def test_single_stage(self):
        res = optimal_delta_v_split(
            total_delta_v=5000.0,
            n_stages=1,
            isp_per_stage=300.0,
            structural_fraction_per_stage=0.1,
            payload_mass=1000.0,
        )
        assert res["ok"]
        assert len(res["optimal_delta_v_split"]) == 1

    def test_invalid_n_stages(self):
        assert not optimal_delta_v_split(5000.0, 0, 300.0)["ok"]

    def test_payload_fraction_positive(self):
        res = optimal_delta_v_split(
            total_delta_v=7000.0,
            n_stages=2,
            isp_per_stage=320.0,
            structural_fraction_per_stage=0.1,
            payload_mass=1000.0,
        )
        assert res["ok"]
        assert res["payload_fraction"] > 0


class TestGravityLoss:
    def test_vertical_launch(self):
        """90° pitch (straight up): loss = g0 × burn_time."""
        res = gravity_loss_estimate(
            delta_v_ideal=9000.0, burn_time=200.0, average_pitch_deg=90.0
        )
        assert res["ok"]
        assert res["gravity_loss_ms"] == pytest.approx(G0 * 200.0, rel=1e-9)

    def test_zero_pitch_no_loss(self):
        """0° pitch (horizontal): no gravity loss."""
        res = gravity_loss_estimate(
            delta_v_ideal=9000.0, burn_time=200.0, average_pitch_deg=0.0
        )
        assert res["ok"]
        assert res["gravity_loss_ms"] == pytest.approx(0.0, abs=1e-9)

    def test_effective_dv(self):
        res = gravity_loss_estimate(
            delta_v_ideal=9000.0, burn_time=300.0, average_pitch_deg=45.0
        )
        assert res["ok"]
        assert res["effective_delta_v_ms"] == pytest.approx(
            9000.0 - res["gravity_loss_ms"], rel=1e-9
        )


# ===========================================================================
# Integration tests
# ===========================================================================

class TestIntegration:
    def test_lox_rp1_full_pipeline(self):
        """
        End-to-end: CEA-lite → rocket equation → staging.
        LOX/RP-1 single-stage burn to 3 km/s.
        """
        cea = cea_lite("LOX/RP-1", of_ratio=2.3, pc_bar=70.0, ae_over_at=40.0)
        assert cea["ok"]
        isp = cea["isp_vac"]

        # Propellant mass for ΔV = 3 km/s with 5000 kg dry mass
        pm = propellant_mass(3000.0, isp, 5000.0)
        assert pm["ok"]
        assert pm["propellant_mass"] > 0

        # Thrust at 300 kg/s mass flow
        th = thrust_from_mass_flow(300.0, isp)
        assert th["ok"]
        assert th["thrust_kn"] > 1000.0  # > 1 MN for LOX/RP-1 at 300 kg/s

    def test_two_stage_to_orbit(self):
        """
        Simplified two-stage to LEO at ΔV_total = 9.5 km/s (gravity losses included).
        Stage 1: Isp=310s (LOX/RP-1 sea-level)
        Stage 2: Isp=350s (LOX/RP-1 vacuum)
        Verify total ΔV is delivered.
        """
        stages = [
            {"name": "Stage 1", "isp": 310.0, "m0": 500_000.0, "mf": 55_000.0},
            {"name": "Stage 2", "isp": 350.0, "m0": 55_000.0, "mf": 8_000.0},
        ]
        res = multistage_delta_v(stages)
        assert res["ok"]
        assert res["total_delta_v_kms"] > 9.0  # feasible LEO mission

    def test_nozzle_and_cstar_consistency(self):
        """
        isp_from_cstar with explicit pe/pc must agree with nozzle module Cf.
        """
        c_star = 1789.0
        gamma = 1.17
        ae_at = 40.0

        r_me = exit_mach_from_area_ratio(ae_at, gamma)
        assert r_me["ok"]
        me = r_me["mach"]
        pe_pc = (1.0 + (gamma - 1.0) / 2.0 * me**2) ** (-gamma / (gamma - 1.0))

        r_isp = isp_from_cstar(c_star=c_star, gamma=gamma, expansion_ratio=ae_at,
                                pe_over_pc=pe_pc)
        assert r_isp["ok"]
        assert 330.0 < r_isp["isp_vac"] < 370.0
