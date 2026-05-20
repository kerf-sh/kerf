"""
kerf_textiles.etextiles
=======================
E-textile / smart-textile design: conductive thread routing, resistive heating,
and LED-fabric layout for garment patterns.

Modules
-------
- ResistiveYarn         — yarn spec (resistance per metre) + segment model
- heating_calc          — I²R power dissipation for a resistive heater trace
- thread_route          — conductive-thread routing as a polyline over panel UV
- LEDNode               — Flora-class LED node spec (Vf, If)
- LEDLayout             — serial + parallel branch network; Kirchhoff current solve
- led_layout            — factory: build a grid or custom LED network

Physics
-------
For a resistive-yarn heater segment of length L (m), resistance/metre r_per_m
(Ω/m), carrying current I (A):

    R_total  = r_per_m * L          [Ω]
    P_dissip = I² * R_total         [W]  — Joule heating (I²R)
    V_drop   = I * R_total          [V]

Tolerance: computed values match I²R to within 1% (oracle-tested).

LED network (Kirchhoff)
-----------------------
Each branch is a serial chain of N_s LEDs with forward voltage Vf each.
M branches are wired in parallel across the supply voltage Vsupply.

    V_per_branch = Vsupply
    I_per_branch = (Vsupply - N_s * Vf) / R_series   [A]  — per branch
    I_total      = M * I_per_branch                    [A]  — total supply current

Where R_series is the current-limiting resistor added in each branch.
If R_series=0 the branch is short-limited (V drive must exactly equal N_s*Vf).

Conductive-thread routing (UV polyline)
---------------------------------------
A garment panel is modelled as a UV rectangle [0,1]×[0,1] (u=along-grain,
v=cross-grain).  A route is a sequence of (u, v) waypoints forming a polyline.
Length is computed in real-world units given the panel's physical dimensions
(width_m, height_m).

    arc_length = Σ sqrt((Δu·W)² + (Δv·H)²)   [m]

Pairs naturally with kerf_textiles.sublimation.CylinderPanel UV mapping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Resistive yarn + heating
# ---------------------------------------------------------------------------

@dataclass
class ResistiveYarn:
    """
    Specification of a conductive / resistive yarn.

    Attributes
    ----------
    name : str
        Human-readable name (e.g. "Shieldex 117/17 dtex").
    resistance_per_metre : float
        Resistance in Ω/m at rated current.
    max_current_a : float
        Recommended continuous current in amperes.  0 = unspecified.
    notes : str
        Optional notes (material, twist, coating, etc.).
    """
    name: str
    resistance_per_metre: float          # Ω/m
    max_current_a: float = 0.0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.resistance_per_metre < 0:
            raise ValueError(
                f"resistance_per_metre must be ≥ 0, got {self.resistance_per_metre}"
            )


@dataclass
class HeaterSegment:
    """
    A single resistive-yarn heater trace on a garment panel.

    Attributes
    ----------
    yarn : ResistiveYarn
        The yarn specification.
    length_m : float
        Physical length of the stitched trace in metres.
    current_a : float
        Operating current in amperes.
    """
    yarn: ResistiveYarn
    length_m: float
    current_a: float

    def __post_init__(self) -> None:
        if self.length_m < 0:
            raise ValueError(f"length_m must be ≥ 0, got {self.length_m}")
        if self.current_a < 0:
            raise ValueError(f"current_a must be ≥ 0, got {self.current_a}")

    @property
    def resistance(self) -> float:
        """Total resistance R = r_per_m * L  [Ω]."""
        return self.yarn.resistance_per_metre * self.length_m

    @property
    def power_w(self) -> float:
        """Joule power P = I² * R  [W]."""
        return self.current_a ** 2 * self.resistance

    @property
    def voltage_drop(self) -> float:
        """Voltage drop V = I * R  [V]."""
        return self.current_a * self.resistance


def heating_calc(
    yarn: ResistiveYarn,
    length_m: float,
    current_a: float,
) -> dict:
    """
    Compute resistive-heating parameters for a conductive-thread trace.

    Parameters
    ----------
    yarn : ResistiveYarn
        Yarn specification (Ω/m).
    length_m : float
        Length of the trace in metres.
    current_a : float
        Operating current in amperes.

    Returns
    -------
    dict with keys:
        resistance_ohm   — R = r_per_m * length_m          [Ω]
        power_w          — P = I² * R                       [W]
        voltage_drop_v   — V = I * R                        [V]
        current_a        — echo of input current             [A]
        length_m         — echo of input length              [m]
    """
    seg = HeaterSegment(yarn=yarn, length_m=length_m, current_a=current_a)
    return {
        "resistance_ohm": seg.resistance,
        "power_w": seg.power_w,
        "voltage_drop_v": seg.voltage_drop,
        "current_a": current_a,
        "length_m": length_m,
    }


# ---------------------------------------------------------------------------
# Conductive-thread routing over panel UV
# ---------------------------------------------------------------------------

@dataclass
class ThreadRoute:
    """
    A conductive-thread route as a polyline over a garment panel's UV space.

    UV coordinates are normalised: u ∈ [0,1] (along-grain / width axis),
    v ∈ [0,1] (cross-grain / height axis).

    Attributes
    ----------
    panel_name : str
        Identifier for the garment panel (e.g. "front-bodice").
    waypoints : list[tuple[float, float]]
        Ordered (u, v) waypoints defining the polyline route.
    panel_width_m : float
        Physical width of the panel in metres (for arc-length computation).
    panel_height_m : float
        Physical height of the panel in metres.
    yarn : ResistiveYarn | None
        Optional yarn specification; if set, enables electrical computation.
    """
    panel_name: str
    waypoints: list[tuple[float, float]]
    panel_width_m: float
    panel_height_m: float
    yarn: Optional[ResistiveYarn] = None

    def __post_init__(self) -> None:
        if len(self.waypoints) < 1:
            raise ValueError("At least one waypoint is required")
        if self.panel_width_m <= 0:
            raise ValueError(f"panel_width_m must be > 0, got {self.panel_width_m}")
        if self.panel_height_m <= 0:
            raise ValueError(f"panel_height_m must be > 0, got {self.panel_height_m}")
        for i, (u, v) in enumerate(self.waypoints):
            if not (0.0 <= u <= 1.0) or not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"waypoint[{i}] ({u}, {v}) is outside UV unit square [0,1]²"
                )

    @property
    def arc_length_m(self) -> float:
        """
        Compute the route arc length in metres by summing Euclidean segment
        distances scaled by the panel's physical dimensions.

            Δs = sqrt((Δu * W)² + (Δv * H)²)
        """
        W = self.panel_width_m
        H = self.panel_height_m
        total = 0.0
        for i in range(1, len(self.waypoints)):
            u0, v0 = self.waypoints[i - 1]
            u1, v1 = self.waypoints[i]
            du = (u1 - u0) * W
            dv = (v1 - v0) * H
            total += math.sqrt(du * du + dv * dv)
        return total

    @property
    def segment_lengths_m(self) -> list[float]:
        """Return per-segment arc lengths in metres."""
        W = self.panel_width_m
        H = self.panel_height_m
        lengths: list[float] = []
        for i in range(1, len(self.waypoints)):
            u0, v0 = self.waypoints[i - 1]
            u1, v1 = self.waypoints[i]
            du = (u1 - u0) * W
            dv = (v1 - v0) * H
            lengths.append(math.sqrt(du * du + dv * dv))
        return lengths

    def heating(self, current_a: float) -> Optional[dict]:
        """
        Compute heating for the full route given a current.

        Returns None if no yarn is attached.
        """
        if self.yarn is None:
            return None
        return heating_calc(self.yarn, self.arc_length_m, current_a)


def thread_route(
    panel_name: str,
    waypoints: list[tuple[float, float]],
    panel_width_m: float,
    panel_height_m: float,
    yarn: Optional[ResistiveYarn] = None,
) -> ThreadRoute:
    """
    Build a conductive-thread route polyline over a garment panel's UV space.

    Parameters
    ----------
    panel_name : str
        Panel identifier.
    waypoints : list[tuple[float, float]]
        Ordered (u, v) waypoints in normalised UV coordinates [0,1]×[0,1].
    panel_width_m : float
        Physical panel width in metres.
    panel_height_m : float
        Physical panel height in metres.
    yarn : ResistiveYarn | None
        Optional yarn; if provided, enables heating calculations.

    Returns
    -------
    ThreadRoute with arc_length_m and optional heating().
    """
    return ThreadRoute(
        panel_name=panel_name,
        waypoints=waypoints,
        panel_width_m=panel_width_m,
        panel_height_m=panel_height_m,
        yarn=yarn,
    )


# ---------------------------------------------------------------------------
# LED-fabric layout
# ---------------------------------------------------------------------------

@dataclass
class LEDNode:
    """
    Flora-class LED node specification.

    Attributes
    ----------
    name : str
        Part identifier (e.g. "Adafruit Flora NeoPixel", "WS2812B").
    vf_v : float
        Forward voltage in volts (Vf).  For multi-die LEDs, Vf is the
        combined per-die voltage (all dies driven together).
    if_ma : float
        Nominal operating current in milliamps (If).
    color : str
        Optional colour label ("R", "G", "B", "RGB", etc.).
    """
    name: str
    vf_v: float          # V
    if_ma: float         # mA
    color: str = "RGB"

    def __post_init__(self) -> None:
        if self.vf_v < 0:
            raise ValueError(f"vf_v must be ≥ 0, got {self.vf_v}")
        if self.if_ma < 0:
            raise ValueError(f"if_ma must be ≥ 0, got {self.if_ma}")


@dataclass
class LEDBranch:
    """
    One serial chain of LEDs with a current-limiting resistor.

    Attributes
    ----------
    nodes : list[LEDNode]
        Ordered LED nodes in the serial chain (N_s nodes).
    r_series_ohm : float
        Current-limiting resistor in ohms.  May be 0 if Vsupply == Σ Vf.
    """
    nodes: list[LEDNode]
    r_series_ohm: float = 0.0

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("LEDBranch must contain at least one LED node")
        if self.r_series_ohm < 0:
            raise ValueError(f"r_series_ohm must be ≥ 0, got {self.r_series_ohm}")

    @property
    def n_series(self) -> int:
        """Number of LEDs in series."""
        return len(self.nodes)

    @property
    def total_vf(self) -> float:
        """Sum of forward voltages in the chain."""
        return sum(n.vf_v for n in self.nodes)

    def branch_current_a(self, vsupply: float) -> float:
        """
        Compute branch current via Kirchhoff's voltage law.

            I_branch = (Vsupply - Σ Vf) / R_series

        If R_series == 0, current is undefined (open drive); we return 0.0
        to signal that the series resistor must be non-zero for a real circuit.
        When Vsupply < Σ Vf the branch is reverse-biased; return 0.0.
        """
        v_available = vsupply - self.total_vf
        if v_available <= 0.0:
            return 0.0
        if self.r_series_ohm == 0.0:
            # Ideal drive: no resistor — current is set by Vf match.
            # Treat as if_ma of first node for convenience.
            return self.nodes[0].if_ma / 1000.0
        return v_available / self.r_series_ohm


@dataclass
class LEDLayout:
    """
    A parallel-branches LED-fabric network.

    Topology
    --------
    Multiple LEDBranch objects are wired in parallel across Vsupply.
    Each branch is an independent series chain (Kirchhoff KVL per branch,
    KCL at the supply rail).

    Attributes
    ----------
    branches : list[LEDBranch]
        All parallel branches in the network.
    vsupply : float
        Supply voltage in volts (e.g. 3.3, 5.0).
    """
    branches: list[LEDBranch]
    vsupply: float

    def __post_init__(self) -> None:
        if not self.branches:
            raise ValueError("LEDLayout must have at least one branch")
        if self.vsupply <= 0:
            raise ValueError(f"vsupply must be > 0, got {self.vsupply}")

    @property
    def n_branches(self) -> int:
        return len(self.branches)

    @property
    def total_leds(self) -> int:
        return sum(b.n_series for b in self.branches)

    def branch_currents_a(self) -> list[float]:
        """Return current (A) for each parallel branch."""
        return [b.branch_current_a(self.vsupply) for b in self.branches]

    @property
    def total_current_a(self) -> float:
        """
        Total supply current = sum of all branch currents (Kirchhoff KCL).

            I_total = Σ_i I_branch_i
        """
        return sum(self.branch_currents_a())

    @property
    def total_power_w(self) -> float:
        """Approximate total power = Vsupply * I_total."""
        return self.vsupply * self.total_current_a

    def solve(self) -> dict:
        """
        Return a full solution dict:

            branch_currents_a  — list[float], per-branch currents
            total_current_a    — float, Σ branch currents (KCL)
            total_power_w      — float, Vsupply * I_total
            vsupply            — float
            n_branches         — int
            total_leds         — int
            branch_vf_sums     — list[float], Σ Vf per branch
        """
        branch_i = self.branch_currents_a()
        return {
            "branch_currents_a": branch_i,
            "total_current_a": sum(branch_i),
            "total_power_w": self.vsupply * sum(branch_i),
            "vsupply": self.vsupply,
            "n_branches": self.n_branches,
            "total_leds": self.total_leds,
            "branch_vf_sums": [b.total_vf for b in self.branches],
        }


def led_layout(
    vsupply: float,
    n_parallel: int,
    n_series: int,
    led: LEDNode,
    r_series_ohm: float = 0.0,
) -> LEDLayout:
    """
    Build a uniform LED-fabric grid layout.

    Creates *n_parallel* identical branches, each containing *n_series* copies
    of *led*, with *r_series_ohm* current-limiting resistor per branch.

    Parameters
    ----------
    vsupply : float
        Supply voltage in volts.
    n_parallel : int
        Number of parallel branches (columns of LEDs).
    n_series : int
        Number of LEDs in series per branch (rows of LEDs).
    led : LEDNode
        LED specification (Vf, If).
    r_series_ohm : float
        Current-limiting resistor per branch in ohms.

    Returns
    -------
    LEDLayout ready for solve().
    """
    if n_parallel < 1:
        raise ValueError(f"n_parallel must be ≥ 1, got {n_parallel}")
    if n_series < 1:
        raise ValueError(f"n_series must be ≥ 1, got {n_series}")

    branch = LEDBranch(
        nodes=[led] * n_series,
        r_series_ohm=r_series_ohm,
    )
    branches = [branch] * n_parallel
    return LEDLayout(branches=branches, vsupply=vsupply)


# ---------------------------------------------------------------------------
# Convenience: common yarn presets
# ---------------------------------------------------------------------------

YARN_SHIELDEX_117 = ResistiveYarn(
    name="Shieldex 117/17 dtex 2-ply",
    resistance_per_metre=30.0,   # Ω/m  (typical for this silver-coated yarn)
    max_current_a=0.05,
    notes="Silver-coated nylon, 2-ply, ~30 Ω/m",
)

YARN_BEKINOX_50 = ResistiveYarn(
    name="Bekinox BK 50/2 stainless",
    resistance_per_metre=4.5,    # Ω/m  (stainless steel yarn)
    max_current_a=0.2,
    notes="Stainless steel 316L, 2-ply, ~4.5 Ω/m",
)

LED_FLORA_NEOPIXEL = LEDNode(
    name="Adafruit Flora NeoPixel (WS2812B)",
    vf_v=3.5,    # V  (combined RGB at full brightness)
    if_ma=60.0,  # mA (20 mA per channel × 3 channels)
    color="RGB",
)

LED_FLORA_RGB = LEDNode(
    name="Adafruit Flora RGB Smart NeoPixel v2",
    vf_v=3.5,
    if_ma=60.0,
    color="RGB",
)
