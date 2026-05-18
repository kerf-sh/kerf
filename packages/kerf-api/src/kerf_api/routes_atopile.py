"""
POST /atopile/compile

Accepts an atopile (.ato) source body and compiles it to a Circuit JSON
manifest — the same schema consumed by tscircuit's CircuitEditor and
SchematicView/PCBView renderers.

The route is a thin HTTP wrapper around a pure-Python atopile parser.
It does NOT call external processes, download packages, or touch the DB.
It is auth-optional — compile results are ephemeral.

Request body (JSON):
    {
        "source": string,         // .ato source text (required)
        "module": string          // top-level module name to compile (optional)
    }

Response (JSON):
    {
        "ok": true,
        "circuit": [...],         // Circuit JSON element array
        "warnings": [...]
    }

Error response:
    {
        "ok": false,
        "errors": [
            {"message": "...", "line": N, "col": N}
        ]
    }
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CompileRequest(BaseModel):
    source: str
    module: str | None = None


class CompileError(BaseModel):
    message: str
    line: int | None = None
    col: int | None = None


class CompileResponse(BaseModel):
    ok: bool
    circuit: list[dict[str, Any]] | None = None
    warnings: list[str] | None = None
    errors: list[CompileError] | None = None


# ---------------------------------------------------------------------------
# Public route
# ---------------------------------------------------------------------------

@router.post("/atopile/compile", response_model=CompileResponse)
async def compile_atopile(req: CompileRequest) -> CompileResponse:
    """Compile atopile source to Circuit JSON."""
    if not req.source or not req.source.strip():
        raise HTTPException(status_code=400, detail="source is required")

    result = _compile_ato(req.source, top_module=req.module)
    return result


# ---------------------------------------------------------------------------
# Pure-Python atopile compiler (subset parser → Circuit JSON)
#
# Full atopile uses a ANTLR4 grammar + a semantic resolver.  Here we
# implement a subset sufficient for:
#   * `module` / `component` declarations
#   * `signal` / `pin` declarations
#   * `import X from "pkg/file.ato"`
#   * Value assignment: `resistance = 10kohm`, `capacitance = 100nF`
#   * Component instantiation: `r1 = new Resistor`
#   * Connection notation: `r1.A ~ r2.A`
#
# The output is a valid Circuit JSON array (flat list of elements).  We map
# atopile primitives to tscircuit element types so the existing front-end
# renders them without modification.
# ---------------------------------------------------------------------------

# SI suffix table — shared with the tokenizer's number+unit grammar.
_SI_SUFFIXES: dict[str, float] = {
    "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6,
    "m": 1e-3,  "k": 1e3,   "K": 1e3,  "M": 1e6,  "G": 1e9,
}

# Component-kind heuristics — match by module name substring
_COMP_FTYPE_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"resistor|Resistor|res|Res", re.I),  "simple_resistor"),
    (re.compile(r"capacitor|Capacitor|cap|Cap", re.I), "simple_capacitor"),
    (re.compile(r"inductor|Inductor|ind|Ind", re.I),   "simple_inductor"),
    (re.compile(r"diode|Diode", re.I),                 "simple_diode"),
    (re.compile(r"led|LED", re.I),                     "simple_led"),
    (re.compile(r"nmos|NMOS", re.I),                   "simple_transistor"),
    (re.compile(r"pmos|PMOS", re.I),                   "simple_transistor"),
    (re.compile(r"bjt|BJT|transistor|Transistor", re.I), "simple_transistor"),
    (re.compile(r"power|Power|vcc|VCC|vdd|VDD|gnd|GND", re.I), "simple_power"),
    (re.compile(r"button|Button|switch|Switch", re.I), "simple_push_button"),
]


def _guess_ftype(module_name: str) -> str:
    for pattern, ftype in _COMP_FTYPE_MAP:
        if pattern.search(module_name):
            return ftype
    return "simple_chip"


def _parse_value(val_str: str) -> float | None:
    """Parse a value like '10kohm', '100nF', '3.3V' into a float."""
    val_str = val_str.strip()
    # Match number + optional SI prefix + optional unit
    m = re.match(
        r"^([0-9]+(?:\.[0-9]+)?)([fFpPnNuUµmMkKGg]?)([a-zA-ZΩ]*)?$",
        val_str,
    )
    if not m:
        return None
    num = float(m.group(1))
    prefix = m.group(2)
    multiplier = _SI_SUFFIXES.get(prefix, 1.0)
    return num * multiplier


class _Scope:
    """Represents a parsed module/component scope."""

    def __init__(self, name: str, kind: str):
        self.name = name
        self.kind = kind            # 'module' | 'component'
        self.signals: list[str] = []
        self.pins: list[str] = []
        self.instances: list[dict] = []   # {name, of}
        self.connections: list[tuple[str, str]] = []
        self.values: dict[str, float] = {}
        self.imports: dict[str, str] = {}  # {name: from_path}

    def all_ports(self) -> list[str]:
        return self.signals + self.pins


def _compile_ato(
    source: str,
    top_module: str | None = None,
) -> CompileResponse:
    """Parse + emit Circuit JSON from atopile source."""

    errors: list[CompileError] = []
    warnings: list[str] = []
    scopes: dict[str, _Scope] = {}

    lines = source.splitlines()

    # ---- pass 1: tokenise into scopes ----
    current: _Scope | None = None

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Skip comments and blank lines
        if not line or line.startswith("#"):
            continue

        # Module / component declaration
        m = re.match(r"^(module|component)\s+([A-Za-z_][A-Za-z0-9_]*)(\s*:.*)?:", line)
        if m:
            kind = m.group(1)
            name = m.group(2)
            current = _Scope(name=name, kind=kind)
            scopes[name] = current
            continue

        if current is None:
            # Top-level statements outside a scope
            # import X from "path"  or  from "path" import X
            im = re.match(r"^import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s+[\"'](.+)[\"']", line)
            if not im:
                im = re.match(r"^from\s+[\"'](.+)[\"']\s+import\s+([A-Za-z_][A-Za-z0-9_]*)", line)
                if im:
                    im = type("M", (), {"group": lambda self, i: [None, im.group(2), im.group(1)][i]})()
            # We record but don't resolve external imports in this subset parser
            continue

        line_lower = line.lstrip()

        # import inside scope
        im = re.match(r"^import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s+[\"'](.+)[\"']", line_lower)
        if not im:
            im = re.match(r"^from\s+[\"'](.+)[\"']\s+import\s+([A-Za-z_][A-Za-z0-9_]*)", line_lower)
        if im:
            continue  # ignore import details — cross-file resolution not in scope

        # signal declaration:  signal <name>
        sm = re.match(r"^signal\s+([A-Za-z_][A-Za-z0-9_]*)", line_lower)
        if sm:
            current.signals.append(sm.group(1))
            continue

        # pin declaration:  pin <name>
        pm = re.match(r"^pin\s+([A-Za-z_][A-Za-z0-9_]*)", line_lower)
        if pm:
            current.pins.append(pm.group(1))
            continue

        # instantiation:  r1 = new Resistor
        nm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)", line_lower)
        if nm:
            current.instances.append({"name": nm.group(1), "of": nm.group(2)})
            continue

        # value assignment:  resistance = 10kohm
        vm = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9][0-9a-zA-ZΩµ._]*)",
            line_lower,
        )
        if vm:
            parsed = _parse_value(vm.group(2))
            if parsed is not None:
                current.values[vm.group(1)] = parsed
            continue

        # connection:  r1.A ~ r2.B  or  a.x ~ b.y
        conn = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*~\s*([A-Za-z_][A-Za-z0-9_.]*)", line_lower)
        if conn:
            current.connections.append((conn.group(1), conn.group(2)))
            continue

    if not scopes:
        errors.append(CompileError(message="no module or component declarations found", line=1))
        return CompileResponse(ok=False, errors=errors)

    # ---- pass 2: pick the top-level scope to emit ----
    if top_module and top_module in scopes:
        root = scopes[top_module]
    else:
        # Prefer the last declared scope (top-of-file is typically top-level)
        root = list(scopes.values())[-1]
        if top_module:
            warnings.append(
                f"module '{top_module}' not found; compiling '{root.name}' instead"
            )

    # ---- pass 3: emit Circuit JSON ----
    circuit: list[dict[str, Any]] = []
    id_seq = [0]

    def nid(prefix: str) -> str:
        id_seq[0] += 1
        return f"{prefix}_{id_seq[0]}"

    # One source_component per instance
    comp_id_map: dict[str, str] = {}
    port_id_map: dict[str, str] = {}  # "inst.signal" → port_id

    for inst in root.instances:
        inst_name = inst["name"]
        of_name = inst["of"]

        comp_id = nid("sc")
        comp_id_map[inst_name] = comp_id

        ftype = _guess_ftype(of_name)
        comp: dict[str, Any] = {
            "type": "source_component",
            "source_component_id": comp_id,
            "name": inst_name,
            "ftype": ftype,
        }

        # Propagate value properties when they exist in the child scope
        child_scope = scopes.get(of_name)
        if child_scope:
            for key, val in child_scope.values.items():
                comp[key] = val
            # Add ports from child scope signals + pins
            for sig in child_scope.all_ports():
                pid = nid("sp")
                port_id_map[f"{inst_name}.{sig}"] = pid
                circuit.append({
                    "type": "source_port",
                    "source_port_id": pid,
                    "source_component_id": comp_id,
                    "name": sig,
                    "pin_type": "passive",
                })
        else:
            # Unknown type — synthesise standard A/B pins for passives
            if ftype in (
                "simple_resistor", "simple_capacitor",
                "simple_inductor", "simple_diode", "simple_led",
            ):
                for pin_name in ("A", "B"):
                    pid = nid("sp")
                    port_id_map[f"{inst_name}.{pin_name}"] = pid
                    circuit.append({
                        "type": "source_port",
                        "source_port_id": pid,
                        "source_component_id": comp_id,
                        "name": pin_name,
                        "pin_type": "passive",
                    })
            elif ftype in ("simple_transistor",):
                for pin_name in ("base", "collector", "emitter"):
                    pid = nid("sp")
                    port_id_map[f"{inst_name}.{pin_name}"] = pid
                    circuit.append({
                        "type": "source_port",
                        "source_port_id": pid,
                        "source_component_id": comp_id,
                        "name": pin_name,
                        "pin_type": "passive",
                    })

        circuit.append(comp)

    # Emit connections as source_traces
    for a_ref, b_ref in root.connections:
        pid_a = port_id_map.get(a_ref)
        pid_b = port_id_map.get(b_ref)
        if pid_a and pid_b:
            circuit.append({
                "type": "source_trace",
                "source_trace_id": nid("st"),
                "connected_source_port_ids": [pid_a, pid_b],
            })
        else:
            if not pid_a:
                warnings.append(f"connection references unknown port '{a_ref}'")
            if not pid_b:
                warnings.append(f"connection references unknown port '{b_ref}'")

    # Emit top-level signals as net references
    for sig in root.all_ports():
        circuit.append({
            "type": "source_net",
            "source_net_id": nid("sn"),
            "name": sig,
            "member_source_port_ids": [],
        })

    return CompileResponse(
        ok=True,
        circuit=circuit,
        warnings=warnings if warnings else [],
    )
