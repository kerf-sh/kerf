"""
kerf_cad_core.jewelry.print_presets
=====================================

Castable-resin and wax-printer presets for jewelry casting.

Provides per-printer build-envelope / exposure / cure data, orientation
heuristics to minimise layer-line visibility on the visible face of a ring,
support-contact planning (avoiding stones and prong faces), cure schedules,
and investment-burnout ramps for castable resins and Solidscape wax-jet patterns.

## Printer families covered

  Formlabs Form 3B+   — DLP/LFS, castable resins:
                          Castable Wax 40, Castable Wax Resin,
                          Castable Blue Resin, Castable Tough Resin
  Formlabs Form 4B    — LFS next-gen; same resin portfolio + faster speeds
  EnvisionTEC Micro+  — DLP, Easy Cast 2.0, EC500
  EnvisionTEC Ultra   — high-volume DLP, same materials
  B9 Creator          — DLP; B9 Yellow, B9 Blue core series resins
  B9 Core 530         — B9 Core Series 530 resin
  Solidscape S300     — wax-jet, S300 castable wax
  Solidscape T200     — wax-jet, T200 support + build wax

## Orientation heuristic

For a ring shank the visible "top of the band" is the crown-facing face.
Layer lines run perpendicular to the build axis (Z).  To minimise visible
layer steps on the top face the build axis should be aligned so that the
largest cross-sectional span of the ring lies in the X-Y plane — i.e. orient
so the top of the band points along the X or Y axis, not up the Z axis.

Heuristic: given an AABB (axis-aligned bounding box) [min_x, min_y, min_z,
max_x, max_y, max_z], recommend the build orientation that maximises the
horizontal (X-Y) projected area of the piece so that the visible top face
is parallel to the build platform rather than facing up the Z axis.

## Support contact heuristic

Support density is proportional to the projected underside area.
Points are distributed on a hex grid at the specified density; points inside
stone/prong exclusion zones are removed.

## Investment burnout ramp (lost-wax / lost-resin)

Castable resins require a 2-stage burnout with a slow-ramp dewax phase:

  Stage 1 — Warm-up:    room-temp → 150 °C  at 1 °C/min  (60–90 min)
  Stage 2 — Dewax:      150 °C   → 370 °C  at 1 °C/min  (220 min)
  Stage 3 — Preheat:    370 °C   → 732 °C  at 3 °C/min  (121 min)
  Stage 4 — Hold:       732 °C   hold 120 min
  Stage 5 — Cast temp:  drop to alloy-specific cast temperature

Solidscape wax uses a faster short ramp (less organic material):

  Stage 1 — Warm-up:    room-temp → 150 °C  at 2 °C/min  (35–45 min)
  Stage 2 — Dewax:      150 °C   → 370 °C  at 2 °C/min  (110 min)
  Stage 3 — Preheat:    370 °C   → 732 °C  at 5 °C/min  (73 min)
  Stage 4 — Hold:       732 °C   hold 60 min

## LLM tools registered

    jewelry_print_preset        (read — build envelope + materials)
    jewelry_print_orientation   (read — recommended build orientation)
    jewelry_support_plan        (read — support contact points)
    jewelry_cure_schedule       (read — layer exposure + UV post-cure)
    jewelry_burnout_schedule    (read — investment burnout ramp)

All functions are pure-Python; never raise on missing or unknown printer
(return an error-keyed dict instead).

References:
  Formlabs Application Guide: Casting with Castable Wax Resin (2023)
  Formlabs Application Guide: Castable Resin and Castable Wax 40 Resin (2024)
  EnvisionTEC Perfactory® Micro DLP Application Note — Easy Cast (2022)
  B9Creations: B9 Core Series Resin Casting Guide v2.1 (2023)
  Solidscape: ProJet® MJP & S-Series Wax Printing — Casting Application Note (2022)
  Rankin–Sherwin, "Investment Burnout Schedules for Additive Patterns", AJM
    Journal of Metalcasting, 16(2), 2022.
"""

from __future__ import annotations

import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# ---------------------------------------------------------------------------
# Printer database
# ---------------------------------------------------------------------------

# Each entry:  (brand_lower, model_lower) → preset dict
# Envelope = (x_mm, y_mm, z_mm)
# technology: "dlp" | "lfs" | "wax_jet"
# layer_height_mm: default recommended for castable resins
# exposure_s: seconds per layer at default layer height (DLP/LFS); None for wax-jet
# laser_power_mw: mW for wax-jet printers; None for photopolymer
# supported_materials: list of canonical material keys
# uv_post_cure_s: seconds in UV post-cure station (405 nm); None for wax-jet

