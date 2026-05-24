"""Swiss-lever escapement geometry.

The Swiss lever escapement is the dominant mechanical watch escapement.
This module derives the key geometric parameters from first principles:

  - Pallet angles (entry / exit)
  - Draw angle  — locking-face inclination that keeps the pallet locked
                  under escape-wheel tooth pressure (typically 10°-14°).
  - Lift angle  — total angular sweep of the lever during impulse
                  (typically 8°-12°; half is delivered by each pallet stone).
  - Impulse force at the balance pivot.
  - Drop        — free travel of the escape wheel between tooth release and
                  the next locking face (energy lost per beat).

Public API
----------
swiss_lever_geometry(escape_teeth, lift_deg, draw_deg,
                     escape_wheel_radius_mm, lever_arm_mm,
                     escape_wheel_torque_Nmm)
    → SwissLeverGeometry  (dataclass, all floats in mm / degrees / N·mm)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class SwissLeverGeometry:
    """Derived geometry for a Swiss lever escapement.

    All angles in degrees.  Forces in mN (milli-Newtons).
    Lengths in mm.  Torques in N·mm.

    Attributes
    ----------
    escape_teeth : int
        Number of teeth on the escape wheel.
    lift_deg : float
        Total lever lift angle (degrees).
    draw_deg : float
        Draw angle on each locking face (degrees).
    escape_wheel_radius_mm : float
        Pitch-circle radius of the escape wheel (mm).
    lever_arm_mm : float
        Distance from pallet pivot to pallet stone impulse point (mm).
    escape_wheel_torque_Nmm : float
        Torque applied to the escape-wheel arbor (N·mm).

    Derived
    -------
    tooth_pitch_deg : float
        Angular pitch between adjacent teeth (360 / escape_teeth).
    entry_pallet_angle_deg : float
        Angular position of the entry pallet stone centre relative to
        the escape-wheel arbor (half the tooth pitch beyond vertical).
    exit_pallet_angle_deg : float
        Angular position of the exit pallet stone (symmetric).
    half_lift_deg : float
        Lift angle contributed by each pallet stone (lift_deg / 2).
    impulse_face_angle_deg : float
        Angle of the impulse face of each pallet stone (equal to
        half_lift_deg for a symmetric Swiss lever).
    drop_deg : float
        Drop angle per side — angular freedom the escape wheel gains
        between tooth release and the next locking engagement.
        Estimated as tooth_pitch_deg/2 − half_lift_deg.
    impulse_force_at_balance_mN : float
        Tangential force delivered to the balance roller jewel,
        derived from escape_wheel_torque / escape_wheel_radius
        scaled by lever geometry (lever_arm / lever_arm = 1 here,
        since we give the force at the pallet stone).
    energy_per_impulse_uJ : float
        Energy delivered to the balance per half-beat (micro-joules).
        ≈ impulse_force × arc_length_of_pallet_stone_during_lift.
    consistency_errors : list[str]
        Empty list if the geometry is self-consistent.  Contains
        human-readable error strings otherwise.
    """

    # --- inputs ---
    escape_teeth: int
    lift_deg: float
    draw_deg: float
    escape_wheel_radius_mm: float
    lever_arm_mm: float
    escape_wheel_torque_Nmm: float

    # --- derived (computed in __post_init__) ---
    tooth_pitch_deg: float = field(init=False)
    entry_pallet_angle_deg: float = field(init=False)
    exit_pallet_angle_deg: float = field(init=False)
    half_lift_deg: float = field(init=False)
    impulse_face_angle_deg: float = field(init=False)
    drop_deg: float = field(init=False)
    impulse_force_at_balance_mN: float = field(init=False)
    energy_per_impulse_uJ: float = field(init=False)
    consistency_errors: List[str] = field(init=False)

    def __post_init__(self) -> None:
        self.tooth_pitch_deg = 360.0 / self.escape_teeth
        self.half_lift_deg = self.lift_deg / 2.0
        self.impulse_face_angle_deg = self.half_lift_deg

        # Pallet centre angles (symmetric about 0 — entry left, exit right)
        self.entry_pallet_angle_deg = -(self.tooth_pitch_deg / 2.0)
        self.exit_pallet_angle_deg = self.tooth_pitch_deg / 2.0

        # Drop: the tooth sweeps tooth_pitch_deg per cycle; half per side.
        # The pallet stone occupies half_lift_deg of that arc.
        # Remaining: drop per side.
        self.drop_deg = (self.tooth_pitch_deg / 2.0) - self.half_lift_deg

        # Impulse force at the pallet stone (N → mN)
        # F_tooth = torque / R_wheel   (tangential force at escape wheel tip)
        # The pallet stone receives this force orthogonally during impulse.
        # Force at balance roller = F_tooth × (R_wheel / lever_arm)
        # But the standard approximation for the impulse stone is:
        #   F_impulse = torque / lever_arm
        self.impulse_force_at_balance_mN = (
            self.escape_wheel_torque_Nmm / self.lever_arm_mm * 1000.0
        )

        # Arc length swept by pallet stone during half lift
        arc_mm = self.lever_arm_mm * math.radians(self.half_lift_deg)
        # Energy = force × distance  (micro-joules = mN × mm × 1e-3? No:
        #   mN × mm = 1e-3 N × 1e-3 m = 1e-6 J = 1 µJ  ✓)
        self.energy_per_impulse_uJ = self.impulse_force_at_balance_mN * arc_mm

        # --- self-consistency checks ---
        errors: List[str] = []

        if not (6 <= self.escape_teeth <= 30):
            errors.append(
                f"escape_teeth={self.escape_teeth} outside typical range 6..30"
            )
        if not (6.0 <= self.lift_deg <= 16.0):
            errors.append(
                f"lift_deg={self.lift_deg} outside typical range 6°..16°"
            )
        if not (8.0 <= self.draw_deg <= 16.0):
            errors.append(
                f"draw_deg={self.draw_deg} outside typical range 8°..16°"
            )
        if self.drop_deg < 0:
            errors.append(
                f"drop_deg={self.drop_deg:.3f}° is negative — "
                "lift angle exceeds half tooth pitch (gear would lock)"
            )
        if self.drop_deg > self.tooth_pitch_deg * 0.4:
            errors.append(
                f"drop_deg={self.drop_deg:.3f}° > 40% of tooth pitch — "
                "excessive energy loss"
            )
        if self.escape_wheel_radius_mm <= 0:
            errors.append("escape_wheel_radius_mm must be positive")
        if self.lever_arm_mm <= 0:
            errors.append("lever_arm_mm must be positive")
        if self.escape_wheel_torque_Nmm <= 0:
            errors.append("escape_wheel_torque_Nmm must be positive")

        self.consistency_errors = errors

    @property
    def is_consistent(self) -> bool:
        """True when all self-consistency checks pass."""
        return len(self.consistency_errors) == 0


def swiss_lever_geometry(
    escape_teeth: int = 15,
    lift_deg: float = 8.0,
    draw_deg: float = 12.0,
    escape_wheel_radius_mm: float = 1.925,
    lever_arm_mm: float = 1.6,
    escape_wheel_torque_Nmm: float = 0.35,
) -> SwissLeverGeometry:
    """Compute Swiss lever escapement geometry and return a self-describing dataclass.

    Parameters
    ----------
    escape_teeth : int
        Number of teeth on the escape wheel (default 15, Swiss standard).
    lift_deg : float
        Total lever lift angle in degrees (default 8°).  Each pallet stone
        delivers half this lift.
    draw_deg : float
        Draw angle — inclination of the locking face that keeps the pallet
        safely locked under tooth pressure (default 12°).
    escape_wheel_radius_mm : float
        Pitch-circle radius of the escape wheel in mm.
        Default 1.925 mm ≈ 7¾ liga (OD 3.85 mm / 2).
    lever_arm_mm : float
        Distance from the pallet fork pivot to the centre of the pallet stone
        impulse face (mm).  Default 1.6 mm.
    escape_wheel_torque_Nmm : float
        Torque delivered to the escape-wheel arbor by the gear train (N·mm).
        Default 0.35 N·mm — a typical wristwatch value.

    Returns
    -------
    SwissLeverGeometry
        Fully derived geometry.  Check `.is_consistent` and
        `.consistency_errors` for validation results.

    Notes
    -----
    The draw angle is a *design parameter* on the locking face; it does not
    directly appear in the force/energy calculations but is validated to
    confirm it lies within the range that prevents kick-back (too low) and
    excessive locking friction (too high).

    The half-lift impulse face angle equals half_lift_deg for a symmetric
    Swiss lever.  Asymmetric designs exist (e.g. club-tooth) but are outside
    the scope of this function.
    """
    return SwissLeverGeometry(
        escape_teeth=escape_teeth,
        lift_deg=lift_deg,
        draw_deg=draw_deg,
        escape_wheel_radius_mm=escape_wheel_radius_mm,
        lever_arm_mm=lever_arm_mm,
        escape_wheel_torque_Nmm=escape_wheel_torque_Nmm,
    )
