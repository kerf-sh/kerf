"""graph.py — LLM tools for the .graph parametric file kind.

A .graph file stores a DAG of nodes. Each node is either a built-in op
(number_slider, series, lerp, expression, …) or a wrapper around a Kerf LLM
tool (feature_sweep2, sketch_offset, …). Re-evaluation walks the DAG in
topological order, resolves @nX.out references, and calls either the built-in
Python implementation or the registered tool executor.
"""

import json
import math
import uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

# ── Schema version ────────────────────────────────────────────────────────────

GRAPH_VERSION = 1
FILE_EXTENSION = "graph"

# ── Built-in ops (pure Python) ────────────────────────────────────────────────

def _builtin_number_slider(params: dict) -> float:
    return float(params.get("value", 0))

def _builtin_integer_slider(params: dict) -> int:
    return int(round(float(params.get("value", 0))))

def _builtin_panel(params: dict):
    return params.get("value")

def _builtin_series(params: dict) -> list:
    start = float(params.get("start", 0))
    count = max(0, int(params.get("count", 0)))
    step = float(params.get("step", 1))
    return [start + i * step for i in range(count)]

def _builtin_range(params: dict) -> list:
    from_ = float(params.get("from", 0))
    to = float(params.get("to", 1))
    count = max(2, int(params.get("count", 2)))
    if count == 1:
        return [from_]
    step = (to - from_) / (count - 1)
    return [from_ + i * step for i in range(count)]

def _builtin_lerp(params: dict) -> float:
    a = float(params.get("a", 0))
    b = float(params.get("b", 1))
    t = float(params.get("t", 0.5))
    return a + (b - a) * t

def _builtin_expression(params: dict):
    expr = params.get("expr", "")
    if not expr:
        return None
    inputs = params.get("inputs", {})
    # Safe eval: only math operations and named numeric inputs
    safe_ns = {k: float(v) for k, v in inputs.items() if isinstance(v, (int, float))}
    safe_ns.update({k: v for k, v in math.__dict__.items() if not k.startswith("_")})
    try:
        return eval(expr, {"__builtins__": {}}, safe_ns)  # noqa: S307
    except Exception as e:
        return {"__error": f"expression: {e}"}

def _builtin_map_each(params: dict) -> list:
    arr = params.get("array", [])
    if not isinstance(arr, list):
        return []
    op = params.get("op", "")
    op_params = params.get("op_params", {})
    op_fn = BUILTIN_OPS.get(op)
    if op_fn:
        return [op_fn({**op_params, "value": item}) for item in arr]
    return [{"__defer_to_backend": True, "op": op, "params": {**op_params, "input": item}} for item in arr]

BUILTIN_OPS: dict = {
    "number_slider": _builtin_number_slider,
    "integer_slider": _builtin_integer_slider,
    "panel": _builtin_panel,
    "series": _builtin_series,
    "range": _builtin_range,
    "lerp": _builtin_lerp,
    "expression": _builtin_expression,
    "map_each": _builtin_map_each,
}

# ── DAG helpers ───────────────────────────────────────────────────────────────

import re as _re

def _collect_refs(v, refs: list) -> None:
    """Recursively collect @nX.out node ids from a value."""
    if isinstance(v, str) and v.startswith("@"):
        m = _re.match(r"^@([^.]+)\.out$", v)
        if m:
            refs.append(m.group(1))
    elif isinstance(v, list):
        for el in v:
            _collect_refs(el, refs)
    elif isinstance(v, dict):
        for v2 in v.values():
            _collect_refs(v2, refs)

def _param_refs(params: dict) -> list[str]:
    """Return all node ids referenced as @nX.out in params (recursive)."""
    refs: list[str] = []
    for v in params.values():
        _collect_refs(v, refs)
    return refs

def _resolve_value(v, results: dict):
    """Resolve a single value — handles string refs, lists, and nested dicts."""
    if isinstance(v, str) and v.startswith("@"):
        m = _re.match(r"^@([^.]+)\.out$", v)
        if m:
            return results.get(m.group(1), {"__unresolved": v})
        return v
    if isinstance(v, list):
        return [_resolve_value(el, results) for el in v]
    if isinstance(v, dict):
        return {k2: _resolve_value(v2, results) for k2, v2 in v.items()}
    return v