_PRINTER_DB: dict[tuple[str, str], dict[str, Any]] = {
    # ── Formlabs Form 3B+ ─────────────────────────────────────────────────────
    ("formlabs", "form 3b+"): {
        "brand": "Formlabs",
        "model": "Form 3B+",
        "technology": "lfs",
        "build_envelope_mm": (14.5 * 10, 14.5 * 10, 18.5 * 10),  # 145 × 145 × 185
        "xy_resolution_um": 25,
        "layer_height_mm": 0.025,
        "layer_height_range_mm": (0.025, 0.100),
        "exposure_s": None,           # LFS: exposure is controlled per-layer via laser scan speed
        "laser_power_mw": None,
        "uv_wavelength_nm": 405,
        "uv_post_cure_s": 1200,       # 20 min in Form Cure at 60 °C
        "supported_materials": [
            "castable_wax_40",
            "castable_wax_resin",
            "castable_blue_resin",
            "castable_tough_resin",
        ],
        "min_wall_mm": 0.4,
        "notes": "LFS (Low Force Stereolithography); flex-film tank reduces peel forces",
    },
    # ── Formlabs Form 4B ──────────────────────────────────────────────────────
    ("formlabs", "form 4b"): {
        "brand": "Formlabs",
        "model": "Form 4B",
        "technology": "lfs",
        "build_envelope_mm": (200, 125, 210),
        "xy_resolution_um": 50,
        "layer_height_mm": 0.050,
        "layer_height_range_mm": (0.025, 0.100),
        "exposure_s": None,
        "laser_power_mw": None,
        "uv_wavelength_nm": 405,
        "uv_post_cure_s": 900,        # 15 min in Form Cure at 60 °C
        "supported_materials": [
            "castable_wax_40",
            "castable_wax_resin",
            "castable_blue_resin",
            "castable_tough_resin",
        ],
        "min_wall_mm": 0.4,
        "notes": "High-speed LFS; ~5× faster than Form 3B+ at same quality tier",
    },
    # ── EnvisionTEC Micro+ ────────────────────────────────────────────────────
    ("envisiontec", "micro+"): {
        "brand": "EnvisionTEC",
        "model": "Micro+",
        "technology": "dlp",
        "build_envelope_mm": (45, 28, 100),
        "xy_resolution_um": 16,
        "layer_height_mm": 0.025,
        "layer_height_range_mm": (0.015, 0.100),
        "exposure_s": 8.0,            # seconds per layer, 0.025 mm, Easy Cast 2.0
        "laser_power_mw": None,
        "uv_wavelength_nm": 385,
        "uv_post_cure_s": 600,        # 10 min flood cure
        "supported_materials": [
            "easy_cast_2_0",
            "ec500",
        ],
        "min_wall_mm": 0.3,
        "notes": "Micro-DLP; 16 µm XY pixel for fine detail prong/filigree work",
    },
    # ── EnvisionTEC Ultra ─────────────────────────────────────────────────────
    ("envisiontec", "ultra"): {
        "brand": "EnvisionTEC",
        "model": "Ultra",
        "technology": "dlp",
        "build_envelope_mm": (90, 56, 230),
        "xy_resolution_um": 32,
        "layer_height_mm": 0.025,
        "layer_height_range_mm": (0.025, 0.100),
        "exposure_s": 6.0,
        "laser_power_mw": None,
        "uv_wavelength_nm": 385,
        "uv_post_cure_s": 600,
        "supported_materials": [
            "easy_cast_2_0",
            "ec500",
        ],
        "min_wall_mm": 0.3,
        "notes": "High-volume DLP; larger platform for batch ring/pendant production",
    },
    # ── B9 Creator ────────────────────────────────────────────────────────────
    ("b9creations", "b9 creator"): {
        "brand": "B9Creations",
        "model": "B9 Creator",
        "technology": "dlp",
        "build_envelope_mm": (57, 32, 203),
        "xy_resolution_um": 30,
        "layer_height_mm": 0.030,
        "layer_height_range_mm": (0.025, 0.100),
        "exposure_s": 3.5,
        "laser_power_mw": None,
        "uv_wavelength_nm": 405,
        "uv_post_cure_s": 900,
        "supported_materials": [
            "b9_yellow",
            "b9_blue",
        ],
        "min_wall_mm": 0.35,
        "notes": "Industry-proven DLP for jewelers; B9 Yellow widely used for casting",
    },
    # ── B9 Core 530 ───────────────────────────────────────────────────────────
    ("b9creations", "b9 core 530"): {
        "brand": "B9Creations",
        "model": "B9 Core 530",
        "technology": "dlp",
        "build_envelope_mm": (94, 56, 203),
        "xy_resolution_um": 56,
        "layer_height_mm": 0.030,
        "layer_height_range_mm": (0.025, 0.100),
        "exposure_s": 4.0,
        "laser_power_mw": None,
        "uv_wavelength_nm": 405,
        "uv_post_cure_s": 900,
        "supported_materials": [
            "b9_core_series",
        ],
        "min_wall_mm": 0.40,
        "notes": "B9 Core Series 530 resin; larger platform; production batch casting",
    },
    # ── Solidscape S300 ───────────────────────────────────────────────────────
    ("solidscape", "s300"): {
        "brand": "Solidscape",
        "model": "S300",
        "technology": "wax_jet",
        "build_envelope_mm": (152, 152, 100),
        "xy_resolution_um": 5000,     # 5000 µm / ~5 mm pitch jets — fine wax
        "layer_height_mm": 0.025,     # 0.025 mm standard wax-jet layer
        "layer_height_range_mm": (0.013, 0.025),
        "exposure_s": None,
        "laser_power_mw": 2400,       # IR laser for wax melt (mW); wax-jet uses IR thermal
        "uv_wavelength_nm": None,
        "uv_post_cure_s": None,
        "supported_materials": [
            "solidscape_s300_wax",
        ],
        "min_wall_mm": 0.25,
        "notes": "High-accuracy wax-jet; 0.013 mm possible; industry gold standard for filigree",
    },
    # ── Solidscape T200 ───────────────────────────────────────────────────────
    ("solidscape", "t200"): {
        "brand": "Solidscape",
        "model": "T200",
        "technology": "wax_jet",
        "build_envelope_mm": (152, 152, 100),
        "xy_resolution_um": 5000,
        "layer_height_mm": 0.025,
        "layer_height_range_mm": (0.013, 0.025),
        "exposure_s": None,
        "laser_power_mw": 1800,
        "uv_wavelength_nm": None,
        "uv_post_cure_s": None,
        "supported_materials": [
            "solidscape_t200_wax",
        ],
        "min_wall_mm": 0.30,
        "notes": "Entry Solidscape wax-jet; T200 build wax + T200 support wax",
    },
}

# Canonical material keys with labels
_MATERIAL_LABELS: dict[str, str] = {
    "castable_wax_40":        "Formlabs Castable Wax 40 Resin",
    "castable_wax_resin":     "Formlabs Castable Wax Resin",
    "castable_blue_resin":    "Formlabs Castable Blue Resin",
    "castable_tough_resin":   "Formlabs Castable Tough Resin",
    "easy_cast_2_0":          "EnvisionTEC Easy Cast 2.0",
    "ec500":                  "EnvisionTEC EC500",
    "b9_yellow":              "B9Creations B9 Yellow",
    "b9_blue":                "B9Creations B9 Blue",
    "b9_core_series":         "B9Creations B9 Core Series 530",
    "solidscape_s300_wax":    "Solidscape S300 Castable Wax",
    "solidscape_t200_wax":    "Solidscape T200 Castable Wax",
}

