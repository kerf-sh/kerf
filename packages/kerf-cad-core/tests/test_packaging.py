"""
Hermetic tests for kerf_cad_core.packaging — protective-packaging & shipping design.

Coverage:
  design.box_compression_strength — McKee formula, derating, stack-overload flag
  design.pallet_pattern           — column/interlock optimisation, cube utilisation
  design.shipping_weight          — DIM weight, chargeable weight, NMFC freight class
  design.cushion_design           — drop height → thickness, fragility flags
  design.shock_transmissibility   — single-DOF TR, resonance flag
  design.container_fill           — ISO container optimisation, orientation permutations
  design.stretch_wrap             — containment force, EUMOS 40509 compliance
  tools.*                         — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Values verified against McKee (1963), ASTM D1596 energy method, and standard
packaging-engineering hand-calculations.

References
----------
McKee, R.C. (1963) — Box Compression: A Simple Formula.
TAPPI T804 — Compression Test of Fiberboard Shipping Containers.
ASTM D1596 — Shock-Absorbing Characteristics of Packaging Material.
ISTA 2A/2B — Packaged-Product Performance Testing.
EUMOS 40509 — Test Method for Unitised Loads; Containment Force.
NMFC Item 360 — Freight Classification by Density.
ISO 668:2020 — Series 1 Freight Containers — Classification.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.packaging.design import (
    box_compression_strength,
    pallet_pattern,
    shipping_weight,
    cushion_design,
    shock_transmissibility,
    container_fill,
    stretch_wrap,
)
from kerf_cad_core.packaging.tools import (
    run_box_compression_strength,
    run_pallet_pattern,
    run_shipping_weight,
    run_cushion_design,
    run_shock_transmissibility,
    run_container_fill,
    run_stretch_wrap,
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


REL = 1e-6  # relative tolerance


# ===========================================================================
# 1. box_compression_strength — McKee formula
# ===========================================================================

class TestBoxCompressionStrength:

    # -----------------------------------------------------------------------
    # 1a. McKee formula algebraic verification
    # -----------------------------------------------------------------------

    def test_mckee_algebraic_C_flute(self):
        """
        BCT = C_f × ECT × √(Z_m × t_m)
        C-flute: t = 3.6 mm = 0.0036 m
        Z = 1200 mm = 1.2 m
        ECT = 5000 N/m, C_f = 5.874
        """
        ECT = 5000.0   # N/m
        C_f = 5.874
        Z = 1200.0     # mm
        t_m = 3.6 / 1000.0  # C-flute thickness in m
        Z_m = Z / 1000.0

        expected = C_f * ECT * math.sqrt(Z_m * t_m)
        res = box_compression_strength(ECT, C_f, Z, flute="C")
        assert res["ok"] is True
        assert abs(res["BCT_N"] - expected) / expected < REL

    def test_mckee_b_flute_thinner_board_lower_BCT(self):
        """B-flute (t=3.0 mm) must yield lower BCT than C-flute (t=3.6 mm)
        for identical ECT, C_f, Z because t_B < t_C."""
        ECT, C_f, Z = 5000.0, 5.874, 1200.0
        res_B = box_compression_strength(ECT, C_f, Z, flute="B")
        res_C = box_compression_strength(ECT, C_f, Z, flute="C")
        assert res_B["ok"] is True and res_C["ok"] is True
        assert res_B["BCT_N"] < res_C["BCT_N"]

    def test_humidity_derate_applied(self):
        """BCT_derated = BCT × humidity_factor × time_factor."""
        ECT, C_f, Z = 5000.0, 5.874, 1200.0
        hf, tf = 0.7, 0.8
        res = box_compression_strength(ECT, C_f, Z, humidity_factor=hf, time_factor=tf)
        assert abs(res["BCT_derated_N"] - res["BCT_N"] * hf * tf) / res["BCT_derated_N"] < REL

    def test_allowable_equals_derated_over_SF(self):
        """allowable_N = BCT_derated_N / safety_factor."""
        SF = 1.5
        res = box_compression_strength(5000.0, 5.874, 1200.0, safety_factor=SF)
        assert abs(res["allowable_N"] - res["BCT_derated_N"] / SF) / res["allowable_N"] < REL

    def test_stack_overload_flagged(self):
        """Stack-overload warning and flag when stack_load > allowable."""
        res = box_compression_strength(
            5000.0, 5.874, 1200.0,
            safety_factor=1.5,
            humidity_factor=0.6,
            time_factor=0.5,
            stack_load_N=999999.0,  # ridiculously high
        )
        assert res["ok"] is True
        assert res.get("stack_overload") is True
        assert any("STACK-OVERLOAD" in w for w in res["warnings"])

    def test_no_stack_overload_when_adequate(self):
        """No stack-overload when allowable > stack_load_N."""
        res = box_compression_strength(
            5000.0, 5.874, 1200.0,
            safety_factor=1.0,
            stack_load_N=1.0,
        )
        assert res["ok"] is True
        assert res.get("stack_overload") is False

    def test_invalid_flute_returns_error(self):
        res = box_compression_strength(5000.0, 5.874, 1200.0, flute="X")
        assert res["ok"] is False

    def test_negative_ECT_returns_error(self):
        res = box_compression_strength(-100.0, 5.874, 1200.0)
        assert res["ok"] is False

    def test_board_thickness_returned(self):
        """board_thickness_mm must match the known C-flute value 3.6 mm."""
        res = box_compression_strength(5000.0, 5.874, 1200.0, flute="C")
        assert res["ok"] is True
        assert abs(res["board_thickness_mm"] - 3.6) < 1e-9


# ===========================================================================
# 2. pallet_pattern
# ===========================================================================

class TestPalletPattern:

    def test_column_basic_case_count(self):
        """Simple column pattern: 1200×800 mm pallet, 400×300×300 mm case.
        Expected: floor(1200/400)=3 × floor(800/300)=2 = 6 cases/layer."""
        res = pallet_pattern(400, 300, 300, 1200, 800, 1500, pattern="column")
        assert res["ok"] is True
        assert res["cases_per_layer"] >= 6  # may pick rotated orientation

    def test_interlock_matches_or_beats_column(self):
        """auto pattern must return >= cases per pallet as column."""
        res_col = pallet_pattern(400, 300, 300, 1200, 800, 1500, pattern="column")
        res_auto = pallet_pattern(400, 300, 300, 1200, 800, 1500, pattern="auto")
        assert res_auto["ok"] is True
        assert res_auto["cases_per_pallet"] >= res_col["cases_per_pallet"]

    def test_layer_count_from_height(self):
        """layers = floor(max_height / case_H)."""
        case_H = 300.0
        max_H = 1200.0
        expected_layers = int(max_H / case_H)
        res = pallet_pattern(400, 300, case_H, 1200, 800, max_H, pattern="column")
        assert res["ok"] is True
        assert res["layers"] <= expected_layers  # weight capping may reduce

    def test_cube_utilisation_range(self):
        """cube_utilisation must be between 0 and 1."""
        res = pallet_pattern(300, 200, 250, 1200, 800, 2000)
        assert res["ok"] is True
        assert 0.0 <= res["cube_utilisation"] <= 1.0

    def test_area_utilisation_range(self):
        res = pallet_pattern(300, 200, 250, 1200, 800, 2000)
        assert 0.0 <= res["area_utilisation"] <= 1.0

    def test_pallet_weight_computed_when_case_weight_given(self):
        res = pallet_pattern(
            300, 200, 250, 1200, 800, 2000,
            case_weight_kg=5.0,
        )
        assert res["ok"] is True
        assert "pallet_weight_kg" in res
        assert res["pallet_weight_kg"] == pytest.approx(
            5.0 * res["cases_per_pallet"], rel=1e-6
        )

    def test_invalid_pattern_returns_error(self):
        res = pallet_pattern(300, 200, 250, 1200, 800, 2000, pattern="spiral")
        assert res["ok"] is False

    def test_zero_case_dim_returns_error(self):
        res = pallet_pattern(0, 200, 250, 1200, 800, 2000)
        assert res["ok"] is False


# ===========================================================================
# 3. shipping_weight
# ===========================================================================

class TestShippingWeight:

    def test_dim_weight_domestic(self):
        """DIM weight = volume_cm³ / 5000 for domestic."""
        L, W, H = 500.0, 400.0, 300.0  # mm
        vol_cm3 = (L / 10) * (W / 10) * (H / 10)
        expected_dim = vol_cm3 / 5000.0
        res = shipping_weight(L, W, H, 2.0, carrier="domestic")
        assert res["ok"] is True
        assert abs(res["dim_weight_kg"] - expected_dim) / expected_dim < REL

    def test_dim_weight_international(self):
        """DIM weight = volume_cm³ / 6000 for international."""
        L, W, H = 500.0, 400.0, 300.0
        vol_cm3 = (L / 10) * (W / 10) * (H / 10)
        expected_dim = vol_cm3 / 6000.0
        res = shipping_weight(L, W, H, 2.0, carrier="international")
        assert abs(res["dim_weight_kg"] - expected_dim) / expected_dim < REL

    def test_chargeable_weight_is_max(self):
        """chargeable_weight = max(actual, DIM)."""
        res = shipping_weight(1000, 1000, 1000, 0.001)  # huge but very light → DIM > actual
        assert res["ok"] is True
        assert res["chargeable_weight_kg"] == pytest.approx(
            max(res["actual_kg"] if "actual_kg" in res else 0.001, res["dim_weight_kg"]),
            rel=1e-6,
        )
        # DIM must dominate
        assert res["chargeable_weight_kg"] >= res["dim_weight_kg"] - 1e-9

    def test_chargeable_is_actual_when_dense(self):
        """Dense small package: actual > DIM → chargeable = actual."""
        res = shipping_weight(100, 100, 100, 100.0)  # 100 kg in 10×10×10 cm = very dense
        assert res["ok"] is True
        assert res["chargeable_weight_kg"] == pytest.approx(100.0, rel=1e-6)

    def test_nmfc_class_dense_item(self):
        """Very dense shipment → freight class 50 (lowest, cheapest)."""
        # 1 kg in a 50×50×50 mm box → density ~ 320 lb/ft³ >> 50 lb/ft³
        res = shipping_weight(50, 50, 50, 1.0)
        assert res["ok"] is True
        assert res["freight_class"] == 50.0

    def test_nmfc_class_low_density(self):
        """Low-density shipment → high freight class."""
        # 0.1 kg in 1000×1000×1000 mm box → very low density → class 500
        res = shipping_weight(1000, 1000, 1000, 0.1)
        assert res["ok"] is True
        assert res["freight_class"] >= 300.0

    def test_freight_class_override(self):
        """override forces the exact class."""
        res = shipping_weight(500, 400, 300, 5.0, freight_class_override=175.0)
        assert res["ok"] is True
        assert res["freight_class"] == 175.0

    def test_invalid_carrier_returns_error(self):
        res = shipping_weight(500, 400, 300, 5.0, carrier="expedited")
        assert res["ok"] is False

    def test_negative_weight_returns_error(self):
        res = shipping_weight(500, 400, 300, -1.0)
        assert res["ok"] is False


# ===========================================================================
# 4. cushion_design
# ===========================================================================

class TestCushionDesign:

    def _delta_V(self, h):
        return math.sqrt(2.0 * 9.81 * h)

    def _t_required(self, h, G_allow):
        dv = self._delta_V(h)
        return dv**2 / (2.0 * G_allow * 9.81) * 1000.0  # mm

    def test_delta_V_formula(self):
        """ΔV = √(2 g h) must match returned delta_V_m_s."""
        h = 0.6
        res = cushion_design(2.0, h, 50.0, 5.0, 25.0)
        assert res["ok"] is True
        assert abs(res["delta_V_m_s"] - self._delta_V(h)) < 1e-9

    def test_thickness_algebraic(self):
        """required_thickness_mm = ΔV² / (2 × G_allow × g) × 1000."""
        h, G_frag, SF = 0.5, 60.0, 1.5
        G_allow = G_frag / SF
        expected_t = self._t_required(h, G_allow)
        res = cushion_design(1.0, h, G_frag, 3.0, 20.0, safety_factor=SF)
        assert res["ok"] is True
        assert abs(res["required_thickness_mm"] - expected_t) / expected_t < REL

    def test_g_allow_equals_fragility_over_sf(self):
        """G_allow = fragility_G / safety_factor."""
        G_frag, SF = 80.0, 2.0
        res = cushion_design(1.0, 0.5, G_frag, 3.0, 20.0, safety_factor=SF)
        assert res["ok"] is True
        assert abs(res["G_allow"] - G_frag / SF) < 1e-9

    def test_greater_drop_height_increases_thickness(self):
        """Higher drop height must require thicker cushion."""
        t1 = cushion_design(2.0, 0.3, 50.0, 5.0, 20.0)["required_thickness_mm"]
        t2 = cushion_design(2.0, 0.9, 50.0, 5.0, 20.0)["required_thickness_mm"]
        assert t2 > t1

    def test_higher_fragility_thinner_cushion(self):
        """Higher fragility_G (product can take more shock) → thinner cushion."""
        t1 = cushion_design(2.0, 0.5, 30.0, 5.0, 15.0)["required_thickness_mm"]
        t2 = cushion_design(2.0, 0.5, 80.0, 5.0, 15.0)["required_thickness_mm"]
        assert t2 < t1

    def test_under_cushioned_flag(self):
        """under_cushioned when foam G-curve > fragility_G."""
        res = cushion_design(2.0, 0.5, 40.0, 5.0, 60.0)  # foam_curve_G=60 > frag=40
        assert res["ok"] is True
        assert res["under_cushioned"] is True
        assert any("UNDER-CUSHIONED" in w for w in res["warnings"])

    def test_fragile_exceeded_flag(self):
        """fragile_exceeded when foam G-curve > G_allow but <= fragility_G."""
        # G_allow = 60 / 1.5 = 40.  foam_curve=45 > G_allow but <= frag=60
        res = cushion_design(2.0, 0.5, 60.0, 5.0, 45.0, safety_factor=1.5)
        assert res["ok"] is True
        assert res["fragile_exceeded"] is True

    def test_fragility_G_le_1_returns_error(self):
        res = cushion_design(2.0, 0.5, 0.5, 5.0, 10.0)
        assert res["ok"] is False

    def test_negative_drop_height_returns_error(self):
        res = cushion_design(2.0, -0.3, 50.0, 5.0, 20.0)
        assert res["ok"] is False

    def test_static_stress_returned(self):
        """static_stress_kPa = weight × g / bearing_area (Pa → kPa)."""
        mass = 2.0
        area_cm2 = 100.0
        area_m2 = area_cm2 * 1e-4
        expected_kPa = (mass * 9.81 / area_m2) / 1000.0
        res = cushion_design(mass, 0.5, 50.0, expected_kPa, 20.0, bearing_area_cm2=area_cm2)
        assert res["ok"] is True
        assert abs(res["static_stress_kPa"] - expected_kPa) / expected_kPa < REL


# ===========================================================================
# 5. shock_transmissibility
# ===========================================================================

class TestShockTransmissibility:

    def _T(self, fn, zeta, f_in):
        r = f_in / fn
        num = 1.0 + (2 * zeta * r) ** 2
        den = (1 - r**2) ** 2 + (2 * zeta * r) ** 2
        return math.sqrt(num / den)

    def test_transmissibility_algebraic(self):
        """Verify transmissibility formula against hand-calc."""
        fn, zeta, f_in = 5.0, 0.1, 2.0
        T_expected = self._T(fn, zeta, f_in)
        res = shock_transmissibility(fn, zeta, f_in)
        assert res["ok"] is True
        assert abs(res["transmissibility"] - T_expected) / T_expected < REL

    def test_isolation_region_r_gt_sqrt2(self):
        """For r > √2 and any damping, T < 1 (isolation)."""
        fn = 3.0
        f_in = fn * 1.5  # r = 1.5 > √2
        res = shock_transmissibility(fn, 0.05, f_in)
        assert res["ok"] is True
        assert res["transmissibility"] < 1.0

    def test_amplification_region_r_lt_sqrt2(self):
        """For r < √2 (excl. resonance), T > 1 (amplification) with low damping."""
        fn, zeta = 10.0, 0.02
        f_in = fn * 1.0  # exactly at resonance — transmissibility >> 1
        res = shock_transmissibility(fn, zeta, f_in)
        assert res["ok"] is True
        assert res["transmissibility"] > 1.0

    def test_resonance_flag_near_r_equals_1(self):
        """resonance_warning must be True when r is within 5% of 1."""
        fn = 10.0
        f_in = fn * 1.02  # r = 1.02 → within 5%
        res = shock_transmissibility(fn, 0.05, f_in)
        assert res["ok"] is True
        assert res["resonance_warning"] is True

    def test_no_resonance_flag_far_from_r_equals_1(self):
        """resonance_warning must be False when r >> 1."""
        res = shock_transmissibility(5.0, 0.1, 20.0)  # r = 4.0
        assert res["ok"] is True
        assert res["resonance_warning"] is False

    def test_attenuation_dB_formula(self):
        """attenuation_dB = -20 log10(T)."""
        fn, zeta, f_in = 4.0, 0.15, 2.0
        res = shock_transmissibility(fn, zeta, f_in)
        T = res["transmissibility"]
        expected_dB = -20.0 * math.log10(T)
        assert abs(res["attenuation_dB"] - expected_dB) < 1e-9

    def test_overdamped_returns_error(self):
        """damping_ratio >= 1.0 must return error."""
        res = shock_transmissibility(5.0, 1.0, 10.0)
        assert res["ok"] is False

    def test_negative_fn_returns_error(self):
        res = shock_transmissibility(-1.0, 0.1, 5.0)
        assert res["ok"] is False


# ===========================================================================
# 6. container_fill
# ===========================================================================

class TestContainerFill:

    # 40GP internal: 12025 × 2352 × 2393 mm
    _CON_L = 12_025.0
    _CON_W = 2_352.0
    _CON_H = 2_393.0

    def test_total_cases_40GP_known(self):
        """400×300×250 mm cases in 40GP, no rotation: manual count."""
        cL, cW, cH = 400.0, 300.0, 250.0
        n_row = int(self._CON_L / cL)
        n_col = int(self._CON_W / cW)
        n_lay = int(self._CON_H / cH)
        expected = n_row * n_col * n_lay
        res = container_fill(cL, cW, cH, "40GP", orientation_permutations=False)
        assert res["ok"] is True
        assert res["total_cases"] == expected

    def test_orientation_permutations_ge_no_permutation(self):
        """Allowing orientation permutations must yield >= cases than fixed orientation."""
        cL, cW, cH = 600.0, 400.0, 300.0
        res_fixed = container_fill(cL, cW, cH, orientation_permutations=False)
        res_perms = container_fill(cL, cW, cH, orientation_permutations=True)
        assert res_perms["total_cases"] >= res_fixed["total_cases"]

    def test_20GP_smaller_than_40GP(self):
        """20GP must hold fewer cases than 40GP for the same case size."""
        cL, cW, cH = 500.0, 300.0, 300.0
        res_20 = container_fill(cL, cW, cH, "20GP")
        res_40 = container_fill(cL, cW, cH, "40GP")
        assert res_40["total_cases"] > res_20["total_cases"]

    def test_40HC_vs_40GP_more_layers(self):
        """40HC is taller than 40GP; more layers for tall cases."""
        # 40HC H = 2698 mm vs 40GP H = 2393 mm
        cL, cW, cH = 400.0, 300.0, 500.0  # tall case forces HC advantage
        res_gp = container_fill(cL, cW, cH, "40GP", orientation_permutations=False)
        res_hc = container_fill(cL, cW, cH, "40HC", orientation_permutations=False)
        # HC should fit at least as many as GP
        assert res_hc["total_cases"] >= res_gp["total_cases"]

    def test_volume_utilisation_range(self):
        """volume_utilisation in [0, 1]."""
        res = container_fill(400, 300, 250, "40GP")
        assert res["ok"] is True
        assert 0.0 <= res["volume_utilisation"] <= 1.0

    def test_invalid_container_type(self):
        res = container_fill(400, 300, 250, "10GP")
        assert res["ok"] is False

    def test_internal_dims_returned(self):
        """Internal container dimensions must match known ISO values."""
        res = container_fill(400, 300, 250, "40GP")
        assert res["ok"] is True
        assert res["internal_L_mm"] == pytest.approx(12025.0, rel=1e-6)
        assert res["internal_W_mm"] == pytest.approx(2352.0, rel=1e-6)


# ===========================================================================
# 7. stretch_wrap
# ===========================================================================

class TestStretchWrap:

    def test_eumos_minimum_formula(self):
        """F_min_required_N = 0.4 × W_kg × 9.81."""
        W = 800.0
        res = stretch_wrap(W, 23.0)
        assert res["ok"] is True
        assert abs(res["F_min_required_N"] - 0.4 * W * 9.81) / res["F_min_required_N"] < REL

    def test_more_revolutions_increase_force(self):
        """F_total proportional to revolutions."""
        r1 = stretch_wrap(600.0, 23.0, revolutions=3)
        r2 = stretch_wrap(600.0, 23.0, revolutions=6)
        assert r2["F_total_N"] == pytest.approx(r1["F_total_N"] * 2.0, rel=1e-9)

    def test_eumos_compliance_enough_revolutions(self):
        """With revolutions_for_minimum revolutions, eumos_compliant must be True."""
        W, gauge = 500.0, 23.0
        r = stretch_wrap(W, gauge, revolutions=1)
        min_rev = r["revolutions_for_minimum"]
        r2 = stretch_wrap(W, gauge, revolutions=min_rev)
        assert r2["eumos_compliant"] is True

    def test_eumos_insufficient_warning(self):
        """With very few revolutions, EUMOS warning must appear."""
        res = stretch_wrap(5000.0, 17.0, revolutions=1)
        assert res["ok"] is True
        if not res["eumos_compliant"]:
            assert any("EUMOS" in w for w in res["warnings"])

    def test_thin_film_warning(self):
        """Film gauge < 17 μm must trigger thin-film warning."""
        res = stretch_wrap(500.0, 12.0)
        assert res["ok"] is True
        assert any("17" in w for w in res["warnings"])

    def test_zero_revolutions_returns_error(self):
        res = stretch_wrap(500.0, 23.0, revolutions=0)
        assert res["ok"] is False

    def test_negative_weight_returns_error(self):
        res = stretch_wrap(-100.0, 23.0)
        assert res["ok"] is False

    def test_revolutions_for_minimum_is_positive(self):
        """revolutions_for_minimum must always be a positive integer."""
        res = stretch_wrap(400.0, 20.0, revolutions=3)
        assert res["ok"] is True
        assert isinstance(res["revolutions_for_minimum"], int)
        assert res["revolutions_for_minimum"] >= 1


# ===========================================================================
# 8. LLM Tool wrappers — happy paths
# ===========================================================================

class TestToolsHappyPath:

    def test_tool_box_compression(self):
        raw = _run(run_box_compression_strength(
            _ctx(),
            _args(ECT=5000.0, C_f=5.874, Z=1200.0, flute="C"),
        ))
        d = _ok_tool(raw)
        assert d["BCT_N"] > 0

    def test_tool_pallet_pattern(self):
        raw = _run(run_pallet_pattern(
            _ctx(),
            _args(case_L=400, case_W=300, case_H=300,
                  pallet_L=1200, pallet_W=800, max_height=2000),
        ))
        d = _ok_tool(raw)
        assert d["cases_per_pallet"] > 0

    def test_tool_shipping_weight(self):
        raw = _run(run_shipping_weight(
            _ctx(),
            _args(length_mm=500, width_mm=400, height_mm=300, actual_kg=5.0),
        ))
        d = _ok_tool(raw)
        assert d["chargeable_weight_kg"] >= d["dim_weight_kg"] - 1e-9

    def test_tool_cushion_design(self):
        raw = _run(run_cushion_design(
            _ctx(),
            _args(product_weight_kg=2.0, drop_height_m=0.6, fragility_G=50.0,
                  foam_static_stress_kPa=4.0, foam_cushion_curve_G=25.0),
        ))
        d = _ok_tool(raw)
        assert d["required_thickness_mm"] > 0

    def test_tool_shock_transmissibility(self):
        raw = _run(run_shock_transmissibility(
            _ctx(),
            _args(fn_Hz=5.0, damping_ratio=0.1, input_freq_Hz=10.0),
        ))
        d = _ok_tool(raw)
        assert "transmissibility" in d

    def test_tool_container_fill(self):
        raw = _run(run_container_fill(
            _ctx(),
            _args(case_L=400, case_W=300, case_H=250, container_type="40GP"),
        ))
        d = _ok_tool(raw)
        assert d["total_cases"] > 0

    def test_tool_stretch_wrap(self):
        raw = _run(run_stretch_wrap(
            _ctx(),
            _args(pallet_weight_kg=600.0, film_gauge_um=23.0, revolutions=5),
        ))
        d = _ok_tool(raw)
        assert d["F_total_N"] > 0


# ===========================================================================
# 9. LLM Tool wrappers — error paths
# ===========================================================================

class TestToolsErrorPaths:

    def test_box_compression_missing_ECT(self):
        raw = _run(run_box_compression_strength(_ctx(), _args(C_f=5.874, Z=1200.0)))
        _err_tool(raw)

    def test_pallet_pattern_missing_case_L(self):
        raw = _run(run_pallet_pattern(
            _ctx(),
            _args(case_W=300, case_H=300, pallet_L=1200, pallet_W=800, max_height=2000),
        ))
        _err_tool(raw)

    def test_shipping_weight_missing_actual_kg(self):
        raw = _run(run_shipping_weight(_ctx(), _args(length_mm=500, width_mm=400, height_mm=300)))
        _err_tool(raw)

    def test_cushion_design_missing_drop_height(self):
        raw = _run(run_cushion_design(
            _ctx(),
            _args(product_weight_kg=2.0, fragility_G=50.0,
                  foam_static_stress_kPa=4.0, foam_cushion_curve_G=25.0),
        ))
        _err_tool(raw)

    def test_shock_transmissibility_missing_fn(self):
        raw = _run(run_shock_transmissibility(_ctx(), _args(damping_ratio=0.1, input_freq_Hz=10.0)))
        _err_tool(raw)

    def test_container_fill_missing_case_H(self):
        raw = _run(run_container_fill(_ctx(), _args(case_L=400, case_W=300)))
        _err_tool(raw)

    def test_stretch_wrap_missing_film_gauge(self):
        raw = _run(run_stretch_wrap(_ctx(), _args(pallet_weight_kg=500.0)))
        _err_tool(raw)

    def test_invalid_json_returns_error(self):
        raw = _run(run_box_compression_strength(_ctx(), b"not-json"))
        _err_tool(raw)
