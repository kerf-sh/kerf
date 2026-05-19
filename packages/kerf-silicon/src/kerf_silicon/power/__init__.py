"""kerf_silicon.power — Power analysis: switching activity × capacitance.

Computes total power = dynamic + leakage from:
  - per-net capacitance (from T-246 RC extraction / SPEF)
  - per-cell leakage power (from T-241 Liberty)
  - per-net switching activity factor α (from SAIF or explicit values)

Quick start::

    from kerf_silicon.power.dynamic import dynamic_power
    from kerf_silicon.power.leakage import leakage_power_sum
    from kerf_silicon.power.saif_parser import parse_saif, parse_saif_file

    # Dynamic power for a single net
    P = dynamic_power(capacitance_F=1e-12, voltage_V=1.0, freq_Hz=100e6, alpha=0.5)
    # → 2.5e-8 W  (25 µW)

    # Leakage from Liberty
    from kerf_silicon.liberty import parse
    lib = parse(liberty_text)
    P_leak = leakage_power_sum(lib)

    # SAIF activity factors
    activity = parse_saif(saif_text)
    alpha = activity["net_name"].alpha
"""
from kerf_silicon.power.dynamic import dynamic_power, dynamic_power_report
from kerf_silicon.power.leakage import leakage_power_sum, leakage_per_cell
from kerf_silicon.power.saif_parser import (
    NetActivity,
    SaifData,
    parse_saif,
    parse_saif_file,
)

__all__ = [
    # dynamic
    "dynamic_power",
    "dynamic_power_report",
    # leakage
    "leakage_power_sum",
    "leakage_per_cell",
    # saif
    "NetActivity",
    "SaifData",
    "parse_saif",
    "parse_saif_file",
]
