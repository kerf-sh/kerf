"""kerf_firmware.catalogue.protocols — Embedded communication protocol catalogue.

Covers: I2C, SPI, UART, CAN, OneWire, I2S, USB.

Each entry is a dict with:
  name              str        — protocol name
  full_name         str        — expanded name
  bus_type          str        — "serial", "parallel", "wireless"
  max_speed_kbps    float      — maximum data rate in kbps (None = varies)
  max_devices       int|None   — max devices on one bus (None = unlimited / N/A)
  address_bits      int|None   — address width in bits (for addressed buses)
  voltage_levels    list[float]— common signalling voltages
  duplex            str        — "full", "half", "simplex"
  typical_use       str        — one-line plain-English use-case description
  wire_count        int        — minimum conductor count (excluding power/ground)
  arduino_api       str        — Arduino library / API class name

I2C address helpers
-------------------
  I2C_ADDRESS_MIN  = 0x08   (first non-reserved 7-bit address)
  I2C_ADDRESS_MAX  = 0x77   (last non-reserved 7-bit address)
  is_valid_i2c_address(addr) — returns True for 0x08–0x77
"""
from __future__ import annotations

from typing import Any

# ── I2C address range constants ───────────────────────────────────────────────
I2C_ADDRESS_MIN: int = 0x08
I2C_ADDRESS_MAX: int = 0x77


def is_valid_i2c_address(addr: int) -> bool:
    """Return True if *addr* is a valid 7-bit I2C device address.

    Addresses 0x00–0x07 and 0x78–0x7F are reserved by the I2C specification
    and must not be used for regular device addressing.  Any value outside
    [0x08, 0x77] (inclusive) is therefore invalid.

    >>> is_valid_i2c_address(0x29)
    True
    >>> is_valid_i2c_address(0x78)
    False
    >>> is_valid_i2c_address(0x00)
    False
    """
    return I2C_ADDRESS_MIN <= addr <= I2C_ADDRESS_MAX


# ── Protocol catalogue ────────────────────────────────────────────────────────
PROTOCOLS: list[dict[str, Any]] = [
    {
        "name": "I2C",
        "full_name": "Inter-Integrated Circuit",
        "bus_type": "serial",
        "max_speed_kbps": 3400.0,     # High-speed mode; standard = 100, fast = 400
        "max_devices": 112,            # 7-bit address space minus reserved addresses
        "address_bits": 7,
        "voltage_levels": [1.8, 2.5, 3.3, 5.0],
        "duplex": "half",
        "typical_use": "Short-distance on-board sensor/peripheral communication (SDA + SCL).",
        "wire_count": 2,
        "arduino_api": "Wire",
    },
    {
        "name": "SPI",
        "full_name": "Serial Peripheral Interface",
        "bus_type": "serial",
        "max_speed_kbps": 100_000.0,  # Typically 1–50 MHz
        "max_devices": None,           # One CS line per device; theoretically unlimited
        "address_bits": None,          # No address; CS selects device
        "voltage_levels": [1.8, 3.3, 5.0],
        "duplex": "full",
        "typical_use": "High-speed sensor readout, display drivers, flash memory.",
        "wire_count": 4,               # MOSI, MISO, SCK, CS (one CS per device)
        "arduino_api": "SPI",
    },
    {
        "name": "UART",
        "full_name": "Universal Asynchronous Receiver/Transmitter",
        "bus_type": "serial",
        "max_speed_kbps": 3000.0,     # Practical embedded max ~3 Mbps
        "max_devices": 1,              # Point-to-point; RS-485 extends this
        "address_bits": None,
        "voltage_levels": [3.3, 5.0],
        "duplex": "full",
        "typical_use": "GPS modules, Bluetooth, Wi-Fi co-processors, debug consoles.",
        "wire_count": 2,               # TX + RX (plus optional RTS/CTS)
        "arduino_api": "Serial / HardwareSerial",
    },
    {
        "name": "CAN",
        "full_name": "Controller Area Network",
        "bus_type": "serial",
        "max_speed_kbps": 1000.0,     # CAN 2.0B; CAN FD up to 8 Mbps
        "max_devices": 110,            # Practical limit (load dependent)
        "address_bits": 11,            # Standard frame; extended = 29
        "voltage_levels": [5.0, 12.0, 24.0],
        "duplex": "half",
        "typical_use": "Automotive, industrial, and robotics multi-node communication.",
        "wire_count": 2,               # CAN-H and CAN-L (differential pair)
        "arduino_api": "CAN / mcp_can",
    },
    {
        "name": "OneWire",
        "full_name": "1-Wire",
        "bus_type": "serial",
        "max_speed_kbps": 16.3,       # Overdrive mode; standard = 16.3 kbps
        "max_devices": None,           # Daisy-chain; parasitic power limits count
        "address_bits": 64,            # 64-bit ROM address per device
        "voltage_levels": [3.3, 5.0],
        "duplex": "half",
        "typical_use": "Temperature sensors (DS18B20), iButton authentication.",
        "wire_count": 1,               # Single data line; can also parasitically power
        "arduino_api": "OneWire",
    },
    {
        "name": "I2S",
        "full_name": "Inter-IC Sound",
        "bus_type": "serial",
        "max_speed_kbps": 12288.0,    # 192 kHz × 32 bit × 2 channels
        "max_devices": None,
        "address_bits": None,
        "voltage_levels": [1.8, 3.3],
        "duplex": "simplex",
        "typical_use": "Digital audio: microphones (INMP441, SPH0645), DACs, codecs.",
        "wire_count": 3,               # SCK (bit clock), WS (word select), SD (data)
        "arduino_api": "I2S",
    },
    {
        "name": "USB",
        "full_name": "Universal Serial Bus",
        "bus_type": "serial",
        "max_speed_kbps": 480_000.0,  # USB 2.0 High-Speed; USB FS = 12 Mbps
        "max_devices": 127,
        "address_bits": 7,
        "voltage_levels": [3.3, 5.0],
        "duplex": "full",
        "typical_use": "Device-to-host communication, firmware flashing, HID, CDC.",
        "wire_count": 2,               # D+ and D- (differential pair)
        "arduino_api": "TinyUSB / built-in USB",
    },
]


def lookup_protocol(name: str) -> dict[str, Any] | None:
    """Return the protocol entry matching *name* (case-insensitive), or None."""
    name_lower = name.lower()
    for p in PROTOCOLS:
        if p["name"].lower() == name_lower:
            return p
    return None