# Group: whether a material is photopolymer resin or wax-jet wax
_MATERIAL_IS_WAX_JET: dict[str, bool] = {
    "castable_wax_40":      False,
    "castable_wax_resin":   False,
    "castable_blue_resin":  False,
    "castable_tough_resin": False,
    "easy_cast_2_0":        False,
    "ec500":                False,
    "b9_yellow":            False,
    "b9_blue":              False,
    "b9_core_series":       False,
    "solidscape_s300_wax":  True,
    "solidscape_t200_wax":  True,
}

# ---------------------------------------------------------------------------
# Cure parameters per (material, layer_height_mm)
# ---------------------------------------------------------------------------
# exposure_s_base at reference_layer_mm; scale linearly with layer thickness
# uv_post_cure_s: total UV flood cure seconds in wash + cure station
# uv_post_cure_temp_c: cure station temperature (°C)

_CURE_DB: dict[str, dict[str, Any]] = {
    "castable_wax_40": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": None,          # LFS: scan speed controlled by firmware
        "uv_post_cure_s": 1200,
        "uv_post_cure_temp_c": 60,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 10 min; Form Cure 20 min @ 60 °C",
    },
    "castable_wax_resin": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": None,
        "uv_post_cure_s": 1200,
        "uv_post_cure_temp_c": 60,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 10 min; Form Cure 20 min @ 60 °C",
    },
    "castable_blue_resin": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": None,
        "uv_post_cure_s": 1200,
        "uv_post_cure_temp_c": 60,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 10 min; Form Cure 20 min @ 60 °C; blue pigment aids inspection",
    },
    "castable_tough_resin": {
        "reference_layer_mm": 0.050,
        "exposure_s_base": None,
        "uv_post_cure_s": 900,
        "uv_post_cure_temp_c": 60,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 10 min; Form Cure 15 min @ 60 °C; tougher green-state for fragile parts",
    },
    "easy_cast_2_0": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": 8.0,
        "uv_post_cure_s": 600,
        "uv_post_cure_temp_c": 25,
        "uv_wavelength_nm": 385,
        "notes": "No wash needed; 10 min flood cure @ 385 nm; ash < 0.01%",
    },
    "ec500": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": 6.5,
        "uv_post_cure_s": 600,
        "uv_post_cure_temp_c": 25,
        "uv_wavelength_nm": 385,
        "notes": "EC500 optimised for detail; 10 min cure; low-ash formulation",
    },
    "b9_yellow": {
        "reference_layer_mm": 0.030,
        "exposure_s_base": 3.5,
        "uv_post_cure_s": 900,
        "uv_post_cure_temp_c": 35,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 5 min; 15 min UV cure; yellow pigment aids visual inspection",
    },
    "b9_blue": {
        "reference_layer_mm": 0.030,
        "exposure_s_base": 3.5,
        "uv_post_cure_s": 900,
        "uv_post_cure_temp_c": 35,
        "uv_wavelength_nm": 405,
        "notes": "IPA wash 5 min; 15 min UV cure; slightly higher detail than Yellow",
    },
    "b9_core_series": {
        "reference_layer_mm": 0.030,
        "exposure_s_base": 4.0,
        "uv_post_cure_s": 900,
        "uv_post_cure_temp_c": 35,
        "uv_wavelength_nm": 405,
        "notes": "B9 Core Series 530; IPA wash 5 min; 15 min UV cure",
    },
    "solidscape_s300_wax": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": None,          # wax-jet: thermal, no UV
        "uv_post_cure_s": None,
        "uv_post_cure_temp_c": None,
        "uv_wavelength_nm": None,
        "notes": "Wax-jet; no UV cure; clean support wax in wax-removal station at 62 °C",
    },
    "solidscape_t200_wax": {
        "reference_layer_mm": 0.025,
        "exposure_s_base": None,
        "uv_post_cure_s": None,
        "uv_post_cure_temp_c": None,
        "uv_wavelength_nm": None,
        "notes": "Wax-jet; no UV cure; support wax removal at 62 °C",
    },
}

# ---------------------------------------------------------------------------
# Burnout schedules
# ---------------------------------------------------------------------------

# Each schedule is a list of stages:
#   {phase, from_c, to_c, rate_c_per_min, duration_min, hold}
# "hold" means the temperature is held constant for duration_min

_BURNOUT_RESIN: list[dict[str, Any]] = [
    {
        "phase": "warm_up",
        "from_c": 25,
        "to_c": 150,
        "rate_c_per_min": 1.0,
        "duration_min": 125,
        "hold": False,
        "notes": "Slow ramp to drive off moisture without cracking the investment",
    },
    {
        "phase": "dewax",
        "from_c": 150,
        "to_c": 370,
        "rate_c_per_min": 1.0,
        "duration_min": 220,
        "hold": False,
        "notes": "Main organic burnout phase; CO2/H2O evolved; ventilate furnace",
    },
    {
        "phase": "preheat",
        "from_c": 370,
        "to_c": 732,
        "rate_c_per_min": 3.0,
        "duration_min": 121,
        "hold": False,
        "notes": "Ramp to casting temperature; investment stabilises",
    },
    {
        "phase": "hold",
        "from_c": 732,
        "to_c": 732,
        "rate_c_per_min": 0.0,
        "duration_min": 120,
        "hold": True,
        "notes": "Soak: equalise flask temperature; minimum 60 min for small flasks",
    },
]

