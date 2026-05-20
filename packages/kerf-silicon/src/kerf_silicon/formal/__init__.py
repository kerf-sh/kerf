"""kerf_silicon.formal — combinational formal equivalence checking.

Public surface
--------------
equiv(netlist_a, netlist_b) -> EquivResult
    Check whether two combinational gate-level netlists are functionally
    equivalent on all primary outputs.

EquivResult
    .equivalent   : bool
    .per_output   : dict[str, bool]
    .counterexample : dict | None  ({"output": str, "assignment": {str:int}})

Netlist format (flat JSON)
--------------------------
{
    "inputs":  ["a", "b"],
    "outputs": ["sum", "cout"],
    "gates": [
        {"type": "xor", "inputs": ["a", "b"], "output": "sum"},
        {"type": "and", "inputs": ["a", "b"], "output": "cout"}
    ]
}

Sequential scope
----------------
v1 is combinational only.  Cut each register boundary into a primary
output (register input) and a primary input (register output) before
calling ``equiv``.  Sequential equivalence is handled by T-249 cocotb.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kerf_silicon.formal.equiv import check_equiv


@dataclass
class EquivResult:
    """Result of a formal equivalence check."""

    equivalent: bool
    """True iff ALL primary outputs are functionally equivalent."""

    per_output: dict[str, bool]
    """Per-output equivalence flags (output name → True/False)."""

    counterexample: dict[str, Any] | None
    """
    On mismatch: the first witness that reveals a difference.

    Shape::

        {
            "output":     "<output-name>",
            "assignment": {"<input>": 0|1, ...}
        }

    ``None`` when ``equivalent`` is True.
    """


def equiv(
    netlist_a: dict[str, Any],
    netlist_b: dict[str, Any],
) -> EquivResult:
    """Check formal equivalence of two combinational gate-level netlists.

    Parameters
    ----------
    netlist_a, netlist_b:
        Flat gate-level netlist dicts.  Both must declare the same set of
        primary inputs and primary outputs.

    Returns
    -------
    EquivResult
    """
    raw = check_equiv(netlist_a, netlist_b)
    return EquivResult(
        equivalent=raw["equivalent"],
        per_output=raw["per_output"],
        counterexample=raw["counterexample"],
    )


__all__ = ["equiv", "EquivResult"]
