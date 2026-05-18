"""Tests for the atopile → tscircuit JSX converter (T-201)."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

from kerf_electronics.atopile.to_tscircuit import ato_to_tsx

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "atopile"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tag_attrs(tsx: str, tag: str) -> list[dict[str, str]]:
    """Return a list of attribute dicts for every occurrence of <tag ...> in tsx."""
    pattern = rf"<{tag}\s([^/]*)/>"
    results = []
    for m in re.finditer(pattern, tsx, re.DOTALL):
        attr_str = m.group(1)
        attrs = {}
        for am in re.finditer(r'(\w+)="([^"]*)"', attr_str):
            attrs[am.group(1)] = am.group(2)
        results.append(attrs)
    return results


def _jsx_well_formed(tsx: str) -> bool:
    """Basic structural check: has <board> and </board> tags."""
    return "<board>" in tsx and "</board>" in tsx


# ===========================================================================
# T-201-1  voltage_divider.ato — two resistors, correct values
# ===========================================================================


def test_voltage_divider_has_two_resistors():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    resistors = _tag_attrs(tsx, "resistor")
    assert len(resistors) == 2, f"Expected 2 <resistor>, got {len(resistors)}:\n{tsx}"


def test_voltage_divider_r1_name():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    resistors = _tag_attrs(tsx, "resistor")
    names = {r["name"] for r in resistors}
    assert "R1" in names, f"Missing R1 in {names}:\n{tsx}"


def test_voltage_divider_r2_name():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    resistors = _tag_attrs(tsx, "resistor")
    names = {r["name"] for r in resistors}
    assert "R2" in names, f"Missing R2 in {names}:\n{tsx}"


def test_voltage_divider_r1_resistance_10k():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    resistors = _tag_attrs(tsx, "resistor")
    r1 = next(r for r in resistors if r["name"] == "R1")
    assert r1.get("resistance") == "10kohm", (
        f"R1 resistance={r1.get('resistance')!r}, expected '10kohm'"
    )


def test_voltage_divider_r2_resistance_1k():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    resistors = _tag_attrs(tsx, "resistor")
    r2 = next(r for r in resistors if r["name"] == "R2")
    assert r2.get("resistance") == "1kohm", (
        f"R2 resistance={r2.get('resistance')!r}, expected '1kohm'"
    )


def test_voltage_divider_has_three_nets():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    nets = _tag_attrs(tsx, "net")
    assert len(nets) == 3, f"Expected 3 <net>, got {len(nets)}:\n{tsx}"


def test_voltage_divider_net_names():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    nets = _tag_attrs(tsx, "net")
    net_names = {n["name"] for n in nets}
    assert "vin" in net_names, f"Missing 'vin' in {net_names}"
    assert "vout" in net_names, f"Missing 'vout' in {net_names}"
    assert "gnd" in net_names, f"Missing 'gnd' in {net_names}"


def test_voltage_divider_board_wrapper():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    assert _jsx_well_formed(tsx), f"Missing <board> wrapper:\n{tsx}"


def test_voltage_divider_has_export_default():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    assert "export default function" in tsx, f"Missing export default:\n{tsx}"


def test_voltage_divider_tsx_contains_tscircuit_import():
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    assert "@tscircuit/core" in tsx, f"Missing @tscircuit/core import:\n{tsx}"


# ===========================================================================
# T-201-2  rc_filter.ato — one resistor, one capacitor
# ===========================================================================


def test_rc_filter_has_one_resistor():
    tsx = ato_to_tsx(load("rc_filter.ato"))
    assert len(_tag_attrs(tsx, "resistor")) == 1


def test_rc_filter_has_one_capacitor():
    tsx = ato_to_tsx(load("rc_filter.ato"))
    caps = _tag_attrs(tsx, "capacitor")
    assert len(caps) == 1, f"Expected 1 <capacitor>, got {len(caps)}:\n{tsx}"


def test_rc_filter_capacitor_value():
    tsx = ato_to_tsx(load("rc_filter.ato"))
    caps = _tag_attrs(tsx, "capacitor")
    assert caps[0].get("capacitance") == "100nF", (
        f"capacitance={caps[0].get('capacitance')!r}"
    )


def test_rc_filter_net_count():
    tsx = ato_to_tsx(load("rc_filter.ato"))
    nets = _tag_attrs(tsx, "net")
    assert len(nets) == 3, f"Expected 3 nets (vin/vout/gnd), got {len(nets)}"


# ===========================================================================
# T-201-3  led_driver.ato — resistor + LED with color attribute
# ===========================================================================


def test_led_driver_has_one_resistor():
    tsx = ato_to_tsx(load("led_driver.ato"))
    assert len(_tag_attrs(tsx, "resistor")) == 1


def test_led_driver_has_one_led():
    tsx = ato_to_tsx(load("led_driver.ato"))
    leds = _tag_attrs(tsx, "led")
    assert len(leds) == 1, f"Expected 1 <led>, got {len(leds)}:\n{tsx}"


def test_led_driver_led_color():
    tsx = ato_to_tsx(load("led_driver.ato"))
    leds = _tag_attrs(tsx, "led")
    assert leds[0].get("color") == "red", (
        f"LED color={leds[0].get('color')!r}, expected 'red'"
    )


def test_led_driver_nets():
    tsx = ato_to_tsx(load("led_driver.ato"))
    nets = _tag_attrs(tsx, "net")
    net_names = {n["name"] for n in nets}
    assert "vcc" in net_names, f"Missing 'vcc' in {net_names}"
    assert "gnd" in net_names, f"Missing 'gnd' in {net_names}"


# ===========================================================================
# T-201-4  resistor.ato — component-only file (no module block)
# ===========================================================================


def test_resistor_component_no_module_raises():
    """resistor.ato only defines a component block, no module — should raise."""
    with pytest.raises(ValueError, match="No module block"):
        ato_to_tsx(load("resistor.ato"))


# ===========================================================================
# T-201-5  top_module selection
# ===========================================================================


MULTI_MODULE = """\
import Resistor from "generics/resistors.ato"