def _resolve_params(params: dict, results: dict) -> dict:
    """Substitute @nX.out references (recursive) with their resolved values."""
    return {k: _resolve_value(v, results) for k, v in params.items()}

def _topological_order(nodes: list) -> list[str]:
    """Kahn's algorithm. Raises ValueError on cycle."""
    ids = [n["id"] for n in nodes]
    id_set = set(ids)
    in_degree: dict[str, int] = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}

    for node in nodes:
        deps = set(_param_refs(node.get("params", {})) + node.get("inputs", []))
        for dep in deps:
            if dep in id_set:
                adj[dep].append(node["id"])
                in_degree[node["id"]] += 1

    queue = [i for i in ids if in_degree[i] == 0]
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(ids):
        raise ValueError("Cycle detected in graph")
    return order

def _evaluate_graph_data(graph: dict, extra_ops: dict | None = None) -> dict:
    """
    Walk DAG and evaluate all nodes.
    Returns {outputs, intermediate, errors}.
    """
    nodes = graph.get("nodes", [])
    all_ops = {**BUILTIN_OPS, **(extra_ops or {})}
    node_map = {n["id"]: n for n in nodes}
    results: dict = {}
    errors: list[str] = []

    try:
        order = _topological_order(nodes)
    except ValueError as e:
        return {"outputs": {}, "intermediate": {}, "errors": [str(e)]}

    for nid in order:
        node = node_map.get(nid)
        if not node:
            continue
        op = node.get("op", "")
        op_fn = all_ops.get(op)
        if not op_fn:
            err = f"unknown op: {op} on node {nid}"
            errors.append(err)
            results[nid] = {"__error": err}
            continue
        resolved = _resolve_params(node.get("params", {}), results)
        try:
            results[nid] = op_fn(resolved)
        except Exception as e:
            msg = f"node {nid} ({op}): {e}"
            errors.append(msg)
            results[nid] = {"__error": msg}

    output_ids = graph.get("outputs", [])
    outputs = {oid: results.get(oid) for oid in output_ids}
    intermediate = {k: v for k, v in results.items() if k not in set(output_ids)}
    return {"outputs": outputs, "intermediate": intermediate, "errors": errors}

def _default_graph(name: str = "Untitled") -> dict:
    return {"version": GRAPH_VERSION, "name": name, "nodes": [], "outputs": []}

def _gen_id(nodes: list) -> str:
    existing = {n["id"] for n in nodes}
    i = len(nodes) + 1
    while f"n{i}" in existing:
        i += 1
    return f"n{i}"

# ── create_graph ──────────────────────────────────────────────────────────────

create_graph_spec = ToolSpec(
    name="create_graph",
    description=(
        "Create a new parametric graph (.graph) file. "
        "Returns file_id. The graph is initially empty; add nodes with add_graph_node."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Graph display name (e.g. 'Parametric chair')"},
            "folder_path": {"type": "string", "description": "Folder path in project (default: /)"},
        },
        "required": [],
    },
)

@register(create_graph_spec, write=True)
async def run_create_graph(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    name = a.get("name") or "Untitled"
    graph = _default_graph(name)
    content_json = json.dumps(graph, indent=2)
    file_name = name.replace(" ", "_") + f".{FILE_EXTENSION}"

    file_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES($1,$2,$3,$4,$5) RETURNING id",
        ctx.project_id, None, file_name, FILE_EXTENSION, content_json,
    )
    return ok_payload({"file_id": str(file_id), "name": name, "graph": graph})

# ── add_graph_node ────────────────────────────────────────────────────────────

add_graph_node_spec = ToolSpec(
    name="add_graph_node",
    description=(
        "Add a node to an existing .graph file. "
        "op must be a built-in op (number_slider, series, lerp, expression, range, map_each, panel, integer_slider) "
        "or a Kerf tool op name (feature_sweep2, sketch_offset, …). "
        "Returns the updated graph and the new node id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "op": {"type": "string"},
            "params": {"type": "object"},
            "inputs": {"type": "array", "items": {"type": "string"}},
            "make_output": {"type": "boolean", "description": "If true, add this node to graph.outputs"},
        },
        "required": ["file_id", "op"],
    },
)

