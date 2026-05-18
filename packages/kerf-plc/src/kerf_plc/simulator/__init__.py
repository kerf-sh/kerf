"""
kerf_plc.simulator
------------------
IEC 61131-3 scan-cycle simulator (LD + ST).

Public surface::

    from kerf_plc.simulator import Simulator
    from kerf_plc.simulator.function_blocks import TON, CTU, R_TRIG, F_TRIG, SR, RS
    from kerf_plc.simulator.state import ScanState
"""
from .scan import Simulator
from .state import ScanState
from .function_blocks import (
    TON,
    TOF,
    CTU,
    CTD,
    R_TRIG,
    F_TRIG,
    SR,
    RS,
    FB_REGISTRY,
)

__all__ = [
    "Simulator",
    "ScanState",
    "TON",
    "TOF",
    "CTU",
    "CTD",
    "R_TRIG",
    "F_TRIG",
    "SR",
    "RS",
    "FB_REGISTRY",
]
