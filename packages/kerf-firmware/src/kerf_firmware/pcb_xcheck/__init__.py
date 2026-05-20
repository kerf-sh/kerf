"""kerf_firmware.pcb_xcheck — pin-mapping verification between firmware and PCB.

Cross-checks that:
- Every pin the firmware uses exists on the MCU footprint in the PCB.
- No OUTPUT pin is wired to an INPUT_ONLY net.
- The I2C bus (SDA + SCL) is complete and wired to the correct PCB pads.

Quick-start
-----------
from kerf_firmware.pcb_xcheck import verify

report = verify(fw_sources=["...main.ino text..."], pcb_text="...board.kicad_pcb text...")
if not report.ok:
    for pin in report.missing_pins:
        print(f"Pin {pin} used in firmware but not found on PCB")
"""
from __future__ import annotations

from .compare import XcheckReport, compare
from .fw_pins import FwPinMap, extract_fw_pins
from .pcb_pins import PcbPin, parse_kicad_pcb_pins

__all__ = [
    "verify",
    "XcheckReport",
    "FwPinMap",
    "PcbPin",
    "extract_fw_pins",
    "parse_kicad_pcb_pins",
    "compare",
]


def verify(
    fw_sources: list[str],
    pcb_text: str,
    *,
    mcu_ref: str | None = None,
) -> XcheckReport:
    """One-shot convenience function: parse both sides then cross-check.

    Parameters
    ----------
    fw_sources:
        List of firmware source file text strings (e.g. .ino / .cpp / .h).
    pcb_text:
        Text content of the .kicad_pcb file.
    mcu_ref:
        KiCad component reference for the MCU footprint (e.g. "U1").
        If None, the first "U*" footprint is selected automatically.

    Returns
    -------
    XcheckReport
    """
    fw_map = extract_fw_pins(fw_sources)
    pcb_pins = parse_kicad_pcb_pins(pcb_text, ref=mcu_ref)
    return compare(pcb_pins, fw_map, mcu_ref=mcu_ref)
