"""
Deterministic template-based .ato synthesizer.

Converts a short English spec string into a syntactically-correct
atopile (.ato) source snippet.  No external LLM is called here; this
module IS the template engine that an application-level LLM would call
as a tool.

Supported patterns
------------------
"voltage divider"
    Two-resistor voltage divider: vin → r1 → vout → r2 → gnd.
    Default values: r1=10kΩ, r2=10kΩ.

"RC low-pass <frequency>"
    RC low-pass filter with the cutoff embedded as a parameter comment.
    Frequency accepted with SI suffix: Hz / kHz / MHz.
    Component values are sized to R×C ≈ 1 / (2π × fc).
    Default R = 10 kΩ; C is derived.

"LED driver <current>"
    LED series-resistor circuit.  Current accepted with SI suffix:
    mA / A.  Resistor sized by Ohm's law:
        R = (Vcc - Vled) / I_led
    where Vcc = 5 V, Vled = 2 V (typical red LED forward voltage).

"pull-up resistor <value>"
    Single pull-up resistor between a signal net and VCC.
    Resistance accepted with SI suffix: Ω / kΩ / MΩ.
    Default value 10 kΩ if no explicit value is given.

Validation
----------
Each emitted .ato string passes a minimal regex grammar check
(`_validate_ato`).  When `kerf_electronics.atopile.parser` is
importable, the output is also passed through its `parse()` function.

Author: imranparuk
"""
from __future__ import annotations

import math
import re
from typing import Optional


# ── SI-suffix parsers ─────────────────────────────────────────────────────────

_FREQ_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(MHz|kHz|Hz)?$",
    re.IGNORECASE,
)

_RES_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(MΩ|Mohm|Mohms|kohm|kohms|kΩ|Ω|ohm|ohms)?$",
    re.IGNORECASE,
)

_CURR_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mA|A)?$",
    re.IGNORECASE,
)


def _parse_frequency(token: str) -> float:
    """Return frequency in Hz from a string like '10kHz', '100', '2.4MHz'."""
    m = _FREQ_RE.match(token.strip())
    if not m:
        raise ValueError(f"Cannot parse frequency: {token!r}")
    value = float(m.group(1))
    suffix = (m.group(2) or "Hz").lower()
    if suffix == "mhz":
        value *= 1e6
    elif suffix == "khz":
        value *= 1e3
    return value


def _parse_resistance(token: str) -> float:
    """Return resistance in Ohms from a string like '10k', '4.7kΩ', '100ohm'."""
    m = _RES_RE.match(token.strip())
    if not m:
        raise ValueError(f"Cannot parse resistance: {token!r}")
    value = float(m.group(1))
    # Normalise: lower-case + strip whitespace + replace Ω variants with 'ohm'
    raw = (m.group(2) or "").strip()
    # Replace unicode ohm symbols before lowercasing for comparison
    raw_norm = raw.lower().replace("ω", "ohm").replace("Ω".lower(), "ohm")
    if raw_norm in ("mohm", "mohms", "mmohm"):
        value *= 1e6
    elif raw_norm in ("kohm", "kohms"):
        value *= 1e3
    return value


def _parse_current(token: str) -> float:
    """Return current in Amperes from a string like '20mA', '0.02A', '50'."""
    m = _CURR_RE.match(token.strip())
    if not m:
        raise ValueError(f"Cannot parse current: {token!r}")
    value = float(m.group(1))
    suffix = (m.group(2) or "A").lower()
    if suffix == "ma":
        value *= 1e-3
    return value


# ── Engineering-value formatter ───────────────────────────────────────────────

def _fmt_eng(value: float, unit: str) -> str:
    """Format a value with an SI prefix, e.g. 10000 Ω → '10kΩ'."""
    if value >= 1e6:
        return f"{value / 1e6:.4g}M{unit}"
    if value >= 1e3:
        return f"{value / 1e3:.4g}k{unit}"
    if value < 1e-6:
        return f"{value * 1e9:.4g}n{unit}"
    if value < 1e-3:
        return f"{value * 1e6:.4g}u{unit}"
    if value < 1:
        return f"{value * 1e3:.4g}m{unit}"
    return f"{value:.4g}{unit}"


