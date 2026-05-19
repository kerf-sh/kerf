"""test_protocol_catalogue.py — pytest suite for kerf_firmware protocol catalogue."""
import pytest

from kerf_firmware.catalogue.protocols import (
    PROTOCOLS,
    I2C_ADDRESS_MIN,
    I2C_ADDRESS_MAX,
    is_valid_i2c_address,
    lookup_protocol,
)


# ---------------------------------------------------------------------------
# Protocol catalogue structure
# ---------------------------------------------------------------------------

EXPECTED_PROTOCOLS = {"I2C", "SPI", "UART", "CAN", "OneWire", "I2S", "USB"}

REQUIRED_KEYS = {
    "name",
    "full_name",
    "bus_type",
    "max_speed_kbps",
    "max_devices",
    "address_bits",
    "voltage_levels",
    "duplex",
    "typical_use",
    "wire_count",
    "arduino_api",
}


class TestProtocolCatalogueContent:
    def test_all_required_protocols_present(self):
        names = {p["name"] for p in PROTOCOLS}
        missing = EXPECTED_PROTOCOLS - names
        assert not missing, f"Missing protocols: {missing}"

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_required_keys_present(self, protocol):
        missing = REQUIRED_KEYS - protocol.keys()
        assert not missing, (
            f"Protocol '{protocol.get('name')}' missing keys: {missing}"
        )

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_name_nonempty(self, protocol):
        assert isinstance(protocol["name"], str) and protocol["name"].strip()

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_full_name_nonempty(self, protocol):
        assert isinstance(protocol["full_name"], str) and protocol["full_name"].strip()

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_wire_count_positive(self, protocol):
        assert isinstance(protocol["wire_count"], int) and protocol["wire_count"] >= 1

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_duplex_valid(self, protocol):
        assert protocol["duplex"] in {"full", "half", "simplex"}

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_voltage_levels_nonempty(self, protocol):
        assert isinstance(protocol["voltage_levels"], list)
        assert len(protocol["voltage_levels"]) >= 1

    @pytest.mark.parametrize("protocol", PROTOCOLS)
    def test_typical_use_nonempty(self, protocol):
        assert isinstance(protocol["typical_use"], str) and protocol["typical_use"].strip()


# ---------------------------------------------------------------------------
# Protocol name uniqueness
# ---------------------------------------------------------------------------

class TestProtocolUniqueness:
    def test_names_are_unique(self):
        names = [p["name"] for p in PROTOCOLS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookupProtocol:
    def test_lookup_i2c(self):
        p = lookup_protocol("I2C")
        assert p is not None
        assert p["full_name"] == "Inter-Integrated Circuit"
        assert p["wire_count"] == 2
        assert p["address_bits"] == 7

    def test_lookup_spi(self):
        p = lookup_protocol("SPI")
        assert p is not None
        assert p["duplex"] == "full"
        assert p["wire_count"] == 4

    def test_lookup_uart(self):
        p = lookup_protocol("UART")
        assert p is not None
        assert p["wire_count"] == 2

    def test_lookup_can(self):
        p = lookup_protocol("CAN")
        assert p is not None
        assert p["address_bits"] == 11

    def test_lookup_onewire(self):
        p = lookup_protocol("OneWire")
        assert p is not None
        assert p["wire_count"] == 1
        assert p["address_bits"] == 64

    def test_lookup_i2s(self):
        p = lookup_protocol("I2S")
        assert p is not None
        assert p["duplex"] == "simplex"

    def test_lookup_usb(self):
        p = lookup_protocol("USB")
        assert p is not None
        assert p["max_devices"] == 127

    def test_lookup_case_insensitive(self):
        p = lookup_protocol("i2c")
        assert p is not None
        assert p["name"] == "I2C"

    def test_lookup_nonexistent_returns_none(self):
        assert lookup_protocol("Bluetooth") is None


# ---------------------------------------------------------------------------
# I2C address validation
# ---------------------------------------------------------------------------

class TestI2CAddressConstants:
    def test_min_constant(self):
        assert I2C_ADDRESS_MIN == 0x08

    def test_max_constant(self):
        assert I2C_ADDRESS_MAX == 0x77


class TestIsValidI2CAddress:
    # --- Valid addresses ---
    def test_min_valid_address(self):
        assert is_valid_i2c_address(0x08) is True

    def test_max_valid_address(self):
        assert is_valid_i2c_address(0x77) is True

    def test_mid_range_valid(self):
        assert is_valid_i2c_address(0x29) is True   # VL53L0X

    def test_common_sensor_addresses(self):
        valid_addrs = [0x29, 0x3C, 0x40, 0x48, 0x57, 0x58, 0x62, 0x68, 0x76, 0x77]
        for addr in valid_addrs:
            assert is_valid_i2c_address(addr) is True, f"0x{addr:02X} should be valid"

    # --- Invalid addresses: above 0x77 ───────────────────────────────────────
    def test_0x78_is_invalid(self):
        assert is_valid_i2c_address(0x78) is False

    def test_0x79_is_invalid(self):
        assert is_valid_i2c_address(0x79) is False

    def test_0x7F_is_invalid(self):
        assert is_valid_i2c_address(0x7F) is False

    def test_above_0x7F_is_invalid(self):
        assert is_valid_i2c_address(0x80) is False
        assert is_valid_i2c_address(0xFF) is False

    # --- Invalid addresses: below 0x08 (reserved) ───────────────────────────
    def test_0x00_is_invalid(self):
        assert is_valid_i2c_address(0x00) is False

    def test_0x07_is_invalid(self):
        assert is_valid_i2c_address(0x07) is False

    def test_negative_is_invalid(self):
        assert is_valid_i2c_address(-1) is False

    # --- Boundary: just outside both ends ---
    def test_boundary_just_below_min(self):
        assert is_valid_i2c_address(I2C_ADDRESS_MIN - 1) is False

    def test_boundary_just_above_max(self):
        """Addresses greater than 0x77 must be rejected."""
        assert is_valid_i2c_address(I2C_ADDRESS_MAX + 1) is False


# ---------------------------------------------------------------------------
# Protocol-specific behaviour checks
# ---------------------------------------------------------------------------

class TestI2CProtocol:
    def test_i2c_max_standard_speed(self):
        p = lookup_protocol("I2C")
        # High-speed mode is 3.4 MHz; catalogue records maximum
        assert p["max_speed_kbps"] >= 3400.0

    def test_i2c_is_half_duplex(self):
        p = lookup_protocol("I2C")
        assert p["duplex"] == "half"

    def test_i2c_arduino_api_is_wire(self):
        p = lookup_protocol("I2C")
        assert "Wire" in p["arduino_api"]


class TestSPIProtocol:
    def test_spi_is_full_duplex(self):
        p = lookup_protocol("SPI")
        assert p["duplex"] == "full"

    def test_spi_arduino_api(self):
        p = lookup_protocol("SPI")
        assert "SPI" in p["arduino_api"]


class TestCANProtocol:
    def test_can_standard_frame_11bit(self):
        p = lookup_protocol("CAN")
        assert p["address_bits"] == 11

    def test_can_uses_differential_pair(self):
        p = lookup_protocol("CAN")
        assert p["wire_count"] == 2


class TestOneWireProtocol:
    def test_onewire_single_wire(self):
        p = lookup_protocol("OneWire")
        assert p["wire_count"] == 1

    def test_onewire_64bit_address(self):
        p = lookup_protocol("OneWire")
        assert p["address_bits"] == 64
