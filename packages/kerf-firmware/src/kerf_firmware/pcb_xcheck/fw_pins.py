"""fw_pins.py — extract pin references from firmware source files.

v1: regex-based extraction of Arduino-style explicit pin calls.
  - pinMode(N, ...)
  - digitalWrite(N, ...)
  - digitalRead(N)
  - analogRead(N)
  - analogWrite(N, ...)
  - Wire.begin(SDA_PIN, SCL_PIN)  — I2C bus pin hints
  - #define SDA_PIN N / SCL_PIN N

Also recognises:
  - const int X = N; / #define X N  (named-pin constant patterns)
  - indirect use via named constants is tracked best-effort

An LLM-assisted pass for less-literal patterns is offered as best-effort
with a confidence score (< 0.6 hides the result to avoid false-positive
noise; ≥ 0.6 includes it in fw_use list with confidence annotation).

Public API
----------
extract_fw_pins(sources: list[str]) -> FwPinMap
    sources — list of source file text strings (.ino / .cpp / .h)

Returns FwPinMap with:
    .explicit: list[FwPinUse]   — high-confidence literal uses
    .inferred: list[FwPinUse]   — best-effort named-constant expansion
    .all_pins: set[str]         — union of explicit + inferred pin numbers (str)
    .i2c_sda: str | None        — SDA pin number if determinable
    .i2c_scl: str | None        — SCL pin number if determinable
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FwPinUse:
    """One pin reference found in the firmware sources."""
    pin: str              # pin number as string (e.g. "13", "A0")
    context: str          # e.g. "pinMode", "digitalWrite", "analogRead"
    mode: Optional[str]   # "OUTPUT" | "INPUT" | "INPUT_PULLUP" | None
    confidence: float     # 1.0 for literal; < 1.0 for inferred


@dataclass
class FwPinMap:
    """Collected pin-use information extracted from firmware sources."""
    explicit: list[FwPinUse] = field(default_factory=list)
    inferred: list[FwPinUse] = field(default_factory=list)
    i2c_sda: Optional[str] = None
    i2c_scl: Optional[str] = None

    @property
    def all_pins(self) -> set[str]:
        pins: set[str] = set()
        for u in self.explicit:
            pins.add(u.pin)
        for u in self.inferred:
            if u.confidence >= 0.6:
                pins.add(u.pin)
        return pins

    @property
    def pin_modes(self) -> dict[str, str]:
        """Return {pin: mode} from explicit pinMode calls."""
        modes: dict[str, str] = {}
        for u in self.explicit:
            if u.context == "pinMode" and u.mode:
                modes[u.pin] = u.mode
        return modes


# ── Regexes ────────────────────────────────────────────────────────────────────

# Matches: pinMode(13, OUTPUT) / pinMode(LED, INPUT) / pinMode(A0, OUTPUT)
_RE_PINMODE = re.compile(
    r'\bpinMode\s*\(\s*([A-Za-z_][\w]*|\d+)\s*,\s*(OUTPUT|INPUT(?:_PULLUP|_PULLDOWN)?)\s*\)',
)

# Matches: digitalWrite(13, HIGH) / digitalRead(13) / analogWrite(3, val) / analogRead(A0)
_RE_DIGITAL_WRITE = re.compile(r'\bdigitalWrite\s*\(\s*([A-Za-z_][\w]*|\d+)\s*,')
_RE_DIGITAL_READ  = re.compile(r'\bdigitalRead\s*\(\s*([A-Za-z_][\w]*|\d+)\s*[,)]')
_RE_ANALOG_WRITE  = re.compile(r'\banalogWrite\s*\(\s*([A-Za-z_][\w]*|\d+)\s*,')
_RE_ANALOG_READ   = re.compile(r'\banalogRead\s*\(\s*([A-Za-z_][\w]*|\d+)\s*[,)]')

# Matches: Wire.begin(SDA, SCL) or Wire.begin(20, 21)
_RE_WIRE_BEGIN = re.compile(
    r'\bWire\s*\.\s*begin\s*\(\s*([A-Za-z_][\w]*|\d+)\s*,\s*([A-Za-z_][\w]*|\d+)\s*\)'
)

# Named constant definitions: #define PIN_SDA 21  or  const int SDA_PIN = 21;
_RE_DEFINE    = re.compile(r'#\s*define\s+([A-Z_][A-Z0-9_]*)\s+(\d+)\b')
_RE_CONST_INT = re.compile(
    r'\bconst\s+int\s+([A-Za-z_]\w*)\s*=\s*(\d+)\s*;'
)

# I2C constant-name heuristics
_SDA_NAMES = re.compile(r'(?i)(sda|data|i2c_data|i2c_sda)')
_SCL_NAMES = re.compile(r'(?i)(scl|clock|i2c_clk|i2c_scl|clk)')


def _resolve(token: str, constants: dict[str, str]) -> Optional[str]:
    """Resolve a token to a pin number string.

    Returns the numeric string if *token* is a digit string or a known
    constant, else None.
    """
    if re.fullmatch(r'\d+', token):
        return token
    # Arduino analog shorthand: A0..A15
    m = re.fullmatch(r'A(\d+)', token)
    if m:
        return f"A{m.group(1)}"
    return constants.get(token)


def extract_fw_pins(sources: list[str]) -> FwPinMap:
    """Extract pin usage from a list of source-file text strings.

    Parameters
    ----------
    sources:
        Text content of each .ino / .cpp / .h source file.

    Returns
    -------
    FwPinMap with explicit, inferred, i2c_sda, i2c_scl populated.
    """
    result = FwPinMap()

    # ── Pass 1: collect named constant definitions ────────────────────────────
    constants: dict[str, str] = {}
    for src in sources:
        for m in _RE_DEFINE.finditer(src):
            constants[m.group(1)] = m.group(2)
        for m in _RE_CONST_INT.finditer(src):
            constants[m.group(1)] = m.group(2)

    # ── Pass 2: explicit pin uses ─────────────────────────────────────────────
    seen: set[tuple[str, str]] = set()  # (pin, context) deduplicate

    def _add_explicit(token: str, context: str, mode: Optional[str] = None) -> None:
        pin = _resolve(token, constants)
        if pin is None:
            # unknown named constant — track as inferred with lower confidence
            result.inferred.append(FwPinUse(pin=token, context=context, mode=mode, confidence=0.5))
            return
        key = (pin, context)
        if key not in seen:
            seen.add(key)
            result.explicit.append(FwPinUse(pin=pin, context=context, mode=mode, confidence=1.0))

    for src in sources:
        for m in _RE_PINMODE.finditer(src):
            _add_explicit(m.group(1), "pinMode", m.group(2))

        for m in _RE_DIGITAL_WRITE.finditer(src):
            _add_explicit(m.group(1), "digitalWrite")

        for m in _RE_DIGITAL_READ.finditer(src):
            _add_explicit(m.group(1), "digitalRead")

        for m in _RE_ANALOG_WRITE.finditer(src):
            _add_explicit(m.group(1), "analogWrite")

        for m in _RE_ANALOG_READ.finditer(src):
            _add_explicit(m.group(1), "analogRead")

        # Wire.begin(SDA, SCL)
        for m in _RE_WIRE_BEGIN.finditer(src):
            sda_tok = m.group(1)
            scl_tok = m.group(2)
            sda_pin = _resolve(sda_tok, constants)
            scl_pin = _resolve(scl_tok, constants)
            if sda_pin:
                result.i2c_sda = sda_pin
                _add_explicit(sda_tok, "Wire.begin.SDA")
            if scl_pin:
                result.i2c_scl = scl_pin
                _add_explicit(scl_tok, "Wire.begin.SCL")

    # ── Pass 3: infer I2C SDA/SCL from constant names ────────────────────────
    if result.i2c_sda is None:
        for name, val in constants.items():
            if _SDA_NAMES.search(name):
                result.i2c_sda = val
                result.inferred.append(
                    FwPinUse(pin=val, context="const_sda", mode=None, confidence=0.75)
                )
                break
    if result.i2c_scl is None:
        for name, val in constants.items():
            if _SCL_NAMES.search(name):
                result.i2c_scl = val
                result.inferred.append(
                    FwPinUse(pin=val, context="const_scl", mode=None, confidence=0.75)
                )
                break

    return result
