"""
kerf_bim.openings — Parametric door and window openings hosted in walls.

Public API
----------
  JambProfile(width, depth)
      2-D section of a door or window jamb / frame.

  Door(host_wall, position_along, width, height, *, family)
      Parametric door that cuts a rectangular void in its host wall and
      places a jamb + swing geometry.

  Window(host_wall, position_along, width, height, *, sill_height, family)
      Parametric window that cuts a rectangular void + places a glazing
      frame in its host wall.

Each opening registers itself with its host wall on creation.

References
----------
Revit Architecture 2024 — Door and Window family definitions.
ISO 16739-1:2018 (IFC4) — IfcDoor, IfcWindow, IfcOpeningElement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from kerf_bim.envelope import Wall, SectionProfile, Point2D


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_positive(name: str, value: float) -> None:
    if value <= 0.0:
        raise ValueError(f"{name} must be > 0; got {value}")


def _check_non_negative(name: str, value: float) -> None:
    if value < 0.0:
        raise ValueError(f"{name} must be ≥ 0; got {value}")


# ---------------------------------------------------------------------------
# JambProfile
# ---------------------------------------------------------------------------

@dataclass
class JambProfile:
    """2-D section profile of a door or window jamb / frame.

    Parameters
    ----------
    width : float
        Width of the jamb in metres (measured perpendicular to the wall face).
    depth : float
        Depth of the jamb in metres (measured along the wall thickness).
    """

    width: float
    depth: float

    def __post_init__(self) -> None:
        _check_positive("JambProfile.width", self.width)
        _check_positive("JambProfile.depth", self.depth)

    def section_area(self) -> float:
        """Cross-section area of the jamb in m²."""
        return self.width * self.depth

    def as_section_profile(self) -> SectionProfile:
        """Return the 2-D section polygon of the jamb."""
        verts = [
            (0.0, 0.0),
            (self.depth, 0.0),
            (self.depth, self.width),
            (0.0, self.width),
        ]
        return SectionProfile(vertices=verts)


# ---------------------------------------------------------------------------
# Door
# ---------------------------------------------------------------------------

@dataclass
class Door:
    """Parametric door opening hosted in a ``Wall``.

    The door cuts a rectangular void of width × height through the full
    thickness of the host wall and places a jamb at the opening perimeter.

    Parameters
    ----------
    host_wall : Wall
        The ``Wall`` instance that hosts this door.
    position_along : float
        Distance from ``host_wall.start`` to the door centreline along the
        wall length, in metres.  Must be in (0, wall_length).
    width : float
        Clear opening width in metres.
    height : float
        Clear opening height in metres.
    family : str
        Door family / type name.  Defaults to ``"single_flush"``.
    jamb_thickness : float
        Thickness of the door jamb (frame) in metres.  Defaults to ``0.05``.
    swing_angle : float
        Angle in degrees to which the door leaf swings open.
        Defaults to ``90.0``.

    Notes
    -----
    The door automatically registers itself with ``host_wall`` via
    ``host_wall.add_opening(self)``.
    """

    host_wall: Wall
    position_along: float
    width: float
    height: float
    family: str = "single_flush"
    jamb_thickness: float = 0.05
    swing_angle: float = 90.0

    def __post_init__(self) -> None:
        wall_len = self.host_wall.length()
        _check_positive("Door.width", self.width)
        _check_positive("Door.height", self.height)
        _check_positive("Door.jamb_thickness", self.jamb_thickness)
        if self.position_along <= 0.0 or self.position_along >= wall_len:
            raise ValueError(
                f"Door position_along ({self.position_along:.4f}) must be "
                f"in (0, wall_length={wall_len:.4f})"
            )
        half = self.width / 2.0
        if (self.position_along - half) < 0.0 or (self.position_along + half) > wall_len:
            raise ValueError(
                f"Door (width={self.width}) extends outside host wall "
                f"(length={wall_len:.4f}) at position {self.position_along:.4f}"
            )
        if self.height > self.host_wall.height:
            raise ValueError(
                f"Door height ({self.height}) exceeds wall height "
                f"({self.host_wall.height})"
            )
        # Register with host wall
        self.host_wall.add_opening(self)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def cut_volume(self) -> float:
        """Volume of wall material removed by this door opening.

        The void is a rectangular prism: width × height × wall_thickness.
        """
        return self.width * self.height * self.host_wall.thickness

    def jamb_profile(self) -> JambProfile:
        """Return the jamb cross-section profile."""
        return JambProfile(width=self.jamb_thickness, depth=self.host_wall.thickness)

    def section_profile(self) -> SectionProfile:
        """2-D section of the door opening (in the wall plane).

        Profile is the rectangular void in (u, z) space where u is the
        position across the wall thickness (0 = exterior, thickness = interior)
        and z is height.
        """
        t = self.host_wall.thickness
        verts = [
            (0.0, 0.0),
            (t, 0.0),
            (t, self.height),
            (0.0, self.height),
        ]
        return SectionProfile(vertices=verts)

    def swing_geometry(self) -> List[Tuple[float, float]]:
        """Return (x, y) points of the door swing arc in the wall plan.

        The arc originates at the hinge point and sweeps *swing_angle*
        degrees.  Points are in 2-D wall-local coordinates where x is
        along the wall and y is across the wall thickness.

        Returns a list of (x, y) tuples approximating the arc with 32 segments.
        """
        n_seg = 32
        hinge_x = self.position_along - self.width / 2.0  # hinge at leading edge
        hinge_y = 0.0  # exterior face
        radius = self.width
        pts: List[Tuple[float, float]] = [(hinge_x, hinge_y)]
        for i in range(n_seg + 1):
            angle_rad = math.radians(self.swing_angle * i / n_seg)
            x = hinge_x + radius * math.cos(angle_rad)
            y = hinge_y + radius * math.sin(angle_rad)
            pts.append((x, y))
        return pts


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

@dataclass
class Window:
    """Parametric window opening hosted in a ``Wall``.

    The window cuts a rectangular void of width × height through the full
    thickness of the host wall at a given sill height, and places a
    glazing frame.

    Parameters
    ----------
    host_wall : Wall
        The ``Wall`` instance that hosts this window.
    position_along : float
        Distance from ``host_wall.start`` to the window centreline, metres.
    width : float
        Clear opening width in metres.
    height : float
        Clear opening height in metres.
    sill_height : float
        Height of the bottom of the opening above the base of the wall,
        in metres.  Defaults to ``0.9`` (standard residential sill height).
    family : str
        Window family / type name.  Defaults to ``"casement_single"``.
    frame_thickness : float
        Frame (jamb) thickness in metres.  Defaults to ``0.06``.
    glazing_material : str
        Glazing material name.  Defaults to ``"glass_annealed_float"``.

    Notes
    -----
    The window automatically registers itself with ``host_wall`` via
    ``host_wall.add_opening(self)``.
    """

    host_wall: Wall
    position_along: float
    width: float
    height: float
    sill_height: float = 0.9
    family: str = "casement_single"
    frame_thickness: float = 0.06
    glazing_material: str = "glass_annealed_float"

    def __post_init__(self) -> None:
        wall_len = self.host_wall.length()
        _check_positive("Window.width", self.width)
        _check_positive("Window.height", self.height)
        _check_non_negative("Window.sill_height", self.sill_height)
        _check_positive("Window.frame_thickness", self.frame_thickness)
        if self.position_along <= 0.0 or self.position_along >= wall_len:
            raise ValueError(
                f"Window position_along ({self.position_along:.4f}) must be "
                f"in (0, wall_length={wall_len:.4f})"
            )
        half = self.width / 2.0
        if (self.position_along - half) < 0.0 or (self.position_along + half) > wall_len:
            raise ValueError(
                f"Window (width={self.width}) extends outside host wall "
                f"(length={wall_len:.4f}) at position {self.position_along:.4f}"
            )
        top = self.sill_height + self.height
        if top > self.host_wall.height:
            raise ValueError(
                f"Window top ({top}) exceeds wall height ({self.host_wall.height})"
            )
        # Register with host wall
        self.host_wall.add_opening(self)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def cut_volume(self) -> float:
        """Volume of wall material removed by this window opening.

        The void is a rectangular prism: width × height × wall_thickness.
        """
        return self.width * self.height * self.host_wall.thickness

    def head_height(self) -> float:
        """Height of the top of the window opening above the wall base."""
        return self.sill_height + self.height

    def glazing_area(self) -> float:
        """Visible glazing area (inside frame) in m².

        Reduced by the frame on all four edges.
        """
        clear_w = max(0.0, self.width - 2.0 * self.frame_thickness)
        clear_h = max(0.0, self.height - 2.0 * self.frame_thickness)
        return clear_w * clear_h

    def frame_profile(self) -> JambProfile:
        """Return the window frame cross-section."""
        return JambProfile(
            width=self.frame_thickness,
            depth=self.host_wall.thickness,
        )

    def section_profile(self) -> SectionProfile:
        """2-D section of the window void in (u, z) space.

        u spans the wall thickness (exterior=0, interior=thickness).
        z is height above wall base.
        """
        t = self.host_wall.thickness
        z0 = self.sill_height
        z1 = z0 + self.height
        verts = [
            (0.0, z0),
            (t, z0),
            (t, z1),
            (0.0, z1),
        ]
        return SectionProfile(vertices=verts)
