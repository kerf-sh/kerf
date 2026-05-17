# feature_hole_pattern_from_sketch — Sketch-Driven Hole Pattern

Append a `hole_pattern` node to a `.feature` file.  FreeCAD-parity shortcut: reads every
`type:'point'` entity in a sketch and cuts one cylinder (diameter × depth) per point
through the target body.  Fully parametric — editing the sketch and re-evaluating
automatically updates all holes.

OCCT path (per point): `cutCylinderAtPoint(body, x, y, diameter, depth)`.

---

## When to use

Keywords: hole pattern, bolt circle, hole array, hole grid, multiple holes, hole from
sketch, sketch-driven holes, parametric holes, hole_pattern, cut cylinder array,
bolt hole pattern, fastener holes from sketch.

---

## Entrypoints

### `validate_hole_pattern_args(sketch_path, diameter, depth) -> tuple[str|None, str|None]`

Pure validation.  Returns `(error_msg, error_code)` or `(None, None)`.

---

### `extract_sketch_points(sketch_json) -> list[dict]`

Parse a sketch (JSON string or dict) and return all `type:'point'` entities,
excluding the implicit origin (`id == 'origin'`).

```python
points = extract_sketch_points(sketch_json)
# [{"x": 20.0, "y": 15.0}, {"x": 60.0, "y": 15.0}, ...]
```

Non-point entities (lines, arcs, circles) are silently ignored — they may be used as
construction geometry alongside the hole-centre points.

---

### `build_hole_pattern_node(node_id, sketch_path, diameter, depth, target_id, name) -> dict`

Build the feature-node dict:
```json
{
  "id": "hole_pattern-1",
  "op": "hole_pattern",
  "sketch_path": "/hole-grid.sketch",
  "diameter": 3.0,
  "depth": 8.0,
  "target_id": "pad-1"
}
```

`target_id` is optional — when omitted the worker cuts into the current body in the timeline.

---

## LLM tool

**Name:** `feature_hole_pattern_from_sketch`

**Required args:** `file_id` (UUID), `sketch_path` (ends in `.sketch`, contains ≥1 `type:'point'` entity), `diameter` (> 0 mm), `depth` (> 0 mm)

**Optional args:** `target_id`, `name`, `id`

**Returns:**
```json
{
  "file_id": "...",
  "id": "hole_pattern-1",
  "op": "hole_pattern"
}
```

If the sketch has no `type:'point'` entities the OCCT worker raises an error at evaluation
time (not at node-write time).

---

## Sketch point format

The sketch file must contain entities of the form:
```json
{
  "id": "pt-1",
  "type": "point",
  "x": 20.0,
  "y": 15.0
}
```

Use `sketch_add_entity` with `type:'point'` to add hole centres to the sketch before
calling this tool.  Any number of lines, arcs, or circles can coexist in the same sketch
as visual construction guides — they are ignored by the pattern evaluator.

---

## Usage snippets

```python
from kerf_cad_core.feature_hole_pattern_from_sketch import (
    build_hole_pattern_node, extract_sketch_points
)

# Parse existing sketch
sketch_json = '{"entities": [{"id": "p1", "type": "point", "x": 20, "y": 15}]}'
points = extract_sketch_points(sketch_json)
# [{"x": 20.0, "y": 15.0}]

node = build_hole_pattern_node("hpat-1", "/bolt-circle.sketch", 6.0, 20.0, "pad-1")
# node["op"] == "hole_pattern"
# node["diameter"] == 6.0
# node["depth"] == 20.0
```

```python
# LLM tool call — 4-hole M5 bolt pattern
# {
#   "tool": "feature_hole_pattern_from_sketch",
#   "file_id": "abc...",
#   "sketch_path": "/m5-pattern.sketch",
#   "diameter": 5.0,
#   "depth": 15.0,
#   "target_id": "pad-1"
# }
```

---

## Caveats

- All holes share the same `diameter` and `depth` — use multiple `hole_pattern` nodes for
  mixed-size patterns.
- Hole direction is always normal to the XY sketch plane; inclined holes require the
  `feature_cut_from_sketch` approach instead.
- `countersink_diameter` / `countersink_depth` are reserved for a future version; do not
  populate them in current usage.
- The sketch origin sentinel (`id == 'origin'`) is excluded automatically.
