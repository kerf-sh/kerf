"""
test_allegro_reader.py — pytest suite for allegro_reader.py.

All fixtures are synthetic IPC-2581 XML / Allegro ASCII strings
constructed in-test.  No real Allegro files are used.  Tests cover:
  - IPC-2581 format detected
  - IPC-2581 part count from BomItem
  - IPC-2581 part ref extracted
  - IPC-2581 part_type from partName
  - IPC-2581 net count from LogicalNet
  - IPC-2581 net name extracted
  - IPC-2581 net pins (ref.pin format)
  - IPC-2581 component placement x/y
  - IPC-2581 component rotation
  - IPC-2581 component layer (Top/Bottom)
  - IPC-2581 footprint count from Component
  - IPC-2581 routing wire segments
  - IPC-2581 namespace-prefixed XML handled
  - Allegro ASCII format detected
  - Allegro ASCII $PACKAGES: part count
  - Allegro ASCII $PACKAGES: ref/part_type
  - Allegro ASCII $NETS: net count
  - Allegro ASCII $NETS: net name
  - Allegro ASCII $NETS: pin list
  - Allegro ASCII $LOCATIONS: x/y/rot from location data
  - Allegro ASCII $LOCATIONS: T/B layer assignment
  - Allegro ASCII unknown section emits warning
  - empty string → {"ok": False}
  - malformed XML → falls back to ASCII, or returns not-ok
  - bytes (UTF-8) accepted
  - not-ok has reason key
"""

from __future__ import annotations

import pytest

from kerf_imports.allegro_reader import parse_allegro


# ---------------------------------------------------------------------------
# IPC-2581 XML fixture
# ---------------------------------------------------------------------------

_IPC2581_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 xmlns="http://webstds.ipc.org/2581" revision="B">
  <Bom>
    <BomHeader>
      <StepRef name="BOARD"/>
    </BomHeader>
    <BomItem refDes="R1" partName="RES-0805" description="10k resistor"/>
    <BomItem refDes="R2" partName="RES-0805" description="22k resistor"/>
    <BomItem refDes="C1" partName="CAP-0402" description="100nF capacitor"/>
    <BomItem refDes="U1" partName="NE555" description="Timer IC"/>
  </Bom>
  <Netlist>
    <LogicalNet name="VCC">
      <PinRef componentRef="U1" pin="8"/>
      <PinRef componentRef="C1" pin="1"/>
      <PinRef componentRef="R1" pin="2"/>
    </LogicalNet>
    <LogicalNet name="GND">
      <PinRef componentRef="R1" pin="1"/>
      <PinRef componentRef="R2" pin="1"/>
    </LogicalNet>
    <LogicalNet name="OUT">
      <PinRef componentRef="U1" pin="3"/>
      <PinRef componentRef="R2" pin="2"/>
    </LogicalNet>
  </Netlist>
  <Step name="BOARD">
    <Component refDes="R1" part="RES-0805" layerRef="TOP">
      <Xform x="10.5" y="20.3" rotation="0"/>
    </Component>
    <Component refDes="R2" part="RES-0805" layerRef="TOP">
      <Xform x="15.0" y="20.3" rotation="90"/>
    </Component>
    <Component refDes="C1" part="CAP-0402" layerRef="BOTTOM">
      <Xform x="5.0" y="30.0" rotation="0"/>
    </Component>
    <Component refDes="U1" part="NE555" layerRef="TOP">
      <Xform x="25.0" y="15.0" rotation="180"/>
    </Component>
    <LayerFeature layerRef="TOP">
      <Set>
        <Line>
          <Pt x="10.5" y="20.3"/>
          <Pt x="5.0" y="30.0"/>
        </Line>
        <Line>
          <Pt x="5.0" y="30.0"/>
          <Pt x="25.0" y="15.0"/>
        </Line>
      </Set>
    </LayerFeature>
    <LayerFeature layerRef="BOTTOM">
      <Set>
        <Line>
          <Pt x="15.0" y="20.3"/>
          <Pt x="25.0" y="15.0"/>
        </Line>
      </Set>
    </LayerFeature>
  </Step>
