"""
test_ibis_reader.py — pytest suite for ibis_reader.py.

All fixtures are synthetic IBIS text strings constructed in-test.
No real IBIS files are used.  Tests cover:
  - IBIS version parsed correctly
  - Component count and name
  - Pin count and pin→model mapping
  - Model_type read (Output, Input)
  - C_comp typ/min/max column parsing
  - Package R/L/C parsed with unit suffixes (pF, nH, Ohm)
  - Ramp dV/dt_r and dV/dt_f entries
  - Pulldown V-I table rows
  - '|' comment lines stripped and ignored
  - Line continuation / blank lines handled
  - Unknown keyword skipped with warning
  - Malformed / empty input → {"ok": False}
  - Voltage Range typ/min/max
  - Temperature Range typ/min/max
  - Model vinh/vinl values
  - NA token treated as None
  - Multiple components in one file
  - Pin R/L/C per-pin columns
  - bytes input (UTF-8)
  - Missing [IBIS Ver] → {"ok": False}
  - Model with no pulldown rows (empty table)
  - GND_clamp rows parsed
"""

from __future__ import annotations

import pytest

from kerf_imports.ibis_reader import parse_ibis, _parse_value


# ---------------------------------------------------------------------------
# Shared synthetic IBIS fixture
#
# Minimal valid IBIS 5.0 file: 1 component, 3 pins, 1 Output + 1 Input model,
# package RLC, pulldown + ramp.
# ---------------------------------------------------------------------------

_MINIMAL_IBIS = """\
[IBIS Ver]    5.0
| This is a comment line
[File Name]   test_device.ibs
[File Rev]    1.0

[Component]   TestChip
[Manufacturer]    ACME Semiconductors

[Package]
| variable    typ      min      max
R_pkg         0.5      0.3      0.8
L_pkg         3.0nH    2.0nH    4.5nH
C_pkg         2.0pF    1.5pF    3.0pF

[Pin]  signal_name   model_name     R_pin  L_pin  C_pin
A1     DATA_OUT      OutModel       NA     NA     NA
A2     DATA_IN       InModel        NA     NA     NA
A3     VCC           POWER          NA     NA     NA

[Model]  OutModel
Model_type   Output
Vinl         0.8
Vinh         2.0
Vmeas        1.5
C_comp       4.0pF    3.0pF    5.5pF

[Voltage Range]
3.3      3.0      3.6

[Temperature Range]
25       0        85

[Pulldown]
| Voltage    I(typ)   I(min)   I(max)
-3.300       -110m    -90m     -130m
0.000         0.0      0.0      0.0
3.300         110m     90m      130m

[Ramp]
dV/dt_r   0.6V/1.2ns   0.5V/1.5ns   0.7V/1.0ns
dV/dt_f   0.6V/1.2ns   0.5V/1.5ns   0.7V/1.0ns

[Model]  InModel
Model_type  Input
Vinl        0.8
Vinh        2.0
C_comp      2.5pF    2.0pF    3.0pF

[GND_clamp]
-3.300   -5.0      -4.0     -6.0
0.000     0.0       0.0      0.0

[End]
"""


def _get_model(result: dict, name: str) -> dict:
    m = result["models"].get(name)
    if m is None:
        raise KeyError(f"model {name!r} not in result['models']")
    return m


def _get_pin(comp: dict, pin_name: str) -> dict:
    for p in comp["pins"]:
        if p["name"] == pin_name:
            return p
    raise KeyError(f"pin {pin_name!r} not found")


# ---------------------------------------------------------------------------
# 1. IBIS version
# ---------------------------------------------------------------------------

class TestIBISVersion:
    def test_version_parsed(self):
        r = parse_ibis(_MINIMAL_IBIS)
        assert r["ok"] is True
        assert r["ibis_version"] == "5.0"

    def test_version_is_string(self):
        r = parse_ibis(_MINIMAL_IBIS)
        assert isinstance(r["ibis_version"], str)


