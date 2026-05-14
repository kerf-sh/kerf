"""
LLM tools for KiCad-style hierarchical schematics on CircuitJSON boards.

CircuitJSON extensions (on the board element):
  board.sub_sheets: [{
    id, name, file_id, position: [x, y],
    pins: [{ name, type, net_id }]
  }]
  board.global_labels: [{ name, net_id }]
  board.hierarchical_labels: [{ name, net_id, sheet_id }]

Global labels propagate across ALL sheets (GND, VCC, etc.).
Hierarchical labels propagate ONLY through the matching sheet-symbol pin.
"""

import json
import uuid
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


def _ensure_keys(board: dict) -> None:
    if not isinstance(board.get("sub_sheets"), list):
        board["sub_sheets"] = []
    if not isinstance(board.get("global_labels"), list):
        board["global_labels"] = []
    if not isinstance(board.get("hierarchical_labels"), list):
        board["hierarchical_labels"] = []


# ── Union-Find ────────────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self):
        self._parent: dict[str, str] = {}

    @staticmethod
    def _key(sheet_path: str, net_id: str) -> str:
        return f"{sheet_path}::{net_id}"

    def find(self, sheet_path: str, net_id: str) -> str:
        k = self._key(sheet_path, net_id)
        if k not in self._parent:
            self._parent[k] = k
        if self._parent[k] != k:
            self._parent[k] = self._find_key(self._parent[k])
        return self._parent[k]

    def _find_key(self, k: str) -> str:
        if k not in self._parent:
            self._parent[k] = k
        if self._parent[k] != k:
            self._parent[k] = self._find_key(self._parent[k])
        return self._parent[k]

    def union(self, sp1: str, n1: str, sp2: str, n2: str) -> None:
        r1 = self.find(sp1, n1)
        r2 = self.find(sp2, n2)
        if r1 != r2:
            self._parent[r1] = r2

    def groups(self) -> list[list[str]]:
        from collections import defaultdict
        map_: dict[str, list[str]] = defaultdict(list)
        for k in list(self._parent.keys()):
            root = self._find_key(k)
            map_[root].append(k)
        return list(map_.values())


# ── Internal logic ────────────────────────────────────────────────────────────

def _add_sub_sheet(circuit_json: dict, name: str, file_id: str, position: list, pins: list) -> dict:
    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        raise ValueError("No pcb_board element found in circuit_json")
    _ensure_keys(board)
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "file_id": file_id,
        "position": position,
        "pins": [dict(p) for p in pins],
    }
    board["sub_sheets"].append(entry)
    return cloned


def _remove_sub_sheet(circuit_json: dict, sub_sheet_id: str) -> dict:
    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        raise ValueError("No pcb_board element found in circuit_json")
    _ensure_keys(board)
    board["sub_sheets"] = [s for s in board["sub_sheets"] if s.get("id") != sub_sheet_id]
    board["hierarchical_labels"] = [
        l for l in board["hierarchical_labels"] if l.get("sheet_id") != sub_sheet_id
    ]
    return cloned


def _add_global_label(circuit_json: dict, name: str, net_id: str) -> dict:
    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        raise ValueError("No pcb_board element found in circuit_json")
    _ensure_keys(board)
    labels = board["global_labels"]
    idx = next((i for i, l in enumerate(labels) if l.get("name") == name), -1)
    entry = {"name": name, "net_id": net_id}
    if idx >= 0:
        labels[idx] = entry
    else:
        labels.append(entry)
    return cloned


def _add_hierarchical_label(circuit_json: dict, name: str, net_id: str, sheet_id: str) -> dict:
    cloned = deepcopy(circuit_json)
    board = _get_board(cloned)
    if board is None:
        raise ValueError("No pcb_board element found in circuit_json")
    _ensure_keys(board)
    labels = board["hierarchical_labels"]
    idx = next(
        (i for i, l in enumerate(labels) if l.get("name") == name and l.get("sheet_id") == sheet_id),
        -1,
    )
    entry = {"name": name, "net_id": net_id, "sheet_id": sheet_id}
    if idx >= 0:
        labels[idx] = entry
    else:
        labels.append(entry)
    return cloned


