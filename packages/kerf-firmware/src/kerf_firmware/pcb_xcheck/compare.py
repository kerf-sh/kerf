"""compare.py — cross-check firmware pin assignments against the PCB netlist.

Takes the outputs of pcb_pins.parse_kicad_pcb_pins() and
fw_pins.extract_fw_pins() and produces a structured mismatch report.

Checks performed
----------------
1. missing_pins   — firmware uses a pin that does not exist in the PCB's MCU
                    footprint (e.g. fw uses GPIO21 / pin 7 but the board only
                    exposes pins 1-6 and 8-14).

2. wrong_load     — firmware drives a pin as OUTPUT but the PCB routes it to
                    an INPUT_ONLY net (hardware constraint violated).

3. bus_incomplete — I2C bus consistency: if firmware sets i2c_sda OR i2c_scl,
                    both must be present; if either is wired but the other is
                    missing from the PCB, flag the incomplete bus.

4. pin_mismatch   — firmware uses a pin that exists on the PCB but whose net
                    does not match the expected signal (e.g. fw uses pin 21 for
                    SDA but PCB routes SDA to pin 22).

Public API
----------
compare(pcb_pins, fw_map, *, mcu_ref=None) -> XcheckReport

XcheckReport.ok          True iff all check lists are empty.
XcheckReport.missing_pins        list[str]
XcheckReport.wrong_load          list[tuple[str, str]]   (pin, reason)
XcheckReport.bus_incomplete      list[str]                (bus descriptor)
XcheckReport.pin_mismatch        list[PinMismatch]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .pcb_pins import PcbPin
from .fw_pins import FwPinMap


@dataclass
class PinMismatch:
    """Describes a pin whose net on the PCB does not match fw intent."""
    pin: str
    fw_context: str          # e.g. "Wire.begin.SDA"
    fw_expected_signal: str  # e.g. "SDA"
    pcb_net: str             # actual net name on the PCB
    note: str = ""


@dataclass
class XcheckReport:
    """Result of a full PCB ↔ firmware cross-check."""
    ok: bool = True
    missing_pins: list[str] = field(default_factory=list)
    wrong_load: list[tuple[str, str]] = field(default_factory=list)
    bus_incomplete: list[str] = field(default_factory=list)
    pin_mismatch: list[PinMismatch] = field(default_factory=list)

    def _recompute_ok(self) -> None:
        self.ok = (
            not self.missing_pins
            and not self.wrong_load
            and not self.bus_incomplete
            and not self.pin_mismatch
        )

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "missing_pins": list(self.missing_pins),
            "wrong_load": [list(t) for t in self.wrong_load],
            "bus_incomplete": list(self.bus_incomplete),
            "pin_mismatch": [
                {
                    "pin": m.pin,
                    "fw_context": m.fw_context,
                    "fw_expected_signal": m.fw_expected_signal,
                    "pcb_net": m.pcb_net,
                    "note": m.note,
                }
                for m in self.pin_mismatch
            ],
        }


def _net_contains_signal(net_name: str, signal: str) -> bool:
    """True if *net_name* contains *signal* as a word-boundary substring."""
    return bool(re.search(rf'\b{re.escape(signal)}\b', net_name, re.IGNORECASE))


def _bus_net_has_signal(pcb_pins: dict[str, PcbPin], pin: str, signal: str) -> bool:
    """True if the PCB pad *pin* has a net carrying *signal*."""
    entry = pcb_pins.get(pin)
    if entry is None:
        return False
    return _net_contains_signal(entry.net, signal)


def compare(
    pcb_pins: dict[str, PcbPin],
    fw_map: FwPinMap,
    *,
    mcu_ref: Optional[str] = None,
) -> XcheckReport:
    """Cross-check *fw_map* against *pcb_pins* and return an XcheckReport.

    Parameters
    ----------
    pcb_pins:
        dict[pad_number_str → PcbPin] from parse_kicad_pcb_pins().
    fw_map:
        FwPinMap from extract_fw_pins().
    mcu_ref:
        Informational only (used in note strings).

    Returns
    -------
    XcheckReport with ok / missing_pins / wrong_load / bus_incomplete /
    pin_mismatch populated.
    """
    report = XcheckReport()

    # ── Check 1: missing pins ─────────────────────────────────────────────────
    for pin in fw_map.all_pins:
        if pin not in pcb_pins:
            report.missing_pins.append(pin)

    # ── Check 2: wrong_load (OUTPUT driving an INPUT_ONLY net) ───────────────
    for pin, mode in fw_map.pin_modes.items():
        if mode == "OUTPUT" and pin in pcb_pins:
            pcb_entry = pcb_pins[pin]
            if pcb_entry.direction == "input_only":
                report.wrong_load.append(
                    (pin, f"input-only net ({pcb_entry.net!r})")
                )

    # ── Check 3: bus completeness (I2C) ──────────────────────────────────────
    sda_pin = fw_map.i2c_sda
    scl_pin = fw_map.i2c_scl

    # Check if either I2C pin is declared but the other is absent from PCB or fw
    if sda_pin is not None or scl_pin is not None:
        # We expect both to be declared in fw sources
        if sda_pin is None:
            report.bus_incomplete.append(
                "I2C: SCL declared (pin {}) but SDA missing from firmware".format(scl_pin)
            )
        elif scl_pin is None:
            report.bus_incomplete.append(
                "I2C: SDA declared (pin {}) but SCL missing from firmware".format(sda_pin)
            )
        else:
            # Both declared in FW — check that both exist on PCB
            if sda_pin not in pcb_pins:
                report.bus_incomplete.append(
                    "I2C: SDA pin {} not present in PCB MCU footprint".format(sda_pin)
                )
            if scl_pin not in pcb_pins:
                report.bus_incomplete.append(
                    "I2C: SCL pin {} not present in PCB MCU footprint".format(scl_pin)
                )

            # Check that the PCB nets actually carry SDA / SCL signals
            if sda_pin in pcb_pins and not _net_contains_signal(pcb_pins[sda_pin].net, "SDA"):
                report.pin_mismatch.append(PinMismatch(
                    pin=sda_pin,
                    fw_context="Wire.begin.SDA",
                    fw_expected_signal="SDA",
                    pcb_net=pcb_pins[sda_pin].net,
                    note="PCB net on SDA pin does not carry SDA signal",
                ))
            if scl_pin in pcb_pins and not _net_contains_signal(pcb_pins[scl_pin].net, "SCL"):
                report.pin_mismatch.append(PinMismatch(
                    pin=scl_pin,
                    fw_context="Wire.begin.SCL",
                    fw_expected_signal="SCL",
                    pcb_net=pcb_pins[scl_pin].net,
                    note="PCB net on SCL pin does not carry SCL signal",
                ))

    # ── Finalise ok flag ──────────────────────────────────────────────────────
    report._recompute_ok()
    return report