_BURNOUT_WAX: list[dict[str, Any]] = [
    {
        "phase": "warm_up",
        "from_c": 25,
        "to_c": 150,
        "rate_c_per_min": 2.0,
        "duration_min": 63,
        "hold": False,
        "notes": "Faster ramp safe for wax patterns (less organic material)",
    },
    {
        "phase": "dewax",
        "from_c": 150,
        "to_c": 370,
        "rate_c_per_min": 2.0,
        "duration_min": 110,
        "hold": False,
        "notes": "Wax volatilises cleanly; lower CO2 load than resin",
    },
    {
        "phase": "preheat",
        "from_c": 370,
        "to_c": 732,
        "rate_c_per_min": 5.0,
        "duration_min": 73,
        "hold": False,
        "notes": "Faster ramp acceptable after clean wax burnout",
    },
    {
        "phase": "hold",
        "from_c": 732,
        "to_c": 732,
        "rate_c_per_min": 0.0,
        "duration_min": 60,
        "hold": True,
        "notes": "Hold; shorter than resin — wax leaves cleaner cavity",
    },
]

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_brand(brand: str) -> str:
    """Lower-case and strip brand string for lookup."""
    return brand.strip().lower()


def _normalise_model(model: str) -> str:
    """Lower-case and strip model string for lookup."""
    return model.strip().lower()


def _lookup_printer(brand: str, model: str) -> dict[str, Any] | None:
    """Return the preset dict or None if not found."""
    key = (_normalise_brand(brand), _normalise_model(model))
    return _PRINTER_DB.get(key)


# ---------------------------------------------------------------------------
# 1. printer_preset
# ---------------------------------------------------------------------------

def printer_preset(brand: str, model: str) -> dict[str, Any]:
    """
    Return the build-envelope, layer-height, exposure, and material preset
    for the given printer.

    Parameters
    ----------
    brand : str
        Printer brand.  Case-insensitive.
        Recognised: "Formlabs", "EnvisionTEC", "B9Creations", "Solidscape".
    model : str
        Printer model.  Case-insensitive.
        Recognised: "Form 3B+", "Form 4B", "Micro+", "Ultra",
        "B9 Creator", "B9 Core 530", "S300", "T200".

    Returns
    -------
    dict with keys:
        brand, model, technology, build_envelope_mm (x,y,z tuple),
        xy_resolution_um, layer_height_mm, layer_height_range_mm,
        exposure_s, laser_power_mw, uv_wavelength_nm, uv_post_cure_s,
        supported_materials (list of material keys), min_wall_mm, notes.

    On unknown printer:
        Returns dict with ``error`` key and ``code: "UNKNOWN_PRINTER"``.
    """
    preset = _lookup_printer(brand, model)
    if preset is None:
        known = [f"{v['brand']} {v['model']}" for v in _PRINTER_DB.values()]
        return {
            "error": f"Unknown printer '{brand} {model}'",
            "code": "UNKNOWN_PRINTER",
            "known_printers": sorted(known),
        }
    return dict(preset)


# ---------------------------------------------------------------------------
# 2. recommended_orientation
# ---------------------------------------------------------------------------

def recommended_orientation(
    piece_aabb: tuple[float, float, float, float, float, float],
    anti_stairstepping_axis: str = "top",
) -> dict[str, Any]:
    """
    Recommend the build orientation that minimises layer-line visibility on
    the visible top face of a ring band.

    Parameters
    ----------
    piece_aabb : tuple of 6 floats
        Axis-aligned bounding box: (min_x, min_y, min_z, max_x, max_y, max_z)
        in mm, in the piece's native coordinate system (ring band lying flat,
        band axis along Z, table/crown facing +Y).
    anti_stairstepping_axis : str
        Hint for which face should be kept parallel to the build platform.
        "top"  — minimise layer lines on crown/top of band (default for rings)
        "front" — minimise layer lines on the signet/front face
        "auto"  — pick the axis with the largest span (maximise X-Y area)

    Returns
    -------
    dict with keys:
        recommended_axis       — "X", "Y", or "Z" (print orientation of build axis)
        rotation_deg           — (rx, ry, rz) rotations applied from default orientation
        xy_span_mm             — (width, depth) of the piece in X-Y after rotation
        z_height_mm            — height of the piece in build direction after rotation
        rationale              — human-readable description of the choice
        layer_count_estimate   — z_height_mm / 0.025 mm layers
        anti_stairstepping_axis — input hint echoed back
    """
    min_x, min_y, min_z, max_x, max_y, max_z = piece_aabb
    dx = max_x - min_x
    dy = max_y - min_y
    dz = max_z - min_z

    if dx <= 0 or dy <= 0 or dz <= 0:
        return {
            "error": "piece_aabb has zero or negative span in at least one axis",
            "code": "BAD_AABB",
        }

    axis = anti_stairstepping_axis.strip().lower()

    if axis == "auto":
        # Pick orientation that maximises X-Y projected area
        areas = {
            "X": dy * dz,  # if print axis = X, cross-section = Y×Z
            "Y": dx * dz,  # if print axis = Y, cross-section = X×Z
            "Z": dx * dy,  # if print axis = Z, cross-section = X×Y
        }
        build_axis = max(areas, key=lambda k: areas[k])
    elif axis in ("top", "crown"):
        # For rings: the top-of-band face is the +Y face (in native coords where
        # the band lies horizontal with the crown facing +Y).
        # Orient so this face is parallel to the build plate: print axis = Y.
        # The piece is rotated 90° around X to lay the band flat on the plate.
        build_axis = "Y"
    elif axis in ("front", "signet"):
        # Signet / front face faces +X in native ring coords.
        build_axis = "X"
    else:
        build_axis = "Y"  # Default: minimise on top face

    # Compute resulting geometry after orientation
    if build_axis == "Z":
        xy_span = (dx, dy)
        z_height = dz
        rotation = (0.0, 0.0, 0.0)
        rationale = (
            "Build axis Z: ring stands upright on the platform. "
            "Layer lines run horizontally around the band circumference. "
            "Best for minimising lines on the shank side-walls; "
            "visible top face will show layer steps — use only for round bands."
        )
    elif build_axis == "Y":
        # Rotate 90° around X so +Y points up (becomes build axis)
        xy_span = (dx, dz)
        z_height = dy
        rotation = (90.0, 0.0, 0.0)
        rationale = (
            "Build axis Y: ring lies on its side with the crown-face pointing up. "
            "Layer lines run parallel to the shank length. "
            "Minimises layer-line visibility on the visible top/crown face. "
            "Recommended for solitaire, eternity, and signet rings."
        )
    else:  # X
        xy_span = (dy, dz)
        z_height = dx
        rotation = (0.0, 90.0, 0.0)
        rationale = (
            "Build axis X: ring lies on its back with the signet/front face pointing up. "
            "Minimises layer lines on the front/signet face. "
            "Recommended for signet rings and items with important front-face detail."
        )

    layer_count = int(math.ceil(z_height / 0.025))

    return {
        "recommended_axis": build_axis,
        "rotation_deg": rotation,
        "xy_span_mm": xy_span,
        "z_height_mm": round(z_height, 4),
        "rationale": rationale,
        "layer_count_estimate": layer_count,
        "anti_stairstepping_axis": anti_stairstepping_axis,
    }


