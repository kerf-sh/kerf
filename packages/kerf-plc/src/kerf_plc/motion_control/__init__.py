"""
kerf_plc.motion_control — PLCopen Motion Control Part 1 V2.0 function blocks.

Public API
----------
AxisState           Minimal axis state carrier (position, velocity, power, profile).
ErrorID             Error identifier enumeration.
BufferMode          Buffer-mode enumeration.

MC_Power            Enable / disable axis power.
MC_Halt             Controlled deceleration to standstill.
MC_Stop             Emergency (immediate) stop.
MC_MoveAbsolute     Move to absolute position.
MC_MoveRelative     Move by relative distance.
MC_MoveVelocity     Move at velocity (indefinite).
MC_Home             Run homing sequence.
"""
from kerf_plc.motion_control.blocks import (
    AxisState,
    BufferMode,
    ErrorID,
    HomeOutputs,
    HaltOutputs,
    MC_Halt,
    MC_Home,
    MC_MoveAbsolute,
    MC_MoveRelative,
    MC_MoveVelocity,
    MC_Power,
    MC_Stop,
    MoveAbsoluteOutputs,
    MoveRelativeOutputs,
    MoveVelocityOutputs,
    PowerOutputs,
    StopOutputs,
)

__all__ = [
    "AxisState",
    "BufferMode",
    "ErrorID",
    "HomeOutputs",
    "HaltOutputs",
    "MC_Halt",
    "MC_Home",
    "MC_MoveAbsolute",
    "MC_MoveRelative",
    "MC_MoveVelocity",
    "MC_Power",
    "MC_Stop",
    "MoveAbsoluteOutputs",
    "MoveRelativeOutputs",
    "MoveVelocityOutputs",
    "PowerOutputs",
    "StopOutputs",
]