# ── Minimal .ato syntax validator ─────────────────────────────────────────────

# A .ato file (subset used here) looks like:
#
#   component Foo:
#       signal pin1
#       ...
#
#   module Bar:
#       r1 = new Resistor
#       r1.value = "10kΩ"
#       r1.footprint = "..."
#       net vin ~ r1.p1
#       ...
#
# We validate that:
#   1. There is at least one `module` or `component` block.
#   2. All `new` assignments follow `<ident> = new <Type>`.
#   3. Attribute assignments follow `<ident>.<attr> = "..."`.
#   4. Net connections follow `net <name> ~ <ref>.<pin>`.

_ATO_MODULE_RE = re.compile(r"^\s*(module|component)\s+\w+\s*:", re.MULTILINE)
_ATO_NEW_RE = re.compile(r"^\s*\w+\s*=\s*new\s+\w+", re.MULTILINE)
_ATO_ATTR_RE = re.compile(r'^\s*\w+\.\w+\s*=\s*"[^"]*"', re.MULTILINE)
_ATO_NET_RE = re.compile(r"^\s*net\s+\w+\s*~\s*\w+\.\w+", re.MULTILINE)


def _validate_ato(source: str) -> None:
    """
    Raise ValueError if `source` fails the minimal .ato syntax check.

    When kerf_electronics.atopile.parser is available, also run its
    parse() function.
    """
    if not _ATO_MODULE_RE.search(source):
        raise ValueError("Generated .ato has no module/component block")
    if not _ATO_NEW_RE.search(source):
        raise ValueError("Generated .ato has no `new` component instantiation")
    if not _ATO_ATTR_RE.search(source):
        raise ValueError("Generated .ato has no attribute assignment")
    if not _ATO_NET_RE.search(source):
        raise ValueError("Generated .ato has no net connection")

    # Optional round-trip via the real parser (T-194 sibling)
    try:
        from kerf_electronics.atopile.parser import parse as _ato_parse  # type: ignore
        _ato_parse(source)
    except ImportError:
        pass  # parser not yet present; regex validation is sufficient


# ── Template builders ─────────────────────────────────────────────────────────

def _voltage_divider() -> str:
    return '''\
# Voltage divider: vin → r1 → vout → r2 → gnd
module VoltageDivider:
    r1 = new Resistor
    r1.value = "10kΩ"
    r1.footprint = "R_0402"

    r2 = new Resistor
    r2.value = "10kΩ"
    r2.footprint = "R_0402"

    net vin ~ r1.p1
    net vout ~ r1.p2
    net vout ~ r2.p1
    net gnd ~ r2.p2
'''


def _rc_lowpass(fc_hz: float, label: str) -> str:
    # Size: R = 10kΩ, C = 1/(2π × fc × R)
    r_ohm = 10_000.0
    c_f = 1.0 / (2.0 * math.pi * fc_hz * r_ohm)
    r_str = _fmt_eng(r_ohm, "Ω")
    c_str = _fmt_eng(c_f, "F")
    return f'''\
# RC low-pass filter  fc = {label}  (R={r_str}, C={c_str})
module RCLowPass:
    # cutoff_frequency = "{label}"

    r1 = new Resistor
    r1.value = "{r_str}"
    r1.footprint = "R_0402"

    c1 = new Capacitor
    c1.value = "{c_str}"
    c1.footprint = "C_0402"

    net vin ~ r1.p1
    net vout ~ r1.p2
    net vout ~ c1.p1
    net gnd ~ c1.p2
'''


