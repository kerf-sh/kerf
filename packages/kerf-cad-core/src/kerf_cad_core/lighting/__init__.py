"""
kerf_cad_core.lighting — illumination engineering calculators.

Distinct from:
  buildingenergy/  — daylight factor only
  optics/          — geometrical lens optics
  solarpv/         — photovoltaic energy yield
  electronics/leddriver/ — LED driver circuitry

Public API (re-exported for convenience):

    from kerf_cad_core.lighting import (
        # Lumen / zonal-cavity method
        room_cavity_ratio,
        coefficient_of_utilization,
        light_loss_factor,
        luminaires_for_target_lux,
        lux_from_luminaires,
        spacing_to_mounting_height_ratio,
        uniformity_check,
        # Point method
        horizontal_illuminance,
        vertical_illuminance,
        multi_luminaire_illuminance,
        # Luminance / exitance / contrast
        luminance_from_illuminance,
        exitance,
        contrast_ratio,
        # Glare
        ugr,
        # Roadway
        road_luminance,
        pole_spacing,
        roadway_utilization,
        # Emergency
        emergency_lux_at_floor,
        emergency_spacing,
        # Energy / LPD
        lamp_lumens_per_watt,
        lamp_energy,
        lpd_check,
    )

References
----------
IES Lighting Handbook, 10th ed. (IESNA, 2011)
CIE 117-1995 — Discomfort Glare in Interior Lighting
EN 12464-1:2021 — Light and Lighting of Workplaces
ASHRAE 90.1-2022, §9 — Lighting
California Title 24, Part 6 (2022 BEES)
NFPA 101 / BS 5266 — Emergency Lighting

Author: imranparuk
"""

from kerf_cad_core.lighting.design import (
    room_cavity_ratio,
    coefficient_of_utilization,
    light_loss_factor,
    luminaires_for_target_lux,
    lux_from_luminaires,
    spacing_to_mounting_height_ratio,
    uniformity_check,
    horizontal_illuminance,
    vertical_illuminance,
    multi_luminaire_illuminance,
    luminance_from_illuminance,
    exitance,
    contrast_ratio,
    ugr,
    road_luminance,
    pole_spacing,
    roadway_utilization,
    emergency_lux_at_floor,
    emergency_spacing,
    lamp_lumens_per_watt,
    lamp_energy,
    lpd_check,
)

__all__ = [
    "room_cavity_ratio",
    "coefficient_of_utilization",
    "light_loss_factor",
    "luminaires_for_target_lux",
    "lux_from_luminaires",
    "spacing_to_mounting_height_ratio",
    "uniformity_check",
    "horizontal_illuminance",
    "vertical_illuminance",
    "multi_luminaire_illuminance",
    "luminance_from_illuminance",
    "exitance",
    "contrast_ratio",
    "ugr",
    "road_luminance",
    "pole_spacing",
    "roadway_utilization",
    "emergency_lux_at_floor",
    "emergency_spacing",
    "lamp_lumens_per_watt",
    "lamp_energy",
    "lpd_check",
]
