"""equiv.py — combinational netlist → per-output BDD → BDD equality.

Given two gate-level netlists (flat JSON, see schema below), builds a BDD
for each primary output and checks structural equivalence via BDD identity.

Netlist JSON schema
-------------------
{
    "inputs":  ["a", "b", ...],
    "outputs": ["sum", "cout", ...],
    "gates": [
        {"type": "xor",  "inputs": ["a", "b"], "output": "sum"},
        {"type": "and",  "inputs": ["a", "b"], "output": "cout"},
        ...
    ]
}

Supported gate types (case-insensitive):
    buf, not, and, or, xor, nand, nor, xnor

Register boundaries
-------------------
Sequential elements are *not* supported in v1.  Each register input/output
should be pre-split into separate primary inputs/outputs by the caller before
invoking ``build_output_bdds``.

Public API
----------
build_output_bdds(netlist, engine) -> dict[str, BDDNode]
    Compiles a flat netlist into one BDD node per output wire.

check_equiv(netlist_a, netlist_b) -> dict[str, bool | dict]
    Full per-output equivalence report.
"""

from __future__ import annotations

import logging
from typing import Any

from kerf_silicon.formal.bdd import BDDEngine

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Netlist compilation
# ---------------------------------------------------------------------------

_GATE_OPS = frozenset(
    ["buf", "not", "and", "or", "xor", "nand", "nor", "xnor"]
)


def _net_value(net_name: str, env: dict[str, Any], engine: BDDEngine) -> Any:
    """Return the BDD node bound to *net_name* in *env*.

    Raises ``KeyError`` if the net has not been computed yet (topological
    ordering violation) or is not a primary input.
    """
    try:
        return env[net_name]
    except KeyError:
        raise KeyError(
            f"Net '{net_name}' referenced before it was defined. "
            "Ensure gates are listed in topological order."
        ) from None


