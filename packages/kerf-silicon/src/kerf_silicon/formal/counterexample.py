"""counterexample.py — extract a witness assignment on BDD mismatch.

Given a counterexample assignment (a dict mapping input names to 0/1 values),
this module provides utilities to:

  • evaluate both netlists under the assignment and show which outputs differ.
  • format a human-readable report.

Public API
----------
evaluate_netlist(netlist, assignment) -> dict[str, int]
    Simulate a combinational netlist for a specific input assignment.
    Returns {output_name: 0|1, ...}.

explain_counterexample(netlist_a, netlist_b, cex_assignment) -> str
    Return a formatted string describing the mismatch.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Gate-level simulation (truth table evaluation)
# ---------------------------------------------------------------------------

_GATE_FNS = {
    "buf":  lambda vals: vals[0],
    "not":  lambda vals: 1 - vals[0],
    "and":  lambda vals: int(all(v for v in vals)),
    "or":   lambda vals: int(any(v for v in vals)),
    "xor":  lambda vals: vals[0] ^ vals[1] if len(vals) == 2 else _multi_xor(vals),
    "nand": lambda vals: 1 - int(all(v for v in vals)),
    "nor":  lambda vals: 1 - int(any(v for v in vals)),
    "xnor": lambda vals: 1 - (vals[0] ^ vals[1]) if len(vals) == 2 else 1 - _multi_xor(vals),
}


def _multi_xor(vals: list[int]) -> int:
    result = 0
    for v in vals:
        result ^= v
    return result


def evaluate_netlist(
    netlist: dict[str, Any],
    assignment: dict[str, int],
) -> dict[str, int]:
    """Simulate *netlist* under *assignment* and return the output values.

    Parameters
    ----------
    netlist:
        Flat gate-level netlist dict (``inputs``, ``outputs``, ``gates``).
    assignment:
        Mapping of primary-input name → 0 or 1.

    Returns
    -------
    dict[str, int]
        Output net values under the given assignment.
    """
    inputs: list[str] = netlist.get("inputs", [])
    outputs: list[str] = netlist.get("outputs", [])
    gates: list[dict[str, Any]] = netlist.get("gates", [])

    # Seed the value map with primary inputs.
    values: dict[str, int] = {}
    for pi in inputs:
        if pi not in assignment:
            raise ValueError(
                f"Primary input '{pi}' not present in the assignment. "
                f"Got: {sorted(assignment.keys())}"
            )
        values[pi] = int(assignment[pi])

    # Evaluate gates in order (assumes topological order; if not, will raise).
    for gate in gates:
        gtype = gate["type"].lower()
        gate_inputs = gate["input"] if "input" in gate else gate["inputs"]
        if isinstance(gate_inputs, str):
            gate_inputs = [gate_inputs]
        gate_output = gate["output"]

        fn = _GATE_FNS.get(gtype)
        if fn is None:
            raise ValueError(f"Unsupported gate type: '{gtype}'")

        try:
            in_vals = [values[n] for n in gate_inputs]
        except KeyError as exc:
            raise ValueError(
                f"Gate '{gate_output}' ({gtype}) references undefined net {exc}"
            ) from exc

        values[gate_output] = fn(in_vals)

    return {out: values[out] for out in outputs if out in values}


# ---------------------------------------------------------------------------
# Human-readable explanation
# ---------------------------------------------------------------------------


def explain_counterexample(
    netlist_a: dict[str, Any],
    netlist_b: dict[str, Any],
    cex_assignment: dict[str, int],
) -> str:
    """Return a human-readable explanation of the first mismatch.

    Parameters
    ----------
    netlist_a, netlist_b:
        The two netlists being compared.
    cex_assignment:
        The witness assignment returned by ``EquivResult.counterexample``.

    Returns
    -------
    str
        Multi-line string describing the mismatch.
    """
    vals_a = evaluate_netlist(netlist_a, cex_assignment)
    vals_b = evaluate_netlist(netlist_b, cex_assignment)

    lines = ["Counterexample witness:", f"  Input assignment: {cex_assignment}"]

    outputs = netlist_a.get("outputs", [])
    for out in outputs:
        va = vals_a.get(out, "?")
        vb = vals_b.get(out, "?")
        match_marker = "✓" if va == vb else "✗ MISMATCH"
        lines.append(f"  {out}: netlist_a={va}  netlist_b={vb}  {match_marker}")

    return "\n".join(lines)
