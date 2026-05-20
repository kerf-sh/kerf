"""test_analog_library.py — pytest suite for T-258 analog cell library.

Tests cover:
1. Library registry   — list_families(), instantiate() dispatch.
2. Op-amp generate    — cell loaded, descriptor keys present, LVS clean.
3. Op-amp characterise— analytic oracle, GBW within ±20 %, dc_gain positive.
4. LLM tool           — instantiate_analog_cell() response schema.
5. Comparator stub    — loads without error, characterisation returns stub notes.
6. Bandgap stub       — loads without error, characterisation returns stub notes.
7. Error handling     — unknown family raises KeyError / returns error response.
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
# Comparator stub
# ---------------------------------------------------------------------------

class TestComparatorStub:
    def test_generate_returns_cell(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        from kerf_silicon.analog.library import AnalogCell
        cell = generate()
        assert isinstance(cell, AnalogCell)

    def test_pdk_sky130(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        assert cell.pdk == "sky130"

    def test_descriptor_has_polygons(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        assert "polygons" in cell.descriptor

    def test_descriptor_has_ports(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        cell = generate()
        for port in ["VDD", "VSS", "INP", "INN", "CLK"]:
            assert port in cell.descriptor.get("ports", [])

    def test_characterise_returns_stub(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise({"offset_mv": 5})
        assert result.oracle_path == "stub"

    def test_characterise_notes_mention_todo(self):
        from kerf_silicon.analog.comparator_strongarm import characterise
        result = characterise()
        assert any("TODO" in n for n in result.notes)

    def test_unsupported_pdk_raises(self):
        from kerf_silicon.analog.comparator_strongarm import generate
        with pytest.raises(ValueError):
            generate({"pdk": "tsmc65"})


# ---------------------------------------------------------------------------
# Bandgap stub
# ---------------------------------------------------------------------------

class TestBandgapStub:
    def test_generate_returns_cell(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        from kerf_silicon.analog.library import AnalogCell
        cell = generate()
        assert isinstance(cell, AnalogCell)

    def test_pdk_sky130(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        assert cell.pdk == "sky130"

    def test_descriptor_has_polygons(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        assert "polygons" in cell.descriptor

    def test_descriptor_has_ports(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        cell = generate()
        for port in ["VDD", "VSS", "VREF"]:
            assert port in cell.descriptor.get("ports", [])

    def test_characterise_returns_stub(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise({"iref_ua": 10})
        assert result.oracle_path == "stub"

    def test_characterise_vref_target(self):
        """Brokaw bandgap targets ~1.25 V."""
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert abs(result.vref_target_v - 1.25) < 0.01

    def test_characterise_notes_mention_todo(self):
        from kerf_silicon.analog.bandgap_brokaw import characterise
        result = characterise()
        assert any("TODO" in n for n in result.notes)

    def test_unsupported_pdk_raises(self):
        from kerf_silicon.analog.bandgap_brokaw import generate
        with pytest.raises(ValueError):
            generate({"pdk": "gf180"})


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