def _topo_sort(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return gates in topological order (inputs before outputs).

    Uses a simple iterative Kahn's algorithm on the gate output → input
    dependency graph.
    """
    # Map output wire → gate that drives it
    driver: dict[str, dict[str, Any]] = {}
    for g in gates:
        out = g["output"]
        if out in driver:
            raise ValueError(
                f"Multiple drivers for net '{out}': "
                f"gate types {driver[out]['type']!r} and {g['type']!r}"
            )
        driver[out] = g

    # Compute in-degree: how many gate-outputs feed this gate's inputs
    in_degree: dict[str, int] = {g["output"]: 0 for g in gates}
    dependents: dict[str, list[str]] = {g["output"]: [] for g in gates}

    for g in gates:
        for inp in g["inputs"]:
            if inp in driver:  # inp driven by another gate
                in_degree[g["output"]] += 1
                dependents[inp].append(g["output"])

    queue = [g["output"] for g in gates if in_degree[g["output"]] == 0]
    sorted_outs: list[str] = []

    while queue:
        out = queue.pop(0)
        sorted_outs.append(out)
        for dep in dependents.get(out, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(sorted_outs) != len(gates):
        cycle_nets = [o for o in in_degree if in_degree[o] > 0]
        raise ValueError(
            f"Combinational loop detected involving nets: {cycle_nets!r}"
        )

    return [driver[o] for o in sorted_outs]


def build_output_bdds(
    netlist: dict[str, Any],
    engine: BDDEngine,
) -> dict[str, Any]:
    """Compile *netlist* into one BDD node per primary output.

    Parameters
    ----------
    netlist:
        Parsed netlist dict with keys ``inputs``, ``outputs``, ``gates``.
    engine:
        A :class:`BDDEngine` instance (shared across both netlists for
        proper variable binding).

    Returns
    -------
    dict[str, BDDNode]
        Mapping output-name → BDD node.
    """
    inputs: list[str] = netlist.get("inputs", [])
    outputs: list[str] = netlist.get("outputs", [])
    gates: list[dict[str, Any]] = netlist.get("gates", [])

    # Seed the environment with primary-input BDD variables.
    # All primary inputs must share the same engine so variable names
    # are mapped to the same BDD variables.
    env: dict[str, Any] = {}
    for pi in inputs:
        env[pi] = engine.var(pi)

    # Topological sort to ensure we process drivers before users.
    ordered_gates = _topo_sort(gates)

    for gate in ordered_gates:
        gtype = gate["type"].lower()
        gate_inputs = gate["inputs"]
        gate_output = gate["output"]

        if gtype not in _GATE_OPS:
            raise ValueError(
                f"Unsupported gate type '{gtype}'. "
                f"Supported: {sorted(_GATE_OPS)}"
            )

        if gtype == "buf":
            if len(gate_inputs) != 1:
                raise ValueError(f"buf gate '{gate_output}' needs exactly 1 input")
            env[gate_output] = _net_value(gate_inputs[0], env, engine)

        elif gtype == "not":
            if len(gate_inputs) != 1:
                raise ValueError(f"not gate '{gate_output}' needs exactly 1 input")
            a = _net_value(gate_inputs[0], env, engine)
            env[gate_output] = engine.apply_not(a)

        elif gtype == "and":
            if len(gate_inputs) < 2:
                raise ValueError(f"and gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_and(result, _net_value(inp, env, engine))
            env[gate_output] = result

        elif gtype == "or":
            if len(gate_inputs) < 2:
                raise ValueError(f"or gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_or(result, _net_value(inp, env, engine))
            env[gate_output] = result

        elif gtype == "xor":
            if len(gate_inputs) < 2:
                raise ValueError(f"xor gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_xor(result, _net_value(inp, env, engine))
            env[gate_output] = result

        elif gtype == "nand":
            if len(gate_inputs) < 2:
                raise ValueError(f"nand gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_and(result, _net_value(inp, env, engine))
            env[gate_output] = engine.apply_not(result)

        elif gtype == "nor":
            if len(gate_inputs) < 2:
                raise ValueError(f"nor gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_or(result, _net_value(inp, env, engine))
            env[gate_output] = engine.apply_not(result)

        elif gtype == "xnor":
            if len(gate_inputs) < 2:
                raise ValueError(f"xnor gate '{gate_output}' needs ≥ 2 inputs")
            result = _net_value(gate_inputs[0], env, engine)
            for inp in gate_inputs[1:]:
                result = engine.apply_xor(result, _net_value(inp, env, engine))
            env[gate_output] = engine.apply_not(result)

    # Extract output nodes
    output_bdds: dict[str, Any] = {}
    for out in outputs:
        if out not in env:
            raise ValueError(
                f"Output '{out}' is not driven by any gate or primary input"
            )
        output_bdds[out] = env[out]

    return output_bdds


# ---------------------------------------------------------------------------
# Per-output equivalence check
# ---------------------------------------------------------------------------


def check_equiv(
    netlist_a: dict[str, Any],
    netlist_b: dict[str, Any],
) -> dict[str, Any]:
    """Check per-output BDD equivalence between *netlist_a* and *netlist_b*.

    Both netlists must declare the same set of primary inputs and outputs.

    Returns
    -------
    dict with keys:
        "equivalent"      : bool — True iff ALL outputs are equivalent
        "per_output"      : dict[str, bool] — per-output result
        "counterexample"  : dict[str, dict[str,int]] | None
            Mapping output-name → witness assignment, for the first
            mismatching output.  None when fully equivalent.
    """
    inputs_a = set(netlist_a.get("inputs", []))
    inputs_b = set(netlist_b.get("inputs", []))
    if inputs_a != inputs_b:
        raise ValueError(
            f"Primary-input mismatch: netlist_a has {sorted(inputs_a)}, "
            f"netlist_b has {sorted(inputs_b)}"
        )

    outputs_a = list(netlist_a.get("outputs", []))
    outputs_b = set(netlist_b.get("outputs", []))
    if set(outputs_a) != outputs_b:
        raise ValueError(
            f"Primary-output mismatch: netlist_a has {sorted(outputs_a)}, "
            f"netlist_b has {sorted(outputs_b)}"
        )

    # Use a single shared engine so variable names map to the same BDD nodes.
    engine = BDDEngine()

    bdds_a = build_output_bdds(netlist_a, engine)
    bdds_b = build_output_bdds(netlist_b, engine)

    per_output: dict[str, bool] = {}
    first_cex: dict[str, int] | None = None
    first_mismatch_output: str | None = None

    for out in outputs_a:
        node_a = bdds_a[out]
        node_b = bdds_b[out]
        is_eq = engine.equivalent(node_a, node_b)
        per_output[out] = is_eq
        if not is_eq and first_cex is None:
            cex = engine.counterexample(node_a, node_b)
            first_cex = cex
            first_mismatch_output = out
            log.debug(
                "Output '%s' differs; counterexample: %s", out, cex
            )

    all_equiv = all(per_output.values())

    counterexample: dict[str, Any] | None = None
    if first_cex is not None and first_mismatch_output is not None:
        counterexample = {
            "output": first_mismatch_output,
            "assignment": first_cex,
        }

    return {
        "equivalent": all_equiv,
        "per_output": per_output,
        "counterexample": counterexample,
    }
