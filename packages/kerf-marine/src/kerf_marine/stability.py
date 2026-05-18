"""
kerf_marine.stability — Righting arm curve and intact stability criteria.

Computes the GZ curve (righting arm vs. heel angle), area under the GZ curve,
and the vanishing stability angle for a ship with known cross-curves of
stability (KN curves) or a wall-sided approximation.

Concepts
--------
GZ(φ)   — righting arm at heel angle φ (m).  Positive → vessel rights itself.
            For the wall-sided formula:
                GZ = sin(φ) · (GM + ½ · BM · tan²(φ))

GZ_area — area under the GZ curve between two angles (m·rad or m·degrees).
            IMO criteria use areas in m·rad.

θ_vanish — angle at which GZ = 0 (beyond GM crossing), i.e. the vessel would
            capsize.  Found by bisection.

IMO A.749 simplified criteria (informational):
  - Area 0–30°  ≥ 0.055 m·rad
  - Area 0–40°  ≥ 0.090 m·rad
  - Area 30–40° ≥ 0.030 m·rad
  - Max GZ at or beyond 25°
  - GZ(30°) ≥ 0.200 m
  - GM₀      ≥ 0.150 m
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence


# ---------------------------------------------------------------------------
# GZ data containers
# ---------------------------------------------------------------------------

@dataclass
class GZPoint:
    """One point on the GZ curve."""
    angle_deg: float   # degrees — heel angle
    gz: float          # m — righting arm


@dataclass
class GZCurve:
    """
    Full righting arm curve for a vessel.

    Attributes
    ----------
    points          : list of GZPoint, sorted by angle_deg
    vanishing_angle : angle at which GZ first crosses zero (from positive),
                      None if GZ stays positive over the computed range
    area_0_30       : m·rad — area under GZ between 0° and 30°
    area_0_40       : m·rad — area under GZ between 0° and 40°
    area_30_40      : m·rad — area between 30° and 40°
    max_gz          : maximum GZ value in the curve (m)
    angle_max_gz    : angle at which GZ is maximum (deg)
    """
    points: list[GZPoint] = field(default_factory=list)
    vanishing_angle: float | None = None
    area_0_30: float = 0.0
    area_0_40: float = 0.0
    area_30_40: float = 0.0
    max_gz: float = 0.0
    angle_max_gz: float = 0.0

    def angles_deg(self) -> list[float]:
        return [p.angle_deg for p in self.points]

    def gz_values(self) -> list[float]:
        return [p.gz for p in self.points]

    def gz_at(self, angle_deg: float) -> float:
        """Linearly interpolate GZ at an arbitrary angle."""
        angles = self.angles_deg()
        gzs = self.gz_values()
        if angle_deg <= angles[0]:
            return gzs[0]
        if angle_deg >= angles[-1]:
            return gzs[-1]
        for i in range(len(angles) - 1):
            if angles[i] <= angle_deg <= angles[i + 1]:
                t = (angle_deg - angles[i]) / (angles[i + 1] - angles[i])
                return gzs[i] + t * (gzs[i + 1] - gzs[i])
        return gzs[-1]

    def imo_criteria(self) -> dict[str, bool | float]:
        """
        Evaluate simplified IMO A.749 intact stability criteria.
        Returns a dict of criterion name → pass/fail bool and actual values.
        """
        gz_30 = self.gz_at(30.0)
        return {
            "area_0_30_m_rad": round(self.area_0_30, 4),
            "area_0_30_pass": self.area_0_30 >= 0.055,
            "area_0_40_m_rad": round(self.area_0_40, 4),
            "area_0_40_pass": self.area_0_40 >= 0.090,
            "area_30_40_m_rad": round(self.area_30_40, 4),
            "area_30_40_pass": self.area_30_40 >= 0.030,
            "gz_at_30_m": round(gz_30, 4),
            "gz_at_30_pass": gz_30 >= 0.200,
            "angle_max_gz_deg": round(self.angle_max_gz, 2),
            "angle_max_gz_pass": self.angle_max_gz >= 25.0,
            "vanishing_angle_deg": (
                round(self.vanishing_angle, 2)
                if self.vanishing_angle is not None
                else None
            ),
        }

    def as_dict(self) -> dict:
        return {
            "points": [
                {"angle_deg": p.angle_deg, "gz_m": round(p.gz, 6)}
                for p in self.points
            ],
            "vanishing_angle_deg": self.vanishing_angle,
            "area_0_30_m_rad": round(self.area_0_30, 6),
            "area_0_40_m_rad": round(self.area_0_40, 6),
            "area_30_40_m_rad": round(self.area_30_40, 6),
            "max_gz_m": round(self.max_gz, 6),
            "angle_max_gz_deg": round(self.angle_max_gz, 2),
        }


# ---------------------------------------------------------------------------
# Trapezoidal integration helper (local, no circular import)
# ---------------------------------------------------------------------------

def _trapz_deg(angles_deg: list[float], gz_vals: list[float]) -> float:
    """Trapezoidal integration of GZ(φ) dφ with angles in degrees → result in m·rad."""
    total = 0.0
    for i in range(len(angles_deg) - 1):
        da = math.radians(angles_deg[i + 1]) - math.radians(angles_deg[i])
        total += 0.5 * (gz_vals[i] + gz_vals[i + 1]) * da
    return total


def _interp_zero(a1: float, gz1: float, a2: float, gz2: float) -> float:
    """Linear interpolation to find angle where GZ crosses zero."""
    if abs(gz2 - gz1) < 1e-15:
        return a1
    return a1 - gz1 * (a2 - a1) / (gz2 - gz1)


# ---------------------------------------------------------------------------
# Wall-sided formula GZ
# ---------------------------------------------------------------------------

def gz_wall_sided(phi_deg: float, gm: float, bm: float) -> float:
    """
    Wall-sided formula for righting arm:

        GZ(φ) = sin(φ) · (GM + ½·BM·tan²(φ))

    Valid for moderate angles (< ~35°) for wall-sided vessels.

    Parameters
    ----------
    phi_deg : heel angle (degrees)
    gm      : initial metacentric height GM (m)
    bm      : transverse metacentric radius BM = I_T / ∇ (m)
    """
    phi = math.radians(phi_deg)
    return math.sin(phi) * (gm + 0.5 * bm * math.tan(phi) ** 2)


# ---------------------------------------------------------------------------
# GZ curve computation
# ---------------------------------------------------------------------------

def gz_curve_wall_sided(
    gm: float,
    bm: float,
    *,
    angle_step_deg: float = 5.0,
    max_angle_deg: float = 90.0,
) -> GZCurve:
    """
    Compute the GZ righting arm curve using the wall-sided formula.

    The curve is evaluated from 0° to max_angle_deg in steps of angle_step_deg.
    The vanishing angle is found by detecting the first zero crossing and
    refining by linear interpolation.

    Parameters
    ----------
    gm           : GM (m), positive = stable
    bm           : BM (m), transverse metacentric radius
    angle_step_deg : step size for evaluation (°)
    max_angle_deg  : maximum heel angle to evaluate (°)
    """
    angles = []
    gzs = []
    phi = 0.0
    while phi <= max_angle_deg + 1e-9:
        gz = gz_wall_sided(phi, gm, bm)
        angles.append(phi)
        gzs.append(gz)
        phi += angle_step_deg

    return _build_gz_curve(angles, gzs)


def gz_curve_from_kn(
    kn_angles_deg: list[float],
    kn_values: list[float],
    kg: float,
    *,
    angle_step_deg: float | None = None,
) -> GZCurve:
    """
    Compute GZ from KN cross-curves and KG.

        GZ(φ) = KN(φ) − KG·sin(φ)

    Parameters
    ----------
    kn_angles_deg : list of heel angles (°) for KN table
    kn_values     : KN lever values (m) at each angle
    kg            : vertical centre of gravity above keel (m)
    angle_step_deg: if set, re-interpolate to this step; otherwise use table as-is
    """
    if len(kn_angles_deg) != len(kn_values):
        raise ValueError("kn_angles_deg and kn_values must have equal length")
    if len(kn_angles_deg) < 2:
        raise ValueError("At least 2 KN points required")

    # Compute GZ = KN - KG·sin(φ)
    angles = list(kn_angles_deg)
    gzs = [
        kn_values[i] - kg * math.sin(math.radians(angles[i]))
        for i in range(len(angles))
    ]

    return _build_gz_curve(angles, gzs)


def _build_gz_curve(angles: list[float], gzs: list[float]) -> GZCurve:
    """
    Build a GZCurve from raw (angle_deg, gz) pairs.

    Finds vanishing angle, computes areas, max GZ.
    """
    points = [GZPoint(a, g) for a, g in zip(angles, gzs)]
    curve = GZCurve(points=points)

    # --- Find vanishing angle (first zero crossing after initial positive region)
    # Skip the trivial GZ(0°) = 0 by starting the search from first positive
    # region.
    vanishing: float | None = None
    first_positive_idx: int | None = None

    for i, p in enumerate(points):
        if p.angle_deg > 0.0 and p.gz > 1e-9:
            first_positive_idx = i
            break

    if first_positive_idx is not None:
        for i in range(first_positive_idx, len(points) - 1):
            if points[i].gz >= 0.0 and points[i + 1].gz < 0.0:
                vanishing = _interp_zero(
                    points[i].angle_deg, points[i].gz,
                    points[i + 1].angle_deg, points[i + 1].gz,
                )
                break
    curve.vanishing_angle = vanishing

    # Clip angles to below vanishing (only consider positive GZ region for areas)
    clip_angle = vanishing if vanishing is not None else angles[-1]

    def gz_clamped(phi_deg: float) -> float:
        if phi_deg > clip_angle:
            return 0.0
        return _interp_gz(angles, gzs, phi_deg)

    # --- Area under GZ between 0–30° (in m·rad)
    curve.area_0_30 = _area_under_gz(angles, gzs, 0.0, 30.0, clip_angle)
    curve.area_0_40 = _area_under_gz(angles, gzs, 0.0, 40.0, clip_angle)
    curve.area_30_40 = _area_under_gz(angles, gzs, 30.0, 40.0, clip_angle)

    # --- Max GZ
    pos_gzs = [(p.angle_deg, p.gz) for p in points if p.gz > 0]
    if pos_gzs:
        max_pair = max(pos_gzs, key=lambda t: t[1])
        curve.max_gz = max_pair[1]
        curve.angle_max_gz = max_pair[0]

    return curve


def _interp_gz(angles: list[float], gzs: list[float], phi: float) -> float:
    """Linear interpolation of GZ at angle phi."""
    if phi <= angles[0]:
        return gzs[0]
    if phi >= angles[-1]:
        return gzs[-1]
    for i in range(len(angles) - 1):
        if angles[i] <= phi <= angles[i + 1]:
            t = (phi - angles[i]) / (angles[i + 1] - angles[i])
            return gzs[i] + t * (gzs[i + 1] - gzs[i])
    return gzs[-1]


def _area_under_gz(
    angles: list[float],
    gzs: list[float],
    a_lo: float,
    a_hi: float,
    clip: float,
) -> float:
    """
    Area under GZ between a_lo and a_hi (degrees), clipped at vanishing angle.

    Uses trapezoidal integration with the existing table points, inserting
    exact boundary points at a_lo, a_hi, and clip.
    """
    hi = min(a_hi, clip)
    if hi <= a_lo:
        return 0.0

    # Build dense sample within [a_lo, hi]
    sample_angles = [a for a in angles if a_lo <= a <= hi]
    # Insert boundary points
    for extra in [a_lo, hi]:
        if extra not in sample_angles:
            sample_angles.append(extra)
    sample_angles = sorted(set(sample_angles))

    sample_gzs = [max(0.0, _interp_gz(angles, gzs, a)) for a in sample_angles]
    return _trapz_deg(sample_angles, sample_gzs)


# ---------------------------------------------------------------------------
# Vanishing-angle bisection search
# ---------------------------------------------------------------------------

def vanishing_angle_bisect(
    gz_fn: Callable[[float], float],
    *,
    lo: float = 1.0,
    hi: float = 90.0,
    tol: float = 0.01,
    max_iter: int = 100,
) -> float | None:
    """
    Find the vanishing stability angle using bisection on an arbitrary GZ function.

    Returns the angle (degrees) where GZ first crosses from positive to negative,
    or None if GZ stays positive over the range [lo, hi].

    Parameters
    ----------
    gz_fn   : callable taking angle_deg → gz (m)
    lo, hi  : search range (degrees)
    tol     : convergence tolerance (degrees)
    max_iter: maximum iterations
    """
    gz_lo = gz_fn(lo)
    gz_hi = gz_fn(hi)

    # If GZ never goes negative, there is no vanishing angle
    if gz_hi >= 0.0:
        return None

    # Find an interval that brackets a zero
    if gz_lo < 0.0:
        # GZ is already negative at lo — search earlier
        return None

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        gz_mid = gz_fn(mid)
        if abs(hi - lo) < tol:
            return mid
        if gz_mid > 0.0:
            lo = mid
        else:
            hi = mid

    return 0.5 * (lo + hi)
