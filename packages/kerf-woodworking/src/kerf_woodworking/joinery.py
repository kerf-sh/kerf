"""joinery.py — woodworking joint constructors for Kerf.

Provides parametric constructors for the most common wood-joinery types:

    mortise_tenon   — classic mortise-and-tenon
    dovetail        — through or half-blind dovetail
    finger_joint    — box / finger joint
    dowel           — dowel joint
    biscuit         — plate / biscuit joint
    pocket_screw    — Kreg-style pocket-screw joint

Each constructor returns a plain dict describing the joint geometry and
metadata. All dimensions are in millimetres unless noted.

The returned dict always includes:
    joint_type      — string identifier
    engagement_mm   — the overlap depth (used for volume equality checks)
    volume_mm3      — displaced/engaged volume (mortise == tenon for m&t)
    warnings        — list of GrainWarning dicts (populated by grain.py)
"""

from __future__ import annotations

import math
from typing import Any


def mortise_tenon(
    *,
    tenon_width_mm: float,
    tenon_height_mm: float,
    tenon_depth_mm: float,
    shoulder_gap_mm: float = 0.2,
) -> dict[str, Any]:
    """Return a mortise-and-tenon joint descriptor.

    The mortise is sized to exactly match the tenon (minus the shoulder gap on
    each face), so ``mortise_volume_mm3 == tenon_volume_mm3`` at full
    engagement.

    Args:
        tenon_width_mm:   width of the tenon cheek (the narrow face).
        tenon_height_mm:  height of the tenon shoulder-to-shoulder.
        tenon_depth_mm:   depth the tenon penetrates into the mortise member
                          (the *engagement* dimension).
        shoulder_gap_mm:  clearance subtracted from each cheek face so the
                          tenon fits; defaults to 0.2 mm.
    """
    if tenon_width_mm <= 0 or tenon_height_mm <= 0 or tenon_depth_mm <= 0:
        raise ValueError("tenon dimensions must be positive")
    if shoulder_gap_mm < 0:
        raise ValueError("shoulder_gap_mm must be non-negative")

    tenon_vol = tenon_width_mm * tenon_height_mm * tenon_depth_mm

    # Mortise is carved to accept the tenon: each cheek gets a shoulder_gap
    # clearance on the two width faces only (height and depth are matched).
    mortise_width  = tenon_width_mm  - 2.0 * shoulder_gap_mm
    mortise_height = tenon_height_mm
    mortise_depth  = tenon_depth_mm
    mortise_vol    = mortise_width * mortise_height * mortise_depth

    return {
        "joint_type":       "mortise_tenon",
        "tenon_width_mm":   tenon_width_mm,
        "tenon_height_mm":  tenon_height_mm,
        "tenon_depth_mm":   tenon_depth_mm,
        "shoulder_gap_mm":  shoulder_gap_mm,
        "mortise_width_mm":  mortise_width,
        "mortise_height_mm": mortise_height,
        "mortise_depth_mm":  mortise_depth,
        "engagement_mm":    tenon_depth_mm,
        "tenon_volume_mm3":  tenon_vol,
        "mortise_volume_mm3": mortise_vol,
        # The DoD oracle: volumes are equal when shoulder_gap == 0
        "volume_mm3":       tenon_vol,
        "warnings":         [],
    }


def dovetail(
    *,
    board_thickness_mm: float,
    tail_count: int = 4,
    tail_angle_deg: float = 8.0,
    baseline_offset_mm: float = 3.0,
    half_blind: bool = False,
    lap_mm: float | None = None,
) -> dict[str, Any]:
    """Return a dovetail joint descriptor.

    Args:
        board_thickness_mm:  thickness of the tail board.
        tail_count:          number of tails.
        tail_angle_deg:      dovetail splay angle in degrees (typically 8 for
                             hardwood, 14 for softwood).
        baseline_offset_mm:  distance from the baseline to the board face
                             (controls pin-board socket depth).
        half_blind:          if True, produce a half-blind dovetail leaving a
                             thin front lap.
        lap_mm:              thickness of the front lap (half-blind only);
                             defaults to board_thickness_mm / 4.
    """
    if board_thickness_mm <= 0:
        raise ValueError("board_thickness_mm must be positive")
    if tail_count < 1:
        raise ValueError("tail_count must be >= 1")
    if not (0 < tail_angle_deg < 45):
        raise ValueError("tail_angle_deg must be between 0 and 45")

    if half_blind:
        effective_lap = lap_mm if lap_mm is not None else board_thickness_mm / 4.0
        engagement = board_thickness_mm - effective_lap
    else:
        effective_lap = 0.0
        engagement = board_thickness_mm

    # Approximate tail width at the baseline using the angle
    tail_half_width = baseline_offset_mm * math.tan(math.radians(tail_angle_deg))

    return {
        "joint_type":          "dovetail",
        "board_thickness_mm":  board_thickness_mm,
        "tail_count":          tail_count,
        "tail_angle_deg":      tail_angle_deg,
        "baseline_offset_mm":  baseline_offset_mm,
        "half_blind":          half_blind,
        "lap_mm":              effective_lap,
        "tail_half_width_mm":  tail_half_width,
        "engagement_mm":       engagement,
        # Volume is approximate — useful for relative comparisons
        "volume_mm3":          tail_count * 2.0 * tail_half_width * baseline_offset_mm * board_thickness_mm,
        "warnings":            [],
    }


