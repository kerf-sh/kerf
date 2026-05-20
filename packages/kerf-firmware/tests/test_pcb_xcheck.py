"""Tests for kerf_firmware.pcb_xcheck — pin-mapping verification.

Fixtures
--------
match/        — all pins correct; expects ok=True, no violations.
mismatch/     — fw uses pin 20 for SDA but PCB routes SDA to pin 21;
                expects missing_pins=["20"] and a bus_incomplete violation
                (SDA pin 20 not on PCB).
missing_scl/  — fw declares SDA (pin 21) via constant but never declares SCL;
                expects bus_incomplete citing missing SCL.
input_only/   — fw drives pin 0 as OUTPUT but PCB routes pin 0 to INPUT_ONLY net;
                expects wrong_load=[(0, ...)] violation.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from kerf_firmware.pcb_xcheck import verify, XcheckReport
from kerf_firmware.pcb_xcheck.fw_pins import extract_fw_pins
from kerf_firmware.pcb_xcheck.pcb_pins import parse_kicad_pcb_pins
from kerf_firmware.pcb_xcheck.compare import compare

# ── Fixture helpers ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "xcheck"


def _load_fixture(name: str) -> tuple[list[str], str]:
    """Return (fw_sources, pcb_text) for a named fixture directory."""
    d = FIXTURES / name
    pcb_text = (d / "board.kicad_pcb").read_text(encoding="utf-8")
    ino_text  = (d / "main.ino").read_text(encoding="utf-8")
    return [ino_text], pcb_text


# ── Fixture: match (zero violations) ─────────────────────────────────────────

class TestMatchFixture:
    """All pins correct; expects ok=True with no violations."""

    def test_ok_true(self):
        sources, pcb = _load_fixture("match")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.ok is True, f"Expected ok=True, got: {report.as_dict()}"

    def test_missing_pins_empty(self):
        sources, pcb = _load_fixture("match")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.missing_pins == [], report.missing_pins

    def test_wrong_load_empty(self):
        sources, pcb = _load_fixture("match")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.wrong_load == [], report.wrong_load

    def test_bus_incomplete_empty(self):
        sources, pcb = _load_fixture("match")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.bus_incomplete == [], report.bus_incomplete

    def test_pin_mismatch_empty(self):
        sources, pcb = _load_fixture("match")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.pin_mismatch == [], report.pin_mismatch

    def test_as_dict_schema(self):
        sources, pcb = _load_fixture("match")
        d = verify(fw_sources=sources, pcb_text=pcb).as_dict()
        assert set(d.keys()) == {"ok", "missing_pins", "wrong_load", "bus_incomplete", "pin_mismatch"}
        assert d["ok"] is True


# ── Fixture: mismatch (SDA pin mismatch → missing pin 20) ─────────────────────

class TestMismatchFixture:
    """Firmware uses pin 20 for SDA; PCB has SDA on pin 21."""

    def test_ok_false(self):
        sources, pcb = _load_fixture("mismatch")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.ok is False, f"Expected ok=False, got: {report.as_dict()}"

    def test_missing_pin_20(self):
        """Pin 20 is used for SDA in fw but does not exist in the PCB footprint."""
        sources, pcb = _load_fixture("mismatch")
        report = verify(fw_sources=sources, pcb_text=pcb)
        # pin 20 should be in missing_pins because it's not on the PCB
        assert "20" in report.missing_pins, (
            f"Expected pin '20' in missing_pins; got: {report.missing_pins}\n"
            f"Full report: {report.as_dict()}"
        )

    def test_missing_pins_mentions_both_sides(self):
        """Verify the violation message context covers both FW-side and PCB-side info."""
        sources, pcb = _load_fixture("mismatch")
        report = verify(fw_sources=sources, pcb_text=pcb)
        # The pin that IS on PCB for SDA (pin 21) should NOT be in missing_pins
        assert "21" not in report.missing_pins, (
            f"Pin 21 is valid on the PCB; should NOT be in missing_pins: {report.missing_pins}"
        )

    def test_violation_count_at_least_one(self):
        sources, pcb = _load_fixture("mismatch")
        report = verify(fw_sources=sources, pcb_text=pcb)
        total = (
            len(report.missing_pins)
            + len(report.wrong_load)
            + len(report.bus_incomplete)
            + len(report.pin_mismatch)
        )
        assert total >= 1, f"Expected ≥1 violation; got 0. Report: {report.as_dict()}"


# ── Fixture: missing_scl (bus-incomplete violation) ───────────────────────────

class TestMissingScl:
    """Firmware has SDA but no SCL → bus_incomplete violation."""

    def test_ok_false(self):
        sources, pcb = _load_fixture("missing_scl")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.ok is False, f"Expected ok=False, got: {report.as_dict()}"

    def test_bus_incomplete_has_scl_mention(self):
        """bus_incomplete should mention SCL missing."""
        sources, pcb = _load_fixture("missing_scl")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert len(report.bus_incomplete) >= 1, (
            f"Expected ≥1 bus_incomplete entry; got: {report.bus_incomplete}"
        )
        combined = " ".join(report.bus_incomplete).lower()
        assert "scl" in combined, (
            f"Expected 'scl' to appear in bus_incomplete; got: {report.bus_incomplete}"
        )

    def test_sda_extracted(self):
        """fw_pins should detect SDA=21 from the constant #define SDA_PIN 21."""
        sources, _ = _load_fixture("missing_scl")
        fw_map = extract_fw_pins(sources)
        assert fw_map.i2c_sda == "21", (
            f"Expected i2c_sda='21'; got {fw_map.i2c_sda!r}"
        )

    def test_scl_absent(self):
        """fw_pins should find no SCL constant or Wire.begin(sda, scl) call."""
        sources, _ = _load_fixture("missing_scl")
        fw_map = extract_fw_pins(sources)
        assert fw_map.i2c_scl is None, (
            f"Expected i2c_scl=None; got {fw_map.i2c_scl!r}"
        )


