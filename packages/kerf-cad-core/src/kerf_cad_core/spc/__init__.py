"""
kerf_cad_core.spc — Statistical Process Control (SPC) control charts.

Public API:

    from kerf_cad_core.spc import xbar_r_chart, xbar_s_chart, cusum_chart
    from kerf_cad_core.spc import ewma_chart, run_rules

Charts
------
  xbar_r_chart  — Shewhart X̄-R chart (subgroup mean + range)
  xbar_s_chart  — Shewhart X̄-S chart (subgroup mean + std-dev)
  cusum_chart   — Tabular CUSUM with optional fast-initial-response
  ewma_chart    — EWMA chart with steady-state or transient limits
  run_rules     — Nelson rules 1–8 + Western Electric run rules

All functions are pure Python (no numpy) and return dicts with:
  * control limits
  * per-subgroup / per-point statistics
  * flagged out-of-control points

References
----------
Montgomery, D.C. (2020). Introduction to Statistical Quality Control, 8th ed.
ASTM E2587-16. Standard Practice for Use of Control Charts in SPC.
Nelson, L.S. (1984). "The Shewhart Control Chart — Tests for Special Causes."
Western Electric Company (1956). Statistical Quality Control Handbook.

Author: imranparuk
"""

from kerf_cad_core.spc.charts import (
    xbar_r_chart,
    xbar_s_chart,
    cusum_chart,
    ewma_chart,
    run_rules,
)

__all__ = [
    "xbar_r_chart",
    "xbar_s_chart",
    "cusum_chart",
    "ewma_chart",
    "run_rules",
]
