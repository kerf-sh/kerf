"""erc.py — LLM tool: run Electrical Rules Check over a CircuitJSON schematic.

Mirrors the logic in src/lib/erc.js.  Returns the same shape:
  { "errors": [...], "warnings": [...] }

Each entry has keys: kind, severity, message, and optional
component_id, port_id, net_id.
"""
import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------

run_erc_spec = ToolSpec(
    name="run_erc",
    description=(
        "Run Electrical Rules Check (ERC) over a CircuitJSON schematic. "
        "Returns errors and warnings for: unconnected pins, duplicate reference "
        "designators, conflicting net labels, output-to-output conflicts, missing "
        "power sources, pin-direction mismatches, floating nets, and excessive "
        "bidirectional ports on a net."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Flat array of CircuitJSON source_* elements",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(run_erc_spec, write=False)
async def run_erc(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit = a.get("circuit_json")
    if not isinstance(circuit, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    result = _run_erc(circuit)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class _UF:
    def __init__(self):
        self._p: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._p:
            self._p[x] = x
        if self._p[x] != x:
            self._p[x] = self.find(self._p[x])
        return self._p[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._p[ra] = rb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ports(circuit):
    return [e for e in circuit if isinstance(e, dict) and e.get("type") == "source_port"]

def _traces(circuit):
    return [e for e in circuit if isinstance(e, dict) and e.get("type") == "source_trace"]

def _components(circuit):
    return [e for e in circuit if isinstance(e, dict) and e.get("type") == "source_component"]

def _nets(circuit):
    return [e for e in circuit if isinstance(e, dict) and e.get("type") == "source_net"]

def _touched_port_ids(trace_list):
    ids = set()
    for t in trace_list:
        for pid in (t.get("connected_source_port_ids") or t.get("port_ids") or []):
            ids.add(pid)
    return ids

def _build_net_uf(trace_list) -> _UF:
    uf = _UF()
    for t in trace_list:
        port_ids = t.get("connected_source_port_ids") or t.get("port_ids") or []
        net_ids  = t.get("connected_source_net_ids")  or t.get("net_ids")  or []
        all_ids  = port_ids + net_ids
        for i in range(1, len(all_ids)):
            uf.union(all_ids[0], all_ids[i])
    return uf


# ---------------------------------------------------------------------------
# Check 1: unconnected_pin
# ---------------------------------------------------------------------------

def _check_unconnected_pins(port_list, touched):
    errors = []
    for p in port_list:
        pid = p.get("source_port_id") or p.get("id")
        if pid and pid not in touched:
            errors.append({
                "kind": "unconnected_pin",
                "severity": "error",
                "message": f'Pin "{p.get("name", pid)}" on component "{p.get("source_component_id", "?")}" is unconnected',
                "component_id": p.get("source_component_id"),
                "port_id": pid,
            })
    return errors


# ---------------------------------------------------------------------------
# Check 2: duplicate_refdes
# ---------------------------------------------------------------------------

def _check_duplicate_refdes(component_list):
    errors = []
    seen: dict[str, str] = {}
    for c in component_list:
        ref = c.get("name") or c.get("refdes") or c.get("reference_designator")
        cid = c.get("source_component_id") or c.get("id")
        if not ref:
            continue
        if ref in seen:
            errors.append({
                "kind": "duplicate_refdes",
                "severity": "error",
                "message": f'Duplicate reference designator "{ref}" (components "{seen[ref]}" and "{cid}")',
                "component_id": cid,
            })
        else:
            seen[ref] = cid
    return errors


# ---------------------------------------------------------------------------
# Check 3: conflicting_net_label
# ---------------------------------------------------------------------------

def _check_conflicting_net_labels(net_list, trace_list):
    errors = []
    uf = _build_net_uf(trace_list)
    root_name: dict[str, str] = {}
    for n in net_list:
        nid   = n.get("source_net_id") or n.get("id")
        label = n.get("name") or n.get("net_name") or nid
        root  = uf.find(nid)
        if root in root_name:
            if root_name[root] != label:
                errors.append({
                    "kind": "conflicting_net_label",
                    "severity": "error",
                    "message": f'Net labels "{root_name[root]}" and "{label}" resolve to the same net but have conflicting names',
                    "net_id": nid,
                })
        else:
            root_name[root] = label
    return errors


# ---------------------------------------------------------------------------
# Check 4: output_to_output
# ---------------------------------------------------------------------------

def _check_output_to_output(port_list, trace_list):
    errors = []
    port_by_id = {(p.get("source_port_id") or p.get("id")): p for p in port_list}

    def is_output(p):
        if p is None:
            return False
        pt = p.get("pin_type", "")
        hints = p.get("port_hints") or []
        if pt != "output" and "output" not in hints:
            return False
        ef = p.get("electrical_function", "")
        if ef in ("open_collector", "open_drain"):
            return False
        return True

    for t in trace_list:
        ids = t.get("connected_source_port_ids") or t.get("port_ids") or []
        outputs = [port_by_id[i] for i in ids if i in port_by_id and is_output(port_by_id[i])]
        if len(outputs) >= 2:
            for i in range(1, len(outputs)):
                pid = outputs[i].get("source_port_id") or outputs[i].get("id")
                errors.append({
                    "kind": "output_to_output",
                    "severity": "error",
                    "message": f'Output pin "{outputs[0].get("name", outputs[0].get("source_port_id"))}" tied to output pin "{outputs[i].get("name", pid)}"',
                    "port_id": pid,
                })
    return errors


# ---------------------------------------------------------------------------
# Check 5: missing_power
# ---------------------------------------------------------------------------

import re as _re
_POWER_NAME_RE = _re.compile(r'^(vcc|vdd|vss|gnd|vbat|v\d+v?\d*|pwr)$', _re.IGNORECASE)


def _check_missing_power(port_list, net_list):
    errors = []
    sourced: set[str] = set()
    for p in port_list:
        pt    = p.get("pin_type", "")
        hints = p.get("port_hints") or []
        if pt in ("power", "power_out", "supply") or "power" in hints or "supply" in hints:
            if p.get("source_net_id"):
                sourced.add(p["source_net_id"])
            if p.get("net_name"):
                sourced.add(p["net_name"])

    for n in net_list:
        nid   = n.get("source_net_id") or n.get("id", "")
        label = n.get("name") or n.get("net_name") or ""
        is_power = n.get("is_power") is True or bool(_POWER_NAME_RE.match(label))
        if is_power and nid not in sourced and label not in sourced:
            errors.append({
                "kind": "missing_power",
                "severity": "error",
                "message": f'Power net "{label or nid}" is referenced but never sourced by a power/supply pin',
                "net_id": nid,
            })
    return errors


# ---------------------------------------------------------------------------
# Check 6: pin_direction_mismatch (warning)
# ---------------------------------------------------------------------------

def _check_pin_direction_mismatch(port_list, trace_list):
    warnings = []
    port_by_id = {(p.get("source_port_id") or p.get("id")): p for p in port_list}

    def is_input_only(p):
        if p is None:
            return False
        pt    = p.get("pin_type", "")
        hints = p.get("port_hints") or []
        if pt == "input":
            return True
        if "input" in hints and "output" not in hints and "bidirectional" not in hints:
            return True
        return False

    def is_driver(p):
        if p is None:
            return False
        pt    = p.get("pin_type", "")
        hints = p.get("port_hints") or []
        return pt in ("output", "power", "power_out", "passive") or \
               "output" in hints or "power" in hints

    for t in trace_list:
        ids = t.get("connected_source_port_ids") or t.get("port_ids") or []
        conn = [port_by_id[i] for i in ids if i in port_by_id]
        if any(is_driver(p) for p in conn):
            continue
        inputs = [p for p in conn if is_input_only(p)]
        if len(inputs) >= 2:
            pid = inputs[0].get("source_port_id") or inputs[0].get("id")
            warnings.append({
                "kind": "pin_direction_mismatch",
                "severity": "warning",
                "message": f'Input pin "{inputs[0].get("name", pid)}" drives input pin "{inputs[1].get("name", inputs[1].get("source_port_id"))}" with no driver on the net',
                "port_id": pid,
            })
    return warnings


# ---------------------------------------------------------------------------
# Check 7: floating_net (warning)
# ---------------------------------------------------------------------------

def _check_floating_net(port_list, trace_list):
    warnings = []
    uf = _build_net_uf(trace_list)
    port_by_id = {(p.get("source_port_id") or p.get("id")): p for p in port_list}

    root_ports: dict[str, set] = {}
    for t in trace_list:
        ids = t.get("connected_source_port_ids") or t.get("port_ids") or []
        if not ids:
            continue
        root = uf.find(ids[0])
        if root not in root_ports:
            root_ports[root] = set()
        for pid in ids:
            root_ports[root].add(pid)

    for root, port_set in root_ports.items():
        if len(port_set) == 1:
            only_id = next(iter(port_set))
            p = port_by_id.get(only_id)
            warnings.append({
                "kind": "floating_net",
                "severity": "warning",
                "message": f'Net (root "{root}") has only one connected port "{p.get("name", only_id) if p else only_id}" — possible floating wire',
                "port_id": only_id,
            })
    return warnings


# ---------------------------------------------------------------------------
# Check 8: bidirectional_promiscuity (warning)
# ---------------------------------------------------------------------------

_BIDIR_THRESHOLD = 3


def _check_bidirectional_promiscuity(port_list, trace_list):
    warnings = []
    uf = _build_net_uf(trace_list)
    touched = _touched_port_ids(trace_list)
    port_by_id = {(p.get("source_port_id") or p.get("id")): p for p in port_list}

    root_count: dict[str, int] = {}
    for pid, p in port_by_id.items():
        if pid not in touched:
            continue
        pt    = p.get("pin_type", "")
        hints = p.get("port_hints") or []
        is_bidir = pt == "bidirectional" or "bidirectional" in hints
        if not is_bidir:
            continue
        root = uf.find(pid)
        root_count[root] = root_count.get(root, 0) + 1

    for root, count in root_count.items():
        if count > _BIDIR_THRESHOLD:
            warnings.append({
                "kind": "bidirectional_promiscuity",
                "severity": "warning",
                "message": f'Net (root "{root}") has {count} bidirectional ports — consider using a bus',
                "net_id": root,
            })
    return warnings


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def _run_erc(circuit: list) -> dict:
    if not circuit:
        return {"errors": [], "warnings": []}

    port_list      = _ports(circuit)
    trace_list     = _traces(circuit)
    component_list = _components(circuit)
    net_list       = _nets(circuit)
    touched        = _touched_port_ids(trace_list)

    errors = (
        _check_unconnected_pins(port_list, touched) +
        _check_duplicate_refdes(component_list) +
        _check_conflicting_net_labels(net_list, trace_list) +
        _check_output_to_output(port_list, trace_list) +
        _check_missing_power(port_list, net_list)
    )

    warnings = (
        _check_pin_direction_mismatch(port_list, trace_list) +
        _check_floating_net(port_list, trace_list) +
        _check_bidirectional_promiscuity(port_list, trace_list)
    )

    return {"errors": errors, "warnings": warnings}