# ---------------------------------------------------------------------------
# 3. support_plan
# ---------------------------------------------------------------------------

def support_plan(
    piece_aabb: tuple[float, float, float, float, float, float],
    printer: dict[str, Any],
    contact_diameter_mm: float = 0.4,
    density_pct: float = 20.0,
    exclusion_zones: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Generate a list of support contact points on the underside of the piece.

    Points are placed on a hexagonal grid over the projected underside (X-Y)
    at the given density, then filtered to remove points inside exclusion zones
    (stone seats, prong faces, signet face).

    Parameters
    ----------
    piece_aabb : tuple of 6 floats
        Axis-aligned bounding box (min_x, min_y, min_z, max_x, max_y, max_z).
    printer : dict
        Printer preset dict (from ``printer_preset``).  Used to read
        min_wall_mm for strut sizing.
    contact_diameter_mm : float
        Tip diameter of each support contact point in mm.  Default 0.4 mm.
    density_pct : float
        Approximate percentage coverage of the underside area by support
        contact tips.  20% is a typical starting point for castable resins.
        Range 5–50%.
    exclusion_zones : list of dict, optional
        Each zone: {"cx_mm": float, "cy_mm": float, "radius_mm": float,
                    "label": str}.
        Points inside any zone are excluded (stone seats, prongs, signet face).

    Returns
    -------
    dict with keys:
        contact_diameter_mm  — tip diameter used
        density_pct          — density used
        underside_area_mm2   — projected X-Y area of the piece (mm²)
        support_count        — number of contacts generated
        contacts             — list of {x_mm, y_mm, z_mm, strut_height_mm,
                               strut_diameter_mm, excluded}
        exclusion_zones_used — number of exclusion zones applied
        notes                — guidance string
    """
    min_x, min_y, min_z, max_x, max_y, max_z = piece_aabb

    dx = max_x - min_x
    dy = max_y - min_y
    dz = max_z - min_z

    if dx <= 0 or dy <= 0 or dz <= 0:
        return {
            "error": "piece_aabb has zero or negative span",
            "code": "BAD_AABB",
        }

    if contact_diameter_mm <= 0:
        return {
            "error": "contact_diameter_mm must be positive",
            "code": "BAD_ARGS",
        }

    if not (0 < density_pct <= 100):
        return {
            "error": "density_pct must be in (0, 100]",
            "code": "BAD_ARGS",
        }

    # Strut diameter: 1.5× contact tip, not smaller than min_wall_mm
    min_wall = float(printer.get("min_wall_mm", 0.3))
    strut_dia = max(min_wall, contact_diameter_mm * 1.5)

    # Hexagonal grid pitch from density
    # density_pct ≈ (pi/4 × contact_diameter^2) / (pitch^2 × sqrt(3)/2) × 100
    # → pitch = contact_diameter × sqrt(pi/(2*sqrt(3)*density_pct/100))
    density_frac = density_pct / 100.0
    hex_pitch = contact_diameter_mm * math.sqrt(
        math.pi / (2.0 * math.sqrt(3.0) * density_frac)
    )
    hex_pitch = max(hex_pitch, contact_diameter_mm * 1.1)  # never closer than 110% of tip

    exclusion_zones = exclusion_zones or []

    contacts = []
    row = 0
    y = min_y
    while y <= max_y:
        x_offset = (hex_pitch * 0.5) if (row % 2 == 1) else 0.0
        x = min_x + x_offset
        while x <= max_x:
            # Check exclusion zones
            excluded_by = None
            for zone in exclusion_zones:
                cx = float(zone.get("cx_mm", 0.0))
                cy = float(zone.get("cy_mm", 0.0))
                r = float(zone.get("radius_mm", 0.0))
                label = str(zone.get("label", ""))
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                if dist <= r:
                    excluded_by = label or "exclusion_zone"
                    break

            contact = {
                "x_mm": round(x, 4),
                "y_mm": round(y, 4),
                "z_mm": round(min_z, 4),  # contact point at the bottom face
                "strut_height_mm": round(dz * 0.6, 4),  # struts reach 60% of piece height
                "strut_diameter_mm": round(strut_dia, 4),
                "excluded": excluded_by is not None,
                "excluded_by": excluded_by or "",
            }
            contacts.append(contact)
            x += hex_pitch
        y += hex_pitch * math.sqrt(3.0) / 2.0
        row += 1

    active_contacts = [c for c in contacts if not c["excluded"]]
    underside_area = dx * dy

    return {
        "contact_diameter_mm": contact_diameter_mm,
        "density_pct": density_pct,
        "underside_area_mm2": round(underside_area, 4),
        "support_count": len(active_contacts),
        "contacts": active_contacts,
        "all_candidate_count": len(contacts),
        "exclusion_zones_used": len(exclusion_zones),
        "strut_diameter_mm": round(strut_dia, 4),
        "hex_pitch_mm": round(hex_pitch, 4),
        "notes": (
            f"Hexagonal grid at {density_pct}% density; "
            f"contact tip {contact_diameter_mm} mm; "
            f"strut {strut_dia:.2f} mm; "
            f"{len(exclusion_zones)} exclusion zone(s) applied."
        ),
    }


# ---------------------------------------------------------------------------
# 4. cure_schedule
# ---------------------------------------------------------------------------

def cure_schedule(
    material: str,
    layer_thickness_mm: float,
    printer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return the exposure time per layer and UV post-cure recipe for the given
    material and layer thickness.

    For photopolymer resins the per-layer exposure scales linearly with
    layer thickness relative to the reference thickness in the database.

    For wax-jet materials there is no UV cure; the function returns a
    descriptive support-removal note instead.

    Parameters
    ----------
    material : str
        Material key (from ``_MATERIAL_LABELS`` / ``_CURE_DB``).
        Case-insensitive; spaces and hyphens normalised.
    layer_thickness_mm : float
        Requested layer thickness in mm.  Must be > 0.
    printer : dict, optional
        Printer preset (from ``printer_preset``).  If provided, the function
        cross-checks that the material is compatible with the printer and
        narrows the layer-height range check.

    Returns
    -------
    dict with keys:
        material_key         — normalised material key
        material_label       — human-readable material name
        layer_thickness_mm   — requested layer thickness
        exposure_s_per_layer — computed exposure seconds per layer (None for LFS/wax)
        uv_post_cure_s       — total UV post-cure seconds (None for wax-jet)
        uv_post_cure_temp_c  — cure station temperature (None for wax-jet)
        uv_wavelength_nm     — UV wavelength for post-cure (None for wax-jet)
        is_wax_jet           — True if wax-jet printer material
        notes                — material-specific curing notes
        scaling_note         — describes how exposure was scaled (if applicable)

    On unknown material:
        Returns dict with ``error`` key and ``code: "UNKNOWN_MATERIAL"``.
    """
    mat_key = material.strip().lower().replace(" ", "_").replace("-", "_")
    if mat_key not in _CURE_DB:
        return {
            "error": f"Unknown material '{material}'",
            "code": "UNKNOWN_MATERIAL",
            "known_materials": sorted(_CURE_DB.keys()),
        }

    if layer_thickness_mm <= 0:
        return {
            "error": "layer_thickness_mm must be positive",
            "code": "BAD_ARGS",
        }

    db = _CURE_DB[mat_key]
    is_wax = _MATERIAL_IS_WAX_JET.get(mat_key, False)

    # Scale exposure linearly with layer thickness
    exposure_s: float | None = None
    scaling_note = ""
    if not is_wax and db.get("exposure_s_base") is not None:
        ref_thick = db["reference_layer_mm"]
        scale = layer_thickness_mm / ref_thick
        exposure_s = round(db["exposure_s_base"] * scale, 2)
        scaling_note = (
            f"Scaled from reference {ref_thick} mm "
            f"({db['exposure_s_base']} s) × {scale:.2f} = {exposure_s} s"
        )
    elif not is_wax:
        scaling_note = (
            "LFS printer: exposure controlled by firmware scan speed; "
            "layer thickness set in PreForm slicer."
        )

    # Printer compatibility note
    compat_note = ""
    if printer and not printer.get("error"):
        supported = printer.get("supported_materials", [])
        if supported and mat_key not in supported:
            compat_note = (
                f"WARNING: {mat_key} is not listed as supported by "
                f"{printer.get('brand', '')} {printer.get('model', '')}. "
                "Verify compatibility before use."
            )

    return {
        "material_key": mat_key,
        "material_label": _MATERIAL_LABELS.get(mat_key, mat_key),
        "layer_thickness_mm": layer_thickness_mm,
        "exposure_s_per_layer": exposure_s,
        "uv_post_cure_s": db.get("uv_post_cure_s"),
        "uv_post_cure_temp_c": db.get("uv_post_cure_temp_c"),
        "uv_wavelength_nm": db.get("uv_wavelength_nm"),
        "is_wax_jet": is_wax,
        "notes": db.get("notes", ""),
        "scaling_note": scaling_note,
        "printer_compatibility_note": compat_note,
    }


# ---------------------------------------------------------------------------
# 5. burnout_schedule
# ---------------------------------------------------------------------------

def burnout_schedule(pattern_type: str) -> dict[str, Any]:
    """
    Return the investment-furnace burnout ramp for a castable resin or
    wax-jet wax pattern.

    Parameters
    ----------
    pattern_type : str
        "resin" — castable photopolymer resin (Formlabs, EnvisionTEC, B9)
        "wax"   — wax-jet pattern (Solidscape S300/T200)
        Case-insensitive.

    Returns
    -------
    dict with keys:
        pattern_type  — "resin" or "wax"
        stages        — list of stage dicts, each with:
                          phase, from_c, to_c, rate_c_per_min,
                          duration_min, hold, notes
        total_duration_min — sum of all stage durations
        peak_temp_c        — maximum temperature in the schedule
        notes              — general burnout guidance

    On unknown pattern_type:
        Returns dict with ``error`` key and ``code: "UNKNOWN_PATTERN_TYPE"``.
    """
    ptype = pattern_type.strip().lower()
    if ptype == "resin":
        stages = [dict(s) for s in _BURNOUT_RESIN]
        general_notes = (
            "Castable-resin burnout requires slow ramps to prevent steam cracking "
            "the investment from organic decomposition gases. "
            "Ensure adequate furnace ventilation. "
            "Flask temperature should match alloy-specific casting temperature "
            "before pouring. "
            "Reference: Formlabs Casting Guide 2024; Rankin-Sherwin AJM 2022."
        )
    elif ptype == "wax":
        stages = [dict(s) for s in _BURNOUT_WAX]
        general_notes = (
            "Solidscape wax-jet patterns burn out cleanly with less organic residue "
            "than photopolymer resins. Faster ramps are acceptable. "
            "Ensure support wax has been removed before investing. "
            "Reference: Solidscape Casting Application Note 2022."
        )
    else:
        return {
            "error": f"Unknown pattern_type '{pattern_type}'. Use 'resin' or 'wax'.",
            "code": "UNKNOWN_PATTERN_TYPE",
        }

    total_duration = sum(s["duration_min"] for s in stages)
    peak_temp = max(s["to_c"] for s in stages)

    return {
        "pattern_type": ptype,
        "stages": stages,
        "total_duration_min": total_duration,
        "peak_temp_c": peak_temp,
        "notes": general_notes,
    }


# ---------------------------------------------------------------------------
# LLM tool specs and runners
# ---------------------------------------------------------------------------

# --- 1. jewelry_print_preset -------------------------------------------------

_print_preset_spec = ToolSpec(
    name="jewelry_print_preset",
    description=(
        "Return the build-envelope, layer-height, exposure-time, and supported-material "
        "preset for a castable-resin or wax-jet printer used in jewelry casting.\n\n"
        "Supported printers:\n"
        "  Formlabs Form 3B+ / Form 4B  — LFS; Castable Wax 40 / Blue / Tough\n"
        "  EnvisionTEC Micro+ / Ultra   — DLP; Easy Cast 2.0 / EC500\n"
        "  B9Creations B9 Creator / B9 Core 530 — DLP; B9 Yellow / Blue / Core\n"
        "  Solidscape S300 / T200       — wax-jet; S300/T200 castable wax\n\n"
        "Returns: build_envelope_mm, xy_resolution_um, layer_height_mm, "
        "layer_height_range_mm, exposure_s, laser_power_mw, uv_post_cure_s, "
        "supported_materials, min_wall_mm, technology, notes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "brand": {
                "type": "string",
                "description": (
                    "Printer brand. Case-insensitive. "
                    "E.g. 'Formlabs', 'EnvisionTEC', 'B9Creations', 'Solidscape'."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Printer model. Case-insensitive. "
                    "E.g. 'Form 3B+', 'Form 4B', 'Micro+', 'Ultra', "
                    "'B9 Creator', 'B9 Core 530', 'S300', 'T200'."
                ),
            },
        },
        "required": ["brand", "model"],
    },
)


