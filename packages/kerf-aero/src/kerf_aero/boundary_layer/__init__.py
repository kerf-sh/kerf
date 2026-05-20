"""Integral boundary-layer methods for XFOIL-class viscous coupling.

Modules
-------
laminar        -- Falkner-Skan integral method (Thwaites)
transition_en  -- e^N / Tollmien-Schlichting transition criterion
turbulent      -- Head + Green lag-entrainment turbulent BL
"""
from .laminar import march_laminar, LaminarState
from .transition_en import TransitionDetector
from .turbulent import march_turbulent, TurbulentState

__all__ = [
    "march_laminar",
    "LaminarState",
    "TransitionDetector",
    "march_turbulent",
    "TurbulentState",
]
