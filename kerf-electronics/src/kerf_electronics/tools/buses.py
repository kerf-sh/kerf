"""
LLM tools for KiCad-style buses and differential pairs on CircuitJSON boards.

Tools: add_bus, expand_bus, add_differential_pair, list_differential_pairs.

CircuitJSON extensions (on the board element):
  board.bus_definitions: [{ name, member_nets: [...] }]
  board.differential_pairs: [{
    name, net_p_id, net_n_id,
    target_impedance_ohms?, skew_max_mm?
  }]

Buses can use KiCad-style slice notation in member_nets, e.g. "DATA[7..0]",
which is decoded into individual net names by expand_bus().
"""
import json
import re
from copy import deepcopy
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_board(circuit_json: dict) -> dict | None:
    if isinstance(circuit_json, list):
        for el in circuit_json:
            if isinstance(el, dict) and el.get("type") == "pcb_board":
                return el
        return None
    if isinstance(circuit_json, dict) and circuit_json.get("type") == "pcb_board":
        return circuit_json
    return None


def _ensure_board_keys(board: dict) -> None:
    if not isinstance(board.get("bus_definitions"), list):
        board["bus_definitions"] = []
    if not isinstance(board.get("differential_pairs"), list):
        board["differential_pairs"] = []


def _expand_bus(spec: str) -> list[str]:
    """Parse KiCad-style bus slice like DATA[7..0] into individual net names."""
    if not isinstance(spec, str):
        return []
    has_brackets = '[' in spec
    m = re.match(r'^(.+)\[(\d+)\.\.(\d+)\]$', spec)
    if not m:
        return [] if has_brackets else [spec]
    prefix, a_raw, b_raw = m.group(1), m.group(2), m.group(3)
    a, b = int(a_raw), int(b_raw)
    if a == b:
        return [f"{prefix}{a}"]
    step = 1 if a < b else -1
    return [f"{prefix}{i}" for i in range(a, b + step, step)]


# ── expand_bus ─────────────────────────────────────────────────────────────────

expand_bus_spec = ToolSpec(
    name="expand_bus",
    description=(
        "Expand a KiCad-style bus slice specification into an array of individual "
        "net names.  Examples: 'DATA[7..0]' → ['DATA7','DATA6',…,'DATA0']; "
        "'RX[0..3]' → ['RX0','RX1','RX2','RX3']; 'CLK' → ['CLK']. "
        "Use this to resolve bus member names before routing or net assignment."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": "Bus specification, e.g. 'DATA[7..0]' or a plain net name.",
            },
        },
        "required": ["spec"],
    },
)


@register(expand_bus_spec, write=False)
async def expand_bus(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    spec = a.get("spec", "")
    if not isinstance(spec, str):
        return err_payload("spec must be a string", "BAD_ARGS")

    nets = _expand_bus(spec)
    return ok_payload({"spec": spec, "nets": nets})


# ── add_bus ────────────────────────────────────────────────────────────────────

add_bus_spec = ToolSpec(
    name="add_bus",
    description=(
        "Add or update a named bus definition on the board.  "
        "member_nets entries can be plain strings ('DATA0') or KiCad-style "
        "slice notation ('DATA[7..0]').  Calling again with the same name "
        "overwrites the existing definition.  "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object", "description": "The CircuitJSON board object to modify."},
            "name": {"type": "string", "description": "Bus name, e.g. 'DATA_BUS'."},
            "member_nets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of net names or bus slices, e.g. ['DATA[7..0]', 'CLK'].",
            },
        },
        "required": ["circuit_json", "name", "member_nets"],
    },
)


def _validate_bus(data: dict) -> tuple[bool, list[str]]:
    errors = []
    if not data.get("name") or not isinstance(data["name"], str):
        errors.append("name is required and must be a string")
    if not isinstance(data.get("member_nets"), list) or len(data["member_nets"]) == 0:
        errors.append("member_nets must be a non-empty array")
    elif not all(isinstance(n, str) and n.strip() for n in data["member_nets"]):
        errors.append("all member_nets entries must be non-empty strings")
    else:
        for net in data["member_nets"]:
            if '[' in net and not re.match(r'^\w+\[\d+\.\.\d+\]$', net):
                errors.append(f"Bus member '{net}' uses invalid slice syntax (expected NAME[7..0])")
                break
            expanded = _expand_bus(net)
            if not expanded:
                errors.append(f"Bus member '{net}' failed to expand")
                break
    return len(errors) == 0, errors


