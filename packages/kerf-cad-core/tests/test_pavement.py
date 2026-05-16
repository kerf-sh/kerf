"""
Hermetic tests for kerf_cad_core.pavement — highway & airfield pavement design.

Coverage:
  design.aashto93_flexible_sn    — AASHTO '93 structural number
  design.aashto93_flexible_layers— Layer thicknesses from SN + layer coefficients
  design.esals_design            — Design-period ESAL accumulation
  design.esal_growth_factor      — Compound traffic growth factor
  design.load_equivalency_factor — LEF power-law
  design.cbr_to_mr               — CBR → MR correlation
  design.cbr_to_k                — CBR → k correlation
  design.boussinesq_stress       — Vertical stress under circular load
  design.aashto93_rigid_thickness— AASHTO '93 rigid slab thickness
  design.joint_spacing           — Contraction joint spacing
  design.dowel_bar_size          — Dowel bar size selection
  design.frost_penetration_depth — Stefan frost-depth equation
  design.overlay_thickness_sn    — Overlay SN-deficiency method
  design.asphalt_quantity        — Asphalt mix quantity
  tools.*                        — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified against AASHTO '93 hand-calculations and Huang (2004) examples.

References
----------
AASHTO (1993). Guide for Design of Pavement Structures.
Huang, Y.H. (2004). Pavement Analysis and Design, 2nd ed. Pearson.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.pavement.design import (
    aashto93_flexible_sn,
    aashto93_flexible_layers,
    esals_design,
    esal_growth_factor,
    load_equivalency_factor,
    cbr_to_mr,
    cbr_to_k,
    boussinesq_stress,
    aashto93_rigid_thickness,
    joint_spacing,
    dowel_bar_size,
    frost_penetration_depth,
    overlay_thickness_sn,
    asphalt_quantity,
)
from kerf_cad_core.pavement.tools import (
    run_pavement_flexible_sn,
    run_pavement_flexible_layers,
    run_pavement_esals,
    run_pavement_esal_growth,
    run_pavement_lef,
    run_pavement_cbr_to_mr,
    run_pavement_cbr_to_k,
    run_pavement_boussinesq,
    run_pavement_rigid_thickness,
    run_pavement_joint_spacing,
    run_pavement_dowel_bar,
    run_pavement_frost_depth,
    run_pavement_overlay_sn,
    run_pavement_asphalt_quantity,
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


def _call(tool_fn, payload: dict) -> dict:
    raw = _run(tool_fn(_ctx(), json.dumps(payload).encode()))
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 1. AASHTO '93 Flexible SN
# ---------------------------------------------------------------------------

class TestFlexibleSN:

    def test_typical_highway_sn_range(self):
        """For W18=5e6, R=95% (ZR=-1.645), S0=0.45, ΔPSI=1.7, MR=7500 psi
        AASHTO '93 yields SN ≈ 4–6 for a typical highway."""
        r = aashto93_flexible_sn(
            W18=5_000_000, ZR=-1.645, S0=0.45, DPSI=1.7, MR=7500
        )
        assert r["ok"] is True
        assert 3.0 < r["SN"] < 8.0, f"SN={r['SN']}"
        assert r["MR_psi"] == 7500

    def test_low_traffic_low_sn(self):
        """Low W18 should give low SN."""
        r = aashto93_flexible_sn(
            W18=50_000, ZR=-1.282, S0=0.45, DPSI=1.5, MR=10_000
        )
        assert r["ok"] is True
        assert r["SN"] < 3.0

    def test_high_traffic_high_sn(self):
        """High W18 should give higher SN."""
        r = aashto93_flexible_sn(
            W18=50_000_000, ZR=-2.327, S0=0.45, DPSI=1.7, MR=5000
        )
        assert r["ok"] is True
        assert r["SN"] > 5.0

    def test_sn_increases_with_w18(self):
        """SN must increase monotonically with W18."""
        sns = []
        for w in [1e5, 1e6, 1e7, 5e7]:
            r = aashto93_flexible_sn(W18=w, ZR=-1.282, S0=0.45, DPSI=1.7, MR=7500)
            assert r["ok"]
            sns.append(r["SN"])
        assert sns == sorted(sns), f"SN not monotone: {sns}"

    def test_sn_decreases_with_mr(self):
        """Higher subgrade MR → lower required SN."""
        r_weak = aashto93_flexible_sn(W18=5e6, ZR=-1.282, S0=0.45, DPSI=1.7, MR=3000)
        r_strong = aashto93_flexible_sn(W18=5e6, ZR=-1.282, S0=0.45, DPSI=1.7, MR=15000)
        assert r_weak["ok"] and r_strong["ok"]
        assert r_weak["SN"] > r_strong["SN"]

    def test_invalid_w18(self):
        r = aashto93_flexible_sn(W18=-100, ZR=-1.282, S0=0.45, DPSI=1.7, MR=7500)
        assert r["ok"] is False

    def test_invalid_s0_zero(self):
        r = aashto93_flexible_sn(W18=5e6, ZR=-1.282, S0=0, DPSI=1.7, MR=7500)
        assert r["ok"] is False

    def test_invalid_dpsi_out_of_range(self):
        r = aashto93_flexible_sn(W18=5e6, ZR=-1.282, S0=0.45, DPSI=5.0, MR=7500)
        assert r["ok"] is False

    def test_warnings_present(self):
        r = aashto93_flexible_sn(W18=5e6, ZR=-1.282, S0=0.45, DPSI=1.7, MR=7500)
        assert "warnings" in r


