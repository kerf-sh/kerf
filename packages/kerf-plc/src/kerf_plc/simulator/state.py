"""
kerf_plc.simulator.state
------------------------
Mutable scan-cycle state: variable store + timestamp.
"""
from __future__ import annotations

from typing import Any


class ScanState:
    """Holds all variable values for one scan cycle.

    Variables are stored as a flat dict[str, bool | int | float].
    The simulator owns the canonical instance; function blocks receive a
    reference so they can read and write variables in-place.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._vars: dict[str, Any] = dict(initial) if initial else {}
        # Elapsed simulated time in milliseconds (accumulated across steps).
        self.elapsed_ms: float = 0.0

    # ------------------------------------------------------------------
    # Variable access
    # ------------------------------------------------------------------

    def get(self, name: str, default: Any = False) -> Any:
        return self._vars.get(name, default)

    def set(self, name: str, value: Any) -> None:
        self._vars[name] = value

    def update(self, mapping: dict[str, Any]) -> None:
        self._vars.update(mapping)

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of the current variable store."""
        return dict(self._vars)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ScanState(elapsed_ms={self.elapsed_ms}, vars={self._vars!r})"