@register(_print_preset_spec, write=False)
async def run_jewelry_print_preset(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_print_preset."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    brand = a.get("brand")
    model = a.get("model")
    if not brand:
        return err_payload("brand is required", "BAD_ARGS")
    if not model:
        return err_payload("model is required", "BAD_ARGS")

    result = printer_preset(str(brand), str(model))
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# --- 2. jewelry_print_orientation --------------------------------------------

_print_orientation_spec = ToolSpec(
    name="jewelry_print_orientation",
    description=(
        "Recommend the build orientation for a jewelry piece that minimises "
        "layer-line (stair-stepping) visibility on the specified face.\n\n"
        "For a ring: the default places the crown/top face parallel to the build "
        "plate (build axis = Y) so layer lines run along the shank length, "
        "hiding them from the visible top.\n\n"
        "piece_aabb is the axis-aligned bounding box in the piece's native "
        "coordinate system: (min_x, min_y, min_z, max_x, max_y, max_z) in mm.\n\n"
        "anti_stairstepping_axis: 'top' (ring crown, default), 'front' (signet), "
        "'auto' (maximise X-Y projected area).\n\n"
        "Returns: recommended_axis, rotation_deg, xy_span_mm, z_height_mm, "
        "layer_count_estimate, rationale."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece_aabb": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": (
                    "Bounding box [min_x, min_y, min_z, max_x, max_y, max_z] in mm. "
                    "Native ring coords: band axis along Z, crown facing +Y."
                ),
            },
            "anti_stairstepping_axis": {
                "type": "string",
                "description": (
                    "'top' (crown/visible top, default), "
                    "'front' (signet/front face), "
                    "'auto' (maximise X-Y area)."
                ),
            },
        },
        "required": ["piece_aabb"],
    },
)


