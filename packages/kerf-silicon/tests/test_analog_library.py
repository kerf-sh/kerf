"""test_analog_library.py — pytest suite for T-258 analog cell library.

Tests cover:
1. Library registry    — list_families(), instantiate() dispatch.
2. Op-amp generate     — cell loaded, descriptor keys present, LVS clean.
3. Op-amp characterise — analytic oracle, GBW within ±20 %, dc_gain positive.
4. LLM tool            — instantiate_analog_cell() response schema.
5. Comparator generate — cell loaded, descriptor + LVS reference present.
6. Comparator oracle   — analytic Pelgrom offset oracle within target band.
7. Bandgap generate    — cell loaded, descriptor + LVS reference present.
8. Bandgap oracle      — Vref within ±5 % of 1.25 V; TC sign correct.
9. LVS-clean check     — comparator and bandgap LVS clean via golden netlist.
10. Error handling     — unknown family raises KeyError / returns error response.
"""

from __future__ import annotations

import math
import pytest


# ---------------------------------------------------------------------------
# Library registry
# ---------------------------------------------------------------------------

class TestLibraryRegistry:
    def test_list_families_returns_three(self):
        from kerf_silicon.analog.library import list_families
        families = list_families()
        assert len(families) == 3

    def test_list_families_contains_expected(self):
        from kerf_silicon.analog.library import list_families
        families = set(list_families())
        assert "opamp_2stage" in families
        assert "comparator_strongarm" in families
        assert "bandgap_brokaw" in families

    def test_instantiate_unknown_family_raises_key_error(self):
        from kerf_silicon.analog.library import instantiate
        with pytest.raises(KeyError):
            instantiate("nonexistent_cell")

    def test_instantiate_returns_analog_cell(self):
        from kerf_silicon.analog.library import instantiate, AnalogCell
        cell = instantiate("opamp_2stage", {"gbw_hz": 1e6})
        assert isinstance(cell, AnalogCell)

    def test_analog_cell_has_required_fields(self):
        from kerf_silicon.analog.library import instantiate
        cell = instantiate("opamp_2stage")
        assert hasattr(cell, "name")
        assert hasattr(cell, "pdk")
        assert hasattr(cell, "descriptor")
        assert hasattr(cell, "lvs_reference")
        assert hasattr(cell, "params")


# ---------------------------------------------------------------------------
# Op-amp generate
# ---------------------------------------------------------------------------