@register(add_graph_node_spec, write=True)
async def run_add_graph_node(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")

    graph = json.loads(row["content"])
    op = a.get("op", "")
    if not op:
        return err_payload("op is required", "BAD_ARGS")

    node_id = _gen_id(graph.get("nodes", []))
    node = {
        "id": node_id,
        "op": op,
        "params": a.get("params") or {},
        "inputs": a.get("inputs") or [],
    }
    graph["nodes"] = graph.get("nodes", []) + [node]
    if a.get("make_output"):
        graph["outputs"] = graph.get("outputs", []) + [node_id]

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2 AND project_id=$3",
        json.dumps(graph, indent=2), fid, ctx.project_id,
    )
    return ok_payload({"node_id": node_id, "graph": graph})

# ── connect_graph_nodes ───────────────────────────────────────────────────────

connect_graph_nodes_spec = ToolSpec(
    name="connect_graph_nodes",
    description=(
        "Wire source_id.out into target_id's target_param as an @ref. "
        "Automatically adds source_id to target_id.inputs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "source_id": {"type": "string"},
            "target_id": {"type": "string"},
            "target_param": {"type": "string"},
        },
        "required": ["file_id", "source_id", "target_id", "target_param"],
    },
)

@register(connect_graph_nodes_spec, write=True)
async def run_connect_graph_nodes(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")

    graph = json.loads(row["content"])
    source_id = a.get("source_id", "")
    target_id = a.get("target_id", "")
    target_param = a.get("target_param", "")

    if not all([source_id, target_id, target_param]):
        return err_payload("source_id, target_id, target_param are required", "BAD_ARGS")

    nodes = []
    for node in graph.get("nodes", []):
        if node["id"] == target_id:
            params = {**node.get("params", {}), target_param: f"@{source_id}.out"}
            inputs = list(dict.fromkeys(node.get("inputs", []) + [source_id]))
            nodes.append({**node, "params": params, "inputs": inputs})
        else:
            nodes.append(node)
    graph["nodes"] = nodes

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2 AND project_id=$3",
        json.dumps(graph, indent=2), fid, ctx.project_id,
    )
    return ok_payload({"graph": graph})

# ── set_graph_param ───────────────────────────────────────────────────────────

set_graph_param_spec = ToolSpec(
    name="set_graph_param",
    description="Update a single parameter on a graph node (e.g. slider value, expression string).",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "node_id": {"type": "string"},
            "param_name": {"type": "string"},
            "value": {},
        },
        "required": ["file_id", "node_id", "param_name", "value"],
    },
)

@register(set_graph_param_spec, write=True)
async def run_set_graph_param(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")

    graph = json.loads(row["content"])
    node_id = a.get("node_id", "")
    param_name = a.get("param_name", "")
    value = a.get("value")

    nodes = []
    found = False
    for node in graph.get("nodes", []):
        if node["id"] == node_id:
            found = True
            params = {**node.get("params", {}), param_name: value}
            nodes.append({**node, "params": params})
        else:
            nodes.append(node)
    graph["nodes"] = nodes

    if not found:
        return err_payload(f"node not found: {node_id}", "NOT_FOUND")

    await ctx.pool.execute(
        "UPDATE files SET content=$1, updated_at=now() WHERE id=$2 AND project_id=$3",
        json.dumps(graph, indent=2), fid, ctx.project_id,
    )
    return ok_payload({"node_id": node_id, "param_name": param_name, "value": value, "graph": graph})

# ── evaluate_graph ────────────────────────────────────────────────────────────

evaluate_graph_spec = ToolSpec(
    name="evaluate_graph",
    description=(
        "Evaluate all nodes in a .graph file in topological order. "
        "Built-in ops are evaluated in Python. Kerf tool ops marked as __defer_to_backend "
        "are identified in the output for further dispatch. "
        "Returns outputs (nodes listed in graph.outputs), intermediate results, and any errors."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
        },
        "required": ["file_id"],
    },
)

@register(evaluate_graph_spec, write=False)
async def run_evaluate_graph(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id is not a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")

    graph = json.loads(row["content"])
    result = _evaluate_graph_data(graph)
    return ok_payload(result)
