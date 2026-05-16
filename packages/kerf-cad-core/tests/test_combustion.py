"""
Hermetic tests for kerf_cad_core.combustion — combustion & fuels engineering.

Coverage:
  burn.stoich_afr             — stoichiometric AFR (mass & molar), CxHyOz formulas
  burn.equivalence_ratio      — φ ↔ λ ↔ excess-air conversions
  burn.product_composition    — flue-gas composition wet/dry, ppm
  burn.adiabatic_flame_temp   — iterative AFT energy balance
  burn.hhv_to_lhv             — HHV ↔ LHV water-latent correction
  burn.combustion_efficiency  — Siegert flue-gas heat loss & η
  burn.flue_gas_dew_point     — Antoine dew-point from H2O fraction
  burn.co2_max                — stoichiometric dry CO2%
  burn.fuel_power             — fuel power & SFC
  tools.*                     — LLM wrapper happy paths + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Values verified against Turns "An Introduction to Combustion" 3rd ed.,
Baukal "John Zink Hamworthy Combustion Handbook", and hand calculations.

References
----------
Turns, S.R., "An Introduction to Combustion", 3rd ed.
Baukal, C.E. (ed.), "The John Zink Hamworthy Combustion Handbook", 2nd ed.
Borman, G.L. & Ragland, K.W., "Combustion Engineering"

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import warnings

import pytest

from kerf_cad_core.combustion.burn import (
    stoich_afr,
    equivalence_ratio,
    product_composition,
    adiabatic_flame_temp,
    hhv_to_lhv,
    combustion_efficiency,
    flue_gas_dew_point,
    co2_max,
    fuel_power,
    FUELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. stoich_afr — methane CH4
# ---------------------------------------------------------------------------

class TestStoichAFR:
    def test_methane_afr_mass(self):
        """CH4 stoichiometric AFR_mass ≈ 17.23 (Turns Table 2.1)."""
        r = stoich_afr(C=1, H=4)
        # Hand-calc: n_O2 = 1 + 4/4 = 2; n_air = 2/0.2095 = 9.547;
        # MW_CH4 = 16.043; AFR_mass = 9.547*28.966/16.043 ≈ 17.23
        assert abs(r["AFR_mass"] - 17.23) < 0.15, r

    def test_methane_n_o2(self):
        r = stoich_afr(C=1, H=4)
        assert abs(r["n_O2_stoich"] - 2.0) < 1e-6

    def test_propane_afr_mass(self):
        """C3H8: n_O2 = 3+8/4 = 5; AFR_mass ≈ 15.6."""
        r = stoich_afr(C=3, H=8)
        assert abs(r["AFR_mass"] - 15.6) < 0.15, r

    def test_ethanol_afr_mass(self):
        """C2H6O (ethanol): n_O2 = 2+6/4-1/2 = 3.0; AFR_mass ≈ 9.0."""
        r = stoich_afr(C=2, H=6, O=1)
        # n_O2=3.0; n_air=3/0.2095=14.32; MW_C2H6O=46.068; AFR=14.32*28.966/46.068≈9.0
        assert abs(r["AFR_mass"] - 9.0) < 0.15, r

    def test_hydrogen_afr(self):
        """H2: n_O2 = 0.5; AFR_mass = (0.5/0.2095)*28.966/2.016 ≈ 34.3."""
        r = stoich_afr(C=0, H=2)
        assert abs(r["AFR_mass"] - 34.3) < 0.5, r

    def test_mw_fuel_methane(self):
        r = stoich_afr(C=1, H=4)
        assert abs(r["MW_fuel_g_mol"] - 16.043) < 0.01

    def test_fuel_name_label(self):
        r = stoich_afr(C=1, H=4, fuel_name="methane")
        assert r["fuel_name"] == "methane"

    def test_zero_hydrogen(self):
        """Pure carbon C: n_O2 = 1; no H2O produced."""
        r = stoich_afr(C=1, H=0)
        assert abs(r["n_O2_stoich"] - 1.0) < 1e-6

    def test_negative_atoms_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = stoich_afr(C=-1, H=4)
        assert r["warnings"]  # warns about clamp


# ---------------------------------------------------------------------------
# 2. equivalence_ratio conversions
# ---------------------------------------------------------------------------

class TestEquivalenceRatio:
    def test_stoich_phi_one(self):
        r = equivalence_ratio(phi=1.0)
        assert abs(r["phi"] - 1.0) < 1e-9
        assert abs(r["lambda_"] - 1.0) < 1e-9
        assert abs(r["excess_air_pct"]) < 1e-6
        assert r["mixture"] == "stoichiometric"

    def test_from_excess_air_20pct(self):
        """20% excess air → λ=1.2, φ≈0.833."""
        r = equivalence_ratio(excess_air_pct=20.0)
        assert abs(r["lambda_"] - 1.2) < 1e-6
        assert abs(r["phi"] - 1.0 / 1.2) < 1e-6
        assert r["mixture"] == "lean"

    def test_from_lambda_lean(self):
        r = equivalence_ratio(lambda_=1.5)
        assert abs(r["phi"] - 1.0 / 1.5) < 1e-5   # rounded to 6 dp
        assert abs(r["excess_air_pct"] - 50.0) < 1e-3

    def test_rich_mixture_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = equivalence_ratio(phi=1.2)
        assert r["mixture"] == "rich"
        assert r["warnings"]

    def test_from_afr_actual_stoich(self):
        # CH4 stoich ≈ 17.23; actual 20.0 → lean
        r = equivalence_ratio(afr_actual=20.0, afr_stoich=17.23)
        assert r["phi"] < 1.0
        assert r["mixture"] == "lean"

    def test_no_input_returns_error(self):
        r = equivalence_ratio()
        assert r.get("ok") is False

    def test_invalid_phi_zero(self):
        r = equivalence_ratio(phi=0.0)
        assert r.get("ok") is False


# ---------------------------------------------------------------------------
# 3. product_composition — stoichiometric CH4
# ---------------------------------------------------------------------------

class TestProductComposition:
    def test_methane_stoich_co2_dry(self):
        """CH4 at λ=1: CO2_dry ≈ 11.7% (hand-calc)."""
        r = product_composition(C=1, H=4, excess_air_pct=0.0)
        # n_CO2=1, n_H2O=2, n_N2=2/0.2095*(1-0.2095)=7.524, n_O2=0
        # dry: CO2/(1+7.524)=1/8.524≈11.73%
        assert abs(r["CO2_dry_pct"] - 11.73) < 0.3, r["CO2_dry_pct"]

    def test_methane_stoich_h2o_wet(self):
        """H2O wet fraction: n_H2O=2 / (1+2+7.524)≈19.3%."""
        r = product_composition(C=1, H=4, excess_air_pct=0.0)
        assert abs(r["H2O_wet_pct"] - 19.3) < 0.5, r["H2O_wet_pct"]

    def test_methane_excess_air_o2(self):
        """10% excess air → O2_dry > 0 and < 4%."""
        r = product_composition(C=1, H=4, excess_air_pct=10.0)
        # n_O2_excess = 0.1*2 = 0.2 mol
        assert r["O2_dry_pct"] > 0.5
        assert r["O2_dry_pct"] < 4.0

    def test_propane_stoich_co2_dry(self):
        """C3H8 CO2_dry at λ=1 ≈ 13.7% (standard reference)."""
        r = product_composition(C=3, H=8, excess_air_pct=0.0)
        assert abs(r["CO2_dry_pct"] - 13.7) < 0.5, r["CO2_dry_pct"]

    def test_rich_mixture_warns(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            r = product_composition(C=1, H=4, excess_air_pct=-10.0)
        assert r["warnings"]

    def test_ppm_consistency(self):
        """ppm values consistent with pct values."""
        r = product_composition(C=1, H=4, excess_air_pct=0.0)
        assert abs(r["CO2_dry_ppm"] / 1e4 - r["CO2_dry_pct"]) < 0.01

    def test_zero_o2_at_stoich(self):
        r = product_composition(C=1, H=4, excess_air_pct=0.0)
        assert r["O2_dry_pct"] < 1e-6

    def test_fuel_with_sulphur(self):
        r = product_composition(C=1, H=4, O=0, N=0, S=1, excess_air_pct=0.0)
        assert r["n_SO2"] == 1.0


# ---------------------------------------------------------------------------
# 4. adiabatic_flame_temp
# ---------------------------------------------------------------------------

class TestAdiabaticFlameTemp:
    def test_methane_stoich_aft_range(self):
        """CH4 stoichiometric AFT with LHV should be ~2230 K (±150 K)."""
        r = adiabatic_flame_temp(
            C=1, H=4,
            LHV_MJ_kg=50.05,
            MW_fuel=16.043,
        )
        assert 2050 < r["T_ad_K"] < 2400, r["T_ad_K"]

    def test_converged_flag(self):
        r = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043)
        assert r["converged"] is True

    def test_excess_air_lowers_aft(self):
        """Higher excess air → lower AFT."""
        r0 = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043,
                                   excess_air_pct=0.0)
        r20 = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043,
                                    excess_air_pct=20.0)
        assert r20["T_ad_K"] < r0["T_ad_K"]

    def test_hotter_reactants_raises_aft(self):
        r_cold = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043,
                                       T_reactants=298.15)
        r_hot = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043,
                                      T_reactants=500.0)
        assert r_hot["T_ad_K"] > r_cold["T_ad_K"]

    def test_propane_aft_range(self):
        r = adiabatic_flame_temp(C=3, H=8, LHV_MJ_kg=46.36, MW_fuel=44.096)
        assert 2100 < r["T_ad_K"] < 2500, r["T_ad_K"]

    def test_celsius_consistent_with_kelvin(self):
        r = adiabatic_flame_temp(C=1, H=4, LHV_MJ_kg=50.05, MW_fuel=16.043)
        assert abs(r["T_ad_K"] - r["T_ad_C"] - 273.15) < 0.01


# ---------------------------------------------------------------------------
# 5. hhv_to_lhv
# ---------------------------------------------------------------------------

class TestHHVtoLHV:
    def test_methane_delta(self):
        """CH4: HHV=55.53 MJ/kg → LHV≈50.05 MJ/kg; Δ≈5.48 MJ/kg."""
        r = hhv_to_lhv(HHV_MJ_kg=55.53, C=1, H=4, MW_fuel=16.043)
        assert abs(r["delta_MJ_kg"] - 5.48) < 0.15, r["delta_MJ_kg"]
        assert abs(r["LHV_MJ_kg"] - 50.05) < 0.15, r["LHV_MJ_kg"]

    def test_lhv_less_than_hhv(self):
        r = hhv_to_lhv(HHV_MJ_kg=55.53, C=1, H=4, MW_fuel=16.043)
        assert r["LHV_MJ_kg"] < r["HHV_MJ_kg"]

    def test_lhv_to_hhv_direction(self):
        r = hhv_to_lhv(HHV_MJ_kg=50.05, C=1, H=4, MW_fuel=16.043,
                       direction="lhv_to_hhv")
        assert r["HHV_MJ_kg"] > r["LHV_MJ_kg"]
        assert abs(r["HHV_MJ_kg"] - 55.53) < 0.15

    def test_hydrogen_large_delta(self):
        """H2 has large H2O fraction → large Δ."""
        r = hhv_to_lhv(HHV_MJ_kg=141.79, C=0, H=2, MW_fuel=2.016)
        assert r["delta_MJ_kg"] > 20.0

    def test_invalid_hv(self):
        r = hhv_to_lhv(HHV_MJ_kg=-1.0, C=1, H=4)
        assert r.get("ok") is False

    def test_h2o_mass_frac_methane(self):
        """CH4: H=4 → n_H2O=2 mol; mass H2O per kg fuel = 2*18.015/16.043 ≈ 2.246."""
        r = hhv_to_lhv(HHV_MJ_kg=55.53, C=1, H=4, MW_fuel=16.043)
        # H2O_mass_frac = (H/2 * MW_H2O) / MW_fuel = 2*18.015/16.043 ≈ 2.246
        assert 2.0 < r["H2O_mass_frac"] < 2.5


# ---------------------------------------------------------------------------
# 6. combustion_efficiency (Siegert)
# ---------------------------------------------------------------------------

class TestCombustionEfficiency:
    def test_siegert_methane_typical(self):
        """Natural gas boiler: T_flue=120°C, T_amb=15°C, CO2=9% → η≈91%."""
        r = combustion_efficiency(
            T_flue_C=120, T_ambient_C=15, CO2_dry_pct=9.0, fuel="natural_gas"
        )
        # q_A = (120-15)*(0.68/9.0 + 0.0071) = 105*(0.07556+0.0071)=105*0.08266≈8.68%
        # η ≈ 91.3%
        assert abs(r["eta_pct"] - 91.3) < 1.5, r["eta_pct"]

    def test_higher_flue_temp_lower_eta(self):
        r1 = combustion_efficiency(T_flue_C=100, T_ambient_C=15, CO2_dry_pct=9.0)
        r2 = combustion_efficiency(T_flue_C=200, T_ambient_C=15, CO2_dry_pct=9.0)
        assert r2["eta_pct"] < r1["eta_pct"]

    def test_o2_based_input(self):
        """Estimate CO2 from O2 measurement."""
        r = combustion_efficiency(
            T_flue_C=150, T_ambient_C=20,
            O2_dry_pct=4.0, CO2_max_pct=11.7,
            fuel="natural_gas",
        )
        assert r["eta_pct"] is not None
        assert 80.0 < r["eta_pct"] < 100.0

    def test_no_co2_no_siegert(self):
        r = combustion_efficiency(T_flue_C=150, T_ambient_C=20)
        assert r["eta_pct"] is None
        assert r["q_A_pct"] is None

    def test_oil_fuel_lower_eta(self):
        """Oil has higher B1 → higher loss for same conditions."""
        r_gas = combustion_efficiency(T_flue_C=150, T_ambient_C=20,
                                      CO2_dry_pct=10.0, fuel="natural_gas")
        r_oil = combustion_efficiency(T_flue_C=150, T_ambient_C=20,
                                      CO2_dry_pct=10.0, fuel="oil")
        assert r_oil["eta_pct"] < r_gas["eta_pct"]


# ---------------------------------------------------------------------------
# 7. flue_gas_dew_point
# ---------------------------------------------------------------------------

class TestFlueGasDewPoint:
    def test_methane_stoich_dew_point(self):
        """CH4 stoich wet product: H2O_wet≈19.3% → dew point ~58-60°C."""
        r = product_composition(C=1, H=4, excess_air_pct=0.0)
        dp = flue_gas_dew_point(H2O_wet_pct=r["H2O_wet_pct"])
        assert 50.0 < dp["T_dew_C"] < 70.0, dp["T_dew_C"]

    def test_pct_vs_frac_consistent(self):
        dp_pct = flue_gas_dew_point(H2O_wet_pct=15.0)
        dp_frac = flue_gas_dew_point(H2O_wet_frac=0.15)
        assert abs(dp_pct["T_dew_C"] - dp_frac["T_dew_C"]) < 0.01

    def test_higher_h2o_higher_dew_point(self):
        dp1 = flue_gas_dew_point(H2O_wet_pct=10.0)
        dp2 = flue_gas_dew_point(H2O_wet_pct=20.0)
        assert dp2["T_dew_C"] > dp1["T_dew_C"]

    def test_p_h2o_consistent(self):
        dp = flue_gas_dew_point(H2O_wet_frac=0.10, p_total_Pa=101325.0)
        assert abs(dp["p_H2O_Pa"] - 0.10 * 101325.0) < 1.0

    def test_invalid_fraction(self):
        r = flue_gas_dew_point(H2O_wet_frac=1.5)
        assert r.get("ok") is False

    def test_no_input_error(self):
        r = flue_gas_dew_point()
        assert r.get("ok") is False


# ---------------------------------------------------------------------------
# 8. co2_max
# ---------------------------------------------------------------------------

class TestCO2Max:
    def test_methane_co2_max(self):
        """CH4 CO2_max_dry ≈ 11.7%."""
        r = co2_max(C=1, H=4)
        assert abs(r["CO2_max_dry_pct"] - 11.73) < 0.5, r["CO2_max_dry_pct"]

    def test_propane_co2_max(self):
        """C3H8 CO2_max_dry ≈ 13.7%."""
        r = co2_max(C=3, H=8)
        assert abs(r["CO2_max_dry_pct"] - 13.7) < 0.5, r["CO2_max_dry_pct"]

    def test_pure_carbon_co2_max(self):
        """Pure C: CO2 is 100% of dry products."""
        r = co2_max(C=1, H=0)
        assert abs(r["CO2_max_dry_pct"] - 21.0) < 1.0   # ~21% (CO2/(CO2+N2)) at stoich

    def test_co2_max_dry_ge_wet(self):
        """Dry CO2% ≥ wet CO2% since H2O removed."""
        r = co2_max(C=1, H=4)
        assert r["CO2_max_dry_pct"] >= r["CO2_max_wet_pct"]


# ---------------------------------------------------------------------------
# 9. fuel_power
# ---------------------------------------------------------------------------

class TestFuelPower:
    def test_1kg_s_methane_power(self):
        """1 kg/s CH4 × 50.05 MJ/kg = 50.05 MW."""
        r = fuel_power(mass_flow_kg_s=1.0, LHV_MJ_kg=50.05)
        assert abs(r["thermal_power_MW"] - 50.05) < 0.01, r

    def test_vol_flow_with_density(self):
        """Natural gas: ρ≈0.717 kg/m³ at STP; 1 m³/s × 0.717 kg/m³ × 50.05 MJ/kg."""
        r = fuel_power(vol_flow_m3_s=1.0, density_kg_m3=0.717, LHV_MJ_kg=50.05)
        expected = 0.717 * 50.05e6
        assert abs(r["thermal_power_W"] - expected) < 1000.0

    def test_eta_scales_power(self):
        """η=0.9 → 90% of full power."""
        r1 = fuel_power(mass_flow_kg_s=1.0, LHV_MJ_kg=50.05, eta_combustion=1.0)
        r9 = fuel_power(mass_flow_kg_s=1.0, LHV_MJ_kg=50.05, eta_combustion=0.9)
        assert abs(r9["thermal_power_W"] / r1["thermal_power_W"] - 0.9) < 1e-6

    def test_back_calculate_mass_flow(self):
        """1 MW target → required mass flow = 1e6 / (50.05e6) kg/s."""
        r = fuel_power(target_power_W=1e6, LHV_MJ_kg=50.05)
        expected_mdot = 1e6 / 50.05e6
        assert abs(r["mass_flow_kg_s"] - expected_mdot) < 1e-8

    def test_sfc_units(self):
        """SFC should be > 0 and < 1 kg/kWh for typical fuels."""
        r = fuel_power(mass_flow_kg_s=1.0, LHV_MJ_kg=50.05)
        assert 0.0 < r["SFC_kg_per_kWh"] < 0.5

    def test_no_fuel_flow_error(self):
        r = fuel_power(LHV_MJ_kg=50.05)
        assert r.get("ok") is False

    def test_no_hv_error(self):
        r = fuel_power(mass_flow_kg_s=1.0)
        assert r.get("ok") is False


# ---------------------------------------------------------------------------
# 10. FUELS table sanity
# ---------------------------------------------------------------------------

class TestFuelsTable:
    def test_fuels_table_populated(self):
        assert len(FUELS) >= 8

    def test_methane_lhv_in_table(self):
        """Methane LHV from table ≈ 50.05 MJ/kg."""
        f = FUELS["methane"]
        assert abs(f["LHV_MJ_kg"] - 50.05) < 0.1

    def test_methane_hhv_gt_lhv(self):
        f = FUELS["methane"]
        assert f["HHV_MJ_kg"] > f["LHV_MJ_kg"]

    def test_diesel_mw(self):
        f = FUELS["diesel"]
        # C12H26: 12*12.011 + 26*1.008 = 144.132+26.208=170.34
        assert abs(f["MW"] - 170.335) < 0.5


# ---------------------------------------------------------------------------
# 11. Tools LLM wrapper — happy paths
# ---------------------------------------------------------------------------

class TestTools:
    # ok_payload serialises the calc result dict directly.
    # err_payload returns {"error": ..., "code": ...}.
    # Successful results contain domain keys (no "ok" key).
    # Error results from the calc layer return {"ok": False, "reason": ...}.

    def test_tool_stoich_afr_happy(self):
        from kerf_cad_core.combustion.tools import run_stoich_afr
        result = _run(run_stoich_afr(None, json.dumps({"C": 1, "H": 4}).encode()))
        payload = json.loads(result)
        # Success: dict has AFR_mass; no "ok" key on happy path
        assert "AFR_mass" in payload
        assert abs(payload["AFR_mass"] - 17.23) < 0.2

    def test_tool_stoich_afr_missing_c(self):
        from kerf_cad_core.combustion.tools import run_stoich_afr
        result = _run(run_stoich_afr(None, json.dumps({"H": 4}).encode()))
        payload = json.loads(result)
        assert payload.get("ok") is False

    def test_tool_equivalence_ratio_happy(self):
        from kerf_cad_core.combustion.tools import run_equivalence_ratio
        result = _run(run_equivalence_ratio(None, json.dumps({"phi": 0.8}).encode()))
        payload = json.loads(result)
        assert "mixture" in payload
        assert payload["mixture"] == "lean"

    def test_tool_product_composition_happy(self):
        from kerf_cad_core.combustion.tools import run_product_composition
        result = _run(run_product_composition(
            None, json.dumps({"C": 1, "H": 4, "excess_air_pct": 10.0}).encode()
        ))
        payload = json.loads(result)
        assert "O2_dry_pct" in payload
        assert payload["O2_dry_pct"] > 0

    def test_tool_adiabatic_flame_temp_happy(self):
        from kerf_cad_core.combustion.tools import run_adiabatic_flame_temp
        result = _run(run_adiabatic_flame_temp(
            None, json.dumps({"C": 1, "H": 4, "LHV_MJ_kg": 50.05, "MW_fuel": 16.043}).encode()
        ))
        payload = json.loads(result)
        assert "T_ad_K" in payload
        assert payload["T_ad_K"] > 1500

    def test_tool_hhv_to_lhv_happy(self):
        from kerf_cad_core.combustion.tools import run_hhv_to_lhv
        result = _run(run_hhv_to_lhv(
            None, json.dumps({"HHV_MJ_kg": 55.53, "C": 1, "H": 4, "MW_fuel": 16.043}).encode()
        ))
        payload = json.loads(result)
        assert "LHV_MJ_kg" in payload
        assert abs(payload["LHV_MJ_kg"] - 50.05) < 0.2

    def test_tool_combustion_efficiency_happy(self):
        from kerf_cad_core.combustion.tools import run_combustion_efficiency
        result = _run(run_combustion_efficiency(
            None, json.dumps({"T_flue_C": 120, "T_ambient_C": 15, "CO2_dry_pct": 9.0}).encode()
        ))
        payload = json.loads(result)
        assert "eta_pct" in payload
        assert payload["eta_pct"] is not None

    def test_tool_dew_point_happy(self):
        from kerf_cad_core.combustion.tools import run_flue_gas_dew_point
        result = _run(run_flue_gas_dew_point(
            None, json.dumps({"H2O_wet_pct": 15.0}).encode()
        ))
        payload = json.loads(result)
        assert "T_dew_C" in payload

    def test_tool_co2_max_happy(self):
        from kerf_cad_core.combustion.tools import run_co2_max
        result = _run(run_co2_max(None, json.dumps({"C": 1, "H": 4}).encode()))
        payload = json.loads(result)
        assert "CO2_max_dry_pct" in payload
        assert abs(payload["CO2_max_dry_pct"] - 11.73) < 0.5

    def test_tool_fuel_power_happy(self):
        from kerf_cad_core.combustion.tools import run_fuel_power
        result = _run(run_fuel_power(
            None, json.dumps({"mass_flow_kg_s": 1.0, "LHV_MJ_kg": 50.05}).encode()
        ))
        payload = json.loads(result)
        assert "thermal_power_MW" in payload
        assert abs(payload["thermal_power_MW"] - 50.05) < 0.01

    def test_tool_bad_json(self):
        from kerf_cad_core.combustion.tools import run_stoich_afr
        result = _run(run_stoich_afr(None, b"{bad json}"))
        payload = json.loads(result)
        # err_payload returns {"error": ..., "code": ...}
        assert "error" in payload or payload.get("ok") is False

    def test_tool_dew_point_no_input(self):
        from kerf_cad_core.combustion.tools import run_flue_gas_dew_point
        result = _run(run_flue_gas_dew_point(None, json.dumps({}).encode()))
        payload = json.loads(result)
        assert payload.get("ok") is False


# ===========================================================================
# Authoritative external-reference cases (citable, numeric answers)
# ===========================================================================

class TestAuthoritativeReferences:
    """Cross-checks vs published worked examples with known numeric answers.

    Sources: Turns, S.R. "An Introduction to Combustion" 3rd ed.;
    Çengel & Boles "Thermodynamics" 8th ed.; Bacharach Combustion Test
    Handbook; VDI 2067 / EN 15502 (Siegert)."""

    def test_turns_ch4_afr(self):
        # Turns 3rd ed. Ex. 2.1: CH4 stoichiometric AFR_mass = 17.2
        r = stoich_afr(1, 4, 0)
        assert abs(r["AFR_mass"] - 17.2) < 0.1

    def test_turns_propane_afr(self):
        # Turns Table: C3H8 stoichiometric AFR_mass ≈ 15.6
        r = stoich_afr(3, 8, 0)
        assert abs(r["AFR_mass"] - 15.6) < 0.15

    def test_turns_ethane_afr(self):
        # Turns: C2H6 (ethane), n_O2 = 3.5, AFR_mass ≈ 16.1
        r = stoich_afr(2, 6, 0)
        assert abs(r["AFR_mass"] - 16.1) < 0.1

    def test_turns_hydrogen_afr(self):
        # Turns: H2, n_O2 = 0.5, AFR_mass ≈ 34.3
        r = stoich_afr(0, 2, 0)
        assert abs(r["AFR_mass"] - 34.3) < 0.2

    def test_turns_octane_afr(self):
        # Turns Table A: iso-octane C8H18, AFR_mass ≈ 15.1
        r = stoich_afr(8, 18, 0)
        assert abs(r["AFR_mass"] - 15.1) < 0.15

    def test_bacharach_ch4_co2max(self):
        # Bacharach: stoichiometric dry CO2 for methane ≈ 11.7 %
        r = co2_max(1, 4, 0)
        assert abs(r["CO2_max_dry_pct"] - 11.7) < 0.15

    def test_lambda_phi_excess_air_identity(self):
        # Definitional: λ = 1.2 → excess air 20 %, φ = 1/1.2 = 0.833
        r = equivalence_ratio(lambda_=1.2)
        assert abs(r["phi"] - 0.8333) < 1e-3
        assert abs(r["excess_air_pct"] - 20.0) < 1e-3

    def test_hhv_lhv_methane(self):
        # Methane HHV 55.50 → LHV ≈ 50.0 MJ/kg (water-vapour latent, 2.442 MJ/kg)
        r = hhv_to_lhv(55.50, C=1, H=4)
        assert abs(r["LHV_MJ_kg"] - 50.0) < 0.1

    def test_hhv_lhv_propane(self):
        # Propane HHV 50.35 → LHV ≈ 46.3 MJ/kg
        r = hhv_to_lhv(50.35, C=3, H=8)
        assert abs(r["LHV_MJ_kg"] - 46.3) < 0.15

    def test_siegert_natural_gas_loss(self):
        # Siegert (VDI/EN 15502) natural gas A1=0.68, B1=0.0071:
        # q_A = (200-20)*(0.68/10 + 0.0071) = 13.52 % → η ≈ 86.5 %
        r = combustion_efficiency(
            T_flue_C=200.0, T_ambient_C=20.0,
            CO2_dry_pct=10.0, fuel="natural_gas",
        )
        assert abs(r["q_A_pct"] - 13.52) < 0.1
        assert abs(r["eta_pct"] - 86.48) < 0.1

    def test_turns_ch4_adiabatic_flame_temp(self):
        # Turns 3rd ed.: stoichiometric CH4/air constant-p adiabatic flame
        # temperature ≈ 2226 K (no dissociation). Mean-cp method should land
        # within ~10% of this value.
        ch4 = FUELS["methane"]
        r = adiabatic_flame_temp(
            1, 4, 0, excess_air_pct=0.0,
            LHV_MJ_kg=ch4["LHV_MJ_kg"], MW_fuel=ch4["MW"],
        )
        assert 1900.0 < r["T_ad_K"] < 2600.0