class TestOpampGenerate:
    def test_cell_name(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        assert cell.name == "opamp_2stage_sky130"

    def test_pdk(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        assert cell.pdk == "sky130"

    def test_descriptor_has_polygons(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        assert "polygons" in cell.descriptor
        assert len(cell.descriptor["polygons"]) > 0

    def test_descriptor_has_devices(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        assert "devices" in cell.descriptor
        # Should have M1..M7 + Cc = 8 devices
        assert len(cell.descriptor["devices"]) == 8

    def test_descriptor_has_ports(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        ports = cell.descriptor.get("ports", [])
        for expected in ["VDD", "VSS", "INP", "INN", "OUT"]:
            assert expected in ports

    def test_lvs_reference_has_cells(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "cells" in lvs
        assert len(lvs["cells"]) == 8  # M1..M7 + Cc

    def test_lvs_reference_has_nets(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "nets" in lvs
        net_names = {n["name"] for n in lvs["nets"]}
        assert "VDD" in net_names
        assert "VSS" in net_names
        assert "OUT" in net_names

    def test_params_stored(self):
        from kerf_silicon.analog.opamp_2stage import generate
        cell = generate({"gbw_hz": 2e6, "idd_ua": 100})
        assert cell.params["gbw_hz"] == 2e6
        assert cell.params["idd_ua"] == 100

    def test_unsupported_pdk_raises(self):
        from kerf_silicon.analog.opamp_2stage import generate
        with pytest.raises(ValueError, match="sky130"):
            generate({"pdk": "gf180mcu"})


# ---------------------------------------------------------------------------
# Op-amp characterise — analytic oracle
# ---------------------------------------------------------------------------

class TestOpampCharacterise:
    def test_characterise_returns_dataclass(self):
        from kerf_silicon.analog.opamp_2stage import characterise, CellCharacterisation
        result = characterise({"gbw_hz": 1e6})
        assert isinstance(result, CellCharacterisation)

    def test_gbw_requested_stored(self):
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.gbw_hz_requested == 1e6

    def test_oracle_path_is_analytic_or_ngspice(self):
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.oracle_path in ("analytic", "ngspice")

    def test_gbw_achieved_within_20pct_1mhz(self):
        """Core DoD test: 1 MHz GBW target must achieve ±20 %."""
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.within_20pct, (
            f"GBW oracle FAIL: requested={result.gbw_hz_requested/1e6:.3f} MHz, "
            f"achieved={result.gbw_hz_achieved/1e6:.3f} MHz, "
            f"error={abs(result.gbw_hz_achieved - result.gbw_hz_requested)/result.gbw_hz_requested*100:.1f}%. "
            f"Oracle: {result.oracle_path}. Notes: {result.notes}"
        )

    def test_gbw_achieved_within_20pct_5mhz(self):
        """5 MHz target also within ±20 %."""
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 5e6})
        assert result.within_20pct, (
            f"5 MHz GBW oracle FAIL: achieved={result.gbw_hz_achieved/1e6:.3f} MHz. "
            f"Notes: {result.notes}"
        )

    def test_gbw_achieved_within_20pct_500khz(self):
        """500 kHz target within ±20 %."""
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 5e5})
        assert result.within_20pct

    def test_dc_gain_positive(self):
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.dc_gain_dB > 0

    def test_dc_gain_reasonable_two_stage(self):
        """Two-stage op-amp DC gain should be >30 dB."""
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.dc_gain_dB >= 30.0, (
            f"DC gain too low: {result.dc_gain_dB:.1f} dB"
        )

    def test_gm1_positive(self):
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert result.gm1_A_per_V > 0

    def test_cc_within_process_limits(self):
        from kerf_silicon.analog.opamp_2stage import characterise, _CC_MIN_F, _CC_MAX_F
        result = characterise({"gbw_hz": 1e6})
        assert _CC_MIN_F <= result.cc_F <= _CC_MAX_F, (
            f"Cc={result.cc_F*1e12:.2f} pF out of range [{_CC_MIN_F*1e12},{_CC_MAX_F*1e12}] pF"
        )

    def test_notes_list_non_empty(self):
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise({"gbw_hz": 1e6})
        assert len(result.notes) > 0

    def test_analytic_gbw_formula(self):
        """Directly verify: GBW = gm1 / (2π * Cc)."""
        from kerf_silicon.analog.opamp_2stage import (
            characterise, _analytic_gbw, _size_for_gbw
        )
        gbw_req = 1e6
        sizing  = _size_for_gbw(gbw_req, 50.0)
        gbw_analytic = _analytic_gbw(sizing["gm1"], sizing["cc"])
        # The formula is exact by construction, but Cc clamping can shift it
        pct_err = abs(gbw_analytic - gbw_req) / gbw_req
        # If Cc is at the clamp boundary the error can be larger; still <=20%
        assert pct_err <= 0.20 or math.isclose(gbw_analytic, gbw_req, rel_tol=0.01), (
            f"Analytic formula mismatch: {gbw_analytic/1e6:.3f} MHz vs {gbw_req/1e6:.3f} MHz"
        )

    def test_default_params_produce_1mhz_target(self):
        """Default params should give 1 MHz GBW target."""
        from kerf_silicon.analog.opamp_2stage import characterise
        result = characterise()
        assert result.gbw_hz_requested == 1e6


# ---------------------------------------------------------------------------
# LLM tool: instantiate_analog_cell
# ---------------------------------------------------------------------------

class TestInstantiateAnalogCellTool:
    def test_ok_true_for_opamp(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        assert r["ok"] is True

    def test_response_schema_keys(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        for key in ("ok", "cell_name", "pdk", "params", "descriptor", "lvs",
                    "characterisation", "error"):
            assert key in r, f"Missing key: {key}"

    def test_lvs_clean_for_opamp(self):
        """The op-amp cell has a golden LVS netlist; structural check must pass."""
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        assert r["lvs"]["clean"] is True, (
            f"LVS not clean: {r['lvs']['summary']}"
        )

    def test_lvs_reference_cell_count(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        assert r["lvs"]["reference_cell_count"] == 8

    def test_gbw_within_20pct_via_tool(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        assert r["characterisation"]["within_20pct"] is True, (
            f"Tool GBW check failed: {r['characterisation']}"
        )

    def test_error_for_unknown_family(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bogus_cell")
        assert r["ok"] is False
        assert r["error"] is not None

    def test_cell_name_in_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 2e6})
        assert r["cell_name"] == "opamp_2stage_sky130"

    def test_pdk_in_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage")
        assert r["pdk"] == "sky130"

    def test_descriptor_has_polygons_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage")
        assert "polygons" in r["descriptor"]
        assert len(r["descriptor"]["polygons"]) > 0

    def test_characterisation_oracle_path_present(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("opamp_2stage", {"gbw_hz": 1e6})
        assert r["characterisation"]["oracle_path"] in ("analytic", "ngspice")

    def test_comparator_tool_loads(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("comparator_strongarm", {"offset_mv": 5})
        assert r["ok"] is True
        assert r["cell_name"] == "comparator_strongarm_sky130"

    def test_bandgap_tool_loads(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["ok"] is True
        assert r["cell_name"] == "bandgap_brokaw_sky130"


# ---------------------------------------------------------------------------
# Comparator generate + analytic oracle
# ---------------------------------------------------------------------------

class TestComparatorGenerate:
    def test_generate_returns_cell(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        from kerf_silicon.analog.library import AnalogCell
        cell = generate()
        assert isinstance(cell, AnalogCell)

    def test_pdk_sky130(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        assert cell.pdk == "sky130"

    def test_cell_name(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        assert cell.name == "comparator_strongarm_sky130"

    def test_descriptor_has_polygons(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        assert "polygons" in cell.descriptor
        assert len(cell.descriptor["polygons"]) > 0

    def test_descriptor_has_ports(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        for port in ["VDD", "VSS", "INP", "INN", "CLK"]:
            assert port in cell.descriptor.get("ports", [])

    def test_descriptor_has_devices(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        devices = cell.descriptor.get("devices", [])
        assert len(devices) >= 7, (
            f"Expected ≥7 devices (MP1/MP2/MN1/MN2/ML1/ML2/MT), got {len(devices)}"
        )

    def test_lvs_reference_has_cells(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "cells" in lvs
        assert len(lvs["cells"]) == 7  # MP1/MP2/MN1/MN2/ML1/ML2/MT

    def test_lvs_reference_has_nets(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "nets" in lvs
        net_names = {n["name"] for n in lvs["nets"]}
        assert "VDD" in net_names
        assert "VSS" in net_names
        assert "OUTP" in net_names
        assert "OUTN" in net_names

    def test_unsupported_pdk_raises(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        with pytest.raises(ValueError):
            generate({"pdk": "tsmc65"})


class TestComparatorCharacterise:
    def test_characterise_returns_dataclass(self):
        from kerf_silicon.analog.comparator_strongarm import characterise, CellCharacterisation
        result = characterise({"offset_mv": 5})
        assert isinstance(result, CellCharacterisation)

    def test_oracle_path_is_analytic(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.oracle_path == "analytic"

    def test_offset_target_stored(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.offset_target_mv == 5.0

    def test_offset_achieved_within_target_5mv(self):
        """Core DoD test: analytic offset ≤ requested 5 mV target."""
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.within_target, (
            f"Offset oracle FAIL: target={result.offset_target_mv:.1f} mV, "
            f"achieved={result.offset_achieved_mv:.2f} mV (1σ)"
        )

    def test_offset_achieved_within_target_3mv(self):
        """Tighter 3 mV target should also pass (larger device sized)."""
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 3})
        assert result.within_target, (
            f"3 mV offset oracle FAIL: achieved={result.offset_achieved_mv:.2f} mV"
        )

    def test_offset_achieved_positive(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.offset_achieved_mv > 0

    def test_w_um_positive(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.w_um > 0

    def test_larger_target_gives_smaller_or_equal_device(self):
        """Relaxed offset target should require smaller W (less area)."""
        from kerf_silicon.analog.comparator_strongarm import characterise
        r_tight  = characterise({"offset_mv": 2})
        r_loose  = characterise({"offset_mv": 10})
        assert r_tight.w_um >= r_loose.w_um, (
            f"Tighter target should need larger W: tight={r_tight.w_um:.2f} µm, "
            f"loose={r_loose.w_um:.2f} µm"
        )

    def test_notes_non_empty(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert len(result.notes) > 0

    def test_default_params(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise()
        assert result.offset_target_mv == 5.0

    def test_pelgrom_formula_direct(self):
        """Verify Pelgrom formula: σ_Vos = A_VT / sqrt(W*L)."""
        from kerf_silicon.analog.comparator_strongarm import _pelgrom_offset_mv, _A_VT_N_MV_UM
        w_um = 4.0
        l_um = 0.15
        expected = _A_VT_N_MV_UM / math.sqrt(w_um * l_um)
        got = _pelgrom_offset_mv(w_um, l_um)
        assert math.isclose(got, expected, rel_tol=1e-9), (
            f"Pelgrom formula: expected {expected:.4f} mV, got {got:.4f} mV"
        )


class TestComparatorLVS:
    def test_comparator_lvs_clean_via_tool(self):
        """instantiate_analog_cell must return LVS-clean for the comparator."""
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("comparator_strongarm", {"offset_mv": 5})
        assert r["ok"] is True
        assert r["lvs"]["clean"] is True, (
            f"Comparator LVS not clean: {r['lvs']['summary']}"
        )

    def test_comparator_lvs_reference_cell_count(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("comparator_strongarm", {"offset_mv": 5})
        assert r["lvs"]["reference_cell_count"] == 7

    def test_comparator_oracle_path_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("comparator_strongarm", {"offset_mv": 5})
        assert r["characterisation"]["oracle_path"] == "analytic"

    def test_comparator_within_target_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("comparator_strongarm", {"offset_mv": 5})
        assert r["characterisation"]["within_target"] is True


# ---------------------------------------------------------------------------
# Bandgap generate + analytic oracle
# ---------------------------------------------------------------------------

class TestBandgapGenerate:
    def test_generate_returns_cell(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        from kerf_silicon.analog.library import AnalogCell
        cell = generate()
        assert isinstance(cell, AnalogCell)

    def test_pdk_sky130(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        assert cell.pdk == "sky130"

    def test_cell_name(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        assert cell.name == "bandgap_brokaw_sky130"

    def test_descriptor_has_polygons(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        assert "polygons" in cell.descriptor
        assert len(cell.descriptor["polygons"]) > 0

    def test_descriptor_has_ports(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        for port in ["VDD", "VSS", "VREF"]:
            assert port in cell.descriptor.get("ports", [])

    def test_descriptor_has_devices(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        devices = cell.descriptor.get("devices", [])
        assert len(devices) >= 6, (
            f"Expected ≥6 devices (MP1/MP2/Q1/Q2/R1/R2), got {len(devices)}"
        )

    def test_lvs_reference_has_cells(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "cells" in lvs
        assert len(lvs["cells"]) == 6  # MP1/MP2/Q1/Q2/R1/R2

    def test_lvs_reference_has_nets(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        lvs = cell.lvs_reference
        assert "nets" in lvs
        net_names = {n["name"] for n in lvs["nets"]}
        assert "VDD" in net_names
        assert "VSS" in net_names
        assert "VREF" in net_names

    def test_unsupported_pdk_raises(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        with pytest.raises(ValueError):
            generate({"pdk": "gf180"})


class TestBandgapCharacterise:
    def test_characterise_returns_dataclass(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise, CellCharacterisation
        result = characterise({"iref_ua": 10})
        assert isinstance(result, CellCharacterisation)

    def test_oracle_path_is_analytic(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert result.oracle_path == "analytic"

    def test_vref_target_is_1p25v(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert abs(result.vref_target_v - 1.25) < 0.001

    def test_vref_within_5pct_at_300k(self):
        """Core DoD test: analytic VREF at 300 K within ±5% of 1.25 V."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300})
        assert result.vref_within_5pct, (
            f"VREF oracle FAIL: achieved={result.vref_achieved_v*1e3:.2f} mV "
            f"(target=1250 mV, error={abs(result.vref_achieved_v-1.25)/1.25*100:.2f}%)"
        )

    def test_vref_within_5pct_at_27c(self):
        """27 °C = 300.15 K — standard room temperature."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300.15})
        assert result.vref_within_5pct

    def test_vref_achieved_near_1p25v(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert 1.1 < result.vref_achieved_v < 1.4, (
            f"VREF out of expected range: {result.vref_achieved_v:.4f} V"
        )

    def test_tc_ctat_is_negative(self):
        """CTAT component (dVBE/dT) must be negative."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300})
        assert result.tc_ctat_mv_per_k < 0, (
            f"TC CTAT should be negative: got {result.tc_ctat_mv_per_k:.3f} mV/K"
        )

    def test_tc_ptat_is_positive(self):
        """PTAT component must be positive."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300})
        assert result.tc_ptat_mv_per_k > 0, (
            f"TC PTAT should be positive: got {result.tc_ptat_mv_per_k:.3f} mV/K"
        )

    def test_tc_sign_correct(self):
        """CTAT + PTAT cancellation signs are correct."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300})
        assert result.tc_sign_correct, (
            f"TC sign check failed: CTAT={result.tc_ctat_mv_per_k:.3f} mV/K, "
            f"PTAT={result.tc_ptat_mv_per_k:.3f} mV/K"
        )

    def test_tc_net_near_zero_at_300k(self):
        """Net TC at design point (300 K) should be near zero."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"temp_k": 300})
        # By design, zero at 300 K; allow tiny floating-point error
        assert abs(result.tc_net_mv_per_k) < 0.01, (
            f"Net TC should be ≈0 at 300 K: got {result.tc_net_mv_per_k:.4f} mV/K"
        )

    def test_r2_r1_ratio_positive(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert result.r2_r1_ratio > 0

    def test_notes_non_empty(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert len(result.notes) > 0

    def test_default_params_iref(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert result.iref_ua == 10.0

    def test_vref_formula_direct(self):
        """Directly verify: VREF = VBE(300) + R2/R1 * 2*Vt*ln(n)."""
        from kerf_silicon.analog.bandgap_brokaw import (
            _vref_at_t, _vbe_at_t, _vt_at_t, _R2_R1, _N_RATIO
        )
        t = 300.0
        expected = _vbe_at_t(t) + _R2_R1 * 2.0 * _vt_at_t(t) * math.log(_N_RATIO)
        got = _vref_at_t(t)
        assert math.isclose(got, expected, rel_tol=1e-9), (
            f"VREF formula: expected {expected:.4f} V, got {got:.4f} V"
        )

    def test_vref_temperature_varies_smoothly(self):
        """VREF at −40 °C and +125 °C should still be within 10% of 1.25 V."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        for temp_k in [233.0, 398.0]:  # -40 C and +125 C
            result = characterise({"temp_k": temp_k})
            err = abs(result.vref_achieved_v - 1.25) / 1.25
            assert err < 0.10, (
                f"VREF at {temp_k:.0f} K = {result.vref_achieved_v:.4f} V "
                f"(error={err*100:.1f}% > 10%)"
            )


class TestBandgapLVS:
    def test_bandgap_lvs_clean_via_tool(self):
        """instantiate_analog_cell must return LVS-clean for the bandgap."""
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["ok"] is True
        assert r["lvs"]["clean"] is True, (
            f"Bandgap LVS not clean: {r['lvs']['summary']}"
        )

    def test_bandgap_lvs_reference_cell_count(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["lvs"]["reference_cell_count"] == 6

    def test_bandgap_oracle_path_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["characterisation"]["oracle_path"] == "analytic"

    def test_bandgap_vref_within_5pct_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["characterisation"]["vref_within_5pct"] is True

    def test_bandgap_tc_sign_correct_in_tool_response(self):
        from kerf_silicon.tools.instantiate_analog_cell import instantiate_analog_cell
        r = instantiate_analog_cell("bandgap_brokaw", {"iref_ua": 10})
        assert r["characterisation"]["tc_sign_correct"] is True


# ---------------------------------------------------------------------------
# JSON descriptor loading (cell JSON files)
# ---------------------------------------------------------------------------

class TestCellDescriptorFiles:
    def _cells_dir(self):
        from pathlib import Path
        import kerf_silicon.analog.opamp_2stage as mod
        return Path(mod.__file__).parent / "cells"

    def test_opamp_json_exists(self):
        d = self._cells_dir()
        assert (d / "opamp_2stage_sky130.json").exists()

    def test_opamp_lvs_json_exists(self):
        d = self._cells_dir()
        assert (d / "opamp_2stage_sky130.lvs.json").exists()

    def test_comparator_json_exists(self):
        d = self._cells_dir()
        assert (d / "comparator_strongarm_sky130.json").exists()

    def test_bandgap_json_exists(self):
        d = self._cells_dir()
        assert (d / "bandgap_brokaw_sky130.json").exists()

    def test_opamp_json_valid(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "opamp_2stage_sky130.json").read_text())
        assert data["cell_name"] == "opamp_2stage_sky130"
        assert data["pdk"] == "sky130"

    def test_opamp_lvs_json_valid(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "opamp_2stage_sky130.lvs.json").read_text())
        assert "cells" in data
        assert "nets" in data

    def test_comparator_lvs_json_exists(self):
        d = self._cells_dir()
        assert (d / "comparator_strongarm_sky130.lvs.json").exists()

    def test_bandgap_lvs_json_exists(self):
        d = self._cells_dir()
        assert (d / "bandgap_brokaw_sky130.lvs.json").exists()

    def test_comparator_lvs_json_valid(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "comparator_strongarm_sky130.lvs.json").read_text())
        assert "cells" in data
        assert "nets" in data
        refs = {c["ref"] for c in data["cells"]}
        # Must have all 7 devices
        for ref in ["MP1", "MP2", "MN1", "MN2", "ML1", "ML2", "MT"]:
            assert ref in refs, f"Missing device {ref} in LVS reference"

    def test_bandgap_lvs_json_valid(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "bandgap_brokaw_sky130.lvs.json").read_text())
        assert "cells" in data
        assert "nets" in data
        refs = {c["ref"] for c in data["cells"]}
        for ref in ["MP1", "MP2", "Q1", "Q2", "R1", "R2"]:
            assert ref in refs, f"Missing device {ref} in LVS reference"

    def test_comparator_json_has_devices(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "comparator_strongarm_sky130.json").read_text())
        assert len(data.get("devices", [])) >= 7

    def test_bandgap_json_has_devices(self):
        import json
        d = self._cells_dir()
        data = json.loads((d / "bandgap_brokaw_sky130.json").read_text())
        assert len(data.get("devices", [])) >= 6
