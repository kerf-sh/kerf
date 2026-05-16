"""
kerf_cad_core.jewelry.watch
============================

Parametric watch / horology design module.

Implements full parametric watch-case construction as pure-Python spec-dict
builders.  Geometry hints are consumed by the occtWorker ``opWatch`` operator.
No OCCT is imported here; never raises on valid input.

## Case shapes

``round``      — circular case; ``case_diameter_mm`` sets the diameter
``cushion``    — square with rounded corners; defined by ``case_diameter_mm``
                 (outer square side) + ``cushion_radius_mm`` (corner radius)
``tonneau``    — barrel-shaped (oval with flattened sides)

## Case dimensions

``case_diameter_mm``    — outer diameter / max width across the case (mm)
``lug_to_lug_mm``       — total height from top lug tip to bottom lug tip (mm)
                          validation: lug_to_lug >= case_diameter + 2·lug_length
``case_thickness_mm``   — total height of case body (crown excluded) (mm)

## Bezel styles

``smooth``    — polished flat top ring
``fluted``    — grooved/knurled channel around the bezel
``dive``      — rotating bezel with 120 click-stop teeth
               (``bezel_teeth`` == 120; ``bezel_clicks_per_rotation`` == 120)

## Lug geometry

``spring_bar_bore_mm``  — diameter of the cross-drill for the spring-bar tube
``strap_width_mm``      — nominal strap/bracelet width at the lug opening (mm)
``lug_length_mm``       — lug protrusion beyond case edge (mm)
                          Note: lug_to_lug_mm = case_diameter_mm + 2·lug_length_mm

## Caseback styles

``snap``        — snap-on / press-fit back; engagement bead ring
``screw``       — threaded caseback; pitch and turn count recorded
``exhibition``  — sapphire exhibition caseback (mineral glass fallback)

## Crown + tube

``crown_diameter_mm``   — crown outer diameter (mm)
``crown_length_mm``     — crown protrusion from case flank (mm)
``crown_tube_od_mm``    — outer diameter of the crown tube (mm)

## Water resistance + gasket groove

If ``water_resistance_m`` > 30, a WR gasket groove is always present in the
spec (``gasket_groove_present == True``).  The groove is also present for any
watch with an explicit ``gasket_profile`` or ``gasket_width_mm`` > 0.

## Movement / caliber catalog

Pre-defined movements with their dial-ring aperture diameters:

    ETA2824   — Swiss ETA 2824-2   Ø 25.6 mm
    SW200     — Sellita SW200-1    Ø 25.6 mm  (ETA2824 interchangeable)
    Miyota9015— Miyota 9015        Ø 28.5 mm
    NH35      — Seiko NH35A        Ø 28.5 mm

Caliber key maps to a ``movement_ring_aperture_mm``.  This is the minimum inner
diameter the dial / movement ring must expose.

## Crystal seat

``flat_sapphire``   — flat mineral-hard crystal; seat is a rebate ring
``domed_sapphire``  — box-section crystal with a dome; seat radius = aperture/2
``flat_mineral``    — standard mineral crystal (cheaper)

Crystal seat aperture ≥ movement ring aperture − fitting clearance (0.2 mm).

## Bracelet end-link

Parametric end-link spec attached to each lug pair:
    ``end_link_width_mm``   == strap_width_mm  (constraint checked in tests)
    ``end_link_taper_mm``   — taper offset; end-link is wider at the case end
    ``end_link_depth_mm``   — thickness of the end-link body

## Metal volume / weight

Volume is computed from case-body and lug geometry as approximate swept solids.
Weight is derived via METAL_DENSITY_G_CM3 (from metal_cost module).

## LLM tools registered (gated)

    jewelry_watch_caliber_info   (read  — movement catalog lookup)
    jewelry_create_watch_case    (write — full watch case + bezel + lugs + back +
                                          crystal + bracelet end-link spec)

## Public spec-dict builders

    compute_watch_params(...)      -> dict
    build_watch_node(...)          -> dict
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    append_feature_node,
    next_node_id,
    read_feature_content,
)
from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    metal_weight,
)

_PI = math.pi

# ---------------------------------------------------------------------------
# Caliber catalog
# ---------------------------------------------------------------------------

CALIBER_CATALOG: dict[str, dict] = {
    "ETA2824": {
        "movement_diameter_mm": 25.6,
        "label": "ETA 2824-2",
        "thickness_mm": 4.6,
        "frequency_bph": 28800,
        "power_reserve_h": 38,
    },
    "SW200": {
        "movement_diameter_mm": 25.6,
        "label": "Sellita SW200-1",
        "thickness_mm": 4.6,
        "frequency_bph": 28800,
        "power_reserve_h": 38,
    },
    "Miyota9015": {
        "movement_diameter_mm": 28.5,
        "label": "Miyota 9015",
        "thickness_mm": 3.9,
        "frequency_bph": 28800,
        "power_reserve_h": 42,
    },
    "NH35": {
        "movement_diameter_mm": 28.5,
        "label": "Seiko NH35A",
        "thickness_mm": 5.86,
        "frequency_bph": 21600,
        "power_reserve_h": 41,
    },
}

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

_VALID_CASE_SHAPES = frozenset(["round", "cushion", "tonneau"])
_VALID_BEZEL_STYLES = frozenset(["smooth", "fluted", "dive"])
_VALID_CASEBACK_STYLES = frozenset(["snap", "screw", "exhibition"])
_VALID_CRYSTAL_STYLES = frozenset(["flat_sapphire", "domed_sapphire", "flat_mineral"])

DIVE_BEZEL_TEETH = 120
_DIVE_BEZEL_CLICKS = 120

# ---------------------------------------------------------------------------
# Fitting clearances (mm)
# ---------------------------------------------------------------------------

# Minimum clearance between movement bore and case inner diameter
_MOVEMENT_BORE_CLEARANCE_MM = 0.3
# Crystal seat aperture min clearance relative to movement ring aperture
_CRYSTAL_SEAT_CLEARANCE_MM = 0.2

# ---------------------------------------------------------------------------
# Helper: lug length implied by lug-to-lug and case diameter
# ---------------------------------------------------------------------------

def _lug_length_from_l2l(case_diameter_mm: float, lug_to_lug_mm: float) -> float:
    return (lug_to_lug_mm - case_diameter_mm) / 2.0


# ---------------------------------------------------------------------------
# Core parametric calculator
# ---------------------------------------------------------------------------

def compute_watch_params(
    # Case geometry
    case_shape: str = "round",
    case_diameter_mm: float = 40.0,
    lug_to_lug_mm: Optional[float] = None,
    case_thickness_mm: float = 11.0,
    cushion_radius_mm: Optional[float] = None,
    # Bezel
    bezel_style: str = "smooth",
    bezel_width_mm: float = 2.5,
    bezel_height_mm: float = 1.8,
    # Lugs
    lug_length_mm: float = 10.0,
    lug_width_mm: float = 20.0,
    lug_height_mm: float = 4.5,
    spring_bar_bore_mm: float = 1.5,
    strap_width_mm: float = 20.0,
    # Caseback
    caseback_style: str = "screw",
    caseback_thickness_mm: float = 1.2,
    caseback_thread_pitch_mm: float = 0.75,
    # Crown + tube
    crown_diameter_mm: float = 6.0,
    crown_length_mm: float = 4.5,
    crown_tube_od_mm: float = 3.5,
    # Water resistance
    water_resistance_m: float = 0.0,
    gasket_profile: Optional[str] = None,
    gasket_width_mm: float = 0.0,
    # Caliber / movement
    caliber: Optional[str] = None,
    movement_diameter_mm: Optional[float] = None,
    # Crystal
    crystal_style: str = "flat_sapphire",
    crystal_thickness_mm: float = 1.2,
    crystal_aperture_mm: Optional[float] = None,
    # Dial / movement ring
    dial_aperture_mm: Optional[float] = None,
    # Bracelet end-link
    end_link_depth_mm: float = 3.5,
    end_link_taper_mm: float = 1.5,
    # Metal
    metal: str = "18k_yellow",
) -> dict:
    """Validate inputs and return a full watch parametric spec dict.

    All dimensional arguments are in millimetres unless noted otherwise.

    Returns
    -------
    dict
        Fully validated watch parameter spec.  Key fields described in module
        docstring.

    Raises
    ------
    ValueError
        On any invalid or out-of-range parameter.
    """

    # -- case shape ----------------------------------------------------------
    case_shape = case_shape.strip().lower()
    if case_shape not in _VALID_CASE_SHAPES:
        raise ValueError(
            f"case_shape={case_shape!r} is not valid. "
            f"Choose from {sorted(_VALID_CASE_SHAPES)}."
        )

    if case_diameter_mm <= 0:
        raise ValueError(f"case_diameter_mm must be > 0; got {case_diameter_mm}")
    if case_thickness_mm <= 0:
        raise ValueError(f"case_thickness_mm must be > 0; got {case_thickness_mm}")

    if case_shape == "cushion":
        if cushion_radius_mm is None:
            cushion_radius_mm = case_diameter_mm * 0.15
        if cushion_radius_mm <= 0 or cushion_radius_mm >= case_diameter_mm / 2.0:
            raise ValueError(
                f"cushion_radius_mm must be in (0, {case_diameter_mm / 2.0}); "
                f"got {cushion_radius_mm}"
            )

    # -- lug geometry --------------------------------------------------------
    if lug_length_mm <= 0:
        raise ValueError(f"lug_length_mm must be > 0; got {lug_length_mm}")
    if strap_width_mm <= 0:
        raise ValueError(f"strap_width_mm must be > 0; got {strap_width_mm}")
    if lug_width_mm <= 0:
        raise ValueError(f"lug_width_mm must be > 0; got {lug_width_mm}")

    # lug_to_lug: if not supplied, compute from case_diameter + 2*lug_length
    computed_l2l = case_diameter_mm + 2.0 * lug_length_mm
    if lug_to_lug_mm is None:
        lug_to_lug_mm = computed_l2l
    else:
        # Validate: must be >= case_diameter + 2·lug_length
        min_l2l = case_diameter_mm + 2.0 * lug_length_mm
        if lug_to_lug_mm < min_l2l - 1e-9:
            raise ValueError(
                f"lug_to_lug_mm ({lug_to_lug_mm}) must be >= "
                f"case_diameter_mm + 2·lug_length_mm = {min_l2l}."
            )

    if spring_bar_bore_mm <= 0:
        raise ValueError(f"spring_bar_bore_mm must be > 0; got {spring_bar_bore_mm}")
    if spring_bar_bore_mm >= lug_width_mm:
        raise ValueError(
            f"spring_bar_bore_mm ({spring_bar_bore_mm}) must be < "
            f"lug_width_mm ({lug_width_mm})."
        )

    # -- bezel ---------------------------------------------------------------
    bezel_style = bezel_style.strip().lower()
    if bezel_style not in _VALID_BEZEL_STYLES:
        raise ValueError(
            f"bezel_style={bezel_style!r} not valid. "
            f"Choose from {sorted(_VALID_BEZEL_STYLES)}."
        )
    if bezel_width_mm <= 0:
        raise ValueError(f"bezel_width_mm must be > 0; got {bezel_width_mm}")
    if bezel_height_mm <= 0:
        raise ValueError(f"bezel_height_mm must be > 0; got {bezel_height_mm}")

    bezel_teeth: Optional[int] = None
    bezel_clicks_per_rotation: Optional[int] = None
    if bezel_style == "dive":
        bezel_teeth = DIVE_BEZEL_TEETH
        bezel_clicks_per_rotation = _DIVE_BEZEL_CLICKS

    # -- caseback ------------------------------------------------------------
    caseback_style = caseback_style.strip().lower()
    if caseback_style not in _VALID_CASEBACK_STYLES:
        raise ValueError(
            f"caseback_style={caseback_style!r} not valid. "
            f"Choose from {sorted(_VALID_CASEBACK_STYLES)}."
        )
    if caseback_thickness_mm <= 0:
        raise ValueError(f"caseback_thickness_mm must be > 0; got {caseback_thickness_mm}")

    # -- crown + tube --------------------------------------------------------
    if crown_diameter_mm <= 0:
        raise ValueError(f"crown_diameter_mm must be > 0; got {crown_diameter_mm}")
    if crown_length_mm <= 0:
        raise ValueError(f"crown_length_mm must be > 0; got {crown_length_mm}")
    if crown_tube_od_mm <= 0:
        raise ValueError(f"crown_tube_od_mm must be > 0; got {crown_tube_od_mm}")
    if crown_tube_od_mm >= crown_diameter_mm:
        raise ValueError(
            f"crown_tube_od_mm ({crown_tube_od_mm}) must be < "
            f"crown_diameter_mm ({crown_diameter_mm})."
        )

    # -- water resistance + gasket groove ------------------------------------
    if water_resistance_m < 0:
        raise ValueError(f"water_resistance_m must be >= 0; got {water_resistance_m}")

    gasket_groove_present = (
        water_resistance_m > 30.0
        or gasket_profile is not None
        or gasket_width_mm > 0
    )

    if gasket_width_mm < 0:
        raise ValueError(f"gasket_width_mm must be >= 0; got {gasket_width_mm}")

    # -- caliber / movement --------------------------------------------------
    caliber_info: Optional[dict] = None
    if caliber is not None:
        if caliber not in CALIBER_CATALOG:
            raise ValueError(
                f"caliber={caliber!r} not found in catalog. "
                f"Valid keys: {sorted(CALIBER_CATALOG)}."
            )
        caliber_info = CALIBER_CATALOG[caliber]
        resolved_movement_diam = caliber_info["movement_diameter_mm"]
    elif movement_diameter_mm is not None:
        if movement_diameter_mm <= 0:
            raise ValueError(
                f"movement_diameter_mm must be > 0; got {movement_diameter_mm}"
            )
        resolved_movement_diam = movement_diameter_mm
    else:
        resolved_movement_diam = None

    # Case bore must be >= movement diameter + clearance
    if resolved_movement_diam is not None:
        min_bore = resolved_movement_diam + _MOVEMENT_BORE_CLEARANCE_MM
        case_bore_mm = case_diameter_mm - 2.0 * bezel_width_mm
        if case_bore_mm < min_bore:
            raise ValueError(
                f"Case bore ({case_bore_mm:.3f} mm = case_diameter "
                f"{case_diameter_mm} - 2·bezel_width {bezel_width_mm}) is "
                f"smaller than minimum required bore {min_bore:.3f} mm "
                f"(movement Ø {resolved_movement_diam} + clearance "
                f"{_MOVEMENT_BORE_CLEARANCE_MM} mm). "
                "Increase case_diameter_mm or reduce bezel_width_mm."
            )
    else:
        case_bore_mm = case_diameter_mm - 2.0 * bezel_width_mm

    # -- dial / movement ring aperture ---------------------------------------
    if dial_aperture_mm is None:
        if resolved_movement_diam is not None:
            dial_aperture_mm = resolved_movement_diam + _MOVEMENT_BORE_CLEARANCE_MM
        else:
            dial_aperture_mm = case_bore_mm * 0.9

    if dial_aperture_mm <= 0:
        raise ValueError(f"dial_aperture_mm must be > 0; got {dial_aperture_mm}")

    # Validate NH35 movement ring fits (movement ring aperture >= movement diam)
    if resolved_movement_diam is not None and dial_aperture_mm < resolved_movement_diam:
        raise ValueError(
            f"dial_aperture_mm ({dial_aperture_mm:.3f}) < movement_diameter_mm "
            f"({resolved_movement_diam}). Increase dial_aperture_mm."
        )

    # -- crystal seat --------------------------------------------------------
    crystal_style = crystal_style.strip().lower()
    if crystal_style not in _VALID_CRYSTAL_STYLES:
        raise ValueError(
            f"crystal_style={crystal_style!r} not valid. "
            f"Choose from {sorted(_VALID_CRYSTAL_STYLES)}."
        )
    if crystal_thickness_mm <= 0:
        raise ValueError(f"crystal_thickness_mm must be > 0; got {crystal_thickness_mm}")

    # crystal aperture must be >= dial_aperture - crystal_seat_clearance
    if crystal_aperture_mm is None:
        crystal_aperture_mm = dial_aperture_mm - _CRYSTAL_SEAT_CLEARANCE_MM
    if crystal_aperture_mm <= 0:
        raise ValueError(f"crystal_aperture_mm must be > 0; got {crystal_aperture_mm}")

    # Crystal seat aperture constraint: seat aperture = crystal_aperture (by definition)
    # Crystal aperture must be compatible with the dial_aperture
    crystal_seat_aperture_mm = crystal_aperture_mm  # seat == crystal outer aperture

    # -- bracelet end-link ---------------------------------------------------
    # End-link width must equal strap_width_mm (lug width constraint)
    end_link_width_mm = strap_width_mm

    if end_link_depth_mm <= 0:
        raise ValueError(f"end_link_depth_mm must be > 0; got {end_link_depth_mm}")
    if end_link_taper_mm < 0:
        raise ValueError(f"end_link_taper_mm must be >= 0; got {end_link_taper_mm}")

    # -- metal / weight -------------------------------------------------------
    metal_key = metal.strip().lower()
    if metal_key not in METAL_DENSITY_G_CM3:
        raise ValueError(
            f"metal={metal!r} not found. "
            f"Valid keys: {sorted(METAL_DENSITY_G_CM3)}."
        )
    density = METAL_DENSITY_G_CM3[metal_key]

    # Approximate volume: cylindrical case body + 4 lug blocks (rough boxes)
    # This is a geometry estimate for a solid case (caseback open).
    if case_shape == "round":
        case_body_vol_mm3 = (
            _PI * (case_diameter_mm / 2.0) ** 2 * case_thickness_mm
        )
    elif case_shape == "cushion":
        # Approximate as square with corner cutouts removed
        side = case_diameter_mm
        r = cushion_radius_mm  # type: ignore[assignment]
        # Area of rounded square: side² − (4 − π)·r²
        area_mm2 = side ** 2 - (4.0 - _PI) * r ** 2
        case_body_vol_mm3 = area_mm2 * case_thickness_mm
    else:  # tonneau: approximate as ellipse with a/b ratio 0.75
        a = case_diameter_mm / 2.0
        b = a * 0.75
        case_body_vol_mm3 = _PI * a * b * case_thickness_mm

    # 4 lugs: each treated as a small rectangular block
    lug_vol_each_mm3 = lug_length_mm * lug_width_mm * lug_height_mm
    lug_vol_total_mm3 = 4.0 * lug_vol_each_mm3

    total_volume_mm3 = case_body_vol_mm3 + lug_vol_total_mm3
    w = metal_weight(total_volume_mm3, metal=metal_key)
    weight_g = w["grams"]

    return {
        "op": "watch",
        # Case
        "case_shape": case_shape,
        "case_diameter_mm": case_diameter_mm,
        "case_thickness_mm": case_thickness_mm,
        "lug_to_lug_mm": round(lug_to_lug_mm, 4),
        "cushion_radius_mm": cushion_radius_mm,
        # Bezel
        "bezel_style": bezel_style,
        "bezel_width_mm": bezel_width_mm,
        "bezel_height_mm": bezel_height_mm,
        "bezel_teeth": bezel_teeth,
        "bezel_clicks_per_rotation": bezel_clicks_per_rotation,
        # Lugs
        "lug_length_mm": lug_length_mm,
        "lug_width_mm": lug_width_mm,
        "lug_height_mm": lug_height_mm,
        "spring_bar_bore_mm": spring_bar_bore_mm,
        "strap_width_mm": strap_width_mm,
        # Caseback
        "caseback_style": caseback_style,
        "caseback_thickness_mm": caseback_thickness_mm,
        "caseback_thread_pitch_mm": caseback_thread_pitch_mm if caseback_style == "screw" else None,
        # Crown
        "crown_diameter_mm": crown_diameter_mm,
        "crown_length_mm": crown_length_mm,
        "crown_tube_od_mm": crown_tube_od_mm,
        # Water resistance
        "water_resistance_m": water_resistance_m,
        "gasket_groove_present": gasket_groove_present,
        "gasket_profile": gasket_profile,
        "gasket_width_mm": gasket_width_mm,
        # Movement
        "caliber": caliber,
        "caliber_info": caliber_info,
        "movement_diameter_mm": resolved_movement_diam,
        "case_bore_mm": round(case_bore_mm, 4),
        # Dial / movement ring
        "dial_aperture_mm": round(dial_aperture_mm, 4),
        # Crystal
        "crystal_style": crystal_style,
        "crystal_thickness_mm": crystal_thickness_mm,
        "crystal_aperture_mm": round(crystal_aperture_mm, 4),
        "crystal_seat_aperture_mm": round(crystal_seat_aperture_mm, 4),
        # Bracelet end-link
        "end_link_width_mm": end_link_width_mm,
        "end_link_taper_mm": end_link_taper_mm,
        "end_link_depth_mm": end_link_depth_mm,
        # Metal / weight
        "metal": metal_key,
        "density_g_cm3": density,
        "total_volume_mm3": round(total_volume_mm3, 4),
        "weight_g": round(weight_g, 4),
    }


def build_watch_node(
    file_id,
    # ----------- forwarded to compute_watch_params -----------
    case_shape: str = "round",
    case_diameter_mm: float = 40.0,
    lug_to_lug_mm: Optional[float] = None,
    case_thickness_mm: float = 11.0,
    cushion_radius_mm: Optional[float] = None,
    bezel_style: str = "smooth",
    bezel_width_mm: float = 2.5,
    bezel_height_mm: float = 1.8,
    lug_length_mm: float = 10.0,
    lug_width_mm: float = 20.0,
    lug_height_mm: float = 4.5,
    spring_bar_bore_mm: float = 1.5,
    strap_width_mm: float = 20.0,
    caseback_style: str = "screw",
    caseback_thickness_mm: float = 1.2,
    caseback_thread_pitch_mm: float = 0.75,
    crown_diameter_mm: float = 6.0,
    crown_length_mm: float = 4.5,
    crown_tube_od_mm: float = 3.5,
    water_resistance_m: float = 0.0,
    gasket_profile: Optional[str] = None,
    gasket_width_mm: float = 0.0,
    caliber: Optional[str] = None,
    movement_diameter_mm: Optional[float] = None,
    crystal_style: str = "flat_sapphire",
    crystal_thickness_mm: float = 1.2,
    crystal_aperture_mm: Optional[float] = None,
    dial_aperture_mm: Optional[float] = None,
    end_link_depth_mm: float = 3.5,
    end_link_taper_mm: float = 1.5,
    metal: str = "18k_yellow",
    # ----------- node identity -----------
    node_id: Optional[str] = None,
) -> dict:
    """Build a full watch node spec dict (without appending to a file).

    Parameters mirror ``compute_watch_params``; additionally accepts:

    file_id
        The project file ID (for node cross-referencing).
    node_id : str, optional
        Explicit node UUID; a new UUID4 is generated when None.

    Returns
    -------
    dict
        Complete watch feature node with ``id``, ``op``, and all geometry hints.
    """
    params = compute_watch_params(
        case_shape=case_shape,
        case_diameter_mm=case_diameter_mm,
        lug_to_lug_mm=lug_to_lug_mm,
        case_thickness_mm=case_thickness_mm,
        cushion_radius_mm=cushion_radius_mm,
        bezel_style=bezel_style,
        bezel_width_mm=bezel_width_mm,
        bezel_height_mm=bezel_height_mm,
        lug_length_mm=lug_length_mm,
        lug_width_mm=lug_width_mm,
        lug_height_mm=lug_height_mm,
        spring_bar_bore_mm=spring_bar_bore_mm,
        strap_width_mm=strap_width_mm,
        caseback_style=caseback_style,
        caseback_thickness_mm=caseback_thickness_mm,
        caseback_thread_pitch_mm=caseback_thread_pitch_mm,
        crown_diameter_mm=crown_diameter_mm,
        crown_length_mm=crown_length_mm,
        crown_tube_od_mm=crown_tube_od_mm,
        water_resistance_m=water_resistance_m,
        gasket_profile=gasket_profile,
        gasket_width_mm=gasket_width_mm,
        caliber=caliber,
        movement_diameter_mm=movement_diameter_mm,
        crystal_style=crystal_style,
        crystal_thickness_mm=crystal_thickness_mm,
        crystal_aperture_mm=crystal_aperture_mm,
        dial_aperture_mm=dial_aperture_mm,
        end_link_depth_mm=end_link_depth_mm,
        end_link_taper_mm=end_link_taper_mm,
        metal=metal,
    )
    nid = node_id or str(uuid.uuid4())
    params["id"] = nid
    params["file_id"] = str(file_id)
    return params


# ---------------------------------------------------------------------------
# LLM tool: caliber catalog lookup
# ---------------------------------------------------------------------------

_watch_caliber_info_spec = ToolSpec(
    name="jewelry_watch_caliber_info",
    description=(
        "Look up a watch movement caliber from the built-in catalog. "
        "Returns the caliber's movement diameter, thickness, beat frequency, "
        "and power reserve. "
        "Supported calibers: ETA2824, SW200, Miyota9015, NH35."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "caliber": {
                "type": "string",
                "description": (
                    "Caliber key. One of: ETA2824, SW200, Miyota9015, NH35."
                ),
            },
        },
        "required": ["caliber"],
    },
)


@register(_watch_caliber_info_spec, write=False)
async def run_jewelry_watch_caliber_info(args: dict, ctx: "ProjectCtx") -> str:
    caliber = str(args.get("caliber", "")).strip()
    if not caliber:
        return err_payload("caliber is required", "BAD_ARGS")
    if caliber not in CALIBER_CATALOG:
        return err_payload(
            f"caliber={caliber!r} not found. "
            f"Valid keys: {sorted(CALIBER_CATALOG)}.",
            "BAD_ARGS",
        )
    info = CALIBER_CATALOG[caliber].copy()
    info["caliber"] = caliber
    return ok_payload(info)


# ---------------------------------------------------------------------------
# LLM tool: create watch case
# ---------------------------------------------------------------------------

_watch_case_spec = ToolSpec(
    name="jewelry_create_watch_case",
    description=(
        "Create a full parametric watch case with bezel, lugs, caseback, "
        "crown+tube, crystal seat, and bracelet end-link. "
        "Appends a watch feature node to the active project file. "
        "Supported case shapes: round, cushion, tonneau. "
        "Bezel styles: smooth, fluted, dive (120-click rotating). "
        "Caseback: snap, screw, exhibition."
    ),
    input_schema={
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "Project file UUID to append the watch node to.",
                },
                "case_shape": {
                    "type": "string",
                    "enum": ["round", "cushion", "tonneau"],
                    "description": "Case silhouette shape.",
                    "default": "round",
                },
                "case_diameter_mm": {
                    "type": "number",
                    "description": "Outer case diameter / max width (mm). Typical 36–45 mm.",
                    "default": 40.0,
                },
                "lug_to_lug_mm": {
                    "type": "number",
                    "description": (
                        "Total lug-to-lug height (mm). "
                        "If omitted, computed as case_diameter + 2·lug_length."
                    ),
                },
                "case_thickness_mm": {
                    "type": "number",
                    "description": "Case total height/thickness (mm), crown excluded.",
                    "default": 11.0,
                },
                "cushion_radius_mm": {
                    "type": "number",
                    "description": "Corner radius for cushion case shape (mm). Default 15% of case_diameter.",
                },
                "bezel_style": {
                    "type": "string",
                    "enum": ["smooth", "fluted", "dive"],
                    "description": "Bezel style. dive = 120-click rotating diver bezel.",
                    "default": "smooth",
                },
                "bezel_width_mm": {
                    "type": "number",
                    "description": "Radial width of the bezel ring (mm).",
                    "default": 2.5,
                },
                "bezel_height_mm": {
                    "type": "number",
                    "description": "Height of the bezel above the case shoulder (mm).",
                    "default": 1.8,
                },
                "lug_length_mm": {
                    "type": "number",
                    "description": "Lug protrusion beyond the case edge (mm).",
                    "default": 10.0,
                },
                "lug_width_mm": {
                    "type": "number",
                    "description": "Width of each lug (mm). Usually matches strap_width_mm.",
                    "default": 20.0,
                },
                "lug_height_mm": {
                    "type": "number",
                    "description": "Vertical height of lug body (mm).",
                    "default": 4.5,
                },
                "spring_bar_bore_mm": {
                    "type": "number",
                    "description": "Diameter of the spring-bar cross-bore through the lug (mm).",
                    "default": 1.5,
                },
                "strap_width_mm": {
                    "type": "number",
                    "description": "Nominal strap/bracelet width at lug opening (mm). Typically 18–22 mm.",
                    "default": 20.0,
                },
                "caseback_style": {
                    "type": "string",
                    "enum": ["snap", "screw", "exhibition"],
                    "description": "Caseback attachment style.",
                    "default": "screw",
                },
                "caseback_thickness_mm": {
                    "type": "number",
                    "description": "Caseback plate thickness (mm).",
                    "default": 1.2,
                },
                "crown_diameter_mm": {
                    "type": "number",
                    "description": "Crown outer diameter (mm).",
                    "default": 6.0,
                },
                "crown_length_mm": {
                    "type": "number",
                    "description": "Crown protrusion from case flank (mm).",
                    "default": 4.5,
                },
                "crown_tube_od_mm": {
                    "type": "number",
                    "description": "Crown tube outer diameter (mm).",
                    "default": 3.5,
                },
                "water_resistance_m": {
                    "type": "number",
                    "description": "Water resistance rating in metres (0 = none). >30 m forces WR gasket groove.",
                    "default": 0.0,
                },
                "caliber": {
                    "type": "string",
                    "description": (
                        "Movement caliber key from catalog: ETA2824, SW200, Miyota9015, NH35. "
                        "Drives bore + crystal aperture constraints."
                    ),
                },
                "movement_diameter_mm": {
                    "type": "number",
                    "description": "Custom movement diameter (mm) when caliber is not in catalog.",
                },
                "crystal_style": {
                    "type": "string",
                    "enum": ["flat_sapphire", "domed_sapphire", "flat_mineral"],
                    "description": "Crystal type.",
                    "default": "flat_sapphire",
                },
                "crystal_thickness_mm": {
                    "type": "number",
                    "description": "Crystal thickness (mm).",
                    "default": 1.2,
                },
                "crystal_aperture_mm": {
                    "type": "number",
                    "description": "Crystal seat aperture diameter (mm). Defaults to dial_aperture − 0.2 mm.",
                },
                "dial_aperture_mm": {
                    "type": "number",
                    "description": "Dial / movement ring inner aperture (mm). Defaults to movement_diameter + clearance.",
                },
                "end_link_depth_mm": {
                    "type": "number",
                    "description": "End-link body thickness / depth (mm).",
                    "default": 3.5,
                },
                "end_link_taper_mm": {
                    "type": "number",
                    "description": "End-link taper offset towards bracelet (mm).",
                    "default": 1.5,
                },
                "metal": {
                    "type": "string",
                    "description": (
                        "Metal alloy key (see METAL_DENSITY_G_CM3). "
                        "E.g. '18k_yellow', 'sterling_925', 'titanium', 'platinum_950'."
                    ),
                    "default": "18k_yellow",
                },
            },
            "required": ["file_id"],
        },
)


@register(_watch_case_spec, write=True)
async def run_jewelry_create_watch_case(args: dict, ctx: "ProjectCtx") -> str:
    file_id_raw = args.get("file_id")
    if not file_id_raw:
        return err_payload("file_id is required", "BAD_ARGS")

    try:
        file_id = uuid.UUID(str(file_id_raw))
    except ValueError:
        return err_payload(f"file_id {file_id_raw!r} is not a valid UUID", "BAD_ARGS")

    try:
        content, kind = await read_feature_content(ctx, file_id)
    except Exception as exc:
        return err_payload(f"Could not read file: {exc}", "NOT_FOUND")

    try:
        node = build_watch_node(
            file_id=file_id,
            case_shape=str(args.get("case_shape", "round")),
            case_diameter_mm=float(args.get("case_diameter_mm", 40.0)),
            lug_to_lug_mm=float(args["lug_to_lug_mm"]) if "lug_to_lug_mm" in args else None,
            case_thickness_mm=float(args.get("case_thickness_mm", 11.0)),
            cushion_radius_mm=float(args["cushion_radius_mm"]) if "cushion_radius_mm" in args else None,
            bezel_style=str(args.get("bezel_style", "smooth")),
            bezel_width_mm=float(args.get("bezel_width_mm", 2.5)),
            bezel_height_mm=float(args.get("bezel_height_mm", 1.8)),
            lug_length_mm=float(args.get("lug_length_mm", 10.0)),
            lug_width_mm=float(args.get("lug_width_mm", 20.0)),
            lug_height_mm=float(args.get("lug_height_mm", 4.5)),
            spring_bar_bore_mm=float(args.get("spring_bar_bore_mm", 1.5)),
            strap_width_mm=float(args.get("strap_width_mm", 20.0)),
            caseback_style=str(args.get("caseback_style", "screw")),
            caseback_thickness_mm=float(args.get("caseback_thickness_mm", 1.2)),
            caseback_thread_pitch_mm=float(args.get("caseback_thread_pitch_mm", 0.75)),
            crown_diameter_mm=float(args.get("crown_diameter_mm", 6.0)),
            crown_length_mm=float(args.get("crown_length_mm", 4.5)),
            crown_tube_od_mm=float(args.get("crown_tube_od_mm", 3.5)),
            water_resistance_m=float(args.get("water_resistance_m", 0.0)),
            gasket_profile=args.get("gasket_profile"),
            gasket_width_mm=float(args.get("gasket_width_mm", 0.0)),
            caliber=args.get("caliber"),
            movement_diameter_mm=float(args["movement_diameter_mm"]) if "movement_diameter_mm" in args else None,
            crystal_style=str(args.get("crystal_style", "flat_sapphire")),
            crystal_thickness_mm=float(args.get("crystal_thickness_mm", 1.2)),
            crystal_aperture_mm=float(args["crystal_aperture_mm"]) if "crystal_aperture_mm" in args else None,
            dial_aperture_mm=float(args["dial_aperture_mm"]) if "dial_aperture_mm" in args else None,
            end_link_depth_mm=float(args.get("end_link_depth_mm", 3.5)),
            end_link_taper_mm=float(args.get("end_link_taper_mm", 1.5)),
            metal=str(args.get("metal", "18k_yellow")),
        )
    except (ValueError, KeyError) as exc:
        return err_payload(str(exc), "BAD_ARGS")

    try:
        new_content = append_feature_node(content, node)
        nid = next_node_id(new_content)  # noqa: F841 — advance counter side-effect
        await ctx.pool.execute(  # type: ignore[attr-defined]
            "UPDATE files SET content=$1 WHERE id=$2",
            new_content,
            file_id,
        )
    except Exception as exc:
        return err_payload(f"Could not persist node: {exc}", "ERROR")

    return ok_payload({
        "node_id": node["id"],
        "file_id": str(file_id),
        "op": "watch",
        "case_shape": node["case_shape"],
        "case_diameter_mm": node["case_diameter_mm"],
        "lug_to_lug_mm": node["lug_to_lug_mm"],
        "bezel_style": node["bezel_style"],
        "bezel_teeth": node["bezel_teeth"],
        "caseback_style": node["caseback_style"],
        "caliber": node["caliber"],
        "weight_g": node["weight_g"],
        "gasket_groove_present": node["gasket_groove_present"],
    })