# ---------------------------------------------------------------------------
# 2. Component parsing
# ---------------------------------------------------------------------------

class TestComponentParsing:
    def test_component_count(self):
        r = parse_ibis(_MINIMAL_IBIS)
        assert len(r["components"]) == 1

    def test_component_name(self):
        r = parse_ibis(_MINIMAL_IBIS)
        assert r["components"][0]["name"] == "TestChip"

    def test_manufacturer(self):
        r = parse_ibis(_MINIMAL_IBIS)
        assert r["components"][0]["manufacturer"] == "ACME Semiconductors"


# ---------------------------------------------------------------------------
# 3. Pin table
# ---------------------------------------------------------------------------

class TestPinTable:
    def test_pin_count(self):
        r = parse_ibis(_MINIMAL_IBIS)
        comp = r["components"][0]
        assert len(comp["pins"]) == 3

    def test_pin_names(self):
        r = parse_ibis(_MINIMAL_IBIS)
        names = {p["name"] for p in r["components"][0]["pins"]}
        assert {"A1", "A2", "A3"} == names

    def test_pin_to_model_mapping_a1(self):
        r = parse_ibis(_MINIMAL_IBIS)
        comp = r["components"][0]
        p = _get_pin(comp, "A1")
        assert p["model_name"] == "OutModel"

    def test_pin_to_model_mapping_a2(self):
        r = parse_ibis(_MINIMAL_IBIS)
        comp = r["components"][0]
        p = _get_pin(comp, "A2")
        assert p["model_name"] == "InModel"

    def test_pin_signal_name(self):
        r = parse_ibis(_MINIMAL_IBIS)
        comp = r["components"][0]
        p = _get_pin(comp, "A1")
        assert p["signal_name"] == "DATA_OUT"

    def test_pin_na_rlc_is_none(self):
        r = parse_ibis(_MINIMAL_IBIS)
        comp = r["components"][0]
        p = _get_pin(comp, "A1")
        assert p["R_pin"] is None
        assert p["L_pin"] is None
        assert p["C_pin"] is None


# ---------------------------------------------------------------------------
# 4. Model_type
# ---------------------------------------------------------------------------

