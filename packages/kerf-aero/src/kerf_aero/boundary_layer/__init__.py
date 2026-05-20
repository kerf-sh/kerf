"""Integral boundary-layer package for viscous-inviscid coupling.

Sub-modules
-----------
laminar         : Falkner-Skan integral marching (Thwaites method)
turbulent       : Head / Green lag-entrainment integral marching
transition_en   : e^N / Michel transition-criterion detector

Public entry-points
-------------------
march(ue, s, Re, transition_N=9)
    Walk the full boundary layer (laminar → transition → turbulent) along
    a surface with edge-velocity distribution ue(s), arc-length array s.
    Returns a BLResult dataclass.
"""

from .laminar import march_laminar, BLState
from .turbulent import march_turbulent
from .transition_en import find_transition

__all__ = ["march_laminar", "march_turbulent", "find_transition", "BLState"]