# ---------------------------------------------------------------------------
# 2. Flexible Layer Thicknesses
# ---------------------------------------------------------------------------

class TestFlexibleLayers:

    def test_three_layer_system(self):
        """Three-layer flexible system should cover required SN."""
        layers = [
            {"a": 0.44, "m": 1.0, "type": "asphalt", "name": "HMA Surface"},
            {"a": 0.14, "m": 1.0, "type": "base",    "name": "Crushed Stone Base"},
            {"a": 0.11, "m": 0.8, "type": "subbase",  "name": "Subbase"},
        ]
        r = aashto93_flexible_layers(SN=4.5, layers=layers)
        assert r["ok"] is True
        assert r["SN_total"] >= r["SN_required"] - 0.1
        assert len(r["layers"]) == 3

    def test_layer_sn_contribution_adds_up(self):
        """Sum of SN_contrib must equal SN_total."""
        layers = [
            {"a": 0.44, "type": "asphalt"},
            {"a": 0.14, "type": "base"},
        ]
        r = aashto93_flexible_layers(SN=3.0, layers=layers)
        assert r["ok"] is True
        total = sum(lyr["SN_contrib"] for lyr in r["layers"])
        assert abs(total - r["SN_total"]) < 1e-9

    def test_minimum_thickness_enforced(self):
        """HMA min = 1 in., base/subbase min = 4 in. should be enforced."""
        layers = [
            {"a": 0.44, "type": "asphalt", "m": 1.0},
            {"a": 0.14, "type": "base",    "m": 1.0},
        ]
        # Very small SN — will be clipped to minimum thicknesses
        r = aashto93_flexible_layers(SN=0.5, layers=layers)
        assert r["ok"] is True
        for lyr in r["layers"]:
            if lyr["type"] == "asphalt":
                assert lyr["D_in"] >= 1.0
            elif lyr["type"] == "base":
                assert lyr["D_in"] >= 4.0

    def test_invalid_layer_missing_a(self):
        r = aashto93_flexible_layers(SN=4.0, layers=[{"type": "asphalt"}])
        assert r["ok"] is False

    def test_empty_layers_error(self):
        r = aashto93_flexible_layers(SN=4.0, layers=[])
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 3. ESALs Design
# ---------------------------------------------------------------------------

