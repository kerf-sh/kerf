"""Mold-flow v1: injection-moulding fill simulation via Hele-Shaw approximation.

Exports
-------
ShellMesh          — thin-shell triangle mesh (mid-plane representation)
GateLocation       — injection gate (node index + optional pressure)
CrossWLFCard       — Cross-WLF viscosity model parameters
InjectionConditions — process conditions (melt T, injection P, fill time)
MoldFlowResult     — fill-time map, weld-line segments, short-shot flag
run_moldflow       — top-level entry point

Out of scope for v1 (follow-up tickets):
  * Residual stress / warpage (requires 3-D through-thickness integration)
  * Fibre orientation (Folgar-Tucker advection)
  * Packing / hold-pressure phase
  * Crystallisation kinetics
"""

from kerf_manufacturing.moldflow.hele_shaw import (
    ShellMesh,
    GateLocation,
    InjectionConditions,
    MoldFlowResult,
    run_moldflow,
)
from kerf_manufacturing.moldflow.materials import CrossWLFCard

__all__ = [
    "ShellMesh",
    "GateLocation",
    "CrossWLFCard",
    "InjectionConditions",
    "MoldFlowResult",
    "run_moldflow",
]
