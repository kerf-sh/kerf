"""to_tscircuit.py — atopile AST → tscircuit JSX one-way converter.

Entry point::

    from kerf_electronics.atopile.to_tscircuit import ato_to_tsx
    tsx_source = ato_to_tsx(source_text)

Returns a ``.tsx`` source string containing a default-exported React component
that renders the circuit using tscircuit JSX components::

    import React from "react";
    import { board, resistor, capacitor, net } from "@tscircuit/core";

    export default function VoltageDivider() {
      return (
        <board>
          <resistor name="R1" resistance="10kohm" />
          <resistor name="R2" resistance="1kohm" />
          <net name="vin" />
          <net name="vout" />
          <net name="gnd" />
        </board>
      );
    }

Converter rules
---------------
- ``signal X``          → ``<net name="X" />``
- ``r1 = new Resistor`` → ``<resistor name="R1" .../>``
- value assignments     → mapped to the component's primary value prop
  (resistance / capacitance / inductance / forward_voltage_drop)
- string assignments    → passed through as props (e.g. color="red")
- connections           → not emitted as explicit JSX; net name is inferred
  from the union-find of signals and passed as ``connections`` comment

One-way only — no reverse path (JSX → .ato) is provided.
"""
from __future__ import annotations

import re
import textwrap
from typing import Dict, List, Optional, Tuple

from .parser import parse
from .ast import (
    Assignment,
    ComponentBlock,
    ComponentInstance,
    Connection,
    Module,
    ModuleBlock,
    QuantityLiteral,
    SignalDecl,
    StringLiteral,
)


# ---------------------------------------------------------------------------
# Component type → tscircuit JSX tag + primary value prop name
# ---------------------------------------------------------------------------

#: Maps atopile type name → (jsx_tag, value_prop)
_TAG_MAP: Dict[str, Tuple[str, str]] = {
    "Resistor":   ("resistor",   "resistance"),
    "Capacitor":  ("capacitor",  "capacitance"),
    "LED":        ("led",        "forward_voltage_drop"),
    "Inductor":   ("inductor",   "inductance"),
    "Transistor": ("transistor", ""),
    "NMOS":       ("nmos",       ""),
    "PMOS":       ("pmos",       ""),
    "Diode":      ("diode",      ""),
    "Crystal":    ("crystal",    "frequency"),
    "OpAmp":      ("opamp",      ""),
}

_DEFAULT_TAG = "component"


def _canonical_ref(instance_name: str) -> str:
    """Convert atopile instance name to PCB reference designator.

    Examples: r1 → R1, c1 → C1, led1 → LED1, r_top → R_TOP
    """
    if instance_name[0].isupper():
        return instance_name
    return instance_name.upper()


def _fmt_value(val) -> str:
    """Format a QuantityLiteral or StringLiteral as a string."""
    if isinstance(val, QuantityLiteral):
        return val.raw
    if isinstance(val, StringLiteral):
        return val.value
    return str(val)


def _slugify_jsx_name(s: str) -> str:
    """Return a valid JSX function-component name (PascalCase)."""
    # Remove non-alphanumeric, split on boundaries, capitalise
    words = re.split(r"[^a-zA-Z0-9]+", s)
    return "".join(w.capitalize() for w in words if w)


