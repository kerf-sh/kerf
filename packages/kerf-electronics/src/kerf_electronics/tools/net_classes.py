"""
LLM tools for KiCad-style net class management on CircuitJSON boards.

Tools: define_net_class, assign_net_to_class, remove_net_class,
       list_net_classes, get_effective_net_rules.

Net-class rules are advisory data — actual DRC enforcement is the DRC agent's
job. These tools only produce and read the data stored at:
  board.net_classes: [...]
  board.net_class_assignments: {net_id: class_name}

The "Default" class is always implicit and cannot be removed.
"""
import json
from copy import deepcopy
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ── Built-in class defaults (mirrors netClasses.js) ───────────────────────────

_BUILTIN_CLASSES = {
    "Default":     {"name": "Default",     "trace_width_mm": 0.25, "clearance_mm": 0.20, "via_diameter_mm": 0.60, "via_drill_mm": 0.30},
    "Power":       {"name": "Power",       "trace_width_mm": 0.50, "clearance_mm": 0.25, "via_diameter_mm": 0.80, "via_drill_mm": 0.40},
    "Signal":      {"name": "Signal",      "trace_width_mm": 0.25, "clearance_mm": 0.20, "via_diameter_mm": 0.60, "via_drill_mm": 0.30},
    "HighSpeed":   {"name": "HighSpeed",   "trace_width_mm": 0.20, "clearance_mm": 0.20, "via_diameter_mm": 0.50, "via_drill_mm": 0.25, "target_impedance_ohms": 50},
    "Differential":{"name": "Differential","trace_width_mm": 0.20, "clearance_mm": 0.20, "via_diameter_mm": 0.50, "via_drill_mm": 0.25, "target_impedance_ohms": 100},
}


def _get_board(circuit_json: dict) -> dict | None:
    """Return the board dict from a circuit_json or None."""
    if isinstance(circuit_json, list):
        for el in circuit_json:
            if isinstance(el, dict) and el.get("type") == "pcb_board":
                return el
        return None
    if isinstance(circuit_json, dict) and circuit_json.get("type") == "pcb_board":
        return circuit_json
    return None


def _ensure_board_keys(board: dict) -> None:
    if not isinstance(board.get("net_classes"), list):
        board["net_classes"] = []
    if not isinstance(board.get("net_class_assignments"), dict):
        board["net_class_assignments"] = {}


def _resolve_class(board: dict, name: str) -> dict | None:
    for c in board.get("net_classes", []):
        if c.get("name") == name:
            return c
    return _BUILTIN_CLASSES.get(name)


def _class_exists(board: dict, name: str) -> bool:
    return _resolve_class(board, name) is not None


# ── define_net_class ──────────────────────────────────────────────────────────

define_net_class_spec = ToolSpec(
    name="define_net_class",
    description=(
        "Add or update a net class in a CircuitJSON board. "
        "Net classes define advisory trace/via dimensions (and optional target "
        "impedance) that apply to all nets assigned to that class. "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object", "description": "The CircuitJSON board object to modify."},
            "name": {"type": "string", "description": "Net class name (e.g. 'Power', 'HighSpeed')."},
            "trace_width_mm": {"type": "number", "description": "Recommended trace width in mm."},
            "clearance_mm": {"type": "number", "description": "Minimum copper clearance in mm."},
            "via_diameter_mm": {"type": "number", "description": "Via annular ring outer diameter in mm."},
            "via_drill_mm": {"type": "number", "description": "Via drill hole diameter in mm."},
            "target_impedance_ohms": {"type": "number", "description": "Target impedance in ohms (optional, for controlled-impedance traces)."},
        },
        "required": ["circuit_json", "name", "trace_width_mm", "clearance_mm", "via_diameter_mm", "via_drill_mm"],
    },
)