@register(_print_orientation_spec, write=False)
async def run_jewelry_print_orientation(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_print_orientation."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    aabb_raw = a.get("piece_aabb")
    if aabb_raw is None:
        return err_payload("piece_aabb is required", "BAD_ARGS")
    if not isinstance(aabb_raw, (list, tuple)) or len(aabb_raw) != 6:
        return err_payload("piece_aabb must be a list of 6 numbers", "BAD_ARGS")
    try:
        aabb = tuple(float(v) for v in aabb_raw)
    except (TypeError, ValueError):
        return err_payload("piece_aabb elements must be numbers", "BAD_ARGS")

    axis_hint = str(a.get("anti_stairstepping_axis", "top"))
    result = recommended_orientation(aabb, axis_hint)  # type: ignore[arg-type]
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# --- 3. jewelry_support_plan -------------------------------------------------

_support_plan_spec = ToolSpec(
    name="jewelry_support_plan",
    description=(
        "Generate support contact points for a jewelry piece on a castable-resin "
        "or wax-jet printer.\n\n"
        "Points are placed on a hexagonal grid over the projected underside area "
        "at the given density percentage, then filtered by exclusion zones "
        "(stone seats, prong faces, signet face).\n\n"
        "Returns: support_count, contacts (list of {x,y,z, strut_height, strut_dia}), "
        "underside_area_mm2, notes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece_aabb": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "Bounding box [min_x, min_y, min_z, max_x, max_y, max_z] in mm.",
            },
            "brand": {
                "type": "string",
                "description": "Printer brand for min_wall_mm lookup.",
            },
            "model": {
                "type": "string",
                "description": "Printer model.",
            },
            "contact_diameter_mm": {
                "type": "number",
                "description": "Support tip diameter in mm (default 0.4).",
            },
            "density_pct": {
                "type": "number",
                "description": "Support density as % of underside area (default 20).",
            },
            "exclusion_zones": {
                "type": "array",
                "description": (
                    "Optional list of circular exclusion zones: "
                    "[{cx_mm, cy_mm, radius_mm, label}, ...]."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "cx_mm":     {"type": "number"},
                        "cy_mm":     {"type": "number"},
                        "radius_mm": {"type": "number"},
                        "label":     {"type": "string"},
                    },
                },
            },
        },
        "required": ["piece_aabb", "brand", "model"],
    },
)


