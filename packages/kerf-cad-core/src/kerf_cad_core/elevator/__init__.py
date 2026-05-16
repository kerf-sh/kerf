"""
kerf_cad_core.elevator — vertical-transportation engineering.

Distinct from crane/, dynamics/, and beltchain/; covers passenger and goods
lifts (traction and hydraulic), escalators, and moving walks.

Public API (re-exported for convenience):

    from kerf_cad_core.elevator import (
        traction_lift,
        hydraulic_lift,
        motor_power,
        kinematics,
        traffic_analysis,
        buffer_stroke,
        escalator,
    )

References
----------
CIBSE Guide D: Transportation Systems in Buildings, 4th ed.
EN 81-1:1998+A3:2009 — Safety rules for traction lifts
EN 81-2:1998+A3:2009 — Safety rules for hydraulic lifts
ISO 4190-1 — Lift (elevator) installations, classification
Barney, G.C. — Elevator Traffic Handbook (2003)
Strakosch, G.R. — The Vertical Transportation Handbook, 4th ed.

Author: imranparuk
"""

from kerf_cad_core.elevator.design import (
    traction_lift,
    hydraulic_lift,
    motor_power,
    kinematics,
    traffic_analysis,
    buffer_stroke,
    escalator,
)

__all__ = [
    "traction_lift",
    "hydraulic_lift",
    "motor_power",
    "kinematics",
    "traffic_analysis",
    "buffer_stroke",
    "escalator",
]
