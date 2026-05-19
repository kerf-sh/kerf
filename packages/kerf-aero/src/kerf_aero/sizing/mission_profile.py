"""
Mission profile definition for Raymer conceptual-sizing method.

Reference
---------
Raymer D. P., "Aircraft Design: A Conceptual Approach," 6th ed. (2018).
Chapter 6: Preliminary Sizing.

A mission consists of an ordered list of segments; each segment carries a
weight-fraction W_end/W_start that represents fuel consumed (or, for
takeoff/landing/loiter, a fixed fraction).  The overall mission fuel fraction
is the product of all per-segment fractions.

Unit conventions (throughout this package)
-------------------------------------------
- Weights / forces  : lbf  (pound-force)
- Distances         : nautical miles (nm)
- Speeds            : knots (nm/hr)
- TSFC (c_j)        : lbf_fuel / (lbf_thrust · hr)  — "per hour" form
- Areas             : ft²
- Lift-to-drag      : dimensionless ratio
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class SegmentKind(str, Enum):
    """Qualitative classification of a mission segment."""

    WARMUP_TAKEOFF = "warmup_takeoff"
    CLIMB = "climb"
    CRUISE = "cruise"
    LOITER = "loiter"
    DESCENT = "descent"
    LANDING = "landing"
    FIXED_FRACTION = "fixed_fraction"  # user supplies fraction directly


@dataclass
class MissionSegment:
    """
    One leg of a flight mission.

    Parameters
    ----------
    kind:
        Segment type (drives default fraction when not supplied explicitly).
    weight_fraction:
        W_end / W_start for this segment.  When ``None`` it is computed from
        the Breguet equation (for CRUISE/LOITER) or from Raymer Table 6.1
        defaults (all other kinds).
    range_nm:
        Cruise range in nautical miles (only used for CRUISE segments).
    endurance_hr:
        Loiter time in hours (only used for LOITER segments).
    velocity_ktas:
        True airspeed in knots (used for CRUISE Breguet; ignored otherwise).
    ld_ratio:
        Lift-to-drag ratio (used for CRUISE and LOITER Breguet).
    tsfc:
        Thrust-specific fuel consumption in lb_fuel/(lb_thrust·hr).
    """

    kind: SegmentKind = SegmentKind.FIXED_FRACTION
    weight_fraction: float | None = None
    range_nm: float = 0.0
    endurance_hr: float = 0.0
    velocity_ktas: float = 0.0
    ld_ratio: float = 0.0
    tsfc: float = 0.0

    # Raymer Table 6.1 defaults ------------------------------------------------
    _DEFAULT_FRACTIONS: dict[str, float] = field(
        default_factory=lambda: {
            SegmentKind.WARMUP_TAKEOFF: 0.970,
            SegmentKind.CLIMB: 0.985,
            SegmentKind.DESCENT: 0.990,
            SegmentKind.LANDING: 0.995,
        },
        repr=False,
        compare=False,
    )

    def compute_fraction(self) -> float:
        """Return W_end/W_start for this segment.

        For CRUISE segments the Breguet range equation is used::

            W_f/W_i = exp(-R · c_j / (V · (L/D)))

        where R is in nm, V in nm/hr, c_j in /hr.

        For LOITER segments the Breguet endurance equation is used::

            W_f/W_i = exp(-E · c_j / (L/D))

        where E is endurance in hours.
        """
        if self.weight_fraction is not None:
            return self.weight_fraction

        defaults = {
            SegmentKind.WARMUP_TAKEOFF: 0.970,
            SegmentKind.CLIMB: 0.985,
            SegmentKind.DESCENT: 0.990,
            SegmentKind.LANDING: 0.995,
        }

        if self.kind == SegmentKind.CRUISE:
            # Breguet range — V and R in consistent units (here: nm & nm/hr)
            if self.velocity_ktas <= 0 or self.ld_ratio <= 0 or self.tsfc <= 0:
                raise ValueError(
                    "CRUISE segment requires velocity_ktas, ld_ratio, and tsfc > 0"
                )
            exp_arg = -(self.range_nm * self.tsfc) / (self.velocity_ktas * self.ld_ratio)
            return math.exp(exp_arg)

        if self.kind == SegmentKind.LOITER:
            if self.endurance_hr <= 0 or self.ld_ratio <= 0 or self.tsfc <= 0:
                raise ValueError(
                    "LOITER segment requires endurance_hr, ld_ratio, and tsfc > 0"
                )
            exp_arg = -(self.endurance_hr * self.tsfc) / self.ld_ratio
            return math.exp(exp_arg)

        if self.kind in defaults:
            return defaults[self.kind]

        raise ValueError(
            f"Segment kind '{self.kind}' requires an explicit weight_fraction"
        )


@dataclass
class MissionProfile:
    """
    An ordered collection of ``MissionSegment`` objects representing a complete
    flight.

    The overall *mission fuel fraction* (fuel burned / TOGW) is derived from
    the product of per-segment W_end/W_start values::

        M_ff = product(W_i_end / W_i_start)   for i in segments

    The total fuel fraction (fuel / W_0) is then::

        W_fuel / W_0 = 1 - M_ff

    A 6% trapped-fuel / unusable-fuel allowance (Raymer §6.2) is included by
    default via ``trapped_fuel_factor``.

    Parameters
    ----------
    segments:
        Ordered list of mission segments.
    trapped_fuel_factor:
        Fraction added for trapped/unusable fuel (default 0.06).
    """

    segments: list[MissionSegment] = field(default_factory=list)
    trapped_fuel_factor: float = 0.06

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def simple_cruise(
        cls,
        range_nm: float,
        velocity_ktas: float,
        ld_ratio: float,
        tsfc: float,
        *,
        include_reserves: bool = True,
    ) -> "MissionProfile":
        """Build a canonical Raymer 'simple cruise' mission (Raymer Fig 6.1).

        Segments: warmup/takeoff → climb → cruise → descent → landing.
        Optionally appends a loiter reserve leg (0.5 hr, typical GA).
        """
        segments: list[MissionSegment] = [
            MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),
            MissionSegment(kind=SegmentKind.CLIMB),
            MissionSegment(
                kind=SegmentKind.CRUISE,
                range_nm=range_nm,
                velocity_ktas=velocity_ktas,
                ld_ratio=ld_ratio,
                tsfc=tsfc,
            ),
            MissionSegment(kind=SegmentKind.DESCENT),
            MissionSegment(kind=SegmentKind.LANDING),
        ]
        if include_reserves:
            segments.append(
                MissionSegment(
                    kind=SegmentKind.LOITER,
                    endurance_hr=0.5,
                    ld_ratio=ld_ratio * 1.1,  # loiter L/D slightly better
                    tsfc=tsfc,
                )
            )
        return cls(segments=segments)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    def mission_fuel_fraction(self) -> float:
        """Product of all segment W_end/W_start fractions."""
        mff = 1.0
        for seg in self.segments:
            mff *= seg.compute_fraction()
        return mff

    def fuel_fraction(self) -> float:
        """W_fuel / W_0 including trapped fuel allowance.

        ::

            W_fuel/W_0 = (1 - M_ff) * (1 + trapped_fuel_factor)
        """
        mff = self.mission_fuel_fraction()
        return (1.0 - mff) * (1.0 + self.trapped_fuel_factor)
