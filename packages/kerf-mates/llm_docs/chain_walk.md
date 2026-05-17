# kerf-mates · chain_walk.py

BFS graph walk for tolerance chain extraction between two assembly features.

## Entrypoints

### `build_chain_from_assembly(assembly_doc, start_ref, end_ref, *, fetch_part_dim=None)`

Builds the dimensional chain between `start_ref` and `end_ref` by walking the
mate graph via BFS.

```python
from kerf_mates.chain_walk import build_chain_from_assembly

chain = build_chain_from_assembly(
    assembly_doc,
    start_ref="comp_A::face_left",
    end_ref="comp_B::face_right",
    fetch_part_dim=my_dim_lookup,   # optional callable(component_id, feature_id) -> float
)
# Returns list[ChainEntry] on success, or {"error": str} on failure.
```

Returns a list of `ChainEntry` objects describing each step:

| Field | Description |
|---|---|
| `component_id` | Component the step belongs to |
| `feature_id` | Feature at this step |
| `mate` | `MateConstraint` or `None` (intra-component step) |
| `contribution` | Dimensional contribution (mm) |

## Graph representation

Nodes are keyed as `"{component_id}::{feature_id}"`.

Edges:
- **Inter-component** (mate edge): keyed by the `MateConstraint` object; contributes distance/angle value from the constraint.
- **Intra-component** (part dimension edge): `mate=None`; dimension retrieved via `fetch_part_dim` callback if provided, else 0.

## Zero-contribution constraint types

The following mate types add a graph edge but contribute **zero dimensional
offset** to the chain:

`_ZERO_CONTRIBUTION_TYPES` = `{coincident, concentric, parallel, perpendicular, tangent}`

Only `distance` and `angle` constraints carry a non-zero numeric contribution.

## Usage pattern

```python
# 1. Build the chain
chain = build_chain_from_assembly(assembly, "A::face_left", "B::face_right")

# 2. Extract contributions for tolerance stack-up
contributions = [entry.contribution for entry in chain if entry.contribution]

# 3. Feed into tolerance.py
from kerf_mates.tolerance import worst_case, rss
print("WC:", worst_case(contributions))
print("RSS:", rss(contributions))
```

## Error handling

Returns `{"error": "no path found"}` when no BFS path exists between the two
refs. Returns `{"error": "ref not found: ..."}` if either ref is not in the
graph.

## LLM tool: `tolerance_auto_chain`

Registered in `kerf_mates.tools`. Accepts `assembly_file_id`, `start_ref`,
`end_ref`; calls `build_chain_from_assembly`, then runs worst-case + RSS
analysis on the extracted chain. Returns:

```json
{
  "chain_length": 4,
  "contributions": [0.05, 0.03],
  "worst_case": 0.08,
  "rss": 0.058,
  "warnings": []
}
```