def _flatten_hierarchy(top_circuit: dict, children: dict[str, dict]) -> dict:
    """Union-find based hierarchy flattening.  Returns {net_groups: [[key, ...], ...]}."""
    uf = _UnionFind()

    def process_sheet(circuit: dict, sheet_path: str) -> None:
        board = _get_board(circuit)
        if board is None:
            return
        _ensure_keys(board)

        # Merge global labels: every net under a global name merges with __global__::<name>
        for gl in board.get("global_labels", []):
            uf.union(sheet_path, gl["net_id"], "__global__", gl["name"])

        for sheet in board.get("sub_sheets", []):
            child_circuit = children.get(sheet.get("file_id"))
            if child_circuit is None:
                continue

            child_path = f"{sheet_path}/{sheet['id']}"

            child_board = _get_board(child_circuit)
            if child_board is None:
                continue
            _ensure_keys(child_board)

            # Union parent pin net ↔ child hierarchical_label net
            for pin in (sheet.get("pins") or []):
                hier_label = next(
                    (l for l in child_board["hierarchical_labels"]
                     if l.get("name") == pin["name"] and l.get("sheet_id") == sheet["id"]),
                    None,
                )
                if hier_label:
                    uf.union(sheet_path, pin["net_id"], child_path, hier_label["net_id"])

            process_sheet(child_circuit, child_path)

    process_sheet(top_circuit, "top")
    return {"net_groups": uf.groups()}


def _validate_hierarchy(top_circuit: dict, children: dict[str, dict]) -> dict:
    """Returns {ok: bool, errors: [str]}."""
    errors: list[str] = []

    def validate_sheet(circuit: dict, sheet_path: str) -> None:
        board = _get_board(circuit)
        if board is None:
            errors.append(f"{sheet_path}: not a valid pcb_board")
            return
        _ensure_keys(board)

        # Check for global label name collisions on this sheet
        global_name_to_net: dict[str, str] = {}
        for gl in board.get("global_labels", []):
            name = gl.get("name", "")
            net_id = gl.get("net_id", "")
            if name in global_name_to_net and global_name_to_net[name] != net_id:
                errors.append(
                    f'{sheet_path}: global label "{name}" has conflicting net_ids: '
                    f'"{global_name_to_net[name]}" vs "{net_id}"'
                )
            global_name_to_net[name] = net_id

        for sheet in board.get("sub_sheets", []):
            file_id = sheet.get("file_id", "")
            child_circuit = children.get(file_id)
            child_path = f"{sheet_path}/{sheet.get('id', '?')}({sheet.get('name', '?')})"

            if child_circuit is None:
                errors.append(
                    f'{child_path}: referenced file_id "{file_id}" not found in children'
                )
                continue

            child_board = _get_board(child_circuit)
            if child_board is None:
                errors.append(f"{child_path}: child circuit is not a valid pcb_board")
                continue
            _ensure_keys(child_board)

            sheet_id = sheet.get("id", "")
            child_hier = child_board.get("hierarchical_labels", [])

            # Every parent pin must have a matching hierarchical_label in child
            for pin in (sheet.get("pins") or []):
                match = next(
                    (l for l in child_hier if l.get("name") == pin["name"] and l.get("sheet_id") == sheet_id),
                    None,
                )
                if match is None:
                    errors.append(
                        f'{child_path}: pin "{pin["name"]}" has no matching hierarchical_label in child circuit'
                    )

            # Every child hier label for this sheet must have a matching parent pin
            for hl in child_hier:
                if hl.get("sheet_id") == sheet_id:
                    pin = next((p for p in (sheet.get("pins") or []) if p["name"] == hl["name"]), None)
                    if pin is None:
                        errors.append(
                            f'{child_path}: hierarchical_label "{hl["name"]}" has no matching pin on parent sheet symbol'
                        )

            validate_sheet(child_circuit, f"{sheet_path}/{sheet_id}")

    validate_sheet(top_circuit, "top")
    return {"ok": len(errors) == 0, "errors": errors}