class TestESALsDesign:

    def test_basic_esal_accumulation(self):
        """Hand-check: ADT=5000, 10% trucks, lane=0.45, dir=0.5, 20yr, r=3%.
        annual = 5000 × 0.5 × 0.45 × 0.5 × 365 ≈ 205 312.5
        G = [(1.03^20 - 1) / 0.03] ≈ 26.87
        W18 ≈ 205312.5 × 26.87 ≈ 5.52e6"""
        r = esals_design(
            ADT=5000, truck_factor=0.5, lane_dist=0.45,
            dir_dist=0.5, design_years=20, growth_rate=0.03,
        )
        assert r["ok"] is True
        assert 4e6 < r["W18"] < 7e6, f"W18={r['W18']:.2e}"

    def test_zero_growth_rate(self):
        """Zero growth rate: G = design_years, so W18 = annual × n."""
        r = esals_design(
            ADT=2000, truck_factor=1.0, lane_dist=1.0,
            dir_dist=0.5, design_years=10, growth_rate=0.0,
        )
        assert r["ok"] is True
        annual = 2000 * 1.0 * 1.0 * 0.5 * 365
        expected = annual * 10
        assert abs(r["W18"] - expected) < 1.0

    def test_invalid_lane_dist(self):
        r = esals_design(ADT=5000, truck_factor=0.5, lane_dist=1.5,
                         dir_dist=0.5, design_years=20, growth_rate=0.03)
        assert r["ok"] is False

    def test_w18_increases_with_adt(self):
        kwargs = dict(truck_factor=0.5, lane_dist=0.45, dir_dist=0.5,
                      design_years=20, growth_rate=0.02)
        r1 = esals_design(ADT=2000, **kwargs)
        r2 = esals_design(ADT=10000, **kwargs)
        assert r1["ok"] and r2["ok"]
        assert r2["W18"] > r1["W18"]


# ---------------------------------------------------------------------------
# 4. Growth Factor
# ---------------------------------------------------------------------------

class TestGrowthFactor:

    def test_zero_growth(self):
        r = esal_growth_factor(growth_rate=0.0, design_years=20)
        assert r["ok"] is True
        assert r["growth_factor"] == 20.0

    def test_three_percent_twenty_years(self):
        """G = [(1.03^20 - 1) / 0.03] ≈ 26.87."""
        r = esal_growth_factor(growth_rate=0.03, design_years=20)
        assert r["ok"] is True
        expected = ((1.03**20) - 1) / 0.03
        assert abs(r["growth_factor"] - expected) < 0.001

    def test_five_percent_ten_years(self):
        r = esal_growth_factor(growth_rate=0.05, design_years=10)
        expected = ((1.05**10) - 1) / 0.05
        assert r["ok"] is True
        assert abs(r["growth_factor"] - expected) < 0.001

    def test_invalid_negative_years(self):
        r = esal_growth_factor(growth_rate=0.03, design_years=-5)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. Load Equivalency Factor
# ---------------------------------------------------------------------------

class TestLEF:

    def test_standard_axle_lef_equals_one(self):
        """Standard single axle (80 kN) LEF = 1.0."""
        r = load_equivalency_factor(axle_load_kN=80.0, axle_type="single")
        assert r["ok"] is True
        assert abs(r["LEF"] - 1.0) < 1e-9

    def test_lighter_axle_lef_less_than_one(self):
        r = load_equivalency_factor(axle_load_kN=40.0, axle_type="single")
        assert r["ok"] is True
        assert r["LEF"] < 1.0

    def test_heavier_axle_lef_greater_than_one(self):
        r = load_equivalency_factor(axle_load_kN=160.0, axle_type="single")
        assert r["ok"] is True
        assert r["LEF"] > 1.0

    def test_tandem_standard_axle_lef(self):
        """Standard tandem (142 kN) LEF = 1.0."""
        r = load_equivalency_factor(axle_load_kN=142.0, axle_type="tandem")
        assert r["ok"] is True
        assert abs(r["LEF"] - 1.0) < 1e-9

    def test_power_law_exponent(self):
        """LEF = (80/80)^4 = 1, (120/80)^4 ≈ 3.164."""
        r = load_equivalency_factor(axle_load_kN=120.0, axle_type="single")
        expected = (120.0 / 80.0) ** 4
        assert abs(r["LEF"] - expected) < 1e-9

    def test_invalid_axle_type(self):
        r = load_equivalency_factor(axle_load_kN=80.0, axle_type="quad")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 6. CBR Correlations
