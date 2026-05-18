"""
kerf_plc.simulator.scan
------------------------
IEC 61131-3 scan-cycle simulator for Ladder Diagram (LD) rungs and a
lightweight compiled form of Structured Text (ST) assignments.

Program representation
~~~~~~~~~~~~~~~~~~~~~~
A *program* is a plain dict (or parsed from JSON) with the shape::

    {
      "variables": {
        "<name>": <initial_value>   // bool | int | float
      },
      "pous": [
        // Each POU is executed in order every scan cycle.
        {
          "kind": "LD",
          "rungs": [
            {
              // A rung is a list of *elements* in series.
              // The rung result (coil power rail) is the AND of all elements.
              // An optional "coil" key names the output variable to set.
              "elements": [
                {"type": "contact", "var": "<name>", "negate": false},
                {
                  "type": "fb_call",
                  "fb_type": "TON",
                  "instance": "<unique_instance_name>",
                  "params": {
                    // pin → variable name in state, OR a literal value
                    "IN":  "<var_name>",
                    "PT":  500,
                    "Q":   "<var_name>",
                    "ET":  "<var_name>"
                  }
                }
              ],
              "coil": "<var_name>",        // optional output coil
              "coil_negate": false          // optional: NC coil
            }
          ]
        },
        {
          "kind": "ST",
          "statements": [
            // Compiled assignment expressions evaluated left-to-right.
            // Each is a dict with "lhs" (var name) and "rhs" (expression).
            // RHS may be:
            //   {"type": "var",    "name": "<v>"}
            //   {"type": "literal","value": <v>}
            //   {"type": "not",    "operand": <rhs_expr>}
            //   {"type": "and",    "left": <rhs>, "right": <rhs>}
            //   {"type": "or",     "left": <rhs>, "right": <rhs>}
            {"lhs": "<var>", "rhs": {"type": "var", "name": "<other_var>"}}
          ]
        }
      ]
    }

FB instantiation
~~~~~~~~~~~~~~~~
FB instances are created lazily on first use and keyed by their ``instance``
name.  The same instance accumulates state across scans (timer accumulators,
counter values, etc.).

Usage
~~~~~
::

    import json, pathlib
    from kerf_plc.simulator.scan import Simulator

    program = json.loads(pathlib.Path("program.json").read_text())
    sim = Simulator(program, tick_ms=1)

    outputs = sim.step({"start_btn": True})
    trace   = sim.run_for(5000, lambda t: {"start_btn": True})
"""
from __future__ import annotations

from typing import Any, Callable

from .function_blocks import (
    CTD,
    CTU,
    F_TRIG,
    R_TRIG,
    RS,
    SR,
    TOF,
    TON,
    FunctionBlock,
    FB_REGISTRY,
)
from .state import ScanState


# ---------------------------------------------------------------------------
# FB instance factory
# ---------------------------------------------------------------------------

