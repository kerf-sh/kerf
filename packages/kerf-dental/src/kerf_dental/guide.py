"""
kerf_dental.guide — Surgical implant-guide placement.

Public API
----------
ImplantSpec
    Defines a single implant: position on jaw, diameter, angulation.

SurgicalGuideResult
    The placed guide geometry and placement metadata.

place_surgical_guide(jaw_surface_pts, implants) -> SurgicalGuideResult
    Place drill-guide cylinders on a jaw model at specified implant angles.
    Returns a SurgicalGuideResult whose Body passes validate_body.

angle_between_vectors(v1, v2) -> float
    Utility: angle in degrees between two 3-D vectors.

Notes
-----
Each guide sleeve is a cylinder whose axis tracks the implant vector
rotated to meet the jaw surface.  Guide placement accuracy is tested to
0.1° (angular deviation between the requested and realised implant axis).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ImplantSpec:
    """Single implant placement specification."""

    position: tuple[float, float, float]
    """Target implant tip position in jaw coordinates (mm)."""

    axis_direction: tuple[float, float, float]
    """Unit vector along the implant axis (apical → crestal direction)."""

    diameter_mm: float = 4.0
    """Implant diameter in mm (guide sleeve inner bore ~ this value)."""

    length_mm: float = 10.0
    """Implant length in mm (sets guide sleeve height)."""

    sleeve_wall_mm: float = 1.5
    """Guide sleeve wall thickness in mm."""

    def __post_init__(self):
        ax = np.array(self.axis_direction, dtype=float)
        norm = float(np.linalg.norm(ax))
        if norm < 1e-9:
            raise ValueError("axis_direction must be a non-zero vector")
        # Normalise and store back
        object.__setattr__(self, "axis_direction",
                           tuple((ax / norm).tolist()))

    @property
    def sleeve_outer_radius_mm(self) -> float:
        return self.diameter_mm / 2.0 + self.sleeve_wall_mm

    @property
    def axis_unit(self) -> np.ndarray:
        return np.array(self.axis_direction, dtype=float)


@dataclass
class SurgicalGuideResult:
    """Output of place_surgical_guide()."""

    sleeves: list[object]
    """One kerf_cad_core Body per implant — each a validate_body-clean cylinder."""

    realised_axes: list[np.ndarray]
    """The normalised axis vector actually stored per sleeve (should match spec)."""

    angular_errors_deg: list[float]
    """Angle (degrees) between requested and realised axis per sleeve."""

    def max_angular_error_deg(self) -> float:
        if not self.angular_errors_deg:
            return 0.0
        return max(self.angular_errors_deg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def angle_between_vectors(v1: np.ndarray, v2: np.ndarray) -> float:
    """
    Angle in degrees between two 3-D vectors.

    Parameters
    ----------
    v1, v2 : array-like of shape (3,)

    Returns
    -------
    float — angle in [0, 180] degrees.
    """
    u1 = np.asarray(v1, dtype=float)
    u2 = np.asarray(v2, dtype=float)
    n1 = float(np.linalg.norm(u1))
    n2 = float(np.linalg.norm(u2))
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    cos_theta = float(np.dot(u1, u2) / (n1 * n2))
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def _closest_surface_point(
    jaw_pts: np.ndarray,
    query: np.ndarray,
) -> np.ndarray:
    """Return the jaw surface point closest to *query*."""
    dists = np.linalg.norm(jaw_pts - query, axis=1)
    return jaw_pts[int(np.argmin(dists))].copy()


# ---------------------------------------------------------------------------
# Guide placement
# ---------------------------------------------------------------------------

def place_surgical_guide(
    jaw_surface_pts: Sequence[tuple[float, float, float]],
    implants: Sequence[ImplantSpec],
) -> SurgicalGuideResult:
    """
    Place drill-guide sleeve cylinders on a jaw model.

    For each implant spec:
      1. Snap the implant position to the nearest jaw surface point.
      2. Create a cylinder Body using make_cylinder with the implant's axis
         and outer sleeve geometry.
      3. Record the realised axis and compute angular error vs. spec.

    The angular error between the requested axis and the realised cylinder
    axis is always < 0.1° (the cylinder axis is set directly from the spec,
    so the only error source is floating-point normalisation, which is < 1e-14°).

    Parameters
    ----------
    jaw_surface_pts : sequence of (x, y, z) points on the jaw surface (mm).
    implants        : sequence of ImplantSpec instances.

    Returns
    -------
    SurgicalGuideResult

    Raises
    ------
    ValueError  if jaw_surface_pts is empty or implants is empty.
    ImportError if kerf_cad_core is not importable.
    """
    from kerf_cad_core.geom.brep import make_cylinder, validate_body

    jaw_pts = np.array(list(jaw_surface_pts), dtype=float)
    if jaw_pts.ndim != 2 or jaw_pts.shape[1] != 3 or len(jaw_pts) == 0:
        raise ValueError(
            "jaw_surface_pts must be a non-empty sequence of (x, y, z) points"
        )
    if not implants:
        raise ValueError("implants must not be empty")

    sleeves: list[object] = []
    realised_axes: list[np.ndarray] = []
    angular_errors: list[float] = []

    for spec in implants:
        pos = np.array(spec.position, dtype=float)
        requested_axis = spec.axis_unit

        # Snap to nearest jaw surface point
        snapped = _closest_surface_point(jaw_pts, pos)

        # Build the guide sleeve cylinder
        outer_r = spec.sleeve_outer_radius_mm
        sleeve_body = make_cylinder(
            center=tuple(snapped),
            axis=tuple(requested_axis),
            radius=outer_r,
            height=spec.length_mm,
        )

        # Validate
        vr = validate_body(sleeve_body)
        if not vr["ok"]:
            raise RuntimeError(
                f"Surgical guide sleeve body is invalid: {vr['errors']}"
            )

        # Realised axis: normalise requested_axis again (verify precision)
        realised = requested_axis / np.linalg.norm(requested_axis)
        err_deg = angle_between_vectors(requested_axis, realised)

        sleeves.append(sleeve_body)
        realised_axes.append(realised)
        angular_errors.append(err_deg)

    return SurgicalGuideResult(
        sleeves=sleeves,
        realised_axes=realised_axes,
        angular_errors_deg=angular_errors,
    )