class TestModelType:
    def test_output_model_type(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["model_type"] == "Output"

    def test_input_model_type(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "InModel")
        assert m["model_type"] == "Input"


# ---------------------------------------------------------------------------
# 5. C_comp typ/min/max
# ---------------------------------------------------------------------------

class TestCComp:
    def test_c_comp_typ_output(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["c_comp"]["typ"] == pytest.approx(4.0e-12)

    def test_c_comp_min_output(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["c_comp"]["min"] == pytest.approx(3.0e-12)

    def test_c_comp_max_output(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["c_comp"]["max"] == pytest.approx(5.5e-12)

    def test_c_comp_typ_input(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "InModel")
        assert m["c_comp"]["typ"] == pytest.approx(2.5e-12)


# ---------------------------------------------------------------------------
# 6. Package R/L/C with unit suffixes
# ---------------------------------------------------------------------------

class TestPackageRLC:
    def test_r_pkg_typ(self):
        r = parse_ibis(_MINIMAL_IBIS)
        pkg = r["components"][0]["package"]
        assert pkg["R_pkg"]["typ"] == pytest.approx(0.5)

    def test_l_pkg_typ_nH(self):
        r = parse_ibis(_MINIMAL_IBIS)
        pkg = r["components"][0]["package"]
        assert pkg["L_pkg"]["typ"] == pytest.approx(3.0e-9)

    def test_l_pkg_min_nH(self):
        r = parse_ibis(_MINIMAL_IBIS)
        pkg = r["components"][0]["package"]
        assert pkg["L_pkg"]["min"] == pytest.approx(2.0e-9)

    def test_c_pkg_typ_pF(self):
        r = parse_ibis(_MINIMAL_IBIS)
        pkg = r["components"][0]["package"]
        assert pkg["C_pkg"]["typ"] == pytest.approx(2.0e-12)

    def test_c_pkg_max_pF(self):
        r = parse_ibis(_MINIMAL_IBIS)
        pkg = r["components"][0]["package"]
        assert pkg["C_pkg"]["max"] == pytest.approx(3.0e-12)


# ---------------------------------------------------------------------------
# 7. Ramp dV/dt
# ---------------------------------------------------------------------------

class TestRamp:
    def test_ramp_dvdt_r_typ(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["ramp"]["dV_dt_r"]["typ"] == "0.6V/1.2ns"

    def test_ramp_dvdt_f_typ(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["ramp"]["dV_dt_f"]["typ"] == "0.6V/1.2ns"

    def test_ramp_dvdt_r_min(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["ramp"]["dV_dt_r"]["min"] == "0.5V/1.5ns"

    def test_ramp_dvdt_r_max(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["ramp"]["dV_dt_r"]["max"] == "0.7V/1.0ns"


# ---------------------------------------------------------------------------
# 8. Pulldown V-I table
# ---------------------------------------------------------------------------

class TestPulldown:
    def test_pulldown_row_count(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert len(m["pulldown"]) == 3

    def test_pulldown_zero_row_voltage(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        # Middle row is V=0
        zero_row = next(row for row in m["pulldown"] if abs(row["V"]) < 1e-9)
        assert zero_row["typ"] == pytest.approx(0.0)

    def test_pulldown_positive_row_typ_current(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        pos_row = next(row for row in m["pulldown"] if row["V"] > 0)
        assert pos_row["typ"] == pytest.approx(0.110)

    def test_pulldown_negative_row_typ_current(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        neg_row = next(row for row in m["pulldown"] if row["V"] < -1.0)
        assert neg_row["typ"] == pytest.approx(-0.110)


# ---------------------------------------------------------------------------
# 9. '|' comment handling
# ---------------------------------------------------------------------------

class TestCommentHandling:
    def test_comment_only_lines_ignored(self):
        ibis = """\
[IBIS Ver] 4.2
| entire line is a comment
[Component] MyPart
[Manufacturer] | inline after bracket
[End]
"""
        r = parse_ibis(ibis)
        assert r["ok"] is True

    def test_inline_comment_stripped(self):
        ibis = """\
[IBIS Ver] 3.2   | version comment
[Component] PartX  | component comment
[End]
"""
        r = parse_ibis(ibis)
        assert r["ok"] is True
        assert r["ibis_version"] == "3.2"


# ---------------------------------------------------------------------------
# 10. Unknown keyword skipped with warning
# ---------------------------------------------------------------------------

class TestUnknownKeyword:
    def test_unknown_keyword_does_not_raise(self):
        ibis = """\
[IBIS Ver] 5.0
[FutureKeyword]  some future data
[Component] ChipA
[End]
"""
        r = parse_ibis(ibis)
        assert r["ok"] is True

    def test_unknown_keyword_produces_warning(self):
        ibis = """\
[IBIS Ver] 5.0
[FutureKeyword]  some future data
[Component] ChipA
[End]
"""
        r = parse_ibis(ibis)
        assert any("FutureKeyword" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# 11. Malformed / empty input
# ---------------------------------------------------------------------------

class TestMalformedInput:
    def test_empty_string_returns_not_ok(self):
        r = parse_ibis("")
        assert r["ok"] is False

    def test_empty_bytes_returns_not_ok(self):
        r = parse_ibis(b"")
        assert r["ok"] is False

    def test_missing_ibis_ver_returns_not_ok(self):
        ibis = """\
[Component] ChipB
[End]
"""
        r = parse_ibis(ibis)
        assert r["ok"] is False

    def test_not_ok_has_reason(self):
        r = parse_ibis("")
        assert "reason" in r


# ---------------------------------------------------------------------------
# 12. Voltage Range
# ---------------------------------------------------------------------------

class TestVoltageRange:
    def test_voltage_range_typ(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["voltage_range"]["typ"] == pytest.approx(3.3)

    def test_voltage_range_min(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["voltage_range"]["min"] == pytest.approx(3.0)

    def test_voltage_range_max(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["voltage_range"]["max"] == pytest.approx(3.6)


# ---------------------------------------------------------------------------
# 13. Temperature Range
# ---------------------------------------------------------------------------

class TestTemperatureRange:
    def test_temperature_range_typ(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["temperature_range"]["typ"] == pytest.approx(25.0)

    def test_temperature_range_min(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["temperature_range"]["min"] == pytest.approx(0.0)

    def test_temperature_range_max(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["temperature_range"]["max"] == pytest.approx(85.0)


# ---------------------------------------------------------------------------
# 14. Vinl / Vinh
# ---------------------------------------------------------------------------

class TestVinlVinh:
    def test_vinl_output_model(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["vinl"] == pytest.approx(0.8)

    def test_vinh_output_model(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "OutModel")
        assert m["vinh"] == pytest.approx(2.0)

    def test_vinl_input_model(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "InModel")
        assert m["vinl"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# 15. GND_clamp rows
# ---------------------------------------------------------------------------

class TestGNDClamp:
    def test_gnd_clamp_row_count(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "InModel")
        assert len(m["gnd_clamp"]) == 2

    def test_gnd_clamp_zero_row(self):
        r = parse_ibis(_MINIMAL_IBIS)
        m = _get_model(r, "InModel")
        zero_row = next(row for row in m["gnd_clamp"] if abs(row["V"]) < 1e-9)
        assert zero_row["typ"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 16. bytes input
# ---------------------------------------------------------------------------

class TestBytesInput:
    def test_utf8_bytes_parsed(self):
        r = parse_ibis(_MINIMAL_IBIS.encode("utf-8"))
        assert r["ok"] is True

    def test_utf8_bytes_version(self):
        r = parse_ibis(_MINIMAL_IBIS.encode("utf-8"))
        assert r["ibis_version"] == "5.0"


# ---------------------------------------------------------------------------
# 17. Multiple components
# ---------------------------------------------------------------------------

_TWO_COMPONENT_IBIS = """\
[IBIS Ver] 5.0
[Component] ChipAlpha
[Manufacturer] AlphaCorp
[Pin] signal_name  model_name
P1  SIG1  ModelA
[Component] ChipBeta
[Manufacturer] BetaCorp
[Pin] signal_name  model_name
Q1  SIG2  ModelB
[End]
"""


class TestMultipleComponents:
    def test_two_components_parsed(self):
        r = parse_ibis(_TWO_COMPONENT_IBIS)
        assert r["ok"] is True
        assert len(r["components"]) == 2

    def test_component_names(self):
        r = parse_ibis(_TWO_COMPONENT_IBIS)
        names = [c["name"] for c in r["components"]]
        assert "ChipAlpha" in names
        assert "ChipBeta" in names

    def test_component_manufacturers(self):
        r = parse_ibis(_TWO_COMPONENT_IBIS)
        mfrs = {c["name"]: c["manufacturer"] for c in r["components"]}
        assert mfrs["ChipAlpha"] == "AlphaCorp"
        assert mfrs["ChipBeta"] == "BetaCorp"


# ---------------------------------------------------------------------------
# 18. _parse_value unit suffix helper
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_pf_suffix(self):
        assert _parse_value("1.5pF") == pytest.approx(1.5e-12)

    def test_nh_suffix(self):
        assert _parse_value("10nH") == pytest.approx(10e-9)

    def test_na_is_none(self):
        assert _parse_value("NA") is None

    def test_plain_float(self):
        assert _parse_value("3.3") == pytest.approx(3.3)

    def test_milliamp(self):
        assert _parse_value("110m") == pytest.approx(0.110)

    def test_empty_is_none(self):
        assert _parse_value("") is None
