"""
Pytest suite for kerf_electronics.atopile.llm.make_atopile.

Covers:
  voltage_divider
    - output contains 'r1' and 'r2' declarations
    - output is a valid .ato module (has module block + net connections)
    - case-insensitive spec match

  RC low-pass
    - 10 kHz cutoff is embedded in the output as a parameter
    - R×C product ≈ 1/(2π×fc)  (within 1 % tolerance)
    - Capacitor value appears in the output string
    - 1 MHz spec accepted

  LED driver
    - 20 mA current → R = (5-2)/0.02 = 150 Ω  (exact to < 0.01 %)
    - 50 mA current → R = 60 Ω
    - current label appears in output
    - led1 and r1 instantiated

  pull-up resistor
    - 4.7 kΩ → value appears in output
    - default (no value given) → 10 kΩ in output
    - signal net appears

  syntax / round-trip
    - all templates pass the internal _validate_ato check
    - if kerf_electronics.atopile.parser is importable,
      round-trip is clean (skipped otherwise)

  error handling
    - unknown spec raises UnknownSpecError
    - bad frequency string raises ValueError
    - bad current string raises ValueError

Author: imranparuk
"""
from __future__ import annotations

import math
import re
import sys
import os

import pytest

# Ensure src/ is on sys.path when running directly
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_electronics.atopile.llm import (
    UnknownSpecError,
    _fmt_eng,
    _parse_current,
    _parse_frequency,
    _parse_resistance,
    _validate_ato,
    make_atopile,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_value(source: str, component: str) -> str:
    """Return the quoted value string for a component, e.g. r1.value = "10kΩ" → '10kΩ'."""
    m = re.search(rf'{re.escape(component)}\.value\s*=\s*"([^"]+)"', source)
    assert m, f"No value for {component!r} found in:\n{source}"
    return m.group(1)


def _parse_resistance_from_output(value_str: str) -> float:
    """Parse a value string like '150Ω' or '10kΩ' from generated output."""
    return _parse_resistance(value_str)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. voltage divider
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoltageDivider:
    def test_r1_declared(self):
        src = make_atopile("voltage divider")
        assert "r1" in src

    def test_r2_declared(self):
        src = make_atopile("voltage divider")
        assert "r2" in src

    def test_r1_new_resistor(self):
        src = make_atopile("voltage divider")
        assert re.search(r"r1\s*=\s*new\s+Resistor", src)

    def test_r2_new_resistor(self):
        src = make_atopile("voltage divider")
        assert re.search(r"r2\s*=\s*new\s+Resistor", src)

    def test_has_vin_net(self):
        src = make_atopile("voltage divider")
        assert "net vin" in src

    def test_has_vout_net(self):
        src = make_atopile("voltage divider")
        assert "net vout" in src

    def test_has_gnd_net(self):
        src = make_atopile("voltage divider")
        assert "net gnd" in src

    def test_module_block(self):
        src = make_atopile("voltage divider")
        assert re.search(r"module\s+\w+\s*:", src)

    def test_validate_passes(self):
        src = make_atopile("voltage divider")
        _validate_ato(src)  # must not raise

    def test_case_insensitive(self):
        src = make_atopile("Voltage Divider")
        assert "r1" in src
        assert "r2" in src

    def test_default_r1_value_10k(self):
        src = make_atopile("voltage divider")
        r1_val = _extract_value(src, "r1")
        assert "10k" in r1_val.lower() or "10000" in r1_val

    def test_default_r2_value_10k(self):
        src = make_atopile("voltage divider")
        r2_val = _extract_value(src, "r2")
        assert "10k" in r2_val.lower() or "10000" in r2_val


# ═══════════════════════════════════════════════════════════════════════════════
# 2. RC low-pass
# ═══════════════════════════════════════════════════════════════════════════════

class TestRCLowPass:
    def test_10khz_label_in_output(self):
        src = make_atopile("RC low-pass 10kHz")
        assert "10kHz" in src or "10KHz" in src or "10khz" in src.lower()

    def test_r1_declared(self):
        src = make_atopile("RC low-pass 10kHz")
        assert re.search(r"r1\s*=\s*new\s+Resistor", src)

    def test_c1_declared(self):
        src = make_atopile("RC low-pass 10kHz")
        assert re.search(r"c1\s*=\s*new\s+Capacitor", src)

    def test_rc_product_within_1pct_10khz(self):
        """R×C must be within 1 % of 1/(2π×10000)."""
        src = make_atopile("RC low-pass 10kHz")
        fc = 10_000.0
        r_str = _extract_value(src, "r1")
        c_str = _extract_value(src, "c1")
        r_ohm = _parse_resistance(r_str)
        # Parse capacitor value
        c_val = _parse_capacitance(c_str)
        expected_rc = 1.0 / (2.0 * math.pi * fc)
        assert abs(r_ohm * c_val - expected_rc) / expected_rc < 0.01

    def test_1mhz_accepted(self):
        src = make_atopile("RC low-pass 1MHz")
        assert re.search(r"c1\s*=\s*new\s+Capacitor", src)

    def test_validate_passes(self):
        src = make_atopile("RC low-pass 10kHz")
        _validate_ato(src)

    def test_vin_net(self):
        src = make_atopile("RC low-pass 10kHz")
        assert "net vin" in src

    def test_vout_net(self):
        src = make_atopile("RC low-pass 10kHz")
        assert "net vout" in src

    def test_gnd_net(self):
        src = make_atopile("RC low-pass 10kHz")
        assert "net gnd" in src


# ═══════════════════════════════════════════════════════════════════════════════
# 3. LED driver
# ═══════════════════════════════════════════════════════════════════════════════

class TestLEDDriver:
    def test_20ma_resistor_150_ohm(self):
        """R = (5V - 2V) / 0.02A = 150 Ω."""
        src = make_atopile("LED driver 20mA")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 150.0) / 150.0 < 1e-4

    def test_50ma_resistor_60_ohm(self):
        """R = (5V - 2V) / 0.05A = 60 Ω."""
        src = make_atopile("LED driver 50mA")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 60.0) / 60.0 < 1e-4

    def test_current_label_in_output(self):
        src = make_atopile("LED driver 20mA")
        assert "20mA" in src or "20ma" in src.lower()

    def test_r1_new_resistor(self):
        src = make_atopile("LED driver 20mA")
        assert re.search(r"r1\s*=\s*new\s+Resistor", src)

    def test_led1_new_led(self):
        src = make_atopile("LED driver 20mA")
        assert re.search(r"led1\s*=\s*new\s+LED", src)

    def test_validate_passes(self):
        src = make_atopile("LED driver 20mA")
        _validate_ato(src)

    def test_vcc_net(self):
        src = make_atopile("LED driver 20mA")
        assert "net vcc" in src

    def test_gnd_net(self):
        src = make_atopile("LED driver 20mA")
        assert "net gnd" in src

    def test_10ma_resistor_300_ohm(self):
        """R = (5V - 2V) / 0.01A = 300 Ω."""
        src = make_atopile("LED driver 10mA")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 300.0) / 300.0 < 1e-4


