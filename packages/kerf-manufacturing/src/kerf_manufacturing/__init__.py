"""kerf-manufacturing: manufacturing process simulation plugins for Kerf.

v1 ships injection-moulding fill simulation (Hele-Shaw approximation).

Out of scope for v1 (planned follow-up tickets):
- Residual stress & warpage prediction
- Fibre orientation (Folgar-Tucker model)
- Cooling-circuit optimisation
- Packing / hold-pressure phase
"""

from kerf_manufacturing.moldflow import (
    ShellMesh,
    GateLocation,
    CrossWLFCard,
    InjectionConditions,
    MoldFlowResult,
    run_moldflow,
)

__all__ = [
    "ShellMesh",
    "GateLocation",
    "CrossWLFCard",
    "InjectionConditions",
    "MoldFlowResult",
    "run_moldflow",
]
