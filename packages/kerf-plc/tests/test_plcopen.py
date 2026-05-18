"""
tests/test_plcopen.py — PLCopen XML reader/writer tests (T-220).

Oracles
-------
- Each fixture round-trips byte-stable: load → dumps → loads compares equal.
- blinker.plc: 1 POU + 1 rung + 1 TON FB instance.
- conveyor.plc: 1 POU + 4 rungs + 6 variables.
- Reader raises PlcopenParseError on malformed XML.
"""
from __future__ import annotations

import pathlib

import pytest

from kerf_plc.plcopen import (
    LDBody,
    PlcopenParseError,
    Project,
    dumps,
    loads,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> Project:
    xml_text = (FIXTURES / name).read_text(encoding="utf-8")
    return loads(xml_text)


def _roundtrip(name: str) -> tuple[Project, Project]:
    """Return (first_load, load_after_round_trip)."""
    xml_text = (FIXTURES / name).read_text(encoding="utf-8")
    p1 = loads(xml_text)
    serialised = dumps(p1)
    p2 = loads(serialised)
    return p1, p2


# ---------------------------------------------------------------------------
# T1 — Round-trip stability
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_blinker_roundtrip_pou_count(self):
        p1, p2 = _roundtrip("blinker.plc")
        assert len(p1.types.pous) == len(p2.types.pous)

    def test_blinker_roundtrip_pou_name(self):
        p1, p2 = _roundtrip("blinker.plc")
        assert p1.types.pous[0].name == p2.types.pous[0].name

    def test_blinker_roundtrip_rung_count(self):
        p1, p2 = _roundtrip("blinker.plc")
        body1 = p1.types.pous[0].body
        body2 = p2.types.pous[0].body
        assert isinstance(body1, LDBody)
        assert isinstance(body2, LDBody)
        assert len(body1.rungs) == len(body2.rungs)

    def test_blinker_roundtrip_variable_names(self):
        p1, p2 = _roundtrip("blinker.plc")
        vars1 = [v.name for vb in p1.types.pous[0].var_blocks for v in vb.variables]
        vars2 = [v.name for vb in p2.types.pous[0].var_blocks for v in vb.variables]
        assert vars1 == vars2

    def test_conveyor_roundtrip_pou_count(self):
        p1, p2 = _roundtrip("conveyor.plc")
        assert len(p1.types.pous) == len(p2.types.pous)

    def test_conveyor_roundtrip_rung_count(self):
        p1, p2 = _roundtrip("conveyor.plc")
        body1 = p1.types.pous[0].body
        body2 = p2.types.pous[0].body
        assert isinstance(body1, LDBody)
        assert isinstance(body2, LDBody)
        assert len(body1.rungs) == len(body2.rungs)

    def test_roundtrip_preserves_negated_contacts(self):
        """Negated contacts survive round-trip."""
        p1, p2 = _roundtrip("conveyor.plc")
        body1 = p1.types.pous[0].body
        body2 = p2.types.pous[0].body
        assert isinstance(body1, LDBody)
        assert isinstance(body2, LDBody)
        neg1 = [c.negated for r in body1.rungs for c in r.contacts]
        neg2 = [c.negated for r in body2.rungs for c in r.contacts]
        assert neg1 == neg2

    def test_roundtrip_content_header_name(self):
        p1, p2 = _roundtrip("blinker.plc")
        assert p1.content_header.name == p2.content_header.name

    def test_roundtrip_instances_config_name(self):
        p1, p2 = _roundtrip("blinker.plc")
        assert (
            p1.instances.configurations[0].name
            == p2.instances.configurations[0].name
        )

    def test_roundtrip_pou_type(self):
        p1, p2 = _roundtrip("blinker.plc")
        assert p1.types.pous[0].pou_type == p2.types.pous[0].pou_type


# ---------------------------------------------------------------------------
# T2 — Blinker fixture structure
# ---------------------------------------------------------------------------

class TestBlinker:
    @pytest.fixture(scope="class")
    def project(self) -> Project:
        return _load_fixture("blinker.plc")

    def test_has_one_pou(self, project: Project):
        assert len(project.types.pous) == 1

    def test_pou_name(self, project: Project):
        assert project.types.pous[0].name == "Blinker"

    def test_pou_type_is_program(self, project: Project):
        assert project.types.pous[0].pou_type == "program"

    def test_has_ld_body(self, project: Project):
        assert isinstance(project.types.pous[0].body, LDBody)

    def test_has_one_rung(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert len(body.rungs) == 1

    def test_has_one_ton_instance(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        rung = body.rungs[0]
        ton_blocks = [fb for fb in rung.fb_instances if fb.type_name == "TON"]
        assert len(ton_blocks) == 1

    def test_ton_instance_name(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        ton = body.rungs[0].fb_instances[0]
        assert ton.instance_name == "timer"

    def test_has_clock_in_variable(self, project: Project):
        vars_ = [v.name for vb in project.types.pous[0].var_blocks for v in vb.variables]
        assert "clock_in" in vars_

    def test_clock_in_is_bool(self, project: Project):
        for vb in project.types.pous[0].var_blocks:
            for v in vb.variables:
                if v.name == "clock_in":
                    assert v.type_name.upper() == "BOOL"

    def test_has_coil(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert len(body.rungs[0].coils) == 1

    def test_coil_variable_is_pulse_out(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert body.rungs[0].coils[0].variable == "pulse_out"

    def test_has_left_power_rail(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert body.rungs[0].left_power_rail is not None

    def test_has_right_power_rail(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert body.rungs[0].right_power_rail is not None

    def test_content_header_name(self, project: Project):
        assert project.content_header.name == "Blinker"


# ---------------------------------------------------------------------------
# T3 — Conveyor fixture structure
# ---------------------------------------------------------------------------

class TestConveyor:
    @pytest.fixture(scope="class")
    def project(self) -> Project:
        return _load_fixture("conveyor.plc")

    def test_has_one_pou(self, project: Project):
        assert len(project.types.pous) == 1

    def test_pou_name(self, project: Project):
        assert project.types.pous[0].name == "Conveyor"

    def test_has_four_rungs(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        assert len(body.rungs) == 4

    def test_has_six_variables(self, project: Project):
        total_vars = sum(
            len(vb.variables) for vb in project.types.pous[0].var_blocks
        )
        assert total_vars == 6

    def test_variable_names(self, project: Project):
        var_names = {
            v.name
            for vb in project.types.pous[0].var_blocks
            for v in vb.variables
        }
        expected = {"btn_start", "btn_stop", "btn_estop", "motor_run", "motor_latch", "estop_latch"}
        assert expected == var_names

    def test_all_variables_are_bool(self, project: Project):
        for vb in project.types.pous[0].var_blocks:
            for v in vb.variables:
                assert v.type_name.upper() == "BOOL", f"{v.name} should be BOOL"

    def test_has_negated_contacts(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        all_contacts = [c for r in body.rungs for c in r.contacts]
        negated = [c for c in all_contacts if c.negated]
        assert len(negated) >= 1

    def test_first_rung_start_contact(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        rung1_contacts = body.rungs[0].contacts
        assert any(c.variable == "btn_start" for c in rung1_contacts)

    def test_fourth_rung_motor_run_coil(self, project: Project):
        body = project.types.pous[0].body
        assert isinstance(body, LDBody)
        rung4_coils = body.rungs[3].coils
        assert any(c.variable == "motor_run" for c in rung4_coils)

    def test_has_one_configuration(self, project: Project):
        assert len(project.instances.configurations) == 1

    def test_configuration_name(self, project: Project):
        assert project.instances.configurations[0].name == "ConveyorConfig"


# ---------------------------------------------------------------------------
# T4 — Error handling
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_empty_string_raises(self):
        with pytest.raises(PlcopenParseError):
            loads("")

    def test_whitespace_only_raises(self):
        with pytest.raises(PlcopenParseError):
            loads("   \n\t  ")

    def test_invalid_xml_raises(self):
        with pytest.raises(PlcopenParseError):
            loads("<project><unclosed>")

    def test_wrong_root_element_raises(self):
        with pytest.raises(PlcopenParseError):
            loads('<root xmlns="http://example.com"><foo/></root>')

    def test_malformed_pou_type_raises(self):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <contentHeader name="X" version="1.0"/>
  <types>
    <pous>
      <pou name="Bad" pouType="bogusType">
        <body><LD/></body>
      </pou>
    </pous>
  </types>
  <instances/>
</project>"""
        with pytest.raises(PlcopenParseError):
            loads(xml)

    def test_bare_text_raises(self):
        with pytest.raises(PlcopenParseError):
            loads("This is not XML at all")

    def test_no_namespace_wrong_root_raises(self):
        with pytest.raises(PlcopenParseError):
            loads("<notproject/>")

    def test_valid_minimal_does_not_raise(self):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <contentHeader name="Min" version="1.0"/>
  <types><pous/></types>
  <instances/>
</project>"""
        project = loads(xml)
        assert project.content_header.name == "Min"
        assert project.types.pous == []
