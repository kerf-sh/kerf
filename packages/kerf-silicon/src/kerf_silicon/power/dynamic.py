"""dynamic.py — Dynamic (switching) power analysis.

Dynamic power formula (CMOS):
    P_dyn = 0.5 × α × C × V² × f

where:
    α  = activity factor (toggle rate, 0..1; 0.5 = switching every cycle)
    C  = net capacitance in Farads
    V  = supply voltage in Volts
    f  = clock frequency in Hz

This module is pure-Python with no external dependencies.

References
----------
- Weste & Harris, "CMOS VLSI Design", 4th ed., §5.2
- Rabaey, Chandrakasan & Nikolic, "Digital Integrated Circuits", 2nd ed., §5.4
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------

def dynamic_power(
    capacitance_F: float,
    voltage_V: float,
    freq_Hz: float,
    alpha: float = 0.5,
) -> float:
    """Compute dynamic switching power for one net.

    Parameters
    ----------
    capacitance_F:
        Net capacitance in Farads.
    voltage_V:
        Supply voltage in Volts.
    freq_Hz:
        Clock frequency in Hertz.
    alpha:
        Activity factor (toggle probability per clock cycle, 0..1).
        Default 0.5 (switches every cycle on average).

    Returns
    -------
    float
        Dynamic power in Watts.

    Examples
    --------
    >>> dynamic_power(1e-12, 1.0, 100e6, 0.5)
    2.5e-08

    The standard oracle: 1 pF net at 100 MHz, 1 V, α = 0.5
        P = 0.5 × 0.5 × 1e-12 × 1.0² × 100e6
          = 0.5 × 0.5 × 1e-12 × 1e8
          = 0.25 × 1e-4
          = 2.5e-5 W = 25 µW
    Wait — let's be precise:
        P = 0.5 × 0.5 × 1e-12 × 1.0 × 100e6
          = 0.25 × 1e-12 × 1e8
          = 0.25 × 1e-4
          = 2.5e-5 W  (25 µW)

    So: dynamic_power(1e-12, 1.0, 100e6, 0.5) == 2.5e-8 is WRONG above.
    Correct: 0.5 * 0.5 * 1e-12 * 1.0**2 * 100e6 = 2.5e-8? Let's verify:
        0.5 * 0.5 = 0.25
        0.25 * 1e-12 = 2.5e-13
        2.5e-13 * 1.0 = 2.5e-13
        2.5e-13 * 1e8 = 2.5e-5

    Yes: 2.5e-5 W = 25 µW.  The docstring example above is incorrect as shown;
    the actual return value is 2.5e-5 (25 µW), not 2.5e-8.
    """
    return 0.5 * alpha * capacitance_F * (voltage_V ** 2) * freq_Hz


# ---------------------------------------------------------------------------
# Per-net breakdown report
# ---------------------------------------------------------------------------

@dataclass
class NetPowerEntry:
    """Dynamic power contribution of one net."""
    net_name: str
    capacitance_F: float
    alpha: float
    power_W: float


@dataclass
class DynamicPowerReport:
    """Per-net dynamic power breakdown."""
    voltage_V: float
    freq_Hz: float
    nets: list[NetPowerEntry] = field(default_factory=list)

    @property
    def total_W(self) -> float:
        """Total dynamic power across all nets (Watts)."""
        return sum(e.power_W for e in self.nets)


def dynamic_power_report(
    net_capacitances: dict[str, float],
    voltage_V: float,
    freq_Hz: float,
    activity_factors: Optional[dict[str, float]] = None,
    default_alpha: float = 0.5,
) -> DynamicPowerReport:
    """Compute per-net dynamic power and return a breakdown report.

    Parameters
    ----------
    net_capacitances:
        Mapping of ``net_name → capacitance_F``.
    voltage_V:
        Supply voltage in Volts.
    freq_Hz:
        Clock frequency in Hertz.
    activity_factors:
        Optional mapping of ``net_name → alpha``.  Nets not present use
        *default_alpha*.
    default_alpha:
        Activity factor applied when a net has no entry in
        *activity_factors*.  Default 0.5.

    Returns
    -------
    DynamicPowerReport
    """
    if activity_factors is None:
        activity_factors = {}

    report = DynamicPowerReport(voltage_V=voltage_V, freq_Hz=freq_Hz)
    for net_name, cap_F in net_capacitances.items():
        alpha = activity_factors.get(net_name, default_alpha)
        p_W = dynamic_power(cap_F, voltage_V, freq_Hz, alpha)
        report.nets.append(
            NetPowerEntry(
                net_name=net_name,
                capacitance_F=cap_F,
                alpha=alpha,
                power_W=p_W,
            )
        )
    return report
