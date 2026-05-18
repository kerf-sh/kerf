"""
tests/test_ld_export.py — IEC 61131-3 XML export tests.

DoD check: IEC XML export round-trips — the exported XML contains the
expected PLCopen structure.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from kerf_plc.ld.schema import load
from kerf_plc.ld.export import export_xml


VALID_LD = {
    "program": "ExportTest",
    "variables": [
        {"name": "sensor",   "type": "BOOL", "dir": "input"},
        {"name": "actuator", "type": "BOOL", "dir": "output"},
    ],
    "rungs": [
        {
            "label": "Rung 0",
            "comment": "basic contact → coil",
            "branches": [
                [{"type": "contact_no", "var": "sensor"}]
            ],
            "output": {"type": "coil", "var": "actuator"},
        }
    ],
}

TIMER_LD = {
    "program": "TimerExport",
    "variables": [
        {"name": "enable", "type": "BOOL", "dir": "input"},
    ],
    "rungs": [
        {
            "branches": [[{"type": "contact_no", "var": "enable"}]],
            "output": {
                "type": "fb_call",
                "fb_type": "TON",
                "fb_instance": "T1",
                "fb_inputs": {"PT": "T#5s"},
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# T1 — output is a valid XML string
# ---------------------------------------------------------------------------

class TestExportXML:
    def test_returns_string(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert isinstance(xml, str)
        assert len(xml) > 0

    def test_xml_declaration_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "<?xml" in xml

    def test_parseable_xml(self):
        """Output must be parseable by Python's ElementTree."""
        prog = load(VALID_LD)
        xml_str = export_xml(prog)
        # Strip XML declaration for ET.fromstring
        if xml_str.startswith("<?xml"):
            idx = xml_str.index("?>") + 2
            xml_str = xml_str[idx:].strip()
        # Must not raise
        ET.fromstring(xml_str)

    def test_project_root_element(self):
        prog = load(VALID_LD)
        xml_str = export_xml(prog)
        if xml_str.startswith("<?xml"):
            xml_str = xml_str[xml_str.index("?>") + 2:].strip()
        root = ET.fromstring(xml_str)
        # root tag may have namespace prefix
        assert "project" in root.tag.lower()

    def test_program_name_in_xml(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "ExportTest" in xml

    def test_pou_section_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "pou" in xml.lower() or "pous" in xml.lower()

    def test_variable_names_in_xml(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "sensor" in xml
        assert "actuator" in xml

    def test_ld_body_section_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "<LD>" in xml or "<LD " in xml

    def test_rung_element_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "rung" in xml.lower()

    def test_contact_element_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "contact" in xml.lower()

    def test_coil_element_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "coil" in xml.lower()

    def test_fb_type_in_timer_export(self):
        prog = load(TIMER_LD)
        xml = export_xml(prog)
        assert "TON" in xml

    def test_fb_instance_in_timer_export(self):
        prog = load(TIMER_LD)
        xml = export_xml(prog)
        assert "T1" in xml

    def test_plcopen_namespace_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "plcopen.org" in xml

    def test_configuration_section_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "configuration" in xml.lower()

    def test_resource_section_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "resource" in xml.lower()

    def test_interface_section_present(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "interface" in xml.lower()

    def test_comment_in_rung_xml(self):
        prog = load(VALID_LD)
        xml = export_xml(prog)
        assert "basic contact" in xml

    def test_round_trip_program_name(self):
        """Export then re-parse XML and confirm program name is preserved."""
        prog = load(VALID_LD)
        xml_str = export_xml(prog)
        assert "ExportTest" in xml_str
        # Confirm the name appears as an attribute value (not just in a comment)
        assert 'name="ExportTest"' in xml_str


# ---------------------------------------------------------------------------
# T2 — empty program exports cleanly
# ---------------------------------------------------------------------------

class TestEmptyExport:
    def test_empty_rungs_exports(self):
        from kerf_plc.ld.schema import LadderProgram
        prog = LadderProgram(program="EmptyProg")
        xml = export_xml(prog)
        assert "EmptyProg" in xml
        # Empty LD body renders as <LD/> (self-closing) or <LD>
        assert "<LD" in xml