# ---------------------------------------------------------------------------
# Union-Find for net resolution (mirrors compile.py logic)
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self) -> None:
        self._parent: Dict[str, str] = {}
        self._signals: List[str] = []
        self._counter = 0

    def add_signal(self, name: str) -> None:
        if name not in self._signals:
            self._signals.append(name)
        self._find(name)

    def _find(self, key: str) -> str:
        if key not in self._parent:
            self._parent[key] = key
        if self._parent[key] != key:
            self._parent[key] = self._find(self._parent[key])
        return self._parent[key]

    def _merge(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return
        a_sig = ra in self._signals
        b_sig = rb in self._signals
        if b_sig and not a_sig:
            self._parent[ra] = rb
        else:
            self._parent[rb] = ra

    def connect(self, left_parts: List[str], right_parts: List[str]) -> None:
        lk = ".".join(left_parts)
        rk = ".".join(right_parts)
        self._find(lk)
        self._find(rk)

        l_sig = len(left_parts) == 1 and left_parts[0] in self._signals
        r_sig = len(right_parts) == 1 and right_parts[0] in self._signals

        if not l_sig and not r_sig:
            cl = self._find(lk)
            cr = self._find(rk)
            if cl not in self._signals and cr not in self._signals:
                auto = f"net_{self._counter}"
                self._counter += 1
                self._signals.append(auto)
                self._find(auto)
                self._merge(lk, auto)
                self._merge(rk, auto)
                return
        self._merge(lk, rk)

    def net_of(self, endpoint: str) -> str:
        """Return the canonical net name for this endpoint."""
        return self._find(endpoint)


# ---------------------------------------------------------------------------
# Per-module converter
# ---------------------------------------------------------------------------

class _ModuleConverter:
    def __init__(self, block: ModuleBlock) -> None:
        self._block = block
        self._signals: List[str] = []
        # instance_name → {"type_name", "value", "extra_attrs"}
        self._instances: Dict[str, Dict] = {}
        self._attrs: Dict[str, object] = {}
        self._uf = _UnionFind()

    def _collect(self) -> None:
        for stmt in self._block.body:
            if isinstance(stmt, SignalDecl):
                self._signals.append(stmt.name)
                self._uf.add_signal(stmt.name)

            elif isinstance(stmt, ComponentInstance):
                self._instances[stmt.instance_name] = {
                    "type_name": stmt.type_name,
                    "value": "",
                    "extra_attrs": {},
                }

            elif isinstance(stmt, Assignment):
                self._attrs[stmt.target.name] = stmt.value

            elif isinstance(stmt, Connection):
                self._uf.connect(stmt.left.parts, stmt.right.parts)

    def _resolve_attrs(self) -> None:
        for k, v in self._attrs.items():
            parts = k.split(".", 1)
            if len(parts) != 2:
                continue
            iname, attr = parts
            if iname not in self._instances:
                continue
            if attr == "value":
                self._instances[iname]["value"] = _fmt_value(v)
            else:
                self._instances[iname]["extra_attrs"][attr] = _fmt_value(v)

    def _component_lines(self) -> List[str]:
        lines: List[str] = []
        for iname, inst in self._instances.items():
            type_name = inst["type_name"]
            tag, val_prop = _TAG_MAP.get(type_name, (_DEFAULT_TAG, ""))
            ref = _canonical_ref(iname)
            props = [f'name="{ref}"']

            # Value prop
            value_str = inst["value"]
            if value_str:
                prop_name = val_prop if val_prop else "value"
                props.append(f'{prop_name}="{value_str}"')

            # Extra string attributes (e.g. color="red")
            for attr, av in inst["extra_attrs"].items():
                props.append(f'{attr}="{av}"')

            props_str = " ".join(props)
            lines.append(f"      <{tag} {props_str} />")
        return lines

    def _net_lines(self) -> List[str]:
        return [f'      <net name="{s}" />' for s in self._signals]

    def to_tsx(self) -> str:
        self._collect()
        self._resolve_attrs()

        fn_name = _slugify_jsx_name(self._block.name) or "Circuit"
        component_lines = self._component_lines()
        net_lines = self._net_lines()

        inner_lines = net_lines + component_lines
        if inner_lines:
            children = "\n".join(inner_lines)
            board_content = f"        <board>\n{children}\n        </board>"
        else:
            board_content = "        <board />"

        return textwrap.dedent(f"""\
            import React from "react";
            import {{ board, net, resistor, capacitor, led, inductor, transistor, nmos, pmos, diode, crystal, opamp, component }} from "@tscircuit/core";

            export default function {fn_name}() {{
              return (
            {board_content}
              );
            }}
            """)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ato_to_tsx(source: str, *, top_module: Optional[str] = None) -> str:
    """Convert a ``.ato`` source string to a tscircuit JSX ``.tsx`` string.

    Parameters
    ----------
    source:
        The text of a ``.ato`` file.
    top_module:
        Name of the module block to convert.  If *None*, the first
        ``module`` block is used.

    Returns
    -------
    A ``.tsx`` source string ready for use with ``@tscircuit/core``.

    Raises
    ------
    ValueError
        If no module block is found in the source.
    """
    ast_root: Module = parse(source)

    module_blocks = [b for b in ast_root.blocks if isinstance(b, ModuleBlock)]
    if not module_blocks:
        raise ValueError("No module block found in .ato source")

    if top_module is not None:
        block = next((b for b in module_blocks if b.name == top_module), None)
        if block is None:
            raise ValueError(
                f"Module {top_module!r} not found. "
                f"Available: {[b.name for b in module_blocks]}"
            )
    else:
        block = module_blocks[0]

    return _ModuleConverter(block).to_tsx()
