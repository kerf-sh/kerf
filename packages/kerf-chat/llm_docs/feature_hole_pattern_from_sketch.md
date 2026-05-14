# `feature_hole_pattern_from_sketch` — parametric hole array from a sketch

## What it does

Appends a single **`hole_pattern`** node to a `.feature` file.  At evaluation
time the OCCT worker reads every `type:'point'` entity in the sketch and cuts
one cylinder per point through the running body.  The result is N identical
holes sharing the same `diameter` and `depth`, located at the positions the
user drew in the sketch.

Because the op stores the sketch path (not a list of expanded coordinates), the
pattern is **parametric**: move a point in the sketch and re-evaluate — all N
holes re-cut automatically without touching the feature node.

## When to use

| Situation | Use this tool |
|---|---|
| Bolt-circle or mounting pattern | yes |
| Regular grid of fastener holes | yes |
| Single isolated hole | use `feature_hole` instead |
| Holes at different diameters | not supported in v1 — use multiple `hole` nodes |

## Workflow

1. Create (or open) a sketch that will hold the hole centres.
2. Add one `type:'point'` entity per hole using `sketch_add_entity`:
   ```json
   { "type": "point", "x": 20, "y": 20 }
   ```
3. Call `feature_hole_pattern_from_sketch` with the sketch path, the target
   body, diameter, and depth.

Non-point entities in the same sketch (lines, arcs, construction circles) are
**silently ignored** — you can mix them in as visual guides.

## Tool input

```json
{
  "file_id": "<uuid of the .feature file>",
  "sketch_path": "/hole-grid.sketch",
  "diameter": 3.0,
  "depth": 8.0,
  "target_id": "pad-1",
  "name": "mounting holes"
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `file_id` | yes | — | UUID of the `.feature` file |
| `sketch_path` | yes | — | Path to the points sketch; must end in `.sketch` |
| `diameter` | yes | — | Hole diameter in mm, > 0 |
| `depth` | yes | — | Hole depth in mm, > 0 |
| `target_id` | no | (current body) | Feature-node id of the body to cut into |
| `name` | no | — | Human-readable label shown in the feature tree |
| `id` | no | auto | Explicit node id (e.g. `"hpat-1"`) |

## Node emitted

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

## OCCT pathway

For each `(x, y)` point in the sketch the worker calls:

```
cutCylinderAtPoint(body, x, y, diameter, depth)
```

which is the same primitive used by `opHole`.  The cylinder is double the
requested depth and centred on the sketch plane so it always punches fully
through bodies sitting on either side.  Holes are cut sequentially on the same
body; the final body is the result.

## Edge cases

| Condition | Behaviour |
|---|---|
| Sketch has zero point entities | Worker error: "sketch has no point entities". Add `type:'point'` entities first. |
| All points coincide | N cuts execute; the body is equivalent to 1 cut — acceptable. |
| Diameter ≥ body wall thickness | Through-hole (desired behaviour — same as `hole`). |
| Mixed non-point entities | Ignored silently; document for the user if asked. |

## v1 limitations / reserved fields

`countersink_diameter` and `countersink_depth` are reserved for a future
patch.  Do **not** populate them — they have no effect in v1.  To get a
countersunk pattern in v1, follow the `hole_pattern` with a second
`hole_pattern` using the countersink diameter and a shallower depth.

## Example

```python
# 4-bolt square pattern on a 50 × 50 × 10 pad
sketch_add_entity(sketch_file_id, {"type": "point", "x":  10, "y":  10})
sketch_add_entity(sketch_file_id, {"type": "point", "x":  40, "y":  10})
sketch_add_entity(sketch_file_id, {"type": "point", "x":  40, "y":  40})
sketch_add_entity(sketch_file_id, {"type": "point", "x":  10, "y":  40})

feature_hole_pattern_from_sketch(
    file_id    = "<feature-file-uuid>",
    sketch_path = "/bolt-circle.sketch",
    diameter   = 3.2,   # M3 clearance
    depth      = 8.0,
    target_id  = "pad-1",
)
```