@register(define_net_class_spec, write=True)
async def define_net_class(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    name = a.get("name", "").strip()
    if not name:
        return err_payload("name is required", "BAD_ARGS")

    for key in ("trace_width_mm", "clearance_mm", "via_diameter_mm", "via_drill_mm"):
        if not isinstance(a.get(key), (int, float)):
            return err_payload(f"{key} must be a number", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        return err_payload("No pcb_board element found in circuit_json", "BAD_ARGS")

    _ensure_board_keys(board)
    entry = {
        "name": name,
        "trace_width_mm": a["trace_width_mm"],
        "clearance_mm": a["clearance_mm"],
        "via_diameter_mm": a["via_diameter_mm"],
        "via_drill_mm": a["via_drill_mm"],
    }
    if isinstance(a.get("target_impedance_ohms"), (int, float)):
        entry["target_impedance_ohms"] = a["target_impedance_ohms"]

    idx = next((i for i, c in enumerate(board["net_classes"]) if c.get("name") == name), -1)
    if idx >= 0:
        board["net_classes"][idx] = entry
    else:
        board["net_classes"].append(entry)

    return ok_payload({"circuit_json": cloned, "defined": name})


# ── assign_net_to_class ───────────────────────────────────────────────────────

assign_net_to_class_spec = ToolSpec(
    name="assign_net_to_class",
    description=(
        "Assign a net to a net class. The class must exist (either as a builtin — "
        "Default, Power, Signal, HighSpeed, Differential — or previously defined via "
        "define_net_class). Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "net_id": {"type": "string", "description": "Net identifier to assign."},
            "class_name": {"type": "string", "description": "Target net class name."},
        },
        "required": ["circuit_json", "net_id", "class_name"],
    },
)


@register(assign_net_to_class_spec, write=True)
async def assign_net_to_class(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    net_id = (a.get("net_id") or "").strip()
    class_name = (a.get("class_name") or "").strip()

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not net_id:
        return err_payload("net_id is required", "BAD_ARGS")
    if not class_name:
        return err_payload("class_name is required", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        return err_payload("No pcb_board element found in circuit_json", "BAD_ARGS")

    _ensure_board_keys(board)
    if not _class_exists(board, class_name):
        return err_payload(f'Net class "{class_name}" does not exist', "BAD_ARGS")

    board["net_class_assignments"][net_id] = class_name
    return ok_payload({"circuit_json": cloned, "net_id": net_id, "class_name": class_name})


# ── remove_net_class ──────────────────────────────────────────────────────────

remove_net_class_spec = ToolSpec(
    name="remove_net_class",
    description=(
        "Remove a user-defined net class. Any nets assigned to it are automatically "
        "reassigned to 'Default'. The 'Default' class cannot be removed. "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "class_name": {"type": "string", "description": "Net class to remove."},
        },
        "required": ["circuit_json", "class_name"],
    },
)


@register(remove_net_class_spec, write=True)
async def remove_net_class(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    class_name = (a.get("class_name") or "").strip()

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not class_name:
        return err_payload("class_name is required", "BAD_ARGS")
    if class_name == "Default":
        return err_payload("Cannot remove the Default net class", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        return err_payload("No pcb_board element found in circuit_json", "BAD_ARGS")

    _ensure_board_keys(board)
    board["net_classes"] = [c for c in board["net_classes"] if c.get("name") != class_name]

    reassigned = []
    for net_id, assigned in board["net_class_assignments"].items():
        if assigned == class_name:
            board["net_class_assignments"][net_id] = "Default"
            reassigned.append(net_id)

    return ok_payload({"circuit_json": cloned, "removed": class_name, "reassigned_to_default": reassigned})


# ── list_net_classes ──────────────────────────────────────────────────────────

list_net_classes_spec = ToolSpec(
    name="list_net_classes",
    description=(
        "List all net classes available on the board: builtin classes plus any "
        "user-defined overrides, along with current net assignments."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
        },
        "required": ["circuit_json"],
    },
)


@register(list_net_classes_spec, write=False)
async def list_net_classes(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")

    board = _get_board(circuit_json)
    user_defined = (board.get("net_classes") or []) if board else []
    assignments = (board.get("net_class_assignments") or {}) if board else {}

    # Merge: builtin base, user-defined on top
    user_by_name = {c["name"]: c for c in user_defined if "name" in c}
    all_classes = []
    for name, cls in _BUILTIN_CLASSES.items():
        all_classes.append(user_by_name.get(name, cls))
    for name, cls in user_by_name.items():
        if name not in _BUILTIN_CLASSES:
            all_classes.append(cls)

    return ok_payload({
        "classes": all_classes,
        "assignments": assignments,
    })


# ── get_effective_net_rules ───────────────────────────────────────────────────

get_effective_net_rules_spec = ToolSpec(
    name="get_effective_net_rules",
    description=(
        "Return the effective design rules for a net: class defaults merged with "
        "any per-net overrides stored at board.net_rules[net_id]. "
        "Use this before routing or DRC to know what widths/clearances apply."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "net_id": {"type": "string", "description": "Net identifier to query."},
        },
        "required": ["circuit_json", "net_id"],
    },
)


@register(get_effective_net_rules_spec, write=False)
async def get_effective_net_rules(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    net_id = (a.get("net_id") or "").strip()

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not net_id:
        return err_payload("net_id is required", "BAD_ARGS")

    board = _get_board(circuit_json)
    assignments = (board.get("net_class_assignments") or {}) if board else {}
    class_name = assignments.get(net_id, "Default")

    # Resolve class
    user_classes = (board.get("net_classes") or []) if board else []
    cls = next((c for c in user_classes if c.get("name") == class_name), None)
    if cls is None:
        cls = _BUILTIN_CLASSES.get(class_name, _BUILTIN_CLASSES["Default"])

    rules = {k: v for k, v in cls.items() if k != "name"}

    # Per-net overrides
    net_rules = (board.get("net_rules") or {}) if board else {}
    rules.update(net_rules.get(net_id, {}))
    rules["net_class"] = class_name

    return ok_payload(rules)