# ═══════════════════════════════════════════════════════════════════════════════
# 4. pull-up resistor
# ═══════════════════════════════════════════════════════════════════════════════

class TestPullUp:
    def test_4k7_value_in_output(self):
        src = make_atopile("pull-up resistor 4.7kΩ")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 4700.0) / 4700.0 < 1e-4

    def test_default_10k_when_no_value(self):
        src = make_atopile("pull-up resistor")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 10_000.0) / 10_000.0 < 1e-4

    def test_signal_net(self):
        src = make_atopile("pull-up resistor 10kΩ")
        assert "net signal" in src

    def test_vcc_net(self):
        src = make_atopile("pull-up resistor 10kΩ")
        assert "net vcc" in src

    def test_r1_new_resistor(self):
        src = make_atopile("pull-up resistor 4.7kΩ")
        assert re.search(r"r1\s*=\s*new\s+Resistor", src)

    def test_validate_passes(self):
        src = make_atopile("pull-up resistor 10kΩ")
        _validate_ato(src)

    def test_space_variant(self):
        """'pull up resistor' (no hyphen) should also work."""
        src = make_atopile("pull up resistor 1kΩ")
        assert re.search(r"r1\s*=\s*new\s+Resistor", src)

    def test_100k_value(self):
        src = make_atopile("pull-up resistor 100kΩ")
        r_str = _extract_value(src, "r1")
        r_ohm = _parse_resistance(r_str)
        assert abs(r_ohm - 100_000.0) / 100_000.0 < 1e-4


