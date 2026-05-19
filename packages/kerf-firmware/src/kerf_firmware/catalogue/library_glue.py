"""kerf_firmware.catalogue.library_glue — Sensor → Arduino library resolver.

Maps each sensor name to its recommended Arduino/PlatformIO library and
provides helper utilities for code generation.

Public API
----------
sensor_library(sensor_name) -> str | None
    Return the primary Arduino library name for the given sensor, or None.

sensor_libraries_by_protocol(protocol) -> dict[str, str]
    Return {sensor_name: library} for all sensors on the given protocol.

include_hint(sensor_name) -> str | None
    Return a suggested ``#include`` directive for the sensor's library.
"""
from __future__ import annotations

from kerf_firmware.catalogue.sensors import SENSORS, lookup_sensor

# ── Sensor → library map (built lazily from catalogue) ───────────────────────
_SENSOR_LIBRARY_MAP: dict[str, str] = {
    entry["name"]: entry["arduino_library"]
    for entry in SENSORS
    if entry.get("arduino_library")
}


def sensor_library(sensor_name: str) -> str | None:
    """Return the primary Arduino library name for *sensor_name*.

    Lookup is case-insensitive.  Returns None if the sensor is not found
    or if no library is catalogued for it.

    Examples
    --------
    >>> sensor_library("DHT22")
    'DHT sensor library'
    >>> sensor_library("BME280")
    'Adafruit BME280 Library'
    >>> sensor_library("unknown_part")
    None
    """
    sensor = lookup_sensor(sensor_name)
    if sensor is None:
        return None
    lib = sensor.get("arduino_library", "")
    return lib if lib else None


def sensor_libraries_by_protocol(protocol: str) -> dict[str, str]:
    """Return a mapping of {sensor_name: library} for sensors using *protocol*.

    Protocol comparison is case-insensitive.

    Examples
    --------
    >>> libs = sensor_libraries_by_protocol("I2C")
    >>> "BME280" in libs
    True
    """
    protocol_upper = protocol.upper()
    result: dict[str, str] = {}
    for entry in SENSORS:
        if entry.get("protocol", "").upper() == protocol_upper:
            lib = entry.get("arduino_library", "")
            if lib:
                result[entry["name"]] = lib
    return result


# ── Well-known include header hints ──────────────────────────────────────────
# Format: library_name (lowercased) → C++ include header
_LIBRARY_INCLUDE_HINTS: dict[str, str] = {
    "dht sensor library": "DHT.h",
    "adafruit bme280 library": "Adafruit_BME280.h",
    "adafruit bmp085 library": "Adafruit_BMP085.h",
    "adafruit bmp3xx library": "Adafruit_BMP3XX.h",
    "adafruit sht31 library": "Adafruit_SHT31.h",
    "dallastemperature": "DallasTemperature.h",
    "adafruit mpu6050": "Adafruit_MPU6050.h",
    "mpu9250": "MPU9250.h",
    "arduino_lsm6ds3": "Arduino_LSM6DS3.h",
    "sparkfun icm-20948 imu": "ICM_20948.h",
    "adafruit adxl345": "Adafruit_ADXL345_U.h",
    "adafruit hmc5883 unified": "Adafruit_HMC5883_U.h",
    "vl53l0x": "VL53L0X.h",
    "sparkfun vl53l1x 4m laser distance sensor": "SparkFun_VL53L1X.h",
    "hcsr04": "HCSR04.h",
    "sparkfun apds-9960 rgb and gesture sensor": "SparkFun_APDS9960.h",
    "sparkfun max3010x pulse and proximity sensor library": "MAX30105.h",
    "protocentral max30205 human body temperature sensor": "protocentral_max30205.h",
    "mqunifiedsensor": "MQUnifiedsensor.h",
    "sparkfun ccs811 arduino library": "SparkFunCCS811.h",
    "adafruit sgp30 gas / air quality sensor library": "Adafruit_SGP30.h",
    "adafruit bme680 library": "Adafruit_BME680.h",
    "adafruit tsl2591 library": "Adafruit_TSL2591.h",
    "bh1750": "BH1750.h",
    "tinygps++": "TinyGPSPlus.h",
    "adafruit ina219": "Adafruit_INA219.h",
    "ina3221": "INA3221.h",
    "adafruit tcs34725": "Adafruit_TCS34725.h",
    "esp-idf i2s": "driver/i2s.h",
    "as5600": "AS5600.h",
    "acs712": "ACS712.h",
    "adafruit mpr121": "Adafruit_MPR121.h",
    "mhz19": "MHZ19.h",
    "sensirion i2c scd4x": "SensirionI2CScd4x.h",
    "hx711": "HX711.h",
    "mfrc522": "MFRC522.h",
    "adafruit pn532": "Adafruit_PN532.h",
}


def include_hint(sensor_name: str) -> str | None:
    """Return a suggested ``#include`` directive for the sensor's library.

    Returns None if the sensor is unknown or no hint is registered.

    Examples
    --------
    >>> include_hint("DHT22")
    '#include <DHT.h>'
    >>> include_hint("MPU6050")
    '#include <Adafruit_MPU6050.h>'
    """
    lib = sensor_library(sensor_name)
    if lib is None:
        return None
    header = _LIBRARY_INCLUDE_HINTS.get(lib.lower())
    if header is None:
        return None
    return f"#include <{header}>"
