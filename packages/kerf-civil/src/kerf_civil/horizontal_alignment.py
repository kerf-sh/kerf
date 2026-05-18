"""
Horizontal alignment geometry for road/highway design.

Supports three element types:
  - TangentSegment  — straight tangent line
  - CircularArc     — simple circular curve (radius R, deflection angle Δ)
  - ClothoidSpiral  — Euler (Cornu) spiral / clothoid entry/exit transitions

Alignment arithmetic follows AASHTO Green Book conventions:
  - Stationing is cumulative from the beginning of the alignment.
  - All angles are in radians unless otherwise stated.
  - x-coordinates increase "forward" along the initial tangent direction.

AASHTO superelevation design speed look-up is provided via
``aashto_superelevation``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Segment types
# ---------------------------------------------------------------------------

@dataclass
class TangentSegment:
    """Straight tangent — no curvature.

    Parameters
    ----------
    length:
        Horizontal length of the tangent (metres ≥ 0).
    bearing_rad:
        Bearing at start (radians, CW from north).  Default 0 = due north /
        positive-x direction.
    """

    length: float
    bearing_rad: float = 0.0

    def __post_init__(self):
        if self.length < 0:
            raise ValueError(f"TangentSegment length must be >= 0, got {self.length}")

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def arc_length(self) -> float:
        """Horizontal arc length (= projected length for a tangent)."""
        return self.length

    def end_bearing(self) -> float:
        """Bearing at the end of the segment (unchanged for a tangent)."""
        return self.bearing_rad

    def coords_at(self, s: float, start_xy: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        """Cartesian (x, y) at distance *s* from the start of the segment.

        x = easting, y = northing.
        """
        if s < 0 or s > self.length + 1e-10:
            raise ValueError(f"s={s} outside [0, {self.length}]")
        return (
            start_xy[0] + s * math.sin(self.bearing_rad),
            start_xy[1] + s * math.cos(self.bearing_rad),
        )


@dataclass
class CircularArc:
    """Simple circular arc.

    Parameters
    ----------
    radius:
        Curve radius R (metres > 0).
    delta_rad:
        Total deflection (central) angle Δ (radians, signed: + = right turn,
        − = left turn).
    bearing_rad:
        Tangent bearing at the PC (Point of Curvature), radians CW from north.
    """

    radius: float
    delta_rad: float
    bearing_rad: float = 0.0

    def __post_init__(self):
        if self.radius <= 0:
            raise ValueError(f"CircularArc radius must be > 0, got {self.radius}")

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def arc_length(self) -> float:
        """Arc length L = R · |Δ| (exact analytic formula)."""
        return self.radius * abs(self.delta_rad)

    def end_bearing(self) -> float:
        """Tangent bearing at the PT (Point of Tangency)."""
        return self.bearing_rad + self.delta_rad

    def chord_length(self) -> float:
        """Long chord C = 2R · sin(Δ/2)."""
        return 2.0 * self.radius * math.sin(abs(self.delta_rad) / 2.0)

    def tangent_length(self) -> float:
        """Tangent distance T = R · tan(Δ/2) from the PI."""
        return self.radius * math.tan(abs(self.delta_rad) / 2.0)

    def middle_ordinate(self) -> float:
        """Middle ordinate M = R · (1 − cos(Δ/2))."""
        return self.radius * (1.0 - math.cos(abs(self.delta_rad) / 2.0))

    def external_distance(self) -> float:
        """External distance E = R · (sec(Δ/2) − 1)."""
        return self.radius * (1.0 / math.cos(abs(self.delta_rad) / 2.0) - 1.0)

    def coords_at(self, s: float, start_xy: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        """Cartesian (x, y) at arc distance *s* from the PC.

        The start point (PC) is at *start_xy*.  This uses the standard
        polar parametrisation of the arc relative to the circle centre.
        """
        L = self.arc_length()
        if s < 0 or s > L + 1e-10:
            raise ValueError(f"s={s} outside [0, {L}]")
        # Sub-angle swept at arc distance s
        theta = s / self.radius  # always positive
        sign = math.copysign(1.0, self.delta_rad)
        # Offset from PC:  (Δx, Δy) in global frame
        # The PC tangent bearing is bearing_rad.
        # Perpendicular to the right (for a right curve, sign>0) leads to
        # the circle centre.
        b = self.bearing_rad
        # Rotate: forward = (sin(b), cos(b)), right = (cos(b), -sin(b))
        dx = self.radius * (math.sin(b + sign * theta) - math.sin(b))
        dy = self.radius * (math.cos(b) - math.cos(b + sign * theta))
        return (start_xy[0] + dx, start_xy[1] + dy)


# ---------------------------------------------------------------------------
# Clothoid (Euler spiral / Cornu spiral)
# ---------------------------------------------------------------------------

def _fresnel(t: float, n_terms: int = 20) -> tuple[float, float]:
    """Power-series approximation of the Fresnel integrals C(t) and S(t).

    Uses the standard parametric form:
        C(t) = ∫₀ᵗ cos(π u²/2) du
        S(t) = ∫₀ᵗ sin(π u²/2) du

    This series converges rapidly for small t; for large t a continued-
    fraction expansion would be more efficient, but highway spiral
    parameters keep RL well below the range where convergence falters
    with 20 terms.
    """
    C = 0.0
    S = 0.0
    t2 = t * t
    term_c = t
    term_s = t * t2 * math.pi / 6.0  # first S term = t^3 * π/6
    # Direct series:
    # C(t) = Σ_{n=0}^∞  (-1)^n (π/2)^{2n} t^{4n+1} / [(4n+1)(2n)!]
    # S(t) = Σ_{n=0}^∞  (-1)^n (π/2)^{2n+1} t^{4n+3} / [(4n+3)(2n+1)!]
    half_pi = math.pi / 2.0
    t4 = t2 * t2
    C_val = t
    S_val = (half_pi * t * t2) / 3.0
    hp2n = 1.0  # (π/2)^{2n}
    fact2n = 1.0  # (2n)!
    tpow_c = t  # t^{4n+1}
    tpow_s = t * t2  # t^{4n+3}
    c_sum = tpow_c  # n=0 term
    s_sum = half_pi * tpow_s / 3.0
    for n in range(1, n_terms):
        hp2n *= half_pi * half_pi  # (π/2)^{2n}
        fact2n *= (2 * n) * (2 * n - 1)  # (2n)!
        tpow_c *= t4  # t^{4n+1}
        tpow_s *= t4
        sign = (-1) ** n
        c_sum += sign * hp2n * tpow_c / ((4 * n + 1) * fact2n)
        s_fact = fact2n * (2 * n + 1)
        s_sum += sign * hp2n * half_pi * tpow_s / ((4 * n + 3) * s_fact)
    return c_sum, s_sum


@dataclass
class ClothoidSpiral:
    """Euler clothoid (Cornu spiral) transition curve.

    The clothoid satisfies  R · L = A²  (the spiral parameter equation),
    where A is the clothoid parameter.

    This models either an *entry* spiral (tangent → curve) or an *exit*
    spiral (curve → tangent) by convention.

    Parameters
    ----------
    length:
        Total spiral length L (metres).
    radius_end:
        Radius at the far end R (metres).  At the start the radius is ∞
        (tangent point).
    bearing_rad:
        Tangent bearing at the TS (Tangent-to-Spiral) point, radians CW
        from north.
    turn_right:
        True for a right-hand (clockwise) spiral; False for left.
    """

    length: float
    radius_end: float
    bearing_rad: float = 0.0
    turn_right: bool = True

    def __post_init__(self):
        if self.length <= 0:
            raise ValueError(f"ClothoidSpiral length must be > 0, got {self.length}")
        if self.radius_end <= 0:
            raise ValueError(f"ClothoidSpiral radius_end must be > 0, got {self.radius_end}")

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def parameter_A(self) -> float:
        """Clothoid parameter A = sqrt(R · L)."""
        return math.sqrt(self.radius_end * self.length)

    def end_angle_rad(self) -> float:
        """Spiral angle θₛ at the SC (Spiral-to-Curve) point.

        Analytic formula for a Euler clothoid:
            θₛ = L / (2 R)

        This is exact (not an approximation).
        """
        return self.length / (2.0 * self.radius_end)

    def end_bearing(self) -> float:
        """Tangent bearing at the SC point."""
        sign = 1.0 if self.turn_right else -1.0
        return self.bearing_rad + sign * self.end_angle_rad()

    # ------------------------------------------------------------------
    # Tangent offsets (x, y in the local spiral frame)
    # ------------------------------------------------------------------

    def _tangent_offsets(self, s: float) -> tuple[float, float]:
        """Local x (along initial tangent) and y (lateral offset) at arc length s.

        Uses exact Fresnel-integral based formula:
            x = A · sqrt(π) · C(s / (A · sqrt(π)))
            y = A · sqrt(π) · S(s / (A · sqrt(π)))

        where C and S are Fresnel integrals.
        """
        A = self.parameter_A
        sqrt_pi = math.sqrt(math.pi)
        arg = s / (A * sqrt_pi)
        C, S = _fresnel(arg)
        x_local = A * sqrt_pi * C
        y_local = A * sqrt_pi * S
        return x_local, y_local

    def coords_at(self, s: float, start_xy: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        """Global (x, y) at arc distance *s* from the TS point."""
        if s < 0 or s > self.length + 1e-10:
            raise ValueError(f"s={s} outside [0, {self.length}]")
        x_l, y_l = self._tangent_offsets(s)
        # Rotate from local spiral frame to global bearing frame
        b = self.bearing_rad
        sign = 1.0 if self.turn_right else -1.0
        # Local x is forward along tangent, y is perpendicular (right if turn_right)
        # In global frame: forward = (sin(b), cos(b)), right = (cos(b), -sin(b))
        gx = x_l * math.sin(b) + sign * y_l * math.cos(b)
        gy = x_l * math.cos(b) - sign * y_l * math.sin(b)
        return (start_xy[0] + gx, start_xy[1] + gy)


# ---------------------------------------------------------------------------
# AASHTO superelevation
# ---------------------------------------------------------------------------

# AASHTO Green Book Table 3-7 (emax = 8%, f_s = side friction factor).
# Keys: design speed (mph); values: list of (radius_ft, e_percent) pairs,
# ordered from min radius to max (straight).

_AASHTO_SUPER_TABLE: dict[int, list[tuple[float, float]]] = {
    # (radius_ft, e_pct)  — abridged representative rows
    20: [(50, 8.0), (75, 6.6), (100, 4.8), (150, 3.0), (200, 2.0), (300, 1.5), (float("inf"), 1.5)],
    30: [(100, 8.0), (150, 7.0), (200, 5.5), (300, 3.6), (500, 2.2), (750, 1.5), (float("inf"), 1.5)],
    40: [(150, 8.0), (200, 7.0), (300, 5.8), (500, 3.8), (750, 2.4), (1200, 1.5), (float("inf"), 1.5)],
    50: [(250, 8.0), (350, 7.0), (500, 5.8), (750, 4.3), (1200, 2.7), (2000, 1.5), (float("inf"), 1.5)],
    60: [(400, 8.0), (550, 7.0), (750, 5.8), (1200, 4.0), (2000, 2.6), (3000, 1.5), (float("inf"), 1.5)],
    70: [(600, 8.0), (850, 7.0), (1200, 5.5), (2000, 3.7), (3000, 2.5), (5000, 1.5), (float("inf"), 1.5)],
    80: [(950, 8.0), (1400, 7.0), (2000, 5.3), (3000, 3.6), (5000, 2.3), (7000, 1.5), (float("inf"), 1.5)],
}


def aashto_superelevation(
    design_speed_mph: int,
    radius_ft: float,
    e_max: float = 8.0,
) -> float:
    """Look up AASHTO design superelevation rate (%) for a given design speed and radius.

    Parameters
    ----------
    design_speed_mph:
        Design speed in mph.  Supported: 20, 30, 40, 50, 60, 70, 80.
    radius_ft:
        Horizontal curve radius in feet.
    e_max:
        Maximum superelevation rate (%).  Default 8 % per AASHTO.

    Returns
    -------
    float
        Superelevation rate e in percent.
    """
    speeds = sorted(_AASHTO_SUPER_TABLE.keys())
    if design_speed_mph not in _AASHTO_SUPER_TABLE:
        # Clamp to nearest tabulated speed
        closest = min(speeds, key=lambda v: abs(v - design_speed_mph))
        design_speed_mph = closest

    table = _AASHTO_SUPER_TABLE[design_speed_mph]
    # Linear interpolation between bracketing rows
    for i, (r_hi, e_hi) in enumerate(table):
        if radius_ft <= r_hi:
            if i == 0:
                return min(e_hi, e_max)
            r_lo, e_lo = table[i - 1]
            if r_lo == r_hi:
                return min(e_hi, e_max)
            # Interpolate (log-radius interpolation is more accurate for highway design)
            t = (math.log(radius_ft) - math.log(r_lo)) / (math.log(r_hi) - math.log(r_lo))
            e = e_lo + t * (e_hi - e_lo)
            return min(max(e, 0.0), e_max)
    return table[-1][1]  # flat section (minimum runoff)


# ---------------------------------------------------------------------------
# Compound alignment
# ---------------------------------------------------------------------------

@dataclass
class HorizontalAlignment:
    """An ordered sequence of horizontal alignment elements.

    Build up using ``add_tangent``, ``add_arc``, and ``add_spiral``.
    Bearings are chained automatically.
    """

    elements: list[TangentSegment | CircularArc | ClothoidSpiral] = field(default_factory=list)

    # Track current state
    _current_bearing: float = field(default=0.0, init=False, repr=False)
    _current_station: float = field(default=0.0, init=False, repr=False)
    _current_xy: tuple[float, float] = field(default=(0.0, 0.0), init=False, repr=False)

    def add_tangent(self, length: float) -> "HorizontalAlignment":
        """Append a tangent segment and chain the bearing."""
        seg = TangentSegment(length=length, bearing_rad=self._current_bearing)
        self.elements.append(seg)
        self._current_xy = seg.coords_at(length, self._current_xy)
        self._current_bearing = seg.end_bearing()
        self._current_station += length
        return self

    def add_arc(self, radius: float, delta_rad: float) -> "HorizontalAlignment":
        """Append a circular arc and chain the bearing."""
        arc = CircularArc(radius=radius, delta_rad=delta_rad, bearing_rad=self._current_bearing)
        self.elements.append(arc)
        L = arc.arc_length()
        self._current_xy = arc.coords_at(L, self._current_xy)
        self._current_bearing = arc.end_bearing()
        self._current_station += L
        return self

    def add_spiral(self, length: float, radius_end: float, turn_right: bool = True) -> "HorizontalAlignment":
        """Append a clothoid spiral and chain the bearing."""
        sp = ClothoidSpiral(
            length=length,
            radius_end=radius_end,
            bearing_rad=self._current_bearing,
            turn_right=turn_right,
        )
        self.elements.append(sp)
        self._current_xy = sp.coords_at(length, self._current_xy)
        self._current_bearing = sp.end_bearing()
        self._current_station += length
        return self

    def total_length(self) -> float:
        """Total horizontal length of the alignment."""
        return sum(e.arc_length() if hasattr(e, "arc_length") else e.length for e in self.elements)

    def station_list(self, interval: float = 20.0) -> list[float]:
        """Return a list of stations at a fixed interval."""
        L = self.total_length()
        n = int(L / interval)
        stations = [i * interval for i in range(n + 1)]
        if stations[-1] < L:
            stations.append(L)
        return stations
