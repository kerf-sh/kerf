"""test_sensor_catalogue.py — pytest suite for kerf_firmware sensor catalogue."""
import pytest

from kerf_firmware.catalogue.sensors import SENSORS, lookup_sensor


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

class TestSensorCount:
    def test_at_least_40_sensors(self):
        assert len(SENSORS) >= 40, (
            f"Expected >= 40 sensors, got {len(SENSORS)}"
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


class TestSensorSchema:
    @pytest.mark.parametrize("sensor", SENSORS)
    def test_required_keys_present(self, sensor):
        missing = REQUIRED_KEYS - sensor.keys()
        assert not missing, f"Sensor '{sensor.get('name')}' missing keys: {missing}"

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_name_is_nonempty_string(self, sensor):
        assert isinstance(sensor["name"], str) and sensor["name"].strip()

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_protocol_is_known(self, sensor):
        known = {"I2C", "SPI", "UART", "OneWire", "Analog", "GPIO", "I2S", "CAN"}
        assert sensor["protocol"] in known, (
            f"Sensor '{sensor['name']}' has unknown protocol '{sensor['protocol']}'"
        )

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_address_none_or_int(self, sensor):
        addr = sensor["address"]
        assert addr is None or isinstance(addr, int)

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_i2c_address_in_valid_range(self, sensor):
        """I2C addresses must be in the valid 7-bit range 0x08–0x77."""
        if sensor["protocol"] == "I2C" and sensor["address"] is not None:
            addr = sensor["address"]
            assert 0x08 <= addr <= 0x77, (
                f"Sensor '{sensor['name']}' I2C address 0x{addr:02X} is outside valid range"
            )

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_supply_voltage_is_list(self, sensor):
        assert isinstance(sensor["supply_voltage"], list)
        assert len(sensor["supply_voltage"]) >= 1

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_current_draw_positive(self, sensor):
        assert sensor["current_draw_mA"] > 0

    @pytest.mark.parametrize("sensor", SENSORS)
    def test_description_nonempty(self, sensor):
        assert isinstance(sensor["description"], str) and sensor["description"].strip()


# ---------------------------------------------------------------------------
# Name uniqueness
# ---------------------------------------------------------------------------

class TestSensorUniqueness:
    def test_names_are_unique(self):
        names = [s["name"] for s in SENSORS]
        assert len(names) == len(set(names)), "Duplicate sensor names found"


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookupSensor:
    def test_lookup_dht22(self):
        s = lookup_sensor("DHT22")
        assert s is not None
        assert s["protocol"] == "OneWire"
        assert s["category"] == "temperature_humidity"

    def test_lookup_bme280(self):
        s = lookup_sensor("BME280")
        assert s is not None
        assert s["protocol"] == "I2C"
        assert s["address"] == 0x76

    def test_lookup_mpu6050(self):
        s = lookup_sensor("MPU6050")
        assert s is not None
        assert s["address"] == 0x68
        assert "imu" in s["category"]

    def test_lookup_vl53l0x(self):
        s = lookup_sensor("VL53L0X")
        assert s is not None
        assert s["address"] == 0x29

    def test_lookup_max30102(self):
        s = lookup_sensor("MAX30102")
        assert s is not None
        assert s["address"] == 0x57
        assert s["category"] == "biometric"

    def test_lookup_ds18b20(self):
        s = lookup_sensor("DS18B20")
        assert s is not None
        assert s["protocol"] == "OneWire"

    def test_lookup_case_insensitive(self):
        s = lookup_sensor("dht22")
        assert s is not None
        assert s["name"] == "DHT22"

    def test_lookup_nonexistent_returns_none(self):
        assert lookup_sensor("NonExistentSensorXYZ") is None

    def test_lookup_empty_string_returns_none(self):
        assert lookup_sensor("") is None


# ---------------------------------------------------------------------------
# Specific known sensors spot-checks
# ---------------------------------------------------------------------------

class TestSpecificSensors:
    def test_neo6m_is_uart(self):
        s = lookup_sensor("NEO-6M")
        assert s is not None
        assert s["protocol"] == "UART"
        assert s["address"] is None

    def test_scd40_co2_sensor(self):
        s = lookup_sensor("SCD40")
        assert s is not None
        assert s["category"] == "co2"
        assert s["address"] == 0x62

    def test_mfrc522_is_spi(self):
        s = lookup_sensor("MFRC522")
        assert s is not None
        assert s["protocol"] == "SPI"

    def test_inmp441_is_i2s(self):
        s = lookup_sensor("INMP441")
        assert s is not None
        assert s["protocol"] == "I2S"

    def test_hc_sr04_is_gpio(self):
        s = lookup_sensor("HC-SR04")
        assert s is not None
        assert s["protocol"] == "GPIO"
        assert s["address"] is None

    def test_mq2_is_analog(self):
        s = lookup_sensor("MQ-2")
        assert s is not None
        assert s["protocol"] == "Analog"