# ── Fixture: input_only (wrong_load violation) ────────────────────────────────

class TestInputOnly:
    """Firmware drives pin 0 OUTPUT but PCB routes it to INPUT_ONLY_BOOT net."""

    def test_ok_false(self):
        sources, pcb = _load_fixture("input_only")
        report = verify(fw_sources=sources, pcb_text=pcb)
        assert report.ok is False, f"Expected ok=False, got: {report.as_dict()}"

    def test_wrong_load_has_pin_0(self):
        sources, pcb = _load_fixture("input_only")
        report = verify(fw_sources=sources, pcb_text=pcb)
        wrong_pins = [wl[0] for wl in report.wrong_load]
        assert "0" in wrong_pins, (
            f"Expected pin '0' in wrong_load pins; got: {report.wrong_load}"
        )

    def test_wrong_load_reason_mentions_input_only(self):
        sources, pcb = _load_fixture("input_only")
        report = verify(fw_sources=sources, pcb_text=pcb)
        reasons = " ".join(r for _, r in report.wrong_load).lower()
        assert "input-only" in reasons, (
            f"Expected 'input-only' in wrong_load reason; got: {report.wrong_load}"
        )

    def test_led_pin_not_flagged(self):
        """Pin 13 (LED, OUTPUT) is fine — should not appear in any violation."""
        sources, pcb = _load_fixture("input_only")
        report = verify(fw_sources=sources, pcb_text=pcb)
        wrong_pins = [wl[0] for wl in report.wrong_load]
        assert "13" not in wrong_pins, (
            f"Pin 13 should not be in wrong_load; got: {report.wrong_load}"
        )


# ── Unit tests: fw_pins extraction ────────────────────────────────────────────

class TestFwPinsUnit:
    """Unit-level tests for the firmware pin extractor."""

    def test_pinmode_output(self):
        src = "void setup() { pinMode(13, OUTPUT); }"
        fw = extract_fw_pins([src])
        assert "13" in fw.all_pins
        assert fw.pin_modes.get("13") == "OUTPUT"

    def test_pinmode_input(self):
        src = "void setup() { pinMode(7, INPUT); }"
        fw = extract_fw_pins([src])
        assert "7" in fw.all_pins
        assert fw.pin_modes.get("7") == "INPUT"

    def test_digital_write(self):
        src = "void loop() { digitalWrite(5, HIGH); }"
        fw = extract_fw_pins([src])
        assert "5" in fw.all_pins

    def test_analog_read(self):
        src = "void loop() { int v = analogRead(A0); }"
        fw = extract_fw_pins([src])
        assert "A0" in fw.all_pins

    def test_wire_begin_extracts_i2c(self):
        src = "void setup() { Wire.begin(21, 22); }"
        fw = extract_fw_pins([src])
        assert fw.i2c_sda == "21"
        assert fw.i2c_scl == "22"

    def test_define_constant_resolution(self):
        src = "#define SDA_PIN 21\n#define SCL_PIN 22\nvoid setup() { Wire.begin(SDA_PIN, SCL_PIN); }"
        fw = extract_fw_pins([src])
        assert fw.i2c_sda == "21"
        assert fw.i2c_scl == "22"

    def test_const_int_resolution(self):
        src = "const int LED_PIN = 13;\nvoid setup() { pinMode(LED_PIN, OUTPUT); }"
        fw = extract_fw_pins([src])
        assert "13" in fw.all_pins
        assert fw.pin_modes.get("13") == "OUTPUT"

    def test_multiple_sources(self):
        src1 = "#define LED_PIN 13\n"
        src2 = "void setup() { pinMode(LED_PIN, OUTPUT); }"
        fw = extract_fw_pins([src1, src2])
        assert "13" in fw.all_pins

    def test_llm_confidence_threshold(self):
        """Inferred uses with confidence < 0.6 should not appear in all_pins."""
        src = "#define MYSTERY_PIN 99\nvoid setup() { pinMode(MYSTERY_PIN, OUTPUT); }"
        fw = extract_fw_pins([src])
        # MYSTERY_PIN resolves via constant → confidence 1.0, must appear
        assert "99" in fw.all_pins

    def test_sda_constant_fallback(self):
        """#define SDA_PIN 21 with no Wire.begin → inferred sda via constant name."""
        src = "#define SDA_PIN 21\nvoid setup() { }"
        fw = extract_fw_pins([src])
        assert fw.i2c_sda == "21"
        assert fw.i2c_scl is None


