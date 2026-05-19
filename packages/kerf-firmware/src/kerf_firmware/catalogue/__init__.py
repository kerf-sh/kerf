"""kerf_firmware.catalogue — Embedded sensor/actuator/protocol catalogue.

Public API
----------
from kerf_firmware.catalogue import (
    SENSORS, ACTUATORS, PROTOCOLS,
    lookup_sensor, lookup_actuator, lookup_protocol,
)
from kerf_firmware.catalogue.library_glue import sensor_library
"""
from kerf_firmware.catalogue.sensors import SENSORS, lookup_sensor
from kerf_firmware.catalogue.actuators import ACTUATORS, lookup_actuator
from kerf_firmware.catalogue.protocols import PROTOCOLS, lookup_protocol

__all__ = [
    "SENSORS",
    "ACTUATORS",
    "PROTOCOLS",
    "lookup_sensor",
    "lookup_actuator",
    "lookup_protocol",
]
