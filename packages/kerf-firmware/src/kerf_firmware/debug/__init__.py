"""
kerf_firmware.debug — RTOS-aware debugger bridge.

Public API
----------
DebugSession        — manages the OpenOCD + GDB-MI lifecycle
TaskInfo            — named tuple for a single RTOS task snapshot
SyncObject          — mutex / semaphore / queue snapshot with dependency edges
DebugBridge         — high-level facade used by the CLI and routes
"""

from .openocd import OpenOCDSession, OpenOCDNotInstalledError, GDBNotInstalledError
from .rtos_inspect import (
    RTOSInspector,
    TaskInfo,
    SyncObject,
    DependencyEdge,
    DebugSnapshot,
)

__all__ = [
    "OpenOCDSession",
    "OpenOCDNotInstalledError",
    "GDBNotInstalledError",
    "RTOSInspector",
    "TaskInfo",
    "SyncObject",
    "DependencyEdge",
    "DebugSnapshot",
]