</IPC-2581>
"""

# ---------------------------------------------------------------------------
# Namespace-prefixed IPC-2581
# ---------------------------------------------------------------------------

_IPC2581_NS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ipc:IPC-2581 xmlns:ipc="http://webstds.ipc.org/2581" revision="B">
  <ipc:Bom>
    <ipc:BomItem refDes="Q1" partName="2N3904" description="NPN transistor"/>
  </ipc:Bom>
  <ipc:Netlist>
    <ipc:LogicalNet name="BASE">
      <ipc:PinRef componentRef="Q1" pin="B"/>
    </ipc:LogicalNet>
  </ipc:Netlist>
</ipc:IPC-2581>
"""

# ---------------------------------------------------------------------------
# Allegro ASCII fixture
# ---------------------------------------------------------------------------

_ALLEGRO_ASC = """\
# Allegro ASCII Board Export
# Format: ASCII

$PACKAGES
R1    RES-0805   10k
R2    RES-0805   22k
C1    CAP-0402   100nF
U1    NE555      NE555

$NETS
VCC
U1.8 C1.1 R1.2
GND
R1.1 R2.1
OUT
U1.3 R2.2

$LOCATIONS
R1    10.5   20.3   0.0    T
R2    15.0   20.3   90.0   T
C1    5.0    30.0   0.0    B
U1    25.0   15.0   180.0  T

$END
"""

# ---------------------------------------------------------------------------
# Minimal Allegro ASCII with unknown section
# ---------------------------------------------------------------------------

_ALLEGRO_UNKNOWN_SECTION = """\
$PACKAGES
X1 XTAL-SMD

$FUTURISTIC_SECTION
some future data

$END
"""


# ===========================================================================
# Tests
# ===========================================================================