def _led_driver(i_led_a: float, label: str) -> str:
    # Ohm's law: R = (Vcc - Vled) / I_led  (Vcc=5V, Vled=2V)
    vcc = 5.0
    vled = 2.0
    r_ohm = (vcc - vled) / i_led_a
    r_str = _fmt_eng(r_ohm, "Ω")
    return f'''\
# LED driver  I_led = {label}  R_limit = {r_str}  (Vcc=5V, Vled=2V)
# R = (5V - 2V) / {label} = {r_str}
module LEDDriver:
    # led_current = "{label}"

    r1 = new Resistor
    r1.value = "{r_str}"
    r1.footprint = "R_0402"

    led1 = new LED
    led1.value = "LED_RED"
    led1.footprint = "LED_0603"

    net vcc ~ r1.p1
    net r1.p2 ~ led1.anode
    net gnd ~ led1.cathode
'''


def _pullup(r_ohm: float, label: str) -> str:
    r_str = _fmt_eng(r_ohm, "Ω")
    return f'''\
# Pull-up resistor  {label}  between signal and VCC
module PullUp:
    r1 = new Resistor
    r1.value = "{r_str}"
    r1.footprint = "R_0402"

    net vcc ~ r1.p1
    net signal ~ r1.p2
'''


# ── Public API ────────────────────────────────────────────────────────────────

class UnknownSpecError(ValueError):
    """Raised when the spec string does not match any known pattern."""


def make_atopile(spec: str) -> str:
    """
    Generate a syntactically-valid .ato source snippet from a short
    English *spec* string.

    Parameters
    ----------
    spec : str
        A natural-language description of the circuit pattern.
        Supported patterns:

        - ``"voltage divider"``
        - ``"RC low-pass <freq>"``  (e.g. ``"RC low-pass 10kHz"``)
        - ``"LED driver <current>"``  (e.g. ``"LED driver 20mA"``)
        - ``"pull-up resistor <value>"``  (e.g. ``"pull-up resistor 4.7kΩ"``)

    Returns
    -------
    str
        Complete .ato module source.

    Raises
    ------
    UnknownSpecError
        If the spec does not match any known pattern.
    ValueError
        If a numeric argument in the spec cannot be parsed.
    """
    normalized = spec.strip().lower()

    # ── Voltage divider ───────────────────────────────────────────────────────
    if re.match(r"^voltage\s+divider$", normalized):
        source = _voltage_divider()
        _validate_ato(source)
        return source

    # ── RC low-pass ───────────────────────────────────────────────────────────
    m = re.match(r"^rc\s+low[-\s]?pass\s+(.+)$", normalized)
    if m:
        freq_token = m.group(1).strip()
        # Preserve original capitalisation for the label
        label_token = spec.strip().split()[-1]
        fc_hz = _parse_frequency(freq_token)
        source = _rc_lowpass(fc_hz, label_token)
        _validate_ato(source)
        return source

    # ── LED driver ────────────────────────────────────────────────────────────
    m = re.match(r"^led\s+driver\s+(.+)$", normalized)
    if m:
        curr_token = m.group(1).strip()
        label_token = spec.strip().split()[-1]
        i_led_a = _parse_current(curr_token)
        source = _led_driver(i_led_a, label_token)
        _validate_ato(source)
        return source

    # ── Pull-up resistor ──────────────────────────────────────────────────────
    m = re.match(r"^pull[-\s]?up\s+resistor(?:\s+(.+))?$", normalized)
    if m:
        val_token = (m.group(1) or "").strip()
        if val_token:
            label_token = spec.strip().split()[-1]
            r_ohm = _parse_resistance(val_token)
        else:
            label_token = "10kΩ"
            r_ohm = 10_000.0
        source = _pullup(r_ohm, label_token)
        _validate_ato(source)
        return source

    raise UnknownSpecError(
        f"No template found for spec {spec!r}.  "
        "Supported: 'voltage divider', 'RC low-pass <freq>', "
        "'LED driver <current>', 'pull-up resistor <value>'."
    )