# ── Tool: add_sub_sheet ───────────────────────────────────────────────────────

add_sub_sheet_spec = ToolSpec(
    name="add_sub_sheet",
    description=(
        "Add a sub-sheet symbol to a parent circuit. The sub-sheet references a child "
        ".circuit file by file_id and exposes hierarchical pins that connect to the "
        "child sheet's hierarchical_labels. Returns the updated circuit_json with a "
        "new sub_sheets entry including a generated id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object", "description": "The parent CircuitJSON board to modify."},
            "name": {"type": "string", "description": "Human-readable label for this sheet instance."},
            "file_id": {"type": "string", "description": "UUID of the child circuit file."},
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Schematic placement position [x, y].",
            },
            "pins": {
                "type": "array",
                "description": "Hierarchical pins exposed by this sheet symbol.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["input", "output", "bidirectional", "passive"]},
                        "net_id": {"type": "string"},
                    },
                    "required": ["name", "type", "net_id"],
                },
            },
        },
        "required": ["circuit_json", "name", "file_id"],
    },
)


@register(add_sub_sheet_spec, write=True)
async def add_sub_sheet(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")

    name = (a.get("name") or "").strip()
    file_id = (a.get("file_id") or "").strip()
    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    position = a.get("position", [0, 0])
    if not isinstance(position, list) or len(position) != 2:
        return err_payload("position must be [x, y]", "BAD_ARGS")

    pins = a.get("pins", [])
    if not isinstance(pins, list):
        return err_payload("pins must be an array", "BAD_ARGS")

    try:
        cloned = _add_sub_sheet(circuit_json, name, file_id, position, pins)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    new_id = cloned if not isinstance(cloned, dict) else \
        next((s["id"] for s in _get_board(cloned).get("sub_sheets", [])[-1:]), None)
    # Simpler: get the last sheet's id
    board = _get_board(cloned)
    new_sheet_id = board["sub_sheets"][-1]["id"] if board and board.get("sub_sheets") else None
    return ok_payload({"circuit_json": cloned, "id": new_sheet_id})


# ── Tool: remove_sub_sheet ────────────────────────────────────────────────────

remove_sub_sheet_spec = ToolSpec(
    name="remove_sub_sheet",
    description=(
        "Remove a sub-sheet symbol from a circuit by its id. Also removes any "
        "hierarchical_labels in the same circuit that were scoped to that sheet. "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "sub_sheet_id": {"type": "string", "description": "The sub_sheet.id to remove."},
        },
        "required": ["circuit_json", "sub_sheet_id"],
    },
)


@register(remove_sub_sheet_spec, write=True)
async def remove_sub_sheet(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    sub_sheet_id = (a.get("sub_sheet_id") or "").strip()
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not sub_sheet_id:
        return err_payload("sub_sheet_id is required", "BAD_ARGS")

    try:
        cloned = _remove_sub_sheet(circuit_json, sub_sheet_id)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    return ok_payload({"circuit_json": cloned})


# ── Tool: add_global_label ────────────────────────────────────────────────────

add_global_label_spec = ToolSpec(
    name="add_global_label",
    description=(
        "Add or update a global label on a circuit sheet. Global labels with the same "
        "name automatically connect across ALL sheets in a hierarchy (e.g. GND, VCC). "
        "Calling again with the same name updates the net_id. "
        "Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "name": {"type": "string", "description": "Global net name, e.g. 'GND' or 'VCC'."},
            "net_id": {"type": "string", "description": "The local net identifier on this sheet."},
        },
        "required": ["circuit_json", "name", "net_id"],
    },
)