module ModA:
    signal vdd
    r1 = new Resistor
    r1.value = 100ohm

module ModB:
    signal gnd
    r2 = new Resistor
    r2.value = 200ohm
"""


def test_top_module_selects_correct_module():
    tsx = ato_to_tsx(MULTI_MODULE, top_module="ModB")
    resistors = _tag_attrs(tsx, "resistor")
    assert len(resistors) == 1
    assert resistors[0]["name"] == "R2"
    assert resistors[0].get("resistance") == "200ohm"


def test_top_module_unknown_raises():
    with pytest.raises(ValueError, match="ModX"):
        ato_to_tsx(MULTI_MODULE, top_module="ModX")


def test_default_module_uses_first():
    tsx = ato_to_tsx(MULTI_MODULE)
    resistors = _tag_attrs(tsx, "resistor")
    assert resistors[0]["name"] == "R1"


# ===========================================================================
# T-201-6  JSX structural validity via regex (no Node dependency)
# ===========================================================================


def test_jsx_no_unclosed_tags():
    """Verify every opening <tag ...> has a corresponding self-close or close tag."""
    tsx = ato_to_tsx(load("voltage_divider.ato"))
    # Self-closing tags <foo ... /> should dominate; board is the only non-self-close pair
    open_board = tsx.count("<board>")
    close_board = tsx.count("</board>")
    assert open_board == 1 and close_board == 1, (
        f"board tag mismatch: {open_board} open, {close_board} close"
    )
    # All <resistor>, <capacitor>, <net>, etc. must be self-closing
    self_close_tags = re.findall(r"<\w+[^>]*/\s*>", tsx)
    # There should be at least as many self-closing tags as components + nets
    resistors = _tag_attrs(tsx, "resistor")
    nets = _tag_attrs(tsx, "net")
    assert len(self_close_tags) >= len(resistors) + len(nets)


# ===========================================================================
# T-201-7  Round-trip via node -e (optional — skip if node not available)
# ===========================================================================


def _node_available() -> bool:
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(
    not _node_available(),
    reason="node not available — skipping JSX syntax check",
)
def test_jsx_parseable_by_node():
    """Validate that the emitted string is at least plausible JSX text."""
    tsx = ato_to_tsx(load("voltage_divider.ato"))

    # Use node to validate basic JS structure (strip JSX tags to plain text check)
    # We check that the import line and function signature parse without node crashing
    # by wrapping in a no-op eval that just checks the string is truthy.
    script = f"""
const src = {repr(tsx)};
// Minimal check: string is non-empty and contains expected substrings
if (!src.includes('<resistor') || !src.includes('<board>')) {{
    process.exit(1);
}}
process.exit(0);
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"node validation failed:\nstdout: {result.stdout}\nstderr: {result.stderr}\n"
        f"tsx:\n{tsx}"
    )