# ── Unit tests: pcb_pins extraction ───────────────────────────────────────────

class TestPcbPinsUnit:
    """Unit-level tests for the PCB pin extractor."""

    def test_basic_pad_extraction(self):
        _, pcb = _load_fixture("match")
        pins = parse_kicad_pcb_pins(pcb, ref="U1")
        assert "21" in pins
        assert "22" in pins
        assert "13" in pins

    def test_net_names(self):
        _, pcb = _load_fixture("match")
        pins = parse_kicad_pcb_pins(pcb, ref="U1")
        assert pins["21"].net == "SDA"
        assert pins["22"].net == "SCL"

    def test_i2c_direction_inferred(self):
        _, pcb = _load_fixture("match")
        pins = parse_kicad_pcb_pins(pcb, ref="U1")
        assert pins["21"].direction == "i2c"
        assert pins["22"].direction == "i2c"

    def test_input_only_direction(self):
        _, pcb = _load_fixture("input_only")
        pins = parse_kicad_pcb_pins(pcb, ref="U1")
        assert "0" in pins
        assert pins["0"].direction == "input_only"

    def test_auto_detect_first_u_ref(self):
        _, pcb = _load_fixture("match")
        # No ref specified — should auto-detect U1
        pins = parse_kicad_pcb_pins(pcb)
        assert "21" in pins

    def test_missing_ref_returns_empty(self):
        _, pcb = _load_fixture("match")
        pins = parse_kicad_pcb_pins(pcb, ref="U99")
        assert pins == {}

    def test_empty_pcb(self):
        pins = parse_kicad_pcb_pins("(kicad_pcb (version 20211014))")
        assert pins == {}


# ── LLM tool smoke test ────────────────────────────────────────────────────────

class TestVerifyPinMappingTool:
    """Smoke-test the LLM tool wrapper."""

    def test_tool_match_fixture(self):
        import json
        from kerf_firmware.tools.verify_pin_mapping import verify_pin_mapping

        fw_path = str(FIXTURES / "match" / "main.ino")
        pcb_path = str(FIXTURES / "match" / "board.kicad_pcb")
        result = json.loads(verify_pin_mapping({"fw_path": fw_path, "pcb_path": pcb_path}))
        assert result.get("ok") is True, result

    def test_tool_mismatch_fixture(self):
        import json
        from kerf_firmware.tools.verify_pin_mapping import verify_pin_mapping

        fw_path = str(FIXTURES / "mismatch" / "main.ino")
        pcb_path = str(FIXTURES / "mismatch" / "board.kicad_pcb")
        result = json.loads(verify_pin_mapping({"fw_path": fw_path, "pcb_path": pcb_path}))
        assert result.get("ok") is False, result

    def test_tool_missing_args(self):
        import json
        from kerf_firmware.tools.verify_pin_mapping import verify_pin_mapping

        result = json.loads(verify_pin_mapping({}))
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_tool_bad_fw_path(self):
        import json
        from kerf_firmware.tools.verify_pin_mapping import verify_pin_mapping

        result = json.loads(verify_pin_mapping({
            "fw_path": "/nonexistent/path/main.ino",
            "pcb_path": str(FIXTURES / "match" / "board.kicad_pcb"),
        }))
        assert result.get("code") == "FW_NOT_FOUND"

    def test_tool_directory_input(self):
        """Passing a directory rather than a single .ino file should work."""
        import json
        from kerf_firmware.tools.verify_pin_mapping import verify_pin_mapping

        fw_dir = str(FIXTURES / "match")
        pcb_path = str(FIXTURES / "match" / "board.kicad_pcb")
        result = json.loads(verify_pin_mapping({"fw_path": fw_dir, "pcb_path": pcb_path}))
        assert result.get("ok") is True, result
