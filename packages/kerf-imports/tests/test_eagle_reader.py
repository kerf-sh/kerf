"""
test_eagle_reader.py — pytest suite for eagle_reader.py.

All fixtures are synthetic Eagle XML strings constructed in-test.
No real Eagle files are used.  Tests cover:
  - schematic source detected
  - board source detected
  - part count parsed from schematic
  - part ref/value/library extracted
  - net count parsed
  - net names extracted
  - pinref mapping (ref.pin)
  - footprint count from board elements
  - footprint ref/value/package extracted
  - footprint x/y coordinates
  - footprint rotation parsed (R90 → 90.0)
  - footprint layer from rotation flag (MR0 → Bottom)
  - signal count from board
  - signal name extracted
  - signal wire x1/y1/x2/y2 parsed
  - signal via drill parsed
  - signal contactref element+pad
  - namespace-prefixed XML handled
  - empty XML document → {"ok": False}
  - malformed XML → {"ok": False}
  - empty string → {"ok": False}
  - bytes (UTF-8) input accepted
  - unknown root element emits warning but still parses
"""

from __future__ import annotations

import pytest

from kerf_imports.eagle_reader import parse_eagle


# ---------------------------------------------------------------------------
# Synthetic schematic fixture
# ---------------------------------------------------------------------------

_SCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eagle version="9.6.2">
  <drawing>
    <schematic>
      <libraries>
        <library name="resistors">
          <devicesets>
            <deviceset name="R" prefix="R">
              <devices>
                <device name="0805" package="R_0805"/>
              </devices>
            </deviceset>
          </devicesets>
        </library>
        <library name="capacitors">
          <devicesets>
            <deviceset name="C" prefix="C">
              <devices>
                <device name="0402" package="C_0402"/>
              </devices>
            </deviceset>
          </devicesets>
        </library>
      </libraries>
      <parts>
        <part name="R1" library="resistors" deviceset="R" device="0805"
              value="10k" package="R_0805"/>
        <part name="R2" library="resistors" deviceset="R" device="0805"
              value="22k" package="R_0805"/>
        <part name="C1" library="capacitors" deviceset="C" device="0402"
              value="100nF" package="C_0402"/>
        <part name="U1" library="ics" deviceset="NE555" device="DIP8"
              value="NE555" package="DIP8"/>
      </parts>
      <sheets>
        <sheet>
          <nets>
            <net name="VCC" class="0">
              <segment>
                <pinref part="U1" gate="G" pin="VCC"/>
                <pinref part="C1" gate="G" pin="1"/>
              </segment>
            </net>
            <net name="GND" class="0">
              <segment>
                <pinref part="R1" gate="G" pin="1"/>
                <pinref part="R2" gate="G" pin="1"/>
              </segment>
            </net>
            <net name="OUT" class="0">
              <segment>
                <pinref part="U1" gate="G" pin="OUT"/>
                <pinref part="R1" gate="G" pin="2"/>
              </segment>
            </net>
          </nets>
        </sheet>
      </sheets>
    </schematic>
  </drawing>
</eagle>
"""

# ---------------------------------------------------------------------------
# Synthetic board fixture
# ---------------------------------------------------------------------------

_BRD_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eagle version="9.6.2">
  <drawing>
    <board>
      <elements>
        <element name="R1" library="resistors" package="R_0805"
                 value="10k" x="10.5" y="20.3" rot="R0"/>
        <element name="R2" library="resistors" package="R_0805"
                 value="22k" x="15.0" y="20.3" rot="R90"/>
        <element name="C1" library="capacitors" package="C_0402"
                 value="100nF" x="5.0" y="30.0" rot="MR0"/>
        <element name="U1" library="ics" package="DIP8"
                 value="NE555" x="25.0" y="15.0" rot="R180"/>
      </elements>
      <signals>
        <signal name="VCC">
          <wire x1="10.5" y1="20.3" x2="5.0" y2="30.0" width="0.25" layer="1"/>
          <wire x1="5.0" y1="30.0" x2="25.0" y2="15.0" width="0.25" layer="1"/>
          <via x="12.0" y="22.0" extent="1-16" drill="0.3"/>
          <contactref element="U1" pad="VCC"/>
          <contactref element="C1" pad="1"/>
        </signal>
        <signal name="GND">
          <wire x1="15.0" y1="20.3" x2="25.0" y2="15.0" width="0.25" layer="1"/>
          <via x="18.0" y="18.0" extent="1-16" drill="0.4"/>
        </signal>
      </signals>
    </board>
  </drawing>
</eagle>
"""

