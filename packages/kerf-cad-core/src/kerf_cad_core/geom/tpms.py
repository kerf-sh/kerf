"""Shared TPMS (Triply-Periodic Minimal Surface) raw field functions.

This module provides the canonical implicit-field functions for TPMS types used
by both the lattice unit-cell library (geom/lattice.py) and the FRep/SDF layer
(frep/sdf.py).  Each function accepts physical coordinates and a period
parameter and returns the raw field value (zero-level = mid-surface, no iso
offset).

Public API
----------
gyroid_field(x, y, z, period) -> float
    Schoen gyroid: sin(kx)cos(ky) + sin(ky)cos(kz) + sin(kz)cos(kx)

schwarz_p_field(x, y, z, period) -> float
    Schwarz-P: cos(kx) + cos(ky) + cos(kz)

diamond_field(x, y, z, period) -> float
    Schwarz-D (diamond): sin(kx)sin(ky)sin(kz) + sin(kx)cos(ky)cos(kz)
                       + cos(kx)sin(ky)cos(kz) + cos(kx)cos(ky)sin(kz)

where k = 2π / period in all cases.

References
----------
- Schoen, A. H. (1970). Infinite periodic minimal surfaces without
  self-intersections. NASA Technical Note D-5541.
- Lord, E.A. & Mackay, A.L. (2003). Periodic minimal surfaces of cubic
  symmetry. Current Science 85(3).
"""

from __future__ import annotations

import math


__all__ = [
    "gyroid_field",
    "schwarz_p_field",
    "diamond_field",
]


def gyroid_field(x: float, y: float, z: float, period: float) -> float:
    """Gyroid implicit field value at (x, y, z).

    Formula: sin(kx)cos(ky) + sin(ky)cos(kz) + sin(kz)cos(kx)
    where k = 2π / period.

    Zero-level set is the gyroid mid-surface.
    """
    k = 2.0 * math.pi / period
    kx, ky, kz = k * x, k * y, k * z
    return (
        math.sin(kx) * math.cos(ky)
        + math.sin(ky) * math.cos(kz)
        + math.sin(kz) * math.cos(kx)
    )


def schwarz_p_field(x: float, y: float, z: float, period: float) -> float:
    """Schwarz-P implicit field value at (x, y, z).

    Formula: cos(kx) + cos(ky) + cos(kz)
    where k = 2π / period.

    Zero-level set is the Schwarz-P mid-surface.
    """
    k = 2.0 * math.pi / period
    return math.cos(k * x) + math.cos(k * y) + math.cos(k * z)


def diamond_field(x: float, y: float, z: float, period: float) -> float:
    """Schwarz-D (diamond) implicit field value at (x, y, z).

    Formula: sin(kx)sin(ky)sin(kz) + sin(kx)cos(ky)cos(kz)
           + cos(kx)sin(ky)cos(kz) + cos(kx)cos(ky)sin(kz)
    where k = 2π / period.

    Zero-level set is the diamond mid-surface.
    """
    k = 2.0 * math.pi / period
    kx, ky, kz = k * x, k * y, k * z
    sx, cx_ = math.sin(kx), math.cos(kx)
    sy, cy_ = math.sin(ky), math.cos(ky)
    sz, cz_ = math.sin(kz), math.cos(kz)
    return (
        sx * sy * sz
        + sx * cy_ * cz_
        + cx_ * sy * cz_
        + cx_ * cy_ * sz
    )
