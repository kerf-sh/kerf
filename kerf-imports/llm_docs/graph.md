# Parametric Graph — `.graph` file kind

A `.graph` file is a DAG of nodes. The LLM authors and edits graphs as JSON; the visual editor renders them. Re-evaluation propagates parameter changes through the DAG.

---

## Schema

```jsonc
{
  "version": 1,
  "name": "Parametric chair",
  "nodes": [
    { "id": "n1", "op": "number_slider", "params": { "min": 100, "max": 1000, "value": 450, "step": 10 }, "inputs": [] },
    { "id": "n2", "op": "series",        "params": { "start": 0, "count": "@n1.out", "step": 1 },          "inputs": ["n1"] },
    { "id": "n3", "op": "feature_sweep2","params": { "rail1": "@n4.out", "rail2": "@n5.out" },              "inputs": ["n4","n5"] }
  ],
  "outputs": ["n3"]
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `version` | int | Always `1` |
| `name` | string | Display name |
| `nodes` | array | Ordered list of node objects |
| `outputs` | string[] | Node ids whose values are the graph outputs |

### Node fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique, auto-assigned (`n1`, `n2`, …) |
| `op` | string | Op name — built-in or Kerf tool name |
| `params` | object | Op parameters; values may be literals or `@nX.out` references |
| `inputs` | string[] | Explicit upstream node ids (used for topology; params `@ref` are primary) |

### `@nX.out` references

Any param value of the form `"@nX.out"` is resolved to the output of node `nX` before the op is called. References form the DAG edges.

---

## Built-in ops (pure data, no server call)

| Op | Key params | Output |
|---|---|---|
| `number_slider` | `value`, `min?`, `max?`, `step?` | `float` |
| `integer_slider` | `value`, `min?`, `max?`, `step?` | `int` |
| `panel` | `value` | passthrough |
| `series` | `start`, `count`, `step` | `[float]` |
| `range` | `from`, `to`, `count` | `[float]` evenly spaced including endpoints |
| `lerp` | `a`, `b`, `t` | `float` — `a + (b-a)*t` |
| `map_each` | `array`, `op`, `op_params` | `[result]` — applies `op` to each element |
| `expression` | `expr` (math string), `inputs` (named vars) | `float` or error |

---

## Tool-op invocation pattern

When a node's `op` matches a Kerf LLM tool name (e.g. `feature_sweep2`), `evaluate_graph` emits `{__defer_to_backend: true, op, params}`. The caller dispatches these to the tool executor with resolved params.

Kerf tool ops include: `feature_extrude`, `feature_revolve`, `feature_sweep2`, `feature_loft`, `feature_chamfer`, `feature_fillet`, `feature_shell`, `feature_mirror`, `feature_helix`, `sketch.read`, `sketch.create`, `sketch_offset`, `sketch_trim`, `sketch_extend`, `material.read`, `assembly.add_part`, `assembly.constrain`.

---

## LLM tools

### `create_graph({name?, folder_path?})`
Creates a new empty `.graph` file. Returns `{file_id, name, graph}`.

### `add_graph_node({file_id, op, params?, inputs?, make_output?})`
Appends a node. Auto-assigns `id`. If `make_output: true`, adds the node to `graph.outputs`. Returns `{node_id, graph}`.

### `connect_graph_nodes({file_id, source_id, target_id, target_param})`
Sets `target_id.params[target_param] = "@source_id.out"` and adds `source_id` to `target_id.inputs`.

### `set_graph_param({file_id, node_id, param_name, value})`
Updates a single param on a node (e.g. change a slider value). Returns `{node_id, param_name, value, graph}`.

### `evaluate_graph({file_id})`
Walks the DAG in topological order, evaluates built-ins in Python, emits defer markers for tool ops. Returns `{outputs, intermediate, errors}`.

---

## Examples

### 1. Parametric chair — seat height driven by slider

```jsonc
// 1. Create graph
create_graph({ "name": "Parametric chair" })
// -> { "file_id": "abc-123" }

// 2. Add a slider for seat height (mm)
add_graph_node({ "file_id": "abc-123", "op": "number_slider", "params": { "value": 450, "min": 350, "max": 700, "step": 10 } })
// -> node n1

// 3. Add expression: leg_height = seat_height - 50
add_graph_node({ "file_id": "abc-123", "op": "expression", "params": { "expr": "h - 50", "inputs": { "h": "@n1.out" } }, "inputs": ["n1"] })
// -> node n2

// 4. Evaluate
evaluate_graph({ "file_id": "abc-123" })
// -> { "outputs": {}, "intermediate": { "n1": 450, "n2": 400 }, "errors": [] }

// 5. Change seat height
set_graph_param({ "file_id": "abc-123", "node_id": "n1", "param_name": "value", "value": 500 })
evaluate_graph({ "file_id": "abc-123" })
// -> intermediate.n2 = 450
```

---

### 2. Grid of points — range × expression

```jsonc
// range 0..1000 in 10 steps → X coords
add_graph_node({ "op": "range", "params": { "from": 0, "to": 1000, "count": 10 } })
// -> n1: [0, 111.1, 222.2, …, 1000]

// expression: y = sin(x/100)*50
add_graph_node({
  "op": "map_each",
  "params": { "array": "@n1.out", "op": "expression", "op_params": { "expr": "sin(x / 100) * 50", "inputs": { "x": 0 } } },
  "inputs": ["n1"]
})
// -> n2: [0, 47.9, 80.5, …] — sine wave heights
```

---

### 3. `map_each` applies sketch_offset to a list of curves

```jsonc
// Assume n1 holds a list of sketch file_ids from a panel
add_graph_node({ "op": "panel", "params": { "value": ["sketch-id-1", "sketch-id-2", "sketch-id-3"] } })
// -> n1

// map_each defers sketch_offset to backend for each curve
add_graph_node({
  "op": "map_each",
  "params": { "array": "@n1.out", "op": "sketch_offset", "op_params": { "distance": 10 } },
  "inputs": ["n1"],
  "make_output": true
})
// evaluate_graph returns __defer_to_backend markers which the orchestrator dispatches
```