class TestIPC2581Format:
    def test_format_is_ipc2581(self):
        r = parse_allegro(_IPC2581_XML)
        assert r["ok"] is True
        assert r["format"] == "ipc2581"

    def test_part_count(self):
        r = parse_allegro(_IPC2581_XML)
        assert len(r["parts"]) == 4

    def test_r1_ref(self):
        r = parse_allegro(_IPC2581_XML)
        refs = {p["ref"] for p in r["parts"]}
        assert "R1" in refs

    def test_r1_part_type(self):
        r = parse_allegro(_IPC2581_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["part_type"] == "RES-0805"

    def test_net_count(self):
        r = parse_allegro(_IPC2581_XML)
        assert len(r["nets"]) == 3

    def test_net_names(self):
        r = parse_allegro(_IPC2581_XML)
        names = {n["name"] for n in r["nets"]}
        assert {"VCC", "GND", "OUT"} == names

    def test_vcc_pins(self):
        r = parse_allegro(_IPC2581_XML)
        vcc = next(n for n in r["nets"] if n["name"] == "VCC")
        assert "U1.8" in vcc["pins"]
        assert "C1.1" in vcc["pins"]

    def test_gnd_pin_count(self):
        r = parse_allegro(_IPC2581_XML)
        gnd = next(n for n in r["nets"] if n["name"] == "GND")
        assert len(gnd["pins"]) == 2

    def test_r1_placement_x(self):
        r = parse_allegro(_IPC2581_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["x"] == pytest.approx(10.5)

    def test_r1_placement_y(self):
        r = parse_allegro(_IPC2581_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["y"] == pytest.approx(20.3)

    def test_r2_rotation(self):
        r = parse_allegro(_IPC2581_XML)
        r2 = next(p for p in r["parts"] if p["ref"] == "R2")
        assert r2["rot"] == pytest.approx(90.0)

    def test_c1_bottom_layer(self):
        r = parse_allegro(_IPC2581_XML)
        c1 = next(p for p in r["parts"] if p["ref"] == "C1")
        assert c1["layer"] == "Bottom"

    def test_r1_top_layer(self):
        r = parse_allegro(_IPC2581_XML)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["layer"] == "Top"

    def test_footprint_count(self):
        r = parse_allegro(_IPC2581_XML)
        assert len(r["footprints"]) >= 4

    def test_routing_signals(self):
        r = parse_allegro(_IPC2581_XML)
        assert len(r["signals"]) >= 2

    def test_top_layer_wire_count(self):
        r = parse_allegro(_IPC2581_XML)
        top = next(s for s in r["signals"] if s["name"] == "TOP")
        assert len(top["wires"]) == 2


class TestIPC2581Namespace:
    def test_ns_ok(self):
        r = parse_allegro(_IPC2581_NS_XML)
        assert r["ok"] is True

    def test_ns_part_parsed(self):
        r = parse_allegro(_IPC2581_NS_XML)
        assert any(p["ref"] == "Q1" for p in r["parts"])

    def test_ns_net_parsed(self):
        r = parse_allegro(_IPC2581_NS_XML)
        names = {n["name"] for n in r["nets"]}
        assert "BASE" in names


class TestAllegroASC:
    def test_format_is_allegro_asc(self):
        r = parse_allegro(_ALLEGRO_ASC)
        assert r["ok"] is True
        assert r["format"] == "allegro_asc"

    def test_part_count(self):
        r = parse_allegro(_ALLEGRO_ASC)
        assert len(r["parts"]) == 4

    def test_r1_ref(self):
        r = parse_allegro(_ALLEGRO_ASC)
        refs = {p["ref"] for p in r["parts"]}
        assert "R1" in refs

    def test_r1_part_type(self):
        r = parse_allegro(_ALLEGRO_ASC)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["part_type"] == "RES-0805"

    def test_net_count(self):
        r = parse_allegro(_ALLEGRO_ASC)
        assert len(r["nets"]) == 3

    def test_net_names(self):
        r = parse_allegro(_ALLEGRO_ASC)
        names = {n["name"] for n in r["nets"]}
        assert {"VCC", "GND", "OUT"} == names

    def test_vcc_pins(self):
        r = parse_allegro(_ALLEGRO_ASC)
        vcc = next(n for n in r["nets"] if n["name"] == "VCC")
        assert "U1.8" in vcc["pins"]

    def test_r1_x_from_locations(self):
        r = parse_allegro(_ALLEGRO_ASC)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["x"] == pytest.approx(10.5)

    def test_c1_bottom_layer(self):
        r = parse_allegro(_ALLEGRO_ASC)
        c1 = next(p for p in r["parts"] if p["ref"] == "C1")
        assert c1["layer"] == "Bottom"

    def test_r1_top_layer(self):
        r = parse_allegro(_ALLEGRO_ASC)
        r1 = next(p for p in r["parts"] if p["ref"] == "R1")
        assert r1["layer"] == "Top"

    def test_unknown_section_warning(self):
        r = parse_allegro(_ALLEGRO_UNKNOWN_SECTION)
        assert r["ok"] is True
        assert any("FUTURISTIC_SECTION" in w for w in r["warnings"])


class TestErrorHandling:
    def test_empty_string_not_ok(self):
        r = parse_allegro("")
        assert r["ok"] is False

    def test_empty_bytes_not_ok(self):
        r = parse_allegro(b"")
        assert r["ok"] is False

    def test_not_ok_has_reason(self):
        r = parse_allegro("")
        assert "reason" in r

    def test_bytes_utf8_accepted_ipc2581(self):
        r = parse_allegro(_IPC2581_XML.encode("utf-8"))
        assert r["ok"] is True
        assert len(r["parts"]) == 4

    def test_bytes_utf8_accepted_asc(self):
        r = parse_allegro(_ALLEGRO_ASC.encode("utf-8"))
        assert r["ok"] is True

    def test_malformed_xml_falls_back(self):
        # Broken XML that starts with '<' should try ASCII fallback
        broken = "<IPC-2581><broken-tag>no close\n$PACKAGES\nX1 XTAL\n$END\n"
        r = parse_allegro(broken)
        # Should either succeed via ASCII fallback or return not-ok with reason
        if r["ok"]:
            assert len(r["parts"]) >= 1
        else:
            assert "reason" in r
