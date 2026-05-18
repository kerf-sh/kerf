"""
NACA 4-digit and 5-digit airfoil coordinate generators.

References:
  NACA TR-460: The Characteristics of 78 Related Airfoil Sections from
               Tests in the Variable-Density Wind Tunnel (1933)
  NACA TR-537: The Aerodynamic Characteristics of Eight Very Thick
               Airfoil Sections … (1935) — 5-digit camber lines
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_NACA4_A = (0.2969, -0.1260, -0.3516, 0.2843)
_NACA4_A_CLOSED = (0.2969, -0.1260, -0.3516, 0.2843, -0.1015)  # finite TE = 0
_NACA4_A_OPEN = (0.2969, -0.1260, -0.3516, 0.2843, -0.1036)    # small open TE


def _thickness_naca4(x: np.ndarray, t: float, finite_te: bool) -> np.ndarray:
    """Half-thickness distribution for NACA 4-digit series (TR-460 eq.)."""
    a = _NACA4_A_CLOSED if finite_te else _NACA4_A_OPEN
    return (t / 0.2) * (
        a[0] * np.sqrt(x)
        + a[1] * x
        + a[2] * x ** 2
        + a[3] * x ** 3
        + a[4] * x ** 4
    )


def _camber_naca4(x: np.ndarray, m: float, p: float):
    """
    Mean camber line and gradient for NACA 4-digit.

    Returns (yc, dyc_dx).
    """
    yc = np.zeros_like(x)
    dyc = np.zeros_like(x)

    if m == 0.0 or p == 0.0:
        return yc, dyc

    fore = x <= p
    aft = ~fore

    yc[fore] = (m / p ** 2) * (2 * p * x[fore] - x[fore] ** 2)
    yc[aft] = (m / (1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x[aft] - x[aft] ** 2)

    dyc[fore] = (2 * m / p ** 2) * (p - x[fore])
    dyc[aft] = (2 * m / (1 - p) ** 2) * (p - x[aft])

    return yc, dyc


def _surface_coords(
    x: np.ndarray,
    yc: np.ndarray,
    dyc: np.ndarray,
    yt: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert camber + thickness to upper/lower surface coordinates."""
    theta = np.arctan(dyc)
    xu = x - yt * np.sin(theta)
    yu = yc + yt * np.cos(theta)
    xl = x + yt * np.sin(theta)
    yl = yc - yt * np.cos(theta)
    return xu, yu, xl, yl


# ---------------------------------------------------------------------------
# Public: NACA 4-digit
# ---------------------------------------------------------------------------

def naca4(
    profile: str,
    n_points: int = 200,
    finite_te: bool = False,
) -> np.ndarray:
    """
    Generate coordinates for a NACA 4-digit airfoil.

    Parameters
    ----------
    profile : str
        4-character code, e.g. ``"2412"`` or ``"0012"``.
    n_points : int
        Number of chordwise stations on each surface (upper + lower).
        The total returned array has ``2*n_points - 1`` rows (the leading
        edge point is shared).
    finite_te : bool
        If True use the closed-trailing-edge coefficient set so y=0 exactly
        at x=1; default False gives a tiny open trailing edge matching the
        original TR-460 polynomial.

    Returns
    -------
    coords : np.ndarray, shape (2*n_points - 1, 2)
        ``(x, y)`` pairs going from trailing edge → upper surface →
        leading edge → lower surface → trailing edge (wrapped around).
        Chord = 1.
    """
    profile = profile.strip()
    if len(profile) != 4 or not profile.isdigit():
        raise ValueError(f"NACA 4-digit profile must be 4 digits, got {profile!r}")

    m = int(profile[0]) / 100.0   # max camber
    p = int(profile[1]) / 10.0    # camber position
    t = int(profile[2:]) / 100.0  # thickness

    # Cosine spacing for better leading-edge resolution
    beta = np.linspace(0, math.pi, n_points)
    x = 0.5 * (1 - np.cos(beta))  # 0 … 1

    yt = _thickness_naca4(x, t, finite_te)
    yc, dyc = _camber_naca4(x, m, p)
    xu, yu, xl, yl = _surface_coords(x, yc, dyc, yt)

    # Build full outline: TE → upper → LE → lower → TE
    upper = np.column_stack([xu[::-1], yu[::-1]])   # TE → LE
    lower = np.column_stack([xl[1:], yl[1:]])        # LE+1 → TE
    coords = np.vstack([upper, lower])
    return coords


# ---------------------------------------------------------------------------
# NACA 5-digit camber-line definitions  (TR-537)
# ---------------------------------------------------------------------------

# Keyed by first 3 digits of 5-digit code → (r, k1) pairs from TR-537 Table 1.
# The first digit encodes design CL, digits 2-3 encode camber position,
# digit 4 encodes reflex flag (0 = normal, 1 = reflexed), digits 4-5 = thickness.
_NACA5_SIMPLE = {
    # (p×10, k1)  — simple (non-reflexed) camber lines
    "210": (0.05,   361.4),
    "220": (0.10,   51.64),
    "230": (0.15,   15.957),
    "240": (0.20,   6.643),
    "250": (0.25,   3.230),
}

_NACA5_REFLEXED = {
    # (p, k1, k2_over_k1) — reflexed camber lines
    "211": (0.10, 51.64, 0.000764),
    "221": (0.15, 15.957, 0.00677),
    "231": (0.20, 6.643, 0.0303),
    "241": (0.25, 3.230, 0.1355),
    "251": (0.30, 3.230, 0.3268),
}