# ═══════════════════════════════════════════════════════════════════════════════
# 5. round-trip via parser (conditional)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoundTrip:
    """
    These tests only run if kerf_electronics.atopile.parser is importable
    (i.e. T-194 has landed).  Otherwise the test is skipped.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_parser(self):
        pytest.importorskip("kerf_electronics.atopile.parser")

    def test_voltage_divider_round_trip(self):
        from kerf_electronics.atopile.parser import parse
        src = make_atopile("voltage divider")
        parse(src)  # must not raise

    def test_rc_lowpass_round_trip(self):
        from kerf_electronics.atopile.parser import parse
        src = make_atopile("RC low-pass 10kHz")
        parse(src)

    def test_led_driver_round_trip(self):
        from kerf_electronics.atopile.parser import parse
        src = make_atopile("LED driver 20mA")
        parse(src)

    def test_pullup_round_trip(self):
        from kerf_electronics.atopile.parser import parse
        src = make_atopile("pull-up resistor 10kΩ")
        parse(src)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_unknown_spec_raises(self):
        with pytest.raises(UnknownSpecError):
            make_atopile("mystery circuit")

    def test_empty_spec_raises(self):
        with pytest.raises((UnknownSpecError, ValueError)):
            make_atopile("")

    def test_bad_frequency_raises(self):
        with pytest.raises(ValueError):
            make_atopile("RC low-pass NotAFrequency!!!")

    def test_bad_current_raises(self):
        with pytest.raises(ValueError):
            make_atopile("LED driver XmA")

    def test_unknown_spec_message_contains_supported(self):
        try:
            make_atopile("unknown circuit")
        except UnknownSpecError as exc:
            assert "voltage divider" in str(exc).lower() or "Supported" in str(exc)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SI-suffix parser unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSIParser:
    def test_parse_frequency_hz(self):
        assert _parse_frequency("1000Hz") == pytest.approx(1000.0)

    def test_parse_frequency_khz(self):
        assert _parse_frequency("10kHz") == pytest.approx(10_000.0)

    def test_parse_frequency_mhz(self):
        assert _parse_frequency("2.4MHz") == pytest.approx(2.4e6)

    def test_parse_frequency_no_suffix_is_hz(self):
        assert _parse_frequency("500") == pytest.approx(500.0)

    def test_parse_resistance_ohm(self):
        assert _parse_resistance("150Ω") == pytest.approx(150.0)

    def test_parse_resistance_kohm(self):
        assert _parse_resistance("10kΩ") == pytest.approx(10_000.0)

    def test_parse_resistance_mohm(self):
        assert _parse_resistance("1Mohm") == pytest.approx(1e6)

    def test_parse_current_ma(self):
        assert _parse_current("20mA") == pytest.approx(0.02)

    def test_parse_current_a(self):
        assert _parse_current("0.35A") == pytest.approx(0.35)

    def test_fmt_eng_kohm(self):
        assert _fmt_eng(10_000.0, "Ω") == "10kΩ"

    def test_fmt_eng_nf(self):
        result = _fmt_eng(1.592e-9, "F")
        assert "n" in result and "F" in result


# ── Capacitance value parser (for internal test use) ─────────────────────────

_CAP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(nF|uF|pF|F)?$",
    re.IGNORECASE,
)


def _parse_capacitance(token: str) -> float:
    """Parse a capacitance string like '15.9nF', '100pF', '1uF' → Farads."""
    m = _CAP_RE.match(token.strip())
    if not m:
        raise ValueError(f"Cannot parse capacitance: {token!r}")
    value = float(m.group(1))
    suffix = (m.group(2) or "F").lower()
    if suffix == "nf":
        value *= 1e-9
    elif suffix == "uf":
        value *= 1e-6
    elif suffix == "pf":
        value *= 1e-12
    return value
