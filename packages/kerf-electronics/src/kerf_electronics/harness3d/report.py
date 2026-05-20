"""
kerf_electronics.harness3d.report
====================================
Per-circuit length / gauge / voltage-drop report.

For each routed circuit the report provides:

  * Total 3D routed length (mm → m for resistance calculation)
  * Wire gauge (AWG), auto-selected from current rating if not specified
  * Resistance per metre (Ω/m) from AWG table (copper, 20 °C)
  * Total circuit resistance (Ω) = R/m × length_m
  * Voltage drop at nominal current:  ΔV = I × R  (V)
  * Percentage voltage drop relative to supply voltage

Formula
-------
    R_wire (Ω)    = resistance_per_m (Ω/m) × length_m
    V_drop (V)    = current_a × R_wire
    pct_drop (%)  = 100 × V_drop / supply_v

All calculations use the single-conductor (one-way) resistance.  For a
return-path circuit multiply by 2; for in-vehicle 12 V systems the
one-way model is conventional unless otherwise noted.

Units: inputs in mm / A / V; outputs in mm / Ω / V.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from kerf_electronics.harness3d.router import RouteResult, awg_resistance_per_m


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CircuitReport:
    """
    Voltage-drop report for a single circuit.

    Attributes
    ----------
    from_pin        Source pin name
    to_pin          Destination pin name
    gauge_awg       Selected AWG gauge
    length_mm       3D routed length (mm)
    resistance_ohm  Total wire resistance (Ω)
    voltage_drop_v  Voltage drop at nominal current (V)
    pct_drop        Percentage drop relative to supply_v
    current_a       Nominal current used in the calculation
    supply_v        Nominal supply voltage
    """
    from_pin: str
    to_pin: str
    gauge_awg: int
    length_mm: float
    resistance_ohm: float
    voltage_drop_v: float
    pct_drop: float
    current_a: float
    supply_v: float

    def to_dict(self) -> dict:
        return {
            "from_pin": self.from_pin,
            "to_pin": self.to_pin,
            "gauge_awg": self.gauge_awg,
            "length_mm": round(self.length_mm, 3),
            "length_m": round(self.length_mm / 1000.0, 6),
            "resistance_ohm": round(self.resistance_ohm, 6),
            "current_a": self.current_a,
            "voltage_drop_v": round(self.voltage_drop_v, 6),
            "pct_drop": round(self.pct_drop, 4),
            "supply_v": self.supply_v,
        }


@dataclass
class HarnessReport:
    """
    Complete harness voltage-drop report.

    Attributes
    ----------
    circuits        Per-circuit reports
    total_length_mm Sum of all circuit lengths
    max_drop_v      Worst-case voltage drop (V)
    max_pct_drop    Worst-case drop as % of supply voltage
    failed_edges    Edges that could not be routed
    """
    circuits: list[CircuitReport] = field(default_factory=list)
    total_length_mm: float = 0.0
    max_drop_v: float = 0.0
    max_pct_drop: float = 0.0
    failed_edges: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "circuit_count": len(self.circuits),
            "total_length_mm": round(self.total_length_mm, 3),
            "max_drop_v": round(self.max_drop_v, 6),
            "max_pct_drop": round(self.max_pct_drop, 4),
            "failed_edges": self.failed_edges,
            "circuits": [c.to_dict() for c in self.circuits],
        }


# ---------------------------------------------------------------------------
# Report function
# ---------------------------------------------------------------------------

def voltage_drop_report(
    routes: Sequence[RouteResult],
    supply_v: float = 12.0,
) -> HarnessReport:
    """
    Compute per-circuit voltage-drop report for a routed harness.

    Parameters
    ----------
    routes
        List of RouteResult from route_harness_3d.
    supply_v
        Nominal supply voltage (V); used to compute percentage drop.
        Default: 12 V (standard automotive).

    Returns
    -------
    HarnessReport
    """
    circuits: list[CircuitReport] = []
    failed: list[str] = []

    for r in routes:
        if not r.ok:
            failed.append(f"{r.edge.from_pin}→{r.edge.to_pin}: {r.reason}")
            continue

        awg = r.edge.gauge_awg if r.edge.gauge_awg is not None else 20
        length_m = r.length_mm / 1000.0
        r_per_m = awg_resistance_per_m(awg)
        resistance = r_per_m * length_m
        v_drop = r.edge.current_a * resistance
        pct = (v_drop / supply_v * 100.0) if supply_v > 0 else 0.0

        circuits.append(CircuitReport(
            from_pin=r.edge.from_pin,
            to_pin=r.edge.to_pin,
            gauge_awg=awg,
            length_mm=r.length_mm,
            resistance_ohm=resistance,
            voltage_drop_v=v_drop,
            pct_drop=pct,
            current_a=r.edge.current_a,
            supply_v=supply_v,
        ))

    total_length = sum(c.length_mm for c in circuits)
    max_drop = max((c.voltage_drop_v for c in circuits), default=0.0)
    max_pct = max((c.pct_drop for c in circuits), default=0.0)

    return HarnessReport(
        circuits=circuits,
        total_length_mm=total_length,
        max_drop_v=max_drop,
        max_pct_drop=max_pct,
        failed_edges=failed,
    )