def _camber_naca5_simple(x: np.ndarray, p: float, k1: float):
    """Non-reflexed NACA 5-digit camber line and slope."""
    yc = np.zeros_like(x)
    dyc = np.zeros_like(x)

    fore = x < p
    aft = ~fore

    yc[fore] = (k1 / 6.0) * (x[fore] ** 3 - 3 * p * x[fore] ** 2 + p ** 2 * (3 - p) * x[fore])
    yc[aft] = (k1 * p ** 3 / 6.0) * (1 - x[aft])

    dyc[fore] = (k1 / 6.0) * (3 * x[fore] ** 2 - 6 * p * x[fore] + p ** 2 * (3 - p))
    dyc[aft] = -(k1 * p ** 3 / 6.0) * np.ones_like(x[aft])

    return yc, dyc


def _camber_naca5_reflexed(x: np.ndarray, p: float, k1: float, k2_k1: float):
    """Reflexed NACA 5-digit camber line and slope."""
    k2 = k2_k1 * k1
    yc = np.zeros_like(x)
    dyc = np.zeros_like(x)

    fore = x < p
    aft = ~fore

    yc[fore] = (k1 / 6.0) * (
        (x[fore] - p) ** 3
        - k2_k1 * (1 - p) ** 3 * x[fore]
        - p ** 3 * x[fore]
        + p ** 3
    )
    yc[aft] = (k1 / 6.0) * (
        k2 * (x[aft] - p) ** 3
        - k2_k1 * (1 - p) ** 3 * x[aft]
        - p ** 3 * x[aft]
        + p ** 3
    )

    # Slopes
    dyc[fore] = (k1 / 6.0) * (
        3 * (x[fore] - p) ** 2
        - k2_k1 * (1 - p) ** 3
        - p ** 3
    )
    dyc[aft] = (k1 / 6.0) * (
        3 * k2 * (x[aft] - p) ** 2
        - k2_k1 * (1 - p) ** 3
        - p ** 3
    )

    return yc, dyc


def naca5(profile: str, n_points: int = 200) -> np.ndarray:
    """
    Generate coordinates for a NACA 5-digit airfoil.

    Parameters
    ----------
    profile : str
        5-character code, e.g. ``"23012"``.
    n_points : int
        Chordwise stations per surface.

    Returns
    -------
    coords : np.ndarray, shape (2*n_points - 1, 2)
        Same ordering as :func:`naca4`.

    Notes
    -----
    The design-CL digit encodes CL_design = digit × 3/20.
    The camber-position digits encode x_camber = digits × 0.05.
    Digit 4 = 0 → normal; 1 → reflexed camber line.
    Digits 4-5 = thickness in percent chord.
    """
    profile = profile.strip()
    if len(profile) != 5 or not profile.isdigit():
        raise ValueError(f"NACA 5-digit profile must be 5 digits, got {profile!r}")

    # NACA 5-digit convention:
    #   digit[0]   : design-CL encoding
    #   digit[1:3] : camber-position encoding
    #   digit[2]   : 0 = non-reflexed, 1 = reflexed camber line
    #   digit[3:5] : thickness in percent chord
    key = profile[:3]         # e.g. "230" (non-reflexed) or "231" (reflexed)
    reflexed = int(profile[2]) == 1
    t = int(profile[3:]) / 100.0  # last two digits = thickness

    if reflexed:
        if key not in _NACA5_REFLEXED:
            raise ValueError(
                f"Unsupported NACA 5-digit reflexed camber line key {key!r}. "
                f"Supported: {sorted(_NACA5_REFLEXED)}"
            )
        p, k1, k2_k1 = _NACA5_REFLEXED[key]
    else:
        if key not in _NACA5_SIMPLE:
            raise ValueError(
                f"Unsupported NACA 5-digit camber line key {key!r}. "
                f"Supported: {sorted(_NACA5_SIMPLE)}"
            )
        p, k1 = _NACA5_SIMPLE[key]

    beta = np.linspace(0, math.pi, n_points)
    x = 0.5 * (1 - np.cos(beta))

    yt = _thickness_naca4(x, t, finite_te=False)

    if reflexed:
        yc, dyc = _camber_naca5_reflexed(x, p, k1, k2_k1)
    else:
        yc, dyc = _camber_naca5_simple(x, p, k1)

    xu, yu, xl, yl = _surface_coords(x, yc, dyc, yt)

    upper = np.column_stack([xu[::-1], yu[::-1]])
    lower = np.column_stack([xl[1:], yl[1:]])
    coords = np.vstack([upper, lower])
    return coords


def parse_naca5(profile: str) -> dict:
    """
    Parse NACA 5-digit profile string and return design parameters.

    Returns
    -------
    dict with keys: cl_design, x_camber, thickness_frac, reflexed
    """
    profile = profile.strip()
    if len(profile) != 5 or not profile.isdigit():
        raise ValueError(f"Expected 5-digit NACA code, got {profile!r}")

    # NACA 5-digit encoding:
    #   digit 1: design CL = digit × 3/20
    #   digit 2: x_camber position = digit × 0.05
    #   digit 3: 0 = non-reflexed, 1 = reflexed
    #   digits 4-5: thickness in percent chord
    cl_design = int(profile[0]) * 3 / 20.0
    x_camber = int(profile[1]) * 0.05
    reflexed = int(profile[2]) == 1
    thickness = int(profile[3:]) / 100.0

    return {
        "cl_design": cl_design,
        "x_camber": x_camber,
        "thickness_frac": thickness,
        "reflexed": reflexed,
    }