@register(add_bus_spec, write=True)
async def add_bus(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")

    name = (a.get("name") or "").strip()
    member_nets = a.get("member_nets", [])

    data = {"name": name, "member_nets": member_nets}
    ok, errors = _validate_bus(data)
    if not ok:
        return err_payload(f"Invalid bus definition: {'; '.join(errors)}", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        return err_payload("No pcb_board element found in circuit_json", "BAD_ARGS")

    _ensure_board_keys(board)

    entry = {"name": name, "member_nets": list(member_nets)}
    idx = next((i for i, b in enumerate(board["bus_definitions"]) if b.get("name") == name), -1)
    if idx >= 0:
        board["bus_definitions"][idx] = entry
    else:
        board["bus_definitions"].append(entry)

    return ok_payload({"circuit_json": cloned, "name": name})


# ── add_differential_pair ──────────────────────────────────────────────────────

add_differential_pair_spec = ToolSpec(
    name="add_differential_pair",
    description=(
        "Add or update a named differential pair definition.  "
        "net_p and net_n are the positive and negative signal net identifiers.  "
        "Optional target_impedance_ohms (Ω) and skew_max_mm guide the router/DRC.  "
        "Overwrites any existing pair with the same name.  "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "name": {"type": "string", "description": "Pair name, e.g. 'USB_DP'."},
            "net_p": {"type": "string", "description": "Positive signal net identifier."},
            "net_n": {"type": "string", "description": "Negative signal net identifier."},
            "target_impedance_ohms": {
                "type": "number",
                "description": "Target differential impedance in ohms (optional).",
            },
            "skew_max_mm": {
                "type": "number",
                "description": "Maximum allowed propagation-skew between P and N traces in mm (optional).",
            },
        },
        "required": ["circuit_json", "name", "net_p", "net_n"],
    },
)


@register(add_differential_pair_spec, write=True)
async def add_differential_pair(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")

    name = (a.get("name") or "").strip()
    net_p = (a.get("net_p") or "").strip()
    net_n = (a.get("net_n") or "").strip()

    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not net_p:
        return err_payload("net_p is required", "BAD_ARGS")
    if not net_n:
        return err_payload("net_n is required", "BAD_ARGS")
    if net_p == net_n:
        return err_payload("net_p and net_n must be different nets", "BAD_ARGS")

    target_impedance_ohms = a.get("target_impedance_ohms")
    if target_impedance_ohms is not None and not isinstance(target_impedance_ohms, (int, float)):
        return err_payload("target_impedance_ohms must be a number if provided", "BAD_ARGS")

    skew_max_mm = a.get("skew_max_mm")
    if skew_max_mm is not None and not isinstance(skew_max_mm, (int, float)):
        return err_payload("skew_max_mm must be a number if provided", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        return err_payload("No pcb_board element found in circuit_json", "BAD_ARGS")

    _ensure_board_keys(board)

    entry = {"name": name, "net_p_id": net_p, "net_n_id": net_n}
    if isinstance(target_impedance_ohms, (int, float)):
        entry["target_impedance_ohms"] = target_impedance_ohms
    if isinstance(skew_max_mm, (int, float)):
        entry["skew_max_mm"] = skew_max_mm

    idx = next((i for i, d in enumerate(board["differential_pairs"]) if d.get("name") == name), -1)
    if idx >= 0:
        board["differential_pairs"][idx] = entry
    else:
        board["differential_pairs"].append(entry)

    return ok_payload({"circuit_json": cloned, "name": name})


# ── list_differential_pairs ────────────────────────────────────────────────────

list_differential_pairs_spec = ToolSpec(
    name="list_differential_pairs",
    description=(
        "Return all differential pair definitions on the board.  "
        "Each entry contains name, net_p_id, net_n_id, and optional "
        "target_impedance_ohms / skew_max_mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
        },
        "required": ["circuit_json"],
    },
)


@register(list_differential_pairs_spec, write=False)
async def list_differential_pairs(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")

    board = _get_board(circuit_json)
    pairs = (board.get("differential_pairs") or []) if board else []
    return ok_payload({"pairs": [dict(p) for p in pairs]})