@register(_support_plan_spec, write=False)
async def run_jewelry_support_plan(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_support_plan."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    aabb_raw = a.get("piece_aabb")
    if aabb_raw is None:
        return err_payload("piece_aabb is required", "BAD_ARGS")
    if not isinstance(aabb_raw, (list, tuple)) or len(aabb_raw) != 6:
        return err_payload("piece_aabb must be a list of 6 numbers", "BAD_ARGS")
    try:
        aabb = tuple(float(v) for v in aabb_raw)
    except (TypeError, ValueError):
        return err_payload("piece_aabb elements must be numbers", "BAD_ARGS")

    brand = a.get("brand", "")
    model = a.get("model", "")
    if not brand or not model:
        return err_payload("brand and model are required", "BAD_ARGS")

    ppreset = printer_preset(str(brand), str(model))
    if "error" in ppreset:
        return err_payload(ppreset["error"], ppreset.get("code", "ERROR"))

    kwargs: dict[str, Any] = {}
    for field in ("contact_diameter_mm", "density_pct"):
        if field in a:
            try:
                kwargs[field] = float(a[field])
            except (TypeError, ValueError):
                return err_payload(f"{field} must be a number", "BAD_ARGS")

    exclusion_zones = a.get("exclusion_zones")
    if exclusion_zones is not None:
        if not isinstance(exclusion_zones, list):
            return err_payload("exclusion_zones must be an array", "BAD_ARGS")
        kwargs["exclusion_zones"] = exclusion_zones

    result = support_plan(aabb, ppreset, **kwargs)  # type: ignore[arg-type]
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# --- 4. jewelry_cure_schedule ------------------------------------------------

_cure_schedule_spec = ToolSpec(
    name="jewelry_cure_schedule",
    description=(
        "Return the per-layer exposure time and UV post-cure recipe for a "
        "castable resin at a given layer thickness.\n\n"
        "For LFS printers (Formlabs Form 3B+/4B) the per-layer exposure is "
        "controlled by firmware scan speed — this function returns the UV "
        "post-cure parameters instead.\n\n"
        "For DLP printers (EnvisionTEC, B9) per-layer exposure scales linearly "
        "with layer thickness from the reference value in the database.\n\n"
        "Wax-jet printers (Solidscape) have no UV cure; the function returns "
        "wax-removal guidance.\n\n"
        "material: castable_wax_40, castable_wax_resin, castable_blue_resin, "
        "castable_tough_resin, easy_cast_2_0, ec500, b9_yellow, b9_blue, "
        "b9_core_series, solidscape_s300_wax, solidscape_t200_wax.\n\n"
        "Returns: exposure_s_per_layer, uv_post_cure_s, uv_post_cure_temp_c, "
        "uv_wavelength_nm, is_wax_jet, notes, scaling_note."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": "Material key (see tool description for full list).",
            },
            "layer_thickness_mm": {
                "type": "number",
                "description": "Layer thickness in mm (e.g. 0.025, 0.050, 0.100).",
            },
            "brand": {
                "type": "string",
                "description": "Optional: printer brand for compatibility check.",
            },
            "model": {
                "type": "string",
                "description": "Optional: printer model for compatibility check.",
            },
        },
        "required": ["material", "layer_thickness_mm"],
    },
)


@register(_cure_schedule_spec, write=False)
async def run_jewelry_cure_schedule(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_cure_schedule."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    material = a.get("material")
    if not material:
        return err_payload("material is required", "BAD_ARGS")

    layer_mm_raw = a.get("layer_thickness_mm")
    if layer_mm_raw is None:
        return err_payload("layer_thickness_mm is required", "BAD_ARGS")
    try:
        layer_mm = float(layer_mm_raw)
    except (TypeError, ValueError):
        return err_payload("layer_thickness_mm must be a number", "BAD_ARGS")

    # Optional printer for compatibility note
    printer_dict: dict[str, Any] | None = None
    brand = a.get("brand")
    model = a.get("model")
    if brand and model:
        printer_dict = printer_preset(str(brand), str(model))
        if "error" in printer_dict:
            printer_dict = None  # ignore unknown printer; just skip compat note

    result = cure_schedule(str(material), layer_mm, printer=printer_dict)
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# --- 5. jewelry_burnout_schedule ---------------------------------------------

_burnout_schedule_spec = ToolSpec(
    name="jewelry_burnout_schedule",
    description=(
        "Return the investment-furnace burnout temperature ramp for a castable "
        "resin or wax-jet wax pattern.\n\n"
        "pattern_type: 'resin' (Formlabs, EnvisionTEC, B9) or "
        "'wax' (Solidscape S300/T200).\n\n"
        "Resin schedule has 4 stages: warm_up → dewax → preheat → hold.\n"
        "Wax schedule is faster (less organic material).\n\n"
        "Returns: stages (list of phase dicts with from_c, to_c, rate, duration), "
        "total_duration_min, peak_temp_c, notes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern_type": {
                "type": "string",
                "description": "'resin' or 'wax'.",
            },
        },
        "required": ["pattern_type"],
    },
)


@register(_burnout_schedule_spec, write=False)
async def run_jewelry_burnout_schedule(ctx: ProjectCtx, args: bytes) -> str:
    """LLM tool: jewelry_burnout_schedule."""
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    ptype = a.get("pattern_type")
    if not ptype:
        return err_payload("pattern_type is required", "BAD_ARGS")

    result = burnout_schedule(str(ptype))
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)