# ---------------------------------------------------------------------------

class TestCBRCorrelations:

    def test_cbr_to_mr_typical(self):
        """CBR=10% → MR = 1500 × 10 = 15 000 psi."""
        r = cbr_to_mr(CBR=10.0)
        assert r["ok"] is True
        assert abs(r["MR_psi"] - 15_000.0) < 1e-6

    def test_cbr_to_mr_linearity(self):
        """MR should scale linearly with CBR."""
        r5 = cbr_to_mr(CBR=5.0)
        r15 = cbr_to_mr(CBR=15.0)
        assert r5["ok"] and r15["ok"]
        assert abs(r15["MR_psi"] / r5["MR_psi"] - 3.0) < 1e-6

    def test_cbr_to_mr_invalid_zero(self):
        r = cbr_to_mr(CBR=0.0)
        assert r["ok"] is False

    def test_cbr_to_k_typical(self):
        """CBR=10% → k = 26.3 × 10^0.45 ≈ 74.3 pci."""
        r = cbr_to_k(CBR=10.0)
        assert r["ok"] is True
        expected = 26.3 * (10.0 ** 0.45)
        assert abs(r["k_pci"] - expected) < 0.01

    def test_cbr_to_k_increases_with_cbr(self):
        r3 = cbr_to_k(CBR=3.0)
        r20 = cbr_to_k(CBR=20.0)
        assert r3["ok"] and r20["ok"]
        assert r20["k_pci"] > r3["k_pci"]

    def test_cbr_to_k_invalid_over_100(self):
        r = cbr_to_k(CBR=110.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 7. Boussinesq Stress
# ---------------------------------------------------------------------------

class TestBoussinesq:

    def test_shallow_depth_high_stress(self):
        """At very shallow depth (z << a), σ_z ≈ q."""
        r = boussinesq_stress(q=700_000, a=0.15, z=0.001)
        assert r["ok"] is True
        assert r["sigma_z_Pa"] > 0.99 * 700_000

    def test_deep_depth_low_stress(self):
        """At depth >> radius, stress should decay significantly."""
        r = boussinesq_stress(q=700_000, a=0.15, z=10.0)
        assert r["ok"] is True
        assert r["sigma_z_Pa"] < 0.01 * 700_000

    def test_stress_ratio_between_zero_and_one(self):
        """Stress ratio σ_z/q must be in (0, 1) for any valid z > 0."""
        r = boussinesq_stress(q=500_000, a=0.15, z=0.30)
        assert r["ok"] is True
        assert 0 < r["stress_ratio"] < 1.0

    def test_boussinesq_formula_hand_check(self):
        """Verify formula: σ_z = q × [1 - z³/(a²+z²)^1.5]."""
        q, a, z = 1e6, 0.1, 0.2
        expected = q * (1.0 - z**3 / (a**2 + z**2)**1.5)
        r = boussinesq_stress(q=q, a=a, z=z)
        assert r["ok"] is True
        assert abs(r["sigma_z_Pa"] - expected) < 1.0

    def test_invalid_negative_z(self):
        r = boussinesq_stress(q=1e6, a=0.15, z=-0.5)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 8. Rigid Pavement Thickness
# ---------------------------------------------------------------------------

class TestRigidThickness:

    def test_typical_highway_slab(self):
        """Typical highway: W18=5e6, R=90% (ZR=-1.282), S0=0.35, ΔPSI=2.0,
        Sc=650 psi, Cd=1.0, J=3.2, Ec=4e6 psi, k=100 pci → D ≈ 8–12 in."""
        r = aashto93_rigid_thickness(
            W18=5_000_000, ZR=-1.282, S0=0.35, DPSI=2.0,
            Sc=650, Cd=1.0, J=3.2, Ec=4_000_000, k=100,
        )
        assert r["ok"] is True
        assert 6.0 <= r["D_in"] <= 18.0, f"D_in={r['D_in']}"

    def test_d_increases_with_traffic(self):
        """Higher W18 should require thicker slab."""
        kwargs = dict(ZR=-1.282, S0=0.35, DPSI=2.0,
                      Sc=650, Cd=1.0, J=3.2, Ec=4_000_000, k=100)
        r_light = aashto93_rigid_thickness(W18=1e5, **kwargs)
        r_heavy = aashto93_rigid_thickness(W18=5e7, **kwargs)
        assert r_light["ok"] and r_heavy["ok"]
        assert r_heavy["D_in"] > r_light["D_in"]

    def test_d_rounded_up_to_half_inch(self):
        """D_in result must be a multiple of 0.5 in."""
        r = aashto93_rigid_thickness(
            W18=2_000_000, ZR=-1.282, S0=0.35, DPSI=2.0,
            Sc=650, Cd=1.0, J=3.2, Ec=4_000_000, k=100,
        )
        assert r["ok"] is True
        assert abs(r["D_in"] * 2 - round(r["D_in"] * 2)) < 1e-9

    def test_invalid_negative_w18(self):
        r = aashto93_rigid_thickness(
            W18=-1, ZR=-1.282, S0=0.35, DPSI=2.0,
            Sc=650, Cd=1.0, J=3.2, Ec=4_000_000, k=100,
        )
        assert r["ok"] is False

    def test_invalid_dpsi_out_of_range(self):
        r = aashto93_rigid_thickness(
            W18=5e6, ZR=-1.282, S0=0.35, DPSI=5.0,
            Sc=650, Cd=1.0, J=3.2, Ec=4_000_000, k=100,
        )
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 9. Joint Spacing
# ---------------------------------------------------------------------------

class TestJointSpacing:

    def test_default_parameters(self):
        """With defaults (ct=10e-6, dT=30, eps=2e-4): L = 2e-4/(10e-6×30) = 0.667 m."""
        r = joint_spacing(h_slab_mm=250)
        assert r["ok"] is True
        expected = 2e-4 / (10e-6 * 30.0)
        assert abs(r["L_joint_m"] - expected) < 1e-9

    def test_joint_spacing_increases_with_lower_temperature(self):
        """Lower temperature differential → longer allowable joint spacing."""
        r15 = joint_spacing(h_slab_mm=200, delta_temp=15.0)
        r30 = joint_spacing(h_slab_mm=200, delta_temp=30.0)
        assert r15["ok"] and r30["ok"]
        assert r15["L_joint_m"] > r30["L_joint_m"]

    def test_l_over_h_ratio_computed(self):
        """L/h ratio should be computed correctly."""
        r = joint_spacing(h_slab_mm=200, coeff_thermal=10e-6, delta_temp=30, allow_strain=2e-4)
        L_m = 2e-4 / (10e-6 * 30)
        expected_ratio = (L_m * 1000) / 200
        assert abs(r["L_over_h_ratio"] - expected_ratio) < 1e-9

    def test_invalid_h_slab(self):
        r = joint_spacing(h_slab_mm=0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 10. Dowel Bar Size
# ---------------------------------------------------------------------------

class TestDowelBar:

    def test_200mm_slab(self):
        """200 mm slab: d_raw = 200/8 = 25 mm → standard 25 mm."""
        r = dowel_bar_size(h_slab_mm=200)
        assert r["ok"] is True
        assert r["dowel_diameter_mm"] == 25.0

    def test_300mm_slab(self):
        """300 mm slab: d_raw = 300/8 = 37.5 → standard 38 mm."""
        r = dowel_bar_size(h_slab_mm=300)
        assert r["ok"] is True
        assert r["dowel_diameter_mm"] >= 37.5

    def test_spacing_and_length_standard(self):
        r = dowel_bar_size(h_slab_mm=250)
        assert r["ok"] is True
        assert r["dowel_spacing_mm"] == 300.0
        assert r["dowel_length_mm"] == 450.0

    def test_diameter_increases_with_slab_thickness(self):
        r_thin = dowel_bar_size(h_slab_mm=150)
        r_thick = dowel_bar_size(h_slab_mm=350)
        assert r_thin["ok"] and r_thick["ok"]
        assert r_thick["dowel_diameter_mm"] >= r_thin["dowel_diameter_mm"]

    def test_invalid_zero_slab(self):
        r = dowel_bar_size(h_slab_mm=0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 11. Frost Penetration Depth
# ---------------------------------------------------------------------------

class TestFrostDepth:

    def test_stefan_formula(self):
        """Hand-check: z = sqrt(2 × 1.5 × 500 × 86400 / 60e6) ≈ 1.039 m."""
        r = frost_penetration_depth(
            freezing_index_degC_days=500,
            k_soil=1.5,
            L_soil=60e6,
        )
        assert r["ok"] is True
        expected = math.sqrt(2 * 1.5 * 500 * 86400 / 60e6)
        assert abs(r["z_frost_m"] - expected) < 1e-9

    def test_depth_increases_with_freezing_index(self):
        """Higher freezing index → greater frost depth."""
        r200 = frost_penetration_depth(200, 1.5, 60e6)
        r1000 = frost_penetration_depth(1000, 1.5, 60e6)
        assert r200["ok"] and r1000["ok"]
        assert r1000["z_frost_m"] > r200["z_frost_m"]

    def test_depth_decreases_with_higher_latent_heat(self):
        """Higher latent heat (wetter soil) → smaller frost depth."""
        r_dry = frost_penetration_depth(500, 1.5, 30e6)
        r_wet = frost_penetration_depth(500, 1.5, 90e6)
        assert r_dry["ok"] and r_wet["ok"]
        assert r_dry["z_frost_m"] > r_wet["z_frost_m"]

    def test_invalid_zero_latent_heat(self):
        r = frost_penetration_depth(500, 1.5, 0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 12. Overlay Thickness (SN deficiency)
# ---------------------------------------------------------------------------

class TestOverlaySN:

    def test_basic_overlay(self):
        """SN_required=5.0, SN_existing=3.5, a=0.44: D = (5.0-3.5)/0.44 ≈ 3.41 in → round up to 3.5 in."""
        r = overlay_thickness_sn(SN_existing=3.5, SN_required=5.0, a_overlay=0.44)
        assert r["ok"] is True
        assert r["D_overlay_in"] >= 3.4
        # Must be multiple of 0.5 in.
        assert abs(r["D_overlay_in"] * 2 - round(r["D_overlay_in"] * 2)) < 1e-9

    def test_no_overlay_needed(self):
        """SN_existing >= SN_required → D_overlay = 0, warning issued."""
        r = overlay_thickness_sn(SN_existing=5.5, SN_required=4.0, a_overlay=0.44)
        assert r["ok"] is True
        assert r["D_overlay_in"] == 0.0
        assert len(r["warnings"]) > 0

    def test_sn_deficiency_correct(self):
        r = overlay_thickness_sn(SN_existing=2.0, SN_required=4.5, a_overlay=0.44)
        assert r["ok"] is True
        assert abs(r["SN_deficiency"] - 2.5) < 1e-9

    def test_invalid_negative_sn_existing(self):
        r = overlay_thickness_sn(SN_existing=-1.0, SN_required=4.0, a_overlay=0.44)
        assert r["ok"] is False

    def test_invalid_zero_a_overlay(self):
        r = overlay_thickness_sn(SN_existing=2.0, SN_required=4.0, a_overlay=0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 13. Asphalt Quantity
# ---------------------------------------------------------------------------

class TestAsphaltQuantity:

    def test_basic_quantity(self):
        """500m × 7m × 0.05m × 2350 kg/m³ = 41 125 kg."""
        r = asphalt_quantity(length_m=500, width_m=7, thickness_m=0.05)
        assert r["ok"] is True
        assert abs(r["volume_m3"] - 175.0) < 1e-6
        assert abs(r["mass_kg"] - 175.0 * 2350.0) < 0.01
        assert abs(r["mass_tonnes"] - 175.0 * 2350.0 / 1000.0) < 1e-6

    def test_custom_density(self):
        """Custom density changes mass proportionally."""
        r2350 = asphalt_quantity(length_m=100, width_m=6, thickness_m=0.08)
        r2500 = asphalt_quantity(length_m=100, width_m=6, thickness_m=0.08, density_kg_m3=2500)
        assert r2350["ok"] and r2500["ok"]
        assert r2500["mass_kg"] > r2350["mass_kg"]

    def test_area_computed_correctly(self):
        r = asphalt_quantity(length_m=200, width_m=8, thickness_m=0.06)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 1600.0) < 1e-9

    def test_invalid_zero_length(self):
        r = asphalt_quantity(length_m=0, width_m=7, thickness_m=0.05)
        assert r["ok"] is False

    def test_thin_layer_warning(self):
        r = asphalt_quantity(length_m=100, width_m=4, thickness_m=0.01)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0


# ---------------------------------------------------------------------------
# 14. LLM Tool Wrappers — Happy Path
# ---------------------------------------------------------------------------

class TestToolsHappyPath:

    def test_tool_flexible_sn(self):
        r = _call(run_pavement_flexible_sn, {
            "W18": 5e6, "ZR": -1.645, "S0": 0.45, "DPSI": 1.7, "MR": 7500
        })
        assert r["ok"] is True
        assert "SN" in r

    def test_tool_flexible_layers(self):
        r = _call(run_pavement_flexible_layers, {
            "SN": 4.5,
            "layers": [
                {"a": 0.44, "m": 1.0, "type": "asphalt"},
                {"a": 0.14, "m": 1.0, "type": "base"},
            ]
        })
        assert r["ok"] is True
        assert "layers" in r

    def test_tool_esals(self):
        r = _call(run_pavement_esals, {
            "ADT": 5000, "truck_factor": 0.5, "lane_dist": 0.45,
            "dir_dist": 0.5, "design_years": 20, "growth_rate": 0.03
        })
        assert r["ok"] is True
        assert r["W18"] > 0

    def test_tool_esal_growth(self):
        r = _call(run_pavement_esal_growth, {"growth_rate": 0.03, "design_years": 20})
        assert r["ok"] is True
        assert r["growth_factor"] > 20.0

    def test_tool_lef(self):
        r = _call(run_pavement_lef, {"axle_load_kN": 80.0})
        assert r["ok"] is True
        assert abs(r["LEF"] - 1.0) < 1e-9

    def test_tool_cbr_to_mr(self):
        r = _call(run_pavement_cbr_to_mr, {"CBR": 10})
        assert r["ok"] is True
        assert abs(r["MR_psi"] - 15000) < 1e-6

    def test_tool_cbr_to_k(self):
        r = _call(run_pavement_cbr_to_k, {"CBR": 10})
        assert r["ok"] is True
        assert r["k_pci"] > 0

    def test_tool_boussinesq(self):
        r = _call(run_pavement_boussinesq, {"q": 700000, "a": 0.15, "z": 0.3})
        assert r["ok"] is True
        assert 0 < r["stress_ratio"] < 1.0

    def test_tool_rigid_thickness(self):
        r = _call(run_pavement_rigid_thickness, {
            "W18": 5e6, "ZR": -1.282, "S0": 0.35, "DPSI": 2.0,
            "Sc": 650, "Cd": 1.0, "J": 3.2, "Ec": 4e6, "k": 100
        })
        assert r["ok"] is True
        assert r["D_in"] > 0

    def test_tool_joint_spacing(self):
        r = _call(run_pavement_joint_spacing, {"h_slab_mm": 250})
        assert r["ok"] is True
        assert r["L_joint_m"] > 0

    def test_tool_dowel_bar(self):
        r = _call(run_pavement_dowel_bar, {"h_slab_mm": 250})
        assert r["ok"] is True
        assert r["dowel_diameter_mm"] > 0

    def test_tool_frost_depth(self):
        r = _call(run_pavement_frost_depth, {
            "freezing_index_degC_days": 500, "k_soil": 1.5, "L_soil": 60e6
        })
        assert r["ok"] is True
        assert r["z_frost_m"] > 0

    def test_tool_overlay_sn(self):
        r = _call(run_pavement_overlay_sn, {
            "SN_existing": 3.5, "SN_required": 5.0, "a_overlay": 0.44
        })
        assert r["ok"] is True
        assert r["D_overlay_in"] > 0

    def test_tool_asphalt_quantity(self):
        r = _call(run_pavement_asphalt_quantity, {
            "length_m": 500, "width_m": 7, "thickness_m": 0.05
        })
        assert r["ok"] is True
        assert r["mass_tonnes"] > 0


# ---------------------------------------------------------------------------
# 15. LLM Tool Wrappers — Error Paths
# ---------------------------------------------------------------------------

class TestToolsErrorPaths:

    def test_tool_flexible_sn_missing_w18(self):
        r = _call(run_pavement_flexible_sn, {"ZR": -1.282, "S0": 0.45, "DPSI": 1.7, "MR": 7500})
        assert r["ok"] is False

    def test_tool_flexible_layers_missing_sn(self):
        r = _call(run_pavement_flexible_layers, {
            "layers": [{"a": 0.44, "type": "asphalt"}]
        })
        assert r["ok"] is False

    def test_tool_esals_missing_adt(self):
        r = _call(run_pavement_esals, {
            "truck_factor": 0.5, "lane_dist": 0.45, "dir_dist": 0.5,
            "design_years": 20, "growth_rate": 0.03
        })
        assert r["ok"] is False

    def test_tool_lef_missing_axle_load(self):
        r = _call(run_pavement_lef, {})
        assert r["ok"] is False

    def test_tool_cbr_to_mr_invalid_cbr(self):
        r = _call(run_pavement_cbr_to_mr, {"CBR": -5})
        assert r["ok"] is False

    def test_tool_boussinesq_missing_z(self):
        r = _call(run_pavement_boussinesq, {"q": 700000, "a": 0.15})
        assert r["ok"] is False

    def test_tool_rigid_missing_k(self):
        r = _call(run_pavement_rigid_thickness, {
            "W18": 5e6, "ZR": -1.282, "S0": 0.35, "DPSI": 2.0,
            "Sc": 650, "Cd": 1.0, "J": 3.2, "Ec": 4e6
        })
        assert r["ok"] is False

    def test_tool_overlay_missing_sn_existing(self):
        r = _call(run_pavement_overlay_sn, {"SN_required": 4.0, "a_overlay": 0.44})
        assert r["ok"] is False

    def test_tool_frost_depth_missing_k_soil(self):
        r = _call(run_pavement_frost_depth, {
            "freezing_index_degC_days": 500, "L_soil": 60e6
        })
        assert r["ok"] is False

    def test_tool_asphalt_quantity_missing_thickness(self):
        r = _call(run_pavement_asphalt_quantity, {"length_m": 500, "width_m": 7})
        assert r["ok"] is False

    def test_tool_invalid_json(self):
        """Tools must handle malformed JSON without raising."""
        import asyncio
        raw = asyncio.get_event_loop().run_until_complete(
            run_pavement_flexible_sn(_ctx(), b"not valid json{{{")
        )
        r = json.loads(raw)
        # err_payload returns {"error": ..., "code": ...} for parse failures
        assert "error" in r or r.get("ok") is False