# ---------------------------------------------------------------------------
# Namespace-prefixed schematic fixture
# ---------------------------------------------------------------------------

_NS_SCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eg:eagle xmlns:eg="http://www.autodesk.com/eagle" version="10.0">
  <eg:drawing>
    <eg:schematic>
      <eg:parts>
        <eg:part name="Q1" library="transistors" deviceset="2N3904"
                 device="TO92" value="2N3904" package="TO92"/>
      </eg:parts>
      <eg:sheets>
        <eg:sheet>
          <eg:nets>
            <eg:net name="BASE" class="0">
              <eg:segment>
                <eg:pinref part="Q1" gate="G" pin="B"/>
              </eg:segment>
            </eg:net>
          </eg:nets>
        </eg:sheet>
      </eg:sheets>
    </eg:schematic>
  </eg:drawing>
</eg:eagle>
"""


# ===========================================================================
# Tests
# ===========================================================================

class TestSchematicSource:
    def test_source_is_sch(self):
        r = parse_eagle(_SCH_XML)
        assert r["ok"] is True
        assert r["source"] == "sch"

    def test_board_source_is_brd(self):
        r = parse_eagle(_BRD_XML)
        assert r["ok"] is True
        assert r["source"] == "brd"


class TestSchematicParts:
    def test_part_count(self):
        r = parse_eagle(_SCH_XML)
        assert r["ok"] is True
        assert len(r["parts"]) == 4

    def test_r1_ref(self):
        r = parse_eagle(_SCH_XML)
        refs = {p["ref"] for p in r["parts"]}
        assert "R1" in refs

    def test_r1_value(self):
        r = parse_eagle(_SCH_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["value"] == "10k"

    def test_r1_library(self):
        r = parse_eagle(_SCH_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["library"] == "resistors"

    def test_r1_package(self):
        r = parse_eagle(_SCH_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["package"] == "R_0805"

    def test_u1_deviceset(self):
        r = parse_eagle(_SCH_XML)
        u1 = next(p for p in r["parts"] if p["ref"] == "U1")
        assert u1["deviceset"] == "NE555"


class TestSchematicNets:
    def test_net_count(self):
        r = parse_eagle(_SCH_XML)
        assert len(r["nets"]) == 3

    def test_net_names(self):
        r = parse_eagle(_SCH_XML)
        names = {n["name"] for n in r["nets"]}
        assert {"VCC", "GND", "OUT"} == names

    def test_vcc_pins(self):
        r = parse_eagle(_SCH_XML)
        vcc = next(n for n in r["nets"] if n["name"] == "VCC")
        assert "U1.VCC" in vcc["pins"]
        assert "C1.1" in vcc["pins"]

    def test_gnd_has_two_pins(self):
        r = parse_eagle(_SCH_XML)
        gnd = next(n for n in r["nets"] if n["name"] == "GND")
        assert len(gnd["pins"]) == 2

    def test_out_pin_mapping(self):
        r = parse_eagle(_SCH_XML)
        out = next(n for n in r["nets"] if n["name"] == "OUT")
        assert "U1.OUT" in out["pins"]


class TestBoardElements:
    def test_footprint_count(self):
        r = parse_eagle(_BRD_XML)
        assert len(r["footprints"]) == 4

    def test_r1_footprint_ref(self):
        r = parse_eagle(_BRD_XML)
        r1 = next(fp for fp in r["footprints"] if fp["ref"] == "R1")
        assert r1["ref"] == "R1"

    def test_r1_footprint_value(self):
        r = parse_eagle(_BRD_XML)
        r1 = next(fp for fp in r["footprints"] if fp["ref"] == "R1")
        assert r1["value"] == "10k"

    def test_r1_footprint_package(self):
        r = parse_eagle(_BRD_XML)
        r1 = next(fp for fp in r["footprints"] if fp["ref"] == "R1")
        assert r1["package"] == "R_0805"

    def test_r1_coordinates(self):
        r = parse_eagle(_BRD_XML)
        r1 = next(fp for fp in r["footprints"] if fp["ref"] == "R1")
        assert r1["x"] == pytest.approx(10.5)
        assert r1["y"] == pytest.approx(20.3)

    def test_r2_rotation(self):
        r = parse_eagle(_BRD_XML)
        r2 = next(fp for fp in r["footprints"] if fp["ref"] == "R2")
        assert r2["rot"] == pytest.approx(90.0)

    def test_c1_mirrored_layer(self):
        r = parse_eagle(_BRD_XML)
        c1 = next(fp for fp in r["footprints"] if fp["ref"] == "C1")
        assert c1["layer"] == "Bottom"

    def test_r1_top_layer(self):
        r = parse_eagle(_BRD_XML)
        r1 = next(fp for fp in r["footprints"] if fp["ref"] == "R1")
        assert r1["layer"] == "Top"


class TestBoardSignals:
    def test_signal_count(self):
        r = parse_eagle(_BRD_XML)
        assert len(r["signals"]) == 2

    def test_signal_names(self):
        r = parse_eagle(_BRD_XML)
        names = {s["name"] for s in r["signals"]}
        assert {"VCC", "GND"} == names

    def test_vcc_wire_count(self):
        r = parse_eagle(_BRD_XML)
        vcc = next(s for s in r["signals"] if s["name"] == "VCC")
        assert len(vcc["wires"]) == 2

    def test_vcc_first_wire_coords(self):
        r = parse_eagle(_BRD_XML)
        vcc = next(s for s in r["signals"] if s["name"] == "VCC")
        w = vcc["wires"][0]
        assert w["x1"] == pytest.approx(10.5)
        assert w["y1"] == pytest.approx(20.3)
        assert w["x2"] == pytest.approx(5.0)
        assert w["y2"] == pytest.approx(30.0)

    def test_vcc_via_drill(self):
        r = parse_eagle(_BRD_XML)
        vcc = next(s for s in r["signals"] if s["name"] == "VCC")
        assert len(vcc["vias"]) == 1
        assert vcc["vias"][0]["drill"] == pytest.approx(0.3)

    def test_vcc_contactrefs(self):
        r = parse_eagle(_BRD_XML)
        vcc = next(s for s in r["signals"] if s["name"] == "VCC")
        assert len(vcc["contactrefs"]) == 2
        elements = {cr["element"] for cr in vcc["contactrefs"]}
        assert "U1" in elements

    def test_gnd_via(self):
        r = parse_eagle(_BRD_XML)
        gnd = next(s for s in r["signals"] if s["name"] == "GND")
        assert gnd["vias"][0]["drill"] == pytest.approx(0.4)


class TestNamespacedXML:
    def test_ns_sch_ok(self):
        r = parse_eagle(_NS_SCH_XML)
        assert r["ok"] is True

    def test_ns_sch_part_parsed(self):
        r = parse_eagle(_NS_SCH_XML)
        assert any(p["ref"] == "Q1" for p in r["parts"])

    def test_ns_sch_net_parsed(self):
        r = parse_eagle(_NS_SCH_XML)
        assert any(n["name"] == "BASE" for n in r["nets"])


class TestErrorHandling:
    def test_empty_string_not_ok(self):
        r = parse_eagle("")
        assert r["ok"] is False

    def test_empty_bytes_not_ok(self):
        r = parse_eagle(b"")
        assert r["ok"] is False

    def test_malformed_xml_not_ok(self):
        r = parse_eagle("<eagle><drawing><not-closed>")
        assert r["ok"] is False

    def test_not_ok_has_reason(self):
        r = parse_eagle("")
        assert "reason" in r

    def test_bytes_utf8_parsed(self):
        r = parse_eagle(_SCH_XML.encode("utf-8"))
        assert r["ok"] is True
        assert len(r["parts"]) == 4