def finger_joint(
    *,
    board_thickness_mm: float,
    finger_width_mm: float = 10.0,
    kerf_mm: float = 3.175,  # 1/8" router bit
) -> dict[str, Any]:
    """Return a box (finger) joint descriptor.

    Args:
        board_thickness_mm:  thickness of the mating boards.
        finger_width_mm:     width of each finger / slot.
        kerf_mm:             router bit / saw kerf diameter; used to compute
                             the number of fingers that fit.
    """
    if board_thickness_mm <= 0 or finger_width_mm <= 0:
        raise ValueError("dimensions must be positive")
    if kerf_mm < 0:
        raise ValueError("kerf_mm must be non-negative")

    finger_count = max(1, int(board_thickness_mm / (finger_width_mm + kerf_mm)))
    engagement   = finger_width_mm  # fingers engage one full finger width

    return {
        "joint_type":         "finger_joint",
        "board_thickness_mm": board_thickness_mm,
        "finger_width_mm":    finger_width_mm,
        "kerf_mm":            kerf_mm,
        "finger_count":       finger_count,
        "engagement_mm":      engagement,
        "volume_mm3":         finger_count * finger_width_mm * finger_width_mm * board_thickness_mm,
        "warnings":           [],
    }


def dowel(
    *,
    diameter_mm: float = 8.0,
    length_mm: float = 40.0,
    count: int = 2,
    spacing_mm: float | None = None,
) -> dict[str, Any]:
    """Return a dowel joint descriptor.

    Args:
        diameter_mm:  dowel diameter (commonly 6, 8, 10, or 12 mm).
        length_mm:    total dowel length; each board gets length_mm/2
                      engagement.
        count:        number of dowels in the joint.
        spacing_mm:   centre-to-centre spacing between dowels (informational).
    """
    if diameter_mm <= 0 or length_mm <= 0 or count < 1:
        raise ValueError("diameter_mm and length_mm must be positive; count >= 1")

    radius     = diameter_mm / 2.0
    engagement = length_mm / 2.0  # each board's bore depth
    bore_vol   = math.pi * radius ** 2 * engagement

    return {
        "joint_type":   "dowel",
        "diameter_mm":  diameter_mm,
        "length_mm":    length_mm,
        "count":        count,
        "spacing_mm":   spacing_mm,
        "engagement_mm": engagement,
        "bore_volume_mm3": bore_vol,
        "volume_mm3":   count * bore_vol * 2.0,  # total displaced volume both boards
        "warnings":     [],
    }


def biscuit(
    *,
    size: str = "#20",
    count: int = 3,
    spacing_mm: float | None = None,
) -> dict[str, Any]:
    """Return a biscuit (plate) joint descriptor.

    Standard biscuit sizes and their approximate dimensions (mm):
        #0   —  47 × 16 × 4
        #10  —  53 × 19 × 4
        #20  —  56 × 23 × 4  (most common)

    Args:
        size:       biscuit size: "#0", "#10", or "#20".
        count:      number of biscuits in the joint.
        spacing_mm: centre-to-centre spacing (informational).
    """
    _SIZES: dict[str, tuple[float, float, float]] = {
        "#0":  (47.0, 16.0, 4.0),
        "#10": (53.0, 19.0, 4.0),
        "#20": (56.0, 23.0, 4.0),
    }
    if size not in _SIZES:
        raise ValueError(f"unknown biscuit size '{size}'; choose from {list(_SIZES)}")
    if count < 1:
        raise ValueError("count must be >= 1")

    length, width, thickness = _SIZES[size]
    engagement = length / 2.0  # each slot is half the biscuit length
    slot_vol   = engagement * width * thickness

    return {
        "joint_type":       "biscuit",
        "size":             size,
        "biscuit_length_mm": length,
        "biscuit_width_mm":  width,
        "biscuit_thickness_mm": thickness,
        "count":            count,
        "spacing_mm":       spacing_mm,
        "engagement_mm":    engagement,
        "slot_volume_mm3":  slot_vol,
        "volume_mm3":       count * slot_vol * 2.0,
        "warnings":         [],
    }


def pocket_screw(
    *,
    board_thickness_mm: float = 19.0,
    screw_diameter_mm: float = 4.5,
    screw_length_mm: float = 32.0,
    count: int = 2,
    spacing_mm: float | None = None,
) -> dict[str, Any]:
    """Return a pocket-screw joint descriptor.

    Pocket screws (Kreg-style) drill an angled pocket into one board and drive
    through into the face of the mating board.  The engagement depth is the
    length of screw thread that bites into the second board.

    Args:
        board_thickness_mm: thickness of the pocket board.
        screw_diameter_mm:  screw shank diameter (commonly 3.5 or 4.5 mm).
        screw_length_mm:    total screw length.
        count:              number of pocket screws.
        spacing_mm:         centre-to-centre spacing (informational).
    """
    if board_thickness_mm <= 0 or screw_length_mm <= 0 or count < 1:
        raise ValueError("board_thickness_mm and screw_length_mm must be positive; count >= 1")

    # Thread engagement into the second board (excluding the pocket board)
    # Typical pocket angle is ~15°; the effective shank length in board 1 is
    # approximately board_thickness_mm / cos(15°).
    pocket_angle_rad = math.radians(15.0)
    shank_in_board1  = board_thickness_mm / math.cos(pocket_angle_rad)
    engagement       = max(0.0, screw_length_mm - shank_in_board1)

    radius = screw_diameter_mm / 2.0
    pocket_vol = math.pi * radius ** 2 * shank_in_board1

    return {
        "joint_type":          "pocket_screw",
        "board_thickness_mm":  board_thickness_mm,
        "screw_diameter_mm":   screw_diameter_mm,
        "screw_length_mm":     screw_length_mm,
        "pocket_angle_deg":    15.0,
        "count":               count,
        "spacing_mm":          spacing_mm,
        "engagement_mm":       engagement,
        "pocket_volume_mm3":   pocket_vol,
        "volume_mm3":          count * pocket_vol,
        "warnings":            [],
    }