@register(add_global_label_spec, write=True)
async def add_global_label(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    name = (a.get("name") or "").strip()
    net_id = (a.get("net_id") or "").strip()
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not net_id:
        return err_payload("net_id is required", "BAD_ARGS")

    try:
        cloned = _add_global_label(circuit_json, name, net_id)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    return ok_payload({"circuit_json": cloned, "name": name})


# ── Tool: add_hierarchical_label ──────────────────────────────────────────────

add_hierarchical_label_spec = ToolSpec(
    name="add_hierarchical_label",
    description=(
        "Add or update a hierarchical label on a child circuit sheet. Hierarchical "
        "labels connect ONLY through the parent's matching sheet-symbol pin; they do "
        "not propagate globally. The sheet_id must match the sub_sheet.id in the "
        "parent circuit. Returns the updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "name": {"type": "string", "description": "Pin name that must match the parent sheet symbol pin."},
            "net_id": {"type": "string", "description": "The local net identifier on this child sheet."},
            "sheet_id": {"type": "string", "description": "The sub_sheet.id in the parent that owns this label."},
        },
        "required": ["circuit_json", "name", "net_id", "sheet_id"],
    },
)


@register(add_hierarchical_label_spec, write=True)
async def add_hierarchical_label(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    name = (a.get("name") or "").strip()
    net_id = (a.get("net_id") or "").strip()
    sheet_id = (a.get("sheet_id") or "").strip()
    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not name:
        return err_payload("name is required", "BAD_ARGS")
    if not net_id:
        return err_payload("net_id is required", "BAD_ARGS")
    if not sheet_id:
        return err_payload("sheet_id is required", "BAD_ARGS")

    try:
        cloned = _add_hierarchical_label(circuit_json, name, net_id, sheet_id)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    return ok_payload({"circuit_json": cloned, "name": name, "sheet_id": sheet_id})


# ── Tool: flatten_hierarchy ───────────────────────────────────────────────────

flatten_hierarchy_spec = ToolSpec(
    name="flatten_hierarchy",
    description=(
        "Flatten a multi-sheet hierarchy into a single net equivalence list using "
        "union-find over (sheet_path, net_id) tuples. "
        "Global labels across all sheets are merged by label name. "
        "Sub-sheet pins are merged with the matching child hierarchical_label. "
        "Returns {net_groups: [[key, ...], ...]} where each group contains electrically "
        "equivalent 'sheet_path::net_id' keys."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "top_circuit_json": {"type": "object", "description": "The top-level CircuitJSON board."},
            "children": {
                "type": "object",
                "description": "Map of file_id → circuit_json for all referenced child sheets.",
                "additionalProperties": {"type": "object"},
            },
        },
        "required": ["top_circuit_json"],
    },
)


@register(flatten_hierarchy_spec, write=False)
async def flatten_hierarchy(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    top_circuit_json = a.get("top_circuit_json")
    if not top_circuit_json:
        return err_payload("top_circuit_json is required", "BAD_ARGS")

    children = a.get("children") or {}
    if not isinstance(children, dict):
        return err_payload("children must be an object mapping file_id → circuit_json", "BAD_ARGS")

    result = _flatten_hierarchy(top_circuit_json, children)
    return ok_payload(result)


# ── Tool: validate_hierarchy ──────────────────────────────────────────────────

validate_hierarchy_spec = ToolSpec(
    name="validate_hierarchy",
    description=(
        "Validate a multi-sheet hierarchy. Checks: "
        "(1) every sub_sheet file_id is present in children; "
        "(2) every sheet-symbol pin has a matching hierarchical_label in the child; "
        "(3) no global label name collisions (same name → different net_id on same sheet); "
        "(4) no orphaned hierarchical_labels (label exists but no matching pin on parent). "
        "Returns {ok: bool, errors: [string]}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "top_circuit_json": {"type": "object"},
            "children": {
                "type": "object",
                "additionalProperties": {"type": "object"},
            },
        },
        "required": ["top_circuit_json"],
    },
)


@register(validate_hierarchy_spec, write=False)
async def validate_hierarchy(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    top_circuit_json = a.get("top_circuit_json")
    if not top_circuit_json:
        return err_payload("top_circuit_json is required", "BAD_ARGS")

    children = a.get("children") or {}
    if not isinstance(children, dict):
        return err_payload("children must be an object mapping file_id → circuit_json", "BAD_ARGS")

    result = _validate_hierarchy(top_circuit_json, children)
    return ok_payload(result)