def _make_fb(fb_type: str, instance_name: str, params: dict[str, Any]) -> FunctionBlock:
    """Instantiate an FB from its type name and wiring params."""
    cls = FB_REGISTRY.get(fb_type)
    if cls is None:
        raise ValueError(f"Unknown FB type: {fb_type!r}")

    p = params  # shorthand

    if fb_type == "TON":
        return TON(
            in_var=p["IN"],
            pt_var=p["PT"],
            q_var=p["Q"],
            et_var=p["ET"],
        )
    if fb_type == "TOF":
        return TOF(
            in_var=p["IN"],
            pt_var=p["PT"],
            q_var=p["Q"],
            et_var=p["ET"],
        )
    if fb_type == "CTU":
        return CTU(
            cu_var=p["CU"],
            r_var=p["R"],
            pv_var=p["PV"],
            q_var=p["Q"],
            cv_var=p["CV"],
        )
    if fb_type == "CTD":
        return CTD(
            cd_var=p["CD"],
            ld_var=p["LD"],
            pv_var=p["PV"],
            q_var=p["Q"],
            cv_var=p["CV"],
        )
    if fb_type == "R_TRIG":
        return R_TRIG(clk_var=p["CLK"], q_var=p["Q"])
    if fb_type == "F_TRIG":
        return F_TRIG(clk_var=p["CLK"], q_var=p["Q"])
    if fb_type == "SR":
        return SR(s1_var=p["S1"], r_var=p["R"], q_var=p["Q"])
    if fb_type == "RS":
        return RS(s_var=p["S"], r1_var=p["R1"], q_var=p["Q"])

    # Fallback: should not reach here given registry check above
    raise ValueError(f"No factory for FB type: {fb_type!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Expression evaluator for ST compiled assignments
# ---------------------------------------------------------------------------

def _eval_expr(expr: dict[str, Any], state: ScanState) -> Any:
    t = expr["type"]
    if t == "literal":
        return expr["value"]
    if t == "var":
        return state.get(expr["name"])
    if t == "not":
        return not _eval_expr(expr["operand"], state)
    if t == "and":
        return bool(_eval_expr(expr["left"], state)) and bool(_eval_expr(expr["right"], state))
    if t == "or":
        return bool(_eval_expr(expr["left"], state)) or bool(_eval_expr(expr["right"], state))
    raise ValueError(f"Unknown expression type: {t!r}")


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class Simulator:
    """IEC 61131-3 scan-cycle simulator.

    Parameters
    ----------
    program:
        Dict representation of the program (see module docstring for schema).
    tick_ms:
        Simulated time per scan cycle in milliseconds (default 1 ms).
    """

    def __init__(self, program: dict[str, Any], tick_ms: float = 1.0) -> None:
        self.tick_ms = float(tick_ms)
        self._pous: list[dict[str, Any]] = program.get("pous", [])

        # Initialise variable store
        initial_vars: dict[str, Any] = dict(program.get("variables", {}))
        self._state = ScanState(initial_vars)

        # FB instance cache: instance_name → FunctionBlock
        self._fb_instances: dict[str, FunctionBlock] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, inputs: dict[str, bool | int | float] | None = None) -> dict[str, Any]:
        """Execute one scan cycle.

        1. Write *inputs* into the variable store (overrides program variables).
        2. Execute every POU in declaration order.
        3. Advance elapsed time by tick_ms.
        4. Return a snapshot of all variables.
        """
        if inputs:
            self._state.update(inputs)

        for pou in self._pous:
            kind = pou.get("kind", "").upper()
            if kind == "LD":
                self._exec_ld(pou)
            elif kind == "ST":
                self._exec_st(pou)
            # Unknown POU kinds are silently skipped

        self._state.elapsed_ms += self.tick_ms
        return self._state.snapshot()

    def run_for(
        self,
        duration_ms: float,
        input_provider: Callable[[float], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run the simulator for *duration_ms* of simulated time.

        Parameters
        ----------
        duration_ms:
            Total simulated duration in milliseconds.
        input_provider:
            Optional callable ``f(elapsed_ms) -> dict``.  Called before each
            step to supply external inputs for that tick.

        Returns
        -------
        list[dict]
            State snapshot after every step (length = ceil(duration_ms / tick_ms)).
        """
        trace: list[dict[str, Any]] = []
        steps = int(duration_ms / self.tick_ms)
        for _ in range(steps):
            inputs = input_provider(self._state.elapsed_ms) if input_provider else {}
            snapshot = self.step(inputs)
            trace.append(snapshot)
        return trace

    # ------------------------------------------------------------------
    # Internal: LD execution
    # ------------------------------------------------------------------

    def _exec_ld(self, pou: dict[str, Any]) -> None:
        for rung in pou.get("rungs", []):
            self._exec_rung(rung)

    def _exec_rung(self, rung: dict[str, Any]) -> None:
        """Evaluate a rung: AND all elements, optionally drive a coil."""
        power: bool = True
        for element in rung.get("elements", []):
            power = power and self._eval_element(element, power)

        coil = rung.get("coil")
        if coil:
            negate = bool(rung.get("coil_negate", False))
            self._state.set(coil, (not power) if negate else power)

    def _eval_element(self, element: dict[str, Any], power_in: bool) -> bool:
        """Evaluate a single rung element; return the output power rail value."""
        etype = element.get("type")

        if etype == "contact":
            val = bool(self._state.get(element["var"], False))
            if element.get("negate", False):
                val = not val
            return power_in and val

        if etype == "fb_call":
            # Execute the FB (which updates its output variables in state).
            instance_name: str = element["instance"]
            if instance_name not in self._fb_instances:
                self._fb_instances[instance_name] = _make_fb(
                    element["fb_type"], instance_name, element["params"]
                )
            self._fb_instances[instance_name].execute(self._state, self.tick_ms)
            # The power rail passes through unchanged (FB calls are side-effectful).
            return power_in

        # Unknown element type: pass through
        return power_in

    # ------------------------------------------------------------------
    # Internal: ST execution
    # ------------------------------------------------------------------

    def _exec_st(self, pou: dict[str, Any]) -> None:
        for stmt in pou.get("statements", []):
            lhs: str = stmt["lhs"]
            value = _eval_expr(stmt["rhs"], self._state)
            self._state.set(lhs, value)
