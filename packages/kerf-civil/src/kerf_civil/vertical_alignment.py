"""
Vertical alignment geometry for road/highway design.

Supports:
  - VerticalTangent — constant grade (g, %)
  - ParabolicCurve  — equal-tangent parabolic crest or sag vertical curve

K-value based design criteria follow AASHTO Green Book conventions.

Grades are expressed in percent (%).  Elevations are in metres.
Stations are horizontal distances (metres) measured along the alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Element types
# ---------------------------------------------------------------------------

@dataclass
class VerticalTangent:
    """Constant-grade vertical tangent segment.

    Parameters
    ----------
    length:
        Horizontal length (metres).
    grade_pct:
        Grade in percent (positive = rising, negative = falling).
    elev_start:
        Elevation at the start of the tangent (metres).
    """

    length: float
    grade_pct: float
    elev_start: float = 0.0

    def __post_init__(self):
        if self.length < 0:
            raise ValueError(f"VerticalTangent length must be >= 0, got {self.length}")

    def elev_at(self, s: float) -> float:
        """Elevation at horizontal distance s from the start."""
        if s < 0 or s > self.length + 1e-10:
            raise ValueError(f"s={s} outside [0, {self.length}]")
        return self.elev_start + self.grade_pct / 100.0 * s

    def elev_end(self) -> float:
        """Elevation at the end of the tangent."""
        return self.elev_at(self.length)

    def slope(self) -> float:
        """Grade as a dimensionless fraction (not percent)."""
        return self.grade_pct / 100.0


@dataclass
class ParabolicCurve:
    """Equal-tangent parabolic vertical curve.

    The standard highway parabolic VPC has the form:

        y(x) = y_bvc + g1 * x + (A / (200 * L)) * x²

    where A = g2 − g1 (algebraic difference of grades, %).

    Parameters
    ----------
    length:
        Horizontal curve length L (metres, > 0).
    grade_in_pct:
        Incoming grade g1 (%).
    grade_out_pct:
        Outgoing grade g2 (%).
    elev_bvc:
        Elevation at the BVC (Beginning of Vertical Curve).
    """

    length: float
    grade_in_pct: float
    grade_out_pct: float
    elev_bvc: float = 0.0

    def __post_init__(self):
        if self.length <= 0:
            raise ValueError(f"ParabolicCurve length must be > 0, got {self.length}")

    # ------------------------------------------------------------------
    # Design properties
    # ------------------------------------------------------------------

    @property
    def A(self) -> float:
        """Algebraic grade difference A = g2 − g1 (%)."""
        return self.grade_out_pct - self.grade_in_pct

    def is_crest(self) -> bool:
        """True when the curve is a crest (g1 > g2, A < 0)."""
        return self.A < 0.0

    def is_sag(self) -> bool:
        """True when the curve is a sag (g2 > g1, A > 0)."""
        return self.A > 0.0

    def K_value(self) -> float:
        """K = L / |A|  (metres per percent, or feet per percent in US units).

        The K-value characterises the sharpness of the vertical curve and is
        used directly in AASHTO stopping-sight-distance tables.
        """
        if abs(self.A) < 1e-12:
            return float("inf")
        return self.length / abs(self.A)

    # ------------------------------------------------------------------
    # Elevation
    # ------------------------------------------------------------------

    def elev_at(self, x: float) -> float:
        """Elevation at horizontal distance x from the BVC.

        Uses the standard parabolic equation:
            y(x) = y_bvc + (g1/100)*x + (A/(200*L))*x²
        """
        if x < 0 or x > self.length + 1e-10:
            raise ValueError(f"x={x} outside [0, {self.length}]")
        g1 = self.grade_in_pct / 100.0
        coeff = self.A / (200.0 * self.length)
        return self.elev_bvc + g1 * x + coeff * x * x

    def elev_evc(self) -> float:
        """Elevation at the EVC (End of Vertical Curve)."""
        return self.elev_at(self.length)

    def grade_at_pct(self, x: float) -> float:
        """Grade (%) at horizontal distance x from the BVC."""
        coeff = self.A / (200.0 * self.length)
        return self.grade_in_pct + 2.0 * coeff * 100.0 * x

    # ------------------------------------------------------------------
    # High / low point
    # ------------------------------------------------------------------

    def high_low_point_x(self) -> float | None:
        """Horizontal distance from the BVC to the high (crest) or low (sag) point.

        Returns None if no such point lies within the curve (grades don't change sign).

        For a parabola  y = y0 + g1*x + c*x²,  the extremum is at:
            x* = −g1 / (2c) = −g1 * L / A  (in consistent units)
        expressed with grades in decimal form:
            x* = −(g1/100) * L / (A/100) = −g1 * L / A
        """
        if abs(self.A) < 1e-12:
            return None
        x_star = -self.grade_in_pct * self.length / self.A
        if 0.0 <= x_star <= self.length:
            return x_star
        return None

    def high_low_point_elev(self) -> float | None:
        """Elevation at the high/low point, or None if outside the curve."""
        x = self.high_low_point_x()
        if x is None:
            return None
        return self.elev_at(x)

    # ------------------------------------------------------------------
    # AASHTO sight-distance design check
    # ------------------------------------------------------------------

    @classmethod
    def from_K_and_A(
        cls,
        K: float,
        A_pct: float,
        grade_in_pct: float = 0.0,
        elev_bvc: float = 0.0,
    ) -> "ParabolicCurve":
        """Construct a curve given a target K-value and |A|.

        L = K · |A|
        """
        length = K * abs(A_pct)
        grade_out_pct = grade_in_pct + A_pct
        return cls(
            length=length,
            grade_in_pct=grade_in_pct,
            grade_out_pct=grade_out_pct,
            elev_bvc=elev_bvc,
        )


# ---------------------------------------------------------------------------
# Compound vertical alignment
# ---------------------------------------------------------------------------

@dataclass
class VerticalAlignment:
    """Ordered sequence of vertical alignment elements (tangents and curves).

    Build up using ``add_tangent`` and ``add_curve``.  Elevations are
    chained automatically.
    """

    elements: list[VerticalTangent | ParabolicCurve] = field(default_factory=list)

    _current_station: float = field(default=0.0, init=False, repr=False)
    _current_elev: float = field(default=0.0, init=False, repr=False)
    _current_grade_pct: float = field(default=0.0, init=False, repr=False)

    def set_datum(self, station: float = 0.0, elev: float = 0.0, grade_pct: float = 0.0) -> "VerticalAlignment":
        """Set the starting station, elevation, and grade."""
        self._current_station = station
        self._current_elev = elev
        self._current_grade_pct = grade_pct
        return self

    def add_tangent(self, length: float) -> "VerticalAlignment":
        """Append a tangent at the current grade."""
        t = VerticalTangent(
            length=length,
            grade_pct=self._current_grade_pct,
            elev_start=self._current_elev,
        )
        self.elements.append(t)
        self._current_elev = t.elev_end()
        self._current_station += length
        return self

    def add_curve(self, length: float, grade_out_pct: float) -> "VerticalAlignment":
        """Append a parabolic curve from the current grade to *grade_out_pct*."""
        c = ParabolicCurve(
            length=length,
            grade_in_pct=self._current_grade_pct,
            grade_out_pct=grade_out_pct,
            elev_bvc=self._current_elev,
        )
        self.elements.append(c)
        self._current_elev = c.elev_evc()
        self._current_grade_pct = grade_out_pct
        self._current_station += length
        return self

    def total_length(self) -> float:
        """Total horizontal length of the vertical alignment."""
        return sum(e.length for e in self.elements)

    def elev_at_station(self, station: float) -> float:
        """Elevation at an absolute station measured from datum."""
        offset = station - (self._current_station - self.total_length())
        cumulative = 0.0
        for e in self.elements:
            L = e.length
            if offset <= cumulative + L + 1e-10:
                s = max(0.0, offset - cumulative)
                s = min(s, L)
                return e.elev_at(s)
            cumulative += L
        # Beyond end: extrapolate with last grade
        if self.elements:
            last = self.elements[-1]
            extra = offset - cumulative
            g = last.grade_pct if isinstance(last, VerticalTangent) else last.grade_out_pct
            return last.elev_at(last.length) + g / 100.0 * extra
        return 0.0
