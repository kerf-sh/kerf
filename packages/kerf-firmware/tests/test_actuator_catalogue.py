"""test_actuator_catalogue.py — pytest suite for kerf_firmware actuator catalogue."""
import pytest

from kerf_firmware.catalogue.actuators import ACTUATORS, lookup_actuator


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

class TestActuatorCount:
    def test_at_least_30_actuators(self):
        assert len(ACTUATORS) >= 30, (
            f"Expected >= 30 actuators, got {len(ACTUATORS)}"
        )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "name",
    "category",
    "protocol",
    "address",
    "datasheet_url",
    "arduino_library",
    "supply_voltage",
    "current_draw_mA",
    "description",
}


class TestActuatorSchema:
    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_required_keys_present(self, actuator):
        missing = REQUIRED_KEYS - actuator.keys()
        assert not missing, f"Actuator '{actuator.get('name')}' missing keys: {missing}"

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_name_is_nonempty_string(self, actuator):
        assert isinstance(actuator["name"], str) and actuator["name"].strip()

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_protocol_is_known(self, actuator):
        known = {"PWM", "GPIO", "I2C", "SPI", "UART", "Analog"}
        assert actuator["protocol"] in known, (
            f"Actuator '{actuator['name']}' has unknown protocol '{actuator['protocol']}'"
        )

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_address_none_or_int(self, actuator):
        addr = actuator["address"]
        assert addr is None or isinstance(addr, int)

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_i2c_address_in_valid_range(self, actuator):
        if actuator["protocol"] == "I2C" and actuator["address"] is not None:
            addr = actuator["address"]
            assert 0x08 <= addr <= 0x77, (
                f"Actuator '{actuator['name']}' I2C address 0x{addr:02X} outside valid range"
            )

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_supply_voltage_is_list(self, actuator):
        assert isinstance(actuator["supply_voltage"], list)
        assert len(actuator["supply_voltage"]) >= 1

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_current_draw_positive(self, actuator):
        assert actuator["current_draw_mA"] > 0

    @pytest.mark.parametrize("actuator", ACTUATORS)
    def test_description_nonempty(self, actuator):
        assert isinstance(actuator["description"], str) and actuator["description"].strip()


# ---------------------------------------------------------------------------
# Name uniqueness
# ---------------------------------------------------------------------------

class TestActuatorUniqueness:
    def test_names_are_unique(self):
        names = [a["name"] for a in ACTUATORS]
        assert len(names) == len(set(names)), "Duplicate actuator names found"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookupActuator:
    def test_lookup_sg90(self):
        a = lookup_actuator("SG90")
        assert a is not None
        assert a["category"] == "servo"
        assert a["protocol"] == "PWM"

    def test_lookup_nema17(self):
        a = lookup_actuator("NEMA 17")
        assert a is not None
        assert a["category"] == "stepper"

    def test_lookup_ws2812b(self):
        a = lookup_actuator("WS2812B")
        assert a is not None
        assert a["category"] == "addressable_led"
        assert a["protocol"] == "GPIO"

    def test_lookup_l298n(self):
        a = lookup_actuator("L298N")
        assert a is not None
        assert a["category"] == "motor_driver"

    def test_lookup_pca9685(self):
        a = lookup_actuator("PCA9685")
        assert a is not None
        assert a["protocol"] == "I2C"
        assert a["address"] == 0x40

    def test_lookup_case_insensitive(self):
        a = lookup_actuator("sg90")
        assert a is not None
        assert a["name"] == "SG90"

    def test_lookup_nonexistent_returns_none(self):
        assert lookup_actuator("NonExistentActuatorXYZ") is None

    def test_lookup_empty_string_returns_none(self):
        assert lookup_actuator("") is None


# ---------------------------------------------------------------------------
# Category spot-checks
# ---------------------------------------------------------------------------

class TestActuatorCategories:
    def _categories(self):
        return {a["category"] for a in ACTUATORS}

    def test_servo_category_present(self):
        assert "servo" in self._categories()

    def test_stepper_category_present(self):
        assert "stepper" in self._categories()

    def test_dc_motor_category_present(self):
        assert "dc_motor" in self._categories()

    def test_addressable_led_category_present(self):
        assert "addressable_led" in self._categories()

    def test_relay_category_present(self):
        assert "relay" in self._categories()

    def test_display_category_present(self):
        assert "display" in self._categories()

    def test_motor_driver_present(self):
        assert "motor_driver" in self._categories()


# ---------------------------------------------------------------------------
# Specific spot-checks
# ---------------------------------------------------------------------------

class TestSpecificActuators:
    def test_drv8825_stepper_driver(self):
        a = lookup_actuator("DRV8825")
        assert a is not None
        assert a["category"] == "stepper_driver"
        assert a["address"] is None

    def test_tmc2208_uart(self):
        a = lookup_actuator("TMC2208")
        assert a is not None
        assert a["protocol"] == "UART"

    def test_ssd1306_i2c_display(self):
        a = lookup_actuator("SSD1306 OLED 128x64")
        assert a is not None
        assert a["protocol"] == "I2C"
        assert a["address"] == 0x3C

    def test_ili9341_spi_display(self):
        a = lookup_actuator("ILI9341 TFT 240x320")
        assert a is not None
        assert a["protocol"] == "SPI"
